"""Pinned ID-only exclusion is nonvacuous at S0, allocation and manifest load."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from skillopt.coevo5 import data
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (exclusion, manifest, prelaunch, profiles as p, v210_smoke,
                               v211_allocation, v211_protection as protection, v211_smoke as smoke)
from skillopt.execskill.sandbox import client as sandbox
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_manifest import MEASURED
from tests.test_execskill_v210_manifest import consent
from tests.test_execskill_v211_allocation import pool, tail
from tests.test_execskill_v211_manifest import ROOT, prepared, reseal, setup


def replace_metadata(source, bench, change):
    pinned = source['data']['pinned']
    path = pinned['paths']['layouts'][bench] if bench in data.EXTENSIONS else pinned['paths']['split']
    value = read_json(path, sealed=True)
    change(value)
    value.pop('record_hash')
    Path(path).write_text(json.dumps(seal(value)))
    pinned['sha256'][path] = smoke._sha(path)


def collect(root, source, monkeypatch):
    path = root / 'changed-preparation.json'
    write_json(path, reseal(source))
    run = root / 'run'
    consent(run, p.MAIN_V4)
    tested = root / 'selftest.json'
    write_json(tested, p.record('sandbox-selftest', 'smoke', {'passed': True, 'measured': MEASURED,
        'limits': {key: asdict(value) for key, value in sandbox.LIMITS.items()}}))
    monkeypatch.setattr(prelaunch, 'zero_call_checks', lambda *a, **k: pytest.fail('Invalid IDs reached checks'))
    return smoke.collect_s0(root / 's0', preparation_file=path, root=run, selftest=tested, snapshot_root=ROOT)


@pytest.mark.parametrize('partition', ['final', 'test', 'sealed', 'reserve', 'verifier_calibration',
                                      'validation', 'evaluation', 'holdout'])
def test_allocation_rejects_nontraining_partition_even_with_training_part(partition):
    rows = pool('officeqa')
    rows[0]['partition'] = partition
    with pytest.raises(ValueError, match='training-side'):
        v211_allocation.allocate('officeqa', rows, excluded=['known-test-id'])


def test_allocation_refuses_empty_protection_and_protects_entire_tail():
    with pytest.raises(ValueError, match='Nonempty protected'):
        v211_allocation.allocate('officeqa', pool('officeqa'))
    rows = tail(1241)
    with pytest.raises(ValueError, match='overlaps protected'):
        v211_allocation.allocate('searchqa', pool('searchqa'), excluded=[rows['tail'][-1]['task_id']], **rows)


@pytest.mark.parametrize('bench', p.BENCHES)
def test_s0_refuses_pool_overlap_with_pinned_test_ids(tmp_path, monkeypatch, bench):
    _, source = prepared(tmp_path, monkeypatch)
    def overlap(value):
        parts = value['parts'] if bench in data.EXTENSIONS else value['splits'][bench]
        parts['test'][0]['task_id'] = 'alfworld-train' if bench == 'alfworld' else pool(bench)[0]['task_id']
    replace_metadata(source, bench, overlap)
    with pytest.raises(ValueError, match='overlaps protected'):
        collect(tmp_path, source, monkeypatch)
    assert not (tmp_path / 's0' / smoke.S0_FILE).exists()


@pytest.mark.parametrize('bench', p.BENCHES)
def test_s0_refuses_empty_test_set_even_if_reserve_is_nonempty(tmp_path, monkeypatch, bench):
    _, source = prepared(tmp_path, monkeypatch)
    replace_metadata(source, bench, lambda value:
        (value['parts'] if bench in data.EXTENSIONS else value['splits'][bench]).update(test=[]))
    with pytest.raises(ValueError, match='nonempty pinned protected test IDs'):
        collect(tmp_path, source, monkeypatch)


@pytest.mark.parametrize('part', ['reserve', 'verifier_calibration', 'closed_validation'])
def test_s0_protects_nontraining_metadata_partitions(tmp_path, monkeypatch, part):
    _, source = prepared(tmp_path, monkeypatch)
    replace_metadata(source, 'officeqa', lambda value: value['parts'].update(
        {part: [{'task_id': pool('officeqa')[0]['task_id'], 'family_id': 'authored'}]}))
    with pytest.raises(ValueError, match='overlaps protected'):
        collect(tmp_path, source, monkeypatch)


def test_s0_protects_extension_evaluation_blocks(tmp_path, monkeypatch):
    _, source = prepared(tmp_path, monkeypatch)
    replace_metadata(source, 'livemath', lambda value: value['evaluation_blocks'].update(
        items=[pool('livemath')[0]['task_id']]))
    with pytest.raises(ValueError, match='overlaps protected'):
        collect(tmp_path, source, monkeypatch)


def test_s0_protects_searchqa_dropped_id_hashes(tmp_path, monkeypatch):
    _, source = prepared(tmp_path, monkeypatch)
    entry = source['data']['exclusion'][exclusion.SEARCHQA_RUN]
    record = read_json(entry['path'])
    record['dropped'] = [protection.id_hash(pool('searchqa')[0]['task_id'])]
    record['exclusion_sha256'] = digest(record['dropped'])
    record = reseal(record)
    # Keep the persisted exclusion location used by _tail.
    Path(entry['path']).write_text(json.dumps(record))
    entry['record_sha256'] = record[p.RECORD_HASH]
    with pytest.raises(ValueError, match='overlaps protected'):
        collect(tmp_path, source, monkeypatch)


def test_metadata_only_access_pins_five_id_sets_and_alf_identity(tmp_path, monkeypatch):
    path, source = prepared(tmp_path, monkeypatch)
    imported = v210_smoke.preparation(path)
    with pytest.raises(ValueError, match='TestAccess'):
        protection.derive(imported, access=None)
    monkeypatch.setattr(data, 'test_panel', lambda *a, **k: pytest.fail('No test item text may be read'))
    protected = smoke.protected_ids(imported)
    for bench, row in protected.items():
        assert row['test_count'] == 1 and row['count'] >= 2
        assert row['protected_ids_sha256'] == digest(row['id_hashes'])
        assert protection.id_hash(bench + '-val') not in row['id_hashes']
        assert row['sources']['split']['sha256'] == source['data']['pinned']['sha256'][row['sources']['split']['path']]
    alf = protected['alfworld']['sources']['alfworld_test_identity']
    assert alf['record_sha256'] == imported['exclusion_records'][exclusion.ALFWORLD_RUN][p.RECORD_HASH]
    assert alf['split'] == 'valid_unseen' and alf['disjoint']
    assert not list(tmp_path.rglob('*unopened-test.json'))
    split = Path(source['data']['pinned']['paths']['split'])
    split.write_bytes(split.read_bytes() + b' ')
    with pytest.raises(ValueError, match='not the pinned file'):
        smoke.protected_ids(imported)


def test_manifest_refuses_resealed_empty_protected_ids(tmp_path, monkeypatch):
    _, options, _ = setup(tmp_path, monkeypatch)
    made = smoke.make_manifest(tmp_path / 'manifest.json', **options)
    protected = deepcopy(made['data']['protected_ids'])
    protected['officeqa'].update(id_hashes=[], count=0, protected_ids_sha256=digest([]))
    made['data']['protected_ids'] = protected
    made['data']['v211_s0']['protected_ids'] = protected
    made['data']['v211_s0'] = reseal(made['data']['v211_s0'])
    made['data']['s0_sha256'] = made['data']['v211_s0'][p.RECORD_HASH]
    with pytest.raises(ValueError, match='Nonempty source-bound'):
        manifest.check(reseal(made))
