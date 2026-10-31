"""v2.15 registration, prompt and cap checks; no model or private data access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.coevo5.ledger import reservation
from skillopt.execskill import (budgets, confirm, diagnostics, engineer, engineer_v215,
                               manifest, profiles as p, smoke, step, v29_limits)
from tests import test_execskill_v212_profile as parent_tests
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CHILD, PARENT = p.ZEBRA_PC_V14, p.ZEBRA_PC_V13
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v215_parents_before.json'
SNAPSHOT = json.loads(CAPTURE.read_text())


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_all_36_preexisting_identities_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parent_tests, 'SNAPSHOT', SNAPSHOT)
    parent_tests.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_capture_and_every_old_profile_table_remain_exact():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == '473ca151f00d121f2277f39bdda7e260a7dc7e23a49ab3b6a67cebd2f655d4b4'
    assert len(SNAPSHOT['configurations']) == 36
    assert {name for name in p.CONFIGURATIONS if not p.is_v216(name) and not p.is_v217(name) and not p.is_implant_v5(name) and not p.is_v218(name)} - set(SNAPSHOT['configurations']) == {CHILD}
    for name, tables in SNAPSHOT['profile_tables'].items():
        found = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(found, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_new_identity_inherits_complete_v13_method_and_no_mixed_or_fixed_import_behavior():
    assert p.is_v215(CHILD) and p.is_v212(CHILD) and p.is_zebra_fc(CHILD)
    assert all(fn(CHILD) for fn in (p.is_zebra, p.is_v23, p.is_v24, p.is_v25, p.is_v26,
                                   p.is_v27, p.is_v28, p.is_v29, p.is_v291, p.is_v292,
                                   p.is_v293, p.is_v294, p.is_v295))
    assert not any(fn(CHILD) for fn in (p.is_alfworld, p.is_v296, p.is_v297, p.is_v210,
                                       p.is_v211, p.is_v213, p.is_v214))
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == (p.ZEBRA,)
    assert p.launchable_chains(CHILD) == ('D',)
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261031-zebra-pc-v14'
    assert p.ZEBRA_PC_V14_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-zpc14', 'D': 'D-zpc14'}
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'zebra_pc_v14_real_run'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[CHILD], {}))
    assert p.read_arms_of(CHILD) == ('F', 'C') and p.estimate_arms(CHILD) == 1
    assert not p.PLACEBO_ARMS[CHILD] and not p.TEST_WITHHOLDING[CHILD] and not p.STAGE_READ[CHILD]
    assert p.train_rounds(CHILD) == 6 and p.train_patience(CHILD) == 4
    assert p.SLICES[p.ZEBRA] == {'run': (60, 1), 'accept': (100, 1), 'blocks': 1}
    assert p.ACCEPT_RULES[CHILD] == p.ACCEPT_RULES[PARENT]
    assert p.ACCEPT_RULES[CHILD]['name'] == 'practical-v2-12-pooled'
    assert p.uses_v212(CHILD, p.ZEBRA) and p.uses_pooled_j1(CHILD, p.ZEBRA)
    assert step.training_units(CHILD) == step.training_units(PARENT)
    changed = {'RUN_ROOTS', 'CHAIN_NAMESPACES', 'REAL_RUN_EVIDENCE', 'ACCEPT_FRESHNESS',
               'CONFIRM_FRESHNESS', 'CONFIG_ROLE_CAPS', 'CONFIG_GLM_CAP'}
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and PARENT in table and key not in changed:
            assert table[CHILD] == table[PARENT], key
            if isinstance(table[PARENT], (dict, list)):
                assert table[CHILD] is not table[PARENT], key


def test_practice_and_holdout_exposure_are_explicit_in_pinned_identity():
    assert p.ACCEPT_FRESHNESS[CHILD] == 'zebra_split_v1_accept_after_zebra_pc_v9_v10_v11_v12_v13_upper_bound_probes_and_main_v5_D'
    assert confirm.FRESHNESS[CHILD] == p.CONFIRM_FRESHNESS[CHILD]
    assert 'v9_v10_v11_v12_v13_and_main_v5_D' in confirm.FRESHNESS[CHILD]
    found = manifest.outcome_engineer_features(CHILD)
    assert found['diagnostics'] == diagnostics.identity()
    assert found['test_freshness'] == p.ZEBRA_PC_V14_TEST_FRESHNESS
    assert 'one_zebra_hp_v3r4_v213_read' in found['test_freshness']
    assert manifest.zebra_features(CHILD)['outcome_engineer'] == found


@pytest.mark.parametrize('mode', ['single', 'train'])
@pytest.mark.parametrize('purpose', engineer_v215.PURPOSES)
def test_actual_dispatch_appends_only_new_generic_section_and_pins_it(mode, purpose):
    old = SimpleNamespace(configuration=PARENT, bench=p.ZEBRA, mode=mode)
    new = SimpleNamespace(configuration=CHILD, bench=p.ZEBRA, mode=mode)
    user = {'request': purpose, 'evidence': {}}
    expected = engineer._legacy_system(old, user) + engineer_v215.DIAGNOSTICS_SECTION
    actual = engineer._legacy_system(new, user)
    assert actual == expected == engineer_v215.dispatch(new, user)
    assert actual.endswith(engineer_v215.DIAGNOSTICS_SECTION)
    assert len(actual.encode()) <= v29_limits.V291_ENGINEER_SYSTEM_BYTES
    pin = manifest.prompt_sha(CHILD)['v215'][mode + '/' + purpose]
    assert pin == {'text': actual, 'sha256': hashlib.sha256(actual.encode()).hexdigest()}


def test_new_prompt_pins_keep_every_other_parent_prompt_identical():
    parent, child = manifest.prompt_sha(PARENT), manifest.prompt_sha(CHILD)
    expected = deepcopy(parent)
    expected['engineer'] = hashlib.sha256(engineer_v215.system(CHILD, train=False).encode()).hexdigest()
    expected['v2']['engineer'] = hashlib.sha256(engineer_v215.system(CHILD, train=True).encode()).hexdigest()
    expected['v215'] = engineer_v215.prompt_pins()
    assert child == expected
    section = engineer_v215.DIAGNOSTICS_SECTION
    assert all(text in section for text in ('5 strings', '240 characters', 'Only the engineer',
                                            'every condition', 'only one consistent', 'return no note'))
    assert 'ZebraLogic' not in section


def test_only_engineer_input_reservation_increases_all_other_caps_are_exact_parent():
    assert diagnostics.INPUT_BYTES == 64000
    assert v29_limits.engineer_input_bytes(p, PARENT) == p.ROLE_INPUT_BYTES == 220000
    assert v29_limits.engineer_input_bytes(p, CHILD) == 284000
    assert smoke.engineer_request_floor(PARENT) == 236000
    assert smoke.engineer_request_floor(CHILD) == 300000
    assert smoke.max_role_calls(CHILD) == smoke.max_role_calls(PARENT)
    assert smoke.max_role_calls(CHILD)['engineer'] == 270
    old = reservation(236000, 32768)
    new = reservation(300000, 32768)
    extra = 271 * (new - old)
    assert (old, new, extra) == (1077120, 1333120, 69376000)
    assert p.CONFIG_ROLE_CAPS[CHILD] == {**p.CONFIG_ROLE_CAPS[PARENT], 'engineer': 497727616}
    assert p.CONFIG_ROLE_CAPS[CHILD]['engineer'] == v29_limits.v291_engineer_cap(p, CHILD)
    assert p.CONFIG_GLM_CAP[CHILD] == p.CONFIG_GLM_CAP[PARENT] + extra == 1694936448
    assert p.CONFIGURATIONS[CHILD] == p.CONFIGURATIONS[PARENT]
    assert p.CONFIG_STEP_CAPS[CHILD] == p.CONFIG_STEP_CAPS[PARENT]
    assert p.CONFIG_SCHEDULE_CELLS[CHILD] == p.CONFIG_SCHEDULE_CELLS[PARENT]
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == 249600000
    assert p.CONFIGURATIONS[CHILD]['test_read_cap'] == 34000000
    assert p.CONFIGURATIONS[CHILD]['redo_reserve'] == 43300000
    assert budgets.chain_caps('D', CHILD)['overall'] == 1944536448
    assert p.ENGINEER_CALL_BUDGETS[CHILD] == 31 and p.TRAIN_ENGINEER_CALL_BUDGETS[CHILD] == 41
    registered = v29_limits.identity(p, CHILD)['fault_feedback']
    assert registered['engineer_payload_bytes_allowance'] == 284000
    assert registered['diagnostics_bytes_allowance'] == 64000
    assert registered['engineer_cap'] == 497727616


def test_cli_choices_and_inherited_northgate_route(tmp_path, monkeypatch):
    from scripts.run_execskill import parser
    from tests.test_execskill_v29_profile import test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 's0', 'manifest', 'smoke'):
        arg = next(a for a in commands['zpc-' + suffix]._actions if a.dest == 'configuration')
        assert CHILD in arg.choices and arg.default == p.ZEBRA_PC_V1
    test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized(tmp_path, monkeypatch, CHILD)


def test_measured_projection_reserves_full_new_engineer_input_without_changing_role_calls():
    measured = {role: {'calls': 1,
        'per_call': reservation(300000 if role == 'engineer' else p.ROLE_INPUT_BYTES,
            32768 if role == 'engineer' else 8192 if role.startswith('audit_') else p.ROLE_MAX_TOKENS),
        'request_bytes': 300000 if role == 'engineer' else p.ROLE_INPUT_BYTES}
        for role in smoke.max_role_calls(CHILD)}
    projected = smoke.glm_projection(measured, CHILD)
    entry = projected[budgets.glm_scopes('D', 'engineer', p.ZEBRA, 1)[-1]]
    assert entry['reservation'] == 1333120
    assert entry['needed'] == entry['cap'] == 497727616 and entry['fits']
    assert entry['needed'] > p.CONFIG_ROLE_CAPS[PARENT]['engineer']
    assert entry['roles'] == ['engineer', 'describer', 'leakage'] and entry['assumed'] == []


def test_every_older_configuration_keeps_the_exact_parent_worker_source_hash():
    from skillopt.execskill.sandbox import client as sandbox
    old = 'bb1ccc0d90cafbda1f842569454ec676a8329d721a423246d92572632cf4ea0d'
    assert sandbox.worker_sha256() == old
    assert all(sandbox.worker_sha256(configuration=name) == old for name in SNAPSHOT['configurations'])
    assert sandbox.worker_sha256(configuration=CHILD) != old


@pytest.mark.parametrize('mode', ['single', 'train'])
def test_inert_system_suffix_uses_original_causes_without_consuming_diagnostics_payload(mode):
    original = {'request': 'inert_repair', 'evidence': {'empty_notes': {'fired': 60, 'empty': 60}}}
    user = deepcopy(original)
    user['evidence']['engineer_diagnostics'] = {'texts': [{'text': 'Unable to interpret this condition.'}],
                                                'items': [{'task_id': 'authored', 'text_indices': [0]}]}
    before = deepcopy(user)
    parent = SimpleNamespace(configuration=PARENT, bench=p.ZEBRA, mode=mode)
    child = SimpleNamespace(configuration=CHILD, bench=p.ZEBRA, mode=mode)
    expected = engineer._legacy_system(parent, original) + engineer_v215.DIAGNOSTICS_SECTION
    assert engineer._legacy_system(child, user) == expected
    assert user == before
    assert 'because empty_notes, engineer_diagnostics' not in expected
