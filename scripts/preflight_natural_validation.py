"""Engineering-only Docker preflight for an already frozen natural panel.

No model client is constructed. Reference and engineering negative-control
programs run exclusively through the existing SSH/Docker executor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.checks import ExecutionCache, validate_callable
from skillopt.skill_validation.models import ArtifactRecord, SourceFile, require
from skillopt.skill_validation.natural_data import load_tasks
from skillopt.skill_validation.natural_study import ExecutorPool, audit
from skillopt.skill_validation.research import fixed_rubric
from skillopt.validator_pilot.api import digest, write_immutable_json


def artifact(row, code, label):
    return ArtifactRecord(
        row["task"].contract.content_hash, 0, "unassigned", "engineering-preflight",
        hashlib.sha256(b"engineering-preflight").hexdigest(),
        (SourceFile("solution.py", code), SourceFile.from_dict(row["public_wrapper"])),
        "available", "fixture", True, False, "synthetic:engineering-preflight:" + label,
        digest({"label": label, "code": code}),
    )


def run(repo, frozen, output, remote_repo, workers=4):
    started = time.monotonic()
    manifest_path = frozen / "data_manifest.json"
    original_manifest_bytes = manifest_path.read_bytes()
    manifest = verify(json.loads(original_manifest_bytes))
    rows = load_tasks(repo, manifest, "development")
    summary_path = output / "summary.json"
    if summary_path.exists():
        summary = verify(json.loads(summary_path.read_text()))
        if summary["manifest_hash"] != manifest["record_hash"]:
            raise ValueError("Engineering output belongs to another frozen panel")
        return summary
    pool = ExecutorPool(remote_repo, workers)
    outcomes = []

    def inspect(row, label, code=None):
        identifier = row["identity"]["task_id"]
        suffix = identifier.replace("/", "_") + "-" + label
        record_path = output / "rows" / (suffix + ".json")
        if record_path.exists():
            return verify(json.loads(record_path.read_text()))
        is_reference = code is None
        item = artifact(row, row["host_audit"]["reference_code"] if is_reference else code, label)
        reference_h = audit(row, None if is_reference else item, pool, output, reference=is_reference)
        cache = ExecutionCache(pool, output / "public_checks" / suffix, max_executions=1)
        public = validate_callable(row["public_task"], item, fixed_rubric(), cache)
        write_immutable_json(output / "public_reports" / (suffix + ".json"), public)
        execution = reference_h.get("execution") or {}
        actual = execution.get("actual") if isinstance(execution.get("actual"), dict) else {}
        record = seal({
            "task_id": identifier, "label": label, "engineering_only": True,
            "provenance_kind": "fixture", "audit_status": reference_h["status"],
            "native_status": reference_h["native_status"], "public_status": public["status"],
            "audit_receipt_hash": reference_h["record_hash"], "public_report_hash": public["record_hash"],
            "audit_execution_status": execution.get("status"), "audit_reason": execution.get("reason"),
            "audit_exception": execution.get("exception"),
            "audit_counts": {key: actual.get(key) for key in (
                "base_count", "plus_count", "base_observed", "plus_observed", "base_failed", "plus_failed",
                "base_unknown", "plus_unknown", "reference_errors", "candidate_errors",
                "reference_unsupported_outputs", "candidate_unsupported_outputs")},
            "audit_seconds": execution.get("duration_seconds"),
            "public_execution_seconds": sum(entry["execution"].get("duration_seconds", 0)
                                            for entry in cache.records.values()),
        })
        write_immutable_json(record_path, record)
        return record

    try:
        health = pool.run({"probe.py": "def ping():\n    return True\n"}, "probe", "ping", [], {})
        if health.get("actual") is not True or health.get("status") != "observed":
            raise ValueError("Docker preflight ping failed")
        write_immutable_json(output / "sandbox_health.json", health)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pending = [executor.submit(inspect, row, "reference") for row in rows]
            for future in as_completed(pending):
                result = future.result()
                outcomes.append(result)
                if result["audit_status"] != "pass" or result["public_status"] != "pass" or len(outcomes) % 8 == 0:
                    print(json.dumps({"completed": len(outcomes), "task_id": result["task_id"],
                                      "audit": result["audit_status"], "public": result["public_status"]}), flush=True)
        first = rows[0]
        entry = first["task"].function
        controls = {
            "explicit_runtime_error": f"def {entry}(*args, **kwargs):\n    raise ValueError('engineering negative control')\n",
            "syntax_error": f"def {entry}(:\n    pass\n",
            "unsupported_output": f"def {entry}(*args, **kwargs):\n    return object()\n",
        }
        negatives = [inspect(first, label, code) for label, code in controls.items()]
    finally:
        pool.close()
    if manifest_path.read_bytes() != original_manifest_bytes:
        raise ValueError("Frozen manifest changed during engineering preflight")
    summary = seal({
        "version": "natural-engineering-preflight-v1", "engineering_only": True,
        "model_calls": 0, "manifest_hash": manifest["record_hash"], "task_count": len(rows),
        "partition": "development", "remote_repo": remote_repo, "executor": pool.identity,
        "transport": pool.transport_identity, "frozen_manifest_unchanged": True,
        "reference_h": dict(Counter(row["audit_status"] for row in outcomes)),
        "reference_public": dict(Counter(row["public_status"] for row in outcomes)),
        "reference_rows": sorted(outcomes, key=lambda row: row["task_id"]),
        "negative_controls": negatives, "wall_seconds": round(time.monotonic() - started, 3),
        "ready": all(row["audit_status"] == row["public_status"] == "pass" for row in outcomes)
                 and all(row["audit_status"] == row["public_status"] == "fail" for row in negatives),
    })
    write_immutable_json(summary_path, summary)
    return summary


def run_public(repo, frozen, output, remote_repo, workers=4):
    """Check every frozen public wrapper with its reference; never run H or a model.

    This validates adapter compatibility, not whether the reference satisfies
    every aspect of the natural-language contract. Results remain host-side.
    """
    manifest_path = frozen / "data_manifest.json"
    original = manifest_path.read_bytes()
    manifest = verify(json.loads(original))
    pool = ExecutorPool(remote_repo, workers)
    expected = {"manifest_hash": manifest["record_hash"], "executor": pool.identity,
                "transport": pool.transport_identity, "public_only": True}
    write_immutable_json(output / "protocol.json", seal(expected))
    rows = [row for part in manifest["splits"] for row in load_tasks(repo, manifest, part)]

    def inspect(row):
        task = row["public_task"]
        item = artifact(row, row["host_audit"]["reference_code"], "public-reference")
        suffix = task.contract.original_task_id.replace("/", "_")
        cache = ExecutionCache(pool, output / "execution" / suffix, max_executions=1)
        report = validate_callable(task, item, fixed_rubric(), cache)
        for receipt in cache.records.values():
            from skillopt.skill_validation.single_round import _healthy
            _healthy(receipt["execution"])
        write_immutable_json(output / "reports" / (suffix + ".json"), report)
        record = seal({"task_id": task.contract.original_task_id,
                       "partition": task.contract.partition, "status": report["status"],
                       "task_hash": task.content_hash, "report_hash": report["record_hash"],
                       "provenance_kind": "reference_compatibility_control"})
        write_immutable_json(output / "rows" / (suffix + ".json"), record)
        return record

    outcomes = []
    try:
        health = pool.run({"probe.py": "def ping():\n    return True\n"}, "probe", "ping", [], {})
        require(health.get("actual") is True and health.get("status") == "observed", "Sandbox unavailable")
        write_immutable_json(output / "sandbox_health.json", health)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for future in as_completed([executor.submit(inspect, row) for row in rows]):
                result = future.result()
                outcomes.append(result)
                if len(outcomes) % 16 == 0 or result["status"] != "pass":
                    print(json.dumps({"public_preflight_completed": len(outcomes), "total": len(rows),
                                      "task_id": result["task_id"], "status": result["status"]}), flush=True)
    finally:
        pool.close()
    require(manifest_path.read_bytes() == original, "Frozen panel changed")
    summary = seal({**expected, "version": "natural-public-compatibility-v1", "model_calls": 0,
                    "hidden_audit_executed": False, "task_count": len(rows),
                    "rows": sorted(outcomes, key=lambda r: (r["partition"], r["task_id"])),
                    "counts": dict(Counter(r["status"] for r in outcomes)),
                    "reference_pass_is_not_contract_truth": True})
    write_immutable_json(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--public-only", action="store_true",
                        help="All-partition public-wrapper compatibility; no H and no model calls")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    runner = run_public if args.public_only else run
    summary = runner(repo, repo / args.frozen, repo / args.output, args.remote_repo, args.workers)
    fields = ("task_count", "counts", "model_calls", "hidden_audit_executed") if args.public_only else (
        "ready", "task_count", "reference_h", "reference_public", "wall_seconds")
    print(json.dumps({key: summary[key] for key in fields}))


if __name__ == "__main__":
    main()
