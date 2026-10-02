"""Independent, zero-API KOR length-output diagnostic; never repair old scores.

Prepare freezes ALL closed length replies after the full original run closes.
Only wrapper syntax determines eligibility. The unchanged entire reply is sent
to the original isolated scorer, never a host expression evaluator. Diagnostic
outcomes cannot authorize a Skill, a changed baseline, or a retry.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
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
from skillopt.validator_pilot.api import digest

VERSION = "kor-frozen-deliverable-diagnostic-v1"


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


@contextmanager
def _parent_lock(root):
    # Keep this standalone: the original evaluation source predates learning
    # reproposal helpers and must never be overlaid to import a lock utility.
    path = safe_path(root / ".writer.lock")
    require(path.is_file(), "Original writer lock missing")
    with path.open("rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Original run still has an active writer") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _syntax(text):
    # Conservative common format: no answer extraction, trimming, or selection.
    return (isinstance(text, str) and len(text.encode()) <= backends.MAX_RESPONSE
            and bool(re.search(r"\[\[\s*\S.*?\]\]", text, re.S)))


def _snapshot(root, source):
    plan = read_json(root / "plan.json", sealed=True)
    fixture = plan["config"]["model"]["provider"] == "fixture"
    require(plan["version"] == "continual-eval-v2" and plan["config"]["partition"] == "development"
            and plan["config"]["methods"] == ["no_skill"] and plan["config"]["histories"] == ["h0"]
            and plan["repeats"] == 2 and all(t["benchmark"] == "korbench" for t in plan["tasks"]),
            "Only completed development KOR No-Skill protocol supported")
    require(fixture or len(plan["tasks"]) == 500, "Full 500-task natural panel required")
    model = plan["config"]["model"]
    require(fixture or (model["provider"] == "bigmodel" and model["name"] == "glm-5.3"
            and model["max_tokens"] == 65536 and model["transport"] == {
                "stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                "initial_health_policy": "completed_response_v1"}), "Unexpected natural long-response profile")
    require(plan["source_identity"] == source_identity() and plan["host_runtime"] == runtime_identity(),
            "Run with the original frozen evaluation package/runtime")
    for name, expected in plan["source_identity"].items():
        path = safe_path(source / "skillopt" / name)
        require(path.is_relative_to(source / "skillopt") and _sha(path) == expected, "Frozen source changed")
    cp = load_checkpoint(root, "no_skill", "h0", 0, plan)
    require(cp["skill_text"] == "", "Not the frozen empty checkpoint")
    service = read_json(root / "model_service.json", sealed=True)
    service.pop("record_hash")
    calls, selected, excluded, positions, caches = [], [], Counter(), set(), set()
    for task in plan["tasks"]:
        require(task["partition"] == "development", "Final data forbidden")
        for repeat in range(2):
            request = {"plan_hash": plan["record_hash"], "checkpoint_hash": cp["record_hash"],
                       "benchmark": "korbench", "task_hash": task["task_hash"], "repeat": repeat}
            key = digest(request)
            positions.add(key)
            base = root / "predictions" / key
            receipts = _stored_calls(base)
            require(len(receipts) == len(list((base / "call_intents").glob("*.json"))) == 1,
                    "Missing, extra or unclosed call")
            path = next((base / "calls").glob("*.json"))
            record, receipt = read_json(path, sealed=True), receipts[0]
            model = plan["config"]["model"]
            require(record["request"]["position"] == request
                    and record["request"]["max_tokens"] == model["max_tokens"]
                    and receipt["request"]["max_tokens"] == model["max_tokens"]
                    and receipt["request"]["service"] == service
                    and receipt["request"]["model"] == model["name"], "Call identity differs")
            require(type(receipt.get("ok")) is bool and type(receipt.get("http_attempt_count")) is int
                    and receipt["http_attempt_count"] >= 1
                    and (not receipt["ok"] or receipt.get("returned_model") == model["name"]),
                    "Invalid closed call/returned model")
            cache = root / "api/calls" / (receipt["request_hash"] + ".json")
            require(read_json(cache) == receipt, "API cache differs from bound receipt")
            caches.add(cache.name)
            prediction = read_json(base / "prediction.json", sealed=True)
            require(prediction["request"] == request and prediction["costs"] == _costs(receipts)
                    and read_json(base / "intent.json", sealed=True) == seal(request), "Prediction binding differs")
            score = read_json(root / "host_only/scores" / (key + ".json"), sealed=True)
            require(score["prediction_hash"] == prediction["record_hash"]
                    and score["plan_hash"] == plan["record_hash"] and score["checkpoint_hash"] == cp["record_hash"]
                    and score["task_id"] == task["task_id"] and score["repeat"] == repeat
                    and score["costs"] == _costs(receipts)
                    and read_json(root / "host_only/score_intents" / (key + ".json"), sealed=True)
                    == seal({"request": request, "prediction_hash": prediction["record_hash"]}), "Score binding differs")
            calls.append(receipt)
            if receipt.get("finish_reason") != "length":
                reason = receipt.get("finish_reason")
                excluded[reason if reason in {"stop", "network_error", "content_filter", "sensitive"} else "other"] += 1
                continue
            require(score["status"] == "unknown" and score["reason"] == "model_response_truncated",
                    "Original length status must remain unknown")
            text = receipt.get("response")
            require(isinstance(text, str), "Missing raw length reply")
            complete = receipt.get("stream_complete") is True and receipt.get("status") == 200
            require(not complete or receipt.get("returned_model") == model["name"], "Returned model differs")
            selected.append({"position": key, "task_hash": task["task_hash"], "repeat": repeat,
                "receipt_path": str(path.relative_to(root)), "receipt_hash": record["record_hash"],
                "raw_response_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "original_score_hash": score["record_hash"], "original_status": "unknown",
                "eligible": complete and _syntax(text),
                "reason": "complete_wrapper" if complete and _syntax(text) else "deliverable_incomplete"})
    require({p.name for p in (root / "api/calls").glob("*.json")} == caches
            and {p.stem for p in (root / "host_only/scores").glob("*.json")} == positions
            and {p.name for p in (root / "predictions").iterdir() if p.is_dir()} == positions,
            "Unexpected or missing frozen positions")
    reports = [read_json(p, sealed=True) for p in (root / "host_only/reports").glob("*.json")]
    reports = [r for r in reports if r["plan_hash"] == plan["record_hash"]
               and r["run_accounting"]["scored_positions"] == len(positions)]
    require(len(reports) == 1 and all(reports[0]["run_accounting"][k] == v for k, v in _costs(calls).items()),
            "No unique, complete original report/accounting")
    native = digest(backends._kor_sources(plan["config"]["runtime"]["korbench"])) if not fixture else None
    files = {str(p.relative_to(root)): _sha(p) for p in root.rglob("*.json")}
    return {"plan_hash": plan["record_hash"], "report_hash": reports[0]["record_hash"],
            "native_sources_hash": native, "files": files, "selected": selected,
            "excluded_finish_reasons": dict(excluded), "original_positions": len(positions), "fixture": fixture}


def prepare(run_root, source_root, output, native_lock):
    parent, source, root = map(safe_path, (run_root, source_root, output))
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
                                        for p in (parent, source)), "New independent output required")
    lock_path = safe_path(native_lock)
    require(lock_path.is_file() and not any(lock_path.is_relative_to(p) for p in (parent, source, root)),
            "Existing external shared native lock required")
    with _parent_lock(parent):
        snapshot = _snapshot(parent, source)
        value = seal({"version": VERSION, "parent_root": str(parent), "source_root": str(source),
            "output_root": str(root), "native_lock": str(lock_path),
            "script_sha256": _sha(Path(__file__)), "snapshot": snapshot,
            "new_model_calls": 0, "diagnostic_only": True, "deployment_authorized": False})
        write_json(root / "protocol.json", value)
        return value


def check(output):
    root = safe_path(output)
    value = read_json(root / "protocol.json", sealed=True)
    require(value["version"] == VERSION and value["output_root"] == str(root)
            and value["script_sha256"] == _sha(Path(__file__)), "Diagnostic identity changed")
    parent, source = safe_path(value["parent_root"]), safe_path(value["source_root"])
    with _parent_lock(parent):
        require(_snapshot(parent, source) == value["snapshot"], "Original frozen evidence changed")
    return value


def run(output, native_lock, *, fixture_score=None):
    root = safe_path(output)
    with output_lock(root):
        value = check(root)
        require(value["snapshot"]["fixture"] == (fixture_score is not None), "Fixture dispatch mismatch")
        parent = safe_path(value["parent_root"])
        lock_path = safe_path(native_lock)
        require(str(lock_path) == value["native_lock"] and lock_path.is_file()
                and not any(lock_path.is_relative_to(p) for p in
                (parent, root, safe_path(value["source_root"]))), "Existing external shared native lock required")
        # Previously published diagnostic records cannot be silently resealed
        # into different outcomes on a later check/run invocation.
        for report_path in (root / "reports").glob("*.json"):
            published = read_json(report_path, sealed=True)
            require(published["protocol_hash"] == value["record_hash"], "Published protocol differs")
            for item, expected in zip(value["snapshot"]["selected"], published["record_hashes"], strict=False):
                require(read_json(root / "records" / (item["position"] + ".json"), sealed=True)["record_hash"] == expected,
                        "Published diagnostic record changed")
            require(len(published["record_hashes"]) <= len(value["snapshot"]["selected"]), "Invalid published roster")
        with _parent_lock(parent), lock_path.open("rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            plan = read_json(parent / "plan.json", sealed=True)
            panel = load_panel(plan["panels"]["korbench"]["path"])
            require(panel_hash(panel) == plan["panels"]["korbench"]["panel_hash"], "Panel changed")
            tasks = {digest(t): t for t in panel["tasks"]}
            runtime = plan["config"]["runtime"]["korbench"]

            def valid_result(result):
                _valid_score(result)
                if not value["snapshot"]["fixture"]:
                    require("runtime_image_id" not in result or result["runtime_image_id"] == runtime["image"],
                            "Native image differs")
                    if result["status"] != "unknown":
                        require(result.get("runtime_image_id") == runtime["image"]
                                and result.get("cleanup_confirmed") is True, "Native identity/cleanup unverified")

            rows = []
            for item in value["snapshot"]["selected"]:
                path = root / "records" / (item["position"] + ".json")
                intent = root / "intents" / path.name
                identity = {"protocol_hash": value["record_hash"], "item": item}
                if path.exists():
                    row = read_json(path, sealed=True)
                    require(row["identity"] == identity and read_json(intent, sealed=True) == seal(identity),
                            "Diagnostic cache differs")
                    valid_result(row["result"])
                    rows.append(row)
                    if row.get("cleanup_unconfirmed"):
                        break
                    continue
                require(not intent.exists(), "Unclosed diagnostic execution: do not retry")
                write_json(intent, seal(identity))
                if not item["eligible"]:
                    result = {"status": "unknown", "score": None, "metrics": {}, "reason": item["reason"]}
                else:
                    raw = read_json(parent / item["receipt_path"], sealed=True)["receipt"]["response"]
                    require(hashlib.sha256(raw.encode()).hexdigest() == item["raw_response_sha256"], "Raw reply changed")
                    task = tasks[item["task_hash"]]
                    scorer = fixture_score or backends.score
                    result = scorer("korbench", task["public"], task["private"],
                        {"status": "available", "output": raw}, runtime=runtime)
                    valid_result(result)
                cleanup_unconfirmed = (item["eligible"] and not value["snapshot"]["fixture"]
                                       and result.get("cleanup_confirmed") is not True)
                row = seal({"identity": identity, "result": result, "cleanup_unconfirmed": cleanup_unconfirmed})
                write_json(path, row)
                rows.append(row)
                if cleanup_unconfirmed:
                    break
            summary = seal({"version": VERSION, "protocol_hash": value["record_hash"],
                "status": "completed" if len(rows) == len(value["snapshot"]["selected"])
                    and not any(r.get("cleanup_unconfirmed") for r in rows) else "pending",
                "counts": dict(Counter(r["result"]["status"] for r in rows)),
                "selected_positions": len(value["snapshot"]["selected"]), "closed_positions": len(rows),
                "record_hashes": [r["record_hash"] for r in rows], "new_model_calls": 0,
                "native_wall_seconds": sum(r["result"].get("execution_costs", {}).get("wall_seconds", 0) for r in rows),
                "diagnostic_only": True, "original_scores_unchanged": True, "deployment_authorized": False})
            write_json(root / "reports" / (summary["record_hash"] + ".json"), summary)
            return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "check", "run"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-root")
    parser.add_argument("--source-root")
    parser.add_argument("--native-lock")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        require(args.run_root and args.source_root and args.native_lock, "Parent run/source/native lock required")
        value = prepare(args.run_root, args.source_root, args.output, args.native_lock)
    elif args.mode == "check":
        value = check(args.output)
    else:
        require(args.native_lock, "Shared native lock required")
        value = run(args.output, args.native_lock)
    print(json.dumps({k: value[k] for k in ("version", "record_hash", "new_model_calls", "diagnostic_only")}))


if __name__ == "__main__":
    main()
