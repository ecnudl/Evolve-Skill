"""Handwritten metric fixtures, not model performance or safety evidence."""
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation.mechanism_metrics import IDENTITY, REGIONS, summarize
from skillopt.validator_pilot.api import digest


def row(task, condition, status="pass", *, family=None, region="target_related", history="h0",
        repeat=0, exposure="raw", applied=None, domain="coding"):
    return {
        "history": history, "task_id": task, "family_id": family or task, "domain": domain,
        "region": region, "repeat": repeat, "condition": condition, "exposure": exposure,
        "status": status, "skill_applied": condition not in {"no_skill", "current"} if applied is None else applied,
    }


def manifest(rows):
    return [{key: record[key] for key in IDENTITY} for record in rows]


def report(rows, expected=None, **kwargs):
    return summarize(rows, manifest(rows) if expected is None else expected, bootstrap_samples=40, **kwargs)


def four_regions():
    statuses = {
        "target_related": ("fail", "fail", "fail", "pass"),
        "near_miss": ("pass", "pass", "fail", "pass"),
        "boundary_control": ("pass", "pass", "pass", "pass"),
        "unrelated": ("pass", "pass", "pass", "unknown"),
    }
    return [row(region, condition, status, region=region, exposure=exposure)
            for exposure in ("raw", "conditional")
            for region in REGIONS
            for condition, status in zip(("no_skill", "current", "local", "mechanism"), statuses[region])]


def test_four_groups_two_exposures_and_direct_method_comparison():
    result = report(four_regions())
    verify(result)
    assert result["expected_positions"] == result["observed_positions"] == 32
    for exposure in ("raw", "conditional"):
        pair = result["comparisons"][f"{exposure}/mechanism_vs_no_skill"]
        assert [pair[k] for k in ("win", "loss", "tie", "unknown")] == [1, 0, 2, 1]
        assert set(pair["by_region"]) == set(REGIONS)
        assert pair["by_region"]["target_related"]["win"] == 1
        assert pair["by_region"]["unrelated"]["unknown"] == 1
        assert pair["baseline_correct_to_fail"] == {"numerator": 0, "denominator": 3, "value": 0}
        assert pair["baseline_correct_to_unknown"]["value"] == 1 / 3
        direct = result["comparisons"][f"{exposure}/mechanism_vs_local"]
        assert direct["win"] == 2
        arm = result["arms"][f"{exposure}/mechanism"]
        assert arm["counts"] == {"pass": 3, "fail": 0, "unknown": 1}
        assert arm["all_attempt_success"]["value"] == arm["known_coverage"]["value"] == .75
    for key in ("deployment_authorized", "skill_admission_authorized", "cross_domain_authorized",
                "formal_noninferiority_established"):
        assert result[key] is False


def test_zero_net_delta_still_reports_a_real_regression():
    rows = []
    for task, baseline, candidate in (("repair", "fail", "pass"), ("damage", "pass", "fail")):
        rows += [row(task, condition, baseline) for condition in ("no_skill", "current")]
        rows.append(row(task, "mechanism", candidate))
    pair = report(rows)["comparisons"]["raw/mechanism_vs_no_skill"]
    assert pair["all_attempt_delta"] == 0
    assert pair["win"] == pair["loss"] == 1
    assert pair["baseline_correct_to_fail"] == {"numerator": 1, "denominator": 1, "value": 1}
    assert pair["regression_task_count"] == pair["regression_family_count"] == 1


def test_all_fallback_is_zero_usage_not_successful_learning():
    rows = [row("one", condition, exposure="conditional", applied=False)
            for condition in ("no_skill", "current", "local", "mechanism")]
    result = report(rows, min_families=1, min_histories=1)
    arm = result["arms"]["conditional/mechanism"]
    assert arm["all_attempt_success"]["value"] == 1
    assert arm["skill_application_coverage"]["value"] == 0
    assert arm["fallback_or_empty_positions"] == 1
    assert arm["learning_gain_established"] is False
    ni = result["comparisons"]["conditional/mechanism_vs_no_skill"]["noninferiority_diagnostic"]
    assert ni["status"] == "pending"
    assert ni["descriptive_lower_exceeds_negative_margin"] is None
    assert "degenerate_bootstrap_does_not_establish_noninferiority" in ni["insufficient_evidence"]


def test_missing_rows_are_unknown_and_cannot_pass_diagnostic_screen():
    complete = [row(task, condition) for task in ("a", "b")
                for condition in ("no_skill", "current", "mechanism")]
    expected = manifest(complete)
    rows = [r for r in complete if not (r["task_id"] == "b" and r["condition"] == "mechanism")]
    result = report(rows, expected, min_families=1, min_histories=1)
    assert result["missing_positions"] == 1 and len(result["missing_keys"]) == 1
    arm = result["arms"]["raw/mechanism"]
    assert arm["positions"] == 2 and arm["counts"] == {"pass": 1, "fail": 0, "unknown": 1}
    assert arm["application_unknown_positions"] == 1
    pair = result["comparisons"]["raw/mechanism_vs_no_skill"]
    assert pair["positions"] == 2 and pair["unknown"] == 1 and pair["loss"] == 0
    assert pair["missing_candidate_positions"] == 1 and pair["all_attempt_delta"] == -.5
    assert pair["baseline_correct_to_fail"]["numerator"] == 0
    assert pair["baseline_correct_to_unknown"]["numerator"] == 1
    assert "missing_positions" in pair["noninferiority_diagnostic"]["insufficient_evidence"]
    assert pair["noninferiority_diagnostic"]["descriptive_lower_exceeds_negative_margin"] is None


def test_missing_baseline_and_explicit_unknown_are_not_confirmed_losses():
    complete = [row(task, condition, "unknown" if task == "a" else "pass") for task in ("a", "b")
                for condition in ("no_skill", "current", "mechanism")]
    rows = [r for r in complete if not (r["task_id"] == "b" and r["condition"] == "no_skill")]
    pair = report(rows, manifest(complete))["comparisons"]["raw/mechanism_vs_no_skill"]
    assert pair["unknown"] == 2 and pair["missing_baseline_positions"] == 1
    assert pair["loss"] == pair["win"] == pair["tie"] == 0
    assert pair["baseline_correct_to_fail"]["denominator"] == 0


def test_repeated_tasks_and_histories_do_not_create_families():
    rows = [row(f"task{task}", condition, family="one-family", history=f"h{history}", repeat=repeat)
            for task in range(4) for history in range(3) for repeat in range(2)
            for condition in ("no_skill", "current", "mechanism")]
    pair = report(rows)["comparisons"]["raw/mechanism_vs_no_skill"]
    assert pair["positions"] == 24
    assert pair["family_equal_delta_ci"]["declared_family_count"] == 1
    assert pair["family_equal_delta_ci"]["task_count"] == 4
    assert pair["family_equal_delta_ci"]["history_count"] == 3
    assert "insufficient_declared_families" in pair["noninferiority_diagnostic"]["insufficient_evidence"]
    assert set(pair["by_history"]) == {"h0", "h1", "h2"}


def test_bootstrap_is_family_equal_not_repeat_count_weighted_and_deterministic():
    rows = []
    for task, family, repeats, before, after in (
        ("win-many-repeats", "a", 10, "fail", "pass"),
        ("loss-once", "b", 1, "pass", "fail"),
    ):
        for repeat in range(repeats):
            rows += [row(task, c, before, family=family, repeat=repeat) for c in ("no_skill", "current")]
            rows.append(row(task, "mechanism", after, family=family, repeat=repeat))
    original = deepcopy(rows)
    result = report(rows)
    assert result == report(list(reversed(rows)), list(reversed(manifest(rows))))
    assert rows == original
    pair = result["comparisons"]["raw/mechanism_vs_no_skill"]
    assert pair["all_attempt_delta"] == 9 / 11
    assert pair["family_equal_delta_ci"]["estimate"] == 0
    assert pair["family_equal_delta_ci"]["per_family_delta"] == {"a": 1, "b": -1}


def test_multi_domain_worst_domain_is_not_hidden_by_overall_gain():
    rows = []
    for task, domain, baseline, candidate in (("coding", "coding", "fail", "pass"),
                                              ("other", "other", "pass", "fail")):
        rows += [row(task, c, baseline, domain=domain) for c in ("no_skill", "current")]
        rows.append(row(task, "mechanism", candidate, domain=domain))
    result = report(rows)
    assert result["arms"]["raw/mechanism"]["worst_domain_all_attempt_success"] == 0
    assert result["comparisons"]["raw/mechanism_vs_no_skill"]["worst_domain_all_attempt_delta"] == -1
    assert result["cross_domain_authorized"] is False


def test_references_report_cold_aliases_but_do_not_authenticate_provenance():
    rows = [row("one", c) for c in ("no_skill", "current", "mechanism")]
    for r in rows:
        r["request_hash"] = digest("cold" if r["condition"] in ("no_skill", "current") else "candidate")
        r["cost"] = {"hidden_payload_do_not_forward": "secret"}
    result = report(rows)
    assert result["reference_reuse"]["request_hash"] == {
        "referenced_positions": 3, "unique_references": 2, "aliased_positions": 1}
    assert "hidden_payload_do_not_forward" not in str(result)
    assert result["reference_reuse"]["receipt_hash"]["referenced_positions"] == 0


def test_ni_always_pending_even_when_configured_descriptive_screen_is_positive():
    rows = []
    for task, before in (("improved", "fail"), ("unchanged", "pass")):
        rows += [row(task, c, before) for c in ("no_skill", "current")]
        rows.append(row(task, "mechanism", "pass"))
    result = report(rows, min_families=2, min_histories=1, noninferiority_delta=.1)
    ni = result["comparisons"]["raw/mechanism_vs_no_skill"]["noninferiority_diagnostic"]
    assert ni["insufficient_evidence"] == []
    assert ni["descriptive_lower_exceeds_negative_margin"] is True
    assert ni["status"] == "pending" and ni["safety_guarantee"] is False


@pytest.mark.parametrize("mutation,message", [
    (lambda r: r.append(deepcopy(r[0])), "Duplicate observed"),
    (lambda r: r[0].update(task_id="unregistered"), "outside frozen"),
    (lambda r: r[0].update(family_id="changed"), "metadata differs"),
    (lambda r: r[0].update(status="not_applicable"), "status required"),
    (lambda r: r[0].update(skill_applied=1), "boolean"),
    (lambda r: r[0].update(skill_applied=True), "No-Skill"),
    (lambda r: r[0].update(repeat=True), "integer repeat"),
    (lambda r: r[0].update(request_hash="unverified"), "SHA256"),
])
def test_reject_invalid_observations(mutation, message):
    rows = [row("one", c) for c in ("no_skill", "current", "mechanism")]
    expected = manifest(rows)
    mutation(rows)
    with pytest.raises(ValueError, match=message):
        report(rows, expected)


def test_manifest_cannot_erase_an_arm_position_to_improve_denominator():
    rows = four_regions()
    expected = manifest(rows)
    expected.pop()
    with pytest.raises(ValueError, match="same frozen position roster"):
        report(rows, expected)
    with pytest.raises(ValueError, match="Duplicate expected"):
        report(rows, manifest(rows) + manifest(rows[:1]))
    expected = manifest(rows)
    expected[1]["region"] = "unrelated"
    with pytest.raises(ValueError, match="changed across positions"):
        report(rows, expected)


@pytest.mark.parametrize("kwargs", [
    {"bootstrap_seed": -1}, {"min_families": 0}, {"min_histories": True},
    {"noninferiority_delta": float("nan")}, {"noninferiority_delta": True},
    {"noninferiority_delta": -1},
])
def test_configuration_is_bounded(kwargs):
    with pytest.raises(ValueError):
        report([], **kwargs)


def test_empty_manifest_has_no_implicit_effect_or_authority():
    result = report([])
    assert result["arms"] == result["comparisons"] == {}
    assert result["expected_positions"] == 0
    assert result["formal_noninferiority_established"] is False


def test_actual_study_panel_roster_is_compatible_before_any_paid_execution():
    from skillopt.skill_validation.mechanism_study import expected_roster
    from skillopt.skill_validation.mechanism_tasks import build_panel

    panel = build_panel(20260925, development_families=1, confirmation_families=1)
    expected = expected_roster(panel, histories=1, repeats=1)
    result = report([], expected)
    assert set(row["region"] for row in expected) == set(REGIONS)
    assert result["expected_positions"] == result["missing_positions"] == len(expected)
    assert result["comparisons"]["raw/mechanism_vs_no_skill"]["unknown"] == len(panel["confirmation"])


def test_explicit_feedback_condition_names_preserve_records_and_pairing():
    rows = four_regions()
    mapping = {"local": "boolean", "mechanism": "case_details"}
    for record in rows:
        record["condition"] = mapping.get(record["condition"], record["condition"])
        # These are identities, not condition names, and must not be rewritten.
        record["family_id"] = "mechanism-" + record["family_id"]
    original = deepcopy(rows)
    result = report(rows, candidate_conditions=("boolean", "case_details"))
    assert rows == original and result["version"] == "mechanism-pilot-descriptive-metrics-v2"
    assert set(result["arms"]) == {f"{e}/{c}" for e in ("raw", "conditional")
                                  for c in ("no_skill", "current", "boolean", "case_details")}
    for exposure in ("raw", "conditional"):
        direct = result["comparisons"][f"{exposure}/case_details_vs_boolean"]
        assert direct["win"] == 2 and direct["loss"] == 0 and direct["unknown"] == 1
        assert direct["candidate_condition"] == "case_details"
        assert direct["baseline_condition"] == "boolean"
        assert all(key.startswith("mechanism-") for key in direct["family_equal_delta_ci"]["per_family_delta"])
        assert f"{exposure}/case_details_vs_no_skill" in result["comparisons"]
        assert f"{exposure}/boolean_vs_current" in result["comparisons"]
        assert f"{exposure}/boolean_vs_case_details" not in result["comparisons"]
        assert f"{exposure}/mechanism_vs_local" not in result["comparisons"]


def test_candidate_order_not_lexical_order_determines_direct_comparison():
    rows = [row("task", condition, "fail" if condition == "boolean" else "pass")
            for condition in ("no_skill", "current", "boolean", "case_details")]
    result = report(rows, candidate_conditions=["case_details", "boolean"])
    direct = result["comparisons"]["raw/boolean_vs_case_details"]
    assert direct["loss"] == 1 and direct["family_equal_delta_ci"]["estimate"] == -1
    assert "raw/case_details_vs_boolean" not in result["comparisons"]


@pytest.mark.parametrize("names", [None, "boolean,case_details", (), ("boolean",),
    ("a", "b", "c"), ("boolean", "boolean"), ("no_skill", "case_details"),
    ("boolean", "current"), (True, "other"), ("", "other"), ("a/b", "other"),
    ("a" * 65, "other"), ("a b", "other"), {"a", "b"}])
def test_invalid_candidate_names_rejected_before_metrics(names):
    with pytest.raises(ValueError, match="candidate|Candidate"):
        report([], candidate_conditions=names)


def test_alternate_namespace_is_explicit_local_and_does_not_mutate_defaults():
    from skillopt.skill_validation.mechanism_metrics import CONDITIONS, _grid
    rows = [row("task", c) for c in ("no_skill", "current", "boolean", "case_details")]
    with pytest.raises(ValueError, match="Unsupported condition"):
        report(rows)
    report(rows, candidate_conditions=("boolean", "case_details"))
    assert CONDITIONS == ("no_skill", "current", "local", "mechanism")
    with pytest.raises(ValueError, match="Unsupported condition"):
        report(four_regions(), candidate_conditions=("boolean", "case_details"))
    legacy = four_regions()
    assert report(legacy) == report(legacy, candidate_conditions=("local", "mechanism"))
    assert len(_grid(legacy, manifest(legacy))) == len(legacy)


def test_missing_feedback_arm_retains_unknown_in_same_frozen_denominator():
    all_rows = [row(task, condition) for task in ("first", "second")
                for condition in ("no_skill", "current", "boolean", "case_details")]
    rows = [r for r in all_rows if not (r["task_id"] == "second" and r["condition"] == "case_details")]
    result = report(rows, manifest(all_rows), candidate_conditions=("boolean", "case_details"))
    pair = result["comparisons"]["raw/case_details_vs_boolean"]
    assert pair["positions"] == 2 and pair["unknown"] == 1 and pair["loss"] == 0
    assert pair["missing_candidate_positions"] == 1
    assert pair["noninferiority_diagnostic"]["status"] == "pending"
    assert result["formal_noninferiority_established"] is False
