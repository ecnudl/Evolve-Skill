"""main-v8 registration, conservative caps, and the 44 frozen parent profiles."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path

import pytest

from skillopt.execskill import budgets, manifest, profiles as p, v222_limits as limits
from tests import test_execskill_v212_profile as parents

CHILD, PARENT = p.MAIN_V8, p.MAIN_V7
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v222_parents_before.json'
BEFORE = json.loads(CAPTURE.read_text()) if CAPTURE.exists() else None
needs_capture = pytest.mark.skipif(BEFORE is None, reason='parent capture not published (it holds ALFWorld game text)')


@needs_capture
@pytest.mark.parametrize('name', sorted(BEFORE['configurations']) if BEFORE else [])
def test_all_forty_four_parent_profiles_keep_exact_registration_prompts_caps_units_judges(name, monkeypatch):
    monkeypatch.setattr(parents, 'SNAPSHOT', BEFORE)
    parents.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


@needs_capture
def test_capture_tables_and_only_new_configuration():
    assert len(BEFORE['configurations']) == 44
    assert set(p.CONFIGURATIONS) - set(BEFORE['configurations']) == {CHILD, p.MAIN_V9, p.MAIN_V10}
    for name, tables in BEFORE['profile_tables'].items():
        assert manifest._plain({key: getattr(p, key)[name] for key in tables}) == tables
    assert p.is_v222(CHILD) and not any(p.is_v222(n) for n in BEFORE['configurations'])
    assert p.is_v221(CHILD) and p.is_v218(CHILD) and p.is_v214(CHILD)
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261103-main-v8'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-v8', 'D': 'D-v8'}
    assert p.verified(p.record('authored', 'main_v8_real_run', {}))


def test_child_is_copied_by_value_and_only_registered_differences_change():
    differences = set()
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and PARENT in table:
            assert CHILD in table, key
            if table[CHILD] != table[PARENT]:
                differences.add(key)
            if isinstance(table[PARENT], (dict, list)):
                assert table[CHILD] is not table[PARENT], key
    assert differences == {'CONFIGURATIONS', 'PILOTS', 'RUN_ROOTS', 'CHAIN_NAMESPACES',
        'REAL_RUN_EVIDENCE', 'CONFIG_STEP_CAPS', 'CONFIG_SCHEDULE_CELLS', 'TEST_READ_CELLS', 'POLICY_VERSIONS'}
    assert p.CONFIG_GLM_CAP[CHILD] == p.CONFIG_GLM_CAP[PARENT]
    assert p.train_rounds(CHILD, 'alfworld') == 0


@pytest.mark.parametrize('bench', p.MAIN_V5_ORDER)
def test_machinery_slices_freshness_and_role_budgets_are_inherited(bench):
    from skillopt.execskill import diagnostics
    assert diagnostics.enabled(CHILD, bench) == diagnostics.enabled(PARENT, bench) == (bench == p.ZEBRA)
    assert p.machinery_configuration(CHILD, bench) == p.machinery_configuration(PARENT, bench)
    if bench == 'alfworld':
        # The inherited final ALFWorld step imports a fixed package; it has no
        # main-v7 training allocation to silently turn into a learned step.
        for configuration in (CHILD, PARENT):
            with pytest.raises(KeyError):
                p.slice_spec(configuration, bench)
            assert p.train_rounds(configuration, bench) == 0
        return
    assert p.slice_spec(CHILD, bench) == p.slice_spec(PARENT, bench)
    assert p.accept_freshness(CHILD, bench) == p.accept_freshness(PARENT, bench)
    assert p.confirm_freshness(CHILD, bench) == p.confirm_freshness(PARENT, bench)
    assert budgets.role_scope_caps(CHILD, bench) == budgets.role_scope_caps(PARENT, bench)


def test_harm_reservation_covers_whole_split_merge_and_acceptance_without_reuse_discount():
    assert (limits.MAX_CONFIRM_CANDIDATES_PER_ROUND, limits.MAX_ACCEPT_CANDIDATES_PER_ROUND) == (5, 1)
    assert limits.HARM_CELLS_PER_CANDIDATE == 4 * 60 * 2 == 480
    expected = deepcopy(p.CONFIG_SCHEDULE_CELLS[PARENT])
    for home in p.MAIN_V5_ORDER[:-1]:
        for phase, candidates in (('confirm', 30), ('accept', 6)):
            assert limits.maximum_candidates(p, home, phase) == candidates
            for other in p.MAIN_V5_ORDER:
                if other == home:
                    continue
                c, q = expected[home][phase].get(other, (0, 0))
                expected[home][phase][other] = (c, q + 2 * 60 * candidates)
            raw = 3 * (sum(p.CELL_ANCHORS[b][1] * (c + Fraction(8, 5) * q)
                           for b, (c, q) in expected[home][phase].items()) + 16 * 520192)
            assert p.CONFIG_STEP_CAPS[CHILD][home][phase] == max(
                p.CONFIG_STEP_CAPS[PARENT][home][phase], p.legacy._round_up(raw, 100000))
        assert p.CONFIG_STEP_CAPS[CHILD][home]['run'] == p.CONFIG_STEP_CAPS[PARENT][home]['run']
    assert p.CONFIG_SCHEDULE_CELLS[CHILD] == expected
    assert limits.identity()['harm_cells_per_step'] == 17280
    assert limits.identity()['reuse_discount'] is False


def test_four_base_read_arms_and_all_stages_are_priced_as_their_actual_kinds():
    assert p.read_arms_of(CHILD) == p.legacy.read_arms_of(CHILD) == ('B', 'C0', 'C', 'F', 'stages')
    assert 'C_hist' not in p.read_arms_of(CHILD)
    assert p.stage_arms_max(CHILD) == 4 and p.estimate_arms(CHILD) == 6
    assert p.TEST_READ_CELLS[CHILD] == {b: (2 * n, 6 * n) for b, n in p.MAIN_V5_TEST_ITEMS.items()}
    measurements = {b: {'card': 11, 'procedure': 17} for b in p.MAIN_V5_ORDER}
    assert p.read_estimate_terms(measurements, Fraction(13, 10), CHILD) == {
        b: Fraction(13, 10) * n * (2 * 11 + 6 * 17) for b, n in p.MAIN_V5_TEST_ITEMS.items()}
    base = p.legacy._round_up(3 * (sum(p.CELL_ANCHORS[b][1] * (2 * n + Fraction(8, 5) * 6 * n)
        for b, n in p.MAIN_V5_TEST_ITEMS.items()) + 5 * 16 * 520192), 1000000)
    assert p.CONFIGURATIONS[CHILD]['test_read_cap'] == base + max(limits.read_unit_caps(p).values())
    assert budgets.chain_caps('G', CHILD)['G:test'] == p.CONFIGURATIONS[CHILD]['test_read_cap']
    assert p.CONFIGURATIONS[CHILD]['redo_reserve'] == max(
        p.CONFIGURATIONS[PARENT]['redo_reserve'],
        *(cap for row in p.CONFIG_STEP_CAPS[CHILD].values() for cap in row.values()))


def test_registered_identity_exposes_costs_and_common_rule():
    identity = p.main_v8_identity()
    assert identity['configuration'] == CHILD
    assert identity['decision_rule'] == p.main_v7_identity()['decision_rule']
    assert identity['automatic_retry'] == p.main_v7_identity()['automatic_retry']
    assert identity['cross_bench_gate']['stages'] == ['confirmation', 'acceptance']
    assert identity['cross_bench_gate']['harm_slice_items'] == {
        b: 20 if b == 'alfworld' else 60 for b in p.MAIN_V5_ORDER}
    assert identity['read_base_cells_per_chain'] == 4740
    assert identity['read_logical_cells_per_chain'] == 9480
    json.dumps(manifest._plain(identity))
