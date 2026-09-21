"""Static data-bridge tests: no API, no downloaded/generated code execution."""
import ast
import hashlib
import json

import pytest

from skillopt.coevolution_v11 import data as mbpp
from skillopt.skill_validation import single_round_data as data
from skillopt.validator_pilot.api import digest


def source_row(*, task_id=605, first="assert solve([3, 1]) == [1, 3]", rest=None):
    return {"task_id": task_id, "prompt": "Return the input integers in ascending order.",
            "code": "def solve(values):\n    return sorted(values)\n",
            "test_list": [first, *(rest or ["assert solve([9, 7]) == [7, 9]"])],
            "test_imports": []}


def identity(row, partition="development"):
    compiled = mbpp._compatibility(row)["compiled"]
    return {"task_id": row["task_id"], "original_task_id": f"mbpp:{row['task_id']}",
            "partition": partition, "source_split": mbpp.source_split(row["task_id"]),
            "question_sha256": mbpp.question_fingerprint(row["prompt"]),
            "family_id": f"family-{row['task_id']}", "source_row_hash": digest(row),
            "compiled_hash": digest(compiled)}


def test_public_projection_hides_reference_and_remaining_assertions():
    row = source_row()
    result = data.materialize_row(row, identity(row))
    visible = json.dumps({"task": result["task"].to_dict(), "wrapper": result["public_wrapper"]})
    assert row["test_list"][0] in result["task"].contract.prompt
    assert row["test_list"][1] not in visible
    assert row["code"] not in visible
    assert "return sorted(values)" not in visible
    assert result["host_audit"]["native_assertions"] == row["test_list"]
    assert result["host_audit"]["original_assertion_count"] == 2
    assert [o.kind for o in result["task"].contract.obligations] == ["requested_behavior"]
    assert not result["task"].relations


@pytest.mark.parametrize("assertion", [
    "assert solve([3,1]) == (1, 3)",
    "assert solve([3,1]) == {1, 3}",
    "assert solve([3,1]) == 1.0",
    "assert solve([3,1]) is True",
    "assert solve([3,1])",
    "assert not solve([3,1])",
])
def test_public_wrapper_retains_native_assertion_ast_no_json_coercion(assertion):
    row = source_row(first=assertion)
    result = data.materialize_row(row, identity(row))
    actual = ast.parse(result["public_wrapper"]["content"])
    checks = [n for n in ast.walk(actual) if isinstance(n, ast.Assert)]
    assert len(checks) == 1
    assert ast.dump(checks[0]) == ast.dump(ast.parse(assertion).body[0])
    assert result["task"].public_cases[0].expected_json == "true"
    assert json.loads(result["task"].public_cases[0].arguments_json) == {"args": [], "kwargs": {}}


def test_artifact_helpers_keep_private_wrapper_separate():
    row = source_row()
    result = data.materialize_row(row, identity(row))
    public_files = data.build_artifact_files(result, "def solve(x): return x")
    private_files = data.build_artifact_files(result, "def solve(x): return x", audit=True)
    assert [f.path for f in public_files] == ["solution.py", "public_runner.py"]
    assert [f.path for f in private_files] == ["solution.py", "hidden_audit.py"]
    assert public_files[0] == private_files[0]
    assert len([n for n in ast.walk(ast.parse(private_files[1].content)) if isinstance(n, ast.Assert)]) == 2
    assert row["test_list"][1] not in public_files[1].content


def test_changed_row_or_compilation_rejected():
    row = source_row()
    selected = identity(row)
    with pytest.raises(ValueError, match="source row changed"):
        data.materialize_row({**row, "prompt": "Other task"}, selected)
    with pytest.raises(ValueError, match="compatibility changed"):
        data.materialize_row(row, {**selected, "compiled_hash": "0" * 64})


def test_zero_or_unsupported_assertions_cannot_become_pass():
    with pytest.raises(ValueError, match="zero-check"):
        data._wrapper([], "solve", audit=True)
    row = source_row(first="assert solve([1]) > 0")
    with pytest.raises(ValueError, match="compatibility changed"):
        data.materialize_row(row, {**identity(row), "compiled_hash": "0" * 64})


def records():
    return [{"task_id": i, "source_split": split, "question_sha256": hashlib.sha256(str(i).encode()).hexdigest(),
             "source_row_hash": "a" * 64, "compiled_hash": "b" * 64, "eligible": True}
            for split, ids in (("train", (601, 602, 603)), ("validation", (551, 552, 553)),
                               ("test", (11, 12, 13))) for i in ids]


def test_selection_deterministic_and_partition_identity_disjoint():
    rows = records()
    groups = {r["task_id"]: "family-" + str(r["task_id"]) for r in rows}
    inventory = {"excluded_ids": [], "excluded_question_sha256": []}
    kwargs = {"counts": {"development": 2, "verifier_calibration": 2, "final": 2}, "seed": 42}
    first = data.select_identities(rows, inventory, groups, **kwargs)
    second = data.select_identities(list(reversed(rows)), inventory, groups, **kwargs)
    assert first == second
    selected = [r for items in first[0].values() for r in items]
    assert len({r["task_id"] for r in selected}) == len(selected)
    assert all(r["source_split"] == {"development": "train", "verifier_calibration": "validation", "final": "test"}[r["partition"]]
               for r in selected)


def test_exposure_applies_to_near_duplicate_family_and_no_silent_downsize():
    rows = records()
    groups = {r["task_id"]: "family-" + str(r["task_id"]) for r in rows}
    groups[601] = groups[11]
    inventory = {"excluded_ids": [11], "excluded_question_sha256": []}
    selected, _ = data.select_identities(rows, inventory, groups,
                                        counts={"development": 2, "verifier_calibration": 2, "final": 2})
    assert 601 not in {r["task_id"] for r in selected["development"]}
    with pytest.raises(ValueError, match="do not lower counts"):
        data.select_identities(rows, inventory, groups,
                               counts={"development": 3, "verifier_calibration": 2, "final": 2})


def test_lexical_grouping_case_punctuation_and_close_word_changes():
    groups = data._fingerprints([
        {"task_id": 1, "prompt": "Return the sum of the positive integers in this list."},
        {"task_id": 2, "prompt": "Return the sum of the positive integers in this list!"},
        {"task_id": 3, "prompt": "RETURN the sum of the positive integers in this list"},
        {"task_id": 4, "prompt": "Determine whether a string is a palindrome."},
    ])
    assert groups[1] == groups[2] == groups[3]
    assert groups[1] != groups[4]


def test_public_wrapper_cannot_silently_take_multiple_checks():
    with pytest.raises(ValueError, match="exactly the first"):
        data._wrapper(["assert solve(1)", "assert solve(2)"], "solve", audit=False)
