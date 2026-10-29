"""main-v4 audit extraction, real phase/source attribution, grouping and inherited agreement fixtures."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import audit, profiles as p, replay, v211_audit as child
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_v211_routing import proc, FACT, BINDING, FEEDBACK, QA
from tests.test_execskill_replay import SHEET_VIEW, precheck, trajectory


def situation(bench, item, *, hook='before_call', procedure=None, source='run', text='Answer only in JSON.'):
    procedure = procedure or proc(FACT, ('before_call',), bench)
    view = deepcopy(SHEET_VIEW if bench == 'spreadsheetbench' else QA)
    if bench == 'livemath':
        view = {'question': 'Q', 'choices': {'A': '17', 'B': '18'}}
    if hook == 'sheet_feedback':
        view['run_report'] = precheck('exception', 'ValueError', 'visible failure')
    return child._situation(bench=bench, item=item, cell=item + '-cell', package='package',
        source_hash=child.sha(procedure.source), hook=hook, request_hash='request-' + hook,
        raw_view=view, text=text, procedure=procedure.id, source=source)


def run(bench='searchqa', *, count=16, g=None, d=None, final=False, rows=None, procedures=None):
    procedures = procedures or [proc(FACT, ('before_call',), bench)]
    if rows is None:
        rows = [situation(bench, str(i), procedure=procedures[0], hook=hook)
                for i in range(count) for hook in (('before_call', 'sheet_feedback') if bench == 'spreadsheetbench' else ('before_call', 'bindings'))]
    return audit.run_audit(procedures, rows, {'G': g or Judge(), 'D': d or Judge()}, bench=bench,
        configuration=p.MAIN_V4, step='G/s1-' + bench, round=1, change_id='1', final=final)


@pytest.mark.parametrize('bench,count,calls', [('searchqa',16,5), ('officeqa',16,5), ('livemath',16,5), ('spreadsheetbench',12,7)])
def test_item_group_batching_matches_caps_and_keeps_both_hooks(bench, count, calls):
    g, d = Judge(), Judge()
    result = run(bench, count=count, g=g, d=d)
    assert len(g.calls) == len(d.calls) == calls
    assert result['sampling']['batch_unit'] == 'item_group'
    assert result['sampling']['sampled_items'] == count
    assert result['coverage_by_bench'][bench]['does_not_certify_other_benches']
    if bench == 'spreadsheetbench':
        for pair in result['requests'][1:]:
            text = pair['requests']['G']['user']
            assert text.count('phase first') == text.count('phase repair') == 2
    assert all('public_view_disclosure' in pair['requests']['G'] for pair in result['requests'])


def test_truncated_unverifiable_is_not_violation_and_missing_coverage_explicit():
    result = run(count=1, g=Judge(truth='unverifiable'), d=Judge(truth='unverifiable'))
    assert not result['confirmed'] and result['audit_incomplete']
    assert result['coverage_by_bench']['searchqa']['shortfall'] == 11


def test_both_judges_same_note_agreement_and_one_retry_preserved():
    result = run(count=12, g=Judge(truth='false', invalid=1), d=Judge(policy='P3'))
    assert any(row['kind'] == 'note' for row in result['confirmed'])
    assert len(result['requests'][0]['requests']['G']['retries']) == 1


def test_request_too_large_refuses_both_judges_without_silently_dropping_notes():
    rows = [situation('searchqa', 'item', text='X' * 65000)]
    g, d = Judge(), Judge()
    result = run(rows=rows, g=g, d=d)
    assert len(g.calls) == len(d.calls) == 1  # A only; B is explicitly unavailable.
    assert result['audit_incomplete'] and result['incomplete_units']
    assert result['requests'][1]['requests']['G']['unavailable_reason'] == 'audit_input_limit_after_public_truncation'


def cell_fixture(*, repair=True, delivered=True):
    procedure = proc(FACT + BINDING + FEEDBACK, ('before_call', 'bindings', 'sheet_feedback'), 'spreadsheetbench', requests_second_call=True)
    shell = {'notes': [], 'precheck': precheck('exception', 'ValueError', 'Public failure'), 'effects': []}
    calls = []
    for hook, purpose in [('before_call', 'first'), ('sheet_feedback', 'repair')]:
        text = 'Visible ' + hook + '.'
        shell['notes'].append({'id': procedure.id, 'hook': hook, 'source_sha256': child.sha(procedure.source), 'delivered_text': text})
        request = {**SHEET_VIEW, p.NOTES_KEY if purpose == 'first' else 'repair_notes': text}
        if purpose == 'repair':
            request.update(previous_program='PRIVATE PROGRAM', run_report={'status': 'exception'})
        if purpose == 'first' or repair:
            calls.append({'purpose': purpose, 'request_sha256': 'hash-' + purpose, 'user': json.dumps(request),
                          'receipt': {'delivery': 'delivered' if delivered else 'not_delivered'}})
    trace = {'bench': 'spreadsheetbench', 'arm': "S'", 'arm_kind': 'candidate', 'unit': 'G/s4-spreadsheetbench/train-r1',
             'task_id': 'item', 'cell': 'cell', 'package_sha256': 'package', 'calls': calls, 'shell': shell,
             'package_procedures': {procedure.id: child.sha(procedure.source)}}
    return procedure, trace


def test_sheet_cell_extraction_preserves_phase_request_source_and_hides_program():
    procedure, trace = cell_fixture()
    rows = audit.situations_from_cells([trace], SimpleNamespace(procedures=[procedure]), configuration=p.MAIN_V4)
    assert [r['phase'] for r in rows] == ['first', 'repair']
    assert [r['request_sha256'] for r in rows] == ['hash-first', 'hash-repair']
    assert 'run_report' not in rows[0]['view'] and rows[1]['view']['run_report']['message'] == 'Public failure'
    assert 'PRIVATE PROGRAM' not in str(rows)
    for row in rows:
        assert all(key in row for key in ('bench','item','cell','package_sha256','procedure_source_sha256','hook','phase',
            'request_sha256','source','public_view_sha256','delivered_note_identity','truncation'))


@pytest.mark.parametrize('tamper,expected', [('no_repair',1),('undelivered',0),('source',0),('package_source',0),('outside_request',1)])
def test_undelivered_and_stale_source_notes_never_become_final_audit_evidence(tamper, expected):
    procedure, trace = cell_fixture(repair=tamper != 'no_repair', delivered=tamper != 'undelivered')
    if tamper == 'source':
        for row in trace['shell']['notes']:
            row['source_sha256'] = 'other'
    if tamper == 'package_source':
        trace['package_procedures'][procedure.id] = 'other'
    if tamper == 'outside_request':
        trace['shell']['notes'][1]['delivered_text'] = 'Never delivered'
    assert len(audit.situations_from_cells([trace], SimpleNamespace(procedures=[procedure]), configuration=p.MAIN_V4)) == expected


def test_delivered_bindings_are_audited():
    procedure, trace = cell_fixture()
    trace['bench'] = 'searchqa'
    trace['shell']['notes'] = [dict(trace['shell']['notes'][0], hook='bindings')]
    trace['calls'][0]['user'] = json.dumps({**QA, p.NOTES_KEY: trace['shell']['notes'][0]['delivered_text']})
    rows = audit.situations_from_cells([trace], SimpleNamespace(procedures=[procedure]), configuration=p.MAIN_V4)
    assert len(rows) == 1 and rows[0]['hook'] == 'bindings' and rows[0]['phase'] == 'first'


def test_replay_audit_suppresses_feedback_when_no_repair_and_pins_source_request():
    procedure = proc(FEEDBACK, ('sheet_feedback',), 'spreadsheetbench', requests_second_call=True)
    trace = trajectory('cell', 'spreadsheetbench', 'item', 'fail', [SHEET_VIEW], report=precheck('exception'))
    entry = replay.inputs_of(trace)
    outcome = SimpleNamespace(notes=[{'hook': 'sheet_feedback', 'text': 'The public run failed.', 'step': None}], repair=False)
    args = dict(configuration=p.MAIN_V4, trajectories={'cell': trace})
    assert not audit.situations_from_replays(procedure, [entry], {'cell': outcome}, **args)
    outcome.repair = True
    rows = audit.situations_from_replays(procedure, [entry], {'cell': outcome}, **args)
    assert rows[0]['phase'] == 'repair' and rows[0]['source'] == 'run' and rows[0]['replayed']
    assert rows[0]['package_sha256'] == replay.solo(procedure).sha256


def test_final_contradiction_removes_later_procedure_without_engineer_endpoint():
    a, b = proc(FACT, ('before_call',)), proc(BINDING, ('bindings',))
    from dataclasses import replace
    b = replace(b, id='fx-second')
    rows = [situation('searchqa', 'item', procedure=a), situation('searchqa', 'item', procedure=b)]
    result = run(rows=rows, procedures=[a,b], final=True, g=Judge(contradiction=True), d=Judge(contradiction=True))
    assert 'fx-second' in audit.removed_procedures(result, [a.id,b.id])
    assert set(result['tokens']) == {'G','D'}
