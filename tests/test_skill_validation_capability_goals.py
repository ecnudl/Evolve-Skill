"""Public-history goal planning fixtures; no paid API or executable generation."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import capability_goals as goals
from skillopt.skill_validation.checks import ExecutionCache, pipeline_hash, validate_callable
from skillopt.skill_validation.development_feedback import build_development_feedback
from skillopt.skill_validation.models import SourceFile
from skillopt.skill_validation.rule_learning import EXECUTION_PROTOCOL, _public_feedback
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.single_round_feedback import skill_hash
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import ScriptedExecutor, artifact, rubric, task
from tests.test_skill_validation_development_feedback import _inputs
from tests.test_skill_validation_public_revision import FixtureCalls
from tests.test_skill_validation_rule_learning import inputs


def reseal(value, **updates):
    return seal({**{k: v for k, v in value.items() if k != "record_hash"}, **updates})


def history(*, preserve=True, fail=False, unknown=False, repeats=2, wrapper=False):
    parent, t, r = "opaque historical advice", task(inplace=not preserve), rubric()
    extras = (SourceFile("public_runner.py", "# HOST_PUBLIC_WRAPPER_SENTINEL"),
              SourceFile("helper.py", "# VISIBLE_HELPER_SENTINEL")) if wrapper else ()
    if wrapper:
        t = replace(t, contract=replace(t.contract, public_files=t.contract.public_files + extras))
    responses = []
    for _ in range(repeats):
        responses.extend([{}, {"status": "unsupported"} if unknown else
                          {"actual": 99, "after_args": [[2, 1]]} if fail else {}])
    cache, entries = ExecutionCache(ScriptedExecutor(responses)), []
    for repeat in range(repeats):
        artifacts = tuple(replace(artifact(t, condition=c, repeat=repeat),
            skill_hash=skill_hash("" if c == "no_skill" else parent),
            files=(SourceFile("solution.py", "# SUBMITTED_CODE_SENTINEL"),) + extras) for c in ("no_skill", "current"))
        reports = tuple(validate_callable(t, a, r, cache) for a in artifacts)
        entries.append({"task": t, "artifacts": artifacts, "reports": reports})
    bundle = build_development_feedback(entries, parent_skill=parent, rubric=r, pipeline_hash=pipeline_hash(r, cache),
                execution_identity=cache.identity, execution_records=tuple(cache.records.values()))
    return goals.history_view(parent, bundle)


def response(view, *, mechanism="input_state_preservation", mode="history"):
    evidence = view["model_views"][mode]["evidence_catalog"][0]["id"]
    return {"status": "goals", "reason": "A bounded prospective learning goal deserves testing.", "goals": [{
        "goal_id": "preserve-constraints", "mechanism": mechanism,
        "suspected_rule": "Unknown: the historical rule is only a candidate explanation.",
        "failure": "Could input/state preservation be an uncovered capability?",
        "competing_hypotheses": ["A rule may be inappropriate.", "Ordinary reasoning variation may explain the outcome."],
        "required_task_roles": list(goals.TASK_ROLES), "evidence_ids": [evidence],
        "desired_observations": ["Inspect public before/after state on new applicable tasks and condition reversals."]}]}


def test_opaque_and_structured_parent_both_replay():
    view = history()
    assert view["source_partition"] == "development" and view["fixture_only"]
    parent, bundle = inputs(parent=RuleSkill("cold-history", ()))
    structured = goals.history_view(parent, bundle)
    opaque = goals.history_view("", bundle)
    assert structured == opaque
    assert structured["model_views"]["history"]["parent_skill"] == ""


def test_full_coverage_and_repeats_not_inflated_to_independent_tasks():
    entries, options = _inputs(count=4, repeats=2)
    bundle = build_development_feedback(entries, **options, detail_limit=3)
    view = goals.history_view(options["parent_skill"], bundle)
    public = view["model_views"]["history"]
    assert public["sample_structure"]["task_count"] == 4
    assert public["sample_structure"]["paired_repeat_count"] == 8
    # All four fixture tasks deliberately have the same family annotation.
    assert public["sample_structure"]["declared_family_count"] == 1
    assert public["sample_structure"]["family_independence_certified"] is False
    assert len(public["public_history"]["coverage"]["pair_summaries"]) == 8
    assert len(public["public_history"]["paired_development"]) == 3


def test_same_contracts_outcome_blind_removes_outputs_submitted_source_and_public_files():
    view = history(fail=True)
    hs, hu, _ = goals.goal_messages(view, mode="history")
    bs, bu, _ = goals.goal_messages(view, mode="outcome_blind")
    historical, blind = json.loads(hu), json.loads(bu)
    assert hs == bs
    assert historical["parent_skill"] == blind["parent_skill"]
    assert historical["evidence_catalog"] == blind["evidence_catalog"]
    for pair, contract in zip(historical["public_history"]["paired_development"], blind["public_contracts"]):
        assert pair["task"]["prompt"] == contract["task"]["prompt"]
        assert pair["task"]["obligations"] == contract["task"]["obligations"]
        assert pair["public_cases"] == contract["public_cases"]
    assert "SUBMITTED_CODE_SENTINEL" in hu and "SUBMITTED_CODE_SENTINEL" not in bu
    for forbidden in ('"roles"', '"checks"', '"coverage"', '"statuses"', '"public_files"', '"artifact"'):
        assert forbidden not in bu
    assert "case selection" in blind["selection_caveat"]


def test_hidden_host_fields_never_projected():
    entries, options = _inputs(count=2, repeats=1, hidden=True)
    bundle = build_development_feedback(entries, **options)
    view = goals.history_view(options["parent_skill"], bundle)
    assert "PRIVATE_AUDIT_SENTINEL" in json.dumps(view["host_only"])
    for mode in goals.MODES:
        _, user, _ = goals.goal_messages(view, mode=mode)
        for forbidden in ("PRIVATE_AUDIT_SENTINEL", "fixture-family", "fixture-project", "execution_records",
                          "source_bundle_hash", "pipeline_hash", "record_hash", "host_only"):
            assert forbidden not in user


def test_wrapper_boilerplate_only_omitted_after_replay_original_bundle_retained():
    view = history(fail=True, repeats=2, wrapper=True)
    host = view["host_only"]
    raw = _public_feedback(host["parent_text"], host["bundle"], "evidence")
    system, user, _ = goals.goal_messages(view)
    projected = json.loads(user)["public_history"]
    assert "HOST_PUBLIC_WRAPPER_SENTINEL" not in user
    assert "HOST_PUBLIC_WRAPPER_SENTINEL" in json.dumps(host["bundle"])
    assert "SUBMITTED_CODE_SENTINEL" in user and "VISIBLE_HELPER_SENTINEL" in user
    assert raw["coverage"] == projected["coverage"]
    assert len(projected["coverage"]["pair_summaries"]) == 2
    expected = deepcopy(raw)
    for pair in expected["paired_development"]:
        pair["task"]["public_files"] = [f for f in pair["task"]["public_files"] if f["path"] != "public_runner.py"]
        for role in pair["roles"].values():
            role["artifact"]["files"] = [f for f in role["artifact"]["files"] if f["path"] != "public_runner.py"]
    assert projected == expected  # All statuses, checks, cases and obligations unchanged.
    for mode in goals.MODES:
        _, payload, _ = goals.goal_messages(view, mode=mode)
        value = json.loads(payload)
        assert value["fixed_execution_protocol"] == EXECUTION_PROTOCOL
        assert "omits only host public-wrapper boilerplate" in value["projection_policy"]
    assert "NOT new learnable capabilities" in system and "Prefer ONE strong" in system
    assert "reason appears ONLY at the ROOT" in system


def test_goal_reason_is_root_only_not_silently_moved_or_repaired():
    view = history()
    payload = response(view)
    payload["goals"][0]["reason"] = payload.pop("reason")
    parsed = goals.plan_goals(view, response=json.dumps(payload))
    assert parsed["status"] == "invalid" and parsed["goals"] == [] and not parsed["retry_authorized"]


def test_goals_return_references_and_uncertified_observation_basis():
    view = history(fail=True)
    result = goals.plan_goals(view, response=json.dumps(response(view)))
    assert result["status"] == "goals"
    assert result["goals"][0]["observation_basis"] == "public_check_failure_observed_not_causal_or_semantically_certified"
    assert result["source"] == "historical_development_hypothesis_not_new_parent_evidence"
    assert not result["semantic_claims_verified"] and not result["method_effect_evaluated"]
    assert not result["deployment_authorized"] and not result["task_generation_performed"]
    assert result["proposal_origin"] == "caller_supplied_not_a_model_run"


def test_uncovered_preservation_not_falsely_reported_as_observed_failure():
    view = history(preserve=False, fail=True)
    result = goals.plan_goals(view, response=json.dumps(response(view)))
    assert result["status"] == "goals"
    assert result["goals"][0]["observation_basis"] == "uncovered_capability_not_observed_in_cited_history"
    boundary = goals.plan_goals(view, response=json.dumps(response(view, mechanism="behavior_boundary")))
    assert boundary["goals"][0]["observation_basis"].startswith("public_check_failure_observed")


def test_blind_does_not_gain_failure_labels_and_unknown_is_not_failure():
    view = history(fail=True)
    result = goals.plan_goals(view, response=json.dumps(response(view)), mode="outcome_blind")
    assert result["goals"][0]["observation_basis"] == "prospective_contract_gap_no_outcome_access"
    uncertain = history(unknown=True)
    result = goals.plan_goals(uncertain, response=json.dumps(response(uncertain)))
    assert result["goals"][0]["observation_basis"] == "public_obligation_seen_no_confirmed_failure_in_cited_checks"


def test_no_update_and_invalid_responses_are_normal_paths():
    view = history()
    value = {"status": "no_update", "goals": [], "reason": "Insufficient relevant evidence."}
    assert goals.plan_goals(view, response=json.dumps(value))["status"] == "no_update"
    for raw in ("NO_UPDATE", "{}", "[]", "not JSON", '{"status":"goals","status":"no_update","goals":[],"reason":"x"}'):
        result = goals.plan_goals(view, response=raw)
        assert result["status"] == "invalid" and result["goals"] == [] and result["retry_authorized"] is False


@pytest.mark.parametrize("status", ["goals", "no_update"])
def test_complete_json_fence_is_transport_equivalent_to_bare_goals(status):
    view = history()
    payload = response(view) if status == "goals" else {"status": "no_update", "goals": [], "reason": "No useful new goal."}
    raw = json.dumps(payload)
    bare = goals.plan_goals(view, response=raw)
    wrapped = goals.plan_goals(view, response=" \n```json\n" + raw + "\n```\n ")
    assert wrapped == bare and wrapped["version"] == "historical-public-capability-goals-v3"


@pytest.mark.parametrize("envelope", ["Explanation.\n```json\n%s\n```", "```json\n%s\n```\nExplanation.",
    "```json\n%s\n```\n```json\n{}\n```", "```json\n```json\n%s\n```\n```"])
def test_goal_parser_never_extracts_json_from_prose_or_double_fences(envelope):
    view = history()
    result = goals.plan_goals(view, response=envelope % json.dumps(response(view)))
    assert result["status"] == "invalid" and not result["retry_authorized"]


@pytest.mark.parametrize("raw", [
    '{"status":"no_update","status":"no_update","goals":[],"reason":"x"}',
    '{"status":"no_update","goals":[],"reason":NaN}',
    '{"status":"no_update","goals":[],"reason":Infinity}',
    '{"status":"no_update","goals":[],"reason":-Infinity}',
])
def test_fenced_goals_still_reject_duplicate_keys_and_nonfinite_numbers(raw):
    result = goals.plan_goals(history(), response="```json\n" + raw + "\n```")
    assert result["status"] == "invalid" and result["goals"] == []


def test_goal_fence_does_not_bypass_original_full_response_byte_budget():
    view = history()
    raw = json.dumps(response(view))
    padded = raw + " " * (16000 - len(raw.encode()))
    catalog = view["model_views"]["history"]["evidence_catalog"]
    assert goals._parse(padded, catalog) == json.loads(raw)
    with pytest.raises(ValueError, match="bounded UTF-8"):
        goals._parse("```json\n" + padded + "\n```", catalog)


@pytest.mark.parametrize("field,value", [
    ("evidence_ids", ["hidden-audit-reference"]), ("evidence_ids", []),
    ("mechanism", "coding_sota"), ("required_task_roles", ["same_mechanism"]),
    ("competing_hypotheses", ["It must be the Skill."]), ("desired_observations", []),
    ("failure", ""), ("goal_id", "bad id"), ("deployment_authorized", True),
    ("observation_basis", "definitely_overfitted"),
])
def test_strict_fields_and_current_catalog(field, value):
    view = history()
    payload = response(view)
    payload["goals"][0][field] = value
    assert goals.plan_goals(view, response=json.dumps(payload))["status"] == "invalid"


def test_no_more_than_three_unique_goals():
    view = history()
    payload = response(view)
    payload["goals"] *= 2
    assert goals.plan_goals(view, response=json.dumps(payload))["status"] == "invalid"
    payload["goals"] = [{**payload["goals"][0], "goal_id": "g" + str(i)} for i in range(4)]
    assert goals.plan_goals(view, response=json.dumps(payload))["status"] == "invalid"
    payload["goals"] = payload["goals"][:3]
    assert goals.plan_goals(view, response=json.dumps(payload))["status"] == "goals"


def test_final_history_parent_mismatch_and_thin_summaries_rejected():
    view = history()
    bundle = deepcopy(view["host_only"]["bundle"])
    bundle["entries"][0]["task"]["contract"]["partition"] = "final"
    with pytest.raises(ValueError):
        goals.history_view(view["host_only"]["parent_text"], reseal(bundle))
    with pytest.raises(ValueError):
        goals.history_view("different parent", view["host_only"]["bundle"])
    _, thin = inputs(legacy=True)
    with pytest.raises(ValueError, match="replayable"):
        goals.history_view("", thin)


def test_tampered_public_projection_is_replayed_before_model_call():
    view = deepcopy(history())
    view["model_views"]["history"]["public_history"]["coverage"]["role_counts"]["current"]["pass"] += 1
    calls = FixtureCalls("{}")
    with pytest.raises(ValueError, match="changed after source replay"):
        goals.plan_goals(reseal(view), calls=calls)
    assert calls.calls == []


def test_single_bounded_call_and_failed_api_not_retried():
    view = history()
    calls = FixtureCalls(json.dumps(response(view)))
    result = goals.plan_goals(view, calls=calls, repeat=3)
    assert result["status"] == "goals" and result["proposal_origin"] == "model_call"
    assert len(calls.calls) == 1 and calls.calls[0]["kind"] == "capability-goal-plan"
    assert calls.calls[0]["repeat"] == 3 and calls.calls[0]["max_tokens"] == 2048
    assert result["api_request_hash"] == digest(calls.calls[0])
    failed = FixtureCalls("unused", ok=False)
    assert goals.plan_goals(view, calls=failed)["status"] == "api_failure" and len(failed.calls) == 1


def test_integrity_exception_not_hidden_as_invalid_proposal():
    view = history()
    with pytest.raises(RuntimeError, match="lost connection"):
        goals.plan_goals(view, calls=FixtureCalls(error=RuntimeError("lost connection")))
    class WrongRequest(FixtureCalls):
        def call(self, *args, **kwargs):
            value = super().call(*args, **kwargs)
            value["request"]["repeat"] += 1
            value["request_hash"] = digest(value["request"])
            return value
    with pytest.raises(ValueError, match="another request"):
        goals.plan_goals(view, calls=WrongRequest("{}"))


def test_prompt_budget_and_exclusive_response_paths(monkeypatch):
    view = history()
    calls = FixtureCalls("{}")
    with pytest.raises(ValueError):
        goals.plan_goals(view)
    with pytest.raises(ValueError):
        goals.plan_goals(view, calls=calls, response="{}")
    with pytest.raises(ValueError):
        goals.plan_goals(view, response="{}", mode="final")
    monkeypatch.setattr(goals, "MAX_PROMPT_BYTES", 10)
    with pytest.raises(ValueError, match="budget"):
        goals.plan_goals(view, calls=calls)
    assert calls.calls == []
