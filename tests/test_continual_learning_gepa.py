"""Isolated learner contracts plus an optional real, pinned GEPA fixture engine."""
import importlib.util
import os
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning.contracts import manifest, validate_manifest
from skillopt.continual_learning.gepa import Adapter, run_stage
from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending, Ledger
from skillopt.validator_pilot.api import digest


def panel():
    return {"version": "continual-panel-v1", "benchmark": "bigcodebench", "dataset_revision": "fixture-v1",
            "provenance": "fixture", "tasks": [
                {"task_id": name, "family_id": name, "project_id": "", "partition": "development",
                 "public": {"prompt": "Implement solve; preserve inputs and handle empty values.", "entry_point": "solve"},
                 "private": {"test": "PRIVATE_TEST_CANARY_DO_NOT_PROMPT"}}
                for name in ("train-a", "train-b", "selection-c", "selection-d")]}


def plan(data=None, **overrides):
    budget = {"max_metric_calls": 30, "max_reflection_calls": 5, "max_api_calls": 40,
              "max_reported_tokens": 100000, "max_iterations": 2, "minibatch_size": 2,
              "solver_max_tokens": 256, "reflection_max_tokens": 256}
    budget.update(overrides.pop("budget", {}))
    args = {"train_families": ["train-a", "train-b"], "selection_families": ["selection-c", "selection-d"],
            "model": {"provider": "fixture", "name": "fixture", "max_tokens": 256, "reasoning_effort": "low"},
            "budget": budget}
    args.update(overrides)
    return manifest(data or panel(), **args)


class FixtureAPI:
    model = "fixture"
    service = {"provider": "fixture", "transport": "offline", "model": "fixture"}

    def __init__(self, response="```\nHandle empty inputs.\n```", *, error=False, missing_usage=False):
        self.calls = []
        self.response, self.error, self.missing_usage = response, error, missing_usage

    def call(self, system, user, kind, key, max_tokens, repeat):
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        self.calls.append(request)
        assert "PRIVATE_TEST_CANARY" not in user
        return {"request": request, "request_hash": digest(request), "ok": not self.error,
                "response": self.response, "finish_reason": "stop", "status": 503 if self.error else 200,
                "http_attempt_count": 1, "usage": {} if self.missing_usage else
                    {"prompt_tokens": 100, "completion_tokens": 10}}


def fixture_evaluate(task, skill):
    passed = "Handle empty inputs." in skill
    return ({"status": "available", "output": "fixture-code", "reason": "authored_fixture"},
            {"status": "pass" if passed else "fail", "score": float(passed), "metrics": {},
             "reason": "authored_fixture_not_native_execution"})


@pytest.fixture
def official_source():
    root = Path(__file__).resolve().parents[1]
    source = Path(os.environ.get("GEPA_OFFICIAL_SOURCE", root / "outputs/continual_eval/baseline_preparation_20260928/gepa"))
    if not source.is_dir() or importlib.util.find_spec("gepa") is None:
        pytest.skip("Optional pinned GEPA not installed; run in the dedicated baseline preparation venv")
    return source


@pytest.mark.parametrize("partition", ["final", "verifier_calibration", "skill_confirmation"])
def test_forbidden_partition(partition):
    data = panel()
    data["tasks"][0]["partition"] = partition
    with pytest.raises(ValueError, match="Only development"):
        plan(data)


def test_family_and_project_boundaries():
    with pytest.raises(ValueError, match="overlap"):
        plan(selection_families=["train-a", "selection-c", "selection-d"])
    with pytest.raises(ValueError, match="Every development family"):
        plan(train_families=["train-a"])
    data = panel()
    data["tasks"][0]["project_id"] = "same-project"
    data["tasks"][2]["project_id"] = "same-project"
    with pytest.raises(ValueError, match="Project crosses"):
        plan(data)


def test_skill_limit_bytes_and_method():
    with pytest.raises(ValueError, match="6000"):
        plan(parent_skill="中" * 2001)
    assert plan(method="skillopt")["method"] == "skillopt"
    with pytest.raises(ValueError, match="Unsupported learning method"):
        plan(method="renamed_reflexion")


def test_changed_manifest_or_tasks():
    data = panel()
    value = plan(data)
    changed = deepcopy(data)
    changed["tasks"][0]["private"]["test"] += "changed"
    with pytest.raises(ValueError, match="changed"):
        validate_manifest(value, changed)


@pytest.mark.parametrize("change", ["final", "role", "private", "public"])
def test_adapter_rejects_unapproved_tasks(tmp_path, change):
    value = plan()
    adapter = Adapter(value, tmp_path, Ledger(tmp_path, value, FixtureAPI()), fixture_evaluate=fixture_evaluate)
    task = panel()["tasks"][0]
    role = "train"
    if change == "final":
        task["partition"] = "final"
    elif change == "role":
        role = "selection"
    else:
        key = "test" if change == "private" else "prompt"
        task[change][key] += "changed"
    with pytest.raises(ValueError, match="not authorized"):
        adapter.evaluate_rows([{"role": role, "task": task}], {"skill": ""})


def test_adapter_unknown_is_not_zero(tmp_path):
    value = plan()
    def unknown(task, skill):
        return ({"status": "unknown", "output": None, "reason": "timeout"},
                {"status": "unknown", "score": None, "reason": "timeout", "metrics": {}})
    adapter = Adapter(value, tmp_path, Ledger(tmp_path, value, FixtureAPI()), fixture_evaluate=unknown)
    with pytest.raises(LearningPending, match="evaluation_unknown"):
        adapter.evaluate_rows([{"role": "train", "task": panel()["tasks"][0]}], {"skill": ""})
    stored = read_json(next((tmp_path / "evaluations").glob("*.json")), sealed=True)
    assert stored["score"]["score"] is None


def test_ledger_cache_budget_and_cost(tmp_path):
    api = FixtureAPI()
    value = plan(budget={"max_api_calls": 1})
    ledger = Ledger(tmp_path, value, api)
    first = ledger.call("reflection", "0", "system", "user", 256)
    assert ledger.call("reflection", "0", "system", "user", 256) == first
    assert len(api.calls) == 1
    assert ledger.snapshot()["reported_tokens_known_subtotal"] == 110
    with pytest.raises(BudgetExhausted, match="max_api_calls"):
        ledger.call("reflection", "1", "system", "new", 256)
    with pytest.raises(ValueError, match="output cap"):
        ledger.call("reflection", "2", "system", "new", 257)


def test_missing_usage_and_interruption(tmp_path):
    value = plan()
    ledger = Ledger(tmp_path, value, FixtureAPI(missing_usage=True))
    ledger.call("reflection", "0", "system", "user", 256)
    assert ledger.snapshot()["missing_usage_calls"] == 1
    with pytest.raises(LearningPending, match="usage_or_receipt_unknown"):
        ledger.call("reflection", "1", "system", "new", 256)


def test_token_stop_and_unknown_retry_cost(tmp_path):
    value = plan(budget={"max_reported_tokens": 100})
    ledger = Ledger(tmp_path, value, FixtureAPI())
    ledger.call("reflection", "0", "system", "user", 256)
    assert ledger.snapshot()["reported_tokens_known_subtotal"] == 110
    with pytest.raises(BudgetExhausted, match="token_stop"):
        ledger.call("reflection", "1", "system", "next", 256)


def test_foreign_receipt_is_preserved_as_unclosed_intent(tmp_path):
    class WrongReceipt(FixtureAPI):
        def call(self, *args, **kwargs):
            receipt = super().call(*args, **kwargs)
            receipt["request"]["user"] = "other position"
            receipt["request_hash"] = digest(receipt["request"])
            return receipt
    value, api = plan(), WrongReceipt()
    ledger = Ledger(tmp_path, value, api)
    with pytest.raises(ValueError, match="does not bind"):
        ledger.call("reflection", "0", "system", "user", 256)
    assert ledger.snapshot()["unclosed_calls"] == 1
    with pytest.raises(LearningPending, match="interrupted_model_call"):
        ledger.call("reflection", "0", "system", "user", 256)
    assert len(api.calls) == 1


def test_real_official_engine_and_completed_replay(tmp_path, official_source):
    data, api = panel(), FixtureAPI()
    value = plan(data)
    result = run_stage(value, data, tmp_path, gepa_source=official_source,
                       fixture_api=api, fixture_evaluate=fixture_evaluate)
    assert result["status"] == "completed", result
    assert result["candidate_skill"] == "Handle empty inputs."
    assert len(result["official_result"]["candidates"]) >= 2
    assert result["official_result"]["val_aggregate_scores"][:2] == [0.0, 1.0]
    assert result["evidence_kind"] == "engineering_fixture"
    assert result["deployment_authorized"] is False
    assert len(api.calls) == 1
    replay_api = FixtureAPI()
    replay = run_stage(value, data, tmp_path, gepa_source=official_source,
                       fixture_api=replay_api, fixture_evaluate=fixture_evaluate)
    assert replay == result and not replay_api.calls


def test_reflection_failure_pending(tmp_path, official_source):
    api = FixtureAPI(error=True)
    result = run_stage(plan(), panel(), tmp_path, gepa_source=official_source,
                       fixture_api=api, fixture_evaluate=fixture_evaluate)
    assert result["status"] == "pending"
    assert result["reason"] == "reflection_unavailable"
    assert result["costs"]["terminal_calls"] == 1
    assert len(api.calls) == 1  # Native proposer catches exceptions; host latch prevents another call.


def test_reflection_failure_stops_future_solver_batches(tmp_path, official_source):
    data = panel()
    for name in ("train-e", "train-f"):
        task = deepcopy(data["tasks"][0])
        task.update(task_id=name, family_id=name)
        data["tasks"].append(task)
    value = plan(data, train_families=["train-a", "train-b", "train-e", "train-f"],
                 budget={"max_iterations": 4})
    evaluations = []
    def counted(task, skill):
        evaluations.append(task["task_id"])
        return fixture_evaluate(task, skill)
    result = run_stage(value, data, tmp_path, gepa_source=official_source,
                       fixture_api=FixtureAPI(error=True), fixture_evaluate=counted)
    assert result["status"] == "pending"
    assert len(evaluations) == 4  # Two seed selection + one two-task parent minibatch only.


def test_natural_run_forbids_fixture_injection(tmp_path, official_source):
    data = panel()
    data["provenance"] = "natural"
    value = plan(data, model={"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 256,
                              "reasoning_effort": "low"})
    with pytest.raises(ValueError, match="Fixture callbacks"):
        run_stage(value, data, tmp_path, gepa_source=official_source,
                  fixture_api=FixtureAPI(), fixture_evaluate=fixture_evaluate)


def test_unknown_engine_keeps_parent_without_reflection(tmp_path, official_source):
    def unknown(task, skill):
        return ({"status": "available", "output": "code", "reason": "fixture"},
                {"status": "unknown", "score": None, "reason": "runtime_unavailable", "metrics": {}})
    api = FixtureAPI()
    result = run_stage(plan(), panel(), tmp_path, gepa_source=official_source,
                       fixture_api=api, fixture_evaluate=unknown)
    assert result["status"] == "pending" and result["candidate_skill"] == ""
    assert not api.calls


def test_oversized_candidate_not_deployed(tmp_path, official_source):
    result = run_stage(plan(), panel(), tmp_path, gepa_source=official_source,
                       fixture_api=FixtureAPI("```\n" + "x" * 6001 + "\n```"), fixture_evaluate=fixture_evaluate)
    assert result["status"] == "pending"
    assert result["candidate_skill"] == ""
    assert result["reason"] == "invalid_candidate_skill_length"


def test_interrupted_stage_never_resamples(tmp_path, official_source):
    class Interrupted(FixtureAPI):
        def call(self, *args, **kwargs):
            raise KeyboardInterrupt
    value = plan()
    with pytest.raises(KeyboardInterrupt):
        run_stage(value, panel(), tmp_path, gepa_source=official_source,
                  fixture_api=Interrupted(), fixture_evaluate=fixture_evaluate)
    api = FixtureAPI()
    result = run_stage(value, panel(), tmp_path, gepa_source=official_source,
                       fixture_api=api, fixture_evaluate=fixture_evaluate)
    assert result["status"] == "pending" and not api.calls
    assert result["model_calls_submitted"] == 0
    assert Ledger(tmp_path, value, api).snapshot()["unclosed_calls"] == 1


def test_evaluation_cache_requires_intent(tmp_path):
    value, task = plan(), panel()["tasks"][0]
    adapter = Adapter(value, tmp_path, Ledger(tmp_path, value, FixtureAPI()), fixture_evaluate=fixture_evaluate)
    request = {"manifest_hash": value["record_hash"], "candidate_hash": digest({"skill": ""}),
               "task_hash": digest(task), "role": "train", "repeat": 0}
    prediction, score = fixture_evaluate(task, "")
    write_json(tmp_path / "evaluations" / (digest(request) + ".json"),
               seal({"request": request, "prediction": prediction, "score": score}))
    with pytest.raises(FileNotFoundError):
        adapter.evaluate_rows([{"role": "train", "task": task}], {"skill": ""})
