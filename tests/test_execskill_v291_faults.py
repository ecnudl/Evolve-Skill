"""v2.9.1 actual C6 diagnostic capture using only authored local worker calls."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer, fault_feedback as ff, profiles as p, replay
from tests.test_execskill_replay import alf_trajectory
from tests.test_execskill_v24_engineer import context, stored, change, PUBLIC
from tests.test_execskill_v28_execution import SeedWorkers
from tests.test_execskill_v29_runtime import procedure
from tests.test_execskill_zpc_pipeline import offline


def report_for(proc, entries, *, capture=True):
    detail, outcomes = replay.zero_crash(proc, entries, SeedWorkers(), capture_faults=capture)
    return {'checks': [{'check': 'C6', 'detail': detail}]}, outcomes


def zebra_entries(count=1):
    return [replay.inputs_of(stored(key='run-%d' % index, cell='cell-%d' % index)) for index in range(count)]


def authored_summary(fired, faulted):
    proc = procedure()
    entries = []
    for index in range(fired):
        fault = {'hook': 'before_call', 'step': None, 'kind': 'crash:exception',
                 'exc_type': 'IndexError', 'message': 'index', 'line': 2,
                 'arguments': {'view': {}, 'state': None}}
        outcome = {'applies': True, 'faults': [fault] if index < faulted else []}
        entries.append({'task_id': 'task-%d' % index, 'first': outcome, 'second': deepcopy(outcome)})
    return ff.summarize(proc, {'checks': [{'check': 'C6', 'detail': {'items': entries}}]})


@pytest.mark.parametrize('fired,faulted,threshold,triggered', [
    (0, 0, 1, False), (1, 0, 1, False), (1, 1, 1, True),
    (9, 1, 1, True), (10, 1, 1, True), (11, 1, 2, False), (11, 2, 2, True),
    (59, 5, 6, False), (60, 6, 6, True), (60, 5, 6, False),
])
def test_threshold_uses_distinct_fired_items_and_integer_ceiling(fired, faulted, threshold, triggered):
    value = authored_summary(fired, faulted)
    assert (value['fired'], value['faulted'], value['threshold'], value['triggered']) == (
        fired, faulted, threshold, triggered)
    assert value['per_hook'] == ({'before_call': faulted} if faulted else {})


def test_exception_keeps_actual_line_source_context_arguments_and_two_pass_union():
    source = ('def before_call(view, state):\n'
              '    lines = view["question"].splitlines()\n'
              '    missing = lines[999]\n'
              '    return {"facts": [missing]}\n')
    proc = procedure(source, origin='zebralogic')
    report, _ = report_for(proc, zebra_entries(3))
    result = ff.summarize(proc, report)
    assert result['fired'] == result['faulted'] == 3 and result['triggered']
    assert len(result['signatures']) == 1
    sig = result['signatures'][0]
    assert sig['exc_type'] == 'IndexError' and sig['message'] == 'list index out of range'
    assert sig['line'] == 3 and sig['source_line'] == '    missing = lines[999]'
    assert sig['source_context'] == [{'line': index, 'text': text}
                                     for index, text in enumerate(source.splitlines(), 1)]
    assert sig['items'] == 3 and sig['example_task_ids'] == ['run-0', 'run-1']
    assert result['example_call'] == {'task_id': 'run-0', 'hook': 'before_call', 'step': None,
                                      'arguments': {'view': PUBLIC, 'state': None}}
    details = report['checks'][0]['detail']
    assert details['fault_count'] == 6
    assert all(item['first']['faults'][0]['line'] == item['second']['faults'][0]['line'] == 3
               for item in details['items'])


def test_alf_state_none_is_captured_from_the_first_step_call():
    source = ('def alf_before_step(view, state):\n'
              '    state.get("visited", [])\n'
              '    return {"fields": {"facts": ["Room observed."]}, "discourage": []}\n')
    proc = procedure(source, origin='alfworld', hooks=('alf_before_step',))
    entry = replay.inputs_of(alf_trajectory())
    report, outcomes = report_for(proc, [entry])
    value = ff.summarize(proc, report)
    assert value['fired'] == value['faulted'] == 1
    signature = value['signatures'][0]
    assert signature['exc_type'] == 'AttributeError' and signature['line'] == 2
    assert signature['first_step'] == 0
    assert value['example_call']['arguments'] == {'view': entry['steps'][0]['view'], 'state': None}
    assert value['example_call']['step'] == 0 and len(outcomes[entry['cell']].steps) == 1


@pytest.mark.parametrize('kind,source,cap,length', [
    ('note_cap', 'def before_call(view, state):\n    return {"facts": ["x" * 201]}\n', 1500, 201),
    ('note_over_declared_cap', 'def before_call(view, state):\n    return {"facts": ["x" * 100]}\n', 50, 159),
    ('note_over_bench_cap', 'def alf_before_step(view, state):\n    return {"fields": {"facts": ["x" * 200] * 15}, "discourage": []}\n', 4000, 3101),
])
def test_note_cap_faults_include_measured_length_declared_and_benchmark_caps(kind, source, cap, length):
    alf = kind == 'note_over_bench_cap'
    bench, hook = ('alfworld', 'alf_before_step') if alf else ('zebralogic', 'before_call')
    proc = procedure(source, origin=bench, hooks=(hook,), max_note_chars=cap)
    entries = [replay.inputs_of(alf_trajectory())] if alf else zebra_entries()
    report, outcomes = report_for(proc, entries)
    value = ff.summarize(proc, report)
    sig = value['signatures'][0]
    assert sig['kind'] == kind and sig['measured_length'] == length
    assert sig['max_note_chars'] == cap and sig['bench_cap'] == p.MAX_NOTE_CHARS[bench]
    assert value['fired'] == value['faulted'] == 1
    assert not next(iter(outcomes.values())).notes
    assert value['example_call']['arguments'] == {
        'view': entries[0]['steps'][0]['view'] if alf else PUBLIC, 'state': None}
    if kind == 'note_cap':
        assert sig['field'] == 'facts' and sig['field_limits']['max_chars'] == 200


def test_state_over_declared_bytes_includes_actual_after_hook_event_and_state():
    source = ('def alf_before_step(view, state):\n    return {"fields": {}, "discourage": []}\n'
              'def alf_after_step(event, state):\n    return {"visited": ["cabinet"]}\n')
    proc = procedure(source, origin='alfworld', hooks=('alf_before_step', 'alf_after_step'), state_bytes=1)
    entry = replay.inputs_of(alf_trajectory())
    report, _ = report_for(proc, [entry])
    value = ff.summarize(proc, report)
    sig = value['signatures'][0]
    assert sig['kind'] == 'state_over_declared_bytes' and sig['measured_length'] > sig['state_bytes'] == 1
    assert value['example_call']['arguments'] == {'event': entry['steps'][0]['event'], 'state': None}


def test_summary_deduplicates_items_across_cells_passes_and_predicate_capture():
    fault = {'hook': 'before_call', 'kind': 'crash:exception', 'exc_type': 'ValueError',
             'message': 'bad', 'step': None, 'line': 2}
    report = {'checks': [
        {'check': 'C6', 'detail': {'items': [
            {'task_id': 'same', 'first': {'applies': True, 'faults': []},
             'second': {'applies': True, 'faults': [fault]}},
            {'task_id': 'same', 'first': {'applies': True, 'faults': [fault]}, 'second': {}},
        ]}},
        {'check': 'C6b', 'detail': {'captures': [
            {'task_id': 'same', 'applies': None, 'faults': [{**fault, 'hook': 'applies', 'kind': 'predicate:not_bool'}]},
            {'task_id': 'never-applied', 'applies': None, 'faults': [fault]},
        ]}},
    ]}
    result = ff.summarize(procedure(), report)
    assert result['fired'] == result['faulted'] == 1
    assert result['per_hook'] == {'applies': 1, 'before_call': 1}
    assert all(row['items'] == 1 for row in result['signatures'])


def test_information_is_not_faulted_and_retained_keyword_hits_are_not_dropped_notes():
    faults = [{'hook': 'before_call', 'kind': 'note_form_instruction', 'informational': True},
              {'hook': 'before_call', 'kind': 'note_audit_keyword', 'informational': True, 'count': 4}]
    outcome = {'applies': True, 'faults': faults}
    report = {'checks': [{'check': 'C6', 'detail': {'items': [
        {'task_id': 'run-1', 'first': outcome, 'second': deepcopy(outcome)}]}}]}
    value = ff.summarize(procedure(), report)
    assert value['fired'] == 1 and value['faulted'] == 0 and not value['triggered']
    assert value['dropped_notes'] == {'count': 2, 'top_reasons': [{'reason': 'form_instruction', 'count': 2}]}


def test_signature_limit_message_bounds_most_frequent_call_and_lint_shape():
    items = []
    for index in range(8):
        row = {'hook': 'before_call', 'step': None, 'kind': 'crash:exception', 'exc_type': 'ValueError',
               'message': ('A' if index < 3 else str(index)) * 500, 'line': 2,
               'arguments': {'view': {'number': index}, 'state': None}}
        items.append({'task_id': 'run-%d' % index, 'first': {'applies': True, 'faults': [row]}, 'second': {}})
    report = {'checks': [{'check': 'C6', 'detail': {'items': items}}]}
    result = ff.summarize(procedure(), report)
    assert len(result['signatures']) == 5 and result['signatures'][0]['items'] == 3
    assert all(len(row['message']) == 300 for row in result['signatures'])
    assert result['example_call']['arguments']['view'] == {'number': 0}
    lint = ff.summarize(procedure(), report, limit=3, example=False)
    assert 'example_call' not in lint
    row = {key: lint[key] for key in ('signatures', 'dropped_notes')}
    row.update(fired_items=lint['fired'], faulted_items=lint['faulted'])
    assert ff.lint_details_ok(row)
    row['signatures'][0]['arguments'] = {'view': 'not allowed in lint'}
    assert not ff.lint_details_ok(row)


def test_argument_snapshot_is_exact_when_small_and_json_bounded_when_large():
    view, state = {'text': 'authored'}, {'visited': []}
    args = ff.capture_arguments('before_call', [view, state])
    view['text'], state['visited'] = 'mutated', ['cabinet']
    assert args == {'view': {'text': 'authored'}, 'state': {'visited': []}}
    args = ff.capture_arguments('before_call', [{'text': '\\"' * 10_000}, ['x' * 2000]])
    assert args['view']['truncated'] and args['state']['truncated']
    assert len(json.dumps(args['view'], ensure_ascii=False, sort_keys=True)) <= 4000
    assert len(json.dumps(args['state'], ensure_ascii=False, sort_keys=True)) <= 1000


@pytest.mark.parametrize('configuration', ['zebra-pc-v7', 'alfworld-v4'])
def test_older_c6_records_remain_byte_identical_when_capture_disabled(configuration):
    bench = p.active_benches(configuration)[0]
    source = ('def before_call(view, state):\n    return view["question"].splitlines()[999]\n'
              if bench == 'zebralogic' else 'def alf_before_step(view, state):\n    return state.get("x")\n')
    proc = procedure(source, origin=bench, hooks=('before_call',) if bench == 'zebralogic' else ('alf_before_step',))
    entries = zebra_entries() if bench == 'zebralogic' else [replay.inputs_of(alf_trajectory())]
    old, _ = replay.zero_crash(proc, entries, SeedWorkers())
    explicit, _ = replay.zero_crash(proc, entries, SeedWorkers(), capture_faults=False)
    assert json.dumps(old, sort_keys=True) == json.dumps(explicit, sort_keys=True)
    assert 'task_id' not in old['items'][0]
    assert set(old['items'][0]['first']['faults'][0]) == {'hook', 'step', 'kind', 'detail'}


def test_c6b_predicate_capture_keeps_type_line_arguments_without_extra_calls():
    ctx, _ = context(configuration='zebra-pc-v8')
    workers = SeedWorkers()
    ctx.workers, ctx.routing_workers = workers, workers.routing
    proposed = change(ctx, 'def applies(view):\n    raise ValueError("predicate fixture")\n'
                          'def before_call(view, state):\n    return {}\n')
    checked = engineer.check(proposed, ctx)
    detail = next(row['detail'] for row in checked['checks'] if row['check'] == 'C6b')
    capture = detail['captures'][0]
    assert capture['applies'] is None and len(capture['faults']) == 1
    fault = capture['faults'][0]
    assert fault['exc_type'] == 'ValueError' and fault['line'] == 2 and fault['message'] == 'predicate fixture'
    assert fault['arguments'] == {'view': PUBLIC}
    assert len([call for call in workers.calls if call[1] == 'applies']) == 3
    assert ff.summarize(proposed.procedure, checked)['fired'] == 0
