"""Offline boundary controls for v6; these are not method-effect evidence."""
from copy import deepcopy

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.continual_learning.contracts import manifest
from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending, Ledger
from skillopt.continual_learning.recovery import DELIVERY_VERSION, HARDENED_VERSION, POLICY_V5, POLICY_V6
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import setup


def authorization(version=HARDENED_VERSION):
    _, panel, args = setup()
    args.update(version=version, recovery_policy=deepcopy(
        POLICY_V6 if version == HARDENED_VERSION else POLICY_V5))
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"].update(max_api_calls=200, max_reported_tokens=1000000)
    return manifest(panel, **args)


class API:
    model = "fixture"

    def __init__(self, *, hardened=True):
        self.service = {"delivery_retry_policy": "closed_delivery_error_v3" if hardened
                        else "closed_delivery_error_v2", "max_retries": 2}
        self.calls = []
        self.usages = [{}, {"prompt_tokens": 20, "completion_tokens": 30}]
        self.ok = True

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        request = dict(model=self.model, system=system, user=user, kind=kind, key=key,
                       max_tokens=max_tokens, repeat=repeat, service=deepcopy(self.service))
        self.calls.append(request)
        return dict(request=request, request_hash=digest(request), ok=self.ok,
                    response="fixture" if self.ok else "", finish_reason="stop" if self.ok else "sensitive",
                    usage=deepcopy(self.usages[-1]), attempts=[{"usage": deepcopy(u)} for u in self.usages],
                    http_attempt_count=len(self.usages))


def call(ledger, key):
    return ledger.call("solver", key, "system", "user", 100)


def seed_unknown(ledger, api, count):
    # All seeded receipts respect the production three-attempt service bound.
    # The final failed response may also have unknown usage; it is not zero.
    for index in range(min(count, 61)):
        call(ledger, f"seed-{index}")
    if count > 61:
        api.usages, api.ok = [{} for _ in range(count - 61)], False
        call(ledger, "seed-tail")
    assert ledger.snapshot()["unknown_cost_attempts"] == count


def test_v5_reproduces_unknown_cost_overrun_without_rewriting_history(tmp_path):
    api = API(hardened=False)
    ledger = Ledger(tmp_path, authorization(DELIVERY_VERSION), api)
    seed_unknown(ledger, api, 63)
    api.usages = [{}, {}, {"prompt_tokens": 20, "completion_tokens": 30}]
    api.ok = True
    call(ledger, "overrun")
    costs = ledger.snapshot()
    assert costs["unknown_cost_attempts"] == 65
    assert not ledger.usage_blocks_completion(costs)
    assert "unknown_cost_attempt_cap_exceeded" not in costs
    with pytest.raises(BudgetExhausted, match="unknown_cost_attempt_cap"):
        call(ledger, "next")


@pytest.mark.parametrize("unknown_before,allowed", [(60, True), (61, True), (62, False),
                                                   (63, False), (64, False)])
def test_v6_reserves_all_possible_attempts_before_intent(tmp_path, unknown_before, allowed):
    api = API()
    ledger = Ledger(tmp_path, authorization(), api)
    seed_unknown(ledger, api, unknown_before)
    existing_intents = set((tmp_path / "call_intents").glob("*.json"))
    previous_calls = len(api.calls)
    api.usages, api.ok = [{}, {}, {}], False
    if allowed:
        call(ledger, "boundary")
        assert ledger.snapshot()["unknown_cost_attempts"] == unknown_before + 3 <= 64
        assert len(api.calls) == previous_calls + 1
    else:
        with pytest.raises(BudgetExhausted, match="unknown_cost_attempt_cap"):
            call(ledger, "boundary")
        assert set((tmp_path / "call_intents").glob("*.json")) == existing_intents
        assert len(api.calls) == previous_calls
        assert ledger.snapshot()["unknown_cost_attempts"] == unknown_before
    costs = ledger.snapshot()
    assert not costs["usage_complete"]
    assert not costs["unknown_cost_attempt_cap_exceeded"]
    assert not ledger.usage_blocks_completion(costs)


def test_v6_completed_cache_replays_without_new_budget_reservation(tmp_path):
    api = API()
    value = authorization()
    ledger = Ledger(tmp_path, value, api)
    seed_unknown(ledger, api, 64)
    expected = call(ledger, "seed-0")
    count = len(api.calls)
    reopened = Ledger(tmp_path, value, api)
    assert call(reopened, "seed-0") == expected
    assert len(api.calls) == count
    assert reopened.snapshot() == ledger.snapshot()


@pytest.mark.parametrize("submit", [False, True])
def test_v6_read_only_replay_uses_persisted_service_without_writes(tmp_path, submit):
    api = API()
    value = authorization()
    ledger = Ledger(tmp_path, value, api)
    if submit:
        call(ledger, "one")
    files_before = {str(p.relative_to(tmp_path)): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in tmp_path.rglob("*") if p.is_file()}
    replay = Ledger(tmp_path, value, None)
    assert replay.snapshot() == ledger.snapshot()
    assert replay.artifacts() == ledger.artifacts()
    assert "model_service.json" in replay.artifacts()
    assert read_json(tmp_path / "model_service.json", sealed=True)["max_retries"] == 2
    assert files_before == {str(p.relative_to(tmp_path)): (p.read_bytes(), p.stat().st_mtime_ns)
                            for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="Read-only"):
        call(replay, "new")


def test_v6_empty_failed_initialization_can_be_replayed_without_invented_service(tmp_path):
    replay = Ledger(tmp_path, authorization(), None)
    costs = replay.snapshot()
    assert costs["logical_calls"] == costs["terminal_calls"] == 0
    assert not replay.usage_blocks_completion(costs)
    assert replay.artifacts() == {}
    assert not list(tmp_path.iterdir())


def test_v6_read_only_replay_rejects_records_without_frozen_service(tmp_path):
    api = API()
    value = authorization()
    ledger = Ledger(tmp_path, value, api)
    call(ledger, "one")
    # Test-fixture corruption: do not infer a supposedly frozen budget from
    # whichever API happens to be supplied during a later replay.
    (tmp_path / "model_service.json").unlink()
    with pytest.raises(ValueError, match="records require the frozen service"):
        Ledger(tmp_path, value, None)


def test_v6_counts_complete_usage_for_all_attempts(tmp_path):
    api = API()
    api.usages = [{"prompt_tokens": 1, "completion_tokens": 2},
                  {"prompt_tokens": 20, "completion_tokens": 30}]
    ledger = Ledger(tmp_path, authorization(), api)
    call(ledger, "known")
    costs = ledger.snapshot()
    assert costs["reported_tokens_known_subtotal"] == 53
    assert costs["unknown_cost_attempts"] == 0
    assert costs["usage_complete"] and costs["retry_inclusive_usage_known"]
    assert not ledger.usage_blocks_completion(costs)


@pytest.mark.parametrize("max_retries", [None, True, -1, 2.0, "2"])
def test_v6_rejects_missing_or_untyped_retry_bound(tmp_path, max_retries):
    api = API()
    if max_retries is None:
        del api.service["max_retries"]
    else:
        api.service["max_retries"] = max_retries
    with pytest.raises(ValueError, match="max_retries"):
        Ledger(tmp_path, authorization(), api)
    assert api.calls == []


def test_v6_retry_budget_is_derived_from_service_not_hardcoded(tmp_path):
    # A one-attempt client can use its full cap without a three-slot reserve.
    single = API()
    single.service["max_retries"] = 0
    single.usages, single.ok = [{}], False
    single_ledger = Ledger(tmp_path / "single-attempt", authorization(), single)
    for index in range(64):
        call(single_ledger, str(index))
    assert single_ledger.snapshot()["unknown_cost_attempts"] == 64
    with pytest.raises(BudgetExhausted, match="unknown_cost_attempt_cap"):
        call(single_ledger, "overrun")


def test_v6_delivered_answer_without_usage_still_blocks_completion(tmp_path):
    api = API()
    api.usages = [{}]
    ledger = Ledger(tmp_path, authorization(), api)
    call(ledger, "delivered-without-usage")
    costs = ledger.snapshot()
    assert costs["unknown_cost_attempts"] == 1
    assert costs["delivered_without_usage"] == 1
    assert ledger.usage_blocks_completion(costs)
    with pytest.raises(LearningPending, match="previous_call_usage_or_receipt_unknown"):
        call(ledger, "next")
    assert len(api.calls) == 1


def test_v6_oversized_receipt_is_retained_and_blocks_completion_and_replay(tmp_path):
    api = API()
    api.usages = [{"prompt_tokens": 1, "completion_tokens": 1}] * 4
    ledger = Ledger(tmp_path, authorization(), api)
    with pytest.raises(LearningPending, match="provider_http_attempt_limit_exceeded"):
        call(ledger, "oversized")
    costs = ledger.snapshot()
    assert costs["terminal_calls"] == costs["logical_calls"] == 1
    assert costs["unclosed_calls"] == 0 and costs["reported_tokens_known_subtotal"] == 8
    assert costs["receipt_attempt_limit_exceeded"] == 1
    assert ledger.usage_blocks_completion(costs)
    for key in ("oversized", "next"):
        with pytest.raises(LearningPending, match="provider_http_attempt_limit_exceeded"):
            call(ledger, key)
    assert len(api.calls) == 1


def test_v6_unknown_over_cap_receipt_remains_auditable_and_blocks_completion(tmp_path):
    api = API()
    api.usages, api.ok = [{}] * 65, False
    ledger = Ledger(tmp_path, authorization(), api)
    with pytest.raises(BudgetExhausted, match="unknown_cost_attempt_cap"):
        call(ledger, "malformed-client")
    costs = ledger.snapshot()
    assert costs["terminal_calls"] == 1 and costs["unclosed_calls"] == 0
    assert costs["unknown_cost_attempts"] == 65
    assert costs["unknown_cost_attempt_cap_exceeded"]
    assert ledger.usage_blocks_completion(costs)
    with pytest.raises(BudgetExhausted, match="unknown_cost_attempt_cap"):
        call(ledger, "malformed-client")
    assert len(api.calls) == 1


def test_v6_service_cannot_change_after_budget_is_bound(tmp_path):
    api = API()
    ledger = Ledger(tmp_path, authorization(), api)
    api.service["max_retries"] = 10
    with pytest.raises(ValueError, match="service changed"):
        call(ledger, "mutated")
    assert api.calls == []


def test_v6_large_retry_bound_fails_without_intent_or_api_call(tmp_path):
    api = API()
    api.service["max_retries"] = 64
    ledger = Ledger(tmp_path, authorization(), api)
    with pytest.raises(BudgetExhausted, match="unknown_cost_attempt_cap"):
        call(ledger, "unreservable")
    assert ledger.snapshot()["logical_calls"] == 0
    assert api.calls == []
