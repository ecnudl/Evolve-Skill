"""main-v7 registration and the exact pre-edit forty-three-profile capture."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.execskill import budgets, diagnostics, manifest, profiles as p, v221_limits
from tests import test_execskill_v212_profile as parents

CHILD, PARENT = p.MAIN_V7, p.MAIN_V6
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v221_parents_before.json'
BEFORE = json.loads(CAPTURE.read_text()) if CAPTURE.exists() else None
needs_capture = pytest.mark.skipif(BEFORE is None, reason='parent capture not published (it holds ALFWorld game text)')


@needs_capture
@pytest.mark.parametrize('name', sorted(BEFORE['configurations']) if BEFORE else [])
def test_all_forty_three_parent_fingerprints_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parents, 'SNAPSHOT', BEFORE)
    parents.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


@needs_capture
def test_capture_and_all_historical_tables_are_byte_identical():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == 'e4ef0a2d69f704d8a082063dc7df40bef73d69775eff8f5d038c8073ae0fa997'
    assert len(BEFORE['configurations']) == 43
    assert set(p.CONFIGURATIONS) - set(BEFORE['configurations']) == {CHILD, p.MAIN_V8, p.MAIN_V9, p.MAIN_V10}
    for name, tables in BEFORE['profile_tables'].items():
        actual = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(actual, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


@needs_capture
def test_only_registered_child_tables_change_and_copies_do_not_alias_parent():
    expected = {'CONFIGURATIONS', 'PILOTS', 'RUN_ROOTS', 'CHAIN_NAMESPACES', 'REAL_RUN_EVIDENCE',
                'CONFIG_STEP_CAPS', 'CONFIG_SCHEDULE_CELLS'}
    differences = set()
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and PARENT in table:
            assert CHILD in table, key
            if table[CHILD] != table[PARENT]:
                differences.add(key)
            if isinstance(table[PARENT], (dict, list)):
                assert table[CHILD] is not table[PARENT], key
    assert differences == expected
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261103-main-v7'
    assert p.MAIN_V7_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-v7', 'D': 'D-v7'}
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'main_v7_real_run'
    assert p.verified(p.record('authored', 'main_v7_real_run', {}))
    assert p.is_v221(CHILD) and not any(p.is_v221(n) for n in BEFORE['configurations'])
    assert p.is_v218(CHILD) and p.is_v214(CHILD) and p.is_v211(CHILD)
    assert p.active_benches(CHILD) == p.MAIN_V5_ORDER
    assert p.read_benches(CHILD) == p.read_benches(PARENT)
    assert p.read_arms_of(CHILD) == p.legacy.read_arms_of(CHILD) == ('F', 'C', 'B', 'stages')
    assert p.legacy.stage_arms_max(CHILD) == p.stage_arms_max(CHILD) == 4
    assert p.uses_request_reuse(CHILD) and p.uses_environment_lock(CHILD)
    assert p.launchable_chains(CHILD) == ('G', 'D')
    assert p.train_rounds(CHILD, 'alfworld') == 0


@pytest.mark.parametrize('bench', p.MAIN_V5_ORDER[:-1])
def test_machinery_pools_slices_panels_and_method_budgets_stay_by_value(bench):
    assert p.machinery_configuration(CHILD, bench) == p.machinery_configuration(PARENT, bench)
    assert p.slice_spec(CHILD, bench) == p.slice_spec(PARENT, bench)
    assert p.confirm_spec(CHILD, bench, 1) == p.confirm_spec(PARENT, bench, 1)
    assert p.acceptance_rule(CHILD, bench) == p.acceptance_rule(PARENT, bench)  # diagnostic computation
    assert p.train_rounds(CHILD, bench) == 6 and p.train_patience(CHILD, bench) == 4
    assert p.TEST_READ_CELLS[CHILD] == p.TEST_READ_CELLS[PARENT]
    assert budgets.role_scope_caps(CHILD, bench) == budgets.role_scope_caps(PARENT, bench)
    assert diagnostics.enabled(CHILD, bench) == (bench == p.ZEBRA)


def test_early_read_and_merged_split_caps_use_frozen_formula_without_reuse_discount():
    expected = deepcopy(p.CONFIG_SCHEDULE_CELLS[PARENT])
    extras = v221_limits.extra_cells(p)
    for bench, kinds in extras.items():
        a, runs = p.slice_spec(CHILD, bench)['accept']
        assert kinds['accept'] == (5 * a * runs, 10 * a * runs)
        for kind, (cards, procs) in kinds.items():
            old_c, old_p = expected[bench][kind][bench]
            expected[bench][kind][bench] = (old_c + cards, old_p + procs)
            raw = 3 * (sum(p.CELL_ANCHORS[b][1] * (c + Fraction(8, 5) * q)
                           for b, (c, q) in expected[bench][kind].items()) + 16 * 520192)
            assert p.CONFIG_STEP_CAPS[CHILD][bench][kind] == max(
                p.CONFIG_STEP_CAPS[PARENT][bench][kind], p.legacy._round_up(raw, 100000))
        assert p.CONFIG_STEP_CAPS[CHILD][bench]['run'] == p.CONFIG_STEP_CAPS[PARENT][bench]['run']
        assert p.CONFIG_STEP_CAPS[CHILD][bench]['examiner'] == p.CONFIG_STEP_CAPS[PARENT][bench]['examiner']
    assert p.CONFIG_SCHEDULE_CELLS[CHILD] == expected
    assert p.CONFIGURATIONS[CHILD] == {**p.CONFIGURATIONS[PARENT],
        'redo_reserve': 322000000, 'solver_cap': 2830000000}
    assert p.CONFIG_GLM_CAP[CHILD] == 7592790784
    assert budgets.chain_caps('G', CHILD)['overall'] == 10422790784
    assert budgets.chain_caps('D', CHILD)['D:test'] == 662000000
    assert p.CONFIGURATIONS[CHILD]['solver_cap'] == p.legacy._round_up(
        sum(sum(row.values()) for row in p.CONFIG_STEP_CAPS[CHILD].values()) + 662000000 + 322000000,
        5000000)


def test_rule_constants_and_child_identity_are_bound_in_manifest():
    assert (p.GAIN_MIN_ITEMS, p.GAIN_MIN_SHARE, p.HARM_RATIO, p.WHOLE_BATCH_FLOOR) == (
        3, Fraction(1, 10), Fraction(2, 3), Fraction(-1, 100))
    identity = manifest.registered(CHILD)['sizes']['v214']
    assert identity == manifest._plain(p.main_v7_identity())
    assert identity['decision_rule']['stages'] == ['training', 'confirmation', 'acceptance']
    assert identity['automatic_retry'] == {'count': 1, 'delay_seconds': 60, 'pure_infrastructure_only': True}
    assert identity['launch'] == "not before the owner's go"


@pytest.mark.parametrize('action', ['snapshot', 'selftest', 's0', 'manifest', 'structural-smoke', 'smoke-run', 'smoke-summary'])
def test_cli_adds_only_main_v7_and_preserves_default(action):
    from scripts.run_execskill import parser
    command = parser()._subparsers._group_actions[0].choices['v214-' + action]
    option = next(a for a in command._actions if a.dest == 'configuration')
    assert tuple(option.choices) == (p.MAIN_V5, p.IMPLANT_V5, p.MAIN_V6, p.CROSS_V5, p.SEARCHQA_HP_V6, CHILD, p.MAIN_V8, p.MAIN_V9, p.MAIN_V10)
    assert option.default == p.MAIN_V5
