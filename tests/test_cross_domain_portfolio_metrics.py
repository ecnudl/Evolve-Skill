"""Pure deterministic tests; the 60/70/70 example is illustrative, not a run."""

import json
import math
from collections.abc import Mapping
from copy import deepcopy

import pytest

from skillopt.cross_domain.portfolio_metrics import summarize_portfolio

ILLUSTRATIVE = {
    "coding": {"baseline": 0.60, "reference": 0.80, "candidate": 0.78},
    "research": {"baseline": 0.70, "reference": 0.60, "candidate": 0.75},
    "spreadsheet": {"baseline": 0.70, "reference": 0.60, "candidate": 0.75},
}


def test_user_illustration_checks_all_core_portfolio_metrics():
    result = summarize_portfolio(ILLUSTRATIVE, source_domains=["coding"])
    assert result["weighting"]["mode"] == "equal_domain"
    assert result["weighting"]["weights"] == {domain: 1 / 3 for domain in ILLUSTRATIVE}
    assert result["macro_scores"] == pytest.approx({"baseline": 2 / 3, "reference": 2 / 3, "candidate": 0.76})
    assert result["macro_gain"] == pytest.approx({"reference": 0, "candidate": 0.28 / 3})
    assert result["worst_domain_score"] == pytest.approx({"baseline": 0.6, "reference": 0.6, "candidate": 0.75})
    assert result["worst_delta_vs_base"] == pytest.approx({"reference": -0.1, "candidate": 0.05})
    assert result["negative_transfer_domain_fraction"] == {"reference": 2 / 3, "candidate": 0}
    assert result["macro_shortfall"] == pytest.approx({"reference": 0.2 / 3, "candidate": 0})
    assert result["max_regression_vs_base"] == pytest.approx({"reference": 0.1, "candidate": 0})
    assert result["source_gain_retention"]["coding"]["retention"] == pytest.approx(0.9)
    assert result["tradeoff_vs_reference"]["per_domain_delta"] == pytest.approx(
        {"coding": -0.02, "research": 0.15, "spreadsheet": 0.15}
    )
    assert result["tradeoff_vs_reference"]["higher_domains"] == ["research", "spreadsheet"]
    assert result["tradeoff_vs_reference"]["lower_domains"] == ["coding"]
    assert result["tradeoff_vs_reference"]["max_regression"] == pytest.approx(0.02)
    json.dumps(result, allow_nan=False)


def test_explicit_weights_preserved_not_silently_renormalized():
    weights = {"coding": 0.5, "research": 0.3, "spreadsheet": 0.2}
    result = summarize_portfolio(ILLUSTRATIVE, weights=weights)
    assert result["weighting"] == {
        "mode": "explicit_weights",
        "weights": weights,
        "explicit_weights_registration_verified": False,
        "weights_automatically_rescaled": False,
    }
    assert result["macro_scores"] == pytest.approx({"baseline": 0.65, "reference": 0.7, "candidate": 0.765})
    assert result["macro_gain"] == pytest.approx({"reference": 0.05, "candidate": 0.115})
    assert result["macro_shortfall"] == pytest.approx({"reference": 0.05, "candidate": 0})
    # This is a fraction of domains, deliberately NOT the sum of their weights.
    assert result["negative_transfer_domain_fraction"]["reference"] == pytest.approx(2 / 3)


def test_shortfall_is_not_net_gain_and_does_not_cancel_regressions():
    scores = {
        "a": {"baseline": 0.4, "reference": 0.4, "candidate": 0.9},
        "b": {"baseline": 0.9, "reference": 0.9, "candidate": 0.8},
    }
    result = summarize_portfolio(scores)
    assert result["macro_gain"]["candidate"] == pytest.approx(0.2)
    assert result["macro_shortfall"]["candidate"] == pytest.approx(0.05)
    assert result["worst_delta_vs_base"]["candidate"] == pytest.approx(-0.1)
    assert result["max_regression_vs_base"]["candidate"] == pytest.approx(0.1)
    assert result["negative_transfer_domains"]["candidate"] == ["b"]


def test_source_retention_not_implicitly_selected_by_largest_source_gain():
    result = summarize_portfolio(ILLUSTRATIVE)
    assert result["source_domains"] == []
    assert result["source_gain_retention"] == {}
    assert result["source_gain_retention_status"] == "not_requested_no_source_domains"


@pytest.mark.parametrize("reference", [0.5, 0.4, 0])
def test_nonpositive_reference_gain_has_no_retention_ratio(reference):
    result = summarize_portfolio(
        {"a": {"baseline": 0.5, "reference": reference, "candidate": 0.8}}, source_domains=["a"]
    )
    retention = result["source_gain_retention"]["a"]
    assert retention["retention"] is None
    assert retention["reason"] == "undefined_nonpositive_reference_gain"
    assert retention["candidate_gain"] == pytest.approx(0.3)


@pytest.mark.parametrize("candidate,expected", [(0.8, 3), (0.2, -3), (0.5, 0)])
def test_defined_source_retention_can_exceed_one_be_negative_or_zero(candidate, expected):
    result = summarize_portfolio(
        {"a": {"baseline": 0.5, "reference": 0.6, "candidate": candidate}}, source_domains=("a",)
    )
    assert result["source_gain_retention"]["a"]["retention"] == pytest.approx(expected)
    assert result["source_gain_retention"]["a"]["reason"] is None


def test_numerically_unrepresentable_ratio_stays_json_finite():
    result = summarize_portfolio({"a": {"baseline": 0, "reference": 5e-324, "candidate": 1}}, source_domains=["a"])
    assert result["source_gain_retention"]["a"]["retention"] is None
    assert (
        result["source_gain_retention"]["a"]["reason"] == "positive_reference_gain_but_ratio_not_finitely_representable"
    )
    json.dumps(result, allow_nan=False)


def test_multiple_explicit_source_domains_are_kept_separate():
    result = summarize_portfolio(ILLUSTRATIVE, source_domains=["research", "coding"])
    assert result["source_domains"] == ["coding", "research"]
    assert result["source_gain_retention"]["coding"]["retention"] == pytest.approx(0.9)
    assert result["source_gain_retention"]["research"]["retention"] is None
    assert "spreadsheet" not in result["source_gain_retention"]


def test_single_domain_and_closed_interval_endpoints_are_supported():
    result = summarize_portfolio({"only": {"baseline": 0, "reference": 1, "candidate": 1}}, source_domains=["only"])
    assert result["macro_scores"] == {"baseline": 0, "reference": 1, "candidate": 1}
    assert result["source_gain_retention"]["only"]["retention"] == 1
    assert result["tradeoff_vs_reference"]["equal_domains"] == ["only"]
    assert result["max_regression_vs_base"] == {"reference": 0, "candidate": 0}


def test_strict_negative_sign_has_no_hidden_safety_tolerance():
    lower = math.nextafter(0.5, 0)
    result = summarize_portfolio({"a": {"baseline": 0.5, "reference": 0.5, "candidate": lower}})
    assert result["negative_transfer_domain_fraction"]["candidate"] == 1
    assert result["macro_shortfall"]["candidate"] > 0


@pytest.mark.parametrize(
    "value", [None, True, False, "0.5", float("nan"), float("inf"), -float("inf"), -0.01, 1.01, 60, complex(0.5, 0)]
)
def test_missing_boolean_nonfinite_nonnumeric_or_unnormalized_scores_rejected(value):
    with pytest.raises(ValueError):
        summarize_portfolio({"a": {"baseline": 0.5, "reference": 0.5, "candidate": value}})


@pytest.mark.parametrize(
    "scores",
    [
        {},
        [],
        None,
        {"a": {"baseline": 0.5, "candidate": 0.6}},
        {"a": {"baseline": 0.5, "reference": 0.6, "candidate": 0.7, "benchmark": 1}},
        {"a": None},
        {"": {"baseline": 0.5, "reference": 0.5, "candidate": 0.5}},
        {" a": {"baseline": 0.5, "reference": 0.5, "candidate": 0.5}},
        {1: {"baseline": 0.5, "reference": 0.5, "candidate": 0.5}},
    ],
)
def test_incomplete_or_invalid_domain_tables_rejected(scores):
    with pytest.raises(ValueError):
        summarize_portfolio(scores)


@pytest.mark.parametrize(
    "weights",
    [
        {},
        [],
        {"coding": 1},
        {"coding": 0.3, "research": 0.3, "spreadsheet": 0.3},
        {"coding": 2, "research": 1, "spreadsheet": 1},
        {"coding": 0, "research": 0.5, "spreadsheet": 0.5},
        {"coding": -0.1, "research": 0.5, "spreadsheet": 0.6},
        {"coding": True, "research": 0, "spreadsheet": 0},
        {"coding": None, "research": 0.5, "spreadsheet": 0.5},
        {"coding": float("nan"), "research": 0.5, "spreadsheet": 0.5},
        {"coding": float("inf"), "research": 0.5, "spreadsheet": 0.5},
        {"coding": 0.2, "research": 0.3, "spreadsheet": 0.3, "extra": 0.2},
    ],
)
def test_illegal_or_incomplete_weights_rejected(weights):
    with pytest.raises(ValueError):
        summarize_portfolio(ILLUSTRATIVE, weights=weights)


def test_finite_oversized_weights_raise_value_error_before_fsum_overflow():
    scores = {
        "a": {"baseline": 0.5, "reference": 0.6, "candidate": 0.7},
        "b": {"baseline": 0.5, "reference": 0.6, "candidate": 0.7},
    }
    with pytest.raises(ValueError, match="0 < weight <= 1"):
        summarize_portfolio(scores, weights={"a": 1e308, "b": 1e308})


@pytest.mark.parametrize("sources", ["coding", None, {"coding": True}, ["coding", "coding"], ["unknown"], [False]])
def test_source_names_must_be_explicit_known_distinct_domains(sources):
    with pytest.raises(ValueError):
        summarize_portfolio(ILLUSTRATIVE, source_domains=sources)


class DuplicateMapping(Mapping):
    def __init__(self, items):
        self.items_list = items

    def __iter__(self):
        return iter(key for key, _ in self.items_list)

    def __len__(self):
        return len(self.items_list)

    def __getitem__(self, name):
        return next(value for key, value in self.items_list if name == key)

    def items(self):
        return iter(self.items_list)


def test_duplicate_domain_method_or_weight_item_streams_rejected():
    row = ILLUSTRATIVE["coding"]
    with pytest.raises(ValueError, match="duplicate"):
        summarize_portfolio(DuplicateMapping([("coding", row), ("coding", row)]))
    with pytest.raises(ValueError, match="duplicate"):
        summarize_portfolio({"coding": DuplicateMapping([*row.items(), ("candidate", 0.1)])})
    with pytest.raises(ValueError, match="duplicate"):
        summarize_portfolio(ILLUSTRATIVE, weights=DuplicateMapping([("coding", 0.5), ("coding", 0.5)]))


def test_input_order_is_irrelevant_and_inputs_are_not_mutated():
    scores, weights = deepcopy(ILLUSTRATIVE), {"coding": 0.5, "research": 0.3, "spreadsheet": 0.2}
    before = deepcopy((scores, weights))
    first = summarize_portfolio(scores, weights=weights, source_domains=["coding"])
    second = summarize_portfolio(
        dict(reversed(list(scores.items()))), weights=dict(reversed(list(weights.items()))), source_domains=("coding",)
    )
    assert first == second
    assert (scores, weights) == before
    first["per_domain"]["coding"]["scores"]["baseline"] = 0.1
    first["weighting"]["weights"]["coding"] = 0.1
    assert (scores, weights) == before


def test_caller_aggregates_multiple_benchmarks_within_domain_first():
    # Three Coding benchmarks and one Research benchmark must still receive
    # equal domain weight once the predefined within-domain mean is supplied.
    scores = {
        "coding": {"baseline": 0.5, "reference": 0.6, "candidate": (0.7 + 0.8 + 0.9) / 3},
        "research": {"baseline": 0.5, "reference": 0.6, "candidate": 0.4},
    }
    result = summarize_portfolio(scores)
    assert result["macro_scores"]["candidate"] == pytest.approx(0.6)
    assert result["weighting"]["weights"] == {"coding": 0.5, "research": 0.5}
    assert result["macro_scores"]["candidate"] != pytest.approx((0.7 + 0.8 + 0.9 + 0.4) / 4)


def test_output_explicitly_disclaims_risk_safety_and_real_experiment_provenance():
    result = summarize_portfolio(ILLUSTRATIVE)
    assert result["descriptive_only"] is True
    assert result["safety_certificate"] is False
    assert result["statistical_risk_estimate"] is False
    assert result["confidence_intervals_computed"] is False
    assert result["missing_scores_imputed"] is False
    notes = " ".join(result["interpretation"])
    assert "incompatible raw benchmark units" in notes
    assert "not an estimated probability" in notes
    assert "Illustrative numbers alone are not results from a real experiment" in notes
