"""Offline safety and exact typed semantics for the V10 compatibility runner."""

import ast
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

from skillopt.coevolution_v10 import executor as e


def cases(*args, **kwargs):
    return [{"args": [e.encode_value(value) for value in args], "kwargs": {
        key: e.encode_value(value) for key, value in kwargs.items()
    }}]


requires_sandbox = pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="OS-isolated execution requires macOS sandbox-exec",
)


@pytest.mark.parametrize("source", [
    "import os\ndef f(): return 1", "import sys\ndef f(): return 1",
    "from math import __dict__", "from math import *", "from . import math",
    "from string import Formatter", "from typing import get_type_hints",
    "def f(): return globals()", "def f(): return eval('1')",
    "def f(): return open('/etc/passwd')", "def f(): return vars()",
    "def f(): return getattr(1, '__class__')", "def f(): return (1).__class__",
    "def f(): return (x for x in []).gi_frame", "def f(): return (x for x in []).gi_code",
    "def f(): return Exception.mro()", "def f(): return type(1)",
    "def f(): return {}.format_map({})", "def f(): return object()",
    "import math\nmath.sqrt = lambda value: 0", "import math\ndel math.sqrt",
    "class A: pass", "@print\ndef f(): pass", "async def f(): pass",
    "def __attack(): pass", "def f(__builtins__): pass", "import math as __builtins__",
    "import math as globals", "from collections import namedtuple",
])
def test_forbidden_code_never_starts_child(source, monkeypatch):
    monkeypatch.setattr(e, "_run_payload", lambda _: pytest.fail("unsafe code reached child"))
    with pytest.raises(ValueError):
        e.validate_code(source)
    result = e.run_cases(source, "f", cases())
    assert result["status"] == "candidate_rejected"
    assert result["observations"] == []


@pytest.mark.parametrize("source", [None, "", " ", "x" * 60001, "def broken(: pass"])
def test_invalid_source(source):
    assert e.run_cases(source, "f", cases())["status"] == "candidate_rejected"


def test_ast_node_bound():
    with pytest.raises(ValueError, match="AST"):
        e.validate_code("x=0\n" * 4000)


@pytest.mark.parametrize("source", [
    "import math\ndef f(a): return math.factorial(a)",
    "from collections import Counter\ndef f(a): return list(Counter(a).items())",
    "from itertools import permutations\ndef f(a): return list(permutations(a))",
    "from typing import List\ndef f(a: List[int]) -> int: return len(a)",
    "def f(a): return [i for i in a if i > 1]",
    "def f(a):\n def helper(x): return x*2\n return helper(a)",
])
def test_supported_ast(source):
    assert isinstance(e.validate_code(source), ast.Module)


@pytest.mark.parametrize("entry", ["_f", "__import__", "a.b", "a()", "class", "", None])
def test_entry_point_must_be_public(entry, monkeypatch):
    monkeypatch.setattr(e, "_run_payload", lambda _: pytest.fail("invalid call reached child"))
    assert e.run_cases("def f(): return 1", entry, cases())["status"] == "candidate_rejected"


@pytest.mark.parametrize("bad_cases", [
    [], {}, [{"args": [], "kwargs": {}, "expected": 1}], [{"args": []}],
    [{"args": "[]", "kwargs": {}}], [{"args": [], "kwargs": []}],
    [{"args": [], "kwargs": {"__builtins__": {"type": "int", "value": "1"}}}],
    [{"args": [{"type": "execute", "value": "arbitrary"}], "kwargs": {}}],
    [{"args": [{"type": "int", "value": "01"}], "kwargs": {}}],
    [{"args": [], "kwargs": {}}] * 129,
])
def test_call_schema_is_closed(bad_cases, monkeypatch):
    monkeypatch.setattr(e, "_run_payload", lambda _: pytest.fail("malformed payload reached child"))
    assert e.run_cases("def f(): return 1", "f", bad_cases)["status"] == "candidate_rejected"


def test_candidate_source_bytes_and_private_payload(monkeypatch):
    source = "# Preserve comments and whitespace.\ndef f(x):\n    return x + 1\n\n"
    seen = []
    def fake(payload):
        seen.append(payload)
        return 0, json.dumps({"observations": [{"value": e.encode_value(3), "exception": None}],
                             "unsupported_output": False}), ""
    monkeypatch.setattr(e, "_run_payload", fake)
    result = e.run_cases(source, "f", cases(2))
    assert result["status"] == "completed"
    assert result["code_hash"] == hashlib.sha256(source.encode()).hexdigest()
    assert seen[0] == {"code": source, "entry_point": "f", "cases": cases(2)}
    assert "expected" not in json.dumps(seen)


@pytest.mark.parametrize("output", [
    "not-json", "[]", "{}",
    json.dumps({"observations": [], "unsupported_output": False}),
    json.dumps({"observations": [{"value": None, "exception": None}], "unsupported_output": False}),
    json.dumps({"observations": [{"value": {"type": "int", "value": "01"}, "exception": None}],
                "unsupported_output": False}),
    json.dumps({"observations": [{"value": {"type": "none", "value": None}, "exception": "TypeError"}],
                "unsupported_output": False}),
    json.dumps({"observations": [{"value": None, "exception": "__fake"}], "unsupported_output": False}),
    json.dumps({"observations": [{"value": None, "exception": "TypeError", "passed": True}],
                "unsupported_output": False}),
    "x" * 250001,
])
def test_malformed_child_observation_is_unknown(output, monkeypatch):
    monkeypatch.setattr(e, "_run_payload", lambda _: (0, output, ""))
    result = e.run_cases("def f(): return 1", "f", cases())
    assert result["status"] == "infrastructure_unknown"
    assert result["observations"] == []


@pytest.mark.parametrize("error", [RuntimeError("wall"), OSError("sandbox unavailable")])
def test_failed_sandbox_never_falls_back_to_host(error, monkeypatch):
    def fail(_):
        raise error
    monkeypatch.setattr(e, "_run_payload", fail)
    assert e.run_cases("def f(): return 1", "f", cases())["status"] == "infrastructure_unknown"


@pytest.mark.parametrize("exit_code", [-9, -24, 1, 2])
def test_nonzero_child_exit_remains_unknown(exit_code, monkeypatch):
    monkeypatch.setattr(e, "_run_payload", lambda _: (exit_code, "", ""))
    assert e.run_cases("def f(): return 1", "f", cases())["status"] == "infrastructure_unknown"


@pytest.mark.parametrize("rows", [
    [{"value": None, "exception": "MemoryError"}],
    [{"value": e.encode_value(1), "exception": None}, {"value": None, "exception": "MemoryError"}],
    [{"value": None, "exception": "MemoryError"}, {"value": None, "exception": "ValueError"}],
])
def test_child_memory_error_is_resource_unknown_without_real_oom(rows, monkeypatch):
    receipt = json.dumps({"observations": rows, "unsupported_output": False})
    monkeypatch.setattr(e, "_run_payload", lambda _: (0, receipt, ""))
    result = e.run_cases("def f(): return 1", "f", cases() * len(rows))
    assert result["status"] == "infrastructure_unknown"
    assert result["error_category"] == "resource_unknown"
    assert "MemoryError" in result["error"]
    assert result["observations"] == []


@requires_sandbox
def test_actual_os_probe_denies_private_reads_writes_network_and_credentials(monkeypatch):
    monkeypatch.setenv("V10_TEST_API_KEY", "synthetic-not-a-real-key")
    probe = e.sandbox_probe()
    assert probe["ok"] is True
    assert all(probe[key] for key in (
        "interpreter", "environment_clean", "workspace_denied", "home_denied", "network_denied", "write_denied"
    ))


@requires_sandbox
@pytest.mark.parametrize("value", [
    None, True, False, 1, -999, 1.00000000000001, -0.0, float("inf"), float("nan"),
    "你好", [], (), set(), [1, (2, 3)], {(1, 2): [True, None]}, {1, "x", (2, 3)},
])
def test_actual_typed_roundtrip(value):
    result = e.run_cases("def identity(value): return value", "identity", cases(value))
    assert result["status"] == "completed", result
    actual = e.decode_value(result["observations"][0]["value"])
    assert type(actual) is type(value)
    if isinstance(value, float) and math.isnan(value):
        assert math.isnan(actual)
    elif value == 0.0 and type(value) is float:
        assert math.copysign(1.0, value) == math.copysign(1.0, actual)
    else:
        assert actual == value


@requires_sandbox
def test_candidate_namespace_cannot_override_harness_or_encoder():
    source = """encode_value = lambda value: {'type': 'int', 'value': '999'}
decode_value = lambda value: 999
json = None
payload = {'expected': 999}
rows = [{'passed': True}]
def solve(x, *, offset=0):
    print('forged result')
    return x + offset
"""
    result = e.run_cases(source, "solve", cases(2, offset=3))
    assert result["status"] == "completed", result
    assert e.decode_value(result["observations"][0]["value"]) == 5


@requires_sandbox
def test_each_case_has_fresh_candidate_state_and_no_expected_payload():
    source = "counter = []\ndef solve():\n counter.append(1)\n return len(counter)\n"
    result = e.run_cases(source, "solve", cases() * 3)
    assert result["status"] == "completed"
    assert [e.decode_value(row["value"]) for row in result["observations"]] == [1, 1, 1]
    result = e.run_cases("def solve(): return expected", "solve", cases())
    assert result["observations"] == [{"value": None, "exception": "NameError"}]


@requires_sandbox
@pytest.mark.parametrize("source,expected", [
    ("import math\ndef solve(): return math.factorial(5)", 120),
    ("from collections import Counter\ndef solve(): return list(Counter('aaab').items())", [("a", 3), ("b", 1)]),
    ("from itertools import permutations\ndef solve(): return list(permutations([1,2]))", [(1, 2), (2, 1)]),
    ("from typing import List\ndef solve(x: List[int]=[1,2]) -> int: return sum(x)", 3),
    ("import heapq\ndef solve(): return heapq.nlargest(2,[4,1,7])", [7, 4]),
    ("from bisect import bisect_left\ndef solve(): return bisect_left([1,3,5],4)", 2),
    ("from functools import reduce\ndef solve(): return reduce(lambda a,b:a+b,[1,2,3])", 6),
    ("import re\ndef solve(): return re.findall('[a-z]+','12abc3def')", ["abc", "def"]),
    ("import string\ndef solve(): return string.digits", "0123456789"),
])
def test_restricted_library_proxies(source, expected):
    result = e.run_cases(source, "solve", cases())
    assert result["status"] == "completed", result
    assert e.decode_value(result["observations"][0]["value"]) == expected


@requires_sandbox
@pytest.mark.parametrize("source,exception", [
    ("def f(): return 1/0", "ZeroDivisionError"),
    ("def f(): raise ValueError('not a grade')", "ValueError"),
    ("def f(): return missing", "NameError"),
    ("def other(): return 1", "KeyError"),
    ("f = 1", "TypeError"),
])
def test_python_exceptions_are_completed_semantic_observations(source, exception):
    result = e.run_cases(source, "f", cases())
    assert result["status"] == "completed"
    assert result["observations"] == [{"value": None, "exception": exception}]


@requires_sandbox
@pytest.mark.parametrize("expression", ["iter([1])", "frozenset({1})", "lambda: 1", "range(3)"])
def test_unsupported_return_types_are_explicit(expression):
    result = e.run_cases("def f(): return " + expression, "f", cases())
    assert result["status"] == "unsupported_output"
    assert result["observations"] == [{"value": None, "exception": None}]


@requires_sandbox
def test_actual_wall_watchdog_is_unknown(monkeypatch):
    monkeypatch.setattr(e, "WALL_SECONDS", 0.1)
    result = e.run_cases("def f():\n while True: pass", "f", cases())
    assert result["status"] == "infrastructure_unknown"
    assert "wall" in result["error"]


@requires_sandbox
def test_actual_sampled_rss_watchdog_is_unknown(monkeypatch):
    monkeypatch.setattr(e, "RSS_BYTES", 1)
    result = e.run_cases("def f():\n while True: pass", "f", cases())
    assert result["status"] == "infrastructure_unknown"
    assert "RSS" in result["error"]


def test_host_executor_has_no_exec_eval_compile_calls():
    tree = ast.parse(Path(e.__file__).read_text())
    forbidden = [node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id in {"exec", "eval", "compile"}]
    assert forbidden == []
    assert e.RUNNER_SHA256 == hashlib.sha256(e.CHILD_RUNNER.encode()).hexdigest()
