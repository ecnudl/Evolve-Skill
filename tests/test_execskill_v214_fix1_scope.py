"""Mixed-chain procedure scope with authored inputs and in-process workers only."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import audit, engineer, fault_feedback, profiles as p, replay, step, v211_audit
from skillopt.execskill.package import Package, empty, procedure_input_benches
from tests.test_execskill_replay import SHEET_VIEW, trajectory, test_case as replay_test_case
from tests.test_execskill_v24_engineer import PUBLIC, Workers, stored, context as engineer_context
from tests.test_execskill_v211_audit import cell_fixture
from tests.test_execskill_v211_routing import FACT, context as routing_context, proc

CHILD = p.MAIN_V5
SHEET = 'def before_call(view,state):\n    return {"facts": [view["instruction"]]}\n'


def mixed():
    return [trajectory('sheet', 'spreadsheetbench', 'sheet-item', 'fail', [SHEET_VIEW]),
            stored(key='zebra-item', cell='zebra')]


def inputs():
    return [replay.inputs_of(trace) for trace in mixed()]


@pytest.mark.parametrize('origin,expected', [('spreadsheetbench', ['sheet']), ('zebralogic', ['sheet', 'zebra'])])
def test_engineer_scope_and_prebuild_resolution_share_intrinsic_scope(origin, expected):
    procedure = proc(FACT, ('before_call',), origin)
    candidate = replay.solo(procedure)
    ctx = SimpleNamespace(configuration=CHILD, bench=origin, mode='train',
                          trajectories=mixed(), current=[])
    assert list(engineer._scope(ctx, candidate, procedure)) == expected
    assert list(engineer._scope_entries(ctx, set())) == expected
    ctx.current = [stored(key='current-zebra', cell='current-zebra')]
    assert ('current-zebra' in engineer._scope(ctx, candidate, procedure)) == (origin == 'zebralogic')


def test_package_narrowing_and_procedure_exclusions_both_apply():
    procedure = proc(FACT, ('before_call',), 'zebralogic', excluded_benches=('searchqa',))
    assert 'zebralogic' in procedure_input_benches(procedure)
    assert 'searchqa' not in procedure_input_benches(procedure)
    assert 'spreadsheetbench' not in procedure_input_benches(procedure, excluded=('spreadsheetbench',))
    ctx = SimpleNamespace(configuration=CHILD, bench='zebralogic', mode='train', trajectories=mixed(), current=[])
    package = SimpleNamespace(excluded=lambda _: ('spreadsheetbench',))
    assert list(engineer._scope(ctx, package, procedure)) == ['zebra']


@pytest.mark.parametrize('configuration,expected,faults', [(CHILD, ['sheet'], 0), (p.MAIN_V4, ['sheet', 'zebra'], 2)])
def test_sheet_helper_never_reads_zebra_and_old_replay_behavior_stays_exact(configuration, expected, faults):
    procedure, workers = proc(SHEET, ('before_call',), 'spreadsheetbench'), Workers()
    report, outcomes = replay.zero_crash(procedure, inputs(), workers,
                                        configuration=configuration, capture_faults=True)
    assert list(outcomes) == expected
    assert report['trajectories'] == len(expected) and report['fault_count'] == faults
    if configuration == CHILD:
        assert [row['bench'] for row in report['items']] == ['spreadsheetbench']
        assert all('instruction' in args[0] for _, _, args in workers.calls)
        summary = fault_feedback.summarize(procedure, {'checks': [{'check': 'C6', 'detail': report}]},
                                           configuration=CHILD, bench='spreadsheetbench')
        assert summary['faulted'] == 0 and not summary['triggered']
    else:
        assert all('bench' not in row for row in report['items'])


def test_zebra_origin_replays_all_inherited_benches_and_explicit_exclusions():
    workers = Workers()
    procedure = proc(FACT, ('before_call',), 'zebralogic')
    assert list(replay.replay_many(procedure, inputs(), workers, configuration=CHILD)) == ['sheet', 'zebra']
    assert list(replay.replay_many(replace(procedure, excluded_benches=('spreadsheetbench',)), inputs(),
                                   workers, configuration=CHILD)) == ['zebra']


def test_out_of_scope_direct_replay_never_calls_worker_or_exposes_view():
    class Forbidden:
        def call(self, *args, **kwargs):
            pytest.fail('An impossible procedure scope must not execute')
    found = replay.replay(Forbidden(), proc(SHEET, ('before_call',), 'spreadsheetbench'),
                          inputs()[1], configuration=CHILD)
    assert found.applies is False and not found.faults and not found.values


def test_full_sheet_engineer_check_never_replays_earlier_zebra():
    from skillopt.execskill import instruction_start
    ctx, workers = engineer_context(configuration=p.MAIN_V2_3, bench='officeqa')
    ctx = replace(ctx, configuration=CHILD, bench='spreadsheetbench', routing_shared_worker=False,
                  card=instruction_start.pins()['spreadsheetbench']['text'])
    ctx.trajectories = mixed()
    ctx.routing_items = [('sheet-item', SHEET_VIEW)]
    change = engineer.Change(1, 'new', {'kind': 'new', 'description': 'Reads the visible spreadsheet instruction.',
        'hooks': ['before_call'], 'max_note_chars': 1500,
        'excluded_benches': [bench for bench in p.BENCHES if bench != 'spreadsheetbench'],
        'replay_tests': []}, SHEET, 'a' * 64)
    report = engineer.check(change, ctx)
    crash = next(row['detail'] for row in report['checks'] if row['check'] == 'C6')
    assert crash['trajectories'] == 1 and crash['fault_count'] == 0
    assert all('instruction' in args[0] for _, _, args in workers.calls)
    assert fault_feedback.summarize(change.procedure, report, configuration=CHILD,
                                    bench=ctx.bench)['faulted'] == 0


def test_mutation_replay_rejects_out_of_scope_reference_before_worker():
    case = replay_test_case('zebra', 'before_call', {'kind': 'note_contains', 'value': 'visible'},
                            mutation='strip_digits')
    procedure = proc(FACT, ('before_call',), 'spreadsheetbench', replay_tests=(case,))
    workers = Workers()
    report = replay.run_tests(procedure, {row['cell']: row for row in inputs()}, {}, workers,
                              configuration=CHILD)
    assert not report['passed'] and report['problems'][0]['reason'] == 'invalid_test'
    assert not workers.opened


@pytest.mark.parametrize('bench,excluded', [('zebralogic', ()), ('spreadsheetbench', ('spreadsheetbench',))])
def test_routing_checks_open_no_workers_for_impossible_scope(bench, excluded):
    ctx, workers = routing_context('spreadsheetbench')
    ctx.configuration, ctx.bench = CHILD, bench
    procedure = proc(SHEET, ('before_call',), 'spreadsheetbench', excluded_benches=excluded)
    found = engineer._routing_checks(procedure, ctx)
    assert found['C6b'][1]['items'] == found['C6b'][1]['fires_on'] == 0
    assert not workers.opened and len(ctx.routing_items) == 1


def fault(procedure):
    return {'procedure': procedure.id, 'hook': 'before_call', 'kind': 'crash:exception',
            'exc_type': 'KeyError', 'message': 'Authored scope failure', 'arguments': {'view': 'public'}}


def test_fault_feedback_filters_mixed_artifacts_by_entry_scope():
    procedure = proc(FACT, ('before_call',), 'spreadsheetbench')
    rows = [{'task_id': bench, 'bench': bench, 'first': {'applies': True, 'faults': [fault(procedure)]}}
            for bench in ('zebralogic', 'spreadsheetbench')]
    report = {'checks': [{'check': 'C6', 'detail': {'items': rows}}]}
    found = fault_feedback.summarize(procedure, report, configuration=CHILD, bench='spreadsheetbench')
    assert found['fired'] == found['faulted'] == 1
    assert 'zebralogic' not in str(found)
    unscoped = deepcopy(report)
    for row in unscoped['checks'][0]['detail']['items']:
        row.pop('bench')
    assert fault_feedback.summarize(procedure, unscoped, configuration=CHILD)['fired'] == 0


def test_zebra_origin_on_sheet_keeps_v211_generated_fault_example_restriction():
    ctx, _ = routing_context('spreadsheetbench')
    ctx.configuration = CHILD
    ctx.routing_items.insert(0, ('generated-private', SHEET_VIEW))
    procedure = proc('def before_call(view,state):\n    return 17\n', ('before_call',), 'zebralogic')
    checked = engineer._routing_checks(procedure, ctx)
    report = {'checks': [{'check': key, 'detail': value[1]} for key, value in checked.items()]}
    found = fault_feedback.summarize(procedure, report, configuration=CHILD, bench=ctx.bench)
    assert found['fired'] == found['faulted'] == 2
    assert found['example_call']['task_id'] == 'item-0'
    assert 'generated-private' not in str(found)


def test_mixed_replay_audit_uses_each_entry_parent_and_intrinsic_scope():
    traces, entries = mixed(), inputs()
    outcomes = {row['cell']: replay.Outcome(row['cell'], row['bench'], applies=True,
                notes=[{'hook': 'before_call', 'step': None, 'text': 'The visible instruction was read.'}])
                for row in entries}
    raw = {row['cell']: row for row in traces}
    sheet = proc(FACT, ('before_call',), 'spreadsheetbench')
    rows = audit.situations_from_replays(sheet, entries, outcomes, configuration=CHILD, trajectories=raw)
    assert len(rows) == 1 and rows[0]['bench'] == 'spreadsheetbench'
    zebra = proc(FACT, ('before_call',), 'zebralogic')
    rows = audit.situations_from_replays(zebra, entries, outcomes, configuration=CHILD, trajectories=raw)
    assert [row['cell'] for row in rows] == ['sheet', 'zebra']
    assert 'delivered_note_identity' in rows[0] and 'delivered_note_identity' not in rows[1]


def test_cell_audit_filters_excluded_procedure_before_frozen_adapter_without_mutating_trace():
    procedure, trace = cell_fixture()
    excluded = replace(procedure, excluded_benches=('spreadsheetbench',))
    original = deepcopy(trace)
    assert audit.situations_from_cells([trace], replay.solo(excluded), configuration=CHILD) == []
    assert trace == original
    assert len(audit.situations_from_cells([trace], replay.solo(procedure), configuration=CHILD)) == 2
    assert len(audit.situations_from_cells([trace], replay.solo(excluded), configuration=p.MAIN_V4)) == 2


def test_zebra_cell_audit_cannot_reintroduce_sheet_origin_notes():
    procedure = proc(FACT, ('before_call',), 'spreadsheetbench')
    trace = dict(stored(), arm="S'", unit='D/s3-zebralogic/train-r1')
    trace['shell'] = {'notes': [{'id': procedure.id, 'hook': 'before_call',
                    'source_sha256': audit.text_sha256(procedure.source), 'delivered_text': 'Visible.'}]}
    from skillopt.execskill import zebralogic
    trace['calls'][0]['user'] = zebralogic.render_user(PUBLIC, notes='Visible.')
    assert not audit.situations_from_cells([trace], replay.solo(procedure), configuration=CHILD)


def test_freeze_skips_intrinsically_impossible_replay(tmp_path, monkeypatch):
    procedure = proc(SHEET, ('before_call',), 'spreadsheetbench')
    parent = empty(step='D/s0', evidence='engineering_fixture')
    candidate = Package((procedure,), 'D/s3-zebralogic', 'engineering_fixture', parent_sha256=parent.sha256)
    st = SimpleNamespace(bench='zebralogic', parent=parent, evidence='engineering_fixture', chain_root=tmp_path,
        setting=SimpleNamespace(extra={'configuration': CHILD}), label=lambda _: 'freeze',
        roles=lambda _: None, unit=lambda _, work: work(1), services=SimpleNamespace(workers=None))
    monkeypatch.setattr(step, '_run_trajectories', lambda *args, **kwargs: [mixed()[1]])
    @contextmanager
    def mounts(*args):
        yield {}
    monkeypatch.setattr(step, '_inputs_dirs', mounts)
    monkeypatch.setattr(replay, 'replay_many', lambda *args, **kwargs: pytest.fail('No impossible freeze replay'))
    lengths = []
    monkeypatch.setattr(step.describer, 'describe', lambda *args, **kwargs: lengths.append(kwargs['lengths']) or {})
    monkeypatch.setattr(step.describer, 'entries', lambda _: {})
    monkeypatch.setattr(step, 'with_describer', lambda package, _: package)
    monkeypatch.setattr(step, 'save', lambda *args: None)
    assert step._freeze(st, {}, candidate, True)['accepted']
    assert lengths == [[]]
