"""Scripted host measurement tests; no execution, natural-efficacy, or API claim."""
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation.natural_metrics import DEFAULT_CONFIG, calibrate_policy, summarize
from skillopt.validator_pilot.api import digest

BINDINGS = {key: digest(key) for key in ("policy_hash", "protocol_hash", "manifest_hash")}


def calibration_rows():
    rows = []
    for task in range(8):
        for condition in ("no_skill", "current"):
            audit = "fail" if task < 2 else "pass"
            rows.append({
                "task_id": f"fixture-task-{task}", "family_id": f"fixture-family-{task}", "repeat": 0,
                "condition": condition, "audit_status": audit, "fixed_status": "pass", "new_status": audit,
                "artifact_hash": digest([task, condition]), "report_hash": digest([task, condition, "report"]),
                "audit_hash": digest([task, condition, "audit"]), "partition": "verifier_calibration",
            })
    return rows


def final_row(task, status, *, arm="candidate", repeat=0, family=None, native="pass"):
    return {"task_id": task, "family_id": family or task, "repeat": repeat, "arm": arm,
            "status": status, "native_status": native, "partition": "final"}


def test_default_calibration_is_only_finite_qualified_development_permission():
    result = calibrate_policy(calibration_rows(), **BINDINGS)
    verify(result)
    assert result["status"] == "accepted"
    assert result["config"] == DEFAULT_CONFIG
    assert result["counts"] == {
        "artifact_obligation_positions": 16, "tasks": 8, "independent_families": 8,
        "natural_errors": 4, "natural_correct": 12, "audit_unknown": 0,
        "error_families": 2, "correct_families": 6,
    }
    assert result["qualified_development_feedback_authorized"] is True
    assert result["scope"] == {"adapter_domain": "coding", "obligation_kinds": ["requested_behavior"],
                               "allowed_partition": "development", "purpose": "qualified_public_feedback_only"}
    for authority in ("deployment_authorized", "skill_admission_authorized", "cross_domain_authorized", "near_miss_authorized"):
        assert result[authority] is False
    assert result["net_new_detection"] == 4
    assert result["fixed"]["error_detection"]["denominator"] == result["new"]["error_detection"]["denominator"] == 4
    assert result["fixed"]["false_rejection"]["denominator"] == result["new"]["false_rejection"]["denominator"] == 12
    assert "not per probe" in result["unit"]


def test_no_known_errors_is_pending_even_with_many_positive_outputs():
    rows = calibration_rows()
    for row in rows:
        row.update(audit_status="pass", fixed_status="pass", new_status="pass")
    result = calibrate_policy(rows, **BINDINGS)
    assert result["status"] == "pending"
    assert "insufficient_natural_errors" in result["reasons"]
    assert result["new"]["error_detection"]["value"] is None
    assert result["qualified_development_feedback_authorized"] is False
    assert calibrate_policy([], **BINDINGS)["status"] == "pending"


def test_unknown_audit_is_never_an_error_or_correct_obligation():
    rows = calibration_rows()
    rows[0].update(audit_status="unknown", new_status="fail")
    result = calibrate_policy(rows, **BINDINGS)
    assert result["status"] == "pending"
    assert result["counts"]["natural_errors"] == 3
    assert result["counts"]["audit_unknown"] == 1
    assert result["new"]["error_detection"] == {"numerator": 3, "denominator": 3, "value": 1.0}
    assert result["net_new_detection"] == 3


def test_unknown_predictions_are_coverage_loss_not_false_rejections():
    rows = calibration_rows()
    rows[-1]["new_status"] = "unknown"
    accepted = calibrate_policy(rows, **BINDINGS)
    assert accepted["status"] == "accepted"
    assert accepted["new"]["coverage"]["value"] == 15 / 16
    assert accepted["new"]["false_rejection"]["numerator"] == 0
    rows[-2]["new_status"] = "unknown"
    rejected = calibrate_policy(rows, **BINDINGS)
    assert rejected["status"] == "rejected"
    assert "coverage_below_frozen_floor" in rejected["reasons"]


def test_false_rejection_increase_and_lost_detection_block_qualification():
    rows = calibration_rows()
    rows[-1]["new_status"] = "fail"
    rejected = calibrate_policy(rows, **BINDINGS)
    assert rejected["status"] == "rejected"
    assert rejected["false_rejection_increase"] == 1 / 12
    rows = calibration_rows()
    for row in rows[:3]:
        row.update(fixed_status="fail", new_status="pass")
    rejected = calibrate_policy(rows, **BINDINGS)
    assert rejected["status"] == "rejected"
    assert rejected["new_detection_count"] == 1
    assert rejected["lost_detection_count"] == 3
    assert rejected["net_new_detection"] == -2


def test_repeated_tasks_do_not_manufacture_independent_families():
    rows = calibration_rows()
    for row in rows:
        row["family_id"] = "one-family"
    result = calibrate_policy(rows, **BINDINGS)
    assert result["status"] == "pending"
    assert "insufficient_independent_families" in result["reasons"]


def test_calibration_is_order_invariant_detached_and_bound_to_declarations():
    rows = calibration_rows()
    original = deepcopy(rows)
    assert calibrate_policy(rows, **BINDINGS) == calibrate_policy(reversed(rows), **BINDINGS)
    assert rows == original
    for row in rows:
        row.update(BINDINGS)
    assert calibrate_policy(rows, **BINDINGS)["status"] == "accepted"
    rows[0]["policy_hash"] = digest("other policy")
    with pytest.raises(ValueError, match="frozen policy"):
        calibrate_policy(rows, **BINDINGS)


@pytest.mark.parametrize("mutation,reason", [
    (lambda rows: rows.append(deepcopy(rows[0])), "Duplicate calibration"),
    (lambda rows: rows[0].update(partition="final"), "verifier_calibration"),
    (lambda rows: rows[0].update(condition="candidate"), "No-Skill/Current"),
    (lambda rows: rows[0].update(new_status="not_applicable"), "statuses"),
    (lambda rows: rows[0].update(family_id="inconsistent-family"), "family identity"),
    (lambda rows: rows[0].update(artifact_hash="not-a-hash"), "SHA256"),
    (lambda rows: rows[0].update(probe_count=10000), "Exact artifact/task/obligation"),
])
def test_calibration_rejects_changed_units_scope_or_identity(mutation, reason):
    rows = calibration_rows()
    mutation(rows)
    with pytest.raises(ValueError, match=reason):
        calibrate_policy(rows, **BINDINGS)


@pytest.mark.parametrize("config", [
    {"min_natural_errors": 0}, {"min_natural_correct": True}, {"min_net_new_detection": 0},
    {"min_coverage": float("nan")}, {"max_false_rejection_increase": -1}, {"min_near_miss": 0},
])
def test_invalid_or_weakened_to_zero_sample_config_cannot_invent_authority(config):
    with pytest.raises(ValueError):
        calibrate_policy(calibration_rows(), config=config, **BINDINGS)


def test_final_counts_keep_unknown_separate_and_show_native_hidden_gap():
    rows = [final_row("a", "pass"), final_row("b", "fail"), final_row("c", "unknown")]
    report = summarize(rows, protocolseed=42)
    verify(report)
    arm = report["arms"]["candidate"]
    assert report["bootstrap_samples"] == 2000
    assert arm["counts"] == {"pass": 1, "fail": 1, "unknown": 1}
    assert arm["full_attempt_success"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert arm["native_counts"] == {"pass": 3, "fail": 0, "unknown": 0}
    gap = arm["native_vs_stronger"]
    assert gap["native_pass_stronger_fail"] == 1
    assert gap["unknown_pairs"] == 1
    assert gap["full_attempt_success_gap"] == 2 / 3
    assert report["deployment_authorized"] is False


def test_paired_wins_losses_ties_unknown_for_each_available_baseline():
    rows = []
    for task, before, after in (("win", "fail", "pass"), ("loss", "pass", "fail"),
                                ("tie", "fail", "fail"), ("unknown", "pass", "unknown")):
        rows += [final_row(task, before, arm="no_skill"), final_row(task, before, arm="current"),
                 final_row(task, after)]
    report = summarize(rows, protocolseed=17, bootstrap_samples=100)
    for baseline in ("no_skill", "current"):
        pair = report["paired"]["candidate_vs_" + baseline]
        assert [pair[key] for key in ("win", "loss", "tie", "unknown")] == [1, 1, 1, 1]
        assert pair["known_pair_coverage"]["value"] == 3 / 4
        assert pair["task_mean_full_attempt_delta_ci"]["estimate"] == -1 / 4


def test_missing_compared_position_is_retained_as_unknown():
    rows = [final_row("a", "pass", arm="no_skill"), final_row("a", "pass"),
            final_row("b", "pass", arm="no_skill")]
    pair = summarize(rows, bootstrap_samples=100)["paired"]["candidate_vs_no_skill"]
    assert pair["positions"] == 2 and pair["tie"] == 1 and pair["unknown"] == 1
    assert pair["missing_arm_positions"] == 1
    assert pair["task_mean_full_attempt_delta_ci"]["task_count"] == 2


def test_repeats_average_within_task_before_bootstrap():
    rows = [final_row("many-repeats", "pass", repeat=index) for index in range(9)]
    rows.append(final_row("one-repeat", "fail"))
    arm = summarize(rows, protocolseed=3)["arms"]["candidate"]
    assert arm["full_attempt_success"]["value"] == 0.9
    ci = arm["task_mean_success_ci"]
    assert ci["estimate"] == 0.5 and ci["task_count"] == 2 and ci["family_count"] == 2
    assert ci["lower"] == 0 and ci["upper"] == 1


def test_complete_family_clusters_move_together_not_tasks_or_repeats():
    rows = [final_row("a", "pass", family="one-family"), final_row("b", "fail", family="one-family")]
    ci = summarize(rows, protocolseed=3)["arms"]["candidate"]["task_mean_success_ci"]
    assert ci["task_count"] == 2 and ci["family_count"] == 1
    assert ci["lower"] == ci["estimate"] == ci["upper"] == 0.5
    assert ci["inferential_claim_authorized"] is False


def test_bootstrap_is_seeded_order_invariant_and_ignores_unrelated_record_metadata():
    rows = [final_row(str(i), "pass" if i % 3 else "fail", family=str(i // 2)) for i in range(12)]
    expected = summarize(rows, protocolseed=20260920)
    assert summarize(reversed(rows), protocolseed=20260920) == expected
    for row in rows:
        row["diagnostic_log"] = "Ignored metadata is not an independent observation."
    assert summarize(rows, protocolseed=20260920) == expected


@pytest.mark.parametrize("mutation,reason", [
    (lambda rows: rows.append(deepcopy(rows[0])), "Duplicate final"),
    (lambda rows: rows[0].update(partition="development"), "declared partition"),
    (lambda rows: rows[0].update(status="error"), "statuses"),
    (lambda rows: rows[0].update(repeat=True), "integer repeat"),
    (lambda rows: rows.append(final_row("a", "pass", arm="no_skill", family="changed")), "family identity"),
])
def test_final_positions_and_family_identity_are_not_silently_changed(mutation, reason):
    rows = [final_row("a", "pass")]
    mutation(rows)
    with pytest.raises(ValueError, match=reason):
        summarize(rows)


def test_empty_final_panel_is_explicit_and_non_authorizing():
    report = summarize([], protocolseed=7)
    assert report["attempts"] == report["tasks"] == report["families"] == 0
    assert report["arms"] == report["paired"] == {}
    assert report["deployment_authorized"] is False


@pytest.mark.parametrize("partition", ["development", "skill_confirmation", "final"])
def test_descriptive_partition_is_explicit_and_never_erased(partition):
    row = {**final_row("a", "pass"), "partition": partition}
    report = summarize([row], partition=partition, bootstrap_samples=10)
    assert report["partition"] == partition
    assert report["purpose"] == "descriptive_" + partition + "_audit_summary"
    assert report["deployment_authorized"] is False
    with pytest.raises(ValueError, match="declared partition"):
        summarize([row], partition="development" if partition == "final" else "final")


def test_calibration_is_not_a_descriptive_evaluation_partition():
    with pytest.raises(ValueError, match="Unsupported descriptive partition"):
        summarize([], partition="verifier_calibration")
