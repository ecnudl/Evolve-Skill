"""Authored engineering-control mocks only: no Docker/model/task execution."""
import contextlib
import inspect
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import pool_guard_control_worker as worker
from scripts import pool_guard_controls as c
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json
from skillopt.skill_validation.sandbox import _Command


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    lock = tmp_path / "native.lock"
    lock.touch()
    monkeypatch.setattr(c, "_image_ready", lambda runtime: {
        "status": "ready", "image_id": runtime["image"], "architecture": "amd64"})
    root = tmp_path / "new"
    value = c.prepare(root, lock)
    return root, value


def authored(item, root, *, cleaned=True):
    logs = c._private_logs(root, item, b"", b"")
    return {"status": "outer_timeout" if item["guard"] and item["case"] == "busy_exit" else "completed",
            "phases": ["sdk_verified"], "cleanup_confirmed": cleaned, "model_calls": 0,
            "image_id": c.IMAGES[item["image"]], "container_calls": 1, "wall_seconds": 0.1,
            "private_logs": logs, "stdout_sha256": logs["stdout"]["sha256"],
            "stderr_sha256": logs["stderr"]["sha256"]}


def test_fixed24_matrix_and_bound_protocol(prepared):
    root, protocol = prepared
    assert c.check(root) == protocol
    assert len(protocol["matrix"]) == 24
    assert set(Counter((x["image"], x["guard"], x["case"]) for x in protocol["matrix"]).values()) == {3}
    assert protocol["runtime"]["outer_timeout_seconds"] == 20 and protocol["model_calls"] == 0
    assert not protocol["hidden_tasks_used"] and not protocol["qualification_or_skill_gate_authorized"]
    assert protocol["sdk_sources"] == c.SDK


def test_mock_controls_are_single_attempt_and_replay_without_new_runs(prepared, monkeypatch):
    root, _ = prepared
    calls = []
    monkeypatch.setattr(c, "_execute", lambda item, root: calls.append(item) or authored(item, root))
    value = c.run(root)
    assert value["status"] == "completed" and value["counts"] == {"completed": 18, "outer_timeout": 6}
    assert len(calls) == value["container_calls"] == 24 and value["model_calls"] == 0
    assert c.run(root) == value and len(calls) == 24
    assert not value["qualification_or_skill_gate_authorized"]


def test_cleanup_uncertainty_stops_and_is_not_retried(prepared, monkeypatch):
    root, _ = prepared
    calls = []
    monkeypatch.setattr(c, "_execute", lambda item, root: calls.append(item) or {**authored(item, root, cleaned=False),
                                                                       "status": "cleanup_unconfirmed"})
    value = c.run(root)
    assert value["status"] == "pending" and value["closed"] == 1
    assert c.run(root) == value and len(calls) == 1


def test_open_control_never_retried(prepared, monkeypatch):
    root, _ = prepared
    calls = []

    def crash(item, root):
        calls.append(item)
        raise KeyboardInterrupt

    monkeypatch.setattr(c, "_execute", crash)
    with pytest.raises(KeyboardInterrupt):
        c.run(root)
    with pytest.raises(ValueError, match="no retries"):
        c.run(root)
    assert len(calls) == 1


def test_resealed_published_record_rejected(prepared, monkeypatch):
    root, _ = prepared
    monkeypatch.setattr(c, "_execute", authored)
    c.run(root)
    path = root / "records/0.json"
    row = read_json(path, sealed=True)
    row.pop("record_hash")
    row["result"]["status"] = "outer_timeout"
    path.write_text(json.dumps(seal(row)))
    with pytest.raises(ValueError, match="Published control record changed"):
        c.run(root)


@pytest.mark.parametrize("field", ["matrix", "sdk_sources", "sources", "runtime"])
def test_modified_protocol_rejected(prepared, field):
    root, _ = prepared
    path = root / "protocol.json"
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    value[field] = [] if field == "matrix" else {}
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="protocol changed"):
        c.check(root)


def test_worker_cannot_run_on_host(monkeypatch):
    monkeypatch.delenv("SKILLOPT_POOL_CONTROL", raising=False)
    with pytest.raises(SystemExit, match="Container-only"):
        worker.main()


def test_decorated_sdk_source_is_unwrapped():
    @contextlib.contextmanager
    def sdk_fixture():
        yield

    assert Path(inspect.getsourcefile(sdk_fixture)).resolve() == Path(contextlib.__file__).resolve()
    assert Path(worker.source_file(sdk_fixture)).resolve() == Path(__file__).resolve()


def test_old_prepared_protocol_is_not_reused(prepared):
    root, value = prepared
    value.pop("record_hash")
    value["version"] = "pool-guard-engineering-controls-v1"
    (root / "protocol.json").write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="protocol changed"):
        c.check(root)


def test_bound_private_log_tamper_rejected_without_new_controls(prepared, monkeypatch):
    root, _ = prepared
    monkeypatch.setattr(c, "_execute", authored)
    c.run(root)
    (root / "logs/0-stderr.bin").write_bytes(b"changed")
    monkeypatch.setattr(c, "_execute", lambda *_: pytest.fail("No new controls"))
    with pytest.raises(ValueError, match="Private control log changed"):
        c.run(root)


def test_private_logs_are_bounded_and_never_overwritten(prepared):
    root, _ = prepared
    item = c.matrix()[0]
    with pytest.raises(ValueError, match="output bound"):
        c._private_logs(root, item, b"x" * 32769, b"")
    value = c._private_logs(root, item, b"private stdout", b"private stderr")
    assert (root / value["stdout"]["path"]).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        c._private_logs(root, item, b"overwritten", b"")


@pytest.mark.parametrize("timeout,cleanup", [(False, True), (True, True), (True, False)])
def test_actual_command_bounded_and_cleanup_result_retained(prepared, monkeypatch, timeout, cleanup):
    calls = []

    def command(args, seconds, **kwargs):
        calls.append((args, seconds, kwargs))
        if args[1] == "rm":
            return _Command(0 if cleanup else 1, b"", b"cleanup_problem")
        raw = b'POOL_DIAG {"phase":"sdk_verified"}\nPrevented attempt to kill PID 42 with signal 15\n'
        if not timeout:
            raw += b'POOL_DIAG {"phase":"after_guard_exit"}\n'
        return _Command(0, raw, b"private_path_not_exported", timed_out=timeout)

    monkeypatch.setattr(c.sandbox, "_bounded_command", command)
    root, _ = prepared
    value = c._execute(deepcopy(c.matrix()[0]), root)
    assert calls[0][1] == 20 and calls[1][1] == 10 and calls[1][0][:3] == ["docker", "rm", "--force"]
    assert all(flag in calls[0][0] for flag in ("--network=none", "--read-only", "--user=65534:65534",
        "--cpus=1", "--memory=8192m", "--pids-limit=128", "--workdir=/tmp", "-u"))
    assert value["status"] == ("cleanup_unconfirmed" if not cleanup else "outer_timeout" if timeout else "completed")
    assert value["cleanup_confirmed"] is cleanup and value["kill_denial_messages"] == 1
    assert "private_path_not_exported" not in json.dumps(value) and value["model_calls"] == 0
    assert (root / value["private_logs"]["stderr"]["path"]).read_bytes() == b"private_path_not_exported"
    c._validate_logs(root, c.matrix()[0], value)
