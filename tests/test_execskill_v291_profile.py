"""v2.9.1 registration/cap invariants and frozen parent identities, offline only."""
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.coevo5.ledger import reservation
from skillopt.execskill import (budgets, confirm, engineer_v291, manifest, profiles as p,
                               routes, smoke, v29_limits)
from tests.test_execskill_zpc_pipeline import offline
from tests.test_execskill_v28_profile import tmp_path
from tests.test_execskill_zpc_regression import FEATURES

CHILDREN = [(p.ZEBRA_PC_V8, p.ZEBRA_PC_V7, 'zpc8', 'zebralogic'),
            (p.ALFWORLD_V5, p.ALFWORLD_V4, 'alf5', 'alfworld')]


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_v291_copies_parents_without_mutating_them(config, parent, tag, bench):
    assert p.is_v291(config) and p.is_v29(config) and not p.is_v291(parent)
    assert p.FEATURE_FAMILIES[config] == 'v2.9'
    assert p.active_benches(config) == (bench,) and p.launchable_chains(config) == ('D',)
    assert p.RUN_ROOTS[config] == '/data/execskill-20261027-' + config
    assert p.CHAIN_NAMESPACES[config] == {'G': 'G-' + tag, 'D': 'D-' + tag}
    assert p.ENGINEER_RECORDS[config] == 'engineer-v2-9-1'
    assert p.POLICY_VERSIONS[config] == p.POLICY_VERSIONS[parent]
    assert p.read_arms_of(config) == p.read_arms_of(parent)
    for name in ('LEARNING', 'ACCEPT_RULES', 'TRAIN_SIGN', 'STAGE_READ', 'ENGINEER_MAX_TOKENS',
                 'FIX_ECHO', 'META_COUNTERFACTUAL', 'CHECK_NON_FIRING', 'IDENTICAL_REQUEST_REUSE'):
        assert getattr(p, name)[config] == getattr(p, name)[parent]
    assert p.CONFIGURATIONS[config] is not p.CONFIGURATIONS[parent]
    record = p.record('engineer-v2-9-1', p.REAL_RUN_EVIDENCE[config], {})
    assert p.verified(record, 'engineer') == record
    assert p.train_patience(config) == 4 and p.train_patience(parent) == p.TRAIN_PATIENCE == 2
    assert p.TRAIN_ROUNDS == 6 and p.FAULT_REPAIRS == 2 and p.TRAIN_FIXES == 3


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_v291_budgets_cover_full_repair_format_audit_and_six_round_schedules(config, parent, tag, bench):
    assert p.ENGINEER_CALL_BUDGETS[config] == 31
    assert p.TRAIN_ENGINEER_CALL_BUDGETS[config] == 41
    for name in ('ENGINEER_CALL_BUDGETS', 'TRAIN_ENGINEER_CALL_BUDGETS'):
        assert getattr(p, name)[config] == getattr(p, name)[parent] + p.MAX_CHANGES * (2 * p.FAULT_REPAIRS + 1)
    expected = v29_limits.v291_role_calls(p, config)
    assert expected == {'engineer': 270, 'leakage': 126, 'describer': 18}
    assert {key: smoke.max_role_calls(config)[key] for key in expected} == expected
    ordinary = reservation(p.ROLE_INPUT_BYTES, p.ROLE_MAX_TOKENS)
    engineer = reservation(p.ROLE_INPUT_BYTES + 16000, p.ENGINEER_MAX_TOKENS[config])
    assert p.CONFIG_ROLE_CAPS[config]['engineer'] == 270 * engineer + 144 * ordinary + engineer
    assert p.CONFIG_ROLE_CAPS[config]['engineer'] == 428351616
    assert p.CONFIG_GLM_CAP[config] == p.CONFIG_GLM_CAP[parent] + 428351616 - p.CONFIG_ROLE_CAPS[parent]['engineer']
    schedule = p.CONFIG_SCHEDULE_CELLS[config][bench]
    assert schedule['confirm'] == {bench: (0, 480)}
    assert schedule['selftest'] == {bench: (0, 1360 if bench == 'alfworld' else 720)}
    roles = smoke.max_role_calls(config)
    measured = {role: {'calls': 1, 'tokens': 100, 'per_call': 100, 'request_bytes': 220000} for role in roles}
    # Maximum reservation settlement still fits the engineer, including the next call.
    for role in ('engineer', 'leakage', 'describer'):
        measured[role].update(tokens=engineer if role == 'engineer' else ordinary,
                             per_call=engineer if role == 'engineer' else ordinary)
    projected = smoke.glm_projection(measured, config)
    scope = budgets.glm_scopes('D', 'engineer', bench, 1)[-1]
    assert projected[scope]['fits'] and projected[scope]['needed'] == projected[scope]['cap']
    assert v29_limits.identity(p, config)['fault_feedback']['train_call_budget'] == 41
    for mode in (False, True):
        text = engineer_v291.system(config, train=mode)
        assert len(text.encode()) + max(len(pin['text'].encode()) for key, pin in engineer_v291.prompt_pins().items()
                                      if '/' not in key) <= 16000
    assert smoke.engineer_request_floor(config) == 236000


@pytest.mark.parametrize('parent', [p.ZEBRA_PC_V7, p.ALFWORLD_V4])
def test_parent_registrations_prompts_budgets_remain_byte_identical(parent):
    baseline = json.loads((Path(__file__).parent / 'fixtures' / 'execskill' / 'v291_parents_before.json').read_text())
    found = manifest._plain({'features': {key: getattr(p, key).get(parent, {'unregistered': True}) for key in FEATURES},
        'registered': manifest.registered(parent), 'prompts': manifest.prompt_sha(parent),
        'roles': manifest.role_settings(parent), 'budgets': {c: budgets.chain_caps(c, parent) for c in p.CHAINS},
        'call_budgets': [p.ENGINEER_CALL_BUDGETS[parent], p.TRAIN_ENGINEER_CALL_BUDGETS[parent]]})
    assert found == baseline[parent]


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_manifest_prompt_and_fault_registration_pins_are_configuration_specific(config, parent, tag, bench):
    pins = manifest.prompt_sha(config)
    assert pins['v29'] == manifest.prompt_sha(parent)['v29']
    assert pins['engineer'] == hashlib.sha256(engineer_v291.system(config, train=False).encode()).hexdigest()
    assert pins['v291'] == engineer_v291.prompt_pins()
    features = manifest.outcome_engineer_features(config)
    assert features['train_patience'] == 4 and features['fault_repair']['calls_per_change'] == 2
    assert 'fault_repair' not in manifest.outcome_engineer_features(parent)
    assert confirm.FRESHNESS[config] == p.CONFIRM_FRESHNESS[config]
    assert p.CONFIRM_FRESHNESS[p.ZEBRA_PC_V8] == p.CONFIRM_FRESHNESS[p.ZEBRA_PC_V7]
    assert p.ACCEPT_FRESHNESS[p.ZEBRA_PC_V8] == p.ACCEPT_FRESHNESS[p.ZEBRA_PC_V7]
    assert p.CONFIRM_FRESHNESS[p.ALFWORLD_V5] == 'alfworld_split_v1_confirm_spare_rooms_reused_after_alfworld_v4'
    assert p.ACCEPT_FRESHNESS[p.ALFWORLD_V5] == 'alfworld_split_v1_slices_reused_after_alfworld_v4'


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_cli_routes_and_fresh_manifest_paths(config, parent, tag, bench, tmp_path):
    from scripts.run_execskill import parser
    for command in (('zpc-s0', 'zpc-smoke') if bench == 'zebralogic' else ('alf-s0', 'alf-smoke')):
        assert config in next(action for action in parser()._subparsers._group_actions[0].choices[command]._actions
                              if action.dest == 'configuration').choices
    assert routes.current(tmp_path, configuration=config) == 'B'
    root, manifest_path = ((p.ZEBRA_PC_V8_ROOT, p.ZEBRA_PC_V8_MANIFEST) if bench == 'zebralogic'
                           else (p.ALFWORLD_V5_ROOT, p.ALFWORLD_V5_MANIFEST))
    assert manifest_path == root + '-manifest.json'
    if bench == 'alfworld':
        assert manifest.alfworld_registration_key(config) == 'alfworld_v5'
        command = parser()._subparsers._group_actions[0].choices['alf-confirm-views']
        assert config in next(action for action in command._actions if action.dest == 'configuration').choices


def test_alf_v5_confirm_prereset_is_fresh_and_parent_pins_remain_distinct(tmp_path, monkeypatch):
    from tests.test_execskill_v29_confirm_views import authored_preparation
    from skillopt.execskill import alf_confirm_views as cv, alf_smoke
    preparation, root, pool, runtime, calls = authored_preparation(tmp_path / 'source', monkeypatch)
    target = tmp_path / 'v291-confirm.json'
    result = cv.prepare(target, configuration=p.ALFWORLD_V5, preparation_file=preparation, data_root=root)
    assert len(calls) == 80 and result['configuration'] == p.ALFWORLD_V5
    assert result['confirm']['freshness'] == p.CONFIRM_FRESHNESS[p.ALFWORLD_V5]
    assert cv.load_for_preparation(target, configuration=p.ALFWORLD_V5,
        imported=alf_smoke.preparation(preparation), items=pool) == result
    with pytest.raises(ValueError, match='configuration|configured'):
        cv.load_for_preparation(target, configuration=p.ALFWORLD_V4,
            imported=alf_smoke.preparation(preparation), items=pool)


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V8, p.ALFWORLD_V5])
def test_child_full_manifest_round_trip_binds_new_prompts_confirm_and_route(tmp_path, monkeypatch, configuration):
    from tests.test_execskill_v29_manifest_smoke import test_complete_manifest_pins_exact_practice_ids_prompts_and_models
    test_complete_manifest_pins_exact_practice_ids_prompts_and_models(tmp_path, monkeypatch, configuration)
