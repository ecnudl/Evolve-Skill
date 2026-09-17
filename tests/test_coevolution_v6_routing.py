from copy import deepcopy

import pytest

from skillopt.coevolution_v6.native import final_native_tasks
from skillopt.coevolution_v6.routing import route, validate_contract
from skillopt.validator_pilot.api import digest


def contract():
    return {"change_scope": "partial_update", "preserve_obligations": ["Preserve explicitly unchanged behavior"],
            "supersedes_old_policy": False}


def test_partial_preservation_applies_and_receipt_is_sealed():
    result = route(contract(), "Bounded constraint-preservation Skill")
    assert result["apply"] is True
    assert result["learned_router"] is False
    assert result["record_hash"] == digest({k: v for k, v in result.items() if k != "record_hash"})


def test_native_panel_routes_only_mechanism_compatible_contracts():
    tasks = final_native_tasks()
    for adapter in tasks:
        result = route(adapter.task["contract"], "Preserve explicit invariants while modifying a local mechanism")
        assert result["apply"] is (adapter.task["metadata"]["group"] == "same_mechanism")
    assert sum(route(a.task["contract"], "Skill")["apply"] for a in tasks) == 6


@pytest.mark.parametrize("scope,supersedes", [("partial_update", True), ("full_replacement", False), ("read_only", True),
                                             ("new_implementation", True)])
def test_contradictory_contract_falls_back(scope, supersedes):
    value = contract()
    value.update(change_scope=scope, supersedes_old_policy=supersedes)
    result = route(value, "Skill")
    assert result["apply"] is False
    assert result["reason"] == "contradictory_contract"


@pytest.mark.parametrize("mutation", [{"change_scope": "unknown"}, {"supersedes_old_policy": "false"},
                                     {"preserve_obligations": "Preserve everything"},
                                     {"preserve_obligations": ["same", "same"]}, {"preserve_obligations": [False]}])
def test_unknown_or_illtyped_contract_falls_back(mutation):
    value = {**contract(), **mutation}
    with pytest.raises((ValueError, TypeError)):
        validate_contract(value)
    assert route(value, "Skill")["apply"] is False


@pytest.mark.parametrize("field", ["domain", "task_id", "gold", "group", "score"])
def test_noncontract_labels_cannot_enter_router(field):
    value = {**contract(), field: "positive-looking label"}
    assert route(value, "Skill")["reason"] == "invalid_or_unknown_contract"


def test_external_metadata_cannot_change_same_contract_decision():
    base = final_native_tasks()[0].task
    changed = deepcopy(base)
    changed.update(domain="another_domain", id="other_task", metadata={"group": "near_miss", "gold": "different"})
    assert route(base["contract"], "Skill") == route(changed["contract"], "Skill")


def test_no_preservation_or_empty_skill_falls_back():
    value = contract()
    value["preserve_obligations"] = []
    assert route(value, "Skill")["reason"] == "no_explicit_preservation_evidence"
    assert route(contract(), " ")["reason"] == "empty_or_invalid_skill"


def test_standalone_implementation_not_mislabelled_readonly_or_local_update():
    value = contract()
    value["change_scope"] = "new_implementation"
    assert validate_contract(value)["change_scope"] == "new_implementation"
    decision = route(value, "Preserve unchanged legacy behavior")
    assert decision["apply"] is False
    assert decision["reason"] == "standalone_new_implementation"


def test_route_does_not_modify_contract():
    value = contract()
    frozen = deepcopy(value)
    route(value, "Skill")
    assert value == frozen
