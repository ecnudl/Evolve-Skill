"""The end-to-end zero-API pilot (implementation plan §8.2; registration §5, §6, §7.2, §8.1, §9.3, §21): the default
pilot SpreadsheetBench -> OfficeQA run as the two chains G (solver glm-5.3) and D (solver deepseek-v4.1-flash-1017)
through ``chain.run`` with the real ``step.learn``, then the one multi-arm test read, the owner's continuation file
with the formal-chain addendum, the unseal and the readout. Offline and deterministic; everything is an engineering
fixture, never method-effect evidence:

- each chain's solver is a FakeSolver behind the real client of its model (glm-5.3 / elucid) and the chain's own real
  ledger; the method roles are FakeGLM behind the real ``Roles`` (one per chain, charged to that chain's ledger);
- the cells' procedures are FakeSandbox hooks that compute what the engineer's sources compute; the engineer's checks
  C1-C9, the detectors and the describer's replays run the real sandbox worker through FakeDocker;
- SpreadsheetBench programs run through FakeNative: every pre-check reports the same KeyError, and the frozen scorer is
  replaced by a fixture verdict (a program passes when it writes ``=SUM(A1:A5)``);
- the research sources are FakeResearch, with a second eligible numeric table added for this test, so the OfficeQA
  findings split into a G_self and a G_acc half.

The pilot: step 1 (SpreadsheetBench, empty parent) -- the parent's first program fails on half the workbooks; the
engineer writes one ``sheet_feedback`` procedure that names the workbook's column A and asks for one repair call; the
examiner's policy requests no research there (ticket PR-C12-2). Step 2 (OfficeQA) -- the examiner researches two
tables (G_self and G_acc), its generator is admitted, the engineer proposes three changes (one valid, one crashing,
one leaking a run-slice reference answer) and only the valid one survives; the acceptance runs S', S, P_y, P_i, C,
the withholding twins, G_acc and S_dup. The test read is real on OfficeQA (structural-zero sharing on the test items
without a year column); the other four benches' read units are stand-in records (their test panels need the test
qualification or the ALFWorld environment).

Assertions: both chains complete with the same two accepted procedures, each after its one confirmed first call
(registrar addendum 2026-10-22 14:10, row 7) and chain G's read gate corrected by its cost factor (row 8); every
record is versioned and labelled; chain G and chain D records name their chain, scopes and consumption namespace,
and both chains consume the same slice items without a ConsumptionConflict; the registry states; each ledger's
reservations equal its settlements; no test text in any training-side artifact (canary scan, with a positive
control); every decision again from its stored cell records and sealed record alone; the run root's two canary
records (S0's and the test read's, checked against the pinned training pools) and the unseal's clean run-root
scan (tickets PR-C31-2, P2-A3-2); the unseal and the readout tables.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import io
import itertools
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from skillopt.coevo5.budget import Budget
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (acceptance, budgets, chain, describer, donors, engineer, evaluation, examiner,
                                readout, research, rounds, slots, step, units)
from skillopt.execskill.cells import Arm
from skillopt.execskill.client import GLM_SOLVER
from skillopt.execskill.errors import CleanupUnconfirmed
from skillopt.execskill.package import FIXTURE, empty, load
from skillopt.execskill.protocol import (BENCHES, CANARIES, CHAINS, ELUCID_MAX_TOKENS, ELUCID_READ_TIMEOUT,
                                         FIRST_CALL_USER, NOTES_KEY, ORDER, ledger_bound, record, verified)
from skillopt.execskill.registry import Registry
from skillopt.execskill.sandbox.client import Worker
from skillopt.validator_pilot.api import digest
from tests import execskill_fakes_research as fake_research
from tests.execskill_fakes import FakeGLM, FakeSolver, engineer_reply, tagged
from tests.execskill_fakes_docker import FakeDocker
from tests.execskill_fakes_env import FakeNative, FakeSandbox
from tests.fixtures.execskill.items import officeqa_items, spreadsheetbench_items
from tests.test_execskill_evaluation import consent_value
from tests.test_execskill_examiner import PARAMS
from tests.test_execskill_integration_b3 import CARD, ERROR_REPORT, SHEET_RUNTIME, canonical, key
from tests.test_execskill_integration_b4 import CRASH, DESCRIPTION, new
from tests.test_execskill_replay import TEST_LIMITS, source, test_case

RUN = "fixture-e2e-pilot"
SB, OQ = "spreadsheetbench", "officeqa"
DEEPSEEK = CHAINS["D"]
SHEET_ID, YEARS_ID = "fx-spreadsheetbench-1-1", "fx-officeqa-2-1"  # the engineer's procedures (step, change)
OQ_ITEMS = officeqa_items(120)[40:]  # pages 40-119: run slice 40-63, acceptance slice 64-113
SB_COUNT = 31 + 60  # the registered run (31) and acceptance (60) slices
LEAKED = next(item["private"]["answer"] for item in OQ_ITEMS[:24]
              if item["private"]["answer"].isdigit() and len(item["private"]["answer"]) >= 4
              and not any(item["private"]["answer"] in json.dumps(other["public"]) for other in OQ_ITEMS[:24]))
OWNER_FILES = {"consent.json", "owner-continuation.json"}
SUM_FORMULA = "=SUM(A1:A5)"
RIGHT = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\nbook.active['B1'] = '%s'\n"
         "book.save('output.xlsx')\n```" % SUM_FORMULA)
WRONG = RIGHT.replace("'%s'" % SUM_FORMULA, "0")
DETECTOR = 'def detect(view):\n    return "ratio" in str(view["task"]).lower()\n'
SECOND_TABLE = (  # a second eligible numeric table for the research (G_acc needs a second material)
    "<p>Public finance studies government revenue.</p>"
    "<table><caption>Receipts by year, revised (billions)</caption>"
    "<tr><th>Year</th><th>Income tax</th><th>Customs</th><th>Total</th></tr>"
    "<tr><td>2019</td><td>1,702</td><td>73</td><td>1,775</td></tr>"
    "<tr><td>2020</td><td>1,596</td><td>69</td><td>1,665</td></tr>"
    "<tr><td>2021</td><td>2,032</td><td>84</td><td>2,116</td></tr></table>")
CONCEPTS = ("government revenue table", "public finance table")

# The engineer's sources. They run on every bench's stored trajectories (the chain's earlier benches included), so
# they read their view defensively.
SHEET = """
def applies(view):
    return "workbook_preview" in view or str(view.get("question", "")).startswith("What is the")

def sheet_feedback(view, run_report, state):
    if run_report.get("status") != "exception" or not run_report.get("message"):
        return None
    rows = view["workbook_preview"][0]["preview"]
    column = [str(row[0]) for row in rows if row and row[0] is not None]
    return {"fields": {"warnings": ["Column A holds " + ", ".join(column) + "."]}, "request_repair": True}
"""
YEARS = """
import re

def applies(view):
    return "Year |" in str(view.get("context", ""))

def before_call(view, state):
    rows = re.findall(r"^([0-9]+) [|] ([0-9]+) [|]", str(view.get("context", "")), re.M)
    if not rows:
        return None
    return {"facts": ["Customs receipts by year: " + "; ".join(year + " = " + customs for year, customs in rows)]}
"""
LEAK = """
def applies(view):
    return "Year |" in str(view.get("context", ""))

def before_call(view, state):
    return {"candidates": [LEAKED]}
"""


# ------------------------------------------------------------------------------------------------ the fixtures
def column_a(view):
    """What the SHEET procedure writes for a workbook's request view (the same text as its source)."""
    rows = view["workbook_preview"][0]["preview"]
    return "Column A holds " + ", ".join(str(row[0]) for row in rows if row and row[0] is not None) + "."


def years(context):
    """What the YEARS procedure writes for a table (the same text as its source)."""
    rows = re.findall(r"^([0-9]+) [|] ([0-9]+) [|]", context, re.M)
    return "Customs receipts by year: " + "; ".join(y + " = " + c for y, c in rows) if rows else None


# the cells' procedures (FakeSandbox), computing what the engineer's sources compute
HOOKS = {
    SHEET_ID: {"applies": lambda view: ("workbook_preview" in view
                                        or str(view.get("question", "")).startswith("What is the")),
               "sheet_feedback": lambda view, report, state: (
                   {"fields": {"warnings": [column_a(view)]}, "request_repair": True}
                   if report.get("status") == "exception" and report.get("message") else None)},
    YEARS_ID: {"applies": lambda view: "Year |" in str(view.get("context", "")),
               "before_call": lambda view, state: ({"facts": [years(view["context"])]}
                                                   if years(view["context"]) else None)}}


def read_items():
    """The synthetic OfficeQA test panel: pages 180-219, never a training page; every fourth page names its first
    column "Term", so the YEARS procedure does not fire there (a structural zero of the read). "Term" is as long as
    "Year": every test text has one length, so the canary scan hashes each window once."""
    out = []
    for n, item in enumerate(officeqa_items(220)[180:]):
        public = dict(item["public"])
        if n % 4 == 0:
            public["context"] = public["context"].replace("Year |", "Term |")
        out.append({**item, "public": public})
    return out


TEST_ITEMS = read_items()
WIDTH = len(TEST_ITEMS[0]["public"]["context"])


def filler(bench):
    """Six stand-in test texts of a bench without a fixture test set, as long as the OfficeQA test pages (one window
    length keeps the run-root scan cheap)."""
    return [("%s fixture test text %d " % (bench, n)).ljust(WIDTH, ".") for n in range(6)]


def even(text):
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % 2 == 0


class Answers:
    """Both chains' fake solver (``answer(system, user)``), the same replies in every arm and run.

    OfficeQA (T-STEP-1's rule): right when the notes carry the item's own customs receipts (YEARS on that item), else
    right on the items whose key is even; a generated item is known once ``examiner.build`` made it (the parent
    solves every second one); an unknown request (a shortcut variant without its table) gets a wrong answer.
    SpreadsheetBench: the first program is right on the workbooks whose preview hashes even; a repair call returns the
    right program only when its notes name the workbook's own column A, else the previous program again."""

    def __init__(self, items):
        self.answers = {key(item["public"]): item["private"]["answer"] for item in items}
        self.right = {}

    def add(self, generated):
        for n, item in enumerate(generated):
            found = key(item["public"])
            self.answers[found], self.right[found] = item["private"]["answer"], n % 2 == 0

    def __call__(self, system, user):
        if user == FIRST_CALL_USER:  # chain.run's first-call confirmation (registrar addendum 14:10, row 7)
            return "ready"
        view = json.loads(user)
        if "workbook_preview" in view:
            if "previous_program" in view:
                return RIGHT if column_a(view) in view.get("repair_notes", "") else view["previous_program"]
            return RIGHT if even(json.dumps(view["workbook_preview"], sort_keys=True)) else WRONG
        found = key(view)
        if found not in self.answers:
            return tagged("0")
        own = years(view["context"])
        right = (own is not None and own in view.get(NOTES_KEY, "")) or self.right.get(found, int(found, 16) % 2 == 0)
        return tagged(self.answers[found] if right else "0")


class Native(FakeNative):
    """FakeNative for this pilot: the pre-check reports the KeyError for a wrong program and a clean run for the right
    one (a procedure asking for a repair after a passed run fails the engineer's negative test, C7), and every program
    run delivers one workbook (the fixture verdict below decides the score)."""

    def precheck(self, program, workbook, answer_position, runtime, *, evidence):
        report = {"status": "ok", "answer_cells": {"Sheet!B1": "15"}} if SUM_FORMULA in program else ERROR_REPORT
        return FakeNative(report=report).precheck(program, workbook, answer_position, runtime, evidence=evidence)

    def native(self, request, runtime):
        super().native(request, runtime)
        book = openpyxl.Workbook()
        book.active["B1"] = 15
        buffer = io.BytesIO()
        book.save(buffer)
        return {"status": "available", "output_base64": base64.b64encode(buffer.getvalue()).decode(),
                "reason": "isolated_workbook_generated", "cleanup_confirmed": True}


def sheet_score(real):
    """The fixture SpreadsheetBench verdict in place of the frozen recalculating scorer (the programs never run)."""
    def score(benchmark, public, private, prediction, *, runtime=None):
        if benchmark != SB or prediction.get("status") != "available":
            return real(benchmark, public, private, prediction, runtime=runtime)
        passed = SUM_FORMULA in prediction["output"]["code"]
        return {"status": "pass" if passed else "fail", "score": float(passed), "reason": "fixture_sheet_verdict",
                "cleanup_confirmed": True,
                "metrics": {"cases": [{"status": "pass" if passed else "fail", "reason": "fixture"}]}}
    return score


def sheet_change(failing):
    test = test_case(failing, "sheet_feedback", {"kind": "repair_requested", "value": True},
                     mutation="drop_exception_message")
    return {"kind": "new", "description": "Names the values of the workbook's column A after a failed pre-check and "
                                          "asks for one repair.", "hooks": ["applies", "sheet_feedback"],
            "max_note_chars": 1000, "requests_second_call": True, "replay_tests": [test]}


def roles_answer(system, payload):
    """The scripted GLM-5.3 roles of both chains, told apart by their pinned system prompts and the payload's bench."""
    bench = payload.get("bench") if isinstance(payload, dict) else None
    if system == examiner.DETECTOR_SYSTEM:
        return engineer_reply({"detectors": [{"description": "Ratio questions fail."}]}, [DETECTOR])
    if system == examiner.POLICY_SYSTEM:
        if bench == SB:  # no research request: no material, no generated item (§7.2 no_material)
            return {"families": ["spreadsheetbench.formula_edit"], "rationale": "Workbook formulas.", "requests": []}
        return {"families": ["officeqa.percent_change"], "rationale": "Public finance tables.",
                "requests": [{"kind": "family_material", "family": "officeqa.percent_change", "concept": concept,
                              "topic": None} for concept in CONCEPTS]}
    if system == examiner.GENERATOR_SYSTEM:
        if bench == SB or not payload["materials"]:
            return {"specs": []}
        return {"specs": [{"family": "officeqa.percent_change", "material": payload["materials"][0]["id"],
                           "params": PARAMS}]}
    if system == research.QUERY_SYSTEM:
        return fake_research.query(CONCEPTS[1] if "public finance" in json.dumps(payload) else CONCEPTS[0])
    if system == research.PICK_SYSTEM:
        return fake_research.pick("R1")
    if system in research.CONCLUDE_SYSTEM.values():
        return fake_research.table("P1", 0)
    if system == engineer.ENGINEER_SYSTEM:
        if payload["request"] == "fix":  # resend the change unchanged
            change = dict(payload["change"])
            code = change.pop("source")
            return engineer_reply({"changes": [change]}, [code])
        failing = next(t["cell"] for t in payload["trajectories"] if t["kind"] == "failures")
        if payload["bench"] == SB:
            return engineer_reply({"changes": [sheet_change(failing)]}, [source(SHEET)])
        years_test = test_case(failing, "before_call", {"kind": "note_contains", "value": "Customs receipts by year"},
                               mutation="strip_digits")
        return engineer_reply({"changes": [
            new("Lists the customs receipts of each year in the table.", years_test),
            new("Counts the table rows.",
                test_case(failing, "before_call", {"kind": "note_contains", "value": "rows"})),
            new("Suggests a candidate number.", test_case(failing, "before_call",
                                                          {"kind": "note_contains", "value": LEAKED}))]},
            [source(YEARS), source(CRASH), source(LEAK, LEAKED=LEAKED)])
    if system == describer.DESCRIBER_SYSTEM:
        return DESCRIPTION
    # the leakage adjudicator: a leak only where the run-slice reference answer is named
    if LEAKED in json.dumps(payload):
        return {"verdict": "yes", "reason": "It names a run-slice reference answer."}
    return {"verdict": "no", "reason": "It names no reference answer."}


def docker_workers(docker, scratch):
    """``Services.workers``: a FakeDocker-backed sandbox worker per block (the real worker in a local process)."""
    @contextmanager
    def factory(package, *, kind, hashseed=0, inputs_dir=None, tag=None):  # the step binds each unit's tag (C5-1)
        worker = Worker(docker=docker, limits=TEST_LIMITS, scratch=scratch, hashseed=hashseed, tag=tag)
        worker.start(package, kind=kind, inputs_dir=inputs_dir)
        try:
            yield worker
        finally:
            try:
                worker.close()
            except CleanupUnconfirmed:
                pass

    return factory


@contextmanager
def item_workers(package, item):
    """The router's and the donors' factory: a started FakeSandbox with the cells' procedures."""
    worker = FakeSandbox(HOOKS).start(package, kind="cell")
    try:
        yield worker
    finally:
        worker.close()


def panel(pinned, bench, *, access):
    assert bench == OQ and access.unit in ("G/test/" + OQ, "D/test/" + OQ)
    tasks = [{"task_id": i["task_id"], "public": i["public"], "private": i["private"]} for i in TEST_ITEMS]
    return tasks, {"panel_hash": digest(tasks), "excluded_without_pages": 0, "source_files": None}


def descriptions(chain_root):
    """{procedure id: frozen text} of the describer's records of every step's freeze unit."""
    found = []
    for path in sorted(chain_root.glob("s*-*/freeze/unit.json")):
        found += verified(read_json(path), "unit")["result"]["descriptions"]
    return describer.texts(found)


def canary_panel(pinned, bench, *, access):
    """The test sets the read's canaries come from (registrar decision C3-1 (b)): each OfficeQA test page's context
    as its question text (the fixture's questions repeat four templates of the training pages), stand-ins for the
    other two benches."""
    assert access.unit == evaluation.READ_CANARY_UNIT
    texts = [i["public"]["context"] for i in TEST_ITEMS] if bench == OQ else filler(bench)
    tasks = [{"task_id": "%s-%d" % (bench, n), "public": {evaluation.READ_CANARY_SOURCES[bench]: text}}
             for n, text in enumerate(texts)]
    return tasks, {"panel_hash": digest(tasks)}


def pool_pins(directory, pools):
    """The manifest's ``data.pools`` pins of the pilot's two pools ({bench: {"path", "sha256"}}): the training side the
    read record's selection checks (registrar decision PR-C31-3 (1a)), written outside the run root."""
    pins = {}
    for bench, items in sorted(pools.items()):
        write_json(directory / ("%s.json" % bench), items)
        path = directory / ("%s.json" % bench)
        pins[bench] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return pins


class Pilot:
    """The read children of both chains, in process: the OfficeQA unit for real, the others stand-in records."""

    def __init__(self, canaries, pins):
        self.canaries, self.pins = canaries, pins

    def launch(self, setting_, spec):
        unit_root, name = Path(spec["unit_root"]), spec["chain"]
        if spec["bench"] != OQ:  # a stand-in unit: it names its run, chain and package like a real one
            unit_root.mkdir(parents=True, exist_ok=True)
            write_json(unit_root / "unit.json", record("evaluation", FIXTURE, {
                "run": setting_.run, "chain": name, "bench": spec["bench"],
                "packages": {"F": spec["package_sha256"]}, "stand_in": True}))
            return chain.EXIT_COMPLETE
        chain_root = chain.chain_root(setting_, name)
        final = load(chain_root / "packages" / (spec["package_sha256"] + ".json"))
        model = CHAINS[name]
        client = setting_.clients(model, OQ)
        bound = ledger_bound(model, OQ, branch=None if name == "G" else setting_.branch,
                             longest=None if name == "G" else setting_.longest)
        endpoint = budgets.endpoint(setting_, budgets.solver_scopes(name, None, None, "test"), client=client,
                                    max_tokens_bound=bound)
        context = units.cell_context(setting_, unit_root / "attempt-1", endpoint)

        def placebo(cell, task):
            return Arm("placebo_y", final, placebo={"procedures": {
                YEARS_ID: {"before_call": {"facts": ["Customs receipts by year: a donor's table."]}}},
                "seed": "seed:" + cell["id"]})

        arms = {"F": Arm("candidate", final), "C": Arm("card", empty(step="%s/card" % name, evidence=FIXTURE)),
                "P_F": placebo, "T_F": Arm("text", final, text=descriptions(chain_root))}
        evaluation.make_read_canaries(setting_.root, None, pools=self.pins, run=setting_.run, evidence=FIXTURE,
                                      panel=canary_panel)
        evaluation.evaluate(unit_root, run=setting_.run, shared=setting_.shared, pinned=None, chain=name, bench=OQ,
                            arms=arms, context=context, workers=1, route_workers=item_workers,
                            canaries=evaluation.load_canaries(setting_.root, read=True), panel=panel)
        return chain.EXIT_COMPLETE


# ------------------------------------------------------------------------------------------------- the pilot run
@pytest.fixture(scope="module")
def pilot(tmp_path_factory):
    """Run both chains through the pilot, the test read, the continuation file, the addendum and the unseal."""
    tmp = tmp_path_factory.mktemp("e2e")
    root, shared = tmp / "root", tmp / "root" / "shared"
    shared.mkdir(parents=True)
    write_json(shared / "consent.json", consent_value())
    found, counts = evaluation.select_canaries({"alfworld": filler("alfworld"), "searchqa": filler("searchqa")})
    write_json(root / CANARIES, record("test-canaries", FIXTURE, {"canaries": found, "counts": counts}))
    sb_items = spreadsheetbench_items(tmp / "sheets", SB_COUNT)
    pins = pool_pins(tmp / "pools", {SB: sb_items, OQ: OQ_ITEMS})
    answers = Answers(OQ_ITEMS + TEST_ITEMS)
    solvers = {"G": FakeSolver(tmp / "solver-G", [(None, answers)], model=GLM_SOLVER)}
    solvers.update({("D", bench): FakeSolver(tmp / ("solver-D-" + bench), [(None, answers)], model=DEEPSEEK,
                                             max_tokens=ELUCID_MAX_TOKENS[bench],
                                             read_timeout=ELUCID_READ_TIMEOUT[bench]) for bench in (SB, OQ)})
    glms = {name: FakeGLM(tmp / ("glm-" + name), roles_answer) for name in CHAINS}
    ledgers = {name: Budget(budgets.ledger_root(root, name), sleep=lambda _: None) for name in CHAINS}
    pools = slots.pools(tmp / "slots", poll=0.01, log=lambda line: None)
    ticks, waited = itertools.count(), []

    def clock():  # advanced by the dispatch's wait between OfficeQA's time blocks (§3.3)
        return float(next(ticks)) + sum(waited)

    def clients(name):
        def client(model, bench):
            if bench is None:
                return glms[name].client
            return solvers["G"].client if name == "G" else solvers[("D", bench)].client
        return client

    base = units.Setting(
        run=RUN, root=root, shared=shared, pools={SB: sb_items, OQ: OQ_ITEMS}, cards={b: CARD for b in BENCHES},
        runtime={**RUNTIME, SB: SHEET_RUNTIME}, clients=None, budget=None, slots=pools, sandbox={},
        evidence=FIXTURE, workers=1, cooldown=0,
        extra={"verify": lambda: None, "slot_root": str(tmp / "slots"),
               "test_read_estimate": {"G": 10 ** 6, "D": 10 ** 6}})
    settings = {name: replace(base, clients=clients(name), budget=ledgers[name], branch=None if name == "G" else "E")
                for name in CHAINS}
    docker = FakeDocker(tmp / "containers")
    registry = Registry(tmp / "history", evidence=FIXTURE)
    research_root = tmp / "research"
    canaries = [evaluation.canary(item["public"]["context"]) for item in TEST_ITEMS]
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(fake_research.PAGES, "Public finance", ("Public finance", 1007, SECOND_TABLE, [], False))
        patch.setitem(fake_research.SEARCHES, CONCEPTS[1], ["Public finance"])
        Native().install(patch)
        patch.setattr(backends, "score", sheet_score(backends.score))
        real_context = units.cell_context

        def context(setting_, attempt, endpoint):
            found = real_context(setting_, attempt, endpoint)
            found.worker, found.clock = (lambda bench: FakeSandbox(HOOKS)), clock
            return found

        patch.setattr(units, "cell_context", context)
        patch.setattr(rounds, "cell_context", context)
        made = examiner.build

        def known(*args, **kwargs):  # the fake solver learns the generated items' answers
            found = made(*args, **kwargs)
            answers.add(found.items)
            return found

        patch.setattr(examiner, "build", known)
        patch.setattr(examiner, "BAND_PROBE_ITEMS", 4)  # the four-item OQ set's band probe (Codex finding #9)
        services = step.Services(registry=registry, sources=fake_research.sources(research_root)[0],
                                 workers=docker_workers(docker, tmp), item_workers=item_workers, clock=clock,
                                 sleep=waited.append)
        launcher = Pilot(canaries, pins)
        results = {name: chain.run(settings[name], name, learn=functools.partial(step.learn, services=services),
                                   launch=launcher.launch) for name in CHAINS}
    docker.close()

    # the owner's continuation file and the formal-chain addendum, sealed before the unseal (Codex F17)
    write_json(shared / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "fixture: the formal chain"})
    (shared / "formal-addendum.md").write_text("# Formal-chain addendum (fixture)\n", encoding="utf-8")
    addendum = evaluation.seal_addendum(root, evidence=FIXTURE, clock=lambda: "2026-10-22T09:00:00Z")
    opened, labels = {}, {}
    for name in CHAINS:
        labels[name] = evaluation.continuation_check({"root": str(root)}, chain=name,
                                                     clock=lambda: "2026-10-22T10:00:00Z")["label"]
        opened[name] = evaluation.unseal(root, root / name, name, [chain.unit_root(settings[name], name, OQ)],
                                         run=RUN, evidence=FIXTURE, clock=lambda: "2026-10-22T10:00:00Z")
    return SimpleNamespace(root=root, shared=shared, tmp=tmp, results=results, settings=settings, ledgers=ledgers,
                           solvers=solvers, glms=glms, registry=registry, research_root=research_root,
                           canaries=canaries, sb_items=sb_items, waited=waited, addendum=addendum, labels=labels,
                           opened=opened)


def unit_result(chain_root, k, bench, name):
    return verified(read_json(units.unit_path(chain_root, k, bench, name) / "unit.json"), "unit")


def step_record(chain_root, k, bench):
    return verified(read_json(chain_root / ("s%d-%s" % (k, bench)) / step.STEP_FILE), "step")


# ---------------------------------------------------------------------------------------------------- the chains
def test_both_chains_complete_the_pilot_and_accept_the_same_procedures(pilot):
    assert ORDER == (SB, OQ)
    assert pilot.results == {"G": {"status": "complete"}, "D": {"status": "complete"}}
    finals = {}
    for name in CHAINS:
        chain_root = pilot.root / name
        done = verified(read_json(chain_root / "chain-complete.json"), "chain-complete")
        assert done["identity"] == {"run": RUN, "chain": name}
        assert verified(read_json(chain_root / "chain.json"), "chain")["solver"] == CHAINS[name]
        first, second = step_record(chain_root, 1, SB), step_record(chain_root, 2, OQ)
        assert done["steps"] == [first["record_sha256"], second["record_sha256"]]
        for value, k, bench in ((first, 1, SB), (second, 2, OQ)):
            assert (value["chain"], value["k"], value["bench"]) == (name, k, bench)
            assert value["step"] == "%s/s%d-%s" % (name, k, bench) and value["evidence_kind"] == "selection"
            assert value["decision"] == "accept" and value["reason"] == "J1-J7 hold"
        assert second["parent_sha256"] == first["package_sha256"] != first["parent_sha256"]
        final = load(chain_root / "packages" / (done["package_sha256"] + ".json"))
        assert final.order == (SHEET_ID, YEARS_ID) and set(final.describer) == {SHEET_ID, YEARS_ID}
        read = verified(read_json(chain_root / chain.TEST_READ), "test-read")
        assert read["status"] == "read" and read["gate"]["used"] == read["gate"]["estimate"] == 10 ** 6
        assert (read["gate"]["factor"] is None) == (name == "D")  # chain G's measured factor (< 1 here)
        confirmed = verified(read_json(chain_root / chain.CONFIRM), "first-call")  # before its first unit
        assert confirmed["passed"] and confirmed["returned_model"] == CHAINS[name] and confirmed["charged"] > 0
        finals[name] = final
    # both chains learned the same procedures from the same fixtures (their solvers answer alike); the records differ
    # in their lineage (each chain's own engineer call)
    same = [[(p.id, p.source, p.hooks, p.description) for p in finals[name].procedures] for name in CHAINS]
    assert same[0] == same[1] and finals["G"].sha256 != finals["D"].sha256


def test_step_one_spreadsheetbench_runs_every_sub_step_and_its_generator_is_not_admitted(pilot):
    for name in CHAINS:
        chain_root = pilot.root / name
        value = step_record(chain_root, 1, SB)
        assert set(value["units"]) == {"run", "diagnose", "generate", "engineer", "selftest", "accept", "freeze"}
        run = unit_result(chain_root, 1, SB, "run")["result"]
        assert run["cells"] == 31 * 2 and run["firing_share"] == 0.0 and run["entry_reading"] is None
        generated = unit_result(chain_root, 1, SB, "generate")["result"]
        assert generated["research"] == [] and generated["g_self"] == []
        assert generated["generator"]["status"] == "not_admitted"
        changes = unit_result(chain_root, 1, SB, "engineer")["result"]["engineer"]["changes"]
        assert [c["survived"] for c in changes] == [True]
        tested = unit_result(chain_root, 1, SB, "selftest")["result"]
        assert tested["reason"] == "no_generated_items" and not tested["blocked"]
        accepted = unit_result(chain_root, 1, SB, "accept")["result"]
        assert accepted["decision"] == "accept" and not accepted["dup"] and accepted["g_acc"] == 0
        frozen = unit_result(chain_root, 1, SB, "freeze")["result"]
        assert [d["procedure"] for d in frozen["descriptions"]] == [SHEET_ID]


def test_step_two_officeqa_researches_generates_and_keeps_only_the_valid_change(pilot):
    for name in CHAINS:
        chain_root = pilot.root / name
        # the inherited SpreadsheetBench procedure fires on half the run slice: the card arm runs beside S (§5.1)
        run = unit_result(chain_root, 2, OQ, "run")["result"]
        assert run["cells"] == 24 * 2 + 24 and run["firing_share"] == 0.5
        assert run["entry_reading"]["items"] == 24 and run["entry_reading"]["decides"] is False
        generated = unit_result(chain_root, 2, OQ, "generate")
        made = generated["result"]
        assert [finding["status"] for finding in made["research"]] == ["found", "found"]
        assert all(finding["calls"] <= 8 for finding in made["research"])  # §7.2: at most 8 calls per request
        split = read_json(chain_root / "s2-officeqa" / "generate" / generated["attempt"] / "research-split.json")
        assert len(split["g_self"]) == len(split["g_acc"]) == 1
        assert split["g_self"][0]["id"] != split["g_acc"][0]["id"]
        for material in split["g_self"] + split["g_acc"]:  # each table's page was archived before use
            page = read_json(pilot.research_root / "store" / "sources" / (material["archive"] + ".json"))
            assert material["caption"] in page["html"]  # the table is quoted verbatim from its archived page
            assert all(cell in page["html"] for row in material["rows"] for cell in row)
        # the family consumed only the G_self finding; the G_acc half stayed for the registrar's G_acc build
        assert made["generator"]["status"] == "admitted" and made["g_self"]
        assert {item["material"] for item in made["g_self"]} == {split["g_self"][0]["id"]}
        changes = unit_result(chain_root, 2, OQ, "engineer")["result"]["engineer"]["changes"]
        valid, crash, leak = changes  # the crashing and the leaking change are dropped after their one fix
        assert valid["survived"] and len(valid["attempts"]) == 1
        assert not crash["survived"] and [a["failed"] for a in crash["attempts"]] == ["C6", "C6"]
        assert not leak["survived"] and [a["failed"] for a in leak["attempts"]] == ["C4", "C4"]
        assert all(a["checks"][-1]["detail"]["adjudicated"] for a in leak["attempts"])
        tested = unit_result(chain_root, 2, OQ, "selftest")["result"]
        assert not tested["blocked"] and tested["cells"] == 2 * len(made["g_self"])


def test_the_acceptance_rounds_seal_every_registered_arm(pilot):
    for name in CHAINS:
        chain_root = pilot.root / name
        for k, bench, dup in ((1, SB, False), (2, OQ, True)):
            sealed = verified(read_json(units.unit_path(chain_root, k, bench, "accept") / "sealed.json"),
                              "acceptance-sealed")
            assert (sealed["chain"], sealed["bench"], sealed["dup"]) == (name, bench, dup)
            assert sealed["freshness"] == step.FRESHNESS and sealed["plan"]["decision"] == "run"
            assert len(sealed["plan"]["astar"]) >= 30 and sealed["placebo_y"] and sealed["placebo_i"]
            # P_y's donors: the parent's run-slice trajectories, sealed with zero calls before dispatch (§6.4)
            slices = verified(read_json(chain_root / ("s%d-%s" % (k, bench)) / step.SLICES_FILE),
                              "step-slices")["slices"]
            corpus = sealed["corpus"]
            assert donors.seal(corpus) == corpus["record_sha256"] and corpus["donors"] and not corpus["faults"]
            assert {rounds.bench_of(item) for item in corpus["items"].values()} == {bench}
            assert {item.partition("/")[2] for item in corpus["items"].values()} <= set(slices["run"])
            twins = [twin for found in sealed["plan"]["twins"].values() for twin in found]
            if bench == SB:  # one new change: S' - S is its twin's estimand, no twin is drawn (§6.1, §6.5)
                assert twins == []
            else:  # the inherited SpreadsheetBench procedure fires on >= 15 A* items: its withholding twins
                assert twins and {(t["procedure"], t["kind"]) for t in twins} == {(SHEET_ID, "withhold")}
            if bench == OQ:  # G_acc from the frozen generator on the g_acc research half (§7.2)
                assert sealed["g_acc"] and all(g["source_item"] in sealed["plan"]["astar"] for g in sealed["g_acc"])
                made = unit_result(chain_root, k, bench, "generate")["result"]  # no id names two items (C4-1)
                acc = {int(g["id"].rpartition(":")[2]) for g in sealed["g_acc"]}
                assert max(int(i["id"].rpartition(":")[2]) for i in made["g_self"]) < made["numbered"] <= min(acc)
            else:
                assert sealed["g_acc"] is None
            attempt = units.unit_path(chain_root, k, bench, "accept") / unit_result(chain_root, k, bench,
                                                                                     "accept")["attempt"]
            arms = {verified(read_json(p), "cell")["arm"] for p in (attempt / "cells").glob("*.json")}
            expected = {"S'", "S", "P_y", "P_i", "C"} | ({"S_dup", "withhold:" + SHEET_ID} if dup else set())
            assert arms == expected
    assert len(pilot.waited) == 2  # OfficeQA's block gap, once in each chain


def test_every_decision_again_from_its_cell_records_and_sealed_record_alone(pilot):
    for name in CHAINS:
        chain_root = pilot.root / name
        for k, bench in ((1, SB), (2, OQ)):
            accept_root = units.unit_path(chain_root, k, bench, "accept")
            attempt = accept_root / unit_result(chain_root, k, bench, "accept")["attempt"]
            cells = [verified(read_json(path), "cell") for path in sorted((attempt / "cells").glob("*.json"))]
            sealed = verified(read_json(accept_root / "sealed.json"), "acceptance-sealed")
            stored = verified(read_json(attempt / "decision" / "decision.json"), "decision")
            again = acceptance.decide(cells, sealed)
            assert canonical(again) == canonical(stored)
            assert again["record_sha256"] == step_record(chain_root, k, bench)["decision_sha256"]


# ------------------------------------------------------------------------------------------ records and stamps
def test_every_record_is_versioned_labelled_and_stamped_with_its_chain(pilot):
    ledger_roots = [ledger.root for ledger in pilot.ledgers.values()]
    checked = 0
    for path in sorted(pilot.root.rglob("*.json")):
        parts = set(path.relative_to(pilot.root).parts)
        if {"artifacts", "host_only"} & parts or path.name in OWNER_FILES or any(r in path.parents
                                                                               for r in ledger_roots):
            continue
        value = read_json(path)
        assert value["version"].startswith("fivebench-execskill-v1-") and value["evidence"] == FIXTURE, path
        checked += 1
    assert checked > 1000
    for name in CHAINS:  # the units of a chain name that chain; its cells sit under the chain's root
        for path in sorted((pilot.root / name).glob("s*-*/*/unit.json")):
            value = verified(read_json(path), "unit")
            assert value["identity"]["chain"] == name and value["identity"]["unit"].startswith(name + "/")
        unit = verified(read_json(chain.unit_root(pilot.settings[name], name, OQ) / "unit.json"), "evaluation")
        assert unit["chain"] == name and unit["run"] == RUN
    # the consumption lines are records of their chain's namespace
    for path in sorted((pilot.tmp / "history").rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            value = verified(json.loads(line), "consumption")
            assert value["chain"] == path.parent.name and value["unit"].startswith(value["chain"] + "/")


def test_both_chains_consume_the_same_slice_items_in_their_own_namespaces(pilot):
    entries = {(name, bench): pilot.registry.entries(name, bench) for name in CHAINS for bench in (SB, OQ)}
    for bench, k in ((SB, 1), (OQ, 2)):
        assert set(entries[("G", bench)]) == set(entries[("D", bench)])
        for name in CHAINS:
            chain_root = pilot.root / name
            slices = verified(read_json(chain_root / ("s%d-%s" % (k, bench)) / step.SLICES_FILE),
                              "step-slices")["slices"]
            astar = set(verified(read_json(units.unit_path(chain_root, k, bench, "accept") / "sealed.json"),
                                 "acceptance-sealed")["plan"]["astar"])
            lines = entries[(name, bench)]
            assert set(lines) == set(slices["run"]) | set(slices["accept"])
            label = "%s/s%d-%s/" % (name, k, bench)
            assert all(lines[i]["state"] == "decided" and lines[i]["unit"] == label + "run" for i in slices["run"])
            assert all(lines[i]["state"] == ("decided" if i in astar else "routed_not_dispatched")
                       and lines[i]["unit"] == label + "accept" for i in slices["accept"])
    assert len(entries[("G", SB)]) == SB_COUNT and pilot.registry.consumed("smoke", SB) == set()


def test_each_chain_ledger_settles_every_reservation_on_its_own_scopes(pilot):
    for name, other in (("G", "D"), ("D", "G")):
        ledger = pilot.ledgers[name]
        events = [json.loads(line) for line in (ledger.root / "events.jsonl").read_text().splitlines()]
        reserved = {e["id"] for e in events if e["event"] == "reserve"}
        settled = [e for e in events if e["event"] == "settle"]
        assert reserved and reserved == {e["id"] for e in settled} and len(settled) == len(reserved)
        assert not [e for e in events if e["event"] in ("halt", "refuse")]
        assert all(entry["open"] == 0 for entry in ledger.snapshot().values())
        charged = {scope for e in settled for scope in e["scopes"]}
        assert all(scope == budgets.ROOT or scope.startswith(name + ":") for scope in charged)
        assert not any(scope.startswith(other + ":") for scope in ledger.snapshot())
        kinds = {SB: ("run", "accept", "role:engineer", "role:examiner"),  # no generated item: no probe, no self-test
                 OQ: ("run", "examiner", "selftest", "accept", "role:engineer", "role:examiner",
                      "role:examiner:research")}
        for k, bench in ((1, SB), (2, OQ)):
            assert {"%s:xs:%s:%d:%s" % (name, bench, k, kind_) for kind_ in kinds[bench]} <= charged
        assert name + ":test" in charged  # the test read was charged to the chain's test scope
        roles = sum(name + ":glm" in e["scopes"] for e in settled)
        assert roles == len(pilot.glms[name].seen)
    solver_calls = {"G": len(pilot.solvers["G"].requests),
                    "D": sum(len(pilot.solvers[("D", b)].requests) for b in (SB, OQ))}
    for name in CHAINS:
        events = [json.loads(line) for line in (pilot.ledgers[name].root / "events.jsonl").read_text().splitlines()]
        assert sum(name + ":solver" in e["scopes"] for e in events if e["event"] == "settle") == solver_calls[name]


# ------------------------------------------------------------------------------------------- the test read
def test_no_test_text_in_any_training_side_artifact(pilot):
    training = [pilot.root / name / ("s%d-%s" % (k, bench)) for name in CHAINS for k, bench in ((1, SB), (2, OQ))]
    training += [pilot.root / name / "packages" for name in CHAINS]
    training += [pilot.tmp / "history", pilot.research_root]
    assert len({found["chars"] for found in pilot.canaries}) == 1  # one window length (read_items)
    for directory in training:
        files, hits = evaluation.canary_scan(directory, pilot.canaries)
        assert files > 0 and hits == [], directory
    # positive control: the same scan finds a planted test text
    planted = pilot.tmp / "planted"
    planted.mkdir()
    (planted / "note.json").write_text(json.dumps({"note": TEST_ITEMS[5]["public"]["context"]}), encoding="utf-8")
    assert evaluation.canary_scan(planted, pilot.canaries)[1]


def test_the_read_shares_structural_zeros_and_seals_hashes_only(pilot):
    zero = {item["task_id"] for item in TEST_ITEMS if "Year |" not in item["public"]["context"]}
    for name in CHAINS:
        unit_root = chain.unit_root(pilot.settings[name], name, OQ)
        unit = verified(read_json(unit_root / "unit.json"), "evaluation")
        assert unit["structural_zero"] == len(zero) and unit["counts"]["infrastructure"] == 0
        assert verified(read_json(unit_root / unit["attempt"] / "canary_scan.json"), "canary-scan")["hits"] == 0
        assert not (unit_root / unit["attempt"] / "transient").exists()
        for path in unit_root.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                assert "Fixture bulletin page" not in text and "<answer>" not in text, path


def test_the_owner_continuation_unseals_and_the_readout_tables(pilot):
    assert verified(read_json(pilot.shared / "formal-addendum.json"), "formal-addendum") == pilot.addendum
    tables = {}
    for name in CHAINS:
        assert pilot.labels[name] == "interim_read_addendum_before_unseal"
        marker = verified(read_json(pilot.root / name / evaluation.UNSEALED), "unseal")  # C3-1 (b): scanned first
        scan = verified(read_json(pilot.root / name / evaluation.ROOT_SCAN / marker["canary_scan"]["attempt"]
                                  / "scan.json"), "root-canary-scan")
        assert (scan["hits"], scan["canaries"], marker["canary_scan"]["release"]) == (0, 25, None)
        assert scan["files_scanned"] > 1000
        opened = pilot.opened[name]
        assert (opened["label"], opened["later_reads"]) == ("interim_read_addendum_before_unseal", "confirmatory")
        table = opened["units"][OQ]
        assert table and all(len(key_) == 3 for key_ in table)
        tables[name] = sorted(key_ for key_ in table if not key_[0].startswith("withhold:"))
        found = verified(readout.readout(opened["units"], learned=[OQ], procedures={YEARS_ID: OQ},
                                         label=opened["later_reads"], evidence=FIXTURE), "readout")
        assert found["evidence_kind"] == "generalization" and found["learned"] == [OQ]
        assert found["q1_home"][OQ]["mean"] > 0  # F beats C on the items YEARS reads (an engineering fixture)
    assert tables["G"] == tables["D"]
    assert evaluation.read_label([pilot.root / "G", pilot.root / "D"]) == "confirmatory"
