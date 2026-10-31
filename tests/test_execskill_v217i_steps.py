"""Implant chains use pinned program records only: no task data, model or worker."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (chain, evaluation, manifest, policy, profiles as p, step,
                               v210_import, v213_import, v217_import, v217_implant as imp)
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import Package, Procedure, edits, empty, load, validate
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def setting(root, *, evidence='engineering_fixture', configuration=None):
    return SimpleNamespace(root=root, evidence=evidence, extra={
        'configuration': configuration or p.IMPLANT_V5,
        imp.PIN_KEY: imp.pins(), 'alfworld_v11_import': v210_import.pins()})


def forbid_learning(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('An implant step attempted a learning unit, worker, or call')
    for name in ('_slices', '_run', '_diagnose', '_generate', '_trained', '_accept', '_freeze'):
        monkeypatch.setattr(step, name, forbidden)
    for name in ('run_unit', 'cell_context', 'solver_endpoint', 'role_endpoint', 'audit_judges'):
        monkeypatch.setattr(step.units, name, forbidden)
    monkeypatch.setattr(manifest, 'services_of', forbidden)


def build_chain(st, chain_id):
    start = current = empty(step=chain_id + '/s0', evidence=st.evidence)
    found = []
    for k, bench in enumerate(p.MAIN_V5_ORDER, 1):
        result = step.run_step(st, chain_id, bench, k, current, services=None)
        found.append(result)
        current = result.package
    stages = evaluation.stage_rows(st.root / chain_id, chain_id, p.MAIN_V5_ORDER, current, start)
    return start, found, stages


@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('evidence', ['engineering_fixture', 'implant_v5_test_read'])
def test_both_fixed_imports_preserve_all_program_fields_and_are_one_new_edit(chain_id, evidence):
    parent = empty(step=chain_id + '/s0', evidence=evidence)
    source = imp.pins()[chain_id]
    final = imp.zebra_package(chain_id, parent)
    validate(final, parent)
    assert final.step == chain_id + '/s3-zebralogic' and final.evidence == evidence
    assert final.parent_sha256 == parent.sha256
    assert [(edit.kind, edit.id) for edit in edits(parent, final)] == [('new', source['procedures'][0]['id'])]
    copied = final.procedures[0]
    original = source['procedures'][0]['record']
    assert copied.source.encode() == original['source'].encode()
    assert hashlib.sha256(copied.source.encode()).hexdigest() == source['procedures'][0]['source_sha256']
    assert copied.policy_version == p.POLICY_VERSIONS[p.machinery_configuration(p.MAIN_V5, p.ZEBRA)]
    assert not policy.check(copied.source, version=copied.policy_version)
    clean = lambda row: {k: v for k, v in row.items() if k not in ('evidence', p.RECORD_HASH)}
    assert clean(copied.to_json()) == clean(original)
    assert copied.evidence == evidence
    assert len(copied.source.encode()) == (6872 if chain_id == 'G' else 10955)
    assert v210_import.learning_capacity(final)['remaining_procedures'] == 20


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_all_five_steps_are_zero_call_skips_or_imports_and_resume_exactly(tmp_path, monkeypatch, chain_id):
    forbid_learning(monkeypatch)
    st = setting(tmp_path)
    start, found, stages = build_chain(st, chain_id)
    assert step.training_units(p.IMPLANT_V5) == ()
    assert stages['rows'] == ['C', 'C', 'C', 'S3', 'S3', 'F']
    assert imp.check_stage_rows(tmp_path / chain_id, chain_id, p.MAIN_V5_ORDER,
                               found[-1].package, start, stages) == stages
    assert found[0].package is start and found[1].package is start
    assert found[3].package is found[2].package
    for k in (1, 2, 4):
        row = found[k-1].record
        assert row['learning'] == 'none' and row['decision'] == 'skip'
        assert row['reason'] == 'preregistered_implant_chain_no_learning'
        assert row['package_sha256'] == row['parent_sha256'] == row['chain_parent_sha256']
    for row in found:
        assert row.record['units'] == {}
        assert row.record['candidate_sha256'] is row.record['decision_sha256'] is None
    assert found[2].record['learning'] == found[2].record['decision'] == 'import'
    assert found[4].record['learning'] == found[4].record['decision'] == 'import'
    assert len(found[2].package.procedures) == 1 and len(found[4].package.procedures) == 4
    assert not list(tmp_path.rglob('unit.json')) and not list(tmp_path.rglob('attempt-*'))
    assert build_chain(st, chain_id)[1:] == (found, stages)


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_alf_import_is_exact_main_v5_composition_and_keeps_fixed_zebra_first(tmp_path, monkeypatch, chain_id):
    st = setting(tmp_path / 'implant')
    parent = imp.zebra_package(chain_id, empty(step=chain_id + '/s0', evidence=st.evidence))
    original = v210_import.import_step
    seen = []
    def spy(*args, **kwargs):
        seen.append((args[2], args[3], args[4], args[5].sha256))
        return original(*args, **kwargs)
    monkeypatch.setattr(v210_import, 'import_step', spy)
    child = step.run_step(st, chain_id, 'alfworld', 5, parent, services=None)
    assert seen == [(chain_id, 5, 'alfworld', parent.sha256)]
    old = setting(tmp_path / 'main-v5', configuration=p.MAIN_V5)
    expected = original(old, old.root / chain_id, chain_id, 5, 'alfworld', parent)
    assert (child.package, child.record) == expected
    assert child.package.procedures[0] == parent.procedures[0]
    assert child.package.order == parent.order + tuple(row[0] for row in v210_import.PROCEDURES)
    assert child.record['source_package_sha256'] == v210_import.PACKAGE_SHA256
    assert child.record['reason'] == 'preregistered_alfworld_v11_import'
    validate(child.package, parent)


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_bad_pin_or_nonempty_s2_is_refused_without_writes(tmp_path, chain_id):
    st = setting(tmp_path)
    parent = empty(step=chain_id + '/s0', evidence=st.evidence)
    st.extra[imp.PIN_KEY][chain_id]['package_record_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='source pins differ'):
        step.run_step(st, chain_id, p.ZEBRA, 3, parent, services=None)
    st.extra[imp.PIN_KEY] = imp.pins()
    nonempty = imp.zebra_package(chain_id, parent)
    with pytest.raises(ValueError, match='empty s2'):
        step.run_step(st, chain_id, p.ZEBRA, 3, nonempty, services=None)
    assert not (tmp_path / chain_id).exists()


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_policy_failure_stops_without_repairing_either_program(tmp_path, monkeypatch, chain_id):
    source = imp.pins()[chain_id]
    original = source['procedures'][0]['record']['source']
    parent = empty(step=chain_id + '/s0', evidence='engineering_fixture')
    monkeypatch.setattr(policy, 'check', lambda *args, **kwargs: [
        SimpleNamespace(to_json=lambda: {'reason': 'authored policy refusal'})])
    with pytest.raises(PackageInvalid, match='Policy violations'):
        imp.zebra_package(chain_id, parent, source=source)
    assert source['procedures'][0]['record']['source'] == original
    assert not (tmp_path / chain_id).exists()


@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('damage', ['rows', 'zebra', 'final', 'skip', 'import'])
def test_read_shape_or_step_drift_is_refused_before_cells(tmp_path, chain_id, damage):
    st = setting(tmp_path)
    start, found, stages = build_chain(st, chain_id)
    final = found[-1].package
    if damage == 'rows':
        stages['rows'][4] = 'S4'
    elif damage == 'zebra':
        stages['packages']['S3'] = replace(stages['packages']['S3'], step=chain_id + '/wrong')
    elif damage == 'final':
        final = replace(final, procedures=final.procedures[:1], describer={}, narrowed={})
    else:
        path = tmp_path / chain_id / ('s1-searchqa' if damage == 'skip' else 's3-zebralogic') / 'step.json'
        row = read_json(path)
        fields = {k: v for k, v in row.items() if k not in ('version', 'evidence', p.RECORD_HASH)}
        fields['decision' if damage == 'skip' else 'source_package_sha256'] = 'changed'
        path.write_text(__import__('json').dumps(p.record('step-v2-3', row['evidence'], fields)))
    with pytest.raises(ValueError, match='implant|S3|F is'):
        imp.check_stage_rows(tmp_path / chain_id, chain_id, p.MAIN_V5_ORDER, final, start, stages)


@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('k', [1, 2, 3, 4, 5])
def test_child_process_entry_keeps_first_call_confirmation_but_builds_no_services(tmp_path, monkeypatch, chain_id, k):
    st = setting(tmp_path)
    start, found, _ = build_chain(st, chain_id)
    parent = start if k == 1 else found[k-2].package
    forbid_learning(monkeypatch)
    confirmed = []
    monkeypatch.setattr(step, 'confirmation', lambda *args, **kwargs: confirmed.append((args, kwargs)))
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    monkeypatch.setattr(step.budgets, 'own_ledger', lambda *args: SimpleNamespace(declare=lambda caps: None))
    monkeypatch.setattr(step, 'parent_of', lambda *args: parent)
    spec = tmp_path / 'step-spec.json'
    write_json(spec, {'chain': chain_id, 'bench': p.MAIN_V5_ORDER[k-1], 'k': k})
    result = step.run_unit_spec({'configuration': p.IMPLANT_V5, 'root': str(tmp_path), p.RECORD_HASH: 'authored'}, spec=spec)
    assert result == chain.EXIT_COMPLETE and len(confirmed) == 1
    assert confirmed[0][1] == {'configuration': p.IMPLANT_V5}


def test_structural_smoke_runs_both_persisted_chains_without_learning(tmp_path, monkeypatch):
    forbid_learning(monkeypatch)
    result = imp.structural_smoke(tmp_path)
    assert result['passed'] and result['rows'] == {'G': list(imp.ROWS), 'D': list(imp.ROWS)}
    assert result['model_calls'] == result['sealed_reads'] == result['learning_units'] == 0
    assert all(len(row['S3']) == len(row['F']) == 64 for row in result['packages'].values())
    assert not list(tmp_path.rglob('unit.json'))
