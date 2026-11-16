"""typed-v3 item bank evaluator (bank/calc.py): exact rational arithmetic, the statistics against the standard
library, certified rounding of inexact values, the grammar's refusals. No model, no file."""
import math
import statistics
from fractions import Fraction

import pytest

from skillopt.execskill.typed.bank import calc

V = {'a': Fraction(3), 'b': Fraction(4), 'c': Fraction('10.5'), 'd': Fraction(-2)}


def value(expression, bound=V):
    return calc.evaluate(expression, bound)


def reason(expression, bound=V):
    with pytest.raises(calc.CalcError) as caught:
        calc.evaluate(expression, bound)
    return caught.value.reason


def test_rational_arithmetic_is_exact():
    assert value('(a + b) * c / 7 - d ** 3') == (Fraction('10.5') + 8, True)
    assert value('a / b') == (Fraction(3, 4), True)
    assert value('2 ** -2 + abs(d) + min(a, b, c) + max([a, b])') == (Fraction(1, 4) + 2 + 3 + 4, True)
    assert value('sum(a, b, c) + mean([a, b]) + median(a, b, c, d)') == (Fraction('17.5') + Fraction(7, 2) + Fraction(7, 2), True)
    assert value('var_pop(a, b) + var_samp(a, b)') == (Fraction(1, 4) + Fraction(1, 2), True)
    assert value('round(c / a, 1) + round(2.5) + round(-2.5)') == (Fraction('3.5') + 3 - 3, True)
    assert value('a − b × 2 ÷ 4') == (Fraction(1), True)
    assert value('pow(a, 2) + 0.1 + 0.2') == (Fraction(93, 10), True)                   # decimal literals are exact


def test_irrational_functions_match_the_library_and_are_marked_inexact():
    cases = {'sqrt(b + c)': math.sqrt(14.5), 'ln(c)': math.log(10.5), 'log10(c)': math.log10(10.5), 'exp(a / b)': math.exp(.75),
             'c ** 0.5': math.sqrt(10.5), '(c / a) ** (1 / 8) - 1': 3.5 ** .125 - 1, 'pow(a, 1.5)': 3 ** 1.5,
             'stdev_pop(a, b, c)': statistics.pstdev([3, 4, 10.5]), 'stdev_samp([a, b, c])': statistics.stdev([3, 4, 10.5]),
             'geomean(a, b, c)': statistics.geometric_mean([3, 4, 10.5]),
             'corr(a, b, c, 1, 2, 5)': statistics.correlation([3, 4, 10.5], [1, 2, 5]),
             'stdev_pop(a, b, c) / abs(mean(a, b, c))': statistics.pstdev([3, 4, 10.5]) / (17.5 / 3)}
    for expression, expected in cases.items():
        got, exact = value(expression)
        assert not exact and abs(float(got) - expected) < 1e-12 * max(1, abs(expected)), expression
    got, exact = value('sqrt(4) * 2')
    assert got == 4 and not exact                                                        # exact in value, not known to be


def test_refusals():
    assert reason('a + z') == 'name'
    assert reason('a +') == 'syntax'
    assert reason('') == 'text'
    assert reason('a / (b - 4)') == 'division_by_zero'
    assert reason('sqrt(d)') == 'domain' and reason('ln(0)') == 'domain' and reason('d ** 0.5') == 'domain'
    assert reason('geomean(a, d)') == 'domain' and reason('corr(a, a, 1, 2)') == 'domain'
    assert reason('a ** 100') == 'exponent' and reason('10 ** 60') == 'magnitude'
    assert reason('mean(a)') == 'arguments' and reason('corr(a, b, c)') == 'arguments' and reason('round(a, 0.5)') == 'arguments'
    assert reason('a if b else c') == 'grammar' and reason('__import__("os")') == 'grammar' and reason('a.real') == 'grammar'
    assert reason('[a, b]') == 'grammar' and reason('abs(x=a)') == 'grammar' and reason('a < b') == 'grammar'
    assert reason('1e3 + a') == 'literal' and reason('"a"') == 'literal' and reason('True + a') == 'literal'
    assert reason('a + 1,000') == 'grammar'                                              # a comma makes a tuple
    assert reason('+'.join(['a'] * 4000)) == 'size'
    assert reason('abs(' * 90 + 'a' + ')' * 90) == 'depth' and value('(' * 60 + 'a' + ')' * 60) == (3, True)
    assert reason('round(sqrt(6.25), 0)') == 'uncertain_rounding'                        # 2.5: an inexact value at a tie


def test_long_sums_fit():
    bound = {'v%d' % i: Fraction(i) for i in range(1, 41)}
    assert calc.evaluate('+'.join(sorted(bound)), bound) == (Fraction(820), True)
    assert calc.evaluate('sum([%s])' % ', '.join(sorted(bound)), bound)[0] == 820
    assert calc.names('sum(v1, v2) + mean([x, y]) * sqrt(z)') == {'v1', 'v2', 'x', 'y', 'z'}
    assert calc.literals('a * 1000000 + 0.50 - b / 12') == ['1000000', '0.50', '12']
    assert calc.operations('stdev_pop(a, b) / mean(a, b) * 100 - c ** 2') == ['div', 'mean', 'mul', 'pow', 'stdev_pop', 'sub']


def test_answer_text_and_certified_rounding():
    assert calc.text(Fraction(600100, 10102), 2, True) == '59.40' and calc.text(Fraction(-5, 2), 0, True) == '-3'
    assert calc.text(Fraction(1, 8), None, True) == '0.125' and calc.text(Fraction(894), None, True) == '894'
    assert calc.text(Fraction(-1, 2000), 2, True) == '0.00'                              # never a negative zero
    assert calc.text(Fraction('0.0124'), 4, True) == '0.0124' and calc.text(Fraction(7), 3, True) == '7.000'
    with pytest.raises(calc.CalcError) as caught:
        calc.text(Fraction(1, 3), None, True)
    assert caught.value.reason == 'not_terminating'
    with pytest.raises(calc.CalcError) as caught:
        calc.text(Fraction(1, 4), None, False)
    assert caught.value.reason == 'not_terminating'
    with pytest.raises(calc.CalcError) as caught:
        calc.text(Fraction(1), 7, True)
    assert caught.value.reason == 'decimals'
    root, exact = calc.evaluate('sqrt(x)', {'x': Fraction('6.25')})                      # 2.5 up to 10^-55
    with pytest.raises(calc.CalcError) as caught:
        calc.text(root, 0, exact)
    assert caught.value.reason == 'rounding_tie'
    assert calc.text(root, 1, exact) == '2.5' and calc.text(root, 3, exact) == '2.500'
    assert calc.candidates(Fraction('2.125'), 2, True) == ['2.13', '2.12']               # an exact tie: both neighbours
    assert calc.candidates(Fraction('-2.125'), 2, True) == ['-2.13', '-2.12']
    assert calc.candidates(Fraction('2.126'), 2, True) == ['2.13'] and calc.candidates(Fraction(5, 2), None, True) == ['2.5']
    assert calc.near_tie(Fraction('0.125'), 2) and not calc.near_tie(Fraction('0.1251'), 2)


def test_number_as_printed():
    assert calc.number('10,102') == 10102 and calc.number('0.063') == Fraction(63, 1000) and calc.number('−109') == -109
    for bad in ('$5', '5%', '(18)', '.5', '1e3', '1,00'):
        with pytest.raises(calc.CalcError):
            calc.number(bad)


def test_an_inexact_value_carries_an_enclosure_that_decides_the_rounding():
    import copy
    import pickle
    root, exact = calc.evaluate('sqrt(2)', {})
    assert not exact and isinstance(root, calc.Approx) and root.lo < root < root.hi
    assert root.lo ** 2 < 2 < root.hi ** 2 and root.hi - root.lo < Fraction(1, 10 ** 50)
    for same in (copy.copy(root), copy.deepcopy(root), pickle.loads(pickle.dumps(root))):
        assert (same.lo, same.hi) == (root.lo, root.hi) and same == root
    # the enclosure follows the value into a later expression (a named step) and grows with what is done to it
    scaled, exact = calc.evaluate('s * 10 ** 30', {'s': root})
    assert not exact and scaled.hi - scaled.lo == (root.hi - root.lo) * 10 ** 30
    assert calc.evaluate('round(s, 3)', {'s': root}) == (Fraction('1.414'), True)          # proved, so exact again
    assert calc.text(root, 4, False) == '1.4142'
    # review 2026-11-13: the true value is 12 + 1 - 5e-65, which rounds to 13; sixty digits alone gave 12
    lost, exact = calc.evaluate('a + ln(1 + 10 ** -64) / (10 ** -64)', {'a': Fraction(12)})
    assert not exact and lost.lo <= 13 - Fraction(1, 10 ** 60) <= lost.hi
    with pytest.raises(calc.CalcError) as refused:
        calc.text(lost, 0, exact)
    assert refused.value.reason == 'rounding_tie'
    assert calc.near_tie(lost, 0) and not calc.near_tie(root, 6)
    with pytest.raises(calc.CalcError) as refused:
        calc.evaluate('1 / (sqrt(4) - 2)', {})                                           # a divisor that may be zero
    assert refused.value.reason == 'uncertain_rounding'
    with pytest.raises(calc.CalcError) as refused:
        calc.evaluate('round(a + ln(1 + 10 ** -64) / (10 ** -64), 0)', {'a': Fraction(12)})
    assert refused.value.reason == 'uncertain_rounding'
    # statistics over exact numbers: the enclosure is tight and holds the library's value
    import math
    import statistics
    for expression, expected in (('stdev_samp(2, 4, 4, 4, 5, 5, 7, 9)', statistics.stdev([2, 4, 4, 4, 5, 5, 7, 9])),
                                 ('geomean(1, 3, 9, 27)', statistics.geometric_mean([1, 3, 9, 27])),
                                 ('corr(1, 2, 3, 4, 2, 4, 5, 9)', statistics.correlation([1, 2, 3, 4], [2, 4, 5, 9])),
                                 ('pow(2, 0.5) * ln(10) - log10(7) + exp(1)',
                                  2 ** 0.5 * math.log(10) - math.log10(7) + math.e)):
        got, exact = calc.evaluate(expression, {})
        assert not exact and got.hi - got.lo < Fraction(1, 10 ** 45) and abs(float(got) - expected) < 1e-12, expression


def test_random_expressions_stay_inside_their_enclosures():
    """An independent 250-digit evaluation of 700 seeded random expressions (statistics, logarithms, fractional
    powers, near-cancelling values) must lie inside the enclosure the evaluator returns, and the enclosures of
    well-conditioned expressions stay tight."""
    import ast
    import random
    from decimal import Decimal, localcontext

    def D(f):
        return Decimal(f.numerator) / Decimal(f.denominator)


    def ref(node, bound):
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value)) if not isinstance(node.value, float) else Decimal(repr(node.value))
        if isinstance(node, ast.Name):
            return D(bound[node.id])
        if isinstance(node, ast.UnaryOp):
            return -ref(node.operand, bound) if isinstance(node.op, ast.USub) else ref(node.operand, bound)
        if isinstance(node, ast.BinOp):
            a, b = ref(node.left, bound), ref(node.right, bound)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div): return a / b
            if b == b.to_integral_value(): return a ** int(b)
            return (b * a.ln()).exp()
        name = node.func.id
        args = node.args[0].elts if len(node.args) == 1 and isinstance(node.args[0], (ast.List, ast.Tuple)) else node.args
        v = [ref(x, bound) for x in args]
        n = len(v)
        if name == 'abs': return abs(v[0])
        if name == 'sqrt': return v[0].sqrt()
        if name == 'ln': return v[0].ln()
        if name == 'log10': return v[0].log10()
        if name == 'exp': return v[0].exp()
        if name == 'pow': return v[0] ** int(v[1]) if v[1] == v[1].to_integral_value() else (v[1] * v[0].ln()).exp()
        if name == 'min': return min(v)
        if name == 'max': return max(v)
        if name == 'sum': return sum(v)
        mean = sum(v) / n
        if name == 'mean': return mean
        if name == 'median':
            s = sorted(v); return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
        if name in ('var_pop', 'var_samp', 'stdev_pop', 'stdev_samp'):
            var = sum((x - mean) ** 2 for x in v) / (n if name.endswith('pop') else n - 1)
            return var if name.startswith('var') else var.sqrt()
        if name == 'geomean': return (sum(x.ln() for x in v) / n).exp()
        xs, ys = v[:n // 2], v[n // 2:]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)).sqrt()

    rng = random.Random(20261113)
    NAMES = 'abcde'
    def leaf():
        return rng.choice(NAMES) if rng.random() < 0.7 else rng.choice(['2', '3', '100', '0.5', '12', '1.07', '0.001'])
    def series(k=None):
        k = k or rng.randint(2, 6)
        return ', '.join(expr(1) for _ in range(k))
    def expr(depth):
        if depth <= 0 or rng.random() < 0.25:
            return leaf()
        kind = rng.random()
        if kind < 0.40:
            return '(%s %s %s)' % (expr(depth - 1), rng.choice(['+', '-', '*', '/']), expr(depth - 1))
        if kind < 0.47:
            return '(%s ** %s)' % (expr(depth - 1), rng.choice(['2', '3', '-1', '-2', '0.5', '0.25', '(1 / 3)', '1.5']))
        if kind < 0.70:
            return '%s(%s)' % (rng.choice(['sqrt', 'ln', 'log10', 'exp', 'abs']), expr(depth - 1))
        if kind < 0.75:
            return 'pow(%s, %s)' % (expr(depth - 1), rng.choice(['0.5', '1 / 12', '2', '-0.5', '1 / 7']))
        if kind < 0.95:
            return '%s(%s)' % (rng.choice(['min', 'max', 'sum', 'mean', 'median', 'var_pop', 'var_samp', 'stdev_pop', 'stdev_samp', 'geomean']), series())
        return 'corr(%s)' % series(2 * rng.randint(2, 4))


    checked = unsound = 0
    with localcontext() as context:
        context.prec = 250
        for _ in range(700):
            bound = {name: Fraction(rng.randint(1, 999999), 10 ** rng.randint(0, 4)) for name in NAMES}
            if rng.random() < 0.15:
                bound['b'] = bound['a'] + Fraction(rng.randint(1, 9), 10 ** rng.randint(3, 30))
            text = expr(3)
            try:
                value, is_exact = calc.evaluate(text, bound)
                truth = ref(ast.parse(text, mode='eval').body, bound)
            except Exception:
                continue
            if not truth.is_finite():
                continue
            checked += 1
            truth = Fraction(truth)
            slack = abs(truth) * Fraction(1, 10 ** 200) + Fraction(1, 10 ** 200)
            lo, hi = (value.lo, value.hi) if isinstance(value, calc.Approx) else (value, value)
            assert is_exact == (lo == hi), text
            if not (lo - slack <= truth <= hi + slack):
                unsound += 1
    assert checked > 400 and unsound == 0


def test_ordinary_compounding_stays_inside_the_size_bounds():
    # second review 2026-11-13: sixty monthly factors of an annual 10 % -- the widened ends were raised digit for digit
    value, exact = calc.evaluate('(g ** (1 / 12)) ** 60', {'g': Fraction(11, 10)})
    assert not exact and value.lo < Fraction(11, 10) ** 5 < value.hi and calc.text(value, 6, exact) == '1.610510'
    value, exact = calc.evaluate('sqrt(g) ** 60', {'g': Fraction(101, 100)})
    assert calc.text(value, 6, exact) == '1.347849' and value.hi - value.lo < Fraction(1, 10 ** 50)
    growth, exact = calc.evaluate('(pow(b / a, 1 / 7) - 1) * 100', {'a': Fraction(1234), 'b': Fraction(5678)})
    assert calc.text(growth, 2, exact) == '%.2f' % (((5678 / 1234) ** (1 / 7) - 1) * 100)   # far from a tie
    # an exact value is never compacted, however long
    long, exact = calc.evaluate('(a / 3) ** 40', {'a': Fraction(7)})
    assert exact and long == Fraction(7, 3) ** 40
