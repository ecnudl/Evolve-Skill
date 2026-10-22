"""LiveMath transformation families (protocol ``fivebench-execskill-v1``; registration §7.2 "LiveMath 族", Codex F8,
§21 owner rule (b); implementation plan §1 generators row; T-GEN-2, T-GEN-6).

A template's mathematical content comes from research: one qualified ``family_material`` finding, a definition or
theorem quoted verbatim from English Wikipedia (at most 1,500 characters), which must state the template's concept
(``material_mismatch`` otherwise) and is shown to the solver as the question's background. The examiner's generator
only gives the template's parameters, within the registered ranges; it never gives an answer.

The truth is computed by the fixed checker (``CHECKER_SOURCE``, registrar code) in the generator sandbox, the only
place sympy exists: the template turns the parameters into a symbolic variant spec (expression strings in the
whitelisted grammar of the worker's ``safe_sympify``) and the checker SOLVES the instance from that structure --
differentiates, integrates, counts or sums with sympy -- and returns the exact value and its 50-digit decimal
(``LIVEMATH_DIGITS``). A checker fault, a non-rational value or an exact value that disagrees with its 50 digits drops
the set (``reference_fn_failed``). The host then writes five options: the truth and four distinct distractors derived
from it by fixed offsets; exactly one option must equal the solved value (``options``); the correct letter rotates with
the kept item's number (A..E, so a set's key letters stay at 20 % +- 5 %, checked by the labels gate); no option is
the meta option and no meta-option term appears anywhere in the item (``meta_option``).
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, localcontext
from fractions import Fraction

from skillopt.continual_eval.core import require
from skillopt.continual_eval.datasets import LIVEMATH_LABELS, livemath_options

from .. import policy
from ..protocol import LIVEMATH_DIGITS, LIVEMATH_META_OPTION, SANDBOX_TIMEOUTS
from .families import Drop, Entry, Family, Param, bundle, check

CHECKED_BY = "execskill.generators.livemath"
CHECKER_ID = "livemath-checker"
AGREEMENT_DIGITS = 45  # the exact value and the checker's 50 digits agree to this many significant digits
ORDINAL = {1: "first", 2: "second"}
CHECKER_SOURCE = '''"""The fixed LiveMath checker (registrar code; fivebench-execskill-v1 registration section 7.2): it solves one
template instance from its structure with sympy, at 50 digits, and never sees an answer."""
import sympy

DIGITS = 50


def solve(spec):
    x = sympy.Symbol("x")
    op = spec["op"]
    if op == "derivative":
        value = sympy.diff(safe_sympify(spec["expression"]), x, int(spec["order"])).subs(x, safe_sympify(spec["at"]))
    elif op == "integral":
        bounds = (x, safe_sympify(spec["lower"]), safe_sympify(spec["upper"]))
        value = sympy.integrate(safe_sympify(spec["expression"]), bounds)
    elif op == "binomial":
        value = sympy.binomial(safe_sympify(spec["n"]), safe_sympify(spec["k"]))
    elif op == "geometric_series":
        i = sympy.Symbol("i", integer=True, nonnegative=True)
        term = safe_sympify(spec["first"]) * safe_sympify(spec["ratio"]) ** i
        value = sympy.summation(term, (i, 0, safe_sympify(spec["terms"]) - 1))
    else:
        raise ValueError("unknown template")
    value = sympy.simplify(value)
    exact = str(value) if value.is_Rational else None
    return {"exact": exact, "digits": str(sympy.N(value, DIGITS))}
'''
CHECKER = bundle([Entry(CHECKER_ID, CHECKER_SOURCE, ("solve",))])

COEFFICIENTS = Param("ints", -9, 9, count=(2, 5))
FAMILIES = {
    "livemath.derivative": Family(
        "livemath.derivative", "livemath", "definition", reference="derivative", concept="derivative",
        params={"coefficients": COEFFICIENTS, "at": Param("int", -5, 5), "order": Param("int", 1, 2)}),
    "livemath.integral": Family(
        "livemath.integral", "livemath", "definition", reference="integral", concept="integral",
        params={"coefficients": Param("ints", -9, 9, count=(2, 4)), "lower": Param("int", -5, 5),
                "upper": Param("int", -5, 5)}),
    "livemath.binomial": Family(
        "livemath.binomial", "livemath", "definition", reference="binomial", concept="binomial coefficient",
        params={"n": Param("int", 2, 30), "k": Param("int", 0, 30)}),
    "livemath.geometric_series": Family(
        "livemath.geometric_series", "livemath", "definition", reference="geometric_series",
        concept="geometric series",
        params={"first": Param("int", 1, 20), "ratio_numerator": Param("int", -5, 5),
                "ratio_denominator": Param("int", 1, 6), "terms": Param("int", 2, 12)}),
}


class SandboxChecker:
    """The fixed checker in a generator sandbox: ``worker`` is an unstarted ``sandbox.client.Worker`` (one per
    generation run); ``solve(spec)`` returns the worker's Result."""

    def __init__(self, worker):
        self.worker = worker.start(CHECKER, kind="generator")

    def solve(self, spec):
        return self.worker.call(CHECKER_ID, "solve", [spec], timeout_s=SANDBOX_TIMEOUTS["generator"])


class WorkerChecker:
    """The fixed checker as ``step.Services.checker`` (ticket C6-1; the smoke's S3, notes/C7d.md): ``workers`` is a
    worker factory -- ``workers(package, *, kind, hashseed=0, inputs_dir=None)``, a context manager yielding a started
    worker, i.e. ``Services.workers`` (``sandbox.client.with_worker`` with the Setting's sandbox options, the unit's tag
    bound). ``solve(spec)`` returns the worker's Result for one template instance: inside ``session()`` from the
    session's one generator worker, else from a worker opened for that solve alone (closed, its container's removal
    confirmed, afterwards). ``solved`` lists each solve's template op and outcome -- ok, the exact value and its 50
    digits, or the fault kind -- never the question."""

    def __init__(self, workers):
        require(callable(workers), "A worker factory")
        self.workers, self.solved, self._worker = workers, [], None

    @contextmanager
    def session(self):
        """One generator worker for every ``solve`` in the block."""
        require(self._worker is None, "One checker session at a time")
        with self.workers(CHECKER, kind="generator") as worker:
            self._worker = worker
            try:
                yield self
            finally:
                self._worker = None

    def solve(self, spec):
        if self._worker is not None:
            result = self._call(self._worker, spec)
        else:
            with self.workers(CHECKER, kind="generator") as worker:
                result = self._call(worker, spec)
        value = result.get("value") if isinstance(result, dict) and result.get("ok") is True else None
        self.solved.append({"op": spec.get("op") if isinstance(spec, dict) else None,
                            "ok": isinstance(result, dict) and result.get("ok") is True,
                            "exact": value.get("exact") if isinstance(value, dict) else None,
                            "digits": value.get("digits") if isinstance(value, dict) else None,
                            "fault": None if value is not None else (result or {}).get("fault")})
        return result

    @staticmethod
    def _call(worker, spec):
        return worker.call(CHECKER_ID, "solve", [spec], timeout_s=SANDBOX_TIMEOUTS["generator"])


def polynomial(coefficients):
    """The polynomial with ``coefficients`` (highest degree first) in the checker grammar, e.g. ``3*x^2 - 1``."""
    degree, terms = len(coefficients) - 1, []
    for power, c in zip(range(degree, -1, -1), coefficients):
        if c == 0:
            continue
        body = "x" if power == 1 else "x^%d" % power if power else ""
        size = str(abs(c)) if (abs(c) != 1 or not body) else ""
        term = size + ("*" if size and body else "") + body
        terms.append(("- " if c < 0 else "+ ") + term)
    require(terms, "A polynomial with a nonzero coefficient")
    text = " ".join(terms)
    return text[2:] if text.startswith("+ ") else "-" + text[2:]


def instance(family, params):
    """(question, spec) of one template instance; Drop("format") for parameters the template cannot use."""
    template = family.reference
    if template in ("derivative", "integral") and not any(params["coefficients"]):
        raise Drop("format", "a polynomial with a nonzero coefficient")
    if template == "derivative":
        f = polynomial(params["coefficients"])
        question = "Let f(x) = %s. What is the value of the %s derivative of f at x = %d?" % (
            f, ORDINAL[params["order"]], params["at"])
        return question, {"op": "derivative", "expression": f, "order": params["order"], "at": str(params["at"])}
    if template == "integral":
        if params["lower"] >= params["upper"]:
            raise Drop("format", "the lower bound is below the upper bound")
        f = polynomial(params["coefficients"])
        question = "What is the value of the definite integral of f(x) = %s from x = %d to x = %d?" % (
            f, params["lower"], params["upper"])
        return question, {"op": "integral", "expression": f, "lower": str(params["lower"]),
                          "upper": str(params["upper"])}
    if template == "binomial":
        if params["k"] > params["n"]:
            raise Drop("format", "k is at most n")
        question = "In how many ways can %d elements be chosen from a set of %d elements, that is, what is the " \
                   "binomial coefficient C(%d, %d)?" % (params["k"], params["n"], params["n"], params["k"])
        return question, {"op": "binomial", "n": str(params["n"]), "k": str(params["k"])}
    if params["ratio_numerator"] == 0:
        raise Drop("format", "a nonzero ratio")
    ratio = Fraction(params["ratio_numerator"], params["ratio_denominator"])
    question = "What is the sum of the first %d terms of the geometric series with first term %d and common ratio " \
               "%s?" % (params["terms"], params["first"], ratio)
    return question, {"op": "geometric_series", "first": str(params["first"]),
                      "ratio": "%d/%d" % (ratio.numerator, ratio.denominator), "terms": str(params["terms"])}


def solved(result):
    """The exact rational value of a checker Result whose exact value agrees with its 50 digits; Drop otherwise."""
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise Drop("reference_fn_failed", "checker fault: %s" % (result or {}).get("fault"))
    value = result["value"]
    if not isinstance(value, dict) or type(value.get("exact")) is not str or type(value.get("digits")) is not str:
        raise Drop("reference_fn_failed", "no exact rational value")
    try:
        exact = Fraction(value["exact"])
        digits = Decimal(value["digits"])
    except (ValueError, ArithmeticError):
        raise Drop("reference_fn_failed", "unreadable checker value") from None
    with localcontext() as context:
        context.prec = LIVEMATH_DIGITS + 10
        scale = max(Decimal(1), abs(digits))
        if abs(Decimal(exact.numerator) / Decimal(exact.denominator) - digits) > scale * Decimal(10) ** -AGREEMENT_DIGITS:
            raise Drop("reference_fn_failed", "the exact value and its digits disagree")
    return exact


def option_text(value):
    return str(value.numerator) if value.denominator == 1 else "%d/%d" % (value.numerator, value.denominator)


def options(truth, number):
    """Five option texts with the truth at letter ``number % 5`` and four distinct distractors from fixed offsets."""
    distractors = []
    for candidate in (truth + 1, truth - 1, truth + 2, 2 * truth, truth - 2, -truth, truth + 3):
        if candidate != truth and candidate not in distractors:
            distractors.append(candidate)
    values = distractors[:4]
    values.insert(number % len(LIVEMATH_LABELS), truth)
    return [option_text(v) for v in values]


def apply(family, params, material, *, checker, number):
    """One LiveMath item from one parameter set: {"public": {question, choices}, "answer" (a letter), "truth"}; Drop
    on any failure (module docstring). ``number``: the kept item's running number (the key letter's rotation)."""
    if material.get("kind") != "definition":
        raise Drop("material_mismatch", "a LiveMath family consumes a researched definition")
    if family.concept.lower() not in material["quote"].lower():
        raise Drop("material_mismatch", "the definition does not state %r" % family.concept)
    question, spec = instance(family, check(family, params))
    truth = solved(checker.solve(spec))
    texts = options(truth, number)
    if sum(1 for t in texts if Fraction(t) == truth) != 1 or len(set(texts)) != len(texts):
        raise Drop("options", "exactly one option equals the solved value")
    background = 'Background (quoted from English Wikipedia, "%s"): %s' % (material["source"]["title"],
                                                                          material["quote"])
    full = background + "\n\n" + question
    choices = "\n\n".join("%s. %s" % (label, t) for label, t in zip(LIVEMATH_LABELS, texts))
    require(livemath_options(choices) == texts, "The rendered choices parse back")
    if LIVEMATH_META_OPTION in texts or policy.meta_option_hits(full + "\n" + choices):
        raise Drop("meta_option")
    letter = LIVEMATH_LABELS[texts.index(option_text(truth))]
    return {"public": {"question": full, "choices": choices}, "answer": letter,
            "truth": {"kind": "sympy_solve", "family": family.name, "checked_by": CHECKED_BY, "spec": spec,
                      "exact": option_text(truth), "digits": LIVEMATH_DIGITS}}
