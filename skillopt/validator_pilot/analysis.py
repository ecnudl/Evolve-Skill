"""Descriptive, paired verifier audits with explicit failure denominators.

Natural responses and controlled defects are never pooled into the main result.
An abstention, malformed judgment, API failure, or missing execution oracle is not
a correct rejection. Rates are descriptive pilot statistics, not evidence of
causality, longitudinal drift, or statistically established improvement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

DECISIONS = ("pass", "fail", "unknown")
ORIGINS = ("natural", "controlled")


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _hard(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    raise ValueError("hard must be bool, integer 0/1, or None")


def _key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return row["id"], row["skill_version"], row["repeat"], row["origin"]


def _validated(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for incoming in rows:
        if not isinstance(incoming, Mapping):
            raise TypeError("audit rows must be mappings")
        row = dict(incoming)
        for field in ("id", "skill_version", "request_hash"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"{field} must be a nonempty string")
        if type(row.get("repeat")) is not int or row["repeat"] < 0:
            raise ValueError("repeat must be a nonnegative integer")
        if row.get("origin") not in ORIGINS:
            raise ValueError("origin must be natural or controlled")
        for field in ("target_ok", "execution_ok", "judge_ok"):
            if type(row.get(field)) is not bool:
                raise ValueError(f"{field} must be an explicit boolean")
        if "hard" not in row:
            raise ValueError("hard must be explicit, using None for unavailable oracle")
        row["hard"] = _hard(row["hard"])
        for field, fallback in (("cluster_id", row["id"]), ("family", "unspecified"), ("split", "unspecified")):
            row.setdefault(field, fallback)
            if not isinstance(row[field], str) or not row[field]:
                raise ValueError(f"{field} must be a nonempty string")
        pair_key = _key(row)
        if pair_key in seen:
            raise ValueError("duplicate audit pairing key")
        seen.add(pair_key)
        output.append(row)
    return output


def _decision(row: Mapping[str, Any]) -> tuple[str, str | None]:
    if not row["judge_ok"]:
        return "unknown", "judge_api_error"
    judgment = row.get("judgment")
    if (not isinstance(judgment, Mapping) or judgment.get("schema_valid") is not True
            or judgment.get("decision") not in DECISIONS):
        return "unknown", "schema_error"
    decision = judgment["decision"]
    return decision, "declared_unknown" if decision == "unknown" else None


def _observable(row: Mapping[str, Any]) -> bool:
    return row["target_ok"] and row["execution_ok"] and row["hard"] is not None


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for row in rows:
        decision, reason = _decision(row)
        counts[f"effective_{decision}"] += 1
        if reason:
            counts[reason] += 1
        else:
            counts["valid_decisive"] += 1
        if row["judge_ok"] and reason != "schema_error":
            counts["schema_valid"] += 1
        counts["target_api_errors"] += not row["target_ok"]
        counts["execution_errors"] += row["target_ok"] and not row["execution_ok"]
        counts["missing_hard"] += row["hard"] is None
        counts["unusable_populated_hard"] += row["hard"] is not None and not _observable(row)
        if not _observable(row):
            counts["unobservable"] += 1
            continue
        counts["observable"] += 1
        truth = row["hard"]
        counts["hard_pass" if truth else "hard_fail"] += 1
        if decision == "unknown":
            counts["unknown_true" if truth else "unknown_false"] += 1
        elif decision == "pass":
            counts["TP" if truth else "FP"] += 1
        else:
            counts["FN" if truth else "TN"] += 1
    n = len(rows)
    observed = counts["observable"]
    passes = counts["TP"] + counts["FP"]
    decisive = passes + counts["TN"] + counts["FN"]
    result = {
        "n_tasks": len({row["id"] for row in rows}),
        "n_clusters": len({row["cluster_id"] for row in rows}),
        "n_responses": n,
        "n_observable": observed,
        "n_unobservable": counts["unobservable"],
        "hard_pass": counts["hard_pass"],
        "hard_fail": counts["hard_fail"],
        "hard_pass_rate": _rate(counts["hard_pass"], observed),
        **{key: counts[key] for key in ("TP", "TN", "FP", "FN", "unknown_true", "unknown_false")},
        "false_pass_rate": _rate(counts["FP"], counts["hard_fail"]),
        "pass_contamination": _rate(counts["FP"], passes),
        "true_pass_acceptance": _rate(counts["TP"], counts["hard_pass"]),
        "false_reject_rate": _rate(counts["FN"], counts["hard_pass"]),
        "decisive_coverage": _rate(decisive, observed),
        "schema_valid_count": counts["schema_valid"],
        "schema_valid_rate": _rate(counts["schema_valid"], n),
        "target_api_errors": counts["target_api_errors"],
        "execution_errors": counts["execution_errors"],
        "judge_api_errors": counts["judge_api_error"],
        "schema_errors": counts["schema_error"],
        "declared_unknown_count": counts["declared_unknown"],
        "missing_hard_count": counts["missing_hard"],
        "unusable_populated_hard_count": counts["unusable_populated_hard"],
        "effective_decisions_all_rows": {name: counts[f"effective_{name}"] for name in DECISIONS},
        "rate_denominators": {"hard_pass_rate": observed, "false_pass_rate": counts["hard_fail"],
                              "pass_contamination": passes, "true_pass_acceptance": counts["hard_pass"],
                              "false_reject_rate": counts["hard_pass"], "decisive_coverage": observed,
                              "schema_valid_rate": n},
    }
    assert observed == sum(result[key] for key in ("TP", "TN", "FP", "FN", "unknown_true", "unknown_false"))
    return result


def _origin_groups(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {origin: defaultdict(list) for origin in ORIGINS}
    for row in rows:
        groups[row["origin"]][row[field]].append(row)
    return {origin: {name: _metrics(values) for name, values in sorted(group.items())}
            for origin, group in groups.items()}


def summarize_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Report observed response-level rates; cluster counts disclose dependence."""
    values = _validated(rows)
    by_origin = {origin: _metrics([row for row in values if row["origin"] == origin]) for origin in ORIGINS}
    return {
        "main_origin": "natural",
        "main": by_origin["natural"],
        "by_origin": by_origin,
        "by_skill_version": _origin_groups(values, "skill_version"),
        "by_family": _origin_groups(values, "family"),
        "by_split": _origin_groups(values, "split"),
        "audit_totals": {"n_rows": len(values), "n_tasks": len({row["id"] for row in values}),
                         "n_clusters": len({row["cluster_id"] for row in values}),
                         "n_target_api_errors": sum(not row["target_ok"] for row in values),
                         "n_execution_errors": sum(row["target_ok"] and not row["execution_ok"] for row in values),
                         "n_judge_api_errors": sum(not row["judge_ok"] for row in values)},
        "limitations": ["Natural and controlled response rates are separate; controlled defects are not population risk estimates.",
                        "Rates count responses; repeats and variants may share tasks or clusters.",
                        "Unknown and schema/API errors are abstentions, never correct rejections.",
                        "Unavailable hard outcomes are reported, not treated as failed tasks.",
                        "Descriptive pilot results do not establish causality, drift, or significance."],
    }


def _paired_metrics(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    transitions = {truth: {f"{left}->{right}": 0 for left in DECISIONS for right in DECISIONS}
                   for truth in ("hard_pass", "hard_fail")}
    corrections = regressions = abstention_to_correct = correct_to_abstention = 0
    for left, right in pairs:
        if not _observable(left):
            continue
        ld, _ = _decision(left)
        rd, _ = _decision(right)
        truth = left["hard"]
        transitions["hard_pass" if truth else "hard_fail"][f"{ld}->{rd}"] += 1
        correct = "pass" if truth else "fail"
        wrong = "fail" if truth else "pass"
        corrections += ld == wrong and rd == correct
        regressions += ld == correct and rd == wrong
        abstention_to_correct += ld == "unknown" and rd == correct
        correct_to_abstention += ld == correct and rd == "unknown"
    left_metrics = _metrics([left for left, _ in pairs])
    right_metrics = _metrics([right for _, right in pairs])
    return {
        "n_pairs": len(pairs), "n_observable_pairs": left_metrics["n_observable"],
        "n_tasks": left_metrics["n_tasks"], "n_clusters": left_metrics["n_clusters"],
        "left": left_metrics, "right": right_metrics,
        "transitions": transitions,
        "decisive_corrections": corrections, "decisive_regressions": regressions,
        "corrected_false_passes": transitions["hard_fail"]["pass->fail"],
        "introduced_false_passes": transitions["hard_fail"]["fail->pass"],
        "false_pass_to_abstention": transitions["hard_fail"]["pass->unknown"],
        "abstention_to_false_pass": transitions["hard_fail"]["unknown->pass"],
        "corrected_false_rejections": transitions["hard_pass"]["fail->pass"],
        "introduced_false_rejections": transitions["hard_pass"]["pass->fail"],
        "abstention_to_correct": abstention_to_correct,
        "correct_to_abstention": correct_to_abstention,
        "net_decisive_corrections": corrections - regressions,
        "net_correct_decision_count": corrections - regressions + abstention_to_correct - correct_to_abstention,
    }


def compare_judges(left: Iterable[Mapping[str, Any]], right: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Strictly pair the same target response; request_hash is the TARGET hash.

    Caller must store judge request hashes separately. Disagreement about target
    execution, oracle truth, provenance, or task grouping is an error, not an
    observation to exclude. Unpaired records remain reported in full summaries.
    No model calls, resampling, significance test, or causal label is produced.
    """
    lv, rv = _validated(left), _validated(right)
    lm, rm = {_key(row): row for row in lv}, {_key(row): row for row in rv}
    common = sorted(lm.keys() & rm.keys())
    pairs = []
    for key in common:
        lrow, rrow = lm[key], rm[key]
        for field in ("hard", "request_hash", "target_ok", "execution_ok", "cluster_id", "family", "split"):
            if lrow[field] != rrow[field]:
                raise ValueError(f"paired target evidence mismatch: {field}")
        pairs.append((lrow, rrow))
    by_origin = {origin: _paired_metrics([pair for pair in pairs if pair[0]["origin"] == origin]) for origin in ORIGINS}
    by_skill: dict[str, dict[str, Any]] = {}
    for origin in ORIGINS:
        versions = sorted({pair[0]["skill_version"] for pair in pairs if pair[0]["origin"] == origin})
        by_skill[origin] = {version: _paired_metrics([pair for pair in pairs if pair[0]["origin"] == origin
                                                    and pair[0]["skill_version"] == version]) for version in versions}
    return {
        "main_origin": "natural", "main": by_origin["natural"], "by_origin": by_origin,
        "by_skill_version": by_skill, "n_pairs": len(pairs),
        "left_only_count": len(lm.keys() - rm.keys()), "right_only_count": len(rm.keys() - lm.keys()),
        "left_only_keys": [list(key) for key in sorted(lm.keys() - rm.keys())],
        "right_only_keys": [list(key) for key in sorted(rm.keys() - lm.keys())],
        "left_all_rows": summarize_rows(lv), "right_all_rows": summarize_rows(rv),
        "limitations": ["Paired metrics use shared target responses only; unmatched rows remain in all-row summaries.",
                        "Corrections mean wrong decisive judgments became correct decisive judgments; abstention changes are separate.",
                        "Natural and controlled observations are not pooled into the main result.",
                        "No confidence intervals or significance claims; repeats/mutants are not independent task samples."],
    }
