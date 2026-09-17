"""V11 bounded typed/truthiness single-function runner; never executes candidates in host.

This is a compatibility subset, NOT a native MBPP / HumanEval implementation.
OS confinement is inherited without edits from the frozen validator pilot. AST
and import policies add defense in depth, not an independent security sandbox.
"""

from __future__ import annotations

import ast
import hashlib
import json
import keyword
import subprocess
import time
from pathlib import Path
from typing import Any

from skillopt.coevolution_v10.codec import decode_value, encode_value
from skillopt.coevolution_v11.child import AVAILABLE_BUILTINS, IMPORT_MEMBERS
from skillopt.validator_pilot import tasks as _pilot

__all__ = ["AVAILABLE_BUILTINS", "IMPORT_MEMBERS", "encode_value", "decode_value", "validate_code", "run_cases"]

VERSION = "coevolution-v11-typed-truthiness-executor-v1"
_DIRECTORY = Path(__file__).resolve().parent
CHILD_RUNNER = (
    (_DIRECTORY.parent / "coevolution_v10/codec.py").read_text(encoding="utf-8")
    + "\n"
    + (_DIRECTORY / "child.py").read_text(encoding="utf-8")
)
RUNNER_SHA256 = hashlib.sha256(CHILD_RUNNER.encode()).hexdigest()
MAX_CASES = 128
MAX_PAYLOAD_BYTES = 1000000
MAX_OUTPUT_BYTES = 250000
WALL_SECONDS = 12
RSS_BYTES = 384 * 1024 * 1024
FORBIDDEN_ATTRIBUTES = {
    "gi_frame", "gi_code", "ag_frame", "ag_code", "cr_frame", "cr_code", "f_globals",
    "f_locals", "f_builtins", "f_code", "f_back", "tb_frame", "tb_next", "mro",
    "format_map",
}
FORBIDDEN_NAMES = _pilot.FORBIDDEN_NAMES | {"type", "object", "super"}


def _public_name(value: Any) -> bool:
    return (
        isinstance(value, str) and value.isidentifier() and not keyword.iskeyword(value)
        and not value.startswith("_") and len(value) <= 200
    )


def validate_code(code: str) -> ast.Module:
    """Validate syntax plus the declared restricted subset, preserving source.

    Raises SyntaxError for syntax and ValueError for unsupported / unsafe code.
    Imports expose only member proxies, never a module or its private namespace.
    """
    if not isinstance(code, str) or not code.strip() or len(code) > 60000:
        raise ValueError("code must be nonempty and at most 60000 characters")
    tree = ast.parse(code)
    nodes = list(ast.walk(tree))
    if len(nodes) > 12000:
        raise ValueError("code AST exceeds limit")
    for node in nodes:
        if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith, ast.ClassDef)):
            raise ValueError("classes and asynchronous execution are unsupported")
        if isinstance(node, ast.Import):
            if any(alias.name not in IMPORT_MEMBERS for alias in node.names):
                raise ValueError("import is not allowlisted")
        if isinstance(node, ast.ImportFrom):
            if (
                node.level or node.module not in IMPORT_MEMBERS
                or any(alias.name not in IMPORT_MEMBERS[node.module] for alias in node.names)
            ):
                raise ValueError("from-import member is not allowlisted")
        if isinstance(node, ast.alias) and node.asname and (
            node.asname.startswith("__") or node.asname in FORBIDDEN_NAMES
        ):
            raise ValueError("forbidden import alias")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in FORBIDDEN_NAMES):
            raise ValueError("introspection or dynamic execution is forbidden")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRIBUTES
            or isinstance(node.ctx, (ast.Store, ast.Del))
        ):
            raise ValueError("private, frame or writable attributes are forbidden")
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("__") or node.name in FORBIDDEN_NAMES or node.decorator_list:
                raise ValueError("special names and decorators are unsupported")
        if isinstance(node, ast.arg) and (node.arg.startswith("__") or node.arg in FORBIDDEN_NAMES):
            raise ValueError("forbidden function argument")
    return tree


def sandbox_probe() -> dict[str, Any]:
    """Run the existing trusted OS filesystem / network / credential probe."""
    return {"version": VERSION, "runner_sha256": RUNNER_SHA256, **_pilot.sandbox_probe()}


def _payload(code: str, entry_point: str, cases: list[dict]) -> dict:
    if not _public_name(entry_point):
        raise ValueError("entry point must be a public Python function identifier")
    if type(cases) is not list or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("cases must be a nonempty bounded list")
    clean = []
    for case in cases:
        if type(case) is not dict or set(case) != {"args", "kwargs"}:
            raise ValueError("cases may contain only args and kwargs, never expected values")
        if type(case["args"]) is not list or type(case["kwargs"]) is not dict:
            raise ValueError("invalid args or kwargs containers")
        if len(case["args"]) + len(case["kwargs"]) > 256:
            raise ValueError("too many call arguments")
        if any(not _public_name(key) for key in case["kwargs"]):
            raise ValueError("keyword names must be public identifiers")
        # Decode and re-encode bounded exact builtins, rejecting malformed schemas.
        clean.append({
            "args": [encode_value(decode_value(value)) for value in case["args"]],
            "kwargs": {key: encode_value(decode_value(value)) for key, value in case["kwargs"].items()},
        })
    payload = {"code": code, "entry_point": entry_point, "cases": clean}
    if len(json.dumps(payload, allow_nan=False).encode()) > MAX_PAYLOAD_BYTES:
        raise ValueError("candidate payload exceeds bound")
    return payload


def _run_payload(payload: dict) -> tuple[int, str, str]:
    """Inherited 5s CPU, 12s wall, sampled 384MiB RSS; no filesystem writes."""
    import psutil

    process = subprocess.Popen(
        _pilot._command(CHILD_RUNNER),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd="/private/tmp", env={"PATH": "/usr/bin:/bin"}, text=True,
    )
    started = time.monotonic()
    first = json.dumps(payload, allow_nan=False)
    try:
        while True:
            try:
                output, error = process.communicate(input=first, timeout=0.05)
                return process.returncode, output, error
            except subprocess.TimeoutExpired:
                first = None
                if time.monotonic() - started > WALL_SECONDS:
                    raise RuntimeError("candidate exceeded wall limit")
                try:
                    if psutil.Process(process.pid).memory_info().rss > RSS_BYTES:
                        raise RuntimeError("candidate exceeded monitored RSS limit")
                except psutil.NoSuchProcess:
                    pass
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def run_cases(code: str, entry_point: str, cases: list[dict]) -> dict:
    """Return typed observations, never a self-reported pass / expected value.

    Runtime Python exceptions are completed semantic observations. Transport,
    sandbox and resource failures remain unknown, never silently semantic fails.
    Untyped returns retain uniformly observed truthiness. Private predicate
    compatibility is decided only by the host assertion layer, not this runner.
    """
    result = {
        "version": VERSION, "runner_sha256": RUNNER_SHA256,
        "code_hash": hashlib.sha256(code.encode()).hexdigest() if isinstance(code, str) else None,
        "status": "candidate_rejected", "observations": [], "error_category": None,
    }
    try:
        validate_code(code)
        payload = _payload(code, entry_point, cases)
    except (ValueError, TypeError, SyntaxError, RecursionError) as error:
        result["error_category"] = "candidate_or_call_contract_violation"
        result["error"] = f"{type(error).__name__}: {str(error)[:160]}"
        return result
    result["payload_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    try:
        returncode, output, _error = _run_payload(payload)
        if returncode != 0:
            raise RuntimeError(f"sandbox child exit {returncode}")
        if len(output.encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("child output exceeds bound")
        decoded = json.loads(output)
        if type(decoded) is not dict or set(decoded) != {"observations"}:
            raise ValueError("invalid child envelope")
        rows = decoded["observations"]
        if type(rows) is not list or len(rows) != len(cases):
            raise ValueError("child observation cardinality mismatch")
        for row in rows:
            if type(row) is not dict or set(row) != {"value", "exception", "truthiness", "typed"}:
                raise ValueError("invalid child observation")
            if type(row["typed"]) is not bool:
                raise ValueError("invalid typed flag")
            if row["exception"] is not None:
                if (not _public_name(row["exception"]) or row["value"] is not None
                        or row["truthiness"] is not None or row["typed"]):
                    raise ValueError("invalid child exception")
            else:
                if type(row["truthiness"]) is not bool:
                    raise ValueError("invalid truthiness observation")
                if row["typed"]:
                    value = decode_value(row["value"])
                    if bool(value) is not row["truthiness"]:
                        raise ValueError("typed value differs from actual truthiness")
                elif row["value"] is not None:
                    raise ValueError("untyped output cannot carry a typed value")
        # Allocation failure can be raised before the parent RSS watchdog sees
        # it. It is not evidence of a wrong semantic answer, even when the
        # trusted child successfully encodes the exception as an observation.
        # Invalidate the complete task rather than score a partial case prefix.
        if any(row["exception"] == "MemoryError" for row in rows):
            result["status"] = "infrastructure_unknown"
            result["error_category"] = "resource_unknown"
            result["error"] = "candidate child reported MemoryError"
            return result
        result["observations"] = rows
        result["status"] = "completed"
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError, TypeError, RecursionError) as error:
        result["status"] = "infrastructure_unknown"
        result["error_category"] = "sandbox_resource_or_transport_failure"
        result["error"] = f"{type(error).__name__}: {str(error)[:160]}"
    return result
