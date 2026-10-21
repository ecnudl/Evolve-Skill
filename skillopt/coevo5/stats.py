"""Exact per-item statistics for the gate (registration §5.4-§5.5) and the readings (§12).

A cell is one (arm, item, run) outcome token: "pass", "fail", "unknown" (infrastructure or unclassified) or
"unknown_artifact" (a delivered SpreadsheetBench workbook the scorer could not judge); see ``outcomes``. Every gate
criterion uses conservative item rates: L counts an arm's unknown runs as fail, H counts them as pass; a rule is judged
on L, the parent and the controls on H. Fractions keep comparisons exact.
"""
from __future__ import annotations

import math
import random
from fractions import Fraction

from skillopt.continual_eval.core import require

OUTCOMES = ("pass", "fail", "unknown", "unknown_artifact")


def bounds(cells):
    """{(arm, item): [token, ...]} -> {(arm, item): (L, H, unknown runs, runs, infrastructure-unknown runs)}."""
    out = {}
    for key, outcomes in cells.items():
        require(outcomes and all(o in OUTCOMES for o in outcomes), "Outcome tokens are " + ", ".join(OUTCOMES))
        passed, infrastructure = outcomes.count("pass"), outcomes.count("unknown")
        unknown = infrastructure + outcomes.count("unknown_artifact")
        out[key] = (Fraction(passed, len(outcomes)), Fraction(passed + unknown, len(outcomes)), unknown, len(outcomes),
                    infrastructure)
    return out


def total(table, arm, items, side):
    """Σ over items of the arm's L (side "L") or H (side "H"), in items. Every item must have been scheduled."""
    require(side in ("L", "H"), "side is L or H")
    index = 0 if side == "L" else 1
    missing = [i for i in items if (arm, i) not in table]
    require(not missing, "Arm %s has no cells for %d scheduled items" % (arm, len(missing)))
    return sum((table[(arm, i)][index] for i in items), Fraction(0))


def unknown_share(table, arm, items, infrastructure_only=False):
    """Share of the arm's scheduled runs on these items whose outcome is unknown (of any kind, or infrastructure only)."""
    unknown = sum(table[(arm, i)][4 if infrastructure_only else 2] for i in items)
    runs = sum(table[(arm, i)][3] for i in items)
    return Fraction(unknown, runs) if runs else Fraction(0)


def sign_test(wins, losses):
    """Exact two-sided sign test on the untied pairs."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(wins, losses) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def bootstrap(strata, statistic, *, resamples=10000, seed=20261017, level=0.95):
    """Percentile interval of ``statistic`` under resampling units with replacement within each stratum.

    ``strata``: {stratum: [unit, ...]}; ``statistic({stratum: [unit, ...]})`` -> float (None skips the resample).
    The same resampled units feed every arm and stage inside ``statistic``, so comparisons stay paired."""
    require(strata and all(units for units in strata.values()), "Every stratum needs units")
    rng = random.Random(seed)
    values = []
    names = sorted(strata)
    for _ in range(resamples):
        draw = {name: [rng.choice(strata[name]) for _ in strata[name]] for name in names}
        value = statistic(draw)
        if value is not None:
            values.append(float(value))
    require(values, "No resample produced a value")
    values.sort()
    lo = values[int(math.floor((1 - level) / 2 * len(values)))]
    hi = values[min(len(values) - 1, int(math.ceil((1 + level) / 2 * len(values))) - 1)]
    return lo, hi
