"""Failure detectors of the examiner (protocol ``fivebench-execskill-v1``; registration §5.2, §7.1 after Codex F10,
F11 and consistency check C2; implementation plan §1 detectors row, §2.4; T-DET-1..6).

A detector is a model-written module whose one entry point ``detect(view) -> bool`` reads ONE masked view
(``trajectories.masked_view``, purpose "detector"): QA the task, the notes and the replies with every answer carrier
masked; SpreadsheetBench the task, the first notes and the first program (the pre-check and the repair exchange are
the program's run status on the public input); ALFWorld the landmark view (Codex F10: an episode still running after
step 10, as its first 10 (observation, action) pairs -- no terminal observation, no won/done flag, no step count). It
never sees a reference answer, a token or a run status, and it runs only in the sandbox (worker kind "detector").

Mechanical categories: fixed registrar code with no reference answer (§5.2). They are not examiner evolution.
- ``MECHANICAL[bench]`` ({name: test of a whitelisted trajectory}): the registered categories on the whole trajectory,
  descriptive only. QA reads the deciding reply and the receipts' truncation; SpreadsheetBench reads the first reply
  and the stored pre-check; ALFWorld reads every step, with the canonicaliser's ``how`` and the observation after the
  step.
- ``MECHANICAL_MASKED[bench]`` ({name: test of a detector view}): the same categories on the SAME masked view the
  detector reads. With the accepted detectors they define the residual cells (check C2). A category that needs what
  the view hides is descriptive only:
  - QA ``truncated_or_suspected`` keeps only its text part (an answer tag left open);
  - SpreadsheetBench ``program_exception_on_public_input`` (the run status) drops out;
  - ALFWorld keeps the three categories its ten (observation, action) pairs carry. ``step_budget_exhausted`` and the
    inadmissible and level-1 shares need the step count or the canonicaliser's log.

The rules (the registration names the categories; these are the registrar's definitions):
- QA, on one reply: ``empty_reply`` = no reply or a blank one; ``no_answer_tag`` = a non-blank reply without a closed
  answer tag (frozen ``checks.last_answer``); ``json_answer_untagged`` = no answer tag but a JSON answer
  (``judge.json_answer``); ``multiple_answers`` = more than one closed answer tag; ``truncated_or_suspected`` = an
  answer tag left open (on the whole trajectory also any call delivered truncated or stopped for length).
- SpreadsheetBench, on the first reply: ``no_program`` = the frozen ``code_delivery.extract_python`` finds no program;
  ``excel_formula_only`` = no explicit Python block and a line that starts with ``=`` and a function call;
  ``fence_glued`` = a line with a code fence after other text; ``program_exception_on_public_input`` = the stored
  pre-check status "exception".
- ALFWorld, on the (action, observation after it) pairs: ``revisit_empty_receptacle>=3`` = at least 3 "go to X" where X
  was last seen holding nothing; ``repeated_action_loop`` = one action, or two alternating actions, repeated three
  times in a row; ``nothing_happens_share>0.2`` = more than a fifth of the known after-observations are "Nothing
  happens"; on the whole episode also ``step_budget_exhausted`` = 50 steps (the frozen default, backends.py:727),
  ``inadmissible_share>0.2`` = more than a fifth of the steps executed a command the canonicaliser could not map
  (``how`` "unchanged"), ``level1_canonical_share`` = more than a fifth of the steps were mapped by level 1.

Validation on the hold half (§7.1, Codex F11):
- ``split``: the run trajectories in a write and a hold half, by item, ALFWorld by room (at least
  ``MIN_ROOMS_PER_HALF`` rooms per half, else "cannot_decide"), in the seeded order of ``execskill-v1:detsplit:<unit>``.
- ``seal_candidates``: the step's candidates (at most ``DETECTORS_PER_STEP``) are hashed and written once BEFORE the
  hold half is read. ``validate`` refuses candidates that differ from the sealed ones.
- ``validate``: works on the included hold cells; Excluded views and infrastructure tokens are counted by reason.
  The residual cells are those on which no masked category and no accepted detector fires. A candidate is accepted
  iff all of these hold:
  - it fires on at least ``DETECTOR_MIN_FIRED`` residual cells of at least ``DETECTOR_MIN_ITEMS`` items (ALFWorld:
    also ``DETECTOR_MIN_ROOMS`` rooms);
  - the one-sided item-cluster (ALFWorld: room-cluster) bootstrap p of the null "precision - base <=
    ``DETECTOR_LIFT``" is at most ``HOLM_FAMILY`` after Holm over the step's candidates. Base is the residual cells'
    failure rate; the bootstrap uses ``BOOTSTRAP_RESAMPLES`` draws;
  - its recall among the residual failures is at least ``DETECTOR_MIN_RECALL``;
  - its Jaccard with every accepted detector's alarms, on the WHOLE included hold half before residualization, is
    below ``DETECTOR_MAX_JACCARD``;
  - it has no fault, and two runs agree (PYTHONHASHSEED 0 in sorted cell order, 1 in reverse order).
  A hold half too small to meet the counts is "cannot_decide" outright. Model-written labels are never evidence.
"""
from __future__ import annotations

import ast
import hashlib
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass
from fractions import Fraction

from skillopt.coevo5.checks import ANSWER, last_answer
from skillopt.coevo5.data import ranked
from skillopt.continual_eval.code_delivery import extract_python
from skillopt.continual_eval.core import require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import policy
from .generators.families import Entry, bundle
from .judge import json_answer
from .outcomes_ext import TRUNCATED
from .protocol import (BENCHES, BOOTSTRAP_RESAMPLES, DETECTOR_LIFT, DETECTOR_MAX_JACCARD, DETECTOR_MIN_FIRED,
                       DETECTOR_MIN_ITEMS, DETECTOR_MIN_RECALL, DETECTOR_MIN_ROOMS, DETECTORS_PER_STEP, HOLM_FAMILY,
                       MIN_ROOMS_PER_HALF, QA, SANDBOX_TIMEOUTS, SEED, detsplit_tag, record, verified)
from .stats_ext import holm
from .trajectories import OPEN_TAG, UNKNOWN_TOKENS, Excluded, masked_view, whitelisted

ENTRY = "detect"
DETECTOR_ID = re.compile(r"d-[a-z]+-\d{1,3}-\d{1,2}|fx-[a-z0-9][a-z0-9-]{0,39}")
MAX_DESCRIPTION = 600
VIEWS = {"alfworld": "alf_landmark10", "spreadsheetbench": "sheet_masked", **{bench: "qa_masked" for bench in QA}}
CANDIDATES = "candidates.json"
CANNOT_DECIDE = "cannot_decide"

SHARE = Fraction(1, 5)  # the registered share categories' 0.2
REVISITS = 3
LOOP_REPEATS = 3
ALFWORLD_MAX_STEPS = 50  # backends.py:727, the frozen default; failed episodes run all 50 (§7.1 [FP])
LEVEL1 = ("tag_level1", "whole_level1")
FORMULA_LINE = re.compile(r"^\s*=\s*[A-Za-z][A-Za-z0-9._]*\s*\(", re.M)
GLUED_FENCE = re.compile(r"^[^\n`]*[^\s`][^\n`]*```", re.M)
NOTHING_HAPPENS = re.compile(r"\s*Nothing happens", re.I)
SEES_NOTHING = re.compile(r"\byou see nothing\b", re.I)
GO_TO = re.compile(r"\s*go to (.+?)\s*$")
OPEN = re.compile(r"\s*open (.+?)\s*$")
PUT = re.compile(r"\s*(?:move .+? to|put .+? (?:in/on|in|on)) (.+?)\s*$")


@dataclass(frozen=True)
class Detector:
    """One candidate or accepted detector: ``id`` (``d-<bench>-<k>-<n>``; ``fx-`` for engineering fixtures), its
    bench, its source (a module defining ``detect(view)``; it must pass the static policy for its bench) and its
    description (at most 600 characters)."""
    id: str
    bench: str
    source: str
    description: str

    def __post_init__(self):
        require(type(self.id) is str and DETECTOR_ID.fullmatch(self.id) is not None and self.bench in BENCHES,
                "A detector id and a known bench")
        require(type(self.description) is str and 0 < len(self.description) <= MAX_DESCRIPTION,
                "A detector description of 1 to 600 characters")
        violations = policy.check(self.source, bench=self.bench)
        if violations:
            raise ValueError("detector_policy: " + ",".join(sorted({v.rule for v in violations})))
        require(any(isinstance(node, ast.FunctionDef) and node.name == ENTRY for node in ast.parse(self.source).body),
                "A detector defines detect(view) at module level")


# ------------------------------------------------------------------------------------------ mechanical categories
def empty_reply(reply):
    return reply is None or not reply.strip()


def no_answer_tag(reply):
    return not empty_reply(reply) and last_answer(reply) is None


def json_answer_untagged(reply):
    return no_answer_tag(reply) and json_answer(reply) is not None


def multiple_answers(reply):
    return not empty_reply(reply) and len(ANSWER.findall(reply)) > 1


def open_answer_tag(reply):
    return not empty_reply(reply) and OPEN_TAG.search(reply) is not None


def no_program(reply):
    return extract_python(reply)["status"] != "available"


def excel_formula_only(reply):
    return (not empty_reply(reply) and extract_python(reply)["explicit_python_blocks"] == 0
            and FORMULA_LINE.search(reply) is not None)


def fence_glued(reply):
    return not empty_reply(reply) and GLUED_FENCE.search(reply) is not None


def empty_revisits(pairs):
    """How many "go to X" went back to an X last seen holding nothing (module docstring)."""
    empty, count = set(), 0
    for action, after in pairs:
        action = action if type(action) is str else ""
        went, opened, put = GO_TO.fullmatch(action), OPEN.fullmatch(action), PUT.fullmatch(action)
        if went and went.group(1) in empty:
            count += 1
        target = (went or opened or put).group(1) if (went or opened or put) else None
        if target is None or type(after) is not str or NOTHING_HAPPENS.match(after):
            continue
        if not put and SEES_NOTHING.search(after):
            empty.add(target)
        else:
            empty.discard(target)
    return count


def repeated_action_loop(pairs):
    """One action, or two alternating actions, executed three times in a row."""
    actions = [action for action, _ in pairs]
    for period in (1, 2):
        for start in range(len(actions) - LOOP_REPEATS * period + 1):
            block = actions[start:start + period]
            if period == 2 and block[0] == block[1]:
                continue
            if actions[start:start + LOOP_REPEATS * period] == block * LOOP_REPEATS:
                return True
    return False


def nothing_happens_share(pairs):
    known = [after for _, after in pairs if type(after) is str]
    return bool(known) and Fraction(sum(NOTHING_HAPPENS.match(after) is not None for after in known),
                                    len(known)) > SHARE


QA_TEXT = {"no_answer_tag": no_answer_tag, "json_answer_untagged": json_answer_untagged,
           "multiple_answers": multiple_answers, "truncated_or_suspected": open_answer_tag, "empty_reply": empty_reply}
SHEET_TEXT = {"no_program": no_program, "excel_formula_only": excel_formula_only, "fence_glued": fence_glued}
ALF_PAIRS = {"revisit_empty_receptacle>=3": lambda pairs: empty_revisits(pairs) >= REVISITS,
             "repeated_action_loop": repeated_action_loop, "nothing_happens_share>0.2": nothing_happens_share}


def _deciding_reply(trajectory):
    replies, deciding = trajectory["replies"], trajectory["deciding_receipt"]
    if type(deciding) is int and 0 <= deciding < len(replies):
        return replies[deciding]
    return replies[-1] if replies else None


def _last_reply(view):
    replies = view.get("replies") or []
    return replies[-1] if replies else None


def _first_reply(value):
    replies = value.get("replies") or []
    return replies[0] if replies else None


def _trajectory_pairs(trajectory):
    return [(step["action"], step["post_observation"]) for step in trajectory["alfworld_steps"] or []]


def _view_pairs(view):
    """The landmark view's (action, observation after it) pairs: the next step's observation; none after step 10."""
    steps = view["steps"]
    return [(step["action"], steps[i + 1]["observation"] if i + 1 < len(steps) else None)
            for i, step in enumerate(steps)]


def _truncated(trajectory):
    return any(call["receipt"].get("delivery") == TRUNCATED or call["receipt"].get("finish_reason") == "length"
               for call in trajectory["calls"])


def _share(trajectory, hows):
    steps = trajectory["alfworld_steps"] or []
    return bool(steps) and Fraction(sum(step["how"] in hows for step in steps), len(steps)) > SHARE


def _on(take, test):
    """A category testing what ``take`` reads from its input."""
    return lambda value: bool(test(take(value)))


MECHANICAL_MASKED = {
    **{bench: {name: _on(_last_reply, test) for name, test in QA_TEXT.items()} for bench in QA},
    "spreadsheetbench": {name: _on(_first_reply, test) for name, test in SHEET_TEXT.items()},
    "alfworld": {name: _on(_view_pairs, test) for name, test in ALF_PAIRS.items()},
}
MECHANICAL = {
    **{bench: {**{name: _on(_deciding_reply, test) for name, test in QA_TEXT.items()},
               "truncated_or_suspected": lambda t: open_answer_tag(_deciding_reply(t)) or _truncated(t)}
       for bench in QA},
    "spreadsheetbench": {**{name: _on(_first_reply, test) for name, test in SHEET_TEXT.items()},
                         "program_exception_on_public_input":
                             lambda t: (t["shell"].get("precheck") or {}).get("status") == "exception"},
    "alfworld": {"step_budget_exhausted": lambda t: len(t["alfworld_steps"] or []) >= ALFWORLD_MAX_STEPS,
                 **{name: _on(_trajectory_pairs, test) for name, test in ALF_PAIRS.items()},
                 "inadmissible_share>0.2": lambda t: _share(t, ("unchanged",)),
                 "level1_canonical_share": lambda t: _share(t, LEVEL1)},
}


def mechanical(trajectory, *, bench):
    """The registered categories that fire on one whole (whitelisted) trajectory, sorted; descriptive only."""
    clean = whitelisted(trajectory)
    require(clean["bench"] == bench, "A trajectory of the bench")
    return sorted(name for name, test in MECHANICAL[bench].items() if test(clean))


def mechanical_masked(view, *, bench):
    """The categories that fire on one detector view (the residual definition, check C2), sorted."""
    require(bench in BENCHES and view.get("bench") == bench, "A detector view of the bench")
    return sorted(name for name, test in MECHANICAL_MASKED[bench].items() if test(view))


def diagnosis(trajectories, *, bench):
    """What the ENGINEER is shown of the mechanical categories (§5.2): per registered category its cells and failed
    cells on the whole run-slice trajectories (descriptive), and per failed cell the categories that fired. The
    examiner gets ``examiner_diagnosis`` (the write half, masked views); the engineer's payload takes ``counts``."""
    categories = {name: {"cells": 0, "failed": 0} for name in MECHANICAL[bench]}
    failing = {}
    for trajectory in trajectories:
        fired, failed = mechanical(trajectory, bench=bench), trajectory["token"] == "fail"
        for name in fired:
            categories[name]["cells"] += 1
            categories[name]["failed"] += failed
        if failed:
            failing[trajectory["cell"]] = fired
    return {"cells": len(trajectories), "failed": len(failing), "categories": categories, "failing": failing}


def counts(found):
    """The counts of a diagnosis -- cells, failed cells and per category its cells and failed cells -- without any
    cell id or per-cell label (what the engineer's ``detectors`` field may carry, §4.2)."""
    return {"cells": found["cells"], "failed": found["failed"], "categories": found["categories"]}


def examiner_diagnosis(halves, *, bench):
    """What the EXAMINER is shown of the mechanical categories (§4.3, §5.2; isolation review 6): the write half of
    ``split`` only -- no hold-half cell appears, before ``seal_candidates`` -- with the categories computed on the
    examiner's masked view (``MECHANICAL_MASKED``, the residual's own definition): per category its cells and failed
    cells, per failed write cell the categories that fired, and the excluded cells by reason."""
    require(isinstance(halves, dict) and {"write", "hold"} <= set(halves), "The examiner's diagnosis takes the split")
    write, hold = halves["write"], {t["cell"] for t in halves["hold"]}
    require(not hold & {t["cell"] for t in write}, "No hold-half cell reaches the examiner")
    categories = {name: {"cells": 0, "failed": 0} for name in MECHANICAL_MASKED[bench]}
    failing, excluded, shown = {}, Counter(), 0
    for trajectory in write:
        view = masked_view(trajectory, bench=bench, purpose="examiner")
        if isinstance(view, Excluded):
            excluded[view.reason] += 1
            continue
        shown += 1
        fired, failed = mechanical_masked(view, bench=bench), trajectory["token"] == "fail"
        for name in fired:
            categories[name]["cells"] += 1
            categories[name]["failed"] += failed
        if failed:
            failing[trajectory["cell"]] = fired
    return {"half": "write", "cells": shown, "failed": len(failing), "categories": categories, "failing": failing,
            "excluded": dict(sorted(excluded.items()))}


# ------------------------------------------------------------------------------------------- split and sealing
def split(trajectories, *, bench, unit, rooms=None):
    """The write and hold halves of a run slice (§5.2, Codex F11): ``{"unit": "item" | "room", "tag", "status": "ok"
    | "cannot_decide", "write_<unit>s", "hold_<unit>s", "write", "hold"}``. Items (ALFWorld: rooms, from ``rooms``
    = {task_id: room}) in the seeded order of ``execskill-v1:detsplit:<unit>`` (``data.ranked``) are dealt
    alternately to the write and the hold half; ALFWorld with fewer than ``MIN_ROOMS_PER_HALF`` rooms in a half
    cannot be decided."""
    require(bench in BENCHES, "A known bench")
    if bench == "alfworld":
        require(isinstance(rooms, dict) and all(t["task_id"] in rooms for t in trajectories),
                "Every ALFWorld trajectory's item has its room")

    def group(trajectory):
        return str(rooms[trajectory["task_id"]]) if bench == "alfworld" else trajectory["task_id"]

    tag = detsplit_tag(unit)
    keys = [entry["task_id"] for entry in ranked([{"task_id": key} for key in sorted({group(t) for t in trajectories})],
                                                  SEED, tag)]
    write_keys, hold_keys = set(keys[0::2]), set(keys[1::2])
    by = "room" if bench == "alfworld" else "item"
    status = CANNOT_DECIDE if by == "room" and min(len(write_keys), len(hold_keys)) < MIN_ROOMS_PER_HALF else "ok"
    return {"unit": by, "tag": tag, "status": status, "write_%ss" % by: len(write_keys),
            "hold_%ss" % by: len(hold_keys), "write": [t for t in trajectories if group(t) in write_keys],
            "hold": [t for t in trajectories if group(t) in hold_keys]}


def candidates_sha256(detectors):
    """The digest of one step's candidates: 1 to ``DETECTORS_PER_STEP`` detectors of one bench, distinct ids."""
    detectors = list(detectors)
    require(1 <= len(detectors) <= DETECTORS_PER_STEP and all(isinstance(d, Detector) for d in detectors)
            and len({d.id for d in detectors}) == len(detectors) and len({d.bench for d in detectors}) == 1,
            "One step's candidates: 1 to 3 detectors of one bench with distinct ids")
    return digest([[d.id, d.bench, d.source, d.description] for d in detectors])


def seal_candidates(root, detectors, *, unit, written_from, evidence):
    """Write the step's candidates once to ``<root>/candidates.json`` BEFORE the hold half is read (Codex F11); the
    sealed ``fivebench-execskill-v1-detector-candidates`` record."""
    detectors = list(detectors)
    value = record("detector-candidates", evidence, {
        "unit": unit, "bench": detectors[0].bench if detectors else None, "written_from": written_from,
        "candidates": [asdict(d) for d in detectors], "candidates_sha256": candidates_sha256(detectors)})
    write_json(safe_path(root) / CANDIDATES, value)
    return value


# ------------------------------------------------------------------------------------------------- evaluation
def hold_cells(trajectories, *, bench):
    """({cell: {"view", "item", "failed"}}, {reason: n}): the cells a detector is validated on, and why the others
    are not (an ALFWorld episode outside the landmark task by outcome, a cell without a call, an infrastructure
    token as ``censored:infrastructure``)."""
    included, excluded = {}, Counter()
    for trajectory in trajectories:
        view = masked_view(trajectory, bench=bench, purpose="detector")
        if not isinstance(view, Excluded) and trajectory["token"] in UNKNOWN_TOKENS:
            view = Excluded("censored:infrastructure")
        if isinstance(view, Excluded):
            excluded[view.reason] += 1
            continue
        require(trajectory["cell"] not in included, "One trajectory per cell")
        included[trajectory["cell"]] = {"view": view, "item": trajectory["task_id"],
                                        "failed": trajectory["token"] == "fail"}
    return included, dict(sorted(excluded.items()))


def evaluate(detectors, views, workers, *, hashseed=0, reverse=False):
    """{detector id: {"fired": [cells], "faults": {cell: fault}}} of ``detectors`` on ``views`` ({cell: view}) in one
    fresh worker of kind "detector" (``workers(bundle, kind=, hashseed=, inputs_dir=)``, a context manager such as
    ``sandbox.client.with_worker`` with its options bound), cells in sorted order (reversed when ``reverse``). A value
    that is not a bool is a fault ``not_bool``."""
    detectors = list(detectors)
    out = {d.id: {"fired": [], "faults": {}} for d in detectors}
    if not detectors or not views:
        return out
    cells = sorted(views, reverse=reverse)
    package = bundle(Entry(d.id, d.source, (ENTRY,)) for d in detectors)
    with workers(package, kind="detector", hashseed=hashseed, inputs_dir=None) as worker:
        for detector in detectors:
            found = out[detector.id]
            for cell in cells:
                result = worker.call(detector.id, ENTRY, [views[cell]], timeout_s=SANDBOX_TIMEOUTS["detector"])
                if not result["ok"]:
                    found["faults"][cell] = result["fault"]
                elif type(result["value"]) is not bool:
                    found["faults"][cell] = "not_bool"
                elif result["value"]:
                    found["fired"].append(cell)
    for found in out.values():
        found["fired"].sort()
    return out


def _seed(candidates, detector_id):
    return int(hashlib.sha256(("%s:%s:%s" % (SEED, candidates, detector_id)).encode()).hexdigest()[:16], 16)


def bootstrap_p(residual, fired, failed, cluster, *, seed, resamples=BOOTSTRAP_RESAMPLES):
    """The one-sided cluster-bootstrap p of the null "precision - base <= DETECTOR_LIFT" on the ``residual`` cells:
    the share of resamples of whole clusters (``cluster``: {cell: item or room}) in which the detector's precision
    minus the residual failure rate is at most the lift, a resample without an alarm counting for the null."""
    totals = {}
    for cell in residual:
        entry = totals.setdefault(cluster[cell], [0, 0, 0, 0])
        hit = cell in fired
        entry[0], entry[1] = entry[0] + 1, entry[1] + failed[cell]
        entry[2], entry[3] = entry[2] + hit, entry[3] + (hit and failed[cell])
    groups = [totals[key] for key in sorted(totals)]
    if not groups:
        return 1.0
    rng, null = random.Random(seed), 0
    for _ in range(resamples):
        n = bad = alarms = hits = 0
        for _ in range(len(groups)):
            cells, failures, fired_cells, fired_failures = groups[rng.randrange(len(groups))]
            n, bad, alarms, hits = n + cells, bad + failures, alarms + fired_cells, hits + fired_failures
        if alarms == 0 or hits * n - bad * alarms <= DETECTOR_LIFT * alarms * n:
            null += 1
    return null / resamples


def jaccard(first, second):
    first, second = set(first), set(second)
    union = first | second
    return len(first & second) / len(union) if union else 0.0


def _jaccard_counts(first, second):
    """[shared, union] alarm counts of ``jaccard``: the exact ratio for the §7.1 rule (Codex review 2026-10-22 #11)."""
    first, second = set(first), set(second)
    return [len(first & second), len(first | second)]


def _ratio(counts):
    """The exact fraction of [numerator, denominator] counts; 0 when the denominator is 0 (no alarm, no failure)."""
    numerator, denominator = counts
    return Fraction(numerator, denominator) if denominator else Fraction(0)


def _too_small(included, rooms, bench):
    items = {entry["item"] for entry in included.values()}
    if len(included) < DETECTOR_MIN_FIRED or len(items) < DETECTOR_MIN_ITEMS:
        return True
    return bench == "alfworld" and len({str(rooms[item]) for item in items}) < DETECTOR_MIN_ROOMS


def validate(sealed, detectors, halves, *, bench, library, workers, rooms=None, evidence):
    """The sealed ``fivebench-execskill-v1-detector-validation`` record of one step's candidates on the hold half of
    ``halves`` (``split``), with ``library`` the bench's accepted detectors (module docstring). ``sealed``: the
    record of ``seal_candidates``; the candidates must be exactly the sealed ones. ``rooms``: {task_id: room}
    (ALFWorld)."""
    sealed = verified(sealed, "detector-candidates")
    detectors, library = list(detectors), list(library)
    require(sealed["bench"] == bench and all(d.bench == bench for d in detectors + library), "Detectors of the bench")
    if candidates_sha256(detectors) != sealed["candidates_sha256"]:
        raise ValueError("candidates_changed_after_sealing: the candidates differ from the sealed ones (Codex F11)")
    require(bench != "alfworld" or isinstance(rooms, dict), "ALFWorld validation needs the rooms")
    included, excluded = hold_cells(halves["hold"], bench=bench)
    base_fields = {"bench": bench, "unit": sealed["unit"], "candidates_sha256": sealed["candidates_sha256"],
                   "view": VIEWS[bench], "split": {k: v for k, v in halves.items() if k not in ("write", "hold")},
                   "included": len(included), "excluded": excluded}
    if halves["status"] == CANNOT_DECIDE or _too_small(included, rooms, bench):
        return record("detector-validation", evidence, {
            **base_fields, "status": CANNOT_DECIDE, "residual_cells": None, "base": None, "masked_categories": {},
            "library": {}, "candidates": [{"id": d.id, "accepted": False, "reason": CANNOT_DECIDE} for d in detectors]})
    views = {cell: entry["view"] for cell, entry in included.items()}
    failed = {cell: entry["failed"] for cell, entry in included.items()}
    cluster = {cell: str(rooms[entry["item"]]) if bench == "alfworld" else entry["item"]
               for cell, entry in included.items()}
    categories = {cell: mechanical_masked(view, bench=bench) for cell, view in views.items()}
    known = evaluate(library, views, workers)
    covered = {cell for found in known.values() for cell in found["fired"]}
    residual = sorted(cell for cell in views if not categories[cell] and cell not in covered)
    residual_failed = sum(failed[cell] for cell in residual)
    base = Fraction(residual_failed, len(residual)) if residual else None
    first, second = evaluate(detectors, views, workers), evaluate(detectors, views, workers, hashseed=1, reverse=True)
    rows = []
    for detector in detectors:
        found = first[detector.id]
        fired = set(found["fired"]) & set(residual)
        hits = sum(failed[cell] for cell in fired)
        precision = Fraction(hits, len(fired)) if fired else None
        # §7.1 compares the exact ratios (Codex review 2026-10-22 #11: a float round trip put 3/20 below 0.15): the
        # integer counts ride in the row, the floats are for reading only
        overlap = max((_jaccard_counts(found["fired"], known[d.id]["fired"]) for d in library), key=_ratio,
                      default=[0, 0])
        rows.append({
            "id": detector.id, "n_fired": len(fired), "n_items": len({included[c]["item"] for c in fired}),
            "n_rooms": len({cluster[c] for c in fired}) if bench == "alfworld" else None,
            "precision": None if precision is None else float(precision),
            "lift": None if precision is None or base is None else float(precision - base),
            "p_boot_lift_le_0.10": bootstrap_p(residual, fired, failed, cluster,
                                               seed=_seed(sealed["candidates_sha256"], detector.id)),
            "recall_residual": float(_ratio([hits, residual_failed])), "recall_counts": [hits, residual_failed],
            "jaccard_max_full_hold": float(_ratio(overlap)), "jaccard_max_counts": overlap,
            "faults": len(found["faults"]) + len(second[detector.id]["faults"]),
            "deterministic": found == second[detector.id]})
    for row, adjusted in zip(rows, holm([row["p_boot_lift_le_0.10"] for row in rows])):
        row["p_holm"] = adjusted
        row["reason"] = _verdict(row, bench)
        row["accepted"] = row["reason"] == "accepted"
    return record("detector-validation", evidence, {
        **base_fields, "status": "ok", "residual_cells": len(residual), "residual_failed": residual_failed,
        "base": None if base is None else float(base),
        "masked_categories": dict(sorted(Counter(n for names in categories.values() for n in names).items())),
        "library": {d.id: {"fired": len(known[d.id]["fired"]), "faults": len(known[d.id]["faults"])}
                    for d in library},
        "candidates": rows})


def _verdict(row, bench):
    """The first acceptance rule ``row`` fails, or "accepted" (§7.1). Recall and Jaccard are compared as exact
    fractions of the row's integer counts (``recall_counts``, ``jaccard_max_counts``), never through a float (Codex
    review 2026-10-22 #11: recall exactly 3/20 meets ``DETECTOR_MIN_RECALL``)."""
    if row["faults"] or not row["deterministic"]:
        return "faults_or_nondeterministic"
    if row["n_fired"] < DETECTOR_MIN_FIRED or row["n_items"] < DETECTOR_MIN_ITEMS:
        return "too_few_alarms"
    if bench == "alfworld" and row["n_rooms"] < DETECTOR_MIN_ROOMS:
        return "too_few_rooms"
    if row["p_holm"] > HOLM_FAMILY:
        return "lift_not_established"
    if _ratio(row["recall_counts"]) < DETECTOR_MIN_RECALL:
        return "recall_below_minimum"
    if _ratio(row["jaccard_max_counts"]) >= DETECTOR_MAX_JACCARD:
        return "duplicate_of_accepted"
    return "accepted"


def detector_records(validation, detectors, *, written_from, evidence):
    """The sealed ``fivebench-execskill-v1-detector`` record of every candidate (plan §2.4) from its validation."""
    validation = verified(validation, "detector-validation")
    rows = {row["id"]: row for row in validation["candidates"]}
    require({d.id for d in detectors} == set(rows), "One validation row per candidate")
    context = {"status": validation["status"], "residual_rule": "mechanical_on_masked_view",
               "excluded": validation["excluded"], "residual_cells": validation["residual_cells"],
               "base": validation["base"]}
    return [record("detector", evidence, {
        "id": d.id, "bench": d.bench, "source": d.source, "description": d.description, "view": validation["view"],
        "written_from": written_from, "candidates_sha256": validation["candidates_sha256"],
        "split": validation["split"], "validation": {**context, **rows[d.id]}, "retired_at": None})
        for d in detectors]
