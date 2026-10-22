"""The fixed exact evaluator of the solver's <calc> tags (registration §2.4; plan §1 compute.py, T-COMP-1..5).

A copy of the frozen exact-arithmetic kernel of ``skillopt/coevo5/forward.py:105-221`` (``_tree``, ``_literal``,
``_bounded``, ``_integer``, ``_binary``, ``_value``, ``evaluate``, ``literals``, ``rounded``) with the changes the
registration makes for route B (§2.4 item 2):

- names: an expression may use the names a ``bindings`` hook extracted; their values are numbers quoted verbatim from
  the item (``notes.check_bindings``). Any other name fails (``name``).
- signs: the registration's operators + − × ÷ are read as + - * / (registrar addendum 2026-10-22 15:5x R6 (a)); a
  doubled multiplication sign (×× or a × beside *) never becomes a power and fails (``syntax``).
- the exponent cap is 12 (frozen ``MAX_EXPONENT`` 10); integer exponents only, negative only for a nonzero base.
- 4,096 bits (frozen ``MAX_BITS``): every value's numerator and denominator is checked when the value is created, so
  every operand is bounded before an operation uses it; a power is refused before it is computed when its result
  cannot fit (the frozen pre-check of forward.py:152-153 with the exact lower bound of the result's size), and every
  result is checked again (forward.py:126-129). A failure is ``magnitude``.
- the registered functions are abs, round, min, max and sum (frozen: abs, min, max, floor, ceil, factorial, comb,
  perm, gcd, lcm). ``round(x)`` / ``round(x, n)`` round half away from zero, the frozen ``rounded`` convention, to
  0 <= n <= 12 places; min, max and sum also take one list or tuple of numbers.
- nesting: at most 20 levels of brackets (frozen: none); at most 300 characters and 100 syntax nodes (frozen caps,
  forward.py:35-36, kept).
- a failure is a result, never an exception: ``{"value": "not evaluated", "error": "computation_failed:<reason>"}``,
  the same text the placebo arms show (§2.4 item 3, §6.1).
- a per-cell watchdog bounds the wall time of one cell's evaluations (plan §1); the caps above make it a safety net.

The kernel itself (``exact``) raises ``ComputeError``; the generators (plan §1 generators/) use it and ``rounded`` /
``literals`` as the frozen ones are used in forward.py.
"""
from __future__ import annotations

import ast
import math
import re
import time
from fractions import Fraction

from skillopt.continual_eval.core import require

from .protocol import MAX_BITS, MAX_CALC_CHARS, MAX_CALC_TAGS, MAX_DEPTH, MAX_EXPONENT, NOT_EVALUATED

# implementation constants (registered values come from ``protocol``)
MAX_FORMULA_NODES = 100  # the frozen kernel's node cap (forward.py:36), kept
MAX_ROUND_PLACES = 12  # round(x, n): 0 <= n <= 12, the exponent cap
MAX_DECIMALS = 4  # ``rounded``: the frozen 0-4 decimal places of a generated answer (forward.py:41)
MAX_EXACT_DECIMALS = 30  # a terminating value with more fractional digits is shown as a fraction
APPROXIMATE_PLACES = 12
CELL_WATCHDOG_SECONDS = 5.0  # one cell's evaluations (the hook wall time of plan §4)
FAILED = "computation_failed:"

TAG = re.compile(r"<calc>(.*?)</calc>", re.S)
LITERAL = re.compile(r"\d+(?:\.\d+)?")  # frozen forward.py:46: digits, one optional fraction part
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
NUMBER = re.compile(r"([+\-−]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")
FUNCTIONS = ("abs", "round", "min", "max", "sum")
OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
SIGNS = str.maketrans({"\u2212": "-", "\u00d7": "*", "\u00f7": "/"})  # registration §2.4: + − × ÷
POWER_OF_SIGNS = re.compile("[*\u00d7]\u00d7|\u00d7\\*")
REASONS = ("text", "syntax", "size", "depth", "literal", "name", "element", "arguments", "integer_argument",
           "division_by_zero", "exponent", "magnitude", "watchdog")


class ComputeError(ValueError):
    """An expression the fixed evaluator does not evaluate; ``reason`` is one of ``REASONS``."""

    def __init__(self, reason):
        require(reason in REASONS, "Unknown computation failure")
        super().__init__(reason)
        self.reason = reason


def parse_tags(reply):
    """The expressions of the reply's <calc> tags, in order: the first eight well-formed tags (non-empty after
    stripping, at most 300 characters). A reply with none triggers no second call (§2.4 item 2)."""
    if type(reply) is not str:
        return []
    found = [m.group(1).strip() for m in TAG.finditer(reply)]
    return [e for e in found if e and len(e) <= MAX_CALC_CHARS][:MAX_CALC_TAGS]


def number(text):
    """A number quoted from an item (a binding's value): optional sign (also U+2212), digits with optional ","
    thousands groups, optional decimal part. Anything else: ``ComputeError("name")`` (the binding is unusable)."""
    match = NUMBER.fullmatch(text.strip()) if type(text) is str else None
    if match is None:
        raise ComputeError("name")
    sign, whole, part = match.groups()
    value = Fraction(whole.replace(",", "") + ("." + part if part else ""))
    return -value if sign in ("-", "−") else value


def _depth(source):
    depth = deepest = 0
    for char in source:
        if char in "([":
            depth += 1
            deepest = max(deepest, depth)
        elif char in ")]":
            depth -= 1
    return deepest


def _tree(formula):
    if type(formula) is not str or not formula.strip() or len(formula) > MAX_CALC_CHARS:
        raise ComputeError("text")
    source = formula.strip()
    if POWER_OF_SIGNS.search(source):
        raise ComputeError("syntax")
    source = source.translate(SIGNS)  # one character for one: the literals' source segments are unchanged
    if _depth(source) > MAX_DEPTH:
        raise ComputeError("depth")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        raise ComputeError("syntax") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_FORMULA_NODES:
        raise ComputeError("size")
    return source, tree


def _literal(source, node):
    """A number literal exactly as written (never through a float)."""
    written = ast.get_source_segment(source, node)
    if type(node.value) not in (int, float) or written is None or LITERAL.fullmatch(written) is None:
        raise ComputeError("literal")
    return written


def _bounded(value):
    if value.numerator.bit_length() > MAX_BITS or value.denominator.bit_length() > MAX_BITS:
        raise ComputeError("magnitude")
    return value


def _integer(value):
    if value.denominator != 1:
        raise ComputeError("integer_argument")
    return value.numerator


def _power(base, exponent):
    if abs(exponent) > MAX_EXPONENT or (exponent < 0 and base == 0):
        raise ComputeError("exponent")
    if exponent and base:
        # base**e is reduced when base is: its larger part has at least |e| * (bits - 1) + 1 bits
        bits = max(base.numerator.bit_length(), base.denominator.bit_length())
        if abs(exponent) * (bits - 1) + 1 > MAX_BITS:
            raise ComputeError("magnitude")
    return base ** exponent


def _binary(op, left, right):
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        if right == 0:
            raise ComputeError("division_by_zero")
        return left / right
    return _power(left, _integer(right))


def _round_half_away(value, places):
    scaled = abs(value) * 10 ** places
    whole = math.floor(scaled + Fraction(1, 2))
    return Fraction(whole if value >= 0 else -whole, 10 ** places)


def _call(name, args):
    if name == "abs" and len(args) == 1:
        return abs(args[0])
    if name == "round" and len(args) in (1, 2):
        places = _integer(args[1]) if len(args) == 2 else 0
        if not 0 <= places <= MAX_ROUND_PLACES:
            raise ComputeError("arguments")
        return _round_half_away(args[0], places)
    if name in ("min", "max") and args:
        return min(args) if name == "min" else max(args)
    if name == "sum" and args:
        return sum(args, Fraction(0))
    raise ComputeError("arguments")


class _Evaluation:
    """One expression's evaluation: its source text, the bound names and the cell's watchdog deadline."""

    def __init__(self, source, names, deadline):
        self.source, self.names, self.deadline = source, names, deadline

    def arguments(self, node):
        if node.keywords:
            raise ComputeError("arguments")
        if (node.func.id in ("min", "max", "sum") and len(node.args) == 1
                and isinstance(node.args[0], (ast.List, ast.Tuple))):
            return [self.value(e) for e in node.args[0].elts]
        if node.func.id in ("min", "max", "sum") and len(node.args) < 2:
            raise ComputeError("arguments")
        return [self.value(a) for a in node.args]

    def value(self, node):
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise ComputeError("watchdog")
        if isinstance(node, ast.Expression):
            return self.value(node.body)
        if isinstance(node, ast.Constant):
            return _bounded(Fraction(_literal(self.source, node)))
        if isinstance(node, ast.Name):
            if node.id not in self.names:
                raise ComputeError("name")
            return self.names[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = self.value(node.operand)
            return operand if isinstance(node.op, ast.UAdd) else -operand
        if isinstance(node, ast.BinOp) and isinstance(node.op, OPERATORS):
            return _bounded(_binary(node.op, self.value(node.left), self.value(node.right)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            return _bounded(_call(node.func.id, self.arguments(node)))
        raise ComputeError("element")


def _names(bindings):
    """{name: bounded value} of ``bindings``: a mapping {name: number text or Fraction}, or the binding records that
    ``notes.check_bindings`` keeps ([{"name", "value", "quote"}], each name once), which the shell passes as they are.
    Records of another shape are a wiring error (ValueError), never a computation result."""
    if isinstance(bindings, (list, tuple)):
        require(all(type(b) is dict and type(b.get("name")) is str and "value" in b for b in bindings)
                and len({b["name"] for b in bindings}) == len(bindings),
                "Binding records hold a name and a value, each name once")
        bindings = {b["name"]: b["value"] for b in bindings}
    names = {}
    for name, value in dict(bindings or {}).items():
        if type(name) is not str or NAME.fullmatch(name) is None or name in FUNCTIONS:
            raise ComputeError("name")
        names[name] = _bounded(value if isinstance(value, Fraction) else number(value))
    return names


def exact(formula, bindings=None, *, deadline=None):
    """The exact value (``Fraction``) of an expression: number literals as written, the bound names, unary + and -,
    + - * / (also written − × ÷), ** with an integer exponent of at most 12 in size, brackets nested at most 20 deep
    and the functions abs, round, min, max and sum. ``bindings``: {name: number text or Fraction}, or the checked
    binding records of ``notes.check_bindings`` (``_names``). ``deadline``: a ``time.monotonic()`` value after which
    evaluation stops. Anything else: ``ComputeError``."""
    source, tree = _tree(formula)
    return _Evaluation(source, _names(bindings), deadline).value(tree)


def literals(formula):
    """The expression's number literals as written, in order of appearance (forward.py:206-210)."""
    source, tree = _tree(formula)
    found = sorted((n for n in ast.walk(tree) if isinstance(n, ast.Constant)), key=lambda n: (n.lineno, n.col_offset))
    return [_literal(source, node) for node in found]


def rounded(value, decimals):
    """``value`` rounded half away from zero to exactly ``decimals`` (0-4) digits after the point, no separators
    (forward.py:213-220)."""
    require(type(decimals) is int and 0 <= decimals <= MAX_DECIMALS, "Rounding to 0-4 decimal places")
    value = Fraction(value)
    whole = math.floor(abs(value) * 10 ** decimals + Fraction(1, 2))
    digits = str(whole).rjust(decimals + 1, "0")
    body = digits[:-decimals] + "." + digits[-decimals:] if decimals else digits
    return ("-" if value < 0 and whole else "") + body


def _terminating_places(denominator):
    """The number of fractional digits of a terminating decimal with this denominator, or None."""
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    return max(twos, fives) if denominator == 1 else None


def render(value):
    """How an exact value is shown to the solver: an integer as digits; a terminating decimal with at most 30
    fractional digits exactly; anything else as ``p/q (approximately d)``, d rounded half away from zero to 12
    places."""
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    places = _terminating_places(value.denominator)
    if places is not None and places <= MAX_EXACT_DECIMALS:
        scaled = abs(value.numerator) * 10 ** places // value.denominator
        digits = str(scaled).rjust(places + 1, "0")
        return ("-" if value < 0 else "") + digits[:-places] + "." + digits[-places:]
    approximate = render(_round_half_away(value, APPROXIMATE_PLACES))
    return "%d/%d (approximately %s)" % (value.numerator, value.denominator, approximate)


def evaluate(formula, bindings=None, *, deadline=None):
    """``{"value": str}`` or ``{"value": "not evaluated", "error": "computation_failed:<reason>"}``."""
    try:
        return {"value": render(exact(formula, bindings, deadline=deadline))}
    except ComputeError as failure:
        return {"value": NOT_EVALUATED, "error": FAILED + failure.reason}


def evaluate_tags(tags, bindings=None, *, watchdog_seconds=CELL_WATCHDOG_SECONDS):
    """One cell's evaluations, in tag order: ``[{"expr", "value"[, "error"]}]``. ``bindings`` are the checked ones:
    the records ``notes.check_bindings`` kept, passed as they are (or a mapping {name: value}); an unusable binding
    fails every expression (``name``). The watchdog spans the whole cell: once it has expired, every remaining
    expression is ``computation_failed:watchdog``."""
    require(type(tags) is list and len(tags) <= MAX_CALC_TAGS and all(type(t) is str for t in tags),
            "At most eight <calc> expressions per cell")
    deadline = time.monotonic() + watchdog_seconds
    return [{"expr": tag, **evaluate(tag, bindings, deadline=deadline)} for tag in tags]
