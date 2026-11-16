"""SearchQA post-hoc registration; all forty-two frozen parent configurations."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, chain, manifest, profiles as p, smoke, step
from tests import test_execskill_v212_profile as parents
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CHILD = p.SEARCHQA_HP_V6
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v220_parents_before.json'
BEFORE = json.loads(CAPTURE.read_text()) if CAPTURE.exists() else None
needs_capture = pytest.mark.skipif(BEFORE is None, reason='parent capture not published (it holds ALFWorld game text)')


@needs_capture
@pytest.mark.parametrize('name', sorted(BEFORE['configurations']) if BEFORE else [])
def test_all_forty_two_parent_fingerprints_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parents, 'SNAPSHOT', BEFORE)
    parents.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


@needs_capture
def test_original_capture_and_every_parent_table_are_unchanged():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == '29a87872fbb2d80d2fdeb101dfaba48728a6e164449e9ca373d3905dbd605b01'
    assert len(BEFORE['configurations']) == 42
    assert {n for n in p.CONFIGURATIONS if not p.is_v221(n)} - set(BEFORE['configurations']) == {CHILD}
    for name, tables in BEFORE['profile_tables'].items():
        actual = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(actual, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


@needs_capture
def test_configuration_inherits_import_contract_without_learning_or_other_benches():
    parent = p.ZEBRA_HP_V3R4
    assert p.CONFIGURATIONS[CHILD]['order'] == ('main-v6-final', 'searchqa-candidate')
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == ('searchqa',)
    assert p.launchable_chains(CHILD) == ('G', 'D') and p.first_call_bench(CHILD) == 'searchqa'
    assert p.read_items(CHILD, 'searchqa') == 400
    assert p.read_arms_of(CHILD) == p.legacy.read_arms_of(CHILD) == ('F', 'C')
    assert p.stage_arms_max(CHILD) == p.legacy.stage_arms_max(CHILD) == 0
    assert p.estimate_arms(CHILD) == p.legacy.estimate_arms(CHILD) == 1
    assert p.LEARNING[CHILD] == 'import' and step.training_units(CHILD) == ()
    assert p.train_rounds(CHILD) == p.train_patience(CHILD) == 0
    assert p.CONFIG_STEP_CAPS[CHILD] == p.CONFIG_SCHEDULE_CELLS[CHILD] == {}
    assert p.CONFIG_GLM_CAP[CHILD] == p.ENGINEER_CALL_BUDGETS[CHILD] == p.TRAIN_ENGINEER_CALL_BUDGETS[CHILD] == 0
    assert not any(budgets.role_scope_caps(CHILD).values())
    assert not any(smoke.max_role_calls(CHILD).values())
    assert not any((p.STAGE_READ[CHILD], p.PLACEBO_ARMS[CHILD], p.TEST_WITHHOLDING[CHILD]))
    assert not p.is_zebra(CHILD) and not p.is_implant_v5(CHILD) and not p.is_v218(CHILD) and not p.is_v219(CHILD)
    assert all(fn(CHILD) for fn in (p.is_v210, p.is_v211, p.is_v214, p.is_v220))
    assert not any(p.is_v220(name) for name in BEFORE['configurations'])
    assert p.uses_request_reuse(CHILD) and not p.uses_environment_lock(CHILD)
    assert p.machinery_configuration(CHILD, 'searchqa') == p.machinery_configuration(p.MAIN_V6, 'searchqa')
    differences = {'CONFIGURATIONS', 'PILOTS', 'TEST_READ_CELLS', 'RUN_ROOTS', 'CHAIN_NAMESPACES',
        'REAL_RUN_EVIDENCE', 'ACCEPT_FRESHNESS', 'CONFIRM_FRESHNESS'}
    actual_differences = set()
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and parent in table:
            assert CHILD in table, key
            if table[CHILD] != table[parent]:
                actual_differences.add(key)
            if isinstance(table[parent], (dict, list)):
                assert table[CHILD] is not table[parent], key
    assert actual_differences == differences


def test_identity_and_solver_route_are_the_registered_main_v6_searchqa_values(tmp_path):
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261102-searchqa-hp-v6'
    assert p.SEARCHQA_HP_V6_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-sq6', 'D': 'D-sq6'}
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'searchqa_hp_v6_test_read'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[CHILD], {}))
    identity = p.searchqa_hp_v6_identity()
    assert identity['evidence_kind'] == 'post_hoc_selected_upper_bound'
    assert identity['sheet_test_qualification'] is False and identity['memory_lock'] == 'never'
    assert manifest.registered(CHILD)['sizes']['v214'] == manifest._plain(identity)
    assert manifest.registered(CHILD)['sizes']['slices'] == {}
    for c in p.CHAINS:
        opts = {'env_path': str(tmp_path / 'unopened'), 'branch': 'N' if c == 'D' else None,
                'longest': 256 if c == 'D' else None}
        current = manifest.solver_block(c, configuration=CHILD, **opts)
        old = manifest.solver_block(c, configuration=p.MAIN_V6, **opts)
        for key in ('M', 'B', 'read_timeout'):
            old[key] = {'searchqa': old[key]['searchqa']}
        assert current == old


def test_caps_follow_frozen_formula_and_read_retry_is_funded():
    raw = 3 * (3400 * (400 + Fraction(8, 5) * 400) + 16 * 520192)
    assert raw == 35577216
    assert p.CELL_ANCHORS['searchqa'][1] == 3400
    assert p.legacy._round_up(raw, p.MILLION) == 36000000
    assert p.TEST_READ_CELLS[CHILD] == {'searchqa': (400, 400)}
    assert p.CONFIGURATIONS[CHILD] == {'order': ('main-v6-final', 'searchqa-candidate'),
        'test_read_cap': 36000000, 'redo_reserve': 36000000, 'solver_cap': 73100000}
    assert p.FIRST_CALL_CAP == 1100000
    for c in p.CHAINS:
        assert budgets.chain_caps(c, CHILD) == {'overall': 73100000, c + ':solver': 73100000, c + ':test': 72000000}
        assert smoke._scope_cells(c, CHILD) == {
            c + ':test': [{'searchqa': (800, 800)}], c + ':solver': [{'searchqa': (800, 800)}]}
    assert p.read_estimate_terms({'searchqa': {'card': 100, 'procedure': 180}}, 2, CHILD) == {'searchqa': 224000}
    assert p.read_estimate_terms({'searchqa': {'card': 100, 'procedure_assumed': True}}, 1, CHILD) == {'searchqa': 104000}
    with pytest.raises(ValueError):
        p.read_estimate_terms({'officeqa': {'card': 100}}, 1, CHILD)


@pytest.mark.parametrize('c', ['G', 'D'])
def test_read_budget_needs_no_learning_cost_check(tmp_path, monkeypatch, c):
    from tests.test_execskill_chain import setting
    st = setting(tmp_path, chain_=c, consent=False)
    st.extra.update(configuration=CHILD, test_read_estimate={c: 20000000},
                    test_read_terms={c: {'searchqa': 20000000}})
    st.budget = SimpleNamespace(snapshot=lambda: {scope: {'cap': cap, 'settled': 0, 'open': 0}
        for scope, cap in budgets.chain_caps(c, CHILD).items()})
    monkeypatch.setattr(chain, 'latest_cap_check', lambda *_: pytest.fail('No learning gate in an import-only run'))
    gate = chain.read_budget(st, c)
    assert gate['units'] == ['searchqa'] and gate['need'] == 26000000
    assert gate['cost_check'] == 'not_applicable_no_learning_run'
