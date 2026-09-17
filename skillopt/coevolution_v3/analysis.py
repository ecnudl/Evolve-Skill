"""Frozen cross-project comparisons, keeping shared calls and unknowns explicit."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Mapping

from skillopt.coevolution.analysis import _arm, _bootstrap, _combine, _contrast, _index

POLICIES = ("coupled_evolving", "decoupled_fixed", "decoupled_evolving")
ARMS = ("noskill", *POLICIES, *("working_" + p for p in POLICIES))
CONTRASTS = (
    ("working_decoupled_evolving", "working_coupled_evolving", "primary_local_decoupling"),
    ("working_decoupled_evolving", "working_decoupled_fixed", "primary_validator_memory"),
    ("decoupled_evolving", "coupled_evolving", "secondary_approved_decoupling"),
    ("decoupled_evolving", "decoupled_fixed", "secondary_approved_memory"),
    ("decoupled_evolving", "noskill", "secondary_approved_vs_base"),
    ("working_decoupled_evolving", "noskill", "secondary_working_vs_base"),
)


def analyze_final(rows, manifest, *, streams=(0, 1), repeats=(0, 1, 2), draws=5000, seed=20260909):
    tasks, indexed = _index(rows, manifest, ARMS, streams, repeats)
    hashes = defaultdict(list)
    for row in rows:
        hashes[row["request_hash"]].append(row)
    for group in hashes.values():
        for key in ("id", "stream", "repeat", "skill_hash", "skill_active", "target_ok", "execution_ok",
                    "hard", "case_fraction", "response", "files"):
            if any(row.get(key) != group[0].get(key) for row in group):
                raise ValueError("Aliased shared request contains inconsistent observations")
    arms = {arm: _arm(tasks, indexed, arm, streams, repeats) for arm in ARMS}
    for arm in ARMS:
        values = defaultdict(list)
        for row in rows:
            if row["arm"] == arm and row["target_ok"] and row["execution_ok"]:
                score = row.get("case_fraction")
                if isinstance(score, (int, float)) and not isinstance(score, bool) and 0 <= score <= 1:
                    values[row["stream"], row["id"]].append(float(score))
        aggregate = _combine({key: sum(v) / len(v) for key, v in values.items()}, tasks, streams)
        arms[arm]["case_fraction_macro"] = aggregate["macro_cluster_mean"]
        arms[arm]["diagnostic_not_deployment"] = arm.startswith("working_")
    contrasts = {f"{left}_vs_{right}": _contrast(tasks, indexed, left, right, priority,
                    streams, repeats, draws, seed) for left, right, priority in CONTRASTS}
    return {
        "version": "coevolution-v3-frozen-analysis-v1", "exploratory": True,
        "n_rows": len(rows), "expected_rows": len(tasks) * len(ARMS) * len(streams) * len(repeats),
        "unique_api_requests": len(hashes), "shared_alias_rows": len(rows) - len(hashes),
        "n_tasks": len(tasks), "n_project_clusters": len({t["cluster_id"] for t in tasks.values()}),
        "arms": arms, "contrasts": contrasts,
        "all_rows_present": len(indexed) == len(tasks) * len(ARMS) * len(streams) * len(repeats),
        "same_input_shared_draws": True,
        "limitations": [
            "Two execution histories, not established independent seeds or representative project sampling.",
            "Repeated calls and two request modes are not additional independent projects.",
            "Working arms are explicitly sandbox-only diagnostic deployment interventions.",
            "Shared identical-content calls enforce exact zero differences for identical policies.",
            "Finite authored tests may miss real defects; not a public or cross-domain benchmark.",
            "Cluster bootstrap is exploratory; no superiority, equivalence, or statistical safety certificate.",
        ],
    }


def _assessment_available(row):
    return row.get("baseline_available") is True and (row.get("detected") is True or (
        row.get("search_status") == "completed" and row.get("valid_probes", 0) > 0))


def _shadow_counts(rows):
    observable = [r for r in rows if r.get("baseline_available") is True and r.get("oracle_hard") is not None]
    bad = [r for r in observable if not r["oracle_hard"]]
    good = [r for r in observable if r["oracle_hard"]]
    bad_usable = [r for r in bad if _assessment_available(r)]
    return {
        "rows": len(rows), "unique_artifact_hashes": len({r["artifact_hash"] for r in rows}),
        "observable": len(observable), "unavailable": len(rows) - len(observable),
        "oracle_failed_artifacts": len(bad), "detected_oracle_failures": sum(r["detected"] for r in bad),
        "missed_oracle_failures_with_usable_assessment": sum(not r["detected"] for r in bad_usable),
        "oracle_failed_assessment_unknown": sum(not _assessment_available(r) for r in bad),
        "assessment_unknown": sum(not _assessment_available(r) for r in observable),
        "end_to_end_nondetected_including_unknown": sum(not r["detected"] for r in bad),
        "oracle_passed_artifacts": len(good),
        "oracle_disagreements_require_audit": sum(r["detected"] for r in good),
        "additional_detections_after_public_pass": sum(r["detected"] and r["public_pass"] for r in observable),
        "search_unavailable": sum(r.get("search_status") == "claim_unavailable" for r in rows),
        "schema_valid": sum(r.get("schema_valid") is True for r in rows),
        "with_admissible_probe": sum(r.get("valid_probes", 0) > 0 for r in rows),
        "verified_mismatch_receipts": sum(r.get("verified_mismatches", 0) for r in rows),
        "receipt_count_not_independent_defects": True,
    }


def analyze_shadow(rows, *, draws=5000, seed=20260909):
    indexed = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("validator") not in ("fixed", "evolving"):
            raise ValueError("Invalid shadow row")
        key = row["stream"], row["artifact_id"], row["validator"]
        if key in indexed:
            raise ValueError("Duplicate shadow observation")
        indexed[key] = row
    groups = {}
    for kind in ("natural", "controlled"):
        group = [r for r in rows if r["artifact_group"] == kind]
        comparisons, cluster_values = [], defaultdict(list)
        end_to_end, unknown_pairs = [], 0
        identities = sorted({(r["stream"], r["artifact_id"]) for r in group})
        for stream, artifact in identities:
            fixed = indexed.get((stream, artifact, "fixed"))
            evolved = indexed.get((stream, artifact, "evolving"))
            if fixed is None or evolved is None:
                raise ValueError("Incomplete planned validator pair")
            for field in ("id", "artifact_hash", "oracle_hard", "public_pass", "artifact_group",
                          "kind", "cluster_id", "baseline_available"):
                if fixed[field] != evolved[field]:
                    raise ValueError("Shadow validators did not receive the same artifact and hard labels")
            if fixed["baseline_available"] and evolved["baseline_available"] and fixed["oracle_hard"] is False:
                delta = int(evolved["detected"]) - int(fixed["detected"])
                end_to_end.append(delta)
                if not (_assessment_available(fixed) and _assessment_available(evolved)):
                    unknown_pairs += 1
                    continue
                cluster_values[fixed["cluster_id"]].append(delta)
                comparisons.append({"stream": stream, "artifact_id": artifact, "cluster_id": fixed["cluster_id"],
                                    "detection_delta": delta})
        means = {cluster: sum(v) / len(v) for cluster, v in cluster_values.items()}
        groups[kind] = {
            "fixed": _shadow_counts([r for r in group if r["validator"] == "fixed"]),
            "evolving": _shadow_counts([r for r in group if r["validator"] == "evolving"]),
            "paired_bad_artifacts": len(comparisons),
            "bad_pairs_with_unknown_assessment": unknown_pairs,
            "end_to_end_bad_pairs_including_search_unknown": len(end_to_end),
            "end_to_end_detection_delta_including_search_unknown": sum(end_to_end) / len(end_to_end) if end_to_end else None,
            "more_detected": sum(r["detection_delta"] > 0 for r in comparisons),
            "fewer_detected": sum(r["detection_delta"] < 0 for r in comparisons),
            "cluster_macro_detection_delta": sum(means.values()) / len(means) if means else None,
            "cluster_bootstrap": _bootstrap(means, draws, seed) if means else None,
            "paired_details": comparisons,
        }
    requests = {r.get("claim", {}).get("request_hash") for r in rows}
    requests.discard(None)
    return {"version": "same-artifact-validator-audit-v1", "rows": len(rows), "groups": groups,
            "request_positions": dict(Counter(r["validator"] for r in rows)),
            "actual_unique_claim_requests": len(requests),
            "shadow_not_fed_back": True, "natural_and_controlled_not_pooled": True,
            "oracle_disagreement_is_not_automatic_false_positive": True,
            "finite_tests_not_formal_correctness": True,
            "one_probe_call_per_artifact_validator_stream": True}
