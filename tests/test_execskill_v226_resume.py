"""Confirmation/split retries bind deterministic inputs and retain original faults."""
from copy import deepcopy

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import profiles as p, step, v221_split, v222_runtime
from skillopt.execskill.cells import Pause
from tests.execskill_v226_fakes import DiagnosticsWorker, authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v226_card_units import candidate_pair, zebra_pool
from tests.test_execskill_v218_split import cell


def setup(tmp_path, monkeypatch, configuration=p.MAIN_V10):
    parent, candidate = candidate_pair()
    st, workers = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3, configuration=configuration)
    st.solver = lambda *a, **kw: None
    state = {'fault': True, 'interrupted': False}
    real = DiagnosticsWorker.call
    def flaky(self, proc, hook, args, **kw):
        if state['fault'] and hook == 'before_call':
            return {'ok': False, 'fault': 'timeout', 'exc_type': None,
                    'message': 'Original transient timeout details are retained.', 'line': 17}
        return real(self, proc, hook, args, **kw)
    monkeypatch.setattr(DiagnosticsWorker, 'call', flaky)
    def cells(_st, attempt, endpoint, unit, jobs, **kw):
        if not state['interrupted']:
            state['interrupted'] = True
            raise Pause('infrastructure_incomplete', 'authored interrupted dispatch', unit)
        result = [cell(unit, arm, key, 'pass' if arm == "S'" else 'fail', run)
                  for arm, _, key, run, _ in jobs]
        for row in result:
            write_json(attempt/'cells'/(row['cell']['id']+'.json'), row)
        return result
    monkeypatch.setattr(step, '_cells', cells)
    monkeypatch.setattr(v222_runtime, 'confirmation', lambda st, attempt, **kw: kw['result'])
    monkeypatch.setattr(step, '_feedback', lambda *a, **kw: {})
    return st, parent, candidate, state, workers


def redo(st, unit):
    write_json(st.root/unit/'attempt-1/recovery.json',
               {'by': 'owner', 'date': '2026-11-09', 'decision': 'Authored retry fixture'})


def assert_faults_preserved(signatures):
    faults = [fault for arms in signatures.values() for sig in arms.values() for fault in sig['faults']]
    assert faults and all(fault['message'] == 'Original transient timeout details are retained.' for fault in faults)


def test_confirmation_resume_reuses_sealed_signatures_before_routing_hooks(tmp_path, monkeypatch):
    st, parent, candidate, state, _ = setup(tmp_path, monkeypatch)
    cut = {'confirm': zebra_pool(2)}
    with pytest.raises(Pause):
        step._confirm_eval(st, cut, 1, parent, candidate, exercise=True)
    path = st.root/'confirm-selection-r1.json'
    sealed = p.verified(read_json(path), 'v226-confirm-requests')
    assert_faults_preserved(sealed['request_signatures'])
    redo(st, 'confirm-r1')
    state['fault'] = False
    monkeypatch.setattr(step, '_routes', lambda *a, **kw: pytest.fail('Resume must not re-run routing'))
    result = step._confirm_eval(st, cut, 1, parent, candidate, exercise=True)
    assert result['request_signatures'] == sealed['request_signatures']
    assert result['request_identities'] == sealed['request_identities']
    assert read_json(path) == sealed


@pytest.mark.parametrize('confirmation', [False, True])
def test_split_resume_reuses_sealed_signatures_and_observations(tmp_path, monkeypatch, confirmation):
    st, parent, candidate, state, _ = setup(tmp_path, monkeypatch)
    rows = zebra_pool(2)
    cut = {'confirm': rows, 'run': rows}
    source = {'slice_ids': [row['task_id'] for row in rows]}
    unit = ('confirm' if confirmation else 'train') + '-r1-split-p1'
    with pytest.raises(Pause):
        v221_split.evaluate(st, cut, 1, 1, parent, candidate, candidate, source, None, confirmation=confirmation)
    path = st.root/unit/'split-binding.json'
    sealed = p.verified(read_json(path), 'v226-split-requests')
    assert_faults_preserved(sealed['request_signatures'])
    redo(st, unit)
    state['fault'] = False
    monkeypatch.setattr(step, '_routes', lambda *a, **kw: pytest.fail('Resume must not re-run routing'))
    result = v221_split.evaluate(st, cut, 1, 1, parent, candidate, candidate, source, None, confirmation=confirmation)
    assert result['request_signatures'] == sealed['request_signatures']
    assert read_json(path) == sealed


@pytest.mark.parametrize('field', ['runtime', 'card', 'view', 'candidate'])
def test_confirmation_resume_still_rejects_changed_deterministic_core(tmp_path, monkeypatch, field):
    st, parent, candidate, state, _ = setup(tmp_path, monkeypatch)
    cut = {'confirm': zebra_pool(2)}
    with pytest.raises(Pause):
        step._confirm_eval(st, cut, 1, parent, candidate, exercise=True)
    redo(st, 'confirm-r1')
    state['fault'] = False
    if field == 'runtime':
        st.setting.runtime[p.ZEBRA]['authored_version'] = 'changed'
    elif field == 'card':
        from skillopt.execskill import v222_cards
        original = v222_cards.format_text
        monkeypatch.setattr(v222_cards, 'format_text',
            lambda bench: original(bench) + (' Changed.' if bench == p.ZEBRA else ''))
    elif field == 'view':
        cut = deepcopy(cut)
        cut['confirm'][0]['public']['question'] += ' Changed.'
    else:
        candidate = parent
    with pytest.raises(Pause) as raised:
        step._confirm_eval(st, cut, 1, parent, candidate, exercise=True)
    assert raised.value.kind == 'configuration'
    assert 'deterministic confirmation core' in (st.root/'confirm-r1/attempt-2/diagnostics.log').read_text()


@pytest.mark.parametrize('split', [False, True])
def test_frozen_main_v9_retains_flaky_request_identity_pause(tmp_path, monkeypatch, split):
    st, parent, candidate, state, _ = setup(tmp_path, monkeypatch, configuration=p.MAIN_V9)
    rows = zebra_pool(2)
    cut = {'confirm': rows}
    unit = 'confirm-r1-split-p1' if split else 'confirm-r1'
    def run():
        if split:
            return v221_split.evaluate(st, cut, 1, 1, parent, candidate, candidate,
                {'slice_ids': [row['task_id'] for row in rows]}, None, confirmation=True)
        return step._confirm_eval(st, cut, 1, parent, candidate, exercise=True)
    with pytest.raises(Pause):
        run()
    redo(st, unit)
    state['fault'] = False
    with pytest.raises(Pause) as raised:
        run()
    assert raised.value.kind == 'configuration'
    diagnostic = (st.root/unit/'attempt-2/diagnostics.log').read_text()
    assert ('same immutable request plan' if split else 'same sealed confirmation request identities') in diagnostic
