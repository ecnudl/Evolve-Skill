"""Isolated coevolution runtime amendment: supply the promised builtin divmod.

The frozen pilot is never modified or monkeypatched. Its audited runner is
extended ONLY at the builtin-name list; its sandbox profile, restricted imports,
resource limits, normalization and per-case execution remain unchanged.
Candidate source is never rewritten and never evaluated in this host process.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import time
from typing import Any, Mapping

from skillopt.validator_artifact_sensitivity import extract_artifact
from skillopt.validator_pilot import tasks as _pilot

VERSION = "coevolution-executor-v2-divmod-only"
BASE_RUNNER_SHA256 = "c4e77223ee75f8fa3e03dcea4c6e85fe1f8f1de148718620d7ef353d331d66be"
Task = _pilot.Task
validate_code = _pilot.validate_code
sandbox_probe = _pilot.sandbox_probe


def _extend_runner(base: str) -> tuple[str, tuple[str, ...]]:
    """Fail closed if the frozen trusted runner is not the reviewed source."""
    if hashlib.sha256(base.encode()).hexdigest() != BASE_RUNNER_SHA256:
        raise RuntimeError("frozen pilot runner changed; divmod amendment requires a new audit")
    tree = ast.parse(base)
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "names"
    ]
    if len(assignments) != 1:
        raise RuntimeError("trusted builtin-list anchor is not unique")
    assignment = assignments[0]
    names = ast.literal_eval(assignment.value)
    if (
        not isinstance(names, list)
        or not all(isinstance(name, str) for name in names)
        or len(names) != len(set(names))
        or "divmod" in names
        or assignment.end_lineno != assignment.lineno
    ):
        raise RuntimeError("trusted builtin-list shape changed")
    names = [*names, "divmod"]
    lines = base.splitlines(keepends=True)
    lines[assignment.lineno - 1] = "names=" + repr(names) + "\n"
    amended = "".join(lines)
    # Independently confirm no AST statement except the exact names value changed.
    new_tree = ast.parse(amended)
    replacement = next(
        node
        for node in new_tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "names"
    )
    replacement.value = assignment.value
    if ast.dump(tree, include_attributes=False) != ast.dump(new_tree, include_attributes=False):
        raise RuntimeError("runner amendment changed more than the builtin list")
    return amended, tuple(names)


# These are the actual ordinary candidate-callable builtin names. print is the
# inherited no-op. __import__ and __build_class__ remain compiler-internal helpers
# under the original AST/import restrictions, not extra public-call allowances.
CHILD_RUNNER, AVAILABLE_BUILTINS = _extend_runner(_pilot.CHILD_RUNNER)
INTERNAL_COMPILER_BUILTINS = ("__import__", "__build_class__")
RUNNER_SHA256 = hashlib.sha256(CHILD_RUNNER.encode()).hexdigest()


def run_payload(payload: Mapping[str, Any]) -> tuple[int, str, str]:
    """Same process isolation/watchdog as the pilot; only the runner differs.

    Fixture setup/expr must be trusted harness code, as in the original executor.
    Candidate AST is checked here too, so direct probe callers fail closed. Darwin
    RSS monitoring is sampled every 50 ms and is not a hard allocation barrier.
    """
    import psutil

    validate_code(payload["code"])
    proc = subprocess.Popen(
        _pilot._command(CHILD_RUNNER),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/private/tmp",
        env={"PATH": "/usr/bin:/bin"},
        text=True,
    )
    start = time.monotonic()
    first = json.dumps(payload)
    try:
        while True:
            try:
                out, err = proc.communicate(input=first, timeout=0.05)
                return proc.returncode, out, err
            except subprocess.TimeoutExpired:
                first = None
                if time.monotonic() - start > 12:
                    raise RuntimeError("candidate exceeded 12 second wall limit")
                try:
                    if psutil.Process(proc.pid).memory_info().rss > 384 * 1024 * 1024:
                        raise RuntimeError("candidate exceeded monitored RSS limit")
                except psutil.NoSuchProcess:
                    pass
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()


def evaluate(task: Task, response: str | Mapping[str, Any]) -> dict[str, Any]:
    """Pilot-compatible hard evaluation through the divmod-only child runtime."""
    cases = task.public_cases + task.private_cases
    result = {
        "correct": False,
        "hard": False,
        "execution_ok": False,
        "artifact_execution_ok": False,
        "public_observations": [],
        "private_diagnostics": [],
        "dimensions": {
            key: {"passed": 0, "total": sum(case["dimension"] == key for case in cases)}
            for key in ("requested_behavior", "preserved_behavior")
        },
    }
    try:
        code = _pilot.parse_response(response)
        tree = validate_code(code)
        payload = {"code": code, "cases": [{key: case[key] for key in ("setup", "expr")} for case in cases]}
        returncode, stdout, _stderr = run_payload(payload)
        if returncode != 0:
            result["safety_error"] = f"sandbox execution failed: exit {returncode}"
            result["error_category"] = "sandbox_or_resource_failure"
            return result
        rows = json.loads(stdout)["rows"]
        if len(rows) != len(cases):
            raise ValueError("runner result cardinality mismatch")
        result["execution_ok"] = True
        result["artifact_execution_ok"] = all(
            row["exception"] is None or case["exception"] is not None for case, row in zip(cases, rows)
        )
        for case, row in zip(cases, rows):
            passed = (
                row["exception"] == case["exception"]
                if case["exception"]
                else row["exception"] is None and _pilot._same(row["actual"], case["expected"])
            )
            result["dimensions"][case["dimension"]]["passed"] += int(passed)
            observation = {
                "label": case["label"],
                "expr": case["expr"],
                "setup": case["setup"],
                "passed": passed,
                "actual": row["actual"],
                "exception": row["exception"],
            }
            if case["public"]:
                result["public_observations"].append(observation)
            elif not passed:
                result["private_diagnostics"].append(
                    {**observation, "expected": case["expected"], "expected_exception": case["exception"]}
                )
        # Retain the old task adapter's one structural check for compatibility;
        # new coevolution task IDs do not activate this branch.
        if task.metadata["upstream_name"] == "refactor-extract-test-add-coverage":
            count = sum(isinstance(node, ast.FunctionDef) for node in tree.body)
            dimension = result["dimensions"]["requested_behavior"]
            dimension["total"] += 1
            dimension["passed"] += int(count >= 5)
            if count < 5:
                result["private_diagnostics"].append(
                    {"label": "limited helper count structure", "passed": False, "actual": count, "expected_minimum": 5}
                )
        result["correct"] = result["hard"] = all(
            dimension["passed"] == dimension["total"] for dimension in result["dimensions"].values()
        )
        result["passed_tests"] = sum(dimension["passed"] for dimension in result["dimensions"].values())
        result["total_tests"] = sum(dimension["total"] for dimension in result["dimensions"].values())
        result["public_pass"] = all(row["passed"] for row in result["public_observations"])
        return result
    except (ValueError, TypeError, SyntaxError) as exc:
        result["execution_ok"] = True
        result["error_category"] = "candidate_contract_violation"
        result["public_pass"] = False
        result["passed_tests"] = 0
        result["total_tests"] = sum(dimension["total"] for dimension in result["dimensions"].values())
        result["safety_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return result
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        result["error_category"] = "infrastructure_or_resource_failure"
        result["safety_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return result


def native_evaluation(task: Task, response: str, target_ok: bool) -> dict:
    """Same frozen native artifact extraction and guard semantics, new evaluator."""
    if not target_ok:
        return {
            "extraction": None,
            "evaluation": {
                "execution_ok": False,
                "hard": None,
                "error_category": "target_unavailable",
                "public_observations": [],
            },
            "format_ok": False,
            "code": None,
            "guard_reason": "target_unavailable",
        }
    artifact = extract_artifact(response)
    if not artifact["ok"]:
        return {
            "extraction": artifact,
            "evaluation": {
                "execution_ok": True,
                "hard": False,
                "error_category": "native_artifact_unextractable",
                "public_observations": [],
                "public_pass": False,
            },
            "format_ok": False,
            "code": None,
            "guard_reason": "unambiguous_native_artifact_required",
        }
    code = artifact["code"]
    result = evaluate(task, {"code": code})
    try:
        validate_code(code)
        invalid_code = False
    except (ValueError, TypeError, SyntaxError):
        invalid_code = True
    reason = "python_syntax_or_runtime_contract" if invalid_code else None
    if reason is None and result["execution_ok"] and result.get("public_pass") is False:
        reason = "visible_test_failure"
    return {
        "extraction": artifact,
        "evaluation": result,
        "code": code,
        "format_ok": artifact["ok"],
        "guard_reason": reason,
    }
