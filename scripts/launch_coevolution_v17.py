"""Supervise one V17 run; drain and pause on suspend, never auto-resample."""

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

from scripts import coevolution_v17 as cli  # noqa: E402

HEARTBEAT_SECONDS = 30
SUSPEND_THRESHOLD_SECONDS = 120


def suspend_evidence(last_wall, last_mono, now_wall, now_mono):
    """Also detect platforms whose monotonic clock includes suspended time."""
    wall, mono = now_wall - last_wall, now_mono - last_mono
    drift = wall - mono
    return {"pause_needed": (max(wall, mono) > SUSPEND_THRESHOLD_SECONDS
                             or abs(drift) > SUSPEND_THRESHOLD_SECONDS),
            "wall_gap_seconds": round(wall, 3), "monotonic_gap_seconds": round(mono, 3),
            "clock_divergence_seconds": round(drift, 3)}


def main(argv=None):
    study = cli._study()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=tuple(study.DESIGNS), required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    root = study.safe_root(REPO, args.output)
    report = cli.report_path(REPO, args.report) if args.report else None
    # Completed launch is a pure verification path, with no new supervisor log.
    if (root / "results.json").is_file():
        return cli.main(["--output", str(root), "--design", args.design, "--replay-only"]
                        + (["--report", str(report)] if report else []))
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".audit.lock").open("a"):
        pass
    with (root / "supervisor.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (root / "supervisor.log").open("a", buffering=1) as log:
            def event(stage, **details):
                row = {"stage": stage, "time_utc": datetime.now(timezone.utc).isoformat(), **details}
                with (root / ".audit.lock").open("rb") as audit_lock:
                    fcntl.flock(audit_lock, fcntl.LOCK_SH)
                    print(json.dumps(row), file=log, flush=True)
                    print(json.dumps(row), flush=True)

            command = [sys.executable, "-B", "-u", str(REPO / "scripts/coevolution_v17.py"),
                       "--output", str(root), "--design", args.design]
            if report:
                command += ["--report", str(report)]
            if args.resume:
                command.append("--resume")
            child = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
            event("started", child_pid=child.pid, design=args.design, automatic_restart=False)
            last_wall, last_mono = time.time(), time.monotonic()
            pause_emitted = False
            while child.poll() is None:
                try:
                    child.wait(timeout=HEARTBEAT_SECONDS)
                except subprocess.TimeoutExpired:
                    now_wall, now_mono = time.time(), time.monotonic()
                    evidence = suspend_evidence(last_wall, last_mono, now_wall, now_mono)
                    last_wall, last_mono = now_wall, now_mono
                    with (root / ".audit.lock").open("rb") as audit_lock:
                        try:
                            fcntl.flock(audit_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        except BlockingIOError:
                            continue
                        if (root / "results.json").exists():
                            continue
                        if evidence["pause_needed"] and not pause_emitted:
                            (root / "PAUSE").touch(exist_ok=True)
                            pause_emitted = True
                            event("possible_suspend_or_clock_jump_pause_requested", **evidence,
                                  receipts_preserved=True, not_automatically_excluded=True,
                                  inflight_drained_before_stop=True)
                        event("heartbeat", child_pid=child.pid,
                              completed_calls=len(list((root / "api/calls").glob("*.json"))),
                              pause_requested=(root / "PAUSE").exists())
            code = child.returncode
            event("finished" if code == 0 else "paused" if code == 75 else "stopped",
                  returncode=code, automatic_retry=False, evidence_preserved=True)
            return code


if __name__ == "__main__":
    raise SystemExit(main())
