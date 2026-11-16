"""Re-judging a card on SPARE real practice items (design section 11 step 2; BANK-PILOT B28).

A bench whose pinned practice pool is larger than the two slices a typed run drew from it (ZebraLogic: 327 of 500
left; SearchQA: 400 of 600) needs no made items to judge a card on more items: the pool items that are in neither
slice are real, no writer of the run saw them, and they continue the very ranking the gate slice was cut from
(``prepare.draw_slices``: the first ``learn`` ids of the seeded ranking, then ``gate``; the spare items are the rest,
in that order, so the first N of them are as exchangeable with the gate slice as the gate slice is with itself).

A configuration is a system card (the hand card C, or a card text mounted on it by ``typed.mount.system_card``, the
text taken verbatim). Each spare item is solved R times under it through the chain's own cell function
(``typed.mount.solve``: the route-B shell with an empty package, the benchmark's judge), and two configurations are
compared by the chain's gate rule (``typed.gatestats`` through ``oqa_build.gate_statistics``). The card is mounted on
EVERY spare item, while a run mounts it on the items its type map routes into the card's type: the report states
this difference.

Before any call: the parity record (``rejudge``: the requests built here for the run's gate items are the requests
the run sent) and the configuration records (one card, one solver, one run count, one ordered item list per name).
A report decides only when both configurations hold a record for every registered item.

Nothing here reads a test-side file, changes a run, or decides anything in a run: the result is a post-hoc reading of
a card a finished run did not accept.
"""
from __future__ import annotations

import random
import re
import time

from .. import GATE_REPEATS, units
from ..units import sha256_text
from . import SEED, rejudge, report
from .env import text_sha256
from .oqa_build import BOOTSTRAP_DRAWS, CONFIG_NAME, NO_REPLY, gate_statistics

SPARE_BENCHES = ('searchqa', 'zebralogic')   # text benches (no sandbox, no machine lock) with unused pool items
BASE_CONFIG = 'c'                            # the hand card alone: the base of every learned mount (addendum D17)
KIND = 'spare'
KIND_NAME = re.compile(r'[a-z]{2,12}')
BASE_UNIT = 'noise'                          # the step's unit that ran the learning base (arm B) on the gate slice
PREFIXES = (100, 200)                        # the gate rule is also given on the first items of the ranking


def stem(task_id):
    """The file name of an item's record and the tag of its calls: a hash, never the id itself (real item ids may
    hold words the path guard refuses, and a path must not depend on them)."""
    return sha256_text(task_id)[:32]


def spare_items(manifest, bench, *, load_pool, ranked, slice_tag):
    """The items of the pinned practice pool of ``bench`` that are in NEITHER slice of the typed run, in the run's
    own seeded ranking (the continuation of its gate slice). ``load_pool`` / ``ranked`` / ``slice_tag``:
    ``typed.prepare.load_pool``, ``coevo5.data.ranked`` and ``typed.prepare.SLICE_TAG`` (passed in: this module
    imports no frozen machinery). The ranking is proved to be the run's: its first ids are the manifest's slices,
    which have their registered sizes (the caller verified the manifest against its seal)."""
    assert bench in SPARE_BENCHES, 'A bench with spare practice items: ' + str(SPARE_BENCHES)
    pin = manifest['pools'][bench]
    items, _ = load_pool(bench, manifest['pools_root'], pin={'path': pin['path'], 'sha256': pin['sha256']})
    order = [item['task_id'] for item in ranked(items, manifest['seed'], slice_tag % bench)]
    learn, gate = manifest['slices'][bench]['learn'], manifest['slices'][bench]['gate']
    sizes = manifest['slice_sizes'][bench]
    assert len(learn) == sizes['learn'] and len(gate) == sizes['gate'], \
        'The slices of %s do not have their registered sizes' % bench
    assert order[:len(learn)] == list(learn) and order[len(learn):len(learn) + len(gate)] == list(gate), \
        'The ranking of the %s pool is not the one the run cut its slices from' % bench
    by_id = {item['task_id']: item for item in items}
    return [by_id[name] for name in order[len(learn) + len(gate):]]


def gate_items(manifest, bench, *, load_pool):
    """The run's gate slice of ``bench`` (the items its gates judged on), in slice order."""
    pin = manifest['pools'][bench]
    items, _ = load_pool(bench, manifest['pools_root'], pin={'path': pin['path'], 'sha256': pin['sha256']})
    by_id = {item['task_id']: item for item in items}
    return [by_id[name] for name in manifest['slices'][bench]['gate']]


def forced_mount(mount, bench, item, card_text, runtime):
    """The mount record of one item with the system card of a configuration: arm C (the hand card alone) without a
    card text, else the text mounted on the hand card exactly as a run mounts a learned card
    (``mount.system_card``, base 'historical') -- on this item whatever its type would be. No program is enabled."""
    record = mount.mount(bench, item, arm='C', typemap=None, library=None, vector=None, runtime=runtime)
    if card_text is None:
        return record
    assert type(card_text) is str and card_text.strip(), 'A card text'
    system = mount.system_card(bench, card_text, base_card='historical')
    record.update({'arm': 'cand_card', 'card_text': card_text, 'system_card': system,
                   'system_card_sha256': sha256_text(system), 'candidate': {'forced_on_every_item': True}})
    return record


def system_card_of(mount, bench, card_text):
    return mount.historical_card(bench) if card_text is None else mount.system_card(bench, card_text,
                                                                                    base_card='historical')


def card_shas(tools, bench, cards):
    """{configuration: sha256 of its system card}; the names and the base's meaning are checked here."""
    assert bench in SPARE_BENCHES and cards and all(CONFIG_NAME.fullmatch(name) for name in cards), \
        'A text bench of this tool and configuration names of lower-case letters and digits'
    assert all((name == BASE_CONFIG) == (text is None) for name, text in cards.items()), \
        'The configuration "c" is the hand card alone, and only it'
    shas = {name: text_sha256(system_card_of(tools['mount'], bench, text)) for name, text in cards.items()}
    assert len(set(shas.values())) == len(shas), 'Two configurations with one system card'
    return shas


def solve_run(env, tools, bench, item, mounted, unit, tag):
    """One run of one spare item: the chain's cell (``mount.solve``) on the bank's recorded solver call. Returns
    {'verdict': pass / fail / unknown, 'token', 'label', 'replied', 'flags'}. The verdict is the cell's: the judge
    scores a reply the model cut or withheld as wrong, and a cell left unknown for a model-side reason is a FINAL
    wrong run as in a gate arm (gatestats: scored 0, never run again; ``label`` NO_REPLY); an infrastructure or
    configuration unknown leaves the item open (the stage is run again). ``replied``: the cell holds a reply text;
    ``flags``: the judge's flags (such as 'truncated')."""
    cell = tools['mount'].solve(bench, item, mounted, call=env.solver_call(unit, tag), runtime=tools['runtime'],
                                worker_factory=None, native=None, nominal_tokens=tools.get('nominal_tokens'),
                                unit=unit, tag=tag, scorer_root=None, mode='run', step='bank/' + unit, episodes=None)
    if cell['correct'] is None:
        # the gate's own rule (gatestats.arm_runs): an unknown that is neither an infrastructure nor a
        # configuration unknown is a final model-side verdict, scored 0 and never run again
        if cell.get('configuration_error') or cell.get('infrastructure_unknown'):
            return {'verdict': 'unknown', 'token': cell.get('token'),
                    'reason': str(cell.get('failure') or cell.get('reason'))[:120]}
        return {'verdict': 'fail', 'token': cell.get('token'), 'label': NO_REPLY, 'replied': False, 'flags': []}
    return {'verdict': 'pass' if cell['correct'] else 'fail', 'token': cell.get('token'), 'label': None,
            'replied': bool(cell.get('reply')), 'flags': sorted(cell.get('flags') or [])}


def stage_spare(env, tools, bench, items, cards, *, step_dir, identity, runs=GATE_REPEATS, solver='G', kind=KIND,
                extra=None):
    """The configurations ``cards`` ({name: card text, or None for the hand card alone, whose name is 'c'}) on the
    spare ``items`` of ``bench``, ``runs`` fresh runs per item and configuration. (``kind`` names the records:
    'spare' here; 'made' when ``zebra_check`` hands in the run's gate items together with made puzzles, and then
    ``extra`` holds what else every configuration is registered on: the group and size of each item and the hash of
    the bank.) Before any call: the parity record
    must be of the run's learning step ``step_dir`` and of this request ``identity`` and cover every configuration
    with the card it mounts (``rejudge.require_parity``), and every configuration is registered on its card, solver,
    run count, origin (step, source unit, role) and the ordered item ids (``rejudge.register``). The tasks are
    ordered item by item, the configurations of one item in a seeded order of their own (as a gate unit orders its
    arms): base and candidates meet an item in the same minutes, so a drift of the service over the hours of a stage
    is not read as a difference between configurations. Records ``<bench>/spare-<config>/<hash of the id>.json``,
    write-once."""
    assert type(runs) is int and 2 <= runs <= 5, 'Two to five runs per item (the gate rule needs two)'
    shas = card_shas(tools, bench, cards)
    assert KIND_NAME.fullmatch(kind), 'A kind of records: lower-case letters'
    extra = dict(extra or {})
    assert not set(extra) & {'card_sha256', 'solver', 'runs', 'origin', 'bench', 'config', 'items'}, \
        'Extra registration fields may not replace the stage\'s own'
    origins = rejudge.require_parity(env, bench, kind, shas, step_dir, identity)
    ids = [item['task_id'] for item in items]
    for config in sorted(cards):
        rejudge.register(env, bench, kind, config, {**extra, 'card_sha256': shas[config], 'solver': solver,
                                                    'runs': runs, 'origin': origins[config]}, ids)
    names = sorted(cards)
    tasks = [(item, config) for item in items
             for config in random.Random('%d:%s-order:%s' % (SEED, kind, item['task_id'])).sample(names, len(names))]

    def work(task):
        item, config = task
        name, unit = item['task_id'], '%s/%s-%s' % (bench, kind, config)

        def compute():
            mounted = forced_mount(tools['mount'], bench, item, cards[config], tools['runtime'])
            made = [solve_run(env, tools, bench, item, mounted, unit, '%s-r%d' % (stem(name), run))
                    for run in range(1, runs + 1)]
            if any(run['verdict'] == 'unknown' for run in made):
                raise RuntimeError('unknown solver run')
            return {'id': name, 'bench': bench, 'config': config, 'card_sha256': shas[config], 'solver': solver,
                    'runs': made, 'passes': sum(run['verdict'] == 'pass' for run in made),
                    'finished_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        try:
            row = env.once((bench, '%s-%s' % (kind, config), stem(name) + '.json'), compute)
            assert row['id'] == name and row['card_sha256'] == shas[config] and row['solver'] == solver \
                and len(row['runs']) == runs, 'The record of %s is not of the configuration %s' % (stem(name), config)
            return '%s: %d of %d' % (config, row['passes'], runs)
        except units.Stop:
            raise
        except RuntimeError:
            return '%s: unknown' % config
    return {'bench': bench, 'configurations': shas, 'solver': solver, 'runs': runs, 'items': len(items),
            'results': report.tally(env.fan(tasks, work, label=kind + ' ' + ','.join(names)))}


def _records(env, bench, config, kind=KIND):
    folder = env.path(bench, '%s-%s' % (kind, config))
    return {row['id']: row for row in (units.read_json(path) for path in sorted(folder.glob('*.json')))} \
        if folder.is_dir() else {}


def _incomplete(rows):
    """Wrong runs of a configuration whose reply the model cut, withheld or never gave (they count as wrong, as in
    a gate arm; the count shows how much of a difference is output length rather than reasoning)."""
    return sum(run['verdict'] == 'fail' and (not run.get('replied') or 'truncated' in (run.get('flags') or []))
               for row in rows for run in row['runs'])


def spare_report(env, bench, base, cand):
    """Candidate configuration against base on the items BOTH are registered on (``rejudge.comparable``: the run's
    base and a candidate of a card round of the same learning step and request construction, the same ordered item
    list, solver and run count: anything else is refused). While an item of that list lacks a record under either
    configuration there is no decision (``complete`` False, ``reading`` INCOMPLETE): an item that failed for an
    infrastructure reason must never drop out of the judged population. Complete: the chain's gate rule (tau from
    the base's own repeats; accepted when the gain reaches tau and more items got better than worse), the pass
    rates, a 95 % interval of the gain from resampling ITEMS (spare items are separate real items: each is its own
    cluster), and the rule on the first 100 and 200 items of the ranking."""
    first, second = rejudge.registered(env, bench, KIND, base), rejudge.registered(env, bench, KIND, cand)
    refusal = rejudge.comparable(first, second)
    assert refusal is None, 'No report: ' + refusal
    ids, repeats = first['items'], first['runs']
    rows_b = rejudge.complete_rows(first, _records(env, bench, base))
    rows_k = rejudge.complete_rows(second, _records(env, bench, cand))
    out = {'bench': bench, 'base': base, 'candidate': cand, 'solver': first['solver'], 'items': len(ids),
           'repeats': repeats, 'base_card_sha256': first['card_sha256'], 'candidate_card_sha256': second['card_sha256'],
           'origin': {'step_dir': first['origin']['step_dir'], 'base_unit': first['origin']['unit'],
                      'candidate_unit': second['origin']['unit']},
           'complete': rows_b is not None and rows_k is not None,
           'note': 'the card is mounted on every spare item; a run mounts it on the items routed into its type'}
    if not out['complete']:
        have = lambda config: len(set(ids) & set(_records(env, bench, config)))
        out.update({'records': {'base': have(base), 'candidate': have(cand)}, 'reading': 'INCOMPLETE'})
        return out
    runs_b = {row['id']: [run['verdict'] == 'pass' for run in row['runs']] for row in rows_b}
    runs_k = {row['id']: [run['verdict'] == 'pass' for run in row['runs']] for row in rows_k}
    total = lambda runs, names: sum(sum(runs[name]) for name in names)
    gain = lambda names: 100.0 * (total(runs_k, names) - total(runs_b, names)) / (repeats * len(names))
    rng = random.Random('%d:spare:%s:%s:%s' % (SEED, bench, base, cand))
    draws = sorted(gain([rng.choice(ids) for _ in ids]) for _ in range(BOOTSTRAP_DRAWS))
    span = lambda rows: [min(row.get('finished_at') or '' for row in rows),
                         max(row.get('finished_at') or '' for row in rows)]
    out.update({
        'finished_between': {'base': span(rows_b), 'candidate': span(rows_k)},
        'base_pass_pct': round(100.0 * total(runs_b, ids) / (repeats * len(ids)), 2),
        'candidate_pass_pct': round(100.0 * total(runs_k, ids) / (repeats * len(ids)), 2),
        'wrong_runs_without_a_complete_reply': {'base': _incomplete(rows_b), 'candidate': _incomplete(rows_k)},
        'gate_rule': gate_statistics(runs_b, runs_k, ids),
        'gain_interval_95_resampling_items': [round(draws[int(0.025 * (len(draws) - 1))], 2),
                                              round(draws[int(0.975 * (len(draws) - 1))], 2)],
        'gate_rule_on_the_first': {str(n): gate_statistics(runs_b, runs_k, ids[:n]) for n in PREFIXES if n < len(ids)}})
    out['reading'] = reading(out['gate_rule'], out['gain_interval_95_resampling_items'])
    return out


def reading(rule, interval):
    """The registered reading (BANK-PILOT B28, as B26): CONFIRMED when the gate rule accepts and the interval of
    the gain lies above 0; NO EVIDENCE when the interval contains 0; HARMFUL when it lies below 0; BELOW THE
    THRESHOLD otherwise (a gain whose interval lies above 0 and that the rule does not accept)."""
    low, high = interval
    if low <= 0 <= high:
        return 'NO EVIDENCE'
    if high < 0:
        return 'HARMFUL'
    return 'CONFIRMED' if rule and rule['accepted'] else 'BELOW THE THRESHOLD'


# ---- parity with the run (no call) -----------------------------------------------------------------------------------
def first_request(tools, bench, item, card_text):
    """The first request the chain's cell would send for ``item`` under a configuration, with NO call (the cell is
    run on a probe that records the request and answers with a failed receipt); None when the cell sends nothing."""
    call, seen = rejudge.probe()
    mounted = forced_mount(tools['mount'], bench, item, card_text, tools['runtime'])
    tools['mount'].solve(bench, item, mounted, call=call, runtime=tools['runtime'], worker_factory=None, native=None,
                         nominal_tokens=tools.get('nominal_tokens'), unit='parity', tag='parity',
                         scorer_root=None, mode='run', step='bank/parity', episodes=None)
    return seen[0] if seen else None


def stage_parity(env, tools, bench, gate, cards, step_dir, identity, kind=KIND):
    """Every configuration of ``cards`` against its source in the run's learning step ``step_dir`` on the run's
    gate items ``gate``: the hand card ``c`` against the step's noise unit (the learning base, which the step's card
    gate compared its candidates against), a card text against the card round whose writer wrote exactly it. The
    record ``<bench>/<kind>-parity.json`` (``rejudge.check_parity``). No call."""
    shas = card_shas(tools, bench, cards)
    assert BASE_CONFIG in cards, 'The base "c" is part of every re-judging on spare items'
    configurations = {
        config: (shas[config],
                 rejudge.base_source(BASE_UNIT) if text is None else rejudge.candidate_source(step_dir, text),
                 lambda item, text=text: first_request(tools, bench, item, text))
        for config, text in cards.items()}
    return rejudge.check_parity(env, bench, kind, step_dir, identity, gate, configurations)
