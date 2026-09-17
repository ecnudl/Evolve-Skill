"""Recover only the V6 null-model reporting-index failure, entirely offline.

The frozen runner must first terminate. This exporter does not inspect process
state: --write requires an explicit operator attestation. Original results are
never fabricated or overwritten; only recovered_results.json may be created.
No model calls, task evaluation, research, environment loading, or score changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import audit_coevolution_v6 as auditor  # noqa: E402
from skillopt.coevolution_v5 import core  # noqa: E402
from skillopt.coevolution_v6.experiment import VERSION  # noqa: E402
from skillopt.validator_pilot.api import digest, write_immutable_json  # noqa: E402

RECOVERY_VERSION = "v6-reporting-index-recovery-v1"
ROOT_EVIDENCE = (
    "protocol.json", "panel.json", "skills_frozen.json", "validator_candidate_frozen.json",
    "research_selection.json", "calibration_manifest.json", "calibration_schedule.json",
    "calibration_rows.json", "calibration_summary.json", "private_preflight.json",
    "repair_results.json", "final_frozen.json", "final_rows.json", "api/budget_protocol.json",
)
EVIDENCE_DIRECTORIES = (
    "source_states", "source_decisions", "targets", "probes", "calibration_calls",
    "research", "feedback_utility", "human_review",
)
EXPORTER_SOURCE = "scripts/finalize_coevolution_v6.py"
AUDITOR_SOURCE = "scripts/audit_coevolution_v6.py"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def evidence_manifest(run):
    """Exact complete input-file set, excluding reporting products and lock files."""
    run = Path(run).resolve()
    paths = {run / name for name in ROOT_EVIDENCE}
    for name in EVIDENCE_DIRECTORIES:
        directory = run / name
        _require(not directory.is_symlink(), "Symlink evidence directories are forbidden")
        if directory.exists():
            paths.update(p for p in directory.rglob("*") if p.is_file() or p.is_symlink())
    for name in ("api/calls", "api/budget_reservations"):
        directory = run / name
        _require(not directory.is_symlink(), "Symlink API evidence directories are forbidden")
        paths.update(directory.glob("*.json"))
    result = {}
    for path in sorted(paths):
        if path.name.endswith(".lock"):
            continue
        _require(not path.name.startswith(".pending-"), "An unfinished evidence write remains")
        _require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(run),
                 "Required evidence is missing or unsafe")
        _require(not any(p.is_symlink() for p in path.parents if p != run and p.is_relative_to(run)),
                 "Symlink evidence ancestors are forbidden")
        result[str(path.relative_to(run))] = hashlib.sha256(path.read_bytes()).hexdigest()
    _require("human_review/queue.json" in result and "human_review/queue.json.private.json" in result,
             "A complete human assignment queue is required; review itself remains pending")
    return result


def _source_hashes(repo):
    return {name: hashlib.sha256(auditor._safe(repo, name).read_bytes()).hexdigest()
            for name in (EXPORTER_SOURCE, AUDITOR_SOURCE)}


def finalize(run, *, repo=REPO, write=False, runtime_failure_confirmed=False):
    """Return the complete recovered index; write only on explicit confirmation.

    The retained stage receipts and frozen grids are checked by the independent
    read-only auditor before constructing the index. All input bytes must remain
    unchanged through that check. An existing identical recovery is reusable.
    Confirmation records an operator statement, not an independently observed exit.
    """
    run, repo = Path(run).resolve(), Path(repo).resolve()
    _require(run.is_dir() and run.is_relative_to(repo), "Existing run inside repository required")
    _require(type(write) is bool and type(runtime_failure_confirmed) is bool, "Explicit boolean operation flags required")
    _require(not write or runtime_failure_confirmed, "Writing requires operator confirmation of original runtime failure")
    _require(not (run / "results.json").exists(), "Original results already exist; reporting recovery is not applicable")
    destination = run / "recovered_results.json"
    _require(not destination.is_symlink(), "Recovery destination must not be a symlink")
    before, sources = evidence_manifest(run), _source_hashes(repo)
    report = auditor.audit(run, repo=repo, require_complete=False, require_evidence_complete=True)
    core.verify(report)
    _require(report.get("evidence_complete") is True, "All frozen evidence stages must be complete")
    for stage in ("calibration", "final", "research"):
        _require(report.get(stage, {}).get("complete") is True, "A required evidence stage is incomplete")
    ledger = report["api"]["ledger"]
    _require(not ledger["unresolved_reservations"], "Unresolved API reservations cannot be reported complete")
    _require(report["human_review"]["status"] == "pending_external_human", "Human assignment queue must be complete")

    calls = [auditor._json(run / relative) for relative in before if relative.startswith("api/calls/")]
    null_models = sum("returned_model" in row and row["returned_model"] is None and row.get("ok") is False
                      for row in calls)
    named_models = sum(isinstance(row.get("returned_model"), str) and bool(row["returned_model"]) for row in calls)
    _require(null_models > 0 and named_models > 0, "The specific mixed null/string model-counter failure is absent")
    _require(len(calls) == ledger["cached_logical_calls"], "API model count and validated ledger disagree")
    returned = dict(Counter(row.get("returned_model") or "unreported" for row in calls))
    _require(returned == report["api"]["returned_models"], "Normalized model counts differ from the audit")

    protocol = auditor._read(run / "protocol.json")
    freeze = auditor._read(run / "skills_frozen.json")
    selection = auditor._read(run / "validator_candidate_frozen.json")
    repairs = auditor._read(run / "repair_results.json")
    _require(repairs.get("no_update") is True, "Repair diagnostic cannot update a Skill")
    packets = {}
    for round_index in range(protocol["source_rounds"]):
        state = auditor._read(run / "source_states" / f"r{round_index}.json")
        for branch in state["histories"]:
            for packet in branch["feedback"]:
                core.verify(packet)
                packets[packet["record_hash"]] = packet
    _require(len(packets) == report["source_skills"]["unique_retained_feedback"], "Development feedback count mismatch")
    _require(selection["proposal_hash"] == report["research"]["proposal_hash"], "Frozen research selection mismatch")

    existing = auditor._json(destination) if destination.exists() else None
    if existing is not None:
        core.verify(existing)
        # The auditor has independently validated any existing recovery metadata.
        runtime_failure_confirmed = existing["reporting_recovery"]["runtime_failure_confirmation"]["confirmed"]
    recovery = {
        "version": RECOVERY_VERSION, "reason": "null_returned_model_counter_serialization",
        "original_runtime_completed": False, "original_results_present": False,
        "runtime_completion_success": False, "source_results_file": "recovered_results.json",
        "no_api_calls": True, "no_rescoring": True, "original_evidence_unchanged": True,
        "exporter_source": EXPORTER_SOURCE, "exporter_source_sha256": sources[EXPORTER_SOURCE],
        "auditor_source": AUDITOR_SOURCE, "auditor_source_sha256": sources[AUDITOR_SOURCE],
        "source_evidence_manifest": before,
        "runtime_failure_confirmation": {"kind": "operator_attestation", "confirmed": runtime_failure_confirmed,
                                         "independently_verified_process_exit": False},
    }
    result = core.seal({
        "version": VERSION, "status": "complete", "protocol_hash": digest(protocol),
        "decisions": freeze["decisions"], "validator_selection": selection,
        "research_proposal_hash": report["research"]["proposal_hash"],
        "calibration": report["calibration"]["summary"], "final": report["final"]["summary"],
        "repair": repairs["rows"], "repair_summary": report["repair"]["summary"], "ledger": ledger,
        "returned_models": returned, "unique_feedback": len(packets),
        "human_review": "pending_external_human", "engineering_only": True,
        "public_benchmark_efficacy_established": False, "final_feedback_used": False,
        "calibration_feedback_used": False, "reporting_recovery": recovery,
    })
    _require(evidence_manifest(run) == before and _source_hashes(repo) == sources,
             "Evidence or recovery tools changed during verification")
    _require(not (run / "results.json").exists(), "Original runtime wrote results during verification")
    if existing is not None:
        _require(existing == result, "Existing recovered index disagrees with complete retained evidence")
    if write:
        write_immutable_json(destination, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--write", action="store_true", help="Write only recovered_results.json after complete verification")
    parser.add_argument("--confirm-runtime-failed", action="store_true",
                        help="Operator confirms the original runtime exited with the observed reporting failure")
    args = parser.parse_args()
    try:
        result = finalize(args.run, repo=args.repo, write=args.write,
                          runtime_failure_confirmed=args.confirm_runtime_failed)
    except (ValueError, KeyError, TypeError, OSError):
        print(json.dumps({"recovery_valid": False, "error": "evidence_incomplete_inconsistent_or_failure_not_confirmed"}))
        raise SystemExit(2) from None
    print(json.dumps({"recovery_valid": True, "written": args.write, "original_runtime_completed": False,
                      "source_results_file": "recovered_results.json" if args.write else "dry_run_no_output_written",
                      "result_hash": result["record_hash"], "returned_models": result["returned_models"],
                      "logical_calls": result["ledger"]["cached_logical_calls"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
