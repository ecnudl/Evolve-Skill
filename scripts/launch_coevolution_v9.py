"""Run the frozen V9 CLI, then produce an independently verified Markdown report.

This supervisor does not change sampling, model settings, selection or scoring.
One run owns its lock; it never retries a failed experiment subprocess.
"""

import argparse
import fcntl
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v9.study import _safe_run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--design", required=True, choices=("smoke", "source"))
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    root = _safe_run(REPO, args.output)
    report = args.report.absolute()
    if report.is_symlink() or not report.resolve().is_relative_to(REPO / "docs") or report.suffix != ".md":
        parser.error("Report must be a new Markdown file below this repository's docs directory")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "supervisor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("A supervisor already owns this experiment; no duplicate process started")
        with (root / "supervisor.log").open("a", buffering=1) as log:
            command = [sys.executable, "-u", str(REPO / "scripts/coevolution_v9.py"),
                       "--design", args.design, "--output", str(root)]
            print(json.dumps({"phase": "experiment", "design": args.design}), file=log, flush=True)
            code = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
            if code:
                print(json.dumps({"phase": "stopped", "returncode": code,
                                  "automatic_retry": False, "evidence_preserved": True}), file=log, flush=True)
                return code
            print(json.dumps({"phase": "offline_verified_report"}), file=log, flush=True)
            code = subprocess.run([sys.executable, "-B", str(REPO / "scripts/report_coevolution_v9.py"),
                "--output", str(root), "--report", str(report)], cwd=REPO,
                stdout=log, stderr=subprocess.STDOUT).returncode
            print(json.dumps({"phase": "finished" if code == 0 else "report_stopped", "returncode": code}),
                  file=log, flush=True)
            return code


if __name__ == "__main__":
    raise SystemExit(main())
