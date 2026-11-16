"""typed-v2 gate statistics (step 5s, ``T/gatestats.py``): labels, arm runs, the exact integer forms against the D5
formulas computed in fractions.Fraction (seeded random loops and an exhaustive enumeration of small slices), every
decision reason of DESIGN 3.4, ``recompute`` from the stored record alone, the informational fired-item fields of
the addendum, and the purity of the module. Plain dicts only: no files, no network, no fakes."""
import ast
import importlib.util
import itertools
import json
import math
import random
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from skillopt.execskill.typed import gatestats as gs

A, C = 3.0, 2.0  # the caller's tau constants (T/__init__: minimum 3.0 points, multiplier 2.0)

STATS_KEYS = {'scores', 'repeats', 'n', 'minimum_points', 'multiplier', 'difference_sum', 'variance_sum',
              'gain_points', 'mean_points', 'se_points', 'tau_points', 'better', 'worse', 'tied', 'reaches',
              'no_regress', 'baseline_runs_correct', 'candidate_runs_correct', 'unknown_final', 'excluded_unknown',
              'per_item'}
CARD_KEYS = {'kind', 'accepted', 'reason'} | STATS_KEYS
NO_HARM_KEYS = {'kind', 'merge', 'reason'} | STATS_KEYS
PROGRAM_KEYS = CARD_KEYS | {'fired_items', 'fired_cells', 'difference_sum_fired', 'gain_points_fired', 'better_fired',
                            'worse_fired', 'tied_fired', 'reaches_fired', 'se_points_fired', 'se_points_scaled'}
NOISE_KEYS = {'kind', 'rule', 'scores', 'repeats', 'n', 'minimum_points', 'multiplier', 'variance_sum', 'se_points',
              'tau_points', 'mixed_items', 'runs_correct', 'unknown_final', 'per_item'}
FLOAT_KEYS = {'gain_points', 'mean_points', 'se_points', 'tau_points', 'gain_points_fired', 'se_points_fired',
              'se_points_scaled'}
BOOL_KEYS = {'accepted', 'merge', 'reaches', 'no_regress', 'reaches_fired'}

# one cell row per value: 1 / 0 known, None a final model-side unknown, 'infra' / 'config' the re-run kinds
ROW = {1: {'correct': True}, 0: {'correct': False}, None: {'correct': None, 'token': 'unknown'},
       'infra': {'correct': None, 'infrastructure_unknown': True},
       'config': {'correct': None, 'configuration_error': True}}


def make_cells(arm, table):
    """{(item, '<arm>#<r>'): row} from {item: [value per repeat]}; the value 'missing' leaves the cell out."""
    cells = {}
    for item, values in table.items():
        for label, value in zip(gs.repeat_labels(arm, len(values)), values):
            if value != 'missing':
                cells[(item, label)] = {'item_id': item, 'arm': label, 'infrastructure_unknown': False,
                                        'configuration_error': False, **ROW[value]}
    return cells


def runs(sums, unknown=0):
    sums = dict(sums)  # may be a one-shot iterator
    return {'sums': sums, 'squares': dict(sums), 'unknown': unknown}


def slice_ids(n):
    return ['item-%03d' % j for j in range(n)]


def compare(sb, sk, *, repeats=3, minimum_points=A, multiplier=C, subset=None, unknown=(0, 0)):
    """Statistics from per-item run sums (lists in slice order)."""
    ids = slice_ids(len(sb))
    return gs.repeat_statistics(runs(zip(ids, sb), unknown[0]), runs(zip(ids, sk), unknown[1]), items=ids,
                                repeats=repeats, minimum_points=minimum_points, multiplier=multiplier,
                                subset=None if subset is None else [ids[j] for j in subset])


def program(sb, sk, counts, *, repeats=3, minimum_points=A, multiplier=C):
    """A program decision; ``counts`` = fired count per item position (0..R)."""
    ids = slice_ids(len(sb))
    fired = [j for j, count in enumerate(counts) if count]
    whole = compare(sb, sk, repeats=repeats, minimum_points=minimum_points, multiplier=multiplier)
    on_fired = compare(sb, sk, repeats=repeats, minimum_points=minimum_points, multiplier=multiplier, subset=fired)
    return gs.program_decision(whole, on_fired, {ids[j]: count for j, count in enumerate(counts)})


def roundtrip(record):
    return json.loads(json.dumps(record))


# ---- the D5 formulas in fractions.Fraction, from the 0/1 runs themselves --------------------------------------------
def d5(xb, xk, R, a, c, chosen=None):
    """Item means, the baseline's own s2[i], SE^2 of the whole slice, the gain over the chosen items (all by
    default); gain >= tau = max(a, c * SE) and gain >= -tau without a square root: SE >= 0 and c >= 0, so
    gain >= c * SE <=> gain >= 0 and gain^2 >= c^2 * SE^2."""
    n = len(xb)
    mb = [Fraction(sum(r), R) for r in xb]
    mk = [Fraction(sum(r), R) for r in xk]
    s2 = [sum(((x - m) ** 2 for x in r), Fraction(0)) / (R - 1) for r, m in zip(xb, mb)]
    se2 = Fraction(100) ** 2 * 2 * sum(s2, Fraction(0)) / (R * n * n)
    sel = list(range(n)) if chosen is None else list(chosen)
    a, c = Fraction(a), Fraction(c)
    out = {'s2': s2, 'se2': se2, 'm': len(sel), 'better': sum(mk[i] > mb[i] for i in sel),
           'worse': sum(mk[i] < mb[i] for i in sel), 'tied': sum(mk[i] == mb[i] for i in sel),
           'gain': None, 'reaches': False, 'no_regress': None}
    if sel:
        gain = 100 * sum((mk[i] - mb[i] for i in sel), Fraction(0)) / len(sel)
        out.update(gain=gain, reaches=gain >= a and gain >= 0 and gain ** 2 >= c ** 2 * se2,
                   no_regress=gain >= -a or gain >= 0 or gain ** 2 <= c ** 2 * se2)
    return out


def decimal(value):
    value = Fraction(value)
    return Decimal(value.numerator) / Decimal(value.denominator)


def check_with_square_root(ref, a, c):
    """Third reading of the same rule: tau with a real square root at 80 digits (away from exact ties)."""
    if ref['gain'] is None:
        return
    with localcontext() as ctx:
        ctx.prec = 80
        tau = max(decimal(a), decimal(c) * decimal(ref['se2']).sqrt())
        gain, eps = decimal(ref['gain']), Decimal(10) ** -50
        if abs(gain - tau) > eps:
            assert (gain >= tau) == ref['reaches']
        if abs(gain + tau) > eps:
            assert (gain >= -tau) == ref['no_regress']


def close(x, y):
    return abs(x - y) <= 1e-9 * max(1.0, abs(y))


# ---- labels ---------------------------------------------------------------------------------------------------------
def test_labels_round_trip_and_refusals():
    assert gs.REPEAT_SEP == '#'
    assert gs.repeat_labels('C0', 3) == ('C0#1', 'C0#2', 'C0#3')
    assert gs.repeat_labels('cand_program', 2) == ('cand_program#1', 'cand_program#2')
    for arm in ('C0', 'F', 'cand_card', 'cand_program'):
        for r, label in enumerate(gs.repeat_labels(arm, 5), 1):
            assert gs.arm_of_label(label) == arm and gs.repeat_of_label(label) == r
    for label in ('F', 'C0', 'cand_card', 'C0#2', 'F#1', 'x#y#z', '#1', ''):
        assert gs.arm_of_label(label) == label.split('#', 1)[0]  # DESIGN 3.4, literally
    assert gs.repeat_of_label('F') is None and gs.repeat_of_label('cand_card') is None
    assert gs.repeat_of_label('F#10') == 10 and type(gs.repeat_of_label('F#3')) is int
    for bad in ('F#', 'F#0', 'F#01', 'F#x', '#1', 'F#1#2', 'F#-1', 'F# 1', 'F#٣'):
        with pytest.raises(ValueError):
            gs.repeat_of_label(bad)
    for bad in (None, 3, b'F#1'):
        with pytest.raises(TypeError):
            gs.arm_of_label(bad)
    for arm in ('', 'C0#1', None, 7):
        with pytest.raises(ValueError):
            gs.repeat_labels(arm, 3)


def test_repeats_must_be_at_least_two_everywhere():
    ids = slice_ids(2)
    good = runs(zip(ids, (1, 2)))
    for repeats in (1, 0, -3, True, 3.0, '3', None):
        with pytest.raises(ValueError):
            gs.repeat_labels('F', repeats)
        with pytest.raises(ValueError):
            gs.arm_runs({}, ids, 'F', repeats)
        with pytest.raises(ValueError):
            gs.repeat_statistics(good, good, items=ids, repeats=repeats, minimum_points=A, multiplier=C)
        with pytest.raises(ValueError):
            gs.calibration(good, items=ids, repeats=repeats, minimum_points=A, multiplier=C)
    record = gs.card_decision(compare([1, 2], [2, 2]))
    with pytest.raises(ValueError):
        gs.recompute({**record, 'repeats': 1})


# ---- runs of one arm ------------------------------------------------------------------------------------------------
def test_arm_runs_binary_scores_and_model_side_unknowns():
    table = {'q-1': [1, 0, 1], 'q-2': [None, 0, 0], 'q-3': [1, 1, 1], 'q-4': [None, None, 1]}
    cells = make_cells('C0', table)
    cells[('q-1', 'C0')] = {'correct': True}  # a bare single-run label is not a repeat
    cells.update(make_cells('F', {'q-1': [0, 0, 0]}))  # another arm of the same unit
    found = gs.arm_runs(cells, list(table), 'C0', 3)
    assert found == {'sums': {'q-1': 2, 'q-2': 0, 'q-3': 3, 'q-4': 1},
                     'squares': {'q-1': 2, 'q-2': 0, 'q-3': 3, 'q-4': 1}, 'unknown': 3}
    assert list(found['sums']) == list(table)  # slice order
    assert gs.arm_runs(cells, ['q-3', 'q-1'], 'C0', 3)['sums'] == {'q-3': 3, 'q-1': 2}
    for value in (1, 0, 1.0, 0.5, 'pass', 'True', [True]):  # O11: True, False or None only
        broken = dict(cells)
        broken[('q-1', 'C0#2')] = {'correct': value}
        with pytest.raises(ValueError, match='binary'):
            gs.arm_runs(broken, list(table), 'C0', 3)
    with pytest.raises(TypeError):
        gs.arm_runs(list(cells.items()), list(table), 'C0', 3)


def test_arm_runs_refuses_missing_and_rerun_kinds_with_counts_only():
    table = {'secret-item-a': [1, 'infra', 0], 'secret-item-b': ['config', 'missing', 1], 'secret-item-c': [0, 0, 0]}
    with pytest.raises(gs.UndecidableRuns) as raised:
        gs.arm_runs(make_cells('cand_card', table), list(table), 'cand_card', 3)
    error = raised.value
    assert isinstance(error, ValueError)
    assert (error.arm, error.missing, error.infrastructure, error.expected) == ('cand_card', 1, 2, 9)
    assert 'secret' not in str(error) and '1 of 9 cells missing' in str(error)
    with pytest.raises(gs.UndecidableRuns) as raised:
        gs.arm_runs(make_cells('F', {'a': [1, 1, 'missing']}), ['a', 'b'], 'F', 3)
    assert (raised.value.missing, raised.value.infrastructure) == (4, 0)
    # the model-side unknown is NOT a re-run kind: present, final, scored 0
    assert gs.arm_runs(make_cells('F', {'a': [None, None, None]}), ['a'], 'F', 3) == {
        'sums': {'a': 0}, 'squares': {'a': 0}, 'unknown': 3}


def test_items_and_inputs_are_validated():
    ids = slice_ids(3)
    good = runs(zip(ids, (0, 1, 3)))
    for items in ([], ['a', 'a'], ['a', ''], ['a', 3]):
        with pytest.raises(ValueError):
            gs.repeat_statistics(good, good, items=items, repeats=3, minimum_points=A, multiplier=C)
    with pytest.raises(TypeError):
        gs.repeat_statistics(good, good, items='abc', repeats=3, minimum_points=A, multiplier=C)
    for bad in (runs(zip(ids[:2], (0, 1))), runs(zip(ids, (0, 1, 4))), runs(zip(ids, (0, True, 1))),
                {**good, 'squares': {**good['squares'], ids[0]: 1}}, {**good, 'unknown': 6}, {**good, 'unknown': -1}):
        with pytest.raises(ValueError):
            gs.repeat_statistics(good, bad, items=ids, repeats=3, minimum_points=A, multiplier=C)
    for value in (-1.0, float('inf'), float('nan'), True, '3', None):
        with pytest.raises(ValueError):
            gs.repeat_statistics(good, good, items=ids, repeats=3, minimum_points=value, multiplier=C)
        with pytest.raises(ValueError):
            gs.repeat_statistics(good, good, items=ids, repeats=3, minimum_points=A, multiplier=value)
    for subset in (['nope'], [ids[0], ids[0]]):
        with pytest.raises(ValueError):
            gs.repeat_statistics(good, good, items=ids, repeats=3, minimum_points=A, multiplier=C, subset=subset)
    with pytest.raises(TypeError):
        gs.repeat_statistics(good, good, items=ids, repeats=3, minimum_points=A, multiplier=C, subset=ids[0])
    as_set = gs.repeat_statistics(good, good, items=ids, repeats=3, minimum_points=A, multiplier=C,
                                  subset={ids[2], ids[0]})
    assert as_set['subset'] == [ids[0], ids[2]]  # slice order, whatever the collection


# ---- the integer forms against the D5 formulas ----------------------------------------------------------------------
CONSTANTS = [(A, C)] * 6 + [(0.0, 2.0), (3.0, 0.0), (2.5, 1.5), (3, 2), (10.0, 1.0), (0.1, 2.0)]


def test_property_integer_forms_equal_d5_fractions():
    rng = random.Random(20261112)
    seen = {'accepted': 0, 'rejected': 0, 'merge': 0, 'harm': 0, 'program_accepted': 0, 'fired_reaches': 0}
    for _ in range(2000):
        R, n = rng.choice((2, 3, 3, 3, 4, 5)), rng.randint(1, 30)
        a, c = rng.choice(CONSTANTS)
        level, flip, lost = rng.random(), rng.random() * 0.6, rng.choice((0.0, 0.0, 0.05, 0.25))
        ids = slice_ids(n)
        table_b, table_k = {}, {}
        for item in ids:
            p = rng.choice((0.0, 1.0, level, rng.random()))
            base = [int(rng.random() < p) for _ in range(R)]
            cand = [v if rng.random() > flip else int(rng.random() < 0.6) for v in base]
            table_b[item] = [None if rng.random() < lost else v for v in base]
            table_k[item] = [None if rng.random() < lost else v for v in cand]
        B = gs.arm_runs(make_cells('C0', table_b), ids, 'C0', R)
        K = gs.arm_runs(make_cells('cand_card', table_k), ids, 'cand_card', R)
        xb = [[int(v == 1) for v in table_b[item]] for item in ids]  # a model-side unknown scores 0 (O1)
        xk = [[int(v == 1) for v in table_k[item]] for item in ids]
        args = {'items': ids, 'repeats': R, 'minimum_points': a, 'multiplier': c}
        stats = gs.repeat_statistics(B, K, **args)
        ref = d5(xb, xk, R, a, c)
        check_with_square_root(ref, a, c)
        # the integer sums are the D5 quantities exactly
        assert 100 * Fraction(stats['difference_sum'], R * n) == ref['gain']
        assert Fraction(stats['variance_sum'], R * (R - 1)) == sum(ref['s2'], Fraction(0))
        assert (stats['reaches'], stats['no_regress']) == (ref['reaches'], ref['no_regress'])
        assert (stats['better'], stats['worse'], stats['tied']) == (ref['better'], ref['worse'], ref['tied'])
        assert stats['unknown_final'] == {'baseline': sum(v is None for item in ids for v in table_b[item]),
                                          'candidate': sum(v is None for item in ids for v in table_k[item])}
        # reported floats
        se = float(decimal(ref['se2']).sqrt())
        assert close(stats['gain_points'], float(ref['gain'])) and stats['mean_points'] == stats['gain_points']
        assert close(stats['se_points'], se) and close(stats['tau_points'], max(float(a), float(c) * se))
        # the noise record of the same baseline has the same Q, se and tau
        noise = gs.calibration(B, **args)
        assert (noise['variance_sum'], noise['se_points'], noise['tau_points']) == (
            stats['variance_sum'], stats['se_points'], stats['tau_points'])
        # decisions
        card, no_harm = gs.card_decision(stats), gs.no_harm_decision(stats)
        assert card['accepted'] == (ref['reaches'] and ref['better'] > ref['worse'])
        assert no_harm['merge'] == ref['no_regress']
        seen['accepted' if card['accepted'] else 'rejected'] += 1
        seen['merge' if no_harm['merge'] else 'harm'] += 1
        # a fired subset: D, m and the counts over it, Q and n of the whole slice
        chosen = sorted(rng.sample(range(n), rng.randint(0, n)))
        counts = [rng.randint(1, R) if j in chosen else 0 for j in range(n)]
        fired_stats = gs.repeat_statistics(B, K, subset=[ids[j] for j in chosen], **args)
        sub = d5(xb, xk, R, a, c, chosen)
        check_with_square_root(sub, a, c)
        assert fired_stats['subset_reaches'] == sub['reaches']
        assert (fired_stats['subset_better'], fired_stats['subset_worse'], fired_stats['subset_tied']) == (
            sub['better'], sub['worse'], sub['tied'])
        prog = gs.program_decision(stats, fired_stats, {ids[j]: counts[j] for j in range(n)})
        assert prog['accepted'] == (bool(chosen) and sub['reaches'] and sub['better'] > sub['worse']
                                    and ref['no_regress'])
        seen['program_accepted'] += prog['accepted']
        seen['fired_reaches'] += sub['reaches']
        if chosen:
            m = len(chosen)
            assert 100 * Fraction(prog['difference_sum_fired'], R * m) == sub['gain']
            assert close(prog['gain_points_fired'], float(sub['gain']))
            fired_s2 = sum((ref['s2'][j] for j in chosen), Fraction(0))
            assert close(prog['se_points_fired'], float(decimal(Fraction(100) ** 2 * 2 * fired_s2 / (R * m * m)).sqrt()))
            assert close(prog['se_points_scaled'], stats['se_points'] * math.sqrt(n / m))
            assert prog['fired_cells'] == [[ids[j], counts[j]] for j in chosen]
        # each record is reproduced from itself after a JSON round trip
        for record in (card, no_harm, prog, noise):
            assert gs.recompute(roundtrip(record)) == record
            assert json.dumps(gs.recompute(roundtrip(record))) == json.dumps(record)
    assert min(seen.values()) >= 50, seen  # both sides of every rule were exercised


def test_exhaustive_small_slices_hit_the_exact_boundaries():
    """Every pair of run sums per item for small n: the integer forms equal the Fraction formulas, including the
    exact ties gain == tau on both sides of max(a, c * SE)."""
    ties = {'gain = c * SE >= a': 0, 'gain = a >= c * SE': 0, 'gain = -c * SE <= -a': 0, 'gain = -a <= -c * SE': 0}
    for (R, n), (a, c) in itertools.product(((2, 1), (2, 2), (2, 3), (3, 1), (3, 2), (3, 3), (4, 2)),
                                            ((A, C), (50.0, 2.0), (0.0, 1.0), (25.0, 0.5))):
        exact_a = Fraction(a)
        for sums in itertools.product(range(R + 1), repeat=2 * n):
            sb, sk = list(sums[:n]), list(sums[n:])
            xb = [[1] * s + [0] * (R - s) for s in sb]
            xk = [[1] * s + [0] * (R - s) for s in sk]
            ref = d5(xb, xk, R, a, c)
            stats = compare(sb, sk, repeats=R, minimum_points=a, multiplier=c)
            assert (stats['reaches'], stats['no_regress']) == (ref['reaches'], ref['no_regress'])
            gain, c_se_squared = ref['gain'], Fraction(c) ** 2 * ref['se2']
            on_tau = {'gain = c * SE >= a': gain > 0 and gain ** 2 == c_se_squared and gain >= exact_a,
                      'gain = a >= c * SE': gain == exact_a and gain >= 0 and gain ** 2 >= c_se_squared,
                      'gain = -c * SE <= -a': gain < 0 and gain ** 2 == c_se_squared and gain <= -exact_a,
                      'gain = -a <= -c * SE': gain == -exact_a and gain < 0 and gain ** 2 <= c_se_squared}
            for name, hit in on_tau.items():
                ties[name] += hit
                if hit:  # equality holds on both sides: gain >= tau, gain >= -tau
                    assert stats['no_regress' if name.startswith('gain = -') else 'reaches'], name
    assert min(ties.values()) > 0, ties


# ---- hand cases: floats never decide, the two sides of tau ----------------------------------------------------------
def tie_slice():
    """R = 3, n = 26: 18 baseline items at 1 of 3 (q = 2 each, Q = 36) and 8 at 0 of 3; se = 600/78 points,
    tau = 2 * se = 1200/78 points exactly."""
    return [1] * 18 + [0] * 8


def test_exact_tie_accepted_where_floats_would_reject():
    sb = tie_slice()
    sk = [2] * 12 + [1] * 6 + [0] * 8  # D = 12: gain = 1200/78 points = tau exactly
    stats = compare(sb, sk)
    assert (stats['difference_sum'], stats['variance_sum'], stats['n']) == (12, 36, 26)
    assert stats['gain_points'] < stats['tau_points']  # the floats disagree with the exact tie ...
    card = gs.card_decision(stats)
    assert card['accepted'] and card['reason'] == 'accepted'  # ... and do not decide
    assert gs.card_decision(compare(sb, [2] * 11 + [1] * 7 + [0] * 8))['reason'] == 'gain_below_tau'
    # the fired-subset form: 13 fired items, D_f = 6: gain_f = 600/39 points = the whole-slice tau exactly
    sk = [2] * 6 + [1] * 12 + [0] * 8
    prog = program(sb, sk, [1] * 13 + [0] * 13)
    assert prog['gain_points_fired'] < prog['tau_points'] and prog['reaches_fired']
    assert prog['accepted'] and (prog['fired_items'], prog['difference_sum_fired']) == (13, 6)
    assert program(sb, [2] * 5 + [1] * 13 + [0] * 8, [1] * 13 + [0] * 13)['reason'] == 'gain_below_tau'


def test_minimum_points_boundary_and_eleven_points_case():
    flat = [0] * 100  # Q = 0: tau = the 3-point floor
    at_floor = compare(flat, [1] * 9 + [0] * 91)  # gain = 900/300 = 3.0 points exactly
    assert at_floor['tau_points'] == 3.0 and at_floor['gain_points'] == 3.0
    assert gs.card_decision(at_floor)['accepted']
    assert gs.card_decision(compare(flat, [1] * 8 + [0] * 92))['reason'] == 'gain_below_tau'
    # +11.0 points with 20 better and 9 worse (DESIGN section 5): 2 items 0 -> 3, 18 items 0 -> 2, 9 items 1 -> 0,
    # 20 tied items at 2 of 3 (they add to Q), 51 tied items at 0 or 3
    sb = [0] * 2 + [0] * 18 + [1] * 9 + [2] * 20 + [0] * 26 + [3] * 25
    sk = [3] * 2 + [2] * 18 + [0] * 9 + [2] * 20 + [0] * 26 + [3] * 25
    card = gs.card_decision(compare(sb, sk))
    assert (card['difference_sum'], card['gain_points'], card['better'], card['worse'], card['tied']) == (
        33, 11.0, 20, 9, 71)
    assert card['variance_sum'] == 58 and card['accepted'] and 5.0 < card['tau_points'] < 5.1


def test_no_regress_boundaries():
    sb = tie_slice()
    at_minus_tau = compare(sb, [0] * 12 + [1] * 6 + [0] * 8)  # D = -12: gain = -tau exactly
    assert at_minus_tau['difference_sum'] == -12 and gs.no_harm_decision(at_minus_tau)['merge']
    beyond = compare(sb, [0] * 13 + [1] * 5 + [0] * 8)  # D = -13
    assert gs.no_harm_decision(beyond) == {**gs.no_harm_decision(beyond), 'merge': False, 'reason': 'harm_beyond_tau'}
    flat = [3] * 100  # Q = 0: -tau = -3 points
    assert gs.no_harm_decision(compare(flat, [2] * 9 + [3] * 91))['merge']  # -3.0 points
    assert not gs.no_harm_decision(compare(flat, [2] * 10 + [3] * 90))['merge']  # -3.33 points


# ---- every decision reason of DESIGN 3.4 ----------------------------------------------------------------------------
def test_every_card_reason():
    q0 = [0] * 5 + [3] * 5  # Q = 0
    reasons = {
        'accepted': gs.card_decision(compare(q0, [1] * 2 + [0] * 3 + [3] * 5)),  # +6.7 points, 2 better, 0 worse
        'gain_below_tau': gs.card_decision(compare(q0, q0)),
        # +10 points but 2 better against 3 worse: 0 -> 3 twice, 3 -> 2 three times
        'not_more_better_than_worse': gs.card_decision(compare(q0, [3] * 2 + [0] * 3 + [2] * 3 + [3] * 2)),
    }
    assert set(reasons) == set(gs.CARD_REASONS)
    for reason, card in reasons.items():
        assert card['reason'] == reason and card['accepted'] == (reason == 'accepted') and card['kind'] == 'card'
    assert reasons['not_more_better_than_worse']['reaches']  # the gain alone would pass
    # better == worse is not "more better than worse", whatever the gain
    one_each = gs.card_decision(compare(q0, [3] + [0] * 4 + [2] + [3] * 4))  # D = 2: +6.7 points
    assert (one_each['better'], one_each['worse'], one_each['reaches']) == (1, 1, True)
    assert one_each['reason'] == 'not_more_better_than_worse'
    even = gs.card_decision(compare(q0, [3, 3] + [0] * 3 + [2, 2] + [3] * 3))
    assert (even['better'], even['worse'], even['reason']) == (2, 2, 'not_more_better_than_worse')


def test_every_program_reason():
    n = 30
    sb = [0] * 15 + [3] * 15  # Q = 0, tau = 3 points
    reasons = {
        'accepted': program(sb, [3] * 3 + [0] * 12 + [3] * 15, [3] * 3 + [0] * 27),
        'never_fired': program(sb, [3] * 3 + [0] * 12 + [3] * 15, [0] * n),
        'gain_below_tau': program(sb, [0] * 15 + [3] * 15, [1] * 10 + [0] * 20),
        # fired: two items 0 -> 3, three items 3 -> 2: +20 points on 5 items, 2 better against 3 worse
        'not_more_better_than_worse': program(sb, [3] * 2 + [0] * 13 + [2] * 3 + [3] * 12,
                                              [1] * 2 + [0] * 13 + [2] * 3 + [0] * 12),
        # fired items +100 points, but 15 unfired items 3 -> 2: whole slice -6.7 points < -tau
        'harm': program(sb, [3] * 3 + [0] * 12 + [2] * 15, [1] * 3 + [0] * 27),
    }
    assert set(reasons) == set(gs.PROGRAM_REASONS)
    for reason, decision in reasons.items():
        assert decision['reason'] == reason and decision['accepted'] == (reason == 'accepted')
        assert decision['kind'] == 'program' and set(decision) == PROGRAM_KEYS
    assert reasons['harm']['reaches_fired'] and not reasons['harm']['no_regress']
    assert reasons['not_more_better_than_worse']['reaches_fired']


def test_every_no_harm_reason():
    sb = [1] * 10 + [3] * 10
    merged, harm = gs.no_harm_decision(compare(sb, sb)), gs.no_harm_decision(compare(sb, [0] * 10 + [3] * 10))
    assert {merged['reason'], harm['reason']} == set(gs.NO_HARM_REASONS)
    assert (merged['merge'], merged['reason'], harm['merge'], harm['reason']) == (True, 'merged', False,
                                                                                   'harm_beyond_tau')
    assert set(merged) == NO_HARM_KEYS and merged['kind'] == 'no_harm'


# ---- the fired-item fields of the addendum --------------------------------------------------------------------------
def test_program_fired_fields_are_informational():
    """4 fired items at 1 of 3 (Q_f = 8; the whole slice has Q = 8 too), D_f = 3: gain_f = 25 points, below
    2 * se_points_fired = 47.1 points, and still accepted: the whole-slice tau (6.3 points) decides."""
    sb = [1] * 4 + [0] * 13 + [3] * 13
    sk = [2] * 3 + [1] + [0] * 13 + [3] * 13
    prog = program(sb, sk, [3, 1, 2, 3] + [0] * 26)
    ids = slice_ids(30)
    assert prog['accepted'] and prog['fired_items'] == 4
    assert prog['fired_cells'] == [[ids[0], 3], [ids[1], 1], [ids[2], 2], [ids[3], 3]]
    assert (prog['difference_sum_fired'], prog['better_fired'], prog['worse_fired'], prog['tied_fired']) == (3, 3, 0, 1)
    assert prog['gain_points_fired'] == 25.0
    assert close(prog['se_points_fired'], (100 / 12) * math.sqrt(8))
    assert close(prog['se_points'], (100 / 90) * math.sqrt(8))
    assert close(prog['se_points_scaled'], prog['se_points'] * math.sqrt(30 / 4))
    assert prog['gain_points_fired'] < 2 * prog['se_points_fired'] and prog['tau_points'] < 6.3
    # the fired count above 0 is all that decides (O6): one cell or all three give the same decision
    once = program(sb, sk, [1, 1, 1, 1] + [0] * 26)
    assert {k: v for k, v in once.items() if k != 'fired_cells'} == {
        k: v for k, v in prog.items() if k != 'fired_cells'}
    never = program(sb, sk, [0] * 30)
    assert (never['fired_items'], never['fired_cells'], never['difference_sum_fired']) == (0, [], 0)
    assert never['gain_points_fired'] is None and never['se_points_fired'] is None and never['se_points_scaled'] is None
    assert never['reaches_fired'] is False and never['reason'] == 'never_fired'


def test_decisions_refuse_statistics_that_do_not_follow_from_per_item():
    stats = compare([0] * 5 + [3] * 5, [1] * 2 + [0] * 3 + [3] * 5)
    for key, value in (('reaches', False), ('better', 0), ('difference_sum', 0), ('tau_points', 50.0),
                       ('better', 2.0), ('unknown_final', {'baseline': 0, 'candidate': 0, 'x': 0})):
        with pytest.raises(ValueError):
            gs.card_decision({**stats, key: value})
    rows = [list(row) for row in stats['per_item']]
    rows[5][2] = 0
    with pytest.raises(ValueError):
        gs.card_decision({**stats, 'per_item': rows})
    with pytest.raises(ValueError):
        gs.card_decision({k: v for k, v in stats.items() if k != 'per_item'})
    assert gs.card_decision(roundtrip(stats)) == gs.card_decision(stats)  # stored statistics are fine
    ids = slice_ids(10)
    fired = compare([0] * 5 + [3] * 5, [1] * 2 + [0] * 3 + [3] * 5, subset=[0, 1])
    with pytest.raises(ValueError):
        gs.card_decision(fired)  # a subset is not a whole-slice comparison
    with pytest.raises(ValueError):
        gs.program_decision(stats, stats, {ids[0]: 1})  # no subset in the fired statistics
    other = compare([0] * 5 + [3] * 5, [1] * 3 + [0] * 2 + [3] * 5, subset=[0, 1])
    with pytest.raises(ValueError, match='another comparison'):
        gs.program_decision(stats, other, {ids[0]: 1, ids[1]: 2})
    with pytest.raises(ValueError, match='fired subset'):
        gs.program_decision(stats, fired, {ids[0]: 1})
    for counts in ({ids[0]: 4, ids[1]: 1}, {ids[0]: 1, 'elsewhere': 1}, [[ids[0], 1], [ids[0], 1]],
                   {ids[0]: True, ids[1]: 1}, [[ids[0], 1, 2]]):
        with pytest.raises(ValueError):
            gs.program_decision(stats, fired, counts)
    assert gs.program_decision(stats, fired, [[ids[0], 1], [ids[1], 3]]) == gs.program_decision(
        stats, fired, {ids[0]: 1, ids[1]: 3, ids[2]: 0})


# ---- records and recompute ------------------------------------------------------------------------------------------
def all_records():
    sb = [1] * 4 + [0] * 13 + [3] * 13  # Q = 8, tau = 6.3 points
    sk = [2] * 3 + [1] + [0] * 13 + [3] * 13  # D = 3: +3.3 points
    card = [3] * 4 + [0] * 13 + [3] * 13  # D = 8: +8.9 points
    ids = slice_ids(30)
    noise = gs.calibration(runs(zip(ids, sb), 2), items=ids, repeats=3, minimum_points=A, multiplier=C)
    return {'card accepted': gs.card_decision(compare(sb, card, unknown=(2, 1))),
            'card rejected': gs.card_decision(compare(sb, sb)),
            'no_harm merged': gs.no_harm_decision(compare(sb, sk)),
            'no_harm harm': gs.no_harm_decision(compare(sb, [0] * 4 + [0] * 13 + [1] * 13)),
            'program accepted': program(sb, sk, [3, 1, 2, 3] + [0] * 26),
            'program never fired': program(sb, sk, [0] * 30),
            'noise': noise}


def walk_json(value):
    """Records hold JSON types only: dict with str keys, list (never a tuple), str, int, float, bool, None."""
    if isinstance(value, dict):
        assert all(type(key) is str for key in value)
        for inner in value.values():
            walk_json(inner)
    elif isinstance(value, list):
        for inner in value:
            walk_json(inner)
    else:
        assert value is None or type(value) in (str, int, float, bool), type(value)


def test_record_shapes_hold_json_integers_and_the_design_fields():
    records = all_records()
    for name, record in records.items():
        walk_json(record)
        assert record['scores'] == 'binary' and record['repeats'] == 3
        expected = {'card': CARD_KEYS, 'no_harm': NO_HARM_KEYS, 'program': PROGRAM_KEYS, 'noise': NOISE_KEYS}
        assert set(record) == expected[record['kind']], name
        for key, value in record.items():
            if key in FLOAT_KEYS:
                assert value is None or type(value) is float, (name, key)
            elif key in BOOL_KEYS:
                assert type(value) is bool, (name, key)
            elif key in ('n', 'difference_sum', 'variance_sum', 'better', 'worse', 'tied', 'excluded_unknown',
                         'fired_items', 'difference_sum_fired', 'better_fired', 'worse_fired', 'tied_fired',
                         'baseline_runs_correct', 'candidate_runs_correct', 'mixed_items', 'runs_correct'):
                assert type(value) is int, (name, key)
        width = 2 if record['kind'] == 'noise' else 3
        assert all(len(row) == width and type(row[0]) is str and all(type(s) is int for s in row[1:])
                   for row in record['per_item'])
    card = records['card accepted']
    assert card['accepted'] and not records['card rejected']['accepted']
    assert card['excluded_unknown'] == 0 and card['unknown_final'] == {'baseline': 2, 'candidate': 1}
    assert card['per_item'][:5] == [['item-000', 1, 3], ['item-001', 1, 3], ['item-002', 1, 3], ['item-003', 1, 3],
                                    ['item-004', 0, 0]]
    assert (card['baseline_runs_correct'], card['candidate_runs_correct']) == (43, 51)
    noise = records['noise']
    assert noise['per_item'][0] == ['item-000', 1] and noise['rule'] == 'baseline_repeats'
    assert (noise['n'], noise['variance_sum'], noise['mixed_items'], noise['runs_correct'], noise['unknown_final']) == (
        30, 8, 4, 43, 2)
    assert noise['tau_points'] == card['tau_points'] and noise['se_points'] == card['se_points']


def test_recompute_reproduces_each_decision_from_its_stored_record():
    for name, record in all_records().items():
        stored = roundtrip({**record, 'unit': 's2/card-r1', 'round': 1, 'items': 30, 'cells': 90,
                            'baseline': {'unit': 's2/noise', 'arm': 'C0', 'shared': True}, 'reruns': 0})
        assert gs.recompute(stored) == stored, name
        assert json.dumps(gs.recompute(stored)) == json.dumps(stored), name
        # a stored verdict or statistic that does not follow from per_item is exposed, not trusted
        flipped = 'merge' if record['kind'] == 'no_harm' else 'accepted' if record['kind'] != 'noise' else None
        tampered = [{**stored, 'tau_points': stored['tau_points'] + 1.0}, {**stored, 'minimum_points': 40.0}]
        if flipped:
            tampered.append({**stored, flipped: not stored[flipped]})
        rows = [list(row) for row in stored['per_item']]
        rows[-1][1] = 2
        tampered.append({**stored, 'per_item': rows})
        for bad in tampered:
            assert gs.recompute(bad) != bad, name
    card = all_records()['card accepted']
    rebuilt = gs.recompute({**card, 'accepted': False, 'reason': 'gain_below_tau'})
    assert (rebuilt['accepted'], rebuilt['reason']) == (True, 'accepted')
    for broken in ({'kind': 'card', 'accepted': False, 'reason': 'writer_screens_failed'},
                   {k: v for k, v in card.items() if k != 'unknown_final'},
                   {k: v for k, v in all_records()['program accepted'].items() if k != 'fired_cells'},
                   {**card, 'kind': 'typing'}, {**card, 'per_item': [['a', 4, 0]]},
                   {**card, 'per_item': [['a', 1, 0], ['a', 1, 1]]}, {**card, 'unknown_final': 0}):
        with pytest.raises(ValueError):
            gs.recompute(broken)
    with pytest.raises(TypeError):
        gs.recompute([card])


# ---- the module is pure ---------------------------------------------------------------------------------------------
def test_module_is_pure_and_loads_alone():
    path = Path(gs.__file__)
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source, feature_version=(3, 11))  # Python 3.11 grammar (the real run's interpreter)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, 'no relative import: nothing from T or the frozen machinery'
            imported.add(node.module)
    assert imported <= {'__future__', 'math', 'fractions', 'collections.abc'}
    names = ({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
             | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)})
    assert not names & {'GATE_REPEATS', 'TAU_MIN_POINTS', 'TAU_SE_MULTIPLIER', 'open', 'eval', 'exec', 'compile',
                        '__import__', 'os', 'sys', 'Path', 'random', 'time'}
    assert 'GATE_REPEATS' not in source
    spec = importlib.util.spec_from_file_location('typed2_gatestats_alone', path)
    alone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(alone)  # no package, no sys.path entry of the tree: it still loads
    for record in all_records().values():
        assert alone.recompute(roundtrip(record)) == record
