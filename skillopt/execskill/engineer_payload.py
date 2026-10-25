"""The v2.3 engineer/analyst excerpts (2026-10-25 request E2).

Only detached, shown public fields are shortened; stored trajectories and replay inputs remain full. Anchors use
only answers the payload already discloses. ALFWorld is left intact, including its step lists.
"""
from __future__ import annotations

import copy
import json
import re

from .trajectories import _carried

TRIM_CHARS = 6_000
HEAD_CHARS = 1_500
WINDOW_CHARS = 600
MAX_WINDOWS = 6
PUBLIC_FIELDS = frozenset({"question", "context", "choices", "instruction", "workbook_preview"})
NUMBER = re.compile(r"(?<!\w)[+-]?\d[\d,.]*(?:%|\b)")
WORD = re.compile(r"[^\W\d_]{5,}", re.UNICODE)
COMMON = frozenset({"which", "where", "there", "their", "these", "those", "about", "would", "could", "should",
                    "between", "following", "according", "please", "calculate", "question", "answer"})


def _texts(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [text for child in value.values() for text in _texts(child)]
    if isinstance(value, (list, tuple)):
        return [text for child in value for text in _texts(child)]
    return [] if value is None or type(value) is bool else [str(value)]


def _merge(windows):
    merged = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _render(text, windows):
    parts, position = [], 0
    for start, end in _merge(windows):
        if start > position:
            parts.append("[... %d characters omitted ...]" % (start - position))
        parts.append(text[start:end])
        position = end
    if position < len(text):
        parts.append("[... %d characters omitted ...]" % (len(text) - position))
    return "".join(parts)


def excerpt(text, *, question="", references=(), answers=()):
    """At most 6,000 characters: the opening 1,500 and up to six answer/question windows, in document order.

    Matches are case-insensitive literal substrings, first occurrence first; reference, final answer, question
    numbers, then distinctive words (longest first, lexical tie break). Lower-priority windows use only the space
    remaining, symmetrically shortened when necessary; omission markers count toward the cap.
    """
    if len(text) <= TRIM_CHARS:
        return text
    words = sorted({w for w in WORD.findall(question) if w.casefold() not in COMMON}, key=lambda w: (-len(w), w))
    anchors = list(references) + list(answers) + NUMBER.findall(question) + words
    windows, used, seen = [(0, HEAD_CHARS)], 0, set()
    for anchor in anchors:
        if not isinstance(anchor, str) or not anchor.strip() or anchor.casefold() in seen:
            continue
        seen.add(anchor.casefold())
        for match in re.finditer(re.escape(anchor), text, re.IGNORECASE):
            start, end = match.span()
            if any(left <= start and end <= right for left, right in _merge(windows)):
                continue
            full = (max(0, start - WINDOW_CHARS), min(len(text), end + WINDOW_CHARS))
            if len(_render(text, windows + [full])) <= TRIM_CHARS:
                chosen = full
            else:
                # An answer itself may be longer than the remaining space: center on its first character.
                low, high, chosen = 0, WINDOW_CHARS, None
                while low <= high:
                    radius = (low + high) // 2
                    trial = (max(0, start - radius), min(len(text), start + max(1, radius)))
                    if len(_render(text, windows + [trial])) <= TRIM_CHARS:
                        chosen, low = trial, radius + 1
                    else:
                        high = radius - 1
                if chosen is None:
                    return _render(text, windows)
            windows.append(chosen)
            used += 1
            if used == MAX_WINDOWS:
                return _render(text, windows)
    return _render(text, windows)


def trim(user):
    """A detached payload plus per-field and total original/trimmed public character counts."""
    out, rows = copy.deepcopy(user), []
    counts = {"original_chars": 0, "trimmed_chars": 0}

    def cut(value, path, question, references, answers):
        if isinstance(value, str):
            shortened = excerpt(value, question=question, references=references, answers=answers)
            counts["original_chars"] += len(value)
            counts["trimmed_chars"] += len(shortened)
            if shortened != value:
                rows.append({"path": path, "original_chars": len(value), "trimmed_chars": len(shortened)})
            return shortened
        if isinstance(value, dict):
            return {key: cut(child, path + "/" + str(key), question, references, answers)
                    for key, child in value.items()}
        if isinstance(value, list):
            return [cut(child, path + "/" + str(i), question, references, answers) for i, child in enumerate(value)]
        return value

    if out.get("bench") != "alfworld":
        for index, entry in enumerate(out.get("trajectories", [])):
            if entry.get("bench") == "alfworld":
                continue
            refs = _texts(entry.get("reference")) if entry.get("kind") == "failures" else []
            replies = entry.get("replies") or []
            final = next((reply for reply in reversed(replies) if isinstance(reply, str)), "")
            answers = _carried(entry.get("bench", out.get("bench")), final) or ([final] if final else [])
            for n, call in enumerate(entry.get("calls", [])):
                view = json.loads(call["user"])
                question = "\n".join(_texts(view.get("question", view.get("instruction", ""))))
                for key in sorted(PUBLIC_FIELDS & set(view)):
                    view[key] = cut(view[key], "trajectories/%d/calls/%d/%s" % (index, n, key), question, refs, answers)
                call["user"] = json.dumps(view, ensure_ascii=False, sort_keys=True)
        for n, procedure in enumerate((out.get("training") or {}).get("procedures", [])):
            for m, example in enumerate(procedure.get("examples", [])):
                refs = _texts(example.get("reference"))
                answers = _texts(example.get("current_reply")) + _texts(example.get("candidate_reply"))
                for key in sorted(PUBLIC_FIELDS & set(example)):
                    example[key] = cut(example[key], "training/procedures/%d/examples/%d/%s" % (n, m, key),
                                       example.get("question", ""), refs, answers)
    out["payload_trimming"] = {**counts, "fields": rows, "limit_chars": TRIM_CHARS,
                               "scope": "public text before whole-example fitting"}
    return out
