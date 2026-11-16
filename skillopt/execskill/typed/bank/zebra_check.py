"""ZebraLogic made puzzles put before a solver (BANK-PILOT B31 (f)).

Configurations (the hand card alone, or a card text of a finished run mounted on it) are run on the run's real gate
items AND on the whole judging side of a FINISHED bank of made puzzles in ONE stage: ``spare.stage_spare`` with a
record kind of its own for each solver chain ('maded', 'madeg': the two checks share a root, a bank and the name
'c' of the hand card, never a record), so everything that stage guarantees holds here too (a passing zero-call parity with the run's own
requests on the gate items, every configuration registered before any call on its card, solver, run count and
ordered item list, base and candidates meeting an item in the same minutes, write-once records).

What this module adds (review of 2026-11-14):

- the POPULATION is registered with every configuration: for each item its group (real / made) and its size, and
  the hash of the bank's list. A report groups and stratifies by what was registered, never by what a caller hands
  in, and refuses a bank or gate slice that is not the registered one;
- the made part is always the whole judging side of the finished bank (as many puzzles of every size as of every
  other); the gate slice is the run's own and holds the sizes UNEQUALLY often (6 to 13 of the 100 items of
  typed-v2), so whatever compares made with real items weights the made puzzles of a size by the share of that
  size among the gate items (B31 (h)): a difference of the two groups is then no difference of their sizes;
- the re-judging by the chain-G solver starts only after check D of the same bank was read PARITY and REPRODUCED
  (``check-d.json``, written by the report of the chain-D check), and its reading on made items is withheld when
  the made puzzles are not as hard as the real ones for that solver;
- every report names the sizes the fixed-code comparison of made with real puzzles puts below its line (B31 (d)).

The report reads three things, each with the reading BANK-PILOT fixed before any run: PARITY of difficulty (the pass
rate under the base, made minus real), a KNOWN EFFECT (the gain of a candidate over the base on real and on made
items, and their difference) -- in both, the made puzzles at the sizes of the gate items -- and the chain's gate
rule on the real items (a fresh replication of the run's gate), on the made items and on both (every registered
item counted once, as a chain's gate counts). Intervals resample items within their size, real and made
independently.
"""
from __future__ import annotations

import random

from ..library import canonical_sha256
from . import SEED, SIDES, rejudge, spare, zebra_build
from .oqa_build import BOOTSTRAP_DRAWS, gate_statistics

BENCH = 'zebralogic'
KINDS = {'D': 'maded', 'G': 'madeg'}      # the record kind of a solver chain's check
CHECK_D = 'check-d.json'
CHECK_D_UNIT = 'card-r1'         # B31 (f): check D's candidate is the first card round of chain D's step
WITHHELD = 'NOT INTERPRETABLE: the made puzzles are not as hard as the real ones for this solver'


def population(env, gate):
    """[[item id, 'real' or 'made', size], ...]: the run's gate items followed by the whole judging side of the
    finished bank, and the hash of the bank's list. The gate slice must hold every size of the bank and no other
    size (how often it holds a size is the run's matter: the report weights by it)."""
    plan = zebra_build.made_plan(env)
    made = zebra_build.made_items(env, SIDES[1])
    rows = [[item['task_id'], 'real', item['task']] for item in gate] + [[item['task_id'], 'made', item['task']] for item in made]
    ids = [row[0] for row in rows]
    assert gate and made and len(set(ids)) == len(ids), 'Real gate items and made puzzles, each once'
    counts = {size: sum(item['task'] == size for item in gate) for size in plan['sizes']}
    assert sum(counts.values()) == len(gate) and min(counts.values()) > 0, \
        'The gate slice does not hold every size of the bank and no other size: %s' % counts
    assert all(sum(item['task'] == size for item in made) == plan['count'] - plan['shown'] for size in plan['sizes']), \
        'The judging side of the bank is not whole'
    return gate + made, rows, canonical_sha256(env.read(BENCH, zebra_build.LIST))


def stage_parity(env, tools, gate, cards, step_dir, identity, solver):
    """The zero-call parity of every configuration with its source in the run, on the run's gate items."""
    return spare.stage_parity(env, tools, BENCH, gate, cards, step_dir, identity, kind=KINDS[solver])


def require_check_d(env, bank):
    """B31 (f): the chain-G re-judging starts only after check D of THIS bank was read PARITY and REPRODUCED."""
    assert env.exists(BENCH, CHECK_D), 'Check D of this bank has not been read (zebra-contrast-report of the chain-D check)'
    check = env.read(BENCH, CHECK_D)
    assert check['bank_sha256'] == bank, 'Check D was read on another bank'
    assert check['parity'] == 'PARITY' and check['known_effect'] == 'REPRODUCED', \
        'Check D gave %s and %s: the re-judging on made puzzles does not start' % (check['parity'], check['known_effect'])
    return check


def stage_contrast(env, tools, gate, cards, *, step_dir, identity, runs, solver):
    """The configurations on the run's gate items followed by the whole judging side of the finished bank. Before
    any call: the bank is finished and its comparison with the pool exists, the gate slice holds every size of the
    bank and the judging side is whole, and for the chain-G solver check D of this bank passed; then
    ``spare.stage_spare`` (parity, registration)."""
    assert solver in KINDS, 'A solver chain: G or D'
    items, rows, bank = population(env, gate)
    zebra_build.named_sizes(env)
    if solver == 'G':
        require_check_d(env, bank)
    return spare.stage_spare(env, tools, BENCH, items, cards, step_dir=step_dir, identity=identity, runs=runs,
                             solver=solver, kind=KINDS[solver], extra={'population': rows, 'bank_sha256': bank})


def _interval(draws):
    draws = sorted(draws)
    return [round(draws[int(0.025 * (len(draws) - 1))], 2), round(draws[int(0.975 * (len(draws) - 1))], 2)]


def _strata(ids, size_of):
    table = {}
    for name in ids:
        table.setdefault(size_of[name], []).append(name)
    return [table[size] for size in sorted(table)]


def _resampled(rng, strata):
    return [rng.choice(names) for names in strata for _ in names]


def contrast_report(env, base, cand, gate, solver):
    """Candidate against base (of the check of ``solver``'s chain) on the population both are registered on, which must be this gate
    slice and this bank. INCOMPLETE while an item lacks a record under either. Else: pass rates and gains by group
    ('real', 'made', 'both': every item counted once) and by size, the chain's gate rule per group, the made
    puzzles at the sizes of the gate items (each size weighted by its share of the gate items: what PARITY and
    the KNOWN EFFECT compare with the real items), the sizes the bank's comparison names, and the readings. The
    report of the chain-D check on the first card round also writes ``check-d.json``."""
    kind = KINDS[solver]
    first, second = rejudge.registered(env, BENCH, kind, base), rejudge.registered(env, BENCH, kind, cand)
    refusal = rejudge.comparable(first, second)
    assert refusal is None, 'No report: ' + refusal
    assert first['solver'] == solver, 'The records of this kind are of another solver'
    _, rows, bank = population(env, gate)
    assert first.get('population') == rows == second.get('population') and first['items'] == [row[0] for row in rows] \
        and first.get('bank_sha256') == bank == second.get('bank_sha256'), \
        'The configurations are registered on another population than this gate slice and this bank'
    ids, repeats = first['items'], first['runs']
    real_ids, made_ids = [row[0] for row in rows if row[1] == 'real'], [row[0] for row in rows if row[1] == 'made']
    size_of = {row[0]: row[2] for row in rows}
    rows_b = rejudge.complete_rows(first, spare._records(env, BENCH, base, kind))
    rows_k = rejudge.complete_rows(second, spare._records(env, BENCH, cand, kind))
    out = {'bench': BENCH, 'base': base, 'candidate': cand, 'solver': first['solver'], 'repeats': repeats,
           'items': {'real': len(real_ids), 'made': len(made_ids)}, 'bank_sha256': bank,
           'base_card_sha256': first['card_sha256'], 'candidate_card_sha256': second['card_sha256'],
           'origin': {'step_dir': first['origin']['step_dir'], 'base_unit': first['origin']['unit'],
                      'candidate_unit': second['origin']['unit']},
           'sizes_named_by_the_comparison_of_made_with_real_puzzles': zebra_build.named_sizes(env),
           'complete': rows_b is not None and rows_k is not None,
           'note': 'the card is mounted on every item; a run mounts it on the items routed into its type'}
    if not out['complete']:
        have = lambda config: len(set(ids) & set(spare._records(env, BENCH, config, kind)))
        out.update({'records': {'base': have(base), 'candidate': have(cand)}, 'reading': 'INCOMPLETE'})
        return out
    runs_b = {row['id']: [run['verdict'] == 'pass' for run in row['runs']] for row in rows_b}
    runs_k = {row['id']: [run['verdict'] == 'pass' for run in row['runs']] for row in rows_k}
    rate = lambda runs, names: 100.0 * sum(sum(runs[name]) for name in names) / (repeats * len(names))
    gain = lambda names: rate(runs_k, names) - rate(runs_b, names)
    rng = random.Random('%d:zebra-contrast:%s:%s' % (SEED, base, cand))
    strata = {'real': _strata(real_ids, size_of), 'made': _strata(made_ids, size_of)}
    drawn = [(_resampled(rng, strata['real']), _resampled(rng, strata['made'])) for _ in range(BOOTSTRAP_DRAWS)]
    groups = {}
    for name, names, pick in (('real', real_ids, lambda pair: pair[0]), ('made', made_ids, lambda pair: pair[1]),
                              ('both', ids, lambda pair: pair[0] + pair[1])):
        groups[name] = {'items': len(names), 'base_pass_pct': round(rate(runs_b, names), 2),
                        'candidate_pass_pct': round(rate(runs_k, names), 2), 'gain_points': round(gain(names), 2),
                        'gain_interval_95': _interval([gain(pick(pair)) for pair in drawn]),
                        'gate_rule': gate_statistics(runs_b, runs_k, names)}
    by_size = {}
    for group, names in (('real', real_ids), ('made', made_ids)):
        for part in _strata(names, size_of):
            by_size.setdefault(size_of[part[0]], {})[group] = {
                'items': len(part), 'base_pass_pct': round(rate(runs_b, part), 1),
                'candidate_pass_pct': round(rate(runs_k, part), 1)}
    # made against real: the made puzzles of a size weigh what that size weighs among the gate items (B31 (h))
    share = {size: sum(size_of[name] == size for name in real_ids) / len(real_ids) for size in sorted(set(size_of.values()))}

    def at_gate_sizes(runs, names):
        table = {}
        for name in names:
            table.setdefault(size_of[name], []).append(name)
        return sum(share[size] * rate(runs, table[size]) for size in share)
    made_gain = lambda names: at_gate_sizes(runs_k, names) - at_gate_sizes(runs_b, names)
    weighted = {'weights': {size: round(share[size], 4) for size in share},
                'base_pass_pct': round(at_gate_sizes(runs_b, made_ids), 2),
                'candidate_pass_pct': round(at_gate_sizes(runs_k, made_ids), 2),
                'gain_points': round(made_gain(made_ids), 2),
                'gain_interval_95': _interval([made_gain(pair[1]) for pair in drawn])}
    harder = at_gate_sizes(runs_b, made_ids) - rate(runs_b, real_ids)
    harder_interval = _interval([at_gate_sizes(runs_b, pair[1]) - rate(runs_b, pair[0]) for pair in drawn])
    parity = 'PARITY' if harder_interval[0] <= 0 <= harder_interval[1] else 'EASIER' if harder > 0 else 'HARDER'
    effect = made_gain(made_ids) - gain(real_ids)
    effect_interval = _interval([made_gain(pair[1]) - gain(pair[0]) for pair in drawn])
    made_low, made_high = weighted['gain_interval_95']
    same_sign = weighted['gain_points'] * groups['real']['gain_points'] > 0
    known = 'REPRODUCED' if same_sign and not made_low <= 0 <= made_high \
        and effect_interval[0] <= 0 <= effect_interval[1] else 'NOT REPRODUCED'
    read = lambda name: spare.reading(groups[name]['gate_rule'], groups[name]['gain_interval_95'])
    out.update({
        'groups': groups, 'by_size': {size: by_size[size] for size in sorted(by_size)},
        'made_at_the_sizes_of_the_gate_items': weighted,
        'wrong_runs_without_a_complete_reply': {'base': spare._incomplete(rows_b), 'candidate': spare._incomplete(rows_k)},
        'parity': {'base_pass_made_minus_real_points': round(harder, 2), 'interval_95': harder_interval, 'reading': parity},
        'known_effect': {'gain_made_minus_gain_real_points': round(effect, 2), 'interval_95': effect_interval,
                         'reading': known},
        'rejudging': {'on_real_items': read('real'),
                      'on_real_and_made_items': read('both') if parity == 'PARITY' else WITHHELD},
        'intervals': 'items resampled within their size, real and made independently, %d draws, seeded' % BOOTSTRAP_DRAWS})
    if solver == 'D' and second['origin']['unit'] == CHECK_D_UNIT:
        check = {'bank_sha256': bank, 'base': base, 'candidate': cand, 'candidate_card_sha256': second['card_sha256'],
                 'step_dir': first['origin']['step_dir'], 'parity': parity, 'known_effect': known,
                 'base_pass_made_minus_real_points': out['parity']['base_pass_made_minus_real_points'],
                 'gain_points': {'real': groups['real']['gain_points'],
                                 'made_at_the_sizes_of_the_gate_items': weighted['gain_points']}}
        assert env.once((BENCH, CHECK_D), lambda: check) == check, 'Check D of this root was read differently before'
        out['check_d_recorded'] = True
    return out
