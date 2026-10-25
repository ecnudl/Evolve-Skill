"""The examiner's predictive validity of a generator (protocol ``fivebench-execskill-v1``; registration §7.2
"预测效度" rewritten after Codex F9, §3.2 seeds, §3.3 G_acc; implementation plan §1 validity.py, T-VAL-1..4).

The evidence unit is ONE acceptance round: ``round_pair`` takes a single pair (d_gen, d_real) = S' - S on the round's
generated items (G_acc, one run each, made by the frozen generator on the A* public views) and on its real A* items,
with both standard errors and their within-round covariance (the G_acc item of each A* item pairs the two, so the two
means are not independent). The other contrasts of a round share its cells and are never counted as further evidence.
The negative control is the registered duplicate arm pair (``dup_control``: two arms with the same package, S and C
while S has no procedure on the bench, later S and S_dup), whose differences should be zero on both item sets.

``status`` reads a generator's rounds with the precedence refuted > validated > not_evaluable:
- refuted: >= 8 rounds and [>= 2 rounds with |d_gen - d_real| > 2 sqrt(se_gen^2 + se_real^2 - 2 cov), or the
  duplicate pair's 95 % interval on the generated items excludes 0];
- validated: >= 8 rounds, not refuted, Spearman's rho of (d_gen, d_real) over rounds > 0 with a one-sided permutation p
  < 0.05 (``stats_ext.spearman_perm``: 10,000 permutations over rounds, seed 20261021), and the duplicate pair's 95 %
  intervals contain 0 on both item sets;
- otherwise not_evaluable. With fewer than 8 rounds the status is not_evaluable whatever the disagreement; the pilot
  (one round per bench) therefore cannot evaluate validity.
Only rounds with both numbers count (a round that did not run, or ran without G_acc, gives none).

v2.3 (Codex review finding 5, coordinator fix request 2026-10-25): expand the round's sealed shared cells before
reading either set, and keep each set's ``identical_all`` items as exact-zero differences. These unmeasured
unchanged items retain their denominators and the real/generated covariance pairing; no accuracy is invented.
Duplicate controls retain their existing item-set scope, including the added exact zeros. Rounds without a reuse
plan follow the historical path and return the same fields and values.
"""
from __future__ import annotations

import math

from skillopt.continual_eval.core import require

from . import acceptance, stats_ext
from .protocol import (SEED, VALIDITY_ALPHA, VALIDITY_MIN_DISAGREEMENTS, VALIDITY_MIN_ROUNDS, VALIDITY_PERMUTATIONS,
                       VALIDITY_SE_MULTIPLE, verified)


def _mean_se(d):
    """(mean, se) of per-item differences; se 0 for a single item."""
    mean = sum(d) / len(d)
    if len(d) < 2:
        return float(mean), 0.0
    variance = sum((x - mean) ** 2 for x in d) / (len(d) - 1)
    return float(mean), math.sqrt(variance / len(d))


def round_pair(cells, sealed):
    """``{"d_gen", "d_real", "se_gen", "se_real", "cov", "n_gen", "n_real"}`` of one acceptance round (S' - S on the
    G_acc items and on the answered A* items), or None when the round has no G_acc pair. ``cov`` estimates the
    covariance of the two means from the A* items that have a generated item: n_both x s_gr / (n_gen x n_real)."""
    sealed = verified(sealed, "acceptance-sealed")
    if sealed["plan"]["decision"] == acceptance.SMALL or not sealed["g_acc"]:
        return None
    physical = cells
    identical = (sealed.get("reuse") or {}).get("identical_all", {})
    if sealed.get("reuse") is not None:
        physical = [cell for cell in cells if not cell.get("reused_from")]
        cells = acceptance.expanded_cells(physical, sealed)
    real_table = acceptance.table(cells, identical=identical.get("real", []))
    gen_table = acceptance.table(cells, "G_acc", identical=identical.get("G_acc", []))
    unanswered = set(acceptance.shared_unanswered(physical, sealed["plan"]["astar"]))
    real_items = [i for i in sealed["plan"]["astar"] if i not in unanswered]
    generated = [g for g in sealed["g_acc"]
                 if g["id"] in identical.get("G_acc", [])
                 or (acceptance.CANDIDATE, g["id"]) in gen_table and (acceptance.PARENT, g["id"]) in gen_table]
    if not real_items or not generated:
        return None
    real = dict(zip(real_items, acceptance.differences(real_table, acceptance.CANDIDATE, acceptance.PARENT,
                                                       real_items)))
    gen = dict(zip([g["id"] for g in generated], acceptance.differences(
        gen_table, acceptance.CANDIDATE, acceptance.PARENT, [g["id"] for g in generated])))
    d_real, se_real = _mean_se(list(real.values()))
    d_gen, se_gen = _mean_se(list(gen.values()))
    both = [(gen[g["id"]], real[g["source_item"]]) for g in generated if g["source_item"] in real]
    cov = 0.0
    if len(both) > 1:
        mg, mr = sum(x for x, _ in both) / len(both), sum(y for _, y in both) / len(both)
        s_gr = sum((x - mg) * (y - mr) for x, y in both) / (len(both) - 1)
        cov = float(len(both) * s_gr / (len(gen) * len(real)))
    return {"d_gen": d_gen, "d_real": d_real, "se_gen": se_gen, "se_real": se_real, "cov": cov,
            "n_gen": len(gen), "n_real": len(real)}


def dup_control(cells, sealed):
    """``{"pair", "gen_ci95", "real_ci95"}``: the 95 % bootstrap intervals of the registered duplicate pair's
    differences on the generated and on the real items (seed 20261021); None when the round has no such pair or no
    generated items."""
    sealed = verified(sealed, "acceptance-sealed")
    if sealed["dup"]:
        first, second = acceptance.DUP, acceptance.PARENT
    elif sealed["card_is_parent"]:
        first, second = acceptance.CARD, acceptance.PARENT
    else:
        return None
    identical = (sealed.get("reuse") or {}).get("identical_all", {})
    if sealed.get("reuse") is not None:
        cells = acceptance.expanded_cells([cell for cell in cells if not cell.get("reused_from")], sealed)
    out = {"pair": "%s-%s" % (first, second)}
    for name, cell_set in (("gen_ci95", "G_acc"), ("real_ci95", "real")):
        eligible = set(sealed["plan"]["astar"] if cell_set == "real" else [g["id"] for g in sealed["g_acc"] or []])
        unchanged = set(identical.get(cell_set, [])) & eligible
        found = acceptance.table(cells, cell_set, identical=unchanged)
        items = sorted(({i for (a, i) in found if a == first} & {i for (a, i) in found if a == second})
                       | unchanged)
        if not items:
            return None
        d = acceptance.differences(found, first, second, items)
        out[name] = list(stats_ext.bootstrap_ci(d))
    return out


def _covers_zero(interval):
    return interval[0] <= 0 <= interval[1]


def disagrees(pair):
    """|d_gen - d_real| > 2 sqrt(se_gen^2 + se_real^2 - 2 cov) (the pooled SE floored at 0)."""
    pooled = math.sqrt(max(0.0, pair["se_gen"] ** 2 + pair["se_real"] ** 2 - 2 * pair["cov"]))
    return abs(pair["d_gen"] - pair["d_real"]) > VALIDITY_SE_MULTIPLE * pooled


def status(rounds, dup=None):
    """The generator's validity record (module docstring). ``rounds``: its rounds' ``round_pair`` values (None for a
    round without a pair); ``dup``: its ``dup_control`` (None when no duplicate pair ran)."""
    pairs = [r for r in rounds if r is not None]
    for pair in pairs:
        require(all(type(pair.get(k)) in (int, float) for k in ("d_gen", "d_real", "se_gen", "se_real", "cov")),
                "A round pair holds d_gen, d_real, se_gen, se_real and cov")
    disagreements = sum(disagrees(p) for p in pairs)
    out = {"rounds": len(pairs), "disagreements": disagreements, "rho": None, "p_perm": None, "dup": dup}
    if len(pairs) < VALIDITY_MIN_ROUNDS:
        return {**out, "status": "not_evaluable", "reason": "fewer than %d rounds" % VALIDITY_MIN_ROUNDS}
    dup_gen_excludes = dup is not None and not _covers_zero(dup["gen_ci95"])
    if disagreements >= VALIDITY_MIN_DISAGREEMENTS or dup_gen_excludes:
        reason = ("%d rounds disagree" % disagreements if disagreements >= VALIDITY_MIN_DISAGREEMENTS
                  else "the duplicate pair's generated-item interval excludes 0")
        return {**out, "status": "refuted", "reason": reason}
    rho, p = stats_ext.spearman_perm([r["d_gen"] for r in pairs], [r["d_real"] for r in pairs],
                                     n=VALIDITY_PERMUTATIONS, seed=SEED)
    out.update(rho=rho, p_perm=p)
    dup_clean = dup is not None and _covers_zero(dup["gen_ci95"]) and _covers_zero(dup["real_ci95"])
    if rho is not None and rho > 0 and p < VALIDITY_ALPHA and dup_clean:
        return {**out, "status": "validated", "reason": "rank agreement over rounds, duplicate pair clean"}
    return {**out, "status": "not_evaluable",
            "reason": "no duplicate pair" if dup is None else "no significant rank agreement or duplicate not clean"}
