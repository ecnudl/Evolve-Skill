"""Opt-in lexical JSON recovery for native optimizer replies, not Skill repair.

Policy v1's sole repair inserts a backslash before an illegal JSON escape inside
a quoted string. Thus ``\\-`` becomes the literal two-character text backslash +
hyphen, never a guessed escape or deleted character. Policy v2 (learning v9) adds
one more lexical repair: a raw control character inside a quoted string (a model
writing a real newline inside a JSON string, as happened on 10/7) is replaced by
its JSON escape, so the decoded text is unchanged. No optional tolerant parser,
object extraction, brace completion, or schema/value rewriting is used.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

POLICY = "strict-json-invalid-escape-v1"
CONTROL_POLICY = "strict-json-invalid-escape-control-v2"
POLICIES = (POLICY, CONTROL_POLICY)
MAX_RESPONSE_BYTES = 4_000_000
_LEGAL_ESCAPES = frozenset('"\\/bfnrtu')
_CONTROL_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}


class NativeJSONError(ValueError):
    """A content-free rejection reason with a separately recordable audit."""

    def __init__(self, reason, audit=None):
        super().__init__(reason)
        self.reason = reason
        self.audit = audit or {}


def _utf8(text):
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        raise NativeJSONError("invalid_unicode_scalar") from None


def strict_native_object(text):
    """Read exactly one JSON object, rejecting duplicates and nonfinite numbers."""
    if type(text) is not str or len(_utf8(text)) > MAX_RESPONSE_BYTES:
        raise NativeJSONError("invalid_or_oversized_json_text")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise NativeJSONError("duplicate_json_key")
            result[key] = value
        return result

    def constant(_):
        raise NativeJSONError("nonfinite_json_number")

    def number(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise NativeJSONError("nonfinite_json_number")
        return value

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except NativeJSONError:
        raise
    except (ValueError, RecursionError):
        raise NativeJSONError("invalid_json_document") from None
    if type(value) is not dict:
        raise NativeJSONError("json_object_required")
    # Escaped lone surrogates otherwise survive json.loads and later fail when
    # the native Skill/audit is encoded. Reject, rather than replace, them here.
    try:
        _utf8(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except RecursionError:
        raise NativeJSONError("invalid_json_document") from None
    return value


def _body(raw):
    start = len(raw) - len(raw.lstrip())
    end = len(raw.rstrip())
    text = raw[start:end]
    envelope = "document"
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(?P<body>.*?)\r?\n?```", text, re.DOTALL)
        if not match:
            raise NativeJSONError("invalid_json_envelope")
        start += match.start("body")
        end = start + len(match.group("body"))
        text = raw[start:end]
        envelope = "whole_json_fence"
    return text, start, end, envelope


def _literal_invalid_escapes(text, control=False):
    result, offsets, controls = [], [], []
    quoted = False
    index, byte_offset = 0, 0
    while index < len(text):
        char = text[index]
        if char == '"':
            quoted = not quoted
        if quoted and char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if following not in _LEGAL_ESCAPES:
                result.append("\\")
                offsets.append(byte_offset)
            if control and ord(following) < 0x20:
                # A backslash followed by a raw control character: the backslash was just
                # doubled (illegal escape), and the control character gets its own escape.
                result.append(char)
                byte_offset += len(_utf8(char))
                result.append(_CONTROL_ESCAPES.get(following, "\\u%04x" % ord(following)))
                controls.append(byte_offset)
                byte_offset += len(_utf8(following))
                index += 2
                continue
            # Skip an escaped quote/backslash too: it cannot toggle string
            # boundaries. Malformed unicode escapes are deliberately untouched.
            result.extend((char, following))
            byte_offset += len(_utf8(char + following))
            index += 2
            continue
        if control and quoted and ord(char) < 0x20:
            # Policy v2: a raw control character inside a string becomes its JSON escape;
            # the decoded string is identical, only the representation changes.
            result.append(_CONTROL_ESCAPES.get(char, "\\u%04x" % ord(char)))
            controls.append(byte_offset)
            byte_offset += len(_utf8(char))
            index += 1
            continue
        result.append(char)
        byte_offset += len(_utf8(char))
        index += 1
    return "".join(result), offsets, controls


def prepare_native_json(raw, policy=POLICY):
    """Return a strict JSON body plus metadata-only audit, or an audited error.

    Insertion offsets refer to the original response's UTF-8 bytes. Every byte
    within the selected body is retained in order; only the listed backslashes
    may be inserted (v1), and under policy v2 the listed raw control characters
    inside strings are replaced by their escapes. Whole-response whitespace/fences
    are envelope, not content. The original response must remain in its immutable
    model receipt.
    """
    if policy not in POLICIES:
        raise NativeJSONError("unsupported_parser_policy")
    control = policy == CONTROL_POLICY
    audit = {"version": policy, "status": "rejected", "repair_count": 0,
             "insert_backslash_before_response_byte_offsets": [],
             **({"escape_control_character_at_response_byte_offsets": []} if control else {})}
    try:
        if type(raw) is not str:
            raise NativeJSONError("response_text_required")
        encoded = _utf8(raw)
        audit.update(response_sha256=hashlib.sha256(encoded).hexdigest(), response_bytes=len(encoded))
        if len(encoded) > MAX_RESPONSE_BYTES:
            raise NativeJSONError("invalid_or_oversized_json_text")
        body, start, _end, envelope = _body(raw)
        body_start = len(_utf8(raw[:start]))
        body_end = body_start + len(_utf8(body))
        audit.update(envelope=envelope, body_start_byte=body_start, body_end_byte=body_end,
                     original_body_sha256=hashlib.sha256(_utf8(body)).hexdigest())
        repaired, offsets, controls = _literal_invalid_escapes(body, control=control)
        audit.update(repair_count=len(offsets) + len(controls), insert_backslash_before_response_byte_offsets=[
            body_start + offset for offset in offsets])
        if control:
            audit["escape_control_character_at_response_byte_offsets"] = [body_start + offset for offset in controls]
        strict_native_object(repaired)
        audit.update(status="repaired" if (offsets or controls) else "strict",
                     delivered_body_sha256=hashlib.sha256(_utf8(repaired)).hexdigest())
        return repaired, audit
    except NativeJSONError as exc:
        audit["reason"] = exc.reason
        raise NativeJSONError(exc.reason, audit) from None
