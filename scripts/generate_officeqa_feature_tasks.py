"""Generate FEATURE-AWARE OfficeQA tasks from one side of an L/H split of a stage's training tasks (generator v3,
2026-10-16; design docs/handoff/two-architectures-design-20261016.md section 4).

Everything that makes a v1/v2 generated task sound is kept: the writer never states an answer; every figure is
quoted verbatim and is the whole content of a table cell of the pages (``v1.printed``); the answer is computed on the
host from the figures by a closed grammar that is parsed and walked, never executed; the answer must depend on every
figure; no figure or answer may appear in the question; questions are deduplicated against the source, training and
earlier generated questions; an independent reviewer checks each question. What changes, because the 10/16 profile
showed the v1/v2 items covering none of the statistics that 46% of the training questions ask for:

- the grammar adds ``sqrt ln exp pow`` (and ``**``) and the series functions ``mean median sum stdev_pop stdev_samp
  geomean corr`` over up to 24 figures, evaluated in 60-digit decimal arithmetic; a rounding tie is any value within
  1e-9 of a half unit of the last kept digit;
- a question may ask for up to three values ("parts", each with its own rounding), answered as a bracketed list;
- every question has a TARGET TYPE given in its payload: on the learn side the type of the source question (its
  operation family, rounding, series and multi-value shape, read by ``skillopt.skill_features.tagger`` from the
  question only, never from its reference answer); on the held-out side (pages only, no question of that side in any
  prompt) two types drawn, per source, from the question-derived tags of the LEARN-side training profile.

Fidelity (zero calls, after a run): ``fidelity`` tags the accepted items and compares their profile with the
training profile (total-variation distance per axis against registered limits).

Usage:
  generate_officeqa_feature_tasks.py prepare --side learn|held_out --study <study> --split <split> --repo <repo>
      --seed <stage seed> --lh-split <L/H split.json> --profile <learn-side training profile.json> --output <new dir>
  generate_officeqa_feature_tasks.py run --output <dir>
  generate_officeqa_feature_tasks.py check --output <dir>
  generate_officeqa_feature_tasks.py fidelity --output <dir> --profile <training profile.json> --report <new.json>
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import random
import re
import sys
from copy import deepcopy
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, DivisionByZero, InvalidOperation, Overflow, getcontext, localcontext
from fractions import Fraction
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_officeqa_tasks as v1  # noqa: E402
from scripts import generate_searchqa_tasks as base  # noqa: E402
from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402
from skillopt.skill_features import profile as fp  # noqa: E402
from skillopt.skill_features import tagger  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

VERSION = "generated-officeqa-tasks-v3-feature-aware"
BENCHMARK = v1.BENCHMARK
PER_TASK = 4
MAX_FIGURES, MAX_PARTS, MAX_EXPRESSION, MAX_DECIMALS, MAX_DEPTH = 24, 3, 400, 4, 16
# Every value is carried as a rational interval [lo, hi] that certainly holds the exact value: rational operations are
# exact on the bounds; an irrational function (sqrt, ln, exp, a fractional power, the standard deviations, geomean,
# corr) is evaluated at a decimal precision on outward-rounded inputs and widened by a hundred units of its last digit.
# A part has an answer only when both ends of its interval round to the same text (certified rounding), tried at
# PRECISION and, failing that, at CHECK_PRECISION digits. Every expression node's interval stays below
# MAX_INTERMEDIATE in magnitude and MAX_BITS in its numerators and denominators. ``evaluate`` reports a value only
# when its interval is narrower than 10^-AGREEMENT of max(|value|, 1).
PRECISION, CHECK_PRECISION, AGREEMENT = 60, 120, 25
MAX_POW_LOG = 100  # |y * ln(x)| of a fractional power
MAX_INTERMEDIATE, MAX_BITS = Fraction(10) ** 40, 50000
TIE_MARGIN = Fraction(1, 10 ** 9)  # of a unit of the last kept digit
MAX_MAGNITUDE = Fraction(10) ** 15
MAX_EXPONENT = 64  # |y| of pow(x, y)
MAX_EXP_ARGUMENT = 50
TYPES_PER_HELD_OUT_SOURCE = 2
# registered fidelity limits (design section 4): total-variation distance of the accepted items' profile to the
# training profile, per axis
FIDELITY_LIMITS = {"primary_op_tv": 0.25, "answer_form_tv": 0.20, "rounding_tv": 0.25}

_SCALAR = {"abs": (1, 1), "sqrt": (1, 1), "ln": (1, 1), "exp": (1, 1), "pow": (2, 2), "min": (2, MAX_FIGURES),
           "max": (2, MAX_FIGURES)}
_SERIES = {"mean": 2, "median": 2, "sum": 2, "stdev_pop": 2, "stdev_samp": 2, "geomean": 2, "corr": 6}
_ARITHMETIC = re.compile(r"[a-z0-9_+\-*/()., ]+")
# a multi-part question ends with the fixed sentence "Answer in the format [x, y]." -- one placeholder word per part,
# a comma and a space between them (the scorer drops commas and brackets but keeps spaces: "[1.2,3.4]" never matches
# "[1.2, 3.4]")
_TEMPLATE = re.compile(r"Answer in the format \[([^\[\]]{1,200})\]\.$")
_PLACEHOLDER = re.compile(r"[A-Za-z][A-Za-z_-]*(?: [A-Za-z_-]+){0,4}")

OP_TEXT = {
    "cv": "a coefficient of variation of a series of printed values: stdev_pop(...) / mean(...) or "
          "stdev_samp(...) / mean(...), as the question states, possibly in percent",
    "stdev": "a standard deviation of a series of printed values; the question says population (stdev_pop) or "
             "sample (stdev_samp)",
    "geomean": "a geometric mean of a series of printed values (geomean)",
    "cagr": "a compound annual growth rate between two printed values a stated number of years apart: "
            "pow(b / a, 1 / years) - 1, usually in percent",
    "log_growth": "a continuously compounded (logarithmic) growth rate: ln(b / a), possibly per year",
    "log": "a natural logarithm of a printed value or of a ratio of printed values (ln), possibly averaged",
    "correlation": "a Pearson correlation coefficient between two printed series of equal length (corr)",
    "trend": "a projection: a printed value continued at a growth rate computed from printed values (pow), or a "
             "linear extrapolation from printed values",
    "order_stat": "a median of a series of printed values (median), or another order statistic expressible with "
                  "median/min/max",
    "which_period": "the largest or smallest value of a series of printed values (max/min), or its difference to "
                    "another printed value",
    "mean": "an arithmetic mean of a series of printed values (mean)",
    "pp_change": "a change in percentage points between two shares computed from printed values",
    "percent_change": "a percent change between two printed values",
    "share": "a share or ratio of printed values, possibly in percent",
    "sum": "a sum of several printed values, possibly converted to another unit",
    "difference": "a difference between printed values (absolute or signed, as the question states)",
    "extreme": "the largest or smallest value of a series of printed values (max/min), possibly combined with "
               "another value",
    "count": "a value computed over a series of printed values",
    "lookup": "one printed value converted to another unit, or combined with one other printed value",
}

WRITER = (
    "You write evaluation questions for a document question-answering task over U.S. Treasury Bulletin pages. "
    "{source} Write up to {count} NEW questions over these pages, each a precise, self-contained request that names "
    "the table or series, the periods and the unit as needed, each about DIFFERENT figures than the others{distinct}.\n"
    "TARGET TYPE: the payload's \"target_types\" lists the question type(s) wanted, in order of preference. Every "
    "question must have one of these types (the first one the pages support): the same kind of computation, the "
    "same rounding style, a series of similar length when the type names one, and several requested values when "
    "the type asks for them. If the pages support none of the types, return fewer questions or none -- never a "
    "simpler type instead.\n"
    "Do NOT state an answer. For each question give instead:\n"
    "- \"figures\": the one to {figures} printed figures the answer is computed from. For each figure: a short "
    "lower-case \"name\" (a, b, c, ... or a1, a2, ...), its \"value\" exactly as printed (digits with their commas, "
    "decimal point and minus sign, for example \"1,513\" or \"-18\" or \"4.73\"), and a \"quote\": a verbatim excerpt "
    "of the pages (at most 300 characters; for a table the row with its label) that contains this value;\n"
    "- \"parts\": one entry per value the question asks for (one to {parts}); each part has an \"expression\" over "
    "the figure names and \"decimals\", the number of decimal places that value is rounded to (0 to {decimals}). "
    "An expression may use + - * / ** parentheses, plain numbers, and the functions abs(x), sqrt(x), ln(x), exp(x), "
    "pow(x, y), min(...), max(...), and over a list of figures mean(...), median(...), sum(...), stdev_pop(...), "
    "stdev_samp(...), geomean(...), and corr(x1, ..., xn, y1, ..., yn) for two series of equal length -- for "
    "example \"stdev_pop(a1, a2, a3, a4, a5, a6)\", \"pow(b / a, 1 / 8) - 1\" or \"(b - a) / a * 100\".\n"
    "Requirements:\n"
    "- the pages alone are enough to answer, and only one reading of the question fits them;\n"
    "- the question says exactly which unit each value is in and how it is rounded, says which statistic or "
    "convention it means (population or sample, percent or ratio, which periods are included), asks for plain "
    "numbers, and never states any of the figures it needs; a question asking for several values ends with the "
    "sentence \"Answer in the format [x, y].\" naming one short placeholder word per value (letters only, no digits), "
    "in the order asked, a comma and a space between them -- for example \"Answer in the format [deviation, mean].\";\n"
    "- use only figures that are legible and unambiguous in the pages (nothing read off a chart, nothing "
    "estimated), and only figures that stand alone in a table cell: the cell holds just the number, possibly with "
    "a currency or percent sign or a footnote mark -- no numbers from running text, no dates, no fractions, no "
    "cells with letters or several numbers.\n"
    "Return one JSON object and nothing else: {{\"tasks\": [{{\"question\": \"...\", \"figures\": [{{\"name\": "
    "\"a\", \"value\": \"...\", \"quote\": \"...\"}}], \"parts\": [{{\"expression\": \"...\", \"decimals\": 0}}]}}]}}")
_LEARN_SOURCE = "You are given ONE source item: a question and the parsed page(s) it was asked about."
_HELD_OUT_SOURCE = "You are given the parsed page(s) of ONE source document."
REVIEWER = (
    "You check an evaluation question against parsed U.S. Treasury Bulletin pages. You are given the pages, "
    "{source}a new question, the figures its answer is computed from (each with its printed value and a quote of the "
    "pages), one arithmetic expression per requested value with its number of decimal places, and the values "
    "computed from them (functions: mean, median, sum, stdev_pop = population and stdev_samp = sample standard "
    "deviation, geomean, corr = Pearson correlation of the first half of its arguments with the second half, ln = "
    "natural logarithm, pow, sqrt, exp, abs, min, max). Decide {count} things:\n"
    "- grounded: is every figure the value the pages print for exactly the thing the question refers to (the right "
    "table, row, column, period and unit)?\n"
    "- computation: does each expression compute exactly what the question asks for, in the stated convention, "
    "including any unit conversion, and does the question ask for this rounding and this order of values?\n"
    "- unique: do the pages support only this reading and these values (no other table, revision or footnote that "
    "fits the question equally well)?\n"
    "- format: does the question state the unit and the rounding of each value, so that the computed values written "
    "as plain numbers (several in a bracketed list) are the only correctly formatted answer?\n"
    "{distinct}"
    "- needs_pages: can the question be answered only by reading the pages -- it neither states nor hints at its "
    "answer or at any of its figures (in digits, in words or in any other notation), and its answer does not follow "
    "from the wording of the question alone?\n"
    "Return one JSON object and nothing else: {{\"grounded\": true|false, \"computation\": true|false, \"unique\": "
    "true|false, \"format\": true|false, {distinct_key}\"needs_pages\": true|false, \"reason\": "
    "\"at most 200 characters\"}}")
_DISTINCT = ("- distinct: does the question ask for something else than the source question does (not a paraphrase "
             "of it and not the same figure)?\n")
FILTERS = (v1.FILTERS.replace("one to six figures", "one to twenty-four figures")
           + "; v3: one to three parts, each an expression of at most 400 ASCII chars over the v1 grammar plus "
             "sqrt/ln/exp/pow/** and the series functions mean/median/sum/stdev_pop/stdev_samp/geomean (2-24 "
             "arguments) and corr (an even number of 6-24 arguments), evaluated in rational interval arithmetic "
             "(exact bounds; the irrational functions on outward-rounded inputs at 60, else 120 digits, widened by a "
             "hundred units of their last digit) -- a part has an answer only when both ends of its interval round to "
             "it -- with domain checks (sqrt of a negative, ln or geomean of a non-positive, |exponent| > 64, exp of "
             "more than 50, a constant series in corr are no value) and every node's interval below 1e40; a "
             "multi-part question ends with \"Answer in the format [x, y].\" (one placeholder word "
             "per part, a comma and a space between); every figure used by some part; a part is a tie when it "
             "lies within 1e-9 of a half unit of its last kept digit; each figure changes some part's answer; no "
             "figure and no part's answer in the question; plain arithmetic text only")


def tool_sha256():
    """The generator's identity: this file, v1 (whose filters it reuses), the tagger and profile code, and the
    shared lifecycle."""
    parts = [base._sha(Path(__file__)), v1.tool_sha256(), base._sha(PROJECT_ROOT / "skillopt/skill_features/tagger.py"),
             base._sha(PROJECT_ROOT / "skillopt/skill_features/profile.py")]
    return hashlib.sha256("".join(parts).encode()).hexdigest()


# ----------------------------------------------------------------------------- the grammar (interval arithmetic)
ONE = (Fraction(1), Fraction(1))


def _point(x):
    return (Fraction(x), Fraction(x))


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _neg(a):
    return (-a[1], -a[0])


def _sub(a, b):
    return (a[0] - b[1], a[1] - b[0])


def _mul(a, b):
    products = (a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1])
    return (min(products), max(products))


def _div(a, b):
    if b[0] <= 0 <= b[1]:
        raise ZeroDivisionError("division by an interval that holds 0")
    return _mul(a, (1 / b[1], 1 / b[0]))


def _abs(a):
    if a[0] >= 0:
        return a
    if a[1] <= 0:
        return _neg(a)
    return (Fraction(0), max(-a[0], a[1]))


def _int_power(a, n):
    if n < 0:
        if a[0] <= 0 <= a[1]:
            raise ZeroDivisionError("zero to a negative power")
        return _div(ONE, _int_power(a, -n))
    if n == 0:
        return ONE
    lo, hi = a[0] ** n, a[1] ** n
    if n % 2 or a[0] >= 0:
        return (lo, hi)
    if a[1] <= 0:
        return (hi, lo)
    return (Fraction(0), max(lo, hi))


def _outward(x, rounding):
    """A decimal at the current precision on the given side of the rational ``x``."""
    with localcontext() as ctx:
        ctx.rounding = rounding
        return Decimal(x.numerator) / Decimal(x.denominator)


def _increasing(function, a):
    """An interval holding function(x) for every x in ``a``, for an increasing decimal function at the current
    precision: outward-rounded inputs, the results widened by a hundred units of their last digit."""
    precision = getcontext().prec
    lo, hi = function(_outward(a[0], ROUND_FLOOR)), function(_outward(a[1], ROUND_CEILING))
    margin = lambda r: abs(Fraction(r)) / 10 ** (precision - 2) + Fraction(1, 10 ** (2 * precision))
    return (Fraction(lo) - margin(lo), Fraction(hi) + margin(hi))


def _sqrt(a):
    if a[0] < 0:
        raise ValueError("sqrt of a negative value")
    return _increasing(Decimal.sqrt, a)


def _ln(a):
    if a[0] <= 0:
        raise ValueError("ln of a non-positive value")
    return _increasing(Decimal.ln, a)


def _exp(a, bound=MAX_EXP_ARGUMENT):
    if max(abs(a[0]), abs(a[1])) > bound:
        raise ValueError("exp argument too large")
    return _increasing(Decimal.exp, a)


def _mean(args):
    total = args[0]
    for x in args[1:]:
        total = _add(total, x)
    return _div(total, _point(len(args)))


def _series_value(name, args):
    n = len(args)
    if name == "sum":
        return _mul(_mean(args), _point(n))
    if name == "mean":
        return _mean(args)
    if name == "median":  # median is increasing in every argument
        lows, highs = sorted(a[0] for a in args), sorted(a[1] for a in args)
        pick = lambda xs: xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
        return (pick(lows), pick(highs))
    if name in ("stdev_pop", "stdev_samp"):
        m = _mean(args)
        squares = _mean([_int_power(_sub(x, m), 2) for x in args])
        return _sqrt(_mul(squares, _point(Fraction(n, n if name == "stdev_pop" else n - 1))))
    if name == "geomean":
        if any(x[0] <= 0 for x in args):
            raise ValueError("geomean of a non-positive value")
        return _exp(_mean([_ln(x) for x in args]), MAX_POW_LOG)
    # corr: the first half of the arguments against the second half
    if n % 2:
        raise ValueError("corr needs two series of equal length")
    xs, ys = args[: n // 2], args[n // 2:]
    mx, my = _mean(xs), _mean(ys)
    sxy = _mean([_mul(_sub(x, mx), _sub(y, my)) for x, y in zip(xs, ys)])
    sxx = _mean([_int_power(_sub(x, mx), 2) for x in xs])
    syy = _mean([_int_power(_sub(y, my), 2) for y in ys])
    if sxx[0] <= 0 or syy[0] <= 0:
        raise ValueError("corr of a constant (or not certainly varying) series")
    return _div(sxy, _sqrt(_mul(sxx, syy)))


def _power(x, y):
    if max(abs(y[0]), abs(y[1])) > MAX_EXPONENT:
        raise ValueError("exponent too large")
    if y[0] == y[1] and y[0].denominator == 1:
        return _int_power(x, int(y[0]))
    if x[0] <= 0:
        raise ValueError("a non-positive base to a fractional power")
    return _exp(_mul(y, _ln(x)), MAX_POW_LOG)


def _walk_at(tree, expression, values, precision):
    """(interval, figure names used) of a parsed expression with the irrational functions at ``precision`` significant
    digits; raises outside the grammar, a function's domain or the node bounds."""
    seen = set()

    def bounded(value):
        for end in value:
            if (abs(end) >= MAX_INTERMEDIATE or end.numerator.bit_length() > MAX_BITS
                    or end.denominator.bit_length() > MAX_BITS):
                raise ValueError("An intermediate value is out of bounds")
        return value

    def walk(node, depth):
        return bounded(step(node, depth))

    def step(node, depth):
        require(depth <= MAX_DEPTH, "Expression too deep")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            spelling = expression[node.col_offset:node.end_col_offset]
            require(v1._LITERAL.fullmatch(spelling) is not None, "Constant outside the grammar")
            return _point(Fraction(spelling))
        if isinstance(node, ast.Name) and node.id in values:
            seen.add(node.id)
            return _point(values[node.id])
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.USub, ast.UAdd):
            value = walk(node.operand, depth + 1)
            return _neg(value) if type(node.op) is ast.USub else value
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left, depth + 1), walk(node.right, depth + 1)
            if type(node.op) is ast.Add:
                return _add(left, right)
            if type(node.op) is ast.Sub:
                return _sub(left, right)
            if type(node.op) is ast.Mult:
                return _mul(left, right)
            if type(node.op) is ast.Div:
                return _div(left, right)
            if type(node.op) is ast.Pow:
                return _power(left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name, args = node.func.id, node.args
            if name in _SCALAR and _SCALAR[name][0] <= len(args) <= _SCALAR[name][1]:
                xs = [walk(a, depth + 1) for a in args]
                if name == "abs":
                    return _abs(xs[0])
                if name == "min":
                    return (min(x[0] for x in xs), min(x[1] for x in xs))
                if name == "max":
                    return (max(x[0] for x in xs), max(x[1] for x in xs))
                if name == "sqrt":
                    return _sqrt(xs[0])
                if name == "ln":
                    return _ln(xs[0])
                if name == "exp":
                    return _exp(xs[0])
                return _power(xs[0], xs[1])
            if name in _SERIES and _SERIES[name] <= len(args) <= MAX_FIGURES:
                return _series_value(name, [walk(a, depth + 1) for a in args])
        raise ValueError("Outside the expression grammar")

    with localcontext() as ctx:
        ctx.prec = precision
        ctx.traps[InvalidOperation] = ctx.traps[DivisionByZero] = ctx.traps[Overflow] = True
        return walk(tree.body, 0), seen


def evaluate_interval(expression, values, precision, used=None):
    """(lo, hi): rationals that certainly bound the expression's exact value over the named figures (``values``:
    name -> Fraction), the irrational functions evaluated at ``precision`` digits; or None outside the grammar, outside
    a function's domain, beyond a node bound or the magnitude bound, or when ``used`` is None and a figure is left
    unused. When ``used`` is a set, the names the expression uses are added to it and unused figures are allowed (a
    part of a multi-part question). Parsed and walked, never compiled or executed."""
    if not expression.isascii() or "\n" in expression or "\r" in expression or len(expression) > MAX_EXPRESSION:
        return None
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    try:
        interval, seen = _walk_at(tree, expression, values, precision)
    except (ValueError, ArithmeticError, RecursionError):
        return None
    if max(abs(interval[0]), abs(interval[1])) >= MAX_MAGNITUDE:
        return None
    if used is None:
        return interval if seen == set(values) else None
    used.update(seen)
    return interval


def evaluate(expression, values, used=None):
    """The expression's value (the middle of its CHECK_PRECISION interval, exact for a rational expression), or None
    as for ``evaluate_interval`` or when the interval is wider than 10^-AGREEMENT of max(|value|, 1)."""
    interval = evaluate_interval(expression, values, CHECK_PRECISION, used)
    if interval is None:
        return None
    middle = (interval[0] + interval[1]) / 2
    return middle if interval[1] - interval[0] <= Fraction(1, 10 ** AGREEMENT) * max(abs(middle), Fraction(1)) else None


def rounded(value, decimals):
    """The value (a Fraction or a Decimal) at ``decimals`` places as plain text, or None for a near-tie (within
    TIE_MARGIN of a half unit) or a trailing zero after the decimal point (v1's rule). Exact."""
    scaled = Fraction(value) * 10 ** decimals
    whole = math.floor(scaled)
    rest = scaled - whole
    if abs(rest - Fraction(1, 2)) < TIE_MARGIN:
        return None
    whole += 1 if rest > Fraction(1, 2) else 0
    digits = str(abs(whole)).rjust(decimals + 1, "0")
    text = digits[:-decimals] + "." + digits[-decimals:] if decimals else digits
    if decimals and text.endswith("0"):
        return None
    return ("-" if whole < 0 else "") + text


def certified(expression, decimals, values, used=None):
    """The answer text of one part when both ends of its interval round to it (at PRECISION, else at
    CHECK_PRECISION digits), or None."""
    for precision in (PRECISION, CHECK_PRECISION):
        interval = evaluate_interval(expression, values, precision, used)
        if interval is None:
            return None
        low, high = rounded(interval[0], decimals), rounded(interval[1], decimals)
        if low is not None and low == high:
            return low
    return None


def _answers(parts, values):
    """[certified answer of each part], or None when some part has none or some figure is used by no part."""
    used, out = set(), []
    for part in parts:
        answer = certified(part["expression"], part["decimals"], values, used)
        if answer is None:
            return None
        out.append(answer)
    return out if used == set(values) else None


def depends(parts, values):
    """Every figure changes some part's answer to another valid answer (v1's ``depends``, over all parts)."""
    reference = _answers(parts, values)
    if reference is None:
        return False
    for name, value in values.items():
        others = [v for other, v in values.items() if other != name]
        trials = [value + 1, value - 1, 2 * value + 1, value + 3, value + 10 ** 6, value - 10 ** 6]
        trials += [v + shift for v in others[:6] for shift in (1, -1)]
        if not any(_answers(parts, {**values, name: t}) not in (None, reference) for t in trials):
            return False
    return True


def answer_text(answers):
    return answers[0] if len(answers) == 1 else "[" + ", ".join(answers) + "]"


def states_template(question, parts):
    """Does a multi-part question end with the fixed sentence "Answer in the format [x, y]." -- exactly one
    placeholder per part (one to five words of letters, _ or -; no digit), a comma and a space between them?"""
    match = _TEMPLATE.search(question.strip())
    names = match.group(1).split(", ") if match else []
    return len(names) == parts and all(_PLACEHOLDER.fullmatch(name) for name in names)


def _parts(candidate):
    """The candidate's parts as [{expression, decimals}] (a v1-style single expression is one part), or None."""
    if "parts" in candidate:
        parts = candidate["parts"]
        if type(parts) is not list or not 1 <= len(parts) <= MAX_PARTS:
            return None
    else:
        parts = [{"expression": candidate.get("expression"), "decimals": candidate.get("decimals")}]
    if any(type(p) is not dict or type(p.get("expression")) is not str or type(p.get("decimals")) is not int
           or len(p["expression"]) > 2 * MAX_EXPRESSION for p in parts):
        return None
    return [{"expression": base._squash(p["expression"]), "decimals": p["decimals"]} for p in parts]


def admit(candidate, source, seen_questions):
    """(None, the fields of the candidate's record incl. its computed answer) for a survivor of the deterministic
    filters, else (the first reason it fails, None). v1's checks, extended to v3's figures, parts and grammar."""
    if (type(candidate) is not dict or type(candidate.get("question")) is not str
            or type(candidate.get("figures")) is not list or not 1 <= len(candidate["figures"]) <= MAX_FIGURES
            or any(type(f) is not dict or any(type(f.get(k)) is not str for k in ("name", "value", "quote"))
                   for f in candidate["figures"])):
        return "malformed", None
    parts = _parts(candidate)
    if parts is None:
        return "malformed_parts", None
    if (not 60 <= len(candidate["question"]) <= 2000
            or any(len(f["name"]) > 16 or len(f["value"]) > 2 * v1.MAX_VALUE or len(f["quote"]) > 4 * v1.MAX_QUOTE
                   for f in candidate["figures"])):
        return "field_length", None
    question = base._squash(candidate["question"])
    figures = [{k: base._squash(f[k]) for k in ("name", "value", "quote")} for f in candidate["figures"]]
    if not 60 <= len(question) <= 900:
        return "question_length", None
    if len({f["name"] for f in figures}) != len(figures) or any(v1._NAME.fullmatch(f["name"]) is None for f in figures):
        return "figure_names", None
    (pages, starts), values = v1.lines(source["context"]), {}
    for item in figures:
        value = v1.figure(item["value"])
        if value is None:
            return "figure_not_a_number", None
        if not 1 <= len(item["quote"]) <= v1.MAX_QUOTE or not v1.printed(item["value"], item["quote"], pages, starts):
            return "quote_not_verbatim_or_without_figure", None
        values[item["name"]] = value
    if any(not 0 <= p["decimals"] <= MAX_DECIMALS or not _ARITHMETIC.fullmatch(p["expression"]) for p in parts):
        return "expression_or_decimals_out_of_bounds", None
    answers = _answers(parts, values)
    if answers is None:
        return "expression_outside_grammar_tie_or_figure_unused", None
    if not depends(parts, values):
        return "answer_does_not_depend_on_every_figure", None
    if len(parts) > 1 and not states_template(question, len(parts)):
        return "multi_part_without_answer_template", None
    stated = v1._numbers(question)
    if stated & {v1._decimal(v) for v in values.values()} or stated & {v1._decimal(Fraction(a)) for a in answers}:
        return "figure_or_answer_in_question", None
    key = v1.question_key(question)
    if key in seen_questions or ("question" in source and key == v1.question_key(source["question"])):
        return "duplicate_question", None
    return None, {"question": question, "figures": figures, "parts": parts, "answer": answer_text(answers)}


# ----------------------------------------------------------------------------- target types
def type_of(question):
    """The target type of a question, from its wording only (no reference answer): its tagger operation family,
    rounding requirement, series shape and multi-value shape."""
    record = tagger.tag_item(question, None, None)
    return {"op": record["primary_op"], "rounding": record["rounding"], "series": "q:series" in record["tags"],
            "multi_value": "q:multi_value" in record["tags"]}


def describe(target):
    rounding = target["rounding"]
    text = OP_TEXT.get(target["op"], OP_TEXT["lookup"])
    if target["series"]:
        text += ", over a series of several periods (months, quarters or years)"
    if target["multi_value"]:
        text += "; the question asks for two or three values (several parts)"
    if isinstance(rounding, int):
        text += "; " + ("rounded to a whole number" if rounding == 0 else "rounded to %d decimal places" % rounding)
    return text


def held_out_types(profile_items, pages, seed):
    """TYPES_PER_HELD_OUT_SOURCE distinct types drawn for one held-out source from the learn-side profile's items
    (each a whole item's question-derived tags, so the joint distribution is kept), seeded by the stage seed and the
    source's pages."""
    rng = random.Random(digest({"seed": seed, "pages": hashlib.sha256(pages.encode()).hexdigest(), "version": VERSION}))
    pool = [{"op": r["primary_op"], "rounding": r["rounding"], "series": "q:series" in r["tags"],
             "multi_value": "q:multi_value" in r["tags"]} for _, r in sorted(profile_items.items())]
    out = []
    for target in rng.sample(pool, len(pool)):
        if target not in out:
            out.append(target)
        if len(out) == TYPES_PER_HELD_OUT_SOURCE:
            break
    return out


# ----------------------------------------------------------------------------- one side of a generation
class Kind:
    """One side of a v3 generation, with the attributes and functions the shared lifecycle reads from a generator."""

    VERSION, BENCHMARK, PER_TASK, FILTERS = VERSION, BENCHMARK, PER_TASK, FILTERS

    def __init__(self, side, targets):
        require(side in ("learn", "held_out"), "Unknown side")
        self.SIDE = side
        self.SOURCE_QUESTION_SHOWN = side == "learn"
        # side substitutions by replace: the template's doubled braces stay for the one format(count=...) at prepare
        self.WRITER = (WRITER.replace("{source}", _LEARN_SOURCE if side == "learn" else _HELD_OUT_SOURCE)
                       .replace("{distinct}", " and than the source question" if side == "learn" else "")
                       .replace("{figures}", str(MAX_FIGURES)).replace("{parts}", str(MAX_PARTS))
                       .replace("{decimals}", str(MAX_DECIMALS)))
        self.REVIEWER = REVIEWER.format(source="the source question they came with, " if side == "learn" else "",
                                        count="six" if side == "learn" else "five",
                                        distinct=_DISTINCT if side == "learn" else "",
                                        distinct_key="\"distinct\": true|false, " if side == "learn" else "")
        self.VERDICTS = v1.VERDICTS if side == "learn" else tuple(v for v in v1.VERDICTS if v != "distinct")
        self._targets = targets

    @staticmethod
    def tool_sha256():
        return tool_sha256()

    @staticmethod
    def question_key(text):
        return v1.question_key(text)

    def write_payload(self, public):
        payload = {"pages": public["context"],
                   "target_types": [describe(t) for t in self._targets[digest(public)]]}
        if self.SOURCE_QUESTION_SHOWN:
            payload["source_question"] = public["question"]
        return payload

    def admit(self, candidate, source, seen_questions):
        """``source`` is the source task's public fields (the lifecycle passes them): its question is used on the host
        only, for the duplicate check, on either side. The item is labelled with the operation family of its own
        question wording; the types requested for its source are kept beside it."""
        reason, fields = admit(candidate, source, seen_questions)
        if fields is not None:
            fields["type"] = type_of(fields["question"])["op"]
            fields["requested_types"] = [t["op"] for t in self._targets[digest(source)]]
        return reason, fields

    def review_payload(self, public, item):
        payload = {"pages": public["context"], "question": item["question"], "figures": item["figures"],
                   "parts": item["parts"], "computed_answer": item["answer"]}
        if self.SOURCE_QUESTION_SHOWN:
            payload["source_question"] = public["question"]
        return payload

    def task_item(self, public, item):
        return {"id": item["id"], "question": item["question"], "context": public["context"], "answer": item["answer"],
                "category": item["type"]}


def learn_profile_items(tasks):
    """The per-item records of the training profile of ``tasks``, exactly as scripts/build_training_profile.py
    writes them (the tagger's record and the digest of the public fields)."""
    from scripts.build_training_profile import public_digest

    return {t["task_id"]: {**tagger.tag_item(t["public"]["question"], t.get("private", {}).get("answer"),
                                             t["public"].get("context")), "public_digest": public_digest(t["public"])}
            for t in tasks}


def kind_of(output):
    record = read_json(safe_path(output) / "generation.json", sealed=True)
    require(record["version"] == VERSION, "Not a v3 generation")
    return Kind(record["side"], record["targets"])


def prepare(study, split_path, output, repo, *, side, seed, lh_split, profile, per_task=PER_TASK):
    """v2's preparation (this seed's training draw restricted to one side of the L/H split, v1's manifest and
    lifecycle record) plus the target type of every source, sealed in the generation record."""
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    version, policy, budget = tool._protocol("v11")
    require(type(per_task) is int and 1 <= per_task <= 4, "One to four questions per training task")
    root, protocol = tool._study(study)
    out = safe_path(output)
    tool._outside(out, root, protocol, [split_path, lh_split, profile])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    tool.check_split(split, protocol, BENCHMARK)
    cut = read_json(lh_split, sealed=True)
    dev_path = tool.dev_panel_path(protocol, BENCHMARK)
    dev_panel = read_json(dev_path)
    train, _ = tool.train_tasks(dev_panel, split, BENCHMARK, seed)
    learn_tasks = [t for t in train if t["task_id"] in set(cut["learn_tasks"])]
    drawn = {t["task_id"] for t in train}
    require(set(cut["learn_tasks"]) | set(cut["held_out_tasks"]) == drawn
            and not set(cut["learn_tasks"]) & set(cut["held_out_tasks"]),
            "The L/H split does not partition this seed's training draw")
    kept = set(cut["learn_tasks"] if side == "learn" else cut["held_out_tasks"])
    train = [t for t in train if t["task_id"] in kept]
    require(train and all(type(t["public"]["context"]) is str for t in train), "A training task's pages are one text")
    profile_value = json.loads(Path(profile).read_text(encoding="utf-8"))
    require(profile_value.get("tagger_version") == tagger.VERSION
            and profile_value.get("items") == learn_profile_items(learn_tasks)
            and profile_value.get("profile") == fp.profile(profile_value["items"].values()),
            "The profile must be the learn side's training profile (recomputed from the training tasks)")
    if side == "learn":
        targets = {digest(t["public"]): [type_of(t["public"]["question"])] for t in train}
    else:
        targets = {digest(t["public"]): held_out_types(profile_value["items"], t["public"]["context"], seed)
                   for t in train}
    kind = Kind(side, targets)
    families = sorted({t["family_id"] for t in train})
    panel = {**deepcopy(dev_panel), "tasks": deepcopy(train)}
    value = ae.manifest(panel, step_families=families, challenge_families=[], model=deepcopy(protocol["model"]),
                        budget=budget, runtime=protocol["roles"][BENCHMARK]["runtime"], parent_skill="", seed=seed,
                        arms=base.ARMS, limits=ae.effective_limits(base.ARMS, 0))
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "split_hash": split["record_hash"], "benchmark": BENCHMARK, "repo": str(safe_path(repo)),
                   "seed": seed, "per_task": per_task, "source_tasks": len(train),
                   "source_task_hashes": sorted(digest(t) for t in train), "source_families": families,
                   "lh_split_hash": cut["record_hash"], "side": side, "source_question_shown": side == "learn",
                   "targets": targets, "profile": str(Path(profile).resolve()),
                   "profile_sha256": hashlib.sha256(Path(profile).read_bytes()).hexdigest(),
                   "tagger_version": tagger.VERSION,
                   "writer_system": kind.WRITER.format(count=per_task), "reviewer_system": kind.REVIEWER,
                   "filters": FILTERS,
                   "development_questions_hash": digest(sorted(v1.question_key(t["public"]["question"])
                                                               for t in dev_panel["tasks"])),
                   "information": "public fields of this side's training tasks only (%s); target types from the "
                                  "question wording of %s; no reference answer, no validation / test item, no solver "
                                  "outcome" % ("question and parsed pages" if side == "learn" else "parsed pages only",
                                               "the source" if side == "learn" else "learn-side training questions"),
                   "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                   "learning_model_service": protocol["learning_model_service"],
                   "native_lock": protocol["config"]["native_lock"], "dev_panel": str(safe_path(dev_path)),
                   "manifest_hash": value["record_hash"], "panel_sha256": base._sha(out / "panel.json"),
                   "tool_sha256": tool_sha256()})
    write_json(out / "generation.json", record)
    return record


def run(output, *, fixture_api=None, fixture_gate=None):
    return base.run(output, fixture_api=fixture_api, fixture_gate=fixture_gate, kind=kind_of(output))


def check(output):
    return base.check(output, kind_of(output))


def family_map(output):
    return base.family_map(output, kind_of(output))


def derivations(output):
    """Zero calls: {generated item id -> its derivation} (figures, parts, answer, type, source task) of a completed
    generation. Host-only: these are the items' reference answers."""
    out = safe_path(output)
    path, _, _ = check(output)
    records = read_json(out / "records.json", sealed=True)
    items = {i["id"]: i for i in json.loads(path.read_text(encoding="utf-8"))}
    found = {}
    for entry in records["sources"]:
        for candidate in entry["candidates"]:
            if candidate.get("accepted") and candidate["id"] in items:
                found[candidate["id"]] = {"source_task_hash": entry["source_task_hash"],
                                          **{k: deepcopy(candidate[k]) for k in ("question", "figures", "parts",
                                                                                 "answer", "type")}}
    require(set(found) == set(items), "Every accepted item has exactly one derivation")
    return found


def fidelity_value(output, profile, ids=None):
    """Zero calls: the feature profile of the accepted items (of those among ``ids`` when given: the items a pool
    actually keeps) against the training profile this generation was prepared with (checked by its hash), with the
    registered limits."""
    path, record, _ = check(output)
    require(hashlib.sha256(Path(profile).read_bytes()).hexdigest() == record["profile_sha256"],
            "Not the training profile this generation was prepared with")
    items = [i for i in json.loads(path.read_text(encoding="utf-8")) if ids is None or i["id"] in ids]
    require(items, "No accepted item")
    records = {i["id"]: tagger.tag_item(i["question"], i["answer"], i["context"]) for i in items}
    stored = json.loads(Path(profile).read_text(encoding="utf-8"))
    target = fp.profile(stored["items"].values())  # recomputed from the per-item records, never the stored summary
    require(target == stored["profile"], "The profile's summary differs from its items")
    generated = fp.profile(records.values())
    distance = fp.compare(target, generated)
    return {"version": VERSION, "generation_hash": record["record_hash"], "items": len(items),
            "profile": str(Path(profile).resolve()), "profile_sha256": record["profile_sha256"],
            "generated_profile": generated, "distance": distance, "limits": dict(FIDELITY_LIMITS),
            "passed": all(distance[k] <= limit for k, limit in FIDELITY_LIMITS.items())}


def fidelity(output, profile, report):
    """``fidelity_value`` written once as a sealed report."""
    out = Path(report)
    require(not out.exists(), "Use a new report file")
    value = seal(fidelity_value(output, profile))
    write_json(out, value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("--side", "--study", "--split", "--repo", "--output", "--lh-split", "--profile"):
        p.add_argument(name, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--per-task", type=int, default=PER_TASK)
    for name in ("run", "check"):
        sub.add_parser(name).add_argument("--output", required=True)
    f = sub.add_parser("fidelity")
    for name in ("--output", "--profile", "--report"):
        f.add_argument(name, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        record = prepare(args.study, args.split, args.output, args.repo, side=args.side, seed=args.seed,
                         lh_split=args.lh_split, profile=args.profile, per_task=args.per_task)
        print(json.dumps({k: record[k] for k in ("version", "side", "seed", "source_tasks", "record_hash")}))
        return 0
    if args.command == "run":
        result = run(args.output)
        print(json.dumps({k: result.get(k) for k in ("version", "status", "reason", "items")}))
        return 0 if result["status"] == "completed" else 1
    if args.command == "check":
        _, _, result = check(args.output)
        print(json.dumps({k: result.get(k) for k in ("version", "status", "items")}))
        return 0
    value = fidelity(args.output, args.profile, args.report)
    print(json.dumps({"passed": value["passed"], "items": value["items"], **value["distance"]}, indent=1))
    return 0 if value["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
