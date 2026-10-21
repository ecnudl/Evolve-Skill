"""Zero-call, illustrative component simulations for the coevo5 gate (registration §5.6). Model-based; not an estimate
from data and not an operating characteristic of the whole gate.

Item model (logit scale): an item's pass probability under a Skill text is logistic(theta_i + e_text,i + d_i), where
theta_i ~ N(mu, sigma^2) is item difficulty, e_text,i ~ N(0, tau^2) is that text's idiosyncratic per-item effect (the
parent keeps the same e in the diagnostic execution and in every gate round; every control text and every rule text
draws its own), and d_i is a rule's true effect. mu and sigma are fitted per bench to the historical mean pass rate and
the run-to-run flip rate of one Skill (ledger 10/13-10/16); tau is unknown and reported at 0.3 and 1.0.

Reported, per bench and panel size, two separate components:
- C1 only: the probability that a rule passes the trigger criterion in both rounds, as a function of the share f of
  its trigger items whose pass probability it raises to at least 0.9. Acceptance also needs C2-C4, the placement and
  the composition, so this is not an acceptance probability;
- C2/C3 only: the probability that a no-harm criterion rejects, in at least one of two rounds, a harmless rule or a
  rule that subtracts H/100 from every item's pass probability (clipped at 0; the realised panel decline is therefore
  at most H points and smaller on hard items). C2 assumes exactly 8 trigger items, i.e. the rest panel is the focal
  panel minus 8 items.

``calibrate`` is the registered tolerance rule (§5.5): the smallest tolerance whose simulated harmless rejection over
two rounds is at most 0.05 at tau = 1.0, with a seed fixed by the panel; it gives the tolerances of panels whose size is
known only after SpreadsheetBench's reference qualification.

    python docs/handoff/coevo5_power_sim.py                          # the tables quoted in the registration
    python docs/handoff/coevo5_power_sim.py calibrate BENCH ITEMS RUNS  # a tolerance for an actual panel size
"""
from __future__ import annotations

import sys
import zlib

import numpy as np

SIMS = 4000
BENCH = {  # mean pass rate under the parent, run-to-run flip rate of one Skill (historical, GLM-5.3)
    "searchqa": (0.80, 0.10),
    "officeqa": (0.57, 0.20),
    "livemath": (0.38, 0.30),
    "spreadsheetbench": (0.45, 0.15),
    "alfworld": (0.90, 0.10),
}


def fit(mean, flip):
    """(mu, sigma) of the logit-normal item model matching the mean pass rate and the flip rate 2E[p(1-p)]."""
    z = np.random.default_rng(0).standard_normal(200000)
    best = None
    for sigma in np.arange(0.2, 6.0, 0.05):
        lo, hi = -8.0, 8.0
        for _ in range(40):
            mu = (lo + hi) / 2
            if (1 / (1 + np.exp(-(mu + sigma * z)))).mean() < mean:
                lo = mu
            else:
                hi = mu
        p = 1 / (1 + np.exp(-(mu + sigma * z)))
        err = abs(2 * (p * (1 - p)).mean() - flip)
        if best is None or err < best[0]:
            best = (err, mu, sigma)
    return best[1], best[2]


def logistic(x):
    return 1 / (1 + np.exp(-x))


def trigger_power(rng, mu, sigma, tau, n_t, runs, diag_runs, f, controls=4, rounds=2):
    """P(rule passes C1 in every round): delta(rule) >= 1 item and > the best of the controls, on n_t frozen trigger
    items that failed at least once in the diagnostic execution. A fixed item's pass probability becomes 0.9."""
    passed = np.ones(SIMS, dtype=bool)
    # failure-selected trigger items: rejection-sample items with >= 1 failed diagnostic run under the parent text
    theta = np.empty((SIMS, n_t))
    parent_e = np.empty((SIMS, n_t))
    filled = np.zeros(SIMS, dtype=int)
    while filled.min() < n_t:
        th = mu + sigma * rng.standard_normal((SIMS, n_t))
        pe = tau * rng.standard_normal((SIMS, n_t))
        fail = (rng.random((SIMS, n_t, diag_runs)) > logistic(th + pe)[..., None]).any(-1)
        for s in np.nonzero(filled < n_t)[0]:
            take = np.nonzero(fail[s])[0][: n_t - filled[s]]
            theta[s, filled[s]:filled[s] + len(take)] = th[s, take]
            parent_e[s, filled[s]:filled[s] + len(take)] = pe[s, take]
            filled[s] += len(take)
    fixed = rng.random((SIMS, n_t)) < f
    rule_e = tau * rng.standard_normal((SIMS, n_t))
    for _ in range(rounds):
        def rate(logit):
            return (rng.random((SIMS, n_t, runs)) < logistic(logit)[..., None]).mean(-1)

        parent = rate(theta + parent_e)
        rule_p = np.where(fixed, np.maximum(logistic(theta + rule_e), 0.9), logistic(theta + rule_e))
        rule = (rng.random((SIMS, n_t, runs)) < rule_p[..., None]).mean(-1)
        best = np.full(SIMS, -np.inf)
        for _ in range(controls):
            best = np.maximum(best, (rate(theta + tau * rng.standard_normal((SIMS, n_t))) - parent).sum(-1))
        gain = (rule - parent).sum(-1)
        passed &= (gain >= 1) & (gain > best)
    return passed.mean()


def harm_reject(rng, mu, sigma, tau, n, runs, tolerance, harm_points, rounds=2):
    """P(a rule fails a no-harm criterion in at least one round): delta(rule, panel) < -tolerance items, where the rule
    lowers every item's pass probability by harm_points (absolute, clipped at 0)."""
    theta = mu + sigma * rng.standard_normal((SIMS, n))
    parent_e, rule_e = tau * rng.standard_normal((2, SIMS, n))
    rejected = np.zeros(SIMS, dtype=bool)
    for _ in range(rounds):
        parent = (rng.random((SIMS, n, runs)) < logistic(theta + parent_e)[..., None]).mean(-1)
        p_rule = np.clip(logistic(theta + rule_e) - harm_points / 100, 0, 1)
        rule = (rng.random((SIMS, n, runs)) < p_rule[..., None]).mean(-1)
        rejected |= (rule - parent).sum(-1) < -tolerance
    return rejected.mean()


# registered panels: focal training panel (items x runs) for C2, regression panel (items x 1 run) for C3, and the
# no-harm tolerances in items (§5.5)
# (tolerances = calibrate(bench, items - 8, runs) for the focal panel and calibrate(bench, 60, 1) for the regression
# panel; SpreadsheetBench's sizes are nominal until its reference qualification fixes them)
FOCAL = {"searchqa": (200, 2, 7), "officeqa": (74, 2, 6), "livemath": (100, 2, 9), "spreadsheetbench": (120, 1, 9),
         "alfworld": (57, 1, 5)}
REGRESSION = {"searchqa": (60, 1, 5), "officeqa": (60, 1, 7), "livemath": (60, 1, 9), "spreadsheetbench": (60, 1, 6)}
DIAG_RUNS = {"searchqa": 2, "officeqa": 2, "livemath": 2, "spreadsheetbench": 1, "alfworld": 2}


CALIBRATION_TAU, CALIBRATION_TARGET = 1.0, 0.05


def calibrate(bench, items, runs):
    """The smallest no-harm tolerance (items) with simulated two-round harmless rejection <= 0.05 at tau = 1.0."""
    mu, sigma = fit(*BENCH[bench])
    for tolerance in range(items * runs + 1):
        rng = np.random.default_rng(zlib.crc32(("%s:%d:%d" % (bench, items, runs)).encode()))
        if harm_reject(rng, mu, sigma, CALIBRATION_TAU, items, runs, tolerance, 0) <= CALIBRATION_TARGET:
            return tolerance
    raise ValueError("no tolerance reaches the target")


def main():
    rng = np.random.default_rng(20261017)
    for tau in (0.3, 1.0):
        print("=== tau = %.1f (per-item idiosyncratic effect of a text, logit scale)" % tau)
        for bench, (mean, flip) in BENCH.items():
            mu, sigma = fit(mean, flip)
            focal_n, runs, tol = FOCAL[bench]
            print("%s: mean %.2f flip %.2f -> mu %.2f sigma %.2f" % (bench, mean, flip, mu, sigma))
            for n_t in (4, 6, 10, 20):
                row = [trigger_power(rng, mu, sigma, tau, n_t, runs, DIAG_RUNS[bench], f) for f in (0, .25, .5, .75, 1)]
                print("  C1 both rounds, %2d triggers x %d runs, f=0/.25/.5/.75/1: %s"
                      % (n_t, runs, " ".join("%.2f" % x for x in row)))
            rest = focal_n - 8
            row = [harm_reject(rng, mu, sigma, tau, rest, runs, tol, h) for h in (0, 5, 10, 20)]
            print("  C2 reject, %d rest items x %d runs, tolerance %d, harm 0/5/10/20 pts: %s"
                  % (rest, runs, tol, " ".join("%.2f" % x for x in row)))
            if bench in REGRESSION:
                n, r, t = REGRESSION[bench]
                row = [harm_reject(rng, mu, sigma, tau, n, r, t, h) for h in (0, 5, 10, 20)]
                print("  C3 reject, regression %d items x %d run, tolerance %d, harm 0/5/10/20 pts: %s"
                      % (n, r, t, " ".join("%.2f" % x for x in row)))


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "calibrate":
        print(calibrate(sys.argv[2], int(sys.argv[3]), int(sys.argv[4])))
    else:
        main()
