"""Isolated divmod runtime amendment; no APIs or live experiment artifacts."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution import executor as e
from skillopt.coevolution.tasks import build_tasks
from skillopt.validator_pilot import tasks as old

SANDBOX = sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()
NATIVE = 'def solve(data):\n    return list(divmod(data["a"], data["b"]))\n'


def simple_task():
    cases = []
    for index, (data, expected, exception) in enumerate(
        [
            ({"a": 7, "b": 3}, [2, 1], None),
            ({"a": -7, "b": 3}, [-3, 2], None),
            ({"a": 7, "b": -3}, [-3, -2], None),
            ({"a": 2, "b": 0}, None, "ZeroDivisionError"),
        ]
    ):
        cases.append(
            {
                "label": f"case-{index}",
                "setup": "data=" + repr(data),
                "expr": "solve(data)",
                "expected": expected,
                "exception": exception,
                "dimension": "requested_behavior",
                "public": True,
            }
        )
    cases.append(
        {
            "label": "input-preserved",
            "setup": "data={'a':7,'b':3}",
            "expr": "(solve(data),data)",
            "expected": [[2, 1], {"a": 7, "b": 3}],
            "exception": None,
            "dimension": "preserved_behavior",
            "public": False,
        }
    )
    return old.Task(
        "divmod-test",
        "dev",
        "divmod-test",
        "divmod-test",
        "Use standard divmod.",
        NATIVE,
        NATIVE,
        cases[:-1],
        cases[-1:],
        {"upstream_name": "divmod-test"},
    )


def test_audited_runner_adds_exactly_divmod_and_nothing_else():
    before, after = ast.parse(old.CHILD_RUNNER), ast.parse(e.CHILD_RUNNER)

    def names_node(tree):
        return next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "names"
        )

    old_names = ast.literal_eval(names_node(before).value)
    assert list(e.AVAILABLE_BUILTINS) == old_names + ["divmod"]
    assert ast.literal_eval(names_node(after).value) == list(e.AVAILABLE_BUILTINS)
    names_node(after).value = names_node(before).value
    assert ast.dump(before) == ast.dump(after)
    assert hashlib.sha256(old.CHILD_RUNNER.encode()).hexdigest() == e.BASE_RUNNER_SHA256
    assert "'divmod'" not in old.CHILD_RUNNER
    assert e.validate_code is old.validate_code
    assert e.sandbox_probe is old.sandbox_probe
    assert e.Task is old.Task


def test_runner_change_requires_explicit_reaudit():
    with pytest.raises(RuntimeError, match="requires a new audit"):
        e._extend_runner(old.CHILD_RUNNER + "\n# drift")


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
def test_real_standard_divmod_nonempty_negative_and_zero_division():
    result = e.evaluate(simple_task(), {"code": NATIVE})
    assert result["hard"] and result["public_pass"] and result["artifact_execution_ok"], result
    assert result["dimensions"]["preserved_behavior"] == {"passed": 1, "total": 1}


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
def test_old_executor_still_reports_nameerror_and_is_not_monkeypatched():
    run_identity, evaluate_identity, runner = old._run_payload, old.evaluate, old.CHILD_RUNNER
    result = old.evaluate(simple_task(), {"code": NATIVE})
    assert result["execution_ok"] and not result["hard"]
    assert {row["exception"] for row in result["public_observations"]} == {"NameError"}
    assert e.evaluate(simple_task(), {"code": NATIVE})["hard"]
    assert old._run_payload is run_identity and old.evaluate is evaluate_identity and old.CHILD_RUNNER == runner
    assert not old.evaluate(simple_task(), {"code": NATIVE})["hard"]


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
def test_existing_filesystem_network_environment_write_isolation_probe():
    probe = e.sandbox_probe()
    assert probe["ok"], probe
    assert all(
        probe[key] for key in ("workspace_denied", "home_denied", "network_denied", "write_denied", "environment_clean")
    )


@pytest.mark.parametrize("code", ["import os", 'open("/etc/passwd")', "x=(1).__class__", "eval('1')", "import socket"])
def test_ast_restrictions_still_fail_before_new_process(code, monkeypatch):
    monkeypatch.setattr(e.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("unsafe code launched"))
    result = e.evaluate(simple_task(), {"code": code})
    assert result["hard"] is False and result["execution_ok"] is True
    assert result["error_category"] == "candidate_contract_violation"
    with pytest.raises((ValueError, SyntaxError, TypeError)):
        e.run_payload({"code": code, "cases": []})


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
@pytest.mark.parametrize("bundle", build_tasks(), ids=lambda bundle: bundle["task"].id)
def test_all_frozen_references_keep_exact_old_evaluation_semantics(bundle):
    task = bundle["task"]
    response = {"code": task.reference_code}
    amended, original = e.evaluate(task, response), old.evaluate(task, response)
    assert amended == original
    assert amended["hard"]


def test_payload_has_no_expected_answers_and_candidate_is_not_rewritten(monkeypatch):
    seen = []

    def fake_run(payload):
        seen.append(deepcopy(payload))
        return 0, json.dumps({"rows": [{"actual": None, "exception": None} for _ in payload["cases"]]}), ""

    monkeypatch.setattr(e, "run_payload", fake_run)
    e.evaluate(simple_task(), {"code": NATIVE})
    assert seen[0]["code"] == NATIVE
    assert set(seen[0]) == {"code", "cases"}
    assert all(set(case) == {"setup", "expr"} for case in seen[0]["cases"])


def test_new_process_uses_old_profile_clean_environment_and_original_limits(monkeypatch):
    captured = {}

    class Process:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            if input is not None:
                captured["payload"] = json.loads(input)
                captured["timeout"] = timeout
            return '{"rows":[]}', ""

        def poll(self):
            return 0

    def popen(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return Process()

    monkeypatch.setattr(e.subprocess, "Popen", popen)
    monkeypatch.setattr(old, "_command", lambda runner: ["unchanged-profile", runner])
    assert e.run_payload({"code": NATIVE, "cases": []})[0] == 0
    assert captured["command"] == ["unchanged-profile", e.CHILD_RUNNER]
    assert captured["kwargs"]["env"] == {"PATH": "/usr/bin:/bin"}
    assert captured["kwargs"]["cwd"] == "/private/tmp"
    assert captured["timeout"] == 0.05
    assert "RLIMIT_CPU,(5,5)" in e.CHILD_RUNNER
    assert "RLIMIT_FSIZE,(0,0)" in e.CHILD_RUNNER
    assert "RLIMIT_NOFILE,(32,32)" in e.CHILD_RUNNER
    assert "len(encoded)>250000" in e.CHILD_RUNNER


def test_native_evaluation_uses_new_evaluator_and_unchanged_extracted_source(monkeypatch):
    seen = []

    def fake_evaluate(task, response):
        seen.append(response)
        return {"execution_ok": True, "hard": True, "public_pass": True}

    monkeypatch.setattr(e, "evaluate", fake_evaluate)
    result = e.native_evaluation(simple_task(), "```python\n" + NATIVE + "```", True)
    assert result["evaluation"]["hard"] and result["guard_reason"] is None
    assert seen == [{"code": result["code"]}]
    assert "divmod" in result["code"]


@pytest.mark.skipif(not SANDBOX, reason="requires macOS sandbox-exec")
def test_native_evaluation_direct_divmod_path_and_unavailable_handling():
    assert e.native_evaluation(simple_task(), NATIVE, True)["evaluation"]["hard"]
    unavailable = e.native_evaluation(simple_task(), NATIVE, False)
    assert unavailable["evaluation"]["hard"] is None
    assert unavailable["guard_reason"] == "target_unavailable"


def test_infrastructure_failure_is_not_reclassified_as_candidate_failure(monkeypatch):
    monkeypatch.setattr(e, "run_payload", lambda _: (_ for _ in ()).throw(RuntimeError("sandbox unavailable")))
    result = e.evaluate(simple_task(), {"code": NATIVE})
    assert result["execution_ok"] is False
    assert result["error_category"] == "infrastructure_or_resource_failure"
