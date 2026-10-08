"""Label-free executable checks of KOR-Bench operation, puzzle and cipher answers.

Input: one task's public rule text and question plus a model response. Gold
answers and official scores are never read. A rule is checked only when the
sha256 of its exact public text is registered, and a question only when it is
fully consumed by a supported template plus known answer-format instructions:
an edited rule, a rule change inside the question or any unrecognized text is
``unknown``. ``pass`` means the answer satisfies every public constraint;
``fail`` means it gives no answer span or provably violates one. Arithmetic is
exact (Gaussian rationals); irrational values are 80-digit outward-rounded
interval enclosures, which can prove an answer wrong but never right.
Unspecified operator precedence, unsupported answer representations and
inverse questions (substitution can refute, never prove, a solution set) are
``unknown``. A cipher answer is recomputed under every admissible reading of
its rule (where the prose, its own worked example or an unstated convention
leave a choice): ``pass`` needs all readings to give the response's answer,
``fail`` none of them. The answer span is selected as in the official scorer.
This is a measurement instrument for cross-domain applicability, never exposed
to solvers or learners.
"""
from __future__ import annotations

import hashlib
import math
import operator
import re
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from fractions import Fraction

VERSION = "kor-applicability-verifier-v5"
MAX_RESPONSE_CHARS = 20000
MAX_BITS = 4096


class Unknown(Exception):
    """The instrument cannot decide; never converted into pass or fail."""


def rule_hash(rule):
    return hashlib.sha256(rule.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ exact values
_PRECISION = 80


def _rounded(operation, rounding):
    with localcontext() as context:
        context.prec, context.rounding = _PRECISION, rounding
        return operation()


class _Interval:
    """A rigorous enclosure [lo, hi] of a real number, rounded outward."""

    __slots__ = ("lo", "hi")

    def __init__(self, lo, hi):
        self.lo, self.hi = lo, hi

    @classmethod
    def of(cls, value):
        quotient = lambda: Decimal(value.numerator) / Decimal(value.denominator)  # noqa: E731
        return cls(_rounded(quotient, ROUND_FLOOR), _rounded(quotient, ROUND_CEILING))

    def __add__(self, other):
        return _Interval(_rounded(lambda: self.lo + other.lo, ROUND_FLOOR),
                         _rounded(lambda: self.hi + other.hi, ROUND_CEILING))

    def __sub__(self, other):
        return _Interval(_rounded(lambda: self.lo - other.hi, ROUND_FLOOR),
                         _rounded(lambda: self.hi - other.lo, ROUND_CEILING))

    def __mul__(self, other):
        pairs = [(a, b) for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return _Interval(min(_rounded(lambda: a * b, ROUND_FLOOR) for a, b in pairs),
                         max(_rounded(lambda: a * b, ROUND_CEILING) for a, b in pairs))

    def reciprocal(self):
        if self.lo <= 0 <= self.hi:
            raise Unknown("division_by_an_interval_containing_zero")
        return _Interval(_rounded(lambda: 1 / self.hi, ROUND_FLOOR), _rounded(lambda: 1 / self.lo, ROUND_CEILING))

    def monotone(self, function):
        """Apply an increasing, correctly rounded function, widened by one unit in the last place."""
        with localcontext() as context:
            context.prec = _PRECISION
            return _Interval(function(self.lo).next_minus(), function(self.hi).next_plus())

    def has_zero(self):
        return self.lo <= 0 <= self.hi


_ZERO = _Interval(Decimal(0), Decimal(0))


class _Value:
    """An exact Gaussian rational, or rigorous interval enclosures of its two parts."""

    __slots__ = ("re", "im", "exact")

    def __init__(self, re_, im=0, exact=True):
        if exact:
            self.re, self.im = Fraction(re_), Fraction(im)
            if any(abs(x.numerator).bit_length() + x.denominator.bit_length() > MAX_BITS for x in (self.re, self.im)):
                raise Unknown("number_too_large")
        else:
            self.re, self.im = re_, im
        self.exact = exact

    def parts(self):
        if self.exact:
            return (_Interval.of(self.re), _ZERO if self.im == 0 else _Interval.of(self.im))
        return self.re, self.im

    def _lift(self, other, exact, inexact):
        if self.exact and other.exact:
            return exact(self, other)
        (a, b), (c, d) = self.parts(), other.parts()
        return _Value(*inexact(a, b, c, d), exact=False)

    def __add__(self, other):
        return self._lift(other, lambda x, y: _Value(x.re + y.re, x.im + y.im), lambda a, b, c, d: (a + c, b + d))

    def __sub__(self, other):
        return self._lift(other, lambda x, y: _Value(x.re - y.re, x.im - y.im), lambda a, b, c, d: (a - c, b - d))

    def __mul__(self, other):
        return self._lift(other, lambda x, y: _Value(x.re * y.re - x.im * y.im, x.re * y.im + x.im * y.re),
                          lambda a, b, c, d: (a * c - b * d, a * d + b * c))

    def __truediv__(self, other):
        if other.exact and other.re == 0 and other.im == 0:
            raise ZeroDivisionError("division by zero")

        def exact(x, y):
            norm = y.re * y.re + y.im * y.im
            return _Value((x.re * y.re + x.im * y.im) / norm, (x.im * y.re - x.re * y.im) / norm)

        def inexact(a, b, c, d):
            inverse = (c * c + d * d).reciprocal()
            return (a * c + b * d) * inverse, (b * c - a * d) * inverse
        return self._lift(other, exact, inexact)

    def __neg__(self):
        if self.exact:
            return _Value(-self.re, -self.im)
        return _Value(_ZERO - self.re, _ZERO - self.im, exact=False)

    def real(self):
        """The real part when the value is provably real (exact, or an exactly zero imaginary enclosure)."""
        if self.exact:
            if self.im != 0:
                raise Unknown("non_real_operand")
        elif not (self.im.lo == 0 and self.im.hi == 0):
            raise Unknown("non_real_operand")
        return self.re


_I = _Value(0, 1)


def _integer(value):
    real = value.real()
    if not value.exact or real.denominator != 1:
        raise Unknown("non_integer_operand")
    return int(real)


def _power(base, exponent):
    if not (exponent.exact and exponent.im == 0 and exponent.re.denominator == 1):
        raise Unknown("unsupported_power")
    n = int(exponent.re)
    if abs(n) > 64:
        raise Unknown("exponent_out_of_range")
    result = _Value(1)
    for _ in range(abs(n)):
        result = result * base
    return _Value(1) / result if n < 0 else result


def _sqrt(value):
    real = value.real()
    if value.exact:
        if real < 0:
            raise Unknown("square_root_of_negative")
        top, bottom = math.isqrt(real.numerator), math.isqrt(real.denominator)
        if top * top == real.numerator and bottom * bottom == real.denominator:
            return _Value(Fraction(top, bottom))
        real = _Interval.of(real)
    if real.lo < 0:
        raise Unknown("square_root_of_negative")
    return _Value(real.monotone(Decimal.sqrt), _ZERO, exact=False)


def _log(argument, base):
    a, b = argument.real(), base.real()
    if argument.exact and base.exact:
        if a <= 0 or b <= 0 or b == 1:
            raise Unknown("logarithm_domain")
        guess = Fraction(math.log(a) / math.log(b)).limit_denominator(64)
        p, q = guess.numerator, guess.denominator
        if abs(p) <= 256 and max(a.numerator, a.denominator).bit_length() * q <= MAX_BITS \
                and max(b.numerator, b.denominator).bit_length() * abs(p) <= MAX_BITS and a ** q == b ** p:
            return _Value(guess)  # proven: b^(p/q) == a
    a, b = (x if isinstance(x, _Interval) else _Interval.of(x) for x in (a, b))
    if a.lo <= 0 or b.lo <= 0:
        raise Unknown("logarithm_domain")
    return _Value(a.monotone(Decimal.ln) * b.monotone(Decimal.ln).reciprocal(), _ZERO, exact=False)


def _compare(value, expected):
    """True only for equal exact values; False when the difference provably excludes zero."""
    if value.exact and expected.exact:
        return value.re == expected.re and value.im == expected.im
    re_, im = (value - expected).parts()
    if not (re_.has_zero() and im.has_zero()):
        return False
    raise Unknown("irrational_equality_unprovable")


# --------------------------------------------------------- numeric expressions
_TOKEN = re.compile(r"\\[A-Za-z]+|[0-9]+(?:\.[0-9]+)?|[A-Za-z]|\S")
_MINUS, _TIMES, _DIVIDE = {"-", "−", "–"}, {"×", "*", "·", "\\cdot", "\\times"}, {"÷", "/", "\\div"}
_CLOSE = {"(": ")", "{": "}"}


def _clean(text):
    text = re.sub(r"\\(?:text|mathrm|operatorname)\{([^{}]*)\}", r"\1", text)
    for noise in ("\\left", "\\right", "\\displaystyle", "\\,", "\\;", "\\!", "$"):
        text = text.replace(noise, "")
    return text.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")


def _tokens(text):
    return [m.group(0) for m in _TOKEN.finditer(_clean(text))]


def _constant(value):
    return lambda env: value


def _apply(function, *operands):
    return lambda env: function(*(operand(env) for operand in operands))


class _Parser:
    """Compile an expression before evaluating it: syntax and precedence are settled
    first, values later. Each level returns (function, kind); kind "custom" marks an
    unparenthesized custom-operator result, which may only be combined after
    parenthesizing."""

    def __init__(self, text, *, custom=None, angle=None, variables=(), implicit=True, unit=True):
        self.tokens, self.index = _tokens(text), 0
        self.custom, self.angle, self.variables = custom or {}, angle, set(variables)
        self.implicit, self.unit = implicit, unit
        self.literals = []

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self, expected=None):
        token = self.peek()
        if token is None or (expected is not None and token != expected):
            raise Unknown("unparsed_expression")
        self.index += 1
        return token

    def compile(self):
        function, _ = self.expression()
        if self.peek() is not None:
            raise Unknown("unparsed_expression")
        return function

    def parse(self, **env):
        return self.compile()(env)

    @staticmethod
    def _combine(*kinds):
        if "custom" in kinds:
            raise Unknown("unspecified_precedence")

    def expression(self):
        function, kind = self.term()
        while self.peek() == "+" or self.peek() in _MINUS:
            plus = self.take() == "+"
            right, right_kind = self.term()
            self._combine(kind, right_kind)
            function, kind = _apply(operator.add if plus else operator.sub, function, right), "standard"
        return function, kind

    def term(self):
        function, kind = self.unary()
        while True:
            token = self.peek()
            if token in _TIMES or token in _DIVIDE:
                self.take()
                right, right_kind = self.unary()
                self._combine(kind, right_kind)
                function = _apply(operator.mul if token in _TIMES else operator.truediv, function, right)
                kind = "standard"
            elif self.implicit and token is not None and self._starts_atom(token):
                if token[0].isdigit() or token == "\\frac":
                    raise Unknown("ambiguous_juxtaposition")  # 2 1/3 or 3\frac{1}{3}: a mixed number?
                right, right_kind = self.unary()
                self._combine(kind, right_kind)
                function, kind = _apply(operator.mul, function, right), "standard"  # 2\sqrt{3}, 5i, 2(3+4)
            else:
                return function, kind

    def _starts_atom(self, token):
        return (token[0].isdigit() or token in {"(", "{", "\\sqrt", "√", "\\frac", "\\log"}
                or (token == "⟨" and self.angle is not None) or (token == "i" and self.unit)
                or token in self.variables)

    def unary(self):
        if self.peek() == "+" or self.peek() in _MINUS:
            negative = self.take() != "+"
            function, kind = self.unary()
            self._combine(kind)  # -1○2: (-1)○2 or -(1○2)?
            return (_apply(operator.neg, function) if negative else function), "standard"
        return self.chain()

    def chain(self):
        function, kind = self.power()
        while self.peek() in self.custom:
            rule = self.custom[self.take()]
            right, right_kind = self.power()
            if "standard" in (kind, right_kind):
                raise Unknown("unspecified_precedence")  # 3^2○1
            function, kind = _apply(rule, function, right), "custom"  # left to right
        return function, kind

    def power(self):
        base = self.atom()
        if self.peek() != "^":
            return base, "atom"
        self.take()
        negative = self.peek() in _MINUS
        if negative:
            self.take()
        exponent = self.atom()
        if negative:
            exponent = _apply(operator.neg, exponent)
        return _apply(_power, base, exponent), "standard"

    def group(self):
        if self.peek() == "{":
            self.take()
            function, _ = self.expression()
            self.take("}")
            return function
        return self.atom()

    def atom(self):
        token = self.take()
        if token[0].isdigit():
            self.literals.append(Fraction(token))
            return _constant(_Value(Fraction(token)))
        if token in _CLOSE:
            function, _ = self.expression()
            self.take(_CLOSE[token])
            return function
        if token == "⟨" and self.angle is not None:
            arity, rule = self.angle
            arguments = [self.expression()[0]]
            while self.peek() == ",":
                self.take()
                arguments.append(self.expression()[0])
            self.take("⟩")
            if len(arguments) != arity:
                raise Unknown("wrong_arity")
            return _apply(rule, *arguments)
        if token == "\\sqrt":
            return _apply(_sqrt, self.group())
        if token == "√":
            return _apply(_sqrt, self.atom())
        if token == "\\frac":
            numerator = self.group()
            return _apply(operator.truediv, numerator, self.group())
        if token == "\\log":
            self.take("_")
            base = self.group()
            return _apply(lambda base_, argument: _log(argument, base_), base, self.group())
        if token in self.variables:
            return lambda env: env[token]
        if token == "i" and self.unit:
            return _constant(_I)
        raise Unknown("unparsed_expression")


# ---------------------------------------------------------------- answer spans
def _puzzle_span(response):
    match = re.search(r"\[\[(.*?)\]\]", response, re.S)
    return None if match is None else match.group(1).strip()


def _operation_span(response):
    # Same fallback order as the official operation extraction.
    for pattern in (r"\[\[\s*(.*?)\s*\]\]", r"\$\\boxed\{(.*?)\}\$", r"\[\s*(.*?)\s*\]"):
        found = re.findall(pattern, response, re.S)
        if found:
            return found[0].strip()
    return None


def _values(span):
    """The listed answer values; an ``X=`` prefix per value is allowed."""
    parts = [p for p in re.split(r"\s*(?:\\text\{\s*or\s*\}|\bor\b|(?<=[0-9}i)])or(?=[-−0-9\\(√]))\s*", span) if p]
    if not parts:
        raise Unknown("unparsed_answer")
    return [_Parser(re.sub(r"^\s*[A-Za-z]\s*=\s*", "", part)).parse() for part in parts]


# ------------------------------------------------------------ question templates
_RULE_CHANGE = re.compile(r"change to the rule|ignoring the previous rule|given that|parameter", re.I)
# Answer-format instructions observed in the registered rules' public questions.
_FORMAT_SENTENCES = (
    "Please ensure the answer is a single number and wrap it in double square brackets, like this: [[your answer]].",
    "When providing your answer, please enclose it in double square brackets, like this: [[answer]].",
    "If there is more than one correct answer, separate the answers with 'or', like this: [[1or2]].",
    "The answer should only be given as a number.",
    "The answer may be negative; if so, write it in text format like '-5'.",
    "If there is more than one answer, please separate them with 'or', e.g., 1 or 2.",
    "Ensure that the final answer is wrapped in double square brackets, like this: [[1or2]].",
    "If the answer is a fraction, write it in 'a/b' text format.Decimals are not allowed.",
    "If the answer contains a root sign, write it in the form \\sqrt{x} (x is the number under the root sign).",
    "Please wrap the answer in double square brackets, like this: [[your answer]].",
    "Please provide your answer in LaTeX format.",
    "If the answer is a fraction, write it as \\frac{a}{b}.",
    "If it contains a root sign, use \\sqrt{x} where x is the number under the root.",
    "Wrap the final answer in double square brackets, like this: [[your answer]].",
    "If the answer cannot be reduced to an integer or fraction then retain the form \\log_{b}{a}+\\log_{a}{b}.",
    "If the answer is a complex number, write it in the form x + yi.",
    "The answer may be negative, if so write it in a format such as '-5'.",
    "The answer is a matrix, write it in this form:[[((a,b),(c,d))]].",
    "The answer is a matrix, write it in this form:[[((a,b,c),(d,e,f),(g,h,i))]].",
)
_PUZZLE_TEMPLATES = {
    "puzzle:twenty_four": "Your answer should be in the form of a calculation expression, like this: a + b / c - d, "
                          "giving one answer is sufficient. Wrap your final answer in double square brackets, "
                          "like this: [[a + b / c - d]].",
    "puzzle:hidato": "Output all the numbers in the grid, including both the original numbers and any numbers you "
                     "have filled in. List the numbers in the order from left to right, and from top to bottom. "
                     "Separate each number with a space, and separate different rows with a comma. Wrap your final "
                     "answer in double square brackets, like this: [[your answer]].",
    "puzzle:grid_letters": "Please provide each element in order from left to right, and from top to bottom, with each "
                           "element separated by a space and each row separated by a comma. Ensure that your final "
                           "answer is wrapped in double square brackets. For example, if the answer is: A B C D E F "
                           "G H I please output [[A B C,D E F,G H I]].",
    "puzzle:dominoes": "The answer should contain the coordinates of all dominoes in the format (row i,column j)"
                       "(row x,column y). The coordinates should be listed in order from left to right or top to "
                       "bottom. Different dominoes should be separated by commas. Ensure that your final answer is "
                       "enclosed in double square brackets, like this: [[(1,2)(1,3),(2,4)(3,4),(4,1)(4,2)]].",
    "puzzle:skyscrapers": "The answer should be given from left to right, top to bottom. Separate elements with a "
                          "space and rows with a comma. Wrap the entire answer in double square brackets.",
}


def _operation_head(question):
    """The question with its trailing known format instructions removed."""
    text = " ".join(question.split())
    tail = [False] * (len(text) + 1)
    tail[-1] = True
    for p in range(len(text) - 1, -1, -1):
        tail[p] = (text[p] == " " and tail[p + 1]) or any(
            text.startswith(s, p) and tail[p + len(s)] for s in _FORMAT_SENTENCES)
    start = next(p for p in range(len(text) + 1) if tail[p] and (p in (0, len(text)) or text[p - 1] == " "))
    return text[:start].strip()


def _puzzle_body(question, template):
    template = _PUZZLE_TEMPLATES[template]
    index = question.find(template[:24])
    if index < 0 or " ".join(question[index:].split()) != template:
        raise Unknown("unrecognized_instruction")
    return question[:index]


# --------------------------------------------------------------- operation rules
def _operation(custom, angle=None):
    def check(question, response):
        head = _operation_head(question)
        forward = re.fullmatch(r"Compute (?P<expression>.+?)\.?", head)
        inverse = re.fullmatch(r"If (?P<left>.+?)\s*=\s*(?P<right>[^,=]+?)\s*,?\s*[Ff]ind (?P<variable>[A-Za-z])\.?",
                               head)
        if forward:
            if "=" in forward.group("expression"):
                raise Unknown("ambiguous_question")
            expected = _Parser(forward.group("expression"), custom=custom, angle=angle).parse()
        elif inverse:
            variable, left = inverse.group("variable"), inverse.group("left")
            if _tokens(left).count(variable) != 1:
                raise Unknown("unknown_not_in_equation")
            # Compile the whole equation before looking at the answer.
            equation = _Parser(left, custom=custom, angle=angle, variables={variable}).compile()
            target = _Parser(inverse.group("right")).parse()
        else:
            raise Unknown("unparsed_question")
        span = _operation_span(response)
        if span is None:
            return "fail", "no_answer_span"
        values = _values(span)
        if forward:
            if len(values) != 1:
                return "fail", "multiple_answers_to_a_computation"
            matches = _compare(values[0], expected)
            return ("pass", "value_matches_rule") if matches else ("fail", "value_differs")
        for value in values:
            substituted = equation({variable: value})
            try:
                holds = _compare(substituted, target)
            except Unknown:
                holds = None
            if holds is False:
                return "fail", "substitution_violates_equation"
        raise Unknown("inverse_completeness_unverified")
    return check


def _multiple(a, b):
    a, b = _integer(a), _integer(b)
    if b != 0 and a % b == 0:
        return _Value(a // b + 2)
    if a != 0 and b % a == 0:
        return _Value(b // a + 2)
    return _Value(24)


def _pmatrix(body):
    rows = [[cell.strip() for cell in row.split("&")] for row in body.strip().split("\\\\") if row.strip()]
    if not rows or any(len(row) != len(rows[0]) for row in rows) \
            or not all(re.fullmatch(r"-?[0-9]+", cell) for row in rows for cell in row):
        raise Unknown("unparsed_question")
    return [[int(cell) for cell in row] for row in rows]


def _answer_matrix(span):
    """A complete matrix in the instructed ((a,b),(c,d)) form or a pmatrix; else unknown."""
    text = " ".join(span.split())
    pmatrix = re.fullmatch(r"\\begin\{pmatrix\}(.*)\\end\{pmatrix\}", text)
    if pmatrix:
        rows = [row.split("&") for row in pmatrix.group(1).split("\\\\") if row.strip()]
    else:
        nested = re.fullmatch(r"\(\s*(\([^()]*\)(?:\s*,\s*\([^()]*\))*)\s*\)", text)
        if nested is None:
            raise Unknown("unparsed_answer")
        rows = [row.split(",") for row in re.findall(r"\(([^()]*)\)", nested.group(1))]
    matrix = []
    for row in rows:
        cells = []
        for cell in row:
            value = _Parser(cell, unit=False).parse()
            if not value.exact:
                raise Unknown("inexact_matrix_entry")
            cells.append(value.real())
        matrix.append(cells)
    return matrix


def _matrix(symbol, cell):
    def check(question, response):
        head = _operation_head(question)
        found = re.fullmatch(r"A\s*=\s*\\\[\s*\\begin\{pmatrix\}(?P<a>.*?)\\end\{pmatrix\}\s*\\\]\s*"
                             r"B\s*=\s*\\\[\s*\\begin\{pmatrix\}(?P<b>.*?)\\end\{pmatrix\}\s*\\\]\s*"
                             r"Compute A\s*(?P<symbol>\S)\s*B\.?", head)
        if found is None or found.group("symbol") != symbol:
            raise Unknown("unparsed_question")
        a, b = _pmatrix(found.group("a")), _pmatrix(found.group("b"))
        if len(a) != len(b) or len(a[0]) != len(b[0]):
            raise Unknown("unparsed_question")
        expected = [[cell(x, y) for x, y in zip(row_a, row_b)] for row_a, row_b in zip(a, b)]
        span = _operation_span(response)
        if span is None:
            return "fail", "no_answer_span"
        answer = _answer_matrix(span)
        if [len(row) for row in answer] != [len(row) for row in expected]:
            return "fail", "matrix_shape"
        return ("pass", "matrix_matches_rule") if answer == expected else ("fail", "matrix_differs")
    return check


def _elementwise_power(x, y):
    if y < 0 or y > 64 or abs(x) > 10 ** 6:
        raise Unknown("unsupported_power")
    return x ** y


# ------------------------------------------------------------------ puzzle rules
def _layout(body, *, optional):
    """The body after exactly one leading "Grid Layout:" header; nothing may precede it."""
    text = body.lstrip()
    if text.startswith("Grid Layout:"):
        text = text[len("Grid Layout:"):]
    elif not optional:
        raise Unknown("unparsed_question")
    if "Grid Layout:" in text:
        raise Unknown("unparsed_question")
    return text


def _question_grid(body, allowed):
    rows = [line.split() for line in body.strip("\n").split("\n") if line.strip()]
    if not rows or any(len(row) != len(rows[0]) for row in rows) or any(not allowed(t) for r in rows for t in r):
        raise Unknown("unparsed_question")
    return rows


def _is_int(token):
    return re.fullmatch(r"[0-9]+", token) is not None


def _numeric_grid(span, height, width, single_digit=False):
    """Row-major cell values; None when the answer cannot be a complete grid."""
    rows = [row.split() for row in span.split(",")]
    if len(rows) == height and all(len(r) == width and all(_is_int(t) for t in r) for r in rows):
        return [[int(t) for t in r] for r in rows]
    if re.fullmatch(r"[0-9\s,;]*", span) is None:
        raise Unknown("unparsed_answer")  # words or symbols: not a representation we read
    numbers = re.findall(r"[0-9]+", span)
    if single_digit and sum(map(len, numbers)) == height * width:
        values = [int(c) for n in numbers for c in n]  # tolerate missing spaces between single digits
    elif len(numbers) == height * width:
        values = [int(n) for n in numbers]
    else:
        return None
    return [values[i * width:(i + 1) * width] for i in range(height)]


def _twenty_four(question, response):
    body = _puzzle_body(question, "puzzle:twenty_four")
    match = re.fullmatch(r"\s*The four randomly selected numbers are:\s*((?:[0-9]+[ \t]+){3}[0-9]+)\s*\.?\s*", body)
    if match is None:
        raise Unknown("unparsed_question")
    numbers = sorted(Fraction(v) for v in match.group(1).split())
    span = _puzzle_span(response)
    if span is None:
        return "fail", "no_answer_span"
    text = re.sub(r"\s*=\s*24\s*\.?\s*$", "", span)
    if any(t in {"^", "√", "\\sqrt", "\\log", "!", "%"} for t in _tokens(text)):
        return "fail", "operation_not_allowed"
    parser = _Parser(text, implicit=False, unit=False)
    try:
        value = parser.parse()
    except ZeroDivisionError:
        return "fail", "division_by_zero"
    if sorted(parser.literals) != numbers:
        return "fail", "numbers_not_used_exactly_once"
    return ("pass", "equals_24") if value.exact and value.re == 24 and value.im == 0 else ("fail", "not_24")


def _hidato(question, response):
    rows = _question_grid(_puzzle_body(question, "puzzle:hidato"), lambda t: t == "X" or _is_int(t))
    n = len(rows)
    if len(rows[0]) != n:
        raise Unknown("unparsed_question")
    span = _puzzle_span(response)
    if span is None:
        return "fail", "no_answer_span"
    values = _numeric_grid(span, n, n)
    if values is None:
        return "fail", "malformed_grid"
    if sorted(v for r in values for v in r) != list(range(1, n * n + 1)):
        return "fail", "not_each_number_once"
    if any(rows[i][j] != "X" and int(rows[i][j]) != values[i][j] for i in range(n) for j in range(n)):
        return "fail", "given_changed"
    where = {values[i][j]: (i, j) for i in range(n) for j in range(n)}
    for k in range(1, n * n):
        (a, b), (c, d) = where[k], where[k + 1]
        if abs(a - c) + abs(b - d) != 1:
            return "fail", "consecutive_numbers_not_adjacent"
    return "pass", "valid_path"


def _components(cells):
    cells, seen, parts = set(cells), set(), []
    for start in sorted(cells):
        if start in seen:
            continue
        stack, part = [start], []
        while stack:
            cell = stack.pop()
            if cell in seen:
                continue
            seen.add(cell)
            part.append(cell)
            i, j = cell
            stack += [p for p in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)) if p in cells]
        parts.append(part)
    return parts


def _islands(question, response):
    rows = _question_grid(_puzzle_body(question, "puzzle:grid_letters"), lambda t: t == "X" or _is_int(t))
    height, width = len(rows), len(rows[0])
    span = _puzzle_span(response)
    if span is None:
        return "fail", "no_answer_span"
    grid = [row.split() for row in span.split(",")]
    if len(grid) != height or any(len(r) != width for r in grid):
        if re.fullmatch(r"[0-9XA\s,;]*", span) is None:
            raise Unknown("unparsed_answer")
        tokens = re.findall(r"[0-9]+|[XA]", span)
        if len(tokens) != height * width:
            return "fail", "malformed_grid"
        grid = [tokens[i * width:(i + 1) * width] for i in range(height)]
    for i in range(height):
        for j in range(width):
            if (rows[i][j] != "X" and grid[i][j] != rows[i][j]) or (rows[i][j] == "X" and grid[i][j] not in {"X", "A"}):
                return "fail", "hint_changed_or_invalid_cell"
    walls = {(i, j) for i in range(height) for j in range(width) if grid[i][j] == "A"}
    land = {(i, j) for i in range(height) for j in range(width)} - walls
    for island in _components(land):
        hints = [int(grid[i][j]) for i, j in island if grid[i][j] != "X"]
        if len(hints) != 1 or hints[0] != len(island):
            return "fail", "island_hint_or_size"
    if any({(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} <= walls for i, j in walls):
        return "fail", "wall_2x2_block"
    if len(_components(walls)) > 1:
        return "fail", "walls_not_continuous"
    return "pass", "valid_islands"


def _latin(grid, n):
    full = set(range(1, n + 1))
    return all(set(row) == full for row in grid) and all({grid[i][j] for i in range(n)} == full for j in range(n))


def _sudoku(question, response):
    rows = _question_grid(_puzzle_body(question, "puzzle:grid_letters"),
                          lambda t: t == "X" or re.fullmatch(r"[1-9]", t) is not None)
    if len(rows) != 9 or len(rows[0]) != 9:
        raise Unknown("unparsed_question")
    span = _puzzle_span(response)
    if span is None:
        return "fail", "no_answer_span"
    grid = _numeric_grid(span, 9, 9, single_digit=True)
    if grid is None:
        return "fail", "malformed_grid"
    if any(rows[i][j] != "X" and int(rows[i][j]) != grid[i][j] for i in range(9) for j in range(9)):
        return "fail", "given_changed"
    boxes = all({grid[i][j] for i in range(r, r + 3) for j in range(c, c + 3)} == set(range(1, 10))
                for r in (0, 3, 6) for c in (0, 3, 6))
    return ("pass", "valid_sudoku") if _latin(grid, 9) and boxes else ("fail", "sudoku_constraint")


_COORDINATE = r"\(\s*(-?[0-9]+)\s*[,.]\s*(-?[0-9]+)\s*\)"
_DOMINO = _COORDINATE + r"\s*" + _COORDINATE


def _dominoes(question, response):
    rows = _question_grid(_layout(_puzzle_body(question, "puzzle:dominoes"), optional=True),
                          lambda t: re.fullmatch(r"[A-Z]", t) is not None)
    height, width = len(rows), len(rows[0])
    span = _puzzle_span(response)
    if span is None:
        return "fail", "no_answer_span"
    if not span:
        return "fail", "no_dominoes"
    if re.fullmatch(_DOMINO + r"(?:\s*[,;]?\s*" + _DOMINO + r")*", span) is None:
        raise Unknown("unparsed_answer")
    cells = [(int(r) - 1, int(c) - 1) for r, c in re.findall(_COORDINATE, span)]
    owner = {}
    for index in range(0, len(cells), 2):
        (a, b), (c, d) = cells[index], cells[index + 1]
        if not (0 <= a < height and 0 <= c < height and 0 <= b < width and 0 <= d < width) \
                or abs(a - c) + abs(b - d) != 1:
            return "fail", "domino_not_adjacent_cells"
        for cell in ((a, b), (c, d)):
            if cell in owner:
                return "fail", "overlapping_dominoes"
            owner[cell] = index
    for (i, j), index in owner.items():
        if any(owner.get(p, index) != index for p in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1))):
            return "fail", "dominoes_touch"
    # A region is a connected area of one letter; a letter may label several regions.
    regions = []
    for letter in {t for row in rows for t in row}:
        regions += _components({(i, j) for i in range(height) for j in range(width) if rows[i][j] == letter})
    if all(sum(cell in owner for cell in region) == 2 for region in regions):
        return "pass", "valid_dominoes"
    return "fail", "region_coverage"


def _visible(line):
    count, tallest = 0, 0
    for height in line:
        if height > tallest:
            count, tallest = count + 1, height
    return count


def _skyscrapers(question, response):
    body = _layout(_puzzle_body(question, "puzzle:skyscrapers"), optional=False)
    lines = [line.split() for line in body.strip("\n").split("\n") if line.strip()]
    n = len(lines[0]) if lines else 0
    if n < 2 or len(lines) != n + 2 or len(lines[-1]) != n or any(len(r) != n + 2 for r in lines[1:-1]):
        raise Unknown("unparsed_question")
    middle = lines[1:-1]
    clues = [lines[0], lines[-1], [r[0] for r in middle], [r[-1] for r in middle]]
    if not all(_is_int(t) and 1 <= int(t) <= n for group in clues for t in group) or not all(
            t == "X" or (_is_int(t) and 1 <= int(t) <= n) for r in middle for t in r[1:-1]):
        raise Unknown("unparsed_question")  # e.g. a 0 clue: "no clue" is not publicly defined
    top, bottom, left, right = ([int(t) for t in group] for group in clues)
    span = _puzzle_span(response)
    if span is None:
        return "fail", "no_answer_span"
    grid = _numeric_grid(span, n, n, single_digit=n <= 9)
    if grid is None:
        return "fail", "malformed_grid"
    if any(middle[i][j + 1] != "X" and int(middle[i][j + 1]) != grid[i][j] for i in range(n) for j in range(n)):
        return "fail", "given_changed"
    if not _latin(grid, n):
        return "fail", "latin_square"
    columns = [[grid[i][j] for i in range(n)] for j in range(n)]
    views = ([(clue, _visible(row)) for clue, row in zip(left, grid)]
             + [(clue, _visible(row[::-1])) for clue, row in zip(right, grid)]
             + [(clue, _visible(col)) for clue, col in zip(top, columns)]
             + [(clue, _visible(col[::-1])) for clue, col in zip(bottom, columns)])
    return ("pass", "valid_skyscrapers") if all(c == v for c, v in views) else ("fail", "visibility_clue")


# ------------------------------------------------------------------ cipher rules
_CIPHER_INPUT = re.compile(r'\s*(Plaintext|Ciphertext): "([^"]*)"(.*)', re.S)
MAX_CIPHER_INPUT = 1000


def _cipher_question(question):
    """(encrypt, quoted input, remaining fields) of a fully recognized cipher question."""
    match = _CIPHER_INPUT.fullmatch(question)
    if match is None:
        raise Unknown("unrecognized_question")
    kind, text, rest = match.groups()
    direction = "encrypted" if kind == "Plaintext" else "decrypted"
    instruction = (f"Please provide the {direction} answer, encapsulated in double square brackets. "
                   f"For example, the format should be: [[{direction} answer]].")
    rest = " ".join(rest.split())
    if not rest.endswith(instruction):
        raise Unknown("unrecognized_instruction")
    if len(text) > MAX_CIPHER_INPUT:
        raise Unknown("input_too_long")
    return kind == "Plaintext", text, rest[:-len(instruction)].strip()


def _cipher_clean(span):
    # The official cipher comparison removes exactly these characters from the response span.
    for char in '"\n []':
        span = span.replace(char, "")
    return span


def _letters(text, pattern="[A-Z]+"):
    if not re.fullmatch(pattern, text):
        raise Unknown("input_outside_rule")
    return text


def _plaintext(text, pattern="[A-Z]+"):
    # A decryption the rule cannot express as its stated plaintext alphabet is undefined.
    if not re.fullmatch(pattern, text):
        raise Unknown("undefined_by_rule")
    return text


def _fits(expected, answer):
    # A tuple lists, per position, the characters the rule leaves open there.
    if isinstance(expected, str):
        return answer == expected
    return len(answer) == len(expected) and all(c in options for c, options in zip(answer, expected))


def _cipher(readings, fields=""):
    """``readings(encrypt, text, *fields)`` gives the answer under every admissible reading."""
    def check(question, response):
        encrypt, text, extra = _cipher_question(question)
        match = re.fullmatch(fields, extra)
        if match is None:
            raise Unknown("unrecognized_question")
        expected = set(readings(encrypt, text, *match.groups()))
        if not expected or any(_cipher_clean("".join(e)) != "".join(e) for e in expected):
            raise Unknown("answer_not_comparable")  # e.g. a plaintext whose spaces the comparison would drop
        span = _operation_span(response)
        if span is None:
            return "fail", "no_answer_span"
        answer = _cipher_clean(span)
        if not any(_fits(e, answer) for e in expected):
            return "fail", "wrong_cipher_answer"
        if len(expected) > 1 or not isinstance(next(iter(expected)), str):
            raise Unknown("reading_dependent_answer")
        return "pass", "cipher_answer"
    return check


_AFFINE = "XMJQUDONPRGTVBWFAKSHZCYEIL"


def _affine(encrypt, text):
    index = _AFFINE.index
    return ["".join(_AFFINE[(3 * index(c) + 5) % 26 if encrypt else 9 * (index(c) - 5) % 26]
                    for c in _letters(text))]


_SOLITAIRE = "JDWOTRACXQMFYEZGUKPVBSHNLI"
_DECK = (9, 25, 44, 38, 40, 22, 11, 36, 13, 39, 18, 42, 10, 53, 26, 12, 1, 16, 3, 43, 37, 17, 30, 4, 28, 48, 27,
         41, 32, 15, 47, 29, 20, 51, 6, 7, 52, 34, 35, 5, 50, 9, 54, 46, 23, 31, 24, 14, 8, 33, 2, 49, 45, 21)


def _move(deck, card, steps):
    # Down by ``steps`` in a circular deck whose first position a moving joker never takes.
    index = deck.index(card)
    deck.pop(index)
    target = index + steps
    deck.insert(target - len(deck) if target > len(deck) else target, card)


def _keystream(deck):
    while True:
        _move(deck, 53, 1)
        _move(deck, 54, 2)
        first, second = sorted((deck.index(53), deck.index(54)))
        deck[:] = deck[second + 1:] + deck[first:second + 1] + deck[:first]   # triple cut
        count = min(deck[-1], 53)
        deck[:] = deck[count:-1] + deck[:count] + deck[-1:]                     # count cut
        value = deck[min(deck[0], 53)]
        if value < 53:                                                          # a joker repeats the algorithm
            return value


def _solitaire(encrypt, text):
    deck, out = list(_DECK), []
    for c in _letters(text):
        shift = _keystream(deck)
        out.append(_SOLITAIRE[(_SOLITAIRE.index(c) + (shift if encrypt else -shift)) % 26])
    return ["".join(out)]


_GRID = ("PHILS", "ABCDE", "FGKMN", "OQRTU", "VWXYZ")
_GRIDS = tuple(_GRID[-(k % 5):] + _GRID[:-(k % 5)] for k in range(8))  # Grid0..Grid7 as listed


def _grid_shift(encrypt, text):
    step = 1 if encrypt else -1

    def shift(c, grid):
        if c == "J":
            return c
        row = next(r for r, line in enumerate(grid) if c in line)
        return grid[(row + step) % 5][(grid[row].index(c) + step) % 5]
    # grid_index = (i // 5) % 8 with i the character number (encryption prose) or the block number (decryption).
    return {"".join(shift(c, _GRIDS[(i // 5 // (5 if by_block else 1)) % 8]) for i, c in enumerate(_letters(text)))
            for by_block in (False, True)}


_PORTA = ("NOPQRSTUVWXYZABCDEFGHIJKLM", "ZNOPQRSTUVWXYBCDEFGHIJKLMA", "YZNOPQRSTUVWXCDEFGHIJKLMAB",
          "XYZNOPQRSTUVWDEFGHIJKLMABC", "WXYZNOPQRSTUVEFGHIJKLMABCD", "VWXYZNOPQRSTUFGHIJKLMABCDE",
          "UVWXYZNOPQRSTGHIJKLMABCDEF", "TUVWXYZNOPQRSHIJKLMABCDEFG", "STUVWXYZNOPQRIJKLMABCDEFGH",
          "RSTUVWXYZNOPQJKLMABCDEFGHI", "QRSTUVWXYZNOPKLMABCDEFGHIJ", "PQRSTUVWXYZNOLMABCDEFGHIJK",
          "OPQRSTUVWXYZNMABCDEFGHIJKL")


def _porta(encrypt, text, key):
    alphabets = [_PORTA[(ord(k) - 65) // 2] for k in _letters(key)]
    return ["".join(alphabets[i % len(alphabets)][ord(c) - 65] if encrypt
                    else chr(65 + alphabets[i % len(alphabets)].index(c)) for i, c in enumerate(_letters(text)))]


_OUTER, _INNER = "QWERTYUIOPASDFGHJZXCVBNMKL", "JKLZXCVBNMASDFGHJQWERTYUIO"


def _disks(encrypt, text, period, increment):
    period, increment = int(period), int(increment) % 26
    if period < 1:
        raise Unknown("input_outside_rule")
    answers = set()
    # The prose rotates "to the right"; its own example moves the first characters to the end.
    for rotate in (lambda s: s[increment:] + s[:increment], lambda s: s[len(s) - increment:] + s[:len(s) - increment]):
        inner, out = _INNER, []
        for i, c in enumerate(_letters(text)):
            # The inner disk lists J twice and omits P: a J decrypts to either partner, a P to nothing.
            options = inner[_OUTER.index(c)] if encrypt else "".join(_OUTER[j] for j, x in enumerate(inner) if x == c)
            if not options:
                raise Unknown("undefined_by_rule")
            out.append(options)
            if (i + 1) % period == 0:
                inner = rotate(inner)
        answers.add("".join(out) if all(len(o) == 1 for o in out) else tuple(out))
    return answers


_MORSE = {"A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....",
          "I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.",
          "Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
          "Y": "-.--", "Z": "--.."}
_PAIRS = {"..": "5", ".-": "4", "./": "9", "-.": "8", "--": "6", "-/": "7", "/.": "3", "/-": "1", "//": "2"}


def _morse_pairs(encrypt, text):
    if encrypt:
        code = "/".join(_MORSE[c] for c in _letters(text))
        return ["".join(_PAIRS[code[i:i + 2]] for i in range(0, len(code) - 1, 2)) + code[len(code) // 2 * 2:]]
    digits, tail = re.fullmatch(r"([1-9]*)([./-]?)", _letters(text, r"(?=.)[1-9]*[./-]?")).groups()
    pairs, letters = {v: k for k, v in _PAIRS.items()}, {v: k for k, v in _MORSE.items()}
    # The unmapped trailing symbol rejoins the Morse code: decryption is the exact opposite of encryption.
    words = ("".join(pairs[d] for d in digits) + tail).split("/")
    if not all(w in letters for w in words):
        raise Unknown("undefined_by_rule")
    return ["".join(letters[w] for w in words)]


def _rail_columns(encrypt, text):
    if not encrypt:
        rows = _letters(text, r"(?:[A-Z#]*\*){5}").split("*")[:5]
        out = []
        for j in range(max(map(len, rows))):
            column = [row[j] for row in rows if j < len(row)]
            out += column if j % 2 == 0 else column[::-1]  # read down, then up, alternately
        return [_plaintext("".join(out).replace("#", ""))]
    letters = _letters(text)
    columns = [letters[:5]] + [letters[i:i + 4] for i in range(5, len(letters), 4)]
    answers = set()
    # Its worked example puts an upward column's "#" on line 5; its prose puts it on line 1 after the
    # letters, without saying whether a partly filled upward column still gets it.
    for reading in ("example", "prose_with_mark", "prose_without_mark"):
        rows = [""] * 5
        for j, chunk in enumerate(columns):
            if j == 0:
                cells = zip(range(5), chunk)
            elif j % 2 == 0:
                cells = zip(range(5), "#" + chunk)
            elif reading == "example":
                cells = zip((4, 3, 2, 1, 0), "#" + chunk)
            else:
                mark = reading == "prose_with_mark" or len(chunk) == 4
                cells = [*zip((4, 3, 2, 1), chunk), *([(0, "#")] if mark else [])]
            for row, char in cells:
                rows[row] += char
        answers.add("".join(row + "*" for row in rows))
    return answers


_BLOCK_KEY = b"1234567890ABCDEF"
_SBOX = (0x0F, 0x0A, 0x07, 0x05, 0x09, 0x03, 0x0D, 0x00, 0x0E, 0x08, 0x04, 0x06, 0x01, 0x02, 0x0B, 0x0C)


def _sbox_blocks(encrypt, text):
    answers = set()
    inverse = tuple(_SBOX.index(v) for v in range(16))
    # Each 8-byte block meets the 16-byte key: restart at its first byte per block, or continue through it.
    for span in (8, 16):
        out = bytearray()
        if encrypt:
            data = _letters(text, "[A-Z ]+").encode("ascii")
            for i, byte in enumerate(data + b"\0" * (-len(data) % 8)):
                byte ^= _BLOCK_KEY[i % span]
                byte = _SBOX[byte >> 4] << 4 | _SBOX[byte & 15]
                out.append(((byte << 1 | byte >> 7) & 0xFF) ^ _BLOCK_KEY[i % span])
            answer = out.hex().upper()
            # Its output spec capitalizes only hexadecimal A-E, so an F may be written either way.
            answers |= {answer, tuple("Ff" if c == "F" else c for c in answer) if "F" in answer else answer}
            continue
        for i, byte in enumerate(bytes.fromhex(_letters(text, "(?:[0-9A-Ff]{16})+"))):
            byte ^= _BLOCK_KEY[i % span]
            byte = (byte >> 1 | byte << 7) & 0xFF
            out.append((inverse[byte >> 4] << 4 | inverse[byte & 15]) ^ _BLOCK_KEY[i % span])
        plain = out.rstrip(b"\0").decode("latin-1")
        if re.fullmatch("[A-Z ]+", plain):  # a reading that yields no stated plaintext is not admissible
            answers.add(plain)
    if not answers:
        raise Unknown("undefined_by_rule")
    return answers


def _ascii_scale(encrypt, text):
    if encrypt:
        return [",".join(str(ord(c) * 12) for c in _letters(text))]
    numbers = _letters(text, r"[0-9]{1,6}(?:,[0-9]{1,6})*").split(",")
    return [_plaintext("".join(chr(int(n) // 12) for n in numbers))]


HANDLERS = {
    "operation:multiple": _operation({"※": _multiple}),
    "operation:circle": _operation({"○": lambda a, b: (a + _Value(3) * b) * (a + b)}),
    "operation:angle": _operation({}, angle=(4, lambda a, b, c, d: _Value(2) * a * b + c - d)),
    "operation:venus_mars": _operation({"♀": lambda a, b: (a + b) / _Value(2), "♂": lambda a, b: _Value(4) * a + b}),
    "operation:sqrt": _operation({"①": lambda a, b: _sqrt(a) + b * b, "②": lambda a, b: _sqrt(a) * b}),
    "operation:log": _operation({"￠": lambda a, b: _log(a, b) + _log(b, a)}),
    "operation:complex_pair": _operation({"⊕": lambda a, b: a + b * _I}),
    "operation:complex_square": _operation({"◎": lambda a, b: (a + b * _I) * (a + b * _I)}),
    "operation:matrix_power": _matrix("&", _elementwise_power),
    "operation:matrix_affine": _matrix("€", lambda x, y: 2 * x + 3 * y),
    "puzzle:twenty_four": _twenty_four,
    "puzzle:hidato": _hidato,
    "puzzle:islands": _islands,
    "puzzle:sudoku": _sudoku,
    "puzzle:dominoes": _dominoes,
    "puzzle:skyscrapers": _skyscrapers,
    "cipher:affine": _cipher(_affine),
    "cipher:solitaire": _cipher(_solitaire),
    "cipher:grid_shift": _cipher(_grid_shift),
    "cipher:porta": _cipher(_porta, r"Key: ([A-Z]+)"),
    "cipher:disks": _cipher(_disks, r"period: ([0-9]{1,4}) increment: ([0-9]{1,4})"),
    "cipher:morse_pairs": _cipher(_morse_pairs),
    "cipher:rail_columns": _cipher(_rail_columns),
    "cipher:sbox_blocks": _cipher(_sbox_blocks),
    "cipher:ascii_scale": _cipher(_ascii_scale),
}

# sha256 of the exact public KOR rule text -> handler; only these texts are checked.
# Not registered: cipher rule 21 (its fixed key is named only as an example, "e.g.", so no
# answer is fixed by the public text), word-suffix and logic-grid puzzles (need a lexicon or free-text
# clue parsing), grid-sum puzzles (the "specified set" of numbers is not public)
# and arrow mazes (the public text fixes neither jump distance nor which landings
# count as "inflection points").
RULES = {
    "0a8f117f381c855d4c3643355e3589f1d6347e8976b1155f63dbc8aefeba2300": "operation:angle",
    "f580d18a3d0726ebd835b4578791541741d4f9b29d56861bc83015d372ed1df1": "operation:circle",
    "ae9a7d101bfa9161bc454b8f2a8c00c6102213c5b5bf94e473dae8076cd97657": "operation:complex_pair",
    "2852d61f9f957e6369ef2a52653cc77d4a8f37bc08249b5a0b73282d278c7ffe": "operation:complex_square",
    "dd6f40b2937dd200969307e7d9951337d3d99fd1303c5a3ace52b46d5e834177": "operation:log",
    "2317fbeb07bccfd054fd3187ac9f74551815d2e20f096cbfb8f442c68f4c2a35": "operation:matrix_affine",
    "6e91a231c5274509652a5ae8b9a875c2a413b5d2598815023100efeb8546173b": "operation:matrix_power",
    "8c7dd333754ee3c1f56763adb95670a9288961f2d9f794a7c7efcaeb79aa71ee": "operation:multiple",
    "007be49f4f841bb9daae2161b8c64faec1fb86a8b277d25e78468f47d0064f48": "operation:sqrt",
    "9875028fc445d09ce3ac327e62cbd39a699306f02c8b4ddb1546f51abbc12a18": "operation:venus_mars",
    "0a4ddc9d9a406b9ef3930aa125d63b39f055d23a459bc34c152e3d5ead2aee16": "puzzle:dominoes",
    "8a7410ba6fc4737118c9d43cd172316d421af6c14340c04deb78919394c3d2a0": "puzzle:hidato",
    "4f3cd425f139794588a37eafe863b33daa8bb45f0b02d48b44de77dd5eac6c18": "puzzle:islands",
    "332d3bf55d6ea1f0a6db746cdc99f13a8d8b30899cffe5896d8606d570203515": "puzzle:skyscrapers",
    "cfc14cfa03c2e2a40bb08d0b34c16b02fcaf4909956835ba4c44e736833b2512": "puzzle:sudoku",
    "482ee0aca292a74878ace115b99e95e018814f4281c4ec4f9df1a13e63b78d81": "puzzle:twenty_four",
    "e3c0ebaa02b3aa3a355004a05a4291a40d38db2f10883c88e188ab6d8bb5c90f": "cipher:affine",
    "8eca8eeda76db554fa5ce29f4efb1e5fdcfae0faabb6d40a7205e1a64edaa5f2": "cipher:solitaire",
    "37f052dd0c40365783167c148de2c5a368bd446bd3f8f93fc3134e044b848608": "cipher:grid_shift",
    "f3e138da05cadaf95795c18d5ce18104075c3a6d4220e3ec40d923255532388d": "cipher:porta",
    "dbf633d3e0832d9c465e44ad6af432b7ded7352a9e871f253c9a49112fecb6dd": "cipher:disks",
    "aa8d071bed655c5d822b06742d906a0bb600e163d1380c8afc1d25032107320f": "cipher:morse_pairs",
    "8cd20f759610034c6d7dd2e1926bd8d1e128991290b327ae1504137a540511dd": "cipher:rail_columns",
    "d31d789eb29dd359a4d6c232f98fefa6b72667dbfcecffb39284de933b2e1456": "cipher:sbox_blocks",
    "dd19412f1555bfb94b239792c86f4538852e76467960d423cebcc41f24089ed1": "cipher:ascii_scale",
}
# The public KOR (category, rule_id) each handler implements; studies check it on the panel.
RULE_IDS = {
    "operation:multiple": ("operation", "1"), "operation:circle": ("operation", "2"),
    "operation:angle": ("operation", "3"), "operation:venus_mars": ("operation", "7"),
    "operation:sqrt": ("operation", "8"), "operation:log": ("operation", "10"),
    "operation:complex_pair": ("operation", "13"), "operation:complex_square": ("operation", "14"),
    "operation:matrix_power": ("operation", "23"), "operation:matrix_affine": ("operation", "25"),
    "puzzle:twenty_four": ("puzzle", "10"), "puzzle:hidato": ("puzzle", "13"), "puzzle:islands": ("puzzle", "14"),
    "puzzle:sudoku": ("puzzle", "15"), "puzzle:dominoes": ("puzzle", "23"), "puzzle:skyscrapers": ("puzzle", "25"),
    "cipher:affine": ("cipher", "5"), "cipher:solitaire": ("cipher", "6"), "cipher:grid_shift": ("cipher", "7"),
    "cipher:porta": ("cipher", "8"), "cipher:disks": ("cipher", "9"), "cipher:morse_pairs": ("cipher", "12"),
    "cipher:rail_columns": ("cipher", "16"), "cipher:sbox_blocks": ("cipher", "22"),
    "cipher:ascii_scale": ("cipher", "24"),
}


def verify(rule, question, response, rules=None):
    rules = RULES if rules is None else rules
    if not all(type(v) is str for v in (rule, question, response)):
        return {"status": "unknown", "reason": "invalid_input", "handler": None, "version": VERSION}
    handler = rules.get(rule_hash(rule))
    if handler is None:
        return {"status": "unknown", "reason": "unregistered_rule", "handler": None, "version": VERSION}
    if len(response) > MAX_RESPONSE_CHARS:
        status, reason = "unknown", "response_too_long"
    elif _RULE_CHANGE.search(question) and not handler.startswith("cipher:"):
        # A cipher question is consumed whole by its template, so its quoted data is never an instruction.
        status, reason = "unknown", "rule_changed_in_question"
    else:
        try:
            status, reason = HANDLERS[handler](question, response)
        except Unknown as exc:
            status, reason = "unknown", str(exc)
        except (ArithmeticError, ValueError, RecursionError) as exc:
            status, reason = "unknown", "evaluation_error:" + type(exc).__name__
    return {"status": status, "reason": reason, "handler": handler, "version": VERSION}
