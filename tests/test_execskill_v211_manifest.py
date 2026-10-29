"""Child manifest preparation, exact supply identity and fail-closed readiness; no services."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (alfworld_format, engineer_v211, exclusion, manifest, prelaunch,
                               profiles as p, routes, step, supply, v210_import, v211_smoke as v)
from skillopt.execskill.sandbox import client as sandbox
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_manifest import MEASURED, fake_environment
from tests.test_execskill_v210_manifest import consent, preparation as parent_preparation
from tests.test_execskill_v211_allocation import pool, tail
from tests.execskill_sheet_runtime_fakes import make_runtime

ROOT = Path(__file__).resolve().parents[1]


def reseal(value):
    return p.record(value['version'].removeprefix(p.VERSION + '-'), value['evidence'],
                    {k: v for k, v in value.items() if k not in ('version', 'evidence', p.RECORD_HASH)})


def prepared(root, monkeypatch, *, tail_count=1240):
    path, source, records = parent_preparation(root / 'source', monkeypatch)
    from skillopt.coevo5 import data
    from skillopt.coevolution_v5.core import seal
    pinned = source['data']['pinned']
    parts = {bench: {part: [{'task_id': bench + '-' + part, 'family_id': bench + '-' + part}]
                        for part in ('train', 'val', 'test', 'reserve')}
             for bench in p.BENCHES}
    split = Path(pinned['paths']['split'])
    write_json(split, seal({'version': data.SPLIT_VERSION,
        'splits': {bench: parts[bench] for bench in p.BENCHES if bench not in data.EXTENSIONS}, 'sources': {}}))
    pinned['sha256'][str(split)] = v._sha(split)
    for bench in data.EXTENSIONS:
        layout = Path(pinned['paths']['layouts'][bench])
        write_json(layout, seal({'version': data.LAYOUT_VERSION, 'benchmark': bench, 'parts': parts[bench],
            'evaluation_blocks': {'items': [bench + '-closed-evaluation']}}))
        pinned['sha256'][str(layout)] = v._sha(layout)
    alf = root / 'source/alfworld-pool.json'
    write_json(alf, [{'benchmark': 'alfworld', 'task_id': 'alfworld-train', 'part': 'fresh',
                      'room': 'authored-room', 'public': {}, 'private': {}}])
    source['data']['pools']['alfworld'] = {'path': str(alf), 'sha256': v._sha(alf)}
    rows = tail(tail_count)['tail']
    for bench in p.BENCHES[:-1]:
        target = root / 'source' / (bench + '-pool.json')
        write_json(target, pool(bench))
        source['data']['pools'][bench] = {'path': str(target), 'sha256': v._sha(target)}
    target = root / 'source/tail.json'
    write_json(target, p.record(supply.RECORD_KIND, 'engineering_fixture',
                              {'name': 'searchqa-tail', 'bench': 'searchqa', 'items': rows}))
    source['data']['searchqa_tail'] = {'path': str(target), 'sha256': v._sha(target)}
    records[exclusion.SEARCHQA_RUN] = p.record(exclusion.RECORD_KIND, 'engineering_fixture', {
        'run': exclusion.SEARCHQA_RUN, 'dropped': [], 'exclusion_sha256': digest([]),
        'consent_sha256': 'a' * 64, 'supply_sha256': digest(sorted(i['task_id'] for i in rows)),
        'counts': {'supply': len(rows), 'kept': len(rows)}})
    for name, record in records.items():
        target = root / 'source' / (p.CANARIES if name == 'test_canaries' else p.EXCLUSION_DIR + '/' + name + '.json')
        write_json(target, record)
        source['data']['exclusion'][name] = {'path': str(target), 'record_sha256': record[p.RECORD_HASH]}
    path = root / 'source/child-preparation.json'
    write_json(path, reseal(source))
    return path, source


def setup(root, monkeypatch):
    source, before = prepared(root, monkeypatch)
    run = root / 'run'
    consent(run, p.MAIN_V4)
    selftest = root / 'selftest.json'
    write_json(selftest, p.record('sandbox-selftest', 'smoke', {'passed': True, 'measured': MEASURED,
        'limits': {k: asdict(l) for k, l in sandbox.LIMITS.items()}}))
    runtime_file = make_runtime(root / 'launch-sheet', monkeypatch)
    checked = v.collect_s0(root / 's0', preparation_file=source, root=run, snapshot_root=ROOT,
        selftest=selftest, sheet_runtime=runtime_file,
        checks={'passed': True, 'summary': 'authored injected zero-call receipt'})
    provenance = root / 'provenance.json'
    write_json(provenance, {'build_tree': str(ROOT), 'git_head': 'f' * 40, 'snapshot_root': str(ROOT),
        'sha256_list_sha256': checked['snapshot_sha256'], 'env_files_absent': True})
    options = {'root': run, 's0_file': root / 's0' / v.S0_FILE, 'provenance': provenance,
        'roles_repo': root / 'roles', 'route_b_env': root / 'route.env', 'smoke_chain': 'G',
        'sheet_runtime': runtime_file, 'environment_found': fake_environment()}
    return checked, options, before


def test_child_s0_and_manifest_pin_four_allocations_five_runtimes_and_both_auditors(tmp_path, monkeypatch):
    checked, options, old = setup(tmp_path, monkeypatch)
    made = v.make_manifest(tmp_path / 'manifest.json', **options)
    assert made['configuration'] == p.MAIN_V4 and made['data']['launchable_chains'] == ['G']
    assert checked['historical_fingerprints']['count'] == 32 and checked['sealed_reads'] == 0
    assert made['data']['allocations'] == checked['allocations']
    assert made['data']['protected_ids'] == checked['protected_ids']
    assert all(row['count'] > 0 and row['item_text_reads'] == 0 for row in checked['protected_ids'].values())
    assert made['data']['freshness_amendment'] == v.AMENDMENT
    assert made['data']['v211_prompt_pins'] == engineer_v211.pins()
    assert made['data']['alfworld_v11_import'] == v210_import.pins()
    assert 'confirm' not in made['data']
    assert made['cards'] == old['cards']
    assert alfworld_format.validate(made['runtime']['alfworld'], p.MAIN_V4)
    assert made['sizes']['min_astar'] == {'searchqa': {'items': 30, 'rooms': None},
        'officeqa': {'items': 4, 'rooms': None}, 'livemath': {'items': 5, 'rooms': None},
        'spreadsheetbench': {'items': 3, 'rooms': None}}
    assert manifest.check(made) == made
    carrier = SimpleNamespace(setting=SimpleNamespace(extra={'searchqa_tail': manifest._searchqa_tail(made['data'])}))
    kept, _ = step._tail(carrier)
    assert len(kept) == 1240
    assert not list(tmp_path.rglob('*unopened-test.json'))


def test_s0_rejects_insufficient_tail_before_zero_call_tests(tmp_path, monkeypatch):
    source, _ = prepared(tmp_path, monkeypatch, tail_count=1239)
    run = tmp_path / 'run'; consent(run, p.MAIN_V4)
    tested = tmp_path / 'selftest.json'
    write_json(tested, p.record('sandbox-selftest', 'smoke', {'passed': True, 'measured': MEASURED,
        'limits': {k: asdict(l) for k, l in sandbox.LIMITS.items()}}))
    monkeypatch.setattr(prelaunch, 'zero_call_checks', lambda *a, **k: pytest.fail('Insufficient supply reached checks'))
    with pytest.raises(ValueError, match='1,240'):
        v.collect_s0(tmp_path / 's0', preparation_file=source, root=run, snapshot_root=ROOT, selftest=tested)
    assert not (tmp_path / 's0' / v.S0_FILE).exists()


@pytest.mark.parametrize('field', ['allocations', 'v211_prompt_pins', 'freshness_amendment', 'smoke_schedule'])
def test_resealed_manifest_child_drift_refused(tmp_path, monkeypatch, field):
    _, options, _ = setup(tmp_path, monkeypatch)
    made = v.make_manifest(tmp_path / 'manifest.json', **options)
    if field == 'allocations':
        pin = made['data'][field]['officeqa']
        pin['slices']['confirm-r2'][0] = pin['slices']['confirm-r1'][0]
        pin['allocation_sha256'] = digest({k: x for k, x in pin.items() if k != 'allocation_sha256'})
    else:
        made['data'][field] = {}
    with pytest.raises(ValueError):
        manifest.check(reseal(made))


def test_real_manifest_refuses_structural_or_absent_readiness(tmp_path, monkeypatch):
    _, options, _ = setup(tmp_path, monkeypatch)
    options['smoke_chain'] = None
    monkeypatch.setitem(p.RUN_ROOTS, p.MAIN_V4, str(options['root']))
    with pytest.raises(ValueError, match='measured smoke'):
        v.make_manifest(tmp_path / 'real.json', **options)
    fake = tmp_path / 'structural'; fake.mkdir()
    write_json(fake / v.RESULT, p.record('v211-structural-smoke', 'engineering_fixture', {'passed': True}))
    options['measured_smoke'] = fake
    with pytest.raises(ValueError):
        v.make_manifest(tmp_path / 'real.json', **options)
    assert not (tmp_path / 'real.json').exists()


def test_g_chain_auditor_gets_independent_pinned_northgate_client(tmp_path, monkeypatch):
    _, options, _ = setup(tmp_path, monkeypatch)
    made = v.make_manifest(tmp_path / 'manifest.json', **options)
    called = []
    monkeypatch.setattr(manifest.client, 'solver_client', lambda model, **kwargs:
                        called.append((model, kwargs['config'])) or SimpleNamespace(model=model))
    factory = manifest._clients(made, 'G', None)
    found = factory(p.CHAINS['D'], 'officeqa')
    assert found.model == p.CHAINS['D'] and called[0][1]['route'] == 'B'
    assert called[0][0] == made['clients']['solver']['D']['model']
    assert factory(p.CHAINS['D'], 'officeqa') is found


def test_new_cli_choices_keep_g_measured_smoke_and_require_selftest():
    from scripts.run_execskill import parser
    args = parser().parse_args(['v211-manifest', '--out', '/tmp/m.json', '--root', '/tmp/r', '--s0', '/tmp/s0',
        '--provenance', '/tmp/p.json', '--roles-repo', '/tmp/roles', '--route-b-env', '/tmp/route.env',
        '--sheet-runtime', '/tmp/sheet-runtime.json', '--smoke-chain', 'G'])
    assert args.smoke_chain == 'G' and args.measured_smoke is None
    with pytest.raises(SystemExit):
        parser().parse_args(['v211-s0', '--out', '/tmp/s0', '--root', '/tmp/r'])
