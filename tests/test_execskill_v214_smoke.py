"""Offline authored smoke receipts; no model, sandbox service or test-panel reads."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import manifest, profiles as p, v214_smoke as v, v214_stages as stages
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_manifest import reseal
from tests.test_execskill_v214_preparation import prepared
from tests.test_execskill_v210_manifest import consent


def setup(root, monkeypatch, chain='G'):
    _, source, zebra, old = prepared(root / 'inputs', monkeypatch)
    run = root / 'run'
    consent(run, p.MAIN_V5)
    checked = v.collect_s0(root / 's0', preparation_file=source, **zebra, root=run,
        snapshot_root=manifest.REPO, selftest=source.parent.parent / 'selftest.json',
        sheet_runtime=old['sheet_runtime'], checks={'passed': True, 'evidence': 'authored_zero_call_fixture'})
    provenance = root / 'provenance.json'
    write_json(provenance, {**read_json(old['provenance']), 'sha256_list_sha256': checked['snapshot_sha256']})
    options = {**old, 'root': run, 's0_file': root / 's0' / v.S0_FILE, 'provenance': provenance,
               'smoke_chain': chain}
    made = v.make_manifest(root / 'manifest.json', **options)
    return checked, made, options


def measured_s2(tokens=100):
    return {'passed': True, 'benches': {bench: {'passed': True, 'items': n, 'cells': n, 'arms': ['C'],
        'measurements': {'per_class': {bench: {'card': {'cells': n, 'tokens': tokens*n}}},
                         'request_bytes': {bench: 1000}, 'actual': tokens*n},
        'settled_tokens': tokens*n} for bench, n in v.S2_ITEMS.items()}}


def measured_probe(longest):
    """Authored shape of v29_route_probe.measure; never a real provider receipt."""
    from skillopt.execskill import client, v29_route_probe, routes
    rows = [{'passed': True, 'route': 'B', 'returned_model': client.NORTHGATE_MODEL,
        'usage': {'prompt_tokens': 20, 'completion_tokens': n, 'total_tokens': n + 20},
        'finish_reason': 'stop', 'capped_measurement': False,
        'request_sha256': digest({'authored_probe_request': i}), 'tokens': n + 20}
        for i, n in enumerate((min(100, longest), min(200, longest), longest))]
    return {'passed': True, 'route': 'B', 'model': client.NORTHGATE_MODEL, 'branch': 'N',
        'longest': longest, 'calls': 3, 'receipts': rows, 'tokens': sum(row['tokens'] for row in rows),
        'prompt': v29_route_probe.prompt_pins(), 'bench': 'zebralogic', 'provider': 'northgate',
        'max_tokens': p.solver_tokens(p.CHAINS['D'], 'zebralogic'),
        'ledger_bound': p.ledger_bound(p.CHAINS['D'], 'zebralogic', branch='N', longest=longest),
        'request_ceiling': p.ledger_bound(p.CHAINS['D'], 'zebralogic', branch='N', longest=routes.S1B_CEILING),
        'first_response_confirmed': True, 'code_sha256': digest(manifest.pin_code())}


def receipts(chain='D', *, longest=60000, s2_longest=None, m=None):
    m = m or {p.RECORD_HASH: 'a'*64, 'data': {'snapshot_sha256': 'b'*64, 's0_sha256': 'c'*64}}
    probe = measured_probe(longest) if chain == 'D' else None
    bounds = v.solver_bounds(chain, probe)
    later = v.solver_bounds(chain, {'passed': True, 'route': 'B', 'longest': s2_longest}) if s2_longest else bounds
    s2 = {**measured_s2(), 'solver_bounds': later}
    s3 = {'passed': True, 'engineer_calls': 1, 'tokens': 100, 'solver_bounds': bounds}
    outputs = {'S0': {'passed': True},
        'S1': {'passed': True, 'solver_probe': probe, 'solver_bounds': bounds}, 'S2': s2, 'S3': s3,
        'SE6': stages.projection(s2, chain, s3=s3, bounds=bounds),
        'SX': {'passed': True, 'model_calls': 0, 'solver_bounds': bounds}}
    rows = {name: p.record('v214-smoke-stage', 'smoke', {'configuration': p.MAIN_V5,
        'chain': chain, 'stage': name, 'manifest_sha256': m[p.RECORD_HASH], 'measured': True,
        'schedule_sha256': digest(v.schedule()), 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'result': output}) for name, output in outputs.items()}
    return p.record('v214-smoke-result', 'smoke', {'configuration': p.MAIN_V5, 'chain': chain,
        'manifest_sha256': m[p.RECORD_HASH], 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'schedule_sha256': digest(v.schedule()),
        'stages': {name: row[p.RECORD_HASH] for name, row in rows.items()}, 'stage_records': rows,
        'passed': True, 'sealed_reads': 0})


def test_main_v5_s0_manifest_keeps_mixed_allocations_import_and_neutral_zebra(tmp_path, monkeypatch):
    checked, made, _ = setup(tmp_path, monkeypatch)
    assert checked['sealed_reads'] == 0 and checked['smoke_schedule']['S2_arms'] == ['C']
    assert set(made['cards']) == set(p.MAIN_V5_ORDER)
    assert made['data']['confirm']['configuration'] == p.ZEBRA_PC_V13
    assert made['data']['launchable_chains'] == ['G']
    assert 'livemath' not in made['data']['pools']
    assert set(made['data']['allocations']) == {'searchqa', 'officeqa', 'spreadsheetbench'}
    assert manifest.check(made) == made
    assert made['clients']['solver']['G']['B']['zebralogic'] == 65536
    assert made['clients']['solver']['G']['read_timeout']['zebralogic'] == 2400


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_measured_receipts_bind_every_later_stage_to_s1(chain):
    result = receipts(chain)
    found, projected = v.checked_readiness(result, chain=chain, source_sha256='b'*64, s0_sha256='c'*64)
    assert found == result and projected['passed'] and projected['stage_packages'] == 4
    assert set(projected['per_cell']) == set(p.MAIN_V5_ORDER)


@pytest.mark.parametrize('stage', ['S2', 'S3', 'SE6', 'SX'])
def test_resealed_later_solver_bounds_mismatch_is_refused(stage):
    result = receipts('D')
    bad = deepcopy(result['stage_records'][stage])
    bad['result']['solver_bounds'] = v.solver_bounds('D', {'passed': True, 'route': 'B', 'longest': 256})
    bad = reseal(bad)
    result['stage_records'][stage] = bad
    result['stages'][stage] = bad[p.RECORD_HASH]
    with pytest.raises(ValueError, match=stage + ' solver_bounds must equal S1'):
        v.checked_readiness(reseal(result), chain='D', source_sha256='b'*64, s0_sha256='c'*64)


def test_exact_review_mismatch_longest_60000_and_256_fails():
    result = receipts('D', longest=60000, s2_longest=256)
    with pytest.raises(ValueError, match='S2 solver_bounds must equal S1'):
        v.checked_readiness(result, chain='D', source_sha256='b'*64, s0_sha256='c'*64)


def test_se6_prices_four_worst_stage_packages_and_rejects_over_cap():
    bound = v.solver_bounds('G')
    s3 = {'passed': True, 'engineer_calls': 1, 'tokens': 100}
    small = stages.projection(measured_s2(), 'G', s3=s3, bounds=bound)
    expensive = stages.projection(measured_s2(10_000_000), 'G', s3=s3, bounds=bound)
    assert small['passed'] and not expensive['passed']
    assert small['stage_packages'] == 4
    assert small['read_estimate'] > sum(p.MAIN_V5_TEST_ITEMS.values()) * 3 * 100
    assert small['solver_bounds'] == bound
    assert all(row['procedure_assumed'] for row in small['per_cell'].values())


def test_sx_uses_persisted_rows_and_c_f_earlier_stage_sharing(tmp_path):
    result = stages.sx(tmp_path / 'demo')
    assert result['passed'] and result['model_calls'] == result['sealed_reads'] == 0
    assert result['rows'] == ['C', 'C', 'S2', 'S2', 'S4', 'F']
    assert result['sources']['officeqa']['S4']['stage-only'] == 'S2'
    assert set(result['sources']['zebralogic']['S2'].values()) == {'C'}
    assert stages.sx(tmp_path / 'demo') == result


@pytest.mark.parametrize('stage', v.STAGES)
@pytest.mark.parametrize('chain', ['G', 'D'])
def test_new_cli_has_both_chain_lean_stage_choices(stage, chain):
    from scripts.run_execskill import parser
    parsed = parser().parse_args(['v214-smoke-run', '--manifest', '/tmp/unread.json',
                                  '--chain', chain, '--stage', stage])
    assert parsed.stage == stage and parsed.chain == chain


def test_real_manifest_requires_both_readiness_and_checks_resealed_mismatch(tmp_path, monkeypatch):
    checked, made, options = setup(tmp_path, monkeypatch)
    options['smoke_chain'] = None
    monkeypatch.setitem(p.RUN_ROOTS, p.MAIN_V5, str(options['root']))
    with pytest.raises(ValueError, match='both measured'):
        v.make_manifest(tmp_path / 'refused.json', **options)
    paths = []
    for chain in ('G', 'D'):
        result = receipts(chain, m=made, s2_longest=256 if chain == 'D' else None)
        root = tmp_path / 'measured' / chain
        for name, row in result['stage_records'].items():
            write_json(root / (name + '.json'), row)
        path = root / v.RESULT
        write_json(path, result)
        paths.append(path)
    with pytest.raises(ValueError, match='S2 solver_bounds must equal S1'):
        v.make_manifest(tmp_path / 'refused.json', measured_smoke=paths, **options)
    assert not (tmp_path / 'refused.json').exists()


def test_manifest_check_rechecks_embedded_bounds_without_reloading_receipt(tmp_path, monkeypatch):
    _, made, _ = setup(tmp_path, monkeypatch)
    fields = deepcopy(made)
    fields['evidence'] = p.REAL_RUN_EVIDENCE[p.MAIN_V5]
    fields['data']['launchable_chains'] = ['G', 'D']
    fields['data']['v214_readiness'] = {chain: receipts(chain, m=made,
        s2_longest=256 if chain == 'D' else None) for chain in ('G', 'D')}
    for chain, result in fields['data']['v214_readiness'].items():
        se6 = result['stage_records']['SE6']['result']
        fields['data']['test_read_terms'][chain] = se6['read_terms']
        fields['data']['test_read_estimate'][chain] = se6['read_estimate']
        bounds = result['stage_records']['S1']['result']['solver_bounds']
        fields['clients']['solver'][chain].update(branch=bounds['branch'], longest=bounds['longest'], B=bounds['ledger_bound'])
    from skillopt.execskill import routes
    fields['clients']['routes']['D']['B'] = routes.pin('D', 'B', env_path=fields['clients']['solver']['D']['env_path'],
        solver_block=fields['clients']['solver']['D'], configuration=p.MAIN_V5)
    with pytest.raises(ValueError, match='S2 solver_bounds must equal S1'):
        manifest.check(reseal(fields))


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_s1_confirms_route_then_only_d_runs_inherited_zebra_probe(monkeypatch, chain):
    from skillopt.execskill import chain as chain_module, v29_route_probe
    seen = []
    monkeypatch.setattr(chain_module, 'first_call', lambda setting, c: seen.append(('first', c)) or
                        {'passed': True, p.RECORD_HASH: 'a'*64})
    def probe(setting, *, bench):
        seen.append(('probe', bench))
        return {'passed': True, 'route': 'B', 'longest': 60000, 'calls': 3}
    monkeypatch.setattr(v29_route_probe, 'measure', probe)
    value = stages.s1(object(), chain)
    assert value['passed'] and seen[0] == ('first', chain)
    assert seen[1:] == ([('probe', 'zebralogic')] if chain == 'D' else [])
    assert value['solver_bounds']['longest'] == (60000 if chain == 'D' else None)


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_s2_sends_exactly_76_card_only_cells_on_both_chains(tmp_path, monkeypatch, chain):
    from skillopt.execskill import rounds, units, budgets, smoke
    from skillopt.coevo5.budget import Budget
    pools = {bench: [{'task_id': bench + str(i), 'public': {}, 'private': {}} for i in range(n)]
             for bench, n in v.S2_ITEMS.items()}
    setting = units.Setting('a'*64, tmp_path, tmp_path/'shared', pools, {}, {}, lambda *a: object(),
        Budget(tmp_path/'ledger'), {}, {}, 'engineering_fixture', branch='N' if chain == 'D' else None,
        longest=60000 if chain == 'D' else None, extra={'configuration': p.MAIN_V5})
    monkeypatch.setattr(stages, 'fixture_pools', lambda *a: pools)
    monkeypatch.setattr(units, 'for_unit', lambda setting, *args: setting)
    monkeypatch.setattr(units, 'drainer', lambda *args: None)
    monkeypatch.setattr(units, 'run_unit', lambda root, **kw: {'result': kw['work'](tmp_path/'attempt')})
    monkeypatch.setattr(budgets, 'endpoint', lambda *a, **k: object())
    seen = []
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
    value = stages.s2(setting, chain)
    assert value['passed'] and value['cells'] == len(seen) == 76
    assert len(set(seen)) == 76 and all(run == 1 for _, _, run in seen)
    assert 'livemath' not in value['benches']


@pytest.mark.parametrize('kind,passed', [('fenced', True), ('inline', True), ('bogus', False),
                                          ('empty', True), ('missing', False)])
def test_s3_makes_one_engineer_call_without_repair_or_other_roles(tmp_path, monkeypatch, kind, passed):
    from skillopt.execskill import units, zebra_smoke
    calls = []
    import json
    replies = {'fenced': zebra_smoke.authored_reply(),
        'inline': json.dumps({'changes': [{'kind': 'new', 'source': 'def before_call(view, state):\n    return {}\n'}]}),
        'bogus': json.dumps({'changes': [{'kind': 'not-a-change'}]}),
        'empty': '{"changes": []}', 'missing': '{}'}
    class Endpoint:
        def recorder(self, **kwargs):
            return SimpleNamespace(sends=[])
        def send(self, system, user, recorder):
            calls.append((system, user))
            recorder.sends.append({'charged': 100, 'request_bytes': 1000})
            return {'ok': True, 'response': replies[kind]}
    monkeypatch.setattr(units, 'role_endpoint', lambda setting, chain, role, bench, k:
                        Endpoint() if role == 'engineer' else pytest.fail('Extra role'))
    monkeypatch.setattr(units, '_bounded_endpoint', lambda endpoint, bound: endpoint)
    monkeypatch.setattr(units, 'drainer', lambda *args: None)
    monkeypatch.setattr(units, 'run_unit', lambda root, **kw: {'result': kw['work'](tmp_path/'attempt')})
    setting = SimpleNamespace(root=tmp_path, run='a'*64, evidence='engineering_fixture')
    value = stages.s3(setting, 'G')
    assert value['passed'] is passed and value['engineer_calls'] == len(calls) == 1
    assert value['no_change'] is (kind == 'empty')
    assert value['transport_sends'] == 1 and value['benchmark_effect_evidence'] is False


def test_stage_runner_is_ordered_resumable_and_fixture_receipts_cannot_be_readiness(tmp_path, monkeypatch):
    from skillopt.execskill import units
    from skillopt.coevo5.budget import Budget
    m = {p.RECORD_HASH: 'a'*64, 'root': str(tmp_path), 'configuration': p.MAIN_V5, 'evidence': 'smoke',
        'data': {'launchable_chains': ['D'], 'snapshot_sha256': 'b'*64, 's0_sha256': 'c'*64,
                 'v214_s0': {'passed': True}}}
    setting = units.Setting('a'*64, tmp_path, tmp_path/'shared', {}, {}, {}, None,
        Budget(tmp_path/'ledger'), {}, {}, 'engineering_fixture', branch='N', longest=60000,
        extra={'configuration': p.MAIN_V5})
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: m)
    calls = []
    monkeypatch.setattr(stages, 's1', lambda *args: calls.append('S1') or {
        'passed': True, 'solver_probe': {'passed': True, 'route': 'B', 'longest': 60000},
        'solver_bounds': v.solver_bounds('D', {'passed': True, 'route': 'B', 'longest': 60000})})
    monkeypatch.setattr(stages, 's2', lambda setting, chain: calls.append('S2') or measured_s2())
    monkeypatch.setattr(stages, 's3', lambda setting, chain: calls.append('S3') or {
        'passed': True, 'engineer_calls': 1, 'tokens': 100})
    with pytest.raises((ValueError, FileNotFoundError)):
        v.run_stage(tmp_path/'unread', 'D', 'S2', _setting=setting)
    for name in v.STAGES:
        first = v.run_stage(tmp_path/'unread', 'D', name, _setting=setting)
        assert first == v.run_stage(tmp_path/'unread', 'D', name, _setting=setting)
        assert first['evidence'] == 'engineering_fixture' and first['measured'] is False
    assert calls == ['S1', 'S2', 'S3']
    with pytest.raises(ValueError, match='passing measured receipt'):
        v.summarize(tmp_path/'unread', 'D')


def test_real_manifest_accepts_both_consistent_measured_receipts(tmp_path, monkeypatch):
    _, made, options = setup(tmp_path, monkeypatch)
    options['smoke_chain'] = None
    monkeypatch.setitem(p.RUN_ROOTS, p.MAIN_V5, str(options['root']))
    paths = []
    for chain in ('G', 'D'):
        result = receipts(chain, m=made)
        root = tmp_path / 'measured' / chain
        for name, row in result['stage_records'].items():
            write_json(root / (name + '.json'), row)
        path = root / v.RESULT
        write_json(path, result)
        paths.append(path)
    real = v.make_manifest(tmp_path / 'real.json', measured_smoke=paths, **options)
    assert real['evidence'] == 'main_v5_real_run'
    assert real['data']['launchable_chains'] == ['G', 'D']
    assert real['clients']['solver']['D']['longest'] == 60000
    assert real['data']['v214_readiness']['D']['stage_records']['S2']['result']['solver_bounds']['longest'] == 60000
    from skillopt.execskill import zebralogic as z
    assert real['importable_versions'] == [*p.IMPORTABLE, p.TEXTS_IMPORT, z.CARD_VERSION]
    assert manifest.check(real) == real


@pytest.mark.parametrize('damage', ['longest', 'receipt_count', 'prompt', 'model', 'ledger_bound', 'source'])
def test_s1_probe_provenance_and_longest_are_recomputed_before_readiness(damage):
    result = receipts('D', longest=60000)
    s1 = deepcopy(result['stage_records']['S1'])
    probe = s1['result']['solver_probe']
    if damage == 'longest':
        # Reseal every stated bound consistently; the actual receipt maximum is still 60000.
        probe['longest'] = 256
        probe['ledger_bound'] = p.ledger_bound(p.CHAINS['D'], 'zebralogic', branch='N', longest=256)
        s1['result']['solver_bounds'] = v.solver_bounds('D', probe)
    elif damage == 'receipt_count':
        probe['receipts'].pop()
    elif damage == 'prompt':
        probe['prompt']['user'] += 'changed'
    elif damage == 'model':
        probe['receipts'][0]['returned_model'] = 'wrong-model'
    elif damage == 'ledger_bound':
        probe['ledger_bound'] += 1
    else:
        probe['code_sha256'] = '0'*64
    changed = reseal(s1)
    result['stage_records']['S1'] = changed
    result['stages']['S1'] = changed[p.RECORD_HASH]
    with pytest.raises(ValueError, match='S1'):
        v.checked_readiness(reseal(result), chain='D', source_sha256='b'*64, s0_sha256='c'*64)
