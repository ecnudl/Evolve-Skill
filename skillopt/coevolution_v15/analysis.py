"""All-attempt V15 final analysis, conditional on the frozen learning histories.

This module neither runs artifacts nor calls a validator. Bootstrap units are
authored structural families within domains; all observed tasks and history
blocks of a sampled family travel together. Family labels are not themselves
proof of independence. Confidence intervals are exploratory, not safety gates.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections import defaultdict
from collections.abc import Mapping
from statistics import NormalDist

from skillopt.coevolution_v5.core import seal

VERSION = "v15-native-final-family-clustered-analysis-v1"
POLICIES = ("no_skill", "fixed", "adaptive", "adaptive_research")
EMPTY_SKILL_HASH = hashlib.sha256(b"").hexdigest()
SEED = 2026091505


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 500


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _interval(values):
    return [_quantile(values, 0.025), _quantile(values, 0.975)]


def _validate(rows, policies, expected_tasks, expected_histories):
    if (not isinstance(policies, (list, tuple)) or not policies
            or len(policies) > 20 or any(not _text(p) for p in policies)
            or len(set(policies)) != len(policies) or "no_skill" not in policies):
        raise ValueError("Unique policies including no_skill are required")
    if not isinstance(rows, (list, tuple)) or not rows or len(rows) > 200000:
        raise ValueError("A bounded nonempty materialized final grid is required")
    indexed, tasks, histories, clusters = {}, {}, set(), defaultdict(set)
    rounds = set()
    for item in rows:
        if not isinstance(item, Mapping):
            raise ValueError("Each observation must be an object")
        row = dict(item)
        task, history, policy = row.get("task_id"), row.get("history"), row.get("policy")
        domain, cluster = row.get("domain"), row.get("cluster_id")
        if (any(not _text(v) for v in (task, domain, cluster))
                or type(history) is not int or not 0 <= history < 100
                or policy not in policies):
            raise ValueError("Invalid task/domain/family/history/policy identity")
        for field in ("passed", "oracle_available", "artifact_valid", "skill_nonempty"):
            if type(row.get(field)) is not bool:
                raise ValueError(f"{field} must be an explicit bool, including unknown attempts")
        if row["oracle_available"] and not row["artifact_valid"]:
            raise ValueError("An unavailable artifact cannot have a semantic oracle result")
        if row["passed"] and not (row["oracle_available"] and row["artifact_valid"]):
            raise ValueError("A pass requires a valid artifact and an available oracle")
        skill_hash = row.get("skill_hash")
        if not isinstance(skill_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", skill_hash):
            raise ValueError("An exact lowercase SHA256 of the effective Skill is required")
        if row["skill_nonempty"] != (skill_hash != EMPTY_SKILL_HASH):
            raise ValueError("Skill nonempty flag contradicts its text hash")
        if policy == "no_skill" and row["skill_nonempty"]:
            raise ValueError("No-Skill must have empty effective Skill text")
        if "phase" in row:
            if row["phase"] != "final":
                raise ValueError("Final inference cannot mix development or calibration rows")
        if "round" in row:
            if type(row["round"]) is not int or row["round"] < 0:
                raise ValueError("Round must be a nonnegative integer")
            rounds.add(row["round"])
        key = task, history, policy
        if key in indexed:
            raise ValueError("Duplicate task/history/policy observation")
        metadata = {"domain": domain, "cluster_id": cluster}
        if tasks.setdefault(task, metadata) != metadata:
            raise ValueError("Task domain or family changed across conditions")
        indexed[key] = row
        histories.add(history)
        clusters[domain].add(cluster)
    if len(rounds) > 1:
        raise ValueError("Do not pool final checkpoints as independent observations")
    if expected_tasks is not None:
        if not isinstance(expected_tasks, Mapping) or not expected_tasks:
            raise ValueError("Expected tasks must map IDs to frozen domain/family metadata")
        expected = {}
        for task, metadata in expected_tasks.items():
            if (not _text(task) or not isinstance(metadata, Mapping)
                    or any(not _text(metadata.get(k)) for k in ("domain", "cluster_id"))):
                raise ValueError("Malformed frozen task universe")
            expected[task] = {k: metadata[k] for k in ("domain", "cluster_id")}
        if tasks != expected:
            raise ValueError("Observed task universe differs from the frozen panel")
    if expected_histories is not None:
        if (not isinstance(expected_histories, (list, tuple)) or not expected_histories
                or any(type(h) is not int or not 0 <= h < 100 for h in expected_histories)
                or len(set(expected_histories)) != len(expected_histories)):
            raise ValueError("Expected histories must be explicit unique nonnegative IDs")
        if histories != set(expected_histories):
            raise ValueError("Observed histories differ from the frozen protocol")
    wanted = {(t, h, p) for t in tasks for h in histories for p in policies}
    if set(indexed) != wanted:
        raise ValueError("Incomplete paired grid; keep missing attempts as explicit unknown rows")
    return indexed, dict(sorted(tasks.items())), sorted(histories), {
        domain: sorted(values) for domain, values in sorted(clusters.items())}


def _rates(rows):
    rows = list(rows)
    available = [r for r in rows if r["oracle_available"]]
    return {"total": len(rows), "passed": sum(r["passed"] for r in rows),
            "all_attempt_success": _mean(r["passed"] for r in rows),
            "artifact_valid": sum(r["artifact_valid"] for r in rows),
            "oracle_available": len(available),
            "oracle_unknown": len(rows) - len(available),
            "artifact_invalid": sum(not r["artifact_valid"] for r in rows),
            "valid_artifact_oracle_unknown": sum(r["artifact_valid"] and not r["oracle_available"] for r in rows),
            "semantic_failures": sum(not r["passed"] for r in available),
            "conditional_semantic_success": _mean(r["passed"] for r in available),
            "conditional_rate_not_primary": True,
            "skill_nonempty_positions": sum(r["skill_nonempty"] for r in rows)}


def _counts(pairs):
    pairs = list(pairs)
    return {"pairs": len(pairs),
            "wins": sum(a["passed"] and not b["passed"] for a, b in pairs),
            "losses": sum(b["passed"] and not a["passed"] for a, b in pairs),
            "both_pass": sum(a["passed"] and b["passed"] for a, b in pairs),
            "both_fail_or_unknown": sum(not a["passed"] and not b["passed"] for a, b in pairs),
            "both_oracles_available": sum(a["oracle_available"] and b["oracle_available"] for a, b in pairs),
            "semantic_wins": sum(a["passed"] and b["oracle_available"] and not b["passed"] for a, b in pairs),
            "semantic_losses": sum(b["passed"] and a["oracle_available"] and not a["passed"] for a, b in pairs),
            "wins_against_unavailable": sum(a["passed"] and not b["oracle_available"] for a, b in pairs),
            "losses_with_unavailable": sum(b["passed"] and not a["oracle_available"] for a, b in pairs)}


def summarize(final_rows, *, policies=POLICIES, expected_tasks=None,
              expected_histories=None, bootstrap_samples=2000, seed=SEED):
    """Summarize native final outcomes; no online-validator judgments are used.

    Domain accuracy weights real tasks equally and averages their complete
    history blocks. Macro weights domains equally. Family bootstrap preserves
    each sampled family's size, so unequal family sizes do not silently change
    the estimand to a family-equal score. Histories are held fixed, not resampled.

    Without externally frozen expected_tasks/expected_histories, completeness
    can only be established relative to the universe present in the rows.
    """
    if type(bootstrap_samples) is not int or not 100 <= bootstrap_samples <= 20000:
        raise ValueError("Use 100..20000 bootstrap replicates")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Use a bounded nonnegative bootstrap seed")
    indexed, tasks, histories, clusters = _validate(
        final_rows, policies, expected_tasks, expected_histories)
    domains, rng = list(clusters), random.Random(seed)
    if bootstrap_samples * sum(map(len, clusters.values())) > 2000000:
        raise ValueError("Bootstrap plan exceeds the bounded family-draw budget")
    family_tasks = {d: {c: [] for c in clusters[d]} for d in domains}
    for task, meta in tasks.items():
        family_tasks[meta["domain"]][meta["cluster_id"]].append(task)
    plans = {d: [[rng.randrange(len(clusters[d])) for _ in clusters[d]]
                 for _ in range(bootstrap_samples)] for d in domains}
    family_values, policy_summary = {}, {}
    for policy in policies:
        values = {d: [] for d in domains}
        for domain in domains:
            for cluster in clusters[domain]:
                ts = family_tasks[domain][cluster]
                total = sum(_mean(indexed[t, h, policy]["passed"] for h in histories) for t in ts)
                values[domain].append((total, len(ts)))
        family_values[policy] = values
        selected = [r for r in indexed.values() if r["policy"] == policy]
        by_domain = {d: {**_rates(r for r in selected if r["domain"] == d),
                         "task_instances": sum(m["domain"] == d for m in tasks.values()),
                         "structural_families": len(clusters[d])} for d in domains}
        by_history = {}
        for history in histories:
            hs = [r for r in selected if r["history"] == history]
            rates = {d: _rates(r for r in hs if r["domain"] == d) for d in domains}
            by_history[str(history)] = {**_rates(hs), "by_domain": rates,
                "macro_all_attempt_success": _mean(rates[d]["all_attempt_success"] for d in domains)}
        policy_summary[policy] = {**_rates(selected), "by_domain": by_domain, "by_history": by_history,
            "macro_all_attempt_success": _mean(by_domain[d]["all_attempt_success"] for d in domains),
            "worst_domain_all_attempt_success": min(by_domain[d]["all_attempt_success"] for d in domains),
            "distinct_skill_hashes": len({r["skill_hash"] for r in selected}),
            "nonempty_is_not_proof_of_learning_or_use": True}
    comparisons = {}
    requested = [(p, "no_skill") for p in policies if p != "no_skill"]
    requested += [(a, b) for a, b in (("adaptive", "fixed"), ("adaptive_research", "adaptive"))
                  if a in policies and b in policies]
    for candidate, reference in requested:
        pairs = [(indexed[t, h, candidate], indexed[t, h, reference]) for t in tasks for h in histories]
        draws, by_domain = {}, {}
        for domain in domains:
            av, bv = family_values[candidate][domain], family_values[reference][domain]
            draws[domain] = [sum(av[i][0] - bv[i][0] for i in sample)
                             / sum(av[i][1] for i in sample) for sample in plans[domain]]
            delta = (policy_summary[candidate]["by_domain"][domain]["all_attempt_success"]
                     - policy_summary[reference]["by_domain"][domain]["all_attempt_success"])
            by_domain[domain] = {"delta": delta, "ci95": _interval(draws[domain]),
                "counts": _counts((a, b) for a, b in pairs if a["domain"] == domain),
                "structural_families": len(clusters[domain])}
        macro_draws = [_mean(draws[d][i] for d in domains) for i in range(bootstrap_samples)]
        delta = _mean(by_domain[d]["delta"] for d in domains)
        worst = min(by_domain[d]["delta"] for d in domains)
        comparisons[candidate + "_vs_" + reference] = {
            "candidate": candidate, "reference": reference,
            "counts": _counts(pairs), "macro": {"delta": delta, "ci95": _interval(macro_draws)},
            "by_domain": by_domain, "worst_domain_delta": worst,
            "maximum_domain_drop": max(0.0, -worst),
            "negative_domain_fraction": _mean(by_domain[d]["delta"] < 0 for d in domains),
            "by_history": {str(h): {
                "counts": _counts((a, b) for a, b in pairs if a["history"] == h),
                "macro_delta": (policy_summary[candidate]["by_history"][str(h)]["macro_all_attempt_success"]
                                - policy_summary[reference]["by_history"][str(h)]["macro_all_attempt_success"])
            } for h in histories},
            "all_attempt_losses_not_necessarily_semantic": True}
    for policy, summary in policy_summary.items():
        deltas = {d: summary["by_domain"][d]["all_attempt_success"]
                  - policy_summary["no_skill"]["by_domain"][d]["all_attempt_success"] for d in domains}
        summary.update(domain_deltas_vs_no_skill=deltas, worst_domain_delta_vs_no_skill=min(deltas.values()))
    identity_groups = {(r["task_id"], r["history"], r["skill_hash"]) for r in indexed.values()}
    return seal({"version": VERSION, "policies": list(policies), "histories": histories, "domains": domains,
        "task_instances": len(tasks), "logical_rows": len(indexed),
        "structural_families_by_domain": {d: len(clusters[d]) for d in domains},
        "policy_summary": policy_summary, "comparisons": comparisons,
        "data_quality": {"complete_observed_grid": True,
            "frozen_task_universe_checked": expected_tasks is not None,
            "frozen_history_universe_checked": expected_histories is not None,
            "grid_reference": "frozen_universe" if expected_tasks is not None and expected_histories is not None
                              else "observed_universe_only_or_partial_external_check",
            "unique_task_history_skill_identities": len(identity_groups),
            "repeated_text_positions_beyond_first": len(indexed) - len(identity_groups),
            "actual_request_aliasing_not_inferred_from_text_identity": True,
            "request_independence_requires_external_receipt_audit": True},
        "inference": {"estimand": "equal task/history native accuracy per domain; equal-domain macro",
            "bootstrap_unit": "structural family, stratified by domain, retaining all tasks and histories",
            "bootstrap_samples": bootstrap_samples, "seed": seed, "confidence_level": 0.95,
            "conditional_on_frozen_histories": True, "histories_not_independent_task_multipliers": True,
            "family_labels_do_not_establish_independence": True,
            "history_variation_mixes_learning_and_solver_sampling": True,
            "unknown_attempts_retained_as_all_attempt_failures_not_semantic_failures": True,
            "pointwise_intervals_not_multiple_comparison_control": True,
            "zero_width_interval_not_equivalence_or_safety": True,
            "few_families_have_low_and_unmeasured_power": True,
            "formal_significance_or_safety_certified": False,
            "final_native_outcomes_not_online_validator_verdicts": True,
            "outcome_analysis_cannot_verify_data_leakage_or_oracle_correctness": True}})


def rough_family_budget(*, effect_size, discordance, target_power=0.8, alpha=0.05):
    """Illustrative paired-family normal approximation, NOT a power guarantee.

    Inputs must be planned from development evidence or an external assumption,
    not selected to make an observed final effect significant. Treat one family
    as one independent paired Bernoulli unit. This deliberately gives no credit
    for extra variants, calls, or learning histories, but dependence between
    families can still invalidate the calculation. Discordance is P(win or loss).
    """
    values = (effect_size, discordance, target_power, alpha)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Planning inputs must be finite real numbers, not bools")
    if not 0 < effect_size <= discordance <= 1 or not 0.5 < target_power < 1 or not 0 < alpha < 0.5:
        raise ValueError("Require 0 < effect <= discordance <= 1, power > .5 and alpha < .5")
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(target_power)
    count = max(2, math.ceil(z * z * discordance / (effect_size * effect_size)))
    return {"version": VERSION, "approximate_independent_families": count,
        "effect_size": effect_size, "discordance": discordance,
        "target_power_assumption": target_power, "nominal_alpha_assumption": alpha,
        "model": "normal approximation n=(z_1-alpha/2+z_power)^2*discordance/effect^2",
        "per_planned_paired_endpoint_not_per_history": True,
        "does_not_multiply_evidence_by_variants_or_histories": True,
        "does_not_model_learning_variance_or_domain_shift": True,
        "requires_multiple_endpoint_adjustment_and_external_design_review": True,
        "not_a_formal_power_or_safety_guarantee": True}
