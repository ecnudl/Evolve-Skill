import pytest

from skillopt.coevolution_v4.analysis import ARMS, analyze


def rows():
    return [{"id": "t", "stream": 0, "repeat": rep, "arm": arm, "cluster_id": "p",
             "job_hash": f"shared{rep}", "request_hash": f"request{rep}", "hard": rep == 0,
             "case_fraction": 1.0 if rep == 0 else .5, "skill_hash": "empty", "format_ok": True,
             "target_ok": True, "execution_ok": True, "skill_active": False}
            for rep in (0, 1) for arm in ARMS]


def test_shared_empty_policies_are_structural_not_independent_zero():
    result = analyze(rows())
    assert result["unique_solution_jobs"] == 2
    assert all(c["all_pairs_structurally_identical"] for c in result["contrasts"].values())
    assert result["repeat_variability"]["noskill"]["groups_with_repeat_flip"] == 1
    assert result["project_clusters"] == 1


def test_missing_and_duplicate_positions_rejected():
    with pytest.raises(ValueError, match="Incomplete"):
        analyze(rows()[:-1])
    with pytest.raises(ValueError, match="Duplicate"):
        analyze(rows() + [rows()[0]])


def test_alias_observations_cannot_diverge():
    data = rows()
    data[0]["hard"] = False
    with pytest.raises(ValueError, match="Shared"):
        analyze(data)
