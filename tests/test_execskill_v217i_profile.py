"""Implant-v5 registration, exact parent fingerprints and zero learning budgets."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, chain, manifest, profiles as p, smoke, step
from tests import test_execskill_v212_profile as parent_tests
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CHILD, PARENT = p.IMPLANT_V5, p.MAIN_V5
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v217i_parents_before.json'
SNAPSHOT = json.loads(CAPTURE.read_text())


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_all_39_existing_configuration_identities_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parent_tests, 'SNAPSHOT', SNAPSHOT)
    parent_tests.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_capture_and_all_older_tables_are_exact():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == 'c8f7f8c37ac01ce40ffe3f4ec586bc99d3edcc1c4636ed753cfad76cb90940e0'
    assert len(SNAPSHOT['configurations']) == 39
    assert {n for n in p.CONFIGURATIONS if not p.is_v218(n)} - set(SNAPSHOT['configurations']) == {CHILD}
    for name, tables in SNAPSHOT['profile_tables'].items():
        actual = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(actual, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_every_table_difference_is_explicit_and_every_other_value_inherits_main_v5():
    changes = {
        'CONFIGURATIONS': {**p.CONFIGURATIONS[PARENT], 'test_read_cap': 662000000, 'redo_reserve': 0, 'solver_cap': 663100000},
        'PILOTS': {**p.PILOTS[PARENT], 'test_read_cap': 662000000, 'redo_reserve': 0, 'solver_cap': 663100000},
        'RUN_ROOTS': '/data/execskill-20261101-implant-v5',
        'CHAIN_NAMESPACES': {'G': 'G-imp5', 'D': 'D-imp5'},
        'REAL_RUN_EVIDENCE': 'implant_v5_test_read', 'LEARNING': 'none',
        'ENGINEER_CALL_BUDGETS': 0, 'TRAIN_ENGINEER_CALL_BUDGETS': 0,
        'CONFIG_STEP_CAPS': {}, 'CONFIG_SCHEDULE_CELLS': {},
        'CONFIG_ROLE_CAPS': {key: 0 for key in p.CONFIG_ROLE_CAPS[PARENT]}, 'CONFIG_GLM_CAP': 0,
    }
    observed = set()
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and PARENT in table:
            assert CHILD in table, key
            if table[CHILD] != table[PARENT]:
                observed.add(key)
                assert table[CHILD] == changes[key]
            else:
                assert key not in changes
            if isinstance(table[PARENT], (dict, list)):
                assert table[CHILD] is not table[PARENT], key
    assert observed == set(changes)


def test_identity_machinery_order_panels_and_routes_keep_the_main_v5_registration(tmp_path):
    assert p.is_implant_v5(CHILD) and p.is_v214(CHILD) and p.is_v211(CHILD) and p.is_v210(CHILD)
    assert not p.is_zebra(CHILD) and not p.is_v217(CHILD)
    assert p.launchable_chains(CHILD) == ('G', 'D')
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == p.MAIN_V5_ORDER
    assert p.read_arms_of(CHILD) == ('F', 'C', 'B', 'stages')
    assert p.legacy.read_arms_of(CHILD) == p.read_arms_of(CHILD)
    assert p.stage_arms_max(CHILD) == p.legacy.stage_arms_max(CHILD) == 4
    assert p.estimate_arms(CHILD) == p.legacy.estimate_arms(CHILD) == 5
    assert p.IMPLANT_V5_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.verified(p.record('authored', 'implant_v5_test_read', {}))
    assert p.similar_pairs(CHILD) == (('searchqa', 'officeqa'), ('officeqa', 'spreadsheetbench'))
    assert manifest.prompt_sha(CHILD) == manifest.prompt_sha(PARENT)
    assert p.TEST_READ_CELLS[CHILD] == p.TEST_READ_CELLS[PARENT]
    for bench in p.MAIN_V5_ORDER:
        assert p.machinery_configuration(CHILD, bench) == p.machinery_configuration(PARENT, bench)
        assert p.read_items(CHILD, bench) == p.MAIN_V5_TEST_ITEMS[bench]
        assert p.train_rounds(CHILD, bench) == p.train_patience(CHILD, bench) == 0
        assert not any(budgets.role_scope_caps(CHILD, bench).values())
        assert not any(smoke.max_role_calls(CHILD, bench).values())
    for c in p.CHAINS:
        opts = dict(env_path=str(tmp_path / 'unopened-path'), branch='N' if c == 'D' else None,
                    longest=256 if c == 'D' else None)
        assert manifest.solver_block(c, configuration=CHILD, **opts) == manifest.solver_block(c, configuration=PARENT, **opts)
    assert step.training_units(CHILD) == ()
    assert manifest.registered(CHILD)['sizes']['v214'] == manifest._plain(p.implant_v5_identity())


def test_caps_fund_parent_read_and_largest_single_unit_retry_in_the_test_scope():
    units = {bench: p.legacy._round_up(p.MAIN_CAP_FACTOR * (p.CELL_ANCHORS[bench][1]
        * (cards + Fraction(8, 5) * procedures) + 16 * p.READ_RESERVATION), p.MILLION)
        for bench, (cards, procedures) in p.TEST_READ_CELLS[PARENT].items()}
    assert units == p.IMPLANT_READ_UNIT_CAPS == {
        'searchqa': 66000000, 'officeqa': 66000000, 'zebralogic': 57000000,
        'spreadsheetbench': 61000000, 'alfworld': 206000000}
    assert p.CONFIGURATIONS[PARENT]['test_read_cap'] == 456000000
    assert p.CONFIGURATIONS[CHILD]['test_read_cap'] == 456000000 + max(units.values()) == 662000000
    assert p.CONFIGURATIONS[CHILD]['redo_reserve'] == 0
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == 456000000 + 1100000 + max(units.values()) == 663100000
    for c in p.CHAINS:
        assert budgets.chain_caps(c, CHILD) == {'overall': 663100000, c+':solver': 663100000,
                                               c+':test': 662000000}
        scopes = smoke._scope_cells(c, CHILD)
        assert set(scopes) == {c+':solver', c+':test'}
        assert scopes[c+':test'] == scopes[c+':solver']
        read = p.TEST_READ_CELLS[PARENT]
        assert scopes[c+':test'] == [{b: (card * (2 if b == retry else 1),
                                         proc * (2 if b == retry else 1))
                                     for b, (card, proc) in read.items()} for retry in read]


def test_missing_consent_refuses_before_first_call_or_step(tmp_path, monkeypatch):
    from tests.test_execskill_chain import setting
    st = setting(tmp_path, chain_='G', consent=False)
    st.extra['configuration'] = CHILD
    monkeypatch.setattr(chain, 'first_call', lambda *a, **kw: pytest.fail('No call before consent'))
    result = chain.run(st, 'G', learn=lambda *a, **kw: pytest.fail('No step before consent'))
    assert result['status'] == 'paused'
    assert not list((st.root / 'G').glob('s*/step.json'))


def test_fixed_chain_read_budget_uses_smoke_without_learning_cost_check(tmp_path, monkeypatch):
    from tests.test_execskill_chain import setting
    st = setting(tmp_path, chain_='G', consent=False)
    st.extra.update(configuration=CHILD, test_read_estimate={'G': 1000000})
    caps = budgets.chain_caps('G', CHILD)
    st.budget = SimpleNamespace(snapshot=lambda: {s: {'cap': v, 'open': 0, 'settled': 0} for s,v in caps.items()})
    monkeypatch.setattr(chain, 'latest_cap_check', lambda *_: pytest.fail('No training cost check'))
    gate = chain.read_budget(st, 'G')
    assert gate['need'] == 1300000 and gate['cost_check'] == 'not_applicable_no_learning_run'
    caps['G:test'] = 1299999
    with pytest.raises(chain.Pause, match='1.3'):
        chain.read_budget(st, 'G')
