"""Explicit bounded delivery recovery, not retries after a wrong answer.

The original receipt remains immutable. Only a closed length response can get
one larger-budget request, before scoring. Filters and semantic failures never
trigger retries. Actual usage for every request remains in the learner ledger.
"""
from __future__ import annotations

from skillopt.continual_eval.core import require

VERSION = "continual-learning-v4"
POLICY = {
    "version": "closed-delivery-recovery-v1",
    "reflection_parser": "strict-json-invalid-escape-v1",
    "network_retry": "closed_network_error_v1",
    "length_retries": 1,
    "length_max_tokens": 131072,
    "filtered_response": "pending_no_retry",
    "unknown_score": "pending_never_zero",
}


def validate_policy(policy, model):
    require(type(policy) is dict and policy == POLICY, "Explicit supported recovery policy required")
    require(all(type(policy[key]) is type(value) for key, value in POLICY.items()),
            "Recovery policy fields must have exact types")
    require(model.get("provider") in {"fixture", "bigmodel"}, "Recovery provider unsupported")
    require(model.get("provider") == "fixture" or model.get("name") == "glm-5.3", "Recovery model unsupported")
    require(type(model.get("transport", {}).get("stream_wall_seconds")) is int
            and model["transport"]["stream_wall_seconds"] == 3600,
            "V4 length recovery requires stream_wall_seconds=3600")


def client_options(manifest):
    return ({"delivery_retry_policy": "closed_network_error_v1"}
            if manifest["version"] == VERSION else {})


def is_closed_length(receipt):
    return (receipt.get("finish_reason") == "length"
            and receipt.get("error_type") in (None, "truncated_content")
            and receipt.get("stream_complete") is True
            and receipt.get("status") == 200
            and receipt.get("returned_model") == "glm-5.3")


def solver_call(ledger, logical_id, system, user):
    cap = ledger.manifest["budget"]["solver_max_tokens"]
    first = ledger.call("solver", logical_id, system, user, cap)
    if ledger.manifest["version"] != VERSION or not is_closed_length(first):
        return first
    # The request hash resolves to the original durable call intent. Ledger
    # validates it rather than trusting the caller's recovery description.
    from skillopt.validator_pilot.api import digest

    original = digest({"manifest_hash": ledger.manifest["record_hash"], "role": "solver",
                       "logical_id": logical_id, "system": system, "user": user, "max_tokens": cap})
    return ledger.call("solver", logical_id + ":length-recovery:1", system, user,
                       ledger.manifest["recovery_policy"]["length_max_tokens"], recovery_of=original)
