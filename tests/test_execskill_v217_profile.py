"""Fixed G solver import; authored profile checks and all 38 pre-edit identities."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, chain, manifest, profiles as p, smoke, step
from tests import test_execskill_v212_profile as parent_tests
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CHILD = p.ZEBRA_HP_G3R2
CAPTURE = Path(__file__).parent / 'fixtures/execskill/v217_parents_before.json'
SNAPSHOT = json.loads(CAPTURE.read_text())


@pytest.mark.parametrize('name', sorted(SNAPSHOT['configurations']))
def test_all_38_preexisting_identities_are_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parent_tests, 'SNAPSHOT', SNAPSHOT)
    parent_tests.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)


def test_preedit_capture_and_all_historical_tables_are_unchanged():
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == '1977bbbda76e040acc8e549da9430c495a883e015985b0dc55656e17edba48c9'
    assert len(SNAPSHOT['configurations']) == 38
    assert {n for n in p.CONFIGURATIONS if not p.is_implant_v5(n)} - set(SNAPSHOT['configurations']) == {CHILD}
    for name, tables in SNAPSHOT['profile_tables'].items():
        found = manifest._plain({key: getattr(p, key)[name] for key in tables})
        assert json.dumps(found, sort_keys=True).encode() == json.dumps(tables, sort_keys=True).encode()


def test_fixed_child_identity_and_no_learning_caps():
    assert p.is_v217(CHILD) and p.is_v213(CHILD) and p.is_zebra_fc(CHILD)
    assert not any(p.is_v217(name) for name in SNAPSHOT['configurations'])
    assert p.launchable_chains(CHILD) == ('G',)
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-zhpg3r2', 'D': 'D-zhpg3r2'}
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261031-zebra-hp-g3r2'
    assert p.ZEBRA_HP_G3R2_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'zebra_hp_g3r2_test_read'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[CHILD], {}))
    assert p.LEARNING[CHILD] == 'import' and step.training_units(CHILD) == ()
    assert p.ACCEPT_RULES[CHILD] is None
    assert p.train_rounds(CHILD) == p.train_patience(CHILD) == 0
    assert p.read_arms_of(CHILD) == ('F', 'C') and p.estimate_arms(CHILD) == 1
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == (p.ZEBRA,)
    assert p.TEST_READ_CELLS[CHILD] == {p.ZEBRA: (200, 200)}
    assert not p.PLACEBO_ARMS[CHILD] and not p.TEST_WITHHOLDING[CHILD] and not p.STAGE_READ[CHILD]
    assert manifest.prompt_sha(CHILD) == manifest.prompt_sha(p.ZEBRA_HP_V3R4)
    assert manifest.outcome_engineer_features(CHILD)['audit'] == 'not_run_fixed_post_hoc_import'
    assert p.CONFIG_STEP_CAPS[CHILD] == p.CONFIG_SCHEDULE_CELLS[CHILD] == {}
    assert not any(p.CONFIG_ROLE_CAPS[CHILD].values()) and p.CONFIG_GLM_CAP[CHILD] == 0
    assert p.ENGINEER_CALL_BUDGETS[CHILD] == p.TRAIN_ENGINEER_CALL_BUDGETS[CHILD] == 0
    assert not any(smoke.max_role_calls(CHILD).values())


def test_exact_bound_read_headroom_and_first_call_caps():
    assert p.ledger_bound(p.CHAINS['G'], p.ZEBRA) == 65536
    assert p.ZEBRA_HP_G3R2_READ_BOUND == 65536 * 200 * 2 == 26214400
    assert p.ZEBRA_HP_G3R2_READ_CAP == 34078720
    assert p.ZEBRA_HP_G3R2_READ_CAP - p.ZEBRA_HP_G3R2_READ_BOUND == 7864320
    assert p.READ_RESERVATION < 7864320
    assert p.CONFIGURATIONS[CHILD]['redo_reserve'] == 0
    assert budgets.chain_caps('G', CHILD) == {'overall': 35178720, 'G:solver': 35178720, 'G:test': 34078720}
    assert budgets.first_call_caps('G') == {'G:confirm': 1100000}


def test_read_budget_needs_no_training_cost_check_and_preserves_start_gate(tmp_path, monkeypatch):
    from tests.test_execskill_chain import setting
    st = setting(tmp_path, chain_='G', consent=False)
    st.extra.update(configuration=CHILD, test_read_estimate={'G': p.ZEBRA_HP_G3R2_READ_BOUND})
    caps = budgets.chain_caps('G', CHILD)
    st.budget = SimpleNamespace(snapshot=lambda: {s: {'cap': v, 'open': 0, 'settled': 0} for s,v in caps.items()})
    monkeypatch.setattr(chain, 'latest_cap_check', lambda *_: pytest.fail('No training cost check for fixed import'))
    assert chain.read_budget(st, 'G')['need'] == 34078720
    assert chain.read_budget(st, 'G')['cost_check'] == 'not_applicable_no_learning_run'
    caps['G:test'] -= 1
    with pytest.raises(chain.Pause, match='1.3'):
        chain.read_budget(st, 'G')


def test_d_refused_before_chain_root_or_learning(tmp_path):
    st = SimpleNamespace(root=tmp_path, extra={'configuration': CHILD})
    with pytest.raises(ValueError, match='registered chain'):
        chain.run(st, 'D', learn=lambda *_: pytest.fail('Reserved D cannot import'))
    assert not (tmp_path / 'D').exists()


def test_cli_choices_preserve_defaults_and_accept_child():
    from scripts.run_execskill import parser
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 's0', 'manifest', 'smoke'):
        arg = next(a for a in commands['zpc-' + suffix]._actions if a.dest == 'configuration')
        assert CHILD in arg.choices and arg.default == p.ZEBRA_PC_V1
