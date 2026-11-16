"""Unit-bound real card identities, loud contradictions and rejected cross harm."""
from dataclasses import replace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import policy, profiles as p, solver, step, v222_runtime, v225_cards, v225_phase as phase
from skillopt.execskill.cells import Pause
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import procedure
from tests.execskill_v226_fakes import authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def zebra_pool(count=40):
    return [{'task_id': 'authored-%02d' % n, 'benchmark': p.ZEBRA, 'partition': 'practice',
        'public': {'question': 'There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. Compare clues.',
                   'columns': ['Name', 'Color']}, 'private': {'answer': 'authored'}} for n in range(count)]


def candidate_pair(bench=p.ZEBRA):
    parent = empty(step='G/s0', evidence='engineering_fixture')
    if bench == p.ZEBRA:
        proc = procedure('fx-card-unit-zebra', ('applies', 'before_call'), origin=p.ZEBRA,
            policy_version=policy.POLICY_VERSION_V222,
            source="def applies(view):\n    return 'columns' in view\n\ndef before_call(view, state):\n    return {'facts': ['Compare the constraints.'], 'diagnostics': {'extra': 'x' * 2048}}\n")
        parent = with_(parent, step='G/s3-zebralogic', add=[proc])
    return parent, with_(parent, step='G/s3-zebralogic', add=[
        v225_cards.make_card(bench, 'Compare the supplied clues carefully.')])


def authored_cells(_st, attempt, endpoint, label, jobs, **kwargs):
    return [{'cell': {'id': '%s-%s-%s' % (arm, key, run), 'arm': arm, 'task_id': key, 'run': run},
             'judge': {'v2': {'token': 'pass' if arm == "S'" else 'fail'}},
             'faults': [], 'stop': None} for arm, _, key, run, _ in jobs]


def test_zebra_card_selection_and_measure_use_real_unit_bound_diagnostics(tmp_path, monkeypatch):
    parent, candidate = candidate_pair()
    st, workers = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    st.solver = lambda *a, **kw: None
    pool = zebra_pool()
    monkeypatch.setattr(step, '_cells', authored_cells)
    result = phase.measure(st, pool, parent, candidate, name='card-accept-c1', kind='accept', runs=1,
        consume=True, selection=({'accept': pool}, 1, 'accept'))
    assert result['decision'] == 'accept' and result['rule']['touched'] == 40
    assert [call[0] for call in st.services.registry.calls] == ['register', 'dispatch', 'decide']
    assert workers.opened and all(worker.diagnostics_configuration == p.ZEBRA_PC_V15 for worker in workers.opened)
    assert all(worker.options.get('tag') for worker in workers.opened)
    assert all(call[-1] for worker in workers.opened for call in worker.calls if call[1] == 'before_call')
    assert all(pair[arm]['faults'] == [] for pair in result['request_signatures'].values() for arm in ('S', "S'"))
    # Compare with the ordinary Zebra unit, retaining exact faults and identities.
    def reference(attempt):
        publics = {item['task_id']: item['public'] for item in pool}
        return step._pair_signatures(st, candidate, parent, publics,
            [(key, solver.routing_view(p.ZEBRA, public)) for key, public in publics.items()])
    assert st.unit('train-r1', reference) == result['request_signatures']
    selection = p.verified(read_json(st.root/'card-accept-selection-c1.json'), 'v225-card-selection')
    assert selection['core']['configuration'] == p.MAIN_V10
    plan = p.verified(read_json(st.root/'card-accept-c1/card-request-plan.json'), 'v226-card-requests')
    assert plan['request_signatures'] == result['request_signatures']


@pytest.mark.parametrize('narrowed', [False, True])
def test_card_cross_gate_failure_or_narrowing_records_rejection_not_pause(tmp_path, monkeypatch, narrowed):
    parent, candidate = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    gate = {'passed': narrowed, 'candidate_sha256': parent.sha256 if narrowed else None,
            'reason': 'cross_bench_harm'}
    monkeypatch.setattr(v222_runtime, 'cross_gate', lambda *a, **kw: (parent if narrowed else None, gate))
    result = phase.measure(st, zebra_pool(2), parent, candidate, name='card-accept-c1', kind='accept',
                           runs=1, consume=True, cross=True)
    assert result['decision'] == 'reject' and result['reason'] == 'cross_bench_harm'
    assert result['cross_gate'] == gate and result['cells'] == 0
    assert st.services.registry.calls == []
    record = p.verified(read_json(st.root/'card-accept-c1/unit.json'), 'unit')
    assert record['result']['reason'] == 'cross_bench_harm'
    assert not (st.root/'card-accept-c1/attempt-1/status.json').exists()


def test_changed_card_with_forced_identical_requests_is_a_loud_configuration_pause(tmp_path, monkeypatch):
    parent, candidate = candidate_pair()
    st, _ = authored_step(tmp_path, parent, bench=p.ZEBRA, k=3)
    original = step._pair_signatures
    def contradicted(*args, **kw):
        pairs = original(*args, **kw)
        return {key: {'S': row['S'], "S'": row['S']} for key, row in pairs.items()}
    monkeypatch.setattr(step, '_pair_signatures', contradicted)
    with pytest.raises(Pause) as raised:
        phase.measure(st, zebra_pool(2), parent, candidate, name='card-train-c1', kind='selftest', runs=1)
    assert raised.value.kind == 'configuration'
    assert 'card_request_identity_defect:zebralogic' in raised.value.reason


@pytest.mark.parametrize('bench', phase.CARD_ACCEPT_ITEMS)
def test_authored_main_v10_phase_smoke_uses_real_request_identity(tmp_path, monkeypatch, bench):
    original = step._pair_signatures
    seen = []
    def observe(*args, **kw):
        result = original(*args, **kw)
        seen.append(result)
        return result
    monkeypatch.setattr(step, '_pair_signatures', observe)
    result = phase.authored_phase_smoke(tmp_path/bench, bench=bench, configuration=p.MAIN_V10)
    assert result['passed'] and result['rounds'][0]['decision'] == 'accept'
    assert seen and all(phase.request_changed(row) == list(row) for row in seen)
