"""Independent synthetic score tables; no benchmark examples or API calls."""

from copy import deepcopy

import pytest

from skillopt.coevolution_v9 import analysis as a
from skillopt.validator_pilot.api import digest


def observations(n=8, histories=(0, 1, 2)):
    expected = {f"q{i}": {"cluster_id": f"cluster{i}"} for i in range(n)}
    rows = []
    for task, metadata in expected.items():
        for history in histories:
            for policy in a.POLICIES:
                shared_history = 0 if policy in ("no_skill", "initial") else history
                rows.append({"task_id": task, "cluster_id": metadata["cluster_id"], "history": history,
                             "policy": policy, "em": 0, "f1": 0.0, "api_ok": True,
                             "skill_hash": digest(policy), "request_hash": digest([task, shared_history, policy])})
    return rows, expected


def summary(rows, expected, histories=(0, 1, 2), **kw):
    return a.summarize_final(rows, expected_tasks=expected, histories=histories,
                             bootstrap_samples=100, permutation_samples=100, **kw)


def gate_rows(n=64, wins=4, losses=0, base_correct=0):
    rows, expected = observations(n, (0,))
    parent = [r for r in rows if r["policy"] == "initial"]
    candidate = [r for r in rows if r["policy"] == "ours"]
    base = [r for r in rows if r["policy"] == "no_skill"]
    for index, row in enumerate(candidate):
        row["em"] = row["f1"] = int(index < wins)
    for index, row in enumerate(parent):
        row["em"] = row["f1"] = int(wins <= index < wins + losses)
    for index, row in enumerate(base):
        row["em"] = row["f1"] = int(index < base_correct)
    return parent, candidate, base, expected


def gate(data, **kw):
    parent, candidate, base, expected = data
    return a.local_gate(parent, candidate, base, expected_tasks=expected, **kw)


def test_summary_keeps_three_histories_but_counts_shared_base_once():
    rows, expected = observations()
    result = summary(rows, expected)
    assert result["n_observation_positions"] == 8 * 3 * 4
    assert result["unique_actual_requests"] == 8 * (1 + 1 + 3 + 3)
    assert result["aliased_positions_beyond_first_request"] == 8 * 4
    assert result["n_question_clusters"] == 8
    assert result["policy_summary"]["no_skill"]["unique_requests"] == 8
    assert result["policy_summary"]["no_skill"]["n_positions"] == 24
    assert result["histories"] == [0, 1, 2]
    assert result["scope_expansion_authorized"] is False
    assert result["cross_domain_generalization_established"] is False
    assert result["safety_or_noninferiority_certified"] is False


def test_exact_shared_rejected_skill_has_zero_effect_vs_initial():
    rows, expected = observations()
    initial = {(r["task_id"], r["history"]): r for r in rows if r["policy"] == "initial"}
    for row in rows:
        if row["policy"] in ("ours", "skillopt"):
            source = initial[row["task_id"], row["history"]]
            row.update({k: source[k] for k in ("request_hash", "skill_hash", "em", "f1")})
    result = summary(rows, expected)
    pair = result["comparisons"]["ours_vs_initial"]
    assert pair["shared_request_positions"] == 24
    assert pair["metrics"]["em"]["all_attempt"]["mean_delta"] == 0
    assert result["unique_actual_requests"] == 16


def test_failures_are_preserved_and_unknown_losses_are_not_semantic_failures():
    rows, expected = observations(1)
    for row in rows:
        if row["policy"] == "no_skill":
            row["em"] = row["f1"] = 1
        elif row["policy"] == "ours":
            row.update(api_ok=False, em=None, f1=None)
    result = summary(rows, expected)
    rates = result["policy_summary"]["ours"]
    assert rates["all_attempt_em"] == 0
    assert rates["oracle_available"] == 0
    assert rates["available_only_em_diagnostic"] is None
    losses = result["comparisons"]["ours_vs_no_skill"]["right_correct_left_unsuccessful"]
    assert losses["count"] == losses["unknown_left_losses"] == 3
    assert losses["confirmed_scored_losses"] == 0


def test_cluster_means_average_histories_before_uncertainty():
    rows, expected = observations(2)
    for row in rows:
        if row["policy"] == "ours" and (row["task_id"] == "q0" or row["history"] == 0):
            row["em"] = row["f1"] = 1
    result = summary(rows, expected)
    inference = result["comparisons"]["ours_vs_no_skill"]["metrics"]["em"]["cluster_inference"]
    assert inference["clusters"] == 2
    assert inference["cluster_deltas"] == {"cluster0": 1, "cluster1": 1 / 3}
    assert inference["mean_delta"] == pytest.approx(2 / 3)
    assert inference["bootstrap"]["conditional_on_observed_learning_histories"] is True


def test_question_micro_and_cluster_equal_weighting_are_distinct():
    rows, expected = observations(3)
    expected["q1"]["cluster_id"] = "cluster0"
    for row in rows:
        row["cluster_id"] = expected[row["task_id"]]["cluster_id"]
        if row["policy"] == "ours" and row["task_id"] != "q2":
            row["em"] = row["f1"] = 1
    rates = summary(rows, expected)["policy_summary"]["ours"]
    assert rates["all_attempt_em"] == pytest.approx(2 / 3)
    assert rates["question_cluster_equal_em"] == 0.5


def test_per_history_results_prevent_picking_only_favorable_learning_seed():
    rows, expected = observations()
    for row in rows:
        if row["policy"] == "ours" and row["history"] == 1:
            row["em"] = row["f1"] = 1
    pair = summary(rows, expected)["comparisons"]["ours_vs_no_skill"]
    assert pair["per_history"]["1"]["em"]["mean_delta"] == 1
    assert pair["per_history"]["0"]["em"]["mean_delta"] == 0
    assert pair["history_em_delta_range"] == {"min": 0, "max": 1, "history_resampling_claim": False}


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows.append(deepcopy(rows[0])),
    lambda rows: rows[0].update(cluster_id="wrong"),
    lambda rows: rows[0].update(history=5),
    lambda rows: rows[0].update(history=True),
    lambda rows: rows[0].update(policy="forced_rejected_candidate"),
    lambda rows: rows[0].update(request_hash="bad"),
    lambda rows: rows[0].update(skill_hash="bad"),
    lambda rows: rows[0].update(api_ok=1),
    lambda rows: rows[0].update(api_ok=False),
    lambda rows: rows[0].update(em=0.5),
    lambda rows: rows[0].update(em=True),
    lambda rows: rows[0].update(em=1, f1=0),
    lambda rows: rows[0].update(f1=float("nan")),
    lambda rows: rows[0].update(f1=2),
    lambda rows: rows[0].update(em=None),
    lambda rows: rows[0].pop("em"),
    lambda rows: rows[0].update(skill_hash=digest("changing-base")),
    lambda rows: rows[1].update(request_hash=rows[0]["request_hash"]),
    lambda rows: rows[-4].update(request_hash=rows[0]["request_hash"]),
])
def test_invalid_or_incomplete_grid_rejected(mutation):
    rows, expected = observations()
    mutation(rows)
    with pytest.raises(ValueError):
        summary(rows, expected)


def test_complete_common_missing_question_detected_from_reservation():
    rows, expected = observations()
    rows = [row for row in rows if row["task_id"] != "q1"]
    with pytest.raises(ValueError, match="Incomplete"):
        summary(rows, expected)


@pytest.mark.parametrize("histories", [[], [0, 0], [True], [-1]])
def test_invalid_history_declaration_rejected(histories):
    rows, expected = observations()
    with pytest.raises(ValueError):
        summary(rows, expected, histories)


def test_holm_adjusts_only_frozen_primary_em_family_not_selected_p_values():
    assert a._holm({"a": 0.04, "b": 0.03}) == {"b": 0.06, "a": 0.06}
    rows, expected = observations()
    result = summary(rows, expected)
    assert result["primary_em_multiplicity"]["family"] == ["ours_vs_no_skill", "ours_vs_skillopt"]
    assert "primary_em_holm_adjusted_p" not in result["comparisons"]["skillopt_vs_no_skill"]
    assert set(result["comparisons"]) == {"ours_vs_no_skill", "ours_vs_skillopt", "skillopt_vs_no_skill",
                                         "ours_vs_initial", "skillopt_vs_initial", "initial_vs_no_skill"}


def test_exact_sign_flip_and_bootstrap_do_not_fake_significance_with_few_clusters():
    result = a.question_cluster_inference({"one": 1, "two": 1}, bootstrap_samples=100)
    assert result["ci95"] == {"low": 1, "high": 1}
    assert result["sign_flip"]["p_two_sided"] == 0.5
    assert result["few_clusters_descriptive_only"] is True


def test_exact_sign_flip_ignores_zero_signs_without_changing_probability():
    result = a.question_cluster_inference({"one": 1, **{f"zero{i}": 0 for i in range(30)}}, bootstrap_samples=100)
    assert result["sign_flip"]["exact"] is True
    assert result["sign_flip"]["assignments"] == 2
    assert result["sign_flip"]["p_two_sided"] == 1


def test_monte_carlo_sign_flip_is_deterministic_and_never_zero():
    deltas = {f"c{i}": 1 for i in range(20)}
    first = a.question_cluster_inference(deltas, bootstrap_samples=100, permutation_samples=100)
    second = a.question_cluster_inference(deltas, bootstrap_samples=100, permutation_samples=100)
    assert first == second
    assert first["sign_flip"]["exact"] is False
    assert first["sign_flip"]["p_two_sided"] >= 1 / 101


@pytest.mark.parametrize("options", [
    {"deltas": {}}, {"deltas": {"x": float("nan")}}, {"deltas": {"x": True}},
    {"deltas": {"x": 1.1}}, {"bootstrap_samples": 99}, {"permutation_samples": 99}, {"seed": -1},
])
def test_invalid_inference_inputs_rejected(options):
    settings = {"deltas": {"x": 0}, "bootstrap_samples": 100, "permutation_samples": 100, **options}
    with pytest.raises(ValueError):
        a.question_cluster_inference(**settings)


def test_local_gate_calls_real_standard_strict_gate_and_commits_supported_candidate(monkeypatch):
    original = a.evaluate_gate
    calls = []

    def observed(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(a, "evaluate_gate", observed)
    result = gate(gate_rows())
    assert len(calls) == 1
    assert result["standard_accept"] is True
    assert result["ours_accept"] is True
    assert result["ours_action"] == "Local Commit"
    assert result["exact_discordant_one_sided_p"] == 1 / 16
    assert result["candidate_vs_parent"] == {"n": 64, "wins": 4, "losses": 0, "ties": 60, "mean_delta": 4 / 64}
    assert result["record_hash"] == digest({k: v for k, v in result.items() if k != "record_hash"})
    assert result["per_question_labels_returned"] is False
    assert result["optimizer_feedback_authorized"] is False
    assert result["cross_domain_commit_authorized"] is False
    assert "q0" not in str(result)


def test_small_net_gain_can_pass_original_gate_but_restrict_ours():
    result = gate(gate_rows(wins=3))
    assert result["standard_accept"] is True
    assert result["ours_accept"] is False
    assert result["exact_discordant_one_sided_p"] == 1 / 8
    assert "paired_parent_improvement_evidence_insufficient" in result["reasons"]


def test_baseline_harm_blocks_even_supported_parent_gain():
    result = gate(gate_rows(wins=4, base_correct=5))
    assert result["standard_accept"] is True
    assert result["exact_discordant_one_sided_p"] == 1 / 16
    assert result["ours_accept"] is False
    assert "candidate_native_em_below_no_skill" in result["reasons"]
    assert result["base_correct_candidate_unsuccessful"]["count"] == 1


def test_zero_discordance_is_not_positive_evidence_and_retains_parent():
    result = gate(gate_rows(wins=0))
    assert result["standard_accept"] is result["ours_accept"] is False
    assert result["exact_discordant_one_sided_p"] == 1
    assert result["rejection_retains_parent_not_no_skill"] is True


def test_eight_question_smoke_cannot_relax_main_64_question_gate():
    result = gate(gate_rows(n=8, wins=8))
    assert result["standard_accept"] is True
    assert result["ours_accept"] is False
    assert result["minimum_clusters"] == 64
    assert "insufficient_independent_confirmation_question_clusters" in result["reasons"]


def test_unchanged_candidate_reuses_exact_parent_and_never_promotes():
    parent, _, base, expected = gate_rows()
    result = a.local_gate(parent, deepcopy(parent), base, expected_tasks=expected)
    assert result["standard_accept"] is result["ours_accept"] is False
    assert result["unique_actual_requests"] == 128


def test_same_skill_fresh_draw_cannot_manufacture_gate_improvement():
    parent, candidate, base, expected = gate_rows()
    for row in candidate:
        row["skill_hash"] = parent[0]["skill_hash"]
    with pytest.raises(ValueError, match="unchanged"):
        a.local_gate(parent, candidate, base, expected_tasks=expected)


@pytest.mark.parametrize("mutation", [
    lambda p, c, b, e: c.pop(),
    lambda p, c, b, e: c.append(deepcopy(c[0])),
    lambda p, c, b, e: c[0].update(history=1),
    lambda p, c, b, e: c[0].update(cluster_id="bad"),
    lambda p, c, b, e: c[0].update(skill_hash=digest("unfrozen-other-skill")),
    lambda p, c, b, e: c[0].update(api_ok=False),
    lambda p, c, b, e: c[0].update(em=None),
    lambda p, c, b, e: c[0].update(em=0.5),
    lambda p, c, b, e: c[0].update(f1=float("inf")),
    lambda p, c, b, e: c[0].update(request_hash=p[0]["request_hash"]),
    lambda p, c, b, e: e.pop("q0"),
])
def test_invalid_gate_input_cannot_silently_drop_or_reinterpret_observations(mutation):
    data = gate_rows()
    mutation(*data)
    with pytest.raises(ValueError):
        gate(data)


def test_repeated_question_clusters_cannot_fake_64_independent_questions():
    data = gate_rows()
    for rows in data[:3]:
        rows[1]["cluster_id"] = rows[0]["cluster_id"]
    data[3]["q1"]["cluster_id"] = data[3]["q0"]["cluster_id"]
    with pytest.raises(ValueError, match="independent"):
        gate(data)


def test_gate_keeps_unknown_denominator_and_avoids_semantic_relabel():
    parent, candidate, base, expected = gate_rows(wins=0)
    candidate[0].update(api_ok=False, em=None, f1=None)
    result = a.local_gate(parent, candidate, base, expected_tasks=expected)
    assert result["rates"]["candidate"]["unknown"] == 1
    assert result["rates"]["candidate"]["n_positions"] == 64
    assert result["unknowns_are_not_confirmed_semantic_failures"] is True


def test_exact_discordant_tail_includes_losses_and_is_not_sign_only_on_net_wins():
    result = gate(gate_rows(wins=5, losses=1))
    assert result["exact_discordant_one_sided_p"] == 7 / 64
    assert result["ours_accept"] is False


def test_analysis_is_pure_and_order_independent():
    rows, expected = observations()
    before = deepcopy(rows)
    result = summary(rows, expected)
    assert rows == before
    assert summary(list(reversed(rows)), dict(reversed(list(expected.items())))) == result
    data = gate_rows()
    snapshot = deepcopy(data)
    gate(data)
    assert data == snapshot
