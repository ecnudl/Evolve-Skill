"""Handwritten complete-grid and weighting tests; no model, task file, or child."""

import copy
import itertools
import math

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.coevolution_v12 import analysis as a
from skillopt.validator_pilot.api import digest


def score(success=1, *, oracle=True, delivery=True, category=None):
    value = {"all_attempt_success": success, "oracle_available": oracle, "delivery_valid": delivery,
             "semantic_success": success if oracle else None}
    if category:
        value["category"] = category
    return value


def panel(*, counts=(4, 4, 4), variants=1, histories=3):
    expected, rows = {}, []
    for domain, count in zip(a.DOMAINS, counts):
        for family in range(count):
            for variant in range(variants):
                task = f"{domain}-{family}-{variant}"
                expected[task] = {"domain": domain, "cluster_id": f"family{family}"}
    for task, metadata in expected.items():
        for history in range(histories):
            for policy in a.POLICIES:
                raw = policy.removeprefix("selected_")
                skill = a.EMPTY_SKILL_HASH if raw == "no_skill" else digest([raw, history])
                rows.append({"task_id": task, **metadata, "history": history, "policy": policy,
                    "skill_hash": skill, "request_hashes": [digest([task, skill, stage]) for stage in (0, 1)],
                    "score": score()})
    return rows, expected


def change(rows, policy, value, *, domain=None, cluster=None, history=None, task=None):
    selected = {(row["task_id"], row["skill_hash"]) for row in rows
                if row["policy"] == policy and (domain is None or row["domain"] == domain)
                and (cluster is None or row["cluster_id"] == cluster)
                and (history is None or row["history"] == history) and (task is None or row["task_id"] == task)}
    for row in rows:
        if (row["task_id"], row["skill_hash"]) in selected:
            row["score"] = copy.deepcopy(value)


def summarize(rows, expected, **kwargs):
    return a.summarize(rows, expected, bootstrap_samples=100, **kwargs)


def test_complete_grid_sealed_and_alias_counts():
    rows, expected = panel()
    result = verify(summarize(rows, expected))
    assert result["task_instances"] == 12 and result["logical_rows"] == 180
    assert result["unique_trajectory_receipts"] == 84 and result["unique_request_hashes"] == 168
    assert result["aliased_rows_beyond_first_trajectory"] == 96
    assert result["structural_clusters_by_domain"] == dict.fromkeys(a.DOMAINS, 4)
    base = result["policy_summary"]["no_skill"]
    assert base["macro_all_attempt_success"] == 1 and base["nonempty_skill_coverage"] == 0
    assert result["policy_summary"]["contrastive"]["nonempty_skill_coverage"] == 1
    assert result["primary_endpoints"]["macro"]["holm_adjusted_p"] == 1
    assert not result["safety_or_noninferiority_certified"]
    assert not result["research_contribution_identified_by_this_comparison"]


def test_macro_domain_weights_are_not_pooled_cluster_weights():
    rows, expected = panel(counts=(4, 4, 8))
    for domain in ("coding", "spreadsheet"):
        change(rows, "independent", score(0), domain=domain)
    change(rows, "contrastive", score(0), domain="rule_reasoning")
    result = summarize(rows, expected)
    main = result["comparisons"]["contrastive_vs_independent"]
    assert main["macro"]["mean_delta"] == pytest.approx(1 / 3)
    assert main["macro"]["ci95"]["low"] == main["macro"]["ci95"]["high"] == pytest.approx(1 / 3)
    assert main["by_domain"]["rule_reasoning"]["mean_delta"] == -1
    # Domain weights are 1/3; family weights are 1/12, 1/12, and 1/24.
    extreme = sum(math.comb(8, i) * math.comb(8, j) for i in range(9) for j in range(9)
                  if abs(2 * (2 * i - 8) + (2 * j - 8)) >= 8)
    assert main["macro"]["p_two_sided"] == extreme / 2**16
    assert main["macro"]["sign_flip"]["exact"]


def test_task_variants_do_not_overweight_a_large_family():
    rows, expected = panel()
    template = [row for row in rows if row["task_id"] == "coding-0-0"]
    for variant in range(1, 20):
        task = f"coding-0-{variant}"
        expected[task] = {"domain": "coding", "cluster_id": "family0"}
        for source in template:
            row = copy.deepcopy(source)
            row["task_id"] = task
            row["request_hashes"] = [digest([task, row["skill_hash"], stage]) for stage in (0, 1)]
            rows.append(row)
    change(rows, "independent", score(0), domain="coding")
    change(rows, "independent", score(1), domain="coding", cluster="family0")
    change(rows, "contrastive", score(0), domain="coding", cluster="family0")
    main = summarize(rows, expected)["comparisons"]["contrastive_vs_independent"]
    assert main["by_domain"]["coding"]["mean_delta"] == 0.5
    assert main["macro"]["mean_delta"] == pytest.approx(1 / 6)
    assert main["counts"]["losses"] == 60 and main["counts"]["wins"] == 9


def test_history_repeats_averaged_inside_each_family_not_independent_samples():
    rows, expected = panel()
    change(rows, "independent", score(0), domain="coding", history=0)
    main = summarize(rows, expected)["comparisons"]["contrastive_vs_independent"]
    assert main["macro"]["mean_delta"] == pytest.approx(1 / 9)
    assert main["by_domain"]["coding"]["mean_delta"] == pytest.approx(1 / 3)
    assert main["macro"]["sign_flip"]["nonzero_cluster_differences"] == 4
    assert main["macro"]["p_two_sided"] == 0.125
    assert main["by_history"]["0"]["macro"] == pytest.approx(1 / 3)
    assert main["by_history"]["1"]["macro"] == 0


def test_exact_signflip_and_holm_two_primary_endpoints():
    rows, expected = panel()
    change(rows, "independent", score(0))
    result = summarize(rows, expected)
    primary = result["primary_endpoints"]
    assert primary["macro"]["p_two_sided"] == 2 / 4096
    assert primary["macro"]["holm_adjusted_p"] == 4 / 4096
    assert primary["macro"]["holm_reject_null"]
    assert primary["rule_reasoning"]["p_two_sided"] == 0.125
    assert primary["rule_reasoning"]["holm_adjusted_p"] == 0.125
    assert not primary["rule_reasoning"]["holm_reject_null"]


def test_no_skill_fallback_selected_diagnostic_does_not_replace_raw_comparison():
    rows, expected = panel()
    change(rows, "contrastive", score(0))
    base = {(r["task_id"], r["history"]): r for r in rows if r["policy"] == "no_skill"}
    for row in rows:
        if row["policy"] == "selected_contrastive":
            reference = base[row["task_id"], row["history"]]
            for field in ("skill_hash", "request_hashes", "score"):
                row[field] = copy.deepcopy(reference[field])
    result = summarize(rows, expected)
    assert result["comparisons"]["contrastive_vs_independent"]["macro"]["mean_delta"] == -1
    assert result["policy_summary"]["selected_contrastive"]["nonempty_skill_coverage"] == 0
    assert result["comparisons"]["selected_contrastive_vs_no_skill"]["macro"]["mean_delta"] == 0
    assert result["comparisons"]["selected_contrastive_vs_selected_independent"]["selected_policy_diagnostic_only"]
    assert result["primary_endpoints"]["macro"]["comparison"] == "contrastive_vs_independent"


def test_unknown_delivery_and_semantic_loss_counts_do_not_collapse():
    rows, expected = panel()
    change(rows, "contrastive", score(0, oracle=False, delivery=False, category="delivery"),
           domain="coding", cluster="family0", history=0)
    change(rows, "contrastive", score(0, oracle=False, delivery=True, category="infra"),
           domain="coding", cluster="family1", history=0)
    change(rows, "contrastive", score(0, category="evaluated_failure"),
           domain="coding", cluster="family2", history=0)
    result = summarize(rows, expected)
    counts = result["comparisons"]["contrastive_vs_no_skill"]["counts"]
    assert counts["losses"] == 3 and counts["wins"] == 0 and counts["paired_unknown"] == 2
    assert counts["delivery_losses"] == counts["confirmed_semantic_losses"] == counts["delivered_oracle_unknown_losses"] == 1
    rates = result["policy_summary"]["contrastive"]
    assert rates["unknown"] == 2 and rates["oracle_available"] == 34
    assert rates["delivery_invalid"] == rates["delivery_valid_oracle_unknown"] == 1
    assert rates["available_semantic_success_diagnostic"] == pytest.approx(33 / 34)


def test_base_unavailable_gains_not_all_called_semantic_improvements():
    rows, expected = panel()
    change(rows, "no_skill", score(0, oracle=False, delivery=False), task="coding-0-0")
    change(rows, "no_skill", score(0, oracle=False, delivery=True), task="coding-1-0")
    change(rows, "no_skill", score(0), task="coding-2-0")
    counts = summarize(rows, expected)["comparisons"]["contrastive_vs_no_skill"]["counts"]
    assert counts["wins"] == 9
    assert counts["confirmed_semantic_gains"] == counts["reference_delivery_failure_gains"] == counts["reference_oracle_unknown_gains"] == 3


def test_api_initial_failure_can_be_repaired_and_scored_successfully():
    rows, expected = panel()
    for row in rows:
        row.update(api_ok=False, stage_api_ok=[False, True])
    assert summarize(rows, expected)["policy_summary"]["contrastive"]["macro_all_attempt_success"] == 1


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows.append(copy.deepcopy(rows[0])),
    lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["task_id"] != "coding-0-0"]),
    lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["history"] != 2]),
])
def test_missing_duplicate_or_entire_missing_block_rejected(mutation):
    rows, expected = panel()
    mutation(rows)
    with pytest.raises(ValueError):
        summarize(rows, expected)


@pytest.mark.parametrize("field,value", [
    ("domain", "other"), ("cluster_id", "invented"), ("task_id", "other"), ("history", True), ("history", 9),
    ("skill_hash", "bad"), ("policy", "best_selected_after_final"), ("request_hashes", []),
    ("request_hashes", ["a" * 64]), ("request_hashes", ["a" * 64] * 2),
    ("request_hashes", ["bad", "b" * 64]),
])
def test_malformed_identity_or_request_grid_rejected(field, value):
    rows, expected = panel()
    rows[0][field] = value
    with pytest.raises(ValueError):
        summarize(rows, expected)


@pytest.mark.parametrize("value", [
    None, 1, {}, score(True), score(1, oracle=False), score(0, oracle=True, delivery=False),
    {**score(), "semantic_success": None}, {**score(), "semantic_success": True},
    {**score(), "semantic_success": 0}, {**score(), "all_attempt_success": float("nan")},
    {**score(), "all_attempt_success": 0.5}, {**score(), "oracle_available": 1},
    {**score(), "delivery_valid": 1}, {**score(), "category": ""},
])
def test_invalid_score_schema_rejected(value):
    rows, expected = panel()
    rows[0]["score"] = value
    with pytest.raises(ValueError):
        summarize(rows, expected)


def test_same_request_with_disagreeing_score_rejected():
    rows, expected = panel()
    rows[0]["score"] = score(0)
    with pytest.raises(ValueError, match="Aliased trajectories"):
        summarize(rows, expected)


def test_same_task_skill_cannot_create_another_independent_draw():
    rows, expected = panel()
    rows[0]["request_hashes"] = [digest(["new", i]) for i in (0, 1)]
    with pytest.raises(ValueError, match="Identical task/Skill"):
        summarize(rows, expected)


def test_stage_alias_or_cross_skill_alias_rejected():
    rows, expected = panel()
    row = next(r for r in rows if r["policy"] == "contrastive")
    row["request_hashes"][0] = rows[0]["request_hashes"][1]
    with pytest.raises(ValueError, match="another task, Skill, or trajectory stage"):
        summarize(rows, expected)


def test_policy_history_skill_cannot_drift_across_domains():
    rows, expected = panel()
    row = next(r for r in rows if r["policy"] == "contrastive" and r["domain"] == "spreadsheet")
    row["skill_hash"] = digest("changed")
    row["request_hashes"] = [digest(["changed", stage]) for stage in (0, 1)]
    with pytest.raises(ValueError, match="cannot change Skill"):
        summarize(rows, expected)


def test_no_skill_must_be_true_empty_text_not_placeholder():
    rows, expected = panel()
    for row in rows:
        if row["policy"] == "no_skill":
            row["skill_hash"] = digest("initial")
    with pytest.raises(ValueError, match="empty-text"):
        summarize(rows, expected)


@pytest.mark.parametrize("expected_value", [None, [], {}, {"t": {}}, {"t": {"domain": "coding", "cluster_id": "c"}}])
def test_expected_metadata_is_mandatory_and_structural(expected_value):
    rows, _ = panel()
    with pytest.raises(ValueError):
        summarize(rows, expected_value)


def test_small_engineering_smoke_cannot_emit_effect_decision():
    rows, expected = panel(counts=(1, 1, 1))
    change(rows, "independent", score(0))
    with pytest.raises(ValueError, match="minimum structural"):
        summarize(rows, expected)
    result = summarize(rows, expected, minimum_clusters=1)
    assert result["primary_endpoints"]["macro"]["engineering_smoke_not_effect_evidence"]
    assert not result["primary_endpoints"]["macro"]["holm_reject_null"]


@pytest.mark.parametrize("kwargs", [
    {"histories": 0}, {"histories": True}, {"histories": [0, 0]}, {"histories": [True]},
    {"policies": []}, {"policies": [*a.POLICIES[:-1], "independent"]},
    {"minimum_clusters": 0}, {"minimum_clusters": True}, {"minimum_clusters": 101},
    {"seed": -1}, {"seed": True},
])
def test_analysis_parameters_fail_closed(kwargs):
    rows, expected = panel()
    with pytest.raises(ValueError):
        summarize(rows, expected, **kwargs)


def test_deterministic_order_independent_and_nonmutating_results():
    rows, expected = panel()
    change(rows, "independent", score(0), domain="coding", history=0)
    frozen = copy.deepcopy(rows)
    first = summarize(rows, expected)
    second = summarize(list(reversed(rows)), dict(reversed(list(expected.items()))))
    assert first == second and rows == frozen


def test_weighted_sign_flip_matches_explicit_enumeration():
    values = [0.2, -0.1, 0.05, 0.0]
    observed = abs(sum(values))
    outcomes = [sum(sign * v for sign, v in zip(signs, values))
                for signs in itertools.product((-1, 1), repeat=len(values))]
    expected = sum(abs(v) >= observed - 1e-12 for v in outcomes) / len(outcomes)
    assert a._sign_flip(values, seed=3)["p_two_sided"] == expected
    assert a._sign_flip([0, 0], seed=3)["p_two_sided"] == 1


def test_large_family_panel_signflip_is_reproducible_monte_carlo_with_plus_one():
    first = a._sign_flip([0.1] * 17, seed=3)
    assert first == a._sign_flip([0.1] * 17, seed=3)
    assert not first["exact"] and first["assignments"] == 20000
    assert first["p_two_sided"] >= 1 / 20001
