"""The evaluator of derivation expressions (typed-v3 item bank): exact where the arithmetic is rational, certified
where it is not. An expression is PARSED AND WALKED, never compiled or executed.

Why not ``skillopt.execskill.compute`` alone: the first pass over the 74 OfficeQA practice items (2026-11-13) anchored
34; most of the others ask for a statistic (standard deviation, geometric mean, coefficient of variation,
correlation, a compound growth rate) or sum thirty lines of a table, which the solver-side evaluator (+ - * / and
whole powers, 300 characters) cannot write down. The design follows the certified evaluator of
``scripts/generate_officeqa_feature_tasks.py`` (2026-10-16) with wider bounds and named steps.

Grammar: number literals (digits, an optional decimal part), names, unary + and -, + - * / **, brackets, and

    abs(x) sqrt(x) ln(x) log10(x) exp(x) pow(x, y) round(x[, n])
    min max sum mean median stdev_pop stdev_samp var_pop var_samp geomean      over two or more values
    corr(x1, ..., xn, y1, ..., yn)                                             the first half against the second

A function over several values takes them as arguments or as one list ``[a, b, c]``.

Values are ``fractions.Fraction``. + - * /, whole powers, abs, min, max, sum, mean, median, the variances and
``round`` are exact. sqrt, ln, log10, exp, a fractional power, the standard deviations, geomean and corr are not:
the evaluator then carries an ENCLOSURE, two rationals lo <= true value <= hi, through every later operation
(interval arithmetic; each irrational function is evaluated at PRECISION decimal digits on both ends, its argument
rounded outwards and its result widened by SLACK). ``evaluate`` returns ``(value, exact)``: an exact value is a
plain Fraction; an inexact one is an ``Approx`` (a Fraction, the midpoint, that keeps ``lo`` and ``hi``) and stays
one when it is bound to a name and used by a later expression, so the bound follows it. ``text(value, decimals,
exact)`` writes an answer and refuses an inexact value unless BOTH ends of its enclosure round to the same digits
and stay more than TIE_MARGIN away from a rounding boundary: a kept answer is proved, whatever cancellation or
scaling the expression holds (review 2026-11-13: a fixed number of digits alone certified ``12 + ln(1 + 10**-64) /
10**-64`` as 12). Rounding is half away from zero, the benchmark writers' convention being unknown: an EXACT tie is
refused for a made answer and tried both ways when a reference is to be reproduced (``candidates``).

Every refusal is a ``CalcError(reason)``.
"""
from __future__ import annotations

import ast
import math
import re
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from fractions import Fraction

REASONS = ('text', 'syntax', 'size', 'depth', 'literal', 'name', 'grammar', 'arguments', 'division_by_zero', 'domain',
           'exponent', 'magnitude', 'uncertain_rounding', 'decimals', 'not_terminating', 'rounding_tie')
PRECISION = 60
SLACK = Fraction(1, 10 ** (PRECISION - 4))   # relative widening of an irrational function's two ends (the decimal
                                             # module rounds these functions correctly; this is 10^4 units of it)
MAX_CHARS, MAX_NODES, MAX_DEPTH = 6000, 4000, 80
MAX_MAGNITUDE = Fraction(10) ** 40
MAX_BITS = 20000
MAX_EXPONENT = 64
MAX_DECIMALS = 6
MAX_EXACT_PLACES = 6
TIE_MARGIN = Fraction(1, 10 ** 9)
SCALAR = {'abs': (1, 1), 'sqrt': (1, 1), 'ln': (1, 1), 'log10': (1, 1), 'exp': (1, 1), 'pow': (2, 2), 'round': (1, 2)}
SERIES = ('min', 'max', 'sum', 'mean', 'median', 'stdev_pop', 'stdev_samp', 'var_pop', 'var_samp', 'geomean', 'corr')
FUNCTIONS = tuple(SCALAR) + SERIES
INEXACT = ('sqrt', 'ln', 'log10', 'exp', 'stdev_pop', 'stdev_samp', 'geomean', 'corr')
LITERAL = re.compile(r'\d+(?:\.\d+)?')
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,31}')
NUMBER = re.compile(r'([+\-−]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?')
SIGNS = str.maketrans({'−': '-', '×': '*', '÷': '/'})
OPERATORS = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.Div: 'div', ast.Pow: 'pow'}


class CalcError(ValueError):
    def __init__(self, reason, detail=''):
        assert reason in REASONS, reason
        super().__init__(reason + (': ' + str(detail) if detail else ''))
        self.reason, self.detail = reason, str(detail)


def number(written):
    """The exact value of a number as printed (thousands commas, an optional sign, a decimal part)."""
    match = NUMBER.fullmatch(written.strip()) if isinstance(written, str) else None
    if match is None:
        raise CalcError('literal', written)
    sign, whole, part = match.groups()
    value = Fraction(whole.replace(',', '') + ('.' + part if part else ''))
    return -value if sign in ('-', '−') else value


def parse(expression):
    """(source, tree) of an expression inside the size bounds; ``CalcError`` otherwise."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalcError('text')
    source = expression.translate(SIGNS).strip()
    if not source.isascii():
        raise CalcError('text')
    if len(source) > MAX_CHARS or '\n' in source or '\r' in source:
        raise CalcError('size')
    try:
        tree = ast.parse(source, mode='eval')
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise CalcError('syntax') from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise CalcError('size')
    return source, tree


def names(expression):
    """The names an expression uses that are not functions."""
    _, tree = parse(expression)
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} - set(FUNCTIONS)


def literals(expression):
    """The number literals of an expression as written, in order."""
    source, tree = parse(expression)
    found = sorted((node for node in ast.walk(tree) if isinstance(node, ast.Constant)),
                   key=lambda node: node.col_offset)
    return [source[node.col_offset:node.end_col_offset] for node in found]


def operations(expression):
    """Sorted labels of the arithmetic and the functions an expression uses (a fidelity feature)."""
    _, tree = parse(expression)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            found.add(OPERATORS[type(node.op)])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            found.add(node.func.id)
    return sorted(found)


def _bounded(value):
    if abs(value) > MAX_MAGNITUDE or value.numerator.bit_length() > MAX_BITS or value.denominator.bit_length() > MAX_BITS:
        raise CalcError('magnitude')
    return value


def round_half_away(value, places):
    scaled = abs(value) * 10 ** places
    return Fraction(math.floor(scaled + Fraction(1, 2)), 10 ** places) * (-1 if value < 0 else 1)


class Approx(Fraction):
    """An inexact value: the midpoint of its enclosure as a Fraction, with the enclosure's ends ``lo`` and ``hi``.
    Arithmetic on it outside the evaluator gives plain Fractions (the midpoint's): the ends matter where a rounding
    is decided (``near_tie``, ``text``) and inside the evaluator, which reads them from bound names."""
    def __new__(cls, lo, hi):
        made = super().__new__(cls, (Fraction(lo) + Fraction(hi)) / 2)
        made.lo, made.hi = Fraction(lo), Fraction(hi)
        return made

    def __reduce__(self):                      # Fraction's own would rebuild it from numerator and denominator
        return (Approx, (self.lo, self.hi))

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


def _ends(value):
    return (value.lo, value.hi) if isinstance(value, Approx) else (Fraction(value), Fraction(value))


def _near(value, places, margin):
    scaled = abs(value) * 10 ** places
    return abs(scaled - math.floor(scaled) - Fraction(1, 2)) <= margin


def near_tie(value, places, margin=TIE_MARGIN):
    """Whether ``value`` lies within ``margin`` (in units of the last kept digit) of a rounding boundary. For an
    ``Approx``: whether its enclosure does -- an end within the margin, or the two ends rounding differently."""
    lo, hi = _ends(value)
    return (_near(lo, places, margin) or _near(hi, places, margin)
            or round_half_away(lo, places) != round_half_away(hi, places))


def _point(value):
    return (value, value)


COMPACT_BITS = 512   # an inexact end longer than this is rounded outwards to PRECISION digits (about 200 bits)


def _outward(value, rounding):
    with localcontext() as context:
        context.prec, context.rounding = PRECISION, rounding
        return Fraction(Decimal(value.numerator) / Decimal(value.denominator))


def _compact(pair):
    """An enclosure whose ends carry more digits than they are worth, rounded OUTWARDS to PRECISION significant
    digits (lo down, hi up): still an enclosure, wider by one part in 10^59 at most, and short again -- so that
    ordinary compounding such as ``(g ** (1 / 12)) ** 60`` stays inside the size bounds (second review 2026-11-13).
    A point (an exact value) is never touched."""
    if pair[0] == pair[1] or max(v.numerator.bit_length() + v.denominator.bit_length() for v in pair) <= COMPACT_BITS:
        return pair
    return (_outward(pair[0], ROUND_FLOOR), _outward(pair[1], ROUND_CEILING))


def _b(pair):
    pair = _compact(pair)
    _bounded(pair[0])
    _bounded(pair[1])
    return pair


def _mul(a, b):
    products = (a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1])
    return _b((min(products), max(products)))


def _inverse(b):
    if b[0] <= 0 <= b[1]:
        raise CalcError('division_by_zero' if b[0] == b[1] else 'uncertain_rounding', 'a divisor that may be zero')
    return (1 / b[1], 1 / b[0])


def _whole_power(x, n):
    if n == 0:
        return _point(Fraction(1))
    if n < 0:
        return _whole_power(_inverse(x), -n)   # invert first: the bounds apply to the result, not to x ** |n|
    x = _compact(x)
    if abs(n) * max(v.numerator.bit_length() + v.denominator.bit_length() for v in x) > 2 * MAX_BITS:
        raise CalcError('magnitude')
    ends = (x[0] ** n, x[1] ** n)
    if n % 2 == 0 and x[0] < 0 < x[1]:
        return _b((Fraction(0), max(ends)))
    return _b((min(ends), max(ends)))


def _monotone(function, x):
    """The enclosure of an INCREASING irrational function over the enclosure ``x``: the lower end from the lower
    argument rounded down, the upper end from the upper argument rounded up, each widened by SLACK."""
    out = []
    for value, rounding, sign in ((x[0], ROUND_FLOOR, -1), (x[1], ROUND_CEILING, 1)):
        with localcontext() as context:
            context.prec = PRECISION
            context.traps[InvalidOperation] = context.traps[DivisionByZero] = context.traps[Overflow] = True
            try:
                context.rounding = rounding
                argument = Decimal(value.numerator) / Decimal(value.denominator)
                made = Fraction(function(argument))
            except (InvalidOperation, DivisionByZero, Overflow, ArithmeticError):
                raise CalcError('domain') from None
        out.append(made + sign * (abs(made) * SLACK + Fraction(1, 10 ** (2 * PRECISION))))
    return _b((out[0], out[1]))


class _Run:
    """Walks one expression; every node gives an enclosure (lo, hi), a point when the value is exact."""

    def __init__(self, source, bound):
        self.source, self.bound = source, bound

    def sqrt(self, x):
        if x[0] < 0:
            raise CalcError('domain' if x[1] < 0 or x[0] == x[1] else 'uncertain_rounding', 'sqrt of a negative value')
        return _monotone(lambda d: d.sqrt(), x) if x[0] > 0 else (Fraction(0), _monotone(lambda d: d.sqrt(), (x[1], x[1]))[1])

    def ln(self, x):
        if x[0] <= 0:
            raise CalcError('domain' if x[1] <= 0 or x[0] == x[1] else 'uncertain_rounding', 'logarithm of a non-positive value')
        return _monotone(lambda d: d.ln(), x)

    def exp(self, x):
        if max(abs(x[0]), abs(x[1])) > 80:
            raise CalcError('magnitude')
        return _monotone(lambda d: d.exp(), x)

    def power(self, x, y):
        if max(abs(y[0]), abs(y[1])) > MAX_EXPONENT:
            raise CalcError('exponent')
        if y[0] == y[1] and y[0].denominator == 1:
            if x[0] <= 0 <= x[1] and y[0] < 0:
                raise CalcError('division_by_zero' if x[0] == x[1] else 'uncertain_rounding')
            return _whole_power(x, int(y[0]))
        if x[0] <= 0:
            raise CalcError('domain', 'a non-positive base to a fractional power')
        return self.exp(_mul(y, self.ln(x)))

    def series(self, name, values):
        n = len(values)
        if n < 2:
            raise CalcError('arguments', name)
        if name == 'min':
            return (min(v[0] for v in values), min(v[1] for v in values))
        if name == 'max':
            return (max(v[0] for v in values), max(v[1] for v in values))
        total = _b((sum((v[0] for v in values), Fraction(0)), sum((v[1] for v in values), Fraction(0))))
        if name == 'sum':
            return total
        mean = (total[0] / n, total[1] / n)
        if name == 'mean':
            return mean
        if name == 'median':
            los, his = sorted(v[0] for v in values), sorted(v[1] for v in values)
            pick = lambda ordered: ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
            return (pick(los), pick(his))
        spread = lambda series, centre: [_whole_power((v[0] - centre[1], v[1] - centre[0]), 2) for v in series]
        add = lambda pairs: _b((sum((q[0] for q in pairs), Fraction(0)), sum((q[1] for q in pairs), Fraction(0))))
        if name in ('var_pop', 'var_samp', 'stdev_pop', 'stdev_samp'):
            squares = add(spread(values, mean))
            count = n if name.endswith('pop') else n - 1
            variance = (max(squares[0], Fraction(0)) / count, squares[1] / count)
            return variance if name.startswith('var') else self.sqrt(variance)
        if name == 'geomean':
            if any(v[0] <= 0 for v in values):
                raise CalcError('domain', 'geomean of a non-positive value')
            logs = add([self.ln(v) for v in values])
            return self.exp((logs[0] / n, logs[1] / n))
        if n % 2:
            raise CalcError('arguments', 'corr needs two series of equal length')
        xs, ys = values[:n // 2], values[n // 2:]
        half = len(xs)
        centre = lambda series: (sum((v[0] for v in series), Fraction(0)) / half, sum((v[1] for v in series), Fraction(0)) / half)
        mx, my = centre(xs), centre(ys)
        sxy = add([_mul((x[0] - mx[1], x[1] - mx[0]), (y[0] - my[1], y[1] - my[0])) for x, y in zip(xs, ys)])
        sxx, syy = add(spread(xs, mx)), add(spread(ys, my))
        if sxx[1] == 0 or syy[1] == 0:
            raise CalcError('domain', 'corr of a constant series')
        if sxx[0] <= 0 or syy[0] <= 0:
            raise CalcError('uncertain_rounding', 'corr of a series that may be constant')
        return _mul(sxy, _inverse(self.sqrt(_mul(sxx, syy))))

    def value(self, node, depth=0):
        if depth > MAX_DEPTH:
            raise CalcError('depth')
        if isinstance(node, ast.Constant):
            spelling = self.source[node.col_offset:node.end_col_offset]
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)) or LITERAL.fullmatch(spelling) is None:
                raise CalcError('literal', spelling[:40])
            return _point(_bounded(Fraction(spelling)))
        if isinstance(node, ast.Name):
            if node.id not in self.bound:
                raise CalcError('name', node.id)
            return _ends(self.bound[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self.value(node.operand, depth + 1)
            return (-value[1], -value[0]) if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = self.value(node.left, depth + 1), self.value(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return _b((left[0] + right[0], left[1] + right[1]))
            if isinstance(node.op, ast.Sub):
                return _b((left[0] - right[1], left[1] - right[0]))
            if isinstance(node.op, ast.Mult):
                return _mul(left, right)
            if isinstance(node.op, ast.Div):
                return _mul(left, _inverse(right))
            return self.power(left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name, arguments = node.func.id, node.args
            if name in SCALAR:
                if not SCALAR[name][0] <= len(arguments) <= SCALAR[name][1]:
                    raise CalcError('arguments', name)
                values = [self.value(argument, depth + 1) for argument in arguments]
                x = values[0]
                if name == 'abs':
                    ends = (abs(x[0]), abs(x[1]))
                    return (Fraction(0), max(ends)) if x[0] < 0 < x[1] else (min(ends), max(ends))
                if name == 'sqrt':
                    return self.sqrt(x)
                if name == 'ln':
                    return self.ln(x)
                if name == 'log10':
                    if x[0] <= 0:
                        raise CalcError('domain' if x[1] <= 0 or x[0] == x[1] else 'uncertain_rounding',
                                        'logarithm of a non-positive value')
                    return _monotone(lambda d: d.log10(), x)
                if name == 'exp':
                    return self.exp(x)
                if name == 'pow':
                    return self.power(x, values[1])
                places = values[1] if len(values) == 2 else _point(Fraction(0))
                if places[0] != places[1] or places[0].denominator != 1 or not 0 <= places[0] <= 12:
                    raise CalcError('arguments', 'round places')
                where = int(places[0])
                if x[0] != x[1] and (_near(x[0], where, TIE_MARGIN) or _near(x[1], where, TIE_MARGIN)
                                     or round_half_away(x[0], where) != round_half_away(x[1], where)):
                    raise CalcError('uncertain_rounding')
                return _point(round_half_away(x[0], where))
            if name in SERIES:
                if len(arguments) == 1 and isinstance(arguments[0], (ast.List, ast.Tuple)):
                    arguments = arguments[0].elts
                return self.series(name, [self.value(argument, depth + 1) for argument in arguments])
        raise CalcError('grammar', type(node).__name__)


def evaluate(expression, bound):
    """(value, exact) of an expression over ``bound`` {name: Fraction or Approx}: a plain Fraction when the value is
    exact, an ``Approx`` (midpoint with its enclosure) when it is not."""
    source, tree = parse(expression)
    try:
        lo, hi = _Run(source, bound).value(tree.body)
    except RecursionError:
        raise CalcError('depth') from None
    return (lo, True) if lo == hi else (Approx(lo, hi), False)


def _digits(value, decimals):
    whole = int(abs(value) * 10 ** decimals)
    digits = str(whole).rjust(decimals + 1, '0')
    body = digits[:-decimals] + '.' + digits[-decimals:] if decimals else digits
    return ('-' if value < 0 and whole else '') + body


def text(value, decimals, exact):
    """The answer text of a value: ``decimals`` None is the exact value (it must be exact and end within
    MAX_EXACT_PLACES places); else exactly ``decimals`` digits after the point, rounded half away from zero. An
    inexact value within TIE_MARGIN of a rounding boundary is refused (``rounding_tie``)."""
    if decimals is None:
        if not exact:
            raise CalcError('not_terminating', 'an inexact value needs its decimals')
        for places in range(MAX_EXACT_PLACES + 1):
            if (value * 10 ** places).denominator == 1:
                return _digits(value, places)
        raise CalcError('not_terminating')
    if type(decimals) is not int or not 0 <= decimals <= MAX_DECIMALS:
        raise CalcError('decimals', decimals)
    if not exact and near_tie(value, decimals):
        raise CalcError('rounding_tie')
    return _digits(round_half_away(_ends(value)[0], decimals), decimals)


def candidates(value, decimals, exact):
    """The answer texts a REFERENCE may show for this value: the half-away rounding, and for an exact tie also the
    other neighbour (a reference written with round-half-even or truncation of the tie)."""
    first = text(value, decimals, exact)
    if decimals is None or not exact or not near_tie(value, decimals, Fraction(0)):
        return [first]
    step = Fraction(1, 10 ** decimals)
    rounded = round_half_away(value, decimals)
    other = rounded - step if value > 0 else rounded + step
    return [first, _digits(other, decimals)]
