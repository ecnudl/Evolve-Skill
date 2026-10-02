"""Native SkillOpt engineering controls, never natural method-effect evidence."""
import json
from copy import deepcopy

import pytest

from skillopt.continual_learning.contracts import manifest
from skillopt.continual_learning.skillopt import native_sources, propose_native, run_stage
from skillopt.validator_pilot.api import digest


def setup(*, iterations=1):
    panel = {"version": "continual-panel-v1", "benchmark": "bigcodebench", "dataset_revision": "fixture-v1",
             "provenance": "fixture", "tasks": [
                 {"task_id": str(i), "family_id": str(i), "project_id": "", "partition": "development",
                  "public": {"prompt": "Fixture: return one.", "entry_point": "f"},
                  "private": {"test": "HIDDEN_TEST_DO_NOT_PROJECT"}} for i in range(4)]}
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 100, "reasoning_effort": "low"}
    budget = {"max_metric_calls": 24, "max_reflection_calls": 10, "max_api_calls": 20,
              "max_reported_tokens": 10000, "max_iterations": iterations, "minibatch_size": 2,
              "solver_max_tokens": 100, "reflection_max_tokens": 100}
    auth = manifest(panel, train_families=["0", "1"], selection_families=["2", "3"],
                    model=model, budget=budget, method="skillopt")
    return auth, panel


class API:
    model = "fixture"
    service = {"fixture": "native-skillopt-test"}

    def __init__(self, mode="valid"):
        self.mode, self.calls = mode, []

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        self.calls.append(request)
        assert "HIDDEN_TEST_DO_NOT_PROJECT" not in system + user
        content = "Use the requested constant result."
        if self.mode == "oversize":
            content = "x" * 6001
        response = {"batch_size": 2, "patch": {"reasoning": "Fixture evidence", "edits": [
            {"op": "append", "content": content}]}}
        raw = "not JSON" if self.mode == "invalid_json" else json.dumps(response)
        return {"request": request, "request_hash": digest(request), "response": raw,
                "ok": self.mode != "failed", "finish_reason": "stop" if self.mode != "truncated" else "length",
                "usage": {"prompt_tokens": 20, "completion_tokens": 20}, "http_attempt_count": 1}


def evaluate(task, skill):
    correct = "requested constant" in skill
    return ({"status": "available", "output": "def f(): return 1" if correct else "def f(): return 0", "reason": "fixture"},
            {"status": "pass" if correct else "fail", "score": float(correct), "metrics": {}, "reason": "fixture"})


def test_sources_include_real_native_files():
    sources = native_sources()
    assert len(sources) >= 16
    assert all(len(value) == 64 for value in sources.values())


def test_real_native_reflection_patch_gate_and_completed_replay(tmp_path):
    auth, panel = setup()
    api = API()
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate)
    assert result["status"] == "completed", result
    assert result["initial_selection_score"] == 0
    assert result["selected_score"] == 1
    assert result["steps"][0]["gate_action"] == "accept_new_best"
    assert "requested constant" in result["candidate_skill"]
    assert result["evidence_kind"] == "engineering_fixture"
    assert not result["deployment_authorized"]
    assert len(api.calls) == 1
    replay = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate)
    assert replay == result and len(api.calls) == 1


@pytest.mark.parametrize("mode", ["failed", "truncated", "invalid_json", "oversize"])
def test_bad_optimizer_response_cannot_become_completed(tmp_path, mode):
    auth, panel = setup()
    result = run_stage(auth, panel, tmp_path, fixture_api=API(mode), fixture_evaluate=evaluate)
    assert result["status"] == "pending"
    assert result["candidate_skill"] == ""
    assert len(result["steps"]) == 0


def test_unknown_is_not_zero_or_reasoning_error(tmp_path):
    auth, panel = setup()
    api = API()
    def unknown(task, skill):
        return {"status": "unknown", "output": None, "reason": "runtime_unavailable"}, {
            "status": "unknown", "score": None, "reason": "fixture", "metrics": {}}
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=unknown)
    assert result["status"] == "pending"
    assert result["costs"]["logical_calls"] == 0
    assert not api.calls


def test_native_gate_rejects_tie_not_rename_learning_gain(tmp_path):
    auth, panel = setup()
    def same(task, skill):
        return {"status": "available", "output": "def f(): return 1", "reason": "fixture"}, {
            "status": "pass", "score": 1.0, "metrics": {}, "reason": "fixture"}
    result = run_stage(auth, panel, tmp_path, fixture_api=API(), fixture_evaluate=same)
    assert result["status"] == "completed"
    assert result["steps"][0]["gate_action"] == "reject"
    assert result["candidate_skill"] == ""


def test_final_or_other_method_manifest_rejected(tmp_path):
    auth, panel = setup()
    final = deepcopy(panel)
    final["tasks"][0]["partition"] = "final"
    with pytest.raises(ValueError):
        run_stage(auth, final, tmp_path, fixture_api=API(), fixture_evaluate=evaluate)
    auth.pop("record_hash")
    auth["method"] = "gepa"
    from skillopt.coevolution_v5.core import seal
    with pytest.raises(ValueError):
        run_stage(seal(auth), panel, tmp_path, fixture_api=API(), fixture_evaluate=evaluate)


def test_native_proposal_evidence_tamper_blocks_replay(tmp_path):
    auth, panel = setup()
    run_stage(auth, panel, tmp_path, fixture_api=API(), fixture_evaluate=evaluate)
    path = tmp_path / "native/0/result.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="evidence changed"):
        run_stage(auth, panel, tmp_path, fixture_api=API(), fixture_evaluate=evaluate)


@pytest.mark.parametrize("mutation", ["hash", "selection", "parent", "output", "public"])
def test_foreign_or_relabelled_feedback_cannot_reach_native_reflection(tmp_path, mutation):
    from skillopt.continual_eval.core import write_json
    from skillopt.continual_learning.gepa import Adapter
    from skillopt.continual_learning.ledger import Ledger
    auth, panel = setup()
    api = API()
    ledger = Ledger(tmp_path, auth, api)
    write_json(tmp_path / "panel.json", panel)
    role = "selection" if mutation == "selection" else "train"
    task = panel["tasks"][2 if role == "selection" else 0]
    row = Adapter(auth, tmp_path, ledger, fixture_evaluate=evaluate).evaluate_rows(
        [{"role": role, "task": task}], {"skill": ""})[0]
    trace = {**row["trajectory"], "evidence_hash": row["output"]["evidence_hash"]}
    if mutation == "hash":
        trace["evidence_hash"] = "0" * 64
    if mutation == "output":
        trace["Generated Outputs"] = "different actual output"
    if mutation == "public":
        trace["Inputs"] = {"prompt": "different contract", "entry_point": "f"}
    with pytest.raises(ValueError):
        propose_native("different parent" if mutation == "parent" else "", [trace],
                       tmp_path / "proposal", ledger)
    assert not api.calls


def test_optimizer_modules_restored_after_failure(tmp_path):
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    modules = (reflect, aggregate, clip)
    originals = [m.chat_optimizer for m in modules]
    auth, panel = setup()
    result = run_stage(auth, panel, tmp_path, fixture_api=API("failed"), fixture_evaluate=evaluate)
    assert result["status"] == "pending"
    assert [m.chat_optimizer for m in modules] == originals


def test_real_native_merge_and_rank_are_not_replaced_by_one_reflection(tmp_path):
    from skillopt.continual_eval.core import read_json
    auth, panel = setup()
    class MergeAPI(API):
        def call(self, system, user, kind, key, **kwargs):
            receipt = super().call(system, user, kind, key, **kwargs)
            if "Two pre-merged patch groups" in user:
                receipt["response"] = json.dumps({"reasoning": "fixture merged", "edits": [
                    {"op": "append", "content": f"Use the requested constant result. Rule {i}."} for i in range(5)]})
            elif "Pool (" in user and "selected_indices" in system:
                receipt["response"] = json.dumps({"selected_indices": [0, 1, 2, 3]})
            return receipt
    def mixed(task, skill):
        prediction, score = evaluate(task, skill)
        if task["task_id"] == "0":
            prediction = {"status": "available", "output": "def f(): return 1", "reason": "fixture"}
            score = {"status": "pass", "score": 1.0, "reason": "fixture", "metrics": {}}
        return prediction, score
    api = MergeAPI()
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=mixed)
    assert result["status"] == "completed", result
    assert len(api.calls) == 4  # Failure + success reflection, merge, ranking.
    proposal = read_json(tmp_path / "native/0/result.json", sealed=True)
    assert len(proposal["raw"]) == 2
    assert len(proposal["merged"]["edits"]) == 5
    assert len(proposal["selected"]["edits"]) == 4
    assert "optimizer-ranked" in proposal["selected"]["reasoning"]


def test_zero_update_is_completed_without_claiming_improvement(tmp_path):
    auth, panel = setup()
    class NoUpdateAPI(API):
        def call(self, *args, **kwargs):
            receipt = super().call(*args, **kwargs)
            receipt["response"] = json.dumps({"patch": {"reasoning": "No evidence", "edits": []}})
            return receipt
    result = run_stage(auth, panel, tmp_path, fixture_api=NoUpdateAPI(), fixture_evaluate=evaluate)
    assert result["status"] == "completed", result
    assert result["candidate_skill"] == "" and result["selected_score"] == 0
    assert result["steps"][0]["gate_action"] == "reject"
