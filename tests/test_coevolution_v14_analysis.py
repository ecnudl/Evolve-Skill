"""Handwritten complete block grids only; no model, task files, or execution."""

import copy

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.coevolution_v14 import analysis as a
from skillopt.validator_pilot.api import digest


def score(success=1, *, oracle=True, delivery=True, category=None):
    result = {"all_attempt_success": success, "oracle_available": oracle, "delivery_valid": delivery,
              "semantic_success": success if oracle else None}
    if category is not None:
        result["category"] = category
    return result


def panel(*, counts=(8, 8, 8), variants=1, histories=3):
    expected, rows = {}, []
    for domain, count in zip(a.DOMAINS, counts):
        for family in range(count):
            for variant in range(variants):
                task = f"{domain}-{family}-{variant}"
                expected[task] = {"domain": domain, "cluster_id": f"family{family}"}
    for task, metadata in expected.items():
        for history in range(histories):
            for policy in a.POLICIES:
                skill = a.EMPTY_SKILL_HASH if policy == "no_skill" else digest([policy, history])
                rows.append({"task_id": task, **metadata, "history": history, "policy": policy,
                    "skill_hash": skill, "request_hashes": [digest([task, history, skill, step]) for step in (0, 1)],
                    "score": score()})
    return rows, expected


def summarize(rows, expected, **kwargs):
    return a.summarize(rows, expected, bootstrap_samples=100, **kwargs)


def change(rows, policy, value, *, domain=None, cluster=None, history=None, task=None):
    identities = {(r["task_id"], r["history"], r["skill_hash"]) for r in rows
                  if r["policy"] == policy and (domain is None or r["domain"] == domain)
                  and (cluster is None or r["cluster_id"] == cluster)
                  and (history is None or r["history"] == history) and (task is None or r["task_id"] == task)}
    for row in rows:
        if (row["task_id"], row["history"], row["skill_hash"]) in identities:
            row["score"] = copy.deepcopy(value)


def alias_policy(rows, policy, reference):
    indexed = {(r["task_id"], r["history"]): r for r in rows if r["policy"] == reference}
    for row in rows:
        if row["policy"] == policy:
            target = indexed[row["task_id"], row["history"]]
            for key in ("skill_hash", "request_hashes", "score"):
                row[key] = copy.deepcopy(target[key])


def test_complete_grid_and_truly_separate_baseline_requests():
    rows, expected = panel()
    before = copy.deepcopy(rows)
    result = verify(summarize(rows, expected))
    assert result["task_instances"] == 24 and result["logical_rows"] == 216
    assert result["unique_trajectory_receipts"] == 216 and result["unique_request_hashes"] == 432
    assert result["aliased_rows_beyond_first_trajectory"] == 0
    assert result["no_skill_sampling"]["unique_trajectory_receipts"] == 72
    assert result["no_skill_sampling"]["unique_request_hashes"] == 144
    assert result["no_skill_sampling"]["trajectories_by_history"] == {"0": 24, "1": 24, "2": 24}
    assert result["structural_clusters_by_domain"] == dict.fromkeys(a.DOMAINS, 8)
    assert result["cross_history_request_aliases_forbidden"] and rows == before
    assert not result["safety_or_noninferiority_certified"]
    assert result["history_variation_mixes_skill_text_and_solver_sampling"]


def test_within_block_identical_skill_is_exact_alias_not_extra_cost():
    rows, expected = panel()
    alias_policy(rows, "constrained", "independent")
    result = summarize(rows, expected)
    assert result["logical_rows"] == 216 and result["unique_trajectory_receipts"] == 144
    assert result["aliased_rows_beyond_first_trajectory"] == 72
    assert result["comparisons"][a.PRIMARY_COMPARISON]["counts"]["ties"] == 72
    assert result["primary_endpoints"]["macro"]["p_two_sided"] == 1


def test_empty_candidate_can_alias_baseline_only_in_its_own_block():
    rows, expected = panel()
    alias_policy(rows, "constrained", "no_skill")
    result = summarize(rows, expected)
    assert result["policy_summary"]["constrained"]["nonempty_skill_coverage"] == 0
    assert result["unique_trajectory_receipts"] == 144
    assert result["no_skill_sampling"]["unique_trajectory_receipts"] == 72


@pytest.mark.parametrize("policy", a.POLICIES)
def test_complete_sequence_cannot_cross_history_even_if_scores_identical(policy):
    rows, expected = panel()
    previous = {(r["task_id"], r["policy"]): r for r in rows if r["history"] == 0}
    for row in rows:
        if row["history"] == 1 and row["policy"] == policy:
            source = previous[row["task_id"], policy]
            row["skill_hash"] = source["skill_hash"]
            row["request_hashes"] = source["request_hashes"][:]
    with pytest.raises(ValueError, match="history blocks"):
        summarize(rows, expected)


@pytest.mark.parametrize("step", [0, 1])
def test_single_stage_cannot_cross_history(step):
    rows, expected = panel()
    base = [r for r in rows if r["policy"] == "no_skill" and r["task_id"] == "coding-0-0"]
    base[1]["request_hashes"][step] = base[0]["request_hashes"][step]
    with pytest.raises(ValueError, match="history blocks"):
        summarize(rows, expected)


def test_same_text_across_blocks_still_gets_fresh_requests():
    rows, expected = panel()
    for row in rows:
        if row["policy"] != "no_skill":
            row["skill_hash"] = digest(row["policy"])
            row["request_hashes"] = [digest([row["task_id"], row["history"], row["skill_hash"], s]) for s in (0, 1)]
    result = summarize(rows, expected)
    assert result["unique_trajectory_receipts"] == 216


def test_real_baseline_block_outcomes_may_differ():
    rows, expected = panel()
    change(rows, "no_skill", score(0), history=1, domain="coding")
    result = summarize(rows, expected)
    baseline = result["policy_summary"]["no_skill"]
    assert baseline["by_history"]["0"]["macro"] == 1
    assert baseline["by_history"]["1"]["macro"] == pytest.approx(2 / 3)
    assert baseline["macro_all_attempt_success"] == pytest.approx(8 / 9)
    inferred = result["comparisons"]["constrained_vs_no_skill"]["macro"]
    assert inferred["mean_delta"] == pytest.approx(1 / 9)
    assert inferred["sign_flip"]["nonzero_cluster_differences"] == 8  # not 24 block/family positions


def test_primary_is_bundle_macro_and_sheet_not_rule_or_base():
    rows, expected = panel()
    change(rows, "independent", score(0), domain="spreadsheet")
    result = summarize(rows, expected)
    primary = result["primary_endpoints"]
    assert set(primary) == {"macro", "spreadsheet"}
    assert all(x["comparison"] == "constrained_vs_independent" for x in primary.values())
    assert primary["spreadsheet"]["p_two_sided"] == 2 / 2**8
    assert primary["spreadsheet"]["holm_adjusted_p"] == 4 / 2**8
    assert primary["spreadsheet"]["holm_reject_null"]
    assert primary["macro"]["holm_adjusted_p"] == 4 / 2**8
    comparisons = result["comparisons"]
    assert not comparisons[a.PRIMARY_COMPARISON]["exploratory_comparison"]
    assert comparisons["constrained_vs_no_skill"]["exploratory_comparison"]
    assert not comparisons[a.PRIMARY_COMPARISON]["by_domain"]["rule_reasoning"]["primary_endpoint"]


def test_macro_has_equal_domains_not_pooled_family_weights():
    rows, expected = panel(counts=(8, 8, 16))
    for domain in ("coding", "spreadsheet"):
        change(rows, "independent", score(0), domain=domain)
    change(rows, "constrained", score(0), domain="rule_reasoning")
    main = summarize(rows, expected)["comparisons"][a.PRIMARY_COMPARISON]
    assert main["macro"]["mean_delta"] == pytest.approx(1 / 3)
    assert main["macro"]["ci95"]["low"] == main["macro"]["ci95"]["high"] == pytest.approx(1 / 3)
    assert main["by_domain"]["rule_reasoning"]["mean_delta"] == -1
    assert not main["macro"]["sign_flip"]["exact"]
    assert main["macro"]["sign_flip"]["assignments"] == 20000


def test_extra_variants_do_not_overweight_a_family():
    rows, expected = panel()
    template = [r for r in rows if r["task_id"] == "coding-0-0"]
    for variant in range(1, 10):
        task = f"coding-0-{variant}"
        expected[task] = {"domain": "coding", "cluster_id": "family0"}
        for source in template:
            row = copy.deepcopy(source)
            row["task_id"] = task
            row["request_hashes"] = [digest([task, row["history"], row["skill_hash"], s]) for s in (0, 1)]
            rows.append(row)
    change(rows, "constrained", score(0), domain="coding", cluster="family0")
    result = summarize(rows, expected)
    assert result["comparisons"][a.PRIMARY_COMPARISON]["by_domain"]["coding"]["mean_delta"] == -1 / 8
    assert result["comparisons"][a.PRIMARY_COMPARISON]["macro"]["sign_flip"]["nonzero_cluster_differences"] == 1


def test_worst_absolute_domain_is_distinct_from_maximum_domain_drop():
    rows, expected = panel()
    change(rows, "no_skill", score(0), domain="coding")
    change(rows, "constrained", score(0), domain="spreadsheet", cluster="family0")
    result = summarize(rows, expected)
    summary = result["policy_summary"]["constrained"]
    assert summary["worst_domain_all_attempt_success"] == 7 / 8
    assert summary["maximum_domain_drop_vs_no_skill"] == 1 / 8
    assert summary["domain_deltas_vs_no_skill"]["coding"] == 1
    assert result["comparisons"]["constrained_vs_no_skill"]["negative_domain_fraction"] == 1 / 3


def test_delivery_unknown_and_evaluated_losses_are_separate():
    rows, expected = panel()
    change(rows, "constrained", score(0, oracle=False, delivery=False), task="coding-0-0", history=0)
    change(rows, "constrained", score(0, oracle=False), task="coding-1-0", history=0)
    change(rows, "constrained", score(0), task="coding-2-0", history=0)
    result = summarize(rows, expected)
    counts = result["comparisons"][a.PRIMARY_COMPARISON]["counts"]
    assert counts["losses"] == 3 and counts["paired_unknown"] == 2
    assert counts["delivery_losses"] == counts["delivered_oracle_unknown_losses"] == counts["confirmed_semantic_losses"] == 1
    summary = result["policy_summary"]["constrained"]
    assert summary["unknown"] == 2 and summary["oracle_available"] == 70
    assert summary["macro_all_attempt_success"] == pytest.approx(69 / 72)


def test_zero_width_zero_effect_is_not_equivalence_or_safety():
    rows, expected = panel()
    result = summarize(rows, expected)
    main = result["comparisons"][a.PRIMARY_COMPARISON]["macro"]
    assert main["ci95"] == {"low": 0, "high": 0} and main["p_two_sided"] == 1
    assert not main["safety_or_noninferiority_certified"]
    assert result["zero_width_bootstrap_interval_not_equivalence_or_safety"]
    assert not result["primary_endpoints"]["macro"]["holm_reject_null"]


def test_smoke_has_no_positive_inference_even_with_large_observed_effect():
    rows, expected = panel(counts=(4, 4, 4))
    change(rows, "independent", score(0))
    result = summarize(rows, expected, minimum_clusters=4)
    assert result["engineering_smoke_only"]
    assert not any(x["holm_reject_null"] for x in result["primary_endpoints"].values())


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows.append(copy.deepcopy(rows[0])),
    lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["history"] != 2]),
    lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["policy"] != "no_skill"]),
])
def test_incomplete_or_duplicate_grid_is_not_silently_dropped(mutation):
    rows, expected = panel()
    mutation(rows)
    with pytest.raises(ValueError, match="grid|Duplicate"):
        summarize(rows, expected)


@pytest.mark.parametrize("key,value", [("domain", "other"), ("cluster_id", "wrong"), ("task_id", "wrong"),
    ("history", True), ("history", 9), ("policy", "selected_constrained"), ("skill_hash", "unhashed")])
def test_identity_validation(key, value):
    rows, expected = panel()
    rows[0][key] = value
    with pytest.raises(ValueError):
        summarize(rows, expected)


def test_no_skill_cannot_be_placeholder_text():
    rows, expected = panel()
    rows[0]["skill_hash"] = digest("No skill")
    with pytest.raises(ValueError, match="empty-text"):
        summarize(rows, expected)


def test_policy_block_skill_cannot_change_by_domain():
    rows, expected = panel()
    row = next(r for r in rows if r["policy"] == "constrained" and r["domain"] == "spreadsheet")
    row["skill_hash"] = digest("changed")
    with pytest.raises(ValueError, match="same Skill"):
        summarize(rows, expected)


def test_within_block_alias_requires_matching_exact_score():
    rows, expected = panel()
    alias_policy(rows, "constrained", "independent")
    next(r for r in rows if r["policy"] == "constrained")["score"] = score(0)
    with pytest.raises(ValueError, match="Aliased trajectory"):
        summarize(rows, expected)


def test_same_text_same_block_cannot_be_rerun_under_another_policy():
    rows, expected = panel()
    for row in rows:
        if row["policy"] == "constrained":
            row["skill_hash"] = digest(["independent", row["history"]])
    with pytest.raises(ValueError, match="within one history"):
        summarize(rows, expected)


@pytest.mark.parametrize("raw", [
    {}, score(True), score(1, oracle=False), score(0, oracle=True, delivery=False),
    {**score(0, oracle=False), "semantic_success": 0}, {**score(), "oracle_available": 1},
])
def test_invalid_scores_cannot_create_semantic_evidence(raw):
    rows, expected = panel()
    rows[0]["score"] = raw
    with pytest.raises(ValueError):
        summarize(rows, expected)


def test_first_api_failure_does_not_force_final_unknown():
    rows, expected = panel()
    rows[0].update(api_ok=False, stage_api_ok=[False, True])
    result = summarize(rows, expected)
    assert result["policy_summary"]["no_skill"]["macro_all_attempt_success"] == 1


@pytest.mark.parametrize("histories", [0, True, -1, [], [0, 0], [True], "3"])
def test_invalid_history_blocks(histories):
    rows, expected = panel()
    with pytest.raises(ValueError):
        summarize(rows, expected, histories=histories)


def test_explicit_history_ids_and_row_order_are_reproducible():
    rows, expected = panel()
    change(rows, "independent", score(0), domain="coding", cluster="family0", history=1)
    first = summarize(rows, expected, histories=[2, 1, 0])
    assert first == summarize(list(reversed(rows)), expected, histories=[0, 1, 2])


@pytest.mark.parametrize("keyword,value", [("minimum_clusters", 0), ("minimum_clusters", True),
    ("bootstrap_samples", 99), ("bootstrap_samples", True), ("seed", -1), ("seed", True),
    ("policies", ["no_skill", "independent", "selected_independent"])])
def test_analysis_parameter_bounds(keyword, value):
    rows, expected = panel()
    kwargs = {"bootstrap_samples": 100, keyword: value}
    with pytest.raises(ValueError):
        a.summarize(rows, expected, **kwargs)


def test_default_eight_families_cannot_be_satisfied_with_extra_variants():
    rows, expected = panel(counts=(7, 8, 8), variants=2)
    with pytest.raises(ValueError, match="family minimum"):
        summarize(rows, expected)
