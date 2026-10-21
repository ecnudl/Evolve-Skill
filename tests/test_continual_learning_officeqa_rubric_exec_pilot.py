"""The exploratory executable-rubric pilot on OfficeQA (2026-10-14): structured replies are re-checked against the
pages and recomputed by the host; a derived arm scores the recomputed value. Engineering fixtures only."""
import json
from fractions import Fraction

import pytest

from scripts import pilot_officeqa_rubric_exec as pilot
from skillopt.continual_eval.core import read_json
from tests.test_continual_learning_generated_validation import _study
from tests.test_continual_learning_livemath_pilot import Client as Base
from tests.test_continual_learning_officeqa_pilot import ROWS, _upstream

PAGE = "### bulletin page 3\n| Item | Value |\n| Total | 1,234.5 |\n| Other | 42 |\n| Share | 7% |\n| Neg | -18 |"


def test_the_closed_grammar_and_the_formatting():
    v = {"a": Fraction(4908), "b": Fraction(5900)}
    value = lambda text, names=v: pilot.evaluate(text, names)[0]
    exact = lambda text, names=v: (lambda iv: iv[0] if iv[0] == iv[1] else iv)(value(text, names))
    near = lambda iv, text: iv[0] <= Fraction(text) + Fraction(1, 10 ** 6) and iv[1] >= Fraction(text) - Fraction(1, 10 ** 6) and iv[1] - iv[0] < Fraction(1, 10 ** 60)
    assert exact("(b - a) / a * 100") == Fraction(99200, 4908)  # exact over the rationals: an exact interval
    assert exact("pstdev(a, b)") != 496 and near(value("pstdev(a, b)"), "496")  # through sqrt: a tight interval around 496
    assert near(value("sstdev(a, b)"), "701.449927")  # 496 * sqrt(2)
    assert near(value("gmean(a, b)"), "5381.189459")  # sqrt(4908 * 5900)
    assert near(value("mean(a, b) + min(a, b) - max(a, b) + abs(-a) + sqrt(a * 0 + 4) + ln(exp(1)) + pow(2, 3)"), str(5404 - 992 + 4908 + 2 + 1 + 8))
    assert exact("a ^ 2", {"a": Fraction(4908)}) == 4908 ** 2 and exact("a ** -1", {"a": Fraction(42)}) == Fraction(1, 42)
    # an increment smaller than any precision cannot vanish: + - * / are exact and values are bounded to [1e-20, 1e20]
    assert exact("a + ((10**19 + 1/10**19) - 10**19)*10**19", {"a": Fraction(42)}) == 43
    outside = "expression_too_long_or_outside_character_set"
    for text, reason in (("a", "figure_unused_or_unknown_name"), ("a + c", "figure_unused_or_unknown_name"),
                         ("__import__(os) + a + b", "expression_valueerror"), ("__import__('os') + a + b", outside),
                         ("a.real + b", "expression_valueerror"), ("a / (b - b)", "expression_valueerror"),
                         ("ln(a - b)", "expression_valueerror"), ("sqrt(a - b)", "expression_valueerror"),
                         ("a ** b ** b", "expression_valueerror"), ("a ** 999", "expression_valueerror"),
                         ("a + b + 1e400", "expression_valueerror"), ("sum()", "expression_valueerror"),
                         ("a + b; a", outside), ("a + b +", "expression_not_parsable"),
                         ("a + b + \u00bd", outside), ("x" * 5000, outside), ("1+a+b+(\r2)", outside),
                         # the magnitude and size bounds on EVERY value, inside the series functions too
                         ("a + b + ((10**30 + 1/10**30) - 10**30)*10**30", "expression_valueerror"),
                         ("a * 10**999999 + b", "expression_valueerror"), ("exp(ln(a - a)) + b", "expression_valueerror"),
                         ("gmean(a, b, 0)", "expression_valueerror"), ("mean(%s) + a + b" % ",".join(["10**20"] * 11), "expression_valueerror"),
                         ("0 ** 0 + a + b", "expression_valueerror"), ("exp(100) + a + b", "expression_valueerror"),
                         ("pow(1.5, a) + b", "expression_valueerror"), ("pow(a, 64.5) + b", "expression_valueerror"),  # |exponent| <= 64
                         ("pow(a, -64.5) + b", "expression_valueerror"), ("pow(1.5, -a) + b", "expression_valueerror"),
                         ("sum(" * 190 + "a + b" + ")" * 190, "expression_valueerror")):  # depth counts through series
        got, why = pilot.evaluate(text, v)
        assert got is None and why == reason, (text, why)
    # sizes are bounded BEFORE a power is computed: nested powers of a near-one value cannot exhaust memory
    nested = "(a/a+0.00000000000000000001)"
    for _ in range(5):
        nested = "pow(%s, 64)" % nested
    assert pilot.evaluate(nested, {"a": Fraction(42)}) == (None, "expression_valueerror")
    assert exact("sum(" + ",".join(["a/7"] * 120) + ")", {"a": Fraction(42)}) == Fraction(42 * 120, 7)
    # rounding half away from zero, certified only when both bounds give the same text and no half lies between
    one = lambda x: (Fraction(x), Fraction(x))
    assert pilot.formatted(one("20.2051"), 2) == ("20.21", True) and pilot.formatted(one("20.205"), 2) == ("20.21", False)
    assert pilot.formatted(one(678077), 2) == ("678077.00", True) and pilot.formatted(one("-2.6"), 0) == ("-3", True)
    assert pilot.formatted(one("0.0004"), 2) == ("0.00", True) and pilot.formatted(one("-0.4"), 0) == ("0", True)
    assert pilot.formatted((Fraction("20.2049"), Fraction("20.2051")), 2) == ("20.20", False)  # a half inside the interval
    assert pilot.formatted((Fraction("20.2051"), Fraction("20.2052")), 2) == ("20.21", True)
    assert pilot.formatted(one("1234.5000"), "printed") == ("1234.5", True) and pilot.formatted(one(42), "printed") == ("42", True)
    assert pilot.formatted(one(Fraction(42, 2 ** 40)), "printed") == ("0.000000000038198777474462985992431640625", True)
    for interval in (one(Fraction(1, 3)), (Fraction(1), Fraction(2))):
        with pytest.raises(ValueError):
            pilot.formatted(interval, "printed")  # not terminating / not exact
    # a correct number in another spelling is never replaced; a value that differs is, keeping the percent sign;
    # an answer that is not one number is never replaced -- read on the raw text, not on its normalization
    verdict = {"verdict": "verified", "recomputed": "69"}
    assert pilot.scored_answer("69%", verdict) == ("69%", "model_answer_same_value")
    assert pilot.scored_answer("$69.00 million", verdict) == ("$69.00 million", "model_answer_same_value")
    assert pilot.scored_answer("70%", verdict) == ("69%", "recomputed") and pilot.scored_answer("70", verdict) == ("69", "recomputed")
    for found in ("[2017, 0.69]", "March 1988", "[1,2]", "01/02/2020", "1/2", "1+2", "69 and 70"):
        assert pilot.scored_answer(found, verdict) == (found, "model_answer_not_one_number"), found
    assert pilot.scored_answer(None, verdict) == (None, "model_answer") and pilot.scored_answer("70", {"verdict": "failed"}) == ("70", "model_answer")


def test_the_rubric_verifies_figures_against_the_pages_and_recomputes():
    good = ('<figures>[{"name": "a", "value": "1,234.5", "quote": "| Total | 1,234.5 |"}, {"name": "b", "value": "42", '
            '"quote": "| Other | 42 |"}]</figures><expression>(a - b) / b * 100</expression><decimals>2</decimals>'
            '<answer>2839.29</answer>')
    verdict = pilot.rubric(good, PAGE)
    assert verdict["verdict"] == "verified" and verdict["recomputed"] == "2839.29" and verdict["figures"] == 2
    assert pilot.rubric(good.replace("<decimals>2", "<decimals>printed"), PAGE)["reason"] == "value_not_representable"  # not terminating
    assert pilot.rubric(good.replace("(a - b) / b * 100", "(a + b) / 2").replace("<decimals>2", "<decimals>1"), PAGE)["reason"] == "rounding_not_certified"  # (1234.5 + 42) / 2 = 638.25: a tie at one place
    assert pilot.rubric(good.replace('"value": "42"', '"value": "4"'), PAGE) == {
        "verdict": "failed", "reason": "figure_not_a_whole_table_cell_at_quote:b", "figures": 2, "recomputed": None}
    assert pilot.rubric(good.replace("| Other | 42 |", "Other 42"), PAGE)["reason"] == "figure_not_a_whole_table_cell_at_quote:b"
    assert pilot.rubric(good.replace("(a - b) / b * 100", "a ** b ** b ** b"), PAGE)["verdict"] == "failed"
    assert pilot.rubric(good.replace("(a - b) / b * 100", "a * b * 10**20"), PAGE)["verdict"] == "failed"  # magnitude bound
    # a mathematically exact half reached through an 80-digit function is not certified either way; an error
    # amplified by later operations widens the interval instead of producing a wrong certified value
    half = ('<figures>[{"name": "b", "value": "42", "quote": "| Other | 42 |"}]</figures><expression>sqrt(b / 42 * 2) ** 2 / 4'
            '</expression><decimals>0</decimals><answer>1</answer>')
    assert pilot.rubric(half, PAGE)["reason"] == "rounding_not_certified"
    amplified = "sqrt(b / 21)**2"
    for _ in range(4):
        amplified = "(%s-(2-0.00000000000000000002))*10**20" % amplified
    assert pilot.rubric(half.replace("sqrt(b / 42 * 2) ** 2 / 4", amplified), PAGE)["reason"] == "rounding_not_certified"
    assert pilot.rubric(half.replace("sqrt(b / 42 * 2) ** 2 / 4", "sqrt(b / 21)**2").replace("<decimals>0", "<decimals>2"), PAGE)["recomputed"] == "2.00"
    # a huge exponent would amplify the base's conversion error beyond the widening: refused before anything is computed
    big = PAGE + "\n| Huge | 100000000000000000000 |\n| Near | 1.00000000000000000001 |"
    chain = ('<figures>[{"name": "a", "value": "100000000000000000000", "quote": "| Huge | 100000000000000000000 |"}, '
             '{"name": "c", "value": "1.00000000000000000001", "quote": "| Near | 1.00000000000000000001 |"}]</figures>'
             '<expression>(((pow(c**4/(4*c**3-6*c**2+4*c-1),a)-(1+2/a))*a+(2+2/a))*a-(2-2/a))*a</expression>'
             '<decimals>2</decimals><answer>3.00</answer>')
    assert pilot.rubric(chain, big)["verdict"] == "failed"
    exact = half.replace("sqrt(b / 42 * 2) ** 2 / 4", "b / 42 / 2 ** 40").replace("<decimals>0", "<decimals>printed")
    assert pilot.rubric(exact, PAGE)["recomputed"] == "0.0000000000009094947017729282379150390625"
    assert pilot.rubric(good.replace("(a - b) / b * 100", "a - b"), PAGE)["reason"] == "figure_unused_or_unknown_name" or \
        pilot.rubric(good.replace("(a - b) / b * 100", "a"), PAGE)["reason"] == "figure_unused_or_unknown_name"
    assert pilot.rubric(good.replace("<decimals>2", "<decimals>two"), PAGE)["reason"] == "decimals_field"
    assert pilot.rubric("<figures>none</figures><answer>March 1988</answer>", PAGE)["verdict"] == "not_applicable"
    assert pilot.rubric("<answer>42</answer>", PAGE)["verdict"] == "no_structure"
    assert pilot.rubric("<figures>[1, 2]</figures><answer>42</answer>", PAGE)["reason"] == "figures_shape"
    assert pilot.rubric("<figures>{bad json</figures><answer>42</answer>", PAGE)["reason"] == "figures_not_json"
    negative = ('<figures>[{"name": "n", "value": "-18", "quote": "| Neg | -18 |"}]</figures><expression>n * 2</expression>'
                '<decimals>0</decimals><answer>-36</answer>')
    assert pilot.rubric(negative, PAGE)["recomputed"] == "-36"
    assert pilot.rubric(negative.replace('"value": "-18"', '"value": "18"'), PAGE)["verdict"] == "failed"  # the sign stays
    many = json.dumps([{"name": "f%d" % i, "value": "42", "quote": "| Other | 42 |"} for i in range(121)])
    assert pilot.rubric("<figures>%s</figures><expression>f0</expression><decimals>0</decimals>" % many, PAGE)["reason"] == "figures_shape"


class Client(Base):
    """Structured arms: the right figures and expression; the model's own answer is right for u1, wrong for u2 (an
    arithmetic slip the host recomputation fixes), and a date for u3 (no figures). Plain arms: the headroom pilot's."""

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        receipt = super().call(system, '{"choices": "A. right option\\n\\nB. wrong one"}', kind, key, max_tokens, repeat)
        uid = json.loads(user)["question"].split("for ")[1].rstrip("?")
        if "machine-readable" not in system:
            return {**receipt, "response": "work <answer>%s</answer>" % {"u1": "1234.5", "u2": "41", "u3": "7"}[uid]}
        if uid == "u3":
            return {**receipt, "response": "<figures>none</figures><answer>7%</answer>"}
        value, expression, said = {"u1": ("1,234.5", "a", "1234.5"), "u2": ("42", "a * 2 / 2", "41")}[uid]
        return {**receipt, "response": '<figures>[{"name": "a", "value": "%s", "quote": "| %s | %s |"}]</figures>'
                                       '<expression>%s</expression><decimals>printed</decimals><answer>%s</answer>'
                                       % (value, "Total" if uid == "u1" else "Other", value, expression, said)}


def _prepared(tmp_path, monkeypatch):
    from skillopt.envs.officeqa import tool_runtime

    _study(tmp_path, monkeypatch)
    up, ids = _upstream(tmp_path, monkeypatch)
    monkeypatch.setattr(tool_runtime, "build_oracle_parsed_pages_context",
                        lambda files, docs, roots, **kw: "" if "u4" in files else kw["evidence_note"] + "\n\n" + PAGE)
    monkeypatch.setattr(pilot.oq, "require", lambda ok, message: None if ok or "tenth" in message else
                        (_ for _ in ()).throw(ValueError(message)))
    monkeypatch.setattr(pilot, "require", lambda ok, message: None if ok or "tenth" in message else
                        (_ for _ in ()).throw(ValueError(message)))
    (tmp_path / "b.md").write_text("Read the table.\n", encoding="utf-8")
    return pilot.prepare(str(tmp_path / "study"), str(tmp_path), str(up), str(ids), str(tmp_path / "p"),
                         ["bzero=f:" + str(tmp_path / "b.md"), "bzero_struct=f:" + str(tmp_path / "b.md") + ":struct"],
                         revision="r" * 40)


def test_a_structured_arm_yields_a_derived_arm_scored_on_the_recomputed_value(tmp_path, monkeypatch):
    record = _prepared(tmp_path, monkeypatch)
    assert [a["name"] for a in record["arms"]] == ["bzero", "bzero_struct", "bzero_struct_exec"]
    assert [a["name"] for a in record["solved_arms"]] == ["bzero", "bzero_struct"] and record["items"] == 3
    assert "SECRET" not in (tmp_path / "p/items.json").read_text(encoding="utf-8")
    client = Client()
    result = pilot.run(str(tmp_path / "p"), fixture_api=client)
    assert result["status"] == "completed", result
    assert len(client.calls) == 6  # two solved arms, three items; the derived arm makes no call
    assert result["arms"]["bzero"] == {"pass": 1, "fail": 2, "unknown": 0, "not_run": 0, "invalid_format": 0}  # u2 slip, u3 "7" vs "7%"
    assert result["arms"]["bzero_struct"] == {"pass": 2, "fail": 1, "unknown": 0, "not_run": 0, "invalid_format": 0}
    assert result["arms"]["bzero_struct_exec"] == {"pass": 3, "fail": 0, "unknown": 0, "not_run": 0, "invalid_format": 0}
    assert result["costs"]["calls"] == 6 and result["costs_complete"] is True
    rows = {p.name: read_json(p, sealed=True) for p in (tmp_path / "p/calls/bzero_struct_exec").glob("*.json")}
    assert rows["u2.json"]["rubric"]["verdict"] == "verified" and rows["u2.json"]["scored_answer"] == "42"
    assert rows["u2.json"]["scored_source"] == "recomputed" and rows["u2.json"]["model_status"] == "fail"
    assert all(rows["u2.json"][k] == 0 for k in pilot.base.COSTS) and rows["u2.json"]["derived_from"] == "bzero_struct"
    assert rows["u1.json"]["scored_source"] == "model_answer_same_value" and rows["u1.json"]["scored_answer"] == "1234.5"
    assert rows["u3.json"]["rubric"]["verdict"] == "not_applicable" and rows["u3.json"]["scored_answer"] == "7%"
    assert all(r["invalid_format"] is False for r in rows.values())
    value = pilot.report(str(tmp_path / "p"), ["bzero_struct_exec-bzero", "bzero_struct-bzero"])
    assert value["contrasts"]["bzero_struct_exec-bzero"]["estimate"] == pytest.approx(2 / 3)
    assert value["rubric"]["bzero_struct_exec"] == {
        "verdicts": {"verified": 2, "not_applicable": 1},
        "scored_from": {"recomputed": 1, "model_answer_same_value": 1, "model_answer": 1},
        "transitions": {"fixed": 1, "broke": 0, "same_pass": 2, "same_fail": 0}}
    assert pilot.run(str(tmp_path / "p"), fixture_api=client) == result and len(client.calls) == 6
    with pytest.raises(ValueError, match="at least one structured"):
        pilot.prepare(str(tmp_path / "study"), str(tmp_path), str(tmp_path / "up"), str(tmp_path / "ids"), str(tmp_path / "q"),
                      ["empty=none", "bzero=f:" + str(tmp_path / "b.md")], revision="r" * 40)
