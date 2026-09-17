"""Descriptive statistics with missingness and pairing checked explicitly."""
from copy import deepcopy

import pytest

from skillopt.validator_pilot.analysis import compare_judges, summarize_rows


def row(index, hard=True, decision="pass", **changes):
    value = {"id": f"task-{index}", "cluster_id": f"cluster-{index}", "family": "mapping",
             "split": "audit", "skill_version": "v0", "repeat": 0, "origin": "natural",
             "target_ok": True, "execution_ok": True, "hard": hard,
             "judgment": {"decision": decision, "schema_valid": True}, "judge_ok": True,
             "request_hash": f"target-hash-{index}"}
    value.update(changes)
    return value


def test_complete_confusion_and_denominators():
    rows = [row(0, True, "pass"), row(1, False, "fail"), row(2, False, "pass"),
            row(3, True, "fail"), row(4, True, "unknown"), row(5, False, "unknown")]
    metrics = summarize_rows(rows)["main"]
    assert all(metrics[key] == 1 for key in ("TP", "TN", "FP", "FN", "unknown_true", "unknown_false"))
    assert metrics["n_tasks"] == metrics["n_responses"] == 6
    assert metrics["false_pass_rate"] == pytest.approx(1 / 3)
    assert metrics["pass_contamination"] == .5
    assert metrics["true_pass_acceptance"] == pytest.approx(1 / 3)
    assert metrics["decisive_coverage"] == pytest.approx(4 / 6)
    assert metrics["schema_valid_count"] == 6


def test_natural_and_controlled_never_pooled_main():
    result = summarize_rows([row(0, True, "pass"), row(1, False, "pass", origin="controlled")])
    assert result["main"]["FP"] == 0
    assert result["main"]["n_responses"] == 1
    assert result["by_origin"]["controlled"]["FP"] == 1
    assert result["by_skill_version"]["natural"]["v0"]["n_responses"] == 1
    assert result["by_family"]["controlled"]["mapping"]["n_responses"] == 1
    assert result["audit_totals"]["n_rows"] == 2


def test_invalid_schema_is_unknown_not_dropped_or_correct_rejection():
    bad = row(0, False, "fail", judgment={"decision": "fail", "schema_valid": False})
    result = summarize_rows([bad])["main"]
    assert result["n_observable"] == result["schema_errors"] == result["unknown_false"] == 1
    assert result["TN"] == result["schema_valid_count"] == 0
    assert result["decisive_coverage"] == 0


def test_api_failures_not_conflated_with_task_or_schema_failure():
    rows = [row(0, None, target_ok=False, execution_ok=False, judge_ok=False),
            row(1, None, execution_ok=False), row(2, False, "pass", judge_ok=False)]
    result = summarize_rows(rows)["main"]
    assert result["target_api_errors"] == 1
    assert result["execution_errors"] == 1
    assert result["judge_api_errors"] == 2
    assert result["schema_errors"] == 0
    assert result["n_unobservable"] == 2
    assert result["hard_fail"] == 1
    assert result["unknown_false"] == 1
    assert result["FP"] == result["TN"] == 0


def test_unusable_or_missing_oracle_never_becomes_wrong_answer():
    result = summarize_rows([row(0, None), row(1, False, target_ok=False)])["main"]
    assert result["n_unobservable"] == 2
    assert result["unusable_populated_hard_count"] == 1
    assert result["missing_hard_count"] == 1
    assert result["hard_fail"] == 0
    assert result["false_pass_rate"] is None


def test_repeats_and_mutants_disclose_cluster_dependence():
    rows = [row(0), row(0, repeat=1), row(1, cluster_id="cluster-0", origin="controlled")]
    result = summarize_rows(rows)
    assert result["main"]["n_responses"] == 2
    assert result["main"]["n_tasks"] == result["main"]["n_clusters"] == 1
    assert result["audit_totals"]["n_clusters"] == 1


def test_empty_denominators_are_none_not_zero():
    metrics = summarize_rows([])["main"]
    assert metrics["n_responses"] == 0
    assert metrics["false_pass_rate"] is metrics["decisive_coverage"] is None


def test_all_accept_and_all_abstain_cannot_hide_tradeoffs():
    rows = [row(0, True), row(1, False)]
    accepted = summarize_rows(rows)["main"]
    assert accepted["true_pass_acceptance"] == accepted["false_pass_rate"] == 1
    for item in rows:
        item["judgment"]["decision"] = "unknown"
    abstained = summarize_rows(rows)["main"]
    assert abstained["false_pass_rate"] == abstained["true_pass_acceptance"] == abstained["decisive_coverage"] == 0
    assert abstained["pass_contamination"] is None


@pytest.mark.parametrize("change", [{"hard": "false"}, {"hard": 1.0}, {"judge_ok": 1}, {"target_ok": None},
                                   {"repeat": True}, {"origin": "mixed"}, {"request_hash": ""}])
def test_ambiguous_input_fields_raise(change):
    with pytest.raises(ValueError):
        summarize_rows([row(0, **change)])


def test_duplicates_are_not_silently_double_counted():
    with pytest.raises(ValueError, match="duplicate"):
        summarize_rows([row(0), row(0)])


def test_integer_hard_labels_are_supported():
    metrics = summarize_rows([row(0, 1), row(1, 0)])["main"]
    assert metrics["TP"] == metrics["FP"] == 1


def test_paired_corrections_and_abstentions_separate():
    left = [row(0, False, "pass"), row(1, True, "fail"), row(2, True, "pass"),
            row(3, False, "pass"), row(4, True, "unknown"), row(5, True, "pass")]
    right = deepcopy(left)
    for item, decision in zip(right, ["fail", "pass", "fail", "unknown", "pass", "unknown"]):
        item["judgment"]["decision"] = decision
    result = compare_judges(left, right)["main"]
    assert result["decisive_corrections"] == 2
    assert result["decisive_regressions"] == 1
    assert result["corrected_false_passes"] == result["corrected_false_rejections"] == 1
    assert result["false_pass_to_abstention"] == 1
    assert result["abstention_to_correct"] == result["correct_to_abstention"] == 1
    assert result["net_correct_decision_count"] == 1
    assert result["left"]["FP"] == 2 and result["right"]["FP"] == 0


@pytest.mark.parametrize("field,new", [("hard", False), ("request_hash", "other-target"),
                                      ("execution_ok", False), ("target_ok", False),
                                      ("family", "other"), ("cluster_id", "other"), ("split", "test")])
def test_conflicting_paired_evidence_raises(field, new):
    left, right = row(0), row(0)
    right[field] = new
    with pytest.raises(ValueError, match="evidence mismatch"):
        compare_judges([left], [right])


def test_pairing_key_includes_version_repeat_and_origin():
    left = [row(0), row(0, repeat=1), row(0, skill_version="v1"), row(0, origin="controlled")]
    right = deepcopy(left)
    result = compare_judges(left, right)
    assert result["n_pairs"] == 4
    assert result["main"]["n_pairs"] == 3
    assert result["by_origin"]["controlled"]["n_pairs"] == 1


def test_unpaired_rows_reported_not_erased():
    result = compare_judges([row(0), row(1, False)], [row(0), row(2)])
    assert result["n_pairs"] == result["left_only_count"] == result["right_only_count"] == 1
    assert result["left_all_rows"]["main"]["FP"] == 1
    assert result["main"]["left"]["FP"] == 0


def test_unknown_oracle_pairs_have_no_correctness_transition():
    result = compare_judges([row(0, None, "pass")], [row(0, None, "fail")])["main"]
    assert result["n_pairs"] == 1
    assert result["n_observable_pairs"] == 0
    assert result["decisive_corrections"] == result["decisive_regressions"] == 0


def test_distinct_judge_request_hash_does_not_replace_target_hash():
    left, right = row(0), row(0)
    left["judge_request_hash"] = "judge-left"
    right["judge_request_hash"] = "judge-right"
    assert compare_judges([left], [right])["n_pairs"] == 1


def test_empty_comparison_is_explicit():
    result = compare_judges([], [])
    assert result["n_pairs"] == 0
    assert result["main"]["left"]["false_pass_rate"] is None
