"""Run one V10 study and publish its offline-verified report; never auto-retry."""

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.coevolution_v10 import safe_root  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--design", required=True, choices=("smoke", "formal"))
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    root = safe_root(args.output, REPO)
    report = args.report.absolute()
    if (any(p.is_symlink() for p in (report, *report.parents)) or report.suffix != ".md"
            or not report.resolve().is_relative_to(REPO / "docs")):
        parser.error("Report must be a Markdown file beneath docs")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "supervisor.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("This run already has a supervisor")
        with (root / "supervisor.log").open("a", buffering=1) as log:
            command = [sys.executable, "-B", "-u", str(REPO / "scripts/coevolution_v10.py"),
                       "--design", args.design, "--output", str(root)]
            if args.resume:
                command.append("--resume")
            print(json.dumps({"phase": "experiment", "design": args.design}), file=log, flush=True)
            code = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
            if code:
                print(json.dumps({"phase": "paused" if code == 75 else "stopped", "returncode": code,
                    "automatic_retry": False, "evidence_preserved": True}), file=log, flush=True)
                return code
            print(json.dumps({"phase": "offline_verified_report"}), file=log, flush=True)
            code = subprocess.run([sys.executable, "-B", str(REPO / "scripts/report_coevolution_v10.py"),
                "--output", str(root), "--report", str(report)], cwd=REPO,
                stdout=log, stderr=subprocess.STDOUT).returncode
            print(json.dumps({"phase": "finished" if code == 0 else "report_stopped", "returncode": code}),
                  file=log, flush=True)
            return code


if __name__ == "__main__":
    raise SystemExit(main())
