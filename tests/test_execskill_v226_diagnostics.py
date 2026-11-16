"""Accepted-step counts and unit-bound Zebra diagnostics regressions."""
from copy import copy
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import acceptance, diagnostics_runtime, engineer, policy, profiles as p
from skillopt.execskill import replay, step, units, v221_learning, v222_gate, v222_runtime
from skillopt.execskill.errors import ConfigurationError
from skillopt.execskill.package import Procedure, empty, save, with_
from tests.execskill_v226_fakes import DiagnosticsWorker, authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v215_diagnostics_runtime import VIEW, entry
from tests.test_execskill_acceptance import fast_statistics, make_cells  # noqa: F401


def zebra_procedure(number=1, expression=None):
    value = expression or '{"facts": ["Clue 6 compares positions."], "diagnostics": ["x" * 2000000]}'
    return Procedure(id='p-zebralogic-3-%d' % number, origin=p.ZEBRA,
        description='Authored diagnostic transport fixture', hooks=('applies', 'before_call'),
        source='def applies(view):\n    return True\n\ndef before_call(view, state):\n    return '+value+'\n',
        max_note_chars=600, excluded_benches=tuple(b for b in p.SUPPORTED_BENCHES if b != p.ZEBRA),
        evidence='engineering_fixture', policy_version=policy.POLICY_VERSION_V222)


def packages():
    initial = empty(step='G/s0', evidence='engineering_fixture')
    parent = with_(initial, step='G/s3-zebralogic', add=[zebra_procedure()])
    candidate = with_(parent, step='G/s4-spreadsheetbench', add=[zebra_procedure(2)])
    return parent, candidate


@pytest.mark.parametrize('faults,formats,expected_faults,expected_formats', [
    (['secret-item-a', 'secret-item-b'], ['secret-item-c'], 2, 1),
    (7, 3, 7, 3), ({'timeout': 2, 'hook': {'exception': 1}}, {'shape': 0},
                   {'timeout': 2, 'hook': {'exception': 1}}, {'shape': 0})])
def test_previous_executed_acceptance_shows_counts_only(tmp_path, faults, formats, expected_faults, expected_formats):
    st, _ = authored_step(tmp_path, empty(step='G/s0', evidence='engineering_fixture'))
    path = st.chain_root/'s3-zebralogic'/step.STEP_FILE
    write_json(path, p.record('step', 'engineering_fixture',
        {'decision': 'accept', 'fault_items': faults, 'violating_items': formats}))
    previous = step._previous(st)
    assert previous == {'decision': 'accepted', 'faults': {'fault_items': expected_faults},
                        'format': {'violating_items': expected_formats}}
    assert engineer._counts(previous['faults']) and engineer._counts(previous['format'])
    assert 'secret-item' not in str(previous)
    st.setting.extra['configuration'] = p.MAIN_V9
    assert step._previous(st)['faults']['fault_items'] == faults


@pytest.mark.parametrize('value,expected', [(('a', 'b'), 2), ({'a', 'b'}, 2)])
def test_previous_sequence_counts_are_normalized_without_relaxing_engineer(tmp_path, monkeypatch, value, expected):
    st, _ = authored_step(tmp_path, empty(step='G/s0', evidence='engineering_fixture'))
    path = st.chain_root/'s3-zebralogic'/step.STEP_FILE
    write_json(path, {})
    monkeypatch.setattr(step, '_read_record', lambda *_: {'decision': 'reject', 'fault_items': value, 'violating_items': 0})
    assert step._previous(st)['faults'] == {'fault_items': expected}
    assert not engineer._counts(value)


@pytest.mark.parametrize('value', ['not a count', None, True, -1, {'nested': ['id']}])
def test_previous_invalid_counts_fail_closed(tmp_path, value):
    st, _ = authored_step(tmp_path, empty(step='G/s0', evidence='engineering_fixture'))
    write_json(st.chain_root/'s3-zebralogic'/step.STEP_FILE, p.record('step', 'engineering_fixture',
        {'decision': 'accept', 'fault_items': value, 'violating_items': 0}))
    with pytest.raises(ValueError, match='counts only'):
        step._previous(st)


@pytest.mark.parametrize('expression', [None, '{"facts": ["x" * 2000], "diagnostics": ["x" * 2000000]}',
                                      '{"diagnostics": "not a list"}'])
def test_engineer_replay_in_sheet_unit_matches_zebra_value_hash_and_faults(tmp_path, expression):
    procedure = zebra_procedure(expression=expression)
    parent = replay.solo(procedure)
    outcomes, opened = [], []
    for bench, k in [('spreadsheetbench', 4), (p.ZEBRA, 3)]:
        st, workers = authored_step(tmp_path/bench, parent, bench=bench, k=k)
        def work(attempt):
            actual = {}
            crash, values = replay.zero_crash(procedure, [entry()], st.services.workers,
                configuration='main-v10', actual=actual)
            with st.services.workers(parent, kind='cell') as worker:
                raw = diagnostics_runtime.worker_call(worker, procedure.id, 'before_call', [VIEW, None],
                    timeout_s=1, configuration='main-v10', bench=p.ZEBRA)
                clean, _ = diagnostics_runtime.capture(raw, configuration='main-v10', bench=p.ZEBRA, procedure=procedure)
            return {'crash': crash, 'replay': values[entry()['cell']].summary(), 'actual': actual,
                    'value': clean.get('value'), 'value_sha256': clean.get('value_sha256'),
                    'fault': clean.get('fault')}
        # The same zero_crash entry point is used by engineer C6/C7 and repair rechecks.
        outcomes.append(st.unit('engineer-r1', work))
        opened.extend(workers.opened)
    assert outcomes[0] == outcomes[1]
    assert all(w.diagnostics_configuration == p.ZEBRA_PC_V15 and w.options['tag'] for w in opened)
    assert all(call[-1] for w in opened for call in w.calls if call[1] == 'before_call')


def test_required_diagnostics_on_unbound_worker_is_named_host_configuration_error():
    procedure = zebra_procedure()
    worker = DiagnosticsWorker().start(replay.solo(procedure))
    with pytest.raises(ConfigurationError, match='diagnostics_worker_unbound'):
        diagnostics_runtime.worker_call(worker, procedure.id, 'before_call', [VIEW, None],
            timeout_s=1, configuration='main-v10', bench=p.ZEBRA)
    assert worker.calls == []
    with pytest.raises(ValueError, match='v2.15 Zebra worker'):
        diagnostics_runtime.worker_call(worker, procedure.id, 'before_call', [VIEW, None],
            timeout_s=1, configuration=p.MAIN_V9, bench=p.ZEBRA)


@pytest.mark.parametrize('home,k', [('spreadsheetbench', 4), ('searchqa', 1)])
def test_cross_gate_uses_unit_bound_diagnostics_and_matches_zebra_step(tmp_path, monkeypatch, home, k):
    parent, candidate = packages()
    st, workers = authored_step(tmp_path/home, parent, bench=home, k=k)
    rows = [{'task_id': 'zebra-%02d' % i, 'benchmark': p.ZEBRA, 'public': VIEW, 'private': {}}
            for i in range(18)]
    # Supply and paid scoring are authored boundaries. All worker factories,
    # cross-gate inspection, routing and request identity paths are production.
    from tests.test_execskill_v225_routing import VIEWS
    slices = {b: [{'task_id': b+'-%02d' % i, 'benchmark': b, 'public': VIEWS[b], 'private': {}}
                  for i in range(18)] for b in p.MAIN_V5_ORDER}
    slices[p.ZEBRA] = rows
    # Native inputs for the off-home sheet/ALF slices use real authored resources.
    from tests.test_execskill_v225_anchor_environment import task_for
    for b in ('spreadsheetbench', 'alfworld'):
        task = task_for(tmp_path/('resources-'+home), b)
        if b == 'alfworld':
            import json
            from pathlib import Path
            from skillopt.execskill import solver
            from skillopt.validator_pilot.api import digest
            game = json.loads(Path(task['public']['game_file']).read_text())
            view = solver.alfworld_routing_view(game['initial_observation'], game['admissible_commands'])
            task['public'].update(routing_view=view, routing_view_sha256=digest(view))
        for row in slices[b]: row['public'] = task['public']
    registered = v222_gate.registration(slices, configuration='main-v10')
    monkeypatch.setattr(v222_runtime, 'preflight', lambda _: (slices, registered))
    st.solver = lambda *args, **kw: None
    def cells(_st, attempt, endpoint, unit, jobs, *, tag):
        return [{'cell': {'arm': arm, 'task_id': key}, 'faults': [],
                 'judge': {'v2': {'token': 'pass'}, 'format': {}}} for arm, chosen, key, run, task in jobs]
    monkeypatch.setattr(step, '_cells', cells)
    def work(attempt):
        gate = v222_runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation',
                                       parent=parent, candidate=candidate)[1]
        zebra = copy(st)
        zebra.bench = p.ZEBRA
        inspected = v222_gate.inspect(p.ZEBRA, parent, candidate, rows,
            step._item_workers(zebra, {r['task_id']: r['public'] for r in rows}),
            card_text=st.setting.cards[p.ZEBRA], configuration='main-v10')
        return {'gate': gate, 'zebra': inspected}
    found = st.unit('confirm-r1', work)
    assert found['gate']['passed'] and not found['zebra']['faults']
    other, _ = authored_step(tmp_path/(home+'-zebra'), parent, bench=p.ZEBRA, k=3)
    expected = other.unit('confirm-r1', lambda attempt: v222_gate.inspect(p.ZEBRA, parent, candidate, rows,
        step._item_workers(other, {r['task_id']: r['public'] for r in rows}),
        card_text=other.setting.cards[p.ZEBRA], configuration='main-v10'))
    assert found['zebra']['signatures'] == expected['signatures']
    assert all(w.diagnostics_configuration == p.ZEBRA_PC_V15 for w in workers.opened)


def test_immediate_acceptance_selection_is_inside_real_unit_and_resumes_without_routing(tmp_path, monkeypatch):
    parent = empty(step='G/s0', evidence='engineering_fixture')
    candidate = with_(parent, step='G/s3-zebralogic', add=[zebra_procedure()])
    st, workers = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    for package in (parent, candidate): save(st.chain_root, package)
    st.solver = lambda *args, **kwargs: None
    @dataclass
    class Context:
        endpoint: object = None
    monkeypatch.setattr(units, 'cell_context', lambda *args: Context())
    monkeypatch.setattr(acceptance, 'runner', lambda *args, **kwargs: None)
    monkeypatch.setattr(acceptance, 'dispatch', lambda sealed, *args, **kwargs:
        make_cells(sealed, token=lambda job: 'pass' if job['arm'] == "S'" else 'fail'))
    def cross(st, attempt, **kw):
        return kw['candidate'], p.record('v222-cross-gate', st.evidence, {
            'passed': True, 'configuration': 'main-v10', 'home': st.bench,
            'unit': st.label(kw['unit']), 'phase': kw['phase'],
            'parent_sha256': kw['parent'].sha256, 'candidate_sha256': kw['candidate'].sha256})
    monkeypatch.setattr(v222_runtime, 'cross_gate', cross)
    rows = [{'task_id': 'zebra-%02d' % i, 'benchmark': p.ZEBRA, 'public': VIEW, 'private': {}} for i in range(10)]
    found = v221_learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidate)
    assert found['accepted'] and found['rule']['touched'] == 10
    assert all(w.diagnostics_configuration == p.ZEBRA_PC_V15 and w.options.get('tag') for w in workers.opened)
    before = len(workers.opened)
    assert v221_learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidate) == found
    assert len(workers.opened) == before
    assert [call[0] for call in st.services.registry.calls] == ['register', 'decide']
    assert read_json(st.root/'accept-r1'/'unit.json')['result']['decision'] == 'accept'


@pytest.mark.parametrize('method', [None, False])
def test_diagnostics_required_call_never_falls_back_to_plain_worker(method):
    worker = SimpleNamespace(call_diagnostics=method, diagnostics_configuration=p.ZEBRA_PC_V15,
                             call=lambda *args, **kw: pytest.fail('No plain fallback'))
    with pytest.raises(ConfigurationError, match='diagnostics_worker_unbound'):
        diagnostics_runtime.worker_call(worker, 'authored', 'before_call', [VIEW, None],
            timeout_s=1, configuration='main-v10', bench=p.ZEBRA)
