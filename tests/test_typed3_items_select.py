"""typed-v3 item stage tools, section 4 (brief P2a): the SearchQA selector (one scripted selector call per batch of 25
candidates), the ALFWorld selection by task type, and the registry entries of the benches without a maker. Fakes
only; expected values are computed in the tests from the rules, not read from the code."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill.typed import SEED, chain as chain_, items as items_, units
from skillopt.execskill.typed.items import plan as plan_, select_items, store as store_

IDENTITY = {'version': 'typed-v3', 'chain': 'D', 'step': 1, 'round': 1}
TOPICS = ('date', 'person', 'place', 'number')
QUESTION = {'date': 'In what year did event %d happen?', 'person': 'Who wrote book %d?',
            'place': 'Where is landmark %d?', 'number': 'How many parts has machine %d?'}


@pytest.fixture
def root():
    base = Path('/tmp/typed3-items-neutral')
    base.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='select-', dir=base))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def receipt(text, *, ok=True, error=None):
    return {'ok': ok, 'response': text if ok else None, 'finish_reason': 'stop' if ok else None,
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}, 'error_type': error}


# ---- SearchQA ------------------------------------------------------------------------------------------------------
def sq_item(i, topic=None):
    topic = topic or TOPICS[i % 4]
    return {'benchmark': 'searchqa', 'task_id': 'sq-%02d' % i, 'family_id': 'exact-%02d' % i, 'part': 'pool',
            'public': {'question': QUESTION[topic] % i, 'context': 'Snippet on item %d: some text.' % i},
            'private': {'answers': ['ANSWER-%02d' % i]}}


POOL = [sq_item(i) for i in range(80)]
POOL[50]['family_id'] = 'exact-05'            # the same question as the learn item sq-05: a near duplicate
LEARN, GATE = ['sq-%02d' % i for i in range(10)], ['sq-%02d' % i for i in range(10, 20)]
OUTCOMES = {i: [True, False, False] for i in LEARN}
PLAN = {'weaknesses': [{'id': 'w1', 'given_id': 'dates', 'description': 'Questions that ask for a year (dates).',
                        'evidence': [], 'signature': '', 'spec': {}},
                       {'id': 'w2', 'given_id': 'who', 'description': 'Questions that ask who (people).',
                        'evidence': [], 'signature': '', 'spec': {}},
                       {'id': 'w3', 'given_id': 'where', 'description': 'Questions that ask where (places).',
                        'evidence': [], 'signature': '', 'spec': {}}],
        'guards': [{'id': 'g1', 'description': 'Questions that ask how many (counts).', 'spec': {}}],
        'note': '', 'unreadable': False}
QUOTAS = {'searchqa': {'judging': {'attack': 6, 'guard': 3, 'calibration': 3}, 'shown': {'attack': 3, 'guard': 2}}}
KEYWORD = {'year': 'dates', 'who': 'people', 'where': 'places', 'how many': 'counts'}


class Selector:
    """A scripted selector: for each candidate the description whose words name the candidate's question kind.
    ``bad``: {tag: [replies]} scripted per batch tag instead; every request is kept."""

    def __init__(self, bad=None, skip=()):
        self.bad, self.skip, self.requests, self.tags = dict(bad or {}), set(skip), [], []

    def __call__(self, tag):
        self.tags.append(tag)

        def call(system, user):
            self.requests.append((tag, system, user))
            if self.bad.get(tag):
                reply = self.bad[tag].pop(0)
                return reply if isinstance(reply, dict) else receipt(reply)
            request = json.loads(user.split('\n\nFormat retry')[0])
            by_word = {}
            for row in request['descriptions']:
                for word, kind in KEYWORD.items():
                    if kind in row['description']:
                        by_word[word] = row['id']
            matches = {}
            for row in request['candidates']:
                question = row['text'].split('\n')[0].lower()
                found = [by_word[word] for word in KEYWORD if word in question and word in by_word]
                matches[row['label']] = None if any(s in row['text'] for s in self.skip) else (found[0] if found else None)
            return receipt('Matches:\n```json\n' + json.dumps({'matches': matches}) + '\n```')
        return call


def sq_input(folder, selector, *, plan=PLAN, quotas=QUOTAS, registry=None, identity=IDENTITY, kept=None):
    kept = [w['id'] for w in plan['weaknesses']] if kept is None else kept
    return items_.MakeInput(bench='searchqa', plan=plan, counts=items_.counts('searchqa', kept, quotas), pool=POOL,
                            pool_pin={'path': '/p/searchqa.json', 'sha256': 'b' * 64}, learn_ids=LEARN, gate_ids=GATE,
                            outcomes=OUTCOMES, repeats=3, identity=identity,
                            registry=registry if registry is not None else store_.RunRegistry(),
                            store=store_.ItemStore(folder), role_call=selector)


def ranked_ids(ids, tag):
    """The seeded draw order of ``coevo5.data.ranked``, written out: sha256 of [seed, tag, id]."""
    return sorted(ids, key=lambda i: hashlib.sha256(json.dumps([SEED, tag, i]).encode()).hexdigest())


def picks(found):
    return [(r['side'], r['class'], r['weakness'], r['item']) for r in found['records']]


def test_the_searchqa_selection_by_hand(root):
    selector = Selector()
    found = select_items.SearchQASelector().make(sq_input(root / 'u', selector))
    # candidates: sq-20 .. sq-79 without sq-50 (the family of learn item sq-05): 59, in batches of 25, 25, 9
    assert found['record']['candidates'] == 59
    assert found['record']['excluded'] == {'learn_or_gate': 20, 'family_of_learn_or_gate': 1, 'selected_before': 0,
                                           'family_selected_before': 0}
    assert selector.tags == ['selector-01', 'selector-02', 'selector-03'] and len(selector.requests) == 3
    assert [b['candidates'] for b in found['record']['batches']] == [25, 25, 9]
    # topics cycle date, person, place, number from sq-20: weaknesses in the pool's order, judging (2 each), then
    # shown (1 each); guards (counts) 3 judging, then 2 shown
    expected = [('judging', 'attack', 'w1', 'sq-20'), ('judging', 'attack', 'w1', 'sq-24'),
                ('judging', 'attack', 'w2', 'sq-21'), ('judging', 'attack', 'w2', 'sq-25'),
                ('judging', 'attack', 'w3', 'sq-22'), ('judging', 'attack', 'w3', 'sq-26'),
                ('judging', 'guard', None, 'sq-23'), ('judging', 'guard', None, 'sq-27'),
                ('judging', 'guard', None, 'sq-31')]
    assert picks(found)[:9] == expected
    chosen = {row[3] for row in expected} | {'sq-28', 'sq-29', 'sq-30', 'sq-35', 'sq-39'}
    tag = select_items.DRAW_TAG % ('searchqa', 'typed-v3:D:s1:r1')
    remaining = [i for i in ranked_ids(['sq-%02d' % i for i in range(20, 80) if i != 50], tag) if i not in chosen]
    assert picks(found)[9:12] == [('judging', 'calibration', None, i) for i in remaining[:3]]
    assert picks(found)[12:] == [('shown', 'attack', 'w1', 'sq-28'), ('shown', 'attack', 'w2', 'sq-29'),
                                 ('shown', 'attack', 'w3', 'sq-30'), ('shown', 'guard', None, 'sq-35'),
                                 ('shown', 'guard', None, 'sq-39')]
    assert found['shortfalls'] == [] and found['made_counts']['judging'] == {'attack': 6, 'guard': 3, 'calibration': 3}
    store = store_.ItemStore(root / 'u')
    for row, record in zip(found['slots'], found['records']):
        item = store.item(row['slot'])
        assert item == POOL[int(record['item'][3:])]                          # the real item, its real reference
        assert record['source'] == 'selected' and record['certificate'] is None
        assert record['family'] == item['family_id'] and record['item_sha256'] == items_.item_sha256('searchqa', item)
    assert [row['slot'] for row in found['slots']][:3] == ['judging-attack-w1-001', 'judging-attack-w1-002',
                                                           'judging-attack-w2-001']
    sides = {}
    for record in found['records']:
        sides.setdefault(record['family'], set()).add(record['side'])
    assert all(len(value) == 1 for value in sides.values()) and len({r['item'] for r in found['records']}) == 17


def test_the_selector_sees_public_text_only_and_opaque_ids(root):
    selector = Selector()
    select_items.SearchQASelector().make(sq_input(root / 'u', selector))
    text = ''.join(system + user for _, system, user in selector.requests)
    assert 'ANSWER' not in text and 'sq-' not in text and 'exact-' not in text      # no reference, no id, no family
    for i in list(range(0, 20)) + [50]:
        assert 'event %d happen' % i not in text and 'item %d:' % i not in text   # no learn or gate item
    request = json.loads(selector.requests[0][2])
    assert [row['id'] for row in request['descriptions']] == ['d1', 'd2', 'd3', 'd4']
    assert request['candidates'][0] == {'label': 'c01', 'text': plan_.public_text_of('searchqa', POOL[20])}
    assert selector.requests[0][1] == select_items.SELECTOR_SYSTEM


def test_shortfalls_go_to_calibration_on_the_judging_side(root):
    # the scripted selector finds no 'places' question except sq-22: w3 is one short on the judging side and short on
    # the shown side; the judging calibration takes the missing one
    skip = ['landmark %d?' % i for i in range(26, 80, 4)]
    found = select_items.SearchQASelector().make(sq_input(root / 'u', Selector(skip=skip)))
    assert found['shortfalls'] == [
        {'side': 'judging', 'class': 'attack', 'weakness': 'w3', 'missing': 1, 'filled_by': 'calibration'},
        {'side': 'shown', 'class': 'attack', 'weakness': 'w3', 'missing': 1, 'filled_by': None}]
    assert found['made_counts']['judging'] == {'attack': 5, 'guard': 3, 'calibration': 4}
    assert found['made_counts']['shown'] == {'attack': 2, 'guard': 2, 'calibration': 0}
    assert found['record']['calibration_wanted'] == 4


def test_without_kept_weaknesses_the_attack_items_are_drawn_like_calibration(root):
    plan = {**PLAN, 'weaknesses': []}
    found = select_items.SearchQASelector().make(sq_input(root / 'u', Selector(), plan=plan))
    # 20 % rule: judging 12 -> attack 2, guard 3, calibration 7; shown 5 -> attack 1, guard 4; only the guard is matched
    counts = items_.counts('searchqa', [], QUOTAS)
    assert (counts['judging'], counts['shown']) == ({'attack': 2, 'guard': 3, 'calibration': 7}, {'attack': 1, 'guard': 4})
    tag = select_items.DRAW_TAG % ('searchqa', 'typed-v3:D:s1:r1')
    guards = ['sq-23', 'sq-27', 'sq-31', 'sq-35', 'sq-39', 'sq-43', 'sq-47']
    order = [i for i in ranked_ids(['sq-%02d' % i for i in range(20, 80) if i != 50], tag) if i not in guards]
    assert picks(found) == ([('judging', 'attack', None, i) for i in order[:2]]
                            + [('judging', 'guard', None, i) for i in guards[:3]]
                            + [('judging', 'calibration', None, i) for i in order[3:10]]
                            + [('shown', 'attack', None, order[2])]
                            + [('shown', 'guard', None, i) for i in guards[3:7]])
    assert found['record']['descriptions'] == ['g1']                       # only the guard is matched


def test_an_item_is_selected_once_per_run(root):
    first = select_items.SearchQASelector().make(sq_input(root / 'a', Selector()))
    registry = store_.RunRegistry(first['records'])
    twin = sq_item(80, 'date')
    twin['family_id'] = 'exact-20'                       # another id, the question of the selected sq-20
    pool = POOL + [twin]
    inp = sq_input(root / 'b', Selector(), registry=registry, identity={**IDENTITY, 'round': 2})
    inp.pool = pool
    second = select_items.SearchQASelector().make(inp)
    assert not {r['item'] for r in second['records']} & {r['item'] for r in first['records']}
    assert second['record']['excluded']['selected_before'] == 17
    assert second['record']['excluded']['family_selected_before'] == 1 and 'sq-80' not in {r['item'] for r in second['records']}
    assert registry.ids >= {r['item'] for r in first['records'] + second['records']}


def test_an_unreadable_batch_selects_nothing_after_one_retry(root):
    selector = Selector(bad={'selector-01': ['I would match them by topic.', '{"matches": "all of them"}']})
    found = select_items.SearchQASelector().make(sq_input(root / 'u', selector))
    batch = json.loads((root / 'u' / 'selector' / 'batch-01.json').read_text())
    assert batch['readable'] is False and all(value is None for value in batch['matches'].values())
    assert [a['reply'] for a in batch['attempts']] == ['I would match them by topic.', '{"matches": "all of them"}']
    assert [tag for tag, _, _ in selector.requests] == ['selector-01', 'selector-01', 'selector-02', 'selector-03']
    first, retry = selector.requests[0][2], selector.requests[1][2]
    assert retry == first + select_items.SELECTOR_RETRY
    assert found['record']['batches'][0] == {'batch': 1, 'candidates': 25, 'readable': False, 'matched': 0, 'calls': 2}
    # batch 1 held sq-20 .. sq-44: the date questions of w1 come from the later batches (sq-48, sq-52)
    assert [r['item'] for r in found['records'] if r['class'] == 'attack' and r['side'] == 'judging'][:2] == ['sq-48', 'sq-52']
    # a retry that is read: the batch is readable with two calls; a key that is no candidate label is named
    selector = Selector(bad={'selector-01': ['prose', json.dumps({'matches': {'c01': 'd1', 'c99': 'd1', 'c02': None}})]})
    select_items.SearchQASelector().make(sq_input(root / 'v', selector))
    batch = json.loads((root / 'v' / 'selector' / 'batch-01.json').read_text())
    assert batch['readable'] and batch['matches']['sq-20'] == 'w1' and batch['matches']['sq-21'] is None
    assert batch['unknown_labels'] == ['c99'] and 'unknown_ids' not in batch


@pytest.mark.parametrize('value', [[], ['d1'], {'id': 'd1'}, {}, 1, True, 'd9', 'w1', ''])
def test_a_reply_with_a_value_of_another_shape_is_unreadable(root, value):
    # review P2a finding 2: every value is null or one of the batch's description ids, else the reply is unreadable:
    # the one format retry, then the batch is recorded as unreadable and selects nothing
    bad = json.dumps({'matches': {'c01': value, 'c02': 'd2'}})
    assert select_items.read_matches(bad, {'d1': 'w1', 'd2': 'w2'}) is None
    selector = Selector(bad={'selector-01': [bad, bad]})
    found = select_items.SearchQASelector().make(sq_input(root / 'u', selector))
    batch = json.loads((root / 'u' / 'selector' / 'batch-01.json').read_text())
    assert batch['readable'] is False and all(match is None for match in batch['matches'].values())
    assert [a['readable'] for a in batch['attempts']] == [False, False] and [a['reply'] for a in batch['attempts']] == [bad, bad]
    assert [tag for tag, _, _ in selector.requests] == ['selector-01', 'selector-01', 'selector-02', 'selector-03']
    batch_one = {'sq-%02d' % i for i in range(20, 45)}      # the candidates of batch 1: none of them is matched
    assert not {r['item'] for r in found['records'] if r['class'] in ('attack', 'guard')} & batch_one
    # the same value on the first attempt and a good retry: the batch is read from the retry
    selector = Selector(bad={'selector-01': [bad, json.dumps({'matches': {'c01': 'd1', 'c02': None}})]})
    select_items.SearchQASelector().make(sq_input(root / 'v', selector))
    batch = json.loads((root / 'v' / 'selector' / 'batch-01.json').read_text())
    assert batch['readable'] and [a['readable'] for a in batch['attempts']] == [False, True]
    assert batch['matches']['sq-20'] == 'w1' and batch['matches']['sq-21'] is None


def test_an_infrastructure_failure_raises_and_the_rerun_sends_only_what_is_missing(root):
    selector = Selector(bad={'selector-02': [receipt(None, ok=False, error='http_502')]})
    with pytest.raises(items_.RoleUnavailable) as caught:
        select_items.SearchQASelector().make(sq_input(root / 'u', selector))
    assert caught.value.tag == 'selector-02' and caught.value.failure == 'infrastructure:http_502'
    assert (root / 'u' / 'selector' / 'batch-01.json').exists() and not (root / 'u' / 'selector' / 'batch-02.json').exists()
    assert not (root / 'u' / select_items.SELECTION).exists()
    again = Selector()
    resumed = select_items.SearchQASelector().make(sq_input(root / 'u', again))
    assert again.tags == ['selector-02', 'selector-03']                        # batch 1 is not sent again
    whole = select_items.SearchQASelector().make(sq_input(root / 'w', Selector()))
    assert picks(resumed) == picks(whole)


class Killed(Exception):
    """The process killed at a chosen point (the unit is resumed by running it again)."""


class Client:
    """The role client behind real call recorders: the scripted selector's reply on the first send of a request and
    all-null matches on any later send of the same request, so a second send would change the selection."""

    def __init__(self):
        self.users, self.seen = [], {}

    def __call__(self, system, user):
        self.users.append(user)
        key = units.sha256_text(system + '\x00' + user)
        self.seen[key] = self.seen.get(key, 0) + 1
        if self.seen[key] > 1:
            request = json.loads(user.split('\n\nFormat retry')[0])
            return receipt(json.dumps({'matches': {row['label']: None for row in request['candidates']}}))
        return Selector()('any')(system, user)


def recorders(folder, ledger, client, *, refill=True):
    """``Services.role_call`` as P2b wires it: a ``units.CallRecorder`` per batch tag over the role client, writing its
    sends to the unit's calls file, refilled from that file on resume by the chain's ``_keep_earlier_sends``."""
    def role_call(tag):
        call = units.CallRecorder(client, ledger, max_tokens=32_768, tag=tag, unit='s1/items',
                                  out_path=folder / 'calls' / ('%s-item_selector.json' % tag))
        return chain_._keep_earlier_sends(call) if refill else call
    return role_call


def test_a_batch_answered_before_a_kill_is_not_sent_again(root, monkeypatch):
    # review P2a finding 3: the recorder writes the receipt of a batch before the batch record is written; a kill in
    # between must not make the resumed unit send the batch again (one batch: the 25 candidates sq-20 .. sq-44)
    pool = POOL[:45]
    real_ask = select_items.SearchQASelector.ask

    def killed_after_the_call(self, inp, number, *args):
        real_ask(self, inp, number, *args)
        raise Killed()                                 # the receipt is in the calls file, the batch record is not
    whole_inp = sq_input(root / 'w', recorders(root / 'w', units.Ledger(None, 10 ** 9), Client()))
    whole_inp.pool = pool
    whole = select_items.SearchQASelector().make(whole_inp)
    for folder, refill in (('u', True), ('x', False)):
        ledger, client = units.Ledger(None, 10 ** 9), Client()
        monkeypatch.setattr(select_items.SearchQASelector, 'ask', killed_after_the_call)
        inp = sq_input(root / folder, recorders(root / folder, ledger, client))
        inp.pool = pool
        with pytest.raises(Killed):
            select_items.SearchQASelector().make(inp)
        assert not (root / folder / 'selector' / 'batch-01.json').exists()
        sends = json.loads((root / folder / 'calls' / 'selector-01-item_selector.json').read_text())
        assert len(sends) == 1 and sends[0]['receipt']['ok'] is True and len(client.users) == 1
        monkeypatch.setattr(select_items.SearchQASelector, 'ask', real_ask)
        inp = sq_input(root / folder, recorders(root / folder, ledger, client, refill=refill))
        inp.pool = pool
        resumed = select_items.SearchQASelector().make(inp)
        if refill:      # zero new sends, nothing charged again, the selection of an uninterrupted run
            assert len(client.users) == 1 and ledger.state['sends'] == 1
            assert picks(resumed) == picks(whole) and resumed == whole
            assert {k: v for k, v in files(root / 'u').items() if not k.startswith('calls')} == {
                k: v for k, v in files(root / 'w').items() if not k.startswith('calls')}
        else:           # a recorder that is not refilled sends again, and the second reply changes the selection
            assert len(client.users) == 2 and picks(resumed) != picks(whole)


def files(folder):
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(Path(folder).rglob('*.json'))}


def test_the_selection_is_written_once_and_reproducible(root):
    first = select_items.SearchQASelector().make(sq_input(root / 'a', Selector()))
    second = select_items.SearchQASelector().make(sq_input(root / 'b', Selector()))
    assert first == second and files(root / 'a') == files(root / 'b')
    selector = Selector()
    again = select_items.SearchQASelector().make(sq_input(root / 'a', selector))     # the same unit run again
    assert again == first and selector.tags == [] and files(root / 'a') == files(root / 'b')
    # a stored batch of another request is refused (the plan changed under a finished batch)
    other = {**PLAN, 'weaknesses': [{**PLAN['weaknesses'][0], 'description': 'Questions about years.'}] + PLAN['weaknesses'][1:]}
    with pytest.raises(ValueError):
        select_items.SearchQASelector().make(sq_input(root / 'a', Selector(), plan=other))


# ---- ALFWorld ------------------------------------------------------------------------------------------------------
TYPES = select_items.TYPES          # pick_and_place, look_at, clean, heat, cool, two


def game(i, kind, room, *, view=True):
    path = 'json_2.1.1/train/%s-Mug-None-Shelf-%d/trial_T2019_%03d/game.tw-pddl' % (kind, room, i)
    public = {'game_file': path}
    if view:
        observation = 'You are in room %d. Your task is to: do game %d.' % (room, i)
        public.update(routing_view={'initial_observation': observation, 'admissible_commands_at_reset': ['look'],
                                    'task_text': 'do game %d' % i}, routing_view_sha256=hashlib.sha256(observation.encode()).hexdigest())
    return {'benchmark': 'alfworld', 'task_id': 'alfworld-xs:%04d' % i, 'family_id': 'alfworld-xs:%04d' % i,
            'part': 'pool', 'room': str(room), 'task_type': kind, 'public': public, 'private': {'game_metadata': {}}}


def alf_pool():
    games, i = [], 0
    for room in range(1, 13):                          # 12 rooms, one game of each type in each room: 72 games
        for kind in TYPES:
            games.append(game(i, kind, room))
            i += 1
    games.append(game(i, TYPES[0], 13, view=False))    # no registered routing view
    bad = game(i + 1, TYPES[1], 13)
    bad['public']['game_file'] = 'alf-smoke-fixture://1'
    games.append(bad)                                  # no task folder: no task type
    return games


ALF = alf_pool()
ALF_BY = {g['task_id']: g for g in ALF}
# learn: rooms 1 and 2 (12 games); gate: rooms 3 to 5 restricted to heat x3, cool x2, clean x1
ALF_LEARN = [g['task_id'] for g in ALF if g['room'] in ('1', '2')]
ALF_GATE = ([g['task_id'] for g in ALF if g['task_type'] == TYPES[3] and g['room'] in ('3', '4', '5')]
            + [g['task_id'] for g in ALF if g['task_type'] == TYPES[4] and g['room'] in ('3', '4')]
            + [g['task_id'] for g in ALF if g['task_type'] == TYPES[2] and g['room'] == '3'])
# B won every run of pick_and_place and look_at; mixed elsewhere
ALF_OUTCOMES = {i: ([True] * 3 if ALF_BY[i]['task_type'] in TYPES[:2] else [True, False, False]) for i in ALF_LEARN}


def alf_input(folder, plan, quotas, *, registry=None, identity=IDENTITY):
    kept = [w['id'] for w in plan['weaknesses']]
    return items_.MakeInput(bench='alfworld', plan=plan, counts=items_.counts('alfworld', kept, quotas), pool=ALF,
                            pool_pin={'path': '/p/alfworld.json', 'sha256': 'c' * 64}, learn_ids=ALF_LEARN,
                            gate_ids=ALF_GATE, outcomes=ALF_OUTCOMES, repeats=3, identity=identity,
                            registry=registry if registry is not None else store_.RunRegistry(),
                            store=store_.ItemStore(folder))


def alf_plan(*types):
    return {'weaknesses': [{'id': 'w%d' % n, 'given_id': None, 'description': 'd', 'evidence': [], 'signature': '',
                            'spec': {'task_types': list(kinds)} if kinds else {}} for n, kinds in enumerate(types, 1)],
            'guards': [], 'note': '', 'unreadable': False}


def alf_quotas(a, g, k, sa, sg):
    return {'alfworld': {'judging': {'attack': a, 'guard': g, 'calibration': k}, 'shown': {'attack': sa, 'guard': sg}}}


def test_alfworld_task_types_come_from_the_games_own_file():
    assert select_items.game_type(ALF[0]) == (TYPES[0], '1')
    assert select_items.ALFWorldSelector().public_kind(ALF[9]) == {'task_type': TYPES[3]}
    with pytest.raises(ValueError):
        select_items.game_type({**ALF[0], 'task_type': TYPES[1]})        # the item and its game file disagree
    assert select_items.ALFWorldSelector().public_kind(ALF[-1]) == {}
    sheet = select_items.ALFWorldSelector().capability_sheet()
    assert sheet['fields']['task_types']['values'] == list(TYPES) and set(sheet['fields']['task_types']['types']) == set(TYPES)
    assert select_items.type_guards([ALF_BY[i] for i in ALF_LEARN], ALF_OUTCOMES, 3) == (list(TYPES[:2]), 'all_right')
    # review P2a finding 1: no fallback for ALFWorld. Nobody won every run of a type: no guard type at all, however
    # high a pass rate is (cool and two at 2 of 3 runs here)
    mixed = {i: [True, True, False] if ALF_BY[i]['task_type'] in (TYPES[4], TYPES[5]) else [True, False, False]
             for i in ALF_LEARN}
    assert select_items.type_guards([ALF_BY[i] for i in ALF_LEARN], mixed, 3) == ([], 'none_all_right')
    # one type of two games won in every run, the other games of that type too: exactly that type
    mixed.update({i: [True, True, True] for i in ALF_LEARN if ALF_BY[i]['task_type'] == TYPES[2]})
    assert select_items.type_guards([ALF_BY[i] for i in ALF_LEARN], mixed, 3) == ([TYPES[2]], 'all_right')
    # one of its two games lost once: the type no longer qualifies
    clean = [i for i in ALF_LEARN if ALF_BY[i]['task_type'] == TYPES[2]]
    mixed[clean[1]] = [True, True, False]
    assert select_items.type_guards([ALF_BY[i] for i in ALF_LEARN], mixed, 3) == ([], 'none_all_right')


def test_the_alfworld_selection_by_type(root):
    plan = alf_plan([TYPES[3]], [TYPES[4], TYPES[5]], [])       # heat; cool or two; every type
    found = select_items.ALFWorldSelector().make(alf_input(root / 'u', plan, alf_quotas(6, 4, 6, 3, 2)))
    assert found['record']['candidates'] == 72 - 12 - 6 and found['record']['excluded'] == {
        'learn_or_gate': 18, 'no_routing_view': 1, 'no_task_type': 1, 'selected_before': 0}
    by_class = {}
    for record in found['records']:
        kind = select_items.game_type(ALF_BY[record['item']])[0]
        by_class.setdefault((record['side'], record['class'], record['weakness']), []).append(kind)
    assert by_class[('judging', 'attack', 'w1')] == [TYPES[3]] * 2 and by_class[('shown', 'attack', 'w1')] == [TYPES[3]]
    assert set(by_class[('judging', 'attack', 'w2')]) <= {TYPES[4], TYPES[5]} and len(by_class[('judging', 'attack', 'w2')]) == 2
    assert len(by_class[('judging', 'attack', 'w3')]) == 2
    # guards: the types B won in every run, in turn
    assert by_class[('judging', 'guard', None)] == [TYPES[0], TYPES[1], TYPES[0], TYPES[1]]
    assert by_class[('shown', 'guard', None)] == [TYPES[0], TYPES[1]]
    # calibration 6 by the gate's 3 heat, 2 cool, 1 clean of 6: exactly 3, 2, 1
    assert sorted(by_class[('judging', 'calibration', None)]) == sorted([TYPES[3]] * 3 + [TYPES[4]] * 2 + [TYPES[2]])
    assert found['shortfalls'] == [] and found['record']['gate_types'] == [[TYPES[0], 0], [TYPES[1], 0], [TYPES[2], 1],
                                                                            [TYPES[3], 3], [TYPES[4], 2], [TYPES[5], 0]]
    rooms = {}
    for record in found['records']:
        assert record['family'] == 'alfworld-room:' + ALF_BY[record['item']]['room'] and record['source'] == 'selected'
        rooms.setdefault(record['family'], set()).add(record['side'])
    assert all(len(sides) == 1 for sides in rooms.values())               # shown and judging share no room
    assert not {r['item'] for r in found['records']} & set(ALF_LEARN + ALF_GATE)
    assert len({r['item'] for r in found['records']}) == len(found['records']) == 21


def alf_types(found, side, cls):
    return [select_items.game_type(ALF_BY[r['item']])[0] for r in found['records'] if (r['side'], r['class']) == (side, cls)]


def test_alfworld_without_a_guard_type_moves_the_judging_guards_to_calibration(root):
    # review P2a finding 1 (Codex's case): every learn outcome [False, False, False]. No guard item at all; the judging
    # guard count (4) joins the calibration count (6): 10 by the gate's 3 heat, 2 cool, 1 clean of 6 -> 5, 3.33, 1.67
    # -> 5 3 1, the one left to the larger remainder (clean 4/6 against cool 2/6) -> heat 5, cool 3, clean 2. The shown
    # guard count (2) is a recorded shortfall. No shown attack items, so no room is held by the shown side.
    plan = alf_plan([TYPES[1]], [TYPES[5]], [TYPES[0]])
    inp = alf_input(root / 'u', plan, alf_quotas(6, 4, 6, 0, 2))
    inp.outcomes = {i: [False, False, False] for i in ALF_LEARN}
    found = select_items.ALFWorldSelector().make(inp)
    assert found['record']['guard_types'] == {'types': [], 'rule': 'none_all_right'}
    assert found['record']['guard_to_calibration'] == 4
    assert found['made_counts'] == {'judging': {'attack': 6, 'guard': 0, 'calibration': 10},
                                    'shown': {'attack': 0, 'guard': 0, 'calibration': 0}}
    assert sorted(alf_types(found, 'judging', 'calibration')) == sorted([TYPES[3]] * 5 + [TYPES[4]] * 3 + [TYPES[2]] * 2)
    assert found['shortfalls'] == [{'side': 'shown', 'class': 'guard', 'weakness': None, 'task_type': None, 'missing': 2,
                                    'reason': 'no_guard_type'}]
    assert not [r for r in found['records'] if r['class'] == 'guard']


def test_alfworld_with_exactly_one_perfect_type_guards_with_that_type(root):
    # only clean games were won in every run: every guard game, judging and shown, is a clean game; calibration 6 by
    # the gate's proportions -> heat 3, cool 2, clean 1; nothing moves to calibration
    outcomes = {i: [True, True, True] if ALF_BY[i]['task_type'] == TYPES[2] else [True, False, False] for i in ALF_LEARN}
    inp = alf_input(root / 'u', alf_plan([TYPES[1]], [TYPES[5]], [TYPES[0]]), alf_quotas(6, 4, 6, 0, 2))
    inp.outcomes = outcomes
    found = select_items.ALFWorldSelector().make(inp)
    assert found['record']['guard_types'] == {'types': [TYPES[2]], 'rule': 'all_right'}
    assert found['record']['guard_to_calibration'] == 0 and found['shortfalls'] == []
    assert alf_types(found, 'judging', 'guard') == [TYPES[2]] * 4 and alf_types(found, 'shown', 'guard') == [TYPES[2]] * 2
    assert sorted(alf_types(found, 'judging', 'calibration')) == sorted([TYPES[3]] * 3 + [TYPES[4]] * 2 + [TYPES[2]])
    rooms = {}
    for record in found['records']:
        rooms.setdefault(record['family'], set()).add(record['side'])
    assert all(len(sides) == 1 for sides in rooms.values())


def test_alfworld_shortfalls_are_recorded_and_never_filled(root):
    # heat games outside learn and gate: rooms 6 to 12 (7 games) -> 9 judging heat items ask for two more than exist
    plan = alf_plan([TYPES[3]], [TYPES[3]], [TYPES[3]])
    found = select_items.ALFWorldSelector().make(alf_input(root / 'u', plan, alf_quotas(9, 0, 0, 0, 0)))
    assert found['made_counts']['judging']['attack'] == 7
    assert found['shortfalls'] == [{'side': 'judging', 'class': 'attack', 'weakness': 'w2', 'missing': 1},
                                   {'side': 'judging', 'class': 'attack', 'weakness': 'w3', 'missing': 1}]
    assert found['made_counts']['judging']['calibration'] == 0


def test_the_alfworld_selection_reduced_and_reproducible(root):
    found = select_items.ALFWorldSelector().make(alf_input(root / 'a', alf_plan(), alf_quotas(4, 2, 4, 2, 2)))
    # 20 % rule: judging 10 -> attack 2, guard 2, calibration 6; shown 4 -> attack 0 (0.8), guard 4
    assert found['made_counts']['judging'] == {'attack': 2, 'guard': 2, 'calibration': 6}
    assert found['made_counts']['shown'] == {'attack': 0, 'guard': 4, 'calibration': 0}
    attack = [select_items.game_type(ALF_BY[r['item']])[0] for r in found['records'] if r['class'] == 'attack']
    assert attack == [TYPES[3], TYPES[4]]           # 2 by 3, 2, 1 of 6: 1 .67 .33 -> 1 0 0, then cool: heat, cool
    again = select_items.ALFWorldSelector().make(alf_input(root / 'b', alf_plan(), alf_quotas(4, 2, 4, 2, 2)))
    assert again == found and files(root / 'a') == files(root / 'b')
    second = select_items.ALFWorldSelector().make(alf_input(root / 'c', alf_plan(), alf_quotas(4, 2, 4, 2, 2),
                                                            registry=store_.RunRegistry(found['records']),
                                                            identity={**IDENTITY, 'round': 2}))
    assert not {r['item'] for r in second['records']} & {r['item'] for r in found['records']}
    sides = {r['family']: r['side'] for r in found['records']}
    assert all(sides.get(r['family'], r['side']) == r['side'] for r in second['records'])   # rooms keep their side


# ---- the registry -----------------------------------------------------------------------------------------------------
def test_the_registry_and_the_benches_without_a_maker(root):
    assert set(items_.MAKERS) == {'searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld'}
    assert [items_.MAKERS[b].built for b in ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld')] == [
        True, False, True, False, True]
    for bench in ('officeqa', 'spreadsheetbench'):
        maker = items_.MAKERS[bench]
        inp = items_.MakeInput(bench=bench, plan={'weaknesses': [], 'guards': []}, counts=items_.counts(bench, 0),
                               pool=[], pool_pin={}, learn_ids=[], gate_ids=[], outcomes={}, repeats=3,
                               identity=IDENTITY, registry=store_.RunRegistry(), store=store_.ItemStore(root / bench))
        found = maker.make(inp)
        assert found['status'] == 'no_items' and found['reason'] == 'maker_not_built' and found['records'] == []
        assert maker.capability_sheet()['fields'] == {} and maker.public_kind({}) == {}
        assert not (root / bench).exists()
    assert items_.MAKERS['searchqa'].capability_sheet()['fields'] == {}
    plan_.check_sheet(items_.MAKERS['searchqa'].capability_sheet())
    plan_.check_sheet(items_.MAKERS['alfworld'].capability_sheet())
