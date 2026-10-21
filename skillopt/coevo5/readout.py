"""The pre-registered readings (registration §12; v2: delta §9, which retires v1's P1-P4 and their combined claims;
v3: delta §1, the deepseek family with I-ds primary) of a run's evaluation records, once its chains are unsealed.

A reading is a linear combination of test accuracies A[chain][stage][bench] (completion basis, in percentage points),
optionally transformed (the truncated descriptions). Every reading is computed three times on the same resamples
(§12.6): ``known`` -- only the items whose records in the reading are all known, dropped pairwise; ``low`` -- every
unknown record set to the value that lowers the reading; ``high`` -- the opposite. A record shared by several
accuracies (the shared stage 0, a record reused for a byte-identical Skill) has one value, chosen by the sign of its
total coefficient, so it still cancels where it enters a difference. A claim that the reading is large (not worse,
gain, exceeds) must hold on ``known`` and ``low``; a claim that it is small (worse, less forgetting) on ``known`` and
``high``. A transformed reading is computed on the records imputed for its untransformed sum.

Intervals are percentile intervals of 10,000 paired resamples (seed 20261017): within each bench the items -- for
OfficeQA, the groups of items that share a source file -- are drawn with replacement once, and the same draw serves
every chain, stage, reading and variant. A resample in which some bench of a reading keeps no usable item is skipped;
a reading whose original sample has a bench without a usable item, or that needs a unit a chain never evaluated, is
"not assessable".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy

from skillopt.continual_eval.core import require

from .protocol import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, NI_MARGIN, ORDER, similar_targets

KNOWN, LOW, HIGH = "known", "low", "high"
VARIANTS = (KNOWN, LOW, HIGH)
VALUE = {"pass": 1.0, "fail": 0.0, "unknown": math.nan, "unknown_artifact": math.nan}
STAGES = range(len(ORDER) + 1)
DIGITS = 9  # resampled readings are rounded to 1e-9 points; point estimates are exact before rounding


@dataclass(frozen=True)
class Unit:
    """One evaluation unit's records: ``source``, the unit whose cells they are (shared or reused records name the
    same source); ``tokens``: {task id: final token}."""

    source: str
    tokens: dict


@dataclass(frozen=True)
class Panel:
    """One bench's test items, in a fixed order, and the resampling group of each (0..groups-1)."""

    items: tuple
    groups: tuple


def panel(items, groups=None):
    """A ``Panel`` of the task ids ``items``; ``groups``: {task id: [source file, ...]} (OfficeQA) -- items that share
    a file, directly or through other items, are one group; otherwise each item is its own group."""
    items = tuple(sorted(items))
    require(items and len(set(items)) == len(items), "A panel lists distinct items")
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    if groups is not None:
        require(set(groups) == set(items), "Every item has its source files")
        first = {}
        for i, item in enumerate(items):
            for name in groups[item]:
                if name in first:
                    parent[find(i)] = find(first[name])
                else:
                    first[name] = i
    roots, index = {}, []
    for i in range(len(items)):
        index.append(roots.setdefault(find(i), len(roots)))
    return Panel(items, tuple(index))


def accuracy(chain, stage, bench, coefficient=1):
    return {(chain, stage, bench): Fraction(coefficient)}


def combine(*parts, scale=1):
    """The sum of term dicts, times ``scale``."""
    out = {}
    for part in parts:
        for key, value in part.items():
            out[key] = out.get(key, Fraction(0)) + Fraction(scale) * value
    return {k: v for k, v in out.items() if v != 0}


def macro(chain, stage):
    return combine(*[accuracy(chain, stage, b) for b in ORDER], scale=Fraction(1, len(ORDER)))


def difference(a, b):
    return combine(a, combine(b, scale=-1))


def stage_of(bench):
    return ORDER.index(bench) + 1


def gain(chain, bench):  # G_b
    return difference(accuracy(chain, stage_of(bench), bench), accuracy(chain, stage_of(bench) - 1, bench))


def forgetting(chain, bench):  # F_b, signed: positive = worse
    return difference(accuracy(chain, stage_of(bench), bench), accuracy(chain, len(ORDER), bench))


def ahead(chain, bench):  # N_b, signed: positive = better
    return difference(accuracy(chain, stage_of(bench) - 1, bench), accuracy(chain, 0, bench))


def mean_forgetting(chain):
    return combine(*[forgetting(chain, b) for b in ORDER[:-1]], scale=Fraction(1, len(ORDER) - 1))


def mean_ahead(chain):
    return combine(*[ahead(chain, b) for b in ORDER[1:]], scale=Fraction(1, len(ORDER) - 1))


def step_change(chain, stage, bench):  # ΔA[s][b]
    return difference(accuracy(chain, stage, bench), accuracy(chain, stage - 1, bench))


def transfer_cells():
    """§12.8: the 25 step changes (s, b), s = 1..5, by class -- "self", "similar" (checkable similar targets: backward
    and forward) and "rest" (every other cell, including a similar bench the gate cannot check)."""
    cells = {"self": [], "forward": [], "backward": [], "rest": []}
    for s, learned in enumerate(ORDER, 1):
        backward, forward = similar_targets(learned)
        for b in ORDER:
            kind = ("self" if b == learned else "backward" if b in backward else "forward" if b in forward
                    else "rest")
            cells[kind].append((s, b))
    cells["similar"] = sorted(cells["forward"] + cells["backward"])
    return cells


def class_mean(chain, cells):
    return combine(*[step_change(chain, s, b) for s, b in cells], scale=Fraction(1, len(cells)))


class Readings:
    """The readings of one run. ``units``: {(chain, stage, bench): Unit}; ``panels``: {bench: Panel}; every unit holds
    exactly its bench's panel items."""

    def __init__(self, units, panels, *, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
        require(set(panels) == set(ORDER), "A panel for every bench")
        for (_, _, bench), unit in units.items():
            require(set(unit.tokens) == set(panels[bench].items)
                    and all(t in VALUE for t in unit.tokens.values()), "A unit holds its bench's test items")
        self.units, self.panels, self.resamples = units, panels, resamples
        rng = numpy.random.Generator(numpy.random.PCG64(seed))
        self.weights = {}
        for bench in ORDER:  # the paired draw: once per bench, shared by every reading
            groups = numpy.asarray(panels[bench].groups)
            count = int(groups.max()) + 1
            drawn = rng.integers(0, count, size=(resamples, count))
            per_group = numpy.zeros((resamples, count), dtype=numpy.int64)
            numpy.add.at(per_group, (numpy.arange(resamples)[:, None], drawn), 1)
            self.weights[bench] = per_group[:, groups]  # integer products: exact, no floating-point library

    def values(self, key):
        unit = self.units[key]
        return numpy.array([VALUE[unit.tokens[i]] for i in self.panels[key[2]].items])

    def _imputed(self, keys, terms, direction):
        """{key: values} of ``keys`` with every unknown record set to lower (``direction`` -1) or raise (+1) the linear
        reading ``terms``; a record whose total coefficient is 0 takes 0."""
        total = {}
        for key, c in terms.items():
            for item in self.panels[key[2]].items:
                record = (self.units[key].source, item)
                total[record] = total.get(record, Fraction(0)) + c
        out = {}
        for key in keys:
            values = self.values(key)
            for n, item in enumerate(self.panels[key[2]].items):
                if math.isnan(values[n]):
                    c = total.get((self.units[key].source, item), Fraction(0))
                    values[n] = 1.0 if c != 0 and (c > 0) == (direction > 0) else 0.0
            out[key] = values
        return out

    def reading(self, parts, *, transform=None):
        """``parts``: terms, or {name: terms} -- the reading is ``transform({name: value})`` (default: the sum), in
        percentage points; unknown records are imputed for the sum of the parts. Returns {"available": True, variant:
        {"estimate", "interval95", "lower90", "resamples", "items": {bench: usable items}}} or {"available": False,
        "missing": [...]}."""
        if all(isinstance(k, tuple) for k in parts):
            parts = {"reading": parts}
        keys = sorted({key for part in parts.values() for key in part}, key=lambda k: (k[0], k[1], ORDER.index(k[2])))
        missing = ["%s/s%d/%s" % key for key in keys if key not in self.units]
        if missing:
            return {"available": False, "missing": missing}
        terms = combine(*parts.values())
        out = {"available": True}
        for variant in VARIANTS:
            values = ({key: self.values(key) for key in keys} if variant == KNOWN
                      else self._imputed(keys, terms, -1 if variant == LOW else 1))
            result = self._evaluate(parts, values, transform)
            if result is None:
                return {"available": False, "missing": ["no usable item in a bench"]}
            out[variant] = result
        return out

    def _evaluate(self, parts, values, transform):
        """One variant: unknown values (still NaN only in ``known``) drop their item from every accuracy of the
        bench."""
        usable = {}
        for bench in sorted({key[2] for key in values}, key=ORDER.index):
            rows = numpy.vstack([values[key] for key in values if key[2] == bench])
            usable[bench] = (~numpy.isnan(rows)).all(axis=0).astype(numpy.int64)
            if not usable[bench].any():
                return None
        point, resampled = {}, {}
        valid = numpy.ones(self.resamples, dtype=bool)
        for name, part in parts.items():
            total_point, total_resampled = Fraction(0), numpy.zeros(self.resamples)
            for key, c in part.items():
                w = usable[key[2]]
                x = numpy.where(w > 0, numpy.nan_to_num(values[key]), 0.0).astype(numpy.int64)
                counts, sums = self.weights[key[2]] @ w, self.weights[key[2]] @ x
                valid &= counts > 0
                total_point += c * Fraction(int(x.sum()), int(w.sum()))
                total_resampled += float(c) * numpy.divide(sums, counts, out=numpy.zeros(self.resamples),
                                                           where=counts > 0)
            point[name], resampled[name] = 100 * total_point, 100 * total_resampled
        kept = numpy.flatnonzero(valid)
        require(len(kept) > 0, "No resample kept a usable item in every bench")
        if transform is None:  # the sum, vectorized
            draws, estimate = sum(resampled[n][kept] for n in parts), sum(point.values())
        else:
            draws = numpy.array([transform({n: resampled[n][r] for n in parts}) for r in kept])
            estimate = transform(point)
        draws = numpy.sort(numpy.round(draws, DIGITS))  # floating-point noise never decides a comparison
        return {"estimate": round(float(estimate), DIGITS),
                "interval95": [_percentile(draws, 0.025), _percentile(draws, 0.975)],
                "lower90": _percentile(draws, 0.05), "resamples": int(len(kept)),
                "items": {b: int(w.sum()) for b, w in usable.items()}}


def _percentile(sorted_draws, q):
    """The percentile convention of ``stats.bootstrap``: the lower end floor(q n), the upper end ceil(q n) - 1."""
    n = len(sorted_draws)
    index = int(math.floor(q * n)) if q < 0.5 else min(n - 1, int(math.ceil(q * n)) - 1)
    return float(sorted_draws[index])


# ----------------------------------------------------------------------------------------------------- claims
def holds_large(result, threshold, *, bound="interval95"):
    """A claim that the reading exceeds ``threshold`` (its lower end), on ``known`` and on ``low`` (§12.6)."""
    if not result["available"]:
        return None
    lower = (lambda r: r["lower90"]) if bound == "lower90" else (lambda r: r["interval95"][0])
    return lower(result[KNOWN]) > threshold and lower(result[LOW]) > threshold


def holds_small(result, threshold):
    """A claim that the reading's upper end is below ``threshold``, on ``known`` and on ``high``."""
    if not result["available"]:
        return None
    return result[KNOWN]["interval95"][1] < threshold and result[HIGH]["interval95"][1] < threshold


def noninferiority(result, margin):
    """§12.3: "not worse" (L > -margin), "worse" (U < -margin) or "uncertain"; None when not assessable."""
    if not result["available"]:
        return None
    if holds_large(result, -margin):
        return "not_worse"
    if holds_small(result, -margin):
        return "worse"
    return "uncertain"


# --------------------------------------------------------------------------------------------- the registered set
# v2 delta §1, §9: no baseline chain runs, so v1's P1-P4 tests and their combined claims are retired; a reference is
# evaluated at stage 0 only. v3 delta §1: one solver per family -- the chain from the scaffold ("method"), the chain
# from the instructions ("instructed") and the empty-Skill reference; the deepseek family is v3's run, with I-ds
# primary; the GLM-5.3 family keeps v2's reading (E-glm primary) and is not run by v3.
FAMILIES = {"ds": {"method": "E-ds", "instructed": "I-ds", "reference": "NoSkill-ds", "primary": "instructed"},
            "glm": {"method": "E-glm", "instructed": "I-glm", "reference": "NoSkill-glm", "primary": "method"}}
FAMILY = "ds"
METHOD, INSTRUCTED, REFERENCE = (FAMILIES[FAMILY][k] for k in ("method", "instructed", "reference"))
LEARNING = (INSTRUCTED, METHOD)
CHAIN_NAMES = (INSTRUCTED, METHOD, REFERENCE)
GAINS = {"method": "learning_gain", "instructed": "exceeds_instructions"}  # a learning chain's M[5] - M[0]
REST_MARGIN = 2  # §12.8 Q3: the rest's mean change not below -2 points


def _truncated(value):
    return sum(max(0.0, v) for v in value.values())


def _updates(updates, chain):
    """(stages with accepted rules, moved -- at least two --, similar placement used) of a learning chain.
    ``updates`` holds an ended chain's merges only: a chain that has not ended, or a stage it never merged, is
    unavailable, never zero (§12.5, §13.4) -- a status is decided only when the records present already decide it."""
    found = updates.get(chain)
    if found is None:
        return None, None, None
    last = len(ORDER)
    complete = all(stage in found for stage in range(1, last + 1))
    moved = sum(1 for value in found.values() if value.get("local", 0) + value.get("similar", 0) > 0)
    similar = any(value.get("similar", 0) > 0 for value in found.values())
    return (moved, True if moved >= 2 else (False if complete else None),
            True if similar else (False if complete else None))


def chain_readings(readings, chain):
    """§12.4 and §12.8 descriptions of one chain: trajectories, G_b, F_b, N_b, their means and truncated means, the
    step changes and their class means."""
    cells = transfer_cells()
    quarter = Fraction(1, len(ORDER) - 1)
    out = {
        "macro": {s: readings.reading(macro(chain, s)) for s in STAGES},
        "accuracy": {"%d/%s" % (s, b): readings.reading(accuracy(chain, s, b)) for s in STAGES for b in ORDER},
        "gain": {b: readings.reading(gain(chain, b)) for b in ORDER},
        "forgetting": {b: readings.reading(forgetting(chain, b)) for b in ORDER[:-1]},
        "ahead": {b: readings.reading(ahead(chain, b)) for b in ORDER[1:]},
        "mean_forgetting": readings.reading(mean_forgetting(chain)),
        "mean_ahead": readings.reading(mean_ahead(chain)),
        "mean_forgetting_truncated": readings.reading(
            {b: combine(forgetting(chain, b), scale=quarter) for b in ORDER[:-1]}, transform=_truncated),
        "mean_ahead_truncated": readings.reading(
            {b: combine(ahead(chain, b), scale=quarter) for b in ORDER[1:]}, transform=_truncated),
        "step_change": {"%d/%s" % (s, b): readings.reading(step_change(chain, s, b))
                        for s in range(1, len(ORDER) + 1) for b in ORDER},
        "transfer": {name: readings.reading(class_mean(chain, cells[name]))
                     for name in ("self", "similar", "rest", "forward", "backward")},
    }
    return out


def reference_readings(readings, chain=REFERENCE):
    """v2 §1: the reference's stage 0, its only evaluation."""
    return {"macro": {0: readings.reading(macro(chain, 0))},
            "accuracy": {"0/%s" % b: readings.reading(accuracy(chain, 0, b)) for b in ORDER}}


def questions(cells, moved, similar_used):
    """§12.8's Q1-Q3 on one chain's transfer classes (one-sided 95% lower bounds) and their conjunction."""
    out = {"Q1": holds_large(cells["self"], 0, bound="lower90"),
           "Q2": holds_large(cells["similar"], 0, bound="lower90"),
           "Q3": holds_large(cells["rest"], -REST_MARGIN, bound="lower90"),
           "similar_placement_used": similar_used, "method_moved": moved}
    out["registered_transfer_criterion"] = None if None in (out["Q1"], out["Q2"], out["Q3"]) else (
        out["Q1"] and out["Q2"] and out["Q3"])
    return out


def registered(readings, updates, family=FAMILY):
    """Every registered reading of one family (v2 delta §9; v3 delta §1) -- chains that were not evaluated give "not
    assessable" readings. ``updates``: {chain: {stage: {"local": n, "similar": n}}} -- the rules each stage of an
    ended learning chain accepted, by placement (an absent chain or stage is unavailable, not "no update").

    Primary: the leading chain's M[5] - M[0] (L > 0) -- v3, I-ds beyond its instructions ("exceeds_instructions");
    v2, E-glm's learning gain above the fixed scaffold ("learning_gain") -- whether it moved, and its Q1-Q3.
    Secondary, without multiplicity correction: the other learning chain's M[5] - M[0], the scaffold-only start
    reaching the instructions' level (three outcomes), the scaffold's own contrast with the reference and the other
    chain's Q1-Q3 (descriptions only)."""
    names = FAMILIES[family]
    method, instructed, reference = names["method"], names["instructed"], names["reference"]
    lead = names["primary"]
    other = "method" if lead == "instructed" else "instructed"
    out = {"family": family, "chains": {names[role]: chain_readings(readings, names[role]) for role in (lead, other)}}
    out["chains"][reference] = reference_readings(readings, reference)
    last = len(ORDER)
    moved = {names[role]: _updates(updates, names[role]) for role in (lead, other)}
    out["updates"] = {chain: {"stages_with_accepted_rules": n, "moved": ok, "similar_used": similar}
                      for chain, (n, ok, similar) in moved.items()}
    gain = {role: readings.reading(difference(macro(names[role], last), macro(names[role], 0)))
            for role in (lead, other)}
    first = names[lead]
    out["primary"] = {"chain": first, "kind": GAINS[lead], "reading": gain[lead], "status": {
        "method_moved": moved[first][1], "stages_with_accepted_rules": moved[first][0],
        "verdict": holds_large(gain[lead], 0)}}
    out["transfer"] = questions(out["chains"][first]["transfer"], moved[first][1], moved[first][2])
    from_scaffold = readings.reading(difference(macro(method, last), macro(instructed, 0)))
    second = names[other]
    out["secondary"] = {
        "chain": second, "kind": GAINS[other],
        "gain": {"reading": gain[other], "verdict": holds_large(gain[other], 0)},
        "scaffold_reaches_instructions": {"reading": from_scaffold,
                                          "verdict": noninferiority(from_scaffold, NI_MARGIN)},
        "scaffold": readings.reading(difference(macro(method, 0), macro(reference, 0))),
        "transfer": questions(out["chains"][second]["transfer"], moved[second][1], moved[second][2]),
    }
    return out
