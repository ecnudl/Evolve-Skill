"""Self-contained evidence attribution tests; no models, network, or frozen run writes."""

import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_evidence_view import research_evidence_view


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def seal(value, field="record_hash"):
    value = deepcopy(value)
    value.pop(field, None)
    return {**value, field: digest(value)}


STARTER = {"logic.py": "def touches(left, right):\n    return left < right\n"}
BASE = {"logic.py": "def touches(left, right):\n    return left <= right  # base execution\n"}
CANDIDATE = {"logic.py": "def touches(left, right):\n    return left <= right\n"}


def assessment(artifact, *, status="pass", check_id="coding_contract", **overrides):
    return seal({"check_id": check_id, "task_id": "dev-interval", "domain": "coding",
                 "phase": "development", "artifact_hash": digest(artifact), "rubric_hash": digest("rubric"),
                 "status": status, "evidence_kind": "execution", "verified": status != "unknown",
                 "gate_eligible": status in {"pass", "fail"},
                 "details": {"input": {"left": 3, "right": 3}, "expected": True,
                             "actual": True, "task_split": "learn0", "requested_phase": "development"},
                 **overrides}, "receipt_hash")


def packet(artifact=None):
    artifact = CANDIDATE if artifact is None else artifact
    rows = [assessment(artifact), assessment(artifact, status="unknown", check_id="coding_probe")]
    baseline = assessment(BASE)

    def reference(row):
        return {k: row[k] for k in ("check_id", "status", "receipt_hash", "artifact_hash")}

    return seal({"phase": "development", "task_id": "dev-interval", "cluster_id": "interval-substrate",
                 "domain": "coding", "artifact_hash": digest(artifact), "rubric_hash": digest("rubric"),
                 "artifact": deepcopy(artifact), "contract": "Closed endpoints count as touching; preserve input order.",
                 "task_context": {"id": "dev-interval", "files": deepcopy(STARTER),
                                  "public_cases": [{"input": {"left": 3, "right": 3}, "expected": True}]},
                 "observations": rows,
                 "facts": [{k: rows[0][k] for k in ("receipt_hash", "check_id", "status", "evidence_kind", "details")}],
                 "comparisons": [{"repeat": 0, "arms": {"baseline": [reference(baseline)],
                                                         "current": [reference(baseline)],
                                                         "candidate": [reference(rows[0])]},
                                  "interpretation": "paired_observation_not_causation"}],
                 "hypotheses": [{"text": "Maybe endpoint coverage is incomplete.", "status": "unverified_hypothesis"}],
                 "repair_guidance": [{"receipt_hash": rows[1]["receipt_hash"], "check_id": "coding_probe",
                                      "action": "Collect a legal probe; no demonstrated defect.",
                                      "status": "investigation_not_bug_claim"}],
                 "research_context": {"audit": {"preselected": True, "selection": "pre_execution_random"}},
                 "no_causal_claim_from_single_pair": True})


def registry(artifact=BASE, *, include_assessments=False):
    value = {"phase": "development", "task_id": "dev-interval", "artifact_hash": digest(artifact),
             "artifact": deepcopy(artifact), "request_hashes": [digest("actual solver request")],
             "skill_hash": digest("")}
    if include_assessments:
        value["assessments"] = [assessment(artifact)]
    return {digest(artifact): seal(value)}


def test_starter_is_not_baseline_and_missing_solver_artifact_stays_missing():
    source = packet()
    view = research_evidence_view(source)
    assert view["initial_task_fixture"]["artifact"] == STARTER
    assert view["initial_task_fixture"]["role"] == "original_task_fixture_NOT_execution"
    assert view["evaluated_artifact"]["artifact"] == CANDIDATE
    assert "files" not in view["public_task"]["context_without_initial_fixture"]
    assert view["public_task"]["context_without_initial_fixture"]["public_cases"][0]["expected"] is True
    pair = view["paired_observations"][0]
    assert pair["arms"] == source["comparisons"][0]["arms"]
    for arm in ("baseline", "current"):
        check = pair["reference_checks"][arm][0]
        assert check["artifact_content_available"] is False
        assert check["artifact_content_source"] == "unavailable_not_inferred_from_initial_fixture"
        assert check["receipt_integrity"] == "unavailable_reference_only"
    assert pair["reference_checks"]["candidate"][0]["receipt_integrity"] == "packet_observation"


def test_actual_base_registry_reveals_leq_not_starter_lt_without_authenticating_execution():
    records = registry(include_assessments=True)
    view = research_evidence_view(packet(), artifact_registry=records)
    assert "<= right" in view["supplied_solver_artifact_registry"][digest(BASE)]["artifact"]["logic.py"]
    assert "< right" in view["initial_task_fixture"]["artifact"]["logic.py"]
    check = view["paired_observations"][0]["reference_checks"]["baseline"][0]
    assert check["artifact_content_available"] is True
    assert check["receipt_integrity"] == "supplied_registry_assessment"
    assert check["execution_authenticated"] is False


def test_registry_bytes_alone_do_not_verify_arm_receipt():
    view = research_evidence_view(packet(), artifact_registry=registry())
    check = view["paired_observations"][0]["reference_checks"]["baseline"][0]
    assert check["artifact_content_available"] is True
    assert check["receipt_integrity"] == "unavailable_reference_only"


def test_shared_content_hash_resolves_bytes_not_independent_execution():
    source = packet(BASE)
    view = research_evidence_view(source)
    check = view["paired_observations"][0]["reference_checks"]["baseline"][0]
    assert check["artifact_content_source"] == "evaluated_artifact_identical_content_hash"
    assert check["artifact_content_available"] and not check["execution_authenticated"]
    assert any("not independent runs" in line for line in view["guardrails"])


def test_verified_statuses_and_receipts_preserved_and_claims_separated():
    source = packet()
    view = research_evidence_view(source)
    assert view["observations"] == source["observations"]
    assert [r["status"] for r in view["observations"]] == ["pass", "unknown"]
    assert view["verified_observation_facts"] == source["facts"]
    assert view["unsupported_hypotheses"] == source["hypotheses"]
    assert view["repair_advice_requires_reexecution"] == source["repair_guidance"]
    assert all(r["details"]["expected"] is True for r in view["observations"])
    assert any("Pass and unknown" in line for line in view["guardrails"])
    assert any("not entailment" in line for line in view["guardrails"])
    assert view["source_packet_hash"] == source["record_hash"]
    assert view["record_hash"] == digest({k: v for k, v in view.items() if k != "record_hash"})


def test_verified_failure_is_retained_but_repair_stays_hypothesis():
    source = packet()
    row = assessment(CANDIDATE, status="fail", details={"actual": False, "expected": True})
    source["observations"] = [row]
    source["facts"] = [{k: row[k] for k in ("receipt_hash", "check_id", "status", "evidence_kind", "details")}]
    source["comparisons"] = []
    source["repair_guidance"] = [{"receipt_hash": row["receipt_hash"], "check_id": row["check_id"],
                                 "action": "Repair this mismatch.", "status": "repair_hypothesis_requires_reexecution"}]
    view = research_evidence_view(seal(source))
    assert view["verified_observation_facts"][0]["status"] == "fail"
    assert view["repair_advice_requires_reexecution"][0]["status"] == "repair_hypothesis_requires_reexecution"


def test_absent_artifact_delivery_unknown_is_not_hidden_or_repaired():
    source = packet()
    row = assessment(None, status="unknown", details={"reason": "delivery", "expected": "strict FILE sections"})
    source.update(artifact=None, artifact_hash=digest(None), observations=[row], facts=[], comparisons=[], repair_guidance=[])
    view = research_evidence_view(seal(source))
    assert not view["evaluated_artifact"]["available"]
    assert view["evaluated_artifact"]["artifact"] is None
    assert view["observations"][0]["status"] == "unknown"


@pytest.mark.parametrize("field,value", [("contract", "changed"), ("artifact", STARTER), ("record_hash", "0" * 64)])
def test_packet_tampering_rejected(field, value):
    source = packet()
    source[field] = value
    with pytest.raises(ValueError, match="checksum"):
        research_evidence_view(source)


def test_resealed_packet_cannot_substitute_evaluated_artifact():
    source = packet()
    source["artifact"] = STARTER
    with pytest.raises(ValueError, match="artifact hash"):
        research_evidence_view(seal(source))


@pytest.mark.parametrize("field,value", [("task_id", "other"), ("domain", "qa"), ("phase", "promotion"),
                                         ("rubric_hash", digest("other")), ("artifact_hash", digest(STARTER))])
def test_resealed_observation_identity_mismatch_rejected(field, value):
    source = packet()
    source["observations"][0][field] = value
    source["observations"][0] = seal(source["observations"][0], "receipt_hash")
    with pytest.raises(ValueError):
        research_evidence_view(seal(source))


def test_outer_reseal_does_not_hide_receipt_tampering():
    source = packet()
    source["observations"][0]["status"] = "fail"
    with pytest.raises(ValueError, match="checksum"):
        research_evidence_view(seal(source))


@pytest.mark.parametrize("phase", ["final", "promotion", "calibration", "audit", "holdout", "test", "evaluation", "shadow"])
@pytest.mark.parametrize("key", ["phase", "task_split", "requested_phase", "dataset_split", "partition"])
def test_nested_non_development_markers_rejected_even_if_outer_resealed(phase, key):
    source = packet()
    source["research_context"]["nested"] = [{key: "private_" + phase}]
    with pytest.raises(ValueError, match="Non-development"):
        research_evidence_view(seal(source))


def test_qa_rejected_even_if_all_hashes_and_phases_are_valid():
    source = packet()
    source["domain"] = "qa"
    with pytest.raises(ValueError, match="Only Coding"):
        research_evidence_view(seal(source))


@pytest.mark.parametrize("phase", ["heldout", "held-out", "held_out", "validation", "eval", "confirmation"])
def test_additional_heldout_phase_aliases_rejected(phase):
    source = packet()
    source["task_context"]["nested"] = {"source_phase": phase}
    with pytest.raises(ValueError, match="Non-development"):
        research_evidence_view(seal(source))


@pytest.mark.parametrize("field", ["final_results", "calibration_label", "reference_implementation",
                                   "truth", "oracle_label", "promotion_result", "audit_result",
                                   "calibration", "promotion", "final", "holdout", "test_results", "audit"])
def test_explicit_heldout_objects_rejected_without_phase_marker(field):
    source = packet()
    source["task_context"]["nested"] = [{field: {"score": 1}}]
    with pytest.raises(ValueError, match="Non-development"):
        research_evidence_view(seal(source))


def test_development_expected_values_and_preselected_audit_flag_are_kept():
    source = packet()
    source["task_context"]["public_cases"].append({"input": {"text": "final_results"}, "expected": "held-out"})
    view = research_evidence_view(seal(source))
    assert view["research_context"]["audit"] == {"preselected": True, "selection": "pre_execution_random"}
    assert view["public_task"]["context_without_initial_fixture"]["public_cases"] == source["task_context"]["public_cases"]
    assert view["observations"][0]["details"]["expected"] is True


def test_excessive_nested_payload_rejected():
    source = packet()
    nested = {}
    source["research_context"]["nested"] = nested
    for _ in range(25):
        nested["next"] = {}
        nested = nested["next"]
    with pytest.raises(ValueError, match="nesting"):
        research_evidence_view(seal(source))


@pytest.mark.parametrize("field,value", [("status", "fail"), ("check_id", "other"),
                                         ("artifact_hash", digest(STARTER))])
def test_comparison_reference_cannot_disagree_with_known_receipt(field, value):
    source = packet()
    source["comparisons"][0]["arms"]["candidate"][0][field] = value
    with pytest.raises(ValueError):
        research_evidence_view(seal(source))


def test_registry_assessment_checks_baseline_status_reference():
    source = packet()
    source["comparisons"][0]["arms"]["baseline"][0]["status"] = "fail"
    with pytest.raises(ValueError, match="disagrees"):
        research_evidence_view(seal(source), artifact_registry=registry(include_assessments=True))


@pytest.mark.parametrize("field,value", [("artifact", STARTER), ("task_id", "wrong-task"),
                                         ("phase", "final"), ("artifact_hash", digest(STARTER)),
                                         ("request_hashes", []), ("request_hashes", ["not-a-hash"])])
def test_resealed_registry_mismatches_rejected(field, value):
    records = registry()
    records[digest(BASE)][field] = value
    records[digest(BASE)] = seal(records[digest(BASE)])
    with pytest.raises(ValueError):
        research_evidence_view(packet(), artifact_registry=records)


def test_registry_tampering_rejected():
    records = registry()
    records[digest(BASE)]["artifact"] = STARTER
    with pytest.raises(ValueError, match="checksum"):
        research_evidence_view(packet(), artifact_registry=records)


@pytest.mark.parametrize("field,value", [("solver_request_hashes", [digest("a different actual request")]),
                                        ("solver_skill_hash", digest("a different skill"))])
def test_registry_receipt_solver_provenance_cannot_disagree_even_when_resealed(field, value):
    records = registry(include_assessments=True)
    record = records[digest(BASE)]
    record["assessments"][0]["details"][field] = value
    record["assessments"][0] = seal(record["assessments"][0], "receipt_hash")
    records[digest(BASE)] = seal(record)
    with pytest.raises(ValueError, match="solver provenance disagrees"):
        research_evidence_view(packet(), artifact_registry=records)


def test_registry_matching_solver_provenance_is_preserved():
    records = registry(include_assessments=True)
    record = records[digest(BASE)]
    record["assessments"][0]["details"].update(solver_request_hashes=record["request_hashes"],
                                              solver_skill_hash=record["skill_hash"])
    record["assessments"][0] = seal(record["assessments"][0], "receipt_hash")
    records[digest(BASE)] = seal(record)
    view = research_evidence_view(packet(), artifact_registry=records)
    assert view["supplied_solver_artifact_registry"] == records


def test_fact_or_hypothesis_promotion_rejected():
    source = packet()
    source["facts"][0]["status"] = "fail"
    with pytest.raises(ValueError, match="Fact summary"):
        research_evidence_view(seal(source))
    source = packet()
    source["hypotheses"][0]["status"] = "verified_fact"
    with pytest.raises(ValueError, match="explicitly unverified"):
        research_evidence_view(seal(source))
    source = packet()
    source["repair_guidance"][0]["status"] = "repair_hypothesis_requires_reexecution"
    with pytest.raises(ValueError, match="unsupported defect"):
        research_evidence_view(seal(source))


def test_complete_content_and_no_mutation_or_silent_truncation():
    source, records = packet(), registry(include_assessments=True)
    before_source, before_records = deepcopy(source), deepcopy(records)
    view = research_evidence_view(source, artifact_registry=records, max_chars=20000)
    assert source == before_source and records == before_records
    assert view["supplied_solver_artifact_registry"] == records
    assert view["research_context"] == source["research_context"]
    assert len(json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":"))) <= 20000
    assert view["context_budget"]["truncation"] is False
    view["evaluated_artifact"]["artifact"]["logic.py"] = "changed"
    assert source == before_source
    with pytest.raises(ValueError, match="character budget"):
        research_evidence_view(source, artifact_registry=records, max_chars=100)


def test_budget_includes_added_guardrails_registry_and_seal_not_just_input():
    source = packet()
    input_size = len(json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(",", ":"))) + 2
    with pytest.raises(ValueError, match="nothing was truncated"):
        research_evidence_view(source, max_chars=input_size + 100)


@pytest.mark.parametrize("limit", [False, 0, -1, 1.1, 1000001])
def test_invalid_budget_rejected(limit):
    with pytest.raises(ValueError, match="budget"):
        research_evidence_view(packet(), max_chars=limit)


def test_nonfinite_and_unexpected_extra_fields_rejected():
    source = packet()
    source["research_context"]["value"] = float("nan")
    with pytest.raises(ValueError, match="finite JSON"):
        research_evidence_view(source)
    source = packet()
    source["unreviewed_side_channel"] = "extra context"
    with pytest.raises(ValueError, match="complete V5"):
        research_evidence_view(seal(source))
