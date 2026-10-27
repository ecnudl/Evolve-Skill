"""v2.9.5 opt-in identities, parent preservation and inherited runtime plumbing, offline only."""
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.execskill import (budgets, confirm, engineer_v294, manifest, profiles as p,
                               routes, smoke, v29_limits)
from tests.test_execskill_zpc_pipeline import offline
from tests.execskill_v293_fakes import tmp_path
from tests.test_execskill_zpc_regression import FEATURES

CHILDREN = [(p.ZEBRA_PC_V12, p.ZEBRA_PC_V11, 'zpc12', 'zebralogic'),
            (p.ALFWORLD_V9, p.ALFWORLD_V8, 'alf9', 'alfworld')]


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_child_clones_every_parent_table_with_only_registered_identity_changes(config, parent, tag, bench):
    exceptions = {'ENGINEER_RECORDS', 'REAL_RUN_EVIDENCE', 'RUN_ROOTS', 'CHAIN_NAMESPACES',
                  'ACCEPT_FRESHNESS', 'CONFIRM_FRESHNESS'}
    if config == p.ZEBRA_PC_V12:
        exceptions |= {'CONFIGURATIONS', 'CONFIG_STEP_CAPS', 'CONFIG_SCHEDULE_CELLS', 'CONFIG_ROLE_CAPS', 'CONFIG_GLM_CAP', 'PILOTS'}
    tables = {name: value for name, value in vars(p).items()
              if name.isupper() and isinstance(value, dict) and parent in value}
    assert tables
    for name, table in tables.items():
        assert config in table, name
        if name not in exceptions:
            assert table[config] == table[parent], name
            if isinstance(table[parent], (dict, list)):
                assert table[config] is not table[parent], name
    assert all(fn(config) for fn in (p.is_v23, p.is_v24, p.is_v25, p.is_v26, p.is_v27,
                                    p.is_v28, p.is_v29, p.is_v291, p.is_v292, p.is_v293, p.is_v294, p.is_v295))
    assert not p.is_v295(parent)
    assert p.active_benches(config) == p.read_benches(config) == (bench,)
    assert p.read_arms_of(config) == p.read_arms_of(parent)
    assert p.launchable_chains(config) == ('D',)
    assert p.is_zebra(config) == (bench == 'zebralogic')
    assert p.is_alfworld(config) == p.is_alfworld_v2(config) == (bench == 'alfworld')
    assert p.RUN_ROOTS[config] == '/data/execskill-20261027-' + config
    assert p.CHAIN_NAMESPACES[config] == {'G': 'G-' + tag, 'D': 'D-' + tag}
    assert set(p.CHAIN_NAMESPACES[config].values()) <= set(p.SUPPORTED_NAMESPACES)
    assert p.REAL_RUN_EVIDENCE[config] == config.replace('-', '_') + '_real_run'
    assert p.ENGINEER_RECORDS[config] == 'engineer-v2-9-5'
    value = p.record(p.ENGINEER_RECORDS[config], p.REAL_RUN_EVIDENCE[config], {})
    assert p.verified(value, 'engineer') == value
    assert p.train_patience(config) == (8 if config == p.ZEBRA_PC_V12 else 4)
    assert p.train_rounds(config) == (10 if config == p.ZEBRA_PC_V12 else 6)
    assert p.train_patience(parent) == 4 and p.train_rounds(parent) == 6
    assert p.FAULT_REPAIRS == 2
    assert p.cleanup_grace_seconds(config) == p.cleanup_grace_seconds(parent) == 120
    assert p.ready_timeout_seconds(config) == p.ready_timeout_seconds(parent) == 90
    assert manifest.registered(config)['thresholds']['sandbox_cleanup_grace_seconds'] == 120
    assert manifest.registered(config)['thresholds']['sandbox_ready_timeout_seconds'] == 90


def test_exact_child_roster_roots_and_freshness_labels():
    assert {name for name in p.CONFIGURATIONS if p.is_v295(name)} == {p.ZEBRA_PC_V12, p.ALFWORLD_V9}
    assert p.ZEBRA_PC_V12_MANIFEST == p.ZEBRA_PC_V12_ROOT + '-manifest.json'
    assert p.ALFWORLD_V9_MANIFEST == p.ALFWORLD_V9_ROOT + '-manifest.json'
    assert p.ACCEPT_FRESHNESS[p.ZEBRA_PC_V12] == 'zebra_split_v1_slices_accept_after_zebra_pc_v9_v11'
    assert p.CONFIRM_FRESHNESS[p.ZEBRA_PC_V12] == 'zebra_split_v1_confirm_after_zebra_pc_v9_v11'
    assert p.ACCEPT_FRESHNESS[p.ALFWORLD_V9] == 'alfworld_split_v1_slices_after_alfworld_v7_v8_not_launched'
    assert p.CONFIRM_FRESHNESS[p.ALFWORLD_V9] == 'alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7_v8_not_launched'
    assert not p.is_v295(None)
    for config, _, _, _ in CHILDREN:
        assert confirm.FRESHNESS[config] == p.CONFIRM_FRESHNESS[config]


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_per_round_budgets_unchanged_and_alf_step_caps_are_exact_parent_copies(config, parent, tag, bench):
    assert p.ENGINEER_CALL_BUDGETS[config] == p.ENGINEER_CALL_BUDGETS[parent] == 31
    assert p.TRAIN_ENGINEER_CALL_BUDGETS[config] == p.TRAIN_ENGINEER_CALL_BUDGETS[parent] == 41
    assert smoke.engineer_request_floor(config) == smoke.engineer_request_floor(parent) == 236000
    if config == p.ALFWORLD_V9:
        assert v29_limits.identity(p, config) == v29_limits.identity(p, parent)
        assert smoke.max_role_calls(config) == smoke.max_role_calls(parent)
        assert budgets.caps(config) == budgets.caps(parent)
        for chain in p.CHAINS:
            assert budgets.chain_caps(chain, config) == budgets.chain_caps(chain, parent)


@pytest.mark.parametrize('parent', [p.ZEBRA_PC_V7, p.ALFWORLD_V4, p.ZEBRA_PC_V8, p.ALFWORLD_V5,
                                    p.ZEBRA_PC_V9, p.ALFWORLD_V6, p.ZEBRA_PC_V10, p.ALFWORLD_V7,
                                    p.ZEBRA_PC_V11, p.ALFWORLD_V8])
def test_parent_registration_prompt_and_budget_bytes_remain_frozen(parent):
    baseline = json.loads((Path(__file__).parent / 'fixtures/execskill/v295_parents_before.json').read_text())
    found = manifest._plain({'features': {key: getattr(p, key).get(parent, {'unregistered': True}) for key in FEATURES},
        'registered': manifest.registered(parent), 'prompts': manifest.prompt_sha(parent),
        'roles': manifest.role_settings(parent), 'budgets': {c: budgets.chain_caps(c, parent) for c in p.CHAINS},
        'call_budgets': [p.ENGINEER_CALL_BUDGETS[parent], p.TRAIN_ENGINEER_CALL_BUDGETS[parent]]})
    assert found == baseline[parent]


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_system_text_adds_abstention_rule_and_manifest_pins_new_round_limits(config, parent, tag, bench):
    from skillopt.execskill import engineer_v295
    pins = manifest.prompt_sha(config)
    for version in ('v29', 'v291', 'v292', 'v293', 'v294'):
        assert pins[version] == manifest.prompt_sha(parent)[version]
    assert pins['v295'] == engineer_v295.prompt_pins()
    for mode in (False, True):
        text = engineer_v295.system(config, train=mode)
        expected = engineer_v294.system(parent, train=mode).replace('(v2.9.4)', '(v2.9.5)')
        if config == p.ZEBRA_PC_V12:
            expected = expected.replace('6 training rounds, patience 4', '10 training rounds, patience 8')
            expected = expected.replace('patience 4 over at most 6 rounds', 'patience 8 over at most 10 rounds')
        assert text == expected + engineer_v295.ABSTAIN_RULE + '\n'
        digest = hashlib.sha256(text.encode()).hexdigest()
        assert (pins['v2']['engineer'] if mode else pins['engineer']) == digest
        assert len(text.encode()) + max(len(pin['text'].encode()) for key, pin in pins['v295'].items()
                                       if '/' not in key) <= v29_limits.V291_ENGINEER_SYSTEM_BYTES
    for key in ('format_retry', 'fix', 'audit_fix', 'fault_repair', 'inert_repair'):
        assert pins['v295'][key] == pins['v294'][key]
    for key, value in pins['v295'].items():
        assert value['sha256'] == hashlib.sha256(value['text'].encode()).hexdigest(), key
    features = manifest.outcome_engineer_features(config)
    assert features['train_rounds'] == p.train_rounds(config)
    assert features['train_patience'] == p.train_patience(config)
    assert features['inert_repair'] == manifest.outcome_engineer_features(parent)['inert_repair']
    assert features['fault_repair'] == manifest.outcome_engineer_features(parent)['fault_repair']


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_cli_all_profile_commands_accept_child_without_changing_defaults(config, parent, tag, bench):
    from scripts.run_execskill import parser
    prefix = 'zpc' if bench == 'zebralogic' else 'alf'
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 's0', 'manifest', 'smoke'):
        action = next(row for row in commands[prefix + '-' + suffix]._actions if row.dest == 'configuration')
        assert config in action.choices
        assert action.default == (p.ZEBRA_PC_V1 if prefix == 'zpc' else p.ALFWORLD_V1)
    if bench == 'alfworld':
        assert manifest.alfworld_registration_key(config) == 'alfworld_v9'
        assert config in next(row for row in commands['alf-confirm-views']._actions
                              if row.dest == 'configuration').choices


@pytest.mark.parametrize('config', [p.ZEBRA_PC_V12, p.ALFWORLD_V9])
def test_child_northgate_route_and_switch_checks(tmp_path, monkeypatch, config):
    from tests.test_execskill_v29_profile import (
        test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized)
    test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized(tmp_path, monkeypatch, config)


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V12, p.ALFWORLD_V9])
def test_child_full_manifest_round_trip_binds_new_prompts_and_confirmation(tmp_path, monkeypatch, configuration):
    from tests.test_execskill_v29_manifest_smoke import (
        test_complete_manifest_pins_exact_practice_ids_prompts_and_models)
    test_complete_manifest_pins_exact_practice_ids_prompts_and_models(tmp_path, monkeypatch, configuration)


def test_alf_v9_confirmation_preparation_is_distinct_and_s0_rejects_parent_identity(tmp_path, monkeypatch):
    from skillopt.execskill import alf_confirm_views as cv, alf_smoke
    from tests.test_execskill_v29_confirm_views import authored_preparation
    preparation, root, pool, runtime, calls = authored_preparation(tmp_path / 'source', monkeypatch)
    target = tmp_path / 'v295-confirm.json'
    result = cv.prepare(target, configuration=p.ALFWORLD_V9, preparation_file=preparation, data_root=root)
    assert len(calls) == 80 and result['configuration'] == p.ALFWORLD_V9
    assert result['confirm']['freshness'] == p.CONFIRM_FRESHNESS[p.ALFWORLD_V9]
    assert cv.load_for_preparation(target, configuration=p.ALFWORLD_V9,
        imported=alf_smoke.preparation(preparation), items=pool) == result
    parent_target = tmp_path / 'parent-confirm.json'
    cv.prepare(parent_target, configuration=p.ALFWORLD_V8, preparation_file=preparation, data_root=root)
    with pytest.raises(ValueError, match='configuration|configured'):
        cv.load_for_preparation(parent_target, configuration=p.ALFWORLD_V9,
            imported=alf_smoke.preparation(preparation), items=pool)
    with pytest.raises(ValueError, match='configuration|configured'):
        cv.load_for_preparation(target, configuration=p.ALFWORLD_V8,
            imported=alf_smoke.preparation(preparation), items=pool)
    # Check parent-identity refusal in a separate resolved OS scratch directory.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='alf9-s0-parent-') as outside:
        out = Path(outside).resolve() / 's0'
        assert not out.is_relative_to(manifest.REPO)
        with pytest.raises(ValueError, match='configuration|configured'):
            alf_smoke.collect_s0(out, preparation_file=preparation,
                confirm_views=target, configuration=p.ALFWORLD_V8,
                selftest=tmp_path / 'must-not-open', checks={'passed': True})
        assert not out.exists()
        with pytest.raises(ValueError, match='configuration|configured'):
            alf_smoke.collect_s0(out, preparation_file=preparation,
                confirm_views=parent_target, configuration=p.ALFWORLD_V9,
                selftest=tmp_path / 'must-not-open', checks={'passed': True})
        assert not out.exists()

    # The same sealed child views feed the inherited S0/prelaunch checks.
    from dataclasses import asdict
    from skillopt.continual_eval.core import write_json
    from skillopt.execskill.sandbox import client as sandbox
    from tests.test_execskill_manifest import MEASURED, tree
    snapshot = tree(tmp_path / 'snapshot')
    monkeypatch.setattr(manifest, 'REPO', snapshot)
    selftest = tmp_path / 'selftest.json'
    write_json(selftest, p.record('sandbox-selftest', 'smoke', {'passed': True,
        'measured': dict(MEASURED), 'limits': {key: asdict(limits) for key, limits in sandbox.LIMITS.items()}}))
    checked = alf_smoke.collect_s0(tmp_path / 's0-child', preparation_file=preparation, confirm_views=target,
        configuration=p.ALFWORLD_V9, snapshot_root=snapshot, selftest=selftest, checks={'passed': True})
    assert checked['passed'] and checked['configuration'] == p.ALFWORLD_V9
    assert checked['slice_counts']['confirm'] == 40 and checked['alf_confirm_views'] == result


@pytest.mark.parametrize('config,parent,tag,bench', CHILDREN)
def test_s3c_fixture_and_worker_options_are_exactly_inherited(tmp_path, monkeypatch, config, parent, tag, bench):
    from types import SimpleNamespace
    from skillopt.execskill import v29_smoke, units
    from tests.test_execskill_v292_cleanup_plumbing import setting
    assert v29_smoke.authored_fault_reply(bench, configuration=config) == v29_smoke.authored_fault_reply(
        bench, configuration=parent)
    original = setting(tmp_path, config)
    local = units.for_unit(original, 'D', bench, 'D/unit')
    assert local.sandbox['cleanup_grace_seconds'] == 120
    assert local.sandbox['ready_timeout_seconds'] == 90
    seen = []
    monkeypatch.setattr(units, 'Worker', lambda **options: seen.append(options))
    context = units.cell_context(local, tmp_path / 'attempt', SimpleNamespace(model=p.CHAINS['G']))
    context.worker(bench)
    assert seen[0]['cleanup_grace_seconds'] == 120 and seen[0]['ready_timeout_seconds'] == 90
    assert seen[0]['cleanup_events'] is local.sandbox['cleanup_events']
    assert seen[0]['start_events'] is local.sandbox['start_events']


@pytest.mark.parametrize('configuration', (p.ZEBRA_PC_V12, p.ALFWORLD_V9, p.ZEBRA_PC_V11, p.ALFWORLD_V8))
def test_sealed_cell_preserves_inherited_configuration_route_and_keyword_metadata(tmp_path, configuration):
    from skillopt.execskill import cells, client, evaluation, replay
    from tests.test_execskill_cells import _Client, _context, _cell, _reply
    from tests.test_execskill_v29_runtime import procedure, worker
    from tests.fixtures.execskill.items import searchqa_items
    proc = procedure()
    response = {**_reply('<answer>Fixtown 0</answer>'), 'returned_model': client.NORTHGATE_MODEL, 'route': 'B'}
    fake = _Client(response)
    fake.route, fake.request_model = 'B', client.NORTHGATE_MODEL
    context = _context(tmp_path, fake, worker=lambda bench: worker(proc))
    context.configuration = configuration
    item = searchqa_items(1)[0]
    cell = _cell(item, arm="S'", unit='D/authored/sealed-cell')
    full = cells.run_cell(context, cell, item, cells.Arm('candidate', replay.solo(proc)),
                          store=cells.TrainingStore(context.attempt))
    sealed = evaluation.sealed_cell(full)
    assert full['keyword_hits']['count'] > 0 and full['applies'] == {proc.id: 'default_true'}
    for key in ('configuration', 'keyword_hits', 'applies', 'returned_model', 'returned_models'):
        assert sealed[key] == full[key]
    assert sealed['configuration'] == configuration
    assert sealed['returned_models'] == [client.NORTHGATE_MODEL]
    assert sealed['solver_route'] == {'route': 'B', 'model': client.NORTHGATE_MODEL}
    assert sealed['calls'][0]['reply_sha256'] == hashlib.sha256(response['response'].encode()).hexdigest()
    assert response['response'] not in json.dumps(sealed)


def test_zebra_ten_round_caps_recompute_each_round_dependent_reservation():
    import math
    from skillopt.coevo5.ledger import reservation
    config, parent, bench = p.ZEBRA_PC_V12, p.ZEBRA_PC_V11, 'zebralogic'
    rounds = p.train_rounds(config)
    assert rounds == 10 and p.train_rounds(parent) == p.TRAIN_ROUNDS == 6
    calls = smoke.max_role_calls(config)
    assert calls['engineer'] == rounds * (41 + p.TRAIN_ANALYST_CALLS) == 450
    assert calls['leakage'] == rounds * p.MAX_CHANGES * (1 + p.TRAIN_FIXES + p.FAULT_REPAIRS + 1) == 210
    assert calls['describer'] == min(p.MAX_PROCEDURES, rounds * p.MAX_CHANGES) == 24
    re = reservation(p.ROLE_INPUT_BYTES + v29_limits.V291_ENGINEER_SYSTEM_BYTES, p.ENGINEER_MAX_TOKENS[config])
    ro = reservation(p.ROLE_INPUT_BYTES, p.ROLE_MAX_TOKENS)
    engineer_cap = calls['engineer'] * re + (calls['leakage'] + calls['describer']) * ro + re
    assert engineer_cap == p.CONFIG_ROLE_CAPS[config]['engineer'] == 707515776
    judge_calls = (rounds * p.MAX_CHANGES * v29_limits.AUDIT1_PASSES + p.MAX_PROCEDURES) * 5 * 2
    assert judge_calls == calls['audit_g'] == calls['audit_d'] == 840
    for role in v29_limits.JUDGE_ROLES:
        assert p.CONFIG_ROLE_CAPS[config][role] == (judge_calls + 1) * reservation(p.ROLE_INPUT_BYTES, 8192) == 769360256
    old_roles, roles = p.CONFIG_ROLE_CAPS[parent], p.CONFIG_ROLE_CAPS[config]
    assert p.CONFIG_GLM_CAP[config] == p.CONFIG_GLM_CAP[parent] + sum(roles[key] - old_roles[key] for key in roles)
    assert p.CONFIG_GLM_CAP[config] == 2343836288
    cells = p.CONFIG_SCHEDULE_CELLS[config][bench]
    assert cells['selftest'] == {bench: (0, rounds * 2 * 60)}
    assert cells['confirm'] == {bench: (0, rounds * 2 * 40)}
    caps = p.CONFIG_STEP_CAPS[config][bench]
    for kind in ('selftest', 'confirm'):
        amount = math.ceil(p.MAIN_CAP_FACTOR * (sum(p.CELL_ANCHORS[b][1] * (card + p.PROCEDURE_ARM_FACTOR[1] * proc)
            for b, (card, proc) in cells[kind].items()) + p.MAIN_RESERVATIONS * p.READ_RESERVATION))
        assert caps[kind] == math.ceil(amount / 100000) * 100000
    assert caps['selftest'] == 55500000 and caps['confirm'] == 45400000
    for kind in ('run', 'examiner', 'accept'):
        assert cells[kind] == p.CONFIG_SCHEDULE_CELLS[parent][bench][kind]
        assert caps[kind] == p.CONFIG_STEP_CAPS[parent][bench][kind]
    before, after = p.CONFIGURATIONS[parent], p.CONFIGURATIONS[config]
    assert after['test_read_cap'] == before['test_read_cap'] == 54000000
    assert after['redo_reserve'] == max(caps.values()) == 55500000
    assert after['solver_cap'] == (before['solver_cap'] + after['redo_reserve'] - before['redo_reserve']
        + sum(caps[kind] - p.CONFIG_STEP_CAPS[parent][bench][kind] for kind in ('selftest', 'confirm'))) == 304800000
    for chain in p.CHAINS:
        full = budgets.chain_caps(chain, config)
        assert full['overall'] == after['solver_cap'] + p.CONFIG_GLM_CAP[config] == 2648636288
        assert full[chain + ':xs:zebralogic:1:selftest'] == 55500000
        assert full[chain + ':xs:zebralogic:1:confirm'] == 45400000
        assert full[chain + ':xs:zebralogic:1:role:engineer'] == 707515776


def test_all_other_configuration_round_limits_keep_six_and_old_patience_values():
    for config in p.CONFIGURATIONS:
        assert p.train_rounds(config) == (10 if config == p.ZEBRA_PC_V12 else 6)
        expected = 8 if config == p.ZEBRA_PC_V12 else 4 if p.is_v291(config) else p.TRAIN_PATIENCE
        assert p.train_patience(config) == expected
    assert p.train_rounds(None) == 6 and p.train_patience(None) == p.TRAIN_PATIENCE
