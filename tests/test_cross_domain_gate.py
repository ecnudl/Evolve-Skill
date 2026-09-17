"""The cross-domain gate is opt-in, pure, paired, and subgroup sensitive."""

from copy import deepcopy

import pytest

from skillopt.cross_domain.gate import decide_scope, pair_stats


def _cell(domain, group, outcomes, *, mechanism="preservation"):
    return [
        {"id": f"{domain}-{group}-{mechanism}-{i}", "domain": domain, "mechanism": mechanism,
         "group": group, "baseline": baseline, "current": current, "candidate": candidate}
        for i, (baseline, current, candidate) in enumerate(outcomes)
    ]


def _evidence(n=200):
    rows = []
    for domain in ("coding", "spreadsheet"):
        rows += _cell(domain, "positive", [(1, 1, 1)] * (n // 2) + [(0, 0, 1)] * (n // 2))
        rows += _cell(domain, "nearmiss", [(1, 1, 1)] * n)
        rows += _cell(domain, "unrelated", [(1, 1, 1)] * n)
    return rows


def test_pair_counts_and_conditional_harm_have_distinct_denominators():
    stats = pair_stats(_cell("coding", "positive", [(0, 0, 1), (1, 1, 0), (1, 1, 1), (0, 1, 0)]))
    baseline = stats["comparisons"]["baseline"]
    current = stats["comparisons"]["current"]
    assert (baseline["wins"], baseline["losses"], baseline["ties"]) == (1, 1, 2)
    assert baseline["delta"] == 0
    assert baseline["conditional_harm"] == 0.5
    assert current["losses"] == 2
    assert current["conditional_harm"] == pytest.approx(2 / 3)
    assert baseline["delta_interval"][0] < 0 < baseline["delta_interval"][1]


def test_all_ties_in_small_sample_are_pending_not_safe():
    rows = []
    for domain in ("coding", "spreadsheet"):
        for group in ("positive", "nearmiss", "unrelated"):
            rows += _cell(domain, group, [(1, 1, 1)] * 24)
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "pending"
    assert not result["cross_domain_accepted"]
    for audit in result["group_audits"]:
        assert audit["safety"] == "pending"
        assert audit["comparisons"]["baseline"]["conditional_harm_interval"][1] > 0.1


def test_exact_paired_gain_detects_six_unopposed_wins_but_does_not_skip_safety():
    rows = _cell("coding", "source", [(0, 0, 1)] * 6 + [(1, 1, 1)] * 26)
    stats = pair_stats(rows)
    assert stats["comparisons"]["baseline"]["exact_paired_p"] == pytest.approx(1 / 64)
    result = decide_scope(rows)
    comparison = result["group_audits"][0]["comparisons"]["baseline"]
    assert comparison["checks"]["gain"] == "pass"
    assert result["action"] == "pending"
    assert result["missing_cells"]


def test_explicit_preinjection_base_identity_is_structurally_zero_not_sampled_ties():
    rows = _cell("spreadsheet", "unrelated", [(0, 0, 0), (1, 1, 1)])
    for row in rows:
        row["candidate_is_baseline"] = row["current_is_baseline"] = True
        row["applied"] = False
    result = decide_scope(rows)
    for reference in ("baseline", "current"):
        comparison = result["group_audits"][0]["comparisons"][reference]
        assert comparison["structural_identity"] is True
        assert comparison["delta_interval"] == [0.0, 0.0]
        assert comparison["conditional_harm_interval"] == [0.0, 0.0]
        assert comparison["checks"]["safety"] == "pass"
        assert comparison["checks"]["gain"] != "pass"
    assert result["action"] == "pending"


def test_identity_against_baseline_does_not_imply_identity_against_current():
    rows = _cell("spreadsheet", "unrelated", [(1, 1, 1)] * 24)
    for row in rows:
        row["candidate_is_baseline"] = True
    stats = pair_stats(rows)
    assert stats["comparisons"]["baseline"]["structural_identity"]
    assert not stats["comparisons"]["current"]["structural_identity"]
    assert stats["comparisons"]["current"]["delta_interval"][0] < 0


def test_inconsistent_or_nonboolean_identity_contract_is_rejected():
    rows = _cell("coding", "positive", [(0, 0, 1)])
    rows[0]["candidate_is_baseline"] = True
    with pytest.raises(ValueError, match="contradicts"):
        pair_stats(rows)
    rows[0]["candidate_is_baseline"] = "true"
    with pytest.raises(ValueError, match="boolean"):
        pair_stats(rows)
    rows[0]["candidate"] = 0
    rows[0]["candidate_is_baseline"] = True
    rows[0]["applied"] = True
    with pytest.raises(ValueError, match="application"):
        pair_stats(rows)


def test_strong_evidence_can_commit_across_domains():
    result = decide_scope(_evidence(), {"source_domains": ["coding"]})
    assert result["action"] == "cross_domain_commit"
    assert result["local_accepted"]
    assert result["counterexample_ids"] == []
    assert result["missing_cells"] == []
    assert any("multiplicity" in note for note in result["statistical_limitations"])


def test_average_improvement_cannot_hide_protected_domain_harm():
    rows = _evidence()
    rows += _cell("research", "unrelated", [(1, 1, 0)] * 40)
    assert sum(row["candidate"] - row["baseline"] for row in rows) > 0
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "restrict"
    assert not result["cross_domain_accepted"]
    assert len(result["counterexample_ids"]) == 40


def test_prior_local_flag_cannot_override_uncertified_source_update_when_restricting():
    rows = _evidence(n=24)
    rows += _cell("research", "unrelated", [(1, 1, 0)] * 40)
    result = decide_scope(rows, {"source_domains": ["coding"], "local_already_committed": True})
    assert not result["local_accepted"]
    assert result["action"] == "reject"


def test_harm_is_separate_even_when_same_cell_net_gain_is_positive():
    rows = _evidence()
    rows = [r for r in rows if not (r["domain"] == "spreadsheet" and r["group"] == "positive")]
    rows += _cell("spreadsheet", "positive", [(0, 0, 1)] * 100 + [(1, 1, 0)] * 40 + [(1, 1, 1)] * 60)
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "restrict"
    audit = next(a for a in result["group_audits"] if a["domain"] == "spreadsheet" and a["group"] == "positive")
    assert audit["comparisons"]["baseline"]["delta"] > 0
    assert audit["comparisons"]["baseline"]["checks"]["conditional_harm"] == "fail"


def test_candidate_must_not_harm_current_even_if_it_beats_baseline():
    rows = _evidence()
    rows += _cell("research", "unrelated", [(0, 1, 0)] * 200)
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "restrict"
    audit = next(a for a in result["group_audits"] if a["domain"] == "research")
    assert audit["comparisons"]["baseline"]["losses"] == 0
    assert audit["comparisons"]["current"]["checks"]["safety"] == "fail"


def test_source_harm_rejects_candidate():
    rows = _evidence()
    rows += _cell("coding", "unrelated", [(1, 1, 0)] * 200, mechanism="other")
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "reject"
    assert not result["local_accepted"]


def test_no_positive_gain_does_not_expand_scope():
    rows = _evidence()
    for row in rows:
        if row["domain"] == "spreadsheet" and row["group"] == "positive":
            row["baseline"] = row["current"] = row["candidate"] = 1
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "local_commit"
    assert not result["cross_domain_accepted"]


def test_source_groups_can_identify_source_domain_without_config():
    rows = _evidence()
    for row in rows:
        if row["domain"] == "coding" and row["group"] == "positive":
            row["group"] = "source"
    assert decide_scope(rows)["action"] == "cross_domain_commit"


def test_missing_protection_or_preregistered_cell_blocks_expansion():
    rows = [r for r in _evidence() if not (r["domain"] == "spreadsheet" and r["group"] == "unrelated")]
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "local_commit"
    assert result["missing_cells"]
    complete = decide_scope(_evidence(), {"source_domains": ["coding"], "expected_cells": [
        {"domain": "research", "group": "positive", "mechanism": "verification"},
    ]})
    assert not complete["cross_domain_accepted"]


def test_distinct_mechanisms_are_not_averaged_together():
    rows = _evidence()
    rows += _cell("spreadsheet", "nearmiss", [(1, 1, 0)] * 100, mechanism="verification")
    result = decide_scope(rows, {"source_domains": ["coding"]})
    assert result["action"] == "restrict"
    assert len([a for a in result["group_audits"] if a["domain"] == "spreadsheet" and a["group"] == "nearmiss"]) == 2


def test_no_reference_correct_observations_cannot_certify_conditional_safety():
    stats = pair_stats(_cell("coding", "positive", [(0, 0, 1)] * 200))
    assert stats["comparisons"]["baseline"]["conditional_harm"] is None
    assert stats["comparisons"]["baseline"]["conditional_harm_interval"] == [0.0, 1.0]


def test_local_prior_is_only_used_when_no_source_update_is_supplied():
    rows = [r for r in _evidence() if r["domain"] != "coding"]
    result = decide_scope(rows, {"source_domains": ["coding"], "local_already_committed": True})
    assert result["action"] == "cross_domain_commit"
    for row in rows:
        if row["group"] == "positive":
            row["domain"] = "coding"
    assert not decide_scope(rows, {"source_domains": ["coding"], "local_already_committed": True})["cross_domain_accepted"]


def test_inputs_are_not_modified_and_empty_input_is_pending():
    rows = _evidence()
    config = {"source_domains": ["coding"]}
    before = deepcopy((rows, config))
    decide_scope(rows, config)
    assert (rows, config) == before
    assert decide_scope([])["action"] == "pending"
    assert pair_stats([])["n"] == 0


@pytest.mark.parametrize("score", [float("nan"), float("inf"), None, "1", 0.5])
def test_invalid_scores_raise_instead_of_becoming_failures(score):
    rows = _cell("coding", "positive", [(1, 1, 1)])
    rows[0]["candidate"] = score
    with pytest.raises(ValueError, match="binary"):
        decide_scope(rows)


def test_duplicate_ids_and_invalid_config_are_rejected():
    rows = _cell("coding", "positive", [(1, 1, 1)])
    with pytest.raises(ValueError, match="Duplicate"):
        pair_stats(rows + rows)
    for config in ({"confidence": 1}, {"min_group_n": 0}, {"max_conditional_harm": -1}, {"typo": 1}):
        with pytest.raises(ValueError):
            decide_scope(rows, config)
