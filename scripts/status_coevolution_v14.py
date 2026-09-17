"""Read aggregate V14 progress; no credentials, API, artifact execution or writes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.coevolution_v14 import study_module  # noqa: E402

EVENT_FIELDS = {"time_utc", "sequence", "stage", "phase", "history", "round", "arm",
                "completed_trajectories", "total_trajectories", "calls", "result_hash"}


def closed_json_files(directory):
    # Atomic writers may have a temporary .pending-*.json in flight. It is not
    # a durable receipt and must never be parsed or counted as one.
    return sorted(p for p in directory.glob("*.json") if not p.name.startswith("."))


def status(output, *, repo=REPO):
    module = study_module()
    root = module.safe_root(repo, output)
    if not (root / "protocol.json").is_file():
        return {"prepared": False, "complete": False, "output": str(root), "read_only": True}
    protocol = module.read(root / "protocol.json")
    hashes, by_kind, errors = set(), Counter(), Counter()
    successes = attempts = usage_missing = 0
    for path in closed_json_files(root / "api/calls"):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row["request_hash"] != path.stem or path.stem in hashes:
            raise ValueError("API progress receipt identity differs")
        hashes.add(path.stem)
        by_kind[row["request"]["kind"]] += 1
        successes += row["ok"]
        attempts += row.get("http_attempt_count", 0)
        usage_missing += not row.get("usage")
        if not row["ok"]:
            label = row.get("error_type", "unclassified")
            errors[label if isinstance(label, str) and len(label) <= 100 else "unclassified"] += 1
    events = closed_json_files(root / "events")
    last = module.read(events[-1]) if events else {}
    complete = (root / "results.json").is_file()
    result = module.read(root / "results.json") if complete else None
    intents = {p.stem for p in closed_json_files(root / "runtime/request_intents")}
    stages = {p.stem for p in closed_json_files(root / "runtime/stages")}
    proposals = [module.read(path) for path in closed_json_files(root / "learning")]
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "prepared": True,
        "complete": complete, "design": protocol["design"], "model": protocol["model"],
        "pause_requested": (root / "PAUSE").exists(),
        "last_event": {k: v for k, v in last.items() if k in EVENT_FIELDS},
        "closed_logical_calls": len(hashes), "max_logical_calls": protocol["max_calls"],
        "calls_by_kind": dict(sorted(by_kind.items())), "successful_calls": successes,
        "terminal_errors": dict(sorted(errors.items())), "http_attempts_in_closed_calls": attempts,
        "missing_usage_calls": usage_missing,
        "pending_solver_receipts": len(intents - hashes), "pending_solver_stages": len(intents - stages),
        "pending_counts_may_be_normal_inflight_not_resume_authority": True,
        "skill_proposals": len(proposals), "valid_proposals": sum(bool(r.get("valid")) for r in proposals),
        "frozen_final": (root / "final_frozen.json").exists(),
        "result_hash": result["record_hash"] if result else None,
        "no_model_api_calls": True, "read_only": True, "process_liveness_checked": False,
        "final_scores_not_exposed": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(status(args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
