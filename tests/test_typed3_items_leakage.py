"""typed-v3 item stage tools (brief P2a, rules that are not negotiable): the analyst sees learn items' public text and
outcomes only, the selector candidates' public text only; no gate item, no judging-side item (in the analyst's
requests) and no reference answer reaches a role call. Every request the fakes receive is scanned. Fakes only."""
import json
import random
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill import zebralogic
from skillopt.execskill.typed import items as items_
from skillopt.execskill.typed.bank import zebra
from skillopt.execskill.typed.items import plan as plan_, select_items, store as store_, zebra_items


@pytest.fixture
def root():
    base = Path('/tmp/typed3-items-neutral')
    base.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='leak-', dir=base))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def receipt(text):
    return {'ok': True, 'response': text, 'finish_reason': 'stop',
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}, 'error_type': None}


class Recorder:
    """A role call that keeps every request and answers from ``reply(system, user)``."""

    def __init__(self, reply):
        self.reply, self.requests, self.users = reply, [], []

    def __call__(self, system, user):
        self.requests.append(system + '\n' + user)
        self.users.append(user)
        return receipt(self.reply(system, user))


def found_in(requests, markers):
    """The markers found in the requests, as written or as they stand inside a JSON string (a puzzle's newlines)."""
    text = '\n'.join(requests)
    return sorted(marker for marker in markers if marker in text or json.dumps(marker, ensure_ascii=False)[1:-1] in text)


def test_the_scan_finds_an_escaped_text():
    puzzle = 'There are 5 houses.\n## Clues:\n1. Bob is "first".\n'
    assert found_in(['{"q": %s}' % json.dumps(puzzle)], [puzzle, 'absent']) == [puzzle]


def cells(item_id, outcomes):
    return [{'item_id': item_id, 'correct': value, 'reply': 'My answer is guess-%s-%d.' % (item_id, r),
             'sends': []} for r, value in enumerate(outcomes)]


def analyst_reply(weakness_evidence, guards=True):
    plan = {'weaknesses': [{'id': 'k%d' % n, 'description': 'kind %d' % n, 'evidence': evidence, 'signature': 's',
                            'spec': {}} for n, evidence in enumerate(weakness_evidence, 1)],
            'guards': [{'description': 'what it gets right (counts).', 'spec': {}}] if guards else [], 'note': ''}
    return lambda system, user: json.dumps(plan)


# ---- SearchQA: the analyst, the selector, the revision ------------------------------------------------------------------
def sq(i):
    return {'benchmark': 'searchqa', 'task_id': 'sq-%02d' % i, 'family_id': 'exact-%02d' % i,
            'public': {'question': 'Q-%02d: which city hosted event %d?' % (i, i), 'context': 'CTX-%02d snippet.' % i},
            'private': {'answers': ['REF-%02d' % i]}}


def test_no_gate_item_judging_item_or_reference_reaches_a_searchqa_role_call(root):
    pool = [sq(i) for i in range(70)]
    learn, gate = pool[:10], pool[10:20]
    outcomes = {item['task_id']: ([False, False, True] if i < 9 else [True] * 3) for i, item in enumerate(learn)}
    runs = {item['task_id']: cells(item['task_id'], outcomes[item['task_id']]) for item in learn}
    sheet = items_.MAKERS['searchqa'].capability_sheet()
    rows = plan_.learn_rows('searchqa', learn, runs, 3)
    experience = plan_.experience_log([{'step': 1, 'bench': 'zebralogic', 'candidates': [
        {'kind': 'card', 'accepted': True, 'reason': 'accepted', 'gain_points': 5.0, 'n': 300, 'text': 'Q-15: leaked?',
         'attack': {'w1': {'n': 80, 'gain_points': 7.5, 'items': ['sq-11']}}}],
        'weaknesses': [{'id': 'w1', 'description': 'big grids', 'evidence': ['sq-12']}]}])
    payload, _ = plan_.analyst_payload(bench='searchqa', task_card='Answer from the snippets.', learn=rows, repeats=3,
                                       experience=experience, capability_sheet=sheet)
    analyst = Recorder(analyst_reply([['sq-00', 'sq-01', 'sq-02'], ['sq-03', 'sq-04', 'sq-05'],
                                      ['sq-06', 'sq-07', 'sq-08', 'sq-15']]))
    raw = plan_.request_plan(analyst, payload)['raw']
    plan, record = plan_.validate_plan(raw, plan_.outcomes_of(runs, 3), 3, sheet)
    assert len(plan['weaknesses']) == 3 and {'weakness': 3, 'id': 'sq-15', 'reason': 'not_a_learn_item'} in record['evidence']

    def select(system, user):
        request = json.loads(user.split('\n\nFormat retry')[0])
        ids = [row['id'] for row in request['descriptions']]
        return json.dumps({'matches': {row['label']: ids[n % len(ids)] for n, row in enumerate(request['candidates'])}})
    selector = Recorder(select)
    quotas = {'searchqa': {'judging': {'attack': 6, 'guard': 3, 'calibration': 6}, 'shown': {'attack': 3, 'guard': 2}}}
    counts = items_.counts('searchqa', [w['id'] for w in plan['weaknesses']], quotas)
    inp = items_.MakeInput(bench='searchqa', plan=plan, counts=counts, pool=pool, pool_pin={'path': '/p', 'sha256': 'b' * 64},
                           learn_ids=[i['task_id'] for i in learn], gate_ids=[i['task_id'] for i in gate],
                           outcomes=plan_.outcomes_of(runs, 3), repeats=3, identity={'version': 'typed-v3', 'chain': 'G',
                                                                                       'step': 1, 'round': 1},
                           registry=store_.RunRegistry(), store=store_.ItemStore(root / 'items'),
                           role_call=lambda tag: selector)
    found = items_.MAKERS['searchqa'].make(inp)
    judging = [r for r in found['records'] if r['side'] == 'judging']
    assert len(judging) == 15 and len(selector.requests) == 2
    # the revision of items-plan-2 after a check of B on the judging attack and calibration items (counts only)
    check = items_.check_items([r for r in judging if r['class'] != 'guard'],
                               {r['item']: n % 2 == 0 for n, r in enumerate(judging)})
    payload_2, _ = plan_.analyst_payload(bench='searchqa', task_card='Answer from the snippets.', learn=rows, repeats=3,
                                         experience=experience, capability_sheet=sheet,
                                         revision=plan_.revision_block(plan, check))
    plan_.request_plan(analyst, payload_2)
    assert len(analyst.requests) == 2

    by_id = {item['task_id']: item for item in pool}
    gate_text = [m for item in gate for m in (item['public']['question'], item['public']['context'], item['task_id'])]
    references = ['REF-%02d' % i for i in range(70)]
    judging_text = [m for r in judging for m in (by_id[r['item']]['public']['question'],
                                                 by_id[r['item']]['public']['context'], r['item'])]
    # the analyst: nothing of a gate item, of a judging-side item or a reference, in either request
    assert found_in(analyst.requests, gate_text + references + judging_text) == []
    assert found_in(analyst.requests, ['Q-15', 'sq-11', 'sq-12', 'leaked']) == []      # junk of the experience input
    # the selector: candidates' public text only -- no gate or learn item, no reference, no item id
    learn_text = [m for item in learn for m in (item['public']['question'], item['public']['context'])]
    assert found_in(selector.requests, gate_text + learn_text + references + ['sq-', 'exact-']) == []
    shown = [json.loads(user.split('\n\nFormat retry')[0]) for user in selector.users]
    candidates = {plan_.public_text_of('searchqa', item) for item in pool[20:]}
    assert all(row['text'] in candidates for request in shown for row in request['candidates'])
    # and the learn items' public text and outcomes do reach the analyst
    assert all(item['public']['question'] in analyst.requests[0] for item in learn)


# ---- ZebraLogic: the analyst before and after making ---------------------------------------------------------------------
VALUES = {'Name': ['Alice', 'Arnold', 'Bob', 'Carol', 'Eric', 'Peter'],
          'Pet': ['bird', 'cat', 'dog', 'fish', 'hamster', 'rabbit'],
          'Height': ['average', 'short', 'super tall', 'tall', 'very short', 'very tall']}
LANGUAGE = {'columns': {c: {'intro': 'Intro of %s' % c, 'values': {str(n): sorted(VALUES[c][:n]) for n in range(2, 7)}}
                        for c in VALUES},
            'phrases': {'Name': {v: v for v in VALUES['Name']}, 'Pet': {v: 'the person who keeps a %s' % v for v in VALUES['Pet']},
                        'Height': {v: 'the person who is %s' % v for v in VALUES['Height']}}}


def zebra_pool(count=48):
    rows = []
    for n in range(count):
        houses, columns = (5, 6)[n % 2], (2, 3)[(n // 2) % 2]
        rng = random.Random('leak:%d' % n)
        puzzle = zebra.make(rng, houses, ['Name'] + rng.sample(['Height', 'Pet'], columns - 1), LANGUAGE)
        rows.append(zebralogic.normalize(zebra.row_of(puzzle, LANGUAGE, 'lgp-test-%03d' % n), partition='pool'))
    return rows


def test_no_gate_or_judging_puzzle_or_grid_reaches_the_zebralogic_analyst(root):
    pool = zebra_pool()
    learn, gate = pool[:12], pool[12:24]
    outcomes = {item['task_id']: [False, False, False] if n < 8 else [True] * 3 for n, item in enumerate(learn)}
    runs = {item['task_id']: cells(item['task_id'], outcomes[item['task_id']]) for item in learn}
    maker = items_.MAKERS['zebralogic']
    sheet = maker.capability_sheet(pool=pool, learn_ids=[i['task_id'] for i in learn], gate_ids=[i['task_id'] for i in gate])
    rows = plan_.learn_rows('zebralogic', learn, runs, 3, kind_of=maker.public_kind)
    assert {row['size'] for row in rows} == {'5*2', '6*2', '5*3', '6*3'}
    payload, _ = plan_.analyst_payload(bench='zebralogic', task_card='Solve the grid.', learn=rows, repeats=3,
                                       experience=[], capability_sheet=sheet)
    ids = [item['task_id'] for item in learn]
    analyst = Recorder(analyst_reply([ids[0:3], ids[3:6], ids[5:8]], guards=False))
    plan, _ = plan_.validate_plan(plan_.request_plan(analyst, payload)['raw'], plan_.outcomes_of(runs, 3), 3, sheet)
    quotas = {'zebralogic': {'judging': {'attack': 3, 'guard': 2, 'calibration': 2}, 'shown': {'attack': 3, 'guard': 1}}}
    inp = items_.MakeInput(bench='zebralogic', plan=plan, counts=items_.counts('zebralogic', [w['id'] for w in plan['weaknesses']], quotas),
                           pool=pool, pool_pin={'path': '/p/z.json', 'sha256': 'a' * 64}, learn_ids=ids,
                           gate_ids=[i['task_id'] for i in gate], outcomes=plan_.outcomes_of(runs, 3), repeats=3,
                           identity={'version': 'typed-v3', 'chain': 'D', 'step': 3, 'round': 1},
                           registry=store_.RunRegistry(), store=store_.ItemStore(root / 'items'))
    found = zebra_items.ZebraMaker().make(inp)
    judging = [r for r in found['records'] if r['side'] == 'judging']
    assert len(judging) == 7
    check = items_.check_items([r for r in judging if r['class'] != 'guard'], {r['item']: True for r in judging})
    payload_2, _ = plan_.analyst_payload(bench='zebralogic', task_card='Solve the grid.', learn=rows, repeats=3,
                                         experience=[], capability_sheet=sheet, revision=plan_.revision_block(plan, check))
    plan_.request_plan(analyst, payload_2)
    store = store_.ItemStore(root / 'items')
    made_text = [store.item(row['slot'])['public']['question'] for row in found['slots'] if row['side'] == 'judging']
    grids = [json.dumps(item['private']['answer'], sort_keys=True) for item in pool]
    gate_text = [item['public']['question'] for item in gate] + [item['task_id'] for item in gate]
    assert found_in(analyst.requests, gate_text + made_text + [r['item'] for r in judging] + grids) == []
    assert all(json.dumps(item['public']['question'])[1:-1] in analyst.requests[0] for item in learn)


# ---- ALFWorld: the analyst sees learn games only ---------------------------------------------------------------------------
def test_no_gate_game_reaches_the_alfworld_analyst():
    def game(i, kind):
        observation = 'OBS-%02d: you are in a room. Your task is to: do %s.' % (i, kind)
        return {'benchmark': 'alfworld', 'task_id': 'alfworld-xs:%02d' % i, 'room': str(i % 5 + 1), 'task_type': kind,
                'public': {'game_file': 'json_2.1.1/train/%s-Mug-None-Shelf-%d/trial_%d/game.tw-pddl' % (kind, i % 5 + 1, i),
                           'routing_view': {'initial_observation': observation, 'admissible_commands_at_reset': ['look'],
                                            'task_text': 'do %s' % kind},
                           'routing_view_sha256': '0' * 64},
                'private': {'game_metadata': {'walkthrough': ['WALK-%02d' % i]}}}
    games = [game(i, select_items.TYPES[i % 6]) for i in range(30)]
    learn, gate = games[:8], games[8:20]
    runs = {g['task_id']: cells(g['task_id'], [False, True, False]) for g in learn}
    maker = items_.MAKERS['alfworld']
    rows = plan_.learn_rows('alfworld', learn, runs, 3, kind_of=maker.public_kind)
    assert [row['task_type'] for row in rows] == [select_items.TYPES[i % 6] for i in range(8)]
    payload, _ = plan_.analyst_payload(bench='alfworld', task_card='Act in the house.', learn=rows, repeats=3,
                                       experience=[], capability_sheet=maker.capability_sheet())
    analyst = Recorder(analyst_reply([]))
    plan_.request_plan(analyst, payload)
    markers = ['OBS-%02d' % i for i in range(8, 30)] + ['WALK-'] + [g['task_id'] for g in gate]
    assert found_in(analyst.requests, markers) == []
    assert all('OBS-%02d' % i in analyst.requests[0] for i in range(8))
