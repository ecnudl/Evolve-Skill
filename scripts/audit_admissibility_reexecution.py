"""Offline identity-bound comparison of original and admitted executions.

Only the standard library is used. No model, benchmark program, subprocess,
network or hidden answer is executed. Default mode requires a completed study;
--partial explicitly reports incomplete coverage while a study is running.
Hashes are consistency checks, not proof against an adversarial host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

VERSION = "admissibility-reexecution-audit-v1"
ARMS = ("adaptive_no_research", "adaptive_research")
PARTITIONS = ("verifier_calibration", "skill_confirmation")
FIELDS = ("actual", "before_args", "after_args", "before_kwargs", "after_kwargs", "exception")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def seal(value):
    require("record_hash" not in value, "Already sealed")
    return {**value, "record_hash": digest(value)}


def verify(value):
    require(type(value) is dict and value.get("record_hash") == digest(
        {k: v for k, v in value.items() if k != "record_hash"}), "Evidence checksum mismatch")
    return value


def checked(path):
    path = Path(path).absolute()
    require(".." not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)),
            "Unsafe or symlink evidence path")
    return path


def read(path):
    path = checked(path)
    require(path.stat().st_size <= 32_000_000, "Oversized evidence record")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("Nonfinite JSON")
    return verify(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=constant))


def hash_path(root, name):
    require(type(name) is str and re.fullmatch(r"[0-9a-f]{64}", name), "Invalid evidence identity")
    return checked(root) / (name + ".json")


def observation(execution, call):
    """Reconstruct only the public observation fields used by task_probes."""
    public = {field: None for field in FIELDS}
    require(execution["status"] in {"observed", "unsupported", "execution_error"}, "Unknown executor status")
    if execution["status"] != "observed":
        return public, "unknown", execution.get("reason", "execution_unavailable")
    if execution.get("cleanup_confirmed") is not True:
        return public, "unknown", "isolation_cleanup_not_confirmed"
    public.update({field: execution[field] for field in FIELDS if field in execution})
    if not all(field in execution for field in FIELDS):
        return public, "unknown", "missing_observation_fields"
    if not (type(public["before_args"]) is type(public["after_args"]) is list
            and type(public["before_kwargs"]) is type(public["after_kwargs"]) is dict):
        return public, "unknown", "unavailable_input_state"
    require(digest({"args": public["before_args"], "kwargs": public["before_kwargs"]}) == digest(call),
            "Execution before-state differs from proposed call")
    if public["exception"] is not None:
        return public, "unknown", "call_raised_exception"
    return public, "observed", "bounded_call_observed"


def checked_report(report, execution_root, artifact):
    """Check proposal, artifact, intent, terminal and projected observations."""
    verify(report)
    request = report["request"]
    require(request["artifact_record_hash"] == artifact["record_hash"] == report["artifact_record_hash"]
            and request["task_hash"] == artifact["task_hash"] == report["task_hash"], "Wrong artifact/task report")
    proposal = read(hash_path(execution_root / "proposals", request["proposal_hash"]))
    require(request["proposal_hash"] == report["proposal_hash"] == proposal["record_hash"]
            and request["pipeline_hash"] == report["pipeline_hash"] == proposal["pipeline_hash"]
            and request["callable_task_hash"] == proposal["callable_task_hash"]
            and proposal["task_hash"] == artifact["task_hash"], "Wrong proposal/callable report")
    require(len(report["probes"]) == len(proposal["probes"]), "Incomplete report probes")
    files = {f["path"]: f["content"] for f in artifact["files"]}
    result = []
    for index, (probe, row) in enumerate(zip(proposal["probes"], report["probes"])):
        observations, executions, references = [], [], []
        require(row["probe_index"] == index and row["probe"] == probe, "Changed report probe")
        for call_index, call in enumerate(probe["calls"]):
            call_request = {**request, "probe_index": index, "call_index": call_index, "call": call}
            key = digest(call_request)
            terminal = read(hash_path(execution_root / "calls", key))
            require(read(hash_path(execution_root / "intents", key)) == seal({"request": call_request})
                    and terminal["request"] == call_request, "Wrong execution intent/terminal")
            execution = verify(terminal["execution"])
            require(execution["source_hash"] == digest(files)
                    and execution["executor_identity"] == request["executor_identity"]
                    and type(terminal["execution_performed"]) is bool, "Wrong executor/source identity")
            public, state, reason = observation(execution, call)
            observations.append({"call_index": call_index, "status": state, "reason": reason,
                "execution_performed": terminal["execution_performed"], "execution_ref": execution["record_hash"],
                "receipt_ref": terminal["record_hash"], "public_observation": public})
            executions.append({key: execution[key] for key in ("input_hash", "source_hash", "call_hash")})
            references.append(terminal["record_hash"])
        status = "unknown"
        if all(o["status"] == "observed" for o in observations):
            expected = probe["expected"] if probe["kind"] == "expected" else observations[1]["public_observation"]["actual"]
            status = "match" if digest(observations[0]["public_observation"]["actual"]) == digest(expected) else "mismatch"
        require(row["observations"] == observations and row["evidence_refs"] == references
                and row["status"] == status, "Projected observation or check status mismatch")
        result.append({"probe": probe, "status": status, "observations": observations, "executions": executions})
    states = [row["status"] for row in result]
    expected = "mismatch" if "mismatch" in states else "unknown" if not states or "unknown" in states else "match"
    require(report["status"] == expected, "Incorrect aggregate probe status")
    return proposal, result


def audit(source, study, *, partial=False):
    source, study = checked(source), checked(study)
    protocol, original_protocol = read(study / "protocol.json"), read(source / "protocol.json")
    original_result = read(source / "results.json")
    require(protocol["version"] == "pre-execution-admissibility-study-v1"
            and checked(protocol["source_root"]) == source
            and protocol["source_result_hash"] == original_result["record_hash"]
            and protocol["source_protocol_hash"] == original_protocol["record_hash"]
            and original_result["protocol_hash"] == original_protocol["record_hash"], "Study/source identity mismatch")
    require(protocol["final_access"] is False and protocol["feedback_authorized"] is False
            and protocol["deployment_authorized"] is False, "Only no-final shadow study is supported")
    terminal = read(study / "results.json") if (study / "results.json").exists() else None
    require(partial or terminal is not None, "Completed results.json required; use --partial explicitly")
    if terminal:
        require(terminal["protocol_hash"] == protocol["record_hash"], "Study results belong to another protocol")
    natural = checked(original_protocol["source_root"])
    totals, arms, differences, completed = Counter(), {}, [], True
    for arm in ARMS:
        old_index, expected = {}, {}
        for part in PARTITIONS:
            for row in read(source / "host_only" / (arm + "_" + part + ".json"))["rows"]:
                if row["artifact_hash"] is not None:
                    require(row["artifact_hash"] not in expected, "Duplicate expected artifact")
                    expected[row["artifact_hash"]] = row
        for path in sorted((source / "probe_execution" / arm / "reports").glob("*.json")):
            report = read(path)
            require(report["request"]["executor_identity"] == original_protocol["executor"], "Wrong source executor")
            artifact_id = report["artifact_record_hash"]
            require(artifact_id in expected and expected[artifact_id]["report_hash"] == report["record_hash"],
                    "Original report is not bound to the frozen source row")
            require(artifact_id not in old_index, "Duplicate original report")
            old_index[artifact_id] = report
        counts, seen = Counter(expected_admitted_records=len(expected)), set()
        # Capture admitted records before reviews: a running study publishes its
        # review first, so every captured record must already have its reviewer.
        admitted_paths = sorted((study / "admitted_execution" / arm / "admitted").glob("*.json"))
        reviews = {}
        for path in sorted((study / "reviews" / arm).glob("*.json")):
            review = read(path)
            require(path.stem == digest(review["binding"]), "Review cache filename mismatch")
            reviews[review["record_hash"]] = review
        for path in admitted_paths:
            admitted = read(path)
            artifact_id = admitted["artifact_hash"]
            require(artifact_id in expected and artifact_id not in seen, "Unexpected/duplicate admitted artifact")
            seen.add(artifact_id)
            pipeline = digest({"protocol": protocol["record_hash"], "historical_generator": arm})
            require(admitted["pipeline_hash"] == pipeline and path.stem == digest(
                [pipeline, admitted["review_hash"], artifact_id]), "Admitted pipeline or filename mismatch")
            artifact = read(hash_path(natural / "artifacts", artifact_id))
            require(artifact["record_hash"] == artifact_id, "Artifact filename identity mismatch")
            frozen = read(hash_path(source / "probes" / arm, artifact["task_hash"]))
            original = verify(frozen["proposal"])
            require(frozen["record_hash"] == expected[artifact_id]["proposal_hash"]
                    and original["record_hash"] == admitted["original_proposal_hash"]
                    and original["task_hash"] == artifact["task_hash"]
                    and original["callable_task_hash"] == admitted["task_hash"], "Wrong artifact/proposal identity")
            review = reviews.get(admitted["review_hash"])
            require(review is not None, "Missing admitted review")
            prepared = verify(review["inventory"])
            require(review["binding"]["pipeline_hash"] == pipeline
                    and review["binding"]["inventory_hash"] == prepared["record_hash"]
                    and prepared["proposal_hash"] == original["record_hash"]
                    and prepared["task_hash"] == admitted["task_hash"], "Review/proposal identity mismatch")
            kept = {d["probe_id"] for d in review["decisions"] if d["decision"] == "keep"}
            selected = [item for item in prepared["items"] if item["probe_id"] in kept]
            require(admitted["retained_ids"] == [item["probe_id"] for item in selected]
                    and admitted["retained_checks"] == len(selected), "Admitted selection differs from review")
            require(all(item["probe_id"] == "p-" + digest({"task": admitted["task_hash"], "probe": item["probe"]})
                    and item["probe"] in original["probes"] for item in selected), "Retained check content identity mismatch")
            counts["completed_admitted_records"] += 1
            report = admitted["execution_report"]
            if report is None:
                require(admitted["probe_status"] == "not_executed" and admitted["retained_checks"] == 0,
                        "Absent execution cannot imply checked correctness")
                counts["not_executed_records"] += 1
                continue
            require(report["request"]["executor_identity"] == protocol["executor"], "Wrong new executor")
            new_root = study / "admitted_execution" / arm / "execution"
            require(read(hash_path(new_root / "reports", digest(report["request"]))) == report,
                    "Embedded execution differs from durable report")
            new_proposal, new_rows = checked_report(report, new_root, artifact)
            require(artifact_id in old_index, "Admitted check has no original execution")
            old_proposal, old_rows = checked_report(old_index[artifact_id], source / "probe_execution" / arm, artifact)
            require(admitted["original_proposal_hash"] == old_proposal["record_hash"]
                    and admitted["filtered_proposal_hash"] == new_proposal["record_hash"]
                    and new_proposal["probes"] == [item["probe"] for item in selected]
                    and admitted["task_hash"] == new_proposal["callable_task_hash"]
                    and admitted["retained_checks"] == len(new_rows)
                    and admitted["probe_status"] == report["status"], "Admitted proposal identity mismatch")
            counts["executed_artifact_records"] += 1
            for new in new_rows:
                matches = [old for old in old_rows if old["probe"] == new["probe"]]
                require(matches, "A newly admitted check was not in the original proposal")
                counts["fresh_probe_instances"] += 1
                for old in matches:
                    require(old["executions"] == new["executions"], "Reexecution input/source/call identities differ")
                    changed = []
                    if old["status"] != new["status"]:
                        changed.append("check_status")
                    for index, (before, after) in enumerate(zip(old["observations"], new["observations"])):
                        for field in ("status", "reason", "execution_performed"):
                            if before[field] != after[field]:
                                changed.append(f"call_{index}.{field}")
                        for field in FIELDS:
                            if digest(before["public_observation"][field]) != digest(after["public_observation"][field]):
                                changed.append(f"call_{index}.{field}")
                    counts["compared_probe_pairs"] += 1
                    counts["compared_call_pairs"] += len(new["observations"])
                    counts["changed_probe_pairs" if changed else "identical_probe_pairs"] += 1
                    if changed:
                        host = expected[artifact_id]
                        differences.append({"arm": arm, "task_id": host["task_id"], "partition": host["partition"],
                            "artifact_hash": artifact_id, "probe_hash": digest(new["probe"]), "changed_fields": changed,
                            "old_probe_status": old["status"], "new_probe_status": new["status"],
                            "old_report_hash": old_index[artifact_id]["record_hash"], "new_report_hash": report["record_hash"]})
        counts["pending_admitted_records"] = len(expected) - len(seen)
        for key in ("completed_admitted_records", "executed_artifact_records", "not_executed_records",
                    "fresh_probe_instances", "compared_probe_pairs", "compared_call_pairs",
                    "identical_probe_pairs", "changed_probe_pairs"):
            counts.setdefault(key, 0)
        completed = completed and seen == set(expected)
        arms[arm] = dict(counts)
        totals.update(counts)
    require(partial or completed, "Completed study is missing admitted artifact records")
    return seal({"version": VERSION, "source_result_hash": original_result["record_hash"],
        "study_protocol_hash": protocol["record_hash"], "study_result_hash": terminal["record_hash"] if terminal else None,
        "requested_mode": "partial" if partial else "complete", "study_terminal_present": terminal is not None,
        "comparison_complete": terminal is not None and completed, "totals": dict(totals), "arms": arms,
        "differences": differences, "generated_code_executed": False, "model_calls": 0,
        "interpretation": "Common retained-check execution consistency only; no verdict on check admissibility or Skill benefit.",
        "limitations": ["Discarded probes have no new execution and are not compared.",
                        "Repeated original duplicates produce separate comparison pairs, not independent tasks.",
                        "A partial run is not a complete study result; no private code, expected value or answer is printed."]})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit(args.source, args.study, partial=args.partial)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = checked(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            require(read(output) == result, "Audit output already exists with different content")
        else:
            with output.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
