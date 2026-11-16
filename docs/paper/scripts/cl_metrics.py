#!/usr/bin/env python3
"""Continual-learning (CL) metrics for the route-B five-bench chains.

Reads only aggregate files whose numbers the owner has already opened (no model
calls, no network, no run directories) and prints markdown tables:

  * the stage matrix R[k][t] (k = 0 is C, the instruction-only start) per run/chain,
  * ACC / dACC / PG (plasticity) / BWT / FGT (forgetting) / FWT,
  * TS / TD (incremental transfer to similar / dissimilar benches),
  * the no-harm rate over off-diagonal cells and the touch (non-abstention) rate,
  * the same-text rerun noise floor and the replication of package effects,
  * the cross-v5 instruction-transfer matrix (UPPER BOUND / diagnostic only),
  * a token-cost table.

Standard library only.  Usage (from the repository root):

    python3 -I -B docs/paper/scripts/cl_metrics.py \
        --out docs/paper/scripts/cl_metrics_output.md

Inputs can be overridden with --input NAME=PATH (names: see INPUTS below).
Missing inputs or cells are reported as "missing"/"—" and excluded from means.
"""

import argparse
import hashlib
import json
import math
import os
import sys

BENCHES = ["SearchQA", "OfficeQA", "ZebraLogic", "SpreadsheetBench", "ALFWorld"]
SHORT = {"SearchQA": "SQA", "OfficeQA": "OQA", "ZebraLogic": "Zebra",
         "SpreadsheetBench": "Sheet", "ALFWorld": "ALF"}
KEY = {"SearchQA": "searchqa", "OfficeQA": "officeqa", "ZebraLogic": "zebralogic",
       "SpreadsheetBench": "spreadsheetbench", "ALFWorld": "alfworld"}
BENCH_OF_KEY = {v: k for k, v in KEY.items()}
STEPS = 5                                    # K: steps per chain
HOME = {k: BENCHES[k - 1] for k in range(1, STEPS + 1)}   # bench learned/imported at step k
SINGLE_TURN = ["SearchQA", "OfficeQA", "ZebraLogic", "SpreadsheetBench"]
# Registered "related" map of the fivebench readout (stage_questions.related_benches);
# taken from the main-v6 readout when present, this constant is only the fallback.
FALLBACK_SIMILAR = {"SearchQA": ["OfficeQA"], "OfficeQA": ["SearchQA", "SpreadsheetBench"],
                    "ZebraLogic": [], "SpreadsheetBench": ["OfficeQA"], "ALFWorld": []}
Z95 = 1.96

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
DASH = os.environ.get("CL_METRICS_DASH", "<local-scratch>/dash")  # input directory (set the variable)
V219 = os.environ.get("CL_METRICS_V219", "<local-scratch>/v219")  # input directory (set the variable)
HANDOFF = os.path.join(REPO, "docs", "handoff")

# name -> candidate paths (first existing one is used)
INPUTS = {
    "m5_cells": [os.path.join(DASH, "m5_cells.json")],
    "m5_arms": [os.path.join(DASH, "m5_arms.json")],
    "imp5_cells": [os.path.join(DASH, "imp5_cells.json")],
    "imp5_arms": [os.path.join(DASH, "imp5_arms.json")],
    # canonical registered aggregates (sha-bound in the ledger); used for the
    # cross-check and the per-item rerun flips, and as fallback for the dash cells
    "m5_agg": [os.path.join(HANDOFF, "main-v5-readout-20261101", "readout-aggregates.json")],
    "imp5_agg": [os.path.join(HANDOFF, "implant-v5-readout-20261101", "readout-aggregates.json")],
    "m6": [os.path.join(V219, "m6-D-readout.json"),
           os.path.join(HANDOFF, "main-v6-readout-20261103", "m6-D-readout.json")],
    "m6_ledger": [os.path.join(V219, "m6-D-ledger-state.json")],
    # chain G of the same run (opened 11/04 09:48); its chains block is merged into "m6"
    "m6g": [os.path.join(V219, "m6-G-readout.json"),
            os.path.join(HANDOFF, "main-v6-readout-20261103", "m6-G-readout.json")],
    "m6g_ledger": [os.path.join(V219, "m6-G-ledger-state.json")],
    "cross5": [os.path.join(V219, "cross5-readout.json"),
               os.path.join(HANDOFF, "cross-v5-readout-20261103", "cross5-readout.json")],
}

RUNS = {
    "main-v5": ("method", "nothing kept in steps 1-4; ALFWorld v11 package imported at step 5"),
    "implant-v5": ("UPPER BOUND", "hand-picked ZebraLogic program implanted at step 3, no learning; "
                                  "ALFWorld v11 import at step 5"),
    "main-v6": ("method", "ZebraLogic solver learned and accepted at step 3; ALFWorld v11 import at step 5"),
}
EXPECTED_CHAINS = {"main-v5": ["G", "D"], "implant-v5": ["G", "D"], "main-v6": ["G", "D"]}

# Token costs transcribed from docs/results-and-lessons.md (entry date in the last field).
# main-v6 D is recomputed from its ledger state file instead.
LEDGER_COSTS = [
    ("main-v5", "G", 40454792, "solver 31,526,995 (test read 13,967,827) + GLM roles 8,927,797", "11/01 02:46"),
    ("main-v5", "D", 28524698, "solver 21,570,503 (test read 16,336,982) + roles 6,954,195", "11/01 02:46"),
    ("implant-v5", "G", 15581996, "test read 15,581,960 + first-call check 36 (no learning)", "11/01 12:08"),
    ("implant-v5", "D", 16987946, "test read 16,987,920 + first-call check 26 (no learning)", "11/01 12:08"),
    ("cross-v5", "G", 33024479, "test read 33,024,443 + 36 (F/C/B + 4 card-swap arms)", "11/03 07:52"),
    ("cross-v5", "D", 38316226, "test read 38,316,200 + 26 (F/C/B + 4 card-swap arms)", "11/03 07:52"),
    ("main-v4", "G", 33945390, "solver 26,905,738 (test read 13,749,468) + roles 7,039,652", "10/31 03:05"),
    ("main-v4", "D", 30959571, "solver 25,017,416 (test read 19,349,595 incl. 3,414,507 redo) + roles 5,942,155",
     "10/31 03:05"),
    ("baseline-v210", "G", 8090096, "B and C arms, 4 benches (no SpreadsheetBench)", "10/30 11:0x"),
    ("baseline-v210", "D", 9238763, "B and C arms, 4 benches (no SpreadsheetBench)", "10/30 11:0x"),
    ("alfworld-v11", "D", 71755052, "one ALFWorld step: training 15,947,596, acceptance 25,485,353, "
                                    "test 20,910,157", "10/29 02:4x"),
    ("zebra-hp-v3r4", "D", 1513930, "ZebraLogic test read only, F and C (200 items)", "10/30 18:27"),
    ("cal-1", "D", 27481897, "11 texts x 200 SearchQA train items x 4 reruns (train side only)", "10/20 23:43"),
    ("route-A coevo5-v1 E-glm", "G", 36125058, "5 steps incl. per-step test reads (LiveMath set)", "10/19 10:52"),
    ("route-A coevo5-v1 I-glm", "G", 60339685, "instruction chain, 5 steps (LiveMath set)", "10/19 10:52"),
    ("route-A coevo5-v1 SkillOpt-glm", "G", 59596851, "5 steps (LiveMath set)", "10/19 10:52"),
    ("route-A coevo5-v1 GEPA-glm", "G", 16183204, "5 steps (LiveMath set)", "10/19 10:52"),
]


# ----------------------------------------------------------------------------- utils
def first_existing(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fmt_pts(x, nd=1, sign=True):
    """fraction -> points string."""
    if x is None:
        return "—"
    v = round(100.0 * x, nd) + 0.0
    return ("%+.*f" if sign else "%.*f") % (nd, v)


def fmt_pct(x, nd=1):
    return "—" if x is None else "%.*f" % (nd, round(100.0 * x, nd) + 0.0)


def fmt_ci(lo, hi):
    if lo is None or hi is None:
        return ""
    return " [%s, %s]" % (fmt_pts(lo), fmt_pts(hi))


def mean(values):
    vals = [v for v in values if v is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def est(mean_, lo=None, hi=None, better=None, worse=None):
    return {"mean": mean_, "lo": lo, "hi": hi, "better": better, "worse": worse}


# ----------------------------------------------------------------------------- loaders
def chains_from_dash(cells, arms, run, src):
    """main-v5 / implant-v5 dashboard cells (d1 = primary, d2 = identical-request rule, points)."""
    out = {}
    for ch in sorted({r["chain"] for r in cells}):
        c = {"run": run, "chain": ch, "src": src, "stage": ["C"] + [None] * STEPS,
             "n": {}, "accC": {}, "accB": {}, "raw": {}, "delta": {}, "pairs": {}}
        for a in arms:                  # exact integer counts of correct items
            if a["chain"] != ch:
                continue
            b = a["bench"]
            c["n"][b] = a["n"]
            c["accC"][b] = a["C"] / a["n"]
            c["accB"][b] = a["B"] / a["n"]
            c["raw"].setdefault("F", {})[b] = a["F"] / a["n"]
        for r in cells:
            if r["chain"] != ch:
                continue
            k, arm, b = r["k"], r["arm"], r["bench"]
            if c["stage"][k] not in (None, arm):
                raise ValueError("inconsistent stage arm %s %s k=%s" % (run, ch, k))
            c["stage"][k] = arm
            c["n"].setdefault(b, r["n"])
            c["accC"].setdefault(b, r["acc_c"])
            if arm == "C" or b in c["delta"].get(arm, {}):
                continue
            lo = None if r["lo"] is None else r["lo"] / 100.0
            hi = None if r["hi"] is None else r["hi"] / 100.0
            accC = c["accC"][b]
            # primary row value: exact count for F, C + rounded paired difference otherwise
            rP = c["raw"].get("F", {}).get(b) if arm == "F" else None
            if rP is None:
                rP = accC + (r["acc"] - r["acc_c"])
            P = est(rP - accC, lo, hi, r["better"], r["worse"])
            if r["d2"] == r["d1"]:
                S = dict(P)
                rS = rP
            elif r["d2"] == 0 and r["same_req"] == r["n"]:
                S = est(0.0, 0.0, 0.0, 0, 0)
                rS = accC
            else:                       # secondary CI not in the dash file
                S = est(r["d2"] / 100.0)
                rS = accC + r["d2"] / 100.0
            S["mean"] = rS - accC
            reread = r["same_req"] == r["n"] and (r["better"] + r["worse"]) > 0
            c["delta"].setdefault(arm, {})[b] = {
                "P": P, "S": S, "RP": rP, "RS": rS, "touched": r["n"] - r["same_req"],
                "same": r["same_req"], "tie_n": r["same_req"] if reread else None,
                "tie_flips": (r["better"] + r["worse"]) if reread else None}
        out[ch] = c
    return out


def _pair_est(p, which):
    e = p[which]["estimate"]
    lo, hi = (e.get("ci95") or [None, None])
    return est(e["mean"], lo, hi, p[which].get("better"), p[which].get("worse"))


def chains_from_readout(doc, run, src):
    """fivebench readout format (main-v6, cross-v5, in-repo v5 aggregates)."""
    out = {}
    for ch, C in doc.get("chains", {}).items():
        stage = C.get("stage_rows")
        c = {"run": run, "chain": ch, "src": C.get("_src", src), "stage": list(stage) if stage else None,
             "n": {}, "accC": {}, "accB": {}, "raw": {}, "delta": {}, "pairs": {}}
        for key, pb in C.get("per_bench", {}).items():
            b = BENCH_OF_KEY.get(key)
            if b is None:
                continue
            c["n"][b] = pb.get("items_all_arms")
            acc = pb.get("acc", {})
            if "C" in acc:
                c["accC"][b] = acc["C"]
            if "B" in acc:
                c["accB"][b] = acc["B"]
            for arm, v in acc.items():
                c["raw"].setdefault(arm, {})[b] = v
            for pname, p in pb.get("pairs", {}).items():
                P, S = _pair_est(p, "primary"), _pair_est(p, "secondary")
                one = p.get("items_reading_one_cell") or 0
                tie = p.get("items_tied_by_identical_requests") or 0
                flips = None
                if tie and None not in (P["better"], P["worse"], S["better"], S["worse"]):
                    flips = (P["better"] + P["worse"]) - (S["better"] + S["worse"])
                entry = {"P": P, "S": S, "one": one, "tie_n": tie or None, "tie_flips": flips,
                         "touched": p["n"] - one - tie, "same": one + tie}
                c["pairs"].setdefault(b, {})[pname] = entry
                if pname.endswith("-C") and b in c["accC"]:
                    arm = pname[:-2]
                    if arm in ("B",):
                        continue
                    e = dict(entry)
                    e["RP"] = c["accC"][b] + P["mean"]
                    e["RS"] = c["accC"][b] + S["mean"]
                    c["delta"].setdefault(arm, {})[b] = e
        out[ch] = c
    return out


# ----------------------------------------------------------------------------- CL matrix
def stage_matrix(c, an):
    """R[k][j] (fractions) for analysis an in {'P','S'}; None where missing."""
    R = []
    for k in range(STEPS + 1):
        arm = c["stage"][k] if c["stage"] else None
        row = []
        for b in BENCHES:
            if arm is None or b not in c["accC"]:
                row.append(None)
            elif arm == "C":
                row.append(c["accC"][b])
            else:
                e = c["delta"].get(arm, {}).get(b)
                row.append(None if e is None else e["R" + an])
        R.append(row)
    return R


def changed_steps(c):
    st = c["stage"]
    return [k for k in range(1, STEPS + 1) if st[k] != st[k - 1]]


def diff(a, b):
    return None if a is None or b is None else a - b


def cl_metrics(c, an, similar):
    R = stage_matrix(c, an)
    st = c["stage"]
    m = {}
    m["ACC_B"], _ = mean([c["accB"].get(b) for b in BENCHES])
    m["ACC_C"], _ = mean(R[0])
    m["ACC_F"], nf = mean(R[STEPS])
    m["n_bench"] = nf
    m["dACC"], _ = mean([diff(R[STEPS][j], R[0][j]) for j in range(5)])
    m["dACC_learned"], _ = mean([diff(R[STEPS][j], R[0][j]) for j in range(4)])
    tot = sum(c["n"].get(b, 0) for b in BENCHES)
    m["microF"] = (sum(R[STEPS][j] * c["n"][b] for j, b in enumerate(BENCHES)
                       if R[STEPS][j] is not None) / tot) if tot else None
    m["microC"] = (sum(R[0][j] * c["n"][b] for j, b in enumerate(BENCHES)
                       if R[0][j] is not None) / tot) if tot else None
    # plasticity: gain on the step's own bench at the moment of the step
    m["PG"], _ = mean([diff(R[k][k - 1], R[k - 1][k - 1]) for k in range(1, STEPS + 1)])
    m["PG_learned"], _ = mean([diff(R[k][k - 1], R[k - 1][k - 1]) for k in range(1, STEPS)])
    # backward transfer / forgetting over benches t < K (index j = t-1)
    m["BWT"], _ = mean([diff(R[STEPS][j], R[j + 1][j]) for j in range(STEPS - 1)])
    fg = []
    for j in range(STEPS - 1):
        hist = [R[l][j] for l in range(j + 1, STEPS) if R[l][j] is not None]
        fg.append(None if not hist or R[STEPS][j] is None else max(hist) - R[STEPS][j])
    m["FGT"], _ = mean(fg)
    # forward transfer: package before learning bench j vs C
    m["FWT"], _ = mean([diff(R[j][j], R[0][j]) for j in range(1, STEPS)])
    # incremental transfer of changed steps
    ts, td = [], []
    for k in changed_steps(c):
        for j, b in enumerate(BENCHES):
            if j == k - 1:
                continue
            v = diff(R[k][j], R[k - 1][j])
            (ts if b in similar.get(HOME[k], []) else td).append(v)
    m["TS"], m["TS_n"] = mean(ts)
    m["TD"], m["TD_n"] = mean(td)
    # harm over off-diagonal cells (contrast vs C), informative rows = package != C
    harmed = uncertain = informative = 0
    for k in range(1, STEPS + 1):
        arm = st[k]
        for j, b in enumerate(BENCHES):
            if j == k - 1 or arm == "C":
                continue
            informative += 1
            e = c["delta"].get(arm, {}).get(b)
            if e is None:
                uncertain += 1
                continue
            x = e[an]
            if x["mean"] is not None and x["mean"] < -1e-12:
                if x["hi"] is None:
                    uncertain += 1
                elif x["hi"] < 0:
                    harmed += 1
    m["off_all"] = STEPS * (len(BENCHES) - 1)
    m["off_inf"], m["harmed"], m["uncertain"] = informative, harmed, uncertain
    m["no_harm_all"] = 1 - harmed / m["off_all"]
    m["no_harm_inf"] = (1 - harmed / informative) if informative else None
    # touch rate of the final package
    homes = {HOME[k] for k in changed_steps(c)}
    fin = st[STEPS]
    t_items = t_tot = off_items = off_tot = 0
    m["touch"] = {}
    for b in BENCHES:
        n = c["n"].get(b)
        if fin == "C":
            touched = 0
        else:
            e = c["delta"].get(fin, {}).get(b)
            touched = None if e is None else e["touched"]
        m["touch"][b] = (touched, n)
        if touched is None or n is None:
            continue
        t_items += touched
        t_tot += n
        if b not in homes:
            off_items += touched
            off_tot += n
    m["touch_all"] = (t_items, t_tot)
    m["touch_off"] = (off_items, off_tot)
    m["homes"] = sorted(homes, key=BENCHES.index)
    return m, R


# ----------------------------------------------------------------------------- sections
def provenance(paths):
    rows = []
    for name in INPUTS:
        p = paths.get(name)
        rows.append((name, p if p else "missing", sha16(p) if p else "—"))
    return "## Inputs\n\n" + table(["name", "path", "sha256[:16]"], rows)


def row_label(c, k):
    st = c["stage"]
    if k == 0:
        return "C (instruction only)"
    arm = st[k]
    if arm == st[k - 1]:
        what = "nothing new kept" if arm == "C" else "same package as k-1"
    else:
        what = "package changed"
    return "%s, %s" % (arm, what)


def matrix_section(c, similar):
    kind, desc = RUNS[c["run"]]
    lines = ["### %s chain %s (%s: %s)" % (c["run"], c["chain"], kind, desc), "",
             "source `%s`; stage rows k=0..5: %s" % (os.path.basename(c["src"]), ", ".join(c["stage"])), ""]
    RP, RS = stage_matrix(c, "P"), stage_matrix(c, "S")
    rows = []
    for k in range(STEPS + 1):
        cells = []
        for j in range(5):
            p, s = RP[k][j], RS[k][j]
            if p is None:
                cells.append("—")
            elif s is not None and abs(p - s) > 5e-4:
                cells.append("%s (S %s)" % (fmt_pct(p), fmt_pct(s)))
            else:
                cells.append(fmt_pct(p))
        rows.append(["%d" % k, "—" if k == 0 else SHORT[HOME[k]], row_label(c, k)] + cells)
    lines.append("R[k][t], accuracy % (primary; '(S x)' = identical-request rule where it differs):")
    lines.append("")
    lines.append(table(["k", "step", "row"] + BENCHES, rows))
    # delta matrix with CI and touched items for informative rows
    rows = []
    for k in range(1, STEPS + 1):
        arm = c["stage"][k]
        if arm == "C":
            continue
        if k > 1 and arm == c["stage"][k - 1]:
            rows.append(["%d" % k, arm, "same as k=%d" % (k - 1), "", "", "", ""])
            continue
        cells = []
        for b in BENCHES:
            e = c["delta"].get(arm, {}).get(b)
            if e is None:
                cells.append("missing")
                continue
            P, S = e["P"], e["S"]
            txt = fmt_pts(P["mean"]) + fmt_ci(P["lo"], P["hi"])
            if abs(P["mean"] - S["mean"]) > 5e-4:
                txt += "; S " + fmt_pts(S["mean"]) + fmt_ci(S["lo"], S["hi"])
            txt += "; touched %s/%s" % (e["touched"], c["n"].get(b))
            cells.append(txt)
        rows.append(["%d" % k, arm] + cells)
    if rows:
        lines += ["", "Registered contrast row − C (points, 95% CI; P = primary, S = identical-request rule):", ""]
        lines.append(table(["k", "row"] + BENCHES, rows))
    # raw per-arm accuracies that differ from C + paired delta (SpreadsheetBench unknown rule)
    notes = []
    for arm, per in c["raw"].items():
        if arm in ("B", "C") or arm.startswith("X_"):
            continue
        for b, v in per.items():
            e = c["delta"].get(arm, {}).get(b)
            if e is not None and abs(v - e["RP"]) > 1.5e-3:
                notes.append("%s on %s: raw per-arm accuracy %s vs C + paired contrast %s" % (
                    arm, b, fmt_pct(v), fmt_pct(e["RP"])))
    if notes:
        lines += ["", "Note (scoring rule: unknown SpreadsheetBench artifacts count as correct for C/B and wrong "
                      "for package arms; the matrix uses C + registered paired contrast): " + "; ".join(notes) + "."]
    return "\n".join(lines)


def metrics_table(entries, similar):
    rows = []
    for c in entries:
        both = []
        for an in ("P", "S"):
            both.append((an, metric_cells(c, an, similar)))
        if both[0][1] == both[1][1]:
            both = [("P = S", both[0][1])]
        for an, cells in both:
            label = {"P": "primary", "S": "ident-req (S)"}.get(an, an)
            rows.append([c["run"], c["chain"], label, RUNS[c["run"]][0]] + cells)
    hdr = ["run", "chain", "analysis", "kind", "ACC_B", "ACC_C", "ACC_F", "dACC(F−C)", "dACC learned 4",
           "PG", "PG learned 4", "BWT", "FGT", "FWT", "TS (cells)", "TD (cells)",
           "harmed/informative off-diag (no-harm)", "no-harm all 20", "touched F", "off-target touched F"]
    return table(hdr, rows)


def headline_table(entries, similar):
    """Compact paper-style row per run/chain; 'P / S' where the two analyses differ."""
    def ps(fp, fs):
        return fp if fp == fs else "%s (S %s)" % (fp, fs)
    rows = []
    for c in entries:
        mp, _ = cl_metrics(c, "P", similar)
        ms, _ = cl_metrics(c, "S", similar)
        oa, ot = ms["touch_off"]
        rows.append([
            "%s %s" % (c["run"], c["chain"]), RUNS[c["run"]][0],
            "B %s · C %s · F %s" % (fmt_pct(ms["ACC_B"]), fmt_pct(ms["ACC_C"]),
                                    ps(fmt_pct(mp["ACC_F"]), fmt_pct(ms["ACC_F"]))),
            "C %s · F %s" % (fmt_pct(ms["microC"]), ps(fmt_pct(mp["microF"]), fmt_pct(ms["microF"]))),
            ps(fmt_pts(mp["dACC"]), fmt_pts(ms["dACC"])),
            ps(fmt_pts(mp["BWT"], 2), fmt_pts(ms["BWT"], 2)),
            ps(fmt_pts(mp["FWT"], 2), fmt_pts(ms["FWT"], 2)),
            "n/a" if ms["TS_n"] == 0 else fmt_pts(ms["TS"], 2),
            ps("%d/%d" % (mp["off_inf"] - mp["harmed"], mp["off_inf"]),
               "%d/%d" % (ms["off_inf"] - ms["harmed"], ms["off_inf"])),
            "%d/%d" % (oa, ot),
        ])
    return table(["run chain", "kind", "ACC macro % (P, S)", "micro % over 1,110 items", "dACC F−C (pp)",
                  "BWT (pp)", "FWT (pp)", "TS", "non-harmed informative off-diag cells", "off-target touched"], rows)


def metric_cells(c, an, similar):
    m, _ = cl_metrics(c, an, similar)
    ta, tt = m["touch_all"]
    oa, ot = m["touch_off"]
    return [
        fmt_pct(m["ACC_B"]), fmt_pct(m["ACC_C"]), fmt_pct(m["ACC_F"]),
        fmt_pts(m["dACC"]), fmt_pts(m["dACC_learned"]),
        fmt_pts(m["PG"]), fmt_pts(m["PG_learned"]),
        fmt_pts(m["BWT"], 2), fmt_pts(m["FGT"], 2), fmt_pts(m["FWT"], 2),
        ("n/a (0 cells)" if m["TS_n"] == 0 else "%s (%d)" % (fmt_pts(m["TS"], 2), m["TS_n"])),
        ("n/a" if m["TD_n"] == 0 else "%s (%d)" % (fmt_pts(m["TD"], 2), m["TD_n"])),
        "%d/%d = %s%%" % (m["harmed"], m["off_inf"],
                          "—" if m["no_harm_inf"] is None else fmt_pct(m["no_harm_inf"])) +
        (" (+%d uncertain)" % m["uncertain"] if m["uncertain"] else ""),
        "%s%%" % fmt_pct(m["no_harm_all"]),
        "%d/%d" % (ta, tt), "%d/%d" % (oa, ot),
    ]


def touch_table(chains):
    rows = []
    for c in chains:
        m, _ = cl_metrics(c, "S", FALLBACK_SIMILAR)
        cells = []
        for b in BENCHES:
            t, n = m["touch"][b]
            cells.append("—" if t is None or not n else "%d/%d (%s%%)" % (t, n, fmt_pct(t / n, 1)))
        rows.append([c["run"], c["chain"], c["stage"][STEPS], ", ".join(SHORT[h] for h in m["homes"])] + cells)
    return table(["run", "chain", "final row", "procedure homes"] + BENCHES, rows)


def noise_rerun_table(sources):
    """Single-turn benches: items whose solver requests were byte-identical to C but re-read."""
    rows, pooled = [], {}
    for c in sources:
        for b in SINGLE_TURN:
            e = None
            if b in c.get("pairs", {}) and "F-C" in c["pairs"][b]:
                e = c["pairs"][b]["F-C"]
            elif "F" in c["delta"] and b in c["delta"]["F"]:
                e = c["delta"]["F"][b]
            if not e or not e.get("tie_n") or e.get("tie_flips") is None:
                continue
            n_b = c["n"][b]
            tie, fl = e["tie_n"], e["tie_flips"]
            net = e["P"]["mean"] - e["S"]["mean"]
            f = fl / tie
            rows.append([c["run"], c["chain"], b, tie, fl, fmt_pct(f), fmt_pts(net),
                         "±%s" % fmt_pts(Z95 * math.sqrt(f / n_b), 1, sign=False)])
            agg = pooled.setdefault((c["chain"], b), [0, 0, n_b, []])
            agg[0] += fl
            agg[1] += tie
            agg[3].append(c["run"])
    prow = []
    for (ch, b), (fl, tie, n_b, runs) in sorted(pooled.items(), key=lambda x: (x[0][0], BENCHES.index(x[0][1]))):
        f = fl / tie
        prow.append([ch, b, "+".join(runs), tie, fl, fmt_pct(f),
                     "±%s" % fmt_pts(Z95 * math.sqrt(f / n_b), 1, sign=False), n_b])
    t1 = table(["run", "chain", "bench", "identical items re-read", "flips", "flip rate %",
                "net Δ (pts)", "NF95 for a full-panel contrast"], rows)
    t2 = table(["chain", "bench", "runs pooled", "items", "flips", "flip rate %", "NF95 (pts)", "panel n"], prow)
    return t1, t2


def across_run_table(chains_by_run):
    """Same arm text, same panel, different runs (C, B; and F on ALFWorld = same v11 package)."""
    rows = []
    for ch in ("G", "D"):
        for b in BENCHES:
            for arm in ("C", "B", "F"):
                if arm == "F" and b != "ALFWorld":
                    continue
                if arm == "B" and b == "ZebraLogic":      # shell sends no card: B and C share one cell
                    continue
                vals, n = [], None
                for run, chains in chains_by_run:
                    c = chains.get(ch)
                    if not c or not c["n"].get(b):
                        continue
                    n = n or c["n"][b]
                    if arm == "C":
                        v = c["accC"].get(b)
                    elif arm == "B":
                        v = c["accB"].get(b)
                    else:
                        e = c["delta"].get("F", {}).get(b)
                        v = None if e is None else e["RP"]
                    if v is not None:
                        vals.append((run, int(round(v * c["n"][b]))))
                if len(vals) < 2:
                    continue
                cnt = [x[1] for x in vals]
                rows.append([ch, b, arm, ", ".join("%s %d" % (r, v) for r, v in vals),
                             max(cnt) - min(cnt), fmt_pts((max(cnt) - min(cnt)) / n, 1, sign=False), n])
    return table(["chain", "bench", "arm", "correct per run", "spread (items)", "spread (pts)", "n"], rows)


def replication_table(chains_by_run):
    rows = []
    for ch in ("G", "D"):
        for b in ("ZebraLogic", "ALFWorld"):
            vals = []
            for run, chains in chains_by_run:
                c = chains.get(ch)
                e = c and c["delta"].get("F", {}).get(b)
                if e:
                    vals.append("%s %s" % (run, fmt_pts(e["S"]["mean"])))
            if vals:
                rows.append([ch, b, "; ".join(vals)])
    return table(["chain", "bench", "F − C (identical-request rule, pts) per run"], rows)


def cross_section(cross, similar):
    out = []
    targets = ["SearchQA", "OfficeQA", "SpreadsheetBench", "ALFWorld"]
    summary = []
    for ch in ("G", "D"):
        c = cross.get(ch)
        if not c:
            out.append("chain %s: missing" % ch)
            continue
        rows_xf, rows_xc = [], []
        cells, sim, dis = [], [], []
        harmed = improved = 0
        for s in BENCHES:
            r_xf, r_xc = [SHORT[s] + " card"], [SHORT[s] + " card"]
            for t in targets:
                if s == t:
                    r_xf.append("own (0)")
                    r_xc.append("F−C " + fmt_pts(c["pairs"][t]["F-C"]["S"]["mean"]))
                    continue
                p = c["pairs"].get(t, {}).get("X_%s-F" % KEY[s])
                q = c["pairs"].get(t, {}).get("X_%s-C" % KEY[s])
                if p is None:
                    r_xf.append("missing")
                    r_xc.append("missing")
                    continue
                e = p["S"]
                mark = " ↓" if e["hi"] is not None and e["hi"] < 0 else (
                    " ↑" if e["lo"] is not None and e["lo"] > 0 else "")
                r_xf.append(fmt_pts(e["mean"]) + fmt_ci(e["lo"], e["hi"]) + mark)
                r_xc.append("—" if q is None else fmt_pts(q["P"]["mean"]))
                cells.append(e["mean"])
                (sim if t in similar.get(s, []) else dis).append(e["mean"])
                harmed += e["hi"] is not None and e["hi"] < 0
                improved += e["lo"] is not None and e["lo"] > 0
            rows_xf.append(r_xf)
            rows_xc.append(r_xc)
        zeb = c["pairs"].get("ZebraLogic", {})
        zx = [zeb[k]["S"]["mean"] for k in zeb if k.startswith("X_") and k.endswith("-C")]
        out += ["### chain %s (%s)" % (ch, "GLM-5.3" if ch == "G" else "deepseek-v4-flash"), "",
                "Card swap with the package held fixed: X_s − F on target bench t (identical-request rule, pts, "
                "95% CI; ↓ = CI below 0, ↑ = CI above 0):", "",
                table(["source card \\ target"] + targets, rows_xf), "",
                "Registered contrast X_s − C (primary, pts; diagonal shows F − C): ", "",
                table(["source card \\ target"] + targets, rows_xc), "",
                "ZebraLogic target (shell sends no card): F − C %s; mean X_s − C over 4 sources %s "
                "(package effect, identical by construction)." % (
                    fmt_pts(zeb["F-C"]["S"]["mean"]) if "F-C" in zeb else "—",
                    fmt_pts(mean(zx)[0]) if zx else "—"), ""]
        n = len(cells)
        summary.append([ch, n, harmed, improved, "%s%%" % fmt_pct(1 - harmed / n) if n else "—",
                        "%s (%d)" % (fmt_pts(mean(sim)[0], 2), len(sim)),
                        "%s (%d)" % (fmt_pts(mean(dis)[0], 2), len(dis)),
                        fmt_pts(mean(cells)[0], 2)])
    out += ["### Instruction-transfer metrics (card swap; UPPER-BOUND/diagnostic, not a learning effect)", "",
            table(["chain", "off-diag cells", "harmed (CI<0)", "improved (CI>0)", "card no-harm rate",
                   "TS_card mean X−F (cells)", "TD_card mean X−F (cells)", "mean all off-diag"], summary)]
    return "\n".join(out)


def cost_section(ledgers):
    out = []
    rows = [[r, ch, "{:,}".format(t), note, src] for r, ch, t, note, src in LEDGER_COSTS]
    for ch in ("D", "G"):                      # one ledger state file per chain (shared/ledger-<chain>/state.json)
        ledger_path = ledgers.get(ch)
        if not ledger_path:
            rows.insert(0, ["main-v6", ch, "missing ledger file", "", ""])
            continue
        led = load_json(ledger_path)
        s = led.get("settled", {})
        overall = s.get("overall")
        test = s.get(ch + ":test", 0)
        conf = s.get(ch + ":confirm", 0)
        redo = s.get(ch + ":redo", 0)
        rows.insert(0, ["main-v6", ch, "{:,}".format(overall) if overall else "—",
                        "solver %s (test read %s) + roles %s; first-call check %s%s" % (
                            "{:,}".format(s.get(ch + ":solver", 0)), "{:,}".format(test),
                            "{:,}".format(s.get(ch + ":glm", 0)), conf,
                            "; redo %s" % "{:,}".format(redo) if redo else ""), "ledger state file"])
        steps = {}
        for k, v in s.items():
            parts = k.split(":")
            if len(parts) >= 4 and parts[1] == "xs":
                steps.setdefault((int(parts[3]), parts[2]), 0)
                steps[(int(parts[3]), parts[2])] += v
        srows = [[k, b, "{:,}".format(v)] for (k, b), v in sorted(steps.items())]
        tot = sum(steps.values())
        srows.append(["1-4", "training + acceptance", "{:,}".format(tot)])
        if overall:
            srows.append(["chain end", "test read (5 panels, stage rows + F/C/B)", "{:,}".format(test)])
            # the redo aggregate re-counts an "xs:…:attempt-2" key already inside the step sum
            srows.append(["check", "overall − (steps + test + first call)",
                          "{:,}".format(overall - tot - test - conf)])
        out += ["main-v6 %s per step (settled tokens from the run ledger):" % ch, "",
                table(["step", "bench / part", "tokens"], srows), ""]
    out.insert(0, table(["run", "chain", "tokens", "breakdown", "ledger entry"], rows) + "\n")
    return "\n".join(out)


def cross_check(dash_chains, agg_chains, run):
    lines = []
    for ch, c in dash_chains.items():
        a = agg_chains.get(ch)
        if not a:
            lines.append("%s %s: aggregate chain missing" % (run, ch))
            continue
        worst = 0.0
        for an in ("P", "S"):
            R1, R2 = stage_matrix(c, an), stage_matrix(a, an)
            for k in range(STEPS + 1):
                for j in range(5):
                    if R1[k][j] is not None and R2[k][j] is not None:
                        worst = max(worst, abs(R1[k][j] - R2[k][j]))
        same_stage = c["stage"] == a["stage"]
        lines.append("%s %s: stage rows equal = %s; max |R_dash − R_aggregate| = %.3f pts" % (
            run, ch, same_stage, 100 * worst))
    return lines


# ----------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", action="append", default=[], help="NAME=PATH override")
    ap.add_argument("--out", help="also write the markdown to this file")
    args = ap.parse_args(argv)
    for item in args.input:
        name, _, path = item.partition("=")
        if name not in INPUTS:
            ap.error("unknown input %s" % name)
        INPUTS[name] = [path]
    paths = {name: first_existing(cands) for name, cands in INPUTS.items()}

    out = ["# CL metrics for the route-B five-bench chains (generated by cl_metrics.py)", "",
           "Benches in learning order: " + " → ".join(BENCHES) + " (step 5 imports a fixed ALFWorld package). "
           "R[k][t] = accuracy on bench t of the package frozen after step k plus bench t's instruction card; "
           "k = 0 is C. All cells are single reads per item on the held-out test panels. "
           "Primary = registered analysis; S = identical-request rule (items whose solver requests are "
           "byte-identical to C count as ties). Contrasts are paired, in points (pp).", "",
           provenance(paths), ""]

    similar, sim_src = FALLBACK_SIMILAR, "fallback constant"
    m6 = load_json(paths["m6"]) if paths["m6"] else None
    m6g = load_json(paths["m6g"]) if paths.get("m6g") else None
    if m6g:                      # the G readout is a separate file with the same layout
        if m6 is None:
            m6 = m6g
        else:
            m6 = dict(m6)
            m6["chains"] = dict(m6.get("chains", {}))
            for ch, block in m6g.get("chains", {}).items():
                block = dict(block)
                block["_src"] = paths["m6g"]          # provenance of the merged chain
                m6["chains"][ch] = block
    if m6:
        try:
            sq = m6["chains"]["D"]["readout"]["stage_questions"]
            derived = {b: [] for b in BENCHES}
            for q in sq:
                derived[BENCH_OF_KEY[q["home_bench"]]] = [BENCH_OF_KEY[x] for x in q.get("related_benches", [])]
            similar, sim_src = derived, "main-v6 readout stage_questions.related_benches"
        except (KeyError, TypeError):
            pass
    out += ["Similarity map (%s): %s." % (sim_src, "; ".join(
        "%s ~ %s" % (SHORT[b], ", ".join(SHORT[x] for x in v) or "none") for b, v in similar.items())), ""]

    runs = []          # (run, {chain: data})
    for run, cells_k, arms_k, agg_k in (("main-v5", "m5_cells", "m5_arms", "m5_agg"),
                                        ("implant-v5", "imp5_cells", "imp5_arms", "imp5_agg")):
        dash = agg = None
        if paths[cells_k] and paths[arms_k]:
            dash = chains_from_dash(load_json(paths[cells_k]), load_json(paths[arms_k]), run, paths[cells_k])
        if paths[agg_k]:
            agg = chains_from_readout(load_json(paths[agg_k]), run, paths[agg_k])
        if dash:
            runs.append((run, dash))
            if agg:
                out += ["Cross-check dash cells vs in-repo aggregates: " + "; ".join(cross_check(dash, agg, run)), ""]
        elif agg:
            runs.append((run, agg))
            out += ["%s: dash cells missing, using in-repo aggregates." % run, ""]
        else:
            runs.append((run, {}))
    m6_chains = chains_from_readout(m6, "main-v6", paths["m6"]) if m6 else {}
    runs.append(("main-v6", m6_chains))

    # ---- stage matrices
    out += ["## 1. Stage matrices R[k][t]", ""]
    entries = []
    for run, chains in runs:
        for ch in EXPECTED_CHAINS[run]:
            c = chains.get(ch)
            if not c or not c["stage"]:
                out += ["### %s chain %s: pending/missing (no opened readout for this chain)" % (run, ch), ""]
                continue
            out += [matrix_section(c, similar), ""]
            entries.append(c)

    # ---- metrics
    out += ["## 2. CL metrics (pp = percentage points; means over benches, each bench weighted equally)", "",
            "ACC = mean_t R[K][t]; dACC = mean_t (R[K][t] − R[0][t]); PG = mean_k (R[k][k] − R[k−1][k]); "
            "BWT = mean_{t<K} (R[K][t] − R[t][t]); FGT = mean_{t<K} (max_{t≤l<K} R[l][t] − R[K][t]); "
            "FWT = mean_{t≥2} (R[t−1][t] − R[0][t]); TS/TD = mean incremental effect R[k][t] − R[k−1][t] of steps "
            "that changed the package, on similar / dissimilar benches t ≠ home(k); harmed = off-diagonal cell "
            "whose contrast vs C has 95% CI upper bound < 0; informative = rows whose package differs from C; "
            "touched = items whose solver request differs from C under the final package; off-target = benches "
            "that host no procedure of the package. UPPER BOUND rows are not method effects.", ""]
    out += ["Headline (registered primary; '(S x)' = identical-request rule where it differs):", "",
            headline_table(entries, similar), "", "Full table:", "",
            metrics_table(entries, similar), ""]
    out += ["Touched items per bench under the final package (abstention = 1 − touched):", "",
            touch_table(entries), ""]

    # ---- noise floor
    noise_src = []
    for run, chains in runs:
        for ch in ("G", "D"):
            c = chains.get(ch)
            if c:
                noise_src.append(c)
    # prefer exact aggregates for v5 per-item flips when present
    for run, agg_k in (("main-v5", "m5_agg"), ("implant-v5", "imp5_agg")):
        if paths[agg_k]:
            agg = chains_from_readout(load_json(paths[agg_k]), run, paths[agg_k])
            noise_src = [c for c in noise_src if c["run"] != run] + [agg[ch] for ch in ("G", "D") if ch in agg]
    cross = chains_from_readout(load_json(paths["cross5"]), "cross-v5", paths["cross5"]) if paths["cross5"] else {}
    noise_src += [cross[ch] for ch in ("G", "D") if ch in cross]
    t1, t2 = noise_rerun_table(noise_src)
    rule = []
    for c in noise_src:
        prs = c.get("pairs", {}).get("SpreadsheetBench", {})
        if "F-C" in prs and "F-S3" in prs and abs(prs["F-C"]["P"]["mean"] - prs["F-S3"]["P"]["mean"]) > 5e-4:
            rule.append("%s %s F−C %s vs F−S3 %s (both package-rule scored)" % (
                c["run"], c["chain"], fmt_pts(prs["F-C"]["P"]["mean"]), fmt_pts(prs["F-S3"]["P"]["mean"])))
    out += ["## 3. Same-text noise floor", "",
            "(a) Within-run rereads of byte-identical requests (single-turn benches only; for ALFWorld an "
            "identical request sequence implies identical replies, so ties there are not a noise measure). "
            "NF95 = 1.96·sqrt(flip rate / n_panel): half-width of a pure-rerun paired contrast on the full panel.", "",
            t1, "", "Pooled per chain and bench:", "", t2, "",
            "SpreadsheetBench flips and net Δ include the unknown-artifact scoring asymmetry (C counts unknown as "
            "correct, package arms as wrong), so its pure rerun noise is somewhat smaller" +
            (": " + "; ".join(rule) + "." if rule else "."), ""]
    by_run = [(run, chains) for run, chains in runs] + [("cross-v5", cross)]
    out += ["(b) Across-run rereads of the same arm on the same panel (different runs and code snapshots; "
            "F on ALFWorld = the same imported v11 package):", "", across_run_table(by_run), "",
            "(c) Replication of the package effects (F − C, identical-request rule) on the two benches where "
            "procedures fire (implant-v5 and cross-v5 share the hand-picked programs; main-v6 D uses its learned "
            "solver; main-v5 has no ZebraLogic program):", "", replication_table(by_run), ""]

    # ---- instruction transfer
    out += ["## 4. Instruction transfer: cross-v5 card-swap matrix (UPPER BOUND / diagnostic)", ""]
    out += [cross_section(cross, similar) if cross else "cross-v5 readout missing", ""]

    # ---- costs
    out += ["## 5. Token costs", "",
            cost_section({"D": paths["m6_ledger"], "G": paths.get("m6g_ledger")}), ""]

    text = "\n".join(out).rstrip() + "\n"
    sys.stdout.write(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
