"""Supervise one bounded V14 run and its zero-API completed report.

No automatic restart, semantic resampling, power-setting changes, or failure
deletion. Explicit --resume only consumes a validated experiment's PAUSE marker.
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

from scripts.coevolution_v14 import configuration, study_module  # noqa: E402


def report_target(path, repo=REPO):
    path = Path(path).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents)) or path.suffix != ".md"
            or not path.resolve().is_relative_to(Path(repo).resolve() / "docs")):
        raise ValueError("Report must be a Markdown file beneath repository docs")
    return path.resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--design", required=True, choices=("smoke", "formal"))
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    module = study_module()
    root = module.safe_root(REPO, args.output)
    report = report_target(args.report, REPO)
    protocol = module.read(root / "protocol.json") if (root / "protocol.json").is_file() else None
    config = configuration(protocol, design=args.design, max_calls=args.max_calls, workers=args.workers)
    if args.resume and (protocol is None or (root / "results.json").exists()):
        parser.error("Resume requires a prepared unfinished run")
    sources = protocol["source_hashes"] if protocol else module.source_hashes(REPO)
    if str(report.relative_to(REPO)) in sources:
        parser.error("Report cannot overwrite a frozen source")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "supervisor.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (root / "supervisor.log").open("a", buffering=1) as log:
            def event(phase, **fields):
                record = {"time_utc": datetime.now(timezone.utc).isoformat(), "phase": phase, **fields}
                print(json.dumps(record), file=log, flush=True)
                print(json.dumps(record), flush=True)
            command = [sys.executable, "-B", "-u", str(REPO / "scripts/coevolution_v14.py"),
                       "--design", config["design"], "--output", str(root),
                       "--max-calls", str(config["max_calls"]), "--workers", str(config["workers"])]
            if args.resume:
                command.append("--resume")
            event("experiment", **config)
            code = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
            if code:
                event("paused" if code == 75 else "stopped", returncode=code,
                      automatic_retry=False, evidence_preserved=True)
                return code
            event("offline_verified_report")
            code = subprocess.run([sys.executable, "-B", str(REPO / "scripts/report_coevolution_v14.py"),
                "--output", str(root), "--report", str(report)], cwd=REPO,
                stdout=log, stderr=subprocess.STDOUT).returncode
            event("finished" if code == 0 else "report_stopped", returncode=code)
            return code


if __name__ == "__main__":
    raise SystemExit(main())
