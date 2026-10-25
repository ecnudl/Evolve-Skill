"""Independent regression cases for the ALF S3 split, using authored replies and in-process workers."""
from dataclasses import replace
import json

import pytest

from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_zpc_pipeline import offline
from tests.test_execskill_alf_v1_pipeline import BENCH, build
from tests.execskill_fakes import FakeSolver, engineer_reply
from skillopt.continual_eval.core import read_json
from skillopt.execskill import alf_smoke as smoke, engineer, profiles as p, replay

BEFORE_ONLY = '''def applies(view):
    return "task_text" in view
def alf_before_step(view, state):
    return {"fields": {"facts": [view["initial_observation"]]}, "discourage": []}
'''
CONSTANT_STATE = BEFORE_ONLY + '''def alf_after_step(event, state):
    return {"facts": {"nothing_happens": 0}, "counter": 0}
'''


def made(tmp_path, monkeypatch, *, response="empty"):
    setting, services, _, roles, _ = build(tmp_path, monkeypatch)
    original = roles.replies
    def role(system, payload):
        if system != engineer.ENGINEER_SYSTEM_ALF_V1:
            return original(system, payload)
        if response == "unusable":
            return "This authored receipt has no parseable proposal."
        if response == "empty":
            return engineer_reply({"changes": []}, [])
        source = BEFORE_ONLY if response == "before_only" else BEFORE_ONLY.replace(
            '{"fields": {"facts": [view["initial_observation"]]}, "discourage": []}',
            '{"fields": {}, "discourage": []}')
        return engineer_reply({"changes": [{"kind": "new", "description": "Retains the initial public task.",
            "hooks": ["alf_before_step", "applies"], "max_note_chars": 4000,
            "excluded_benches": [b for b in p.BENCHES if b != BENCH]}]}, [source])
    roles.replies = role
    def answer(system, user):
        view = json.loads(user)
        return "<action>" + view["admissible_commands"][-1] + "</action>"
    solver = FakeSolver(tmp_path / "review-solver", [(None, answer)],
        max_tokens=p.ELUCID_MAX_TOKENS[BENCH], read_timeout=p.ELUCID_READ_TIMEOUT[BENCH])
    setting = replace(setting, clients=lambda model, bench: roles.client if bench is None else solver.client)
    return setting, services, solver, roles


def checks_of(found):
    return found["proposal"]["checks"]


@pytest.mark.parametrize("response", ["empty", "before_only", "rejected"])
def test_s3_real_role_can_legitimately_choose_no_state_tracker(tmp_path, monkeypatch, response):
    setting, services, solver, roles = made(tmp_path, monkeypatch, response=response)
    found = smoke._s3(setting, services)
    assert found["passed"] and found["failed_substages"] == []
    assert found["S3a"]["passed"] and found["S3b"]["passed"] and found["S3b"]["parsed"]
    role = found["S3b"]
    if response == "before_only":
        assert role["candidate_sha256"] is not None and role["training"]["cells"] > 0
        assert role["training"]["adopted"] is False
        assert all("alf_after_step" not in row["hooks"] for row in role["engineer"]["engineer"]["procedures"])
    else:
        assert role["candidate_sha256"] is None and role["training"] is None
    assert role["role_measurements"]["engineer"]["calls"] > 0
    assert role["role_measurements"]["engineer"]["request_bytes"] > 0
    calls = len(solver.requests), len(roles.seen)
    assert smoke._s3(setting, services) == found
    assert (len(solver.requests), len(roles.seen)) == calls


def test_s3a_executes_the_real_proposal_checks_and_stateful_training_without_role_calls(tmp_path, monkeypatch):
    setting, services, solver, roles = made(tmp_path, monkeypatch)
    parsed, normalized = [], []
    parse, normalize = engineer.parse, engineer._normalize
    def observing(reply, **kwargs):
        result = parse(reply, **kwargs)
        parsed.append((reply, result))
        return result
    def normalizing(change, **kwargs):
        result = normalize(change, **kwargs)
        normalized.extend(change.normalized)
        return result
    monkeypatch.setattr(engineer, "parse", observing)
    monkeypatch.setattr(engineer, "_normalize", normalizing)
    found = smoke._s3a(setting, services)
    assert found["passed"] and parsed and all(smoke.AUTHORED_SOURCE in reply for reply, _ in parsed)
    assert roles.seen == [] and solver.requests
    assert any(row["field"] == "hooks" for row in normalized)
    checks = checks_of(found)
    assert {row["check"] for row in checks} >= {
        "C1", "C2", "C3", "C4", "C5", "C5b", "C6", "C6b", "C6c", "C7", "C8", "C9"}
    assert all(row["passed"] for row in checks)
    checked = next(row["detail"] for row in checks if row["check"] == "C7")["tracker_agreement"]
    assert checked[0] == checked[1] and checked[1] > 0
    assert found["training"]["cells"] > 0
    continuity = found["state_changes"]
    assert continuity["passed"] and continuity["changed"] == continuity["checked"] > 0
    root = setting.root / "D" / "role-smoke" / "S3a"
    trajectories = [p.verified(read_json(path), "trajectory") for path in root.glob("**/trajectories/*.json")]
    candidates = [row for row in trajectories if row["arm_kind"] == "candidate"]
    assert candidates
    assert all(len({json.dumps(step["state_sha256"], sort_keys=True) for step in row["alfworld_steps"]}) > 1
               for row in candidates)


def test_s3a_rejects_constant_state_even_with_declared_stateful_hooks(tmp_path, monkeypatch):
    setting, services, solver, roles = made(tmp_path, monkeypatch)
    monkeypatch.setattr(smoke, "AUTHORED_SOURCE", CONSTANT_STATE)
    found = smoke._s3a(setting, services)
    assert not found["passed"]
    assert all(row["passed"] for row in checks_of(found))
    assert found["training"]["cells"] > 0
    continuity = found["state_changes"]
    assert not continuity["passed"] and continuity["checked"] > 0 and continuity["changed"] == 0
    assert roles.seen == []
    calls = len(solver.requests)
    assert smoke._s3a(setting, services) == found and len(solver.requests) == calls
    combined = smoke._s3(setting, services)
    assert not combined["passed"] and combined["failed_substages"] == ["S3a"]
    assert combined["S3a"] == found and combined["S3b"]["passed"]
    calls = len(solver.requests), len(roles.seen)
    assert smoke._s3(setting, services) == combined
    assert (len(solver.requests), len(roles.seen)) == calls


def test_unusable_real_reply_fails_only_s3b_and_resume_keeps_both_completed_substages(tmp_path, monkeypatch):
    setting, services, solver, roles = made(tmp_path, monkeypatch, response="unusable")
    found = smoke._s3(setting, services)
    assert found["passed"] is False and found["failed_substages"] == ["S3b"]
    assert found["S3a"]["passed"] and not found["S3b"]["passed"] and not found["S3b"]["parsed"]
    assert found["S3b"]["role_measurements"]["engineer"]["calls"] > 0
    calls = len(solver.requests), len(roles.seen)
    roles.replies = lambda system, payload: pytest.fail("A completed failed substage must not call a role again")
    assert smoke._s3(setting, services) == found
    assert (len(solver.requests), len(roles.seen)) == calls


def test_every_authored_episode_matches_intended_reference_and_proposal_facts_including_rejection():
    intended = [
        {"reached": [], "carrying": [], "nothing_happens": 1},
        {"reached": ["table 1"], "carrying": [], "nothing_happens": 1},
        {"reached": ["table 1"], "carrying": ["mug 1"], "nothing_happens": 1},
        {"reached": ["shelf 1", "table 1"], "carrying": ["mug 1"], "nothing_happens": 1},
        {"reached": ["shelf 1", "table 1"], "carrying": [], "nothing_happens": 1},
    ]
    namespace = {}
    exec(compile(smoke.AUTHORED_SOURCE, "<authored-s3-tracker>", "exec"), namespace)
    for item in smoke.fixture_items({"max_steps": 50}):
        env = smoke._FixtureEnv(item["public"])
        observations, _, _ = env.reset()
        tracker, state = replay.ReferenceTracker(observations[0]), None
        commands = ["take mug 1 from shelf 1", "go to table 1", "take mug 1 from table 1", "go to shelf 1",
                    "put mug 1 in/on shelf 1"]
        for index, (command, expected) in enumerate(zip(commands, intended)):
            observations, _, _, done, info = env.step([command])
            observation = observations[0]
            tracker.update(command, observation)
            event = {"step": index, "action": command, "observation": observation,
                     "admissible_commands": info[0]["admissible_commands"]}
            state = namespace["alf_after_step"](event, state)
            assert tracker.facts() == state["facts"] == expected
            assert state["counter"] == index + 1
            assert done[0] is (index == len(commands) - 1)
        env.close()
