"""ALF v10 identity and exact inherited v2.9.5 behavior, with frozen parent snapshots."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.coevo5.outcomes import Verdict
from skillopt.execskill import (budgets, confirm, engineer, engineer_reader, engineer_v295,
                               judge, manifest, profiles as p, smoke, step, v29_limits)
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401
from tests.test_execskill_zpc_regression import FEATURES

CHILD, PARENT = p.ALFWORLD_V10, p.ALFWORLD_V9
SNAPSHOT = json.loads((Path(__file__).parent / 'fixtures/execskill/v296_parents_before.json').read_text())


def test_only_alf_v10_is_new_and_all_inherited_feature_versions_apply():
    assert {name for name in p.CONFIGURATIONS if p.is_v296(name) and not p.is_v297(name)} == {CHILD}
    assert not p.is_v296(None)
    for name in p.CONFIGURATIONS:
        assert p.alfworld_format_rule(name) == ('alfworld-readable-action-v2-9-6' if p.is_v296(name)
                                                else 'alfworld-admissible-9-10')
    assert all(fn(CHILD) for fn in (p.is_v23, p.is_v24, p.is_v25, p.is_v26, p.is_v27,
        p.is_v28, p.is_v29, p.is_v291, p.is_v292, p.is_v293, p.is_v294, p.is_v295))
    assert p.is_alfworld(CHILD) and p.is_alfworld_v2(CHILD) and not p.is_zebra(CHILD)
    assert p.active_benches(CHILD) == p.read_benches(CHILD) == ('alfworld',)
    assert p.read_arms_of(CHILD) == p.read_arms_of(PARENT)
    assert p.launchable_chains(CHILD) == ('D',)
    assert p.ALFWORLD_ADMISSIBLE_MIN == Fraction(9, 10)


def test_all_tables_clone_parent_except_registered_identity_values():
    exceptions = {'REAL_RUN_EVIDENCE', 'RUN_ROOTS', 'CHAIN_NAMESPACES', 'ACCEPT_FRESHNESS', 'CONFIRM_FRESHNESS'}
    tables = {key: value for key, value in vars(p).items()
              if key.isupper() and isinstance(value, dict) and PARENT in value}
    assert tables
    for key, values in tables.items():
        assert CHILD in values, key
        if key not in exceptions:
            assert values[CHILD] == values[PARENT], key
            if isinstance(values[PARENT], (dict, list)):
                assert values[CHILD] is not values[PARENT], key
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261028-alfworld-v10'
    assert p.ALFWORLD_V10_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-alf10', 'D': 'D-alf10'}
    assert set(p.CHAIN_NAMESPACES[CHILD].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'alfworld_v10_real_run'
    assert p.ENGINEER_RECORDS[CHILD] == p.ENGINEER_RECORDS[PARENT] == 'engineer-v2-9-5'
    value = p.record('engineer-v2-9-5', p.REAL_RUN_EVIDENCE[CHILD], {})
    assert p.verified(value, 'engineer') == value
    assert p.ACCEPT_FRESHNESS[CHILD] == 'alfworld_split_v1_slices_after_alfworld_v7_accept_v9_stopped'
    assert p.CONFIRM_FRESHNESS[CHILD] == confirm.FRESHNESS[CHILD] == (
        'alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7_v9_stopped')


def test_budget_formulas_units_and_runtime_limits_are_exact_parent_values():
    assert p.train_rounds(CHILD) == p.train_rounds(PARENT) == 6
    assert p.train_patience(CHILD) == p.train_patience(PARENT) == 4
    assert step.training_units(CHILD) == step.training_units(PARENT)
    assert p.ENGINEER_CALL_BUDGETS[CHILD] == 31 and p.TRAIN_ENGINEER_CALL_BUDGETS[CHILD] == 41
    assert p.cleanup_grace_seconds(CHILD) == 120 and p.ready_timeout_seconds(CHILD) == 90
    assert smoke.engineer_request_floor(CHILD) == smoke.engineer_request_floor(PARENT)
    assert smoke.max_role_calls(CHILD) == smoke.max_role_calls(PARENT)
    assert v29_limits.identity(p, CHILD) == v29_limits.identity(p, PARENT)
    assert budgets.caps(CHILD) == budgets.caps(PARENT)
    assert manifest.role_settings(CHILD) == manifest.role_settings(PARENT)
    for chain in p.CHAINS:
        assert budgets.chain_caps(chain, CHILD) == budgets.chain_caps(chain, PARENT)


@pytest.mark.parametrize('parent', sorted(SNAPSHOT['configurations']))
def test_full_parent_registration_prompts_caps_units_and_k1_judges_are_byte_identical(parent):
    before = SNAPSHOT['configurations'][parent]
    found = manifest._plain({'features': {key: getattr(p, key).get(parent, {'unregistered': True}) for key in FEATURES},
        'registered': manifest.registered(parent), 'prompts': manifest.prompt_sha(parent),
        'roles': manifest.role_settings(parent), 'budgets': {c: budgets.chain_caps(c, parent) for c in p.CHAINS},
        'call_budgets': [p.ENGINEER_CALL_BUDGETS[parent], p.TRAIN_ENGINEER_CALL_BUDGETS[parent]],
        'units': list(step.training_units(parent)), 'runtime': before['runtime'],
        'k1_judge': {label: judge.judge('alfworld', {'game_file': 'authored'}, {}, case['prediction'],
            runtime=before['runtime'], score=case['score'], verdict=Verdict(**case['verdict']))
            for label, case in SNAPSHOT['k1_episodes'].items()}})
    def encoded(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert encoded(found) == encoded(before)


@pytest.mark.parametrize('train', [False, True])
def test_engineer_prompt_text_and_complete_pin_map_are_parent_bytes(train):
    assert engineer_v295.system(CHILD, train=train) == engineer_v295.system(PARENT, train=train)
    assert manifest.prompt_sha(CHILD) == manifest.prompt_sha(PARENT)
    archived = SNAPSHOT['configurations'][PARENT]['prompts']
    assert manifest.prompt_sha(CHILD) == archived
    key = archived['v2']['engineer'] if train else archived['engineer']
    assert hashlib.sha256(engineer_v295.system(CHILD, train=train).encode()).hexdigest() == key


@pytest.mark.parametrize('request_kind', ['propose', 'fix', 'format_retry', 'audit_fix', 'fault_repair', 'inert_repair'])
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_engineer_actual_request_system_bytes_match_parent(request_kind, mode):
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    systems = []
    for configuration in (PARENT, CHILD):
        ctx, _ = context(configuration=configuration, bench='alfworld', mode=mode)
        ctx.roles = WireRoles(['authored reply'])
        user = {'request': request_kind, 'evidence': {'no_effect_hook': {'effect_hooks': ['before_call']}}}
        reply, call = engineer._ask(ctx, user, 'wire/' + request_kind)
        assert reply == 'authored reply' and call
        systems.append(ctx.roles.wire[0]['system'])
    assert systems[0] == systems[1]


@pytest.mark.parametrize('value', [False, True, 0, 1, 'TrUe', 'FALSE', 2, -1, 0.0, None, 'yes'])
def test_reader_boolean_tolerance_is_exact_parent_rule(value):
    from tests.test_execskill_v295_reader import entry, encoded
    from tests.test_execskill_v293_reader import context
    rows = []
    for configuration in (PARENT, CHILD):
        original = entry(configuration)
        original['requests_second_call'] = value
        rows.append(engineer_reader.read(encoded(original), context(configuration)))
    assert rows[0] == rows[1]


def test_cli_exposes_child_in_all_alf_profile_commands_without_default_change():
    from scripts.run_execskill import parser
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 's0', 'manifest', 'smoke', 'confirm-views'):
        action = next(row for row in commands['alf-' + suffix]._actions if row.dest == 'configuration')
        assert CHILD in action.choices
        if suffix != 'confirm-views':
            assert action.default == p.ALFWORLD_V1
    assert manifest.alfworld_registration_key(CHILD) == 'alfworld_v10'


def test_child_northgate_route_and_switch_checks(tmp_path, monkeypatch):
    from tests.test_execskill_v29_profile import (
        test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized)
    test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized(tmp_path, monkeypatch, CHILD)


def test_confirmation_preparation_rejects_parent_identity_both_directions(tmp_path, monkeypatch):
    from skillopt.execskill import alf_confirm_views as cv, alf_smoke
    from tests.test_execskill_v29_confirm_views import authored_preparation
    preparation, root, pool, runtime, calls = authored_preparation(tmp_path / 'source', monkeypatch)
    files = {}
    for configuration in (PARENT, CHILD):
        path = tmp_path / (configuration + '-confirm.json')
        files[configuration] = path
        result = cv.prepare(path, configuration=configuration, preparation_file=preparation, data_root=root)
        assert result['configuration'] == configuration
        assert result['confirm']['freshness'] == p.CONFIRM_FRESHNESS[configuration]
        assert cv.load_for_preparation(path, configuration=configuration,
            imported=alf_smoke.preparation(preparation), items=pool) == result
    assert len(calls) == 160
    for expected, actual in ((CHILD, PARENT), (PARENT, CHILD)):
        with pytest.raises(ValueError, match='configuration|configured'):
            cv.load_for_preparation(files[actual], configuration=expected,
                imported=alf_smoke.preparation(preparation), items=pool)
        out = tmp_path / ('s0-' + expected)
        with pytest.raises(ValueError, match='configuration|configured'):
            alf_smoke.collect_s0(out, preparation_file=preparation,
                confirm_views=files[actual], configuration=expected,
                selftest=tmp_path / 'must-not-open', checks={'passed': True})
        assert not out.exists()


def test_sealed_cell_keeps_child_configuration_and_inherited_metadata(tmp_path):
    from tests.test_execskill_v295_profile import (
        test_sealed_cell_preserves_inherited_configuration_route_and_keyword_metadata)
    test_sealed_cell_preserves_inherited_configuration_route_and_keyword_metadata(tmp_path, CHILD)


def test_s3c_authored_fixture_and_worker_options_are_parent_values(tmp_path, monkeypatch):
    from tests.test_execskill_v295_profile import test_s3c_fixture_and_worker_options_are_exactly_inherited
    test_s3c_fixture_and_worker_options_are_exactly_inherited(tmp_path, monkeypatch, CHILD, PARENT, 'alf10', 'alfworld')
