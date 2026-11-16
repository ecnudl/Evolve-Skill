"""typed-v3 item stage tools, section 3 (brief P2a): the ZebraLogic maker. A small language written here stands in for
the pool's (as in the bank's tests); no benchmark data, no model, no network."""
import json
import random
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill import zebralogic
from skillopt.execskill.typed import items as items_
from skillopt.execskill.typed.bank import zebra, zebra_build
from skillopt.execskill.typed.bank.env import text_sha256
from skillopt.execskill.typed.items import store as store_, zebra_items

VALUES = {'Name': ['Alice', 'Arnold', 'Bob', 'Carol', 'Eric', 'Peter'],
          'Pet': ['bird', 'cat', 'dog', 'fish', 'hamster', 'rabbit'],
          'Mother': ['Aniya', 'Holly', 'Janelle', 'Kailyn', 'Penny', 'Sarah'],
          'Height': ['average', 'short', 'super tall', 'tall', 'very short', 'very tall']}
INTRO = {'Name': 'Each person has a unique name', 'Pet': 'Each person has a unique type of pet',
         'Mother': "The mothers' names in different houses are unique", 'Height': 'People have unique heights'}
PHRASE = {'Name': '%s', 'Pet': 'the person who keeps a %s', 'Mother': "The person whose mother's name is %s",
          'Height': 'the person who is %s'}
LANGUAGE = {'columns': {column: {'intro': INTRO[column],
                                 'values': {str(n): sorted(VALUES[column][:n]) for n in range(2, 7)}} for column in VALUES},
            'phrases': {column: {value: PHRASE[column] % value for value in VALUES[column]} for column in VALUES}}
OTHERS = sorted(column for column in VALUES if column != 'Name')
PIN = {'path': '/somewhere/pool.json', 'sha256': 'a' * 64}
IDENTITY = {'version': 'typed-v3', 'chain': 'G', 'step': 3, 'round': 1}


def pool_rows(count=72):
    rows = []
    for number in range(count):
        houses, columns = (5, 6)[number % 2], (2, 3, 4)[number % 3]
        rng = random.Random('pool:%d' % number)
        puzzle = zebra.make(rng, houses, ['Name'] + rng.sample(OTHERS, columns - 1), LANGUAGE)
        rows.append(zebra.row_of(puzzle, LANGUAGE, 'lgp-test-%03d' % number))    # pool ids may hold 'test'
    return rows


POOL = [zebralogic.normalize(row, partition='pool') for row in pool_rows()]
BY_SIZE = {}
for _item in POOL:
    BY_SIZE.setdefault(_item['task'], []).append(_item['task_id'])
# sizes cycle 5*2, 6*3, 5*4, 6*2, 5*3, 6*4 (12 items each); learn: two of every size; gate: 5 x 5*2, 2 x 5*3, 1 x 6*2
LEARN = [i for size in ('5*2', '5*3', '5*4', '6*2', '6*3', '6*4') for i in BY_SIZE[size][:2]]
GATE = BY_SIZE['5*2'][2:7] + BY_SIZE['5*3'][2:4] + BY_SIZE['6*2'][2:3]
SHEET_SIZES = ['5*2', '5*3', '5*4', '6*2', '6*3', '6*4']
# outcomes of B (R = 3): 5*2 and 6*2 right in every run; the rest mixed
OUTCOMES = {i: [True, True, True] for i in BY_SIZE['5*2'][:2] + BY_SIZE['6*2'][:2]}
OUTCOMES.update({i: [True, False, False] for i in BY_SIZE['5*3'][:2] + BY_SIZE['6*3'][:2]})
OUTCOMES.update({i: [False, False, False] for i in BY_SIZE['5*4'][:2] + BY_SIZE['6*4'][:2]})


@pytest.fixture
def root():
    base = Path('/tmp/typed3-items-neutral')
    base.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='zebra-', dir=base))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def quotas(a, g, k, sa, sg):
    return {'zebralogic': {'judging': {'attack': a, 'guard': g, 'calibration': k}, 'shown': {'attack': sa, 'guard': sg}}}


def plan_of(*specs):
    return {'weaknesses': [{'id': 'w%d' % n, 'given_id': None, 'description': 'kind %d' % n, 'evidence': [],
                            'signature': '', 'spec': spec} for n, spec in enumerate(specs, 1)],
            'guards': [], 'note': '', 'unreadable': False}


def make_input(folder, plan, counts, *, registry=None, pool=POOL, identity=IDENTITY, language=None):
    return items_.MakeInput(bench='zebralogic', plan=plan, counts=counts, pool=pool, pool_pin=PIN, learn_ids=LEARN,
                            gate_ids=GATE, outcomes=OUTCOMES, repeats=3, identity=identity,
                            registry=registry if registry is not None else store_.RunRegistry(),
                            store=store_.ItemStore(folder), language=language)


def files(folder):
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(Path(folder).rglob('*.json'))}


# ---- the sheet and the sizes -------------------------------------------------------------------------------------------
def test_the_capability_sheet_names_the_sizes_of_the_practice_slices():
    maker = zebra_items.ZebraMaker()
    sheet = maker.capability_sheet(pool=POOL, learn_ids=LEARN, gate_ids=GATE)
    assert sheet['fields']['sizes']['values'] == SHEET_SIZES
    assert sheet['fields']['emphasis']['keys'] == list(zebra.KINDS) and sheet['fields']['emphasis']['range'] == [0.5, 2.0]
    assert sheet['fields']['search']['values'] == ['any', 'needed']
    only = maker.capability_sheet(pool=POOL, learn_ids=BY_SIZE['6*3'][:1], gate_ids=BY_SIZE['5*2'][:1])
    assert only['fields']['sizes']['values'] == ['5*2', '6*3']
    assert maker.public_kind(POOL[0]) == {'size': '5*2'}


def test_guard_sizes_by_hand():
    learn = [{'task_id': i, 'task': size} for size in SHEET_SIZES for i in BY_SIZE[size][:2]]
    assert zebra_items.guard_sizes(learn, OUTCOMES, 3, SHEET_SIZES) == (['5*2', '6*2'], 'all_right')
    # nobody right in all runs: 5*3 and 6*3 at 2/6, 6*2 at 4/6 (one item 3/3, one 1/3), 5*2 at 4/6 too
    mixed = dict(OUTCOMES)
    mixed.update({BY_SIZE['5*2'][0]: [True, True, True], BY_SIZE['5*2'][1]: [False, True, False]})
    mixed.update({BY_SIZE['6*2'][0]: [True, False, True], BY_SIZE['6*2'][1]: [False, True, True]})
    assert zebra_items.guard_sizes(learn, mixed, 3, SHEET_SIZES) == (['5*2', '6*2'], 'two_highest')
    # a tie for the second place: 6*2 at 4/6 and 5*3 at 4/6 -> the earlier size (5*3) wins the tie; 5*2 at 5/6 first
    mixed.update({BY_SIZE['5*2'][1]: [True, True, False], BY_SIZE['5*3'][0]: [True, True, True],
                  BY_SIZE['5*3'][1]: [True, False, False]})
    assert zebra_items.guard_sizes(learn, mixed, 3, SHEET_SIZES) == (['5*2', '5*3'], 'two_highest')


def test_the_slots_follow_the_counts_and_the_rules():
    counts = items_.counts('zebralogic', ['w1', 'w2', 'w3'], quotas(8, 3, 7, 4, 3))
    assert counts['attack_split'] == {'judging': [['w1', 3], ['w2', 3], ['w3', 2]], 'shown': [['w1', 2], ['w2', 1], ['w3', 1]]}
    plan = plan_of({'sizes': ['5*3', '6*4'], 'emphasis': {'same': 2.0}, 'search': 'needed'}, {}, {'sizes': ['6*2']})
    by_id = {item['task_id']: item for item in POOL}
    guard = zebra_items.guard_sizes([by_id[i] for i in LEARN], OUTCOMES, 3, SHEET_SIZES)
    slots = zebra_items.plan_slots(plan, counts, SHEET_SIZES, [by_id[i] for i in GATE], guard)
    rows = [(s['side'], s['class'], s['weakness'], s['size']) for s in slots]
    assert rows[:8] == [('judging', 'attack', 'w1', '5*3'), ('judging', 'attack', 'w1', '6*4'),
                        ('judging', 'attack', 'w1', '5*3'),
                        ('judging', 'attack', 'w2', '5*2'), ('judging', 'attack', 'w2', '5*3'),      # every size in turn
                        ('judging', 'attack', 'w2', '5*4'), ('judging', 'attack', 'w3', '6*2'),
                        ('judging', 'attack', 'w3', '6*2')]
    assert [r[3] for r in rows if r[:2] == ('judging', 'guard')] == ['5*2', '6*2', '5*2']               # in turn
    # calibration 7 by the gate (5, 2, 1 of 5*2, 5*3, 6*2): 4.375 1.75 0.875 -> 4 1 0, remainders 3 6 7 of 8 -> 4 2 1,
    # interleaved in turn
    assert [r[3] for r in rows if r[1] == 'calibration'] == ['5*2', '5*3', '6*2', '5*2', '5*3', '5*2', '5*2']
    assert [r[:3] for r in rows if r[0] == 'shown'] == [('shown', 'attack', 'w1'), ('shown', 'attack', 'w1'),
                                                        ('shown', 'attack', 'w2'), ('shown', 'attack', 'w3'),
                                                        ('shown', 'guard', None), ('shown', 'guard', None),
                                                        ('shown', 'guard', None)]
    first = slots[0]
    assert (first['slot'], first['emphasis'], first['search']) == ('judging-attack-w1-001', {'same': 2.0}, 'needed')
    assert len({s['slot'] for s in slots}) == len(slots)
    # without kept weaknesses: the attack puzzles are drawn like calibration puzzles, weakness None
    reduced = items_.counts('zebralogic', [], quotas(8, 3, 7, 4, 3))      # judging 18 -> attack 3, guard 3, calibration 12
    slots = zebra_items.plan_slots(plan_of(), reduced, SHEET_SIZES, [by_id[i] for i in GATE], guard)
    attack = [(s['weakness'], s['size']) for s in slots if s['side'] == 'judging' and s['class'] == 'attack']
    # 3 by 5, 2, 1 of 8: 1.875 .75 .375 -> 1 0 0, remainders 7 6 3 of 8 -> 5*2 2, 5*3 1, interleaved in turn
    assert attack == [(None, '5*2'), (None, '5*3'), (None, '5*2')]


# ---- making ------------------------------------------------------------------------------------------------------------
def test_made_puzzles_are_certified_items_of_the_benchmarks_own_form(root):
    counts = items_.counts('zebralogic', ['w1', 'w2', 'w3'], quotas(3, 2, 3, 2, 1))
    plan = plan_of({'sizes': ['5*2']}, {'sizes': ['5*3']}, {'sizes': ['6*2']})
    inp = make_input(root / 'u', plan, counts)
    found = zebra_items.ZebraMaker().make(inp)
    assert found['status'] == 'made' and not found['shortfalls']
    assert found['made_counts'] == {'judging': {'attack': 3, 'guard': 2, 'calibration': 3},
                                    'shown': {'attack': 2, 'guard': 1, 'calibration': 0}}
    language = json.loads((root / 'u' / 'zebralogic' / 'language.json').read_text())
    assert language['checks']['written_back_exactly'] == len(POOL) == language['checks']['solved_to_the_reference_alone']
    for row, record in zip(found['slots'], found['records']):
        item = inp.store.item(row['slot'])
        assert record['item'] == item['task_id'] == row['item'] and record['family'] == record['item']
        assert record['source'] == 'made' and record['item_sha256'] == zebra_build.item_digest(item)
        assert item['task'] == row['size'] and item['part'] == 'made' and item['origin'] == 'made'
        assert record['item'].startswith('zm3-') and len(record['item']) == 20
        certificate = record['certificate']
        assert certificate['solutions'] == 1 and certificate['second_solver_agrees'] and certificate['no_clue_can_be_left_out']
        # the certificate is the one a fresh certification of the stored item gives
        again = zebra.certify(zebra_build.row_of_task(item) | {'puzzle': item['public']['question']}, language)
        assert {key: certificate[key] for key in again} == again
        assert certificate['text_sha256'] == text_sha256(item['public']['question'])
        assert zebra_build.row_of_task(item)['solution'] == zebra.row_of(
            zebra_items.make_puzzle(language, row['size'], certificate['seed'], certificate['emphasis']), language,
            item['task_id'])['solution']
    assert inp.registry.ids == {r['item'] for r in found['records']}
    assert len(inp.registry.texts) == len(found['records'])
    assert json.loads((root / 'u' / 'zebralogic' / 'maker.json').read_text()) == found['record']


def test_certification_comes_before_the_item_is_written(root, monkeypatch):
    certified, real = [], zebra.certify
    refuse = zebra_items.seed_of(IDENTITY, 'judging', 'guard', None, 1, 1)      # the first attempt of one slot

    def certify(row, language):
        certified.append(row['id'])
        if row['id'] == zebra_items.item_id_of(refuse):
            raise ValueError('Not exactly the stored grid (first solver)')
        return real(row, language)
    written, real_write = [], store_.ItemStore.write_item

    def write_item(self, name, item):
        assert item['task_id'] in certified                   # nothing is written before its certificate
        written.append(item['task_id'])
        return real_write(self, name, item)
    monkeypatch.setattr(zebra, 'certify', certify)
    monkeypatch.setattr(store_.ItemStore, 'write_item', write_item)
    counts = items_.counts('zebralogic', [], quotas(0, 2, 1, 0, 0))
    found = zebra_items.ZebraMaker().make(make_input(root / 'u', plan_of(), counts))
    guard = next(row for row in found['slots'] if row['slot'] == 'judging-guard-x-001')
    stored = store_.ItemStore(root / 'u').slot('judging-guard-x-001')
    assert [a.get('refused') for a in stored['attempts']] == ['not_certified', None]
    assert stored['attempts'][0]['detail'].startswith('Not exactly') and guard['attempts'] == 2
    assert zebra_items.item_id_of(refuse) not in written and len(written) == len(found['records']) == 3


def test_a_text_of_the_pool_or_of_an_earlier_made_puzzle_is_refused(root):
    counts = items_.counts('zebralogic', [], quotas(0, 1, 1, 0, 0))
    language = zebra_build.stage_language(store_.ItemStore(root / 'lang'), POOL, PIN)
    # what the first attempts of the two slots make
    first = {}
    for side, cls, size in (('judging', 'guard', '5*2'), ('judging', 'calibration', '5*2')):
        seed = zebra_items.seed_of(IDENTITY, side, cls, None, 1, 1)
        first[cls] = zebra.row_of(zebra_items.make_puzzle(language, size, seed, {}), language, 'lgp-test-900')
    # the guard slot's first puzzle is in the pool; the calibration slot's first puzzle was made earlier in the run
    pool = POOL + [zebralogic.normalize(first['guard'], partition='pool')]
    earlier = items_.item_record(item='zm3-earlier', cls='calibration', weakness=None, side='judging',
                                 family='zm3-earlier', source='made',
                                 certificate={'text_sha256': text_sha256(first['calibration']['puzzle'])},
                                 item_sha256='e' * 64)
    inp = make_input(root / 'u', plan_of(), counts, registry=store_.RunRegistry([earlier]), pool=pool)
    found = zebra_items.ZebraMaker().make(inp)
    store = store_.ItemStore(root / 'u')
    assert [a.get('refused') for a in store.slot('judging-guard-x-001')['attempts']] == ['pool_text', None]
    assert [a.get('refused') for a in store.slot('judging-calibration-x-001')['attempts']] == ['made_text', None]
    texts = {r['certificate']['text_sha256'] for r in found['records']}
    assert text_sha256(first['guard']['puzzle']) not in texts and len(found['records']) == 2


def test_sizes_emphasis_and_search_are_followed(root):
    # three weaknesses of one size: 'same' clues kept more (2.0), fewer (0.5), and search needed at 5*2
    counts = items_.counts('zebralogic', ['w1', 'w2', 'w3'], quotas(30, 0, 0, 0, 0))
    plan = plan_of({'sizes': ['5*3'], 'emphasis': {'same': 2.0}}, {'sizes': ['5*3'], 'emphasis': {'same': 0.5}},
                   {'sizes': ['5*2'], 'search': 'needed'})
    inp = make_input(root / 'u', plan, counts)
    found = zebra_items.ZebraMaker().make(inp)
    assert not found['shortfalls'] and len(found['records']) == 30
    language = json.loads((root / 'u' / 'zebralogic' / 'language.json').read_text())
    kinds = {}
    for row, record in zip(found['slots'], found['records']):
        item = inp.store.item(row['slot'])
        parsed = zebra.parse(item['public']['question'], language)
        assert '%d*%d' % (parsed['houses'], len(parsed['columns'])) == {'w1': '5*3', 'w2': '5*3', 'w3': '5*2'}[row['weakness']]
        entry = kinds.setdefault(row['weakness'], {'same': 0, 'clues': 0, 'nodes': []})
        entry['same'] += sum(clue[0] == 'same' for clue in parsed['clues'])
        entry['clues'] += len(parsed['clues'])
        entry['nodes'].append(zebra.solve(parsed['houses'], parsed['columns'], parsed['clues'], limit=2)[1])
        assert record['certificate']['emphasis'] == plan['weaknesses'][int(row['weakness'][1:]) - 1]['spec'].get('emphasis', {})
    # the emphasis moves the clue kinds: over ten puzzles each, far more 'same' clues kept at 2.0 than at 0.5
    assert kinds['w1']['same'] > 2 * kinds['w2']['same'] > 0
    assert kinds['w1']['same'] / kinds['w1']['clues'] > kinds['w2']['same'] / kinds['w2']['clues']
    # 'needed': no puzzle of w3 is settled without search (one search node), and the filter did refuse some
    assert all(nodes > 1 for nodes in kinds['w3']['nodes'])
    refused = [a for row in found['slots'] if row['weakness'] == 'w3'
               for a in inp.store.slot(row['slot'])['attempts'] if a.get('refused') == 'settled_without_search']
    assert refused
    # natural weights at 5*2 settle some puzzles without search: the filter is what keeps them out
    natural = [zebra.solve(5, p['columns'], p['clues'], limit=2)[1] for p in
               (zebra_items.make_puzzle(language, '5*2', 'natural:%d' % n, {}) for n in range(12))]
    assert min(natural) == 1


def tally(rows, cls):
    sizes = [row['size'] for row in rows if row['class'] == cls]
    return {size: sizes.count(size) for size in set(sizes)}


def test_calibration_and_reduced_attack_sizes_follow_the_gate(root):
    # three kept weaknesses without attack items (the quota rule): 7 calibration puzzles by the gate's 5, 2, 1 of 8
    counts = items_.counts('zebralogic', ['w1', 'w2', 'w3'], quotas(0, 0, 7, 0, 0))
    found = zebra_items.ZebraMaker().make(make_input(root / 'u', plan_of({}, {}, {}), counts))
    assert tally(found['slots'], 'calibration') == {'5*2': 4, '5*3': 2, '6*2': 1}      # 4.375 1.75 .875, see above
    assert all(record['weakness'] is None for record in found['records']) and len(found['records']) == 7
    assert found['record']['gate_sizes'] == [['5*2', 5], ['5*3', 2], ['5*4', 0], ['6*2', 1], ['6*3', 0], ['6*4', 0]]
    # no kept weakness (the 20 % rule): judging 7 -> attack 1, calibration 6; 6 by 5, 2, 1: 3.75 1.5 .75 -> 3 1 0,
    # remainders 6 4 6 of 8: a tie of 5*2 and 6*2, the larger gate count (5*2) first -> 5*2 4, 5*3 1, 6*2 1
    reduced = items_.counts('zebralogic', [], quotas(0, 0, 7, 0, 0))
    found = zebra_items.ZebraMaker().make(make_input(root / 'v', plan_of(), reduced))
    assert tally(found['slots'], 'calibration') == {'5*2': 4, '5*3': 1, '6*2': 1}
    assert [(row['weakness'], row['size']) for row in found['slots'] if row['class'] == 'attack'] == [(None, '5*2')]


def test_made_puzzles_are_reproducible_from_their_seeds(root):
    counts = items_.counts('zebralogic', ['w1', 'w2', 'w3'], quotas(3, 1, 2, 1, 1))
    plan = plan_of({'sizes': ['5*2'], 'emphasis': {'not_at': 0.5}}, {'search': 'needed', 'sizes': ['5*2', '6*2']}, {})
    first = zebra_items.ZebraMaker().make(make_input(root / 'a', plan, counts))
    second = zebra_items.ZebraMaker().make(make_input(root / 'b', plan, counts))
    assert first == second and files(root / 'a') == files(root / 'b')        # byte-identical items and records
    other = zebra_items.ZebraMaker().make(make_input(root / 'c', plan, counts, identity={**IDENTITY, 'round': 2}))
    assert not {r['item'] for r in other['records']} & {r['item'] for r in first['records']}   # another round, other seeds
    assert {r['certificate']['text_sha256'] for r in other['records']}.isdisjoint(
        {r['certificate']['text_sha256'] for r in first['records']})


class Killed(Exception):
    """A process killed in the middle of making (the unit is resumed by running it again)."""


def test_a_resumed_unit_makes_only_the_missing_slots(root, monkeypatch):
    counts = items_.counts('zebralogic', ['w1', 'w2', 'w3'], quotas(3, 2, 2, 1, 1))
    plan = plan_of({'sizes': ['5*2']}, {'sizes': ['5*3']}, {})
    whole = zebra_items.ZebraMaker().make(make_input(root / 'whole', plan, counts))
    made, real = [], zebra_items.ZebraMaker.make_slot

    def stop_after_four(self, inp, slot, *args):
        if len(made) == 4:
            raise Killed()
        made.append(slot['slot'])
        return real(self, inp, slot, *args)
    monkeypatch.setattr(zebra_items.ZebraMaker, 'make_slot', stop_after_four)
    with pytest.raises(Killed):
        zebra_items.ZebraMaker().make(make_input(root / 'cut', plan, counts))
    assert not (root / 'cut' / 'zebralogic' / 'maker.json').exists()
    monkeypatch.setattr(zebra_items.ZebraMaker, 'make_slot', real)
    again, seen = [], real

    def counting(self, inp, slot, *args):
        again.append(slot['slot'])
        return seen(self, inp, slot, *args)
    monkeypatch.setattr(zebra_items.ZebraMaker, 'make_slot', counting)
    resumed = zebra_items.ZebraMaker().make(make_input(root / 'cut', plan, counts))
    assert resumed == whole and files(root / 'cut') == files(root / 'whole')
    assert not set(again) & set(made) and len(again) + len(made) == len(whole['slots'])
    # a stored slot of another spec is refused
    other = plan_of({'sizes': ['6*2']}, {'sizes': ['5*3']}, {})
    with pytest.raises(ValueError):
        zebra_items.ZebraMaker().make(make_input(root / 'cut', other, counts))


def test_a_shortfall_is_recorded_and_never_filled(root, monkeypatch):
    def never(row, language):
        raise ValueError('A clue that can be left out')
    monkeypatch.setattr(zebra_items, 'MAX_ATTEMPTS', 3)
    monkeypatch.setattr(zebra, 'certify', never)
    counts = items_.counts('zebralogic', [], quotas(0, 1, 2, 0, 1))
    found = zebra_items.ZebraMaker().make(make_input(root / 'u', plan_of(), counts))
    assert found['records'] == [] and found['made_counts']['judging'] == {'attack': 0, 'guard': 0, 'calibration': 0}
    assert [(s['slot'], s['reason']) for s in found['shortfalls']] == [
        ('judging-guard-x-001', 'attempts_exhausted'), ('judging-calibration-x-001', 'attempts_exhausted'),
        ('judging-calibration-x-002', 'attempts_exhausted'), ('shown-guard-x-001', 'attempts_exhausted')]
    stored = store_.ItemStore(root / 'u').slot('judging-guard-x-001')
    assert [a['refused'] for a in stored['attempts']] == ['not_certified'] * 3 and stored['record'] is None
    assert not (root / 'u' / 'items').exists()


def test_the_language_is_learned_once_or_taken_from_the_step(root):
    counts = items_.counts('zebralogic', [], quotas(0, 1, 0, 0, 0))
    found = zebra_items.ZebraMaker().make(make_input(root / 'u', plan_of(), counts))
    language = json.loads((root / 'u' / 'zebralogic' / 'language.json').read_text())
    assert found['record']['language']['checks'] == language['checks'] and language['pool'] == PIN
    again = zebra_items.ZebraMaker().make(make_input(root / 'v', plan_of(), counts, language=language))
    assert not (root / 'v' / 'zebralogic' / 'language.json').exists()
    assert [r['item_sha256'] for r in again['records']] == [r['item_sha256'] for r in found['records']]
    with pytest.raises(ValueError):
        zebra_items.ZebraMaker().make(make_input(root / 'w', plan_of(), counts, language={**language, 'pool_items': 3}))
    nothing = zebra_items.ZebraMaker().make(make_input(root / 'x', plan_of(), items_.counts('zebralogic', 3, {})))
    assert nothing['status'] == 'no_items' and nothing['reason'] == 'no_quota' and not (root / 'x').exists()
