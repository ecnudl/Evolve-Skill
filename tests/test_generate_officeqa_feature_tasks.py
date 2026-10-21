"""Generator v3 (scripts/generate_officeqa_feature_tasks.py): v1's sound generation with series statistics,
multi-part answers and per-source target types; the held-out side shows pages only (engineering fixtures)."""
import json
import math
from pathlib import Path
import statistics
from decimal import Decimal
from fractions import Fraction

import pytest

from scripts import build_training_profile as builder
from scripts import generate_officeqa_feature_tasks as gen3
from skillopt.continual_eval.core import read_json
from tests.test_continual_learning_officeqa_diagnostic_generation import _cut
from tests.test_continual_learning_officeqa_generated_validation import API, PAGES, _study

V = {"a": Fraction(4908), "b": Fraction(5900), "c": Fraction(5935)}
XS = [4908, 5900, 5935]


@pytest.mark.parametrize("expression,expected", [
    ("mean(a, b, c)", statistics.mean(XS)), ("median(a, b, c)", 5900), ("sum(a, b, c)", sum(XS)),
    ("stdev_pop(a, b, c)", statistics.pstdev(XS)), ("stdev_samp(a, b, c)", statistics.stdev(XS)),
    ("geomean(a, b, c)", statistics.geometric_mean(XS)), ("pow(c / a, 1 / 2) - 1 + b - b", math.sqrt(5935 / 4908) - 1),
    ("(c / a) ** 0.5 - 1 + b - b", math.sqrt(5935 / 4908) - 1), ("ln(c / a) + b * 0", math.log(5935 / 4908)),
    ("sqrt(a) + exp(1) + b - b - c + c", math.sqrt(4908) + math.e),
    ("stdev_pop(a, b, c) / mean(a, b, c) * 100", statistics.pstdev(XS) / statistics.mean(XS) * 100),
    ("max(a, b, c) - min(a, b, c)", 5935 - 4908),
])
def test_the_extended_grammar_computes_series_statistics(expression, expected):
    value = gen3.evaluate(expression, V)
    assert value is not None and abs(float(value) - expected) < 1e-9 * max(1, abs(expected))


def test_correlation_and_domain_errors():
    six = {k: Fraction(v) for k, v in zip("abcdef", (1, 2, 3, 2, 4, 7))}
    r = gen3.evaluate("corr(a, b, c, d, e, f)", six)
    assert r is not None and abs(float(r) - statistics.correlation([1, 2, 3], [2, 4, 7])) < 1e-12
    for expression in ("ln(a - a + b - b)", "sqrt(a - b - c)", "geomean(a, b, -c)", "pow(a, 100) + b + c",
                       "exp(a) + b + c", "corr(a, b, c, a, b)", "a / (b - b) + c", "mean(a) + b + c"):
        assert gen3.evaluate(expression, V) is None, expression
    assert gen3.evaluate("corr(a, a, a, b, c, b)", {"a": Fraction(1), "b": Fraction(2), "c": Fraction(3)}) is None


@pytest.mark.parametrize("expression", [
    "__import__('os').system('x')", "a.real + b + c", "(lambda x: x)(a) + b + c", "[a, b, c][0] + b + c",
    "mean(*[a, b, c])", "sum(a, b, c, start=0)", "1e3 + a + b + c", "a + b", "a + b + c + d",
    "open('f') + a + b + c", "mean(a, b, c) if a else b",
])
def test_anything_outside_the_grammar_or_with_an_unused_figure_is_no_value(expression):
    assert gen3.evaluate(expression, V) is None


def test_rounding_ties_and_trailing_zeros():
    assert gen3.rounded(Decimal("2.345"), 2) is None  # an exact tie
    assert gen3.rounded(Decimal("2.3450000000001"), 2) is None  # within 1e-9 of a tie
    assert gen3.rounded(Decimal("2.346"), 2) == "2.35" and gen3.rounded(Decimal("-1.26"), 1) == "-1.3"
    assert gen3.rounded(Decimal("1.5049"), 2) is None  # "1.50": a trailing zero
    assert gen3.rounded(Decimal("1234.6"), 0) == "1235"


STDEV = {"question": "What was the population standard deviation of total general expenditures over fiscal years "
                     "1934 through 1936, in millions of dollars? Report the value rounded to three decimal places.",
         "figures": [{"name": "a", "value": "4,908", "quote": "| 1934 | 4,908 | 507 |"},
                     {"name": "b", "value": "5,900", "quote": "| 1935 | 5,900 | 557 |"},
                     {"name": "c", "value": "5,935", "quote": "| 1936 | 5,935 | -18 |"}],
         "parts": [{"expression": "stdev_pop(a, b, c)", "decimals": 3}]}
TWO = {**STDEV, "question": "Over fiscal years 1934 through 1936, what were the population standard deviation and the "
                            "mean of total general expenditures, in millions of dollars? Return both values in square "
                            "brackets: the deviation to three decimal places, then the mean as a whole number. "
                            "Answer in the format [deviation, mean].",
       "parts": [{"expression": "stdev_pop(a, b, c)", "decimals": 3}, {"expression": "mean(a, b, c)", "decimals": 0}]}


def test_admit_keeps_v1_filters_for_statistics_and_multi_part_answers():
    source = {"question": "What is the value for u1?", "context": PAGES % "u1.txt"}
    reason, fields = gen3.admit(STDEV, source, set())
    assert reason is None and fields["answer"] == gen3.rounded(Decimal(str(statistics.pstdev(XS))), 3)
    reason, fields = gen3.admit(TWO, source, set())
    assert reason is None and fields["answer"] == "[%s, 5581]" % gen3.rounded(Decimal(str(statistics.pstdev(XS))), 3)
    assert gen3.admit({**STDEV, "figures": [*STDEV["figures"][:2], {**STDEV["figures"][2], "value": "5,936"}]},
                      source, set())[0] == "quote_not_verbatim_or_without_figure"
    assert gen3.admit({**STDEV, "parts": [{"expression": "stdev_pop(a, b)", "decimals": 3}]}, source,
                      set())[0] == "expression_outside_grammar_tie_or_figure_unused"
    exact = gen3.rounded(Decimal(str(statistics.pstdev(XS))), 3)
    leak = {**STDEV, "question": STDEV["question"] + " (Hint: it is %s.)" % exact}
    assert gen3.admit(leak, source, set())[0] == "figure_or_answer_in_question"  # an approximate hint is the reviewer's
    states = {**STDEV, "question": STDEV["question"].replace("total general", "total general (5,935 in 1936)")}
    assert gen3.admit(states, source, set())[0] == "figure_or_answer_in_question"
    assert gen3.admit({**STDEV, "parts": []}, source, set())[0] == "malformed_parts"
    assert gen3.admit({**STDEV, "parts": [{"expression": "stdev_pop(a, b, c)", "decimals": 9}]}, source,
                      set())[0] == "expression_or_decimals_out_of_bounds"
    seen = {gen3.v1.question_key(STDEV["question"])}
    assert gen3.admit(STDEV, source, seen)[0] == "duplicate_question"
    flat = {"question": STDEV["question"], "figures": STDEV["figures"], "expression": "stdev_pop(a, b, c)", "decimals": 3}
    assert gen3.admit(flat, source, set())[0] is None  # a v1-style single expression is one part
    # a multi-part question states its answer template (the frozen scorer keeps the space after a comma)
    bare = {**TWO, "question": TWO["question"].replace(" Answer in the format [deviation, mean].", "")}
    assert gen3.admit(bare, source, set())[0] == "multi_part_without_answer_template"
    assert gen3.states_template("Answer in the format [x, y].", 2)
    for wrong in ("Answer in the format [x,y].", "Answer in the format [x, y, z].", "Answer in the format [x, ].",
                  "Answer as [x, y].", "Answer in the format [x, y]. Thanks.", "Answer in the format [1934, 1936]."):
        assert not gen3.states_template(wrong, 2), wrong
    # Codex (Step 1, round 2): a bracketed year interval elsewhere in the question is no answer template
    interval = {**TWO, "question": TWO["question"].replace("Over fiscal years 1934 through 1936", "Over the inclusive "
                "fiscal-year interval [1934, 1936]").replace("[deviation, mean]", "[deviation,mean]")}
    assert gen3.admit(interval, source, set())[0] == "multi_part_without_answer_template"
    from skillopt.envs.officeqa.evaluator import exact_match
    assert exact_match("[1.2, 34]", gen3.answer_text(["1.2", "34"])) and not exact_match("[1.2,34]", "[1.2, 34]")


def test_cancellation_of_huge_intermediates_is_no_value():
    # Codex (Step 1, round 1): at a fixed 60 digits, (10^64 + 123) - 10^64 evaluated to 0
    assert gen3.evaluate("(pow(10, 64) + a) - pow(10, 64)", {"a": Fraction(123)}) is None  # beyond 1e40
    assert gen3.evaluate("(pow(10, 20) + a) - pow(10, 20)", {"a": Fraction(123)}) == 123  # exact at both precisions
    # rational arithmetic is exact: a cancellation within the bound loses nothing
    big = gen3.evaluate("((pow(10, 39) + sqrt(a)) - pow(10, 39)) * pow(10, 12)", {"a": Fraction(4908)})
    assert abs(float(big) - math.sqrt(4908) * 1e12) < 1e-2
    # Codex (Step 1, round 2): a tiny term both fixed precisions dropped; exactly, the answer is 4909
    assert gen3.evaluate("((1 + pow(a, -64)) - 1) / pow(a, -64) + a", {"a": Fraction(4908)}) == 4909
    # Codex (Step 1, round 3): an irrational function of 1 + t (t ~ 1e-237) rounds its input to 1 at any fixed
    # precision; interval bounds make these uncertifiable instead of wrong
    a = {"a": Fraction(4908)}
    for expression in ("ln(1 + pow(a, -64)) / pow(a, -64) + a", "(exp(pow(a, -64)) - 1) / pow(a, -64) + a",
                       "(geomean(1 + pow(a, -64), 1 + pow(a, -64)) - 1) / pow(a, -64) + a",
                       "(pow(1 + pow(a, -64), 0.5) - 1) / pow(a, -64) + a"):
        assert gen3.evaluate(expression, a) is None and gen3.certified(expression, 0, a) is None, expression
    # a rounding amplified by 1e69: uncertified at 60 digits, certified at its exact value at 120
    amplified = "(sqrt(a) * sqrt(a) - a) * pow(10, 39) * pow(10, 30) + a"
    low = gen3.evaluate_interval(amplified, a, gen3.PRECISION)
    assert low is None or gen3.rounded(low[0], 0) != gen3.rounded(low[1], 0)
    assert gen3.certified(amplified, 0, a) == "4908"
    # every interval holds the exact value of a certified statistic
    lo, hi = gen3.evaluate_interval("stdev_pop(a, b, c)", V, gen3.PRECISION)
    exact = Decimal(str(statistics.pstdev(XS)))
    assert lo <= Fraction(exact) + Fraction(1, 10 ** 12) and hi >= Fraction(exact) - Fraction(1, 10 ** 12)
    assert hi - lo < Fraction(1, 10 ** 50)
    # an identity in a figure never depends on it, whatever its magnitude
    source = {"question": "What is the value for u1?", "context": PAGES % "u1.txt"}
    identity = {**STDEV, "figures": STDEV["figures"][:1], "parts": [{"expression": "pow(a, 64) + 1 - pow(a, 64)",
                                                                       "decimals": 0}]}
    assert gen3.admit(identity, source, set())[0] == "expression_outside_grammar_tie_or_figure_unused"
    small = {**identity, "parts": [{"expression": "pow(a, 4) + 1 - pow(a, 4)", "decimals": 0}]}
    assert gen3.admit(small, source, set())[0] == "answer_does_not_depend_on_every_figure"


def test_target_types_come_from_question_wording_only():
    t = gen3.type_of("What was the population standard deviation of monthly outlays from January 1984 to March "
                     "1987? Round to 2 decimal places.")
    assert t == {"op": "stdev", "rounding": 2, "series": True, "multi_value": False}
    assert "stdev_pop" in gen3.describe(t) and "2 decimal places" in gen3.describe(t)
    items = {"L%d" % i: {"primary_op": op, "rounding": r, "tags": tags, "answer_form": "SECRET-FORM"}
             for i, (op, r, tags) in enumerate([("stdev", 2, ["q:series"]), ("cagr", 3, []), ("lookup", None, []),
                                                ("geomean", 1, ["q:series", "q:multi_value"])])}
    one = gen3.held_out_types(items, "pages one", 7)
    assert len(one) == 2 and one[0] != one[1] and one == gen3.held_out_types(items, "pages one", 7)
    assert all(set(t) == {"op", "rounding", "series", "multi_value"} for t in one)  # never the answer form
    others = {json.dumps(gen3.held_out_types(items, "pages %d" % k, 7)) for k in range(12)}
    assert len(others) > 1


class FeatureWriter(API):
    """Writes one statistics question, one two-part question and one figure not on the pages per source; the reviewer
    accepts everything grounded. Records every payload."""

    def __init__(self):
        super().__init__()
        self.payloads = []

    def _verifier(self, payload):
        self.payloads.append(payload)
        if "computed_answer" not in payload:
            uid = payload["pages"].rsplit("item=", 1)[1].split(".txt")[0]
            return {"tasks": [{**STDEV, "question": STDEV["question"] + " (item %s)" % uid},
                              {**TWO, "question": TWO["question"].replace(" Answer in the format",
                                                                          " (item %s) Answer in the format" % uid)},
                              {**STDEV, "question": "Not on the pages (item %s): " % uid + STDEV["question"],
                               "figures": [*STDEV["figures"][:2], {**STDEV["figures"][2], "value": "6,000"}]}]}
        verdict = {k: True for k in ("grounded", "computation", "unique", "format", "needs_pages")}
        if "source_question" in payload:
            verdict["distinct"] = True
        return {**verdict, "reason": "fixture"}


def _profile(tmp_path, lh):
    dev = tmp_path / "study" / "dev_panel.json"
    value = builder.build(dev, tmp_path / "profile.json", partition="development", tasks_spec="%s:learn_tasks" % lh)
    return str(tmp_path / "profile.json"), value


def test_learn_side_shows_its_source_question_and_its_type(tmp_path, monkeypatch):
    where = _study(tmp_path, monkeypatch)
    lh, ids = _cut(tmp_path, where)
    profile, _ = _profile(tmp_path, lh)
    record = gen3.prepare(*where, str(tmp_path / "g"), str(tmp_path), side="learn", seed=3, lh_split=lh, profile=profile)
    assert record["side"] == "learn" and record["source_question_shown"] is True and record["source_tasks"] == 4
    assert "24" in record["writer_system"] and "stdev_pop" in record["writer_system"]
    api = FeatureWriter()
    result = gen3.run(str(tmp_path / "g"), fixture_api=api)
    assert result["status"] == "completed" and result["candidates_accepted"] == 8
    path, _, _ = gen3.check(str(tmp_path / "g"))
    items = json.loads(path.read_text())
    assert all(set(i) == {"id", "question", "context", "answer", "category"} for i in items)
    writes = [p for p in api.payloads if "computed_answer" not in p]
    assert writes and all(set(p) == {"pages", "source_question", "target_types"} for p in writes)
    assert all("TRAIN-GOLD" not in json.dumps(p) for p in api.payloads)  # no reference answer in any prompt
    derivations = gen3.derivations(str(tmp_path / "g"))
    assert set(derivations) == {i["id"] for i in items}
    # an item's category is its own question's operation family (the lookup sources asked for lookups)
    assert {i["category"] for i in items} == {"stdev"} and {d["type"] for d in derivations.values()} == {"stdev"}
    records = read_json(tmp_path / "g" / "records.json", sealed=True)
    accepted = [c for e in records["sources"] for c in e["candidates"] if c.get("accepted")]
    assert accepted and all(c["requested_types"] == ["lookup"] for c in accepted)
    for item in items:
        d = derivations[item["id"]]
        values = {f["name"]: gen3.v1.figure(f["value"]) for f in d["figures"]}
        assert gen3.answer_text(gen3._answers(d["parts"], values)) == item["answer"] == d["answer"]
    report = gen3.fidelity(str(tmp_path / "g"), profile, str(tmp_path / "fidelity.json"))
    assert set(report["distance"]) >= set(gen3.FIDELITY_LIMITS) and report["items"] == 8
    with pytest.raises(ValueError):
        gen3.fidelity(str(tmp_path / "g"), profile, str(tmp_path / "fidelity.json"))  # written once


def test_held_out_side_is_page_only_with_types_from_the_learn_profile(tmp_path, monkeypatch):
    where = _study(tmp_path, monkeypatch)
    lh, ids = _cut(tmp_path, where)
    profile, _ = _profile(tmp_path, lh)
    record = gen3.prepare(*where, str(tmp_path / "t"), str(tmp_path), side="held_out", seed=3, lh_split=lh,
                          profile=profile)
    assert record["side"] == "held_out" and record["source_question_shown"] is False
    assert all(len(v) <= gen3.TYPES_PER_HELD_OUT_SOURCE for v in record["targets"].values())
    api = FeatureWriter()
    assert gen3.run(str(tmp_path / "t"), fixture_api=api)["status"] == "completed"
    held = {t["public"]["question"] for t in read_json(tmp_path / "t/panel.json")["tasks"]}
    assert held and not any(q in json.dumps(p) for q in held for p in api.payloads)
    assert all(set(p) == {"pages", "target_types"} for p in api.payloads if "computed_answer" not in p)
    assert all("source_question" not in p and "distinct" not in p for p in api.payloads)
    with pytest.raises(ValueError):  # the profile must be the learn side's
        gen3.prepare(*where, str(tmp_path / "t2"), str(tmp_path), side="held_out", seed=3, lh_split=lh,
                     profile=_profile_of(tmp_path, where))
    # the learn side's ids are not enough: the records and the summary are recomputed from the training tasks
    good = json.loads(Path(profile).read_text())
    first = sorted(good["items"])[0]
    for n, tamper in enumerate((lambda v: v["profile"]["primary_op"].update({"stdev": 1.0}),
                                lambda v: v["items"][first].update({"tags": ["op:stdev"]}),
                                lambda v: v["items"][first].update({"public_digest": "0" * 64}))):
        bad = json.loads(json.dumps(good))
        tamper(bad)
        (tmp_path / ("bad%d.json" % n)).write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            gen3.prepare(*where, str(tmp_path / ("t-bad%d" % n)), str(tmp_path), side="held_out", seed=3, lh_split=lh,
                         profile=str(tmp_path / ("bad%d.json" % n)))


def _profile_of(tmp_path, where):
    dev = tmp_path / "study" / "dev_panel.json"
    builder.build(dev, tmp_path / "all.json", partition="development")
    return str(tmp_path / "all.json")
