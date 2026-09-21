"""Bounded public-input generation tests: no model, oracle or code execution."""
import json
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation.checks import CallableTask, PublicCase
from skillopt.skill_validation.models import Obligation, RubricCheck, RubricVersion, TaskContract
from skillopt.skill_validation.probe_recipes import (
    ORDER_QUOTE,
    HostInputCapability,
    InputStateProbeRecipe,
    bind_rubric,
    instantiate,
)


def task(values=(1, 2, 3), *, preserve=True, order_permission=True, index=0):
    return_quote = "Return the sorted input."
    preservation_quote = "Do not modify the input list." if preserve else "Sort the input list in place."
    prompt = return_quote + " " + preservation_quote
    if order_permission:
        prompt += " " + ORDER_QUOTE
    obligations = (Obligation("return", "requested_behavior", return_quote, return_quote),)
    if preserve:
        obligations += (Obligation("state", "input_preservation", preservation_quote, preservation_quote),)
    contract = TaskContract("probe-fixture", "probe-fixture", "fixture-family", "fixture-project",
                            "development", "coding", "constraint_preservation", prompt, obligations)
    args = [list(values)] if index == 0 else ["untouched", list(values)]
    case = PublicCase("example", json.dumps({"args": args, "kwargs": {"limit": 9}}), return_quote,
                      tuple(o.id for o in obligations), expected_json=json.dumps(sorted(values)))
    return CallableTask(contract, "solution", "solve", (case,))


def rubric():
    return RubricVersion("fixture", "constraint_preservation", "registered-public-cases",
                         "stage2-contract-checks-v1", "explicit-public-obligation-v1", "common-task-obligations-v1",
                         (RubricCheck("state", "input_preservation", "input_state", "explicit_obligation",
                                      "absent_obligation", "Observe input state before and after execution."),))


def test_reverses_one_public_list_without_expected_answer_or_mutating_original():
    original = task()
    before = original.to_dict()
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert original.to_dict() == before
    assert output.contract == original.contract
    assert output.public_cases[:-1] == original.public_cases
    generated = output.public_cases[-1]
    assert json.loads(generated.arguments_json) == {"args": [[3, 2, 1]], "kwargs": {"limit": 9}}
    assert generated.obligation_ids == ("state",)
    assert generated.expected_json is None and generated.expected_exception is None
    assert receipt["status"] == "proposed_only" and not receipt["confirmed_failure"]
    assert not receipt["execution_performed"]
    assert verify(receipt)["result_callable_task_hash"] == output.content_hash


def test_preserves_other_arguments_and_mutable_nested_values():
    original = task(index=1)
    output, _ = instantiate(original, InputStateProbeRecipe("reverse_list"),
                            HostInputCapability(original.contract.content_hash, 1))
    assert json.loads(output.public_cases[-1].arguments_json)["args"] == ["untouched", [3, 2, 1]]


def test_no_capability_does_not_infer_one_from_prompt():
    original = task()
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"))
    assert output is original and receipt["status"] == "unsupported"
    assert receipt["reason"] == "missing_host_input_capability"


def test_near_miss_task_never_gets_preservation_obligation():
    original = task(preserve=False)
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is original and receipt["status"] == "not_applicable"
    assert receipt["reason"] == "no_explicit_input_preservation_obligation"


def test_capability_cannot_be_reused_for_another_contract():
    original = task()
    other = replace(original, contract=replace(original.contract, task_id="another-task"))
    output, receipt = instantiate(other, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is other and receipt["reason"] == "host_capability_task_mismatch"


def test_missing_public_permission_is_unsupported():
    original = task(order_permission=False)
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is original and receipt["reason"] == "arbitrary_order_permission_not_public"


@pytest.mark.parametrize("values", [(), (1,), (1, 2, 1), (4, 4)])
def test_empty_or_identical_reversal_does_not_add_duplicate_input(values):
    original = task(values)
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is original and receipt["reason"] == "no_new_supported_list_ordering"


def test_existing_reverse_is_not_added_again():
    original = task()
    reverse = replace(original.public_cases[0], id="already-reversed",
                      arguments_json=json.dumps({"args": [[3, 2, 1]], "kwargs": {"limit": 9}}))
    original = replace(original, public_cases=original.public_cases + (reverse,))
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is original and receipt["status"] == "not_applicable"


@pytest.mark.parametrize("arguments", [{"args": [], "kwargs": {}},
                                      {"args": ["not a list"], "kwargs": {}},
                                      {"args": [{"nested": [1, 2]}], "kwargs": {}}])
def test_absent_or_wrong_argument_type_is_not_transformed(arguments):
    original = task()
    original = replace(original, public_cases=(replace(original.public_cases[0], arguments_json=json.dumps(arguments)),))
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is original and receipt["status"] == "not_applicable"


def test_exceptional_examples_are_not_assumed_valid_ordinary_inputs():
    original = task()
    original = replace(original, public_cases=(replace(original.public_cases[0], expected_json=None,
                                                      expected_exception="ValueError"),))
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is original and receipt["status"] == "not_applicable"


def test_budget_is_one_and_case_capacity_is_respected():
    original = task()
    original = replace(original, public_cases=tuple(replace(original.public_cases[0], id=f"case-{i}") for i in range(16)))
    output, receipt = instantiate(original, InputStateProbeRecipe("reverse_list"),
                                  HostInputCapability(original.contract.content_hash, 0))
    assert output is original and receipt["reason"] == "public_case_budget_exhausted"
    for invalid in (0, 2, True):
        with pytest.raises(ValueError):
            InputStateProbeRecipe("reverse_list", invalid)


def test_replay_and_repeated_instantiation_are_deterministic():
    original = task()
    recipe = InputStateProbeRecipe("reverse_list")
    capability = HostInputCapability(original.contract.content_hash, 0)
    assert instantiate(original, recipe, capability) == instantiate(original, recipe, capability)
    output, _ = instantiate(original, recipe, capability)
    repeated, receipt = instantiate(output, recipe, capability)
    assert repeated is output and receipt["status"] == "not_applicable"


def test_multiple_examples_cannot_exceed_one_generated_case_on_replay():
    original = task()
    second = replace(original.public_cases[0], id="second",
                     arguments_json=json.dumps({"args": [[7, 8, 9]], "kwargs": {"limit": 9}}))
    original = replace(original, public_cases=original.public_cases + (second,))
    recipe = InputStateProbeRecipe("reverse_list")
    capability = HostInputCapability(original.contract.content_hash, 0)
    output, _ = instantiate(original, recipe, capability)
    repeated, receipt = instantiate(output, recipe, capability)
    assert len(output.public_cases) == 3
    assert repeated is output and receipt["reason"] == "recipe_already_instantiated"


def test_disabled_recipe_needs_no_capability():
    original = task()
    output, receipt = instantiate(original, InputStateProbeRecipe())
    assert output is original and receipt["reason"] == "recipe_disabled"


def test_model_capability_dictionary_and_unregistered_permission_are_rejected():
    original = task()
    with pytest.raises(ValueError, match="registered by the host"):
        instantiate(original, InputStateProbeRecipe("reverse_list"), {"task_hash": original.contract.content_hash})
    with pytest.raises(ValueError, match="arbitrary-order"):
        HostInputCapability(original.contract.content_hash, 0, "Anything is valid.")
    with pytest.raises(ValueError, match="Unregistered"):
        InputStateProbeRecipe("execute_custom_python")


def test_binding_changes_pipeline_for_recipe_or_implementation_changes(monkeypatch):
    original = rubric()
    enabled = bind_rubric(original, InputStateProbeRecipe("reverse_list"))
    disabled = bind_rubric(original, InputStateProbeRecipe("none"))
    assert enabled.content_hash != disabled.content_hash != original.content_hash
    assert enabled.parent_hash == original.content_hash
    assert enabled == bind_rubric(original, InputStateProbeRecipe("reverse_list"))
    policy = json.loads(enabled.generation_policy)
    assert policy["recipe_hash"] == InputStateProbeRecipe("reverse_list").content_hash
    monkeypatch.setattr("skillopt.skill_validation.probe_recipes.implementation_hash", lambda: "b" * 64)
    changed = bind_rubric(original, InputStateProbeRecipe("reverse_list"))
    assert changed.pipeline_hash != enabled.pipeline_hash


def test_enabled_recipe_requires_input_state_checker():
    original = rubric()
    check = replace(original.checks[0], method="public_examples", obligation_kind="requested_behavior")
    with pytest.raises(ValueError, match="input-state"):
        bind_rubric(replace(original, checks=(check,)), InputStateProbeRecipe("reverse_list"))


def test_serializable_recipe_rejects_unknown_fields():
    recipe = InputStateProbeRecipe("reverse_list")
    assert InputStateProbeRecipe.from_dict(recipe.to_dict()) == recipe
    with pytest.raises(ValueError):
        InputStateProbeRecipe.from_dict({**recipe.to_dict(), "hidden_expected_answer": 3})
