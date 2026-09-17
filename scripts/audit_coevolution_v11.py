"""Read-only, score-blind V11 transport progress; no API or candidate execution."""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.coevolution_v11 import _read, completed_replay, safe_root  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402


def progress(output, repo=REPO):
    root = safe_root(output, repo)
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("Run evidence cannot contain symlinks")
    protocol = _read(root / "protocol.json")
    calls = {}
    for path in (root / "api/calls").glob("*.json"):
        row = json.loads(path.read_text())
        if (row.get("request_hash") != path.stem or digest(row["request"]) != path.stem
                or type(row.get("ok")) is not bool or row["request"].get("kind") != "v11_coding_solve"):
            raise ValueError("Invalid actual transport receipt")
        calls[path.stem] = row
    reserved = {p.stem for p in (root / "api/budget_reservations").glob("*.json")}
    admissions = [_read(p) for p in (root / "api/pacing/admissions").glob("*.json")]
    outcomes = [_read(p) for p in (root / "api/pacing/attempts").glob("*.json")]
    active = False
    lock_path = root / ".run.lock"
    if lock_path.exists():
        with lock_path.open("r") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                active = True
    pending_pause = {p.stem for p in (root / "controls/requests").glob("*.json")} - {
        p.stem for p in (root / "controls/resumes").glob("*.json")}
    final = (root / "final_freeze.json").is_file()
    complete = (root / "results.json").is_file()
    last = max((r["finished_wall"] for r in outcomes), default=None)
    return {"read_only": True, "effect_scores_opened": False, "design": protocol["design_name"],
        "process_lock_held": active, "pending_pause": sorted(pending_pause),
        "stage": "completed_record_present_not_audited" if complete else "frozen_final" if final else "confirmation",
        "max_logical_calls": protocol["max_calls"], "cached_logical_calls": len(calls),
        "api_ok": sum(r["ok"] for r in calls.values()),
        "terminal_errors": dict(Counter(r.get("error_type") for r in calls.values() if not r["ok"])),
        "unclosed_logical_requests": sorted(reserved - set(calls)),
        "http_admissions": len(admissions), "http_outcomes": len(outcomes),
        "unclosed_http_attempt_count": max(0, len(admissions) - len(outcomes)),
        "last_http_completion_utc": datetime.fromtimestamp(last, timezone.utc).isoformat() if last else None,
        "reported_total_tokens": sum(r.get("usage", {}).get("total_tokens", 0) or 0 for r in calls.values()),
        "counts_are_snapshot_not_atomic": True, "unclosed_is_not_failure_while_process_active": True,
        "evidence_of_sleep_cause": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    result = completed_replay(args.output)["audit"] if args.require_complete else progress(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

