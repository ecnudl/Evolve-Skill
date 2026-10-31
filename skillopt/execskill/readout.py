"""The registered readouts of a test read (protocol ``fivebench-execskill-v1``; registration §8.2, §8.3, §6.3, §6.4;
Codex F2, F20, F21; implementation plan §1 readout row, T-READ-1).

Input: ``evaluation.unseal``'s cells {bench: {(arm, task_id, run): {"v2", "enabled", "shared_with", "answered",
"block", "room", "format", ...}}}. Item scores follow §6.3: F and its twins F∖p are read on L (an unknown token counts
as wrong), C, P_F and T_F on H (right). Two rules come first in every contrast (statistics review 1):

- one cell, one outcome: where an arm shares the card arm's cell (structural-zero sharing, §8.1: F, P_F and T_F on an
  item F enables nothing on), both arms read the SAME cell, so their difference on that run is 0 by construction --
  never one cell scored on L against itself on H;
- the §6.3 mask: the items on which no arm got any reply (``shared_unanswered``: every distinct cell unknown and
  undelivered) leave every contrast; their count is reported.

All intervals use the paired t of ``stats_ext`` (the registered primary model, §6.4): strata are the read's blocks
(OfficeQA's two time blocks, §8.1); on ALFWorld the rooms are the clusters (df = rooms - blocks; statistics review 7).
The bootstrap interval is reported beside it. Every reading is fixed before the read:

- Q1 (home): on each learned bench F − C, the one-sided paired t-test of §6.4, Holm over |L| (sign-flip and Wilcoxon
  as sensitivity, never deciding);
- Q2 (similar benches, owner's 10/17 map ``SIMILAR_PAIRS``): description only -- estimate, two-sided 95 % interval, the
  enable rate and every procedure's τ;
- Q3 (dissimilar benches): the equal-weight mean of F − C, one-sided 95 % lower bound > −5 points (``NI_MARGIN``) under
  BOTH the complete-case and the adverse reading (v6 §12.6: a favourable conclusion must hold under both); a package
  enabled on < 10 % of the dissimilar items "cannot act by construction" and is never "non-inferior";
- code vs text (Codex F20): F − T_F per bench, the estimand being the difference of the two implementations; readings
  from the intervals only -- two-sided 95 % lower > 0 "code_better", upper < 0 "text_better"; off home one-sided 95 %
  lower > −5 points "code_transfer_not_worse", upper < +5 points "text_transfer_not_worse"; otherwise "inconclusive";
  on a bench where F is enabled on < 10 % of the items (the Q3 guard) the only reading is "cannot_act_by_construction";
- labels (Codex F21): one primary label per procedure by the priority table, every other holding descriptor listed;
  the τ statements are Holm-adjusted over the family procedure × bench (each statement's one-sided p at 2.5 %, the
  side of a two-sided 95 % interval);
- ``format_withholding``: per procedure and bench, the J4-style format violations with and without it on its twin
  items (does it change the answer format);
- ``arm_table`` (§8.3, §6.2): per bench and arm, next to every accuracy (labelled "this period"): v2, official,
  official completion and lenient shares, the unknown counts, the cell and format flags, the procedure faults, the
  enable rate and, per 15-minute window of dispatch, the answer-tag share, the mean visible completion tokens and the
  short-answer share (registrar decision fixer-2, 2026-10-22: a cell whose completion tokens are below a quarter of
  the median of the same bench and arm in the unit's first window, ``_reference``); F − P_F is described per bench.

- ``stage_table`` (v2 stage reads, main-v2; owner decision 2026-10-23 16:0x): per bench and row k of the stage table
  -- the package after step k, row 0 the card arm -- the row's arm (C, a stage arm S<j> or F), its accuracy on L and on
  H over the masked items, and the paired contrasts row − C and row − row k−1 (each arm on its §6.3 side; a run on
  which both arms read the same cell -- a stage cell shares C's, F's or an earlier stage arm's -- adds 0), description
  only.

The test read is independent GENERALIZATION evidence; acceptance decisions are SELECTION evidence (Codex F2).

``report(manifest, out=)`` (ticket A13-1, A12-1 item 5) is the command line's readout: per chain that has read, once
the chain has ended and the owner's continuation file exists (``evaluation.unseal`` refuses otherwise), its read units
are unsealed and the readout written once into the new directory ``out``, with the final package's procedures as
{procedure id: home bench} (``Procedure.origin``; the integration-B5 contract) and the benches they were learned on.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from fractions import Fraction

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import evaluation, profiles, stats_ext
from .package import empty, load
from .profiles import (ALPHA, BENCHES, SUPPORTED_BENCHES, ZEBRA, ZEBRA_PC_V1, is_zebra, is_alfworld, read_benches, CANNOT_ACT_FIRED, CHAINS, NI_MARGIN, NI_MIN_FIRED, RECORD_HASH, SIMILAR_PAIRS,
                       STAGE_ARM, TIME_WINDOW_SECONDS, record, verified)

__all__ = ("arm_table", "code_vs_text", "differences", "format_withholding", "labels", "placebo_contrast", "q1_home",
           "q2_similar", "q3_noninferiority", "readout", "report", "side", "stage_table", "tau", "unanswered")

TWIN = "withhold:"
STAGE_LABEL = re.compile(r"%s[1-9][0-9]*" % STAGE_ARM)  # a stage arm "S<k>" of a v2 stage read
UNKNOWN = ("unknown", "unknown_artifact", "unknown_fault")
UNANSWERED = ("unknown",)  # §6.3 (acceptance.UNANSWERED): a cell that got no reply
LEVEL = 0.025  # one side of a two-sided 95 % interval
PRIORITY = ("harmful_elsewhere", "general", "home_benefit_established", "cannot_act_elsewhere", "no_measurable_effect")
EVIDENCE_KIND = "generalization"  # Codex F2: acceptance decisions are "selection"
PERIOD = "this_period"  # §8.3: every absolute accuracy is labelled with its serving period
# §6.2, §8.3 (registrar decision fixer-2, 2026-10-22): a short answer is below a quarter of its arm's first-window
# median; the registered value itself, so it stays here and is no protocol.py constant
SHORT_ANSWER = Fraction(1, 4)


# ------------------------------------------------------------------------------------------- cells and contrasts
def side(arm):
    """§6.3: F, its twins and the stage arms (packages with procedures, as F) are read on L, every other arm on H."""
    return "L" if arm == "F" or arm.startswith(TWIN) or STAGE_LABEL.fullmatch(arm) else "H"


def _runs(cells, arm, item):
    return sorted(r for (a, i, r) in cells if a == arm and i == item)


def _source(cells, arm, item, run):
    """The cell an arm reads on (item, run): its own, else the cell it shares -- the card arm's (§8.1), or in a stage
    read F's or an earlier stage arm's (``shared_arm``; a read without it shares only C's)."""
    value = cells[(arm, item, run)]
    if arm == "C" or value["shared_with"] is None:
        return arm
    return value.get("shared_arm") or "C"


def _score(token, on):
    """One run's score on side ``on`` (``stats_ext.item_scores``: L counts every unknown as wrong, H as right)."""
    return stats_ext.item_scores({("arm", "item"): [token]}, "arm", ["item"], side=on)["item"]


def differences(cells, first, second, items):
    """Per-item first − second (each arm on its §6.3 side), the mean over the item's runs; a run on which both arms
    read the same cell contributes 0 by construction (statistics review 1)."""
    out = []
    for item in items:
        runs = _runs(cells, first, item)
        require(runs and runs == _runs(cells, second, item), "Both arms have the same runs of an item")
        total = Fraction(0)
        for run in runs:
            if _source(cells, first, item, run) != _source(cells, second, item, run):
                total += (_score(cells[(first, item, run)]["v2"], side(first))
                          - _score(cells[(second, item, run)]["v2"], side(second)))
        out.append(total / len(runs))
    return out


def unanswered(cells):
    """§6.3 ``shared_unanswered``: the items on which no arm got any reply -- every distinct cell (a shared cell is
    C's) unknown and undelivered."""
    by_item = {}
    for (_, item, _), value in cells.items():
        if value["shared_with"] is None:
            by_item.setdefault(item, []).append(value)
    return sorted(i for i, found in by_item.items()
                  if all(v["v2"] in UNANSWERED and not v["answered"] for v in found))


def _items(cells, *arms):
    """The items every arm has cells on, the §6.3 mask removed."""
    found = set.intersection(*({i for (a, i, _) in cells if a == arm} for arm in arms))
    return sorted(found - set(unanswered(cells)))


def _known(cells, items, *arms):
    """The complete cases: items on which no run of the arms is unknown."""
    return [i for i in items if not any(cells[(arm, i, r)]["v2"] in UNKNOWN for arm in arms
                                        for r in _runs(cells, arm, i))]


def _design(cells, items):
    """The read's design for ``items``: its blocks as strata (OfficeQA's two time blocks, §8.1) and, on ALFWorld, the
    rooms as clusters (§6.4); {} when neither is recorded."""
    of_c = {i: v for (arm, i, _), v in cells.items() if arm == "C"}
    design = {}
    if any(of_c[i].get("block") is not None for i in items):
        design["strata"] = [str(of_c[i]["block"]) for i in items]
    if any(of_c[i].get("room") is not None for i in items):
        require(all(of_c[i].get("room") is not None for i in items), "Every item of a clustered read has its room")
        design["clusters"] = [str(of_c[i]["room"]) for i in items]
    return design


def _clustered(bench, cells):
    """ALFWorld's readouts are room-clustered (§6.4): its cells must carry their rooms."""
    if bench == "alfworld":
        require(all(v.get("room") is not None for v in cells.values()), "ALFWorld test cells carry their rooms")


# ------------------------------------------------------------------------------------------------- estimates
def _t_quantile(q, df):
    """The upper ``q`` quantile of Student's t (bisection on ``stats_ext.t_upper``)."""
    low, high = 0.0, 1e3
    for _ in range(200):
        mid = (low + high) / 2
        if stats_ext.t_upper(mid, df) > q:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _p_above(test, shift):
    """One-sided p of mean > ``shift`` from a ``paired_t`` result."""
    if test["se"] == 0:
        return 0.0 if test["mean"] > shift else 1.0
    return stats_ext.t_upper((test["mean"] - shift) / test["se"], test["df"])


def _p_below(test, shift):
    if test["se"] == 0:
        return 0.0 if test["mean"] < shift else 1.0
    return stats_ext.t_upper((shift - test["mean"]) / test["se"], test["df"])


def estimate(d, *, design=None, bootstrap=False, sensitivity=False):
    """A contrast's paired-t description: n, mean, se, df, the one-sided p (greater), the two-sided 95 % t interval
    and the one-sided 95 % bounds (``design``: strata and, on ALFWorld, room clusters); with ``bootstrap`` the
    bootstrap interval beside it, with ``sensitivity`` (Q1's registered sensitivity analyses) the sign-flip and
    Wilcoxon p, which never decide."""
    require(len(d) >= 2, "A contrast needs two or more items")
    design = design or {}
    test = stats_ext.paired_t(d, **design)
    two, one = _t_quantile(LEVEL, test["df"]), _t_quantile(ALPHA, test["df"])
    out = {"n": len(d), "mean": test["mean"], "se": test["se"], "df": test["df"], "p_t": test["p"],
           "ci95": [test["mean"] - two * test["se"], test["mean"] + two * test["se"]],
           "lower95_one_sided": test["mean"] - one * test["se"], "upper95_one_sided": test["mean"] + one * test["se"]}
    if "clusters" in design:
        out["rooms"] = len(set(design["clusters"]))
    if bootstrap:
        out["bootstrap_ci95"] = list(stats_ext.bootstrap_ci(d, **design))
    if sensitivity:
        out["sensitivity"] = {"p_signflip": stats_ext.signflip(d, **design), "p_wilcoxon": stats_ext.wilcoxon(d)}
    return out


def _contrast(cells, first, second, items, **options):
    return estimate(differences(cells, first, second, items), design=_design(cells, items), **options)


def enable_rate(cells, procedure=None, *, arm="F"):
    """The share of the bench's items on which F enables ``procedure`` (any procedure when None)."""
    rows = [v for (label, _, _), v in cells.items() if label == arm]
    require(rows, "The bench has F cells")
    hit = [bool(v["enabled"]) if procedure is None else procedure in v["enabled"] for v in rows]
    return sum(hit) / len(hit)


# ----------------------------------------------------------------------------------------------- Q1, Q2, Q3
def q1_home(units, learned, *, arm="F"):
    """Q1: F − C on each learned bench, one-sided paired t, Holm over |L|."""
    require(learned and set(learned) <= set(units), "Q1 reads the learned benches")
    out = {}
    for bench in learned:
        cells = units[bench]
        _clustered(bench, cells)
        out[bench] = _contrast(cells, arm, "C", _items(cells, arm, "C"), bootstrap=True, sensitivity=True)
    adjusted = stats_ext.holm([out[b]["p_t"] for b in learned])
    for bench, p in zip(learned, adjusted):
        out[bench].update(p_holm=p, established=p <= ALPHA)
    return out


def similar(learned, configuration=None):
    """The benches similar to a learned one (``SIMILAR_PAIRS``), outside L."""
    found = {b for pair in profiles.similar_pairs(configuration) for a, b in (pair, pair[::-1]) if a in learned}
    return sorted(found - set(learned), key=SUPPORTED_BENCHES.index)


def dissimilar(learned, configuration=None):
    if set(learned) == {"zebralogic"} and not profiles.is_v214(configuration):
        return []
    roster = read_benches(configuration) if profiles.is_v214(configuration) else BENCHES
    return [b for b in roster if b not in learned and b not in similar(learned, configuration)]


def q2_similar(units, learned, procedures, *, arm="F", configuration=None):
    """Q2: description only on the similar benches -- F − C, the enable rate and each procedure's τ."""
    out = {}
    for bench in similar(learned, configuration):
        if bench not in units:
            continue
        cells = units[bench]
        _clustered(bench, cells)
        out[bench] = {"reading": "descriptive", **_contrast(cells, arm, "C", _items(cells, arm, "C"), bootstrap=True),
                      "enable_rate": enable_rate(cells, arm=arm), "tau": {p: tau(cells, p) for p in procedures}}
    return out


def _pooled(parts):
    """The equal-weight mean of per-bench estimates with its Satterthwaite df and one-sided 95 % lower bound."""
    k = len(parts)
    mean = sum(p["mean"] for p in parts) / k
    variance = sum(p["se"] ** 2 for p in parts) / k ** 2
    se = variance ** 0.5
    if se == 0:
        return {"mean": mean, "se": 0.0, "lower95_one_sided": mean}
    df = (sum(p["se"] ** 2 for p in parts) ** 2) / sum(p["se"] ** 4 / p["df"] for p in parts if p["se"] > 0)
    return {"mean": mean, "se": se, "df": df, "lower95_one_sided": mean - _t_quantile(ALPHA, df) * se}


def q3_noninferiority(units, learned, *, arm="F", configuration=None):
    """Q3: the dissimilar benches' pooled F − C against −5 points under the complete-case and the adverse readings."""
    benches = [b for b in dissimilar(learned, configuration) if b in units]
    require(benches, "Q3 needs a dissimilar bench in the read")
    fired = [v for b in benches for (label, _, _), v in units[b].items() if label == arm]
    rate = sum(bool(v["enabled"]) for v in fired) / len(fired)
    extra = ({"per_bench": {b: _bench_noninferiority(b, units[b], arm) for b in benches},
              "margin": -float(NI_MARGIN)} if profiles.is_v214(configuration) else {})
    if rate < NI_MIN_FIRED:
        return {"benches": benches, "enable_rate": rate, "reading": "cannot_act_by_construction", **extra}
    readings = {}
    for name in ("adverse", "complete_case"):
        parts = []
        for bench in benches:
            cells = units[bench]
            _clustered(bench, cells)
            items = _items(cells, arm, "C")
            if name == "complete_case":
                items = _known(cells, items, arm, "C")
            parts.append(_contrast(cells, arm, "C", items))
        readings[name] = _pooled(parts)
    holds = all(r["lower95_one_sided"] > -float(NI_MARGIN) for r in readings.values())
    return {"benches": benches, "enable_rate": rate, "margin": -float(NI_MARGIN), **readings,
            "shared_unanswered": {b: len(unanswered(units[b])) for b in benches},
            "reading": "noninferiority_established" if holds else "noninferiority_not_established", **extra}


def _bench_noninferiority(bench, cells, arm):
    """The registered adverse/complete-case NI test for one unrelated bench of a main-v5 row."""
    _clustered(bench, cells)
    rate = enable_rate(cells, arm=arm)
    out = {"enable_rate": rate, "margin": -float(NI_MARGIN)}
    if rate < NI_MIN_FIRED:
        items = _items(cells, arm, "C")
        values = differences(cells, arm, "C", items)
        return {**out, "n": len(items), "mean": float(sum(values) / len(values)) if values else None,
                "reading": "cannot_act_by_construction"}
    for name in ("adverse", "complete_case"):
        items = _items(cells, arm, "C")
        if name == "complete_case":
            items = _known(cells, items, arm, "C")
        out[name] = _contrast(cells, arm, "C", items)
    holds = all(out[name]["lower95_one_sided"] > -float(NI_MARGIN) for name in ("adverse", "complete_case"))
    return {**out, "reading": "noninferiority_established" if holds else "noninferiority_not_established"}


# ------------------------------------------------------------------------------------------- code vs text
def code_vs_text(units, learned):
    """F − T_F per bench with the interval readings of §8.2 (Codex F20); the rest "inconclusive"; below the Q3
    enable threshold "cannot_act_by_construction" (the two arms differ only where F is enabled)."""
    out = {}
    for bench in sorted(units, key=SUPPORTED_BENCHES.index):
        cells = units[bench]
        _clustered(bench, cells)
        items = _items(cells, "F", "T_F")
        rate = enable_rate(cells)
        if len(items) < 2:
            out[bench] = {"n": len(items), "enable_rate": rate, "readings": ["inconclusive"]}
            continue
        found = _contrast(cells, "F", "T_F", items, bootstrap=True)
        readings = []
        if rate < NI_MIN_FIRED:
            readings.append("cannot_act_by_construction")
        else:
            if found["ci95"][0] > 0:
                readings.append("code_better")
            if found["ci95"][1] < 0:
                readings.append("text_better")
            if bench not in learned:
                if found["lower95_one_sided"] > -float(NI_MARGIN):
                    readings.append("code_transfer_not_worse")
                if found["upper95_one_sided"] < float(NI_MARGIN):
                    readings.append("text_transfer_not_worse")
        out[bench] = {**found, "enable_rate": rate, "estimand": "difference_of_the_two_implementations",
                      "readings": readings or ["inconclusive"]}
    return out


def placebo_contrast(units):
    """F − P_F per bench, description only (§8.1's sham arm of the read)."""
    out = {}
    for bench in sorted(units, key=SUPPORTED_BENCHES.index):
        cells = units[bench]
        _clustered(bench, cells)
        items = _items(cells, "F", "P_F")
        out[bench] = {"n": len(items), "reading": "descriptive",
                      **(_contrast(cells, "F", "P_F", items) if len(items) >= 2 else {})}
    return out


# ---------------------------------------------------------------------------------------- procedures (τ, labels)
def _tau(cells, procedure):
    """(τ_p's description, its estimate or None) on one bench."""
    items = _items(cells, "F", TWIN + procedure)
    if len(items) < 2:
        return {"n": len(items), "tau": None}, None
    found = _contrast(cells, "F", TWIN + procedure, items)
    return {"n": len(items), "tau": found["mean"], "se": found["se"], "df": found["df"], "ci95": found["ci95"]}, found


def tau(cells, procedure):
    """τ_p on one bench: the mean over p's twin items of [F − F∖p] (both on L); None without two twin items."""
    return _tau(cells, procedure)[0]


def _statements(tests):
    """{statement: {(procedure, bench): bool}}: "positive" (lower > 0), "negative" (upper < 0) and "noninferior"
    (lower > −5 points), each a one-sided p at 2.5 % after Holm over the whole family."""
    family = sorted(tests)
    tests_of = {"positive": lambda t: _p_above(t, 0.0), "negative": lambda t: _p_below(t, 0.0),
                "noninferior": lambda t: _p_above(t, -float(NI_MARGIN))}
    out = {}
    for name, p_of in tests_of.items():
        adjusted = stats_ext.holm([p_of(tests[key]) for key in family]) if family else []
        out[name] = {key: p <= LEVEL for key, p in zip(family, adjusted)}
    return out


def labels(units, procedures):
    """{procedure: {"label", "descriptors", "tau", "enable_rate"}} (§8.2, Codex F21). ``procedures``: {id: home
    bench}. The τ statements are Holm-adjusted over every (procedure, bench) pair with two or more twin items
    (``_statements``); the primary label is the first holding descriptor in ``PRIORITY``, the others are listed."""
    taus, tests = {}, {}
    for p in procedures:
        taus[p] = {}
        for bench in units:
            _clustered(bench, units[bench])
            taus[p][bench], found = _tau(units[bench], p)
            if found is not None:
                tests[(p, bench)] = found
    statements = _statements(tests)
    out = {}
    for p, home in procedures.items():
        others = [b for b in units if b != home]
        rates = {b: enable_rate(units[b], p) for b in units}
        positive = {b for b in units if statements["positive"].get((p, b), False)}
        negative = {b for b in units if statements["negative"].get((p, b), False)}
        noninferior = {b for b in units if statements["noninferior"].get((p, b), False)}
        found = {
            "harmful_elsewhere": bool(negative & set(others)),
            "general": bool(positive & set(others)) and all(b in positive | noninferior for b in units
                                                             if rates[b] > 0),
            "home_benefit_established": home in positive,
            "cannot_act_elsewhere": bool(others) and all(rates[b] < float(CANNOT_ACT_FIRED) for b in others),
        }
        found["no_measurable_effect"] = not any(found.values())
        descriptors = [name for name in PRIORITY if found[name]]
        out[p] = {"label": descriptors[0], "descriptors": descriptors, "tau": taus[p], "enable_rate": rates}
    return out


def format_withholding(units, procedures):
    """{procedure: {bench: {"n", "violations_with", "violations_without"}}}: J4's format violations of F and of F∖p
    on p's twin items (an unknown cell's violation is None and not counted)."""
    out = {}
    for p in procedures:
        out[p] = {}
        for bench, cells in units.items():
            items = {i for (arm, i, _) in cells if arm == TWIN + p}
            if not items:
                continue
            violations = {arm: sum(bool(v["format"].get("violation")) for (a, i, _), v in cells.items()
                                   if a == arm and i in items) for arm in ("F", TWIN + p)}
            out[p][bench] = {"n": len(items), "violations_with": violations["F"],
                             "violations_without": violations[TWIN + p]}
    return out


# ------------------------------------------------------------------------------------------ the §8.3 arm table
def _seconds(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return datetime.fromisoformat(value).timestamp()


def _share(rows, test):
    return sum(bool(test(v)) for v in rows) / len(rows) if rows else None


def _reply_tokens(value):
    """A cell's completion tokens for the short answer (registrar decision fixer-2 on §8.3): the mean visible
    completion tokens of its logical calls, i.e. its reply's count on a one-call cell, so the number of calls (an
    ALFWorld episode's steps, a ``<calc>`` second call, a repair call, a restarted episode) stays out of it. None -- a
    cell without usage -- when the cell made no call or one of its calls carries no count."""
    tokens = value.get("completion_tokens") or []
    if not tokens or not all(type(t) is int and t >= 0 for t in tokens):
        return None
    return Fraction(sum(tokens), len(tokens))


def _median(values):
    ordered = sorted(values)
    half = len(ordered) // 2
    return ordered[half] if len(ordered) % 2 else (ordered[half - 1] + ordered[half]) / 2


def _reference(first):
    """One arm's short-answer reference (registrar decision fixer-2): the median completion tokens of its cells with
    usage in the unit's first window ``first``. Returns ({"window": 0, "cells", "no_usage", "median", "status"}, the
    median when it defines short answers, else None). Without such a cell ("no_cell_with_usage") or with a zero median
    ("zero_median": a quarter of 0 marks no cell) the arm has no short-answer share in any window -- no constant and no
    later window stands in."""
    measured = [t for t in map(_reply_tokens, first) if t is not None]
    median = _median(measured) if measured else None
    status = "no_cell_with_usage" if median is None else "zero_median" if median == 0 else "defined"
    return ({"window": 0, "cells": len(measured), "no_usage": len(first) - len(measured),
             "median": None if median is None else float(median), "status": status},
            median if status == "defined" else None)


def _windows(rows, start):
    """§6.2, §8.3: per 15-minute window of dispatch (from the unit's first dispatch; one unit per bench, §8.1), the
    cells that sent requests, their answer-tag share (None on a bench without an answer tag -- SpreadsheetBench and
    ALFWorld formats carry no ``tag_present``, ``judge._format`` -- not a false 0.0; ticket P2-A2-1), their mean
    visible completion tokens (over calls) and their short-answer share: the share of the window's cells with usage
    whose completion tokens (``_reply_tokens``) are below a quarter of the arm's reference median (``_reference``),
    ``no_usage`` counting the cells left out; None without a reference or without a cell with usage. Shared cells sent
    nothing and are left out. Returns (the reference, the windows)."""
    found = {}
    for value in rows:
        if value["shared_with"] is None and value.get("dispatch_ts") is not None:
            found.setdefault(int((_seconds(value["dispatch_ts"]) - start) // TIME_WINDOW_SECONDS), []).append(value)
    reference, median = _reference(found.get(0, []))
    out = []
    for window, members in sorted(found.items()):
        tokens = [t for v in members for t in v.get("completion_tokens") or [] if type(t) is int]
        measured = [t for t in map(_reply_tokens, members) if t is not None]
        out.append({"window": window, "cells": len(members),
                    "answer_tag_share": (_share(members, lambda v: v["format"].get("tag_present"))
                                         if any("tag_present" in v["format"] for v in members) else None),
                    "mean_completion_tokens": sum(tokens) / len(tokens) if tokens else None,
                    "short_answer_share": None if median is None else _share(measured,
                                                                             lambda t: t < SHORT_ANSWER * median),
                    "no_usage": len(members) - len(measured)})
    return reference, out


windows = _windows  # the public name of the fixer-2 series (``acceptance.series``; ticket P2-A2-1)


def arm_table(cells):
    """§8.3 per arm of one bench: the accuracies (v2 the main reading, official, official completion, lenient), the
    unknown counts, the cell and format flags, the procedure faults, the enable rate, the short-answer reference and
    the 15-minute series (``_windows``)."""
    stamps = [_seconds(v["dispatch_ts"]) for v in cells.values() if v.get("dispatch_ts") is not None]
    start = min(stamps) if stamps else 0.0
    out = {}
    for arm in sorted({a for (a, _, _) in cells}):
        rows = [v for (a, _, _), v in cells.items() if a == arm]
        reference, windows = _windows(rows, start)
        out[arm] = {
            "period": PERIOD, "cells": len(rows), "shared": sum(v["shared_with"] is not None for v in rows),
            "v2": _share(rows, lambda v: v["v2"] == "pass"),
            "official": _share(rows, lambda v: v.get("official") == "pass"),
            "official_completion": _share(rows, lambda v: v.get("final") == "pass"),
            "lenient": _share(rows, lambda v: v.get("lenient") is True),
            "unknown": dict(sorted(Counter(v["v2"] for v in rows if v["v2"] in UNKNOWN).items())),
            "flags": dict(sorted(Counter(f for v in rows for f in v.get("flags") or []).items())),
            "format": dict(sorted(Counter(k for v in rows for k, x in (v.get("format") or {}).items()
                                          if x is True).items())),
            "fault_cells": sum(bool(v.get("fault_kinds")) for v in rows),
            "faults": dict(sorted(sum((Counter(v.get("fault_kinds") or {}) for v in rows), Counter()).items())),
            "enable_rate": _share(rows, lambda v: v["enabled"]),
            "short_answer_reference": reference, "windows": windows}
    return out


# ------------------------------------------------------------------------------------------ v2 stage table
def _accuracy(cells, arm, items, on):
    """The arm's mean score on side ``on`` over ``items`` (each item's mean over its runs)."""
    values = [sum(Fraction(_score(cells[(arm, i, r)]["v2"], on)) for r in _runs(cells, arm, i)) / len(_runs(cells, arm, i))
              for i in items]
    return float(sum(values) / len(values)) if values else None


def stage_table(units, rows, *, configuration=None):
    """v2 stage reads (owner decision 2026-10-23 16:0x): {bench: [row k: {"k", "arm", "n", "accuracy": {"L", "H"},
    "minus_card", "minus_previous"}]} -- ``rows`` the arm of each row (row 0 C; ``evaluation.stage_rows``), the items
    those arms all have cells on with the §6.3 mask removed, the paired contrasts on each arm's §6.3 side (a run on
    which both arms read the same cell adds 0; "minus_previous" absent where the row reads the previous row's arm).
    Description only: no test, no correction, no decision."""
    require(isinstance(rows, list) and rows and rows[0] == "C", "The stage table's rows start with the card arm")
    out = {}
    for bench in sorted(units, key=SUPPORTED_BENCHES.index):
        cells = units[bench]
        _clustered(bench, cells)
        items = _items(cells, *sorted(set(rows)))
        entries = []
        for k, arm in enumerate(rows):
            entry = {"k": k, "arm": arm, "n": len(items),
                     "accuracy": {on: _accuracy(cells, arm, items, on) for on in ("L", "H")}}
            if profiles.is_v214(configuration) and arm == "C":
                entry["minus_card"] = {"mean": 0.0, "reading": "no program accepted at this step"}
            if arm != "C" and len(items) >= 2:
                entry["minus_card"] = _contrast(cells, arm, "C", items, bootstrap=True)
            if k and rows[k - 1] != arm and len(items) >= 2:
                entry["minus_previous"] = _contrast(cells, arm, rows[k - 1], items, bootstrap=True)
            entries.append(entry)
        out[bench] = entries
    return out


def stage_questions(units, rows, *, configuration):
    """The owner's three questions on every frozen package, relative to C and the step's home benchmark."""
    order = profiles.CONFIGURATIONS[configuration]["order"]
    require(profiles.is_v214(configuration) and len(rows) == len(order) + 1 and rows[0] == "C"
            and set(units) == set(read_benches(configuration)),
            "main-v5 reports every step on every benchmark")
    out = []
    for k, home in enumerate(order, 1):
        arm = rows[k]
        related = [b for b in similar([home], configuration) if b in units]
        unrelated = [b for b in dissimilar([home], configuration) if b in units]
        entry = {"k": k, "arm": arm, "home_bench": home,
                 "related_benches": related, "unrelated_benches": unrelated,
                 "reuses_row": rows.index(arm) if arm in rows[:k] else None}
        if arm == "C":
            zero = {"mean": 0.0, "reading": "no program accepted at this step"}
            entry.update(q1_home={home: dict(zero)}, q2_similar={b: dict(zero) for b in related},
                         q3_noninferiority={**zero, "benches": unrelated, "margin": -float(NI_MARGIN),
                                           "per_bench": {b: {**zero, "margin": -float(NI_MARGIN)}
                                                         for b in unrelated}})
        else:
            entry.update(q1_home=q1_home(units, [home], arm=arm),
                         q2_similar=q2_similar(units, [home], {}, arm=arm, configuration=configuration),
                         q3_noninferiority=q3_noninferiority(units, [home], arm=arm, configuration=configuration))
        out.append(entry)
    return out


# ---------------------------------------------------------------------------------------------- the readout
def readout(units, *, learned, procedures, label, evidence, stages=None, configuration=None):
    """The sealed readout record (``fivebench-execskill-v1-readout``) of one chain's unsealed read; ``label``: the
    unseal's read label (Codex F17); ``stages``: a stage read's rows (``stage_table``; F's readings are left out,
    None, only where F learned nothing and the stage arms carry the read)."""
    from . import profiles
    if profiles.is_v210(configuration) or profiles.is_zebra_fc(configuration):
        main_v5 = profiles.is_v214(configuration)
        if main_v5:
            require(stages is not None, "main-v5 readout includes the frozen stage rows")
        contrasts = {}
        baseline = configuration == profiles.BASELINE_V210
        zebra = profiles.is_zebra_fc(configuration)
        implanted = profiles.is_implant_v5(configuration)
        hand_picked = profiles.is_v213(configuration) or implanted
        if hand_picked:
            require(not learned, "A post-hoc import has no newly learned benchmarks")
        imported = [ZEBRA, "alfworld"] if implanted else [ZEBRA] if hand_picked else [] if baseline or zebra else ["alfworld"]
        # Imported programs are not newly learned here, and their home bench is
        # not an unexposed transfer target. Its F-C remains measured below.
        exposed = [bench for bench in (read_benches(configuration) if main_v5 else SUPPORTED_BENCHES if zebra else BENCHES)
                   if bench in set(learned) | set(imported)]
        pairs = (("F", "C"),) if zebra else (("C", "B"),) if baseline else (("F", "C"), ("C", "B"), ("F", "B"))
        for bench in sorted(units, key=SUPPORTED_BENCHES.index):
            cells = units[bench]
            expected = ({"F", "C", "B", *stages} if main_v5 else set(profiles.read_arms_of(configuration)))
            require({arm for arm, _, _ in cells} == expected,
                    "v2.10 readout arms must match the configuration")
            _clustered(bench, cells)
            contrasts[bench] = {first + "-" + second: _contrast(
                cells, first, second, _items(cells, first, second), bootstrap=True, sensitivity=True)
                for first, second in pairs}
        return record("readout", evidence, {
            "configuration": configuration, "evidence_kind": ("post_hoc_selected_upper_bound" if hand_picked else
                             "pipeline_control" if zebra else EVIDENCE_KIND), "read_label": label,
            "learned": list(learned), "imported": imported,
            "contrasts": contrasts, "contrasts_reading": "descriptive",
            **({"reading": "descriptive"} if baseline else {
                "similar": similar(exposed, configuration), "dissimilar": dissimilar(exposed, configuration),
                "q1_home": q1_home(units, learned) if learned else None,
                "q2_similar": q2_similar(units, exposed, procedures, configuration=configuration),
                "q3_noninferiority": q3_noninferiority(units, exposed, configuration=configuration)
                    if any(bench in units for bench in dissimilar(exposed, configuration)) else None}),
            "shared_unanswered": {bench: len(unanswered(cells)) for bench, cells in units.items()},
            "arms": {bench: arm_table(cells) for bench, cells in units.items()},
            "placebo": {"removed": True}, "code_vs_text": {"removed": True}, "twins": {"removed": True},
            **({"stages": stage_table(units, stages, configuration=configuration),
                "stage_questions": stage_questions(units, stages, configuration=configuration)} if main_v5 else {})})
    return record("readout", evidence, {
        "evidence_kind": "pipeline_control" if set(units) == {ZEBRA} else EVIDENCE_KIND,
        "read_label": label, "learned": list(learned),
        "similar": similar(learned), "dissimilar": dissimilar(learned),
        "shared_unanswered": {b: len(unanswered(units[b])) for b in sorted(units, key=SUPPORTED_BENCHES.index)},
        "q1_home": q1_home(units, learned) if learned or not stages else None,
        "q2_similar": q2_similar(units, learned, procedures),
        "q3_noninferiority": q3_noninferiority(units, learned) if [b for b in dissimilar(learned) if b in units]
        else None,
        "code_vs_text": code_vs_text(units, learned), "placebo": placebo_contrast(units),
        "labels": labels(units, procedures), "format_withholding": format_withholding(units, procedures),
        "arms": {b: arm_table(units[b]) for b in sorted(units, key=SUPPORTED_BENCHES.index)},
        **({"stages": stage_table(units, stages)} if stages else {})})


def report(manifest, *, out):
    """``run_execskill.py report --manifest M --out NEWDIR``: one readout per chain of the manifest's run root that
    read the test sets (``test-read.json`` status "read"), written once as ``<out>/readout-<chain>.json``; a chain that
    read nothing (F = C) or was terminated before its read is listed as such, and one that has neither read nor ended
    is refused. ``evaluation.unseal`` refuses before every chain has ended and the owner's continuation file exists;
    nothing is written after a refusal. Returns {chain: the readout's record hash, or "not_read"}."""
    from . import profiles
    out = safe_path(out)
    require(not out.exists(), "The readout goes to a new directory")
    root, run, evidence = safe_path(manifest["root"]), manifest[RECORD_HASH], manifest["evidence"]
    found, written = {}, {}
    chains = (manifest["data"].get("launchable_chains", CHAINS)
              if is_zebra(manifest["configuration"]) or is_alfworld(manifest["configuration"]) else CHAINS)
    for chain in sorted(chains):
        chain_root = root / chain
        if not (chain_root / "test-read.json").exists():  # terminated before its read
            require((chain_root / "chain-terminated.json").exists(), "Chain %s has neither read nor ended" % chain)
            found[chain] = "not_read"
            continue
        read = verified(read_json(chain_root / "test-read.json"), "test-read")
        if read["status"] != "read":
            found[chain] = "not_read"
            continue
        start = empty(step="%s/s0" % chain, evidence=evidence)  # a stage read whose F is the empty start
        final = start if read["package_sha256"] == start.sha256 else load(
            chain_root / "packages" / (read["package_sha256"] + ".json"))
        procedures = {p.id: p.origin for p in final.procedures}
        roster = read_benches(manifest["configuration"])
        learned = [b for b in roster if b in procedures.values()
                   and not profiles.is_v213(manifest["configuration"])
                   and not profiles.is_implant_v5(manifest["configuration"])
                   and not (manifest["configuration"] in (profiles.MAIN_V3, profiles.MAIN_V4, profiles.MAIN_V5)
                            and b == "alfworld")]
        units = [chain_root / "test" / b for b in roster if (chain_root / "test" / b / "unit.json").exists()]
        opened = evaluation.unseal(root, chain_root, chain, units, run=run, evidence=evidence,
                                   **({"configuration": manifest["configuration"]}
                                      if is_zebra(manifest["configuration"]) or is_alfworld(manifest["configuration"])
                                      or profiles.is_v210(manifest["configuration"]) else {}))
        rows = {tuple(found) for found in (opened.get("stages") or {}).values()}
        require(len(rows) <= 1 and (not rows or set(opened["stages"]) == set(opened["units"])),
                "Every read unit of a stage read names the same rows")
        value = readout(opened["units"], learned=learned, procedures=procedures, label=opened["label"],
                        evidence=evidence, stages=list(rows.pop()) if rows else None,
                        **({"configuration": manifest["configuration"]}
                           if profiles.is_v210(manifest["configuration"]) or profiles.is_zebra_fc(manifest["configuration"]) else {}))
        written[chain], found[chain] = value, value[RECORD_HASH]
    out.mkdir(parents=True)
    for chain, value in written.items():
        write_json(out / ("readout-%s.json" % chain), value)
    return found
