"""Fail-closed, bounded Linux Docker execution for public callable checks.

This is a narrow Python/JSON runner, NOT a SWE-bench repository harness. Only
explicit source files and a public call specification are mounted, read-only.
Docker and a preinstalled digest-pinned Linux image are required. We never
pull images automatically or execute candidate code on the host.

SHA seals establish receipt integrity, not authenticity against hostile code:
the in-container state observer and candidate share a process. The declared
measurement scope is non-adversarial model-produced Python callables.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from .models import file_path, require

VERSION = "skill-validation-docker-callable-v1"
PROTOCOL = "skill-validation-python-observer-v1"
MAX_OUTPUT_BYTES = 65536
MAX_INPUT_BYTES = 262144
MAX_SOURCE_BYTES = 1048576
_IMAGE = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9._:/-]*@)?sha256:[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(frozen=True)
class _Command:
    code: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    overflow: bool = False
    unavailable: bool = False


def _bounded_command(argv: list[str], timeout: float, limit: int = MAX_OUTPUT_BYTES) -> _Command:
    """Drain both pipes with a shared deadline, never unbounded communicate()."""
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, shell=False, start_new_session=True)
    except OSError:
        return _Command(None, unavailable=True)
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    timed_out = overflow = False
    try:
        with selectors.DefaultSelector() as selector:
            for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffer = streams[key.data]
                    available = limit - len(buffer)
                    buffer.extend(chunk[:available])
                    if len(chunk) > available:
                        overflow = True
                        break
                if overflow:
                    break
            if not timed_out and not overflow:
                try:
                    proc.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    timed_out = True
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=2)
        proc.stdout.close()
        proc.stderr.close()
    return _Command(proc.returncode, bytes(streams["stdout"]), bytes(streams["stderr"]), timed_out, overflow)


def _json_value(value: Any, depth: int = 0) -> None:
    require(depth <= 32, "JSON nesting exceeds execution input budget")
    if type(value) in (str, int, bool, type(None)):
        return
    if type(value) is float:
        require(value == value and abs(value) != float("inf"), "Nonfinite JSON is unsupported")
        return
    if type(value) is list:
        require(len(value) <= 10000, "JSON list exceeds execution input budget")
        for item in value:
            _json_value(item, depth + 1)
        return
    if type(value) is dict:
        require(len(value) <= 10000 and all(type(key) is str for key in value), "JSON requires bounded string keys")
        for item in value.values():
            _json_value(item, depth + 1)
        return
    raise ValueError("Execution accepts only plain JSON values")


def _strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key in execution receipt")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("Nonfinite JSON in execution receipt")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    _json_value(value)
    return value


class DockerExecutor:
    """One isolated public callable execution per run; no hidden oracle input."""

    def __init__(self, image: str, timeout_seconds: float = 10, memory_mb: int = 256, cpus: float = 1):
        require(type(image) is str and len(image) <= 512, "Expected a bounded image reference")
        require(type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 120, "Timeout must be in (0, 120]")
        require(type(memory_mb) is int and 64 <= memory_mb <= 4096, "Memory must be 64 to 4096 MiB")
        require(type(cpus) in (int, float) and 0 < cpus <= 8, "CPUs must be in (0, 8]")
        self.image, self.timeout_seconds, self.memory_mb, self.cpus = image, timeout_seconds, memory_mb, cpus

    @property
    def identity(self) -> dict:
        """Stable policy/source binding available before any container executes."""
        return {
            "version": VERSION, "image": self.image, "timeout_seconds": self.timeout_seconds,
            "memory_mb": self.memory_mb, "cpus": self.cpus,
            "worker_hash": hashlib.sha256(Path(__file__).with_name("sandbox_worker.py").read_bytes()).hexdigest(),
            "executor_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "measurement_trust": "bounded_non_adversarial_process",
            "formal_adversarial_authorization": False,
        }

    def run(self, files: dict[str, str], module: str, function: str, args: list, kwargs: dict) -> dict:
        require(type(files) is dict and 0 < len(files) <= 100, "Expected 1 to 100 public source files")
        for path, content in files.items():
            file_path(path)
            require(type(content) is str, "Source file content must be text")
            require(not any(part.startswith(".env") or part == ".git" for part in Path(path).parts),
                    "Credential files and Git history cannot enter the callable sandbox")
            require(not any(str(parent) in files for parent in Path(path).parents if str(parent) != "."),
                    "A source file cannot also be a directory")
        require(sum(len(text.encode("utf-8")) for text in files.values()) <= MAX_SOURCE_BYTES,
                "Source exceeds execution byte budget")
        require(type(module) is str and len(module) <= 256 and all(_IDENTIFIER.fullmatch(p) for p in module.split(".")),
                "Module must be an import identifier, not a path or expression")
        require(type(function) is str and _IDENTIFIER.fullmatch(function) is not None, "Function must be an identifier")
        module_path = module.replace(".", "/")
        require(module_path + ".py" in files or module_path + "/__init__.py" in files,
                "Callable module must come from the explicit public source files")
        require(type(args) is list and type(kwargs) is dict, "Expected JSON args list and kwargs object")
        payload = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        _json_value(payload)
        payload_bytes = json.dumps(payload, allow_nan=False, ensure_ascii=False).encode("utf-8")
        require(len(payload_bytes) <= MAX_INPUT_BYTES, "Call exceeds execution input byte budget")
        # Materialize detached input bytes; later caller mutations cannot change the receipt.
        payload = json.loads(payload_bytes)
        files = dict(files)
        worker = Path(__file__).with_name("sandbox_worker.py").read_bytes()
        isolation = {
            "image": self.image, "network": "none", "root_read_only": True,
            "source_read_only": True, "user": "65534:65534", "cap_drop": ["ALL"],
            "no_new_privileges": True, "pids_limit": 64, "memory_mb": self.memory_mb,
            "memory_swap_mb": self.memory_mb, "cpus": self.cpus,
            "timeout_seconds": self.timeout_seconds, "tmpfs_mb": 16,
            "seccomp": "docker-daemon-default", "automatic_pull": False,
            "measurement_scope": "non_adversarial_python_json_callable",
            "adversarial_measurement_authenticated": False,
        }
        base = {
            "version": VERSION, "status": "unsupported", "actual": None,
            "before_args": None, "after_args": None, "before_kwargs": None, "after_kwargs": None,
            "exception": None, "reason": "", "isolation": isolation,
            "isolation_hash": digest(isolation), "input_hash": digest({"files": files, **payload}),
            "source_hash": digest(files), "call_hash": digest(payload),
            "worker_hash": hashlib.sha256(worker).hexdigest(),
            "executor_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "executor_identity": self.identity,
            "measurement_trust": "bounded_non_adversarial_process",
            "image_id": None, "container_name": None, "cleanup_confirmed": True,
            "duration_seconds": 0.0, "diagnostic": "",
        }

        def finish(status: str, reason: str, **extra) -> dict:
            return seal({**base, "status": status, "reason": reason, **extra})

        if platform.system() != "Linux":
            return finish("unsupported", "linux_docker_required")
        if not _IMAGE.fullmatch(self.image):
            return finish("unsupported", "digest_pinned_image_required")
        docker = shutil.which("docker")
        if docker is None:
            return finish("unsupported", "docker_unavailable")
        inspect_format = ('{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},'
                          '"Os":{{json .Os}},"Volumes":{{json .Config.Volumes}}}')
        inspected = _bounded_command([docker, "image", "inspect", "--format", inspect_format, self.image], 5)
        if inspected.code != 0 or inspected.unavailable or inspected.timed_out or inspected.overflow:
            return finish("unsupported", "pinned_image_or_daemon_unavailable")
        try:
            info = _strict_json(inspected.stdout)
            valid = (info["Os"] == "linux" and not info.get("Volumes")
                     and (self.image == info["Id"] or self.image in (info.get("RepoDigests") or [])))
            require(valid, "Unexpected image identity, OS or automatic volume")
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", info["Id"]) is not None, "Invalid image ID")
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            return finish("unsupported", "image_inspection_mismatch")
        base["image_id"] = info["Id"]
        name = "skillval-" + uuid.uuid4().hex
        base["container_name"] = name
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="skill-validation-call-") as directory:
            root = Path(directory)
            root.chmod(0o755)
            source = root / "source"
            source.mkdir(mode=0o755)
            for path, content in files.items():
                destination = source / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                for parent in destination.parents:
                    if parent == root:
                        break
                    parent.chmod(0o755)
                destination.write_text(content, encoding="utf-8")
                destination.chmod(0o444)
            (root / "request.json").write_bytes(payload_bytes)
            (root / "request.json").chmod(0o444)
            (root / "worker.py").write_bytes(worker)
            (root / "worker.py").chmod(0o444)
            command = [
                docker, "run", "--pull=never", "--name", name, "--network=none", "--read-only",
                "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges=true",
                "--pids-limit=64", f"--memory={self.memory_mb}m", f"--memory-swap={self.memory_mb}m",
                f"--cpus={self.cpus}", "--ipc=none", "--no-healthcheck", "--log-driver=none",
                "--ulimit=nofile=64:64", "--ulimit=core=0:0",
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
                "--mount", f"type=bind,source={root},target=/input,readonly",
                "--workdir=/input/source", "--entrypoint=/usr/local/bin/python", self.image,
                "-I", "-B", "/input/worker.py", "/input/request.json",
            ]
            try:
                ran = _bounded_command(command, self.timeout_seconds)
            finally:
                # Kill/remove only the exact randomly named container, even when
                # the client died. No wildcard cleanup, no host path deletion.
                cleaned = _bounded_command([docker, "rm", "--force", name], 5)
                base["cleanup_confirmed"] = (
                    not cleaned.timed_out and not cleaned.unavailable and not cleaned.overflow
                    and (cleaned.code == 0 or b"no such container" in cleaned.stderr.lower())
                )
        base["duration_seconds"] = round(time.monotonic() - started, 6)
        base["diagnostic"] = ran.stderr[:2048].decode("utf-8", errors="replace")
        if not base["cleanup_confirmed"]:
            return finish("execution_error", "container_cleanup_unconfirmed")
        if ran.timed_out:
            return finish("execution_error", "execution_timeout")
        if ran.overflow:
            return finish("execution_error", "execution_output_limit")
        if ran.unavailable or ran.code != 0:
            return finish("execution_error", "container_execution_failed")
        try:
            result = _strict_json(ran.stdout)
            require(type(result) is dict and result.get("protocol") == PROTOCOL, "Invalid observer protocol")
            if result.get("status") == "execution_error":
                require(set(result) == {"protocol", "status", "reason"}, "Invalid worker error envelope")
                require(result["reason"] in {"non_json_or_oversized_observation", "module_origin_mismatch"},
                        "Invalid worker failure reason")
                return finish("execution_error", result["reason"])
            require(set(result) == {"protocol", "status", "actual", "before_args", "after_args", "before_kwargs",
                                    "after_kwargs", "exception"} and result["status"] == "observed", "Invalid observation")
            require(type(result["before_args"]) is list and type(result["after_args"]) is list
                    and type(result["before_kwargs"]) is dict and type(result["after_kwargs"]) is dict,
                    "Invalid observed state types")
            require(digest(result["before_args"]) == digest(payload["args"])
                    and digest(result["before_kwargs"]) == digest(payload["kwargs"]), "Before-state receipt mismatch")
            require(result["exception"] is None or (type(result["exception"]) is str
                    and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,199}", result["exception"])), "Invalid exception name")
        except (ValueError, TypeError, KeyError, RecursionError):
            return finish("execution_error", "invalid_observation_receipt")
        return finish("observed", "public_callable_executed", **{
            key: result[key] for key in ("actual", "before_args", "after_args", "before_kwargs", "after_kwargs", "exception")
        })
