"""typed-v3 decision arithmetic in ``T/gatestats.py`` (CHAIN-DECISIONS T7, brief P3a): the card rule on E = R + A with
tau_E from the baseline's repeats on E, its exact reduction to today's card rule when E = J, the screen's pass rule
and its count helper, gains by item class, and ``recompute`` of the new records. Expected values are computed by hand
(the numbers are in the comments) or independently in fractions.Fraction from 0/1 runs. Plain dicts only: no files,
no network, no fakes."""
import itertools
import json
import math
import random
from fractions import Fraction

import pytest

from skillopt.execskill.typed import gatestats as gs

A, C = 3.0, 2.0  # the caller's tau constants (T/__init__: minimum 3.0 points, multiplier 2.0)
R = 3            # T1: R = 3 fresh runs per item and arm

STATS_KEYS = {'scores', 'repeats', 'n', 'minimum_points', 'multiplier', 'difference_sum', 'variance_sum',
              'gain_points', 'mean_points', 'se_points', 'tau_points', 'better', 'worse', 'tied', 'reaches',
              'no_regress', 'baseline_runs_correct', 'candidate_runs_correct', 'unknown_final', 'excluded_unknown',
              'per_item'}
CARD_KEYS = {'kind', 'accepted', 'reason'} | STATS_KEYS
EVOLUTION_KEYS = {'item_ids', 'n', 'difference_sum', 'variance_sum', 'gain_points', 'se_points', 'tau_points',
                  'better', 'worse', 'tied', 'reaches'}
SCREEN_KEYS = {'kind', 'b', 'c', 'repeats', 'items', 'fired', 'baseline_pass_points', 'candidate_pass_points',
               'passed', 'reason'}
CLASS_ROW_KEYS = {'n', 'difference_sum', 'gain_points', 'baseline_runs_correct', 'candidate_runs_correct'}
PREFIX = {'real': 'r', 'attack': 'a', 'guard': 'g', 'calibration': 'k'}

# one cell row per value: 1 / 0 known, None a final model-side unknown, 'infra' / 'config' the re-run kinds
ROW = {1: {'correct': True}, 0: {'correct': False}, None: {'correct': None, 'token': 'unknown'},
       'infra': {'correct': None, 'infrastructure_unknown': True},
       'config': {'correct': None, 'configuration_error': True}}


# ---- helpers --------------------------------------------------------------------------------------------------------
def runs(sums, unknown=0):
    sums = dict(sums)  # may be a one-shot iterator
    return {'sums': sums, 'squares': dict(sums), 'unknown': unknown}


def gate_list(real, attack=(), guard=(), calibration=()):
    """J = R + A + G + K from per-class lists of (S_B, S_K): (ids in J's order, class map, baseline, candidate)."""
    ids, classes, sb, sk = [], {}, {}, {}
    for name, pairs in (('real', real), ('attack', attack), ('guard', guard), ('calibration', calibration)):
        for j, (b, k) in enumerate(pairs):
            item = '%s-%02d' % (PREFIX[name], j)
            ids.append(item)
            classes[item], sb[item], sk[item] = name, b, k
    return ids, classes, sb, sk


def compare(ids, sb, sk, *, repeats=R, minimum_points=A, multiplier=C, unknown=(0, 0), subset=None):
    return gs.repeat_statistics(runs(((i, sb[i]) for i in ids), unknown[0]), runs(((i, sk[i]) for i in ids), unknown[1]),
                                items=ids, repeats=repeats, minimum_points=minimum_points, multiplier=multiplier,
                                subset=subset)


def e_of(ids, classes):
    return [item for item in ids if classes[item] in gs.EVOLUTION_CLASSES]


def decide(real, attack=(), guard=(), calibration=(), **kw):
    """(statistics over J, today's card decision on J, the typed-v3 card decision on E = R + A, the class map)."""
    ids, classes, sb, sk = gate_list(real, attack, guard, calibration)
    stats = compare(ids, sb, sk, **kw)
    card = gs.card_decision_evolution(stats, gs.evolution_statistics(stats, e_of(ids, classes)))
    return stats, gs.card_decision(stats), card, classes


def roundtrip(record):
    return json.loads(json.dumps(record))


def close(x, y):
    return abs(x - y) <= 1e-9 * max(1.0, abs(y))


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


def reference(sb, sk, chosen, repeats, a, c):
    """The D5 formulas in fractions over the items ``chosen`` AS IF THEY WERE THE SLICE (their own n and their own
    baseline variance), from explicit 0/1 runs: gain >= tau = max(a, c * SE) and gain >= -tau without a square root
    (SE >= 0 and c >= 0, so gain >= c * SE <=> gain >= 0 and gain^2 >= c^2 * SE^2)."""
    n = len(chosen)
    xb = [[1] * sb[i] + [0] * (repeats - sb[i]) for i in chosen]
    mb = [Fraction(sum(r), repeats) for r in xb]
    mk = [Fraction(sk[i], repeats) for i in chosen]
    s2 = [sum(((x - m) ** 2 for x in r), Fraction(0)) / (repeats - 1) for r, m in zip(xb, mb)]
    se2 = Fraction(100) ** 2 * 2 * sum(s2, Fraction(0)) / (repeats * n * n)
    gain = 100 * sum((k - b for b, k in zip(mb, mk)), Fraction(0)) / n
    a, c = Fraction(a), Fraction(c)
    return {'n': n, 's2': sum(s2, Fraction(0)), 'gain': gain,
            'reaches': gain >= a and gain >= 0 and gain ** 2 >= c ** 2 * se2,
            'no_regress': gain >= -a or gain >= 0 or gain ** 2 <= c ** 2 * se2,
            'better': sum(k > b for b, k in zip(mb, mk)), 'worse': sum(k < b for b, k in zip(mb, mk)),
            'tied': sum(k == b for b, k in zip(mb, mk))}


# The running hand case. J = 10 real + 10 attack + 10 guard + 10 calibration items, R = 3. Baseline: on E four items
# at 1 of 3 (q = 3 * 1 - 1^2 = 2 each: Q_E = 8), on K one item at 1 and one at 2 of 3 (q = 2 each: Q_K = 4), every
# other item at 0 or 3 of 3 (q = 0): Q_J = 12. The card lifts five E items (D_R = 4, D_A = 2: D_E = 6, better 5,
# worse 0) and changes nothing on G and K: D_J = 6.
REAL = [(1, 3), (1, 2), (0, 1), (0, 0), (0, 0), (0, 0), (3, 3), (3, 3), (3, 3), (3, 3)]
ATTACK = [(1, 2), (1, 1), (0, 1), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (3, 3), (3, 3)]
GUARD = [(3, 3)] * 10
CALIBRATION = [(1, 1), (2, 2), (0, 0), (0, 0), (3, 3), (3, 3), (3, 3), (0, 0), (0, 0), (3, 3)]
E_IDS = ['r-%02d' % j for j in range(10)] + ['a-%02d' % j for j in range(10)]


# ---- 1. the card rule on E ------------------------------------------------------------------------------------------
def test_a_card_with_a_gain_on_E_above_tau_E_and_no_regression_on_J_is_accepted():
    stats, today, card, _ = decide(REAL, ATTACK, GUARD, CALIBRATION)
    e = card['evolution']
    # on E: n_E = 20, D_E = 6, Q_E = 8: gain_E = 100 * 6 / (3 * 20) = 10 points, se_E = (100 / 60) * sqrt(2 * 8 / 2)
    # = 4.714 points, tau_E = max(3, 2 * se_E) = 9.428 points <= 10. In integers: 100 * 6 >= 3 * 3 * 20 (floor) and
    # 6^2 * 20^2 * (3 - 1) = 28800 >= 2 * 2^2 * 8 * 20^2 = 25600, i.e. 36 >= 32.
    assert e['item_ids'] == E_IDS
    assert (e['n'], e['difference_sum'], e['variance_sum'], e['better'], e['worse'], e['tied']) == (20, 6, 8, 5, 0, 15)
    assert e['gain_points'] == 10.0 and close(e['se_points'], (100 / 60) * math.sqrt(8))
    assert close(e['tau_points'], 2 * (100 / 60) * math.sqrt(8)) and e['reaches'] is True
    # on J: n = 40, D = 6, Q = 12, no_regress (D >= 0)
    assert (card['n'], card['difference_sum'], card['variance_sum'], card['no_regress']) == (40, 6, 12, True)
    assert (card['kind'], card['accepted'], card['reason']) == ('card', True, 'accepted')
    # today's whole-list rule refuses the same card: gain_J = 600 / 120 = 5 points < tau_J = 2 * (100 / 120) *
    # sqrt(12) = 5.77 points (6^2 * 40^2 * 2 = 115200 < 2 * 2^2 * 12 * 40^2 = 153600): G and K dilute the gain
    assert (today['accepted'], today['reason']) == (False, 'gain_below_tau')
    assert close(stats['tau_points'], 2 * (100 / 120) * math.sqrt(12)) and stats['gain_points'] == 5.0
    # the record keeps today's whole-list statistics exactly, plus the block on E
    assert {k: v for k, v in card.items() if k not in ('accepted', 'reason', 'evolution')} == {
        k: v for k, v in today.items() if k not in ('accepted', 'reason')}


def test_the_same_card_with_a_regression_on_guard_items_beyond_tau_J_is_refused_with_harm():
    # no_regress on J (n = 40, Q = 12): 100 D >= -3 * 3 * 40 or D >= 0 or D^2 * 2 <= 2 * 2^2 * 12, i.e. D_J >= -6
    # (-tau_J = -5.77 points; D_J = -6 is -5.0 points, D_J = -7 is -5.83 points)
    at_bound = [(3, 0)] * 4 + [(3, 3)] * 6               # D_G = -12: D_J = 6 - 12 = -6
    beyond = [(3, 0)] * 4 + [(3, 2)] + [(3, 3)] * 5      # D_G = -13: D_J = -7
    held_stats, _, held, _ = decide(REAL, ATTACK, at_bound, CALIBRATION)
    harm_stats, _, harmed, _ = decide(REAL, ATTACK, beyond, CALIBRATION)
    for card, D in ((held, -6), (harmed, -7)):
        e = card['evolution']
        assert card['difference_sum'] == D and card['variance_sum'] == 12
        assert (e['difference_sum'], e['better'], e['worse'], e['reaches']) == (6, 5, 0, True)  # E as before
    assert held['no_regress'] and (held['accepted'], held['reason']) == (True, 'accepted')
    assert held['gain_points'] == -5.0
    assert not harmed['no_regress'] and (harmed['accepted'], harmed['reason']) == (False, 'harm')
    assert close(harmed['gain_points'], -700 / 120) and harmed['gain_points'] < -harmed['tau_points']
    # the harm clause is no_regress on J exactly as no_harm_decision defines it
    assert gs.no_harm_decision(held_stats)['merge'] is True
    assert gs.no_harm_decision(harm_stats)['reason'] == 'harm_beyond_tau'


def test_a_card_whose_gain_sits_only_on_calibration_items_is_refused():
    real, attack = [(b, b) for b, _ in REAL], [(b, b) for b, _ in ATTACK]
    calibration = [(b, 3) for b, _ in CALIBRATION]  # D_K = 2 + 1 + 3 + 3 + 0 + 0 + 0 + 3 + 3 + 0 = 15, better 6
    _, today, card, _ = decide(real, attack, GUARD, calibration)
    # today's rule on J accepts it: gain_J = 1500 / 120 = 12.5 points >= tau_J = 5.77 points, better 6 > worse 0
    assert (today['accepted'], today['difference_sum'], today['better'], today['worse']) == (True, 15, 6, 0)
    # on E nothing moved: gain_E = 0 < tau_E
    e = card['evolution']
    assert (e['difference_sum'], e['gain_points'], e['better'], e['worse'], e['reaches']) == (0, 0.0, 0, 0, False)
    assert (card['accepted'], card['reason']) == (False, 'gain_below_tau')
    # a small gain on E too (one real item 1 -> 3: D_E = 2, 3.3 points, over the 3-point floor but 2^2 < 4 * 8):
    # still refused although the whole list gains 17 runs
    _, today, card, _ = decide([(1, 3)] + real[1:], attack, GUARD, calibration)
    assert today['accepted'] and card['evolution']['difference_sum'] == 2
    assert close(card['evolution']['gain_points'], 200 / 60) and card['reason'] == 'gain_below_tau'


def test_tau_E_comes_from_the_baseline_repeats_on_E_not_on_J():
    # (i) the baseline's variance sits outside E: E as above (Q_E = 8, D_E = 6), all 10 guard items at 2 of 3 and
    # the 10 calibration items at 1 or 2 of 3 (q = 2 each: Q_G = Q_K = 20): Q_J = 48; nothing changes outside E.
    guard, calibration = [(2, 2)] * 10, [(1, 1)] * 5 + [(2, 2)] * 5
    stats, today, card, classes = decide(REAL, ATTACK, guard, calibration)
    e = card['evolution']
    assert (e['variance_sum'], stats['variance_sum'], e['difference_sum'], stats['difference_sum']) == (8, 48, 6, 6)
    # with Q_E: 6^2 >= 4 * 8 = 32, tau_E = 2 * (100 / 60) * sqrt(8) = 9.43 points <= 10 points: ACCEPTED
    assert e['reaches'] and close(e['tau_points'], 2 * (100 / 60) * math.sqrt(8)) and card['reason'] == 'accepted'
    # Q_J on E's n would refuse it: 6^2 * 2 < 2 * 2^2 * 48 (tau 2 * (100 / 60) * sqrt(48) = 23.1 points)
    assert not 6 ** 2 * (R - 1) >= 2 * 2 ** 2 * 48
    # so would the whole list's tau (Q_J and n_J, the fired-subset rule of a program): 6^2 * 40^2 * 2 = 115200 <
    # 2 * 2^2 * 48 * 20^2 = 153600 (gain_E = 10 points < tau_J = 2 * (100 / 120) * sqrt(48) = 11.55 points)
    ids, _, sb, sk = gate_list(REAL, ATTACK, guard, calibration)
    assert compare(ids, sb, sk, subset=E_IDS)['subset_reaches'] is False
    assert close(stats['tau_points'], 2 * (100 / 120) * math.sqrt(48)) and e['gain_points'] < stats['tau_points']
    assert today['reason'] == 'gain_below_tau'

    # (ii) the baseline's variance sits on E alone: ten real items at 1 or 2 of 3 (Q_E = 20), every other item at
    # 0 or 3 (Q_J = Q_E = 20); six real items up by one run: D_E = 6 = D_J, better 6, worse 0.
    real = [(1, 2)] * 3 + [(2, 3)] * 3 + [(1, 1)] * 2 + [(2, 2)] * 2
    attack, calibration = [(0, 0)] * 5 + [(3, 3)] * 5, [(0, 0)] * 5 + [(3, 3)] * 5
    stats, today, card, _ = decide(real, attack, GUARD, calibration)
    e = card['evolution']
    assert (e['variance_sum'], stats['variance_sum'], e['difference_sum'], e['better'], e['worse']) == (20, 20, 6, 6, 0)
    # with Q_E and n_E: 6^2 < 4 * 20 = 80 (gain_E = 10 points < tau_E = 2 * (100 / 60) * sqrt(20) = 14.9): REFUSED
    assert not e['reaches'] and close(e['tau_points'], 2 * (100 / 60) * math.sqrt(20))
    assert card['reason'] == 'gain_below_tau'
    # the whole list's tau would let it through: 6^2 * 40^2 * 2 = 115200 >= 2 * 2^2 * 20 * 20^2 = 64000
    # (gain_E = 10 points >= tau_J = 2 * (100 / 120) * sqrt(20) = 7.45 points)
    ids, _, sb, sk = gate_list(real, attack, GUARD, calibration)
    assert compare(ids, sb, sk, subset=E_IDS)['subset_reaches'] is True
    assert close(stats['tau_points'], 2 * (100 / 120) * math.sqrt(20)) and e['gain_points'] > stats['tau_points']


def test_an_exact_tie_on_E_is_decided_in_integers_not_floats():
    # E = 18 real items at 1 of 3 (Q_E = 36) and 8 attack items at 0: n_E = 26, se_E = (100 / 78) * 6 = 600 / 78,
    # tau_E = 1200 / 78 points; D_E = 12 gives gain_E = 1200 / 78 = tau_E exactly (12^2 * 26^2 * 2 = 194688 =
    # 2 * 2^2 * 36 * 26^2). The calibration items add variance outside E (Q_K = 20), which must not count.
    attack, calibration = [(0, 0)] * 8, [(2, 2)] * 10
    _, _, card, _ = decide([(1, 2)] * 12 + [(1, 1)] * 6, attack, GUARD, calibration)
    e = card['evolution']
    assert (e['n'], e['variance_sum'], e['difference_sum'], card['variance_sum']) == (26, 36, 12, 56)
    assert e['gain_points'] < e['tau_points']  # the floats disagree with the exact tie ...
    assert e['reaches'] and card['reason'] == 'accepted'  # ... and do not decide
    _, _, card, _ = decide([(1, 2)] * 11 + [(1, 1)] * 7, attack, GUARD, calibration)
    assert card['evolution']['difference_sum'] == 11 and card['reason'] == 'gain_below_tau'


def test_better_and_worse_are_counted_on_E():
    # (a) on E: two items 0 -> 3 and three items 3 -> 2 (D_E = 3, Q_E = 0: tau_E = 3 points, gain_E = 10 points),
    # better 2 against worse 3; ten calibration items 0 -> 1 make J's count 12 against 3.
    real, attack = [(0, 3)] * 2 + [(0, 0)] * 3, [(3, 2)] * 3 + [(3, 3)] * 2
    _, today, card, _ = decide(real, attack, (), [(0, 1)] * 10)
    assert (card['evolution']['better'], card['evolution']['worse'], card['evolution']['reaches']) == (2, 3, True)
    assert (card['better'], card['worse'], card['accepted'], card['reason']) == (12, 3, False,
                                                                                 'not_more_better_than_worse')
    assert (today['accepted'], today['reason']) == (True, 'accepted')
    # (b) on E: two items 0 -> 3 (D_E = 6, better 2, worse 0); three guard items 3 -> 2 make J's count 2 against 3,
    # D_J = 3 >= 0 holds no_regress: accepted on E, where today's rule refuses on J's counts
    _, today, card, _ = decide([(0, 3)] * 2 + [(0, 0)] * 3, [(3, 3)] * 5, [(3, 2)] * 3 + [(3, 3)] * 7)
    assert (card['evolution']['better'], card['evolution']['worse'], card['evolution']['difference_sum']) == (2, 0, 6)
    assert (card['better'], card['worse'], card['difference_sum'], card['no_regress']) == (2, 3, 3, True)
    assert (card['accepted'], card['reason']) == (True, 'accepted')
    assert (today['accepted'], today['reason']) == (False, 'not_more_better_than_worse')
    # better == worse on E is not "more better than worse"
    _, _, card, _ = decide([(0, 3), (3, 2), (0, 0)], [(0, 0)], [(3, 3)])
    assert (card['evolution']['better'], card['evolution']['worse']) == (1, 1)
    assert card['evolution']['reaches'] and card['reason'] == 'not_more_better_than_worse'


def test_every_reason_of_the_card_rule_on_E():
    held = [(3, 0)] * 4 + [(3, 3)] * 6
    beyond = [(3, 0)] * 4 + [(3, 2)] + [(3, 3)] * 5
    reasons = {'accepted': decide(REAL, ATTACK, held, CALIBRATION)[2],
               'gain_below_tau': decide([(b, b) for b, _ in REAL], ATTACK, GUARD, CALIBRATION)[2],
               'not_more_better_than_worse': decide([(0, 3)] * 2 + [(0, 0)] * 3, [(3, 2)] * 3, (), [(0, 1)] * 10)[2],
               'harm': decide(REAL, ATTACK, beyond, CALIBRATION)[2]}
    assert set(reasons) == set(gs.EVOLUTION_CARD_REASONS)
    assert gs.EVOLUTION_CARD_REASONS == ('accepted', 'gain_below_tau', 'not_more_better_than_worse', 'harm')
    for reason, card in reasons.items():
        assert card['reason'] == reason and card['accepted'] == (reason == 'accepted') and card['kind'] == 'card'
        assert set(card) == CARD_KEYS | {'evolution'} and set(card['evolution']) == EVOLUTION_KEYS
    # the order: a gain below tau_E is reported before a count or a harm that also fails
    _, _, card, _ = decide([(3, 3)] * 2 + [(0, 0)] * 3, [(3, 2)], [(3, 0)] * 10)
    assert not card['evolution']['reaches'] and not card['no_regress'] and card['reason'] == 'gain_below_tau'
    # counts before harm: D_E = 3 reaches (Q_E = 0), better 1 = worse 1 on E, J loses 30 runs
    _, _, card, _ = decide([(0, 3), (3, 2)] + [(0, 0)] * 3, [(0, 0)] * 5, [(3, 0)] * 10)
    assert card['evolution']['reaches'] and not card['no_regress']
    assert card['reason'] == 'not_more_better_than_worse'


def test_with_E_equal_to_J_the_rule_is_today_s_card_rule_on_every_input():
    """The harm clause is implied when E = J: reaches(D, n) requires D >= 0, which is a disjunct of no_regress(D).
    Verdict and reason equal card_decision's on every input, also where no_regress fails; the statistics on E equal
    the whole list's; only the evolution block is added to the record."""
    seen = dict.fromkeys(gs.CARD_REASONS, 0)
    no_regress_fails = 0
    for (repeats, n), (a, c) in itertools.product(((2, 1), (2, 2), (2, 3), (3, 1), (3, 2), (3, 3), (4, 2)),
                                                  ((A, C), (50.0, 2.0), (0.0, 1.0), (25.0, 0.5), (0.0, 0.0))):
        ids = ['item-%d' % j for j in range(n)]
        for sums in itertools.product(range(repeats + 1), repeat=2 * n):
            sb, sk = dict(zip(ids, sums[:n])), dict(zip(ids, sums[n:]))
            stats = compare(ids, sb, sk, repeats=repeats, minimum_points=a, multiplier=c)
            today = gs.card_decision(stats)
            card = gs.card_decision_evolution(stats, gs.evolution_statistics(stats, ids))
            assert (card['accepted'], card['reason']) == (today['accepted'], today['reason'])
            assert {k: v for k, v in card.items() if k != 'evolution'} == today
            e = card['evolution']
            assert e['item_ids'] == ids and all(e[key] == today[key] for key in EVOLUTION_KEYS - {'item_ids'})
            seen[today['reason']] += 1
            no_regress_fails += not today['no_regress']
    assert min(seen.values()) > 0 and no_regress_fails > 0, (seen, no_regress_fails)


CONSTANTS = [(A, C)] * 6 + [(0.0, 2.0), (3.0, 0.0), (2.5, 1.5), (3, 2), (10.0, 1.0), (0.1, 2.0)]


def test_property_the_rule_on_E_equals_the_D5_formulas_on_E_and_no_regress_on_J():
    """Random J and E: the block on E equals the D5 formulas over E as the slice (fractions, 0/1 runs) and equals
    ``repeat_statistics`` run on E's items directly; the verdict and its reason follow the three clauses in order;
    the record is reproduced by ``recompute`` after a JSON round trip."""
    rng = random.Random(20261115)
    seen = dict.fromkeys(gs.EVOLUTION_CARD_REASONS, 0)
    for _ in range(3000):
        repeats, n = rng.choice((2, 3, 3, 3, 4)), rng.randint(1, 40)
        a, c = rng.choice(CONSTANTS)
        ids = ['item-%03d' % j for j in range(n)]
        chosen = sorted(rng.sample(range(n), rng.randint(1, n)))
        E, in_e = [ids[j] for j in chosen], set(chosen)
        up, down, mixed = rng.random(), rng.random(), rng.random() < 0.3
        on_e_shifts = (3, 3, -1, -1, -1, 0) if mixed else (0, 1, 1, 2, -1)  # mixed: few big gains, more small losses
        sb, sk = {}, {}
        for j, item in enumerate(ids):
            p = rng.choice((0.0, 1.0, rng.random(), rng.random()))
            b = sum(rng.random() < p for _ in range(repeats))
            shift = (rng.choice(on_e_shifts) if rng.random() < up else 0) if j in in_e else (
                rng.choice((0, -1, -2, -3, 1)) if rng.random() < down else 0)
            sb[item], sk[item] = b, min(repeats, max(0, b + shift))
        unknown = (rng.randint(0, n * repeats - sum(sb.values())), rng.randint(0, n * repeats - sum(sk.values())))
        stats = compare(ids, sb, sk, repeats=repeats, minimum_points=a, multiplier=c, unknown=unknown)
        block = gs.evolution_statistics(stats, E)
        card = gs.card_decision_evolution(stats, block)
        on_e, on_j = reference(sb, sk, E, repeats, a, c), reference(sb, sk, ids, repeats, a, c)
        # the block on E: E's own n, D, Q (= R (R - 1) * the baseline's summed sample variances on E), counts, reaches
        assert block['item_ids'] == E and block['n'] == on_e['n'] == len(E)
        assert 100 * Fraction(block['difference_sum'], repeats * len(E)) == on_e['gain']
        assert Fraction(block['variance_sum'], repeats * (repeats - 1)) == on_e['s2']
        assert (block['better'], block['worse'], block['tied'], block['reaches']) == (
            on_e['better'], on_e['worse'], on_e['tied'], on_e['reaches'])
        # ... and repeat_statistics run on E's items alone (E as the slice) gives the same numbers
        direct = compare(E, sb, sk, repeats=repeats, minimum_points=a, multiplier=c)
        assert all(block[key] == direct[key] for key in EVOLUTION_KEYS - {'item_ids'})
        # the verdict: the three clauses, in order
        assert card['no_regress'] == on_j['no_regress']
        expected = ('gain_below_tau' if not on_e['reaches'] else
                    'not_more_better_than_worse' if on_e['better'] <= on_e['worse'] else
                    'harm' if not on_j['no_regress'] else 'accepted')
        assert (card['reason'], card['accepted']) == (expected, expected == 'accepted')
        assert card['evolution'] == block and card['unknown_final'] == {'baseline': unknown[0],
                                                                        'candidate': unknown[1]}
        seen[expected] += 1
        assert gs.recompute(roundtrip(card)) == card
        assert json.dumps(gs.recompute(roundtrip(card))) == json.dumps(card)
    assert min(seen.values()) >= 20, seen  # every clause decided some cases


def test_statistics_on_E_from_other_runs_are_refused():
    stats, _, _, _ = decide(REAL, ATTACK, GUARD, CALIBRATION)
    block = gs.evolution_statistics(stats, E_IDS)
    other_stats, _, _, _ = decide([(b, b) for b, _ in REAL], ATTACK, GUARD, CALIBRATION)  # same items, other runs
    with pytest.raises(ValueError, match='do not follow'):
        gs.card_decision_evolution(stats, gs.evolution_statistics(other_stats, E_IDS))
    for key, value in (('difference_sum', 7), ('variance_sum', 12), ('n', 40), ('reaches', False), ('tau_points', 3.0),
                       ('better', 6), ('tied', 14), ('item_ids', tuple(E_IDS)), ('gain_points', 10)):
        with pytest.raises(ValueError, match='do not follow'):
            gs.card_decision_evolution(stats, {**block, key: value})
    with pytest.raises(ValueError, match='do not follow'):
        gs.card_decision_evolution(stats, {**block, 'unknown_final': {'baseline': 0, 'candidate': 0}})
    for bad in (None, [], E_IDS, {k: v for k, v in block.items() if k != 'item_ids'}):
        with pytest.raises(ValueError, match='evolution_statistics output'):
            gs.card_decision_evolution(stats, bad)
    with pytest.raises(ValueError):  # whole-list statistics that do not follow from their own per_item
        gs.card_decision_evolution({**stats, 'difference_sum': 7}, block)
    ids, _, sb, sk = gate_list(REAL, ATTACK, GUARD, CALIBRATION)
    with pytest.raises(ValueError):  # a fired-subset comparison is not a whole-list comparison
        gs.card_decision_evolution(compare(ids, sb, sk, subset=E_IDS[:2]), block)
    assert gs.card_decision_evolution(roundtrip(stats), roundtrip(block)) == gs.card_decision_evolution(stats, block)


def test_the_ids_of_E_are_items_of_J_non_empty_and_in_J_order():
    stats, _, _, _ = decide(REAL, ATTACK, GUARD, CALIBRATION)
    for bad in ([], E_IDS + ['x-00'], ['x-00'], E_IDS[:3] + [E_IDS[0]], [E_IDS[1], E_IDS[0]], E_IDS[::-1],
                E_IDS[:1] + [''], E_IDS[:1] + [7], ['g-00', 'r-00']):
        with pytest.raises(ValueError):
            gs.evolution_statistics(stats, bad)
    for bad in (set(E_IDS), 'r-00', None, dict.fromkeys(E_IDS, 1)):
        with pytest.raises(TypeError):
            gs.evolution_statistics(stats, bad)
    assert gs.evolution_statistics(stats, tuple(E_IDS)) == gs.evolution_statistics(stats, E_IDS)  # a list is kept
    one = gs.evolution_statistics(stats, ['r-00'])  # a single item (1 -> 3): q = 2, D = 2
    assert (one['item_ids'], one['n'], one['difference_sum'], one['variance_sum'], one['better']) == (
        ['r-00'], 1, 2, 2, 1)
    # E may skip items of J (here every second one) as long as it follows J's order
    ids = [row[0] for row in stats['per_item']]
    assert gs.evolution_statistics(stats, ids[::2])['n'] == 20
    ids_j, _, sb, sk = gate_list(REAL, ATTACK, GUARD, CALIBRATION)
    with pytest.raises(ValueError):
        gs.evolution_statistics(compare(ids_j, sb, sk, subset=E_IDS), E_IDS)  # not a whole-list comparison
    with pytest.raises(ValueError):
        gs.evolution_statistics({**stats, 'variance_sum': 13}, E_IDS)  # does not follow from its per_item


# ---- 2. the screen --------------------------------------------------------------------------------------------------
def test_the_screen_passes_exactly_at_R_times_c_equal_to_b():
    # 10 screen items (A + G), R = 3, the candidate right on 4 of them in its one run
    at = gs.screen_decision(12, 4, repeats=3, items=10)      # R * c = 12 == b
    below = gs.screen_decision(13, 4, repeats=3, items=10)   # R * c = 12 == b - 1
    assert at == {'kind': 'screen', 'b': 12, 'c': 4, 'repeats': 3, 'items': 10, 'fired': None,
                  'baseline_pass_points': 40.0, 'candidate_pass_points': 40.0, 'passed': True, 'reason': 'passed'}
    assert (below['passed'], below['reason']) == (False, 'screen_below_baseline')
    assert below['baseline_pass_points'] == float(Fraction(1300, 30)) and below['candidate_pass_points'] == 40.0
    for fired in (1, 10):  # a program or package that fired: the same count rule
        assert gs.screen_decision(12, 4, repeats=3, items=10, fired=fired)['reason'] == 'passed'
        assert gs.screen_decision(13, 4, repeats=3, items=10, fired=fired)['reason'] == 'screen_below_baseline'
    # review of P3a (Codex, MINOR 2): the comparison is exact for counts beyond float precision. R = 3,
    # c = 2**53, b = 3 * 2**53 + 1 (so R * c = b - 1: refuse); as floats 3 * 2**53 and b coincide and would pass.
    big_c, big_items = 2 ** 53, 2 ** 53 + 1
    big_b = 3 * big_c + 1
    assert float(3 * big_c) == float(big_b)  # the trap the exact rule must not fall into
    assert gs.screen_decision(big_b, big_c, repeats=3, items=big_items)['reason'] == 'screen_below_baseline'
    assert gs.screen_decision(big_b - 1, big_c, repeats=3, items=big_items)['reason'] == 'passed'
    # every small case against the rule in fractions: c / items >= (b / R) / items, the baseline's mean pass count
    for repeats, items in itertools.product((2, 3, 4), range(1, 6)):
        for b, c in itertools.product(range(repeats * items + 1), range(items + 1)):
            passes = Fraction(c) >= Fraction(b, repeats)
            assert gs.screen_decision(b, c, repeats=repeats, items=items)['passed'] is passes
            for fired in range(items + 1):
                found = gs.screen_decision(b, c, repeats=repeats, items=items, fired=fired)
                assert found['passed'] is (passes and fired >= 1)
                assert found['reason'] == ('screen_never_fired' if fired == 0 else 'passed' if passes
                                           else 'screen_below_baseline')


def test_a_program_that_never_fired_on_the_screen_items_fails_the_screen():
    never = gs.screen_decision(0, 10, repeats=3, items=10, fired=0)  # right on every item, the baseline on none
    assert (never['passed'], never['reason'], never['fired']) == (False, 'screen_never_fired', 0)
    both = gs.screen_decision(30, 0, repeats=3, items=10, fired=0)  # both clauses fail: never_fired is reported
    assert both['reason'] == 'screen_never_fired'
    assert gs.screen_decision(30, 0, repeats=3, items=10, fired=4)['reason'] == 'screen_below_baseline'
    assert gs.screen_decision(30, 0, repeats=3, items=10)['reason'] == 'screen_below_baseline'  # a card
    assert set(gs.SCREEN_REASONS) == {'passed', 'screen_never_fired', 'screen_below_baseline'}


def test_the_screen_inputs_are_validated():
    for b, c, extra in ((31, 0, {}), (-1, 0, {}), (0, 11, {}), (0, -1, {}), (True, 0, {}), (0, False, {}),
                        (12.0, 4, {}), (0, 1.0, {}), (0, 0, {'fired': 11}), (0, 0, {'fired': -1}),
                        (0, 0, {'fired': True}), (0, 0, {'fired': 1.0}), (None, 0, {}), (0, '4', {})):
        with pytest.raises(ValueError):
            gs.screen_decision(b, c, repeats=3, items=10, **extra)
    for repeats in (1, 0, True, 3.0, None):
        with pytest.raises(ValueError):
            gs.screen_decision(0, 0, repeats=repeats, items=10)
    for items in (0, -1, True, 10.0, None):
        with pytest.raises(ValueError):
            gs.screen_decision(0, 0, repeats=3, items=items)
    assert gs.screen_decision(30, 10, repeats=3, items=10, fired=10)['passed']  # the upper bounds are allowed


def repeat_cells(arm, table):
    """{(item, '<arm>#<r>'): row} from {item: [value per repeat]}; the value 'missing' leaves the cell out."""
    cells = {}
    for item, values in table.items():
        for label, value in zip(gs.repeat_labels(arm, len(values)), values):
            if value != 'missing':
                cells[(item, label)] = {'item_id': item, 'arm': label, **ROW[value]}
    return cells


def single_cells(label, table):
    """{(item, label): row}: one screen cell per item."""
    return {(item, label): {'item_id': item, 'arm': label, **ROW[value]} for item, value in table.items()}


SCREEN_ITEMS = ['a-00', 'a-01', 'g-00', 'g-01']
BASE = {'a-00': [1, 0, 1], 'a-01': [0, 0, 0], 'g-00': [1, 1, 1], 'g-01': [1, None, 1]}  # b = 2 + 0 + 3 + 2 = 7
CAND = {'a-00': 1, 'a-01': 1, 'g-00': 1, 'g-01': None}                                    # c = 3


def test_screen_counts_b_and_c_from_the_cells_of_both_arms():
    base = repeat_cells('C0', BASE)
    base.update(repeat_cells('F', {item: [1, 1, 1] for item in SCREEN_ITEMS}))  # another arm of the unit: not read
    cand = single_cells('cand_card', CAND)
    cand.update(repeat_cells('cand_card', {'a-01': [0, 0, 0]}))  # gate-style labels of the candidate: not read
    found = gs.screen_counts(base, cand, items=SCREEN_ITEMS, baseline_arm='C0', candidate_label='cand_card',
                             repeats=3)
    # a model-side unknown run is present and final and scores 0 on both sides (O1)
    assert found == (7, 3) and type(found[0]) is int and type(found[1]) is int
    record = gs.screen_decision(*found, repeats=3, items=len(SCREEN_ITEMS))
    assert (record['passed'], record['reason']) == (True, 'passed')  # 3 * 3 = 9 >= 7
    # the baseline may be any arm with R runs
    assert gs.screen_counts(repeat_cells('cand_card', BASE), single_cells('cand_program', CAND), items=SCREEN_ITEMS,
                            baseline_arm='cand_card', candidate_label='cand_program', repeats=3) == (7, 3)
    # review of P3a (Codex, BLOCKER 1): a gate repeat label is never read as the candidate's screen run. One item,
    # R = 3: the baseline right in all three runs (b = 3), the screen cell `cand_card` wrong (c = 0: refuse), a gate
    # cell `cand_card#1` right. Naming the gate cell must raise, not give (3, 1) and a pass.
    one = repeat_cells('C0', {'g-00': [1, 1, 1]})
    both = {**single_cells('cand_card', {'g-00': 0}), **repeat_cells('cand_card', {'g-00': [1, 1, 1]})}
    assert gs.screen_counts(one, both, items=['g-00'], baseline_arm='C0', candidate_label='cand_card',
                            repeats=3) == (3, 0)
    for label in ('cand_card#1', 'cand_card#3', 'cand_program#1'):
        with pytest.raises(ValueError, match='never a gate repeat label'):
            gs.screen_counts(one, both, items=['g-00'], baseline_arm='C0', candidate_label=label, repeats=3)
    for label in ('cand_card#', 'cand_card#0', '#1'):  # malformed labels stay refused
        with pytest.raises(ValueError):
            gs.screen_counts(one, both, items=['g-00'], baseline_arm='C0', candidate_label=label, repeats=3)
    # only the screen items are read
    assert gs.screen_counts(base, single_cells('cand_card', CAND), items=['g-00'], baseline_arm='C0',
                            candidate_label='cand_card', repeats=3) == (3, 1)


def test_screen_counts_refuse_missing_or_undecided_cells_with_counts_only():
    base, cand = repeat_cells('C0', BASE), single_cells('cand_card', CAND)
    kw = {'items': SCREEN_ITEMS, 'baseline_arm': 'C0', 'candidate_label': 'cand_card', 'repeats': 3}
    missing = {key: row for key, row in cand.items() if key != ('a-01', 'cand_card')}
    with pytest.raises(gs.UndecidableRuns) as raised:
        gs.screen_counts(base, missing, **kw)
    error = raised.value
    assert isinstance(error, ValueError)
    assert (error.arm, error.missing, error.infrastructure, error.expected) == ('cand_card', 1, 0, 4)
    assert 'a-01' not in str(error)
    for kind in ('infra', 'config'):
        undecided = {**cand, ('g-01', 'cand_card'): {'item_id': 'g-01', **ROW[kind]}}
        with pytest.raises(gs.UndecidableRuns) as raised:
            gs.screen_counts(base, undecided, **kw)
        assert (raised.value.missing, raised.value.infrastructure, raised.value.expected) == (0, 1, 4)
    # the baseline's R runs of every screen item must all be there
    with pytest.raises(gs.UndecidableRuns) as raised:
        gs.screen_counts(repeat_cells('C0', {**BASE, 'a-00': [1, 'missing', 1]}), cand, **kw)
    assert (raised.value.arm, raised.value.missing, raised.value.expected) == ('C0', 1, 12)
    with pytest.raises(gs.UndecidableRuns) as raised:
        gs.screen_counts(repeat_cells('C0', {**BASE, 'g-00': [1, 'infra', 1]}), cand, **kw)
    assert (raised.value.arm, raised.value.infrastructure) == ('C0', 1)
    with pytest.raises(gs.UndecidableRuns):  # a screen item the baseline never ran on
        gs.screen_counts(base, {**cand, **single_cells('cand_card', {'x-00': 1})}, **{**kw, 'items': SCREEN_ITEMS + ['x-00']})
    for value in (1, 0, 0.5, 'pass'):  # binary scores only (O11)
        with pytest.raises(ValueError, match='binary'):
            gs.screen_counts(base, {**cand, ('a-00', 'cand_card'): {'correct': value}}, **kw)
    for label in ('', '#1', 'cand_card#0', 'cand_card#', None, 7):
        with pytest.raises(ValueError):
            gs.screen_counts(base, cand, **{**kw, 'candidate_label': label})
    with pytest.raises(TypeError):
        gs.screen_counts(base, list(cand.items()), **kw)
    with pytest.raises(TypeError):
        gs.screen_counts(list(base.items()), cand, **kw)
    with pytest.raises(TypeError):
        gs.screen_counts(base, {**cand, ('a-00', 'cand_card'): [True]}, **kw)
    for bad in ({'items': []}, {'items': ['a-00', 'a-00']}, {'repeats': 1}, {'baseline_arm': 'C0#1'}):
        with pytest.raises(ValueError):
            gs.screen_counts(base, cand, **{**kw, **bad})


# ---- 3. gains by item class -----------------------------------------------------------------------------------------
HAND_ROWS = [['r-00', 1, 3], ['r-01', 0, 0], ['r-02', 2, 1], ['r-03', 3, 3], ['a-00', 0, 2], ['a-01', 1, 1],
             ['g-00', 3, 2], ['g-01', 3, 3], ['k-00', 2, 2], ['k-01', 1, 3], ['k-02', 3, 3]]
HAND_CLASSES = {row[0]: {'r': 'real', 'a': 'attack', 'g': 'guard', 'k': 'calibration'}[row[0][0]] for row in HAND_ROWS}


def test_class_gains_on_a_hand_made_case():
    gains = gs.class_gains(HAND_ROWS, HAND_CLASSES, 3)
    assert list(gains) == ['real', 'attack', 'guard', 'calibration', 'parity']
    # real: D = (3 - 1) + 0 + (1 - 2) + 0 = 1 over 4 items: 100 * 1 / 12 = 8.33 points; B 1 + 0 + 2 + 3 = 6, K 7
    assert gains['real'] == {'n': 4, 'difference_sum': 1, 'gain_points': float(Fraction(100, 12)),
                             'baseline_runs_correct': 6, 'candidate_runs_correct': 7}
    # attack: D = 2 + 0 = 2 over 2 items: 33.33 points; guard: D = -1 + 0 over 2 items: -16.67 points
    assert gains['attack'] == {'n': 2, 'difference_sum': 2, 'gain_points': float(Fraction(200, 6)),
                               'baseline_runs_correct': 1, 'candidate_runs_correct': 3}
    assert gains['guard'] == {'n': 2, 'difference_sum': -1, 'gain_points': float(Fraction(-100, 6)),
                              'baseline_runs_correct': 6, 'candidate_runs_correct': 5}
    # calibration: D = 0 + 2 + 0 = 2 over 3 items: 22.22 points; B 2 + 1 + 3 = 6, K 8
    assert gains['calibration'] == {'n': 3, 'difference_sum': 2, 'gain_points': float(Fraction(200, 9)),
                                    'baseline_runs_correct': 6, 'candidate_runs_correct': 8}
    # parity of the baseline: 6 of 9 runs on K = 66.67 points, 6 of 12 on R = 50 points: +16.67 points
    assert gains['parity'] == {'calibration_pass_points': float(Fraction(600, 9)), 'real_pass_points': 50.0,
                               'parity_points': float(Fraction(50, 3))}
    walk_json(gains)
    # the class sums add up to the decision's own D and counts, and the rows of a stored decision are accepted
    sb, sk = {row[0]: row[1] for row in HAND_ROWS}, {row[0]: row[2] for row in HAND_ROWS}
    ids = [row[0] for row in HAND_ROWS]
    decision = gs.card_decision(compare(ids, sb, sk))
    assert sum(gains[name]['difference_sum'] for name in gs.ITEM_CLASSES) == decision['difference_sum'] == 4
    assert sum(gains[name]['n'] for name in gs.ITEM_CLASSES) == decision['n'] == 11
    assert gs.class_gains(roundtrip(decision)['per_item'], HAND_CLASSES, 3) == gains
    # parity is the baseline's alone: another candidate leaves it unchanged
    other = [[item, b, 0] for item, b, _ in HAND_ROWS]
    assert gs.class_gains(other, HAND_CLASSES, 3)['parity'] == gains['parity']


def test_class_gains_report_absent_classes_with_n_zero():
    rows = [row for row in HAND_ROWS if row[0][0] in 'rk']
    gains = gs.class_gains(rows, {row[0]: HAND_CLASSES[row[0]] for row in rows}, 3)
    empty = {'n': 0, 'difference_sum': 0, 'gain_points': None, 'baseline_runs_correct': 0, 'candidate_runs_correct': 0}
    assert gains['attack'] == gains['guard'] == empty and gains['real']['n'] == 4 and gains['calibration']['n'] == 3
    assert gains['parity']['parity_points'] == float(Fraction(50, 3))
    real_only = [row for row in HAND_ROWS if row[0][0] == 'r']
    gains = gs.class_gains(real_only, {row[0]: 'real' for row in real_only}, 3)  # a step without made items: J = R
    assert gains['calibration'] == empty and gains['parity'] == {'calibration_pass_points': None,
                                                                 'real_pass_points': 50.0, 'parity_points': None}
    made_only = [row for row in HAND_ROWS if row[0][0] == 'k']
    gains = gs.class_gains(made_only, {row[0]: 'calibration' for row in made_only}, 3)
    assert gains['real'] == empty and gains['parity'] == {'calibration_pass_points': float(Fraction(600, 9)),
                                                          'real_pass_points': None, 'parity_points': None}
    for name in gs.ITEM_CLASSES:
        assert set(gains[name]) == CLASS_ROW_KEYS


def test_class_gains_inputs_are_validated():
    for classes in ({k: v for k, v in HAND_CLASSES.items() if k != 'k-02'}, {**HAND_CLASSES, 'x-00': 'real'},
                    {**HAND_CLASSES, 'k-02': 'shown'}, {**HAND_CLASSES, 'k-02': None}, {**HAND_CLASSES, 'k-02': 'K'}):
        with pytest.raises(ValueError):
            gs.class_gains(HAND_ROWS, classes, 3)
    with pytest.raises(TypeError):
        gs.class_gains(HAND_ROWS, list(HAND_CLASSES.items()), 3)
    for rows in ([], [['r-00', 4, 0]], [['r-00', 1]], [['r-00', 1, 1], ['r-00', 1, 1]], [['r-00', True, 1]]):
        with pytest.raises(ValueError):
            gs.class_gains(rows, {'r-00': 'real'}, 3)
    for repeats in (1, True, 3.0):
        with pytest.raises(ValueError):
            gs.class_gains(HAND_ROWS, HAND_CLASSES, repeats)
    assert gs.ITEM_CLASSES == ('real', 'attack', 'guard', 'calibration')
    assert gs.EVOLUTION_CLASSES == ('real', 'attack')


# ---- 4. records and recompute ---------------------------------------------------------------------------------------
def evolution_records():
    held = [(3, 0)] * 4 + [(3, 3)] * 6
    beyond = [(3, 0)] * 4 + [(3, 2)] + [(3, 3)] * 5
    return {'accepted': decide(REAL, ATTACK, held, CALIBRATION, unknown=(2, 1))[2],
            'gain_below_tau': decide([(b, b) for b, _ in REAL], ATTACK, GUARD, CALIBRATION)[2],
            'not_more_better_than_worse': decide([(0, 3)] * 2 + [(0, 0)] * 3, [(3, 2)] * 3, (), [(0, 1)] * 10)[2],
            'harm': decide(REAL, ATTACK, beyond, CALIBRATION)[2]}


def test_record_shapes_hold_json_types_only():
    for name, card in evolution_records().items():
        assert card['reason'] == name
        walk_json(card)
        assert set(card) == CARD_KEYS | {'evolution'} and set(card['evolution']) == EVOLUTION_KEYS
        e = card['evolution']
        for key in ('n', 'difference_sum', 'variance_sum', 'better', 'worse', 'tied'):
            assert type(e[key]) is int, (name, key)
        for key in ('gain_points', 'se_points', 'tau_points'):
            assert type(e[key]) is float, (name, key)
        assert type(e['reaches']) is bool and type(e['item_ids']) is list
        assert all(type(item) is str for item in e['item_ids'])
        assert roundtrip(card) == card
    screen = gs.screen_decision(7, 3, repeats=3, items=4, fired=2)
    walk_json(screen)
    assert set(screen) == SCREEN_KEYS and roundtrip(screen) == screen
    assert type(screen['baseline_pass_points']) is float and type(screen['candidate_pass_points']) is float
    assert type(screen['passed']) is bool and gs.screen_decision(7, 3, repeats=3, items=4)['fired'] is None


def chain_fields(record):
    """Fields the chain adds to a stored record; recompute keeps them as stored."""
    return {**record, 'unit': 's3/card-r1', 'round': 1, 'items': record['n'], 'cells': 3 * record['n'],
            'baseline': {'unit': 's3/noise', 'arm': 'C0', 'shared': True}, 'reruns': 0,
            'by_class': {'note': 'informational, kept as stored'}}


def test_recompute_reproduces_an_evolution_card_and_refuses_a_tampered_one():
    for name, card in evolution_records().items():
        stored = roundtrip(chain_fields(card))
        assert gs.recompute(stored) == stored, name
        assert json.dumps(gs.recompute(stored)) == json.dumps(stored), name
        e = stored['evolution']
        tampered = [{**stored, 'evolution': {**e, key: value}} for key, value in (
            ('difference_sum', e['difference_sum'] + 1), ('variance_sum', e['variance_sum'] + 2), ('n', e['n'] - 1),
            ('better', e['better'] + 1), ('worse', e['worse'] + 1), ('tied', e['tied'] - 1),
            ('gain_points', e['gain_points'] + 1.0), ('se_points', e['se_points'] + 0.5),
            ('tau_points', e['tau_points'] + 1.0), ('reaches', not e['reaches']), ('item_ids', e['item_ids'][:-1]))]
        tampered += [{**stored, 'evolution': {**e, 'note': 1}},
                     {**stored, 'accepted': not stored['accepted']},
                     {**stored, 'reason': 'harm' if name != 'harm' else 'accepted'},
                     {**stored, 'tau_points': stored['tau_points'] + 1.0}, {**stored, 'minimum_points': 40.0}]
        rows = [list(row) for row in stored['per_item']]
        rows[0][2] = (rows[0][2] + 1) % (R + 1)  # another valid run sum of the first real item
        tampered.append({**stored, 'per_item': rows})
        for bad in tampered:
            assert gs.recompute(bad) != bad, name
    # the verdict comes from per_item and the stored ids of E, never from a stored flag
    card = evolution_records()['accepted']
    rebuilt = gs.recompute({**card, 'accepted': False, 'reason': 'gain_below_tau'})
    assert (rebuilt['accepted'], rebuilt['reason']) == (True, 'accepted') and rebuilt == card
    for broken in ({**card, 'evolution': None}, {**card, 'evolution': []}, {**card, 'evolution': E_IDS},
                   {**card, 'evolution': {k: v for k, v in card['evolution'].items() if k != 'item_ids'}},
                   {**card, 'evolution': {**card['evolution'], 'item_ids': card['evolution']['item_ids'][::-1]}},
                   {**card, 'evolution': {**card['evolution'], 'item_ids': ['x-00']}},
                   {**card, 'evolution': {**card['evolution'], 'item_ids': []}}):
        with pytest.raises(ValueError):
            gs.recompute(broken)
    with pytest.raises(TypeError):
        gs.recompute({**card, 'evolution': {**card['evolution'], 'item_ids': None}})


def test_recompute_reproduces_a_screen_record_and_sees_a_changed_number():
    record = {**gs.screen_decision(7, 3, repeats=3, items=4, fired=2), 'unit': 's3/card-r1-screen',
              'baseline': {'unit': 's3/noise', 'arm': 'C0'}, 'cells': 4}
    stored = roundtrip(record)
    assert stored['baseline_pass_points'] == float(Fraction(700, 12)) and stored['candidate_pass_points'] == 75.0
    assert gs.recompute(stored) == stored and json.dumps(gs.recompute(stored)) == json.dumps(stored)
    # every one-number change of an input is seen through the verdict or the two pass rates
    for key, value in (('b', 8), ('b', 6), ('c', 2), ('c', 4), ('items', 5), ('repeats', 4), ('fired', 0),
                       ('passed', False), ('reason', 'screen_below_baseline'), ('baseline_pass_points', 58.0),
                       ('candidate_pass_points', 70.0)):
        bad = {**stored, key: value}
        assert gs.recompute(bad) != bad, key
    # only fired >= 1 enters the rule: a fired count of 3 instead of 2 is not a different decision (the chain checks
    # the count against the screen cells)
    assert gs.recompute({**stored, 'fired': 3}) == {**stored, 'fired': 3}
    for name in ('b', 'c', 'repeats', 'items', 'fired'):
        with pytest.raises(ValueError, match='cannot be recomputed'):
            gs.recompute({k: v for k, v in stored.items() if k != name})
    for bad in ({**stored, 'b': 13}, {**stored, 'c': 5}, {**stored, 'repeats': 1}, {**stored, 'fired': 5},
                {**stored, 'shared_with': [{'bench': 'searchqa'}]}, {**stored, 'members': []}):
        with pytest.raises(ValueError):
            gs.recompute(bad)
    card = gs.screen_decision(13, 4, repeats=3, items=10)
    assert gs.recompute(roundtrip(card)) == card and card['reason'] == 'screen_below_baseline'


def test_an_evolution_block_belongs_to_a_card_record_only():
    stats, _, card, _ = decide(REAL, ATTACK, GUARD, CALIBRATION)
    block = card['evolution']
    ids, _, sb, sk = gate_list(REAL, ATTACK, GUARD, CALIBRATION)
    fired = gs.program_decision(stats, compare(ids, sb, sk, subset=E_IDS[:2]), {E_IDS[0]: 3, E_IDS[1]: 1})
    noise = gs.calibration(runs(sb.items()), items=ids, repeats=3, minimum_points=A, multiplier=C)
    member = {**gs.member_decision(stats), 'bench': 'searchqa'}
    for record in (gs.no_harm_decision(stats), fired, noise, member, gs.screen_decision(7, 3, repeats=3, items=4)):
        assert gs.recompute(roundtrip(record)) == record
        with pytest.raises(ValueError, match='evolution'):
            gs.recompute({**record, 'evolution': block})


def test_an_evolution_card_of_a_shared_type_recomputes_with_its_member_checks():
    _, _, home, _ = decide(REAL, ATTACK, GUARD, CALIBRATION)
    shared_with = [{'bench': 'searchqa', 'source': 'src-searchqa'}]

    def member(base, cand):
        items = sorted(base)
        stats = gs.repeat_statistics(runs(base.items()), runs(cand.items()), items=items, repeats=3,
                                     minimum_points=A, multiplier=C)
        return {**gs.member_decision(stats), 'bench': 'searchqa', 'source': 'src-searchqa'}

    hold = member({'m-1': 1, 'm-2': 3}, {'m-1': 1, 'm-2': 3})
    harm = member({'m-1': 3, 'm-2': 3}, {'m-1': 0, 'm-2': 3})  # D = -3 over 2 items, Q = 0: -50 points < -3
    assert hold['no_regress'] and not harm['no_regress']
    record = {**home, 'shared_with': shared_with, 'members': [hold],
              **gs.shared_verdict(home, [hold], shared_with), 'unit': 's3/card-r1'}
    assert (record['accepted'], record['reason'], record['member_harm']) == (True, 'accepted', None)
    assert gs.recompute(roundtrip(record)) == record
    harmed = {**home, 'shared_with': shared_with, 'members': [harm], **gs.shared_verdict(home, [harm], shared_with)}
    assert (harmed['accepted'], harmed['reason'], harmed['member_harm']) == (False, 'member_harm', 'searchqa')
    assert gs.recompute(roundtrip(harmed)) == harmed
    tampered = roundtrip(record)
    tampered['evolution']['better'] = 4
    assert gs.recompute(tampered) != tampered
    # a card refused at home for harm on J carries no member check, and keeps its own reason
    _, _, refused, _ = decide(REAL, ATTACK, [(3, 0)] * 4 + [(3, 2)] + [(3, 3)] * 5, CALIBRATION)
    verdict = gs.shared_verdict(refused, [], shared_with)
    assert verdict == {'accepted': False, 'reason': 'harm', 'member_harm': None}
    stored = roundtrip({**refused, 'shared_with': shared_with, 'members': [], **verdict})
    assert gs.recompute(stored) == stored


def test_default_rules_and_records_are_unchanged():
    stats, today, card, _ = decide(REAL, ATTACK, GUARD, CALIBRATION)
    assert 'evolution' not in today and set(today) == CARD_KEYS
    assert gs.CARD_REASONS == ('accepted', 'gain_below_tau', 'not_more_better_than_worse')
    assert gs.PROGRAM_REASONS == ('accepted', 'never_fired', 'gain_below_tau', 'not_more_better_than_worse', 'harm')
    assert gs.NO_HARM_REASONS == ('merged', 'harm_beyond_tau') and gs.MEMBER_HARM == 'member_harm'
    # a stored typed-v2 card record is rebuilt by today's rule (here: refused), whatever the rule on E would say
    assert gs.recompute(roundtrip(today)) == today and today['reason'] == 'gain_below_tau'
    # the block decides only where it is stored: the accepted typed-v3 record without it no longer reproduces
    stripped = {k: v for k, v in card.items() if k != 'evolution'}
    assert card['accepted'] and gs.recompute(stripped)['reason'] == 'gain_below_tau'
    assert gs.recompute(stripped) != stripped
    with pytest.raises(ValueError, match='screen'):  # the error names every kind recompute knows
        gs.recompute({**today, 'kind': 'typing'})
