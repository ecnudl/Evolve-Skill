"""Post-hoc artifact-format sensitivity, deliberately outside the frozen pilot.

This module extracts one unambiguous Python artifact from a frozen response. It
does not alter Python syntax, escapes inside extracted code, quotes, or behavior;
does not execute anything; and does not access tasks or expected results. Scores
computed after using it are post-hoc sensitivity analyses, not replacement scores
for a protocol requiring a strict JSON response.

``ok`` means extraction succeeded, NOT that the code is valid or correct.
``syntax_ok`` independently records ast.parse. A malformed Python artifact in an
otherwise valid JSON wrapper remains extracted, with syntax_ok=False.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from typing import Any

VERSION = "artifact-format-sensitivity-v1"
MAX_RESPONSE_CHARS = 1_000_000
_FENCE = re.compile(r"^[ \t]*(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)[ \t]*(?:\r?\n)?$")


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey("duplicate JSON object key")
        result[key] = value
    return result


def _json_artifact(text: str) -> tuple[str | None, str | None, str | None]:
    """Decode strict JSON, or ONLY its unescaped-control-character relaxation."""
    relaxed = False
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
    except _DuplicateKey:
        return None, None, "ambiguous_duplicate_json_keys"
    except json.JSONDecodeError as exc:
        if not exc.msg.startswith("Invalid control character"):
            return None, None, "malformed_json"
        try:
            value = json.loads(text, strict=False, object_pairs_hook=_unique_object)
        except _DuplicateKey:
            return None, None, "ambiguous_duplicate_json_keys"
        except json.JSONDecodeError:
            return None, None, "malformed_json"
        relaxed = True
    if not isinstance(value, dict) or set(value) != {"code"} or not isinstance(value["code"], str):
        return None, None, "json_artifact_schema"
    if not value["code"].strip():
        return None, None, "empty_artifact"
    return value["code"], "json_unescaped_controls" if relaxed else "strict_json", None


def _extracted(result: dict[str, Any], code: str, mode: str) -> dict[str, Any]:
    result.update(ok=True, code=code, mode=mode, code_sha256=hashlib.sha256(code.encode("utf-8")).hexdigest())
    try:
        ast.parse(code)
    except (SyntaxError, ValueError) as exc:
        result["error_category"] = "python_syntax_error"
        result["syntax_error"] = {
            "message": str(exc).split("\n", 1)[0],
            "line": getattr(exc, "lineno", None),
            "offset": getattr(exc, "offset", None),
        }
    else:
        result["syntax_ok"] = True
    return result


def extract_artifact(response: str) -> dict[str, Any]:
    """Return an unchanged Python artifact, with explicit extraction provenance.

    Supported, in priority order: an exact JSON ``{"code": str}`` object;
    the same object using JSON's ``strict=False`` control-character relaxation;
    one Markdown Python/py fenced block (optional surrounding prose recorded);
    one JSON/untyped JSON fenced block; or raw syntactically valid Python.

    Multiple blocks, mismatched fences, duplicate JSON keys and invalid JSON
    schemas are refused. No substring JSON guessing, quote repair, trailing-brace
    deletion, unicode-escape re-decoding, AST rewriting or model repair occurs.
    """
    result: dict[str, Any] = {
        "version": VERSION,
        "ok": False,
        "code": None,
        "mode": None,
        "syntax_ok": False,
        "error_category": None,
        "raw_sha256": None,
        "code_sha256": None,
    }
    if not isinstance(response, str):
        result["error_category"] = "response_not_string"
        return result
    result["raw_sha256"] = hashlib.sha256(response.encode("utf-8")).hexdigest()
    if len(response) > MAX_RESPONSE_CHARS:
        result["error_category"] = "response_size_limit"
        return result
    stripped = response.strip()
    if not stripped:
        result["error_category"] = "empty_response"
        return result
    # JSON-looking malformed/schema-invalid values must not be silently treated
    # as valid Python dictionary/list/expression modules.
    if stripped.startswith(("{", "[", '"')) and not stripped.startswith('"""'):
        code, mode, error = _json_artifact(stripped)
        if error:
            result["error_category"] = error
            return result
        return _extracted(result, code, mode)

    fences = []
    offset = 0
    for line in response.splitlines(keepends=True):
        match = _FENCE.fullmatch(line)
        if match:
            fences.append(
                {
                    "start": offset,
                    "end": offset + len(line),
                    "marker": match.group("marker"),
                    "info": match.group("info").strip(),
                }
            )
        offset += len(line)
    if fences:
        if len(fences) != 2:
            result["error_category"] = "multiple_fenced_blocks" if len(fences) > 2 else "unclosed_fence"
            return result
        opening, closing = fences
        if (
            closing["info"]
            or closing["marker"][0] != opening["marker"][0]
            or len(closing["marker"]) < len(opening["marker"])
        ):
            result["error_category"] = "mismatched_fences"
            return result
        code = response[opening["end"] : closing["start"]]
        prose = bool(response[: opening["start"]].strip() or response[closing["end"] :].strip())
        suffix = "_with_prose" if prose else ""
        language = opening["info"].lower()
        if language in ("python", "py"):
            if not code.strip():
                result["error_category"] = "empty_artifact"
                return result
            return _extracted(result, code, "python_fence" + suffix)
        if language in ("json", ""):
            decoded, mode, error = _json_artifact(code)
            if error:
                result["error_category"] = error
                return result
            mode = "fenced_json_unescaped_controls" if mode == "json_unescaped_controls" else "fenced_json"
            return _extracted(result, decoded, mode + suffix)
        result["error_category"] = "unsupported_fence_language"
        return result

    try:
        ast.parse(response)
    except (SyntaxError, ValueError):
        result["error_category"] = "unrecognized_artifact"
        return result
    return _extracted(result, response, "raw_python")
