"""Gates for typed-v2: the read-side paired statistics without SciPy (``paired_statistics``, ``split_pairs``,
``noise_threshold``: the readout's contrasts and same-request noise of read events) and, re-exported from
``gatestats`` (addendum 2026-11-12 16:1x, module placement), the repeat statistics and the card / program / no-harm
decisions of DESIGN 3.4 (D5): R fresh runs per item and arm, exact integer decisions, ``recompute``.

Read-side pairs are ``(item_id, first, second)`` with booleans; an item whose either side is unknown (None) is
excluded from the paired statistics and counted in ``excluded_unknown`` (never scored as wrong). The gate decisions
never exclude an item: a model-side unknown run scores 0 (addendum O1) and an undecidable arm pauses the chain.
"""
from __future__ import annotations

import math

from . import SEED, TAU_MIN_POINTS, TAU_SE_MULTIPLIER
from .gatestats import (CARD_REASONS, MEMBER_HARM, NO_HARM_REASONS, NOISE_RULE, PROGRAM_REASONS,  # noqa: F401
                        REPEAT_SEP, SCORES, UndecidableRuns, arm_of_label, arm_runs, calibration, card_decision,
                        member_decision, no_harm_decision, program_decision, recompute, repeat_labels,
                        repeat_of_label, repeat_statistics, shared_verdict)
# typed-v3 T7 (P3a's arithmetic, wired by brief P3b): the card rule on E, the screen, the gains by item class
from .gatestats import (EVOLUTION_CARD_REASONS, EVOLUTION_CLASSES, ITEM_CLASSES, SCREEN_REASONS,  # noqa: F401
                        card_decision_evolution, class_gains, evolution_statistics, screen_counts, screen_decision)


def _regularized_beta(x, a, b):
    """Regularized incomplete beta I_x(a, b) by a convergent continued fraction (Numerical Recipes betacf)."""
    if not 0 <= x <= 1 or a <= 0 or b <= 0:
        raise ValueError('Invalid incomplete beta arguments')
    if x in (0, 1):
        return float(x)

    def fraction(left, right, value):
        tiny, epsilon = 1e-300, 3e-14
        qab, qap, qam = left + right, left + 1, left - 1
        c, d = 1.0, 1 - qab * value / qap
        if abs(d) < tiny:
            d = tiny
        d = 1 / d
        result = d
        for m in range(1, 1001):
            twice = 2 * m
            for coefficient in (m * (right - m) * value / ((qam + twice) * (left + twice)),
                                -(left + m) * (qab + m) * value / ((left + twice) * (qap + twice))):
                d = 1 + coefficient * d
                c = 1 + coefficient / c
                if abs(d) < tiny:
                    d = tiny
                if abs(c) < tiny:
                    c = tiny
                d = 1 / d
                delta = d * c
                result *= delta
            if abs(delta - 1) <= epsilon:
                return result
        raise ArithmeticError('Incomplete beta continued fraction did not converge')

    scale = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return scale * fraction(a, b, x) / a
    return 1 - scale * fraction(b, a, 1 - x) / b


_T_CACHE = {}


def student_t_quantile975(df):
    """Two-sided 95% Student-t quantile without SciPy (bisection on the regularized beta tail)."""
    if not isinstance(df, (int, float)) or not math.isfinite(df) or df <= 0:
        raise ValueError('Student-t degrees of freedom must be positive')
    if df in _T_CACHE:
        return _T_CACHE[df]

    def upper_tail(value):
        return .5 * _regularized_beta(df / (df + value * value), df / 2, .5)

    low, high = 0.0, 1.0
    while upper_tail(high) > .025:
        high *= 2
    for _ in range(100):
        middle = (low + high) / 2
        if upper_tail(middle) > .025:
            low = middle
        else:
            high = middle
    _T_CACHE[df] = (low + high) / 2
    return _T_CACHE[df]


def paired_statistics(differences, *, resamples=10000, seed=SEED):
    """Mean, Student-t and bootstrap 95% intervals, better/worse/tied counts of paired differences (unit: items)."""
    values = [float(x) for x in differences]
    n = len(values)
    result = {'n': n, 'mean': None, 'se': None, 't_interval95': None, 'bootstrap_interval95': None,
              'better': sum(x > 0 for x in values), 'worse': sum(x < 0 for x in values),
              'tied': sum(x == 0 for x in values)}
    if not n:
        return result
    mean = sum(values) / n
    result['mean'] = mean
    if n > 1:
        se = math.sqrt(sum((x - mean) ** 2 for x in values) / (n - 1) / n)
        result['se'] = se
        width = student_t_quantile975(n - 1) * se
        result['t_interval95'] = [mean - width, mean + width]
    import numpy as np
    rng = np.random.default_rng(seed)
    draws = np.mean(rng.choice(values, (resamples, n)), axis=1)
    result['bootstrap_interval95'] = [float(x) for x in np.quantile(draws, [.025, .975])]
    return result


def split_pairs(pairs):
    """(differences in {-1,0,1}, kept pair rows, excluded_unknown count)."""
    kept, excluded = [], 0
    for item_id, current, candidate in pairs:
        if current is None or candidate is None:
            excluded += 1
            continue
        kept.append((item_id, bool(current), bool(candidate)))
    return [int(c) - int(b) for _, b, c in kept], kept, excluded


def noise_threshold(pairs, *, minimum_points=TAU_MIN_POINTS, multiplier=TAU_SE_MULTIPLIER):
    """tau from two identical-request runs: max(minimum, multiplier * SE of the paired difference), in points."""
    diffs, kept, excluded = split_pairs(pairs)
    stats = paired_statistics(diffs)
    se_points = (stats['se'] or 0.0) * 100
    tau = max(minimum_points, multiplier * se_points)
    return {'rule': 'max(%.1f points, %.1f * SE)' % (minimum_points, multiplier), 'n': len(kept),
            'excluded_unknown': excluded, 'flip_rate': sum(1 for d in diffs if d) / len(diffs) if diffs else None,
            'mean_points': (stats['mean'] or 0.0) * 100, 'se_points': se_points, 'tau_points': tau,
            'statistics': stats}
