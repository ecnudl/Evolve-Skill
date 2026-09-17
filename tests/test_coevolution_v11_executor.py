"""Synthetic-only safety/transport regression for V11; never executes MBPP."""

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

from skillopt.coevolution_v10 import executor as frozen
from skillopt.coevolution_v11 import executor as e

sandbox = pytest.mark.skipif(sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
                             reason="macOS OS isolation required")


def cases(value=1):
    return [{"args": [e.encode_value(value)], "kwargs": {}}]


def observation(value):
    return {"value": e.encode_value(value), "exception": None, "truthiness": bool(value), "typed": True}


@pytest.mark.parametrize("source", [
    "import os", "import sys", "from math import *", "from string import Formatter",
    "class A: pass", "async def f(): pass", "@print\ndef f(): pass",
    "def f(): return eval('1')", "def f(): return globals()", "def f(): return open('file')",
    "def f(): return (1).__class__", "def f(): return (x for x in []).gi_frame",
    "def f(): return (x for x in []).gi_code", "import math\nmath.sqrt = lambda x: 0",
    "def f(__builtins__): pass", "import math as __builtins__", "def f(): return type(1)",
])
def test_frozen_ast_safety_rejections_preserved(source, monkeypatch):
    for validate in (frozen.validate_code, e.validate_code):
        with pytest.raises(ValueError):
            validate(source)
    monkeypatch.setattr(e, "_run_payload", lambda _: pytest.fail("unsafe AST reached child"))
    assert e.run_cases(source, "f", cases())["status"] == "candidate_rejected"


def test_ast_and_payload_implementations_exactly_match_frozen_policy():
    import inspect

    for name in ("validate_code", "_public_name", "_payload", "_run_payload"):
        assert ast.dump(ast.parse(inspect.getsource(getattr(e, name)))) == ast.dump(
            ast.parse(inspect.getsource(getattr(frozen, name))))
    assert e.IMPORT_MEMBERS == frozen.IMPORT_MEMBERS
    assert e.AVAILABLE_BUILTINS == frozen.AVAILABLE_BUILTINS
    assert e.RUNNER_SHA256 != frozen.RUNNER_SHA256


@sandbox
def test_synthetic_regex_match_preserves_truthiness_without_typed_coercion():
    source = "import re\ndef match(text): return re.search('z+', text)"
    result = e.run_cases(source, "match", cases("zz") + cases("abc"))
    assert result["status"] == "completed", result
    assert result["observations"] == [
        {"value": None, "exception": None, "truthiness": True, "typed": False}, observation(None)]
    assert result["code_hash"] == hashlib.sha256(source.encode()).hexdigest()


@sandbox
@pytest.mark.parametrize("expression,truthiness", [
    ("iter([])", True), ("frozenset()", False), ("frozenset({1})", True),
    ("range(0)", False), ("range(3)", True), ("lambda: 0", True),
])
def test_other_untyped_objects_keep_actual_truthiness(expression, truthiness):
    result = e.run_cases("def f(x): return " + expression, "f", cases())
    assert result["status"] == "completed", result
    assert result["observations"] == [
        {"value": None, "exception": None, "truthiness": truthiness, "typed": False}]


@sandbox
@pytest.mark.parametrize("value", [None, True, False, 0, 7, -0.0, float("nan"), "", "你好", [], (), {}, set(), (1,), {1}])
def test_typed_values_have_consistent_truthiness(value):
    result = e.run_cases("def f(x): return x", "f", cases(value))
    assert result["status"] == "completed", result
    assert result["observations"] == [observation(value)]


@sandbox
def test_candidate_cannot_overwrite_truthiness_or_encoder():
    source = """bool = lambda value: False
encode_value = lambda value: {'type':'int','value':'999'}
truthiness = False
typed = True
rows = [{'passed':True}]
def f(x): return [x]
"""
    result = e.run_cases(source, "f", cases())
    assert result["status"] == "completed"
    assert result["observations"] == [observation([1])]


@sandbox
def test_exceptions_and_fresh_globals_keep_old_semantics():
    result = e.run_cases("def f(x): return 1/0", "f", cases())
    assert result["status"] == "completed"
    assert result["observations"] == [{"value": None, "exception": "ZeroDivisionError", "truthiness": None, "typed": False}]
    result = e.run_cases("state=[]\ndef f(x):\n state.append(x)\n return len(state)", "f", cases()*2)
    assert result["observations"] == [observation(1), observation(1)]


@pytest.mark.parametrize("row", [
    {"value": None, "exception": None},
    {"value": None, "exception": None, "truthiness": True, "typed": 0},
    {"value": None, "exception": None, "truthiness": 1, "typed": False},
    {"value": None, "exception": None, "truthiness": True, "typed": True},
    {"value": e.encode_value(0), "exception": None, "truthiness": True, "typed": True},
    {"value": e.encode_value(0), "exception": None, "truthiness": False, "typed": False},
    {"value": None, "exception": "TypeError", "truthiness": False, "typed": False},
    {"value": None, "exception": "TypeError", "truthiness": None, "typed": True},
])
def test_malformed_or_inconsistent_observations_are_unknown(row, monkeypatch):
    monkeypatch.setattr(e, "_run_payload", lambda _: (0, json.dumps({"observations": [row]}), ""))
    result = e.run_cases("def f(x): return x", "f", cases())
    assert result["status"] == "infrastructure_unknown"
    assert result["observations"] == []


def test_memory_error_remains_resource_unknown_without_actual_oom(monkeypatch):
    row = {"value": None, "exception": "MemoryError", "truthiness": None, "typed": False}
    monkeypatch.setattr(e, "_run_payload", lambda _: (0, json.dumps({"observations": [row]}), ""))
    result = e.run_cases("def f(x): return x", "f", cases())
    assert result["status"] == "infrastructure_unknown"
    assert result["error_category"] == "resource_unknown" and result["observations"] == []


def test_child_payload_still_has_no_checks_or_expected(monkeypatch):
    seen = []
    def fake(payload):
        seen.append(payload)
        return 0, json.dumps({"observations": [observation(1)]}), ""
    monkeypatch.setattr(e, "_run_payload", fake)
    source = "# untouched\ndef f(x): return x\n"
    assert e.run_cases(source, "f", cases())["status"] == "completed"
    assert seen == [{"code": source, "entry_point": "f", "cases": cases()}]
    bad = [{**cases()[0], "expected": e.encode_value(1)}]
    assert e.run_cases(source, "f", bad)["status"] == "candidate_rejected"


@sandbox
def test_actual_os_probe_and_wall_watchdog(monkeypatch):
    assert e.sandbox_probe()["ok"] is True
    monkeypatch.setattr(e, "WALL_SECONDS", 0.1)
    result = e.run_cases("def f(x):\n while True: pass", "f", cases())
    assert result["status"] == "infrastructure_unknown"
    assert "wall" in result["error"]


def test_no_host_exec_eval_compile_calls():
    tree = ast.parse(Path(e.__file__).read_text())
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "compile"}]
