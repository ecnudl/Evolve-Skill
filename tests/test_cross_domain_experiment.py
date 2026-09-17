"""Regression checks for the opt-in experiment, without network calls."""
import pytest

from skillopt.cross_domain.evolution import select_candidate
from skillopt.cross_domain.experiment import summarize_repeats


def test_empty_noop_cannot_win_shortest_tie_break():
    rows = [{"id": "v1", "content": "Preserve unchanged constraints.", "dev_em": 1.0},
            {"id": "v2", "content": "", "dev_em": 1.0}]
    assert select_candidate(rows)["id"] == "v1"


def test_all_noops_are_not_experimental_interventions():
    with pytest.raises(RuntimeError):
        select_candidate([{"id": "v1", "content": " ", "dev_em": 1.0}])


def test_empty_complete_case_set_reports_unknown_not_perfect():
    result = summarize_repeats([[], []], ["missing1", "missing2"])
    assert result["n_unique_tasks"] == 0
    assert result["em"] is None
    assert result["excluded_tasks_missing_any_repeat"] == 2


def test_reruns_count_as_one_task_and_missing_all_reruns_count_as_excluded():
    row = {"id": "a", "baseline": 1, "current": 1, "candidate": 0, "applied": True}
    result = summarize_repeats([[row], [row]], ["a", "b"])
    assert result["n_unique_tasks"] == 1
    assert result["regressed_observations"] == 2
    assert result["delta_em"] == -1
    assert result["excluded_tasks_missing_any_repeat"] == 1
