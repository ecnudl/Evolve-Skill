"""G-only imported-read smoke using authored puzzles and offline transports."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, chain, confirm, manifest, prelaunch, profiles as p, units
from skillopt.execskill import v217_import, v29_route_probe, zebra_smoke as smoke, zebralogic as z
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_fakes import FakeSolver
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_manifest import MEASURED, FakeDockerCLI, fake_environment, tree
from tests.test_execskill_v210_snapshot import INSTRUCTION, _registered_files
from tests.test_execskill_v27_zebra_smoke_review import made
from tests.test_execskill_zpc_adapter import materialize, pool_rows
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CHILD = 'zebra-hp-g3r2'
ROOT = Path(__file__).resolve().parents[1]


def probe(run='a' * 64, request='b' * 64):
    return smoke.g3r2_solver_probe(p.record('first-call', 'smoke', {
        'identity': {'chain': 'G', 'run': run}, 'passed': True,
        'model': p.CHAINS['G'], 'returned_model': p.CHAINS['G'], 'bench': z.BENCH,
        'max_tokens': p.solver_tokens(p.CHAINS['G'], z.BENCH),
        'bound': p.ledger_bound(p.CHAINS['G'], z.BENCH), 'charged': 15,
        'request_sha256': request}))


def prepared(root, monkeypatch):
    source = tree(root / 'source')
    monkeypatch.setattr(manifest, 'REPO', source)
    pool = root / 'authored-pool.json'
    sha = materialize(pool, pool_rows())
    original = z.load_pool
    monkeypatch.setattr(z, 'POOL_SHA256', sha)
    monkeypatch.setattr(z, 'load_pool', lambda path, **kwargs: original(path, expected_sha256=sha))
    split = root / 'split-manifest.json'
    write_json(split, {'output_sha256': {'zebralogic/pool.json': sha,
                                      'zebralogic/sealed-holdout.json': z.SEALED_SHA256}})
    selftest = root / 'selftest.json'
    write_json(selftest, p.record('sandbox-selftest', 'smoke', {'passed': True,
        'measured': dict(MEASURED), 'limits': {key: asdict(value) for key, value in sandbox.LIMITS.items()}}))
    monkeypatch.setattr(z, 'test_panel', lambda *a, **kw: pytest.fail('Preparation cannot open a panel'))
    checked = smoke.collect_s0(root / 's0', pool=pool, split_manifest=split, snapshot_root=source,
        selftest=selftest, checks={'passed': True, 'evidence': 'authored_zero_call_checks'}, configuration=CHILD)
    provenance = root / 'provenance.json'
    write_json(provenance, {'build_tree': str(source), 'git_head': 'f' * 40, 'snapshot_root': str(source),
        'sha256_list_sha256': checked['snapshot_sha256'], 'env_files_absent': True})
    options = dict(root=root / 'smoke', s0_file=root / 's0' / smoke.S0_FILE, provenance=provenance,
        roles_repo=root / 'unread-roles', elucid_env=root / 'unread-elucid.env', route_b_env=root / 'unread-route.env',
        configuration=CHILD, environment_found=fake_environment())
    path = root / 'smoke-manifest.json'
    value = smoke.make_manifest(path, smoke_chain='G', **options)
    return checked, value, path, options


def measured_s2(found=None, tokens=100):
    found = found or probe()
    return {'passed': True, 'items': 10, 'parsed': 10, 'tokens_per_cell': tokens,
        'settled_tokens': 10 * tokens, 'measurements': {'actual': 10 * tokens,
            'request_bytes': {z.BENCH: 3000}}, 'solver_probe': found,
        'solver_bounds': found['solver_bounds']}


def smoke_records(root, m, path, checked, *, damage=None):
    found = probe(m[p.RECORD_HASH])
    s2 = measured_s2(found)
    if damage == 'different_s2_probe':
        s2['solver_probe'] = probe(m[p.RECORD_HASH], 'c' * 64)
    projection = smoke.projection(s2, 'G', CHILD)
    outputs = {'S1': {'passed': True, 'roles': {}, 'solver_probe': found,
                     'solver_confirmation': found['first_call'][p.RECORD_HASH]},
               'S2': s2, 'SE6': projection}
    if damage == 'different_se6_probe':
        outputs['SE6']['solver_probe'] = probe(m[p.RECORD_HASH], 'd' * 64)
    elif damage == 'failed_s2':
        outputs['S2']['passed'] = False
    elif damage == 'different_bound':
        outputs['S2']['solver_bounds'] = {**found['solver_bounds'], 'ledger_bound': 1}
    elif damage == 'wrong_projection':
        outputs['SE6']['read_estimate'] += 1
    for stage, result in outputs.items():
        if damage == 'missing_s1' and stage == 'S1':
            continue
        write_json(root / (stage + '.json'), p.record('zebra-smoke-stage', 'smoke', {
            'configuration': CHILD, 'chain': 'G', 'manifest': m[p.RECORD_HASH], 'stage': stage, 'result': result}))
    value = p.record('zebra-smoke-result', 'smoke', {'configuration': CHILD, 'chain': 'G',
        'manifest': m[p.RECORD_HASH], 'manifest_path': str(path), 's0': checked[p.RECORD_HASH],
        'snapshot_sha256': checked['snapshot_sha256'],
        'stages': list(smoke.STAGES) if damage == 's3_roster' else ['S1', 'S2', 'SE6'],
        'passed': True, 'sealed_reads': 0, 'read_estimate': projection['read_estimate'],
        'solver_probe': probe(m[p.RECORD_HASH], 'e' * 64) if damage == 'different_result_probe' else found})
    result_path = root / 'result.json'
    write_json(result_path, value)
    return result_path, value


def g_setting(tmp_path, monkeypatch):
    setting, _, old_solver, _ = made(tmp_path, monkeypatch, response='empty')
    client = FakeSolver(tmp_path / 'g-solver', old_solver.rules, model=p.CHAINS['G'])
    def clients(model, bench):
        assert model == p.CHAINS['G'] and bench == z.BENCH
        return client.client
    ledger = Budget(budgets.ledger_root(setting.root, 'G'), sleep=lambda _: None)
    ledger.declare({**budgets.chain_caps('G', CHILD), **budgets.first_call_caps('G')})
    setting = replace(setting, branch=None, longest=None, clients=clients, budget=ledger,
                      extra={'configuration': CHILD})
    return setting, client


def test_s0_manifest_pins_import_and_g_route_without_confirmation(tmp_path, monkeypatch):
    checked, value, path, _ = prepared(tmp_path, monkeypatch)
    assert checked['passed'] and checked['sealed_reads'] == 0 and checked['configuration'] == CHILD
    assert checked['slice_counts'] == {'smoke': 10, 'run': 60, 'accept': 100, 'spare': 3}
    assert manifest.check(value) == value
    assert value['data']['launchable_chains'] == ['G']
    assert value['cards'] == {z.BENCH: z.CARD_TEXT}
    solver = value['clients']['solver']['G']
    expected = manifest.solver_block('G', env_path=tmp_path / 'unread-roles', configuration=p.MAIN_V5)
    for key in solver:
        assert solver[key] == ({z.BENCH: expected[key][z.BENCH]} if key in ('M', 'B', 'read_timeout') else expected[key])
    assert solver['backend'] == 'bigmodel' and solver['model'] == p.CHAINS['G']
    assert value['caps'] == budgets.caps(CHILD) and 'confirm' not in value['data']
    assert value['data']['smoke_results'] == {} and value['data'][v217_import.PIN_KEY] == v217_import.pins()
    monkeypatch.setattr(confirm, 'identity', lambda *a, **kw: pytest.fail('No confirmation identity'))
    monkeypatch.setattr(manifest, '_clients', lambda *a, **kw: pytest.fail('No client construction'))
    with pytest.raises(ValueError):
        manifest.setting_of(value, 'D', path=path, docker=FakeDockerCLI())


def test_s1_is_one_actual_g_response_with_no_roles_or_northgate_probe(tmp_path, monkeypatch):
    setting, client = g_setting(tmp_path, monkeypatch)
    monkeypatch.setattr(v29_route_probe, 'measure', lambda *a, **kw: pytest.fail('No northgate requests'))
    monkeypatch.setattr(units, 'role_endpoint', lambda *a, **kw: pytest.fail('No role endpoint'))
    with pytest.raises(ValueError, match='chain G only'):
        smoke._s1(setting, 'D')
    assert not client.requests
    result = smoke._s1(setting, 'G')
    assert result['passed'] and result['roles'] == {} and len(client.requests) == 1
    found = smoke.check_g3r2_probe(result['solver_probe'])
    assert found['first_call']['request_sha256'] and found['first_call']['charged'] > 0
    assert found['solver_bounds'] == {'branch': None, 'longest': None, 'ledger_bound': 65536}
    assert result['solver_confirmation'] == found['first_call'][p.RECORD_HASH]
    assert smoke._s1(setting, 'G') == result and len(client.requests) == 1


def test_s2_uses_existing_g_solver_scope_and_se6_projects_fc(tmp_path, monkeypatch):
    setting, client = g_setting(tmp_path, monkeypatch)
    first = smoke._s1(setting, 'G')
    setting = replace(setting, extra={**setting.extra, 'solver_probe': first['solver_probe']})
    monkeypatch.setattr(units, 'drainer', lambda *a: None)
    monkeypatch.setattr(units, 'solver_endpoint', lambda *a, **kw: pytest.fail('No learning scope'))
    measured = smoke._s2(setting, 'G')
    assert measured['passed'] and measured['items'] == measured['parsed'] == 10
    assert len(client.requests) == 11
    assert measured['solver_probe'] == first['solver_probe']
    assert smoke._s2(setting, 'G') == measured and len(client.requests) == 11
    projected = smoke.projection(measured, 'G', CHILD)
    assert projected['passed'] and projected['solver_probe'] == first['solver_probe']
    assert set(projected['scopes']) == {'G:solver', 'G:test'} and 'roles' not in projected
    assert projected['read_start']['passed'] and projected['read_start']['factor'] == '13/10'
    assert smoke._scope_cells('G', CHILD) == {'G:solver': [{z.BENCH: (200, 200)}],
                                            'G:test': [{z.BENCH: (200, 200)}]}


def test_se6_checks_read_start_headroom_in_addition_to_reservation_fit():
    # The ordinary measured projection fits, but 1.3 times its read estimate does not.
    measured = measured_s2(tokens=55000)
    projected = smoke.projection(measured, 'G', CHILD)
    assert all(row['passed'] for row in projected['scopes'].values())
    assert not projected['read_start']['passed'] and not projected['passed']
    with pytest.raises(ValueError, match='chain G only'):
        smoke.projection(measured, 'D', CHILD)


def test_stage_plan_refuses_s3_and_binds_s1_through_se6(tmp_path, monkeypatch):
    setting, _ = g_setting(tmp_path, monkeypatch)
    m = {'configuration': CHILD, 'evidence': 'smoke', p.RECORD_HASH: 'a' * 64,
         'data': {'s0_sha256': 'b' * 64, 'snapshot_sha256': 'c' * 64}}
    found = probe(m[p.RECORD_HASH])
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: m)
    monkeypatch.setattr(manifest, 'setting_of', lambda *a, **kw: setting)
    monkeypatch.setattr(manifest, 'services_of', lambda *a, **kw: pytest.fail('No engineer smoke services'))
    monkeypatch.setattr(smoke, '_s3', lambda *a, **kw: pytest.fail('S3 is inapplicable'))
    monkeypatch.setattr(smoke, '_s1', lambda *a, **kw: {'passed': True, 'solver_probe': found,
        'solver_confirmation': found['first_call'][p.RECORD_HASH]})
    def s2(st, chain_id):
        assert chain_id == 'G' and st.branch is st.longest is None and st.extra['solver_probe'] == found
        return measured_s2(st.extra['solver_probe'])
    monkeypatch.setattr(smoke, '_s2', s2)
    path = tmp_path / 'unread-manifest.json'
    assert smoke.stages_of(CHILD) == ('S1', 'S2', 'SE6')
    with pytest.raises(ValueError, match='lean smoke stage'):
        smoke.run_stage(path, 'G', 'S3', configuration=CHILD)
    with pytest.raises(ValueError, match='chain G only'):
        smoke.run_stage(path, 'D', 'S1', configuration=CHILD)
    with pytest.raises((ValueError, FileNotFoundError)):
        smoke.run_stage(path, 'G', 'SE6', configuration=CHILD)
    stages = {}
    for stage in smoke.stages_of(CHILD):
        first = smoke.run_stage(path, 'G', stage, configuration=CHILD)
        assert smoke.run_stage(path, 'G', stage, configuration=CHILD) == first
        stages[stage] = first['result']
    smoke.check_g3r2_stages(stages, found)
    result = p.verified(read_json(setting.root / 'G/lean-smoke/result.json'), 'zebra-smoke-result')
    assert result['stages'] == ['S1', 'S2', 'SE6'] and result['sealed_reads'] == 0
    assert result['solver_probe'] == found and not (setting.root / 'G/lean-smoke/S3.json').exists()


@pytest.mark.parametrize('damage', [None, 'missing_s1', 'failed_s2', 's3_roster', 'wrong_projection',
    'different_s2_probe', 'different_se6_probe', 'different_result_probe', 'different_bound'])
def test_real_manifest_requires_all_three_stages_on_same_actual_probe(tmp_path, monkeypatch, damage):
    checked, m, path, options = prepared(tmp_path, monkeypatch)
    result_path, result = smoke_records(tmp_path / 'measured', m, path, checked, damage=damage)
    monkeypatch.setitem(p.RUN_ROOTS, CHILD, str(tmp_path / 'real'))
    options['root'] = tmp_path / 'real'
    out = tmp_path / 'real-manifest.json'
    if damage:
        with pytest.raises((ValueError, FileNotFoundError)):
            smoke.make_manifest(out, smoke_results=[result_path], **options)
        assert not out.exists()
    else:
        value = smoke.make_manifest(out, smoke_results=[result_path], **options)
        assert value['evidence'] == 'zebra_hp_g3r2_test_read'
        assert value['data']['smoke_results']['G']['record_sha256'] == result[p.RECORD_HASH]
        assert value['data']['test_read_estimate'] == {'G': 52000}


@pytest.mark.parametrize('damage', ['missing_receipt', 'different_solver', 'estimate', 'probe'])
def test_direct_manifest_check_refuses_resealed_readiness_drift(tmp_path, monkeypatch, damage):
    checked, m, path, options = prepared(tmp_path, monkeypatch)
    result_path, _ = smoke_records(tmp_path / 'measured', m, path, checked)
    monkeypatch.setitem(p.RUN_ROOTS, CHILD, str(tmp_path / 'real'))
    options['root'] = tmp_path / 'real'
    value = smoke.make_manifest(tmp_path / 'real-manifest.json', smoke_results=[result_path], **options)
    fields = deepcopy({key: entry for key, entry in value.items()
                       if key not in ('version', 'evidence', p.RECORD_HASH)})
    if damage == 'missing_receipt':
        fields['data']['smoke_results'] = {}
    elif damage == 'different_solver':
        fields['clients']['solver']['G']['env_path'] = str(tmp_path / 'different-unread-roles')
    elif damage == 'estimate':
        fields['data']['test_read_estimate']['G'] += 1
    else:
        s2path = result_path.with_name('S2.json')
        s2 = read_json(s2path)
        changed = {key: entry for key, entry in s2.items()
                   if key not in ('version', 'evidence', p.RECORD_HASH)}
        changed['result']['solver_probe'] = probe(m[p.RECORD_HASH], 'c' * 64)
        s2path.unlink()
        write_json(s2path, p.record('zebra-smoke-stage', 'smoke', changed))
    with pytest.raises(ValueError):
        manifest.check(p.record(manifest.KIND, value['evidence'], fields))


@pytest.mark.parametrize('field', ['model', 'returned_model', 'bound', 'charged', 'bench', 'passed'])
def test_probe_refuses_unconfirmed_or_wrong_solver_response(field):
    first = deepcopy(probe()['first_call'])
    first[field] = False if field == 'passed' else 0 if field in ('bound', 'charged') else 'wrong'
    fields = {key: value for key, value in first.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    with pytest.raises(ValueError):
        smoke.g3r2_solver_probe(p.record('first-call', 'smoke', fields))


def test_snapshot_contains_new_import_fixture_and_public_instruction_fixture(tmp_path):
    target = tmp_path / 'snapshot'
    value = smoke.snapshot(target, source=ROOT, git_head='a' * 40, configuration=CHILD)
    assert value['env_files_absent'] and _registered_files(target) == _registered_files(ROOT)
    assert (target / INSTRUCTION).read_bytes() == (ROOT / INSTRUCTION).read_bytes()
    assert prelaunch.sha256_list(target) == (target / 'sha256-list.txt').read_text()
    assert (target / 'tests/fixtures/execskill/v217_zebra_hp_g3r2_package').is_dir()
