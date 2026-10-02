"""Pure parsing; no code execution, scoring, provider, or benchmark answers."""
import hashlib

import pytest

from skillopt.continual_eval.code_delivery import MAX_BYTES, extract_python


@pytest.mark.parametrize("fence", ["```", "~~~~", "````"])
@pytest.mark.parametrize("language", ["python", "py", "Python"])
def test_explicit_python_literal_payload(fence, language):
    code = 'x = "hello"\nprint(x)\n'
    text = f"Explanation\n{fence}{language}\n{code}{fence}\nAfterwards"
    row = extract_python(text)
    assert row["status"] == "available" and row["code"] == code
    assert text[slice(*row["span"])] == code and not row["syntax_validated"]
    assert row["code_sha256"] == hashlib.sha256(code.encode()).hexdigest()


def test_excel_close_cannot_become_unlabelled_opening():
    text = "```excel\n=AVERAGE(A:A)\n```\nWrong prose from old regex\n```excel\n=SUM(A:A)\n```\n```python\nprint('deliverable')\n```"
    row = extract_python(text)
    assert row["code"] == "print('deliverable')\n" and row["fenced_blocks"] == 3


def test_non_python_fences_with_python_markers_inside_are_not_candidates():
    text = "~~~~html\n```python\nnot_python()\n```\n~~~~\n```py\nreal_program()\n```"
    row = extract_python(text)
    assert row["code"] == "real_program()\n" and row["explicit_python_blocks"] == 1


@pytest.mark.parametrize("second", ["print(1)", "print(2)", "this is not valid Python"])
def test_multiple_python_blocks_never_selected_by_syntax_or_equality(second):
    row = extract_python(f"```python\nprint(1)\n```\n```py\n{second}\n```")
    assert row["status"] == "unknown" and row["reason"] == "multiple_python_blocks" and row["code"] is None


@pytest.mark.parametrize("text,reason", [
    ("```python\nprint(1)", "unclosed_fence"),
    ("```python\nprint(1)\n~~~~", "unclosed_fence"),
    ("````python\nprint(1)\n```", "unclosed_fence"),
    ("```excel\n=A1\n```", "no_unambiguous_python_deliverable"),
    ("```\nprint(1)\n```\n```\nprint(2)\n```", "no_unambiguous_python_deliverable"),
    ("```\nprint(1)\n```\n~~~html\ntext\n~~~", "no_unambiguous_python_deliverable"),
    ("    ```python\nprint(1)\n    ```", "unsupported_fence_syntax"),
    ("```py`bad\nprint(1)\n```", "unclosed_fence"),
    ("```python\n\n```", "empty_code_block"),
])
def test_unsupported_or_ambiguous_never_guessed(text, reason):
    row = extract_python(text)
    assert row["status"] == "unknown" and row["reason"] == reason and row["code"] is None


def test_sole_unlabelled_block_and_bare_payload_preserved_verbatim():
    assert extract_python("Before\n```\nprint(1)\n```\nAfter")["code"] == "print(1)\n"
    text = "  print('not automatically repaired')\r\n"
    row = extract_python(text)
    assert row["code"] == text and row["candidate_kind"] == "whole_unfenced_response"


def test_no_syntax_or_success_filtering():
    row = extract_python("```python\nthis is invalid Python !!!\n```")
    assert row["status"] == "available" and not row["syntax_validated"]


def test_crlf_and_unicode_offsets_are_literal_character_spans():
    code = "print('你好')\r\n"
    text = f"说明\r\n  ```python\r\n{code}  ````\r\n"
    row = extract_python(text)
    assert row["code"] == code and text[slice(*row["span"])] == code


def test_fence_closing_requires_no_trailing_text():
    code = "print(1)\n``` not a close\n"
    assert extract_python(f"```python\n{code}```")["code"] == code


@pytest.mark.parametrize("value,reason", [(None, "response_not_text"), ("", "empty_response"),
    ("  \n", "empty_response"), ("\ud800", "invalid_unicode"), ("x" * (MAX_BYTES + 1), "response_size_limit")])
def test_bounded_input(value, reason):
    assert extract_python(value)["reason"] == reason
