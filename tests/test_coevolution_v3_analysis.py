"""Pure synthetic statistics: no task solutions, executor, provider or file IO."""

import copy

import pytest

from skillopt.coevolution_v3.analysis import ARMS, CONTRASTS, analyze_final, analyze_shadow


def manifest():
    return [{"id": f"t{index}", "cluster_id": f"project{index // 2}", "family": f"project{index // 2}",
             "context": "synthetic", "mode": "local" if index % 2 == 0 else "replacement"} for index in range(4)]


def matrix(*, shared=False, outcome=lambda task, arm, stream, repeat: True):
    rows = []
    for task in manifest():
        for stream in [0, 1]:
            for arm in ARMS:
                for repeat in [0, 1, 2]:
                    hard = outcome(task, arm, stream, repeat)
                    content = "empty" if shared else arm
                    rows.append({**task, "stream": stream, "arm": arm, "repeat": repeat,
                                 "target_ok": True, "execution_ok": True, "hard": hard,
                                 "case_fraction": float(hard) if hard is not None else None,
                                 "skill_active": False if shared else arm != "noskill", "skill_hash": content,
                                 "request_hash": f"{task['id']}:{stream}:{repeat}:{content}",
                                 "response": content, "files": {"api.py": content}})
    return rows


def audit(rows, **kwargs):
    return analyze_final(rows, manifest(), draws=1000, **kwargs)


def test_seven_arms_shared_draws_have_exact_observed_zero_not_fake_seven_samples():
    result = audit(matrix(shared=True))
    assert len(result["arms"]) == 7
    assert result["n_rows"] == result["expected_rows"] == 168
    assert result["unique_api_requests"] == 24
    assert result["shared_alias_rows"] == 144
    assert result["n_tasks"] == 4 and result["n_project_clusters"] == 2
    assert result["all_rows_present"] is True
    assert set(result["contrasts"]) == {f"{left}_vs_{right}" for left, right, _ in CONTRASTS}
    for record in result["contrasts"].values():
        assert record["primary_macro_cluster_delta"] == 0
        assert record["n_matched_pairs"] == 24
        assert record["family_cluster_bootstrap"]["ci95"] == [0., 0.]
        assert record["family_cluster_bootstrap"]["degenerate_distribution"] is True
        assert record["family_cluster_bootstrap"]["equivalence_established"] is False


@pytest.mark.parametrize("field,replacement", [
    ("hard", False), ("target_ok", False), ("execution_ok", False), ("response", "different"),
    ("skill_hash", "different"), ("case_fraction", 0.25), ("skill_active", True),
    ("files", {"api.py": "different code"}),
])
def test_alias_provenance_cannot_manufacture_score_or_artifact_differences(field, replacement):
    rows = matrix(shared=True)
    rows[0][field] = replacement
    with pytest.raises(ValueError, match="Aliased shared request"):
        audit(rows)


def test_unavailable_populated_hard_stays_missing_and_bounds_remain_explicit():
    rows = matrix()
    for row in rows:
        if row["arm"] == "working_decoupled_evolving" and row["id"] == "t0" and row["stream"] == 0 and row["repeat"] == 0:
            row["target_ok"] = False  # hard=True is deliberately unusable, not a free success.
    result = audit(rows)
    arm = result["arms"]["working_decoupled_evolving"]
    assert arm["hard_passes"] == arm["n_observable"] == 23
    assert arm["missingness"]["target_api_error"] == arm["missingness"]["unusable_populated_hard"] == 1
    contrast = result["contrasts"]["working_decoupled_evolving_vs_working_coupled_evolving"]
    assert contrast["n_expected_pairs"] == 24
    assert contrast["n_matched_pairs"] == 23 and contrast["n_missing_pairs"] == 1
    assert contrast["primary_macro_cluster_delta"] == 0.
    bounds = contrast["full_expected_matrix_missingness_bounds"]
    assert bounds["lower"] == pytest.approx(-1 / 24)
    assert bounds["upper"] == 0. and bounds["not_confidence_interval"] is True


def test_joint_task_estimate_drops_a_missing_stream_without_hiding_missing_matrix():
    rows = matrix()
    for row in rows:
        if row["arm"] == "working_decoupled_evolving" and row["id"] == "t0" and row["stream"] == 0:
            row.update(execution_ok=False, hard=None, case_fraction=None)
    result = audit(rows)
    arm = result["arms"]["working_decoupled_evolving"]
    assert arm["missingness"]["execution_unavailable"] == 3
    assert arm["n_observable"] == 21
    assert arm["tasks_excluded_missing_streams"] == [{"id": "t0", "cluster_id": "project0", "unavailable_streams": [0]}]
    contrast = result["contrasts"]["working_decoupled_evolving_vs_working_coupled_evolving"]
    assert contrast["n_joint_observed_tasks"] == 3 and contrast["n_missing_pairs"] == 3


def test_family_bootstrap_keeps_both_modes_streams_and_repeats_correlated():
    def outcome(task, arm, stream, repeat):
        return arm == "working_decoupled_evolving" and task["cluster_id"] == "project0"

    rows = matrix(outcome=outcome)
    result = audit(rows, seed=123)
    key = "working_decoupled_evolving_vs_working_coupled_evolving"
    contrast = result["contrasts"][key]
    assert contrast["primary_macro_cluster_delta"] == 0.5
    assert contrast["cluster_deltas"] == {"project0": 1., "project1": 0.}
    assert contrast["family_cluster_bootstrap"]["n_clusters"] == 2
    assert contrast["family_cluster_bootstrap"]["ci95"] == [0., 1.]
    assert contrast["family_cluster_bootstrap"] == audit(rows, seed=123)["contrasts"][key]["family_cluster_bootstrap"]
    assert all(row["macro_cluster_mean"] == 0.5 for row in contrast["per_repeat"])
    assert all(row["macro_cluster_mean"] == 0.5 for row in contrast["per_stream"].values())


def test_absent_final_row_is_reported_without_inventing_a_failure():
    rows = matrix()
    omitted = rows.pop()
    result = audit(rows)
    assert result["all_rows_present"] is False
    assert result["n_rows"] == 167 and result["expected_rows"] == 168
    arm = result["arms"][omitted["arm"]]
    assert arm["missingness"]["missing_row"] == 1
    assert arm["hard_failures"] == 0 and arm["n_observable"] == 23


def shadow_pair(identity, *, group="natural", hard=False, detected=(False, True), stream=0,
                cluster="p0", public_pass=True, available=(True, True), shared_claim=False):
    result = []
    for index, validator in enumerate(["fixed", "evolving"]):
        searched = available[index]
        result.append({"id": "task-" + identity, "cluster_id": cluster, "stream": stream,
                       "artifact_id": identity, "artifact_hash": "code-" + identity,
                       "artifact_group": group, "kind": "natural" if group == "natural" else "semantic_mutant",
                       "validator": validator, "oracle_hard": hard, "public_pass": public_pass,
                       "baseline_available": True, "detected": detected[index],
                       "search_status": "completed" if searched else "claim_unavailable",
                       "schema_valid": searched, "valid_probes": int(searched),
                       "verified_mismatches": int(detected[index] and public_pass),
                       "assessment_available": detected[index] or searched,
                       "claim": {"request_hash": "shared" + identity if shared_claim else identity + validator}})
    return result


def test_shadow_natural_controls_remain_distinct_despite_opposite_effects():
    rows = shadow_pair("natural-bad", detected=(False, True))
    rows += shadow_pair("controlled-bad", group="controlled", detected=(True, False))
    result = analyze_shadow(rows, draws=100, seed=123)
    assert result["natural_and_controlled_not_pooled"] is True
    natural, controlled = result["groups"]["natural"], result["groups"]["controlled"]
    assert natural["paired_bad_artifacts"] == controlled["paired_bad_artifacts"] == 1
    assert natural["cluster_macro_detection_delta"] == 1.
    assert controlled["cluster_macro_detection_delta"] == -1.
    assert natural["cluster_bootstrap"]["ci95"] is None  # one family cannot yield a credible bootstrap interval
    assert natural["fixed"]["missed_oracle_failures_with_usable_assessment"] == 1
    assert natural["evolving"]["detected_oracle_failures"] == 1


def test_shadow_failed_search_is_unknown_not_definite_semantic_miss_or_complete_pair():
    rows = shadow_pair("bad", detected=(False, False), available=(True, False))
    result = analyze_shadow(rows, draws=100)
    natural = result["groups"]["natural"]
    assert natural["evolving"]["missed_oracle_failures_with_usable_assessment"] == 0
    assert natural["evolving"]["search_unavailable"] == 1
    assert natural["evolving"]["oracle_failed_assessment_unknown"] == 1
    assert natural["evolving"]["end_to_end_nondetected_including_unknown"] == 1
    assert natural["paired_bad_artifacts"] == 0
    assert natural["bad_pairs_with_unknown_assessment"] == 1
    assert natural["end_to_end_bad_pairs_including_search_unknown"] == 1
    assert natural["end_to_end_detection_delta_including_search_unknown"] == 0.
    assert natural["cluster_macro_detection_delta"] is None


def test_shadow_public_failure_is_known_even_when_optional_model_search_fails():
    rows = shadow_pair("syntax", detected=(True, True), public_pass=False, available=(False, False))
    natural = analyze_shadow(rows, draws=100)["groups"]["natural"]
    assert natural["paired_bad_artifacts"] == 1
    assert natural["cluster_macro_detection_delta"] == 0
    assert natural["fixed"]["detected_oracle_failures"] == natural["evolving"]["detected_oracle_failures"] == 1


def test_shadow_oracle_disagreement_not_automatically_a_false_positive():
    rows = shadow_pair("apparently-good", hard=True, detected=(False, True))
    natural = analyze_shadow(rows, draws=100)["groups"]["natural"]
    assert natural["paired_bad_artifacts"] == 0
    assert natural["evolving"]["oracle_disagreements_require_audit"] == 1
    assert natural["evolving"]["oracle_failed_artifacts"] == 0


def test_shadow_shared_calls_are_positions_not_two_real_api_calls():
    rows = shadow_pair("same", detected=(False, False), shared_claim=True)
    result = analyze_shadow(rows, draws=100)
    assert result["request_positions"] == {"fixed": 1, "evolving": 1}
    assert result["actual_unique_claim_requests"] == 1


def test_shadow_duplicate_row_or_incomplete_pair_rejected():
    rows = shadow_pair("bad")
    with pytest.raises(ValueError, match="Duplicate"):
        analyze_shadow(rows + [copy.deepcopy(rows[0])], draws=100)
    with pytest.raises(ValueError, match="Incomplete"):
        analyze_shadow(rows[:1], draws=100)


@pytest.mark.parametrize("field,replacement", [("id", "wrong"), ("artifact_hash", "wrong"),
                                               ("oracle_hard", True), ("public_pass", False),
                                               ("artifact_group", "controlled"), ("kind", "reference"),
                                               ("cluster_id", "other-project"), ("baseline_available", False)])
def test_shadow_same_artifact_alignment_required(field, replacement):
    rows = shadow_pair("bad")
    rows[1][field] = replacement
    with pytest.raises(ValueError, match="same artifact"):
        analyze_shadow(rows, draws=100)
