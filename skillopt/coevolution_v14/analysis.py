"""Frozen-history, family-clustered V14 evaluation with real block-specific draws.

No-Skill is independently requested in every history block. Exact task/text
aliases may be reused ONLY within a block; a reused response is never counted
as an independent evaluation block. This is a bundled-intervention pilot, not
a safety certification or an isolated estimate of solver sampling variance.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v12.analysis import (
    DOMAINS,
    EMPTY_SKILL_HASH,
    _cluster_values,
    _counts,
    _hash,
    _hierarchy,
    _holm,
    _inference,
    _mean,
    _plan,
    _rates,
    _score,
    _text,
)
from skillopt.validator_pilot.api import digest

VERSION = "v14-block-specific-draws-family-clustered-analysis-v1"
POLICIES = ("no_skill", "independent", "constrained")
PRIMARY_COMPARISON = "constrained_vs_independent"


def _validate(rows, expected_task_ids, histories, policies, minimum_clusters):
    if type(histories) is int and 1 <= histories <= 100:
        histories = tuple(range(histories))
    elif (type(histories) not in (list, tuple) or not histories or len(histories) > 100
          or any(type(h) is not int or h < 0 for h in histories)
          or len(histories) != len(set(histories))):
        raise ValueError("Declare a count or unique nonnegative history-block identifiers")
    histories = tuple(sorted(histories))
    if (type(policies) not in (list, tuple) or len(policies) != len(POLICIES)
            or not all(_text(p) for p in policies) or set(policies) != set(POLICIES)):
        raise ValueError("Exactly No-Skill, independent and constrained policies are required")
    policies = tuple(policies)
    if not isinstance(expected_task_ids, Mapping) or not 1 <= len(expected_task_ids) <= 5000:
        raise ValueError("Expected task IDs must map to frozen domain/structural-family metadata")
    expected, clusters = {}, defaultdict(set)
    for task, metadata in expected_task_ids.items():
        if (not _text(task) or not isinstance(metadata, Mapping) or metadata.get("domain") not in DOMAINS
                or not _text(metadata.get("cluster_id"))):
            raise ValueError("Every task needs a supported domain and structural family")
        expected[task] = {"domain": metadata["domain"], "cluster_id": metadata["cluster_id"]}
        clusters[metadata["domain"]].add(metadata["cluster_id"])
    if set(clusters) != set(DOMAINS) or any(len(values) < minimum_clusters for values in clusters.values()):
        raise ValueError("Every domain must meet the predeclared structural-family minimum")
    if type(rows) not in (list, tuple) or not rows or len(rows) > 1000000:
        raise ValueError("A bounded complete materialized evaluation grid is required")
    indexed, requests, trajectories, task_skills, policy_skills = {}, {}, {}, {}, {}
    for incoming in rows:
        if not isinstance(incoming, Mapping):
            raise ValueError("Each final observation must be an object")
        row = dict(incoming)
        task, history, policy = row.get("task_id"), row.get("history"), row.get("policy")
        if (not _text(task) or task not in expected or type(history) is not int
                or history not in histories or policy not in policies
                or {key: row.get(key) for key in ("domain", "cluster_id")} != expected[task]):
            raise ValueError("Task/domain/family/history/policy differs from preregistration")
        if not _hash(row.get("skill_hash")):
            raise ValueError("Exact frozen Skill text hash is required")
        sequence = row.get("request_hashes")
        if (type(sequence) is not list or len(sequence) != 2
                or not all(_hash(h) for h in sequence) or sequence[0] == sequence[1]):
            raise ValueError("Exactly two distinct ordered generation/revision request hashes are required")
        row["score"] = _score(row.get("score"))
        # History is part of the actual sampling identity, even for empty text.
        identity = task, row["domain"], row["cluster_id"], history, row["skill_hash"]
        sequence = tuple(sequence)
        payload = identity, row["score"]
        if trajectories.setdefault(sequence, payload) != payload:
            raise ValueError("Aliased trajectory crosses history blocks or disagrees on task/Skill/score")
        if task_skills.setdefault((task, history, row["skill_hash"]), sequence) != sequence:
            raise ValueError("Same task/text within one history must reuse its exact ordered trajectory")
        for step, request in enumerate(sequence):
            if requests.setdefault(request, (identity, step)) != (identity, step):
                raise ValueError("API request reuse across history blocks, tasks, Skills or stages is forbidden")
        if policy_skills.setdefault((policy, history), row["skill_hash"]) != row["skill_hash"]:
            raise ValueError("One frozen policy/history must use the same Skill across tasks and domains")
        if policy == "no_skill" and row["skill_hash"] != EMPTY_SKILL_HASH:
            raise ValueError("No-Skill must use the actual empty-text hash")
        key = task, history, policy
        if key in indexed:
            raise ValueError("Duplicate task/history/policy observation")
        indexed[key] = row
    if set(indexed) != {(task, h, p) for task in expected for h in histories for p in policies}:
        raise ValueError("Incomplete final grid; all missing attempts must remain explicit unknown rows")
    return indexed, expected, histories, policies, {d: sorted(clusters[d]) for d in DOMAINS}, requests, trajectories


def summarize(rows, expected_task_ids, histories=3, policies=POLICIES, *, minimum_clusters=8,
              bootstrap_samples=5000, seed=20260916):
    """Return sealed descriptive and two-endpoint primary paired inference.

    Average observed history blocks within each task, tasks within families,
    families within domains, then domains equally. Bootstrap only families,
    stratified by domain. No-Skill's distinct calls allow observed block
    variation, but three blocks do not isolate Skill versus solver variance.
    """
    if type(bootstrap_samples) is not int or not 100 <= bootstrap_samples <= 100000:
        raise ValueError("Use 100..100000 deterministic bootstrap replicates")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Use a bounded nonnegative analysis-only seed")
    if type(minimum_clusters) is not int or not 1 <= minimum_clusters <= 100:
        raise ValueError("Use a positive bounded family minimum; below eight is engineering smoke only")
    indexed, expected, histories, policies, clusters, requests, trajectories = _validate(
        rows, expected_task_ids, histories, policies, minimum_clusters)
    smoke_only = minimum_clusters < 8
    plan = _plan(clusters, bootstrap_samples, seed)
    policy_summary = {}
    for policy in policies:
        values = _cluster_values(indexed, expected, histories, policy)
        hierarchy = _hierarchy(values)
        selected = [row for row in indexed.values() if row["policy"] == policy]
        policy_summary[policy] = {
            **_rates(selected), "macro_all_attempt_success": hierarchy["macro"],
            "worst_domain_all_attempt_success": min(hierarchy["by_domain"].values()),
            "by_domain": {d: {**_rates([r for r in selected if r["domain"] == d]),
                "cluster_equal_all_attempt_success": hierarchy["by_domain"][d],
                "structural_clusters": len(clusters[d]), "cluster_success": values[d]} for d in DOMAINS},
            "by_history": {str(h): {**_rates([r for r in selected if r["history"] == h]),
                **_hierarchy(_cluster_values(indexed, expected, (h,), policy))} for h in histories},
            "nonempty_does_not_prove_new_learning_or_skill_adherence": True}
    comparisons = {}
    for candidate, reference in (("constrained", "independent"), ("independent", "no_skill"), ("constrained", "no_skill")):
        key = candidate + "_vs_" + reference
        values = _cluster_values(indexed, expected, histories, candidate, reference=reference)
        pairs = [(indexed[t, h, candidate], indexed[t, h, reference]) for t in expected for h in histories]
        per_domain = {d: {**_inference(values, clusters, plan, domains=(d,), seed=seed),
            "counts": _counts([(a, b) for a, b in pairs if a["domain"] == d]),
            "primary_endpoint": key == PRIMARY_COMPARISON and d == "spreadsheet"} for d in DOMAINS}
        worst = min(per_domain[d]["mean_delta"] for d in DOMAINS)
        comparisons[key] = {
            "candidate": candidate, "reference": reference, "counts": _counts(pairs),
            "macro": _inference(values, clusters, plan, seed=seed), "by_domain": per_domain,
            "by_history": {str(h): {
                **_hierarchy(_cluster_values(indexed, expected, (h,), candidate, reference=reference)),
                "counts": _counts([(a, b) for a, b in pairs if a["history"] == h])} for h in histories},
            "worst_domain_delta": worst, "maximum_domain_drop": max(0.0, -worst),
            "negative_domain_fraction": _mean(per_domain[d]["mean_delta"] < 0 for d in DOMAINS),
            "exploratory_comparison": key != PRIMARY_COMPARISON,
            "all_attempt_losses_are_not_all_semantic": True}
    base_domains = policy_summary["no_skill"]["by_domain"]
    for policy, summary in policy_summary.items():
        deltas = {d: summary["by_domain"][d]["cluster_equal_all_attempt_success"]
                     - base_domains[d]["cluster_equal_all_attempt_success"] for d in DOMAINS}
        summary.update(domain_deltas_vs_no_skill=deltas,
                       worst_domain_delta_vs_no_skill=min(deltas.values()),
                       maximum_domain_drop_vs_no_skill=max(0.0, -min(deltas.values())))
    main = comparisons[PRIMARY_COMPARISON]
    primary = {"macro": main["macro"]["p_two_sided"],
               "spreadsheet": main["by_domain"]["spreadsheet"]["p_two_sided"]}
    adjusted = _holm(primary)
    base = [row for row in indexed.values() if row["policy"] == "no_skill"]
    return seal({"version": VERSION, "histories": list(histories), "policies": list(policies),
        "expected_task_metadata_hash": digest(expected), "task_instances": len(expected),
        "structural_clusters_by_domain": {d: len(clusters[d]) for d in DOMAINS},
        "minimum_clusters": minimum_clusters, "engineering_smoke_only": smoke_only,
        "logical_rows": len(rows), "unique_trajectory_receipts": len(trajectories),
        "unique_request_hashes": len(requests), "aliased_rows_beyond_first_trajectory": len(rows) - len(trajectories),
        "no_skill_sampling": {"positions": len(base),
            "unique_trajectory_receipts": len({tuple(r["request_hashes"]) for r in base}),
            "unique_request_hashes": len({v for r in base for v in r["request_hashes"]}),
            "trajectories_by_history": {str(h): sum(r["history"] == h for r in base) for h in histories},
            "distinct_actual_requests_in_every_history_block": True,
            "distinct_requests_do_not_prove_provider_random_seed_independence": True},
        "policy_summary": policy_summary, "comparisons": comparisons,
        "primary_endpoints": {name: {"comparison": PRIMARY_COMPARISON,
            "p_two_sided": primary[name], "holm_adjusted_p": adjusted[name], "family_size": 2,
            "alpha": 0.05, "holm_reject_null": adjusted[name] <= 0.05 and not smoke_only,
            "engineering_smoke_not_effect_evidence": smoke_only} for name in primary},
        "primary_bundle_comparison_not_component_ablation": True,
        "coding_rule_reasoning_and_vs_base_exploratory": True,
        "unit": "history mean within task, task mean within structural family, equal families within domain, equal domains",
        "bootstrap_stratified_by_domain": True, "conditional_on_frozen_learning_histories": True,
        "histories_and_variants_not_independent_family_multipliers": True,
        "within_history_aliases_counted_once_for_actual_request_cost": True,
        "cross_history_request_aliases_forbidden": True,
        "history_variation_mixes_skill_text_and_solver_sampling": True,
        "no_provider_random_seed_reproducibility_claim": True,
        "structural_labels_independence_requires_external_task_design": True,
        "unseen_domain_exposure_not_verified_by_outcome_analysis": True,
        "eight_families_low_power_not_a_precision_guarantee": True,
        "zero_width_bootstrap_interval_not_equivalence_or_safety": True,
        "sign_flip_exact_up_to_16_nonzero_families_else_seeded_monte_carlo_plus_one": True,
        "safety_or_noninferiority_certified": False, "public_benchmark_claim": False,
        "research_contribution_identified_by_this_comparison": False})
