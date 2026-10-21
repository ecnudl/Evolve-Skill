"""Zero-call, illustrative component simulations for the coevo5 v2 gate (registration delta v2, docs/handoff/
coevo5-registration-v2-delta-20261019.md). The item model, the fitted bench parameters and the calibration target are
those of ``coevo5_power_sim.py`` (v1, unchanged); v2 changes only the run counts:

- C1: every arm of the trigger criterion (the rule, the parent, the four controls) runs ``TRIGGER_RUNS`` times per
  trigger item (v1: the focal panel's run count);
- C3: on a regression panel the parent runs ``PARENT_REGRESSION_RUNS`` = 2 times per item, a rule arm once (v1: once
  each). ``calibrate_split`` is the registered v2 tolerance rule: the smallest tolerance whose simulated two-round
  harmless rejection is at most 0.05 at tau = 1.0, with a seed fixed by the panel and the two run counts.

    python docs/handoff/coevo5_power_sim_v2.py                                   # the tables quoted in the delta
    python docs/handoff/coevo5_power_sim_v2.py calibrate BENCH ITEMS PARENT_RUNS RULE_RUNS
"""
from __future__ import annotations

import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coevo5_power_sim import (  # noqa: E402  (the v1 model, imported unchanged)
    BENCH,
    CALIBRATION_TARGET,
    CALIBRATION_TAU,
    DIAG_RUNS,
    SIMS,
    calibrate,  # the v1 focal tolerance rule (C2), unchanged in v2
    fit,
    logistic,
    trigger_power,
)

TRIGGER_RUNS = {"searchqa": 4, "officeqa": 4, "livemath": 4, "spreadsheetbench": 2, "alfworld": 2}
V1_TRIGGER_RUNS = {"searchqa": 2, "officeqa": 2, "livemath": 2, "spreadsheetbench": 1, "alfworld": 1}
PARENT_REGRESSION_RUNS, RULE_REGRESSION_RUNS = 2, 1
REGRESSION_ITEMS = 60


def harm_reject_split(rng, mu, sigma, tau, n, parent_runs, rule_runs, tolerance, harm_points, rounds=2):
    """P(a rule fails the no-harm criterion in at least one round) when the parent runs ``parent_runs`` times and the
    rule ``rule_runs`` times per item: sum of per-item rates, rule minus parent < -tolerance."""
    theta = mu + sigma * rng.standard_normal((SIMS, n))
    parent_e, rule_e = tau * rng.standard_normal((2, SIMS, n))
    rejected = np.zeros(SIMS, dtype=bool)
    for _ in range(rounds):
        parent = (rng.random((SIMS, n, parent_runs)) < logistic(theta + parent_e)[..., None]).mean(-1)
        p_rule = np.clip(logistic(theta + rule_e) - harm_points / 100, 0, 1)
        rule = (rng.random((SIMS, n, rule_runs)) < p_rule[..., None]).mean(-1)
        rejected |= (rule - parent).sum(-1) < -tolerance
    return rejected.mean()


def calibrate_split(bench, items, parent_runs, rule_runs):
    """The smallest no-harm tolerance (items) with simulated two-round harmless rejection <= 0.05 at tau = 1.0."""
    mu, sigma = fit(*BENCH[bench])
    for tolerance in range(items * max(parent_runs, rule_runs) + 1):
        rng = np.random.default_rng(zlib.crc32(("%s:%d:%d:%d" % (bench, items, parent_runs, rule_runs)).encode()))
        if harm_reject_split(rng, mu, sigma, CALIBRATION_TAU, items, parent_runs, rule_runs, tolerance, 0) \
                <= CALIBRATION_TARGET:
            return tolerance
    raise ValueError("no tolerance reaches the target")


def main():
    rng = np.random.default_rng(20261019)
    print("=== C3 tolerances (regression panel of %d items; parent x%d, rule x%d) and rejection at harm 0/5/10/20 pts"
          % (REGRESSION_ITEMS, PARENT_REGRESSION_RUNS, RULE_REGRESSION_RUNS))
    for bench in ("searchqa", "officeqa", "livemath", "spreadsheetbench"):
        mu, sigma = fit(*BENCH[bench])
        tol = calibrate_split(bench, REGRESSION_ITEMS, PARENT_REGRESSION_RUNS, RULE_REGRESSION_RUNS)
        row = [harm_reject_split(rng, mu, sigma, CALIBRATION_TAU, REGRESSION_ITEMS, PARENT_REGRESSION_RUNS,
                                 RULE_REGRESSION_RUNS, tol, h) for h in (0, 5, 10, 20)]
        old = [harm_reject_split(rng, mu, sigma, CALIBRATION_TAU, REGRESSION_ITEMS, 1, 1,
                                 {"searchqa": 5, "officeqa": 7, "livemath": 9, "spreadsheetbench": 6}[bench], h)
               for h in (0, 5, 10, 20)]
        print("  %-16s v2 tolerance %d: %s | v1 (x1/x1, v1 tolerance): %s"
              % (bench, tol, " ".join("%.2f" % x for x in row), " ".join("%.2f" % x for x in old)))
    for tau in (0.3, 1.0):
        print("=== C1 both rounds, tau = %.1f: v1 runs -> v2 runs; f = 0/.25/.5/.75/1" % tau)
        for bench in ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld"):
            mu, sigma = fit(*BENCH[bench])
            for n_t in (6, 10, 20, 35):
                rows = []
                for runs in (V1_TRIGGER_RUNS[bench], TRIGGER_RUNS[bench]):
                    rows.append([trigger_power(rng, mu, sigma, tau, n_t, runs, DIAG_RUNS[bench], f)
                                 for f in (0, .25, .5, .75, 1)])
                print("  %-16s %2d triggers  x%d: %s  ->  x%d: %s"
                      % (bench, n_t, V1_TRIGGER_RUNS[bench], " ".join("%.2f" % x for x in rows[0]),
                         TRIGGER_RUNS[bench], " ".join("%.2f" % x for x in rows[1])))


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] == "calibrate":
        print(calibrate_split(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])))
    else:
        main()
