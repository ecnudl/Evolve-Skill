"""Statistics of the acceptance decisions, the detectors and the readouts (docs/handoff/execskill-registration-v1-
20261021.md §6.3, §6.4 after Codex F1, §6.6, §7.1, §7.2 after Codex F9, §3.3; implementation plan §1 stats_ext row,
§8.1 T-STATS-1..7; zero-call arithmetic docs/handoff/execskill-calc-20261021.py, appendix A T1-T3, T9).

- Item scores (§6.3): per item, the mean over its runs of the v2 tokens; L counts every unknown token
  (``unknown``, ``unknown_artifact``, P3's ``unknown_fault``) as wrong, H as right -- the candidate arm is read on L,
  the parent and the controls on H (frozen stats.py:1-28, whose ``bounds`` this extends by ``unknown_fault``).
  ``infrastructure_share`` counts the token ``unknown`` only: ``unknown_fault`` is never infrastructure (§4.4 P3).
- The PRIMARY test (§6.4, Codex F1) is the one-sided paired t-test on the per-item differences (null: mean <= 0):
  with blocks it is stratified (block means weighted by block size, residual variance pooled within blocks,
  df = items - blocks); on ALFWorld it runs on room means weighted by games (a weighted t-test whose units are rooms,
  blocks made of whole rooms, df = rooms - blocks). One weighted least-squares form covers all three: units u with
  values x_u and weights w_u, block means m_b, estimate m = sum(w x) / W, s^2 = sum(w (x - m_b)^2) / (U - B),
  se = s / sqrt(W). Its 5 % is a large-sample approximation; calc T9 gives its exact size under the registered skewed
  nulls (12.3 % at 30 items for Codex's null).
- Sensitivity analyses, recorded and never deciding: the sign-flip test of the same weighted sum (whole rooms flip
  together; exact when 2^units <= the flip count) and the Wilcoxon signed-rank test (zeros dropped, midranks,
  tie-corrected normal approximation, as calc T9's W).
- ``bootstrap_ci`` (the frozen percentile bootstrap, stats.py:56-74, over items or rooms within blocks), ``iut``
  (both contrasts significant; p = the larger p), ``holm`` (step-down adjusted p-values), ``spearman_perm`` (the
  validity rounds' rank correlation with a one-sided permutation p over rounds) and ``power_table`` / ``mde`` (the
  registered bivariate-normal model of the two IUT contrasts, calc T1-T2).
"""
from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from fractions import Fraction
from statistics import NormalDist

from skillopt.coevo5.stats import bootstrap, bounds
from skillopt.continual_eval.core import require

from .outcomes_ext import TOKENS, UNKNOWN_FAULT
from .protocol import ALPHA, BOOTSTRAP_RESAMPLES, MIN_WHOLE_BATCH, SEED, SIGNFLIP_FLIPS, VALIDITY_PERMUTATIONS

NORMAL = NormalDist()
SIDES = ("L", "H")


# ------------------------------------------------------------------------------------------------- item scores (§6.3)
def item_scores(cells, arm, items, *, side):
    """{item: Fraction}: the arm's per-item mean over runs on ``side`` L (unknown tokens wrong) or H (right).
    ``cells``: {(arm, item): [token per run]} with tokens from ``outcomes_ext.TOKENS``; every item must have runs."""
    require(side in SIDES, "side is L or H")
    missing = [i for i in items if not cells.get((arm, i))]
    require(not missing, "Arm %s has no cells for %d scheduled items" % (arm, len(missing)))
    for item in items:
        require(all(t in TOKENS for t in cells[(arm, item)]), "Outcome tokens are " + ", ".join(TOKENS))
    table = bounds({(arm, i): ["unknown" if t == UNKNOWN_FAULT else t for t in cells[(arm, i)]] for i in items})
    index = SIDES.index(side)
    return {i: table[(arm, i)][index] for i in items}


def infrastructure_share(cells, arm, items):
    """The arm's share of runs on these items whose token is ``unknown`` (infrastructure or unclassified); P3's
    ``unknown_fault`` and ``unknown_artifact`` are not infrastructure."""
    runs = [t for i in items for t in cells[(arm, i)]]
    return Fraction(runs.count("unknown"), len(runs)) if runs else Fraction(0)


# ------------------------------------------------------------------------------------------- the primary t-test
def paired_t(d, *, strata=None, clusters=None, weights=None):
    """The one-sided paired t-test of mean(d) > 0 (module docstring): ``{"mean", "se", "df", "t", "p"}``.

    ``d``: per-item differences; ``strata``: a block label per item (None: one block); ``clusters``: a room per item
    (None: items are the units), every room inside one block; ``weights``: a positive weight per item (None: 1), so a
    room's weight is its number of games. With no residual variance the test is decided by the sign of the mean
    (p 0 or 1, t None)."""
    units = _units(d, strata, clusters, weights)
    blocks = {}
    for value, weight, block in units:
        blocks.setdefault(block, []).append((value, weight))
    df = len(units) - len(blocks)
    require(df >= 1, "The t-test needs more units than blocks")
    total = sum(w for _, w, _ in units)
    mean = sum(w * x for x, w, _ in units) / total
    residual = 0
    for members in blocks.values():
        block_mean = sum(w * x for x, w in members) / sum(w for _, w in members)
        residual += sum(w * (x - block_mean) ** 2 for x, w in members)
    se = math.sqrt(residual / df / total)
    if se == 0:
        return {"mean": float(mean), "se": 0.0, "df": df, "t": None, "p": 0.0 if mean > 0 else 1.0}
    t = float(mean) / se
    return {"mean": float(mean), "se": se, "df": df, "t": t, "p": t_upper(t, df)}


def t_upper(t, df):
    """P(T_df >= t) for Student's t (calc T9's ``t_upper``)."""
    require(df > 0, "Degrees of freedom must be positive")
    tail = 0.5 * _ibeta(df / 2, 0.5, df / (df + t * t))
    return tail if t >= 0 else 1 - tail


def _units(d, strata, clusters, weights):
    """[(value, weight, block)] of the test's units: items, or rooms (games-weighted means of their items)."""
    d = list(d)
    require(d and all(isinstance(x, (int, float, Fraction)) and not isinstance(x, bool) and -1 <= x <= 1 for x in d),
            "Differences are numbers in [-1, 1]")
    n = len(d)
    strata = [None] * n if strata is None else list(strata)
    weights = [1] * n if weights is None else list(weights)
    require(len(strata) == n and len(weights) == n, "One block and one weight per item")
    require(all(isinstance(w, (int, float, Fraction)) and not isinstance(w, bool) and w > 0 for w in weights),
            "Weights are positive numbers")
    if clusters is None:
        return list(zip(d, weights, strata))
    clusters = list(clusters)
    require(len(clusters) == n, "One room per item")
    rooms = {}
    for x, w, b, room in zip(d, weights, strata, clusters):
        rooms.setdefault(room, []).append((x, w, b))
    units = []
    for room in sorted(rooms, key=repr):
        members = rooms[room]
        require(len({b for _, _, b in members}) == 1, "A block is made of whole rooms")
        weight = sum(w for _, w, _ in members)
        units.append((sum(w * x for x, w, _ in members) / weight, weight, members[0][2]))
    return units


# --------------------------------------------------------------------------------------- sensitivity analyses
def signflip(d, *, strata=None, clusters=None, weights=None, n=SIGNFLIP_FLIPS, seed=SEED):
    """One-sided sign-flip p of the weighted sum of the units' values (rooms flip whole); exact over all 2^units sign
    patterns when that is at most ``n``, else ``n`` seeded random patterns, p = (1 + exceedances) / (n + 1).
    Sensitivity only (§6.4): it never decides. ``strata`` only checks that blocks hold whole rooms."""
    require(type(n) is int and n > 0, "Invalid flip count")
    units = _units(d, strata, clusters, weights)
    magnitudes = [abs(w * x) for x, w, _ in units]
    observed = sum(w * x for x, w, _ in units)
    if 2 ** len(magnitudes) <= n:
        patterns = list(itertools.product((1, -1), repeat=len(magnitudes)))
        hits = sum(sum(s * a for s, a in zip(signs, magnitudes)) >= observed for signs in patterns)
        return hits / len(patterns)
    rng, total, hits = random.Random(seed), sum(magnitudes), 0
    for _ in range(n):
        bits = rng.getrandbits(len(magnitudes))
        positive = sum(a for j, a in enumerate(magnitudes) if bits >> j & 1)
        hits += 2 * positive - total >= observed
    return (1 + hits) / (n + 1)


def wilcoxon(d):
    """One-sided Wilcoxon signed-rank p (greater): zeros dropped, midranks, tie-corrected normal approximation
    without continuity correction (calc T9's W). Sensitivity only (§6.4): it tests symmetry, not the mean."""
    values = [x for x in d if x != 0]
    if not values:
        return 1.0
    ordered = sorted(values, key=abs)
    count, rank, positive, ties, index = len(ordered), 0, 0.0, 0, 0
    while index < count:
        same = index
        while same < count and abs(ordered[same]) == abs(ordered[index]):
            same += 1
        size = same - index
        midrank = rank + (size + 1) / 2
        positive += midrank * sum(x > 0 for x in ordered[index:same])
        ties += size ** 3 - size
        rank, index = rank + size, same
    variance = count * (count + 1) * (2 * count + 1) / 24 - ties / 48
    if variance <= 0:
        return 1.0
    return 1 - NORMAL.cdf((positive - count * (count + 1) / 4) / math.sqrt(variance))


def bootstrap_ci(d, *, strata=None, clusters=None, weights=None, resamples=BOOTSTRAP_RESAMPLES, seed=SEED,
                 level=0.95):
    """Percentile interval of the weighted mean, resampling units (items or whole rooms) within blocks with the frozen
    ``stats.bootstrap`` (stats.py:56-74)."""
    groups = {}
    for value, weight, block in _units(d, strata, clusters, weights):
        groups.setdefault(repr(block), []).append((value, weight))

    def statistic(draw):
        units = [u for members in draw.values() for u in members]
        return sum(w * x for x, w in units) / sum(w for _, w in units)

    return bootstrap(groups, statistic, resamples=resamples, seed=seed, level=level)


# ----------------------------------------------------------------------------------------- decisions and families
@dataclass(frozen=True)
class Decision:
    """The intersection-union test of two one-sided contrasts: ``reject`` when both p <= alpha; ``p`` = the larger p;
    ``contrasts`` = the two ``paired_t`` results."""

    reject: bool
    p: float
    alpha: float
    contrasts: tuple


def iut(d1, d2, *, alpha=ALPHA, design1=None, design2=None):
    """J1/J2's statistical part (§6.4): ``paired_t`` on both differences (``design1``/``design2``: its keyword
    arguments ``strata``, ``clusters``, ``weights``). No multiplicity correction: the IUT's size is the larger of the
    two. J1's whole-batch floor and the guards J3-J7 are the acceptance's (acceptance.py)."""
    require(0 < alpha < 1, "Invalid level")
    first, second = paired_t(d1, **(design1 or {})), paired_t(d2, **(design2 or {}))
    p = max(first["p"], second["p"])
    return Decision(reject=p <= alpha, p=p, alpha=alpha, contrasts=(first, second))


def holm(pvals):
    """Holm's step-down adjusted p-values, in the input order."""
    pvals = list(pvals)
    require(all(isinstance(p, (int, float)) and 0 <= p <= 1 for p in pvals), "p-values are in [0, 1]")
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    adjusted, running = [0.0] * len(pvals), 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(pvals) - rank) * pvals[index]))
        adjusted[index] = running
    return adjusted


def spearman_perm(xs, ys, *, n=VALIDITY_PERMUTATIONS, seed=SEED):
    """``(rho, p)``: Spearman's rank correlation (midranks) of paired per-round values and its one-sided permutation p
    (rho > 0) over rounds -- the ys are permuted against the xs, exactly over all orders when there are at most ``n``,
    else ``n`` seeded permutations with p = (1 + exceedances) / (n + 1). A constant side: (None, 1.0)."""
    xs, ys = list(xs), list(ys)
    require(len(xs) == len(ys) >= 2, "Two or more rounds of paired values")
    require(type(n) is int and n > 0, "Invalid permutation count")
    rx, ry = _ranks(xs), _ranks(ys)
    if len(set(rx)) == 1 or len(set(ry)) == 1:
        return None, 1.0
    rho = _pearson(rx, ry)
    if math.factorial(len(ry)) <= n:
        orders = list(itertools.permutations(ry))
        return rho, sum(_pearson(rx, o) >= rho - 1e-12 for o in orders) / len(orders)
    rng, hits, shuffled = random.Random(seed), 0, list(ry)
    for _ in range(n):
        rng.shuffle(shuffled)
        hits += _pearson(rx, shuffled) >= rho - 1e-12
    return rho, (1 + hits) / (n + 1)


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks, index = [0.0] * len(values), 0
    while index < len(order):
        same = index
        while same < len(order) and values[order[same]] == values[order[index]]:
            same += 1
        for k in order[index:same]:
            ranks[k] = (index + same + 1) / 2
        index = same
    return ranks


def _pearson(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


# ------------------------------------------------------------------------------------- power (§6.6, calc T1-T2)
def power_table(se, *, effects=(3, 5, 10), rho=0.5, placebo=0.0, cover=1.0, deff=1.0, deff_y=1.0, alpha=ALPHA):
    """{effect: {"single", "joint"}}: the chance that J1 alone ("single", reference only) and J1 and J2 together
    ("joint", the registered decision) pass at a true whole-batch effect (points), from the registered bivariate-normal
    model of the two contrasts (calc ``single``/``joint``): ``se`` = one contrast's whole-batch SE in points;
    ``rho`` their correlation; ``placebo`` the effect of P_y over S; ``cover`` = |A*| / |A|; ``deff`` the room design
    effect; ``deff_y`` the donor-reuse design effect on P_y. J1 includes the 2-point whole-batch floor."""
    return {e: {"single": _single(e, se, cover=cover, deff=deff, alpha=alpha),
                "joint": _joint(e, se, rho=rho, placebo=placebo, cover=cover, deff=deff, deff_y=deff_y, alpha=alpha)}
            for e in effects}


def mde(se, *, power=0.80, **model):
    """The smallest true whole-batch effect (points) whose joint acceptance chance reaches ``power`` (calc ``mde``)."""
    lo, hi = 0.0, 60.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _joint(mid, se, **model) < power else (lo, mid)
    return (lo + hi) / 2


def _floor_points():
    return float(MIN_WHOLE_BATCH) * 100


def _single(delta, se, *, cover=1.0, deff=1.0, alpha=ALPHA):
    s1 = se * math.sqrt(cover * deff)
    return 1 - NORMAL.cdf(max(NORMAL.inv_cdf(1 - alpha), _floor_points() / s1) - delta / s1)


def _joint(delta, se, *, rho=0.5, placebo=0.0, cover=1.0, deff=1.0, deff_y=1.0, alpha=ALPHA):
    z = NORMAL.inv_cdf(1 - alpha)
    s1 = se * math.sqrt(cover * deff)
    s2 = s1 * math.sqrt((1 + deff_y) / 2)
    r = rho * math.sqrt(2 / (1 + deff_y))
    return _orthant(max(z, _floor_points() / s1) - delta / s1, z - (delta - placebo) / s2, r)


def _orthant(a, b, rho, n=4000):
    """P(Z1 > a, Z2 > b) for a standard bivariate normal with correlation rho (Simpson's rule, calc ``orthant``)."""
    lo, hi = max(a, -9.0), 9.0
    if lo >= hi:
        return 0.0
    s, h = math.sqrt(1 - rho * rho), (hi - lo) / n

    def f(z):
        return NORMAL.pdf(z) * (1 - NORMAL.cdf((b - rho * z) / s))

    return (f(lo) + f(hi) + sum((4 if i % 2 else 2) * f(lo + i * h) for i in range(1, n))) * h / 3


# ------------------------------------------------------------------------- the incomplete beta (calc T9's ibeta)
def _betacf(a, b, x):
    qab, qap, qam, c, d = a + b, a + 1, a - 1, 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-300 else 1e-300
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    return h


def _ibeta(a, b, x):
    """The regularized incomplete beta function I_x(a, b) (continued fraction; calc T9)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b
