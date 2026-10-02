"""Evidence-bound delivery observations, separate from semantic correctness.

This pure ledger adapter neither executes a candidate nor verifies files on disk.
The caller must first verify the frozen records and code bytes, then supply their
identities and a normalized observation. A matching digest is a binding, not a
substitute for that verification or a causal explanation. Never infer blame from
an exception name or reinterpret a historical semantic unknown as a failure.

``assess_delivery_outcome`` accepts four observation kinds:

* ``native_execution``: status (delivered/execution_failed/missing_output),
  completed, cleanup_confirmed, generated_lines, exception_type, artifact_sha256s.
  Artifacts must cover every expected case; expected_artifacts is required.
* ``model_call``: closed, http_status, stream_complete, finish_reason,
  transport_error. Only a closed HTTP 200, complete stream with length/max_tokens
  and no transport error establishes completed budget exhaustion.
* ``infrastructure_failure``: stage, failure_confirmed, evidence_record_hash.
  This requires an independently verified infrastructure observation, not a
  generated exception bearing a familiar name.
* ``extraction``: literal_source_verified, response_sha256, literal_code_sha256,
  literal_span. This records a verified literal extraction discrepancy; it
  never substitutes corrected code for the original prediction.

Every observation carries ``identity`` equal to the caller's frozen identity.
Optional reviewed attribution rows use the archived static-audit row format:
all identity fields, attribution, finding, evidence_limit, exception_type and
generated_line. Program defects require a closed matching native failure;
contract ambiguity requires a closed missing output; extractor bugs additionally
bind the response digest, literal code digest and source span. No task-specific
exception rules or benchmark answers are embedded here.
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy

VERSION = "delivery-semantic-attribution-axes-v1"
IDENTITY_FIELDS = frozenset({"task_id", "repeat", "prediction_hash", "original_call_record_hash",
                             "code_sha256", "diagnostic_record_hash"})
INFRASTRUCTURE_STAGES = frozenset({"transport", "api_authorization", "api_service", "container_start",
                                  "dependency_provisioning", "input_mount", "host_resource"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _require(value, message):
    if not value:
        raise ValueError(message)


def _sha256(value):
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _validate_identity(identity):
    _require(type(identity) is dict and set(identity) == IDENTITY_FIELDS, "Invalid delivery identity fields")
    _require(type(identity["task_id"]) is str and bool(identity["task_id"].strip()), "Task identity required")
    _require(type(identity["repeat"]) is int and identity["repeat"] >= 0, "Invalid repeat identity")
    for key in ("prediction_hash", "original_call_record_hash"):
        _require(_sha256(identity[key]), "Invalid " + key)
    for key in ("code_sha256", "diagnostic_record_hash"):
        _require(identity[key] is None or _sha256(identity[key]), "Invalid " + key)


def _validate_score(score):
    _require(type(score) is dict and {"status", "score"} <= set(score), "Semantic score required")
    _require(type(score["status"]) is str and score["status"] in {"pass", "fail", "unknown"},
             "Invalid semantic status")
    if score["status"] == "unknown":
        _require(score["score"] is None, "Semantic unknown must have no numeric score")
    else:
        value = score["score"]
        _require(type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1,
                 "Invalid semantic score value")


def _fields(observation, expected):
    _require(set(observation) == {"identity", "kind"} | set(expected), "Unexpected observation fields")


def _bools(observation, *names):
    for name in names:
        _require(type(observation[name]) is bool, "Explicit boolean required: " + name)


def _native(observation, identity):
    _fields(observation, {"status", "completed", "cleanup_confirmed", "generated_lines", "exception_type",
                          "artifact_sha256s", "expected_artifacts"})
    _bools(observation, "completed", "cleanup_confirmed")
    _require(identity["code_sha256"] is not None and identity["diagnostic_record_hash"] is not None,
             "Native evidence requires original code and diagnostic identities")
    _require(type(observation["status"]) is str
             and observation["status"] in {"delivered", "execution_failed", "missing_output"}, "Invalid native status")
    _require(type(observation["generated_lines"]) is list and all(type(v) is int and v > 0
             for v in observation["generated_lines"]), "Invalid generated source lines")
    _require(observation["exception_type"] is None or (type(observation["exception_type"]) is str
             and bool(observation["exception_type"].strip())), "Invalid exception observation")
    _require(type(observation["artifact_sha256s"]) is list and all(_sha256(v)
             for v in observation["artifact_sha256s"]), "Invalid artifact identities")
    _require(type(observation["expected_artifacts"]) is int and observation["expected_artifacts"] > 0,
             "Expected artifact denominator required")
    _require(len(observation["artifact_sha256s"]) <= observation["expected_artifacts"], "Extra delivery artifacts")
    if not observation["completed"] or not observation["cleanup_confirmed"]:
        return "unknown", "unknown", "native_lifecycle_not_closed"
    if observation["status"] == "delivered":
        _require(observation["exception_type"] is None and not observation["generated_lines"],
                 "Delivered observation cannot contain an execution exception")
        _require(len(observation["artifact_sha256s"]) == observation["expected_artifacts"],
                 "Delivered artifacts do not cover the expected cases")
        return "delivered", "delivered", "all_required_artifacts_observed"
    if observation["status"] == "missing_output":
        _require(observation["exception_type"] is None and not observation["generated_lines"],
                 "Missing-output observation cannot contain an execution exception")
        _require(len(observation["artifact_sha256s"]) < observation["expected_artifacts"],
                 "Missing output conflicts with complete delivery")
        return "not_delivered", "missing_deliverable", "required_artifact_missing_after_completed_execution"
    _require(observation["exception_type"] is not None, "Native failure requires exception evidence")
    return "not_delivered", "execution_failure_unattributed", "observed_exception_does_not_establish_cause"


def _observe(observation, identity):
    if observation is None:
        return "unknown", "unknown", "no_delivery_observation"
    _require(type(observation) is dict and observation.get("identity") == identity, "Observation identity differs")
    _validate_identity(observation["identity"])
    kind = observation.get("kind")
    if kind == "native_execution":
        return _native(observation, identity)
    if kind == "model_call":
        _fields(observation, {"closed", "http_status", "stream_complete", "finish_reason", "transport_error"})
        _bools(observation, "closed", "stream_complete", "transport_error")
        _require(observation["http_status"] is None or (type(observation["http_status"]) is int
                 and 100 <= observation["http_status"] <= 599), "Invalid HTTP status")
        _require(observation["finish_reason"] is None or type(observation["finish_reason"]) is str,
                 "Invalid finish reason")
        if (observation["closed"] and observation["http_status"] == 200 and observation["stream_complete"]
                and not observation["transport_error"] and observation["finish_reason"] in {"length", "max_tokens"}):
            return "not_delivered", "completed_model_budget_exhaustion", "completed_response_exhausted_declared_budget"
        return "unknown", "unknown", "model_receipt_does_not_establish_delivery_or_cause"
    if kind == "infrastructure_failure":
        _fields(observation, {"stage", "failure_confirmed", "evidence_record_hash"})
        _bools(observation, "failure_confirmed")
        _require(type(observation["stage"]) is str and observation["stage"] in INFRASTRUCTURE_STAGES,
                 "Unsupported infrastructure stage")
        _require(_sha256(observation["evidence_record_hash"]), "Infrastructure evidence identity required")
        if observation["stage"] in {"transport", "api_authorization", "api_service"}:
            expected = identity["original_call_record_hash"]
        else:
            expected = identity["diagnostic_record_hash"]
        _require(expected is not None and observation["evidence_record_hash"] == expected,
                 "Infrastructure evidence does not match the original call or diagnostic")
        if observation["failure_confirmed"]:
            return "unknown", "infrastructure_error", "independently_observed_infrastructure_failure"
        return "unknown", "unknown", "infrastructure_failure_not_confirmed"
    if kind == "extraction":
        _fields(observation, {"literal_source_verified", "response_sha256", "literal_code_sha256", "literal_span"})
        _bools(observation, "literal_source_verified")
        _require(identity["code_sha256"] is not None and identity["diagnostic_record_hash"] is not None,
                 "Extraction evidence requires original code and diagnostic identities")
        _require(_sha256(observation["response_sha256"]) and _sha256(observation["literal_code_sha256"]),
                 "Extraction byte identities required")
        span = observation["literal_span"]
        _require(type(span) is list and len(span) == 2 and all(type(v) is int for v in span)
                 and 0 <= span[0] < span[1], "Invalid literal source span")
        return "unknown", "unknown", "extraction_discrepancy_requires_reviewed_attribution"
    raise ValueError("Unsupported delivery observation kind")


def _attribute(attribution, identity, observation, outcome):
    _require(type(attribution) is dict and IDENTITY_FIELDS <= set(attribution), "Attribution identity required")
    claimed_identity = {key: attribution[key] for key in IDENTITY_FIELDS}
    _validate_identity(claimed_identity)
    _require(claimed_identity == identity, "Attribution identity differs")
    _require(identity["code_sha256"] is not None and identity["diagnostic_record_hash"] is not None,
             "Attribution requires original code and diagnostic identities")
    for field in ("finding", "evidence_limit"):
        _require(type(attribution.get(field)) is str and bool(attribution[field].strip()),
                 "Reviewed attribution must state " + field)
    category = attribution.get("attribution")
    if category == "generated_program_defect":
        _require(outcome == "execution_failure_unattributed", "Program defect requires a completed native failure")
        line = attribution.get("generated_line")
        _require(type(line) is int and line > 0 and line in observation["generated_lines"]
                 and attribution.get("exception_type") == observation["exception_type"],
                 "Reviewed defect must match the observed exception and generated line")
        return "not_delivered", "generated_program_failure"
    if category == "task_delivery_contract_ambiguity":
        _require(outcome == "missing_deliverable" and attribution.get("generated_line") is None
                 and attribution.get("exception_type") is None, "Contract ambiguity requires completed missing delivery")
        return "not_delivered", "contract_ambiguity"
    if category == "extractor_bug":
        _require(observation is not None and observation["kind"] == "extraction"
                 and observation["literal_source_verified"]
                 and observation["literal_code_sha256"] != identity["code_sha256"],
                 "Extractor attribution requires a verified literal extraction discrepancy")
        _require(all(attribution.get(key) == observation[key]
                     for key in ("response_sha256", "literal_code_sha256", "literal_span")),
                 "Extractor attribution byte identities differ")
        return "unknown", "extractor_bug"
    raise ValueError("Unsupported reviewed attribution category")


def assess_delivery_outcome(*, identity, semantic_score, observation=None, attribution=None):
    """Return JSON-ready independent axes without changing any semantic score.

    ``identity`` requires task_id, repeat, prediction_hash,
    original_call_record_hash, code_sha256 and diagnostic_record_hash. The last
    two may be null before extraction/execution. Malformed or mismatched evidence
    raises ValueError; absent, incomplete, or insufficient observations remain
    unknown. Attribution text is a host-reviewed finding, never model-supplied
    evidence. This API is not a file verifier, score policy, or learning gate.
    """
    _validate_identity(identity)
    _validate_score(semantic_score)
    if "prediction_hash" in semantic_score:
        _require(semantic_score["prediction_hash"] == identity["prediction_hash"], "Semantic score prediction differs")
    for key in ("task_id", "repeat"):
        if key in semantic_score:
            _require(type(semantic_score[key]) is type(identity[key]) and semantic_score[key] == identity[key],
                     "Semantic score position differs")
    status, outcome, reason = _observe(observation, identity)
    attribution_axis = {"status": "unresolved", "category": "undetermined", "evidence": None}
    if attribution is not None:
        status, outcome = _attribute(attribution, identity, observation, outcome)
        reason = "reviewed_attribution_matches_frozen_evidence"
        attribution_axis = {"status": "confirmed", "category": attribution["attribution"],
                            "evidence": deepcopy(attribution)}
    elif outcome in {"completed_model_budget_exhaustion", "infrastructure_error"}:
        attribution_axis = {"status": "confirmed", "category": outcome, "evidence": deepcopy(observation)}
    _require(not (semantic_score["status"] != "unknown" and status == "not_delivered"),
             "Known semantic score conflicts with missing original delivery")
    result = {"version": VERSION, "identity": deepcopy(identity),
              "delivery": {"status": status, "outcome": outcome, "reason": reason},
              "semantic_score": deepcopy(semantic_score), "attribution": attribution_axis,
              "observation": deepcopy(observation), "original_scores_unchanged": True,
              "feedback_allowed": False, "is_method_effect": False}
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Delivery assessment evidence must be finite JSON data") from None
    return result
