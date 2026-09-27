"""Engineering controls for bounded Skill edits; not model-effect evidence."""
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from skillopt.skill_validation.admission import ScopeRule
from skillopt.skill_validation.checks import CallableTask
from skillopt.skill_validation.models import Obligation, TaskContract
from skillopt.skill_validation.rule_skill import (
    MAX_RENDER_BYTES, Rule, RuleEdit, RuleSkill, RuleUpdate, RuleUpdateResult,
    apply_update, render_for_task, render_skill,
)


def rule(identifier="keep-input", scope=None):
    return Rule(identifier, "Constraint Preservation", ("Compare input state before and after execution.",),
                "Only when the task explicitly requires unchanged input.",
                ("Do not apply when the task permits input mutation.",),
                scope or ScopeRule(("input_preservation",)), ("visible-case-1",))


def task(preserve=True):
    prompt = "Return a sorted copy. Do not mutate the input." if preserve else "Sort input in place."
    obligations = (Obligation("answer", "requested_behavior", prompt, prompt),)
    if preserve:
        obligations += (Obligation("input", "input_preservation", "Do not mutate the input.",
                                   "Do not mutate the input."),)
    contract = TaskContract("t", "original-t", "hidden-family", "hidden-project", "development",
                            "coding", "hidden-mechanism", prompt, obligations)
    return CallableTask(contract, "solution", "solve", ())


def update(parent, *edits):
    return RuleUpdate(parent.content_hash, tuple(edits))


def test_cold_is_canonical_empty_and_history_bound():
    cold = RuleSkill("h0", ())
    assert render_skill(cold) == ""
    assert RuleSkill.from_dict(cold.to_dict()) == cold
    assert cold.content_hash != RuleSkill("h1", ()).content_hash
    assert render_for_task(cold, task())["text"] == ""


@pytest.mark.parametrize("value", [rule(), RuleSkill("h0", (rule(),)), RuleEdit("remove", "keep-input"),
                                  RuleEdit("no_update", reason="No justified change.")])
def test_strict_json_roundtrip_and_detached_views(value):
    raw = json.loads(json.dumps(value.to_dict()))
    assert type(value).from_dict(raw) == value
    raw["unexpected_host_answer"] = "must not be accepted"
    with pytest.raises(ValueError):
        type(value).from_dict(raw)


def test_update_and_result_roundtrip():
    cold = RuleSkill("h0", ())
    proposal = update(cold, RuleEdit("add", rule().id, rule(), ("visible-case-1",), "Observed regression."))
    assert RuleUpdate.from_dict(proposal.to_dict()) == proposal
    result = apply_update(cold, proposal)
    assert RuleUpdateResult.from_dict(result.to_dict()) == result
    assert result.changed and result.applied_rule_ids == (rule().id,)
    assert result.deployment_authorized is False
    assert result.skill.history_id == cold.history_id


def test_frozen_nested_containers_and_unique_ids():
    skill = RuleSkill("h0", (rule(),))
    with pytest.raises(FrozenInstanceError):
        skill.history_id = "h1"
    with pytest.raises(ValueError):
        RuleSkill("h0", [rule()])
    with pytest.raises(ValueError):
        RuleSkill("h0", (rule(), rule()))
    detached = skill.to_dict()
    detached["rules"][0]["procedure"][0] = "changed"
    assert skill.rules[0].procedure == rule().procedure


@pytest.mark.parametrize("field", ["procedure", "exceptions", "evidence_ids"])
def test_string_is_not_json_array(field):
    value = rule().to_dict()
    value[field] = "not-an-array"
    with pytest.raises(ValueError):
        Rule.from_dict(value)


def test_exact_scope_rejects_hidden_domain_and_labels():
    raw = rule().to_dict()
    raw["scope"]["domain"] = "coding"
    with pytest.raises(ValueError):
        Rule.from_dict(raw)
    raw = rule().to_dict()
    raw["scope"]["required_obligation_kinds"] = ["hidden-mechanism"]
    with pytest.raises(ValueError):
        Rule.from_dict(raw)
    raw["scope"]["required_obligation_kinds"] = [{"answer": 42}]
    with pytest.raises(ValueError):
        Rule.from_dict(raw)


@pytest.mark.parametrize("field,value", [("id", "unstable id"), ("mechanism", ""),
    ("procedure", ()), ("when", ""), ("evidence_ids", ("same", "same")), ("procedure", ["step"])])
def test_invalid_rule_fields(field, value):
    with pytest.raises(ValueError):
        replace(rule(), **{field: value})


def test_rule_and_skill_size_budgets():
    with pytest.raises(ValueError):
        replace(rule(), when="x" * 1025)
    long = replace(rule(), procedure=("x" * 1024,) * 5)
    with pytest.raises(ValueError):
        RuleSkill("h0", (long, replace(rule("other"), when="x" * 1024)))
    with pytest.raises(ValueError):
        RuleSkill("h0", tuple(rule(str(i)) for i in range(9)))
    eight = RuleSkill("h0", tuple(rule(str(i)) for i in range(8)))
    assert len(render_skill(eight).encode()) <= MAX_RENDER_BYTES


def test_full_render_keeps_all_scope_when_and_exceptions():
    skill = RuleSkill("h0", (rule(), rule("second", ScopeRule(("requested_behavior",)))))
    rendered = render_skill(skill)
    for r in skill.rules:
        assert r.id in rendered and r.when in rendered and all(e in rendered for e in r.exceptions)
    assert "input_preservation" in rendered and "no deployment authorization" in rendered
    # Evidence references are retained host-side rather than presented as truth.
    assert "visible-case-1" not in rendered


def test_public_preconditions_disable_rule_without_hidden_metadata():
    skill = RuleSkill("h0", (rule(),))
    applicable = render_for_task(skill, task(True))
    absent = render_for_task(skill, task(False))
    assert applicable["selected_rule_ids"] == ["keep-input"]
    assert applicable["disabled_rule_ids"] == []
    assert absent["selected_rule_ids"] == [] and absent["text"] == ""
    assert absent["disabled_rule_ids"] == ["keep-input"]
    assert applicable["deployment_authorized"] is False
    assert "syntax_only" in applicable["scope_basis"]
    altered = replace(task(True), contract=replace(task(True).contract, mechanism="different-hidden-mechanism",
                        family_id="different-hidden-family", project_id="different-project", partition="final"))
    assert render_for_task(skill, altered) == applicable
    assert "hidden-mechanism" not in json.dumps(applicable) and "hidden-family" not in json.dumps(applicable)


def test_forbidden_public_kind_disables_rule():
    r = rule(scope=ScopeRule(("requested_behavior",), ("input_preservation",)))
    skill = RuleSkill("h0", (r,))
    assert render_for_task(skill, task(True))["selected_rule_ids"] == []
    assert render_for_task(skill, task(False))["selected_rule_ids"] == [r.id]


def test_no_update_and_identical_replace_are_true_noops():
    parent = RuleSkill("h0", (rule(),))
    for edit in (RuleEdit("no_update"), RuleEdit("replace", rule().id, rule())):
        result = apply_update(parent, update(parent, edit))
        assert result.skill == parent and not result.changed
        assert result.applied_rule_ids == ()


def test_remove_can_return_to_cold():
    parent = RuleSkill("h0", (rule(),))
    result = apply_update(parent, update(parent, RuleEdit("remove", rule().id,
                              evidence_ids=("case-with-bad-advice",), reason="Rule caused interference.")))
    assert result.changed and result.skill.rules == ()
    assert render_skill(result.skill) == ""


@pytest.mark.parametrize("operation", ["replace", "remove", "scope_expansion_request"])
def test_edit_requires_existing_parent_id(operation):
    parent = RuleSkill("h0", ())
    edit = RuleEdit(operation, rule().id, None if operation == "remove" else rule())
    with pytest.raises(ValueError, match="does not exist"):
        apply_update(parent, update(parent, edit))


def test_add_existing_and_duplicate_targets_rejected():
    parent = RuleSkill("h0", (rule(),))
    with pytest.raises(ValueError, match="already exists"):
        apply_update(parent, update(parent, RuleEdit("add", rule().id, rule())))
    with pytest.raises(ValueError, match="Duplicate"):
        update(parent, RuleEdit("remove", rule().id), RuleEdit("replace", rule().id, rule()))


def test_parent_hash_and_cross_history_binding():
    parent = RuleSkill("h0", (rule(),))
    other = RuleSkill("h1", (rule(),))
    with pytest.raises(ValueError, match="bound"):
        apply_update(other, update(parent, RuleEdit("no_update")))
    with pytest.raises(ValueError, match="SHA256"):
        RuleUpdate("not-a-hash", (RuleEdit("no_update"),))


def test_fixed_edit_budget_cannot_be_raised_by_caller():
    parent = RuleSkill("h0", ())
    edits = tuple(RuleEdit("add", str(i), rule(str(i))) for i in range(3))
    with pytest.raises(ValueError):
        RuleUpdate(parent.content_hash, edits)
    proposal = RuleUpdate(parent.content_hash, edits[:2])
    for budget in (True, 0, 3, 1.5):
        with pytest.raises(ValueError):
            apply_update(parent, proposal, max_edits=budget)
    with pytest.raises(ValueError, match="budget"):
        apply_update(parent, proposal, max_edits=1)
    assert len(apply_update(parent, proposal).skill.rules) == 2


def test_replace_can_keep_or_narrow_but_not_expand_scope():
    original = rule(scope=ScopeRule(("requested_behavior",), ("file_preservation",)))
    parent = RuleSkill("h0", (original,))
    narrower = replace(original, scope=ScopeRule(("input_preservation", "requested_behavior"),
                                                 ("file_preservation",)))
    result = apply_update(parent, update(parent, RuleEdit("replace", original.id, narrower)))
    assert result.changed and result.skill.rules == (narrower,)
    required_dropped = replace(narrower, scope=original.scope)
    forbidden_dropped = replace(original, scope=ScopeRule(("requested_behavior",)))
    for source, candidate in ((result.skill, required_dropped), (parent, forbidden_dropped)):
        with pytest.raises(ValueError, match="cannot expand"):
            apply_update(source, update(source, RuleEdit("replace", original.id, candidate)))


def test_scope_expansion_is_recorded_only_never_applied():
    parent = RuleSkill("h0", (rule(),))
    proposal = replace(rule(), scope=ScopeRule(("requested_behavior",)))
    edit = RuleEdit("scope_expansion_request", rule().id, proposal, ("development-case",),
                    "Hypothesis requiring independent confirmation.")
    result = apply_update(parent, update(parent, edit))
    assert result.skill == parent and result.changed is False
    assert result.scope_expansion_requests == (edit,) and result.applied_rule_ids == ()
    assert result.deployment_authorized is False


def test_no_evidence_authority_inferred_and_no_update_cannot_hide_edit():
    candidate = replace(rule(), evidence_ids=())
    cold = RuleSkill("h0", ())
    # Integration must validate references; this model never fabricates evidence.
    assert apply_update(cold, update(cold, RuleEdit("add", candidate.id, candidate))).deployment_authorized is False
    with pytest.raises(ValueError):
        RuleEdit("no_update", rule().id, rule())
    with pytest.raises(ValueError):
        update(cold, RuleEdit("no_update"), RuleEdit("add", candidate.id, candidate))
    with pytest.raises(ValueError):
        RuleUpdate(cold.content_hash, ())


def test_exact_edits_cannot_smuggle_authority_or_wrong_id():
    edit = RuleEdit("remove", rule().id)
    raw = edit.to_dict()
    raw["deployment_authorized"] = True
    with pytest.raises(ValueError):
        RuleEdit.from_dict(raw)
    with pytest.raises(ValueError):
        RuleEdit("replace", "other", rule())
    with pytest.raises(ValueError):
        RuleEdit("remove", rule().id, rule())
    result = apply_update(RuleSkill("h0", ()), RuleUpdate(RuleSkill("h0", ()).content_hash,
                                                        (RuleEdit("no_update"),)))
    with pytest.raises(ValueError):
        replace(result, deployment_authorized=True)
