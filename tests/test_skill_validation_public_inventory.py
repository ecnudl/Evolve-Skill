"""Static public evidence inventories; fixtures are not method-effect evidence."""
import json

from skillopt.skill_validation import public_examples as corrected
from tests.test_skill_validation_natural_data import row


def inventory(example):
    return corrected.coverage_inventory(row(example=example))


def test_adjacent_examples_are_bound_to_prompt_and_source_lines():
    source = row(example=">>> solve(3) == 6\n    >>> solve(4) == 8")
    report = corrected.coverage_inventory(source)
    assert report["candidate_count"] == report["parsed_supported_count"] == 2
    assert report["selected_supported_count"] == 2
    assert report["unsupported_count"] == report["unselected_supported_count"] == 0
    assert report["prompt_hash"] and report["entry_point"] == "solve"
    for candidate in report["candidates"]:
        assert candidate["source_quote"] == source["prompt"].splitlines()[candidate["prompt_line_1based"] - 1]
        assert candidate["case_hash"] and candidate["candidate_id"]


def test_inventory_includes_normal_doctest_and_explicit_duplicate():
    report = inventory(">>> solve(3)\n    6\n\n    >>> solve(3) == 6\n    >>> solve(4) == 8")
    assert report["candidate_count"] == report["parsed_supported_count"] == 3
    assert report["unique_supported_count"] == report["selected_supported_count"] == 2
    assert report["duplicate_count"] == 1
    assert report["candidates"][1]["duplicate_of"] == report["candidates"][0]["candidate_id"]


def test_unsupported_expressions_remain_in_denominator_without_execution():
    report = inventory(">>> solve(make_input()) == 6\n    >>> solve(3) == compute()\n"
                       "    >>> solve(3) == 3 + 3\n    >>> solve(4) == 8")
    assert report["candidate_count"] == 4 and report["unsupported_count"] == 3
    assert report["parsed_supported_count"] == 1
    assert all(r["reason"] for r in report["candidates"][:3])
    assert report["benchmark_code_executed"] is False


def test_same_call_different_expected_is_public_conflict_not_adjudication():
    report = inventory(">>> solve(3) == 6\n    >>> solve(3) == 7\n    >>> solve(3) == 6")
    assert report["conflict_call_count"] == 1
    assert report["duplicate_count"] == 1
    conflict = report["conflicts"][0]
    assert json.loads(conflict["arguments_json"]) == {"args": [3], "kwargs": {}}
    assert [r["expected_json"] for r in conflict["alternatives"]] == ["6", "7"]
    assert sum(len(r["candidate_ids"]) for r in conflict["alternatives"]) == 3
    assert report["hidden_or_reference_accessed"] is False


def test_cap_truncation_is_visible_without_changing_historical_output():
    source = row(example="\n    ".join(f">>> solve({i}) == {i * 2}" for i in range(19)))
    before = corrected.public_examples(source)
    report = corrected.coverage_inventory(source)
    assert corrected.public_examples(source) == before
    assert len(before) == report["selected_public_case_count"] == 16
    assert report["candidate_count"] == report["unique_supported_count"] == 19
    assert report["unselected_supported_count"] == report["cap_truncation_minimum_count"] == 3
    assert report["extractor_at_limit"] is True


def test_inventory_is_deterministic_serializable_and_prompt_only():
    source = row(example=">>> solve(3) == 6\n    >>> solve(3) == 7")
    visible = {key: source[key] for key in ("prompt", "entry_point")}
    first = corrected.coverage_inventory(source)
    assert json.loads(json.dumps(first)) == first == corrected.coverage_inventory(visible)
    assert first == corrected.coverage_inventory(source)
    serialized = json.dumps(first)
    for sentinel in ("HOST_REFERENCE_SENTINEL", "HOST_CONTRACT_SENTINEL", "97871", "812391"):
        assert sentinel not in serialized


def test_inline_examples_are_not_silently_counted_as_full_coverage():
    report = inventory("solve(3) => 6")
    assert report["scope"] == "explicit_doctest_blocks_only"
    assert report["candidate_count"] == 0
    assert report["selected_public_case_count"] == report["selected_outside_inventory_count"] == 1
    assert report["limitations"]


def test_non_true_doctest_comparison_is_not_certified_by_inventory():
    report = inventory(">>> solve(3) == 7\n    False")
    assert report["unsupported_count"] == 1
    assert "comparison_has_non_true_output" in report["candidates"][0]["reason"]


def test_escaped_logical_docstring_lines_do_not_invent_physical_line_number():
    source = {"entry_point": "solve", "prompt": 'def solve(x):\n    """Return twice x.\\n    >>> solve(3) == 6"""\n'}
    report = corrected.coverage_inventory(source)
    assert report["candidate_count"] == report["parsed_supported_count"] == 1
    assert report["candidates"][0]["docstring_line_1based"] == 2
    assert report["candidates"][0]["prompt_line_1based"] is None
