"""Zero-model, full frozen BCB development-roster reference qualification.

References are executed only by the existing isolated native scorer. This is
environment qualification, not a model run, answer feedback, or a Skill gate.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from contextlib import contextmanager

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

from . import backends
from .core import output_lock, read_json, require, runtime_identity, safe_path, source_identity, write_json
from .datasets import _rows, panel_hash
from .runner import _valid_score

VERSION = "bcb-frozen-reference-qualification-v1"
REVISION = "b74c0d0bf70d2c0bc459be537895cca163007f1a"


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


@contextmanager
def _lock(path, *, shared=False):
    import fcntl

    path = safe_path(path)
    require(path.is_file(), "Existing baseline/native lock required")
    with path.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _inputs(plan_path, raw_root):
    plan_path, raw_root = safe_path(plan_path), safe_path(raw_root)
    plan = read_json(plan_path, sealed=True)
    current = source_identity()
    require(all(current.get(k) == h for k, h in plan["source_identity"].items())
            and runtime_identity() == plan["host_runtime"], "Baseline execution source/runtime changed")
    require(plan["config"]["partition"] == "development" and plan["config"]["methods"] == ["no_skill"],
            "Reference qualification requires the original No-Skill development plan")
    panel_path = safe_path(plan["panels"]["bigcodebench"]["path"])
    panel = read_json(panel_path)
    require(panel_hash(panel) == plan["panels"]["bigcodebench"]["panel_hash"], "Baseline panel changed")
    tasks = panel["tasks"]
    fixture = plan["config"]["model"]["provider"] == "fixture"
    require((panel["provenance"] == "fixture") == fixture and panel["benchmark"] == "bigcodebench"
            and len(tasks) == 400 and len({t["family_id"] for t in tasks}) == 399
            and all(t["partition"] == "development" for t in tasks), "Full original 400-task/399-family roster required")
    roster = [{"benchmark": "bigcodebench", **{k: t[k] for k in
              ("task_id", "family_id", "project_id", "partition")}, "task_hash": digest(t)} for t in tasks]
    require([t for t in plan["tasks"] if t["benchmark"] == "bigcodebench"] == roster, "Plan task roster differs")
    receipt = read_json(raw_root / "download-receipt.json")
    rows_path, parquet = raw_root / "rows.json", raw_root / "v0.1.4.parquet"
    require(receipt["rows_sha256"] == _sha(rows_path)
            and receipt["source_parquet_sha256"] == _sha(parquet), "Raw cache/download receipt mismatch")
    require(fixture or (receipt["repository"] == "bigcode/bigcodebench" and receipt["revision"] == REVISION
            and receipt["version_split"] == "v0.1.4" and panel["dataset_revision"] ==
            f"bigcode/bigcodebench@{REVISION}:v0.1.4:instruct"), "Unreviewed reference dataset revision")
    raw, raw_digest = _rows(read_json(rows_path))
    by_id = {r["task_id"]: r for r in raw}
    require(len(by_id) == len(raw) and (fixture or len(raw) == 1140), "Raw task IDs/count changed")
    references = []
    for task in tasks:
        row = by_id[task["task_id"]]
        require(task["public"] == {"prompt": row["instruct_prompt"], "entry_point": row["entry_point"]}
                and task["private"]["test"] == row["test"]
                and task["private"]["source_sha256"] == raw_digest, "Raw reference/public/test binding mismatch")
        require(type(row["canonical_solution"]) is str and row["canonical_solution"].strip()
                and type(row["complete_prompt"]) is str, "Missing reference body/prefix")
        code = row["complete_prompt"] + row["canonical_solution"]
        tree = ast.parse(code)  # Parsing only: no eval, exec, import or host task execution.
        require(sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == row["entry_point"]
                    for n in tree.body) == 1, "Assembled reference entrypoint missing/ambiguous")
        references.append({"task": task, "code": code, "identity": {
            "task_hash": digest(task), "public_hash": digest(task["public"]),
            "test_sha256": hashlib.sha256(row["test"].encode()).hexdigest(),
            "reference_sha256": hashlib.sha256(code.encode()).hexdigest()}})
    runtime = plan["config"]["runtime"]["bigcodebench"]
    require(runtime.get("timeout_seconds") == 300 and runtime.get("memory_mb") == 8192
            and runtime.get("cpus") == 1 and set(runtime) == {"image", "timeout_seconds", "memory_mb", "cpus"},
            "Use the exact 300s/8GiB/1CPU baseline runtime")
    files = {str(p): _sha(p) for p in (plan_path, panel_path, rows_path, parquet, raw_root / "download-receipt.json")}
    return {"plan": plan, "references": references, "files": files, "runtime": runtime, "fixture": fixture}


def _protocol(plan_path, raw_root, native_lock, data):
    return seal({"version": VERSION, "plan_path": str(plan_path), "raw_root": str(raw_root),
                 "native_lock": str(native_lock), "baseline_plan_hash": data["plan"]["record_hash"],
                 "input_files": data["files"], "source_identity": source_identity(), "host_runtime": runtime_identity(),
                 "runtime": data["runtime"], "reference_roster": [r["identity"] for r in data["references"]],
                 "assembly": "complete_prompt + canonical_solution; exact concatenation",
                 "tasks": 400, "families": 399, "repeats": 1,
                 "evidence_kind": "engineering_fixture" if data["fixture"] else "official_reference_environment_qualification",
                 "model_calls": 0, "score_feedback_allowed": False, "baseline_scores_replaced": False,
                 "deployment_authorized": False, "skill_gate_allowed": False,
                 "resume_policy": "skip_closed_records_never_retry_unknown_or_open_intents"})


def prepare(plan_path, raw_root, output, *, native_lock):
    plan_path, raw_root, root, native_lock = map(safe_path, (plan_path, raw_root, output, native_lock))
    require(not root.exists() and not root.is_relative_to(plan_path.parent) and not root.is_relative_to(raw_root),
            "Use a new independent qualification directory")
    require(native_lock.is_file(), "Existing common native lock required")
    with _lock(plan_path.parent / ".writer.lock", shared=True):
        data = _inputs(plan_path, raw_root)
        value = _protocol(plan_path, raw_root, native_lock, data)
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
    return {"status": "prepared_not_executed", "protocol_hash": value["record_hash"], "tasks": 400,
            "model_calls": 0, "container_calls": 0}


def _load(root):
    value = read_json(root / "protocol.json", sealed=True)
    data = _inputs(safe_path(value["plan_path"]), safe_path(value["raw_root"]))
    require(value == _protocol(safe_path(value["plan_path"]), safe_path(value["raw_root"]),
                              safe_path(value["native_lock"]), data), "Qualification identity changed")
    return value, data


def _request(protocol, ref):
    return {"protocol_hash": protocol["record_hash"], **ref["identity"], "repeat": 0}


def _validated_score(value, data):
    value = _valid_score(value)
    if not data["fixture"]:
        image = data["runtime"]["image"]
        if value["status"] in {"pass", "fail"}:
            require(value.get("runtime_image_id") == image and value.get("cleanup_confirmed") is True,
                    "Known result requires frozen native image and confirmed cleanup")
        for metadata, field in ((value, "runtime_image_id"), (value.get("execution_costs", {}), "image_id")):
            require(field not in metadata or metadata[field] == image, "Native execution image differs")
    return value


def _records(root, protocol, data):
    requests = {digest(_request(protocol, r)): _request(protocol, r) for r in data["references"]}
    intents, records = {}, {}
    for path in (root / "intents").glob("*.json"):
        require(path.stem in requests and read_json(path, sealed=True) == seal(requests[path.stem]), "Unknown/changed intent")
        intents[path.stem] = requests[path.stem]
    for path in (root / "records").glob("*.json"):
        row = read_json(path, sealed=True)
        require(path.stem in intents and row["request"] == intents[path.stem], "Reference receipt/input mismatch")
        _validated_score(row["score"], data)
        records[path.stem] = row
    for path in (root / "reports").glob("*.json"):
        prior = read_json(path, sealed=True)
        require(prior["protocol_hash"] == protocol["record_hash"] and path.stem == prior["record_hash"]
                and all(k in records and records[k]["record_hash"] == h for k, h in prior["record_hashes"].items()),
                "Previously reported closed evidence changed")
    return intents, records


def _report(root, protocol, data):
    intents, rows = _records(root, protocol, data)
    counts = {s: sum(r["score"]["status"] == s for r in rows.values()) for s in ("pass", "fail", "unknown")}
    unclosed, unsubmitted = len(intents) - len(rows), 400 - len(intents)
    executions = [r["score"].get("execution_costs", {}) for r in rows.values()]
    costs_known = all(type(c.get("container_calls")) is int and type(c.get("wall_seconds")) in (int, float)
                      for c in executions) and not unclosed
    reasons = {}
    for row in rows.values():
        # Controlled native reason codes only; no traceback, test or code text.
        reason = row["score"]["reason"]
        reason = reason if reason in {"official_bigcodebench_untrusted_check", "native_timeout", "native_dependency_unavailable",
            "container_cleanup_unconfirmed", "native_execution_unavailable", "invalid_native_receipt"} else "other_or_host_exception"
        reasons[reason] = reasons.get(reason, 0) + 1
    return seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
                 "status": "completed" if len(rows) == 400 else "pending", "model_calls": 0,
                 "tasks": 400, "families": 399, "closed": len(rows), **counts,
                 "unclosed": unclosed, "unsubmitted": unsubmitted, "reason_counts": reasons,
                 "container_calls_known_subtotal": sum(c.get("container_calls", 0) for c in executions),
                 "container_wall_seconds_known_subtotal": round(sum(c.get("wall_seconds", 0) for c in executions), 6),
                 "execution_costs_complete_for_submitted_positions": costs_known,
                 "cleanup_confirmed": sum(r["score"].get("cleanup_confirmed") is True for r in rows.values()),
                 "record_hashes": {k: r["record_hash"] for k, r in rows.items()}, "evidence_kind": protocol["evidence_kind"],
                 "score_feedback_allowed": False, "baseline_scores_replaced": False, "skill_gate_allowed": False,
                 "limitations": ["Reference failure does not prove a model failure on that task was environmental.",
                                 "Reference passing does not certify all alternative implementations or runtime behaviors.",
                                 "This is not a model accuracy or Skill-effect experiment; no old outcome is relabeled."]})


def run(output, *, max_new_tasks=None, fixture_score=None):
    root = safe_path(output)
    initial = read_json(root / "protocol.json", sealed=True)
    require(max_new_tasks is None or type(max_new_tasks) is int and 0 <= max_new_tasks <= 400, "Invalid bounded run size")
    with output_lock(root), _lock(safe_path(initial["plan_path"]).parent / ".writer.lock", shared=True), \
            _lock(safe_path(initial["native_lock"])):
        protocol, data = _load(root)
        require(data["fixture"] == (fixture_score is not None), "Fixture scorer boundary")
        intents, records = _records(root, protocol, data)
        terminal = root / "result.json"
        if terminal.exists():
            result = read_json(terminal, sealed=True)
            require(result == _report(root, protocol, data), "Completed reference evidence changed")
            return result
        unsafe = any(r["score"]["reason"] in {"container_cleanup_unconfirmed", "host_scorer_exception"}
                     for r in records.values())
        if set(intents) - set(records) or unsafe:
            return _report(root, protocol, data)  # Never retry an uncertain execution or possibly live container.
        if not data["fixture"]:
            require(backends._image_ready(data["runtime"])["status"] == "ready", "Pinned native image unavailable")
        count = 0
        for ref in data["references"]:
            request = _request(protocol, ref)
            key = digest(request)
            if key in records:
                continue
            if (root / "PAUSE").exists() or (max_new_tasks is not None and count >= max_new_tasks):
                break
            write_json(root / "intents" / (key + ".json"), seal(request))
            task = ref["task"]
            try:
                score = fixture_score(task, ref["code"]) if fixture_score else backends.score(
                    "bigcodebench", task["public"], task["private"],
                    {"status": "available", "output": ref["code"], "reason": "official_reference_not_model"},
                    runtime=data["runtime"])
                score = _validated_score(score, data)
            except Exception:
                score = {"status": "unknown", "score": None, "reason": "host_scorer_exception", "metrics": {}}
            write_json(root / "records" / (key + ".json"), seal({"request": request, "score": score}))
            count += 1
            if score["reason"] in {"container_cleanup_unconfirmed", "host_scorer_exception"}:
                break
        result = _report(root, protocol, data)
        write_json(root / "reports" / (result["record_hash"] + ".json"), result)
        if result["status"] == "completed":
            write_json(terminal, result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "run"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--raw-root")
    parser.add_argument("--native-lock")
    parser.add_argument("--max-new-tasks", type=int)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        require(args.plan and args.raw_root and args.native_lock, "Plan/cache/native lock required")
        result = prepare(args.plan, args.raw_root, args.output, native_lock=args.native_lock)
    elif args.command == "check":
        root = safe_path(args.output)
        initial = read_json(root / "protocol.json", sealed=True)
        with _lock(safe_path(initial["plan_path"]).parent / ".writer.lock", shared=True):
            value, _ = _load(root)
        result = {"status": "validated_not_executed", "protocol_hash": value["record_hash"], "model_calls": 0}
    else:
        result = run(args.output, max_new_tasks=args.max_new_tasks)
    print(json.dumps({k: result[k] for k in ("status", "protocol_hash", "model_calls", "tasks", "closed", "pass", "fail",
          "unknown", "unclosed", "unsubmitted", "container_calls_known_subtotal") if k in result}))


if __name__ == "__main__":
    main()
