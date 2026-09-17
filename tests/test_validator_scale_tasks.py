"""Pre-response QA: authored contracts, independent answers and controlled stress."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from skillopt import validator_scale_tasks as t
from skillopt.validator_pilot import tasks as oracle

ALL = t.build_tasks("dev") + t.build_tasks("holdout")
SANDBOX = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()


def test_32_distinct_contracts_with_explicit_family_dependence():
    assert len(ALL) == 32
    assert len({task.id for task in ALL}) == 32
    assert len({task.prompt for task in ALL}) == 32
    assert len({task.reference_code for task in ALL}) == 32
    assert set(Counter(task.family for task in ALL).values()) == {4}
    assert len({task.family for task in ALL}) == 8
    assert len({task.cluster_id for task in ALL}) == 8
    assert len(t.build_tasks("dev")) == len(t.build_tasks("holdout")) == 16
    assert {task.family for task in t.build_tasks("dev")}.isdisjoint(task.family for task in t.build_tasks("holdout"))
    assert t.catalog()["public_benchmark"] is False
    assert t.catalog()["independence_unit"] == "family"


def test_task_and_solver_system_agree_on_native_python_output():
    from skillopt.validator_scale_experiment import ARMS, solver_messages

    assert t.VERSION.endswith("v2-output-consistent")
    for task in ALL:
        assert "Return exactly JSON" not in task.prompt
        assert '{"code":' not in task.prompt
        assert "raw Python or one python fenced code block" in task.prompt
        assert "Do NOT wrap Python source in a JSON string" in task.prompt
        for arm in ARMS:
            system, user = solver_messages(task, arm)
            assert "raw Python or one python fenced code block" in system
            assert "Do NOT wrap Python source in a JSON string" in system
            assert json.loads(user)["task"]["prompt"] == task.prompt


@pytest.mark.parametrize("split", ["train", "all", "test", "validation", "unknown"])
def test_no_accidental_split_aliases(split):
    with pytest.raises(ValueError):
        t.build_tasks(split)


@pytest.mark.parametrize("task", ALL, ids=lambda task: task.id)
def test_metadata_determinism_and_no_private_material_in_visible_prompt(task):
    assert task == oracle.Task.from_dict(json.loads(json.dumps(task.to_dict())))
    assert task in t.build_tasks(task.split, seed=92834)
    assert task.metadata["author_created"] is True
    assert task.metadata["within_family_dependence"] is True
    assert "not a public benchmark" in task.metadata["origin"]
    assert "upstream_commit" not in task.metadata
    assert task.metadata["reference_sha256"] == hashlib.sha256(task.reference_code.encode()).hexdigest()
    assert task.starter_code not in task.prompt
    assert task.reference_code not in task.prompt
    assert "reference_code" not in task.prompt
    assert "private_cases" not in task.prompt
    assert "source" not in task.metadata  # no fabricated public provenance
    assert len(task.public_cases) in (2, 3)
    assert len(task.private_cases) >= 5
    assert {case["dimension"] for case in task.private_cases} == {"requested_behavior", "preserved_behavior"}
    visible = json.dumps({"prompt": task.prompt, "starter_code": task.starter_code, "public_cases": task.public_cases})
    for case in task.private_cases:
        assert case["label"] not in visible
    assert all(case["public"] for case in task.public_cases)
    assert not any(case["public"] for case in task.private_cases)
    fixtures = t.controlled_fixtures(task)
    assert {fixture["kind"] for fixture in fixtures} == {"reference", "starter", "preservation_mutant"}
    assert len({fixture["response"] for fixture in fixtures}) == 3
    for fixture in fixtures:
        assert fixture["controlled"] and fixture["origin"] == "controlled"
        code = oracle.parse_response(fixture["response"])
        oracle.validate_code(code)
        assert len(code.splitlines()) >= 23
        tree = ast.parse(code)
        assert any(isinstance(node, ast.FunctionDef) and node.name == "solve" for node in tree.body)


@pytest.mark.skipif(not SANDBOX, reason="generated modules fail closed without macOS sandbox-exec")
@pytest.mark.parametrize("task", ALL, ids=lambda task: task.id)
@pytest.mark.parametrize("kind", ["reference", "starter", "preservation_mutant"])
def test_all_96_reference_bug_and_isolated_preservation_oracles(task, kind):
    fixture = next(item for item in t.controlled_fixtures(task) if item["kind"] == kind)
    result = oracle.evaluate(task, fixture["response"])
    assert result["execution_ok"], result
    assert "error_category" not in result, result
    if kind == "reference":
        assert result["hard"] and result["artifact_execution_ok"], result
        assert not result["private_diagnostics"]
    else:
        assert result["hard"] is False, result
        if kind == "starter":
            requested = result["dimensions"]["requested_behavior"]
            assert requested["passed"] < requested["total"], result
        else:
            assert result["public_pass"], result
            requested = result["dimensions"]["requested_behavior"]
            preserved = result["dimensions"]["preserved_behavior"]
            assert requested["passed"] == requested["total"], result
            assert preserved["passed"] < preserved["total"], result
            assert result["private_diagnostics"]


def test_oracle_payload_cannot_receive_expected_answers_or_family_labels(monkeypatch):
    task = ALL[0]
    captured = []

    def fake_run(payload):
        captured.append(payload)
        return 0, json.dumps({"rows": [{"actual": None, "exception": None} for case in payload["cases"]]}), ""

    monkeypatch.setattr(oracle, "_run_payload", fake_run)
    oracle.evaluate(task, {"code": task.reference_code})
    assert len(captured) == 1
    assert set(captured[0]) == {"code", "cases"}
    assert all(set(case) == {"setup", "expr"} for case in captured[0]["cases"])
    serialized = json.dumps(captured[0])
    for forbidden in ("expected", "dimension", "cluster_id", task.family, task.id):
        assert forbidden not in serialized


def test_missing_mutation_anchor_fails_closed():
    with pytest.raises(ValueError, match="anchor missing"):
        t._replace_once("x = 1", ("nonexistent", "x = 2"))
