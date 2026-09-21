"""Operational resume overlay; never edit frozen sources or resample missing replies.

Only development collection is permitted. The original protocol remains intact;
the separate amendment discloses a lower transport concurrency, circuit breaker,
and explicit local unknown for a previously interrupted request. It does NOT
invent an API receipt or change any existing score or response.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import signal
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.models import require
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import digest, write_immutable_json


class RecoveryPause(RuntimeError):
    pass


def read(path):
    return verify(json.loads(Path(path).read_text()))


class RecoveryControl:
    def __init__(self, root, pause_path, *, concurrency=2, max_new=24, min_idle_seconds=0,
                 launch_window_seconds=0):
        self.root = Path(root).resolve()
        self.pause = read(pause_path)
        self.protocol = read(self.root / "protocol.json")
        require(self.pause["protocol_hash"] == self.protocol["record_hash"], "Pause protocol mismatch")
        require(1 <= concurrency <= 4 and 1 <= max_new <= 256, "Bounded recovery limits required")
        require(type(min_idle_seconds) is int and 0 <= min_idle_seconds <= 60,
                "Recovery idle interval must be 0..60 seconds")
        require(not min_idle_seconds or concurrency == 1, "Paced recovery requires single concurrency")
        require(type(launch_window_seconds) is int and 0 <= launch_window_seconds <= 60,
                "Launch window must be 0..60 seconds")
        self.concurrency, self.max_new = concurrency, max_new
        self.min_idle_seconds = min_idle_seconds
        self.launch_window_seconds = launch_window_seconds
        self.window_start, self.window_used = time.monotonic(), 0
        self.semaphore = threading.BoundedSemaphore(concurrency)
        self.lock, self.stopped = threading.Lock(), threading.Event()
        self.request_locks, self.started, self.failures = {}, [], []
        self.reason = None
        self.resolutions = {}
        for entry in self.pause["unclosed_requests"]:
            request, identifier = entry["request"], entry["request_hash"]
            require(digest(request) == identifier and identifier not in self.resolutions, "Interrupted request mismatch")
            expected_key = digest({"protocol": self.protocol["record_hash"], **{
                k: request[k] for k in ("system", "user", "kind", "repeat", "max_tokens")}})
            require(request["key"] == expected_key and request["service"] == self.protocol["service"]
                    and request["model"] == self.protocol["service"]["model"]
                    and request["kind"] == "natural-solver", "Interrupted request is outside frozen solver")
            intent = read(self.root / "model_budget/intents" / (identifier + ".json"))
            require(intent == seal({"request_hash": identifier, "protocol_hash": self.protocol["record_hash"],
                                   "kind": request["kind"], "repeat": request["repeat"]}), "Interrupted intent mismatch")
            require(not (self.root / "api/calls" / (identifier + ".json")).exists(), "Terminal reply must not be replaced")
            self.resolutions[identifier] = seal({
                "kind": "local_interrupted_unknown", "request_hash": identifier, "request": request,
                "protocol_hash": self.protocol["record_hash"], "pause_hash": self.pause["record_hash"],
                "provider_reply_observed": False, "new_request_sent": False,
                "ok": False, "response": "", "error_type": "local_interrupted_unknown",
                "status": None, "http_attempt_count": None, "usage": None,
                "information_origin": "host_recovery_control_not_provider_receipt",
            })
        intents = {p.stem for p in (self.root / "model_budget/intents").glob("*.json")}
        terminals = {p.stem for p in (self.root / "api/calls").glob("*.json")}
        require(intents - terminals == set(self.resolutions), "Additional interruption requires explicit review")

    def stop(self, reason):
        with self.lock:
            if self.reason is None:
                self.reason = reason
            self.stopped.set()

    def reserve_launch(self, identifier):
        """Limit fresh logical requests per time window; cache hits consume none."""
        while True:
            with self.lock:
                if self.stopped.is_set():
                    raise RecoveryPause(self.reason)
                if len(self.started) >= self.max_new:
                    self.reason = "new_request_chunk_limit"
                    self.stopped.set()
                    raise RecoveryPause(self.reason)
                now = time.monotonic()
                if now - self.window_start >= self.launch_window_seconds:
                    self.window_start, self.window_used = now, 0
                if not self.launch_window_seconds or self.window_used < self.concurrency:
                    self.window_used += 1
                    self.started.append(identifier)
                    return
                remaining = max(0., self.window_start + self.launch_window_seconds - now)
            if self.stopped.wait(remaining):
                raise RecoveryPause(self.reason)

    def _call(self, original, caller, system, user, kind, *, repeat=0, max_tokens=2048):
        require(Path(caller.root).resolve() == self.root / "model_budget"
                and caller.protocol_hash == self.protocol["record_hash"], "Recovery caller scope mismatch")
        require(kind == "natural-solver", "Recovery overlay only permits solver collection")
        key = digest({"protocol": caller.protocol_hash, "system": system, "user": user,
                      "kind": kind, "repeat": repeat, "max_tokens": max_tokens})
        request = {"model": caller.api.model, "system": system, "user": user, "kind": kind,
                   "key": key, "repeat": repeat, "max_tokens": max_tokens, "service": caller.api.service}
        identifier = digest(request)
        with self.lock:
            request_lock = self.request_locks.setdefault(identifier, threading.Lock())
        with request_lock:
            terminal = caller.api.root / "calls" / (identifier + ".json")
            if identifier in self.resolutions:
                require(not terminal.exists(), "Late terminal response needs separate review")
                result = self.resolutions[identifier]
                write_immutable_json(self.root / "resume_control/local_unknown" / (identifier + ".json"), result)
                return result
            if terminal.exists():
                return original(caller, system, user, kind, repeat=repeat, max_tokens=max_tokens)
            with self.semaphore:
                with self.lock:
                    if self.stopped.is_set():
                        raise RecoveryPause(self.reason)
                    if len(self.started) >= self.max_new:
                        self.reason = "new_request_chunk_limit"
                        self.stopped.set()
                        raise RecoveryPause(self.reason)
                # Includes the first new request, so a just-finished health check
                # does not turn into a burst. Cached results never incur a delay.
                # Waiting holds the single network slot, not a request intent.
                if self.min_idle_seconds and self.stopped.wait(self.min_idle_seconds):
                    raise RecoveryPause(self.reason)
                self.reserve_launch(identifier)
                try:
                    result = original(caller, system, user, kind, repeat=repeat, max_tokens=max_tokens)
                except Exception:
                    self.stop("request_or_cache_error")
                    raise
                if result.get("ok") is not True:
                    with self.lock:
                        self.failures.append(identifier)
                    self.stop("new_terminal_api_failure")
                return result

    @contextmanager
    def active(self):
        original = BoundedCalls.call
        control = self

        def guarded(caller, *args, **kwargs):
            return control._call(original, caller, *args, **kwargs)

        with patch.object(BoundedCalls, "call", guarded):
            yield self

    def summary(self):
        return {"new_requests_started": len(self.started), "new_request_hashes": list(self.started),
                "actual_max_api_concurrency": self.concurrency,
                "minimum_idle_seconds_between_logical_calls": self.min_idle_seconds,
                "launch_window_seconds": self.launch_window_seconds,
                "max_new_logical_requests_per_window": self.concurrency if self.launch_window_seconds else None,
                "new_terminal_api_failures": list(self.failures), "stop_reason": self.reason,
                "local_interrupted_unknown_count": len(self.resolutions),
                "unobserved_interrupted_request_http_and_token_cost": None,
                "original_provider_receipts_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pause", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--reuse-from", type=Path, required=True)
    parser.add_argument("--public-preflight", type=Path, required=True)
    parser.add_argument("--health-summary", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--min-idle-seconds", type=int, default=30)
    parser.add_argument("--launch-window-seconds", type=int, default=0)
    parser.add_argument("--max-new", type=int, default=24)
    args = parser.parse_args()
    require(args.session and all(c.isalnum() or c in "-_" for c in args.session), "Invalid session label")
    repo, root = args.repo.resolve(), args.output.resolve()
    control = RecoveryControl(root, args.pause, concurrency=args.concurrency, max_new=args.max_new,
                              min_idle_seconds=args.min_idle_seconds,
                              launch_window_seconds=args.launch_window_seconds)
    current_sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (repo / "skillopt/skill_validation").glob("*.py")}
    require(current_sources == control.protocol["source_hashes"], "Frozen source changed; do not resume in place")
    health = read(args.health_summary)
    require(health.get("all_requests_completed") is True and health.get("all_first_attempt") is True
            and len(health.get("calls", [])) >= 6 and health.get("concurrency") >= args.concurrency,
            "Representative low-concurrency health check required")
    completed = datetime.fromisoformat(health.get("completed_utc", ""))
    require(completed.tzinfo is not None
            and 0 <= (datetime.now(timezone.utc) - completed).total_seconds() <= 900,
            "A fresh health check completed within 15 minutes is required")
    require(args.min_idle_seconds >= health.get("minimum_idle_seconds_between_logical_calls", 0),
            "Recovery must not outpace its health check")
    require(args.launch_window_seconds >= health.get("minimum_idle_seconds_between_waves", 0),
            "A burst health check requires a matching or slower launch window")
    destination = root / "resume_control" / args.session
    require(not destination.exists(), "Use a new operational session label")
    amendment = seal({"kind": "operational_recovery_overlay", "protocol_hash": control.protocol["record_hash"],
        "pause_hash": control.pause["record_hash"], "health_hash": health["record_hash"],
        "overlay_source_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "original_protocol_workers": control.protocol["workers"], "actual_max_api_concurrency": args.concurrency,
        "minimum_idle_seconds_between_logical_calls": args.min_idle_seconds,
        "initial_idle_seconds": args.min_idle_seconds,
        "launch_window_seconds": args.launch_window_seconds,
        "max_new_logical_requests_per_window": args.concurrency if args.launch_window_seconds else None,
        "intra_request_retries_keep_original_frozen_backoff": True,
        "max_new_requests_this_session": args.max_new, "stop_after": "development",
        "local_unknown_request_hashes": sorted(control.resolutions),
        "source_protocol_and_existing_receipts_preserved": True,
        "transport_schedule_changed": True, "no_research_updater_calibration_or_final": True,
        "audit_contract_disputes_unresolved": True})
    write_immutable_json(destination / "amendment.json", amendment)
    write_immutable_json(destination / "overlay_source.json", seal({"path": str(Path(__file__).resolve()),
        "sha256": amendment["overlay_source_hash"], "content": Path(__file__).read_text()}))
    old_signals = {s: signal.signal(s, lambda *_: control.stop("requested_graceful_stop"))
                   for s in (signal.SIGINT, signal.SIGTERM)}
    status, error_type, executor = "paused", None, None
    try:
        from skillopt.skill_validation import natural_study
        # Preserve the frozen SSH transport as well as the Docker policy. A
        # local-Docker migration requires its own identity and reviewed protocol;
        # do not relabel local execution as the original SSH transport.
        executor = natural_study.ExecutorPool(args.remote_repo,
                                               workers=control.protocol["transport"]["parallel_ssh_workers"])
        with control.active():
            natural_study.run(repo, root, executor, workers=control.protocol["workers"],
                              repeats=control.protocol["repeats"], update_repeats=control.protocol["update_repeats"],
                              stop_after="development", reuse_from=args.reuse_from.resolve(),
                              public_preflight=args.public_preflight.resolve())
        status = "development_complete"
    except RecoveryPause:
        pass
    except Exception as exc:
        # Exception strings may include credentials or private request content.
        status, error_type = "blocked", type(exc).__name__
    finally:
        if executor is not None:
            executor.close()
        for signum, handler in old_signals.items():
            signal.signal(signum, handler)
        result = seal({"status": status, "error_type": error_type,
                       "amendment_hash": amendment["record_hash"],
                       **control.summary()})
        write_immutable_json(destination / "summary.json", result)
        print(json.dumps(result), flush=True)
    return 1 if status == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
