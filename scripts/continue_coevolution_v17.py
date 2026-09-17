"""One-shot operational queue: audited smoke -> prepared pilot -> optional analysis.

No API, automatic retry/resume, score selection, or frozen-source mutation.
A durable launch intent prevents another start even after a queue crash.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
WAIT_SECONDS = 1800
POLL_SECONDS = 30
VERSION = "v17-operational-one-shot-queue-v1"


def _study():
    from skillopt.coevolution_v17 import study
    return study


def supervisor_state(root):
    """Only the latest supervisor session can supply a terminal/audit pair."""
    path = Path(root) / "supervisor.log"
    terminal = audit = None
    if not path.is_file():
        return terminal, audit
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if type(row) is not dict:
            continue
        if row.get("stage") == "started" and "child_pid" in row:
            terminal = audit = None
        elif row.get("offline_verified") is True and row.get("complete") is True:
            audit = row
        elif row.get("stage") in {"finished", "stopped", "paused"} and "returncode" in row:
            terminal = row
    return terminal, audit


def last_supervisor_terminal(root):
    return supervisor_state(root)[0]


def ready(repo, smoke):
    """Operational readiness only: ignore scientific scores and gate decisions."""
    study = _study()
    smoke = Path(smoke)
    if (smoke / "PAUSE").exists():
        return "stop", "explicit_smoke_pause"
    terminal, audit = supervisor_state(smoke)
    if terminal is None:
        return "wait", "smoke_not_yet_audited_and_reported"
    if terminal.get("returncode") != 0 or terminal.get("stage") != "finished":
        return "stop", "smoke_supervisor_failed_or_paused"
    try:
        protocol, result = study.read(smoke / "protocol.json"), study.read(smoke / "results.json")
        if (protocol.get("design") != "smoke" or result.get("design") != "smoke"
                or result.get("complete") is not True
                or result.get("protocol_hash") != protocol["record_hash"]
                or study.source_hashes(repo) != protocol.get("source_hashes")):
            return "stop", "smoke_identity_or_frozen_source_mismatch"
        if audit is None or audit.get("result_hash") != result["record_hash"]:
            return "stop", "missing_result_bound_offline_audit"
        ledger, learning = result["ledger"], result["learning"]
        calls, errors, valid = ledger["cached_logical_calls"], ledger["terminal_errors"], learning["valid"]
        if (type(calls) is not int or type(errors) is not int or type(valid) is not int
                or calls <= 0 or not 0 <= errors <= calls or valid < 0):
            return "stop", "malformed_smoke_health_receipt"
        if errors / calls > 0.10 or valid == 0:
            return "stop", "smoke_transport_or_learning_delivery_unhealthy"
    except (OSError, ValueError, KeyError, TypeError):
        return "stop", "missing_or_invalid_smoke_evidence"
    return "ready", "audited_smoke_complete_independent_of_scientific_scores"


def prepared_pilot(repo, root):
    """Only an untouched, independently prepared pilot may be launched."""
    study = _study()
    root = Path(root)
    protocol = study.read(root / "protocol.json")
    if protocol.get("design") != "pilot" or protocol.get("source_hashes") != study.source_hashes(repo):
        raise ValueError("Pilot must already be prepared with exactly the frozen sources")
    for name, field in (("private_panel.json", "panel_hash"),
                        ("source_snapshot.json", "source_snapshot_hash"),
                        ("task_preflight.json", "preflight_hash")):
        record = study.read(root / name)
        if record["record_hash"] != protocol.get(field):
            raise ValueError("Prepared dependency differs from protocol: " + name)
        if name == "task_preflight.json" and record.get("all_checked") is not True:
            raise ValueError("Prepared pilot lacks successful preflight")
    if any((root / name).exists() for name in (
            "results.json", "supervisor.log", "headroom.json", "final_frozen.json")):
        raise ValueError("Pilot already started/completed; no automatic retry/resume")
    for name in ("api", "runtime", "learning", "learning_intents", "events"):
        if any(path.is_file() for path in (root / name).rglob("*")):
            raise ValueError("Pilot has prior runtime/API activity; never resume automatically")
    return protocol


def _smoke_lock_held(smoke):
    path = Path(smoke) / "supervisor.lock"
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def _paused(*roots):
    return any((Path(root) / "PAUSE").exists() for root in roots)


def _exclusive_intent(path, value):
    """Durably reserve the one launch BEFORE process creation."""
    from skillopt.coevolution_v5.core import seal
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(seal(value), handle, ensure_ascii=False, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(str(Path(path).parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _monitor_pilot(command, *, repo, smoke, pilot, queue, log, event):
    child = subprocess.Popen(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT)
    event("pilot_supervisor_started", child_pid=child.pid, automatic_retry=False)
    pause_forwarded = False
    while child.poll() is None:
        if _paused(smoke, pilot, queue) and not pause_forwarded:
            (pilot / "PAUSE").touch(exist_ok=True)
            pause_forwarded = True
            event("pilot_pause_requested", inflight_drained_before_stop=True, automatic_resume=False)
        try:
            child.wait(timeout=POLL_SECONDS)
        except subprocess.TimeoutExpired:
            event("monitoring_registered_pilot", child_pid=child.pid,
                  pause_requested=pause_forwarded, automatic_retry=False)
    code = child.returncode
    event("pilot_finished" if code == 0 else "paused" if code == 75 else "stopped",
          returncode=code, automatic_retry=False, launch_intent_retained=True)
    return code


def _analysis(repo, pilot, report, expected_hash, log, event):
    """One optional read-only analysis subprocess after successful pilot audit."""
    study = _study()
    script = Path(repo) / "scripts/analyze_coevolution_v17.py"
    terminal, audit = supervisor_state(pilot)
    result, protocol = study.read(pilot / "results.json"), study.read(pilot / "protocol.json")
    if (terminal is None or terminal.get("stage") != "finished" or terminal.get("returncode") != 0
            or audit is None or audit.get("result_hash") != result["record_hash"]
            or result.get("complete") is not True or result.get("protocol_hash") != protocol["record_hash"]
            or hashlib.sha256(script.read_bytes()).hexdigest() != expected_hash):
        event("analysis_not_started", reason="pilot_audit_or_analysis_source_mismatch")
        return 1
    command = [sys.executable, "-B", "-u", str(script), "--output", str(pilot), "--report", str(report)]
    event("starting_read_only_analysis", command=command, api_calls=0, automatic_retry=False)
    code = subprocess.run(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT).returncode
    event("analysis_finished" if code == 0 else "analysis_failed", returncode=code, automatic_retry=False)
    return code


def main(argv=None):
    from scripts.coevolution_v17 import report_path
    study = _study()
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("smoke", "pilot", "queue", "report"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--analysis-report", type=Path)
    args = parser.parse_args(argv)
    smoke, pilot, queue = (study.safe_root(REPO, p) for p in (args.smoke, args.pilot, args.queue))
    if (len({smoke, pilot, queue}) != 3
            or any(a.is_relative_to(b) for a in (smoke, pilot, queue) for b in (smoke, pilot, queue) if a != b)):
        parser.error("Disjoint smoke, prepared pilot and operational queue roots required")
    if queue.parent != REPO / "outputs/coevolution_v17" or not queue.name.startswith("queue_"):
        parser.error("Queue must be outputs/coevolution_v17/queue_...")
    report = report_path(REPO, args.report)
    analysis_report = report_path(REPO, args.analysis_report) if args.analysis_report else None
    analyzer = REPO / "scripts/analyze_coevolution_v17.py"
    if analysis_report and (analysis_report == report or not analyzer.is_file() or analyzer.is_symlink()):
        parser.error("Optional analysis requires an existing script and a separate nonsource report")
    analysis_hash = hashlib.sha256(analyzer.read_bytes()).hexdigest() if analysis_report else None
    pilot_protocol = prepared_pilot(REPO, pilot)
    smoke_protocol = study.read(smoke / "protocol.json")
    if (smoke_protocol.get("design") != "smoke"
            or smoke_protocol.get("source_hashes") != pilot_protocol["source_hashes"]):
        parser.error("Smoke and pilot must share their frozen source map")
    queue.mkdir(parents=True, exist_ok=True)
    with (queue / "queue.lock").open("a+") as lock, (queue / "queue.log").open("a", buffering=1) as log:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def event(stage, **details):
            row = {"version": VERSION, "time_utc": datetime.now(timezone.utc).isoformat(),
                   "stage": stage, **details}
            print(json.dumps(row, ensure_ascii=False), file=log, flush=True)
            os.fsync(log.fileno())
        if (queue / "launch_intent.json").exists():
            event("stopped_without_launch", reason="prior_launch_intent_never_retry_or_resume")
            return 75
        settings = {"version": VERSION, "smoke": str(smoke), "pilot": str(pilot), "report": str(report),
                    "smoke_protocol_hash": smoke_protocol["record_hash"],
                    "pilot_protocol_hash": pilot_protocol["record_hash"],
                    "queue_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "analysis_report": str(analysis_report) if analysis_report else None,
                    "analysis_script_sha256": analysis_hash,
                    "maximum_smoke_wait_seconds": WAIT_SECONDS, "automatic_retry": False}
        plan_path = queue / "queue_plan.json"
        if plan_path.exists():
            plan = study.read(plan_path)
            if any(plan.get(key) != value for key, value in settings.items()):
                event("stopped_without_launch", reason="operational_queue_configuration_changed")
                return 1
        else:
            plan = study.save(plan_path, {**settings, "created_unix": time.time()})
        if type(plan.get("created_unix")) not in (float, int):
            event("stopped_without_launch", reason="invalid_queue_start_time")
            return 1
        started_mono = time.monotonic()
        event("queued", **settings, operational_health_not_model_score_selection=True)
        while True:
            if _paused(smoke, pilot, queue):
                event("stopped_without_launch", reason="explicit_smoke_queue_or_pilot_pause")
                return 75
            elapsed = max(time.time() - plan["created_unix"], time.monotonic() - started_mono)
            if elapsed >= WAIT_SECONDS:
                event("stopped_without_launch", reason="smoke_wait_timeout", elapsed_seconds=elapsed)
                return 75
            state, reason = ready(REPO, smoke)
            if state == "stop":
                event("stopped_without_launch", reason=reason)
                return 75
            if state == "ready":
                break
            if not _smoke_lock_held(smoke):
                state, reason = ready(REPO, smoke)
                if state == "ready":
                    break
                event("stopped_without_launch", reason="smoke_supervisor_exited_without_success",
                      last_readiness_reason=reason)
                return 1
            event("waiting_for_audited_smoke", elapsed_seconds=elapsed)
            time.sleep(min(POLL_SECONDS, WAIT_SECONDS - elapsed))
        if _paused(smoke, pilot, queue):
            event("stopped_without_launch", reason="explicit_pause_before_launch")
            return 75
        if (prepared_pilot(REPO, pilot) != pilot_protocol
                or study.read(smoke / "protocol.json") != smoke_protocol
                or ready(REPO, smoke)[0] != "ready"):
            event("stopped_without_launch", reason="prepared_pilot_or_smoke_changed")
            return 1
        result = study.read(smoke / "results.json")
        command = [sys.executable, "-B", "-u", str(REPO / "scripts/launch_coevolution_v17.py"),
                   "--output", str(pilot), "--design", "pilot", "--report", str(report)]
        _exclusive_intent(queue / "launch_intent.json", {**settings,
            "smoke_result_hash": result["record_hash"], "command": command,
            "created_unix": time.time(), "scientific_score_selection": False})
        event("launching_registered_pilot", command=command,
              max_calls=pilot_protocol.get("max_calls"), durable_launch_intent=True)
        try:
            code = _monitor_pilot(command, repo=REPO, smoke=smoke, pilot=pilot,
                                  queue=queue, log=log, event=event)
            if code == 0 and analysis_report:
                if _paused(smoke, pilot, queue):
                    event("analysis_not_started", reason="explicit_pause")
                    return 75
                code = _analysis(REPO, pilot, analysis_report, analysis_hash, log, event)
            event("finished" if code == 0 else "stopped", returncode=code, automatic_retry=False)
            return code
        except BaseException as error:
            event("stopped_after_launch_intent", exception_type=type(error).__name__,
                  automatic_retry=False, launch_intent_retained=True)
            raise


if __name__ == "__main__":
    raise SystemExit(main())
