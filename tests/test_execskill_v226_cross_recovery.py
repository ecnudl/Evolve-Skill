"""Review regressions for inherited faults and cross-gate replay records."""
from contextlib import contextmanager
from dataclasses import replace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import profiles as p, step, v222_gate as gate, v222_runtime as runtime
from tests.execskill_v226_fakes import DiagnosticsWorker, authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v225_cross_card import packages as card_packages, inspector as card_inspector, paired as card_paired
from tests.test_execskill_v226_gate import packages, slices, paired
from tests.test_execskill_v225_routing import VIEWS


def flaky_inspector(parent, state):
    def inspect(bench, before, after, items, *args, **kwargs):
        @contextmanager
        def workers(package, key):
            class FlakyWorker(DiagnosticsWorker):
                def call(self, proc_id, fn, args, **kw):
                    if (fn == 'before_call' and proc_id == 'fx-inherited-zebra'
                            and package.sha256 != parent.sha256 and key == state['key']):
                        return {'ok': False, 'fault': 'timeout', 'message': 'authored flake'}
                    return super().call(proc_id, fn, args, **kw)
            yield FlakyWorker(diagnostics_configuration=p.ZEBRA_PC_V15).start(package)
        return gate.inspect(bench, before, after, items, workers,
            views={row['task_id']: VIEWS[bench] for row in items}, configuration=p.MAIN_V10)
    return inspect


@pytest.mark.parametrize('card', [False, True])
def test_candidate_arm_only_unchanged_inherited_timeout_is_measured(card):
    parent, candidate = packages(card)
    calls = []
    def run(bench, before, after, items):
        calls.append((bench, [row['task_id'] for row in items]))
        return paired(items)
    selected, record = gate.check(home='spreadsheetbench', parent=parent, candidate=candidate,
        slices=slices(), inspector=flaky_inspector(parent, {'key': 'zebralogic-00'}), run_pairs=run,
        narrower=lambda *a, **kw: None, phase='acceptance', configuration=p.MAIN_V10)
    assert selected == candidate and record['passed']
    assert calls == [('zebralogic', ['zebralogic-00'])]
    assert record['benches']['zebralogic']['candidate_faults'] == []
    assert len(record['benches']['zebralogic']['inherited_faults']) == 1


def test_cross_card_non_target_inherited_flake_uses_no_harm_rule():
    parent, candidate, _ = card_packages()
    calls = []
    def inspect(bench, before, after, items):
        found = card_inspector(bench, before, after, items)
        if bench == 'zebralogic':
            key = items[0]['task_id']
            found.update(fired=1, fired_items=[key], identity_proven=False,
                inherited_faults=[{'item': key, 'arm': "S'", 'kind': 'timeout'}], candidate_faults=[])
        return found
    def run(bench, before, after, items):
        calls.append((bench, len(items)))
        return card_paired(items, 3 if bench == 'officeqa' else 0, 0)
    selected, record = gate.check(home='searchqa', parent=parent, candidate=candidate,
        slices=slices(), inspector=inspect, run_pairs=run, phase='cross_card', configuration=p.MAIN_V10)
    assert selected == candidate and record['passed']
    assert calls == [('officeqa', 18), ('zebralogic', 1)]
    assert 'card_rule' not in record['benches']['zebralogic']


def runtime_setup(tmp_path, monkeypatch):
    parent, candidate = packages()
    st, _ = authored_step(tmp_path, parent)
    rows = {bench: [{**row, 'private': {'answer': 'authored'}} for row in items]
            for bench, items in slices().items()}
    registration = gate.registration(rows, configuration=p.MAIN_V10)
    monkeypatch.setattr(runtime, 'preflight', lambda setting: (rows, registration))
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kw: public)
    state = {'key': 'zebralogic-00', 'inspections': 0, 'interrupted': False}
    # Capture the real implementation before replacing the runtime import's alias.
    real_inspect = gate.inspect
    def inspected(bench, before, after, items, workers, **kwargs):
        state['inspections'] += 1
        @contextmanager
        def flaky_workers(package, key):
            class Worker(DiagnosticsWorker):
                def call(self, proc_id, fn, args, **kw):
                    if (proc_id == 'fx-inherited-zebra' and fn == 'before_call'
                            and package.sha256 == parent.sha256 and key == state['key']):
                        return {'ok': False, 'fault': 'timeout', 'message': 'authored flake'}
                    return super().call(proc_id, fn, args, **kw)
            yield Worker(diagnostics_configuration=p.ZEBRA_PC_V15).start(package)
        return real_inspect(bench, before, after, items, flaky_workers,
            views={row['task_id']: VIEWS[bench] for row in items}, configuration=p.MAIN_V10)
    monkeypatch.setattr(gate, 'inspect', inspected)
    def solver(*args, **kw):
        if not state['interrupted']:
            state['interrupted'] = True
            raise RuntimeError('authored interruption after the routing pin')
        return object()
    st.solver = solver
    def cells(st, attempt, endpoints, name, jobs, **kw):
        return [{'cell': {'unit': name, 'arm': arm, 'task_id': key, 'run': 0},
                 'judge': {'v2': {'token': 'fail'}}} for arm, package, key, run, task in jobs]
    monkeypatch.setattr(step, '_system_cells', cells)
    return st, parent, candidate, state, rows


@pytest.mark.parametrize('unit,phase', [('confirm-r1', 'confirmation'), ('accept-r1', 'acceptance'),
                                      ('card-accept-c1', 'acceptance')])
def test_cross_gate_redo_reuses_sealed_inspection_before_pair_binding(tmp_path, monkeypatch, unit, phase):
    st, parent, candidate, state, rows = runtime_setup(tmp_path, monkeypatch)
    first = st.root / unit / 'attempt-1'; first.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='authored interruption'):
        runtime.cross_gate(st, first, unit=unit, phase=phase, parent=parent, candidate=candidate)
    inspected = state['inspections']
    state['key'] = 'zebralogic-01'
    second = first.parent / 'attempt-2'; second.mkdir()
    chosen, record = runtime.cross_gate(st, second, unit=unit, phase=phase, parent=parent, candidate=candidate)
    assert chosen == candidate and record['passed']
    assert state['inspections'] == inspected + 1  # only the unfinished ALF slice
    pinned = p.verified(read_json(first.parent / 'v226-cross-inspection-zebralogic.json'),
                        'v226-cross-inspection')
    assert pinned['inspection']['fired_items'] == ['zebralogic-00']
    assert set(('signatures', 'request_changed', 'potential_post_call', 'faults', 'candidate_faults',
                'inherited_faults', 'observations')) <= pinned['inspection'].keys()


def test_cross_gate_redo_refuses_changed_runtime_before_reinspection(tmp_path, monkeypatch):
    st, parent, candidate, state, rows = runtime_setup(tmp_path, monkeypatch)
    attempt = st.root / 'confirm-r1' / 'attempt-1'; attempt.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='authored interruption'):
        runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation', parent=parent, candidate=candidate)
    state['key'] = None
    st.setting.runtime['searchqa']['changed'] = True
    with pytest.raises(ValueError, match='deterministic cross inspection'):
        runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation', parent=parent, candidate=candidate)


@pytest.mark.parametrize('filename', ['v222-cross-completed.json', 'v222-cross-zebralogic.json',
    'v226-cross-inspection-zebralogic.json', 'attempt-1/cells/broken.json'])
@pytest.mark.parametrize('corrupt', ['{', '[]'])
def test_cross_recovery_corrupt_records_pause_outside_containment(tmp_path, monkeypatch, filename, corrupt):
    from skillopt.execskill import v226_candidates as guards
    from skillopt.execskill.cells import Pause
    st, parent, candidate, state, rows = runtime_setup(tmp_path, monkeypatch)
    attempt = st.root / 'confirm-r1' / 'attempt-1'; attempt.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='authored interruption'):
        runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation', parent=parent, candidate=candidate)
    path = attempt.parent / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(corrupt)
    def work(_attempt):
        return runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation',
                                  parent=parent, candidate=candidate)
    with pytest.raises(Pause) as raised:
        st.unit('confirm-r2', guards.guard(st, 'procedure-r1', parent, work,
                                           lambda event: {'candidate_error': event}))
    assert raised.value.kind == 'configuration'
    assert guards.counts(st.root) == {}


def test_cross_gate_redo_reuses_sealed_narrowing_rechecks(tmp_path, monkeypatch):
    st, parent, candidate, state, rows = runtime_setup(tmp_path, monkeypatch)
    changed = replace(candidate.procedures[-1], source=(
        "def applies(view):\n    return 'context' in view or 'instruction' in view\n\n"
        "def before_call(view, state):\n    return {'facts': ['Check the supplied values.']}\n"))
    candidate = replace(candidate, procedures=candidate.procedures[:-1] + (changed,))
    state['interrupted'] = True
    def cells(st, attempt, endpoints, name, jobs, **kw):
        return [{'cell': {'unit': name, 'arm': arm, 'task_id': key, 'run': 0},
                 'judge': {'v2': {'token': 'pass' if name.endswith('officeqa') and arm == 'S' else 'fail'}}}
                for arm, package, key, run, task in jobs]
    monkeypatch.setattr(step, '_system_cells', cells)
    save = runtime.save
    def interrupted_save(*args, **kwargs):
        raise RuntimeError('authored interruption after narrowing')
    monkeypatch.setattr(runtime, 'save', interrupted_save)
    attempt = st.root / 'confirm-r1' / 'attempt-1'; attempt.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='after narrowing'):
        runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation', parent=parent, candidate=candidate)
    assert len(list(attempt.parent.glob('v226-cross-inspection-narrowed-*.json'))) == 4
    inspected = state['inspections']
    state['key'] = 'zebralogic-01'
    monkeypatch.setattr(runtime, 'save', save)
    chosen, record = runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation',
                                       parent=parent, candidate=candidate)
    assert chosen is not None and record['narrowing']['passed']
    assert state['inspections'] == inspected


def test_candidate_arm_only_inherited_fault_is_informational_during_narrowing():
    parent, candidate = packages()
    changed = replace(candidate.procedures[-1], source=(
        "def applies(view):\n    return 'context' in view or 'instruction' in view\n\n"
        "def before_call(view, state):\n    return {'facts': ['Check the supplied values.']}\n"))
    candidate = replace(candidate, procedures=candidate.procedures[:-1] + (changed,))
    selected, record = gate.check(home='spreadsheetbench', parent=parent, candidate=candidate,
        slices=slices(), inspector=flaky_inspector(parent, {'key': 'zebralogic-00'}),
        run_pairs=lambda bench, before, after, items: paired(items, harmful=bench == 'officeqa'),
        phase='acceptance', configuration=p.MAIN_V10)
    assert selected is not None and record['passed'] and record['narrowing']['passed']
    zebra = record['narrowing']['rechecked']['zebralogic']
    assert zebra['candidate_faults'] == [] and len(zebra['inherited_faults']) == 1


@pytest.mark.parametrize('kind,hook', [('note_duplicate_name', 'bindings'), ('note_over_declared_cap', 'notes')])
def test_inherited_shell_interaction_fault_still_belongs_to_candidate(monkeypatch, kind, hook):
    parent, candidate = packages()
    def signature(bench, package, view, worker, **kw):
        return {'request_sha256': 'a' * 64, 'post_call': [], 'enabled': ['fx-inherited-zebra'],
                'faults': [] if package.sha256 == parent.sha256 else [
                    {'procedure': 'fx-inherited-zebra', 'kind': kind, 'hook': hook}]}
    monkeypatch.setattr(gate.reuse, 'signature', signature)
    @contextmanager
    def workers(package, key):
        yield None
    found = gate.inspect('zebralogic', parent, candidate, slices()['zebralogic'], workers,
                         configuration=p.MAIN_V10)
    assert len(found['candidate_faults']) == 18 and not found['inherited_faults']
