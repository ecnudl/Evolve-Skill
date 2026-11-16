"""Authored production-unit wiring and package bindings; no external service."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (profiles as p, step, v221_learning, v222_alf_views, v222_cards,
                               v222_gate, v222_runtime as runtime)
from skillopt.execskill.package import save
from tests.test_execskill_v221_learning import FixtureStep, packages, pool, signature
from tests.test_execskill_v222_gate import pools
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.execskill_v222_fakes import alf_rows


@pytest.fixture(autouse=True)
def no_native_alfworld(monkeypatch):
    monkeypatch.setattr(runtime.supply, 'alfworld_reset',
        lambda *args, **kwargs: pytest.fail('Authored pinned views must not open a native ALFWorld session'))


def pin_practice(st):
    """Prepare the real overlay over authored, already reset-view-pinned games."""
    available, excluded = runtime._training_allocations(st)
    harms = v222_gate.harm_slices(available, excluded=excluded)
    decomposition = v222_cards.decomposition_slices({bench: [row['task_id'] for row in rows]
                                                    for bench, rows in available.items()})
    overlay = v222_alf_views.prepare(available['alfworld'], harms['alfworld'], decomposition['alfworld'],
                                     runtime=st.runtime['alfworld'])
    st.extra['v222_practice'] = {v222_alf_views.KEY: overlay}
    attached, excluded = runtime.routing_allocations(st)
    st.extra['v222_practice'].update(harm=v222_gate.registration(v222_gate.harm_slices(attached, excluded=excluded)),
        v222_practice_supply=v222_gate.practice_supply(attached, excluded=excluded))


def setting(root):
    rows = pools()
    rows['alfworld'], alf_runtime = alf_rows(rows['alfworld'], root/'alfworld')
    allocations = {bench: {'slices': {'run': [row['task_id'] for row in items[:80]],
        'accept': [row['task_id'] for row in items[80:]]}} for bench, items in rows.items()}
    st = SimpleNamespace(shared=root/'shared', pools=rows, runtime={'alfworld': alf_runtime},
        extra={'configuration': p.MAIN_V8, 'v211_allocation': allocations})
    pin_practice(st)
    return st


def test_preflight_registers_fixed_slices_once_and_refuses_changed_public_rows(tmp_path):
    st = setting(tmp_path)
    slices, first = runtime.preflight(st)
    assert first == read_json(st.shared/'v222-harm-slices.json')
    assert runtime.preflight(st) == (slices, first)
    selected = slices['officeqa'][0]['task_id']
    next(row for row in st.pools['officeqa'] if row['task_id'] == selected)['public']['question'] = 'Changed'
    with pytest.raises(ValueError, match='changed after registration|differ from S0 registration'):
        runtime.preflight(st)


def test_preflight_uses_actual_eighteen_items_and_stops_below_floor(tmp_path):
    st = setting(tmp_path)
    allocation = st.extra['v211_allocation']['officeqa']['slices']
    allocation['accept'] += allocation['run'][18:]
    allocation['run'] = allocation['run'][:18]
    pin_practice(st)
    slices, record = runtime.preflight(st)
    assert len(slices['officeqa']) == record['benches']['officeqa']['items'] == 18
    assert not set(allocation['accept']) & {row['task_id'] for row in slices['officeqa']}
    allocation['accept'].append(allocation['run'].pop())
    with pytest.raises(ValueError, match='18'):
        runtime.preflight(st)


def test_preflight_allows_confirmation_and_spares_but_never_acceptance(tmp_path):
    st = setting(tmp_path)
    allocation = st.extra['v211_allocation']['officeqa']['slices']
    allocation['confirm-r1'] = allocation['run'][18:]
    allocation['run'] = allocation['run'][:18]
    available, excluded = runtime._training_allocations(st)
    assert len(available['officeqa']) == 80
    assert set(allocation['confirm-r1']) <= {row['task_id'] for row in available['officeqa']}
    assert excluded['officeqa'] == allocation['accept']
    st.extra['v222_practice']['v222_practice_supply'] = v222_gate.practice_supply(available, excluded=excluded)
    assert len(runtime.preflight(st)[0]['officeqa']) == 60
    st.extra['v222_practice']['v222_practice_supply']['benches']['officeqa']['available'] += 1
    with pytest.raises(ValueError, match='registered actual'):
        runtime.preflight(st)


def test_additional_loaded_practice_supply_is_bound_but_does_not_recut_home_allocations(tmp_path):
    st = setting(tmp_path); before = deepcopy(st.extra['v211_allocation'])
    extra = [{**row, 'task_id': 'additional-' + row['task_id']} for row in st.pools['officeqa']]
    st.extra['v222_harm_pools'] = {'officeqa': extra}
    pin_practice(st)
    slices, record = runtime.preflight(st)
    available, excluded = runtime._training_allocations(st)
    assert len(available['officeqa']) == len(extra) + 80
    assert set(before['officeqa']['slices']['run']) <= {row['task_id'] for row in available['officeqa']}
    assert not set(excluded['officeqa']) & {row['task_id'] for row in slices['officeqa']}
    assert st.extra['v211_allocation'] == before
    assert record['benches']['officeqa']['items'] == 60


@pytest.mark.parametrize('home_pass', [True, False])
def test_confirmation_checks_cross_bench_even_when_home_verdict_fails(monkeypatch, home_pass):
    parent, candidates = packages(); candidate = candidates[0]; called = []
    gate = {'passed': False, 'proposed_sha256': candidate.sha256, 'candidate_sha256': None}
    def check(st, attempt, **kw):
        called.append(kw); return None, gate
    monkeypatch.setattr(runtime, 'cross_gate', check)
    result = runtime.confirmation(None, None, unit='confirm-r1', parent=parent, candidate=candidate,
                                  result={'confirm': {'passed': home_pass, 'reason': None}})
    assert called[0]['phase'] == 'confirmation'
    assert not result['confirm']['passed'] and result['confirm']['reason'] == 'cross_bench_harm'
    assert result['cross_gate'] == gate and result['accepted_candidate_sha256'] is None


def test_failed_acceptance_cross_gate_prevents_home_registration_dispatch_and_settlement(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); st = FixtureStep(tmp_path, parent)
    st.setting.extra['configuration'] = p.MAIN_V8
    def rejected(st, attempt, **kwargs):
        assert kwargs['phase'] == 'acceptance'
        return None, {'passed': False, 'proposed_sha256': candidates[0].sha256}
    monkeypatch.setattr(runtime, 'cross_gate', rejected)
    st.solver = lambda *args, **kw: pytest.fail('No home solver may be created after rejected gate')
    found = step._accept(st, {'accept': pool(10)}, candidates[0], None, unit='accept-r1')
    assert found['decision'] == 'not_run' and found['reason'] == 'cross_bench_harm'
    assert st.services.registry.calls == []
    assert not found['cross_gate']['passed']


def test_narrowed_confirmation_binds_loaded_package_and_preserves_home_cell_provenance(tmp_path):
    parent, candidates = packages(tmp_path); original = candidates[0]
    narrowed = v222_gate.narrow_additions(parent, original, home='searchqa', benches=['officeqa'])
    save(tmp_path, narrowed); st = FixtureStep(tmp_path, parent)
    gate = {'passed': True, 'proposed_sha256': original.sha256, 'candidate_sha256': narrowed.sha256,
            'benches': {'officeqa': {'fired': 10, 'passed': False, 'fixed': 0, 'broken': 10, 'net': -10}}}
    confirmation = {'cross_gate': gate, 'accepted_candidate_sha256': narrowed.sha256}
    chosen = runtime.confirmed_candidate(st, original, confirmation)
    bound = runtime.bind_training({'candidate_sha256': original.sha256, 'feedback': {}}, chosen, confirmation)
    assert chosen.sha256 == bound['candidate_sha256'] == narrowed.sha256
    assert bound['home_measured_candidate_sha256'] == original.sha256
    assert bound['feedback']['cross_gate']['benches']['officeqa']['broken'] == 10
    with pytest.raises(ValueError, match='candidate-bound'):
        runtime.confirmed_candidate(st, candidates[1], confirmation)


def test_acceptance_narrowing_keeps_selection_and_exact_final_contrast_binding(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); original = candidates[0]
    st = FixtureStep(tmp_path, parent); st.setting.extra['configuration'] = p.MAIN_V8
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kw: public)
    monkeypatch.setattr(step, '_pair_signatures', lambda st, candidate, incumbent, publics, views: {
        key: {'S': signature('base'), "S'": signature('candidate')} for key, _ in views})
    def accept(st, cut, contrast, generated, **kw):
        narrowed = v222_gate.narrow_additions(parent, contrast, home='searchqa', benches=['officeqa'])
        save(st.chain_root, narrowed)
        return {'decision': 'accept', 'reason': None, 'candidate_sha256': narrowed.sha256,
                'incumbent_sha256': parent.sha256, 'cross_gate': {'passed': True}, 'decision_sha256': 'a'*64}
    monkeypatch.setattr(step, '_accept', accept)
    accepted = v221_learning.immediate_acceptance(st, {'accept': pool(60)}, 1, parent, original)
    selected = accepted['selection']
    assert selected['candidate_sha256'] == original.sha256
    binding = accepted['accepted_binding']
    assert binding['accepted_candidate_sha256'] == accepted['accepted_candidate_sha256']
    assert binding['accepted_contrast_candidate_sha256'] == accepted['contrast_candidate_sha256']
    assert binding['accepted_candidate_sha256'] != original.sha256
    # A resume retains the original sampling identity, including its original candidate.
    monkeypatch.setattr(step, '_pair_signatures', lambda *args: pytest.fail('No resampling'))
    assert v221_learning.immediate_acceptance(st, {'accept': pool(60)}, 1, parent, original) == accepted


def test_split_and_merge_keep_their_cross_narrowings_and_candidate_bindings(tmp_path):
    from skillopt.execskill import v221_split
    from tests.test_execskill_v221_learning import training, confirmation
    parent, candidates = packages(tmp_path); full = candidates[1]
    st = FixtureStep(tmp_path, parent); st.setting.extra['configuration'] = p.MAIN_V8
    checked = []
    def evaluate(st, cut, r, n, incumbent, candidate, full, source, generated, **kw):
        if not kw.get('confirmation'):
            return {**training(3), 'candidate_sha256': candidate.sha256}
        narrowed = v222_gate.narrow_additions(incumbent, candidate, home='searchqa', benches=['officeqa'])
        save(st.chain_root, narrowed)
        checked.append((n, narrowed.sha256))
        return {**confirmation(3), 'accepted_candidate_sha256': narrowed.sha256,
                'cross_gate': {'passed': True, 'proposed_sha256': candidate.sha256,
                               'candidate_sha256': narrowed.sha256, 'benches': {}}}
    selected, result = v221_split.run(st, {}, 1, parent, full,
        {'engineer': {'changes': [{'id': pid, 'kind': 'new', 'target': None} for pid in full.order]}},
        {**training(6), 'candidate_sha256': full.sha256}, confirmation(0, 3), None,
        current=[], evaluator=evaluate)
    assert [n for n, _ in checked] == [1, 2, 'merge']
    assert result['adopted'] and selected.order == full.order and selected.for_bench('officeqa') == ()
    assert selected.sha256 == result['candidate_sha256'] == checked[-1][1]
    assert all('officeqa' in selected.narrowed[pid] for pid in selected.order)


@pytest.mark.parametrize('field,value', [('home', 'officeqa'), ('unit', 'G/s9-searchqa/confirm-r1'),
                                        ('configuration', p.MAIN_V7)])
def test_completed_cross_gate_cannot_be_replayed_for_another_scope(tmp_path, monkeypatch, field, value):
    parent, candidates = packages(tmp_path); candidate = candidates[0]
    st = FixtureStep(tmp_path, parent); st.setting.extra['configuration'] = p.MAIN_V8
    attempt = st.root/'confirm-r1'/'attempt-2'; attempt.mkdir(parents=True)
    fields = {'phase': 'confirmation', 'configuration': p.MAIN_V8, 'home': 'searchqa',
        'unit': st.label('confirm-r1'), 'parent_sha256': parent.sha256,
        'proposed_sha256': candidate.sha256, 'candidate_sha256': candidate.sha256,
        'harm_registration_sha256': 'c'*64, 'passed': True}
    fields[field] = value
    write_json(attempt.parent/'v222-cross-completed.json', p.record('v222-cross-gate', st.evidence, fields))
    monkeypatch.setattr(runtime, 'preflight', lambda setting: ({}, {'sha256': 'c'*64, 'benches': {'officeqa': {'items': 60}}}))
    with pytest.raises(ValueError, match='original candidate, parent and harm slices'):
        runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation', parent=parent, candidate=candidate)


def test_completed_cross_gate_retry_is_exactly_read_back_without_worker_or_model(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); candidate = candidates[0]
    st = FixtureStep(tmp_path, parent); st.setting.extra['configuration'] = p.MAIN_V8
    attempt = st.root/'confirm-r1'/'attempt-2'; attempt.mkdir(parents=True)
    record = p.record('v222-cross-gate', st.evidence, {'phase': 'confirmation',
        'configuration': p.MAIN_V8, 'home': 'searchqa', 'unit': st.label('confirm-r1'),
        'parent_sha256': parent.sha256, 'proposed_sha256': candidate.sha256,
        'candidate_sha256': candidate.sha256, 'harm_registration_sha256': 'c'*64, 'passed': True})
    write_json(attempt.parent/'v222-cross-completed.json', record)
    monkeypatch.setattr(runtime, 'preflight', lambda setting: ({}, {'sha256': 'c'*64, 'benches': {'officeqa': {'items': 60}}}))
    monkeypatch.setattr(v222_gate, 'inspect', lambda *a, **kw: pytest.fail('No repeated routing'))
    st.solver = lambda *a, **kw: pytest.fail('No repeated model call')
    selected, found = runtime.cross_gate(st, attempt, unit='confirm-r1', phase='confirmation',
                                        parent=parent, candidate=candidate)
    assert selected == candidate and found == record
    assert read_json(attempt/'v222-cross-gate.json') == record


@pytest.mark.parametrize('number', [1, 2])
def test_acceptance_cross_pairs_charge_original_or_redo_scope_by_attempt(tmp_path, monkeypatch, number):
    from skillopt.execskill import budgets, units
    parent, candidates = packages(tmp_path); candidate = candidates[0]
    st = FixtureStep(tmp_path, parent); st.setting.extra['configuration'] = p.MAIN_V8
    st.setting.clients = lambda model, bench: SimpleNamespace(model=model)
    attempt = st.root/'accept-r1'/('attempt-%d' % number); attempt.mkdir(parents=True)
    monkeypatch.setattr(runtime, 'preflight', lambda setting: ({}, {'sha256': 'c'*64, 'benches': {'officeqa': {'items': 60}}}))
    monkeypatch.setattr(budgets, 'endpoint', lambda setting, scopes, **kwargs: scopes)
    endpoints = []
    def endpoint(kind, path, **kwargs):
        scopes = units.solver_endpoint(st.setting, st.chain, st.bench, st.k, kind, path, **kwargs)
        endpoints.append((kwargs, scopes))
        return scopes
    st.solver = endpoint
    def cells(st, path, solvers, name, jobs, **kwargs):
        assert len(jobs) == 2 and solvers['officeqa'] == endpoints[-1][1]
        return [{'cell': {'arm': arm, 'task_id': key}} for arm, package, key, run, task in jobs]
    monkeypatch.setattr(step, '_cells', cells)
    def check(**kwargs):
        kwargs['run_pairs']('officeqa', parent, candidate, pools()['officeqa'][:1])
        return candidate, p.record('v222-cross-gate', st.evidence, {'passed': True})
    monkeypatch.setattr(v222_gate, 'check', check)
    selected, record = runtime.cross_gate(st, attempt, unit='accept-r1', phase='acceptance',
                                          parent=parent, candidate=candidate)
    assert selected == candidate and record['new_model_cells'] == 2
    assert endpoints == [({'cell_bench': 'officeqa'},
                          budgets.solver_scopes('G', 'searchqa', 1, 'accept', number))]
    assert ('G:redo' in endpoints[0][1]) is (number == 2)


def test_no_parent_measurements_yields_no_hygiene_candidate_and_no_pause(tmp_path, monkeypatch):
    from skillopt.execskill import v222_cards
    parent = v222_cards.initial_package(evidence='engineering_fixture', step='G/s0')
    st = FixtureStep(tmp_path, parent); st.setting.extra['configuration'] = p.MAIN_V8
    monkeypatch.setattr(runtime, 'initial_package', lambda st: parent)
    selected, found = runtime.hygiene_candidate(st, {'run': pool(10)}, 1, parent, [])
    assert selected is None and found['hygiene_mode'] == 'measured_candidates'
    assert found['reason'] == 'no_negative_supported_segment'
    assert not list(st.root.glob('*pending*'))


@pytest.mark.parametrize('bench,k', [('searchqa', 1), ('alfworld', 5)])
def test_first_run_and_fixed_import_are_not_preceded_by_hygiene_pause(tmp_path, monkeypatch, bench, k):
    from skillopt.execskill import v210_import, v222_cards
    parent = v222_cards.initial_package(evidence='engineering_fixture', step='G/s0')
    config = SimpleNamespace(root=tmp_path, extra={'configuration': p.MAIN_V8}, evidence='engineering_fixture')
    monkeypatch.setattr(step, '_slices', lambda st: {'run': pool(20)})
    monkeypatch.setattr(runtime, 'hygiene_candidate', lambda *a: pytest.fail('Hygiene only follows measured parent cells'))
    class ReachedOrdinaryWork(Exception): pass
    def reached(*a, **kw): raise ReachedOrdinaryWork()
    monkeypatch.setattr(step, '_run', reached)
    monkeypatch.setattr(v210_import, 'import_step', reached)
    with pytest.raises(ReachedOrdinaryWork):
        step.run_step(config, 'G', bench, k, parent, services=None)
    assert not hasattr(runtime, 'hygiene_before_training')
