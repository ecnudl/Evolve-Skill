"""Zero-call, illustrative simulations for registration v6 (transfer to similar benchmarks). Model-based, using the
item model of ``coevo5_power_sim.py`` (logit-normal item difficulty fitted per bench to the historical mean pass rate
and run-to-run flip rate of one Skill; every text has its own per-item effect N(0, tau^2), tau = 0.3 or 1.0). Not an
estimate from data.

1. ``similar_check``: the similar-target criterion C4' (§5.5) on a target's check panel -- a backward target's
   60-item regression panel solved once per arm, a forward target's generated panel of 12 items solved twice -- for a
   rule that adds d to every item's pass probability (clipped to [0, 1]); reported is the probability of passing both
   rounds (the rule and the parent keep their texts) -- the passage of C4' on one target, not the probability of a
   similar placement, which also needs C1-C3 (and C4' on every other target). Two criteria: the registered one, "no
   worse than the parent" (the rule's per-item mean summed over the panel is at least the parent's), and, for
   comparison, the stricter criterion of the v6 draft, "at least one item more than the parent and strictly more than
   the best of four control texts at the same positions" (per-item means; new control texts in the confirmation
   round).
2. ``readout``: the noise of the transfer readouts of §12.8 on the test sets -- the equal-weight means over the cells
   of a category (self 5, targeted similar 5, rest 15) of Delta A[s][b] = A[s][b] - A[s-1][b] -- with a Skill text that
   changes at every stage; bounds by the normal approximation of the item bootstrap within a bench (paired across
   stages). Reported: the standard errors, the probability that "rest" reads as no drop (L > -delta) when nothing
   changes, and the probability of L > 0 for "self" and "similar" under given per-cell shifts, with the registered
   one-sided 95% lower bound L (z = 1.645) and, for comparison, the two-sided 95% one (z = 1.96). A shift is added to
   an item's pass probability before clipping to [0, 1] and accumulates over the stages; the realised category means
   are smaller (near-ceiling items) and are printed next to the nominal shifts.

    python docs/handoff/coevo5_transfer_sim.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location("coevo5_power_sim", Path(__file__).with_name("coevo5_power_sim.py"))
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)

ORDER = ["searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld"]
# SpreadsheetBench: an assumed number of reference-qualified test items (qualified at the first evaluation)
TEST = {"searchqa": 400, "officeqa": 170, "livemath": 125, "spreadsheetbench": 180, "alfworld": 134}
SIMILAR = {("searchqa", "officeqa"), ("officeqa", "livemath"), ("officeqa", "spreadsheetbench")}
FORWARD_TESTABLE = {"officeqa", "livemath"}  # question-answer formats with generated panels
SIMS = 3000
FIT = {b: sim.fit(*sim.BENCH[b]) for b in ORDER}


def similar(a, b):
    return (a, b) in SIMILAR or (b, a) in SIMILAR


def category(s, b):
    """The §12.8 category of the cell (stage s = 1..5, bench index b = 0..4)."""
    learned = ORDER[s - 1]
    if b == s - 1:
        return "self"
    if similar(learned, ORDER[b]) and (b < s - 1 or ORDER[b] in FORWARD_TESTABLE):
        return "similar"
    return "rest"


CELLS = {(s, b): category(s, b) for s in range(1, 6) for b in range(5)}


def similar_check(bench, d, tau, items=60, runs=1, strict=False, controls=4, seed=7):
    rng = np.random.default_rng(seed)
    mu, sigma = FIT[bench]
    theta = mu + sigma * rng.standard_normal((SIMS, items))
    parent = sim.logistic(theta + tau * rng.standard_normal((SIMS, items)))
    rule = np.clip(sim.logistic(theta + tau * rng.standard_normal((SIMS, items))) + d, 0, 1)

    def solved(p):
        return sum((rng.random((SIMS, items)) < p).sum(1) for _ in range(runs))

    passed = np.ones(SIMS, dtype=bool)
    for _ in range(2):  # screening, confirmation: new calls (and new control texts)
        y_parent, y_rule = solved(parent), solved(rule)
        if not strict:
            passed &= y_rule >= y_parent
            continue
        best = np.zeros(SIMS)
        for _ in range(controls):
            best = np.maximum(best, solved(sim.logistic(theta + tau * rng.standard_normal((SIMS, items)))))
        passed &= (y_rule - y_parent >= runs) & (y_rule > best)  # one item = ``runs`` cells
    return passed.mean()


def readout(tau, effects, seed=1):
    rng = np.random.default_rng(seed)
    params = FIT
    counts = {k: sum(1 for c in CELLS.values() if c == k) for k in ("self", "similar", "rest")}
    out = {k: [] for k in counts}
    for _ in range(SIMS):
        values, variances = dict.fromkeys(out, 0.0), dict.fromkeys(out, 0.0)
        for bi, bench in enumerate(ORDER):
            mu, sigma = params[bench]
            n = TEST[bench]
            theta = mu + sigma * rng.standard_normal(n)
            shift, y = np.zeros(n), []
            for s in range(6):
                if s:
                    shift = shift + effects.get(CELLS[(s, bi)], 0.0)
                p = np.clip(sim.logistic(theta + tau * rng.standard_normal(n)) + shift, 0, 1)
                y.append((rng.random(n) < p).astype(float))
            for key in out:
                stages = [s for s in range(1, 6) if CELLS[(s, bi)] == key]
                if stages:
                    per_item = sum(y[s] - y[s - 1] for s in stages) / counts[key]  # this bench's share of the mean
                    values[key] += per_item.mean() * 100
                    variances[key] += per_item.var(ddof=1) / n * 100 ** 2
        for key in out:
            out[key].append((values[key], variances[key] ** 0.5))  # estimate, standard error
    return counts, {k: np.array(v) for k, v in out.items()}


def lower(values, z):
    return values[:, 0] - z * values[:, 1]


def main():
    print("C4', P(pass both rounds) at tau 0.3 / 1.0, registered criterion (no worse than the parent) "
          "[v6 draft: one more and above four controls]:")
    for label, bench, items, runs in (("backward SearchQA 60x1", "searchqa", 60, 1),
                                      ("backward OfficeQA 60x1", "officeqa", 60, 1),
                                      ("forward OfficeQA-style 12x2", "officeqa", 12, 2),
                                      ("forward OfficeQA-style 8x2", "officeqa", 8, 2),
                                      ("forward LiveMath-style 12x2", "livemath", 12, 2),
                                      ("forward LiveMath-style 8x2", "livemath", 8, 2)):
        row = ["%+3dpp %.2f/%.2f [%.2f/%.2f]" % ((d * 100,) + tuple(
            similar_check(bench, d, tau, items, runs, strict) for strict in (False, True) for tau in (0.3, 1.0)))
               for d in (-0.10, -0.05, 0.0, 0.05, 0.10)]
        print("  %-27s %s" % (label, " | ".join(row)))
    for tau in (0.3, 1.0):
        counts, null = readout(tau, {})
        se = {k: round(float(v[:, 1].mean()), 2) for k, v in null.items()}
        print("readout tau %.1f, cells %s, SE (pp): %s" % (tau, counts, se))
        print("  registered one-sided 95% [two-sided 95%] lower bound L")
        for delta in (1.0, 2.0):
            print("  no change: P(L_rest > -%.0f) = %.2f [%.2f]; P(L_self > 0) = %.2f [%.2f]" % (
                delta, (lower(null["rest"], 1.645) > -delta).mean(), (lower(null["rest"], 1.96) > -delta).mean(),
                (lower(null["self"], 1.645) > 0).mean(), (lower(null["self"], 1.96) > 0).mean()))
        for gain in (0.04, 0.06):
            _, alt = readout(tau, {"self": gain, "similar": gain / 2})
            realised = tuple(alt[k][:, 0].mean() - null[k][:, 0].mean() for k in ("self", "similar"))
            print("  shift self +%dpp, similar +%dpp per cell (realised means %+.2f / %+.2f pp): P(L_self > 0) = %.2f "
                  "[%.2f], P(L_similar > 0) = %.2f [%.2f], P(L_rest > -2) = %.2f [%.2f]" % (
                      (gain * 100, gain * 50) + realised + tuple(
                      (lower(alt[key], z) > bound).mean() for key, bound in (("self", 0), ("similar", 0), ("rest", -2))
                      for z in (1.645, 1.96))))


if __name__ == "__main__":
    main()
