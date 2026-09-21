"""Bounded SSH transport for the existing Linux Docker callable executor.

Only public source and call arguments cross SSH. Candidate Python is never
executed by this module, on either host. SSH host-key trust must already exist.
An interrupted connection is terminal: subsequent calls return unavailable
evidence, rather than silently reconnecting or rerunning an uncertain call.
The Docker observer remains a non-adversarial measurement, not an authenticated
defence against deliberately hostile candidate code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePosixPath

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

from .models import file_path, require
from .sandbox import (
    _IDENTIFIER,
    _IMAGE,
    MAX_INPUT_BYTES,
    MAX_SOURCE_BYTES,
    DockerExecutor,
    _json_value,
    _strict_json,
)

VERSION = "skill-validation-ssh-docker-v1"
MAX_REQUEST_BYTES = 6 * MAX_SOURCE_BYTES + 6 * MAX_INPUT_BYTES + 16384
MAX_RESPONSE_BYTES = 262144
MAX_STDERR_BYTES = 65536


def _source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _absolute_path(value):
    require(type(value) is str and 1 < len(value) <= 512
            and re.fullmatch(r"/[A-Za-z0-9_./-]+", value) is not None
            and ".." not in PurePosixPath(value).parts and str(PurePosixPath(value)) == value,
            "Expected a normalized, non-root trusted absolute path")
    return value


def _request(files, module, function, args, kwargs):
    """Pure validation/detachment; does not invoke a local executor."""
    require(type(files) is dict and 0 < len(files) <= 100, "Expected bounded public source files")
    for path, content in files.items():
        file_path(path)
        require(type(content) is str, "Expected source text")
        require(not any(p.startswith(".env") or p == ".git" for p in PurePosixPath(path).parts),
                "Credentials and Git history cannot enter the executor")
    require(sum(len(v.encode("utf-8")) for v in files.values()) <= MAX_SOURCE_BYTES,
            "Source exceeds execution budget")
    require(type(module) is str and len(module) <= 256
            and all(_IDENTIFIER.fullmatch(p) for p in module.split(".")), "Invalid module identifier")
    require(type(function) is str and _IDENTIFIER.fullmatch(function), "Invalid function identifier")
    prefix = module.replace(".", "/")
    require(prefix + ".py" in files or prefix + "/__init__.py" in files,
            "Callable module must be supplied as public source")
    require(type(args) is list and type(kwargs) is dict, "Expected args list and kwargs object")
    call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
    _json_value(call)
    raw = json.dumps(call, ensure_ascii=False, allow_nan=False).encode()
    require(len(raw) <= MAX_INPUT_BYTES, "Call exceeds execution budget")
    return {"files": dict(files), **json.loads(raw)}


class _TransportError(Exception):
    pass


class SSHExecutor:
    """Persistent, serial SSH adapter with exactly the Docker policy identity."""

    def __init__(self, image, *, host="PJ-CL4MIND-DULIN", remote_repo="/root/Evolve-Skill-validation",
                 remote_python="/root/miniconda3/envs/skill_validation/bin/python",
                 timeout_seconds=10, call_timeout_seconds=40, memory_mb=256, cpus=1):
        require(type(host) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", host),
                "Expected a configured SSH host alias")
        require(type(call_timeout_seconds) in (int, float) and 0 < call_timeout_seconds <= 45,
                "SSH call timeout must be in (0,45]")
        require(_IMAGE.fullmatch(image or "") is not None, "A digest-pinned image is required")
        require(timeout_seconds + 12 < call_timeout_seconds,
                "SSH deadline must allow Docker execution, inspection and cleanup")
        self._policy = DockerExecutor(image, timeout_seconds, memory_mb, cpus)
        self.host, self.remote_repo = host, _absolute_path(remote_repo)
        self.remote_python = _absolute_path(remote_python)
        self.call_timeout_seconds = call_timeout_seconds
        self._proc = None
        self._stdout = bytearray()
        self._stderr_bytes = 0
        self._lock = threading.Lock()
        self._sequence = 0
        self._terminal_reason = None

    @property
    def identity(self):
        return self._policy.identity

    @property
    def transport_identity(self):
        return {"version": VERSION, "host": self.host, "remote_repo": self.remote_repo,
                "remote_python": self.remote_python, "transport_source_hash": _source_hash(),
                "call_timeout_seconds": self.call_timeout_seconds, "automatic_reconnect": False}

    def _command(self):
        policy = self.identity
        arguments = [self.remote_python, "-u", "-m", "skillopt.skill_validation.remote_executor",
                     "--serve", "--image", policy["image"], "--timeout-seconds", str(policy["timeout_seconds"]),
                     "--memory-mb", str(policy["memory_mb"]), "--cpus", str(policy["cpus"])]
        remote = "cd " + shlex.quote(self.remote_repo) + " && exec " + shlex.join(arguments)
        return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2", self.host, remote]

    def _exchange(self, outbound, deadline):
        """Bound writes and both output streams, including partial JSON lines."""
        proc = self._proc
        position = 0
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
            selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
            if outbound:
                selector.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
            while True:
                if b"\n" in self._stdout and position == len(outbound):
                    line, _, rest = self._stdout.partition(b"\n")
                    self._stdout = bytearray(rest)
                    if len(line) > MAX_RESPONSE_BYTES:
                        raise _TransportError("ssh_response_limit")
                    try:
                        return _strict_json(bytes(line))
                    except (ValueError, TypeError, RecursionError):
                        raise _TransportError("ssh_invalid_json") from None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _TransportError("ssh_call_timeout")
                for key, _ in selector.select(min(remaining, 0.1)):
                    if key.data == "stdin":
                        try:
                            position += os.write(proc.stdin.fileno(), outbound[position:position + 65536])
                        except BlockingIOError:
                            continue
                        if position == len(outbound):
                            selector.unregister(proc.stdin)
                        continue
                    try:
                        chunk = os.read(key.fileobj.fileno(), 8192)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        if key.data == "stdout":
                            raise _TransportError("ssh_disconnected")
                        continue
                    if key.data == "stdout":
                        self._stdout.extend(chunk)
                        if len(self._stdout) > MAX_RESPONSE_BYTES:
                            raise _TransportError("ssh_response_limit")
                    else:
                        self._stderr_bytes += len(chunk)
                        if self._stderr_bytes > MAX_STDERR_BYTES:
                            raise _TransportError("ssh_stderr_limit")

    def _start(self, deadline):
        self._proc = subprocess.Popen(self._command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, shell=False, start_new_session=True)
        for pipe in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            os.set_blocking(pipe.fileno(), False)
        hello = self._exchange(b"", deadline)
        expected = {"protocol": VERSION, "type": "hello", "executor_identity": self.identity,
                    "transport_source_hash": _source_hash(), "cwd": self.remote_repo}
        if digest(hello) != digest(expected):
            raise _TransportError("ssh_identity_mismatch")

    def _dispose(self):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    def _unavailable(self, payload, reason, started):
        call = {k: v for k, v in payload.items() if k != "files"}
        return seal({"version": VERSION, "status": "execution_error", "actual": None,
                     "before_args": None, "after_args": None, "before_kwargs": None, "after_kwargs": None,
                     "exception": None, "reason": reason, "input_hash": digest(payload),
                     "source_hash": digest(payload["files"]), "call_hash": digest(call),
                     "executor_identity": self.identity, "measurement_trust": "bounded_non_adversarial_process",
                     "cleanup_confirmed": False, "duration_seconds": round(time.monotonic() - started, 6),
                     "ssh_transport": self.transport_identity,
                     "diagnostic": "Transport unavailable is not a confirmed task failure; do not resample."})

    def run(self, files, module, function, args, kwargs):
        payload = _request(files, module, function, args, kwargs)
        with self._lock:
            started = time.monotonic()
            if self._terminal_reason:
                return self._unavailable(payload, self._terminal_reason, started)
            # Reserve bounded local process teardown within the public cap.
            deadline = started + self.call_timeout_seconds - 2
            try:
                if self._proc is None:
                    self._start(deadline)
                self._sequence += 1
                request = {"protocol": VERSION, "sequence": self._sequence, "payload": payload}
                request_hash = digest(request)
                encoded = json.dumps({**request, "request_hash": request_hash}, ensure_ascii=False,
                                     allow_nan=False).encode() + b"\n"
                require(len(encoded) <= MAX_REQUEST_BYTES, "SSH request exceeds byte budget")
                response = self._exchange(encoded, deadline)
                require(type(response) is dict and set(response) == {"protocol", "request_hash", "result"}
                        and response["protocol"] == VERSION and response["request_hash"] == request_hash,
                        "SSH response request mismatch")
                result = verify(response["result"])
                call = {k: v for k, v in payload.items() if k != "files"}
                require(result.get("input_hash") == digest(payload)
                        and result.get("source_hash") == digest(payload["files"])
                        and result.get("call_hash") == digest(call)
                        and digest(result.get("executor_identity")) == digest(self.identity)
                        and result.get("status") in {"observed", "unsupported", "execution_error"},
                        "SSH execution receipt binding mismatch")
                if result["status"] == "observed":
                    require(digest(result.get("before_args")) == digest(payload["args"])
                            and digest(result.get("before_kwargs")) == digest(payload["kwargs"])
                            and result.get("cleanup_confirmed") is True, "SSH observed input/cleanup mismatch")
                if result.get("cleanup_confirmed") is not True:
                    self._terminal_reason = "ssh_remote_cleanup_unconfirmed"
                    self._dispose()
                return seal({**{k: v for k, v in result.items() if k != "record_hash"},
                             "ssh_transport": self.transport_identity, "remote_record_hash": result["record_hash"]})
            except _TransportError as error:
                self._terminal_reason = str(error)
            except OSError:
                self._terminal_reason = "ssh_transport_unavailable"
            except (ValueError, TypeError, KeyError, RecursionError):
                self._terminal_reason = "ssh_receipt_mismatch"
            self._dispose()
            return self._unavailable(payload, self._terminal_reason, started)

    def close(self):
        with self._lock:
            self._terminal_reason = self._terminal_reason or "ssh_executor_closed"
            self._dispose()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def serve(executor, reader, writer):
    """Trusted remote entry; injectable streams/executor for offline fixtures."""
    def send(value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        require(len(raw) <= MAX_RESPONSE_BYTES, "Remote response exceeds transport budget")
        writer.write(raw)
        writer.flush()

    send({"protocol": VERSION, "type": "hello", "executor_identity": executor.identity,
          "transport_source_hash": _source_hash(), "cwd": str(Path.cwd())})
    sequence = 0
    while True:
        raw = reader.readline(MAX_REQUEST_BYTES + 1)
        if not raw:
            return
        require(len(raw) <= MAX_REQUEST_BYTES and raw.endswith(b"\n"), "Oversized or truncated SSH request")
        request = _strict_json(raw)
        require(type(request) is dict and set(request) == {"protocol", "sequence", "payload", "request_hash"}
                and request["protocol"] == VERSION and type(request["sequence"]) is int
                and request["sequence"] == sequence + 1, "Invalid SSH request envelope")
        require(request["request_hash"] == digest({k: v for k, v in request.items() if k != "request_hash"}),
                "SSH request hash mismatch")
        require(type(request["payload"]) is dict
                and set(request["payload"]) == {"files", "module", "function", "args", "kwargs"},
                "Only explicit public call data is accepted")
        payload = _request(**request["payload"])
        sequence = request["sequence"]
        result = executor.run(**payload)
        send({"protocol": VERSION, "request_hash": request["request_hash"], "result": result})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--timeout-seconds", type=json.loads, default=10)
    parser.add_argument("--memory-mb", type=int, default=256)
    parser.add_argument("--cpus", type=json.loads, default=1)
    options = parser.parse_args(argv)
    require(_IMAGE.fullmatch(options.image) is not None, "A digest-pinned image is required")
    if hasattr(signal, "SIGHUP"):
        # Let the currently bounded Docker call reach its finally/cleanup after
        # a dropped SSH channel. The client still records cleanup as unknown.
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    executor = DockerExecutor(options.image, options.timeout_seconds, options.memory_mb, options.cpus)
    try:
        serve(executor, sys.stdin.buffer, sys.stdout.buffer)
    except (ValueError, TypeError, KeyError, RecursionError, BrokenPipeError, OSError):
        # Do not print untrusted source, request data or credentials to stderr.
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
