"""Versioned obligations and host-grounded feedback, never self-certified scores."""

from __future__ import annotations

import json
import re
from copy import deepcopy

from skillopt.validator_pilot.api import digest

VERSION = "coevolution-v5-evidence-rubric-v1"
STATUSES = {"pass", "fail", "unknown", "not_applicable"}
PHASES = {"development", "promotion", "audit", "final"}
HARD_EVIDENCE = {"execution", "native_oracle"}
FORBIDDEN_PHASES = {"promotion", "calibration", "audit", "final", "holdout", "test", "evaluation", "shadow"}


def strict_object(raw):
    """No completion of truncated braces, no best-of retry, no duplicate keys."""
    if not isinstance(raw, str) or len(raw) > 100000:
        raise ValueError("Expected bounded JSON response")
    text = raw.strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if not match:
            raise ValueError("Unclosed JSON fence")
        text = match.group(1)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("Nonfinite JSON")

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def seal(value, field="record_hash"):
    value = deepcopy(value)
    if field in value:
        raise ValueError("Already sealed")
    json.dumps(value, allow_nan=False)
    return {**value, field: digest(value)}


def verify(value, field="record_hash"):
    if not isinstance(value, dict):
        raise ValueError("Expected sealed object")
    payload = {k: v for k, v in value.items() if k != field}
    json.dumps(payload, allow_nan=False)
    if value.get(field) != digest(payload):
        raise ValueError("Evidence/version checksum mismatch")
    return deepcopy(value)


def _check(identifier, mechanism, obligation, domains, evidence, search, criterion, limits):
    return {"id": identifier, "mechanism": mechanism, "obligation": obligation, "domains": domains,
            "when": "Use only when this obligation is stated by the task contract.", "evidence": evidence,
            "search": search, "criterion": criterion, "limits": limits, "source_refs": []}


def initial_rubric():
    checks = [
        _check("coding_contract", "constraint_preservation", "Fulfil requested behavior and preserve explicitly unchanged behavior.",
               ["coding"], "execution", "Trace changed dependencies and public/legacy/error paths; public examples are not the whole contract.",
               "host_frozen_contract_tests", "No style or preferred reasoning-path requirements; disputed references are unknown."),
        _check("coding_probe", "evidence_verification", "Search for behavior that existing examples leave unchecked.",
               ["coding"], "execution", "Propose legal boundary and shared-dependency inputs, with single-path controls and explicit applicability.",
               "host_legal_differential_execution", "No counterexample found is not proof; reference semantics remain an audited assumption."),
        _check("qa_answer", "constraint_preservation", "Answer the requested question under its entity, relation, and temporal constraints.",
               ["qa"], "native_oracle", "Check the requested answer object and qualifier; use supplied context, not the most salient unrelated fact.",
               "native_searchqa_em_f1", "Native exact match is a benchmark metric, not universal semantic correctness; disputed gold is unknown."),
        _check("qa_citation", "evidence_verification", "Ground claimed evidence in supplied passages without inventing quotations.",
               ["qa"], "citation_match", "Bind citations to exact context spans; distinguish evidence presence from answer entailment.",
               "exact_span_provenance_only", "A matching quote neither establishes entailment nor authorizes Skill approval."),
    ]
    return seal({"version": VERSION, "revision": 0, "parent_hash": None, "checks": checks,
                 "rationale": "Fixed task obligations with evolvable evidence-search strategies."}, "rubric_hash")


def validate_rubric(rubric):
    verify(rubric, "rubric_hash")
    if set(rubric) != {"version", "revision", "parent_hash", "checks", "rationale", "rubric_hash"}:
        raise ValueError("Rubric fields changed")
    if rubric["version"] != VERSION or type(rubric["revision"]) is not int or rubric["revision"] < 0:
        raise ValueError("Invalid Rubric version")
    if (rubric["revision"] == 0 and rubric["parent_hash"] is not None
            or rubric["revision"] > 0 and not re.fullmatch(r"[a-f0-9]{64}", str(rubric["parent_hash"]))):
        raise ValueError("Invalid Rubric parent")
    foundation = {c["id"]: c for c in initial_rubric()["checks"]}
    checks = rubric["checks"]
    if not isinstance(checks, list) or len(checks) != len(foundation):
        raise ValueError("Immutable obligations may not be added or dropped by a proposal")
    ids = [c.get("id") for c in checks if isinstance(c, dict)]
    if len(set(ids)) != len(checks) or set(ids) != set(foundation):
        raise ValueError("Missing/duplicate/unknown obligation")
    for check in checks:
        original = foundation[check["id"]]
        if set(check) != set(original):
            raise ValueError("Check fields changed")
        for field in ("mechanism", "obligation", "domains", "evidence", "criterion"):
            if check[field] != original[field]:
                raise ValueError("Task requirements and evidence authority cannot evolve")
        for field in ("search", "when", "limits"):
            if not isinstance(check[field], str) or not check[field].strip() or len(check[field]) > 2400:
                raise ValueError("Invalid bounded check text")
        if not isinstance(check["source_refs"], list) or len(check["source_refs"]) > 12:
            raise ValueError("Bounded source references required")
    if not isinstance(rubric["rationale"], str) or not 1 <= len(rubric["rationale"]) <= 6000:
        raise ValueError("Bounded rationale required")
    return deepcopy(rubric)


def apply_rubric_patch(rubric, patch):
    current = validate_rubric(rubric)
    if not isinstance(patch, dict) or set(patch) != {"changes", "rationale", "source_refs"}:
        raise ValueError("Invalid bounded Rubric patch")
    changes = patch["changes"]
    if not isinstance(changes, list) or not 1 <= len(changes) <= 3:
        raise ValueError("One to three check changes required")
    if not isinstance(patch["source_refs"], list) or len(patch["source_refs"]) > 12:
        raise ValueError("Invalid source references")
    indexed, seen = {c["id"]: c for c in current["checks"]}, set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"check_id", "search", "when", "limits"}:
            raise ValueError("Only search, when and limits may be modified")
        identifier = change["check_id"]
        if identifier not in indexed or identifier in seen:
            raise ValueError("Duplicate or unknown check modification")
        seen.add(identifier)
        if all(indexed[identifier][k] == change[k] for k in ("search", "when", "limits")):
            raise ValueError("No substantive search change")
        indexed[identifier].update({k: change[k] for k in ("search", "when", "limits")})
        indexed[identifier]["source_refs"] = deepcopy(patch["source_refs"])
    value = {k: v for k, v in current.items() if k != "rubric_hash"}
    value.update(revision=current["revision"] + 1, parent_hash=current["rubric_hash"], rationale=patch["rationale"])
    return validate_rubric(seal(value, "rubric_hash"))


def make_assessment(*, check_id, task_id, domain, phase, artifact_hash, rubric_hash,
                    status, evidence_kind, verified, gate_eligible, details):
    if status not in STATUSES or phase not in PHASES or domain not in {"coding", "qa"}:
        raise ValueError("Invalid assessment status, phase or domain")
    if type(verified) is not bool or type(gate_eligible) is not bool or not isinstance(details, dict):
        raise ValueError("Explicit host evidence flags required")
    if gate_eligible and (not verified or evidence_kind not in HARD_EVIDENCE or status not in {"pass", "fail"}):
        raise ValueError("Unverified, unknown or soft evidence cannot authorize approval")
    for value in (artifact_hash, rubric_hash):
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("Exact artifact and Rubric hashes required")
    return seal({"check_id": check_id, "task_id": task_id, "domain": domain, "phase": phase,
                 "artifact_hash": artifact_hash, "rubric_hash": rubric_hash, "status": status,
                 "evidence_kind": evidence_kind, "verified": verified, "gate_eligible": gate_eligible,
                 "details": deepcopy(details)}, "receipt_hash")


def development_only(value):
    """Reject forbidden feedback recursively; renaming the outer phase is insufficient."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"phase", "split", "source_phase", "source_split", "task_split", "requested_phase"}:
                pieces = set(re.split(r"[^a-z]+", str(child).lower()))
                if pieces & FORBIDDEN_PHASES:
                    raise ValueError("Promotion/audit/final data cannot become development feedback")
            development_only(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            development_only(child)


def feedback_packet(*, task_id, cluster_id, domain, assessments, artifact, contract,
                    comparisons=(), hypotheses=(), research_context=None, task_context=None):
    if not assessments:
        raise ValueError("Feedback needs actual observations")
    checked = [verify(row, "receipt_hash") for row in assessments]
    for row in checked:
        if (row["phase"] != "development" or row["task_id"] != task_id or row["domain"] != domain
                or row["artifact_hash"] != digest(artifact)):
            raise ValueError("Feedback task/artifact/split identity mismatch")
    if len({row["rubric_hash"] for row in checked}) != 1:
        raise ValueError("A feedback packet must use one frozen Rubric")
    facts, guidance = [], []
    for row in checked:
        if row["verified"] and row["status"] in {"pass", "fail"}:
            facts.append({"receipt_hash": row["receipt_hash"], "check_id": row["check_id"],
                          "status": row["status"], "evidence_kind": row["evidence_kind"],
                          "details": deepcopy(row["details"])})
        if row["status"] == "fail" and row["gate_eligible"]:
            guidance.append({"receipt_hash": row["receipt_hash"], "check_id": row["check_id"],
                             "action": "Repair the demonstrated contract mismatch; preserve passing and non-applicable paths.",
                             "status": "repair_hypothesis_requires_reexecution"})
        elif row["status"] == "unknown":
            guidance.append({"receipt_hash": row["receipt_hash"], "check_id": row["check_id"],
                             "action": "Collect missing evidence; do not treat an unknown as correctness or a semantic defect.",
                             "status": "investigation_not_bug_claim"})
    value = {"phase": "development", "task_id": task_id, "cluster_id": cluster_id, "domain": domain,
             "artifact_hash": digest(artifact), "rubric_hash": checked[0]["rubric_hash"],
             "artifact": deepcopy(artifact), "contract": contract, "task_context": deepcopy(task_context),
             "observations": checked, "facts": facts,
             "comparisons": deepcopy(list(comparisons)),
             "hypotheses": [{"text": text, "status": "unverified_hypothesis"} for text in hypotheses],
             "repair_guidance": guidance, "research_context": deepcopy(research_context or {}),
             "no_causal_claim_from_single_pair": True}
    development_only(value)
    return seal(value)


def optimizer_messages(working, repair_parent, packets):
    for packet in packets:
        verify(packet)
    development_only(packets)
    development_only(repair_parent)
    system = (
        "Improve a procedural Skill from DEVELOPMENT evidence. Return 100-450 words of plain text, "
        "no fences. Task contracts outrank Skills. Learn a bounded mechanism, its applicability, "
        "counterconditions and fallback; do not memorize answers, task IDs or constants. Facts have "
        "host receipts; diagnoses and repair suggestions are hypotheses requiring new execution. "
        "Working is admitted for development; repair_parent is NOT approved for deployment. "
        "Distinguish transport/delivery faults from semantic regressions. Preserve passing paths. "
        "You cannot change the evaluator, task requirements, or authorize your own Skill."
    )
    unique = {p["record_hash"]: p for p in packets}
    selected, size = [], 0
    for packet in sorted(unique.values(), key=lambda p: (
            not any(r["status"] == "fail" for r in p["observations"]), p["record_hash"])):
        length = len(json.dumps(packet, ensure_ascii=False))
        if len(selected) < 6 and size + length <= 100000:
            selected.append(packet)
            size += length
    if packets and not selected:
        raise ValueError("No complete feedback packet fits the context budget")
    repair = None
    if repair_parent:
        repair = {k: deepcopy(repair_parent[k]) for k in ("candidate", "round_index", "usage", "reason")
                  if k in repair_parent}
        repair["gate_summaries"] = {name: {k: deepcopy(repair_parent[name][k])
                                          for k in ("action", "reasons", "harms", "gains")}
                                     for name in ("source", "replay", "scope") if repair_parent.get(name)}
        repair["eligible_for_execution"] = False
    payload = {"working": working, "repair_parent": repair, "development_evidence": selected,
               "evidence_manifest": [{"hash": p["record_hash"], "model_visible": p in selected}
                                     for p in unique.values()],
               "context_selection": "Bounded complete packets, no code or expected-value truncation.",
               "final_or_promotion_feedback_available": False}
    return system, json.dumps(payload, ensure_ascii=False, sort_keys=True)


def feedback_summary(packets):
    rows = [r for p in packets for r in verify(p)["observations"]]
    return {"packets": len(packets), "observations": len(rows),
            "verified_failures": sum(r["status"] == "fail" and r["gate_eligible"] for r in rows),
            "unknown": sum(r["status"] == "unknown" for r in rows),
            "not_applicable": sum(r["status"] == "not_applicable" for r in rows),
            "unverified_hypotheses_not_facts": True}
