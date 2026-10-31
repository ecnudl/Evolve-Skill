"""v2.16 lean smoke and scripted repair-cycle demonstration, entirely authored/offline."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import budgets, diagnostics, evaluation, manifest, profiles as p, smoke, units, zebra_smoke
from skillopt.execskill.sandbox import client
from tests import test_execskill_v215_smoke as parent_smoke
from tests import test_execskill_v212_smoke as lean_smoke
from tests import test_execskill_v212_evaluation as eval_parent
from tests import test_execskill_v212_acceptance as accept_parent
from tests.test_execskill_manifest import FakeDockerCLI
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CHILD, PARENT = 'zebra-pc-v15', 'zebra-pc-v14'


def prepared(root, monkeypatch, *, worker_configuration=CHILD):
    monkeypatch.setattr(parent_smoke, 'CHILD', CHILD)
    return parent_smoke.prepared(root, monkeypatch, worker_configuration=worker_configuration)


def test_s0_manifest_inherits_worker_diagnostics_fc_pins_and_new_cycle_caps(tmp_path, monkeypatch):
    checked, value = prepared(tmp_path, monkeypatch)
    assert checked['passed'] and checked['sealed_reads'] == 0 and checked['configuration'] == CHILD
    assert checked['slice_counts'] == {'smoke': 10, 'run': 60, 'accept': 100, 'spare': 3}
    assert manifest.check(value) == value
    assert value['data']['launchable_chains'] == ['D']
    assert value['caps'] == budgets.caps(CHILD)
    assert value['sandbox']['worker_sha256'] == checked['worker_sha256'] == client.worker_sha256(configuration=PARENT)
    assert value['prompt_sha'] == manifest.prompt_sha(CHILD)
    features = value['data']['zebra_pc_features']['outcome_engineer']
    assert features['diagnostics'] == diagnostics.identity()
    assert features['test_freshness'] == p.ZEBRA_PC_V14_TEST_FRESHNESS
    assert features['repair_cycle']['inert_repairs'] == 3
    assert features['repair_cycle']['audit_fixes'] == 2 and features['repair_cycle']['audits'] == 3
    assert value['data']['smoke_results'] == {}
    assert value['data']['test_read_estimate'] == {'D': 1768000}
    assert value['data']['confirm']['freshness'] == p.CONFIRM_FRESHNESS[CHILD]


@pytest.mark.parametrize('configuration', [None, 'zebra-pc-v13', PARENT])
def test_s0_requires_child_selftest_identity_even_when_worker_bytes_are_inherited(tmp_path, monkeypatch, configuration):
    with pytest.raises(ValueError, match='child diagnostics worker selftest'):
        prepared(tmp_path, monkeypatch, worker_configuration=configuration)


@pytest.mark.parametrize('field', ['worker', 'caps', 'cycle', 'diagnostics'])
def test_resealed_manifest_rejects_drift_from_child_registration(tmp_path, monkeypatch, field):
    _, value = prepared(tmp_path, monkeypatch)
    fields = deepcopy({key: item for key, item in value.items() if key not in ('version', 'evidence', p.RECORD_HASH)})
    if field == 'worker':
        fields['sandbox']['worker_sha256'] = client.worker_sha256()
    elif field == 'caps':
        fields['caps'] = budgets.caps(PARENT)
    else:
        features = fields['data']['zebra_pc_features']['outcome_engineer']
        if field == 'cycle':
            features['repair_cycle']['inert_repairs'] = 1
        else:
            features['diagnostics']['engineer_input_bytes'] = 0
    with pytest.raises(ValueError):
        manifest.check(p.record(manifest.KIND, value['evidence'], fields))


def test_child_structural_s2_s3_and_se6_keep_parent_lean_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(lean_smoke, 'CHILD', CHILD)
    lean_smoke.test_authored_s2_s3_fault_repair_cache_and_fc_projection(tmp_path, monkeypatch)


def test_child_measured_stage_plan_remains_ordered_resumable_and_sealed(tmp_path, monkeypatch):
    monkeypatch.setattr(lean_smoke, 'CHILD', CHILD)
    lean_smoke.test_measured_smoke_stage_plan_is_ordered_resumable_and_keeps_test_sealed(tmp_path, monkeypatch)
    assert zebra_smoke.stages_of(CHILD) == zebra_smoke.stages_of(PARENT) == ('S1', 'S2', 'S3', 'SE6')


def test_child_owner_consent_and_full_independent_acceptance_anchor(tmp_path):
    value = eval_parent.consent()
    write_json(tmp_path / 'consent.json', value)
    assert evaluation.consent(tmp_path, CHILD) == value
    sealed = accept_parent.seal(tmp_path, configuration=CHILD)
    assert sealed['configuration'] == CHILD and sealed['rule'] == p.ACCEPT_RULES[CHILD]
    sample = sealed['reuse']['card_sample']
    assert sample['coverage'] == 'full_independent_astar' and len(sample['items']) == 100
    assert sealed['placebo_y'] is None and sealed['placebo_i'] is None


@pytest.mark.parametrize('accepted', [False, True])
def test_child_read_requires_adoption_and_occurs_once(tmp_path, monkeypatch, accepted):
    monkeypatch.setattr(eval_parent, 'CONFIG', CHILD)
    eval_parent.test_chain_end_reads_once_only_when_a_package_was_accepted(tmp_path, monkeypatch, accepted)


def test_all_worker_factories_carry_child_config_but_frozen_worker_bytes(tmp_path, monkeypatch):
    _, value = prepared(tmp_path, monkeypatch)
    value = {**value, 'slot_root': str(tmp_path / 'slots'), 'history_root': str(tmp_path / 'history')}
    monkeypatch.setattr(manifest, '_clients', lambda *args, **kwargs:
                        lambda *a, **kw: pytest.fail('No credentialed client in worker wiring fixture'))
    setting = manifest.setting_of(value, 'D', docker=FakeDockerCLI())
    services = manifest.services_of(value, 'D', setting=setting)
    assert setting.sandbox['diagnostics_configuration'] == CHILD
    assert services.workers.keywords['diagnostics_configuration'] == CHILD
    captured = []
    monkeypatch.setattr(units, 'Worker', lambda **options: captured.append(options))
    units.cell_context(setting, tmp_path / 'attempt', SimpleNamespace(model=p.CHAINS['D'])).worker(p.ZEBRA)
    assert captured[0]['diagnostics_configuration'] == CHILD


@pytest.mark.parametrize('correct_hash', [True, False])
def test_selftest_runs_frozen_diagnostics_worker_under_child_identity(tmp_path, monkeypatch, correct_hash):
    monkeypatch.setattr(parent_smoke, 'CHILD', CHILD)
    parent_smoke.test_child_selftest_selects_and_requires_its_executed_worker_hash(tmp_path, monkeypatch, correct_hash)


def test_offline_cycle_demonstration_survives_repair_after_inert_audit_fix(tmp_path, monkeypatch, record_testsuite_property):
    """Script the brief's full cycle through real checks, requests, replays and audits."""
    from skillopt.execskill import audit, engineer_v216
    from tests.test_execskill_v291_engineer import run
    from tests.test_execskill_v29_audit import Judge
    sources = [
        'def before_call(view,state):\n    return {"diagnostics":["First authored clue remains unresolved."]}\n',
        'def before_call(view,state):\n    return {"facts":["The public question was read."],'
        '"diagnostics":["First authored clue was understood."]}\n',
        'def before_call(view,state):\n    return {"diagnostics":["An audit-adjusted relation remains unresolved."]}\n',
        'def before_call(view,state):\n    return {"facts":["The visible public clue was read."],'
        '"diagnostics":["The revised relation was understood."]}\n',
    ]
    original, seen = audit.audit1, []
    def scripted(ctx, change, report):
        seen.append(change.source)
        ctx.audit_judges = {name: Judge(template='P1' if len(seen) == 1 else None) for name in ('G', 'D')}
        return original(ctx, change, report)
    monkeypatch.setattr(audit, 'audit1', scripted)
    ctx, found, record = run(*sources, configuration=CHILD)
    assert found is not None and found.procedures[0].source.strip() == sources[-1].strip()
    row = record['changes'][0]
    cycle = row['repair_cycle']
    assert row['survived'] and row['kept_attempt'] == 3 and not row['inert'] and not row['deferred']
    assert [attempt['inert'] for attempt in row['attempts']] == [True, False, True, False]
    assert [step['kind'] for step in cycle['steps']] == ['inert_repair', 'audit', 'audit_fix', 'inert_repair', 'audit']
    assert cycle['inert_repairs'] == record['inert_repair_calls'] == 2
    assert cycle['audit_fixes'] == record['audit_fix_calls'] == 1
    assert cycle['audits'] == len(row['audits']) == 2 and cycle['stop_reason'] == 'survived'
    assert [bool(value['confirmed']) for value in row['audits']] == [True, False]
    assert [source.strip() for source in seen] == [sources[1].strip(), sources[3].strip()]
    wires = [json.loads(wire['user']) for wire in ctx.roles.wire if wire['role'] == 'engineer']
    repairs = [wire for wire in wires if wire['request'] == 'inert_repair']
    assert repairs[0]['change']['source'].strip() == sources[0].strip() and repairs[1]['change']['source'].strip() == sources[2].strip()
    assert 'First authored clue remains unresolved.' in json.dumps(repairs[0]['evidence']['engineer_diagnostics'])
    assert 'An audit-adjusted relation remains unresolved.' in json.dumps(repairs[1]['evidence']['engineer_diagnostics'])
    audit_fix = next(wire for wire in wires if wire['request'] == 'audit_fix')
    assert audit_fix['change']['source'].strip() == sources[1].strip()
    assert audit_fix['evidence']['notes'] == {'fired': 1, 'nonempty': 1, 'empty': 0, 'exceptions': 0}
    assert 'First authored clue was understood.' in json.dumps(audit_fix['evidence']['engineer_diagnostics'])
    assert audit_fix['instruction'].endswith(engineer_v216.AUDIT_FIX_PARAGRAPH)
    assert audit_fix['instruction'].count(engineer_v216.AUDIT_FIX_PARAGRAPH) == 1
    assert record['audit_tokens'] == {judge: {key: sum(value['tokens'][judge][key] for value in row['audits'])
                                            for key in ('input', 'output', 'charged')} for judge in ('G', 'D')}
    report = {'evidence': 'authored_offline_cycle_demonstration', 'configuration': CHILD,
              'model_calls': 0, 'survived': row['survived'], 'repair_cycle': cycle,
              'inert_attempts': [attempt['inert'] for attempt in row['attempts']],
              'kept_attempt': row['kept_attempt'], 'audit_tokens_are_synthetic': True}
    write_json(tmp_path / 'cycle-demonstration.json', report)
    record_testsuite_property('v216_offline_cycle_demonstration', json.dumps(report, sort_keys=True))
