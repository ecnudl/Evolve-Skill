"""Typed procedure notes: fields, fixed headers, the lexicon screen and the note caps (registration §2.2, §2.3, §2.4
item 1, §5.4 C9; plan §1 notes.py, §3, T-NOTES-1..3).

A procedure never writes free text to the solver: its ``before_call`` / ``bindings`` / ``sheet_feedback`` /
``alf_before_step`` hooks return typed fields (``FIELD_TYPES``) and the shell renders them under the registered fixed
headers (``protocol.NOTE_HEADERS``), after the procedure's own constant header. ``screen`` drops a field that is
malformed, over its caps, or that contains a term of the registered lexicon (``protocol.LEXICON[bench]``, matched by
the registered rule ``protocol.LEXICON_MATCH``, inflections included; SpreadsheetBench exempts "format"; on LiveMath
the meta-option terms of check C4, ``policy.meta_option_hits``, belong to it). Given the item's public text, a table
cell or a binding's quote that occurs in it verbatim is the item's text and is not screened (registrar decision
2026-10-22 on ticket A3-1, ``protocol.LEXICON_VERBATIM``); ``screen`` returns the kept fields as ``Screened``, which
remembers that text, so ``render`` screens them again against the same text. Every dropped field, and every binding
``check_bindings`` drops, is one procedure fault, counted toward the 2% cap (§2.2, §4.4 P1). ``assemble`` joins the
rendered notes of
one cell (at most 4,000 characters) or of one ALFWorld step (at most 1,500) in package order and skips a whole note
that would exceed the cap -- deterministic, the same in every arm (§2.3). ``lexicon_sha256`` freezes what this module
applies (terms, rule, headers, field types, caps) before S2 (plan §11).
"""
from __future__ import annotations

import re

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from .compute import FUNCTIONS, NAME, ComputeError, number
from .policy import META_TERMS, meta_option_hits
from .protocol import (
    BENCHES,
    LEXICON,
    LEXICON_MATCH,
    LEXICON_SUFFIXES,
    LEXICON_VERBATIM,
    MAX_HEADER_CHARS,
    MAX_NOTE_CHARS,
    NOTE_HEADERS,
    kind,
)

FIELD_ORDER = ("facts", "table", "candidates", "warnings", "bindings")
FIELD_TYPES = {  # plan §1 notes.py
    "facts": {"kind": "strings", "max_chars": 200},
    "table": {"kind": "rows", "max_chars": 40, "max_rows": 20, "max_columns": 12},
    "candidates": {"kind": "strings", "max_chars": 120},
    "warnings": {"kind": "strings", "max_chars": 200},
    "bindings": {"kind": "bindings", "keys": ["name", "quote", "value"], "max_chars": 200},
}
SEPARATOR = "\n\n"


def _pattern(term):
    """``protocol.LEXICON_MATCH``: case-insensitive; a term starting and ending with a letter matches on word
    boundaries (its spaces match any whitespace), also with one of ``LEXICON_SUFFIXES`` (its last letter optionally
    doubled before "ed" and "ing": "formatted") and, when it ends in "s", also without that "s" ("decimal place", with
    no suffix: "units" never matches "united"); any other term matches as a substring, so its inflections match too."""
    if not (term[0].isalpha() and term[-1].isalpha()):
        return re.compile(re.escape(term), re.I)
    words = r"\s+".join(re.escape(w) for w in term.split())
    last = re.escape(term[-1])
    suffixes = "|".join([re.escape(s) for s in LEXICON_SUFFIXES] + [last + "ed", last + "ing"])
    forms = [words + "(?:" + suffixes + ")?"]
    if term.endswith("s"):
        forms.append(r"\s+".join(re.escape(w) for w in term[:-1].split()))
    return re.compile(r"\b(?:" + "|".join(forms) + r")\b", re.I)


PATTERNS = {bench: tuple((term, _pattern(term)) for term in LEXICON[bench]) for bench in BENCHES}
PATTERNS["zebralogic"] = tuple((term, _pattern(term)) for term in LEXICON["searchqa"])


def lexicon_record():
    """What the screen applies, as one record (hashed into the manifest before S2)."""
    return {"version": kind("lexicon"), "terms": {bench: list(LEXICON[bench]) for bench in BENCHES},
            "match": LEXICON_MATCH, "suffixes": list(LEXICON_SUFFIXES), "verbatim": LEXICON_VERBATIM,
            "meta_option": {"bench": "livemath", "terms": list(META_TERMS)},
            "field_types": FIELD_TYPES, "headers": NOTE_HEADERS, "caps": MAX_NOTE_CHARS,
            "max_header_chars": MAX_HEADER_CHARS}


def lexicon_sha256():
    return digest(lexicon_record())


def lexicon_hits(text, *, bench):
    """The lexicon terms of ``bench`` in ``text`` (LiveMath: also the meta-option terms)."""
    require(bench in PATTERNS, "Unknown bench")
    hits = [term for term, rx in PATTERNS[bench] if rx.search(text)]
    return hits + (meta_option_hits(text) if bench == "livemath" else [])


def header_hits(header, *, benches):
    """[(bench, term)]: the lexicon terms a procedure's constant header shows on the benches it may fire on."""
    return [(bench, term) for bench in benches for term in lexicon_hits(header, bench=bench)]


def _strings(value, max_chars):
    """(well_typed, within_caps) of a list of strings."""
    typed = type(value) is list and all(type(s) is str for s in value)
    return typed, typed and all(len(s) <= max_chars for s in value)


def _shape(name, value):
    """(well_typed, within_caps) of one field."""
    spec = FIELD_TYPES[name]
    if spec["kind"] == "strings":
        return _strings(value, spec["max_chars"])
    if spec["kind"] == "rows":
        typed = type(value) is list and all(_strings(row, spec["max_chars"])[0] for row in value)
        capped = typed and len(value) <= spec["max_rows"] and all(
            len(row) <= spec["max_columns"] and _strings(row, spec["max_chars"])[1] for row in value)
        return typed, capped
    typed = type(value) is list and all(
        type(b) is dict and sorted(b) == spec["keys"] and all(type(b[k]) is str for k in spec["keys"]) for b in value)
    return typed, typed and all(len(b[k]) <= spec["max_chars"] for b in value for k in spec["keys"])


def _screened(name, value, public_text):
    """The texts of the well-typed field ``name`` that the lexicon screen reads: all of them, except (given the item's
    ``public_text``) a table cell or a binding's quote that occurs in it verbatim (``protocol.LEXICON_VERBATIM``)."""
    def item_text(text):
        return public_text is not None and text in public_text

    if name == "table":
        return [cell for row in value for cell in row if not item_text(cell)]
    if name == "bindings":
        return [b[k] for b in value for k in FIELD_TYPES[name]["keys"]
                if not (k == LEXICON_VERBATIM[name] and item_text(b[k]))]
    return list(value)


def _copy(name, value):
    if name == "table":
        return [list(row) for row in value]
    if name == "bindings":
        return [dict(b) for b in value]
    return list(value)


def _field_order(name):
    return (name not in FIELD_TYPES, FIELD_ORDER.index(name) if name in FIELD_TYPES else 0, str(name))


class Screened(dict):
    """The fields ``screen`` kept, with the item's public text they were screened against (None: every text was
    screened); ``render`` screens them again against the same text."""

    def __init__(self, fields, public_text):
        super().__init__(fields)
        self.public_text = public_text


def screen(fields, *, bench, public_text=None):
    """``(kept, dropped)``: the well-formed, capped, lexicon-clean fields as ``Screened`` (an empty field is absent,
    not dropped), and one ``{"field", "reason", "detail"}`` per dropped field, reason ``unknown_field``, ``type``,
    ``cap``, ``lexicon`` or ``meta_option``. Every dropped field is one procedure fault. ``public_text``: the item's
    public text, against which table cells and binding quotes are verified verbatim and then not screened (ticket
    A3-1 (b)); None (a sham's content, or a caller without the item) screens every text."""
    require(bench in PATTERNS, "Unknown bench")
    require(public_text is None or type(public_text) is str, "The public text is text")
    if not isinstance(fields, dict):
        return Screened({}, public_text), [{"field": None, "reason": "type", "detail": type(fields).__name__}]
    kept, dropped = Screened({}, public_text), []
    for name in sorted(fields, key=_field_order):
        value = fields[name]
        if name not in FIELD_TYPES:
            dropped.append({"field": str(name), "reason": "unknown_field", "detail": ""})
            continue
        typed, capped = _shape(name, value)
        if not typed or not capped:
            dropped.append({"field": name, "reason": "type" if not typed else "cap", "detail": ""})
            continue
        hits = [term for text in _screened(name, value, public_text) for term in lexicon_hits(text, bench=bench)]
        if hits:
            meta = any(term in META_TERMS for term in hits)
            dropped.append({"field": name, "reason": "meta_option" if meta else "lexicon", "detail": hits[0]})
        elif value:
            kept[name] = _copy(name, value)
    return kept, dropped


def check_bindings(bindings, public_text):
    """``(kept, dropped)`` of the screened ``bindings`` field: a binding is kept only if its name is a usable,
    unrepeated identifier, its value is a number (``compute.number``) and both its value and its quote appear
    verbatim in the item's public text, the value inside the quote (§2.2, §2.4 item 1: checked by fixed code). Every
    dropped binding is one procedure fault."""
    require(type(public_text) is str, "The public text is text")
    kept, dropped, seen = [], [], set()
    for binding in bindings:
        name, value, quote = binding["name"], binding["value"], binding["quote"]
        reason = None
        if NAME.fullmatch(name) is None or name in FUNCTIONS:
            reason = "name"
        elif name in seen:
            reason = "duplicate_name"
        else:
            try:
                number(value)
            except ComputeError:
                reason = "value"
        if reason is None and not (value in quote and quote in public_text):
            reason = "not_verbatim"
        if reason is None:
            seen.add(name)
            kept.append(dict(binding))
        else:
            dropped.append({"field": "bindings", "reason": reason, "detail": name})
    return kept, dropped


def _lines(name, value):
    if name == "table":
        return ["| " + " | ".join(row) + " |" for row in value]
    if name == "bindings":
        return ['- %s = %s (quoted: "%s")' % (b["name"], b["value"], b["quote"]) for b in value]
    return ["- " + item for item in value]


def render(fields, *, bench, header):
    """The note of one procedure: its constant header, then each field under its fixed header, in ``FIELD_ORDER``.
    ``fields`` must pass ``screen`` unchanged (the shell screens first), against the public text it was screened with
    when it is ``Screened`` (else every text); no field renders as ""."""
    require(type(header) is str and len(header) <= MAX_HEADER_CHARS and not lexicon_hits(header, bench=bench),
            "A procedure header is at most 200 lexicon-clean characters")
    reference = fields.public_text if isinstance(fields, Screened) else None
    kept, dropped = screen(fields, bench=bench, public_text=reference)
    require(not dropped and kept == {k: v for k, v in fields.items() if v}, "Only screened fields are rendered")
    if not kept:
        return ""
    blocks = [header.strip()] if header.strip() else []
    blocks += ["\n".join([NOTE_HEADERS[name]] + _lines(name, kept[name])) for name in FIELD_ORDER if name in kept]
    return "\n".join(blocks)


def assemble(notes, *, bench):
    """``(text, skipped)``: the rendered notes of one cell or ALFWorld step, joined in package order. ``notes``:
    ``[(procedure_id, text, max_note_chars)]``. A note longer than its procedure's declared cap is skipped
    (``over_declared_cap``, a procedure fault, §5.4 C9); a note that would bring the total over
    ``protocol.MAX_NOTE_CHARS[bench]`` is skipped whole (``over_total_cap``, the same in every arm, §2.3)."""
    require(bench in PATTERNS, "Unknown bench")
    cap = 4_000 if bench == "zebralogic" else MAX_NOTE_CHARS[bench]
    parts, skipped, total = [], [], 0
    for procedure, text, declared in notes:
        if not text:
            continue
        if len(text) > declared:
            skipped.append({"procedure": procedure, "reason": "over_declared_cap", "chars": len(text)})
            continue
        added = len(text) + (len(SEPARATOR) if parts else 0)
        if total + added > cap:
            skipped.append({"procedure": procedure, "reason": "over_total_cap", "chars": len(text)})
            continue
        parts.append(text)
        total += added
    return SEPARATOR.join(parts), skipped
