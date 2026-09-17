"""V7 per-HTTP-attempt admission pacing around the unchanged PJLAB client.

Only this instance's public httpx hooks are installed. The original cache,
bounded HTTP retry predicate, SSE parser and BudgetedAPI remain unchanged.
Admission timestamps describe local client attempts, not provider arrival or
proof that a timed-out request reached the server. One process owns a run.
"""

from __future__ import annotations

import json
import math
import threading
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.validator_pilot.api import CachedAPI, digest, write_immutable_json

VERSION = "v7-global-attempt-pacing-v1"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _seal(value):
    return {**value, "record_hash": digest(value)}


def _read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    _require(value.get("record_hash") == digest({k: v for k, v in value.items() if k != "record_hash"}),
             "Pacing record integrity mismatch")
    return value


@dataclass(frozen=True)
class PacingPolicy:
    min_interval_seconds: float = 3.0
    cooldown_seconds: float = 20.0
    max_retry_after_seconds: float = 60.0

    def __post_init__(self):
        for value in asdict(self).values():
            _require(type(value) in {int, float} and math.isfinite(value) and 0 < value <= 60,
                     "Pacing policy requires finite positive durations at most 60 seconds")
        _require(self.cooldown_seconds <= self.max_retry_after_seconds, "Cooldown exceeds frozen maximum")


class _Clock:
    @staticmethod
    def monotonic():
        return time.monotonic()

    @staticmethod
    def wall():
        return time.time()

    @staticmethod
    def sleep(seconds):
        time.sleep(seconds)


def returned_model_label(record):
    """Missing and explicit null mean unreported, never inferred from request."""
    value = record.get("returned_model")
    _require(value is None or isinstance(value, str), "Returned model must be text or unreported")
    return value or "unreported"


def classify_failure(record, *, delivery_valid=None, native_status=None):
    """Pure diagnostic; never used to trigger a new model attempt.

    Native ``fail`` is a measured wrong answer, while ``unknown`` is unavailable
    execution/oracle evidence. Missing stages are not silently called failures.
    """
    _require(isinstance(record, dict) and type(record.get("ok")) is bool, "Explicit API outcome required")
    _require(delivery_valid is None or type(delivery_valid) is bool, "Delivery must be explicit boolean or unavailable")
    _require(native_status in {None, "pass", "fail", "unknown", "not_applicable"}, "Unknown native status")
    transport = not record["ok"] and record.get("error_type") in {"http_status", "timeout", "transport_error"}
    client = not record["ok"] and record.get("error_type") == "unexpected_client_error"
    response = not record["ok"] and not transport and not client
    delivery = record["ok"] and delivery_valid is False
    native_unknown = record["ok"] and delivery_valid is True and native_status == "unknown"
    semantic = record["ok"] and delivery_valid is True and native_status == "fail"
    classification = ("transport_failure" if transport else "client_error" if client else "response_failure" if response else
                      "delivery_error" if delivery else "native_unavailable" if native_unknown else
                      "semantic_failure" if semantic else "success" if delivery_valid is True and native_status == "pass"
                      else "not_evaluated")
    return {"classification": classification, "transport_failure": transport,
            "client_error": client, "response_failure": response, "delivery_error": delivery, "native_unavailable": native_unknown,
            "semantic_failure": semantic, "semantic_retry_authorized": False}


def _retry_after(value, now, maximum):
    if value is None:
        return 0.0
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = parsedate_to_datetime(str(value)).timestamp() - now
        except (ValueError, TypeError, OverflowError, AttributeError):
            return 0.0
    return max(0.0, min(maximum, seconds)) if math.isfinite(seconds) else 0.0


class _Pacer:
    def __init__(self, root, policy, service, clock):
        self.root, self.policy, self.clock = Path(root) / "pacing", policy, clock
        self.lock = threading.Lock()
        self.epoch = uuid.uuid4().hex
        protocol = _seal({"version": VERSION, "policy": asdict(policy), "service_hash": digest(service),
                          "workers": 4, "unit": "http_client_attempt_admission_not_logical_call",
                          "cooldown_statuses": [429], "retry_policy": "unchanged_cached_api_max_three_transport_attempts",
                          "semantic_resampling": False, "one_process_per_run": True,
                          "resume_clock": "persisted_wall_deadline_converted_to_new_monotonic_deadline",
                          "wall_clock_assumption": "clock_not_moved_forward_across_process_restart",
                          "inflight_attempts_cannot_be_retracted_by_a_later_429": True})
        write_immutable_json(self.root / "protocol.json", protocol)
        self.protocol_hash = protocol["record_hash"]
        admissions, outcomes, cooldowns = self._existing()
        _require(set(admissions) == set(outcomes), "Unresolved HTTP admission; preserve run without silent retry")
        self.sequence = len(admissions)
        now, wall = self.clock.monotonic(), self.clock.wall()
        last_wall = max((r["admitted_wall"] + policy.min_interval_seconds for r in admissions.values()), default=wall)
        cooldown_wall = max((r["cooldown_until_wall"] for r in cooldowns.values()), default=wall)
        remaining = max(last_wall, cooldown_wall) - wall
        _require(remaining <= max(policy.min_interval_seconds, policy.max_retry_after_seconds) + 5,
                 "Persisted pacing deadline indicates backward wall-clock drift")
        self.next_allowed = now + max(0.0, last_wall - wall)
        self.cooldown_until = now + max(0.0, cooldown_wall - wall)

    def _existing(self):
        values = {}
        for kind in ("admissions", "attempts", "cooldowns"):
            records = {}
            for path in sorted((self.root / kind).glob("*.json")):
                row = _read(path)
                sequence = row.get("sequence")
                _require(type(sequence) is int and sequence > 0 and path.stem == f"{sequence:08d}",
                         "Pacing sequence identity mismatch")
                _require(row.get("protocol_hash") == self.protocol_hash, "Pacing policy provenance mismatch")
                records[sequence] = row
            values[kind] = records
        admissions, outcomes, cooldowns = (values[k] for k in ("admissions", "attempts", "cooldowns"))
        _require(set(admissions) == set(range(1, len(admissions) + 1)), "Pacing admission sequence has a gap")
        _require(set(outcomes) <= set(admissions) and set(cooldowns) <= set(admissions), "Orphan pacing receipt")
        for kind in (outcomes, cooldowns):
            for sequence, row in kind.items():
                admission = admissions[sequence]
                _require(row["admission_hash"] == admission["record_hash"]
                         and row["request_hash"] == admission["request_hash"], "Attempt receipt admission binding mismatch")
        positions = set()
        for sequence, admission in admissions.items():
            position = admission["request_hash"], admission["attempt"]
            _require(position not in positions and type(admission["attempt"]) is int and 1 <= admission["attempt"] <= 3,
                     "Duplicate or invalid logical HTTP attempt")
            positions.add(position)
            for key in ("admitted_monotonic", "admitted_wall", "waited_seconds"):
                _require(type(admission.get(key)) in {int, float} and math.isfinite(admission[key])
                         and admission[key] >= 0, "Invalid attempt admission clock")
            cooldown, outcome = cooldowns.get(sequence), outcomes.get(sequence)
            if cooldown:
                _require(cooldown["status"] == 429 and 0 <= cooldown["retry_after_seconds"] <= self.policy.max_retry_after_seconds
                         and cooldown["cooldown_seconds"] == max(self.policy.cooldown_seconds, cooldown["retry_after_seconds"])
                         and cooldown["cooldown_until_wall"] >= cooldown["observed_wall"] + cooldown["cooldown_seconds"] - 1e-6,
                         "Persisted cooldown violates the frozen policy")
            if outcome:
                attempt = outcome["api_attempt"]
                _require(attempt["attempt"] == admission["attempt"] and type(attempt.get("ok")) is bool
                         and outcome["cooldown_hash"] == (cooldown["record_hash"] if cooldown else None)
                         and (attempt.get("status") != 429 or cooldown is not None)
                         and (cooldown is None or attempt.get("status") in {None, 429}),
                         "Completed attempt/cooldown receipt mismatch")
        return admissions, outcomes, cooldowns

    def admit(self, request_hash, kind, attempt, http_request_hash):
        waited = 0.0
        while True:
            with self.lock:
                now = self.clock.monotonic()
                wait = max(self.next_allowed, self.cooldown_until) - now
                if wait <= 0:
                    self.sequence += 1
                    row = _seal({"version": VERSION, "protocol_hash": self.protocol_hash,
                        "sequence": self.sequence, "request_hash": request_hash, "kind": kind,
                        "attempt": attempt, "http_request_hash": http_request_hash,
                        "process_epoch": self.epoch, "admitted_monotonic": now,
                        "admitted_wall": self.clock.wall(), "waited_seconds": waited,
                        "wire_delivery_confirmed": False})
                    write_immutable_json(self.root / "admissions" / f"{self.sequence:08d}.json", row)
                    self.next_allowed = now + self.policy.min_interval_seconds
                    return row
            # Recheck after waking: another worker may have extended cooldown.
            self.clock.sleep(wait)
            waited += wait

    def observe_response(self, admission, status, retry_after):
        if status != 429:
            return None
        with self.lock:
            now, wall = self.clock.monotonic(), self.clock.wall()
            header_delay = _retry_after(retry_after, wall, self.policy.max_retry_after_seconds)
            duration = max(self.policy.cooldown_seconds, header_delay)
            self.cooldown_until = max(self.cooldown_until, now + duration)
            row = _seal({"version": VERSION, "protocol_hash": self.protocol_hash,
                         "sequence": admission["sequence"], "request_hash": admission["request_hash"],
                         "admission_hash": admission["record_hash"], "status": 429,
                         "observed_wall": wall, "retry_after_seconds": header_delay,
                         "cooldown_seconds": duration,
                         "cooldown_until_wall": wall + self.cooldown_until - now})
            write_immutable_json(self.root / "cooldowns" / f"{admission['sequence']:08d}.json", row)
            return row

    def finish(self, admission, outcome, cooldown):
        row = _seal({"version": VERSION, "protocol_hash": self.protocol_hash,
                     "sequence": admission["sequence"], "request_hash": admission["request_hash"],
                     "admission_hash": admission["record_hash"], "api_attempt": outcome,
                     "cooldown_hash": cooldown["record_hash"] if cooldown else None,
                     "finished_wall": self.clock.wall()})
        write_immutable_json(self.root / "attempts" / f"{admission['sequence']:08d}.json", row)
        return row


class PacedCachedAPI(CachedAPI):
    """Backend for BudgetedAPI, with instance-local hooks on every HTTP attempt.

    ``http_client`` and ``clock`` are dependency-injection seams for offline
    tests. Production defaults retain the original direct HTTPS client, source
    credentials, stream parser and fixed retry behavior.
    """

    def __init__(self, repo, root, model="glm-5.3", workers=4, *, policy=None,
                 stream=True, reasoning_effort="low", http_client=None, clock=None):
        _require(type(workers) is int and workers == 4, "V7 requires four shared workers")
        policy = PacingPolicy() if policy is None else policy
        _require(isinstance(policy, PacingPolicy), "Explicit frozen PacingPolicy required")
        super().__init__(repo, root, model=model, workers=workers, stream=stream, reasoning_effort=reasoning_effort)
        try:
            if http_client is not None:
                _require(isinstance(http_client, httpx.Client) and not http_client.trust_env
                         and not http_client.follow_redirects, "Injected client must disable proxies and redirects")
                self._client.close()
                self._client = http_client
            _require(not any(self._client.event_hooks.values()), "Owned HTTP client must not contain unrelated hooks")
            self._pacer = _Pacer(self.root, policy, self.service, clock or _Clock())
            self._context = threading.local()
            self._client.event_hooks = {"request": [self._request_hook], "response": [self._response_hook]}
            for path in (self.root / "calls").glob("*.json"):
                self._verify_cached(json.loads(path.read_text(encoding="utf-8")))
        except BaseException:
            self._client.close()
            raise

    def _request_hook(self, request):
        context = getattr(self._context, "value", None)
        _require(context is not None and request.method == "POST" and str(request.url) == self._endpoint,
                 "Unexpected HTTP request outside the frozen logical call")
        attempt = len(context["admissions"]) + 1
        _require(attempt <= 3, "HTTP attempt count exceeds unchanged retry policy")
        body = json.loads(request.content)
        wire_hash = digest({"method": request.method, "endpoint": self._endpoint, "body": body})
        admission = self._pacer.admit(context["request_hash"], context["kind"], attempt, wire_hash)
        context["admissions"].append(admission)
        context["http_requests"][id(request)] = admission

    def _response_hook(self, response):
        context = getattr(self._context, "value", None)
        _require(context is not None and id(response.request) in context["http_requests"], "Unbound HTTP response")
        admission = context["http_requests"][id(response.request)]
        cooldown = self._pacer.observe_response(admission, response.status_code, response.headers.get("retry-after"))
        if cooldown:
            context["cooldowns"][admission["sequence"]] = cooldown

    def _perform(self, request, identifier):
        reservation = self.root / "budget_reservations" / f"{identifier}.json"
        _require(reservation.exists() and json.loads(reservation.read_text(encoding="utf-8")) == {
            "request_hash": identifier, "kind": request["kind"]}, "Budget reservation must precede every real HTTP attempt")
        _require(getattr(self._context, "value", None) is None, "Nested logical calls cannot share an attempt context")
        context = {"request_hash": identifier, "kind": request["kind"], "admissions": [], "http_requests": {}, "cooldowns": {}}
        self._context.value = context
        try:
            result = super()._perform(request, identifier)
            _require(len(context["admissions"]) == result["http_attempt_count"] == len(result["attempts"]),
                     "HTTP attempts and global admission receipts disagree")
            references = []
            for admission, outcome in zip(context["admissions"], result["attempts"]):
                _require(admission["attempt"] == outcome["attempt"], "Retry attempt identity mismatch")
                receipt = self._pacer.finish(admission, outcome, context["cooldowns"].get(admission["sequence"]))
                references.append({"sequence": admission["sequence"], "admission_hash": admission["record_hash"],
                                   "attempt_receipt_hash": receipt["record_hash"]})
            result["pacing"] = {"protocol_hash": self._pacer.protocol_hash, "attempts": references}
            result["transport_diagnostic"] = classify_failure(result)
            return result
        finally:
            self._context.value = None

    def _verify_cached(self, result):
        identifier = result.get("request_hash")
        _require(isinstance(result.get("request"), dict) and identifier == digest(result["request"]),
                 "Cached pacing request identity mismatch")
        pacing = result.get("pacing", {})
        _require(pacing.get("protocol_hash") == self._pacer.protocol_hash
                 and len(pacing.get("attempts", [])) == result.get("http_attempt_count") == len(result.get("attempts", [])),
                 "Cached result lacks all frozen per-attempt pacing evidence")
        for reference, outcome in zip(pacing["attempts"], result["attempts"]):
            sequence = reference["sequence"]
            admission = _read(self._pacer.root / "admissions" / f"{sequence:08d}.json")
            receipt = _read(self._pacer.root / "attempts" / f"{sequence:08d}.json")
            _require(admission["request_hash"] == identifier and admission["record_hash"] == reference["admission_hash"]
                     and receipt["record_hash"] == reference["attempt_receipt_hash"] and receipt["api_attempt"] == outcome
                     and receipt["admission_hash"] == admission["record_hash"], "Cached result/HTTP receipt binding mismatch")
        _require(result.get("transport_diagnostic") == classify_failure(result), "Cached failure classification changed")
        return result

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        result = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        return self._verify_cached(result)

    def pacing_audit(self):
        """Read-only counts; cached completion never performs a health probe."""
        admissions, receipts, cooldowns = self._pacer._existing()
        return {"protocol_hash": self._pacer.protocol_hash, "http_attempt_admissions": len(admissions),
                "completed_attempt_receipts": len(receipts), "unresolved_attempts": sorted(set(admissions) - set(receipts)),
                "cooldown_events": len(cooldowns),
                "attempt_statuses": dict(Counter(str(r["api_attempt"].get("status")) for r in receipts.values())),
                "server_arrival_or_billing_proven": False}


def make_budgeted_api(repo, root, *, max_calls=700, workers=4, policy=None, **backend_options):
    """Drop-in V7 Study factory, retaining the existing logical budget guard."""
    backend = PacedCachedAPI(repo, root, workers=workers, policy=policy, **backend_options)
    try:
        return BudgetedAPI(repo, root, max_calls=max_calls, workers=workers, api=backend)
    except BaseException:
        backend.close()
        raise
