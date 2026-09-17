"""Offline oracle/task checks only; no model inference or efficacy measurement."""

import itertools
import json
from collections import Counter
from copy import deepcopy

import pytest

from skillopt.coevolution_v6.native import calculate_workbook, forward_chain
from skillopt.coevolution_v8 import native_tasks as n
from skillopt.validator_pilot.api import digest


@pytest.fixture(scope="module")
def panel():
    return n.development_native_tasks()


def test_eight_instances_four_true_families_not_eight_independent_projects(panel):
    assert len(panel) == len({a.task["id"] for a in panel}) == 8
    assert Counter(a.domain for a in panel) == {"spreadsheet": 4, "rule_reasoning": 4}
    assert sorted(Counter(a.task["cluster_id"] for a in panel).values()) == [2, 2, 2, 2]
    for adapter in panel:
        task = adapter.task
        assert task["split"] == "development"
        assert task["metadata"]["structural_family"] == task["family"]
        assert task["metadata"]["variant"] in {0, 1}
        assert task["metadata"]["historical_task_or_model_artifacts_used"] is False
        assert task["metadata"]["initial_task_is_public_repair_fixture_not_model_generated_failure"]
        assert len(task["public_cases"]) == 2 and len(task["hidden_cases"]) >= 8
        cases = task["public_cases"] + task["hidden_cases"]
        assert len({c["id"] for c in cases}) == len(cases)


def test_no_hidden_or_reference_values_are_exposed_as_model_fields(panel):
    for adapter in panel:
        public, task = adapter.public_task(), adapter.task
        assert not {"hidden_cases", "reference_artifact", "metadata", "cluster_id", "family"}.intersection(public)
        serialized = json.dumps(public)
        assert all(case["id"] not in serialized for case in task["hidden_cases"])
        assert public["public_cases"] == task["public_cases"]
        assert "runtime" in public


def test_deterministic_independent_builds_no_mutable_alias(panel):
    one, two = n.development_native_tasks(), n.development_native_tasks()
    assert [a.task for a in one] == [a.task for a in two] == [a.task for a in panel]
    one[0].task["inputs"]["A1"] = 999
    assert one[0].task != two[0].task and two[0].task == panel[0].task


@pytest.mark.parametrize("index", range(8))
def test_reference_satisfies_native_oracle_and_public_fixture_needs_repair(panel, index):
    adapter = panel[index]
    task = adapter.task
    result = adapter.evaluate(task["reference_artifact"])
    assert result["score"] == 1.0 and result["total_cases"] == 11
    assert adapter.evaluate(task["reference_artifact"], public_only=True)["total_cases"] == 2
    initial = ({"formulas": {cell: task["formulas"][cell] for cell in task["editable_cells"]}}
               if adapter.domain == "spreadsheet" else {"rules": task["rules"]})
    initial_result = adapter.evaluate(initial)
    assert initial_result["score"] == 0.0
    assert adapter.evaluate(initial, public_only=True)["score"] == 0.0
    assert initial_result["status"] == "fail" and initial_result["error"] is None


@pytest.mark.parametrize("variant,units,energy,total,reconcile", [
    (0, [10, 3, 0], 32, 37, 116), (1, [8, 3, 0], 42, 53, 170)])
def test_hand_calculated_marginal_energy_spots(variant, units, energy, total, reconcile):
    task = n._energy(variant).task
    assert n.spreadsheet_oracle(task["family"], task["inputs"]) == {
        "B1": units[0], "B2": units[1], "B3": units[2], "B4": energy,
        "B5": 0, "B6": total, "C1": reconcile}
    empty = {**task["inputs"], "A1": 0, "A8": 1, "A9": 1000}
    assert n.spreadsheet_oracle(task["family"], empty)["B6"] == task["inputs"]["A7"]
    assert n.spreadsheet_oracle(task["family"], empty)["C1"] == 4 * task["inputs"]["A7"]


def test_hand_calculated_energy_waiver_never_erases_base():
    inputs = {"A1": 9, "A2": 3, "A3": 7, "A4": 0, "A5": 2, "A6": 5, "A7": 13, "A8": 1, "A9": 100}
    assert n.spreadsheet_oracle(n.SHEET_FAMILIES[0], inputs) == {
        "B1": 3, "B2": 4, "B3": 2, "B4": 18, "B5": 18, "B6": 13, "C1": 52}


@pytest.mark.parametrize("variant,reserve,usable,middle,last,unmet", [(0, 4, 16, 6, 2, 3), (1, 7, 13, 5, 0, 6)])
def test_hand_calculated_priority_waterfall(variant, reserve, usable, middle, last, unmet):
    task = n._waterfall(variant).task
    assert n.spreadsheet_oracle(task["family"], task["inputs"]) == {
        "B1": reserve, "B2": usable, "B3": 8, "B4": middle, "B5": last, "B6": 0, "B7": unmet, "C1": 20}
    shortage = {**task["inputs"], "A1": 3, "A6": 1}
    assert n.spreadsheet_oracle(task["family"], shortage) == {
        "B1": 3, "B2": 0, "B3": 0, "B4": 0, "B5": 0, "B6": 0, "B7": 19, "C1": 3}


@pytest.mark.parametrize("variant", [0, 1])
def test_sheet_reference_vs_independent_oracle_over_boundaries(variant):
    for adapter in (n._energy(variant), n._waterfall(variant)):
        task = adapter.task
        for quantity, flag, modifier in itertools.product(range(0, 51, 2), (0, 1), (0, 3, 100)):
            changing = "A9" if task["family"] == n.SHEET_FAMILIES[0] else "A7"
            flag_cell = "A8" if task["family"] == n.SHEET_FAMILIES[0] else "A6"
            inputs = {**task["inputs"], "A1": quantity, flag_cell: flag, changing: modifier}
            before = deepcopy(inputs)
            expected = n.spreadsheet_oracle(task["family"], inputs)
            values = calculate_workbook(inputs, {**task["formulas"], **task["reference_artifact"]["formulas"]})
            assert {key: values[key] for key in expected} == expected
            assert inputs == before
            if task["family"] == n.SHEET_FAMILIES[1]:
                assert expected["C1"] == inputs["A1"]
                assert all(value >= 0 for value in expected.values())


@pytest.mark.parametrize("variant", [0, 1])
@pytest.mark.parametrize("family", n.RULE_FAMILIES)
def test_rule_reference_vs_independent_boolean_oracle_for_every_primitive_subset(family, variant):
    task = n._rule_task(family, variant).task
    primitives, _, names = n._vocabulary(family, variant)
    for mask in range(1 << len(primitives)):
        facts = [names[p] for i, p in enumerate(primitives) if mask & (1 << i)]
        before = deepcopy(facts)
        closure = forward_chain(facts, task["reference_artifact"]["rules"], task["vocabulary"])
        actual = sorted(set(closure) & set(task["answer_facts"]))
        assert actual == n.rule_oracle(family, variant, facts)
        assert facts == before


@pytest.mark.parametrize("facts,expected", [
    (["urgent_waiver", "destination_ok"], []),
    (["identity_ok", "intact", "chain_logged", "review_signed", "destination_ok"], ["audit_required", "checked", "reviewed"]),
    (["identity_ok", "intact", "review_signed", "storage_ok"], ["archive_allowed", "checked", "reviewed"]),
    (["identity_ok", "intact", "chain_logged", "screen_clear", "urgent_waiver", "destination_ok"],
     ["audit_required", "chain_ready", "checked", "dispatch_allowed", "release_ready"]),
])
def test_literal_specimen_path_and_independent_branch_answers(facts, expected):
    assert n.rule_oracle(n.RULE_FAMILIES[0], 0, facts) == expected


@pytest.mark.parametrize("facts,expected", [
    (["vote_b", "sealed", "export_scope"], []),
    (["vote_a", "vote_b", "sealed", "export_scope", "audit_signed"], ["quorum"]),
    (["vote_b", "vote_c", "identity_ok", "policy_ok", "local_scope"], ["cleared", "local_allowed", "quorum"]),
    (["identity_ok", "audit_signed"], ["trace_ready"]),
])
def test_literal_quorum_and_independent_branch_answers(facts, expected):
    assert n.rule_oracle(n.RULE_FAMILIES[1], 0, facts) == expected


@pytest.mark.parametrize("index", range(8))
def test_protected_structure_rejected_as_delivery_not_semantic_score(panel, index):
    adapter, artifact = panel[index], deepcopy(panel[index].task["reference_artifact"])
    if adapter.domain == "spreadsheet":
        artifact["formulas"]["C1"] = "=0"
    else:
        artifact["rules"][0]["then"] = adapter.task["vocabulary"][0]
    result = adapter.evaluate(artifact)
    assert result["score"] is None and result["error"] == "delivery"


def test_all_fixtures_are_distinct_after_merging_overrides(panel):
    for adapter in panel:
        task = adapter.task
        cases = task["public_cases"] + task["hidden_cases"]
        if adapter.domain == "spreadsheet":
            hashes = [digest({**task["inputs"], **c["overrides"]}) for c in cases]
        else:
            hashes = [digest(sorted(c["facts"])) for c in cases]
        assert len(set(hashes)) == len(cases)


def test_unknown_host_oracle_family_fails_closed():
    with pytest.raises(ValueError):
        n.spreadsheet_oracle("not-a-family", {})
    with pytest.raises(ValueError):
        n.rule_oracle("not-a-family", 0, [])
