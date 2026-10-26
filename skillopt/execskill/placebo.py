"""The placebo arms P_y (paired) and P_i (irrelevant text) of an acceptance round (protocol ``fivebench-execskill-v1``;
registration §6.1 placebo rows and "替身的细则" [FE-F5, FA-F11, ME-F9, MA-M22, EE-F6], Codex F4/F5;
implementation plan §1 placebo.py, §3 "Placebo arms", T-PLACEBO-1..6; ticket A6-1 gives the shape the shell takes).

P_y is the parent S plus a yoked sham of every changed procedure (§6.1 edit-type table): the package is the candidate
with any deleted or narrowed procedure put back as the parent had it (``placebo_package``), every changed procedure is
shammed, and the shell keeps its predicates, hooks, slots and trigger RULES (``solver.solve(placebo=...)``):

- notes (``before_call``, ``bindings``, ``sheet_feedback``, ALFWorld step and state notes): the procedure's constant
  header is rendered by the shell and stays; only the content is the paired donor's (``donors``). ``sham_fields`` puts
  that content into the length band: a donor note whose rendered length differs from the target by more than 20 % is
  clipped (trailing entries dropped, then the last text entry clipped) or extended with the same donor's next output
  (ALFWorld: its next steps), never beyond the procedure's declared note cap. The target is the length of the real note
  it replaces, computed before dispatch with zero model calls from the acceptance item's public view where that note
  exists before dispatch (``before_call``, ``bindings``: ``real_lengths``); for the dynamic hooks, whose real note
  exists only after dispatch, it is the procedure's median note length on the donor corpus (the run slice), the band
  the text arm T_F uses (§8.1). Only a length is read from an acceptance item, never content.
- compute, repair and the ALFWorld discouragement are the shell's rules (ticket A6-1): every ``<calc>`` of the arm is
  answered ``"not evaluated"`` with its expression echoed; the repair call keeps the program and the shell's own error
  message, the advice is the donor's, the trigger is the real hook's shadow on the arm's own run report; the
  discouraged commands are drawn at dispatch by ``sham_discourage``. Call counts are not matched; the acceptance
  reports the rates (Codex F5).

P_i (descriptive; SpreadsheetBench, OfficeQA and LiveMath only, owner #9 default) has the same package and slots; its
content is the item's registered irrelevant text (v3's eight control texts, coevo5 protocol.py:105-124, imported by
value) cut into ``facts`` of the same length as the P_y sham. It carries no binding, so no ``<calc>`` invitation.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics

from skillopt.continual_eval.core import require

from . import donors, notes
from .package import restore
from .protocol import DONOR_LENGTH_BAND, PLACEBO_CORPUS, yoke_tag
from .solver import sham_discouraged as sham_discourage  # noqa: F401 -- the one draw rule at dispatch (ticket A6-1)

PI_BENCHES = ("spreadsheetbench", "officeqa", "livemath")  # §6.1 (owner #9 default: not ALFWorld, not SearchQA)
FACT_CHARS = notes.FIELD_TYPES["facts"]["max_chars"]


def placebo_package(candidate, parent):
    """``(package, shammed ids)`` of P_y and P_i (§6.1 table): the candidate with each deleted or narrowed procedure
    restored as the parent had it; every changed procedure is shammed."""
    changed = donors.changed(parent, candidate)
    back = {p.id for kind, p, _ in changed if kind in ("deletion", "narrowing")}
    return (restore(candidate, parent, back) if back else candidate), tuple(p.id for _, p, _ in changed)


def rendered(fields, *, bench, header, outcome_judged=False):
    """The length of one procedure's note as the shell renders it (its header included)."""
    if outcome_judged:
        fields, dropped = notes.screen(fields, bench=bench, outcome_judged=True)
        _, header_drops = notes.screen_header(header)
        fields = notes.suppress_faulted(fields, dropped + header_drops, outcome_judged=True)
    return len(notes.render(fields, bench=bench, header=header)) if fields else 0


def band(target, cap):
    """``(lower, upper)`` characters: the target +-20 % (``DONOR_LENGTH_BAND``), neither above the note cap."""
    require(type(target) is int and target >= 0 and type(cap) is int and cap >= 0, "Lengths are counts")
    lower = math.ceil(target * (1 - DONOR_LENGTH_BAND))
    upper = math.floor(target * (1 + DONOR_LENGTH_BAND))
    return min(lower, cap), min(upper, cap)


def _entries(fields):
    return [(name, value) for name in notes.FIELD_ORDER for value in fields.get(name, [])]


def _fields(entries):
    out = {}
    for name, value in entries:
        out.setdefault(name, []).append(value)
    return out


def sham_fields(segments, target, *, bench, header, cap, outcome_judged=False):
    """``(fields, band record)``: the donor content in the length band of ``target`` (module docstring).
    ``segments``: the donor's screened fields, the paired output first, then the same donor's next outputs;
    ``header``: the procedure's constant header (the shell renders it; it counts here); ``cap``: its note cap."""
    lower, upper = band(target, cap)
    if outcome_judged:
        screened = [notes.screen(segment, bench=bench, outcome_judged=True) for segment in segments]
        segments = [notes.suppress_faulted(fields, dropped, outcome_judged=True) for fields, dropped in screened]

    def size(entries):
        fields = _fields(entries)
        _, dropped = notes.screen(fields, bench=bench, outcome_judged=outcome_judged)
        return (math.inf if notes.fault_drops(dropped, outcome_judged=outcome_judged)
                else rendered(fields, bench=bench, header=header, outcome_judged=outcome_judged))

    first = _entries(segments[0]) if segments else []
    chosen, action = [], "kept"
    if target == 0:
        action = "nothing"
    elif size(first) <= upper:
        chosen = list(first)
        for segment in segments[1:]:
            for entry in _entries(segment):
                if size(chosen) >= lower:
                    break
                if size(chosen + [entry]) <= upper:
                    chosen.append(entry)
                    action = "extended"
    else:
        action = "clipped"
        for name, value in first:
            if size(chosen + [(name, value)]) <= upper:
                chosen.append((name, value))
                continue
            if isinstance(value, str):  # the last text entry, clipped to the room left
                room = upper - size(chosen + [(name, "x")]) + 1
                clipped = value[:room].rstrip() if room > 0 else ""
                if clipped and size(chosen + [(name, clipped)]) <= upper:
                    chosen.append((name, clipped))
            break
    fields = _fields(chosen)
    chars = rendered(fields, bench=bench, header=header, outcome_judged=outcome_judged)
    within = lower <= chars <= upper
    return fields, {"target": target, "chars": chars, "within": within,
                    "action": "short" if action == "kept" and not within else action}


def real_lengths(changed, views, workers, *, bench, packages):
    """{procedure: {item: {hook: chars}}}: the rendered length of each changed procedure's real ``before_call`` /
    ``bindings`` note on each acceptance item, from the item's public view with zero model calls (the shell's
    arguments; bindings verified on the item's own text). ``changed``: ``donors.changed``; ``packages``: {"candidate",
    "parent"}; ``workers(package, item)``: ``router.plan``'s worker factory."""
    out = {p.id: {} for _, p, _ in changed}
    for item, view in views.items():
        for side in ("candidate", "parent"):
            mine = [p for _, p, s in changed if s == side and set(p.hooks) & set(donors.QA_HOOKS)]
            if not mine:
                continue
            with workers(packages[side], item) as worker:
                for procedure in mine:
                    found = donors.procedure_outputs(worker, procedure, {"id": item, "item": item, "view": view,
                                                                         "report": None, "steps": None},
                                                     bench=bench, faults=[])
                    out[procedure.id][item] = {hook: rendered(fields, bench=bench, header=procedure.header,
                                                            outcome_judged=notes.outcome_judged(procedure))
                                               for hook, fields in found.items()}
    return out


def median_length(corpus, procedure, hook):
    """The median rendered length of ``procedure``'s non-empty donor notes for a dynamic ``hook`` (0 when there is
    none): the band target of ``sheet_feedback`` and of ALFWorld steps."""
    lengths = []
    for content in corpus["outputs"][procedure.id].values():
        found = content.get(hook)
        if hook == donors.STEP_HOOK:
            notes_ = [entry["fields"] for entry in found or []]
        else:
            notes_ = [found] if found else []
        lengths += [rendered(f, bench=corpus["bench"], header=procedure.header,
                            outcome_judged=notes.outcome_judged(procedure)) for f in notes_ if f]
    return int(statistics.median(lengths)) if lengths else 0


def build_y(corpus, pairs, lengths, *, changed):
    """The sealed P_y content {item: {"procedures": {id: sham}, "donor", "bands"}} of the A* items (``pairs``:
    ``donors.pair``; ``lengths``: ``real_lengths``). A sham maps QA/SpreadsheetBench hooks to fields and ALFWorld's
    ``alf_before_step`` to the donor's step entries ``{"fields", "discourage"}`` (ticket A6-1)."""
    bench, out = corpus["bench"], {}
    medians = {(p.id, h): median_length(corpus, p, h) for _, p, _ in changed
               for h in (donors.SHEET_HOOK, donors.STEP_HOOK) if h in p.hooks}
    for item, donor in pairs.items():
        content, bands = {}, {}
        for _, procedure, _ in changed:
            sham, keep = {}, {"bench": bench, "header": procedure.header, "cap": procedure.max_note_chars,
                             **({"outcome_judged": True} if notes.outcome_judged(procedure) else {})}
            for hook in procedure.hooks:
                label = procedure.id + "/" + hook
                if hook in donors.QA_HOOKS:
                    sham[hook], bands[label] = sham_fields(donors.segments(corpus, procedure.id, donor, hook),
                                                           lengths[procedure.id][item][hook], **keep)
                elif hook == donors.SHEET_HOOK:
                    sham[hook], bands[label] = sham_fields(donors.segments(corpus, procedure.id, donor, hook),
                                                           medians[(procedure.id, hook)], **keep)
                elif hook == donors.STEP_HOOK:
                    entries = []
                    for t, step in enumerate(corpus["outputs"][procedure.id][donor].get(hook) or []):
                        fields, bands["%s/%d" % (label, t)] = sham_fields(
                            donors.segments(corpus, procedure.id, donor, hook, t), medians[(procedure.id, hook)],
                            **keep)
                        entries.append({"fields": fields, "discourage": step["discourage"]})
                    sham[hook] = entries
            content[procedure.id] = sham
        out[item] = {"procedures": content, "donor": donor, "bands": bands}
    return out


def irrelevant_text(item, unit):
    """The item's registered irrelevant text: one of the eight, by the sha256 of (``yoke_tag(unit)``, item)."""
    key = hashlib.sha256(json.dumps([yoke_tag(unit), item]).encode()).hexdigest()
    return PLACEBO_CORPUS[int(key, 16) % len(PLACEBO_CORPUS)]


def chunks(text, count):
    """The first ``count`` ``facts`` entries of ``text`` repeated without end, cut at spaces (<= 200 characters)."""
    out, line, words = [], "", text.split()
    require(words and max(len(w) for w in words) <= FACT_CHARS, "A placebo text has words that fit a fact")
    while len(out) < count:
        for word in words:
            if line and len(line) + 1 + len(word) > FACT_CHARS:
                out.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
    return out[:count]


def build_i(placebo_y, procedures, *, bench, unit):
    """The sealed P_i content {item: {"procedures": {id: {hook: fields}}}} (§6.1): every shammed note of P_y replaced
    by ``facts`` of the item's irrelevant text with the same rendered length (within 20 %); ALFWorld steps and benches
    outside ``PI_BENCHES`` have none (None). ``procedures``: {id: Procedure} of the shammed procedures."""
    if bench == "zebralogic":  # zebra-pc-v1: explicitly no irrelevant-text arm
        return None
    if bench not in PI_BENCHES:
        return None
    out = {}
    for item, entry in placebo_y.items():
        content = {}
        for procedure_id, sham in entry["procedures"].items():
            procedure = procedures[procedure_id]
            modern = notes.outcome_judged(procedure)
            content[procedure_id] = {}
            for hook, fields in sham.items():
                target, count = rendered(fields, bench=bench, header=procedure.header, outcome_judged=modern), 1
                text = irrelevant_text(item, unit)
                while target and rendered({"facts": chunks(text, count)}, bench=bench,
                                          header=procedure.header, outcome_judged=modern) < target:
                    count += 1
                content[procedure_id][hook], _ = sham_fields([{"facts": chunks(text, count)}], target, bench=bench,
                                                             header=procedure.header, cap=procedure.max_note_chars,
                                                             outcome_judged=modern)
        out[item] = {"procedures": content}
    return out


def arm(content, item, *, seed):
    """The ``placebo=`` value of ``solver.solve`` for one cell (ticket A6-1): the item's sealed sham content and the
    cell's discouragement seed ``protocol.discourage_tag(unit, cell)``."""
    require(type(seed) is str and seed and item in content, "A placebo cell of a sealed item, with its seed")
    return {"procedures": json.loads(json.dumps(content[item]["procedures"])), "seed": seed}
