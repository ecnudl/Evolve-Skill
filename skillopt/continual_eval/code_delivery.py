"""Conservative, non-executing extraction of an unchanged Python deliverable.

Line-delimited backtick/tilde fences are parsed as paired blocks, not regex
matches starting at arbitrary closing fences. This is a bounded subset, not a
complete Markdown renderer. Body indentation/line endings are never rewritten.
Syntax, correctness, and whether the code creates its required output are NOT
inferred here; those are independent execution checks.
"""
from __future__ import annotations

import hashlib
import re

VERSION = "explicit-python-fences-v1"
MAX_BYTES = 262144
_OPEN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>[^\r\n]*)$")
_CLOSE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})[ \t]*$")
_FENCE_LIKE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})")


def extract_python(response):
    """Return one literal source span, or an explicit unknown/ambiguity.

    One explicit python/py block takes precedence over non-Python explanatory
    blocks. Two explicit Python blocks are ambiguous even when equal. Without
    explicit Python, only a sole unlabelled block or an entirely unfenced reply
    is a candidate. Bare reply acceptance does not assert it is valid Python.
    No compilation, best-scoring selection, text repair, or inference occurs.
    """
    result = {"version": VERSION, "status": "unknown", "reason": None, "code": None,
              "source_sha256": None, "code_sha256": None, "span": None, "candidate_kind": None,
              "fenced_blocks": 0, "explicit_python_blocks": 0, "syntax_validated": False}
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
    blocks, active, offset, unsupported_fence = [], None, 0, False
    for line in response.splitlines(keepends=True):
        visible = line.rstrip("\r\n")
        if active is None:
            match = _OPEN.fullmatch(visible)
            if match and (match["fence"][0] != "`" or "`" not in match["info"]):
                info = match["info"].strip()
                language = info.split()[0].casefold() if info else ""
                active = {"character": match["fence"][0], "size": len(match["fence"]),
                          "language": language, "start": offset + len(line)}
            elif _FENCE_LIKE.match(visible):
                unsupported_fence = True
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
    if unsupported_fence:
        return {**result, "reason": "unsupported_fence_syntax"}
    if len(explicit) > 1:
        return {**result, "reason": "multiple_python_blocks"}
    if explicit:
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
    return {**result, "status": "available", "reason": "single_literal_deliverable",
            "code": code, "span": [block["start"], block["end"]], "candidate_kind": kind,
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest()}
