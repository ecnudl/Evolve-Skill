"""Mock artifacts only: the live test set and model outputs are never accessed."""
import json
from copy import deepcopy

import pytest

from scripts.analyze_cross_domain_mvp import COMPARISONS, _digest
from scripts.analyze_cross_domain_shape_sensitivity import (
    analyze_shape_sensitivity,
    correct_policy_rows,
    corrected_score,
    main,
    shape_only_correct,
)


def _task():
    return {"id": "mock-task", "split": "test", "domain": "coding", "mechanism": "none",
            "group": "unrelated", "gold": [[1, 2, 3, 4, 5], 15, 3]}


def _rollout(prediction=None, *, hard=0, valid=True, ok=True):
    return {"id": "mock-task", "hard": hard, "agent_ok": ok,
            "evaluation": {"format_valid": valid,
                           "parsed_answer": [1, 2, 3, 4, 5, 15, 3] if prediction is None else prediction}}


def test_exact_flattened_shape_only_error_is_corrected_but_strict_success_is_not_relabelled():
    task, raw = _task(), _rollout()
    assert shape_only_correct(task, raw)
    assert corrected_score(task, raw) == 1
    strict = _rollout(task["gold"], hard=1)
    assert not shape_only_correct(task, strict)
    assert corrected_score(task, strict) == 1


@pytest.mark.parametrize("prediction", [
    [1, 2, 3, 4, 5, 16, 3], [2, 1, 3, 4, 5, 15, 3],
    [True, 2, 3, 4, 5, 15, 3], [1.0, 2, 3, 4, 5, 15, 3],
    ["1", 2, 3, 4, 5, 15, 3], [1, 2, 3, 4, 5, 15],
    [[1, 2, 3, 4, 5], 15, 3], {"answer": [1, 2, 3, 4, 5, 15, 3]},
])
def test_other_value_type_order_length_or_structure_errors_are_not_tolerated(prediction):
    assert not shape_only_correct(_task(), _rollout(prediction))


@pytest.mark.parametrize("change", [
    {"split": "validation"}, {"mechanism": "constraint_preservation"}, {"group": "near_miss"},
    {"gold": [[1, 2], 3, 1]}, {"gold": [[1, 2, 3, 4, 5], "15", 3]},
])
def test_secondary_rule_never_expands_to_other_tasks_or_gold_shapes(change):
    assert not shape_only_correct({**_task(), **change}, _rollout())


def test_invalid_json_or_api_failure_is_never_repaired():
    assert not shape_only_correct(_task(), _rollout(valid=False))
    failed = _rollout(ok=False, hard=None)
    assert not shape_only_correct(_task(), failed)
    assert corrected_score(_task(), failed) is None


def test_policy_replay_preserves_membership_and_mask_and_corrects_current_with_base():
    task, base, guided = _task(), _rollout(), _rollout([1, 2, 3, 4, 5, 99, 3])
    row = {"id": task["id"], "domain": "coding", "group": "unrelated", "mechanism": "none",
           "baseline": 0, "current": 0, "candidate": 0, "applied": False}
    original = deepcopy(row)
    fallback = correct_policy_rows([row], {task["id"]: task}, {task["id"]: base}, {task["id"]: guided})
    assert row == original
    assert len(fallback) == 1 and fallback[0]["id"] == task["id"]
    assert fallback[0]["applied"] is False
    assert (fallback[0]["baseline"], fallback[0]["current"], fallback[0]["candidate"]) == (1, 1, 1)
    injected = correct_policy_rows([{**row, "applied": True}], {task["id"]: task},
                                   {task["id"]: base}, {task["id"]: guided})
    assert (injected[0]["baseline"], injected[0]["current"], injected[0]["candidate"]) == (1, 1, 0)


@pytest.fixture
def shape_out(tmp_path):
    sid, protocol = "mock-skill", {"test_repeats": 2}
    policies = {name for _, _, left, right in COMPARISONS for name in (left, right)}
    policies.add("no_skill")
    frozen = {"protocol_hash": _digest(protocol), "tracks": {sid: {"skill": {
        "parent_content": "", "source_domain": "coding", "mechanism": "constraint_preservation"}}}}
    summary = {"protocol": protocol, "tracks": {sid: {name: {"em": 0.0} for name in policies}}}

    def write(relative, value):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    write("summary.json", summary)
    write("frozen_policies.json", frozen)
    write("datasets/test.json", [_task()])
    for repeat in range(2):
        write(f"rollouts/test_r{repeat}_base.json", [_rollout()])
        write(f"rollouts/test_r{repeat}_{sid}.json", [_rollout([1, 2, 3, 4, 5, 99, 3])])
        for policy in policies:
            applied = policy != "no_skill" and not policy.startswith("safe_")
            write(f"policy_outcomes/{sid}/{policy}_r{repeat}.json", [{
                "id": "mock-task", "domain": "coding", "mechanism": "none", "group": "unrelated",
                "baseline": 0, "current": 0, "candidate": 0, "applied": applied}])
    return tmp_path


def test_mock_artifact_analysis_reuses_all_fixed_comparisons_and_keeps_primary_unchanged(shape_out):
    before = {p.relative_to(shape_out): p.read_bytes() for p in shape_out.rglob("*") if p.is_file()}
    result = analyze_shape_sensitivity(shape_out)
    track = result["tracks"]["mock-skill"]
    assert track["strict_primary_policy_metrics"]["no_skill"]["em"] == 0.0
    assert track["shape_tolerant_policy_metrics"]["no_skill"]["em"] == 1.0
    assert track["shape_tolerant_policy_metrics"]["unconditional"]["em"] == 0.0
    assert track["shape_tolerant_policy_metrics"]["no_skill"]["n_unique_tasks"] == 1
    assert len(track["fixed_paired_comparisons"]) == 10
    paired = track["fixed_paired_comparisons"]["H1_safe_vs_unconditional"]["strata"]["overall"]
    assert paired["difference_pp"] == 100
    assert paired["difference_ci95_pp"] == [100, 100]
    assert result["shape_only_raw_correction_ids_by_repeat"]["baseline"] == [["mock-task"], ["mock-task"]]
    assert before == {p.relative_to(shape_out): p.read_bytes() for p in shape_out.rglob("*") if p.is_file()}
    json.dumps(result, allow_nan=False)


def test_nonempty_current_skill_is_rejected_before_any_raw_test_reads(shape_out):
    path = shape_out / "frozen_policies.json"
    frozen = json.loads(path.read_text())
    frozen["tracks"]["mock-skill"]["skill"]["parent_content"] = "Already deployed skill"
    path.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="current must equal base"):
        analyze_shape_sensitivity(shape_out)


def test_cli_optional_report_only_writes_secondary_file(shape_out, capsys):
    main(["--out", str(shape_out)])
    expected = json.loads(capsys.readouterr().out)
    assert not (shape_out / "shape_sensitivity.json").exists()
    main(["--out", str(shape_out), "--report"])
    capsys.readouterr()
    assert json.loads((shape_out / "shape_sensitivity.json").read_text()) == expected
