"""Paired diagnostics with missingness and structural clusters kept explicit."""

from collections import Counter, defaultdict

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v5.evaluation import summarize_final
from skillopt.coevolution_v6.statistics import cluster_inference

POLICIES = ("no_skill", "fixed_validator_candidate", "research_candidate_shadow",
            "gated_validator_candidate", "gated_validator_routed")


def _mean(values):
    return sum(values) / len(values) if values else None


def compare(rows, left, right):
    """left minus right; all-attempt and jointly available estimates differ."""
    indexed = {(r["task_id"], r["history"], r["policy"]): r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError("Duplicate final observation")
    clusters, available, attempts, shared = defaultdict(list), [], [], 0
    both_stages_success = []
    for (task, history, policy), row in indexed.items():
        if policy != left:
            continue
        other = indexed.get((task, history, right))
        if other is None or row["cluster_id"] != other["cluster_id"]:
            raise ValueError("Incomplete or inconsistent paired design")
        delta = (row["score"] or 0.0) - (other["score"] or 0.0)
        attempts.append(delta)
        clusters[row["cluster_id"]].append(delta)
        if row["request_hashes"] == other["request_hashes"]:
            if (row["score"], row["artifact_hash"]) != (other["score"], other["artifact_hash"]):
                raise ValueError("Shared trajectory received inconsistent scoring")
            shared += 1
        if row["score"] is not None and other["score"] is not None:
            available.append(row["score"] - other["score"])
            if row["all_solver_stages_api_ok"] and other["all_solver_stages_api_ok"]:
                both_stages_success.append(row["score"] - other["score"])

    def tally(values):
        return {"n": len(values), "wins": sum(v > 0 for v in values),
                "losses": sum(v < 0 for v in values), "ties": sum(v == 0 for v in values),
                "mean_delta": _mean(values)}

    return {"left": left, "right": right, "all_attempt": tally(attempts),
            "both_available": tally(available), "missing_pairs": len(attempts) - len(available),
            "all_stages_api_delivery_success_diagnostic": tally(both_stages_success),
            "shared_trajectory_pairs": shared,
            "all_attempt_cluster_inference": cluster_inference({c: _mean(v) for c, v in clusters.items()}),
            "api_delivery_filtered_is_selection_sensitive_not_causal": True}


def summarize(rows, *, expected):
    positions = {(r["task_id"], r["history"], r["policy"]) for r in rows}
    if len(rows) != len(positions) or positions != set(expected):
        raise ValueError("Final grid differs from the complete frozen plan")
    if {r["policy"] for r in rows} != set(POLICIES):
        raise ValueError("Unknown or missing final policy")
    native = summarize_final(rows)
    outcomes = {p: dict(Counter(r["outcome_category"] for r in rows if r["policy"] == p)) for p in POLICIES}
    comparisons = {left + "_vs_" + right: compare(rows, left, right) for left, right in (
        ("research_candidate_shadow", "fixed_validator_candidate"),
        ("gated_validator_candidate", "fixed_validator_candidate"),
        ("gated_validator_routed", "no_skill"),
        ("fixed_validator_candidate", "no_skill"),
        ("research_candidate_shadow", "no_skill"),
        ("gated_validator_routed", "gated_validator_candidate"))}
    return seal({"native": native, "outcome_categories": outcomes, "comparisons": comparisons,
                 "full_grid_verified": True, "synthetic_native_diagnostic": True,
                 "unapproved_candidates_are_counterfactuals": True,
                 "public_benchmark_efficacy_established": False, "causal_or_safety_claim": False})
