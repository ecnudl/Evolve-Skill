"""Container-only, additive exception diagnostics around the frozen worker.

No task code runs on the host. This is an observer of non-adversarial programs,
not an adversarially secure judge: model code shares the observer's interpreter.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

PROTOCOL = "native-unknown-diagnostic-v1"


def exception_evidence(exc):
    """Never retain exception messages, source snippets, frame locals or paths."""
    frames = []
    generated_lines = []
    tb = exc.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        generated = frame.f_code.co_filename == "generated.py"
        if generated:
            generated_lines.append(tb.tb_lineno)
        name = frame.f_code.co_name
        frames.append({"origin": "generated" if generated else "dependency_or_wrapper",
                       "line": tb.tb_lineno,
                       "function": name if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}|<module>", name)
                       else "redacted"})
        tb = tb.tb_next
    syntax = isinstance(exc, SyntaxError) and exc.filename == "generated.py"
    if syntax and type(exc.lineno) is int:
        generated_lines.append(exc.lineno)
    kind = type(exc).__name__
    return {"exception_type": kind if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", kind) else "redacted",
            "phase": "generated_compile" if syntax else "generated_execution" if generated_lines
            else "wrapper_or_input",
            "generated_lines": generated_lines[:16], "frames": frames[-12:],
            "frames_omitted": max(0, len(frames) - 12), "messages_and_locals_retained": False}


def perform(request, worker):
    if set(request) != {"operation", "code", "input_base64"} or request["operation"] != "spreadsheet_generate":
        raise ValueError("Only public-input spreadsheet generation is supported")
    try:
        return worker.perform(request)
    except BaseException as exc:
        evidence = exception_evidence(exc)
        return {"status": "unknown", "reason": "native_exception:" + evidence["exception_type"],
                "diagnostic": evidence}


def main():
    if os.environ.get("NATIVE_UNKNOWN_CONTAINER") != PROTOCOL or not Path("/.dockerenv").is_file():
        raise SystemExit("Container-only worker; no host execution")
    source = Path("/input/original_worker.py")
    expected = os.environ.get("ORIGINAL_WORKER_SHA256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise SystemExit("Frozen worker identity mismatch")
    spec = importlib.util.spec_from_file_location("frozen_native_worker", source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    request = json.loads(Path("/input/request.json").read_text())
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        result = perform(request, worker)
    print(json.dumps({"protocol": PROTOCOL, "result": result}, allow_nan=False))


if __name__ == "__main__":
    main()
