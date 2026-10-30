"""V2.8 registered identities, explicit caps and pinned manifests; authored offline fixtures."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from skillopt.execskill import budgets, engineer, manifest, notes, policy, profiles as p, protocol, smoke
from skillopt.execskill.package import Procedure
from tests.test_execskill_alf_v1_profile import alf_manifest
from tests.test_execskill_manifest import MEASURED, fake_environment
from tests.test_execskill_v24_profile import padded_source
from tests.test_execskill_zpc_orchestration import made
from tests.test_execskill_zpc_profile import procedure

from tests.execskill_v293_fakes import tmp_path  # noqa: F401; neutral OS scratch, including plain pytest.


NEW = ((p.ZEBRA_PC_V6, p.ZEBRA_PC_V5, 'zpc6', 'zebralogic'),
       (p.ALFWORLD_V3, p.ALFWORLD_V2, 'alf3', 'alfworld'))


@pytest.mark.parametrize('configuration,parent,namespace,bench', NEW)
def test_profiles_inherit_panels_caps_and_adoption_bars(configuration, parent, namespace, bench):
    assert p.FEATURE_FAMILIES[configuration] == 'v2.8'
    assert all(fn(configuration) for fn in (p.is_v23, p.is_v24, p.is_v25, p.is_v26, p.is_v27, p.is_v28))
    assert {name for name in p.CONFIGURATIONS if p.is_v28(name) and not p.is_v29(name)} == {p.ZEBRA_PC_V6, p.ALFWORLD_V3}
    assert not p.is_v28(None)
    for name in ('CONFIGURATIONS', 'CONFIG_STEP_CAPS', 'CONFIG_SCHEDULE_CELLS', 'CONFIG_ROLE_CAPS', 'CONFIG_GLM_CAP',
                 'CONFIG_CAP_FACTOR', 'COST_CHECK_PAUSES', 'TEST_READ_CELLS', 'STAGE_READ', 'LEARNING', 'FIX_ECHO',
                 'META_COUNTERFACTUAL', 'TRAIN_SIGN', 'PRUNE_NON_FIRING', 'ACCEPT_RULES', 'ENGINEER_MAX_TOKENS',
                 'TRIM_PAYLOADS', 'NORMALIZE_STRUCTURE', 'CHECK_NON_FIRING', 'IDENTICAL_REQUEST_REUSE',
                 'CODE_EXTRACTION', 'MULTIPLE_PYTHON_BLOCKS'):
        assert getattr(p, name)[configuration] == getattr(p, name)[parent], name
    assert p.CONFIGURATIONS[configuration] is not p.CONFIGURATIONS[parent]
    assert p.ACCEPT_RULES[configuration] is not p.ACCEPT_RULES[parent]
    assert budgets.caps(configuration) == budgets.caps(parent)
    assert p.active_benches(configuration) == p.read_benches(configuration) == (bench,)
    assert p.launchable_chains(configuration) == ('D',)
    assert p.CHAIN_NAMESPACES[configuration] == {'G': 'G-' + namespace, 'D': 'D-' + namespace}
    assert p.RUN_ROOTS[configuration] == '/data/execskill-20261026-' + configuration
    assert p.ENGINEER_RECORDS[configuration] == 'engineer-v2-8'
    assert p.POLICY_VERSIONS[configuration] == policy.POLICY_VERSION_V28
    assert p.ENGINEER_CALL_BUDGETS[configuration] == 13
    assert p.TRAIN_ENGINEER_CALL_BUDGETS[configuration] == 23
    assert p.ENGINEER_CALL_BUDGETS[parent] == p.ENGINEER_CALLS == 6
    assert p.TRAIN_ENGINEER_CALL_BUDGETS[parent] == p.TRAIN_ENGINEER_CALLS == 10
    assert p.TRAIN_ROUNDS == 6 and p.TRAIN_PATIENCE == 2 and p.TRAIN_FIXES == 3
    for kind in ('engineer', 'manifest', 'procedure'):
        stamped = p.record(kind + '-v2-8', p.REAL_RUN_EVIDENCE[configuration], {'authored': True})
        assert p.verified(stamped, kind) == stamped
    with pytest.raises(ValueError, match='another kind'):
        p.verified(p.record('cell-v2-8', 'engineering_fixture', {}), 'cell')


def test_freshness_and_manifest_paths_are_new_and_explicit():
    assert p.ZEBRA_PC_V6_MANIFEST == p.ZEBRA_PC_V6_ROOT + '-manifest.json'
    assert p.ALFWORLD_V3_MANIFEST == p.ALFWORLD_V3_ROOT + '-manifest.json'
    assert p.ACCEPT_FRESHNESS[p.ZEBRA_PC_V6] == 'zebra_split_v1_slices_reused_accept_used_three_times_plus_ub_probe'
    assert p.ALFWORLD_V3_FRESHNESS == 'alfworld_split_v1_slices_reused_acceptance_used_once'
    assert p.ACCEPT_FRESHNESS[p.ALFWORLD_V3] == p.ALFWORLD_V3_FRESHNESS
    assert p.REAL_RUN_EVIDENCE[p.ZEBRA_PC_V6] == 'zebra_pc_v6_real_run'
    assert p.REAL_RUN_EVIDENCE[p.ALFWORLD_V3] == 'alfworld_v3_real_run'
    assert manifest.alfworld_registration_key(p.ALFWORLD_V3) == 'alfworld_v3'


@pytest.mark.parametrize('size', (16000, 16001, 23999, 24000, 24001))
def test_source_limit_is_24000_only_for_v28(size):
    source = padded_source(size)
    assert bool(policy.check(source, version=policy.POLICY_VERSION_V28)) is (size > 24000)
    assert bool(policy.check(source, version=policy.POLICY_VERSION_V25)) is (size > 16000)
    assert policy.MAX_SOURCE_BYTES_V28 == policy.source_limit(policy.POLICY_VERSION_V28) == 24000


def test_policy_canonical_bytes_keep_every_safety_rule_and_roundtrip():
    ignored = {'version', 'registration', 'max_source_bytes'}
    assert {k: v for k, v in policy.POLICY_V28.items() if k not in ignored} == {
        k: v for k, v in policy.POLICY_V25.items() if k not in ignored}
    raw = policy.POLICY_PATH_V28.read_bytes()
    assert json.loads(raw) == policy.POLICY_V28
    assert hashlib.sha256(raw).hexdigest() == policy.policy_sha256(version=policy.POLICY_VERSION_V28)
    assert policy.policy_sha256(version=policy.POLICY_VERSION_V28) == '1027a5fcd9f3289d29366800a8d9df32fe1a60bc465e47dfb05b5072b174b0d6'
    proc = replace(procedure('zebralogic', p.BENCHES), policy_version=policy.POLICY_VERSION_V28,
                   source=padded_source(24000))
    assert proc.to_json()['version'] == p.kind('procedure-v2-8')
    assert Procedure.from_json(proc.to_json()) == proc


@pytest.mark.parametrize('configuration,parent,namespace,bench', NEW)
def test_manifests_pin_v28_contract_prompts_and_policy(tmp_path, monkeypatch, configuration, parent, namespace, bench):
    before = (made if bench == 'zebralogic' else alf_manifest)(tmp_path, monkeypatch)
    given = {key: deepcopy(before[key]) for key in manifest.GIVEN}
    given['data']['launchable_chains'] = ['D']
    if bench == 'alfworld':
        given['data']['alfworld_v3'] = given['data'].pop('alfworld_v1')
    value = manifest.make(tmp_path / 'v28.json', evidence='engineering_fixture', configuration=configuration,
        measured=MEASURED, environment_found=fake_environment(), **given)
    assert value['version'] == p.kind('manifest-v2-8')
    assert manifest.check(value) == value
    assert value['prompt_sha'] == manifest.prompt_sha(configuration)
    assert value['prompt_sha']['v28'] == {
        'fix': engineer.ENGINEER_PROMPT_FIX_V28_SHA256,
        'format_retry': engineer.ENGINEER_PROMPT_FORMAT_RETRY_V28_SHA256}
    assert value['sandbox']['policy_sha256'] == policy.policy_sha256(version=policy.POLICY_VERSION_V28)
    key = 'zebra_pc_features' if bench == 'zebralogic' else 'alfworld_features'
    features = value['data'][key]['outcome_engineer']
    assert features == manifest.outcome_engineer_features(configuration)
    assert features['source_bytes'] == 24000 and features['hashseed'] == 0
    assert features['note_screen_sha256'] == notes.v28_screen_sha256()
    assert features['single_call_budget'] == 13 and features['train_call_budget'] == 23
    assert features['acceptance_j3'] == features['train_fault_guards'] == 'information'
    assert value['caps'] == budgets.caps(parent)


@pytest.mark.parametrize('command,configuration', [('zpc-smoke', p.ZEBRA_PC_V6), ('alf-smoke', p.ALFWORLD_V3)])
def test_cli_accepts_new_configuration(command, configuration):
    from scripts.run_execskill import parser
    options = parser().parse_args([command, '--manifest', 'authored.json', '--chain', 'D', '--stage', 'S3',
                                   '--configuration', configuration])
    assert options.configuration == configuration


@pytest.mark.parametrize('configuration,parent,namespace,bench', NEW)
def test_smoke_projection_reserves_format_calls_and_full_system_prompt(configuration, parent, namespace, bench):
    before = smoke.max_role_calls(parent)
    assert smoke.max_role_calls(configuration) == {**before, 'engineer': 6 * (23 + 4)}
    assert smoke.max_role_calls(configuration)['leakage'] == 72
    systems = [engineer.engineer_v28.system(configuration, train=train) + suffix
               for train in (True, False)
               for suffix in ('', engineer.engineer_v28.FIX_SYSTEM, engineer.engineer_v28.FORMAT_RETRY_SYSTEM)]
    assert smoke.engineer_request_floor(configuration) == p.ROLE_INPUT_BYTES + max(
        len(system.encode()) for system in [*systems, engineer.ANALYST_SYSTEM])
