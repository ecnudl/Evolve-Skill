"""Pure, offline tests for V17 projection, scope decisions and analysis."""

from copy import deepcopy

import pytest

from skillopt.coevolution_v17.core import analyze, empirical_gate, feedback_views, flatten_feedback


def facts():
    return [{"phase": "development", "task_id": task, "domain": domain, "role": role,
             "mechanism_cell": "SECRET_LABEL", "structural_family": "HOST_FAMILY",
             "cell": "near_miss", "artifact_valid": True, "oracle_available": True,
             "passed": False, "checks": [{"id": "actual-check", "passed": False}],
             "public_contract": {"preserve": ["public declared obligation"]}}
            for task, domain, role in [("t2", "spreadsheet", "current"),
                                      ("t1", "coding", "no_skill"),
                                      ("t2", "spreadsheet", "no_skill"),
                                      ("t1", "coding", "current")]]


def gate_rows():
    return [{"phase": "calibration", "task_id": domain + "-" + cell,
             "history": 0, "domain": domain, "cell": cell, "arm": arm,
             "artifact_valid": True, "oracle_available": True,
             "passed": not (domain == "spreadsheet" and cell == "same_mechanism" and arm != "candidate")}
            for domain in ("coding", "spreadsheet") for cell in ("same_mechanism", "near_miss")
            for arm in ("no_skill", "parent", "candidate")]


def final_rows(histories=(0, 1)):
    rows = []
    for domain in ("coding", "spreadsheet"):
        for family in ("a", "b"):
            for h in histories:
                for arm in ("no_skill", "local", "cross"):
                    rows.append({"phase": "final", "task_id": domain + family,
                                 "history": h, "domain": domain,
                                 "structural_family": family, "cell": "same_mechanism",
                                 "arm": arm, "artifact_valid": True, "oracle_available": True,
                                 "passed": (family == "a" or arm == "cross")})
    return rows


def test_feedback_information_and_order_are_identical():
    records = facts()
    original = deepcopy(records)
    raw, structured = feedback_views(records, "raw"), feedback_views(records, "structured")
    assert flatten_feedback(raw) == flatten_feedback(structured)
    assert records == original
    assert "SECRET_LABEL" not in str(raw) + str(structured)
    assert "HOST_FAMILY" not in str(raw) + str(structured)
    assert "near_miss" not in str(raw) + str(structured)
    assert flatten_feedback(structured)[0]["checks"] == records[0]["checks"]
    assert flatten_feedback(structured)[0]["public_contract"] == records[0]["public_contract"]


@pytest.mark.parametrize("phase", ["calibration", "final", "selection", None])
def test_feedback_refuses_other_phases(phase):
    records = facts()
    records[0]["phase"] = phase
    with pytest.raises(ValueError):
        feedback_views(records, "structured")


def test_feedback_rejects_unknown_mode_nonjson_and_bad_roles():
    with pytest.raises(ValueError):
        feedback_views(facts(), "invent_advice")
    records = facts()
    records[0]["checks"] = float("nan")
    with pytest.raises(ValueError):
        feedback_views(records, "raw")
    records = facts()
    records[0]["role"] = "gold"
    with pytest.raises(ValueError):
        feedback_views(records, "raw")


def test_flatten_checks_actual_group_identity_and_unique_position():
    view = feedback_views(facts(), "structured")
    bad = deepcopy(view)
    bad["groups"][0]["domain"] = "coding"
    with pytest.raises(ValueError):
        flatten_feedback(bad)
    bad = deepcopy(view)
    roles = bad["groups"][0]["tasks"][0]["roles"]
    roles[1]["records"][0]["position"] = roles[0]["records"][0]["position"]
    with pytest.raises(ValueError):
        flatten_feedback(bad)


def test_gate_cross_commit_routes_whole_domain_but_not_unseen_rule():
    result = empirical_gate(gate_rows())
    assert result["decision"] == "cross_domain_commit"
    assert result["scope"] == "cross_domain"
    assert result["deployment_mapping"]["spreadsheet"] == "candidate"
    assert result["deployment_mapping"]["coding"] == "candidate"
    assert result["deployment_mapping"]["rule_reasoning"] == "no_skill"
    assert result["deployment_domains"] == ["coding", "spreadsheet"]
    assert result["unseen_domain_default"] == "no_skill"
    assert result["statistical_safety_claim"] is False


def test_gate_transfer_gain_against_parent_alone_is_insufficient():
    rows = gate_rows()
    for row in rows:
        if row["arm"] == "no_skill":
            row["passed"] = True
    result = empirical_gate(rows)
    assert result["decision"] == "restrict_parent"
    assert result["scope"] == "no_skill"
    assert all(value == "no_skill" for value in result["deployment_mapping"].values())


def test_gate_source_gain_can_commit_only_local_despite_target_harm():
    rows = gate_rows()
    for row in rows:
        row["passed"] = True
        if row["domain"] == "coding" and row["cell"] == "same_mechanism":
            row["passed"] = row["arm"] == "candidate"
        if row["domain"] == "spreadsheet" and row["arm"] == "candidate":
            row["passed"] = False
    result = empirical_gate(rows)
    assert result["decision"] == "local_commit"
    assert result["deployment_mapping"]["coding"] == "candidate"
    assert result["deployment_mapping"]["spreadsheet"] == "no_skill"
    assert result["deployment_domains"] == ["coding"]


def test_gate_no_cross_domain_score_cancellation():
    rows = gate_rows()
    next(row for row in rows if row["domain"] == "coding" and row["arm"] == "candidate")["passed"] = False
    assert empirical_gate(rows)["decision"] == "reject"


@pytest.mark.parametrize("field,value", [("oracle_available", False), ("artifact_valid", None), ("passed", None)])
def test_gate_unknown_fails_closed(field, value):
    rows = gate_rows()
    rows[0].update(passed=False, oracle_available=False)
    rows[0][field] = value
    result = empirical_gate(rows)
    assert result["decision"] == "reject"
    assert result["reason"] == "unknown_evidence_cannot_approve_scope"


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "wrong_phase", "multiple_histories", "missing_cell"])
def test_gate_rejects_bad_panels(mutation):
    rows = gate_rows()
    if mutation == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif mutation == "missing":
        rows.pop()
    elif mutation == "wrong_phase":
        rows[0]["phase"] = "development"
    elif mutation == "multiple_histories":
        rows += [{**row, "history": 1} for row in rows]
    else:
        rows = [row for row in rows if row["task_id"] != "coding-near_miss"]
    with pytest.raises(ValueError):
        empirical_gate(rows)


def test_analysis_complete_paired_values_and_reproducibility():
    rows = final_rows()
    result = analyze(rows)
    assert result == analyze(list(reversed(rows)))
    assert result["unique_tasks"] == 4
    assert result["arms"]["cross"]["macro_success_rate"] == 1
    assert result["arms"]["no_skill"]["macro_success_rate"] == 0.5
    paired = result["comparisons"]["cross_vs_no_skill"]
    assert paired["paired"]["wins"] == 4
    assert paired["paired"]["losses"] == 0
    assert paired["worst_domain_delta"] == 0.5
    assert result["bootstrap"]["samples"] == 1000
    assert result["bootstrap"]["histories_resampled_as_independent_tasks"] is False


def test_repeating_identical_histories_does_not_narrow_family_interval():
    once = analyze(final_rows((0,)))
    repeated = analyze(final_rows((0, 1, 2, 3, 4)))
    assert once["comparisons"]["cross_vs_no_skill"]["macro_delta_ci95"] == repeated["comparisons"]["cross_vs_no_skill"]["macro_delta_ci95"]
    assert once["comparisons"]["cross_vs_no_skill"]["worst_domain_delta_ci95"] == repeated["comparisons"]["cross_vs_no_skill"]["worst_domain_delta_ci95"]


def test_failures_separated_without_dropping_unknown():
    rows = final_rows()
    cross = [row for row in rows if row["arm"] == "cross"]
    cross[0].update(passed=False)
    cross[1].update(passed=False, artifact_valid=False, oracle_available=False)
    cross[2].update(passed=None, artifact_valid=None, oracle_available=False)
    cross[3].update(passed=None, artifact_valid=True, oracle_available=False)
    summary = analyze(rows)["arms"]["cross"]
    assert summary["attempts"] == 8
    assert summary["successes"] == 4
    assert summary["semantic_failures"] == 1
    assert summary["delivery_failures"] == 1
    assert summary["delivery_unknown"] == 1
    assert summary["execution_unknown"] == 1


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "metadata", "phase", "bad_success", "no_family"])
def test_analysis_rejects_incomplete_or_inconsistent_grid(mutation):
    rows = final_rows()
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif mutation == "metadata":
        rows[0]["domain"] = "wrong"
    elif mutation == "phase":
        rows[0]["phase"] = "development"
    elif mutation == "bad_success":
        rows[0].update(passed=True, oracle_available=False)
    else:
        del rows[0]["structural_family"]
    with pytest.raises(ValueError):
        analyze(rows)


def test_explicit_manifest_detects_an_entire_omitted_task():
    rows = final_rows()
    tasks = sorted({row["task_id"] for row in rows})
    arms = sorted({row["arm"] for row in rows})
    result = analyze(rows, expected_tasks=tasks, expected_arms=arms, expected_histories=[0, 1])
    assert result["manifest_checked"] is True
    filtered = [row for row in rows if row["task_id"] != tasks[0]]
    with pytest.raises(ValueError):
        analyze(filtered, expected_tasks=tasks, expected_arms=arms, expected_histories=[0, 1])


def test_analysis_is_input_immutable():
    rows = final_rows()
    before = deepcopy(rows)
    analyze(rows)
    assert rows == before


def test_analysis_includes_preregistered_learning_contrasts():
    rows = final_rows()
    for row in rows:
        row["arm"] = {"local": "local_feedback", "cross": "cross_raw_feedback"}.get(row["arm"], row["arm"])
    rows += [{**row, "arm": "cross_structured_feedback"} for row in rows if row["arm"] == "cross_raw_feedback"]
    result = analyze(rows)
    assert result["comparisons"]["cross_raw_feedback_vs_local_feedback"]["macro_delta"] == 0.5
    assert result["comparisons"]["cross_structured_feedback_vs_cross_raw_feedback"]["macro_delta"] == 0


def test_local_commit_checks_near_miss_even_when_source_mechanism_wins():
    rows = gate_rows()
    for row in rows:
        row["passed"] = not (row["domain"] == "coding" and row["cell"] == "same_mechanism" and row["arm"] != "candidate")
        if row["domain"] == "coding" and row["cell"] == "near_miss" and row["arm"] == "candidate":
            row["passed"] = False
    assert empirical_gate(rows)["decision"] == "reject"
