"""Zero-API, once-only replay of frozen BCB/Sheet native unknowns.

Run using the ORIGINAL frozen source on PYTHONPATH and its original interpreter.
BCB retains the original scorer, SDK guard, image and limits. Sheet re-executes
unchanged code/public input, adding bounded exception evidence, not a repair or
a semantic score. No reference workbook is mounted. Old scores are immutable.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import (
    load_checkpoint,
    output_lock,
    read_json,
    require,
    runtime_identity,
    safe_path,
    source_identity,
    write_json,
)
from skillopt.continual_eval.datasets import load_panel, panel_hash
from skillopt.continual_eval.runner import _costs, _stored_calls, _valid_score
from skillopt.skill_validation.sandbox import _bounded_command, _strict_json
from skillopt.validator_pilot.api import digest

VERSION = "native-unknown-replay-v1"
WORKER_PROTOCOL = "native-unknown-diagnostic-v1"
WORKER = Path(__file__).with_name("native_unknown_worker.py")


def sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


@contextmanager
def parent_lock(root):
    with safe_path(root / ".writer.lock").open("rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Original run still has an active writer") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _snapshot(parent, source):
    plan = read_json(parent / "plan.json", sealed=True)
    benchmarks = {t["benchmark"] for t in plan["tasks"]}
    require(len(benchmarks) == 1 and benchmarks <= {"bigcodebench", "spreadsheetbench"}, "Single supported benchmark required")
    benchmark = next(iter(benchmarks))
    fixture = plan["config"]["model"]["provider"] == "fixture"
    require(plan["version"] == "continual-eval-v2" and plan["config"]["partition"] == "development"
            and plan["config"]["methods"] == ["no_skill"] and plan["config"]["histories"] == ["h0"]
            and plan["repeats"] == 2, "Frozen development No-Skill repeat-two protocol required")
    require(fixture or len(plan["tasks"]) == {"bigcodebench": 400, "spreadsheetbench": 80}[benchmark], "Full natural panel required")
    model = plan["config"]["model"]
    require(fixture or (model["provider"] == "bigmodel" and model["name"] == "glm-5.3"
            and model["max_tokens"] == 65536 and model["reasoning_effort"] == "low"
            and model["transport"] == {"stream": True, "read_timeout_seconds": 300,
                "stream_wall_seconds": 1800, "initial_health_policy": "completed_response_v1"}),
            "Unexpected frozen natural model profile")
    require(plan["source_identity"] == source_identity() and plan["host_runtime"] == runtime_identity(),
            "Use original frozen source and interpreter")
    for name, expected in plan["source_identity"].items():
        path = safe_path(source / "skillopt" / name)
        require(path.is_relative_to(source / "skillopt") and sha(path) == expected, "Frozen source changed")
    panel = load_panel(plan["panels"][benchmark]["path"])
    require(panel_hash(panel) == plan["panels"][benchmark]["panel_hash"], "Panel changed")
    tasks = {digest(t): t for t in panel["tasks"]}
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    require(cp["skill_text"] == "", "Frozen checkpoint must be empty")
    service = read_json(parent / "model_service.json", sealed=True)
    service.pop("record_hash")
    selected, positions, calls, cache_names = [], set(), [], set()
    excluded = Counter()
    for task in plan["tasks"]:
        require(task["partition"] == "development", "Final data forbidden")
        for repeat in range(2):
            request = {"plan_hash": plan["record_hash"], "checkpoint_hash": cp["record_hash"],
                       "benchmark": benchmark, "task_hash": task["task_hash"], "repeat": repeat}
            key = digest(request)
            positions.add(key)
            base = parent / "predictions" / key
            receipts = _stored_calls(base)
            require(len(receipts) == len(list((base / "call_intents").glob("*.json"))) == 1, "Unclosed or extra call")
            record = read_json(next((base / "calls").glob("*.json")), sealed=True)
            receipt = receipts[0]
            require(record["request"]["position"] == request and receipt["request"]["service"] == service
                    and receipt["request"]["model"] == model["name"]
                    and record["request"]["max_tokens"] == receipt["request"]["max_tokens"] == model["max_tokens"],
                    "Call identity differs")
            require(type(receipt.get("ok")) is bool and type(receipt.get("http_attempt_count")) is int
                    and receipt["http_attempt_count"] >= 1 and
                    (not receipt["ok"] or receipt.get("returned_model") == model["name"]), "Invalid closed model receipt")
            cache = parent / "api/calls" / (receipt["request_hash"] + ".json")
            require(read_json(cache) == receipt, "Receipt cache changed")
            cache_names.add(cache.name)
            prediction = read_json(base / "prediction.json", sealed=True)
            require(prediction["request"] == request and prediction["costs"] == _costs(receipts)
                    and read_json(base / "intent.json", sealed=True) == seal(request), "Prediction identity differs")
            score = read_json(parent / "host_only/scores" / (key + ".json"), sealed=True)
            require(score["prediction_hash"] == prediction["record_hash"] and score["plan_hash"] == plan["record_hash"]
                    and score["checkpoint_hash"] == cp["record_hash"] and score["task_id"] == task["task_id"]
                    and score["repeat"] == repeat and score["costs"] == _costs(receipts)
                    and read_json(parent / "host_only/score_intents" / (key + ".json"), sealed=True)
                    == seal({"request": request, "prediction_hash": prediction["record_hash"]}), "Score binding differs")
            calls.extend(receipts)
            value = prediction["prediction"]
            if score["status"] != "unknown" or value["status"] != "available":
                excluded[score["status"] + ":" + ("unavailable" if value["status"] != "available" else "available")] += 1
                continue
            code = value["output"] if benchmark == "bigcodebench" else value["output"]["code"]
            require(type(code) is str and len(code.encode()) <= backends.MAX_RESPONSE, "Invalid frozen code")
            require(receipt["ok"] and receipt.get("finish_reason") == "stop"
                    and type(receipt.get("response")) is str and code == backends._code(receipt["response"]),
                    "Frozen generated code differs from the closed model deliverable")
            common = {"position": key, "task_hash": task["task_hash"], "repeat": repeat,
                      "prediction_hash": prediction["record_hash"], "score_hash": score["record_hash"],
                      "code_sha256": hashlib.sha256(code.encode()).hexdigest()}
            if benchmark == "bigcodebench":
                selected.append({**common, "case": None, "original_reason": score["reason"]})
                continue
            inputs = tasks[task["task_hash"]]["public"]["input_files"]
            cases = value["output"]["cases"]
            require(len(inputs) == len(cases), "Input/case count differs")
            eligible = 0
            for index, case in enumerate(cases):
                reason = case.get("reason", "")
                if case["status"] not in {"unknown", "missing_output"} or not (
                        reason.startswith("native_exception:") or reason == "output.xlsx_not_produced"):
                    continue
                eligible += 1
                selected.append({**common, "case": index, "input_sha256": sha(inputs[index]), "original_reason": reason})
            if not eligible:
                excluded["unknown:non_generation"] += 1
    require({p.name for p in (parent / "api/calls").glob("*.json")} == cache_names
            and {p.stem for p in (parent / "host_only/scores").glob("*.json")} == positions
            and {p.name for p in (parent / "predictions").iterdir() if p.is_dir()} == positions,
            "Unexpected or missing positions")
    reports = [read_json(p, sealed=True) for p in (parent / "host_only/reports").glob("*.json")]
    reports = [r for r in reports if r["plan_hash"] == plan["record_hash"]
               and r["run_accounting"]["scored_positions"] == len(positions)]
    require(len(reports) == 1 and all(reports[0]["run_accounting"][k] == v for k, v in _costs(calls).items()),
            "Unique completed report with matching cost required")
    return {"benchmark": benchmark, "fixture": fixture, "plan_hash": plan["record_hash"],
            "report_hash": reports[0]["record_hash"], "selected": selected,
            "original_positions": len(positions), "excluded": dict(excluded),
            "files": {str(p.relative_to(parent)): sha(p) for p in parent.rglob("*.json")}}


def prepare(parent, source, output, native_lock):
    parent, source, root, lock = map(safe_path, (parent, source, output, native_lock))
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
                                        for p in (parent, source)), "New independent output required")
    require(lock.is_file() and not any(lock.is_relative_to(p) for p in (parent, source, root)), "Existing external shared native lock required")
    with parent_lock(parent):
        snapshot = _snapshot(parent, source)
        protocol = seal({"version": VERSION, "parent": str(parent), "source": str(source), "output": str(root),
            "native_lock": str(lock), "script_sha256": sha(__file__), "wrapper_sha256": sha(WORKER),
            "snapshot": snapshot, "new_model_calls": 0, "diagnostic_only": True, "deployment_authorized": False})
        root.mkdir(mode=0o700)
        write_json(root / "protocol.json", protocol)
        return protocol


def check(output):
    root = safe_path(output)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["version"] == VERSION and protocol["output"] == str(root)
            and protocol["script_sha256"] == sha(__file__) and protocol["wrapper_sha256"] == sha(WORKER),
            "Diagnostic identity changed")
    parent, source = safe_path(protocol["parent"]), safe_path(protocol["source"])
    with parent_lock(parent):
        require(_snapshot(parent, source) == protocol["snapshot"], "Frozen parent evidence changed")
    return protocol


def sheet_native(request, runtime, original_worker):
    ready = backends._image_ready(runtime)
    if ready["status"] != "ready":
        return {"status": "unknown", "reason": ready["reason"], "execution_costs": {"container_calls": 0, "wall_seconds": 0}}
    timeout, memory, cpus = backends._runtime_limits(runtime)
    payload = json.dumps(request, allow_nan=False).encode()
    require(len(payload) <= 32 * 1024 * 1024, "Native request exceeds budget")
    docker, name = shutil.which("docker"), "unknown-replay-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="native-unknown-") as directory:
        root = Path(directory)
        root.chmod(0o755)
        for filename, raw in (("request.json", payload), ("wrapper.py", WORKER.read_bytes()),
                              ("original_worker.py", safe_path(original_worker).read_bytes())):
            (root / filename).write_bytes(raw)
            (root / filename).chmod(0o444)
        command = [docker, "run", "--pull=never", "--name", name, "--network=none", "--read-only",
            "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges=true", "--pids-limit=128",
            f"--memory={memory}m", f"--memory-swap={memory}m", f"--cpus={cpus}", "--ipc=private", "--shm-size=64m",
            "--no-healthcheck", "--log-driver=none", "--ulimit=nofile=256:256", "--ulimit=core=0:0",
            "--env", f"NATIVE_UNKNOWN_CONTAINER={WORKER_PROTOCOL}", "--env", f"ORIGINAL_WORKER_SHA256={sha(original_worker)}",
            "--env", f"CONTINUAL_EVAL_CONTAINER={backends.PROTOCOL}", "--env", "MPLCONFIGDIR=/tmp/matplotlib",
            "--env", "OMP_NUM_THREADS=1", "--env", "OPENBLAS_NUM_THREADS=1",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777", "--workdir=/tmp",
            "--mount", f"type=bind,source={root},target=/input,readonly",
            "--entrypoint=python", runtime["image"], "-I", "-B", "/input/wrapper.py"]
        started, result, cleanup, error = time.monotonic(), None, None, None
        try:
            result = _bounded_command(command, timeout, limit=16 * 1024 * 1024)
        except (OSError, subprocess.TimeoutExpired) as exc:
            error = type(exc).__name__
        finally:
            try:
                cleanup = _bounded_command([docker, "rm", "--force", name], 10)
            except (OSError, subprocess.TimeoutExpired):
                pass
        cleaned = (cleanup is not None and not cleanup.timed_out and not cleanup.overflow and not cleanup.unavailable
                   and (cleanup.code == 0 or b"no such container" in cleanup.stderr.lower()))
        metadata = {"cleanup_confirmed": bool(cleaned), "runtime_image_id": ready["image_id"],
            "execution_costs": {"container_calls": 1, "wall_seconds": round(time.monotonic() - started, 6), "includes_cleanup": True}}
        if not cleaned or error or result.timed_out or result.overflow or result.unavailable or result.code != 0:
            return {**metadata, "status": "unknown", "reason": "container_cleanup_unconfirmed" if not cleaned
                    else "native_timeout" if error == "TimeoutExpired" or (result and result.timed_out)
                    else "native_execution_unavailable"}
        try:
            envelope = _strict_json(result.stdout)
            require(envelope["protocol"] == WORKER_PROTOCOL and type(envelope["result"]) is dict, "Invalid native receipt")
            body = envelope["result"]
            require(set(body) <= {"status", "reason", "diagnostic", "output_base64"}
                    and body.get("status") in {"available", "unknown", "missing_output"}, "Invalid worker result")
            return {**body, **metadata}
        except (ValueError, KeyError, TypeError, RecursionError):
            return {**metadata, "status": "unknown", "reason": "invalid_native_receipt"}


def _validate_result(result, benchmark, fixture, runtime):
    require(type(result) is dict, "Missing native result")
    if benchmark == "bigcodebench":
        _valid_score(result)
    else:
        require(result.get("status") in {"available", "unknown", "missing_output", "invalid_program"}, "Invalid diagnostic result")
        require(type(result.get("reason")) is str, "Missing diagnostic reason")
    if not fixture and result.get("execution_costs", {}).get("container_calls", 0):
        require(result.get("runtime_image_id", runtime["image"]) == runtime["image"], "Native image differs")
    if not fixture and result.get("status") in {"pass", "fail", "available", "missing_output"}:
        require(result.get("cleanup_confirmed") is True and result.get("runtime_image_id") == runtime["image"],
                "Successful execution identity or cleanup unverified")


def run(output, native_lock, *, fixture_execute=None):
    root = safe_path(output)
    with output_lock(root):
        protocol = check(root)
        snapshot = protocol["snapshot"]
        require(snapshot["fixture"] == (fixture_execute is not None), "Fixture dispatch mismatch")
        parent, source, lock_path = map(safe_path, (protocol["parent"], protocol["source"], native_lock))
        require(str(lock_path) == protocol["native_lock"] and lock_path.is_file(), "Shared native lock differs")
        for path in (root / "reports").glob("*.json"):
            report = read_json(path, sealed=True)
            require(report["protocol_hash"] == protocol["record_hash"], "Published protocol differs")
            for key, expected in report["record_hashes"].items():
                require(read_json(root / "records" / (key + ".json"), sealed=True)["record_hash"] == expected,
                        "Published diagnostic record changed")
        with parent_lock(parent), lock_path.open("rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            require(_snapshot(parent, source) == snapshot, "Original evidence changed before execution")
            plan = read_json(parent / "plan.json", sealed=True)
            benchmark = snapshot["benchmark"]
            runtime = plan["config"]["runtime"][benchmark]
            if not snapshot["fixture"]:
                require(backends._image_ready(runtime)["status"] == "ready", "Native image/runtime unavailable; no execution submitted")
            panel = load_panel(plan["panels"][benchmark]["path"])
            tasks = {digest(t): t for t in panel["tasks"]}
            rows = {}
            for item in snapshot["selected"]:
                key = digest(item)
                identity = {"protocol_hash": protocol["record_hash"], "item": item}
                path, intent = root / "records" / (key + ".json"), root / "intents" / (key + ".json")
                if path.exists():
                    row = read_json(path, sealed=True)
                    require(row["identity"] == identity and read_json(intent, sealed=True) == seal(identity), "Diagnostic binding differs")
                else:
                    require(not intent.exists(), "Unclosed diagnostic execution: do not retry")
                    prediction = read_json(parent / "predictions" / item["position"] / "prediction.json", sealed=True)["prediction"]
                    task = tasks[item["task_hash"]]
                    code = prediction["output"] if benchmark == "bigcodebench" else prediction["output"]["code"]
                    write_json(intent, seal(identity))
                    syntax = None
                    if benchmark == "spreadsheetbench":
                        try:
                            compile(code, "generated.py", "exec")  # Parse only; no execution on host.
                        except SyntaxError as exc:
                            syntax = {"status": "invalid_program", "reason": "frozen_generated_syntax_error",
                                      "diagnostic": {"phase": "generated_compile", "exception_type": "SyntaxError",
                                                     "line": exc.lineno, "offset": exc.offset},
                                      "execution_costs": {"container_calls": 0, "wall_seconds": 0}}
                    if syntax is not None:
                        result = syntax
                    elif fixture_execute:
                        result = fixture_execute(benchmark, task, prediction, item, runtime)
                    elif benchmark == "bigcodebench":
                        result = backends.score(benchmark, task["public"], task["private"], prediction, runtime=runtime)
                    else:
                        input_path = task["public"]["input_files"][item["case"]]
                        require(sha(input_path) == item["input_sha256"], "Public workbook changed")
                        result = sheet_native({"operation": "spreadsheet_generate", "code": code,
                            "input_base64": base64.b64encode(backends._xlsx_bytes(input_path)).decode()},
                            runtime, source / "skillopt/continual_eval/native_worker.py")
                    _validate_result(result, benchmark, snapshot["fixture"], runtime)
                    calls = result.get("execution_costs", {}).get("container_calls", 0)
                    row = seal({"identity": identity, "result": result,
                        "cleanup_unconfirmed": not snapshot["fixture"] and bool(calls) and result.get("cleanup_confirmed") is not True})
                    write_json(path, row)
                _validate_result(row["result"], benchmark, snapshot["fixture"], runtime)
                rows[key] = row
                if row["cleanup_unconfirmed"]:
                    break
            require(_snapshot(parent, source) == snapshot, "Original evidence changed during diagnostic")
            report = seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "benchmark": benchmark,
                "status": "completed" if len(rows) == len(snapshot["selected"]) and not any(r["cleanup_unconfirmed"] for r in rows.values()) else "pending",
                "counts": dict(Counter(r["result"]["status"] for r in rows.values())), "selected_cases": len(snapshot["selected"]),
                "selected_positions": len({s["position"] for s in snapshot["selected"]}), "closed_cases": len(rows),
                "record_hashes": {k: v["record_hash"] for k, v in rows.items()}, "new_model_calls": 0,
                "container_calls": sum(r["result"].get("execution_costs", {}).get("container_calls", 0) for r in rows.values()),
                "native_wall_seconds": sum(r["result"].get("execution_costs", {}).get("wall_seconds", 0) for r in rows.values()),
                "original_scores_unchanged": True, "diagnostic_only": True, "deployment_authorized": False})
            write_json(root / "reports" / (report["record_hash"] + ".json"), report)
            return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "check", "preflight", "run"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-root")
    parser.add_argument("--source-root")
    parser.add_argument("--native-lock")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        require(args.run_root and args.source_root and args.native_lock, "Parent/source/lock required")
        result = prepare(args.run_root, args.source_root, args.output, args.native_lock)
    elif args.mode in {"check", "preflight"}:
        result = check(args.output)
        if args.mode == "preflight":
            plan = read_json(Path(result["parent"]) / "plan.json", sealed=True)
            result = {"version": VERSION, "new_model_calls": 0, "diagnostic_only": True,
                      **backends._image_ready(plan["config"]["runtime"][result["snapshot"]["benchmark"]])}
    else:
        require(args.native_lock, "Shared native lock required")
        result = run(args.output, args.native_lock)
    print(json.dumps({k: result[k] for k in ("version", "record_hash", "status", "reason", "counts", "new_model_calls", "diagnostic_only") if k in result}))


if __name__ == "__main__":
    main()
