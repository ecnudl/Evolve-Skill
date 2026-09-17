"""Read-only V9 metadata progress, or completed cached-result verification.

Progress never opens task materializations, Skill text, gate scores, or final
rows. API files are parsed only to project transport/usage metadata; their
request prompts and responses are never inspected or returned. A completed
audit invokes the driver's offline replay, which may read frozen host gold for
score verification but cannot issue model calls or feed results into learning.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.core import seal, verify  # noqa: E402
from skillopt.coevolution_v9.study import DESIGNS, VERSION, Study  # noqa: E402

_HASH = re.compile(r"[a-f0-9]{64}\Z")
_KINDS = frozenset({"v9_searchqa_solve", "v9_native_analyst", "v9_native_merge", "v9_native_rank"})
_ERRORS = frozenset({
    "http_status", "incomplete_stream", "truncated_content", "empty_content", "unexpected_finish_reason",
    "missing_stream_finish", "timeout", "transport_error", "invalid_response_schema", "unexpected_client_error",
    "content_after_stream_finish", "inconsistent_stream_finish", "inconsistent_stream_model", "invalid_stream_choice",
    "invalid_stream_choices", "invalid_stream_content", "invalid_stream_delta", "invalid_stream_event", "invalid_stream_usage",
    "stream_content_limit", "stream_size_limit", "stream_wall_time_limit", "unexpected_stream_content_type", "upstream_stream_error",
})


def _read(path, *, sealed=False):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Audit metadata must be an object")
    return verify(value) if sealed else value


def _safe_root(output, repo):
    path = Path(output).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Symlink audit paths are unsupported")
    path = path.resolve()
    registry = repo / "outputs/coevolution_v9"
    if path == registry or not path.is_relative_to(registry) or not path.is_dir():
        raise ValueError("Audit an existing isolated run beneath outputs/coevolution_v9")
    if any(part.is_symlink() for part in path.rglob("*")):
        raise ValueError("Symlink run contents are unsupported")
    return path


def _tree_hashes(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def _protocol(root):
    record = _read(root / "protocol.json", sealed=True)
    if (record.get("version") != VERSION or record.get("design_name") not in DESIGNS
            or record.get("design") != DESIGNS[record["design_name"]]
            or type(record.get("max_calls")) is not int or record["max_calls"] < 1):
        raise ValueError("A sealed recognized V9 design protocol is required")
    return record


def _progress(root, protocol):
    api_root = root / "api"
    receipts = sorted((api_root / "calls").glob("*.json"))
    api_ok, http_attempts, missing_usage = 0, 0, 0
    errors, kinds, statuses = Counter(), Counter(), Counter()
    usage = {key: 0 for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    missing_fields = {key: 0 for key in usage}
    for path in receipts:
        row = _read(path)
        if (not _HASH.fullmatch(path.stem) or row.get("request_hash") != path.stem
                or type(row.get("ok")) is not bool or type(row.get("http_attempt_count")) is not int
                or not 1 <= row["http_attempt_count"] <= 3):
            raise ValueError("Invalid cached transport metadata; no progress score is inferred")
        api_ok += row["ok"]
        http_attempts += row["http_attempt_count"]
        kind = row.get("request", {}).get("kind") if isinstance(row.get("request"), dict) else None
        kinds[kind if isinstance(kind, str) and kind in _KINDS else "other_or_missing_kind"] += 1
        if not row["ok"]:
            error = row.get("error_type")
            errors[error if isinstance(error, str) and error in _ERRORS else "other_or_missing_error"] += 1
            status = row.get("status")
            statuses[str(status) if type(status) is int and 100 <= status <= 599 else "no_http_status"] += 1
        reported = row.get("usage", {})
        if not isinstance(reported, dict):
            raise ValueError("Cached usage metadata is malformed")
        missing_usage += not bool(reported)
        for key in usage:
            value = reported.get(key)
            if value is None:
                missing_fields[key] += 1
            elif type(value) is not int or value < 0:
                raise ValueError("Cached token usage must be a nonnegative integer or missing")
            else:
                usage[key] += value
    proposals = len(list((root / "learning").glob("history_*/result.json")))
    gates = len(list((root / "histories").glob("*.json")))
    complete = (root / "results.json").is_file()
    if complete:
        stage = "completed_record_present_not_yet_audited"
    elif (root / "final_freeze.json").is_file():
        stage = "frozen_final_execution"
    elif proposals > gates:
        stage = "source_confirmation"
    elif len(list((root / "learning").glob("history_*/identity.json"))) > proposals:
        stage = "native_skillopt_update"
    elif receipts:
        stage = "training_or_between_histories"
    else:
        stage = "prepared_no_completed_model_calls"
    reserved = {path.stem for path in (api_root / "budget_reservations").glob("*.json")}
    called = {path.stem for path in receipts}
    return {
        "design": protocol["design_name"], "stage": stage, "completed_record_present": complete,
        "histories_planned": protocol["design"]["histories"], "proposal_records_present": proposals,
        "gate_history_records_present": gates, "solver_records_present": len(list((root / "solves").glob("*.json"))),
        "max_planned_logical_calls": protocol["max_calls"], "completed_logical_calls": len(receipts),
        "api_ok": api_ok, "terminal_calls": len(receipts) - api_ok, "http_attempts": http_attempts,
        "logical_reservations_present": len(reserved), "pending_reservations": len(reserved - called),
        "receipts_without_reservations": len(called - reserved),
        "failure_categories": dict(sorted(errors.items())), "terminal_http_statuses": dict(sorted(statuses.items())),
        "calls_by_kind": dict(sorted(kinds.items())), **usage, "missing_usage_calls": missing_usage,
        "missing_usage_fields": missing_fields, "usage_not_invoice": True,
        "intermediate_scores_computed": False, "counts_are_progress_not_integrity_verification": True,
        "snapshot_is_non_atomic_while_running": True,
    }


def forbidden_api(*_args, **_kwargs):
    raise RuntimeError("Read-only V9 audit forbids constructing a model API client")


def audit(output, repo=REPO, *, require_complete=False):
    """Project progress metadata, optionally checking completed offline replay."""
    repo = Path(repo).resolve()
    root = _safe_root(output, repo)
    protocol = _protocol(root)
    if require_complete:
        if not (root / "results.json").is_file():
            raise ValueError("A completed result is required; this audit cannot resume an experiment")
        expected = _read(root / "results.json", sealed=True)
        if (expected.get("complete") is not True or expected.get("version") != VERSION
                or expected.get("protocol_hash") != protocol["record_hash"]):
            raise ValueError("A sealed completed result bound to this protocol is required")
    progress = _progress(root, protocol)
    if not require_complete:
        return seal({"audit_kind": "v9_transport_progress_only", "progress": progress,
                     "read_only": True, "complete_integrity_audit": False, "model_api_calls": 0})
    before = _tree_hashes(root)
    manifest = _read(root / "data_manifest.json", sealed=True)
    if manifest["record_hash"] != protocol["data_manifest_hash"]:
        raise ValueError("Completed data identity manifest differs from the protocol")
    cache_paths = {name: metadata["path"] for name, metadata in manifest["settings"]["sources"].items()}
    runner = Study(repo, root, design=protocol["design_name"], cache_paths=cache_paths)
    if not runner.completed:
        raise ValueError("Completed runner state vanished; audit cannot start live execution")
    # The existing driver emits stage-only logs during offline reconstruction.
    # Suppress them so this CLI emits exactly one bounded audit result.
    try:
        with redirect_stdout(io.StringIO()):
            actual = runner.run(api_factory=forbidden_api)
    finally:
        if _tree_hashes(root) != before:
            raise ValueError("Completed audit changed run files; result is not accepted as read-only")
    if actual != expected:
        raise ValueError("Completed offline recomputation differs from the published result")
    return seal({"audit_kind": "v9_completed_offline_replay", "progress": progress,
                 "read_only": True, "complete_integrity_audit": True, "model_api_calls": 0,
                 "run_files_unchanged": True, "verified_run_files": len(before),
                 "result_hash": actual["record_hash"], "summary": actual["summary"], "ledger": actual["ledger"],
                 "source_domain_only": True, "cross_domain_efficacy_established": False})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    result = audit(args.output, require_complete=args.require_complete)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
