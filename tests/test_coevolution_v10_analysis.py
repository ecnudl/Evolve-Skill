"""Prospective transfer gates with fabricated complete observations only."""

from copy import deepcopy

import pytest

from skillopt.coevolution_v10 import analysis
from skillopt.validator_pilot.api import digest


def panel(n=64):
    expected = {f"task_{i}": {"cluster_id": digest(f"question_{i}")} for i in range(n)}
    source = {h: {"skill_hash": digest("initial" if h == 0 else f"learned_{h}"), "learned": h != 0}
              for h in range(3)}
    rows = []
    for i, (task, meta) in enumerate(expected.items()):
        for history in range(3):
            for policy in ("no_skill", "initial", "raw_transfer"):
                skill = digest("base") if policy == "no_skill" else digest("initial") if policy == "initial" else source[history]["skill_hash"]
                hard = int(i < n - 8) if policy != "raw_transfer" or history == 0 else 1
                rows.append({"task_id": task, "cluster_id": meta["cluster_id"], "history": history,
                    "policy": policy, "skill_hash": skill, "request_hash": digest((task, skill)),
                    "api_ok": True, "hard": hard, "soft": float(hard)})
    return rows, expected, source


def gate(rows, expected, source):
    return analysis.portfolio_gate(rows, expected_tasks=expected, source_skills=source)


def test_shared_panel_adjustment_and_initial_never_approved():
    rows, expected, source = panel()
    result = gate(rows, expected, source)
    assert result["n_questions"] == 64 and len(result["family"]) == 2
    assert not result["decisions"]["0"]["approve"]
    for h in ("1", "2"):
        row = result["decisions"][h]
        assert row["approve"] and row["wins"] == 8 and row["losses"] == 0
        assert row["holm_one_sided_p"] == 2 * row["raw_one_sided_p"]
    assert not result["safety_or_noninferiority_certified"]


def test_smoke_never_lowers_sixty_four_requirement():
    rows, expected, source = panel(8)
    result = gate(rows, expected, source)
    assert all(not row["approve"] for row in result["decisions"].values())
    assert "insufficient_independent_target_questions" in result["decisions"]["1"]["reasons"]


def test_observed_harm_screen_rejects_even_large_net_gain():
    rows, expected, source = panel()
    for row in rows:
        if row["history"] == 1 and row["policy"] == "raw_transfer" and row["task_id"] in ("task_0", "task_1"):
            row["hard"] = row["soft"] = 0
    result = gate(rows, expected, source)
    assert result["decisions"]["1"]["all_attempt_delta"] > 0
    assert "observed_target_loss_screen_exceeded" in result["decisions"]["1"]["reasons"]


def test_unknowns_count_in_endpoint_but_not_confirmed_semantic_losses():
    rows, expected, source = panel()
    for row in rows:
        if row["history"] == 1 and row["policy"] == "raw_transfer" and row["task_id"] == "task_0":
            row.update(api_ok=False, hard=None, soft=None)
    decision = gate(rows, expected, source)["decisions"]["1"]
    assert decision["losses"] == 1 and decision["confirmed_scored_losses"] == 0
    assert "candidate_availability_worse_than_base" in decision["reasons"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_skill", "inconsistent_alias", "unknown_score",
                                   "pretend_learned", "resampled_base"])
def test_invalid_evidence_refused(change):
    rows, expected, source = panel()
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif change == "wrong_skill":
        source[1]["skill_hash"] = digest("wrong")
    elif change == "inconsistent_alias":
        rows[0]["hard"] = rows[0]["soft"] = 0
    elif change == "unknown_score":
        rows[0]["api_ok"] = False
    elif change == "pretend_learned":
        source[0]["learned"] = True
    else:
        rows[0]["request_hash"] = digest("another_draw")
    with pytest.raises(ValueError):
        gate(rows, expected, source)


def test_final_exact_fallback_alias_and_coding_metric_labels():
    rows, expected, source = panel()
    final = rows + [{**row, "policy": "scope_gated"} for row in rows if row["policy"] == "no_skill"]
    result = analysis.summarize_final(final, expected_tasks=expected, histories=[0, 1, 2], bootstrap_samples=100)
    assert result["n_questions"] == 64 and result["n_observation_positions"] == 768
    assert result["policy_summary"]["scope_gated"]["all_attempt_task_success"] == result["policy_summary"]["no_skill"]["all_attempt_task_success"]
    assert result["comparisons"]["scope_gated_vs_no_skill"]["metrics"]["task_success"]["all_attempt"]["mean_delta"] == 0
    assert "em" not in result["comparisons"]["scope_gated_vs_raw_transfer"]["metrics"]
    assert result["fallback_is_not_skill_generalization"] and not result["cross_domain_generalization_established"]


@pytest.mark.parametrize("kwargs", [{"minimum_clusters": 63}, {"alpha": 0.2}, {"maximum_observed_loss_rate": 0.1}])
def test_cannot_weaken_fixed_gate_bounds(kwargs):
    rows, expected, source = panel()
    with pytest.raises(ValueError):
        analysis.portfolio_gate(rows, expected_tasks=expected, source_skills=source, **kwargs)
