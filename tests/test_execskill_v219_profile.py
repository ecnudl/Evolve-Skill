"""Cross-v5 registration and the unchanged forty-one-configuration baseline."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, chain, manifest, profiles as p, smoke, step
from tests import test_execskill_v212_profile as parents
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CHILD, PARENT = p.CROSS_V5, p.IMPLANT_V5
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v219_parents_before.json'
BEFORE = json.loads(CAPTURE.read_text())
CELLS = {'searchqa': (800, 1600), 'officeqa': (344, 688), 'zebralogic': (200, 200),
         'spreadsheetbench': (558, 1116), 'alfworld': (268, 670)}
UNIT_CAPS = {'searchqa': 60000000, 'officeqa': 60000000, 'zebralogic': 34000000,
             'spreadsheetbench': 56000000, 'alfworld': 206000000}


@pytest.mark.parametrize('name', sorted(BEFORE['configurations']))
def test_all_forty_one_older_configurations_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parents, 'SNAPSHOT', BEFORE)
    parents.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_capture_and_every_older_table_remain_byte_identical():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == '7bfbff8fc6b65953a51dbb4ae7ff8ac717da8ec633bf704c59040e52c0066509'
    assert len(BEFORE['configurations']) == 41
    assert set(p.CONFIGURATIONS) - set(BEFORE['configurations']) == {CHILD}
    for name, tables in BEFORE['profile_tables'].items():
        actual = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(actual, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_only_enumerated_tables_differ_from_implant_v5():
    plan = {**p.CONFIGURATIONS[PARENT], 'test_read_cap': 413000000,
            'redo_reserve': 206000000, 'solver_cap': 620100000}
    expected = {'CONFIGURATIONS': plan, 'PILOTS': plan,
        'RUN_ROOTS': '/data/execskill-20261102-cross-v5',
        'CHAIN_NAMESPACES': {'G': 'G-x5', 'D': 'D-x5'},
        'REAL_RUN_EVIDENCE': 'cross_v5_test_read', 'STAGE_READ': False,
        'TEST_READ_CELLS': CELLS}
    differences = set()
    for name, table in vars(p).items():
        if name.isupper() and isinstance(table, dict) and PARENT in table:
            assert CHILD in table, name
            if table[CHILD] != table[PARENT]:
                differences.add(name)
                assert table[CHILD] == expected[name], name
            if isinstance(table[PARENT], (dict, list)):
                assert table[CHILD] is not table[PARENT], name
    assert differences == set(expected)


def test_identity_keeps_implant_machinery_panels_and_zero_learning(tmp_path):
    assert p.is_v219(CHILD) and not any(p.is_v219(name) for name in BEFORE['configurations'])
    assert p.is_implant_v5(CHILD) and p.is_v214(CHILD) and p.is_v211(CHILD) and p.is_v210(CHILD)
    assert not p.is_v218(CHILD) and not p.is_zebra(CHILD)
    assert p.launchable_chains(CHILD) == ('G', 'D')
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == p.MAIN_V5_ORDER
    assert p.read_arms_of(CHILD) == p.legacy.read_arms_of(CHILD) == ('F', 'C', 'B', 'cross')
    assert p.stage_arms_max(CHILD) == p.legacy.stage_arms_max(CHILD) == 0
    assert not p.STAGE_READ[CHILD] and not p.PLACEBO_ARMS[CHILD] and not p.TEST_WITHHOLDING[CHILD]
    assert p.CROSS_V5_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.verified(p.record('authored', 'cross_v5_test_read', {}))
    assert p.similar_pairs(CHILD) == p.similar_pairs(PARENT)
    assert manifest.prompt_sha(CHILD) == manifest.prompt_sha(PARENT)
    assert p.CONFIG_GLM_CAP[CHILD] == 0
    assert p.CONFIG_SCHEDULE_CELLS[CHILD] == p.CONFIG_STEP_CAPS[CHILD] == {}
    assert step.training_units(CHILD) == ()
    for bench in p.MAIN_V5_ORDER:
        assert p.machinery_configuration(CHILD, bench) == p.machinery_configuration(PARENT, bench)
        assert p.read_items(CHILD, bench) == p.read_items(PARENT, bench)
        assert p.train_rounds(CHILD, bench) == p.train_patience(CHILD, bench) == 0
        assert not any(budgets.role_scope_caps(CHILD, bench).values())
        assert not any(smoke.max_role_calls(CHILD, bench).values())
    for c in p.CHAINS:
        opts = {'env_path': str(tmp_path / 'unopened'), 'branch': 'N' if c == 'D' else None,
                'longest': 256 if c == 'D' else None}
        assert manifest.solver_block(c, configuration=CHILD, **opts) == manifest.solver_block(c, configuration=PARENT, **opts)
    identity = p.cross_v5_identity()
    assert identity['configuration'] == CHILD
    assert identity['evidence_kind'] == 'post_hoc_selected_upper_bound_transfer'
    assert manifest.registered(CHILD)['sizes']['v214'] == manifest._plain(identity)


def test_caps_use_registered_package_arm_factor_and_fund_retry_in_charged_scope():
    counts = {'searchqa': 6, 'officeqa': 6, 'zebralogic': 2, 'spreadsheetbench': 6, 'alfworld': 7}
    assert p.TEST_READ_CELLS[CHILD] == CELLS
    for bench, (cards, procedures) in CELLS.items():
        assert cards + procedures == counts[bench] * p.read_items(CHILD, bench)
    # X arms remain package arms even when no effective solver hook runs.
    raw = sum(p.CELL_ANCHORS[b][1] * (c + Fraction(8, 5) * q) for b, (c, q) in CELLS.items())
    assert raw == Fraction(479735662, 5)
    bounded = 3 * (raw + 5 * 16 * 520192)
    assert bounded == Fraction(2063437386, 5)
    base = p.legacy._round_up(bounded, p.MILLION)
    units = {b: p.legacy._round_up(3 * (p.CELL_ANCHORS[b][1] * (c + Fraction(8, 5) * q)
                     + 16 * 520192), p.MILLION) for b, (c, q) in CELLS.items()}
    assert base == 413000000 and units == UNIT_CAPS == p.CROSS_READ_UNIT_CAPS
    retry = max(units.values())
    assert retry == 206000000
    assert p.FIRST_CALL_CAP == 1100000
    assert p.CONFIGURATIONS[CHILD]['test_read_cap'] == base
    assert p.CONFIGURATIONS[CHILD]['redo_reserve'] == retry
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == base + retry + p.FIRST_CALL_CAP == 620100000
    for c in p.CHAINS:
        assert budgets.chain_caps(c, CHILD) == {'overall': 620100000, c + ':solver': 620100000,
                                               c + ':test': 619000000}
        assert budgets.solver_scopes(c, None, None, 'test') == ('overall', c + ':solver', c + ':test')
        scopes = smoke._scope_cells(c, CHILD)
        assert set(scopes) == {c + ':solver', c + ':test'}
        assert scopes[c + ':test'] == scopes[c + ':solver']
        assert scopes[c + ':test'] == [{b: (card * (2 if b == retry_bench else 1),
            proc * (2 if b == retry_bench else 1)) for b, (card, proc) in CELLS.items()} for retry_bench in CELLS]


@pytest.mark.parametrize('c', ['G', 'D'])
def test_interrupted_read_retry_uses_funded_test_scope_without_learning_gate(tmp_path, monkeypatch, c):
    from skillopt.continual_eval.core import write_json
    from tests.test_execskill_chain import setting
    st = setting(tmp_path, chain_=c, consent=False)
    terms = {b: 37500000 for b in p.MAIN_V5_ORDER[:-1]}
    terms['alfworld'] = 150000000
    st.extra.update(configuration=CHILD, test_read_estimate={c: 300000000}, test_read_terms={c: terms})
    ledger = {scope: {'cap': value, 'open': 0, 'settled': 0} for scope, value in budgets.chain_caps(c, CHILD).items()}
    st.budget = SimpleNamespace(snapshot=lambda: ledger)
    monkeypatch.setattr(chain, 'latest_cap_check', lambda *_: pytest.fail('No learning cost gate for fixed imports'))
    assert chain.read_budget(st, c)['need'] == 390000000
    for bench in p.MAIN_V5_ORDER[:-1]:
        write_json(chain.unit_root(st, c, bench) / 'unit.json', {'authored_completion_marker': True})
    for scope in budgets.solver_scopes(c, None, None, 'test'):
        ledger[scope]['settled'] = 300000000
    gate = chain.read_budget(st, c)
    assert gate['units'] == ['alfworld'] and gate['need'] == 195000000
    assert ledger[c + ':test']['cap'] - ledger[c + ':test']['settled'] == 319000000
    assert gate['cost_check'] == 'not_applicable_no_learning_run'
