"""Controls for OfficeQA validation by GENERATED tasks (engineering fixtures, no method-effect claim): questions are
written from a stage's training tasks only, their reference answers are computed exactly from figures quoted from the
pages, and the published set can replace the 24-item validation part as the selection set of the gated learners."""
import hashlib
import json
from copy import deepcopy
from fractions import Fraction

import pytest

from scripts import generate_officeqa_tasks as gen
from scripts import generate_searchqa_tasks as shared
from scripts import make_extension_study as ext
from scripts import run_fivebench_g_stage as tool
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_active_evidence import API
from tests.test_continual_learning_domains import setup
from tests.test_continual_learning_extension_study import _base

PAGES = ("### bulletin page 8\nTable 3.- Analysis of General Expenditures (in millions of dollars)\n"
         "| Fiscal year | Total | Veterans' Administration |\n| 1934 | 4,908 | 507 |\n| 1935 | 5,900 | 557 |\n"
         "| 1936 | 5,935 | -18 |\nitem=%s")
SOURCE = {"question": "What is the value for u1?", "context": PAGES % "u1.txt"}
GOOD = {"question": "By what percentage did total general expenditures change from fiscal year 1934 to fiscal year "
                    "1935? Report a plain number in percent, rounded to two decimal places.",
        "figures": [{"name": "a", "value": "4,908", "quote": "| 1934 | 4,908 | 507 |"},
                    {"name": "b", "value": "5,900", "quote": "| 1935 | 5,900 | 557 |"}],
        "expression": "(b - a) / a * 100", "decimals": 2}


def test_reference_answers_are_computed_exactly_inside_a_closed_grammar():
    assert gen.figure("1,513") == 1513 and gen.figure("-18") == -18
    assert gen.figure("$4.73") == Fraction(473, 100) and gen.figure("12.5%") == Fraction(25, 2)
    assert all(gen.figure(text) is None for text in ("1,51", "1 513", "abc", "", "1e9", "--1", "(18)", "\u221218",
                                                     "9" * 25, "9" * 5000))
    values = {"a": Fraction(507), "b": Fraction(557)}
    assert gen.evaluate("(b - a) / a * 100", values) == Fraction(5000, 507)
    assert gen.evaluate("max(a, b) - abs(-a) + 0.5", values) == Fraction(101, 2)
    # outside the grammar, an unused figure, a division by zero: no value (the text is never executed)
    for text in ("a", "a ** b", "__import__('os').system('x') or a + b", "a.real + b", "a if b else b", "[a, b][0]",
                 "a + b + True", "a / (b - b)", "sum([a, b])", "a + b +", "(lambda: a + b)()", "a + b + c",
                 "min(a) + b", "abs(a, b)", "a + 'b'", "a + b; a", "a + b\nimport os"):
        assert gen.evaluate(text, values) is None, text
    assert gen.evaluate("+".join(["a"] * 40) + "+b", values) is None  # deeper than the bound
    assert gen.evaluate("a + b + 1e400", values) is None and gen.evaluate("a * b * 1000000000000000", values) is None
    # constants are read from their spelling, never as the float Python parsed: no silent loss of exactness
    assert gen.evaluate("a + b * 0.1", values) == Fraction(5627, 10)
    for text in ("a + b + 9007199254740993.0 - 9007199254740992", "a + b + 1e-400", "a + b + 1e3", "a + b + 1_000",
                 "a + b + 0x10", "a + b + 1j", "a + b + 1234567890123456", "a + b + .5", "a + b + 5.",
                 "a + b + \uff11"):
        assert gen.evaluate(text, values) is None, text
    rounding = {("9.8619", 2): "9.86", ("2.5", 0): None, ("-2.4", 0): "-2", ("-2.6", 0): "-3", ("12.5", 2): None,
                ("1513", 0): "1513", ("0.126", 2): "0.13", ("-0.126", 2): "-0.13", ("99.96", 1): None,
                ("-0.4", 0): "0", ("0.05", 1): None, ("1234.5678", 3): "1234.568"}
    assert {key: gen.rounded(Fraction(key[0]), key[1]) for key in rounding} == rounding


def test_deterministic_filters():
    reason, fields = gen.admit(GOOD, SOURCE, set())
    assert reason is None and fields["answer"] == "20.21" and fields["expression"] == "(b - a) / a * 100"
    from skillopt.envs.officeqa.evaluator import exact_match
    assert exact_match("20.21%", "20.21") == 0.0 and exact_match("$20.21 million", fields["answer"]) == 1.0
    first, second = GOOD["figures"]
    for change, expected in (
            ({"decimals": "2"}, "malformed"), ({"decimals": True}, "malformed"), ({"figures": []}, "malformed"),
            ({"figures": [first] * 7}, "malformed"), ({"figures": [{**first, "value": 4908}, second]}, "malformed"),
            ({"question": "Too short?"}, "field_length"), ({"question": "Q" * 2001}, "field_length"),
            ({"expression": "a + " * 100 + "b"}, "field_length"),
            ({"figures": [first, {**second, "value": "9" * 5000, "quote": "| 1935 | 5,900 | 557 |"}]}, "field_length"),
            ({"figures": [first, {**second, "value": "9" * 40}]}, "figure_not_a_number"),
            ({"figures": [first, {**second, "quote": "x" * 1601}]}, "field_length"),
            ({"figures": [first, {**second, "name": "a"}]}, "figure_names"),
            ({"figures": [first, {**second, "name": "B"}]}, "figure_names"),
            ({"figures": [first, {**second, "value": "about 5,900"}]}, "figure_not_a_number"),
            ({"figures": [first, {**second, "quote": "| 1935 | 5,900 | 558 |"}]}, "quote_not_verbatim_or_without_figure"),
            # the figure must be a whole number token of its quote: "908" is only a part of "4,908", "18" of "-18"
            ({"figures": [{**first, "value": "908"}, second]}, "quote_not_verbatim_or_without_figure"),
            ({"figures": [first, {"name": "b", "value": "18", "quote": "| 1936 | 5,935 | -18 |"}]},
             "quote_not_verbatim_or_without_figure"),
            ({"figures": [first, {**second, "quote": "x" * 401}]}, "quote_not_verbatim_or_without_figure"),
            ({"decimals": 5}, "expression_or_decimals_out_of_bounds"),
            ({"expression": "a + " * 60 + "b"}, "expression_or_decimals_out_of_bounds"),
            ({"expression": "a * 2"}, "expression_outside_grammar_or_figure_unused"),
            ({"expression": "a ** b"}, "expression_outside_grammar_or_figure_unused"),
            ({"expression": "(a + b) / 2", "decimals": 1}, "rounding_tie_or_trailing_zero"),  # 5404.0
            ({"expression": "(a + b + 1) / 2", "decimals": 0}, "rounding_tie_or_trailing_zero"),  # 5404.5
            ({"question": GOOD["question"] + " The 1934 total was 4,908."}, "figure_or_answer_in_question"),
            ({"question": GOOD["question"] + " Is it 20.21?"}, "figure_or_answer_in_question"),
            # ... in any spelling of the same value
            ({"question": GOOD["question"] + " The 1934 total was 4908.0."}, "figure_or_answer_in_question"),
            ({"question": GOOD["question"] + " Is it 020.210?"}, "figure_or_answer_in_question"),
            ({"question": "What is the value for u1?" + " " * 60}, "question_length")):
        assert gen.admit({**GOOD, **change}, SOURCE, set()) == (expected, None), change
    negative = {**GOOD, "figures": [first, {"name": "b", "value": "-18", "quote": "| 1936 | 5,935 | -18 |"}],
                "expression": "a + b", "decimals": 0}
    assert gen.admit(negative, SOURCE, set())[1]["answer"] == "4890"
    # a figure is the WHOLE content of a table cell of the pages, with its sign (at most "$", "%" and footnote marks
    # beside it): the cell is read in the pages, on one line, so a quote cropped around a part of a number or
    # behind its sign proves nothing; (value, quote, pages)
    whole = {("18", "18", "| 18 |"): True, ("18", "total | 18", "Total | 18 |"): True, ("18", "18", "|18|"): True,
             ("18", "18", "| $18 |"): True, ("$18", "$18", "| $18 |"): True, ("18", "18", "| 18% |"): True,
             ("18%", "18%", "| 18% |"): True, ("-18", "-18", "| -18 |"): True, ("-$18", "-$18", "| -$18 |"): True,
             ("18", "18", "| - | 18 |"): True, ("507", "507", "| 4,908 | 507 |"): True,
             ("654", "654", "| 1942-December | 654 | 47 |"): True, ("1,006", "1,006", "| 1,006 10/ | 457 |"): True,
             ("507", "507", "| 507 1/ 2/ |"): True, ("457", "457", "| 1,006 10/ | 457 |"): True,
             ("18", "18", "| 18 | 1/8 |"): True, ("18", "18", "running 18 text\n| a | 18 |"): True,
             # not a cell: running text, a line of its own between two tables, a cell with a label
             ("18", "18", "Total 18 |"): False, ("18", "18", "| Total 18 |"): False, ("18", "18", "18"): False,
             ("5.5", "5.5", "rate 5.5 percent"): False, ("8", "8", "| 1934 | 507 |\n\n8\n\n| Fiscal year | Total |"): False,
             ("18", "Total 18", "no such text"): False,
             # the sign, in any notation and also detached
             ("18", "18", "| -$18 |"): False, ("18", "$18", "| -$18 |"): False, ("-18", "-18", "| -$18 |"): False,
             ("18", "18", "| (18) |"): False, ("18", "18", "| ( 18 ) |"): False, ("18", "18", "| \u221218 |"): False,
             ("18", "18", "| \ufe6318 |"): False, ("18", "18", "| \ufe63 18 |"): False, ("18", "18", "| - 18 |"): False,
             ("18", "18", "| \u2013 18 |"): False, ("-18", "-18", "| 1942-18 |"): False,
             # a part of a longer number, of a fraction or of a word; another number in the cell
             ("908", "908", "| 4,908 |"): False, ("908", "908", "| 4, 908 |"): False, ("18", "18", "| 18, 000 |"): False,
             ("18", "18", "| 18,\n000 |"): False, ("18", "18", "| 18 .5 |"): False, ("18", "18", "| 18.5 |"): False,
             ("1", "1", "| 1e3 |"): False, ("4", "4", "| 4 1/8 |"): False, ("1", "1", "| 1/4 |"): False,
             ("4", "4", "| 1/4 |"): False, ("4", "4", "| 4 1\u20448 |"): False, ("4", "4", "| 4 1 / 8 |"): False,
             ("1", "1", "| 1 / 4 |"): False, ("4", "4", "| 1/ 4 |"): False, ("4", "4", "| 4 1,000/8 |"): False,
             ("4", "4", "| 4 " + "0" * 64 + "1/8 |"): False, ("4", "4", "| 4 " + "0" * 30 + "1/8 |"): False,
             ("100.01", "100.01", "| 100.01\u00bd |"): False, ("100", "100", "| 100 \u00bd |"): False,
             ("37,172", "37,172", "| 37,172r |"): False, ("18", "18", "| 18abc |"): False, ("12", "12", "| FY12 |"): False,
             ("18", "18", "| 18 000 |"): False, ("18", "18", "| 18 19 |"): False, ("10", "10", "| 1,006 10/ |"): False,
             ("18", "18", "| 18 100/ |"): False, ("18", "18", "| 18 1/ 2/ 3/ 4/ 5/ |"): False}
    assert {key: gen.printed(key[0], key[1], *gen.lines(key[2])) for key in whole} == whole
    text = "| 1934 |  4,908 | 507 |\n\n8\r\n|  Fiscal   year | Total |"
    assert gen.lines(text) == (shared._squash(text), [0, 23, 25])
    lost = {"question": "What amount is listed in the Total row of the table in dollars? Report a plain whole number.",
            "figures": [{"name": "a", "value": "18", "quote": "Total | -$18"}], "expression": "a", "decimals": 0}
    assert gen.admit(lost, {"question": "Source?", "context": "| Total | -$18 |"}, set()) == (
        "quote_not_verbatim_or_without_figure", None)
    stated = {**lost, "question": lost["question"] + " The listed total is 2.0 dollars.",
              "figures": [{"name": "a", "value": "2", "quote": "Total | 2"}]}
    assert gen.admit(stated, {"question": "Source?", "context": "| Total | 2 |"}, set()) == (
        "figure_or_answer_in_question", None)
    assert gen.admit({**stated, "question": lost["question"]}, {"question": "Source?", "context": "| Total | 2 |"},
                     set())[1]["answer"] == "2"
    for quote, context in (("18", "| -$18 |"), ("908", "| 4,908 |"), ("1", "| 1e3 |"), ("18", "| 18abc |"),
                           ("4", "| 4 1/8 |"), ("18", "| 18,\n000 |"), ("18", "| 18 .5 |"), ("18", "| \ufe6318 |"),
                           ("4", "| 4 1,000/8 |"), ("4", "| 4 " + "0" * 64 + "1/8 |"), ("18", "Total 18")):
        crop = {**lost, "figures": [{"name": "a", "value": quote, "quote": quote}]}
        assert gen.admit(crop, {"question": "Source?", "context": context}, set()) == (
            "quote_not_verbatim_or_without_figure", None), context
    # other notations of the answer in the question; an expression that names a figure without depending on it
    plain = {**lost, "figures": [{"name": "a", "value": "18", "quote": "Total | 18"}]}
    page = {"question": "Source?", "context": "| Total | 18 |\n| Other | 7 |"}
    assert gen.admit(plain, page, set())[1]["answer"] == "18"
    assert gen.admit({**plain, "question": lost["question"] + " The answer is 1.8e1."}, page, set()) == (
        "figure_or_answer_in_question", None)
    assert gen.admit({**plain, "question": lost["question"] + " The answer is 1.8e0001."}, page, set()) == (
        "figure_or_answer_in_question", None)
    assert gen.admit({**plain, "question": lost["question"] + " The answer is 1.8e000000001."}, page, set()) == (
        "figure_or_answer_in_question", None)
    assert gen.admit({**plain, "question": lost["question"] + " It is 18" + "0" * 401 + "e-401."}, page, set()) == (
        "figure_or_answer_in_question", None)
    # every spelling of one value is the same pair, whatever the length or padding of its exponent
    seen = gen._numbers("is it .18 or 1.8e0001 or 02 or 1,513.50 or 3e99999999999 or 0.0?")
    assert {gen._decimal(Fraction(v)) for v in ("0.18", "1.8", "18", "2", "1513.5", "3", "0")} <= seen
    assert (3, 99999999999) in seen and gen._decimal(Fraction(1, 3)) is None and gen._decimal(Fraction(-25, 2)) == (125, -1)
    assert gen._decimal(Fraction(18)) not in gen._numbers("fiscal year 1935, 13-week bills, 0.18 and 180")
    tenth = {**plain, "expression": "a / 100", "decimals": 2}
    assert gen.admit(tenth, page, set())[1]["answer"] == "0.18"
    assert gen.admit({**tenth, "question": lost["question"] + " The answer is .18."}, page, set()) == (
        "figure_or_answer_in_question", None)
    # the ANSWER must change with every figure: a substitution that cannot be evaluated proves nothing
    for expression in ("a - a", "a * 0 + 5", "a / a", "a - a + 3", "(a - 19) / (a - 19)", "5 + a / (abs(a) + 1) / 100",
                       "min(abs(a - 18), 0.5)"):  # the last one: every other value gives 0 or a rounding tie
        assert gen.admit({**plain, "expression": expression}, page, set()) == (
            "expression_outside_grammar_or_figure_unused", None), expression
    values = {"a": Fraction(5), "b": Fraction(7)}
    assert [gen.depends(e, values, 0) for e in ("a - a + b", "a * 0 + b", "a / a * b", "max(a, b)", "min(a, b)",
                                                "a + b", "abs(a - b)")] == [False] * 3 + [True] * 4
    assert gen.depends("(b - a) / a * 100", {"a": Fraction(4908), "b": Fraction(5900)}, 2)
    assert not gen.depends("min(abs(a - 18), 0.5)", {"a": Fraction(18)}, 0)  # other values: 0 or a rounding tie
    assert not gen.depends("a + b", values, 2)  # "12.00" is no valid reference in the first place
    assert not gen.depends("a / a", {"a": Fraction(-1)}, 0)  # a + 1 divides by zero: not a different answer
    assert gen.depends("max(a, b)", {"a": Fraction(3), "b": Fraction(10) ** 12}, 0)
    assert gen.depends("(a + b + c) / 3", {"a": Fraction(1), "b": Fraction(2), "c": Fraction(4)}, 2)
    assert gen.admit(GOOD, SOURCE, {gen.question_key(GOOD["question"])}) == ("duplicate_question", None)
    assert gen.admit(GOOD, {**SOURCE, "question": GOOD["question"].upper()}, set()) == ("duplicate_question", None)
    assert gen.admit("text", SOURCE, set()) == ("malformed", None)


def _study(tmp_path, monkeypatch, *, tasks=8):
    """A fixture-provenance study with an OfficeQA development panel whose pages carry a small table (the shape of
    the SearchQA generator's fixture; the real extension layout is covered by the zero-call test below)."""
    _, base, args = setup("searchqa")
    dev = {**base, "benchmark": "officeqa",
           "tasks": [{"task_id": str(i), "family_id": str(i), "project_id": "", "partition": "development",
                      "public": {"question": f"What is the value for u{i}?", "context": PAGES % f"u{i}.txt"},
                      "private": {"answer": "TRAIN-GOLD-%d" % i}} for i in range(tasks)]}
    dev_path = tmp_path / "study" / "dev_panel.json"
    write_json(dev_path, dev)
    plan = seal({"config": {"panels": {"officeqa": str(dev_path)}}})
    write_json(tmp_path / "study/ref/plan.json", plan)
    model = args["model"]
    model["transport"]["stream_wall_seconds"] = 3600
    model["max_tokens"] = tool.BUDGET_V11["solver_max_tokens"]
    protocol = {"record_hash": "p" * 64, "root": str(tmp_path / "study"),
                "references": {"officeqa": {"root": str(tmp_path / "study/ref"), "plan_hash": plan["record_hash"]}},
                "files": {str(dev_path): hashlib.sha256(dev_path.read_bytes()).hexdigest()},
                "model": model, "roles": {"officeqa": {"runtime": {}}},
                "learning_model_service": {"fixture": True}, "config": {"native_lock": str(tmp_path / "lock")}}
    split = seal({"version": tool.SPLIT_VERSION, "f_study_usage": {"officeqa": {"protocol_hash": "p" * 64}},
                  "splits": {"officeqa": {"train": [{"task_id": t["task_id"], "family_id": t["family_id"]}
                                                    for t in dev["tasks"]], "val": []}}})
    write_json(tmp_path / "split.json", split)
    monkeypatch.setattr(tool, "_study", lambda study: (tmp_path / "study", protocol))
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    monkeypatch.setattr(tool, "TRAIN", {**tool.TRAIN, "officeqa": {"families": 7}})
    return str(tmp_path / "study"), str(tmp_path / "split.json")


class Writer(API):
    """Fixture writer / reviewer: per source one sound computation, one lookup (the reviewer rejects it for the
    odd-numbered sources), one figure that is not on the pages, one answer with a trailing zero, and a fifth proposal
    beyond the per-task limit."""

    def _verifier(self, payload):
        if "pages" in payload and "computed_answer" not in payload:
            uid = payload["pages"].rsplit("item=", 1)[1].split(".txt")[0]
            first, second = GOOD["figures"]
            lookup = {"question": f"For item {uid}, what were the Veterans' Administration expenditures in fiscal year "
                                  "1935, in millions of dollars? Report a plain whole number.",
                      "figures": [{"name": "v", "value": "557", "quote": "| 1935 | 5,900 | 557 |"}],
                      "expression": "v", "decimals": 0}
            return {"tasks": [{**GOOD, "question": f"For item {uid}: " + GOOD["question"]}, lookup,
                              {**GOOD, "question": f"For item {uid}, second version: " + GOOD["question"],
                               "figures": [first, {**second, "value": "5,901"}]},
                              {**GOOD, "question": f"For item {uid}, the mean: " + GOOD["question"],
                               "expression": "(a + b) / 2", "decimals": 1},
                              {**lookup, "question": "A fifth proposal beyond the per-task limit, " + lookup["question"]}]}
        if "computed_answer" in payload:
            assert payload["source_question"].startswith("What is the value for u")
            assert payload["computed_answer"] in ("20.21", "557") and "decimals" in payload and payload["figures"]
            uid = int(payload["question"].split("item u", 1)[1].split(":")[0].split(",")[0])
            keep = payload["computed_answer"] == "20.21" or uid % 2 == 0
            return {"grounded": True, "computation": True, "unique": keep, "format": True, "distinct": True,
                    "needs_pages": True, "reason": "fixture"}
        return super()._verifier(payload)


def test_tasks_are_generated_from_training_pages_with_computed_references(tmp_path, monkeypatch):
    where = _study(tmp_path, monkeypatch)
    record = gen.prepare(*where, str(tmp_path / "g"), str(tmp_path), seed=3)
    assert record["version"] == gen.VERSION and record["benchmark"] == "officeqa"
    assert record["source_tasks"] == 7 and record["per_task"] == 4 and "no reference answer" in record["information"]
    api = Writer()
    result = gen.run(str(tmp_path / "g"), fixture_api=api)
    assert result["status"] == "completed" and result["version"] == gen.VERSION and result["source_tasks"] == 7
    assert (result["candidates_written"], result["candidates_after_filters"]) == (28, 14)
    assert 7 < result["candidates_accepted"] < 14
    path, _, checked = gen.check(str(tmp_path / "g"))
    items = json.loads(path.read_text(encoding="utf-8"))
    assert checked == result and all(set(i) == {"id", "question", "context", "answer"} for i in items)
    assert {i["answer"] for i in items} == {"20.21", "557"} and all(i["id"].startswith("gen-") for i in items)
    families = gen.family_map(str(tmp_path / "g"))
    assert set(families) == {i["id"] for i in items} and len(set(families.values())) == 7
    # every generated task keeps the pages of one of THIS seed's training tasks
    train = read_json(tmp_path / "g/panel.json")["tasks"]
    assert {i["context"] for i in items} == {t["public"]["context"] for t in train} and len(train) == 7
    # prompts carry public fields only: no reference answer of a training task
    assert len(api.prompts["verifier"]) == 7 + 14 and not api.prompts["solver"] and not api.prompts["reflection"]
    assert all("GOLD" not in prompt for prompt in api.prompts["verifier"])
    records = read_json(tmp_path / "g/records.json", sealed=True)["sources"]
    reasons = [c["filter"] for r in records for c in r["candidates"]]
    assert reasons.count("quote_not_verbatim_or_without_figure") == reasons.count("rounding_tie_or_trailing_zero") == 7
    assert all(len(r["candidates"]) == 4 for r in records)  # the fifth proposal is beyond the per-task limit
    kept = [c for r in records for c in r["candidates"] if c.get("accepted") is True]
    assert len(kept) == len(items) and all(c["figures"] and c["expression"] and "decimals" in c for c in kept)
    assert gen.run(str(tmp_path / "g"), fixture_api=api) == result and len(api.prompts["verifier"]) == 21
    # the published reference is what the frozen scorer accepts on the answer tag, and nothing else
    item = next(i for i in items if i["answer"] == "20.21")
    public = {"question": item["question"], "context": item["context"]}
    for reply, status in (("<answer>20.21</answer>", "pass"), ("<answer>20.21 million dollars</answer>", "pass"),
                          ("<answer>20.2</answer>", "fail"), ("<answer>20.21%</answer>", "fail")):
        assert backends.score("officeqa", public, {"answer": item["answer"]},
                              {"status": "available", "output": reply})["status"] == status
    # a generation is bound to its own generator: the SearchQA generator does not accept this directory, and a
    # change of this generator or of the shared lifecycle is a changed tool
    with pytest.raises(ValueError, match="No completed generation"):
        shared.check(str(tmp_path / "g"))
    with pytest.raises(ValueError, match="Tool changed"):
        shared.run(str(tmp_path / "g"), fixture_api=api)
    monkeypatch.setattr(shared, "tool_sha256", lambda: "0" * 64)
    with pytest.raises(ValueError, match="Tool changed"):
        gen.run(str(tmp_path / "g"), fixture_api=api)


def test_generated_tasks_replace_the_validation_part_of_an_officeqa_stage(tmp_path, monkeypatch):
    """``--generated-val`` on OfficeQA: the stage tool binds a completed generation made from exactly this stage's
    training tasks; the frozen SkillOpt learner (learning v9) then runs unchanged from a fixed initial instruction
    and its gate decides on the generated tasks (no validation panel exists anywhere in this fixture)."""
    from skillopt.continual_learning.skillopt import run_stage
    from tests.test_continual_learning_active_evidence import evaluate

    where = _study(tmp_path, monkeypatch)
    gen.prepare(*where, str(tmp_path / "g"), str(tmp_path), seed=3)
    generation = gen.run(str(tmp_path / "g"), fixture_api=Writer())
    text = "Read the table row and column named in the question.\n"
    (tmp_path / "b.md").write_text(text, encoding="utf-8")
    common = dict(benchmark="officeqa", method="skillopt", learning_version="v9", val_source=None)
    record = tool.prepare(*where, str(tmp_path / "stage"), str(tmp_path), parent="f:" + str(tmp_path / "b.md"), seed=3,
                          generated_val=str(tmp_path / "g"), **common)
    assert record["selection_source"].startswith("generated_from_this_stage_training_tasks")
    assert record["selection_tasks"] == generation["candidates_accepted"] and record["train_tasks"] == 7
    assert record["selection_families"] == 7 == record["generated_val"]["families"]
    assert record["generated_val"]["generator_version"] == gen.VERSION and record["parent_action"] == "fixed_text"
    value, panel = read_json(tmp_path / "stage/manifest.json", sealed=True), read_json(tmp_path / "stage/panel.json")
    selection = [t for t in panel["tasks"] if t["partition"] == "skill_confirmation"]
    assert len(selection) == record["selection_tasks"] and all(t["task_id"].startswith("gen-") for t in selection)
    assert all(t["family_id"].startswith("generated-") for t in selection) and value["parent_skill"] == text
    assert all(set(t["public"]) == {"question", "context"} and set(t["private"]) >= {"answer"} for t in selection)
    assert tool._load(str(tmp_path / "stage"))[1] == record
    with pytest.raises(ValueError, match="not made from this stage's training tasks"):  # another seed's draw
        tool.prepare(*where, str(tmp_path / "r1"), str(tmp_path), parent="f:" + str(tmp_path / "b.md"), seed=4,
                     generated_val=str(tmp_path / "g"), **common)
    v10 = tool.prepare(*where, str(tmp_path / "stage10"), str(tmp_path), benchmark="officeqa", val_source=None,
                       method="rubric_research", learning_version="v10", parent="f:" + str(tmp_path / "b.md"), seed=3,
                       generated_val=str(tmp_path / "g"))
    assert v10["selection_families"] == 7 and v10["generated_val"] == record["generated_val"]
    with pytest.raises(ValueError, match="SearchQA and OfficeQA only"):
        tool.generated_val_panel(str(tmp_path / "g"), {}, {}, "livemath", 3, {})
    with pytest.raises(ValueError, match="no test cell"):
        tool.test(str(tmp_path / "stage"), str(tmp_path / "unused"))
    seen = set()

    def spy(task, skill):
        if task["task_id"].startswith("gen-"):
            seen.add(skill)
        return evaluate("candidate_wins")(task, skill)

    result = run_stage(value, panel, tmp_path / "stage/learning", fixture_api=API(), fixture_evaluate=spy)
    assert result["status"] == "completed", result.get("reason")
    assert result["steps"][0]["gate_action"] == "accept_confirmed" and text in seen
    assert result["candidate_skill"] != text and result["candidate_skill"].startswith(text)


ROWS = ([("u%d" % i, "train", "easy", "TRAIN-GOLD-%d" % i) for i in range(1, 9)]
        + [("u9", "val", "easy", "VAL-GOLD-9"), ("u10", "val", "hard", "VAL-GOLD-10"),
           ("t1", "test", "hard", "SECRET TEST ANSWER")])


def test_a_generation_in_the_extension_study_draws_exactly_the_training_tasks_of_a_stage(tmp_path, monkeypatch):
    """Zero-call: in the real OfficeQA layout (the paper's split) a prepared generation is bound to the study, its
    pinned split and the training draw of a stage of the same seed; validation and test items are not sources."""
    from skillopt.envs.officeqa import tool_runtime
    from tests.test_continual_learning_officeqa_pilot import _upstream

    monkeypatch.setattr("tests.test_continual_learning_officeqa_pilot.ROWS", ROWS)
    up, ids = _upstream(tmp_path, monkeypatch)
    monkeypatch.setattr(tool_runtime, "build_oracle_parsed_pages_context",
                        lambda files, docs, roots, **kw: kw["evidence_note"] + "\n\n" + PAGES % files)
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    monkeypatch.setattr(tool, "TRAIN", {**tool.TRAIN, "officeqa": {"families": 7}})
    ext.data("officeqa", str(up), str(ids), str(tmp_path / "oq"), revision="r" * 40)
    base, _ = _base(tmp_path)
    ext.study(str(base), [str(tmp_path / "oq")], str(tmp_path / "X"))
    split = ext.split(str(tmp_path / "X"), str(tmp_path / "split.json"))
    where = (str(tmp_path / "X"), str(tmp_path / "split.json"))
    record = gen.prepare(*where, str(tmp_path / "g"), str(tmp_path), seed=3)
    stage = tool.prepare(*where, str(tmp_path / "s9"), str(tmp_path), benchmark="officeqa", parent="none", seed=3,
                         val_source=str(tmp_path / "oq/val_panel.json"), method="skillopt", learning_version="v9")
    train = [t for t in read_json(tmp_path / "s9/panel.json")["tasks"] if t["partition"] == "development"]
    assert record["source_tasks"] == stage["train_tasks"] == 7 and record["split_hash"] == split["record_hash"]
    assert record["source_task_hashes"] == sorted(digest(t) for t in train)
    sources = read_json(tmp_path / "g/panel.json")["tasks"]
    assert {t["task_id"] for t in sources} <= {"u%d" % i for i in range(1, 9)}
    written = "".join(path.read_text(encoding="utf-8") for path in (tmp_path / "g").glob("*.json"))
    assert "SECRET" not in written and "VAL-GOLD" not in written and "u9.txt" not in written
    assert all("family_id" in e for part in split["splits"]["officeqa"].values() for e in part)
    with pytest.raises(ValueError, match="pinned data layout|not verified"):  # a resealed split without its test part
        changed = deepcopy(split)
        changed["splits"]["officeqa"]["test"] = []
        write_json(tmp_path / "split2.json", seal({k: v for k, v in changed.items() if k != "record_hash"}))
        gen.prepare(str(tmp_path / "X"), str(tmp_path / "split2.json"), str(tmp_path / "g2"), str(tmp_path), seed=3)
    with pytest.raises((ValueError, FileNotFoundError)):  # prepared, never run: not a selection set
        tool.prepare(*where, str(tmp_path / "s9g"), str(tmp_path), benchmark="officeqa", parent="none", seed=3,
                     val_source=None, method="skillopt", learning_version="v9", generated_val=str(tmp_path / "g"))
    # a completed generation (published here by hand in the run's own formats, no call) is the selection set of
    # SkillOpt and Rubric+Research stages from the empty Skill and from a fixed instruction -- and the layout's
    # validation panel is not opened by such a stage
    items, published = [], []
    for number, task in enumerate(sorted(sources, key=digest)):
        fields = gen.admit({**GOOD, "question": f"For item {number}: " + GOOD["question"]}, task["public"], set())[1]
        item = {"filter": None, "id": "gen-%016d" % number, **fields, "review_status": "ok",
                "review": {k: True for k in gen.VERDICTS}, "accepted": True}
        published.append({"source_task_hash": digest(task), "write_status": "ok", "candidates": [item]})
        items.append(gen.task_item(task["public"], item))
    (tmp_path / "g/items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    write_json(tmp_path / "g/records.json", seal({"sources": published}))
    write_json(tmp_path / "g/result.json", seal({
        "version": gen.VERSION, "generation_hash": record["record_hash"], "status": "completed", "reason": None,
        "items": len(items), "items_sha256": hashlib.sha256((tmp_path / "g/items.json").read_bytes()).hexdigest(),
        "records_hash": read_json(tmp_path / "g/records.json", sealed=True)["record_hash"], "source_tasks": 7}))
    val_path, opened = tmp_path / "oq/val_panel.json", []
    real_open = type(val_path).open

    def spy(self, *args, **kwargs):
        if self == val_path:
            opened.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(type(val_path), "open", spy)
    (tmp_path / "b.md").write_text("Read the table row and column named in the question.\n", encoding="utf-8")
    for name, method, version, parent in (("a", "skillopt", "v9", "none"), ("b", "skillopt", "v9", "f:" + str(tmp_path / "b.md")),
                                          ("c", "rubric_research", "v10", "none"),
                                          ("d", "rubric_research", "v10", "f:" + str(tmp_path / "b.md"))):
        bound = tool.prepare(*where, str(tmp_path / ("gv-" + name)), str(tmp_path), benchmark="officeqa", parent=parent,
                             seed=3, val_source=None, method=method, learning_version=version,
                             generated_val=str(tmp_path / "g"))
        assert bound["selection_tasks"] == bound["selection_families"] == 7 == bound["train_tasks"]
        assert bound["generated_val"]["generator_version"] == gen.VERSION and "selection_is_generated" in bound["data_scope"]
        panel = read_json(tmp_path / ("gv-" + name) / "panel.json")
        assert {t["task_id"] for t in panel["tasks"] if t["partition"] == "skill_confirmation"} == {i["id"] for i in items}
        assert not {"u9", "u10", "t1"} & {t["task_id"] for t in panel["tasks"]}
        assert tool._load(str(tmp_path / ("gv-" + name)))[1] == bound
    assert opened == []
    tool.prepare(*where, str(tmp_path / "s9b"), str(tmp_path), benchmark="officeqa", parent="none", seed=3,
                 val_source=str(val_path), method="skillopt", learning_version="v9")
    assert opened  # positive control: a stage gated on the validation part does open it
    with pytest.raises(ValueError, match="no test cells"):
        tool.test(str(tmp_path / "gv-a"), str(tmp_path / "unused"))
