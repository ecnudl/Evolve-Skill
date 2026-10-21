"""coevo5 token accounting (registration §13.2): bounds, reservations and conservative per-attempt settlement."""
import pytest

from skillopt.coevo5.ledger import (
    attempt_bound,
    baseline_worst_case,
    request_bytes,
    reservation,
    settle,
    settle_baseline,
)
from skillopt.coevo5.protocol import BASELINE_LEARNING_CAP

SIZE, MAX = 1000, 4000
BOUND = SIZE + 512 + MAX
USAGE = {"prompt_tokens": 900, "completion_tokens": 300, "total_tokens": 1200}


def _receipt(*attempts, usage=None, **extra):
    return {"attempts": list(attempts), "usage": usage or {}, **extra}


def test_the_reservation_is_four_attempt_bounds():
    assert request_bytes("sys", "ü") == 5
    assert attempt_bound(SIZE, MAX) == BOUND and reservation(SIZE, MAX) == 4 * BOUND


@pytest.mark.parametrize("receipt,charged", [
    (_receipt({"status": 200}, usage=USAGE, ok=True), 1200),  # delivered with usage
    (_receipt({"status": 503}, {"status": 200}, usage=USAGE, ok=True), BOUND + 1200),  # a 5xx may have generated
    (_receipt({"error": "ConnectError"}, {"status": 429}, {"status": 200}, usage=USAGE), 1200),  # refused first
    (_receipt({"error": "ReadTimeout"}, {"error": "RemoteProtocolError"}, {"error": "ProxyError"},
              {"error": "ConnectTimeout"}, error_type="transport"), 3 * BOUND),
    (_receipt({"status": 200}, ok=True), BOUND),  # delivered without usage
    (_receipt({"status": 200}, error_type="model_mismatch", finish_reason="length"), BOUND),  # usage dropped
    (_receipt({"status": 200}, usage={"prompt_tokens": 1, "completion_tokens": 2}), BOUND),  # incomplete usage
    (_receipt({"status": 400}, error_type="http_400"), 0),
    (None, 4 * BOUND)])  # no receipt: the whole reservation
def test_settlement_charges_reported_usage_zero_only_when_refused_and_else_the_bound(receipt, charged):
    assert settle(receipt, SIZE, MAX) == (charged, False)
    assert settle(receipt, SIZE, MAX)[0] <= reservation(SIZE, MAX)


def test_a_reported_usage_beyond_the_bound_breaks_the_assumption():
    assert settle(_receipt({"status": 200}, usage={**USAGE, "prompt_tokens": SIZE + 513}), SIZE, MAX)[1]
    assert settle(_receipt({"status": 200}, usage={**USAGE, "completion_tokens": MAX + 1}), SIZE, MAX)[1]
    assert not settle(_receipt({"status": 200}, usage={**USAGE, "prompt_tokens": SIZE + 512}), SIZE, MAX)[1]


def test_receipts_list_one_to_four_attempts():
    for attempts in ([], [{"status": 200}] * 5):
        with pytest.raises(ValueError):
            settle(_receipt(*attempts), SIZE, MAX)


def test_the_baseline_reservation_covers_the_frozen_learner_s_worst_case():
    assert baseline_worst_case() == 60_000_000 + 88 * (240000 + 512 + 131072) == 92_699_392
    assert BASELINE_LEARNING_CAP >= baseline_worst_case()


def test_baseline_settlement_uses_per_attempt_usage_and_bounds():
    intent = {"system": "s" * 500, "user": "u" * 500, "max_tokens": MAX}
    known = {"prompt_tokens": 900, "completion_tokens": 300}
    calls = [(intent, {"attempts": [{"usage": {}}, {"usage": known}]}),  # a failed attempt without usage, then usage
             (intent, None)]  # an intent without a receipt: every attempt of the baseline client
    assert settle_baseline(calls) == (BOUND + 1200 + 3 * BOUND, False)
    assert settle_baseline([(intent, {"attempts": [{"usage": {**known, "completion_tokens": MAX + 1}}]})])[1]
