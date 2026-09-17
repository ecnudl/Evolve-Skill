import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v6.native import (
    NativeAdapter,
    calculate_workbook,
    final_native_tasks,
    forward_chain,
)
from skillopt.validator_pilot.api import digest


def selected(domain="spreadsheet", group="same_mechanism", variant=0):
    return next(adapter for adapter in final_native_tasks() if adapter.domain == domain
                and adapter.task["metadata"]["group"] == group and adapter.task["metadata"]["parameter_variant"] == variant)


def test_panel_counts_clusters_and_category_contracts():
    tasks = final_native_tasks()
    assert len(tasks) == len({a.task["id"] for a in tasks}) == 18
    assert len({a.task["cluster_id"] for a in tasks}) == 4
    for domain in ("spreadsheet", "rule_reasoning"):
        chosen = [a for a in tasks if a.domain == domain]
        assert len(chosen) == 9
        for group, scope in (("same_mechanism", "partial_update"), ("near_miss", "full_replacement"), ("unrelated", "read_only")):
            family = [a for a in chosen if a.task["metadata"]["group"] == group]
            assert len(family) == 3
            assert len({a.task["cluster_id"] for a in family}) == 1
            assert {a.task["contract"]["change_scope"] for a in family} == {scope}
    assert all(a.task["split"] == "final" and a.task["metadata"]["synthetic_engineering"] for a in tasks)


def test_contract_strata_sharing_native_substrate_are_one_inference_cluster():
    for domain in ("spreadsheet", "rule_reasoning"):
        same, near, unrelated = (selected(domain, group) for group in ("same_mechanism", "near_miss", "unrelated"))
        assert same.task["cluster_id"] == near.task["cluster_id"]
        assert same.task["cluster_id"] != unrelated.task["cluster_id"]
        assert same.task["metadata"]["family"] != near.task["metadata"]["family"]
        assert same.task["metadata"]["shared_substrate"] == near.task["metadata"]["shared_substrate"]
        assert same.task["metadata"]["contract_strata_are_not_independent_projects"] is True


def test_every_reference_passes_independent_native_cases():
    for adapter in final_native_tasks():
        artifact = adapter.task["reference_artifact"]
        result = adapter.evaluate(artifact)
        assert result["status"] == "pass", (adapter.task["id"], result)
        assert result["score"] == 1
        assert result["passed_cases"] == result["total_cases"] >= 1
        payload = {k: v for k, v in result.items() if k != "record_hash"}
        assert digest(payload) == result["record_hash"]


def test_every_edit_starter_fails_desired_changed_semantics():
    for adapter in final_native_tasks():
        if adapter.task["contract"]["change_scope"] == "read_only":
            continue
        artifact = ({"formulas": {cell: adapter.task["formulas"][cell] for cell in adapter.task["editable_cells"]}}
                    if adapter.domain == "spreadsheet" else {"rules": adapter.task["rules"]})
        result = adapter.evaluate(artifact)
        assert result["status"] == "fail", adapter.task["id"]
        assert result["score"] == 0


def test_public_task_hides_groups_gold_and_hidden_recomputations():
    for adapter in final_native_tasks():
        public = adapter.public_task()
        assert not {"metadata", "group", "reference_artifact", "hidden_cases", "cluster_id", "split"} & set(public)
        assert public["contract"] == adapter.task["contract"]
        if adapter.task["contract"]["change_scope"] != "read_only":
            assert len(public["public_cases"]) == 1
            assert len(adapter.task["hidden_cases"]) >= 5
        public["contract"]["change_scope"] = "MODIFIED"
        assert adapter.task["contract"]["change_scope"] != "MODIFIED"


def test_spreadsheet_recomputes_and_rejects_hardcoded_public_answer():
    adapter = selected()
    expected = adapter.task["public_cases"][0]["expected"]["B8"]
    patch = {"formulas": {"B8": "=" + str(expected)}}
    assert adapter.evaluate(patch, public_only=True)["score"] == 1
    result = adapter.evaluate(patch)
    assert result["score"] == 0
    assert result["passed_cases"] < result["total_cases"]


def test_spreadsheet_old_tax_preserved_for_partial_but_obsolete_on_replacement():
    partial = selected()
    wrong = {"formulas": {"B8": "=MAX(0,B6-B10)*(1+B4)+B5"}}
    assert partial.evaluate(wrong)["score"] == 0
    full = selected(group="near_miss")
    wrong = deepcopy(full.task["reference_artifact"])
    wrong["formulas"]["B7"] = "=B2*B3*B4"
    assert full.evaluate(wrong)["score"] == 0


def test_formula_arithmetic_shared_dependency_lazy_if_and_round():
    result = calculate_workbook({"A1": 4, "A2": 2}, {"B1": "=A1*A2", "B2": "=B1+1", "B3": "=B1-1",
                                                    "C1": "=IF(A2>0,B2+B3,1/0)", "C2": "=ROUND(2.5,0)"})
    assert result["C1"] == 16
    assert result["C2"] == 2


@pytest.mark.parametrize("formula", ["=__import__('os')", "=A1.real", "=A1[0]", "=(lambda:1)()", "=2**999999",
                                      "='hello'", "=True", "=SUM(A1:A2)", "=[1,2]", "=IF(1,2,3)",
                                      "=ROUND(A1,999)", "=A1/0", "=MAX()"])
def test_forbidden_or_invalid_formulas_fail_closed(formula):
    with pytest.raises((ValueError, SyntaxError, ZeroDivisionError)):
        calculate_workbook({"A1": 2}, {"B1": formula})


def test_formula_cycles_unknown_cells_and_nonfinite_inputs_rejected():
    with pytest.raises(ValueError, match="Circular"):
        calculate_workbook({}, {"A1": "=B1", "B1": "=A1"})
    with pytest.raises(ValueError, match="Unknown cell"):
        calculate_workbook({}, {"A1": "=B1"})
    with pytest.raises(ValueError):
        calculate_workbook({"A1": float("nan")}, {"B1": "=A1"})


def test_positive_rule_engine_handles_order_shared_paths_and_cycles():
    rules = [{"id": "r4", "if": ["b", "c"], "then": "d"},
             {"id": "r2", "if": ["a"], "then": "b"}, {"id": "r3", "if": ["a"], "then": "c"},
             {"id": "r1", "if": ["d"], "then": "a"}]
    assert forward_chain(["a"], rules, ["a", "b", "c", "d"]) == ["a", "b", "c", "d"]
    assert forward_chain([], rules, ["a", "b", "c", "d"]) == []


@pytest.mark.parametrize("rule", [{"id": "r", "if": [], "then": "b"}, {"id": "r", "if": ["not a"], "then": "b"},
                                  {"id": "r", "if": ["a", "a"], "then": "b"},
                                  {"id": "r", "if": ["a"], "then": "missing"},
                                  {"id": "r", "if": ["a"], "then": "b", "priority": 3}])
def test_rule_language_rejects_unapproved_semantics(rule):
    with pytest.raises(ValueError):
        forward_chain(["a"], [rule], ["a", "b"])


def test_rule_patch_preserves_other_rule_bytes_and_complete_identity():
    adapter = selected("rule_reasoning")
    wrong = deepcopy(adapter.task["reference_artifact"])
    wrong["rules"][2]["if"].append("eligible")
    assert adapter.evaluate(wrong)["error"] == "delivery"
    missing = deepcopy(adapter.task["reference_artifact"])
    missing["rules"].pop()
    assert adapter.evaluate(missing)["status"] == "unknown"


def test_rule_hidden_factsets_check_both_preservation_and_qualification():
    adapter = selected("rule_reasoning")
    wrong = deepcopy(adapter.task["reference_artifact"])
    wrong["rules"][0]["if"] = ["express"]
    assert adapter.evaluate(wrong, public_only=True)["score"] == 1
    assert adapter.evaluate(wrong)["score"] == 0


@pytest.mark.parametrize("domain", ["spreadsheet", "rule_reasoning"])
def test_readonly_no_gold_feedback_and_no_edits(domain):
    adapter = selected(domain, "unrelated")
    public = adapter.evaluate(adapter.task["reference_artifact"], public_only=True)
    assert public["score"] is None
    assert public["case_results"] == []
    assert adapter.evaluate(adapter.task["reference_artifact"])["score"] == 1
    invalid = {**adapter.task["reference_artifact"], "formulas": {}}
    assert adapter.evaluate(invalid)["error"] == "delivery"


@pytest.mark.parametrize("raw", ['{"formulas":', '```json\n{"formulas":{"B8":"=1"}}\n```',
                                  '{"formulas":{"B8":"=1","B8":"=2"}}', '{"answer":NaN}'])
def test_artifacts_are_strict_json_without_repair(raw):
    with pytest.raises((ValueError, SyntaxError)):
        selected().parse_artifact(raw)


class FakeAPI:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def call(self, system, user, **kwargs):
        row = {"system": system, "user": user, **kwargs}
        self.calls.append(row)
        response = self.responses.pop(0)
        return {"ok": response is not None, "response": json.dumps(response) if isinstance(response, dict) else response,
                "request_hash": digest(row)}


def test_solver_two_equal_budget_calls_and_hidden_boundary():
    adapter = selected()
    api = FakeAPI([adapter.task["reference_artifact"], "KEEP"])
    result = adapter.solve(api, "Check preserved dependencies", key="x", repeat=2)
    assert len(api.calls) == result["solver_calls"] == 2
    assert {row["max_tokens"] for row in api.calls} == {8500}
    assert {row["repeat"] for row in api.calls} == {2}
    assert result["artifact"] == adapter.task["reference_artifact"]
    assert result["revision_kept"] is True
    assert result["format_ok"] is True
    assert adapter.evaluate(result["artifact"])["score"] == 1
    for call in api.calls:
        assert "hidden_cases" not in call["user"]
        assert "reference_artifact" not in call["user"]
        assert "same_mechanism" not in call["user"]
        assert "recompute-1" not in call["user"]


def test_solver_revision_merges_partial_formula_patch():
    adapter = selected(group="near_miss")
    target = adapter.task["reference_artifact"]["formulas"]
    first = {"formulas": {"B6": target["B6"]}}
    second = {"formulas": {cell: formula for cell, formula in target.items() if cell != "B6"}}
    api = FakeAPI([first, second])
    result = adapter.solve(api, "", key="x")
    assert result["artifact"] == adapter.task["reference_artifact"]


def test_invalid_initial_keep_not_invented_as_artifact():
    adapter = selected()
    api = FakeAPI(['{"formulas":', "KEEP"])
    result = adapter.solve(api, "", key="x")
    assert result["artifact"] is None
    assert result["delivery_status"] == "delivery"
    assert len(api.calls) == 2


def test_terminal_transport_error_not_rerolled():
    adapter = selected()
    api = FakeAPI([None, None])
    result = adapter.solve(api, "", key="x")
    assert result["target_ok"] is False
    assert result["artifact"] is None
    assert len(api.calls) == 2


def test_mutating_public_return_cannot_modify_internal_task():
    adapter = selected()
    original = deepcopy(adapter.task)
    public = adapter.public_task()
    public["inputs"]["B2"] = 999
    assert adapter.task == original
    clone = NativeAdapter(original)
    original["inputs"]["B2"] = 999
    assert clone.task["inputs"]["B2"] != 999
