"""Public compatibility covers all partitions without executing hidden audits."""
import json
from copy import deepcopy

from scripts import preflight_natural_validation as preflight
from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.checks import CallableTask, PublicCase
from skillopt.skill_validation.models import Obligation, TaskContract
from skillopt.validator_pilot.api import digest, write_immutable_json


def test_full_public_preflight_has_no_hidden_calls_and_replays(tmp_path, monkeypatch):
    parts = ("development", "verifier_calibration", "skill_confirmation", "final")
    manifest = seal({"splits": {p: [{"task_id": p}] for p in parts}})
    frozen, out = tmp_path / "frozen", tmp_path / "public"
    write_immutable_json(frozen / "data_manifest.json", manifest)
    calls = []

    def load(repo, given, part):
        assert given == manifest
        prompt = "Return True."
        contract = TaskContract(part, part, "family-" + part, "fixture", part, "coding", "return",
                                prompt, (Obligation("behavior", "requested_behavior", prompt, prompt),))
        case = PublicCase("one", '{"args":[],"kwargs":{}}', prompt, ("behavior",), expected_json="true")
        task = CallableTask(contract, "public_runner", "check", (case,))
        return [{"public_task": task, "task": task,
                 "public_wrapper": {"path": "public_runner.py", "content": "# fixture"},
                 "host_audit": {"reference_code": "# reference fixture", "secret": "HIDDEN_SENTINEL"}}]

    class Pool:
        identity = {"kind": "fixture"}
        transport_identity = {"kind": "fixture-no-network"}

        def __init__(self, *_):
            pass

        def run(self, files, module, function, args, kwargs):
            assert module in {"probe", "public_runner"}
            assert "HIDDEN_SENTINEL" not in json.dumps(files)
            calls.append(module)
            call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
            return seal({"status": "observed", "actual": True, "exception": None,
                         "reason": "fixture", "cleanup_confirmed": True,
                         "input_hash": digest({"files": files, **call}), "source_hash": digest(files),
                         "call_hash": digest(call), "executor_identity": self.identity,
                         "before_args": deepcopy(args), "after_args": deepcopy(args),
                         "before_kwargs": deepcopy(kwargs), "after_kwargs": deepcopy(kwargs)})

        def close(self):
            pass

    monkeypatch.setattr(preflight, "load_tasks", load)
    monkeypatch.setattr(preflight, "ExecutorPool", Pool)
    first = preflight.run_public(tmp_path, frozen, out, "/fixture", 2)
    assert first["task_count"] == 4 and first["counts"] == {"pass": 4}
    assert {r["partition"] for r in first["rows"]} == set(parts)
    assert first["model_calls"] == 0 and not first["hidden_audit_executed"]
    assert calls.count("public_runner") == 4
    assert preflight.run_public(tmp_path, frozen, out, "/fixture", 2) == first
    assert calls.count("public_runner") == 4
