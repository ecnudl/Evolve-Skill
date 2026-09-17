"""Finite oracle/provenance/admissibility checks; never execute code on host."""

import json
import sys
from copy import deepcopy

import pytest

from skillopt.coevolution_v3.executor import evaluate, validate_files
from skillopt.coevolution_v4.tasks import NAMES, build_tasks, validate_input

TASKS = build_tasks()


def _patch(task, files):
    return {"files": {path: code for path, code in files.items() if path in task.editable_paths}}


def test_panel_is_nine_exposed_projects_not_twelve_independent_benchmarks():
    assert len(TASKS) == 12
    assert len({task.id for task in TASKS}) == 12
    assert len({task.cluster_id for task in TASKS}) == 9
    assert [task.split for task in TASKS].count("holdout") == 3
    assert [task.split for task in TASKS].count("gate") == 3
    assert all("older flattened pilot" in task.metadata["previous_exposure"] for task in TASKS)
    assert all(task.metadata["domain"] == "coding" for task in TASKS)
    assert all(task.metadata["source_files"] for task in TASKS)
    assert sum(len(task.public_cases) + len(task.private_cases) for task in TASKS) == 135


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.id)
def test_task_namespace_and_public_boundary(task):
    assert 2 <= len(task.files) <= 8
    assert "api.py" not in task.editable_paths
    assert task.files["api.py"] == task.reference_files["api.py"]
    assert all(validate_input(task, case["input"]) for case in task.public_cases + task.private_cases)
    public = task.public_task()
    assert "metadata" not in public
    assert "reference_files" not in public
    assert "private_cases" not in public
    assert public["public_cases"] == task.public_cases
    assert task.prompt.startswith("C1: ")
    validate_files(task, task.files)


def test_gate_and_final_have_disjoint_inputs_but_shared_project_identity():
    def encode(cases):
        return {json.dumps(case["input"], sort_keys=True) for case in cases}

    for gate in (task for task in TASKS if task.split == "gate"):
        final = next(task for task in TASKS if task.split == "holdout" and task.cluster_id == gate.cluster_id)
        assert encode(gate.public_cases + gate.private_cases).isdisjoint(encode(final.public_cases + final.private_cases))
        assert gate.files == final.files
        assert gate.prompt == final.prompt
        assert gate.input_domain == final.input_domain
        assert gate.id != final.id


@pytest.mark.skipif(sys.platform != "darwin", reason="mandatory OS sandbox only on macOS")
@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.id)
@pytest.mark.parametrize("kind", ["reference", "equivalent", "semantic_mutant", "preservation_mutant"])
def test_finite_oracle_controls_in_sandbox(task, kind):
    files = task.reference_files if kind == "reference" else task.metadata["controls"][kind]
    result = evaluate(task, _patch(task, files))
    assert result["execution_ok"] is True, result
    assert "safety_error" not in result, result
    assert result["hard"] is (kind in {"reference", "equivalent"}), result
    if kind == "preservation_mutant":
        assert any(row["dimension"] == "preserved_behavior" and not row["passed"] for row in result["case_results"])


@pytest.mark.skipif(sys.platform != "darwin", reason="mandatory OS sandbox only on macOS")
@pytest.mark.parametrize("task", [task for task in TASKS if task.split.startswith("learn")], ids=lambda task: task.id)
def test_learning_starter_has_behavior_failure_not_delivery_failure(task):
    result = evaluate(task, _patch(task, task.files))
    assert result["execution_ok"] is True
    assert result["hard"] is False
    assert "safety_error" not in result
    assert 0 < result["passed_tests"] < result["total_tests"]


@pytest.mark.parametrize("bad", [None, [], "{}", {"extra": 1}, {"operation": "unknown"}])
def test_invalid_schema_fails_closed(bad):
    assert not validate_input(TASKS[0], bad)
    assert not validate_input("unknown-id", bad)


def test_boundaries_and_bool_integer_distinction():
    money = next(task for task in TASKS if task.metadata["project"] == NAMES[1])
    value = deepcopy(money.public_cases[0]["input"])
    assert validate_input(money, value)
    value["quantity"] = True
    assert not validate_input(money, value)
    value["quantity"] = 3
    value["price"] = "NaN"
    assert not validate_input(money, value)
    value["price"] = "123456789012345.12345"
    assert not validate_input(money, value)
    value["price"] = "0.10"
    value["total"] = float("inf")
    assert not validate_input(money, value)
    pipeline = next(task for task in TASKS if task.metadata["project"] == NAMES[6])
    assert not validate_input(pipeline, {"operation": "new", "value": "x" * 2049})
    assert not validate_input(pipeline, {"operation": "new", "value": [0] * 65})
    assert not validate_input(pipeline, {"operation": "new", "value": 1000001})
    assert not validate_input(pipeline, {"operation": "new", "value": (1, 2)})
    nested = {}
    for _ in range(10):
        nested = {"x": nested}
    assert not validate_input(pipeline, {"operation": "new", "value": nested})


def test_cross_field_admissibility():
    etl = TASKS[0]
    value = deepcopy(etl.public_cases[0]["input"])
    value["history"] = {"01": "0.30"}
    assert not validate_input(etl, value)
    value["history"] = {"-0": "0.30"}
    assert not validate_input(etl, value)
    value["history"] = {}
    value["operation"] = "transform"
    value["rows"][0]["amount"] = None
    assert not validate_input(etl, value)
    integration = next(task for task in TASKS if task.metadata["project"] == NAMES[5])
    value = deepcopy(integration.public_cases[0]["input"])
    value["users"][1]["id"] = value["users"][0]["id"]
    assert not validate_input(integration, value)
    value = deepcopy(integration.public_cases[0]["input"])
    value["events"][0]["user"] = 99
    assert not validate_input(integration, value)


def test_build_returns_deeply_independent_bundles():
    first = build_tasks()
    first[0].reference_files["validator.py"] = "broken"
    first[0].public_cases[0]["input"]["rows"].clear()
    again = build_tasks()
    assert again[0].reference_files["validator.py"] != "broken"
    assert again[0].public_cases[0]["input"]["rows"]
