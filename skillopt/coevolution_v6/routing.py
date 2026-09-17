"""A fixed contract-only routing control, not a learned generalization claim."""

from __future__ import annotations

from copy import deepcopy

from skillopt.validator_pilot.api import digest

FIELDS = {"change_scope", "preserve_obligations", "supersedes_old_policy"}


def validate_contract(contract):
    if not isinstance(contract, dict) or set(contract) != FIELDS:
        raise ValueError("Contract must contain exactly the three declared fields")
    if contract["change_scope"] not in {"partial_update", "full_replacement", "read_only", "new_implementation"}:
        raise ValueError("Unknown change scope")
    if type(contract["supersedes_old_policy"]) is not bool:
        raise ValueError("Supersession must be an explicit boolean")
    obligations = contract["preserve_obligations"]
    if (not isinstance(obligations, list) or len(obligations) > 12
            or any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in obligations)
            or len(set(obligations)) != len(obligations)):
        raise ValueError("Preservation obligations must be distinct bounded strings")
    return deepcopy(contract)


def route(contract, skill):
    """Only a local-update contract with explicit preservation can apply Skill.

    The caller must supply ONLY the task's declared contract, not domain, group,
    gold answers or outcome metadata. Unknown/extra fields fail closed. This is
    an explicit-rule ablation and must not be advertised as a learned router.
    """
    result = {"apply": False, "reason": None, "skill_hash": digest(skill) if isinstance(skill, str) else None,
              "contract_hash": None, "routing_inputs": sorted(FIELDS), "learned_router": False}
    try:
        checked = validate_contract(contract)
    except (ValueError, TypeError):
        result["reason"] = "invalid_or_unknown_contract"
    else:
        result["contract_hash"] = digest(checked)
        scope = checked["change_scope"]
        obsolete = checked["supersedes_old_policy"]
        if not isinstance(skill, str) or not skill.strip():
            result["reason"] = "empty_or_invalid_skill"
        elif scope in {"partial_update", "read_only", "new_implementation"} and obsolete:
            result["reason"] = "contradictory_contract"
        elif scope == "full_replacement" and not obsolete:
            result["reason"] = "contradictory_contract"
        elif scope == "new_implementation":
            result["reason"] = "standalone_new_implementation"
        elif scope != "partial_update":
            result["reason"] = "policy_replacement" if scope == "full_replacement" else "no_edit_requested"
        elif not checked["preserve_obligations"]:
            result["reason"] = "no_explicit_preservation_evidence"
        else:
            result.update(apply=True, reason="local_change_with_explicit_preservation")
    result["record_hash"] = digest(result)
    return result
