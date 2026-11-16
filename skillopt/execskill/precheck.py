"""SpreadsheetBench public-input pre-check (protocol ``fivebench-execskill-v1``; registration §2.5; implementation plan
§1 precheck.py row, §3 sheet rows; T-SOLVER-5).

After the first reply the shell runs the extracted program ONCE on the item's public input workbook, in a one-shot
container whose ``docker run`` argv and environment are the frozen ``backends._native``'s byte for byte but the name
(continual_eval/backends.py:169-178: pids 128, nofile 256, tmpfs 256m, OMP/OPENBLAS = 1, ``python -I -B
/input/worker.py``). ``run`` is a copy of ``_native`` (backends.py:153-214) with four changes: the mounted worker is
``precheck_worker.py`` (a copy of the frozen ``native_worker.py`` whose one operation returns the last traceback line
instead of the output workbook); the request is ``spreadsheet_precheck`` with the public answer position; the
container is named as a sandbox container (``container_name``: ``execskill-sbx-<chain>-<unit12>-<uuid4 hex>`` with the
unit tag of the cell's worker, else ``execskill-sbx-<uuid4 hex>``; the frozen ``continual-eval-<uuid>`` prefix is
shared with frozen pipelines on the machine), so the S2 leftovers row and the unit's drain list it (ticket C5-2); and
its removal is the sandbox's bounded ``cleanup`` (``rm --force`` and an exact-name check, 3 tries of 10 s each, 1 s
apart; registrar decision 2026-10-22), its latency recorded in ``execution_costs.cleanup_seconds``, instead of one
``rm``. The image check, the limits, the bounded command and the envelope check are the frozen helpers, imported
unchanged and called through ``backends`` (so a test that replaces ``backends._bounded_command`` sees both the frozen
case runs and the pre-check).

The report ({version, evidence, status, exc_type, message, answer_cells, reason, ...}) is stored in the prediction's
shell; a replay reads it back instead of running the program again (§2.5). The caller holds the ``spreadsheet-native``
slot around the call and never across a model call (§2.5). A container whose removal is not confirmed is a stop
(``CleanupUnconfirmed``, raised by ``sandbox.cleanup``): the report carries no reason the frozen decision table would
see.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import require

from .protocol import EVIDENCE, MAX_RUN_MESSAGE_CHARS, kind
from .sandbox import client as sandbox

WORKER = Path(__file__).with_name("precheck_worker.py")
OPERATION = "spreadsheet_precheck"
STATUSES = ("ok", "exception", "missing_output", "unknown")
MAX_REQUEST_BYTES = 32 * 1024 * 1024  # backends.py:160
OUTPUT_LIMIT = 16 * 1024 * 1024  # backends.py:182


def native_command(docker, name, root, image, memory, cpus):
    """The frozen ``_native`` container argv (backends.py:169-178), unchanged."""
    return [docker, "run", "--pull=never", "--name", name, "--network=none", "--read-only",
            "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges=true",
            "--pids-limit=128", f"--memory={memory}m", f"--memory-swap={memory}m", f"--cpus={cpus}",
            "--ipc=private", "--shm-size=64m", "--no-healthcheck", "--log-driver=none",
            "--ulimit=nofile=256:256", "--ulimit=core=0:0", "--env", f"CONTINUAL_EVAL_CONTAINER={backends.PROTOCOL}",
            "--env", "MPLCONFIGDIR=/tmp/matplotlib", "--env", "OMP_NUM_THREADS=1",
            "--env", "OPENBLAS_NUM_THREADS=1",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777", "--workdir=/tmp",
            "--mount", f"type=bind,source={root},target=/input,readonly",
            "--entrypoint=python", image, "-I", "-B", "/input/worker.py"]


def container_name(tag=None):
    """A pre-check container's name (ticket C5-2): the sandbox's ``execskill-sbx-<tag>-<uuid4 hex>`` for the unit tag
    ``tag`` (``sandbox.unit_tag(chain, unit)``), else ``execskill-sbx-<uuid4 hex>``."""
    require(tag is None or (type(tag) is str and sandbox.TAG.fullmatch(tag) is not None), "A unit tag or None")
    return sandbox.PREFIX + ("%s-" % tag if tag else "") + uuid.uuid4().hex


def report(status, *, evidence, exc_type=None, message="", answer_cells=None, reason=None, **extra):
    """A pre-check run report (``fivebench-execskill-v1-precheck``)."""
    require(status in STATUSES and (evidence in EVIDENCE or evidence in ('main_v9_real_run', 'main_v10_real_run')),
            "A known pre-check status and evidence label")
    return {"version": kind("precheck"), "evidence": evidence, "status": status, "exc_type": exc_type,
            "message": message, "answer_cells": answer_cells, "reason": reason or status, **extra}


def run(request, runtime, *, evidence, tag=None, docker=None):
    """Copy of ``backends._native`` (backends.py:153-214) with the pre-check worker mounted: the worker's report, or
    the frozen unknown shapes. ``tag``: the unit tag of the container's name (``container_name``); ``docker``: the
    sandbox's docker CLI for the removal (``sandbox.Docker``; a fake in tests). CleanupUnconfirmed when the container's
    removal is not confirmed after the sandbox's bounded tries."""
    ready = backends._image_ready(runtime)
    if ready["status"] != "ready":
        return report("unknown", evidence=evidence, reason=ready["reason"],
                      execution_costs={"container_calls": 0, "wall_seconds": 0.0})
    timeout, memory, cpus = backends._runtime_limits(runtime)
    docker_cli, name = shutil.which("docker"), container_name(tag)
    payload = json.dumps(request, allow_nan=False).encode()
    if len(payload) > MAX_REQUEST_BYTES:
        return report("unknown", evidence=evidence, reason="native_request_size_limit")
    with tempfile.TemporaryDirectory(prefix="continual-eval-native-") as directory:
        root = Path(directory)
        root.chmod(0o755)
        (root / "request.json").write_bytes(payload)
        (root / "request.json").chmod(0o444)
        (root / "worker.py").write_bytes(WORKER.read_bytes())
        (root / "worker.py").chmod(0o444)
        command = native_command(docker_cli, name, root, runtime["image"], memory, cpus)
        started = time.monotonic()
        result = None
        execution_exception = None
        try:
            result = backends._bounded_command(command, timeout, limit=OUTPUT_LIMIT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            execution_exception = type(exc).__name__
        finally:
            removing = time.monotonic()
            sandbox.cleanup(name, docker=docker)  # CleanupUnconfirmed after the last try
        execution_costs = {"container_calls": 1, "wall_seconds": round(time.monotonic() - started, 6),
                           "includes_cleanup": True, "cleanup_seconds": round(time.monotonic() - removing, 3),
                           "image_id": ready["image_id"]}
    if execution_exception is not None:
        return report("unknown", evidence=evidence, execution_costs=execution_costs,
                      reason="native_timeout" if execution_exception == "TimeoutExpired"
                      else "native_execution_unavailable")
    if result.timed_out or result.overflow or result.code != 0 or result.unavailable:
        return report("unknown", evidence=evidence, execution_costs=execution_costs,
                      reason="native_timeout" if result.timed_out else "native_execution_unavailable")
    try:
        envelope = backends._strict_json(result.stdout)
        if envelope["protocol"] != backends.PROTOCOL or not isinstance(envelope["result"], dict):
            raise ValueError("Invalid native envelope")
        found = envelope["result"]
        if found.get("status") not in STATUSES:
            return report("unknown", evidence=evidence, execution_costs=execution_costs,
                          reason=str(found.get("reason", "invalid_precheck_result"))[:200])
        message, cells = found.get("message"), found.get("answer_cells")
        return report(found["status"], evidence=evidence, exc_type=found.get("exc_type"),
                      message=message[:MAX_RUN_MESSAGE_CHARS] if isinstance(message, str) else "",
                      answer_cells=cells if isinstance(cells, dict) else None,
                      runtime_image_id=ready["image_id"], cleanup_confirmed=True, execution_costs=execution_costs)
    except (ValueError, KeyError, TypeError, RecursionError):
        return report("unknown", evidence=evidence, reason="invalid_native_receipt", execution_costs=execution_costs)


def precheck(program, workbook, answer_position, runtime, *, evidence, tag=None, docker=None):
    """The run report of ``program`` executed once on the public input ``workbook`` (a path; at most 8 MiB, read with
    the frozen ``_xlsx_bytes``) with the public ``answer_position``; ``tag`` and ``docker`` as for ``run``."""
    return run({"operation": OPERATION, "code": program, "answer_position": answer_position,
                "input_base64": base64.b64encode(backends._xlsx_bytes(workbook)).decode()}, runtime, evidence=evidence,
               tag=tag, docker=docker)
