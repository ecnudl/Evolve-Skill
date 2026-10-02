"""Read-only experiment observer; never submits, resumes, kills or repairs jobs.

Run outside frozen experiment roots. Snapshots are operational observations,
not authenticated benchmark reports. Only allowlisted metadata is emitted;
model outputs, prompts, hidden tests, environment and raw logs stay private.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = "experiment-observer-v4"
KINDS = {"eval", "learning", "recovery", "full_delivery_recovery", "single_delivery_recovery"}
DELIVERY_KINDS = {"recovery", "full_delivery_recovery", "single_delivery_recovery"}

SAFE_CODES = frozenset("""
pass fail unknown pending completed complete incomplete not_started available stop length max_tokens
content_filter tool_calls function_call native_timeout native_execution_unavailable invalid_native_receipt
native_reflection_parse_incomplete native_reflection_incomplete native_optimizer_incomplete
native_optimizer_response_unknown earlier_native_optimizer_failure unknown_is_not_failure_feedback
native_proposal_interrupted_no_automatic_resume native_candidate_exceeds_skill_budget
interrupted_stage_no_automatic_optimizer_resume native_skillopt_development_selection
official_gepa_development_selection reflection_unavailable incomplete_usage interrupted_model_call
previous_call_usage_or_receipt_unknown max_api_calls max_reflection_calls reported_token_stop_threshold
invalid_candidate_skill_length native_dependency_unavailable container_cleanup_unconfirmed
model_response_truncated model_response_unavailable model_response_incomplete prediction_unavailable
operator_closed_interrupted_attempt unsupported_full_episode_resume
""".split())


def _read(path):
    if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("unsupported_observation_file")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("observation_not_object")
    return value


def _reason(value):
    # A syntactically simple string can still be a credential or model text.
    # Unknown codes remain explicitly redacted, never silently successful.
    return value if isinstance(value, str) and value in SAFE_CODES else "not_exported"


def _targets(value):
    if not isinstance(value, list) or not value:
        raise ValueError("nonempty_monitor_targets_required")
    for target in value:
        if not isinstance(target, dict) or target.get("kind") not in KINDS:
            raise ValueError("invalid_monitor_target")
        if not isinstance(target.get("root"), str) or not Path(target["root"]).is_absolute():
            raise ValueError("invalid_monitor_target")
        if not isinstance(target.get("label"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", target["label"]):
            raise ValueError("invalid_monitor_label")
        expected = target.get("expected_positions")
        if expected is not None and (type(expected) is not int or expected < 1):
            raise ValueError("invalid_expected_positions")
    return value


def observe(target, *, processes=(), now=None):
    _targets([target])
    root = Path(target["root"]).resolve()
    kind = target["kind"]
    if kind not in KINDS or not Path(target["root"]).is_absolute():
        raise ValueError("invalid_monitor_target")
    now = time.time() if now is None else now
    if kind == "eval":
        score_pattern, call_pattern = "host_only/scores/*.json", "predictions/*/calls/*.json"
        intent_pattern = "predictions/*/call_intents/*.json"
    elif kind == "learning":
        score_pattern, call_pattern = "evaluations/*.json", "calls/*.json"
        intent_pattern = "call_intents/*.json"
    elif kind == "single_delivery_recovery":
        score_pattern, call_pattern, intent_pattern = "result.json", "call.json", "intent.json"
    else:
        score_pattern, call_pattern = "positions/*/result.json", "positions/*/call.json"
        intent_pattern = "positions/*/intent.json" if kind == "full_delivery_recovery" else "positions/*/call_intent.json"
    errors, mtimes, record_paths = Counter(), [], {}

    def records(pattern):
        result = []
        record_paths[pattern] = []
        for path in root.glob(pattern):
            # The immutable writer publishes .pending-*.json with a hardlink,
            # then unlinks the temporary name. These are not logical records:
            # reading them can duplicate costs or race with the final unlink.
            if path.name.startswith("."):
                continue
            try:
                if not path.resolve().is_relative_to(root):
                    raise ValueError("observation_outside_root")
                value = _read(path)
                modified = path.stat().st_mtime
                result.append(value)
                record_paths[pattern].append(path)
                mtimes.append(modified)
            except (OSError, ValueError) as exc:
                errors[type(exc).__name__] += 1
        return result

    raw_scores, raw_calls = records(score_pattern), records(call_pattern)
    scores, calls = [], []
    for row in raw_scores:
        value = row if kind == "eval" else row.get("score")
        if not isinstance(value, dict) or value.get("status") not in ("pass", "fail", "unknown"):
            errors["invalid_score_record"] += 1
        else:
            scores.append(value)
    closed_paths = set()
    for path, row in zip(record_paths[call_pattern], raw_calls):
        value = row.get("receipt")
        if (not isinstance(value, dict) or not isinstance(value.get("usage", {}), dict)
                or type(value.get("ok")) is not bool
                or type(value.get("http_attempt_count")) is not int or value["http_attempt_count"] < 1):
            errors["invalid_call_record"] += 1
        else:
            calls.append(value)
            closed_paths.add(path)
    intents = [path for path in root.glob(intent_pattern) if not path.name.startswith(".")]
    expected_calls = {p.parent / "call.json" if kind in DELIVERY_KINDS else p.parent.parent / "calls" / p.name
                      for p in intents}
    intent_count = len(intents)
    unclosed = len(expected_calls - closed_paths)
    orphan_receipts = len(closed_paths - expected_calls)
    known_tokens = missing_usage = http = 0
    for call in calls:
        usage = call.get("usage", {})
        if all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
            known_tokens += usage["prompt_tokens"] + usage["completion_tokens"]
        else:
            missing_usage += 1
        count = call.get("http_attempt_count")
        if type(count) is int and count >= 0:
            http += count
    terminal = records("result.json") if kind == "learning" else []
    terminal_state = terminal[0].get("status") if terminal else None
    expected = target.get("expected_positions")
    if kind == "learning":
        state = _reason(terminal_state) if terminal else "not_started" if not root.exists() else "incomplete"
    else:
        state = "complete" if expected is not None and len(scores) == expected \
            and not (errors or unclosed or orphan_receipts) else "incomplete"
    newest = max(mtimes) if mtimes else None
    return {
        "label": target["label"], "kind": kind, "root": str(root), "status": state,
        "status_is_operational_not_validated_report": True,
        "process_seen": any(str(root) in command and ("python" in command or "flock" in command)
                            for command in processes),
        "expected_positions": expected, "scored_positions": len(scores),
        "score_counts": dict(Counter(_reason(r.get("status")) for r in scores)),
        "unknown_reasons": dict(Counter(_reason(r.get("reason")) for r in scores if r.get("status") == "unknown")),
        "closed_calls": len(calls), "finish_reasons": dict(Counter(_reason(r.get("finish_reason")) for r in calls)),
        "call_intents": intent_count, "unclosed_calls": unclosed,
        "receipts_without_intents": orphan_receipts,
        "http_attempts_known": http, "reported_tokens_known": known_tokens, "missing_usage_calls": missing_usage,
        "usage_complete": not (unclosed or orphan_receipts or missing_usage or errors),
        "retry_inclusive_usage_known": not (unclosed or orphan_receipts or missing_usage or errors)
            and all(r.get("http_attempt_count") == 1 for r in calls),
        "terminal_reason": _reason(terminal[0].get("reason")) if terminal else None,
        "terminal_hash": terminal[0].get("record_hash") if terminal and isinstance(terminal[0].get("record_hash"), str)
            and re.fullmatch(r"[0-9a-f]{64}", terminal[0]["record_hash"]) else None,
        "seconds_since_new_evidence": max(0, now - newest) if newest is not None else None,
        "observation_errors": dict(errors), "can_authorize_deployment": False,
    }


def collect(config):
    targets = _targets(config if isinstance(config, list) else json.loads(Path(config).read_text()))
    result = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=10, check=False)
    processes = result.stdout.splitlines() if result.returncode == 0 else []
    return {"version": VERSION, "captured_at": datetime.now(timezone.utc).isoformat(),
            "process_observation_available": result.returncode == 0,
            "jobs": [observe(target, processes=processes) for target in targets],
            "actions_taken": [], "model_calls": 0}


def _append_file(path):
    """Reject pre-existing symlinks/hardlinks before appending observer data."""
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(descriptor)
        raise ValueError("unsafe_observer_output")
    return os.fdopen(descriptor, "a")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--hours", type=float, default=12)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not 10 <= args.interval <= 60 or not 0 < args.hours <= 24:
        parser.error("interval must be 10..60 seconds and hours 0..24")
    output = Path(args.output).resolve()
    targets = _targets(json.loads(Path(args.config).read_text()))
    for target in targets:
        root = Path(target["root"]).resolve()
        if output == root or root in output.parents or output in root.parents:
            parser.error("monitor output must be outside experiment directories")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with _append_file(output / "observer.lock") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deadline = time.monotonic() + args.hours * 3600
        while True:
            try:
                # Freeze the validated roots; later config edits cannot bypass
                # the outside-experiment-directory checks above.
                value = collect(targets)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                value = {"version": VERSION, "captured_at": datetime.now(timezone.utc).isoformat(),
                         "observer_error": type(exc).__name__, "actions_taken": [], "model_calls": 0}
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
            with _append_file(output / "observations.jsonl") as stream:
                stream.write(raw + "\n")
            with tempfile.NamedTemporaryFile(mode="w", dir=output, prefix=".latest.", delete=False) as stream:
                stream.write(raw + "\n")
                temporary_path = stream.name
            os.replace(temporary_path, output / "latest.json")
            print(raw, flush=True)
            if args.once or time.monotonic() >= deadline:
                return 0
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    raise SystemExit(main())
