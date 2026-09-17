"""Post-completion, same-response delivery sensitivity; never an online fix.

Only missing FILE terminators may be interpreted differently. No model call,
source rewriting, hidden-test repair, primary rescoring, or state transition is
performed. Candidate execution still uses the frozen, OS-isolated V3 executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v4 import runtime
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "coevolution-v4-same-response-delivery-sensitivity-v1"
_HEADER = re.compile(r"<<<FILE ([A-Za-z][A-Za-z0-9_]*\.py)>>>")
_HEX = re.compile(r"[0-9a-f]{64}")
EXECUTOR_SOURCES = (
    "skillopt/coevolution_v4/runtime.py", "skillopt/coevolution_v3/executor.py",
    "skillopt/coevolution/executor.py", "skillopt/validator_pilot/tasks.py",
)


def raw_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def recover_delivery(task: executor.RepoTask, raw: str) -> dict:
    """Conservative raw-block recovery, preserving module source bytes exactly.

    A missing END marker may be inferred only immediately before the next exact
    FILE header, or at end of response. This does not strip code fences, prose,
    protected modules, duplicate sections, unsafe imports, or invalid Python.
    """
    try:
        files = runtime.parse_delivery(task, raw)
        return {"files": files, "mode": "strict_unchanged", "implicit_boundaries": [],
                "raw_sha256": raw_hash(raw)}
    except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
        strict_error = str(exc)[:300]
    if not isinstance(raw, str) or len(raw) > executor.MAX_ARTIFACT_CHARS + 20000:
        raise ValueError("Recovery requires a bounded text response")
    patches, boundaries, current, source = {}, [], None, []

    def close(kind, line):
        nonlocal current, source
        if current is None:
            raise ValueError("Unexpected END FILE marker")
        code = "".join(source)
        if not code.strip():
            raise ValueError("Recovered module is empty")
        patches[current] = code
        if kind != "explicit":
            boundaries.append({"path": current, "boundary": kind, "line": line})
        current, source = None, []

    lines = raw.splitlines(keepends=True)
    for line_number, line in enumerate(lines, 1):
        token = line[:-1] if line.endswith("\n") else line
        header = _HEADER.fullmatch(token)
        if header:
            path = header.group(1)
            if current is not None:
                close("next_file_header", line_number)
            if path in patches:
                raise ValueError("Duplicate recovered module")
            if path not in task.editable_paths:
                raise ValueError("Undeclared or protected recovered module")
            current, source = path, []
        elif token == "<<<END FILE>>>":
            close("explicit", line_number)
        elif current is None:
            if line.strip():
                raise ValueError("Prose or fences outside file sections are not recoverable")
        else:
            if token.startswith("<<<") or token.startswith("```"):
                raise ValueError("Malformed delimiters or code fences are not recoverable")
            source.append(line)
    if current is not None:
        close("end_of_response", len(lines) + 1)
    if not patches or not boundaries:
        raise ValueError("No missing terminator can explain the strict failure")
    files = {**task.files, **patches}
    executor.validate_files(task, files)
    return {"files": files, "mode": "missing_end_marker_only", "implicit_boundaries": boundaries,
            "strict_error": strict_error, "raw_sha256": raw_hash(raw), "submitted_paths": sorted(patches)}


def _score(value):
    total = value.get("total_tests")
    return {"hard": value.get("hard"), "execution_ok": value.get("execution_ok") is True,
            "case_fraction": value.get("passed_tests", 0) / total if total else None,
            "passed_tests": value.get("passed_tests"), "total_tests": total,
            "error_category": value.get("error_category"),
            "error": value.get("delivery_error", value.get("safety_error"))}


def _evaluated(task, recovered, *, public_only):
    score = executor.evaluate(task, {"files": {p: recovered["files"][p] for p in task.editable_paths}},
                              public_only=public_only)
    return {**{k: v for k, v in recovered.items() if k != "files"},
            "format_ok": True, "artifact_hash": digest(recovered["files"]),
            "file_sha256": {p: raw_hash(code) for p, code in recovered["files"].items()},
            "score": _score(score)}


def _rejected(error):
    return {"format_ok": False, "artifact_hash": digest(None), "mode": "not_recoverable",
            "error": str(error)[:300], "score": {"hard": None, "execution_ok": False, "case_fraction": None}}


def audit_target(task, row, initial_ok: bool, revision_ok: bool) -> dict:
    """Audit the unchanged two returned strings; never regenerate the revision."""
    if type(initial_ok) is not bool or type(revision_ok) is not bool:
        raise ValueError("Original API availability must be explicit")
    if row.get("public_task_hash") != digest(task.public_task()) or row.get("id") != task.id:
        raise ValueError("Frozen task/target provenance mismatch")
    if row.get("artifact_hash") != digest(row.get("files")):
        raise ValueError("Original target artifact hash mismatch")
    first_raw, final_raw = row["initial_response"], row["revision_response"]
    initial_files = None
    if initial_ok:
        try:
            initial_files = runtime.parse_delivery(task, first_raw)
        except (ValueError, TypeError, SyntaxError, RecursionError):
            pass
    if initial_files != row["initial_evaluation"].get("files"):
        raise ValueError("Strict initial interpretation differs from the frozen runtime")
    initial_recovery = None
    if initial_ok and initial_files is None:
        try:
            initial_recovery = recover_delivery(task, first_raw)
            initial_report = _evaluated(task, initial_recovery, public_only=True)
        except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
            initial_report = _rejected(exc)
    else:
        initial_report = {"mode": "strict_unchanged" if initial_ok else "api_unavailable_excluded",
                          "format_ok": initial_files is not None, "artifact_hash": digest(initial_files),
                          "score": _score(row["initial_evaluation"])}
    base = replace(task, files=initial_files) if initial_files is not None else task
    original = {"format_ok": row.get("files") is not None, "artifact_hash": row["artifact_hash"],
                "score": _score(row["evaluation"])}
    if not revision_ok:
        recovered = {**_rejected("Original revision API was unavailable/truncated; text excluded"),
                     "mode": "api_unavailable_excluded"}
    elif final_raw.strip() == "KEEP":
        recovered = ({**original, "mode": "strict_keep_unchanged", "implicit_boundaries": []}
                     if initial_files is not None else {
                         **_rejected("KEEP after invalid initial artifact cannot invent a patch"),
                         "mode": "keep_after_invalid_initial_excluded"})
    else:
        try:
            parsed = recover_delivery(base, final_raw)
            if parsed["mode"] == "strict_unchanged":
                if parsed["files"] != row.get("files"):
                    raise ValueError("Strict final interpretation differs from the frozen runtime")
                recovered = {**original, "mode": "strict_unchanged", "implicit_boundaries": []}
            else:
                recovered = _evaluated(task, parsed, public_only=row["public_only"])
        except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
            recovered = _rejected(exc)
    recovered["base_interpretation"] = (
        "same_revision_prompt_strict_initial_files" if initial_files is not None
        else "same_revision_prompt_original_starter_initial_invalid"
    )
    counterfactual = None
    if initial_recovery is not None and revision_ok and final_raw.strip() != "KEEP":
        if initial_recovery["files"] != task.files:
            try:
                alternate = replace(task, files=initial_recovery["files"])
                counterfactual = _evaluated(task, recover_delivery(alternate, final_raw), public_only=row["public_only"])
            except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
                counterfactual = _rejected(exc)
            counterfactual["base_interpretation"] = "counterfactual_recovered_initial_files_not_seen_in_revision_prompt"
            counterfactual["new_trajectory"] = False
            counterfactual["revision_and_feedback_not_regenerated"] = True
    return {"task_id": task.id, "split": task.split,
            **{k: row.get(k) for k in ("job_hash", "stream", "stage", "repeat", "skill_hash", "request_hashes")},
            "skill_active": bool(row.get("skill")), "initial_api_ok": initial_ok, "revision_api_ok": revision_ok,
            "raw_sha256": {"initial": raw_hash(first_raw), "revision": raw_hash(final_raw)},
            "original": original, "initial_public_only_sensitivity": initial_report,
            "same_prompt_base_sensitivity": recovered,
            "counterfactual_recovered_initial_base": counterfactual,
            "primary_score_or_state_changed": False, "new_model_calls": 0}


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.hashes, self.complete = {}, False

    def read(self, relative, *, api=False):
        allowed = relative in {"results.json", "protocol.json", "tasks.json", "final_frozen.json", "final_alias_plan.json"}
        allowed = allowed or bool(re.fullmatch(r"decisions/r[0-9]+\.json", relative))
        allowed = allowed or bool(re.fullmatch(r"(?:targets|api/calls)/[0-9a-f]{64}\.json", relative))
        if not allowed or relative != "results.json" and not self.complete:
            raise ValueError("Unmet completion barrier or forbidden audit input")
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root) or any(p.is_symlink() for p in (path, *path.parents) if p != self.root and self.root in p.parents):
            raise ValueError("Symlinked or escaped audit input")
        raw = path.read_bytes()
        self.hashes[relative] = hashlib.sha256(raw).hexdigest()
        value = json.loads(raw)
        if api:
            if (value.get("request_hash") != path.stem or digest(value.get("request")) != path.stem
                    or type(value.get("ok")) is not bool):
                raise ValueError("Original API receipt identity mismatch")
            return value
        if set(value) != {"record", "record_hash"} or digest(value["record"]) != value["record_hash"]:
            raise ValueError("Frozen wrapped record integrity mismatch")
        return value["record"]

    def verify_unchanged(self):
        for relative, expected in self.hashes.items():
            if hashlib.sha256((self.root / relative).read_bytes()).hexdigest() != expected:
                raise ValueError("Frozen run changed during delivery sensitivity audit")


def pair_accounting(pairs, records):
    result = []
    for pair in pairs:
        left, right = records[pair["reference_job"]], records[pair["candidate_job"]]
        groups = {}
        for name, field in (("original_both_strict_valid", "original"),
                            ("same_prompt_base_both_recovered_valid", "same_prompt_base_sensitivity")):
            a, b = left[field], right[field]
            eligible = all(r["format_ok"] and r["score"]["execution_ok"] for r in (a, b))
            groups[name] = {"eligible": eligible,
                            "hard_delta": int(b["score"]["hard"]) - int(a["score"]["hard"]) if eligible else None,
                            "case_fraction_delta": b["score"]["case_fraction"] - a["score"]["case_fraction"] if eligible else None}
        result.append({**pair, **groups})
    return {"rows": result, "paired_rows": len(result),
            "conditional_selection_not_primary_performance": True,
            "counterfactual_recovered_initial_base_excluded": True,
            **{name: {"eligible_pairs": sum(r[name]["eligible"] for r in result),
                      "hard_gain_sum": sum(r[name]["hard_delta"] or 0 for r in result),
                      "case_fraction_delta_sum": sum(r[name]["case_fraction_delta"] or 0 for r in result)}
               for name in ("original_both_strict_valid", "same_prompt_base_both_recovered_valid")}}


def audit(run, *, repo=None):
    reader = Reader(run)
    results = reader.read("results.json")
    if results.get("status") != "complete":
        raise ValueError("Only a completed frozen V4 run may be audited")
    reader.complete = True
    protocol, raw_tasks = reader.read("protocol.json"), reader.read("tasks.json")
    if protocol.get("version") != "coevolution-v4-engineering-v1" or results.get("protocol_hash") != digest(protocol):
        raise ValueError("Completed run/protocol lineage mismatch")
    if digest(raw_tasks) != protocol.get("tasks_hash"):
        raise ValueError("Frozen task manifest mismatch")
    frozen = reader.read("final_frozen.json")
    if frozen.get("protocol_hash") != digest(protocol) or frozen.get("freeze_before_final") is not True:
        raise ValueError("Final freeze provenance mismatch")
    repo = Path(repo).resolve() if repo else Path(__file__).resolve().parents[1]
    source_hashes = {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in EXECUTOR_SOURCES}
    if any(protocol.get("source_hashes", {}).get(name) != value for name, value in source_hashes.items()):
        raise ValueError("Frozen execution implementation changed; audit refused")
    probe = executor.sandbox_probe()
    if probe.get("ok") is not True:
        raise RuntimeError("OS sandbox unavailable; no candidate may execute")
    tasks = {identifier: executor.RepoTask.from_dict(value) for identifier, value in raw_tasks.items()}
    records, source_records = {}, {}
    for path in sorted((reader.root / "targets").glob("*.json")):
        if not _HEX.fullmatch(path.stem):
            raise ValueError("Unexpected target record path")
        row = reader.read("targets/" + path.name)
        job = {k: row[k] for k in ("id", "skill", "stream", "stage", "repeat")}
        if digest(job) != path.stem or row.get("job_hash") != path.stem or row.get("skill_hash") != digest(row["skill"]):
            raise ValueError("Target identity is not its frozen job")
        hashes = row["request_hashes"]
        if len(hashes) != 2 or any(not isinstance(h, str) or not _HEX.fullmatch(h) for h in hashes):
            raise ValueError("Two original API request receipts required")
        calls = [reader.read(f"api/calls/{h}.json", api=True) for h in hashes]
        if calls[0].get("response") != row["initial_response"] or calls[1].get("response") != row["revision_response"]:
            raise ValueError("Target strings differ from original returned API text")
        records[path.stem] = audit_target(tasks[row["id"]], row, calls[0]["ok"], calls[1]["ok"])
        source_records[path.stem] = row
    pairs = []
    for round_index in protocol["rounds"]:
        decisions = reader.read(f"decisions/r{round_index}.json")
        for branch, decision in decisions.items():
            for group, group_pairs in decision["pairs"].items():
                arm = "approved" if group == "scope" else "working"
                parent = decision["learning_before"]["approved_deployed" if group == "scope" else "working_local"]
                for pair in group_pairs:
                    common = {"id": pair["id"], "stream": decision["stream"], "stage": f"r{round_index}", "repeat": pair["repeat"]}
                    candidate_key = digest({**common, "skill": decision["candidate"]["content"]})
                    for reference, text in (("base", ""), (arm, parent)):
                        pairs.append({"branch": branch, "round": round_index, "group": group,
                                      "task_id": pair["id"], "repeat": pair["repeat"], "reference_arm": reference,
                                      "reference_job": digest({**common, "skill": text}), "candidate_job": candidate_key})
    aliases = reader.read("final_alias_plan.json")
    final_base = {(source_records[a["job_hash"]]["id"], source_records[a["job_hash"]]["stream"],
                   source_records[a["job_hash"]]["repeat"]): a["job_hash"] for a in aliases if a["arm"] == "noskill"}
    for alias in aliases:
        if alias["arm"] == "noskill":
            continue
        row = source_records[alias["job_hash"]]
        pairs.append({"branch": f"s{row['stream']}_{alias['arm']}", "round": "final", "group": "final",
                      "task_id": row["id"], "repeat": row["repeat"], "reference_arm": "noskill",
                      "reference_job": final_base[row["id"], row["stream"], row["repeat"]], "candidate_job": alias["job_hash"]})
    changed = [r for r in records.values() if r["same_prompt_base_sensitivity"]["mode"] == "missing_end_marker_only"]
    report = {"version": VERSION, "run": str(reader.root), "protocol_hash": digest(protocol),
              "post_completion_only": True, "primary_scores_states_or_protocol_changed": False,
              "new_model_calls": 0, "new_trajectories": False, "same_returned_text_only": True,
              "strict_unchanged_scores_not_rerun": True, "sandbox_probe": probe,
              "executor_source_sha256": source_hashes,
              "summary": {"unique_original_target_jobs": len(records),
                          "recovery_modes": dict(Counter(r["same_prompt_base_sensitivity"]["mode"] for r in records.values())),
                          "missing_terminator_recovered_jobs": len(changed),
                          "recovered_hard_pass_jobs": sum(r["same_prompt_base_sensitivity"]["score"]["hard"] is True for r in changed),
                          "initial_base_counterfactual_jobs": sum(r["counterfactual_recovered_initial_base"] is not None for r in records.values())},
              "targets": records, "conditional_pair_accounting": pair_accounting(pairs, records),
              "limitations": ["Posthoc diagnostic, not a corrected benchmark or replacement training result.",
                              "Original optimizer feedback, proposals, gates, working and approved Skills remain unchanged.",
                              "Recovered-initial-base rows are a stronger counterfactual: the revision saw different current_files and feedback.",
                              "Conditional-valid pair subsets are selected and cannot establish generalization or safety.",
                              "Only missing END markers are recoverable; truncated API results, invalid Python, prose and protected edits remain excluded."]}
    reader.verify_unchanged()
    report["source_artifact_sha256"] = dict(sorted(reader.hashes.items()))
    report["audit_sha256"] = digest(report)
    return report


def publish(report, output):
    output, run = Path(output).resolve(), Path(report["run"]).resolve()
    if output.is_relative_to(run):
        raise ValueError("Delivery audit output must be outside the frozen run")
    write_immutable_json(output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Immutable JSON report outside the frozen run")
    args = parser.parse_args()
    report = audit(args.run)
    publish(report, args.output)
    print(json.dumps({"output": str(args.output.resolve()), **report["summary"], "primary_results_changed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
