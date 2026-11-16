"""typed-v3 item stage tools, section 1 (brief P2a): the quota table of T5, the counts of T4 with the 20 % rule and the
split of the attack counts, the plan check of T3.4 in exact fractions, largest-remainder proportions, item records and
hashes, the write-once item store and the run-level registry. Expected values are computed by hand in the comments."""
import json
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path

import pytest

from skillopt.execskill.typed import items as items_
from skillopt.execskill.typed.items import store as store_


@pytest.fixture
def root():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    base = Path('/tmp/typed3-items-neutral')
    base.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='core-', dir=base))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- the quota table ---------------------------------------------------------------------------------------------
def test_the_quota_table_is_the_table_of_t5():
    expected = {'searchqa': (60, 45, 45, 27, 13), 'officeqa': (32, 24, 24, 16, 8), 'zebralogic': (80, 60, 60, 40, 20),
                'spreadsheetbench': (24, 18, 18, 13, 7), 'alfworld': (16, 12, 12, 8, 4)}
    for bench, (a, g, k, sa, sg) in expected.items():
        assert items_.ITEM_QUOTAS[bench] == {'judging': {'attack': a, 'guard': g, 'calibration': k},
                                            'shown': {'attack': sa, 'guard': sg}}
    assert set(items_.ITEM_QUOTAS) == set(expected)
    # 4 : 3 : 3 on the judging side everywhere
    for row in items_.ITEM_QUOTAS.values():
        a, g, k = (row['judging'][name] for name in ('attack', 'guard', 'calibration'))
        assert 3 * a == 4 * g and g == k


# (bench, judging A/G/K and shown A/G with at least 3 kept weaknesses, the same with fewer)
# reduced: judging attack = floor(total / 5), guard unchanged, calibration the rest; shown attack = floor(total / 5)
#   searchqa  150 -> 30, 45, 75; shown 40 -> 8, 32
#   officeqa   80 -> 16, 24, 40; shown 24 -> 4 (4.8), 20
#   zebralogic 200 -> 40, 60, 100; shown 60 -> 12, 48
#   sheet      60 -> 12, 18, 30; shown 20 -> 4, 16
#   alfworld   40 -> 8, 12, 20; shown 12 -> 2 (2.4), 10
BY_HAND = {'searchqa': ((60, 45, 45, 27, 13), (30, 45, 75, 8, 32)),
           'officeqa': ((32, 24, 24, 16, 8), (16, 24, 40, 4, 20)),
           'zebralogic': ((80, 60, 60, 40, 20), (40, 60, 100, 12, 48)),
           'spreadsheetbench': ((24, 18, 18, 13, 7), (12, 18, 30, 4, 16)),
           'alfworld': ((16, 12, 12, 8, 4), (8, 12, 20, 2, 10))}


def flat(found):
    return (found['judging']['attack'], found['judging']['guard'], found['judging']['calibration'],
            found['shown']['attack'], found['shown']['guard'])


@pytest.mark.parametrize('bench', sorted(BY_HAND))
def test_counts_of_every_bench_with_and_without_three_weaknesses(bench):
    full, reduced = BY_HAND[bench]
    for kept in (3, 4, 5, 9):
        found = items_.counts(bench, kept)
        assert flat(found) == full and found['rule'] == 'quota' and found['weaknesses'] == kept
    for kept in (0, 1, 2):
        found = items_.counts(bench, kept)
        assert flat(found) == reduced and found['rule'] == 'reduced_attack'
        assert found['totals'] == {'judging': sum(full[:3]), 'shown': sum(full[3:])}
    assert items_.counts(bench, 0)['attack_split'] == {'shown': [], 'judging': []}


def test_the_attack_split_of_zebralogic_over_its_kept_weaknesses():
    # in turn, plan order: total // k each, the first total % k weaknesses one more
    split = lambda kept: items_.counts('zebralogic', kept)['attack_split']
    assert split(['w1']) == {'judging': [['w1', 40]], 'shown': [['w1', 12]]}                      # reduced: 40 / 12
    assert split(['w1', 'w2']) == {'judging': [['w1', 20], ['w2', 20]], 'shown': [['w1', 6], ['w2', 6]]}
    assert split(['w1', 'w2', 'w3']) == {'judging': [['w1', 27], ['w2', 27], ['w3', 26]],         # 80 = 27 + 27 + 26
                                         'shown': [['w1', 14], ['w2', 13], ['w3', 13]]}           # 40 = 14 + 13 + 13
    assert split(5) == {'judging': [['w%d' % i, 16] for i in range(1, 6)],                       # 80 / 5
                        'shown': [['w%d' % i, 8] for i in range(1, 6)]}                          # 40 / 5
    assert split(['w1', 'w2', 'w3', 'w4', 'w5', 'w6', 'w7']) == {
        'judging': [['w1', 12], ['w2', 12], ['w3', 12], ['w4', 11], ['w5', 11], ['w6', 11], ['w7', 11]],  # 80 = 3*12+4*11
        'shown': [['w1', 6], ['w2', 6], ['w3', 6], ['w4', 6], ['w5', 6], ['w6', 5], ['w7', 5]]}             # 40 = 5*6+2*5


def test_the_attack_split_of_the_other_benches():
    assert items_.counts('searchqa', 2)['attack_split'] == {'judging': [['w1', 15], ['w2', 15]], 'shown': [['w1', 4], ['w2', 4]]}
    assert items_.counts('searchqa', 3)['attack_split'] == {'judging': [['w1', 20], ['w2', 20], ['w3', 20]],
                                                            'shown': [['w1', 9], ['w2', 9], ['w3', 9]]}
    assert items_.counts('alfworld', 1)['attack_split'] == {'judging': [['w1', 8]], 'shown': [['w1', 2]]}
    assert items_.counts('alfworld', 5)['attack_split'] == {'judging': [['w1', 4], ['w2', 3], ['w3', 3], ['w4', 3],
                                                                        ['w5', 3]],          # 16 = 4 + 4*3
                                                            'shown': [['w1', 2], ['w2', 2], ['w3', 2], ['w4', 1],
                                                                      ['w5', 1]]}            # 8 = 3*2 + 2*1
    assert items_.counts('officeqa', 3)['attack_split']['shown'] == [['w1', 6], ['w2', 5], ['w3', 5]]   # 16


def test_a_bench_absent_or_at_zero_gets_no_items():
    zero = {'judging': {'attack': 0, 'guard': 0, 'calibration': 0}, 'shown': {'attack': 0, 'guard': 0}}
    for quotas in ({}, {'searchqa': zero}):
        found = items_.counts('searchqa', 4, quotas)
        assert found['rule'] == 'no_items' and flat(found) == (0, 0, 0, 0, 0)
        assert found['attack_split'] == {'judging': [['w1', 0], ['w2', 0], ['w3', 0], ['w4', 0]],
                                         'shown': [['w1', 0], ['w2', 0], ['w3', 0], ['w4', 0]]}
    with pytest.raises(ValueError):
        items_.counts('searchqa', 1, {'searchqa': {'judging': {'attack': 1}, 'shown': {}}})
    with pytest.raises(ValueError):
        items_.counts('searchqa', 1, {'searchqa': {**zero, 'judging': {'attack': -1, 'guard': 0, 'calibration': 0}}})
    with pytest.raises(ValueError):
        items_.counts('searchqa', ['w1', 'w1'])


def test_check_counts_validates_a_reduced_counts_record():
    found = items_.counts('zebralogic', ['w1', 'w2', 'w3'])
    assert items_.check_counts(found) is found
    broken = json.loads(json.dumps(found))
    broken['attack_split']['judging'][0][1] += 1
    with pytest.raises(ValueError):
        items_.check_counts(broken)
    replacement = {'judging': {'attack': 80, 'guard': 0, 'calibration': 0}, 'shown': {'attack': 0, 'guard': 0},
                   'weakness_ids': ['w1', 'w2', 'w3'],
                   'attack_split': {'judging': [['w1', 27], ['w2', 27], ['w3', 26]], 'shown': []}}
    assert items_.check_counts(replacement) is replacement


# ---- the plan check (T3.4) ----------------------------------------------------------------------------------------
def test_the_plan_check_is_exact_at_its_boundary():
    # 15/20 = 75 %, 16/20 = 80 %: exactly 5 points below -> holds
    assert items_.check_plan(15, 20, 16, 20)['holds'] is True
    # 16/20 = 80 % against 84/100 = 84 %: 4 points -> does not hold
    assert items_.check_plan(16, 20, 84, 100)['holds'] is False
    # thirds: 2/3 = 66.67 % and 43/60 = 71.67 %: exactly 5 points (2/3 + 1/20 = 43/60) -> holds
    found = items_.check_plan(2, 3, 43, 60)
    assert found['holds'] is True and found['difference_points']['exact'] == '5/1'
    # one more calibration item failed: 42/60 = 70 % -> 3.33 points -> does not hold
    assert items_.check_plan(2, 3, 42, 60)['holds'] is False
    # attack easier than calibration
    assert items_.check_plan(9, 10, 1, 10)['holds'] is False
    assert items_.check_plan(0, 0, 3, 10) == {**items_.check_plan(0, 0, 3, 10), 'holds': False, 'reason': 'empty_class'}
    assert items_.check_plan(1, 10, 0, 0)['holds'] is False
    with pytest.raises(ValueError):
        items_.check_plan(3, 2, 1, 1)
    # the record's rates are the exact fractions in points
    record = items_.check_plan(1, 3, 1, 2)
    assert record['attack']['rate']['exact'] == '100/3' and record['calibration']['rate']['exact'] == '50/1'
    assert Fraction(record['difference_points']['exact']) == Fraction(50, 3)


def record(item, cls, side, weakness=None):
    return items_.item_record(item=item, cls=cls, weakness=weakness, side=side, family=item, source='selected',
                              certificate=None, item_sha256='a' * 64)


def test_check_items_counts_classes_and_weaknesses_from_one_run():
    rows = ([record('a%d' % i, 'attack', 'judging', 'w1') for i in range(4)]
            + [record('b%d' % i, 'attack', 'judging', 'w2') for i in range(2)]
            + [record('c%d' % i, 'calibration', 'judging') for i in range(5)] + [record('g0', 'guard', 'judging')])
    outcomes = {'a0': True, 'a1': False, 'a2': None, 'a3': False, 'b0': True, 'b1': True,
                'c0': True, 'c1': True, 'c2': True, 'c3': True, 'c4': False}
    found = items_.check_items(rows, outcomes)
    # attack 3/6 = 50 %, calibration 4/5 = 80 % -> 30 points below -> holds; an unknown run does not pass
    assert found['attack'] == {'n': 6, 'pass': 3, 'rate': {'points': 50.0, 'exact': '50/1'}}
    assert found['calibration']['n'] == 5 and found['calibration']['pass'] == 4 and found['holds'] is True
    assert found['by_weakness'] == [['w1', 4, 1], ['w2', 2, 2]]
    with pytest.raises(ValueError):
        items_.check_items(rows, {k: v for k, v in outcomes.items() if k != 'c4'})     # an outcome per checked item
    with pytest.raises(ValueError):
        items_.check_items([record('s0', 'attack', 'shown', 'w1')], {'s0': True})


# ---- proportions -------------------------------------------------------------------------------------------------
def test_largest_remainder_by_hand():
    # the 100 gate items of typed-v2 by size (BANK-PILOT B31 (h)), 60 calibration puzzles:
    # 60 * w / 100 = 7.2 7.8 3.6 6 5.4 | 7.2 6 6.6 6 4.2 -> floors 57, three left to remainders .8, .6, .6
    sizes = ['5*2', '5*3', '5*4', '5*5', '5*6', '6*2', '6*3', '6*4', '6*5', '6*6']
    gate = [12, 13, 6, 10, 9, 12, 10, 11, 10, 7]
    found = items_.largest_remainder(60, list(zip(sizes, gate)))
    assert found == list(zip(sizes, [7, 8, 4, 6, 5, 7, 6, 7, 6, 4]))
    # equal remainders: the larger weight first (5 * 3 / 10 and 5 * 1 / 10 both leave 5 / 10), then the listed order
    assert items_.largest_remainder(5, [('a', 1), ('b', 3), ('c', 6)]) == [('a', 0), ('b', 2), ('c', 3)]
    assert items_.largest_remainder(2, [('a', 1), ('b', 2), ('c', 1)]) == [('a', 1), ('b', 1), ('c', 0)]
    assert items_.largest_remainder(0, [('a', 0)]) == [('a', 0)]
    assert items_.largest_remainder(3, [('a', 0), ('b', 2)]) == [('a', 0), ('b', 3)]
    with pytest.raises(ValueError):
        items_.largest_remainder(1, [('a', 0)])
    assert items_.ordered_proportion(5, [('a', 1), ('b', 3), ('c', 6)]) == ['b', 'c', 'b', 'c', 'c']


# ---- records and hashes -------------------------------------------------------------------------------------------
def test_item_records_are_validated():
    good = dict(item='q1', cls='attack', weakness='w2', side='judging', family='q1', source='selected', certificate=None,
                item_sha256='0' * 64)
    found = items_.item_record(**good)
    assert sorted(found) == sorted(items_.RECORD_KEYS) and found['class'] == 'attack'
    bad = [{'cls': 'calibration', 'side': 'shown', 'weakness': None},     # the shown side has no calibration
           {'weakness': 'weak-1'}, {'weakness': 'w0'},                      # not a canonical weakness id
           {'cls': 'guard'},                                                # a weakness on a guard item
           {'source': 'made'},                                              # a made item without its certificate
           {'certificate': {}},                                             # a selected item with one
           {'item_sha256': 'A' * 64}, {'family': ''}, {'item': ''}, {'side': 'judge'}, {'source': 'bank'}]
    for change in bad:
        with pytest.raises(ValueError):
            items_.item_record(**{**good, **change})
    with pytest.raises(ValueError):
        items_.check_record({**found, 'extra': 1})
    assert items_.item_record(**{**good, 'cls': 'attack', 'weakness': None})['weakness'] is None   # no-weakness draw


def test_item_hashes_cover_what_a_solver_and_the_judge_read():
    sq = {'benchmark': 'searchqa', 'task_id': 'sq-1', 'family_id': 'exact-1', 'part': 'pool',
          'public': {'question': 'q', 'context': 'c'}, 'private': {'answers': ['a'], 'source_sha256': 'x'}}
    base = items_.item_sha256('searchqa', sq)
    assert items_.item_sha256('searchqa', {**sq, 'family_id': 'other', 'part': 'tail'}) == base
    assert items_.item_sha256('searchqa', {**sq, 'private': {'answers': ['a'], 'source_sha256': 'y'}}) == base
    assert items_.item_sha256('searchqa', {**sq, 'private': {'answers': ['b']}}) != base
    assert items_.item_sha256('searchqa', {**sq, 'public': {'question': 'q', 'context': 'd'}}) != base
    assert items_.item_sha256('searchqa', {**sq, 'task_id': 'sq-2'}) != base
    alf = {'benchmark': 'alfworld', 'task_id': 'g1', 'room': '5', 'task_type': 'pick_and_place_simple',
           'public': {'game_file': 'x/game.tw-pddl', 'routing_view': {'initial_observation': 'o'},
                      'routing_view_sha256': 'h'}, 'private': {'game_metadata': {}}}
    base = items_.item_sha256('alfworld', alf)
    assert items_.item_sha256('alfworld', {**alf, 'room': '6', 'task_type': 'other'}) == base
    assert items_.item_sha256('alfworld', {**alf, 'private': {'game_metadata': {'k': 1}}}) != base
    zebra = {'benchmark': 'zebralogic', 'task_id': 'z1', 'task': '5*2', 'partition': 'made', 'part': 'made',
             'public': {'question': 'Q', 'columns': ['Name', 'Pet']}, 'private': {'answer': {'House 1': {}}}}
    from skillopt.execskill.typed.bank import zebra_build
    assert items_.item_sha256('zebralogic', zebra) == zebra_build.item_digest(zebra)
    with pytest.raises(ValueError):
        items_.item_sha256('searchqa', {'task_id': 'x', 'public': {}, 'private': {}})


def changed(item, path, value):
    """A deep copy of ``item`` with the field at ``path`` set to ``value``."""
    copy = json.loads(json.dumps(item))
    target = copy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return copy


SQ_ITEM = {'benchmark': 'searchqa', 'task_id': 'sq-1', 'family_id': 'exact-1', 'part': 'pool',
           'public': {'question': 'Which river?', 'context': 'The Nile flows north.'}, 'private': {'answers': ['Nile']}}
ALF_ITEM = {'benchmark': 'alfworld', 'task_id': 'alfworld-xs:01', 'room': '5', 'task_type': 'pick_and_place_simple',
            'public': {'game_file': 'json_2.1.1/train/pick_and_place_simple-Mug-None-Shelf-5/trial_1/game.tw-pddl',
                       'routing_view': {'initial_observation': 'You are in a room. Your task is to: put a mug on a shelf.',
                                        'admissible_commands_at_reset': ['look', 'go to shelf 1'],
                                        'task_text': 'put a mug on a shelf'},
                       'routing_view_sha256': 'a' * 64},
            'private': {'game_metadata': {'walkthrough': ['go to shelf 1']}}}
ZEBRA_ITEM = {'benchmark': 'zebralogic', 'task_id': 'zm3-0123456789abcdef', 'task': '5*2', 'partition': 'made',
              'part': 'made', 'origin': 'made', 'family_id': 'zebralogic:zm3-0123456789abcdef',
              'public': {'question': 'There are 5 houses ...', 'columns': ['Name', 'Pet']},
              'private': {'answer': {'House 1': {'Name': 'Alice', 'Pet': 'cat'}}}}
# (bench, item, every field a solver or the judge reads, each with another value)
READ_FIELDS = [
    ('searchqa', SQ_ITEM, [(('task_id',), 'sq-2'), (('public', 'question'), 'Which sea?'),
                           (('public', 'context'), 'The Nile flows south.'), (('private', 'answers'), ['Amazon'])]),
    ('alfworld', ALF_ITEM, [(('task_id',), 'alfworld-xs:02'),
                            (('public', 'game_file'), ALF_ITEM['public']['game_file'].replace('trial_1', 'trial_2')),
                            (('public', 'routing_view', 'initial_observation'), 'You are in another room.'),
                            (('public', 'routing_view', 'admissible_commands_at_reset'), ['look']),
                            (('public', 'routing_view', 'task_text'), 'put a cup on a shelf'),
                            (('public', 'routing_view_sha256'), 'b' * 64),
                            (('private', 'game_metadata'), {'walkthrough': ['go to shelf 2']})]),
    ('zebralogic', ZEBRA_ITEM, [(('task_id',), 'zm3-fedcba9876543210'), (('task',), '5*3'),
                                (('public', 'question'), 'There are 5 houses, again ...'),
                                (('public', 'columns'), ['Name', 'Drink']),
                                (('private', 'answer', 'House 1', 'Pet'), 'dog')])]


@pytest.mark.parametrize('bench, item, fields', READ_FIELDS, ids=[row[0] for row in READ_FIELDS])
def test_every_field_a_solver_or_the_judge_reads_changes_the_item_hash(bench, item, fields):
    # review P2a finding 5: each field changed alone changes the digest (dropping the public part of a bench's digest,
    # or any of its fields, fails here); the bookkeeping fields do not
    base = items_.item_sha256(bench, item)
    digests = {base}
    for path, value in fields:
        digest = items_.item_sha256(bench, changed(item, path, value))
        assert digest != base, path
        digests.add(digest)
    assert len(digests) == len(fields) + 1                          # every change gives its own digest
    for path in (('benchmark',), ('family_id',), ('part',), ('room',), ('task_type',), ('origin',), ('partition',)):
        if path[0] in item:
            assert items_.item_sha256(bench, changed(item, path, 'other')) == base, path


# ---- the store and the registry -----------------------------------------------------------------------------------
def test_slot_names_and_the_path_guard(root):
    assert store_.slot_name('judging', 'attack', 'w3', 7) == 'judging-attack-w3-007'
    assert store_.slot_name('shown', 'guard', None, 12) == 'shown-guard-x-012'
    for args in (('judge', 'attack', None, 1), ('shown', 'attack', 'weak', 1), ('shown', 'attack', None, 0)):
        with pytest.raises(ValueError):
            store_.slot_name(*args)
    with pytest.raises(ValueError):
        store_.ItemStore(root / 'unit-test')                 # a forbidden word in the unit path
    store = store_.ItemStore(root / 'unit')
    with pytest.raises(ValueError):
        store.once(('final', 'x.json'), lambda: {})


def test_the_store_writes_once(root):
    store = store_.ItemStore(root / 's3' / 'items')
    calls = []
    value = store.once(('zebralogic', 'language.json'), lambda: calls.append(1) or {'a': 1})
    assert value == {'a': 1} and store.once(('zebralogic', 'language.json'), lambda: calls.append(2) or {'a': 2}) == {'a': 1}
    assert calls == [1]
    rec = record('q1', 'attack', 'judging', 'w1')
    with pytest.raises(ValueError):
        store.write_slot('judging-attack-w1-001', record=rec, shortfall=None, attempts=[])   # no item file yet
    store.write_item('judging-attack-w1-001', {'task_id': 'q1'})
    first = store.write_slot('judging-attack-w1-001', record=rec, shortfall=None, attempts=[{'n': 1}])
    assert store.slot('judging-attack-w1-001') == first and store.item('judging-attack-w1-001') == {'task_id': 'q1'}
    assert store.write_slot('judging-attack-w1-001', record=rec, shortfall=None, attempts=[{'n': 1}]) == first
    with pytest.raises(ValueError):
        store.write_slot('judging-attack-w1-001', record=None, shortfall='no_candidate', attempts=[])
    with pytest.raises(ValueError):
        store.write_slot('judging-attack-w1-002', record=rec, shortfall='both', attempts=[])
    short = store.write_slot('judging-attack-w1-002', record=None, shortfall='no_candidate', attempts=[])
    assert short['record'] is None and short['shortfall'] == 'no_candidate'
    on_disk = json.loads((root / 's3' / 'items' / 'records' / 'judging-attack-w1-001.json').read_text())
    assert on_disk == first and on_disk['version'] == items_.RECORD_VERSION


def test_a_make_input_is_checked_before_anything_is_made(root):
    pool = [{'task_id': 'i%d' % n, 'public': {}, 'private': {}} for n in range(6)]
    good = dict(bench='searchqa', plan={'weaknesses': [], 'guards': []}, counts=items_.counts('searchqa', 0), pool=pool,
                pool_pin={}, learn_ids=['i0', 'i1'], gate_ids=['i2'], outcomes={'i0': [True, False, None], 'i1': [False] * 3},
                repeats=3, identity={'version': 'typed-v3', 'chain': 'G', 'step': 2, 'round': 1},
                registry=store_.RunRegistry(), store=store_.ItemStore(root / 'u'))
    assert items_.MakeInput(**good).check().bench == 'searchqa'
    assert items_.identity_tag(good['identity']) == 'typed-v3:G:s2:r1'
    bad = [{'outcomes': {'i0': [True] * 3}},                                  # an outcome row per learn item
           {'outcomes': {'i0': [1, 0, 0], 'i1': [False] * 3}},                # booleans, not numbers
           {'outcomes': {'i0': [True] * 2, 'i1': [False] * 2}},               # R per item
           {'gate_ids': ['i1']},                                              # disjoint slices
           {'learn_ids': ['i0', 'zz'], 'outcomes': {'i0': [True] * 3, 'zz': [True] * 3}},   # ids of the pool
           {'pool': pool + pool[:1]},                                          # each pool item once
           {'identity': {'version': 'typed-v3', 'chain': 'X', 'step': 2}},
           {'identity': {'version': 'typed-v3', 'chain': 'G', 'step': 2, 'round': 3}},
           {'identity': {'version': 'typed-v3', 'chain': 'G', 'step': 0}},
           {'counts': {'judging': {'attack': 1}, 'shown': {}}},
           {'plan': None}]
    for change in bad:
        with pytest.raises(ValueError):
            items_.MakeInput(**{**good, **change}).check()


def test_an_item_file_is_written_once(root):
    # review P2a finding 4: an existing item file is kept when the same item is written again (byte for byte the
    # same file) and a different item is refused, also when a slot record already binds the first one
    store = store_.ItemStore(root / 'u')
    item = {'task_id': 'q1', 'public': {'question': 'Q', 'context': 'C'}, 'private': {'answers': ['A']}}
    store.write_item('judging-guard-x-001', item)
    path = root / 'u' / 'items' / 'judging-guard-x-001.json'
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    same = {'private': {'answers': ['A']}, 'public': {'context': 'C', 'question': 'Q'}, 'task_id': 'q1'}   # key order
    store.write_item('judging-guard-x-001', same)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    for other in ({**item, 'private': {'answers': ['B']}}, {**item, 'extra': None}, {'task_id': 'q1'}):
        with pytest.raises(ValueError):
            store.write_item('judging-guard-x-001', other)
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    record = items_.item_record(item='q1', cls='guard', weakness=None, side='judging', family='q1', source='selected',
                                certificate=None, item_sha256=items_.item_sha256('searchqa', item))
    store.write_slot('judging-guard-x-001', record=record, shortfall=None, attempts=[])
    with pytest.raises(ValueError):
        store.write_item('judging-guard-x-001', {**item, 'public': {'question': 'Q2', 'context': 'C'}})
    assert store.item('judging-guard-x-001') == item
    assert items_.item_sha256('searchqa', store.item('judging-guard-x-001')) == record['item_sha256']


def test_the_registry_knows_ids_families_and_texts():
    made = items_.item_record(item='zm3-1', cls='guard', weakness=None, side='shown', family='zm3-1', source='made',
                              certificate={'text_sha256': 'f' * 64}, item_sha256='b' * 64)
    registry = store_.RunRegistry([record('q1', 'attack', 'judging', 'w1'), made])
    assert registry.ids == {'q1', 'zm3-1'} and registry.texts == {'f' * 64}
    assert registry.family_sides('q1') == {'judging'} and registry.family_sides('none') == frozenset()
    with pytest.raises(ValueError):
        registry.add(record('q1', 'guard', 'shown'))                              # an item once per run
    with pytest.raises(ValueError):
        registry.add({**made, 'item': 'zm3-2'})                                   # a text once per run
    assert registry.summary() == {'ids': 2, 'texts': 1, 'families': 2}
