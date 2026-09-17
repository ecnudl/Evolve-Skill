"""Independent fixtures, sandbox fail-closed behavior and task provenance."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

from skillopt.validator_pilot import tasks as t

ALL_TASKS = [task for split in t.SPLIT_TASKS for task in t.build_tasks(split)]
SANDBOX = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()


def test_distinct_authentic_task_ids_and_disjoint_original_families():
    assert len(ALL_TASKS) == 9
    assert len({task.id for task in ALL_TASKS}) == 9
    assert len({task.family for task in ALL_TASKS}) == 3
    assert len({task.cluster_id for task in ALL_TASKS}) == 3
    for split in t.SPLIT_TASKS:
        tasks = t.build_tasks(split)
        assert len(tasks) == 3
        assert len({task.cluster_id for task in tasks}) == 1
        assert tasks == t.build_tasks(split)
        assert {task.id for task in t.build_tasks(split, seed=1)} == {task.id for task in tasks}
        for task in tasks:
            assert task == t.Task.from_dict(json.loads(json.dumps(task.to_dict())))
            assert task.metadata["upstream_commit"] == t.UPSTREAM_COMMIT
            assert "not canonical" in task.metadata["adaptation"]
            assert task.metadata["source_files"]


@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda x: x.id)
def test_all_snapshots_are_hash_attested_and_private_answers_not_in_prompt(task):
    for source in task.metadata["source_files"]:
        path = t.ASSETS / source["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
        assert t.UPSTREAM_COMMIT in source["url"]
    assert task.starter_code in task.prompt
    assert task.reference_code not in task.prompt
    assert '"private_cases"' not in task.prompt
    assert '"reference_code"' not in task.prompt
    assert "Hidden checks:" not in task.prompt  # Upstream author fixture plans withheld.
    for case in task.public_cases:
        assert case["label"] in task.prompt
    for case in task.private_cases:
        assert '"label": ' + json.dumps(case["label"]) not in task.prompt


@pytest.mark.parametrize("split", ["validation", "test", "unknown"])
def test_split_aliases_cannot_silently_expose_holdout(split):
    with pytest.raises(ValueError):
        t.build_tasks(split)


@pytest.mark.parametrize("n", [0, 4, 24, -1])
def test_no_padded_pseudo_independent_samples(n):
    with pytest.raises(ValueError):
        t.build_tasks("train", n_per_family=n)


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
def test_sandbox_interpreter_runs_and_secrets_network_writes_are_denied():
    result = t.sandbox_probe()
    assert result["ok"], result
    assert result["workspace_denied"] and result["home_denied"]
    assert result["network_denied"] and result["write_denied"]


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda x: x.id)
def test_references_pass_starters_fail_and_mutants_expose_visible_check_blindspots(task):
    fixtures = t.controlled_fixtures(task)
    assert len(fixtures) == 3
    for fixture in fixtures:
        assert fixture["controlled"] is True
        result = t.evaluate(task, fixture["response"])
        assert result["execution_ok"], result
        if fixture["kind"] == "reference":
            assert result["hard"] is True, result
            assert result["artifact_execution_ok"]
            assert not result["private_diagnostics"]
            assert result["passed_tests"] == result["total_tests"]
        elif fixture["kind"] == "starter":
            assert not result["hard"]
        else:
            assert not result["hard"]
            assert result["public_pass"]
            assert result["private_diagnostics"]
            if fixture["kind"] == "preservation_mutant":
                requested = result["dimensions"]["requested_behavior"]
                preserved = result["dimensions"]["preserved_behavior"]
                assert requested["passed"] == requested["total"]
                assert preserved["passed"] < preserved["total"]


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from pathlib import Path",
        "from json import *",
        "x=globals()",
        "x=eval('1')",
        "x=open('anything')",
        "x=(1).__class__",
        "x=getattr(1,'x')",
        "x=__builtins__",
        "class Bad(list): pass",
        "class Bad(metaclass=list): pass",
        "@str\ndef f(): return 1",
        "def __getattribute__(self,x): return 1",
        "import subprocess",
        "db.enable_load_extension(True)",
        "db.set_authorizer(None)",
        "async def f(): pass",
        "from . import x",
    ],
)
def test_static_contract_rejects_unsafe_or_unsupported_operations(code):
    with pytest.raises(ValueError):
        t.validate_code(code)


@pytest.mark.parametrize("code", ["def bad(:", "import os", "class A(list):pass"])
def test_candidate_contract_failures_are_observed_failures_not_missing_data(code):
    result = t.evaluate(ALL_TASKS[0], {"code": code})
    assert result["execution_ok"]
    assert not result["hard"]
    assert not result["artifact_execution_ok"]
    assert result["error_category"] == "candidate_contract_violation"


@pytest.mark.parametrize(
    "response", ["not JSON", '{"answer":"x"}', '{"code": 1}', '{"code":"x","extra":1}', "```python\nx=1\n```"]
)
def test_wrong_response_schema_is_observed_failure(response):
    result = t.evaluate(ALL_TASKS[0], response)
    assert result["execution_ok"] and not result["hard"]
    assert result["error_category"] == "candidate_contract_violation"


def test_plain_and_json_fenced_responses_have_identical_meaning():
    response = json.dumps({"code": "x=1"})
    assert t.parse_response(response) == t.parse_response("```json\n" + response + "\n```")
    assert t.parse_response("```\n" + response + "\n```") == "x=1"


def test_reference_ast_contract_including_classes_and_safe_imports():
    for task in ALL_TASKS:
        assert isinstance(t.validate_code(task.reference_code), ast.Module)


def test_unsupported_host_fails_closed(monkeypatch):
    monkeypatch.setattr(t.sys, "platform", "linux")
    result = t.evaluate(ALL_TASKS[0], {"code": ALL_TASKS[0].reference_code})
    assert not result["execution_ok"]
    assert not result["hard"]
    assert "refusing unsandboxed" in result["safety_error"]


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
def test_sqlite_filesystem_attach_rejected_inside_sandbox():
    task = t.build_tasks("dev")[2]
    case = t._case(
        "attach blocked",
        "db.execute(\"ATTACH DATABASE '/private/tmp/forbidden.sqlite' AS x\")",
        exception="DatabaseError",
        setup='db=sqlite3.connect(":memory:")',
        public=True,
    )
    altered = t.Task(**{**task.to_dict(), "public_cases": [case], "private_cases": []})
    result = t.evaluate(altered, {"code": task.reference_code})
    assert result["hard"], result


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
def test_each_case_gets_a_fresh_candidate_namespace():
    task = ALL_TASKS[0]
    cases = [
        t._case("first", "len(items)", 1, setup="items.append(1)", public=True),
        t._case("second", "len(items)", 0, public=True),
    ]
    altered = t.Task(**{**task.to_dict(), "public_cases": cases, "private_cases": []})
    result = t.evaluate(altered, {"code": "items=[]"})
    assert result["hard"], result


def test_numeric_comparison_does_not_collapse_boolean_or_integer_contracts():
    assert not t._same(True, 1)
    assert not t._same(1, True)
    assert not t._same(1.00000000001, 1)
    assert t._same(1.0, 1)
    assert t._same(0.30000000000000004, 0.3)
    assert not t._same("0.30", "0.3")
    assert not t._same({"a": 1, "extra": 2}, {"a": 1})


def test_manual_statistics_fixture_cross_checks():
    expected = t._statistics_expected([-1, 0, 1])
    assert expected["mean"] == 0
    assert expected["median"] == 0
    assert expected["report"] == "crosses_zero"
    assert expected["value_buckets"] == {"negative": 1, "zero": 1, "positive": 1}
    assert t._statistics_expected([7, 7, 7])["stddev"] == 0
    assert t._statistics_expected([1, 1, 1, 1, 100])["outliers"] == [100.0]
