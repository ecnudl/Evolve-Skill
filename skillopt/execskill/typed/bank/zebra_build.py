"""ZebraLogic made items: the bank's stages around ``zebra`` (BANK-PILOT B31). No model is called in this file.

- ``stage_language``: the puzzle language, learned from the pinned practice pool and proved on it (every pool
  puzzle written back exactly and solved to its reference alone); write-once ``zebralogic/language.json``;
- ``stage_make``: for every judged size ``count`` new puzzles, each one certified from its text before it is
  written (``zebra.certify``), stored in the benchmark's own item form with a side;
- ``made_items``: the items of a FINISHED bank, each checked against what its record certifies;
- ``build_report``: what the bank holds, and the comparison of made with real puzzles on a larger reference sample
  that is made for the comparison alone.

What makes a bank one thing (review of 2026-11-14): its PLAN (how many puzzles of which sizes, which of them are
shown to writers, the weights, the language's pool) is written before the first puzzle and never changes; a puzzle
that has the text of a pool puzzle or of another made puzzle is refused before anything of it is written; the LIST
of the finished bank is written after the last puzzle; and an item is handed out only from a finished bank and only
when the hash of everything a solver and the judge read of it (id, size, question, columns, grid) is the hash its
record certifies.

A made puzzle has no parent: it is its own family, and its side (shown to writers / kept for judging) is fixed by
its number in the plan. Nothing here reads a test-side file: a made puzzle is compared with the pool's texts only.
That it could equal a puzzle outside the pool is not checked and need not be: it would take the same grid, the same
listing orders, the same clues and the same clue order.
"""
from __future__ import annotations

import random

from .. import units
from ..library import canonical_sha256
from . import SEED, SIDES, zebra
from .env import text_sha256

BENCH = 'zebralogic'
SIZES = tuple('%d*%d' % (houses, columns) for houses in (5, 6) for columns in range(2, 7))   # the judged sizes
FIRST_COLUMN = 'Name'            # every pool puzzle starts with it
PER_SIZE = 30                    # design section 5: 300 made puzzles, 100 shown to writers and 200 kept for judging
SHOWN_PER_SIZE = 10
REFERENCE_PER_SIZE = 300         # made for the comparison with the pool alone, never handed to anyone
COMPARE_DRAWS = 2000
NAMED_BELOW = 0.001              # B31 (d): a size with a comparison below this is named in every report on its items
LANGUAGE_VERSION = 'zebra-language-v1'
BANK_VERSION = 'zebra-bank-v1'
PLAN, LIST, COMPARISON = 'make.json', 'made.json', 'comparison.json'


def row_of_task(task):
    """A normalised practice item as the source row ``zebra.learn`` reads."""
    columns, grid = list(task['public']['columns']), task['private']['answer']
    return {'id': task['task_id'], 'puzzle': task['public']['question'],
            'solution': {'header': ['House'] + columns,
                         'rows': [[str(number)] + [grid['House %d' % number][column] for column in columns]
                                  for number in range(1, len(grid) + 1)]}}


def item_name(size, number):
    houses, columns = size.split('*')
    return 'zm-%sx%s-%03d' % (houses, columns, number)


def item_digest(item):
    """The hash of everything a solver and the judge read of a made item."""
    return canonical_sha256({'task_id': item['task_id'], 'task': item['task'],
                             'public': {'question': item['public']['question'], 'columns': list(item['public']['columns'])},
                             'private': {'answer': item['private']['answer']}})


def stage_language(env, tasks, pin):
    """The language record of the bank: learned from ``tasks`` (the pinned practice pool, ``pin`` its path and
    sha256), with the counts of the two proofs. An existing record must be of the same pool."""
    def compute():
        language = zebra.learn([row_of_task(task) for task in tasks])
        return {'version': LANGUAGE_VERSION, 'pool': dict(pin), 'pool_items': len(tasks), **language}
    record = env.once((BENCH, 'language.json'), compute)
    assert record['version'] == LANGUAGE_VERSION and record['pool'] == dict(pin) and record['pool_items'] == len(tasks), \
        'The language record is of another pool'
    return record


def _made(language, size, number, tag):
    """(puzzle, seed) of the puzzle ``number`` of ``size``; the random stream is the bank seed, a tag and the two
    numbers, so a puzzle can be made again and compared."""
    houses, columns = (int(part) for part in size.split('*'))
    seed = '%d:%s:%s:%d' % (SEED, tag, size, number)
    rng = random.Random(seed)
    others = sorted(name for name in language['columns'] if name != FIRST_COLUMN)
    names = [FIRST_COLUMN] + rng.sample(others, columns - 1)
    puzzle = zebra.make(rng, houses, names, language)
    return puzzle, seed


def _plan(language, count, shown, sizes):
    return {'version': BANK_VERSION, 'seed': SEED, 'tag': 'zebra-make', 'count': count, 'shown': shown,
            'sizes': list(sizes), 'weights': dict(zebra.REMOVAL_WEIGHTS), 'language_version': language['version'],
            'pool_sha256': language['pool']['sha256']}


def stage_make(env, language, pool_tasks, normalize, *, count=PER_SIZE, shown=SHOWN_PER_SIZE, sizes=SIZES):
    """``count`` certified puzzles per size, the first ``shown`` of a size on the side shown to writers.

    The plan ``zebralogic/make.json`` is written first and must be the plan of every later call (a bank's numbers
    and sides do not change). Per puzzle: made from its seed; refused, before anything is written, when its text is
    a pool puzzle's or an earlier made puzzle's; certified; the item ``zebralogic/items/<name>.json`` (``normalize``:
    the benchmark's own reading of a source row, so a made item has exactly the form of a real one) and then the
    write-once record ``zebralogic/records/<name>.json`` (seed, side, certificate, the hash of the text and of the
    item). A stage interrupted between the two files makes the same item again. After the last puzzle the list
    ``zebralogic/made.json`` closes the bank."""
    assert 0 < shown < count and sizes and set(sizes) <= set(SIZES) and len(set(sizes)) == len(sizes), \
        'Puzzles of the judged sizes, some on each side'
    plan = _plan(language, count, shown, sizes)
    assert env.once((BENCH, PLAN), lambda: plan) == plan, \
        'This bank was begun with another plan (numbers, sides, sizes, weights or pool)'
    taken = {text_sha256(task['public']['question']): task['task_id'] for task in pool_tasks}
    rows = []
    for size in sizes:
        for number in range(1, count + 1):
            name, side = item_name(size, number), SIDES[0] if number <= shown else SIDES[1]

            def compute(size=size, number=number, name=name, side=side):
                puzzle, seed = _made(language, size, number, plan['tag'])
                row = zebra.row_of(puzzle, language, name)
                text = text_sha256(row['puzzle'])
                assert text not in taken, 'The made puzzle %s has the text of %s' % (name, taken[text])
                certificate = zebra.certify(row, language)
                item = {**normalize(row, partition='bank'), 'part': 'bank', 'origin': 'made', 'dataset_revision': None}
                assert item['task_id'] == name and item['task'] == size, 'The benchmark reads the made row as made'
                units.write_json(env.path(BENCH, 'items', name + '.json'), item)
                return {'item': name, 'kind': 'made_puzzle', 'size': size, 'number': number, 'seed': seed, 'side': side,
                        'certificate': certificate, 'text_sha256': text, 'item_sha256': item_digest(item),
                        'plan_sha256': canonical_sha256(plan)}
            record = env.once((BENCH, 'records', name + '.json'), compute)
            assert record['item'] == name and record['size'] == size and record['side'] == side \
                and record['plan_sha256'] == canonical_sha256(plan), 'The record of %s is of another bank' % name
            assert taken.setdefault(record['text_sha256'], name) == name, \
                'The made puzzle %s has the text of %s' % (name, taken[record['text_sha256']])
            rows.append(record)
    listing = {'plan_sha256': canonical_sha256(plan),
               'items': [{key: row[key] for key in ('item', 'size', 'side', 'item_sha256')} for row in rows]}
    assert env.once((BENCH, LIST), lambda: listing) == listing, 'The finished bank is not the bank of its list'
    return {'made': len(rows), 'sizes': {size: sum(row['size'] == size for row in rows) for size in sizes},
            'sides': {side: sum(row['side'] == side for row in rows) for side in SIDES},
            'certified': sum(bool(row['certificate'].get('second_solver_agrees')) for row in rows)}


def made_plan(env):
    """The plan of a FINISHED bank (its list exists and is of this plan)."""
    assert env.exists(BENCH, PLAN) and env.exists(BENCH, LIST), 'The bank of made puzzles is not finished: run zebra-make'
    plan, listing = env.read(BENCH, PLAN), env.read(BENCH, LIST)
    assert listing['plan_sha256'] == canonical_sha256(plan) and \
        [row['item'] for row in listing['items']] == [item_name(size, number) for size in plan['sizes']
                                                      for number in range(1, plan['count'] + 1)], \
        'The list of the bank is not of its plan'
    return plan


def made_items(env, side=None):
    """The items of a finished bank in the order of its list, optionally of one side. Every item is what its record
    certifies: the hash of its id, size, question, columns and grid."""
    plan = made_plan(env)
    out = []
    for row in env.read(BENCH, LIST)['items']:
        record = env.read(BENCH, 'records', row['item'] + '.json')
        item = env.read(BENCH, 'items', row['item'] + '.json')
        assert all(record[key] == row[key] for key in row) and record['plan_sha256'] == canonical_sha256(plan), \
            'The record of %s is not the one the bank lists' % row['item']
        assert item_digest(item) == row['item_sha256'] and text_sha256(item['public']['question']) == record['text_sha256'], \
            'The item %s is not the one its record certifies' % row['item']
        if side is None or row['side'] == side:
            out.append(item)
    return out


def named_sizes(env):
    """The sizes the comparison of made with real puzzles puts below ``NAMED_BELOW`` on some measure (B31 (d): they
    are named in every report that uses their items). The comparison must have been made: ``zebra-report``."""
    assert env.exists(BENCH, COMPARISON), 'The comparison of made with real puzzles is missing: run zebra-report'
    stored = env.read(BENCH, COMPARISON)
    assert stored['plan_sha256'] == canonical_sha256(made_plan(env)), 'The comparison is of another bank'
    return sorted(size for size, entry in stored['comparison']['sizes'].items()
                  if entry.get('compared') and min(entry['beyond'].values()) < NAMED_BELOW)


def build_report(env, language, pool_tasks, *, reference=REFERENCE_PER_SIZE):
    """Counts of the finished bank and the comparison of made with real puzzles (``zebra.compare``): the pool's
    puzzles of each size against ``reference`` puzzles made for this comparison (their own random stream, not the
    bank's items; never stored). The comparison is the bank's record ``zebralogic/comparison.json``, written once:
    every model report on the bank's items reads the sizes it names. Also where the bank's own items stand."""
    plan = made_plan(env)
    sizes = plan['sizes']
    real = [zebra.parse(task['public']['question'], language) for task in pool_tasks]

    def compute():
        sample = [_made(language, size, number, 'zebra-reference')[0] for size in sizes for number in range(1, reference + 1)]
        return {'plan_sha256': canonical_sha256(plan), 'pool_sha256': language['pool']['sha256'], 'reference_per_size': reference,
                'comparison': zebra.compare(real, sample, random.Random('%d:zebra-compare' % SEED), draws=COMPARE_DRAWS)}
    stored = env.once((BENCH, COMPARISON), compute)
    assert stored['plan_sha256'] == canonical_sha256(plan) and stored['reference_per_size'] == reference \
        and stored['pool_sha256'] == language['pool']['sha256'], 'The stored comparison is of another bank or sample'
    items = made_items(env)
    bank = zebra.profile([zebra.parse(item['public']['question'], language) for item in items])
    pool = zebra.profile(real)
    brief = lambda table: {size: {'puzzles': entry['puzzles'], 'clues_mean': round(sum(entry['clues']) / len(entry['clues']), 2),
                                   'kinds': entry['kinds'],
                                   'settled_without_search': sum(nodes == 1 for nodes in entry['search_nodes'])}
                           for size, entry in sorted(table.items())}
    records = [env.read(BENCH, 'records', row['item'] + '.json') for row in env.read(BENCH, LIST)['items']]
    return {'language': {'version': language['version'], 'pool': language['pool'], 'pool_items': language['pool_items'],
                         'checks': language['checks']},
            'plan': plan,
            'made': {'items': len(items), 'sides': {side: sum(row['side'] == side for row in records) for side in SIDES},
                     'certified_exactly_one_solution_by_two_solvers': sum(
                         row['certificate'].get('solutions') == 1 and bool(row['certificate'].get('second_solver_agrees'))
                         for row in records),
                     'no_clue_can_be_left_out': sum(bool(row['certificate'].get('no_clue_can_be_left_out')) for row in records)},
            'reference_per_size': reference, 'comparison': stored['comparison'], 'sizes_named': named_sizes(env),
            'pool_by_size': brief(pool), 'bank_by_size': brief(bank)}
