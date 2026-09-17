"""Offline fake-client checks: no environment configuration or API access."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.validator_pilot.api import digest, write_immutable_json


class FakeAPI:
    def __init__(self, root, *, fail=False, explode=False):
        self.root, self.model = Path(root), "glm-5.3"
        self.service = {"model": self.model, "max_retries": 2}
        self.calls, self.closed, self.fail, self.explode = 0, False, fail, explode

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        identity = digest(request)
        path = self.root / "calls" / (identity + ".json")
        if path.exists():
            import json
            return json.loads(path.read_text())
        self.calls += 1
        if self.explode:
            raise RuntimeError("synthetic interrupted call")
        record = {"request": request, "request_hash": identity, "ok": not self.fail,
                  "response": "ok" if not self.fail else "", "usage": {"total_tokens": 7},
                  "http_attempt_count": 3 if self.fail else 1}
        write_immutable_json(path, record)
        return record

    def parallel(self, jobs, fn, label):
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(fn, jobs))

    def close(self):
        self.closed = True


def make(tmp_path, max_calls=3, **kwargs):
    fake = FakeAPI(tmp_path, **kwargs)
    return BudgetedAPI(tmp_path, tmp_path, max_calls=max_calls, api=fake), fake


def call(api, key="k", **kwargs):
    return api.call("system", "user", "test", key, **kwargs)


def test_fresh_and_cached_identities_count_once(tmp_path):
    api, fake = make(tmp_path, max_calls=1)
    first = call(api)
    assert call(api) == first
    assert fake.calls == 1
    with pytest.raises(RuntimeError, match="budget exhausted"):
        call(api, "new")
    assert fake.calls == 1
    assert api.ledger()["logical_requests_reserved"] == 1


def test_concurrent_unique_requests_never_overshoot(tmp_path):
    api, fake = make(tmp_path, max_calls=3)

    def attempt(index):
        try:
            return call(api, str(index))["ok"]
        except RuntimeError:
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(attempt, range(40)))
    assert sum(outcomes) == 3
    assert fake.calls == 3
    assert api.ledger()["cached_logical_calls"] == 3


def test_concurrent_same_identity_is_one_logical_and_wire_call(tmp_path):
    api, fake = make(tmp_path, max_calls=1)
    with ThreadPoolExecutor(max_workers=12) as pool:
        records = list(pool.map(lambda _: call(api), range(24)))
    assert len({record["request_hash"] for record in records}) == 1
    assert fake.calls == 1


def test_failed_cached_call_not_retried_and_http_attempts_accounted(tmp_path):
    api, fake = make(tmp_path, max_calls=1, fail=True)
    assert not call(api)["ok"]
    assert not call(api)["ok"]
    assert fake.calls == 1
    ledger = api.ledger()
    assert ledger["terminal_errors"] == 1
    assert ledger["http_attempts_from_cached_records"] == 3
    assert ledger["unresolved_reservations"] == []


def test_existing_cache_without_reservation_consumes_budget(tmp_path):
    fake = FakeAPI(tmp_path)
    fake.call("system", "user", "test", "old")
    api = BudgetedAPI(tmp_path, tmp_path, max_calls=1, api=fake)
    assert call(api, "old")["ok"]
    with pytest.raises(RuntimeError, match="budget exhausted"):
        call(api, "new")
    assert fake.calls == 1


def test_interrupted_reservation_cannot_silently_retry_now_or_on_resume(tmp_path):
    api, fake = make(tmp_path, explode=True)
    with pytest.raises(RuntimeError, match="synthetic interrupted"):
        call(api)
    with pytest.raises(RuntimeError, match="Unresolved"):
        call(api)
    assert fake.calls == 1
    assert len(api.ledger()["unresolved_reservations"]) == 1
    resumed, fresh = make(tmp_path)
    with pytest.raises(RuntimeError, match="Unresolved"):
        call(resumed)
    assert fresh.calls == 0


def test_resume_completed_cache_budget_protocol_is_immutable(tmp_path):
    api, _ = make(tmp_path)
    call(api)
    resumed, fake = make(tmp_path)
    call(resumed)
    assert fake.calls == 0
    with pytest.raises(ValueError, match="Immutable"):
        make(tmp_path, max_calls=4)


def test_parallel_and_context_forward_without_new_retry_layer(tmp_path):
    api, fake = make(tmp_path)
    with api:
        rows = api.parallel(["a", "b", "c"], lambda key: call(api, key), "fake")
        assert [row["request"]["key"] for row in rows] == ["a", "b", "c"]
    assert fake.closed


@pytest.mark.parametrize("max_calls", [0, -1, True, 1.5, 1601])
def test_invalid_budget_rejected_without_api_configuration(tmp_path, max_calls):
    with pytest.raises(ValueError):
        BudgetedAPI(tmp_path, tmp_path, max_calls=max_calls)


@pytest.mark.parametrize("repeat", [-1, True, 1.5])
def test_invalid_request_is_not_reserved(tmp_path, repeat):
    api, fake = make(tmp_path)
    with pytest.raises(ValueError):
        call(api, repeat=repeat)
    assert fake.calls == 0
    assert api.ledger()["logical_requests_reserved"] == 0


def test_request_repeat_changes_identity(tmp_path):
    api, _ = make(tmp_path)
    assert call(api, repeat=0)["request_hash"] != call(api, repeat=1)["request_hash"]


def test_explicit_1600_frozen_upper_bound_is_supported(tmp_path):
    api, _ = make(tmp_path, max_calls=1600)
    assert api.ledger()["max_logical_calls"] == 1600
    assert api.ledger()["max_planned_http_attempts"] == 4800
