"""Run or replay the bounded cross-domain Skill-refinement experiment."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v12.study import PauseRequested, Study, read, safe_root  # noqa: E402


def tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=("smoke", "formal"), default=None)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--replay-only", action="store_true")
    actions.add_argument("--request-pause", action="store_true")
    actions.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    root = safe_root(REPO, args.output)
    if args.request_pause:
        if not (root / "protocol.json").exists():
            parser.error("No prepared run exists to pause")
        if not (root / "PAUSE_REQUESTED").exists():
            (root / "PAUSE_REQUESTED").touch(exist_ok=False)
        print('{"pause_requested":true,"drain_current_chunk":true}')
        return 0
    if args.replay_only and not (root / "results.json").exists():
        parser.error("A complete result is required; replay cannot start a run")
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".run.lock"
    if args.replay_only and not lock_path.exists():
        parser.error("Completed CLI run must already have its lock")
    with lock_path.open("rb" if args.replay_only else "a+") as handle:
        fcntl.flock(handle, (fcntl.LOCK_SH if args.replay_only else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        if args.resume and (root / "PAUSE_REQUESTED").exists():
            # Only the explicit request marker is consumed. Evidence is retained.
            (root / "PAUSE_REQUESTED").unlink()
        saved = read(root / "protocol.json")["design"] if (root / "protocol.json").exists() else None
        design = args.design or saved or "smoke"
        if saved and design != saved:
            parser.error("Cannot change a frozen design")
        before = tree(root) if args.replay_only else None
        try:
            result = Study(REPO, root, design=design).run()
        except PauseRequested:
            print('{"complete":false,"paused":true}')
            return 75
        if before is not None and tree(root) != before:
            raise ValueError("Completed replay changed files")
        print(json.dumps({"complete": result["complete"], "result_hash": result["record_hash"],
            "learning": result["learning"], "summary": result["summary"], "ledger": result["ledger"],
            "replay_files_unchanged": before is not None}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
