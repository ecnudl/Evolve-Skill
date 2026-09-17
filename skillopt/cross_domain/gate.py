"""Pure, conservative screening for a *fixed* cross-domain skill policy.

This experimental gate does not change SkillOpt's original validation gate.
Intervals use Wilson marginal bounds, not a formal sequential/family-wise safety
guarantee. In particular, repeated candidate selection and distribution shift
are not covered. A small, all-tied sample is insufficient evidence of safety.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from math import comb, isfinite, sqrt
from numbers import Real
from statistics import NormalDist
from typing import Any

_REFERENCES = ("baseline", "current")
_DEFAULTS: dict[str, Any] = {
    "confidence": 0.95,
    "min_group_n": 16,
    "min_positive_gain": 0.0,
    "gain_test": "exact_paired",
    "noninferiority_margin": 0.05,
    "max_conditional_harm": 0.10,
    "source_groups": ["source", "local"],
    "positive_groups": ["positive"],
    "source_domains": [],
    "required_protected_groups": ["nearmiss", "unrelated"],
    "min_positive_domains": 1,
    "local_already_committed": False,
    "expected_cells": [],
}
_LIMITATIONS = [
    "Wilson intervals are approximate fixed-sample screening intervals, not formal safety guarantees.",
    "The win-minus-loss interval uses Bonferroni-adjusted marginal Wilson bounds within one comparison only.",
    "No multiplicity correction across cells, references, candidates, or repeated looks is applied.",
    "Results concern the supplied fixed policy and sampled domains; unseen-domain safety is not established.",
    "Rows must be independent task-level observations, not correlated reruns counted as independent tasks.",
    "Structural identity relies on explicit caller-provided policy contracts; it does not bound unseen router false activations.",
]


def _group_name(value: str) -> str:
    return "nearmiss" if value in {"near_miss", "near-miss"} else value


def _validate_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated = []
    seen: set[str] = set()
    for raw in rows:
        row = dict(raw)
        for field in ("id", "domain", "mechanism", "group"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Each row needs a nonempty string {field!r}")
        if row["id"] in seen:
            raise ValueError(f"Duplicate task id: {row['id']!r}")
        seen.add(row["id"])
        for field in (*_REFERENCES, "candidate"):
            value = row.get(field)
            if not isinstance(value, Real) or not isfinite(value) or value not in (0, 1):
                raise ValueError(f"Task {row['id']!r}: {field} must be a finite binary score")
            row[field] = int(value)
        for field in ("candidate", "current"):
            marker = f"{field}_is_baseline"
            if marker in row and not isinstance(row[marker], bool):
                raise ValueError(f"{marker} must be an explicit boolean policy-identity contract")
            if row.get(marker) is True and row[field] != row["baseline"]:
                raise ValueError(f"Task {row['id']!r}: {marker} contradicts paired scores")
        if row.get("candidate_is_baseline") is True and "applied" in row and row["applied"] is not False:
            raise ValueError(f"Task {row['id']!r}: baseline identity contradicts skill application")
        row["group"] = _group_name(row["group"])
        validated.append(row)
    return validated


def _wilson(successes: int, n: int, confidence: float) -> list[float]:
    if not n:
        return [0.0, 1.0]
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _check_confidence(confidence: float) -> None:
    if not isinstance(confidence, Real) or not isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence must be finite and strictly between 0 and 1")


def pair_stats(rows: Iterable[Mapping[str, Any]], *, confidence: float = 0.95) -> dict[str, Any]:
    """Summarize paired binary outcomes against both baseline and current policy.

    ``rows`` contain id/domain/mechanism/group and baseline/current/candidate.
    Conditional harm is P(candidate wrong | reference correct), not the average
    score delta. When no reference answer was correct, its interval is [0, 1]
    and its rate is None; absence of such observations does not establish safety.
    """
    _check_confidence(confidence)
    records = _validate_rows(rows)
    n = len(records)
    comparisons = {}
    for reference in _REFERENCES:
        wins = [r["id"] for r in records if r[reference] == 0 and r["candidate"] == 1]
        losses = [r["id"] for r in records if r[reference] == 1 and r["candidate"] == 0]
        reference_correct = sum(r[reference] for r in records)
        # Two marginal intervals each receive half of alpha. Their difference
        # uses the same paired outcomes; no independence of wins/losses is assumed.
        marginal_confidence = 1 - (1 - confidence) / 2
        win_interval = _wilson(len(wins), n, marginal_confidence)
        loss_interval = _wilson(len(losses), n, marginal_confidence)
        structural_identity = bool(records) and all(
            r.get("candidate_is_baseline") is True
            and (reference == "baseline" or r.get("current_is_baseline") is True)
            for r in records
        )
        comparisons[reference] = {
            "wins": len(wins),
            "losses": len(losses),
            "ties": n - len(wins) - len(losses),
            "delta": (len(wins) - len(losses)) / n if n else None,
            "exact_paired_p": sum(comb(len(wins) + len(losses), k) for k in range(len(wins), len(wins) + len(losses) + 1)) / (2 ** (len(wins) + len(losses))),
            "delta_interval": [win_interval[0] - loss_interval[1], win_interval[1] - loss_interval[0]],
            "win_interval": win_interval,
            "loss_interval": loss_interval,
            "reference_correct": reference_correct,
            "conditional_harm": len(losses) / reference_correct if reference_correct else None,
            "conditional_harm_interval": _wilson(len(losses), reference_correct, confidence),
            "improved_ids": sorted(wins),
            "counterexample_ids": sorted(losses),
            "structural_identity": structural_identity,
        }
        if structural_identity:
            comparisons[reference].update({
                "delta_interval": [0.0, 0.0], "win_interval": [0.0, 0.0],
                "loss_interval": [0.0, 0.0], "conditional_harm": 0.0,
                "conditional_harm_interval": [0.0, 0.0],
            })
    return {
        "n": n,
        "rates": {key: sum(r[key] for r in records) / n if n else None for key in (*_REFERENCES, "candidate")},
        "confidence": confidence,
        "comparisons": comparisons,
        "counterexample_ids": sorted({task_id for value in comparisons.values() for task_id in value["counterexample_ids"]}),
    }


def _config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    result = dict(_DEFAULTS)
    supplied = dict(config or {})
    unknown = supplied.keys() - _DEFAULTS.keys()
    if unknown:
        raise ValueError(f"Unknown gate settings: {sorted(unknown)}")
    result.update(supplied)
    _check_confidence(result["confidence"])
    if result["gain_test"] not in {"exact_paired", "conservative_interval"}:
        raise ValueError("gain_test must be exact_paired or conservative_interval")
    for key in ("min_group_n", "min_positive_domains"):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    for key in ("min_positive_gain", "noninferiority_margin", "max_conditional_harm"):
        value = result[key]
        if not isinstance(value, Real) or not isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be finite and between 0 and 1")
    for key in ("source_groups", "positive_groups", "source_domains", "required_protected_groups"):
        values = result[key]
        if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"{key} must be a list of nonempty strings")
        result[key] = [_group_name(v) for v in values] if key.endswith("groups") else list(values)
    if set(result["source_groups"]) & set(result["positive_groups"]):
        raise ValueError("source_groups and positive_groups must be disjoint")
    if set(result["required_protected_groups"]) & (set(result["source_groups"]) | set(result["positive_groups"])):
        raise ValueError("required_protected_groups cannot contain source or positive groups")
    if not isinstance(result["local_already_committed"], bool):
        raise ValueError("local_already_committed must be a boolean")
    if not isinstance(result["expected_cells"], (list, tuple)):
        raise ValueError("expected_cells must be a list of group/domain/mechanism mappings")
    for cell in result["expected_cells"]:
        if not isinstance(cell, Mapping) or any(not isinstance(cell.get(k), str) or not cell[k].strip() for k in ("group", "domain", "mechanism")):
            raise ValueError("expected_cells must contain group/domain/mechanism strings")
    return result


def _cell_status(stats: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, str]:
    """Attach separate gain, noninferiority and harm checks for both references."""
    safety_states, gain_states = [], []
    for comparison in stats["comparisons"].values():
        low, high = comparison["delta_interval"]
        harm_low, harm_high = comparison["conditional_harm_interval"]
        enough = stats["n"] >= cfg["min_group_n"]
        ni = "pass" if enough and low >= -cfg["noninferiority_margin"] else "pending"
        if enough and high < -cfg["noninferiority_margin"]:
            ni = "fail"
        harm = "pass" if enough and harm_high <= cfg["max_conditional_harm"] else "pending"
        if enough and comparison["reference_correct"] and harm_low > cfg["max_conditional_harm"]:
            harm = "fail"
        if comparison["structural_identity"]:
            # Identity is a pre-execution policy contract, not inferred from ties.
            ni = harm = "pass"
        gain = "pass" if enough and low > cfg["min_positive_gain"] else "pending"
        if enough and high <= cfg["min_positive_gain"]:
            gain = "fail"
        if cfg["gain_test"] == "exact_paired":
            # One-sided exact sign test on discordant pairs tests zero net
            # improvement, not a nonzero minimum-effect null. The minimum effect
            # below is an additional observed-effect threshold, not a CI claim.
            if (enough and comparison["delta"] > 0
                    and comparison["delta"] >= cfg["min_positive_gain"]
                    and comparison["exact_paired_p"] <= 1 - cfg["confidence"]):
                gain = "pass"
        safety = "fail" if "fail" in (ni, harm) else "pass" if ni == harm == "pass" else "pending"
        comparison["checks"] = {"noninferiority": ni, "conditional_harm": harm, "gain": gain, "safety": safety}
        safety_states.append(safety)
        gain_states.append(gain)
    safety = "fail" if "fail" in safety_states else "pass" if all(s == "pass" for s in safety_states) else "pending"
    gain = "fail" if "fail" in gain_states else "pass" if all(s == "pass" for s in gain_states) else "pending"
    return safety, gain


def decide_scope(rows: Iterable[Mapping[str, Any]], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Decide a scope action without executing models, changing skills or routing.

    Safety is checked separately in every (group, domain, mechanism) cell against
    BOTH baseline and current. Positive cells default to a one-sided exact paired
    test against zero gain, plus an observed minimum-effect threshold; optionally
    use ``gain_test='conservative_interval'`` to require a positive lower bound.
    ``source_domains`` marks positive cells
    from the source domain as local evidence. ``expected_cells`` can preregister
    the full validation matrix; missing cells block expansion. ``restrict`` is a
    request to revise/revalidate the router, not automatic approval of a new one.
    ``local_already_committed`` applies only to an unchanged, previously validated
    skill version, never to an unvalidated content update.
    Explicit ``candidate_is_baseline``/``current_is_baseline`` flags assert that
    the caller reused the identical base policy before any skill injection. Both
    flags are needed for structural identity against current; matching scores
    alone never suffice. The caller must validate the routing contract separately.
    """
    cfg = _config(config)
    records = _validate_rows(rows)
    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        cells[(row["group"], row["domain"], row["mechanism"])].append(row)
    source_domains = set(cfg["source_domains"])
    source_domains.update(domain for group, domain, _ in cells if group in cfg["source_groups"])
    audits = []
    for (group, domain, mechanism), values in sorted(cells.items()):
        role = "protected"
        if group in cfg["source_groups"] or (group in cfg["positive_groups"] and domain in source_domains):
            role = "local"
        elif group in cfg["positive_groups"]:
            role = "positive"
        stats = pair_stats(values, confidence=cfg["confidence"])
        safety, gain = _cell_status(stats, cfg)
        audits.append({"group": group, "domain": domain, "mechanism": mechanism, "role": role, "safety": safety, "gain": gain, **stats})
    local = [a for a in audits if a["role"] == "local"]
    positive = [a for a in audits if a["role"] == "positive"]
    protected = [a for a in audits if a["role"] == "protected"]
    missing = []
    for expected in cfg["expected_cells"]:
        cell = (_group_name(expected["group"]), expected["domain"], expected["mechanism"])
        if cell not in cells:
            missing.append({"group": cell[0], "domain": cell[1], "mechanism": cell[2]})
    # Require near-miss/unrelated coverage in each proposed activation domain.
    active_domains = {a["domain"] for a in local + positive}
    for domain in sorted(active_domains):
        for group in cfg["required_protected_groups"]:
            if not any(a["domain"] == domain and a["group"] == group for a in protected):
                missing.append({"group": group, "domain": domain, "mechanism": "*"})
    source_protected = [a for a in protected if a["domain"] in source_domains]
    local_harm = any(a["safety"] == "fail" for a in local + source_protected)
    local_pass = bool(local) and all(a["safety"] == a["gain"] == "pass" for a in local)
    local_pass = local_pass and all(a["safety"] == "pass" for a in source_protected)
    local_pass = local_pass and not any(m["domain"] in source_domains for m in missing)
    local_pass = not local_harm and (local_pass or (cfg["local_already_committed"] and not local))
    positive_pass = bool(positive) and all(a["safety"] == a["gain"] == "pass" for a in positive)
    enough_domains = len({a["domain"] for a in positive}) >= cfg["min_positive_domains"]
    protective_pass = bool(protected) and all(a["safety"] == "pass" for a in protected)
    expansion_harm = any(a["safety"] == "fail" for a in positive + protected)
    reasons = []
    if missing:
        reasons.append("missing_validation_cells")
    if not enough_domains:
        reasons.append("insufficient_cross_domain_coverage")
    if not local_pass:
        reasons.append("local_evidence_not_accepted")
    if not positive_pass:
        reasons.append("cross_domain_positive_gain_not_established")
    if not protective_pass:
        reasons.append("protected_cell_safety_not_established")
    if local_harm:
        action = "reject"
        reasons.append("source_scope_harm_detected")
    elif expansion_harm:
        # A prior local contract must not override pending/failed evidence for
        # a supplied source-scope update. ``local_pass`` handles the only valid
        # prior-only case (unchanged version, no new local rows) above.
        action = "restrict" if local_pass else "reject"
        reasons.append("proposed_scope_harm_detected")
    elif local_pass and positive_pass and protective_pass and enough_domains and not missing:
        action = "cross_domain_commit"
        reasons.append("all_preregistered_checks_passed")
    elif local_pass and local:
        action = "local_commit"
        reasons.append("only_source_scope_accepted")
    else:
        action = "pending"
        reasons.append("insufficient_evidence_keep_current_scope")
    return {
        "action": action,
        "reason_codes": reasons,
        "local_accepted": local_pass,
        "cross_domain_accepted": action == "cross_domain_commit",
        "group_audits": audits,
        "missing_cells": missing,
        "counterexample_ids": sorted({task_id for a in audits for task_id in a["counterexample_ids"]}),
        "config": cfg,
        "statistical_limitations": list(_LIMITATIONS),
    }
