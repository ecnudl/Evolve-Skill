"""Read aggregate V12 progress without credentials, model clients or writes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v12.study import read, safe_root  # noqa: E402


def status(output, repo=REPO):
    root = safe_root(repo, output)
    if not (root / "protocol.json").exists():
        return {"prepared": False, "complete": False, "output": str(root)}
    protocol = read(root / "protocol.json")
    calls = [json.loads(p.read_text(encoding="utf-8")) for p in (root / "api/calls").glob("*.json")]
    events = sorted((root / "events").glob("*.json"))
    latest = read(events[-1]) if events else None
    complete = (root / "results.json").exists()
    result = read(root / "results.json") if complete else None
    api_hashes = {row["request_hash"] for row in calls}
    stage_hashes = {p.stem for p in (root / "runtime/stages").glob("*.json")}
    solve_intents = {p.stem for p in (root / "runtime/request_intents").glob("*.json")}
    learned = [read(p) for p in (root / "learning").glob("*.json")]
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "prepared": True, "complete": complete, "design": protocol["design"], "model": protocol["model"],
        "pause_requested": (root / "PAUSE_REQUESTED").exists(),
        "last_event": latest, "closed_logical_calls": len(calls), "max_logical_calls": protocol["max_calls"],
        "successful_calls": sum(row["ok"] for row in calls),
        "terminal_errors": dict(Counter(row.get("error_type", "unclassified") for row in calls if not row["ok"])),
        "http_attempts_in_closed_calls": sum(row.get("http_attempt_count", 0) for row in calls),
        "pending_solver_receipts": len(solve_intents - api_hashes),
        "pending_solver_stages": len(solve_intents - stage_hashes),
        "pending_counts_may_be_normal_inflight_not_resume_authority": True,
        "skill_proposals": len(learned), "valid_proposals": sum(row["valid"] for row in learned),
        "frozen_final": (root / "final_frozen.json").exists(),
        "result_hash": result["record_hash"] if result else None,
        "no_model_api_calls": True, "read_only": True,
        "process_liveness_checked": False, "final_scores_not_exposed": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(status(args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
