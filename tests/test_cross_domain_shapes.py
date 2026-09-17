"""Only the narrowly declared post-hoc validation diagnostic gets secondary credit."""

import json
from copy import deepcopy

import pytest

from scripts.audit_cross_domain_shapes import audit_run, main, normalization


def _task(identifier="example", **changes):
    task = {"id": identifier, "domain": "coding", "mechanism": "none", "group": "unrelated",
            "split": "validation", "gold": [[-4, 3, -14, 16, 0, -10, -13, 19, -3], 82, 3]}
    return {**task, **changes}


def _row(task, answer=None, *, correct=False, agent_ok=True, format_valid=True):
    return {**{key: task[key] for key in ("id", "domain", "mechanism", "group", "split")},
            "hard": int(correct) if agent_ok else None, "agent_ok": agent_ok,
            "evaluation": {"correct": correct, "format_valid": format_valid,
                           "parsed_answer": task["gold"][0] + task["gold"][1:] if answer is None else answer},
            "request_hash": "request-" + task["id"]}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_exact_flattening_is_marked_without_mutating_scores_or_input():
    task = _task()
    row = _row(task)
    original = deepcopy((task, row))
    annotation = normalization(task, row)
    assert annotation["shape_only"]
    assert not annotation["strict_correct"]
    assert annotation["shape_tolerant_correct"]
    assert annotation["request_hash"] == row["request_hash"]
    assert (task, row) == original


@pytest.mark.parametrize("changes", [
    {"split": "test"}, {"split": "train"}, {"split": "dev"},
    {"mechanism": "constraint_preservation"}, {"group": "near_miss"},
    {"gold": [[1, 2, 3, 4, 5], 15, 3]},
])
def test_other_splits_mechanisms_groups_and_shapes_get_no_credit(changes):
    task = _task(**changes)
    assert not normalization(task, _row(task))["shape_only"]


@pytest.mark.parametrize("changes", [{"agent_ok": False}, {"format_valid": False}])
def test_api_and_format_failures_are_never_rescued(changes):
    task = _task()
    annotation = normalization(task, _row(task, **changes))
    assert not annotation["shape_only"]
    assert not annotation["shape_tolerant_correct"]


@pytest.mark.parametrize("mutation", ["wrong_number", "wrong_order", "extra_item", "missing_item", "boolean", "nested", "string", "nan"])
def test_no_numeric_order_type_or_extra_item_tolerance(mutation):
    task = _task()
    answer = task["gold"][0] + task["gold"][1:]
    if mutation == "wrong_number":
        answer[-1] += 1
    elif mutation == "wrong_order":
        answer[0], answer[1] = answer[1], answer[0]
    elif mutation == "extra_item":
        answer.append(0)
    elif mutation == "missing_item":
        answer.pop()
    elif mutation == "boolean":
        answer[4] = False
    elif mutation == "nested":
        answer = task["gold"]
    elif mutation == "string":
        answer[0] = str(answer[0])
    else:
        answer[0] = float("nan")
    assert not normalization(task, _row(task, answer))["shape_only"]


def test_exact_finite_float_values_follow_original_numeric_equality():
    task = _task()
    answer = [float(value) for value in task["gold"][0] + task["gold"][1:]]
    assert normalization(task, _row(task, answer))["shape_only"]


def test_original_correct_answer_is_preserved_but_not_counted_as_shape_only():
    task = _task()
    annotation = normalization(task, _row(task, task["gold"], correct=True))
    assert annotation["strict_correct"]
    assert annotation["shape_tolerant_correct"]
    assert not annotation["shape_only"]


def test_identity_metadata_and_score_contradictions_raise():
    task = _task()
    row = _row(task)
    row["split"] = "test"
    with pytest.raises(ValueError, match="mismatch"):
        normalization(task, row)
    row = _row(task)
    row["hard"] = 1
    with pytest.raises(ValueError, match="contradicts"):
        normalization(task, row)


def test_audit_reports_arm_cell_and_paired_strict_vs_secondary_counts(tmp_path):
    first, second, third = _task("shape"), _task("regression"), _task("api_error")
    tasks = [first, second, third]
    baseline = [_row(first), _row(second, second["gold"], correct=True), _row(third, agent_ok=False)]
    candidate = [_row(first, first["gold"], correct=True), _row(second, [9] * 11), _row(third)]
    _write(tmp_path / "datasets/validation.json", tasks)
    _write(tmp_path / "rollouts/validation_base.json", baseline)
    _write(tmp_path / "rollouts/validation_constraint_preservation_v1.json", candidate)
    # A malformed test file ensures discovery does not accidentally open it.
    (tmp_path / "datasets/test.json").write_text("do not read", encoding="utf-8")
    (tmp_path / "rollouts/test_r0_base.json").write_text("do not read", encoding="utf-8")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    audit = audit_run(tmp_path)
    assert audit["test_read"] is False
    assert audit["gate_recomputed"] is False
    assert audit["arms"]["base"]["strict_correct"] == 1
    assert audit["arms"]["base"]["shape_only"] == 1
    assert audit["arms"]["base"]["shape_tolerant_correct"] == 2
    assert audit["arms"]["base"]["cells"][0]["shape_only"] == 1
    paired = audit["forced_candidate_vs_base"]["constraint_preservation_v1"]
    assert paired["n_paired_api_success"] == 2
    assert paired["n_excluded_missing_or_api_error"] == 1
    assert (paired["strict"]["wins"], paired["strict"]["losses"]) == (1, 1)
    assert (paired["shape_tolerant"]["wins"], paired["shape_tolerant"]["losses"]) == (0, 1)
    assert all("validation" in source["path"] for source in audit["input_sources"])
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


def test_missing_rows_are_reported_and_duplicate_or_unknown_ids_rejected(tmp_path):
    task = _task()
    _write(tmp_path / "datasets/validation.json", [task])
    path = tmp_path / "rollouts/validation_base.json"
    _write(path, [])
    assert audit_run(tmp_path)["arms"]["base"]["n_missing"] == 1
    _write(path, [_row(task), _row(task)])
    with pytest.raises(ValueError, match="Duplicate"):
        audit_run(tmp_path)
    _write(path, [_row(_task("unknown"))])
    with pytest.raises(ValueError, match="out-of-dataset"):
        audit_run(tmp_path)


def test_cli_default_is_stdout_and_report_never_overwrites(tmp_path, capsys):
    task = _task()
    _write(tmp_path / "datasets/validation.json", [task])
    _write(tmp_path / "rollouts/validation_base.json", [_row(task)])
    assert main(["--run-dir", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["diagnostic_only"]
    report = tmp_path / "validation_shape_audit.json"
    assert not report.exists()
    assert main(["--run-dir", str(tmp_path), "--report"]) == 0
    assert report.exists()
    before = report.read_bytes()
    with pytest.raises(FileExistsError):
        main(["--run-dir", str(tmp_path), "--report"])
    assert report.read_bytes() == before


def test_explicit_test_candidate_and_nonvalidation_dataset_are_refused(tmp_path):
    _write(tmp_path / "datasets/validation.json", [_task()])
    with pytest.raises(ValueError, match="Candidate IDs"):
        audit_run(tmp_path, ["../../datasets/test"])
    _write(tmp_path / "datasets/validation.json", [_task(split="test")])
    with pytest.raises(ValueError, match="validation dataset"):
        audit_run(tmp_path)
