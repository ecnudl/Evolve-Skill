"""Cluster-level repeated-execution diagnostics for frozen validator portfolios.

Parameter variants and repeated probe draws are never treated as independent
projects. Bootstrap intervals are descriptive with few clusters; a favorable
standalone gate is not validator activation or a statistical safety proof.
"""

from __future__ import annotations

import itertools
import math
import random
import re
from collections import defaultdict
from copy import deepcopy
from typing import Mapping, Sequence

from skillopt.validator_pilot.api import digest

VERSION = "v6-cluster-repeated-validator-statistics-v1"
POLICIES = ("old_single", "new_single", "old_double", "portfolio")
METRICS = ("bad_detection", "good_false_rejection", "unknown", "unknown_good", "unknown_bad")


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 500


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _validate(rows, expected_artifacts, expected_blocks):
    if not isinstance(rows, (list, tuple)) or not rows or len(rows) > 100000:
        raise ValueError("A bounded nonempty frozen observation grid is required")
    if (expected_artifacts is None) != (expected_blocks is None):
        raise ValueError("Provide both preregistered artifacts and blocks, or neither")
    indexed, identities = {}, {}
    request_positions = {}
    for incoming in rows:
        if not isinstance(incoming, Mapping):
            raise ValueError("Validator observation must be an object")
        row = deepcopy(dict(incoming))
        if (not _text(row.get("artifact_id")) or not _text(row.get("cluster_id"))
                or row.get("truth") not in {"good", "bad"} or row.get("policy") not in POLICIES
                or row.get("outcome") not in {"detected", "not_detected", "unknown"}
                or type(row.get("block")) is not int or row["block"] < 0):
            raise ValueError("Invalid artifact/cluster/truth/policy/block/outcome identity")
        single = row["policy"] in {"old_single", "new_single"}
        if type(row.get("input_count")) is not int or not 0 <= row["input_count"] <= (4 if single else 8):
            raise ValueError("Probe input counts exceed the frozen per-policy quota")
        requests = row.get("probe_request_hashes")
        if (not isinstance(requests, list) or len(requests) != (1 if single else 2)
                or not all(_hash(request) for request in requests) or len(set(requests)) != len(requests)):
            raise ValueError("Policy must record its one/two distinct actual probe request hashes")
        identity = {"cluster_id": row["cluster_id"], "truth": row["truth"]}
        if identities.setdefault(row["artifact_id"], identity) != identity:
            raise ValueError("Artifact oracle truth or project cluster changes across rows")
        position = (row["artifact_id"], row["block"])
        for request in requests:
            if request_positions.setdefault(request, position) != position:
                raise ValueError("Cached probe aliases cannot masquerade as independent artifacts or blocks")
        key = (row["artifact_id"], row["block"], row["policy"])
        if key in indexed:
            raise ValueError("Duplicate artifact/block/policy observation")
        indexed[key] = row
    blocks = sorted({key[1] for key in indexed})
    if expected_artifacts is not None:
        if not isinstance(expected_artifacts, Mapping) or not expected_artifacts:
            raise ValueError("Preregistered artifact design must be a nonempty identity mapping")
        expected = {}
        for artifact_id, metadata in expected_artifacts.items():
            if (not _text(artifact_id) or not isinstance(metadata, Mapping)
                    or not _text(metadata.get("cluster_id")) or metadata.get("truth") not in {"good", "bad"}):
                raise ValueError("Invalid preregistered artifact identity")
            expected[artifact_id] = {"cluster_id": metadata["cluster_id"], "truth": metadata["truth"]}
        if expected != identities:
            raise ValueError("Observed artifact identities differ from the full preregistered design")
        if (not isinstance(expected_blocks, (list, tuple)) or not expected_blocks
                or any(type(block) is not int or block < 0 for block in expected_blocks)
                or len(expected_blocks) != len(set(expected_blocks))):
            raise ValueError("Preregistered blocks must be unique nonnegative integer positions")
        if sorted(expected_blocks) != blocks:
            raise ValueError("Observed blocks differ from the full preregistered design")
    expected_grid = {(artifact_id, block, policy) for artifact_id in identities for block in blocks for policy in POLICIES}
    if set(indexed) != expected_grid:
        raise ValueError("Incomplete paired grid: missing executions must be explicit unknown outcomes")
    for artifact_id in identities:
        for block in blocks:
            records = {policy: indexed[artifact_id, block, policy] for policy in POLICIES}
            old_a = records["old_single"]["probe_request_hashes"][0]
            new = records["new_single"]["probe_request_hashes"][0]
            double = set(records["old_double"]["probe_request_hashes"])
            portfolio = set(records["portfolio"]["probe_request_hashes"])
            if old_a == new or old_a not in double or new in double or portfolio != {old_a, new}:
                raise ValueError("The equal-cost arms must be old_a+old_b versus old_a+new")
            if not (records["old_single"]["input_count"] <= records["old_double"]["input_count"]
                    <= records["old_single"]["input_count"] + 4):
                raise ValueError("Old-double union input count contradicts its shared old-a search")
            if not (max(records["old_single"]["input_count"], records["new_single"]["input_count"])
                    <= records["portfolio"]["input_count"]
                    <= records["old_single"]["input_count"] + records["new_single"]["input_count"]):
                raise ValueError("Portfolio union input count contradicts constituent searches")
            # Execution on a superset of the same legal probes cannot erase an
            # actually detected error. Unknowns may resolve with a second draw.
            if records["old_single"]["outcome"] == "detected" and any(
                records[policy]["outcome"] != "detected" for policy in ("old_double", "portfolio")
            ):
                raise ValueError("Union policy lost a detection present in its exact shared old-a probes")
            if records["new_single"]["outcome"] == "detected" and records["portfolio"]["outcome"] != "detected":
                raise ValueError("Portfolio lost a detection present in its exact new probes")
    return indexed, identities, blocks, request_positions


def _mean(values):
    return sum(values) / len(values) if values else None


def _percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap(values, samples):
    if not values:
        return {"low": None, "high": None, "level": 0.95, "samples": len(samples)}
    draws = [sum(values[index] for index in sample) / len(sample) for sample in samples]
    return {"low": _percentile(draws, 0.025), "high": _percentile(draws, 0.975),
            "level": 0.95, "samples": len(samples), "method": "paired_cluster_percentile_bootstrap",
            "interpretation": "descriptive_conditional_on_observed_blocks_not_a_safety_guarantee"}


def _sign_flip(values):
    if not values:
        return {"p_two_sided": None, "exact": False, "reason": "no_paired_clusters"}
    if len(values) > 16:
        return {"p_two_sided": None, "exact": False, "reason": "more_than_16_clusters_exact_test_not_enumerated"}
    observed = _mean(values)
    statistics = [sum(sign * value for sign, value in zip(signs, values)) / len(values)
                  for signs in itertools.product((-1, 1), repeat=len(values))]
    return {"p_two_sided": sum(abs(value) >= abs(observed) - 1e-12 for value in statistics) / len(statistics),
            "p_one_sided_positive": sum(value >= observed - 1e-12 for value in statistics) / len(statistics),
            "exact": True, "assignments": len(statistics), "unit": "project_cluster",
            "null_assumption": "exchangeable_signs_of_independent_cluster_differences",
            "causal_randomization_claim": False}


def cluster_inference(deltas: Mapping[str, float], *, bootstrap_samples: int = 10000,
                      seed: int = 20260911) -> dict:
    """Inference over already averaged project-family differences.

    Caller must average repeated histories and parameter variants inside the
    true project family BEFORE calling. This function cannot discover whether
    a supplied family label falsely splits one underlying project.
    """
    if not isinstance(deltas, Mapping) or not deltas:
        raise ValueError("A nonempty mapping of independent project-family deltas is required")
    if type(bootstrap_samples) is not int or not 100 <= bootstrap_samples <= 100000:
        raise ValueError("Use 100..100000 deterministic cluster-bootstrap samples")
    if type(seed) is not int or seed < 0:
        raise ValueError("Bootstrap seed must be a nonnegative integer")
    if any(not _text(cluster) or type(value) not in {int, float} or not math.isfinite(value)
           for cluster, value in deltas.items()):
        raise ValueError("Cluster deltas require nonempty identities and finite numeric values")
    ordered = {cluster: deltas[cluster] for cluster in sorted(deltas)}
    values = list(ordered.values())
    rng = random.Random(seed)
    samples = [tuple(rng.randrange(len(values)) for _ in values) for _ in range(bootstrap_samples)]
    bootstrap, sign_flip = _bootstrap(values, samples), _sign_flip(values)
    return {"mean_delta": _mean(values), "ci95": {"low": bootstrap["low"], "high": bootstrap["high"]},
            "exact_sign_flip_p": sign_flip["p_two_sided"], "clusters": len(values),
            "cluster_deltas": ordered, "few_clusters_descriptive_only": len(values) < 20,
            "bootstrap": {**bootstrap, "seed": seed}, "sign_flip": sign_flip,
            "bootstrap_excludes_zero_but_exact_p_gt_05": (
                (bootstrap["low"] > 0 or bootstrap["high"] < 0)
                and sign_flip["p_two_sided"] is not None and sign_flip["p_two_sided"] > 0.05),
            "independence_unit": "project_family_not_variant_history_or_execution",
            "within_family_averaging_required": True, "causal_or_safety_claim": False}


def _rates(group):
    good = [row for row in group if row["truth"] == "good"]
    bad = [row for row in group if row["truth"] == "bad"]
    return {"bad_detection": _mean([int(row["outcome"] == "detected") for row in bad]),
            "good_false_rejection": _mean([int(row["outcome"] == "detected") for row in good]),
            "unknown": _mean([int(row["outcome"] == "unknown") for row in group]),
            "unknown_good": _mean([int(row["outcome"] == "unknown") for row in good]),
            "unknown_bad": _mean([int(row["outcome"] == "unknown") for row in bad]),
            "good_acceptance": _mean([int(row["outcome"] == "not_detected") for row in good]),
            "input_count": _mean([row["input_count"] for row in group])}


def summarize_validator(rows: Sequence[Mapping], *, expected_artifacts: Mapping | None = None,
                        expected_blocks: Sequence[int] | None = None, bootstrap_samples: int = 10000,
                        seed: int = 20260911) -> dict:
    """Summarize a frozen 4-policy x artifact x block grid without activation.

    Optional expected design is required for a favorable gate: rows alone
    cannot reveal an artifact/block missing from every policy. Probe requests
    are deliberately shared inside each position, never across positions.
    """
    if type(bootstrap_samples) is not int or not 100 <= bootstrap_samples <= 100000:
        raise ValueError("Use 100..100000 deterministic cluster-bootstrap samples")
    if type(seed) is not int or seed < 0:
        raise ValueError("Bootstrap seed must be a nonnegative integer")
    indexed, identities, blocks, requests = _validate(rows, expected_artifacts, expected_blocks)
    clusters = sorted({identity["cluster_id"] for identity in identities.values()})
    clustered = defaultdict(list)
    for row in indexed.values():
        clustered[row["policy"], row["cluster_id"]].append(row)
    cluster_rates = {policy: {cluster: _rates(clustered[policy, cluster]) for cluster in clusters} for policy in POLICIES}
    rng = random.Random(seed)
    samples = [tuple(rng.randrange(len(clusters)) for _ in clusters) for _ in range(bootstrap_samples)]
    policy_summary = {}
    for policy in POLICIES:
        stats = {}
        for metric in (*METRICS, "good_acceptance", "input_count"):
            values = [cluster_rates[policy][cluster][metric] for cluster in clusters]
            available = [value for value in values if value is not None]
            stats[metric] = {"cluster_mean": _mean(available), "clusters_available": len(available),
                             "clusters_total": len(clusters)}
        policy_summary[policy] = {"metrics": stats, "clusters": cluster_rates[policy],
                                  "logical_rows": sum(row["policy"] == policy for row in indexed.values()),
                                  "unique_probe_requests": len({request for row in indexed.values() if row["policy"] == policy
                                                                for request in row["probe_request_hashes"]})}
    comparisons = {}
    for name, baseline, candidate in (("new_single_vs_old_single", "old_single", "new_single"),
                                      ("portfolio_vs_old_double", "old_double", "portfolio"),
                                      ("old_double_vs_old_single", "old_single", "old_double")):
        metrics = {}
        for metric in METRICS:
            differences = {cluster: cluster_rates[candidate][cluster][metric] - cluster_rates[baseline][cluster][metric]
                           for cluster in clusters if cluster_rates[candidate][cluster][metric] is not None
                           and cluster_rates[baseline][cluster][metric] is not None}
            values = list(differences.values())
            if len(values) == len(clusters):
                bootstrap = _bootstrap(values, samples)
            else:
                local_rng = random.Random(seed)
                local_samples = [tuple(local_rng.randrange(len(values)) for _ in values) for _ in range(bootstrap_samples)]
                bootstrap = _bootstrap(values, local_samples)
            metrics[metric] = {"cluster_mean_delta": _mean(values), "cluster_deltas": differences,
                               "bootstrap_95": bootstrap, "sign_flip": _sign_flip(values)}
        comparisons[name] = {"baseline": baseline, "candidate": candidate, "metrics": metrics,
                             "equal_model_call_budget": name != "old_double_vs_old_single"}
    lost_draws, artifact_changes = [], []
    new_false_rejections, new_false_draws, unknown_increases = [], [], []
    for artifact_id, identity in sorted(identities.items()):
        if identity["truth"] == "bad":
            values = {}
            for policy in ("old_single", "new_single"):
                values[policy] = _mean([int(indexed[artifact_id, block, policy]["outcome"] == "detected") for block in blocks])
            lost = [block for block in blocks if indexed[artifact_id, block, "old_single"]["outcome"] == "detected"
                    and indexed[artifact_id, block, "new_single"]["outcome"] != "detected"]
            lost_draws.extend({"artifact_id": artifact_id, "cluster_id": identity["cluster_id"], "block": block} for block in lost)
            artifact_changes.append({"artifact_id": artifact_id, "cluster_id": identity["cluster_id"],
                                     "old_detection_rate": values["old_single"], "new_detection_rate": values["new_single"],
                                     "mean_delta": values["new_single"] - values["old_single"],
                                     "has_lost_draw": bool(lost),
                                     "lost_draw_but_mean_not_lower": bool(lost) and values["new_single"] >= values["old_single"]})
        else:
            old_detected = [block for block in blocks if indexed[artifact_id, block, "old_double"]["outcome"] == "detected"]
            new_detected = [block for block in blocks if indexed[artifact_id, block, "portfolio"]["outcome"] == "detected"]
            new_false_draws.extend({"artifact_id": artifact_id, "cluster_id": identity["cluster_id"], "block": block}
                                   for block in new_detected if block not in old_detected)
            if len(new_detected) > len(old_detected):
                new_false_rejections.append({"artifact_id": artifact_id, "cluster_id": identity["cluster_id"],
                                             "old_rate": len(old_detected) / len(blocks),
                                             "new_rate": len(new_detected) / len(blocks),
                                             "newly_affected_artifact": not old_detected})
    for cluster in clusters:
        for metric in ("unknown_good", "unknown_bad"):
            before, after = cluster_rates["old_double"][cluster][metric], cluster_rates["portfolio"][cluster][metric]
            if before is not None and after is not None and after > before:
                unknown_increases.append({"cluster_id": cluster, "metric": metric, "delta": after - before})
    reasons = []
    if expected_artifacts is None:
        reasons.append("no_preregistered_full_design")
    if len(clusters) < 6:
        reasons.append("fewer_than_six_project_clusters")
    if len(blocks) < 4:
        reasons.append("fewer_than_four_repeated_blocks")
    if any(any(cluster_rates["old_double"][cluster][metric] is None
               for metric in ("bad_detection", "good_false_rejection")) for cluster in clusters):
        reasons.append("each_cluster_requires_both_oracle_truths")
    primary = comparisons["portfolio_vs_old_double"]["metrics"]["bad_detection"]
    lower = primary["bootstrap_95"]["low"]
    if lower is None or lower <= 0:
        reasons.append("benefit_uncertain_cluster_interval_not_strictly_positive")
    if new_false_rejections:
        reasons.append("new_good_artifact_false_rejections")
    if unknown_increases:
        reasons.append("cluster_class_unknown_rate_increased")
    harmful = bool(new_false_rejections or unknown_increases)
    result = {
        "version": VERSION,
        "design": {"policies": list(POLICIES), "artifacts": len(identities), "clusters": len(clusters),
                   "blocks": blocks, "rows": len(indexed), "full_grid_verified": True,
                   "preregistered_design_checked": expected_artifacts is not None,
                   "independence_unit": "project_cluster_not_parameter_variant_or_draw", "few_clusters": len(clusters) < 20},
        "policy_summary": policy_summary, "comparisons": comparisons,
        "primary_gate": {"action": "Reject" if harmful else "Hold" if reasons else "Support",
                         "activate": False, "reasons": reasons, "primary_comparison": "portfolio_vs_old_double",
                         "bad_detection_lower_bound": lower, "new_false_rejections": new_false_rejections,
                         "new_false_rejection_draws_diagnostic": new_false_draws, "unknown_increases": unknown_increases,
                         "single_bad_detection_draw_loss_is_not_a_veto": True,
                         "bootstrap_positive_but_exact_p_gt_05": (
                             lower is not None and lower > 0
                             and primary["sign_flip"]["p_two_sided"] is not None
                             and primary["sign_flip"]["p_two_sided"] > 0.05),
                         "interpretation": "standalone_finite_evidence_screen_not_activation_or_safety_certificate"},
        "draw_vs_artifact": {"old_single_to_new_single_lost_draws": lost_draws,
                             "lost_draw_count": len(lost_draws), "artifact_rates": artifact_changes,
                             "lost_draw_but_mean_not_lower_count": sum(r["lost_draw_but_mean_not_lower"] for r in artifact_changes),
                             "artifact_mean_regression_count": sum(r["mean_delta"] < 0 for r in artifact_changes),
                             "causal_forgetting_established": False},
        "cost_audit": {"unique_probe_requests": len(requests), "expected_unique_requests": len(identities) * len(blocks) * 3,
                       "logical_policy_request_references": sum(len(row["probe_request_hashes"]) for row in indexed.values()),
                       "shared_old_a_is_intentional": True, "cross_artifact_or_block_aliases": 0,
                       "primary_each_uses_calls": 2, "single_each_uses_calls": 1,
                       "input_quota_per_search": 4, "tokens_and_http_cost_require_external_api_ledger": True},
        "bootstrap": {"seed": seed, "samples": bootstrap_samples, "resampling_unit": "whole_project_cluster",
                      "within_cluster_blocks_kept_together": True, "few_clusters_descriptive_only": len(clusters) < 20},
        "rows_hash": digest([indexed[key] for key in sorted(indexed)]),
    }
    return {**result, "summary_hash": digest(result)}
