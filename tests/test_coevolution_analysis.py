"""Synthetic-only final-policy statistics; no API, files, or candidate execution."""

import copy
import json
import random

import pytest

from skillopt.coevolution.analysis import ARMS, analyze


def task(identity, cluster, context="coding", mode="applicable"):
    return {"id": identity, "cluster_id": cluster, "family": cluster, "context": context, "mode": mode}


def matrix(manifest, outcome, streams=(0, 1), repeats=(0, 1, 2), arms=ARMS):
    return [{**meta, "stream": stream, "arm": arm, "repeat": repeat,
             "target_ok": True, "execution_ok": True,
             "hard": outcome(meta, stream, arm, repeat), "skill_active": arm != "noskill",
             "skill_hash": f"skill-{stream}-{arm}", "request_hash": f"call-{meta['id']}-{stream}-{arm}-{repeat}"}
            for meta in manifest for stream in streams for arm in arms for repeat in repeats]


def audit(rows, manifest, **kwargs):
    return analyze(rows, task_manifest=manifest, bootstrap_draws=kwargs.pop("bootstrap_draws", 100), **kwargs)


def primary(result):
    return result["contrasts"]["evolving_validator_vs_fixed_validator"]


def test_canonical_24_task_design_keeps_twelve_clusters_not_432_independent_units():
    manifest = [task(f"T{i:02}", f"F{i // 2:02}", context="coding" if i < 12 else "tables",
                     mode="applicable" if i % 2 == 0 else "near_miss") for i in range(24)]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: True)
    result = analyze(rows, task_manifest=manifest)
    assert result["design"]["n_expected_rows"] == 432
    assert result["design"]["n_observed_rows"] == 432
    assert result["design"]["n_distinct_request_hashes"] == 432
    assert result["n_expected_tasks"] == 24
    assert result["n_expected_clusters"] == 12
    for arm in ARMS:
        assert result["arms"][arm]["hard_passes"] == 144
        assert result["arms"][arm]["hard_failures"] == 0
        assert result["arms"][arm]["macro_cluster_mean"] == 1.
    data = primary(result)
    assert data["primary_macro_cluster_delta"] == 0
    assert data["n_matched_pairs"] == 144
    assert data["n_missing_pairs"] == 0
    boot = data["family_cluster_bootstrap"]
    assert boot["n_clusters"] == 12
    assert boot["draws"] == 5000
    assert boot["seed"] == 20260909
    assert boot["ci95"] == [0., 0.]
    assert boot["degenerate_distribution"]
    assert not boot["equivalence_tested"]
    assert not boot["equivalence_established"]
    assert not boot["independent_stream_variance_established"]
    assert result["by_context"]["coding"]["n_expected_tasks"] == 12
    assert result["by_mode"]["near_miss"]["n_expected_tasks"] == 12
    assert result["by_context"]["coding"]["contrasts"]["evolving_validator_vs_fixed_validator"]["family_cluster_bootstrap"] is None
    json.dumps(result, allow_nan=False)


def test_family_macro_differs_from_task_micro_when_cluster_sizes_differ():
    manifest = [task("A", "one"), *(task(f"B{i}", "three") for i in range(3))]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: meta["family"] == "one"
                  if arm == "evolving_validator" else meta["family"] == "three")
    data = primary(audit(rows, manifest))
    assert data["primary_macro_cluster_delta"] == 0
    assert data["micro_task_delta"] == -.5
    assert data["micro_matched_response_delta"] == -.5
    assert data["task_discordance"] == {"wins": 1, "losses": 3, "ties": 0, "unavailable_tasks": 0}


def test_shared_family_resampling_preserves_opposite_stream_effects_jointly():
    manifest = [task("A", "F0"), task("B", "F1")]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: (stream == 0)
                  if arm == "evolving_validator" else (stream == 1))
    data = primary(audit(rows, manifest))
    assert data["per_stream"]["0"]["macro_cluster_mean"] == 1.
    assert data["per_stream"]["1"]["macro_cluster_mean"] == -1.
    assert data["stream_effect_range"] == [-1., 1.]
    assert data["primary_macro_cluster_delta"] == 0
    assert data["family_cluster_bootstrap"]["ci95"] == [0., 0.]
    assert data["family_cluster_bootstrap"]["n_clusters"] == 2
    assert not data["family_cluster_bootstrap"]["equivalence_established"]


def test_identical_extra_repeats_do_not_narrow_family_bootstrap():
    manifest = [task(f"T{i}", f"F{i}") for i in range(4)]

    def outcome(meta, stream, arm, repeat):
        return int(meta["id"][1:]) < 2 if arm == "evolving_validator" else False

    once = primary(audit(matrix(manifest, outcome, repeats=(0,)), manifest, expected_repeats=(0,)))
    three = primary(audit(matrix(manifest, outcome), manifest))
    assert once["family_cluster_bootstrap"] == three["family_cluster_bootstrap"]
    assert once["n_matched_pairs"] == 8
    assert three["n_matched_pairs"] == 24


def test_per_repeat_global_deltas_are_preserved():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: repeat != 1
                  if arm == "evolving_validator" else repeat == 1)
    data = primary(audit(rows, manifest))
    assert [row["macro_cluster_mean"] for row in data["per_repeat"]] == [1., -1., 1.]
    assert data["primary_macro_cluster_delta"] == pytest.approx(1 / 3)
    for stream in ("0", "1"):
        assert [row["macro_cluster_mean"] for row in data["per_stream"][stream]["per_repeat"]] == [1., -1., 1.]


def test_missing_entire_stream_does_not_change_joint_weight_to_one_stream():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: arm == "evolving_validator")
    rows = [row for row in rows if not (row["stream"] == 1 and row["arm"] == "evolving_validator")]
    result = audit(rows, manifest)
    data = primary(result)
    assert data["n_matched_pairs"] == 3
    assert data["n_missing_pairs"] == 3
    assert data["primary_macro_cluster_delta"] is None
    assert data["per_stream"]["0"]["macro_cluster_mean"] == 1.
    assert data["tasks_excluded_missing_streams"] == [{"id": "T", "cluster_id": "F", "unavailable_streams": [1]}]
    assert data["full_expected_matrix_missingness_bounds"] == {"lower": .5, "upper": 1., "not_confidence_interval": True}
    assert result["arms"]["evolving_validator"]["hard_failures"] == 0
    assert result["arms"]["evolving_validator"]["missingness"]["missing_row"] == 3


def test_manifest_exposes_wholly_absent_tasks_and_full_binary_bounds():
    manifest = [task("T", "F")]
    result = audit([], manifest)
    assert result["design"]["n_expected_rows"] == 18
    assert result["arms"]["evolving_validator"]["hard_failures"] == 0
    assert result["arms"]["evolving_validator"]["missingness"]["missing_row"] == 6
    assert primary(result)["n_missing_pairs"] == 6
    assert primary(result)["full_expected_matrix_missingness_bounds"] == {"lower": -1., "upper": 1., "not_confidence_interval": True}
    json.dumps(result, allow_nan=False)


def test_unavailable_populated_hard_values_are_not_failures():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda *args: False)
    for row in rows:
        if row["arm"] != "evolving_validator":
            continue
        if row["repeat"] == 0:
            row["target_ok"] = False
        elif row["repeat"] == 1:
            row["execution_ok"] = False
        else:
            row["hard"] = None
    result = audit(rows, manifest)
    arm = result["arms"]["evolving_validator"]
    assert arm["hard_failures"] == 0
    assert arm["missingness"] == {"missing_row": 0, "target_api_error": 2, "execution_unavailable": 2,
                                  "missing_hard": 2, "unusable_populated_hard": 4}
    assert primary(result)["n_matched_pairs"] == 0


def test_paired_means_not_difference_of_unpaired_arm_means():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: arm == "evolving_validator" or repeat > 0)
    rows = [r for r in rows if r["arm"] != "evolving_validator" or r["repeat"] == 0]
    result = audit(rows, manifest)
    assert result["arms"]["evolving_validator"]["macro_cluster_mean"] == 1.
    assert result["arms"]["fixed_validator"]["macro_cluster_mean"] == pytest.approx(2 / 3)
    assert primary(result)["primary_macro_cluster_delta"] == 1.
    assert primary(result)["n_missing_pairs"] == 4


def test_optional_ungated_arm_and_baseline_override_do_not_change_primary():
    manifest = [task("T", "F")]
    arms = ("base", "fixed_validator", "evolving_validator", "ungated_candidate")
    rows = matrix(manifest, lambda *args: True, arms=arms)
    result = audit(rows, manifest, expected_arms=arms, baseline_arm="base")
    assert result["design"]["n_expected_rows"] == 24
    assert result["arms"]["ungated_candidate"]["n_observable"] == 6
    assert set(result["contrasts"]) == {"evolving_validator_vs_fixed_validator", "evolving_validator_vs_base"}
    assert primary(result)["priority"] == "primary"


def test_five_final_arms_form_720_rows_without_new_primary_contrasts():
    manifest = [task(f"T{i:02}", f"F{i // 2:02}", context=("commerce", "tables", "routing")[i // 8],
                     mode="local-update" if i % 2 == 0 else "full-policy-replacement") for i in range(24)]
    arms = (*ARMS, "latest_fixed_candidate", "latest_evolving_candidate")
    result = audit(matrix(manifest, lambda *args: True, arms=arms), manifest, expected_arms=arms)
    assert result["design"]["n_expected_rows"] == 720
    assert result["design"]["n_distinct_request_hashes"] == 720
    assert len(result["arms"]) == 5
    assert len(result["contrasts"]) == 2
    assert result["by_mode"]["local-update"]["n_expected_tasks"] == 12
    assert primary(result)["family_cluster_bootstrap"]["n_clusters"] == 12


def test_streams_keep_equal_weight_with_unequal_available_repeat_counts():
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: stream == 0
                  if arm == "evolving_validator" else stream == 1)
    rows = [row for row in rows if row["stream"] == 1 or row["repeat"] == 0]
    data = primary(audit(rows, manifest))
    assert data["per_stream"]["0"]["macro_cluster_mean"] == 1.
    assert data["per_stream"]["1"]["macro_cluster_mean"] == -1.
    assert data["primary_macro_cluster_delta"] == 0.
    assert data["micro_matched_response_delta"] == -.5


def test_input_order_does_not_change_fixed_seed_report():
    manifest = [task(f"T{i}", f"F{i // 2}") for i in range(6)]
    rows = matrix(manifest, lambda meta, stream, arm, repeat: (int(meta["id"][1:]) + stream + repeat + ARMS.index(arm)) % 3 == 0)
    first = audit(rows, manifest)
    shuffled = copy.deepcopy(rows)
    random.Random(7).shuffle(shuffled)
    assert first == audit(shuffled, list(reversed(manifest)))


def test_reused_request_hashes_are_disclosed(tmp_path):
    manifest = [task("T", "F")]
    rows = matrix(manifest, lambda *args: True)
    rows[1]["request_hash"] = rows[0]["request_hash"]
    report = audit(rows, manifest)
    assert report["design"]["n_distinct_request_hashes"] == 17
    assert report["design"]["reused_request_hash_counts"] == {rows[0]["request_hash"]: 2}


@pytest.mark.parametrize("change", [{"hard": 1}, {"target_ok": None}, {"execution_ok": 1}, {"skill_active": 1},
                                    {"stream": True}, {"stream": 2}, {"repeat": 3}, {"arm": "unexpected"},
                                    {"skill_hash": ""}, {"request_hash": None}, {"family": "other"}])
def test_invalid_rows_rejected(change):
    manifest = [task("T", "F")]
    row = matrix(manifest, lambda *args: True)[0]
    row.update(change)
    with pytest.raises(ValueError):
        audit([row], manifest)


def test_duplicate_rows_and_duplicate_manifest_rejected():
    manifest = [task("T", "F")]
    row = matrix(manifest, lambda *args: True)[0]
    with pytest.raises(ValueError, match="Duplicate"):
        audit([row, row], manifest)
    with pytest.raises(ValueError, match="Duplicate"):
        audit([], manifest + manifest)


@pytest.mark.parametrize("options", [{"expected_streams": ()}, {"expected_repeats": (0, 0)},
                                     {"expected_streams": (True,)}, {"bootstrap_draws": 0},
                                     {"bootstrap_seed": -1}, {"expected_arms": ("noskill",)}])
def test_invalid_design_options_rejected(options):
    with pytest.raises(ValueError):
        audit([], [], **options)
