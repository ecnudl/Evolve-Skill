"""Separate native correctness, delivery coverage and clustered uncertainty."""

from __future__ import annotations

import math
from collections import defaultdict

from skillopt.coevolution_v5.core import seal

from .statistics import cluster_inference


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _score(value):
    if value is not None and (type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError("Native score must be a finite fraction or explicit unknown")
    return float(value) if value is not None else 0.0


def summarize_transfer(rows):
    policies = {"no_skill", "always_candidate", "mechanism_routed_candidate"}
    if not isinstance(rows, list) or not rows:
        raise ValueError("A nonempty final observation grid is required")
    indexed, identities, positions = {}, {}, set()
    for row in rows:
        if row["policy"] not in policies or row["evaluation_group"] not in {"same_mechanism", "near_miss", "unrelated"}:
            raise ValueError("Unknown policy or frozen evaluation group")
        if type(row["history"]) is not int or row["history"] < 0:
            raise ValueError("Explicit learning history required")
        _score(row["score"])
        if not isinstance(row["request_hashes"], list) or not row["request_hashes"]:
            raise ValueError("Actual solver request identities are required")
        identity = row["domain"], row["cluster_id"], row["evaluation_group"]
        if identities.setdefault(row["task_id"], identity) != identity:
            raise ValueError("Task identity or evaluation group changes across conditions")
        position = row["task_id"], row["history"]
        positions.add(position)
        key = row["policy"], *position
        if key in indexed:
            raise ValueError("Duplicate final policy/task/history observation")
        indexed[key] = row
    if set(indexed) != {(p, *position) for p in policies for position in positions}:
        raise ValueError("Missing paired policy positions; unavailable answers must be explicit unknown")
    histories = {row["history"] for row in rows}
    if positions != {(task, history) for task in identities for history in histories}:
        raise ValueError("An entire task/history block is missing")
    for task, history in positions:
        baseline, always, routed = (indexed[p, task, history] for p in (
            "no_skill", "always_candidate", "mechanism_routed_candidate"))
        expected = always if routed["route"]["apply"] else baseline
        if any(routed[k] != expected[k] for k in ("request_hashes", "artifact_hash", "skill_hash", "score")):
            raise ValueError("Routed counterfactual is not the exact predeclared intervention")

    summaries, comparisons = {}, {}
    domains = sorted({r["domain"] for r in rows})
    for policy in sorted(policies):
        domain_summary, group_summary = {}, {}
        for domain in domains:
            selected = [r for r in rows if r["policy"] == policy and r["domain"] == domain]
            by_task = defaultdict(list)
            for row in selected:
                by_task[row["cluster_id"], row["task_id"]].append(_score(row["score"]))
            by_cluster = defaultdict(list)
            for (cluster, _), values in by_task.items():
                by_cluster[cluster].append(mean(values))
            domain_summary[domain] = {"all_attempt_yield": mean(mean(v) for v in by_cluster.values()),
                "available_score_mean": mean(r["score"] for r in selected if r["score"] is not None),
                "unavailable": sum(r["score"] is None for r in selected), "logical_rows": len(selected),
                "task_instances": len(by_task), "structural_clusters": len(by_cluster),
                "skill_application_rate": mean(not r["fallback"] for r in selected)}
            for category in ("same_mechanism", "near_miss", "unrelated"):
                values = [r for r in selected if r["evaluation_group"] == category]
                group_summary[domain + ":" + category] = {"all_attempt_yield": mean(_score(r["score"]) for r in values),
                    "positions": len(values), "task_instances": len({r["task_id"] for r in values}),
                    "clusters": len({r["cluster_id"] for r in values}),
                    "skill_application_rate": mean(not r["fallback"] for r in values)}
        summaries[policy] = {"domains": domain_summary, "groups": group_summary,
                             "macro_all_attempt_yield": mean(d["all_attempt_yield"] for d in domain_summary.values())}
        if policy == "no_skill":
            continue
        task_deltas, counts = defaultdict(list), {"wins": 0, "losses": 0, "ties": 0, "paired_unavailable": 0,
                                                 "confirmed_case_losses": 0, "unavailable_preservation_checks": 0}
        for task, history in sorted(positions):
            baseline, row = indexed["no_skill", task, history], indexed[policy, task, history]
            delta = _score(row["score"]) - _score(baseline["score"])
            task_deltas[row["domain"], row["cluster_id"], task].append(delta)
            counts["wins" if delta > 0 else "losses" if delta < 0 else "ties"] += 1
            counts["paired_unavailable"] += int(row["score"] is None or baseline["score"] is None)
            after = {case["id"]: case["passed"] for case in row["case_results"]}
            for case in baseline["case_results"]:
                if case["passed"] is True:
                    counts["confirmed_case_losses"] += int(after.get(case["id"]) is False)
                    counts["unavailable_preservation_checks"] += int(after.get(case["id"]) is None)
        clusters = defaultdict(list)
        for (domain, cluster, _), values in task_deltas.items():
            clusters[domain, cluster].append(mean(values))
        per_domain = {domain: cluster_inference({cluster: mean(v) for (d, cluster), v in clusters.items() if d == domain})
                      for domain in domains}
        comparisons[policy] = {"vs": "no_skill", **counts, "by_domain": per_domain,
            "overall_cluster_diagnostic": cluster_inference({d + ":" + c: mean(v) for (d, c), v in clusters.items()}),
            "worst_domain_delta": min(d["mean_delta"] for d in per_domain.values()),
            "negative_domain_fraction": mean(d["mean_delta"] < 0 for d in per_domain.values()),
            "unit": "within-task histories averaged, then instances within structural family",
            "all_attempt_losses_include_delivery_not_only_semantic_errors": True}
    avoided, forgone = 0, 0
    for task, history in positions:
        base, always, routed = (indexed[p, task, history] for p in (
            "no_skill", "always_candidate", "mechanism_routed_candidate"))
        if not routed["route"]["apply"]:
            difference = _score(always["score"]) - _score(base["score"])
            avoided += int(difference < 0)
            forgone += int(difference > 0)
    return seal({"policy_summary": summaries, "paired_vs_no_skill": comparisons,
        "routing_counterfactual": {"avoided_loss_positions": avoided, "forgone_gain_positions": forgone},
        "task_instances": len(identities), "histories": len(histories), "logical_rows": len(rows),
        "unique_trajectory_receipts": len({tuple(r["request_hashes"]) for r in rows}),
        "explicit_contract_router_not_free_text_generalization": True,
        "candidate_evaluation_not_deployment_approval": True, "public_benchmark_claim": False})


def summarize_repairs(rows):
    indexed, projects = {}, set()
    for row in rows:
        position = row["task_id"], row["history"]
        if position in indexed:
            raise ValueError("Duplicate predeclared repair position")
        indexed[position] = row
        projects.add(row["cluster_id"])
    arms = {}
    for arm in ("score_only", "structured_evidence"):
        values = [row["result"]["arms"][arm] for row in rows]
        arms[arm] = {"successful_repairs": sum(v["metrics"]["repair_success"] is True for v in values),
                     "unknown_repairs": sum(v["metrics"]["repair_success"] is None for v in values),
                     "attempts": len(values),
                     "passing_case_regressions": sum(len(v["new_passing_check_losses"]) for v in values)}
    differences = defaultdict(list)
    for row in rows:
        arm = row["result"]["arms"]
        differences[row["cluster_id"]].append(int(arm["structured_evidence"]["metrics"]["repair_success"] is True)
            - int(arm["score_only"]["metrics"]["repair_success"] is True))
    return {"arms": arms, "clusters": len(projects), "positions": len(rows),
            "cluster_diagnostic": cluster_inference({k: mean(v) for k, v in differences.items()}) if rows else None,
            "source": "predeclared authored buggy development fixtures, not agent-generated failures",
            "not_human_feedback_quality_rating": True, "small_cluster_count_not_efficacy_proof": True}
