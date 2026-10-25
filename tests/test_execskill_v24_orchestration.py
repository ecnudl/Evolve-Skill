"""v2.4 profile propagation through preparation, smoke and consent; all panels synthetic."""
from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict
from pathlib import Path

import pytest

from tests.execskill_zpc_fakes import tmp_path
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, chain, engineer, evaluation, manifest, profiles as p, policy,
                               readout, smoke, zebra_smoke, zebralogic as z)
from skillopt.execskill.sandbox import client as sandbox
from tests.test_execskill_chain import CONSENT, Launch, Learn, setting as chain_setting
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment
from tests.test_execskill_zpc_adapter import row
from tests.test_execskill_zpc_orchestration import made


def v24_manifest(tmp_path, monkeypatch):
    old = made(tmp_path, monkeypatch)
    given = {key: copy.deepcopy(old[key]) for key in manifest.GIVEN}
    return manifest.make(tmp_path / 'v24.json', evidence='engineering_fixture',
        configuration=p.ZEBRA_PC_V2, environment_found=fake_environment(), measured=MEASURED, **given)


def test_v24_manifest_settings_services_and_prompt_policy_pins(tmp_path, monkeypatch):
    m = v24_manifest(tmp_path, monkeypatch)
    assert m['version'] == p.kind('manifest-v2-4')
    assert m['data']['zebra_pc_features'] == manifest.zebra_features(p.ZEBRA_PC_V2)
    assert m['data']['zebra_pc_features']['family'] == 'v2.4'
    assert m['data']['zebra_pc_features']['features']['ACCEPT_FRESHNESS'] == \
        'zebra_split_v1_slices_reused_zpc1_acceptance_unused'
    assert m['prompt_sha']['v2']['engineer'] == engineer.ENGINEER_PROMPT_ZPC_V24_SHA256
    assert m['prompt_sha']['engineer'] == engineer.ENGINEER_PROMPT_SINGLE_ZPC_V24_SHA256
    assert m['prompt_sha'] != manifest.prompt_sha(p.ZEBRA_PC_V1)
    assert m['sandbox']['policy_sha256'] != policy.policy_sha256(version=policy.POLICY_VERSION_V23)
    setting = manifest.setting_of(m, 'D', docker=FakeDockerCLI(), transport=NO_CALLS)
    assert p.configuration_of(setting) == p.ZEBRA_PC_V2 and p.namespace_of(setting, 'D') == 'D-zpc2'
    services = manifest.services_of(m, 'D', setting=setting, transport=NO_CALLS)
    assert services.sources is services.engine is services.checker is None
    assert set(setting.cards) == set(setting.runtime) == set(setting.pools) == {z.BENCH}
    assert m['clients']['solver']['D']['M'] == {z.BENCH: 16384}
    assert m['clients']['solver']['D']['read_timeout'] == {z.BENCH: 600}


def test_v24_preparation_pins_configuration_and_refuses_v1_s0_and_smoke(tmp_path, monkeypatch):
    listing = 'authored v24 snapshot fixture\n'
    sha = hashlib.sha256(listing.encode()).hexdigest()
    monkeypatch.setattr(zebra_smoke.prelaunch, 'sha256_list', lambda root: listing)
    monkeypatch.setattr(manifest, 'pin_code', lambda: {'authored.py': 'a' * 64})
    provenance = tmp_path / 'provenance.json'
    write_json(provenance, {'build_tree': str(tmp_path / 'source'), 'git_head': 'f' * 40,
        'snapshot_root': str(manifest.REPO), 'sha256_list_sha256': sha, 'env_files_absent': True})
    s0 = tmp_path / 's0.json'
    fields = {'passed': True, 'configuration': p.ZEBRA_PC_V1, 'registration': z.identity(),
        'snapshot_root': str(manifest.REPO), 'snapshot_sha256': sha,
        'pool': {'path': z.POOL_PATH, 'sha256': z.POOL_SHA256},
        'split_manifest': {'path': z.SPLIT_MANIFEST_PATH, 'sha256': 'b' * 64, 'field': 'output_sha256'},
        'measured': MEASURED, 'limits': {k: asdict(v) for k, v in sandbox.LIMITS.items()}}
    write_json(s0, p.record('zebra-s0', 'smoke', fields))
    args = dict(s0_file=s0, provenance=provenance, roles_repo=tmp_path / 'credentials',
        elucid_env=tmp_path / 'elucid.env', route_b_env=tmp_path / 'route-b.env',
        environment_found=fake_environment(), configuration=p.ZEBRA_PC_V2)
    smoke_path = tmp_path / 'smoke-manifest.json'
    with pytest.raises(ValueError, match='S0 belongs'):
        zebra_smoke.make_manifest(smoke_path, root=tmp_path / 'smoke', smoke_chain='D', **args)
    fields['configuration'] = p.ZEBRA_PC_V2
    checked = p.record('zebra-s0', 'smoke', fields)
    s0.write_text(__import__('json').dumps(checked))
    prepared = zebra_smoke.make_manifest(smoke_path, root=tmp_path / 'smoke', smoke_chain='D', **args)
    smoke_result = tmp_path / 'smoke-result.json'
    result = {'passed': True, 'configuration': p.ZEBRA_PC_V1, 'chain': 'D', 's0': checked[p.RECORD_HASH],
        'snapshot_sha256': sha, 'manifest_path': str(smoke_path), 'manifest': prepared[p.RECORD_HASH],
        'read_estimate': 1000}
    write_json(smoke_result, p.record('zebra-smoke-result', 'smoke', result))
    with pytest.raises(ValueError, match='passed measured zebra smoke'):
        zebra_smoke.make_manifest(tmp_path / 'never.json', root=p.RUN_ROOTS[p.ZEBRA_PC_V2],
                                 smoke_results=[smoke_result], **args)
    result['configuration'] = p.ZEBRA_PC_V2
    smoke_result.write_text(__import__('json').dumps(p.record('zebra-smoke-result', 'smoke', result)))
    real = zebra_smoke.make_manifest(tmp_path / 'real.json', root=p.RUN_ROOTS[p.ZEBRA_PC_V2],
                                    smoke_results=[smoke_result], **args)
    assert real['configuration'] == p.ZEBRA_PC_V2 and real['evidence'] == 'zebra_pc_v2_real_run'
    assert real['data']['launchable_chains'] == ['D']
    assert real['data']['zebra_pc'] == prepared['data']['zebra_pc'] == z.identity()
    assert real['root'] == '/data/execskill-20261025-zebra-pc-v2'


def test_v24_read_consent_and_canaries_remain_one_panel_and_profile_bound(tmp_path, monkeypatch):
    m = v24_manifest(tmp_path, monkeypatch)
    root, accesses = Path(m['root']), []
    fake = [z.normalize({**row(index=i), 'puzzle':
        'There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. '
        + 'Synthetic unique canary number %d.' % i}, partition='test') for i in range(6)]
    def panel(pinned, bench, *, access):
        accesses.append(bench)
        assert bench == z.BENCH
        return fake, {'panel_hash': 'a' * 64}
    args = dict(pools=m['data']['pools'], run=m[p.RECORD_HASH], evidence=m['evidence'], panel=panel,
                order=(z.BENCH,), configuration=p.ZEBRA_PC_V2)
    with pytest.raises(ValueError, match='consent'):
        evaluation.make_read_canaries(root, m['data']['pinned'], **args)
    assert accesses == []
    write_json(root / 'shared' / 'consent.json', CONSENT)
    record = evaluation.make_read_canaries(root, m['data']['pinned'], **args)
    assert accesses == [z.BENCH] and record['configuration'] == p.ZEBRA_PC_V2
    assert evaluation.load_canaries(root, read=True, configuration=p.ZEBRA_PC_V2) == record['canaries']
    with pytest.raises(ValueError, match='trusted ZebraLogic'):
        evaluation.load_canaries(root, read=True, configuration=p.ZEBRA_PC_V1)


@pytest.mark.parametrize('accepted', [False, True])
def test_v24_one_step_chain_empty_behavior_and_single_chain_report(tmp_path, accepted):
    setting = chain_setting(tmp_path, chain_='D')
    setting.extra.update(configuration=p.ZEBRA_PC_V2, test_read_terms={'D': {z.BENCH: '1000'}})
    learn, launched = Learn(accept=accepted), Launch(tmp_path)
    assert chain.run(setting, 'D', learn=learn, launch=launched) == {'status': 'complete'}
    assert [(k, bench) for _, k, bench, _ in learn.calls] == [(1, z.BENCH)]
    assert [spec['bench'] for spec in launched.specs] == ([z.BENCH] if accepted else [])
    value = read_json(setting.root / 'D' / chain.TEST_READ)
    assert value['status'] == ('read' if accepted else 'not_read')
    if not accepted:
        assert readout.report({'root': str(setting.root), p.RECORD_HASH: setting.run,
            'evidence': setting.evidence, 'configuration': p.ZEBRA_PC_V2,
            'data': {'launchable_chains': ['D']}}, out=tmp_path / 'report') == {'D': 'not_read'}


@pytest.mark.parametrize('name,args', [
    ('snapshot', ['--out', 'out', '--git-head', 'f' * 40]), ('s0', ['--out', 'out']),
    ('manifest', ['--out', 'out', '--root', 'root', '--s0', 's0', '--provenance', 'prov',
                  '--roles-repo', 'roles', '--elucid-env', 'env', '--route-b-env', 'route']),
    ('smoke', ['--manifest', 'm', '--chain', 'D', '--stage', 'S1']),
])
def test_zpc_cli_configuration_is_explicit_and_defaults_to_v1(name, args):
    from scripts.run_execskill import parser
    assert parser().parse_args(['zpc-' + name, *args]).configuration == p.ZEBRA_PC_V1
    assert parser().parse_args(['zpc-' + name, *args, '--configuration', p.ZEBRA_PC_V2]).configuration == p.ZEBRA_PC_V2


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_v24_smoke_projection_has_same_caps_and_prices_and_new_identity(chain_id):
    s2 = {'tokens_per_cell': 5300, 'items': 10, 'settled_tokens': 53000,
          'measurements': {'actual': 53000, 'request_bytes': {z.BENCH: 1000}}}
    before = zebra_smoke.projection(s2, chain_id)
    after = zebra_smoke.projection(s2, chain_id, p.ZEBRA_PC_V2)
    assert after == {**before, 'configuration': p.ZEBRA_PC_V2}
    assert budgets.chain_caps(chain_id, p.ZEBRA_PC_V1) == budgets.chain_caps(chain_id, p.ZEBRA_PC_V2)
    assert smoke.engineer_request_floor(p.ZEBRA_PC_V2) >= p.ROLE_INPUT_BYTES + len(
        engineer.ENGINEER_SYSTEM_ZPC_V24.encode())
