"""Integration B3 (cells, rounds, acceptance): rows A8 (cells, units, rounds, trajectories) and A9 (donors, placebo,
acceptance, validity) wired together; implementation plan §9 gate (ii), registration §2.5, §3.3, §3.4, §5.1,
§6.1-§6.5, §7.2. Offline and deterministic: a stateless fake solver behind the frozen Endpoint, FakeSandbox
procedures, one worker thread and a tick clock; no model call, no container.

Gate (ii): one fake OfficeQA acceptance round end to end. The parent's run slice runs as a unit (``units.run_unit``,
``rounds.run_round``) and its stored parent trajectories are the donors. ``acceptance.prepare`` seals the round,
``acceptance.dispatch`` runs every scheduled cell through ``acceptance.runner`` -- real ``cells.run_cell``: the shell,
the frozen call wrapper and scorer, the route-B decision rows and the judge -- in the schedule's order, and
``acceptance.decide`` decides. The decision is then made again from the stored cell records and the stored sealed
record alone and must be the identical JSON.

Ticket A9-1: a SpreadsheetBench parent cell at step 1 (the empty package) stores its pre-check report, and the stored
trajectory gives a candidate's ``sheet_feedback`` procedure its donor content (the P_y sham, §6.1).
"""
from __future__ import annotations

import base64
import hashlib
import io
import itertools
import json
from contextlib import contextmanager

import openpyxl

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json
from skillopt.execskill import acceptance, donors, rounds, solver, trajectories, units, validity
from skillopt.execskill.cells import Arm, Context, TrainingStore, cell_id, run_cell
from skillopt.execskill.package import Package, empty, with_
from skillopt.execskill.protocol import BENCHES, NOTES_KEY, kind, verified
from skillopt.execskill.registry import Registry
from tests.execskill_fakes_env import FakeNative, FakeSandbox, procedure
from tests.fixtures.execskill.items import officeqa_items, spreadsheetbench_items

EVIDENCE = "engineering_fixture"
BENCH, CHAIN, RUN = "officeqa", "G", "fixture-run"
STEP = "pilot/s2-officeqa/t1"
RUN_UNIT, ACCEPT_UNIT = "G/s2-officeqa/run", "G/s2-officeqa/accept"
CARD = "Read the public table before answering."
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
CHECKED = "Checked table "
ITEMS = officeqa_items(52)
ACCEPT, RUN_SLICE = ITEMS[:40], ITEMS[40:]  # the acceptance slice A: pages 0-39; the run slice: pages 40-51
GENERATED = officeqa_items(160)[100:]  # the examiner's fixture G_acc items: pages 100-159


def key(view):
    return hashlib.sha256((view["question"] + "\n" + view["context"]).encode()).hexdigest()


def page(view):
    return int(view["context"].split("page ", 1)[1].split("\n", 1)[0])


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def reply(text):
    return {"ok": True, "response": text, "finish_reason": "stop", "error_type": None, "usage": dict(USAGE),
            "attempts": [{"status": 200}]}


K = procedure("p-officeqa-1-1", ("applies", "before_call"), header="Table reading notes.", evidence=EVIDENCE)
D = procedure("p-officeqa-1-2", ("applies", "before_call"), header="Year column notes.", evidence=EVIDENCE)
N = procedure("p-officeqa-2-1", ("applies", "before_call"), header="Row helper notes.", evidence=EVIDENCE)
HOOKS = {K.id: {"before_call": lambda view, state: {"facts": ["Read the years in the first column."]}},
         D.id: {"applies": lambda view: page(view) % 2 == 0,
                "before_call": lambda view, state: {"facts": ["The totals sit in the last row."]}},
         N.id: {"applies": lambda view: page(view) % 4 != 3,
                "before_call": lambda view, state: {"facts": [CHECKED + key(view)[:12]]}}}
PARENT = Package((K, D), "s1", EVIDENCE)
CANDIDATE = with_(PARENT, step="s2", add=[N], remove=[D.id])  # a new procedure and a deletion: both twin kinds


class Solver:
    """The fake solver (``call(system, user) -> receipt``): right when the notes carry the item's own checked-table
    line (N's real note), else right on the items whose key is even -- the same reply in every arm and run."""

    def __init__(self, tasks):
        self.answers = {key(task["public"]): task["private"]["answer"] for task in tasks}
        self.calls = 0

    def call(self, system, user):
        self.calls += 1
        view = json.loads(user)
        found = key(view)
        right = CHECKED + found[:12] in view.get(NOTES_KEY, "") or int(found, 16) % 2 == 0
        return reply("<answer>%s</answer>" % (self.answers[found] if right else "0"))


def context(root, attempt, endpoint, clock):
    return Context(attempt=attempt, endpoint=endpoint, runtime=RUNTIME, cards={b: CARD for b in BENCHES},
                   native=Slots(root / "slots", "spreadsheet-native", 1),
                   episodes=Slots(root / "slots", "alfworld-episode", 1), worker=lambda bench: FakeSandbox(HOOKS),
                   evidence=EVIDENCE, clock=clock)


def sandboxes(hooks):
    """``workers(package, item)`` of ``prepare`` / ``donors.donor_corpus``: a started FakeSandbox per call."""
    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hooks).start(package, kind="cell")
        try:
            yield worker
        finally:
            worker.close()

    return workers


def generate(views):
    """The examiner's fixture generator on the A* public views: one generated item for every third A* item."""
    return [{"id": "gen:g-officeqa-2-1:%d" % n, "source_item": item} for n, item in enumerate(sorted(views)[::3])]


def run_slice(tmp_path, monkeypatch, endpoint, clock):
    """§5.1: the parent on the run slice (12 items x 2 runs) as a unit; returns its record and its parent
    trajectories, the donors (ticket A9-1 §3)."""
    setting = units.Setting(run=RUN, root=tmp_path, shared=tmp_path / "shared", pools={BENCH: RUN_SLICE},
                            cards={b: CARD for b in BENCHES}, runtime=RUNTIME, clients=None, budget=None, slots={},
                            sandbox={}, evidence=EVIDENCE, workers=1, cooldown=0)
    monkeypatch.setattr(rounds, "cell_context",
                        lambda setting_, attempt, endpoint_: context(tmp_path, attempt, endpoint_, clock))
    tasks = rounds.pool_tasks(setting, [BENCH])
    root = tmp_path / "chain" / "s2-officeqa" / "run"

    def work(attempt):
        found = rounds.run_round(setting, attempt, endpoint, RUN_UNIT, {"S": Arm("parent", PARENT)},
                                 {"S": [(item, 2) for item in sorted(tasks)]}, tasks, tag="run")
        return {"cells": sum(len(records) for records in found.values())}

    unit = units.run_unit(root, run=RUN, identity={"unit": RUN_UNIT}, work=work, evidence=EVIDENCE)
    return unit, [t for t in trajectories.load_run(root) if t["arm_kind"] == "parent"]


def test_gate_ii_a_fake_acceptance_round_reproduces_its_decision_from_the_cell_records(tmp_path, monkeypatch):
    fake = Solver(ITEMS + GENERATED)
    endpoint = Endpoint(fake, model="glm-5.3", max_tokens=100, slots=Slots(tmp_path / "slots", "glm-5.3", 1),
                        sleep=lambda _: None)
    ticks, waited = itertools.count(), []

    def clock():  # a tick clock that the dispatch's wait between OfficeQA's time blocks advances (§3.3)
        return float(next(ticks)) + sum(waited)

    run_record, donor_trajectories = run_slice(tmp_path, monkeypatch, endpoint, clock)
    assert run_record["result"] == {"cells": 24} and len(donor_trajectories) == 24

    # sealing: the donors are the stored run-slice trajectories; zero model calls
    calls_before = fake.calls
    views = {item["task_id"]: solver.routing_view(BENCH, item["public"], runtime=RUNTIME[BENCH]) for item in ACCEPT}
    blocks = {item["task_id"]: ("b1" if n < 20 else "b2") for n, item in enumerate(ACCEPT)}
    root = tmp_path / "chain" / "s2-officeqa" / "accept"
    sealed = acceptance.prepare(root, chain=CHAIN, bench=BENCH, step=STEP, unit=ACCEPT_UNIT, candidate=CANDIDATE,
                                parent=PARENT, views=views, blocks=blocks, workers=sandboxes(HOOKS),
                                trajectories=donor_trajectories, generate=generate, dup=True,
                                freshness="route_b_fresh_method_side_reused", mde=0.10)
    assert fake.calls == calls_before
    plan = sealed["plan"]
    assert plan["decision"] == "run" and len(plan["astar"]) == 30 and plan["twin_kinds"] == {
        N.id: "withhold", D.id: "restore"}
    assert sealed["corpus"]["donors"] == [t["cell"] for t in donor_trajectories]
    donors.verify(sealed["corpus"], donor_trajectories)
    first = plan["astar"][0]
    sham = sealed["placebo_y"][first]["procedures"][N.id]["before_call"]["facts"]
    assert sham[0].startswith(CHECKED) and sham[0] != CHECKED + key(views[first])[:12]  # a donor's content

    # dispatch through the runner, inside the acceptance unit
    records = {item["task_id"]: item for item in ACCEPT}
    registry = Registry(tmp_path / "history", evidence=EVIDENCE)
    registry.register(CHAIN, BENCH, ACCEPT, unit=ACCEPT_UNIT, purpose="accept", run_root=str(tmp_path))
    tasks = {**records, **{g["id"]: GENERATED[int(g["id"].rsplit(":", 1)[1])] for g in sealed["g_acc"]}}
    packages = acceptance.round_packages(CANDIDATE, PARENT, step=sealed["step"], twins=plan["twins"])

    def work(attempt):
        run = acceptance.runner(context(tmp_path, attempt, endpoint, clock), sealed, packages, tasks, workers=1,
                                store=TrainingStore(attempt))
        cells = acceptance.dispatch(sealed, registry, run, items=records, clock=clock, sleep=waited.append)
        decision = acceptance.decide(cells, sealed)
        acceptance.write(root, decision)
        acceptance.settle(decision, sealed, registry, records)
        return {"decision": decision["decision"], "decision_sha256": decision["record_sha256"], "cells": len(cells)}

    unit = units.run_unit(root, run=RUN, identity={"unit": ACCEPT_UNIT}, work=work, evidence=EVIDENCE)
    jobs = [job for block in acceptance.schedule(sealed).values() for job in block]
    assert unit["result"]["decision"] == "accept" and unit["result"]["cells"] == len(jobs)
    assert fake.calls == calls_before + len(jobs)  # one logical call per cell, nothing else

    # gate (ii): the decision again from the stored cell records and the stored sealed record alone
    attempt = root / unit["attempt"]
    stored_cells = [verified(read_json(path), "cell") for path in sorted((attempt / "cells").glob("*.json"))]
    stored_sealed = read_json(root / "sealed.json")
    stored = read_json(root / "decision" / "decision.json")
    again = acceptance.decide(stored_cells, stored_sealed)
    assert canonical(again) == canonical(stored) and again["record_sha256"] == unit["result"]["decision_sha256"]
    assert verified(stored, "decision")["version"] == kind("decision")

    # the cells: one per scheduled job, sent in the schedule's order, with the sealed packages and arm kinds
    sent = sorted(stored_cells, key=lambda c: c["dispatch_ts"])
    assert [(c["arm"], c["task_id"], c["run"], c["set"]) for c in sent] == [
        (j["arm"], j["item"], j["run"], j["set"]) for j in jobs]
    keys = {"S'": "candidate", "S": "parent", "C": "card", "P_y": "placebo", "P_i": "placebo", "S_dup": "parent",
            "withhold:" + N.id: "candidate", "restore:" + D.id: "restore:" + D.id}
    kinds = {"S'": "candidate", "S": "parent", "C": "card", "P_y": "placebo_y", "P_i": "placebo_i", "S_dup": "dup"}
    assert {c["arm"] for c in stored_cells} == set(keys)
    assert all(c["package_sha256"] == sealed["packages"][keys[c["arm"]]] and c["arm_kind"] == kinds.get(
        c["arm"], c["arm"]) and c["stop"] is None and c["faults"] == [] for c in stored_cells)
    assert {c["set"] for c in stored_cells} == {"real", "G_acc"} and all(
        c["block"] == blocks[c["cell"]["source_item"]] for c in stored_cells)
    assert len(list((attempt / "trajectories").glob("*.json"))) == len(jobs)
    assert len(trajectories.enable_log(attempt)) == len(jobs)

    # the decision: S' beats S and P_y on A*; every guard holds; the twins and the duplicate pair are reported
    guards = stored["guards"]
    assert stored["decision"] == "accept" and stored["reason"] == "J1-J7 hold"
    assert stored["evidence_kind"] == "selection" and (stored["A"], stored["A_star"]) == (40, 30)
    assert guards["J1"]["ok"] and guards["J2"]["ok"] and stored["placebo_rule"] == "informative"
    assert guards["J3"]["fault_items"] == 0 and guards["J4_items"]["ok"] and guards["J5"]["ok"]
    assert guards["J5"]["balance"]["ok"] and guards["J6_dup"] == {
        "pairs": [{"pair": "S_dup-S", "p_two_sided": 1.0, "ok": True}], "ok": True}
    assert guards["J5"]["block_gap"]["ok"] and min(guards["J5"]["block_gap"]["gaps_s"]) >= 7_200 and len(waited) == 1
    assert guards["J7_meta"] is None and set(stored["twins"]) == {N.id, D.id}
    assert stored["twins"][N.id]["tau"] > 0 and stored["twins"][D.id]["tau"] == 0
    assert stored["second_call_rates"]["flag_gt_10pt"] is False and stored["sealed"]["record"] == sealed[
        "record_sha256"]

    # consumption: A* decided, the rest of A back in the supply
    states = {i: entry["state"] for i, entry in registry.entries(CHAIN, BENCH).items()}
    astar = set(plan["astar"])
    assert all(states[i] == ("decided" if i in astar else "routed_not_dispatched") for i in records)

    # validity (§7.2): one (d_gen, d_real) pair per round; the duplicate pair is zero on both item sets
    pair = validity.round_pair(stored_cells, stored_sealed)
    assert pair["n_gen"] == len(sealed["g_acc"]) == 10 and pair["d_gen"] > 0 and pair["d_real"] > 0
    duplicate = validity.dup_control(stored_cells, stored_sealed)
    assert duplicate["pair"] == "S_dup-S" and duplicate["gen_ci95"] == duplicate["real_ci95"] == [0.0, 0.0]


# ------------------------------------------------------------------------------------------- ticket A9-1
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": "sha256:" + "0" * 64, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['B1'] = '=SUM(A1:A5)'\nbook.save('output.xlsx')\n```")
ERROR_REPORT = {"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Sheet2'"}
PASSED = {"status": "pass", "reason": "qualified_numeric_recalculation_hard_all_cases", "cleanup_confirmed": True,
          "metrics": {"cases": [{"status": "pass", "reason": "cell_values_match"}]}}
SHEET = procedure("p-spreadsheetbench-2-1", ("applies", "sheet_feedback"), evidence=EVIDENCE,
                  requests_second_call=True)
SHEET_HOOKS = {SHEET.id: {"sheet_feedback": lambda view, report, state: {
    "fields": {"warnings": ["The program raised %s on the public input." % report["exc_type"]]},
    "request_repair": report["status"] == "exception"}}}


def _delivered():
    book = openpyxl.Workbook()
    book.active["B1"] = 15
    buffer = io.BytesIO()
    book.save(buffer)
    return {"status": "available", "output_base64": base64.b64encode(buffer.getvalue()).decode(),
            "reason": "isolated_workbook_generated", "cleanup_confirmed": True}


class _Program:
    def __init__(self):
        self.requests = []

    def call(self, system, user):
        self.requests.append(json.loads(user))
        return reply(PROGRAM)


def test_a9_1_a_step_one_sheet_parent_cell_stores_its_precheck_and_feeds_the_sheet_feedback_sham(tmp_path,
                                                                                                  monkeypatch):
    native = FakeNative(report=ERROR_REPORT).install(monkeypatch)
    monkeypatch.setattr(backends, "_native", lambda request, runtime: _delivered())
    monkeypatch.setattr(backends, "score", lambda benchmark, public, private, prediction, *, runtime=None: dict(PASSED))
    item = spreadsheetbench_items(tmp_path / "items", 1)[0]
    parent = empty(step="s1", evidence=EVIDENCE)  # step 1: the parent holds no procedure (§5), nothing is enabled
    client = _Program()
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(tmp_path / "slots", "glm-5.3", 1),
                        sleep=lambda _: None)
    attempt = tmp_path / "run" / "attempt-1"
    ctx = Context(attempt=attempt, endpoint=endpoint, runtime={**RUNTIME, "spreadsheetbench": SHEET_RUNTIME},
                  cards={b: CARD for b in BENCHES}, native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                  episodes=Slots(tmp_path / "slots", "alfworld-episode", 1), worker=lambda bench: FakeSandbox(),
                  evidence=EVIDENCE)
    unit = "G/s1-spreadsheetbench/run"
    cell = {"id": cell_id(unit, "S", item["task_id"], 0), "unit": unit, "arm": "S", "benchmark": "spreadsheetbench",
            "task_id": item["task_id"], "run": 0}
    found = run_cell(ctx, cell, {"public": item["public"], "private": item["private"]}, Arm("parent", parent),
                     store=TrainingStore(attempt))
    # §2.5: the extracted program was pre-checked once although no sheet_feedback procedure is enabled; nothing read
    # the report in the cell (one logical call, no repair), and the stored trajectory carries it
    assert found["stop"] is None and found["final"]["token"] == "pass" and found["enabled"] == []
    assert len(native.prechecks) == 1 and [c["purpose"] for c in found["logical_calls"]] == ["first"]
    trajectory = verified(read_json(attempt / "trajectories" / (cell["id"] + ".json")), "trajectory")
    assert trajectory["arm_kind"] == "parent" and trajectory["shell"]["precheck"]["status"] == "exception"
    assert donors.donor_inputs(trajectory, bench="spreadsheetbench")["report"]["exc_type"] == "KeyError"
    # §6.1: a candidate's new sheet_feedback procedure on that donor's stored report is the P_y sham content
    candidate = with_(parent, step="s2", add=[SHEET])
    corpus = donors.donor_corpus(candidate, parent, [trajectory], sandboxes(SHEET_HOOKS))
    assert corpus["faults"] == [] and len(client.requests) == 1  # zero model calls
    assert donors.output(corpus, SHEET.id, cell["id"], "sheet_feedback") == {
        "warnings": ["The program raised KeyError on the public input."]}
