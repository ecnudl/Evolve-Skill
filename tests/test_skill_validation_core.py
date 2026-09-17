"""Synthetic Stage-1 tests: isolation and replay, never scientific effect data."""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation.engine import execution_policy, fixed_rubric, metrics, validate
from skillopt.skill_validation.models import (
    ArtifactRecord,
    CheckResult,
    EvidenceRecord,
    GateDecision,
    Obligation,
    Observation,
    SourceFile,
    TaskContract,
    ValidationReport,
    unseal_record,
)
from skillopt.skill_validation.views import (
    DevelopmentGap,
    bind,
    research_development_view,
    skill_feedback_view,
    verifier_view,
)
from skillopt.validator_pilot.api import digest


def sample():
    """Public fixture receipts are declared, not executed or model generated."""
    prompt = ("Return the sum of the input list. Do not modify the input list. "
              "Keep config.ini byte-identical.")
    task = TaskContract(
        "fixture:task", "fixture:original", "fixture:family", "fixture:project",
        "development", "coding", "constraint_preservation", prompt,
        (
            Obligation("sum", "requested_behavior", "Return the sum.", "Return the sum of the input list."),
            Obligation("unchanged", "input_preservation", "Input remains unchanged.", "Do not modify the input list."),
            Obligation("config", "file_preservation", "Preserve the configuration.",
                       "Keep config.ini byte-identical.", "config.ini"),
        ),
        (SourceFile("config.ini", "mode=safe\n"),),
    )
    artifact = ArtifactRecord(
        task.content_hash, 0, "candidate", "fixture-skill-v1", digest("fixture-skill"),
        (SourceFile("solution.py", "def solve(values):\n    return sum(values)\n"),
         SourceFile("config.ini", "mode=safe\n")),
        "available", "fixture", True, False, "fixture:artifact", digest("fixture:artifact"),
    )
    evidence = EvidenceRecord(
        task_hash=task.content_hash, artifact_hash=artifact.artifact_hash,
        artifact_record_hash=artifact.content_hash, repeat=0, visibility="public", execution_status="observed",
        observations=(Observation("public-sum", "sum", "public_test", passed=True),
                      Observation("state", "unchanged", "input_state", before_hash=digest([1, 2]), after_hash=digest([1, 2]))),
        source_ref="fixture:receipt", source_hash=digest("fixture:receipt"), provenance_kind="fixture",
    )
    return task, artifact, (evidence,)


def rebind(task, artifact, evidence):
    artifact = replace(artifact, task_hash=task.content_hash)
    evidence = tuple(replace(row, task_hash=task.content_hash, artifact_hash=artifact.artifact_hash,
                             artifact_record_hash=artifact.content_hash, repeat=artifact.repeat,
                             provenance_kind=artifact.provenance_kind)
                     for row in evidence)
    return task, artifact, evidence


def result_for(report, obligation):
    return dict(report.obligation_results)[obligation]


def test_typed_json_round_trip_and_sealed_identity():
    task, artifact, evidence = sample()
    rubric = fixed_rubric()
    report = validate(task, artifact, evidence, rubric)
    gate = GateDecision("verifier", "pending", rubric.pipeline_hash)
    records = [task, artifact, evidence[0], task.obligations[0], task.public_files[0],
               evidence[0].observations[0], rubric.checks[0], rubric,
               report.instances[0], report.checks[0], report, gate]
    for record in records:
        serialized = json.loads(json.dumps(record.sealed()))
        restored = unseal_record(serialized, type(record))
        assert type(restored) is type(record)
        assert restored == record
        assert restored.content_hash == record.content_hash
    with pytest.raises(FrozenInstanceError):
        task.task_id = "cannot-mutate"


@pytest.mark.parametrize("path", ["task", "obligation", "public_file", "artifact_file", "observation"])
def test_unknown_nested_hidden_fields_are_rejected(path):
    task, artifact, evidence = sample()
    if path in {"task", "obligation", "public_file"}:
        value, cls = task.to_dict(), TaskContract
        target = value if path == "task" else value["obligations"][0] if path == "obligation" else value["public_files"][0]
    elif path == "artifact_file":
        value, cls = artifact.to_dict(), ArtifactRecord
        target = value["files"][0]
    else:
        value, cls = evidence[0].to_dict(), EvidenceRecord
        target = value["observations"][0]
    target["hidden_reference_answer"] = {"sentinel": "HIDDEN-DO-NOT-EXPOSE"}
    with pytest.raises(ValueError, match="Unexpected or missing"):
        cls.from_dict(value)


@pytest.mark.parametrize("field", ["prompt", "domain", "mechanism"])
def test_nested_dict_cannot_masquerade_as_text(field):
    task, _, _ = sample()
    raw = task.to_dict()
    raw[field] = {"public": "fine", "hidden_test": "HIDDEN"}
    with pytest.raises(ValueError, match="bounded UTF-8 text"):
        TaskContract.from_dict(raw)


def test_projection_independent_of_host_ids_conditions_skill_and_partition():
    task, artifact, evidence = sample()
    original = verifier_view(task, artifact, evidence)
    renamed = {o.id: f"HIDDEN-obligation-{i}" for i, o in enumerate(task.obligations)}
    changed_task = replace(
        task, task_id="HIDDEN-task", original_task_id="HIDDEN-original", family_id="HIDDEN-family",
        project_id="HIDDEN-project", partition="final", mechanism="HIDDEN-near-miss-label",
        obligations=tuple(replace(o, id=renamed[o.id]) for o in task.obligations),
    )
    changed_artifact = replace(
        artifact, condition="current", skill_version="HIDDEN-skill", skill_hash=digest("HIDDEN-skill"),
        repeat=99, source_ref="HIDDEN-private-path", source_hash=digest("HIDDEN-source"),
    )
    changed_evidence = tuple(replace(
        row, source_ref="HIDDEN-receipt", source_hash=digest("HIDDEN-receipt"),
        observations=tuple(replace(o, id=f"HIDDEN-{i}", obligation_id=renamed[o.obligation_id])
                           for i, o in enumerate(row.observations)),
    ) for row in evidence)
    rebound = rebind(changed_task, changed_artifact, changed_evidence)
    assert verifier_view(*rebound) == original
    assert "HIDDEN" not in json.dumps(verifier_view(*rebound))
    assert "condition" not in original["artifact"]


def test_projection_remains_detached_and_semantic_ids_are_not_presentation_ids():
    task, artifact, evidence = sample()
    view = verifier_view(task, artifact, evidence, anonymous_id="item-0123456789abcdef")
    view["task"]["obligations"][0]["statement"] = "changed locally"
    assert task.obligations[0].statement == "Return the sum."
    with pytest.raises(ValueError, match="neutral opaque"):
        verifier_view(task, artifact, evidence, anonymous_id="candidate-bad-skill")


def test_no_skill_has_empty_skill_hash_without_changing_visible_view():
    task, artifact, evidence = sample()
    with pytest.raises(ValueError, match="canonical empty Skill hash"):
        replace(artifact, condition="no_skill")
    no_skill = replace(artifact, condition="no_skill", skill_version="none",
                       skill_hash=hashlib.sha256(b"").hexdigest())
    assert verifier_view(*rebind(task, no_skill, evidence)) == verifier_view(task, artifact, evidence)


@pytest.mark.parametrize("availability", ["api_failure", "parse_failure"])
def test_delivery_failures_are_unknown_not_semantic_failure(availability):
    task, artifact, _ = sample()
    artifact = replace(artifact, files=(), availability=availability)
    report = validate(task, artifact, ())
    assert report.status == "unknown"
    assert set(dict(report.obligation_results).values()) == {"unknown"}
    assert metrics(report)["fail"] == 0
    assert all(availability in r.reason for r in report.checks if r.obligation_id)


@pytest.mark.parametrize("execution_status", ["unsupported", "execution_error", "api_failure", "parse_failure"])
def test_unavailable_execution_is_preserved_as_unknown(execution_status):
    task, artifact, evidence = sample()
    evidence = (replace(evidence[0], execution_status=execution_status, observations=()),)
    report = validate(task, artifact, evidence)
    assert result_for(report, "sum") == "unknown"
    assert result_for(report, "unchanged") == "unknown"
    assert result_for(report, "config") == "pass"  # Byte comparison does not require execution.
    assert report.status == "unknown"
    assert execution_status in report.checks[0].reason


def test_confirmed_public_test_failure_is_not_an_infrastructure_error():
    task, artifact, evidence = sample()
    observations = (replace(evidence[0].observations[0], passed=False), evidence[0].observations[1])
    report = validate(task, artifact, (replace(evidence[0], observations=observations),))
    assert result_for(report, "sum") == "fail"
    assert report.status == "fail"
    assert metrics(report)["fail"] == 1
    assert report.checks[0].evidence_refs


@pytest.mark.parametrize("change", [
    {"task_hash": digest("wrong-task")}, {"artifact_hash": digest("wrong-artifact")},
    {"artifact_record_hash": digest("wrong-run")}, {"repeat": 12}, {"provenance_kind": "model"},
])
def test_receipt_cannot_be_rebound_to_another_execution(change):
    task, artifact, evidence = sample()
    with pytest.raises(ValueError, match="mismatch"):
        validate(task, artifact, (replace(evidence[0], **change),))


def test_wrong_artifact_task_and_private_receipts_are_rejected():
    task, artifact, evidence = sample()
    with pytest.raises(ValueError, match="another task"):
        validate(task, replace(artifact, task_hash=digest("other")), ())
    with pytest.raises(ValueError, match="Hidden audit receipts"):
        replace(evidence[0], visibility="private")
    with pytest.raises(ValueError, match="cannot supply confirmed observations"):
        replace(evidence[0], execution_status="unsupported")


def test_same_bytes_and_repeat_do_not_allow_receipt_swap_between_conditions():
    task, artifact, evidence = sample()
    other_condition = replace(artifact, condition="current", skill_version="other-parent")
    assert other_condition.artifact_hash == artifact.artifact_hash
    assert other_condition.repeat == artifact.repeat
    assert other_condition.content_hash != artifact.content_hash
    with pytest.raises(ValueError, match="mismatch"):
        validate(task, other_condition, evidence)


def test_unknown_and_not_applicable_have_different_obligation_semantics():
    task, artifact, _ = sample()
    task = replace(task, obligations=(task.obligations[0],), public_files=())
    task, artifact, evidence = rebind(task, artifact, ())
    report = validate(task, artifact, evidence)
    assert report.status == "unknown"
    assert result_for(report, "sum") == "unknown"
    assert sum(row.status == "not_applicable" for row in report.checks) == 2
    assert metrics(report)["obligations"] == 1
    assert metrics(report)["coverage"] == 0.0


def test_omitting_a_rubric_check_does_not_erase_its_task_obligation():
    task, artifact, evidence = sample()
    rubric = fixed_rubric()
    restricted = replace(rubric, checks=tuple(c for c in rubric.checks if c.obligation_kind != "input_preservation"))
    report = validate(task, artifact, evidence, restricted)
    assert result_for(report, "unchanged") == "unknown"
    assert report.status == "unknown"
    assert metrics(report)["obligations"] == 3


def test_extra_checks_do_not_inflate_obligation_denominators():
    task, artifact, evidence = sample()
    rubric = fixed_rubric()
    duplicate_method = replace(rubric.checks[0], id="independent-check-id-same-evidence")
    extra = replace(rubric, version="fixture-extra-check", checks=rubric.checks + (duplicate_method,))
    old_report = validate(task, artifact, evidence, rubric)
    new_report = validate(task, artifact, evidence, extra)
    assert old_report.obligation_results == new_report.obligation_results
    for key in ("obligations", "coverage", "pass", "fail", "unknown"):
        assert metrics(old_report)[key] == metrics(new_report)[key]
    assert metrics(new_report)["check_instances"] == metrics(old_report)["check_instances"] + 1


def test_recorded_state_change_is_detected_without_executing_artifact():
    task, artifact, evidence = sample()
    artifact = replace(artifact, files=(SourceFile("solution.py", "raise RuntimeError('MUST NEVER EXECUTE')"),
                                       artifact.files[1]))
    observations = (evidence[0].observations[0], replace(evidence[0].observations[1], after_hash=digest([3])))
    evidence = (replace(evidence[0], observations=observations),)
    task, artifact, evidence = rebind(task, artifact, evidence)
    report = validate(task, artifact, evidence)
    assert result_for(report, "sum") == "pass"
    assert result_for(report, "unchanged") == "fail"
    assert metrics(report)["new_executions"] == 0


def test_in_place_near_miss_does_not_invent_input_preservation_requirement():
    task, artifact, evidence = sample()
    task = replace(task, prompt="Return the sum of the input list. Modify it in place if necessary.",
                   obligations=(task.obligations[0],), public_files=())
    evidence = (replace(evidence[0], observations=(evidence[0].observations[0],)),)
    task, artifact, evidence = rebind(task, artifact, evidence)
    report = validate(task, artifact, evidence)
    assert report.status == "pass"
    assert next(r for r in report.checks if r.check_id == "input_preservation").status == "not_applicable"
    # A state receipt cannot invent an obligation that the task does not have.
    invalid = replace(evidence[0], observations=(Observation("state", "unchanged", "input_state"),))
    with pytest.raises(ValueError, match="absent obligation"):
        validate(task, artifact, (invalid,))


def test_missing_fingerprints_are_unknown_and_cannot_be_replaced_by_claimed_pass():
    task, artifact, evidence = sample()
    state = replace(evidence[0].observations[1], after_hash=None)
    report = validate(task, artifact, (replace(evidence[0], observations=(evidence[0].observations[0], state)),))
    assert result_for(report, "unchanged") == "unknown"
    with pytest.raises(ValueError, match="fingerprints, not claimed"):
        replace(state, passed=True)


@pytest.mark.parametrize("files", [
    (SourceFile("solution.py", "pass"), SourceFile("config.ini", "mode=unsafe\n")),
    (SourceFile("solution.py", "pass"),),
])
def test_protected_file_modified_or_missing_is_confirmed_failure(files):
    task, artifact, _ = sample()
    artifact = replace(artifact, files=files)
    report = validate(task, artifact, ())
    assert result_for(report, "config") == "fail"
    assert report.status == "fail"


def test_protected_file_requires_public_baseline_and_explicit_contract_quote():
    task, _, _ = sample()
    with pytest.raises(ValueError, match="no public baseline"):
        replace(task, public_files=())
    with pytest.raises(ValueError, match="public contract basis"):
        replace(task, obligations=(replace(task.obligations[0], contract_quote="not in contract"),))


def test_duplicate_and_relabelled_receipts_cannot_inflate_evidence():
    task, artifact, evidence = sample()
    with pytest.raises(ValueError, match="Duplicate evidence receipt"):
        validate(task, artifact, evidence + evidence)
    relabelled = replace(evidence[0], source_ref="fixture:renamed-receipt")
    with pytest.raises(ValueError, match="relabeled as multiple executions"):
        validate(task, artifact, (evidence[0], relabelled))
    with pytest.raises(ValueError, match="Duplicate observation ID"):
        replace(evidence[0], observations=evidence[0].observations + (evidence[0].observations[0],))


def test_replay_idempotent_and_rubric_identity_binds_full_pipeline():
    task, artifact, evidence = sample()
    rubric = fixed_rubric()
    assert fixed_rubric() == rubric
    assert execution_policy() == rubric.execution_policy
    first = validate(task, artifact, evidence, rubric)
    second = validate(task, artifact, evidence, rubric)
    assert first == second
    assert first.sealed() == second.sealed()
    assert verify(first.sealed())["record_hash"] == first.content_hash
    for field in ("generation_policy", "execution_policy", "applicability_policy", "aggregation_policy"):
        changed = replace(rubric, **{field: "unapproved-new-policy"})
        assert changed.pipeline_hash != rubric.pipeline_hash
        with pytest.raises(ValueError, match="changed validation pipeline"):
            validate(task, artifact, evidence, changed)


@pytest.mark.parametrize("method, kind", [("host_script", "requested_behavior"), ("recorded_public_tests", "input_preservation")])
def test_unsupported_or_wrong_method_cannot_gain_checking_authority(method, kind):
    task, artifact, evidence = sample()
    rubric = fixed_rubric()
    changed = replace(rubric, checks=(replace(rubric.checks[0], method=method, obligation_kind=kind),))
    with pytest.raises(ValueError, match="Unsupported method"):
        validate(task, artifact, evidence, changed)


@pytest.mark.parametrize("gate", ["verifier", "skill"])
@pytest.mark.parametrize("status", ["accepted", "rejected", "commit", "approved"])
def test_stage_one_gate_placeholder_cannot_issue_admission(gate, status):
    with pytest.raises(ValueError, match="no admission authority"):
        GateDecision(gate, status, fixed_rubric().pipeline_hash)


def test_development_gap_summary_is_explicit_and_never_contains_private_detail():
    task, artifact, evidence = sample()
    gap = DevelopmentGap(task.content_hash, artifact.artifact_hash, "sum", "missed_error",
                         "private-audit/HIDDEN-EXPECTED-ANSWER-42")
    view = research_development_view(task, artifact, evidence, gaps=(gap,))
    summary = view["development_gaps"][0]
    assert summary == {"obligation_id": "obligation_0", "category": "missed_error",
                       "information_origin": "development_audit_summary", "research_independent_discovery": False}
    assert "HIDDEN" not in json.dumps(view)
    assert "development_gaps" not in verifier_view(task, artifact, evidence)
    assert "development_gaps" not in skill_feedback_view(task, artifact, evidence)
    assert view["purpose"] == "proposal_development_not_blind_evaluation"
    with pytest.raises(ValueError, match="identity mismatch"):
        research_development_view(task, artifact, evidence, gaps=(replace(gap, task_hash=digest("wrong")),))
    with pytest.raises(ValueError, match="identity mismatch"):
        research_development_view(task, artifact, evidence, gaps=({"hidden_answer": 42},))


@pytest.mark.parametrize("partition", ["verifier_calibration", "verifier_audit", "skill_confirmation", "final"])
def test_research_and_updater_cannot_consume_non_development_gap_data(partition):
    task, artifact, evidence = sample()
    task, artifact, evidence = rebind(replace(task, partition=partition), artifact, evidence)
    with pytest.raises(ValueError, match="development-only"):
        research_development_view(task, artifact, evidence)
    with pytest.raises(ValueError, match="development-only"):
        skill_feedback_view(task, artifact, evidence)


def test_historical_records_cannot_be_relabelled_as_fresh_final_data():
    task, artifact, evidence = sample()
    task, artifact, evidence = rebind(replace(task, partition="final"),
                                     replace(artifact, historical_only=True), evidence)
    with pytest.raises(ValueError, match="diagnostic development only"):
        bind(task, artifact, evidence)


def test_confirmed_check_result_requires_evidence_and_valid_status():
    with pytest.raises(ValueError, match="requires evidence"):
        CheckResult(digest("instance"), "check", "obligation", "pass", "Claimed pass", ())
    with pytest.raises(ValueError, match="Invalid check status"):
        CheckResult(digest("instance"), "check", "obligation", "certain", "No authority", ())


def test_typed_report_rejects_mismatched_receipt_binding_and_invalid_status():
    task, artifact, evidence = sample()
    report = validate(task, artifact, evidence)
    with pytest.raises(ValueError, match="Invalid report status"):
        replace(report, status="accepted")
    with pytest.raises(ValueError, match="mismatched evidence"):
        replace(report, checks=(replace(report.checks[0], instance_hash=digest("other-instance")),) + report.checks[1:])
    with pytest.raises(ValueError, match="mismatched task or Rubric"):
        replace(report, task_hash=digest("wrong-task"))


def test_report_round_trip_cannot_import_nested_hidden_fields():
    task, artifact, evidence = sample()
    raw = validate(task, artifact, evidence).to_dict()
    raw["checks"][0]["private_expected_answer"] = "HIDDEN"
    with pytest.raises(ValueError, match="Unexpected or missing CheckResult fields"):
        ValidationReport.from_dict(raw)


def test_signed_payload_tampering_fails_instead_of_recomputing_identity():
    task, _, _ = sample()
    encoded = task.sealed()
    encoded["prompt"] = "tampered"
    with pytest.raises(ValueError, match="checksum mismatch"):
        unseal_record(encoded, TaskContract)
