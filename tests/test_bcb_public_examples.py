"""Static, authored fixtures; no benchmark execution, model or container."""
import json

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation.bcb_public_examples import LIMITS, extract_public_examples


def extract(text):
    return extract_public_examples({"prompt": text, "entry_point": "solve"})


def candidate(text):
    result = extract(text)
    assert result["marker_count"] == 1
    return result["candidates"][0]


def test_flattened_example_preserves_exact_public_spans_and_context():
    text = '公开描述。 >>> solve(["a", "b"], count=2) {"items": [1, -2], "ok": True}\nNote that: random behavior requires review.\n'
    result = extract(text)
    row = result["candidates"][0]
    assert row["status"] == "supported"
    assert row["args"] == [["a", "b"]] and row["kwargs"] == {"count": 2}
    assert row["expected"] == {"items": [1, -2], "ok": True}
    assert result["public"]["prompt"] == text
    assert text[slice(*row["source_span"])] == row["source_text"]
    assert text[slice(*row["boundary"]["span"])] == "Note that:"
    for name in ("call", "expected"):
        start, stop = row[name + "_relative_span"]
        assert row["source_text"][start:stop]
    assert result["executed"] is False and result["authorization"] is False
    assert result["admissibility"] == "not_reviewed"
    verify(result)


@pytest.mark.parametrize("header", ["Note that:", "The function should output with:",
    "The function should raise the exception for:", "You should write self-contained code starting with:"])
def test_only_explicit_line_start_template_headers_delimit(header):
    row = candidate('>>> solve(1) 2\n' + header + ' retained public context')
    assert row["status"] == "supported" and row["expected"] == 2
    assert row["boundary"]["raw"] == header


@pytest.mark.parametrize("tail", ["42 additional explanation", "42 # approximate",
    "42; extra()", "42 Requirements: explanation", "42 The function should output with: int",
    "42\nThe function should improve performance: explanation", "42\n Note that: indented explanation"])
def test_tail_prose_comments_and_nonexact_headers_are_not_silently_discarded(tail):
    row = candidate(">>> solve(1) " + tail)
    assert row["status"] == "unsupported" and row["source_text"].endswith(tail)
    assert "expected" not in row


def test_header_inside_complete_triple_quoted_expected_is_not_a_boundary():
    row = candidate('>>> solve(1) """a\nNote that: not a section\nb"""\nThe function should output with: str')
    assert row["status"] == "supported"
    assert row["expected"] == "a\nNote that: not a section\nb"
    assert row["boundary"]["raw"] == "The function should output with:"


def test_header_inside_call_or_list_cannot_supply_a_shorter_expected():
    for text in ['>>> solve("""a\nNote that: inner\nb""") "ok"',
                 '>>> solve(1) [1,\nNote that: fake section\n2]']:
        row = candidate(text)
        assert row["boundary"]["kind"] == "prompt_end"
    assert candidate('>>> solve(1) [1,\nNote that: fake section\n2]')["status"] == "unsupported"


@pytest.mark.parametrize("body", ["result = solve(1) 2", "print(result) 2", "other(1) 2",
    "obj.solve(1) 2", "solve(x) 2", "solve(np.array([1])) [1]", "solve(*[1]) 2",
    "solve(**{'x': 1}) 2", "solve((1, 2)) [1, 2]", "solve({1, 2}) [1, 2]",
    "solve(b'x') 'x'", "solve({'x': 1, 'x': 2}) 2", "solve({1: 2}) 2",
    "solve(x=1, x=2) 2", "solve(1) float('nan')", "solve(1) (1, 2)",
    "solve(1e999) 2", "solve(1) -1e999", "solve(1) +True", "solve(1) [x for x in []]",
    "solve(__import__('os').system('AUTHORED_DO_NOT_RUN')) 0"])
def test_nonliteral_nonfinite_duplicate_or_stateful_forms_are_unsupported(body):
    row = candidate(">>> " + body)
    assert row["status"] == "unsupported" and "args" not in row


def test_multiple_examples_keep_all_supported_and_unsupported_candidates_in_order():
    text = ">>> solve(1) 2 >>> result = solve(2) >>> print(result) 3 >>> solve(3) 4"
    result = extract(text)
    assert result["marker_count"] == 4
    assert [row["status"] for row in result["candidates"]] == ["supported", "unsupported", "unsupported", "supported"]
    assert result["supported_count"] == 2 and result["unsupported_count"] == 2


def test_no_markers_and_unsupported_replay_are_deterministic():
    for text in ["A public contract without examples.", ">>> solve(x) ???"]:
        a, b = extract(text), extract(text)
        assert a == b
        assert verify(json.loads(json.dumps(a)))["record_hash"] == a["record_hash"]
        assert a["supported_count"] == 0


def test_entry_and_input_whitelist_exclude_host_hidden_and_selection_fields():
    public = {"prompt": ">>> solve(1) 2", "entry_point": "solve"}
    for field in ("private", "hidden_tests", "expected", "selection", "score", "skill_condition"):
        with pytest.raises(ValueError, match="Only explicit public"):
            extract_public_examples({**public, field: "AUTHORED_HIDDEN_CANARY"})
    assert "AUTHORED_HIDDEN_CANARY" not in json.dumps(extract_public_examples(public))
    for entry in ("obj.solve", "__import__('os')", "solve\n", None):
        with pytest.raises(ValueError):
            extract_public_examples({**public, "entry_point": entry})


def test_no_nonmutation_or_determinism_obligations_are_invented():
    result = extract("Mutate input in place; outputs may be random. >>> solve([1]) [2]")
    assert result["supported_count"] == 1
    assert result["admissibility"] == "not_reviewed"
    assert "obligations" not in result and "rubric" not in result
    assert "relation" not in result["candidates"][0]


def test_code_template_markers_cannot_be_promoted_to_examples():
    result = extract("You should write self-contained code starting with:\n```\n# >>> solve(1) 2\n```")
    assert result["candidates"][0]["reason"] == "marker_in_code_template"


@pytest.mark.parametrize("body", [
    "solve(" + str(2 ** 300) + ") 0",
    "solve(" + repr("x" * (LIMITS["string_bytes"] + 1)) + ") 0",
    "solve(" + repr(list(range(LIMITS["items"] + 1))) + ") 0",
    "solve(1) " + "[" * 14 + "0" + "]" * 14,
    "solve(1) " + "x" * (LIMITS["candidate_bytes"] + 1),
])
def test_bounded_literal_resources_are_terminal_unsupported(body):
    result = extract(">>> " + body)
    assert result["unsupported_count"] == 1 and result["supported_count"] == 0


def test_prompt_and_marker_budgets_do_not_silently_drop_unfavorable_candidates():
    with pytest.raises(ValueError, match="prompt budget"):
        extract("x" * (LIMITS["prompt_bytes"] + 1))
    result = extract(">>> solve(1) 2 " * (LIMITS["markers"] + 1))
    assert result["status"] == "unsupported"
    assert result["marker_count"] == result["unsupported_count"] == LIMITS["markers"] + 1
    assert result["candidates"] == [] and result["reason"] == "marker_budget_exceeded"


def test_unterminated_literal_header_remains_unsupported_not_truncated():
    result = extract('>>> solve(1) """unfinished\nNote that: not outside the string')
    assert result["unsupported_count"] == 1
    assert result["candidates"][0]["boundary"]["kind"] == "prompt_end"


@pytest.mark.parametrize("text", [
    '>>> solve(1) """first\n>>> solve(2) 3\nNote that: inside string\n"""',
    'Examples: >>> solve("""\n>>> solve(1) 42\nNote that:\nx""")\n0',
    '>>> solve([\n>>> solve(1) 42\nNote that: inside list\n]) 0',
])
def test_nested_markers_never_restart_inside_prior_literal_or_brackets(text):
    result = extract(text)
    assert result["marker_count"] == 2 and result["supported_count"] == 0
    assert result["unsupported_count"] == 2
    assert result["candidates"][1]["reason"] == "marker_inside_or_after_unresolved_lexical_context"
    assert result["candidates"][1]["lexical_anchor"] == result["candidates"][0]["lexical_anchor"]


def test_real_later_marker_is_supported_only_after_prior_literal_is_closed():
    result = extract('>>> solve("""inside >>> solve(2) 3""") "x" >>> solve(4) 5')
    assert [row["status"] for row in result["candidates"]] == ["unsupported", "unsupported", "supported"]
    assert result["candidates"][-1]["args"] == [4]


@pytest.mark.parametrize("body", [r'solve("\ud800") 0', r'solve(0) "\udfff"',
                                  r'solve({"\ud800": 0}) 0'])
def test_surrogate_literal_is_terminal_unsupported_not_extraction_crash(body):
    result = extract(">>> " + body)
    assert result["unsupported_count"] == 1
    assert result["candidates"][0]["reason"] == "invalid_unicode_literal"


def test_many_quoted_fake_section_headers_have_a_fixed_scan_budget():
    row = candidate('>>> solve(1) """\n' + 'Note that: inner\n' * 65 + '"""')
    assert row["reason"] == "section_boundary_budget_exceeded"


def test_long_prefix_is_rejected_before_scanning_its_later_section_headers():
    row = candidate('>>> solve(1) "' + 'x' * LIMITS["candidate_bytes"] + '"\nNote that: outer')
    assert row["reason"] == "candidate_budget_exceeded"


def test_marker_in_unterminated_comment_line_cannot_restart_an_example():
    result = extract('>>> solve(1) 2 # only comment >>> solve(2) 3\nNote that: text')
    assert result["supported_count"] == 0 and result["unsupported_count"] == 2
    assert result["candidates"][1]["reason"] == "marker_inside_or_after_unresolved_lexical_context"


def test_marker_after_comment_newline_is_not_falsely_marked_inside_comment():
    result = extract('>>> solve(1) 2 # comment\n>>> solve(2) 3\nNote that: text')
    assert [row["status"] for row in result["candidates"]] == ["unsupported", "supported"]
    assert result["candidates"][1]["expected"] == 3
