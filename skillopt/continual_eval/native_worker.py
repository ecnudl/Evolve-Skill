"""Container-only native benchmark worker; never execute on the host.

The host mounts only a detached request and this reviewed worker. Generated
Python and KOR's expression scorer run behind the same OS isolation boundary.
The observer is for non-adversarial generated programs, not a secure judge
against intentional score forgery by code running in the observer process.
"""
from __future__ import annotations

import base64
import contextlib
import importlib.metadata
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

PROTOCOL = "continual-eval-native-v1"
MAX_WORKBOOK = 8 * 1024 * 1024


def load_kor(request):
    root = Path(tempfile.mkdtemp(prefix="kor-scorer-"))
    for package in ("utils", "config"):
        (root / package).mkdir()
        (root / package / "__init__.py").write_text("")
    (root / "utils" / "common.py").write_text(request["common_source"])
    (root / "config" / "config_wrapper.py").write_text(request["config_source"])
    module_path = root / "eval_utils.py"
    module_path.write_text(request["eval_source"])
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("pinned_kor_eval", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def perform(request):
    operation = request["operation"]
    if operation == "probe":
        packages = {"bigcodebench": ["bigcodebench.eval"],
                    "spreadsheetbench": ["openpyxl"],
                    "korbench": ["sympy", "antlr4"]}[request["benchmark"]]
        for name in packages:
            __import__(name)
        if request["benchmark"] == "korbench":
            load_kor(request)
        distribution_names = {"bigcodebench": ["bigcodebench"],
                              "spreadsheetbench": ["openpyxl", "numpy", "pandas"],
                              "korbench": ["sympy", "antlr4-python3-runtime", "PyYAML", "tqdm"]}
        versions = {}
        for name in distribution_names[request["benchmark"]]:
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        return {"status": "ready", "reason": "native_dependencies_imported", "versions": versions}
    if operation == "bigcodebench":
        from bigcodebench.eval import FAIL, PASS, TIMEOUT, untrusted_check

        result, detail = untrusted_check(
            request["code"], request["test"], request["entry_point"],
            max_as_limit=request["memory_mb"], max_data_limit=request["memory_mb"],
            max_stack_limit=10, min_time_limit=request["test_timeout"],
            gt_time_limit=request["test_timeout"],
        )
        status = "pass" if result == PASS else "fail" if result == FAIL else "unknown"
        if any("ModuleNotFoundError" in str(trace) for trace in dict(detail).values()):
            return {"status": "unknown", "score": None, "reason": "native_dependency_unavailable",
                    "metrics": {"native_result": result, "details": dict(detail)}}
        return {"status": status, "score": 1.0 if status == "pass" else 0.0 if status == "fail" else None,
                "reason": "native_timeout" if result == TIMEOUT else "official_bigcodebench_untrusted_check",
                "metrics": {"native_result": result, "details": dict(detail)}}
    if operation == "korbench":
        # Official puzzle scorers evaluate model expressions. Never import this
        # module in the host process, even when the package itself is trusted.
        module = load_kor(request)
        ok = bool(module.evaluate_response_vs_answer(
            request["response"], request["answer"], request["category"],
            request["rule_id"], request["upstream_index"],
        ))
        return {"status": "pass" if ok else "fail", "score": float(ok),
                "reason": "official_kor_evaluate_response_vs_answer", "metrics": {"accuracy": float(ok)}}
    if operation == "spreadsheet_generate":
        with tempfile.TemporaryDirectory(prefix="sheet-task-") as directory:
            os.chdir(directory)
            Path("input.xlsx").write_bytes(base64.b64decode(request["input_base64"], validate=True))
            # A new container per input case, the same generated program, no
            # reference workbook or hidden answer position in this request.
            exec(compile(request["code"], "generated.py", "exec"), {"__name__": "__main__"})
            path = Path("output.xlsx")
            if path.is_symlink() or not path.is_file():
                return {"status": "missing_output", "reason": "output.xlsx_not_produced"}
            if path.stat().st_size > MAX_WORKBOOK:
                return {"status": "unknown", "reason": "output_workbook_size_limit"}
            return {"status": "available", "output_base64": base64.b64encode(path.read_bytes()).decode(),
                    "reason": "isolated_workbook_generated"}
    raise ValueError("Unsupported native operation")


def main():
    # A host caller cannot accidentally run untrusted input through this file.
    if os.environ.get("CONTINUAL_EVAL_CONTAINER") != PROTOCOL or not Path("/.dockerenv").exists():
        raise SystemExit("Container-only worker; use the hardened backend")
    request = json.loads(Path("/input/request.json").read_text())
    # Model code output never becomes an outer protocol frame. /dev/null also
    # avoids retaining arbitrary output in memory inside the container.
    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = perform(request)
    except BaseException as exc:
        result = {"status": "unknown", "reason": "native_exception:" + type(exc).__name__}
    print(json.dumps({"protocol": PROTOCOL, "result": result}, allow_nan=False))


if __name__ == "__main__":
    main()
