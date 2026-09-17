import copy

import pytest

from skillopt.coevolution_v5 import core
from skillopt.validator_pilot.api import digest


def assessment(**overrides):
    values = dict(check_id="coding_contract", task_id="dev", domain="coding", phase="development",
                  artifact_hash=digest({"x.py": "x=1"}), rubric_hash=core.initial_rubric()["rubric_hash"],
                  status="fail", evidence_kind="execution", verified=True, gate_eligible=True,
                  details={"input": {"x": 1}, "expected": 2, "actual": 1})
    return core.make_assessment(**{**values, **overrides})


def packet(rows=None, **overrides):
    return core.feedback_packet(**{**dict(task_id="dev", cluster_id="project", domain="coding",
                                         assessments=rows or [assessment()], artifact={"x.py": "x=1"},
                                         contract="preserve requested values"), **overrides})


def test_rubric_changes_do_not_modify_foundation_or_previous_version():
    before = core.initial_rubric()
    patch = {"changes": [{"check_id": "coding_probe", "when": "shared dependencies",
                           "search": "Test a diamond and a non-shared control", "limits": "Only legal inputs"}],
             "rationale": "observed gap", "source_refs": []}
    updated = core.apply_rubric_patch(before, patch)
    assert updated["revision"] == 1
    assert updated["parent_hash"] == before["rubric_hash"]
    assert before == core.initial_rubric()
    assert updated["checks"][1]["criterion"] == before["checks"][1]["criterion"]


@pytest.mark.parametrize("field,value", [("domains", ["qa"]), ("obligation", "always pass"),
                                        ("criterion", "model says pass"), ("evidence", "citation_match")])
def test_even_resealed_rubric_cannot_change_authority(field, value):
    changed = core.initial_rubric()
    changed.pop("rubric_hash")
    changed["checks"][0][field] = value
    with pytest.raises(ValueError):
        core.validate_rubric(core.seal(changed, "rubric_hash"))


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":NaN}', '```json\n{"x":1}', '{"x":1', '[]'])
def test_unclosed_or_ambiguous_json_not_repaired(raw):
    with pytest.raises(ValueError):
        core.strict_object(raw)


def test_valid_fence_accepted():
    assert core.strict_object('```json\n{"x":1}\n```') == {"x": 1}


@pytest.mark.parametrize("changes", [{"verified": False}, {"status": "unknown"},
                                    {"status": "not_applicable"}, {"evidence_kind": "citation_match"}])
def test_soft_or_missing_evidence_cannot_authorize_gate(changes):
    with pytest.raises(ValueError):
        assessment(**changes)


def test_citation_provenance_may_be_verified_but_not_gate_eligible():
    row = assessment(evidence_kind="citation_match", gate_eligible=False)
    assert row["verified"] and not row["gate_eligible"]


def test_feedback_separates_facts_and_repair_hypotheses():
    result = packet(hypotheses=["Possible cache bug"])
    assert len(result["facts"]) == 1
    assert result["hypotheses"][0]["status"] == "unverified_hypothesis"
    assert result["repair_guidance"][0]["status"] == "repair_hypothesis_requires_reexecution"
    system, user = core.optimizer_messages("", None, [result])
    assert "DEVELOPMENT" in system and "Possible cache bug" in user


@pytest.mark.parametrize("phase", ["promotion", "audit", "final"])
def test_non_development_receipts_cannot_enter_feedback(phase):
    with pytest.raises(ValueError):
        packet(rows=[assessment(phase=phase)])


def test_nested_final_relabel_and_tampering_rejected():
    with pytest.raises(ValueError):
        packet(comparisons=[{"phase": "final"}])
    value = packet()
    changed = copy.deepcopy(value)
    changed["contract"] = "new"
    with pytest.raises(ValueError):
        core.optimizer_messages("", None, [changed])


def test_unknown_is_not_a_bug_claim():
    value = packet(rows=[assessment(status="unknown", gate_eligible=False, verified=False)])
    assert not value["facts"]
    assert value["repair_guidance"][0]["status"] == "investigation_not_bug_claim"


def test_artifact_substitution_and_mixed_rubrics_rejected():
    with pytest.raises(ValueError):
        packet(artifact={"x.py": "x=2"})
    with pytest.raises(ValueError):
        packet(rows=[assessment(), assessment(rubric_hash=digest("other"))])
