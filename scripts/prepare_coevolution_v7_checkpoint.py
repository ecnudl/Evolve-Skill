"""Offline, whole-final-stage exclusion and pause checkpoint for one V7 shape.

Planning is read-only. Applying copies pre-final evidence byte-for-byte into a
new fork, verifies it, then moves the entire original run to an archive. Nothing
is deleted or rescored. No API/client, credentials, or native oracle is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import audit_coevolution_v7 as audit  # noqa: E402
from skillopt.coevolution_v5 import core  # noqa: E402
from skillopt.validator_pilot.api import digest, write_immutable_json  # noqa: E402

VERSION = "v7-whole-final-sleep-exclusion-checkpoint-v1"
SLEEP_START = "2026-09-11T16:39:33+08:00"
ROOT_KEEP = {"protocol.json", "panel.json", "calibration_manifest.json", "private_preflight.json",
             "private_final_preflight.json", "research_inputs.json", "research_selection.json",
             "skills_frozen.json", "validator_candidate_frozen.json", "validator_activation.json", "final_frozen.json"}
ROOT_EXCLUDE = {"final_rows.json", "final_summary.json", "results.json"}
KEEP_DIRS = {"feedback_probes", "skill_proposals", "source_initial", "source_next", "research"}
API_CONFIG = {"api/service.json", "api/budget_protocol.json", "api/pacing/protocol.json"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(path, *, sealed=False):
    value = audit.prior._json(path)
    return core.verify(value) if sealed else value


def _payload(path):
    return {k: v for k, v in _json(path, sealed=True).items() if k != "record_hash"}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _safe_path(path):
    path = Path(path).absolute()
    _require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink path is forbidden")
    return path.resolve()


def _files(root):
    """Enumerate regular files only, rejecting symlinks and unresolved writes."""
    root = _safe_path(root)
    _require(root.is_dir(), "Existing source directory required")
    pending, result = [root], {}
    while pending:
        path = pending.pop()
        _require(not path.is_symlink(), "Symlink inside evidence tree is forbidden")
        _require(not path.name.startswith((".env", ".pending", ".lock")) and path.name != ".git",
                 "Credentials or unresolved write artifacts cannot enter a checkpoint")
        if path.is_dir():
            pending.extend(path.iterdir())
        else:
            _require(path.is_file(), "Only regular evidence files may be copied")
            result[str(path.relative_to(root))] = _sha(path)
    return dict(sorted(result.items()))


def _paths(repo, source, checkpoint, archive):
    repo, source, checkpoint, archive = map(_safe_path, (repo, source, checkpoint, archive))
    parent = repo / "outputs/coevolution_v7"
    _require(repo.is_dir() and source.parent == parent and checkpoint.parent == parent
             and archive.parent == parent / "quarantined", "Explicit V7 source/checkpoint/quarantined archive paths required")
    paths = (source, checkpoint, archive)
    _require(len(set(paths)) == 3 and not any(a.is_relative_to(b) for a in paths for b in paths if a != b),
             "Source, checkpoint and archive must be distinct and non-nested")
    _require(source.is_dir() and not checkpoint.exists() and not archive.exists(),
             "Existing source and absent destinations required; never overwrite or merge")
    return repo, source, checkpoint, archive


def _clock(value):
    _require(isinstance(value, str), "Explicit timezone-aware sleep boundary required")
    stamp = datetime.fromisoformat(value)
    _require(stamp.utcoffset() is not None and stamp.timestamp() == datetime.fromisoformat(SLEEP_START).timestamp(),
             "This isolated operation requires the fixed observed 2026-09-11 sleep boundary")
    return stamp.timestamp()


def _partition(source, manifest, sleep_wall):
    protocol = _payload(source / "protocol.json")
    result = _payload(source / "results.json")
    panel = _payload(source / "panel.json")
    _require(protocol["version"] == audit.experiment.VERSION and protocol["histories"] == 2 and protocol["blocks"] == 4
             and {p: len(v) for p, v in panel.items()} == {"development": 3, "calibration": 6, "final": 18},
             "Only the exact completed two-history V7 panel is supported")
    _require(result["status"] == "complete" and result["calibration"] is None
             and result["research"]["proposed_rubric"] is None and result["research"]["calls_used"] == 1,
             "This checkpoint is only for the completed invalid-Research/no-calibration V7 branch")
    _require(_payload(source / "final_frozen.json")["final_results_known"] is False,
             "Final interventions must have been frozen before final outcomes")
    calls = {Path(p).stem: _json(source / p) for p in manifest if p.startswith("api/calls/")}
    reservations = {Path(p).stem: _json(source / p) for p in manifest if p.startswith("api/budget_reservations/")}
    _require(len(calls) == 197 and calls.keys() == reservations.keys(), "Expected 197 complete logical requests and reservations")
    for h, row in calls.items():
        _require(row["request_hash"] == digest(row["request"]) == h and type(row["ok"]) is bool,
                 "Logical request identity changed")
        _require(reservations[h]["request_hash"] == h and reservations[h]["kind"] == row["request"]["kind"],
                 "Logical request reservation mismatch")
    target_paths, target_calls = {"development": [], "final": []}, {"development": set(), "final": set()}
    for relative in manifest:
        if not relative.startswith("targets/"):
            continue
        row = _payload(source / relative)
        identity, solver = row["identity"], row["result"]
        phase = identity.get("phase")
        _require(phase in target_paths and identity.get("kind") == "v7_solve"
                 and Path(relative).stem == digest({"namespace": "targets", "identity": identity}),
                 "Unknown target stage or cache identity")
        hashes = solver["request_hashes"]
        _require(len(hashes) == len(set(hashes)) == 2 and set(hashes) <= calls.keys(), "Each target needs two complete requests")
        _require(not target_calls[phase].intersection(hashes), "Repeated target requests do not count as new trajectories")
        target_paths[phase].append(relative)
        target_calls[phase].update(hashes)
    _require({p: len(v) for p, v in target_paths.items()} == {"development": 18, "final": 72}
             and len(target_calls["development"]) == 36 and len(target_calls["final"]) == 144
             and not target_calls["development"].intersection(target_calls["final"]), "Whole source/final target partition changed")
    other = calls.keys() - target_calls["development"] - target_calls["final"]
    _require(Counter(calls[h]["request"]["kind"] for h in other)
             == {"v5_validator_probe": 12, "v7_skill": 4, "v7_rubric_plan": 1}, "Unexplained or different pre-final requests")
    retained = target_calls["development"] | other
    excluded = target_calls["final"]
    _require(len(retained) == 53 and retained | excluded == calls.keys(), "Incomplete logical request partition")
    admissions, attempts, cooldowns = {}, {}, {}
    for relative in manifest:
        parts = Path(relative).parts
        if len(parts) == 4 and parts[:2] == ("api", "pacing") and parts[2] in {"admissions", "attempts", "cooldowns"}:
            row = _json(source / relative, sealed=True)
            sequence = row["sequence"]
            _require(type(sequence) is int and Path(relative).stem == f"{sequence:08d}", "Pacing sequence mismatch")
            {"admissions": admissions, "attempts": attempts, "cooldowns": cooldowns}[parts[2]][sequence] = row
    _require(set(admissions) == set(attempts) == set(range(1, 229)) and set(cooldowns) <= set(admissions),
             "The complete 228-attempt original pacing grid is required")
    prefix = {n for n, r in admissions.items() if r["request_hash"] in retained}
    _require(prefix == set(range(1, 56)), "Retained attempts must form the complete 1–55 prefix, without final interleaving")
    referenced = []
    for h, receipt in calls.items():
        sequence = [r["sequence"] for r in receipt["pacing"]["attempts"]]
        _require(len(sequence) == receipt["http_attempt_count"] and all(
            n in admissions and admissions[n]["request_hash"] == attempts[n]["request_hash"] == h
            for n in sequence), "Logical receipt does not bind its complete pacing attempts")
        referenced.extend(sequence)
    _require(len(referenced) == len(set(referenced)) == 228, "Unreferenced or duplicate HTTP attempts")
    for n in prefix:
        end, start = attempts[n].get("finished_wall"), admissions[n].get("admitted_wall")
        _require(type(end) in {int, float} and type(start) in {int, float}
                 and math.isfinite(end) and math.isfinite(start) and start <= end < sleep_wall,
                 "All retained attempt admissions and completions must precede the sleep boundary")
        _require(attempts[n]["admission_hash"] == admissions[n]["record_hash"], "Pacing receipt identity mismatch")
    _require(any(attempts[n]["finished_wall"] >= sleep_wall for n in attempts if n not in prefix),
             "The excluded final stage does not overlap the supplied sleep boundary")
    keep = set(ROOT_KEEP) | API_CONFIG | set(target_paths["development"])
    for relative in manifest:
        parts = Path(relative).parts
        if parts[0] in KEEP_DIRS:
            keep.add(relative)
        elif parts[:2] in {("api", "calls"), ("api", "budget_reservations")} and Path(relative).stem in retained:
            keep.add(relative)
        elif len(parts) == 4 and parts[:2] == ("api", "pacing") and parts[2] in {"admissions", "attempts", "cooldowns"}:
            if int(Path(relative).stem) in prefix:
                keep.add(relative)
    _require(keep <= manifest.keys(), "Missing required retained metadata or API configuration")
    allowed = ROOT_KEEP | ROOT_EXCLUDE
    for relative in manifest:
        parts = Path(relative).parts
        _require((len(parts) == 1 and relative in allowed) or parts[0] in KEEP_DIRS | {"targets"}
                 or relative in API_CONFIG or len(parts) == 3 and parts[:2] in {("api", "calls"), ("api", "budget_reservations")}
                 or len(parts) == 4 and parts[:2] == ("api", "pacing") and parts[2] in {"admissions", "attempts", "cooldowns"},
                 "Unexpected source files require explicit review, not implicit copying")
    _require(ROOT_EXCLUDE <= manifest.keys() and not ROOT_EXCLUDE.intersection(keep), "Final result files must be wholly excluded")
    return {"retained_files": sorted(keep), "excluded_files": sorted(manifest.keys() - keep),
        "inherited_request_hashes": sorted(retained), "excluded_final_request_hashes": sorted(excluded),
        "inherited_target_count": 18, "excluded_final_target_count": 72,
        "inherited_http_sequences": sorted(prefix), "excluded_final_http_sequences": sorted(set(attempts) - prefix),
        "inherited_terminal_error_hashes": sorted(h for h in retained if not calls[h]["ok"]),
        "latest_inherited_finished_wall": max(attempts[n]["finished_wall"] for n in prefix),
        "original_cost_ledger": result["ledger"], "original_result_record_hash": _json(source / "results.json")["record_hash"]}


def plan(repo, source, checkpoint, archive, sleep_start=SLEEP_START):
    """Read-only exact copy/exclusion plan; complete audit never executes artifacts."""
    repo, source, checkpoint, archive = _paths(repo, source, checkpoint, archive)
    sleep_wall = _clock(sleep_start)
    manifest = _files(source)
    report = audit.audit(source, repo=repo, require_complete=True)
    core.verify(report)
    _require(report["complete"] is True, "Original complete offline audit required")
    partition = _partition(source, manifest, sleep_wall)
    _require(_files(source) == manifest, "Source changed while preparing the checkpoint plan")
    original_fork = digest({"source_manifest": manifest, "source_path": str(source)})
    fork = digest({"parent_fork_id": original_fork, "checkpoint_path": str(checkpoint), "sleep_start": sleep_start,
                   "policy": "whole_final_stage_restart"})
    return core.seal({"version": VERSION, "repo": str(repo), "source": str(source), "checkpoint": str(checkpoint),
        "archive": str(archive), "sleep_start": sleep_start, "sleep_start_wall": sleep_wall,
        "sleep_boundary_evidence": "operator-supplied Clamshell Sleep system-log time; script verifies receipt clocks only",
        "source_manifest": manifest, "source_manifest_hash": digest(manifest), "complete_source_audit_hash": report["record_hash"],
        "tool_sources": {"checkpoint_script": _sha(__file__), "v7_auditor": _sha(audit.__file__),
                         "v6_auditor": _sha(audit.prior.__file__)},
        "parent_fork_id": original_fork, "fork_id": fork,
        "request_identity": "(request_fork_id, request_hash); repeated final requests may reuse hashes across forks",
        "inherited_request_fork_id": original_fork, "new_final_request_fork_id": fork,
        "selection": "whole_final_stage_restart_not_score_or_error_selection", "final_stage_retained_count": 0,
        "prior_costs_preserved_not_refunded": True, "inherited_training_is_not_new_independent_evidence": True,
        "original_evidence_action": "move_entire_source_unchanged_after_verified_checkpoint_copy",
        "pause_only_no_resume_or_api": True, "posthoc_user_authorized_exclusion_not_preregistered": True,
        "sleep_causality_not_established_by_exclusion": True, **partition})


def apply(prepared, *, user_authorized=False, original_run_stopped=False):
    """Copy a fresh checkpoint, then archive the original intact; never delete.

    Requires an exclusive operator: filesystem preflight cannot prevent a second
    process racing directory entries. On interruption retain all partial paths
    for manual inspection; do not merge, overwrite, or silently retry this script.
    """
    core.verify(prepared)
    _require(user_authorized is True and original_run_stopped is True,
             "Explicit user authorization and operator stopped-process attestation required")
    actual = plan(prepared["repo"], prepared["source"], prepared["checkpoint"], prepared["archive"], prepared["sleep_start"])
    _require(actual == prepared, "Source/protocol/paths changed since the read-only plan")
    source, checkpoint, archive = (Path(prepared[k]) for k in ("source", "checkpoint", "archive"))
    checkpoint.mkdir(parents=False, exist_ok=False)
    for relative in prepared["retained_files"]:
        src, dst = source / relative, checkpoint / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        _require(not dst.exists(), "Checkpoint copy would overwrite an existing file")
        shutil.copy2(src, dst, follow_symlinks=False)
        _require(_sha(dst) == prepared["source_manifest"][relative], "Copied evidence bytes differ")
    copied = _files(checkpoint)
    _require(copied == {p: prepared["source_manifest"][p] for p in prepared["retained_files"]},
             "Checkpoint copy is incomplete or includes excluded final evidence")
    # Verify actual retained reservations and pacing with existing pure readers.
    protocol = _payload(checkpoint / "protocol.json")
    calls, ledger = audit.prior._receipts(checkpoint, protocol, True)
    pacing = audit._pacing(checkpoint, protocol, calls)
    _require(len(calls) == 53 and not ledger["ledger"]["unresolved_reservations"]
             and pacing["http_attempt_admissions"] == pacing["completed_attempt_receipts"] == 55,
             "Copied prefix cannot be resumed without unresolved API/HTTP attempts")
    exclusion = core.seal({"version": VERSION, "plan": prepared, "user_authorized": True,
        "original_run_stopped_operator_attestation": True, "process_state_independently_verified": False,
        "copied_file_hashes": copied, "copied_prefix_audit": {"ledger": ledger, "pacing": pacing},
        "status": "paused_before_whole_final_restart", "original_archive_completion_receipt": "archive_receipt.json",
        "no_api_calls": True, "no_native_reexecution": True, "original_results_unchanged": True})
    write_immutable_json(checkpoint / "exclusion_manifest.json", exclusion)
    _require(_files(source) == prepared["source_manifest"], "Source changed during copy; original must not be moved")
    _safe_path(archive)
    _require(not archive.exists(), "Archive already exists; never overwrite")
    archive.parent.mkdir(parents=False, exist_ok=True)
    source.rename(archive)
    _require(_files(archive) == prepared["source_manifest"], "Archive bytes differ; preserve both paths for inspection")
    receipt = core.seal({"version": VERSION, "fork_id": prepared["fork_id"], "plan_hash": prepared["record_hash"],
        "exclusion_manifest_hash": exclusion["record_hash"], "source": str(source), "archive": str(archive),
        "checkpoint": str(checkpoint), "archive_manifest_hash": prepared["source_manifest_hash"],
        "original_source_moved_intact": True, "deleted_files": 0, "status": "paused_checkpoint_ready"})
    write_immutable_json(checkpoint / "archive_receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"), nargs="?", default="plan")
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sleep-start", default=SLEEP_START)
    parser.add_argument("--user-authorized", action="store_true")
    parser.add_argument("--original-run-stopped", action="store_true")
    args = parser.parse_args()
    prepared = plan(args.repo, args.source, args.checkpoint, args.archive, args.sleep_start)
    result = prepared if args.action == "plan" else apply(prepared, user_authorized=args.user_authorized,
                                                        original_run_stopped=args.original_run_stopped)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
