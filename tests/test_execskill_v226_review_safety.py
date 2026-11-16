"""Review regressions for corrupt receipts and durable systematic errors."""
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import profiles as p, step, v226_candidates as c, v222_runtime
from skillopt.execskill.cells import Pause
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v226_candidates import fixture, run, _raise
from tests.test_execskill_v226_resume import setup, redo
from tests.test_execskill_v226_card_units import zebra_pool


@pytest.mark.parametrize('payload', ['{', '[]', '{"unsealed": true}'])
@pytest.mark.parametrize('site', ['confirmation', 'selftest', 'acceptance'])
def test_corrupt_sealed_receipt_pauses_without_candidate_error(tmp_path, monkeypatch, site, payload):
    st, parent, candidate, state, _ = setup(tmp_path, monkeypatch)
    rows = zebra_pool(2)
    if site == 'confirmation':
        path = st.root/'confirm-selection-r1.json'
        invoke = lambda: step._confirm_eval(st, {'confirm': rows}, 1, parent, candidate, exercise=True)
        unit = 'confirm-r1'
    elif site == 'selftest':
        path = st.root/'selftest/request-plan.json'
        generated = {'g_self': [{**row, 'id': row['task_id']} for row in rows]}
        invoke = lambda: step._selftest(st, 'selftest', candidate, generated, candidate_key='procedure-r1')
        unit = 'selftest'
    else:
        path = st.root/'accept-r1/sealed.json'
        monkeypatch.setattr(v222_runtime, 'cross_gate', lambda *a, **kw: (candidate, {'passed': True}))
        monkeypatch.setattr(step, '_g_acc', lambda *a: None)
        invoke = lambda: step._accept(st, {'accept': rows}, candidate, None, unit='accept-r1')
        unit = 'accept-r1'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
    with pytest.raises(Pause) as raised:
        invoke()
    assert raised.value.kind == 'configuration'
    assert c.counts(st.root) == {}
    assert read_json(st.root/unit/'attempt-1/status.json')['kind'] == 'configuration'


def test_nonconsecutive_candidate_signature_is_systematic(tmp_path):
    st, parent = fixture(tmp_path)
    run(st, parent, 'r1', lambda _: _raise(KeyError('first')))
    run(st, parent, 'r2', lambda _: {})
    with pytest.raises(KeyError):
        run(st, parent, 'r3', lambda _: _raise(KeyError('repeat')))


def test_prior_step_candidate_signature_is_systematic(tmp_path):
    st, parent = fixture(tmp_path/'G/s2-officeqa')
    st.chain_root, st.k = tmp_path/'G', 2
    result = run(st, parent, 'r1', lambda _: _raise(KeyError('first')))
    write_json(st.root/'step.json', p.record('step', st.evidence,
        {'candidate_errors': c.counts(st.root), 'candidate_error_events': [result['fault']]}))
    later, _ = fixture(tmp_path/'G/s3-zebralogic')
    later.chain_root, later.k = st.chain_root, 3
    with pytest.raises(KeyError):
        run(later, parent, 'r1', lambda _: _raise(KeyError('repeat')))


def test_deleted_journal_tail_is_detected_by_unit_anchor(tmp_path, monkeypatch):
    st, parent, candidate, _, _ = setup(tmp_path, monkeypatch)
    st.unit('train-r1', c.guard(st, 'r1', parent,
        lambda _: _raise(KeyError('first')), lambda event: {'candidate_error': event}))
    paths = sorted((st.root/c.FILE).glob('*.json'))
    paths[-1].unlink()
    with pytest.raises(ValueError, match='anchor'):
        c.counts(st.root)


def test_step_error_counts_must_match_unit_and_journal(tmp_path, monkeypatch):
    st, parent, candidate, _, _ = setup(tmp_path, monkeypatch)
    st.unit('train-r1', c.guard(st, 'r1', parent,
        lambda _: _raise(KeyError('first')), lambda event: {'candidate_error': event}))
    write_json(st.root/'step.json', p.record('step', st.evidence, {'candidate_errors': {}}))
    with pytest.raises(ValueError, match='counts'):
        c.counts(st.root)


def test_immediate_cross_rejection_precedes_acceptance_selection(tmp_path, monkeypatch):
    st, parent, candidate, _, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(v222_runtime, 'cross_gate', lambda *a, **kw:
        (None, {'passed': False, 'proposed_sha256': candidate.sha256}))
    selected = []
    def select():
        selected.append(True)
        return zebra_pool(2), {}
    result = step._accept(st, {'accept': zebra_pool(2)}, candidate, None,
                          unit='accept-r1', incumbent=parent, select=select)
    assert result['reason'] == 'cross_bench_harm'
    assert selected == [] and st.services.registry.calls == []


def test_accepted_candidate_final_selftest_is_system_work(tmp_path, monkeypatch):
    from tests.test_execskill_v226_procedure_errors import setup as faulty_setup
    st, parent, candidates, rows, _ = faulty_setup(tmp_path, monkeypatch)
    candidate = candidates[0]
    monkeypatch.setattr(step, '_train', lambda *a: (candidate, [], candidate))
    monkeypatch.setattr(step, '_audit_final', lambda *a: (candidate, {}))
    monkeypatch.setattr(step, '_audit_summary', lambda *a: {})
    monkeypatch.setattr(step, '_v221_final_acceptance', lambda *a:
        (candidate, {'decision': 'accept'}, {'selected_round': 1}))
    generated = {'g_self': [{**row, 'id': row['task_id']} for row in rows]}
    with pytest.raises(Pause):
        step._trained(st, {}, generated)
    assert c.counts(st.root) == {}


def test_shared_acceptance_card_reference_failure_is_system_work(tmp_path, monkeypatch):
    from skillopt.execskill import acceptance, reuse, solver
    from skillopt.execskill.package import with_
    from tests.test_execskill_v226_identity import fixture_step
    from skillopt.execskill.v225_cards import make_card
    from tests.execskill_fakes_env import procedure
    st, task, initial, candidate, _ = fixture_step(tmp_path, 'searchqa')
    # P0 differs from the current incumbent, so package equality cannot identify its role.
    parent = with_(initial, step='G/s1', add=[procedure('fx-parent-note', ('applies', 'before_call'),
        source="def applies(view):\n    return True\n\ndef before_call(view, state):\n    return 'Read all supplied evidence.'\n")])
    candidate = with_(parent, step='G/s1', add=[make_card('searchqa', 'Compare the evidence carefully.')])
    st.root, st.evidence = tmp_path/'step', 'engineering_fixture'
    original = reuse.signature
    def signature(bench, package, *a, **kw):
        if package.sha256 == initial.sha256:
            raise KeyError('shared P0 renderer')
        return original(bench, package, *a, **kw)
    monkeypatch.setattr(reuse, 'signature', signature)
    key, public = task['task_id'], task['public']
    def work(_):
        return acceptance.prepare(tmp_path/'accept', chain='G', bench=st.bench, step='G/s1',
            unit='G/s1/accept-r1', candidate=candidate, parent=parent,
            views={key: solver.routing_view(st.bench, public)}, blocks={key: 'block'},
            workers=step._item_workers(st, {key: public}), trajectories=[], configuration=p.MAIN_V10,
            initial=initial, rule=p.acceptance_rule(p.MAIN_V10, st.bench),
            reuse={'card_text': st.setting.cards[st.bench], 'runtime': {}})
    with pytest.raises(KeyError):
        c.guard(st, 'r1', parent, work, lambda event: {'candidate_error': event})(None)
    assert c.counts(st.root) == {}
