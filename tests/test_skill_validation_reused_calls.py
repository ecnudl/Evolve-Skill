"""Exact solver-only reuse; all API receipts are fabricated and never sent."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.reused_calls import ReusedSolverCalls
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import digest, write_immutable_json


class API:
    model = "fixture-model"
    service = {"fixture": True, "stream": True}

    def __init__(self, root, *, ok=True):
        self.root, self.ok, self.sent = root, ok, 0

    def call(self, system, user, kind, key, max_tokens=2048, repeat=0):
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        identifier = digest(request)
        path = self.root / "calls" / (identifier + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.sent += 1
        record = {"request": request, "request_hash": identifier, "ok": self.ok,
                  "response": "fixture response" if self.ok else "partial failure", "finish_reason": "stop",
                  "stream_complete": True, "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                  "http_attempt_count": 1, "attempts": [{"attempt": 1, "ok": self.ok}]}
        write_immutable_json(path, record)
        return record


def fixture(tmp_path, *, ok=True, limit=5):
    old_root, new_root = tmp_path / "old", tmp_path / "new"
    old_protocol, new_protocol = seal({"version": "old"}), seal({"version": "new"})
    write_immutable_json(old_root / "protocol.json", old_protocol)
    write_immutable_json(new_root / "protocol.json", new_protocol)
    old_api, new_api = API(old_root / "api", ok=ok), API(new_root / "api")
    old = BoundedCalls(old_api, old_root / "model_budget", old_protocol["record_hash"], 10)
    current = BoundedCalls(new_api, new_root / "model_budget", new_protocol["record_hash"], limit)
    return old, current, ReusedSolverCalls(current, old_root), old_root


@pytest.mark.parametrize("ok", [True, False])
def test_exact_terminal_reused_without_new_call_or_rewriting_history(tmp_path, ok):
    old, current, adapter, source = fixture(tmp_path, ok=ok)
    original = old.call("system", "user", "natural-solver", repeat=1, max_tokens=512)
    before = {p: p.read_bytes() for p in source.rglob("*.json")}
    result = adapter.call("system", "user", "natural-solver", repeat=1, max_tokens=512)
    assert result == original and current.api.sent == 0
    assert {p: p.read_bytes() for p in source.rglob("*.json")} == before
    copied = adapter.root / "receipts" / (original["request_hash"] + ".json")
    assert copied.read_bytes() == (old.api.root / "calls" / (original["request_hash"] + ".json")).read_bytes()
    binding = json.loads(next((adapter.root / "bindings").glob("*.json")).read_text())
    assert binding["old_request_hash"] == original["request_hash"] and binding["new_request_hash"] != original["request_hash"]
    assert binding["old_protocol_hash"] != binding["new_protocol_hash"] and not binding["new_api_request_sent"]
    assert not list((current.api.root / "calls").glob("*.json"))
    assert adapter.call("system", "user", "natural-solver", repeat=1, max_tokens=512) == original
    costs = adapter.accounting()
    assert costs["http_attempts"] == costs["new_paid"]["terminal_logical_requests"] == 0
    assert costs["inherited_solver"]["terminal_logical_requests"] == costs["budget_used_logical_requests"] == 1
    assert costs["inherited_solver"]["terminal_failures"] == int(not ok)
    assert costs["cumulative"]["terminal_reported_tokens"] == 10


@pytest.mark.parametrize("change", [{"system": "different"}, {"user": "different"}, {"repeat": 1}, {"max_tokens": 512}])
def test_changed_request_is_a_new_request(tmp_path, change):
    old, current, adapter, _ = fixture(tmp_path)
    original = old.call("system", "user", "natural-solver")
    kwargs = {"system": "system", "user": "user", "kind": "natural-solver", "repeat": 0, "max_tokens": 2048, **change}
    assert adapter.call(**kwargs)["request_hash"] != original["request_hash"]
    assert current.api.sent == 1 and adapter.accounting()["inherited_solver"]["terminal_logical_requests"] == 0


@pytest.mark.parametrize("kind", ["natural-probes-adaptive_research", "natural-skill-update"])
def test_never_reuses_probe_or_updater(tmp_path, kind):
    old, current, adapter, _ = fixture(tmp_path)
    original = old.call("system", "user", kind)
    assert adapter.call("system", "user", kind)["request_hash"] != original["request_hash"]
    assert current.api.sent == 1


@pytest.mark.parametrize("field", ["model", "service"])
def test_changed_model_or_service_cannot_reuse(tmp_path, field):
    old, current, adapter, _ = fixture(tmp_path)
    old.call("system", "user", "natural-solver")
    setattr(current.api, field, "another-model" if field == "model" else {"fixture": True, "stream": False})
    adapter.call("system", "user", "natural-solver")
    assert current.api.sent == 1


@pytest.mark.parametrize("damage", ["missing_intent", "missing_terminal", "wrong_protocol", "incomplete_terminal", "wrong_request"])
def test_incomplete_or_unbound_parent_cannot_be_resampled(tmp_path, damage):
    old, current, adapter, _ = fixture(tmp_path)
    record = old.call("system", "user", "natural-solver")
    terminal = old.api.root / "calls" / (record["request_hash"] + ".json")
    intent = old.root / "intents" / (record["request_hash"] + ".json")
    if damage == "missing_intent":
        intent.unlink()
    elif damage == "missing_terminal":
        terminal.unlink()
    elif damage == "wrong_protocol":
        value = json.loads(intent.read_text())
        value.pop("record_hash")
        value["protocol_hash"] = digest("wrong")
        intent.write_text(json.dumps(seal(value)))
    else:
        if damage == "incomplete_terminal":
            record["stream_complete"] = False
        else:
            record["request"]["user"] = "changed"
        terminal.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        adapter.call("system", "user", "natural-solver")
    assert current.api.sent == 0


def test_combined_budget_and_concurrent_aliases(tmp_path):
    old, current, adapter, _ = fixture(tmp_path, limit=2)
    original = old.call("system", "inherited", "natural-solver")
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda _: adapter.call("system", "inherited", "natural-solver"), range(4)))
    assert records == [original] * 4
    adapter.call("system", "new", "natural-solver")
    with pytest.raises(ValueError, match="Combined inherited/new"):
        adapter.call("system", "another", "natural-solver")
    costs = adapter.accounting()
    assert costs["budget_used_logical_requests"] == 2 and current.api.sent == 1
    assert costs["new_paid"]["terminal_reported_tokens"] == costs["inherited_solver"]["terminal_reported_tokens"] == 10
    assert costs["cumulative"]["terminal_reported_tokens"] == 20
    resumed = ReusedSolverCalls(current, old.root.parent)
    assert resumed.call("system", "inherited", "natural-solver") == original
    assert resumed.accounting() == costs


def test_unknown_inherited_usage_is_not_invented_as_zero(tmp_path):
    old, _, adapter, _ = fixture(tmp_path)
    record = old.call("system", "user", "natural-solver")
    record["usage"] = {}
    (old.api.root / "calls" / (record["request_hash"] + ".json")).write_text(json.dumps(record))
    adapter.call("system", "user", "natural-solver")
    assert adapter.accounting()["inherited_solver"]["terminal_reported_tokens"] is None
    assert adapter.accounting()["cumulative"]["terminal_reported_tokens"] is None
