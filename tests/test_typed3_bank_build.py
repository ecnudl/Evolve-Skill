"""typed-v3 item bank: the environment (resumable recorded calls, write-once records) and the OfficeQA stages
(trace with one repair, twins, the checker's keep / drop rule, the report) with fake clients. The checker goes
through the real frozen solver request and answer-tag scorer. No network."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.continual_eval import backends
from skillopt.execskill import v222_cards
from skillopt.execskill.typed import prepare, units
from skillopt.execskill.typed.bank import env as bank_env, oqa, oqa_build, prompts

DOC = """The following content is pre-parsed from the oracle OfficeQA source page(s). Treat it as the document evidence for this question.

### treasury_bulletin_1982_08.txt page 13
Source URL: https://fraser.stlouisfed.org/title/treasury-bulletin-407/august-1982-7028?page=13

Tenders for the notes totaled $10,102 million, of which $6,001 million was accepted.

| Item | 1981 | 1982 |
| --- | --- | --- |
| Total tenders | 9,455 | 10,102 |
| Accepted | 5,507 | 6,001 |
"""
GOOD = {'values': [{'name': 'total', 'literal': '10,102', 'quote': 'totaled $10,102 million', 'kind': 'data'},
                   {'name': 'accepted', 'literal': '6,001', 'quote': 'of which $6,001 million was accepted', 'kind': 'data'}],
        'answers': [{'expression': 'total - accepted', 'decimals': 0}],
        'mistakes': [{'label': 'wrong_period', 'text': 'the 1981 column', 'values': [
            {'name': 'total', 'literal': '9,455', 'quote': '| Total tenders | 9,455 | 10,102 |'},
            {'name': 'accepted', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |'}],
            'answers': [{'expression': 'total - accepted', 'decimals': 0}]},
            {'label': 'not_a_label', 'text': '', 'values': [], 'answers': []}]}
BAD_QUOTE = {'values': [{**GOOD['values'][0], 'quote': 'totalled 10,102 millions'}, GOOD['values'][1]], 'answers': GOOD['answers']}


def item(task_id, answer, question='By how many million dollars did the tenders exceed the amount accepted in 1982?'):
    return {'benchmark': 'officeqa', 'task_id': task_id, 'family_id': 'officeqa:' + task_id, 'part': 'train',
            'public': {'question': question, 'context': DOC}, 'private': {'answer': answer, 'source_sha256': 'ab' * 32}}


@pytest.fixture
def root():
    base = Path('/tmp/typed3-neutral')
    base.mkdir(exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='bank-', dir=base))
    yield made
    shutil.rmtree(made, ignore_errors=True)


class Fake:
    """A frozen-contract client: ``call(system, user) -> receipt``; ``answer(system, user)`` gives the reply text,
    None for an infrastructure failure."""
    max_tokens = 2048

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def call(self, system, user):
        self.calls.append((system, user))
        text = self.answer(system, user)
        if text is None:
            return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'transport'}
        return {'ok': True, 'response': text, 'finish_reason': 'stop', 'error_type': None,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}


def make_env(root, role=None, solver=None):
    ledger = units.Ledger(root / 'ledger.json', 50_000_000, resume=(root / 'ledger.json').exists())
    return bank_env.BankEnv(root, ledger, {'role': role, 'solver': solver}, width=2)


def test_read_object_is_tolerant():
    assert bank_env.read_object('{"a": 1}') == {'a': 1}
    assert bank_env.read_object('Here it is:\n```json\n{"a": 2}\n```\nDone.') == {'a': 2}
    assert bank_env.read_object('The answer {"a": 3} follows.') == {'a': 3}
    assert bank_env.read_object('[1, 2]') is None and bank_env.read_object('no json') is None


def test_call_is_resumable_and_keeps_infrastructure_failures_open(root):
    replies = iter([None, 'hello'])
    role = Fake(lambda s, u: next(replies))
    env = make_env(root, role)
    first = env.call('officeqa/trace', 'UID1-a1', 'sys', 'user')
    assert first['reply'] is None and first['failure'].startswith('infrastructure:')
    second = env.call('officeqa/trace', 'UID1-a1', 'sys', 'user')            # not final: sent again
    assert second['reply'] == 'hello' and len(role.calls) == 2
    again = env.call('officeqa/trace', 'UID1-a1', 'sys', 'user')             # final: read, not sent
    assert again == second and len(role.calls) == 2
    assert len(units.read_json(root / 'officeqa/trace/calls/UID1-a1.json')) == 2   # both sends are kept
    assert env.ledger.state['sends'] == 2 and not env.ledger.state['pending']


def test_a_stored_reply_is_used_only_for_the_identical_request(root):
    role = Fake(lambda s, u: 'reply to ' + u)
    env = make_env(root, role)
    first = env.call('officeqa/newq', 'UID1-plain', 'sys', 'one')
    assert env.call('officeqa/newq', 'UID1-plain', 'sys', 'one') == first and len(role.calls) == 1
    other = env.call('officeqa/newq', 'UID1-plain', 'sys', 'two')            # the same tag, another request: sent
    assert other['reply'] == 'reply to two' and len(role.calls) == 2
    assert env.call('officeqa/newq', 'UID1-plain', 'sys', 'two') == other and len(role.calls) == 2
    assert env.call('officeqa/newq', 'UID1-plain', 'sys', 'one') == first and len(role.calls) == 2
    stored = sorted(p.name for p in (root / 'officeqa/newq/calls').glob('*.result.json'))
    assert stored == ['UID1-plain-x%s.result.json' % other['request_sha256'][:12], 'UID1-plain.result.json']
    assert env.reused == {'role': 3, 'solver': 0}


def test_carry_lets_a_new_root_rebuild_without_sending_again(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    parents = [item('UID1', '4101')]
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    old, new = root / 'old', root / 'new'
    for folder in (old, new):
        units.write_json(folder / 'bank.json', {'version': 'v', 'code': {'a.py': 'h'}})
    env = make_env(old, role, Fake(lambda s, u: '<answer>4101</answer>'))
    oqa_build.stage_trace(env, parents)
    oqa_build.stage_twins(env, parents, {'UID1': 'shown'})
    units.write_json(old / 'research' / 'officeqa' / 'brief.json', {'shown': {'k': 1}})
    units.write_json(old / 'research' / 'archive' / 'aa.json', {'page': 1})
    before = oqa_build.stage_check(env, tools, parents)
    note = bank_env.carry(old, new)
    assert note['call_files']['officeqa/trace/calls'] == 2 and note['call_files']['research/archive'] == 1
    assert list(note['research_records_carried_as_data']) == ['research/officeqa/brief.json']
    assert not (new / 'officeqa' / 'trace' / 'UID1.json').exists() and not (new / 'officeqa' / 'check' / 'UID1.json').exists()
    refuse = Fake(lambda s, u: 1 / 0)                                         # the new root must not send anything
    env2 = make_env(new, refuse, refuse)
    assert oqa_build.stage_trace(env2, parents) == {'anchored': 1}
    assert oqa_build.stage_twins(env2, parents, {'UID1': 'shown'})['made'] >= 3
    assert oqa_build.stage_check(env2, tools, parents) == before and not refuse.calls
    assert env2.reused['role'] == 1 and env2.reused['solver'] >= 5 and env2.ledger.state['sends'] == 0
    with pytest.raises(AssertionError):
        bank_env.carry(old, new)                                              # once, into a fresh root only


def test_trace_stage_repairs_once_and_is_write_once(root):
    def annotator(system, user):
        payload = json.loads(user)
        if payload['reference_answer'] == 'March 3, 1977':
            return '{"not_numeric": true}'
        if payload['reference_answer'] == '7':
            return json.dumps(GOOD)                                           # computes 4101, never 7
        if 'previous_reply' in payload:
            assert 'not in the document verbatim' in payload['check_failure'] and 'REPAIR' not in system
            return '```json\n' + json.dumps(GOOD) + '\n```'
        return json.dumps(BAD_QUOTE)
    role = Fake(annotator)
    env = make_env(root, role)
    items = [item('UID1', '4,101'), item('UID2', 'March 3, 1977'), item('UID3', '7')]
    assert oqa_build.stage_trace(env, items) == {'anchored': 1, 'dropped': 1, 'not_numeric': 1}
    record = env.read('officeqa', 'trace', 'UID1.json')
    assert [a.get('check') for a in record['attempts']] == ['quote_not_in_document', 'anchored']
    assert record['computed'] == '4101' and [m['label'] for m in record['mistakes']] == ['wrong_period']
    assert [m['label'] for m in record['rubric']['mistakes']] == ['swapped_operands', 'wrong_period']
    assert env.read('officeqa', 'trace', 'UID3.json')['reason'] == 'reference_not_reproduced'
    sent = len(role.calls)
    assert sent == 5 and oqa_build.stage_trace(env, items)['anchored'] == 1 and len(role.calls) == sent


def test_twins_are_pool_shaped_items_with_a_rubric(root):
    env = make_env(root, Fake(lambda s, u: json.dumps(GOOD)))
    parent = item('UID1', '4101')
    oqa_build.stage_trace(env, [parent])
    result = oqa_build.stage_twins(env, [parent], {'UID1': 'judge'})
    assert result['made'] >= 3
    pairs = oqa_build.twins_of(env)
    twins = [twin for twin, _ in pairs]
    prepare.validate_items(twins, 'officeqa')
    assert len({twin['public']['context'] for twin in twins}) == len(twins)
    for twin, record in pairs:
        assert set(twin) == {'benchmark', 'task_id', 'family_id', 'part', 'public', 'private'}
        assert twin['family_id'] == 'officeqa:UID1' and record['side'] == 'judge' and record['parent'] == 'UID1'
        assert twin['public']['question'] == parent['public']['question']
        assert '?page=13' in twin['public']['context'] and '10,102' not in twin['public']['context']
        changes = {c['old']: c['new'] for c in record['changes']}
        gold = oqa.gold_text(oqa.compute_answers(env.read('officeqa', 'trace', 'UID1.json')['trace'], changes))
        assert gold == twin['private']['answer'] != '4101'
        assert backends._score_answer_tag('officeqa', '<answer>%s</answer>' % gold, gold)['status'] == 'pass'
    assert oqa_build.stage_twins(env, [parent], {'UID1': 'judge'})['made'] == result['made']      # nothing rewritten


def test_checker_keeps_confirms_and_drops(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    parents = [item('UID1', '4101'), item('UID2', '4101', question='How much more was tendered than accepted in 1982, in millions?')]
    env = make_env(root, role)
    oqa_build.stage_trace(env, parents)
    oqa_build.stage_twins(env, parents, {'UID1': 'shown', 'UID2': 'judge'})
    golds = {twin['public']['context']: twin['private']['answer'] for twin, _ in oqa_build.twins_of(env)}

    def solver(system, user):
        assert v222_cards.historical_text('officeqa') in system and system.endswith(v222_cards.historical_text('officeqa'))
        view = json.loads(user)
        easy = 'exceed' in view['question']                                   # UID1 is solved, UID2 never
        if view['context'] == DOC:
            return 'So <answer>4101</answer>' if easy else 'I think <answer>4,010</answer>'
        gold = golds[view['context']]
        if not easy:
            return '<answer>1</answer>'
        return '<answer>%s</answer>' % (gold if int(gold) % 2 else '-' + gold)   # even answers: a sign slip, twice
    env = make_env(root, role, Fake(solver))
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    result = oqa_build.stage_check(env, tools, parents)
    assert result['parents'] == {'passes_0': 1, 'passes_2': 1}
    rows = {p.stem: units.read_json(p) for p in (root / 'officeqa' / 'check').glob('*.json')}
    for twin, record in oqa_build.twins_of(env):
        row = rows[oqa_build.safe_id(twin['task_id'])]
        if record['parent'] == 'UID2':
            assert row['status'] == 'unconfirmed' and len(row['runs']) == 1      # no evidence either way: kept
        elif int(twin['private']['answer']) % 2:
            assert row['status'] == 'confirmed' and len(row['runs']) == 1
        else:
            assert row['status'] == 'dropped' and [r['label'] for r in row['runs']] == ['sign', 'sign']
    assert rows['UID2']['runs'][0]['label'] == 'other' and rows['UID1']['runs'][0]['label'] is None
    calls = len(env.clients['solver'].calls)
    assert oqa_build.stage_check(env, tools, parents) == result and len(env.clients['solver'].calls) == calls

    summary = oqa_build.build_report(env, parents, {'UID1': 'shown', 'UID2': 'judge'}, ['UID2'])
    assert summary['trace']['anchored'] == 2 and summary['twins']['made'] == len(golds)
    count = lambda status: sum(r.get('status') == status for r in rows.values())
    # two or more dropped twins of one parent set ALL its twins aside (here: UID1's confirmed ones)
    aside = count('confirmed') if count('dropped') >= oqa_build.TWIN_PARENT_DROPS else 0
    # only CONFIRMED twins qualify (review 2026-11-13); the unconfirmed ones are a diagnostic set, counted apart
    assert count('dropped') >= 1 and summary['twins']['qualified'] == count('confirmed') - aside
    assert summary['twins']['status'].get('dropped_with_parent', 0) == aside
    assert summary['twins']['diagnostic_only'] == count('unconfirmed') > 0
    assert summary['twins']['diagnostic_only_by_side'] == {'judge': count('unconfirmed')}
    assert summary['checker']['first_run_pass_pct']['parents'] == 50.0
    assert summary['checker']['first_run_pass_pct']['twins_of_parents_never_solved'] == 0.0
    assert set(summary['checker']['wrong_reply_labels']) <= {'sign', 'other'}
    assert summary['fidelity']['n_real'] == 2 and summary['ledger']['sends'] > 0


def test_a_twin_reply_that_is_the_parent_answer_is_labelled(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    parent = item('UID1', '4101')
    env = make_env(root, role)
    oqa_build.stage_trace(env, [parent])
    made = oqa_build.stage_twins(env, [parent], {'UID1': 'shown'})['made']
    env = make_env(root, role, Fake(lambda s, u: '<answer>4,101</answer>'))       # the old result, whatever the numbers
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    result = oqa_build.stage_check(env, tools, [parent])
    assert result['parents'] == {'passes_2': 1} and result['twins'] == {'dropped': made}
    summary = oqa_build.build_report(env, [parent], {'UID1': 'shown'}, [])
    assert summary['twins']['qualified'] == 0 and summary['twins']['status'] == {'dropped': made}
    assert summary['checker']['wrong_reply_labels'] == {oqa_build.PARENT_ANSWER: 2 * made}


def test_new_questions_in_two_arms_and_their_verification(root):
    doc_question = {'question': 'By how many million dollars did the amount accepted for the notes rise from 1981 to 1982 '
                                'according to the table of tenders?',
                    'values': [{'name': 'a', 'literal': '6,001', 'quote': '| Accepted | 5,507 | 6,001 |'},
                               {'name': 'b', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |'}],
                    'answers': [{'expression': 'a - b', 'decimals': 0}],
                    'mistakes': [{'label': 'wrong_series', 'text': 'the total tenders rows', 'values': [
                        {'name': 'a', 'literal': '10,102', 'quote': '| Total tenders | 9,455 | 10,102 |'},
                        {'name': 'b', 'literal': '9,455', 'quote': '| Total tenders | 9,455 | 10,102 |'}],
                        'answers': [{'expression': 'a - b', 'decimals': 0}]}]}
    share = {'question': 'What percent of the total tenders for the notes in 1981 was accepted? Round to the nearest tenth of a percent.',
             'values': [{'name': 'a', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |'},
                        {'name': 'b', 'literal': '9,455', 'quote': '| Total tenders | 9,455 | 10,102 |'}],
             'answers': [{'expression': 'a / b * 100', 'decimals': 1}]}
    leak = {**doc_question, 'question': doc_question['question'] + ' It is 494, is it not?'}

    def writer(system, user):
        payload = json.loads(user)
        if 'reference_answer' in payload:
            return json.dumps(GOOD)
        assert payload['about_this_document'] and len(payload['examples']) == 1 and payload['count'] == 3
        if 'brief' in payload:
            assert payload['brief'] == {'mistakes': [{'label': 'wrong_series', 'description': 'd'}]}
            return json.dumps({'items': [doc_question, share, share]})           # the third repeats the second
        return json.dumps({'items': [leak, doc_question]})
    role = Fake(writer)
    parents = [item('UID1', '4101'), item('UID2', '4101', question='How much more was tendered than accepted in 1982, in millions?'),
               item('UID9', '4101', question='A parent that shares a page with an item outside the pool?')]
    sides = {'UID1': 'shown', 'UID2': 'shown', 'UID9': 'judge'}
    env = make_env(root, role)
    oqa_build.stage_trace(env, parents)
    brief = {'mistakes': [{'label': 'wrong_series', 'description': 'd'}]}
    result = oqa_build.stage_newq(env, parents, sides, ['UID9'], ['plain', 'brief'], brief)
    assert result == {'parents': 2, 'results': {'brief: kept 2': 2, 'plain: kept 1': 2}}
    plain_row = env.read('officeqa', 'newq', 'UID1-plain.json')
    assert plain_row['drops'] == ['answer_in_question'] and plain_row['kept'] == ['UID1~qp1']
    assert env.read('officeqa', 'newq', 'UID1-brief.json')['drops'] == ['question_repeats_sibling']
    pairs = oqa_build.made_items(env, 'new_question')
    assert len(pairs) == 6 and not oqa_build.twins_of(env)
    prepare.validate_items([made for made, _ in pairs], 'officeqa')
    made, record = pairs[0]
    assert made['private']['answer'] == '494' and record['mistakes'] == ['wrong_series'] and record['side'] == 'shown'
    assert made['public']['question'] == doc_question['question']                # no percent named: nothing added
    asked = {m['task_id']: m['public']['question'] for m, _ in pairs}
    assert asked['UID1~qb2'] == share['question'] + ' ' + oqa.FORM_SENTENCES[0]  # the form of a percent answer is fixed
    assert [m['label'] for m in record['rubric']['mistakes']] == ['swapped_operands', 'wrong_series']

    def solver(system, user):                                                  # right on differences, wrong on shares
        view = json.loads(user)
        if view['context'] != DOC or 'percent' in view['question']:
            return '<answer>58.24</answer>'                                     # 58.2 is right: two places given
        return '<answer>494</answer>' if 'accepted for the notes rise' in view['question'] else '<answer>4101</answer>'
    env = make_env(root, role, Fake(solver))
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    checked = oqa_build.stage_check(env, tools, parents)
    assert checked['new_questions'] == {'verified': 4, 'unverified': 2}
    row = units.read_json(root / 'officeqa' / 'check' / (oqa_build.safe_id('UID1~qb2') + '.json'))
    assert row['status'] == 'unverified' and [run['label'] for run in row['runs']] == ['rounding', 'rounding']
    summary = oqa_build.build_report(env, parents, sides, ['UID9'])['new_questions']
    assert summary['plain']['kept_by_fixed_checks'] == 2 and summary['plain']['verified'] == 2
    assert summary['brief']['kept_by_fixed_checks'] == 4 and summary['brief']['verified'] == 2
    assert summary['brief']['drop_reasons'] == {'question_repeats_sibling': 2} and summary['brief']['with_coded_mistakes'] == 2
    assert summary['brief']['operations'] == {'div+mul': 2, 'sub': 2} and summary['brief']['wrong_reply_labels'] == {'rounding': 4}


def test_an_unknown_checker_run_leaves_no_record(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    parent = item('UID1', '4101')
    env = make_env(root, role, Fake(lambda s, u: None))
    oqa_build.stage_trace(env, [parent])
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag, 'card': 'card', 'runtime': {}}
    assert oqa_build.stage_check(env, tools, [parent])['parents'] == {'passes_None': 1}
    assert not (root / 'officeqa' / 'check' / 'UID1.json').exists()


def test_prompts_are_two_strings_and_name_the_repair():
    system, user = prompts.trace_request('Q?', '1.8', 'doc')
    assert 'previous_reply' not in user and 'check_failure' not in system
    system, user = prompts.trace_request('Q?', '1.8', 'doc', '{}', prompts.failure_text('expression', 'syntax'))
    assert json.loads(user)['check_failure'] == 'an expression could not be evaluated (syntax).' and 'check_failure' in system
    assert all(label in prompts.TRACE_SYSTEM for label in prompts.MISTAKE_LABELS)


def test_audit_verdict_needs_the_word_and_no_part_marked_wrong():
    ok = {'values': [{'name': 'a', 'right': True, 'why': ''}], 'computation': {'right': True}, 'verdict': 'accept'}
    assert oqa.audit_verdict(ok) == ('accept', [])
    assert oqa.audit_verdict({**ok, 'values': [{'name': 'a', 'right': False}]}) == ('refuse', ['a'])
    assert oqa.audit_verdict({**ok, 'computation': {'right': False}}) == ('refuse', ['computation'])
    assert oqa.audit_verdict({**ok, 'verdict': 'refuse'}) == ('refuse', [])
    assert oqa.audit_verdict({'verdict': 'maybe'}) == ('void', []) and oqa.audit_verdict(None) == ('void', [])


def test_audit_calibrates_on_known_derivations_and_vouches_for_hard_questions(root, monkeypatch):
    monkeypatch.setitem(oqa_build.AUDIT_RULE, 'right_min', 2)                 # the registered size is 30 and 30
    monkeypatch.setitem(oqa_build.AUDIT_RULE, 'wrong_min', 2)
    question = {'question': 'By how many million dollars did the amount accepted for the notes rise from 1981 to 1982 '
                            'according to the table of tenders?',
                'values': [{'name': 'a', 'literal': '6,001', 'quote': '| Accepted | 5,507 | 6,001 |'},
                           {'name': 'b', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |'}],
                'answers': [{'expression': 'a - b', 'decimals': 0}]}

    def role(system, user):
        payload = json.loads(user)
        if system == prompts.AUDIT_SYSTEM:
            assert set(payload) == {'document', 'question', 'derivation'} and 'answer' not in user.replace('"answers"', '')
            assert set(payload['derivation']['values'][0]) == {'name', 'literal', 'quote'}
            used = {value['literal'] for value in payload['derivation']['values']}
            good = used in ({'10,102', '6,001'}, {'6,001', '5,507'})           # the 1981 column is the coded mistake
            return json.dumps({'values': [], 'computation': {'right': good}, 'verdict': 'accept' if good else 'refuse'})
        if 'reference_answer' in payload:
            return json.dumps(GOOD)
        return json.dumps({'items': [question]})
    fake = Fake(role)
    parents = [item('UID1', '4101'), item('UID2', '4101', question='How much more was tendered than accepted in 1982, in millions?')]
    sides = {'UID1': 'shown', 'UID2': 'judge'}
    env = make_env(root, fake, Fake(lambda s, u: '<answer>1</answer>'))        # the checker solves nothing
    oqa_build.stage_trace(env, parents)
    oqa_build.stage_newq(env, parents, sides, [], ['plain'], None)
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    assert oqa_build.stage_check(env, tools, parents)['new_questions'] == {'unverified': 2}
    assert oqa_build.stage_audit(env, parents, 'calibration') == {
        'scope': 'calibration', 'results': {'known right: accepted': 2, 'known wrong: refused': 2}}
    assert oqa_build.stage_audit(env, parents, 'unverified')['results'] == {'new_question: accepted': 2}
    assert oqa_build.stage_audit(env, parents, 'all')['results']['new_question: accepted'] == 2
    sent = len(fake.calls)
    assert oqa_build.stage_audit(env, parents, 'all')['results']['known right: accepted'] == 2 and len(fake.calls) == sent
    summary = oqa_build.build_report(env, parents, sides, [])
    audit = summary['audit']
    assert audit['calibration']['right'] == {'derivations': 2, 'status': {'accepted': 2}, 'accepted_share': 1.0,
                                             'single_run_accept_share': 1.0, 'void_runs': 0}
    assert audit['calibration']['wrong']['accepted_share'] == 0.0 and audit['meets_the_rule'] is True
    assert audit['calibration']['expected'] == 4 and audit['calibration']['missing'] == 0
    assert audit['calibration']['wrong']['accepted_by_label'] == {'wrong_period': '0 of 2'}
    assert audit['new_questions'] == {'plain': {'checker unverified, audit accepted': 2}}
    plain = summary['new_questions']['plain']
    assert plain['verified'] == 0 and plain['final_status'] == {'audited': 2}
    assert plain['final_status_by_side'] == {'shown': {'audited': 1}, 'judge': {'audited': 1}}
    assert 'brief' not in summary['new_questions'] and 'target' not in summary['new_questions']
    # a calibration smaller than registered, or with a record missing, vouches for nothing (review 2026-11-13)
    monkeypatch.setitem(oqa_build.AUDIT_RULE, 'wrong_min', 3)
    small = oqa_build.build_report(env, parents, sides, [])
    assert small['audit']['meets_the_rule'] is False and small['new_questions']['plain']['final_status'] == {'unverified': 2}
    monkeypatch.setitem(oqa_build.AUDIT_RULE, 'wrong_min', 1)                 # so that ONLY the missing record decides
    (root / 'officeqa' / 'audit' / 'cal-UID2-m1.json').unlink()
    cut = oqa_build.audit_report(env, {}, oqa_build.calibration_names(env, parents))
    assert cut['calibration']['wrong']['derivations'] == 1 and cut['calibration']['wrong']['accepted_share'] == 0.0
    assert cut['calibration']['missing'] == 1 and cut['meets_the_rule'] is False
    quiet = make_env(root, Fake(lambda s, u: 1 / 0), Fake(lambda s, u: 1 / 0))   # nothing may be sent for this answer
    assert oqa_build.stage_audit(quiet, parents, 'unverified')['questions'] == 'not audited: the calibration is not complete'


def test_an_audit_that_misses_its_rule_vouches_for_nothing(root, monkeypatch):
    monkeypatch.setitem(oqa_build.AUDIT_RULE, 'right_min', 1)
    monkeypatch.setitem(oqa_build.AUDIT_RULE, 'wrong_min', 1)
    role = Fake(lambda s, u: json.dumps({'verdict': 'accept'}) if s == prompts.AUDIT_SYSTEM else json.dumps(GOOD))
    parents = [item('UID1', '4101')]
    env = make_env(root, role, Fake(lambda s, u: '<answer>1</answer>'))
    oqa_build.stage_trace(env, parents)
    assert oqa_build.stage_audit(env, parents, 'calibration')['results'] == {'known right: accepted': 1, 'known wrong: accepted': 1}
    audit = oqa_build.build_report(env, parents, {'UID1': 'shown'}, [])['audit']
    assert audit['calibration']['wrong']['accepted_share'] == 1.0 and audit['meets_the_rule'] is False
    sent = len(role.calls)                                                    # no question is audited by such an audit
    assert oqa_build.stage_audit(env, parents, 'questions')['questions'] == 'not audited: the calibration does not meet the rule'
    assert len(role.calls) == sent
    fresh = make_env(root / 'fresh', role, Fake(lambda s, u: '<answer>1</answer>'))
    assert oqa_build.stage_audit(fresh, parents, 'unverified')['questions'] == 'not audited: the calibration has not run'
    checks = {'Q~qp1': {'kind': 'new_question', 'status': 'unverified'}, 'Q~qp2': {'kind': 'new_question', 'status': 'verified'}}
    audits = {'Q~qp1': {'status': 'accepted'}, 'Q~qp2': {'status': 'refused'}}
    assert oqa_build.question_statuses(checks, audits, False) == {'Q~qp1': 'unverified', 'Q~qp2': 'verified'}
    assert oqa_build.question_statuses(checks, audits, True) == {'Q~qp1': 'audited', 'Q~qp2': 'verified'}


def test_diagnosis_reads_the_shown_side_only_and_feeds_the_target_arm(root):
    question = {'question': 'By how many million dollars did the amount accepted for the notes rise from 1981 to 1982 '
                            'according to the table of tenders?',
                'values': [{'name': 'a', 'literal': '6,001', 'quote': '| Accepted | 5,507 | 6,001 |'},
                           {'name': 'b', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |'}],
                'answers': [{'expression': 'a - b', 'decimals': 0}], 'targets': 'w1'}
    seen = {'diagnosis': [], 'merge': [], 'target': []}

    def role(system, user):
        payload = json.loads(user)
        if system == prompts.DIAGNOSIS_SYSTEM:
            seen['diagnosis'].append(payload)
            return json.dumps({'cause': 'It took the 1981 column.', 'kind': 'period',
                               'weakness': 'Takes the neighbouring period column.', 'test': 'Name a period that is not the last column.'})
        if system == prompts.MERGE_SYSTEM:
            seen['merge'].append(payload)
            return json.dumps({'weaknesses': [{'kind': 'period', 'weakness': 'Takes the neighbouring period column.',
                                               'test': 'Name a period that is not the last column.', 'cases': [1, 7]},
                                              {'kind': 'x', 'weakness': '', 'test': 'nothing'}]})
        if 'reference_answer' in payload:
            return json.dumps(GOOD)
        if 'weaknesses' in payload:
            assert system == prompts.NEWQ_SYSTEM + prompts.NEWQ_TARGET_NOTE
            seen['target'].append(payload['weaknesses'])
            other = {'question': 'What was the increase in total tenders received for the notes between the two years '
                                 'that the table shows, in millions of dollars?', 'targets': ['w1', 'w9'],
                     'values': [{'name': 'a', 'literal': '10,102', 'quote': '| Total tenders | 9,455 | 10,102 |'},
                                {'name': 'b', 'literal': '9,455', 'quote': '| Total tenders | 9,455 | 10,102 |'}],
                     'answers': [{'expression': 'a - b', 'decimals': 0}]}
            return json.dumps({'items': [question, other]})
        assert system == prompts.NEWQ_SYSTEM
        return json.dumps({'items': []})
    parents = [item('UID1', '4101'), item('UID2', '4101', question='How much more was tendered than accepted in 1982, in millions?'),
               item('UID3', '4101', question='What did the tenders exceed the accepted amount by in 1982, in millions of dollars?')]
    sides = {'UID1': 'shown', 'UID2': 'judge', 'UID3': 'shown'}

    def solver(system, user):                                                  # UID3 is solved, the others never
        return '<answer>4101</answer>' if 'What did the tenders' in json.loads(user)['question'] else 'It is <answer>3948</answer>'
    env = make_env(root, Fake(role), Fake(solver))
    oqa_build.stage_trace(env, parents)
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    oqa_build.stage_check(env, tools, parents)
    result = oqa_build.stage_diagnose(env, parents, sides)
    assert result == {'failed_parents_of_the_shown_side': 1, 'diagnoses': {'diagnosed': 1}, 'merge': 'merged',
                      'weaknesses': [{'id': 'w1', 'kind': 'period', 'cases': 1}]}
    case = seen['diagnosis'][0]                                               # UID1 only: UID2 is the judging side
    assert len(seen['diagnosis']) == 1 and case['reference_answer'] == '4101' and len(case['wrong_replies']) == 2
    assert case['wrong_replies'][0] == {'reply': 'It is <answer>3948</answer>', 'answer_read_by_the_judge': '3948'}
    assert case['derivation_of_the_reference_answer']['answers'] == [{'expression': 'total - accepted', 'decimals': 0}]
    assert seen['merge'][0] == {'cases': [{'case': 1, 'kind': 'period', 'weakness': 'Takes the neighbouring period column.',
                                           'test': 'Name a period that is not the last column.'}]}
    merged = env.read('officeqa', 'diagnosis', 'weaknesses.json')
    assert merged['shown'] == [{'id': 'w1', 'kind': 'period', 'weakness': 'Takes the neighbouring period column.',
                                'test': 'Name a period that is not the last column.'}]
    made = oqa_build.stage_newq(env, parents, sides, [], ['target'], None, merged['shown'])
    assert made == {'parents': 3, 'results': {'target: kept 2': 3}} and seen['target'][0] == merged['shown']
    records = {record['item']: record for _, record in oqa_build.made_items(env, 'new_question')}
    assert records['UID2~qt1']['targets'] == 'w1' and records['UID2~qt2']['targets'] is None   # a list names no weakness
    assert records['UID2~qt1']['side'] == 'judge' and records['UID2~qt1']['arm'] == 'target'
    summary = oqa_build.build_report(env, parents, sides, [])
    assert summary['diagnosis']['kinds'] == {'period': 1} and summary['diagnosis']['merge']['status'] == 'merged'
    assert summary['new_questions']['target']['targets'] == {'w1': 3} and summary['audit'] is None


def test_contrast_measures_a_second_card_on_real_and_made_items(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    parents = [item('UID1', '4101'), item('UID2', '4101', question='How much more was tendered than accepted in 1982, in millions?')]
    sides = {'UID1': 'shown', 'UID2': 'judge'}
    env = make_env(root, role)
    oqa_build.stage_trace(env, parents)
    oqa_build.stage_twins(env, parents, sides)
    golds = {twin['public']['context']: twin['private']['answer'] for twin, _ in oqa_build.twins_of(env)}
    golds[DOC] = '4101'

    def solver(system, user):                                                 # the bare card fails UID2 and its twins
        view = json.loads(user)
        if 'FORMAT ONLY' in system and 'How much more' in view['question']:
            return '<answer>1</answer>'
        return '<answer>%s</answer>' % golds[view['context']]
    env = make_env(root, role, Fake(solver))
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    assert set(oqa_build.stage_check(env, tools, parents)['twins']) == {'confirmed'}
    judged = oqa_build.judged_items(env, parents)
    twins = len(golds) - 1
    assert len(judged) == 2 + twins and [row[1] for row in judged[:2]] == ['parent', 'parent']
    result = oqa_build.stage_contrast(env, tools, parents, 'c0', 'FORMAT ONLY')
    assert result['results']['parent: 2 of 2'] == 1 and result['results']['parent: 0 of 2'] == 1
    calls = len(env.clients['solver'].calls)
    assert oqa_build.stage_contrast(env, tools, parents, 'c0', 'FORMAT ONLY') == result and len(env.clients['solver'].calls) == calls
    with pytest.raises(AssertionError):
        oqa_build.stage_contrast(env, tools, parents, 'c0', 'ANOTHER CARD')   # one card per configuration name
    with pytest.raises(AssertionError):
        oqa_build.stage_contrast(env, tools, parents, 'c0', 'FORMAT ONLY', solver='D')   # and one solver
    summary = oqa_build.contrast_report(env, 'c', 'c0', sides)
    assert summary['solver'] == {'c': 'G', 'c0': 'G'} and summary['same_solver'] is True
    real, made = summary['groups']['real'], summary['groups']['made']
    assert real == {'items': 2, 'parents': 2, 'base_pass_pct': 100.0, 'candidate_pass_pct': 50.0, 'gain_points': -50.0,
                    'better': 0, 'worse': 1, 'gain_interval_95': real['gain_interval_95']}
    assert made['items'] == twins and made['base_pass_pct'] == 100.0 and made['worse'] == sum(
        record['parent'] == 'UID2' for _, record in oqa_build.twins_of(env))
    assert summary['groups']['real, judging side']['gain_points'] == -100.0
    assert summary['groups']['number twins'] == made and 'new questions, plain' not in summary['groups']
    assert abs(summary['instrument']['made_gain_minus_real_gain_points'] - (made['gain_points'] + 50.0)) < 0.011
    assert summary['parents'] == 2 and summary['instrument']['interval_95'] is not None


IDENT = {'runtime_sha256': 'a' * 64, 'code_sha256': 'b' * 64}


def _origins(root, roles):
    """Origins as ``rejudge.require_parity`` returns them ({name: 'base' | 'candidate'}; the parity itself is tested
    below with a run's cells)."""
    step = root / 'run' / 'G' / 's2'
    step.mkdir(parents=True, exist_ok=True)
    return {name: {'step_dir': str(step.absolute()), 'request_identity': IDENT, 'role': role,
                   'unit': 'noharm-t01' if role == 'base' else 'card-r%d' % index}
            for index, (name, role) in enumerate(sorted(roles.items()))}


def _eight_parents(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    parents = [item('UID%d' % n, '4101', question='By how many million dollars did the tenders exceed the amount accepted in 1982? (%d)' % n)
               for n in range(1, 9)]
    sides = {parent['task_id']: 'judge' for parent in parents}
    oqa_build.stage_trace(make_env(root, role), parents)
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    number_of = lambda user: int(json.loads(user)['question'].split('(')[1].rstrip(')'))
    return role, parents, sides, tools, number_of


def test_two_configurations_with_repeats_get_the_chains_gate_rule(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    parents = [item('UID%d' % n, '4101', question='By how many million dollars did the tenders exceed the amount accepted in 1982? (%d)' % n)
               for n in range(1, 9)]
    sides = {parent['task_id']: 'judge' if n % 2 else 'shown' for n, parent in enumerate(parents)}
    env = make_env(root, role)
    oqa_build.stage_trace(env, parents)

    def solver(system, user):                                                 # the better card solves everything
        number = int(json.loads(user)['question'].split('(')[1].rstrip(')'))
        return '<answer>4101</answer>' if 'BETTER' in system or number <= 4 else '<answer>1</answer>'
    env = make_env(root, role, Fake(solver))
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    oqa_build.stage_check(env, tools, parents)
    origins = _origins(root, {'f2': 'base', 'r1': 'candidate'})
    made = oqa_build.stage_contrasts(env, tools, parents, {'f2': 'PLAIN', 'r1': 'BETTER'}, runs=3, side='judge',
                                     sides=sides, origins=origins)
    assert made['results']['f2'] == {'parent: 0 of 3': 2, 'parent: 3 of 3': 2}      # the four judging-side parents only
    with pytest.raises(AssertionError):
        oqa_build.stage_contrasts(env, tools, parents, {'r1': 'BETTER'}, runs=2, side='judge', sides=sides, origins=origins)
    summary = oqa_build.contrast_report(env, 'f2', 'r1', sides, items=parents)
    gate = summary['gate_rule']['real, judging side']
    assert gate['n'] == 4 and gate['repeats'] == 3 and gate['gain_points'] == 50.0 and gate['se_points'] == 0.0
    assert gate['tau_points'] == 3.0 and gate['better'] == 2 and gate['worse'] == 0 and gate['accepted'] is True
    assert gate['parents'] == 4 and 'made, judging side' not in summary['gate_rule']
    assert summary['gate_rule']['real and made, judging side']['n'] == 4
    assert summary['gate_rule']['origin'] == {'step_dir': origins['f2']['step_dir'], 'base_unit': 'noharm-t01',
                                              'candidate_unit': origins['r1']['unit']}
    # only the run's base against a candidate of a card round is decided; never the reverse, never without the pool
    assert 'not the run' in oqa_build.contrast_report(env, 'r1', 'f2', sides, items=parents)['gate_rule']['undecided']
    assert 'not given' in oqa_build.contrast_report(env, 'f2', 'r1', sides)['gate_rule']['undecided']
    assert 'gate_rule' not in oqa_build.contrast_report(env, 'c', 'r1', sides, items=parents)
    plain = oqa_build.stage_contrast(env, tools, parents, 'p3', 'PLAIN THREE', runs=3, side='judge', sides=sides)
    assert plain['results'] == {'parent: 0 of 3': 2, 'parent: 3 of 3': 2}
    assert 'not registered as a re-judging' in oqa_build.contrast_report(env, 'p3', 'r1', sides, items=parents)['gate_rule']['undecided']
    assert oqa_build.gate_statistics({'a': [True]}, {'a': [True]}, ['a']) is None          # one run decides nothing


def test_several_configurations_in_one_stage_meet_each_item_together(root):
    """A base and its candidates are sent item by item (a seeded order per item), never one configuration after the
    other; the records are those of single-configuration stages."""
    role, parents, sides, tools, number_of = _eight_parents(root)
    client = Fake(lambda s, u: '<answer>4101</answer>' if 'BETTER' in s or number_of(u) <= 4 else '<answer>1</answer>')
    ledger = units.Ledger(root / 'ledger.json', 50_000_000, resume=True)
    env = bank_env.BankEnv(root, ledger, {'role': role, 'solver': client}, width=1)      # one thread: a fixed order
    oqa_build.stage_check(env, tools, parents)
    before = len(client.calls)
    cards = {'b1': 'PLAIN', 'k1': 'BETTER', 'k2': 'BETTER TWO'}
    origins = _origins(root, {'b1': 'base', 'k1': 'candidate', 'k2': 'candidate'})
    out = oqa_build.stage_contrasts(env, tools, parents, cards, runs=2, side='judge', sides=sides, origins=origins)
    assert out['results'] == {'b1': {'parent: 0 of 2': 4, 'parent: 2 of 2': 4}, 'k1': {'parent: 2 of 2': 8},
                              'k2': {'parent: 2 of 2': 8}}
    assert out['configurations'] == {name: bank_env.text_sha256(text) for name, text in cards.items()}
    sent = [(number_of(user), 'k2' if 'BETTER TWO' in system else 'k1' if 'BETTER' in system else 'b1')
            for system, user in client.calls[before:]]
    assert len(sent) == 48 and sorted({n for n, _ in sent[6 * i:6 * i + 6]} for i in range(8)) == [{n} for n in range(1, 9)]
    orders = {tuple(config for _, config in sent[6 * i:6 * i + 6:2]) for i in range(8)}
    assert len(orders) > 1 and all(sorted(order) == ['b1', 'k1', 'k2'] for order in orders)
    again = oqa_build.stage_contrasts(env, tools, parents, {'k1': 'BETTER'}, runs=2, side='judge', sides=sides, origins=origins)
    assert again['results']['k1'] == out['results']['k1'] and len(client.calls) == before + 48     # read, not sent
    gate = oqa_build.contrast_report(env, 'b1', 'k1', sides, items=parents)['gate_rule']['real, judging side']
    assert gate['n'] == 8 and gate['better'] == 4 and gate['worse'] == 0 and gate['accepted'] is True
    assert 'not the run' in oqa_build.contrast_report(env, 'k1', 'k2', sides, items=parents)['gate_rule']['undecided']
    with pytest.raises(AssertionError):
        oqa_build.stage_contrasts(env, tools, parents, {'c': 'PLAIN'}, runs=2)               # 'c' is the checker
    with pytest.raises(AssertionError):
        oqa_build.stage_contrasts(env, tools, parents, {'k1': 'ANOTHER'}, runs=2, side='judge', sides=sides, origins=origins)
    with pytest.raises(AssertionError, match='registered with another'):                    # the origin is identity too
        oqa_build.stage_contrasts(env, tools, parents, {'k1': 'BETTER'}, runs=2, side='judge', sides=sides)


def test_a_contrast_configuration_is_bound_before_any_call_and_decides_only_when_complete(root):
    """Review 2026-11-14 (the same defects on this path): an item left open must not be computed under another card
    when the stage is run again under the same name, and the gate rule is not decided while a registered item has
    no record (it must not drop out of the judged population)."""
    from skillopt.execskill.typed.bank import rejudge
    role, parents, sides, tools, number_of = _eight_parents(root)
    state = {'down': True}

    def solver(system, user):
        if state['down'] and number_of(user) == 1 and 'BETTER' in system:
            return None                                                      # the candidate's first item stays open
        return '<answer>4101</answer>' if 'BETTER' in system or number_of(user) <= 4 else '<answer>1</answer>'
    client = Fake(solver)
    ledger = units.Ledger(root / 'ledger.json', 50_000_000, resume=True)
    env = bank_env.BankEnv(root, ledger, {'role': role, 'solver': client}, width=1)
    oqa_build.stage_check(env, tools, parents)
    cards = {'b1': 'PLAIN', 'k1': 'BETTER'}
    origins = _origins(root, {'b1': 'base', 'k1': 'candidate', 'k2': 'candidate'})
    run = lambda which, **kw: oqa_build.stage_contrasts(env, tools, parents, which, side='judge', sides=sides,
                                                        origins=origins, **kw)
    out = run(cards, runs=2)
    assert out['results']['k1'] == {'parent: 2 of 2': 7, 'unknown': 1}
    record = rejudge.registered(env, 'officeqa', oqa_build.CONTRAST_KIND, 'k1')
    assert record['items'] == [p['task_id'] for p in parents] and record['runs'] == 2 and record['side'] == 'judge'
    assert record['origin'] == origins['k1']
    summary = oqa_build.contrast_report(env, 'b1', 'k1', sides, items=parents)
    assert summary['gate_rule'] == {'undecided': 'records are missing: 8 and 7 of 8 items'}
    state['down'] = False
    sent = len(client.calls)
    for bad, kwargs, word in (({'k1': 'BETTER STILL'}, {'runs': 2}, 'another card'), ({'k1': 'BETTER'}, {'runs': 3}, 'another'),
                              ({'k1': 'BETTER'}, {'runs': 2, 'solver': 'D'}, 'another')):
        with pytest.raises(AssertionError, match=word):
            run(bad, **kwargs)
        assert len(client.calls) == sent and not env.exists('officeqa', 'contrast-k1', 'UID1.json')   # nothing sent or written
    run(cards, runs=2)
    gate = oqa_build.contrast_report(env, 'b1', 'k1', sides, items=parents)['gate_rule']['real, judging side']
    assert gate['n'] == 8 and gate['better'] == 4 and gate['worse'] == 0 and gate['accepted'] is True
    # another run count under a second name: no decision between the two
    run({'k2': 'BETTER TWO'}, runs=3)
    assert 'differ' in oqa_build.contrast_report(env, 'b1', 'k2', sides, items=parents)['gate_rule']['undecided']
    # the judged items of now are not the registered ones (review, second round: an item that lost its status must not
    # stay in the judged population): no decision, and the stage refuses to go on under the old names
    fewer = parents[:6]
    assert 'judged items changed' in oqa_build.contrast_report(env, 'b1', 'k1', sides, items=fewer)['gate_rule']['undecided']
    sent = len(client.calls)
    with pytest.raises(AssertionError, match='judged items changed'):
        oqa_build.stage_contrasts(env, tools, fewer, cards, runs=2, side='judge', sides=sides, origins=origins)
    with pytest.raises(AssertionError, match='judged items changed'):
        oqa_build.stage_contrasts(env, tools, parents + [item('UID9', '4101')], cards, runs=2, side='judge',
                                  sides={**sides, 'UID9': 'judge'}, origins=origins)
    assert len(client.calls) == sent
    # a record of another identity in a configuration's folder is refused by the report
    path = root / 'officeqa' / 'contrast-k1' / 'UID2.json'
    row = units.read_json(path)
    units.write_json(path, {**row, 'card_sha256': 'e' * 64})
    with pytest.raises(AssertionError, match='another card'):
        oqa_build.contrast_report(env, 'b1', 'k1', sides, items=parents)


def test_records_made_before_registration_are_checked_before_any_call(root):
    """Review 2026-11-14 (second round): a configuration folder without a registration (made by earlier code), holding
    a record with another number of runs than the stage would make, stops the stage before it sends anything."""
    role, parents, sides, tools, number_of = _eight_parents(root)
    client = Fake(lambda s, u: '<answer>4101</answer>')
    ledger = units.Ledger(root / 'ledger.json', 50_000_000, resume=True)
    env = bank_env.BankEnv(root, ledger, {'role': role, 'solver': client}, width=1)
    oqa_build.stage_check(env, tools, parents)
    sha = bank_env.text_sha256('FORMAT ONLY')
    legacy = lambda name, runs: units.write_json(root / 'officeqa' / 'contrast-c0' / (name + '.json'), {
        'id': name, 'kind': 'parent', 'parent': name, 'arm': None, 'config': 'c0', 'card_sha256': sha, 'solver': 'G',
        'runs': [{'verdict': 'pass', 'answer': '4101', 'label': None}] * runs, 'passes': runs})
    legacy('UID2', 3)                                                         # the default is two runs per parent
    sent = len(client.calls)
    with pytest.raises(AssertionError, match='another number of runs'):
        oqa_build.stage_contrast(env, tools, parents, 'c0', 'FORMAT ONLY')
    assert len(client.calls) == sent and not env.exists('officeqa', 'contrast-c0.json')
    legacy('UID2', 2)
    legacy('UID77', 2)                                                        # a record of an item that is not judged
    with pytest.raises(AssertionError, match='outside its items'):
        oqa_build.stage_contrast(env, tools, parents, 'c0', 'FORMAT ONLY')
    assert len(client.calls) == sent
    (root / 'officeqa' / 'contrast-c0' / 'UID77.json').unlink()
    done = oqa_build.stage_contrast(env, tools, parents, 'c0', 'FORMAT ONLY')
    assert done['results'] == {'parent: 2 of 2': 8} and len(client.calls) == sent + 14     # UID2 is read, not sent


def test_contrast_parity_compares_the_bank_requests_with_a_runs_cells(root):
    """B26 step 1: for the run's gate items, the request the bank builds under a card is the request the run's cell
    sent with that card FROM THE CARD'S OWN SOURCE (the base: the unit the step's gate compared against; a
    candidate: the round whose writer wrote the text); the re-judging stage runs only with the passing record."""
    from skillopt.execskill.typed import mount
    from skillopt.execskill.typed.bank import rejudge
    role, parents, sides, tools, number_of = _eight_parents(root)
    base_text, cand_text, late_text = 'Read the header row twice.\n', 'Check the period of every figure.\n', 'Sum twice.\n'
    system = lambda text: mount.system_card('officeqa', text, base_card='historical')
    tools = {**tools, 'system_card': system}
    step = root / 'run' / 'G' / 's2'
    reply = {'ok': True, 'response': '<answer>4101</answer>', 'finish_reason': 'stop', 'usage': {}, 'error_type': None}
    runtime = {'officeqa': tools['runtime']}
    for unit, text in (('card-r1', cand_text), ('card-r2', late_text)):
        units.write_json(step / unit / 'writer.json', {'text': text})
    for n, parent in enumerate(parents):
        for unit, label, text in (('noharm-t01', 'F#1', base_text), ('card-r1', 'cand_card#1', cand_text),
                                  ('card-r2', 'cand_card#1', late_text)):
            mounted = mount.mount('officeqa', parent, arm='C', typemap=None, library=None, vector=None, runtime=runtime)
            card = system(text) if n < 6 else mount.historical_card('officeqa')       # the run routed six of eight
            mounted.update({'system_card': card, 'system_card_sha256': units.sha256_text(card)})
            tag = units.cell_tag('officeqa', parent['task_id'], label)
            row = mount.solve('officeqa', parent, mounted, call=lambda s, u: reply, runtime=runtime, unit='s2/' + unit,
                              tag=tag, scorer_root=None, mode='run')
            units.write_json(step / unit / 'cells' / (tag + '.json'), {**row, 'arm': label})
    client = Fake(lambda s, u: '<answer>4101</answer>')
    env = make_env(root, role, client)
    oqa_build.stage_check(env, tools, parents)
    checked = len(client.calls)
    texts = {'gb': base_text, 'gr1': cand_text}
    parity = lambda cards, **kw: oqa_build.stage_parity(env, tools, parents, cards, step, IDENT,
                                                        **{'base': 'gb', 'base_unit': 'noharm-t01', **kw})
    out = parity(texts)
    assert out['ok'] is True and env.read('officeqa', 'contrast-parity.json') == out
    for name, unit in (('gb', 'noharm-t01'), ('gr1', 'card-r1')):
        row = out['configurations'][name]
        assert (row['gate_items'], row['same_request'], row['different'], row['no_run_cell_with_this_card']) == (8, 6, 0, 2)
        assert row['source']['unit'] == unit
    assert len(client.calls) == checked                                          # nothing was sent
    rejudge_stage = lambda cards, **kw: oqa_build.stage_rejudge(env, tools, parents, cards, **{
        'runs': 2, 'side': 'judge', 'sides': sides, 'step_dir': step, 'identity': IDENT, **kw})
    done = rejudge_stage(texts)
    assert done['results'] == {'gb': {'parent: 2 of 2': 8}, 'gr1': {'parent: 2 of 2': 8}} and len(client.calls) == checked + 32
    assert all(any(s.endswith(system(text)) for s, _ in client.calls[checked:]) for text in texts.values())   # verbatim
    record = rejudge.registered(env, 'officeqa', oqa_build.CONTRAST_KIND, 'gr1')
    assert record['origin'] == {'step_dir': str(step.absolute()), 'request_identity': IDENT, 'role': 'candidate', 'unit': 'card-r1'}
    assert oqa_build.contrast_report(env, 'gb', 'gr1', sides, items=parents)['gate_rule']['real, judging side']['n'] == 8
    # what must NOT pass (review, second round), each refused before any request:
    sent = len(client.calls)
    # (a) another round's candidate offered as the base: the base unit's cells never sent that card
    wrong_base = parity({'gb': cand_text, 'gr1': late_text})
    assert wrong_base['ok'] is False and wrong_base['configurations']['gb']['same_request'] == 0
    with pytest.raises(AssertionError, match='differs from the run'):
        rejudge_stage({'gb': cand_text, 'gr1': late_text})
    # (b) a stripped text is no round's text; (c) a card round named as the base unit; (d) no base among the cards
    assert parity({'gb': base_text, 'gr1': cand_text.strip()})['configurations']['gr1']['source'] is None
    with pytest.raises(AssertionError):
        parity(texts, base_unit='card-r1')
    with pytest.raises(AssertionError):
        parity({'gr1': cand_text})
    # (e) the passing record of these cards does not cover others, another step, or another request identity
    assert parity(texts)['ok'] is True
    for cards, kw, word in (({'gb': base_text, 'gr2': late_text}, {}, 'did not cover'),
                            ({'gb': base_text, 'gr1': late_text}, {}, 'did not cover'),
                            (texts, {'identity': {**IDENT, 'code_sha256': 'c' * 64}}, 'another runtime or code'),
                            (texts, {'runs': 1}, 'R >= 2'), (texts, {'side': None}, 'judging side')):
        with pytest.raises(AssertionError, match=word):
            rejudge_stage(cards, **kw)
    (root / 'run' / 'G' / 's3').mkdir()
    with pytest.raises(AssertionError, match='another learning step'):
        rejudge_stage(texts, step_dir=root / 'run' / 'G' / 's3')
    (root / 'officeqa' / 'contrast-parity.json').unlink()
    with pytest.raises(AssertionError, match='parity check first'):
        rejudge_stage(texts)
    assert len(client.calls) == sent


def test_a_ledger_stop_ends_a_stage_and_is_never_a_task_result(root):
    role = Fake(lambda s, u: json.dumps(GOOD))
    ledger = units.Ledger(root / 'ledger.json', 10)                           # far below one request
    env = bank_env.BankEnv(root, ledger, {'role': role, 'solver': None}, width=2)
    with pytest.raises(units.Stop):
        oqa_build.stage_trace(env, [item('UID1', '4101'), item('UID2', '4101')])
    assert not role.calls and not (root / 'officeqa' / 'trace' / 'UID1.json').exists()


def test_a_cut_checker_reply_is_a_final_wrong_run_and_is_not_drawn_again(root):
    class Cut(Fake):
        def call(self, system, user):
            self.calls.append((system, user))
            return {'ok': True, 'response': 'The answer is', 'finish_reason': 'length', 'error_type': None,
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
    role = Fake(lambda s, u: json.dumps(GOOD))
    parent = item('UID1', '4101')
    solver = Cut(None)
    env = make_env(root, role, solver)
    oqa_build.stage_trace(env, [parent])
    tools = {'solve': backends.solve, 'score': backends._score_answer_tag,
             'card': v222_cards.historical_text('officeqa'), 'runtime': {'prompt_layout': 'contract-first-v2'}}
    result = oqa_build.stage_check(env, tools, [parent])
    assert result['parents'] == {'passes_0': 1}
    row = env.read('officeqa', 'check', 'UID1.json')
    assert [(run['verdict'], run['label']) for run in row['runs']] == [('fail', oqa_build.NO_REPLY)] * 2
    sent = len(solver.calls)
    (root / 'officeqa' / 'check' / 'UID1.json').unlink()                      # as if the stage had been interrupted
    assert oqa_build.stage_check(env, tools, [parent]) == result and len(solver.calls) == sent
    assert env.reused['solver'] >= 2


def test_a_delivered_role_call_without_its_result_file_is_not_sent_again(root):
    role = Fake(lambda s, u: 'reply %d' % (len(role.calls)))
    env = make_env(root, role)
    first = env.call('officeqa/newq', 'UID1-plain', 'sys', 'one')
    (root / 'officeqa/newq/calls/UID1-plain.result.json').unlink()            # the process ended between the two writes
    again = env.call('officeqa/newq', 'UID1-plain', 'sys', 'one')
    assert again == first and len(role.calls) == 1 and env.reused['role'] == 1
    assert (root / 'officeqa/newq/calls/UID1-plain.result.json').exists()
