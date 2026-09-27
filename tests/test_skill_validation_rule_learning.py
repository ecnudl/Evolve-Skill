"""Public fixture receipts test integration, not Skill learning effectiveness."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.admission import ScopeRule
from skillopt.skill_validation.checks import ExecutionCache, pipeline_hash, validate_callable
from skillopt.skill_validation.development_feedback import build_development_feedback
from skillopt.skill_validation.rule_learning import (
    MAX_RESPONSE_BYTES, _json_response, build_update_request, candidate_from_response, propose,
)
from skillopt.skill_validation.rule_skill import Rule, RuleEdit, RuleSkill, RuleUpdate, render_skill
from skillopt.skill_validation.single_round_feedback import build_feedback_bundle, skill_hash
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import ScriptedExecutor, artifact, rubric, task
from tests.test_skill_validation_public_revision import FixtureCalls


def inputs(parent=None, *, legacy=False, unknown=False, repeats=1):
    parent = parent or RuleSkill("fixture-history", ())
    t, r = task(), rubric()
    cache = ExecutionCache(ScriptedExecutor(), read_only=unknown)
    entries = []
    for repeat in range(repeats):
        artifacts = tuple(replace(artifact(t, condition=c, repeat=repeat),
            skill_hash=skill_hash("" if c == "no_skill" else render_skill(parent)))
            for c in ("no_skill", "current"))
        reports = tuple(validate_callable(t, a, r, cache) for a in artifacts)
        entries.append({"task": t, "artifacts": artifacts, "reports": reports})
    options = {"parent_skill": render_skill(parent), "rubric": r, "pipeline_hash": pipeline_hash(r, cache),
               "execution_identity": cache.identity,
               "execution_records": tuple(cache.records.values()) + tuple(cache.missing_records.values())}
    bundle = (build_feedback_bundle if legacy else build_development_feedback)(entries, **options)
    return parent, bundle


def rule(evidence, *, id="preserve", scope=None):
    return Rule(id, "Constraint Preservation", ("Compare state before and after the operation.",),
                "Only when the task explicitly requires unchanged input.",
                ("Do not impose preservation when in-place modification is required.",),
                scope or ScopeRule(("input_preservation",)), (evidence,))


def response(parent, bundle, *, operation="add", **options):
    evidence = build_update_request(parent, bundle, **options)["evidence_catalog"][0]["id"]
    r = rule(evidence)
    edit = RuleEdit(operation, r.id, r, (evidence,), "The public obligation supports checking unchanged inputs.")
    return json.dumps(RuleUpdate(parent.content_hash, (edit,)).to_dict())


@pytest.mark.parametrize("legacy", [False, True])
def test_same_visible_evidence_for_local_patch_and_whole_text_control(legacy):
    parent, bundle = inputs(legacy=legacy, repeats=2)
    requests = [build_update_request(parent, bundle, update_mode=m) for m in ("rule_patch", "whole_text")]
    assert requests[0]["feedback_view_hash"] == requests[1]["feedback_view_hash"]
    assert requests[0]["user"] == requests[1]["user"]
    assert requests[0]["system"] != requests[1]["system"]
    for item in requests:
        assert item["feedback_use"] == "shadow_diagnostic_only"
        assert not item["deployment_authorized"]
        for hidden in ("fixture-task", "fixture-family", "fixture-project", "source_hash", "pipeline_hash"):
            assert hidden not in item["user"]
    if not legacy:
        coverage = json.loads(requests[0]["user"])["feedback"]["coverage"]
        assert coverage["independent_task_count"] == 1 and coverage["paired_repeat_count"] == 2


@pytest.mark.parametrize("legacy", [False, True])
def test_contract_only_never_receives_outcomes_or_submitted_code(legacy):
    parent, bundle = inputs(legacy=legacy)
    request = build_update_request(parent, bundle, feedback_mode="contract_only")
    feedback = json.loads(request["user"])["feedback"]
    assert feedback["development_contracts"] and "paired_development" not in feedback
    assert "Fixture candidate source" not in request["user"]
    assert all(item["kind"] == "public_contract" for item in request["evidence_catalog"])


def test_valid_rule_patch_is_only_unconfirmed_candidate():
    parent, bundle = inputs()
    result = candidate_from_response(response(parent, bundle), parent, bundle)
    candidate = RuleSkill.from_dict(result["candidate"])
    assert result["status"] == "candidate" and len(candidate.rules) == 1
    assert result["candidate_text"] == render_skill(candidate)
    assert result["confirmation_required"] and not result["semantic_support_verified"]
    assert result["scope_status"] == "unconfirmed_proposal_only"
    assert not result["deployment_authorized"] and not result["retry_authorized"]
    assert candidate.rules[0].evidence_ids[0] not in result["candidate_text"]


def test_complete_json_fence_is_transport_equivalent_to_bare_rule_patch():
    parent, bundle = inputs()
    raw = response(parent, bundle)
    bare = candidate_from_response(raw, parent, bundle)
    wrapped = candidate_from_response(" \n```json\n" + raw + "\n```\n ", parent, bundle)
    assert wrapped == bare and wrapped["version"] == "conditional-rule-learning-v2"


@pytest.mark.parametrize("envelope", ["Explanation.\n```json\n%s\n```", "```json\n%s\n```\nExplanation.",
    "```json\n%s\n```\n```json\n{}\n```", "```json\n```json\n%s\n```\n```"])
def test_rule_parser_never_extracts_json_from_prose_or_double_fences(envelope):
    parent, bundle = inputs()
    result = candidate_from_response(envelope % response(parent, bundle), parent, bundle)
    assert result["status"] == "invalid" and result["candidate"] is None and not result["retry_authorized"]


@pytest.mark.parametrize("raw", ['{"parent_hash":0,"parent_hash":1,"edits":[]}',
    '{"parent_hash":NaN,"edits":[]}', '{"parent_hash":Infinity,"edits":[]}', '{"parent_hash":-Infinity,"edits":[]}'])
def test_fenced_rules_still_reject_duplicate_keys_and_nonfinite_numbers(raw):
    parent, bundle = inputs()
    result = candidate_from_response("```json\n" + raw + "\n```", parent, bundle)
    assert result["status"] == "invalid" and result["candidate"] is None


def test_rule_fence_does_not_bypass_original_full_response_byte_budget():
    parent, bundle = inputs()
    raw = response(parent, bundle)
    padded = raw + " " * (MAX_RESPONSE_BYTES - len(raw.encode()))
    assert _json_response(padded) == json.loads(raw)
    with pytest.raises(ValueError, match="bounded UTF-8"):
        _json_response("```json\n" + padded + "\n```")


@pytest.mark.parametrize("response_value", [None, "", "{}", "not json", "```json\n{}\n```", "x" * 20001,
    '{"parent_hash":0,"parent_hash":1,"edits":[]}', '{"parent_hash":NaN,"edits":[]}'])
def test_malformed_response_is_invalid_not_repaired(response_value):
    parent, bundle = inputs()
    result = candidate_from_response(response_value, parent, bundle)
    assert result["status"] == "invalid" and result["candidate"] is None
    assert not result["retry_authorized"]


@pytest.mark.parametrize("part", ["parent", "edit_evidence", "rule_evidence", "reason", "extra_field"])
def test_wrong_identity_or_unsupported_citation_is_rejected(part):
    parent, bundle = inputs()
    value = json.loads(response(parent, bundle))
    if part == "parent":
        value["parent_hash"] = "0" * 64
    elif part == "edit_evidence":
        value["edits"][0]["evidence_ids"] = ["invented"]
    elif part == "rule_evidence":
        value["edits"][0]["rule"]["evidence_ids"] = ["invented"]
    elif part == "reason":
        value["edits"][0]["reason"] = "  "
    else:
        value["edits"][0]["rule"]["execution_protocol"] = "Change the JSON wrapper"
    assert candidate_from_response(json.dumps(value), parent, bundle)["status"] == "invalid"


@pytest.mark.parametrize("value", [0, 3, 8, True, 1.0])
def test_edit_budget_rejected_before_model_call(value):
    parent, bundle = inputs()
    with pytest.raises(ValueError, match="edit budget"):
        build_update_request(parent, bundle, max_edits=value)


def test_unknown_preserved_and_literal_no_update_normal():
    parent, bundle = inputs(unknown=True)
    request = build_update_request(parent, bundle)
    pair = json.loads(request["user"])["feedback"]["paired_development"][0]
    assert all(role["status"] == "unknown" for role in pair["roles"].values())
    assert candidate_from_response("NO_UPDATE", parent, bundle)["status"] == "no_update"


def test_removing_all_rules_does_not_invent_learning_or_commit():
    parent = RuleSkill("fixture-history", (rule("old_ref"),))
    parent, bundle = inputs(parent)
    evidence = build_update_request(parent, bundle)["evidence_catalog"][0]["id"]
    update = RuleUpdate(parent.content_hash, (RuleEdit("remove", "preserve", None, (evidence,),
                                                      "Withdraw an unsupported rule."),))
    result = candidate_from_response(json.dumps(update.to_dict()), parent, bundle)
    assert result["status"] == "candidate" and result["candidate_text"] == ""
    assert result["empty_candidate"] and result["zero_learned_content"]
    assert not result["deployment_authorized"]


def test_scope_request_records_hypothesis_without_changing_text():
    parent = RuleSkill("fixture-history", (rule("old_ref"),))
    parent, bundle = inputs(parent)
    evidence = build_update_request(parent, bundle)["evidence_catalog"][0]["id"]
    proposed = rule(evidence, scope=ScopeRule(("requested_behavior",)))
    update = RuleUpdate(parent.content_hash, (RuleEdit("scope_expansion_request", "preserve", proposed,
                                                       (evidence,), "Needs new scope evidence."),))
    result = candidate_from_response(json.dumps(update.to_dict()), parent, bundle)
    assert result["status"] == "scope_pending" and result["candidate_text"] is None
    assert len(result["scope_expansion_requests"]) == 1


def test_new_evidence_reference_alone_is_not_a_new_behavioral_candidate():
    parent = RuleSkill("fixture-history", (rule("old_ref"),))
    parent, bundle = inputs(parent)
    result = candidate_from_response(response(parent, bundle, operation="replace"), parent, bundle)
    assert result["status"] == "metadata_only"
    assert result["candidate_text"] == render_skill(parent)
    assert not result["solver_visible_content_changed"] and not result["deployment_authorized"]


def test_parent_host_evidence_references_never_enter_updater_context():
    parent = RuleSkill("fixture-history", (rule("PRIVATE_OLD_AUDIT_REFERENCE"),))
    parent, bundle = inputs(parent)
    request = build_update_request(parent, bundle)
    assert "PRIVATE_OLD_AUDIT_REFERENCE" not in request["user"] + request["system"]
    assert "evidence_ids" not in json.loads(request["user"])["parent_rules"][0]


def test_delete_and_add_does_not_inherit_authority_for_new_broader_rule():
    parent = RuleSkill("fixture-history", (rule("old_ref"),))
    parent, bundle = inputs(parent)
    evidence = build_update_request(parent, bundle)["evidence_catalog"][0]["id"]
    r = rule(evidence, id="new_rule", scope=ScopeRule(("requested_behavior",)))
    update = RuleUpdate(parent.content_hash, (
        RuleEdit("remove", "preserve", None, (evidence,), "Remove the old proposal."),
        RuleEdit("add", "new_rule", r, (evidence,), "New scope needs independent confirmation.")))
    result = candidate_from_response(json.dumps(update.to_dict()), parent, bundle)
    assert result["status"] == "candidate" and result["confirmation_required"]
    assert result["scope_status"] == "unconfirmed_proposal_only" and not result["deployment_authorized"]


def test_whole_text_candidate_uses_legacy_parser_but_no_scope_authority():
    parent, bundle = inputs()
    md = "## Mechanism\nPreserve state.\n## When\nExplicitly required.\n## Procedure\nCompare input state.\n## Avoid\nIn-place tasks."
    result = candidate_from_response(md, parent, bundle, update_mode="whole_text")
    assert result["status"] == "candidate" and result["candidate_text"] == md
    assert result["candidate"] is None and result["confirmation_required"]


def test_engineering_authority_never_masquerades_as_real_authorization():
    parent, bundle = inputs()
    authority = seal({"version": "skill-admission-authority-v1", "pipeline_hash": bundle["pipeline_hash"],
                      "engineering_simulation": True, "status": "engineering_accepted"})
    request = build_update_request(parent, bundle, authority=authority, engineering_simulation=True)
    assert request["feedback_use"] == "engineering_authorized_diagnostic"
    with pytest.raises(ValueError, match="Engineering authority"):
        build_update_request(parent, bundle, authority=authority)


def test_pending_authority_blocks_even_valid_proposal():
    parent, bundle = inputs()
    authority = seal({"version": "skill-admission-authority-v1", "pipeline_hash": bundle["pipeline_hash"],
                      "engineering_simulation": False, "status": "pending"})
    with pytest.raises(ValueError, match="not authorized"):
        build_update_request(parent, bundle, authority=authority)


def test_changed_evidence_is_integrity_error_not_model_invalid():
    parent, bundle = inputs()
    bundle = deepcopy(bundle)
    bundle["entries"][0]["private_truth"] = "DO_NOT_SHOW"
    bundle = seal({k: v for k, v in bundle.items() if k != "record_hash"})
    with pytest.raises(ValueError):
        candidate_from_response("NO_UPDATE", parent, bundle)


@pytest.mark.parametrize("ok", [False, True])
def test_api_outcome_and_proposal_parse_outcome_are_separate(ok):
    parent, bundle = inputs()
    calls = FixtureCalls("NO_UPDATE", ok=ok)
    result = propose(calls, parent, bundle)
    assert len(calls.calls) == 1
    assert (result["update"]["status"] if ok else result["status"]) == ("no_update" if ok else "api_failure")
    assert not result["deployment_authorized"]


def test_wrong_request_receipt_is_rejected():
    parent, bundle = inputs()
    class WrongCalls(FixtureCalls):
        def call(self, *args, **kwargs):
            receipt = super().call(*args, **kwargs)
            receipt["request"]["user"] = "DIFFERENT_EVIDENCE"
            receipt["request_hash"] = digest(receipt["request"])
            return receipt
    with pytest.raises(ValueError, match="another request"):
        propose(WrongCalls("NO_UPDATE"), parent, bundle)
