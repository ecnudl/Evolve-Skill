"""Pinned training-side program reconstruction and import; no benchmark data or calls."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import shutil
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import chain, manifest, policy, profiles as p, step, v217_import as imp
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import Procedure, edits, empty, load, validate
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def inputs():
    return ((imp.FIXTURE / 'inputs/g3r2-p-zebralogic-3-3.py').read_bytes(),
            (imp.FIXTURE / 'inputs/g3r2-p-zebralogic-3-3.procedure.json').read_bytes())


def setting(tmp_path, *, evidence='engineering_fixture'):
    return SimpleNamespace(root=tmp_path, evidence=evidence,
        extra={'configuration': p.ZEBRA_HP_G3R2, imp.PIN_KEY: imp.pins()})


def test_exact_stored_fields_and_program_build_one_new_procedure_on_empty():
    source, stored_record = inputs()
    original = json.loads(stored_record)
    parent, package = imp.build(source, stored_record)
    validate(package, parent)
    assert len(source) == 6_872 and hashlib.sha256(source).hexdigest() == imp.SOURCE_SHA256
    assert not parent.procedures and package.sha256 == imp.PACKAGE_SHA256
    assert package == load(imp.FIXTURE / 'packages' / (imp.PACKAGE_SHA256 + '.json'))
    assert len(package.procedures) == len(package.for_bench(p.ZEBRA)) == 1
    procedure = package.procedures[0]
    assert [(edit.kind, edit.id) for edit in edits(parent, package)] == [('new', 'p-zebralogic-3-3')]
    assert procedure.source.encode() == source
    assert len(procedure.description) == 600
    assert procedure.hooks == ('applies', 'before_call') and procedure.header == 'zebra-csp-solve-v2'
    assert procedure.max_note_chars == 2200 and procedure.state_bytes == 0
    assert procedure.requests_second_call is False
    assert procedure.excluded_benches == procedure.replay_tests == ()
    assert procedure.accepted_at is None
    assert procedure.lineage == original['lineage']
    assert procedure.lineage['parent'] is procedure.lineage['revises'] is None
    changed = {key for key in original if original[key] != procedure.to_json()[key]}
    assert changed == {'evidence', p.RECORD_HASH}
    assert procedure.policy_version == p.POLICY_VERSIONS[p.machinery_configuration(p.MAIN_V5, p.ZEBRA)]
    assert procedure.policy_version == policy.POLICY_VERSION_V29
    assert not policy.check(procedure.source, version=procedure.policy_version)


def test_all_input_copies_are_exact_and_candidate_is_provenance_only():
    expected = {'g3r2-p-zebralogic-3-3.py': imp.SOURCE_SHA256,
        'g3r2-p-zebralogic-3-3.procedure.json': imp.SOURCE_PROCEDURE_FILE_SHA256,
        'g3r2-candidate-4223c1c0.package.json': imp.SOURCE_CANDIDATE_FILE_SHA256}
    for name, sha in expected.items():
        assert hashlib.sha256((imp.FIXTURE / 'inputs' / name).read_bytes()).hexdigest() == sha
    historical = p.verified(read_json(imp.FIXTURE / 'inputs/g3r2-candidate-4223c1c0.package.json'), 'package')
    assert historical['order'] == ['p-zebralogic-3-3', 'p-zebralogic-3-4']
    assert historical[p.RECORD_HASH] == imp.SOURCE_CANDIDATE_SHA256
    assert historical['parent_sha256'] == imp.SOURCE_PARENT_SHA256
    assert empty(step='G/s0', evidence='main_v5_real_run').sha256 == imp.SOURCE_PARENT_SHA256
    assert imp.build(*inputs())[1].order == ('p-zebralogic-3-3',)


def test_provenance_states_historical_audit_selection_and_exact_hash_changes():
    pins = imp.pins()
    provenance = pins['provenance']
    assert pins['origin'] == 'main-v5/G/s3-zebralogic/engineer-r2'
    assert pins['evidence_kind'] == provenance['evidence_kind'] == 'post_hoc_selected_upper_bound'
    origin = provenance['origin']
    assert origin['source_root'] == '/data/execskill-20261031-main-v5' and not origin['root_accessed']
    assert (origin['chain'], origin['step'], origin['round']) == ('G', 3, 2)
    assert origin['unit'] == 'G/s3-zebralogic/engineer-r2'
    assert origin['candidate_package_sha256'] == imp.SOURCE_CANDIDATE_SHA256
    assert origin['procedure_record_sha256'] == imp.SOURCE_PROCEDURE_SHA256
    assert origin['parent_package_sha256'] == imp.SOURCE_PARENT_SHA256
    assert origin['source_sha256'] == imp.SOURCE_SHA256 and origin['adopted_by_method'] is False
    audit = provenance['historical_checks']['v29_llm_audit']
    assert audit == {'phase': 1, 'decision': 'pass', 'sampled_situations': 12,
                     'eligible_situations': 16, 'confirmed_findings': 0}
    assert provenance['validation']['program_executed'] is False
    assert provenance['validation']['model_calls'] == provenance['validation']['sealed_reads'] == 0
    fixture = imp.build(*inputs())[1].to_json()
    original = read_json(imp.FIXTURE / 'inputs/g3r2-candidate-4223c1c0.package.json')
    changed = {key for key in original if original[key] != fixture[key]}
    assert changed == set(provenance['hash_explanation']['package_changed_fields'])
    assert provenance['hash_explanation']['procedure_changed_fields'] == ['evidence', p.RECORD_HASH]


@pytest.mark.parametrize('name', [
    'inputs/g3r2-p-zebralogic-3-3.py', 'inputs/g3r2-p-zebralogic-3-3.procedure.json',
    'inputs/g3r2-candidate-4223c1c0.package.json', 'provenance.json',
    'packages/' + imp.PACKAGE_SHA256 + '.json', 'packages/' + imp.PARENT_SHA256 + '.json',
    'procedures/' + imp.PROCEDURE_SHA256 + '.json'])
def test_any_fixed_file_change_is_refused_before_import(tmp_path, name):
    fixture = tmp_path / 'fixture'
    shutil.copytree(imp.FIXTURE, fixture)
    path = fixture / name
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='fixture file hash differs'):
        imp.pins(fixture=fixture)


@pytest.mark.parametrize('part', ['source', 'stored_record'])
def test_changed_input_refused_without_rewriting_program(part):
    source, record = inputs()
    with pytest.raises(ValueError, match='input pin'):
        imp.build(source + b'\n' if part == 'source' else source,
                  record + b'\n' if part == 'stored_record' else record)


def test_resealed_source_modification_is_refused(tmp_path):
    fixture = tmp_path / 'fixture'
    shutil.copytree(imp.FIXTURE, fixture)
    original = Procedure.from_json(imp.pins()['procedures'][0]['record'])
    changed = replace(original, source=original.source + '\n# changed\n')
    (fixture / 'procedures' / (imp.PROCEDURE_SHA256 + '.json')).write_text(json.dumps(changed.to_json()))
    with pytest.raises(ValueError, match='fixture file hash differs'):
        imp.pins(fixture=fixture)


def test_policy_failure_stops_reconstruction_without_repair(monkeypatch):
    source, record = inputs()
    monkeypatch.setattr(policy, 'check', lambda *args, **kwargs: [
        SimpleNamespace(to_json=lambda: {'reason': 'authored policy refusal'})])
    with pytest.raises(PackageInvalid, match='Policy violations'):
        imp.build(source, record)
    assert inputs() == (source, record)


@pytest.mark.parametrize('evidence', ['engineering_fixture', 'zebra_hp_g3r2_test_read'])
def test_import_rebinds_only_evidence_and_calls_no_learning_or_solver(tmp_path, monkeypatch, evidence):
    st = setting(tmp_path, evidence=evidence)
    parent = empty(step='G/s0', evidence=evidence)
    def forbidden(*args, **kwargs):
        pytest.fail('The fixed import invoked learning or evaluation before the read')
    for name in ('_slices', '_run', '_diagnose', '_generate', '_trained', '_accept', '_freeze'):
        monkeypatch.setattr(step, name, forbidden)
    for name in ('run_unit', 'cell_context', 'solver_endpoint', 'role_endpoint', 'audit_judges'):
        monkeypatch.setattr(step.units, name, forbidden)
    found = step.run_step(st, 'G', p.ZEBRA, 1, parent, services=None)
    record = found.record
    assert record['learning'] == record['decision'] == 'import'
    assert record['evidence_kind'] == imp.EVIDENCE_KIND
    assert record['candidate_sha256'] is record['decision_sha256'] is None and record['units'] == {}
    assert record['chain_parent_sha256'] == found.package.parent_sha256 == parent.sha256
    imported = load(tmp_path / 'G/packages' / (record['parent_sha256'] + '.json'))
    assert imported.parent_sha256 == imp.PACKAGE_SHA256
    assert found.package.procedures == imported.procedures and imported.evidence == evidence
    copied = found.package.procedures[0]
    original = imp.pins()['procedures'][0]
    without_stamp = lambda row: {k: v for k, v in row.items() if k not in ('evidence', p.RECORD_HASH)}
    assert without_stamp(copied.to_json()) == without_stamp(original['record'])
    assert copied.source.encode() == inputs()[0]
    provenance = p.verified(read_json(tmp_path / 'G/s1-zebralogic/import.json'), 'import-v2-17')
    assert provenance['source'] == imp.pins() and provenance['program_bytes_changed'] is False
    assert provenance['origin'] == imp.ORIGIN and provenance['evidence_kind'] == imp.EVIDENCE_KIND
    assert step.run_step(st, 'G', p.ZEBRA, 1, parent, services=None) == found
    assert not list((tmp_path / 'G').glob('s1-zebralogic/*/unit.json'))


@pytest.mark.parametrize('field', ['source_sha256', 'record_sha256', 'file_sha256'])
def test_manifest_pin_drift_refused_before_write(tmp_path, field):
    st = setting(tmp_path)
    st.extra[imp.PIN_KEY]['procedures'][0][field] = '0' * 64
    with pytest.raises(ValueError, match='pins differ'):
        imp.import_step(st, tmp_path / 'G', 'G', 1, p.ZEBRA, empty(step='G/s0', evidence=st.evidence))
    assert not (tmp_path / 'G').exists()


@pytest.mark.parametrize(('chain_id', 'k', 'bench'), [('D', 1, p.ZEBRA), ('G', 2, p.ZEBRA), ('G', 1, 'alfworld')])
def test_import_rejects_other_chains_or_steps_before_write(tmp_path, chain_id, k, bench):
    st = setting(tmp_path)
    with pytest.raises(ValueError, match='chain G step 1'):
        imp.import_step(st, tmp_path / chain_id, chain_id, k, bench, empty(step='G/s0', evidence=st.evidence))
    assert not (tmp_path / chain_id).exists()


def test_empty_import_and_nonempty_parent_are_refused_before_write(tmp_path, monkeypatch):
    st = setting(tmp_path)
    parent, nonempty = imp.build(*inputs())
    with pytest.raises(ValueError, match='empty parent'):
        imp.import_step(st, tmp_path / 'G', 'G', 1, p.ZEBRA, nonempty)
    source = deepcopy(imp.pins())
    source['procedures'] = []
    st.extra[imp.PIN_KEY] = source
    monkeypatch.setattr(imp, 'pins', lambda: source)
    with pytest.raises(ValueError, match='empty import'):
        imp.import_step(st, tmp_path / 'G', 'G', 1, p.ZEBRA, parent)
    assert not (tmp_path / 'G').exists()


def test_step_child_preserves_route_confirmation_without_learning_services(tmp_path, monkeypatch):
    st = setting(tmp_path)
    parent = empty(step='G/s0', evidence=st.evidence)
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': 'G', 'bench': p.ZEBRA, 'k': 1})
    confirmed = []
    monkeypatch.setattr(step, 'confirmation', lambda *args, **kwargs: confirmed.append(kwargs))
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    monkeypatch.setattr(manifest, 'services_of', lambda *args, **kwargs: pytest.fail('learning services constructed'))
    monkeypatch.setattr(step.budgets, 'own_ledger', lambda *args: SimpleNamespace(declare=lambda caps: None))
    monkeypatch.setattr(step, 'parent_of', lambda *args: parent)
    result = step.run_unit_spec({'configuration': p.ZEBRA_HP_G3R2, 'root': str(tmp_path),
                                p.RECORD_HASH: 'authored'}, spec=spec)
    assert result == chain.EXIT_COMPLETE and confirmed == [{'configuration': p.ZEBRA_HP_G3R2}]
    assert p.verified(read_json(tmp_path / 'G/s1-zebralogic/step.json'), 'step')['learning'] == 'import'
    assert step.training_units(p.ZEBRA_HP_G3R2) == ()
