"""Authored ALF fixtures only: no API, native worker, or real environment."""
import json
from copy import deepcopy

import pytest

from skillopt.continual_eval import backends as b
from skillopt.continual_eval.core import freeze_plan, load_plan
from skillopt.continual_eval.fixtures import fixture_config

TRACE = {"alfworld_trace_version": b.ALFWORLD_TRACE_VERSION}


class Episode:
    def __init__(self, *, win_at=None, done_at=None, step_error=None, close_error=False,
                 missing_won=False, post=None):
        self.win_at, self.done_at = win_at, done_at
        self.step_error, self.close_error = step_error, close_error
        self.missing_won, self.post = missing_won, post
        self.actions, self.closed = [], False

    def reset(self):
        return ["Your task is a public goal. 初始观察"], None, [{
            "admissible_commands": ["look"], "expert_plan": "PRIVATE_EXPERT", "won": False}]

    def step(self, actions):
        self.actions.append(actions)
        n = len(self.actions)
        if n == self.step_error:
            raise RuntimeError("PRIVATE_EXCEPTION_PAYLOAD")
        info = {"admissible_commands": ["look"], "expert_plan": "PRIVATE_EXPERT",
                "reward": "PRIVATE_INFO_REWARD", "other": {"hidden": "PRIVATE_OTHER"}}
        if not self.missing_won:
            info["won"] = n == self.win_at
        obs = self.post if self.post is not None else [f"Actual public observation {n} 观察"]
        return obs, "PRIVATE_EXTRA", ["PRIVATE_REWARD"], [n == self.done_at], [info]

    def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("PRIVATE_CLOSE_PAYLOAD")


def run(monkeypatch, env, *, runtime=None, skill="Frozen test guidance", bad_at=None, bad="invalid"):
    prompts = []
    monkeypatch.setattr(b, "_new_alfworld", lambda *_: env)

    def call(system, user):
        prompts.append((system, user))
        if len(prompts) == bad_at:
            if bad == "unavailable":
                return {"ok": False, "usage": {}, "response": "", "finish_reason": None}
            if bad == "length":
                return {"ok": True, "usage": {}, "response": "look", "finish_reason": "length"}
            return {"ok": True, "usage": {}, "response": "<action>  </action>", "finish_reason": "stop"}
        return {"ok": True, "usage": {"prompt_tokens": 3, "completion_tokens": 4},
                "response": "<action> look </action>", "finish_reason": "stop"}

    prediction = b.solve("alfworld", {"game_file": "authored_fixture", "expert_plan": "PRIVATE_TASK"},
                         skill, call, runtime=runtime or {})
    return prediction, prompts


@pytest.mark.parametrize("win_at,done_at,max_steps,skill", [
    (1, None, 50, ""), (8, None, 50, "Frozen test guidance"),
    (50, None, 50, "Frozen test guidance"),
    (None, 9, 50, ""), (None, None, 50, "Frozen test guidance"),
])
def test_new_logging_preserves_every_model_byte_action_budget_and_score(monkeypatch, win_at, done_at, max_steps, skill):
    legacy_env = Episode(win_at=win_at, done_at=done_at)
    new_env = Episode(win_at=win_at, done_at=done_at)
    legacy, before = run(monkeypatch, legacy_env, runtime={"max_steps": max_steps}, skill=skill)
    new, after = run(monkeypatch, new_env, runtime={"max_steps": max_steps, **TRACE}, skill=skill)
    assert before == after  # Entire actual system/user strings, not parsed equivalence.
    assert legacy_env.actions == new_env.actions
    assert legacy_env.closed and new_env.closed
    assert {k: v for k, v in legacy.items() if k != "trace"} == {
        k: v for k, v in new.items() if k not in {"trace", "trace_version"}}
    assert b.score("alfworld", {}, {}, legacy) == b.score("alfworld", {}, {}, new)
    assert "trace_version" not in legacy
    assert new["trace_version"] == b.ALFWORLD_TRACE_VERSION
    assert len(new["trace"]) == new["output"]["steps"] == len(after)
    for index, ((_, user), old_row, new_row) in enumerate(zip(after, legacy["trace"], new["trace"])):
        view = json.loads(user)
        assert view["recent_history"] == legacy["trace"][max(0, index-5):index]
        assert all(list(r) == ["observation", "action"] for r in view["recent_history"])
        assert {k: new_row[k] for k in ("observation", "action")} == old_row
        assert new_row["post_observation"] == f"Actual public observation {index+1} 观察"
        assert new_row["post_observation_status"] == "complete"
    assert new["trace"][-1]["post_observation"] == f"Actual public observation {len(after)} 观察"
    assert "PRIVATE_" not in json.dumps(after + [new["trace"]])
    assert not any(k in row for row in new["trace"] for k in ("won", "reward", "info", "expert_plan"))


def test_legacy_prompt_golden_bytes_and_return_shape_are_unchanged(monkeypatch):
    prediction, prompts = run(monkeypatch, Episode(win_at=8), skill="")
    history = []
    initial = "Your task is a public goal. 初始观察"
    for index, pair in enumerate(prompts):
        observation = initial if index == 0 else f"Actual public observation {index} 观察"
        expected_view = {"initial_observation": initial, "observation": observation,
                         "admissible_commands": ["look"], "recent_history": history[-5:]}
        assert pair == ("Act in the text environment. Return a single action inside <action>...</action>.",
                        json.dumps(expected_view, ensure_ascii=False))
        history.append({"observation": observation[:12000], "action": "look"})
    assert prediction == {"status": "available", "output": {"won": True, "steps": 8},
        "reason": "fresh_native_episode_completed", "costs": {"calls": 8,
        "usage_by_call": [{"prompt_tokens": 3, "completion_tokens": 4}] * 8}, "trace": history}


@pytest.mark.parametrize("bad", ["invalid", "unavailable", "length"])
def test_model_or_action_unknown_keeps_prior_observed_transitions(monkeypatch, bad):
    new, prompts = run(monkeypatch, Episode(), runtime=TRACE, bad_at=3, bad=bad)
    assert new["status"] == "unknown" and len(prompts) == 3
    assert len(new["trace"]) == 2
    assert new["trace"][-1]["post_observation"] == "Actual public observation 2 观察"
    legacy, legacy_prompts = run(monkeypatch, Episode(), bad_at=3, bad=bad)
    assert legacy_prompts == prompts
    assert new["reason"] == legacy["reason"] and new["costs"] == legacy["costs"]
    if bad == "invalid":
        assert "trace" not in legacy  # Historical missing-trace behavior stays unchanged.


def test_step_exception_retains_attempt_without_inventing_post_observation(monkeypatch):
    env = Episode(step_error=3)
    prediction, prompts = run(monkeypatch, env, runtime=TRACE)
    assert prediction["status"] == "unknown"
    assert prediction["reason"] == "alfworld_environment_error:RuntimeError"
    assert len(prompts) == len(prediction["trace"]) == 3 and env.closed
    assert prediction["trace"][-2]["post_observation_status"] == "complete"
    assert prediction["trace"][-1]["post_observation"] is None
    assert prediction["trace"][-1]["post_observation_status"] == "missing"
    assert prediction["trace"][-1]["post_observation_reason"] == "step_result_unavailable"
    assert "PRIVATE_" not in json.dumps(prediction)
    legacy, old_prompts = run(monkeypatch, Episode(step_error=3))
    assert old_prompts == prompts and legacy["reason"] == prediction["reason"]


def test_cleanup_unknown_keeps_the_last_actual_observation(monkeypatch):
    prediction, _ = run(monkeypatch, Episode(win_at=1, close_error=True), runtime=TRACE)
    assert prediction["status"] == "unknown" and prediction["reason"] == "alfworld_cleanup_unconfirmed"
    assert prediction["trace"][-1]["post_observation"] == "Actual public observation 1 观察"
    assert prediction["trace"][-1]["post_observation_status"] == "complete"
    assert "PRIVATE_" not in json.dumps(prediction)


def test_missing_won_keeps_public_post_observation_without_inferring_success(monkeypatch):
    prediction, _ = run(monkeypatch, Episode(missing_won=True), runtime=TRACE)
    assert prediction["reason"] == "native_won_signal_missing" and prediction["output"] is None
    assert prediction["trace"][-1]["post_observation_status"] == "complete"
    legacy, _ = run(monkeypatch, Episode(missing_won=True))
    assert "trace" not in legacy


@pytest.mark.parametrize("post", [[], [None], [{"secret": "PRIVATE_NONOBSERVATION"}]])
def test_absent_or_nontext_observation_is_missing_not_stringified(monkeypatch, post):
    prediction, _ = run(monkeypatch, Episode(win_at=1, post=post), runtime=TRACE)
    row = prediction["trace"][-1]
    assert row["post_observation"] is None and row["post_observation_characters"] is None
    assert row["post_observation_status"] == "missing"
    assert "PRIVATE_" not in json.dumps(prediction)


@pytest.mark.parametrize("count,status", [(0, "complete"), (12000, "complete"), (12001, "truncated")])
def test_public_observation_character_bound_is_explicit_without_changing_prompts(monkeypatch, count, status):
    text = "界" * count
    new, prompts = run(monkeypatch, Episode(done_at=2, post=[text]), runtime=TRACE)
    legacy, old_prompts = run(monkeypatch, Episode(done_at=2, post=[text]))
    assert prompts == old_prompts
    row = new["trace"][-1]
    assert row["post_observation"] == text[:12000]
    assert row["post_observation_status"] == status
    assert row["post_observation_characters"] == count
    assert legacy["output"] == new["output"]


@pytest.mark.parametrize("version", [False, True, 1, "v2", {}, []])
def test_invalid_profile_never_starts_episode_or_model(monkeypatch, version):
    monkeypatch.setattr(b, "_new_alfworld", lambda *_: pytest.fail("Must not start native episode"))
    prediction = b.solve("alfworld", {"game_file": "fixture"}, "", lambda *_: pytest.fail("No model call"),
                         runtime={"alfworld_trace_version": version})
    assert prediction["reason"] == "invalid_alfworld_trace_version"


def test_trace_option_is_bound_by_existing_frozen_runtime_protocol(tmp_path):
    config = fixture_config(tmp_path/"data")
    legacy = freeze_plan(config, tmp_path/"legacy")
    updated = deepcopy(config)
    updated["runtime"]["alfworld"] = {**updated["runtime"].get("alfworld", {}), **TRACE}
    new = freeze_plan(updated, tmp_path/"new")
    assert load_plan(tmp_path/"new") == new
    assert new["config"]["runtime"]["alfworld"]["alfworld_trace_version"] == b.ALFWORLD_TRACE_VERSION
    assert new["record_hash"] != legacy["record_hash"]
    assert "alfworld_trace_version" not in legacy["config"]["runtime"].get("alfworld", {})
