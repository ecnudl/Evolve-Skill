"""v2.15 S0, manifest, structural fixtures and measured-stage plan; all calls are fake."""
from copy import deepcopy
import math
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import budgets, diagnostics, evaluation, manifest, profiles as p, smoke, units, zebra_smoke as zsmoke
from skillopt.execskill.sandbox import client as sandbox
from tests.test_execskill_manifest import FakeDockerCLI
from tests import test_execskill_v212_acceptance as acceptance_parent
from tests import test_execskill_v212_evaluation as evaluation_parent
from tests import test_execskill_v212_smoke as smoke_parent
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CHILD = p.ZEBRA_PC_V14


def prepared(root, monkeypatch, *, worker_configuration=CHILD):
    monkeypatch.setattr(smoke_parent, 'CHILD', CHILD)
    original = p.record
    def record(name, evidence, fields):
        if name == 'sandbox-selftest' and worker_configuration is not None:
            fields = {**fields, 'configuration': worker_configuration,
                      'worker_sha256': sandbox.worker_sha256(configuration=worker_configuration)}
        return original(name, evidence, fields)
    monkeypatch.setattr(p, 'record', record)
    return smoke_parent.prepared(root, monkeypatch)


def test_s0_manifest_pins_diagnostics_caps_freshness_and_exact_fc_anchor(tmp_path, monkeypatch):
    checked, value = prepared(tmp_path, monkeypatch)
    assert checked['passed'] and checked['sealed_reads'] == 0 and checked['configuration'] == CHILD
    assert checked['slice_counts'] == {'smoke': 10, 'run': 60, 'accept': 100, 'spare': 3}
    assert checked['worker_sha256'] == sandbox.worker_sha256(configuration=CHILD)
    assert manifest.check(value) == value and value['configuration'] == CHILD
    assert value['data']['launchable_chains'] == ['D']
    assert value['caps'] == budgets.caps(CHILD)
    assert value['sandbox']['worker_sha256'] == checked['worker_sha256']
    assert value['prompt_sha'] == manifest.prompt_sha(CHILD)
    assert value['clients']['solver']['D']['backend'] == 'northgate'
    assert value['clients']['solver']['D']['model'] == p.CHAINS['D']
    assert value['clients']['routes']['D']['B']['model'] == 'deepseek-v4-flash'
    assert value['data']['test_read_estimate'] == {'D': math.ceil(3400 * (200 + 200 * 1.6))}
    assert value['data']['test_read_terms'] == {'D': {p.ZEBRA: str(1768000)}}
    assert value['data']['smoke_results'] == {}
    assert len(value['data']['confirm']['ids']) == 40
    assert value['data']['confirm']['freshness'] == p.CONFIRM_FRESHNESS[CHILD]
    features = value['data']['zebra_pc_features']['outcome_engineer']
    assert features['diagnostics'] == diagnostics.identity()
    assert features['test_freshness'] == p.ZEBRA_PC_V14_TEST_FRESHNESS
    assert features['audit']['limits']['fault_feedback']['engineer_cap'] == 497727616


@pytest.mark.parametrize('field', ['diagnostics', 'test_freshness', 'prompt', 'cap', 'worker'])
def test_resealed_manifest_cannot_drift_from_child_diagnostics_or_caps(tmp_path, monkeypatch, field):
    _, value = prepared(tmp_path, monkeypatch)
    fields = deepcopy({key: entry for key, entry in value.items()
                       if key not in ('version', 'evidence', p.RECORD_HASH)})
    if field == 'diagnostics':
        fields['data']['zebra_pc_features']['outcome_engineer']['diagnostics']['engineer_input_bytes'] = 0
    elif field == 'test_freshness':
        fields['data']['zebra_pc_features']['outcome_engineer']['test_freshness'] = 'first_read'
    elif field == 'prompt':
        fields['prompt_sha']['engineer'] = manifest.prompt_sha(p.ZEBRA_PC_V13)['engineer']
    elif field == 'worker':
        fields['sandbox']['worker_sha256'] = sandbox.worker_sha256()
    else:
        fields['caps'] = budgets.caps(p.ZEBRA_PC_V13)
    with pytest.raises(ValueError):
        manifest.check(p.record(manifest.KIND, value['evidence'], fields))


def test_child_snapshot_contains_s0_public_fixture_and_collects_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke_parent, 'CHILD', CHILD)
    smoke_parent.test_v13_snapshot_copies_only_required_public_document_fixture_and_collects_s0(tmp_path)


def test_structural_s2_s3_and_measured_fc_projection_use_child_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke_parent, 'CHILD', CHILD)
    smoke_parent.test_authored_s2_s3_fault_repair_cache_and_fc_projection(tmp_path, monkeypatch)


def test_measured_plan_keeps_parent_four_stages_ordering_resume_and_no_panel_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke_parent, 'CHILD', CHILD)
    smoke_parent.test_measured_smoke_stage_plan_is_ordered_resumable_and_keeps_test_sealed(tmp_path, monkeypatch)
    assert zsmoke.stages_of(CHILD) == ('S1', 'S2', 'S3', 'SE6')


def test_exact_fc_consent_is_required_without_sheet_qualification(tmp_path):
    value = evaluation_parent.consent()
    value['note'] = 'Authored consent-shape fixture for zebra-pc-v14; no real read is authorized.'
    write_json(tmp_path / 'consent.json', value)
    assert evaluation.consent(tmp_path, CHILD) == value
    assert set(value) == p.CONSENT_FIELDS
    for index, change in enumerate(({'multi_arm_arms': ['F', 'C', 'B']}, {'sheet_test_qualification': True}, {'by': 'agent'})):
        altered = tmp_path / str(index)
        write_json(altered / 'consent.json', {**value, **change})
        with pytest.raises(ValueError, match='consent'):
            evaluation.consent(altered, CHILD)


@pytest.mark.parametrize('accepted', [False, True])
def test_child_chain_end_read_occurs_once_only_after_adoption(tmp_path, monkeypatch, accepted):
    monkeypatch.setattr(evaluation_parent, 'CONFIG', CHILD)
    evaluation_parent.test_chain_end_reads_once_only_when_a_package_was_accepted(tmp_path, monkeypatch, accepted)


def test_child_acceptance_preserves_full_independent_card_and_no_placebo(tmp_path):
    sealed = acceptance_parent.seal(tmp_path, configuration=CHILD)
    assert sealed['configuration'] == CHILD and sealed['rule'] == p.ACCEPT_RULES[CHILD]
    sample = sealed['reuse']['card_sample']
    assert sample['coverage'] == 'full_independent_astar'
    assert sample['items'] == sealed['plan']['astar'] and len(sample['items']) == 100
    assert sealed['placebo_y'] is None and sealed['placebo_i'] is None
    assert set(sealed['packages']) == {'candidate', 'parent', 'card'}
    for item in sample['items']:
        assert next(row for row in sealed['reuse']['classes']['real'][item] if 'C' in row['arms']) == {
            'representative': 'C', 'arms': ['C']}


@pytest.mark.parametrize('worker_configuration', [None, p.ZEBRA_PC_V13])
def test_s0_refuses_a_legacy_worker_selftest(tmp_path, monkeypatch, worker_configuration):
    with pytest.raises(ValueError, match='child diagnostics worker selftest'):
        prepared(tmp_path, monkeypatch, worker_configuration=worker_configuration)


def test_setting_and_all_worker_factories_carry_child_worker_without_building_clients(tmp_path, monkeypatch):
    _, value = prepared(tmp_path, monkeypatch)
    value = {**value, 'slot_root': str(tmp_path / 'slots'), 'history_root': str(tmp_path / 'history')}
    clients = lambda *a, **kw: pytest.fail('Setting construction cannot create a credentialed client')
    monkeypatch.setattr(manifest, '_clients', lambda *a, **kw: clients)
    setting = manifest.setting_of(value, 'D', docker=FakeDockerCLI())
    assert setting.sandbox['diagnostics_configuration'] == CHILD
    services = manifest.services_of(value, 'D', setting=setting)
    assert services.workers.keywords['diagnostics_configuration'] == CHILD
    captured = []
    monkeypatch.setattr(units, 'Worker', lambda **options: captured.append(options))
    endpoint = SimpleNamespace(model=p.CHAINS['D'])
    units.cell_context(setting, tmp_path / 'attempt', endpoint).worker(p.ZEBRA)
    assert captured[0]['diagnostics_configuration'] == CHILD


@pytest.mark.parametrize('correct_hash', [True, False])
def test_child_selftest_selects_and_requires_its_executed_worker_hash(tmp_path, monkeypatch, correct_hash):
    calls = []
    monkeypatch.setattr(smoke, '_escape_report', lambda *a, **kw: {})
    monkeypatch.setattr(smoke, 'escape_rows', lambda value: {'authored': True})
    monkeypatch.setattr(smoke, 'view_bytes', lambda paths: {'items': 1, 'p99': 3})
    def factory(**options):
        calls.append(options)
        result = SimpleNamespace(ping=lambda: {'vsz_kib': 1, 'rss_kib': 2,
            'worker_sha256': sandbox.worker_sha256(configuration=CHILD if correct_hash else None)},
            close=lambda: None)
        result.start = lambda *a, **kw: result
        return result
    if correct_hash:
        value = smoke.sandbox_selftest(tmp_path / 'selftest', item_files=[], docker=FakeDockerCLI(),
                                      worker=factory, configuration=CHILD)
        assert value['configuration'] == CHILD
        assert value['worker_sha256'] == sandbox.worker_sha256(configuration=CHILD)
    else:
        with pytest.raises(ValueError, match='executed its diagnostics worker'):
            smoke.sandbox_selftest(tmp_path / 'selftest', item_files=[], docker=FakeDockerCLI(),
                                   worker=factory, configuration=CHILD)
    assert calls[0]['diagnostics_configuration'] == CHILD
