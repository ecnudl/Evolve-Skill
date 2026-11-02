"""main-v6 registration and the immutable forty-configuration baseline."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, engineer, manifest, profiles as p, smoke, v218_limits
from tests import test_execskill_v212_profile as parents
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CHILD, PARENT = p.MAIN_V6, p.MAIN_V5
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v218_parents_before.json'
BEFORE = json.loads(CAPTURE.read_text())


@pytest.mark.parametrize('name', sorted(BEFORE['configurations']))
def test_all_forty_older_configurations_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parents, 'SNAPSHOT', BEFORE)
    parents.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_all_forty_older_tables_are_byte_identical():
    assert len(BEFORE['configurations']) == 40
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == 'cfb663c420fe5004c7ea68bd469835735ac05d859c7f2aaa0e6970ebdf7c80bb'
    assert {n for n in p.CONFIGURATIONS if not p.is_v219(n)} - set(BEFORE['configurations']) == {CHILD}
    for name, tables in BEFORE['profile_tables'].items():
        assert json.dumps(manifest._plain({k: getattr(p,k)[name] for k in tables}),sort_keys=True).encode() == json.dumps(tables,sort_keys=True).encode()


def test_only_enumerated_tables_differ_from_main_v5():
    differences = {'PILOTS','CONFIGURATIONS','CHAIN_NAMESPACES','ACCEPT_FRESHNESS',
        'CONFIG_STEP_CAPS','CONFIG_SCHEDULE_CELLS','CONFIG_ROLE_CAPS','CONFIG_GLM_CAP',
        'REAL_RUN_EVIDENCE','RUN_ROOTS','CONFIRM_FRESHNESS','ENGINEER_CALL_BUDGETS','TRAIN_ENGINEER_CALL_BUDGETS'}
    actual = set()
    for name, table in vars(p).items():
        if name.isupper() and isinstance(table,dict) and PARENT in table:
            assert CHILD in table,name
            if table[CHILD] != table[PARENT]: actual.add(name)
            if isinstance(table[PARENT],(dict,list)): assert table[CHILD] is not table[PARENT],name
    assert actual == differences
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261101-main-v6'
    assert p.MAIN_V6_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G':'G-m6','D':'D-m6'}
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'main_v6_real_run'
    assert p.verified(p.record('authored','main_v6_real_run',{}))
    assert p.active_benches(CHILD) == p.MAIN_V5_ORDER
    assert p.read_arms_of(CHILD) == ('F','C','B','stages')
    assert p.legacy.read_arms_of(CHILD) == p.read_arms_of(CHILD)
    assert p.launchable_chains(CHILD) == ('G','D')
    assert p.TEST_READ_CELLS[CHILD] == p.TEST_READ_CELLS[PARENT]
    assert p.similar_pairs(CHILD) == p.similar_pairs(PARENT)


def test_split_budget_prices_both_cells_and_all_six_rounds_without_reuse_discount():
    extra = v218_limits.split_cells(p)
    assert extra == {'searchqa':{'selftest':10800,'confirm':1440},
        'officeqa':{'selftest':2808,'confirm':144},'zebralogic':{'selftest':2160,'confirm':1440},
        'spreadsheetbench':{'selftest':3276,'confirm':144}}
    expected = deepcopy(p.CONFIG_SCHEDULE_CELLS[PARENT])
    for bench, kinds in extra.items():
        for kind, count in kinds.items():
            cards, procs = expected[bench][kind][bench]
            expected[bench][kind][bench] = (cards,procs+count)
            measured = expected[bench][kind]
            cap=p.legacy._round_up(3*(sum(p.CELL_ANCHORS[b][1]*(c+Fraction(8,5)*q)
                for b,(c,q) in measured.items())+16*520192),100000)
            assert p.CONFIG_STEP_CAPS[CHILD][bench][kind] == max(cap,p.CONFIG_STEP_CAPS[PARENT][bench][kind])
        for kind in ('run','examiner','accept'):
            assert p.CONFIG_STEP_CAPS[CHILD][bench][kind] == p.CONFIG_STEP_CAPS[PARENT][bench][kind]
    assert p.CONFIG_SCHEDULE_CELLS[CHILD] == expected
    assert sum(map(lambda row:sum(row.values()),p.CONFIG_STEP_CAPS[CHILD].values())) == 1352700000
    assert p.CONFIGURATIONS[CHILD] == {**p.CONFIGURATIONS[PARENT], 'test_read_cap':662000000,
                                      'redo_reserve':263200000,'solver_cap':2280000000}
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == p.legacy._round_up(1352700000+662000000+263200000,5000000)
    assert p.CONFIG_GLM_CAP[CHILD] == p.CONFIG_GLM_CAP[PARENT]+521867776 == 7592790784
    for chain in p.CHAINS:
        assert budgets.chain_caps(chain,CHILD)['overall'] == 9872790784
        assert budgets.chain_caps(chain,CHILD)[chain+':test'] == 662000000


@pytest.mark.parametrize('bench',p.MAIN_V5_ORDER[:-1])
def test_machinery_rules_slices_freshness_and_engineer_budgets(bench):
    selected=p.ZEBRA_PC_V15 if bench==p.ZEBRA else p.MAIN_V4
    assert p.machinery_configuration(CHILD,bench)==selected
    assert p.slice_spec(CHILD,bench)==p.slice_spec(PARENT,bench)
    assert p.acceptance_rule(CHILD,bench)==p.acceptance_rule(PARENT,bench)
    assert p.train_rounds(CHILD,bench)==p.train_rounds(PARENT,bench)==6
    assert p.train_patience(CHILD,bench)==p.train_patience(PARENT,bench)==4
    assert p.accept_freshness(CHILD,bench).endswith('_and_main_v5_G_D')
    assert p.confirm_freshness(CHILD,bench).endswith('_and_main_v5_G_D')
    assert p.uses_v215(CHILD,bench)==p.uses_v216(CHILD,bench)==(bench==p.ZEBRA)
    assert budgets.role_scope_caps(CHILD,bench)==budgets.role_scope_caps(selected,bench)
    assert smoke.max_role_calls(CHILD,bench)==smoke.max_role_calls(selected,bench)
    for mode, table in (('train',p.TRAIN_ENGINEER_CALL_BUDGETS),('single',p.ENGINEER_CALL_BUDGETS)):
        ctx=SimpleNamespace(configuration=CHILD,bench=bench,mode=mode)
        assert engineer.Context.calls_cap.fget(ctx)==table[selected]
        assert p.engineer_prompt(CHILD,bench,mode)==p.engineer_prompt(selected,bench,mode)
    parent=manifest.prompt_sha(selected)
    assert manifest.prompt_sha(CHILD)['engineer'][bench] == (parent['engineer'] if bench==p.ZEBRA else parent['engineer'][bench])
