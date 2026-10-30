"""Imported Zebra read smoke: authored practice data, fake clients and no external execution."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, chain, confirm, manifest, prelaunch, profiles as p, units, v213_import, v29_route_probe
from skillopt.execskill import zebra_smoke as smoke, zebralogic as z
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_manifest import MEASURED, FakeDockerCLI, fake_environment, tree
from tests.test_execskill_v210_snapshot import INSTRUCTION, _collect, _registered_files
from tests.test_execskill_v27_zebra_smoke_review import made
from tests.test_execskill_zpc_adapter import materialize, pool_rows
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CHILD = 'zebra-hp-v3r4'
ROOT = Path(__file__).resolve().parents[1]


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
    value = smoke.make_manifest(path, smoke_chain='D', **options)
    return checked, value, path, options


def measured_s2():
    return {'passed': True, 'items': 10, 'parsed': 10, 'tokens_per_cell': 100, 'settled_tokens': 1000,
        'measurements': {'actual': 1000, 'request_bytes': {z.BENCH: 3000}},
        'solver_bounds': {'branch': 'N', 'longest': 256,
            'ledger_bound': p.ledger_bound(p.CHAINS['D'], z.BENCH, branch='N', longest=256)}}


def smoke_records(root, m, path, checked):
    probe = {'passed': True, 'route': 'B', 'longest': 256}
    projection = smoke.projection(measured_s2(), 'D', CHILD)
    outputs = {'S1': {'passed': True, 'roles': {}, 'solver_probe': probe},
               'S2': measured_s2(), 'SE6': projection}
    for stage, result in outputs.items():
        write_json(root / (stage + '.json'), p.record('zebra-smoke-stage', 'smoke', {
            'configuration': CHILD, 'chain': 'D', 'manifest': m[p.RECORD_HASH], 'stage': stage, 'result': result}))
    value = p.record('zebra-smoke-result', 'smoke', {'configuration': CHILD, 'chain': 'D',
        'manifest': m[p.RECORD_HASH], 'manifest_path': str(path), 's0': checked[p.RECORD_HASH],
        'snapshot_sha256': checked['snapshot_sha256'], 'stages': ['S1', 'S2', 'SE6'],
        'passed': True, 'sealed_reads': 0, 'read_estimate': projection['read_estimate'], 'solver_probe': probe})
    result_path = root / 'result.json'
    write_json(result_path, value)
    return result_path, value


def test_s0_manifest_pins_import_and_fc_without_confirmation(tmp_path, monkeypatch):
    checked, value, _, _ = prepared(tmp_path, monkeypatch)
    assert checked['passed'] and checked['sealed_reads'] == 0 and checked['configuration'] == CHILD
    assert checked['slice_counts'] == {'smoke': 10, 'run': 60, 'accept': 100, 'spare': 3}
    assert value['configuration'] == CHILD and value['evidence'] == 'smoke'
    assert manifest.check(value) == value
    assert value['data']['launchable_chains'] == ['D']
    assert value['cards'] == {z.BENCH: z.CARD_TEXT}
    assert value['clients']['solver']['D']['backend'] == 'northgate'
    assert value['caps'] == budgets.caps(CHILD)
    assert 'confirm' not in value['data']
    assert value['data']['test_read_estimate'] == {'D': 1768000}
    assert value['data']['smoke_results'] == {}
    assert value['data'][v213_import.PIN_KEY] == v213_import.pins()
    assert p.read_arms_of(CHILD) == ('F', 'C')


@pytest.mark.parametrize('damage', ['import', 'confirm'])
def test_manifest_rejects_resealed_import_drift_and_confirmation(tmp_path, monkeypatch, damage):
    _, value, _, _ = prepared(tmp_path, monkeypatch)
    fields = deepcopy({key: entry for key, entry in value.items()
                       if key not in ('version', 'evidence', p.RECORD_HASH)})
    if damage == 'import':
        fields['data'][v213_import.PIN_KEY]['package_record_sha256'] = '0' * 64
    else:
        fields['data']['confirm'] = {'ids': ['authored-unauthorized-confirm']}
    resealed = p.record(manifest.KIND, value['evidence'], fields)
    with pytest.raises(ValueError, match='fixed v3r4 import pins|no confirmation slice'):
        manifest.check(resealed)


def test_setting_threads_import_pins_without_confirmation_or_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(confirm, 'identity', lambda *a, **kw: pytest.fail('No confirmation identity'))
    _, value, path, _ = prepared(tmp_path, monkeypatch)
    value = {**value, 'slot_root': str(tmp_path / 'slots')}
    clients = lambda *a, **kw: pytest.fail('Setting construction cannot create a credentialed client')
    monkeypatch.setattr(manifest, '_clients', lambda *a, **kw: clients)
    setting = manifest.setting_of(value, 'D', path=path, docker=FakeDockerCLI())
    assert setting.extra[v213_import.PIN_KEY] == value['data'][v213_import.PIN_KEY]
    assert setting.extra[v213_import.PIN_KEY] is not value['data'][v213_import.PIN_KEY]
    assert 'confirm' not in setting.extra and setting.extra['route'] == 'B'
    assert len(setting.pools[z.BENCH]) == 200
    assert sum(len(items) for items in z.slices(setting.pools[z.BENCH]).values()) == 173


def test_s1_has_solver_first_call_and_route_probe_without_roles(tmp_path, monkeypatch):
    setting, _, _, _ = made(tmp_path, monkeypatch, response='empty')
    setting = replace(setting, extra={'configuration': CHILD, 'route': 'B'})
    seen = []
    def first(*args):
        seen.append('first')
        return {'passed': True, p.RECORD_HASH: 'a' * 64}
    def probe(*args):
        seen.append('probe')
        return {'passed': True, 'route': 'B', 'longest': 256}
    monkeypatch.setattr(chain, 'first_call', first)
    monkeypatch.setattr(v29_route_probe, 'measure', probe)
    monkeypatch.setattr(units, 'role_endpoint', lambda *a, **kw: pytest.fail('No role endpoint in imported-read S1'))
    result = smoke._s1(setting, 'D')
    assert seen == ['first', 'probe'] and result['passed']
    assert result['roles'] == {} and result['solver_probe']['longest'] == 256


def test_s2_uses_only_solver_scope_and_se6_prices_fc_without_s3(tmp_path, monkeypatch):
    setting, _, fake_solver, _ = made(tmp_path, monkeypatch, response='empty')
    setting = replace(setting, branch='N', longest=256, extra={'configuration': CHILD, 'route': 'B'},
                      budget=Budget(tmp_path / 'v213-ledger', sleep=lambda _: None))
    setting.budget.declare(budgets.chain_caps('D', CHILD))
    monkeypatch.setattr(units, 'drainer', lambda *args: None)
    monkeypatch.setattr(units, 'solver_endpoint', lambda *a, **kw: pytest.fail('No learning solver scope'))
    result = smoke._s2(setting, 'D')
    assert result['passed'] and result['parsed'] == result['items'] == 10
    assert len(fake_solver.requests) == 10
    assert smoke._s2(setting, 'D') == result and len(fake_solver.requests) == 10
    projected = smoke.projection(result, 'D', CHILD)
    assert projected['passed'] and 'roles' not in projected
    assert set(projected['scopes']) == {'D:solver', 'D:test'}
    assert projected['per_cell'][z.BENCH]['procedure_assumed'] is True
    assert smoke._scope_cells('D', CHILD) == {'D:solver': [{z.BENCH: (200, 200)}],
                                            'D:test': [{z.BENCH: (200, 200)}]}
    high = measured_s2()
    high.update(tokens_per_cell=100000, settled_tokens=1000000)
    high['measurements']['actual'] = 1000000
    assert not smoke.projection(high, 'D', CHILD)['passed']


def test_stage_plan_refuses_s3_and_requires_prior_measured_stages(tmp_path, monkeypatch):
    setting, _, _, _ = made(tmp_path, monkeypatch, response='empty')
    setting = replace(setting, extra={'configuration': CHILD, 'route': 'B'},
                      budget=Budget(tmp_path / 'v213-ledger', sleep=lambda _: None))
    m = {'configuration': CHILD, 'evidence': 'smoke', p.RECORD_HASH: 'a' * 64,
         'data': {'s0_sha256': 'b' * 64, 'snapshot_sha256': 'c' * 64}}
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: m)
    monkeypatch.setattr(manifest, 'setting_of', lambda *a, **kw: setting)
    monkeypatch.setattr(manifest, 'services_of', lambda *a, **kw: pytest.fail('No engineer smoke services'))
    monkeypatch.setattr(smoke, '_s3', lambda *a, **kw: pytest.fail('S3 is inapplicable'))
    monkeypatch.setattr(smoke, '_s1', lambda *a, **kw: {'passed': True,
        'solver_probe': {'passed': True, 'route': 'B', 'longest': 256}})
    monkeypatch.setattr(smoke, '_s2', lambda *a, **kw: measured_s2())
    path = tmp_path / 'unread-manifest.json'
    assert smoke.stages_of(CHILD) == ('S1', 'S2', 'SE6')
    assert smoke.stages_of(p.ZEBRA_PC_V13) == smoke.STAGES == ('S1', 'S2', 'S3', 'SE6')
    with pytest.raises(ValueError, match='lean smoke stage'):
        smoke.run_stage(path, 'D', 'S3', configuration=CHILD)
    with pytest.raises((ValueError, FileNotFoundError)):
        smoke.run_stage(path, 'D', 'SE6', configuration=CHILD)
    for stage in smoke.stages_of(CHILD):
        first = smoke.run_stage(path, 'D', stage, configuration=CHILD)
        assert smoke.run_stage(path, 'D', stage, configuration=CHILD) == first
    result = p.verified(read_json(setting.root / 'D/lean-smoke/result.json'), 'zebra-smoke-result')
    assert result['stages'] == ['S1', 'S2', 'SE6'] and result['sealed_reads'] == 0
    assert not (setting.root / 'D/lean-smoke/S3.json').exists()
    with pytest.raises(ValueError, match='launches chain D only'):
        smoke.run_stage(path, 'G', 'S1', configuration=CHILD)


@pytest.mark.parametrize('damage', [None, 'missing_s1', 'failed_s2', 's3_roster', 'wrong_projection'])
def test_real_manifest_needs_three_matching_measured_receipts(tmp_path, monkeypatch, damage):
    checked, m, path, options = prepared(tmp_path, monkeypatch)
    result_path, result = smoke_records(tmp_path / 'measured', m, path, checked)
    monkeypatch.setitem(p.RUN_ROOTS, CHILD, str(tmp_path / 'real'))
    options['root'] = tmp_path / 'real'
    if damage == 'missing_s1':
        result_path.with_name('S1.json').unlink()
    elif damage == 'failed_s2':
        found = read_json(result_path.with_name('S2.json'))
        fields = {key: value for key, value in found.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
        fields['result']['passed'] = False
        result_path.with_name('S2.json').unlink()
        write_json(result_path.with_name('S2.json'), p.record('zebra-smoke-stage', 'smoke', fields))
    elif damage in ('s3_roster', 'wrong_projection'):
        fields = {key: value for key, value in result.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
        if damage == 's3_roster':
            fields['stages'] = list(smoke.STAGES)
        else:
            fields['read_estimate'] += 1
        result_path.unlink()
        write_json(result_path, p.record('zebra-smoke-result', 'smoke', fields))
    out = tmp_path / 'real-manifest.json'
    if damage:
        with pytest.raises((ValueError, FileNotFoundError)):
            smoke.make_manifest(out, smoke_results=[result_path], **options)
        assert not out.exists()
    else:
        value = smoke.make_manifest(out, smoke_results=[result_path], **options)
        assert value['evidence'] == 'zebra_hp_v3r4_test_read'
        assert value['data']['smoke_results']['D']['record_sha256'] == result[p.RECORD_HASH]
        assert value['data']['test_read_estimate'] == {'D': 52000}


def test_v213_snapshot_is_self_contained_and_collects_s0(tmp_path):
    target = tmp_path / 'snapshot'
    value = smoke.snapshot(target, source=ROOT, git_head='a' * 40, configuration=CHILD)
    assert value['env_files_absent']
    assert _registered_files(target) == _registered_files(ROOT)
    assert sorted(path.relative_to(target).as_posix() for path in (target / 'docs').rglob('*') if path.is_file()) == [
        INSTRUCTION.as_posix()]
    assert (target / INSTRUCTION).read_bytes() == (ROOT / INSTRUCTION).read_bytes()
    assert prelaunch.sha256_list(target) == (target / 'sha256-list.txt').read_text()
    assert (target / 'tests/fixtures/execskill/v213_zebra_hp_v3r4_package').is_dir()
    collected = _collect(target)
    assert collected['returncode'] == 0 and collected['tests_collected'] > 0
