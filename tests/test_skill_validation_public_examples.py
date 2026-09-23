import json

import pytest

from skillopt.skill_validation import natural_data as legacy
from skillopt.skill_validation import public_examples as corrected
from tests.test_skill_validation_natural_data import row


def test_adjacent_doctest_comparisons_preserve_every_literal_example():
    source = row(example=">>> solve([1, -2, 3]) == [-2, 1, 3]\n    >>> solve([]) == []")
    assert len(legacy.public_examples(source)) == 1  # Preserve the frozen behavior explicitly.
    cases = corrected.public_examples(source)
    assert len(cases) == 2 and len(corrected.missing_examples(source)) == 1
    assert json.loads(cases[1].arguments_json) == {"args": [[1, -2, 3]], "kwargs": {}}
    assert json.loads(cases[1].expected_json) == [-2, 1, 3]
    assert cases[1].contract_quote == source["prompt"]
    assert corrected.public_examples({k: source[k] for k in ("prompt", "entry_point")}) == cases


@pytest.mark.parametrize("expression", [
    "solve(make_input()) == 2", "solve(2) == compute()", "solve(2) == 2 + 2",
    "solve(2) == 2 == 2", "solve(2) != 2", "solve(2) == (1, 2)", "other(2) == 4",
    "solve(2) == {'x': object()}", "solve(2) == [1]; print('never run')",
])
def test_extra_parser_never_executes_or_infers_answers(expression):
    source = row(example=">>> " + expression + "\n    >>> solve(0) == 0")
    assert not corrected.missing_examples(source)


def test_existing_examples_are_not_duplicated_or_rewritten():
    source = row(example=">>> solve(2)\n    4\n\n    >>> solve(2) == 4\n    >>> solve(0) == 0")
    cases = corrected.public_examples(source)
    assert len(cases) == 2
    assert {c.expected_json for c in cases} == {"4", "0"}
