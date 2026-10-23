"""T-STEP-V2: one OfficeQA step of chain G in the v2 configuration ``main-v2`` (owner decision 2026-10-23 13:3x,
"train then accept"; analysts and step buffer, owner suggestion 2026-10-23 15:1x), on T-STEP-1's fixtures: chain G's
solver a FakeSolver behind the real glm-5.3 client and the real ledger, every method role a FakeGLM, the cells'
procedures FakeSandbox hooks, the engineer's checks the real worker through FakeDocker. Everything is an engineering
fixture.

Round 1: the analysts read the parent's failed run items in groups of six, the engineer proposes T-STEP-1's change
(the item's own customs receipts as a note), the training unit runs S' and S on the items they route differently
(the run items with their two runs, the admitted G_self items once): S' fixes every odd-keyed item and breaks none,
so the round adopts it. Rounds 2 and 3 propose nothing (the history shows round 1's proposal as adopted, the feedback
its examples): two rounds without adoption stop the loop. The self-test, the acceptance round and the freeze follow as
in v1, the consumption in chain G's v2 namespace ``G-v2``."""
from __future__ import annotations

import itertools
import json

from skillopt.coevo5.budget import Budget
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json
from skillopt.execskill import budgets, engineer, examiner, protocol, rounds, slots, step, units
from skillopt.execskill.client import GLM_SOLVER
from skillopt.execskill.package import FIXTURE, edits
from skillopt.execskill.protocol import BENCHES, verified
from skillopt.execskill.registry import Registry
from tests.execskill_fakes import FakeGLM, FakeSolver, engineer_reply
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_fakes_research import sources
from tests.test_execskill_integration_b3 import CARD, PARENT, sandboxes
from tests.test_execskill_replay import fake, workers  # noqa: F401  (FakeDocker workers)
from tests.test_execskill_step import (BENCH, CHAIN, HOOKS_STEP, ITEMS, K, NEW, RUN, Answers, result,
                                       roles_answer)

CONFIGURATION = "main-v2"
UNITS_RUN = ("run", "diagnose", "generate", "engineer-r1", "train-r1", "engineer-r2", "engineer-r3", "selftest",
             "accept", "freeze")


def roles_v2(system, payload):
    """T-STEP-1's roles under the v2 prompts: the analysts name one finding per group; the engineer proposes the
    change in round 1 (resending it unchanged when asked to fix it) and nothing afterwards."""
    if system == examiner.POLICY_SYSTEM_V2:
        return roles_answer(examiner.POLICY_SYSTEM, payload)
    if system == examiner.GENERATOR_SYSTEM_V2:
        return roles_answer(examiner.GENERATOR_SYSTEM, payload)
    if system == engineer.ANALYST_SYSTEM:
        shown = [t["task_id"] for t in payload["trajectories"]]
        return engineer_reply({"findings": [{"pattern": "Ratio questions miss the yearly receipts.", "items": shown[:2],
                                             "helper": "List each year's customs receipts read from the table."}]}, [])
    if system == engineer.ENGINEER_SYSTEM_V2:
        if payload["request"] == "fix" or payload["round"] == 1:
            return roles_answer(engineer.ENGINEER_SYSTEM, payload)
        return engineer_reply({"changes": []}, [])
    return roles_answer(system, payload)


def build_v2(tmp_path, monkeypatch, workers_):
    """T-STEP-1's ``build`` with the v2 configuration on the Setting and its caps on chain G's ledger."""
    root = tmp_path / "root"
    answers = Answers(ITEMS)
    solver_fake = FakeSolver(tmp_path / "solver", [(None, answers)], model=GLM_SOLVER)
    glm = FakeGLM(tmp_path / "glm", roles_v2)
    ledger = Budget(budgets.ledger_root(root, CHAIN), sleep=lambda _: None)
    ledger.declare(budgets.chain_caps(CHAIN, CONFIGURATION))
    setting = units.Setting(
        run=RUN, root=root, shared=root / "shared", pools={BENCH: ITEMS}, cards={b: CARD for b in BENCHES},
        runtime=RUNTIME, clients=lambda model, bench: glm.client if bench is None else solver_fake.client,
        budget=ledger, slots=slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None), sandbox={},
        evidence=FIXTURE, workers=1, cooldown=0, extra={"configuration": CONFIGURATION})
    ticks, waited = itertools.count(), []

    def clock():
        return float(next(ticks)) + sum(waited)

    real = units.cell_context

    def context(setting_, attempt, endpoint):
        found = real(setting_, attempt, endpoint)
        found.worker, found.clock = (lambda bench: FakeSandbox(HOOKS_STEP)), clock
        return found

    monkeypatch.setattr(units, "cell_context", context)
    monkeypatch.setattr(rounds, "cell_context", context)
    made = examiner.build

    def known(*args, **kwargs):
        found = made(*args, **kwargs)
        answers.add(found.items)
        return found

    monkeypatch.setattr(examiner, "build", known)
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", 4)
    services = step.Services(registry=Registry(tmp_path / "history", evidence=FIXTURE),
                             sources=sources(tmp_path / "research")[0], workers=workers_,
                             item_workers=sandboxes(HOOKS_STEP), clock=clock, sleep=waited.append)
    return setting, services, solver_fake, glm, waited


def test_step_v2_trains_adopts_then_accepts(tmp_path, monkeypatch, workers):
    setting, services, solver_fake, glm, waited = build_v2(tmp_path, monkeypatch, workers)
    found = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    step_root = setting.root / CHAIN / ("s%d-%s" % (K, BENCH))
    record = verified(read_json(step_root / step.STEP_FILE), "step")
    assert found.record == record and record["learning"] == "train"
    assert record["decision"] == "accept" and found.package.order == PARENT.order + (NEW,)
    assert set(record["units"]) == set(UNITS_RUN)
    training = record["training"]
    assert [r["adopted"] for r in training["rounds"]] == [True, False, False] and training["adopted"] == 1
    assert training["exercise"] is False and training["final_sha256"] == record["candidate_sha256"]
    assert [r["reason"] for r in training["rounds"]][1:] == ["no_candidate", "no_candidate"]

    # the generate unit ran under the v2 prompts
    generated = result(step_root, "generate")["result"]
    assert generated["learning"] == "train" and generated["generator"]["status"] == "admitted"
    assert generated["topups"] == []  # four items: the (fixture) band probe needs no top-up
    asked = [s for s, _ in glm.seen]
    assert examiner.POLICY_SYSTEM_V2 in asked and examiner.GENERATOR_SYSTEM_V2 in asked
    assert examiner.POLICY_SYSTEM not in asked and engineer.ENGINEER_SYSTEM not in asked

    # round 1: the analysts read the parent's failed run items in groups, then the engineer proposes
    run_cells = result(step_root, "run")["result"]
    engineered = result(step_root, "engineer-r1")["result"]["engineer"]
    groups = [c["items"] for c in engineered["analysis"]["calls"]]
    assert groups and all(1 <= len(g) <= protocol.TRAIN_ANALYST_BATCH for g in groups)
    assert len(groups) <= protocol.TRAIN_ANALYST_CALLS and engineered["analysis"]["failed_items"] >= len(groups[0])
    proposals = [p for s, p in glm.seen if s == engineer.ENGINEER_SYSTEM_V2 and p["request"] == "propose"]
    assert [p["round"] for p in proposals] == [1, 2, 3]
    assert proposals[0]["history"] == [] and proposals[0]["training"] is None and proposals[0]["analyses"]
    assert all(f["items"] and set(f["items"]) <= set(groups[0]) | set(sum(groups, [])) for f in proposals[0]["analyses"])

    # the training unit: S' and S on the items routed differently; S' fixes and breaks none; adopted
    trained = result(step_root, "train-r1")["result"]
    verdict = trained["verdict"]
    runs = protocol.SLICES[BENCH]["run"][1]
    assert trained["adopted"] and verdict["fixed"] and verdict["broken"] == [] and verdict["adopted"]
    assert trained["cells"] == 2 * (runs * verdict["items"] + verdict["generated"])
    assert verdict["items"] >= 1 and trained["differs"] == verdict["items"] + verdict["generated"]

    # round 2 sees round 1 in its history (the step buffer) and its evaluation as feedback
    second = proposals[1]
    assert second["history"][0]["adopted"] and second["history"][0]["proposals"] == [
        {"kind": "new", "id": NEW, "target": None, "description": engineered["changes"][0]["summary"],
         "fate": "adopted"}]
    feedback = second["training"]
    assert feedback["adopted"] and [p["id"] for p in feedback["procedures"]] == [NEW]
    examples = feedback["procedures"][0]["examples"]
    assert examples and all(e["outcome"] == "fixed" and "reference" in e for e in examples)
    assert len(examples) <= protocol.TRAIN_EXAMPLES and second["edits"]["used"] == 1
    assert all(e["current_pass"] != e["candidate_pass"] for e in examples)
    # adopted: the incumbent's current cells of the evaluated items are S' cells, all passing, so no failure is left
    # for round 2's analysts among them
    assert result(step_root, "engineer-r2")["result"]["engineer"]["analysis"]["failed_items"] < \
        engineered["analysis"]["failed_items"]

    # self-test, acceptance and freeze as in v1; consumption in the v2 namespace
    assert not result(step_root, "selftest")["result"]["blocked"]
    accepted = result(step_root, "accept")
    assert accepted["result"]["decision"] == "accept"
    sealed = verified(read_json(step_root / "accept" / "sealed.json"), "acceptance-sealed")
    assert sealed["chain"] == "G-v2"
    slices = verified(read_json(step_root / step.SLICES_FILE), "step-slices")["slices"]
    lines = services.registry.entries("G-v2", BENCH)
    assert set(lines) == set(slices["run"]) | set(slices["accept"]) and not services.registry.entries(CHAIN, BENCH)
    assert all(lines[i]["state"] == "decided" and lines[i]["unit"] == "G/s2-officeqa/run" for i in slices["run"])

    # every training cell was charged to the step's self-test scope on chain G's own ledger
    events = [json.loads(line) for line in (budgets.ledger_root(setting.root, CHAIN) / "events.jsonl").read_text()
              .splitlines()]
    settled = [e for e in events if e["event"] == "settle"]
    selftest_scope = "G:xs:officeqa:2:selftest"
    tested = result(step_root, "selftest")["result"]["cells"]
    assert sum(selftest_scope in e["scopes"] for e in settled) >= trained["cells"] + tested
    assert all(entry["open"] == 0 for entry in setting.budget.snapshot().values())

    # read back: no model call
    calls = (len(solver_fake.requests), len(glm.seen))
    again = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    assert again.record == record and (len(solver_fake.requests), len(glm.seen)) == calls
    assert [e.kind for e in edits(PARENT, found.package)] == ["new"] and run_cells["cells"] > 0
