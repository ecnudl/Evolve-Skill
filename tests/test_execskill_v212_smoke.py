"""v2.12 preparation and smoke wiring, using authored data and in-process clients only."""
from dataclasses import asdict, replace
import math
from pathlib import Path

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, manifest, prelaunch, profiles as p, units, zebra_smoke as zsmoke
from skillopt.execskill import zebralogic as z
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401
from tests.test_execskill_zpc_adapter import materialize, pool_rows
from tests.test_execskill_manifest import MEASURED, fake_environment, tree
from tests.test_execskill_v291_smoke import prepare
from tests.test_execskill_v27_zebra_smoke_review import made as zebra_made
from tests.test_execskill_v29_manifest_smoke import FixtureJudge
from tests.test_execskill_v210_snapshot import INSTRUCTION, _collect, _registered_files

CHILD = 'zebra-pc-v13'
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
    monkeypatch.setattr(z, 'test_panel', lambda *args, **kwargs: pytest.fail('Preparation cannot open a panel'))
    checked = zsmoke.collect_s0(root / 's0', pool=pool, split_manifest=split, snapshot_root=source,
        selftest=selftest, checks={'passed': True, 'evidence': 'authored_zero_call_checks'}, configuration=CHILD)
    provenance = root / 'snapshot-provenance.json'
    write_json(provenance, {'build_tree': str(source), 'git_head': 'f' * 40, 'snapshot_root': str(source),
        'sha256_list_sha256': checked['snapshot_sha256'], 'env_files_absent': True})
    options = dict(root=root / 'smoke', s0_file=root / 's0' / zsmoke.S0_FILE, provenance=provenance,
        roles_repo=root / 'unread-roles', elucid_env=root / 'unread-elucid.env', route_b_env=root / 'unread-route.env',
        smoke_chain='D', configuration=CHILD, environment_found=fake_environment())
    value = zsmoke.make_manifest(root / 'manifest.json', **options)
    return checked, value


def test_s0_manifest_uses_authored_pool_fc_anchor_and_inherited_registration(tmp_path, monkeypatch):
    checked, value = prepared(tmp_path, monkeypatch)
    assert checked['passed'] and checked['sealed_reads'] == 0 and checked['configuration'] == CHILD
    assert checked['slice_counts'] == {'smoke': 10, 'run': 60, 'accept': 100, 'spare': 3}
    assert value['configuration'] == CHILD and value['evidence'] == 'smoke'
    assert manifest.check(value) == value
    assert value['data']['launchable_chains'] == ['D']
    assert value['cards'] == {z.BENCH: z.CARD_TEXT}
    assert value['clients']['solver']['D']['backend'] == 'northgate'
    assert value['caps'] == budgets.caps(CHILD)
    assert value['prompt_sha'] == manifest.prompt_sha(CHILD)
    assert len(value['data']['confirm']['ids']) == 40
    assert value['data']['test_read_estimate'] == {'D': math.ceil(3400 * (200 + 200 * 1.6))}
    assert value['data']['test_read_terms'] == {'D': {z.BENCH: str(1768000)}}
    assert value['data']['smoke_results'] == {}  # a preparation anchor is never a measured result
    assert p.read_arms_of(CHILD) == ('F', 'C')
    assert not p.PLACEBO_ARMS[CHILD] and not p.TEST_WITHHOLDING[CHILD]


def test_authored_s2_s3_fault_repair_cache_and_fc_projection(tmp_path, monkeypatch):
    setting, services, solver, roles = prepare(tmp_path, monkeypatch, CHILD, zebra_made, 'fixed')
    setting = replace(setting, branch='N', longest=256,
                      budget=Budget(tmp_path / 'v212-ledger', sleep=lambda _: None))
    authored_workers = services.workers
    def workers(package, **options):
        for name in ('cleanup_grace_seconds', 'cleanup_events', 'ready_timeout_seconds', 'start_events'):
            options.pop(name, None)
        return authored_workers(package, **options)
    services = replace(services, workers=workers)
    setting.budget.declare(budgets.chain_caps('D', CHILD))
    judges = {name: FixtureJudge() for name in ('G', 'D')}
    monkeypatch.setattr(units, 'audit_judges', lambda *args: judges)
    monkeypatch.setattr(units, 'drainer', lambda *args: None)
    s2 = zsmoke._s2(setting, 'D')
    assert s2['passed'] and s2['items'] == s2['parsed'] == 10
    s3 = zsmoke._s3(setting, services)
    assert s3['passed'] and s3['failed_substages'] == []
    assert all(s3[stage]['passed'] for stage in ('S3a', 'S3b', 'S3c'))
    assert s3['S3a']['confirm']['confirm']['items'] == 2
    assert s3['S3a']['decision_used_for_adoption'] is False
    assert s3['S3c']['faulted_after'] == 0
    assert s3['S3c']['role_measurements']['engineer']['calls'] == 1
    counts = len(solver.requests), len(roles.seen), sum(len(judge.calls) for judge in judges.values())
    assert zsmoke._s2(setting, 'D') == s2 and zsmoke._s3(setting, services) == s3
    assert counts == (len(solver.requests), len(roles.seen), sum(len(judge.calls) for judge in judges.values()))
    projected = zsmoke.projection(s2, 'D', CHILD, s3=s3)
    per = projected['per_cell'][z.BENCH]
    assert projected['passed'] and projected['configuration'] == CHILD
    assert projected['read_estimate'] == math.ceil(projected['ratio'] * (200 * per['card'] + 200 * per['procedure']))
    assert zsmoke._scope_cells('D', CHILD)['D:test'] == [{z.BENCH: (200, 200)}]
    assert set(projected['scopes']) | set(projected['roles']) <= set(budgets.chain_caps('D', CHILD))
    assert projected['other_chain'] == 'not_launchable_in_this_configuration'


def test_measured_smoke_stage_plan_is_ordered_resumable_and_keeps_test_sealed(tmp_path, monkeypatch):
    setting, services, _, _ = prepare(tmp_path, monkeypatch, CHILD, zebra_made, 'fixed')
    setting = replace(setting, budget=Budget(tmp_path / 'v212-ledger', sleep=lambda _: None))
    value = {'configuration': CHILD, 'evidence': 'smoke', p.RECORD_HASH: 'a' * 64,
             'data': {'s0_sha256': 'b' * 64, 'snapshot_sha256': 'c' * 64}}
    monkeypatch.setattr(manifest, 'load', lambda *args, **kwargs: value)
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: setting)
    monkeypatch.setattr(manifest, 'services_of', lambda *args, **kwargs: services)
    monkeypatch.setattr(z, 'test_panel', lambda *args, **kwargs: pytest.fail('Smoke cannot open a panel'))
    seen = []
    def stage(name, result):
        def run(*args, **kwargs):
            seen.append(name)
            return result
        return run
    monkeypatch.setattr(zsmoke, '_s1', stage('S1', {'passed': True,
        'solver_probe': {'passed': True, 'route': 'B', 'longest': 256}}))
    monkeypatch.setattr(zsmoke, '_s2', stage('S2', {'passed': True}))
    monkeypatch.setattr(zsmoke, '_s3', stage('S3', {'passed': True}))
    monkeypatch.setattr(zsmoke, 'projection', stage('SE6', {'passed': True, 'read_estimate': 52000}))
    path = tmp_path / 'unread-manifest.json'
    with pytest.raises((ValueError, FileNotFoundError)):
        zsmoke.run_stage(path, 'D', 'S2', configuration=CHILD)
    assert seen == []
    assert zsmoke.STAGES == ('S1', 'S2', 'S3', 'SE6')
    for name in zsmoke.STAGES:
        first = zsmoke.run_stage(path, 'D', name, configuration=CHILD)
        assert zsmoke.run_stage(path, 'D', name, configuration=CHILD) == first
    assert seen == list(zsmoke.STAGES)
    result = p.verified(read_json(setting.root / 'D/lean-smoke/result.json'), 'zebra-smoke-result')
    assert result['configuration'] == CHILD and result['sealed_reads'] == 0
    assert result['stages'] == list(zsmoke.STAGES) and result['read_estimate'] == 52000
    with pytest.raises(ValueError, match='launches chain D only'):
        zsmoke.run_stage(path, 'G', 'S1', configuration=CHILD)


def test_v13_snapshot_copies_only_required_public_document_fixture_and_collects_s0(tmp_path):
    target = tmp_path / 'snapshot'
    value = zsmoke.snapshot(target, source=ROOT, git_head='a' * 40, configuration=CHILD)
    assert value['env_files_absent']
    assert _registered_files(target) == _registered_files(ROOT)
    assert sorted(path.relative_to(target).as_posix() for path in (target / 'docs').rglob('*') if path.is_file()) == [
        INSTRUCTION.as_posix()]
    assert (target / INSTRUCTION).read_bytes() == (ROOT / INSTRUCTION).read_bytes()
    assert prelaunch.sha256_list(target) == (target / 'sha256-list.txt').read_text()
    collected = _collect(target)
    assert collected['returncode'] == 0 and collected['tests_collected'] > 0
