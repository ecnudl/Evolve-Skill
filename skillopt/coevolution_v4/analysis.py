"""Paired descriptive statistics; task repeats are never independent projects."""

import random
import statistics
from collections import defaultdict

ARMS = ("noskill", "fixed", "feedback", "research", "working_fixed", "working_feedback", "working_research")


def _mean(values):
    values = list(values)
    return statistics.mean(values) if values else None


def _ci(cluster_means, draws=5000, seed=20260909):
    values = list(cluster_means.values())
    if not values:
        return None
    rng = random.Random(seed)
    sampled = sorted(_mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return [sampled[int(.025 * draws)], sampled[min(draws - 1, int(.975 * draws))]]


def analyze(rows):
    indexed, projects, shared = {}, set(), defaultdict(list)
    for row in rows:
        if row["arm"] not in ARMS:
            raise ValueError("Unknown final arm")
        key = (row["id"], row["stream"], row["repeat"], row["arm"])
        if key in indexed:
            raise ValueError("Duplicate final position")
        indexed[key] = row
        projects.add(row["cluster_id"])
        shared[row["job_hash"]].append(row)
    positions = {key[:3] for key in indexed}
    if any((*position, arm) not in indexed for position in positions for arm in ARMS):
        raise ValueError("Incomplete paired final arms")
    for group in shared.values():
        fields = ("hard", "case_fraction", "skill_hash", "request_hash", "format_ok", "target_ok", "execution_ok")
        if any(any(row[field] != group[0][field] for field in fields) for row in group):
            raise ValueError("Shared calls must have identical observed results")
    arms = {}
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        available = [r for r in selected if r["target_ok"] and r["execution_ok"]]
        by_project = {}
        for project in sorted(projects):
            group = [r for r in available if r["cluster_id"] == project]
            by_project[project] = {"n": len(group), "hard_accuracy": _mean(r["hard"] for r in group),
                                   "case_fraction": _mean(r["case_fraction"] for r in group)}
        arms[arm] = {"n": len(selected), "available": len(available), "unknown": len(selected) - len(available),
                     "passed": sum(r["hard"] is True for r in available),
                     "delivery_failures": sum(not r["format_ok"] and r["target_ok"] for r in selected),
                     "hard_accuracy": _mean(r["hard"] for r in available),
                     "case_fraction": _mean(r["case_fraction"] for r in available),
                     "active_skill_positions": sum(r["skill_active"] for r in selected),
                     "by_project": by_project,
                     "by_stream": {str(s): _mean(r["hard"] for r in available if r["stream"] == s)
                                   for s in sorted({r["stream"] for r in selected})}}
    contrasts = {}
    for left, right in (("feedback", "fixed"), ("research", "feedback"), ("research", "noskill"),
                        ("working_feedback", "working_fixed"), ("working_research", "working_feedback"),
                        ("working_research", "noskill")):
        changes, aliases, unknown = [], 0, 0
        by_project = defaultdict(list)
        for position in sorted(positions):
            a, b = indexed[(*position, left)], indexed[(*position, right)]
            aliases += a["job_hash"] == b["job_hash"]
            if not all(r["target_ok"] and r["execution_ok"] for r in (a, b)):
                unknown += 1
                continue
            delta = int(a["hard"]) - int(b["hard"])
            changes.append(delta)
            by_project[a["cluster_id"]].append(delta)
        means = {k: _mean(v) for k, v in by_project.items()}
        contrasts[f"{left}_vs_{right}"] = {
            "paired_positions": len(changes), "unknown_pairs": unknown,
            "wins": sum(d > 0 for d in changes), "losses": sum(d < 0 for d in changes),
            "paired_hard_delta": _mean(changes), "project_macro_delta": _mean(means.values()),
            "exploratory_project_bootstrap95": _ci(means), "same_request_alias_pairs": aliases,
            "all_pairs_structurally_identical": aliases == len(positions),
            "structural_zero_is_not_equivalence_evidence": True,
        }
    flips = {}
    for arm in ARMS:
        groups = defaultdict(list)
        for r in rows:
            if r["arm"] == arm and r["target_ok"] and r["execution_ok"]:
                groups[r["id"], r["stream"]].append(r["hard"])
        flips[arm] = {"task_history_groups": len(groups),
                      "groups_with_repeat_flip": sum(len(set(v)) > 1 for v in groups.values())}
    return {"rows": len(rows), "unique_solution_jobs": len(shared), "project_clusters": len(projects),
            "arms": arms, "contrasts": contrasts, "repeat_variability": flips,
            "limitations": [
                "Engineering study on previously exposed adapted Coding projects, not independent benchmark results.",
                "Only three final project clusters and two histories; bootstrap intervals are exploratory.",
                "Repeated observations are not additional independent projects or proven model seeds.",
                "Finite tests and probe searches are not formal correctness or cross-domain safety certificates.",
                "Working arms are diagnostic forced-use interventions, not deployed policies.",
            ]}
