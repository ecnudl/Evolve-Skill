"""Fixed v3r4 reconstruction/import is static, offline and makes no learning calls."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import re
import shutil
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import chain, manifest, policy, profiles as p, step, v213_import as imp
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import Procedure, empty, load, validate
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def setting(tmp_path, *, evidence='engineering_fixture'):
    return SimpleNamespace(root=tmp_path, evidence=evidence,
        extra={'configuration': p.ZEBRA_HP_V3R4, imp.PIN_KEY: imp.pins()})


def test_exact_inputs_rebuild_single_new_current_policy_package_without_execution():
    source = (imp.FIXTURE / 'inputs/v3r4-c6.py').read_bytes()
    reply = (imp.FIXTURE / 'inputs/v3r4-c6.reply.txt').read_bytes()
    assert len(source) == 10_955
    assert hashlib.sha256(source).hexdigest() == imp.SOURCE_SHA256
    assert hashlib.sha256(reply).hexdigest() == imp.REPLY_SHA256
    entry = json.loads(re.search(r'```json\s*(.*?)```', reply.decode(), re.S).group(1))['changes'][0]
    parent, package = imp.build(source, reply)
    validate(package, parent)
    assert not parent.procedures and package.sha256 == imp.PACKAGE_SHA256
    assert package == load(imp.FIXTURE / 'packages' / (imp.PACKAGE_SHA256 + '.json'))
    assert len(package.procedures) == 1 and len(package.for_bench(p.ZEBRA)) == 1
    procedure = package.procedures[0]
    assert procedure.source.encode() == source
    assert len(entry['description']) == 648 and procedure.description == entry['description'][:600]
    assert procedure.hooks == tuple(entry['hooks']) == ('applies', 'before_call')
    assert procedure.header == entry['header'] == 'Zebra puzzle exact solver'
    assert procedure.max_note_chars == entry['max_note_chars'] == 4000
    assert procedure.state_bytes == entry['state_bytes'] == 0
    assert procedure.requests_second_call == entry['requests_second_call'] is False
    assert procedure.excluded_benches == () and len(entry['replay_tests']) == 4 and not procedure.replay_tests
    assert procedure.accepted_at is None
    assert procedure.lineage == {'parent': None, 'revises': None, 'engineer_call': None}
    assert procedure.policy_version == p.POLICY_VERSIONS[p.ZEBRA_PC_V13] == policy.POLICY_VERSION_V29
    assert not policy.check(procedure.source, version=procedure.policy_version)
    assert not policy.check(procedure.source, version=policy.POLICY_VERSION_V25)


def test_provenance_separates_historical_probe_current_wrapper_and_no_audit():
    pins = imp.pins()
    provenance = pins['provenance']
    assert pins['origin'] == 'zebra-pc-v3/round-4'
    assert pins['evidence_kind'] == provenance['evidence_kind'] == 'post_hoc_selected_upper_bound'
    assert pins['package_record_sha256'] == imp.PACKAGE_SHA256 != imp.PROBE_PACKAGE_SHA256
    assert provenance['probe']['package_sha256'] == imp.PROBE_PACKAGE_SHA256
    assert provenance['probe']['policy_version'] == policy.POLICY_VERSION_V25
    assert provenance['probe']['root_accessed'] is False and provenance['probe']['route'] == 'elucid'
    assert provenance['origin']['adopted_by_method'] is False
    assert provenance['reconstruction']['policy_version'] == policy.POLICY_VERSION_V29
    assert provenance['reconstruction']['v29_llm_audit'] == 'not_run'
    assert provenance['validation']['program_executed'] is False
    assert provenance['validation']['model_calls'] == provenance['validation']['sealed_reads'] == 0
    assert 'unavailable' in provenance['hash_explanation']['historical_wrapper_limit']
    assert 'engineering_fixture' in provenance['hash_explanation']['known_changes']


@pytest.mark.parametrize('name', [
    'inputs/v3r4-c6.py', 'inputs/v3r4-c6.reply.txt', 'provenance.json',
    'packages/' + imp.PACKAGE_SHA256 + '.json', 'packages/' + imp.PARENT_SHA256 + '.json',
    'procedures/' + imp.PROCEDURE_SHA256 + '.json'])
def test_any_fixed_file_change_is_refused_before_import(tmp_path, name):
    fixture = tmp_path / 'fixture'
    shutil.copytree(imp.FIXTURE, fixture)
    path = fixture / name
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='fixture file hash differs'):
        imp.pins(fixture=fixture)


def test_resealed_source_modification_is_refused(tmp_path):
    fixture = tmp_path / 'fixture'
    shutil.copytree(imp.FIXTURE, fixture)
    original = Procedure.from_json(imp.pins()['procedures'][0]['record'])
    changed = replace(original, source=original.source + '\n# changed\n')
    (fixture / 'procedures' / (imp.PROCEDURE_SHA256 + '.json')).write_text(json.dumps(changed.to_json()))
    with pytest.raises(ValueError, match='fixture file hash differs'):
        imp.pins(fixture=fixture)


def test_policy_failure_stops_reconstruction_without_repair(monkeypatch):
    source = (imp.FIXTURE / 'inputs/v3r4-c6.py').read_bytes()
    reply = (imp.FIXTURE / 'inputs/v3r4-c6.reply.txt').read_bytes()
    monkeypatch.setattr(policy, 'check', lambda *args, **kwargs: [
        SimpleNamespace(to_json=lambda: {'reason': 'authored policy refusal'})])
    with pytest.raises(PackageInvalid, match='Policy violations'):
        imp.build(source, reply)
    assert (imp.FIXTURE / 'inputs/v3r4-c6.py').read_bytes() == source


@pytest.mark.parametrize('evidence', ['engineering_fixture', 'zebra_hp_v3r4_test_read'])
def test_import_rebinds_only_evidence_and_calls_no_learning_or_solver(tmp_path, monkeypatch, evidence):
    st = setting(tmp_path, evidence=evidence)
    parent = empty(step='D/s0', evidence=evidence)
    def forbidden(*args, **kwargs):
        pytest.fail('The fixed import invoked learning or evaluation before the read')
    for name in ('_slices', '_run', '_diagnose', '_generate', '_trained', '_accept', '_freeze'):
        monkeypatch.setattr(step, name, forbidden)
    for name in ('run_unit', 'cell_context', 'solver_endpoint', 'role_endpoint', 'audit_judges'):
        monkeypatch.setattr(step.units, name, forbidden)
    found = step.run_step(st, 'D', p.ZEBRA, 1, parent, services=None)
    record = found.record
    assert record['learning'] == record['decision'] == 'import'
    assert record['evidence_kind'] == imp.EVIDENCE_KIND
    assert record['candidate_sha256'] is record['decision_sha256'] is None and record['units'] == {}
    assert record['chain_parent_sha256'] == found.package.parent_sha256 == parent.sha256
    imported = load(tmp_path / 'D/packages' / (record['parent_sha256'] + '.json'))
    assert imported.parent_sha256 == imp.PACKAGE_SHA256
    assert found.package.procedures == imported.procedures and imported.evidence == evidence
    copied = found.package.procedures[0]
    original = imp.pins()['procedures'][0]
    without_stamp = lambda row: {k: v for k, v in row.items() if k not in ('evidence', p.RECORD_HASH)}
    assert without_stamp(copied.to_json()) == without_stamp(original['record'])
    assert copied.source.encode() == (imp.FIXTURE / 'inputs/v3r4-c6.py').read_bytes()
    provenance = p.verified(read_json(tmp_path / 'D/s1-zebralogic/import.json'), 'import-v2-13')
    assert provenance['source'] == imp.pins() and provenance['program_bytes_changed'] is False
    assert provenance['origin'] == imp.ORIGIN and provenance['evidence_kind'] == imp.EVIDENCE_KIND
    assert step.run_step(st, 'D', p.ZEBRA, 1, parent, services=None) == found
    assert not list((tmp_path / 'D').glob('s1-zebralogic/*/unit.json'))


@pytest.mark.parametrize('field', ['source_sha256', 'record_sha256', 'file_sha256'])
def test_manifest_pin_drift_refused_before_write(tmp_path, field):
    st = setting(tmp_path)
    st.extra[imp.PIN_KEY]['procedures'][0][field] = '0' * 64
    with pytest.raises(ValueError, match='pins differ'):
        imp.import_step(st, tmp_path / 'D', 'D', 1, p.ZEBRA, empty(step='D/s0', evidence=st.evidence))
    assert not (tmp_path / 'D').exists()


@pytest.mark.parametrize(('chain_id', 'k', 'bench'), [('G', 1, p.ZEBRA), ('D', 2, p.ZEBRA), ('D', 1, 'alfworld')])
def test_import_rejects_other_steps_before_write(tmp_path, chain_id, k, bench):
    st = setting(tmp_path)
    with pytest.raises(ValueError, match='chain D step 1'):
        imp.import_step(st, tmp_path / chain_id, chain_id, k, bench, empty(step='D/s0', evidence=st.evidence))
    assert not (tmp_path / chain_id).exists()


def test_empty_import_and_nonempty_parent_are_refused_before_write(tmp_path, monkeypatch):
    st = setting(tmp_path)
    parent, nonempty = imp.build((imp.FIXTURE / 'inputs/v3r4-c6.py').read_bytes(),
                                (imp.FIXTURE / 'inputs/v3r4-c6.reply.txt').read_bytes())
    with pytest.raises(ValueError, match='empty parent'):
        imp.import_step(st, tmp_path / 'D', 'D', 1, p.ZEBRA, nonempty)
    source = deepcopy(imp.pins())
    source['procedures'] = []
    st.extra[imp.PIN_KEY] = source
    monkeypatch.setattr(imp, 'pins', lambda: source)
    with pytest.raises(ValueError, match='empty import'):
        imp.import_step(st, tmp_path / 'D', 'D', 1, p.ZEBRA, parent)
    assert not (tmp_path / 'D').exists()


def test_step_child_preserves_route_confirmation_without_learning_services(tmp_path, monkeypatch):
    st = setting(tmp_path)
    parent = empty(step='D/s0', evidence=st.evidence)
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': 'D', 'bench': p.ZEBRA, 'k': 1})
    confirmed = []
    monkeypatch.setattr(step, 'confirmation', lambda *args, **kwargs: confirmed.append(kwargs))
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    monkeypatch.setattr(manifest, 'services_of', lambda *args, **kwargs: pytest.fail('learning services constructed'))
    monkeypatch.setattr(step.budgets, 'own_ledger', lambda *args: SimpleNamespace(declare=lambda caps: None))
    monkeypatch.setattr(step, 'parent_of', lambda *args: parent)
    result = step.run_unit_spec({'configuration': p.ZEBRA_HP_V3R4, 'root': str(tmp_path),
                                p.RECORD_HASH: 'authored'}, spec=spec)
    assert result == chain.EXIT_COMPLETE and confirmed == [{'configuration': p.ZEBRA_HP_V3R4}]
    assert p.verified(read_json(tmp_path / 'D/s1-zebralogic/step.json'), 'step')['learning'] == 'import'
    assert step.training_units(p.ZEBRA_HP_V3R4) == ()
