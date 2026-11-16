"""The isolated main-v9 registration and every one of its 45 frozen parents."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.execskill import budgets, manifest, profiles as p
from tests import test_execskill_v212_profile as parents
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

CAPTURE = Path(__file__).parent / 'fixtures/execskill/v225_parents_before.json'
BEFORE = json.loads(CAPTURE.read_text()) if CAPTURE.exists() else None
needs_capture = pytest.mark.skipif(BEFORE is None, reason='parent capture not published (it holds ALFWorld game text)')
CHILD, PARENT = p.MAIN_V9, p.MAIN_V8


@needs_capture
@pytest.mark.parametrize('name', sorted(BEFORE['configurations']) if BEFORE else [])
def test_all_forty_five_parent_fingerprints_stay_byte_identical(name, monkeypatch):
    monkeypatch.setattr(parents, 'SNAPSHOT', BEFORE)
    parents.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)
    tables = BEFORE['profile_tables'][name]
    assert manifest._plain({key: getattr(p, key)[name] for key in tables}) == tables


@needs_capture
def test_capture_precedes_source_edits_and_only_main_v9_is_added():
    assert BEFORE['captured_before_first_code_edit'] is True
    assert len(BEFORE['configurations']) == 45
    assert hashlib.sha256(CAPTURE.read_bytes()).hexdigest() == (
        '9ebcdb4d169f0314a2cd3685ac01c089db14140b1dae6e7a168f2136f544a751')
    assert set(p.CONFIGURATIONS) - set(BEFORE['configurations']) == {CHILD, p.MAIN_V10}
    assert all(not p.is_v225(name) for name in BEFORE['configurations'])


def test_registration_inherits_the_main_v8_family_and_dated_root():
    for predicate in (p.is_v23, p.is_v291, p.is_v292, p.is_v293, p.is_v294, p.is_v295,
                      p.is_v210, p.is_v211, p.is_v214, p.is_v218, p.is_v221, p.is_v222, p.is_v225):
        assert predicate(CHILD)
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261104-main-v9'
    assert p.MAIN_V9_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-v9', 'D': 'D-v9'}
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'main_v9_real_run'
    assert p.verified(p.record('authored', 'main_v9_real_run', {}))
    assert p.POLICY_VERSIONS[CHILD] == p.POLICY_VERSIONS[PARENT]
    assert p.train_rounds(CHILD, 'alfworld') == 0
    assert p.alfworld_format_rule(CHILD, 'alfworld') == p.alfworld_format_rule(PARENT, 'alfworld')


def test_tables_copied_by_value_with_explicit_cap_and_identity_overrides():
    differences = set()
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and PARENT in table:
            assert CHILD in table, key
            if table[CHILD] != table[PARENT]:
                differences.add(key)
            if isinstance(table[PARENT], (dict, list)):
                assert table[CHILD] is not table[PARENT], key
    assert differences == {'CONFIGURATIONS', 'PILOTS', 'RUN_ROOTS', 'CHAIN_NAMESPACES',
        'REAL_RUN_EVIDENCE', 'CONFIG_STEP_CAPS', 'CONFIG_SCHEDULE_CELLS',
        'TEST_READ_CELLS', 'CONFIG_ROLE_CAPS', 'CONFIG_GLM_CAP'}
    assert p.similar_pairs(CHILD) == p.similar_pairs(PARENT) == (
        ('searchqa', 'officeqa'), ('officeqa', 'spreadsheetbench'))


@pytest.mark.parametrize('bench', p.MAIN_V5_ORDER[:-1])
def test_existing_procedure_rules_slices_and_role_caps_are_unchanged(bench):
    assert p.slice_spec(CHILD, bench) == p.slice_spec(PARENT, bench)
    assert p.accept_freshness(CHILD, bench) == p.accept_freshness(PARENT, bench)
    assert p.confirm_freshness(CHILD, bench) == p.confirm_freshness(PARENT, bench)
    assert p.acceptance_rule(CHILD, bench) == p.acceptance_rule(PARENT, bench)
    assert p.GAIN_MIN_SHARE == Fraction(1, 10)
    old_roles = budgets.role_scope_caps(PARENT, bench)
    child_roles = budgets.role_scope_caps(CHILD, bench)
    assert {key: child_roles[key] for key in old_roles} == old_roles
    assert child_roles['card_writer'] == 6 * 613120


def test_cli_registers_main_v9_without_changing_default():
    from scripts.run_execskill import parser
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 'selftest', 's0', 'manifest', 'structural-smoke', 'smoke-run', 'smoke-summary'):
        arg = next(a for a in commands['v214-' + suffix]._actions if a.dest == 'configuration')
        assert CHILD in arg.choices and arg.default == p.MAIN_V5


def test_role_registration_keeps_legacy_scalars_and_scopes_fail_closed():
    assert p.card_writer_settings(CHILD) == {'model': p.ROLE_MODEL, 'max_tokens': 32768,
        'reasoning': p.ROLE_REASONING, 'read_timeout': p.ROLE_READ_TIMEOUT, 'input_chars': 120000}
    assert budgets.glm_scopes('G', 'card_writer', 'searchqa', 1, configuration=CHILD) == (
        'overall', 'G:glm', 'G:xs:searchqa:1:role:card_writer')
    with pytest.raises(ValueError):
        budgets.glm_scopes('G', 'card_writer', 'searchqa', 1, configuration=PARENT)


def test_main_v9_identity_records_all_overlay_choices():
    identity = p.main_v9_identity()
    assert identity['configuration'] == CHILD
    assert identity['card_phase']['gain_floor'] == 'max(3,ceil(0.05*T))'
    assert identity['read_layout']['units_per_chain'] == 40
    assert identity['read_layout']['panel_arm_reads_per_chain'] == 50
    assert identity['hygiene'] == {'hygiene_mode': 'off_no_p0'}
    assert identity['read_arms'] == list(p.read_arms_of(CHILD))
    assert identity['cross_bench_gate'] == p.main_v8_identity()['cross_bench_gate']
    json.dumps(manifest._plain(identity))


def test_real_main_v9_empty_card_and_procedure_packages_roundtrip_without_fixture_evidence(tmp_path):
    from skillopt.execskill import package, policy, v225_cards
    evidence = p.REAL_RUN_EVIDENCE[CHILD]
    parent = package.empty(step='G/s0', evidence=evidence)
    assert p.verified(parent.to_json(), 'package')['evidence'] == evidence
    package.save(tmp_path, parent)
    assert package.load(tmp_path/'packages'/(parent.sha256+'.json')) == parent
    card = v225_cards.make_card('searchqa', 'Compare the available evidence before deciding.',
                               evidence=evidence)
    ordinary = package.Procedure(id='p-searchqa-1-1', origin='searchqa', description='Compare evidence',
        hooks=(), source='GUIDANCE = "Compare evidence"\n', evidence=evidence,
        policy_version=policy.POLICY_VERSION_V222)
    for obj in (card, ordinary):
        assert package.Procedure.from_json(obj.to_json()) == obj
    child = package.with_(parent, step='G/s1', add=[card, ordinary])
    assert p.verified(child.to_json(), 'package')['evidence'] == evidence
    package.save(tmp_path, child)
    assert package.load(tmp_path/'packages'/(child.sha256+'.json')) == child
    assert child.evidence == evidence and not any(proc.is_fixture for proc in child.procedures)
    with pytest.raises(ValueError):
        package.empty(step='G/s0', evidence='main_v11_real_run')
