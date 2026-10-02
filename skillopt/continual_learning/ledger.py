"""Durable pre-call intents and honest costs for the single-writer learner."""
from __future__ import annotations

import hashlib

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest


class LearningPending(RuntimeError):
    """A completed numeric comparison cannot be justified; do not resample."""


class BudgetExhausted(LearningPending):
    pass


class Ledger:
    def __init__(self, root, manifest, api):
        self.root, self.manifest, self.api = safe_path(root), manifest, api
        self.budget = manifest["budget"]

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
            records.append(row)
        known_tokens = 0
        missing_usage = 0
        missing_attempt_usage = 0
        for row in records:
            receipt = row["receipt"]
            per_attempt = receipt.get("request", {}).get("service", {}).get("delivery_retry_policy")
            usages = [receipt.get("usage", {})]
            if per_attempt == "closed_network_error_v1":
                attempts = receipt.get("attempts", [])
                require(type(attempts) is list and len(attempts) == receipt["http_attempt_count"],
                        "Per-attempt cost receipts incomplete")
                usages = [attempt.get("usage", {}) for attempt in attempts]
            gap = False
            for usage in usages:
                if (type(usage) is dict and all(type(usage.get(k)) is int and usage[k] >= 0
                                              for k in ("prompt_tokens", "completion_tokens"))):
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
                        == "closed_network_error_v1" for r in records),
                "reflection_calls": sum(r["role"] == "reflection" for r in records),
                "solver_calls": sum(r["role"] == "solver" for r in records)}
        if self.manifest.get("version") == "continual-learning-v4":
            result["missing_attempt_usage"] = missing_attempt_usage
        return result

    def call(self, role, logical_id, system, user, max_tokens, *, recovery_of=None):
        require(role in {"solver", "reflection"}, "Unsupported learning call role")
        cap = self.budget[role + "_max_tokens"]
        if recovery_of is not None:
            from .recovery import VERSION, is_closed_length

            require(self.manifest["version"] == VERSION and role == "solver",
                    "Recovery requires v4 solver authorization")
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
            self.snapshot()
            row = read_json(target, sealed=True)
            require(read_json(intent_path, sealed=True) == seal(request), "Call cache identity differs")
            return row["receipt"]
        if intent_path.exists():
            raise LearningPending("interrupted_model_call")
        costs = self.snapshot()
        if not costs["usage_complete"]:
            raise LearningPending("previous_call_usage_or_receipt_unknown")
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
        return receipt

    def artifacts(self):
        """Bind completed replay to every immutable receipt and operation record."""
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in ("calls", "call_intents", "evaluations", "evaluation_intents")
                for p in sorted((self.root / folder).glob("*.json"))}
