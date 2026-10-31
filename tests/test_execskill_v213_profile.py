"""Fixed-import identity, caps and all 34 pre-edit configuration identities."""
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.execskill import budgets, manifest, profiles as p, smoke, step
from tests import test_execskill_v212_profile as parent_tests
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CAPTURE = Path(__file__).parent / 'fixtures/execskill/v213_parents_before.json'
SNAPSHOT = json.loads(CAPTURE.read_text())
CHILD = p.ZEBRA_HP_V3R4


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_all_34_preexisting_identities_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parent_tests, 'SNAPSHOT', SNAPSHOT)
    parent_tests.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_preedit_capture_and_every_historical_table_are_unchanged():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == '6b8310776ba30b207ac59e56193ff1226cce131fdee2343ed7318d51c067b7a3'
    assert len(SNAPSHOT['configurations']) == 34
    assert {n for n in p.CONFIGURATIONS if not p.is_v214(n) and not p.is_v215(n) and not p.is_v217(n)} - set(SNAPSHOT['configurations']) == {CHILD}
    for name, tables in SNAPSHOT['profile_tables'].items():
        found = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(found, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_import_identity_and_freshness_are_separate_from_method_evidence():
    assert p.is_zebra(CHILD) and p.is_v29(CHILD) and p.is_v213(CHILD) and not p.is_v212(CHILD)
    assert p.LEARNING[CHILD] == 'import' and step.training_units(CHILD) == ()
    assert p.ACCEPT_RULES[CHILD] is None
    assert p.train_rounds(CHILD) == p.train_patience(CHILD) == 0
    assert p.launchable_chains(CHILD) == ('D',)
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-zhp', 'D': 'D-zhp'}
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261030-zebra-hp-v3r4'
    assert p.ZEBRA_HP_V3R4_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'zebra_hp_v3r4_test_read'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[CHILD], {}))
    assert p.ACCEPT_FRESHNESS[CHILD] == p.CONFIRM_FRESHNESS[CHILD] == 'not_applicable_fixed_post_hoc_v3r4_import'
    assert p.read_arms_of(CHILD) == ('F', 'C') and p.estimate_arms(CHILD) == 1
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == (p.ZEBRA,)
    assert p.TEST_READ_CELLS[CHILD] == p.TEST_READ_CELLS[p.ZEBRA_PC_V13] == {p.ZEBRA: (200, 200)}
    assert not p.PLACEBO_ARMS[CHILD] and not p.TEST_WITHHOLDING[CHILD] and not p.STAGE_READ[CHILD]
    assert manifest.outcome_engineer_features(CHILD)['audit'] == 'not_run_fixed_post_hoc_import'
    assert manifest.prompt_sha(CHILD) == manifest.prompt_sha(p.ZEBRA_PC_V13)


def test_caps_keep_full_read_plus_only_existing_first_response_headroom():
    assert p.CONFIGURATIONS[CHILD]['test_read_cap'] == 34_000_000
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == 34_000_000 + p.FIRST_CALL_CAP == 35_100_000
    assert p.CONFIGURATIONS[CHILD]['redo_reserve'] == 0
    assert p.CONFIG_STEP_CAPS[CHILD] == p.CONFIG_SCHEDULE_CELLS[CHILD] == {}
    assert not any(p.CONFIG_ROLE_CAPS[CHILD].values()) and p.CONFIG_GLM_CAP[CHILD] == 0
    assert p.ENGINEER_CALL_BUDGETS[CHILD] == p.TRAIN_ENGINEER_CALL_BUDGETS[CHILD] == 0
    assert not any(smoke.max_role_calls(CHILD).values())
    assert budgets.chain_caps('D', CHILD) == {'overall': 35_100_000, 'D:solver': 35_100_000, 'D:test': 34_000_000}
    assert budgets.first_call_caps('D') == {'D:confirm': 1_100_000}
    assert 'G' not in p.launchable_chains(CHILD)


def test_cli_choices_and_inherited_solver_route(tmp_path, monkeypatch):
    from scripts.run_execskill import parser
    from tests import test_execskill_v29_profile as historical
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 's0', 'manifest', 'smoke'):
        arg = next(a for a in commands['zpc-' + suffix]._actions if a.dest == 'configuration')
        assert CHILD in arg.choices and arg.default == p.ZEBRA_PC_V1
    historical.test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized(tmp_path, monkeypatch, CHILD)
