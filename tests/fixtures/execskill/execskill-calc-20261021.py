#!/usr/bin/env python3
"""Zero-call arithmetic for the fivebench-execskill-v1 registration (RD v1, revised after the one Codex review round,
2026-10-21).

Deterministic, standard library only, reads no file, makes no network or model call.
Run:  python3 -I docs/handoff/execskill-calc-20261021.py > docs/handoff/execskill-calc-output-20261021.txt

Every number printed here is an ESTIMATE built from the registered anchors below; the anchors themselves are
measured where marked [M] and assumed where marked [A]. Tables:
  T1 MDE from ONE bivariate-normal model of the two IUT contrasts (RD 3.3)   T2 joint power (RD 6.6)
  T3 sensitivity of acceptance at +5 and P(no acceptance) (RD 0 item 4, 6.6)
  T4 pilot learning steps: estimate and registered MAXIMUM schedule (RD 9.2)   T5 final test read (RD 8.1, 9.2)
  T6 caps from the maximum schedule + one full next reservation (RD 9.3)   T7 smoke (RD 10)
  T8 probe reservations, slot waits, ALFWorld pre-reset, memory (RD 4.1, 10; IP 4, 5)
  T9 size of the paired t-test (decides) and of sign-flip / Wilcoxon (sensitivity) under bounded skewed nulls, and the
     chain-wide chance of >= 1 false acceptance over 5-9 decisions (RD 6.4)
  T10 J3/J4 boundary examples (RD 6.4)
  T11 two formal chains G (GLM-5.3 solver) and D (elucid solver), owner rule 2026-10-21 22:3x: per-chain caps apply to
      EACH chain, pilot totals doubled; examiner research sub-scope (RD 4.3, 7.2, 9.3, 11, 21)
T4 also prints the registered OQ duplicate arm S_dup (RD 3.3, 7.2, 14 #22) and the owner-#9 option of P_i on ALFWorld;
T6 prints the caps that option would need under the maximum-schedule rule (RD 9.3, 14 #9).
"""
from math import ceil, comb, exp, lgamma, log, sqrt
from statistics import NormalDist

ND = NormalDist()
PHI, PDF = ND.cdf, ND.pdf
Z95 = ND.inv_cdf(0.95)          # one-sided 5 %
Z80 = ND.inv_cdf(0.80)          # 80 % power
K = Z95 + Z80                   # 2.487
FLOOR = 2.0                     # J1: whole-batch mean difference >= 0.02 (2 points)
M = 1e6


def up(x, step=0.1):
    """Round x (in millions) UP to the next multiple of step."""
    return ceil(round(x / step, 6)) * step


# ---------------------------------------------------------------- one bivariate-normal model (F3)
def orthant(a, b, rho, n=4000):
    """P(Z1 > a, Z2 > b) for a standard bivariate normal with correlation rho (Simpson's rule, deterministic)."""
    lo, hi = max(a, -9.0), 9.0
    if lo >= hi:
        return 0.0
    s, h = sqrt(1 - rho * rho), (hi - lo) / n
    f = lambda z: PDF(z) * (1 - PHI((b - rho * z) / s))
    return (f(lo) + f(hi) + sum((4 if i % 2 else 2) * f(lo + i * h) for i in range(1, n))) * h / 3


def joint(delta, se, *, rho=0.5, pi=0.0, cover=1.0, deff=1.0, deff_y=1.0):
    """P(J1 and J2) for a true whole-batch effect delta (points) of S' over S.
    se: whole-batch SE of one contrast when A* = A; cover = |A*|/|A| (the effect lives on A*, non-firing items are
    noise with the same per-item SD, so the whole-batch-equivalent SE is se*sqrt(cover)); deff: room design effect
    (both contrasts); deff_y: donor-reuse design effect on the P_y arm only; pi: placebo effect P_y - S (points);
    rho: correlation of the two contrast estimates when deff_y = 1 (0.5 = equal-variance independent arms).
    J1 = one-sided 5 % AND whole-batch mean >= FLOOR; J2 = one-sided 5 %."""
    s1 = se * sqrt(cover * deff)
    s2 = s1 * sqrt((1 + deff_y) / 2)
    r = rho * sqrt(2 / (1 + deff_y))
    return orthant(max(Z95, FLOOR / s1) - delta / s1, Z95 - (delta - pi) / s2, r)


def single(delta, se, *, cover=1.0, deff=1.0):
    s1 = se * sqrt(cover * deff)
    return 1 - PHI(max(Z95, FLOOR / s1) - delta / s1)


def mde(se, power=0.80, **kw):
    lo, hi = 0.0, 60.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if joint(mid, se, **kw) < power else (lo, mid)
    return (lo + hi) / 2


# single-contrast MDE anchors (points, whole batch, A* = A): D1 measured lower bounds [FP F40] scaled by sqrt(n_D1/n);
# ALFWorld / LiveMath from DP 5 joint values divided by the critic's 1.135 (used ONLY to recover a single-contrast anchor)
ANCHOR = {
    "spreadsheetbench 60x2": 0.122 * sqrt(46 / 60) * 100,      # D1: 0.122 at 46x2  [M]
    "officeqa 50x4": 0.103 * sqrt(37 / 50) * 100,              # D1: 0.103 at 37x4  [M]
    "searchqa 1000x1": 3.0,                                    # D1-derived [FP F40]
    "alfworld 150x1": 8.4 / 1.135 * sqrt(200 / 150),           # DP 5: joint 8.4 at 200 games [A]
    "alfworld 200x1": 8.4 / 1.135,
    "livemath 100x2 low": 9.0 / 1.135,                         # DP 5: joint 9-10 [A]
    "livemath 100x2 high": 10.0 / 1.135,
}
SE = {k: v / K for k, v in ANCHOR.items()}
SB, OQ, ALF = SE["spreadsheetbench 60x2"], SE["officeqa 50x4"], SE["alfworld 150x1"]
ROOMS_ACCEPT, CAP_PER_ROOM = 40, 5
M_BAR = 150 / ROOMS_ACCEPT
DEFF_ALF = 1 + (M_BAR - 1) * 0.10        # rho_d = 0.10 [A]

print("T1  MDE from ONE bivariate-normal model of the IUT contrasts S'-S and S'-P_y (one-sided 5 % each, 80 % joint power;")
print("    J1 also needs a whole-batch mean >= 2 points; A* = A; placebo effect 0). Points, whole-batch convention.")
RATIO = {0.3: [], 0.5: [], 0.7: []}
for name, se in SE.items():
    j = [mde(se, rho=r) for r in (0.3, 0.5, 0.7)]
    for r, x in zip((0.3, 0.5, 0.7), j):
        RATIO[r].append(x / ANCHOR[name])
    print(f"  {name:24s} single {ANCHOR[name]:5.1f} | joint rho 0.3/0.5/0.7 {j[0]:5.1f} /{j[1]:5.1f} /{j[2]:5.1f}"
          f" | joint/single at 0.5 {j[1] / ANCHOR[name]:.3f}")
print(f"  joint/single MDE ratio over the rows above: rho 0.5 {min(RATIO[0.5]):.3f}-{max(RATIO[0.5]):.3f};"
      f" rho 0.3 {min(RATIO[0.3]):.3f}-{max(RATIO[0.3]):.3f}; rho 0.7 {min(RATIO[0.7]):.3f}-{max(RATIO[0.7]):.3f}")
for rho_d in (0.0, 0.05, 0.10):
    deff = 1 + (M_BAR - 1) * rho_d
    print(f"  alfworld 150x1 room DEFF (40 rooms, m={M_BAR:.2f}, rho_d={rho_d:.2f}) = {deff:.3f} -> joint MDE"
          f" {mde(ALF, deff=deff):5.1f}")
print(f"  capacity check: 40 rooms x {CAP_PER_ROOM} = {ROOMS_ACCEPT * CAP_PER_ROOM} >= 150 acceptance games;"
      f" decision minimum |A*| >= 30 items (ALFWorld >= 20 rooms)")
print("  with A* coverage 0.6 (whole-batch SE x sqrt(0.6)): joint MDE SB"
      f" {mde(SB, cover=0.6):4.1f}, OQ {mde(OQ, cover=0.6):4.1f}, ALF {mde(ALF, cover=0.6):4.1f}")

# ---------------------------------------------------------------- T2 power
print("\nT2  Power at a true whole-batch effect of +3/+5/+10 points from the same model (rho 0.5, A* = A, placebo 0).")
print("    'single' = J1 alone (reference only); 'joint' = J1 and J2, the registered decision.")
rows = [("spreadsheetbench 60x2", SB, 1.0), ("officeqa 50x4", OQ, 1.0), ("alfworld 150x1", ALF, 1.0),
        ("alfworld 150x1 DEFF 1.275", ALF, DEFF_ALF), ("livemath 100x2 low", SE["livemath 100x2 low"], 1.0),
        ("livemath 100x2 high", SE["livemath 100x2 high"], 1.0), ("searchqa 1000x1", SE["searchqa 1000x1"], 1.0)]
for name, se, deff in rows:
    s = [single(d, se, deff=deff) for d in (3, 5, 10)]
    j = [joint(d, se, deff=deff) for d in (3, 5, 10)]
    print(f"  {name:26s} single +3 {s[0]:.2f} +5 {s[1]:.2f} +10 {s[2]:.2f} | joint +3 {j[0]:.2f} +5 {j[1]:.2f} +10 {j[2]:.2f}")
print(f"  design-v0 minimum effects (owner #30), joint: SB +7 -> {joint(7, SB):.2f};"
      f" LM +5 -> {joint(5, SE['livemath 100x2 high']):.2f}-{joint(5, SE['livemath 100x2 low']):.2f}")

# ---------------------------------------------------------------- T3 sensitivity
print("\nT3  Acceptance probability of a true +5 (J1 and J2) and P(the two-step pilot accepts nothing), same model.")
print("    Steps independent; 'guards' = an assumed 10 % chance that J3-J7 block an otherwise accepted step [A].")
YOKE_ALF = 1 + (150 / 60 - 1) * 0.10     # 60 run-slice donors for <= 150 acceptance games, rho_y = 0.10 [A]
grid = []
for rho in (0.3, 0.5, 0.7):
    for cover in (0.6, 1.0):
        for pi in (-2.0, 0.0, 2.0):
            for g in (1.0, 0.9):
                a_sb = g * joint(5, SB, rho=rho, cover=cover, pi=pi)
                a_oq = g * joint(5, OQ, rho=rho, cover=cover, pi=pi)
                a_alf = [g * joint(5, ALF, rho=rho, cover=cover, pi=pi, deff=d, deff_y=y)
                         for d in (1.0, DEFF_ALF) for y in (1.0, YOKE_ALF)]
                grid.append((rho, cover, pi, g, a_sb, a_oq, a_alf))
base = [x for x in grid if x[:4] == (0.5, 1.0, 0.0, 1.0)][0]
print(f"  primary (rho 0.5, A* = A, placebo 0, no guard loss): SB {base[4]:.3f}  OQ {base[5]:.3f}  ALF {base[6][0]:.3f}"
      f" | P(nothing) default SB->OQ {(1 - base[4]) * (1 - base[5]):.3f}  recommended SB->ALF {(1 - base[4]) * (1 - base[6][0]):.3f}")
for label, sel in (("rho 0.3", (0.3, 1.0, 0.0, 1.0)), ("rho 0.7", (0.7, 1.0, 0.0, 1.0)),
                   ("A* coverage 0.6", (0.5, 0.6, 0.0, 1.0)), ("placebo -2", (0.5, 1.0, -2.0, 1.0)),
                   ("placebo +2", (0.5, 1.0, 2.0, 1.0)), ("guards x0.9", (0.5, 1.0, 0.0, 0.9))):
    x = [y for y in grid if y[:4] == sel][0]
    print(f"  {label:16s} SB {x[4]:.3f}  OQ {x[5]:.3f}  ALF {x[6][0]:.3f} | P(nothing) default {(1 - x[4]) * (1 - x[5]):.3f}"
          f"  recommended {(1 - x[4]) * (1 - x[6][0]):.3f}")
print(f"  ALFWorld room DEFF 1.275: {base[6][2]:.3f}; donor reuse DEFF_y {YOKE_ALF:.2f} on P_y: {base[6][1]:.3f}; both {base[6][3]:.3f}")
lo_sb, hi_sb = min(x[4] for x in grid), max(x[4] for x in grid)
lo_oq, hi_oq = min(x[5] for x in grid), max(x[5] for x in grid)
lo_alf, hi_alf = min(min(x[6]) for x in grid), max(max(x[6]) for x in grid)
pn_def = [(1 - x[4]) * (1 - x[5]) for x in grid]
pn_rec = [(1 - x[4]) * (1 - a) for x in grid for a in x[6]]
print(f"  range over the grid (rho 0.3/0.5/0.7 x coverage 0.6/1.0 x placebo -2/0/+2 x guards 1/0.9; ALF also DEFF, DEFF_y):")
print(f"    acceptance of +5: SB {lo_sb:.2f}-{hi_sb:.2f}  OQ {lo_oq:.2f}-{hi_oq:.2f}  ALF {lo_alf:.2f}-{hi_alf:.2f}")
print(f"    P(nothing): default SB->OQ {min(pn_def):.2f}-{max(pn_def):.2f}  recommended SB->ALF {min(pn_rec):.2f}-{max(pn_rec):.2f}")

# ---------------------------------------------------------------- anchors for cost
CELL = {"searchqa": (1535, 3400), "officeqa": (5246, 7927), "livemath": (1602, 3969),
        "spreadsheetbench": (2561, 4273), "alfworld": (36000, 45000)}
# per-cell solver tokens (prompt + reply), card-only arm [RD 9.1]; ALFWorld per EPISODE. low: E-ds cell - 141 scaffold
# tokens + current card at 4.2 B/token [M: FP F32]; high: I-ds / cal-1 ledger per cell [M: FP F61] except ALFWorld high
# = ESTIMATE (single card, ~37 steps x ~1.2k tokens; the measured I-ds episode was 105.7k tokens with the five-card
# render [FP F17], which route B does not use).
PO = (1.25, 1.60)          # procedure arms (S', P_y, P_i, twins) vs card arm [A; D3 state block 1,225 vs 873 FP F2]

# registered schedules (F18). 'estimate': expected workload. 'max': the registered maximum (caps derive from it):
# <= 3 changed procedures per step, <= 2 withholding twins per A* item (changed procedures first, then inherited ones by
# enable count), A* = 100 %, difficulty band = 1 initial + 2 adjustments = 3 probe rounds, self-test = 2 passes (the
# engineer's one revision after a self-test block), G_acc arms S', S, P_y, C (+ S_dup where registered).
SCHED = {
    "estimate": {"astar": {"alfworld": (0.7, 1.0), "*": (0.6, 1.0)}, "twins": {"alfworld": (0.5, 0.5), "*": (0.75, 0.75)},
                 "band": (1, 3), "self_passes": (1, 1)},
    "max": {"astar": {"*": (1.0, 1.0)}, "twins": {"*": (2.0, 2.0)}, "band": (3, 3), "self_passes": (2, 2)},
}


def pick(table, bench):
    return table.get(bench, table["*"])


def step_cost(bench, n_run, k_run, n_acc, k_acc, first, prev_sets, p_i, gen_items, dup, sched):
    """{scope: [low, high]} solver tokens of one pilot learning step under schedule `sched`."""
    sc, out = SCHED[sched], {}
    for i in (0, 1):
        c, po = CELL[bench][i], PO[i]
        par = 1.0 if first else po                 # parent S carries procedures after step 1
        astar, twins_per = pick(sc["astar"], bench)[i], pick(sc["twins"], bench)[i]
        arms_run = 1 if first else 2               # S (+ entry-reading C after step 1)
        run = n_run * k_run * c * arms_run * (1.0 if i == 0 else 1.6)
        cells = n_acc * k_acc * astar
        arms = po + par + po + 1.0 + (po if p_i else 0.0) + (par if dup else 0.0)   # S', S, P_y, C (+P_i) (+S_dup)
        acc_no_twins = cells * c * arms
        twins = cells * c * twins_per * po
        band = 30 * c * par * sc["band"][i]
        shortcut = 0 if bench == "alfworld" else 30 * 2 * c
        g_arms = po + par + po + 1.0 + (par if dup else 0.0)
        g_acc = 0 if gen_items == 0 else min(gen_items, n_acc) * astar * c * g_arms
        n_self = 40 if bench == "alfworld" else 60
        selftest = n_self * c * (po + par) + sum(40 * CELL[pb][i] * (po + po) for pb in prev_sets)
        selftest *= sc["self_passes"][i]
        for k, v in (("run", run), ("accept_no_twins", acc_no_twins), ("twins", twins), ("band", band),
                     ("shortcut", shortcut), ("g_acc", g_acc), ("selftest", selftest)):
            out.setdefault(k, [0, 0])[i] = v
    out["accept"] = [out["accept_no_twins"][j] + out["twins"][j] for j in (0, 1)]
    out["examiner"] = [out["band"][j] + out["shortcut"][j] + out["g_acc"][j] for j in (0, 1)]
    out["total"] = [out["run"][j] + out["accept"][j] + out["examiner"][j] + out["selftest"][j] for j in (0, 1)]
    return out


STEP_ARGS = {
    "SB step 1": ("spreadsheetbench", 31, 2, 60, 2, True, (), True, 60, False),
    "OQ step 2": ("officeqa", 24, 2, 50, 4, False, ("spreadsheetbench",), True, 50, True),
    "ALF step 2": ("alfworld", 60, 1, 150, 1, False, ("spreadsheetbench",), False, 0, False),
}
STEPS = {s: {n: step_cost(*a, s) for n, a in STEP_ARGS.items()} for s in SCHED}
print("\nT4  Pilot learning steps, solver tokens (M). 'estimate' = expected workload, low-high (A* 60-100 %, ALF 70-100 %;")
print("    twins 0.75 per A* cell SB/OQ, 0.5 ALF; band 1-3 probe rounds; 1 self-test pass). 'max' = registered maximum")
print("    schedule (A* 100 %, 2 twins per A* cell, 3 band rounds, 2 self-test passes), high anchors. P_i on SB/OQ/LM;")
print("    G_acc = 1 item per A* item, arms S', S, P_y, C; OQ adds the registered duplicate arm S_dup (A* and G_acc).")
for sched in SCHED:
    for name, s in STEPS[sched].items():
        if sched == "estimate":
            f = lambda k: f"{s[k][0] / M:5.2f}-{s[k][1] / M:5.2f}"
        else:
            f = lambda k: f"{s[k][1] / M:11.2f}"
        print(f"  {sched:8s} {name:10s} run {f('run')} | accept {f('accept')} (twins {f('twins')}) | examiner {f('examiner')}"
              f" (band {f('band')}, G_acc {f('g_acc')}) | selftest {f('selftest')} | step {f('total')}")
learn = {"default SB->OQ": ("SB step 1", "OQ step 2"), "recommended SB->ALF": ("SB step 1", "ALF step 2")}
for name, ss in learn.items():
    lo = sum(STEPS["estimate"][s]["total"][0] for s in ss) / M
    hi = sum(STEPS["estimate"][s]["total"][1] for s in ss) / M
    mx = sum(STEPS["max"][s]["total"][1] for s in ss) / M
    print(f"  learning side {name:20s} estimate {lo:5.1f}-{hi:5.1f} M | maximum schedule {mx:5.1f} M")
OQ_ARGS, ALF_ARGS = STEP_ARGS["OQ step 2"], STEP_ARGS["ALF step 2"]
NODUP = {s: step_cost(*OQ_ARGS[:9], False, s) for s in SCHED}            # OQ step 2 without S_dup
ALF_PI = {s: step_cost(*ALF_ARGS[:7], True, *ALF_ARGS[8:], s) for s in SCHED}   # ALF step 2 with P_i (owner #9)
dup_e = [(STEPS["estimate"]["OQ step 2"]["total"][i] - NODUP["estimate"]["total"][i]) / M for i in (0, 1)]
dup_m = (STEPS["max"]["OQ step 2"]["total"][1] - NODUP["max"]["total"][1]) / M
pi_e = [(ALF_PI["estimate"]["accept"][i] - STEPS["estimate"]["ALF step 2"]["accept"][i]) / M for i in (0, 1)]
pi_m = (ALF_PI["max"]["accept"][1] - STEPS["max"]["ALF step 2"]["accept"][1]) / M
print(f"  included above: OQ duplicate arm S_dup (registered; A* and G_acc; RD 3.3, 7.2, 14 #22): estimate"
      f" {dup_e[0]:.2f}-{dup_e[1]:.2f} | max {dup_m:.2f}")
print(f"  NOT included (owner #9 option): P_i on ALFWorld acceptance would add estimate {pi_e[0]:.2f}-{pi_e[1]:.2f}"
      f" | max {pi_m:.2f}")

# ---------------------------------------------------------------- T5 test read
TEST = {"searchqa": 400, "officeqa": 172, "livemath": 125, "spreadsheetbench": 279, "alfworld": 134}
SIMILAR = {("searchqa", "officeqa"), ("officeqa", "livemath"), ("officeqa", "spreadsheetbench")}


def sim(a, b):
    return (a, b) in SIMILAR or (b, a) in SIMILAR


def test_read(home, twins_per=(0.5, 1.0), fired=None, trimmed=False):
    """C on every item; F, P_F, T_F on fired items (procedure multiplier); twins per fired item; structural-zero sharing."""
    fired = fired or {"home": (0.6, 1.0), "similar": (0.3, 0.7), "other": (0.0, 0.5)}
    res = {"no_twins": [0, 0], "twins": [0, 0], "by_bench": {}}
    for b, n in TEST.items():
        kind = "home" if b in home else ("similar" if any(sim(b, h) for h in home) else "other")
        row = []
        for i in (0, 1):
            c, po, fr = CELL[b][i], PO[i], fired[kind][i]
            proc_arms = 3 if (not trimmed or kind != "other") else 1
            base = n * c * (1.0 + proc_arms * fr * po)
            tw = 0.0 if (trimmed and kind != "home") else n * c * fr * twins_per[i] * po
            res["no_twins"][i] += base
            res["twins"][i] += tw
            row.append((base, tw))
        res["by_bench"][b] = (kind, row)
    return res


print("\nT5  Final test read (1 run per test item; fired share home 60-100 %, similar 30-70 %, other 0-50 %; F, P_F, T_F")
print("    at x1.25/x1.6 on fired items; twins 0.5-1.0 cells per fired item expected, registered maximum 2). M tokens.")
TR, TRMAX = {}, {}
HOMES = (("default SB->OQ", ("spreadsheetbench", "officeqa")), ("recommended SB->ALF", ("spreadsheetbench", "alfworld")))
for name, home in HOMES:
    r = test_read(home)
    TR[name] = r
    lo, hi = r["no_twins"][0] / M, r["no_twins"][1] / M
    tlo, thi = r["twins"][0] / M, r["twins"][1] / M
    print(f"  {name:20s} without twins {lo:5.1f}-{hi:5.1f} | twins alone {tlo:4.1f}-{thi:5.1f} | with twins {lo + tlo:5.1f}-{hi + thi:5.1f}")
    for b, (kind, row) in r["by_bench"].items():
        print(f"      {b:17s} {kind:7s} {row[0][0] / M:5.2f}-{row[1][0] / M:5.2f} (+twins {row[0][1] / M:4.2f}-{row[1][1] / M:4.2f})")
    t = test_read(home, trimmed=True)
    print(f"  {name:20s} OPTION trimmed (P_F, T_F only on L + similar; twins only on L): with twins"
          f" {(t['no_twins'][0] + t['twins'][0]) / M:5.1f}-{(t['no_twins'][1] + t['twins'][1]) / M:5.1f}")
    x = test_read(home, twins_per=(2.0, 2.0))
    TRMAX[name] = (x["no_twins"][1] + x["twins"][1]) / M
    print(f"  {name:20s} MAXIMUM schedule (high fired shares, 2 twins per fired item, high anchors): {TRMAX[name]:5.1f}")

# ---------------------------------------------------------------- T6 caps
print("\nT6  Registered solver caps (ledger) from the MAXIMUM schedule: scope cap = 1.5 x maximum-schedule high + one full")
print("    next reservation R (frozen budget.py:283-314 admits a call only if settled + open + R fits; R = 4 x (request")
print("    bytes + 512 + B), ledger.py:26-36, branch N B = 4M, request bytes [A] QA/SB 64,000, ALFWorld step 32,000);")
print("    rounded up to 0.1 M. Test-read cap likewise (>= the 1.3 x estimate start rule). Redo reserve = the largest single")
print("    acceptance block cap (one redo pre-funded; a second redo needs the owner's recorded cap decision). M tokens.")
B_N = {"spreadsheetbench": 4 * 16384, "officeqa": 4 * 8192, "searchqa": 4 * 8192, "livemath": 4 * 8192, "alfworld": 4 * 1024}
REQ = {"spreadsheetbench": 64000, "officeqa": 64000, "searchqa": 64000, "livemath": 64000, "alfworld": 32000}
R = {b: 4 * (REQ[b] + 512 + B_N[b]) for b in B_N}
print("  one full reservation R: " + ", ".join(f"{b} {R[b]:,}" for b in ("spreadsheetbench", "officeqa", "alfworld")))
CAP = 1.5
caps = {}
for name, a in STEP_ARGS.items():
    bench, s = a[0], STEPS["max"][name]
    c = {k: up(CAP * s[k][1] / M + R[bench] / M) for k in ("run", "examiner", "selftest", "accept")}
    caps[name] = c
    print(f"  {name:10s} run {c['run']:5.1f} | examiner(incl. G_acc) {c['examiner']:4.1f} | selftest {c['selftest']:4.1f}"
          f" | accept {c['accept']:5.1f} | step sum {sum(c.values()):5.1f}   (max high:"
          f" {s['run'][1] / M:.2f}/{s['examiner'][1] / M:.2f}/{s['selftest'][1] / M:.2f}/{s['accept'][1] / M:.2f})")
blocks = {"SB step 1": 1, "OQ step 2": 2, "ALF step 2": 4}
PILOT = {}
for name, ss in learn.items():
    steps_sum = sum(sum(caps[s].values()) for s in ss)
    r = TR[name]
    est_hi = (r["no_twins"][1] + r["twins"][1]) / M
    test_cap = up(CAP * TRMAX[name] + max(R.values()) / M, 1.0)
    redo = max(up(caps[s]["accept"] / blocks[s]) for s in ss)
    total = steps_sum + test_cap + redo
    PILOT[name] = up(total, 5.0)
    print(f"  {name:20s} steps {steps_sum:5.1f} + test read {test_cap:5.1f} (max {TRMAX[name]:4.1f}; estimate high {est_hi:4.1f},"
          f" 1.3 x = {1.3 * est_hi:5.1f}) + redo reserve {redo:4.1f} = {total:5.1f} -> pilot solver cap {PILOT[name]:5.0f}")
    lo = sum(STEPS["estimate"][s]["total"][0] for s in ss) / M + (r["no_twins"][0] + r["twins"][0]) / M
    hi = sum(STEPS["estimate"][s]["total"][1] for s in ss) / M + est_hi
    mx = sum(STEPS["max"][s]["total"][1] for s in ss) / M + TRMAX[name]
    print(f"  {name:20s} solver estimate learning + test read = {lo:5.1f}-{hi:5.1f} M; maximum schedule {mx:5.1f} M")
pi_cap = up(CAP * ALF_PI["max"]["accept"][1] / M + R["alfworld"] / M)
alf_sum_pi = sum(dict(caps["ALF step 2"], accept=pi_cap).values())
steps_pi = sum(caps["SB step 1"].values()) + alf_sum_pi
redo_pi = max(up(caps["SB step 1"]["accept"] / blocks["SB step 1"]), up(pi_cap / blocks["ALF step 2"]))
test_pi = up(CAP * TRMAX["recommended SB->ALF"] + max(R.values()) / M, 1.0)
total_pi = steps_pi + test_pi + redo_pi
mx_pi = (STEPS["max"]["SB step 1"]["total"][1] + ALF_PI["max"]["total"][1]) / M + TRMAX["recommended SB->ALF"]
print(f"  owner #9 option P_i on ALFWorld (recommended pilot), same rule: ALF accept cap {pi_cap:5.1f}"
      f" (max high {ALF_PI['max']['accept'][1] / M:.2f}) | ALF step sum {alf_sum_pi:5.1f}")
print(f"      steps {steps_pi:5.1f} + test read {test_pi:5.1f} + redo reserve {redo_pi:4.1f} = {total_pi:5.1f}"
      f" -> pilot solver cap {up(total_pi, 5.0):5.0f}; maximum schedule {mx_pi:5.1f} M")
print("  previous caps (pre-review, expected workload): SB accept 6.2, OQ accept 20.5, ALF accept 66.9; pilot 135 / 230")

# ---------------------------------------------------------------- T7 smoke
print("\nT7  Smoke (real items: SearchQA pool tail 280 = 20 S2 + 200 S-N1 + 60 S4; ALFWorld 12 = 6 S2 + 6 S-N1;")
print("    fixtures OQ/LM/SB 20 each). M tokens; fixtures sized like SearchQA cells (low) or like real items (high).")
sq = CELL["searchqa"]


def s2(alf_runs, alf_proc_arms):
    out = []
    for i in (0, 1):
        po = PO[i]
        arms_qa = 1.0 + 3 * po                               # C, X, P, twins
        qa = 20 * 2 * sq[i] * arms_qa
        fx = sum(20 * 2 * (sq[0] if i == 0 else CELL[b][1]) * arms_qa for b in ("officeqa", "livemath", "spreadsheetbench"))
        alf = 6 * alf_runs * CELL["alfworld"][i] * (1.0 + alf_proc_arms * po)
        out.append((qa, fx, alf))
    return out


trim = s2(1, 2)
s1 = (60 * 500 + 16_900, 60 * 4_500 + 16_900)          # [A] 60 calls x 0.5-4.5k tokens + one M=16,384 call
sn1 = [200 * 2 * sq[i] + 6 * 2 * CELL["alfworld"][i] for i in (0, 1)]
s4 = [1.25 * (20 * sq[i] * (1.0 if i == 0 else 1.6) + 40 * sq[i] * (PO[i] + 1.0 + PO[i] + 1.0 + 0.75 * PO[i]))
      for i in (0, 1)]                                   # run 20 + accept 40 (A* 100 %), +25 % one-block redo drill
lo, hi = sum(trim[0]) / M, sum(trim[1]) / M
print(f"  S2 registered (ALF 6 x 1 run x C,X,P)          QA {trim[0][0] / M:.2f}-{trim[1][0] / M:.2f} fixtures"
      f" {trim[0][1] / M:.2f}-{trim[1][1] / M:.2f} ALF {trim[0][2] / M:.2f}-{trim[1][2] / M:.2f} = {lo:.2f}-{hi:.2f}")
print(f"  S1 probes (own ledger root, cap 0.5 M) {s1[0] / M:.2f}-{s1[1] / M:.2f}; S-N1 {sn1[0] / M:.2f}-{sn1[1] / M:.2f};"
      f" S4 {s4[0] / M:.2f}-{s4[1] / M:.2f}; S3 solver 0 (GLM <= 0.5 M)")
lo = (sum(trim[0]) + sn1[0] + s4[0]) / M
hi = (sum(trim[1]) + sn1[1] + s4[1]) / M
print(f"  smoke solver total (S2+S-N1+S4) {lo:5.2f}-{hi:5.2f} M -> cap 1.5 x high + R = {up(1.5 * hi + R['spreadsheetbench'] / M, 1.0):4.0f} M")
print("  production-configuration receipts (F19: registered body AND registered M, B) = S2 + S-N1 + S4 cells; S1 probe")
print("    receipts (probe-only M/B: B_probe, or M = B = 64 for S1-d) and control receipts (S1-e, fault drills) are separate;")
n_prod = 20 * 2 * 4 + 3 * 20 * 2 * 4 + 6 * 1 * 3 + 200 * 2 + 6 * 2 + 20 + 40 * 5
n_card = 20 * 2 + 3 * 20 * 2 + 6 * 1 + 200 * 2 + 6 * 2          # S2 card arm C + S-N1: no procedure, never a fault drill
print(f"    planned production cells (each >= 1 receipt): {n_prod}; S2 card arm C + S-N1 alone: {n_card} >= 300 required")

# ---------------------------------------------------------------- T8 misc
print("\nT8  Probe reservations, slot waits, pre-reset, memory (estimates).")


def reserve(req_bytes, B):
    return 4 * (req_bytes + 512 + B)                      # frozen rule, ledger.py:26-36


print(f"  S1-b/c/e with B_probe = 32,768, 2 KB request: one reservation {reserve(2000, 32768):,} tokens (sequential)")
print(f"  S1-d 8 concurrent with M = B = 64: 8 x {reserve(1000, 64):,} = {8 * reserve(1000, 64):,} tokens (< 0.5 M)")
print("  S1-b at M in {16, 64, 256} with B = 2 x M would halt the ledger on any non-enforced reply > B: hence B_probe")
for waiters, releases in ((10, 36), (13, 20)):
    p = (1 - 1 / waiters) ** releases
    print(f"  slot wait: {waiters} waiters, {releases} releases/h, P(no slot within 3,600 s) ~ {p:.3f}")
alf_round = 150 * (4 + 2)                                 # S', S, P_y, C + 2 twins per game (maximum schedule)
print(f"  ALFWorld acceptance round (maximum schedule) ~{alf_round:.0f} episodes; with 16 workers / 6 slots expected"
      f" 3,600 s timeouts ~{alf_round * (0.9 ** 36):.0f}; with workers = 6 slots: 0")
cut = {"smoke": 12, "run": 60, "accept": 150, "select candidates": 200}
for sec in (1, 3):
    print(f"  ALFWorld zero-call pre-reset at {sec} s/game [A]: all 3,514 games {3514 * sec / 3600:.1f} h;"
          f" cut slices only ({sum(cut.values())} games) {sum(cut.values()) * sec / 60:.0f} min")
LIVE_SBX_CAP = 6
worst = {"ALFWorld unit": 6 * 0.75 + 6 * 1.0,
         "QA unit (SQ/OQ/LM)": LIVE_SBX_CAP * 0.75,
         "SpreadsheetBench unit (2 live sandboxes + 3 native x 4 GiB limits)": 2 * 0.75 + 3 * 4.0}
for k, v in worst.items():
    print(f"  memory worst case (sum of container limits) {k}: {v:.1f} GiB of 15 GiB")
print("  SB: admissible only if the S0-measured native peak RSS <= 2 GiB (expected sum <= 7.5 GiB); else native slots 3 -> 2")

# ---------------------------------------------------------------- T9 size under skewed nulls (F1)


def betacf(a, b, x):
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


def ibeta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * betacf(a, b, x) / a
    return 1 - front * betacf(b, a, 1 - x) / b


def t_upper(t, df):
    """P(T_df >= t)."""
    tail = 0.5 * ibeta(df / 2, 0.5, df / (df + t * t))
    return tail if t >= 0 else 1 - tail


def t_crit(df, alpha=0.05):
    lo, hi = 0.0, 20.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if t_upper(mid, df) > alpha else (lo, mid)
    return (lo + hi) / 2


TAIL = {}


def btail(m):
    """[P(Bin(m, 1/2) >= t) for t = 0..m+1]."""
    if m not in TAIL:
        p = [comb(m, k) / 2 ** m for k in range(m + 1)]
        tail, acc = [0.0] * (m + 2), 0.0
        for k in range(m, -1, -1):
            acc += p[k]
            tail[k] = acc
        TAIL[m] = tail
    return TAIL[m]


def compositions(n, s):
    if s == 1:
        yield (n,)
        return
    for k in range(n + 1):
        for rest in compositions(n - k, s - 1):
            yield (k,) + rest


def size(null, n):
    """Exact rejection probability of the three one-sided 5 % tests under an i.i.d. null on a 0.25 lattice."""
    vals = [v for v, _ in null]
    ints = [round(4 * v) for v in vals]
    logp = [log(p) for _, p in null]
    absv = sorted({abs(i) for i in ints if i != 0})
    tc, zc = t_crit(n - 1), Z95
    rej = [0.0, 0.0, 0.0]
    for ks in compositions(n, len(vals)):
        lp = lgamma(n + 1) + sum(k * lp_ - lgamma(k + 1) for k, lp_ in zip(ks, logp))
        if lp < -40:
            continue
        pr = exp(lp)
        s_int = sum(k * i for k, i in zip(ks, ints))
        mean = s_int / 4 / n
        ss = sum(k * (i / 4) ** 2 for k, i in zip(ks, ints))
        var = (ss - n * mean * mean) / (n - 1)
        if var <= 1e-15:
            t_rej = mean > 0
        else:
            t_rej = mean / sqrt(var / n) >= tc
        # exact sign-flip: S* = sum_j a_j (2 B_j - m_j)
        m = {a: sum(k for k, i in zip(ks, ints) if abs(i) == a) for a in absv}
        pos = {a: sum(k for k, i in zip(ks, ints) if i == a) for a in absv}
        if len(absv) == 1:
            a1 = absv[0]
            need = (s_int + a1 * m[a1]) / (2 * a1)
            p_sf = btail(m[a1])[max(0, ceil(need - 1e-9))] if ceil(need - 1e-9) <= m[a1] else 0.0
        else:
            a1, a2 = absv
            p_sf = 0.0
            for b2 in range(m[a2] + 1):
                need = (s_int - a2 * (2 * b2 - m[a2]) + a1 * m[a1]) / (2 * a1)
                k1 = max(0, ceil(need - 1e-9))
                if k1 <= m[a1]:
                    p_sf += comb(m[a2], b2) / 2 ** m[a2] * btail(m[a1])[k1]
        sf_rej = p_sf <= 0.05 + 1e-12
        # Wilcoxon signed rank, zeros dropped, midranks, tie-corrected normal approximation
        nn = sum(m.values())
        w_rej = False
        if nn > 0:
            rank, wplus, ties = 0, 0.0, 0
            for a in absv:
                r = rank + (m[a] + 1) / 2
                wplus += pos[a] * r
                rank += m[a]
                ties += m[a] ** 3 - m[a]
            ew = nn * (nn + 1) / 4
            vw = nn * (nn + 1) * (2 * nn + 1) / 24 - ties / 48
            w_rej = vw > 0 and (wplus - ew) / sqrt(vw) >= zc
        rej[0] += pr * t_rej
        rej[1] += pr * sf_rej
        rej[2] += pr * w_rej
    return rej


NULLS = {
    "N1 Codex (+0.25 p.8, -1 p.2)": ((0.25, 0.8), (-1.0, 0.2)),
    "N2 tie-inflated (0 p.7, +0.25 p.24, -1 p.06)": ((0.0, 0.7), (0.25, 0.24), (-1.0, 0.06)),
    "N3 two-run (+0.5 p.6, 0 p.1, -1 p.3)": ((0.5, 0.6), (0.0, 0.1), (-1.0, 0.3)),
    "N0 symmetric reference (-0.5 p.25, 0 p.5, +0.5 p.25)": ((-0.5, 0.25), (0.0, 0.5), (0.5, 0.25)),
}
print("\nT9  Size (probability of a one-sided 5 % rejection) under bounded mean-zero nulls, exact enumeration over the")
print("    i.i.d. per-item difference distribution (no simulation noise). t = paired t-test (decides);")
print("    sf = exact sign-flip (sensitivity); W = Wilcoxon signed rank, tie-corrected normal approx. (sensitivity).")
for label, null in NULLS.items():
    assert abs(sum(v * p for v, p in null)) < 1e-12 and abs(sum(p for _, p in null) - 1) < 1e-12
    cells = []
    for n in (30, 41, 60, 100, 150):
        t, sf, w = size(null, n)
        cells.append(f"n={n:3d} t {t:.3f} sf {sf:.3f} W {w:.3f}")
    print(f"  {label}")
    print("    " + " | ".join(cells[:3]))
    print("    " + " | ".join(cells[3:]))
print("  Codex's n = 15 example (sign-flip): P(14 or 15 positive) =", f"{15 * 0.8 ** 14 * 0.2 + 0.8 ** 15:.4f}")
print("  chain-wide P(>= 1 false acceptance), k independent decisions at nominal 5 % each, global null: "
      + " | ".join(f"k={k} {1 - 0.95 ** k:.3f}" for k in range(5, 10)))

# ---------------------------------------------------------------- T10 J3/J4 boundaries (F22)
print("\nT10 J3/J4 boundary examples. J3: fault items (acceptance-slice items with >= 1 fault of a changed procedure in")
print("    routing or execution, any arm S'/P_y, any run) / |A| <= 2 %. J4: S' format-violating items <= S's + max(2, ceil(0.02 |A*|)).")
for bench, a, runs in (("spreadsheetbench", 60, 2), ("officeqa", 50, 4), ("alfworld", 150, 1), ("livemath", 100, 2),
                       ("searchqa", 1000, 1)):
    allowed = int(0.02 * a + 1e-9)
    j4 = [max(2, ceil(0.02 * x - 1e-9)) for x in (30, a // 2 if a // 2 >= 30 else 30, a)]
    print(f"  {bench:17s} |A| {a:4d} x {runs} runs: J3 passes with <= {allowed} fault items ({allowed + 1} fail)"
          f" | J4 margin at |A*| = 30 / {max(30, a // 2)} / {a}: {j4[0]} / {j4[1]} / {j4[2]} items")


# ---------------------------------------------------------------- T11 two chains (owner rule 2026-10-21 22:3x)
print("\nT11 Two formal chains (owner 22:3x): chain G = GLM-5.3 solver via the frozen BigModel route (weak_solver_probe.py:76-77,")
print("    no ROUTES entry; v3 SOLVER_MAX_TOKENS 65,536, SLOTS 10), chain D = deepseek-v4.1-flash-1017 via elucid (RD 4.1, 8 slots).")
print("    Method roles GLM-5.3 in both chains. Every registered per-chain cap applies to EACH chain; pilot totals double.")
print("    The per-cell anchors of RD 9.1 are deepseek measurements; chain G reuses them as a PLACEHOLDER [A] (GLM-5.3 answers")
print("    with reasoning low under a 65,536-token bound, so its cells are likely dearer); chain G gets its own zero-call cap")
print("    check after its first run unit (RD 9.3). Items: separate consumption namespaces per chain; both chains see the SAME")
print("    items (a replication, not independent evidence). M tokens.")
for name, ss in learn.items():
    r = TR[name]
    l_lo = sum(STEPS["estimate"][s]["total"][0] for s in ss) / M
    l_hi = sum(STEPS["estimate"][s]["total"][1] for s in ss) / M
    l_mx = sum(STEPS["max"][s]["total"][1] for s in ss) / M
    t_lo, t_hi = (r["no_twins"][0] + r["twins"][0]) / M, (r["no_twins"][1] + r["twins"][1]) / M
    one = (l_lo + t_lo, l_hi + t_hi, l_mx + TRMAX[name], PILOT[name])
    tag = "(owner default, taken 22:3x)" if name.startswith("default") else "(recommendation, not taken)"
    print(f"  {name:20s} {tag}")
    print(f"      per chain   learning {l_lo:5.1f}-{l_hi:5.1f} | test read {t_lo:5.1f}-{t_hi:5.1f} | solver {one[0]:5.1f}-{one[1]:5.1f}"
          f" (maximum {one[2]:5.1f}) | solver cap {one[3]:4.0f}")
    print(f"      two chains  learning {2 * l_lo:5.1f}-{2 * l_hi:5.1f} | test read {2 * t_lo:5.1f}-{2 * t_hi:5.1f} | solver"
          f" {2 * one[0]:5.1f}-{2 * one[1]:5.1f} (maximum {2 * one[2]:5.1f}) | solver cap {2 * one[3]:4.0f}")
    steps_cap = sum(sum(caps[s].values()) for s in ss)
    test_cap = up(CAP * TRMAX[name] + max(R.values()) / M, 1.0)
    redo = max(up(caps[s]["accept"] / blocks[s]) for s in ss)
    print(f"      per-chain cap = steps {steps_cap:5.1f} + test read {test_cap:5.1f} + redo reserve {redo:4.1f};"
          f" two chains: steps {2 * steps_cap:5.1f} + test reads {2 * test_cap:5.1f} + redo reserves {2 * redo:4.1f}")
R_G = {b: 4 * (REQ[b] + 512 + 65536) for b in REQ}
print("  chain G one full reservation with its frozen bound B = 65,536 on every bench (disclosure; the registered per-chain")
print("  caps are NOT recomputed, owner rule): " + ", ".join(f"{b} {R_G[b]:,}" for b in ("spreadsheetbench", "officeqa", "alfworld")))
for name in ("SB step 1", "OQ step 2"):
    bench, s = STEP_ARGS[name][0], STEPS["max"][name]
    cg = {k: up(CAP * s[k][1] / M + R_G[bench] / M) for k in ("run", "examiner", "selftest", "accept")}
    print(f"      {name:10s} caps with R_G for comparison: run {cg['run']:4.1f} | examiner {cg['examiner']:4.1f} | selftest"
          f" {cg['selftest']:4.1f} | accept {cg['accept']:4.1f}  (registered {caps[name]['run']:.1f}/{caps[name]['examiner']:.1f}/"
          f"{caps[name]['selftest']:.1f}/{caps[name]['accept']:.1f})")
# examiner research (RD 7.2): <= 24 requests per step and bench, <= 8 GLM-5.3 calls each (protocol.py:257); tokens per
# call [A] 8,000-15,000 (prompt with <= 3 page excerpts of <= 8,000 characters, research.py:60, plus a low-reasoning reply);
# expected 4-24 requests of 4-8 calls. Role reservation: CLIENT_ATTEMPTS 4 x (request bytes [A] 40,000 + 512 + 16,384).
RES_MAX = 24 * 8 * 15000 / M
R_ROLE = 4 * (40000 + 512 + 16384) / M
res_cap = up(CAP * RES_MAX + R_ROLE)
res_lo, res_hi = 4 * 4 * 8000 / M, 24 * 8 * 15000 / M
print(f"  examiner research sub-scope per step and bench: maximum 24 requests x 8 calls x 15,000 = {RES_MAX:.2f} M;"
      f" cap 1.5 x max + one role reservation ({R_ROLE:.3f}) = {res_cap:.1f} M")
print(f"      expected {res_lo:.2f}-{res_hi:.2f} M per step; default pilot per chain (2 steps) {2 * res_lo:.2f}-{2 * res_hi:.2f} M;"
      f" two chains {4 * res_lo:.2f}-{4 * res_hi:.2f} M")
glm_lo, glm_hi = 3 + 2 * res_lo, 8 + 2 * res_hi
print(f"  GLM-5.3 method roles per chain (v3 anchor 3-8 M [CI F13] + research): {glm_lo:.1f}-{glm_hi:.1f} M; two chains"
      f" {2 * glm_lo:.1f}-{2 * glm_hi:.1f} M; role caps 30 M per chain -> 60 M; per-step ceilings per chain: engineer 1.5 +"
      f" examiner 2.5 + research {res_cap:.1f} = {1.5 + 2.5 + res_cap:.1f} M, x 2 steps = {2 * (1.5 + 2.5 + res_cap):.1f} M <= 30 M")
print("  chain G solver tokens are GLM-5.3 tokens charged to chain G's SOLVER scopes (cap above), never to the role caps;")
print("  smoke (one, elucid only, RD 10) unchanged: solver 14 M, GLM 2 M, S1 probe root 0.5 M")

