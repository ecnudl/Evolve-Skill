import json
from dataclasses import replace

import pytest

from skillopt.coevolution_v3 import executor as ex


def task_for(files=None):
    files = files or {
        "api.py": "import calculation\ndef solve(data):\n    return calculation.divide(data['a'], data['b'])\n",
        "calculation.py": "def divide(a, b):\n    return list(divmod(a, b))\n",
    }
    case = {
        "label": "division",
        "input": {"a": -7, "b": 3},
        "expected": [-3, 2],
        "exception": None,
        "dimension": "requested_behavior",
        "public": True,
    }
    return ex.RepoTask("unit", "dev", "unit", "unit", "test", files, files, list(files), {}, [case], [], {})


def test_dataclass_roundtrip():
    task = task_for()
    assert ex.RepoTask.from_dict(task.to_dict()) == task


def test_real_module_import_divmod_and_partial_patch():
    task = task_for()
    result = ex.evaluate(task, {"files": {}})
    assert result["hard"] is True
    assert result["case_results"] == [
        {
            "id": "division:behavior",
            "label": "division",
            "dimension": "requested_behavior",
            "passed": True,
            "public": True,
        },
        {
            "id": "division:input_unchanged",
            "label": "division",
            "dimension": "preserved_behavior",
            "passed": True,
            "public": True,
        },
    ]
    assert result["files"] == task.files


def test_modules_have_separate_namespaces_shared_cache_and_fresh_case_state():
    files = {
        "api.py": "import first\nimport second\ndef solve(data):\n    return [first.use(), second.use()]\n",
        "first.py": "import state\nNAME='first'\ndef use():\n    return [NAME, state.bump()]\n",
        "second.py": "from state import bump\nNAME='second'\ndef use():\n    return [NAME, bump()]\n",
        "state.py": "counter=0\ndef bump():\n    global counter\n    counter+=1\n    return counter\n",
    }
    task = task_for(files)
    rows = ex.execute_inputs(task, files, [{}, {}])
    assert [r["value"] for r in rows] == [[["first", 1], ["second", 2]]] * 2
    assert all(row["input_unchanged"] for row in rows)


@pytest.mark.parametrize(
    "source",
    [
        "def solve(data):\n    data['a'] = float(data['a'])\n    return [-3, 2]\n",
        "def solve(data):\n    value=data.pop('a')\n    data['a']=value\n    return [-3, 2]\n",
    ],
)
def test_type_and_key_order_nonmutation_checked_inside_child(source):
    task = task_for()
    result = ex.evaluate(task, {"files": {"api.py": source}})
    assert result["hard"] is False
    assert result["dimensions"]["requested_behavior"]["passed"] == 1
    row = result["public_observations"][0]
    assert row["input_unchanged"] is False
    assert row["input_before_fingerprint"] != row["input_after_fingerprint"]


def test_exception_is_observable_not_infrastructure_and_nonmutation_survives():
    task = task_for()
    rows = ex.execute_inputs(task, task.files, [{"a": 7, "b": 0}])
    assert rows[0]["ok"] is True
    assert rows[0]["exception"] == "ZeroDivisionError"
    assert rows[0]["input_unchanged"] is True


def test_restricted_library_proxy_rebinding_cannot_leak_between_cases():
    task = task_for()
    files = {
        **task.files,
        "api.py": "import math\ndef solve(data):\n    previous=math.sqrt(4)\n    math.sqrt=lambda x: 9\n    return previous\n",
    }
    assert [row["value"] for row in ex.execute_inputs(task, files, [{}, {}])] == [2, 2]


def test_nonfinite_return_and_cyclic_input_mutation_are_observable():
    task = task_for()
    files = {**task.files, "api.py": "def solve(data):\n    data['loop']=data\n    return float('nan')\n"}
    row = ex.execute_inputs(task, files, [{}])[0]
    assert row["ok"] is True and row["exception"] == "ValueError"
    assert row["value"] is None and row["input_unchanged"] is False


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef solve(data): return os.environ\n",
        "def solve(data): return open('/etc/passwd').read()\n",
        "def solve(data): return data.__class__\n",
        "from .calculation import divide\ndef solve(data): return []\n",
        "from calculation import *\ndef solve(data): return []\n",
        "def solve(data): return eval('1+1')\n",
    ],
)
def test_unsafe_code_rejected_before_process(monkeypatch, source):
    monkeypatch.setattr(ex, "run_payload", lambda _: pytest.fail("unsafe candidate reached sandbox"))
    result = ex.evaluate(task_for(), {"files": {"api.py": source}})
    assert result["execution_ok"] is True and result["hard"] is False
    assert result["error_category"] == "candidate_contract_violation"


@pytest.mark.parametrize(
    "raw",
    [
        '{"files":{"api.py":"x", "api.py":"y"}}',
        '{"files":{"../api.py":"x"}}',
        '{"files":{"/api.py":"x"}}',
        '{"files":{"new.py":"x"}}',
        'commentary {"files":{}}',
        '```json\n{"files":{}}\n```\n```json\n{"files":{}}\n```',
        '{"files":{},"note":"hi"}',
    ],
)
def test_patch_contract_rejects_ambiguous_or_unbounded_edits(raw):
    with pytest.raises(ValueError):
        ex.parse_patch(task_for(), raw)


def test_single_fence_and_omitted_files():
    task = task_for()
    assert ex.parse_patch(task, '```json\n{"files":{}}\n```') == task.files


def test_local_cycle_is_observable_import_error():
    files = {"api.py": "import calculation\ndef solve(data): return 1\n", "calculation.py": "import api\n"}
    row = ex.execute_inputs(task_for(files), files, [{}])[0]
    assert row["ok"] is True and row["exception"] == "ImportError"


def test_host_payload_excludes_expected_reference_and_keeps_source_exact(monkeypatch):
    task = task_for()
    observed = []

    def fake(payload):
        observed.append(payload)
        return 0, json.dumps({"rows": [{"ok": True, "value": [-3, 2], "exception": None, "input_unchanged": True}]}), ""

    monkeypatch.setattr(ex, "run_payload", fake)
    assert ex.evaluate(task, {"files": {}})["hard"]
    assert set(observed[0]) == {"files", "inputs", "entry_module", "entry_function"}
    assert observed[0]["files"] == task.files


def test_infrastructure_failure_stays_unknown(monkeypatch):
    monkeypatch.setattr(ex, "run_payload", lambda _: (134, "", "blocked"))
    result = ex.evaluate(task_for(), {"files": {}})
    assert result["execution_ok"] is False and result["hard"] is None


def test_public_only_does_not_execute_private(monkeypatch):
    task = task_for()
    task = replace(
        task, private_cases=[{**task.public_cases[0], "label": "private", "input": {"a": 99, "b": 3}, "public": False}]
    )
    seen = []

    def fake(task, files, inputs):
        seen.extend(inputs)
        return [{"ok": True, "value": [-3, 2], "exception": None, "input_unchanged": True} for _ in inputs]

    monkeypatch.setattr(ex, "execute_inputs", fake)
    assert ex.evaluate(task, {"files": {}}, public_only=True)["hard"]
    assert seen == [{"a": -7, "b": 3}]


def test_os_sandbox_and_environment_are_still_enforced():
    assert ex.sandbox_probe()["ok"] is True
    assert ex._PREFIX == ex.previous.CHILD_RUNNER.split("rows=[]\n", 1)[0]
    assert "resource.RLIMIT_CPU,(5,5)" in ex.CHILD_RUNNER
    assert "resource.RLIMIT_FSIZE,(0,0)" in ex.CHILD_RUNNER
    assert "resource.RLIMIT_NOFILE,(32,32)" in ex.CHILD_RUNNER
