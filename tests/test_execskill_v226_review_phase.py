"""Review regressions for sealed split observations, workbook inputs and card supply."""
from copy import deepcopy

import pytest
from openpyxl import Workbook, load_workbook

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import policy, profiles as p, solver, step, v221_split, v222_runtime, v225_phase
from skillopt.execskill.cells import Pause
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import procedure
from tests.execskill_v226_fakes import authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v218_split import cell
from tests.test_execskill_v226_card_units import candidate_pair, zebra_pool
from tests.test_execskill_v226_resume import redo


def note_pair(bench, *, count=1):
    parent = empty(step='G/s0', evidence='engineering_fixture')
    procs = [procedure('fx-review-note-' + str(i), ('applies', 'before_call'), origin=bench,
        policy_version=policy.POLICY_VERSION_V222,
        source="def applies(view):\n    return True\n\ndef before_call(view, state):\n    return {'facts': ['Compare supplied evidence carefully.']}\n") for i in range(count)]
    return parent, with_(parent, step='G/s3-' + bench, add=procs)


def public_rows(bench, count=4):
    if bench == p.ZEBRA:
        return zebra_pool(count)
    return [{'task_id': 'practice-%02d' % i, 'benchmark': bench, 'partition': 'practice',
             'public': {'question': 'Compare supplied evidence.', 'context': ['The supplied evidence.']},
             'private': {}} for i in range(count)]


@pytest.mark.parametrize('bench', [p.ZEBRA, 'searchqa'])
@pytest.mark.parametrize('n', [1, 'merge'])
def test_split_delivered_notes_seal_json_and_resume_identically(tmp_path, monkeypatch, bench, n):
    parent, candidate = note_pair(bench)
    st, _ = authored_step(tmp_path, parent, bench=bench, k=3 if bench == p.ZEBRA else 1)
    st.solver = lambda *a, **kw: None
    rows = public_rows(bench)
    state = {'interrupt': True}
    feedback = []
    def dispatch(_st, attempt, endpoint, unit, jobs, **kw):
        if state['interrupt']:
            raise Pause('infrastructure_incomplete', 'authored interruption after binding', unit)
        return [cell(unit, arm, key, 'pass' if arm == "S'" else 'fail', run)
                for arm, _, key, run, _ in jobs]
    def observe(*args, **kw):
        feedback.append(deepcopy(kw.get('note_coverage')))
        return {}
    monkeypatch.setattr(step, '_cells', dispatch)
    monkeypatch.setattr(step, '_feedback', observe)
    unit = 'train-r1-split-' + ('merge' if n == 'merge' else 'p1')
    with pytest.raises(Pause) as raised:
        v221_split.evaluate(st, {'run': rows}, 1, n, parent, candidate, candidate, {}, None)
    assert raised.value.kind == 'infrastructure_incomplete'
    sealed = p.verified(read_json(st.root/unit/'split-binding.json'), 'v226-split-requests')
    assert any(fields == ['facts'] for arms in sealed['captured'].values()
               for by_proc in arms.values() for fields in by_proc.values())
    redo(st, unit)
    state['interrupt'] = False
    result = v221_split.evaluate(st, {'run': rows}, 1, n, parent, candidate, candidate, {}, None)
    assert result['adopted']
    resumed_feedback = feedback[-1]
    fresh, _ = authored_step(tmp_path/'fresh', parent, bench=bench, k=st.k)
    fresh.solver = st.solver
    uninterrupted = v221_split.evaluate(fresh, {'run': rows}, 1, n, parent, candidate, candidate, {}, None)
    assert result == uninterrupted
    assert feedback[-1] == resumed_feedback


def sheet_rows(root, count=2):
    path = root/'public.xlsx'
    book = Workbook()
    book.active['A1'] = 'Preview value'
    book.active['A20'] = 'Original unpreviewed value'
    book.save(path)
    return [{'task_id': 'sheet-%d' % i, 'benchmark': 'spreadsheetbench', 'partition': 'practice',
             'public': {'instruction': 'Copy A20 to B1.', 'input_files': [str(path)], 'answer_position': 'B1'},
             'private': {}} for i in range(count)], path


@pytest.mark.parametrize('kind', ['confirmation', 'split', 'card', 'card_selection'])
def test_sheet_resume_rejects_change_outside_preview(tmp_path, monkeypatch, kind):
    from unittest.mock import patch
    from tests.execskill_v226_fakes import DiagnosticsWorker
    from skillopt.execskill.sandbox import worker_v222
    parent, candidate = candidate_pair('spreadsheetbench')
    proc = procedure('fx-workbook-reader', ('applies', 'before_call'), origin='spreadsheetbench',
        policy_version=policy.POLICY_VERSION_V222,
        source="def applies(view):\n    return True\n\ndef before_call(view, state):\n    cell = public_workbook()['sheets'][0]['cells']['A20']['value']\n    return {'facts': ['Workbook evidence: ' + str(cell)]}\n")
    candidate = with_(candidate, step=candidate.step, add=[proc])
    st, _ = authored_step(tmp_path, parent)
    st.solver = lambda *a, **kw: None
    original_call = DiagnosticsWorker.call
    def mounted_call(self, proc_id, fn, args, **kw):
        with patch.object(worker_v222, 'INPUT_WORKBOOK', str(self.options['inputs_dir']/'input.xlsx')):
            return original_call(self, proc_id, fn, args, **kw)
    monkeypatch.setattr(DiagnosticsWorker, 'call', mounted_call)
    rows, path = sheet_rows(tmp_path)
    publics = {row['task_id']: row['public'] for row in rows}
    def actual_signatures():
        return step._pair_signatures(st, candidate, parent, publics,
            [(key, solver.routing_view(st.bench, public)) for key, public in publics.items()])
    original_signatures = actual_signatures()
    assert all(not pair["S'"]['faults'] for pair in original_signatures.values())
    views = [solver.routing_view(st.bench, row['public']) for row in rows]
    state = {'interrupt': True}
    def dispatch(_st, attempt, endpoint, unit, jobs, **kw):
        if state['interrupt']:
            raise Pause('infrastructure_incomplete', 'authored interrupted dispatch', unit)
        return [cell(unit, arm, key, 'pass' if arm == "S'" else 'fail', run)
                for arm, _, key, run, _ in jobs]
    monkeypatch.setattr(step, '_cells', dispatch)
    monkeypatch.setattr(v222_runtime, 'confirmation', lambda st, attempt, **kw: kw['result'])
    unit = {'confirmation': 'confirm-r1', 'split': 'confirm-r1-split-p1',
            'card': 'card-train-c1', 'card_selection': 'card-train-c1'}[kind]
    def run():
        if kind == 'confirmation':
            return step._confirm_eval(st, {'confirm': rows}, 1, parent, candidate, exercise=True)
        if kind == 'split':
            return v221_split.evaluate(st, {'confirm': rows}, 1, 1, parent, candidate, candidate,
                {'slice_ids': [row['task_id'] for row in rows]}, None, confirmation=True)
        if kind == 'card_selection':
            def work(attempt):
                value = v225_phase.select(st, {'accept': rows}, 1, 'accept', parent, candidate)
                if state['interrupt']:
                    raise Pause('infrastructure_incomplete', 'authored interrupted selection', st.label(unit))
                return {'selected': len(value[0])}
            return st.unit(unit, work)
        return v225_phase.measure(st, rows, parent, candidate, name=unit, kind='selftest', runs=1)
    with pytest.raises(Pause) as raised:
        run()
    assert raised.value.kind == 'infrastructure_incomplete'
    redo(st, unit)
    state['interrupt'] = False
    book = load_workbook(path)
    book.active['A20'] = 'Changed unpreviewed value'
    book.save(path)
    assert [solver.routing_view(st.bench, row['public']) for row in rows] == views
    changed_signatures = actual_signatures()
    assert all(changed_signatures[key]["S'"]['request_sha256'] != pair["S'"]['request_sha256']
               for key, pair in original_signatures.items())
    with pytest.raises(Pause) as raised:
        run()
    assert raised.value.kind == 'configuration'
    assert 'deterministic' in (st.root/unit/'attempt-2/diagnostics.log').read_text()


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
def test_card_cross_rejection_preserves_procedure_pool(tmp_path, monkeypatch, bench):
    from skillopt.execskill import v222_gate
    def reject(**kw):
        assert kw['phase'] == 'acceptance'
        return None, {'passed': False, 'reason': 'cross_bench_harm'}
    monkeypatch.setattr(v222_gate, 'check', reject)
    result = v225_phase.authored_phase_smoke(tmp_path, bench=bench, scenario='cross_reject', configuration=p.MAIN_V10)
    assert result['rounds'][0]['reason'] == 'cross_bench_harm'
    assert result['procedure_phase'] == 'run'
    assert result['consumed_acceptance'] == 0
    assert not list(tmp_path.glob('G/s*/card-accept-selection-*.json'))


@pytest.mark.parametrize('both', [False, True])
def test_real_split_confirmation_candidate_error_is_restartable_and_systematic(tmp_path, monkeypatch, both):
    from tests.execskill_v226_fakes import DiagnosticsWorker
    from skillopt.execskill import v226_candidates
    parent, candidate = note_pair(p.ZEBRA, count=2)
    st, workers = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    st.solver = lambda *a, **kw: None
    cut = {'run': zebra_pool(4), 'confirm': zebra_pool(4)}
    for row in cut['confirm']:
        row['task_id'] = 'confirm-' + row['task_id']
        row['public']['question'] += ' Confirmation marker.'
    original = DiagnosticsWorker.call
    def broken(self, proc, hook, args, **kw):
        if hook == 'before_call' and 'Confirmation marker.' in args[0].get('question', ''):
            if both or proc == candidate.order[0]:
                raise KeyError('authored candidate defect')
        return original(self, proc, hook, args, **kw)
    monkeypatch.setattr(DiagnosticsWorker, 'call', broken)
    def dispatch(_st, attempt, endpoint, unit, jobs, **kw):
        return [cell(unit, arm, key,
            'pass' if arm == "S'" and (both or chosen.package.order == (candidate.order[0],)) else 'fail', run)
            for arm, chosen, key, run, _ in jobs]
    monkeypatch.setattr(step, '_cells', dispatch)
    monkeypatch.setattr(step, '_feedback', lambda *a, **kw: {})
    training = {'adopted': True, 'verdict': {'fixed': ['original'], 'broken': [], 'net': '1/1',
                                          'reason': None}, 'feedback': {}}
    confirmation = {'confirm': {'passed': False, 'fixed': 0, 'broken': 0, 'net': 0,
                               'reason': 'gain_and_no_harm'},
                    'slice_ids': [row['task_id'] for row in cut['confirm']]}
    engineered = {'engineer': {'changes': [{'id': pid, 'kind': 'new', 'target': None}
                                         for pid in candidate.order]}}
    def run():
        return v221_split.run(st, cut, 1, parent, candidate, engineered,
                             training, confirmation, None, current=[])
    if both:
        with pytest.raises(Pause) as raised:
            run()
        assert raised.value.kind == 'exception' and raised.value.reason == 'KeyError'
        assert sum(v226_candidates.counts(st.root).values()) == 2
    else:
        selected, result = run()
        assert result['split'][0]['reason'] == 'candidate_error'
        assert not result['split'][0]['passed']
        opened = len(workers.opened)
        assert run() == (selected, result)
        assert len(workers.opened) == opened
        assert sum(v226_candidates.counts(st.root).values()) == 1


@pytest.mark.parametrize('site', ['split_plan', 'card_plan', 'card_selection', 'card_phase'])
@pytest.mark.parametrize('contents', ['{', '{"broken": NaN}'])
def test_split_and_card_recovery_corruption_never_contained(tmp_path, monkeypatch, site, contents):
    from skillopt.execskill import v226_candidates
    parent, candidate = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    st.solver = lambda *a, **kw: None
    rows = zebra_pool(2)
    names = {'split_plan': 'confirm-r1-split-p1/split-binding.json',
             'card_plan': 'card-train-c1/card-request-plan.json',
             'card_selection': 'card-accept-selection-c1.json', 'card_phase': 'card-phase.json'}
    path = st.root/names[site]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    if site == 'split_plan':
        def run():
            return v221_split.evaluate(st, {'confirm': rows}, 1, 1, parent, candidate, candidate,
                {'slice_ids': [row['task_id'] for row in rows]}, None, confirmation=True)
    elif site == 'card_plan':
        def run():
            return v225_phase.measure(st, rows, parent, candidate, name='card-train-c1', kind='selftest', runs=1)
    else:
        def work(attempt):
            return (v225_phase.select(st, {'accept': rows}, 1, 'accept', parent, candidate)
                    if site == 'card_selection' else v225_phase.card_phase(st, {'accept': rows}))
        def run():
            return st.unit('card-train-c1', v226_candidates.guard(st, 'card-c1', parent, work,
                lambda event: {'candidate_error': event}))
    with pytest.raises(Pause) as raised:
        run()
    assert raised.value.kind == 'configuration'
    assert v226_candidates.counts(st.root) == {}


@pytest.mark.parametrize('bench', [p.ZEBRA, 'searchqa'])
def test_main_v9_split_notes_keep_legacy_binding(tmp_path, monkeypatch, bench):
    from skillopt.execskill import v226_bindings
    parent, candidate = note_pair(bench)
    st, _ = authored_step(tmp_path, parent, bench=bench, k=3 if bench == p.ZEBRA else 1,
                          configuration=p.MAIN_V9)
    st.solver = lambda *a, **kw: None
    monkeypatch.setattr(v226_bindings, 'json_observations',
                        lambda *a: pytest.fail('main-v9 never canonicalises split observations'))
    monkeypatch.setattr(step, '_feedback', lambda *a, **kw: {})
    monkeypatch.setattr(step, '_cells', lambda _st, attempt, endpoint, unit, jobs, **kw:
        [cell(unit, arm, key, 'pass' if arm == "S'" else 'fail', run)
         for arm, _, key, run, _ in jobs])
    result = v221_split.evaluate(st, {'run': public_rows(bench)}, 1, 1, parent, candidate, candidate, {}, None)
    assert result['adopted']
    binding = read_json(st.root/'train-r1-split-p1/split-binding.json')
    assert set(binding) == {'configuration', 'round', 'incumbent_sha256', 'candidate_sha256',
                           'full_candidate_sha256', 'items', 'request_signatures', 'original_decision_unit'}


def test_workbook_binding_includes_every_public_input(tmp_path):
    from skillopt.execskill.v226_bindings import workbook_digests
    rows, first = sheet_rows(tmp_path)
    second = tmp_path/'second.xlsx'
    second.write_bytes(first.read_bytes())
    public = {**rows[0]['public'], 'input_files': [str(first), str(second)]}
    before = workbook_digests('spreadsheetbench', {'item': public})
    book = load_workbook(second)
    book.active['A20'] = 'Different second public workbook'
    book.save(second)
    after = workbook_digests('spreadsheetbench', {'item': public})
    assert len(before['item']) == 2
    assert before['item'][0] == after['item'][0]
    assert before['item'][1] != after['item'][1]


@pytest.mark.parametrize('contents', ['{', '{"broken": NaN}'])
def test_card_phase_corrupt_completed_receipt_pauses_outside_units(tmp_path, contents):
    parent, _ = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    st.root.mkdir(parents=True, exist_ok=True)
    (st.root/'card-phase.json').write_text(contents)
    with pytest.raises(Pause) as raised:
        v225_phase.card_phase(st, {})
    assert raised.value.kind == 'configuration'
    assert raised.value.reason == 'sealed_record_invalid'
