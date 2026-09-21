"""One bounded, host-authorized task-input recipe, not a new correctness oracle.

The reusable recipe can be selected by a Research proposal. Its permission to
transform a particular input comes only from a separately registered host
capability and an explicit public task contract. The generated case checks
input preservation, never predicts the transformed call's return value.

Instantiation has no access to artifacts, Skill identities, audit labels,
network, or an executor. Call it once per task and apply the same resulting
task to all paired artifacts. A proposed input is not a detected failure.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from .checks import CallableTask, PublicCase, json_value
from .models import Record, RubricVersion, exact_fields, hash_text, require

VERSION = "skill-validation-input-state-probes-v1"
ORDER_QUOTE = "Input values may be in any order."


@dataclass(frozen=True)
class InputStateProbeRecipe(Record):
    """Reusable choice; the budget is deliberately fixed at one added case."""

    choice: str = "none"
    max_cases: int = 1

    def __post_init__(self):
        require(self.choice in {"none", "reverse_list"}, "Unregistered probe recipe")
        require(type(self.max_cases) is int and self.max_cases == 1,
                "This bounded recipe permits exactly one additional case")

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class HostInputCapability(Record):
    """Host annotation, never a model proposal or inferred quote entailment.

    Registration asserts that arbitrary ordering is legal for this positional
    list argument. Exact quote matching is an additional boundary check, not a
    semantic proof. There is intentionally no model-dictionary import method.
    """

    task_hash: str
    positional_arg_index: int
    contract_quote: str = ORDER_QUOTE

    def __post_init__(self):
        hash_text(self.task_hash)
        require(type(self.positional_arg_index) is int and 0 <= self.positional_arg_index < 128,
                "A bounded positional argument index is required")
        require(self.contract_quote == ORDER_QUOTE,
                "Only the registered public arbitrary-order permission is supported")


def implementation_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def bind_rubric(rubric: RubricVersion, recipe: InputStateProbeRecipe) -> RubricVersion:
    """Bind recipe AND implementation to subsequent calibration authorization.

    A changed recipe or implementation creates a different Rubric/pipeline
    hash, so an authorization for the old test-generation procedure cannot be
    reused. No task-specific input list is mistaken for this reusable policy.
    """
    require(type(rubric) is RubricVersion and type(recipe) is InputStateProbeRecipe,
            "Typed rubric and recipe required")
    if recipe.choice != "none":
        require(any(c.method == "input_state" and c.obligation_kind == "input_preservation"
                    for c in rubric.checks), "Input probes require a registered input-state check")
    policy = {
        "version": VERSION,
        "base_generation_policy_hash": digest(rubric.generation_policy),
        "recipe": recipe.to_dict(),
        "recipe_hash": recipe.content_hash,
        "implementation_hash": implementation_hash(),
        "applicability": "host_registered_exact_contract_and_explicit_preservation",
        "pooling": "one_task_level_case_shared_by_all_conditions",
    }
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    return replace(rubric, version="probe-bound-" + digest([rubric.content_hash, policy])[:24],
                   generation_policy=encoded, parent_hash=rubric.content_hash)


def instantiate(task: CallableTask, recipe: InputStateProbeRecipe,
                capability: HostInputCapability | None = None) -> tuple[CallableTask, dict]:
    """Return the unchanged contract plus at most one proposed public input.

    Unsupported capabilities, Near-Miss tasks and exhausted budgets produce
    durable diagnostics, not semantic task failures. Model-supplied capability
    dictionaries are rejected rather than silently treated as host authority.
    """
    require(type(task) is CallableTask and type(recipe) is InputStateProbeRecipe,
            "Typed callable task and recipe required")
    require(capability is None or type(capability) is HostInputCapability,
            "A capability must be registered by the host, not a proposal dictionary")

    def result(status, reason, output=task, *, source_case=None, generated_case=None):
        return output, seal({
            "version": VERSION, "status": status, "reason": reason,
            "task_hash": task.contract.content_hash, "base_callable_task_hash": task.content_hash,
            "result_callable_task_hash": output.content_hash,
            "recipe": recipe.to_dict(), "recipe_hash": recipe.content_hash,
            "implementation_hash": implementation_hash(),
            "host_capability_hash": capability.content_hash if capability is not None else None,
            "source_case_hash": source_case.content_hash if source_case is not None else None,
            "generated_case": generated_case.to_dict() if generated_case is not None else None,
            "evidence_origin": "host_registered_public_contract_input_transformation",
            "execution_performed": False, "confirmed_failure": False,
            "limitations": ["Input generation is not execution evidence.",
                            "No expected return or exception is inferred.",
                            "A host capability is an annotation, not a proof of quote entailment."],
        })

    if recipe.choice == "none":
        return result("not_applicable", "recipe_disabled")
    preservation = tuple(sorted(o.id for o in task.contract.obligations if o.kind == "input_preservation"))
    if not preservation:
        return result("not_applicable", "no_explicit_input_preservation_obligation")
    if capability is None:
        return result("unsupported", "missing_host_input_capability")
    if capability.task_hash != task.contract.content_hash:
        return result("unsupported", "host_capability_task_mismatch")
    if capability.contract_quote not in task.contract.prompt:
        return result("unsupported", "arbitrary_order_permission_not_public")
    if any(case.id.startswith("reverse-list-") for case in task.public_cases):
        # The reserved identifier namespace makes replay idempotent even when
        # multiple base examples could produce different admissible probes.
        return result("not_applicable", "recipe_already_instantiated")
    if len(task.public_cases) >= 16:
        return result("unsupported", "public_case_budget_exhausted")

    existing_inputs = {digest(json_value(case.arguments_json)) for case in task.public_cases}
    existing_ids = {case.id for case in task.public_cases}
    for case in sorted(task.public_cases, key=lambda item: item.id):
        # An explicitly exceptional example is not a registered ordinary input.
        if case.expected_exception is not None:
            continue
        arguments = json_value(case.arguments_json)
        index = capability.positional_arg_index
        if index >= len(arguments["args"]) or type(arguments["args"][index]) is not list:
            continue
        original = arguments["args"][index]
        if not original:
            continue
        arguments["args"][index] = list(reversed(original))
        if digest(arguments) in existing_inputs:
            continue
        generated_id = "reverse-list-" + digest({"source_case": case.content_hash,
                                               "arguments": arguments, "recipe": recipe.content_hash})[:32]
        if generated_id in existing_ids:
            return result("unsupported", "generated_case_identifier_collision")
        generated = PublicCase(
            id=generated_id,
            arguments_json=json.dumps(arguments, sort_keys=True, separators=(",", ":"), allow_nan=False),
            contract_quote=capability.contract_quote,
            obligation_ids=preservation,
            expected_json=None,
            expected_exception=None,
        )
        output = replace(task, public_cases=task.public_cases + (generated,))
        return result("proposed_only", "one_contract_supported_preservation_probe", output,
                      source_case=case, generated_case=generated)
    return result("not_applicable", "no_new_supported_list_ordering")
