"""Pure, outcome-only analysis for prospective SearchQA Skill learning.

The unit of uncertainty is a predeclared question cluster, not a model call or
an aliased No-Skill draw. Intervals condition on the actually trained histories;
three histories cannot support broad claims about learning-seed variability.
This module does not open data, call models, change gates, or authorize scope.
"""

from __future__ import annotations

import itertools
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence

from skillopt.coevolution_v5.core import seal
from skillopt.evaluation.gate import evaluate_gate

POLICIES = ("no_skill", "initial", "skillopt", "ours")
PRIMARY_COMPARISONS = (("ours", "no_skill"), ("ours", "skillopt"))


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1000


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _score(value, *, binary=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and 0 <= value <= 1 and (not binary or value in (0, 1)))


def _mean(values):
    return sum(values) / len(values) if values else None


def _number(row, metric):
    return 0.0 if row[metric] is None else float(row[metric])


def _validate(rows, expected_tasks, histories, policies):
    if (not isinstance(expected_tasks, Mapping) or not expected_tasks
            or len(expected_tasks) > 100000):
        raise ValueError("A bounded, nonempty preregistered question mapping is required")
    expected = {}
    for task, metadata in expected_tasks.items():
        if (not _text(task) or not isinstance(metadata, Mapping)
                or not _text(metadata.get("cluster_id"))):
            raise ValueError("Every expected question needs its predeclared cluster identity")
        expected[task] = metadata["cluster_id"]
    if (not isinstance(histories, (list, tuple)) or not histories
            or any(type(history) is not int or history < 0 for history in histories)
            or len(set(histories)) != len(histories)):
        raise ValueError("Histories must be predeclared, unique, nonnegative integers")
    if (not isinstance(policies, (list, tuple)) or not all(_text(p) for p in policies)
            or len(set(policies)) != len(policies) or not set(POLICIES).issubset(policies)):
        raise ValueError("Unique policies must include the three actual main controls")
    if not isinstance(rows, (list, tuple)) or len(rows) > 1000000:
        raise ValueError("Rows must be a bounded materialized observation grid")
    indexed, requests = {}, {}
    fixed_hashes, history_policy_hashes = defaultdict(set), defaultdict(set)
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Every observation must be an object")
        if (not _text(row.get("task_id")) or row["task_id"] not in expected
                or not _text(row.get("policy")) or type(row.get("history")) is not int
                or row["history"] not in histories or row.get("policy") not in policies
                or row.get("cluster_id") != expected[row["task_id"]]):
            raise ValueError("Question/cluster/history/policy differs from preregistration")
        if (type(row.get("api_ok")) is not bool or not _hash(row.get("request_hash"))
                or not _hash(row.get("skill_hash"))):
            raise ValueError("Actual API outcome, request hash, and Skill hash are required")
        if "em" not in row or "f1" not in row or (row["em"] is None) != (row["f1"] is None):
            raise ValueError("EM and F1 must be present and jointly available or missing")
        if row["em"] is not None and (not _score(row["em"], binary=True) or not _score(row["f1"])):
            raise ValueError("Native EM must be binary and F1 finite in [0, 1]")
        if not row["api_ok"] and row["em"] is not None:
            raise ValueError("An API failure cannot masquerade as a scored semantic failure")
        if row["em"] == 1 and row["f1"] != 1:
            raise ValueError("Native exact match implies token F1 equals one")
        key = (row["task_id"], row["history"], row["policy"])
        if key in indexed:
            raise ValueError("Duplicate question/history/policy observation")
        indexed[key] = dict(row)
        identity = (row["task_id"], row["skill_hash"], row["api_ok"], row["em"], row["f1"])
        if requests.setdefault(row["request_hash"], identity) != identity:
            raise ValueError("Shared request aliases must retain question, Skill, and actual outcome")
        history_policy_hashes[row["history"], row["policy"]].add(row["skill_hash"])
        if row["policy"] in ("no_skill", "initial"):
            fixed_hashes[row["policy"]].add(row["skill_hash"])
    planned = {(task, history, policy) for task in expected for history in histories for policy in policies}
    if set(indexed) != planned:
        raise ValueError("Incomplete frozen grid: missing executions must be explicit missing outcomes")
    if any(len(values) != 1 for values in fixed_hashes.values()):
        raise ValueError("No-Skill and initial controls cannot change Skill across questions or histories")
    if any(len(values) != 1 for values in history_policy_hashes.values()):
        raise ValueError("Each source-local final policy must use its one frozen Skill per history")
    return indexed, expected, tuple(sorted(histories)), tuple(policies), requests


def _percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def question_cluster_inference(deltas, *, bootstrap_samples=5000, seed=20260913,
                               permutation_samples=20000):
    """Question-cluster uncertainty after within-cluster/history averaging.

The sign-flip diagnostic assumes independent, exchangeable cluster difference
signs; it is not a randomization test of the learning algorithm. Monte Carlo
tests use the plus-one correction and a deterministic analysis-only seed.
"""
    if (not isinstance(deltas, Mapping) or not deltas
            or any(not _text(k) or type(v) not in (int, float)
                   or not math.isfinite(v) or not -1 <= v <= 1 for k, v in deltas.items())):
        raise ValueError("Finite, bounded, pre-averaged question-cluster differences are required")
    if (type(bootstrap_samples) is not int or not 100 <= bootstrap_samples <= 100000
            or type(permutation_samples) is not int or not 100 <= permutation_samples <= 100000
            or type(seed) is not int or seed < 0):
        raise ValueError("Use bounded deterministic resampling counts and a nonnegative seed")
    ordered = {key: float(deltas[key]) for key in sorted(deltas)}
    values = list(ordered.values())
    observed = _mean(values)
    rng = random.Random(seed)
    draws = [sum(values[rng.randrange(len(values))] for _ in values) / len(values)
             for _ in range(bootstrap_samples)]
    # Zero differences do not change the null distribution. Enumerating only
    # nonzero signs yields the same exact probability as including their ties.
    nonzero = [value for value in values if value != 0]
    threshold = abs(sum(values)) - 1e-12
    if len(nonzero) <= 16:
        nulls = [sum(sign * value for sign, value in zip(signs, nonzero))
                 for signs in itertools.product((-1, 1), repeat=len(nonzero))]
        p = sum(abs(value) >= threshold for value in nulls) / len(nulls)
        test = {"p_two_sided": p, "exact": True, "assignments": len(nulls)}
    else:
        permutation_rng = random.Random(seed + 1)
        exceed = sum(abs(sum(value if permutation_rng.getrandbits(1) else -value for value in nonzero))
                     >= threshold for _ in range(permutation_samples))
        test = {"p_two_sided": (exceed + 1) / (permutation_samples + 1), "exact": False,
                "assignments": permutation_samples, "plus_one_correction": True}
    test.update({"unit": "question_cluster", "nonzero_clusters": len(nonzero),
                 "null_assumption": "independent_exchangeable_cluster_difference_signs",
                 "causal_randomization_claim": False})
    return {"mean_delta": observed, "clusters": len(values), "cluster_deltas": ordered,
            "ci95": {"low": _percentile(draws, 0.025), "high": _percentile(draws, 0.975)},
            "bootstrap": {"method": "paired_question_cluster_percentile", "samples": bootstrap_samples,
                          "seed": seed, "conditional_on_observed_learning_histories": True},
            "sign_flip": test, "few_clusters_descriptive_only": len(values) < 20,
            "independence_unit": "predeclared_question_cluster_not_draw_or_history",
            "scope_expansion_authorized": False, "safety_claim": False}


def _rates(rows):
    available = [row for row in rows if row["em"] is not None]
    return {"n_positions": len(rows), "unique_requests": len({row["request_hash"] for row in rows}),
            "api_ok": sum(row["api_ok"] for row in rows), "oracle_available": len(available),
            "unknown": len(rows) - len(available),
            "all_attempt_em": _mean([_number(row, "em") for row in rows]),
            "all_attempt_f1": _mean([_number(row, "f1") for row in rows]),
            "available_only_em_diagnostic": _mean([row["em"] for row in available]),
            "available_only_f1_diagnostic": _mean([row["f1"] for row in available]),
            "available_only_is_selection_sensitive": True}


def _tally(deltas):
    return {"n": len(deltas), "wins": sum(d > 0 for d in deltas),
            "losses": sum(d < 0 for d in deltas), "ties": sum(d == 0 for d in deltas),
            "mean_delta": _mean(deltas)}


def _compare(indexed, tasks, histories, left, right, *, bootstrap_samples, seed, permutation_samples):
    pairs = [(indexed[task, history, left], indexed[task, history, right])
             for task in sorted(tasks) for history in histories]
    jointly_available = [(a, b) for a, b in pairs if a["em"] is not None and b["em"] is not None]
    result = {"left": left, "right": right, "n_question_clusters": len(set(tasks.values())),
              "n_learning_histories": len(histories), "n_question_history_positions": len(pairs),
              "shared_request_positions": sum(a["request_hash"] == b["request_hash"] for a, b in pairs),
              "jointly_available_positions": len(jointly_available),
              "jointly_available_is_selection_sensitive": True,
              "per_history": {}, "metrics": {}}
    for metric in ("em", "f1"):
        clusters = defaultdict(list)
        for a, b in pairs:
            clusters[a["cluster_id"]].append(_number(a, metric) - _number(b, metric))
        result["metrics"][metric] = {
            "all_attempt": _tally([_number(a, metric) - _number(b, metric) for a, b in pairs]),
            "jointly_available_diagnostic": _tally([a[metric] - b[metric] for a, b in jointly_available]),
            "cluster_inference": question_cluster_inference(
                {key: _mean(values) for key, values in clusters.items()}, bootstrap_samples=bootstrap_samples,
                seed=seed, permutation_samples=permutation_samples)}
    for history in histories:
        selected = [(a, b) for a, b in pairs if a["history"] == history]
        result["per_history"][str(history)] = {
            metric: _tally([_number(a, metric) - _number(b, metric) for a, b in selected])
            for metric in ("em", "f1")}
    correct_right = [(a, b) for a, b in pairs if b["em"] == 1]
    losses = sum(_number(a, "em") == 0 for a, _ in correct_right)
    confirmed_losses = sum(a["em"] == 0 for a, _ in correct_right)
    result["right_correct_left_unsuccessful"] = {
        "count": losses, "confirmed_scored_losses": confirmed_losses,
        "unknown_left_losses": losses - confirmed_losses,
        "all_positions_denominator": len(pairs), "all_positions_rate": losses / len(pairs),
        "right_correct_denominator": len(correct_right),
        "right_correct_rate": losses / len(correct_right) if correct_right else None}
    history_deltas = [result["per_history"][str(h)]["em"]["mean_delta"] for h in histories]
    result["history_em_delta_range"] = {"min": min(history_deltas), "max": max(history_deltas),
                                         "history_resampling_claim": False}
    return result


def _holm(p_values):
    ordered = sorted(p_values, key=lambda key: (p_values[key], key))
    adjusted, previous = {}, 0.0
    for index, key in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered) - index) * p_values[key]))
        adjusted[key] = previous
    return adjusted


def summarize_final(rows: Sequence[Mapping], *, expected_tasks: Mapping, histories: Sequence[int],
                    policies=POLICIES, bootstrap_samples=5000, seed=20260913,
                    permutation_samples=20000):
    """Analyze a complete frozen three-control grid without selecting anything.

Required row keys: task_id, cluster_id, history, policy, em, f1, api_ok,
request_hash, skill_hash. Missing scores are explicit ``None`` and stay in all
attempt denominators. Additional descriptive reference policies are allowed.
"""
    indexed, tasks, histories, policies, requests = _validate(rows, expected_tasks, histories, policies)
    comparisons = {}
    for left, right in (*PRIMARY_COMPARISONS, ("skillopt", "no_skill"),
                        ("ours", "initial"), ("skillopt", "initial"), ("initial", "no_skill")):
        comparisons[f"{left}_vs_{right}"] = _compare(
            indexed, tasks, histories, left, right, bootstrap_samples=bootstrap_samples,
            seed=seed, permutation_samples=permutation_samples)
    primary = [f"{left}_vs_{right}" for left, right in PRIMARY_COMPARISONS]
    adjusted = _holm({key: comparisons[key]["metrics"]["em"]["cluster_inference"]["sign_flip"]["p_two_sided"]
                      for key in primary})
    for key, value in adjusted.items():
        comparisons[key]["primary_em_holm_adjusted_p"] = value
    request_usage = Counter(row["request_hash"] for row in rows)
    by_policy = {}
    for policy in policies:
        selected = [row for row in indexed.values() if row["policy"] == policy]
        clustered = defaultdict(list)
        for row in selected:
            clustered[row["cluster_id"]].append(row)
        by_policy[policy] = {
            **_rates(selected),
            "distinct_skill_hashes": len({row["skill_hash"] for row in selected}),
            "evolved_skill_positions": sum(row["skill_hash"] != indexed[row["task_id"], row["history"], "initial"]["skill_hash"]
                                           for row in selected) if policy in ("skillopt", "ours") else None,
            "question_cluster_equal_em": _mean([_rates(group)["all_attempt_em"] for group in clustered.values()]),
            "question_cluster_equal_f1": _mean([_rates(group)["all_attempt_f1"] for group in clustered.values()]),
            "per_history": {str(history): _rates([row for row in selected if row["history"] == history])
                            for history in histories}}
    return {"full_grid_verified": True, "n_questions": len(tasks),
            "n_question_clusters": len(set(tasks.values())), "histories": list(histories),
            "n_observation_positions": len(rows), "unique_actual_requests": len(requests),
            "aliased_positions_beyond_first_request": sum(count - 1 for count in request_usage.values()),
            "policy_summary": by_policy, "comparisons": comparisons,
            "primary_metric": "native_searchqa_em", "secondary_metric": "native_searchqa_f1",
            "primary_em_multiplicity": {"method": "Holm", "family": primary, "alpha": 0.05},
            "intervals_are_conditional_on_observed_learning_histories": True,
            "unknown_scored_zero_only_for_all_attempt_summary": True,
            "source_domain_only": True, "cross_domain_generalization_established": False,
            "skill_text_contents_verified_by_this_module": False,
            "safety_or_noninferiority_certified": False, "scope_expansion_authorized": False}


def local_gate(parent_rows, candidate_rows, base_rows, *, expected_tasks,
               minimum_clusters=64, alpha=0.10):
    """Aggregate a one-use source confirmation screen, without per-item feedback.

The standard decision calls the actual SkillOpt strict hard-EM gate. Our
exploratory restriction additionally requires no observed EM loss vs No-Skill
and a one-sided exact discordant-binomial p <= .10 vs the parent. It is NOT a
noninferiority or safety test. Parent retention is not No-Skill fallback.

``minimum_clusters`` is explicit for bounded offline tests. The real frozen
protocol uses 64; changing it after any confirmation call is not permitted.
``expected_tasks`` is mandatory to catch losses common to all three arms,
which observations alone cannot discover.
"""
    if (type(minimum_clusters) is not int or minimum_clusters < 1
            or type(alpha) not in (int, float) or not math.isfinite(alpha) or not 0 < alpha < 1):
        raise ValueError("The confirmation minimum and exploratory alpha must be fixed before scoring")
    groups, question_clusters, histories, requests = {}, {}, set(), {}
    for name, incoming in (("parent", parent_rows), ("candidate", candidate_rows), ("base", base_rows)):
        if not isinstance(incoming, (list, tuple)) or not incoming or len(incoming) > 4096:
            raise ValueError("Each confirmation arm needs a bounded nonempty actual observation list")
        indexed = {}
        for row in incoming:
            if (not isinstance(row, Mapping) or not _text(row.get("task_id"))
                    or not _text(row.get("cluster_id")) or type(row.get("history")) is not int
                    or row["history"] < 0 or type(row.get("api_ok")) is not bool
                    or not _hash(row.get("request_hash")) or not _hash(row.get("skill_hash"))):
                raise ValueError("Confirmation requires question/cluster/history and actual receipt identity")
            if ("em" not in row or "f1" not in row or (row["em"] is None) != (row["f1"] is None)
                    or (row["em"] is not None and (not _score(row["em"], binary=True) or not _score(row["f1"])))
                    or (not row["api_ok"] and row["em"] is not None)
                    or (row["em"] == 1 and row["f1"] != 1)):
                raise ValueError("Confirmation missingness and native scores are inconsistent")
            if row["task_id"] in indexed:
                raise ValueError("Repeated draws cannot enlarge a confirmation question sample")
            indexed[row["task_id"]] = row
            histories.add(row["history"])
            if question_clusters.setdefault(row["task_id"], row["cluster_id"]) != row["cluster_id"]:
                raise ValueError("Confirmation question clusters cannot differ across arms")
            identity = (row["task_id"], row["skill_hash"], row["api_ok"], row["em"], row["f1"])
            if requests.setdefault(row["request_hash"], identity) != identity:
                raise ValueError("Confirmation request aliases cannot change question/Skill/outcome")
        if len({row["skill_hash"] for row in incoming}) != 1:
            raise ValueError("A confirmation arm must use one frozen Skill version")
        groups[name] = indexed
    if (len(histories) != 1 or any(set(group) != set(groups["parent"]) for group in groups.values())
            or len(set(question_clusters.values())) != len(question_clusters)):
        raise ValueError("One history and exactly one question per independent confirmation cluster are required")
    enough_clusters = len(question_clusters) >= minimum_clusters
    if (not isinstance(expected_tasks, Mapping)
            or any(not _text(task) or not isinstance(meta, Mapping) or not _text(meta.get("cluster_id"))
                   for task, meta in expected_tasks.items())
            or {task: meta["cluster_id"] for task, meta in expected_tasks.items()} != question_clusters):
        raise ValueError("Confirmation questions differ from the prospective full reservation")
    if next(iter(groups["parent"].values()))["skill_hash"] == next(iter(groups["candidate"].values()))["skill_hash"]:
        if any(groups["parent"][task]["request_hash"] != groups["candidate"][task]["request_hash"]
               for task in question_clusters):
            raise ValueError("An unchanged candidate must reuse the parent's exact confirmation trajectory")
    rates = {name: _rates(list(group.values())) for name, group in groups.items()}
    parent_em, candidate_em = rates["parent"]["all_attempt_em"], rates["candidate"]["all_attempt_em"]
    base_em = rates["base"]["all_attempt_em"]
    # The gate only uses score ordering. Sentinel Skill strings ensure this
    # helper never emits real candidate text or confirmation labels as feedback.
    standard = evaluate_gate("candidate", candidate_em, "parent", parent_em,
                             "parent", parent_em, 0, 1)
    standard_accept = standard.action in ("accept", "accept_new_best")
    differences = [_number(groups["candidate"][task], "em") - _number(groups["parent"][task], "em")
                   for task in sorted(question_clusters)]
    counts = _tally(differences)
    n_discordant = counts["wins"] + counts["losses"]
    p_one_sided = (sum(math.comb(n_discordant, wins) for wins in range(counts["wins"], n_discordant + 1))
                   / 2 ** n_discordant) if n_discordant else 1.0
    no_observed_base_loss = candidate_em >= base_em
    evidence_pass = p_one_sided <= alpha
    ours_accept = enough_clusters and standard_accept and no_observed_base_loss and evidence_pass
    reasons = []
    if not enough_clusters:
        reasons.append("insufficient_independent_confirmation_question_clusters")
    if not standard_accept:
        reasons.append("candidate_does_not_strictly_improve_parent_native_em")
    if not no_observed_base_loss:
        reasons.append("candidate_native_em_below_no_skill")
    if not evidence_pass:
        reasons.append("paired_parent_improvement_evidence_insufficient")
    base_correct = [task for task in question_clusters if groups["base"][task]["em"] == 1]
    base_losses = sum(_number(groups["candidate"][task], "em") == 0 for task in base_correct)
    return seal({
        "kind": "v9_source_local_confirmation_gate", "history": next(iter(histories)),
        "n_question_clusters": len(question_clusters), "minimum_clusters": minimum_clusters,
        "prospective_reservation_verified": True, "enough_question_clusters": enough_clusters,
        "rates": rates, "candidate_vs_parent": counts,
        "exact_discordant_one_sided_p": p_one_sided, "exploratory_alpha": alpha,
        "standard_action": standard.action, "standard_accept": standard_accept,
        "candidate_em_not_below_base": no_observed_base_loss, "ours_accept": ours_accept,
        "ours_action": "Local Commit" if ours_accept else "Restrict",
        "rejection_retains_parent_not_no_skill": True, "reasons": reasons,
        "base_correct_candidate_unsuccessful": {"count": base_losses, "all_questions_denominator": len(question_clusters),
                                                "base_correct_denominator": len(base_correct)},
        "unique_actual_requests": len(requests), "source_domain_only": True,
        "per_question_labels_returned": False, "optimizer_feedback_authorized": False,
        "cross_domain_commit_authorized": False, "safety_or_noninferiority_certified": False,
        "unknowns_are_not_confirmed_semantic_failures": True})
