"""Synthetic engineering controls; these are not real verifier-effect results."""
from dataclasses import replace

import pytest

from skillopt.skill_validation.calibration import (
    ActualCost,
    CalibrationRow,
    FreezeDeclaration,
    GateConfig,
    calibrate,
    evaluate_comparison,
    paired_diagnostics,
    register_freeze,
)
from skillopt.skill_validation.partitions import PartitionEntry, PartitionManifest
from skillopt.validator_pilot.api import digest

FIXED, ADAPTIVE, RESEARCH = map(digest, ("fixed", "adaptive", "research"))


def row(task="repair", condition="candidate", *, pipeline=FIXED, status="pass", audit="fail",
        applicable=True, near_miss=False, repeat=0, obligation="behavior", partition="verifier_calibration",
        provenance="model", complete=True, historical=False):
    """Deliberately fabricated typed data for unit tests, never persisted as runs."""
    task_hash = digest([task, partition])
    artifact = digest([task_hash, condition, repeat])
    return CalibrationRow(task, "original-" + task, "family-" + task, "project-" + task, partition,
                          task_hash, artifact, repeat, condition, obligation, status, audit, applicable,
                          near_miss, provenance, complete, historical, pipeline,
                          digest([pipeline, artifact]), digest(["audit", artifact]))


def panel(*, provenance="model", complete=True, partition="verifier_calibration", candidate_pipeline=RESEARCH):
    fixed = tuple(row(condition=arm, audit="fail" if arm == "candidate" else "pass",
                      provenance=provenance, complete=complete, partition=partition)
                  for arm in ("no_skill", "current", "candidate"))
    fixed += tuple(row(task="in-place", condition=arm, status="not_applicable", audit="unknown",
                       applicable=False, near_miss=True, provenance=provenance, complete=complete, partition=partition)
                   for arm in ("no_skill", "current", "candidate"))
    candidate = tuple(replace(r, rubric_pipeline_hash=candidate_pipeline,
                              verifier_status="fail" if r.applicable and r.audit_status == "fail" else r.verifier_status,
                              report_hash=digest([candidate_pipeline, r.artifact_record_hash])) for r in fixed)
    return fixed, candidate


def manifest(rows, *, project_disjoint=False):
    return PartitionManifest((PartitionEntry(r.artifact_record_hash, r.original_task_id, r.family_id,
                                            r.project_id, r.partition, r.provenance_kind,
                                            r.provenance_complete, r.historical_only) for r in rows),
                             project_disjoint=project_disjoint)


def configuration(**changes):
    return replace(GateConfig(2, 1, 1, 1, 0.75, 0.0, 0.0, 1), **changes)


def frozen(tmp_path, *, pipeline=RESEARCH, candidates=(RESEARCH,), config=None, dev=None):
    dev = dev or manifest((row(task="development", partition="development"),))
    declaration = FreezeDeclaration(digest(["proposal", pipeline]), pipeline, FIXED, tuple(sorted(candidates)),
                                    digest("protocol"), (config or configuration()).content_hash,
                                    dev.to_dict()["manifest_hash"], digest("frozen-development-data"),
                                    tuple(sorted({e.original_task_id for e in dev.entries})),
                                    tuple(sorted({e.near_duplicate_family for e in dev.entries})))
    register_freeze(declaration, development_manifest=dev, ledger_dir=tmp_path)
    return declaration


def gate(tmp_path, fixed, candidate, *, freeze=None, config=None, supplied_manifest=None):
    config = config or configuration()
    freeze = freeze or frozen(tmp_path, config=config)
    return calibrate(fixed, candidate, manifest=supplied_manifest or manifest(fixed), freeze=freeze,
                     config=config, ledger_dir=tmp_path, fixed_cost=ActualCost(), candidate_cost=ActualCost())


def test_common_obligation_gain_and_complete_evidence(tmp_path):
    fixed, candidate = panel()
    decision, report = gate(tmp_path, fixed, candidate)
    assert decision.status == "accepted"
    assert decision.rubric_pipeline_hash == RESEARCH
    assert report["new_detection_count"] == report["net_new_detection"] == 1
    assert report["full_natural"]["candidate"]["error_detection"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert report["full_natural"]["candidate"]["false_rejection"]["denominator"] == 2
    assert report["natural_old_missed_subset"]["prevalence_all_natural_obligations"]["denominator"] == 6
    assert report["new_detection_evidence"][0]["audit_hash"]
    assert report["paired_diagnostics"]["candidate"]["categories"] == {"skill_related_regression": 1, "uncertain": 1}
    assert report["paired_diagnostics"]["fixed"]["direction_agreement"]["disagree"] == 2
    assert decision.calibration_family_ids == ("family-in-place", "family-repair")
    assert decision.scope_status == "calibration_evidence_only_no_deployment_authority"
    with pytest.raises(ValueError, match="cannot grant"):
        replace(decision, scope_status="cross_domain_deployment_authorized")


def test_calibration_replay_idempotent(tmp_path):
    fixed, candidate = panel()
    first = gate(tmp_path, fixed, candidate)
    snapshot = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert gate(tmp_path, fixed, candidate) == first
    assert snapshot == {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*.json")}


@pytest.mark.parametrize("provenance,complete", [("fixture", True), ("mutant", True), ("model", False)])
def test_non_natural_data_never_authorize(tmp_path, provenance, complete):
    fixed, candidate = panel(provenance=provenance, complete=complete)
    decision, report = gate(tmp_path, fixed, candidate)
    assert decision.status == "pending" and not decision.calibration_family_ids
    assert report["full_natural"]["candidate"]["common_obligation_rows"] == 0
    assert report["diagnostic_only"]["candidate"]["common_obligation_rows"] == 6
    assert report["new_detection_count"] == 0


def test_unknown_can_increase_when_coverage_and_risks_pass(tmp_path):
    fixed, candidate = panel()
    extra = tuple(row(task="extra-correct", condition=arm, audit="pass") for arm in ("no_skill", "current", "candidate"))
    fixed += extra
    candidate += tuple(replace(r, rubric_pipeline_hash=RESEARCH, report_hash=digest([RESEARCH, r.artifact_record_hash]),
                               verifier_status="unknown" if r.condition == "candidate" else "pass") for r in extra)
    decision, report = gate(tmp_path, fixed, candidate)
    assert decision.status == "accepted"
    assert report["full_natural"]["candidate"]["unknown"]["numerator"] == 1
    assert report["full_natural"]["candidate"]["coverage"]["value"] == pytest.approx(5 / 6)


@pytest.mark.parametrize("attack,reason", [("false_reject", "false_rejection_risk_increased"),
                                          ("near_miss", "near_miss_misuse_risk_increased"),
                                          ("coverage", "coverage_below_frozen_floor"),
                                          ("no_gain", "no_sufficient_incremental_natural_detection")])
def test_risk_and_gain_constraints_reject(tmp_path, attack, reason):
    fixed, candidate = panel()
    if attack == "false_reject":
        candidate = tuple(replace(r, verifier_status="fail") if r.applicable and r.audit_status == "pass" else r for r in candidate)
    elif attack == "near_miss":
        candidate = tuple(replace(r, verifier_status="pass") if not r.applicable else r for r in candidate)
    elif attack == "coverage":
        candidate = tuple(replace(r, verifier_status="unknown") if r.applicable and r.audit_status == "pass" else r for r in candidate)
    else:
        candidate = tuple(replace(r, verifier_status="pass") if r.applicable else r for r in candidate)
    decision, _ = gate(tmp_path, fixed, candidate)
    assert decision.status == "rejected" and reason in decision.reasons
    assert decision.scope_status == "calibration_evidence_only_no_deployment_authority"


def test_applicable_not_applicable_is_uncovered_not_success(tmp_path):
    fixed, candidate = panel()
    candidate = tuple(replace(r, verifier_status="not_applicable") if r.applicable and r.audit_status == "pass" else r for r in candidate)
    decision, report = gate(tmp_path, fixed, candidate)
    assert decision.status == "rejected"
    metrics = report["full_natural"]["candidate"]
    assert metrics["applicable_marked_not_applicable"] == 2 and metrics["coverage"]["value"] == pytest.approx(1 / 3)


def test_repeats_do_not_add_independent_families(tmp_path):
    fixed, candidate = panel()
    all_fixed, all_candidate = list(fixed), list(candidate)
    for repeat in range(1, 8):
        for source, target in ((fixed, all_fixed), (candidate, all_candidate)):
            for r in source:
                new_artifact = digest([r.artifact_record_hash, repeat])
                target.append(replace(r, repeat=repeat, artifact_record_hash=new_artifact,
                                      report_hash=digest([r.rubric_pipeline_hash, new_artifact]), audit_hash=digest(["audit", new_artifact])))
    decision, report = gate(tmp_path, all_fixed, all_candidate, config=configuration(min_independent_families=3))
    assert decision.status == "pending"
    assert report["full_natural"]["candidate"]["independent_family_count"] == 2
    assert report["full_natural"]["candidate"]["common_obligation_rows"] == 48


@pytest.mark.parametrize("field,value", [("artifact_record_hash", digest("wrong-artifact")),
                                        ("audit_hash", digest("wrong-audit")), ("audit_status", "fail"),
                                        ("condition", "current"), ("obligation_id", "new-question")])
def test_identity_or_common_obligation_mismatch_rejected(field, value):
    fixed, candidate = panel()
    candidate = (replace(candidate[0], **{field: value}), *candidate[1:])
    with pytest.raises(ValueError):
        evaluate_comparison(fixed, candidate, manifest=manifest(fixed), purpose="verifier_calibration")


def test_duplicate_tests_cannot_inflate_denominator():
    fixed, candidate = panel()
    with pytest.raises(ValueError, match="Duplicate common obligation"):
        evaluate_comparison((*fixed, fixed[0]), (*candidate, candidate[0]), manifest=manifest(fixed), purpose="verifier_calibration")


def test_same_run_cannot_be_relabelled_as_new_repeat():
    fixed, candidate = panel()
    with pytest.raises(ValueError, match="cannot be relabelled"):
        evaluate_comparison((*fixed, replace(fixed[0], repeat=1)),
                            (*candidate, replace(candidate[0], repeat=1)),
                            manifest=manifest(fixed), purpose="verifier_calibration")


def test_common_study_manifest_excludes_audit_development_family_overlap():
    dev = row(task="repair", partition="development")
    audit = row(task="repair", partition="verifier_audit")
    with pytest.raises(ValueError, match="cross validation partitions"):
        manifest((dev, audit))


def test_missing_near_miss_evidence_is_pending(tmp_path):
    fixed, candidate = panel()
    fixed = tuple(r for r in fixed if r.applicable)
    candidate = tuple(r for r in candidate if r.applicable)
    decision, _ = gate(tmp_path, fixed, candidate, config=configuration(min_independent_families=1))
    assert decision.status == "pending" and "insufficient_natural_near_miss" in decision.reasons


def test_lost_detections_are_charged_and_costs_kept_separate():
    fixed, candidate = panel()
    extra = row(task="lost-error", status="fail", audit="fail")
    fixed += (extra,)
    candidate += (replace(extra, rubric_pipeline_hash=RESEARCH, report_hash=digest("lost-report"), verifier_status="unknown"),)
    cost = ActualCost(model_calls=2, input_tokens=100, output_tokens=50, retrievals=1, executions=3,
                      execution_seconds=0.5, failures=1)
    report = evaluate_comparison(fixed, candidate, manifest=manifest(fixed), purpose="verifier_calibration",
                                 candidate_cost=cost)
    assert report["new_detection_count"] == report["lost_detection_count"] == 1
    assert report["net_new_detection"] == 0
    assert report["actual_cost"] == {"fixed": None, "candidate": cost.to_dict()}


def test_pipeline_cannot_change_between_tasks():
    fixed, candidate = panel()
    candidate = tuple(replace(r, rubric_pipeline_hash=ADAPTIVE) if not r.applicable else r for r in candidate)
    with pytest.raises(ValueError, match="pipeline per task"):
        evaluate_comparison(fixed, candidate, manifest=manifest(fixed), purpose="verifier_calibration")


def test_conditions_cannot_have_different_obligation_universes():
    fixed, candidate = panel()
    fixed += (replace(fixed[0], obligation_id="unshared"),)
    candidate += (replace(candidate[0], obligation_id="unshared"),)
    with pytest.raises(ValueError, match="common task-obligation universe"):
        evaluate_comparison(fixed, candidate, manifest=manifest(fixed), purpose="verifier_calibration")


def test_independent_audit_is_descriptive_and_does_not_mutate_gate(tmp_path):
    fixed, candidate = panel()
    decision, _ = gate(tmp_path, fixed, candidate)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    a, b = panel(partition="verifier_audit")
    report = evaluate_comparison(a, b, manifest=manifest(a))
    assert "none" in report["authority"] and decision.status == "accepted"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    with pytest.raises(ValueError, match="different data purpose"):
        gate(tmp_path, a, b)


@pytest.mark.parametrize("purpose", ["skill_confirmation", "final"])
def test_confirmation_final_not_consumed_by_verifier(purpose):
    a, b = panel(partition=purpose)
    with pytest.raises(ValueError, match="cannot consume"):
        evaluate_comparison(a, b, manifest=manifest(a), purpose=purpose)


def test_frozen_group_allows_two_arms_but_prevents_revised_candidate(tmp_path):
    fixed, candidate = panel()
    first = frozen(tmp_path, candidates=(ADAPTIVE, RESEARCH))
    gate(tmp_path, fixed, candidate, freeze=first)
    second = frozen(tmp_path, pipeline=ADAPTIVE, candidates=(ADAPTIVE, RESEARCH))
    a, b = panel(candidate_pipeline=ADAPTIVE)
    assert gate(tmp_path, a, b, freeze=second)[0].status == "accepted"
    newer = digest("revised-proposal")
    third = frozen(tmp_path, pipeline=newer, candidates=(newer,))
    a, b = panel(candidate_pipeline=newer)
    with pytest.raises(ValueError, match="already consumed"):
        gate(tmp_path, a, b, freeze=third)


def test_registered_freeze_cannot_be_rewritten(tmp_path):
    freeze = frozen(tmp_path)
    dev = manifest((row(task="development", partition="development"),))
    with pytest.raises(ValueError, match="Immutable"):
        register_freeze(replace(freeze, proposal_hash=digest("new-proposal")), development_manifest=dev, ledger_dir=tmp_path)


def test_config_or_freeze_missing_rejected(tmp_path):
    fixed, candidate = panel()
    freeze = frozen(tmp_path)
    with pytest.raises(ValueError, match="thresholds changed"):
        gate(tmp_path, fixed, candidate, freeze=freeze, config=configuration(min_coverage=0.1))
    with pytest.raises(ValueError, match="registered before"):
        gate(tmp_path / "missing", fixed, candidate, freeze=freeze)


def test_development_family_cannot_be_reused(tmp_path):
    dev = manifest((row(task="repair", partition="development"),))
    freeze = frozen(tmp_path, dev=dev)
    a, b = panel()
    with pytest.raises(ValueError, match="cross validation partitions"):
        gate(tmp_path, a, b, freeze=freeze)


def test_project_disjoint_protocol_enforced(tmp_path):
    dev_row = replace(row(task="development", partition="development"), project_id="project-repair")
    dev = manifest((dev_row,), project_disjoint=True)
    freeze = frozen(tmp_path, dev=dev)
    a, b = panel()
    with pytest.raises(ValueError, match="Project cannot cross"):
        gate(tmp_path, a, b, freeze=freeze, supplied_manifest=manifest(a, project_disjoint=True))


def test_registered_calibration_artifact_cannot_be_silently_dropped(tmp_path):
    fixed, candidate = panel()
    full = manifest((*fixed, row(task="omitted-harmful")))
    with pytest.raises(ValueError, match="retain every artifact"):
        gate(tmp_path, fixed, candidate, supplied_manifest=full)


def test_shared_error_repair_and_missing_condition_diagnostics():
    shared = [row(condition=a, status="fail", audit="fail") for a in ("no_skill", "current", "candidate")]
    assert paired_diagnostics(shared)["categories"] == {"shared_error": 1}
    repair = [replace(r, audit_status="pass", verifier_status="pass") if r.condition == "candidate" else r for r in shared]
    assert paired_diagnostics(repair)["categories"] == {"skill_repair": 1}
    missing = paired_diagnostics(repair[:-1])
    assert missing["categories"] == {"uncertain": 1}
    assert missing["records"][0]["missing_conditions"] == ["candidate"]


def test_legacy_rows_remain_diagnostic_and_no_cost_is_not_zero():
    a = row(partition="development", historical=True)
    b = replace(a, rubric_pipeline_hash=RESEARCH, report_hash=digest("research-report"), verifier_status="fail")
    report = evaluate_comparison((a,), (b,), manifest=manifest((a,)), purpose="development")
    assert report["diagnostic_only"]["candidate"]["common_obligation_rows"] == 1
    assert report["full_natural"]["candidate"]["common_obligation_rows"] == 0
    assert report["actual_cost"] == {"fixed": None, "candidate": None}


def test_schema_roundtrips_and_nonfinite_cost_rejected(tmp_path):
    example = row()
    assert CalibrationRow.from_dict(example.to_dict()) == example
    freeze = frozen(tmp_path)
    assert FreezeDeclaration.from_dict(freeze.to_dict()) == freeze
    with pytest.raises(ValueError):
        ActualCost(execution_seconds=float("nan"))
    with pytest.raises(ValueError):
        ActualCost(model_calls=True)
    with pytest.raises(ValueError):
        configuration(min_coverage=float("nan"))
    with pytest.raises(ValueError):
        replace(example, applicable=False, audit_status="fail")


def test_ledger_symlink_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        frozen(link)
