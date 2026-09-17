"""Descriptive cross-domain score portfolios, independent of frozen experiments.

Inputs must ALREADY follow a preregistered, higher-is-better normalization to
[0, 1]. Merely dividing incompatible benchmark units by a constant does not make
them comparable. If a domain contains several benchmarks, first use a declared
within-domain aggregation, then pass ONE score triple for that domain here.

No missing-value imputation, confidence intervals, statistical risk estimates,
safety thresholds, candidate selection or execution takes place in this module.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from numbers import Real

METHODS = ("baseline", "reference", "candidate")
COMPARISONS = ("reference", "candidate")


def _mapping(value, label):
    """Detect duplicates still present in a Mapping's item stream.

    Duplicate literal/JSON keys already overwritten by a caller's dict cannot
    be recovered; ingestion must reject them before dict construction.
    """
    if not isinstance(value, Mapping):
        raise ValueError(label + " must be a mapping")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or key != key.strip():
            raise ValueError(label + " keys must be nonempty canonical strings")
        if key in result:
            raise ValueError("duplicate key in " + label)
        result[key] = item
    return result


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(label + " must be a real number, not bool or missing data")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(label + " must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(label + " must be finite")
    return number


def _sources(source_domains, domains):
    if isinstance(source_domains, (str, bytes, Mapping)) or not isinstance(source_domains, Iterable):
        raise ValueError("source_domains must be an explicit iterable of distinct domain names")
    result = []
    for domain in source_domains:
        if not isinstance(domain, str) or domain not in domains:
            raise ValueError("source_domains contains an unknown domain")
        if domain in result:
            raise ValueError("duplicate source domain")
        result.append(domain)
    return sorted(result)


def summarize_portfolio(
    scores: Mapping[str, Mapping[str, float]],
    *,
    source_domains=(),
    weights=None,
) -> dict:
    """Summarize complete paired domain scores without changing their meaning.

    Each domain has exactly baseline/reference/candidate in [0,1]. Default
    weighting is equal DOMAIN weight, irrespective of benchmark/task counts.
    Explicit weights must exactly cover the domains, be finite and strictly
    positive, and sum to one within 1e-12 floating-point validation tolerance.
    Arbitrary ratios are NOT rescaled; preregistration is the caller's duty.

    macro_gain is the weighted absolute score-point difference from baseline,
    NOT percentage relative improvement or relative error reduction. Negative
    transfer fraction is an UNWEIGHTED fraction of supplied domains with strict
    score decrease, not a probability of future harm. No safety epsilon is used.

    Source retention is calculated only for explicitly named source domains as
    (candidate-baseline)/(reference-baseline), without clipping to [0,1]. A
    nonpositive reference gain has no defined retention ratio. Numerically
    unrepresentable ratios also return None with an explicit explanation.
    """
    supplied = _mapping(scores, "scores")
    if not supplied:
        raise ValueError("scores must contain at least one complete domain")
    domains = sorted(supplied)
    validated = {}
    for domain in domains:
        row = _mapping(supplied[domain], "scores[" + domain + "]")
        if set(row) != set(METHODS):
            raise ValueError("every domain requires exactly baseline/reference/candidate; no missing-score filling")
        values = {method: _finite_number(row[method], domain + "/" + method) for method in METHODS}
        if any(not 0 <= value <= 1 for value in values.values()):
            raise ValueError("scores must already be higher-is-better normalized values in [0,1]")
        validated[domain] = values
    sources = _sources(source_domains, set(domains))
    if weights is None:
        domain_weights = {domain: 1.0 / len(domains) for domain in domains}
        weighting_mode = "equal_domain"
    else:
        supplied_weights = _mapping(weights, "weights")
        if set(supplied_weights) != set(domains):
            raise ValueError("explicit weights must cover exactly the supplied domains")
        domain_weights = {domain: _finite_number(supplied_weights[domain], "weight/" + domain) for domain in domains}
        if any(not 0 < value <= 1 for value in domain_weights.values()):
            raise ValueError("explicit domain weights must satisfy 0 < weight <= 1")
        if not math.isclose(math.fsum(domain_weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("explicit domain weights must sum to 1; arbitrary ratios are not normalized")
        weighting_mode = "explicit_weights"

    def weighted(values):
        return math.fsum(domain_weights[domain] * values[domain] for domain in domains)

    deltas = {
        method: {domain: validated[domain][method] - validated[domain]["baseline"] for domain in domains}
        for method in COMPARISONS
    }
    tradeoffs = {domain: validated[domain]["candidate"] - validated[domain]["reference"] for domain in domains}
    source_retention = {}
    for domain in sources:
        reference_gain = deltas["reference"][domain]
        candidate_gain = deltas["candidate"][domain]
        ratio, reason = None, None
        if reference_gain <= 0:
            reason = "undefined_nonpositive_reference_gain"
        else:
            ratio = candidate_gain / reference_gain
            if not math.isfinite(ratio):
                ratio, reason = None, "positive_reference_gain_but_ratio_not_finitely_representable"
        source_retention[domain] = {
            "candidate_gain": candidate_gain,
            "reference_gain": reference_gain,
            "retention": ratio,
            "reason": reason,
        }

    return {
        "version": "cross-domain-portfolio-descriptive-v1",
        "domains": domains,
        "n_domains": len(domains),
        "weighting": {
            "mode": weighting_mode,
            "weights": domain_weights,
            "explicit_weights_registration_verified": False,
            "weights_automatically_rescaled": False,
        },
        "per_domain": {
            domain: {
                "scores": validated[domain],
                "weight": domain_weights[domain],
                "delta_reference_vs_base": deltas["reference"][domain],
                "delta_candidate_vs_base": deltas["candidate"][domain],
                "delta_candidate_vs_reference": tradeoffs[domain],
            }
            for domain in domains
        },
        "macro_scores": {
            method: weighted({domain: validated[domain][method] for domain in domains}) for method in METHODS
        },
        "macro_gain": {method: weighted(deltas[method]) for method in COMPARISONS},
        "worst_domain_score": {method: min(validated[domain][method] for domain in domains) for method in METHODS},
        "worst_delta_vs_base": {method: min(deltas[method].values()) for method in COMPARISONS},
        "negative_transfer_domain_fraction": {
            method: sum(value < 0 for value in deltas[method].values()) / len(domains) for method in COMPARISONS
        },
        "negative_transfer_domains": {
            method: [domain for domain in domains if deltas[method][domain] < 0] for method in COMPARISONS
        },
        "macro_shortfall": {
            method: weighted({domain: max(0.0, -deltas[method][domain]) for domain in domains})
            for method in COMPARISONS
        },
        "max_regression_vs_base": {method: max(0.0, -min(deltas[method].values())) for method in COMPARISONS},
        "tradeoff_vs_reference": {
            "per_domain_delta": tradeoffs,
            "macro_delta": weighted(tradeoffs),
            "higher_domains": [domain for domain in domains if tradeoffs[domain] > 0],
            "lower_domains": [domain for domain in domains if tradeoffs[domain] < 0],
            "equal_domains": [domain for domain in domains if tradeoffs[domain] == 0],
            "max_regression": max(0.0, -min(tradeoffs.values())),
        },
        "source_domains": sources,
        "source_gain_retention": source_retention,
        "source_gain_retention_status": "explicit_sources_only" if sources else "not_requested_no_source_domains",
        "descriptive_only": True,
        "safety_certificate": False,
        "statistical_risk_estimate": False,
        "confidence_intervals_computed": False,
        "missing_scores_imputed": False,
        "interpretation": [
            "Scores require a predefined, same-direction, meaningfully comparable normalization; incompatible raw benchmark units cannot be aggregated directly.",
            "Provide one triple per domain after a predefined within-domain benchmark aggregation; extra benchmarks must not silently increase a domain's weight.",
            "Macro gains and shortfalls are normalized score-point differences, not percentage relative improvements.",
            "Negative-transfer domain fraction is an unweighted descriptive fraction of the supplied domains, not an estimated probability of future harm.",
            "Zero observed regression and good portfolio scores are not safety, generalization or statistical superiority certificates.",
            "Source gain retention has no definition when reference-minus-baseline is nonpositive; values above one or below zero are not clipped.",
            "Explicit weights must be fixed before inspecting outcomes; this pure function cannot verify preregistration or experimental provenance.",
            "Illustrative numbers alone are not results from a real experiment; provenance must be supplied separately.",
        ],
    }
