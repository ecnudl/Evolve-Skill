"""The inherited format rule and new audit identity are bound through manifests, S0 and the unchanged environment views."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (alf_confirm_views as cv, alf_smoke, alfworld_format as af,
                               confirm, manifest, profiles as p, step)
from skillopt.execskill.sandbox import client as sandbox
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment, tree

CHILD, PARENT = p.ALFWORLD_V11, p.ALFWORLD_V10


def reseal(value, kind='manifest-v2-9'):
    return p.record(kind, value['evidence'], {key: item for key, item in value.items()
        if key not in ('version', 'evidence', p.RECORD_HASH)})


def made(root, monkeypatch, configuration=CHILD):
    from tests.test_execskill_v29_manifest_smoke import (
        test_complete_manifest_pins_exact_practice_ids_prompts_and_models)
    root.mkdir(parents=True)
    test_complete_manifest_pins_exact_practice_ids_prompts_and_models(root, monkeypatch, configuration)
    return read_json(root / 'new-manifest.json')


def test_manifest_pins_rule_runtime_and_parent_prompts_and_loads_the_same_sheet(tmp_path, monkeypatch):
    value = made(tmp_path / 'manifest', monkeypatch)
    runtime = value['runtime']['alfworld']
    assert runtime[af.CONFIGURATION_KEY] == CHILD and runtime[af.RULE_KEY] == af.RULE
    assert af.validate(runtime, CHILD)
    assert value['data']['alfworld_features']['format_rule'] == af.RULE
    assert 'admissible_min' not in value['data']['alfworld_features']
    assert value['prompt_sha'] == manifest.prompt_sha(CHILD)
    assert value['prompt_sha']['engineer'] == manifest.prompt_sha(PARENT)['engineer']
    assert value['prompt_sha']['v29']['audit'] != manifest.prompt_sha(PARENT)['v29']['audit']
    assert value['data']['alfworld_v11']['runtime_sha256'] == digest(af.environment_runtime(runtime))
    loaded = manifest.load(tmp_path / 'manifest/new-manifest.json', verify=False)
    assert loaded == value and manifest.check(loaded) == value
    setting = manifest.setting_of(value, 'D', docker=FakeDockerCLI(), transport=NO_CALLS)
    assert setting.runtime['alfworld'] == runtime


@pytest.mark.parametrize('tamper', ['both_missing', 'configuration_missing', 'rule_missing',
    'older_configuration', 'unknown_configuration', 'old_rule', 'unknown_rule', 'null_rule'])
def test_sealed_child_manifest_refuses_partial_mismatched_or_unknown_runtime(tmp_path, monkeypatch, tamper):
    value = made(tmp_path / 'manifest', monkeypatch)
    runtime = value['runtime']['alfworld']
    if tamper in ('both_missing', 'configuration_missing'):
        del runtime[af.CONFIGURATION_KEY]
    if tamper in ('both_missing', 'rule_missing'):
        del runtime[af.RULE_KEY]
    if tamper == 'older_configuration':
        runtime[af.CONFIGURATION_KEY] = PARENT
    if tamper == 'unknown_configuration':
        runtime[af.CONFIGURATION_KEY] = 'alfworld-unknown'
    if tamper in ('old_rule', 'unknown_rule', 'null_rule'):
        runtime[af.RULE_KEY] = {'old_rule': '9/10', 'unknown_rule': 'unknown', 'null_rule': None}[tamper]
    with pytest.raises(ValueError, match='format runtime|exact configuration|exact rule'):
        manifest.check(reseal(value))


@pytest.mark.parametrize('tamper', ['configuration', 'both'])
def test_parent_manifest_cannot_pick_up_child_runtime_identity(tmp_path, monkeypatch, tamper):
    value = made(tmp_path / 'manifest', monkeypatch, PARENT)
    runtime = value['runtime']['alfworld']
    if tamper in ('rule', 'both'):
        runtime[af.RULE_KEY] = af.RULE
    if tamper in ('configuration', 'both'):
        runtime[af.CONFIGURATION_KEY] = CHILD
    with pytest.raises(ValueError, match='exact configuration'):
        manifest.check(reseal(value))


@pytest.mark.parametrize('tamper', ['missing_rule', 'different_rule', 'unexpected_threshold'])
def test_manifest_feature_rule_is_pinned_and_no_share_threshold_is_present(tmp_path, monkeypatch, tamper):
    value = made(tmp_path / 'manifest', monkeypatch)
    features = value['data']['alfworld_features']
    if tamper == 'missing_rule':
        del features['format_rule']
    elif tamper == 'different_rule':
        features['format_rule'] = '9/10'
    else:
        features['admissible_min'] = '9/10'
    with pytest.raises(ValueError, match='feature family'):
        manifest.check(reseal(value))


def prepared(root, monkeypatch):
    from tests.test_execskill_v29_confirm_views import authored_preparation
    preparation, game_root, pool, runtime, calls = authored_preparation(root / 'source', monkeypatch)
    path = root / 'confirm-views.json'
    viewed = cv.prepare(path, configuration=CHILD, preparation_file=preparation, data_root=game_root)
    snapshot = tree(root / 'snapshot')
    monkeypatch.setattr(manifest, 'REPO', snapshot)
    selftest = root / 'selftest.json'
    write_json(selftest, p.record('sandbox-selftest', 'smoke', {'passed': True,
        'measured': dict(MEASURED), 'limits': {key: asdict(limits) for key, limits in sandbox.LIMITS.items()}}))
    checked = alf_smoke.collect_s0(root / 's0', preparation_file=preparation, confirm_views=path,
        configuration=CHILD, snapshot_root=snapshot, selftest=selftest, checks={'passed': True})
    provenance = root / 'snapshot-provenance.json'
    write_json(provenance, {'build_tree': str(snapshot), 'git_head': 'e' * 40, 'snapshot_root': str(snapshot),
        'sha256_list_sha256': checked['snapshot_sha256'], 'env_files_absent': True})
    options = {'root': root / 'run', 's0_file': root / 's0' / alf_smoke.S0_FILE, 'provenance': provenance,
        'roles_repo': root / 'unread-credentials', 'elucid_env': root / 'unread-elucid.env',
        'route_b_env': root / 'unread-route.env', 'smoke_chain': 'D', 'environment_found': fake_environment(),
        'configuration': CHILD}
    return preparation, pool, runtime, calls, viewed, checked, options


def test_full_s0_manifest_step_confirmation_and_fixtures_use_bound_judge_and_original_views(tmp_path, monkeypatch):
    preparation, pool, runtime, calls, viewed, checked, options = prepared(tmp_path, monkeypatch)
    bound = af.bind(runtime, CHILD)
    assert checked['passed'] and checked['configuration'] == CHILD
    assert checked['judge_runtime'] == bound and checked['runtime']['alfworld'] == runtime
    assert checked['alf_confirm_views'] == viewed and checked['slice_ids']['confirm'] == viewed['ids']
    assert checked['slice_counts']['confirm'] == 40 and len(calls) == 80
    assert alf_smoke.fixture_items(bound) == alf_smoke.fixture_items(runtime)
    assert alf_smoke._slices(pool, bound) == alf_smoke._slices(pool, runtime)
    result = alf_smoke.make_manifest(tmp_path / 'manifest.json', **options)
    assert result['runtime']['alfworld'] == bound
    assert result['data']['alf_confirm_views'] == viewed
    assert manifest.check(result) == result
    setting = manifest.setting_of(result, 'D', docker=FakeDockerCLI(), transport=NO_CALLS)
    st = SimpleNamespace(bench='alfworld', setting=setting, runtime=lambda: bound,
        root=tmp_path / 'step', chain='D', k=1, smoke=None)
    cut = step._cut(st, [])
    assert len(cut['confirm']) == 40
    assert all(row['views_runtime_sha256'] == digest(runtime) for row in cut['confirm'])
    assert all(row['public']['routing_view'] == viewed['views'][row['task_id']]['view'] for row in cut['confirm'])
    assert all('routing_view' not in row['public'] for row in confirm.slice_items(CHILD, pool)[0])
    st.root.mkdir()
    write_json(st.root / step.SLICES_FILE, p.record('step-slices', 'engineering_fixture', {
        'chain': 'D', 'k': 1, 'bench': 'alfworld',
        'slices': {name: [row['task_id'] for row in rows] for name, rows in cut.items()}}))
    assert step._slices(st) == cut
    by_id = {row['task_id']: row for row in cut['confirm']}
    identities = step._confirm_identities(st, by_id, list(by_id), SimpleNamespace(sha256='a' * 64),
        SimpleNamespace(sha256='b' * 64), {})
    for key, arms in identities.items():
        for arm, identity in arms.items():
            assert identity['runtime_sha256'] == digest(bound)
            assert identity['view_sha256'] == by_id[key]['public']['routing_view_sha256']
            assert identity['package_sha256'] == ('a' if arm == 'S' else 'b') * 64
    assert len(calls) == 80  # No further resets or environment calls.


@pytest.mark.parametrize('tamper', ['missing', 'older_identity', 'rule', 'environment'])
def test_s0_bound_judge_sheet_cannot_be_removed_or_changed_before_manifest(tmp_path, monkeypatch, tamper):
    _, _, runtime, _, _, checked, options = prepared(tmp_path, monkeypatch)
    if tamper == 'missing':
        del checked['judge_runtime']
    elif tamper == 'older_identity':
        checked['judge_runtime'][af.CONFIGURATION_KEY] = PARENT
    elif tamper == 'rule':
        checked['judge_runtime'][af.RULE_KEY] = '9/10'
    else:
        checked['judge_runtime']['seed'] += 1
    options['s0_file'] = tmp_path / 'changed-s0.json'
    write_json(options['s0_file'], reseal(checked, 'alfworld-s0'))
    with pytest.raises(ValueError, match='S0 pins'):
        alf_smoke.make_manifest(tmp_path / 'manifest.json', **options)
    assert not (tmp_path / 'manifest.json').exists()


def test_parent_s0_is_rejected_before_child_manifest(tmp_path, monkeypatch):
    _, _, _, _, _, checked, options = prepared(tmp_path, monkeypatch)
    checked['configuration'] = PARENT
    options['s0_file'] = tmp_path / 'changed-s0.json'
    write_json(options['s0_file'], reseal(checked, 'alfworld-s0'))
    with pytest.raises(ValueError, match='passing ALFWorld S0'):
        alf_smoke.make_manifest(tmp_path / 'manifest.json', **options)


@pytest.mark.parametrize('tamper', ['rule', 'configuration', 'both'])
def test_historical_five_benchmark_manifest_refuses_new_rule_in_alf_sheet(tmp_path, monkeypatch, tamper):
    from tests.test_execskill_manifest import given
    monkeypatch.setattr(manifest, 'pin_code', lambda: {'authored.py': 'c' * 64})
    monkeypatch.setattr(manifest, 'loaded_code', lambda: {'authored.py'})
    value = manifest.make(tmp_path / 'old-manifest.json', evidence='engineering_fixture',
        environment_found=fake_environment(), measured=MEASURED, **given(tmp_path))
    runtime = value['runtime']['alfworld']
    if tamper in ('rule', 'both'):
        runtime[af.RULE_KEY] = af.RULE
    if tamper in ('configuration', 'both'):
        runtime[af.CONFIGURATION_KEY] = CHILD
    with pytest.raises(ValueError, match='historical runtime'):
        manifest.check(reseal(value, 'manifest'))


@pytest.mark.parametrize('runtime_config,expected', [(CHILD, PARENT), (PARENT, CHILD)])
def test_same_format_rule_never_allows_cross_configuration_runtime_binding(runtime_config, expected):
    runtime = af.bind({'seed': 42}, runtime_config)
    assert runtime[af.RULE_KEY] == p.alfworld_format_rule(expected)
    with pytest.raises(ValueError, match='exact configuration'):
        af.validate(runtime, expected)
    with pytest.raises(ValueError, match='exact configuration'):
        af.bind(runtime, expected)
