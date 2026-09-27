"""Engineering fixtures only; these counts are not natural efficacy evidence."""
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation.verifier_readiness import DEFAULT_CONFIG, diagnose_readiness
from skillopt.validator_pilot.api import digest


PILOT = {"min_independent_families": 2, "min_error_families": 1,
         "min_missed_error_families": 1, "min_correct_families": 1,
         "min_prediction_coverage": 0.5, "min_audit_coverage": 0.5}


def row(task="error", family=None, repeat=0, condition="current", audit="fail", fixed="pass", new="fail",
        partition="verifier_calibration"):
    return {"task_id": task, "family_id": family or task, "repeat": repeat, "condition": condition,
            "audit_status": audit, "fixed_status": fixed, "new_status": new, "partition": partition}


def panel(partition="verifier_calibration"):
    return [row(partition + "-error", partition=partition),
            row(partition + "-correct", audit="pass", new="pass", partition=partition)]


def describe(rows, **kwargs):
    return diagnose_readiness(rows, protocol_hash=digest("frozen fixture protocol"), config=PILOT, **kwargs)


def test_sealed_order_independent_whitelist_and_no_authority():
    rows = panel()
    rows[0].update({"hidden_tests": "SECRET_TEST", "reference_code": object(), "arbitrary": float("nan")})
    report = describe(rows)
    assert verify(report) == report
    assert report == describe(list(reversed(rows)))
    assert "SECRET_TEST" not in json.dumps(report)
    for flag in ("feedback_authorized", "skill_admission_authorized", "deployment_authorized", "model_visible"):
        assert report[flag] is False
    assert report["host_only"] is True
    summary = report["panels"]["verifier_calibration"]
    assert summary["evidence_sufficient"] is True
    assert summary["status"] == "pending" and summary["reasons"] == ["previously_consumed_panel"]
    assert "task_id" not in json.dumps(report) and "error-correct" not in json.dumps(report)


def test_explicit_fresh_enough_only_reports_readiness_not_acceptance():
    report = describe(panel(), consumed_panels=[])
    assert report["panels"]["verifier_calibration"]["status"] == "ready_for_independent_calibration"
    assert not report["feedback_authorized"] and not report["deployment_authorized"]
    assert "accepted" not in json.dumps(report)


def test_repeats_and_conditions_cannot_substitute_for_independent_error_families():
    rows = [row(repeat=i, condition=c) for i in range(100) for c in ("no_skill", "current", "candidate")]
    report = diagnose_readiness(rows, protocol_hash=digest("p"), consumed_panels=[])
    summary = report["panels"]["verifier_calibration"]
    assert summary["counts"]["audit_errors"] == {"positions": 300, "tasks": 1, "families": 1}
    assert summary["counts"]["fixed_undetected_errors"]["families"] == 1
    assert summary["status"] == "pending"
    assert "insufficient_error_families" in summary["reasons"]
    assert "insufficient_fixed_missed_error_families" in summary["reasons"]
    assert DEFAULT_CONFIG["min_error_families"] > 1


def test_distinct_tasks_in_same_family_count_once_and_family_support_not_additive():
    rows = [row("one", "shared"), row("two", "shared", audit="pass", new="fail")]
    result = describe(rows)["panels"]["verifier_calibration"]
    assert result["counts"]["all"] == {"positions": 2, "tasks": 2, "families": 1}
    assert result["counts"]["audit_errors"]["families"] == result["counts"]["audit_correct"]["families"] == 1
    assert result["new"]["false_rejections"]["families"] == 1


def test_unknown_preserved_and_zero_denominators_are_null():
    result = describe([row(audit="unknown", new="unknown")])["panels"]["verifier_calibration"]
    assert result["new"]["error_detection_position_rate"]["value"] is None
    assert result["new"]["false_rejection_position_rate"]["value"] is None
    assert result["new"]["statuses"] == {"pass": 0, "fail": 0, "unknown": 1}
    assert result["audit_coverage"]["value"] == 0
    assert "insufficient_prediction_coverage" in result["reasons"]
    assert "insufficient_audit_coverage" in result["reasons"]


def test_missed_errors_distinguish_unknown_from_explicit_pass():
    rows = [row("one", fixed="unknown", new="fail"), row("two", new="unknown"), row("three", new="pass")]
    result = describe(rows)["panels"]["verifier_calibration"]
    assert result["new"]["undetected_errors"]["positions"] == 2
    assert result["new"]["undetected_unknown"]["positions"] == 1
    assert result["new"]["undetected_explicit_pass"]["positions"] == 1
    assert result["new_detections"] == {"positions": 1, "tasks": 1, "families": 1}


def test_repeated_paired_regressions_have_one_task_and_family_per_matrix_cell():
    rows = []
    for repeat in range(4):
        rows += [row("same", repeat=repeat, condition="no_skill", audit="pass", new="pass"),
                 row("same", repeat=repeat, condition="candidate", audit="fail", new="fail")]
    pair = describe(rows)["panels"]["verifier_calibration"]["paired_diagnostics"]["comparisons"]["candidate_vs_no_skill"]
    summary = pair["new_status"]
    assert summary["audit_vs_verifier"]["regression/regression"] == 4
    assert summary["audit_vs_verifier_distinct_tasks"]["regression/regression"] == 1
    assert summary["audit_vs_verifier_distinct_families"]["regression/regression"] == 1
    assert summary["correctly_labeled_regressions"] == {"positions": 4, "tasks": 1, "families": 1}


def test_complete_direction_matrix_and_regression_support():
    rows = []
    directions = [("pass", "fail", "pass", "pass"), ("pass", "fail", "pass", "unknown"),
                  ("pass", "fail", "pass", "fail"), ("fail", "pass", "fail", "pass"),
                  ("fail", "fail", "fail", "fail"), ("unknown", "pass", "unknown", "pass")]
    for i, (before, after, predicted_before, predicted_after) in enumerate(directions):
        rows += [row(str(i), condition="no_skill", audit=before, new=predicted_before),
                 row(str(i), condition="candidate", audit=after, new=predicted_after)]
    summary = describe(rows)["panels"]["verifier_calibration"]["paired_diagnostics"]
    pair = summary["comparisons"]["candidate_vs_no_skill"]
    assert pair["support"] == {"positions": 6, "tasks": 6, "families": 6}
    metrics = pair["new_status"]
    assert metrics["audit_regressions"] == {"positions": 3, "tasks": 3, "families": 3}
    assert metrics["correctly_labeled_regressions"] == {"positions": 1, "tasks": 1, "families": 1}
    assert metrics["regression_detection_rate"]["value"] == pytest.approx(1 / 3)
    assert metrics["regressions_labeled_shared_correct"]["positions"] == 1
    assert metrics["regressions_labeled_unknown"]["positions"] == 1
    assert metrics["correctly_labeled_repairs"]["positions"] == 1
    matrix = metrics["audit_vs_verifier"]
    assert len(matrix) == 25 and sum(matrix.values()) == 6
    assert matrix["shared_error/shared_error"] == matrix["unknown/unknown"] == 1
    assert summary["unavailable_comparisons_missing_conditions"]["current_vs_no_skill"] == ["current"]


def test_missing_pair_positions_are_unknown_not_dropped():
    rows = [row("one", condition="no_skill", audit="pass", new="pass"),
            row("two", condition="candidate", audit="fail", new="fail")]
    pair = describe(rows)["panels"]["verifier_calibration"]["paired_diagnostics"]["comparisons"]["candidate_vs_no_skill"]
    assert pair["support"]["positions"] == 2
    assert pair["missing_baseline_positions"] == pair["missing_target_positions"] == 1
    assert pair["new_status"]["audit_vs_verifier"]["unknown/unknown"] == 2


def test_mixed_partitions_never_pool_minima_and_consumption_is_explicit():
    rows = panel() + panel("verifier_audit")
    report = describe(rows, consumed_panels=["verifier_calibration"])
    assert report["panels"]["verifier_calibration"]["status"] == "pending"
    assert report["panels"]["verifier_audit"]["status"] == "ready_for_independent_calibration"
    assert all(p["counts"]["all"]["positions"] == 2 for p in report["panels"].values())


def test_cross_partition_family_overlap_is_reported_pending_not_pooled():
    rows = panel() + panel("verifier_audit")
    rows[0]["family_id"] = rows[2]["family_id"] = "overlap"
    report = describe(rows, consumed_panels=[])
    for result in report["panels"].values():
        assert result["cross_partition_family_count"] == 1
        assert "family_overlap_across_partitions" in result["reasons"]
        assert result["status"] == "pending"


@pytest.mark.parametrize("field,value", [("audit_status", "not_applicable"), ("new_status", "error"),
                                          ("fixed_status", None), ("condition", "best_candidate"),
                                          ("repeat", True), ("repeat", -1), ("family_id", {}),
                                          ("partition", "test")])
def test_strict_row_semantics(field, value):
    record = row()
    record[field] = value
    with pytest.raises(ValueError):
        describe([record])


def test_duplicate_positions_and_changed_identities_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        describe([row(), row()])
    with pytest.raises(ValueError, match="family identity"):
        describe([row(), row(family="different", repeat=1)])
    with pytest.raises(ValueError, match="one partition"):
        describe([row(), row(partition="verifier_audit", repeat=1)])


def test_legacy_partition_can_be_declared_but_not_overridden():
    record = row()
    del record["partition"]
    with pytest.raises(ValueError, match="partition"):
        describe([record])
    assert describe([record], partition="verifier_calibration")["panels"]
    with pytest.raises(ValueError, match="differs"):
        describe([row()], partition="development")


@pytest.mark.parametrize("config", [{"min_error_families": 0}, {"min_error_families": True},
                                    {"min_prediction_coverage": float("nan")},
                                    {"min_prediction_coverage": 1.1}, {"arbitrary": 1}])
def test_frozen_threshold_validation(config):
    with pytest.raises(ValueError):
        diagnose_readiness(panel(), protocol_hash=digest("p"), config=config)


def test_empty_input_and_non_verifier_partitions_cannot_be_ready():
    assert describe([])["empty_input"] is True
    assert describe([], partition="verifier_calibration")["panels"]["verifier_calibration"]["status"] == "pending"
    for part in ("development", "skill_confirmation", "final"):
        result = describe(panel(part), consumed_panels=[])["panels"][part]
        assert result["status"] == "pending" and "not_an_independent_verifier_panel" in result["reasons"]


def test_config_and_input_not_mutated_and_status_changes_bound_by_hash():
    config, rows = deepcopy(PILOT), panel()
    before = deepcopy(rows)
    first = diagnose_readiness(rows, protocol_hash=digest("p"), config=config)
    assert rows == before and config == PILOT
    rows[0]["new_status"] = "unknown"
    second = diagnose_readiness(rows, protocol_hash=digest("p"), config=config)
    assert first["records_hash"] != second["records_hash"]
    assert first["record_hash"] != second["record_hash"]
