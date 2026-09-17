"""Evidence-bound local learning and deployment are deliberately separate.

These operational pilot gates are not statistical safety certificates. The
caller seals every decision before using its development feedback in learning.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from skillopt.validator_pilot.api import digest

POLICIES = {"coupled_evolving", "decoupled_fixed", "decoupled_evolving"}
MAX_ARCHIVED_CANDIDATES = 4


def _seal(value):
    return {**value, "state_hash": digest(value)}


def initial_state(policy: str) -> dict:
    if policy not in POLICIES:
        raise ValueError("Unknown preregistered policy")
    return _seal(
        {
            "version": "local-deployed-v3",
            "policy": policy,
            "revision": 0,
            "working_local": "",
            "approved_deployed": "",
            "working_scope": {
                "usage": "sandbox_development_only",
                "deployment_allowed": False,
                "scope_expansion_approved": False,
            },
            "approved_scope": None,
            "pending": [],
            "quarantine": [],
            "last_round": None,
            "last_transition": None,
        }
    )


def _candidate(candidate):
    if not isinstance(candidate, Mapping):
        raise TypeError("Candidate must be a proposal mapping")
    return (
        candidate.get("valid") is True
        and isinstance(candidate.get("content"), str)
        and bool(candidate["content"].strip())
    )


def _evaluation(value):
    """Normalize ONLY the agreed, host-derived evaluation schema."""
    if not isinstance(value, Mapping):
        return {"available": False, "case_results": {}, "preserved": {}, "hard": None}
    result = deepcopy(dict(value))
    results, preserved = result.get("case_results", {}), result.get("preserved", {})
    valid_maps = all(
        isinstance(v, Mapping) and all(isinstance(k, str) and type(b) is bool for k, b in v.items())
        for v in (results, preserved)
    )
    total, passes = result.get("case_total"), result.get("case_passes")
    numeric = type(total) is int and type(passes) is int and total > 0 and 0 <= passes <= total
    complete = (
        result.get("available") is True
        and valid_maps
        and bool(results)
        and bool(preserved)
        and numeric
        and len(results) == total
        and sum(results.values()) == passes
        and set(preserved) <= set(results)
        and all(results[k] == v for k, v in preserved.items())
        and type(result.get("hard")) is bool
        and result["hard"] == all(results.values())
    )
    # Malformed entries cannot silently become true/false or erase valid known checks.
    result.update(
        available=complete,
        case_results={k: v for k, v in results.items() if isinstance(k, str) and type(v) is bool}
        if isinstance(results, Mapping)
        else {},
        preserved={k: v for k, v in preserved.items() if isinstance(k, str) and type(v) is bool}
        if isinstance(preserved, Mapping)
        else {},
    )
    if not complete:
        result["hard"] = None
    return result


def _inspect(pairs, reference_arm, *, replay=False, scope=False):
    evidence = {
        "n_pairs": len(pairs),
        "complete_pairs": 0,
        "unknown_pairs": [],
        "alignment_errors": [],
        "known_losses": [],
        "search_unknown": [],
        "score_deltas_working": [],
        "score_deltas_base": [],
        "hard_deltas_working": [],
        "hard_deltas_base": [],
    }
    seen = set()
    for ordinal, pair in enumerate(pairs):
        if not isinstance(pair, Mapping):
            evidence["unknown_pairs"].append({"ordinal": ordinal, "reason": "invalid_pair"})
            continue
        key = pair.get("id"), pair.get("repeat")
        if not isinstance(key[0], str) or not key[0] or type(key[1]) is not int or key in seen:
            evidence["alignment_errors"].append({"ordinal": ordinal, "reason": "invalid_or_duplicate_pair_identity"})
        seen.add(key)
        arms = {name: _evaluation(pair.get(name)) for name in ("base", reference_arm, "candidate")}
        candidate = arms["candidate"]
        for name in ("base", reference_arm):
            reference = arms[name]
            field = "case_results" if replay or scope else "preserved"
            for label in sorted(set(reference[field]) & set(candidate[field])):
                if reference[field][label] is True and candidate[field][label] is False:
                    evidence["known_losses"].append(
                        {
                            "id": key[0],
                            "repeat": key[1],
                            "reference": name,
                            "case": label,
                            "kind": "replay" if replay else "scope_basis" if scope else "source_preserved",
                        }
                    )
        # Optional incremental model probes: real mismatches count, unavailability
        # cannot invalidate the independently complete deterministic foundation.
        if scope:
            probe = pair.get("probe_results", {})
            if isinstance(probe, Mapping):
                cand = probe.get("candidate", {})
                for name in ("base", reference_arm):
                    ref = probe.get(name, {})
                    if isinstance(cand, Mapping) and isinstance(ref, Mapping):
                        for label in sorted(set(ref) & set(cand)):
                            if ref[label] is True and cand[label] is False:
                                evidence["known_losses"].append(
                                    {
                                        "id": key[0],
                                        "repeat": key[1],
                                        "reference": name,
                                        "case": label,
                                        "kind": "verified_model_probe",
                                    }
                                )
                        if any(v is None for v in list(cand.values()) + list(ref.values())):
                            evidence["search_unknown"].append(
                                {"id": key[0], "repeat": key[1], "reason": "probe_execution_unknown"}
                            )
            if pair.get("search_unknown"):
                evidence["search_unknown"].append(
                    {"id": key[0], "repeat": key[1], "reason": deepcopy(pair["search_unknown"])}
                )
        complete = all(v["available"] for v in arms.values())
        aligned = all(
            set(v["case_results"]) == set(candidate["case_results"])
            and set(v["preserved"]) == set(candidate["preserved"])
            for v in arms.values()
        )
        if not aligned:
            evidence["alignment_errors"].append({"id": key[0], "repeat": key[1], "reason": "case_ids_differ"})
        if not complete or not aligned:
            evidence["unknown_pairs"].append(
                {
                    "id": key[0],
                    "repeat": key[1],
                    "unavailable_arms": [name for name, value in arms.items() if not value["available"]],
                }
            )
            continue
        evidence["complete_pairs"] += 1
        for name, suffix in ((reference_arm, "working"), ("base", "base")):
            evidence["score_deltas_" + suffix].append(
                candidate["case_passes"] / candidate["case_total"]
                - arms[name]["case_passes"] / arms[name]["case_total"]
            )
            evidence["hard_deltas_" + suffix].append(int(candidate["hard"]) - int(arms[name]["hard"]))
    for suffix in ("working", "base"):
        values = evidence["score_deltas_" + suffix]
        evidence["mean_score_gain_" + suffix] = sum(values) / len(values) if values else None
        evidence["hard_gain_" + suffix] = sum(evidence["hard_deltas_" + suffix])
    return evidence


def _decision(candidate, passed, action, reasons, evidence):
    return {
        "passed": passed,
        "action": action,
        "reason": reasons[0],
        "reasons": reasons,
        "evidence": evidence,
        "candidate_hash": digest(dict(candidate)),
        "statistical_safety_certified": False,
    }


def decide_local(candidate, source_pairs, replay_pairs=()) -> dict:
    source = _inspect(source_pairs, "working")
    replay = _inspect(replay_pairs, "working", replay=True)
    evidence = {"source": source, "replay": replay}
    harm, other = [], []
    if source["known_losses"]:
        harm.append("source_preserved_regression")
    if replay["known_losses"]:
        harm.append("retained_case_regression")
    complete = bool(source_pairs) and not any(v["unknown_pairs"] or v["alignment_errors"] for v in (source, replay))
    if complete:
        for suffix in ("working", "base"):
            if source["mean_score_gain_" + suffix] < -1e-12:
                harm.append("source_score_regression_vs_" + suffix)
            if source["hard_gain_" + suffix] < 0:
                harm.append("source_hard_regression_vs_" + suffix)
    if not _candidate(candidate):
        other.append("invalid_candidate")
    if not complete:
        other.append("local_evidence_unavailable_or_misaligned")
    if complete and any(source["mean_score_gain_" + s] <= 1e-12 for s in ("working", "base")):
        other.append("no_positive_mean_source_gain_against_both_references")
    reasons = harm + other
    if reasons:
        return _decision(
            candidate, False, "Reject" if harm or "invalid_candidate" in other else "Restrict", reasons, evidence
        )
    return _decision(candidate, True, "LocalCommit", ["positive_local_gain_with_retention"], evidence)


def decide_scope(candidate, local_decision, gate_pairs) -> dict:
    if local_decision.get("candidate_hash") != digest(dict(candidate)):
        raise ValueError("Local decision belongs to a different candidate")
    gate = _inspect(gate_pairs, "approved", scope=True)
    reasons = []
    if gate["known_losses"]:
        reasons.append("known_scope_regression")
    if local_decision.get("passed") is not True:
        reasons.append("local_gate_not_passed")
    if not gate_pairs or gate["unknown_pairs"] or gate["alignment_errors"]:
        reasons.append("deterministic_scope_evidence_unavailable_or_misaligned")
    if not _candidate(candidate):
        reasons.append("invalid_candidate")
    evidence = {
        "gate": gate,
        "local_decision_hash": digest(local_decision),
        "model_search_unknown_does_not_erase_foundation": True,
    }
    if reasons:
        return _decision(
            candidate,
            False,
            "Reject" if gate["known_losses"] or not _candidate(candidate) else "Restrict",
            reasons,
            evidence,
        )
    return _decision(candidate, True, "ScopeCommit", ["local_gain_and_no_observed_scope_loss"], evidence)


def advance_state(state, candidate, local_decision, scope_decision, *, round_index: int) -> dict:
    current = deepcopy(dict(state))
    checksum = current.pop("state_hash", None)
    if checksum != digest(current) or current.get("policy") not in POLICIES:
        raise ValueError("Learning state integrity mismatch")
    if (
        type(round_index) is not int
        or round_index < 0
        or (current["last_round"] is not None and round_index <= current["last_round"])
    ):
        raise ValueError("Rounds must advance monotonically")
    candidate_hash = digest(dict(candidate))
    if any(d.get("candidate_hash") != candidate_hash for d in (local_decision, scope_decision)):
        raise ValueError("Decision candidate provenance mismatch")
    local = local_decision.get("passed") is True
    deployed = scope_decision.get("passed") is True
    if deployed and not local:
        raise ValueError("Deployment requires local acceptance")
    if (local or deployed) and not _candidate(candidate):
        raise ValueError("Invalid candidate cannot be inherited")
    advance_local = local and (current["policy"] != "coupled_evolving" or deployed)
    if advance_local:
        current["working_local"] = candidate["content"]
    if deployed:
        current["approved_deployed"] = candidate["content"]
        current["approved_scope"] = {
            "usage": "approved_coding_project_policy",
            "statistical_safety_certified": False,
            "scope_decision_hash": digest(scope_decision),
        }
    record = {
        "round": round_index,
        "candidate": deepcopy(dict(candidate)),
        "local_decision": deepcopy(local_decision),
        "scope_decision": deepcopy(scope_decision),
        "eligible_as_execution_parent": advance_local,
        "execution_parent_usage": "sandbox_development_only" if advance_local else None,
        "restricted_scope_harm": local and scope_decision["action"] == "Reject",
    }
    # Scope-only harm does not invalidate a narrowly validated LOCAL parent.
    # It is nevertheless quarantined from deployment outside that local scope.
    if not deployed:
        bucket = (
            "quarantine"
            if (local_decision["action"] == "Reject" or scope_decision["action"] == "Reject")
            else "pending"
        )
        current[bucket] = (current[bucket] + [record])[-MAX_ARCHIVED_CANDIDATES:]
    current["revision"] += int(advance_local or deployed)
    current["last_round"] = round_index
    current["last_transition"] = {
        "local_advanced": advance_local,
        "deployed_advanced": deployed,
        "decision_hash": digest(record),
        "candidate_hash": candidate_hash,
    }
    return _seal(current)
