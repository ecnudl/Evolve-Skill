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
# V7 keeps every v6 guard and raises the frozen Skill interface for both native
# SkillOpt and official GEPA. GEPA gets the same unknown rule in a form its
# official optimizer can consume: positions the parent cannot score are left
# out; a candidate's new unknown is valued at the parent's own known score
# (neither zero nor a gain); the selected candidate is then rechecked on real
# paired scores with the frozen unknown-shift guard.
BUDGET_VERSION = "continual-learning-v7"
POLICY_V7 = {
    **POLICY_V6,
    "version": "closed-delivery-recovery-v4",
    "skill_budget_bytes": 32000,
    "gepa_unknown": "parent_known_mask_neutral_impute_guarded_v1",
}
# V8 keeps every v7 guard and changes what the learner selects on and from:
# the selection role is the canonical val part (partition skill_confirmation),
# an update must win a frozen margin of paired positions (not one position),
# failed train executions carry their expected answer or sanitized execution
# evidence (both methods see the same feedback), a candidate that copies a long
# train label is rejected, the native analysts get a transfer requirement, and
# solver rows run concurrently under one ledger lock. Study F (v7) is untouched.
GENERALIZATION_VERSION = "continual-learning-v8"
POLICY_V8 = {
    **POLICY_V7,
    "version": "generalization-gate-v1",
    "selection_partition": "skill_confirmation",
    "selection_gate": "paired_net_wins_margin_v1",
    "min_net_wins": 3,
    "net_wins_fraction": 0.02,
    "label_leakage": "reject_candidate_containing_long_train_label_v1",
    "label_leakage_min_chars": 12,
    "reflection_preamble": "transfer-requirement-v1",
    "solver_workers": 8,
}
# V9 keeps everything in v8 except the acceptance rule. The 10/6 stage redos measured the noise
# of an identical Skill run twice (6-10% of positions flip) and showed that v8's fixed margin
# (3-5 positions) is about one standard deviation of that noise: two KOR-Bench updates accepted
# on canonical val did not hold on test. V9 therefore (a) screens a candidate with a family-level
# exact one-sided sign test on its first val pass against the parent's rows (one sign per family:
# a KOR-Bench rule, an ALFWorld scenario, a task elsewhere), (b) re-evaluates a screened candidate
# AND its parent on a fresh val pass (the parent's first pass is shared by all candidates of a
# stage, so a low parent draw would otherwise favor every candidate), and (c) accepts only on
# that confirmation pass alone: jointly-known coverage, positive net, and the family-level sign
# test at accept_alpha divided by the number of candidates the stage may try.
CONFIRMATION_VERSION = "continual-learning-v9"
POLICY_V9 = {
    **{k: v for k, v in POLICY_V8.items() if k not in {"min_net_wins", "net_wins_fraction"}},
    "version": "generalization-gate-v2",
    # The analyst's JSON is rejected when it contains a raw newline inside a string (10/7 BCB v9
    # stage); policy v2 of the strict parser escapes such control characters lexically.
    "reflection_parser": "strict-json-invalid-escape-control-v2",
    # A genuinely malformed analyst document (10/7: a missing comma) gets ONE re-issued request with
    # a format reminder; both replies stay in receipts and audits. ~1 in 30 analyst replies is
    # malformed, so a 3-iteration stage would otherwise go pending more often than not.
    "reflection_json_retries": 1,
    "selection_gate": "family_sign_test_screen_then_fresh_confirmation_v1",
    "screen_alpha": 0.10,
    "accept_alpha": 0.05,
    "multiplicity": "bonferroni_over_max_iterations",
}
# V10 is the main method's learning protocol (10/7): the v9 gate, parser and retry rules are kept
# unchanged, but failed train rows no longer carry benchmark labels. Instead a Rubric -> probe ->
# Research verifier produces label-free feedback: a reusable conditional verification policy is
# proposed from public development evidence (the Research arm may read a frozen set of official
# Python documentation pages), instantiated as at most two public probes per task, reviewed for
# admissibility before execution, executed on the Skill-guided product (BigCodeBench: in the
# pinned native container; SearchQA/KOR-Bench: as a V-only judge of the policy's obligations) and
# calibrated against the host's development audit before any probe report reaches the analyst.
# The Skill updater stays the repository's native SkillOpt optimizer, so the comparison with the
# v8/v9 baselines isolates the feedback source (scalar / verifier / oracle label).
VERIFIER_VERSION = "continual-learning-v10"
POLICY_V10 = {
    **POLICY_V9,
    "version": "verifier-feedback-v7",
    "feedback": "rubric_probe_research_verifier_v7",
    # v7 (10/8, KOR chain e): a closed length truncation of a verifier call gets the solver's one length
    # recovery at length_max_tokens; still truncated, empty or provider-filtered replies are unit results
    "verifier_delivery": "closed_length_recovery_terminal_unit_v1",
    "verifier_policy_arm": "adaptive_research",
    "verifier_sources": "python-3.11-official-docs-frozen-v1",
    "verifier_max_pages": 3,
    "verifier_view_rows": 16,
    "verifier_view_output_chars": 3000,
    "verifier_probes_per_task": 2,
    "verifier_review": "pre_execution_admissibility_with_bounded_fact_research_v1",
    # raised calls diagnostic only; v6: decided-row denominators and per-kind admission of `structure`
    "verifier_calibration": "train_host_audit_kind_admission_v6",
    "verifier_min_detections": 1,
    "verifier_min_pass_controls": 5,
    "verifier_max_false_rejection_rate": 0.25,
    "verifier_workers": 8,
}
GENERALIZATION_VERSIONS = (GENERALIZATION_VERSION, CONFIRMATION_VERSION, VERIFIER_VERSION)
HARDENED_VERSIONS = (HARDENED_VERSION, BUDGET_VERSION, *GENERALIZATION_VERSIONS)
DELIVERY_VERSIONS = (DELIVERY_VERSION, *HARDENED_VERSIONS)
VERSIONS = (VERSION, *DELIVERY_VERSIONS)
POLICIES = {VERSION: POLICY, DELIVERY_VERSION: POLICY_V5, HARDENED_VERSION: POLICY_V6, BUDGET_VERSION: POLICY_V7,
            GENERALIZATION_VERSION: POLICY_V8, CONFIRMATION_VERSION: POLICY_V9, VERIFIER_VERSION: POLICY_V10}
RETRY_POLICIES = {VERSION: "closed_network_error_v1", DELIVERY_VERSION: "closed_delivery_error_v2",
                 HARDENED_VERSION: "closed_delivery_error_v3", BUDGET_VERSION: "closed_delivery_error_v3",
                 GENERALIZATION_VERSION: "closed_delivery_error_v3", CONFIRMATION_VERSION: "closed_delivery_error_v3",
                 VERIFIER_VERSION: "closed_delivery_error_v3"}


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
