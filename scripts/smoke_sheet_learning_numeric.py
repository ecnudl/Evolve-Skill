"""Zero-API, opt-in replay of one frozen learning workbook with numeric views.

This is a compatibility diagnostic, not a resumed optimizer or a new candidate.
The original evaluation/manifest/panel are read-only, with new private scorer
receipts and a small result summary. No reference content is published.
"""
from __future__ import annotations

import argparse
import fcntl
import json

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import sheet_numeric_adapter as scorer
from skillopt.continual_eval import sheet_recalc as recalc
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest


def run(evaluation, panel, qualification, output, native_lock):
    evaluation, panel, qualification, output, native_lock = map(
        safe_path, (evaluation, panel, qualification, output, native_lock))
    require(native_lock.is_file(), "Existing shared native lock required")
    require(not output.exists(), "New smoke output directory required")
    original = read_json(evaluation, sealed=True)
    manifest_path = evaluation.parent.parent.parent / "manifest.json"
    manifest = read_json(manifest_path, sealed=True)
    request = original["request"]
    require(request["manifest_hash"] == manifest["record_hash"]
            and request["benchmark"] == manifest["benchmark"] == "spreadsheetbench"
            and evaluation.stem == digest(request), "Frozen learning evaluation binding differs")
    tasks = read_json(panel)["tasks"]
    matches = [task for task in tasks if digest(task) == request["task_hash"]]
    require(len(matches) == 1, "Exactly one frozen source task required")
    task = matches[0]
    require(task["partition"] == "development"
            and manifest["authorized_tasks"].get(digest(task)) == request["role"], "Unauthorized source task")
    require(all(value.get("status") == "ready" and recalc.sha(path) == value.get("sha256")
                for path, value in manifest["asset_identity"].items()),
            "Frozen learning assets changed")
    q = read_json(qualification, sealed=True)
    runtime = {**manifest["runtime"], "spreadsheet_scorer": scorer.VERSION, "recalculation": {
        "image": q["engine"]["image_id"], "timeout_seconds": q["engine"]["timeout_seconds"],
        "qualification_path": str(qualification), "qualification_sha256": recalc.sha(qualification),
        "qualification_hash": q["record_hash"]}}
    scorer.qualified_engine(runtime)
    snapshot = {str(p): recalc.sha(p) for p in (evaluation, panel, manifest_path, qualification)}
    replay_request = {"benchmark": "spreadsheetbench", "source_evaluation_hash": original["record_hash"],
                      "qualification_hash": q["record_hash"], "scorer": scorer.VERSION}
    key = digest(replay_request)
    runtime["_score_context"] = {"artifact_dir": str(output / "host_only/scorer_artifacts" / key),
        "position": key, "request": replay_request, "prediction_hash": digest(original["prediction"])}
    output.mkdir(parents=True, mode=0o700)
    with output_lock(output):
        write_json(output / "protocol.json", seal({"version": "sheet-learning-numeric-smoke-v1",
            "evidence_kind": "historical_replay", "sources": snapshot, "runtime": runtime,
            "script_sha256": recalc.sha(__file__), "native_lock": str(native_lock),
            "original_score_changed": False, "model_api_calls": 0}))
        with native_lock.open("rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            result = scorer.score(task["public"], task["private"], original["prediction"], runtime=runtime)
        require(scorer.score(task["public"], task["private"], original["prediction"], runtime=runtime,
                             replay_only=True) == result, "Repeated scoring evidence differs")
        require(all(recalc.sha(path) == value for path, value in snapshot.items()), "Historical source changed")
        summary = seal({"version": "sheet-learning-numeric-smoke-v1", "evidence_kind": "historical_replay",
            "source_evaluation_hash": original["record_hash"], "task_hash": digest(task),
            "qualification_hash": q["record_hash"], "scorer_profile": scorer.VERSION,
            "before": {"status": original["score"]["status"], "reasons": [c["reason"] for c in
                       original["score"].get("metrics", {}).get("cases", [])]},
            "after": {"status": result["status"], "reasons": [c["reason"] for c in result["metrics"]["cases"]]},
            "execution_costs": result["execution_costs"], "cleanup_confirmed": result["cleanup_confirmed"],
            "cached_replay_equal": True, "model_api_calls": 0, "original_score_changed": False,
            "optimizer_resumed": False, "reference_answer_exposed_to_learner": False})
        write_json(output / "result.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("evaluation", "panel", "qualification", "output", "native-lock"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.evaluation, args.panel, args.qualification, args.output, args.native_lock)))


if __name__ == "__main__":
    main()
