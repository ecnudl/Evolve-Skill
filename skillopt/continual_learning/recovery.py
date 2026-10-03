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
# V5 keeps the v4 delivery rules and fixes blockers observed in the 10/2 D study:
# an HTTP 200 stream that ended before completion is retried within the same
# bound; a failed attempt's unknown usage is reported but only a capped count
# may accumulate; a complete native proposal larger than the frozen Skill
# interface is rejected (parent kept), not left pending. An unknown score is
# never zero: it is excluded from feedback and from the paired selection
# comparison, with frozen coverage and unknown-shift guards. Every update runs
# a fresh train rollout. Ledger and budget stops still leave the stage pending.
DELIVERY_VERSION = "continual-learning-v5"
POLICY_V5 = {
    **POLICY,
    "version": "closed-delivery-recovery-v2",
    "network_retry": "closed_delivery_error_v2",
    "filtered_response": "unknown_no_retry",
    "unknown_score": "paired_known_exclusion_guarded_v1",
    "min_known_fraction": 0.5,
    "unknown_shift_tolerance_min": 2,
    "unknown_shift_tolerance_fraction": 0.05,
    "train_rollout": "fresh_per_update_v1",
    "failed_attempt_usage": "reported_unknown_nonblocking_capped_v1",
    "max_unknown_cost_attempts": 64,
    "over_budget_candidate": "reject_inadmissible_continue_v1",
}
# V6 is opt-in: E's v5 source, policy and receipts remain frozen. These are
# engineering guards, not a change to the paired-known selection criterion.
HARDENED_VERSION = "continual-learning-v6"
POLICY_V6 = {
    **POLICY_V5,
    "version": "closed-delivery-recovery-v3",
    "network_retry": "closed_delivery_error_v3",
    "filtered_response": "unknown_no_retry_complete_filter_health_v1",
    "failed_attempt_usage": "reserved_max_attempts_hard_cap_v1",
    "cleanup_policy": "stop_before_next_task_on_unconfirmed_cleanup_v1",
}
DELIVERY_VERSIONS = (DELIVERY_VERSION, HARDENED_VERSION)
VERSIONS = (VERSION, *DELIVERY_VERSIONS)
POLICIES = {VERSION: POLICY, DELIVERY_VERSION: POLICY_V5, HARDENED_VERSION: POLICY_V6}
RETRY_POLICIES = {VERSION: "closed_network_error_v1", DELIVERY_VERSION: "closed_delivery_error_v2",
                 HARDENED_VERSION: "closed_delivery_error_v3"}


def validate_policy(policy, model, version=VERSION):
    expected = POLICIES.get(version)
    require(expected is not None, "Unsupported recovery protocol version")
    require(type(policy) is dict and policy == expected, "Explicit supported recovery policy required")
    require(all(type(policy[key]) is type(value) for key, value in expected.items()),
            "Recovery policy fields must have exact types")
    require(model.get("provider") in {"fixture", "bigmodel"}, "Recovery provider unsupported")
    require(model.get("provider") == "fixture" or model.get("name") == "glm-5.3", "Recovery model unsupported")
    require(type(model.get("transport", {}).get("stream_wall_seconds")) is int
            and model["transport"]["stream_wall_seconds"] == 3600,
            "V4 length recovery requires stream_wall_seconds=3600")


def client_options(manifest):
    policy = RETRY_POLICIES.get(manifest["version"])
    return {"delivery_retry_policy": policy} if policy else {}


def is_closed_length(receipt):
    return (receipt.get("finish_reason") == "length"
            and receipt.get("error_type") in (None, "truncated_content")
            and receipt.get("stream_complete") is True
            and receipt.get("status") == 200
            and receipt.get("returned_model") == "glm-5.3")


def solver_call(ledger, logical_id, system, user):
    cap = ledger.manifest["budget"]["solver_max_tokens"]
    first = ledger.call("solver", logical_id, system, user, cap)
    if ledger.manifest["version"] not in VERSIONS or not is_closed_length(first):
        return first
    # The request hash resolves to the original durable call intent. Ledger
    # validates it rather than trusting the caller's recovery description.
    from skillopt.validator_pilot.api import digest

    original = digest({"manifest_hash": ledger.manifest["record_hash"], "role": "solver",
                       "logical_id": logical_id, "system": system, "user": user, "max_tokens": cap})
    return ledger.call("solver", logical_id + ":length-recovery:1", system, user,
                       ledger.manifest["recovery_policy"]["length_max_tokens"], recovery_of=original)
