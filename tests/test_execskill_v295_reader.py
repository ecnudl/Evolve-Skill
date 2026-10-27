"""v2.9.5 integer booleans with frozen string tolerance and real ALF replies, offline."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.execskill import engineer as e, engineer_reader as reader, engineer_v28, profiles as p
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v291_engineer import ALF_GOOD, GOOD, proposal
from tests.test_execskill_v293_reader import context as reader_context
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


CHILDREN = ('zebra-pc-v12', 'alfworld-v9')
PARENTS = ('zebra-pc-v7', 'zebra-pc-v8', 'zebra-pc-v9', 'zebra-pc-v10', 'zebra-pc-v11',
           'alfworld-v4', 'alfworld-v5', 'alfworld-v6', 'alfworld-v7', 'alfworld-v8')
BOOLEAN_PATHS = (('requests_second_call',), ('replay_tests', 0, 'claims_fix'),
                 ('replay_tests', 0, 'nonvacuity', 'withheld_expect'),
                 ('replay_tests', 0, 'property', 'value'))
BOOLEAN_STRINGS = ('true', 'TRUE', 'TrUe', 'false', 'FALSE', 'FaLsE')
INVALID_BOOLEANS = (2, -1, 0.0, 1.0, '0', '1', ' true', 'false ', None, 'yes', '')
FIXTURE = Path(__file__).parent / 'fixtures/execskill/alf7_s3b_replies.json'
FIXTURE_SHA256 = 'fad86bf0f48e2acf800ef976962c1443f0dae1f8939a4e5b10f135f378308e94'
REPLIES = {row['label']: row['reply'] for row in json.loads(FIXTURE.read_text())}
IDS = ['alf_world_state_tracker', 'alf_command_guard']


def entry(configuration):
    return {'kind': 'new', 'id': 'authored', 'source': ALF_GOOD if p.is_alfworld(configuration) else GOOD,
            'requests_second_call': False, 'replay_tests': [{
                'id': 'advisory', 'trajectory': 'authored-cell', 'hook': 'sheet_feedback',
                'claims_fix': False, 'nonvacuity': {'withheld_expect': False, 'mutation': None},
                'property': {'kind': 'repair_requested', 'value': False}}]}


def put(value, path, replacement):
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = replacement


def at(value, path):
    for part in path:
        value = value[part]
    return value


def json_path(path):
    return '$' + ''.join('[%d]' % part if isinstance(part, int) else '.' + part for part in path)


def encoded(value):
    return engineer_reply({'changes': [value]}, [])


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('path', BOOLEAN_PATHS)
@pytest.mark.parametrize('number', (0, 1))
def test_every_boolean_schema_field_reads_integer_zero_or_one_and_logs_exact_repair(configuration, path, number):
    original = entry(configuration)
    put(original, path, number)
    row = reader.read(encoded(original), reader_context(configuration))[0]
    assert row['error'] is None and at(row['entry'], path) is bool(number)
    assert type(at(row['original'], path)) is int and at(row['original'], path) == number
    repairs = [repair for repair in row['repairs'] if repair['rule'] == 'integer_boolean']
    assert repairs == [{'rule': 'integer_boolean', 'path': json_path(path), 'from': number}]
    assert not any(repair['rule'] == 'lossless_type_conversion' for repair in row['repairs'])


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('path', BOOLEAN_PATHS)
@pytest.mark.parametrize('value', (False, True))
def test_existing_actual_booleans_stay_exact_without_conversion_repairs(configuration, path, value):
    original = entry(configuration)
    put(original, path, value)
    row = reader.read(encoded(original), reader_context(configuration))[0]
    assert row['error'] is None and at(row['entry'], path) is value
    assert not any(repair['rule'] == 'integer_boolean' for repair in row['repairs'])


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('path', BOOLEAN_PATHS)
@pytest.mark.parametrize('value', INVALID_BOOLEANS)
def test_other_nonboolean_values_are_refused_for_every_boolean_schema_field(configuration, path, value):
    original = entry(configuration)
    put(original, path, value)
    # The same walker handles top-level manifests and advisory nested tests.
    given = original if len(path) == 1 else original['replay_tests'][0]
    fields = reader.schema(source=original['source']) if len(path) == 1 else reader.test_schema(given)
    repairs = []
    with pytest.raises(reader.Unusable, match='must have type bool, got '):
        reader.normalize(given, fields, configuration=configuration, repairs=repairs)
    assert not any(repair['rule'] == 'integer_boolean' for repair in repairs)
    row = reader.read(encoded(original), reader_context(configuration))[0]
    if len(path) == 1:
        assert row['error'] == '$.requests_second_call must have type bool, got ' + type(value).__name__
    else:
        # Malformed replay tests stay advisory; they are refused, not coerced.
        assert row['error'] is None and at(row['entry'], path) == value
        assert any(repair['rule'] == 'malformed_test' and repair['path'] == '$.replay_tests[0]'
                   and 'must have type bool, got ' in repair['reason'] for repair in row['repairs'])


@pytest.mark.parametrize('configuration', PARENTS)
@pytest.mark.parametrize('number', (0, 1))
def test_all_snapshotted_parents_still_refuse_integer_boolean_fields(configuration, number):
    original = entry(configuration)
    original['requests_second_call'] = number
    row = reader.read(encoded(original), reader_context(configuration))[0]
    assert row['error'] == '$.requests_second_call must have type bool, got int'
    assert not any(repair['rule'] == 'integer_boolean' for repair in row['repairs'])


@pytest.mark.parametrize('configuration', CHILDREN + ('zebra-pc-v11', 'alfworld-v8'))
@pytest.mark.parametrize('path', BOOLEAN_PATHS)
@pytest.mark.parametrize('value', BOOLEAN_STRINGS)
def test_children_and_parents_keep_case_insensitive_string_booleans_and_exact_repair(configuration, path, value):
    original = entry(configuration)
    put(original, path, value)
    row = reader.read(encoded(original), reader_context(configuration))[0]
    assert row['error'] is None and at(row['entry'], path) is (value.lower() == 'true')
    assert at(row['original'], path) == value
    conversions = [repair for repair in row['repairs'] if repair['rule'] in (
        'lossless_type_conversion', 'integer_boolean')]
    assert conversions == [{'rule': 'lossless_type_conversion', 'path': json_path(path)}]


@pytest.mark.parametrize('configuration', tuple(p.CONFIGURATIONS))
def test_boolean_normalizer_tolerance_and_refusals_cover_every_registered_configuration(configuration):
    # Generic schema keeps this comparison independent of historical reader
    # availability while exercising the exact normalization branch in use.
    fields = {'flag': reader.Field(bool, True, False)}
    for value in INVALID_BOOLEANS:
        repairs = []
        with pytest.raises(reader.Unusable, match='must have type bool, got '):
            reader.normalize({'flag': value}, fields, configuration=configuration, repairs=repairs)
        assert repairs == []
    for value in BOOLEAN_STRINGS:
        repairs = []
        assert reader.normalize({'flag': value}, fields, configuration=configuration, repairs=repairs) == {
            'flag': value.lower() == 'true'}
        assert repairs == [{'rule': 'lossless_type_conversion', 'path': '$.flag'}]
    for number in (0, 1):
        repairs = []
        if p.is_v295(configuration):
            assert reader.normalize({'flag': number}, fields, configuration=configuration, repairs=repairs) == {
                'flag': bool(number)}
            assert repairs == [{'rule': 'integer_boolean', 'path': '$.flag', 'from': number}]
        else:
            with pytest.raises(reader.Unusable, match='must have type bool, got int'):
                reader.normalize({'flag': number}, fields, configuration=configuration, repairs=repairs)
            assert repairs == []


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('value', (0, 1, 0.0, None))
def test_opaque_state_values_are_not_boolean_coerced(configuration, value):
    original = entry(configuration)
    test = original['replay_tests'][0]
    test['property'] = {'kind': 'state_equals', 'key': 'counter', 'value': value}
    row = reader.read(encoded(original), reader_context(configuration))[0]
    actual = row['entry']['replay_tests'][0]['property']['value']
    assert row['error'] is None and type(actual) is type(value) and actual == value
    assert not any(repair['rule'] == 'integer_boolean' for repair in row['repairs'])


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('representation', ('integer', 'string'))
def test_direct_check_normalizes_manifest_and_nested_test_booleans_before_preparation(configuration, representation):
    bench = p.active_benches(configuration)[0]
    ctx, _ = context(configuration=configuration, bench=bench)
    change = proposal(ctx, ALF_GOOD if bench == 'alfworld' else GOOD)
    hook = 'alf_before_step' if bench == 'alfworld' else 'before_call'
    false, true = (0, 1) if representation == 'integer' else ('FaLsE', 'TrUe')
    change.entry['requests_second_call'] = false
    change.entry['replay_tests'] = [{'id': 'test', 'trajectory': ctx.trajectories[0]['cell'], 'hook': hook,
        'property': {'kind': 'note_contains', 'value': 'observation' if bench == 'alfworld' else 'question',
                     **({'step': 0} if bench == 'alfworld' else {})},
        'claims_fix': true, 'nonvacuity': {'withheld_expect': false, 'mutation': None}}]
    report = e.check(change, ctx)
    assert report['passed'] and report['dropped_tests'] == []
    assert change.entry['requests_second_call'] is False
    test = change.entry['replay_tests'][0]
    assert test['claims_fix'] is True and test['nonvacuity']['withheld_expect'] is False
    repairs = [repair for repair in change.repairs if repair['rule'] in (
        'integer_boolean', 'lossless_type_conversion')]
    if representation == 'integer':
        assert repairs == [{'rule': 'integer_boolean', 'path': '$.requests_second_call', 'from': 0},
            {'rule': 'integer_boolean', 'path': '$.replay_tests[0].claims_fix', 'from': 1},
            {'rule': 'integer_boolean', 'path': '$.replay_tests[0].nonvacuity.withheld_expect', 'from': 0}]
    else:
        assert repairs == [{'rule': 'lossless_type_conversion', 'path': path} for path in (
            '$.requests_second_call', '$.replay_tests[0].claims_fix',
            '$.replay_tests[0].nonvacuity.withheld_expect')]


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('written,expected,rule', [(0, False, 'integer_boolean'), (1, True, 'integer_boolean'),
    ('FaLsE', False, 'lossless_type_conversion'), ('TrUe', True, 'lossless_type_conversion')])
def test_selected_format_retry_uses_integer_and_parent_string_boolean_rules(configuration, written, expected,
                                                                           rule, monkeypatch):
    ctx, _ = context(configuration=configuration, bench=p.active_benches(configuration)[0])
    original, fixed = entry(configuration), entry(configuration)
    original['requests_second_call'], fixed['requests_second_call'] = 2, written
    calls = []
    def ask(actual, request, purpose):
        assert actual is ctx and purpose == 'format-retry/propose/1'
        calls.append(request)
        return encoded(fixed), 'b' * 64
    monkeypatch.setattr(e, '_ask', ask)
    changes, failures = engineer_v28.read_call(ctx, encoded(original), 'a' * 64, 'propose')
    assert not failures and len(changes) == len(calls) == 1
    assert changes[0].entry['requests_second_call'] is expected
    repair = {'rule': rule, 'path': '$.requests_second_call'}
    if rule == 'integer_boolean':
        repair['from'] = written
    assert repair in changes[0].repairs
    assert not any(row['rule'] == ('integer_boolean' if rule == 'lossless_type_conversion'
                                  else 'lossless_type_conversion') for row in changes[0].repairs)
    assert ctx.sheet['format_retries'][0]['parsed']
    assert calls[0]['change_id'] == 'authored' and calls[0]['change_index'] == 1


def test_real_alf_proposal_reads_both_changes_without_any_format_retry(monkeypatch):
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    ctx, _ = context(configuration='alfworld-v9', bench='alfworld')
    rows = reader.read(REPLIES['propose'], ctx)
    assert [row['original']['id'] for row in rows] == IDS
    assert [row['original']['requests_second_call'] for row in rows] == [0, 0]
    assert all(row['error'] is None and row['entry']['requests_second_call'] is False for row in rows)
    assert all(row['source'] and 'alf_before_step' in reader.defined_hooks(row['source']) for row in rows)
    monkeypatch.setattr(e, '_ask', lambda *args, **kwargs: pytest.fail('No format retry is needed'))
    changes, failures = engineer_v28.read_call(ctx, REPLIES['propose'], 'a' * 64, 'propose')
    assert not failures and len(changes) == 2 and not ctx.sheet.get('format_retries')
    assert [change.source for change in changes] == [row['source'] for row in rows]
    assert all({'rule': 'integer_boolean', 'path': '$.requests_second_call', 'from': 0}
               in change.repairs for change in changes)


def test_real_parent_alf_proposal_still_needs_both_recorded_retries_and_loses_the_malformed_one(monkeypatch):
    ctx, _ = context(configuration='alfworld-v7', bench='alfworld')
    rows = reader.read(REPLIES['propose'], ctx)
    assert [row['error'] for row in rows] == ['$.requests_second_call must have type bool, got int'] * 2
    calls = []
    def ask(actual, request, purpose):
        assert actual is ctx
        calls.append((request, purpose))
        return REPLIES[purpose], str(len(calls)) * 64
    monkeypatch.setattr(e, '_ask', ask)
    changes, failures = engineer_v28.read_call(ctx, REPLIES['propose'], 'a' * 64, 'propose')
    assert [purpose for _, purpose in calls] == ['format-retry/propose/1', 'format-retry/propose/2']
    assert [request['change_id'] for request, _ in calls] == IDS
    assert [request['change_index'] for request, _ in calls] == [1, 2]
    assert len(changes) == len(failures) == 1 and changes[0].n == 1 and failures[0]['n'] == 2
    assert failures[0]['reason'] == 'unparseable'
    assert failures[0]['detail'] == '$.requests_second_call must have type bool, got int'
    events = ctx.sheet['format_retries']
    assert events[0]['parsed'] and not events[1]['parsed']
    assert not any(repair['rule'] == 'integer_boolean' for change in changes for repair in change.repairs)


@pytest.mark.parametrize('configuration', ('alfworld-v7', 'alfworld-v9'))
def test_real_malformed_second_retry_is_not_closed_or_guessed(configuration):
    with pytest.raises(reader.Unusable):
        reader.read(REPLIES['format-retry/propose/2'], reader_context(configuration))
    row = reader.read(REPLIES['format-retry/propose/1'], reader_context(configuration))[0]
    assert row['error'] is None and row['entry']['requests_second_call'] is False
    assert not any(repair['rule'] == 'integer_boolean' for repair in row['repairs'])
