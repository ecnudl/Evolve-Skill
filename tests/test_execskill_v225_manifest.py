"""Authored S0 to manifest integration; no services or real data are opened."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import manifest, profiles as p, v214_smoke, v222_smoke, v225_smoke
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_manifest import reseal
from tests.test_execskill_v222_preparation import prepared, full_supply
needs_capture = pytest.mark.skipif(not (Path(__file__).parent / 'fixtures/execskill/v225_parents_before.json').exists(),
                                   reason='parent capture not published (it holds ALFWorld game text)')


@needs_capture
def test_s0_to_smoke_manifest_binds_qualified_task_cards_and_main_v9_identity(tmp_path, monkeypatch):
    inherited, source, kwargs, old = prepared(tmp_path/'inputs', monkeypatch)
    original = v222_smoke.runtime.supply.slices
    monkeypatch.setattr(v222_smoke.runtime.supply, 'slices', lambda bench, rows, sizes, *a, **k:
        {'run': list(rows), 'accept': []} if bench == 'alfworld' else original(bench, rows, sizes, *a, **k))
    monkeypatch.setattr(v222_smoke.runtime.supply, 'alfworld_reset',
        lambda *_a, **_k: pytest.fail('Prepared authored views never open a native environment'))
    additional = full_supply(tmp_path/'supply', alf_runtime=inherited['runtime']['alfworld'])
    supply_value = {**read_json(additional), 'configuration': p.MAIN_V9}
    additional = tmp_path/'v225-additional-practice.json'
    write_json(additional, supply_value)
    worker = read_json(source.parent.parent/'selftest.json')
    worker.update(configuration=p.MAIN_V9, worker_sha256=sandbox.worker_sha256(configuration=p.MAIN_V9))
    measured = tmp_path/'worker.json'
    write_json(measured, reseal(worker))
    consent = tmp_path/'owner-consent.json'
    write_json(consent, {'by': 'owner', 'date': '2026-11-04', 'note': 'Authored main-v9 fixture.',
        'test_evaluation': True, 'sheet_test_qualification': True,
        'multi_arm_arms': list(p.read_arms_of(p.MAIN_V9))})
    checked = v214_smoke.collect_s0(tmp_path/'s0', preparation_file=source, **kwargs,
        root=tmp_path/'real', snapshot_root=manifest.REPO, selftest=measured, sheet_runtime=old['sheet_runtime'],
        checks={'passed': True, 'evidence': 'authored_zero_call_fixture'}, configuration=p.MAIN_V9,
        consent_file=consent, v222_practice_supply=additional)
    runtime = {**checked['preparation']['runtime'],
               'spreadsheetbench': checked['launch_sheet_runtime']['runtime']}
    assert checked['v225'] == v225_smoke.pins(runtime)
    assert checked['parents_before_sha256'] == hashlib.sha256(
        Path('tests/fixtures/execskill/v225_parents_before.json').read_bytes()).hexdigest()
    provenance = tmp_path/'provenance.json'
    write_json(provenance, {**read_json(old['provenance']), 'sha256_list_sha256': checked['snapshot_sha256']})
    options = {**old, 'root': tmp_path/'smoke-G', 's0_file': tmp_path/'s0'/v214_smoke.S0_FILE,
        'provenance': provenance, 'configuration': p.MAIN_V9, 'smoke_chain': 'G'}
    made = v214_smoke.make_manifest(tmp_path/'manifest-G.json', **options)
    assert manifest.check(made) == made
    assert made['data']['v225'] == checked['v225'] == v225_smoke.pins(made['runtime'])
    assert 'v222_cards' not in made['data'] and made['data']['v222_fallbacks'] == {}
    registered = made['data']['v222_practice']
    assert 'cards' not in registered and 'decomposition' not in registered
    assert set(registered['smoke_practice_draws']) == set(p.MAIN_V5_ORDER)
    assert made['data']['instruction_start'] == 'empty_format_only_v2_25'
    assert made['clients']['roles']['card_writer'] == p.card_writer_settings(p.MAIN_V9)
    assert made['sizes']['v214'] == v214_smoke.schedule(p.MAIN_V9)['maximum_schedule']
    monkeypatch.setattr(manifest, '_clients', lambda *_a, **_k:
        lambda *_args, **_kwargs: pytest.fail('Authored manifest load must not call a model'))
    loadable = reseal({**made, 'slot_root': str(tmp_path/'slots'), 'history_root': str(tmp_path/'history')})
    loaded = manifest.setting_of(loadable, 'G', docker=object())
    selected, _, loaded_registration = v222_smoke.practice(loaded)
    assert loaded_registration == registered
    assert all([row['task_id'] for row in selected[b]] == registered['smoke_practice_draws'][b]['items']
               for b in selected)
    for forbidden in ('cards', 'decomposition'):
        changed_registration = deepcopy(registered)
        changed_registration[forbidden] = {}
        loaded.extra['v222_practice'] = changed_registration
        with pytest.raises(ValueError, match='without decomposition pins'):
            v222_smoke.practice(loaded)
    loaded.extra['v222_practice'] = registered
    # A self-consistently resealed S0 with stale task-card text still fails the runtime binding.
    changed = deepcopy(made)
    bad_s0 = changed['data']['v214_s0']
    bad_s0['v225']['task_cards']['spreadsheetbench'] = '0'*64
    changed['data']['v214_s0'] = reseal(bad_s0)
    changed['data']['s0_sha256'] = changed['data']['v214_s0'][p.RECORD_HASH]
    with pytest.raises(ValueError, match='S0 pins recompute'):
        v214_smoke.check_manifest(reseal(changed))
