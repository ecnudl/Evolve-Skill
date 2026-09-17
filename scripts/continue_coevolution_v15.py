"""Queue exactly the registered pilot after a completed, audited smoke run.

Operational only: no model calls, evaluator edits, automatic retries, result
selection, or source changes. Pause/failure stops the queue instead of resuming.
"""

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


def last_supervisor_terminal(root):
    path = Path(root) / "supervisor.log"
    if not path.exists():
        return None
    found = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if type(row) is dict and row.get("stage") in {"finished", "stopped", "paused"} and "returncode" in row:
            found = row
    return found


def ready(repo, smoke):
    from skillopt.coevolution_v12.study import read
    from skillopt.coevolution_v15.study import source_hashes
    smoke = Path(smoke)
    if (smoke / "PAUSE").exists():
        return "stop", "explicit_pause"
    terminal = last_supervisor_terminal(smoke)
    if terminal is None:
        return "wait", "smoke_not_yet_audited_and_reported"
    if terminal.get("returncode") != 0 or terminal.get("stage") != "finished":
        return "stop", "smoke_supervisor_failed_or_paused"
    protocol, result = read(smoke / "protocol.json"), read(smoke / "results.json")
    if (protocol["design"] != "smoke" or result["design"] != "smoke" or result["complete"] is not True
            or result["protocol_hash"] != protocol["record_hash"]
            or source_hashes(repo) != protocol["source_hashes"]):
        return "stop", "smoke_identity_or_frozen_source_mismatch"
    # Health/delivery feasibility only, NEVER select on scores or acceptance.
    ledger = result["ledger"]
    if (ledger["cached_logical_calls"] <= 0
            or ledger["terminal_errors"] / ledger["cached_logical_calls"] > 0.10
            or result["learning"]["valid"] == 0
            or result["validator_evolution"]["valid_proposals"] == 0):
        return "stop", "smoke_transport_or_delivery_not_ready_for_larger_run"
    return "ready", "audited_smoke_complete_independent_of_scientific_scores"


def main(argv=None):
    from skillopt.coevolution_v12.study import read
    from skillopt.coevolution_v15.study import safe_root, source_hashes
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    smoke, pilot, queue = (safe_root(REPO, p) for p in (args.smoke, args.pilot, args.queue))
    if len({smoke, pilot, queue}) != 3:
        parser.error("Separate smoke, prepared pilot and operational queue roots required")
    report = args.report.absolute()
    if (any(p.is_symlink() for p in (report, *report.parents)) or report.suffix != ".md"
            or not report.is_relative_to(REPO / "docs") or report.name == "coevolution-v15-protocol.md"):
        parser.error("Report must be a nonsource Markdown file beneath docs")
    pilot_protocol = read(pilot / "protocol.json")
    if pilot_protocol["design"] != "pilot" or pilot_protocol["source_hashes"] != source_hashes(REPO):
        parser.error("Pilot must already be prepared with the current frozen sources")
    if (pilot / "results.json").exists():
        parser.error("Pilot is already completed; no extra run authorized")
    queue.mkdir(parents=True, exist_ok=True)
    with (queue / "queue.lock").open("a+") as lock, (queue / "queue.log").open("a", buffering=1) as log:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def event(stage, **details):
            value = {"time_utc": datetime.now(timezone.utc).isoformat(), "stage": stage, **details}
            print(json.dumps(value), file=log, flush=True)
        event("queued", smoke=str(smoke), pilot=str(pilot),
              operational_health_not_model_score_selection=True, automatic_retry=False)
        while True:
            state, reason = ready(REPO, smoke)
            if (queue / "PAUSE").exists() or (pilot / "PAUSE").exists():
                state, reason = "stop", "explicit_queue_or_pilot_pause"
            if state == "stop":
                event("stopped_without_launch", reason=reason)
                return 75
            if state == "ready":
                break
            # A dead smoke supervisor with no terminal receipt cannot authorize
            # a launch. A still-held lock is stronger than a possibly reused PID.
            path = smoke / "supervisor.lock"
            if not path.is_file():
                event("stopped_without_launch", reason="missing_smoke_supervisor_lock")
                return 1
            with path.open("rb") as probe:
                try:
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    # Recheck the success receipt after acquiring the released
                    # lock, covering normal supervisor exit during this poll.
                    if ready(REPO, smoke)[0] != "ready":
                        event("stopped_without_launch", reason="smoke_supervisor_exited_without_success")
                        return 1
                    break
            event("waiting_for_audited_smoke")
            time.sleep(30)
        if read(pilot / "protocol.json") != pilot_protocol or source_hashes(REPO) != pilot_protocol["source_hashes"]:
            event("stopped_without_launch", reason="prepared_pilot_changed")
            return 1
        command = [sys.executable, "-B", "-u", str(REPO / "scripts/launch_coevolution_v15.py"),
                   "--output", str(pilot), "--design", "pilot", "--report", str(report)]
        event("launching_registered_pilot", max_calls=pilot_protocol["max_calls"])
        code = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
        event("finished" if code == 0 else "stopped", returncode=code, automatic_retry=False)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
