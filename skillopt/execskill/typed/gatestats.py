"""Gate statistics of typed-v2 (DESIGN 3.4 and 4.1, decision D5): R fresh runs per item and arm, exact decisions;
and the decision arithmetic of typed-v3 (CHAIN-DECISIONS T7): the card rule on E, the screen, gains by item class.

Pure: no file, no clock, no randomness, no import of the frozen machinery or of another typed module. The caller
passes the repeat count R and the two tau constants (``T/__init__``); this module holds none of them. Step 5 of the
build re-exports these names from ``T/gates.py`` (addendum 2026-11-12 16:1x, module placement).

Cells and scores (addendum O1, O11). A gate arm runs R cells per item with labels ``<arm>#<r>``, r = 1..R. Scores
are binary: x = 1 for a cell with ``correct is True``, else 0. A cell whose final outcome is a model-side unknown
(``correct is None`` with neither ``infrastructure_unknown`` nor ``configuration_error`` set, the complement of the
re-run predicate of ``T/units.py``) is present and final: it is scored 0, never re-run, and counted in
``unknown_final``. A missing cell, or an infrastructure or configuration unknown left after the unit's attempts,
makes the arm undecidable (``UndecidableRuns``): nothing is decided and no item is excluded; the chain pauses.

Statistics (B = baseline arm, K = candidate arm, items i = 1..n, a = minimum_points, c = multiplier):

    S[A,i] = sum_r x[A,i,r]      D = sum_i (S[K,i] - S[B,i])      q[i] = R * sum_r x[B,i,r]^2 - S[B,i]^2
    Q = sum_i q[i]               better / worse / tied = items with S[K,i] > / < / = S[B,i]
    gain_points = 100 * D / (R * n)       se_points = (100 / (R * n)) * sqrt(2 * Q / (R - 1))
    tau_points  = max(a, c * se_points)

Every comparison is decided in integers, with a = a_num / a_den and c = c_num / c_den taken exactly:

    reaches(D, m) := 100 * D * a_den >= a_num * R * m  and  D >= 0
                     and  D^2 * n^2 * (R - 1) * c_den^2 >= 2 * c_num^2 * Q * m^2      (gain over m items >= tau)
    no_regress(D) := 100 * D * a_den >= -a_num * R * n  or  D >= 0
                     or  D^2 * (R - 1) * c_den^2 <= 2 * c_num^2 * Q                   (whole-slice gain >= -tau)

With a = 3 and c = 2 these are the forms of DESIGN 3.4. Floats are reported and never compared. Q and n are always
those of the whole slice; a subset (the items where a program fired) changes D, m and the counts only.

Shared types (addendum D16 b). When the home type of a step also holds sources of earlier benches (the members), a
card round or program that passed the home rule is checked on every member bench's gate slice in member order:
``member_decision`` is no_regress(D) of the candidate's member arm against the member baseline, with tau from that
comparison's baseline repeats. ``shared_verdict`` accepts iff the home decision accepted and every member check holds;
the first failing member rejects with reason ``member_harm`` and names its bench (``member_harm``), and no later
member is checked. A record of a shared type carries ``shared_with`` (the members, in order) and ``members`` (the
checks that ran); ``recompute`` rebuilds every member check and the final verdict.

typed-v3, gate rule ``'evolution'`` (CHAIN-DECISIONS T7, owner-approved 2026-11-14). On a step with made items the gate
list J is the real gate slice R followed by the judging-side attack A, guard G and calibration K items, and E = R + A
is where improvement is sought. ``evolution_statistics`` restricts a whole-list comparison over J to the ids of E,
from J's own per_item rows, as if E were the slice: its own n_E, D_E, better / worse / tied and its OWN Q_E from the
baseline's repeats on the items of E, so tau_E = max(a, c * se_E) with se_E from Q_E and n_E. E is not a subset in
the sense above (a subset keeps the whole slice's Q and n). ``card_decision_evolution`` accepts a card iff
reaches(D_E, n_E) with Q_E, better_E > worse_E, and no_regress(D_J) over all items of J exactly as
``no_harm_decision`` (reasons checked in this order: gain_below_tau, not_more_better_than_worse, harm). Today's
``card_decision`` has no harm clause, so the harm clause on J is the only addition; with E = J it can never fail:
reaches requires D >= 0, and D >= 0 is a disjunct of no_regress. With E = J the two rules therefore give the same
verdict and reason on EVERY input (not only where no_regress holds); they differ only when E is a proper part of J.
Programs (on J and their fired items, whole-list tau), typing no-harm and member checks keep their rules.

The screen (T7) runs a candidate ONCE on A + G before the R paid runs of its gate. With b the baseline's right runs
over those items (R runs each, from the arm the candidate is compared with) and c the candidate's right runs in its
one run, it goes on iff R * c >= b (its pass count is not below the baseline's mean); a program or archive package
also needs to have fired on at least one of those items (``screen_decision``, from ``screen_counts``). The screen's
cells are never gate runs: a candidate that passed the screen by luck would carry that luck into the gate.
``class_gains`` reports the gain on each item class and the baseline's calibration-minus-real parity; it decides
nothing.

Records (DESIGN 4.1, addendum O12). ``per_item`` is ``[[item, S_B, S_K], ...]`` in the slice order
(``[[item, S], ...]`` in a noise record; for binary scores the sum of squares equals the sum and is not stored).
Program decisions add ``fired_cells = [[item, count], ...]`` for the items with a count above 0 (an item is fired
when the program fired in at least one of its R cells, O6) and the informational ``se_points_fired`` and
``se_points_scaled``, which never decide. Records hold JSON integers and lists only; ``scores`` is always
``'binary'``. ``recompute(record)`` rebuilds every derived field from the record alone. A typed-v3 card decision is
a card record (kind ``'card'``, the whole-list statistics of J as above) plus ``evolution = {item_ids, n,
difference_sum, variance_sum, gain_points, se_points, tau_points, better, worse, tied, reaches}`` on E; ``item_ids``
are the ids of E themselves, in J's order (not a hash: this module imports no hash function, and the ids let
``recompute`` rebuild E from the record alone). A screen record is ``{kind 'screen', b, c, repeats, items, fired,
baseline_pass_points, candidate_pass_points, passed, reason}`` (``fired`` None for a card; the two pass rates in
points are reported, never compared).
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from fractions import Fraction

REPEAT_SEP = '#'
SCORES = 'binary'
NOISE_RULE = 'baseline_repeats'
CARD_REASONS = ('accepted', 'gain_below_tau', 'not_more_better_than_worse')
PROGRAM_REASONS = ('accepted', 'never_fired', 'gain_below_tau', 'not_more_better_than_worse', 'harm')
NO_HARM_REASONS = ('merged', 'harm_beyond_tau')
MEMBER_HARM = 'member_harm'  # addendum D16 (b): passed the home rule, regressed beyond tau on a member bench
EVOLUTION_CARD_REASONS = ('accepted', 'gain_below_tau', 'not_more_better_than_worse', 'harm')  # typed-v3 T7, on E
SCREEN_REASONS = ('passed', 'screen_never_fired', 'screen_below_baseline')  # typed-v3 T7, the screen on A + G
ITEM_CLASSES = ('real', 'attack', 'guard', 'calibration')  # typed-v3 T3: J = R + A + G + K, in this order
EVOLUTION_CLASSES = ('real', 'attack')  # typed-v3 T7: E = R + A, where improvement is sought

_INPUTS = ('per_item', 'repeats', 'minimum_points', 'multiplier', 'unknown_final')
_EVOLUTION_KEYS = ('n', 'difference_sum', 'variance_sum', 'gain_points', 'se_points', 'tau_points', 'better', 'worse',
                   'tied', 'reaches')
_SCREEN_INPUTS = ('b', 'c', 'repeats', 'items', 'fired')


class UndecidableRuns(ValueError):
    """An arm with a missing cell, or with an infrastructure / configuration unknown left after the unit's attempts.
    Counts only, never item content: the caller pauses (``incomplete_unit:missing_cells`` when ``missing``, else
    ``gate_cells_unknown``); nothing is decided and no item is excluded."""

    def __init__(self, arm, *, missing, infrastructure, expected):
        self.arm, self.missing, self.infrastructure, self.expected = arm, missing, infrastructure, expected
        super().__init__('arm %s: %d of %d cells missing, %d infrastructure or configuration unknown'
                         % (arm, missing, expected, infrastructure))


# ---- labels -----------------------------------------------------------------------------------------------------
def _repeats(repeats):
    if type(repeats) is not int or repeats < 2:
        raise ValueError('A gate arm needs R >= 2 runs per item (the variance needs two), got %r' % (repeats,))
    return repeats


def repeat_labels(arm, repeats):
    """The R cell labels of one gate arm, ``('<arm>#1', ..., '<arm>#R')``. A label enters the cell tag, never a
    request: the R cells of an item are identical requests sent fresh."""
    if type(arm) is not str or not arm or REPEAT_SEP in arm:
        raise ValueError('An arm is a non-empty name without %r, got %r' % (REPEAT_SEP, arm))
    return tuple('%s%s%d' % (arm, REPEAT_SEP, r) for r in range(1, _repeats(repeats) + 1))


def arm_of_label(label):
    """The mount arm of a cell label, ``label.split('#', 1)[0]``; a bare single-run label is its own arm."""
    if type(label) is not str:
        raise TypeError('A cell label is a string, got %r' % (type(label).__name__,))
    return label.split(REPEAT_SEP, 1)[0]


def repeat_of_label(label):
    """The repeat index r of ``<arm>#<r>`` (an int >= 1), None for a bare single-run label. A label with the
    separator but no canonical index (``F#``, ``F#0``, ``F#01``, ``F#x``, ``#1``) is refused."""
    arm = arm_of_label(label)
    if REPEAT_SEP not in label:
        return None
    suffix = label[len(arm) + len(REPEAT_SEP):]
    if not arm or not (suffix.isascii() and suffix.isdigit()) or suffix[0] == '0':
        raise ValueError('A repeat label is <arm>#<r> with r = 1, 2, ..., got %r' % (label,))
    return int(suffix)


# ---- runs of one arm --------------------------------------------------------------------------------------------
def _items(items):
    if not isinstance(items, (list, tuple)):
        raise TypeError('items is the ordered list of the gate slice item ids')
    ids = list(items)
    if not ids:
        raise ValueError('A gate slice has at least one item')
    if any(type(item) is not str or not item for item in ids):
        raise ValueError('An item id is a non-empty string')
    if len(set(ids)) != len(ids):
        raise ValueError('An item id occurs twice in the gate slice')
    return ids


def arm_runs(cells, items, arm, repeats):
    """Run sums of one gate arm over the slice: ``{'sums': {item: S}, 'squares': {item: sum of x^2}, 'unknown': u}``.

    ``cells`` maps ``(item_id, label)`` to a cell row, as the chain's cell units return them; only the labels
    ``repeat_labels(arm, repeats)`` of the given items are read. ``correct`` must be True, False or None (binary
    scores, O11); a model-side unknown scores 0 and is counted in ``unknown`` (O1). A missing cell or an
    infrastructure / configuration unknown raises ``UndecidableRuns`` with the counts of the whole arm."""
    labels, ids = repeat_labels(arm, repeats), _items(items)
    if not isinstance(cells, Mapping):
        raise TypeError('cells maps (item_id, label) to a cell row')
    sums, unknown, missing, infrastructure = {}, 0, 0, 0
    for item in ids:
        total = 0
        for label in labels:
            row = cells.get((item, label))
            if row is None:
                missing += 1
                continue
            if not isinstance(row, Mapping):
                raise TypeError('A cell row is a mapping')
            correct = row.get('correct')
            if correct is True:
                total += 1
            elif correct is None:
                if row.get('infrastructure_unknown') or row.get('configuration_error'):
                    infrastructure += 1
                else:
                    unknown += 1  # a final model-side verdict: x = 0, never re-run (O1)
            elif correct is not False:
                raise ValueError('Gate scores are binary (addendum O11): correct is True, False or None, got a %s'
                                 % type(correct).__name__)
        sums[item] = total
    if missing or infrastructure:
        raise UndecidableRuns(arm, missing=missing, infrastructure=infrastructure, expected=len(ids) * len(labels))
    return {'sums': sums, 'squares': dict(sums), 'unknown': unknown}


# ---- exact forms and reported points ----------------------------------------------------------------------------
def _exact(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('%s is a finite number >= 0, got %r' % (name, value))
    return Fraction(value)


def _reaches(D, m, *, n, Q, R, a, c):
    """gain over m items >= tau = max(a, c * se) of the whole slice (n items, Q), in integers."""
    return (100 * D * a.denominator >= a.numerator * R * m and D >= 0
            and D * D * n * n * (R - 1) * c.denominator ** 2 >= 2 * c.numerator ** 2 * Q * m * m)


def _no_regress(D, *, n, Q, R, a, c):
    """whole-slice gain >= -tau = -max(a, c * se), in integers."""
    return (100 * D * a.denominator >= -a.numerator * R * n or D >= 0
            or D * D * (R - 1) * c.denominator ** 2 <= 2 * c.numerator ** 2 * Q)


def _gain_points(D, R, m):
    return 100 * D / (R * m)


def _se_points(Q, R, m):
    return (100 / (R * m)) * math.sqrt(2 * Q / (R - 1))


def _tau_points(se_points, minimum_points, multiplier):
    return max(float(minimum_points), float(multiplier) * se_points)


def _counts(baseline, candidate):
    pairs = list(zip(baseline, candidate))
    return (sum(k > b for b, k in pairs), sum(k < b for b, k in pairs), sum(k == b for b, k in pairs))


def _derive(ids, sb, sk, repeats, minimum_points, multiplier, unknown, subset):
    """The one computation of every derived field (validated inputs; ``subset`` None or a set of item ids)."""
    R, n = repeats, len(ids)
    a, c = _exact(minimum_points, 'minimum_points'), _exact(multiplier, 'multiplier')
    q = [R * b - b * b for b in sb]  # R * sum_r x^2 - S^2, with sum_r x^2 = S for binary scores
    Q, D = sum(q), sum(k - b for b, k in zip(sb, sk))
    better, worse, tied = _counts(sb, sk)
    se = _se_points(Q, R, n)
    gain = _gain_points(D, R, n)
    stats = {'scores': SCORES, 'repeats': R, 'n': n, 'minimum_points': minimum_points, 'multiplier': multiplier,
             'difference_sum': D, 'variance_sum': Q, 'gain_points': gain, 'mean_points': gain, 'se_points': se,
             'tau_points': _tau_points(se, minimum_points, multiplier), 'better': better, 'worse': worse,
             'tied': tied, 'reaches': _reaches(D, n, n=n, Q=Q, R=R, a=a, c=c),
             'no_regress': _no_regress(D, n=n, Q=Q, R=R, a=a, c=c), 'baseline_runs_correct': sum(sb),
             'candidate_runs_correct': sum(sk), 'unknown_final': dict(unknown), 'excluded_unknown': 0,
             'per_item': [[item, b, k] for item, b, k in zip(ids, sb, sk)]}
    if subset is not None:
        chosen = [j for j, item in enumerate(ids) if item in subset]
        m = len(chosen)
        Df, Qf = sum(sk[j] - sb[j] for j in chosen), sum(q[j] for j in chosen)
        bf, wf, tf = _counts([sb[j] for j in chosen], [sk[j] for j in chosen])
        stats.update({'subset': [ids[j] for j in chosen], 'subset_n': m, 'subset_difference_sum': Df,
                      'subset_gain_points': _gain_points(Df, R, m) if m else None, 'subset_better': bf,
                      'subset_worse': wf, 'subset_tied': tf,
                      'subset_reaches': m > 0 and _reaches(Df, m, n=n, Q=Q, R=R, a=a, c=c),
                      'subset_se_points': _se_points(Qf, R, m) if m else None,
                      'subset_se_points_scaled': se * math.sqrt(n / m) if m else None})
    return stats


# ---- statistics of one comparison and of one calibration --------------------------------------------------------
def _runs(runs, ids, repeats, role):
    if not isinstance(runs, Mapping) or any(key not in runs for key in ('sums', 'squares', 'unknown')):
        raise TypeError('The %s runs are arm_runs output: sums, squares, unknown' % role)
    sums, squares, unknown = runs['sums'], runs['squares'], runs['unknown']
    if not (isinstance(sums, Mapping) and isinstance(squares, Mapping) and set(sums) == set(ids) == set(squares)):
        raise ValueError('The %s runs cover exactly the items of the gate slice' % role)
    values = [sums[item] for item in ids]
    if any(type(s) is not int or not 0 <= s <= repeats for s in values):
        raise ValueError('A %s run sum is an integer in 0..R' % role)
    if any(type(squares[item]) is not int or squares[item] != sums[item] for item in ids):
        raise ValueError('Binary scores (addendum O11): the %s sum of squares equals the sum' % role)
    if type(unknown) is not int or not 0 <= unknown <= len(ids) * repeats - sum(values):
        raise ValueError('The %s unknown count is an integer in 0..(n * R - correct runs)' % role)
    return values, unknown


def _subset(subset, ids):
    if subset is None:
        return None
    if not isinstance(subset, (list, tuple, set, frozenset)):
        raise TypeError('subset is a collection of gate item ids')
    chosen = list(subset)
    if len(set(chosen)) != len(chosen):
        raise ValueError('An item occurs twice in the subset')
    if not set(chosen) <= set(ids):
        raise ValueError('A subset item is not an item of the gate slice')
    return set(chosen)


def repeat_statistics(baseline, candidate, *, items, repeats, minimum_points, multiplier, subset=None):
    """Statistics of candidate K against baseline B (both ``arm_runs`` output over ``items``); tau comes from the
    baseline's own repeats. With ``subset`` (the fired items of a program) the ``subset_*`` fields hold D, the
    gain, the counts, ``reaches`` over those items against the whole-slice tau, and the informational
    ``subset_se_points`` (Q over the subset) and ``subset_se_points_scaled`` (se_points * sqrt(n / n_subset))."""
    ids, R = _items(items), _repeats(repeats)
    sb, ub = _runs(baseline, ids, R, 'baseline')
    sk, uk = _runs(candidate, ids, R, 'candidate')
    return _derive(ids, sb, sk, R, minimum_points, multiplier, {'baseline': ub, 'candidate': uk},
                   _subset(subset, ids))


def calibration(baseline, *, items, repeats, minimum_points, multiplier):
    """The noise record of one step (arm C0 with R repeats on the gate slice): Q, se, tau, ``per_item = [[item,
    S], ...]``. A comparison whose baseline is this arm gets the same Q, se and tau."""
    ids, R = _items(items), _repeats(repeats)
    _exact(minimum_points, 'minimum_points')
    _exact(multiplier, 'multiplier')
    sb, unknown = _runs(baseline, ids, R, 'baseline')
    Q = sum(R * b - b * b for b in sb)
    se = _se_points(Q, R, len(ids))
    return {'kind': 'noise', 'rule': NOISE_RULE, 'scores': SCORES, 'repeats': R, 'n': len(ids),
            'minimum_points': minimum_points, 'multiplier': multiplier, 'variance_sum': Q, 'se_points': se,
            'tau_points': _tau_points(se, minimum_points, multiplier), 'mixed_items': sum(0 < b < R for b in sb),
            'runs_correct': sum(sb), 'unknown_final': unknown, 'per_item': [[item, b] for item, b in zip(ids, sb)]}


# ---- decisions --------------------------------------------------------------------------------------------------
def _same(x, y):
    """Equality that also keeps types apart (1 vs 1.0 vs True; a list is not a tuple)."""
    if type(x) is not type(y):
        return False
    if isinstance(x, list):
        return len(x) == len(y) and all(_same(u, v) for u, v in zip(x, y))
    if isinstance(x, dict):
        return x.keys() == y.keys() and all(_same(x[key], y[key]) for key in x)
    return x == y


def _rows(per_item, repeats, width):
    if not isinstance(per_item, (list, tuple)) or not per_item:
        raise ValueError('per_item is a non-empty list of rows')
    if any(not isinstance(row, (list, tuple)) or len(row) != width for row in per_item):
        raise ValueError('A per_item row has %d fields' % width)
    ids = _items([row[0] for row in per_item])
    columns = [[row[j] for row in per_item] for j in range(1, width)]
    if any(type(s) is not int or not 0 <= s <= repeats for column in columns for s in column):
        raise ValueError('A per_item run sum is an integer in 0..R')
    return (ids, *columns)


def _unknown_pair(unknown, n, repeats, sb, sk):
    if not isinstance(unknown, Mapping) or set(unknown) != {'baseline', 'candidate'}:
        raise ValueError('unknown_final of a comparison counts the baseline and the candidate arm')
    for role, values in (('baseline', sb), ('candidate', sk)):
        count = unknown[role]
        if type(count) is not int or not 0 <= count <= n * repeats - sum(values):
            raise ValueError('The %s unknown count is an integer in 0..(n * R - correct runs)' % role)
    return {'baseline': unknown['baseline'], 'candidate': unknown['candidate']}


def _restate(stats, *, with_subset):
    """Re-derive statistics from their own inputs and require every derived field to be equal: a decision is made
    from the per_item list, never from a stored flag."""
    if not isinstance(stats, Mapping):
        raise TypeError('Gate statistics are repeat_statistics output')
    absent = [key for key in _INPUTS if key not in stats]
    if absent:
        raise ValueError('Gate statistics lack %s' % ', '.join(absent))
    if ('subset' in stats) != with_subset:
        raise ValueError('Expected the statistics %s a subset' % ('of' if with_subset else 'without'))
    R = _repeats(stats['repeats'])
    ids, sb, sk = _rows(stats['per_item'], R, 3)
    unknown = _unknown_pair(stats['unknown_final'], len(ids), R, sb, sk)
    fresh = _derive(ids, sb, sk, R, stats['minimum_points'], stats['multiplier'], unknown,
                    _subset(stats['subset'], ids) if with_subset else None)
    if any(key not in stats or not _same(stats[key], value) for key, value in fresh.items()):
        raise ValueError('The gate statistics do not follow from their own per_item list')
    return fresh


def card_decision(stats):
    """Accept a card iff reaches(D, n) and better > worse (DESIGN 3.4); B = the incumbent F."""
    s = _restate(stats, with_subset=False)
    reason = ('gain_below_tau' if not s['reaches'] else 'not_more_better_than_worse' if s['better'] <= s['worse']
              else 'accepted')
    return {'kind': 'card', 'accepted': reason == 'accepted', 'reason': reason, **s}


def no_harm_decision(stats):
    """Merge a source into a same-signature type iff no_regress(D), with B = C0 of the noise unit and K = F with
    the source provisionally merged (DESIGN 3.4)."""
    s = _restate(stats, with_subset=False)
    merge = s['no_regress']
    return {'kind': 'no_harm', 'merge': merge, 'reason': 'merged' if merge else 'harm_beyond_tau', **s}


def _fired_counts(fired_cells, ids, repeats):
    if isinstance(fired_cells, Mapping):
        pairs = list(fired_cells.items())
    elif isinstance(fired_cells, (list, tuple)):
        if any(not isinstance(pair, (list, tuple)) or len(pair) != 2 for pair in fired_cells):
            raise ValueError('fired_cells rows are [item, count]')
        pairs = [tuple(pair) for pair in fired_cells]
    else:
        raise TypeError('fired_cells maps a gate item to the number of its cells where the program fired')
    known, counts = set(ids), {}
    for item, count in pairs:
        if item not in known:
            raise ValueError('A fired item is not an item of the gate slice')
        if item in counts:
            raise ValueError('A fired item occurs twice')
        if type(count) is not int or not 0 <= count <= repeats:
            raise ValueError('A fired count is an integer in 0..R')
        counts[item] = count
    return counts


def program_decision(stats, fired_stats, fired_cells):
    """Accept a program iff it fired on n_f > 0 items, reaches(D_f, n_f) against the whole-slice tau,
    better_f > worse_f, and no_regress(D) over all items (DESIGN 3.4; addendum, program gate on fired items).
    ``fired_stats`` is the same comparison with ``subset`` = the items whose fired count in ``fired_cells`` (a
    mapping or ``[[item, count], ...]``, counts 0..R, O6) is above 0. The ``*_fired`` / ``se_points_scaled``
    fields are stored for the reports and never decide."""
    s = _restate(stats, with_subset=False)
    f = _restate(fired_stats, with_subset=True)
    if any(not _same(f[key], value) for key, value in s.items()):
        raise ValueError('The fired statistics belong to another comparison')
    ids = [row[0] for row in s['per_item']]
    counts = _fired_counts(fired_cells, ids, s['repeats'])
    fired = [item for item in ids if counts.get(item, 0) > 0]
    if fired != f['subset']:
        raise ValueError('The fired subset is not the set of items with a fired cell')
    reason = ('never_fired' if not fired else 'gain_below_tau' if not f['subset_reaches']
              else 'not_more_better_than_worse' if f['subset_better'] <= f['subset_worse']
              else 'harm' if not s['no_regress'] else 'accepted')
    return {'kind': 'program', 'accepted': reason == 'accepted', 'reason': reason, **s,
            'fired_items': len(fired), 'fired_cells': [[item, counts[item]] for item in fired],
            'difference_sum_fired': f['subset_difference_sum'], 'gain_points_fired': f['subset_gain_points'],
            'better_fired': f['subset_better'], 'worse_fired': f['subset_worse'], 'tied_fired': f['subset_tied'],
            'reaches_fired': f['subset_reaches'], 'se_points_fired': f['subset_se_points'],
            'se_points_scaled': f['subset_se_points_scaled']}


def member_decision(stats):
    """The check of one member bench of a shared type (addendum D16 b) for a candidate that passed the home rule:
    no_regress(D) over that bench's whole gate slice, B = the member baseline (the current mount on the member's
    items; after an accepted card that card's member runs, O5), K = the candidate's member arm, tau from B's own
    repeats. ``no_regress`` is the verdict; a model-side unknown run scores 0 (O1)."""
    return {'kind': 'member', **_restate(stats, with_subset=False)}


def _shared_benches(shared_with):
    if not isinstance(shared_with, (list, tuple)) or not shared_with:
        raise ValueError('shared_with lists the member benches of a shared type')
    benches = []
    for row in shared_with:
        bench = row.get('bench') if isinstance(row, Mapping) else None
        if type(bench) is not str or not bench:
            raise ValueError('A shared_with row names its bench')
        benches.append(bench)
    if len(set(benches)) != len(benches):
        raise ValueError('A member bench occurs twice in shared_with')
    return benches


def shared_verdict(decision, members, shared_with):
    """The final verdict of a candidate of a shared type (addendum D16 b) from its home decision (``card_decision`` /
    ``program_decision`` output) and the member checks that ran (``member_decision`` rows with their ``bench``), in
    the member order of ``shared_with``: accepted iff the home decision accepted and every member holds no_regress.
    The checks run only for a candidate that passed the home rule and stop at the first member harm, so the stored
    checks are exactly: none (home rejected), a prefix ending at the first harm, or every member. Returns
    ``{'accepted', 'reason', 'member_harm'}`` (``member_harm``: the bench that regressed, else None)."""
    benches = _shared_benches(shared_with)
    if not isinstance(members, (list, tuple)) or any(not isinstance(row, Mapping) for row in members):
        raise TypeError('members is the list of member checks that ran')
    if [row.get('bench') for row in members] != benches[:len(members)] or len(members) > len(benches):
        raise ValueError('The member checks follow the member order of shared_with')
    if not decision['accepted']:
        if members:
            raise ValueError('A member check runs only for a candidate that passed the home rule')
        return {'accepted': False, 'reason': decision['reason'], 'member_harm': None}
    for j, row in enumerate(members):
        if type(row.get('no_regress')) is not bool:
            raise ValueError('A member check holds its no_regress verdict')
        if not row['no_regress']:
            if j != len(members) - 1:
                raise ValueError('No member check runs after a member harm')
            return {'accepted': False, 'reason': MEMBER_HARM, 'member_harm': row['bench']}
    if len(members) != len(benches):
        raise ValueError('An accepted candidate of a shared type holds the check of every member bench')
    return {'accepted': True, 'reason': decision['reason'], 'member_harm': None}


# ---- typed-v3: the card rule on E, the screen, gains by item class (CHAIN-DECISIONS T7) -------------------------
def _evolution_ids(items, ids):
    """The ids of E checked against the ids of J: an ordered list, non-empty, no repeat, each an item of J, in the
    order of J (so the stored list is canonical)."""
    if not isinstance(items, (list, tuple)):
        raise TypeError('The items of E are an ordered list of gate item ids, in the order of J')
    chosen = list(items)
    if not chosen:
        raise ValueError('E holds at least one item')
    if any(type(item) is not str or not item for item in chosen):
        raise ValueError('An item id of E is a non-empty string')
    if len(set(chosen)) != len(chosen):
        raise ValueError('An item occurs twice in E')
    place = {item: j for j, item in enumerate(ids)}
    if any(item not in place for item in chosen):
        raise ValueError('An item of E is not an item of the gate list J')
    if any(place[x] > place[y] for x, y in zip(chosen, chosen[1:])):
        raise ValueError('The items of E follow the order of J')
    return chosen


def _evolution_block(s, items):
    """The statistics on E of the validated whole-list statistics ``s``: ``_derive`` (the one computation of this
    module) on the per_item rows of E, which are J's own rows."""
    rows = {row[0]: row for row in s['per_item']}
    chosen = _evolution_ids(items, list(rows))
    e = _derive(chosen, [rows[item][1] for item in chosen], [rows[item][2] for item in chosen], s['repeats'],
                s['minimum_points'], s['multiplier'], {}, None)
    return {'item_ids': chosen, **{key: e[key] for key in _EVOLUTION_KEYS}}


def evolution_statistics(stats, items):
    """The statistics on E (typed-v3 T7: E = R + A, the real gate items and the judging-side attack items) of a
    whole-list comparison over the gate list J: ``stats`` is ``repeat_statistics`` output over J without a subset
    (or a stored decision that holds it), ``items`` the ids of E as an ordered list in the order of J, non-empty,
    each an item of J (else ValueError; a set or a string is a TypeError).

    Built from J's own per_item rows only, so a caller cannot bring in an E computed from other runs. E is treated as
    if it were the slice: its own n_E, D_E, better / worse / tied, and its OWN Q_E from the baseline's repeats on the
    items of E, so tau_E = max(minimum_points, multiplier * se_E) with se_E from Q_E and n_E, and ``reaches`` is
    reaches(D_E, n_E) of the module docstring with n = m = n_E and Q = Q_E (never the whole list's Q or n). Returns
    the ``evolution`` block of ``card_decision_evolution``: ``{'item_ids', 'n', 'difference_sum', 'variance_sum',
    'gain_points', 'se_points', 'tau_points', 'better', 'worse', 'tied', 'reaches'}``. Model-side unknown runs stay
    counted on J alone (``unknown_final``): the per-item sums do not say which items held them, and they decide
    nothing (scored 0, O1)."""
    return _evolution_block(_restate(stats, with_subset=False), items)


def card_decision_evolution(stats, evolution):
    """Accept a card under the typed-v3 gate rule ``'evolution'`` (CHAIN-DECISIONS T7) iff (1) reaches(D_E, n_E)
    with tau_E from the baseline's repeats on E, (2) better_E > worse_E, and (3) no_regress(D_J) over all items of
    J exactly as ``no_harm_decision`` defines it. Reasons, checked in this order: ``gain_below_tau``,
    ``not_more_better_than_worse``, ``harm``; else ``accepted``. B = the arm the candidate is compared with.

    ``stats`` is ``repeat_statistics`` over J; ``evolution`` is ``evolution_statistics(stats, ids of E)``, re-derived
    here from J's per_item rows and required to be equal (statistics on E of other runs are refused). The record is
    ``card_decision``'s (kind ``'card'``, the whole-list statistics of J) with this rule's verdict and reason plus
    the ``evolution`` block, from which ``recompute`` reproduces the decision alone.

    Reduction (exact, tested): today's ``card_decision`` has no harm clause, so clause (3) is the only addition.
    With E = J (a step without made items) clause (3) can never fail, because reaches(D, n) requires D >= 0 and
    D >= 0 is a disjunct of no_regress(D); the verdict and the reason are then ``card_decision``'s on every input,
    whether or not no_regress holds. Only the record differs (the ``evolution`` block): a step without made items
    keeps calling ``card_decision``, whose records stay byte-identical to typed-v2's."""
    s = _restate(stats, with_subset=False)
    if not isinstance(evolution, Mapping) or 'item_ids' not in evolution:
        raise ValueError('The statistics on E are evolution_statistics output')
    e = _evolution_block(s, evolution['item_ids'])
    if not _same(dict(evolution), e):
        raise ValueError('The statistics on E do not follow from the per_item list of J')
    reason = ('gain_below_tau' if not e['reaches'] else 'not_more_better_than_worse' if e['better'] <= e['worse']
              else 'harm' if not s['no_regress'] else 'accepted')
    return {'kind': 'card', 'accepted': reason == 'accepted', 'reason': reason, **s, 'evolution': e}


def screen_decision(b, c, *, repeats, items, fired=None):
    """The screen before the R paid runs of a candidate's gate (typed-v3 T7), in integers. ``b``: the baseline's
    right runs over the ``items`` screen items (A + G; R = ``repeats`` runs each, from the arm the candidate is
    compared with), 0..R * items; ``c``: the candidate's right runs in its ONE run per screen item, 0..items;
    ``fired``: None for a card, else (a program or an archive package) the number of screen items on which it fired,
    0..items. A model-side unknown run counts as not right (O1), as in the gate.

    The candidate goes on to its gate iff R * c >= b (its pass count is not below the baseline's mean pass count
    b / R) and, for a program or package, fired >= 1. When both fail the reason is ``screen_never_fired``, checked
    first as in ``program_decision`` (``never_fired`` before the gain): a program that fired on no screen item ran
    as its incumbent there, and its count is a noise reading. Reasons: ``screen_never_fired``,
    ``screen_below_baseline``, ``passed``. The pass rates in points (``baseline_pass_points`` = 100 b / (R items),
    ``candidate_pass_points`` = 100 c / items) are reported and never compared.

    The screen's cells are never used as gate runs: the gate's R runs are all fresh, because a candidate that passed
    the screen by luck would carry that luck into the gate. A step without made items has no screen."""
    R = _repeats(repeats)
    if type(items) is not int or items < 1:
        raise ValueError('The screen runs on at least one item (A + G), got %r' % (items,))
    if type(b) is not int or not 0 <= b <= R * items:
        raise ValueError('b counts the right runs of the baseline over the screen items, an integer in 0..R * items')
    if type(c) is not int or not 0 <= c <= items:
        raise ValueError('c counts the right runs of the candidate (one per screen item), an integer in 0..items')
    if fired is not None and (type(fired) is not int or not 0 <= fired <= items):
        raise ValueError('fired is None for a card, else the number of screen items where it fired, 0..items')
    reason = 'screen_never_fired' if fired == 0 else 'screen_below_baseline' if R * c < b else 'passed'
    return {'kind': 'screen', 'b': b, 'c': c, 'repeats': R, 'items': items, 'fired': fired,
            'baseline_pass_points': 100 * b / (R * items), 'candidate_pass_points': 100 * c / items,
            'passed': reason == 'passed', 'reason': reason}


def screen_counts(baseline_cells, candidate_cells, *, items, baseline_arm, candidate_label, repeats):
    """``(b, c)`` of the screen from the cells of the two arms on the screen items ``items`` (A + G), in integers.

    ``baseline_cells``: the cells that hold the R runs of the arm the candidate is compared with (labels
    ``repeat_labels(baseline_arm, repeats)``, e.g. the step's noise unit or an accepted card's gate arm); read by
    ``arm_runs``, so every one of the R runs of every item must be present and decided. ``candidate_cells``: the
    screen unit's cells, ONE per item at ``candidate_label`` (the chain's single-run cells carry the bare arm name,
    e.g. ``cand_card``). Both map ``(item_id, label)`` to a cell row; other labels are not read. A missing cell, or
    an infrastructure / configuration unknown, raises ``UndecidableRuns`` (counts only), as the gate's rule does; a
    model-side unknown is present and final and counts as not right (O1). These cells are never gate runs (see
    ``screen_decision``)."""
    ids, R = _items(items), _repeats(repeats)
    if type(candidate_label) is not str or not candidate_label:
        raise ValueError('The label of the candidate screen cells is a non-empty string')
    if repeat_of_label(candidate_label) is not None:  # malformed labels raise inside repeat_of_label
        # review of P3a (Codex, 2026-11-15, BLOCKER 1): a repeat label <arm>#<r> names a GATE run; reading one here
        # would let a gate cell stand in for the candidate's screen run. The screen unit's cells carry the bare arm.
        raise ValueError('The candidate screen cells carry the bare arm name of the screen unit (one run per item), '
                         'never a gate repeat label <arm>#<r>, got %r' % (candidate_label,))
    if not isinstance(candidate_cells, Mapping):
        raise TypeError('candidate_cells maps (item_id, label) to a cell row')
    b = sum(arm_runs(baseline_cells, ids, baseline_arm, R)['sums'].values())
    c, missing, infrastructure = 0, 0, 0
    for item in ids:
        row = candidate_cells.get((item, candidate_label))
        if row is None:
            missing += 1
            continue
        if not isinstance(row, Mapping):
            raise TypeError('A cell row is a mapping')
        correct = row.get('correct')
        if correct is True:
            c += 1
        elif correct is None:
            if row.get('infrastructure_unknown') or row.get('configuration_error'):
                infrastructure += 1
        elif correct is not False:
            raise ValueError('Gate scores are binary (addendum O11): correct is True, False or None, got a %s'
                             % type(correct).__name__)
    if missing or infrastructure:
        raise UndecidableRuns(arm_of_label(candidate_label), missing=missing, infrastructure=infrastructure,
                              expected=len(ids))
    return b, c


def class_gains(per_item, classes, repeats):
    """Gains by item class of one decision over J (typed-v3 T7, reported with every decision, deciding nothing).

    ``per_item``: the decision's rows ``[[item, S_B, S_K], ...]``; ``classes``: maps EVERY item of those rows, and
    nothing else, to one of ``ITEM_CLASSES`` (real, attack, guard, calibration); ``repeats``: R. Returns, in this
    order, one row per class ``{'n', 'difference_sum', 'gain_points', 'baseline_runs_correct',
    'candidate_runs_correct'}`` (a class with no item: n = 0, sums 0, ``gain_points`` None) and ``parity``: the
    baseline's pass rate on the calibration items minus its pass rate on the real items, in points
    (``{'calibration_pass_points', 'real_pass_points', 'parity_points'}``, None where a class has no item). The
    integers are exact; the points are floats for the reports, each one division of integers (gain = 100 D / (R n);
    parity = 100 (B_K n_R - B_R n_K) / (R n_K n_R))."""
    R = _repeats(repeats)
    ids, sb, sk = _rows(per_item, R, 3)
    if not isinstance(classes, Mapping):
        raise TypeError('classes maps every item of the gate list to its class')
    if set(classes) != set(ids):
        raise ValueError('The class map holds exactly the items of the per_item rows')
    if any(classes[item] not in ITEM_CLASSES for item in ids):
        raise ValueError('An item class is one of %s' % ', '.join(ITEM_CLASSES))
    out = {}
    for name in ITEM_CLASSES:
        chosen = [j for j, item in enumerate(ids) if classes[item] == name]
        n, D = len(chosen), sum(sk[j] - sb[j] for j in chosen)
        out[name] = {'n': n, 'difference_sum': D, 'gain_points': _gain_points(D, R, n) if n else None,
                     'baseline_runs_correct': sum(sb[j] for j in chosen),
                     'candidate_runs_correct': sum(sk[j] for j in chosen)}
    k, r = out['calibration'], out['real']
    nk, nr, bk, br = k['n'], r['n'], k['baseline_runs_correct'], r['baseline_runs_correct']
    out['parity'] = {'calibration_pass_points': 100 * bk / (R * nk) if nk else None,
                     'real_pass_points': 100 * br / (R * nr) if nr else None,
                     'parity_points': 100 * (bk * nr - br * nk) / (R * nk * nr) if nk and nr else None}
    return out


def _recompute_member(entry):
    """One stored member check rebuilt from its own fields (the chain's fields kept as stored)."""
    if not isinstance(entry, Mapping) or entry.get('kind') != 'member':
        raise ValueError('A member check is a stored member_decision row')
    absent = [key for key in _INPUTS if key not in entry]
    if absent:
        raise ValueError('A member check without %s cannot be recomputed' % ', '.join(absent))
    R = _repeats(entry['repeats'])
    ids, sb, sk = _rows(entry['per_item'], R, 3)
    unknown = _unknown_pair(entry['unknown_final'], len(ids), R, sb, sk)
    stats = repeat_statistics({'sums': dict(zip(ids, sb)), 'squares': dict(zip(ids, sb)), 'unknown': unknown['baseline']},
                              {'sums': dict(zip(ids, sk)), 'squares': dict(zip(ids, sk)), 'unknown': unknown['candidate']},
                              items=ids, repeats=R, minimum_points=entry['minimum_points'],
                              multiplier=entry['multiplier'])
    return {**entry, **member_decision(stats)}


def _recompute_screen(record):
    """One stored screen record (typed-v3 T7) rebuilt from its own inputs (the chain's fields kept as stored)."""
    absent = [key for key in _SCREEN_INPUTS if key not in record]
    if absent:
        raise ValueError('A screen record without %s cannot be recomputed' % ', '.join(absent))
    return {**record, **screen_decision(record['b'], record['c'], repeats=record['repeats'], items=record['items'],
                                        fired=record['fired'])}


# ---- offline check ----------------------------------------------------------------------------------------------
def recompute(record):
    """Rebuild a stored card, program, no-harm, noise or member record from its own fields (``per_item``,
    ``repeats``, ``minimum_points``, ``multiplier``, ``unknown_final``, and ``fired_cells`` for a program). Returns
    the record with every derived field (statistics, ``accepted`` / ``merge``, ``reason``) recomputed and every other
    field as stored, so ``recompute(record) == record`` iff the stored decision is reproduced. A card or program
    record of a shared type (``shared_with``, addendum D16) also gets every member check and the final verdict
    (``accepted``, ``reason``, ``member_harm``) rebuilt by ``shared_verdict``.

    typed-v3 (T7): a card record with an ``evolution`` block is rebuilt by ``card_decision_evolution`` from its
    per_item rows and the stored ids of E (``evolution.item_ids``), the block included; an ``evolution`` block on any
    other kind is refused. A screen record (kind ``'screen'``) is rebuilt by ``screen_decision`` from its ``b``,
    ``c``, ``repeats``, ``items`` and ``fired``: its verdict and its two pass rates. b and c are the screen's inputs,
    so a change of one of them is seen through those pass rates; whether b and c match the cells is checked against
    the cells (``screen_counts``), not from the record. Records without ``evolution`` and of the typed-v2 kinds are
    rebuilt exactly as before."""
    if not isinstance(record, Mapping):
        raise TypeError('recompute takes a stored gate record')
    kind = record.get('kind')
    if kind not in ('card', 'program', 'no_harm', 'noise', 'member', 'screen'):
        raise ValueError('recompute rebuilds card, program, no_harm, noise, member and screen records, got kind %r'
                         % (kind,))
    if 'evolution' in record and kind != 'card':
        raise ValueError('Only a card record carries an evolution block (typed-v3 T7), got kind %r' % (kind,))
    if kind == 'member':
        return _recompute_member(record)
    shared = 'shared_with' in record or 'members' in record or 'member_harm' in record
    if shared and kind not in ('card', 'program'):
        raise ValueError('Only a card or program record carries member checks (addendum D16)')
    if kind == 'screen':
        return _recompute_screen(record)
    home = _recompute_home(record, kind)
    if not shared:
        return home
    members = record.get('members')
    if not isinstance(members, (list, tuple)):
        raise ValueError('A record of a shared type holds the list of its member checks')
    fresh = [_recompute_member(entry) for entry in members]
    return {**home, 'members': fresh, **shared_verdict(home, fresh, record.get('shared_with'))}


def _recompute_home(record, kind):
    """The home part of ``recompute``: the 5w decision of the record's own comparison."""
    absent = [key for key in _INPUTS + (('fired_cells',) if kind == 'program' else ()) if key not in record]
    if absent:
        raise ValueError('A %s record without %s cannot be recomputed' % (kind, ', '.join(absent)))
    R = _repeats(record['repeats'])
    args = {'repeats': R, 'minimum_points': record['minimum_points'], 'multiplier': record['multiplier']}
    if kind == 'noise':
        ids, sb = _rows(record['per_item'], R, 2)
        runs = {'sums': dict(zip(ids, sb)), 'squares': dict(zip(ids, sb)), 'unknown': record['unknown_final']}
        return {**record, **calibration(runs, items=ids, **args)}
    ids, sb, sk = _rows(record['per_item'], R, 3)
    unknown = _unknown_pair(record['unknown_final'], len(ids), R, sb, sk)
    baseline = {'sums': dict(zip(ids, sb)), 'squares': dict(zip(ids, sb)), 'unknown': unknown['baseline']}
    candidate = {'sums': dict(zip(ids, sk)), 'squares': dict(zip(ids, sk)), 'unknown': unknown['candidate']}
    stats = repeat_statistics(baseline, candidate, items=ids, **args)
    if kind == 'card' and 'evolution' in record:  # typed-v3 T7: the card rule on E
        block = record['evolution']
        if not isinstance(block, Mapping) or 'item_ids' not in block:
            raise ValueError('An evolution card record without the ids of E cannot be recomputed')
        return {**record, **card_decision_evolution(stats, evolution_statistics(stats, block['item_ids']))}
    if kind == 'card':
        return {**record, **card_decision(stats)}
    if kind == 'no_harm':
        return {**record, **no_harm_decision(stats)}
    counts = _fired_counts(record['fired_cells'], ids, R)
    fired = [item for item in ids if counts.get(item, 0) > 0]
    fired_stats = repeat_statistics(baseline, candidate, items=ids, subset=fired, **args)
    return {**record, **program_decision(stats, fired_stats, counts)}
