"""Production procedure evaluation continues and resumes after local host defects."""
import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import engineer, profiles as p, step, v221_learning, v226_candidates as guard
from skillopt.execskill.cells import Pause
from skillopt.execskill.package import empty, save, with_
from tests.execskill_v226_fakes import DiagnosticsWorker, authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v226_diagnostics import VIEW, zebra_procedure
from tests.test_execskill_v218_split import cell


def setup(tmp_path, monkeypatch, *, parent_fault=False, both_fault=False):
    initial = empty(step='G/s0', evidence='engineering_fixture')
    parent = with_(initial, step='G/s3-zebralogic', add=[zebra_procedure(1)]) if parent_fault else initial
    candidates = [with_(parent, step='G/s3-zebralogic', add=[zebra_procedure(n)]) for n in (2, 3)]
    st, workers = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    st.solver = lambda *a, **kw: None
    for pkg in [parent, *candidates]: save(st.chain_root, pkg)
    bad = {parent.order[0]} if parent_fault else {candidates[0].order[-1]}
    if both_fault: bad.add(candidates[1].order[-1])
    real = DiagnosticsWorker.call
    def host_defect(self, proc, hook, args, **kwargs):
        if hook == 'before_call' and proc in bad:
            raise KeyError('private item must never appear in candidate_error')
        return real(self, proc, hook, args, **kwargs)
    monkeypatch.setattr(DiagnosticsWorker, 'call', host_defect)
    def scored(_st, attempt, endpoint, unit, jobs, **kwargs):
        return [cell(unit, arm, key, 'pass' if arm == "S'" else 'fail', run)
                for arm, _, key, run, _ in jobs]
    monkeypatch.setattr(step, '_cells', scored)
    monkeypatch.setattr(step, '_feedback', lambda *args, **kwargs: {})
    pool = [{'task_id': 'authored-%d' % i, 'benchmark': p.ZEBRA, 'public': VIEW, 'private': {}}
            for i in range(4)]
    return st, parent, candidates, pool, workers


def test_train_error_rejects_then_next_candidate_evaluates_with_valid_history(tmp_path, monkeypatch):
    st, parent, candidates, rows, workers = setup(tmp_path, monkeypatch)
    cut = {'run': rows}
    first = step._train_eval(st, cut, 1, parent, candidates[0], None, current=[])
    assert not first['adopted'] and first['candidate_error']['kind'] == 'candidate_error'
    opened = len(workers.opened)
    assert step._train_eval(st, cut, 1, parent, candidates[0], None, current=[]) == first
    assert len(workers.opened) == opened
    authored = {'candidate_sha256': candidates[0].sha256, 'engineer': {'changes': [], 'dropped': []}}
    line = step._line(1, authored, first, configuration=p.MAIN_V10)
    line['patience_counted'] = line['candidate']
    assert engineer._history_line(line, 2, v24=True, v28=True, v29=True, v291=True,
                                  v294=True, v218=True, v221=True, v222=True)
    second = step._train_eval(st, cut, 2, parent, candidates[1], None, current=[])
    assert second['adopted'] and 'candidate_error' not in second
    assert sum(guard.counts(st.root).values()) == 1
    assert not list(st.root.glob('*/attempt-*/status.json'))


def test_confirm_error_resumes_as_rejection_without_registering_or_rerouting(tmp_path, monkeypatch):
    st, parent, candidates, rows, workers = setup(tmp_path, monkeypatch)
    cut = {'confirm': rows[:2]}
    result = step._confirm_eval(st, cut, 1, parent, candidates[0], exercise=True)
    assert not result['confirm']['passed'] and result['candidate_error']['kind'] == 'candidate_error'
    assert not result['registered'] and not st.services.registry.calls
    opened = len(workers.opened)
    assert step._confirm_eval(st, cut, 1, parent, candidates[0], exercise=True) == result
    assert len(workers.opened) == opened and sum(guard.counts(st.root).values()) == 1


def test_accept_selection_error_is_contained_before_any_selection_file_or_registration(tmp_path, monkeypatch):
    from skillopt.execskill import v222_runtime
    monkeypatch.setattr(v222_runtime, "cross_gate", lambda *a, **kw: (kw["candidate"], {"passed": True}))
    st, parent, candidates, rows, workers = setup(tmp_path, monkeypatch)
    result = v221_learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidates[0])
    assert result['decision'] == 'reject' and not result['accepted']
    assert result['candidate_error']['kind'] == 'candidate_error'
    assert not (st.root/'accept-selection-r1.json').exists()
    assert not st.services.registry.calls
    opened = len(workers.opened)
    assert v221_learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidates[0]) == result
    assert len(workers.opened) == opened and sum(guard.counts(st.root).values()) == 1


def test_two_consecutive_procedure_errors_pause_original_exception_and_record_both(tmp_path, monkeypatch):
    st, parent, candidates, rows, _ = setup(tmp_path, monkeypatch, both_fault=True)
    step._train_eval(st, {'run': rows}, 1, parent, candidates[0], None, current=[])
    with pytest.raises(Pause) as raised:
        step._train_eval(st, {'run': rows}, 2, parent, candidates[1], None, current=[])
    assert raised.value.kind == 'exception' and raised.value.reason == 'KeyError'
    status = read_json(st.root/'train-r2/attempt-1/status.json')
    assert status['candidate_errors'] == guard.counts(st.root)
    assert sum(status['candidate_errors'].values()) == 2


def test_incumbent_hook_evaluation_error_is_never_candidate_rejection(tmp_path, monkeypatch):
    st, parent, candidates, rows, _ = setup(tmp_path, monkeypatch, parent_fault=True)
    with pytest.raises(Pause) as raised:
        step._train_eval(st, {'run': rows}, 1, parent, candidates[0], None, current=[])
    assert raised.value.reason == 'KeyError' and guard.counts(st.root) == {}
    assert read_json(st.root/'train-r1/attempt-1/status.json')['status'] == 'paused'


def test_counterfactual_reference_of_new_procedures_is_still_candidate_local(tmp_path, monkeypatch):
    from skillopt.execskill.package import withhold
    st, parent, candidates, rows, _ = setup(tmp_path, monkeypatch)
    candidate = with_(parent, step='G/s3-zebralogic', add=[zebra_procedure(2), zebra_procedure(3)])
    reference = withhold(candidate, [candidate.order[-1]])
    publics = {row['task_id']: row['public'] for row in rows}
    def work(attempt):
        return step._pair_signatures(st, candidate, reference, publics, list(publics.items()))
    result = st.unit('train-r1', guard.guard(st, 'procedure-r1', parent, work,
        lambda event: {'candidate_error': event}))
    assert result['candidate_error']['exception'] == 'KeyError'
    assert sum(guard.counts(st.root).values()) == 1


@pytest.mark.parametrize('parent_fault', [False, True])
def test_selftest_preparation_contains_only_candidate_errors(tmp_path, monkeypatch, parent_fault):
    st, parent, candidates, rows, workers = setup(tmp_path, monkeypatch, parent_fault=parent_fault)
    generated = {'g_self': [{**row, 'id': row['task_id']} for row in rows]}
    if parent_fault:
        with pytest.raises(Pause) as raised:
            step._selftest(st, 'selftest', candidates[0], generated, candidate_key='procedure-r1')
        assert raised.value.reason == 'KeyError' and guard.counts(st.root) == {}
    else:
        result = step._selftest(st, 'selftest', candidates[0], generated, candidate_key='procedure-r1')
        assert result['blocked'] and result['reason'] == 'selftest_candidate_error' and result['cells'] == 0
        assert result['candidate_error']['exception'] == 'KeyError'
        opened = len(workers.opened)
        assert step._selftest(st, 'selftest', candidates[0], generated, candidate_key='procedure-r1') == result
        assert len(workers.opened) == opened and sum(guard.counts(st.root).values()) == 1
