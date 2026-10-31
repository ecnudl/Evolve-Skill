"""Offline implant preparation and measured-readiness checks on authored fixtures."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, client, manifest, profiles as p, units,
                               v214_preparation, v214_smoke as v, v214_stages as stages)
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_manifest import reseal
from tests.test_execskill_v214_preparation import prepared
from tests.test_execskill_v214_smoke import measured_probe, measured_s2

CHILD = p.IMPLANT_V5


def owner_consent():
    return {'by': 'owner', 'date': '2026-11-01', 'note': 'Authored delegated five-benchmark implant consent.',
            'test_evaluation': True, 'sheet_test_qualification': True,
            'multi_arm_arms': ['F', 'C', 'B', 'stages']}


def setup(root, monkeypatch, chain='G'):
    _, source, zebra, old = prepared(root / 'inputs', monkeypatch)
    run = root / 'real'
    consent = root / 'owner-consent.json'
    write_json(consent, owner_consent())
    checked = v.collect_s0(root / 's0', preparation_file=source, **zebra, root=run,
        snapshot_root=manifest.REPO, selftest=source.parent.parent / 'selftest.json',
        sheet_runtime=old['sheet_runtime'], checks={'passed': True, 'evidence': 'authored_zero_call_fixture'},
        configuration=CHILD, consent_file=consent)
    provenance = root / 'provenance.json'
    write_json(provenance, {**read_json(old['provenance']), 'sha256_list_sha256': checked['snapshot_sha256']})
    options = {**old, 'root': root / ('smoke-' + chain), 's0_file': root / 's0' / v.S0_FILE,
               'provenance': provenance, 'smoke_chain': chain, 'configuration': CHILD}
    made = v.make_manifest(root / ('manifest-' + chain + '.json'), **options)
    return checked, made, options


def first_call(chain, run='a'*64, label='first'):
    return p.record('first-call', 'smoke', {'identity': {'run': run, 'chain': chain,
        **({'route': client.ROUTE_B} if chain == 'D' else {})},
        'passed': True, 'model': p.CHAINS[chain],
        'returned_model': client.NORTHGATE_MODEL if chain == 'D' else p.CHAINS[chain],
        'bench': 'searchqa', 'charged': 100, 'request_sha256': digest({'authored_first': label}),
        'bound': p.ledger_bound(p.CHAINS[chain], 'searchqa', branch='N' if chain == 'D' else None,
                              longest=256 if chain == 'D' else None),
        'max_tokens': p.solver_tokens(p.CHAINS[chain], 'searchqa')})


def probe(chain, run='a'*64, label='first'):
    return v.implant_solver_probe(first_call(chain, run, label), chain,
                                  measured_probe(60000) if chain == 'D' else None)


def receipts(chain, *, m=None):
    m = m or {p.RECORD_HASH: 'a'*64, 'data': {'snapshot_sha256': 'b'*64, 's0_sha256': 'c'*64}}
    found = probe(chain, m[p.RECORD_HASH])
    bounds = v.solver_bounds(chain, found, configuration=CHILD)
    s2 = {**measured_s2(), 'solver_bounds': bounds, 'solver_probe': found}
    outputs = {'S0': {'passed': True, 'model_calls': 0},
        'S1': {'passed': True, 'solver_probe': found, 'solver_bounds': bounds,
               'solver_confirmation': found['first_call'][p.RECORD_HASH]},
        'S2': s2, 'SE6': stages.projection(s2, chain, bounds=bounds, configuration=CHILD)}
    rows = {name: p.record('v214-smoke-stage', 'smoke', {'configuration': CHILD,
        'chain': chain, 'stage': name, 'manifest_sha256': m[p.RECORD_HASH], 'measured': True,
        'schedule_sha256': digest(v.schedule(CHILD)), 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'result': output}) for name, output in outputs.items()}
    return p.record('v214-smoke-result', 'smoke', {'configuration': CHILD, 'chain': chain,
        'manifest_sha256': m[p.RECORD_HASH], 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'schedule_sha256': digest(v.schedule(CHILD)),
        'stages': {name: row[p.RECORD_HASH] for name, row in rows.items()}, 'stage_records': rows,
        'passed': True, 'sealed_reads': 0})


def test_preparation_retains_main_v5_panels_sheet_and_practice_metadata_by_value(tmp_path, monkeypatch):
    _, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    main = v214_preparation.preparation(path, **kwargs)
    child = v214_preparation.preparation(path, **kwargs, configuration=CHILD)
    assert v214_preparation.verify(child) == child
    assert child['registration']['configuration'] == CHILD
    expected = deepcopy(main)
    expected['registration']['configuration'] = CHILD
    assert child == expected
    assert child is not main and child['data']['pinned'] is not main['data']['pinned']


def test_s0_writes_real_root_consent_and_preserves_snapshot_sheet_qualification(tmp_path, monkeypatch):
    checked, made, options = setup(tmp_path, monkeypatch)
    assert checked['configuration'] == made['configuration'] == CHILD
    assert checked['sealed_reads'] == 0 and checked['smoke_schedule']['stages'] == ['S0', 'S1', 'S2', 'SE6']
    assert read_json(tmp_path / 'real/shared/consent.json') == owner_consent()
    assert read_json(options['root'] / 'shared/consent.json') == owner_consent()
    assert checked['consent_sha256'] == digest(owner_consent())
    assert made['sheet_qualification'] == checked['launch_sheet_runtime']['qualification']
    assert made['data']['launch_sheet_runtime'] == checked['launch_sheet_runtime']
    assert made['data']['launch_sheet_runtime']['snapshot_sha256'] == checked['snapshot_sha256']
    assert set(made['cards']) == set(p.MAIN_V5_ORDER)
    assert made['data']['allocations'] == checked['preparation']['allocations']
    assert manifest.check(made) == made


@pytest.mark.parametrize('change', [
    {'sheet_test_qualification': False}, {'test_evaluation': False}, {'by': 'agent'},
    {'multi_arm_arms': ['F', 'C']}, {'multi_arm_arms': ['C', 'F', 'B', 'stages']},
    {'date': ''}, {'note': ''}, {'extra': True},
])
def test_preparation_refuses_nonexact_owner_consent_before_write(tmp_path, change):
    supplied = tmp_path / 'owner.json'
    write_json(supplied, {**owner_consent(), **change})
    with pytest.raises(ValueError, match='consent'):
        v.prepare_consent(tmp_path / 'run', CHILD, consent_file=supplied)
    assert not (tmp_path / 'run/shared/consent.json').exists()


def test_preparation_preserves_preexisting_owner_consent(tmp_path):
    supplied = tmp_path / 'owner.json'
    write_json(supplied, owner_consent())
    target = tmp_path / 'run/shared/consent.json'
    write_json(target, {**owner_consent(), 'note': 'different existing owner record'})
    before = target.read_bytes()
    with pytest.raises(ValueError, match='replace different'):
        v.prepare_consent(tmp_path / 'run', CHILD, consent_file=supplied)
    assert target.read_bytes() == before


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_no_engineer_smoke_sequence_has_all_five_s2_measurements(chain):
    found = receipts(chain)
    checked, projected = v.checked_readiness(found, chain=chain, source_sha256='b'*64,
                                            s0_sha256='c'*64, configuration=CHILD)
    assert checked == found and projected['passed']
    assert set(projected['per_cell']) == set(p.MAIN_V5_ORDER)
    assert projected['method_cost'] == {'model_calls': 0, 'all_role_caps': 0, 'learning': 'none'}
    assert set(projected['solver_scopes']) == {chain + suffix for suffix in (':test', ':solver')}
    assert projected['solver_bounds'] == v.solver_bounds(chain, found['stage_records']['S1']['result']['solver_probe'])
    assert v.stages_of(CHILD) == ('S0', 'S1', 'S2', 'SE6')
    assert v.stages_of() == v.STAGES == ('S0', 'S1', 'S2', 'S3', 'SE6', 'SX')


@pytest.mark.parametrize('chain', ['G', 'D'])
@pytest.mark.parametrize('stage', ['S2', 'SE6'])
def test_same_numeric_bounds_but_different_probe_are_refused(chain, stage):
    found = receipts(chain)
    row = deepcopy(found['stage_records'][stage])
    row['result']['solver_probe'] = probe(chain, label='different confirmed response')
    row = reseal(row)
    found['stage_records'][stage] = row
    found['stages'][stage] = row[p.RECORD_HASH]
    with pytest.raises(ValueError, match='same solver probe'):
        v.checked_readiness(reseal(found), chain=chain, source_sha256='b'*64,
                            s0_sha256='c'*64, configuration=CHILD)


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_s1_calls_no_roles_and_binds_actual_first_response(monkeypatch, chain):
    from skillopt.execskill import chain as chains, v29_route_probe
    calls = []
    monkeypatch.setattr(chains, 'first_call', lambda setting, c: calls.append(('first', c)) or first_call(c))
    monkeypatch.setattr(v29_route_probe, 'measure', lambda setting, **kw:
                        calls.append(('probe', kw['bench'])) or measured_probe(60000))
    monkeypatch.setattr(units, 'role_endpoint', lambda *a, **kw: pytest.fail('No method role'))
    result = stages.s1(SimpleNamespace(extra={'configuration': CHILD}), chain)
    assert calls == [('first', chain)] + ([('probe', 'zebralogic')] if chain == 'D' else [])
    assert result['passed'] and result['solver_probe']['first_call'] == first_call(chain)
    assert v.check_implant_probe(chain, result['solver_probe']) == result['solver_probe']


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_s2_retains_all_76_measured_card_cells_without_method_calls(tmp_path, monkeypatch, chain):
    from skillopt.execskill import rounds, smoke
    pools = {bench: [{'task_id': bench + str(i), 'public': {}, 'private': {}} for i in range(n)]
             for bench, n in v.S2_ITEMS.items()}
    setting = units.Setting('a'*64, tmp_path, tmp_path/'shared', pools, {}, {}, lambda *a: object(),
        Budget(tmp_path/'ledger'), {}, {}, 'engineering_fixture', branch='N' if chain == 'D' else None,
        longest=60000 if chain == 'D' else None, extra={'configuration': CHILD})
    monkeypatch.setattr(stages, 'fixture_pools', lambda *a: pools)
    monkeypatch.setattr(units, 'for_unit', lambda setting, *args: setting)
    monkeypatch.setattr(units, 'drainer', lambda *args: None)
    monkeypatch.setattr(units, 'role_endpoint', lambda *a, **kw: pytest.fail('No method role'))
    configurations, seen = [], []
    def run_unit(root, **kw):
        configurations.append(kw['configuration'])
        return {'result': kw['work'](tmp_path/'attempt')}
    monkeypatch.setattr(units, 'run_unit', run_unit)
    monkeypatch.setattr(budgets, 'endpoint', lambda *a, **kw: object())
    def run(setting, attempt, endpoint, name, arms, schedule, tasks, **kw):
        assert list(arms) == ['C']
        if kw['tag'] == 'first-response':
            assert setting.workers == 1
        bench = name.split('/')[-1]
        rows = {}
        for key, run in schedule['C']:
            seen.append((bench, key, run))
            rows[('C', key)] = [{'final': {'token': 'pass'}, 'stop': None, 'sends': [{'charged': 10}],
                'judge': {'format': {'grid': True}}, 'bench': bench}]
        return rows
    monkeypatch.setattr(rounds, 'run_round', run)
    monkeypatch.setattr(smoke, 'measured_cells', lambda cells: {'actual': len(cells)*10,
        'per_class': {cells[0]['bench']: {'card': {'cells': len(cells), 'tokens': 10*len(cells)}}},
        'request_bytes': {cells[0]['bench']: 100}})
    result = stages.s2(setting, chain)
    assert result['passed'] and result['cells'] == len(seen) == 76
    assert len(set(seen)) == 76 and all(run == 1 for _, _, run in seen)
    assert configurations == [CHILD] * 5
    assert {bench: row['cells'] for bench, row in result['benches'].items()} == v.S2_ITEMS
    assert all(row['arms'] == ['C'] and row['first_response_confirmed']
               and row['measurements']['actual'] > 0 and row['settled_tokens'] > 0
               for row in result['benches'].values())


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_stage_runner_refuses_s3_sx_and_preserves_probe_through_summary(tmp_path, monkeypatch, chain):
    m = {p.RECORD_HASH: 'a'*64, 'root': str(tmp_path), 'configuration': CHILD, 'evidence': 'smoke',
        'data': {'launchable_chains': [chain], 'snapshot_sha256': 'b'*64, 's0_sha256': 'c'*64,
                 'v214_s0': {'passed': True}}}
    setting = units.Setting('a'*64, tmp_path, tmp_path/'shared', {}, {}, {}, None,
        Budget(tmp_path/'ledger'), {}, {}, 'engineering_fixture',
        extra={'configuration': CHILD})
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: m)
    calls = []
    actual = probe(chain)
    monkeypatch.setattr(stages, 's1', lambda *args: calls.append('S1') or {
        'passed': True, 'solver_probe': actual, 'solver_confirmation': actual['first_call'][p.RECORD_HASH],
        'solver_bounds': v.solver_bounds(chain, actual)})
    def s2(st, c):
        assert st.extra['solver_probe'] == actual
        calls.append('S2')
        return measured_s2()
    monkeypatch.setattr(stages, 's2', s2)
    monkeypatch.setattr(stages, 's3', lambda *a: pytest.fail('No engineer smoke'))
    monkeypatch.setattr(stages, 'sx', lambda *a: pytest.fail('No SX smoke'))
    for refused in ('S3', 'SX'):
        with pytest.raises(ValueError, match='registered'):
            v.run_stage(tmp_path/'unread', chain, refused, _setting=setting, configuration=CHILD)
    for name in v.stages_of(CHILD):
        row = v.run_stage(tmp_path/'unread', chain, name, _setting=setting, configuration=CHILD)
        assert row == v.run_stage(tmp_path/'unread', chain, name, _setting=setting, configuration=CHILD)
        if name in ('S1', 'S2', 'SE6'):
            assert row['result']['solver_probe'] == actual
    assert calls == ['S1', 'S2']
    with pytest.raises(ValueError, match='passing measured receipt'):
        v.summarize(tmp_path/'unread', chain, configuration=CHILD)


def test_real_manifest_requires_both_measured_chains_and_same_probe(tmp_path, monkeypatch):
    _, made, options = setup(tmp_path, monkeypatch)
    options.update(smoke_chain=None, root=tmp_path / 'real')
    monkeypatch.setitem(p.RUN_ROOTS, CHILD, str(options['root']))
    with pytest.raises(ValueError, match='both measured'):
        v.make_manifest(tmp_path/'refused.json', **options)
    paths = []
    for chain in ('G', 'D'):
        found = receipts(chain, m=made)
        target = tmp_path / 'measured' / chain
        for name, row in found['stage_records'].items():
            write_json(target / (name + '.json'), row)
        path = target / v.RESULT
        write_json(path, found)
        paths.append(path)
    real = v.make_manifest(tmp_path/'real-manifest.json', measured_smoke=paths, **options)
    assert real['evidence'] == 'implant_v5_test_read'
    assert real['data']['launchable_chains'] == ['G', 'D']
    assert manifest.check(real) == real
    bad = deepcopy(real)
    row = bad['data']['v214_readiness']['D']['stage_records']['SE6']
    row['result']['solver_probe'] = probe('D', made[p.RECORD_HASH], label='other')
    bad['data']['v214_readiness']['D']['stage_records']['SE6'] = reseal(row)
    bad['data']['v214_readiness']['D']['stages']['SE6'] = reseal(row)[p.RECORD_HASH]
    bad['data']['v214_readiness']['D'] = reseal(bad['data']['v214_readiness']['D'])
    with pytest.raises(ValueError, match='same solver probe'):
        manifest.check(reseal(bad))


def test_structural_smoke_is_zero_call_and_uses_true_implant_rows(tmp_path, monkeypatch):
    from skillopt.execskill import v217_implant
    m = {'configuration': CHILD, p.RECORD_HASH: 'a'*64}
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: m)
    monkeypatch.setattr(manifest, 'verify_code', lambda *_: None)
    monkeypatch.setattr(stages, 'sx', lambda *a: pytest.fail('No SX'))
    found = v.structural_smoke(tmp_path/'unread', out=tmp_path/'structural.json', configuration=CHILD)
    assert found['passed'] and not found['measured_readiness']
    assert found['model_calls'] == found['sealed_reads'] == 0
    assert found['stage_demo']['rows'] == {'G': ['C', 'C', 'C', 'S3', 'S3', 'F'],
                                          'D': ['C', 'C', 'C', 'S3', 'S3', 'F']}


@pytest.mark.parametrize('action', ['snapshot', 'selftest', 's0', 'manifest', 'structural-smoke', 'smoke-run', 'smoke-summary'])
def test_every_v214_cli_adds_implant_choice_without_changing_default(action):
    from scripts.run_execskill import parser
    commands = parser()._subparsers._group_actions[0].choices
    choice = next(a for a in commands['v214-' + action]._actions if a.dest == 'configuration')
    assert tuple(choice.choices) == (p.MAIN_V5, CHILD) and choice.default == p.MAIN_V5
    if action == 's0':
        assert any(a.dest == 'consent' for a in commands['v214-s0']._actions)


def test_cli_default_does_not_forward_new_configuration_kwarg(tmp_path, monkeypatch):
    from scripts.run_execskill import parser, v214_command
    calls = []
    monkeypatch.setattr(v, 'snapshot', lambda out, **kw: calls.append(kw) or {'passed': True})
    args = ['v214-snapshot', '--out', str(tmp_path/'out'), '--source', str(tmp_path/'source'), '--git-head', 'a'*40]
    assert v214_command(parser().parse_args(args)) == 0
    assert calls[-1] == {'source': str(tmp_path/'source'), 'git_head': 'a'*40}
    assert v214_command(parser().parse_args(args + ['--configuration', CHILD])) == 0
    assert calls[-1] == {**calls[0], 'configuration': CHILD}
