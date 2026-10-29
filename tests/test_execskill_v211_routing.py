"""Four-bench main-v4 hook/effect and delivered coverage fixtures; no services."""
from dataclasses import replace
from types import SimpleNamespace
import hashlib
import json

import pytest

from skillopt.execskill import engineer, policy, profiles as p, replay, solver, step, v211_effects
from skillopt.execskill.package import empty, FIXTURE, Package
from tests.test_execskill_v24_engineer import Workers
from tests.test_execskill_v28_execution import procedure
from tests.test_execskill_replay import trajectory, SHEET_VIEW, precheck
from tests.execskill_fakes_env import Script, FakeSandbox

QA = {'question': 'Count 17 baskets.', 'context': ['There are 17 baskets.']}
BINDING = 'def bindings(view):\n    return {"bindings": [{"name": "count", "value": "17", "quote": "17 baskets"}]}\n'
FEEDBACK = 'def sheet_feedback(view, report, state):\n    return {"fields": {}, "request_repair": True}\n'
FACT = 'def before_call(view, state):\n    return {"facts": ["There are 17 baskets."]}\n'


def proc(source, hooks, bench='searchqa', **kwargs):
    return replace(procedure(source=source, origin=bench, hooks=hooks, **kwargs), policy_version=policy.POLICY_VERSION_V29)


def context(bench='searchqa', *, n=1, report=None):
    view = SHEET_VIEW if bench == 'spreadsheetbench' else QA
    field = 'instruction' if bench == 'spreadsheetbench' else 'question'
    values = [trajectory('cell-%d' % i, bench, 'item-%d' % i, 'fail',
                         [{**view, field: view[field] + '\nFixture index %d' % i}], report=report) for i in range(n)]
    worker = Workers()
    return SimpleNamespace(configuration=p.MAIN_V4, bench=bench, k=1, trajectories=values,
        routing_items=[(t['task_id'], replay.inputs_of(t)['view']) for t in values],
        routing_workers=worker.routing, mode='train'), worker


def test_binding_only_effect_works_over_full_300_run_set():
    ctx, workers = context(n=300)
    found = engineer._routing_checks(proc(BINDING, ('bindings',)), ctx)
    assert found['C6b'][1]['items'] == found['C6b'][1]['fires_on'] == 300
    assert found['C6c'][0] and found['C6c'][1]['effects']['bindings'] == 300
    assert len([c for c in workers.calls if c[1] == 'bindings']) == 300


@pytest.mark.parametrize('bench', p.QA)
def test_each_qa_before_call_and_bindings_correct_public_view(bench):
    ctx, _ = context(bench)
    result = engineer._routing_checks(proc(FACT + BINDING, ('before_call', 'bindings'), bench), ctx)
    assert result['C6c'][1]['effects'] == {'before_call': 1, 'bindings': 1, 'sheet_feedback': 0, 'request_repair': 0}


def test_sheet_repair_only_effect_uses_existing_report_without_program():
    ctx, workers = context('spreadsheetbench', report=precheck('exception', 'KeyError', 'missing Total'))
    result = engineer._routing_checks(proc(FEEDBACK, ('sheet_feedback',), 'spreadsheetbench', requests_second_call=True), ctx)
    assert result['C6c'][0] and result['C6c'][1]['effects']['request_repair'] == 1
    assert result['C6c'][1]['effects']['sheet_feedback'] == 0
    call = next(c for c in workers.calls if c[1] == 'sheet_feedback')
    assert set(call[2][1]) == {'status', 'exc_type', 'message', 'answer_cells'}
    assert 'previous_program' not in str(call[2])


def test_sheet_feedback_without_repair_is_not_delivered_effect_and_missing_report_is_explicit():
    source = FEEDBACK.replace('{}, "request_repair": True', '{"facts": ["The report contains an error."]}, "request_repair": False')
    ctx, _ = context('spreadsheetbench', report=precheck('exception'))
    result = engineer._routing_checks(proc(source, ('sheet_feedback',), 'spreadsheetbench'), ctx)
    assert not result['C6c'][0]
    ctx, _ = context('spreadsheetbench')
    result = engineer._routing_checks(proc(FEEDBACK, ('sheet_feedback',), 'spreadsheetbench', requests_second_call=True), ctx)
    assert result['C6c'][1]['missing_precheck'] == 1


def test_generated_items_count_but_never_become_fault_examples():
    from skillopt.execskill import fault_feedback
    source = 'def before_call(view,state):\n    return 17\n'
    ctx, _ = context()
    ctx.routing_items.insert(0, ('generated-private', {'question': 'DO NOT DISCLOSE'}))
    procedure = proc(source, ('before_call',))
    checked = engineer._routing_checks(procedure, ctx)
    report = {'checks': [{'check': key, 'detail': value[1]} for key, value in checked.items()]}
    summary = fault_feedback.summarize(procedure, report, configuration=p.MAIN_V4)
    assert summary['fired'] == summary['faulted'] == 2
    assert summary['example_call']['task_id'] == 'item-0'
    assert 'generated-private' not in str(summary) and 'DO NOT DISCLOSE' not in str(summary)


def delivered_trace(bench='searchqa', *, hook='before_call', valid=True, purpose='first'):
    source = FACT if hook == 'before_call' else BINDING
    procedure = proc(source, (hook,), bench)
    package = replay.solo(procedure)
    fields = {'facts': ['There are 17 baskets.']} if hook == 'before_call' else {
        'bindings': [{'name': 'count', 'value': '17', 'quote': '17 baskets'}]}
    worker = FakeSandbox({procedure.id: {hook: lambda *args: fields}})
    call = Script(['<answer>17</answer>'])
    prediction = solver.solve(bench, QA, 'Instruction', package, call, worker=worker, configuration=p.MAIN_V4)
    shell = prediction['shell']
    trace = {'task_id': 'item', 'calls': [{'purpose': purpose, 'user': call.requests[0][1],
        'request_sha256': 'r', 'receipt': {'delivery': 'delivered' if valid else 'not_delivered'}}], 'shell': shell}
    return procedure, package, trace


@pytest.mark.parametrize('hook', ['before_call', 'bindings'])
@pytest.mark.parametrize('valid', [True, False])
def test_delivered_fields_coverage_and_undelivered_exclusion(hook, valid):
    procedure, package, trace = delivered_trace(hook=hook, valid=valid)
    st = SimpleNamespace(bench='searchqa', setting=SimpleNamespace(configuration=p.MAIN_V4))
    cells = {("S'", 'item'): [{'cell': {'id': 'c'}, 'faults': []}]}
    out = v211_effects.coverage(st, procedure.id, ['item'], package, cells, {'c': trace}, [], set(), {})
    assert out['with_notes'] == int(valid)
    assert out['fields']['bindings' if hook == 'bindings' else 'facts'] == int(valid)


def test_identical_request_coverage_requires_exact_hash_and_candidate_attribution():
    procedure, package, trace = delivered_trace()
    st = SimpleNamespace(bench='searchqa')
    captured = {'item': {'request_sha256': 'r', 'fields': {procedure.id: {'facts'}}}}
    out = v211_effects.coverage(st, procedure.id, ['item'], package, {}, {}, [trace], {'item'}, captured)
    assert out['with_notes'] == 1
    captured['item']['request_sha256'] = 'different'
    assert v211_effects.coverage(st, procedure.id, ['item'], package, {}, {}, [trace], {'item'}, captured)['with_notes'] == 0


def test_cap_dropped_and_stale_source_notes_are_not_credited():
    procedure, package, trace = delivered_trace()
    rows = trace['shell']['notes']
    request = json.loads(trace['calls'][0]['user'])
    rows[0]['delivered_text'] = ''
    assert not step._shown_note_fields('searchqa', package, rows, QA, request[p.NOTES_KEY], configuration=p.MAIN_V4)
    rows[0]['delivered_text'] = request[p.NOTES_KEY]
    rows[0]['source_sha256'] = 'stale'
    assert not step._shown_note_fields('searchqa', package, rows, QA, request[p.NOTES_KEY], configuration=p.MAIN_V4)


def test_sheet_repair_effect_credits_only_permitted_matching_source_after_assembly():
    dropped = replace(proc(FEEDBACK, ('sheet_feedback',), 'spreadsheetbench', requests_second_call=True),
                      id='fx-cap-dropped', max_note_chars=1)
    kept = replace(dropped, id='fx-kept', max_note_chars=1500)
    package = Package((dropped, kept), 'fixture', FIXTURE)
    worker = FakeSandbox({dropped.id:{'sheet_feedback':lambda *args:{
        'fields':{'facts':['The public report raised an exception.']},'request_repair':True}},
        kept.id:{'sheet_feedback':lambda *args:{'fields':{},'request_repair':True}}})
    shell = solver._Shell('spreadsheetbench',package,None,worker,withhold=(),restore=(),
        placebo=None,text=None,native=None,nominal=None,configuration=p.MAIN_V4)
    shell.start('cell')
    shell.route_on(SHEET_VIEW)
    _, requested = shell.feedback(SHEET_VIEW,precheck('exception'))
    assert requested and [row['permitted'] for row in shell.effects]==[False,True]
    trace = {'task_id':'item','shell':shell.record(),'calls':[{'purpose':'repair',
        'user':json.dumps(SHEET_VIEW),'receipt':{'delivery':'delivered'}}]}
    cells = {("S'",'item'):[{'cell':{'id':'c'},'faults':[]}]}
    count = lambda pid:v211_effects.coverage(SimpleNamespace(bench='spreadsheetbench'),pid,['item'],
        package,cells,{'c':trace},[],set(),{})['repair_requests']
    assert count(dropped.id)==0 and count(kept.id)==1
    trace['shell']['effects'][1]['source_sha256']='stale'
    assert count(kept.id)==0

# Full engineer orchestration on real child Contexts, with authored role replies and in-process workers.
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v29_audit import Judge


def engineer_context(bench, *, mode='train', n=1):
    partial, workers = context(bench, n=n, report=precheck('exception', 'ValueError', 'Public failure'))
    from skillopt.execskill import instruction_start
    parent = empty(step='D/s0', evidence=FIXTURE)
    ctx = engineer.Context(bench=bench, k=1, step='D/s1-' + bench, evidence=FIXTURE, parent=parent,
        trajectories=partial.trajectories, current=partial.trajectories if mode == 'train' else [],
        corpora={}, workers=workers, roles=WireRoles(), label='D/s1-' + bench + '/engineer-r1',
        configuration=p.MAIN_V4, card=instruction_start.pins()[bench]['text'], mode=mode, round=1 if mode == 'train' else 0,
        base=parent if mode == 'train' else None, routing_items=partial.routing_items,
        routing_workers=workers.routing, routing_shared_worker=bench != 'spreadsheetbench',
        audit_judges={'G': Judge(), 'D': Judge()})
    return ctx


def encoded(ctx, source):
    if source is None:
        return 'Malformed authored reply.'
    entry = {'kind': 'new', 'description': 'Compute public input facts.', 'max_note_chars': 1500,
             'requests_second_call': 1 if ctx.bench == 'spreadsheetbench' else 0,
             'excluded_benches': [bench for bench in p.BENCHES if bench != ctx.bench]}
    return engineer_reply({'changes': [entry]}, [source])


def engineer_run(bench, *sources, mode='train', spent=0, n=1):
    ctx = engineer_context(bench, mode=mode, n=n)
    ctx.spent = spent
    analysts = min(p.TRAIN_ANALYST_CALLS, (len(ctx.current) + p.TRAIN_ANALYST_BATCH - 1) // p.TRAIN_ANALYST_BATCH)
    ctx.roles = WireRoles(([engineer_reply({'findings': []}, [])] * analysts if mode == 'train' else [])
                         + [encoded(ctx, source) for source in sources])
    package, record = engineer.run_train(ctx) if mode == 'train' else engineer.run(ctx)
    return ctx, package, record


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'livemath', 'spreadsheetbench'])
@pytest.mark.parametrize('mode', ['train', 'single'])
def test_full_child_engineer_fault_repair_uses_correct_hooks_before_both_auditors(bench, mode):
    bad = ('def sheet_feedback(view, report, state):\n    return report["missing"]\n' if bench == 'spreadsheetbench'
           else 'def bindings(view):\n    return view["missing"]\n')
    good = FEEDBACK if bench == 'spreadsheetbench' else BINDING
    ctx, package, record = engineer_run(bench, bad, good, mode=mode)
    assert package is not None and package.procedures[0].source.strip() == good.strip()
    assert record['fault_repair_calls'] == 1 and record['inert_repair_calls'] == 0
    assert record['changes'][0]['fault_repair']['final']['faulted'] == 0
    assert record['version'] == p.kind('engineer-v2-11')
    assert record['audits'] and all(bench in audit['coverage_by_bench'] for audit in record['audits'])
    assert all('ZebraLogic' not in wire['system'] and 'ALFWorld' not in wire['system'] for wire in ctx.roles.wire)


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'livemath', 'spreadsheetbench'])
def test_one_child_inert_attempt_with_format_retry_can_create_binding_or_repair_effect(bench):
    bad = ('def sheet_feedback(view, report, state):\n    return {"fields": {}, "request_repair": False}\n'
           if bench == 'spreadsheetbench' else 'def before_call(view,state):\n    return {}\n')
    good = FEEDBACK if bench == 'spreadsheetbench' else BINDING
    _, package, record = engineer_run(bench, bad, None, good)
    assert package is not None and record['inert_repair_calls'] == 1
    assert len(record['format_retries']) == 1
    assert record['changes'][0]['inert_repair']['stop_reason'] == 'fixed'


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'livemath', 'spreadsheetbench'])
def test_child_budget_stop_preserves_original_fault_evidence(bench):
    source = ('def sheet_feedback(view, report, state):\n    return report["missing"]\n'
              if bench == 'spreadsheetbench' else 'def before_call(view,state):\n    return view["missing"]\n')
    _, package, record = engineer_run(bench, source, mode='single', spent=30)
    assert package is None and record['fault_repair_calls'] == 0
    assert record['changes'][0]['fault_repair']['stop_reason'] == 'no_calls_left'
    assert record['changes'][0]['fault_repair']['faulted'] == 1


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'livemath', 'spreadsheetbench'])
def test_actual_next_round_context_accepts_child_coverage_and_rejects_wrong_benchmark(bench):
    ctx = engineer_context(bench)
    coverage = {'items': 1, 'with_notes': 0, 'fields': {key: 0 for key in p.NOTE_FIELDS} if hasattr(p, 'NOTE_FIELDS') else
                {key: 0 for key in ('facts','table','candidates','warnings','bindings')}, 'faults': 0,
                'bench': bench, 'repair_requests': int(bench == 'spreadsheetbench'), 'phases': {'first': 0, 'repair': 0}}
    feedback = {'adopted': False, 'reason': 'gain:fixed_over_broken', 'items': 1, 'fixed': 0, 'broken': 0,
        'net': '0/1', 'need': 1, 'p_sign': 1.0, 'guards': {'own_faults': True, 'predicate_faults': True, 'format': True},
        'generated': {'items': 0, 'fixed': 0, 'broken': 0}, 'identical_items': [], 'unfixed_examples': [],
        'informational_guards': ['own_faults', 'predicate_faults'],
        'format': {'S': 0, "S'": 0, 'margin': 0, 'blocked': False, 'examples': []},
        'procedures': [{'id': 'fx-child', 'change': 'added', 'enabled_items': 1, 'fixed': 0, 'broken': 0,
            'examples': [], 'notes_coverage': coverage, 'faults': {'cells': 0, 'signatures': []}}]}
    next_ctx = replace(ctx, round=2, training=feedback)
    assert engineer.payload(next_ctx)['training']['procedures'][0]['notes_coverage'] == coverage
    feedback['procedures'][0]['notes_coverage']['items'] = 'invalid'
    with pytest.raises(ValueError, match='training feedback'):
        replace(ctx, round=2, training=feedback)
    feedback['procedures'][0]['notes_coverage']['items'] = 1
    feedback['procedures'][0]['notes_coverage']['bench'] = 'other'
    with pytest.raises(ValueError, match='training feedback'):
        replace(ctx, round=2, training=feedback)


def test_generated_exception_text_never_reaches_child_fault_feedback_or_check_records():
    from skillopt.execskill import fault_feedback
    ctx, _ = context()
    ctx.routing_items.insert(0, ('generated-item', {'question': 'GENERATED SECRET'}))
    source = 'def before_call(view,state):\n    raise ValueError(view["question"])\n'
    procedure = proc(source, ('before_call',))
    checks = engineer._routing_checks(procedure, ctx)
    report = {'checks': [{'check': key, 'detail': value[1]} for key, value in checks.items()]}
    summary = fault_feedback.summarize(procedure, report, configuration=p.MAIN_V4)
    assert summary['faulted'] == 2 and 'GENERATED SECRET' not in str(report) + str(summary)


def partial_source(bench, faults, label):
    field = 'instruction' if bench == 'spreadsheetbench' else 'question'
    signature = 'sheet_feedback(view, report, state)' if bench == 'spreadsheetbench' else 'before_call(view, state)'
    output = ('{"fields": {"facts": [%r]}, "request_repair": True}' if bench == 'spreadsheetbench'
              else '{"facts": [%r]}') % label
    return ('def %s:\n    index = int(view[%r].splitlines()[-1].split()[-1])\n'
            '    if index < %d:\n        raise ValueError("Authored fault")\n    return %s\n') % (signature, field, faults, output)


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'livemath', 'spreadsheetbench'])
def test_child_two_fault_repairs_retain_strict_best_and_restore_audit_source(bench):
    sources = [partial_source(bench, n, text) for n, text in [(2, 'Initial'), (1, 'Kept'), (2, 'Rejected')]]
    _, package, record = engineer_run(bench, *sources, n=10)
    repair = record['changes'][0]['fault_repair']
    assert package.procedures[0].source.strip() == sources[1].strip()
    assert repair['kept_index'] == 1 and repair['stop_reason'] == 'no_improvement'
    assert repair['final']['faulted'] == 1 and record['fault_repair_calls'] == 2
    assert all('Rejected' not in pair['requests']['G']['user']
               for result in record['audits'] for pair in result['requests'])


@pytest.mark.parametrize('n,triggered', [(10, True), (11, False)])
def test_child_fault_threshold_is_at_least_ten_percent(n, triggered):
    source = partial_source('searchqa', 1, 'Public facts')
    _, _, record = engineer_run('searchqa', source, partial_source('searchqa', 0, 'Repaired'), n=n)
    repair = record['changes'][0]['fault_repair']
    assert repair['triggered'] is triggered and repair['threshold'] == (1 if n == 10 else 2)
