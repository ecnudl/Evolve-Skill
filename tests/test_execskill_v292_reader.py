"""Offline reader regressions, including the unchanged real zebra-pc-v8 replies."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer as e, engineer_reader as reader, engineer_v28, engineer_v292, profiles as p
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import GOOD, context


REPLIES = {row['label'].split('/engineer-r1/')[1]: row['reply'] for row in json.loads(
    (Path(__file__).parent / 'fixtures' / 'execskill' / 'zpc8_r1_replies.json').read_text())}
IDS = ('zebra-solver-v1', 'zebra-clue-digest-v1')


def ctx(configuration=p.ZEBRA_PC_V9):
    return context(configuration=configuration)[0]


def reply(entries):
    return engineer_reply({'changes': entries}, [])


def entry(identity='wanted', **values):
    return {'kind': 'new', 'id': identity, 'source': GOOD, **values}


def retry(monkeypatch, fixed, *, index=1, count=2, identity='wanted', configuration=p.ZEBRA_PC_V9, change=None):
    current, requests = ctx(configuration), []
    def ask(context, request, purpose):
        requests.append((request, purpose))
        return fixed, 'b' * 64
    monkeypatch.setattr(e, '_ask', ask)
    result, call = engineer_v28._retry(current, 'original reply', 'original error', 'propose/%d' % index,
        change=change, index=index, change_count=count, change_id=identity)
    return result, current.sheet['format_retries'][-1], requests[0][0]


def without_ids(text):
    match = next(match for match in reader.FENCE.finditer(text) if match.group(2).strip() == 'json')
    manifest, _ = reader.tolerant_json(match.group(3))
    for value in manifest['changes']:
        value.pop('id', None)
        value.pop('revises', None)
    return text[:match.start(3)] + json.dumps(manifest) + '\n' + text[match.end(3):]


def test_real_proposal_recovers_both_unchanged_programs_and_written_ids():
    result = reader.read(REPLIES['propose'], ctx())
    assert [row['original']['id'] for row in result] == list(IDS)
    for row in result:
        assert row['error'] is None and row['source']
        assert 'before_call' in reader.defined_hooks(row['source'])
        original = row['original']['code']
        assert row['source'] == reader.FENCE.fullmatch(original.strip()).group(3)
        assert {'inline_code_alias', 'inline_source_unfenced'} <= {v['rule'] for v in row['repairs']}
        # New procedure ids remain host-assigned; raw ids are selection metadata.
        assert 'id' not in row['entry'] and 'code' not in row['entry']


@pytest.mark.parametrize('label', ['format-retry/propose/1', 'format-retry/propose/2'])
@pytest.mark.parametrize('index', [1, 2])
@pytest.mark.parametrize('by_id', [True, False])
def test_real_retry_selects_each_requested_program_by_raw_id_or_position(monkeypatch, label, index, by_id):
    fixed = REPLIES[label] if by_id else without_ids(REPLIES[label])
    result, event, request = retry(monkeypatch, fixed, index=index, identity=IDS[index - 1])
    assert len(result) == 1 and result[0]['error'] is None
    baseline = reader.read(REPLIES[label], ctx())[index - 1]
    assert result[0]['source'] == baseline['source']
    assert 'before_call' in reader.defined_hooks(result[0]['source'])
    assert event['selected_by'] == ('id' if by_id else 'position') and event['reply_change_count'] == 2
    assert request['change_index'] == index and request['change_count'] == 2 and request['change_id'] == IDS[index - 1]
    assert request['instruction'] == engineer_v292.FORMAT_RETRY_SYSTEM
    if by_id:
        assert result[0]['original']['id'] == IDS[index - 1]


@pytest.mark.parametrize('index', [1, 2])
def test_real_first_retry_preserves_written_routing_hook_before_registered_normalization(monkeypatch, index):
    result, _, _ = retry(monkeypatch, REPLIES['format-retry/propose/1'], index=index, identity=IDS[index - 1])
    row = result[0]
    proposed = e.Change(index, row['entry']['kind'], row['entry'], row['source'], 'b' * 64)
    assert e._structure(proposed, ctx().parent, (), train=True, benches=p.SUPPORTED_BENCHES) == 'unknown_hook_or_bench'
    assert 'routing' in row['entry']['hooks']


@pytest.mark.parametrize('index', [1, 2])
def test_real_second_retry_selected_changes_pass_c1_without_hook_rewriting(monkeypatch, index):
    result, _, _ = retry(monkeypatch, REPLIES['format-retry/propose/2'], index=index, identity=IDS[index - 1])
    row = result[0]
    proposed = e.Change(index, row['entry']['kind'], row['entry'], row['source'], 'b' * 64)
    assert e._structure(proposed, ctx().parent, (), train=True, benches=p.SUPPORTED_BENCHES) is None
    assert row['entry']['hooks'] == ['applies', 'before_call']


def test_real_parent_proposal_preserves_missing_source_errors():
    result = reader.read(REPLIES['propose'], ctx(p.ZEBRA_PC_V8))
    assert [row['error'] for row in result] == ['no procedure source block'] * 2
    assert all('original' not in row for row in result)


@pytest.mark.parametrize('index', [1, 2])
def test_real_parent_retries_preserve_rejection_and_original_request_shape(monkeypatch, index):
    result, event, request = retry(monkeypatch, REPLIES['format-retry/propose/%d' % index],
        index=index, identity=IDS[index - 1], configuration=p.ZEBRA_PC_V8)
    assert result is None and event['reason'] == 'format retry must contain exactly the requested change'
    assert set(event) == {'purpose', 'call', 'parse_problem', 'parsed', 'reason'}
    assert set(request) == {'request', 'instruction', 'schema', 'parse_problem', 'previous_reply', 'change_index'}
    assert request['instruction'] == engineer_v28.FORMAT_RETRY_SYSTEM


@pytest.mark.parametrize('field', ['source', 'code'])
@pytest.mark.parametrize('fence', ['```', '~~~'])
@pytest.mark.parametrize('info', ['', 'python', 'arbitrary info'])
def test_inline_fenced_program_unwraps_only_the_outer_fence(field, fence, info):
    original = ' \n' + fence + info + '\n' + GOOD + fence + '\n '
    result = reader.read(reply([{'kind': 'new', field: original}]), ctx())[0]
    assert result['source'] == GOOD and result['error'] is None
    rules = [row['rule'] for row in result['repairs']]
    assert 'inline_source_unfenced' in rules
    assert ('inline_code_alias' in rules) == (field == 'code')
    assert not any(row['rule'] == 'unknown_key_ignored' and row['path'] == '$.code' for row in result['repairs'])


@pytest.mark.parametrize('field', ['source', 'code'])
@pytest.mark.parametrize('program', [GOOD, ' \n' + GOOD + '\n ', '```python\n' + GOOD,
    'preface\n```python\n' + GOOD + '```', '```python\n' + GOOD + '```\nafterword',
    '```python\n' + GOOD + '```\n```python\n' + GOOD + '```'])
def test_unfenced_partial_and_multiple_inline_blocks_are_never_rewritten(field, program):
    result = reader.read(reply([{'kind': 'new', field: program}]), ctx())[0]
    assert result['source'] == program
    assert 'inline_source_unfenced' not in {row['rule'] for row in result['repairs']}


@pytest.mark.parametrize('source', [None, '', '  ', 17])
def test_nonempty_code_fills_absent_or_unusable_source(source):
    result = reader.read(reply([entry(source=source, code=GOOD)]), ctx())[0]
    assert result['source'] == GOOD and result['error'] is None
    assert 'inline_code_alias' in {row['rule'] for row in result['repairs']}


@pytest.mark.parametrize('same', [True, False])
def test_source_precedence_is_logged_only_when_code_differs(same):
    result = reader.read(reply([entry(code=GOOD if same else 'different')]), ctx())[0]
    assert result['source'] == GOOD and 'code' not in result['entry']
    assert ('inline_source_precedence' in {row['rule'] for row in result['repairs']}) is not same


def test_parent_inline_code_and_fenced_source_behavior_is_unchanged():
    result = reader.read(reply([{'code': GOOD}, {'source': '```python\n' + GOOD + '```'}]), ctx(p.ZEBRA_PC_V8))
    assert result[0]['error'] == 'no procedure source block'
    assert result[1]['source'] == '```python\n' + GOOD + '```'
    assert all(not any(v['rule'] in {'inline_code_alias', 'inline_source_unfenced'} for v in row['repairs']) for row in result)


@pytest.mark.parametrize('field', ['id', 'revises'])
def test_retry_unique_written_identity_wins_over_position_and_count(monkeypatch, field):
    chosen = entry('different', **{field: 'wanted'})
    result, event, _ = retry(monkeypatch, reply([entry('other'), chosen]), count=3)
    assert result[0]['original'][field] == 'wanted' and event['selected_by'] == 'id'


@pytest.mark.parametrize('values', [
    [entry('same'), entry('same')],
    [entry('a'), entry('b')],
])
def test_retry_position_is_fallback_even_when_identity_is_ambiguous(monkeypatch, values):
    result, event, _ = retry(monkeypatch, reply(values), index=2, identity='same')
    assert result[0]['original'] == values[1] and event['selected_by'] == 'position'


@pytest.mark.parametrize('values,count,index', [
    ([entry(), entry()], 3, 1), ([entry('a'), entry('b')], 3, 1),
    ([entry('a'), entry('b')], 2, 0), ([entry('a'), entry('b')], 2, 3),
    ([], 0, 1),
])
def test_retry_without_unique_identity_or_valid_position_rejects(monkeypatch, values, count, index):
    result, event, _ = retry(monkeypatch, reply(values), count=count, index=index)
    assert result is None and not event['parsed']
    assert event['reply_change_count'] == len(values) and 'selected_by' not in event


def test_single_retry_keeps_single_selection_even_without_written_identity(monkeypatch):
    result, event, request = retry(monkeypatch, reply([{'source': GOOD}]), identity=None)
    assert len(result) == 1 and event['selected_by'] == 'single' and event['reply_change_count'] == 1
    assert 'change_id' not in request


def test_selected_error_rejects_and_records_selection_metadata(monkeypatch):
    result, event, _ = retry(monkeypatch, reply([entry('other'), entry(hooks=None)]))
    assert result is None and 'hooks' in event['reason']
    assert event['selected_by'] == 'id' and event['reply_change_count'] == 2


@pytest.mark.parametrize('bad', [17, {'kind': 'unknown'}, {'hooks': None}])
def test_invalid_unselected_sibling_cannot_discard_selected_change(monkeypatch, bad):
    result, event, _ = retry(monkeypatch, reply([bad, entry()]))
    assert len(result) == 1 and result[0]['error'] is None and event['parsed']


def test_ambiguous_sibling_source_ownership_cannot_discard_inline_selection(monkeypatch):
    fixed = engineer_reply({'changes': [entry(), {}, {}]}, [GOOD])
    result, event, _ = retry(monkeypatch, fixed, count=3)
    assert result[0]['source'] == GOOD and event['parsed']


def test_selected_fenced_source_is_kept_when_only_sibling_ownership_is_ambiguous(monkeypatch):
    selected = {'kind': 'new', 'id': 'wanted', 'hooks': ['before_call']}
    siblings = [{'hooks': ['sheet_feedback']}, {'hooks': ['sheet_feedback']}]
    feedback = 'def sheet_feedback(view, sheet, state):\n    return None\n'
    fixed = engineer_reply({'changes': [selected, *siblings]}, [GOOD, feedback, feedback, feedback])
    result, event, _ = retry(monkeypatch, fixed, count=3)
    assert result[0]['source'].strip() == GOOD.strip() and event['parsed']


def test_format_retry_fix_can_select_one_change_without_inheriting_into_siblings(monkeypatch):
    current = ctx()
    original = e.Change(2, 'new', {'kind': 'new', 'description': 'Keep my description.'}, GOOD, 'a' * 64)
    result, event, _ = retry(monkeypatch, reply([{'kind': 'unknown'}, entry()]), change=original)
    assert result[0]['entry']['description'] == 'Keep my description.' and event['parsed']


def test_read_call_sends_original_count_and_raw_ids_once_per_failed_change(monkeypatch):
    current, requests = ctx(), []
    originals = [{'kind': 'new', 'id': 'first'}, {'kind': 'new', 'id': 17, 'revises': 'second'}]
    fixed = reply([entry('second'), entry('first')])
    def ask(context, request, purpose):
        requests.append((request, purpose))
        return fixed, str(len(requests)) * 64
    monkeypatch.setattr(e, '_ask', ask)
    changes, failures = engineer_v28.read_call(current, reply(originals), 'a' * 64, 'propose')
    assert not failures and len(changes) == len(requests) == 2
    assert [v[0]['change_count'] for v in requests] == [2, 2]
    assert [v[0]['change_index'] for v in requests] == [1, 2]
    assert [v[0]['change_id'] for v in requests] == ['first', 'second']
    assert [v[1] for v in requests] == ['format-retry/propose/1', 'format-retry/propose/2']
    assert [c.n for c in changes] == [1, 2]
    assert [v['selected_by'] for v in current.sheet['format_retries']] == ['id', 'id']


def test_raw_defaulted_identity_cannot_match_retry_target(monkeypatch):
    # A new entry's normalized id is ignored; inherited/defaulted fields must
    # never invent a retry identity match when reply count cannot select it.
    result, event, _ = retry(monkeypatch, reply([{'source': GOOD}, {'source': GOOD}]), identity='', count=3)
    assert result is None and not event['parsed']


def test_reader_does_not_mutate_selection_inputs_or_inline_programs():
    original = entry(code='unused')
    saved = copy.deepcopy(original)
    parsed = reader.read(reply([original]), ctx())[0]
    assert original == saved and parsed['original'] == saved
    ast.parse(parsed['source'])


@pytest.mark.parametrize('original,expected_count', [
    (engineer_reply({'changes': [{}, {}]}, [GOOD]), 2),
    (reply([{}] * (p.MAX_CHANGES + 1)), p.MAX_CHANGES + 1),
    ('not a manifest', None),
])
def test_envelope_retry_retains_count_when_manifest_can_be_read(monkeypatch, original, expected_count):
    current, requests = ctx(), []
    def ask(context, request, purpose):
        requests.append(request)
        return reply([entry()]), 'b' * 64
    monkeypatch.setattr(e, '_ask', ask)
    changes, failures = engineer_v28.read_call(current, original, 'a' * 64, 'propose')
    assert len(changes) == len(requests) == 1 and not failures
    assert requests[0]['change_count'] == expected_count
    assert 'change_id' not in requests[0]


def test_retry_records_reply_count_even_when_oversized_manifest_has_no_unique_selection(monkeypatch):
    result, event, _ = retry(monkeypatch, reply([entry()] * (p.MAX_CHANGES + 1)))
    assert result is None and event['reply_change_count'] == p.MAX_CHANGES + 1
    assert event['reason'] == 'format retry must contain exactly the requested change'


def test_oversized_retry_can_select_inline_source_without_expanding_proposal_limit(monkeypatch):
    entries = [entry(str(n)) for n in range(250)]
    entries[197]['id'] = 'wanted'
    def exponential(*args, **kwargs):
        pytest.fail('oversized retries must not enter the exponential source matcher')
    monkeypatch.setattr(reader, '_source_owners', exponential)
    result, event, _ = retry(monkeypatch, reply(entries))
    assert len(result) == 1 and result[0]['original']['id'] == 'wanted'
    assert result[0]['source'] == GOOD and event['reply_change_count'] == 250
    with pytest.raises(reader.Unusable, match='changes count 250 exceeds 3'):
        reader.read(reply(entries), ctx())


def test_oversized_retry_complete_fences_keep_manifest_order(monkeypatch):
    entries = [{'id': str(n)} for n in range(7)]
    sources = [GOOD + '# authored source %d\n' % n for n in range(len(entries))]
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, sources), identity='5')
    assert result[0]['source'].strip() == sources[5].strip() and event['selected_by'] == 'id'


def test_oversized_retry_incomplete_fences_can_use_unique_hook_match(monkeypatch):
    entries = [{'id': str(n), 'hooks': ['sheet_feedback']} for n in range(7)]
    entries[5]['hooks'] = ['before_call']
    other = 'def sheet_feedback(view, sheet, state):\n    return None\n'
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, [other, GOOD]), identity='5')
    assert result[0]['source'].strip() == GOOD.strip() and event['parsed']


def test_oversized_retry_rejects_ambiguous_selected_source(monkeypatch):
    entries = [{'id': str(n), 'hooks': ['before_call']} for n in range(7)]
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, [GOOD, GOOD]), identity='5')
    assert result is None and event['selected_by'] == 'id'
    assert event['reason'] == 'ambiguous procedure source blocks; ownership is not unique'


def test_oversized_retry_noncoded_selection_ignores_ambiguous_sibling_fences(monkeypatch):
    entries = [{'kind': 'deletion', 'id': 'wanted'}, {}, {}, {}]
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, [GOOD, GOOD]))
    assert result[0]['entry'] == entries[0] and result[0]['source'] is None and event['parsed']


def test_oversized_retry_cannot_take_a_block_competing_siblings_need(monkeypatch):
    entries = [{'id': str(n), 'hooks': ['before_call']} for n in range(4)]
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, [GOOD]), identity='0')
    assert result is None and event['reason'] == 'ambiguous procedure source blocks; ownership is not unique'


def test_oversized_retry_complete_noninline_candidate_fences_keep_order(monkeypatch):
    entries = [entry('inline'), {'id': 'first'}, entry('another-inline'), {'id': 'wanted'}]
    sources = [GOOD + '# first\n', GOOD + '# wanted\n']
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, sources))
    assert result[0]['source'].strip() == sources[1].strip() and event['parsed']


def test_small_retry_many_tied_blocks_remains_ambiguous(monkeypatch):
    entries = [{'id': str(n), 'hooks': ['before_call']} for n in range(3)]
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, [GOOD] * 400), identity='0')
    assert result is None and event['reason'] == 'ambiguous procedure source blocks; ownership is not unique'


def test_oversized_retry_inherits_optional_selected_source_when_mandatory_siblings_need_all_blocks(monkeypatch):
    original = e.Change(1, 'new', {'kind': 'new'}, GOOD, 'a' * 64)
    entries = [{'id': 'wanted', 'hooks': ['before_call']}] + [{'hooks': ['sheet_feedback']}] * 3
    result, event, _ = retry(monkeypatch, engineer_reply({'changes': entries}, [GOOD]), change=original)
    assert result[0]['source'] == GOOD and event['parsed']
    assert any(row['rule'] == 'inherited_source' for row in result[0]['repairs'])


def test_oversized_retry_optional_siblings_compete_when_there_are_spare_blocks():
    current = ctx()
    current.parent = SimpleNamespace(order=('incumbent',), get=lambda identity: SimpleNamespace(source=GOOD))
    entries = [{'id': 'wanted', 'hooks': ['before_call']}] + [
        {'kind': 'revision', 'revises': 'incumbent', 'hooks': ['applies', 'before_call']}] * 3
    other = 'def sheet_feedback(view, sheet, state):\n    return None\n'
    with pytest.raises(reader.Unusable, match='ambiguous procedure source blocks'):
        reader.read(engineer_reply({'changes': entries}, [GOOD, other, other]), current,
            selection={'change_id': 'wanted', 'change_count': 4, 'change_index': 1})


@pytest.mark.parametrize('label,line', [('format-retry/propose/1', 11), ('format-retry/propose/2', 10)])
@pytest.mark.parametrize('index', [0, 1])
def test_real_retry_programs_keep_actual_check_verdicts(label, line, index):
    current = ctx()
    row = reader.read(REPLIES[label], current)[index]
    proposed = e.Change(index + 1, row['entry']['kind'], row['entry'], row['source'], 'b' * 64)
    report = e.check(proposed, current)
    assert proposed.source == row['source']
    assert report['checks'][0]['check'] == 'C1' and report['checks'][0]['passed']
    if index == 0:
        assert not report['passed'] and report['failed'] == 'C2'
        faults = report['checks'][-1]['detail']
        assert {fault['rule'] for fault in faults} == {'module_level', 'statement'}
        assert all(fault['detail'] == 'ClassDef' and fault['line'] == line
                   and fault['line_text'] == 'class _Cap(Exception):' for fault in faults)
    else:
        assert report['passed'] and report['failed'] is None
        for name in ('C6b', 'C6c'):
            check = next(check for check in report['checks'] if check['check'] == name)
            assert not check['passed'] and check['informational']
