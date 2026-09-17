"""Synthetic repeated-observation diagnostics; no experiment effect claims."""

from copy import deepcopy

import pytest

from skillopt.coevolution_v6.statistics import cluster_inference, summarize_validator
from skillopt.validator_pilot.api import digest


def union(left, right):
    if "detected" in {left, right}:
        return "detected"
    if "not_detected" in {left, right}:
        return "not_detected"
    return "unknown"


def grid(*, clusters=6, blocks=4, variants=None, outcomes=None):
    values = []
    variants = variants or {}
    for cluster in range(clusters):
        for truth in ("good", "bad"):
            for variant in range(variants.get((cluster, truth), 1)):
                identifier = f"project{cluster}-{truth}-variant{variant}"
                for block in range(blocks):
                    outcome = outcomes(cluster, truth, variant, block) if outcomes else (
                        "not_detected", "not_detected", "detected" if truth == "bad" else "not_detected")
                    old_a, old_b, new = outcome
                    a_hash, b_hash, n_hash = [digest([identifier, block, arm]) for arm in ("old_a", "old_b", "new")]
                    count_a, count_b, count_n = [0 if result == "unknown" else 4 for result in outcome]
                    arms = {
                        "old_single": (old_a, [a_hash], count_a),
                        "new_single": (new, [n_hash], count_n),
                        "old_double": (union(old_a, old_b), [a_hash, b_hash], count_a + count_b),
                        "portfolio": (union(old_a, new), [a_hash, n_hash], count_a + count_n),
                    }
                    for policy, (result, requests, count) in arms.items():
                        values.append({"artifact_id": identifier, "cluster_id": f"project{cluster}", "truth": truth,
                                       "block": block, "policy": policy, "outcome": result,
                                       "input_count": count, "probe_request_hashes": requests})
    return values


def summarize(rows, *, registered=True, **kwargs):
    expected = {row["artifact_id"]: {"cluster_id": row["cluster_id"], "truth": row["truth"]} for row in rows}
    blocks = sorted({row["block"] for row in rows})
    return summarize_validator(rows, expected_artifacts=expected if registered else None,
                               expected_blocks=blocks if registered else None, bootstrap_samples=200, **kwargs)


def outcome_pair(cluster, truth, variant, block):
    if truth == "good":
        return "not_detected", "not_detected", "not_detected"
    return ("detected" if block == 0 else "not_detected", "not_detected",
            "not_detected" if block == 0 else "detected")


def test_all_cluster_benefit_supports_only_diagnostic_gate():
    result = summarize(grid())
    gate = result["primary_gate"]
    assert gate["action"] == "Support"
    assert gate["activate"] is False
    assert gate["bad_detection_lower_bound"] == 1
    primary = result["comparisons"]["portfolio_vs_old_double"]["metrics"]["bad_detection"]
    assert primary["cluster_mean_delta"] == 1
    assert primary["sign_flip"]["assignments"] == 64
    assert primary["sign_flip"]["p_two_sided"] == 2 / 64
    assert primary["sign_flip"]["p_one_sided_positive"] == 1 / 64
    assert result["design"]["few_clusters"]


def test_block_permutation_and_row_order_do_not_change_summary():
    rows = grid()
    assert summarize(rows) == summarize(list(reversed(rows)))
    assert summarize(rows, seed=3) == summarize(rows, seed=3)


def test_inferred_grid_never_claims_preregistered_coverage():
    result = summarize(grid(), registered=False)
    assert result["primary_gate"]["action"] == "Hold"
    assert "no_preregistered_full_design" in result["primary_gate"]["reasons"]


@pytest.mark.parametrize("clusters,blocks,reason", [(5, 4, "fewer_than_six_project_clusters"),
                                                   (6, 3, "fewer_than_four_repeated_blocks")])
def test_insufficient_independent_coverage_holds(clusters, blocks, reason):
    result = summarize(grid(clusters=clusters, blocks=blocks))
    assert result["primary_gate"]["action"] == "Hold"
    assert reason in result["primary_gate"]["reasons"]


def test_equal_detection_is_uncertainty_not_proven_forgetting():
    rows = grid(outcomes=lambda *args: ("not_detected", "not_detected", "not_detected"))
    result = summarize(rows)
    assert result["primary_gate"]["action"] == "Hold"
    assert result["primary_gate"]["bad_detection_lower_bound"] == 0
    assert not result["draw_vs_artifact"]["causal_forgetting_established"]


def test_lost_single_draw_can_coexist_with_better_artifact_mean():
    result = summarize(grid(outcomes=outcome_pair))
    diagnostic = result["draw_vs_artifact"]
    assert diagnostic["lost_draw_count"] == 6
    assert diagnostic["lost_draw_but_mean_not_lower_count"] == 6
    assert diagnostic["artifact_mean_regression_count"] == 0
    assert result["primary_gate"]["action"] == "Support"


def test_equal_artifact_means_despite_draw_reversal():
    def outcomes(cluster, truth, variant, block):
        if truth == "good":
            return "not_detected", "not_detected", "not_detected"
        return ("detected" if block < 2 else "not_detected", "not_detected",
                "not_detected" if block < 2 else "detected")

    result = summarize(grid(outcomes=outcomes))
    assert result["draw_vs_artifact"]["lost_draw_count"] == 12
    assert result["draw_vs_artifact"]["lost_draw_but_mean_not_lower_count"] == 6
    assert all(row["mean_delta"] == 0 for row in result["draw_vs_artifact"]["artifact_rates"])


def test_unknowns_remain_in_all_attempt_detection_denominator():
    def outcomes(cluster, truth, variant, block):
        if truth == "good":
            return "not_detected", "not_detected", "not_detected"
        return "unknown", "unknown", "detected" if block == 0 else "unknown"

    result = summarize(grid(outcomes=outcomes))
    metrics = result["policy_summary"]["new_single"]["metrics"]
    assert metrics["bad_detection"]["cluster_mean"] == 0.25
    assert metrics["unknown_bad"]["cluster_mean"] == 0.75
    assert result["policy_summary"]["old_single"]["metrics"]["bad_detection"]["cluster_mean"] == 0


def test_parameter_variants_do_not_inflate_independent_cluster_weight():
    def outcomes(cluster, truth, variant, block):
        return "not_detected", "not_detected", "detected" if truth == "bad" and cluster == 0 else "not_detected"

    ordinary = summarize(grid(outcomes=outcomes))
    many_variants = summarize(grid(variants={(0, "bad"): 30}, outcomes=outcomes))
    def metric(result):
        return result["policy_summary"]["portfolio"]["metrics"]["bad_detection"]["cluster_mean"]
    assert metric(ordinary) == metric(many_variants) == 1 / 6
    assert many_variants["design"]["clusters"] == 6
    assert many_variants["comparisons"]["portfolio_vs_old_double"]["metrics"]["bad_detection"]["sign_flip"]["assignments"] == 64


def test_new_artifact_false_rejection_blocks_apparent_benefit():
    def outcomes(cluster, truth, variant, block):
        return "not_detected", "not_detected", "detected" if truth == "bad" or (cluster == 0 and block == 0) else "not_detected"

    result = summarize(grid(outcomes=outcomes))
    assert result["primary_gate"]["action"] == "Reject"
    assert len(result["primary_gate"]["new_false_rejections"]) == 1
    assert result["primary_gate"]["new_false_rejections"][0]["new_rate"] == 0.25


def test_existing_false_rejection_rate_cannot_worsen_unnoticed():
    def outcomes(cluster, truth, variant, block):
        if truth == "good" and cluster == 0:
            return "not_detected", "detected" if block == 0 else "not_detected", "detected"
        return "not_detected", "not_detected", "detected" if truth == "bad" else "not_detected"

    result = summarize(grid(outcomes=outcomes))
    regression = result["primary_gate"]["new_false_rejections"][0]
    assert regression["old_rate"] == 0.25 and regression["new_rate"] == 1
    assert regression["newly_affected_artifact"] is False


def test_false_positive_draw_flip_without_rate_increase_is_diagnostic_only():
    def outcomes(cluster, truth, variant, block):
        if truth == "good" and cluster == 0:
            return "not_detected", "detected" if block == 0 else "not_detected", "detected" if block == 1 else "not_detected"
        return "not_detected", "not_detected", "detected" if truth == "bad" else "not_detected"

    result = summarize(grid(outcomes=outcomes))
    assert result["primary_gate"]["action"] == "Support"
    assert result["primary_gate"]["new_false_rejections"] == []
    assert len(result["primary_gate"]["new_false_rejection_draws_diagnostic"]) == 1


def test_class_specific_unknown_rise_is_not_hidden_by_other_class_improvement():
    def outcomes(cluster, truth, variant, block):
        if cluster == 0 and truth == "good":
            return "unknown", "not_detected", "unknown"
        if cluster == 0 and truth == "bad":
            return "unknown", "unknown", "detected"
        return "not_detected", "not_detected", "detected" if truth == "bad" else "not_detected"

    result = summarize(grid(outcomes=outcomes))
    assert result["primary_gate"]["action"] == "Reject"
    assert result["primary_gate"]["unknown_increases"] == [{"cluster_id": "project0", "metric": "unknown_good", "delta": 1.0}]


def test_each_cluster_needs_both_truths_for_favorable_gate():
    rows = [row for row in grid() if not (row["cluster_id"] == "project0" and row["truth"] == "good")]
    result = summarize(rows)
    assert result["primary_gate"]["action"] == "Hold"
    assert "each_cluster_requires_both_oracle_truths" in result["primary_gate"]["reasons"]


def test_actual_unique_probe_calls_not_policy_references():
    result = summarize(grid())
    cost = result["cost_audit"]
    assert cost["unique_probe_requests"] == cost["expected_unique_requests"] == 12 * 4 * 3
    assert cost["logical_policy_request_references"] == 12 * 4 * 6
    assert result["comparisons"]["portfolio_vs_old_double"]["equal_model_call_budget"]
    assert not result["comparisons"]["old_double_vs_old_single"]["equal_model_call_budget"]


def test_missing_single_position_rejected_not_ignored():
    with pytest.raises(ValueError, match="Incomplete paired grid"):
        summarize(grid()[:-1])


@pytest.mark.parametrize("remove", ["artifact", "block"])
def test_whole_missing_artifact_or_block_detected_against_frozen_design(remove):
    rows = grid()
    expected = {row["artifact_id"]: {"cluster_id": row["cluster_id"], "truth": row["truth"]} for row in rows}
    reduced = [row for row in rows if row["artifact_id"] != rows[0]["artifact_id"]] if remove == "artifact" else [row for row in rows if row["block"] != 0]
    with pytest.raises(ValueError, match="preregistered design"):
        summarize_validator(reduced, expected_artifacts=expected, expected_blocks=[0, 1, 2, 3], bootstrap_samples=100)


@pytest.mark.parametrize("field,value", [("truth", "bad"), ("cluster_id", "another_project")])
def test_oracle_and_cluster_identity_cannot_change(field, value):
    rows = grid()
    rows[0][field] = value
    with pytest.raises(ValueError, match="truth or project cluster"):
        summarize(rows)


def test_duplicate_observation_rejected():
    rows = grid()
    with pytest.raises(ValueError, match="Duplicate"):
        summarize(rows + [deepcopy(rows[0])])


def test_request_alias_across_blocks_cannot_count_as_repeated_execution():
    rows = grid()
    target = next(row for row in rows if row["block"] == 1 and row["policy"] == "old_single")
    target["probe_request_hashes"] = rows[0]["probe_request_hashes"]
    with pytest.raises(ValueError, match="aliases"):
        summarize(rows)


def test_request_alias_across_variants_cannot_count_as_independent_artifacts():
    rows = grid()
    target = next(row for row in rows if row["artifact_id"] != rows[0]["artifact_id"])
    target["probe_request_hashes"] = rows[0]["probe_request_hashes"]
    with pytest.raises(ValueError, match="aliases"):
        summarize(rows)


def test_primary_cost_control_cannot_reuse_same_call_twice():
    rows = grid()
    double = next(row for row in rows if row["policy"] == "old_double")
    double["probe_request_hashes"] = [double["probe_request_hashes"][0]] * 2
    with pytest.raises(ValueError, match="distinct actual"):
        summarize(rows)


def test_portfolio_must_use_exact_shared_old_a_and_new():
    rows = grid()
    portfolio = next(row for row in rows if row["policy"] == "portfolio")
    portfolio["probe_request_hashes"][-1] = digest("not the preregistered new request")
    with pytest.raises(ValueError, match="old_a.old_b versus old_a.new"):
        summarize(rows)


def test_union_outcome_must_preserve_actual_constituent_detection():
    rows = grid()
    target = next(row for row in rows if row["truth"] == "bad" and row["policy"] == "portfolio")
    target["outcome"] = "not_detected"
    with pytest.raises(ValueError, match="Portfolio lost a detection"):
        summarize(rows)


@pytest.mark.parametrize("field,value", [("block", True), ("truth", "unknown"), ("outcome", "pass"),
                                       ("policy", "replacement"), ("input_count", 5),
                                       ("probe_request_hashes", ["not-a-hash"])])
def test_malformed_observation_rejected(field, value):
    rows = grid()
    rows[0][field] = value
    with pytest.raises(ValueError):
        summarize(rows)


def test_all_good_or_all_bad_reports_missing_metric_not_zero():
    rows = [row for row in grid() if row["truth"] == "bad"]
    result = summarize(rows)
    assert result["policy_summary"]["portfolio"]["metrics"]["good_false_rejection"]["cluster_mean"] is None
    assert result["primary_gate"]["action"] == "Hold"


@pytest.mark.parametrize("kwargs", [{"bootstrap_samples": 1}, {"bootstrap_samples": True}, {"seed": -1}, {"seed": True}])
def test_bootstrap_settings_are_explicit_and_bounded(kwargs):
    with pytest.raises(ValueError):
        summarize_validator(grid(), **kwargs)


def test_cluster_inference_uses_only_supplied_independent_family_deltas():
    values = {f"family{index}": 0.5 for index in range(9)}
    result = cluster_inference(values, bootstrap_samples=200)
    assert result["clusters"] == 9
    assert result["mean_delta"] == 0.5
    assert result["ci95"] == {"low": 0.5, "high": 0.5}
    assert result["exact_sign_flip_p"] == 2 / 512
    assert result["few_clusters_descriptive_only"]
    assert result["within_family_averaging_required"]
    assert result == cluster_inference(dict(reversed(list(values.items()))), bootstrap_samples=200)


@pytest.mark.parametrize("values", [{}, {"family": float("nan")}, {"family": float("inf")},
                                    {"family": True}, {"": 0.1}, {"family": "0.1"}])
def test_cluster_inference_invalid_input_rejected(values):
    with pytest.raises(ValueError):
        cluster_inference(values, bootstrap_samples=100)


def test_single_cluster_interval_does_not_imply_population_certainty():
    result = cluster_inference({"only_family": 0.3}, bootstrap_samples=100)
    assert result["ci95"] == {"low": 0.3, "high": 0.3}
    assert result["exact_sign_flip_p"] == 1
    assert result["few_clusters_descriptive_only"]
    assert result["causal_or_safety_claim"] is False


def test_small_cluster_bootstrap_significance_disagreement_is_explicit():
    result = cluster_inference({f"family{index}": int(index < 3) for index in range(6)}, bootstrap_samples=10000)
    assert result["ci95"]["low"] > 0
    assert result["exact_sign_flip_p"] == 0.25
    assert result["bootstrap_excludes_zero_but_exact_p_gt_05"]
