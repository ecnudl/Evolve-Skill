"""Offline engineering fixtures only; no evidence of model or transfer benefit."""
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.admission import ScopeRule
from skillopt.skill_validation.mechanism_learning import (
    CALL_KIND,
    COMMON_PROMPT,
    MAX_EDITS,
    RULE_JSON_SKELETON,
    RULE_SCHEMA,
    STRATEGIES,
    STRATEGY_PROMPTS,
    VERSION,
    build_request,
    inline_evidence_ids,
    propose,
)
from skillopt.skill_validation.rule_learning import build_update_request, candidate_from_response
from skillopt.skill_validation.rule_skill import RuleEdit, RuleSkill, RuleUpdate, render_skill
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import FixtureCalls
from tests.test_skill_validation_rule_learning import inputs, response, rule


@pytest.mark.parametrize("legacy", [False, True])
def test_arms_have_identical_user_evidence_representation_and_budgets(legacy):
    parent, bundle = inputs(legacy=legacy, repeats=2)
    requests = {strategy: build_request(parent, bundle, strategy=strategy) for strategy in STRATEGIES}
    left, right = requests.values()
    assert left["user"] == right["user"]
    assert left["system"] != right["system"]
    # The treatment changes only strategy/system and their hashes, not evidence
    # selection, catalog, schema, allowed edits, representation or authority.
    excluded = {"strategy", "system", "prompt_hash", "record_hash"}
    assert {k: v for k, v in left.items() if k not in excluded} == {
        k: v for k, v in right.items() if k not in excluded}
    for strategy, request in requests.items():
        verify(request)
        assert request["system"] == COMMON_PROMPT + STRATEGY_PROMPTS[strategy] + RULE_SCHEMA
        assert request["max_edits"] == MAX_EDITS == 2
        assert request["max_tokens"] == 2048
        assert request["update_mode"] == "rule_patch"
        assert request["feedback_mode"] == "evidence"
        assert request["feedback_use"] == "shadow_diagnostic_only"
        assert request["verifier_authority_hash"] is None
        assert request["confirmation_required"] and not request["deployment_authorized"]
        assert request["version"] == VERSION == "same-feedback-mechanism-learning-v3"


@pytest.mark.parametrize("legacy", [False, True])
def test_inline_ids_bind_each_public_case_and_before_after_hashes_without_changing_facts(legacy):
    parent, bundle = inputs(legacy=legacy, repeats=2)
    source_request = build_update_request(parent, bundle)
    source_user = source_request["user"]
    original = json.loads(source_user)
    annotated_user, annotation = inline_evidence_ids(source_user)
    annotated = json.loads(annotated_user)
    assert annotation == {
        "version": "inline-public-evidence-handles-v1",
        "source_user_hash": digest(source_user), "annotated_user_hash": digest(annotated_user),
        "source_feedback_view_hash": digest(original["feedback"]),
        "annotated_feedback_view_hash": digest(annotated["feedback"]),
        "semantic_support_verified": False,
    }
    assert annotation["source_feedback_view_hash"] == source_request["feedback_view_hash"]
    assert annotation["source_feedback_view_hash"] != annotation["annotated_feedback_view_hash"]
    for source, marked in zip(original["feedback"]["paired_development"],
                              annotated["feedback"]["paired_development"]):
        assert marked["evidence_id"] == "ev_" + digest(source)[:24]
        assert marked.pop("evidence_id") in {item["id"] for item in original["evidence_catalog"]}
    assert annotated == original
    assert source_user == source_request["user"]  # The original parser view is unchanged.
    request = build_request(parent, bundle, strategy="local")
    assert request["user"] == annotated_user and request["evidence_annotation"] == annotation
    assert request["parser_request_hash"] == source_request["record_hash"]
    assert request["feedback_view_hash"] == source_request["feedback_view_hash"]


def test_inline_duplicate_details_share_existing_id_despite_single_catalog_location():
    parent, bundle = inputs()
    source = json.loads(build_update_request(parent, bundle)["user"])
    pair = source["feedback"]["paired_development"][0]
    source["feedback"]["paired_development"].append(deepcopy(pair))
    source["evidence_catalog"][0]["location"] = ["paired_development", 1]
    annotated, _ = inline_evidence_ids(json.dumps(source))
    payload = json.loads(annotated)
    assert len(payload["evidence_catalog"]) == 1
    assert [item["evidence_id"] for item in payload["feedback"]["paired_development"]] == [
        source["evidence_catalog"][0]["id"]] * 2


def test_inline_contract_only_uses_the_same_binding_without_inventing_observations():
    parent, bundle = inputs()
    source = build_update_request(parent, bundle, feedback_mode="contract_only")
    marked, _ = inline_evidence_ids(source["user"])
    payload = json.loads(marked)
    assert "paired_development" not in payload["feedback"]
    assert all("evidence_id" in item and "roles" not in item
               for item in payload["feedback"]["development_contracts"])


@pytest.mark.parametrize("tamper", ["root_field", "digest", "location_field", "location_bounds", "location_bool",
    "origin", "kind", "duplicate_catalog", "missing_catalog", "unbound_detail", "preannotated_detail"])
def test_inline_evidence_binding_fails_closed_without_guessing_or_correction(tamper):
    parent, bundle = inputs()
    source = json.loads(build_update_request(parent, bundle)["user"])
    catalog = source["evidence_catalog"]
    if tamper == "root_field":
        source["hidden_audit"] = "not a projected model view"
    elif tamper == "digest":
        catalog[0]["id"] = "ev_" + "0" * 24
    elif tamper == "location_field":
        catalog[0]["location"][0] = "host_only"
    elif tamper == "location_bounds":
        catalog[0]["location"][1] = 1000
    elif tamper == "location_bool":
        catalog[0]["location"][1] = False
    elif tamper == "origin":
        catalog[0]["origin"] = "hidden_audit"
    elif tamper == "kind":
        catalog[0]["kind"] = "hidden_audit"
    elif tamper == "duplicate_catalog":
        catalog.append(deepcopy(catalog[0]))
    elif tamper == "missing_catalog":
        catalog.clear()
    elif tamper == "unbound_detail":
        other = deepcopy(source["feedback"]["paired_development"][0])
        other["task"]["prompt"] += " Another public fixture."
        source["feedback"]["paired_development"].append(other)
    else:
        source["feedback"]["paired_development"][0]["evidence_id"] = catalog[0]["id"]
    before = deepcopy(source)
    with pytest.raises(ValueError):
        inline_evidence_ids(json.dumps(source))
    assert source == before


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_inline_annotation_does_not_certify_or_correct_semantically_wrong_existing_citation(strategy):
    # The only fixture evidence here is unknown. The deliberately false claim
    # is structurally valid and must stay unverified, not be silently repaired.
    parent, bundle = inputs(unknown=True)
    raw = json.loads(response(parent, bundle))
    raw["edits"][0]["reason"] = "This supplied observation proves an executed semantic failure."
    raw = json.dumps(raw)
    result = propose(FixtureCalls(raw), parent, bundle, strategy=strategy)
    assert result["status"] == "candidate" and result["api_receipt"]["response"] == raw
    assert result["update"]["proposal"]["edits"][0]["reason"] == json.loads(raw)["edits"][0]["reason"]
    assert not result["update"]["semantic_support_verified"] and not result["deployment_authorized"]
    visible = json.loads(result["request"]["user"])
    assert all(role["status"] == "unknown" for pair in visible["feedback"]["paired_development"]
               for role in pair["roles"].values())
    assert result["update"]["evidence_annotation"] == result["request"]["evidence_annotation"]


def test_shared_skeleton_has_complete_nesting_without_injected_lesson_or_scope():
    skeleton = json.loads(RULE_JSON_SKELETON)
    assert set(skeleton) == {"parent_hash", "edits"}
    edit, = skeleton["edits"]
    assert set(edit) == {"operation", "rule_id", "rule", "evidence_ids", "reason"}
    assert set(edit["rule"]) == {
        "id", "mechanism", "procedure", "when", "exceptions", "scope", "evidence_ids"}
    assert edit["rule_id"] == edit["rule"]["id"]
    assert edit["evidence_ids"] == edit["rule"]["evidence_ids"] == ["<id_from_evidence_catalog>"]
    assert edit["rule"]["scope"] == {
        "required_obligation_kinds": ["<allowed_public_obligation_kind>"],
        "forbidden_obligation_kinds": []}
    assert edit["rule"]["exceptions"] == []
    def leaves(value):
        if type(value) is dict:
            return [leaf for nested in value.values() for leaf in leaves(nested)]
        if type(value) is list:
            return [leaf for nested in value for leaf in leaves(nested)]
        return [value]
    assert all(type(v) is str and v.startswith("<") and v.endswith(">") for v in leaves(skeleton))
    assert RULE_SCHEMA.endswith(RULE_JSON_SKELETON)


def test_shared_prompt_disambiguates_fields_and_scope_without_parser_relaxation():
    for phrase in ("OWN evidence_ids array", "SECOND evidence_ids array", "rule_id is mandatory at edit level",
                   "reason is mandatory at edit level only", "SHORT NAME", "256 UTF-8 bytes",
                   "all required kinds must be present", "NO forbidden kind", "rejects entire tasks",
                   "does NOT prohibit an erroneous behavior", "empty forbidden list",
                   "do not exclude requested_behavior"):
        assert phrase in RULE_SCHEMA


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_filled_wire_scaffold_uses_existing_strict_parser(strategy):
    parent, bundle = inputs()
    evidence = build_request(parent, bundle, strategy=strategy)["evidence_catalog"][0]["id"]
    replacements = {
        "<supplied_parent_hash>": parent.content_hash,
        "<add_or_replace_or_scope_expansion_request>": "add",
        "<rule_identifier>": "fixture_preserve",
        "<short_mechanism_name>": "Constraint Preservation",
        "<bounded_procedural_step>": "Compare input state before and after the operation.",
        "<public_precondition>": "Only when the public task requires unchanged input.",
        "<allowed_public_obligation_kind>": "input_preservation",
        "<id_from_evidence_catalog>": evidence,
        "<brief_evidence_grounded_rationale>": "The public obligation supports the proposed state comparison.",
    }
    raw = RULE_JSON_SKELETON
    for placeholder, value in replacements.items():
        raw = raw.replace(placeholder, value)
    calls = FixtureCalls(raw)
    result = propose(calls, parent, bundle, strategy=strategy)
    expected = candidate_from_response(raw, parent, bundle)
    assert result["status"] == expected["status"] == "candidate"
    assert result["update"]["candidate"] == expected["candidate"]
    assert len(calls.calls) == 1 and not result["deployment_authorized"]


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("tamper", [
    "missing_edit_evidence", "missing_rule_evidence", "missing_rule_id", "reason_inside_rule",
    "long_mechanism_ascii", "long_mechanism_utf8", "placeholder_scaffold",
])
def test_format_smoke_failure_modes_remain_invalid_without_repair_or_retry(strategy, tamper):
    parent, bundle = inputs()
    proposed = json.loads(response(parent, bundle))
    edit = proposed["edits"][0]
    if tamper == "missing_edit_evidence":
        del edit["evidence_ids"]
    elif tamper == "missing_rule_evidence":
        del edit["rule"]["evidence_ids"]
    elif tamper == "missing_rule_id":
        del edit["rule_id"]
    elif tamper == "reason_inside_rule":
        edit["rule"]["reason"] = edit.pop("reason")
    elif tamper == "long_mechanism_ascii":
        edit["rule"]["mechanism"] = "x" * 257
    elif tamper == "long_mechanism_utf8":
        edit["rule"]["mechanism"] = "界" * 86
    raw = RULE_JSON_SKELETON if tamper == "placeholder_scaffold" else json.dumps(proposed)
    calls = FixtureCalls(raw)
    result = propose(calls, parent, bundle, strategy=strategy)
    assert result["status"] == "invalid" and result["update"]["candidate"] is None
    assert result["api_receipt"]["response"] == raw
    assert len(calls.calls) == 1 and not result["retry_authorized"]


def test_strategy_difference_is_explicit_and_does_not_invent_missing_contrasts():
    assert "local experience induction" in STRATEGY_PROMPTS["local"]
    for phrase in ("observed failure", "successful alternative", "condition-reversal",
                   "already-correct behavior", "absent", "do not fabricate"):
        assert phrase in STRATEGY_PROMPTS["mechanism"]
    assert "Scope predicates use explicit public task obligations only" in COMMON_PROMPT


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_no_skill_stays_empty_and_model_never_receives_host_provenance(strategy):
    parent, bundle = inputs()
    before = deepcopy(bundle)
    request = build_request(parent, bundle, strategy=strategy)
    visible = request["system"] + request["user"]
    payload = json.loads(request["user"])
    assert payload["parent_skill"] == "" and payload["parent_rules"] == []
    for hidden in ("fixture-history", "fixture-task", "fixture-family", "fixture-project",
                   "source_hash", "pipeline_hash", "execution_records", "hidden_audit", "host_only"):
        assert hidden not in visible
    assert render_skill(parent) == "" and bundle == before


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_old_parent_evidence_reference_not_exposed(strategy):
    parent, bundle = inputs(RuleSkill("fixture-history", (rule("PRIVATE_H_DIAGNOSIS"),)))
    request = build_request(parent, bundle, strategy=strategy)
    assert "PRIVATE_H_DIAGNOSIS" not in request["user"] + request["system"]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_candidate_retains_actual_prompt_complete_receipt_and_unconfirmed_state(strategy):
    parent, bundle = inputs()
    raw = response(parent, bundle)
    calls = FixtureCalls(raw)
    result = propose(calls, parent, bundle, strategy=strategy, repeat=2)
    update, request = result["update"], result["request"]
    verify(result)
    verify(request)
    verify(update)
    assert len(calls.calls) == 1 and calls.calls[0]["repeat"] == 2
    assert calls.calls[0]["kind"] == CALL_KIND
    assert result["fixture_only"] is True
    assert result["api_receipt"]["response"] == raw
    assert result["api_receipt_hash"] == digest(result["api_receipt"])
    assert update["status"] == result["status"] == "candidate"
    assert RuleSkill.from_dict(update["candidate"]).rules
    assert update["candidate"] == candidate_from_response(raw, parent, bundle)["candidate"]
    assert update["request_hash"] == update["actual_update_request_hash"] == request["record_hash"]
    assert update["parser_request_hash"] == build_update_request(parent, bundle)["record_hash"]
    assert update["parser_request_hash"] != update["request_hash"]
    assert update["parser_result_hash"] == candidate_from_response(raw, parent, bundle)["record_hash"]
    assert update["feedback_view_hash"] == request["feedback_view_hash"]
    assert update["confirmation_required"] and not update["semantic_support_verified"]
    assert not update["deployment_authorized"] and not update["retry_authorized"]
    assert update["scope_status"] == "unconfirmed_proposal_only"


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("answer,ok,status", [
    ("NO_UPDATE", True, "no_update"), ("{}", True, "invalid"),
    (None, True, "invalid"), ("NO_UPDATE", False, "api_failure"),
])
def test_non_candidate_outcomes_have_same_envelope_and_never_retry(strategy, answer, ok, status):
    parent, bundle = inputs()
    calls = FixtureCalls(answer, ok=ok)
    result = propose(calls, parent, bundle, strategy=strategy)
    assert result["status"] == result["update"]["status"] == status
    assert result["update"]["candidate"] is None
    assert result["update"]["candidate_text"] is None
    assert len(calls.calls) == 1 and not result["retry_authorized"]
    assert result["api_receipt"]["ok"] is ok
    assert not result["update"]["deployment_authorized"]
    assert (result["update"]["parser_result_hash"] is None) is (not ok)


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_unknown_feedback_not_hidden_or_relabeled_failure(strategy):
    parent, bundle = inputs(unknown=True)
    request = build_request(parent, bundle, strategy=strategy)
    pair = json.loads(request["user"])["feedback"]["paired_development"][0]
    assert all(role["status"] == "unknown" for role in pair["roles"].values())


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_unsupported_new_bundle_fields_cannot_be_serialized_to_prompt(strategy):
    parent, bundle = inputs()
    bundle["entries"][0]["hidden_audit"] = {"region": "near_miss", "mechanism": "SECRET_H"}
    bundle = seal({k: v for k, v in bundle.items() if k != "record_hash"})
    calls = FixtureCalls("NO_UPDATE")
    with pytest.raises(ValueError):
        propose(calls, parent, bundle, strategy=strategy)
    assert not calls.calls


@pytest.mark.parametrize("field", ["system", "user", "kind", "repeat", "max_tokens"])
def test_even_rehashed_wrong_request_is_integrity_error(field):
    parent, bundle = inputs()
    class WrongCalls(FixtureCalls):
        def call(self, *args, **kwargs):
            receipt = super().call(*args, **kwargs)
            receipt["request"][field] = "WRONG"
            receipt["request_hash"] = digest(receipt["request"])
            return receipt
    calls = WrongCalls("NO_UPDATE", ok=False)
    with pytest.raises(ValueError, match="another request or is incomplete"):
        propose(calls, parent, bundle, strategy="mechanism")
    assert len(calls.calls) == 1


@pytest.mark.parametrize("missing", ["request", "request_hash", "ok"])
def test_missing_receipt_is_integrity_error_not_no_update(missing):
    parent, bundle = inputs()
    class IncompleteCalls(FixtureCalls):
        def call(self, *args, **kwargs):
            receipt = super().call(*args, **kwargs)
            del receipt[missing]
            return receipt
    calls = IncompleteCalls("NO_UPDATE")
    with pytest.raises(ValueError):
        propose(calls, parent, bundle, strategy="local")
    assert len(calls.calls) == 1


def test_thrown_infrastructure_exception_not_swallowed_or_retried():
    parent, bundle = inputs()
    calls = FixtureCalls(error=RuntimeError("interrupted request retained"))
    with pytest.raises(RuntimeError, match="interrupted"):
        propose(calls, parent, bundle, strategy="mechanism")
    assert len(calls.calls) == 1


@pytest.mark.parametrize("options", [
    {"strategy": "whole_text"}, {"strategy": None}, {"strategy": []},
    {"strategy": "local", "repeat": True}, {"strategy": "local", "repeat": -1},
    {"strategy": "local", "max_tokens": True}, {"strategy": "local", "max_tokens": 2049},
    {"strategy": "local", "max_tokens": 0},
])
def test_invalid_control_parameters_fail_before_call(options):
    parent, bundle = inputs()
    calls = FixtureCalls("NO_UPDATE")
    with pytest.raises(ValueError):
        propose(calls, parent, bundle, **options)
    assert not calls.calls


def test_same_configured_lower_budget_in_both_arms_is_receipt_bound():
    parent, bundle = inputs()
    calls = FixtureCalls("NO_UPDATE")
    results = [propose(calls, parent, bundle, strategy=s, max_tokens=1024) for s in STRATEGIES]
    assert all(r["request"]["max_tokens"] == 1024 for r in results)
    assert all(call["max_tokens"] == 1024 for call in calls.calls)


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("tamper", ["evidence", "edits", "identity"])
def test_original_schema_and_evidence_guards_still_reject(strategy, tamper):
    parent, bundle = inputs()
    proposed = json.loads(response(parent, bundle))
    if tamper == "evidence":
        proposed["edits"][0]["rule"]["evidence_ids"] = ["HOST_HIDDEN_TRUTH"]
    elif tamper == "edits":
        proposed["edits"] *= 3
    else:
        proposed["parent_hash"] = "0" * 64
    result = propose(FixtureCalls(json.dumps(proposed)), parent, bundle, strategy=strategy)
    assert result["update"]["status"] == "invalid"
    assert result["update"]["candidate"] is None


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_removal_to_empty_explicitly_reports_zero_learned_content(strategy):
    parent, bundle = inputs(RuleSkill("fixture-history", (rule("old_ref"),)))
    evidence = build_request(parent, bundle, strategy=strategy)["evidence_catalog"][0]["id"]
    patch = RuleUpdate(parent.content_hash, (
        RuleEdit("remove", "preserve", None, (evidence,), "Withdraw the unsupported rule."),))
    result = propose(FixtureCalls(json.dumps(patch.to_dict())), parent, bundle, strategy=strategy)
    update = result["update"]
    assert update["status"] == "candidate" and update["candidate_text"] == ""
    assert update["zero_learned_content"] and update["empty_candidate"]
    assert update["confirmation_required"] and not update["deployment_authorized"]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_scope_expansion_request_does_not_change_active_skill(strategy):
    parent, bundle = inputs(RuleSkill("fixture-history", (rule("old_ref"),)))
    evidence = build_request(parent, bundle, strategy=strategy)["evidence_catalog"][0]["id"]
    broader = rule(evidence, scope=ScopeRule(("requested_behavior",)))
    patch = RuleUpdate(parent.content_hash, (RuleEdit("scope_expansion_request", "preserve", broader,
        (evidence,), "New scope needs independent confirmation."),))
    result = propose(FixtureCalls(json.dumps(patch.to_dict())), parent, bundle, strategy=strategy)
    assert result["update"]["status"] == "scope_pending"
    assert result["update"]["candidate"] is None
    assert result["update"]["scope_expansion_requests"]
    assert not result["update"]["deployment_authorized"]
