"""Offline Docker protocol tests; only explicit trusted fixtures run locally.

These are engineering checks, not real model outputs or safety/gain evidence.
Docker itself is never invoked by the default test suite.
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation import sandbox, sandbox_worker
from skillopt.validator_pilot.api import digest

IMAGE = "python@sha256:" + "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
FILES = {"solution.py": "def solve(values):\n    return sum(values)\n"}


def call(executor=None, **overrides):
    values = {"files": FILES, "module": "solution", "function": "solve", "args": [[1, 2]], "kwargs": {}}
    values.update(overrides)
    return (executor or sandbox.DockerExecutor(IMAGE)).run(**values)


def observation(**overrides):
    row = {"protocol": sandbox.PROTOCOL, "status": "observed", "actual": 3,
           "before_args": [[1, 2]], "after_args": [[1, 2]], "before_kwargs": {},
           "after_kwargs": {}, "exception": None}
    row.update(overrides)
    return row


@pytest.fixture
def mocked_docker(monkeypatch):
    """No candidate code executes: the mock returns declared observation bytes."""
    monkeypatch.setattr(sandbox.platform, "system", lambda: "Linux")
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "/fixture/bin/docker")
    state = {"commands": [], "observation": observation(), "inspect": {
        "Id": IMAGE_ID, "RepoDigests": [IMAGE], "Os": "linux", "Volumes": None}}

    def command(argv, timeout, limit=sandbox.MAX_OUTPUT_BYTES):
        state["commands"].append((argv, timeout))
        if argv[1:3] == ["image", "inspect"]:
            return state.get("inspect_command", sandbox._Command(0, json.dumps(state["inspect"]).encode()))
        if argv[1] == "rm":
            return state.get("cleanup", sandbox._Command(0))
        assert argv[1] == "run"
        spec = argv[argv.index("--mount") + 1]
        root = Path(spec.split("source=", 1)[1].split(",target=", 1)[0])
        state["root"] = root
        state["materialized"] = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
        state["request"] = json.loads((root / "request.json").read_text())
        assert not ((root / "source" / "solution.py").stat().st_mode & 0o222)
        return state.get("run_command", sandbox._Command(0, json.dumps(state["observation"]).encode()))

    monkeypatch.setattr(sandbox, "_bounded_command", command)
    return state


def test_receipt_source_binding_and_declared_measurement_boundary(mocked_docker):
    executor = sandbox.DockerExecutor(IMAGE)
    identity = executor.identity
    row = call(executor)
    verify(row)
    assert row["status"] == "observed"
    assert row["actual"] == 3
    assert row["exception"] is None
    assert row["executor_identity"] == identity
    assert row["measurement_trust"] == "bounded_non_adversarial_process"
    assert not identity["formal_adversarial_authorization"]
    assert not row["isolation"]["adversarial_measurement_authenticated"]
    assert row["source_hash"] == digest(FILES)
    assert row["before_args"] == row["after_args"] == [[1, 2]]
    assert row["image_id"] == IMAGE_ID
    assert row["cleanup_confirmed"]


def test_only_explicit_public_files_mounted_and_limits_enforced(mocked_docker):
    row = call()
    commands = [argv for argv, _ in mocked_docker["commands"]]
    run = commands[1]
    expected = {"--pull=never", "--network=none", "--read-only", "--user=65534:65534",
                "--cap-drop=ALL", "--security-opt=no-new-privileges=true", "--pids-limit=64",
                "--memory=256m", "--memory-swap=256m", "--cpus=1", "--ipc=none",
                "--no-healthcheck", "--log-driver=none"}
    assert expected <= set(run)
    assert run.count("--mount") == 1
    assert "target=/input,readonly" in run[run.index("--mount") + 1]
    assert not any("docker.sock" in arg or ".env" in arg or "--privileged" in arg for arg in run)
    assert mocked_docker["materialized"] == ["request.json", "source/solution.py", "worker.py"]
    assert set(mocked_docker["request"]) == {"module", "function", "args", "kwargs"}
    assert commands[-1] == ["/fixture/bin/docker", "rm", "--force", row["container_name"]]
    assert not mocked_docker["root"].exists()


@pytest.mark.parametrize("configuration", [{"image": "python:3.11-slim"}, {"image": "python:latest"}, {"image": "sha256:abc"}])
def test_unpinned_images_are_unsupported_without_pull(mocked_docker, configuration):
    row = call(sandbox.DockerExecutor(**configuration))
    assert row["status"] == "unsupported"
    assert row["reason"] == "digest_pinned_image_required"
    assert not mocked_docker["commands"]


def test_linux_required_and_no_host_fallback(monkeypatch):
    monkeypatch.setattr(sandbox.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(sandbox, "_bounded_command", lambda *a, **k: pytest.fail("No subprocess allowed"))
    assert call()["reason"] == "linux_docker_required"


def test_missing_docker_is_unsupported_without_host_fallback(mocked_docker, monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: None)
    assert call()["reason"] == "docker_unavailable"
    assert not mocked_docker["commands"]


@pytest.mark.parametrize("update", [{"RepoDigests": []}, {"Os": "windows"}, {"Id": "unknown"}, {"Volumes": {"/secret": {}}}])
def test_image_identity_and_unrequested_volumes_fail_closed(mocked_docker, update):
    mocked_docker["inspect"].update(update)
    assert call()["reason"] == "image_inspection_mismatch"
    assert len(mocked_docker["commands"]) == 1


def test_content_addressed_image_id_supported(mocked_docker):
    assert call(sandbox.DockerExecutor(IMAGE_ID))["status"] == "observed"


@pytest.mark.parametrize("command", [sandbox._Command(1), sandbox._Command(None, unavailable=True),
                                     sandbox._Command(0, timed_out=True), sandbox._Command(0, overflow=True)])
def test_image_daemon_failures_are_unsupported(mocked_docker, command):
    mocked_docker["inspect_command"] = command
    assert call()["reason"] == "pinned_image_or_daemon_unavailable"


@pytest.mark.parametrize("command,reason", [
    (sandbox._Command(-9, timed_out=True), "execution_timeout"),
    (sandbox._Command(-9, overflow=True), "execution_output_limit"),
    (sandbox._Command(125, stderr=b"container could not start"), "container_execution_failed"),
    (sandbox._Command(None, unavailable=True), "container_execution_failed"),
])
def test_failed_execution_still_removes_exact_container(mocked_docker, command, reason):
    mocked_docker["run_command"] = command
    row = call()
    assert row["status"] == "execution_error"
    assert row["reason"] == reason
    assert row["cleanup_confirmed"]
    assert mocked_docker["commands"][-1][0][-1] == row["container_name"]
    assert row["actual"] is None


def test_cleanup_failure_not_silent_even_with_valid_result(mocked_docker):
    mocked_docker["cleanup"] = sandbox._Command(1, stderr=b"daemon disconnected")
    row = call()
    assert row["status"] == "execution_error"
    assert row["reason"] == "container_cleanup_unconfirmed"
    assert not row["cleanup_confirmed"]
    assert row["container_name"].startswith("skillval-")


def test_already_absent_exact_container_is_clean(mocked_docker):
    mocked_docker["cleanup"] = sandbox._Command(1, stderr=b"Error response from daemon: No such container")
    assert call()["cleanup_confirmed"]


@pytest.mark.parametrize("update", [{"before_args": [[999]]}, {"before_args": {}}, {"after_args": {}},
                                  {"after_kwargs": []}, {"hidden_oracle": 42}, {"exception": "huge invalid message"},
                                  {"status": "pass"}, {"protocol": "wrong"}])
def test_observation_identity_and_schema_mismatch_is_not_evidence(mocked_docker, update):
    mocked_docker["observation"].update(update)
    row = call()
    assert row["reason"] == "invalid_observation_receipt"
    assert row["status"] == "execution_error"
    assert row["actual"] is None


@pytest.mark.parametrize("raw", [b"junk", b'{"a":1,"a":2}', b'{"actual":NaN}', b"{}{}", b"[]"])
def test_unparseable_duplicate_nonfinite_or_extra_json_is_not_a_task_failure(mocked_docker, raw):
    mocked_docker["run_command"] = sandbox._Command(0, raw)
    assert call()["reason"] == "invalid_observation_receipt"


def test_observed_target_exception_is_not_infrastructure_failure(mocked_docker):
    mocked_docker["observation"].update(actual=None, exception="ValueError", after_args=[[1]])
    row = call()
    assert row["status"] == "observed"
    assert row["exception"] == "ValueError"
    assert row["after_args"] == [[1]]


def test_worker_serialization_failure_stays_unknown_execution_error(mocked_docker):
    mocked_docker["observation"] = {"protocol": sandbox.PROTOCOL, "status": "execution_error",
                                    "reason": "non_json_or_oversized_observation"}
    assert call()["reason"] == "non_json_or_oversized_observation"


@pytest.mark.parametrize("path", ["../evil.py", "/etc/evil.py", "a/../../evil.py", "a\\evil.py", ".env", ".git/config"])
def test_unsafe_or_credential_paths_rejected_before_subprocess(mocked_docker, path):
    with pytest.raises(ValueError):
        call(files={**FILES, path: "fixture only"})
    assert not mocked_docker["commands"]


@pytest.mark.parametrize("kwargs", [{"module": "os.system"}, {"module": "../solution"}, {"function": "solve()"},
                                  {"args": (1,)}, {"kwargs": {1: 2}}, {"args": [float("nan")]},
                                  {"args": [object()]}, {"files": {**FILES, "solution.py/other.py": ""}}])
def test_invalid_json_callable_or_file_collision_is_rejected(mocked_docker, kwargs):
    with pytest.raises(ValueError):
        call(**kwargs)
    assert not mocked_docker["commands"]


@pytest.mark.parametrize("kwargs", [{"timeout_seconds": 0}, {"timeout_seconds": math.inf}, {"timeout_seconds": True},
                                  {"memory_mb": 8}, {"memory_mb": True}, {"cpus": math.nan}, {"cpus": 99}])
def test_resource_limits_bounded(kwargs):
    with pytest.raises(ValueError):
        sandbox.DockerExecutor(IMAGE, **kwargs)


def test_source_and_input_size_limits(mocked_docker):
    with pytest.raises(ValueError, match="byte budget"):
        call(files={"solution.py": "#" * (sandbox.MAX_SOURCE_BYTES + 1)})
    with pytest.raises(ValueError, match="byte budget"):
        call(args=["x" * (sandbox.MAX_INPUT_BYTES + 1)])


def test_mutating_fixture_observation_snapshots_inputs(monkeypatch):
    # This is a developer-written trusted fixture function, NOT arbitrary source.
    def fixture(values, options):
        values.append(4)
        options["seen"] = True
        return sum(values)

    monkeypatch.setattr(sandbox_worker.importlib, "import_module", lambda _: SimpleNamespace(
        solve=fixture, __file__="/input/source/trusted_fixture.py"))
    result = sandbox_worker.observe({"module": "trusted_fixture", "function": "solve", "args": [[1, 2]],
                                     "kwargs": {"options": {}}})
    assert result["actual"] == 7
    assert result["before_args"] == [[1, 2]]
    assert result["after_args"] == [[1, 2, 4]]
    assert result["before_kwargs"] == {"options": {}}
    assert result["after_kwargs"] == {"options": {"seen": True}}


def test_fixture_exception_records_mutation_without_exception_text(monkeypatch):
    def fixture(values):
        values.clear()
        raise ValueError("A private-looking string should not appear in receipt")

    monkeypatch.setattr(sandbox_worker.importlib, "import_module", lambda _: SimpleNamespace(
        solve=fixture, __file__="/input/source/trusted_fixture.py"))
    result = sandbox_worker.observe({"module": "trusted_fixture", "function": "solve", "args": [[1]], "kwargs": {}})
    assert result["exception"] == "ValueError"
    assert result["after_args"] == [[]]
    assert "private-looking" not in json.dumps(result)


@pytest.mark.parametrize("output", [object(), float("nan"), "x" * 100000])
def test_fixture_non_json_or_oversized_output_not_claimed_observed(monkeypatch, output):
    monkeypatch.setattr(sandbox_worker.importlib, "import_module", lambda _: SimpleNamespace(
        solve=lambda: output, __file__="/input/source/trusted_fixture.py"))
    result = sandbox_worker.observe({"module": "trusted_fixture", "function": "solve", "args": [], "kwargs": {}})
    assert result["status"] == "execution_error"


def test_cached_module_cannot_masquerade_as_artifact(monkeypatch):
    monkeypatch.setattr(sandbox_worker.importlib, "import_module", lambda _: SimpleNamespace(
        solve=lambda: 3, __file__="/usr/local/lib/python/stdlib.py"))
    result = sandbox_worker.observe({"module": "trusted_fixture", "function": "solve", "args": [], "kwargs": {}})
    assert result["status"] == "execution_error"
    assert result["reason"] == "module_origin_mismatch"


def test_worker_cli_rejects_host_invocation(monkeypatch):
    monkeypatch.setattr(sandbox_worker.sys, "argv", ["worker.py", "/irrelevant/request.json"])
    monkeypatch.setattr(sandbox_worker.os.path, "isfile", lambda _: False)
    with pytest.raises(SystemExit, match="Container-only"):
        sandbox_worker.main()


def test_bounded_transport_collects_trusted_fixture_stdout_and_stderr():
    # Literal developer-owned subprocess tests ONLY the pipe transport.
    row = sandbox._bounded_command([sys.executable, "-c", "import sys; print('fixture'); print('diagnostic', file=sys.stderr)"], 5)
    assert row.code == 0 and row.stdout == b"fixture\n" and row.stderr == b"diagnostic\n"


def test_bounded_transport_rejects_trusted_fixture_flood():
    row = sandbox._bounded_command([sys.executable, "-c", "print('x' * 1000000)"], 5, limit=128)
    assert row.overflow
    assert len(row.stdout) <= 128


def test_bounded_transport_times_out_trusted_fixture():
    row = sandbox._bounded_command([sys.executable, "-c", "import time; time.sleep(2)"], 0.05)
    assert row.timed_out


def test_bounded_transport_reports_missing_binary():
    row = sandbox._bounded_command(["/nonexistent/skill-validation-fixture-binary"], 1)
    assert row.unavailable
