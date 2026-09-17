from __future__ import annotations

import hashlib
import random
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.coevolution_v15.analysis import (
    EMPTY_SKILL_HASH,
    POLICIES,
    rough_family_budget,
    summarize,
)


def panel(histories=3, domains=("coding", "spreadsheet", "rule_reasoning"), families=4):
    rows = []
    for domain in domains:
        for i in range(families):
            for history in range(histories):
                for policy in POLICIES:
                    rows.append({"task_id": f"{domain}-{i}", "domain": domain,
                        "cluster_id": f"{domain}-f{i}", "history": history, "policy": policy,
                        "passed": i % 2 == 0, "oracle_available": True, "artifact_valid": True,
                        "skill_hash": EMPTY_SKILL_HASH if policy == "no_skill" else
                                      hashlib.sha256((policy + str(history)).encode()).hexdigest(),
                        "skill_nonempty": policy != "no_skill", "phase": "final", "round": 4})
    return rows


def summary(rows, **kwargs):
    return summarize(rows, bootstrap_samples=200, **kwargs)


def test_balanced_final_and_seal():
    result = summary(panel())
    assert verify(result) == result
    assert result["task_instances"] == 12
    assert result["logical_rows"] == 144
    assert result["structural_families_by_domain"] == {
        "coding": 4, "rule_reasoning": 4, "spreadsheet": 4}
    assert result["policy_summary"]["fixed"]["macro_all_attempt_success"] == 0.5
    assert set(result["comparisons"]) == {"fixed_vs_no_skill", "adaptive_vs_no_skill",
        "adaptive_research_vs_no_skill", "adaptive_vs_fixed", "adaptive_research_vs_adaptive"}
    assert result["comparisons"]["adaptive_vs_fixed"]["macro"] == {"delta": 0, "ci95": [0, 0]}
    assert result["inference"]["zero_width_interval_not_equivalence_or_safety"]


def test_unknowns_remain_in_primary_denominator():
    rows = panel(histories=1, domains=("coding",), families=4)
    for row in rows:
        if row["policy"] == "adaptive":
            row.update(passed=False, oracle_available=False, artifact_valid=False)
    result = summary(rows)
    rates = result["policy_summary"]["adaptive"]
    assert rates["total"] == 4 and rates["all_attempt_success"] == 0
    assert rates["semantic_failures"] == 0 and rates["oracle_unknown"] == 4
    assert rates["conditional_semantic_success"] is None
    counts = result["comparisons"]["adaptive_vs_fixed"]["counts"]
    assert counts["losses"] == 2 and counts["semantic_losses"] == 0
    assert counts["losses_with_unavailable"] == 2


def test_distinguishes_delivery_and_valid_artifact_oracle_unknown():
    rows = panel(histories=1, domains=("coding",), families=1)
    rows[1].update(passed=False, oracle_available=False)
    result = summary(rows)["policy_summary"]["fixed"]
    assert result["artifact_invalid"] == 0
    assert result["valid_artifact_oracle_unknown"] == 1


def test_macro_is_domain_equal_not_pooled():
    rows = panel(histories=1, domains=("coding",), families=4)
    rows += panel(histories=1, domains=("spreadsheet",), families=1)
    for row in rows:
        row["passed"] = row["domain"] == "spreadsheet"
    rates = summary(rows)["policy_summary"]["fixed"]
    assert rates["all_attempt_success"] == 0.2
    assert rates["macro_all_attempt_success"] == 0.5


def test_native_domain_accuracy_not_silently_family_equal():
    rows = panel(histories=1, domains=("coding",), families=4)
    for row in rows:
        row["passed"] = row["task_id"] != "coding-3"
        row["cluster_id"] = "large" if row["passed"] else "small"
    result = summary(rows)
    assert result["policy_summary"]["fixed"]["macro_all_attempt_success"] == 0.75
    assert result["structural_families_by_domain"]["coding"] == 2


def test_all_histories_of_family_travel_together():
    rows = panel(histories=2, domains=("coding",), families=4)
    for row in rows:
        row["passed"] = row["history"] == (1 if row["policy"] == "fixed" else 0)
    result = summary(rows)
    assert result["comparisons"]["adaptive_vs_fixed"]["macro"]["ci95"] == [0, 0]
    assert result["comparisons"]["adaptive_vs_fixed"]["by_history"]["0"]["macro_delta"] == 1
    assert result["comparisons"]["adaptive_vs_fixed"]["by_history"]["1"]["macro_delta"] == -1


def test_duplicate_identical_history_does_not_shrink_family_interval():
    rows = panel(histories=1, domains=("coding",), families=4)
    for row in rows:
        if row["policy"] == "adaptive":
            row["passed"] = True
    once = summary(rows)
    copies = [dict(row, history=1) for row in rows]
    twice = summary(rows + copies)
    assert once["comparisons"]["adaptive_vs_fixed"]["macro"] == twice["comparisons"]["adaptive_vs_fixed"]["macro"]
    assert twice["structural_families_by_domain"] == once["structural_families_by_domain"]


def test_paired_wins_losses_and_worst_domain():
    rows = panel(histories=1, families=2)
    for row in rows:
        if row["policy"] == "adaptive":
            row["passed"] = row["domain"] != "spreadsheet"
    result = summary(rows)["comparisons"]["adaptive_vs_fixed"]
    assert result["counts"]["wins"] == 2 and result["counts"]["losses"] == 1
    assert result["counts"]["semantic_wins"] == 2
    assert result["counts"]["semantic_losses"] == 1
    assert result["worst_domain_delta"] == -0.5
    assert result["maximum_domain_drop"] == 0.5
    assert result["macro"]["delta"] == pytest.approx(1 / 6)


def test_deterministic_and_input_order_invariant_no_mutation():
    rows = panel()
    before = deepcopy(rows)
    a = summary(rows)
    assert rows == before
    random.Random(91).shuffle(rows)
    assert summary(rows) == a


def test_text_identity_is_not_claimed_as_actual_request_alias():
    rows = panel()
    for row in rows:
        if row["policy"] != "no_skill":
            row.update(skill_nonempty=False, skill_hash=EMPTY_SKILL_HASH)
    data = summary(rows)["data_quality"]
    assert data["unique_task_history_skill_identities"] == 36
    assert data["repeated_text_positions_beyond_first"] == 108
    assert data["actual_request_aliasing_not_inferred_from_text_identity"]


def test_external_universe_catches_uniformly_missing_task_and_history():
    rows = panel()
    expected = {r["task_id"]: {k: r[k] for k in ("domain", "cluster_id")} for r in rows}
    result = summary(rows, expected_tasks=expected, expected_histories=[0, 1, 2])
    assert result["data_quality"]["grid_reference"] == "frozen_universe"
    with pytest.raises(ValueError, match="task universe"):
        summary([r for r in rows if r["task_id"] != "coding-0"], expected_tasks=expected)
    with pytest.raises(ValueError, match="histories differ"):
        summary([r for r in rows if r["history"] != 2], expected_histories=[0, 1, 2])


@pytest.mark.parametrize("mutation", [
    {"passed": 1}, {"oracle_available": 0}, {"artifact_valid": "true"}, {"skill_nonempty": 1},
    {"passed": True, "oracle_available": False}, {"artifact_valid": False},
    {"history": True}, {"history": -1}, {"history": 100}, {"domain": ""},
    {"task_id": ""}, {"cluster_id": []}, {"policy": "unknown"},
    {"skill_hash": "not-a-hash"}, {"skill_hash": "A" * 64},
    {"skill_nonempty": True}, {"phase": "development"}, {"round": True}, {"round": -1},
])
def test_invalid_observation_rejected(mutation):
    rows = panel()
    rows[0].update(mutation)
    with pytest.raises(ValueError):
        summary(rows)


def test_no_skill_nonempty_even_when_hash_consistent_rejected():
    rows = panel()
    rows[0].update(skill_nonempty=True, skill_hash="1" * 64)
    with pytest.raises(ValueError, match="No-Skill"):
        summary(rows)


def test_incomplete_duplicate_and_metadata_drift():
    rows = panel()
    with pytest.raises(ValueError, match="Incomplete"):
        summary(rows[1:])
    with pytest.raises(ValueError, match="Duplicate"):
        summary(rows + [rows[0]])
    rows[1]["cluster_id"] = "wrong-family"
    with pytest.raises(ValueError, match="changed"):
        summary(rows)


def test_multiple_checkpoints_rejected():
    rows = panel()
    rows[0]["round"] = 3
    with pytest.raises(ValueError, match="checkpoints"):
        summary(rows)


@pytest.mark.parametrize("policies", [(), ("fixed",), ("no_skill", "no_skill"), "no_skill"])
def test_invalid_policy_universe(policies):
    with pytest.raises(ValueError):
        summary(panel(), policies=policies)


@pytest.mark.parametrize("kwargs", [{"bootstrap_samples": 99}, {"bootstrap_samples": True},
    {"bootstrap_samples": 20001}, {"seed": -1}, {"seed": True}, {"seed": 2**64}])
def test_bootstrap_bounds(kwargs):
    with pytest.raises(ValueError):
        summarize(panel(), **kwargs)


def test_minimal_policy_pair_supported():
    rows = [r for r in panel() if r["policy"] in ("no_skill", "fixed")]
    result = summary(rows, policies=("no_skill", "fixed"))
    assert set(result["comparisons"]) == {"fixed_vs_no_skill"}


def test_optional_fields_absent_supported():
    rows = panel()
    for row in rows:
        del row["phase"], row["round"]
    assert summary(rows)["task_instances"] == 12


def test_budget_is_assumption_not_evidence_multiplier():
    small = rough_family_budget(effect_size=0.05, discordance=0.2)
    large = rough_family_budget(effect_size=0.1, discordance=0.2)
    assert small["approximate_independent_families"] >= 4 * large["approximate_independent_families"] - 3
    assert small["not_a_formal_power_or_safety_guarantee"]
    assert small["does_not_multiply_evidence_by_variants_or_histories"]


@pytest.mark.parametrize("kwargs", [{"effect_size": 0}, {"effect_size": True},
    {"effect_size": float("nan")}, {"effect_size": 0.3}, {"discordance": 2},
    {"target_power": 0.5}, {"alpha": 0}, {"alpha": float("inf")}])
def test_invalid_budget_assumptions(kwargs):
    arguments = {"effect_size": 0.05, "discordance": 0.2, **kwargs}
    with pytest.raises(ValueError):
        rough_family_budget(**arguments)
