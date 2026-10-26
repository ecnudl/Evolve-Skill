"""Focused-review regressions for bounded v2.9.1 diagnostics; authored offline data."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer as e, engineer_v28, engineer_v291, fault_feedback as ff, profiles as p
from tests.test_execskill_v24_engineer import change, context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v29_runtime import procedure
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def wire_bytes(value):
    """Use the actual role serializer, including separators, escaping and UTF-8."""
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8'))


def maximum_source(bench='zebralogic', unit='x'):
    hook = 'alf_before_step' if bench == 'alfworld' else 'before_call'
    prefix = 'def %s(view, state):\n    raise ValueError("authored failure")  # ' % hook
    room = 24_000 - len(prefix.encode('utf-8'))
    padding = unit * (room // len(unit.encode('utf-8')))
    source = prefix + padding + 'x' * (room - len(padding.encode('utf-8')))
    assert len(source.encode('utf-8')) == 24_000
    compile(source, '<authored-max-source>', 'exec')
    return source


def five_signature_report(bench='zebralogic', *, message='m', arguments=None):
    hook = 'alf_before_step' if bench == 'alfworld' else 'before_call'
    arguments = {'view': {'question': 'Public input'}, 'state': None} if arguments is None else arguments
    entries = []
    # Distinct counts impose an unambiguous signature rank, independent of order.
    for signature in range(5):
        for item in range(5 - signature):
            fault = {'hook': hook, 'kind': 'crash:exception', 'exc_type': 'ValueError',
                     'message': str(signature) + message * 400, 'line': 2,
                     'step': 0 if bench == 'alfworld' else None, 'arguments': deepcopy(arguments)}
            value = {'applies': 'default_true', 'faults': [fault]}
            entries.append({'task_id': 'run-%d-%d' % (signature, item),
                            'first': value, 'second': deepcopy(value)})
    return {'checks': [{'check': 'C6', 'passed': True, 'informational': True,
                       'detail': {'items': entries, 'trajectories': 15, 'fault_count': 30, 'mismatched': []}}]}


def lint_extension(value):
    return {key: value[key] for key in ('signatures', 'dropped_notes', 'truncated') if key in value}


@pytest.mark.parametrize('unit', ['x', '🧩', '\\"'])
def test_source_and_context_lines_are_visibly_bounded_without_repeating_previous_context(unit):
    proc = procedure(maximum_source(unit=unit))
    report = five_signature_report()
    before = deepcopy(report)
    evidence = ff.summarize(proc, report)
    assert evidence['truncated'] is True
    assert len(evidence['signatures']) == 5
    shown = set()
    for row in evidence['signatures']:
        assert len(row['source_line']) <= 200 and row['source_line'].endswith('... [truncated]')
        contexts = row.get('source_context', [])
        assert not shown & {line['line'] for line in contexts}
        for line in contexts:
            assert len(line['text']) <= 200
            if line['line'] == 2:
                assert line['text'].endswith('... [truncated]')
        shown.update(line['line'] for line in contexts)
        shown.add(row['line'])
    assert report == before
    assert evidence == ff.summarize(proc, deepcopy(report))
    assert evidence['fired'] == evidence['faulted'] == 15 and evidence['threshold'] == 2
    assert evidence['triggered'] and evidence['per_hook'] == {'before_call': 15}


@pytest.mark.parametrize('unit', ['x', '🧩', '\\"'])
def test_lint_extension_is_bounded_by_actual_serialized_utf8_bytes(unit):
    proc = procedure(maximum_source(unit=unit))
    report = five_signature_report(message='🧩')
    value = ff.summarize(proc, report, limit=3, example=False)
    extension = lint_extension(value)
    assert extension['truncated'] is True
    assert wire_bytes(extension) <= 4000
    assert value['fired'] == value['faulted'] == 15
    assert [row['items'] for row in value['signatures']] == [5, 4, 3][:len(value['signatures'])]
    assert len(value['signatures']) < 3
    row = {**extension, 'fired_items': value['fired'], 'faulted_items': value['faulted']}
    assert ff.lint_details_ok(row)
    oversized = deepcopy(row)
    oversized['signatures'][0]['source_line'] = 'x' * 201
    assert not ff.lint_details_ok(oversized)


def manual_evidence():
    signatures = [{'hook': 'before_call', 'kind': 'crash:exception', 'exc_type': 'ValueError',
                   'message': str(index), 'line': index + 1, 'items': 3 - index, 'first_step': None,
                   'example_task_ids': ['run-' + str(index)], 'source_line': 'public source line',
                   'source_context': [{'line': 1, 'text': 'a' * 200}, {'line': 2, 'text': 'b' * 200}]}
                  for index in range(3)]
    return {'fired': 6, 'faulted': 6, 'threshold': 1, 'triggered': True, 'per_hook': {'before_call': 6},
            'signatures': signatures, 'dropped_notes': {'count': 0, 'top_reasons': []},
            'example_call': {'task_id': 'run-0', 'hook': 'before_call', 'step': None,
                             'arguments': {'view': {'question': 'Public input'}, 'state': None}}}


def test_lower_ranked_signatures_are_dropped_before_contexts_or_arguments(monkeypatch):
    original = manual_evidence()
    target = deepcopy(original)
    target.update(signatures=target['signatures'][:1], truncated=True)
    cap = wire_bytes(target)
    monkeypatch.setattr(ff, 'EVIDENCE_BYTES', cap)
    actual = ff.bound_diagnostics(original, example=True)
    assert actual == target
    assert len(original['signatures']) == 3 and 'truncated' not in original


def test_contexts_are_dropped_before_example_arguments(monkeypatch):
    original = manual_evidence()
    original['signatures'] = original['signatures'][:1]
    target = deepcopy(original)
    target['signatures'][0]['source_context'] = []
    target['truncated'] = True
    cap = wire_bytes(target)
    monkeypatch.setattr(ff, 'EVIDENCE_BYTES', cap)
    actual = ff.bound_diagnostics(original, example=True)
    assert actual['truncated'] and wire_bytes(actual) <= cap
    assert not actual['signatures'][0].get('source_context')
    assert actual['example_call'] == original['example_call']
    assert actual['signatures'][0]['source_line'] == original['signatures'][0]['source_line']


def test_unicode_arguments_are_shortened_after_contexts_and_preserve_none(monkeypatch):
    original = manual_evidence()
    original['signatures'] = original['signatures'][:1]
    original['example_call']['arguments'] = {'view': {'text': '🧩' * 3900}, 'state': None}
    monkeypatch.setattr(ff, 'EVIDENCE_BYTES', 2000)
    actual = ff.bound_diagnostics(original, example=True)
    assert actual['truncated'] and wire_bytes(actual) <= 2000
    assert len(actual['signatures']) == 1
    assert not actual['signatures'][0].get('source_context')
    assert actual['example_call']['arguments']['state'] is None
    assert actual['example_call']['arguments']['view']['truncated'] is True
    assert wire_bytes(actual['example_call']['arguments']) < wire_bytes(original['example_call']['arguments'])
    assert (actual['fired'], actual['faulted'], actual['threshold'], actual['triggered']) == (6, 6, 1, True)


@pytest.mark.parametrize('configuration', ['zebra-pc-v8', 'alfworld-v5'])
@pytest.mark.parametrize('unit', ['x', '🧩', '\\"'])
def test_three_maximum_sources_and_five_signatures_fit_next_payload_and_real_repair_requests(configuration, unit):
    bench = p.active_benches(configuration)[0]
    ctx, _ = context(configuration=configuration, bench=bench)
    changes, lint = [], []
    ctx.roles = WireRoles(['unusable'] * 3)
    arguments = ff.capture_arguments('alf_before_step' if bench == 'alfworld' else 'before_call',
        [{'question': '🧩' * 10_000, 'escaped': '\\"' * 5000}, None])
    for index in range(1, 4):
        proposed = change(ctx, maximum_source(bench, unit))
        proposed.n = index
        if bench == 'alfworld':
            proposed.entry['excluded_benches'] = []
        checked = e.check(proposed, ctx)
        assert checked['passed'] and len(proposed.procedure.source.encode('utf-8')) == 24_000
        original_report = five_signature_report(bench, message='🧩', arguments=arguments)
        # Preserve the real fatal checks but supply five authored C6 failure signatures.
        checked['checks'] = [row for row in checked['checks'] if row['check'] not in ('C6', 'C6b')]
        checked['checks'].extend(original_report['checks'])
        evidence = ff.summarize(proposed.procedure, checked)
        assert evidence['fired'] == evidence['faulted'] == 15
        assert evidence['truncated'] and wire_bytes(evidence) <= 16000
        engineer_v28.advisory_feedback(proposed, checked, configuration=configuration)
        c6 = next(row for row in checked['lint']['information'] if row['check'] == 'C6')
        assert wire_bytes(lint_extension(c6)) <= 4000 and c6['truncated']
        lint.append(checked['lint'])
        _, _, attempts, record = engineer_v291.repair(ctx, proposed, checked, max_repairs=1, format_retry=False)
        assert record['stop_reason'] == 'unparseable' and len(record['calls']) == 1 and not attempts
        assert wire_bytes(record['calls'][0]['request']['evidence']) <= 16000
        changes.append(proposed)
    # The existing package cap is64k: two24k sources can be retained, while lint
    # still reports all three proposed changes. This is the reviewer's next-round path.
    parent, kept = e._combined(ctx.parent, changes[:2], ctx.step)
    assert parent is not None and len(kept) == 2
    next_ctx = replace(ctx, round=2, parent=parent, lint=lint, current=list(ctx.trajectories))
    payload = e.payload(next_ctx)
    assert wire_bytes(payload) <= p.ROLE_INPUT_BYTES
    assert len(payload['lint']) == 3 and len(payload['package']) == 2
    assert len(ctx.roles.wire) == 3
    for request in ctx.roles.wire:
        assert '/fault-repair/' in request['label']
        assert len(request['user'].encode('utf-8')) <= p.ROLE_INPUT_BYTES
        assert len((request['system'] + request['user']).encode('utf-8')) <= 236000


def test_captured_argument_truncation_is_recorded_even_when_aggregate_fits():
    arguments = ff.capture_arguments('before_call', [{'question': 'a' * 6000}, None])
    proc = procedure()
    evidence = ff.summarize(proc, five_signature_report(arguments=arguments))
    assert evidence['truncated'] is True and wire_bytes(evidence) <= 16000
    assert evidence['example_call']['arguments']['state'] is None
    assert evidence['example_call']['arguments']['view'] == arguments['view']


def test_small_evidence_keeps_the_exact_failing_call_without_truncation():
    proc = procedure()
    report = five_signature_report(message='short')
    report['checks'][0]['detail']['items'] = report['checks'][0]['detail']['items'][:1]
    fault = report['checks'][0]['detail']['items'][0]['first']['faults'][0]
    fault['message'] = 'Authored exception'
    report['checks'][0]['detail']['items'][0]['second'] = {}
    evidence = ff.summarize(proc, report)
    assert not evidence.get('truncated')
    assert evidence['example_call']['arguments'] == fault['arguments']
    assert evidence['signatures'][0]['message'] == 'Authored exception'
