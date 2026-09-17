"""Supervise one V15 run; preserve interruptions, no automatic resampling."""

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main(argv=None):
    from skillopt.coevolution_v15.study import DESIGNS, safe_root
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=tuple(DESIGNS), required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    root = safe_root(REPO, args.output)
    report = args.report.absolute()
    if (any(p.is_symlink() for p in (report, *report.parents)) or report.suffix != ".md"
            or not report.is_relative_to(REPO / "docs") or report.name == "coevolution-v15-protocol.md"):
        parser.error("Report must be a derived nonsource Markdown file under docs")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".audit.lock").open("a"):
        pass
    with (root / "supervisor.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (root / "supervisor.log").open("a", buffering=1) as log:
            def event(stage, **details):
                row = {"stage": stage, "time_utc": datetime.now(timezone.utc).isoformat(), **details}
                print(json.dumps(row), file=log, flush=True)
                print(json.dumps(row), flush=True)
            command = [sys.executable, "-B", "-u", str(REPO / "scripts/coevolution_v15.py"),
                       "--output", str(root), "--design", args.design, "--report", str(report)]
            if args.resume:
                command.append("--resume")
            child = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
            event("started", child_pid=child.pid, design=args.design, automatic_restart=False)
            last_wall, last_mono = time.time(), time.monotonic()
            while child.poll() is None:
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    now_wall, now_mono = time.time(), time.monotonic()
                    gap = (now_wall - last_wall) - (now_mono - last_mono)
                    last_wall, last_mono = now_wall, now_mono
                    with (root / ".audit.lock").open("rb") as audit_lock:
                        try:
                            fcntl.flock(audit_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        except BlockingIOError:
                            continue
                        if (root / "results.json").exists():
                            continue
                        if gap > 120:
                            (root / "PAUSE").touch(exist_ok=True)
                            event("possible_suspend_or_clock_jump_pause_requested", gap_seconds=round(gap, 2),
                                  receipts_preserved=True, not_automatically_excluded=True)
                        event("heartbeat", child_pid=child.pid,
                              completed_calls=len(list((root / "api/calls").glob("*.json"))))
            code = child.returncode
            event("finished" if code == 0 else "paused" if code == 75 else "stopped",
                  returncode=code, automatic_retry=False, evidence_preserved=True)
            return code


if __name__ == "__main__":
    raise SystemExit(main())
