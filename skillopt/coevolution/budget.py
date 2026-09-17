"""Thread-safe logical-request reservations around the existing PJLAB transport.

One process owns a run directory. Reservations precede transport execution and
survive process exit; an unresolved old reservation is never silently retried.
The wrapper adds no HTTP retries and never changes credentials or proxy settings.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from pathlib import Path

from skillopt.validator_pilot.api import CachedAPI, digest, write_immutable_json


class BudgetedAPI:
    def __init__(self, repo: Path, root: Path, max_calls: int = 1600, workers: int = 4, *, api=None):
        if type(max_calls) is not int or not 1 <= max_calls <= 1600:
            raise ValueError("max_calls must be an integer in [1,1600]")
        if type(workers) is not int or workers != 4:
            raise ValueError("Co-evolution uses a shared four-worker transport")
        self.root, self.max_calls, self.workers = Path(root), max_calls, workers
        self.api = api if api is not None else CachedAPI(repo, self.root, workers=workers,
                                                       stream=True, reasoning_effort="low")
        if Path(self.api.root).resolve() != self.root.resolve():
            raise ValueError("Wrapped API must use the same isolated cache root")
        self.model, self.service = self.api.model, self.api.service
        if self.model != "glm-5.3" or self.service.get("max_retries") != 2:
            raise ValueError("Requires glm-5.3 transport with at most three HTTP attempts per logical call")
        self._mutex = threading.Lock()
        self._request_locks = {}
        self._reserved = set()
        for path in sorted((self.root / "budget_reservations").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("request_hash") != path.stem:
                raise ValueError("Budget reservation identity mismatch")
            self._reserved.add(path.stem)
        cached = self._cached_records()
        self._reserved.update(cached)
        if len(self._reserved) > max_calls:
            raise ValueError("Existing logical reservations exceed the requested budget")
        self._unresolved = self._reserved - cached.keys()
        write_immutable_json(self.root / "budget_protocol.json", {
            "version": "coevolution-logical-budget-v1", "max_logical_calls": max_calls,
            "workers": workers, "model": self.model, "service_sha256": digest(self.service),
            "max_attempts_per_logical_call": 3, "max_planned_http_attempts": max_calls * 3,
            "client_mode": "provided_client" if api is not None else "pjlab_real",
            "one_process_per_run": True, "unresolved_reservation_policy": "stop_without_silent_retry"})

    def _cached_records(self):
        records = {}
        for path in sorted((self.root / "calls").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            request = record.get("request")
            if (not isinstance(request, dict) or record.get("request_hash") != path.stem
                    or digest(request) != path.stem or request.get("service") != self.service
                    or request.get("model") != self.model or type(record.get("ok")) is not bool):
                raise ValueError("Budget cache provenance mismatch")
            attempts = record.get("http_attempt_count")
            if type(attempts) is not int or not 1 <= attempts <= 3:
                raise ValueError("Budget cache has invalid HTTP-attempt accounting")
            records[path.stem] = record
        return records

    def call(self, system: str, user: str, kind: str, key: str,
             max_tokens: int = 6000, repeat: int = 0):
        if not all(isinstance(value, str) for value in (system, user, kind, key)):
            raise ValueError("Request text and identity fields must be strings")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 16000 or type(repeat) is not int or repeat < 0:
            raise ValueError("Invalid token budget or repeat")
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        identifier = digest(request)
        with self._mutex:
            request_lock = self._request_locks.setdefault(identifier, threading.Lock())
        with request_lock:
            path = self.root / "calls" / f"{identifier}.json"
            with self._mutex:
                if identifier in self._unresolved and not path.exists():
                    raise RuntimeError("Unresolved logical reservation; preserve run and do not silently retry")
                if identifier not in self._reserved:
                    if len(self._reserved) >= self.max_calls:
                        raise RuntimeError("Frozen logical-request budget exhausted before transport")
                    write_immutable_json(self.root / "budget_reservations" / f"{identifier}.json",
                                         {"request_hash": identifier, "kind": kind})
                    self._reserved.add(identifier)
                if not path.exists():
                    # If transport throws before persisting, later invocations
                    # cannot know whether any wire attempt occurred.
                    self._unresolved.add(identifier)
            result = self.api.call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if result.get("request_hash") != identifier or result.get("request") != request:
                raise ValueError("Wrapped API returned a different logical request")
            if not path.exists():
                raise ValueError("Wrapped API did not persist its immutable result")
            with self._mutex:
                self._unresolved.discard(identifier)
            return result

    def parallel(self, jobs, fn, label):
        # Generic fn may construct its request dynamically; each .call reserves
        # atomically before touching transport, including during fan-out.
        return self.api.parallel(jobs, fn, label)

    def ledger(self):
        with self._mutex:
            records = self._cached_records()
            reserved = self._reserved | records.keys()
            rows = list(records.values())
            usage = {key: sum(row.get("usage", {}).get(key, 0) or 0 for row in rows)
                     for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
            return {"max_logical_calls": self.max_calls, "logical_requests_reserved": len(reserved),
                    "cached_logical_calls": len(rows), "successful_calls": sum(row["ok"] for row in rows),
                    "terminal_errors": sum(not row["ok"] for row in rows),
                    "unresolved_reservations": sorted(reserved - records.keys()),
                    "http_attempts_from_cached_records": sum(row["http_attempt_count"] for row in rows),
                    "max_planned_http_attempts": self.max_calls * 3,
                    "by_kind": dict(sorted(Counter(row["request"]["kind"] for row in rows).items())),
                    **usage, "missing_usage_calls": sum(not row.get("usage") for row in rows),
                    "usage_not_invoice": True, "unreturned_or_interrupted_attempt_usage_unknown": True}

    def close(self):
        self.api.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
