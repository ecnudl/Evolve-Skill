"""Single supervised V18 run with suspend-aware draining, audit and auto-report."""

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

from scripts import coevolution_v18 as cli  # noqa: E402
from scripts.launch_coevolution_v17 import suspend_evidence  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    from scripts.coevolution_v17 import report_path
    root = cli._study().safe_root(REPO, args.output)
    report = report_path(REPO, args.report)
    command = ["--output", str(root), "--report", str(report)]
    if (root / "results.json").exists():
        return cli.main([*command, "--replay-only"])
    if args.resume:
        command.append("--resume")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".audit.lock").open("a"):
        pass
    with (root / "supervisor.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (root / "supervisor.log").open("a", buffering=1) as log:
            def event(stage, **details):
                row = {"stage": stage, "time_utc": datetime.now(timezone.utc).isoformat(), **details}
                with (root / ".audit.lock").open("rb") as guard:
                    fcntl.flock(guard, fcntl.LOCK_SH)
                    print(json.dumps(row), file=log, flush=True)
                    print(json.dumps(row), flush=True)
            child = subprocess.Popen([sys.executable, "-B", "-u", str(REPO / "scripts/coevolution_v18.py"),
                                      *command], cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
            event("started", child_pid=child.pid, automatic_restart=False)
            wall, mono = time.time(), time.monotonic()
            while child.poll() is None:
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    now_wall, now_mono = time.time(), time.monotonic()
                    evidence = suspend_evidence(wall, mono, now_wall, now_mono)
                    wall, mono = now_wall, now_mono
                    with (root / ".audit.lock").open("rb") as audit:
                        try:
                            fcntl.flock(audit, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        except BlockingIOError:
                            continue
                        if (root / "results.json").exists():
                            continue
                        if evidence["pause_needed"] and not (root / "PAUSE").exists():
                            (root / "PAUSE").touch()
                            event("suspend_pause_requested", **evidence, inflight_preserved=True)
                        event("heartbeat", child_pid=child.pid,
                              calls=len(list((root / "api/calls").glob("*.json"))),
                              pause_requested=(root / "PAUSE").exists())
            event("finished" if child.returncode == 0 else "paused" if child.returncode == 75 else "stopped",
                  returncode=child.returncode, automatic_retry=False, evidence_preserved=True)
            return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
