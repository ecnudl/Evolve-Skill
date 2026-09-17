"""Isolated, model-free Coding development evidence view for a future round.

This is not wired into frozen V5/V6, an external research query builder, a
validator, or an execution authenticator. Checksums detect content inconsistency,
not a dishonest producer. The caller remains responsible for trusted acquisition
and for an aggregate budget across multiple views.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

_PACKET_FIELDS = {
    "phase", "task_id", "cluster_id", "domain", "artifact_hash", "rubric_hash",
    "artifact", "contract", "task_context", "observations", "facts", "comparisons",
    "hypotheses", "repair_guidance", "research_context", "no_causal_claim_from_single_pair",
    "record_hash",
}
_ASSESSMENT_FIELDS = {
    "check_id", "task_id", "domain", "phase", "artifact_hash", "rubric_hash", "status",
    "evidence_kind", "verified", "gate_eligible", "details", "receipt_hash",
}
_STATUSES = {"pass", "fail", "unknown", "not_applicable"}
_PHASE_KEYS = {
    "phase", "split", "source_phase", "source_split", "task_split", "requested_phase",
    "dataset_split", "partition",
}
_NON_DEVELOPMENT = {
    "promotion", "calibration", "audit", "final", "holdout", "heldout", "held", "test",
    "evaluation", "eval", "shadow", "confirmation", "validation",
}
_FORBIDDEN_PAYLOAD_KEYS = {
    "truth", "oracle_label", "calibration_label", "promotion_result", "audit_result",
    "final_results", "reference_implementation", "calibration", "promotion", "final",
    "holdout", "test_results",
}
_GUARDRAILS = [
    "The initial task fixture is author-provided starter code, NOT a Baseline execution. "
    "Never substitute it for unavailable Base/Current/Candidate solver artifacts.",
    "Pass and unknown observations do not establish a discovered defect. A pass is "
    "limited to its executed checks; unknown is missing evidence, not a semantic failure.",
    "Exact file bytes, matching hashes, and quoted source text do not establish the truth "
    "of a semantic or causal claim. Quotes establish provenance, not entailment.",
    "A comparison arm reference is not a verified execution receipt. Shared artifact "
    "hashes establish identical content, not independent runs or identical provenance.",
    "Local seals verify consistency, not an honest host, an API invocation, or external "
    "authentication. Hypotheses and repair advice require independent re-execution.",
    "This complete Coding development view is for internal diagnosis, not an external "
    "search query. Task contracts outrank documentation; no Skill or Rubric is approved here.",
]


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Evidence must be finite JSON data") from exc


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Exact lowercase SHA-256 reference required")
    return value


def _verify(value, field="record_hash"):
    if not isinstance(value, dict):
        raise ValueError("Expected a sealed evidence object")
    _hash(value.get(field))
    if value[field] != _digest({k: v for k, v in value.items() if k != field}):
        raise ValueError("Evidence checksum mismatch")


def _development_only(value, *, depth=0, parent=None):
    if depth > 24:
        raise ValueError("Development evidence nesting exceeds limit")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Evidence keys must be strings")
            name = key.casefold()
            if name in _FORBIDDEN_PAYLOAD_KEYS or (name == "audit" and parent != "research_context"):
                raise ValueError("Non-development labels, results or reference implementations are forbidden")
            if name in _PHASE_KEYS:
                if not isinstance(child, str):
                    raise ValueError("Provenance markers must be strings")
                if set(re.split(r"[^a-z0-9]+", child.casefold())) & _NON_DEVELOPMENT:
                    raise ValueError("Non-development provenance is forbidden")
            _development_only(child, depth=depth + 1, parent=name)
    elif isinstance(value, list):
        for child in value:
            _development_only(child, depth=depth + 1, parent=parent)
    elif value is not None and type(value) not in {str, int, float, bool}:
        raise ValueError("Evidence must use JSON scalar/list/object types")


def _assessment(row, packet, *, artifact_hash):
    _verify(row, "receipt_hash")
    if set(row) != _ASSESSMENT_FIELDS:
        raise ValueError("Unexpected assessment schema")
    if any(row[k] != packet[k] for k in ("phase", "task_id", "domain", "rubric_hash")):
        raise ValueError("Assessment task, phase, domain or Rubric mismatch")
    if row["artifact_hash"] != artifact_hash:
        raise ValueError("Assessment artifact mismatch")
    if (not isinstance(row["status"], str) or row["status"] not in _STATUSES or not isinstance(row["check_id"], str)
            or not row["check_id"] or not isinstance(row["details"], dict)
            or not isinstance(row["evidence_kind"], str)
            or row["evidence_kind"] not in {"execution", "native_oracle", "citation_match"}
            or type(row["verified"]) is not bool or type(row["gate_eligible"]) is not bool):
        raise ValueError("Invalid assessment evidence fields")
    if row["gate_eligible"] and (not row["verified"] or row["status"] not in {"pass", "fail"}
                                 or row["evidence_kind"] not in {"execution", "native_oracle"}):
        raise ValueError("Unknown or soft evidence cannot authorize a gate")


def _artifact(value):
    if value is not None and (not isinstance(value, dict)
                              or not all(isinstance(k, str) and isinstance(v, str)
                                         for k, v in value.items())):
        raise ValueError("Coding artifact must be a file-to-text object or null")


def _registry(records, packet, referenced):
    if not isinstance(records, dict):
        raise ValueError("Per-packet artifact registry must be a mapping")
    required = {"phase", "task_id", "artifact_hash", "artifact", "request_hashes", "record_hash"}
    for artifact_hash, record in records.items():
        _hash(artifact_hash)
        _verify(record)
        if not required <= set(record) or set(record) - required - {"skill_hash", "assessments"}:
            raise ValueError("Unexpected solver artifact registry schema")
        if artifact_hash not in referenced:
            raise ValueError("Registry contains an artifact unrelated to this packet")
        if record["phase"] != "development" or record["task_id"] != packet["task_id"]:
            raise ValueError("Registry task or phase mismatch")
        _artifact(record["artifact"])
        if record["artifact_hash"] != artifact_hash or _digest(record["artifact"]) != artifact_hash:
            raise ValueError("Registry artifact content mismatch")
        requests = record["request_hashes"]
        if not isinstance(requests, list) or not requests:
            raise ValueError("Registry requires solver request hash references")
        for request_hash in requests:
            _hash(request_hash)
        if len(set(requests)) != len(requests):
            raise ValueError("Registry requires distinct solver request hash references")
        if "skill_hash" in record:
            _hash(record["skill_hash"])
        if not isinstance(record.get("assessments", []), list):
            raise ValueError("Registry assessments must be a list")
        for row in record.get("assessments", []):
            _assessment(row, packet, artifact_hash=artifact_hash)
            for detail_key, record_key in (("solver_request_hashes", "request_hashes"),
                                           ("solver_skill_hash", "skill_hash")):
                if detail_key in row["details"] and row["details"][detail_key] != record.get(record_key):
                    raise ValueError("Registry solver provenance disagrees with its assessment receipt")


def research_evidence_view(packet, *, artifact_registry=None, max_chars=110000):
    """Return a sealed complete view; reject invalid provenance or any budget overflow.

    Only V5 Coding development ``feedback_packet`` objects are accepted. Registry
    keys are artifact hashes; each sealed record has ``phase``, ``task_id``,
    ``artifact_hash``, ``artifact``, nonempty ``request_hashes`` and ``record_hash``.
    Optional ``skill_hash`` and sealed ``assessments`` are retained. If assessments
    carry solver request/Skill identities, those must match the registry record.
    Supply only records for this task and referenced content. No registry is required: absent
    artifacts/receipts remain explicitly unavailable. Hash-equal packet content can
    resolve bytes, but never the provenance of another arm's execution.

    ``max_chars`` bounds the canonical compact JSON of the ENTIRE returned object,
    including its seal. There is no truncation or packet selection. This is a
    per-packet limit; aggregate and token budgets are the caller's responsibility.
    """
    if type(max_chars) is not int or not 1 <= max_chars <= 1000000:
        raise ValueError("A positive per-packet character budget up to 1000000 is required")
    records = {} if artifact_registry is None else artifact_registry
    if len(_json(packet)) + len(_json(records)) > max_chars:
        raise ValueError("Complete evidence exceeds the character budget")
    _verify(packet)
    _development_only(packet)
    _development_only(records)
    if set(packet) != _PACKET_FIELDS:
        raise ValueError("Expected the complete V5 feedback_packet schema")
    if packet["phase"] != "development" or packet["domain"] != "coding":
        raise ValueError("Only Coding development evidence is accepted; QA needs its own projection")
    for key in ("task_id", "cluster_id", "contract"):
        if not isinstance(packet[key], str) or not packet[key]:
            raise ValueError("Task identity and contract are required")
    _hash(packet["artifact_hash"])
    _hash(packet["rubric_hash"])
    _artifact(packet["artifact"])
    if _digest(packet["artifact"]) != packet["artifact_hash"]:
        raise ValueError("Evaluated artifact hash mismatch")
    for key in ("observations", "facts", "comparisons", "hypotheses", "repair_guidance"):
        if not isinstance(packet[key], list):
            raise ValueError("Feedback collections must be lists")
    if not packet["observations"] or packet["no_causal_claim_from_single_pair"] is not True:
        raise ValueError("Actual observations and explicit causal limitation are required")
    if not isinstance(packet["research_context"], dict):
        raise ValueError("Research context must be an object")
    receipts = {}
    expected_facts = []
    for row in packet["observations"]:
        _assessment(row, packet, artifact_hash=packet["artifact_hash"])
        if row["receipt_hash"] in receipts:
            raise ValueError("Duplicate observation receipt")
        receipts[row["receipt_hash"]] = row
        if row["verified"] and row["status"] in {"pass", "fail"}:
            expected_facts.append({k: row[k] for k in ("receipt_hash", "check_id", "status", "evidence_kind", "details")})
    if packet["facts"] != expected_facts:
        raise ValueError("Fact summary does not exactly match verified observations")
    for hypothesis in packet["hypotheses"]:
        if (not isinstance(hypothesis, dict) or set(hypothesis) != {"text", "status"}
                or not isinstance(hypothesis["text"], str) or hypothesis["status"] != "unverified_hypothesis"):
            raise ValueError("Hypotheses must remain explicitly unverified")
    for advice in packet["repair_guidance"]:
        if not isinstance(advice, dict) or set(advice) != {"receipt_hash", "check_id", "action", "status"}:
            raise ValueError("Unexpected repair guidance schema")
        _hash(advice["receipt_hash"])
        row = receipts.get(advice["receipt_hash"])
        if row is None or row["check_id"] != advice["check_id"] or not isinstance(advice["action"], str):
            raise ValueError("Repair guidance receipt mismatch")
        expected = ("repair_hypothesis_requires_reexecution" if row["status"] == "fail" and row["gate_eligible"]
                    else "investigation_not_bug_claim" if row["status"] == "unknown" else None)
        if expected is None or advice["status"] != expected:
            raise ValueError("Repair guidance promotes an unsupported defect claim")

    referenced = {packet["artifact_hash"]}
    for comparison in packet["comparisons"]:
        if (not isinstance(comparison, dict) or set(comparison) != {"repeat", "arms", "interpretation"}
                or type(comparison["repeat"]) is not int or comparison["repeat"] < 0
                or comparison["interpretation"] != "paired_observation_not_causation"
                or not isinstance(comparison["arms"], dict)
                or set(comparison["arms"]) != {"baseline", "current", "candidate"}):
            raise ValueError("Expected bounded paired observation references")
        for arm, rows in comparison["arms"].items():
            if not isinstance(rows, list) or not rows:
                raise ValueError("Each comparison arm needs observation references")
            for ref in rows:
                if (not isinstance(ref, dict) or set(ref) != {"check_id", "status", "receipt_hash", "artifact_hash"}
                        or not isinstance(ref["check_id"], str) or not ref["check_id"]
                        or not isinstance(ref["status"], str) or ref["status"] not in _STATUSES):
                    raise ValueError("Invalid comparison reference")
                _hash(ref["receipt_hash"])
                referenced.add(_hash(ref["artifact_hash"]))
                if arm == "candidate" and ref["artifact_hash"] != packet["artifact_hash"]:
                    raise ValueError("Candidate comparison and evaluated artifact mismatch")
    _registry(records, packet, referenced)
    receipt_origins = {key: "packet_observation" for key in receipts}
    for artifact_hash, record in records.items():
        for row in record.get("assessments", []):
            if row["receipt_hash"] not in receipts:
                receipts[row["receipt_hash"]] = row
                receipt_origins[row["receipt_hash"]] = "supplied_registry_assessment"

    comparisons = []
    for comparison in packet["comparisons"]:
        result = deepcopy(comparison)
        result["reference_checks"] = {}
        for arm, refs in comparison["arms"].items():
            checks = []
            for ref in refs:
                observed = receipts.get(ref["receipt_hash"])
                if observed is not None and any(observed[k] != ref[k] for k in ref):
                    raise ValueError("Comparison status or provenance disagrees with its receipt")
                artifact_hash = ref["artifact_hash"]
                if artifact_hash in records:
                    content_source, available = "supplied_solver_artifact_registry", records[artifact_hash]["artifact"] is not None
                elif artifact_hash == packet["artifact_hash"]:
                    content_source, available = "evaluated_artifact_identical_content_hash", packet["artifact"] is not None
                else:
                    content_source, available = "unavailable_not_inferred_from_initial_fixture", False
                checks.append({"receipt_hash": ref["receipt_hash"], "artifact_hash": artifact_hash,
                               "receipt_integrity": receipt_origins.get(ref["receipt_hash"], "unavailable_reference_only"),
                               "artifact_content_available": available, "artifact_content_source": content_source,
                               "execution_authenticated": False})
            result["reference_checks"][arm] = checks
        comparisons.append(result)

    context = deepcopy(packet["task_context"])
    if context is not None and not isinstance(context, dict):
        raise ValueError("Public task context must be an object or null")
    if context is not None:
        for key in ("id", "task_id"):
            if key in context and context[key] != packet["task_id"]:
                raise ValueError("Public task context identity mismatch")
    fixture = context.pop("files", None) if context is not None else None
    _artifact(fixture)
    view = {
        "version": "coding-development-evidence-view-v1", "phase": "development", "domain": "coding",
        "task_id": packet["task_id"], "cluster_id": packet["cluster_id"], "rubric_hash": packet["rubric_hash"],
        "source_packet_hash": packet["record_hash"], "guardrails": list(_GUARDRAILS),
        "public_task": {"contract": packet["contract"], "context_without_initial_fixture": context},
        "initial_task_fixture": {"role": "original_task_fixture_NOT_execution", "artifact": fixture,
                                 "available": fixture is not None,
                                 "content_hash": _digest(fixture) if fixture is not None else None},
        "evaluated_artifact": {"artifact": deepcopy(packet["artifact"]), "artifact_hash": packet["artifact_hash"],
                               "available": packet["artifact"] is not None,
                               "role": "actual_packet_evaluated_artifact", "content_hash_verified": True},
        "observations": deepcopy(packet["observations"]), "verified_observation_facts": deepcopy(packet["facts"]),
        "paired_observations": comparisons, "supplied_solver_artifact_registry": deepcopy(records),
        "unsupported_hypotheses": deepcopy(packet["hypotheses"]),
        "repair_advice_requires_reexecution": deepcopy(packet["repair_guidance"]),
        "research_context": deepcopy(packet["research_context"]), "no_causal_claim_from_single_pair": True,
        "context_budget": {"max_chars": max_chars, "unit": "canonical_json_unicode_characters",
                           "scope": "one_complete_returned_view_including_seal", "truncation": False},
    }
    view["record_hash"] = _digest(view)
    if len(_json(view)) > max_chars:
        raise ValueError("Complete evidence view exceeds the character budget; nothing was truncated")
    return view
