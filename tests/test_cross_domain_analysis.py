"""Fixed paired-analysis tests; never touch live experiment outputs or APIs."""
import json

import pytest

from scripts.analyze_cross_domain_mvp import COMPARISONS, COVERAGES, _digest, analyze_run, compare_policies, main


def _row(task_id, score, *, domain="coding", applied=True):
    return {"id": task_id, "domain": domain, "candidate": score, "applied": applied,
            "baseline": 0, "current": 0}


def test_constant_paired_difference_has_constant_interval():
    left = [[_row(str(i), 1) for i in range(8)]]
    right = [[_row(str(i), 0, applied=False) for i in range(8)]]
    result = compare_policies(left, right)
    assert result["n_unique_tasks"] == 8
    assert result["difference_pp"] == 100
    assert result["difference_ci95_pp"] == [100, 100]
    assert result["policy_coverage"] == {"left": 1.0, "right": 0.0}


def test_generation_repeats_are_averaged_within_task_not_independent_samples():
    left = [[_row("a", 1), _row("b", 0)], [_row("a", 0), _row("b", 1)]]
    right = [[_row("a", 0), _row("b", 0)], [_row("a", 0), _row("b", 0)]]
    result = compare_policies(left, right)
    assert result["n_unique_tasks"] == 2
    assert result["n_generation_repeats"] == 2
    assert result["n_paired_task_repeat_observations"] == 4
    # Both original task means are exactly 0.5. Bootstrapping individual
    # repeat outcomes instead would spuriously yield a non-constant interval.
    assert result["difference_pp"] == 50
    assert result["difference_ci95_pp"] == [50, 50]


def test_pairing_uses_intersection_of_both_policies_and_all_repeats():
    left = [[_row("a", 0), _row("b", 1)], [_row("b", 1), _row("c", 0)]]
    right = [[_row("a", 1), _row("b", 0), _row("c", 1)], [_row("b", 0), _row("c", 1)]]
    result = compare_policies(left, right)
    assert result["n_unique_tasks"] == 1
    assert result["n_observed_in_any_policy_repeat"] == 3
    assert result["n_excluded_from_observed_union"] == 2
    assert result["difference_pp"] == 100


def test_domain_stratum_is_filtered_before_pairing_and_coverage():
    left = [[_row("a", 0), _row("b", 1, domain="spreadsheet"),
             _row("c", 1, domain="rule_reasoning")]]
    right = [[_row("a", 1), _row("b", 0, domain="spreadsheet", applied=False),
              _row("c", 0, domain="rule_reasoning", applied=False)]]
    result = compare_policies(left, right, domains=("spreadsheet", "rule_reasoning"))
    assert result["n_unique_tasks"] == 2
    assert result["difference_pp"] == 100
    assert result["policy_coverage"] == {"left": 1.0, "right": 0.0}


def test_empty_common_population_returns_standard_json_nulls():
    result = compare_policies([[_row("a", 1)]], [[_row("b", 0)]])
    assert result["n_unique_tasks"] == 0
    assert result["difference_pp"] is None
    assert result["difference_ci95_pp"] == [None, None]
    json.dumps(result, allow_nan=False)


def test_reordering_rows_does_not_change_bootstrap():
    left = [[_row(str(i), i % 2) for i in range(13)]]
    right = [[_row(str(i), int(i % 3 == 0)) for i in range(13)]]
    assert compare_policies(left, right) == compare_policies([left[0][::-1]], [right[0][::-1]])


def test_duplicate_ids_and_mismatched_shared_draws_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        compare_policies([[_row("a", 1), _row("a", 1)]], [[_row("a", 0)]])
    changed = {**_row("a", 0), "baseline": 1}
    with pytest.raises(ValueError, match="same baseline draw"):
        compare_policies([[_row("a", 1)]], [[changed]])
    with pytest.raises(ValueError, match="Domain differs"):
        compare_policies([[_row("a", 1)]], [[_row("a", 0, domain="spreadsheet")]])


@pytest.fixture
def analysis_out(tmp_path):
    protocol = {"test_repeats": 2, "seed": 42}
    sid = "constraint_v1"
    policies = {name for _, _, left, right in COMPARISONS for name in (left, right)}
    summary = {"protocol": protocol, "tracks": {sid: {name: {} for name in policies}},
               "evaluation_type": "offline fixture"}
    frozen = {"protocol_hash": _digest(protocol), "candidates_hash": "fixed-candidate",
              "code_hashes": {"fixed.py": "digest"},
              "tracks": {sid: {"skill": {"source_domain": "coding", "mechanism": "constraint_preservation"}}}}
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "frozen_policies.json").write_text(json.dumps(frozen), encoding="utf-8")
    directory = tmp_path / "policy_outcomes" / sid
    directory.mkdir(parents=True)
    for policy in policies:
        for repeat in range(2):
            score = int("mechanism" in policy)
            rows = [_row(domain, score, domain=domain) for domain in ("coding", "spreadsheet", "rule_reasoning")]
            (directory / f"{policy}_r{repeat}.json").write_text(json.dumps(rows), encoding="utf-8")
    return tmp_path


def test_fixed_comparison_plan_has_every_coverage_and_both_controls(analysis_out):
    assert COVERAGES == (10, 25, 50, 75)
    result = analyze_run(analysis_out)
    assert len(result["comparison_plan"]) == 10
    assert result["fixed_coverage_percentages"] == [10, 25, 50, 75]
    comparisons = result["tracks"]["constraint_v1"]["comparisons"]
    assert set(comparisons) == {item[0] for item in COMPARISONS}
    assert set(comparisons["H1_safe_vs_unconditional"]["strata"]) == {
        "overall", "non_source", "spreadsheet", "rule_reasoning"}
    assert comparisons["H1_safe_vs_unconditional"]["strata"]["non_source"]["n_unique_tasks"] == 2
    json.dumps(result, allow_nan=False)


def test_cli_is_read_only_by_default_and_report_is_explicit(analysis_out, capsys):
    before = {path.relative_to(analysis_out): path.read_bytes() for path in analysis_out.rglob("*") if path.is_file()}
    main(["--out", str(analysis_out)])
    stdout = json.loads(capsys.readouterr().out)
    after = {path.relative_to(analysis_out): path.read_bytes() for path in analysis_out.rglob("*") if path.is_file()}
    assert before == after
    assert not (analysis_out / "cross_domain_analysis.json").exists()
    main(["--out", str(analysis_out), "--report"])
    capsys.readouterr()
    assert json.loads((analysis_out / "cross_domain_analysis.json").read_text()) == stdout
    assert all((analysis_out / path).read_bytes() == content for path, content in before.items())


def test_analysis_rejects_protocol_mismatch(analysis_out):
    path = analysis_out / "summary.json"
    summary = json.loads(path.read_text())
    summary["protocol"]["seed"] = 43
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="protocol"):
        analyze_run(analysis_out)
