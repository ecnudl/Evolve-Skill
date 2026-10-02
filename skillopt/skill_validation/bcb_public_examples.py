"""Conservative, STATIC extraction of flattened BCB public examples.

No task code is executed. A supported extraction is only syntax recognition,
not a correct/admissible oracle, runtime qualification, or verifier authority.
Returned records contain original PUBLIC text: keep them with private task
artifacts, and publish only reviewed aggregate counts and hashes.
"""
from __future__ import annotations

import ast
import io
import math
import re
import tokenize

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

VERSION = "bcb-public-inline-examples-static-v1"
LIMITS = {"prompt_bytes": 131072, "markers": 64, "candidate_bytes": 16384,
          "ast_nodes": 1024, "depth": 12, "items": 128, "string_bytes": 8192,
          "integer_bits": 256, "section_headers_per_candidate": 64}
_HEADERS = re.compile(
    r"(?m)^(?:Note that:|The function should output with:|"
    r"The function should raise the exception for:|"
    r"You should write self-contained code starting with:)")
_FOOTER = "You should write self-contained code starting with:"


class _Unsupported(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise _Unsupported(reason)


def _offset(text, position):
    lines = text.splitlines(keepends=True)
    return sum(map(len, lines[:position[0] - 1])) + position[1]


def _tokens(text):
    try:
        return list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        raise _Unsupported("incomplete_or_invalid_lexical_structure") from None


def _outside_literal_and_brackets(prefix):
    """A line header is a delimiter only after a closed lexical expression."""
    try:
        stack = []
        for token in _tokens(prefix):
            if token.type == tokenize.COMMENT and "\n" not in prefix[_offset(prefix, token.end):]:
                return False  # A later marker on this comment line is not code.
            if token.type == tokenize.ERRORTOKEN and not token.string.isspace():
                return False
            if token.type != tokenize.OP:
                continue
            if token.string in "([{":
                stack.append(token.string)
            elif token.string in ")]}":
                if not stack or stack.pop() != {")": "(", "]": "[", "}": "{"}[token.string]:
                    return False
        return not stack
    except _Unsupported:
        return False


def _literal(node, depth=0):
    _require(depth <= LIMITS["depth"], "literal_depth_exceeded")
    if isinstance(node, ast.Constant):
        value = node.value
        _require(value is None or type(value) in (bool, int, float, str), "non_json_literal")
        if type(value) is float:
            _require(math.isfinite(value), "nonfinite_number")
        if type(value) is int:
            _require(value.bit_length() <= LIMITS["integer_bits"], "integer_budget_exceeded")
        if type(value) is str:
            try:
                size = len(value.encode("utf-8"))
            except UnicodeEncodeError:
                raise _Unsupported("invalid_unicode_literal") from None
            _require(size <= LIMITS["string_bytes"], "string_budget_exceeded")
        return value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _literal(node.operand, depth + 1)
        _require(type(value) in (int, float), "non_numeric_unary_literal")
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.List):
        _require(len(node.elts) <= LIMITS["items"], "literal_item_budget_exceeded")
        return [_literal(child, depth + 1) for child in node.elts]
    if isinstance(node, ast.Dict):
        _require(len(node.keys) <= LIMITS["items"], "literal_item_budget_exceeded")
        result = {}
        for key, child in zip(node.keys, node.values):
            _require(key is not None, "dictionary_unpacking_unsupported")
            name = _literal(key, depth + 1)
            _require(type(name) is str, "non_string_json_key")
            _require(name not in result, "duplicate_json_key")
            result[name] = _literal(child, depth + 1)
        return result
    raise _Unsupported("non_json_literal_or_expression")


def _parse(text, mode):
    try:
        tree = ast.parse(text, mode=mode)
    except (SyntaxError, ValueError, RecursionError):
        raise _Unsupported("invalid_or_ambiguous_expression") from None
    _require(sum(1 for _ in ast.walk(tree)) <= LIMITS["ast_nodes"], "ast_budget_exceeded")
    return tree


def _recognize(raw, entry):
    _require(len(raw.encode("utf-8")) <= LIMITS["candidate_bytes"], "candidate_budget_exceeded")
    left = len(raw) - len(raw.lstrip())
    segment = raw[left:]
    # Find only the end of the first balanced top-level call; the entire
    # remaining span must be an expected literal, never its convenient prefix.
    depth, end = 0, None
    for token in _tokens(segment):
        _require(token.type != tokenize.COMMENT, "comments_require_admissibility_review")
        if token.type == tokenize.OP:
            if token.string in "([{":
                depth += 1
            elif token.string in ")]}":
                depth -= 1
                _require(depth >= 0, "unbalanced_expression")
                if depth == 0:
                    end = _offset(segment, token.end)
                    break
    _require(end is not None, "direct_call_not_found")
    tree = _parse(segment[:end], "exec")
    _require(len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr), "assignment_or_setup_unsupported")
    call = tree.body[0].value
    _require(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
             and call.func.id == entry, "not_direct_entry_call")
    _require(len(call.args) + len(call.keywords) <= LIMITS["items"], "argument_budget_exceeded")
    args, kwargs = [_literal(value) for value in call.args], {}
    for keyword in call.keywords:
        _require(keyword.arg is not None, "argument_unpacking_unsupported")
        _require(keyword.arg not in kwargs, "duplicate_keyword")
        kwargs[keyword.arg] = _literal(keyword.value)
    tail = segment[end:]
    expected_left = len(tail) - len(tail.lstrip())
    expected = tail.strip()
    _require(bool(expected), "expected_literal_missing")
    _require(not any(token.type == tokenize.COMMENT for token in _tokens(expected)),
             "expected_comment_requires_review")
    value = _literal(_parse(expected, "eval").body)
    return {"args": args, "kwargs": kwargs, "expected": value,
            "call_relative_span": [left, left + end],
            "expected_relative_span": [left + end + expected_left,
                                       left + end + expected_left + len(expected)]}


def extract_public_examples(public):
    """Return deterministic, replayable recognition; accept no host/H fields.

    Spans index Unicode characters in the exact retained public prompt. Fixed
    line-start BCB section titles may delimit examples only outside strings and
    brackets. Free-form trailing prose/comments are NOT discarded. Marker
    overflow rejects the entire extraction rather than dropping candidates.
    """
    if type(public) is not dict or set(public) != {"prompt", "entry_point"}:
        raise ValueError("Only explicit public prompt and entry_point are accepted")
    prompt, entry = public["prompt"], public["entry_point"]
    if (type(prompt) is not str or type(entry) is not str
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", entry) is None):
        raise ValueError("Public prompt and simple entry identifier required")
    if len(prompt.encode("utf-8")) > LIMITS["prompt_bytes"]:
        raise ValueError("Public prompt budget exceeded")
    markers = list(re.finditer(r">>>", prompt))
    result = {"version": VERSION, "public": dict(public), "public_hash": digest(public),
              "limits": dict(LIMITS), "span_unit": "unicode_character",
              "marker_count": len(markers), "status": "complete", "reason": "static_recognition_only",
              "candidates": [], "supported_count": 0, "unsupported_count": 0,
              "executed": False, "admissibility": "not_reviewed", "authorization": False}
    if len(markers) > LIMITS["markers"]:
        return seal({**result, "status": "unsupported", "reason": "marker_budget_exceeded",
                     "unsupported_count": len(markers)})
    footer = re.search(r"(?m)^" + re.escape(_FOOTER), prompt)
    lexical_anchor = None
    for index, marker in enumerate(markers):
        context_reason = None
        if lexical_anchor is not None:
            prefix = prompt[lexical_anchor:marker.start()]
            if len(prefix.encode("utf-8")) > LIMITS["candidate_bytes"]:
                context_reason = "lexical_context_budget_exceeded"
            elif not _outside_literal_and_brackets(prefix):
                context_reason = "marker_inside_or_after_unresolved_lexical_context"
        if context_reason is None:
            lexical_anchor = marker.end()
        stop = markers[index + 1].start() if index + 1 < len(markers) else len(prompt)
        boundary = {"kind": "next_marker" if index + 1 < len(markers) else "prompt_end",
                    "span": [stop, stop], "raw": ""}
        for attempt, header in enumerate(_HEADERS.finditer(prompt, marker.end(), stop), start=1):
            if context_reason is not None:
                break
            prefix = prompt[marker.end():header.start()]
            if len(prefix.encode("utf-8")) > LIMITS["candidate_bytes"]:
                context_reason = "candidate_budget_exceeded"
                break
            if attempt > LIMITS["section_headers_per_candidate"]:
                context_reason = "section_boundary_budget_exceeded"
                break
            if _outside_literal_and_brackets(prefix):
                stop = header.start()
                boundary = {"kind": "explicit_bcb_section", "span": [header.start(), header.end()],
                            "raw": header.group()}
                break
        raw = prompt[marker.end():stop]
        record = {"index": index, "marker_span": [marker.start(), marker.end()],
                  "source_span": [marker.end(), stop], "source_text": raw,
                  "lexical_anchor": lexical_anchor,
                  "boundary": boundary, "status": "unsupported", "reason": "not_recognized"}
        try:
            _require(context_reason is None, context_reason)
            _require(footer is None or marker.start() < footer.start(), "marker_in_code_template")
            parsed = _recognize(raw, entry)
            record.update(status="supported", reason="direct_json_literal_pair", **parsed)
        except _Unsupported as exc:
            record["reason"] = str(exc)
        result["candidates"].append(record)
        result[record["status"] + "_count"] += 1
    return seal(result)
