"""Finite behavioral gates, including shared probes in LOCAL admission too."""

from copy import deepcopy

from skillopt.coevolution_v3.state import decide_local as previous_local
from skillopt.coevolution_v3.state import decide_scope as previous_scope


def basis(record):
    score = record["evaluation"]
    cases = score.get("case_results", [])
    return {
        "available": record.get("target_ok") is True and score.get("execution_ok") is True,
        "hard": score.get("hard"),
        "case_results": {c["id"]: c["passed"] for c in cases},
        "preserved": {c["id"]: c["passed"] for c in cases if c["dimension"] == "preserved_behavior"},
        "case_total": score.get("total_tests"),
        "case_passes": score.get("passed_tests"),
    }


def probe_losses(pairs, reference_arm):
    losses, unknown = [], []
    for pair in pairs:
        probes = pair.get("probe_results", {})
        candidate = probes.get("candidate", {})
        for arm in ("base", reference_arm):
            reference = probes.get(arm, {})
            for key in set(candidate) & set(reference):
                if reference[key] is True and candidate[key] is False:
                    losses.append({"id": pair["id"], "repeat": pair["repeat"], "reference": arm,
                                   "probe": key, "kind": "verified_shared_probe_regression"})
                elif reference[key] is None or candidate[key] is None:
                    unknown.append({"id": pair["id"], "probe": key})
        if pair.get("search_unknown"):
            unknown.append({"id": pair["id"], "reason": pair["search_unknown"]})
    return losses, unknown


def decide_local(candidate, source_pairs, replay_pairs=()):
    result = deepcopy(previous_local(candidate, source_pairs, replay_pairs))
    source_losses, source_unknown = probe_losses(source_pairs, "working")
    replay_losses, replay_unknown = probe_losses(replay_pairs, "working")
    result["evidence"]["shared_probe_audit"] = {
        "source_losses": source_losses, "replay_losses": replay_losses,
        "unknown": source_unknown + replay_unknown,
        "unknown_is_not_approval_and_does_not_erase_finite_foundation": True,
    }
    if source_losses or replay_losses:
        result.update(passed=False, action="Reject", reason="verified_local_probe_regression")
        result["reasons"] = ["verified_local_probe_regression", *result["reasons"]]
    return result


def decide_scope(candidate, local_decision, gate_pairs):
    result = previous_scope(candidate, local_decision, gate_pairs)
    result["scope_claim"] = "finite_observed_coding_project_scope_only"
    result["cross_domain_validated"] = False
    return result
