"""Authored solver-profile fixtures; no API or execution of generated code."""
import json

import pytest

from skillopt.continual_eval import backends as b
from skillopt.continual_eval.code_delivery import VERSION


def reply(text):
    return {"ok": True, "finish_reason": "stop", "response": text, "usage": {"total_tokens": 9}}


def test_profile_keeps_prompt_and_only_changes_deliverable_extraction():
    text = "```excel\n=A1\n```\nExplanation\n```python\ndef f(): return 1\n```"
    calls = []
    def call(system, user):
        calls.append((system, user))
        return reply(text)
    public = {"prompt": "Return one", "entry_point": "f", "test": "HIDDEN"}
    legacy = b.solve("bigcodebench", public, "", call)
    new = b.solve("bigcodebench", public, "", call, runtime={"code_extraction_version": VERSION})
    assert calls[0] == calls[1] and "HIDDEN" not in str(calls)
    assert legacy["output"] == "Explanation" and "code_delivery" not in legacy
    assert new["output"] == "def f(): return 1\n"
    assert new["code_delivery"]["version"] == VERSION == b.CODE_EXTRACTION_VERSION
    assert new["code_delivery"]["syntax_validated"] is False
    assert "code" not in new["code_delivery"]
    assert legacy["costs"] == new["costs"]


def test_ambiguous_reply_does_not_launch_sheet_code(monkeypatch):
    monkeypatch.setattr(b, "_sheet_preview", lambda *a, **k: [])
    monkeypatch.setattr(b, "_native", lambda *a, **k: pytest.fail("Ambiguous code executed"))
    text = "```python\nprint(1)\n```\n```python\nprint(2)\n```"
    result = b.solve("spreadsheetbench", {"instruction": "Edit", "input_files": ["fixture.xlsx"],
        "answer_position": "S!A1"}, "", lambda *a: reply(text), runtime={"code_extraction_version": VERSION})
    assert result["status"] == "unknown"
    assert result["reason"] == "code_delivery:multiple_python_blocks"
    assert result["costs"]["calls"] == 1


def test_sheet_uses_exact_single_code_span(monkeypatch):
    captured = []
    monkeypatch.setattr(b, "_sheet_preview", lambda *a, **k: [])
    monkeypatch.setattr(b, "_xlsx_bytes", lambda path: b"fixture")
    monkeypatch.setattr(b, "_native", lambda request, runtime: captured.append(request) or
                        {"status": "missing_output", "reason": "output.xlsx_not_produced"})
    code = "print('no output')\r\n"
    result = b.solve("spreadsheetbench", {"instruction": "Edit", "input_files": ["fixture.xlsx"],
        "answer_position": "S!A1"}, "", lambda *a: reply("```py\r\n" + code + "```"),
        runtime={"code_extraction_version": VERSION})
    assert captured[0]["code"] == result["output"]["code"] == code
    assert result["output"]["cases"][0]["status"] == "missing_output"


@pytest.mark.parametrize("benchmark,version", [("bigcodebench", "typo"), ("searchqa", VERSION)])
def test_invalid_profile_fails_before_paid_call(benchmark, version):
    runtime = {"code_extraction_version": version}
    assert b.readiness(benchmark, runtime)["reason"] == "invalid_code_extraction_version"
    assert b.solve(benchmark, {}, "", lambda *a: pytest.fail("Paid call"), runtime=runtime)["reason"] == "invalid_code_extraction_version"


def test_length_remains_unknown_even_with_complete_python_block():
    response = {**reply("```python\ndef f(): return 1\n```"), "finish_reason": "length"}
    result = b.solve("bigcodebench", {"prompt": "Return one", "entry_point": "f"}, "", lambda *a: response,
                     runtime={"code_extraction_version": VERSION})
    assert result["reason"] == "model_response_truncated" and "code_delivery" not in result
    assert json.dumps(result)
