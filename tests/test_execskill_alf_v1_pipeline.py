"""ALF-only authored pipeline fixtures: real slices, units, replay, training and room-level acceptance.

No benchmark data, native environment, sandbox subprocess, Docker or external calls are used.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_zpc_pipeline import SourceWorker, offline, result, workers
from tests.execskill_fakes import FakeGLM, FakeSolver, engineer_reply
from tests.test_execskill_chain import CONSENT

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (acceptance, budgets, chain, describer, engineer, evaluation, examiner, profiles as p,
                                rounds, slots, solver, step, supply, units)
from skillopt.execskill.package import FIXTURE, empty
from skillopt.execskill.registry import Registry
from skillopt.validator_pilot.api import digest

BENCH = "alfworld"
SOURCE = '''def applies(view):
    return "task_text" in view and "initial_observation" in view
def alf_before_step(view, state):
    return {"fields": {"facts": [view["initial_observation"]]}, "discourage": []}
def alf_after_step(event, state):
    count = state["facts"]["nothing_happens"] if state else 0
    count += int(event["observation"].startswith("Nothing happens"))
    return {"facts": {"nothing_happens": count}}
'''
CARD = "Read the current task, inspect the available objects, and use admissible actions to complete it."
RUNTIME = {"max_steps": 50, "alfworld_trace_version": solver.ALFWORLD_TRACE_VERSION}


def fixture_pool(root):
    items, games = [], {}
    for room in range(108):
        for n in range(5):
            key = "authored-room-%03d-game-%d" % (room, n)
            initial = "You are in an authored room.\nYour task is to: inspect and take object %s." % key
            plan = ["inspect " + key, "take " + key]
            commands = ["look", *plan]
            game = {"initial_observation": initial, "admissible_commands": commands, "plan": plan,
                    "private_sentinel": "PRIVATE-ONLY-EXPERT-PLAN-" + key}
            path = str(root / (key + ".synthetic-game"))
            games[path] = game
            view = supply.routing_view(initial, commands)
            items.append({"benchmark": BENCH, "task_id": key, "family_id": key, "part": "fresh",
                "room": str(room), "task_type": "pick_and_place_simple",
                "public": {"game_file": path, "routing_view": view, "routing_view_sha256": digest(view)},
                "private": {"game_metadata": {"source_split": "train", "task_type": "pick_and_place_simple",
                    "asset_files": []}, "expert_plan": game["private_sentinel"]},
                "views_runtime_sha256": digest(RUNTIME)})
    return supply.order(BENCH, items), games


class TwoStepEnvironment:
    """Two actual transitions; both actions must follow the authored plan to win."""
    def __init__(self, game):
        self.game, self.actions, self.closed = game, [], False

    def infos(self, won=False):
        return [{"admissible_commands": self.game["admissible_commands"], "won": won,
                 "extra.expert_plan": self.game["private_sentinel"]}]

    def reset(self):
        return [self.game["initial_observation"]], None, self.infos()

    def step(self, actions):
        self.actions.append(actions[0])
        done = len(self.actions) == 2
        won = done and self.actions == self.game["plan"]
        return ["The authored transition completed."], None, [int(won)], [done], self.infos(won)

    def close(self):
        self.closed = True


def build(tmp_path, monkeypatch, *, gain=True):
    pool, games = fixture_pool(tmp_path / "games")
    sessions = []
    def environment(public, runtime):
        assert runtime["max_steps"] == 50
        found = TwoStepEnvironment(games[public["game_file"]])
        sessions.append(found)
        return found
    monkeypatch.setattr(backends, "_new_alfworld", environment)
    by_observation = {game["initial_observation"]: game for game in games.values()}
    def answer(system, user):
        if system == p.FIRST_CALL_SYSTEM:
            return "ready"
        view = json.loads(user)
        game = by_observation[view["initial_observation"]]
        own = game["initial_observation"] in view.get(p.NOTES_KEY, "")
        return game["plan"][len(view["recent_history"])] if own and gain else "look"
    def role(system, payload):
        if system == examiner.DETECTOR_SYSTEM:
            return engineer_reply({"detectors": []}, [])
        if system == engineer.ANALYST_SYSTEM:
            return engineer_reply({"findings": []}, [])
        if system == engineer.ENGINEER_SYSTEM_ALF_V1:
            if payload["request"] == "fix" or payload["round"] == 1:
                return engineer_reply({"changes": [{"kind": "new", "description": "Retains the public task while tracking completed steps.",
                    "hooks": ["applies", "alf_before_step", "alf_after_step"], "max_note_chars": 4000,
                    "state_bytes": 1024, "excluded_benches": [b for b in p.BENCHES if b != BENCH]}]}, [SOURCE])
            return engineer_reply({"changes": []}, [])
        if system == describer.DESCRIBER_SYSTEM:
            return "Keep the initial public task available while tracking completed steps."
        return {"verdict": "no", "reason": "A general tracker of public observations."}
    fake_solver = FakeSolver(tmp_path / "solver", [(None, answer)],
        max_tokens=p.ELUCID_MAX_TOKENS[BENCH], read_timeout=p.ELUCID_READ_TIMEOUT[BENCH])
    glm = FakeGLM(tmp_path / "glm", role)
    root = tmp_path / "root"
    ledger = Budget(budgets.ledger_root(root, "D"), sleep=lambda _: None)
    ledger.declare(budgets.chain_caps("D", p.ALFWORLD_V1))
    setting = units.Setting(run="synthetic-alf-v1", root=root, shared=root / "shared", pools={BENCH: pool},
        cards={BENCH: CARD}, runtime={BENCH: dict(RUNTIME)},
        clients=lambda model, bench: glm.client if bench is None else fake_solver.client,
        budget=ledger, slots=slots.pools(tmp_path / "slots", poll=0.01, log=lambda _: None), sandbox={},
        evidence=FIXTURE, workers=1, cooldown=0, branch="E", extra={"configuration": p.ALFWORLD_V1,
            "verify": lambda: None, "slot_root": str(tmp_path / "slots"),
            "test_read_estimate": {"D": 1000}, "test_read_terms": {"D": {BENCH: "1000"}}})
    ticks, waited = itertools.count(), []
    clock = lambda: float(next(ticks)) + sum(waited)
    original = units.cell_context
    def context(setting_, attempt, endpoint):
        ctx = original(setting_, attempt, endpoint)
        ctx.worker, ctx.clock = lambda bench: SourceWorker(), clock
        return ctx
    monkeypatch.setattr(units, "cell_context", context)
    monkeypatch.setattr(rounds, "cell_context", context)
    services = step.Services(registry=Registry(tmp_path / "registry", evidence=FIXTURE), sources=None,
                             workers=workers, clock=clock, sleep=lambda delay: waited.append(delay))
    return setting, services, fake_solver, glm, sessions


@pytest.mark.parametrize("gain", [True, False])
def test_actual_alf_step_training_room_acceptance_and_resume(tmp_path, monkeypatch, gain):
    setting, services, fake_solver, glm, sessions = build(tmp_path, monkeypatch, gain=gain)
    parent = empty(step="D/s0", evidence=FIXTURE)
    found = step.run_step(setting, "D", BENCH, 1, parent, services=services)
    root = setting.root / "D" / "s1-alfworld"
    cut = p.verified(read_json(root / "slices.json"), "step-slices")["slices"]
    assert len(cut["run"]) == 60 and len(cut["accept"]) == 150
    assert result(root, "run")["cells"] == 60
    assert result(root, "generate")["generator"] is None
    first = result(root, "engineer-r1")["engineer"]
    assert first["prompt_sha256"] == engineer.ENGINEER_PROMPT_ALF_V1_SHA256
    assert first["changes"][0]["survived"], json.dumps([row for attempt in first["changes"][0]["attempts"] for row in attempt["checks"] if not row["passed"]])
    checks = {row["check"]: row for row in first["changes"][0]["attempts"][-1]["checks"]}
    assert checks["C6"]["passed"] and checks["C6b"]["passed"] and checks["C6c"]["passed"]
    assert checks["C6c"]["detail"]["nonempty"] == 60
    trained = result(root, "train-r1")
    assert trained["adopted"] is gain and trained["pruned"] == []
    assert trained["verdict"]["sign_required"] is False
    proposals = [payload for system, payload in glm.seen if system == engineer.ENGINEER_SYSTEM_ALF_V1]
    assert proposals and all("PRIVATE-ONLY-EXPERT-PLAN" not in json.dumps(payload) for payload in proposals)
    assert "notes_coverage" not in json.dumps(proposals)
    if gain:
        sealed = p.verified(read_json(root / "accept" / "sealed.json"), "acceptance-sealed")
        assert len(sealed["rooms"]) == 150 and len(set(sealed["rooms"].values())) == 40
        assert set(sealed["blocks"].values()) == {"b1", "b2", "b3", "b4"}
        by_room = {}
        for task, room in sealed["rooms"].items():
            by_room.setdefault(room, set()).add(sealed["blocks"][task])
        assert all(len(blocks) == 1 for blocks in by_room.values())
        assert sealed["runs"] == p.SLICES[BENCH]["accept"][1]
        assert sealed["rule"] == p.ACCEPT_RULES[p.MAIN_V2_2]
        assert sealed["freshness"] == "alfworld_main_accept_slice_first_use"
        assert sealed["plan"]["minimum"] == acceptance.minimum_astar(
            p.ACCEPT_RULES[p.MAIN_V2_2], 150, 4, alfworld=True)
        assert sealed["plan"]["astar_rooms"] == 40
        assert sealed["g_acc"] is None and sealed["placebo_i"] is None and sealed["placebo_y"] is not None
        decision = p.verified(read_json(root / "accept" / "attempt-1" / "decision" / "decision.json"), "decision")
        assert decision["decision"] == found.record["decision"] == "accept"
        assert decision["guards"]["J1"]["ok"] and decision["guards"]["J5"]["ok"]
        assert decision["contrasts"]["S'-S"]["df"] == 36
        assert decision["guards"]["J6_dup"]["ok"] and decision["guards"]["J7_meta"] is None
        assert found.package.procedures[0].source == SOURCE
        assert result(root, "freeze")["descriptions"]
    else:
        assert found.record["reason"] == "no_training_gain"
        assert found.package.sha256 == parent.sha256 and not (root / "accept").exists()
    assert sessions and all(session.closed and len(session.actions) == 2 for session in sessions)
    assert not (setting.root / "shared" / "consent.json").exists()
    assert not (setting.root / "D" / "test").exists() and not (setting.root / "D" / "stage-read").exists()
    consumed = services.registry.entries("D-alf1", BENCH)
    assert len(consumed) == (210 if gain else 60) and {r["state"] for r in consumed.values()} == {"decided"}
    assert all(row["open"] == 0 for row in setting.budget.snapshot().values())
    before = len(fake_solver.requests), len(glm.seen), len(sessions)
    again = step.run_step(setting, "D", BENCH, 1, parent, services=services)
    assert again.record == found.record
    assert (len(fake_solver.requests), len(glm.seen), len(sessions)) == before
    complete_chain_read(setting, services, found, fake_solver, glm, sessions)


def complete_chain_read(setting, services, found, fake_solver, glm, sessions):
    """Resume the actual step through the real chain gate; a fake child opens only the ALF panel."""
    accesses, launches, learns = [], [], []
    fake_panel = [{"benchmark": BENCH, "task_id": "sealed-authored-%d" % n, "partition": "test",
        "public": {"game_file": "/synthetic/json_2.1.1/valid_unseen/pick_and_place_simple-Mug-None-Desk-%d/trial/game.tw-pddl" % n},
        "private": {"game_metadata": {"source_split": "valid_unseen", "asset_files": []}}} for n in range(6)]
    def panel(pinned, bench, *, access):
        assert bench == BENCH and access.unit == "D/test/alfworld"
        accesses.append((bench, access.unit))
        return fake_panel, {"panel_hash": digest(fake_panel), "excluded_without_pages": [], "source_files": None}
    def learn(setting_, root, chain_id, k, bench, parent):
        assert chain_id == "D" and k == 1 and bench == BENCH and not parent.procedures
        learns.append((chain_id, k, bench))
        outcome = step.run_step(setting_, chain_id, bench, k, parent, services=services)
        assert outcome.record == found.record
        return outcome.package, outcome.record
    def launch(setting_, spec):
        launches.append(spec)
        assert spec["bench"] == BENCH
        tasks = evaluation.test_tasks(setting_.shared, {}, BENCH, "D/test/alfworld", run=setting_.run,
            runtime=RUNTIME, native=None, workers=None, evidence=FIXTURE, panel=panel)
        assert tasks == fake_panel
        write_json(Path(spec["unit_root"]) / "unit.json", p.record("evaluation", FIXTURE, {
            "run": setting_.run, "chain": "D", "bench": BENCH, "packages": {"F": spec["package_sha256"]}}))
        return chain.EXIT_COMPLETE
    with pytest.raises(ValueError, match="chain D only"):
        chain.run(setting, "G", learn=learn, launch=launch)
    assert not (setting.root / "G").exists()
    read_root = setting.root / "D"
    before = len(fake_solver.requests), len(glm.seen), len(sessions)
    first = chain.run(setting, "D", learn=learn, launch=launch)
    assert not (setting.shared / "consent.json").exists() and not accesses and not launches
    assert learns == [("D", 1, BENCH)]
    # The real first-call confirmation adds one fixture request; the completed step adds none.
    assert (len(fake_solver.requests), len(glm.seen), len(sessions)) == (before[0] + 1, before[1], before[2])
    if found.package.procedures:
        assert first["status"] == "paused" and first["kind"] == "consent_missing"
        waiting = p.verified(read_json(read_root / chain.READ_WAITING), "read-waiting")
        assert waiting["read_units"] == 1 and waiting["read_attempts"] == 0
        assert not (read_root / "test").exists()
        assert chain.run(setting, "D", learn=learn, launch=launch)["kind"] == "consent_missing"
        assert accesses == [] and launches == [] and not (setting.shared / "consent.json").exists()
        write_json(setting.shared / "consent.json", {**CONSENT, "note": "Authored fixture owner permission."})
        assert chain.run(setting, "D", learn=learn, launch=launch) == {"status": "complete"}
        assert accesses == [(BENCH, "D/test/alfworld")]
        assert [spec["bench"] for spec in launches] == [BENCH]
        status = "read"
    else:
        assert first == {"status": "complete"}
        status = "not_read"
    read = p.verified(read_json(read_root / chain.TEST_READ), "test-read")
    assert read["status"] == status
    marker = p.verified(read_json(read_root / "chain.json"), "chain")
    assert marker["order"] == [BENCH] and marker["configuration"] == p.ALFWORLD_V1
    count = len(fake_solver.requests), len(glm.seen), len(sessions), len(accesses), len(launches), len(learns)
    assert chain.run(setting, "D", learn=learn, launch=launch) == {"status": "complete"}
    assert count == (len(fake_solver.requests), len(glm.seen), len(sessions), len(accesses), len(launches), len(learns))
    assert not any(read_root.glob("s2-*")) and not (read_root / "stage-read").exists()


def test_alf_canaries_read_no_pool_or_panel_before_consent_and_only_alf_after(tmp_path, monkeypatch):
    import hashlib
    pool = tmp_path / "synthetic-pool.json"
    train = [{"task_id": "authored-training", "public": {"game_file":
        "/synthetic/json_2.1.1/train/pick_and_place_simple-Mug-None-Desk-1/trial_TRAIN_SENTINEL/game.tw-pddl"}}]
    panel_rows = [{"task_id": "authored-sealed-%d" % n, "public": {"game_file":
        "/synthetic/json_2.1.1/valid_unseen/pick_and_place_simple-Mug-None-Desk-%d/trial_SEALED_SENTINEL/game.tw-pddl" % n}}
        for n in range(6)]
    write_json(pool, train)
    pinned = {BENCH: {"path": str(pool), "sha256": hashlib.sha256(pool.read_bytes()).hexdigest()}}
    reads, accesses = [], []
    read_bytes, read_text = Path.read_bytes, Path.read_text
    def bytes_spy(path, *args, **kwargs):
        if path == pool:
            reads.append("bytes")
        return read_bytes(path, *args, **kwargs)
    def text_spy(path, *args, **kwargs):
        if path == pool:
            reads.append("text")
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_bytes", bytes_spy)
    monkeypatch.setattr(Path, "read_text", text_spy)
    def panel(pinned, bench, *, access):
        assert bench == BENCH and access.unit == evaluation.READ_CANARY_UNIT
        accesses.append((bench, access.unit))
        return panel_rows, {"panel_hash": digest(panel_rows), "excluded_without_pages": [], "source_files": None}
    root = tmp_path / "root"
    args = {"pools": pinned, "run": "synthetic-alf-only", "evidence": FIXTURE, "panel": panel,
            "order": (BENCH,), "configuration": p.ALFWORLD_V1}
    with pytest.raises(ValueError, match="consent"):
        evaluation.make_read_canaries(root, {}, **args)
    assert reads == accesses == [] and not root.exists()
    write_json(root / "shared" / "consent.json", {**CONSENT, "by": "operator"})
    with pytest.raises(ValueError, match="consent"):
        evaluation.make_read_canaries(root, {}, **args)
    assert reads == accesses == []
    (root / "shared" / "consent.json").unlink()
    write_json(root / "shared" / "consent.json", CONSENT)
    value = evaluation.make_read_canaries(root, {}, **args)
    assert reads == ["bytes", "text"] and accesses == [(BENCH, evaluation.READ_CANARY_UNIT)]
    assert value["counts"] == {BENCH: 5} and value["extends"] is None
    assert value["configuration"] == p.ALFWORLD_V1
    assert "SEALED_SENTINEL" not in json.dumps(value) and "TRAIN_SENTINEL" not in json.dumps(value)
    assert evaluation.load_canaries(root, read=True, configuration=p.ALFWORLD_V1) == value["canaries"]
    assert not (root / p.CANARIES).exists()
    assert evaluation.make_read_canaries(root, {}, **args) == value
    assert reads == ["bytes", "text"] and len(accesses) == 1
    assert not (root / "shared" / "test").exists()
