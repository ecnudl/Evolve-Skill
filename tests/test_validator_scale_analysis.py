"""Offline mathematical/provenance checks; no models, generated code, or network."""

from __future__ import annotations

import copy
import json
import random

import pytest

from skillopt.validator_scale_analysis import ARMS, _bootstrap, analyze


def task(identity, family, split="holdout"):
    return {"id": identity, "family": family, "cluster_id": family, "split": split}


def response(meta, arm, repeat, hard):
    return {**meta, "arm": arm, "repeat": repeat, "target_ok": True,
            "execution_ok": True, "hard": hard, "format_ok": True, "public_ok": True,
            "request_hash": f"request-{meta['id']}-{arm}-{repeat}"}


def matrix(manifest, outcomes, repeats=(0, 1, 2, 3)):
    return [response(meta, arm, repeat, outcomes(meta, arm, repeat))
            for meta in manifest for arm in ARMS for repeat in repeats]


def audit(rows, manifest=None, **overrides):
    options = {"task_manifest": manifest, "bootstrap_draws": 200,
               "subsample_draws": 30, "subsample_sizes": (1, 2, 5)}
    options.update(overrides)
    return analyze(rows, **options)


def primary(report, split="holdout"):
    return report["splits"][split]["contrasts"]["mechanism_skill_vs_noskill"]


def test_canonical_design_is_32_tasks_eight_families_not_384_independent_samples():
    manifest = [task(f"T{family}-{index}", f"F{family}", "dev" if family < 4 else "holdout")
                for family in range(8) for index in range(4)]
    rows = matrix(manifest, lambda meta, arm, repeat: (int(meta["id"][-1]) + repeat) % 2 == 0)
    result = analyze(rows, task_manifest=manifest)
    assert result["design"]["n_expected_tasks"] == 32
    assert result["design"]["n_expected_rows"] == 384
    assert result["design"]["n_family_clusters"] == 8
    assert result["design"]["n_distinct_request_hashes"] == 384
    assert not result["design"]["fresh_call_provenance_warning"]
    for split in ("dev", "holdout"):
        data = result["splits"][split]
        assert data["n_expected_tasks"] == 16
        assert data["n_family_clusters"] == 4
        assert data["n_expected_responses"] == 192
        assert data["arms"]["noskill"]["hard_passes"] == 32
        assert data["arms"]["noskill"]["hard_failures"] == 32
        boot = primary(result, split)["family_cluster_bootstrap"]
        assert boot["n_clusters"] == 4
        assert boot["draws"] == 10000
        assert boot["few_cluster_warning"]
        assert boot["established_equivalence"] is False
        assert boot["independent_replication_required"]
        diagnostic = primary(result, split)["task_batch_subsampling"]
        assert diagnostic["sizes"]["20"]["status"] == "insufficient_complete_tasks"
        assert diagnostic["sizes"]["32"]["draws_executed"] == 0
    full = primary(result, "all")["task_batch_subsampling"]
    assert full["sizes"]["32"]["draws_executed"] == 2000
    assert full["sizes"]["32"]["families_per_draw_min_max"] == [8, 8]
    assert full["sizes"]["32"]["macro_family_delta"]["zero_fraction"] == 1
    json.dumps(result, allow_nan=False)


def test_family_macro_is_primary_and_different_from_task_micro():
    manifest = [task("A", "one"), *(task(f"B{i}", "three") for i in range(3))]
    rows = matrix(manifest, lambda meta, arm, repeat: (meta["family"] == "one")
                  if arm == "mechanism_skill" else (meta["family"] == "three"))
    data = primary(audit(rows, manifest))
    assert data["primary_macro_family_delta"] == 0
    assert data["micro_task_delta"] == -.5
    assert data["micro_response_delta"] == -.5
    assert data["family_deltas"] == {"one": 1., "three": -1.}
    assert data["task_discordance"] == {"wins": 1, "losses": 3, "ties": 0, "unavailable_tasks": 0}


def test_repeating_identical_outcomes_does_not_create_more_bootstrap_clusters():
    manifest = [task(f"T{i}", f"F{i}") for i in range(4)]
    def outcomes(meta, arm, repeat):
        return (int(meta["id"][1:]) < 2) if arm == "mechanism_skill" else False

    once = primary(audit(matrix(manifest, outcomes, (0,)), manifest, expected_repeats=(0,)))
    four = primary(audit(matrix(manifest, outcomes), manifest))
    assert once["family_cluster_bootstrap"] == four["family_cluster_bootstrap"]
    assert once["n_matched_pairs"] == 4
    assert four["n_matched_pairs"] == 16
    assert once["family_cluster_bootstrap"]["n_clusters"] == 4


def test_zero_crossing_is_not_equivalence():
    stats = _bootstrap({"F0": -1., "F1": -1., "F2": 1., "F3": 1.}, 10000, 42, .10, True)
    assert stats["ci95"][0] < 0 < stats["ci95"][1]
    assert not stats["equivalence_interval_inside_margin"]
    assert not stats["exploratory_compatible_with_margin"]
    assert not stats["established_equivalence"]


def test_narrow_interval_is_only_exploratory_and_requires_replication():
    stats = _bootstrap(dict.fromkeys(("F0", "F1", "F2", "F3"), 0.), 10000, 42, .10, True)
    assert stats["ci90"] == [0., 0.]
    assert stats["equivalence_interval_inside_margin"]
    assert stats["exploratory_compatible_with_margin"]
    assert stats["bootstrap_distribution_degenerate"]
    assert stats["few_cluster_warning"]
    assert not stats["established_equivalence"]
    assert stats["independent_replication_required"]


def test_equivalence_requires_strict_margin_and_complete_pairs():
    at_boundary = _bootstrap({"A": .10, "B": .10}, 100, 42, .10, True)
    assert not at_boundary["equivalence_interval_inside_margin"]
    incomplete = _bootstrap({"A": 0., "B": 0.}, 100, 42, .10, False)
    assert incomplete["equivalence_interval_inside_margin"]
    assert not incomplete["exploratory_compatible_with_margin"]


@pytest.mark.parametrize("families", [{}, {"one": 1.}])
def test_less_than_two_clusters_has_no_bootstrap_interval(families):
    stats = _bootstrap(families, 100, 42, .10, True)
    assert stats["status"] == "insufficient_family_clusters"
    assert stats["ci90"] is None
    assert stats["ci95"] is None


def test_manifest_exposes_wholly_absent_tasks_and_missing_is_not_a_failure():
    manifest = [task("seen", "A"), task("absent", "B")]
    rows = [response(manifest[0], "mechanism_skill", 0, True)]
    result = audit(rows, manifest, expected_repeats=(0,))
    arm = result["splits"]["holdout"]["arms"]["mechanism_skill"]
    assert arm["n_expected_responses"] == 2
    assert arm["hard_passes"] == 1
    assert arm["hard_failures"] == 0
    assert arm["missingness"]["missing_row"] == 1
    assert arm["macro_family_mean"] == 1
    assert arm["full_expected_matrix_missingness_bounds"] == {
        "lower_macro_family_mean": .5, "upper_macro_family_mean": 1., "not_confidence_interval": True}
    data = primary(result)
    assert data["n_matched_pairs"] == 0
    assert data["n_missing_pairs"] == 2
    assert data["primary_macro_family_delta"] is None
    assert data["task_discordance"]["unavailable_tasks"] == 2
    bounds = data["full_expected_matrix_missingness_bounds"]
    assert bounds["lower_macro_family_delta"] == -.5
    assert bounds["upper_macro_family_delta"] == 1.


def test_missing_pairs_do_not_use_difference_of_unpaired_arm_means():
    manifest = [task("T", "F")]
    rows = [response(manifest[0], "mechanism_skill", 0, True),
            response(manifest[0], "noskill", 0, False),
            response(manifest[0], "noskill", 1, True)]
    result = audit(rows, manifest, expected_repeats=(0, 1))
    arms = result["splits"]["holdout"]["arms"]
    unpaired_difference = arms["mechanism_skill"]["macro_family_mean"] - arms["noskill"]["macro_family_mean"]
    assert unpaired_difference == .5
    paired = primary(result)
    assert paired["primary_macro_family_delta"] == 1
    assert paired["n_matched_pairs"] == 1
    assert paired["missing_pairs"] == [{"id": "T", "family": "F", "repeat": 1,
                                         "candidate_status": "missing_row", "reference_status": "observable"}]
    assert paired["per_global_replicate"][1]["macro_family_mean"] is None


def test_unavailable_hard_values_are_audited_but_not_scored():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda meta, arm, repeat: True)
    for row in rows:
        if row["arm"] != "mechanism_skill":
            continue
        if row["repeat"] == 0:
            row["target_ok"] = False
        elif row["repeat"] == 1:
            row["execution_ok"] = False
        elif row["repeat"] == 2:
            row["hard"] = None
    result = audit(rows, manifest)
    arm = result["splits"]["holdout"]["arms"]["mechanism_skill"]
    assert arm["hard_passes"] == 1
    assert arm["hard_failures"] == 0
    assert arm["missingness"] == {"missing_row": 0, "target_api_error": 1,
                                  "execution_unavailable": 1, "missing_hard": 1,
                                  "unusable_populated_hard": 2}
    assert arm["format_ok"]["observed"] == 3
    assert arm["public_ok"]["observed"] == 2
    paired = primary(result)
    assert paired["n_matched_pairs"] == 1
    assert paired["n_missing_pairs"] == 3
    assert paired["full_expected_matrix_missingness_bounds"]["lower_macro_family_delta"] == -.75
    assert paired["full_expected_matrix_missingness_bounds"]["upper_macro_family_delta"] == 0.


def test_global_replicates_and_task_instability_are_not_pooled_away():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda meta, arm, repeat: repeat % 2 == (0 if arm == "mechanism_skill" else 1))
    result = audit(rows, manifest)
    data = primary(result)
    assert [r["macro_family_mean"] for r in data["per_global_replicate"]] == [1., -1., 1., -1.]
    assert data["replicate_effect_range"] == [-1., 1.]
    assert data["replicate_effect_sample_sd"] == pytest.approx(1.1547005383792515)
    assert data["tasks"][0]["repeat_sign_changes"]
    assert data["task_discordance"]["ties"] == 1
    assert data["response_pair_discordance"] == {"wins": 2, "losses": 2, "ties": 0}
    instability = result["splits"]["holdout"]["arms"]["mechanism_skill"]["repeat_instability"]
    assert instability["mixed_task_fraction"] == 1.
    assert instability["mean_task_pairwise_disagreement"] == pytest.approx(2 / 3)


def test_task_first_weighting_survives_unequal_available_repeat_counts():
    manifest = [task("A", "F"), task("B", "F")]
    rows = []
    for meta in manifest:
        for repeat in ((0,) if meta["id"] == "A" else (0, 1, 2, 3)):
            for arm in ARMS:
                rows.append(response(meta, arm, repeat, (meta["id"] == "A") if arm == "mechanism_skill" else False))
    data = primary(audit(rows, manifest))
    assert data["primary_macro_family_delta"] == .5
    assert data["micro_task_delta"] == .5
    assert data["micro_response_delta"] == .2


def test_subsamples_are_without_replacement_and_full_size_is_fixed():
    manifest = [task(f"T{i}", f"F{i // 2}") for i in range(4)]
    rows = matrix(manifest, lambda meta, arm, repeat: arm == "mechanism_skill" and meta["id"] == "T0")
    result = audit(rows, manifest, subsample_sizes=(1, 4, 5), subsample_draws=200)
    samples = primary(result)["task_batch_subsampling"]
    assert samples["not_new_evidence"]
    full = samples["sizes"]["4"]
    assert full["without_replacement_within_draw"]
    assert full["families_per_draw_min_max"] == [2, 2]
    assert set(full["macro_family_delta"]["percentiles"].values()) == {.25}
    assert full["macro_family_delta"]["positive_fraction"] == 1.
    tiny = samples["sizes"]["1"]["macro_family_delta"]
    assert 0 < tiny["zero_fraction"] < 1
    assert tiny["negative_fraction"] == 0
    assert tiny["positive_fraction"] + tiny["zero_fraction"] == 1
    assert samples["sizes"]["5"]["draws_executed"] == 0


def test_subsample_complete_pool_is_shared_between_both_contrasts():
    manifest = [task("A", "F0"), task("B", "F1")]
    rows = matrix(manifest, lambda meta, arm, repeat: True)
    rows = [row for row in rows if not (row["id"] == "B" and row["arm"] == "generic_control" and row["repeat"] == 0)]
    result = audit(rows, manifest)
    comparisons = result["splits"]["holdout"]["contrasts"]
    for data in comparisons.values():
        assert data["task_batch_subsampling"]["pool_task_ids"] == ["A"]
        assert data["task_batch_subsampling"]["excluded_incomplete_task_count"] == 1
    assert primary(result)["n_missing_pairs"] == 0


def test_input_order_does_not_change_fixed_seed_outputs():
    manifest = [task(f"T{i}", f"F{i // 2}") for i in range(8)]
    rows = matrix(manifest, lambda meta, arm, repeat: (int(meta["id"][1:]) + ARMS.index(arm) + repeat) % 3 == 0)
    first = audit(rows, manifest)
    shuffled = copy.deepcopy(rows)
    random.Random(7).shuffle(shuffled)
    second = audit(shuffled, list(reversed(manifest)))
    assert first == second
    json.dumps(first, allow_nan=False)


def test_without_manifest_absence_limit_is_explicit_and_empty_scopes_are_json_safe():
    result = audit([])
    assert result["design"]["absence_limit"]
    assert result["design"]["n_expected_tasks"] == 0
    assert primary(result)["primary_macro_family_delta"] is None
    json.dumps(result, allow_nan=False)


def test_reused_request_hashes_raise_provenance_warning():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda meta, arm, repeat: True)
    rows[1]["request_hash"] = rows[0]["request_hash"]
    result = audit(rows, manifest)
    assert result["design"]["fresh_call_provenance_warning"]
    assert result["design"]["n_distinct_request_hashes"] == 11
    assert result["design"]["reused_request_hash_counts"] == {rows[0]["request_hash"]: 2}


@pytest.mark.parametrize("mutation", [
    {"hard": 1}, {"hard": "false"}, {"target_ok": None}, {"execution_ok": 1},
    {"format_ok": 1}, {"public_ok": "true"}, {"request_hash": ""},
    {"repeat": True}, {"repeat": 4}, {"arm": "candidate"}, {"split": "train"},
])
def test_malformed_response_is_rejected(mutation):
    meta = task("T", "F")
    row = response(meta, "noskill", 0, True)
    row.update(mutation)
    with pytest.raises(ValueError):
        audit([row])


def test_duplicate_response_and_manifest_rejected():
    meta = task("T", "F")
    row = response(meta, "noskill", 0, True)
    with pytest.raises(ValueError, match="Duplicate"):
        audit([row, row], [meta])
    with pytest.raises(ValueError, match="unique"):
        audit([row], [meta, meta])


def test_unknown_task_inconsistent_metadata_and_cross_split_family_rejected():
    meta = task("T", "F")
    with pytest.raises(ValueError, match="absent"):
        audit([response(meta, "noskill", 0, True)], [])
    with pytest.raises(ValueError, match="inconsistent"):
        audit([response(task("T", "changed"), "noskill", 0, True)], [meta])
    with pytest.raises(ValueError, match="cannot cross"):
        audit([], [meta, task("other", "F", "dev")])


@pytest.mark.parametrize("options", [
    {"expected_arms": ("noskill", "mechanism_skill")},
    {"expected_repeats": ()}, {"expected_repeats": (0, 0)}, {"expected_repeats": (True,)},
    {"bootstrap_draws": 0}, {"subsample_draws": True}, {"bootstrap_seed": -1},
    {"subsample_sizes": (1, 1)}, {"subsample_sizes": (0,)},
    {"equivalence_margin": 0}, {"equivalence_margin": True}, {"equivalence_margin": float("nan")},
])
def test_invalid_protocol_options_rejected(options):
    with pytest.raises(ValueError):
        audit([], **options)
