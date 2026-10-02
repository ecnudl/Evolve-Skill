"""Authored engineering fixtures only; no model calls or benchmark execution."""
import copy
import json

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, write_json
from skillopt.continual_learning import feedback_ablation as ablation
from skillopt.continual_learning.ledger import Ledger
from skillopt.validator_pilot.api import digest
from tests import test_continual_learning_reproposal as parent_fixture


class API:
    model = parent_fixture.API.model
    service = parent_fixture.API.service

    def __init__(self, response="Check boundaries.", *, finish="stop", ok=True, usage=None):
        self.calls, self.response, self.finish, self.ok = [], response, finish, ok
        self.usage = {"prompt_tokens": 10, "completion_tokens": 20} if usage is None else usage

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        assert all(x not in system + user for x in ("HIDDEN_TEST_SENTINEL", "PRIVATE_TRACEBACK", "SELECTION_ONLY"))
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        self.calls.append(request)
        return {"request": request, "request_hash": digest(request), "ok": self.ok, "finish_reason": self.finish,
                "response": self.response, "http_attempt_count": 1, "usage": self.usage}


def prepare_arm(tmp_path, *, arm="generic_summary"):
    parent, source, old = parent_fixture.parent_run(tmp_path)
    root = tmp_path / arm
    ablation.prepare(parent, source, root, arm=arm)
    return root, parent, source, old


def test_two_arms_only_differ_in_policy_and_never_expose_selection_or_private(tmp_path, monkeypatch):
    original = parent_fixture.fixture_score

    def sentinel_score(task, skill):
        prediction, score = original(task, skill)
        score["metrics"] = {"traceback": "PRIVATE_TRACEBACK"}
        score["reason"] = "PRIVATE_TRACEBACK"
        if int(task["task_id"]) >= 65:
            prediction["output"] = "SELECTION_ONLY"
        return prediction, score

    monkeypatch.setattr(parent_fixture, "fixture_score", sentinel_score)
    parent, source, old = parent_fixture.parent_run(tmp_path)
    before = {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    requests, protocols = [], []
    for arm in ablation.POLICIES:
        root = tmp_path / arm
        assert ablation.prepare(parent, source, root, arm=arm)["model_calls"] == 0
        protocol = read_json(root / "protocol.json", sealed=True)
        protocols.append(protocol)
        assert protocol["manifest"]["method"] == "shadow_" + arm
        assert protocol["manifest"]["budget"]["solver_max_tokens"] == 65536
        assert protocol["manifest"]["budget"]["reflection_max_tokens"] == 4096
        assert protocol["manifest"]["budget"]["max_api_calls"] == 65
        assert protocol["manifest"]["budget"]["max_metric_calls"] == 64
        assert protocol["manifest"]["budget"]["max_reflection_calls"] == 1
        assert protocol["manifest"]["budget"]["max_reported_tokens"] == 2000000 - old["costs"]["reported_tokens_known_subtotal"]
        api, selections = API(), []

        def evaluate(task, skill):
            selections.append(task["task_id"])
            assert 65 <= int(task["task_id"]) < 129 and skill == "Check boundaries."
            return original(task, skill)

        result = ablation.run(root, fixture_api=api, fixture_evaluate=evaluate)
        assert result["status"] == "completed", result
        assert result["gate_action"] == "accept_new_best" and result["candidate_score"] == 1
        assert result["paired_to_parent"] == {"wins": 31, "losses": 0, "ties": 33}
        assert result["selection_closed"] == 64 and len(set(selections)) == 64
        assert result["new_costs"]["reflection_calls"] == len(api.calls) == 1
        assert result["inherited_costs"] == old["costs"]
        assert result["reported_tokens_known_subtotal"] == 30 + old["costs"]["reported_tokens_known_subtotal"]
        assert result["shared_inherited_costs_count_once_across_arms"]
        assert result["inherited_reflection_responses_used"] == 0
        assert result["shadow_only"] and result["evidence_kind"] == "engineering_fixture"
        assert not any(result[k] for k in ("deployment_authorized", "scope_authorized", "research_rubric_method",
                                           "compute_matched_baseline", "resume_supported"))
        assert ablation.run(root, fixture_api=api, fixture_evaluate=evaluate) == result
        assert len(api.calls) == 1 and len(selections) == 64
        requests.append(api.calls[0])
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*") if p.is_file()}
    left, right = [json.loads(row["user"]) for row in requests]
    assert left.pop("update_policy") != right.pop("update_policy") and left == right
    assert len(left["observations"]) == 65 and left["parent_skill"] == ""
    assert all(set(row) == {"public", "model_output", "feedback"} for row in left["observations"])
    assert all(row["feedback"]["source"] == "host_development_audit" for row in left["observations"])
    assert requests[0]["system"] == requests[1]["system"] == ablation.SYSTEM
    assert requests[0]["service"] == requests[1]["service"]
    assert requests[0]["key"] != requests[1]["key"]
    assert requests[0]["max_tokens"] == requests[1]["max_tokens"] == 4096
    assert protocols[0]["training_evidence_hash"] == protocols[1]["training_evidence_hash"]
    assert protocols[0]["training_receipts_hash"] == protocols[1]["training_receipts_hash"]


def test_model_projection_is_whitelist_not_entire_inherited_dict(tmp_path):
    root, _, _, _ = prepare_arm(tmp_path)
    _, inherited = ablation._load(root)
    inherited = copy.deepcopy(inherited)
    inherited["selection_rows"] = {"SECRET_SELECTION": "SELECTION_ONLY"}
    inherited["parent_score"] = "SECRET_SCORE"
    inherited["reflection"] = {"SECRET_REFLECTION": "not model evidence"}
    for trace in inherited["traces"]:
        trace["Inputs"]["private"] = "PRIVATE_INPUT_EXTRA"
        trace["Feedback"]["traceback"] = "PRIVATE_TRACEBACK"
        trace["secret"] = "PRIVATE_TRACE_EXTRA"
    payload = json.dumps(ablation.model_evidence(inherited))
    assert not any(x in payload for x in ("PRIVATE_", "SECRET_", "SELECTION_ONLY"))


@pytest.mark.parametrize("response", ["NO_UPDATE", " \nNO_UPDATE\n"])
def test_no_update_never_resamples_empty_parent(tmp_path, response):
    root, _, _, _ = prepare_arm(tmp_path)
    api = API(response)

    def forbidden(*args):
        pytest.fail("Unchanged parent must not be reevaluated")

    result = ablation.run(root, fixture_api=api, fixture_evaluate=forbidden)
    assert result["status"] == "completed" and result["gate_action"] == "no_update"
    assert result["candidate_score"] == result["parent_score"] == 33 / 64
    assert result["candidate_score_source"] == "inherited_parent_no_new_evaluation"
    assert result["candidate_skill"] == result["selected_skill"] == ""
    assert result["selection_planned"] == result["selection_closed"] == result["selection_not_closed"] == 0
    assert not list((root / "evaluation_intents").glob("*.json"))
    assert ablation.run(root, fixture_api=api, fixture_evaluate=forbidden) == result and len(api.calls) == 1


@pytest.mark.parametrize("response", ["", "  ", "{}", "[]", "```text\nSkill\n```", "NO_UPDATE because...", "好" * 2001])
def test_invalid_proposal_is_pending_not_repaired_or_selected(tmp_path, response):
    root, _, _, _ = prepare_arm(tmp_path)
    api = API(response)
    result = ablation.run(root, fixture_api=api, fixture_evaluate=parent_fixture.fixture_score)
    assert result["status"] == "pending" and result["reason"] == "invalid_skill_proposal"
    assert result["selection_closed"] == 0 and result["selected_skill"] == ""
    assert ablation.run(root, fixture_api=api, fixture_evaluate=parent_fixture.fixture_score) == result
    assert len(api.calls) == 1


@pytest.mark.parametrize("kwargs,reason", [({"finish": "length"}, "proposal_delivery_unknown"),
                                         ({"ok": False}, "proposal_delivery_unknown"),
                                         ({"usage": {}}, "proposal_usage_unknown")])
def test_delivery_or_usage_unknown_does_not_evaluate(tmp_path, kwargs, reason):
    root, _, _, _ = prepare_arm(tmp_path)
    api = API(**kwargs)
    result = ablation.run(root, fixture_api=api, fixture_evaluate=parent_fixture.fixture_score)
    assert result["status"] == "pending" and result["reason"] == reason
    assert result["selection_closed"] == 0 and "gate_action" not in result
    assert len(api.calls) == 1


@pytest.mark.parametrize("unknown_at", [0, 3, 63])
def test_selection_unknown_keeps_evidence_and_never_retries(tmp_path, unknown_at):
    root, _, _, _ = prepare_arm(tmp_path)
    api, visited = API(), []

    def evaluate(task, skill):
        visited.append(task["task_id"])
        if len(visited) > unknown_at:
            return ({"status": "unknown", "output": None, "reason": "authored_fixture"},
                    {"status": "unknown", "score": None, "metrics": {}, "reason": "authored_fixture"})
        return parent_fixture.fixture_score(task, skill)

    result = ablation.run(root, fixture_api=api, fixture_evaluate=evaluate)
    assert result["status"] == "pending" and result["reason"] == "evaluation_unknown"
    assert result["selection_closed"] == unknown_at + 1 and result["selection_unknown"] == 1
    assert result["selection_not_closed"] == 63 - unknown_at
    assert result["selected_skill"] == "" and "gate_action" not in result and "candidate_score" not in result
    assert ablation.run(root, fixture_api=api, fixture_evaluate=evaluate) == result
    assert len(visited) == unknown_at + 1 and len(api.calls) == 1


def test_gate_cannot_accept_short_panel(tmp_path, monkeypatch):
    root, _, _, _ = prepare_arm(tmp_path)
    monkeypatch.setattr(ablation.Adapter, "evaluate_rows", lambda *args: [{"score": 1}] * 63)
    api = API()
    result = ablation.run(root, fixture_api=api, fixture_evaluate=parent_fixture.fixture_score)
    assert result["status"] == "pending" and "gate_action" not in result


@pytest.mark.parametrize("corruption", ["arm", "prompt_hash", "budget", "original_evidence", "panel"])
def test_changed_protocol_or_parent_cannot_issue_call(tmp_path, corruption):
    root, parent, _, _ = prepare_arm(tmp_path)
    if corruption == "original_evidence":
        next((parent / "evaluations").glob("*.json")).write_text("{}")
    elif corruption == "panel":
        value = read_json(root / "panel.json")
        value["tasks"][0]["partition"] = "final"
        (root / "panel.json").write_text(json.dumps(value))
    else:
        value = read_json(root / "protocol.json", sealed=True)
        value.pop("record_hash")
        if corruption == "arm":
            value["arm"] = "conditional_mechanism"
        elif corruption == "prompt_hash":
            value["prompt_hash"] = "0" * 64
        else:
            value["manifest"].pop("record_hash")
            value["manifest"]["budget"]["reflection_max_tokens"] = 8192
            value["manifest"] = seal(value["manifest"])
        (root / "protocol.json").write_text(json.dumps(seal(value)))
    api = API()
    with pytest.raises(ValueError):
        ablation.run(root, fixture_api=api, fixture_evaluate=parent_fixture.fixture_score)
    assert not api.calls


def test_parent_lock_interruption_and_cli_check(tmp_path, capsys):
    parent, source, _ = parent_fixture.parent_run(tmp_path)
    capsys.readouterr()
    root = tmp_path / "arm"
    with output_lock(parent), pytest.raises(ValueError, match="active writer"):
        ablation.prepare(parent, source, root, arm="generic_summary")
    assert ablation.main(["prepare", "--output", str(root), "--parent", str(parent), "--parent-source", str(source),
                          "--arm", "generic_summary"]) == 0
    assert json.loads(capsys.readouterr().out)["model_calls"] == 0
    assert ablation.main(["check", "--output", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["model_calls"] == 0
    write_json(root / "started.json", seal({"fixture_interruption": True}))
    api = API()
    result = ablation.run(root, fixture_api=api, fixture_evaluate=parent_fixture.fixture_score)
    assert result["status"] == "pending" and result["model_calls_submitted"] == 0 and not api.calls


def test_full_evidence_is_never_silently_truncated(tmp_path):
    root, _, _, _ = prepare_arm(tmp_path)
    _, inherited = ablation._load(root)
    inherited["traces"][0]["Inputs"]["prompt"] = "A" * 240000
    with pytest.raises(ValueError, match="Full evidence exceeds prompt limit"):
        ablation.messages(inherited, "generic_summary")


def test_exact_skill_byte_limit():
    assert ablation.parse_skill("好" * 2000) == "好" * 2000
    with pytest.raises(Exception, match="invalid_skill_proposal"):
        ablation.parse_skill("好" * 2001)


def test_selection_uses_existing_solver_exact_budget_and_runtime_without_native_execution(tmp_path, monkeypatch):
    root, _, _, _ = prepare_arm(tmp_path)
    protocol, inherited = ablation._load(root)
    new = protocol["manifest"]
    api = API("```python\ndef solve(): return 1\n```")
    ledger, scored = Ledger(root, new, api), []

    def score(benchmark, public, private, prediction, *, runtime):
        assert benchmark == "bigcodebench" and runtime == inherited["manifest"]["runtime"]
        assert prediction["status"] == "available" and prediction["output"] == "def solve(): return 1"
        scored.append(public)
        return {"status": "pass", "score": 1.0, "metrics": {}, "reason": "fixture_not_native_execution"}

    monkeypatch.setattr(ablation.backends, "score", score)
    result = ablation._select(root, new, inherited, ledger, "Check boundaries.", None)
    assert result["status"] == "completed" and result["gate_action"] == "accept_new_best"
    assert len(scored) == len(api.calls) == 64
    assert all(row["max_tokens"] == 65536 and row["repeat"] == 0 and row["service"] == api.service
               and row["kind"] == "continual-learning-solver" for row in api.calls)
    assert ledger.snapshot()["solver_calls"] == 64


@pytest.mark.parametrize("all_fail", [False, True])
def test_unhelpful_candidate_keeps_raw_score_but_is_rejected_without_retry(tmp_path, all_fail):
    root, _, _, _ = prepare_arm(tmp_path)
    api, visited = API("Preserve current behavior only when required."), []

    def evaluate(task, skill):
        visited.append(task["task_id"])
        prediction, score = parent_fixture.fixture_score(task, skill)
        if all_fail:
            score.update(status="fail", score=0.0)
        return prediction, score

    result = ablation.run(root, fixture_api=api, fixture_evaluate=evaluate)
    assert result["status"] == "completed" and result["gate_action"] == "reject"
    assert result["candidate_score"] == (0 if all_fail else 33 / 64)
    assert result["candidate_skill"] == api.response and result["selected_skill"] == ""
    assert result["selection_closed"] == 64 and result["selection_unknown"] == 0
    assert ablation.run(root, fixture_api=api, fixture_evaluate=evaluate) == result
    assert len(api.calls) == 1 and len(visited) == 64
