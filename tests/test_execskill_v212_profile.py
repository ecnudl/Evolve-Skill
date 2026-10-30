"""Zebra v13 identities and the full pre-edit historical configuration capture."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.coevo5.outcomes import Verdict
from skillopt.execskill import (audit, budgets, engineer, instruction_start, judge, manifest,
                               profiles as p, protocol, routes, smoke, step)
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_regression import FEATURES

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = json.loads((ROOT / 'tests/fixtures/execskill/v212_parents_before.json').read_text())


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name):
    before = SNAPSHOT['configurations'][name]
    found = manifest._plain({'features': {key: getattr(p, key).get(name, {'unregistered': True}) for key in FEATURES},
        'registered': manifest.registered(name), 'prompts': manifest.prompt_sha(name),
        'roles': manifest.role_settings(name), 'budgets': {c: budgets.chain_caps(c, name) for c in p.CHAINS},
        'call_budgets': [p.ENGINEER_CALL_BUDGETS[name], p.TRAIN_ENGINEER_CALL_BUDGETS[name]],
        'units': list(step.training_units(name)), 'runtime': before['runtime'],
        'k1_judge': {label: judge.judge('alfworld', {'game_file': 'authored'}, {}, case['prediction'],
            runtime=before['runtime'], score=case['score'], verdict=Verdict(**case['verdict']))
            for label, case in SNAPSHOT['k1_episodes'].items()},
        'audit_views': {key: audit.public_view('alfworld', view)
                        for key, view in SNAPSHOT['audit_public_inputs'].items()},
        'audit_keys': {key: audit.situation_key({'item': SNAPSHOT['audit_item'], 'step': int(key),
                        'view': audit.public_view('alfworld', view)})
                       for key, view in SNAPSHOT['audit_public_inputs'].items()}})
    encoded = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert encoded(found) == encoded(before)



def test_every_historical_profile_table_is_byte_identical():
    assert len(SNAPSHOT['configurations']) == 33
    assert {n for n in p.CONFIGURATIONS if not p.is_v213(n) and not p.is_v214(n) and not p.is_v215(n)} - set(SNAPSHOT['configurations']) == {p.ZEBRA_PC_V13}
    for name, tables in SNAPSHOT['profile_tables'].items():
        found = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(found, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_v13_inherits_only_the_zebra_v12_family():
    name, parent = p.ZEBRA_PC_V13, p.ZEBRA_PC_V12
    assert all(fn(name) for fn in (p.is_zebra, p.is_v23, p.is_v24, p.is_v25, p.is_v26,
        p.is_v27, p.is_v28, p.is_v29, p.is_v291, p.is_v292, p.is_v293, p.is_v294, p.is_v295, p.is_v212))
    assert not any(fn(name) for fn in (p.is_alfworld, p.is_v296, p.is_v297, p.is_v210, p.is_v211))
    assert p.train_rounds(name) == 6 and p.train_patience(name) == 4
    assert p.train_rounds(parent) == 10 and p.train_patience(parent) == 8
    assert p.launchable_chains(name) == ('D',)
    assert p.active_benches(name) == p.read_benches(name) == (p.ZEBRA,)
    assert p.RUN_ROOTS[name] == '/data/execskill-20261030-zebra-pc-v13'
    assert p.ZEBRA_PC_V13_MANIFEST == p.RUN_ROOTS[name] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[name] == {'G': 'G-zpc13', 'D': 'D-zpc13'}
    assert set(p.CHAIN_NAMESPACES[name].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.REAL_RUN_EVIDENCE[name] == 'zebra_pc_v13_real_run'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[name], {}))
    assert p.read_arms_of(name) == ('F', 'C')
    assert not p.PLACEBO_ARMS[name] and not p.TEST_WITHHOLDING[name] and not p.STAGE_READ[name]
    assert p.uses_pooled_j1(name, p.ZEBRA)
    assert not p.uses_readable_alf_format(name, 'alfworld') and not p.uses_episode_audit(name, 'alfworld')
    assert p.ACCEPT_RULES[name] == {**p.ACCEPT_RULES[parent], 'name': 'practical-v2-12-pooled'}
    assert p.ACCEPT_FRESHNESS[name] == 'zebra_split_v1_slices_accept_after_zebra_pc_v9_v12_and_upper_bound_probes'
    assert p.CONFIRM_FRESHNESS[name] == 'zebra_split_v1_confirm_after_zebra_pc_v9_v12'
    from skillopt.execskill import confirm
    assert confirm.FRESHNESS[name] == p.CONFIRM_FRESHNESS[name]
    changed = {'CONFIGURATIONS','PILOTS','CONFIG_STEP_CAPS','CONFIG_SCHEDULE_CELLS','CONFIG_ROLE_CAPS',
        'CONFIG_GLM_CAP','TEST_READ_CELLS','ACCEPT_RULES','REAL_RUN_EVIDENCE','RUN_ROOTS','CHAIN_NAMESPACES',
        'ACCEPT_FRESHNESS','CONFIRM_FRESHNESS','PLACEBO_ARMS','TEST_WITHHOLDING'}
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and parent in table and key not in changed:
            assert table[name] == table[parent], key
            if isinstance(table[parent], (dict, list)):
                assert table[name] is not table[parent], key


def test_prompt_changes_only_rounds_and_patience_and_pins_actual_text():
    from skillopt.execskill import engineer_v295, v29_limits
    name, parent = p.ZEBRA_PC_V13, p.ZEBRA_PC_V12
    pins = manifest.prompt_sha(name)
    for train in (False, True):
        expected = engineer_v295.system(parent, train=train).replace(
            '10 training rounds, patience 8', '6 training rounds, patience 4').replace(
            'patience 8 over at most 10 rounds', 'patience 4 over at most 6 rounds')
        actual = engineer_v295.system(name, train=train)
        assert actual == expected
        assert hashlib.sha256(actual.encode()).hexdigest() == (pins['v2']['engineer'] if train else pins['engineer'])
    assert all(pins[key] == manifest.prompt_sha(parent)[key] for key in ('v29','v291','v292','v293','v294','v295'))
    assert (p.ENGINEER_CALL_BUDGETS[name], p.TRAIN_ENGINEER_CALL_BUDGETS[name]) == (31, 41)
    assert smoke.engineer_request_floor(name) == 236000
    assert p.cleanup_grace_seconds(name) == 120 and p.ready_timeout_seconds(name) == 90
    assert v29_limits.identity(p, name)['confirm_cells'] == 480


def test_caps_are_v12_method_rederived_for_six_rounds_and_only_fc():
    from skillopt.coevo5.ledger import reservation
    from skillopt.execskill import v29_limits
    name, parent, b = p.ZEBRA_PC_V13, p.ZEBRA_PC_V12, p.ZEBRA
    schedule = {'run': {b: (0,60)}, 'examiner': {}, 'selftest': {b: (0,720)},
                'accept': {b: (200,300)}, 'confirm': {b: (0,480)}}
    assert p.CONFIG_SCHEDULE_CELLS[name][b] == schedule
    def cap(cells, rounding):
        return protocol._round_up(3 * (sum(5300*(c+Fraction(8,5)*q) for c,q in cells.values())
            + 16*p.READ_RESERVATION), rounding)
    assert p.CONFIG_STEP_CAPS[name][b] == {kind: cap(cells, 100000) for kind,cells in schedule.items()}
    assert p.CONFIG_STEP_CAPS[name][b] == {'run':26500000,'examiner':25000000,'selftest':43300000,
                                        'accept':35800000,'confirm':37200000}
    assert p.TEST_READ_CELLS[name] == {b:(200,200)}
    assert p.CONFIGURATIONS[name]['test_read_cap'] == cap({b:(200,200)},p.MILLION) == 34000000
    assert p.CONFIGURATIONS[name]['redo_reserve'] == max(p.CONFIG_STEP_CAPS[name][b].values()) == 43300000
    before = p.CONFIGURATIONS[parent]
    assert p.CONFIGURATIONS[name]['solver_cap'] == (before['solver_cap']
        + sum(p.CONFIG_STEP_CAPS[name][b].values()) - sum(p.CONFIG_STEP_CAPS[parent][b].values())
        + 34000000 - before['test_read_cap'] + 43300000 - before['redo_reserve']) == 249600000
    roles = p.CONFIG_ROLE_CAPS[name]
    assert roles['engineer'] == v29_limits.v291_engineer_cap(p,name) == 428351616
    assert v29_limits.judge_calls(p,b,name) == 600
    assert roles['audit_g'] == roles['audit_d'] == 601*reservation(p.ROLE_INPUT_BYTES,8192) == 549804416
    assert p.CONFIG_GLM_CAP[name] == p.CONFIG_GLM_CAP[parent] + sum(roles.values()) - sum(p.CONFIG_ROLE_CAPS[parent].values()) == 1625560448
    assert budgets.chain_caps('D',name)['overall'] == 1875160448
    assert p.read_estimate_terms({b:{'card':5300,'procedure_assumed':True}},1,name) == {b:Fraction(2756000)}
    calls = smoke.max_role_calls(name)
    assert calls['engineer'] == 270 and calls['audit_g'] == calls['audit_d'] == 600


def test_cli_and_routes_bind_child_without_changing_defaults(tmp_path, monkeypatch):
    from scripts.run_execskill import parser
    from tests.test_execskill_v29_profile import test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot','s0','manifest','smoke'):
        arg = next(a for a in commands['zpc-'+suffix]._actions if a.dest == 'configuration')
        assert p.ZEBRA_PC_V13 in arg.choices and arg.default == p.ZEBRA_PC_V1
    test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized(tmp_path,monkeypatch,p.ZEBRA_PC_V13)
