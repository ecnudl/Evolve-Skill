"""Offline transition-aware gate; deliberately not wired into frozen experiments.

Content updates retain v1's dual-reference gain and safety requirements. Scope
expansion re-evaluates source benefit against Base, but source preservation
against Current needs noninferiority/safety, not a second positive improvement.

The committed-source contract MUST come from a trusted execution/evidence layer,
not an LLM-generated assertion. ``evidence_sha256`` identifies that layer's prior
evidence; this pure function does not load or authenticate the evidence payload.
There is intentionally no prior-only benefit exemption: new local evidence
against Base, protection cells and cross-domain evidence remain mandatory.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from skillopt.cross_domain.gate import decide_scope


def content_sha256(content: str) -> str:
    """Hash actual UTF-8 skill text, not a JSON representation or supplied label."""
    if not isinstance(content, str):
        raise ValueError("Skill content must be a string")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field} must be a lowercase SHA256 digest")
    return value


def _source_contract(contract, current_version, skill_hash, config):
    if not isinstance(contract, Mapping):
        raise ValueError("Scope expansion needs an explicit trusted committed_source contract")
    contract = dict(contract)
    if contract.get("status") != "committed" or contract.get("version") != current_version:
        raise ValueError("committed_source must match the committed current version")
    if _sha(contract.get("content_sha256"), "content_sha256") != skill_hash:
        raise ValueError("committed_source content hash does not match actual unchanged content")
    for field in ("source_policy_sha256", "evidence_sha256"):
        _sha(contract.get(field), field)
    domains = contract.get("source_domains")
    if (not isinstance(domains, (list, tuple)) or not domains
            or any(not isinstance(d, str) or not d.strip() for d in domains)
            or len(set(domains)) != len(domains)):
        raise ValueError("committed_source source_domains must be nonempty unique strings")
    domains = list(domains)
    if "source_domains" in config and set(config["source_domains"]) != set(domains):
        raise ValueError("Configured source domains differ from the committed source scope")
    contract["source_domains"] = domains
    return contract


def _identity_rows(records, transition, contract, skill_hash, version):
    """Validate identity before statistics; observed ties alone confer no status."""
    identities = set()
    for row in records:
        if "candidate_is_current" not in row:
            continue
        if not isinstance(row["candidate_is_current"], bool):
            raise ValueError("candidate_is_current must be an explicit boolean contract")
        if row["candidate_is_current"] is not True:
            continue
        if transition != "scope_expansion":
            raise ValueError("Current identity cannot waive a content_update requirement")
        if row.get("domain") not in contract["source_domains"]:
            raise ValueError("Current identity is authorized only inside the committed source scope")
        for prefix in ("candidate", "current"):
            if row.get(f"{prefix}_content_sha256") != skill_hash:
                raise ValueError("Current identity requires matching candidate/current content hashes")
            if row.get(f"{prefix}_version") != version:
                raise ValueError("Current identity requires matching committed versions")
            if row.get(f"{prefix}_source_policy_sha256") != contract["source_policy_sha256"]:
                raise ValueError("Current identity requires both committed source-policy hashes")
        if row.get("candidate") != row.get("current"):
            raise ValueError("Current identity contradicts actual paired scores")
        if "candidate_applied" in row or "current_applied" in row:
            if (not isinstance(row.get("candidate_applied"), bool)
                    or not isinstance(row.get("current_applied"), bool)
                    or row["candidate_applied"] != row["current_applied"]):
                raise ValueError("Current identity contradicts candidate/current application states")
        identities.add(row["id"])
    return identities


def _joint(states):
    states = list(states)
    return "fail" if "fail" in states else "pass" if states and all(s == "pass" for s in states) else "pending"


def decide_transition(
    rows: Iterable[Mapping[str, Any]],
    *,
    transition: str,
    current_content: str,
    candidate_content: str,
    current_version: str,
    committed_source: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Screen ``content_update`` or ``scope_expansion`` without any side effects.

    Rows retain v1's id/domain/mechanism/group and baseline/current/candidate
    binary outcomes. Configuration is v1-compatible, except that the bare
    ``local_already_committed=True`` bypass is forbidden for both transitions.

    A scope expansion requires identical actual content hashes plus::

        committed_source = {
            "status": "committed", "version": current_version,
            "content_sha256": content_sha256(current_content),
            "source_domains": ["coding"],
            "source_policy_sha256": "<trusted source-execution policy SHA256>",
            "evidence_sha256": "<trusted committed-evidence SHA256>",
        }

    This contract is supplied by trusted execution/provenance code, never by the
    skill or an LLM. Its evidence digest is a reference, not evidence validated
    by this function. New source-vs-Base benefit must still pass in every local
    cell, with at least one local cell in each committed source domain.

    Optional ``candidate_is_current=True`` on a source row requires BOTH
    ``candidate_`` and ``current_`` content_sha256, version and
    source_policy_sha256 fields matching the contract, as well as equal actual
    scores. If either candidate_applied/current_applied is supplied, both must
    be explicit equal booleans. This asserts unchanged execution and shared
    outcome replay, not merely independent runs with equal observed scores.
    Only that comparison's safety bounds become structural zeros. Baseline
    safety, cross-domain dual-reference gain, all protective cells and missing
    cells are still checked. Without identity metadata, sampled safety applies.

    Invalid/missing provenance raises ValueError (no approval). Insufficient
    behavioral evidence returns pending/keep_current_scope. The latter preserves
    an existing source version; it is not a second content commit.
    """
    if transition not in {"content_update", "scope_expansion"}:
        raise ValueError("transition must be content_update or scope_expansion")
    if not isinstance(current_version, str) or not current_version.strip():
        raise ValueError("current_version must be a nonempty string")
    cfg = dict(config or {})
    if cfg.get("local_already_committed", False) is not False:
        raise ValueError("Bare local_already_committed is forbidden; use a verified transition contract")
    current_hash = content_sha256(current_content)
    candidate_hash = content_sha256(candidate_content)
    contract = None
    if transition == "scope_expansion":
        if current_hash != candidate_hash or not candidate_content.strip():
            raise ValueError("Scope expansion requires unchanged nonempty actual content")
        contract = _source_contract(committed_source, current_version, current_hash, cfg)
        cfg["source_domains"] = list(contract["source_domains"])
    elif committed_source is not None:
        raise ValueError("committed_source cannot bypass a content_update gate")
    records = [dict(row) for row in rows]
    result = decide_scope(records, cfg)
    identities = _identity_rows(records, transition, contract, current_hash, current_version)
    result.update({"transition": transition, "current_content_sha256": current_hash,
                   "candidate_content_sha256": candidate_hash, "current_version": current_version,
                   "committed_source": contract, "source_identity_ids": sorted(identities)})
    if transition == "content_update":
        return result

    cfg = result["config"]
    source_domains = set(contract["source_domains"])
    if any(a["role"] == "local" and a["domain"] not in source_domains for a in result["group_audits"]):
        raise ValueError("Local evidence cannot add a source domain absent from the committed scope")
    # v1 normalized near_miss/near-miss to nearmiss in its audits.
    cell_ids = defaultdict(set)
    for row in records:
        group = "nearmiss" if row["group"] in {"near_miss", "near-miss"} else row["group"]
        cell_ids[(group, row["domain"], row["mechanism"])].add(row["id"])
    for audit in result["group_audits"]:
        ids = cell_ids[(audit["group"], audit["domain"], audit["mechanism"])]
        if ids and ids <= identities:
            comparison = audit["comparisons"]["current"]
            comparison.update({"structural_identity": True, "delta_interval": [0.0, 0.0],
                               "win_interval": [0.0, 0.0], "loss_interval": [0.0, 0.0],
                               "conditional_harm": 0.0, "conditional_harm_interval": [0.0, 0.0]})
            comparison["checks"].update(noninferiority="pass", conditional_harm="pass", safety="pass")
        audit["safety"] = _joint(c["checks"]["safety"] for c in audit["comparisons"].values())
        audit["required_gain_references"] = ["baseline", "current"]
        if audit["role"] == "local":
            audit["gain"] = audit["comparisons"]["baseline"]["checks"]["gain"]
            audit["required_gain_references"] = ["baseline"]
            audit["current_requirement"] = "noninferiority_and_conditional_harm_or_verified_identity"

    local = [a for a in result["group_audits"] if a["role"] == "local"]
    positive = [a for a in result["group_audits"] if a["role"] == "positive"]
    protected = [a for a in result["group_audits"] if a["role"] == "protected"]
    missing = result["missing_cells"]
    for domain in sorted(source_domains):
        if not any(a["domain"] == domain for a in local):
            missing.append({"group": "source", "domain": domain, "mechanism": "*"})
    source_protected = [a for a in protected if a["domain"] in source_domains]
    local_harm = any(a["safety"] == "fail" for a in local + source_protected)
    local_pass = bool(local) and all(a["safety"] == a["gain"] == "pass" for a in local)
    local_pass = (local_pass and not local_harm and all(a["safety"] == "pass" for a in source_protected)
                  and not any(m["domain"] in source_domains for m in missing))
    positive_pass = bool(positive) and all(a["safety"] == a["gain"] == "pass" for a in positive)
    protective_pass = bool(protected) and all(a["safety"] == "pass" for a in protected)
    enough_domains = len({a["domain"] for a in positive}) >= cfg["min_positive_domains"]
    expansion_harm = any(a["safety"] == "fail" for a in positive + protected)
    reasons = []
    if missing:
        reasons.append("missing_validation_cells")
    if not local_pass:
        reasons.append("fresh_source_benefit_or_preservation_not_established")
    if not positive_pass:
        reasons.append("cross_domain_positive_gain_not_established")
    if not protective_pass:
        reasons.append("protected_cell_safety_not_established")
    if not enough_domains:
        reasons.append("insufficient_cross_domain_coverage")
    if local_harm:
        action = "reject"
        reasons.append("source_scope_harm_detected")
    elif expansion_harm:
        action = "restrict" if local_pass else "reject"
        reasons.append("proposed_scope_harm_detected")
    elif local_pass and positive_pass and protective_pass and enough_domains and not missing:
        action = "cross_domain_commit"
        reasons.append("all_transition_checks_passed")
    elif local_pass:
        action = "keep_current_scope"
        reasons.append("existing_source_scope_preserved_no_expansion")
    else:
        action = "pending"
        reasons.append("insufficient_evidence_keep_current_scope")
    result.update(action=action, reason_codes=reasons, local_accepted=local_pass,
                  cross_domain_accepted=action == "cross_domain_commit")
    result["statistical_limitations"].append(
        "Committed-source provenance is trusted caller input, not LLM certification; its evidence digest is not loaded."
    )
    return result
