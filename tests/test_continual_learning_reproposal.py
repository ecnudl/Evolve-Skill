"""Frozen-evidence branch fixtures; no real models, benchmarks, or containers."""
import json
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json
from skillopt.continual_learning import reproposal, skillopt
from skillopt.continual_learning.contracts import manifest
from skillopt.continual_learning.ledger import Ledger
from skillopt.validator_pilot.api import digest


class API:
    model = "fixture"
    service = {"provider": "fixture", "model": "fixture", "transport": "offline"}

    def __init__(self, malformed=(), empty_merge=False):
        self.calls, self.malformed, self.empty_merge = [], set(malformed), empty_merge

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        assert "HIDDEN_TEST_SENTINEL" not in system + user
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        index = len(self.calls)
        self.calls.append(request)
        patch = {"reasoning": "Authored fixture evidence", "edits": [{"op": "append", "content": "Check boundaries."}]}
        if self.empty_merge and index >= 2:
            patch["edits"] = []
        body = {"batch_size": 8, "patch": patch, **patch}
        return {"request": request, "request_hash": digest(request), "ok": True, "finish_reason": "stop",
                "response": "not JSON" if index in self.malformed else json.dumps(body),
                "http_attempt_count": 1, "usage": {"prompt_tokens": 10, "completion_tokens": 20}}


def fixture_score(task, skill):
    i = int(task["task_id"])
    success = "Check boundaries." in skill or (i < 36 if i < 65 else i < 98)
    return ({"status": "available", "output": "def solve(): return 1", "reason": "authored_fixture"},
            {"status": "pass" if success else "fail", "score": float(success),
             "metrics": {}, "reason": "fixture_not_native_evidence"})


def parent_run(tmp_path, *, max_reported_tokens=2000000):
    tasks = [{"task_id": str(i), "family_id": str(i if i != 64 else 0), "project_id": "",
              "partition": "development", "public": {"prompt": "Authored fixture: implement solve.", "entry_point": "solve"},
              "private": {"test": "HIDDEN_TEST_SENTINEL"}} for i in range(129)]
    panel = {"version": "continual-panel-v1", "benchmark": "bigcodebench", "dataset_revision": "authored-reproposal-v1",
             "provenance": "fixture", "tasks": tasks}
    model = {"provider": "fixture", "name": "fixture", "reasoning_effort": "low", "max_tokens": 65536,
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                           "initial_health_policy": "completed_response_v1"}}
    budget = {"max_metric_calls": 512, "max_reflection_calls": 32, "max_api_calls": 600,
              "max_reported_tokens": max_reported_tokens, "max_iterations": 2, "minibatch_size": 8,
              "solver_max_tokens": 65536, "reflection_max_tokens": 4096}
    value = manifest(panel, version="continual-learning-v2", method="skillopt", seed=20260928,
                     train_families=[str(i) for i in range(64)], selection_families=[str(i) for i in range(65, 129)],
                     model=model, budget=budget)
    parent = tmp_path / "parent"
    api = API(malformed=(2, 7))
    result = skillopt.run_stage(value, panel, parent, fixture_api=api, fixture_evaluate=fixture_score)
    assert result["status"] == "pending" and result["reason"] == "native_reflection_parse_incomplete"
    assert len(api.calls) == 9
    return parent, Path(__file__).resolve().parents[1], result


def test_two_new_proposals_reuse_seven_and_frozen_solver_evidence(tmp_path):
    parent, source, old = parent_run(tmp_path)
    before = {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    root = tmp_path / "branch"
    prepared = reproposal.prepare(parent, source, root)
    assert prepared["model_calls"] == 0 and prepared["new_analyst_call_limit"] == 2
    protocol = read_json(root / "protocol.json", sealed=True)
    assert protocol["manifest"]["budget"]["max_metric_calls"] == 512 - 129
    assert protocol["manifest"]["budget"]["max_reflection_calls"] == 32 - 9
    assert protocol["manifest"]["budget"]["max_api_calls"] == 600 - old["costs"]["logical_calls"]
    assert protocol["manifest"]["budget"]["max_reported_tokens"] == 2000000 - old["costs"]["reported_tokens_known_subtotal"]
    api = API()
    result = reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score)
    assert result["status"] == "completed", result
    assert result["selection_completed"] == result["selection_planned"] == 64
    assert result["parent_score"] == 33 / 64 and result["candidate_score"] == 1
    assert result["gate_action"] == "accept_new_best" and result["paired_to_parent"] == {"wins": 31, "losses": 0, "ties": 33}
    assert result["evidence_kind"] == "engineering_fixture" and not result["deployment_authorized"]
    assert not result["optimizer_resumed"] and not result["semantics_preserving_repair"]
    calls = [read_json(p, sealed=True) for p in (root / "call_intents").glob("*.json")]
    replays = [r for r in calls if r["logical_id"].startswith("new-proposal:")]
    assert len(replays) == 2
    assert {r["logical_id"].removeprefix("new-proposal:") for r in replays} == set(protocol["malformed"])
    _, inherited = reproposal._load(root)
    for row in replays:
        prior = inherited["reflection"][row["logical_id"].removeprefix("new-proposal:")]["intent"]
        assert all(row[k] == prior[k] for k in ("system", "user", "max_tokens"))
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    count = len(api.calls)
    assert reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score) == result and len(api.calls) == count
    assert result["inherited_costs"] == old["costs"]


def test_bad_new_proposal_remains_pending_without_resampling(tmp_path):
    parent, source, _ = parent_run(tmp_path)
    root = tmp_path / "branch"
    reproposal.prepare(parent, source, root)
    api = API(malformed=(0,))
    result = reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score)
    assert result["status"] == "pending" and result["reason"] == "native_reflection_parse_incomplete"
    assert len(api.calls) == 2 and not list((root / "evaluations").glob("*.json"))
    assert reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score) == result and len(api.calls) == 2


def test_identical_skill_does_not_resample_selection_or_claim_improvement(tmp_path):
    parent, source, _ = parent_run(tmp_path)
    root = tmp_path / "branch"
    reproposal.prepare(parent, source, root)
    api = API(empty_merge=True)

    def prohibited_selection(task, skill):
        pytest.fail("An unchanged Skill must never receive a new selection sample")

    result = reproposal.run(root, fixture_api=api, fixture_evaluate=prohibited_selection)
    assert result["status"] == "completed" and result["reason"] == result["gate_action"] == "no_update"
    assert result["selected_skill"] == result["candidate_skill"] == ""
    assert result["candidate_score"] == result["parent_score"] == 33 / 64
    assert result["candidate_score_source"] == "inherited_parent_no_new_evaluation"
    assert result["paired_to_parent"] is None
    assert result["selection_planned"] == result["selection_completed"] == result["selection_closed"] == 0
    assert not list((root / "evaluation_intents").glob("*.json"))
    count = len(api.calls)
    assert reproposal.run(root, fixture_api=api, fixture_evaluate=prohibited_selection) == result
    assert len(api.calls) == count


def test_selection_unknown_stays_pending_and_keeps_partial_evidence(tmp_path):
    parent, source, _ = parent_run(tmp_path)
    root = tmp_path / "branch"
    reproposal.prepare(parent, source, root)
    api = API()
    attempts = []

    def unknown_selection(task, skill):
        attempts.append(task["task_id"])
        if len(attempts) == 3:
            return ({"status": "unknown", "output": None, "reason": "fixture_delivery_unknown"},
                    {"status": "unknown", "score": None, "metrics": {}, "reason": "fixture_delivery_unknown"})
        return fixture_score(task, skill)

    result = reproposal.run(root, fixture_api=api, fixture_evaluate=unknown_selection)
    assert result["status"] == "pending" and result["reason"] == "evaluation_unknown"
    assert result["selected_skill"] == "" and "gate_action" not in result
    assert result["selection_closed"] == 3 and result["selection_unknown"] == 1
    assert result["selection_not_closed"] == 61 and len(attempts) == 3
    count = len(api.calls)
    assert reproposal.run(root, fixture_api=api, fixture_evaluate=unknown_selection) == result
    assert len(api.calls) == count and len(attempts) == 3


def test_inherited_cost_deduction_exhausts_new_budget_without_extra_retry(tmp_path):
    parent, source, old = parent_run(tmp_path, max_reported_tokens=300)
    root = tmp_path / "branch"
    reproposal.prepare(parent, source, root)
    api = API()
    result = reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score)
    assert old["costs"]["reported_tokens_known_subtotal"] == 270
    assert result["status"] == "pending" and result["reason"] == "native_reflection_incomplete"
    assert len(api.calls) == 1 and result["new_costs"]["reported_tokens_known_subtotal"] == 30
    assert result["reported_tokens_known_subtotal"] == 300
    assert result["selection_closed"] == 0 and result["selection_not_closed"] == 64
    assert reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score) == result and len(api.calls) == 1


@pytest.mark.parametrize("corruption", ["budget", "analyst_count", "old_evidence", "panel"])
def test_mutation_cannot_spend_or_relabel_evidence(tmp_path, corruption):
    parent, source, _ = parent_run(tmp_path)
    root = tmp_path / "branch"
    reproposal.prepare(parent, source, root)
    if corruption == "old_evidence":
        next((parent / "evaluations").glob("*.json")).write_text("{}")
    elif corruption == "panel":
        value = read_json(root / "panel.json")
        value["tasks"][0]["partition"] = "final"
        (root / "panel.json").write_text(json.dumps(value))
    else:
        path = root / "protocol.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        if corruption == "budget":
            value["manifest"].pop("record_hash")
            value["manifest"]["budget"]["max_api_calls"] += 100
            value["manifest"] = seal(value["manifest"])
        else:
            value["max_new_analyst_calls"] = 3
        path.write_text(json.dumps(seal(value)))
    api = API()
    with pytest.raises(ValueError):
        reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score)
    assert not api.calls


def test_parent_lock_and_prompt_identity(tmp_path):
    parent, source, _ = parent_run(tmp_path)
    root = tmp_path / "branch"
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        reproposal.prepare(parent, source, root)
    reproposal.prepare(parent, source, root)
    value, inherited = reproposal._load(root)
    api = API()
    view = reproposal._EvidenceView(parent, inherited, Ledger(root, value["manifest"], api))
    logical = inherited["malformed"][0]
    intent = inherited["reflection"][logical]["intent"]
    with pytest.raises(ValueError, match="prompt/budget differs"):
        view.call("reflection", logical, intent["system"], "changed prompt", intent["max_tokens"])
    assert not api.calls
    view.call("reflection", logical, intent["system"], intent["user"], intent["max_tokens"])
    with pytest.raises(ValueError, match="sampled twice"):
        view.call("reflection", logical, intent["system"], intent["user"], intent["max_tokens"])
    assert len(api.calls) == 1


def test_interruption_cannot_resume_branch(tmp_path):
    from skillopt.continual_eval.core import write_json

    parent, source, _ = parent_run(tmp_path)
    root = tmp_path / "branch"
    reproposal.prepare(parent, source, root)
    write_json(root / "started.json", seal({"authored_interruption": True}))
    api = API()
    result = reproposal.run(root, fixture_api=api, fixture_evaluate=fixture_score)
    assert result["status"] == "pending" and result["model_calls_submitted"] == 0 and not api.calls
