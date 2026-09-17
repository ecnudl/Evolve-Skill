"""Supervise one bounded V12 run and publish a completed offline-verified report.

No automatic restart or semantic resampling. Closed checkpoints and terminal
errors are preserved. Caller may use temporary caffeinate, not power settings.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v12.study import safe_root  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--design", required=True, choices=("smoke", "formal"))
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    root = safe_root(REPO, args.output)
    report = args.report.absolute()
    if (any(p.is_symlink() for p in (report, *report.parents)) or report.suffix != ".md"
            or not report.resolve().is_relative_to(REPO / "docs")):
        parser.error("Report must be Markdown beneath docs")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "supervisor.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Run already has a supervisor")
        with (root / "supervisor.log").open("a", buffering=1) as log:
            def event(phase, **fields):
                record = {"time_utc": datetime.now(timezone.utc).isoformat(), "phase": phase, **fields}
                print(json.dumps(record), file=log, flush=True)
                print(json.dumps(record), flush=True)

            command = [sys.executable, "-B", "-u", str(REPO / "scripts/coevolution_v12.py"),
                       "--design", args.design, "--output", str(root)]
            if args.resume:
                command.append("--resume")
            event("experiment", design=args.design)
            code = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
            if code:
                event("paused" if code == 75 else "stopped", returncode=code,
                      automatic_retry=False, evidence_preserved=True)
                return code
            event("offline_verified_report")
            code = subprocess.run([sys.executable, "-B", str(REPO / "scripts/report_coevolution_v12.py"),
                "--output", str(root), "--report", str(report)], cwd=REPO,
                stdout=log, stderr=subprocess.STDOUT).returncode
            event("finished" if code == 0 else "report_stopped", returncode=code)
            return code


if __name__ == "__main__":
    raise SystemExit(main())
