from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.coevolution_v6.analysis import summarize_repairs, summarize_transfer
from skillopt.coevolution_v6.experiment import portfolio_outcome, selected_feedback


def rows():
    result = []
    for history in range(3):
        for index, category in enumerate(("same_mechanism", "near_miss", "unrelated")):
            for policy in ("no_skill", "always_candidate", "mechanism_routed_candidate"):
                applied = policy == "always_candidate" or policy == "mechanism_routed_candidate" and index == 0
                score = 0.0 if applied and index == 1 else 1.0
                result.append({"policy": policy, "task_id": f"task-{index}", "cluster_id": f"family-{index}",
                    "domain": "coding", "history": history, "evaluation_group": category,
                    "score": score, "request_hashes": [f"request-{history}-{index}-{applied}"],
                    "artifact_hash": f"artifact-{history}-{index}-{applied}", "skill_hash": "skill" if applied else "base",
                    "route": {"apply": index == 0}, "fallback": not applied,
                    "case_results": [{"id": "native", "passed": bool(score)}]})
    return result


def test_structural_routing_avoids_loss_without_claiming_independent_rows():
    result = summarize_transfer(rows())
    verify(result)
    assert result["routing_counterfactual"] == {"avoided_loss_positions": 3, "forgone_gain_positions": 0}
    assert result["policy_summary"]["mechanism_routed_candidate"]["domains"]["coding"]["skill_application_rate"] == pytest.approx(1 / 3)
    assert result["paired_vs_no_skill"]["always_candidate"]["confirmed_case_losses"] == 3
    assert result["paired_vs_no_skill"]["always_candidate"]["overall_cluster_diagnostic"]["clusters"] == 3
    assert result["logical_rows"] == 27 and result["unique_trajectory_receipts"] == 18


@pytest.mark.parametrize("change", ["missing_policy", "missing_history", "duplicate", "wrong_route", "group", "score", "identity"])
def test_bad_transfer_grids_fail_closed(change):
    values = rows()
    if change == "missing_policy":
        values.pop()
    elif change == "missing_history":
        values = [r for r in values if not (r["task_id"] == "task-0" and r["history"] == 2)]
    elif change == "duplicate":
        values.append(deepcopy(values[0]))
    elif change == "wrong_route":
        values[2]["request_hashes"] = ["wrong-intervention"]
    elif change == "group":
        values[0]["evaluation_group"] = "unknown"
    elif change == "score":
        values[0]["score"] = float("nan")
    else:
        values[0]["cluster_id"] = "different"
    with pytest.raises(ValueError):
        summarize_transfer(values)


def test_unknown_is_reported_not_silently_dropped_from_primary_yield():
    values = rows()
    for row in values:
        if row["task_id"] == "task-0" and row["history"] == 0:
            row["score"] = None
            row["case_results"] = []
    result = summarize_transfer(values)
    record = result["policy_summary"]["no_skill"]["domains"]["coding"]
    assert record["unavailable"] == 1
    assert record["all_attempt_yield"] == pytest.approx(8 / 9)
    assert record["available_score_mean"] == 1.0


def component(status):
    return {"assessments": [{"check_id": "coding_contract", "status": "pass", "verified": True},
                            {"check_id": "coding_probe", "status": status, "verified": status != "unknown"}]}


@pytest.mark.parametrize("first,second,expected", [
    ("fail", "pass", "detected"), ("pass", "fail", "detected"), ("fail", "unknown", "detected"),
    ("pass", "unknown", "unknown"), ("unknown", "unknown", "unknown"), ("pass", "pass", "not_detected")])
def test_portfolio_retains_verified_counterexamples_without_inventing_passes(first, second, expected):
    assert portfolio_outcome([component(first), component(second)]) == expected


def test_feedback_context_selection_rejects_unsealed_or_forbidden_packets():
    with pytest.raises(ValueError):
        selected_feedback([{"record_hash": "tampered", "observations": []}])


def test_repair_summary_reports_authored_origin_and_true_sampling_units():
    result = summarize_repairs([{"task_id": "a", "cluster_id": "project", "history": 0, "result": {"arms": {
        "score_only": {"metrics": {"repair_success": None}, "new_passing_check_losses": []},
        "structured_evidence": {"metrics": {"repair_success": True}, "new_passing_check_losses": []}}}}])
    assert result["arms"]["score_only"]["unknown_repairs"] == 1
    assert result["arms"]["structured_evidence"]["successful_repairs"] == 1
    assert result["clusters"] == 1 and result["small_cluster_count_not_efficacy_proof"]
