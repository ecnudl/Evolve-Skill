from copy import deepcopy

import pytest

from skillopt.coevolution_v7 import analysis as a
from skillopt.validator_pilot.api import digest


def rows():
    result = []
    for task in range(3):
        for history in range(2):
            for policy in a.POLICIES:
                shared = "fixed_validator_candidate" if policy == "gated_validator_candidate" else policy
                key = digest([task, history, shared])
                result.append({"task_id": str(task), "cluster_id": "family-" + str(task), "history": history,
                    "repeat": 0, "domain": "coding", "policy": policy, "score": 1.0,
                    "artifact_hash": digest("same correct contents"), "request_hashes": [key],
                    "all_solver_stages_api_ok": True, "outcome_category": "correct"})
    return result


def test_shared_candidate_alias_not_independent_observation():
    values = rows()
    summary = a.summarize(values, expected={(r["task_id"], r["history"], r["policy"]) for r in values})
    result = summary["comparisons"]["gated_validator_candidate_vs_fixed_validator_candidate"]
    assert result["shared_trajectory_pairs"] == 6
    assert result["both_available"] == {"n": 6, "wins": 0, "losses": 0, "ties": 6, "mean_delta": 0.0}
    assert result["all_attempt_cluster_inference"]["clusters"] == 3


def test_unknown_not_counted_as_semantic_gain():
    values = rows()
    baseline = next(r for r in values if r["policy"] == "no_skill")
    baseline.update(score=None, outcome_category="transport_unavailable", all_solver_stages_api_ok=False)
    result = a.compare(values, "research_candidate_shadow", "no_skill")
    assert result["all_attempt"]["wins"] == 1
    assert result["both_available"]["wins"] == 0
    assert result["missing_pairs"] == 1


def test_recovered_transport_stages_are_separate_diagnostic():
    values = rows()
    base = next(r for r in values if r["policy"] == "no_skill")
    base["all_solver_stages_api_ok"] = False
    result = a.compare(values, "research_candidate_shadow", "no_skill")
    assert result["both_available"]["n"] == 6
    assert result["all_stages_api_delivery_success_diagnostic"]["n"] == 5


def test_semantic_negative_transfer_stays_a_loss():
    values = rows()
    candidate = next(r for r in values if r["policy"] == "research_candidate_shadow")
    candidate.update(score=0.0, outcome_category="semantic_failure")
    result = a.compare(values, "research_candidate_shadow", "no_skill")
    assert result["both_available"]["losses"] == 1
    assert result["all_attempt"]["losses"] == 1


def test_shared_trajectory_cannot_receive_different_scores():
    values = rows()
    next(r for r in values if r["policy"] == "gated_validator_candidate")["score"] = 0.0
    with pytest.raises(ValueError, match="Shared trajectory"):
        a.compare(values, "gated_validator_candidate", "fixed_validator_candidate")


def test_missing_position_and_duplicates_rejected():
    values = rows()
    expected = {(r["task_id"], r["history"], r["policy"]) for r in values}
    for damaged in (values[:-1], values + [deepcopy(values[0])]):
        with pytest.raises(ValueError, match="grid"):
            a.summarize(damaged, expected=expected)


def test_pair_cluster_mismatch_rejected():
    values = rows()
    next(r for r in values if r["policy"] == "research_candidate_shadow")["cluster_id"] = "wrong"
    with pytest.raises(ValueError, match="inconsistent"):
        a.compare(values, "research_candidate_shadow", "no_skill")
