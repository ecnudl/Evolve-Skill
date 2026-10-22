"""T-COMP-1..5: the fixed exact evaluator of <calc> tags (registration §2.4; plan §1 compute.py, §8.1)."""
from __future__ import annotations

import time
from fractions import Fraction

import pytest

from skillopt.coevo5 import forward
from skillopt.execskill import compute, protocol
from skillopt.execskill.compute import ComputeError, evaluate, evaluate_tags, exact, parse_tags, render


def failed(reason):
    return {"value": "not evaluated", "error": "computation_failed:" + reason}


# ----------------------------------------------------------------------------------------------- T-COMP-1 grammar
@pytest.mark.parametrize("expr, value", [
    ("1 + 2 * 3", "7"),
    ("(1 + 2) * 3", "9"),
    ("-4 + +2", "-2"),
    ("7 / 2", "3.5"),
    ("1 / 3", "1/3 (approximately 0.333333333333)"),
    ("-2 / 3", "-2/3 (approximately -0.666666666667)"),
    ("0.1 + 0.2", "0.3"),
    ("2 ** 12", "4096"),
    ("2 ** -2", "0.25"),
    ("abs(-3.25)", "3.25"),
    ("round(2.5)", "3"),
    ("round(-2.5)", "-3"),
    ("round(1.005, 2)", "1.01"),
    ("round(2 / 3, 4)", "0.6667"),
    ("min(3, 1, 2)", "1"),
    ("max([3, 1, 2])", "3"),
    ("sum([1.5, 2.5, 3])", "7"),
    ("sum(1, 2, 3)", "6"),
    ("(1250.5 - 1000) / 1000 * 100", "25.05"),
])
def test_grammar_values(expr, value):
    assert evaluate(expr) == {"value": value}


@pytest.mark.parametrize("expr, value", [
    ("2 \u00d7 3 \u2212 1 \u00f7 4", "5.75"),
    ("\u22122 \u00d7 (1.5 \u2212 4)", "5"),
    ("x \u00f7 3", "1/3 (approximately 0.333333333333)"),
])
def test_r6a_the_registered_signs_read_as_ascii_operators(expr, value):
    """Registration §2.4 lists + − × ÷ (registrar addendum 2026-10-22 15:5x R6 (a)); the literals stay as written and a
    doubled multiplication sign never makes a power."""
    assert evaluate(expr, {"x": "1"}) == {"value": value}
    assert compute.literals("12.50 \u00d7 3") == ["12.50", "3"]
    for doubled in ("2 \u00d7\u00d7 3", "2 *\u00d7 3", "2 \u00d7* 3"):
        assert evaluate(doubled) == failed("syntax")


@pytest.mark.parametrize("expr, reason", [
    ("'12' + 1", "literal"),
    ("1e5", "literal"),
    ("1_000 + 1", "literal"),
    ("True + 1", "literal"),
    ("math.sqrt(2)", "element"),
    ("floor(2.5)", "element"),  # frozen forward.py has floor; the registration's set is abs, round, min, max, sum
    ("1 < 2", "element"),
    ("[1, 2][0]", "element"),
    ("(lambda: 1)()", "element"),
    ("round(2.5, ndigits=1)", "arguments"),
    ("round(2.5, 13)", "arguments"),
    ("round(2.5, 0.5)", "integer_argument"),
    ("min(3)", "arguments"),
    ("sum([])", "arguments"),
    ("2 ** 0.5", "integer_argument"),
    ("0 ** -1", "exponent"),
    ("1 / (2 - 2)", "division_by_zero"),
    ("1 +", "syntax"),
    ("", "text"),
    ("1" * 301, "text"),
])
def test_grammar_rejects(expr, reason):
    assert evaluate(expr) == failed(reason)


def test_parse_tags_order_caps_and_wellformedness():
    reply = ("<calc>1+1</calc> text <calc>  </calc><calc>%s</calc>" % ("1" * 301)
             + "".join("<calc>%d*2</calc>" % i for i in range(10)))
    assert parse_tags(reply) == ["1+1"] + ["%d*2" % i for i in range(7)]
    assert parse_tags("no tags <CALC>1</CALC>") == []
    assert parse_tags(None) == []
    assert compute.MAX_CALC_TAGS == protocol.MAX_CALC_TAGS == 8


def test_rounded_and_literals_copies_agree_with_frozen_forward():
    for value in (Fraction(5, 2), Fraction(-5, 2), Fraction(1, 3), Fraction(12345, 1000), Fraction(0)):
        for decimals in range(5):
            assert compute.rounded(value, decimals) == forward.rounded(value, decimals)
    for formula in ("1 + 2.5 * (3 - 0.25)", "10 / 4 - 7", "(1.5 + 2) * 3"):
        assert compute.literals(formula) == forward.literals(formula)
        assert exact(formula) == forward.evaluate(formula)


# ------------------------------------------------------------------------------------------------ T-COMP-2 names
def test_names_bound_from_bindings():
    bindings = {"revenue": "1,234.5", "cost": "−200", "rate": "12"}
    assert evaluate("revenue + cost", bindings) == {"value": "1034.5"}
    assert evaluate("rate / 100 * revenue", bindings) == {"value": "148.14"}
    assert exact("revenue", bindings) == Fraction(24690, 20)


@pytest.mark.parametrize("expr, bindings", [
    ("x + 1", {}),
    ("x + 1", {"y": "2"}),
    ("x + 1", {"x": "12%"}),
    ("x + 1", {"x": "1,23"}),
    ("max + 1", {"max": "2"}),
    ("x + 1", {"1x": "2"}),
])
def test_names_outside_bindings_or_unusable_fail(expr, bindings):
    assert evaluate(expr, bindings) == failed("name")


# ---------------------------------------------------------------------------------------- T-COMP-3 magnitude guard
def test_magnitude_guard_refuses_towers_quickly():
    started = time.monotonic()
    assert evaluate("(((9**99)**99)**99)") == failed("exponent")
    assert evaluate("((((9**12)**12)**12)**12)") == failed("magnitude")
    assert evaluate("2 ** 12 ** 12") == failed("exponent")
    assert time.monotonic() - started < 2


def test_bit_bound_is_exact_at_4096():
    assert compute.MAX_BITS == protocol.MAX_BITS == forward.MAX_BITS == 4096
    top = {"x": str(2 ** 4095)}  # 4,096 bits: allowed
    assert exact("x", top) == 2 ** 4095
    assert evaluate("x * 2", top) == failed("magnitude")
    assert exact("x / 2", top) == 2 ** 4094
    assert evaluate("x", {"x": str(2 ** 4096)}) == failed("magnitude")


def test_power_precheck_uses_the_exact_lower_bound():
    # 2**341 has 342 bits; the frozen pre-check (342 * 12 > 4096) would refuse, the result 2**4092 fits
    assert exact("x ** 12", {"x": str(2 ** 341)}) == 2 ** 4092
    assert evaluate("x ** 12", {"x": str(2 ** 342)}) == failed("magnitude")  # 2**4104
    assert compute.MAX_EXPONENT == protocol.MAX_EXPONENT == 12 and forward.MAX_EXPONENT == 10


# ------------------------------------------------------------------------------------------------ T-COMP-4 depth
def test_bracket_depth_cap():
    assert compute.MAX_DEPTH == protocol.MAX_DEPTH == 20
    assert evaluate("(" * 20 + "1" + ")" * 20) == {"value": "1"}
    assert evaluate("(" * 21 + "1" + ")" * 21) == failed("depth")
    assert evaluate("sum([" + "(" * 19 + "1" + ")" * 19 + "])") == failed("depth")
    assert evaluate("+".join(["1"] * 24)) == {"value": "24"}  # a flat sum is not nesting
    assert evaluate("+".join(["1"] * 60)) == failed("size")  # the frozen 100-node cap


# ------------------------------------------------------------------------------------- T-COMP-5 "not evaluated"
def test_failures_are_results_with_the_registered_text():
    assert compute.NOT_EVALUATED == protocol.NOT_EVALUATED == "not evaluated"
    results = evaluate_tags(["1+1", "1/0", "y*2"], {"x": "3"})
    assert results == [{"expr": "1+1", "value": "2"},
                       {"expr": "1/0", **failed("division_by_zero")},
                       {"expr": "y*2", **failed("name")}]
    with pytest.raises(ValueError):
        evaluate_tags(["1"] * 9)


def test_watchdog_spans_the_cell():
    assert evaluate_tags(["1+1", "2+2"], watchdog_seconds=-1) == [
        {"expr": "1+1", **failed("watchdog")}, {"expr": "2+2", **failed("watchdog")}]


def test_kernel_raises_compute_error():
    with pytest.raises(ComputeError) as caught:
        exact("1/0")
    assert caught.value.reason == "division_by_zero"


@pytest.mark.parametrize("value, shown", [
    (Fraction(-42), "-42"),
    (Fraction(1, 8), "0.125"),
    (Fraction(-3, 20), "-0.15"),
    (Fraction(1, 2 ** 40), "1/1099511627776 (approximately 0.000000000001)"),
    (Fraction(1, 3 * 10 ** 15), "1/3000000000000000 (approximately 0)"),
])
def test_render(value, shown):
    assert render(value) == shown
