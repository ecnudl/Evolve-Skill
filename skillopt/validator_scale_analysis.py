"""Exploratory paired solver analysis respecting task/family/repeat structure.

Pure analysis: no API, model, filesystem, or executable candidate access.
Family-cluster percentile bootstrap is a diagnostic, particularly weak with four
held-out families. Neither bootstrap draws nor serving repeats create new tasks.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

ARMS = ("noskill", "generic_control", "mechanism_skill")
REPEATS = (0, 1, 2, 3)
CONTRASTS = (("mechanism_skill", "noskill", "primary"),
             ("mechanism_skill", "generic_control", "secondary"))
REFERENCES = [
    {"title": "Cameron and Miller (2015), A Practitioner's Guide to Cluster-Robust Inference",
     "url": "https://escholarship.org/uc/item/1jq5d0pq",
     "use": "Cluster dependence and few-cluster cautions; not a guarantee for this four-family percentile bootstrap."},
    {"title": "Agarwal et al. (2021), Deep RL at the Edge of the Statistical Precipice",
     "url": "https://proceedings.neurips.cc/paper_files/paper/2021/file/f514cec81cb148559cf475e7426eed5e-Paper.pdf",
     "use": "Motivation for reporting repeat variability and interval estimates, not direct validation of this design."},
]
LIMITATIONS = [
    "Exploratory, not confirmatory: no p-values, population superiority claim, or established equivalence.",
    "The primary estimator averages paired available repeats within task, tasks within family, then families equally.",
    "Family bootstrap resamples whole observed families; it does not treat tasks or repeated responses as independent clusters.",
    "Four held-out family clusters are very few; intervals can be unstable, discrete, or degenerate and need independent replication.",
    "If these chosen families are not a representative random sample, intervals do not establish generalization to new families/domains.",
    "Repeated temperature-zero serving calls may reveal nondeterminism; repeat labels are not independent training or generation seeds.",
    "Unavailable outcomes are not scored wrong. Observed-pair effects condition on availability; worst-case missingness bounds are separate.",
    "Subsampling draws are conditional diagnostics from the same observed matrix, not extra evidence or probabilities of true benefit.",
    "Primary and secondary contrasts are both reported; intervals are unadjusted exploratory intervals, not simultaneous guarantees.",
    "The all scope combines development and holdout tasks and is not an independent holdout result.",
]


def _mean(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if len(values) else None


def _seed(seed: int, label: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest()[:8], "big")


def _valid_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _index(rows: Iterable[Mapping[str, Any]], manifest, arms, repeats):
    values = list(rows)
    tasks, indexed, family_splits = {}, {}, {}
    manifest_supplied = manifest is not None
    def add_task(incoming):
        meta = {key: incoming.get(key) for key in ("id", "family", "cluster_id", "split")}
        if any(not _valid_text(value) for value in meta.values()) or meta["split"] not in {"dev", "holdout"}:
            raise ValueError("Task metadata requires id/family/cluster_id and dev or holdout split")
        identity = meta["id"]
        if identity in tasks and tasks[identity] != meta:
            raise ValueError("Task identity maps to inconsistent metadata")
        if meta["family"] in family_splits and family_splits[meta["family"]] != meta["split"]:
            raise ValueError("A task family cannot cross development and holdout splits")
        family_splits[meta["family"]] = meta["split"]
        tasks[identity] = meta
    if manifest_supplied:
        for task in manifest:
            if not isinstance(task, Mapping) or task.get("id") in tasks:
                raise ValueError("Manifest must contain unique task objects")
            add_task(task)
    for incoming in values:
        if not isinstance(incoming, Mapping):
            raise ValueError("Each response must be a mapping")
        row = dict(incoming)
        if manifest_supplied and row.get("id") not in tasks:
            raise ValueError("Response task is absent from expected manifest")
        add_task(row)
        if row.get("arm") not in arms or type(row.get("repeat")) is not int or row["repeat"] not in repeats:
            raise ValueError("Unexpected arm or repeat")
        for field in ("target_ok", "execution_ok"):
            if type(row.get(field)) is not bool:
                raise ValueError(f"{field} must be an explicit bool")
        for field in ("hard", "format_ok", "public_ok"):
            if field not in row or (row[field] is not None and type(row[field]) is not bool):
                raise ValueError(f"{field} must be an explicit bool or None")
        if not _valid_text(row.get("request_hash")):
            raise ValueError("Each observed row requires a nonempty request_hash")
        key = row["id"], row["arm"], row["repeat"]
        if key in indexed:
            raise ValueError("Duplicate task/arm/repeat row")
        indexed[key] = row
    return dict(sorted(tasks.items())), indexed, manifest_supplied


def _reason(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return "missing_row"
    if not row["target_ok"]:
        return "target_api_error"
    if not row["execution_ok"]:
        return "execution_unavailable"
    if row["hard"] is None:
        return "missing_hard"
    return "observable"


def _outcome(row) -> float | None:
    return float(row["hard"]) if _reason(row) == "observable" else None


def _aggregate(task_values: Mapping[str, float], tasks) -> dict[str, Any]:
    families: dict[str, list[float]] = defaultdict(list)
    for identity, value in task_values.items():
        families[tasks[identity]["family"]].append(value)
    family_means = {family: float(np.mean(values)) for family, values in sorted(families.items())}
    return {"macro_family_mean": _mean(list(family_means.values())),
            "micro_task_mean": _mean(list(task_values.values())),
            "n_observed_tasks": len(task_values), "n_observed_families": len(family_means),
            "family_means": family_means}


def _arm_summary(tasks, indexed, arm, repeats):
    counts: Counter[str] = Counter()
    all_scores, task_means, task_records = [], {}, []
    lower, upper = {}, {}
    format_values, public_values = [], []
    for identity, task in tasks.items():
        scores, per_repeat, reasons = [], {}, {}
        for repeat in repeats:
            row = indexed.get((identity, arm, repeat))
            reason = _reason(row)
            reasons[str(repeat)] = reason
            counts[reason] += 1
            score = _outcome(row)
            if score is not None:
                scores.append(score)
                per_repeat[str(repeat)] = bool(score)
            if row is not None:
                counts["observed_rows"] += 1
                counts["unusable_populated_hard"] += row["hard"] is not None and reason != "observable"
                if row["target_ok"] and row["format_ok"] is not None:
                    format_values.append(float(row["format_ok"]))
                if row["target_ok"] and row["execution_ok"] and row["public_ok"] is not None:
                    public_values.append(float(row["public_ok"]))
        if scores:
            task_means[identity] = float(np.mean(scores))
            all_scores.extend(scores)
        successes = sum(scores)
        lower[identity] = successes / len(repeats)
        upper[identity] = (successes + len(repeats) - len(scores)) / len(repeats)
        mixed = bool(scores) and min(scores) != max(scores)
        disagreement = (2 * successes * (len(scores) - successes) / (len(scores) * (len(scores) - 1))
                        if len(scores) >= 2 else None)
        task_records.append({"id": identity, "family": task["family"], "available_repeats": len(scores),
                             "hard_passes": int(successes), "hard_mean": _mean(scores),
                             "replicate_outcomes": per_repeat, "replicate_status": reasons,
                             "mixed_success_and_failure": mixed, "pairwise_replicate_disagreement": disagreement})
    eligible = [row for row in task_records if row["available_repeats"] >= 2]
    return {"n_expected_tasks": len(tasks), "n_expected_responses": len(tasks) * len(repeats),
            "n_rows": counts["observed_rows"], "n_observable": len(all_scores),
            "hard_passes": int(sum(all_scores)), "hard_failures": len(all_scores) - int(sum(all_scores)),
            "micro_response_hard_mean": _mean(all_scores), **_aggregate(task_means, tasks),
            "missingness": {name: counts[name] for name in (
                "missing_row", "target_api_error", "execution_unavailable", "missing_hard", "unusable_populated_hard")},
            "format_ok": {"observed": len(format_values), "passes": int(sum(format_values)), "rate": _mean(format_values)},
            "public_ok": {"observed": len(public_values), "passes": int(sum(public_values)), "rate": _mean(public_values)},
            "repeat_instability": {"tasks_with_at_least_two_observed_repeats": len(eligible),
                "tasks_with_mixed_success_and_failure": sum(row["mixed_success_and_failure"] for row in eligible),
                "mixed_task_fraction": _mean([float(row["mixed_success_and_failure"]) for row in eligible]),
                "mean_task_pairwise_disagreement": _mean([row["pairwise_replicate_disagreement"] for row in eligible]),
                "interpretation": "Observed same-task serving variability; not independent training-seed variability."},
            "full_expected_matrix_missingness_bounds": {
                "lower_macro_family_mean": _aggregate(lower, tasks)["macro_family_mean"],
                "upper_macro_family_mean": _aggregate(upper, tasks)["macro_family_mean"],
                "not_confidence_interval": True}, "tasks": task_records}


def _bootstrap(family_means: Mapping[str, float], draws: int, seed: int, margin: float, complete: bool):
    values = np.array(list(family_means.values()), dtype=float)
    result = {"method": "whole-family percentile bootstrap of task-mean paired effects",
              "n_clusters": len(values), "draws": draws, "seed": seed, "few_cluster_warning": len(values) <= 4,
              "ci95": None, "ci90": None, "equivalence_margin": margin,
              "equivalence_interval_inside_margin": False, "exploratory_compatible_with_margin": False,
              "established_equivalence": False, "independent_replication_required": True,
              "missing_pairs_present": not complete,
              "limits": "Clusters are selected families. Few-cluster percentile coverage is not assured; degenerate intervals can be misleading."}
    if len(values) < 2:
        result["status"] = "insufficient_family_clusters"
        return result
    rng = np.random.default_rng(seed)
    samples = values[rng.integers(0, len(values), size=(draws, len(values)))].mean(axis=1)
    result.update(status="exploratory", ci95=np.quantile(samples, [.025, .975]).tolist(),
                  ci90=np.quantile(samples, [.05, .95]).tolist(),
                  bootstrap_distribution_degenerate=bool(np.ptp(samples) <= 1e-12))
    low, high = result["ci90"]
    inside = bool(low > -margin and high < margin)
    result.update(equivalence_interval_inside_margin=inside,
                  exploratory_compatible_with_margin=inside and complete)
    return result


def _contrast(tasks, indexed, candidate, reference, priority, repeats, draws, seed, margin):
    task_values, pair_deltas, details, missing, replicate_values = {}, [], [], [], {r: {} for r in repeats}
    lower, upper = {}, {}
    for identity, task in tasks.items():
        deltas, valid_repeats, bound_low, bound_high = [], [], [], []
        for repeat in repeats:
            left = indexed.get((identity, candidate, repeat))
            right = indexed.get((identity, reference, repeat))
            lv, rv = _outcome(left), _outcome(right)
            bound_low.append((lv if lv is not None else 0) - (rv if rv is not None else 1))
            bound_high.append((lv if lv is not None else 1) - (rv if rv is not None else 0))
            if lv is None or rv is None:
                missing.append({"id": identity, "family": task["family"], "repeat": repeat,
                                "candidate_status": _reason(left), "reference_status": _reason(right)})
                continue
            delta = lv - rv
            deltas.append(delta)
            valid_repeats.append(repeat)
            replicate_values[repeat][identity] = delta
        lower[identity], upper[identity] = float(np.mean(bound_low)), float(np.mean(bound_high))
        if deltas:
            task_values[identity] = float(np.mean(deltas))
            pair_deltas.extend(deltas)
        details.append({"id": identity, "family": task["family"], "n_matched_repeats": len(deltas),
                        "matched_repeats": valid_repeats, "paired_repeat_deltas": deltas,
                        "task_mean_delta": _mean(deltas),
                        "repeat_sign_changes": bool(any(d > 0 for d in deltas) and any(d < 0 for d in deltas))})
    aggregate = _aggregate(task_values, tasks)
    family_bootstrap = _bootstrap(aggregate["family_means"], draws, seed, margin, not missing)
    replicate_stats = [{"repeat": repeat, **_aggregate(values, tasks)} for repeat, values in replicate_values.items()]
    replicate_effects = [item["macro_family_mean"] for item in replicate_stats if item["macro_family_mean"] is not None]
    return {"candidate": candidate, "reference": reference, "priority": priority, "exploratory": True,
            "effect_direction": "candidate minus reference; positive means candidate has higher hard success",
            "n_expected_pairs": len(tasks) * len(repeats), "n_matched_pairs": len(pair_deltas),
            "n_missing_pairs": len(missing), "missing_pairs": missing,
            "primary_macro_family_delta": aggregate["macro_family_mean"],
            "micro_task_delta": aggregate["micro_task_mean"], "micro_response_delta": _mean(pair_deltas),
            "n_observed_tasks": aggregate["n_observed_tasks"], "family_deltas": aggregate["family_means"],
            "task_discordance": {"wins": sum(d > 1e-12 for d in task_values.values()),
                                 "losses": sum(d < -1e-12 for d in task_values.values()),
                                 "ties": sum(abs(d) <= 1e-12 for d in task_values.values()),
                                 "unavailable_tasks": len(tasks) - len(task_values)},
            "response_pair_discordance": {"wins": sum(d > 0 for d in pair_deltas),
                                          "losses": sum(d < 0 for d in pair_deltas),
                                          "ties": sum(d == 0 for d in pair_deltas)},
            "family_cluster_bootstrap": family_bootstrap, "per_global_replicate": replicate_stats,
            "replicate_effect_range": [min(replicate_effects), max(replicate_effects)] if replicate_effects else None,
            "replicate_effect_sample_sd": float(np.std(replicate_effects, ddof=1)) if len(replicate_effects) >= 2 else None,
            "full_expected_matrix_missingness_bounds": {
                "lower_macro_family_delta": _aggregate(lower, tasks)["macro_family_mean"],
                "upper_macro_family_delta": _aggregate(upper, tasks)["macro_family_mean"],
                "not_confidence_interval": True,
                "meaning": "Worst-case binary outcomes only for missing entries, keeping observed values; no population sampling guarantee."},
            "tasks": details}


def _distribution(values: np.ndarray):
    return {"positive_fraction": float(np.mean(values > 1e-12)),
            "zero_fraction": float(np.mean(np.abs(values) <= 1e-12)),
            "negative_fraction": float(np.mean(values < -1e-12)),
            "percentiles": {str(q): float(np.percentile(values, q)) for q in (2.5, 5, 50, 95, 97.5)}}


def _subsampling(tasks, indexed, arms, repeats, candidate, reference, sizes, draws, seed):
    pool = [identity for identity in tasks
            if all(_reason(indexed.get((identity, arm, repeat))) == "observable" for arm in arms for repeat in repeats)]
    deltas = {identity: float(np.mean([float(indexed[identity, candidate, repeat]["hard"])
                                      - float(indexed[identity, reference, repeat]["hard"]) for repeat in repeats]))
              for identity in pool}
    entries = {}
    for size in sizes:
        item = {"tasks_per_draw": size, "draws": draws, "seed": _seed(seed, f"M={size}"),
                "without_replacement_within_draw": True}
        if size > len(pool):
            entries[str(size)] = {**item, "status": "insufficient_complete_tasks", "draws_executed": 0}
            continue
        rng = np.random.default_rng(item["seed"])
        macro, micro, family_counts = [], [], []
        for _ in range(draws):
            chosen = rng.choice(pool, size=size, replace=False).tolist()
            aggregate = _aggregate({identity: deltas[identity] for identity in chosen}, tasks)
            macro.append(aggregate["macro_family_mean"])
            micro.append(aggregate["micro_task_mean"])
            family_counts.append(aggregate["n_observed_families"])
        entries[str(size)] = {**item, "status": "conditional_resampling_diagnostic", "draws_executed": draws,
                             "macro_family_delta": _distribution(np.array(macro)),
                             "micro_task_delta": _distribution(np.array(micro)),
                             "families_per_draw_min_max": [min(family_counts), max(family_counts)]}
    return {"pool_task_count": len(pool), "pool_task_ids": pool, "excluded_incomplete_task_count": len(tasks) - len(pool),
            "complete_matrix_rule": "Every expected arm and repeat must have observable hard outcome for the sampled task.",
            "sizes": entries, "not_new_evidence": True,
            "interpretation": "Sign frequencies describe subsets of this fixed observed matrix, not probabilities of a true benefit.",
            "family_mix_caveat": "Small task subsets may omit families; each draw averages equally over its represented families."}


def analyze(rows: Iterable[Mapping[str, Any]], *, task_manifest: Iterable[Mapping[str, Any]] | None = None,
            expected_arms: Sequence[str] = ARMS, expected_repeats: Sequence[int] = REPEATS,
            bootstrap_draws: int = 10_000, bootstrap_seed: int = 20260908, equivalence_margin: float = .10,
            subsample_draws: int = 2000, subsample_seed: int = 20260909,
            subsample_sizes: Sequence[int] = (5, 10, 20, 32)) -> dict[str, Any]:
    """Analyze solver rows; pass all 32 manifest entries to expose wholly absent tasks.

    Native hard outcomes are binary; missing outcomes remain missing. Defaults
    implement the preregistered 3-arm/4-repeat pilot. Sizes exceeding a split's
    complete task pool are reported unavailable rather than sampled with replacement.
    """
    arms, repeats, sizes = tuple(expected_arms), tuple(expected_repeats), tuple(subsample_sizes)
    if len(arms) != len(set(arms)) or set(arms) != set(ARMS):
        raise ValueError("The scale audit requires exactly the three frozen solver arms")
    if not repeats or any(type(r) is not int or r < 0 for r in repeats) or len(set(repeats)) != len(repeats):
        raise ValueError("Expected repeats must be unique nonnegative integers")
    if any(type(n) is not int or n < 1 for n in (bootstrap_draws, subsample_draws)):
        raise ValueError("Resampling counts must be positive integers")
    if any(type(n) is not int or n < 1 for n in sizes) or len(set(sizes)) != len(sizes):
        raise ValueError("Subsampling sizes must be unique positive task counts")
    if not isinstance(equivalence_margin, (float, int)) or isinstance(equivalence_margin, bool) or not 0 < equivalence_margin <= 1:
        raise ValueError("Predeclared equivalence margin must be in (0,1]")
    if any(type(seed) is not int or seed < 0 for seed in (bootstrap_seed, subsample_seed)):
        raise ValueError("Resampling seeds must be nonnegative integers")
    tasks, indexed, manifest_supplied = _index(rows, task_manifest, arms, repeats)
    request_counts = Counter(row["request_hash"] for row in indexed.values())
    reused_requests = {key: count for key, count in sorted(request_counts.items()) if count > 1}
    reports = {}
    for split in ("dev", "holdout", "all"):
        subset = {identity: task for identity, task in tasks.items() if split == "all" or task["split"] == split}
        report = {"n_expected_tasks": len(subset), "n_family_clusters": len({task["family"] for task in subset.values()}),
                  "n_expected_responses": len(subset) * len(arms) * len(repeats),
                  "arms": {arm: _arm_summary(subset, indexed, arm, repeats) for arm in arms}, "contrasts": {}}
        for candidate, reference, priority in CONTRASTS:
            name = candidate + "_vs_" + reference
            contrast = _contrast(subset, indexed, candidate, reference, priority, repeats,
                                 bootstrap_draws, _seed(bootstrap_seed, split), equivalence_margin)
            contrast["task_batch_subsampling"] = _subsampling(
                subset, indexed, arms, repeats, candidate, reference, sizes,
                subsample_draws, _seed(subsample_seed, split))
            report["contrasts"][name] = contrast
        reports[split] = report
    return {"version": "validator-scale-analysis-v1", "exploratory": True,
            "design": {"expected_arms": list(arms), "expected_repeats": list(repeats),
                       "task_manifest_supplied": manifest_supplied, "n_expected_tasks": len(tasks),
                       "n_family_clusters": len({task["family"] for task in tasks.values()}),
                       "n_observed_rows": len(indexed), "n_expected_rows": len(tasks) * len(arms) * len(repeats),
                       "n_distinct_request_hashes": len(request_counts),
                       "reused_request_hash_counts": reused_requests,
                       "fresh_call_provenance_warning": bool(reused_requests),
                       "bootstrap_draws": bootstrap_draws, "bootstrap_seed": bootstrap_seed,
                       "subsample_draws": subsample_draws, "subsample_seed": subsample_seed,
                       "equivalence_margin": equivalence_margin,
                       "absence_limit": None if manifest_supplied else "Wholly absent tasks cannot be detected without a manifest."},
            "splits": reports, "limitations": LIMITATIONS, "references": REFERENCES}
