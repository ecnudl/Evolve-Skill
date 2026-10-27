"""v2.9.3 whole-envelope retries and frozen parent behavior, entirely offline."""
import json
from pathlib import Path

import pytest

from skillopt.execskill import (audit, engineer as e, engineer_reader as reader, engineer_v28,
                               engineer_v29, engineer_v291, engineer_v292, engineer_v293, profiles as p)
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v291_engineer import run, GOOD, ALF_GOOD
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


CHILDREN = ('alfworld-v7', 'zebra-pc-v10')
PARENTS = {'alfworld-v7': 'alfworld-v6', 'zebra-pc-v10': 'zebra-pc-v9'}
REPLIES = {row['label']: row['reply'] for row in json.loads(
    (Path(__file__).parent / 'fixtures/execskill/alf6_s3b_replies.json').read_text())}
IDS = ['alf_progress_tracker', 'alf_task_planner']


def ctx(configuration='alfworld-v7'):
    return context(configuration=configuration, bench=p.active_benches(configuration)[0])[0]


def entry(configuration, identity='wanted', **values):
    return {'kind': 'new', 'id': identity,
            'source': ALF_GOOD if p.is_alfworld(configuration) else GOOD, **values}


def encoded(entries):
    return engineer_reply({'changes': entries}, [])


def scripted_retry(monkeypatch, current, answer):
    calls = []
    def ask(actual, request, purpose):
        assert actual is current
        calls.append((request, purpose))
        assert len(calls) == 1, 'The envelope retry is already spent'
        return answer, 'b' * 64
    monkeypatch.setattr(e, '_ask', ask)
    return calls


def test_real_alf_proposal_keeps_both_changes_and_makes_no_retry(monkeypatch):
    current = ctx()
    rows = reader.read(REPLIES['propose'], current)
    assert [row['original']['id'] for row in rows] == IDS
    assert [reader.defined_hooks(row['source']) for row in rows] == [
        ['alf_before_step', 'alf_after_step'], ['applies', 'alf_before_step']]
    def no_retry(*args, **kwargs):
        pytest.fail('The real proposal has one changes object and needs no retry')
    monkeypatch.setattr(e, '_ask', no_retry)
    changes, failures = engineer_v28.read_call(current, REPLIES['propose'], 'a' * 64, 'propose')
    assert not failures and len(changes) == 2 and 'format_retries' not in current.sheet
    assert [change.source for change in changes] == [row['source'] for row in rows]
    repair = {'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': 1}
    assert all(repair in change.repairs for change in changes)


def test_real_retry_returns_both_changes_when_original_envelope_is_unreadable(monkeypatch):
    current = ctx()
    calls = scripted_retry(monkeypatch, current, REPLIES['format-retry/propose'])
    changes, failures = engineer_v28.read_call(current, 'unreadable envelope', 'a' * 64, 'propose')
    rows = reader.read(REPLIES['format-retry/propose'], current)
    assert [row['original']['id'] for row in rows] == IDS
    assert not failures and len(changes) == 2 and len(calls) == 1
    assert [change.source for change in changes] == [row['source'] for row in rows]
    event = current.sheet['format_retries'][0]
    assert event['selected_by'] == 'envelope' and event['reply_change_count'] == 2 and event['parsed']
    assert calls[0][0]['change_index'] is None and calls[0][1] == 'format-retry/propose'
    assert calls[0][0]['instruction'] == engineer_v293.FORMAT_RETRY_SYSTEM


@pytest.mark.parametrize('configuration', ('alfworld-v6', 'alfworld-v5'))
def test_real_older_envelope_and_retry_behavior_stays_exact(monkeypatch, configuration):
    current = ctx(configuration)
    with pytest.raises(reader.Unusable, match='^expected one manifest object, found 2$'):
        reader.read(REPLIES['propose'], current)
    calls = scripted_retry(monkeypatch, current, REPLIES['format-retry/propose'])
    changes, failures = engineer_v28.read_call(current, REPLIES['propose'], 'a' * 64, 'propose')
    event, request = current.sheet['format_retries'][0], calls[0][0]
    if configuration == 'alfworld-v6':
        assert changes == [] and len(failures) == 1
        assert failures[0]['detail'] == 'expected one manifest object, found 2'
        assert event['reason'] == 'format retry must contain exactly the requested change'
        assert event['reply_change_count'] == 2 and 'selected_by' not in event and not event['parsed']
        assert request['instruction'] == engineer_v292.FORMAT_RETRY_SYSTEM
        assert set(request) == {'request', 'instruction', 'schema', 'parse_problem', 'previous_reply',
                                'change_index', 'change_count'}
    else:
        assert len(changes) == 2 and failures == [] and event['parsed']
        assert set(event) == {'purpose', 'call', 'parse_problem', 'parsed'}
        assert request['instruction'] == engineer_v28.FORMAT_RETRY_SYSTEM
        assert set(request) == {'request', 'instruction', 'schema', 'parse_problem', 'previous_reply', 'change_index'}


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('count', (1, 2, 3))
def test_whole_envelope_retry_accepts_one_to_max_changes_without_selection(monkeypatch, configuration, count):
    current = ctx(configuration)
    calls = scripted_retry(monkeypatch, current, encoded([entry(configuration, str(n)) for n in range(count)]))
    changes, failures = engineer_v28.read_call(current, 'not an envelope', 'a' * 64, 'propose')
    assert not failures and [change.n for change in changes] == list(range(1, count + 1))
    assert all(change.call == 'b' * 64 for change in changes) and len(calls) == 1
    event = current.sheet['format_retries'][0]
    assert event['parsed'] and event['selected_by'] == 'envelope' and event['reply_change_count'] == count
    assert calls[0][0]['change_index'] is None and calls[0][0]['change_count'] is None


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('count', (0, 4))
def test_whole_envelope_retry_refuses_empty_or_oversized_proposal_and_records_count(monkeypatch, configuration, count):
    current = ctx(configuration)
    scripted_retry(monkeypatch, current, encoded([entry(configuration, str(n)) for n in range(count)]))
    changes, failures = engineer_v28.read_call(current, 'unreadable', 'a' * 64, 'propose')
    assert not changes and len(failures) == 1
    event = current.sheet['format_retries'][0]
    assert not event['parsed'] and event['selected_by'] == 'envelope' and event['reply_change_count'] == count
    assert event['reason'] == ('format retry must contain at least one change' if count == 0 else
                               'changes count 4 exceeds 3')


@pytest.mark.parametrize('configuration', CHILDREN)
def test_unreadable_retry_records_unknown_reply_count_without_another_call(monkeypatch, configuration):
    current = ctx(configuration)
    scripted_retry(monkeypatch, current, 'also unreadable')
    changes, failures = engineer_v28.read_call(current, 'unreadable', 'a' * 64, 'propose')
    assert not changes and len(failures) == 1
    event = current.sheet['format_retries'][0]
    assert event['selected_by'] == 'envelope' and event['reply_change_count'] is None and not event['parsed']


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('all_bad', (False, True))
def test_broken_retry_change_is_a_failure_and_spends_no_further_retry(monkeypatch, configuration, all_bad):
    current = ctx(configuration)
    bad = {'kind': 'new', 'id': 'broken', 'code': entry(configuration)['source'], 'state_bytes': []}
    entries = [bad] if all_bad else [entry(configuration, 'first'), bad, entry(configuration, 'last')]
    calls = scripted_retry(monkeypatch, current, encoded(entries))
    changes, failures = engineer_v28.read_call(current, 'unreadable envelope', 'a' * 64, 'propose')
    assert [change.n for change in changes] == ([] if all_bad else [1, 3])
    assert len(calls) == len(failures) == 1
    failure = failures[0]
    assert set(failure) == {'n', 'reason', 'detail', 'repairs'}
    assert failure['n'] == (1 if all_bad else 2) and failure['reason'] == 'unparseable'
    assert failure['detail'] == '$.state_bytes must have type int, got list'
    assert {'rule': 'inline_code_alias', 'path': '$.code', 'to': '$.source'} in failure['repairs']
    event = current.sheet['format_retries'][0]
    assert event['parsed'] and event['selected_by'] == 'envelope' and event['reply_change_count'] == len(entries)


@pytest.mark.parametrize('configuration', CHILDREN)
def test_ordinary_bad_change_still_has_its_one_selected_retry(monkeypatch, configuration):
    current = ctx(configuration)
    original = encoded([entry(configuration, state_bytes=[]), entry(configuration, 'other')])
    answer = encoded([{'kind': 'unknown', 'id': 'other'}, entry(configuration)])
    calls = scripted_retry(monkeypatch, current, answer)
    changes, failures = engineer_v28.read_call(current, original, 'a' * 64, 'propose')
    assert not failures and [change.n for change in changes] == [1, 2]
    assert [change.call for change in changes] == ['b' * 64, 'a' * 64]
    event, request = current.sheet['format_retries'][0], calls[0][0]
    assert event['selected_by'] == 'id' and event['reply_change_count'] == 2
    assert request['change_index'] == 1 and request['change_count'] == 2 and request['change_id'] == 'wanted'


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('purpose', ('fix/2/1', 'audit-fix/2', 'fault-repair/2/1'))
def test_fix_retries_keep_selected_change_and_ignore_bad_sibling(monkeypatch, configuration, purpose):
    current = ctx(configuration)
    original = e.Change(2, 'new', {'kind': 'new', 'id': 'wanted'}, entry(configuration)['source'], 'a' * 64)
    calls = scripted_retry(monkeypatch, current, encoded([{'kind': 'unknown'}, entry(configuration)]))
    changes, failures = engineer_v28.read_call(current, 'unreadable fix', 'a' * 64, purpose, change=original)
    assert not failures and len(changes) == 1 and changes[0].n == 2
    assert changes[0].source == original.source
    event, request = current.sheet['format_retries'][0], calls[0][0]
    assert event['selected_by'] == 'id' and event['reply_change_count'] == 2
    assert request['change_index'] == 2 and request['change_id'] == 'wanted'
    assert request['change'] == dict(original.entry, source=original.source)


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('identified', (False, True))
def test_per_change_selection_is_identical_to_v292_parent(monkeypatch, configuration, identified):
    entries = [entry(configuration, 'other'), entry(configuration)]
    if not identified:
        for value in entries:
            value.pop('id')
    answer = encoded(entries)
    found = []
    for config in (PARENTS[configuration], configuration):
        current = ctx(config)
        calls = scripted_retry(monkeypatch, current, answer)
        rows, call = engineer_v28._retry(current, 'bad', 'parse problem', 'propose/2', index=2,
            change_count=2, change_id='wanted' if identified else None)
        found.append((rows, current.sheet['format_retries'][0], calls[0][0]))
    assert found[0][0] == found[1][0] and found[0][1] == found[1][1]
    assert found[1][1]['selected_by'] == ('id' if identified else 'position')
    expected = dict(found[0][2], instruction=engineer_v293.FORMAT_RETRY_SYSTEM)
    assert found[1][2] == expected


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('mode', ('single', 'train'))
def test_actual_engineer_record_and_format_retry_wire_use_v293_pins(configuration, mode):
    good = ALF_GOOD if p.is_alfworld(configuration) else GOOD
    current, package, record = run(None, good, configuration=configuration, mode=mode)
    assert package is not None and record['version'] == p.kind('engineer-v2-9-3')
    prompt = engineer_v293.system(configuration, train=mode == 'train')
    assert prompt == engineer_v292.system(PARENTS[configuration], train=mode == 'train').replace('(v2.9.2)', '(v2.9.3)')
    assert record['prompt_sha256'] == audit.text_sha256(prompt)
    event = record['format_retries'][0]
    assert event['selected_by'] == 'envelope' and event['reply_change_count'] == 1
    wire = next(row for row in current.roles.wire if '/format-retry/' in row['label'])
    assert wire['system'] == prompt + engineer_v293.FORMAT_RETRY_SYSTEM
    assert json.loads(wire['user'])['instruction'] == engineer_v293.FORMAT_RETRY_SYSTEM


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('mode', ('single', 'train'))
def test_inherited_fault_repair_uses_v293_system_and_unchanged_fault_instruction(configuration, mode):
    hook = 'alf_before_step' if p.is_alfworld(configuration) else 'before_call'
    good = ALF_GOOD if p.is_alfworld(configuration) else GOOD
    bad = 'def %s(view, state):\n    return 3\n' % hook
    current, package, record = run(bad, good, configuration=configuration, mode=mode)
    assert package is not None and record['fault_repair_calls'] == 1
    wire = next(row for row in current.roles.wire if '/fault-repair/' in row['label'])
    assert wire['system'] == engineer_v293.system(configuration, train=mode == 'train') + engineer_v291.FAULT_REPAIR_INSTRUCTION
    assert record['changes'][0]['fault_repair']['calls'][0]['request']['instruction'] == engineer_v291.FAULT_REPAIR_INSTRUCTION


def test_new_retry_instruction_and_all_prompt_hashes_are_pinned():
    text = engineer_v293.FORMAT_RETRY_SYSTEM
    assert text.startswith('When `change_index` is null, the whole reply could not be read:')
    assert 'every change (at most 3, with each change\'s replay tests inside that change)' in text
    assert 'one Python block per change in manifest order' in text
    assert 'Otherwise, return only the change at `change_index` (identified by `change_id` when given)' in text
    assert text.endswith(engineer_v29.SHORT_POLICY)
    pins = engineer_v293.prompt_pins()
    assert pins['format_retry']['text'] == text
    assert all(audit.text_sha256(row['text']) == row['sha256'] for row in pins.values())
