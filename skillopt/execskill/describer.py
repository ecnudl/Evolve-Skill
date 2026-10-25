"""The text twin T_F of a frozen procedure (registration §5.7, §8.1 per-hook T_F table after Codex F20, FE-F10, ME-F8;
implementation plan §1 describer.py, §2.1 package ``describer``).

At freeze, one GLM-5.3 call per procedure (``roles.plain``, the pinned ``DESCRIBER_SYSTEM``) rewrites the procedure as
plain advice for the solver; the shell shows that text instead of running the code (``solver._Shell``, ``text=``),
only where the predicate fires, in the same slot. The text is screened as a note is: a sentence carrying a lexicon term
of a bench the procedure may fire on (``notes.lexicon_hits``; LiveMath: the meta-option terms too) is left out. Its
length targets the procedure's median note length on the run slice, within +-``TEXT_LENGTH_BAND``: a longer text is cut
at the last sentence (else word) end inside the band, a shorter one is kept and flagged ``short`` (there is one call,
no second try); the shell's caps (the declared note cap and the smallest per-request cap of its benches) bound it in
every case. The record ``fivebench-execskill-v1-description`` freezes the text and prompt hashes that
``package.with_describer`` stores (``entries``); ``texts`` is the solver's ``text=`` mapping. A procedure without a
usable text (no reply, or nothing left after the screen) has none: the T_F arm's handling of it is the caller's.
"""
from __future__ import annotations

import json
import re
from statistics import median_low

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from .notes import lexicon_hits
from .package import Procedure, procedure_benches
from .profiles import BENCHES, DEFAULT_TARGET, MAX_NOTE_CHARS, TEXT_LENGTH_BAND, record, verified

ROLE = "describer"
DESCRIBER_SYSTEM = """\
You rewrite one helper program as a short plain-text note for a model that solves benchmark tasks. The note will be \
shown to the model instead of the program's output, on the tasks where the program applies. Describe, as general \
advice, what the program looks for in a task and how that information helps; state no task-specific facts, numbers \
or names. Write about the requested number of characters ("target_chars"; when it is null, at most 600). Never \
instruct the form of the model's reply: avoid words such as answer, output, return, respond, json, format, round, \
units, decimal places, only the, just the, bare and single letter. Reply with the note text only."""
DESCRIBER_PROMPT_SHA256 = digest(DESCRIBER_SYSTEM)
SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n|$)")


def _scope(procedure, excluded):
    return [b for b in procedure_benches(procedure) if b not in set(procedure.excluded_benches) | set(excluded)]


def screened(text, benches):
    """``(text, dropped sentences)``: ``text`` without the sentences carrying a lexicon term of ``benches``."""
    kept, dropped = [], []
    for sentence in SENTENCE.findall(text):
        hit = any(lexicon_hits(sentence, bench=b) for b in benches)
        (dropped if hit else kept).append(sentence)
    return " ".join(" ".join(s.split()) for s in kept if s.strip()), len(dropped)


def clipped(text, limit):
    """``text`` cut to at most ``limit`` characters at its last sentence end, else at its last word end."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", head)]
    if ends:
        return head[:ends[-1]].strip()
    return head.rsplit(" ", 1)[0].strip() if " " in head else head


def describe(roles, procedure, *, lengths, label, evidence, excluded=()):
    """The sealed ``description`` record of one procedure: ONE ``roles.plain`` call (none for a procedure without a
    note hook, which shows the solver nothing). ``lengths``: the procedure's shown note lengths on the run slice (their
    median sets the target); ``excluded``: the package's narrowing of it. ``band``: within, clipped (cut to the band),
    short (below it) or no_target."""
    require(isinstance(procedure, Procedure) and all(type(n) is int and n > 0 for n in lengths),
            "A procedure and its positive note lengths")
    benches = _scope(procedure, excluded)
    target = median_low(lengths) if lengths else None
    cap = min([procedure.max_note_chars] + [MAX_NOTE_CHARS[b] for b in benches])
    upper = min(cap, DEFAULT_TARGET if target is None else int(target * (1 + TEXT_LENGTH_BAND)))
    text = request = band = None
    dropped, reason = 0, None
    if not cap:
        reason = "no_note_hook"
    else:
        user = json.dumps({"procedure": {"description": procedure.description, "hooks": list(procedure.hooks),
                                         "header": procedure.header, "source": procedure.source},
                           "target_chars": target}, ensure_ascii=False, sort_keys=True)
        reply = roles.plain(ROLE, DESCRIBER_SYSTEM, user, label=label)
        request = roles.calls[-1]["request_sha256"]
        full, dropped = screened(reply, benches) if reply is not None else ("", 0)
        text = clipped(full, upper) or None
        if reply is None or text is None:
            reason = "no_reply" if reply is None else "screened_empty"
        elif target is None:
            band = "no_target"
        elif len(text) < target * (1 - TEXT_LENGTH_BAND):
            band = "short"
        else:
            band = "clipped" if len(text) < len(full) else "within"
    return record("description", evidence, {
        "procedure": procedure.id, "procedure_sha256": procedure.sha256, "text": text,
        "text_sha256": digest(text) if text is not None else None, "prompt_sha256": DESCRIBER_PROMPT_SHA256,
        "request_sha256": request, "target_chars": target, "chars": len(text) if text else 0, "cap": cap,
        "band": band, "dropped_sentences": dropped, "reason": reason})


def texts(records):
    """{procedure id: frozen text} of the usable descriptions (the solver's ``text=``)."""
    return {r["procedure"]: r["text"] for r in (verified(v, "description") for v in records) if r["text"] is not None}


def entries(records):
    """{procedure id: {text_sha256, prompt_sha256}} of the usable descriptions (``package.with_describer``)."""
    out = {}
    for value in records:
        value = verified(value, "description")
        require(value["prompt_sha256"] == DESCRIBER_PROMPT_SHA256, "A description by the pinned prompt")
        if value["text"] is not None:
            require(digest(value["text"]) == value["text_sha256"], "A description's text hash")
            out[value["procedure"]] = {"text_sha256": value["text_sha256"], "prompt_sha256": value["prompt_sha256"]}
    return out
