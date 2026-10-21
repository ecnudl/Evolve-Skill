"""GLM-5.3 token accounting (registration §13.2): per-attempt bounds, reservations and conservative settlement.

An attempt's bound is its request's UTF-8 bytes + 512 + ``max_tokens`` (one token is at least one byte); a call reserves
four bounds, the frozen solver client's most attempts. After the receipt each attempt is charged its reported usage, 0
when it was refused before generation, else its bound -- so a call's charge never exceeds its reservation.
"""
from __future__ import annotations

from skillopt.continual_eval.core import require

from .protocol import (
    BASELINE_CLIENT_ATTEMPTS,
    BASELINE_INFLIGHT,
    BASELINE_PROMPT_BYTES,
    BASELINE_RECOVERY_TOKENS,
    BASELINE_REPORTED_TOKENS,
    BASELINE_UNKNOWN_COST_ATTEMPTS,
    CLIENT_ATTEMPTS,
    RESERVATION_OVERHEAD,
)

# transport exceptions raised before a request reached the provider (scripts/weak_solver_probe.py records the type)
NOT_CONNECTED = frozenset({"ConnectError", "ConnectTimeout", "PoolTimeout"})


def request_bytes(system, user):
    return len((system + user).encode())


def attempt_bound(size, max_tokens):
    require(type(size) is int and size >= 0 and type(max_tokens) is int and max_tokens > 0, "Invalid request size")
    return size + RESERVATION_OVERHEAD + max_tokens


def reservation(size, max_tokens):
    return CLIENT_ATTEMPTS * attempt_bound(size, max_tokens)


def _usage(value, keys=("prompt_tokens", "completion_tokens", "total_tokens")):
    """(prompt, completion) of a valid reported usage, else None. The frozen learner's ledger requires two keys."""
    if isinstance(value, dict) and all(type(value.get(k)) is int and value[k] >= 0 for k in keys):
        return value["prompt_tokens"], value["completion_tokens"]
    return None


def _refused(attempt):
    status = attempt.get("status")
    return attempt.get("error") in NOT_CONNECTED or (type(status) is int and 400 <= status < 500)


def settle(receipt, size, max_tokens):
    """(tokens charged, assumption broken) for one call of the frozen solver client. Its receipt lists every attempt (a
    status code or an exception type); a reported usage belongs to the last attempt. No receipt (the process ended
    during the call): the whole reservation."""
    bound = attempt_bound(size, max_tokens)
    if receipt is None:
        return CLIENT_ATTEMPTS * bound, False
    attempts = receipt.get("attempts") if isinstance(receipt, dict) else None
    require(isinstance(attempts, list) and 1 <= len(attempts) <= CLIENT_ATTEMPTS
            and all(isinstance(a, dict) for a in attempts), "A receipt lists 1-4 attempts")
    usage = _usage(receipt.get("usage"))
    charged, broken = 0, False
    for index, attempt in enumerate(attempts):
        if index == len(attempts) - 1 and usage is not None:
            prompt, completion = usage
            charged += prompt + completion
            broken = prompt > size + RESERVATION_OVERHEAD or completion > max_tokens
        elif not _refused(attempt):
            charged += bound
    return charged, broken


def baseline_worst_case():
    """The frozen learner's most tokens in one learning stage: the reported-usage stop, plus every attempt of the calls
    open when it is reached and every attempt without usage, each at the largest attempt it admits."""
    bound = BASELINE_PROMPT_BYTES + RESERVATION_OVERHEAD + BASELINE_RECOVERY_TOKENS
    return BASELINE_REPORTED_TOKENS + (BASELINE_INFLIGHT * BASELINE_CLIENT_ATTEMPTS + BASELINE_UNKNOWN_COST_ATTEMPTS) * bound


def settle_baseline(calls):
    """(tokens charged, assumption broken) of a finished baseline learning stage from the frozen ledger's records:
    ``calls`` = [(intent, receipt or None)], an intent with "system", "user", "max_tokens" and a receipt with per-attempt
    "usage" (closed_delivery_error_v3). Reported usage where valid, else each attempt's bound; an intent without a
    receipt, every attempt of its client."""
    charged, broken = 0, False
    for intent, receipt in calls:
        size = request_bytes(intent["system"], intent["user"])
        bound = attempt_bound(size, intent["max_tokens"])
        if receipt is None:
            charged += BASELINE_CLIENT_ATTEMPTS * bound
            continue
        attempts = receipt.get("attempts")
        require(isinstance(attempts, list) and 1 <= len(attempts) <= BASELINE_CLIENT_ATTEMPTS
                and all(isinstance(a, dict) for a in attempts), "A baseline receipt lists 1-3 attempts")
        for attempt in attempts:
            usage = _usage(attempt.get("usage"), ("prompt_tokens", "completion_tokens"))
            if usage is None:
                charged += bound
            else:
                prompt, completion = usage
                charged += prompt + completion
                broken = broken or prompt > size + RESERVATION_OVERHEAD or completion > intent["max_tokens"]
    return charged, broken
