"""Literal SpreadsheetBench extraction v2 (owner 2026-10-24 21:5x; REQUEST-v23 E5).

Only main-v2-3 selects this parser. Per the 2026-10-25 review fix, every successful v1 extraction is preserved
before attempting recovery. Prose-prefixed explicit openers and redundant trailing fence-only lines have separate
recorded recovery kinds. Multiple explicit blocks still refuse unless the sealed configuration selects ``last``.
Source spans are unchanged; no syntax validation, execution, repair or answer-dependent selection occurs. The
continual_eval v1 parser and all its callers outside this configuration retain their frozen behavior.
"""
from __future__ import annotations

import hashlib
import re

from skillopt.continual_eval.code_delivery import MAX_BYTES, _OPEN, _CLOSE, _FENCE_LIKE, extract_python as _extract_v1
from skillopt.continual_eval.core import require

VERSION = "explicit-python-fences-v2"
_INLINE_OPEN = re.compile(r"(?P<prose>.+?)(?P<fence>`{3,})(?:python|py)[ \t]*$", re.I)


def extract_python(response, *, multiple="refuse"):
    """One unchanged source span and the applied ``kinds``; ``multiple`` is ``refuse`` or ``last``."""
    require(multiple in ("refuse", "last"), "Multiple Python blocks: refuse or last")
    original = _extract_v1(response)
    if original["status"] == "available":
        return {**original, "version": VERSION, "multiple_python_blocks": multiple, "kinds": []}
    result = {"version": VERSION, "status": "unknown", "reason": None, "code": None,
              "source_sha256": None, "code_sha256": None, "span": None, "candidate_kind": None,
              "fenced_blocks": 0, "explicit_python_blocks": 0, "syntax_validated": False,
              "multiple_python_blocks": multiple, "kinds": []}
    if type(response) is not str:
        return {**result, "reason": "response_not_text"}
    try:
        raw = response.encode("utf-8")
    except UnicodeEncodeError:
        return {**result, "reason": "invalid_unicode"}
    result["source_sha256"] = hashlib.sha256(raw).hexdigest()
    if len(raw) > MAX_BYTES:
        return {**result, "reason": "response_size_limit"}
    if not response.strip():
        return {**result, "reason": "empty_response"}
    lines = response.splitlines(keepends=True)
    suffix = [True] * (len(lines) + 1)
    for i in range(len(lines) - 1, -1, -1):
        visible = lines[i].rstrip("\r\n")
        suffix[i] = suffix[i + 1] and (not visible.strip() or _CLOSE.fullmatch(visible) is not None)
    blocks, active, offset, unsupported = [], None, 0, False
    kinds = result["kinds"]
    for i, line in enumerate(lines):
        visible = line.rstrip("\r\n")
        if active is None:
            match = _OPEN.fullmatch(visible)
            inline = _INLINE_OPEN.fullmatch(visible) if match is None else None
            if blocks and _CLOSE.fullmatch(visible) and suffix[i]:
                if "trailing_fence_only_lines" not in kinds:
                    kinds.append("trailing_fence_only_lines")
            elif inline is not None and inline["prose"].strip():
                active = {"character": "`", "size": len(inline["fence"]), "language": "python",
                          "start": offset + len(line)}
                if "prose_prefixed_opening_fence" not in kinds:
                    kinds.append("prose_prefixed_opening_fence")
            elif match and (match["fence"][0] != "`" or "`" not in match["info"]):
                info = match["info"].strip()
                active = {"character": match["fence"][0], "size": len(match["fence"]),
                          "language": info.split()[0].casefold() if info else "", "start": offset + len(line)}
            elif _FENCE_LIKE.match(visible):
                unsupported = True
        else:
            match = _CLOSE.fullmatch(visible)
            if match and match["fence"][0] == active["character"] and len(match["fence"]) >= active["size"]:
                blocks.append({**active, "end": offset})
                active = None
        offset += len(line)
    explicit = [b for b in blocks if b["language"] in {"python", "py"}]
    result.update(fenced_blocks=len(blocks), explicit_python_blocks=len(explicit))
    if active is not None:
        return {**result, "reason": "unclosed_fence"}
    if unsupported:
        return {**result, "reason": "unsupported_fence_syntax"}
    if len(explicit) > 1 and multiple == "refuse":
        return {**result, "reason": "multiple_python_blocks"}
    if len(explicit) > 1:
        block, kind = explicit[-1], "last_explicit_python"
        kinds.append("last_explicit_python_block")
    elif explicit:
        block, kind = explicit[0], "explicit_python"
    elif len(blocks) == 1 and blocks[0]["language"] == "":
        block, kind = blocks[0], "sole_unlabelled"
    elif not blocks:
        block, kind = {"start": 0, "end": len(response)}, "whole_unfenced_response"
    else:
        return {**result, "reason": "no_unambiguous_python_deliverable"}
    code = response[block["start"]:block["end"]]
    if not code.strip():
        return {**result, "reason": "empty_code_block"}
    return {**result, "status": "available", "reason": "single_literal_deliverable", "code": code,
            "span": [block["start"], block["end"]], "candidate_kind": kind,
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest()}
