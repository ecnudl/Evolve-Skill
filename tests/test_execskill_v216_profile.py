"""Bounded repair-cycle registration; authored checks and frozen parent captures only."""
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

CHILD, PARENT = p.ZEBRA_PC_V15, p.ZEBRA_PC_V14
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v216_parents_before.json'
SNAPSHOT = json.loads(CAPTURE.read_text())


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_all_37_preexisting_identities_keep_exact_prompts_caps_records_and_registration(name, monkeypatch):
    monkeypatch.setattr(parent_tests, 'SNAPSHOT', SNAPSHOT)
    parent_tests.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_capture_and_every_older_profile_table_are_unchanged():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == '4d75edd1f0843f57b92dd248e5917724b64d9eccb363a50c1049f0f51e5ce538'
    assert len(SNAPSHOT['configurations']) == 37
    assert {n for n in p.CONFIGURATIONS if not p.is_v220(n) and not p.is_v217(n) and not p.is_implant_v5(n) and not p.is_v218(n)} - set(SNAPSHOT['configurations']) == {CHILD}
    for name, tables in SNAPSHOT['profile_tables'].items():
        found = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(found, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_child_inherits_all_v14_gates_and_only_adds_bounded_cycle():
    assert p.is_v216(CHILD) and p.is_v215(CHILD) and p.is_v215(PARENT)
    assert not any(p.is_v216(name) for name in SNAPSHOT['configurations'])
    assert p.V216_INERT_REPAIRS == 3 and p.V216_AUDIT_FIXES == 2
    assert p.INERT_REPAIRS == 1 and p.FAULT_REPAIRS == 2
    assert all(fn(CHILD) for fn in (p.is_zebra, p.is_v23, p.is_v24, p.is_v25, p.is_v26,
        p.is_v27, p.is_v28, p.is_v29, p.is_v291, p.is_v292, p.is_v293, p.is_v294,
        p.is_v295, p.is_v212, p.is_zebra_fc))
    assert not any(fn(CHILD) for fn in (p.is_alfworld, p.is_v296, p.is_v297,
        p.is_v210, p.is_v211, p.is_v213, p.is_v214))
    assert p.launchable_chains(CHILD) == ('D',)
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == (p.ZEBRA,)
    assert p.read_arms_of(CHILD) == ('F', 'C')
    assert p.train_rounds(CHILD) == 6 and p.train_patience(CHILD) == 4
    assert step.training_units(CHILD) == step.training_units(PARENT)
    changed = {'RUN_ROOTS', 'CHAIN_NAMESPACES', 'REAL_RUN_EVIDENCE', 'ACCEPT_FRESHNESS',
               'CONFIRM_FRESHNESS', 'ENGINEER_CALL_BUDGETS', 'TRAIN_ENGINEER_CALL_BUDGETS',
               'CONFIG_ROLE_CAPS', 'CONFIG_GLM_CAP'}
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and PARENT in table and key not in changed:
            assert table[CHILD] == table[PARENT], key
            if isinstance(table[PARENT], (dict, list)):
                assert table[CHILD] is not table[PARENT], key


def test_new_root_evidence_and_freshness_preserve_single_prior_holdout_read():
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261031-zebra-pc-v15'
    assert p.ZEBRA_PC_V15_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-zpc15', 'D': 'D-zpc15'}
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'zebra_pc_v15_real_run'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[CHILD], {}))
    assert p.ACCEPT_FRESHNESS[CHILD] == p.ACCEPT_FRESHNESS[PARENT] + '_and_zebra_pc_v14'
    assert confirm.FRESHNESS[CHILD] == p.CONFIRM_FRESHNESS[CHILD] == p.CONFIRM_FRESHNESS[PARENT] + '_and_zebra_pc_v14'
    assert p.ZEBRA_PC_V15_TEST_FRESHNESS == p.ZEBRA_PC_V14_TEST_FRESHNESS
    features = manifest.outcome_engineer_features(CHILD)
    assert features['test_freshness'] == 'zebra_split_v1_holdout_after_one_zebra_hp_v3r4_v213_read'
    assert features['diagnostics'] == diagnostics.identity()
    assert features['inert_repair']['calls_per_change'] == 3
    assert features['repair_cycle'] == {
        'inert_repairs': 3, 'audit_fixes': 2, 'audits': 3,
        'replay_evidence': 'current_attempt;rejected_reply_restores_previous',
        'survival': 'passed_fatal_checks_and_not_inert_and_not_deferred_and_last_audit_not_confirmed',
    }
    assert 'repair_cycle' not in manifest.outcome_engineer_features(PARENT)


@pytest.mark.parametrize('mode', ['single', 'train'])
@pytest.mark.parametrize('purpose', engineer_v215.PURPOSES)
def test_every_inherited_system_prompt_is_byte_identical(mode, purpose):
    old = SimpleNamespace(configuration=PARENT, bench=p.ZEBRA, mode=mode)
    new = SimpleNamespace(configuration=CHILD, bench=p.ZEBRA, mode=mode)
    user = {'request': purpose, 'evidence': {}}
    assert engineer._legacy_system(new, user) == engineer._legacy_system(old, user)
    assert engineer_v215.system(CHILD, train=mode == 'train') == engineer_v215.system(PARENT, train=mode == 'train')


def test_manifest_adds_only_exact_audit_fix_paragraph_pin():
    from skillopt.execskill import engineer_v216
    expected = deepcopy(manifest.prompt_sha(PARENT))
    expected['v216'] = engineer_v216.prompt_pins()
    assert manifest.prompt_sha(CHILD) == expected
    text = ('Fix every confirmed finding. Do not make the program silent on every item: where the program '
            'cannot verify that every condition of an item was understood, return no note for that item only '
            'and say why in `diagnostics`.')
    assert expected['v216'] == {'audit_fix_paragraph': {
        'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}}
    assert expected['v215'] == manifest.prompt_sha(PARENT)['v215']


def test_exact_extra_call_reservations_leave_solver_and_parent_caps_unchanged():
    rounds, changes = p.train_rounds(CHILD), p.MAX_CHANGES
    assert (rounds, changes) == (6, 3)
    extras = (p.V216_INERT_REPAIRS - p.INERT_REPAIRS) + (p.V216_AUDIT_FIXES - 1)
    assert extras == 3
    assert p.ENGINEER_CALL_BUDGETS[CHILD] == p.ENGINEER_CALL_BUDGETS[PARENT] + changes * extras == 40
    assert p.TRAIN_ENGINEER_CALL_BUDGETS[CHILD] == p.TRAIN_ENGINEER_CALL_BUDGETS[PARENT] + changes * extras == 50
    old, new = smoke.max_role_calls(PARENT), smoke.max_role_calls(CHILD)
    assert new == {**old, 'engineer': 324, 'leakage': 180, 'audit_g': 780, 'audit_d': 780}
    extra_requests = rounds * changes * extras
    assert extra_requests == 54
    assert v29_limits.engineer_input_bytes(p, CHILD) == v29_limits.engineer_input_bytes(p, PARENT) == 284000
    assert smoke.engineer_request_floor(CHILD) == smoke.engineer_request_floor(PARENT) == 300000
    engineer_delta = extra_requests * (reservation(300000, 32768) + reservation(p.ROLE_INPUT_BYTES, p.ROLE_MAX_TOKENS))
    assert engineer_delta == 123158016
    judge_delta = rounds * changes * v29_limits.prompts_per_audit(p.ZEBRA) * (1 + v29_limits.FORMAT_RETRIES)
    assert judge_delta == 180
    judge_tokens = judge_delta * reservation(p.ROLE_INPUT_BYTES, v29_limits.JUDGE_MAX_TOKENS)
    assert judge_tokens == 164666880
    assert p.CONFIG_ROLE_CAPS[CHILD] == {**p.CONFIG_ROLE_CAPS[PARENT], 'engineer': 620885632,
                                       'audit_g': 714471296, 'audit_d': 714471296}
    assert p.CONFIG_ROLE_CAPS[CHILD]['engineer'] == v29_limits.v291_engineer_cap(p, CHILD)
    assert p.CONFIG_GLM_CAP[CHILD] == p.CONFIG_GLM_CAP[PARENT] + engineer_delta + 2 * judge_tokens == 2147428224
    assert budgets.chain_caps('D', CHILD)['overall'] == 2397028224
    assert p.CONFIGURATIONS[CHILD] == p.CONFIGURATIONS[PARENT]
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == 249600000
    assert p.CONFIGURATIONS[CHILD]['test_read_cap'] == 34000000
    assert p.CONFIG_STEP_CAPS[CHILD] == p.CONFIG_STEP_CAPS[PARENT]
    assert p.CONFIG_SCHEDULE_CELLS[CHILD] == p.CONFIG_SCHEDULE_CELLS[PARENT]
    identity = v29_limits.identity(p, CHILD)
    assert identity['audit1_passes'] == 3 and identity['calls_per_judge'] == 780
    assert identity['fault_feedback']['single_call_budget'] == 40
    assert identity['fault_feedback']['train_call_budget'] == 50
    assert v29_limits.identity(p, PARENT)['audit1_passes'] == 2


def test_full_request_projection_fits_exact_engineer_and_each_judge_role_cap():
    measured = {role: {'calls': 1,
        'per_call': reservation(300000 if role == 'engineer' else p.ROLE_INPUT_BYTES,
            32768 if role == 'engineer' else 8192 if role.startswith('audit_') else p.ROLE_MAX_TOKENS),
        'request_bytes': 300000 if role == 'engineer' else p.ROLE_INPUT_BYTES}
        for role in smoke.max_role_calls(CHILD)}
    projected = smoke.glm_projection(measured, CHILD)
    scope = budgets.glm_scopes('D', 'engineer', p.ZEBRA, 1)[-1]
    assert projected[scope]['needed'] == projected[scope]['cap'] == 620885632
    assert projected[scope]['fits']
    for chain in ('G', 'D'):
        scope = budgets.audit_scopes('D', chain, p.ZEBRA, 1)[-1]
        assert projected[scope]['needed'] == projected[scope]['cap'] == 714471296
        assert projected[scope]['fits']


def test_cli_accepts_child_for_every_prep_and_smoke_entry_and_keeps_defaults(tmp_path, monkeypatch):
    from scripts.run_execskill import parser
    from tests.test_execskill_v29_profile import test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 's0', 'manifest', 'smoke'):
        arg = next(a for a in commands['zpc-' + suffix]._actions if a.dest == 'configuration')
        assert CHILD in arg.choices and arg.default == p.ZEBRA_PC_V1
    for configuration in (CHILD, PARENT):
        parsed = parser().parse_args(['test-read-estimate', '--smoke', str(tmp_path / 'authored.json'),
                                     '--out', str(tmp_path / configuration),
                                     '--configuration', configuration])
        assert parsed.configuration == configuration
    assert parser().parse_args(['run', '--manifest', p.ZEBRA_PC_V15_MANIFEST, '--chain', 'D']).chain == 'D'
    assert parser().parse_args(['recover', '--attempt', 'authored-attempt',
                               '--decision', 'authored-decision']).attempt == 'authored-attempt'
    test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized(tmp_path, monkeypatch, CHILD)


def test_child_reuses_v14_worker_while_all_older_worker_pins_are_exact():
    from skillopt.execskill.sandbox import client as sandbox
    old = 'bb1ccc0d90cafbda1f842569454ec676a8329d721a423246d92572632cf4ea0d'
    assert sandbox.worker_sha256() == old
    assert sandbox.worker_sha256(configuration=CHILD) == sandbox.worker_sha256(configuration=PARENT) != old
    assert all(sandbox.worker_sha256(configuration=name) == old
               for name in SNAPSHOT['configurations'] if name != PARENT)
