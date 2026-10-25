"""Review finding 3: recovery never replaces a literal v1 deliverable; offline parsing only."""
from itertools import product

import pytest

from skillopt.continual_eval.code_delivery import extract_python as extract_v1
from skillopt.execskill.code_delivery import VERSION, extract_python


@pytest.mark.parametrize("multiple", ["refuse", "last"])
def test_review_glued_prose_before_a_v1_python_block_preserves_program_and_span(multiple):
    reply = "Here is the code.```python\n```python\nprint(1)\n```"
    original = extract_v1(reply)
    actual = extract_python(reply, multiple=multiple)
    assert actual["status"] == "available"
    assert actual["code"] == original["code"] == "print(1)\n"
    assert actual["span"] == original["span"] == [reply.index("print(1)"), reply.rindex("```")]
    assert actual["kinds"] == []


# Successful fixtures from test_continual_eval_code_delivery.py cover the v1
# contract, including non-Python blocks, Unicode/CRLF, invalid Python and bare text.
_V1_PROGRAMS = [
    f'Explanation\n{fence}{language}\nx = "hello"\nprint(x)\n{fence}\nAfterwards'
    for fence, language in product(["```", "~~~~", "````"], ["python", "py", "Python"])
] + [
    "```excel\n=AVERAGE(A:A)\n```\nWrong prose from old regex\n```excel\n=SUM(A:A)\n```\n```python\nprint('deliverable')\n```",
    "~~~~html\n```python\nnot_python()\n```\n~~~~\n```py\nreal_program()\n```",
    "Before\n```\nprint(1)\n```\nAfter",
    "  print('not automatically repaired')\r\n",
    "```python\nthis is invalid Python !!!\n```",
    "说明\r\n  ```python\r\nprint('你好')\r\n  ````\r\n",
    "```python\nprint(1)\n``` not a close\n```",
]


@pytest.mark.parametrize("multiple", ["refuse", "last"])
@pytest.mark.parametrize("reply", _V1_PROGRAMS)
def test_every_successful_v1_case_retains_all_extraction_fields_under_recovery_variants(reply, multiple):
    assert extract_v1(reply)["status"] == "available"
    # A glued prefix and paired trailing fences expose interactions between the
    # added grammar and existing programs. Whenever v1 succeeds, all its fields
    # (apart from the extractor version) must still agree exactly.
    for prefix, suffix in product(["", "Here is the code.```python\n"], ["", "\n```\n```\n"]):
        candidate = prefix + reply + suffix
        original = extract_v1(candidate)
        actual = extract_python(candidate, multiple=multiple)
        if original["status"] == "available":
            assert actual == {**original, "version": VERSION, "multiple_python_blocks": multiple, "kinds": []}
            assert candidate[slice(*actual["span"])] == actual["code"]


@pytest.mark.parametrize("multiple", ["refuse", "last"])
def test_v1_bare_response_success_precedes_glued_opener_recovery(multiple):
    reply = "Here is the code.```python\nprint(1)"
    original = extract_v1(reply)
    assert original["status"] == "available" and original["candidate_kind"] == "whole_unfenced_response"
    assert extract_python(reply, multiple=multiple) == {
        **original, "version": VERSION, "multiple_python_blocks": multiple, "kinds": []}
