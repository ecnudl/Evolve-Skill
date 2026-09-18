"""Small container-only observer for non-adversarial Python/JSON callables.

The parent Docker boundary protects the host. This observer shares a Python
process with the candidate: it is NOT an authenticated measurement device for
actively hostile code. In particular, code could monkeypatch Python objects or
inspect file descriptors. Such outputs require a stronger execution service
before they can receive adversarial-evaluation authority.

No task answer, reference implementation or private test is accepted here.
"""
from __future__ import annotations

import importlib
import json
import os
import sys

PROTOCOL = "skill-validation-python-observer-v1"
MAX_BYTES = 65536


def observe(payload: dict) -> dict:
    """Container-only call; tests may use explicitly trusted fixture modules."""
    # Capture immutable snapshots before importing any candidate module.
    dumps = json.dumps
    loads = json.loads
    def snapshot(value):
        return loads(dumps(value, allow_nan=False))
    args, kwargs = payload["args"], payload["kwargs"]
    before_args, before_kwargs = snapshot(args), snapshot(kwargs)
    actual, exception = None, None
    try:
        module = importlib.import_module(payload["module"])
        expected = "/input/source/" + payload["module"].replace(".", "/")
        if getattr(module, "__file__", None) not in {expected + ".py", expected + "/__init__.py"}:
            # A cached standard-library module with the same name is not the
            # provided artifact, even if it happens to expose this function.
            return {"protocol": PROTOCOL, "status": "execution_error", "reason": "module_origin_mismatch"}
        target = getattr(module, payload["function"])
        actual = target(*args, **kwargs)
    except BaseException as exc:
        # Do not trust exception.__str__ or expose potentially large diagnostics.
        exception = type(exc).__name__[:200]
    try:
        result = {
            "protocol": PROTOCOL, "status": "observed", "actual": snapshot(actual),
            "before_args": before_args, "after_args": snapshot(args),
            "before_kwargs": before_kwargs, "after_kwargs": snapshot(kwargs),
            "exception": exception,
        }
        if len(dumps(result, allow_nan=False).encode("utf-8")) > MAX_BYTES:
            raise ValueError("Observation exceeds output budget")
        return result
    except (TypeError, ValueError, OverflowError, RecursionError):
        return {"protocol": PROTOCOL, "status": "execution_error", "reason": "non_json_or_oversized_observation"}


def main() -> None:
    # This file is copied, not imported from the host repository in a container.
    if len(sys.argv) != 2 or not os.path.isfile("/.dockerenv"):
        raise SystemExit("Container-only worker: no host execution fallback")
    with open(sys.argv[1], encoding="utf-8") as stream:
        payload = json.load(stream)
    sys.path.insert(0, "/input/source")
    # Ordinary print/log output cannot impersonate the transport envelope. A
    # malicious candidate can still inspect receipt_fd: see the trust boundary.
    receipt_fd = os.dup(1)
    saved_write, saved_dumps = os.write, json.dumps
    null_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null_fd, 1)
    os.dup2(null_fd, 2)
    os.close(null_fd)
    result = observe(payload)
    encoded = (saved_dumps(result, allow_nan=False, ensure_ascii=False) + "\n").encode("utf-8")
    while encoded:
        written = saved_write(receipt_fd, encoded)
        encoded = encoded[written:]
    os.close(receipt_fd)


if __name__ == "__main__":
    main()
