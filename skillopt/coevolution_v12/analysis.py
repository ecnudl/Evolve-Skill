"""Preregistered, domain-balanced analysis of frozen Skill-content updates.

Raw contrastive versus raw independent is the primary comparison. Selected
deployment variants cannot replace it after scores are observed. Uncertainty
conditions on the frozen learning histories and respects structural families.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Mapping

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest

VERSION = "v12-domain-balanced-content-analysis-v1"
DOMAINS = ("coding", "spreadsheet", "rule_reasoning")
POLICIES = ("no_skill", "independent", "contrastive", "selected_independent", "selected_contrastive")
EMPTY_SKILL_HASH = hashlib.sha256(b"").hexdigest()
_HASH = re.compile(r"[a-f0-9]{64}\Z")


def _text(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 500


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _score(value):
    if not isinstance(value, Mapping):
        raise ValueError("Every trajectory needs the structured native final score")
    required = {"all_attempt_success", "oracle_available", "delivery_valid", "semantic_success"}
    if not required <= set(value):
        raise ValueError("Final score omits delivery/oracle/semantic separation")
    success, semantic = value["all_attempt_success"], value["semantic_success"]
    oracle, delivery = value["oracle_available"], value["delivery_valid"]
    if (type(success) is not int or success not in (0, 1)
            or type(oracle) is not bool or type(delivery) is not bool
            or semantic is not None and (type(semantic) is not int or semantic not in (0, 1))):
        raise ValueError("Score requires binary success, explicit availability, and optional binary semantics")
    if oracle:
        if not delivery or semantic is None or success != semantic:
            raise ValueError("Available native oracle must have delivered, evaluated semantic outcome")
    elif semantic is not None or success != 0:
        raise ValueError("Oracle unknown cannot masquerade as a scored semantic result")
    if not delivery and oracle:
        raise ValueError("Undelivered artifacts cannot have available oracle evaluation")
    if "category" in value and not _text(value["category"]):
        raise ValueError("Optional outcome category must be a bounded string")
    # Validate strict JSON data, not arbitrary candidate-defined object hooks.
    digest(dict(value))
    return dict(value)


def _validate(rows, expected_task_ids, histories, policies, minimum_clusters):
    if type(histories) is int and 1 <= histories <= 100:
        histories = tuple(range(histories))
    elif (type(histories) not in (list, tuple) or not histories
          or any(type(h) is not int or h < 0 for h in histories)
          or len(histories) != len(set(histories))):
        raise ValueError("Histories must be a count or unique predeclared nonnegative identifiers")
    histories = tuple(sorted(histories))
    if (type(policies) not in (list, tuple) or len(policies) != len(POLICIES)
            or not all(_text(p) for p in policies) or set(policies) != set(POLICIES)):
        raise ValueError("The five fixed raw/control/selected policies must all be declared")
    policies = tuple(policies)
    if not isinstance(expected_task_ids, Mapping) or not 1 <= len(expected_task_ids) <= 5000:
        raise ValueError("Expected task IDs must map to preregistered domain and structural cluster")
    expected, clusters = {}, defaultdict(set)
    for task, metadata in expected_task_ids.items():
        if (not _text(task) or not isinstance(metadata, Mapping) or metadata.get("domain") not in DOMAINS
                or not _text(metadata.get("cluster_id"))):
            raise ValueError("Every expected task needs a supported domain and structural cluster")
        expected[task] = {"domain": metadata["domain"], "cluster_id": metadata["cluster_id"]}
        clusters[metadata["domain"]].add(metadata["cluster_id"])
    if set(clusters) != set(DOMAINS) or any(len(values) < minimum_clusters for values in clusters.values()):
        raise ValueError("Each domain must meet its predeclared minimum structural family count")
    if type(rows) not in (list, tuple) or not rows or len(rows) > 1000000:
        raise ValueError("A bounded, nonempty, materialized final grid is required")
    indexed, requests, trajectories, task_skills, policy_skills = {}, {}, {}, {}, {}
    for incoming in rows:
        if not isinstance(incoming, Mapping):
            raise ValueError("Every final observation must be an object")
        row = dict(incoming)
        task, history, policy = row.get("task_id"), row.get("history"), row.get("policy")
        if (not _text(task) or task not in expected or type(history) is not int
                or history not in histories or policy not in policies
                or {key: row.get(key) for key in ("domain", "cluster_id")} != expected[task]):
            raise ValueError("Task/domain/cluster/history/policy differs from preregistration")
        if not _hash(row.get("skill_hash")):
            raise ValueError("Exact frozen Skill text hash is required")
        sequence = row.get("request_hashes")
        if (type(sequence) is not list or len(sequence) != 2
                or not all(_hash(h) for h in sequence) or sequence[0] == sequence[1]):
            raise ValueError("Record exactly two distinct, ordered generation/revision request hashes")
        row["score"] = _score(row.get("score"))
        identity = (task, row["domain"], row["cluster_id"], row["skill_hash"])
        sequence = tuple(sequence)
        payload = identity, row["score"]
        if trajectories.setdefault(sequence, payload) != payload:
            raise ValueError("Aliased trajectories disagree on task, Skill, or exact actual score")
        if task_skills.setdefault((task, row["skill_hash"]), sequence) != sequence:
            raise ValueError("Identical task/Skill must reuse the exact ordered trajectory")
        for step, request in enumerate(sequence):
            if requests.setdefault(request, (identity, step)) != (identity, step):
                raise ValueError("An API request cannot alias another task, Skill, or trajectory stage")
        if policy_skills.setdefault((policy, history), row["skill_hash"]) != row["skill_hash"]:
            raise ValueError("A frozen policy/history cannot change Skill across tasks or domains")
        if policy == "no_skill" and row["skill_hash"] != EMPTY_SKILL_HASH:
            raise ValueError("No-Skill must use the actual empty-text hash")
        key = task, history, policy
        if key in indexed:
            raise ValueError("Duplicate task/history/policy observation")
        indexed[key] = row
    if set(indexed) != {(task, h, p) for task in expected for h in histories for p in policies}:
        raise ValueError("Incomplete final grid; missing attempts must be explicit unknown rows")
    return indexed, expected, histories, policies, {d: sorted(clusters[d]) for d in DOMAINS}, requests, trajectories


def _cluster_values(indexed, expected, histories, policy, *, reference=None, metric="all_attempt_success"):
    grouped = defaultdict(lambda: defaultdict(list))
    for task, metadata in expected.items():
        for history in histories:
            value = indexed[task, history, policy]["score"][metric]
            if reference is not None:
                value -= indexed[task, history, reference]["score"][metric]
            grouped[metadata["domain"], metadata["cluster_id"]][task].append(value)
    return {domain: {cluster: _mean(_mean(v) for v in grouped[domain, cluster].values())
                     for d, cluster in grouped if d == domain} for domain in DOMAINS}


def _hierarchy(values):
    domains = {domain: _mean(clusters.values()) for domain, clusters in values.items()}
    return {"macro": _mean(domains.values()), "by_domain": domains}


def _percentile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _sign_flip(weighted, *, seed):
    nonzero = [value for value in weighted if value != 0]
    observed = sum(weighted)
    if len(nonzero) <= 16:
        count = 0
        total = 2 ** len(nonzero)
        for signs in itertools.product((-1, 1), repeat=len(nonzero)):
            statistic = sum(sign * value for sign, value in zip(signs, nonzero))
            count += abs(statistic) >= abs(observed) - 1e-12
        probability, exact = count / total, True
    else:
        rng, count, total = random.Random(seed), 0, 20000
        for _ in range(total):
            statistic = sum(rng.choice((-1, 1)) * value for value in nonzero)
            count += abs(statistic) >= abs(observed) - 1e-12
        probability, exact = (count + 1) / (total + 1), False
    return {"p_two_sided": probability, "exact": exact, "assignments": total,
            "nonzero_cluster_differences": len(nonzero),
            "method": "weighted_cluster_sign_flip" if exact else "weighted_cluster_sign_flip_monte_carlo_plus_one",
            "seed": None if exact else seed,
            "assumption": "independent_structural_families_with_exchangeable_difference_signs",
            "causal_randomization_claim": False}


def _plan(clusters, samples, seed):
    rng = random.Random(seed)
    return [{domain: [rng.randrange(len(clusters[domain])) for _ in clusters[domain]]
             for domain in DOMAINS} for _ in range(samples)]


def _inference(values, clusters, plan, *, domains=DOMAINS, seed=20260915):
    ordered = {d: [values[d][c] for c in clusters[d]] for d in domains}
    observed = _mean(_mean(v) for v in ordered.values())
    draws = [_mean(_mean(ordered[d][index] for index in draw[d]) for d in domains) for draw in plan]
    weighted = [value / (len(domains) * len(ordered[d])) for d in domains for value in ordered[d]]
    sign_flip = _sign_flip(weighted, seed=seed)
    return {"mean_delta": observed, "ci95": {"low": _percentile(draws, 0.025), "high": _percentile(draws, 0.975)},
            "p_two_sided": sign_flip["p_two_sided"], "sign_flip": sign_flip,
            "bootstrap_samples": len(plan), "bootstrap_seed": seed,
            "bootstrap_method": "paired_structural_cluster_resampling_within_each_domain_then_equal_domain_mean",
            "clusters": sum(len(ordered[d]) for d in domains), "domains": list(domains),
            "few_clusters_descriptive_only": any(len(ordered[d]) < 20 for d in domains),
            "conditional_on_frozen_histories": True, "safety_or_noninferiority_certified": False}


def _rates(rows):
    scores = [row["score"] for row in rows]
    return {"positions": len(rows), "task_instances": len({row["task_id"] for row in rows}),
            "oracle_available": sum(s["oracle_available"] for s in scores),
            "unknown": sum(not s["oracle_available"] for s in scores),
            "delivery_valid": sum(s["delivery_valid"] for s in scores),
            "delivery_invalid": sum(not s["delivery_valid"] for s in scores),
            "delivery_valid_oracle_unknown": sum(s["delivery_valid"] and not s["oracle_available"] for s in scores),
            "all_attempt_position_success_diagnostic": _mean(s["all_attempt_success"] for s in scores),
            "available_semantic_success_diagnostic": _mean(s["semantic_success"] for s in scores if s["oracle_available"]),
            "nonempty_skill_positions": sum(row["skill_hash"] != EMPTY_SKILL_HASH for row in rows),
            "nonempty_skill_coverage": _mean(row["skill_hash"] != EMPTY_SKILL_HASH for row in rows),
            "unique_trajectory_receipts": len({tuple(row["request_hashes"]) for row in rows}),
            "outcome_categories": dict(sorted(Counter(s["category"] for s in scores if "category" in s).items()))}


def _counts(pairs):
    counts = Counter({key: 0 for key in (
        "wins", "losses", "ties", "paired_unknown", "confirmed_semantic_losses", "delivery_losses",
        "delivered_oracle_unknown_losses", "confirmed_semantic_gains", "reference_delivery_failure_gains",
        "reference_oracle_unknown_gains", "reference_success_positions")})
    for candidate, reference in pairs:
        a, b = candidate["score"], reference["score"]
        delta = a["all_attempt_success"] - b["all_attempt_success"]
        counts["wins" if delta > 0 else "losses" if delta < 0 else "ties"] += 1
        counts["paired_unknown"] += not a["oracle_available"] or not b["oracle_available"]
        counts["reference_success_positions"] += b["all_attempt_success"] == 1
        if delta < 0:
            counts["confirmed_semantic_losses"] += a["semantic_success"] == 0
            counts["delivery_losses"] += not a["delivery_valid"]
            counts["delivered_oracle_unknown_losses"] += a["delivery_valid"] and not a["oracle_available"]
        elif delta > 0:
            counts["confirmed_semantic_gains"] += b["semantic_success"] == 0
            counts["reference_delivery_failure_gains"] += not b["delivery_valid"]
            counts["reference_oracle_unknown_gains"] += b["delivery_valid"] and not b["oracle_available"]
    result = dict(counts)
    result.update(loss_position_rate=counts["losses"] / len(pairs) if pairs else None,
                  loss_given_reference_success=(counts["losses"] / counts["reference_success_positions"]
                                                if counts["reference_success_positions"] else None),
                  counts_are_correlated_positions_not_independent_trials=True,
                  semantic_score_losses_are_oracle_evaluated_not_pure_reasoning_attribution=True)
    return result


def _holm(values):
    result, previous = {}, 0.0
    for index, (key, value) in enumerate(sorted(values.items(), key=lambda item: (item[1], item[0]))):
        previous = max(previous, min(1.0, (len(values) - index) * value))
        result[key] = previous
    return result


def summarize(rows, expected_task_ids, histories=3, policies=POLICIES, *, bootstrap_samples=5000, seed=20260915,
              minimum_clusters=4):
    """Validate the full frozen grid and return sealed descriptive/paired results."""
    if type(bootstrap_samples) is not int or not 100 <= bootstrap_samples <= 100000:
        raise ValueError("Use 100..100000 deterministic bootstrap replicates")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Use a bounded nonnegative analysis-only seed")
    if type(minimum_clusters) is not int or not 1 <= minimum_clusters <= 100:
        raise ValueError("Use a positive bounded structural-family minimum; below four is engineering smoke only")
    indexed, expected, histories, policies, clusters, requests, trajectories = _validate(
        rows, expected_task_ids, histories, policies, minimum_clusters)
    smoke_only = minimum_clusters < 4
    plan = _plan(clusters, bootstrap_samples, seed)
    policy_summary = {}
    for policy in policies:
        values = _cluster_values(indexed, expected, histories, policy)
        hierarchy = _hierarchy(values)
        selected = [row for row in indexed.values() if row["policy"] == policy]
        policy_summary[policy] = {
            **_rates(selected), "macro_all_attempt_success": hierarchy["macro"],
            "by_domain": {d: {**_rates([r for r in selected if r["domain"] == d]),
                "cluster_equal_all_attempt_success": hierarchy["by_domain"][d],
                "structural_clusters": len(clusters[d]), "cluster_success": values[d]} for d in DOMAINS},
            "by_history": {str(h): {**_rates([r for r in selected if r["history"] == h]),
                **_hierarchy(_cluster_values(indexed, expected, (h,), policy))} for h in histories},
            "nonempty_does_not_prove_new_learning": True,
            "selected_policy_diagnostic_only": policy.startswith("selected_")}
    comparisons = {}
    pairs_to_compare = [("contrastive", "independent")]
    pairs_to_compare += [(p, "no_skill") for p in policies if p != "no_skill"]
    pairs_to_compare += [("selected_contrastive", "selected_independent"),
                        ("selected_independent", "independent"), ("selected_contrastive", "contrastive")]
    for candidate, reference in pairs_to_compare:
        key = candidate + "_vs_" + reference
        values = _cluster_values(indexed, expected, histories, candidate, reference=reference)
        pairs = [(indexed[t, h, candidate], indexed[t, h, reference]) for t in expected for h in histories]
        per_domain = {d: {**_inference(values, clusters, plan, domains=(d,), seed=seed),
                         "counts": _counts([(a, b) for a, b in pairs if a["domain"] == d])} for d in DOMAINS}
        comparisons[key] = {
            "candidate": candidate, "reference": reference, "counts": _counts(pairs),
            "macro": _inference(values, clusters, plan, seed=seed), "by_domain": per_domain,
            "by_history": {str(h): {
                **_hierarchy(_cluster_values(indexed, expected, (h,), candidate, reference=reference)),
                "counts": _counts([(a, b) for a, b in pairs if a["history"] == h])} for h in histories},
            "worst_domain_delta": min(per_domain[d]["mean_delta"] for d in DOMAINS),
            "negative_domain_fraction": _mean(per_domain[d]["mean_delta"] < 0 for d in DOMAINS),
            "selected_policy_diagnostic_only": candidate.startswith("selected_") or reference.startswith("selected_"),
            "all_attempt_losses_are_not_all_semantic": True}
    main = comparisons["contrastive_vs_independent"]
    primary = {"macro": main["macro"]["p_two_sided"],
               "rule_reasoning": main["by_domain"]["rule_reasoning"]["p_two_sided"]}
    adjusted = _holm(primary)
    return seal({"version": VERSION, "histories": list(histories), "policies": list(policies),
        "expected_task_metadata_hash": digest(expected), "task_instances": len(expected),
        "structural_clusters_by_domain": {d: len(clusters[d]) for d in DOMAINS},
        "minimum_clusters": minimum_clusters, "engineering_smoke_only": smoke_only,
        "logical_rows": len(rows), "unique_trajectory_receipts": len(trajectories),
        "unique_request_hashes": len(requests), "aliased_rows_beyond_first_trajectory": len(rows) - len(trajectories),
        "policy_summary": policy_summary, "comparisons": comparisons,
        "primary_endpoints": {name: {"comparison": "contrastive_vs_independent",
            "p_two_sided": primary[name], "holm_adjusted_p": adjusted[name], "family_size": 2,
            "alpha": 0.05, "holm_reject_null": adjusted[name] <= 0.05 and not smoke_only,
            "engineering_smoke_not_effect_evidence": smoke_only} for name in primary},
        "primary_raw_comparison_not_replaceable_by_selected": True,
        "unit": "history mean within task, task mean within structural cluster, equal clusters within domain, equal domains",
        "bootstrap_stratified_by_domain": True, "histories_conditioned_not_independent_sample_multiplier": True,
        "no_provider_random_seed_reproducibility_claim": True,
        "structural_labels_independence_requires_external_task_design": True,
        "unseen_domain_exposure_not_verified_by_outcome_analysis": True,
        "nonempty_skill_text_and_new_learning_distinct": True,
        "safety_or_noninferiority_certified": False, "public_benchmark_claim": False,
        "research_contribution_identified_by_this_comparison": False})
