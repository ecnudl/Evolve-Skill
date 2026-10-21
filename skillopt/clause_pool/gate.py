"""The pre-registered clause gate (design docs/handoff/two-architectures-design-20261016.md section 6; zero calls).

Pure computation over measurements: per (Skill, item) the statuses of independent runs. An item's rate is its mean
pass over its known runs. For an edit with tags T on the REGISTERED gate items G: S = registered items matching T (all
of G for a generic edit); thresholds use the registered sizes |S| and |G|; the deltas Δ_trig = Σ_S (p_edit − p_parent)
and Δ_rest = Σ_{G∖S} (p_edit − p_parent) run over the items known for both Skills. When fewer than MIN_COVERAGE of G
are known for both, the edit is pending (never passed).

- noise: σ(n) = sqrt(v · n), v = mean over items of (p_A − p_B)² for the parent measured by two independent probes
  (the second moment: a drift between the probes counts as noise), registered before any edit is measured;
- screen: Δ_trig ≥ max(SCREEN_MIN, σ(|S|)) and Δ_rest ≥ REST_FLOOR; a generic edit: Δ_total ≥ max(GENERIC_MIN, σ(|G|));
- confirm (fresh runs, another probe): Δ_trig > 0 and Δ_rest ≥ REST_FLOOR (generic: Δ_total > 0).

Every decision is exact: rates, v and the deltas are rationals (kept as "p/q" strings in the records, beside values
rounded for display only), and Δ ≥ max(floor, sqrt(v·n)) is decided as Δ ≥ floor and Δ² ≥ v·n.
"""
from __future__ import annotations

import math
from fractions import Fraction

from skillopt.skill_features.tagger import matches

VERSION = "clause-pool-gate-v1"
SCREEN_MIN, REST_FLOOR, GENERIC_MIN, MIN_COVERAGE = Fraction(1), Fraction(-1), Fraction(3, 2), Fraction(9, 10)
KNOWN = ("pass", "fail")
DELTAS = ("delta_trigger", "delta_rest", "delta_total")


def rates(runs, items):
    """{item: mean pass over known runs (exact)} for the items with at least one known run."""
    out = {}
    for item in items:
        known = [s for s in runs.get(item, []) if s in KNOWN]
        if known:
            out[item] = Fraction(sum(s == "pass" for s in known), len(known))
    return out


def _shown(x):
    return round(float(x), 6)


def noise(half_a, half_b, items):
    """v = mean over the items known in both halves of (p_A − p_B)² (exact, as "p/q"); refused below MIN_COVERAGE of
    the items."""
    items = sorted(items)
    a, b = rates(half_a, items), rates(half_b, items)
    common = [i for i in items if i in a and i in b]
    if not items or len(common) < MIN_COVERAGE * len(items):
        raise ValueError("Too few items known in both halves for a noise estimate")
    v = sum(((a[i] - b[i]) ** 2 for i in common), Fraction(0)) / len(common)
    mean = sum((a[i] - b[i] for i in common), Fraction(0)) / len(common)
    return {"version": VERSION, "v": str(v), "v_shown": _shown(v), "n_items": len(items),
            "items_known_in_both": len(common), "mean_difference": _shown(mean)}


def sigma(v, n):
    """σ(n) for display (decisions never use this float)."""
    return math.sqrt(float(Fraction(v) * n))


def measure(edit_tags, item_tags, edit_runs, parent_runs):
    """The deltas of one edit over the registered gate items (the keys of ``item_tags``): exact in ``exact``, rounded
    for display at the top level."""
    items = sorted(item_tags)
    trigger = [i for i in items if matches(item_tags[i], edit_tags)]
    in_trigger = set(trigger)
    pe, p0 = rates(edit_runs, items), rates(parent_runs, items)
    known = {i for i in items if i in pe and i in p0}
    delta = lambda subset: sum((pe[i] - p0[i] for i in subset if i in known), Fraction(0))
    rest = [i for i in items if i not in in_trigger]
    exact = {"delta_trigger": delta(trigger), "delta_rest": delta(rest), "delta_total": delta(items)}
    return {"generic": not edit_tags, "n_items": len(items), "n_trigger": len(trigger), "n_rest": len(rest),
            "known_in_both": len(known), "coverage": _shown(Fraction(len(known), len(items))) if items else 0.0,
            **{k: _shown(x) for k, x in exact.items()}, "exact": {k: str(x) for k, x in exact.items()}}


def exact(m, key):
    return Fraction(m["exact"][key])


def _covered(m):
    return m["n_items"] > 0 and m["known_in_both"] >= MIN_COVERAGE * m["n_items"]


def _at_least(delta, floor, v, n):
    """delta >= max(floor, sqrt(v * n)), decided exactly (floor > 0)."""
    return delta >= floor and delta * delta >= v * n


def screen(m, v):
    """The screen decision for a measurement ``m`` with the registered noise ``v`` (the "p/q" string)."""
    v = Fraction(v)
    if not _covered(m):
        return {"threshold": None, "passed": False, "pending": "insufficient_coverage"}
    if m["generic"]:
        floor, n = GENERIC_MIN, m["n_items"]
        passed = _at_least(exact(m, "delta_total"), floor, v, n)
    else:
        floor, n = SCREEN_MIN, m["n_trigger"]
        passed = (n > 0 and _at_least(exact(m, "delta_trigger"), floor, v, n)
                  and exact(m, "delta_rest") >= REST_FLOOR)
    return {"threshold": _shown(max(float(floor), sigma(v, n))), "passed": passed, "pending": None}


def confirm(m):
    if not _covered(m):
        return {"passed": False, "pending": "insufficient_coverage"}
    if m["generic"]:
        return {"passed": exact(m, "delta_total") > 0, "pending": None}
    return {"passed": m["n_trigger"] > 0 and exact(m, "delta_trigger") > 0 and exact(m, "delta_rest") >= REST_FLOOR,
            "pending": None}
