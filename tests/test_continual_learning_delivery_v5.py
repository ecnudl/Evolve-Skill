"""Learning v5 closed-delivery fixes: engineering controls, never method-effect evidence."""
import json
from copy import deepcopy

import httpx
import pytest

from skillopt.continual_learning.contracts import DELIVERY_VERSION, RECOVERY_VERSION, manifest, validate_manifest
from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY, POLICY_V5, client_options
from skillopt.continual_learning.skillopt import run_stage
from skillopt.validator_pilot import api as provider
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import API as DomainAPI
from tests.test_continual_learning_domains import evaluate, setup


def auth(version=DELIVERY_VERSION, policy=POLICY_V5, *, iterations=1):
    _, panel, args = setup()
    args.update(version=version, recovery_policy=deepcopy(policy))
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"]["max_iterations"] = iterations
    return manifest(panel, **args), panel


class API:
    model = "fixture"

    def __init__(self, failed_attempt_usages=(), *, final_usage=True, policy="closed_delivery_error_v2"):
        self.failed, self.final_usage, self.calls = list(failed_attempt_usages), final_usage, []
        self.service = {"delivery_retry_policy": policy}

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        request = dict(model=self.model, system=system, user=user, kind=kind, key=key,
                       max_tokens=max_tokens, repeat=repeat, service=self.service)
        self.calls.append(request)
        usage = {"prompt_tokens": 20, "completion_tokens": 30} if self.final_usage else {}
        attempts = [{"usage": dict(u)} for u in self.failed] + [{"usage": dict(usage)}]
        return dict(request=request, request_hash=digest(request), ok=True, response="<answer>Paris</answer>",
                    finish_reason="stop", stream_complete=True, status=200, returned_model="glm-5.3",
                    http_attempt_count=len(attempts), attempts=attempts, usage=usage)


def test_v5_manifest_policy_and_client_option_are_exact():
    value, panel = auth()
    assert validate_manifest(value, panel) == value
    assert value["recovery_policy"] == POLICY_V5
    assert client_options(value) == {"delivery_retry_policy": "closed_delivery_error_v2"}
    with pytest.raises(ValueError, match="recovery policy"):
        auth(DELIVERY_VERSION, POLICY)
    with pytest.raises(ValueError, match="recovery policy"):
        auth(RECOVERY_VERSION, POLICY_V5)
    v4, _ = auth(RECOVERY_VERSION, POLICY)
    assert client_options(v4) == {"delivery_retry_policy": "closed_network_error_v1"}


def test_v5_failed_attempt_unknown_usage_is_reported_but_not_blocking(tmp_path):
    value, _ = auth()
    api = API([{}])
    ledger = Ledger(tmp_path, value, api)
    ledger.call("solver", "one", "system", "user", 100)
    costs = ledger.snapshot()
    assert costs["unknown_cost_attempts"] == costs["missing_attempt_usage"] == 1
    assert costs["usage_complete"] is False and costs["blocking_usage_gap"] is False
    assert costs["reported_tokens_known_subtotal"] == 50
    assert not ledger.usage_blocks_completion(costs)
    ledger.call("solver", "two", "system", "user", 100)
    assert len(api.calls) == 2


def test_v4_failed_attempt_unknown_usage_still_blocks(tmp_path):
    value, _ = auth(RECOVERY_VERSION, POLICY)
    api = API([{}], policy="closed_network_error_v1")
    ledger = Ledger(tmp_path, value, api)
    ledger.call("solver", "one", "system", "user", 100)
    assert ledger.usage_blocks_completion(ledger.snapshot())
    with pytest.raises(LearningPending, match="usage"):
        ledger.call("solver", "two", "system", "user", 100)
    assert len(api.calls) == 1


def test_v5_delivered_response_without_usage_blocks(tmp_path):
    value, _ = auth()
    api = API(final_usage=False)
    ledger = Ledger(tmp_path, value, api)
    ledger.call("solver", "one", "system", "user", 100)
    costs = ledger.snapshot()
    assert costs["delivered_without_usage"] == 1 and costs["blocking_usage_gap"] is True
    with pytest.raises(LearningPending, match="usage"):
        ledger.call("solver", "two", "system", "user", 100)


def test_v5_unknown_cost_attempts_are_capped(tmp_path):
    value, _ = auth()
    cap = POLICY_V5["max_unknown_cost_attempts"]
    api = API([{}] * cap)
    ledger = Ledger(tmp_path, value, api)
    ledger.call("solver", "one", "system", "user", 100)
    assert ledger.snapshot()["unknown_cost_attempts"] == cap
    with pytest.raises(BudgetExhausted, match="unknown_cost_attempt_cap"):
        ledger.call("solver", "two", "system", "user", 100)
    assert len(api.calls) == 1


@pytest.mark.parametrize("policy,expected_attempts,ok", [
    ("closed_delivery_error_v2", 2, True),
    ("closed_network_error_v1", 1, False),
])
def test_incomplete_http200_stream_is_retried_only_by_v2(tmp_path, monkeypatch, policy, expected_attempts, ok):
    monkeypatch.setattr(provider, "_configuration", lambda *a, **k: (
        "https://open.bigmodel.cn/api/paas/v4/chat/completions", "FIXTURE_NOT_A_KEY"))
    monkeypatch.setattr(provider.time, "sleep", lambda _: None)
    requests = []
    sync_client, async_client = httpx.Client, httpx.AsyncClient

    def handle(request):
        complete = len(requests) > 0
        requests.append(json.loads(request.content))
        event = {"model": "glm-5.3", "choices": [{"index": 0, "delta": {"content": "ok" if complete else "part"},
                                                  "finish_reason": "stop" if complete else None}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
        body = "data: " + json.dumps(event) + "\n\n" + ("data: [DONE]\n\n" if complete else "")
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())

    monkeypatch.setattr(provider.httpx, "Client", lambda **k: sync_client(transport=httpx.MockTransport(handle), **k))
    monkeypatch.setattr(provider.httpx, "AsyncClient",
                        lambda **k: async_client(transport=httpx.MockTransport(handle), **k))
    with provider.CachedAPI(tmp_path, tmp_path / "api", provider="bigmodel", stream=True,
                            read_timeout_seconds=300, stream_wall_seconds=3600,
                            initial_health_policy="completed_response_v1", delivery_retry_policy=policy) as api:
        receipt = api.call("system", "user", "smoke", "0", max_tokens=100)
    assert len(requests) == expected_attempts == receipt["http_attempt_count"]
    assert receipt["ok"] is ok
    assert receipt["attempts"][0]["error_type"] == "incomplete_stream"
    assert receipt["request"]["service"]["delivery_retry_policy"] == policy


class OversizeAPI(DomainAPI):
    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if not kind.endswith("solver"):
            row["response"] = json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": [
                {"op": "append", "content": "x" * 6001}]}})
        return row


def test_v5_over_budget_native_candidate_is_rejected_and_replays(tmp_path):
    value, panel = auth()
    api = OversizeAPI()
    result = run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "completed", result
    assert result["candidate_skill"] == "" and result["selected_score"] == result["initial_selection_score"]
    step = result["steps"][0]
    assert step["gate_action"] == "reject_inadmissible_over_budget"
    assert step["rejected_candidate_bytes"] > 6000 and step["candidate_score"] is None
    assert not result["deployment_authorized"]
    calls = len(api.calls)
    assert run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa")) == result
    assert len(api.calls) == calls


def test_v5_over_budget_rejection_continues_to_next_native_iteration(tmp_path):
    value, panel = auth(iterations=2)
    api = OversizeAPI()
    result = run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "completed", result
    assert [s["gate_action"] for s in result["steps"]] == ["reject_inadmissible_over_budget"] * 2
    reflections = [c for c in api.calls if not c["kind"].endswith("solver")]
    assert len({c["key"] for c in reflections}) == len(reflections) >= 2


def test_v4_over_budget_native_candidate_stays_pending(tmp_path):
    value, panel = auth(RECOVERY_VERSION, POLICY)
    result = run_stage(value, panel, tmp_path, fixture_api=OversizeAPI(), fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "pending" and result["reason"] == "native_candidate_exceeds_skill_budget"


def test_v5_is_skillopt_only():
    _, panel, args = setup(method="gepa")
    args.update(version=DELIVERY_VERSION, recovery_policy=deepcopy(POLICY_V5))
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    with pytest.raises(ValueError, match="SkillOpt-only"):
        manifest(panel, **args)


@pytest.mark.parametrize("version,policy", [(DELIVERY_VERSION, POLICY_V5), (RECOVERY_VERSION, POLICY)])
def test_native_merge_fallback_is_recorded_only_in_v5(tmp_path, version, policy):
    _, panel, args = setup()
    args.update(version=version, recovery_policy=deepcopy(policy))
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"]["minibatch_size"] = 1  # two analyst patches force a native merge call
    value = manifest(panel, **args)
    result = run_stage(value, panel, tmp_path, fixture_api=DomainAPI(), fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "completed", result
    step = result["steps"][0]
    if version == DELIVERY_VERSION:
        # The fixture answers the merge in analyst format, which upstream silently replaces.
        assert any("using fallback" in item for item in step["native_fallbacks"])
    else:
        assert "native_fallbacks" not in step


def _natural_stage(tmp_path, monkeypatch, version, policy, max_api_calls):
    import skillopt.continual_learning.skillopt as learner

    _, panel, args = setup("searchqa", natural=True)
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"]["max_api_calls"] = max_api_calls
    value = manifest(panel, **{**args, "version": version, "recovery_policy": deepcopy(policy)})

    class Fake(DomainAPI):
        def __init__(self):
            super().__init__(model="glm-5.3")
            self.service = {"fixture": "offline", "delivery_retry_policy": client_options(value)["delivery_retry_policy"]}

        def call(self, *a, **k):
            row = super().call(*a, **k)
            row.update(returned_model="glm-5.3", status=200, stream_complete=True,
                       attempts=[{"usage": dict(row["usage"])}])
            return row

    api = Fake()
    monkeypatch.setattr(learner, "CachedAPI", lambda *a, **k: api)
    return learner.run_stage(value, panel, tmp_path, repo=tmp_path), api


@pytest.mark.parametrize("version,policy,reason", [
    (DELIVERY_VERSION, POLICY_V5, "max_api_calls"),
    (RECOVERY_VERSION, POLICY, "evaluation_unknown"),
])
def test_ledger_budget_stop_reason_survives_solver_adapter_only_in_v5(tmp_path, monkeypatch, version, policy, reason):
    result, api = _natural_stage(tmp_path, monkeypatch, version, policy, max_api_calls=2)
    assert result["status"] == "pending" and result["reason"] == reason
    assert len(api.calls) == 2


def _wide(version=DELIVERY_VERSION, policy=POLICY_V5, *, selection=2, iterations=1):
    """SearchQA fixture with two train families and a configurable selection set."""
    _, base, args = setup()
    task = base["tasks"][0]
    panel = {**base, "tasks": [{**deepcopy(task), "task_id": str(i), "family_id": str(i)}
                               for i in range(2 + selection)]}
    args.update(version=version, recovery_policy=deepcopy(policy), train_families=["0", "1"],
                selection_families=[str(i) for i in range(2, 2 + selection)])
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"].update(max_iterations=iterations, max_metric_calls=64)
    return manifest(panel, **args), panel


def _scorer(unknown):
    """Fixture outcomes; ``unknown(task_id, skill)`` marks a position unknown."""
    def execute(task, skill):
        prediction, score = evaluate("searchqa")(task, skill)
        if unknown(task["task_id"], skill):
            return prediction, {**score, "status": "unknown", "score": None}
        return prediction, score
    return execute


def test_v5_excludes_unknown_and_gates_on_jointly_known_selection(tmp_path):
    value, panel = _wide()
    result = run_stage(value, panel, tmp_path, fixture_api=DomainAPI(),
                       fixture_evaluate=_scorer(lambda task_id, skill: task_id == "3"))
    assert result["status"] == "completed", result
    assert "requested constant" in result["candidate_skill"]
    assert result["unknown_policy"] == "paired_known_exclusion_guarded_v1"
    step = result["steps"][0]
    assert step["gate_action"] == "accept_new_best"
    assert step["jointly_known"] == 1 and step["candidate_new_unknown"] == 0
    assert step["parent_score"] == 0 and step["candidate_score"] == 1


def test_v4_still_pends_on_the_same_unknown(tmp_path):
    value, panel = _wide(RECOVERY_VERSION, POLICY)
    result = run_stage(value, panel, tmp_path, fixture_api=DomainAPI(),
                       fixture_evaluate=_scorer(lambda task_id, skill: task_id == "3"))
    assert result["status"] == "pending" and result["reason"] == "evaluation_unknown"


@pytest.mark.parametrize("unknown_ids,reason", [({"2", "3"}, "insufficient_known_selection"),
                                                ({"0", "1"}, "insufficient_known_train")])
def test_v5_too_few_known_positions_stay_pending(tmp_path, unknown_ids, reason):
    value, panel = _wide()
    result = run_stage(value, panel, tmp_path, fixture_api=DomainAPI(),
                       fixture_evaluate=_scorer(lambda task_id, skill: task_id in unknown_ids))
    assert result["status"] == "pending" and result["reason"] == reason and result["candidate_skill"] == ""


def test_v5_candidate_cannot_hide_failures_as_unknowns(tmp_path):
    value, panel = _wide(selection=8)
    # The candidate turns three parent-known selection positions into unknowns.
    hidden = {"2", "3", "4"}
    result = run_stage(value, panel, tmp_path, fixture_api=DomainAPI(), fixture_evaluate=_scorer(
        lambda task_id, skill: task_id in hidden and "requested constant" in skill))
    assert result["status"] == "completed" and result["candidate_skill"] == ""
    step = result["steps"][0]
    assert step["gate_action"] == "reject_unknown_shift_or_coverage" and not step["paired_admissible"]
    assert step["candidate_new_unknown"] == 3 > step["unknown_shift_tolerance"] == 2


@pytest.mark.parametrize("version,policy,intents", [(DELIVERY_VERSION, POLICY_V5, 6), (RECOVERY_VERSION, POLICY, 4)])
def test_each_update_gets_a_fresh_train_rollout_only_in_v5(tmp_path, version, policy, intents):
    value, panel = _wide(version, policy, iterations=2)
    result = run_stage(value, panel, tmp_path, fixture_api=DomainAPI(no_update=True),
                       fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "completed" and len(result["steps"]) == 2
    assert len(list((tmp_path / "evaluation_intents").glob("*.json"))) == intents


def test_v2_filtered_receipt_keeps_specific_unknown_reason():
    from skillopt.continual_eval.backends import _response

    def call(system, user):
        return {"ok": False, "response": "", "finish_reason": "sensitive", "usage": {},
                "request": {"service": {"delivery_retry_policy": "closed_delivery_error_v2"}}}

    assert _response(call, "system", "user")[2] == "model_response_filtered"
