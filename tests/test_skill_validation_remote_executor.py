"""Offline SSH tests: candidate source remains inert data, never executed."""
import io
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import remote_executor as remote
from skillopt.validator_pilot.api import digest

IMAGE = "sha256:" + "a" * 64
FILES = {"solution.py": "THIS IS INERT FIXTURE SOURCE, NOT EXECUTABLE"}
PAYLOAD = {"files": FILES, "module": "solution", "function": "solve", "args": [[1, 2]], "kwargs": {}}


def receipt(identity, payload=PAYLOAD):
    call = {k: v for k, v in payload.items() if k != "files"}
    return seal({"status": "observed", "actual": 3, "before_args": payload["args"],
                 "after_args": payload["args"], "before_kwargs": payload["kwargs"],
                 "after_kwargs": payload["kwargs"], "exception": None, "cleanup_confirmed": True,
                 "executor_identity": identity, "input_hash": digest(payload),
                 "source_hash": digest(payload["files"]), "call_hash": digest(call)})


class FixtureProcess:
    """Real bounded pipe IO, but no subprocess and no candidate evaluation."""
    def __init__(self, executor, state):
        self.returncode = None
        in_read, in_write = os.pipe()
        out_read, out_write = os.pipe()
        err_read, err_write = os.pipe()
        self.stdin, self.stdout, self.stderr = (os.fdopen(in_write, "wb", buffering=0),
                                               os.fdopen(out_read, "rb", buffering=0),
                                               os.fdopen(err_read, "rb", buffering=0))

        def worker():
            try:
                with os.fdopen(in_read, "rb", buffering=0) as reader, os.fdopen(out_write, "wb", buffering=0) as writer, \
                        os.fdopen(err_write, "wb", buffering=0) as error:
                    hello = {"protocol": remote.VERSION, "type": "hello", "executor_identity": executor.identity,
                             "transport_source_hash": remote._source_hash(), "cwd": executor.remote_repo}
                    hello.update(state.get("hello_update", {}))
                    if state.get("hello_raw") is not None:
                        writer.write(state["hello_raw"])
                    else:
                        writer.write(json.dumps(hello).encode() + b"\n")
                    while True:
                        line = reader.readline(remote.MAX_REQUEST_BYTES + 1)
                        if not line:
                            break
                        request = json.loads(line)
                        state["requests"].append(request)
                        if state.get("disconnect"):
                            break
                        if state.get("block"):
                            state["release"].wait(2)
                            break
                        if state.get("stderr"):
                            error.write(state["stderr"])
                            break
                        result = receipt(executor.identity, request["payload"])
                        if state.get("result_update"):
                            result = seal({**{k: v for k, v in result.items() if k != "record_hash"},
                                           **state["result_update"]})
                        response = {"protocol": remote.VERSION, "request_hash": request["request_hash"], "result": result}
                        response.update(state.get("response_update", {}))
                        writer.write(state.get("response_raw", json.dumps(response).encode() + b"\n"))
            except (BrokenPipeError, OSError):
                pass
            finally:
                self.returncode = 0

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        self.thread.join(timeout)
        return self.returncode


@pytest.fixture
def transport(monkeypatch):
    executor = remote.SSHExecutor(IMAGE)
    state = {"requests": [], "launches": [], "release": threading.Event()}

    def popen(argv, **kwargs):
        state["launches"].append((argv, kwargs))
        return FixtureProcess(executor, state)

    monkeypatch.setattr(remote.subprocess, "Popen", popen)
    yield executor, state
    state["release"].set()
    executor.close()


def test_two_calls_share_connection_and_keep_docker_identity(transport):
    executor, state = transport
    identity = remote.DockerExecutor(IMAGE).identity
    for _ in range(2):
        result = verify(executor.run(**PAYLOAD))
        assert result["status"] == "observed" and result["actual"] == 3
        assert result["executor_identity"] == identity == executor.identity
        assert digest(result["executor_identity"]) == digest(identity)
        assert result["ssh_transport"] == executor.transport_identity
        assert result["remote_record_hash"]
    assert len(state["launches"]) == 1
    assert [r["sequence"] for r in state["requests"]] == [1, 2]
    assert all(set(r["payload"]) == set(PAYLOAD) for r in state["requests"])
    assert state["launches"][0][1]["shell"] is False
    argv = state["launches"][0][0]
    assert "StrictHostKeyChecking=yes" in argv and "BatchMode=yes" in argv
    assert FILES["solution.py"] not in str(argv)


def test_concurrent_clients_use_one_serial_request_sequence(transport):
    executor, state = transport
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: executor.run(**PAYLOAD), range(8)))
    assert all(row["status"] == "observed" for row in results)
    assert [r["sequence"] for r in state["requests"]] == list(range(1, 9))
    assert len(state["launches"]) == 1


@pytest.mark.parametrize("update", [
    {"cwd": "/wrong/snapshot"}, {"transport_source_hash": "bad"},
    {"executor_identity": {}}, {"protocol": "bad"}, {"unrequested": "field"},
])
def test_handshake_mismatch_terminal_without_sending_candidate(transport, update):
    executor, state = transport
    state["hello_update"] = update
    assert executor.run(**PAYLOAD)["reason"] == "ssh_identity_mismatch"
    assert executor.run(**PAYLOAD)["reason"] == "ssh_identity_mismatch"
    assert len(state["launches"]) == 1 and not state["requests"]


@pytest.mark.parametrize("update", [
    {"input_hash": "bad"}, {"source_hash": "bad"}, {"call_hash": "bad"},
    {"executor_identity": {}}, {"status": "pass"}, {"before_args": [[999]]},
    {"cleanup_confirmed": False},
])
def test_receipt_mismatch_returns_bound_unknown_not_semantic_fail(transport, update):
    executor, state = transport
    state["result_update"] = update
    result = verify(executor.run(**PAYLOAD))
    assert result["reason"] == "ssh_receipt_mismatch"
    assert result["status"] == "execution_error" and result["actual"] is None
    assert result["input_hash"] == digest(PAYLOAD)
    assert result["source_hash"] == digest(FILES)
    assert result["executor_identity"] == executor.identity
    assert not result["cleanup_confirmed"]
    executor.run(**PAYLOAD)
    assert len(state["requests"]) == 1 and len(state["launches"]) == 1


def test_response_request_hash_cannot_be_reused(transport):
    executor, state = transport
    state["response_update"] = {"request_hash": "another-request"}
    assert executor.run(**PAYLOAD)["reason"] == "ssh_receipt_mismatch"


@pytest.mark.parametrize("raw", [b"not json\n", b'{"x":1,"x":2}\n', b'{"x":NaN}\n'])
def test_invalid_protocol_json(transport, raw):
    executor, state = transport
    state["response_raw"] = raw
    assert executor.run(**PAYLOAD)["reason"] == "ssh_invalid_json"


def test_disconnect_is_not_retried_or_run_locally(transport):
    executor, state = transport
    state["disconnect"] = True
    assert executor.run(**PAYLOAD)["reason"] == "ssh_disconnected"
    assert executor.run(**PAYLOAD)["reason"] == "ssh_disconnected"
    assert len(state["launches"]) == len(state["requests"]) == 1


def test_connection_failure_produces_valid_error_receipt(monkeypatch):
    executor = remote.SSHExecutor(IMAGE)
    monkeypatch.setattr(remote.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    result = verify(executor.run(**PAYLOAD))
    assert result["reason"] == "ssh_transport_unavailable"
    assert result["input_hash"] == digest(PAYLOAD)


def test_response_and_stderr_are_bounded(transport, monkeypatch):
    executor, state = transport
    monkeypatch.setattr(remote, "MAX_RESPONSE_BYTES", 4096)
    state["response_raw"] = b"x" * 8192
    assert executor.run(**PAYLOAD)["reason"] == "ssh_response_limit"


def test_stderr_is_bounded_without_reporting_its_contents(transport, monkeypatch):
    executor, state = transport
    monkeypatch.setattr(remote, "MAX_STDERR_BYTES", 10)
    state["stderr"] = b"sensitive diagnostic contents" * 10
    result = executor.run(**PAYLOAD)
    assert result["reason"] in {"ssh_stderr_limit", "ssh_disconnected"}
    assert "sensitive" not in json.dumps(result)


def test_deadline_is_terminal(transport):
    executor, state = transport
    executor.call_timeout_seconds = 2.05  # fixture-only short clock including teardown reserve
    state["block"] = True
    result = executor.run(**PAYLOAD)
    assert result["reason"] == "ssh_call_timeout"
    assert executor.run(**PAYLOAD)["reason"] == "ssh_call_timeout"
    assert len(state["requests"]) == 1


def test_close_prevents_implicit_reconnect(transport):
    executor, state = transport
    executor.close()
    assert executor.run(**PAYLOAD)["reason"] == "ssh_executor_closed"
    assert not state["launches"]


@pytest.mark.parametrize("options", [
    {"host": "-oProxyCommand=evil"}, {"host": "host;evil"}, {"remote_repo": "/"},
    {"remote_repo": "/root/../tmp"}, {"remote_repo": "/root/repo;evil"},
    {"remote_python": "python"}, {"call_timeout_seconds": 46}, {"call_timeout_seconds": 15},
    {"image": "python:latest"},
])
def test_invalid_transport_configuration_rejected(options):
    with pytest.raises(ValueError):
        remote.SSHExecutor(**{"image": IMAGE, **options})


@pytest.mark.parametrize("override", [
    {"files": {".env": "secret"}}, {"files": {"../source.py": "bad"}},
    {"module": "os;echo bad"}, {"module": "missing"}, {"args": [float("nan")]},
    {"kwargs": []}, {"files": {"solution.py": "x" * (remote.MAX_SOURCE_BYTES + 1)}},
])
def test_invalid_public_input_never_starts_transport(transport, override):
    executor, state = transport
    with pytest.raises(ValueError):
        executor.run(**{**PAYLOAD, **override})
    assert not state["launches"]


class DeclaredExecutor:
    def __init__(self):
        self.identity = remote.DockerExecutor(IMAGE).identity
        self.calls = []

    def run(self, **payload):
        self.calls.append(payload)
        return receipt(self.identity, payload)


def request_line(sequence=1, **update):
    request = {"protocol": remote.VERSION, "sequence": sequence, "payload": PAYLOAD}
    request.update(update)
    return json.dumps({**request, "request_hash": digest(request)}).encode() + b"\n"


def test_server_uses_only_supplied_executor_and_public_payload():
    executor, output = DeclaredExecutor(), io.BytesIO()
    remote.serve(executor, io.BytesIO(request_line() + request_line(2)), output)
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]["cwd"] == str(Path.cwd())
    assert rows[0]["executor_identity"] == executor.identity
    assert len(rows) == 3 and executor.calls == [PAYLOAD, PAYLOAD]
    verify(rows[1]["result"])


@pytest.mark.parametrize("raw", [
    b"{}\n", request_line(2), request_line(protocol="bad"),
    request_line(payload={**PAYLOAD, "hidden_oracle": 3}), request_line(sequence=True),
    request_line()[:-1], b'{"x":1,"x":2}\n',
])
def test_server_rejects_malformed_or_privileged_input(raw):
    executor = DeclaredExecutor()
    with pytest.raises(ValueError):
        remote.serve(executor, io.BytesIO(raw), io.BytesIO())
    assert not executor.calls


def test_server_rejects_duplicate_sequence_after_one_execution():
    executor = DeclaredExecutor()
    with pytest.raises(ValueError):
        remote.serve(executor, io.BytesIO(request_line() + request_line()), io.BytesIO())
    assert len(executor.calls) == 1


def test_server_request_byte_limit(monkeypatch):
    monkeypatch.setattr(remote, "MAX_REQUEST_BYTES", 20)
    executor = DeclaredExecutor()
    with pytest.raises(ValueError):
        remote.serve(executor, io.BytesIO(b"x" * 30 + b"\n"), io.BytesIO())
    assert not executor.calls


def test_server_cli_preserves_json_numeric_identity(monkeypatch):
    state = {}
    monkeypatch.setattr(remote.signal, "signal", lambda *args: None)
    monkeypatch.setattr(remote, "serve", lambda e, r, w: state.update(identity=e.identity))
    assert remote.main(["--serve", "--image", IMAGE, "--timeout-seconds", "10", "--cpus", "1"]) == 0
    assert digest(state["identity"]) == digest(remote.DockerExecutor(IMAGE).identity)
