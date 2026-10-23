"""The examiner role (protocol ``fivebench-execskill-v1``; registration §4.3, §5.2, §5.3, §7.1, §7.2 after Codex F8
and F11, owner rule (b) of §21; implementation plan §1 examiner row, §2.4, §2.5; T-EXAM-1..6).

The examiner is GLM-5.3 behind ``roles.Roles`` (the role settings of §4.3; the caller's endpoint charges its calls to
``<chain>:...:examiner`` and the researcher's to ``...:examiner:research``). It evolves along two paths (§7, owner
rule (b)). This module builds every examiner payload, parses every examiner reply and computes the gates; it makes no
solver call itself (the probe cells are run by the caller, charged to ``...:examiner``).

1. Failure detectors (§5.2, §7.1). ``detector_payload`` shows the WRITE half of the run slice only
   (``detectors.examiner_diagnosis`` refuses hold-half cells; isolation review 6) as masked views (answers masked by
   ``trajectories.masked_view``; the right/wrong bit ``passed`` is the one verdict shown, §4.3), each with the
   mechanical categories that fire on that view and the accepted detectors that fire on it (run in the sandbox), so
   the examiner can aim at the residual failures; plus the category counts and the accepted detectors' ids.
   ``detector_write`` makes at most ``DETECTOR_CALLS`` calls (the second only after an unparseable reply). The reply
   is one ```json manifest ``{"detectors": [{"description"}]}`` and one ```python block per detector, at most
   ``DETECTORS_PER_STEP``. Each becomes a ``detectors.Detector`` candidate with the registrar's id
   ``d-<bench>-<k>-<n>`` (``fx-`` for engineering fixtures); a source the static policy refuses, or one without
   ``detect(view)``, is dropped with its reason. Sealing and validation stay in ``detectors``.
2. Researched generation (§5.3, §7.2). ``policy_revise`` writes the step's generation policy: the families to use and at
   most ``MAX_RESEARCH_REQUESTS`` research requests. Its input is the family catalogue, the previous policy and the
   previous outcomes as aggregated counts (``outcome_counts``; isolation review 21: never per item). An invalid reply
   keeps the previous policy, or an empty one, which generates nothing (``no_material``). ``research_requests`` sends
   the policy's requests through ``research.Researcher``, the frozen machinery with its pre-dispatch leakage screen and
   ceilings. ``generator_payload`` shows the family catalogue (``generators.FAMILIES``), the qualified materials of one
   research half, the researched parameter values inside a registered range and, on SpreadsheetBench, the public views
   of the source tasks. ``generator_write`` parses the reply (one JSON object ``{"specs": [...]}``) into parameter
   specs: a family, a shown material and at most ``MAX_ITEMS_PER_FINDING`` parameter sets (ALFWorld: a selection filter
   citing a selection finding). A spec with an answer-like key anywhere is dropped: the examiner never writes answers
   (Codex F8). ``build`` turns the specs into items with ``generators.generate``, whose fixed reference functions give
   every truth, and keeps at most ``MAX_ITEMS_PER_FINDING`` items per finding across specs AND across the attempt's
   builds: the band adjustments rebuild from the same findings, so each build continues the finding-keyed counter
   of the previous one (``Generated.derived``, persisted by the step per build; Codex finding #10, §7.2, T-GEN-6).
3. The four gates (§7.2), zero model calls:
   - truth (``truth``): the fixed code's made, kept and dropped counts and the engine qualification;
   - difficulty band (``band``): the parent's pass rate on ``BAND_PROBE_ITEMS`` (30) probe items, one run, within
     ``BAND``; at most ``BAND_ROUNDS`` probes (two parameter adjustments), the last one deciding. A set with fewer
     than 30 qualified items, or a deciding probe of fewer, records ``insufficient_material`` and is never admitted
     (§7.2 "父包在 30 道探针题上"; Codex finding #9);
   - shortcut (``shortcut``): the card arm twice on at most ``SHORTCUT_PROBE_ITEMS`` probe variants
     (``shortcut_variant``: LiveMath options only, OfficeQA the question only, SpreadsheetBench without the
     workbook -- its public fields unchanged, solved in the shell's no-workbook mode ``probe_mode`` so the program
     still runs on the real input, ticket C1-2); every probe cell must have run in its bench's mode; an item right in
     both runs is dropped, and a dropped share above ``SHORTCUT_DROP_MAX`` rejects the whole set;
   - labels (``labels``): every truth from a registrar module's fixed code (and no answer in any spec, checked at
     parsing); LiveMath answer letters each within ``KEY_SHARE`` +- ``KEY_TOLERANCE``.
   ``gates`` seals all four as one record; a set that passes them is "admitted", which is engineering, not evolution.
   ``generator_record`` is the plan §2.5 generator record; after acceptance rounds its status is
   ``validity.status``. ``selection`` is ALFWorld's selection validity, reported apart and never an examiner claim.

Every payload is scanned for keys that would carry a reference or a verdict (``FORBIDDEN_KEYS``) and refused if one
appears.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction

from skillopt.coevo5.data import ranked
from skillopt.coevo5.roles import Invalid, fields, fit, items, text
from skillopt.continual_eval.core import require
from skillopt.continual_eval.datasets import LIVEMATH_LABELS
from skillopt.validator_pilot.api import digest

from . import detectors, generators, validity
from .generators import alfworld_select, livemath, officeqa, sheet
from .generators.families import Drop
from .package import FIXTURE
from .protocol import (BAND, BAND_PROBE_ITEMS, BAND_ROUNDS, BENCHES, DETECTOR_CALLS, DETECTORS_PER_STEP,
                       EXAMINER_PROBE_TAG as PROBE_TAG, G_ACC, GENERATOR_CALLS, KEY_SHARE, KEY_TOLERANCE,
                       MAX_CONCEPT_CHARS, MAX_ITEMS_PER_FINDING, MAX_QUESTION_CHARS, MAX_RATIONALE,
                       MAX_RESEARCH_REQUESTS, MAX_SPECS, POLICY_CALLS, ROLE_INPUT_BYTES, SEED, SHORTCUT_DROP_MAX,
                       SHORTCUT_PROBE_ITEMS, SHORTCUT_RUNS, record, verified)
from .research import FUNCTION, MAX_PARAMETERS, number_value
from .solver import NO_WORKBOOK
from .trajectories import UNKNOWN_TOKENS, Excluded, masked_view

ROLE = "examiner"
INSUFFICIENT = "insufficient_material"  # §7.2, Codex finding #9: a set or a deciding probe below 30 probe items
MAX_COUNT_KEY = 60
PASS = "pass"
BLOCK = re.compile(r"```([A-Za-z]*)[ \t]*\n(.*?)\n[ \t]*```", re.S)
# keys that carry a reference answer, a scoring verdict or hidden ALFWorld data; none may reach an examiner payload
FORBIDDEN_KEYS = frozenset({"private", "reference", "references", "answer", "answers", "truth", "test_files",
                            "judge", "token", "final", "official", "verdict", "lenient", "expert_plan", "gamefile",
                            "game_file", "extra"})
# keys by which a spec would state an answer; such a spec is dropped (Codex F8)
ANSWER_KEYS = frozenset({"answer", "answers", "solution", "expected", "truth", "result", "correct"})
SHORTCUT_PROBES = {"officeqa": "question_only", "livemath": "options_only", "spreadsheetbench": NO_WORKBOOK}
CHOOSABLE_KINDS = ("int", "ints")  # the parameter kinds a parameter_choice request may name
# the shell mode a probe cell runs in (its cell's ``shortcut``, ``solver.solve(..., shortcut=...)``); the QA variants
# are public-field blanks solved in the normal mode (ticket C1-2)
SHORTCUT_MODES = {"spreadsheetbench": NO_WORKBOOK}
TRUTH_BY = {officeqa.CHECKED_BY: "family_reference", livemath.CHECKED_BY: "sympy_solve",
            sheet.CHECKED_BY: "recalc_formula"}  # the registrar modules whose fixed code computes a truth
USABLE = {"officeqa": "table", "livemath": "definition", "alfworld": "selection"}  # SpreadsheetBench: a function set

POLICY_SYSTEM = """\
You are the examiner of a study that writes practice tasks for a solver model. Before tasks are built, a researcher \
looks up material in fixed sources: English Wikipedia and a pinned archive of Python 3.11, openpyxl and LibreOffice \
Calc documentation. A fixed registrar program then builds every task from a qualified research finding through a \
registered transformation family and computes every answer itself. You receive the bench's families, your previous \
generation policy and counts of what it produced: research requests by kind and status; task sets made and admitted; \
tasks made, kept and dropped by reason; the gates the sets failed ("no_items": no task survived the truth check, \
"band": the difficulty band, "shortcut", "labels"); band outcomes; spec statuses per family; generator statuses, \
predictive validity included. Write this step's generation policy: the families to use and at most 24 research \
requests.

Request kinds:
- {"kind": "family_material", "family", "concept", "topic"}: the material one family consumes. concept: OfficeQA a \
topic whose English Wikipedia articles hold numeric tables; LiveMath the definition or theorem the family's template \
uses; SpreadsheetBench one LibreOffice Calc function name in capitals (the family's formulas may call only researched \
functions). topic: an optional hint, or null.
- {"kind": "parameter_choice", "family", "question", "names", "topic"}: realistic values for 1 to 6 of the family's \
integer parameters (names), each to be backed by a verbatim quote.
- ALFWorld has no families: {"kind": "selection_hint", "question", "topic"}, a known failure mode to verify, used \
only to select existing games.
Research general knowledge only; never put the text of a task in a request.

Reply with only a JSON object {"families": [family names], "requests": [requests], "rationale": "at most 600 \
characters"}."""
DETECTOR_SYSTEM = """\
You are the examiner of a study in which a solver model is helped by small programs. You receive the solver's \
trajectories on training tasks of one benchmark (the write half of a run slice): each with every answer masked, \
whether it passed, the fixed mechanical failure categories that fire on it and the accepted detectors that fire on it \
("residual": true when none fires). Write at most 3 failure detectors: programs that read ONE view and return True \
when they predict that the solver failed. Aim at residual failures: a detector is validated on a held-out half, only \
on residual cells, against their base failure rate.

A detector is a Python module defining detect(view) -> bool; view is exactly a trajectory's "view": QA and \
SpreadsheetBench {"bench", "task", "notes", "replies"} (SpreadsheetBench: the first reply only); ALFWorld {"bench", \
"steps": [{"observation", "action"}]} (the first 10 steps of an episode still running at step 10). It never sees \
whether the cell passed. Code policy: at most 6000 bytes; module level holds only imports, literal constants \
(<= 2000 characters) and plain functions; importable: bisect, calendar, collections, copy, datetime, decimal, \
difflib, fractions, functools, heapq, itertools, json, math, numpy, openpyxl.utils, operator, pandas, re, statistics, \
string, sympy, textwrap, unicodedata. No classes, globals, I/O, eval, randomness or clock; no dunder names or private \
attributes; deterministic (never depend on set order) and fast (5 seconds per view).

Reply with one ```json block {"detectors": [{"description": "at most 600 characters: the failure pattern it \
predicts"}]} and then one ```python block per detector, in the same order. {"detectors": []} writes none. When the \
user message has "unparseable", your previous reply could not be read: reply again in this format."""
GENERATOR_SYSTEM = """\
You are the examiner of a study that writes practice tasks for a solver model. A fixed registrar program builds every \
task from a researched material (a numeric table, a quoted definition, quoted spreadsheet functions) and a parameter \
set you choose, and it computes every answer itself. You receive the bench's registered transformation families (each \
with the material kind it consumes and its parameter schema), the qualified research materials, researched parameter \
values and, on SpreadsheetBench, the public views of the source tasks whose workbooks the edits change. Write \
parameter specs: one family, one shown material of the family's kind and 1 to 10 parameter sets. Never write an \
answer, a solution, an expected value or a truth: a spec with such a field is dropped.

Parameter kinds: "int" an integer in [low, high]; "cell" a [row, column] pair of the material table (row 0 is the \
header row and column 0 the row labels, so data cells start at [1, 1]); "cells" a list of such pairs whose length is \
in "count"; "ints" a list of integers in [low, high]; "edits" a list of entries whose length is in "count": OfficeQA \
perturbations {"cell": [row, column] of a chosen cell, "percent": an integer in [low, high], not 0}; SpreadsheetBench \
edits {"cell": "B3", "formula": "=SUM(C3:D3)", optionally "sheet"} that replace a numeric literal cell of the source \
workbook by a formula over other cells calling only researched functions. A parameter marked optional may be left \
out. ALFWorld has no families: write selection filters {"selection": {"task_kinds": [kinds among heat, cool, clean, \
two, look, place], "min_receptacles": 0-40, "min_openable": 0-20, "target": "receptacles" or "openable", "finding": \
the id of a selection material}}.

Reply with only a JSON object {"specs": [{"family": name, "material": material id, "params": [parameter sets]}]}; on \
SpreadsheetBench each spec also has "source": a source key; on ALFWorld {"specs": [{"selection": filter}]}. \
{"specs": []} writes none. When the user message has "band", the parent solved the previous set at that pass rate, \
outside the registered band of 20% to 80%: write specs for a harder set ("too_easy") or an easier one ("too_hard"). \
When it has "unparseable", your previous reply could not be read: reply again in this format."""
PROMPT_SHA256 = {"policy": digest(POLICY_SYSTEM), "detectors": digest(DETECTOR_SYSTEM),
                 "generators": digest(GENERATOR_SYSTEM)}
# v2 (owner decision 2026-10-23 13:3x; spec-v2): the generated sets are practice items of the engineer's training
# rounds and are probed only with BAND_PROBE_ITEMS items, so the v2 policy asks for every research request, the v2
# generator writes specs for every shown material, and a top-up call ("topup") follows while a set is short. v1's
# prompts and hashes are unchanged.
POLICY_SYSTEM_V2 = POLICY_SYSTEM + """

Training mode: the tasks are practice items for the engineer's training rounds, and a set is probed and admitted only \
when at least 30 tasks survive the truth check. Each found material yields at most 10 tasks, and half of the findings \
are kept apart for the acceptance check. So use all 24 requests, at least 16 of them family_material requests spread \
over the families you choose, each for a distinct concept likely to be found."""
GENERATOR_SYSTEM_V2 = GENERATOR_SYSTEM + """

Training mode: the set must hold at least 30 tasks after the truth check. Write one spec for every shown material of \
a family's kind, each with up to 10 parameter sets. When the user message has "topup", the set built so far is short: \
"topup" gives the tasks it holds, the tasks still needed and, per finding, the tasks already made from it (at most 10 \
per finding in all); write further specs, on materials with room left, that add the missing tasks."""
PROMPT_V2_SHA256 = {"policy": digest(POLICY_SYSTEM_V2), "generators": digest(GENERATOR_SYSTEM_V2)}


class Unparseable(ValueError):
    """A detector reply without exactly one manifest, or whose code blocks do not match it."""


def _refuse_forbidden(value):
    """ValueError when a key of ``FORBIDDEN_KEYS`` appears anywhere in ``value`` (a payload)."""
    if isinstance(value, dict):
        hit = sorted(FORBIDDEN_KEYS & set(value))
        require(not hit, "An examiner payload never carries a reference or verdict field: %s" % hit)
        for entry in value.values():
            _refuse_forbidden(entry)
    elif isinstance(value, (list, tuple)):
        for entry in value:
            _refuse_forbidden(entry)


def _aggregate(value):
    """Aggregated counts only (isolation review 21): numbers, or mappings of short names -- never an item or cell key
    (no "/", no "gen:" prefix) -- to aggregated counts."""
    if value is None or type(value) in (bool, int, float):
        return True
    return isinstance(value, dict) and all(
        type(k) is str and 0 < len(k) <= MAX_COUNT_KEY and "/" not in k and not k.startswith("gen:") and _aggregate(v)
        for k, v in value.items())


def _generating(bench):
    require(bench in BENCHES and bench != "searchqa", "SearchQA neither generates nor researches for generation (§7.2)")


def _attempted(roles, prefix):
    return {"calls": roles.count(prefix), "request_sha256": [c["request_sha256"] for c in roles.calls
                                                             if c["label"].startswith(prefix)]}


# ------------------------------------------------------------------------------------------------------ detectors
def detector_payload(halves, *, bench, library=(), workers=None):
    """The user message of the detector call (module docstring 1): ``halves`` is ``detectors.split``'s record; only
    its write half is read. ``library``: the bench's accepted ``Detector`` objects, run on the write-half views
    through ``workers`` (the ``detectors.evaluate`` factory). Fitted to ``ROLE_INPUT_BYTES`` (residual cells first,
    each group in the seeded order of the split's tag)."""
    found = detectors.examiner_diagnosis(halves, bench=bench)
    library = list(library)
    require(all(isinstance(d, detectors.Detector) and d.bench == bench for d in library),
            "The bench's accepted detectors")
    require(not library or workers is not None, "Accepted detectors run in the sandbox: give the worker factory")
    views = {}
    for trajectory in halves["write"]:
        view = masked_view(trajectory, bench=bench, purpose="examiner")
        if not isinstance(view, Excluded):
            views[trajectory["cell"]] = view
    plain = {cell: {k: v for k, v in view.items() if k != "passed"} for cell, view in views.items()}
    fired = detectors.evaluate(library, plain, workers) if library and plain else {}
    entries = []
    for cell, view in views.items():
        categories = detectors.mechanical_masked(plain[cell], bench=bench)
        covered = sorted(d for d, out in fired.items() if cell in out["fired"])
        # "task_id" (the cell id, never shown) is the key data.ranked orders by
        entries.append({"task_id": cell, "residual": not categories and not covered, "passed": view["passed"],
                        "categories": categories, "covered_by": covered, "view": plain[cell]})
    tag = halves["tag"] + ":examiner-shown"
    ordered = [e for group in (True, False) for e in ranked([e for e in entries if e["residual"] is group], SEED, tag)]
    user = {"request": "detectors", "bench": bench, "view": detectors.VIEWS[bench], "half": "write",
            "max_detectors": DETECTORS_PER_STEP,
            "counts": {key: found[key] for key in ("cells", "failed", "categories", "excluded")},
            "library": [{"id": d.id, "description": d.description} for d in library],
            "trajectories": [{k: e[k] for k in ("residual", "passed", "categories", "covered_by", "view")}
                             for e in ordered]}
    _refuse_forbidden(user)
    return fit(user, "trajectories", ROLE_INPUT_BYTES)


def parse_detectors(reply):
    """[(description, source)] of a detector reply; raises ``Unparseable``."""
    if type(reply) is not str:
        raise Unparseable("no_reply")
    blocks = BLOCK.findall(reply)
    manifests = [body for lang, body in blocks if lang.lower() == "json"]
    sources = [body for lang, body in blocks if lang.lower() in ("python", "py")]
    if len(manifests) != 1:
        raise Unparseable("manifest_blocks:%d" % len(manifests))
    try:
        manifest = json.loads(manifests[0])
    except ValueError:
        raise Unparseable("manifest_json") from None
    entries = manifest.get("detectors") if isinstance(manifest, dict) and set(manifest) == {"detectors"} else None
    if (type(entries) is not list or len(entries) > DETECTORS_PER_STEP
            or not all(isinstance(e, dict) and set(e) == {"description"} for e in entries)):
        raise Unparseable("manifest_shape")
    if len(sources) != len(entries):
        raise Unparseable("code_blocks")
    return [(entry["description"], source) for entry, source in zip(entries, sources)]


def _detector_id(bench, k, n, evidence, taken):
    prefix = "fx" if evidence == FIXTURE else "d"
    while "%s-%s-%d-%d" % (prefix, bench, k, n) in taken:
        n += 1
    taken.add("%s-%s-%d-%d" % (prefix, bench, k, n))
    return "%s-%s-%d-%d" % (prefix, bench, k, n)


def detector_write(roles, payload, *, k, label, evidence):
    """``(candidates, the sealed fivebench-execskill-v1-examiner-detectors record)``: the examiner's detector call(s)
    on ``payload`` (``detector_payload``) and the parsed candidates (module docstring 1). ``k``: the step number in
    detector ids; ``label``: the unit's label. An unparseable reply gets one more call; two give no candidate."""
    require(isinstance(payload, dict) and payload.get("request") == "detectors" and payload.get("bench") in BENCHES,
            "A detector payload")
    require(type(k) is int and 0 <= k <= 999, "A step number of at most three digits")
    _refuse_forbidden(payload)
    bench, prefix = payload["bench"], "%s/%s/detectors/" % (ROLE, label)
    user, attempts, written = payload, [], []
    for purpose in ("write", "rewrite"):
        if roles.count(prefix) >= DETECTOR_CALLS:
            break
        reply = roles.plain(ROLE, DETECTOR_SYSTEM, json.dumps(user, ensure_ascii=False, sort_keys=True),
                            label=prefix + purpose)
        try:
            written = parse_detectors(reply)
        except Unparseable as error:
            attempts.append({"parsed": False, "reason": str(error)})
            user = {**payload, "unparseable": str(error)}  # the second call says why the first was not read
            continue
        attempts.append({"parsed": True, "detectors": len(written)})
        break
    taken = {entry["id"] for entry in payload["library"]}
    candidates, rows = [], []
    for n, (description, source) in enumerate(written, 1):
        detector_id = _detector_id(bench, k, n, evidence, taken)
        try:
            candidates.append(detectors.Detector(id=detector_id, bench=bench, source=source, description=description))
            rows.append({"n": n, "id": detector_id, "kept": True, "reason": None})
        except (ValueError, SyntaxError) as error:  # policy, missing detect(view), description; never a stop
            rows.append({"n": n, "id": detector_id, "kept": False, "reason": str(error)[:200]})
    sealed = record("examiner-detectors", evidence, {
        "bench": bench, "k": k, "label": label, "prompt_sha256": PROMPT_SHA256["detectors"],
        "payload_sha256": digest(payload), "attempts": attempts, "written": rows,
        "candidates_sha256": detectors.candidates_sha256(candidates) if candidates else None,
        **_attempted(roles, prefix)})
    return candidates, sealed


# --------------------------------------------------------------------------------------------- generation policy
def catalogue(bench):
    """The registered families of ``bench`` as the examiner sees them (``generators.FAMILIES``)."""
    return [{"name": family.name, "material": family.material, "template": family.reference,
             "concept": family.concept,
             "params": {name: {"kind": p.kind, "low": p.low, "high": p.high, "count": list(p.count),
                               "optional": p.optional} for name, p in sorted(family.params.items())}}
            for _, family in sorted(generators.FAMILIES[bench].items())]


def choosable(family):
    """The parameters of ``family`` a ``parameter_choice`` request may name (``_request``: the integer kinds)."""
    return [name for name, parameter in sorted(family.params.items()) if parameter.kind in CHOOSABLE_KINDS]


def request_kinds(bench):
    """The request kinds a policy reply may hold on ``bench``, as ``_request`` validates them: ALFWorld
    ``selection_hint`` only; elsewhere ``family_material``, and ``parameter_choice`` while a family has a parameter
    it may name (none on SpreadsheetBench)."""
    if bench == "alfworld":
        return ["selection_hint"]
    families = generators.FAMILIES[bench].values()
    return ["family_material"] + (["parameter_choice"] if any(choosable(f) for f in families) else [])


def outcome_counts(gate_records, *, research=(), generator_records=()):
    """The previous step's outcomes as the next policy call sees them (isolation review 21), counts only: research
    requests by kind and status (``research_requests``' pairs); over the sealed generator-gates records the sets and
    admitted sets, failed gates ("no_items" for the truth gate), items made and kept, drops by reason, band outcomes
    and per family the spec statuses; the sealed generator records by status (predictive validity included). Never
    an item id or a probe verdict."""
    requested = {}
    for request, found in research:
        requested.setdefault(request["kind"], Counter())[found["status"]] += 1
    statuses = Counter(verified(found, "generator")["status"] for found in generator_records)
    sets = admitted = made = kept = 0
    failed, dropped, banded, families = Counter(), Counter(), Counter(), {}
    for gated in gate_records:
        gated = verified(gated, "generator-gates")
        sets += 1
        admitted += gated["admitted"]
        failed.update("no_items" if name == "truth" else name for name in gated["failed"])
        made += gated["truth"]["made"]
        kept += gated["truth"]["kept"]
        dropped.update(gated["truth"]["dropped"])
        band_gate = gated["band"]
        banded["in_band" if band_gate["in_band"] else band_gate.get("direction") or (
            INSUFFICIENT if band_gate.get("reason") == INSUFFICIENT else "not_run")] += 1
        for spec in gated["specs"]:
            families.setdefault(spec["family"], Counter())[spec["status"]] += 1
    return {"sets": sets, "admitted": admitted, "failed": dict(sorted(failed.items())),
            "items": {"made": made, "kept": kept}, "dropped": dict(sorted(dropped.items())),
            "band": dict(sorted(banded.items())),
            "families": {name: dict(sorted(found.items())) for name, found in sorted(families.items())},
            "research": {kind: dict(sorted(found.items())) for kind, found in sorted(requested.items())},
            "generators": dict(sorted(statuses.items()))}


def policy_payload(bench, *, previous=None, outcomes=None):
    """The user message of the policy call: the catalogue, each family with the parameter names a
    ``parameter_choice`` request may name (``choosable``), the bench's valid request kinds (``request_kinds``), the
    previous policy (``policy_revise``'s value) and the previous outcomes as aggregated counts only
    (``outcome_counts``). The kinds and names state what ``_policy`` validates, so the registered rule (one invalid
    request voids the reply) is not hidden from the model (registrar addendum 2026-10-22 15:5x R4)."""
    _generating(bench)
    require(previous is None or (isinstance(previous, dict) and previous.get("bench") == bench),
            "The bench's previous policy")
    require(_aggregate(outcomes), "Previous outcomes as aggregated counts only (isolation review 21)")
    registered = generators.FAMILIES[bench]
    families = [{**entry, "parameter_choice_names": choosable(registered[entry["name"]])} for entry in catalogue(bench)]
    user = {"request": "policy", "bench": bench, "families": families, "request_kinds": request_kinds(bench),
            "previous": previous, "outcomes": outcomes, "max_requests": MAX_RESEARCH_REQUESTS}
    _refuse_forbidden(user)
    return user


def _topic(value):
    return None if value is None else text(value, limit=MAX_CONCEPT_CHARS).strip()


def _request(entry, bench, names):
    """One validated research request of a policy reply (``Invalid`` otherwise)."""
    kind = entry.get("kind") if isinstance(entry, dict) else None
    if kind == "selection_hint" and bench == "alfworld":
        fields(entry, ["kind", "question"], ["topic"])
        return {"kind": kind, "question": text(entry["question"], limit=MAX_QUESTION_CHARS).strip(),
                "topic": _topic(entry.get("topic"))}
    if kind not in ("family_material", "parameter_choice") or bench == "alfworld":
        raise Invalid("request_kind")
    fields(entry, ["kind", "family", "concept"] if kind == "family_material" else
           ["kind", "family", "question", "names"], ["topic"])
    if type(entry["family"]) is not str or entry["family"] not in names:
        raise Invalid("request_family")
    family = generators.FAMILIES[bench][entry["family"]]
    if kind == "family_material":
        concept = text(entry["concept"], limit=MAX_CONCEPT_CHARS).strip()
        if family.material == "function" and FUNCTION.fullmatch(concept) is None:
            raise Invalid("function_name")
        return {"kind": kind, "family": family.name, "concept": concept, "topic": _topic(entry.get("topic"))}
    chosen = items(entry["names"], limit=MAX_PARAMETERS, low=1)
    if (len(set(map(str, chosen))) != len(chosen) or not all(
            type(n) is str and n in family.params and family.params[n].kind in CHOOSABLE_KINDS for n in chosen)):
        raise Invalid("parameter_names")
    return {"kind": kind, "family": family.name, "question": text(entry["question"], limit=MAX_QUESTION_CHARS).strip(),
            "names": list(chosen), "topic": _topic(entry.get("topic"))}


def _policy(value, bench):
    fields(value, ["families", "requests", "rationale"])
    text(value["rationale"], limit=MAX_RATIONALE, empty=True)
    registered = generators.FAMILIES[bench]
    names = items(value["families"], limit=len(registered))
    if not all(type(n) is str and n in registered for n in names) or len(set(names)) != len(names):
        raise Invalid("families")
    requests = [_request(entry, bench, names) for entry in items(value["requests"], limit=MAX_RESEARCH_REQUESTS)]
    return {"bench": bench, "families": list(names), "requests": requests, "rationale": value["rationale"]}


def policy_revise(roles, payload, *, label, evidence, train=False):
    """``(policy, the sealed fivebench-execskill-v1-examiner-policy record)``: the examiner's generation policy for the
    step's research (module docstring 2). An invalid reply keeps the previous policy (``fallback`` "previous"), or an
    empty one ("empty"). The policy and its counts are a process record, never effect evidence (§7.2). ``train``
    (v2): under ``POLICY_SYSTEM_V2``."""
    require(isinstance(payload, dict) and payload.get("request") == "policy", "A policy payload")
    _refuse_forbidden(payload)
    bench, prefix = payload["bench"], "%s/%s/policy" % (ROLE, label)
    _generating(bench)
    value = None
    if roles.count(prefix) < POLICY_CALLS:
        value = roles.ask(ROLE, POLICY_SYSTEM_V2 if train else POLICY_SYSTEM, payload, label=prefix,
                          check=lambda reply: _policy(reply, bench))
    fallback = None
    if value is None:
        fallback = "previous" if payload["previous"] is not None else "empty"
        value = payload["previous"] or {"bench": bench, "families": [], "requests": [], "rationale": ""}
    sealed = record("examiner-policy", evidence, {
        "bench": bench, "label": label, "prompt_sha256": (PROMPT_V2_SHA256 if train else PROMPT_SHA256)["policy"],
        "payload_sha256": digest(payload), "policy": value, "fallback": fallback, **_attempted(roles, prefix)})
    return value, sealed


def research_requests(policy, researcher):
    """[(request, research record)]: the policy's requests sent in order through ``researcher`` (a
    ``research.Researcher`` of the policy's bench), whose pre-dispatch leakage screen and 24-request ceiling apply; a
    refused request's record says why (status "not_dispatched")."""
    require(isinstance(policy, dict) and policy.get("bench") == researcher.bench, "A policy of the researcher's bench")
    out = []
    for request in policy["requests"]:
        if request["kind"] == "family_material":
            found = researcher.family_material(concept=request["concept"], topic=request["topic"])
        elif request["kind"] == "parameter_choice":
            found = researcher.parameter_choice(question=request["question"], names=request["names"],
                                                topic=request["topic"])
        else:
            found = researcher.selection_hint(question=request["question"], topic=request["topic"])
        out.append((request, found))
    return out


# ------------------------------------------------------------------------------------------------ generator specs
def usable(bench, materials):
    """{material id: material} of one research half (``research.material`` values) that ``bench``'s families
    consume: OfficeQA tables, LiveMath definitions, ALFWorld selection findings, SpreadsheetBench the one function set
    of all function findings (``sheet.function_set``)."""
    _generating(bench)
    if bench == "spreadsheetbench":
        functions = [m for m in materials if m.get("kind") == "function"]
        found = sheet.function_set(functions) if functions else None
        return {found["id"]: found} if found else {}
    return {m["id"]: m for m in materials if m.get("kind") == USABLE[bench]}


def _shown(material):
    kind, out = material["kind"], {"id": material["id"], "kind": material["kind"]}
    if kind == "table":
        return {**out, "caption": material["caption"], "rows": material["rows"], "source": material["source"]}
    if kind == "definition":
        return {**out, "quote": material["quote"], "source": material["source"]}
    if kind == "functions":
        return {**out, "functions": {name: {"conclusion": f["conclusion"], "quotes": [q["text"] for q in f["quotes"]]}
                                     for name, f in sorted(material["functions"].items())}}
    return {**out, "conclusion": material["conclusion"]}


def researched_values(bench, materials):
    """[{"finding", "name", "value", "families"}]: the researched parameter values that lie inside a registered range
    of one of ``bench``'s families (§7.2 parameter_choice: other values are dropped)."""
    out = []
    for material in materials:
        if material.get("kind") != "parameter":
            continue
        for entry in material["values"]:
            value = number_value(entry["value"])
            families = sorted(name for name, family in generators.FAMILIES[bench].items()
                              if value is not None and family.in_range(entry["name"], value))
            if families:
                out.append({"finding": material["id"], "name": entry["name"], "value": int(value),
                            "families": families})
    return out


def generator_payload(bench, materials, *, sources=None, band=None, topup=None):
    """The user message of the generator call (module docstring 2): ``materials`` = the ``research.material`` values
    of one research half; ``sources`` (SpreadsheetBench only) = {key: the public view of a source task} -- public
    content only; ``band`` = the previous probe's ``band`` value when this call adjusts the parameters (at most twice
    after an out-of-band probe); ``topup`` (v2) = ``topup``'s hint when this call adds items to a short set."""
    _generating(bench)
    require(sources is None or (bench == "spreadsheetbench" and isinstance(sources, dict)),
            "Only SpreadsheetBench specs edit source tasks")
    hint = None
    if band is not None:
        require(not band["in_band"] and band["adjustments"] < BAND_ROUNDS - 1,
                "A parameter adjustment follows an out-of-band probe, at most twice")
        hint = {"pass_rate": band["pass_rate"], "direction": band["direction"], "adjustment": band["adjustments"] + 1}
    user = {"request": "generators", "bench": bench, "families": catalogue(bench),
            "materials": [_shown(m) for _, m in sorted(usable(bench, materials).items())],
            "parameters": researched_values(bench, materials),
            "sources": [{"key": key, "view": view} for key, view in sorted((sources or {}).items())],
            "max_parameter_sets": MAX_ITEMS_PER_FINDING, "band": hint}
    if topup is not None:
        require(isinstance(topup, dict) and band is None, "A top-up hint, never with a band adjustment")
        user["topup"] = topup
    _refuse_forbidden(user)
    return fit(user, "sources", ROLE_INPUT_BYTES)


def _answer_like(value):
    if isinstance(value, dict):
        return bool(ANSWER_KEYS & set(value)) or any(_answer_like(v) for v in value.values())
    if isinstance(value, list):
        return any(_answer_like(v) for v in value)
    return False


def _spec(entry, payload):
    """(the spec, None), or (None, why it is dropped). The family's fixed code checks each parameter set again."""
    bench = payload["bench"]
    if not isinstance(entry, dict):
        return None, "not_an_object"
    if _answer_like(entry):
        return None, "answer_field"
    shown = {m["id"]: m for m in payload["materials"]}
    if bench == "alfworld":
        if set(entry) != {"selection"} or not isinstance(entry["selection"], dict):
            return None, "keys"
        try:
            alfworld_select.check_spec(entry["selection"], list(shown.values()))
        except Drop as drop:
            return None, drop.reason
        except TypeError:  # an unhashable value where the filter has names
            return None, "format"
        return {"selection": dict(entry["selection"])}, None
    required = {"family", "material", "params"} | ({"source"} if bench == "spreadsheetbench" else set())
    if set(entry) != required:
        return None, "keys"
    family = generators.FAMILIES[bench].get(entry["family"]) if type(entry["family"]) is str else None
    if family is None:
        return None, "unknown_family"
    material = shown.get(entry["material"]) if type(entry["material"]) is str else None
    if material is None or material["kind"] != generators.MATERIAL_KINDS[family.material]:
        return None, "material_not_shown"
    if bench == "spreadsheetbench" and (type(entry["source"]) is not str
                                        or entry["source"] not in {source["key"] for source in payload["sources"]}):
        return None, "source_not_shown"
    if type(entry["params"]) is not list or not 1 <= len(entry["params"]) <= MAX_ITEMS_PER_FINDING:
        return None, "params"
    return {key: entry[key] for key in sorted(required)}, None


def _specs_shape(value):
    fields(value, ["specs"])
    return items(value["specs"], limit=MAX_SPECS)


def generator_write(roles, payload, *, label, evidence, train=False):
    """``(specs, the sealed fivebench-execskill-v1-examiner-generators record)``: the examiner's generator call(s) on
    ``payload`` (``generator_payload``) and the specs that name a registered family, a shown material (and source)
    and 1 to 10 parameter sets, without an answer-like key (module docstring 2). An invalid reply gets one more call;
    two give no spec. ``train`` (v2): under ``GENERATOR_SYSTEM_V2``."""
    require(isinstance(payload, dict) and payload.get("request") == "generators", "A generator payload")
    _refuse_forbidden(payload)
    bench, prefix = payload["bench"], "%s/%s/generators/" % (ROLE, label)
    _generating(bench)
    user, attempts, entries = payload, [], []
    for purpose in ("write", "rewrite"):
        if roles.count(prefix) >= GENERATOR_CALLS:
            break
        value = roles.ask(ROLE, GENERATOR_SYSTEM_V2 if train else GENERATOR_SYSTEM, user, label=prefix + purpose,
                          check=_specs_shape)
        if value is None:
            reason = roles.calls[-1]["reason"]
            attempts.append({"parsed": False, "reason": reason})
            user = {**payload, "unparseable": reason}
            continue
        attempts.append({"parsed": True, "specs": len(value)})
        entries = value
        break
    specs, dropped = [], []
    for n, entry in enumerate(entries, 1):
        spec, reason = _spec(entry, payload)
        if spec is None:
            dropped.append({"n": n, "reason": reason})
        else:
            specs.append({"n": n, **spec})
    sealed = record("examiner-generators", evidence, {
        "bench": bench, "label": label, "prompt_sha256": (PROMPT_V2_SHA256 if train else PROMPT_SHA256)["generators"],
        "payload_sha256": digest(payload), "attempts": attempts, "specs": specs, "dropped": dropped,
        "specs_sha256": digest(specs), **_attempted(roles, prefix)})
    return specs, sealed


@dataclass(frozen=True)
class Generated:
    """A generated set: the generator's id, its bench, one ``generators.generate`` result per spec (each with its
    ``family`` and ``material``) and ``next_number``, the first item number it left unused: a later set of the same
    generator is numbered from there, so no item id names two items (ticket C4-1). ``derived``: {finding id: items
    kept from it} over this build and the builds of the attempt it continues (Codex finding #10)."""
    generator: str
    bench: str
    results: tuple
    next_number: int = 0
    derived: dict = field(default_factory=dict, hash=False)

    @property
    def items(self):
        return [item for result in self.results for item in result["items"]]


def _findings(item, material):
    """The findings a generated item draws on: its material, or (SpreadsheetBench) each researched function its edits
    call."""
    if material["kind"] != "functions":
        return [material["id"]]
    names = {name for edit in item["private"]["truth"]["edits"] for name in sheet.functions(edit["formula"])}
    return sorted(material["functions"][name]["id"] for name in names if name in material["functions"])


def build(specs, materials, *, bench, generator, set_name, seed, evidence, start=0, derived=None, sources=None,
          checker=None, engine=None, out_dir=None):
    """The ``Generated`` set of ``specs`` (``generator_write``) on the research half ``materials``: each spec through
    ``generators.generate`` (truth by the family's fixed reference function), items numbered across specs from
    ``start`` (the ``next_number`` of the generator's previous set, ticket C4-1); an item
    beyond ``MAX_ITEMS_PER_FINDING`` of one finding is dropped (``finding_exhausted``), counted across specs and from
    ``derived`` (the ``Generated.derived`` of the attempt's previous build of this set: a band adjustment rebuilds
    from the same findings, Codex finding #10). ``sources``: {key: source item} (SpreadsheetBench); ``checker``
    (LiveMath), ``engine`` and ``out_dir`` (SpreadsheetBench): the fixed engines of ``generators.generate``."""
    require(generators.mode(bench) == "families", "Only a bench with families builds items")
    require(derived is None or (isinstance(derived, dict) and all(
        type(n) is int and 0 <= n <= MAX_ITEMS_PER_FINDING for n in derived.values())), "A finding-keyed counter")
    found = usable(bench, materials)
    results, count, used = [], start, Counter(derived or {})
    for spec in specs:
        material = found[spec["material"]]
        params = list(spec["params"])
        source = [sources[spec["source"]]] * len(params) if bench == "spreadsheetbench" else None
        made = generators.generate(generators.family(spec["family"]), params, material, generator=generator,
                                   set_name=set_name, seed=seed, evidence=evidence, start=count, source_items=source,
                                   checker=checker, engine=engine, out_dir=out_dir)
        count += len(made["items"])
        kept, dropped = [], Counter(made["dropped"])
        for item in made["items"]:
            findings = _findings(item, material)
            if any(used[finding] >= MAX_ITEMS_PER_FINDING for finding in findings):
                dropped["finding_exhausted"] += 1
                continue
            used.update(findings)
            kept.append(item)
        status = made["status"] if kept or made["status"] == "no_material" else "none_kept"
        results.append({**made, "items": kept, "dropped": dict(sorted(dropped.items())), "status": status,
                        "family": spec["family"], "material": spec["material"]})
    return Generated(generator, bench, tuple(results), count, dict(sorted(used.items())))


def joined(first, more):
    """v2's top-up: the set ``first`` with the items of ``more``, a later build of the same generator and set that
    was numbered from ``first.next_number`` and continued its per-finding counter (``derived``)."""
    require(first.generator == more.generator and first.bench == more.bench
            and more.next_number >= first.next_number
            and all(more.derived.get(finding, 0) >= n for finding, n in first.derived.items()),
            "A top-up continues its set's numbering and per-finding counter")
    return Generated(first.generator, first.bench, first.results + more.results, more.next_number, dict(more.derived))


def topup(generated, call):
    """v2: the "topup" hint of a set's ``call``-th top-up call: the items it holds, the items still needed for its
    band probe and the items made per finding so far (at most ``MAX_ITEMS_PER_FINDING`` each)."""
    return {"call": call, "items": len(generated.items),
            "needed": max(0, BAND_PROBE_ITEMS - len(generated.items)), "per_finding": dict(generated.derived)}


def sufficient(generated):
    """Whether a generated set holds the ``BAND_PROBE_ITEMS`` qualified items its band probe needs (§7.2: the parent's
    accuracy on 30 probe items; Codex finding #9): with fewer, no probe is run and the band gate records
    ``insufficient_material``."""
    return len(generated.items) >= BAND_PROBE_ITEMS


# ---------------------------------------------------------------------------------------------------------- gates
def probe_items(generated, *, generator, purpose):
    """The probe items of a set: the first ``BAND_PROBE_ITEMS`` (band) or ``SHORTCUT_PROBE_ITEMS`` (shortcut) items in
    the seeded order of ``execskill-v1:examiner-probe:<generator>:<purpose>``."""
    require(purpose in ("band", "shortcut"), "A band or a shortcut probe")
    size = BAND_PROBE_ITEMS if purpose == "band" else SHORTCUT_PROBE_ITEMS
    return ranked(list(generated), SEED, "%s:%s:%s" % (PROBE_TAG, generator, purpose))[:size]


def shortcut_public(bench, public):
    """The public fields of a shortcut-probe variant (``shortcut_variant``): OfficeQA without its table (the question
    only), LiveMath without its stem (the options only), plain public-field blanks; SpreadsheetBench unchanged. Also
    the view of LiveMath's J7 options-only probe cells (§6.4; registrar addendum 2026-10-22 17:0x; ``step``)."""
    require(bench in SHORTCUT_PROBES, "A shortcut probe of a bench with families")
    blanks = {"officeqa": {"context": ""}, "livemath": {"question": ""}}.get(bench, {})
    return {**public, **blanks}


def shortcut_variant(item):
    """The shortcut-probe variant of a generated item (§7.2), resealed with ``set`` "shortcut", ``probe`` and
    ``variant_of``: OfficeQA without its table (the question only) and LiveMath without its stem (the options only),
    plain public-field blanks (``shortcut_public``); SpreadsheetBench with its public fields unchanged, so the program
    still runs on the real input workbook, solved in the shell's no-workbook mode (``probe_mode``), whose request
    carries neither the preview nor any other sheet content (registrar decision 2026-10-22, ticket C1-2)."""
    item = verified(item, "generated-item")
    bench = item["benchmark"]
    public = shortcut_public(bench, item["public"])
    kept = {k: v for k, v in item.items() if k not in ("version", "evidence", "record_sha256")}
    return record("generated-item", item["evidence"], {**kept, "public": public, "set": "shortcut",
                                                       "probe": SHORTCUT_PROBES[bench],
                                                       "variant_of": item["record_sha256"]})


def probe_mode(variant):
    """The shell mode a shortcut-probe variant is solved in, i.e. its probe cell's ``shortcut`` key, which
    ``cells.run_cell`` hands to ``solver.solve``: ``NO_WORKBOOK`` on SpreadsheetBench, None on OfficeQA and LiveMath
    (``SHORTCUT_MODES``)."""
    variant = verified(variant, "generated-item")
    require(variant["set"] == "shortcut" and variant.get("probe") == SHORTCUT_PROBES.get(variant["benchmark"])
            and type(variant.get("variant_of")) is str, "A shortcut-probe variant (shortcut_variant)")
    return SHORTCUT_MODES.get(variant["benchmark"])


def _probed(cell):
    """(item, run, token) of a sealed probe cell record: its scorer-v2 token, the precedence the self-test and the
    acceptance count by (``judge.v2.token``; registrar addendum 2026-10-22 15:5x R6 (b)); a cell stopped before its
    verdict (no judge) counts as unknown."""
    value = verified(cell, "cell")
    judged = value.get("judge")
    token = judged["v2"]["token"] if isinstance(judged, dict) else "unknown"
    return value["cell"]["task_id"], value["cell"]["run"], token


def truth(results):
    """The truth gate of a set's ``generators.generate`` results: parameter sets tried, items kept, drops by reason
    (counts across the set only), specs without material and the separate engine qualification."""
    dropped, engine = Counter(), 0
    for result in results:
        dropped.update(result["dropped"])
        engine += sum(1 for item in result["items"] if item["private"].get("engine_qualification") is not None)
    failed = dropped["engine_qualification_failed"]
    return {"made": sum(result["made"] for result in results), "kept": sum(len(r["items"]) for r in results),
            "dropped": dict(sorted(dropped.items())),
            "no_material": sum(1 for result in results if result["status"] == "no_material"),
            "engine_qualification": {"checked": engine + failed, "failed": failed}}


def band(rounds, item_ids):
    """The difficulty band (§7.2): ``rounds`` holds the parent's sealed probe cells of each band probe in order (one
    run per item, at most ``BAND_PROBE_ITEMS`` items); at most ``BAND_ROUNDS`` probes, i.e. the first and two
    parameter adjustments. The LAST probe decides, on items of the final set (``item_ids``); an unknown token counts
    as not passed. ``direction``: "too_easy" above the band, "too_hard" below it. A probe of fewer than
    ``BAND_PROBE_ITEMS`` items is never in the band and has no direction: the deciding one makes the gate
    ``insufficient_material`` (§7.2: 30 probe items; Codex finding #9)."""
    rounds = [list(cells) for cells in rounds]
    require(1 <= len(rounds) <= BAND_ROUNDS, "One to three band probes (at most two parameter adjustments)")
    rows, last = [], None
    for cells in rounds:
        tokens = {}
        for cell in cells:
            item, _, token = _probed(cell)
            require(item not in tokens, "One run per band-probe item")
            tokens[item] = token
        require(0 < len(tokens) <= BAND_PROBE_ITEMS, "A band probe of 1 to %d items" % BAND_PROBE_ITEMS)
        rate, full = Fraction(sum(t == PASS for t in tokens.values()), len(tokens)), len(tokens) == BAND_PROBE_ITEMS
        rows.append({"probe_items": len(tokens), "passed": sum(t == PASS for t in tokens.values()),
                     "unknown": sum(t in UNKNOWN_TOKENS for t in tokens.values()), "pass_rate": float(rate),
                     "in_band": full and BAND[0] <= rate <= BAND[1],
                     "direction": None if not full else "too_easy" if rate > BAND[1] else "too_hard"
                     if rate < BAND[0] else None})
        last = tokens
    require(set(last) <= set(item_ids), "The deciding band probe ran on items of the final set")
    final = rows[-1]
    return {"probe_items": final["probe_items"], "pass_rate": final["pass_rate"], "adjustments": len(rows) - 1,
            "in_band": final["in_band"], "direction": final["direction"],
            "reason": None if final["probe_items"] == BAND_PROBE_ITEMS else INSUFFICIENT, "rounds": rows}


def _mode(cell):
    """The shell mode a sealed probe cell ran in as its record states it: the top-level ``shortcut`` that
    ``cells.run_cell`` takes from the shell's own record on a cell that asked for a mode; None without one."""
    return verified(cell, "cell").get("shortcut")


def shortcut(cells, item_ids, *, bench):
    """The shortcut gate (§7.2): ``cells`` = the card arm's sealed cells on the probe variants (``SHORTCUT_RUNS`` runs
    per item, at most ``SHORTCUT_PROBE_ITEMS`` items of the set), None when the probe did not run (the set is not
    used). Every cell must have run in its bench's mode (``SHORTCUT_MODES``; a SpreadsheetBench cell that saw the
    workbook probes nothing, ticket C1-2). Items right in both runs are dropped; a dropped share above
    ``SHORTCUT_DROP_MAX`` rejects the whole set."""
    probe = SHORTCUT_PROBES[bench]
    if cells is None:
        return {"probe": probe, "probe_items": 0, "dropped": [], "flagged_share": None, "used": False,
                "reason": "not_run"}
    runs = {}
    for cell in cells:
        item, run, token = _probed(cell)
        require(_mode(cell) == SHORTCUT_MODES.get(bench),
                "Every shortcut-probe cell ran in its bench's probe mode (§7.2; SpreadsheetBench without the workbook)")
        require(run not in runs.setdefault(item, {}), "One cell per probe item and run")
        runs[item][run] = token
    require(0 < len(runs) <= SHORTCUT_PROBE_ITEMS and set(runs) <= set(item_ids),
            "A shortcut probe of 1 to 30 items of the set")
    require(all(len(found) == SHORTCUT_RUNS for found in runs.values()), "Two runs per shortcut-probe item")
    dropped = sorted(item for item, found in runs.items() if all(t == PASS for t in found.values()))
    share = Fraction(len(dropped), len(runs))
    used = share <= SHORTCUT_DROP_MAX
    return {"probe": probe, "probe_items": len(runs), "dropped": dropped, "flagged_share": float(share), "used": used,
            "reason": None if used else "dropped_share_above_maximum"}


def labels(generated, *, bench):
    """The labels gate (§7.2): every truth computed by a registrar module's fixed code (the specs carried no answer,
    checked by ``generator_write``); LiveMath answer letters each within ``KEY_SHARE`` +- ``KEY_TOLERANCE``."""
    generated = list(generated)
    fixed = all(TRUTH_BY.get(item["private"]["truth"].get("checked_by")) == item["private"]["truth"].get("kind")
                for item in generated)
    balance, balanced = None, True
    if bench == "livemath" and generated:
        letters = Counter(item["private"]["answer"] for item in generated)
        shares = {letter: Fraction(letters[letter], len(generated)) for letter in LIVEMATH_LABELS}
        balance = {letter: float(share) for letter, share in shares.items()}
        balanced = all(abs(share - KEY_SHARE) <= KEY_TOLERANCE for share in shares.values())
    return {"truth_by_fixed_code": fixed, "key_balance": balance, "ok": bool(generated) and fixed and balanced}


def gates(bundle, probe_cells, *, evidence):
    """The sealed ``fivebench-execskill-v1-generator-gates`` record of a ``Generated`` set (module docstring 3):
    ``probe_cells`` = {"band": [the cells of each band probe], "shortcut": the shortcut probe's cells or None}.
    ``admitted`` when it keeps items and passes the band, the shortcut and the labels; ``kept`` lists the admitted
    items (the set minus the shortcut drops)."""
    require(isinstance(bundle, Generated) and generators.mode(bundle.bench) == "families",
            "A generated set of a bench with families")
    require(isinstance(probe_cells, dict) and set(probe_cells) <= {"band", "shortcut"}, "Band and shortcut cells")
    found = bundle.items
    ids = [item["id"] for item in found]
    not_run = {"in_band": False, "reason": "not_run"}
    if found and not sufficient(bundle):  # §7.2, Codex finding #9: 30 qualified probe items or no admission
        band_gate = {"in_band": False, "reason": INSUFFICIENT, "items": len(found), "required": BAND_PROBE_ITEMS,
                     "probe_items": 0, "pass_rate": None, "direction": None}  # a recorded outcome: no probe ran
    else:
        band_gate = band(probe_cells["band"], ids) if found and probe_cells.get("band") else not_run
    cut = (shortcut(probe_cells.get("shortcut"), ids, bench=bundle.bench) if found
           else shortcut(None, ids, bench=bundle.bench))
    kept = [item for item in found if item["id"] not in set(cut["dropped"])]
    label_gate = labels(kept, bench=bundle.bench)
    passed = {"truth": bool(found), "band": band_gate["in_band"], "shortcut": cut["used"], "labels": label_gate["ok"]}
    admitted = all(passed.values())
    kept_ids = [item["id"] for item in kept] if admitted else []
    return record("generator-gates", evidence, {
        "generator": bundle.generator, "bench": bundle.bench,
        "specs": [{"family": r["family"], "material": r["material"], "status": r["status"]} for r in bundle.results],
        "truth": truth(bundle.results), "band": band_gate, "shortcut": cut, "labels": label_gate,
        "failed": [name for name, ok in passed.items() if not ok], "admitted": admitted, "kept": kept_ids,
        "kept_sha256": digest([item["record_sha256"] for item in kept]) if admitted else None})


def generator_record(gates_record, specs, *, rounds=(), dup=None, evidence):
    """The sealed plan §2.5 ``fivebench-execskill-v1-generator`` record: the frozen specs, the gates and the status --
    "not_admitted", "admitted" before any acceptance round, else ``validity.status`` of the rounds' pairs (§7.2,
    Codex F9: refuted > validated > not_evaluable)."""
    gates_record = verified(gates_record, "generator-gates")
    found = validity.status(list(rounds), dup) if gates_record["admitted"] and rounds else None
    status = found["status"] if found else ("admitted" if gates_record["admitted"] else "not_admitted")
    return record("generator", evidence, {
        "id": gates_record["generator"], "bench": gates_record["bench"], "specs": list(specs),
        "specs_sha256": digest(list(specs)), "gates_sha256": gates_record["record_sha256"],
        "gates": {key: gates_record[key] for key in ("truth", "band", "shortcut", "labels")}, "status": status,
        "rounds": list(rounds), "dup_control": dup, "validity": found})


def g_acc(items, astar, *, bench, generator):
    """``acceptance.prepare``'s ``generate`` value, [{"id", "source_item"}] (§3.3, §7.2): the frozen generator's G_acc
    items (``build`` with set "G_acc" on the g_acc research half; the caller passes only items its gates kept) in the
    seeded order of ``execskill-v1:examiner-probe:<generator>:g_acc``, paired one to one with the A* items in their
    given order, at most ``G_ACC[bench]``. The families draw on researched material, so the A* public views fix the
    size and the pairing only (ticket C1-3)."""
    items = [verified(item, "generated-item") for item in items]
    require(all(item["set"] == "G_acc" and item["benchmark"] == bench and item["id"].startswith("gen:%s:" % generator)
                for item in items), "G_acc items of the bench's frozen generator")
    require(len(set(astar)) == len(astar), "Distinct A* items")
    ordered = ranked(items, SEED, "%s:%s:g_acc" % (PROBE_TAG, generator))
    return [{"id": item["id"], "source_item": source} for item, source in zip(ordered, astar)][:G_ACC[bench]]


def selection(spec, pool_views, materials, *, n, seed_tag, evidence):
    """The sealed ``fivebench-execskill-v1-selection-validity`` record of an ALFWorld selection filter (§7.2):
    ``alfworld_select`` picks at most ``n`` games of ``pool_views`` (zero-call routing views); a seeded null set of the
    same size is the control and ``shift`` their difference on the target feature. Selection validity only: never an
    examiner claim."""
    try:
        checked = alfworld_select.check_spec(spec, list(materials))
    except Drop as drop:
        return record("selection-validity", evidence, {"spec": spec, "status": drop.reason, "selected": [],
                                                       "null": [], "shift": None, "claim": "selection_validity"})
    chosen = alfworld_select.select(checked, pool_views, n=n, seed_tag=seed_tag)
    null = alfworld_select.null_select(pool_views, len(chosen), seed_tag=seed_tag) if chosen else []
    return record("selection-validity", evidence, {
        "spec": checked, "status": "selected" if chosen else "none_selected", "selected": chosen, "null": null,
        "shift": alfworld_select.shift(chosen, null, pool_views, checked["target"]) if chosen else None,
        "claim": "selection_validity"})
