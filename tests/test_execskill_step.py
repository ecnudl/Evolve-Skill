"""T-STEP-1 and the per-chain ledger (implementation plan §1 step row, §7 fakes; registration §5.1-§5.8, §9.3;
ticket fixer-5). Offline and deterministic: chain G's solver is a FakeSolver behind the real glm-5.3 client and the
real ledger, every method role a FakeGLM behind the real ``Roles`` and the same ledger, the cells' procedures
FakeSandbox hooks, the engineer's checks, the detectors and the replays the real sandbox worker through FakeDocker, the
research sources FakeResearch; one worker thread and a tick clock that the acceptance's block gap advances.
Everything is an engineering fixture.

T-STEP-1: one OfficeQA step of chain G (k = 2, the default pilot order) on a parent whose procedures fire on every
run item, through the eight sub-steps of §5: the run unit with the card arm, the diagnosis with one sealed detector,
the researched generation (policy, research, G_self, band and shortcut probes, gates), one engineered change (the
item's customs receipts as a note), the self-test, the acceptance round and the freeze with the describer's text. It
checks that every model call was reserved and settled on chain G's own ledger, that every record is versioned, that
the consumption registry advanced (run slice and A* decided, the rest of A released), that the decision is made again
from the stored cell records alone, and that a finished step is read back without a model call.

Ticket PR-C12-1: chain G's SpreadsheetBench generate unit reaches the shortcut gate with probe cells run without the
workbook. Ticket C7e-1: an acceptance round's G_acc cells are charged to the examiner's scope, in a redone block too.
"""
from __future__ import annotations

import base64
import itertools
import json
import math
import re
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.coevo5 import ledger as frozen_ledger
from skillopt.coevo5.budget import Budget
from skillopt.coevo5.outcomes import AssumptionBroken, ConfigurationError
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (acceptance, budgets, chain, describer, engineer, examiner, fixtures, research, rounds,
                                slots, step, units)
from skillopt.execskill import protocol
from skillopt.execskill.cells import Pause
from skillopt.execskill.errors import CleanupUnconfirmed, SandboxUnavailable, stop_kind
from skillopt.execskill.client import GLM_SOLVER
from skillopt.execskill.generators import sheet
from skillopt.execskill.generators.families import generated_item
from skillopt.execskill.package import FIXTURE, empty
from skillopt.execskill.protocol import BENCHES, CELL_ANCHORS, NOTES_KEY, kind, verified
from skillopt.execskill.registry import Registry
from tests.execskill_fakes import FakeGLM, FakeSolver, engineer_reply, tagged
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_fakes_research import PAGES, SEARCHES, pick, query, sources, table
from tests.fixtures.execskill.items import livemath_items, officeqa_items, spreadsheetbench_items
from tests.test_execskill_examiner import PARAMS
from tests.test_execskill_integration_b3 import CARD, HOOKS, PARENT, canonical, key, sandboxes
from tests.test_execskill_integration_b4 import DESCRIPTION, YEARS, new
from tests.test_execskill_replay import fake, source, test_case, workers  # noqa: F401  (FakeDocker workers)
from tests.test_execskill_shortcut_sb import RIGHT as RIGHT_FORMULA, RUNTIMES, WRONG as WRONG_FORMULA
from tests.test_execskill_shortcut_sb import assert_no_workbook, containers, program, workbook

RUN, BENCH, CHAIN, K = "fixture-run", "officeqa", "G", 2
ITEMS = officeqa_items(120)[40:]  # pages 40-119: run slice 40-63, acceptance slice 64-113
NEW = "fx-officeqa-2-1"  # the engineer's procedure (chain step 2, the first change)
UNITS = ("run", "diagnose", "generate", "engineer", "selftest", "accept", "freeze")
POLICY = {"families": ["officeqa.percent_change"], "rationale": "Public finance tables.",
          "requests": [{"kind": "family_material", "family": "officeqa.percent_change",
                        "concept": "government revenue table", "topic": None}]}
DETECTOR = 'def detect(view):\n    return "ratio" in view["task"]["question"]\n'
CHANGE = "Lists the customs receipts of each year in the table."


def years(context):
    """The note of the engineer's YEARS procedure on a table (the same rows, the same text)."""
    rows = re.findall(r"^([0-9]+) [|] ([0-9]+) [|]", context, re.M)
    return "Customs receipts by year: " + "; ".join(y + " = " + c for y, c in rows) if rows else None


# the cells' procedures (FakeSandbox): the parent's two (B3) and the engineer's change, which writes the item's own
# customs receipts
HOOKS_STEP = {pid: HOOKS[pid] for pid in PARENT.order}
HOOKS_STEP[NEW] = {"applies": lambda view: "Year |" in view["context"],
                   "before_call": lambda view, state: ({"facts": [years(view["context"])]}
                                                       if years(view["context"]) else None)}


class Answers:
    """Chain G's fake solver (``answer(system, user)``): right when the notes carry the item's own customs receipts
    (the engineer's change on that item), else right on the items whose key is even -- the same reply in every arm and
    run. Generated items are known once ``examiner.build`` made them: the parent solves every second one (the band
    probe passes half). A request it does not know (a shortcut variant: no table) gets a wrong answer."""

    def __init__(self, items):
        self.answers = {key(item["public"]): item["private"]["answer"] for item in items}
        self.right = {}

    def add(self, generated):
        for n, item in enumerate(generated):
            found = key(item["public"])
            self.answers[found], self.right[found] = item["private"]["answer"], n % 2 == 0

    def __call__(self, system, user):
        view = json.loads(user)
        found = key(view)
        if found not in self.answers:
            return tagged("0")
        own = years(view["context"])
        right = (own is not None and own in view.get(NOTES_KEY, "")) or self.right.get(found, int(found, 16) % 2 == 0)
        return tagged(self.answers[found] if right else "0")


def roles_answer(system, payload):
    """The scripted GLM-5.3 roles, told apart by their pinned system prompts."""
    if system == examiner.DETECTOR_SYSTEM:
        return engineer_reply({"detectors": [{"description": "Ratio questions fail."}]}, [DETECTOR])
    if system == examiner.POLICY_SYSTEM:
        return POLICY
    if system == examiner.GENERATOR_SYSTEM:
        return {"specs": [{"family": "officeqa.percent_change", "material": payload["materials"][0]["id"],
                           "params": PARAMS}]}
    if system == research.QUERY_SYSTEM:
        return query("government revenue table")
    if system == research.PICK_SYSTEM:
        return pick("R1")
    if system in research.CONCLUDE_SYSTEM.values():
        return table("P1", 0)
    if system == engineer.ENGINEER_SYSTEM:
        if payload["request"] == "fix":  # resend the change unchanged
            change = dict(payload["change"])
            code = change.pop("source")
            return engineer_reply({"changes": [change]}, [code])
        failing = next(t["cell"] for t in payload["trajectories"] if t["kind"] == "failures")
        check = test_case(failing, "before_call", {"kind": "note_contains", "value": "Customs receipts by year"},
                          mutation="strip_digits")
        return engineer_reply({"changes": [new(CHANGE, check)]}, [source(YEARS)])
    if system == describer.DESCRIBER_SYSTEM:
        return DESCRIPTION
    return {"verdict": "no", "reason": "It names no reference answer."}  # the leakage adjudicator


def build(tmp_path, monkeypatch, workers_, *, answer=roles_answer, hooks=None):
    """(setting, services, FakeSolver, FakeGLM, the waits): chain G's setting on its own ledger and the step's
    services; the cells get the FakeSandbox procedures (``hooks``, default ``HOOKS_STEP``) and the tick clock."""
    hooks = hooks or HOOKS_STEP
    root = tmp_path / "root"
    answers = Answers(ITEMS)
    solver_fake = FakeSolver(tmp_path / "solver", [(None, answers)], model=GLM_SOLVER)
    glm = FakeGLM(tmp_path / "glm", answer)
    ledger = Budget(budgets.ledger_root(root, CHAIN), sleep=lambda _: None)
    ledger.declare(budgets.chain_caps(CHAIN))
    setting = units.Setting(
        run=RUN, root=root, shared=root / "shared", pools={BENCH: ITEMS}, cards={b: CARD for b in BENCHES},
        runtime=RUNTIME, clients=lambda model, bench: glm.client if bench is None else solver_fake.client,
        budget=ledger, slots=slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None), sandbox={},
        evidence=FIXTURE, workers=1, cooldown=0)
    ticks, waited = itertools.count(), []

    def clock():  # advanced by the dispatch's wait between OfficeQA's time blocks (§3.3)
        return float(next(ticks)) + sum(waited)

    real = units.cell_context

    def context(setting_, attempt, endpoint):
        found = real(setting_, attempt, endpoint)
        found.worker, found.clock = (lambda bench: FakeSandbox(hooks)), clock
        return found

    monkeypatch.setattr(units, "cell_context", context)
    monkeypatch.setattr(rounds, "cell_context", context)
    made = examiner.build

    def known(*args, **kwargs):  # the fake solver learns the generated items' answers
        found = made(*args, **kwargs)
        answers.add(found.items)
        return found

    monkeypatch.setattr(examiner, "build", known)
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", 4)  # the four-item fixture sets' band probe (Codex finding #9)
    services = step.Services(registry=Registry(tmp_path / "history", evidence=FIXTURE),
                             sources=sources(tmp_path / "research")[0], workers=workers_,
                             item_workers=sandboxes(hooks), clock=clock, sleep=waited.append)
    return setting, services, solver_fake, glm, waited


def result(step_root, name):
    return verified(read_json(step_root / name / "unit.json"), "unit")


# --------------------------------------------------------------------------------------------------- T-STEP-1
def test_step1_one_fake_officeqa_step_through_the_eight_sub_steps(tmp_path, monkeypatch, workers):
    setting, services, solver_fake, glm, waited = build(tmp_path, monkeypatch, workers)
    found = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    root = setting.root
    step_root = root / CHAIN / ("s%d-%s" % (K, BENCH))

    # the step record: accepted; S' with the describer's frozen text passes on
    record = verified(read_json(step_root / step.STEP_FILE), "step")
    assert found.record == record and record["version"] == kind("step") and record["evidence"] == FIXTURE
    assert record["decision"] == "accept" and record["reason"] == "J1-J7 hold"
    assert found.package.order == PARENT.order + (NEW,) and NEW in found.package.describer
    assert record["package_sha256"] == found.package.sha256 != record["candidate_sha256"]
    assert record["fault_items"] == record["violating_items"] == 0
    assert set(record["units"]) == set(UNITS)  # no second engineer or self-test: the first self-test passed
    assert all(result(step_root, name)["record_sha256"] == sha for name, sha in record["units"].items())

    # 5.1 run: S twice and the card arm once on the 24 run items (S's procedures fire on every item)
    slices = verified(read_json(step_root / step.SLICES_FILE), "step-slices")["slices"]
    assert slices == {"run": [i["task_id"] for i in ITEMS[:24]], "accept": [i["task_id"] for i in ITEMS[24:74]]}
    run = result(step_root, "run")["result"]
    assert run["cells"] == 24 * 2 + 24 and run["firing_share"] == 1.0
    assert run["entry_reading"] == {"items": 24, "mean_s_minus_c": 0.0, "decides": False}
    # 5.2 diagnose: one candidate sealed before the hold half was read, validated (too few alarms)
    diagnosed = result(step_root, "diagnose")
    assert diagnosed["result"]["written"]["candidates_sha256"] is not None
    assert (step_root / "diagnose" / diagnosed["attempt"] / "candidates.json").exists()
    assert [d["validation"]["accepted"] for d in diagnosed["result"]["detectors"]] == [False]
    # 5.3 generate: researched material split by seed, four items in band, no shortcut, admitted
    generated = result(step_root, "generate")
    made = generated["result"]
    assert (step_root / "generate" / generated["attempt"] / "research-split.json").exists()
    assert len(made["split"]["g_self"]) == 1 and made["split"]["g_acc"] == []
    assert made["generator"]["status"] == "admitted" and len(made["g_self"]) == 4
    assert made["gates"]["band"]["pass_rate"] == 0.5 and made["gates"]["shortcut"]["dropped"] == []
    # 5.4 engineer: the one change survived C1-C9
    engineered = result(step_root, "engineer")["result"]
    assert engineered["candidate_sha256"] == record["candidate_sha256"]
    assert [c["survived"] for c in engineered["engineer"]["changes"]] == [True]
    # 5.5 self-test: S' and S once on G_self, not blocked; the parent's year-column procedure faults on the generated
    # tables in both arms (no "page" line): reported, never charged to the change
    tested = result(step_root, "selftest")["result"]
    assert tested["cells"] == 8 and not tested["blocked"] and tested["fault_share"] == 0.0
    assert tested["inherited_fault_cells"] == 4
    assert tested["sets"][BENCH]["items"] == 4 and tested["sets"][BENCH]["format_gap"] == 0.0
    # 5.6 accept: the round ran with the duplicate arm and waited out the block gap once
    accepted = result(step_root, "accept")
    assert accepted["result"]["decision"] == "accept" and accepted["result"]["dup"] and len(waited) == 1
    # 5.7 freeze: one description, of the new procedure only
    frozen = result(step_root, "freeze")["result"]
    assert frozen["accepted"] and [d["procedure"] for d in frozen["descriptions"]] == [NEW]
    assert frozen["package_sha256"] == found.package.sha256

    # the decision again from the stored cell records and the stored sealed record alone
    attempt = step_root / "accept" / accepted["attempt"]
    cells = [verified(read_json(path), "cell") for path in sorted((attempt / "cells").glob("*.json"))]
    sealed = verified(read_json(step_root / "accept" / "sealed.json"), "acceptance-sealed")
    stored = verified(read_json(attempt / "decision" / "decision.json"), "decision")
    again = acceptance.decide(cells, sealed)
    assert canonical(again) == canonical(stored) and again["record_sha256"] == record["decision_sha256"]
    assert len(cells) == accepted["result"]["cells"] and sealed["freshness"] == step.FRESHNESS

    # the consumption registry: the run slice and A* decided, the rest of A back in the supply
    lines = services.registry.entries(CHAIN, BENCH)
    astar = set(sealed["plan"]["astar"])
    assert set(lines) == set(slices["run"]) | set(slices["accept"]) and len(astar) >= 30
    assert all(lines[i]["state"] == "decided" and lines[i]["unit"] == "G/s2-officeqa/run" for i in slices["run"])
    assert all(lines[i]["state"] == ("decided" if i in astar else "routed_not_dispatched")
               and lines[i]["unit"] == "G/s2-officeqa/accept" for i in slices["accept"])

    # chain G's own ledger: every model call reserved and settled, nothing open, nothing halted or refused
    ledger_root = budgets.ledger_root(root, CHAIN)
    events = [json.loads(line) for line in (ledger_root / "events.jsonl").read_text().splitlines()]
    reserved = {e["id"]: e for e in events if e["event"] == "reserve"}
    settled = [e for e in events if e["event"] == "settle"]
    assert reserved and set(reserved) == {e["id"] for e in settled} and len(settled) == len(reserved)
    assert not [e for e in events if e["event"] in ("halt", "refuse")]
    assert all(entry["open"] == 0 for entry in setting.budget.snapshot().values())
    assert sum("G:solver" in e["scopes"] for e in settled) == len(solver_fake.requests)
    assert sum("G:glm" in e["scopes"] for e in settled) == len(glm.seen)
    charged = {scope for e in settled for scope in e["scopes"]}
    prefix = "G:xs:officeqa:2:"
    assert {prefix + s for s in ("run", "examiner", "selftest", "accept", "role:engineer", "role:examiner",
                                 "role:examiner:research")} <= charged
    assert not any(scope.startswith("D:") for scope in charged) and not budgets.ledger_root(root, "D").exists()

    # registrar addendum 15:5x R5: every role call once, in its unit's role-calls.jsonl (no receipt, no ledger figure)
    logs = {name: step_root / name / step.ROLE_CALLS for name in UNITS if (step_root / name / step.ROLE_CALLS).exists()}
    rows = {name: [json.loads(line) for line in path.read_text().splitlines()] for name, path in logs.items()}
    assert {"diagnose", "generate", "engineer", "freeze"} <= set(logs)
    assert sum(len(found) for found in rows.values()) == len(glm.seen)
    keys = {"attempt", "role", "label", "request_sha256", "valid", "reason", "reply", "adjudicator_reason"}
    assert all(set(row) <= keys and type(row["reply"]) is str and row["attempt"] == 1
               for found in rows.values() for row in found)
    assert "engineer" in {row["role"] for row in rows["engineer"]} and rows["freeze"][0]["role"] == "describer"
    logged = {name: path.read_text() for name, path in logs.items()}

    # every record the step wrote is versioned and labelled (artifacts are content-addressed values, not records)
    checked = 0
    for path in sorted((root / CHAIN).rglob("*.json")):
        if {"artifacts", "host_only"} & set(path.relative_to(root).parts):
            continue
        value = read_json(path)
        assert value["version"].startswith("fivebench-execskill-v1-") and value["evidence"] == FIXTURE, path
        checked += 1
    assert checked > len(cells)

    # a finished step is read back: no model call, the same record and package
    calls = (len(solver_fake.requests), len(glm.seen))
    again_step = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    assert again_step.record == record and again_step.package.sha256 == found.package.sha256
    assert (len(solver_fake.requests), len(glm.seen)) == calls
    assert {name: path.read_text() for name, path in logs.items()} == logged  # written once: nothing appended
    with pytest.raises(ValueError, match="another parent"):
        step.run_step(setting, CHAIN, BENCH, K, empty(step="G/s1", evidence=FIXTURE), services=services)


# ------------------------------------------------------------------------------- steps ending before the acceptance
def no_change(system, payload):
    """The roles of ``roles_answer``, but the engineer proposes nothing."""
    if system == engineer.ENGINEER_SYSTEM:
        return engineer_reply({"changes": []}, [])
    return roles_answer(system, payload)


def _real_pages_only(view):
    """The change's routing on the fixture's pages; it raises on any other table (the generated ones)."""
    if "Fixture bulletin page" not in view["context"]:
        raise ValueError("not a fixture page")
    return "Year |" in view["context"]


@pytest.mark.parametrize("variant", ["no_change", "blocked_twice"])
def test_a_step_ending_before_the_acceptance_consumes_no_acceptance_item(tmp_path, monkeypatch, workers, variant):
    hooks = dict(HOOKS_STEP, **{NEW: dict(HOOKS_STEP[NEW], applies=_real_pages_only)})
    setting, services, solver_fake, glm, waited = build(
        tmp_path, monkeypatch, workers, answer=no_change if variant == "no_change" else roles_answer,
        hooks=hooks if variant == "blocked_twice" else None)
    found = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    step_root = setting.root / CHAIN / ("s%d-%s" % (K, BENCH))
    record = found.record
    assert record["decision"] == "not_run" and found.package.sha256 == PARENT.sha256 == record["package_sha256"]
    assert record["decision_sha256"] is None and not (step_root / "accept").exists() and not waited
    lines = services.registry.entries(CHAIN, BENCH)  # the run slice decided; the acceptance slice never registered
    slices = verified(read_json(step_root / step.SLICES_FILE), "step-slices")["slices"]
    assert set(lines) == set(slices["run"]) and all(line["state"] == "decided" for line in lines.values())
    frozen = result(step_root, "freeze")["result"]
    assert not frozen["accepted"] and frozen["descriptions"] == [] and frozen["archived"] == record["candidate_sha256"]
    if variant == "no_change":
        assert record["reason"] == "no_surviving_change" and record["candidate_sha256"] is None
        assert set(record["units"]) == {"run", "diagnose", "generate", "engineer", "freeze"}
    else:  # the change faults on every generated item in S': blocked, re-engineered once, blocked again
        assert record["reason"] == "selftest_blocked_twice" and record["candidate_sha256"] is not None
        assert set(record["units"]) == set(UNITS) - {"accept"} | {"engineer-2", "selftest-2"}
        for name in ("selftest", "selftest-2"):
            tested = result(step_root, name)["result"]
            assert tested["blocked"] and tested["fault_blocks"] and tested["fault_cells"] == 4
        first, second = (result(step_root, name)["result"]["engineer"] for name in ("engineer", "engineer-2"))
        assert second["earlier_calls"] == first["calls"] >= 1  # R7a: one engineer-call count for the step
        assert first["calls"] + second["calls"] <= engineer.ENGINEER_CALLS
        previous = [payload["previous"] for system, payload in glm.seen
                    if system == engineer.ENGINEER_SYSTEM and payload["request"] == "propose"]
        assert previous == [None, {"decision": "not_accepted", "faults": {"selftest_fault_cells": 4},
                                   "format": {BENCH: {"worse_items": 0}}}]


# ------------------------------------------------------------------------------------------- self-test verdict
def _cell(arm, item, *, violation=False, token="pass", faults=()):
    return {"cell": {"arm": arm, "task_id": item}, "faults": list(faults),
            "judge": {"format": {"violation": violation}, "v2": {"token": token}}}


def test_selftest_blocks_only_on_faults_and_a_significant_format_regression():
    items, changed = ["g%d" % n for n in range(20)], {NEW}
    clean = [_cell(arm, i) for i in items for arm in ("S'", "S")]
    verdict = step.selftest_verdict(clean, {BENCH: items}, changed)
    assert not verdict["blocked"] and verdict["sets"][BENCH]["accuracy"] == {"S'": 1.0, "S": 1.0}
    # accuracy never blocks
    wrong = [_cell("S'", i, token="fail") for i in items] + [_cell("S", i) for i in items]
    assert not step.selftest_verdict(wrong, {BENCH: items}, changed)["blocked"]
    # one S' cell in 20 with a fault of the change is 5 % > 2 %: blocks; an inherited procedure's fault does not
    for pid, blocks in ((NEW, True), ("p-officeqa-1-2", False)):
        faulted = [_cell("S'", i, faults=[{"kind": "exception", "procedure": pid}] if i == "g0" else ())
                   for i in items] + [_cell("S", i) for i in items]
        verdict = step.selftest_verdict(faulted, {BENCH: items}, changed)
        assert verdict["fault_blocks"] is blocks and verdict["inherited_fault_cells"] == (0 if blocks else 1)
    # five items newly format-violating (25 points, sign test p = 1/32): blocks; one item (5 points, p = 1/2) does not
    for worse, blocks in ((5, True), (1, False)):
        cells = [_cell("S'", i, violation=n < worse) for n, i in enumerate(items)] + [_cell("S", i) for i in items]
        row = step.selftest_verdict(cells, {BENCH: items}, changed)["sets"][BENCH]
        assert row["worse"] == worse and row["blocks"] is blocks and row["p_sign"] == 0.5 ** worse


# ------------------------------------------------------------------------------------------- cost projection
def test_cost_projection_rescales_chain_g_caps_by_the_measured_cost_per_cell(tmp_path):
    ledger = Budget(budgets.ledger_root(tmp_path, "G"), sleep=lambda _: None)
    ledger.declare({**budgets.chain_caps("G"), **budgets.first_call_caps("G")})  # as chain.run declares it
    setting = SimpleNamespace(budget=ledger)
    high = CELL_ANCHORS["spreadsheetbench"][1]
    scopes = budgets.solver_scopes("G", "spreadsheetbench", 1, "run")
    for charged in (high, high):  # two cells at the registered high anchor
        rid = ledger.reserve(scopes, high, label="cell", generation=ledger.generation())
        ledger.settle(rid, charged, detail={})
    found = step.cost_projection(setting, "G", "spreadsheetbench", 1, 2)
    assert found["ok"] and found["per_cell"] == high and found["anchor_high"] == high
    assert all(row["projected"] == math.ceil(row["cap"] / Fraction(3, 2)) for row in found["scopes"].values())
    assert "G:solver" in found["scopes"] and not any(s == "G:glm" or ":role:" in s for s in found["scopes"])
    assert "G:confirm" not in found["scopes"]  # the first-call confirmation (addendum 14:10, row 7): spent
    rid = ledger.reserve(scopes, 3 * high, label="cell", generation=ledger.generation())
    ledger.settle(rid, 3 * high, detail={})  # three cells now average 5/3 of the anchor: above 1.5 x, a breach
    breach = step.cost_projection(setting, "G", "spreadsheetbench", 1, 3)
    assert not breach["ok"] and all(row["projected"] > row["cap"] for row in breach["scopes"].values())
    # registrar addendum 15:5x R6 (e): after a redone run unit, the completing attempt's own spend and cells
    redo = budgets.solver_scopes("G", "spreadsheetbench", 1, "run", 2)
    rid = ledger.reserve(redo, high, label="redo cell", generation=ledger.generation())
    ledger.settle(rid, high // 2, detail={})  # one redo cell at half the anchor; the first attempt's 5 x high aside
    again = step.cost_projection(setting, "G", "spreadsheetbench", 1, 1, attempt=2)
    assert again["ok"] and again["per_cell"] == high // 2


# ------------------------------------------------------------------------- registrar addendum 15:5x R5
def test_r5_role_calls_appends_each_attempts_role_calls_once_without_receipts(tmp_path):
    unit = tmp_path / "G" / "s1-officeqa" / "engineer"
    unit.mkdir(parents=True)

    def sent(text):
        return {"request_sha256": "0" * 64, "reserved": 70000, "charged": 1200,
                "receipt": {"ok": True, "response": text, "usage": {"total_tokens": 1200}}}

    verdict = '{"verdict": "no", "reason": "general advice, no answer"}'
    made = [SimpleNamespace(calls=[
        {"role": "engineer", "label": "engineer/G/s1-officeqa/engineer/propose", "request_sha256": "a" * 64,
         "valid": True, "reason": None, "sends": [sent("a proposal")]},
        {"role": "leak_adjudicate", "label": "leak/G/s1-officeqa/engineer/p-1", "request_sha256": "b" * 64,
         "valid": True, "reason": None, "sends": [sent("not json"), sent(verdict)]},
        {"role": "engineer", "label": "engineer/G/s1-officeqa/engineer/fix/1", "request_sha256": "c" * 64,
         "valid": False, "reason": "no_reply:timeout", "sends": [{"request_sha256": "c" * 64, "refused": "cap"}]}])]
    step.role_calls(unit, unit / "attempt-1", made)
    step.role_calls(unit, unit / "attempt-2", [])  # no role call: nothing written
    step.role_calls(unit, unit / "attempt-2", [SimpleNamespace(calls=made[0].calls[:1])])
    text = (unit / step.ROLE_CALLS).read_text()
    rows = [json.loads(line) for line in text.splitlines()]
    assert [(r["attempt"], r["request_sha256"][0], r["reply"]) for r in rows] == [
        (1, "a", "a proposal"), (1, "b", verdict), (1, "c", None), (2, "a", "a proposal")]
    assert rows[1]["adjudicator_reason"] == "general advice, no answer" and "adjudicator_reason" not in rows[0]
    assert rows[2]["valid"] is False and rows[2]["reason"] == "no_reply:timeout"
    assert not any(word in text for word in ("charged", "reserved", "usage", "receipt"))


# ------------------------------------------------------------------------- registrar addendum 15:5x R1
def test_r1_spreadsheetbench_references_are_the_answer_cells_as_the_frozen_scorer_reads_them(tmp_path):
    """§4.2: the engineer sees the references of failed run items on every bench but ALFWorld; on SpreadsheetBench the
    answer-position values of the item's (first) answer workbook, read as ``spreadsheet_compat.evaluate`` reads a
    reference, in the table shape ``engineer._answer_shape`` takes."""
    from openpyxl import Workbook

    items = spreadsheetbench_items(tmp_path / "items", 2)  # the answer puts the sum of A1:A5 into B1
    parents = [{"task_id": rounds.key("spreadsheetbench", items[0]["task_id"]), "token": "fail"},
               {"task_id": rounds.key("spreadsheetbench", items[1]["task_id"]), "token": "pass"}]
    found = step._references(SimpleNamespace(bench="spreadsheetbench"), {"run": items}, parents)
    assert found == {parents[0]["task_id"]: {"Sheet!B1": 15}} and engineer._answer_shape(found[parents[0]["task_id"]])

    def answer(name, cells):
        book = Workbook()
        for coordinate, value in cells.items():
            book.active[coordinate] = value
        book.save(tmp_path / name)
        return str(tmp_path / name)

    mixed = answer("mixed.xlsx", {"A1": 1.5, "B1": "x", "A2": True, "C9": 3})
    assert step._sheet_reference({"test_files": [mixed], "answer_position": "A1:B2"}) == {
        "Sheet!A1": 1.5, "Sheet!B1": "x", "Sheet!A2": "TRUE", "Sheet!B2": ""}  # an empty cell is ""
    assert step._sheet_reference({"test_files": [mixed], "answer_position": "'Sheet'!C9"}) == {"Sheet!C9": 3}
    uncached = answer("formula.xlsx", {"A1": 1, "B1": "=A1*2"})  # openpyxl writes no cached value
    assert step._sheet_reference({"test_files": [uncached], "answer_position": "B1"}) is None
    assert step._sheet_reference({"test_files": [mixed], "answer_position": "Other!A1"}) is None  # no such sheet
    assert step._sheet_reference({"test_files": [str(tmp_path / "missing.xlsx")], "answer_position": "B1"}) is None
    assert step._references(SimpleNamespace(bench="alfworld"), {"run": items}, parents) == {}


# ------------------------------------------------------------------------- registrar addendum 15:5x R2
def test_r2_every_stored_spreadsheetbench_trajectory_mounts_its_own_workbook_at_any_step(tmp_path):
    """C6/C7 at a later (OfficeQA) step replay a procedure in SpreadsheetBench's scope on the earlier SpreadsheetBench
    step's stored trajectories: each gets its own item's public workbook as /input, whatever this step's bench."""
    items = spreadsheetbench_items(tmp_path / "items", 3)
    st = SimpleNamespace(bench="officeqa", setting=SimpleNamespace(pools={"spreadsheetbench": items}))
    stored = [{"bench": "spreadsheetbench", "task_id": rounds.key("spreadsheetbench", item["task_id"]),
               "cell": "G/s1-spreadsheetbench/run:%d" % n} for n, item in enumerate(items[:2])] + [
        {"bench": "officeqa", "task_id": rounds.key("officeqa", "oq-1"), "cell": "oq"}]  # trajectories' item keys
    with step._inputs_dirs(st, stored, {"run": []}) as found:
        assert sorted(found) == [t["cell"] for t in stored[:2]]
        for n, directory in enumerate(found[t["cell"]] for t in stored[:2]):
            assert (Path(directory) / "input.xlsx").read_bytes() == Path(items[n]["public"]["input_files"][0]) \
                .read_bytes()
        made = list(found.values())
    assert not any(Path(directory).exists() for directory in made)  # removed afterwards
    with step._inputs_dirs(st, stored[2:], {"run": []}) as found:
        assert found is None  # no SpreadsheetBench trajectory: nothing mounted
    st.setting.pools = {}
    with pytest.raises(ValueError, match="known item"):
        with step._inputs_dirs(st, stored, {"run": []}):
            pass
    sheet_step = SimpleNamespace(bench="spreadsheetbench", setting=SimpleNamespace(pools={}))
    with step._inputs_dirs(sheet_step, stored, {"run": items[:2]}) as found:  # this step's run slice (smoke cuts)
        assert sorted(found) == [t["cell"] for t in stored[:2]]


# ------------------------------------------------------------------------------------------- ticket fixer-5
def _endpoint_setting(root, ledger):
    return units.Setting(run=RUN, root=root, shared=root / "shared", pools={}, cards={}, runtime={}, clients=None,
                         budget=ledger, slots={GLM_SOLVER: object()}, sandbox={}, evidence=FIXTURE, cooldown=0)


def test_fixer5_each_chain_has_its_own_ledger_and_a_halt_stops_that_chain_only(tmp_path):
    root = tmp_path / "root"
    assert budgets.ledger_root(root, "G") == root / "shared" / "ledger-G"
    assert budgets.ledger_root(root, "D") == root / "shared" / "ledger-D"
    assert budgets.ledger_root(root, "smoke") == root / "shared" / "ledger"  # the smoke keeps one ledger
    ledgers = {c: Budget(budgets.ledger_root(root, c), sleep=lambda _: None) for c in ("G", "D")}
    for name, ledger in ledgers.items():
        ledger.declare(budgets.chain_caps(name))
        assert set(ledger.snapshot()) == set(budgets.chain_caps(name))
        assert all(s == budgets.ROOT or s.startswith(name + ":") for s in ledger.snapshot())

    def charge(name, *, breach=None):
        ledger = ledgers[name]
        rid = ledger.reserve(budgets.solver_scopes(name, BENCH, 2, "run"), 1000, label=name,
                             generation=ledger.generation())
        ledger.settle(rid, 2000 if breach else 10, detail={}, breach=breach)

    for halted, other in (("G", "D"), ("D", "G")):  # a completion above B halts its own chain, never the other
        charge(halted, breach="completion_above_bound")
        with pytest.raises(AssumptionBroken):
            charge(halted)
        charge(other)
        ledgers[halted].resume(decision="fixture: the owner resumes after the breach")
        charge(halted)

    # the other chain's scopes are not declared on a chain's ledger: refused before anything is sent
    setting = _endpoint_setting(root, ledgers["G"])
    client = SimpleNamespace(model=GLM_SOLVER, max_tokens=100)
    with pytest.raises(ConfigurationError, match="Undeclared"):
        budgets.endpoint(setting, budgets.solver_scopes("D", BENCH, 2, "run"), client=client, max_tokens_bound=100)
    assert budgets.endpoint(setting, budgets.solver_scopes("G", BENCH, 2, "run"), client=client,
                            max_tokens_bound=100) is not None
    # a chain refuses any ledger but its own: the other chain's or the shared one
    assert budgets.own_ledger(setting, "G") is ledgers["G"]
    shared = Budget(budgets.ledger_root(root, "smoke"), sleep=lambda _: None)
    for wrong in (ledgers["D"], shared, None):
        with pytest.raises(ConfigurationError, match="own ledger"):
            budgets.own_ledger(replace(setting, budget=wrong), "G")
    with pytest.raises(ConfigurationError, match="own ledger"):
        chain.run(replace(setting, budget=shared), "G", learn=lambda *args: pytest.fail("no step runs"))
    # the manifest's listing still names both chains' caps, overall their sum
    listing = budgets.caps()
    assert listing[budgets.ROOT] == sum(budgets.chain_caps(c)[budgets.ROOT] for c in ("G", "D"))
    assert all(listing[s] == cap for c in ("G", "D") for s, cap in budgets.chain_caps(c).items() if s != budgets.ROOT)


# ----------------------------------------------------------------------------------------------- ticket C1-3
def test_c1_3_sheet_generator_sources_are_run_slice_items_and_its_g_acc_is_not_evaluable():
    """Ticket C1-3 (registrar decision): a SpreadsheetBench spec edits a source task of the current step's run slice
    only; there is no SpreadsheetBench G_acc in v1, so its acceptance result discloses the validity as not
    evaluable instead of a G_acc rate."""
    cut = {"run": [{"task_id": "r-1"}, {"task_id": "r-2"}], "accept": [{"task_id": "a-1"}],
           "selection": [{"task_id": "s-1"}]}
    assert step._sources(cut, "spreadsheetbench") == {"r-1": cut["run"][0], "r-2": cut["run"][1]}
    assert step._sources(cut, "officeqa") is None
    admitted = {"generator": {"status": "admitted", "specs": [{"family": "sheet-family"}]},
                "split": {"g_acc": {"m-1": {"kind": "workbook"}}}, "numbered": 0}
    assert step._g_acc(SimpleNamespace(bench="spreadsheetbench"), admitted, None) is None
    assert step.SHEET_VALIDITY == {"status": "not_evaluable",
                                   "reason": "no SpreadsheetBench G_acc in v1 (registrar decision, C1-3)"}


def test_the_s4_mini_step_is_the_smokes_searchqa_step_1_with_a_candidate_of_the_empty_parent():
    """§10 S4 (C7b2-1): ``run_step(..., smoke=SmokeStep)`` refuses anything but chain "smoke", SearchQA, k = 1, an
    empty parent and a candidate whose parent it is -- before a unit, a model call or a registration."""
    parent = empty(step="smoke/s0", evidence="smoke")
    x = fixtures.fixture_package()
    good = step.SmokeStep(items=(), candidate=replace(x, parent_sha256=parent.sha256))
    for args, mini in ((("smoke", "searchqa", 1, parent), step.SmokeStep(items=(), candidate=x)),
                       (("smoke", "officeqa", 1, parent), good), (("D", "searchqa", 1, parent), good),
                       (("smoke", "searchqa", 2, parent), good), (("smoke", "searchqa", 1, x), good)):
        with pytest.raises(ValueError, match="S4 mini-step"):
            step.run_step(None, *args, services=None, smoke=mini)


# ----------------------------------------------------------------------------------------------- ticket C7c-2
class _Down(FakeSandbox):
    """A sandbox that is gone: its first call raises ``SandboxUnavailable`` (P4: the cell stops, the unit pauses)."""

    def call(self, proc_id, fn, args, *, timeout_s):
        raise SandboxUnavailable("sandbox_unavailable: the test's stop inside block 2")


def _pause(monkeypatch, at):
    """``acceptance.runner`` with a stop in attempt 1 (ticket C7c-2): in a block where ``at(block, jobs)`` names a job,
    the jobs before it run, then that job's cell meets a gone sandbox (``_Down``) -- its record is stored and the unit
    pauses. Every other block, and every later attempt, runs as the step's runner does."""
    real = acceptance.runner

    def runner(context, sealed, packages, tasks, *, workers, store, **options):
        run = real(context, sealed, packages, tasks, workers=workers, store=store, **options)
        if context.attempt.name != "attempt-1":
            return run

        def stopping(block, jobs):
            stop = at(block, jobs)
            if stop is None:
                return run(block, jobs)
            run(block, jobs[:stop])
            down = real(replace(context, worker=lambda bench: _Down(HOOKS_STEP)), sealed, packages, tasks,
                        workers=workers, store=store, **options)
            return down(block, [jobs[stop]])  # the stopped cell's record is stored, then the unit pauses

        return stopping

    monkeypatch.setattr(acceptance, "runner", runner)


def test_c7e_a_paused_acceptance_redoes_one_block_on_its_own_sub_scope(tmp_path, monkeypatch, workers):
    """Ticket C7c-2 (registration §9.3: a pause redoes only one block, each redo in its own sub-scope; owner decision
    #15: the block is redone whole, never spliced). The OfficeQA round, cut into three blocks for the test, pauses on
    a sandbox stop inside block 2. After the owner's recovery.json the same step keeps block 1 from attempt 1, redoes
    block 2 whole on chain G's ``...:accept:attempt-2`` and redo reserve, and runs block 3 -- never started -- on
    ``...:accept``; the decision reads the union by its block -> attempt map and is made again from the records."""
    monkeypatch.setitem(step.SLICES[BENCH], "blocks", 3)
    setting, services, solver_fake, glm, waited = build(tmp_path, monkeypatch, workers)

    def middle(block, jobs):  # attempt 1: block 2 stops at its first real S' cell past the middle
        if block != "b2":
            return None
        return next(n for n, job in enumerate(jobs)
                    if job["arm"] == "S'" and job["set"] == "real" and n >= len(jobs) // 2)

    _pause(monkeypatch, middle)
    with pytest.raises(Pause) as stop:
        step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    step_root = setting.root / CHAIN / ("s%d-%s" % (K, BENCH))
    accept_root = step_root / "accept"
    status = verified(read_json(accept_root / "attempt-1" / "status.json"), "unit-status")
    assert stop.value.kind == status["kind"] == "sandbox" and len(waited) == 1  # block 1, the gap, part of block 2
    write_json(accept_root / "attempt-1" / "recovery.json",
               {"by": "owner", "date": "2026-10-22", "decision": "fixture: redo the paused block (ticket C7c-2)"})
    found = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    accepted = result(step_root, "accept")
    assert accepted["attempt"] == "attempt-2" and found.record["decision"] in ("accept", "reject")
    assert accepted["result"]["reused"] == {"b1": "attempt-1"} and accepted["result"]["redone"] == ["b2"]
    assert accepted["result"]["provenance"] == {"b1": "attempt-1", "b2": "attempt-2", "b3": "attempt-2"}
    assert len(waited) == 2  # attempt 2 waits the gap before block 3; block 1 finished more than 2 h before block 2

    def stored(attempt):
        return [verified(read_json(p), "cell") for p in sorted((accept_root / attempt / "cells").glob("*.json"))]

    first, second = stored("attempt-1"), stored("attempt-2")
    assert {c["cell"]["block"] for c in first} == {"b1", "b2"} and {c["cell"]["block"] for c in second} == {"b2", "b3"}
    assert any(c["stop"] is not None and c["cell"]["block"] == "b2" for c in first)
    sealed = verified(read_json(accept_root / "sealed.json"), "acceptance-sealed")
    decision = verified(read_json(accept_root / "attempt-2" / "decision" / "decision.json"), "decision")
    union = acceptance.round_cells(accept_root, sealed, decision)
    assert len(union) == accepted["result"]["cells"] == sum(len(jobs) for jobs in acceptance.schedule(sealed).values())
    assert {acceptance.unit_attempt(c) for c in union if c["cell"]["block"] == "b2"} == {"attempt-2"}
    assert acceptance.reproduce(union, sealed, decision)
    assert canonical(acceptance.decide(union, sealed)) == canonical(decision)

    # chain G's ledger: the attempt-2 sub-scope and the redo reserve hold block 2's sends only, the kind's scope
    # attempt 1's sends and block 3's; block 1 is charged nowhere in attempt 2
    events = [json.loads(line) for line in (budgets.ledger_root(setting.root, CHAIN) / "events.jsonl").read_text()
              .splitlines()]
    settled = [e for e in events if e["event"] == "settle"]
    scope = "G:xs:officeqa:2:accept"

    def charged(name):
        return sum(name in e["scopes"] for e in settled)

    def sends(cells, blocks):
        return sum(len(c["sends"]) for c in cells if c["cell"]["block"] in blocks)

    assert charged(scope + ":attempt-2") == charged("G:redo") == sends(second, {"b2"}) > 0
    assert charged(scope) == sends(first, {"b1", "b2"}) + sends(second, {"b3"})
    snapshot = setting.budget.snapshot()
    assert snapshot[scope + ":attempt-2"]["settled"] > 0 and snapshot[scope + ":attempt-3"]["settled"] == 0
    assert all(entry["open"] == 0 for entry in snapshot.values())


# ----------------------------------------------------------------------------------------------- ticket C7e-1
SECOND = "Public finance"  # a second researched page: the research split gives G_acc a table of its own (§7.2)
SECOND_TABLE = (
    "<p>Public finance studies government revenue.</p>"
    "<table><caption>Receipts by year, revised (billions)</caption>"
    "<tr><th>Year</th><th>Income tax</th><th>Customs</th><th>Total</th></tr>"
    "<tr><td>2019</td><td>1,702</td><td>73</td><td>1,775</td></tr>"
    "<tr><td>2020</td><td>1,596</td><td>69</td><td>1,665</td></tr>"
    "<tr><td>2021</td><td>2,032</td><td>84</td><td>2,116</td></tr></table>")
CONCEPTS = ("government revenue table", "public finance table")


def two_tables(system, payload):
    """The roles of ``roles_answer``, but the policy asks for two tables and each query finds its own page: the
    research split deals one to G_self and one to G_acc, so the acceptance round has G_acc items."""
    if system == examiner.POLICY_SYSTEM:
        return {**POLICY, "requests": [dict(POLICY["requests"][0], concept=concept) for concept in CONCEPTS]}
    if system == research.QUERY_SYSTEM:
        return query(CONCEPTS[1] if "public finance" in json.dumps(payload) else CONCEPTS[0])
    return roles_answer(system, payload)


def test_c7e_1_the_g_acc_cells_are_charged_to_the_examiners_scope_in_a_redone_block_too(tmp_path, monkeypatch,
                                                                                          workers):
    """Ticket C7e-1 (registration §3.3 "它的做题费用记在考官作用域里（9.2、9.3）", §9.2, calc T6; registrar decision
    2026-10-22): an OfficeQA round with G_acc items (two researched tables), cut into three blocks, pauses inside the
    first block holding G_acc jobs after one of them ran. Every G_acc send -- in attempt 1 and in the redone block of
    attempt 2 -- is charged to chain G's ``...:examiner`` scope and to nothing else of the step; ``...:accept``, its
    ``attempt-2`` sub-scope and the redo reserve hold the round's other cells as ticket C7c-2 has them. The stored
    decision carries §6.2's descriptive series of both sets (ticket PR-F2-1)."""
    monkeypatch.setitem(step.SLICES[BENCH], "blocks", 3)
    monkeypatch.setitem(PAGES, SECOND, (SECOND, 1007, SECOND_TABLE, [], False))
    monkeypatch.setitem(SEARCHES, CONCEPTS[1], [SECOND])
    setting, services, solver_fake, glm, waited = build(tmp_path, monkeypatch, workers, answer=two_tables)
    chosen = []

    def after_g_acc(block, jobs):  # attempt 1: the first block with G_acc jobs stops at a real S' job after one
        first = next((n for n, job in enumerate(jobs) if job["set"] == "G_acc"), None)
        if chosen or first is None:
            return None
        chosen.append(block)
        return next(n for n, job in enumerate(jobs) if n > first and job["arm"] == "S'" and job["set"] == "real")

    _pause(monkeypatch, after_g_acc)
    events_path = budgets.ledger_root(setting.root, CHAIN) / "events.jsonl"
    with pytest.raises(Pause) as stop:
        step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    assert stop.value.kind == "sandbox" and len(chosen) == 1
    paused = len(events_path.read_text().splitlines())  # the ledger up to the pause: the units before, attempt 1
    step_root = setting.root / CHAIN / ("s%d-%s" % (K, BENCH))
    accept_root = step_root / "accept"
    write_json(accept_root / "attempt-1" / "recovery.json",
               {"by": "owner", "date": "2026-10-22", "decision": "fixture: redo the paused block (ticket C7e-1)"})
    step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    accepted = result(step_root, "accept")
    assert accepted["attempt"] == "attempt-2" and accepted["result"]["redone"] == chosen
    assert accepted["result"]["g_acc"] > 0

    def stored(attempt):
        return [verified(read_json(p), "cell") for p in sorted((accept_root / attempt / "cells").glob("*.json"))]

    def g_acc(cell):
        return cell["set"] == "G_acc"

    cells = {name: stored(name) for name in ("attempt-1", "attempt-2")}
    redone = [c for c in cells["attempt-2"] if c["cell"]["block"] in chosen]
    assert any(g_acc(c) for c in cells["attempt-1"] if c["cell"]["block"] in chosen) and any(map(g_acc, redone))

    # each cell's settled sends, by the attempt that sent them: a G_acc cell's on the examiner's scope only, the
    # redone block's other cells' on ...:accept:attempt-2 and the redo reserve, every other cell's on ...:accept
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    expected = {"G_acc": sorted(budgets.solver_scopes(CHAIN, BENCH, K, "examiner")),
                "redone": sorted(budgets.solver_scopes(CHAIN, BENCH, K, "accept", 2)),
                "first": sorted(budgets.solver_scopes(CHAIN, BENCH, K, "accept"))}
    for name, part in (("attempt-1", events[:paused]), ("attempt-2", events[paused:])):
        labels = {"%s/%s" % (c["cell"]["unit"], c["cell"]["id"]): c for c in cells[name]}
        settled = [e for e in part if e["event"] == "settle" and e["label"] in labels]
        assert len(settled) == sum(len(c["sends"]) for c in cells[name]) > 0
        for event in settled:
            cell = labels[event["label"]]
            way = "G_acc" if g_acc(cell) else "redone" if name == "attempt-2" and cell in redone else "first"
            assert event["scopes"] == expected[way], (name, cell["set"], cell["cell"]["block"], event["scopes"])

    # the scopes' totals: the examiner's holds its probes and every G_acc send, the acceptance's none of them
    settled = [e for e in events if e["event"] == "settle"]
    prefix = "G:xs:officeqa:2:"

    def charged(scope):
        return sum(scope in e["scopes"] for e in settled)

    def sends(found, keep):
        return sum(len(c["sends"]) for c in found if keep(c))

    first, second = cells["attempt-1"], cells["attempt-2"]
    probes = [e for e in settled if "G:solver" in e["scopes"] and e["label"].startswith("G/s2-officeqa/generate/")]
    assert probes and all(e["scopes"] == expected["G_acc"] for e in probes)
    assert charged(prefix + "examiner") == len(probes) + sends(first, g_acc) + sends(second, g_acc)
    assert charged(prefix + "accept:attempt-2") == charged("G:redo") == sends(redone, lambda c: not g_acc(c)) > 0
    assert charged(prefix + "accept") == (sends(first, lambda c: not g_acc(c))
                                          + sends(second, lambda c: not g_acc(c) and c not in redone))
    assert all(entry["open"] == 0 for entry in setting.budget.snapshot().values())

    # the decision from the union of both attempts, with the series of the real and the G_acc set (deciding nothing)
    sealed = verified(read_json(accept_root / "sealed.json"), "acceptance-sealed")
    decision = verified(read_json(accept_root / "attempt-2" / "decision" / "decision.json"), "decision")
    union = acceptance.round_cells(accept_root, sealed, decision)
    assert canonical(acceptance.decide(union, sealed)) == canonical(decision)
    assert decision["series"]["decides"] is False and set(decision["series"]["sets"]) == {"real", "G_acc"}
    assert set(decision["series"]["sets"]["G_acc"]) == {c["arm"] for c in union if g_acc(c)}


# ----------------------------------------------------------------------------------------------- ticket PR-C12-1
SB = "spreadsheetbench"


def sheet_roles(system, payload):
    """The GLM-5.3 roles of a SpreadsheetBench generate unit: a policy without research requests and a generator
    without specs (the test hands the step its generated set through ``step._build``)."""
    if system == examiner.POLICY_SYSTEM:
        return {"families": ["spreadsheetbench.formula_edit"], "rationale": "Workbook formulas.", "requests": []}
    if system == examiner.GENERATOR_SYSTEM:
        return {"specs": []}
    raise AssertionError("Only the policy and the generator speak in this unit")


class SheetAnswers:
    """Chain G's fake solver on the generated workbooks (``answer(system, user)``): the item's number is in its
    instruction; with the workbook preview (the parent's band probe) right on the even items, without it (the
    no-workbook shortcut probe) right on item 0 only, in both runs. Every request is kept as (system, user)."""

    def __init__(self):
        self.requests = []

    def __call__(self, system, user):
        self.requests.append((system, user))
        view = json.loads(user)
        n = int(re.search(r"block ([0-9]+)", view["instruction"]).group(1))
        right = n % 2 == 0 if "workbook_preview" in view else n == 0
        return program(RIGHT_FORMULA if right else WRONG_FORMULA)


def sheet_set(root, generator, source, count=4):
    """A generated SpreadsheetBench set of the step's generator: ``count`` formula-edit items of the run-slice item
    ``source``, each with its own instruction and real public workbook (``workbook``)."""
    found = []
    for n in range(count):
        tag = "q%02dz" % n
        public = {"instruction": "Write the ledger total of block %d into B1." % n,
                  "input_files": [workbook(root / ("input-%d.xlsx" % n), tag)], "answer_position": "B1"}
        found.append(generated_item(
            evidence=FIXTURE, generator=generator, number=n, bench=SB, family="spreadsheetbench.formula_edit",
            source_item=source, material_id="m", public=public,
            private_fields={"test_files": [workbook(root / ("answer-%d.xlsx" % n), tag)], "answer_position": "B1"},
            truth={"kind": "recalc_formula", "checked_by": sheet.CHECKED_BY}, set_name="G_self", seed=1))
    return examiner.Generated(generator, SB, ({"items": found, "made": count, "dropped": {}, "status": "made",
                                               "material": "m", "family": "spreadsheetbench.formula_edit"},), count)


def sheet_step(tmp_path, monkeypatch, answer):
    """(chain G's SpreadsheetBench step 1 on the empty parent, its cut): the real ledger, slots, roles (``sheet_roles``)
    and cells; the solver ``answer``; the cells' sandbox a FakeSandbox (the card and parent arms hold no procedure)."""
    root = tmp_path / "root"
    pool = spreadsheetbench_items(tmp_path / "pool", 4)
    solver_fake = FakeSolver(tmp_path / "solver", [(None, answer)], model=GLM_SOLVER)
    glm = FakeGLM(tmp_path / "glm", sheet_roles)
    ledger = Budget(budgets.ledger_root(root, CHAIN), sleep=lambda _: None)
    ledger.declare(budgets.chain_caps(CHAIN))
    setting = units.Setting(
        run=RUN, root=root, shared=root / "shared", pools={SB: pool}, cards={b: CARD for b in BENCHES},
        runtime=RUNTIMES, clients=lambda model, bench: glm.client if bench is None else solver_fake.client,
        budget=ledger, slots=slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None), sandbox={},
        evidence=FIXTURE, workers=1, cooldown=0, extra={"slot_root": str(tmp_path / "heavy")})
    real = units.cell_context

    def context(setting_, attempt, endpoint):
        found = real(setting_, attempt, endpoint)
        found.worker = lambda bench: FakeSandbox()
        return found

    def no_worker(*args, **kwargs):
        raise AssertionError("The generate unit starts no sandbox worker of its own")

    monkeypatch.setattr(units, "cell_context", context)
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", 4)  # the four-item fixture sets' band probe (Codex finding #9)
    services = step.Services(registry=Registry(tmp_path / "history", evidence=FIXTURE),
                             sources=sources(tmp_path / "research")[0], workers=no_worker)
    parent = empty(step="G/s0", evidence=FIXTURE)
    return step._Step(setting, services, CHAIN, SB, 1, parent, root / CHAIN), {"run": pool[:2], "accept": pool[2:]}


def test_pr_c12_1_a_spreadsheetbench_step_reaches_the_shortcut_gate_with_no_workbook_cells(tmp_path, monkeypatch):
    """Ticket PR-C12-1 (registration §7.2 shortcut gate "表格题去掉工作簿, 2 次都答对的题丢掉", §9.2; registrar decision
    on ticket C1-2): chain G's SpreadsheetBench generate unit probes the band with the workbook and the shortcut
    without it -- each probe cell carries ``examiner.probe_mode`` as its ``shortcut``, its record states the mode the
    shell ran in, its program still runs on the real input workbook -- so the gate reaches a verdict (one item of four
    right in both runs: dropped, 25 % allowed, the set admitted). No probe request holds a workbook byte or a preview
    text; every probe call is charged to ``...:examiner``. Without the mode the gate refuses the probe cells and the
    unit pauses on its configuration."""
    _, runs = containers(monkeypatch)
    answers = SheetAnswers()
    st, cut = sheet_step(tmp_path, monkeypatch, answers)
    made, built = sheet_set(tmp_path / "generated", step._generator_id(st), cut["run"][0]["task_id"]), []

    def build_set(st_, specs, materials, set_name, sources_, attempt, start):  # C1-3: the run slice's items only
        built.append((set_name, sorted(sources_), start))
        return made

    monkeypatch.setattr(step, "_build", build_set)
    found = step._generate(st, cut)
    ids = [item["id"] for item in made.items]
    assert built == [("G_self", sorted(item["task_id"] for item in cut["run"]), 0)]
    gates = found["gates"]
    assert gates["band"]["pass_rate"] == 0.5 and gates["band"]["in_band"]
    assert gates["shortcut"] == {"probe": examiner.SHORTCUT_PROBES[SB], "probe_items": 4, "dropped": [ids[0]],
                                 "flagged_share": 0.25, "used": True, "reason": None}
    assert gates["admitted"] and gates["kept"] == ids[1:] and found["generator"]["status"] == "admitted"
    assert [item["id"] for item in found["g_self"]] == ids[1:]

    # the stored cells: the band probe (S once, with the workbook) and the shortcut probe (C twice, without it)
    attempt = st.root / "generate" / result(st.root, "generate")["attempt"]
    cells = [verified(read_json(path), "cell") for path in sorted((attempt / "cells").glob("*.json"))]
    probe = [c for c in cells if c["cell"]["unit"] == st.label("generate/shortcut")]
    band = [c for c in cells if c["cell"]["unit"] == st.label("generate/band-1")]
    mode = examiner.SHORTCUT_MODES[SB]
    assert len(probe) == 8 and len(band) == 4 and len(cells) == 12
    assert all(c["cell"]["shortcut"] == c["shortcut"] == mode and c["arm_kind"] == "card" for c in probe)
    assert all("shortcut" not in c and "shortcut" not in c["cell"] and c["arm_kind"] == "parent" for c in band)
    # the requests: four with the preview (band), eight without any workbook byte or preview text (shortcut)
    shown = [r for r in answers.requests if "workbook_preview" in json.loads(r[1])]
    hidden = [r for r in answers.requests if "workbook_preview" not in json.loads(r[1])]
    assert len(shown) == 4 and len(hidden) == 8
    assert_no_workbook(hidden, [path for item in made.items for path in item["public"]["input_files"]],
                       RUNTIMES[SB]["spreadsheet_preview_version"])
    # each program still ran on its item's real input workbook (the band probe first, then the shortcut probe)
    inputs = {Path(item["public"]["input_files"][0]).read_bytes() for item in made.items}
    assert len(runs) == 12 and {base64.b64decode(run["input_base64"]) for run in runs[4:]} == inputs
    # chain G's ledger: every probe call on the step's examiner scope
    events = [json.loads(line) for line in (budgets.ledger_root(st.setting.root, CHAIN) / "events.jsonl").read_text()
              .splitlines()]
    solved = [e for e in events if e["event"] == "settle" and "G:solver" in e["scopes"]]
    assert len(solved) == 12 and all(e["scopes"] == sorted(budgets.solver_scopes(CHAIN, SB, 1, "examiner"))
                                     for e in solved)

    # without the mode (before PR-C12-1) the probe cells see the workbook: the gate refuses them, the unit pauses
    monkeypatch.setattr(examiner, "probe_mode", lambda variant: None)
    unwired = replace(st, chain_root=tmp_path / "unwired" / CHAIN)
    with pytest.raises(Pause) as stop:
        step._generate(unwired, cut)
    assert stop.value.kind == "configuration"
    assert "probe mode" in next((unwired.root / "generate").glob("attempt-*/diagnostics.log")).read_text()


# --------------------------------------------------------------------------- M round: Codex #4, #5, #7, #8, #9
def _bare_step(root, history, bench, pools, k=K):
    """A chain-G step of ``bench`` under run root ``root`` on fixture pools, with the registry of ``history``: the
    Setting's parts the slicing reads."""
    setting = SimpleNamespace(root=root, pools=pools, extra={}, runtime={}, evidence=FIXTURE, workers=1)
    services = SimpleNamespace(registry=Registry(history, evidence=FIXTURE), item_workers=None)
    return step._Step(setting, services, CHAIN, bench, k, empty(step="%s/s0" % CHAIN, evidence=FIXTURE),
                      root / CHAIN)


def test_codex7_the_same_step_labels_under_another_run_root_hold_their_items_out_of_the_slices(tmp_path):
    """Codex finding #7 (registration §3.1-§3.4): the slice exclusion keys a unit by its label AND its run root. The
    same step under a fresh run root of the same history cuts around the items its labels hold under the first root
    -- another root's units -- and its units then register without a conflict; the first root's step, resumed before
    its slices were sealed, is not shifted by its own registrations."""
    pool, history = officeqa_items(200), tmp_path / "history"
    first = _bare_step(tmp_path / "pilot", history, BENCH, {BENCH: pool})
    cut, registry = step._slices(first), first.services.registry
    for name in ("run", "accept"):
        registry.register(CHAIN, BENCH, cut[name], unit=first.label(name), purpose=name, run_root=first.setting.root)
    (first.root / step.SLICES_FILE).unlink()
    assert step._slices(first) == cut  # its own registrations do not shift the resumed step
    second = _bare_step(tmp_path / "main", history, BENCH, {BENCH: pool})
    assert second.label("run") == first.label("run") and second.setting.root != first.setting.root
    moved = step._slices(second)
    taken = {item["task_id"] for items in cut.values() for item in items}
    assert not taken & {item["task_id"] for items in moved.values() for item in items}
    assert {name: len(items) for name, items in moved.items()} == {name: len(items) for name, items in cut.items()}
    for name in ("run", "accept"):
        assert second.services.registry.bound(second.setting.root).register(
            CHAIN, BENCH, moved[name], unit=second.label(name), purpose=name) == len(moved[name])


def test_codex9_an_insufficient_generated_set_is_recorded_and_never_probed(tmp_path, monkeypatch):
    """Codex finding #9 (registration §7.2: the band is the parent's accuracy on 30 probe items): at the registered
    probe size a four-item SpreadsheetBench set is insufficient material -- recorded in the gates and the outcomes,
    never probed (no band or shortcut cell, no solver call, no workbook run) and never admitted."""
    _, runs = containers(monkeypatch)
    answers = SheetAnswers()
    st, cut = sheet_step(tmp_path, monkeypatch, answers)
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", protocol.BAND_PROBE_ITEMS)  # the registered 30
    made = sheet_set(tmp_path / "generated", step._generator_id(st), cut["run"][0]["task_id"])
    monkeypatch.setattr(step, "_build", lambda *args: made)
    found = step._generate(st, cut)
    gates = found["gates"]
    assert gates["band"] == {"in_band": False, "reason": "insufficient_material", "items": 4, "required": 30,
                             "probe_items": 0, "pass_rate": None, "direction": None}
    assert gates["shortcut"]["reason"] == "not_run" and not gates["admitted"] and gates["kept"] == []
    assert found["generator"]["status"] == "not_admitted" and found["g_self"] == []
    assert found["outcomes"]["band"] == {"insufficient_material": 1}
    attempt = st.root / "generate" / result(st.root, "generate")["attempt"]
    assert not list((attempt / "cells").glob("*.json")) and answers.requests == [] and runs == []


def test_codex7_a_step_unit_moves_items_only_as_a_unit_of_its_own_run_root(tmp_path, monkeypatch, workers):
    """Codex finding #7: while a step unit runs its consumption registry is bound to the run root (``_Step.unit``),
    so a move naming no run root -- acceptance.py's dispatch, decide and release -- is THIS root's unit: settling
    items the same label holds under another run root conflicts (the unit pauses on consumption) instead of passing
    as a redo's own settlement, while the owning root's unit settles them again idempotently."""
    setting, services, solver_fake, glm, waited = build(tmp_path, monkeypatch, workers)
    first = step._Step(setting, services, CHAIN, BENCH, K, PARENT, setting.root / CHAIN)
    items, label, registry = ITEMS[:3], first.label("run"), services.registry
    registry.register(CHAIN, BENCH, items, unit=label, purpose="run", run_root=setting.root)
    registry.dispatch(CHAIN, BENCH, items, unit=label)
    registry.decide(CHAIN, BENCH, items, unit=label)
    elsewhere = replace(setting, root=tmp_path / "other-root")
    second = step._Step(elsewhere, services, CHAIN, BENCH, K, PARENT, elsewhere.root / CHAIN)
    assert second.label("run") == label

    def settle_again(st):
        return lambda attempt: {"written": st.services.registry.decide(CHAIN, BENCH, items, unit=label)}

    with pytest.raises(Pause) as stop:
        second.unit("run", settle_again(second))
    assert stop.value.kind == "consumption" and not solver_fake.requests
    assert first.unit("run", settle_again(first)) == {"written": 0}

def test_codex9_a_thirty_item_set_is_probed_whole_and_admitted_at_the_registered_size(tmp_path, monkeypatch):
    """Codex finding #9 (registration §7.2): at the registered probe size (no fixture knob) a SpreadsheetBench set of
    30 qualified items is probed whole -- the band probe on all 30 with the workbook (15 right: 50 %, in band), the
    shortcut probe on all 30 twice without it (item 0 right in both runs: dropped, 1/30 <= 25 %) -- and admitted."""
    _, runs = containers(monkeypatch)
    answers = SheetAnswers()
    st, cut = sheet_step(tmp_path, monkeypatch, answers)
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", protocol.BAND_PROBE_ITEMS)  # the registered 30
    made = sheet_set(tmp_path / "generated", step._generator_id(st), cut["run"][0]["task_id"], count=30)
    monkeypatch.setattr(step, "_build", lambda *args: made)
    found = step._generate(st, cut)
    ids, gates = [item["id"] for item in made.items], found["gates"]
    assert (gates["band"]["probe_items"], gates["band"]["pass_rate"], gates["band"]["in_band"],
            gates["band"]["reason"]) == (30, 0.5, True, None)
    assert (gates["shortcut"]["probe_items"], gates["shortcut"]["dropped"], gates["shortcut"]["used"]) == (
        30, [ids[0]], True)
    assert gates["admitted"] and gates["kept"] == ids[1:] and found["generator"]["status"] == "admitted"
    attempt = st.root / "generate" / result(st.root, "generate")["attempt"]
    assert len(list((attempt / "cells").glob("*.json"))) == len(answers.requests) == len(runs) == 30 + 2 * 30

class _Killed(BaseException):
    """The process dies: no handler runs, no status is written."""


def test_codex8_an_accept_unit_killed_before_its_completion_evidence_settles_only_in_its_redo(
        tmp_path, monkeypatch, workers):
    """Codex finding #8 on the accept unit (§3.4, §9.3, §13): the round's items are decided only after the unit's
    completion evidence is persisted. A process killed while writing that evidence leaves A* dispatched, never decided;
    after the owner's decision the redo registers its own items again, reuses every block the killed attempt
    finished (no solver call), decides, persists its evidence and only then settles -- the step completes as without
    the kill (before the fix the redo's registration met decided items and paused)."""
    setting, services, solver_fake, glm, waited = build(tmp_path, monkeypatch, workers)
    step_root = setting.root / CHAIN / ("s%d-%s" % (K, BENCH))
    accept_root, real = step_root / "accept", units.write_json

    def killed_at_the_accept_evidence(path, value):
        if path.name == units.COMPLETED and path.parent.parent == accept_root:
            raise _Killed()
        return real(path, value)

    monkeypatch.setattr(units, "write_json", killed_at_the_accept_evidence)
    with pytest.raises(_Killed):
        step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    monkeypatch.setattr(units, "write_json", real)
    slices = verified(read_json(step_root / step.SLICES_FILE), "step-slices")["slices"]
    astar = set(verified(read_json(accept_root / "sealed.json"), "acceptance-sealed")["plan"]["astar"])
    lines = services.registry.entries(CHAIN, BENCH)
    assert len(astar) >= 30 and {lines[i]["state"] for i in astar} == {"dispatched"}  # consumed, not decided
    calls = len(solver_fake.requests)
    with pytest.raises(Pause) as waiting:
        step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    assert waiting.value.kind == "awaiting_owner_decision"
    write_json(accept_root / "attempt-1" / "recovery.json", {"by": "owner", "date": "2026-10-22",
                                                             "decision": "redo the killed attempt"})
    found = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    done = verified(read_json(accept_root / "unit.json"), "unit")
    assert found.record["decision"] == "accept" and done["attempt"] == "attempt-2" and "committed_in" not in done
    assert done["result"]["redone"] == [] and set(done["result"]["reused"].values()) == {"attempt-1"}
    assert len(solver_fake.requests) == calls  # every block reused from the killed attempt
    lines = services.registry.entries(CHAIN, BENCH)
    assert all(lines[i]["state"] == ("decided" if i in astar else "routed_not_dispatched") for i in slices["accept"])
    assert {lines[i]["attempt"] for i in astar} == {2}

def _generated_set(bench, items, k):
    """Generated items of chain D's step ``k`` on ``bench`` made of fixture items (their public and private
    fields)."""
    return [generated_item(evidence=FIXTURE, generator="g-%s-%d-1" % (bench, k), number=n, bench=bench,
                           family=bench + ".fixture", source_item=item["task_id"], material_id="m",
                           public=item["public"], private_fields=item["private"],
                           truth={"kind": "fixture", "checked_by": "fixture"}, set_name="G_self", seed=1)
            for n, item in enumerate(items)]


def test_codex4_5_a_mixed_self_test_runs_each_set_on_its_benchs_client_and_bound_and_lock(tmp_path, monkeypatch):
    """Codex findings #4 and #5 (registration §4.1, §5.5, §9.3; §2.6, §11): chain D's SpreadsheetBench step 4 of the
    main order self-tests the earlier OfficeQA and LiveMath sets in one seeded interleaving. Every cell goes to its
    own bench's chain-D client (its nominal M) with its own bench's ledger bound B -- 16,384 on the question-answer
    benches, not the step's 32,768 -- the step's own client gets none, and every call is charged to this step's
    ``D:xs:spreadsheetbench:4:selftest``; the unit takes the memory lock of every bench it runs."""
    d, sb = protocol.CHAINS["D"], "spreadsheetbench"
    fakes = {bench: FakeSolver(tmp_path / bench, [(None, tagged("A" if bench == "livemath" else "0"))], model=d,
                               max_tokens=protocol.solver_tokens(d, bench)) for bench in ("officeqa", "livemath", sb)}
    root = tmp_path / "root"
    ledger = Budget(budgets.ledger_root(root, "D"), sleep=lambda _: None)
    ledger.declare(budgets.chain_caps("D", protocol.MAIN))
    setting = units.Setting(
        run=RUN, root=root, shared=root / "shared", pools={}, cards={b: CARD for b in BENCHES}, runtime=RUNTIMES,
        clients=lambda model, bench: fakes[bench].client, budget=ledger,
        slots=slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None), sandbox={}, evidence=FIXTURE,
        workers=1, cooldown=0, branch="E", longest=None)
    real, locks = units.cell_context, []

    def context(setting_, attempt, endpoint):
        found = real(setting_, attempt, endpoint)
        found.worker = lambda bench: FakeSandbox()
        return found

    @contextmanager
    def heavy(setting_, bench, *more):
        locks.append((bench, *more))
        yield

    def no_worker(*args, **kwargs):
        raise AssertionError("The self-test starts no sandbox worker of its own")

    monkeypatch.setattr(units, "cell_context", context)
    monkeypatch.setattr(step, "heavy", heavy)
    parent = empty(step="D/s0", evidence=FIXTURE)
    services = step.Services(registry=Registry(tmp_path / "history", evidence=FIXTURE), sources=None,
                             workers=no_worker)
    st = step._Step(setting, services, "D", sb, 4, parent, root / "D")
    earlier = {"officeqa": _generated_set("officeqa", officeqa_items(2), 2),
               "livemath": _generated_set("livemath", livemath_items(2), 3)}
    for k, bench in ((2, "officeqa"), (3, "livemath")):
        units.run_unit(units.unit_path(st.chain_root, k, bench, "generate"), run=RUN,
                       identity={"unit": "D/s%d-%s/generate" % (k, bench), "chain": "D", "k": k},
                       work=lambda attempt, found=earlier[bench]: {"g_self": found}, evidence=FIXTURE)
    tested = step._selftest(st, "selftest", parent, {"g_self": []})
    assert tested["cells"] == 8 and tested["reason"] is None and set(tested["sets"]) == {"officeqa", "livemath"}
    assert len(fakes["officeqa"].requests) == len(fakes["livemath"].requests) == 4 and fakes[sb].requests == []
    attempt = units.unit_path(st.chain_root, 4, sb, "selftest") / "attempt-1"
    cells = [verified(read_json(path), "cell") for path in sorted((attempt / "cells").glob("*.json"))]
    bound = {bench: protocol.ledger_bound(d, bench, branch="E", longest=None) for bench in fakes}
    assert bound["officeqa"] == bound["livemath"] == 16_384 < bound[sb] == 32_768
    sends = [(c["cell"]["benchmark"], send) for c in cells for send in c["sends"]]
    assert sorted(Counter(bench for bench, _ in sends).items()) == [("livemath", 4), ("officeqa", 4)]
    assert all(send["max_tokens"] == bound[bench] and send["model"] == d
               and send["reserved"] == frozen_ledger.reservation(send["request_bytes"], bound[bench])
               for bench, send in sends)
    events = [json.loads(line) for line in (budgets.ledger_root(root, "D") / "events.jsonl").read_text()
              .splitlines()]
    reserved = [e for e in events if e["event"] == "reserve"]
    assert len(reserved) == 8 and all(e["scopes"] == sorted(budgets.solver_scopes("D", sb, 4, "selftest", 1))
                                      for e in reserved)
    assert locks == [(sb, "livemath", "officeqa")]  # the memory lock of every bench the unit runs (§2.6)


def test_codex8_a_run_unit_whose_drain_fails_after_its_settlement_commits_without_a_new_solver_call(
        tmp_path, monkeypatch, workers):
    """Codex finding #8 (§3.4, §5): the run unit's work persists its completion evidence, then the settlement decides
    the run slice; a drain failing right after pauses the unit. After the owner's decision the commit attempt settles
    again (nothing written), drains and completes the unit naming the attempt whose cells ran -- no solver call,
    no registry line, no cell again."""
    setting, services, solver_fake, glm, waited = build(tmp_path, monkeypatch, workers)
    st = step._Step(setting, services, CHAIN, BENCH, K, PARENT, setting.root / CHAIN)
    cut, drained = step._slices(st), []

    def drainer(setting_, chain_, label):
        def drain():
            drained.append(label)
            if len(drained) == 1:
                raise CleanupUnconfirmed("a container of the run unit remains")
        return drain

    monkeypatch.setattr(units, "drainer", drainer)
    with pytest.raises(Pause) as stop:
        step._run(st, cut)
    root = units.unit_path(st.chain_root, K, BENCH, "run")
    assert stop.value.kind == stop_kind(CleanupUnconfirmed("x")) and not (root / "unit.json").exists()
    assert (root / "attempt-1" / units.COMPLETED).exists()
    lines = services.registry.entries(CHAIN, BENCH)
    assert {i for i, line in lines.items() if line["state"] == "decided"} == {i["task_id"] for i in cut["run"]}
    path = services.registry.path(CHAIN, BENCH)
    calls, count, cells = len(solver_fake.requests), len(path.read_text().splitlines()), len(
        list((root / "attempt-1" / "cells").glob("*.json")))
    assert calls > 0 and cells > 0
    with pytest.raises(Pause) as waiting:
        step._run(st, cut)
    assert waiting.value.kind == "awaiting_owner_decision"
    write_json(root / "attempt-1" / "recovery.json", {"by": "owner", "date": "2026-10-22",
                                                      "decision": "finish the commit"})
    found = step._run(st, cut)
    done = verified(read_json(root / "unit.json"), "unit")
    assert (done["attempt"], done["committed_in"]) == ("attempt-1", "attempt-2") and found == done["result"]
    assert found["cells"] == cells and len(solver_fake.requests) == calls
    assert len(path.read_text().splitlines()) == count and not (root / "attempt-2" / "cells").exists()
    assert drained == [st.label("run")] * 2 and step._run(st, cut) == found
