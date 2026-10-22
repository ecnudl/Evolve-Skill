"""T-JUDGE-1..5 (implementation plan §8.1): scorer v2 with the reference-independent precedence (registration §4.4,
Codex F7), the JSON answer, completion-aware failures, the lenient score, the format flags (J4) and the cell flags.

Offline and deterministic: synthetic fixture items (no pool or test data), receipts in the frozen client shape.
"""
from __future__ import annotations

import base64
import io
import json

import openpyxl
import pytest

from skillopt.coevo5.outcomes import FAIL, MALFORMED, NONCOMPLETION, PROGRAM_DEFECT, Verdict
from skillopt.execskill import judge, outcomes_ext

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
ITEMS = {
    "searchqa": ({"question": "Which city is the capital of France?", "context": ["Paris is the capital."]},
                 {"answers": ["Paris", "City of Paris"]}),
    "officeqa": ({"question": "What was the 1999 outlay in millions?", "context": ["Table: outlays 1999 12.5"]},
                 {"answer": "12.5"}),
    "livemath": ({"question": "2 + 2 = ?", "choices": "A) 3 B) 4 C) 5 D) 6 E) 7"}, {"answer": "B"}),
}
RIGHT = {"searchqa": "Paris", "officeqa": "12.5", "livemath": "B"}
WRONG = {"searchqa": "Lyon", "officeqa": "13", "livemath": "C"}


def receipt(text, *, finish="stop", ok=True, error=None, **extra):
    found = {"status": 200, "attempts": [{"status": 200, "seconds": 0.1}], "seconds": 0.1, "response": text,
             "finish_reason": finish, "usage": dict(USAGE), "usage_valid": True,
             "returned_model": "deepseek-v4.1-flash-1017", "reasoning_chars": 0, "ok": ok}
    if error is not None:
        found["error_type"] = error
    return {**found, **extra}


def available(reply, **shell):
    prediction = {"status": "available", "output": reply, "costs": {"calls": 1, "usage": USAGE},
                  "reason": "model_response_available"}
    return {**prediction, "shell": shell} if shell else prediction


def run(bench, reply, **kw):
    public, private = ITEMS[bench]
    return judge.judge(bench, public, private, available(reply), [receipt(reply)], runtime={}, **kw)


def fixtures():
    """(bench, reply) pairs covering every carrier and conflict of §4.4 (registered fixtures) on the three QA benches."""
    out = []
    for bench in ITEMS:
        r, w = RIGHT[bench], WRONG[bench]
        out += [(bench, reply) for reply in (
            "<answer>%s</answer>" % r, "<answer>%s</answer>" % w,
            '<answer>%s</answer> {"answer": "%s"}' % (r, w), '<answer>%s</answer> {"answer": "%s"}' % (w, r),
            '{"answer": "%s"} <answer>%s</answer>' % (w, r), '{"answer": "%s"} <answer>%s</answer>' % (r, w),
            '<answer></answer> {"answer": "%s"}' % r, '<answer> </answer>\n```json\n{"answer": "%s"}\n```' % r,
            '{"answer": "%s"}' % r, '{"answer": "%s"}' % w, '<answer>{"answer": "%s"}</answer>' % r,
            "The answer is %s." % r, "no answer here", '{"answer": null} %s' % r, "", r, "Reasoning first.\n%s" % r,
            '{"answer": "%s"}\n%s' % (w, r), '{"answer": "%s"}\n%s' % (r, w),
            '{"reasoning": "first", "answer": "%s"} then {"answer": "%s"}' % (r, w),
            '{"answer": "%s", "meta": {"answer": "%s"}}' % (r, w))]
    return out


# ------------------------------------------------------------------------------- T-JUDGE-1: v2 >= official and final
@pytest.mark.parametrize("bench,reply", fixtures())
def test_t_judge_1_v2_never_below_official_or_final(bench, reply):
    found = run(bench, reply)
    official, final, v2 = found["official"]["status"], found["final"]["token"], found["v2"]["token"]
    assert v2 == "pass" or official != "pass"
    assert v2 == final or (final == "fail" and v2 == "pass")
    assert found["carrier"] in judge.CARRIERS
    assert set(found) == {"version", "scorer", "official", "final", "v2", "lenient", "format", "flags", "carrier"}
    assert found["version"] == "fivebench-execskill-v1-judge" and found["scorer"] == "execskill-judge-v2"
    assert set(found["flags"]) <= set(judge.FLAGS) and found["flags"] == sorted(found["flags"])


def test_t_judge_1_the_invariant_is_asserted_not_assumed(monkeypatch):
    """Break-the-code check (9): a v2 that could turn a pass into a fail stops the judge."""
    monkeypatch.setattr(judge, "_passes", lambda *a: True)
    monkeypatch.setattr(outcomes_ext, "token", lambda verdict: "pass" if verdict.outcome == "pass" else "fail")
    found = run("searchqa", '{"answer": "Lyon"}')  # a forced rescue of a wrong JSON answer is still >= official
    assert found["v2"]["token"] == "pass"
    monkeypatch.setattr(outcomes_ext, "token", lambda verdict: "fail")  # a final below official
    with pytest.raises(ValueError, match="below the official score"):
        run("searchqa", "<answer>Paris</answer>")


# ------------------------------------------------------------------------------------- T-JUDGE-2: the JSON answer
@pytest.mark.parametrize("reply,expected", [
    ('{"answer": "Paris"}', "Paris"),
    ('Some text {"reasoning": "x", "answer": "Paris"} done', "Paris"),
    ('```json\n{"answer": "Paris"}\n```', "Paris"),
    ('{"answer": "Lyon"} and later {"answer": "Paris"}', "Paris"),
    ('{"answer": 12.50}', "12.50"),
    ('{"answer": 42}', "42"),
    ('{"answer": -1e3}', "-1e3"),
    ('{"answer": "Paris", "meta": {"answer": "Lyon"}}', "Paris"),  # a nested object belongs to its parent
    ('{"answer": "Paris"} {"note": "no key"}', "Paris"),
    ('<answer>{"answer": "Paris"}</answer>', "Paris"),
    ('{"answer": "Lyon"} {"answer": null}', None),  # the last object decides: no fallback to an earlier one
    ('{"answer": true}', None),
    ('{"answer": ["Paris"]}', None),
    ('{"answer": NaN}', None),
    ('{"answer": "   "}', None),
    ('{"answer": "a</answer>b"}', None),
    ('{"result": {"answer": "Paris"}}', None),  # only top-level objects
    ("{not json} {'answer': 'Paris'}", None),
    ("answer: Paris", None),
    ("", None),
    ('{"answer": "Pa' + "{" * 3, None),
    ('{"answer": "x", ' + '"a": [' * 5000, None),  # deeply nested, unterminated
])
def test_t_judge_2_json_answer_extraction(reply, expected):
    assert judge.json_answer(reply) == expected


def test_t_judge_2_a_json_only_reply_is_judged_by_the_frozen_comparison():
    found = run("searchqa", '{"answer": "the city of paris"}')  # SQuAD normalisation keeps "city of paris"
    assert (found["carrier"], found["official"]["status"], found["v2"]["token"]) == ("json", "fail", "pass")
    assert found["flags"] == ["json_rescued"] and found["format"]["violation"] is True  # J4 still sees no tag
    found = run("officeqa", '{"answer": 12.50}')  # numbers keep their text: OfficeQA's exact match says no
    assert (found["carrier"], found["v2"]["token"]) == ("json", "fail")
    assert "numeric_equal_string_unequal" in found["flags"] and found["lenient"]["pass"] is True
    found = run("livemath", 'I pick {"answer": "b."}')  # the frozen letter rule (backends.py:501-504)
    assert (found["carrier"], found["v2"]["token"]) == ("json", "pass")


# ----------------------------------------------------------------------- T-JUDGE-3: completion-aware failures
def test_t_judge_3_truncated_filtered_empty_and_undelivered_stay_wrong_or_unknown():
    public, private = ITEMS["searchqa"]
    cut = {"status": "unknown", "output": None, "costs": {"calls": 1}, "reason": "model_response_truncated"}
    found = judge.judge("searchqa", public, private, cut, [receipt('{"answer": "Paris"', finish="length", ok=False,
                                                                   error="finish_length")], runtime={})
    assert (found["final"]["token"], found["final"]["kind"], found["v2"]["token"]) == ("fail", NONCOMPLETION, "fail")
    assert found["flags"] == ["truncated"] and found["format"] == {"reply": False, "violation": True}
    blank = {"status": "available", "output": "", "costs": {"calls": 1},
             "reason": "model_response_completed_without_text"}
    found = judge.judge("searchqa", public, private, blank, [receipt("", ok=False, error="empty_content")],
                        runtime={})
    assert (found["final"]["token"], found["v2"]["token"], found["carrier"]) == ("fail", "fail", "none")
    assert found["flags"] == ["completed_without_text"]
    filtered = {"status": "unknown", "output": None, "costs": {"calls": 1}, "reason": "model_call_unavailable"}
    found = judge.judge("searchqa", public, private, filtered,
                        [receipt(None, finish="content_filter", ok=False, error="finish_content_filter")], runtime={})
    assert (found["final"]["token"], found["v2"]["token"], found["flags"]) == ("fail", "fail", ["filtered"])
    lost = {"status": "unknown", "output": None, "costs": {"calls": 1}, "reason": "model_call_unavailable"}
    gone = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "status": 503, "attempts": [],
            "error_type": "http_503", "seconds": 0.1}
    found = judge.judge("searchqa", public, private, lost, [gone], runtime={})
    assert (found["final"]["token"], found["v2"]["token"]) == ("unknown", "unknown")
    assert found["format"]["violation"] is None and found["lenient"]["pass"] is None


def test_t_judge_3_spreadsheet_and_alfworld_have_no_json_channel():
    malformed = {"status": "unknown", "output": None, "costs": {"calls": 1}, "reason": "code_delivery:no_candidate"}
    found = judge.judge("spreadsheetbench", {}, {}, malformed, [receipt('{"answer": "=SUM(A1:A3)"}')], runtime={})
    assert (found["final"]["token"], found["final"]["kind"], found["v2"]["token"]) == ("fail", MALFORMED, "fail")
    assert found["carrier"] == "none" and found["format"]["violation"] is True
    defect = {"status": "available", "output": {"code": "raise KeyError", "cases": [
        {"status": "unknown", "reason": "native_exception:KeyError"}]}, "costs": {"calls": 1},
        "reason": "generated_once_executed_per_public_case"}
    found = judge.judge("spreadsheetbench", {}, {}, defect, [receipt("```python\nraise KeyError\n```")], runtime={})
    assert (found["final"]["kind"], found["v2"]["token"]) == (PROGRAM_DEFECT, "fail")
    assert found["official"] == judge.NOT_SCORED and found["format"]["program_delivered"] is True
    invalid = {"status": "unknown", "output": None, "costs": {"calls": 3}, "reason": "invalid_action_format"}
    found = judge.judge("alfworld", {"game_file": "fixture"}, {}, invalid, [receipt("go")] * 3, runtime={})
    assert (found["final"]["kind"], found["v2"]["token"], found["format"]["violation"]) == (MALFORMED, "fail", True)


def _workbook():
    stream = io.BytesIO()
    openpyxl.Workbook().save(stream)
    return base64.b64encode(stream.getvalue()).decode()


def test_t_judge_3_a_spreadsheet_cell_is_scored_by_its_runner():
    prediction = {"status": "available", "output": {"code": "print(1)", "cases": [
        {"status": "available", "output_base64": _workbook()}]}, "costs": {"calls": 1},
        "reason": "generated_once_executed_per_public_case"}
    with pytest.raises(ValueError, match="scored by its runner"):
        judge.judge("spreadsheetbench", {}, {}, prediction, [receipt("x")], runtime={})
    score = {"status": "pass", "score": 1.0, "reason": "native_cell_values_hard_all_cases",
             "metrics": {"cases": [{"status": "pass", "reason": "values_match"}]}}
    found = judge.judge("spreadsheetbench", {}, {}, prediction, [receipt("x")], runtime={}, score=score)
    assert (found["official"]["status"], found["final"]["token"], found["v2"]["token"]) == ("pass", "pass", "pass")
    assert found["carrier"] == "official" and found["format"] == {"program_delivered": True, "cases": 1,
                                                                  "cases_available": 1, "violation": False}


def test_t_judge_3_a_runner_verdict_is_read_as_given():
    public, private = ITEMS["searchqa"]
    prediction = available('{"answer": "Paris"}')
    verdict = Verdict(FAIL, "noncompletion", "model_response_truncated", "5")  # e.g. the shell's margin rule
    found = judge.judge("searchqa", public, private, prediction, [receipt("x")], runtime={}, verdict=verdict)
    assert (found["final"]["token"], found["v2"]["token"]) == ("fail", "fail")  # only a scored fail is rescued
    with pytest.raises(ValueError):
        judge.judge("searchqa", public, private, prediction, [receipt("x")], runtime={},
                    verdict=Verdict("unknown", "infrastructure", "x", "9a", "reexecute", ("fail", "x")))


# ------------------------------------------------------------- T-JUDGE-4: lenient, format flags, cell flags, no text
def test_t_judge_4_format_flags_per_bench():
    found = run("searchqa", "Paris")  # no tag: the frozen last-line fallback passes it
    assert found["official"]["status"] == "pass" and found["v2"]["token"] == "pass"
    assert found["format"] == {"reply": True, "tag_count": 0, "tag_present": False, "tag_usable": False,
                               "json_in_tag": False, "json_answer": False, "last_line_fallback": True,
                               "violation": True}
    found = run("officeqa", "<answer>$12.5 million</answer>")
    assert found["format"]["single_number"] is True and found["format"]["violation"] is False
    found = run("livemath", "<answer>B is correct</answer> \\boxed{B}")
    assert (found["format"]["single_letter"], found["format"]["boxed"], found["format"]["violation"]) == (
        False, True, True)
    assert (found["official"]["status"], found["v2"]["token"], found["lenient"]["pass"]) == ("fail", "fail", True)


@pytest.mark.parametrize("hows,violation", [(["tag_exact"] * 9 + ["unchanged"], False),
                                            (["tag_exact"] * 8 + ["unchanged"] * 2, True),
                                            (["whole_level1"] * 3, False)])
def test_t_judge_4_alfworld_admissible_share(hows, violation):
    prediction = {"status": "available", "output": {"won": True, "steps": len(hows)}, "costs": {"calls": len(hows)},
                  "reason": "fresh_native_episode_completed",
                  "shell": {"deciding_receipt": len(hows) - 1, "alfworld_steps": [{"how": h} for h in hows]}}
    found = judge.judge("alfworld", {"game_file": "fixture"}, {}, prediction, [receipt("<action>go</action>")]
                        * len(hows), runtime={})
    assert (found["official"]["status"], found["v2"]["token"], found["carrier"]) == ("pass", "pass", "official")
    assert found["format"] == {"steps": len(hows), "admissible_steps": sum(h != "unchanged" for h in hows),
                               "violation": violation}


def test_t_judge_4_cell_flags_and_no_text_leaves_the_judge():
    public, private = ITEMS["officeqa"]
    prediction = available("<answer>12.50</answer>", deciding_receipt=0, fallback="second_call_fallback")
    receipts = [receipt("<answer>12.50</answer>", over_nominal=True),
                receipt(None, ok=False, error="thinking_mismatch", subtype="reasoning_mismatch")]
    found = judge.judge("officeqa", public, private, prediction, receipts, runtime={})
    assert found["flags"] == ["numeric_equal_string_unequal", "over_nominal", "reasoning_mismatch",
                              "second_call_fallback"]
    text = json.dumps(found)
    for secret in ("12.50", "12.5", "outlay", "Table"):
        assert secret not in text


# ----------------------------------------------------------------------------- T-JUDGE-5: one answer per reply
@pytest.mark.parametrize("bench", sorted(ITEMS))
def test_t_judge_5_a_usable_official_carrier_is_used_exclusively(bench):
    r, w = RIGHT[bench], WRONG[bench]
    for reply in ('<answer>%s</answer> {"answer": "%s"}' % (r, w), '{"answer": "%s"} <answer>%s</answer>' % (w, r)):
        found = run(bench, reply)
        assert (found["carrier"], found["v2"]["token"]) == ("official", "pass")
        assert judge.select_answer(bench, reply) == (r, "official")
    for reply in ('<answer>%s</answer> {"answer": "%s"}' % (w, r), '{"answer": "%s"} <answer>%s</answer>' % (r, w)):
        found = run(bench, reply)
        assert (found["carrier"], found["v2"]["token"]) == ("official", "fail")
    for reply in ('<answer></answer> {"answer": "%s"}' % r, '{"answer": "%s"}' % r,
                  '<answer>{"answer": "%s"}</answer>' % r):
        found = run(bench, reply)
        assert (found["carrier"], found["v2"]["token"]) == ("json", "pass")
        assert found["official"]["status"] == "fail"


def test_t_judge_5_livemath_only_a_letter_is_a_usable_tag():
    # the frozen strict rule (checks.py:24-28) drops one trailing ".", ")" or ":" only: "(B)" is no letter
    assert judge.select_answer("livemath", '<answer>(B)</answer> {"answer": "C"}') == ("C", "json")
    assert judge.select_answer("livemath", '<answer>B)</answer> {"answer": "C"}') == ("B)", "official")
    assert judge.select_answer("livemath", '<answer>Option B</answer> {"answer": "C"}') == ("C", "json")
    assert judge.select_answer("livemath", "<answer>Option B</answer>") == (None, "none")


def test_t_judge_5_program_and_action_carriers():
    # the frozen extraction's literal span (code_delivery.extract_python) keeps the program's last newline
    assert judge.select_answer("spreadsheetbench", "```python\nprint(1)\n```") == ("print(1)\n", "official")
    assert judge.select_answer("spreadsheetbench", '```python\na=1\n```\n```python\nb=2\n```') == (None, "none")
    assert judge.select_answer("spreadsheetbench", '{"answer": "=SUM(A1:A2)"}') == ('{"answer": "=SUM(A1:A2)"}',
                                                                                    "official")
    assert judge.select_answer("alfworld", '<action>open drawer 1</action> {"answer": "go"}') == (
        "open drawer 1", "official")
    assert judge.select_answer("alfworld", "  ") == (None, "none")
    assert judge.select_answer("alfworld", "x" * 1001) == (None, "none")
    with pytest.raises(ValueError):
        judge.select_answer("korbench", "x")


# --------------------------------------------- statistics review 6 (registrar decision 2026-10-22): one guess
@pytest.mark.parametrize("reply,carrier,v2", [
    ('{"answer": "Lyon"}\nParis', "official", "pass"),
    ('{"answer": "Paris"}\nLyon', "official", "fail"),  # the JSON beside a last line that holds an answer is not read
    ('Answer: {"answer": "Paris"}', "official", "fail"),
    ('<answer>Lyon</answer>\n{"answer": "Paris"}', "official", "fail"),
    ('{"answer": "Paris"}\n<answer>Lyon</answer>', "official", "fail"),
    ('{"answer": "Paris"}', "json", "pass"),  # the last line is the JSON object itself
    ('{\n  "answer": "Paris"\n}', "json", "pass"),  # "}" normalises to nothing
    ('```json\n{"answer": "Paris"}\n```', "json", "pass"),
    ('<answer></answer>\n{"answer": "Paris"}\nLyon', "json", "pass"),  # an empty tag: the last line is never read
    ('<answer>.</answer> {"answer": "Paris"}', "json", "pass"),
    ("Paris\n.", "none", "fail"),
])
def test_statistics_6_searchqa_one_guess_per_reply(reply, carrier, v2):
    found = run("searchqa", reply)
    assert (found["carrier"], found["v2"]["token"]) == (carrier, v2)
    assert found["official"]["status"] == ("pass" if carrier == "official" and v2 == "pass" else "fail")
    assert judge.select_answer("searchqa", reply)[1] == carrier


def test_statistics_6_conflicting_carriers_never_pass_on_both_sides():
    """A reply whose official carrier and JSON answer disagree passes on the official side only, so of the two orders
    exactly one passes (before the decision both did)."""
    passes = [run("searchqa", reply)["v2"]["token"] for reply in ('{"answer": "Lyon"}\nParis',
                                                                    '{"answer": "Paris"}\nLyon')]
    assert passes == ["pass", "fail"]
    assert judge.select_answer("officeqa", '{"answer": "12.5"}\n13') == ("12.5", "json")  # no last-line carrier there
