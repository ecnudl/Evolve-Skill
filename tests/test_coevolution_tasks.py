"""Pre-response finite-oracle and public/private boundary qualification."""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from skillopt.coevolution import tasks as t
from skillopt.validator_pilot import tasks as oracle

BANK = t.build_tasks()
SANDBOX = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists()
ANCHOR = {"items": [0, 1, 2], "limit": 2, "enabled": True, "priority": True}
# Independently hand-calculated contract examples; not generated from source or oracle.
ANCHORS = {
    "commerce": [
        ([0, 1, 1], [0, 0, 0], [1, 3, 5]),
        ([2, 3, 4], [2, 4, 6], [0, 1, 3]),
        ([0, 1, 1], [0, 0, 2], [1, 1, 0]),
        ([1, 1, 2], [1, 1, 1], [1, 1, 2]),
        ([2, 1, 0], [2, 1, 0], [2, 1, 0]),
        ([0, 1, 1], [0, 1, 0], [0, 1, 1]),
        ([0, 1, 1], [0, 1, 1], [1, 1, 0]),
        ([0, 1, 3], [0, 1, 3], [0, 1, 3]),
    ],
    "tabular_reporting": [
        ([0, 1, 3], [0, 1, 3], [0, 1, 3]),
        ([1, 1, 1], [0, 1, 1], [1, 1, 1]),
        ([1, 2, 3], [3, 2, 1], [1, 2, 3]),
        ([1, 1, 1], [1, 1, 1], [1, 2, 3]),
        ([0, 1, 2], [1, 2, 2], [1, 1, 1]),
        ([1, 1, 2], [0, 1, 2], [1, 1, 1]),
        ([0, 1, 1], [0, 1, 2], [0, 1, 2]),
        ([2, 1, 2], [1, 1, 2], [2, 1, 2]),
    ],
    "policy_routing": [
        ([0, 1, 2], [0, 1, 3], [0, 1, 2]),
        ([2, 1, 2], [2, 1, 3], [8, 7, 8]),
        ([0, 2, 3], [2, 2, 3], [0, 2, 1]),
        ([1, 1, 0], [2, 1, 0], [1, 1, 1]),
        ([0, 0, 0], [0, 0, 0], [0, 0, 0]),
        ([0, 1, 2], [0, 1, 2], [0, 1, 2]),
        ([0, 1, 1], [0, 1, 2], [0, 1, 2]),
        ([0, 1, 3], [0, 1, 3], [0, 1, 2]),
    ],
}


def test_frozen_counts_and_paired_cluster_split_integrity():
    assert len(BANK) == 48
    assert Counter(row["phase"] for row in BANK) == {"learn0": 6, "gate0": 6, "learn1": 6, "gate1": 6, "holdout": 24}
    assert Counter(row["context"] for row in BANK) == {name: 16 for name in t.CONTEXTS}
    assert len({row["task"].id for row in BANK}) == 48
    assert len({row["task"].cluster_id for row in BANK}) == 24
    for cluster in {row["task"].cluster_id for row in BANK}:
        paired = [row for row in BANK if row["task"].cluster_id == cluster]
        assert len(paired) == 2
        assert {row["mode"] for row in paired} == set(t.MODES)
        assert len({row["phase"] for row in paired}) == 1
        assert paired[0]["task"].starter_code == paired[1]["task"].starter_code
    assert len({spec.legacy for spec in t.SPECS}) >= 20
    first = t.build_tasks()
    first[0]["task"].metadata["context"] = "caller corruption"
    assert t.build_tasks()[0]["context"] == "commerce"
    assert t.build_tasks()[0]["task"].metadata["context"] == "commerce"


@pytest.mark.parametrize("spec", t.SPECS, ids=lambda spec: f"{spec.context}-{spec.index}")
def test_independent_hand_calculated_contract_examples(spec):
    expected = ANCHORS[spec.context][spec.index]
    for mode, values in zip(("old", *t.MODES), expected):
        assert t.oracle_values(spec, ANCHOR, mode) == values


@pytest.mark.parametrize("row", BANK, ids=lambda row: row["task"].id)
def test_finite_domain_is_exact_and_every_input_gets_both_dimensions(row):
    task = row["task"]
    assert len(t.legal_inputs()) == 40
    assert len(task.public_cases) == 4
    assert len(task.private_cases) == 76
    combined = task.public_cases + task.private_cases
    assert Counter(case["dimension"] for case in combined) == {"requested_behavior": 40, "preserved_behavior": 40}
    for data in t.legal_inputs():
        assert t.input_valid(task.id, data) is True
        assert t.input_valid(task.id, json.dumps(data)) is True
        setup = "data=" + repr(data)
        assert sum(case["setup"] == setup for case in combined) == 2
    spec, mode = t._spec_mode(task)
    assert any(
        t.expected(spec, data, mode)["current"] != t.expected(spec, data, mode)["history"] for data in t.legal_inputs()
    ), "new contract cannot equal old policy on the whole declared domain"
    assert task == oracle.Task.from_dict(json.loads(json.dumps(task.to_dict())))
    assert task.metadata["all_coding"] and task.metadata["not_public_benchmark"]
    visible = t.public_task(row)
    assert set(visible) == {"id", "prompt", "starter_code", "public_cases", "input_domain"}
    assert "Return exactly JSON" not in visible["prompt"]
    assert "do NOT wrap source in JSON" in visible["prompt"]
    for case in task.private_cases:
        assert case["label"] not in json.dumps(visible)
    for fixture in t.controlled_fixtures(task):
        oracle.validate_code(fixture["code"])
        assert fixture["controlled"]
        assert "oracle QA only" in fixture["interpretation"]


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {**ANCHOR, "items": [999]},
        {**ANCHOR, "items": (0, 1, 2)},
        {**ANCHOR, "items": [False, 1, 2]},
        {**ANCHOR, "limit": 2.0},
        {**ANCHOR, "enabled": 1},
        {**ANCHOR, "priority": None},
        {**ANCHOR, "extra": 1},
        '{"items":[],"limit":2,"limit":4,"enabled":true,"priority":false}',
        "[]",
        "NaN",
    ],
)
def test_out_of_domain_rejected_without_oracle_execution(bad):
    assert t.input_valid(BANK[0]["task"].id, bad) is False
    assert t.input_valid("unknown", ANCHOR) is False


@pytest.mark.skipif(not SANDBOX, reason="native candidate execution requires the existing safe sandbox")
@pytest.mark.parametrize("row", BANK, ids=lambda row: row["task"].id)
@pytest.mark.parametrize("kind", ["reference", "starter", "semantic_mutant", "preservation_mutant", "alternative"])
def test_all_240_native_artifacts_against_exhaustive_independent_oracles(row, kind):
    task = row["task"]
    fixture = next(item for item in t.controlled_fixtures(task) if item["kind"] == kind)
    result = oracle.evaluate(task, fixture["response"])
    assert result["execution_ok"], result
    assert not result.get("error_category"), result
    assert result["hard"] is fixture["expected_hard"], result
    requested = result["dimensions"]["requested_behavior"]
    preserved = result["dimensions"]["preserved_behavior"]
    if kind in {"reference", "alternative"}:
        assert result["passed_tests"] == 80
    elif kind == "semantic_mutant":
        assert result["public_pass"]
        assert requested["passed"] < requested["total"]
        assert preserved["passed"] == preserved["total"]
    elif kind == "preservation_mutant":
        assert result["public_pass"]
        assert requested["passed"] == requested["total"]
        assert preserved["passed"] < preserved["total"]
    else:
        assert requested["passed"] < requested["total"]
        assert preserved["passed"] == preserved["total"], "old starter must be correct OLD policy"


def test_expected_answers_and_hidden_labels_never_enter_executor_payload(monkeypatch):
    task = BANK[0]["task"]
    seen = []

    def fake_run(payload):
        seen.append(payload)
        return 0, json.dumps({"rows": [{"actual": None, "exception": None} for _ in payload["cases"]]}), ""

    monkeypatch.setattr(oracle, "_run_payload", fake_run)
    oracle.evaluate(task, {"code": task.reference_code})
    assert set(seen[0]) == {"code", "cases"}
    assert all(set(case) == {"setup", "expr"} for case in seen[0]["cases"])
    assert '"expected"' not in json.dumps(seen)
    assert '"dimension"' not in json.dumps(seen)


def test_no_candidate_execution_inside_trusted_oracle_source():
    tree = ast.parse(Path(t.__file__).read_text())
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile"}
        for node in ast.walk(tree)
    )


@pytest.mark.skipif(not SANDBOX, reason="requires existing safe sandbox")
def test_input_numeric_type_mutation_is_not_hidden_by_numeric_output_equivalence():
    task = BANK[0]["task"]
    code = task.reference_code.replace(
        '    return {"history": history, "current": current}',
        '    data["limit"] = float(data["limit"])\n    return {"history": history, "current": current}',
    )
    result = oracle.evaluate(task, {"code": code})
    assert result["execution_ok"]
    assert result["hard"] is False
    assert result["dimensions"]["requested_behavior"]["passed"] == 40
    assert result["dimensions"]["preserved_behavior"]["passed"] == 0
