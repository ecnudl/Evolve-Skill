"""typed-v3 item stage tools, section 2 (brief P2a): the analyst's payload, request and plan validation (T4) and the
experience log (brief P2, section C). Fakes only: scripted replies, no network."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill import v225_writer
from skillopt.execskill.typed import chain as chain_, items as items_, units, writers
from skillopt.execskill.typed.items import plan as plan_


@pytest.fixture
def root():
    base = Path('/tmp/typed3-items-neutral')
    base.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='plan-', dir=base))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def receipt(text, *, finish='stop', ok=True, error=None):
    return {'ok': ok, 'response': text if ok else None, 'finish_reason': finish if ok else None,
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}, 'error_type': error}


class Script:
    """call(system, user) replying from a list: a str becomes a delivered receipt, a dict is returned as is."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        return reply if isinstance(reply, dict) else receipt(reply)


SHEET = {'maker': 'fake', 'what': 'A fake maker.', 'fields': {
    'sizes': {'kind': 'subset', 'values': ['5*2', '5*3', '6*2'], 'meaning': 'sizes'},
    'emphasis': {'kind': 'factors', 'keys': ['same', 'found_at', 'next_to'], 'range': [0.5, 2.0], 'default': 1.0,
                 'meaning': 'factors'},
    'search': {'kind': 'choice', 'values': ['any', 'needed'], 'default': 'any', 'meaning': 'search'}}}
# R = 3: failed runs (an outcome that is not True): a b c 2 each, d 1, e 3, f 2 (two unknown runs), g 0
OUTCOMES = {'a': [True, False, False], 'b': [False, True, False], 'c': [False, False, True], 'd': [True, True, False],
            'e': [False, False, False], 'f': [None, None, True], 'g': [True, True, True]}


def weakness(given, evidence, **extra):
    return {'id': given, 'description': 'Puzzles with %s.' % given, 'evidence': evidence, 'signature': 'wrong grid',
            **extra}


# ---- the evidence rule ------------------------------------------------------------------------------------------------
def test_a_weakness_needs_three_items_each_failed_in_two_of_three_runs():
    raw = {'weaknesses': [
        weakness('three', ['a', 'b', 'c']),                      # 3 items, each failed twice: kept
        weakness('two', ['a', 'b']),                             # 2 items: dropped
        weakness('one-run', ['a', 'b', 'd']),                    # d failed once: 2 counted, dropped
        weakness('with-e', ['a', 'b', 'd', 'e']),                # d does not count, e does: 3 counted, kept
        weakness('unknown-runs', ['a', 'f', 'g']),               # f: two unknown runs count as failed; g never: 2
        weakness('foreign', ['a', 'b', 'gate-7', 'zz']),         # two ids that are not learn items: 2 counted
        weakness('repeated', ['a', 'a', 'b', 'c', 7]),           # a repeated id counts once; 7 is not an id
        {'id': 'no-text', 'evidence': ['a', 'b', 'c']},          # no description: dropped
        'not an object'],
        'guards': [{'description': 'Two-column puzzles.', 'spec': {'sizes': ['5*2']}}, {'spec': {}}], 'note': 'n'}
    plan, record = plan_.validate_plan(raw, OUTCOMES, 3, SHEET)
    assert [(w['id'], w['given_id'], w['evidence']) for w in plan['weaknesses']] == [
        ('w1', 'three', ['a', 'b', 'c']), ('w2', 'with-e', ['a', 'b', 'e']), ('w3', 'repeated', ['a', 'b', 'c'])]
    rows = {row['position']: row for row in record['weaknesses']}
    assert [rows[p]['reason'] for p in range(1, 10)] == ['kept', 'too_little_evidence', 'too_little_evidence', 'kept',
                                                          'too_little_evidence', 'too_little_evidence', 'kept',
                                                          'no_description', 'not_an_object']
    assert (rows[3]['evidence_given'], rows[3]['evidence_counted']) == (3, 2)
    assert (rows[7]['evidence_given'], rows[7]['evidence_counted']) == (3, 3)
    assert {'weakness': 3, 'id': 'd', 'reason': 'failed_in_too_few_runs', 'failed_runs': 1} in record['evidence']
    assert {'weakness': 5, 'id': 'g', 'reason': 'failed_in_too_few_runs', 'failed_runs': 0} in record['evidence']
    assert [e for e in record['evidence'] if e['reason'] == 'not_a_learn_item'] == [
        {'weakness': 6, 'id': 'gate-7', 'reason': 'not_a_learn_item'}, {'weakness': 6, 'id': 'zz', 'reason': 'not_a_learn_item'}]
    assert {'weakness': 7, 'id': '7', 'reason': 'not_an_id'} in record['evidence']
    assert plan['guards'] == [{'id': 'g1', 'description': 'Two-column puzzles.', 'spec': {'sizes': ['5*2']}}]
    assert [row['reason'] for row in record['guards']] == ['kept', 'no_description']
    assert record['kept'] == 3 and record['rule_applied'] == 'quota' and plan['unreadable'] is False
    assert items_.counts('zebralogic', [w['id'] for w in plan['weaknesses']])['rule'] == 'quota'


def test_ids_are_unique_and_canonical_whatever_the_analyst_wrote():
    raw = {'weaknesses': [weakness('x', ['a', 'b', 'c']), weakness('x', ['a', 'b', 'e']),
                          weakness('../final/test', ['a', 'c', 'e'])], 'guards': [], 'note': ''}
    plan, record = plan_.validate_plan(raw, OUTCOMES, 3, SHEET)
    assert [(w['id'], w['given_id']) for w in plan['weaknesses']] == [('w1', 'x'), ('w2', 'x'), ('w3', '../final/test')]
    again, _ = plan_.validate_plan(json.loads(json.dumps(raw)), OUTCOMES, 3, SHEET)
    assert again == plan                                                          # deterministic


def test_spec_fields_are_those_of_the_capability_sheet():
    spec = {'sizes': ['6*2', '9*9', '5*2'], 'emphasis': {'same': 2.0, 'found_at': 0.25, 'nope': 1, 'next_to': True},
            'search': 'sometimes', 'colour': 'red'}
    raw = {'weaknesses': [weakness('w', ['a', 'b', 'c'], spec=spec)], 'guards': [{'description': 'g', 'spec': {'x': 1}}]}
    plan, record = plan_.validate_plan(raw, OUTCOMES, 3, SHEET)
    assert plan['weaknesses'][0]['spec'] == {'sizes': ['5*2', '6*2'], 'emphasis': {'same': 2.0}}   # the sheet's order
    assert record['spec'] == [
        {'weakness': 1, 'field': 'colour', 'reason': 'unknown_field'},
        {'weakness': 1, 'field': 'emphasis', 'value': 'found_at', 'reason': 'out_of_range'},
        {'weakness': 1, 'field': 'emphasis', 'value': 'next_to', 'reason': 'not_a_number'},
        {'weakness': 1, 'field': 'emphasis', 'value': 'nope', 'reason': 'unknown_key'},
        {'weakness': 1, 'field': 'search', 'value': 'sometimes', 'reason': 'unknown_value'},
        {'weakness': 1, 'field': 'sizes', 'value': '9*9', 'reason': 'unknown_value'},
        {'guard': 1, 'field': 'x', 'reason': 'unknown_field'}]
    assert plan['guards'][0]['spec'] == {}
    kept, dropped = plan_.check_spec({'emphasis': {'same': 0.5, 'next_to': 2}, 'search': 'needed'}, SHEET)
    assert kept == {'emphasis': {'same': 0.5, 'next_to': 2}, 'search': 'needed'} and dropped == []   # bounds included
    assert plan_.check_spec({'sizes': ['7*7']}, SHEET) == ({}, [{'field': 'sizes', 'value': '7*7', 'reason': 'unknown_value'},
                                                                {'field': 'sizes', 'reason': 'empty'}])
    assert plan_.check_spec('fast', SHEET) == ({}, [{'field': None, 'reason': 'not_an_object'}])


def test_an_unreadable_plan_is_no_weakness():
    for raw in (None, 'unreadable', {'weaknesses': 'none'}, {'guards': []}):
        plan, record = plan_.validate_plan(raw, OUTCOMES, 3, SHEET)
        assert plan == {'weaknesses': [], 'guards': [], 'note': '', 'unreadable': True}
        assert record['readable'] is False and record['reason'] == 'unreadable' and record['kept'] == 0
    assert items_.counts('searchqa', [])['rule'] == 'reduced_attack'


def test_long_texts_are_cut_and_named():
    raw = {'weaknesses': [{**weakness('w', ['a', 'b', 'c']), 'description': 'd' * 900, 'signature': 's' * 400}],
           'note': 'n' * 1500}
    plan, record = plan_.validate_plan(raw, OUTCOMES, 3, SHEET)
    w = plan['weaknesses'][0]
    assert len(w['description']) == plan_.DESCRIPTION_CHARS and len(w['signature']) == plan_.SIGNATURE_CHARS
    assert len(plan['note']) == plan_.NOTE_CHARS
    assert [row['part'] for row in record['truncated']] == ['description', 'signature', 'note']


# ---- the request ------------------------------------------------------------------------------------------------------
GOOD = json.dumps({'weaknesses': [weakness('w', ['a', 'b', 'c'])], 'guards': [], 'note': 'ok'})


def payload():
    rows = [{'id': key, 'public_text': 'puzzle %s' % key, 'outcomes': value} for key, value in OUTCOMES.items()]
    found, dropped = plan_.analyst_payload(bench='zebralogic', task_card='Solve the grid.', learn=rows, repeats=3,
                                           experience=[], capability_sheet=SHEET)
    assert dropped == {'stable_texts': 0, 'replies': 0, 'texts': 0}
    return found


def test_a_readable_reply_is_read_once():
    call = Script(['Here is my plan:\n```json\n' + GOOD + '\n```'])
    found = plan_.request_plan(call, payload())
    assert found['status'] == 'ok' and found['raw']['note'] == 'ok' and len(call.calls) == 1
    system, user = call.calls[0]
    assert system == plan_.ANALYST_SYSTEM and json.loads(user) == payload()
    assert found['request_sha256'] == writers.request_sha256(system, user) and found['attempts'][0]['readable']


def test_one_format_retry_then_unreadable_with_both_replies_kept():
    call = Script(['I think the solver struggles with big grids.', '{"weaknesses": "several"}'])
    found = plan_.request_plan(call, payload())
    assert found['status'] == 'unreadable' and found['raw'] is None and len(call.calls) == 2
    assert call.calls[1][1] == call.calls[0][1] + plan_.ANALYST_RETRY and call.calls[1][0] == plan_.ANALYST_SYSTEM
    assert [a['reply'] for a in found['attempts']] == ['I think the solver struggles with big grids.', '{"weaknesses": "several"}']
    assert [a['readable'] for a in found['attempts']] == [False, False]
    plan, record = plan_.validate_plan(found['raw'], OUTCOMES, 3, SHEET)
    assert plan['unreadable'] and record['reason'] == 'unreadable'
    # a model-side noncompletion is unreadable too (the retry is sent); the retry may succeed
    call = Script([receipt('{"weak', finish='length'), GOOD])
    found = plan_.request_plan(call, payload())
    assert found['status'] == 'ok' and found['attempts'][0]['failure'] == 'model_side:finish_length'
    assert found['request_sha256'] == found['attempts'][1]['request_sha256'] != found['attempts'][0]['request_sha256']


def test_an_infrastructure_failure_ends_the_request_without_the_format_retry():
    call = Script([receipt(None, ok=False, error='http_502')])
    found = plan_.request_plan(call, payload())
    assert found['status'] == 'infrastructure' and len(call.calls) == 1
    assert found['attempts'][0]['failure'] == 'infrastructure:http_502'
    call = Script(['no json here', receipt(None, ok=False, error='timeout')])
    assert plan_.request_plan(call, payload())['status'] == 'infrastructure' and len(call.calls) == 2


def test_the_request_is_charged_and_recorded_like_a_writer_call(root):
    ledger = units.Ledger(root / 'ledger.json', 10 ** 9)
    script = Script(['not a plan', GOOD])
    out = root / 's3' / 'items-plan' / 'calls' / 'analyst-item_analyst.json'
    call = units.CallRecorder(script, ledger, max_tokens=32_768, tag='analyst', unit='s3/items-plan', out_path=out)
    found = plan_.request_plan(call, payload())
    assert found['status'] == 'ok'
    assert ledger.state['sends'] == 2 and ledger.state['by_unit']['s3/items-plan']['calls'] == 2
    assert ledger.state['reported'] == 30 and not ledger.state['pending']
    sends = json.loads(out.read_text())
    assert [s['system'] for s in sends] == [plan_.ANALYST_SYSTEM] * 2 and sends[1]['receipt']['response'] == GOOD


class Killed(Exception):
    """The process killed at a chosen point."""


def recorder(client, ledger, out):
    return units.CallRecorder(client, ledger, max_tokens=32_768, tag='analyst', unit='s3/items-plan', out_path=out)


def test_a_recorded_verdict_is_replayed_and_an_infrastructure_failure_is_not():
    request = units.sha256_text('S' + '\x00' + 'U')
    infrastructure = {'request_sha256': request, 'receipt': receipt(None, ok=False, error='http_502')}
    cut = {'request_sha256': request, 'receipt': receipt('{"weak', finish='length')}
    delivered = {'request_sha256': request, 'receipt': receipt(GOOD)}
    other = {'request_sha256': units.sha256_text('S' + '\x00' + 'V'), 'receipt': receipt(GOOD)}
    held = type('Held', (), {})()
    held.sends = [other, infrastructure, cut, delivered]
    assert plan_.recorded_receipt(held, 'S', 'U') == cut['receipt']           # the first verdict of exactly this request
    held.sends = [other, infrastructure, {'request_sha256': request, 'receipt': None, 'exception': 'Killed'}]
    assert plan_.recorded_receipt(held, 'S', 'U') is None                     # no verdict: it is sent again
    assert plan_.recorded_receipt(lambda system, user: None, 'S', 'U') is None
    held.sends = [delivered]                                                  # no __call__: a send would raise
    assert plan_.send_or_replay(held, 'S', 'U') == delivered['receipt']


def test_an_analyst_request_answered_before_a_kill_is_not_sent_again(root):
    # the gap of review P2a finding 3 for the analyst: the recorder wrote the reply before P2b wrote the plan record;
    # the resumed unit refills a new recorder from the calls file (chain._keep_earlier_sends) and sends nothing
    ledger, sent = units.Ledger(None, 10 ** 9), []
    replies = [GOOD, json.dumps({'weaknesses': [], 'guards': [], 'note': 'another plan'})]

    def client(system, user):
        sent.append(user)
        return receipt(replies[len(sent) - 1])
    out = root / 'a' / 'calls' / 'analyst-item_analyst.json'
    first = plan_.request_plan(recorder(client, ledger, out), payload())
    again = plan_.request_plan(chain_._keep_earlier_sends(recorder(client, ledger, out)), payload())
    assert again == first and first['raw']['note'] == 'ok' and len(sent) == 1 and ledger.state['sends'] == 1
    # attempt 1 answered (unreadable) and the process killed during attempt 2: only attempt 2 is sent on resume
    calls = []

    def flaky(system, user):
        calls.append(user)
        if len(calls) == 2:
            raise Killed()
        return receipt('prose, no plan' if len(calls) == 1 else GOOD)
    out = root / 'b' / 'calls' / 'analyst-item_analyst.json'
    with pytest.raises(Killed):
        plan_.request_plan(recorder(flaky, ledger, out), payload())
    found = plan_.request_plan(chain_._keep_earlier_sends(recorder(flaky, ledger, out)), payload())
    assert found['status'] == 'ok' and len(calls) == 3 and [a['reply'] for a in found['attempts']] == ['prose, no plan', GOOD]
    assert calls[2] == calls[1] == calls[0] + plan_.ANALYST_RETRY
    # an infrastructure failure is no verdict: the resumed request sends it again
    count = []

    def outage(system, user):
        count.append(user)
        return receipt(None, ok=False, error='http_502') if len(count) == 1 else receipt(GOOD)
    out = root / 'c' / 'calls' / 'analyst-item_analyst.json'
    assert plan_.request_plan(recorder(outage, ledger, out), payload())['status'] == 'infrastructure'
    found = plan_.request_plan(chain_._keep_earlier_sends(recorder(outage, ledger, out)), payload())
    assert found['status'] == 'ok' and len(count) == 2


# ---- what the analyst sees -------------------------------------------------------------------------------------------
def cell(item_id, correct, reply):
    return {'item_id': item_id, 'arm': 'B', 'correct': correct, 'reply': reply,
            'sends': [{'system': 's', 'user': 'u', 'receipt': receipt(reply)}]}


def test_learn_rows_are_public_text_outcomes_and_one_wrong_reply_bounded():
    items = [{'benchmark': 'searchqa', 'task_id': 'q%d' % i,
              'public': {'question': 'Question %d?' % i, 'context': ('Snippet %d. ' % i) * 400},
              'private': {'answers': ['SECRET-ANSWER-%d' % i]}} for i in range(3)]
    runs = {'q0': [cell('q0', True, 'r'), cell('q0', True, 'r'), cell('q0', True, 'r')],
            'q1': [cell('q1', True, 'right'), cell('q1', False, 'first wrong ' + 'x' * 3000), cell('q1', False, 'second')],
            'q2': [cell('q2', None, ''), cell('q2', None, 'cut reply'), cell('q2', True, 'r')]}
    rows = plan_.learn_rows('searchqa', items, runs, 3)
    assert [row['outcomes'] for row in rows] == [[True] * 3, [True, False, False], [None, None, True]]
    assert 'wrong_reply' not in rows[0] and rows[2]['wrong_reply'] == 'cut reply'
    assert rows[1]['wrong_reply'].startswith('first wrong') and v225_writer.TRUNCATION_MARK in rows[1]['wrong_reply']
    assert len(rows[1]['wrong_reply']) == writers.REPLY_HEAD + writers.REPLY_TAIL + len(v225_writer.TRUNCATION_MARK)
    # the public text: question + the first 1,500 characters of the snippets (tasktypes.public_text), then the
    # writers' view bound of 3,000 characters
    assert rows[0]['public_text'].startswith('Question 0?\nSnippet 0.') and len(rows[0]['public_text']) <= writers.VIEW_CHARS
    assert 'SECRET-ANSWER' not in json.dumps(rows)
    sized = plan_.learn_rows('searchqa', items, runs, 3, kind_of=lambda item: {'size': item['task_id'][-1]})
    assert [row['size'] for row in sized] == ['0', '1', '2']
    with pytest.raises(ValueError):
        plan_.learn_rows('searchqa', items[:2], runs, 3)


def test_the_payload_refuses_references_and_fits_its_bound(monkeypatch):
    rows = [{'id': 'r%02d' % i, 'public_text': 't' * 1000, 'outcomes': [i % 2 == 0] * 3,
             **({'wrong_reply': 'w' * 500} if i % 2 else {})} for i in range(10)]
    with pytest.raises(ValueError):
        plan_.analyst_payload(bench='searchqa', task_card='c', learn=[{**rows[0], 'reference': 'x'}], repeats=3,
                              experience=[], capability_sheet=SHEET)
    found, dropped = plan_.analyst_payload(bench='searchqa', task_card='c', learn=rows, repeats=3, experience=[],
                                           capability_sheet=SHEET)
    assert dropped == {'stable_texts': 0, 'replies': 0, 'texts': 0} and found['request'] == 'plan'
    full = plan_._bytes(found)
    # null in place of a 1,000-character text saves 1,002 - 4 bytes; a dropped reply saves its key, its 502 quoted
    # characters and the separators: len(', "wrong_reply": "w...w"')
    text_saving = len(json.dumps('t' * 1000)) - len('null')
    reply_saving = len(', "wrong_reply": ' + json.dumps('w' * 500))
    assert (text_saving, reply_saving) == (998, 519)
    # a bound 10 bytes beyond five stable texts, five replies and one more text: a second text has to go as well
    monkeypatch.setattr(plan_, 'INPUT_BYTES', full - 5 * text_saving - 5 * reply_saving - text_saving - 10)
    found, dropped = plan_.analyst_payload(bench='searchqa', task_card='c', learn=rows, repeats=3, experience=[],
                                           capability_sheet=SHEET)
    assert dropped == {'stable_texts': 5, 'replies': 5, 'texts': 2}
    # stable texts are rows 8, 6, 4, 2, 0 (from the last), replies rows 9 .. 1, then the texts of rows 9 and 7
    assert [row['public_text'] is None for row in found['learn_items']] == [True, False, True, False, True, False,
                                                                            True, True, True, True]
    assert all('wrong_reply' not in row for row in found['learn_items'])
    assert plan_._bytes(found) <= plan_.INPUT_BYTES


def test_the_revision_block_holds_the_first_plan_and_counts_only():
    plan, _ = plan_.validate_plan({'weaknesses': [weakness('x', ['a', 'b', 'c'])], 'guards': []}, OUTCOMES, 3, SHEET)
    rows = [items_.item_record(item='i%d' % i, cls='attack', weakness='w1', side='judging', family='i%d' % i,
                               source='selected', certificate=None, item_sha256='c' * 64) for i in range(4)]
    rows += [items_.item_record(item='k%d' % i, cls='calibration', weakness=None, side='judging', family='k%d' % i,
                                source='selected', certificate=None, item_sha256='d' * 64) for i in range(4)]
    check = items_.check_items(rows, {**{'i%d' % i: i < 3 for i in range(4)}, **{'k%d' % i: i < 3 for i in range(4)}})
    block = plan_.revision_block(plan, check)
    assert block['check'] == {'attack': {'n': 4, 'right': 3}, 'calibration': {'n': 4, 'right': 3},
                              'by_weakness': [['w1', 4, 3]], 'margin_points': 5}
    assert block['first_plan']['weaknesses'][0]['evidence'] == ['a', 'b', 'c']
    assert 'i0' not in json.dumps(block) and 'k0' not in json.dumps(block)
    found, _ = plan_.analyst_payload(bench='zebralogic', task_card='c', learn=[], repeats=3, experience=[],
                                     capability_sheet=SHEET, revision=block)
    assert found['request'] == 'revise' and found['revision'] == block


# ---- the experience log ----------------------------------------------------------------------------------------------
def test_the_experience_log_holds_counts_and_descriptions_only():
    decisions = {'cards': [{'kind': 'card', 'accepted': False, 'reason': 'gain_below_tau', 'gain_points': 4.6666667,
                            'n': 100, 'text_sha256': 'f' * 64, 'per_item': [['q1', 2, 3]]},
                           {'kind': 'card', 'accepted': True, 'reason': 'accepted', 'gain_points': 6.0, 'n': 100}],
                 'programs': [{'kind': 'program', 'origin': 'archive', 'accepted': False,
                               'reason': 'screen:policy: [{"rule": "import", "line": "import os"}]'},
                              {'kind': 'program', 'accepted': True, 'reason': 'accepted', 'gain_points': 3.333,
                               'n': 100, 'procedure_id': 'p-1'}]}
    candidates = plan_.candidates_of_decisions(decisions)
    assert [(c['kind'], c['accepted']) for c in candidates] == [('card', False), ('card', True), ('archive', False),
                                                                ('program', True)]
    candidates[1]['attack'] = {'w1': {'n': 20, 'gain_points': 10.0}, 'w2': {'n': 20, 'gain_points': -1.6667}}
    candidates[0]['attack'] = {'w1': {'n': 20, 'gain_points': 50.0}}            # refused: never shown
    candidates[3]['attack'] = {'w1': {'n': 20, 'gain_points': 0}}
    steps = [{'step': 1, 'bench': 'searchqa', 'candidates': candidates,
              'weaknesses': [{'id': 'w1', 'description': 'Questions about dates. ' * 40, 'evidence': ['q1', 'q2']},
                             {'id': 'w2', 'description': 'Lists.'}],
              'items': [{'public': {'question': 'SECRET QUESTION TEXT'}}], 'replies': ['SECRET REPLY']},
             {'step': 2, 'bench': 'officeqa', 'candidates': [], 'weaknesses': []}]
    log = plan_.experience_log(steps)
    assert log[0]['candidates'] == [
        {'candidate': 1, 'kind': 'card', 'decision': 'refused', 'reason': 'gain_below_tau', 'gain_points': 4.67, 'n': 100},
        {'candidate': 2, 'kind': 'card', 'decision': 'accepted', 'reason': None, 'gain_points': 6.0, 'n': 100},
        {'candidate': 3, 'kind': 'archive', 'decision': 'refused', 'reason': 'screen:policy', 'gain_points': None, 'n': None},
        {'candidate': 4, 'kind': 'program', 'decision': 'accepted', 'reason': None, 'gain_points': 3.33, 'n': 100}]
    first, second = log[0]['weaknesses']
    assert len(first['description']) == plan_.DESCRIPTION_CHARS and 'evidence' not in first
    assert first['accepted_candidates_on_attack'] == [{'candidate': 2, 'kind': 'card', 'n': 20, 'gain_points': 10.0},
                                                      {'candidate': 4, 'kind': 'program', 'n': 20, 'gain_points': 0.0}]
    assert second['accepted_candidates_on_attack'] == [{'candidate': 2, 'kind': 'card', 'n': 20, 'gain_points': -1.67}]
    assert log[1] == {'step': 2, 'bench': 'officeqa', 'candidates': [], 'weaknesses': []}
    text = json.dumps(log)
    for secret in ('SECRET', 'q1', 'text_sha256', 'per_item', 'procedure_id', 'import os'):
        assert secret not in text
    assert set(log[0]) == {'step', 'bench', 'candidates', 'weaknesses'}


def test_the_experience_log_refuses_what_it_cannot_vouch_for():
    with pytest.raises(ValueError):
        plan_.experience_log([{'step': 2, 'bench': 'searchqa'}, {'step': 1, 'bench': 'officeqa'}])   # order
    with pytest.raises(ValueError):
        plan_.experience_log([{'step': 1, 'bench': 'searchqa', 'candidates': [{'kind': 'idea', 'accepted': True}]}])
    with pytest.raises(ValueError):
        plan_.experience_log([{'step': 1, 'bench': 'searchqa', 'weaknesses': [{'id': 'dates', 'description': 'x'}]}])
    with pytest.raises(ValueError):
        plan_.experience_log([{'step': 1, 'bench': 'searchqa',
                               'candidates': [{'kind': 'card', 'accepted': False, 'gain_points': 'many'}]}])
    assert plan_.reason_label(None) == 'unknown' and plan_.reason_label('unreadable:no_manifest') == 'unreadable:no_manifest'
    assert plan_.reason_label('x' * 100) == 'x' * 64
