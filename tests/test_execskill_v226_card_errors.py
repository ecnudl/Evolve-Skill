"""Loud candidate-local card failures preserve hard stops and readout counts."""
import json

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import package, profiles as p, step, v222_runtime, v225_cards, v225_phase as phase, v225_read, v226_candidates
from skillopt.execskill.cells import Pause
from tests.execskill_v226_fakes import DiagnosticsWorker, authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_v225_read import synthetic_units
from tests.test_execskill_v226_card_units import candidate_pair, zebra_pool


def faulty_hook(monkeypatch, *, parent=False):
    original = DiagnosticsWorker.call
    def hook_error(self, proc, hook, args, **kw):
        if hook == 'before_call' and (parent or self.package.card_for(p.ZEBRA) is not None):
            raise ValueError('private-item-id-and-exception-message')
        return original(self, proc, hook, args, **kw)
    monkeypatch.setattr(DiagnosticsWorker, 'call', hook_error)


def test_single_card_error_rejects_with_only_safe_event_and_resume_deduplicates(tmp_path, monkeypatch):
    parent, candidate = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    faulty_hook(monkeypatch)
    result = phase.measure(st, zebra_pool(2), parent, candidate, name='card-train-c1', kind='selftest', runs=1)
    assert result['decision'] == 'reject' and result['reason'] == 'candidate_error'
    event = result['candidate_error']
    assert set(event) == {'kind', 'exception', 'where'}
    assert event['exception'] == 'ValueError' and event['where'].endswith(':hook_error')
    assert 'private-item' not in json.dumps(event)
    assert result['cells'] == 0 and not result['registered'] and st.services.registry.calls == []
    assert v226_candidates.counts(st.root) == {v226_candidates.signature(event): 1}
    assert phase.measure(st, zebra_pool(2), parent, candidate, name='card-train-c1', kind='selftest', runs=1) == result
    assert v226_candidates.counts(st.root) == {v226_candidates.signature(event): 1}
    assert not (st.root/'card-train-c1/attempt-1/status.json').exists()


def test_consecutive_card_candidates_with_same_error_still_pause(tmp_path, monkeypatch):
    parent, candidate = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    faulty_hook(monkeypatch)
    first = phase.measure(st, zebra_pool(2), parent, candidate, name='card-train-c1', kind='selftest', runs=1)
    second = phase.place_card(parent, v225_cards.make_card(p.ZEBRA, 'A different card checks the clues.', round=2), step=st.name)
    with pytest.raises(Pause) as raised:
        phase.measure(st, zebra_pool(2), parent, second, name='card-train-c2', kind='selftest', runs=1)
    assert raised.value.kind == 'configuration'
    assert v226_candidates.counts(st.root) == {v226_candidates.signature(first['candidate_error']): 2}


def test_parent_card_path_error_is_never_contained(tmp_path, monkeypatch):
    parent, candidate = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    faulty_hook(monkeypatch, parent=True)
    with pytest.raises(Pause) as raised:
        phase.measure(st, zebra_pool(2), parent, candidate, name='card-train-c1', kind='selftest', runs=1)
    assert raised.value.kind == 'configuration'
    assert v226_candidates.counts(st.root) == {}


def test_paid_card_dispatch_error_is_not_mislabeled_candidate_fault(tmp_path, monkeypatch):
    parent, candidate = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    st.solver = lambda *a, **kw: None
    def dispatch_error(*a, **kw):
        raise ValueError('dispatch plumbing error')
    monkeypatch.setattr(step, '_cells', dispatch_error)
    with pytest.raises(Pause):
        phase.measure(st, zebra_pool(2), parent, candidate, name='card-train-c1', kind='selftest', runs=1)
    assert v226_candidates.counts(st.root) == {}


def test_cross_card_candidate_error_keeps_own_accepted_card(tmp_path, monkeypatch):
    parent = package.empty(step='G/s0', evidence='engineering_fixture')
    own = v225_cards.make_card('searchqa', 'Check corroborating evidence.')
    incumbent = phase.place_card(parent, own, step='G/s1-searchqa')
    st, _ = authored_step(tmp_path, parent, bench='searchqa', k=1)
    package.save(st.chain_root, incumbent)
    def cross_error(*args, **kwargs):
        raise ValueError('private cross item')
    monkeypatch.setattr(v222_runtime, 'cross_gate', cross_error)
    selected, rows = phase.cross_cards(st, incumbent, own)
    assert selected.sha256 == incumbent.sha256 and len(rows) == 1
    assert rows[0]['decision'] == 'reject' and rows[0]['reason'] == 'candidate_error'
    assert rows[0]['candidate_error']['where'].endswith(':cross_error')
    assert phase.cross_bindings(rows) == []


def test_readout_candidate_errors_are_counts_and_main_v9_unchanged(fast_statistics):
    units = synthetic_units()
    counts = {'ValueError@authored:hook_error': 2, 'KeyError@authored:render': 1}
    arguments = dict(learned=[], procedures={}, label='authored', evidence='engineering_fixture')
    result = v225_read.readout(units, **arguments, configuration=p.MAIN_V10, candidate_errors=counts)
    assert result['candidate_errors'] == counts and result['candidate_error_count'] == 3
    old = v225_read.readout(units, **arguments)
    assert 'candidate_errors' not in old and 'candidate_error_count' not in old
    assert old == v225_read.readout(units, **arguments, configuration=p.MAIN_V9, candidate_errors=counts)


def test_report_sums_each_completed_step_candidate_errors(tmp_path, monkeypatch, fast_statistics):
    from skillopt.execskill import evaluation
    root = tmp_path/'run'
    expected = {'ValueError@authored:hook_error': 3}
    for chain in p.CHAINS:
        cr = root/chain
        final = package.empty(step=chain+'/s0', evidence='engineering_fixture')
        package.save(cr, final)
        write_json(cr/'test-read.json', p.record('test-read', 'engineering_fixture', {
            'status': 'read', 'arms': list(v225_read.ARMS), 'package_sha256': final.sha256}))
        for k, bench in enumerate(p.MAIN_V5_ORDER, 1):
            write_json(cr/('s%d-%s' % (k, bench))/'step.json', p.record('step', 'engineering_fixture', {
                'package_sha256': final.sha256,
                'candidate_errors': {'ValueError@authored:hook_error': k} if k in (1, 2) else {}}))
    monkeypatch.setattr(evaluation, 'unseal', lambda *a, **kw: {'units': synthetic_units(), 'label': 'authored'})
    out = tmp_path/'report'
    v225_read.report({'configuration': p.MAIN_V10, 'root': str(root), p.RECORD_HASH: 'authored',
                      'evidence': 'engineering_fixture'}, out=out)
    for chain in p.CHAINS:
        record = read_json(out/('readout-'+chain+'.json'))
        aggregate = read_json(out/('readout-aggregates-'+chain+'.json'))
        assert record['candidate_errors'] == expected and record['candidate_error_count'] == 3
        assert aggregate['chains'][chain]['candidate_errors'] == expected
        assert aggregate['chains'][chain]['candidate_error_count'] == 3


def test_card_controller_advances_after_candidate_error_and_accepts_next_card(tmp_path, monkeypatch):
    original = step._pair_signatures
    def first_card_error(st, candidate, parent, publics, views, **kwargs):
        card = candidate.card_for(st.bench)
        if card is not None and card.id.endswith('-101'):
            raise ValueError('private item of first card')
        return original(st, candidate, parent, publics, views, **kwargs)
    monkeypatch.setattr(step, '_pair_signatures', first_card_error)
    result = phase.authored_phase_smoke(tmp_path/'phase', configuration=p.MAIN_V10, scenario='training')
    assert result['rounds'][0]['decision'] == 'reject'
    assert result['rounds'][0]['reason'] == 'candidate_error'
    assert result['rounds'][0]['candidate_error']['where'].endswith(':first_card_error')
    assert result['rounds'][1]['decision'] == 'accept'
    assert result['accepted_training_unit'] == 'card-train-c2'


@pytest.mark.parametrize('reason', ['candidate_error', 'cross_bench_harm'])
def test_writer_receives_safe_new_rejection_clause_only_in_main_v10(reason):
    from skillopt.execskill import v225_writer
    feedback = {'stage': 'acceptance', 'clause': reason, 'decision': 'reject'}
    assert v225_writer.count_result(feedback, configuration=p.MAIN_V10)['failing_clause'] == reason
    for configuration in (None, p.MAIN_V9, p.MAIN_V8):
        with pytest.raises(ValueError, match='registered failing clause'):
            v225_writer.count_result(feedback, configuration=configuration)
