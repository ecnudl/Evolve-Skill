"""Strict main-v8 practice pins, authored pools and protected-ID exclusion only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (alfworld_format, manifest, profiles as p, v214_preparation, v214_smoke,
                               v222_cards as cards, v222_smoke as v)
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v214_preparation import prepared as inherited_prepared
from tests.test_execskill_v211_manifest import reseal
from tests.execskill_v222_fakes import alf_rows
needs_capture = pytest.mark.skipif(not (Path(__file__).parent / 'fixtures/execskill/v222_parents_before.json').exists(),
                                   reason='parent capture not published (it holds ALFWorld game text)')


@pytest.fixture(autouse=True)
def no_native_alfworld(monkeypatch):
    monkeypatch.setattr(v.runtime.supply, 'alfworld_reset',
        lambda *args, **kwargs: pytest.fail('Authored pinned views must not open a native ALFWorld session'))


def prepared(root, monkeypatch):
    """Upgrade only this compressed fixture's inherited ALF row to a real pin."""
    source, path, kwargs, options = inherited_prepared(root, monkeypatch)
    source['runtime']['alfworld']['alfworld_data'] = str(root / 'alfworld')
    environment = alfworld_format.environment_runtime(source['runtime']['alfworld'])
    pin = source['data']['pools']['alfworld']
    rows, _ = alf_rows(manifest._items(pin, 'alfworld'), Path(environment['alfworld_data']), runtime=environment)
    pin['path'] = str(root / 'authored-alfworld-pool.json')
    write_json(pin['path'], rows)
    pin['sha256'] = hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()
    source = reseal(source)
    path = path.with_name('authored-alfworld-s0.json')
    write_json(path, source)
    return source, path, kwargs, options


def supply(root, *, bench='officeqa', count=100, alf_runtime=None):
    path = root / (bench + '-practice.json')
    rows = [{'task_id': 'authored-' + bench + '-' + str(i), 'benchmark': bench, 'partition': 'development',
             'public': {'question': 'An authored public quantity?', 'context': 'An authored context.'},
             'private': {'answer': 'author-defined'}} for i in range(count)]
    if bench == 'alfworld':
        environment = alfworld_format.environment_runtime(alf_runtime) if alf_runtime else None
        games = Path(environment['alfworld_data']) if environment else root / 'games'
        rows, _ = alf_rows(rows, games, runtime=environment)
    write_json(path, rows)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}, rows


def full_supply(root, *, alf_runtime=None):
    pins = {bench: supply(root, bench=bench, count=20 if bench == 'alfworld' else 100,
                         alf_runtime=alf_runtime)[0] for bench in cards.BENCHES}
    path = root / 'additional-practice.json'
    write_json(path, {'configuration': p.MAIN_V8, 'pools': pins})
    return path


def test_insufficient_original_practice_blocks_before_measurement_and_preserves_the_parent(tmp_path, monkeypatch):
    _, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    parent = v214_preparation.preparation(path, **kwargs, configuration=p.MAIN_V7)
    with pytest.raises(ValueError, match='minimum available 18|Too few items'):
        v214_preparation.preparation(path, **kwargs, configuration=p.MAIN_V8)
    assert v214_preparation.preparation(path, **kwargs, configuration=p.MAIN_V7) == parent
    assert 'v222_practice' not in parent['data']


def test_explicit_additional_practice_binds_exact_seeded_draws_and_reverifies_content(tmp_path, monkeypatch):
    source, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    # The inherited bridge fixture has one authored ALF row; its original
    # decision-pool IDs are deliberately empty in this compressed unit test.
    original = v.runtime.supply.slices
    monkeypatch.setattr(v.runtime.supply, 'slices', lambda bench, rows, sizes, *a, **k:
        {'run': list(rows), 'accept': []} if bench == 'alfworld' else original(bench, rows, sizes, *a, **k))
    additional = full_supply(tmp_path / 'supply', alf_runtime=source['runtime']['alfworld'])
    found = v214_preparation.preparation(path, **kwargs, configuration=p.MAIN_V8,
                                       v222_practice_supply=additional)
    registered = found['data']['v222_practice']
    assert registered['cards'] == cards.manifest_pins() and registered['sealed_reads'] == 0
    assert {b: row['count'] for b, row in registered['decomposition'].items()} == {
        b: 20 if b == 'alfworld' else 100 for b in cards.BENCHES}
    assert v214_preparation.verify(found) == found
    pin = registered['supply_pins']['officeqa']
    Path(pin['path']).write_text('[]\n')
    with pytest.raises(ValueError, match='SHA256 differs'):
        v214_preparation.verify(found)


@pytest.mark.parametrize('problem', ['sha', 'partition', 'duplicate', 'protected', 'alias', 'label', 'schema'])
def test_additional_practice_fails_closed_on_drift_or_unreviewed_sources(tmp_path, problem):
    pin, rows = supply(tmp_path)
    args = {}
    if problem == 'partition': rows[0]['partition'] = 'test'
    if problem == 'duplicate': rows[1]['task_id'] = rows[0]['task_id']
    if problem == 'label': rows[0].pop('partition')
    if problem == 'schema': rows[0].pop('private')
    if problem == 'protected':
        args['protected_ids'] = {'officeqa': {'id_hashes': [hashlib.sha256(rows[0]['task_id'].encode()).hexdigest()]}}
    if problem == 'alias': args['forbidden_paths'] = [pin['path']]
    if problem in ('partition', 'duplicate', 'label', 'schema'):
        Path(pin['path']).write_text(json.dumps(rows))
        pin['sha256'] = hashlib.sha256(Path(pin['path']).read_bytes()).hexdigest()
    if problem == 'sha': pin['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        v.load_supply_pins({'officeqa': pin}, **args)


def test_source_paths_cannot_name_protected_partitions_even_when_the_pin_matches(tmp_path):
    pin, _ = supply(tmp_path / 'sealed')
    with pytest.raises(ValueError, match='protected partition'):
        v.load_supply_pins({'officeqa': pin})


def test_additional_supply_is_never_enabled_for_an_older_configuration(tmp_path, monkeypatch):
    _, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    additional = full_supply(tmp_path / 'supply')
    with pytest.raises(ValueError, match='main-v8 only'):
        v214_preparation.preparation(path, **kwargs, configuration=p.MAIN_V7, v222_practice_supply=additional)


@needs_capture
def test_main_v8_s0_and_manifest_bind_worker_cards_supplies_consent_and_all_older_fingerprints(tmp_path, monkeypatch):
    inherited, source, kwargs, old = prepared(tmp_path / 'inputs', monkeypatch)
    original = v.runtime.supply.slices
    monkeypatch.setattr(v.runtime.supply, 'slices', lambda bench, rows, sizes, *a, **k:
        {'run': list(rows), 'accept': []} if bench == 'alfworld' else original(bench, rows, sizes, *a, **k))
    additional = full_supply(tmp_path / 'supply', alf_runtime=inherited['runtime']['alfworld'])
    selftest = read_json(source.parent.parent / 'selftest.json')
    selftest.update(configuration=p.MAIN_V8, worker_sha256=sandbox.worker_sha256(configuration=p.MAIN_V8))
    tested = tmp_path / 'main-v8-worker.json'
    write_json(tested, reseal(selftest))
    consent = tmp_path / 'owner-consent.json'
    write_json(consent, {'by': 'owner', 'date': '2026-11-03', 'note': 'Authored consent fixture.',
        'test_evaluation': True, 'sheet_test_qualification': True, 'multi_arm_arms': list(p.read_arms_of(p.MAIN_V8))})
    checked = v214_smoke.collect_s0(tmp_path / 's0', preparation_file=source, **kwargs,
        root=tmp_path / 'real', snapshot_root=manifest.REPO, selftest=tested, sheet_runtime=old['sheet_runtime'],
        checks={'passed': True, 'evidence': 'authored_zero_call_fixture'}, configuration=p.MAIN_V8,
        consent_file=consent, v222_practice_supply=additional)
    assert checked['parents_before_sha256'] == hashlib.sha256(
        Path('tests/fixtures/execskill/v222_parents_before.json').read_bytes()).hexdigest()
    provenance = tmp_path / 'provenance.json'
    write_json(provenance, {**read_json(old['provenance']), 'sha256_list_sha256': checked['snapshot_sha256']})
    options = {**old, 'root': tmp_path / 'smoke-G', 's0_file': tmp_path / 's0' / v214_smoke.S0_FILE,
        'provenance': provenance, 'configuration': p.MAIN_V8, 'smoke_chain': 'G'}
    made = v214_smoke.make_manifest(tmp_path / 'manifest-G.json', **options)
    assert manifest.check(made) == made
    assert made['data']['v222_practice'] == checked['preparation']['data']['v222_practice']
    assert made['data']['v222_practice_supply'] == checked['v222_practice_supply']
    assert checked['v222_practice_supply'] == made['data']['v222_practice']['v222_practice_supply']
    assert made['cards'] == {bench: cards.format_text(bench) for bench in cards.BENCHES}
    assert set(made['sandbox']['worker_sha256_by_bench'].values()) == {sandbox.worker_sha256(configuration=p.MAIN_V8)}
    assert made['sizes']['v214'] == v214_smoke.schedule(p.MAIN_V8)['maximum_schedule']
    overlay_key = 'alfworld_routing_overlay'
    overlay = checked['preparation']['data']['v222_practice'][overlay_key]
    assert made['data']['v222_practice'][overlay_key] == overlay
    assert v214_preparation.verify(checked['preparation'])['data']['v222_practice'][overlay_key] == overlay

    # The real manifest loader must reuse the prepared overlay without making
    # a client or opening a native environment; the latter is guarded above.
    monkeypatch.setattr(manifest, '_clients', lambda *args, **kwargs:
        lambda *a, **k: pytest.fail('Overlay reload must not create or call a model client'))
    loadable = reseal({**made, 'slot_root': str(tmp_path / 'slots'), 'history_root': str(tmp_path / 'history')})
    assert all(Path(loadable[key]).is_relative_to(tmp_path) for key in ('root', 'slot_root', 'history_root'))
    assert all(Path(pin['path']).is_relative_to(tmp_path) for pin in loadable['data']['pools'].values())
    loaded = manifest.setting_of(loadable, 'G', docker=object())
    selected, harms, registered = v.practice(loaded)
    assert registered[overlay_key] == overlay
    assert v.runtime.preflight(loaded)[1] == registered['harm']
    for row in selected['alfworld'] + harms['alfworld']:
        view = overlay['views'][row['task_id']]
        assert row['public']['routing_view'] == view['view']
        assert row['public']['routing_view_sha256'] == view['view_sha256']

    for problem in ('missing', 'view_hash'):
        changed = deepcopy(loadable)
        practice = changed['data']['v222_practice']
        if problem == 'missing':
            practice.pop(overlay_key)
            message = 'requires its prepared ALFWorld routing overlay'
        else:
            view = next(iter(practice[overlay_key]['views'].values()))
            view['view_sha256'] = '0' * 64
            practice[overlay_key] = reseal(practice[overlay_key])
            message = 'intact public reset routing view'
        with pytest.raises(ValueError, match=message):
            manifest.setting_of(reseal(changed), 'G', docker=object())


@needs_capture
def test_snapshot_copies_every_pinned_decomposition_file_and_parent_capture(tmp_path):
    target = tmp_path / 'snapshot'
    v214_smoke.snapshot(target, source=manifest.REPO, git_head='a' * 40, configuration=p.MAIN_V8)
    for name, sha in cards.FILE_SHA256.items():
        assert hashlib.sha256((target / 'tests/fixtures/execskill/v222_cards' / name).read_bytes()).hexdigest() == sha
    relative = Path('tests/fixtures/execskill/v222_parents_before.json')
    assert (target / relative).read_bytes() == (manifest.REPO / relative).read_bytes()
    assert (target / 'skillopt/execskill/sandbox/worker_v222.py').is_file()
    listing = (target / 'sha256-list.txt').read_text()
    assert str(relative) in listing
    assert all('tests/fixtures/execskill/v222_cards/' + name in listing for name in cards.FILE_SHA256)
