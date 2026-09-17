"""Typed local patch contracts cannot turn an unknown or spec into a failure."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v14 import learning as l


def operation(**changes):
    return {"op": "upsert", "id": "check-units", "mechanism": "unit", "when": "On unit conversions.",
            "procedure": "Track the unit of each intermediate quantity.", "avoid": "Do not convert twice.",
            "claim_type": "observed_failure", "evidence_refs": ["a" * 64], **changes}


def parse(operations, parent=None, supports=None, **receipt):
    return l.parse_update({"ok": True, "response": json.dumps({"operations": operations}), **receipt},
        parent or l.empty_state(), "constrained", supports or {"a"*64: {"claim_type": "observed_failure"}})


def test_initial_patch_and_local_preservation():
    first = parse([operation(), operation(id="dependency")])
    assert first["valid"] and len(first["state"]["rules"]) == 2
    parent = deepcopy(first["state"])
    second = parse([operation(procedure="Check input and intermediate units separately.")], parent)
    assert second["valid"]
    assert second["state"]["rules"][1] == parent["rules"][1]
    assert parent == first["state"]
    assert second["skill"] == l.render(second["state"]["rules"])


@pytest.mark.parametrize("change", [
    {"claim_type": "regression"}, {"claim_type": "task_requirement"}, {"evidence_refs": ["b"*64]},
    {"evidence_refs": []}, {"evidence_refs": ["a"*64, "a"*64]}, {"evidence_refs": [None]},
    {"mechanism": "global-rule"}, {"mechanism": []}, {"when": ""}, {"procedure": "x"*601},
    {"id": "../escape"}, {"op": "replace-all"}, {"extra": True}, {"claim_type": []},
])
def test_invalid_patch_retains_parent(change):
    value = parse([operation(**change)])
    assert not value["valid"] and value["state"] == l.empty_state()


def test_extra_operations_and_duplicate_ids_rejected():
    assert not parse([operation(id="a"), operation(id="b"), operation(id="c")])["valid"]
    assert not parse([operation(), operation()])["valid"]


def test_empty_operations_and_remove():
    parent = parse([operation()])["state"]
    assert parse([], parent)["state"] == parent
    removed = parse([{k: v for k, v in operation(op="remove").items()
                      if k in {"op", "id", "claim_type", "evidence_refs"}}], parent)
    assert removed["valid"] and removed["state"] == l.empty_state()


@pytest.mark.parametrize("raw", ['{"operations":[],"operations":[]}', '{"operations":NaN}', "```json\n{}\n```", "[]"])
def test_strict_json(raw):
    assert not parse([], response=raw)["valid"]


def test_api_failure_no_retry_or_parent_loss():
    parent = parse([operation()])["state"]
    result = parse([], parent, ok=False)
    assert not result["valid"] and result["state"] == parent and result["reason"] == "api_unknown"


def test_whole_rewrite_control_contract():
    text = "## When\nConditional.\n## Procedure\nVerify.\n## Avoid\nUnsupported changes."
    value = l.parse_update({"ok": True, "response": text}, l.empty_state(), "independent", {})
    assert value["valid"] and value["skill"] == text and value["state"]["rules"] == []
    assert not l.parse_update({"ok": True, "response": "nonsense"}, value["state"], "independent", {})["valid"]


def feedback(available=False, passed=False, phase="development"):
    return seal({"phase": phase, "task_id": "dev", "stages": [],
        "provenance": {"skill_hash": l.text_hash("")}, "final_execution": {
            "score": {"oracle_available": available},
            "observations": [{"observation": {"id": "executed", "passed": passed}}]}})


def test_unknown_execution_does_not_create_semantic_support():
    rows = [{"role": "current", "feedback": feedback()}]
    assert l.support_registry([], rows, []) == {}
    rows[0]["feedback"] = feedback(available=True)
    assert {r["claim_type"] for r in l.support_registry([], rows, []).values()} == {"observed_failure"}


def test_specification_support_is_not_executed_failure():
    supports = l.support_registry([{"id": "dev", "obligations": [{"id": "o1", "statement": "Use units."}]}], [], [])
    assert {r["claim_type"] for r in supports.values()} == {"task_requirement"}
    assert not parse([operation(evidence_refs=list(supports))], supports=supports)["valid"]


def test_final_feedback_refused_before_model_prompt():
    rows = [{"role": role, "feedback": feedback(phase="final")} for role in ("no_skill", "current")]
    with pytest.raises(ValueError, match="Final or selection"):
        l.messages(l.empty_state(), [{"id": "dev", "obligations": []}], rows, [], "independent")


def test_control_has_no_extra_probe_context():
    with pytest.raises(ValueError, match="extra probe"):
        l.messages(l.empty_state(), [], [], [{"probe": True}], "independent")


def test_wrong_current_skill_or_missing_pair_refused():
    rows = [{"role": role, "feedback": feedback()} for role in ("no_skill", "current")]
    with pytest.raises(ValueError, match="Skill hash"):
        l.messages({"skill": "different", "rules": []}, [{"id": "dev", "obligations": []}], rows, [], "independent")
    with pytest.raises(ValueError, match="complete paired"):
        l.messages(l.empty_state(), [{"id": "dev", "obligations": []}], rows[:1], [], "independent")
