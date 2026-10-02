"""Engineering fixtures, not observed model or generalization results."""
from copy import deepcopy

import pytest

from skillopt.continual_eval.metrics import summarize


def fixture():
    order = ["coding", "sheets", "qa", "rules", "actions"]
    tasks = [{"benchmark": name, "task_id": f"{name}/0", "family_id": f"{name}/family",
              "partition": "final", "project_id": ""} for name in order]
    checkpoints = [{"method": "ours", "history": "h0", "stage": stage,
                    "checkpoint_hash": f"checkpoint-{stage}"} for stage in range(6)]
    plan = {"order": order, "repeats": 2, "tasks": tasks, "checkpoints": checkpoints}
    rows = [{"method": "ours", "history": "h0", "stage": stage, **task, "repeat": repeat,
             "status": "pass", "score": .5 + stage * .05, "reason": "fixture",
             "costs": {"calls": 1, "tokens": 10}, "prediction_hash": f"{stage}/{task['task_id']}/{repeat}"}
            for stage in range(6) for task in tasks for repeat in range(2)]
    return plan, rows


def test_complete_five_benchmark_matrix_and_transfer():
    plan, rows = fixture()
    result = summarize(plan, rows)
    run = result["runs"][0]
    assert result["status"] == "complete"
    assert result["expected_positions"] == 60
    assert result["tasks"] == result["declared_families"] == 5
    assert result["costs"] == {"calls": 60, "tokens": 600}
    assert list(run["matrix"]) == [str(n) for n in range(6)]
    assert run["stage_metrics"][-1]["macro_score_all_attempt_lower_bound"] == .75
    assert run["forward_transfer"]["value"] == pytest.approx(.125)
    assert run["backward_transfer"]["value"] == pytest.approx(.125)
    assert run["stage_metrics"][-1]["macro_delta_vs_stage0"] == pytest.approx(.25)
    assert run["stage_metrics"][-1]["negative_domain_count_vs_stage0"] == 0
    assert run["pairs"]["vs_stage0"][-1]["win"] == 2
    assert result["limitations"]["statistical_significance_claimed"] is False


def test_missing_is_not_zero_or_silently_removed():
    plan, rows = fixture()
    result = summarize(plan, rows[:-1])
    run = result["runs"][0]
    cell = run["matrix"]["5"]["actions"]
    assert result["status"] == cell["status"] == "pending"
    assert cell["missing_positions"] == 1
    assert cell["counts"] == {"pass": 1, "fail": 0, "unknown": 0}
    assert cell["score_all_attempt_lower_bound"] is None
    assert cell["observed_attempt_lower_bound"] == {"numerator": .75, "denominator": 1, "value": .75}
    assert run["stage_metrics"][-1]["macro_score_all_attempt_lower_bound"] is None
    assert run["stage_metrics"][-1]["negative_domain_count_vs_stage0"] is None
    pair = run["pairs"]["vs_previous"][-1]
    assert pair["unknown"] == pair["missing_pairs"] == 1
    assert pair["observed_unknown_pairs"] == 0


def test_terminal_unknown_keeps_denominator_and_is_not_fail():
    plan, rows = fixture()
    rows[-1].update(status="unknown", score=None, reason="timeout")
    result = summarize(plan, rows)
    cell = result["runs"][0]["matrix"]["5"]["actions"]
    assert result["status"] == cell["status"] == "complete"
    assert cell["counts"] == {"pass": 1, "fail": 0, "unknown": 1}
    assert cell["score_all_attempt_lower_bound"] == .375
    assert cell["score_all_attempt_upper_bound"] == .875
    assert cell["score_evaluable"]["value"] == .75
    assert cell["evaluable_coverage"]["value"] == .5
    pair = result["runs"][0]["pairs"]["vs_stage0"][-1]
    assert pair["observed_unknown_pairs"] == 1
    assert pair["missing_pairs"] == 0


def test_unknown_and_missing_propagate_only_to_required_transfer_cells():
    plan, rows = fixture()
    rows = [row for row in rows if not (row["stage"] == 2 and row["benchmark"] == "qa")]
    run = summarize(plan, rows)["runs"][0]
    assert run["forward_transfer"]["status"] == "pending"
    assert run["forward_transfer"]["value"] is None
    assert run["backward_transfer"]["status"] == "complete"


def test_task_counts_do_not_multiply_with_repeats_and_empty_grid_is_pending():
    plan, _ = fixture()
    result = summarize(plan, [])
    assert result["observed_positions"] == 0
    assert result["missing_positions"] == 60
    cell = result["runs"][0]["matrix"]["0"]["qa"]
    assert cell["tasks"] == cell["declared_families"] == 1
    assert cell["expected_positions"] == 2
    assert cell["score_evaluable"]["value"] is None


@pytest.mark.parametrize("mutation, message", [
    (lambda p, r: r.append(deepcopy(r[0])), "Duplicate observed"),
    (lambda p, r: r[0].update(task_id="unexpected"), "outside frozen task"),
    (lambda p, r: r[0].update(repeat=2), "Repeat outside"),
    (lambda p, r: r[0].update(repeat=True), "Repeat outside"),
    (lambda p, r: r[0].update(family_id="changed"), "family differs"),
    (lambda p, r: r[0].update(checkpoint_hash="changed"), "checkpoint hash differs"),
    (lambda p, r: r[0].update(score=float("nan")), "finite"),
    (lambda p, r: r[0].update(score=True), "finite"),
    (lambda p, r: r[0].update(status="unknown"), "Unknown must not"),
    (lambda p, r: r[0].update(score=1.1), "normalized"),
    (lambda p, r: r[0].update(costs={"tokens": -1}), "finite"),
    (lambda p, r: p["checkpoints"].pop(), "explicit stages"),
    (lambda p, r: p["tasks"].append(deepcopy(p["tasks"][0])), "Duplicate frozen task"),
    (lambda p, r: p["order"].__setitem__(0, "qa"), "Duplicate benchmark"),
])
def test_invalid_rosters_and_observations_rejected(mutation, message):
    plan, rows = fixture()
    mutation(plan, rows)
    with pytest.raises(ValueError, match=message):
        summarize(plan, rows)


def test_multiple_methods_and_histories_not_pooled_as_extra_tasks():
    plan, rows = fixture()
    checkpoints = deepcopy(plan["checkpoints"])
    other_rows = deepcopy(rows)
    for checkpoint in checkpoints:
        checkpoint.update(method="fixed", history="h1")
    for row in other_rows:
        row.update(method="fixed", history="h1", score=.4)
    plan["checkpoints"] += checkpoints
    result = summarize(plan, rows + other_rows)
    assert len(result["runs"]) == 2
    assert result["tasks"] == 5
    assert result["expected_positions"] == 120
    assert result["runs"][0]["forward_transfer"]["value"] == 0


def test_known_pair_losses_ties_and_negative_domains():
    plan, rows = fixture()
    for row in rows:
        if row["stage"] == 5 and row["benchmark"] == "actions":
            row.update(status="fail", score=0 if row["repeat"] == 0 else .5)
    run = summarize(plan, rows)["runs"][0]
    pair = run["pairs"]["vs_stage0"][-1]
    assert (pair["win"], pair["loss"], pair["tie"], pair["unknown"]) == (0, 1, 1, 0)
    assert run["stage_metrics"][-1]["worst_domain_delta_vs_stage0"] == -.25
    assert run["stage_metrics"][-1]["negative_domain_count_vs_stage0"] == 1


def test_unregistered_checkpoint_slots_and_missing_panels_remain_pending():
    plan, _ = fixture()
    for checkpoint in plan["checkpoints"]:
        checkpoint["checkpoint_hash"] = None
    plan["tasks"] = []
    result = summarize(plan, [])
    assert result["status"] == "pending"
    assert result["unavailable_benchmarks"] == plan["order"]
    cell = result["runs"][0]["matrix"]["0"]["qa"]
    assert cell["status"] == "pending"
    assert cell["score_all_attempt_lower_bound"] is None
    assert cell["task_roster_available"] is False
    assert result["runs"][0]["stage_metrics"][0]["macro_score_all_attempt_lower_bound"] is None


def test_observations_cannot_attach_to_unregistered_checkpoint():
    plan, rows = fixture()
    plan["checkpoints"][0]["checkpoint_hash"] = None
    with pytest.raises(ValueError, match="registered checkpoint"):
        summarize(plan, rows)


def test_cost_unknown_and_completeness_are_not_summed_as_zero_or_integers():
    plan, rows = fixture()
    for row in rows:
        row["costs"] = {"logical_calls": 1, "http_attempts": 1, "reported_tokens": 10,
                        "usage_complete": True, "retry_inclusive_usage_known": True}
    rows[-1]["costs"].update(reported_tokens=None, usage_complete=False,
                            retry_inclusive_usage_known=False, http_attempts=2)
    result = summarize(plan, rows)
    assert result["costs"] == {"logical_calls": 60, "http_attempts": 61, "reported_tokens": None}
    assert result["cost_known_subtotals"]["reported_tokens"] == 590
    assert result["cost_unknown_positions"]["reported_tokens"] == 1
    assert result["cost_completeness"] == {"usage_complete": False, "retry_inclusive_usage_known": False}
    cell = result["runs"][0]["matrix"]["5"]["actions"]
    assert cell["costs"]["reported_tokens"] is None
    assert cell["cost_known_subtotals"]["reported_tokens"] == 10


def test_missing_cost_key_is_not_a_complete_zero_cost_observation():
    plan, rows = fixture()
    rows[-1]["costs"].pop("tokens")
    result = summarize(plan, rows)
    assert result["costs"]["tokens"] is None
    assert result["cost_known_subtotals"]["tokens"] == 590
    assert result["cost_unknown_positions"]["tokens"] == 1


def test_cost_completeness_flags_require_actual_booleans():
    plan, rows = fixture()
    rows[0]["costs"]["usage_complete"] = 1
    with pytest.raises(ValueError, match="must be boolean"):
        summarize(plan, rows)


def _add_method(plan, rows, method, score, *, history="h0"):
    checkpoints = [deepcopy(cp) for cp in plan["checkpoints"] if cp["method"] == "ours"]
    observations = [deepcopy(row) for row in rows if row["method"] == "ours"]
    for checkpoint in checkpoints:
        checkpoint.update(method=method, history=history)
    for row in observations:
        row.update(method=method, history=history, score=score)
    plan["checkpoints"] += checkpoints
    rows += observations


def test_cross_method_comparisons_use_no_skill_stage0_and_same_stage_skillopt():
    plan, rows = fixture()
    _add_method(plan, rows, "no_skill", .4)
    _add_method(plan, rows, "skillopt", .6)
    # Later No-Skill stages deliberately differ: the reference must remain s0.
    for row in rows:
        if row["method"] == "no_skill" and row["stage"] > 0:
            row["score"] = .9
    result = summarize(plan, rows)
    ours = next(run for run in result["runs"] if run["method"] == "ours")
    comparisons = ours["cross_method_pairs"]
    no_skill = comparisons["vs_no_skill_stage0"]["by_stage"][5]
    skillopt = comparisons["vs_skillopt_same_stage"]["by_stage"][5]
    assert no_skill["reference_stage"] == 0
    assert no_skill["macro_native_mean_delta_all_attempt_lower_bound"] == pytest.approx(.35)
    assert skillopt["reference_stage"] == 5
    assert skillopt["macro_native_mean_delta_all_attempt_lower_bound"] == pytest.approx(.15)
    assert all(pair["win"] == 2 for pair in no_skill["pairs"])
    assert no_skill["pairs"][0]["reference_method"] == "no_skill"
    assert no_skill["pairs"][0]["reference_history"] == "h0"


def test_cross_method_missing_reference_cell_stays_pending_without_imputation():
    plan, rows = fixture()
    _add_method(plan, rows, "no_skill", .4)
    rows = [row for row in rows if not (row["method"] == "no_skill" and row["stage"] == 0
                                       and row["benchmark"] == "qa" and row["repeat"] == 1)]
    ours = next(run for run in summarize(plan, rows)["runs"] if run["method"] == "ours")
    stage = ours["cross_method_pairs"]["vs_no_skill_stage0"]["by_stage"][5]
    assert stage["status"] == "pending"
    assert stage["macro_native_mean_delta_all_attempt_lower_bound"] is None
    pair = next(pair for pair in stage["pairs"] if pair["benchmark"] == "qa")
    assert pair["missing_reference_positions"] == pair["unknown"] == 1
    assert pair["win"] == 1
    assert pair["native_mean_delta_all_attempt_lower_bound"] is None


def test_cross_method_reference_does_not_borrow_other_history_or_own_stage0():
    plan, rows = fixture()
    _add_method(plan, rows, "no_skill", .4, history="h1")
    ours = next(run for run in summarize(plan, rows)["runs"] if run["method"] == "ours")
    comparison = ours["cross_method_pairs"]["vs_no_skill_stage0"]
    assert comparison["reference_registered"] is False
    assert comparison["status"] == "pending"
    assert comparison["by_stage"] == []
    assert "vs_skillopt_same_stage" not in ours["cross_method_pairs"]


def test_cross_method_unknown_keeps_pair_unknown_and_cost_independent():
    plan, rows = fixture()
    _add_method(plan, rows, "no_skill", .4)
    for row in rows:
        if row["method"] == "no_skill" and row["stage"] == 0 and row["benchmark"] == "qa" and row["repeat"] == 1:
            row.update(status="unknown", score=None, reason="timeout")
    ours = next(run for run in summarize(plan, rows)["runs"] if run["method"] == "ours")
    stage = ours["cross_method_pairs"]["vs_no_skill_stage0"]["by_stage"][5]
    pair = next(pair for pair in stage["pairs"] if pair["benchmark"] == "qa")
    assert pair["status"] == "complete"
    assert pair["unknown"] == pair["observed_unknown_pairs"] == 1
    assert pair["win"] == 1
    assert pair["known_pair_mean_delta"]["value"] == pytest.approx(.35)
    assert pair["native_mean_delta_all_attempt_lower_bound"] == pytest.approx(.55)
