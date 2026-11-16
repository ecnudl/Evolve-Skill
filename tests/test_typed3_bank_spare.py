"""typed-v3 item bank: re-judging a card of a finished run (bank/rejudge.py: configuration records and the parity
with the run; bank/spare.py: spare real practice items) with fake clients. The cells go through the chain's real cell
function (typed.mount.solve: the frozen solver request and the ZebraLogic judge). No network."""
import importlib.util
import json
import math
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill import solver, zebralogic
from skillopt.execskill.typed import TAU_MIN_POINTS, TAU_SE_MULTIPLIER, gatestats, mount, prepare, units
from skillopt.execskill.typed.bank import env as bank_env, oqa_build, rejudge, spare

GRID = {'House 1': {'Name': 'Eric', 'Drink': 'milk'}, 'House 2': {'Name': 'Arnold', 'Drink': 'tea'}}
WRONG = {'House 1': {'Name': 'Arnold', 'Drink': 'milk'}, 'House 2': {'Name': 'Eric', 'Drink': 'tea'}}
CARD = 'Check every clue against the finished table before answering.\n'      # as a writer stores it: a final newline
OTHER = 'Fill the table one house at a time.\n'
TOOLS = {'mount': mount, 'runtime': {'zebralogic': {}}, 'nominal_tokens': None}


def puzzle(number, prefix='zb'):
    question = ('There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. Each house is '
                'occupied by a different person. Eric drinks milk. The milk drinker lives in house 1. Arnold drinks '
                'tea. (Puzzle %d.)' % number)
    return {'benchmark': 'zebralogic', 'task_id': '%s-%03d' % (prefix, number),
            'public': {'question': question, 'columns': ['Name', 'Drink']}, 'private': {'answer': GRID}}


def number_of(user):
    return int(user.split('(Puzzle ')[1].split('.)')[0])


def config_of(system):
    return 'k2' if OTHER.strip() in system else 'k1' if CARD.strip() in system else 'c'


@pytest.fixture
def root():
    base = Path('/tmp/typed3-neutral')
    base.mkdir(exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='bank-', dir=base))
    yield made
    shutil.rmtree(made, ignore_errors=True)


class Fake:
    """A frozen-contract client. ``answer(system, user)``: a grid (the reply's solution), 'cut' for a reply the model
    cut at its token bound, 'withheld' for a reply the model side filtered, None for an infrastructure failure."""
    max_tokens = 2048

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def call(self, system, user):
        self.calls.append((system, user))
        made = self.answer(system, user)
        if made is None:
            return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'transport'}
        if made == 'cut':
            return {'ok': False, 'response': 'partial', 'finish_reason': 'length', 'usage': {}, 'error_type': 'finish_length'}
        if made == 'withheld':
            return {'ok': False, 'response': None, 'finish_reason': 'content_filter', 'usage': {},
                    'error_type': 'finish_content_filter'}
        return {'ok': True, 'response': json.dumps({'reasoning': 'given', 'solution': made}), 'finish_reason': 'stop',
                'error_type': None, 'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}


def make_env(root, solver_client, width=2):
    ledger = units.Ledger(root / 'ledger.json', 50_000_000, resume=(root / 'ledger.json').exists())
    return bank_env.BankEnv(root, ledger, {'role': None, 'solver': solver_client}, width=width)


IDENT = rejudge.request_identity(TOOLS['runtime'], {'code': 'fixture'})


def step_of(env):
    """The learning step directory the fixtures re-judge (``<root>/run/G/s3``)."""
    path = env.root / 'run' / 'G' / 's3'
    path.mkdir(parents=True, exist_ok=True)
    return path


def allow(env, cards):
    """A passing parity record of step ``step_of(env)`` and identity IDENT that covers ``cards`` (the parity itself
    is tested below with a run's cells)."""
    shas = spare.card_shas(TOOLS, 'zebralogic', cards)
    rows = {name: {'card_sha256': sha, 'gate_items': 1, 'same_request': 1, 'different': 0,
                   'no_run_cell_with_this_card': 0,
                   'source': rejudge.base_source('noise') if cards[name] is None else
                   {'role': 'candidate', 'unit': 'card-r%d' % (1 + sorted(n for n in cards if cards[n] is not None).index(name)),
                    'arms': ['cand_card']}} for name, sha in shas.items()}
    record = {'bench': 'zebralogic', 'step_dir': str(rejudge.step_dir_of(step_of(env))), 'request_identity': IDENT,
              'ok': True, 'configurations': rows}
    units.write_json(env.path('zebralogic', 'spare-parity.json'), record)
    return record


def run_spare(env, items, cards, runs=3, **kwargs):
    return spare.stage_spare(env, TOOLS, 'zebralogic', items, cards, step_dir=step_of(env), identity=IDENT, runs=runs,
                             **kwargs)


def record_of(env, config, task_id):
    return env.read('zebralogic', 'spare-' + config, spare.stem(task_id) + '.json')


# ---- the spare pool ----------------------------------------------------------------------------------------------------
def test_spare_items_continue_the_ranking_the_slices_were_cut_from():
    pool = [puzzle(n) for n in range(1, 11)]
    order = [pool[i]['task_id'] for i in (3, 0, 7, 9, 1, 5, 2, 8, 4, 6)]
    manifest = {'seed': 7, 'pools_root': '/pools', 'pools': {'zebralogic': {'path': 'p', 'sha256': 's'}},
                'slice_sizes': {'zebralogic': {'learn': 2, 'gate': 3}},
                'slices': {'zebralogic': {'learn': order[:2], 'gate': order[2:5]}}}
    seen = {}

    def load_pool(bench, pools_root, pin=None):
        seen['pin'] = (bench, pools_root, pin)
        return list(pool), {}

    def ranked(items, seed, tag):
        seen['draw'] = (seed, tag)
        by_id = {item['task_id']: item for item in items}
        return [by_id[name] for name in order]
    got = spare.spare_items(manifest, 'zebralogic', load_pool=load_pool, ranked=ranked, slice_tag='tag:%s:slices')
    assert [item['task_id'] for item in got] == order[5:]                 # neither slice, in the ranking's order
    assert seen == {'pin': ('zebralogic', '/pools', {'path': 'p', 'sha256': 's'}), 'draw': (7, 'tag:zebralogic:slices')}
    assert [item['task_id'] for item in spare.gate_items(manifest, 'zebralogic', load_pool=load_pool)] == order[2:5]
    manifest['slices']['zebralogic']['gate'] = order[3:6]                 # not the slices of this ranking
    with pytest.raises(AssertionError, match='not the one the run cut its slices from'):
        spare.spare_items(manifest, 'zebralogic', load_pool=load_pool, ranked=ranked, slice_tag='tag:%s:slices')
    manifest['slices']['zebralogic']['gate'] = order[2:4]                 # a gate slice cut short: its last item
    with pytest.raises(AssertionError, match='registered sizes'):         # would become "spare"
        spare.spare_items(manifest, 'zebralogic', load_pool=load_pool, ranked=ranked, slice_tag='tag:%s:slices')
    with pytest.raises(AssertionError):
        spare.spare_items(manifest, 'officeqa', load_pool=load_pool, ranked=ranked, slice_tag='tag:%s:slices')


def _run_bank():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'run_bank.py'
    spec = importlib.util.spec_from_file_location('run_bank_under_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_manifest_is_verified_against_its_seal_and_card_files_are_read_verbatim(root):
    run_bank = _run_bank()
    sealed = prepare.seal({'slices': {'zebralogic': {'learn': ['1'], 'gate': ['2', '3']}}, 'seed': 7})
    path = root / 'manifest.json'
    path.write_text(json.dumps(sealed))
    bank = {'typed_manifest': {'path': str(path), 'record_sha256': sealed['record_sha256']}}
    assert run_bank.typed_manifest_of(bank) == sealed
    cut = json.loads(json.dumps(sealed))
    cut['slices']['zebralogic']['gate'] = ['2']                           # the contents changed, the seal kept
    path.write_text(json.dumps(cut))
    with pytest.raises(Exception, match='hash differs'):
        run_bank.typed_manifest_of(bank)
    path.write_text(json.dumps(sealed))
    with pytest.raises(AssertionError, match='manifest changed'):
        run_bank.typed_manifest_of({'typed_manifest': {'path': str(path), 'record_sha256': 'f' * 64}})
    card = root / 'card-r1.txt'
    card.write_text(CARD, encoding='utf-8')
    cards = run_bank.read_cards('c,k1=%s' % card)
    assert cards == {'c': None, 'k1': CARD} and cards['k1'].endswith('.\n')            # the final newline stays
    assert mount.system_card('zebralogic', cards['k1']) != mount.system_card('zebralogic', CARD.strip())
    (root / 'empty.txt').write_text(' \n')
    for spec in ('k1=%s' % (root / 'empty.txt'), 'c=%s' % card, 'k1', 'k1=%s,k1=%s' % (card, card), ''):
        with pytest.raises(AssertionError):
            run_bank.read_cards(spec)


# ---- the mount of a configuration --------------------------------------------------------------------------------------
def test_a_configuration_mounts_the_hand_card_or_a_card_on_it_on_every_item():
    item = puzzle(1)
    base = spare.forced_mount(mount, 'zebralogic', item, None, TOOLS['runtime'])
    assert base['arm'] == 'C' and base['system_card'] == zebralogic.CARD_TEXT == mount.historical_card('zebralogic')
    cand = spare.forced_mount(mount, 'zebralogic', item, CARD, TOOLS['runtime'])
    assert cand['system_card'] == mount.system_card('zebralogic', CARD, base_card='historical')
    assert cand['system_card'].startswith(CARD) and cand['system_card'].endswith(zebralogic.CARD_TEXT)
    assert cand['arm'] == 'cand_card' and cand['enabled'] == [] and cand['card_text'] == CARD
    assert cand['system_card_sha256'] == units.sha256_text(cand['system_card'])
    with pytest.raises(AssertionError):
        spare.forced_mount(mount, 'zebralogic', item, '  ', TOOLS['runtime'])
    with pytest.raises(AssertionError, match='hand card alone'):
        spare.card_shas(TOOLS, 'zebralogic', {'c': CARD})
    with pytest.raises(AssertionError, match='hand card alone'):
        spare.card_shas(TOOLS, 'zebralogic', {'k2': None})
    with pytest.raises(AssertionError, match='one system card'):
        spare.card_shas(TOOLS, 'zebralogic', {'k3': CARD, 'k4': CARD})


# ---- runs ----------------------------------------------------------------------------------------------------------------
def test_spare_runs_are_fresh_recorded_once_and_final(root):
    items = [puzzle(n, prefix='lgp-test-2x2') for n in range(1, 7)]      # real ids hold a word the path guard refuses
    # the hand card solves the odd puzzles; the model cuts its reply to puzzle 6 and withholds its reply to puzzle 4
    solver_client = Fake(lambda s, u: {6: 'cut', 4: 'withheld'}.get(number_of(u), GRID if number_of(u) % 2 else WRONG))
    env = make_env(root, solver_client)
    with pytest.raises(AssertionError, match='parity check first'):
        run_spare(env, items, {'c': None}, runs=3)
    assert solver_client.calls == []                                      # nothing is sent without the parity record
    allow(env, {'c': None, 'k1': CARD})
    out = run_spare(env, items, {'c': None}, runs=3)
    assert out['results'] == {'c: 0 of 3': 3, 'c: 3 of 3': 3} and out['runs'] == 3 and out['items'] == 6
    assert len(solver_client.calls) == 18                                 # three fresh sends per item
    assert solver_client.calls[0][0] == solver.QA_SYSTEM + '\n\n' + solver.GUIDANCE + zebralogic.CARD_TEXT
    row = record_of(env, 'c', items[5]['task_id'])
    assert [run['verdict'] for run in row['runs']] == ['fail'] * 3 and row['passes'] == 0    # final, not unknown
    row = record_of(env, 'c', items[3]['task_id'])                        # no reply at all: the judge scores it wrong
    assert [(run['verdict'], run['replied']) for run in row['runs']] == [('fail', False)] * 3
    assert record_of(env, 'c', items[0]['task_id'])['passes'] == 3
    assert not any('test' in path.name for path in (root / 'zebralogic').rglob('*'))        # hashed names only
    again = run_spare(env, items, {'c': None}, runs=3)
    assert again['results'] == out['results'] and len(solver_client.calls) == 18             # read, not sent
    k = run_spare(env, items, {'k1': CARD}, runs=3)
    counted = spare.spare_report(env, 'zebralogic', 'c', 'k1')
    assert counted['wrong_runs_without_a_complete_reply'] == {'base': 6, 'candidate': 6} and k['items'] == 6
    assert counted['complete'] is True and counted['items'] == 6
    with pytest.raises(AssertionError):
        run_spare(env, items, {'k1': CARD}, runs=1)


def test_a_cell_left_unknown_follows_the_gate_rule(root):
    """gatestats.arm_runs: an unknown cell that is neither an infrastructure nor a configuration unknown is final and
    scores 0; the other two leave the item open."""
    class Stub:
        def __init__(self, cell):
            self.cell = cell

        def solve(self, bench, item, mounted, **kwargs):
            return dict(self.cell)
    env = make_env(root, Fake(lambda s, u: GRID))
    run = lambda cell: spare.solve_run(env, {'mount': Stub(cell), 'runtime': {}}, 'zebralogic', puzzle(1), {}, 'u', 't')
    final = run({'correct': None, 'token': 'unknown_model', 'configuration_error': False, 'infrastructure_unknown': False})
    assert final == {'verdict': 'fail', 'token': 'unknown_model', 'label': oqa_build.NO_REPLY, 'replied': False, 'flags': []}
    assert run({'correct': None, 'token': 'unknown', 'infrastructure_unknown': True})['verdict'] == 'unknown'
    assert run({'correct': None, 'token': 'unknown', 'configuration_error': True, 'reason': 'x'})['verdict'] == 'unknown'
    assert run({'correct': True, 'token': 'pass', 'reply': 'text', 'flags': ['b', 'a']}) == {
        'verdict': 'pass', 'token': 'pass', 'label': None, 'replied': True, 'flags': ['a', 'b']}


def test_a_configuration_is_bound_before_any_call(root):
    """Review 2026-11-14: an item left open by an infrastructure failure must not be computed under another card,
    another run count or other items when the stage is run again under the same name."""
    items = [puzzle(1), puzzle(2)]
    state = {'down': True}
    solver_client = Fake(lambda s, u: None if state['down'] and number_of(u) == 1 else GRID)
    env = make_env(root, solver_client)
    allow(env, {'k1': CARD})
    out = run_spare(env, items, {'k1': CARD}, runs=2)
    assert out['results'] == {'k1: 2 of 2': 1, 'k1: unknown': 1}          # puzzle 1 stays open, puzzle 2 is recorded
    registered = rejudge.registered(env, 'zebralogic', spare.KIND, 'k1')
    assert registered['items'] == ['zb-001', 'zb-002'] and registered['runs'] == 2 and registered['solver'] == 'G'
    state['down'] = False
    sent = len(solver_client.calls)
    allow(env, {'k1': OTHER})                                             # even with a parity record for the other text
    for cards, runs, pool, word in (({'k1': OTHER}, 2, items, 'another card'), ({'k1': CARD}, 3, items, 'another'),
                                    ({'k1': CARD}, 2, [puzzle(2), puzzle(1)], 'other items')):
        if cards == {'k1': CARD}:
            allow(env, cards)
        with pytest.raises(AssertionError, match=word):
            run_spare(env, pool, cards, runs=runs)
        assert len(solver_client.calls) == sent                           # refused before anything was sent
        assert not env.exists('zebralogic', 'spare-k1', spare.stem('zb-001') + '.json')     # and nothing written
    more = run_spare(env, items + [puzzle(3)], {'k1': CARD}, runs=2)   # more items: continues
    assert more['results'] == {'k1: 2 of 2': 3}
    assert rejudge.registered(env, 'zebralogic', spare.KIND, 'k1')['items'] == ['zb-001', 'zb-002', 'zb-003']
    fewer = run_spare(env, items, {'k1': CARD}, runs=2)                # its head: unchanged
    assert fewer['items'] == 2 and len(rejudge.registered(env, 'zebralogic', spare.KIND, 'k1')['items']) == 3
    # a record of another identity found in the folder stops the stage too (a folder is never mixed)
    path = root / 'zebralogic' / 'spare-k1' / (spare.stem('zb-002') + '.json')
    row = units.read_json(path)
    units.write_json(path, {**row, 'card_sha256': 'e' * 64})
    with pytest.raises(AssertionError, match='records of another card'):
        run_spare(env, items, {'k1': CARD}, runs=2)


def test_a_configuration_without_any_record_is_bound_too(root):
    """A stage whose every item stayed open has written no item record: its name is bound all the same."""
    items = [puzzle(1), puzzle(2)]
    solver_client = Fake(lambda s, u: None)                               # the service is down for the whole stage
    env = make_env(root, solver_client)
    allow(env, {'k1': CARD})
    out = run_spare(env, items, {'k1': CARD}, runs=2)
    assert out['results'] == {'k1: unknown': 2} and not list((root / 'zebralogic' / 'spare-k1').glob('*.json'))
    sent = len(solver_client.calls)
    allow(env, {'k1': OTHER})
    with pytest.raises(AssertionError, match='registered with another card'):
        run_spare(env, items, {'k1': OTHER}, runs=2)
    allow(env, {'k1': CARD})
    with pytest.raises(AssertionError, match='registered with another card, solver or run count'):
        run_spare(env, items, {'k1': CARD}, runs=3)
    assert len(solver_client.calls) == sent


def test_a_card_configuration_sends_the_card_verbatim(root):
    items = [puzzle(n) for n in range(1, 4)]
    solver_client = Fake(lambda s, u: GRID if s.startswith(solver.QA_SYSTEM) and CARD in s else WRONG)
    env = make_env(root, solver_client)
    allow(env, {'k1': CARD})
    out = run_spare(env, items, {'k1': CARD}, runs=2)
    assert out['results'] == {'k1: 2 of 2': 3}
    assert all(CARD + mount.CARD_JOIN + zebralogic.CARD_TEXT in system for system, _ in solver_client.calls)
    with pytest.raises(AssertionError, match='did not cover'):            # the parity record is about another text
        run_spare(env, items, {'k1': CARD.strip()}, runs=2)


def test_an_interrupted_item_reuses_its_delivered_replies(root):
    """Review 2026-11-14: one repeat delivered, a later repeat failing for an infrastructure reason before the item
    record exists; the stage run again must not send (or pay for) the delivered repeat a second time."""
    item = puzzle(1)
    state = {'sends': 0}

    def answer(system, user):
        state['sends'] += 1
        return GRID if state['sends'] != 2 else None                      # the second send (repeat 2) fails
    solver_client = Fake(answer)
    env = make_env(root, solver_client, width=1)
    allow(env, {'c': None})
    out = run_spare(env, [item], {'c': None}, runs=3)
    assert out['results'] == {'c: unknown': 1} and not env.exists('zebralogic', 'spare-c', spare.stem('zb-001') + '.json')
    sent, charged = len(solver_client.calls), env.ledger.state['charged']
    assert sent == 3                                                       # repeat 1 delivered, 2 failed, 3 delivered
    env = make_env(root, solver_client, width=1)                           # a new process on the same root
    out = run_spare(env, [item], {'c': None}, runs=3)
    assert out['results'] == {'c: 3 of 3': 1}
    assert len(solver_client.calls) == sent + 1                            # only the failed repeat is sent again
    assert env.reused['solver'] == 2 and env.ledger.state['charged'] == charged + 15   # one reply paid for, once
    again = run_spare(make_env(root, solver_client), [item], {'c': None}, runs=3)
    assert again['results'] == {'c: 3 of 3': 1} and len(solver_client.calls) == sent + 1


def test_the_ledger_cap_stops_the_stage(root):
    ledger = units.Ledger(root / 'ledger.json', 1, resume=False)       # a cap below one request's bound
    env = bank_env.BankEnv(root, ledger, {'role': None, 'solver': Fake(lambda s, u: GRID)}, width=1)
    allow(env, {'c': None})
    with pytest.raises(units.Stop):
        run_spare(env, [puzzle(1)], {'c': None}, runs=2)
    assert not env.exists('zebralogic', 'spare-c', spare.stem('zb-001') + '.json')


def test_configurations_of_one_stage_meet_each_item_together(root):
    """Base and candidates are sent item by item, never one configuration after the other: a drift of the service
    during a stage cannot be read as a difference between configurations."""
    items = [puzzle(n) for n in range(1, 9)]
    solver_client = Fake(lambda s, u: GRID)
    env = make_env(root, solver_client, width=1)                          # one thread: a fixed order
    cards = {'c': None, 'k1': CARD, 'k2': OTHER}
    allow(env, cards)
    out = run_spare(env, items, cards, runs=2)
    assert out['results'] == {'c: 2 of 2': 8, 'k1: 2 of 2': 8, 'k2: 2 of 2': 8} and sorted(out['configurations']) == ['c', 'k1', 'k2']
    sent = [(number_of(user), config_of(system)) for system, user in solver_client.calls]
    assert [n for n, _ in sent] == [n for n in range(1, 9) for _ in range(6)]       # item by item, six sends each
    orders = {tuple(config for _, config in sent[6 * i:6 * i + 6:2]) for i in range(8)}
    assert len(orders) > 1 and all(sorted(order) == ['c', 'k1', 'k2'] for order in orders)   # the order varies by item
    row = record_of(env, 'k1', 'zb-001')
    assert row['finished_at'] and row['config'] == 'k1' and row['id'] == 'zb-001'


# ---- the report ----------------------------------------------------------------------------------------------------------
def scripted(table):
    """A solver client that answers run r of (puzzle number, configuration) by ``table[(number, config)][r]``."""
    counts = {}

    def answer(system, user):
        key = (number_of(user), config_of(system))
        counts[key] = counts.get(key, 0) + 1
        return GRID if table[key][counts[key] - 1] else WRONG
    return Fake(answer)


def expected_rule(base, cand, ids, repeats=3):
    """The gate rule written out again from DESIGN 3.4 (independent of typed.gatestats)."""
    sb, sk = [sum(base[i]) for i in ids], [sum(cand[i]) for i in ids]
    n, D, Q = len(ids), sum(sk) - sum(sb), sum(repeats * b - b * b for b in sb)
    se = (100.0 / (repeats * n)) * math.sqrt(2 * Q / (repeats - 1))
    gain, tau = 100.0 * D / (repeats * n), max(3.0, 2.0 * se)
    better, worse = sum(k > b for b, k in zip(sb, sk)), sum(k < b for b, k in zip(sb, sk))
    reaches = D >= 0 and 100 * D >= 3 * repeats * n and D * D * (repeats - 1) >= 8 * Q
    return {'n': n, 'gain_points': gain, 'se_points': se, 'tau_points': tau, 'better': better, 'worse': worse,
            'reaches': reaches, 'accepted': reaches and better > worse}


@pytest.mark.parametrize('extra, accepted', [(4, True), (3, False)])
def test_report_gives_the_chains_gate_rule_at_its_threshold(root, extra, accepted):
    """Unequal variances and a gain exactly AT the threshold (D^2 = 4 Q with R = 3: accepted) and one item below it
    (refused). The rule of the report equals typed.gatestats on the records and the rule written out again."""
    T, F = True, False
    numbers = list(range(1, 41))
    base = {n: [T, T, T] if n <= 10 else [T, F, F] if n <= 12 else [F, F, F] for n in numbers}      # Q = 2 + 2 = 4
    cand = {n: list(base[n]) for n in numbers}
    for n in (13, 14, 15, 16)[:extra]:                                    # D = extra: one run more on these items
        cand[n] = [T, F, F]
    cand[11], cand[12] = [T, T, F], [F, F, F]                             # the candidate's own variance differs; net 0
    table = {**{(n, 'c'): base[n] for n in numbers}, **{(n, 'k1'): cand[n] for n in numbers}}
    items = [puzzle(n) for n in numbers]
    env = make_env(root, scripted(table), width=1)
    allow(env, {'c': None, 'k1': CARD})
    run_spare(env, items, {'c': None, 'k1': CARD}, runs=3)
    out = spare.spare_report(env, 'zebralogic', 'c', 'k1')
    ids = [item['task_id'] for item in items]
    by_id = lambda runs: {'zb-%03d' % n: runs[n] for n in numbers}
    want = expected_rule(by_id(base), by_id(cand), ids)
    rule = out['gate_rule']
    assert out['complete'] is True and out['items'] == 40 and out['repeats'] == 3
    for key in ('n', 'better', 'worse', 'reaches', 'accepted'):
        assert rule[key] == want[key], key
    for key in ('gain_points', 'se_points', 'tau_points'):
        assert rule[key] == pytest.approx(want[key]), key
    assert rule['accepted'] is accepted and rule['reason'] == ('accepted' if accepted else 'gain_below_tau')
    assert (rule['gain_points'] >= rule['tau_points']) is accepted and rule['tau_points'] > TAU_MIN_POINTS
    arm = lambda runs: {'sums': {i: sum(runs[i]) for i in ids}, 'squares': {i: sum(runs[i]) for i in ids}, 'unknown': 0}
    direct = gatestats.card_decision(gatestats.repeat_statistics(
        arm(by_id(base)), arm(by_id(cand)), items=ids, repeats=3, minimum_points=TAU_MIN_POINTS,
        multiplier=TAU_SE_MULTIPLIER))
    assert all(rule[key] == direct[key] for key in rule)
    assert out['base_pass_pct'] == round(100.0 * sum(map(sum, base.values())) / 120, 2)
    assert out['candidate_pass_pct'] == round(100.0 * sum(map(sum, cand.values())) / 120, 2)
    low, high = out['gain_interval_95_resampling_items']
    assert low <= rule['gain_points'] <= high
    assert out['reading'] == spare.reading(rule, [low, high]) and out['gate_rule_on_the_first'] == {}
    assert spare.spare_report(env, 'zebralogic', 'c', 'k1')['gain_interval_95_resampling_items'] == [low, high]   # seeded


def test_report_decides_nothing_while_an_item_is_missing_and_prefixes_follow_the_ranking(root, monkeypatch):
    """Review 2026-11-14: an item whose runs failed must not drop out of the judged population, and the "first N"
    reports are the first N items of the registered ranking."""
    monkeypatch.setattr(spare, 'PREFIXES', (4, 6))
    ranking = [5, 1, 7, 2, 8, 3, 6, 4]                                    # the registered order is not the sorted one
    items = [puzzle(n) for n in ranking]
    state = {'down': True}

    def answer(system, user):
        n, card = number_of(user), CARD in system
        if state['down'] and n == 5 and card:
            return None                                                   # the candidate's FIRST item fails
        return GRID if card or n not in ranking[:4] else WRONG            # the card alone solves the first four
    solver_client = Fake(answer)
    env = make_env(root, solver_client, width=1)
    cards = {'c': None, 'k1': CARD}
    allow(env, cards)
    first = run_spare(env, items, cards, runs=2)
    assert first['results'] == {'c: 0 of 2': 4, 'c: 2 of 2': 4, 'k1: 2 of 2': 7, 'k1: unknown': 1}
    out = spare.spare_report(env, 'zebralogic', 'c', 'k1')
    assert out['complete'] is False and out['reading'] == 'INCOMPLETE' and 'gate_rule' not in out
    assert out['records'] == {'base': 8, 'candidate': 7} and out['items'] == 8
    state['down'] = False
    run_spare(make_env(root, solver_client, width=1), items, cards, runs=2)
    out = spare.spare_report(env, 'zebralogic', 'c', 'k1')
    assert out['complete'] is True and out['gate_rule']['n'] == 8 and out['gate_rule']['better'] == 4
    assert out['gate_rule_on_the_first']['4']['n'] == 4 and out['gate_rule_on_the_first']['4']['better'] == 4
    assert out['gate_rule_on_the_first']['6']['better'] == 4 and out['gate_rule_on_the_first']['6']['tied'] == 2
    assert out['gate_rule_on_the_first']['4']['gain_points'] == 100.0     # the FIRST four of the ranking (5, 1, 7, 2)
    assert rejudge.registered(env, 'zebralogic', spare.KIND, 'k1')['items'] == ['zb-%03d' % n for n in ranking]
    # two configurations must share items, solver and run count
    other = [puzzle(n) for n in ranking[1:]]
    allow(env, {'c': None, 'k1': CARD, 'k2': OTHER})
    run_spare(env, other, {'k2': OTHER}, runs=2)
    with pytest.raises(AssertionError, match='differ in items'):
        spare.spare_report(env, 'zebralogic', 'c', 'k2')
    with pytest.raises(AssertionError, match='without a record'):
        spare.spare_report(env, 'zebralogic', 'c', 'k9')


def test_report_refuses_unequal_run_counts_and_mixed_records(root):
    items = [puzzle(n) for n in range(1, 4)]
    env = make_env(root, Fake(lambda s, u: GRID), width=1)
    allow(env, {'c': None, 'k1': CARD})
    run_spare(env, items, {'c': None}, runs=2)
    run_spare(env, items, {'k1': CARD}, runs=3)     # separate stages may differ in R
    with pytest.raises(AssertionError, match='run count'):
        spare.spare_report(env, 'zebralogic', 'c', 'k1')                 # ... a report of the two is refused
    allow(env, {'c': None, 'k2': OTHER})
    run_spare(env, items, {'k2': OTHER}, runs=2)
    assert spare.spare_report(env, 'zebralogic', 'c', 'k2')['complete'] is True
    path = root / 'zebralogic' / 'spare-k2' / (spare.stem('zb-002') + '.json')
    row = units.read_json(path)
    units.write_json(path, {**row, 'runs': row['runs'] + row['runs'][:1]})       # a record with a third run
    with pytest.raises(AssertionError, match='another number of runs'):
        spare.spare_report(env, 'zebralogic', 'c', 'k2')
    units.write_json(path, {**row, 'card_sha256': 'e' * 64})                      # a record of another card
    with pytest.raises(AssertionError, match='another card'):
        spare.spare_report(env, 'zebralogic', 'c', 'k2')


def test_only_the_runs_base_and_a_candidate_of_the_same_step_are_comparable():
    origin = lambda role, step='/run/G/s3', code='b': {'step_dir': step, 'role': role, 'unit': 'u',
                                                         'request_identity': {'runtime_sha256': 'a', 'code_sha256': code}}
    config = lambda role, **kw: {'items': ['1', '2'], 'solver': 'G', 'runs': 3, 'origin': origin(role), **kw}
    assert rejudge.comparable(config('base'), config('candidate')) is None
    for first, second, word in (
            (None, config('candidate'), 'without a record'),
            (config('base', origin=None), config('candidate'), 'not registered as a re-judging'),
            (config('candidate'), config('candidate'), 'not the run'),
            (config('base'), config('base'), 'not the run'),
            (config('base'), config('candidate', origin=origin('candidate', step='/run/G/s4')), 'different steps'),
            (config('base'), config('candidate', origin=origin('candidate', code='c')), 'different steps'),
            (config('base'), config('candidate', items=['1']), 'differ in items'),
            (config('base'), config('candidate', solver='D'), 'differ in items'),
            (config('base'), config('candidate', runs=2), 'differ in items'),
            (config('base', runs=1), config('candidate', runs=1), 'at least two runs'),
            (config('base', runs=None), config('candidate', runs=None), 'at least two runs')):
        assert word in rejudge.comparable(first, second), word


def test_the_reading_has_four_outcomes():
    accepted, refused = {'accepted': True}, {'accepted': False}
    assert spare.reading(accepted, [1.0, 9.0]) == 'CONFIRMED'
    assert spare.reading(refused, [1.0, 9.0]) == 'BELOW THE THRESHOLD'
    assert spare.reading(None, [0.5, 2.0]) == 'BELOW THE THRESHOLD'
    assert spare.reading(accepted, [-1.0, 9.0]) == 'NO EVIDENCE'       # an interval with 0 never confirms
    assert spare.reading(refused, [0.0, 4.0]) == 'NO EVIDENCE'
    assert spare.reading(refused, [-9.0, -1.0]) == 'HARMFUL'


# ---- parity with the run ---------------------------------------------------------------------------------------------------
def run_step(root, gate, routed, card, other=None):
    """A learning step of a finished run as the chain stores it: the noise unit (learning base, three repeats), the
    card round ``card-r1`` whose candidate ``card`` was mounted on the ``routed`` gate items only (its writer record
    holds the text), optionally a second round with ``other``, and one program-gate cell that enabled a program.
    Cells are made by the chain's own cell function on a recording call."""
    step = root / 'run' / 'G' / 's3'

    def cell(unit, item, label, mounted):
        reply = {'ok': True, 'response': json.dumps({'reasoning': 'x', 'solution': GRID}), 'finish_reason': 'stop',
                 'usage': {}, 'error_type': None}
        tag = units.cell_tag('zebralogic', item['task_id'], label)
        row = mount.solve('zebralogic', item, mounted, call=lambda s, u: reply, runtime=TOOLS['runtime'],
                          unit='s3/' + unit, tag=tag, scorer_root=None, mode='run')
        units.write_json(step / unit / 'cells' / (tag + '.json'), {**row, 'arm': label})
        return row
    rounds = [('card-r1', card)] + ([('card-r2', other)] if other else [])
    for unit, text in rounds:
        units.write_json(step / unit / 'writer.json', {'text': text})
    for item in gate:
        base = mount.mount('zebralogic', item, arm='C', typemap=None, library=None, vector=None)
        for label in ('B#1', 'B#2', 'B#3'):
            cell('noise', item, label, base)
        for unit, text in rounds:
            mounted = spare.forced_mount(mount, 'zebralogic', item, text, TOOLS['runtime']) if item in routed else base
            cell(unit, item, 'cand_card#1', mounted)
    with_program = cell('program-1-gate', gate[0], 'cand_program#1',
                        spare.forced_mount(mount, 'zebralogic', gate[0], card, TOOLS['runtime']))
    path = step / 'program-1-gate' / 'cells' / (units.cell_tag('zebralogic', gate[0]['task_id'], 'cand_program#1') + '.json')
    units.write_json(path, {**with_program, 'mount': {**with_program['mount'], 'enabled': [{'id': 'p'}]},
                            'request_sha256': ['d' * 64]})                # a program changes the request: never compared
    return step


def parity_of(env, gate, cards, step, tools=TOOLS, identity=IDENT):
    return spare.stage_parity(env, tools, 'zebralogic', gate, cards, step, identity)


def test_parity_compares_every_configuration_with_its_own_source_in_the_run(root):
    gate = [puzzle(n) for n in range(1, 6)]
    step = run_step(root, gate, gate[:4], CARD)
    env = make_env(root, Fake(lambda s, u: GRID))
    out = parity_of(env, gate, {'c': None, 'k1': CARD}, step)
    assert out['ok'] is True and env.read('zebralogic', 'spare-parity.json') == out
    assert out['step_dir'] == str(step.absolute()) and out['request_identity'] == IDENT
    assert out['configurations']['c'] == {
        'card_sha256': units.sha256_text(zebralogic.CARD_TEXT), 'gate_items': 5, 'same_request': 5, 'different': 0,
        'no_run_cell_with_this_card': 0, 'source': {'role': 'base', 'unit': 'noise', 'arms': ['B', 'F']}}
    k1 = out['configurations']['k1']
    assert (k1['same_request'], k1['different'], k1['no_run_cell_with_this_card']) == (4, 0, 1)    # the run routed 4 of 5
    assert k1['source'] == {'role': 'candidate', 'unit': 'card-r1', 'arms': ['cand_card']}
    assert env.clients['solver'].calls == [] and not (root / 'ledger.json').exists()               # nothing was sent
    done = run_spare(env, [puzzle(9)], {'c': None, 'k1': CARD}, runs=2)                             # now it may run
    assert done['results'] == {'c: 2 of 2': 1, 'k1: 2 of 2': 1}
    origin = rejudge.registered(env, 'zebralogic', spare.KIND, 'k1')['origin']
    assert origin == {'step_dir': str(step.absolute()), 'request_identity': IDENT, 'role': 'candidate', 'unit': 'card-r1'}
    assert rejudge.registered(env, 'zebralogic', spare.KIND, 'c')['origin']['role'] == 'base'
    # the stripped text is no round's text: it has no source, the check fails and the stage is refused
    out = parity_of(env, gate, {'c': None, 'k1': CARD.strip()}, step)
    assert out['ok'] is False and out['configurations']['k1']['source'] is None
    assert out['configurations']['k1']['error'] == 'no card round of the step wrote this text'
    with pytest.raises(AssertionError, match='differs from the run'):
        run_spare(env, [puzzle(9)], {'c': None, 'k1': CARD.strip()}, runs=2)
    with pytest.raises(AssertionError, match='base "c"'):
        parity_of(env, gate, {'k1': CARD}, step)


def test_a_request_built_differently_fails_the_parity_and_a_stale_record_authorizes_nothing(root):
    """Review 2026-11-14 (second round): a parity record made with another runtime or code, or for another learning
    step, must not let a stage run; a runtime that changes the request is seen by the check."""
    gate = [puzzle(n) for n in range(1, 4)]
    step = run_step(root, gate, gate, CARD)
    solver_client = Fake(lambda s, u: GRID)
    env = make_env(root, solver_client)
    cards = {'c': None, 'k1': CARD}
    other_tools = {**TOOLS, 'runtime': {'zebralogic': {'v222_whole_card_fallback': True}}}
    assert spare.first_request(other_tools, 'zebralogic', gate[0], None) != spare.first_request(TOOLS, 'zebralogic', gate[0], None)
    changed = parity_of(env, gate, cards, step, tools=other_tools,
                        identity=rejudge.request_identity(other_tools['runtime'], {'code': 'fixture'}))
    assert changed['ok'] is False
    assert changed['configurations']['c']['different'] == 3 and changed['configurations']['c']['same_request'] == 0
    assert changed['configurations']['k1']['different'] == 3
    assert parity_of(env, gate, cards, step)['ok'] is True               # the run's own runtime: the same requests
    spare_item = [puzzle(9)]
    for kwargs, word in (
            ({'identity': rejudge.request_identity(other_tools['runtime'], {'code': 'fixture'})}, 'another runtime or code'),
            ({'identity': rejudge.request_identity(TOOLS['runtime'], {'code': 'another snapshot'})}, 'another runtime or code')):
        with pytest.raises(AssertionError, match=word):
            spare.stage_spare(env, TOOLS, 'zebralogic', spare_item, cards, step_dir=step, runs=2, **kwargs)
    elsewhere = root / 'run' / 'G' / 's4'
    elsewhere.mkdir()
    with pytest.raises(AssertionError, match='another learning step'):
        spare.stage_spare(env, TOOLS, 'zebralogic', spare_item, cards, step_dir=elsewhere, identity=IDENT, runs=2)
    assert solver_client.calls == [] and not list((root / 'zebralogic').glob('spare-c*'))   # nothing sent or registered


def test_the_base_is_certified_by_the_runs_base_cells_only(root):
    """Review 2026-11-14 (second round): the candidate of one card round must not pass as the base of a comparison
    with another round's candidate; a report compares the run's base with a candidate, nothing else."""
    gate = [puzzle(n) for n in range(1, 4)]
    step = run_step(root, gate, gate, CARD, other=OTHER)
    env = make_env(root, Fake(lambda s, u: GRID), width=1)
    # every round's text finds its own round; the hand card finds the noise unit
    out = parity_of(env, gate, {'c': None, 'k1': CARD, 'k2': OTHER}, step)
    assert out['ok'] is True
    assert [out['configurations'][n]['source']['unit'] for n in ('c', 'k1', 'k2')] == ['noise', 'card-r1', 'card-r2']
    # each source is read alone: a candidate's cells never certify a base, the base's cells never a candidate
    base, cand = rejudge.base_source('noise'), rejudge.candidate_source(step, CARD)
    card_sha = units.sha256_text(mount.system_card('zebralogic', CARD, base_card='historical'))
    hand_sha = units.sha256_text(zebralogic.CARD_TEXT)
    assert {sha for _, sha in rejudge.run_cell_index(step, base)} == {hand_sha}
    assert {sha for _, sha in rejudge.run_cell_index(step, cand)} == {card_sha}
    assert rejudge.candidate_source(step, CARD + ' ') is None and rejudge.candidate_source(step, OTHER)['unit'] == 'card-r2'
    as_base = rejudge.check_parity(env, 'zebralogic', spare.KIND, step, IDENT, gate, {
        'k1': (card_sha, rejudge.base_source('noise'), lambda item: spare.first_request(TOOLS, 'zebralogic', item, CARD))})
    assert as_base['ok'] is False and as_base['configurations']['k1']['same_request'] == 0   # no base cell sent this card
    for unit in ('card-r1', 'Noise', '../noise'):
        with pytest.raises(AssertionError):
            rejudge.base_source(unit)
    # two candidates and no base, or two bases: no passing record
    pair = {'k1': (card_sha, cand, lambda item: spare.first_request(TOOLS, 'zebralogic', item, CARD))}
    assert rejudge.check_parity(env, 'zebralogic', spare.KIND, step, IDENT, gate, pair)['ok'] is False
    # a report between two candidates is refused
    parity_of(env, gate, {'c': None, 'k1': CARD, 'k2': OTHER}, step)
    spare.stage_spare(env, TOOLS, 'zebralogic', [puzzle(9), puzzle(10)], {'c': None, 'k1': CARD, 'k2': OTHER},
                      step_dir=step, identity=IDENT, runs=2)
    assert spare.spare_report(env, 'zebralogic', 'c', 'k2')['origin'] == {
        'step_dir': str(step.absolute()), 'base_unit': 'noise', 'candidate_unit': 'card-r2'}
    for base_name, cand_name in (('k1', 'k2'), ('k1', 'c'), ('c', 'c')):
        with pytest.raises(AssertionError, match='No report'):
            spare.spare_report(env, 'zebralogic', base_name, cand_name)


def test_the_run_cell_index_reads_one_unit_of_one_learning_step_and_skips_program_cells(root):
    gate = [puzzle(1), puzzle(2)]
    step = run_step(root, gate, gate, CARD)
    card_sha = units.sha256_text(mount.system_card('zebralogic', CARD, base_card='historical'))
    index = rejudge.run_cell_index(step, rejudge.candidate_source(step, CARD))
    assert set(index) == {(item['task_id'], card_sha) for item in gate}
    assert all(len(requests) == 1 for requests in index.values())
    noise = rejudge.run_cell_index(step, rejudge.base_source('noise'))
    assert all(len(requests) == 1 for requests in noise.values()) and len(noise) == 2     # three repeats, one request
    program = rejudge.run_cell_index(step, {'role': 'candidate', 'unit': 'program-1-gate', 'arms': ['cand_program']})
    assert program == {}                                                  # a cell that enabled a program is skipped
    # a cell of another arm inside the base unit (sent with the candidate's card) is not a base cell
    stray = units.read_json(next((step / 'card-r1' / 'cells').glob('*.json')))
    units.write_json(step / 'noise' / 'cells' / ('0' * 64 + '.json'), stray)
    assert {sha for _, sha in rejudge.run_cell_index(step, rejudge.base_source('noise'))} == {units.sha256_text(zebralogic.CARD_TEXT)}
    assert card_sha in {sha for _, sha in rejudge.run_cell_index(step, {'role': 'x', 'unit': 'noise', 'arms': ['cand_card']})}
    assert rejudge.run_cell_index(step, rejudge.base_source('outcomes')) == {}            # a unit the step has not
    for bad in (step.parent, step / 'noise', root):
        with pytest.raises(AssertionError, match='learning step directory'):
            rejudge.run_cell_index(bad, rejudge.base_source('noise'))
    same = rejudge.parity(index, gate, card_sha, lambda item: spare.first_request(TOOLS, 'zebralogic', item, CARD))
    assert same['same_request'] == 2 and same['different'] == 0
    wrong = rejudge.parity(index, gate, card_sha, lambda item: 'f' * 64)
    assert wrong['different'] == 2 and wrong['same_request'] == 0
    env = make_env(root, None)
    assert rejudge.check_parity(env, 'zebralogic', spare.KIND, step, IDENT, gate, {})['ok'] is False


def test_first_request_is_the_request_a_cell_sends_and_costs_nothing(root):
    item = puzzle(3)
    seen = []

    def recording(system, user):
        seen.append(units.sha256_text(system + '\x00' + user))
        return {'ok': True, 'response': json.dumps({'reasoning': 'x', 'solution': GRID}), 'finish_reason': 'stop',
                'usage': {}, 'error_type': None}
    mount.solve('zebralogic', item, spare.forced_mount(mount, 'zebralogic', item, None, TOOLS['runtime']),
                call=recording, runtime=TOOLS['runtime'], unit='u', tag='t', scorer_root=None, mode='run')
    assert spare.first_request(TOOLS, 'zebralogic', item, None) == seen[0]
    assert spare.first_request(TOOLS, 'zebralogic', item, CARD) != seen[0]
    assert spare.first_request(TOOLS, 'zebralogic', item, CARD) != spare.first_request(TOOLS, 'zebralogic', item, CARD.strip())
