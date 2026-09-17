"""Descriptive paired analysis of two complete co-evolution streams.

No API or filesystem access. Stream replications, repeated serving requests and
resampled families are not independent additional benchmark tasks. Final scores
are measured by the fixed hard oracle, never by an evolved validator's own score.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Mapping

import numpy as np

METADATA = ("id", "cluster_id", "family", "context", "mode")
ARMS = ("noskill", "fixed_validator", "evolving_validator")


def _mean(values):
    return float(np.mean(values)) if len(values) else None


def _reason(row):
    if row is None:
        return "missing_row"
    if not row["target_ok"]:
        return "target_api_error"
    if not row["execution_ok"]:
        return "execution_unavailable"
    if row["hard"] is None:
        return "missing_hard"
    return "observable"


def _score(row):
    return float(row["hard"]) if _reason(row) == "observable" else None


def _index(rows, manifest, arms, streams, repeats):
    tasks, indexed, cluster_families = {}, {}, {}
    for task in manifest:
        if not isinstance(task, Mapping):
            raise ValueError("Expected manifest entries must be mappings")
        meta = {key: task.get(key) for key in METADATA}
        if any(not isinstance(value, str) or not value.strip() for value in meta.values()):
            raise ValueError("Manifest requires nonempty id/cluster_id/family/context/mode strings")
        if meta["id"] in tasks:
            raise ValueError("Duplicate task in expected manifest")
        if meta["cluster_id"] in cluster_families and cluster_families[meta["cluster_id"]] != meta["family"]:
            raise ValueError("One cluster_id cannot represent inconsistent family labels")
        cluster_families[meta["cluster_id"]] = meta["family"]
        tasks[meta["id"]] = meta
    for incoming in rows:
        if not isinstance(incoming, Mapping):
            raise ValueError("Observed rows must be mappings")
        row = dict(incoming)
        if row.get("id") not in tasks or any(row.get(key) != tasks[row["id"]][key] for key in METADATA):
            raise ValueError("Observed task metadata differs from expected manifest")
        if row.get("arm") not in arms:
            raise ValueError("Unexpected final arm")
        if type(row.get("stream")) is not int or row["stream"] not in streams:
            raise ValueError("Unexpected evolution stream")
        if type(row.get("repeat")) is not int or row["repeat"] not in repeats:
            raise ValueError("Unexpected solver repeat")
        for key in ("target_ok", "execution_ok", "skill_active"):
            if type(row.get(key)) is not bool:
                raise ValueError(f"{key} must be an explicit bool")
        if "hard" not in row or (row["hard"] is not None and type(row["hard"]) is not bool):
            raise ValueError("hard must be an explicit bool or None")
        for key in ("skill_hash", "request_hash"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"{key} must be a nonempty string")
        identity = row["stream"], row["id"], row["arm"], row["repeat"]
        if identity in indexed:
            raise ValueError("Duplicate stream/task/arm/repeat row")
        indexed[identity] = row
    return dict(sorted(tasks.items())), indexed


def _aggregate(task_values, tasks):
    clusters = defaultdict(list)
    for identity, value in task_values.items():
        clusters[tasks[identity]["cluster_id"]].append(value)
    cluster_means = {key: _mean(value) for key, value in sorted(clusters.items())}
    return {"macro_cluster_mean": _mean(list(cluster_means.values())),
            "micro_task_mean": _mean(list(task_values.values())),
            "n_observed_tasks": len(task_values), "n_observed_clusters": len(cluster_means),
            "cluster_means": cluster_means}


def _combine(task_stream_means, tasks, streams):
    values, excluded = {}, []
    for identity in tasks:
        missing = [stream for stream in streams if (stream, identity) not in task_stream_means]
        if missing:
            excluded.append({"id": identity, "cluster_id": tasks[identity]["cluster_id"],
                             "unavailable_streams": missing})
        else:
            values[identity] = _mean([task_stream_means[stream, identity] for stream in streams])
    return {**_aggregate(values, tasks), "task_means": values,
            "tasks_excluded_missing_streams": excluded,
            "equal_stream_weighting": "Each task contributes only when every expected stream has at least one observable repeat; average stream-specific task means equally."}


def _arm(tasks, indexed, arm, streams, repeats):
    counts, observations, task_means, bounds_low, bounds_high = Counter(), [], {}, {}, {}
    stream_summaries, task_details = {}, []
    hashes = defaultdict(set)
    for stream in streams:
        stream_scores = []
        for identity, meta in tasks.items():
            scores, statuses, per_repeat = [], {}, {}
            for repeat in repeats:
                row = indexed.get((stream, identity, arm, repeat))
                reason = _reason(row)
                counts[reason] += 1
                statuses[str(repeat)] = reason
                value = _score(row)
                if value is not None:
                    scores.append(value)
                    per_repeat[str(repeat)] = bool(value)
                if row is not None:
                    counts["rows"] += 1
                    counts["skill_active"] += row["skill_active"]
                    counts["unusable_populated_hard"] += row["hard"] is not None and reason != "observable"
                    hashes[str(stream)].add(row["skill_hash"])
            if scores:
                task_means[stream, identity] = _mean(scores)
                stream_scores.extend(scores)
            bounds_low[stream, identity] = sum(scores) / len(repeats)
            bounds_high[stream, identity] = (sum(scores) + len(repeats) - len(scores)) / len(repeats)
            task_details.append({"stream": stream, "id": identity, "cluster_id": meta["cluster_id"],
                                 "n_observed_repeats": len(scores), "hard_mean": _mean(scores),
                                 "hard_passes": int(sum(scores)), "replicate_outcomes": per_repeat,
                                 "replicate_status": statuses,
                                 "hard_flip": bool(scores) and min(scores) != max(scores)})
        stream_summaries[str(stream)] = {**_aggregate({identity: value for (s, identity), value in task_means.items()
                                                    if s == stream}, tasks),
                                        "n_observable": len(stream_scores), "hard_passes": int(sum(stream_scores)),
                                        "hard_failures": len(stream_scores) - int(sum(stream_scores))}
        observations.extend(stream_scores)
    combined = _combine(task_means, tasks, streams)
    return {"n_expected_rows": len(tasks) * len(streams) * len(repeats), "n_rows": counts["rows"],
            "n_observable": len(observations), "hard_passes": int(sum(observations)),
            "hard_failures": len(observations) - int(sum(observations)),
            "micro_response_hard_mean": _mean(observations), **combined,
            "missingness": {key: counts[key] for key in ("missing_row", "target_api_error", "execution_unavailable",
                                                         "missing_hard", "unusable_populated_hard")},
            "skill_active_rows": counts["skill_active"],
            "skill_active_fraction": counts["skill_active"] / counts["rows"] if counts["rows"] else None,
            "skill_hashes_by_stream": {key: sorted(values) for key, values in sorted(hashes.items())},
            "per_stream": stream_summaries, "task_stream_details": task_details,
            "task_streams_with_hard_flips": sum(row["hard_flip"] for row in task_details),
            "full_expected_matrix_missingness_bounds": {
                "lower": _combine(bounds_low, tasks, streams)["macro_cluster_mean"],
                "upper": _combine(bounds_high, tasks, streams)["macro_cluster_mean"],
                "not_confidence_interval": True}}


def _bootstrap(cluster_means, draws, seed):
    values = np.asarray(list(cluster_means.values()), dtype=float)
    result = {"unit": "shared family cluster_id, keeping all task/stream/repeat observations together",
              "n_clusters": len(values), "draws": draws, "seed": seed, "ci95": None,
              "status": "insufficient_clusters", "exploratory": True,
              "equivalence_tested": False, "equivalence_established": False,
              "independent_stream_variance_established": False,
              "coverage_not_validated_for_author_selected_families": True}
    if len(values) >= 2:
        rng = np.random.default_rng(seed)
        sample = values[rng.integers(0, len(values), size=(draws, len(values)))].mean(axis=1)
        result.update(status="exploratory", ci95=np.quantile(sample, [.025, .975]).tolist(),
                      degenerate_distribution=bool(np.ptp(sample) <= 1e-12))
    return result


def _contrast(tasks, indexed, candidate, reference, priority, streams, repeats, draws, seed):
    task_means, paired, missing, bounds_low, bounds_high, task_details = {}, [], [], {}, {}, []
    repeat_means = {repeat: {} for repeat in repeats}
    for stream in streams:
        for identity, meta in tasks.items():
            differences, lower, upper, matched = [], [], [], []
            for repeat in repeats:
                left = indexed.get((stream, identity, candidate, repeat))
                right = indexed.get((stream, identity, reference, repeat))
                lv, rv = _score(left), _score(right)
                lower.append((lv if lv is not None else 0) - (rv if rv is not None else 1))
                upper.append((lv if lv is not None else 1) - (rv if rv is not None else 0))
                if lv is None or rv is None:
                    missing.append({"stream": stream, "id": identity, "cluster_id": meta["cluster_id"],
                                    "repeat": repeat, "candidate_status": _reason(left), "reference_status": _reason(right)})
                    continue
                delta = lv - rv
                differences.append(delta)
                matched.append(repeat)
                repeat_means[repeat][stream, identity] = delta
            if differences:
                task_means[stream, identity] = _mean(differences)
                paired.extend(differences)
            bounds_low[stream, identity], bounds_high[stream, identity] = _mean(lower), _mean(upper)
            task_details.append({"stream": stream, "id": identity, "cluster_id": meta["cluster_id"],
                                 "n_matched_repeats": len(differences), "matched_repeats": matched,
                                 "paired_repeat_deltas": differences, "task_mean_delta": _mean(differences)})
    combined = _combine(task_means, tasks, streams)
    per_stream = {}
    for stream in streams:
        values = {identity: value for (s, identity), value in task_means.items() if s == stream}
        per_stream[str(stream)] = {**_aggregate(values, tasks),
                                   "per_repeat": [{"repeat": repeat, **_aggregate({identity: value
                                        for (s, identity), value in repeat_means[repeat].items() if s == stream}, tasks)}
                                                  for repeat in repeats]}
    estimates = [item["macro_cluster_mean"] for item in per_stream.values() if item["macro_cluster_mean"] is not None]
    deltas = list(combined["task_means"].values())
    return {"candidate": candidate, "reference": reference, "priority": priority,
            "effect_direction": "candidate minus reference", "n_expected_pairs": len(tasks) * len(streams) * len(repeats),
            "n_matched_pairs": len(paired), "n_missing_pairs": len(missing), "missing_pairs": missing,
            "primary_macro_cluster_delta": combined["macro_cluster_mean"],
            "micro_task_delta": combined["micro_task_mean"], "micro_matched_response_delta": _mean(paired),
            "cluster_deltas": combined["cluster_means"], "n_joint_observed_tasks": combined["n_observed_tasks"],
            "tasks_excluded_missing_streams": combined["tasks_excluded_missing_streams"],
            "task_discordance": {"wins": sum(value > 1e-12 for value in deltas),
                                 "losses": sum(value < -1e-12 for value in deltas),
                                 "ties": sum(abs(value) <= 1e-12 for value in deltas),
                                 "unavailable_tasks": len(tasks) - len(deltas)},
            "per_stream": per_stream, "stream_effect_range": [min(estimates), max(estimates)] if estimates else None,
            "per_repeat": [{"repeat": repeat, **_combine(values, tasks, streams)} for repeat, values in repeat_means.items()],
            "family_cluster_bootstrap": _bootstrap(combined["cluster_means"], draws, seed) if draws else None,
            "full_expected_matrix_missingness_bounds": {
                "lower": _combine(bounds_low, tasks, streams)["macro_cluster_mean"],
                "upper": _combine(bounds_high, tasks, streams)["macro_cluster_mean"],
                "not_confidence_interval": True}, "task_stream_details": task_details}


def analyze(rows, *, task_manifest, expected_arms=ARMS, expected_streams=(0, 1), expected_repeats=(0, 1, 2),
            baseline_arm="noskill", fixed_arm="fixed_validator", evolving_arm="evolving_validator",
            bootstrap_draws=5000, bootstrap_seed=20260909):
    """Final frozen-policy comparison; all expected manifest tasks are required.

    Main joint estimates average matched repeats per task/stream, require both
    streams for that task, average streams equally, then average tasks within
    cluster_id and clusters equally. Missing outcomes never become failures.
    """
    arms, streams, repeats = tuple(expected_arms), tuple(expected_streams), tuple(expected_repeats)
    if (len(set(arms)) != len(arms) or any(not isinstance(arm, str) or not arm for arm in arms)
            or len({baseline_arm, fixed_arm, evolving_arm}) != 3
            or not {baseline_arm, fixed_arm, evolving_arm} <= set(arms)):
        raise ValueError("Expected arms must include distinct baseline/fixed/evolving policies")
    for values in (streams, repeats):
        if not values or any(type(value) is not int or value < 0 for value in values) or len(set(values)) != len(values):
            raise ValueError("Stream/repeat labels must be unique nonnegative integers")
    if type(bootstrap_draws) is not int or bootstrap_draws < 1 or type(bootstrap_seed) is not int or bootstrap_seed < 0:
        raise ValueError("Invalid bootstrap count or seed")
    tasks, indexed = _index(rows, task_manifest, arms, streams, repeats)

    def report(subset, bootstrap):
        return {"n_expected_tasks": len(subset), "n_expected_clusters": len({t["cluster_id"] for t in subset.values()}),
                "arms": {arm: _arm(subset, indexed, arm, streams, repeats) for arm in arms},
                "contrasts": {f"{evolving_arm}_vs_{reference}": _contrast(subset, indexed, evolving_arm, reference,
                               priority, streams, repeats, bootstrap_draws if bootstrap else None, bootstrap_seed)
                              for reference, priority in ((fixed_arm, "primary"), (baseline_arm, "secondary"))}}

    request_counts = Counter(row["request_hash"] for row in indexed.values())
    return {"version": "coevolution-paired-final-analysis-v1", "exploratory": True,
            "design": {"expected_arms": list(arms), "expected_streams": list(streams), "expected_repeats": list(repeats),
                       "n_expected_tasks": len(tasks), "n_expected_clusters": len({t["cluster_id"] for t in tasks.values()}),
                       "n_expected_rows": len(tasks) * len(arms) * len(streams) * len(repeats), "n_observed_rows": len(indexed),
                       "n_distinct_request_hashes": len(request_counts),
                       "reused_request_hash_counts": {key: count for key, count in sorted(request_counts.items()) if count > 1},
                       "bootstrap_draws": bootstrap_draws, "bootstrap_seed": bootstrap_seed},
            **report(tasks, True),
            **{f"by_{field}": {value: report({key: task for key, task in tasks.items() if task[field] == value}, False)
                                for value in sorted({task[field] for task in tasks.values()})} for field in ("context", "mode")},
            "limitations": ["Exploratory fixed-holdout comparison, not established superiority, equivalence or safety.",
                            "Two independent evolution histories do not establish between-run variance or independent generation seeds.",
                            "Repeated serving calls and shared final tasks are dependent; joint family bootstrap keeps all streams/repeats together.",
                            "Chosen family clusters are not necessarily a representative random sample; interval coverage is not validated.",
                            "Unavailable outcomes remain missing; joint estimates require both streams per task, and worst-case full-matrix bounds are separate.",
                            "Context/mode strata and secondary contrasts are descriptive, not multiplicity-adjusted confirmatory tests."]}
