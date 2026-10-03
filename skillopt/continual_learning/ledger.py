"""Durable pre-call intents and honest costs for the single-writer learner."""
from __future__ import annotations

import hashlib
from copy import deepcopy

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

PER_ATTEMPT_POLICIES = {"closed_network_error_v1", "closed_delivery_error_v2", "closed_delivery_error_v3"}
RECOVERY_VERSIONS = {"continual-learning-v4", "continual-learning-v5", "continual-learning-v6"}
DELIVERY_VERSION = "continual-learning-v5"
HARDENED_VERSION = "continual-learning-v6"
DELIVERY_VERSIONS = {DELIVERY_VERSION, HARDENED_VERSION}


def _known_usage(usage):
    return (type(usage) is dict and all(type(usage.get(k)) is int and usage[k] >= 0
                                        for k in ("prompt_tokens", "completion_tokens")))


class LearningPending(RuntimeError):
    """A completed numeric comparison cannot be justified; do not resample."""


class BudgetExhausted(LearningPending):
    pass


class Ledger:
    def __init__(self, root, manifest, api):
        self.root, self.manifest, self.api = safe_path(root), manifest, api
        self.budget = manifest["budget"]
        if manifest.get("version") == HARDENED_VERSION:
            service_path = self.root / "model_service.json"
            if api is not None:
                service = deepcopy(api.service)
            elif service_path.exists():
                frozen = read_json(service_path, sealed=True)
                service = {k: v for k, v in frozen.items() if k != "record_hash"}
            else:
                # API construction can fail before it has a service or submits
                # anything. Such a zero-call Pending result can be inspected
                # without inventing a retry limit or writing during replay.
                require(not any(p for folder in ("calls", "call_intents")
                                for p in (self.root / folder).glob("*.json")),
                        "Learning v6 call records require the frozen service")
                self._service, self._max_http_attempts = None, None
                return
            require(type(service) is dict
                    and service.get("delivery_retry_policy") == "closed_delivery_error_v3"
                    and type(service.get("max_retries")) is int
                    and service["max_retries"] >= 0,
                    "Learning v6 requires a frozen service with an explicit nonnegative max_retries")
            if api is not None:
                # run_stage already writes this file; direct ledger users use
                # the same immutable format. V6 includes it in result artifacts.
                write_json(service_path, seal(service))
            self._service = service
            self._max_http_attempts = self._service["max_retries"] + 1

    def snapshot(self):
        records = []
        intents = list((self.root / "call_intents").glob("*.json"))
        for path in sorted((self.root / "calls").glob("*.json")):
            row = read_json(path, sealed=True)
            intent = read_json(self.root / "call_intents" / path.name, sealed=True)
            require(row["intent_hash"] == intent["record_hash"], "Call/intent binding differs")
            require(intent["manifest_hash"] == self.manifest["record_hash"] and path.stem == intent["record_hash"],
                    "Call intent belongs to another manifest")
            require(type(row["receipt"].get("ok")) is bool
                    and type(row["receipt"].get("usage", {})) is dict
                    and type(row["receipt"].get("http_attempt_count")) is int
                    and row["receipt"]["http_attempt_count"] >= 1,
                    "Receipt lacks typed outcome, usage or HTTP attempt count")
            inner = row["receipt"].get("request", {})
            require(row["receipt"].get("request_hash") == digest(inner)
                    and all(inner.get(k) == intent[k] for k in ("system", "user", "max_tokens"))
                    and inner.get("key") == path.stem and inner.get("repeat") == 0
                    and inner.get("kind") == "continual-learning-" + row["role"]
                    and row["role"] == intent["role"], "Nested call receipt does not bind to intent")
            if self.manifest.get("version") == HARDENED_VERSION:
                require(self._service is not None and inner.get("service") == self._service,
                        "Call receipt service differs from frozen learning service")
            records.append(row)
        known_tokens = 0
        missing_usage = 0
        missing_attempt_usage = 0
        delivered_without_usage = 0
        for row in records:
            receipt = row["receipt"]
            per_attempt = receipt.get("request", {}).get("service", {}).get("delivery_retry_policy")
            usages = [receipt.get("usage", {})]
            if receipt.get("ok") is True and not _known_usage(receipt.get("usage", {})):
                delivered_without_usage += 1
            if per_attempt in PER_ATTEMPT_POLICIES:
                attempts = receipt.get("attempts", [])
                require(type(attempts) is list and len(attempts) == receipt["http_attempt_count"],
                        "Per-attempt cost receipts incomplete")
                usages = [attempt.get("usage", {}) for attempt in attempts]
            gap = False
            for usage in usages:
                if _known_usage(usage):
                    known_tokens += usage["prompt_tokens"] + usage["completion_tokens"]
                else:
                    gap = True
                    missing_attempt_usage += 1
            if gap:
                missing_usage += 1
        unclosed = len(intents) - len(records)
        require(unclosed >= 0, "Receipt without intent")
        http_known = sum(r["receipt"].get("http_attempt_count", 0) for r in records)
        result = {"logical_calls": len(intents), "terminal_calls": len(records), "unclosed_calls": unclosed,
                "http_attempts": http_known, "http_attempts_known_subtotal": http_known,
                "http_attempts_total": None if unclosed else http_known,
                "http_attempts_semantics": "known_subtotal_total_unknown_if_unclosed",
                "reported_tokens_known_subtotal": known_tokens, "missing_usage_calls": missing_usage,
                "usage_complete": not (missing_usage or unclosed),
                "retry_inclusive_usage_known": not (missing_usage or unclosed) and
                    all(r["receipt"].get("http_attempt_count") == 1 or
                        r["receipt"].get("request", {}).get("service", {}).get("delivery_retry_policy")
                        in PER_ATTEMPT_POLICIES for r in records),
                "reflection_calls": sum(r["role"] == "reflection" for r in records),
                "solver_calls": sum(r["role"] == "solver" for r in records)}
        if self.manifest.get("version") in RECOVERY_VERSIONS:
            result["missing_attempt_usage"] = missing_attempt_usage
        if self.manifest.get("version") in DELIVERY_VERSIONS:
            # Failed attempts can end before the provider reports usage; their
            # cost stays unknown (never zero) and only a frozen count may build up.
            # A delivered answer without usage, or an open call, still blocks.
            result.update(unknown_cost_attempts=missing_attempt_usage,
                          delivered_without_usage=delivered_without_usage,
                          blocking_usage_gap=bool(unclosed or delivered_without_usage))
        if self.manifest.get("version") == HARDENED_VERSION:
            # Retain even a client protocol violation as a terminal receipt.
            # This must remain readable so the learner can persist Pending,
            # rather than losing the result when it snapshots its final costs.
            over_attempt_limit = sum(row["receipt"]["http_attempt_count"] > self._max_http_attempts
                                     for row in records)
            over_unknown_cap = missing_attempt_usage > self.manifest["recovery_policy"]["max_unknown_cost_attempts"]
            result.update(receipt_attempt_limit_exceeded=over_attempt_limit,
                          unknown_cost_attempt_cap_exceeded=over_unknown_cap,
                          blocking_usage_gap=bool(result["blocking_usage_gap"]
                                                  or over_attempt_limit or over_unknown_cap))
        return result

    def usage_blocks_completion(self, costs):
        if self.manifest.get("version") == HARDENED_VERSION:
            return bool(costs["blocking_usage_gap"] or costs["receipt_attempt_limit_exceeded"]
                        or costs["unknown_cost_attempts"]
                        > self.manifest["recovery_policy"]["max_unknown_cost_attempts"])
        if self.manifest.get("version") in DELIVERY_VERSIONS:
            return costs["blocking_usage_gap"]
        return not costs["usage_complete"]

    def _hardened_budget_check(self, costs):
        if self.manifest.get("version") != HARDENED_VERSION:
            return
        if costs["unknown_cost_attempt_cap_exceeded"]:
            raise BudgetExhausted("unknown_cost_attempt_cap")
        if costs["receipt_attempt_limit_exceeded"]:
            raise LearningPending("provider_http_attempt_limit_exceeded")

    def call(self, role, logical_id, system, user, max_tokens, *, recovery_of=None):
        require(role in {"solver", "reflection"}, "Unsupported learning call role")
        if self.manifest.get("version") == HARDENED_VERSION:
            require(self.api is not None, "Read-only learning ledger cannot submit calls")
            require(self.api.service == self._service, "Learning service changed after ledger initialization")
        cap = self.budget[role + "_max_tokens"]
        if recovery_of is not None:
            from .recovery import VERSIONS, is_closed_length

            require(self.manifest["version"] in VERSIONS and role == "solver",
                    "Recovery requires v4/v5/v6 solver authorization")
            require(type(recovery_of) is str and len(recovery_of) == 64
                    and all(c in "0123456789abcdef" for c in recovery_of), "Invalid recovery parent")
            parent = read_json(self.root / "call_intents" / (recovery_of + ".json"), sealed=True)
            receipt = read_json(self.root / "calls" / (recovery_of + ".json"), sealed=True)
            require(receipt["intent_hash"] == recovery_of and parent["record_hash"] == recovery_of
                    and "recovery_of" not in parent and parent["manifest_hash"] == self.manifest["record_hash"]
                    and parent["role"] == role and parent["system"] == system and parent["user"] == user
                    and parent["max_tokens"] == cap
                    and logical_id == parent["logical_id"] + ":length-recovery:1"
                    and is_closed_length(receipt["receipt"]), "Invalid or repeated length recovery")
            cap = self.manifest["recovery_policy"]["length_max_tokens"]
            require(max_tokens == cap, "Length recovery must use the frozen cap")
        require(type(max_tokens) is int and 1 <= max_tokens <= cap,
                "Call exceeds frozen output cap")
        require(type(system) is str and type(user) is str and len((system + user).encode()) <= 240000,
                "Invalid or oversized prompt")
        request = {"manifest_hash": self.manifest["record_hash"], "role": role, "logical_id": logical_id,
                   "system": system, "user": user, "max_tokens": max_tokens}
        if recovery_of is not None:
            request["recovery_of"] = recovery_of
        key = digest(request)
        target = self.root / "calls" / (key + ".json")
        intent_path = self.root / "call_intents" / (key + ".json")
        if target.exists():
            costs = self.snapshot()
            self._hardened_budget_check(costs)
            row = read_json(target, sealed=True)
            require(read_json(intent_path, sealed=True) == seal(request), "Call cache identity differs")
            return row["receipt"]
        if intent_path.exists():
            raise LearningPending("interrupted_model_call")
        costs = self.snapshot()
        self._hardened_budget_check(costs)
        if self.usage_blocks_completion(costs):
            raise LearningPending("previous_call_usage_or_receipt_unknown")
        if (self.manifest.get("version") == DELIVERY_VERSION and costs["unknown_cost_attempts"]
                >= self.manifest["recovery_policy"]["max_unknown_cost_attempts"]):
            raise BudgetExhausted("unknown_cost_attempt_cap")
        if (self.manifest.get("version") == HARDENED_VERSION
                and costs["unknown_cost_attempts"] + self._max_http_attempts
                > self.manifest["recovery_policy"]["max_unknown_cost_attempts"]):
            # A logical call may retry internally, and even its last attempt can
            # fail without usage. Reserve the frozen worst case before writing
            # an intent; unknown token usage is never assumed to be zero.
            raise BudgetExhausted("unknown_cost_attempt_cap")
        if costs["logical_calls"] >= self.budget["max_api_calls"]:
            raise BudgetExhausted("max_api_calls")
        if role == "reflection" and costs["reflection_calls"] >= self.budget["max_reflection_calls"]:
            raise BudgetExhausted("max_reflection_calls")
        if costs["reported_tokens_known_subtotal"] >= self.budget["max_reported_tokens"]:
            raise BudgetExhausted("reported_token_stop_threshold")
        write_json(intent_path, seal(request))
        receipt = self.api.call(system, user, "continual-learning-" + role, key, max_tokens=max_tokens, repeat=0)
        expected = {"model": self.api.model, "system": system, "user": user,
                    "kind": "continual-learning-" + role, "key": key, "max_tokens": max_tokens,
                    "repeat": 0, "service": self.api.service}
        require(type(receipt) is dict and type(receipt.get("ok")) is bool
                and type(receipt.get("usage", {})) is dict
                and type(receipt.get("http_attempt_count")) is int and receipt["http_attempt_count"] >= 1
                and receipt.get("request") == expected
                and receipt.get("request_hash") == digest(expected), "Provider receipt does not bind to request")
        write_json(target, seal({"role": role, "intent_hash": seal(request)["record_hash"], "receipt": receipt}))
        if self.manifest.get("version") == HARDENED_VERSION:
            self._hardened_budget_check(self.snapshot())
        return receipt

    def artifacts(self):
        """Bind completed replay to every immutable receipt and operation record."""
        result = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for folder in ("calls", "call_intents", "evaluations", "evaluation_intents")
                  for p in sorted((self.root / folder).glob("*.json"))}
        service_path = self.root / "model_service.json"
        if self.manifest.get("version") == HARDENED_VERSION and service_path.exists():
            result["model_service.json"] = hashlib.sha256(service_path.read_bytes()).hexdigest()
        return result
