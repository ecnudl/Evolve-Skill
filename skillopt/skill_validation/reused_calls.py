"""Explicit cross-protocol solver receipt reuse, without resampling outcomes.

The caller must authorize the parent manifest/source/split relationship first.
Original requests are retained verbatim; reuse bindings are separate records.
Probe/updater calls always use the current protocol and its ordinary cache.
"""
from __future__ import annotations

import json
import threading

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from .models import require
from .panel import checked_path
from .single_round import BoundedCalls


def _read(path, *, sealed=False):
    path = checked_path(path)
    require(path.stat().st_size <= 32_000_000, "Oversized inherited receipt")
    value = json.loads(path.read_text(encoding="utf-8"))
    return verify(value) if sealed else value


def _write(path, value):
    write_immutable_json(checked_path(path), value)


class ReusedSolverCalls:
    """Wrap BoundedCalls; every inherited logical request consumes budget once."""

    def __init__(self, current, parent_root):
        require(type(current) is BoundedCalls, "An existing bounded current caller is required")
        self.current, self.api = current, current.api
        self.parent_root = checked_path(parent_root)
        self.old_protocol = _read(self.parent_root / "protocol.json", sealed=True)["record_hash"]
        require(self.old_protocol != current.protocol_hash, "Reuse requires a distinct explicit protocol")
        self.root = checked_path(current.root.parent / "reused_solver_receipts")
        self.lock = threading.Lock()
        _write(self.root / "context.json", seal({"parent_root": str(self.parent_root),
            "old_protocol_hash": self.old_protocol, "new_protocol_hash": current.protocol_hash,
            "allowed_kind": "natural-solver", "original_requests_preserved": True}))

    def _request(self, protocol, system, user, kind, repeat, max_tokens):
        key = digest({"protocol": protocol, "system": system, "user": user,
                      "kind": kind, "repeat": repeat, "max_tokens": max_tokens})
        return {"model": self.api.model, "system": system, "user": user, "kind": kind,
                "key": key, "repeat": repeat, "max_tokens": max_tokens, "service": self.api.service}

    def _reserved(self):
        return ({p.stem for p in (self.current.root / "intents").glob("*.json")}
                | {p.stem for p in (self.root / "reservations").glob("*.json")})

    def call(self, system, user, kind, *, repeat=0, max_tokens=2048):
        require(all(type(v) is str for v in (system, user, kind)), "Text request fields required")
        require(len((system + user).encode()) <= 120000, "Pilot prompt byte budget exceeded")
        require(type(repeat) is int and repeat >= 0 and type(max_tokens) is int and 1 <= max_tokens <= 2048,
                "Invalid repeat or output budget")
        request = self._request(self.current.protocol_hash, system, user, kind, repeat, max_tokens)
        new_hash = digest(request)
        with self.lock:
            used = self._reserved()
            require(new_hash in used or len(used) < self.current.limit, "Combined inherited/new logical request budget exhausted")
            _write(self.root / "reservations" / (new_hash + ".json"), seal({"new_request_hash": new_hash,
                "new_protocol_hash": self.current.protocol_hash, "kind": kind}))
        if kind != "natural-solver":
            return self.current.call(system, user, kind, repeat=repeat, max_tokens=max_tokens)
        old_request = self._request(self.old_protocol, system, user, kind, repeat, max_tokens)
        old_hash = digest(old_request)
        terminal = checked_path(self.parent_root / "api/calls" / (old_hash + ".json"))
        intent = checked_path(self.parent_root / "model_budget/intents" / (old_hash + ".json"))
        if not terminal.exists():
            require(not intent.exists(), "Interrupted parent solver request cannot be resampled")
            return self.current.call(system, user, kind, repeat=repeat, max_tokens=max_tokens)
        require(intent.is_file(), "Inherited solver terminal has no original intent")
        expected_intent = seal({"request_hash": old_hash, "protocol_hash": self.old_protocol,
                                "kind": kind, "repeat": repeat})
        require(_read(intent, sealed=True) == expected_intent, "Inherited intent belongs to another protocol/request")
        record = _read(terminal)
        require(record.get("request_hash") == old_hash and record.get("request") == old_request,
                "Inherited solver request does not exactly match")
        require(type(record.get("ok")) is bool and type(record.get("response")) is str
                and type(record.get("usage")) is dict and type(record.get("http_attempt_count")) is int
                and record["http_attempt_count"] >= 1 and type(record.get("attempts")) is list
                and len(record["attempts"]) == record["http_attempt_count"]
                and record["attempts"][-1].get("ok") is record["ok"], "Incomplete inherited terminal receipt")
        if record["ok"]:
            require(bool(record["response"].strip()), "Empty inherited successful response")
            require(not self.api.service.get("stream") or record.get("stream_complete") is True
                    and record.get("finish_reason") == "stop", "Incomplete inherited successful stream")
        # A failed terminal is intentionally preserved, not retried or repaired.
        _write(self.root / "receipts" / (old_hash + ".json"), record)
        _write(self.root / "bindings" / (new_hash + ".json"), seal({"old_request_hash": old_hash,
            "new_request_hash": new_hash, "old_protocol_hash": self.old_protocol,
            "new_protocol_hash": self.current.protocol_hash, "source_receipt_hash": digest(record),
            "source_receipt": str(terminal), "kind": kind, "new_api_request_sent": False}))
        return record

    def accounting(self):
        new = self.current.accounting()
        inherited = []
        for path in sorted((self.root / "bindings").glob("*.json")):
            binding = _read(path, sealed=True)
            require(binding["new_protocol_hash"] == self.current.protocol_hash
                    and binding["old_protocol_hash"] == self.old_protocol, "Changed reuse accounting protocol")
            record = _read(self.root / "receipts" / (binding["old_request_hash"] + ".json"))
            require(digest(record) == binding["source_receipt_hash"], "Changed inherited accounting receipt")
            inherited.append(record)
        known = all(type(r["usage"].get(k)) is int for r in inherited for k in ("prompt_tokens", "completion_tokens"))
        old = {"terminal_logical_requests": len(inherited),
               "http_attempts": sum(r["http_attempt_count"] for r in inherited),
               "terminal_failures": sum(not r["ok"] for r in inherited),
               "terminal_reported_tokens": sum(r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"]
                                                for r in inherited) if known else None}
        total = {key: new[key] + old[key] if new[key] is not None and old[key] is not None else None for key in old}
        return {**new, "new_paid": new, "inherited_solver": old, "cumulative": total,
                "budget_used_logical_requests": len(self._reserved()),
                "cost_scope": "Top-level HTTP/tokens are new calls; cumulative includes inherited original costs."}
