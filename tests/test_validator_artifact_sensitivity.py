"""Post-hoc extraction preserves code exactly and never repairs Python logic."""

from __future__ import annotations

import hashlib
import json

import pytest

from skillopt.validator_artifact_sensitivity import extract_artifact

CODE = "def f(value):\n    return value + 1\n"


@pytest.mark.parametrize("indent", [None, 2])
def test_strict_json_preserves_code_exactly(indent):
    raw = json.dumps({"code": CODE}, indent=indent)
    result = extract_artifact(raw)
    assert result["ok"] and result["syntax_ok"]
    assert result["code"] == CODE
    assert result["mode"] == "strict_json"
    assert result["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert result["code_sha256"] == hashlib.sha256(CODE.encode()).hexdigest()


def test_unescaped_json_newline_is_labeled_without_changing_code():
    raw = '{"code":"def f():\n    return 1\n"}'
    result = extract_artifact(raw)
    assert result["ok"] and result["syntax_ok"]
    assert result["mode"] == "json_unescaped_controls"
    assert result["code"] == "def f():\n    return 1\n"


@pytest.mark.parametrize(
    "prefix,suffix,mode",
    [
        ("", "", "python_fence"),
        ("Here is the repair:\n", "", "python_fence_with_prose"),
        ("", "\nThis preserves behavior.", "python_fence_with_prose"),
        ("\n   \n", "\n\t", "python_fence"),
    ],
)
def test_single_python_fence_with_optional_explicitly_labeled_prose(prefix, suffix, mode):
    result = extract_artifact(prefix + "```python\n" + CODE + "```" + suffix)
    assert result["ok"] and result["syntax_ok"]
    assert result["code"] == CODE
    assert result["mode"] == mode


@pytest.mark.parametrize("marker,language", [("```", "py"), ("~~~~", "python"), ("````", "PYTHON")])
def test_equivalent_markdown_fence_shapes(marker, language):
    result = extract_artifact(marker + language + "\n" + CODE + marker)
    assert result["ok"] and result["syntax_ok"]
    assert result["code"] == CODE


@pytest.mark.parametrize("language", ["json", ""])
def test_json_fences_use_json_decoding_not_python_dict_literal(language):
    raw = "```" + language + "\n" + json.dumps({"code": CODE}) + "\n```"
    result = extract_artifact(raw)
    assert result["code"] == CODE
    assert result["mode"] == "fenced_json"
    assert result["syntax_ok"]


def test_json_fence_control_relaxation_and_prose_both_reported():
    raw = 'Result:\n```json\n{"code":"def f():\n    return 1\n"}\n```\nDone.'
    result = extract_artifact(raw)
    assert result["code"] == "def f():\n    return 1\n"
    assert result["mode"] == "fenced_json_unescaped_controls_with_prose"


def test_raw_python_preserves_original_whitespace():
    raw = "\n\n" + CODE + "\n"
    result = extract_artifact(raw)
    assert result["ok"] and result["syntax_ok"]
    assert result["code"] == raw
    assert result["mode"] == "raw_python"


def test_raw_module_starting_with_a_docstring_is_not_mistaken_for_json():
    raw = '"""Module documentation."""\n' + CODE
    result = extract_artifact(raw)
    assert result["ok"] and result["syntax_ok"]
    assert result["code"] == raw
    assert result["mode"] == "raw_python"


@pytest.mark.parametrize("wrapper", [lambda x: json.dumps({"code": x}), lambda x: "```python\n" + x + "\n```"])
def test_extracted_python_syntax_error_is_not_fixed_or_hidden(wrapper):
    code = CODE + "}\n"
    result = extract_artifact(wrapper(code))
    assert result["ok"] and not result["syntax_ok"]
    assert result["error_category"] == "python_syntax_error"
    assert result["code"].startswith(code)
    assert "}" in result["code"]


@pytest.mark.parametrize(
    "raw,category",
    [
        ('{"code":"x=1","code":"x=2"}', "ambiguous_duplicate_json_keys"),
        ('{"code":1}', "json_artifact_schema"),
        ('{"code":"x=1","explanation":"extra"}', "json_artifact_schema"),
        ('{"answer":"x=1"}', "json_artifact_schema"),
        ('["x=1"]', "json_artifact_schema"),
        ('"x=1"', "json_artifact_schema"),
        ('{"code":"x=1"} trailing prose', "malformed_json"),
        ('{"code":"x=1"', "malformed_json"),
        ('{"code":""}', "empty_artifact"),
        ('{"code":"   "}', "empty_artifact"),
        ("```python\nx=1\n```\n```python\ny=2\n```", "multiple_fenced_blocks"),
        ('```json\n{"code":"x=1"}\n```\n```python\ny=2\n```', "multiple_fenced_blocks"),
        ("```python\nx=1", "unclosed_fence"),
        ("```python\nx=1\n~~~", "mismatched_fences"),
        ("````python\nx=1\n```", "mismatched_fences"),
        ("```python\nx=1\n```python", "mismatched_fences"),
        ("```javascript\nx=1\n```", "unsupported_fence_language"),
        ("```python\n\n```", "empty_artifact"),
        ("def f(:", "unrecognized_artifact"),
        ("Here is the repair:\ndef f():\n    return 1", "unrecognized_artifact"),
        ("", "empty_response"),
    ],
)
def test_ambiguous_or_malformed_artifacts_are_refused(raw, category):
    result = extract_artifact(raw)
    assert not result["ok"]
    assert result["code"] is None
    assert result["error_category"] == category


def test_literal_backslash_n_is_not_redecoded_as_newline():
    code = r"def f():\n    return 1"
    result = extract_artifact(json.dumps({"code": code}))
    assert result["code"] == code
    assert result["ok"] and not result["syntax_ok"]


def test_json_invalid_quoting_is_not_repaired():
    result = extract_artifact('{"code":"return "hello""}')
    assert not result["ok"]
    assert result["error_category"] == "malformed_json"


def test_newline_relaxation_does_not_repair_missing_quote_or_brace():
    result = extract_artifact('{"code":"def f():\n    return 1\n}')
    assert not result["ok"]
    assert result["error_category"] == "malformed_json"


def test_no_execution_even_when_raw_artifact_raises():
    result = extract_artifact("raise RuntimeError('never execute')\n")
    assert result["ok"] and result["syntax_ok"]


def test_code_fence_text_inside_valid_json_code_is_not_ambiguous():
    code = 'example = "```python\\nx=1\\n```"\n'
    result = extract_artifact(json.dumps({"code": code}))
    assert result["ok"] and result["code"] == code


def test_non_string_input_and_bounded_size():
    assert extract_artifact(None)["error_category"] == "response_not_string"
    assert extract_artifact("x" * 1_000_001)["error_category"] == "response_size_limit"
