"""typed-v3 item bank: ZebraLogic made puzzles (bank/zebra.py: the language, the two solvers, making, the
certificate, the comparison; bank/zebra_build.py: the stages). A small language written here stands in for the
pool's; no benchmark data, no model, no network."""
import itertools
import json
import random
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import zebralogic
from skillopt.execskill.typed import units
from skillopt.execskill.typed.bank import env as bank_env, zebra, zebra_build

VALUES = {'Name': ['Alice', 'Arnold', 'Bob', 'Carol', 'Eric', 'Peter'],
          'Pet': ['bird', 'cat', 'dog', 'fish', 'hamster', 'rabbit'],
          'Mother': ['Aniya', 'Holly', 'Janelle', 'Kailyn', 'Penny', 'Sarah'],
          'Height': ['average', 'short', 'super tall', 'tall', 'very short', 'very tall']}
INTRO = {'Name': 'Each person has a unique name', 'Pet': 'Each person has a unique type of pet',
         'Mother': "The mothers' names in different houses are unique", 'Height': 'People have unique heights'}
PHRASE = {'Name': '%s', 'Pet': 'the person who keeps a %s',            # a name: a capital everywhere
          'Mother': "The person whose mother's name is %s",             # a capital inside a sentence too; holds " is "
          'Height': 'the person who is %s'}                             # holds " is "; 'short' is part of 'very short'
LANGUAGE = {'columns': {column: {'intro': INTRO[column],
                                 'values': {str(n): sorted(VALUES[column][:n]) for n in range(2, 7)}} for column in VALUES},
            'phrases': {column: {value: PHRASE[column] % value for value in VALUES[column]} for column in VALUES}}
OTHERS = sorted(column for column in VALUES if column != 'Name')
NODE_COUNTS = [4, 1, 3, 1, 1, 3, 1, 1, 3, 3, 1, 1]      # search nodes of twelve fixed made puzzles (5 houses, 2 columns)


def says(clue, place):
    """What a clue says, written out again here (not ``zebra.RULES``)."""
    kind, a, b = clue
    if kind == 'found_at':
        return place[a] == b
    if kind == 'not_at':
        return place[a] != b
    x, y = place[a], place[b]
    return {'same': x == y, 'direct_left': y - x == 1, 'left_of': x < y, 'right_of': x > y, 'next_to': x - y in (1, -1),
            'one_between': x - y in (2, -2), 'two_between': x - y in (3, -3)}[kind]


def every_grid(houses, columns, clues):
    """All grids that satisfy the clues, by trying every grid."""
    out = []
    for orders in itertools.product(*[itertools.permutations(range(houses)) for _ in columns]):
        place = {(column, value): house for (column, values), order in zip(columns, orders) for value, house in zip(values, order)}
        if all(says(clue, place) for clue in clues):
            out.append(place)
    return out


def as_set(solutions):
    return {frozenset(solution.items()) for solution in solutions}


def grid_columns(houses, names):
    return [(name, LANGUAGE['columns'][name]['values'][str(houses)]) for name in names]


def made(seed, houses, columns, weights=None):
    rng = random.Random(seed)
    return zebra.make(rng, houses, ['Name'] + rng.sample(OTHERS, columns - 1), LANGUAGE, weights)


def pool_rows(count=72):
    rows = []
    for number in range(count):
        houses, columns = (5, 6)[number % 2], (2, 3, 4)[number % 3]
        puzzle = made('pool:%d' % number, houses, columns)
        rows.append(zebra.row_of(puzzle, LANGUAGE, 'p-%03d' % number))
    return rows


# ---- the two solvers ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('kind', zebra.KINDS)
def test_every_kind_means_what_its_sentence_says(kind):
    columns = grid_columns(4, ['Name', 'Pet'])
    a, same_column, other_column = ('Name', 'Alice'), ('Name', 'Bob'), ('Pet', 'cat')
    cases = [(kind, a, 2)] if kind in zebra.HOUSE_KINDS else [(kind, a, other_column), (kind, other_column, a)]
    if kind in zebra.PAIR_KINDS and kind != 'same':
        cases.append((kind, a, same_column))
    for clue in cases:
        truth = as_set(every_grid(4, columns, [clue]))
        assert truth and len(truth) < 576
        assert as_set(zebra.solve(4, columns, [clue], limit=10 ** 6)[0]) == truth
        assert as_set(zebra.solve_plainly(4, columns, [clue], limit=10 ** 6)) == truth


def test_the_solvers_agree_with_trying_every_grid_on_random_clue_sets():
    columns = grid_columns(4, ['Name', 'Pet', 'Height'])
    cells = [(column, value) for column, values in columns for value in values]
    rng, seen_none, seen_one, seen_many = random.Random(7), 0, 0, 0
    for _ in range(40):
        clues = []
        for _ in range(rng.randint(3, 9)):
            kind = rng.choice(zebra.KINDS)
            clues.append((kind, rng.choice(cells), rng.randrange(4)) if kind in zebra.HOUSE_KINDS
                         else (kind,) + tuple(rng.sample(cells, 2)))
        truth = as_set(every_grid(4, columns, clues))
        assert as_set(zebra.solve(4, columns, clues, limit=10 ** 6)[0]) == truth
        assert as_set(zebra.solve_plainly(4, columns, clues, limit=10 ** 6)) == truth
        seen_none, seen_one, seen_many = seen_none + (not truth), seen_one + (len(truth) == 1), seen_many + (len(truth) > 1)
    assert seen_none and seen_many      # the comparison met clue sets without a grid and with several


def test_a_solver_stops_at_its_limit_and_a_value_cannot_be_beside_itself():
    columns = grid_columns(4, ['Name', 'Pet'])
    assert len(zebra.solve(4, columns, [], limit=2)[0]) == 2 and len(zebra.solve_plainly(4, columns, [], limit=2)) == 2
    alice = ('Name', 'Alice')
    assert zebra.solve(4, columns, [('next_to', alice, alice)], limit=2)[0] == []
    assert zebra.solve_plainly(4, columns, [('next_to', alice, alice)], limit=2) == []
    assert len(zebra.solve(4, columns, [('same', alice, alice)], limit=3)[0]) == 3
    assert len(zebra.solve_plainly(4, columns, [('same', alice, alice)], limit=3)) == 3


def test_a_settled_value_clears_its_house_for_the_rest_of_its_column():
    # two values pinned to houses leave the third nowhere else to go: no search is needed, and the count says so
    columns = grid_columns(3, ['Name'])
    clues = [('found_at', ('Name', 'Alice'), 0), ('found_at', ('Name', 'Arnold'), 1)]
    solutions, nodes = zebra.solve(3, columns, clues, limit=2)
    assert solutions == [{('Name', 'Alice'): 0, ('Name', 'Arnold'): 1, ('Name', 'Bob'): 2}] and nodes == 1
    # 'not in the first house' and 'not in the second' pin Bob; then Alice and Arnold share what is left
    loose = [('not_at', ('Name', 'Bob'), 0), ('not_at', ('Name', 'Bob'), 1), ('left_of', ('Name', 'Alice'), ('Name', 'Arnold'))]
    assert zebra.solve(3, columns, loose, limit=2) == (solutions, 1)
    counts = [zebra.solve(p['houses'], p['columns'], p['clues'], limit=2)[1] for p in (made('nodes:%d' % n, 5, 2) for n in range(12))]
    assert counts == NODE_COUNTS


# ---- the starting clue set and the thinning ------------------------------------------------------------------------------
def test_the_true_clues_are_all_true_counted_and_said_from_the_left():
    puzzle = made('clues', 5, 3)
    columns, place = puzzle['columns'], puzzle['place']
    clues = zebra.true_clues(5, columns, place, random.Random(3))
    assert all(says(clue, place) for clue in clues) and len(set(clues)) == len(clues)
    count = lambda *kinds: sum(clue[0] in kinds for clue in clues)
    assert count('found_at') == 15 and count('not_at') == 60 and count('same') == 15     # 5 houses, 3 columns
    assert count('left_of', 'right_of') == 90 and count('left_of') and count('right_of')  # each pair in two houses once
    assert count('direct_left', 'next_to') == 36 and count('direct_left') and count('next_to')
    assert count('one_between') == 27 and count('two_between') == 18
    for kind, a, b in clues:
        if kind in ('direct_left', 'next_to', 'one_between', 'two_between', 'left_of'):
            assert place[a] < place[b]      # the value on the left is named first, as in the pool
        if kind == 'same':
            assert a[0] != b[0]
    pairs = [frozenset(clue[1:]) for clue in clues if clue[0] in ('left_of', 'right_of')]
    assert len(set(pairs)) == len(pairs)    # 'left of' and 'right of' never both for one pair


def test_thinning_is_the_loop_that_takes_one_clue_at_a_time():
    for seed in range(12):
        houses, names = (4, 5)[seed % 2], ['Name'] + OTHERS[:2]
        columns = grid_columns(houses, names)
        rng = random.Random(seed)
        place = {}
        for name, values in columns:
            order = list(range(houses))
            rng.shuffle(order)
            place.update({(name, value): house for value, house in zip(values, order)})
        ordered = zebra.true_clues(houses, columns, place, rng)
        rng.shuffle(ordered)
        kept = list(ordered)
        for clue in ordered:                 # the loop of the paper, one removal at a time, to its end
            rest = [other for other in kept if other != clue]
            if len(zebra.solve(houses, columns, rest, limit=2)[0]) == 1:
                kept = rest
        assert zebra.thin(houses, columns, ordered) == kept
        assert as_set(zebra.solve(houses, columns, kept, limit=2)[0]) == {frozenset(place.items())}


def test_thinning_refuses_clues_that_do_not_pin_a_grid():
    columns = grid_columns(4, ['Name', 'Pet'])
    with pytest.raises(ValueError):
        zebra.thin(4, columns, [('found_at', ('Name', 'Alice'), 0)])


# ---- text ------------------------------------------------------------------------------------------------------------
def test_a_made_puzzle_is_read_back_as_made_and_certified():
    for seed, (houses, columns) in enumerate([(5, 2), (5, 3), (6, 4), (6, 3)]):
        puzzle = made('text:%d' % seed, houses, columns)
        row = zebra.row_of(puzzle, LANGUAGE, 'zm-x')
        parsed = zebra.parse(row['puzzle'], LANGUAGE)
        assert parsed == {key: puzzle[key] for key in ('houses', 'columns', 'clues')}
        assert zebra.write(parsed, LANGUAGE) == row['puzzle'] and row['puzzle'].endswith('\n')
        assert row['size'] == row['task'] == '%d*%d' % (houses, columns) and row['solution']['header'][:2] == ['House', 'Name']
        certificate = zebra.certify(row, LANGUAGE)
        assert certificate['solutions'] == 1 and certificate['second_solver_agrees'] and certificate['no_clue_can_be_left_out']
        assert certificate['clues'] == len(puzzle['clues']) == sum(certificate['kinds'].values())
        assert as_set(every_grid(houses, puzzle['columns'], puzzle['clues'])) == {frozenset(puzzle['place'].items())} \
            if houses == 5 and columns <= 3 else True


def test_sentences_are_written_as_the_pool_writes_them():
    arnold, short, aniya, cat = ('Name', 'Arnold'), ('Height', 'short'), ('Mother', 'Aniya'), ('Pet', 'cat')
    say = lambda *clue: zebra.sentence_of(clue, LANGUAGE)
    assert say('found_at', short, 2) == 'The person who is short is in the third house.'
    assert say('not_at', arnold, 0) == 'Arnold is not in the first house.'
    assert say('same', short, arnold) == 'The person who is short is Arnold.'
    assert say('same', arnold, aniya) == "Arnold is The person whose mother's name is Aniya."
    assert say('direct_left', cat, short) == 'The person who keeps a cat is directly left of the person who is short.'
    assert say('left_of', arnold, cat) == 'Arnold is somewhere to the left of the person who keeps a cat.'
    assert say('right_of', cat, arnold) == 'The person who keeps a cat is somewhere to the right of Arnold.'
    assert say('next_to', cat, arnold) == 'The person who keeps a cat and Arnold are next to each other.'
    assert say('one_between', cat, short) == 'There is one house between the person who keeps a cat and the person who is short.'
    assert say('two_between', aniya, cat) == "There are two houses between The person whose mother's name is Aniya and the person who keeps a cat."


def text_of(clue_sentences, houses=5, names=('Name', 'Height')):
    lines = [zebra.OPENING % (houses, houses)]
    lines += [' - %s: %s' % (INTRO[name], ', '.join('`%s`' % value for value in LANGUAGE['columns'][name]['values'][str(houses)]))
              for name in names]
    return '\n'.join(lines + ['', zebra.CLUE_HEAD] + ['%d. %s' % (n, s) for n, s in enumerate(clue_sentences, 1)]) + '\n'


def test_reading_refuses_what_is_not_the_language():
    good = text_of(['Arnold is in the first house.', 'The person who is short is Arnold.'])
    assert zebra.parse(good, LANGUAGE)['clues'] == [('found_at', ('Name', 'Arnold'), 0), ('same', ('Height', 'short'), ('Name', 'Arnold'))]
    bad = [
        good[:-1],                                                                   # no final newline
        good.replace('2. The', '3. The'),                                            # numbering
        good.replace('unique heights', 'unique shoe sizes'),                         # an attribute the language lacks
        good.replace('`short`', '`tiny`'),                                           # not the value set
        good.replace('`average`', '`tiny`'),                                         # not the value set, in no clue
        good.replace('`Arnold`, ', ''),                                              # a value per house
        text_of(['Arnold is in the sixth house.']),                                  # a house outside the grid
        text_of(['Arnold lives in the first house.']),                               # no pattern
        text_of(['Arnold is Arnold.']),                                              # a value with itself
        text_of(['arnold is in the first house.']),                                  # a name without its capital
        text_of(['Arnold is The person who is short.']),                             # a capital inside a sentence
        text_of(['the person who is short is Arnold.']),                             # no capital at the start
        text_of(['Peter is in the first house.']).replace('`Peter`', '`Petra`'),     # a value that is not listed
        text_of(['The person who keeps a cat is in the first house.']),              # a column the puzzle does not have
        good.replace('across the street.', 'across the road.'),                      # not the opening sentence
    ]
    for text in bad:
        with pytest.raises(ValueError):
            zebra.parse(text, LANGUAGE)


def test_the_layout_is_read_strictly():
    good = text_of(['Arnold is in the first house.'])
    houses, attributes, sentences = zebra.split_text(good)
    assert houses == 5 and [intro for intro, _ in attributes] == [INTRO['Name'], INTRO['Height']]
    assert sentences == ['Arnold is in the first house.'] and all(len(values) == 5 for _, values in attributes)
    for bad in (good.replace('`Arnold`', '`Alice`'),                 # a value listed twice
                good.replace('`Arnold`, ', ''),                      # a value too few
                good.replace(' - ' + INTRO['Height'], ' - ' + INTRO['Name']),   # an attribute twice
                good.replace('## Clues:', '## Clues'), good.replace('1. Arnold', '1.Arnold'), good + '\n'):
        with pytest.raises(ValueError):
            zebra.split_text(bad)


def test_a_sentence_with_two_readings_is_refused():
    # a language in which "Anna is the one who is Bob." can be cut at either " is "
    language = {'columns': {'Name': {'intro': 'Names', 'values': {'2': ['Anna', 'Bob']}},
                            'Job': {'intro': 'Jobs', 'values': {'2': ['x1', 'x2']}},
                            'Toy': {'intro': 'Toys', 'values': {'2': ['y1', 'y2']}}},
                'phrases': {'Name': {'Anna': 'Anna', 'Bob': 'Bob'},
                            'Job': {'x1': 'the one who is Bob', 'x2': 'the baker'},
                            'Toy': {'y1': 'anna is the one who', 'y2': 'the kite owner'}}}
    head = zebra.OPENING % (2, 2) + '\n - Names: `Anna`, `Bob`\n - Jobs: `x1`, `x2`\n - Toys: `y1`, `y2`\n\n## Clues:\n'
    assert zebra.parse(head + '1. Anna is the baker.\n', language)['clues'] == [('same', ('Name', 'Anna'), ('Job', 'x2'))]
    with pytest.raises(ValueError, match='2 readings'):
        zebra.parse(head + '1. Anna is the one who is Bob.\n', language)


def test_a_phrase_that_is_part_of_another_is_read_whole():
    text = text_of(['The person who is very short is Arnold.', 'The person who is short is in the second house.'])
    assert [clue[1] for clue in zebra.parse(text, LANGUAGE)['clues']] == [('Height', 'very short'), ('Height', 'short')]


# ---- the certificate -----------------------------------------------------------------------------------------------------
def test_the_certificate_refuses_a_puzzle_that_is_not_exact():
    puzzle = made('certificate', 5, 3)
    row = zebra.row_of(puzzle, LANGUAGE, 'zm-x')
    zebra.certify(row, LANGUAGE)

    def rewritten(clues):
        return {**row, 'puzzle': zebra.write({**puzzle, 'clues': clues}, LANGUAGE)}

    cell, house = next(iter(puzzle['place'].items()))
    spare_clue = ('found_at', cell, house)
    assert spare_clue not in puzzle['clues'] or len(puzzle['clues']) > 1
    extra = [clue for clue in puzzle['clues'] if clue != spare_clue] + [spare_clue, ('not_at', cell, (house + 1) % 5)]
    with pytest.raises(ValueError, match='can be left out'):
        zebra.certify(rewritten(extra), LANGUAGE)
    with pytest.raises(ValueError, match='stored grid'):
        zebra.certify(rewritten(puzzle['clues'][1:]), LANGUAGE)                      # one clue fewer: a second solution
    swapped = json.loads(json.dumps(row))
    swapped['solution']['rows'][0][1], swapped['solution']['rows'][1][1] = swapped['solution']['rows'][1][1], swapped['solution']['rows'][0][1]
    with pytest.raises(ValueError, match='stored grid'):
        zebra.certify(swapped, LANGUAGE)
    with pytest.raises(ValueError):
        zebra.certify({**row, 'puzzle': row['puzzle'].replace('1. ', '1.  ', 1)}, LANGUAGE)
    reordered = rewritten(list(reversed(puzzle['clues'])))
    assert zebra.certify(reordered, LANGUAGE)['clues'] == len(puzzle['clues'])       # the order of clues is free


def test_the_certificate_needs_both_solvers(monkeypatch):
    puzzle = made('both', 5, 3)
    row = zebra.row_of(puzzle, LANGUAGE, 'zm-x')
    other = dict(puzzle['place'])
    first, second = list(other)[:2]
    other[first], other[second] = other[second], other[first]
    real_plain, real_solve = zebra.solve_plainly, zebra.solve
    monkeypatch.setattr(zebra, 'solve_plainly', lambda *args, **kwargs: real_plain(*args, **kwargs) + [other])
    with pytest.raises(ValueError, match='second solver'):
        zebra.certify(row, LANGUAGE)
    monkeypatch.setattr(zebra, 'solve_plainly', lambda *args, **kwargs: [other])
    with pytest.raises(ValueError, match='second solver'):
        zebra.certify(row, LANGUAGE)
    monkeypatch.setattr(zebra, 'solve_plainly', real_plain)
    monkeypatch.setattr(zebra, 'solve', lambda *args, **kwargs: ([other], 1))
    with pytest.raises(ValueError, match='first solver'):
        zebra.certify(row, LANGUAGE)
    monkeypatch.setattr(zebra, 'solve', real_solve)
    assert zebra.certify(row, LANGUAGE)['solutions'] == 1


# ---- learning the language from puzzle texts -----------------------------------------------------------------------------
def test_the_language_is_learned_back_from_puzzle_texts_alone():
    rows = pool_rows()
    learned = zebra.learn(rows)
    assert learned['phrases'] == LANGUAGE['phrases']
    assert {column: entry['intro'] for column, entry in learned['columns'].items()} == INTRO
    for column in VALUES:
        assert learned['columns'][column]['values'] == {n: LANGUAGE['columns'][column]['values'][n] for n in ('5', '6')}
    clues = sum(len(zebra.parse(row['puzzle'], LANGUAGE)['clues']) for row in rows)
    assert learned['checks'] == {'puzzles': len(rows), 'clues': clues, 'phrases': 24, 'columns': 4,
                                 'written_back_exactly': len(rows), 'solved_to_the_reference_alone': len(rows)}
    assert json.loads(json.dumps(learned)) == learned          # the record of the language is the language
    again = {key: learned[key] for key in ('columns', 'phrases')}
    assert zebra.parse(rows[0]['puzzle'], again) == zebra.parse(rows[0]['puzzle'], LANGUAGE)


def test_learning_refuses_a_pool_it_cannot_prove():
    rows = pool_rows(24)
    wrong_grid = json.loads(json.dumps(rows))
    cells = wrong_grid[5]['solution']['rows']
    cells[0][1], cells[1][1] = cells[1][1], cells[0][1]                                # a reference that is not the solution
    with pytest.raises(ValueError):
        zebra.learn(wrong_grid)
    loose = json.loads(json.dumps(rows))
    parsed = zebra.parse(loose[7]['puzzle'], LANGUAGE)
    loose[7]['puzzle'] = zebra.write({**parsed, 'clues': parsed['clues'][1:]}, LANGUAGE)   # every clue still true
    with pytest.raises(ValueError, match='reference alone'):
        zebra.learn(loose)
    garbled = json.loads(json.dumps(rows))
    garbled[3]['puzzle'] = garbled[3]['puzzle'].replace(' is ', ' was ', 1) if ' is ' in garbled[3]['puzzle'].split(zebra.CLUE_HEAD)[1] \
        else garbled[3]['puzzle'].replace('1. ', '1. Maybe ', 1)
    with pytest.raises(ValueError):
        zebra.learn(garbled)
    two_intros = json.loads(json.dumps(rows))
    two_intros[0]['puzzle'] = two_intros[0]['puzzle'].replace(INTRO['Name'], 'Everybody has a first name')
    with pytest.raises(ValueError):
        zebra.learn(two_intros)


# ---- made against real -----------------------------------------------------------------------------------------------------
def test_the_comparison_tells_another_generator_apart():
    whole = [made('whole:%d' % number, 5, 3) for number in range(120)]
    alike = [made('alike:%d' % number, 5, 3) for number in range(20)]
    heavy = dict(zebra.REMOVAL_WEIGHTS, same=60.0, found_at=40.0)      # 'same' and house clues go first: few are left
    unlike = [made('unlike:%d' % number, 5, 3, heavy) for number in range(20)]
    same = zebra.compare(alike, whole, random.Random(1), draws=400)
    other = zebra.compare(unlike, whole, random.Random(1), draws=400)
    assert same['comparisons'] == other['comparisons'] == 3 and same['beyond_below_0.001'] == 0
    assert other['sizes']['5*3']['beyond']['kinds'] < 0.01 and other['beyond_below_0.05'] >= 1
    assert same['sizes']['5*3']['real'] == 20 and same['sizes']['5*3']['made'] == 120
    few = zebra.compare(alike, whole[:30], random.Random(1), draws=50)
    assert few['sizes']['5*3']['compared'] is False and few['comparisons'] == 0   # too few made puzzles to compare with


# ---- the stages ------------------------------------------------------------------------------------------------------------
@pytest.fixture
def root():
    base = Path('/tmp/typed3-neutral')
    base.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='zebra-', dir=base))
    yield folder
    shutil.rmtree(folder, ignore_errors=True)


def open_env(root):
    return bank_env.BankEnv(root, SimpleNamespace(state={}), {}, width=1)


def pool_tasks(count=48):
    return [zebralogic.normalize(row, partition='pool') for row in pool_rows(count)]


PIN = {'path': '/somewhere/pool.json', 'sha256': 'a' * 64}
SMALL = ('5*2', '5*3', '6*2')


def make_small(env, language, tasks, **kwargs):
    return zebra_build.stage_make(env, language, tasks, zebralogic.normalize, **{'count': 3, 'shown': 1, 'sizes': SMALL, **kwargs})


def test_the_language_record_is_written_once_and_bound_to_its_pool(root):
    env, tasks = open_env(root), pool_tasks()
    record = zebra_build.stage_language(env, tasks, PIN)
    assert record['phrases'] == LANGUAGE['phrases'] and record['pool'] == PIN and record['pool_items'] == len(tasks)
    assert record['checks']['solved_to_the_reference_alone'] == len(tasks)
    assert [zebra_build.row_of_task(task)['solution'] for task in tasks] == [row['solution'] for row in pool_rows(48)]
    stamp = (root / 'zebralogic' / 'language.json').stat().st_mtime_ns
    assert zebra_build.stage_language(open_env(root), tasks, PIN) == record
    assert (root / 'zebralogic' / 'language.json').stat().st_mtime_ns == stamp
    with pytest.raises(AssertionError):
        zebra_build.stage_language(open_env(root), tasks, {**PIN, 'sha256': 'b' * 64})
    with pytest.raises(AssertionError):
        zebra_build.stage_language(open_env(root), tasks[:-1], PIN)


def test_made_puzzles_are_certified_items_of_the_benchmarks_own_form(root):
    env, tasks = open_env(root), pool_tasks()
    language = zebra_build.stage_language(env, tasks, PIN)
    result = make_small(env, language, tasks)
    assert result == {'made': 9, 'sizes': {size: 3 for size in SMALL}, 'sides': {'shown': 3, 'judge': 6}, 'certified': 9}
    names = sorted(path.stem for path in (root / 'zebralogic' / 'items').glob('*.json'))
    assert names == sorted(zebra_build.item_name(size, number) for size in SMALL for number in (1, 2, 3))
    plan = units.read_json(root / 'zebralogic' / 'make.json')
    assert plan == {'version': zebra_build.BANK_VERSION, 'seed': zebra_build.SEED, 'tag': 'zebra-make', 'count': 3, 'shown': 1,
                    'sizes': list(SMALL), 'weights': zebra.REMOVAL_WEIGHTS, 'language_version': language['version'],
                    'pool_sha256': PIN['sha256']}
    listing = units.read_json(root / 'zebralogic' / 'made.json')
    assert [row['item'] for row in listing['items']] == [zebra_build.item_name(size, number) for size in SMALL for number in (1, 2, 3)]
    texts = set()
    for name in names:
        item, record = units.read_json(root / 'zebralogic' / 'items' / (name + '.json')), units.read_json(root / 'zebralogic' / 'records' / (name + '.json'))
        assert item['task_id'] == name and item['benchmark'] == 'zebralogic' and item['part'] == 'bank' and item['origin'] == 'made'
        assert item['family_id'] == 'zebralogic:' + name and item['task'] == record['size'] and item['dataset_revision'] is None
        assert record['side'] == ('shown' if name.endswith('-001') else 'judge') and record['certificate']['solutions'] == 1
        assert record['item_sha256'] == zebra_build.item_digest(item)
        houses = int(record['size'][0])
        assert zebralogic.public_house_count(item['public']) == houses and 'House %d' % houses in zebralogic.render_user(item['public'])
        row = zebra_build.row_of_task(item)                       # the stored item, certified again from what it holds
        assert zebra.certify({**row, 'size': record['size']}, language)['clues'] == record['certificate']['clues']
        texts.add(item['public']['question'])
    assert len(texts) == 9 and not texts & {task['public']['question'] for task in tasks}
    stamps = {path.name: path.stat().st_mtime_ns for path in (root / 'zebralogic').rglob('*.json')}
    assert make_small(open_env(root), language, tasks) == result       # a second run makes and writes nothing
    assert stamps == {path.name: path.stat().st_mtime_ns for path in (root / 'zebralogic').rglob('*.json')}
    assert len(zebra_build.made_items(env)) == 9 and len(zebra_build.made_items(env, 'judge')) == 6
    assert [item['task_id'] for item in zebra_build.made_items(env, 'shown')] == [zebra_build.item_name(size, 1) for size in SMALL]
    assert zebra_build.made_plan(env) == plan


def test_a_bank_keeps_the_plan_it_was_begun_with(root):
    env, tasks = open_env(root), pool_tasks()
    language = zebra_build.stage_language(env, tasks, PIN)
    for count, shown, sizes in ((3, 3, ('5*3',)), (3, 0, ('5*3',)), (3, 1, ('4*2',)), (3, 1, ('5*2', '5*2'))):
        with pytest.raises(AssertionError, match='judged sizes'):        # refused before anything is written
            make_small(env, language, tasks, count=count, shown=shown, sizes=sizes)
    assert not (root / 'zebralogic' / 'make.json').exists()
    make_small(env, language, tasks)
    for change in ({'shown': 2}, {'count': 4}, {'sizes': SMALL[:2]}):
        with pytest.raises(AssertionError, match='another plan'):
            make_small(open_env(root), language, tasks, **change)
    other = {**language, 'pool': {**PIN, 'sha256': 'c' * 64}}
    with pytest.raises(AssertionError, match='another plan'):
        make_small(open_env(root), other, tasks)
    # the plan of a finished bank cannot be exchanged for one that names the same items
    plan_path = root / 'zebralogic' / 'make.json'
    units.write_json(plan_path, {**units.read_json(plan_path), 'shown': 2})
    for call in (zebra_build.made_plan, zebra_build.made_items):
        with pytest.raises(AssertionError, match='not of its plan'):
            call(env)


def test_an_interrupted_bank_is_not_a_bank_and_resumes_as_planned(root, monkeypatch):
    env, tasks = open_env(root), pool_tasks()
    language = zebra_build.stage_language(env, tasks, PIN)
    real_once = bank_env.BankEnv.once

    def interrupted(self, parts, compute):
        if parts == ('zebralogic', 'records', 'zm-5x2-002.json'):
            compute()                                    # the item file is written, the record is not
            raise KeyboardInterrupt
        return real_once(self, parts, compute)
    monkeypatch.setattr(bank_env.BankEnv, 'once', interrupted)
    with pytest.raises(KeyboardInterrupt):
        make_small(env, language, tasks)
    monkeypatch.setattr(bank_env.BankEnv, 'once', real_once)
    assert (root / 'zebralogic' / 'items' / 'zm-5x2-002.json').exists()
    assert not (root / 'zebralogic' / 'records' / 'zm-5x2-002.json').exists() and not (root / 'zebralogic' / 'made.json').exists()
    orphan = (root / 'zebralogic' / 'items' / 'zm-5x2-002.json').read_text()
    for call in (zebra_build.made_items, zebra_build.made_plan, zebra_build.named_sizes):
        with pytest.raises(AssertionError, match='not finished|missing'):   # nothing of an unfinished bank is handed out
            call(env)
    with pytest.raises(AssertionError, match='not finished'):
        zebra_build.build_report(env, language, tasks, reference=24)
    with pytest.raises(AssertionError, match='another plan'):               # the side of the written item cannot change
        make_small(open_env(root), language, tasks, shown=2)
    make_small(open_env(root), language, tasks)
    assert (root / 'zebralogic' / 'items' / 'zm-5x2-002.json').read_text() == orphan
    assert units.read_json(root / 'zebralogic' / 'records' / 'zm-5x2-002.json')['side'] == 'judge'
    assert len(zebra_build.made_items(env, 'judge')) == 6


def test_an_item_is_handed_out_only_as_its_record_certifies_it(root):
    env, tasks = open_env(root), pool_tasks()
    language = zebra_build.stage_language(env, tasks, PIN)
    make_small(env, language, tasks)
    path = root / 'zebralogic' / 'items' / 'zm-5x3-002.json'
    stored = units.read_json(path)

    def tampered(change):
        item = json.loads(json.dumps(stored))
        change(item)
        units.write_json(path, item)
        with pytest.raises(AssertionError, match='not the one its record certifies'):
            zebra_build.made_items(env)
        units.write_json(path, stored)
        assert len(zebra_build.made_items(env)) == 9

    def swap_answer(item):                       # the question untouched, the grid the judge reads changed
        one, two = item['private']['answer']['House 1'], item['private']['answer']['House 2']
        one['Name'], two['Name'] = two['Name'], one['Name']
    tampered(swap_answer)
    tampered(lambda item: item['public'].update(columns=list(reversed(item['public']['columns']))))   # the answer template
    tampered(lambda item: item['public'].update(question=item['public']['question'].replace('first', 'second', 1)))
    tampered(lambda item: item.update(task='6*3'))
    listing_path = root / 'zebralogic' / 'made.json'
    listing = units.read_json(listing_path)
    units.write_json(listing_path, {**listing, 'items': listing['items'][:-1]})          # a shortened list
    with pytest.raises(AssertionError, match='not of its plan'):
        zebra_build.made_items(env)
    units.write_json(listing_path, listing)
    record_path = root / 'zebralogic' / 'records' / 'zm-5x3-002.json'
    record = units.read_json(record_path)
    units.write_json(record_path, {**record, 'side': 'shown'})                            # a record moved to the other side
    with pytest.raises(AssertionError, match='not the one the bank lists'):
        zebra_build.made_items(env)


def test_a_made_puzzle_with_the_text_of_a_pool_puzzle_is_refused_before_it_is_written(root):
    env, tasks = open_env(root), pool_tasks()
    language = zebra_build.stage_language(env, tasks, PIN)
    twin, _ = zebra_build._made(language, '5*2', 2, 'zebra-make')
    copy = zebralogic.normalize(zebra.row_of(twin, language, 'p-copy'), partition='pool')
    with pytest.raises(AssertionError, match='has the text of p-copy'):
        make_small(env, language, tasks + [copy], sizes=('5*2',))
    assert sorted(path.stem for path in (root / 'zebralogic' / 'items').glob('*.json')) == ['zm-5x2-001']
    assert sorted(path.stem for path in (root / 'zebralogic' / 'records').glob('*.json')) == ['zm-5x2-001']
    with pytest.raises(AssertionError, match='not finished'):               # the refused puzzle cannot be loaded
        zebra_build.made_items(env, 'judge')
    # a bank made while the pool did not hold that text is refused when it is read again with a pool that does
    make_small(open_env(root), language, tasks, sizes=('5*2',))
    assert [item['task_id'] for item in zebra_build.made_items(env, 'judge')] == ['zm-5x2-002', 'zm-5x2-003']
    with pytest.raises(AssertionError, match='has the text of p-copy'):
        make_small(open_env(root), language, tasks + [copy], sizes=('5*2',))


def test_the_report_counts_the_bank_and_keeps_its_comparison_with_the_pool(root):
    env, tasks = open_env(root), pool_tasks()
    language = zebra_build.stage_language(env, tasks, PIN)
    make_small(env, language, tasks)
    with pytest.raises(AssertionError, match='missing'):
        zebra_build.named_sizes(env)
    report = zebra_build.build_report(env, language, tasks, reference=24)
    assert report['made'] == {'items': 9, 'sides': {'shown': 3, 'judge': 6}, 'certified_exactly_one_solution_by_two_solvers': 9,
                              'no_clue_can_be_left_out': 9}
    assert report['language']['checks']['written_back_exactly'] == len(tasks) and report['plan']['weights'] == zebra.REMOVAL_WEIGHTS
    compared = {size: entry['compared'] for size, entry in report['comparison']['sizes'].items()}
    assert all(compared[size] for size in SMALL) and report['comparison']['comparisons'] == 9
    assert set(report['bank_by_size']) == set(SMALL) and all(entry['puzzles'] == 3 for entry in report['bank_by_size'].values())
    assert sum(entry['puzzles'] for entry in report['pool_by_size'].values()) == len(tasks)
    stamp = (root / 'zebralogic' / 'comparison.json').stat().st_mtime_ns
    assert zebra_build.build_report(open_env(root), language, tasks, reference=24) == report
    assert (root / 'zebralogic' / 'comparison.json').stat().st_mtime_ns == stamp           # the comparison is the bank's record
    with pytest.raises(AssertionError, match='another bank or sample'):
        zebra_build.build_report(open_env(root), language, tasks, reference=30)
    first = units.read_json(root / 'zebralogic' / 'items' / 'zm-5x2-001.json')['public']['question']
    bank_one, seed = zebra_build._made(language, '5*2', 1, 'zebra-make')
    reference_one, other_seed = zebra_build._made(language, '5*2', 1, 'zebra-reference')
    assert zebra.write(bank_one, language) == first and seed != other_seed          # a bank item can be made again
    assert zebra.write(reference_one, language) != first                             # the reference sample is other puzzles
    # a size the comparison puts below its line is named (B31 (d))
    assert report['sizes_named'] == zebra_build.named_sizes(env)
    stored = units.read_json(root / 'zebralogic' / 'comparison.json')
    stored['comparison']['sizes']['5*3']['beyond']['kinds'] = 0.0005
    units.write_json(root / 'zebralogic' / 'comparison.json', stored)
    assert zebra_build.named_sizes(env) == sorted(set(report['sizes_named']) | {'5*3'})
    stored['plan_sha256'] = 'f' * 64
    units.write_json(root / 'zebralogic' / 'comparison.json', stored)
    with pytest.raises(AssertionError, match='another bank'):
        zebra_build.named_sizes(env)
