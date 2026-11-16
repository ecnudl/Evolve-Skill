"""Exact source pins, two no-learning imports and composition checks on authored roots."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import shutil
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import policy, profiles as p, step, v220_import as imp
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import Package, Procedure, edits, empty, load, save
from tests.execskill_v220_fakes import main_v6_root, pinned_source
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def setting(root, source, evidence='engineering_fixture'):
    return SimpleNamespace(root=root, evidence=evidence,
        extra={'configuration': p.SEARCHQA_HP_V6, imp.PIN_KEY: source})


def imported(st, chain):
    parent = empty(step=chain + '/s0', evidence=st.evidence)
    found = []
    for k, bench in enumerate(imp.STEPS, 1):
        package, record = imp.run_step(st, st.root / chain, chain, k, bench, parent)
        found.append((package, record))
        parent = package
    return found


def test_all_nine_fixture_files_are_pinned_and_provenance_keeps_j1_rejection():
    source = imp.fixture_pins()
    actual = {str(path.relative_to(imp.FIXTURE)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in imp.FIXTURE.rglob('*') if path.is_file()}
    assert actual == imp.FILE_SHA256 == source['files']
    assert len(actual) == 9
    for chain, n, mean, up, down in [('G', 951, -4/951, 17, 21), ('D', 1000, .01, 21, 11)]:
        data = source['chains'][chain]
        assert data['package_record_sha256'] == imp.PACKAGE_SHA256[chain]
        provenance = data['provenance']
        assert provenance == source['manifest']['chains'][chain]
        assert provenance['decision'] == 'reject' and provenance['reason'] == 'failed: J1'
        assert provenance['rule'] == 'practical-v2-11-pooled'
        contrast = provenance['contrasts']["S'-S"]
        assert (contrast['n'], contrast['up'], contrast['down']) == (n, up, down)
        assert contrast['mean'] == pytest.approx(mean)
        assert [row['id'] for row in data['procedures']] == list(imp.PROCEDURE_IDS[chain])


@pytest.mark.parametrize('chain,bytes_', [('G', [1538, 1716]), ('D', [2972, 1898])])
def test_candidates_pass_main_v6_policy_without_any_program_or_field_edit(chain, bytes_):
    rows = imp.fixture_pins()['chains'][chain]['procedures']
    version = p.POLICY_VERSIONS[p.machinery_configuration(p.MAIN_V6, 'searchqa')]
    assert [len(row['record']['source'].encode()) for row in rows] == bytes_
    for row in rows:
        procedure = Procedure.from_json(row['record'])
        assert procedure.policy_version == version and not policy.check(procedure.source, version=version)
        assert procedure.lineage['revises'] is None
        copied = replace(procedure, evidence='engineering_fixture')
        assert {key for key in row['record'] if copied.to_json()[key] != row['record'][key]} == {'evidence', p.RECORD_HASH}
        assert copied.source.encode() == procedure.source.encode()


@pytest.mark.parametrize('name', sorted(imp.FILE_SHA256))
def test_any_modified_fixture_file_is_refused(tmp_path, name):
    fixture = tmp_path / 'fixture'
    shutil.copytree(imp.FIXTURE, fixture)
    path = fixture / name
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='fixture file hash differs'):
        imp.fixture_pins(fixture=fixture)


def test_candidate_policy_failure_refuses_without_repair(monkeypatch):
    monkeypatch.setattr(policy, 'check', lambda *args, **kwargs: [
        SimpleNamespace(to_json=lambda: {'reason': 'authored policy refusal'})])
    with pytest.raises(PackageInvalid, match='Policy violations'):
        imp.fixture_pins()


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_both_chains_must_complete_before_any_main_package_is_read(tmp_path, monkeypatch, chain):
    root = main_v6_root(tmp_path / 'main-v6')
    (root / chain / 'chain-complete.json').unlink()
    monkeypatch.setattr(imp, '_file_pin', lambda *args: pytest.fail('A source record was opened before both completions'))
    with pytest.raises(ValueError, match='Both main-v6 chains'):
        imp.pins(root)


@pytest.mark.parametrize('part', ['package', 'procedure'])
def test_missing_main_v6_record_refused(tmp_path, part):
    root = main_v6_root(tmp_path / 'main-v6')
    path = next((root / 'G' / ('packages' if part == 'package' else 'procedures')).glob('*.json'))
    path.unlink()
    with pytest.raises(ValueError, match='source record is missing'):
        imp.pins(root)


@pytest.mark.parametrize('part', ['package', 'procedure', 'completion'])
def test_mismatched_main_v6_record_refused(tmp_path, part):
    root = main_v6_root(tmp_path / 'main-v6')
    path = (root / 'G' / 'chain-complete.json' if part == 'completion' else
            next((root / 'G' / ('packages' if part == 'package' else 'procedures')).glob('*.json')))
    data = read_json(path)
    data[p.RECORD_HASH] = '0' * 64
    path.write_text(json.dumps(data))
    with pytest.raises((ValueError, PackageInvalid)):
        imp.pins(root)


def test_mismatched_completion_chain_or_package_refused(tmp_path):
    root = main_v6_root(tmp_path / 'main-v6')
    path = root / 'G' / 'chain-complete.json'
    data = read_json(path)
    fields = {key: value for key, value in data.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    fields['identity']['chain'] = 'D'
    path.write_text(json.dumps(p.record('chain-complete', imp.SOURCE_EVIDENCE, fields)))
    with pytest.raises(ValueError, match='completion does not name this chain'):
        imp.pins(root)


def test_s0_pins_every_record_and_raw_file_hash_and_copies_are_detached(tmp_path):
    source = pinned_source(tmp_path)
    assert imp.validate_pins(source) == source
    root = source['main_v6_root']
    for chain, bundle in source['main_v6'].items():
        assert bundle['chain_complete']['record']['package_sha256'] == bundle['package']['record_sha256']
        assert bundle['package']['record']['procedures'] == [row['record_sha256'] for row in bundle['procedures']]
        for row in [bundle['chain_complete'], bundle['package'], *bundle['procedures']]:
            assert row['record_sha256'] == row['record'][p.RECORD_HASH]
            assert json.loads(row['file_text']) == row['record']
            assert hashlib.sha256(row['file_text'].encode()).hexdigest() == row['file_sha256']
        for row in bundle['procedures']:
            assert hashlib.sha256(row['record']['source'].encode()).hexdigest() == row['source_sha256']
    shutil.rmtree(root)
    assert imp.validate_pins(source) == source  # Only record copies and the fixed repo fixture remain.


@pytest.mark.parametrize('chain', ['G', 'D'])
@pytest.mark.parametrize('evidence', ['engineering_fixture', 'searchqa_hp_v6_test_read'])
def test_two_imports_keep_main_order_and_append_two_new_procedures_without_learning(tmp_path, monkeypatch, chain, evidence):
    source = pinned_source(tmp_path)
    st = setting(tmp_path / 'run', source, evidence)
    def forbidden(*args, **kwargs):
        pytest.fail('A fixed import called a learning or solver service')
    for name in ('_slices', '_run', '_diagnose', '_generate', '_trained', '_accept', '_freeze'):
        monkeypatch.setattr(step, name, forbidden)
    for name in ('run_unit', 'cell_context', 'solver_endpoint', 'role_endpoint', 'audit_judges'):
        monkeypatch.setattr(step.units, name, forbidden)
    shutil.rmtree(source['main_v6_root'])
    start = empty(step=chain + '/s0', evidence=evidence)
    first = step.run_step(st, chain, imp.STEPS[0], 1, start, services=None)
    second = step.run_step(st, chain, imp.STEPS[1], 2, first.package, services=None)
    final = second.package
    main_order = source['main_v6'][chain]['package']['record']['order']
    assert final.order == tuple(main_order) + imp.PROCEDURE_IDS[chain]
    assert final.procedures[:len(main_order)] == first.package.procedures
    assert final.retired == first.package.retired == ('b' * 64,)
    assert final.narrowed == first.package.narrowed and final.describer == first.package.describer
    assert [(edit.kind, edit.id) for edit in edits(first.package, final)] == [('new', pid) for pid in imp.PROCEDURE_IDS[chain]]
    assert imp.check_read_package(chain, final, source) == final
    originals = [row['record'] for row in source['main_v6'][chain]['procedures']]
    originals += [row['record'] for row in source['candidate']['chains'][chain]['procedures']]
    for original, copied in zip(originals, final.procedures):
        assert {key for key in original if original[key] != copied.to_json()[key]} == {'evidence', p.RECORD_HASH}
        assert original['source'].encode() == copied.source.encode()
    for k, result in enumerate([first, second], 1):
        assert result.record['learning'] == result.record['decision'] == 'import'
        assert result.record['evidence_kind'] == imp.EVIDENCE_KIND and result.record['units'] == {}
        assert result.record['candidate_sha256'] is result.record['decision_sha256'] is None
        path = st.root / chain / ('s%d-%s' % (k, imp.STEPS[k-1])) / 'import.json'
        provenance = p.verified(read_json(path), 'import-v2-20')
        assert provenance['program_bytes_changed'] is False
        assert provenance['changed_procedure_fields'] == ['evidence', p.RECORD_HASH]
        assert provenance['changed_imported_package_fields'] == ['evidence', 'procedures', p.RECORD_HASH]
    assert imported(st, chain)[-1][0] == final


@pytest.mark.parametrize('empty_chains', [('G',), ('D',), ('G', 'D')])
def test_empty_main_v6_package_still_imports_and_candidate_remains_nonempty(tmp_path, empty_chains):
    source = pinned_source(tmp_path, empty_chains=empty_chains)
    st = setting(tmp_path / 'run', source)
    for chain in p.CHAINS:
        (first, _), (final, _) = imported(st, chain)
        assert bool(first.procedures) == (chain not in empty_chains)
        assert final.order[-2:] == imp.PROCEDURE_IDS[chain]
        assert final.procedures and imp.check_read_package(chain, final, source) == final


@pytest.mark.parametrize('part,field', [('package', 'record_sha256'), ('package', 'file_sha256'),
    ('package', 'file_text'), ('chain_complete', 'record_sha256'), ('chain_complete', 'file_sha256'),
    ('procedure', 'record_sha256'), ('procedure', 'file_sha256'), ('procedure', 'source_sha256')])
def test_pinned_record_copy_mismatch_refused_before_any_write(tmp_path, part, field):
    source = pinned_source(tmp_path)
    entry = source['main_v6']['G']['procedures'][0] if part == 'procedure' else source['main_v6']['G'][part]
    entry[field] = '0' * 64
    st = setting(tmp_path / 'run', source)
    with pytest.raises((ValueError, PackageInvalid)):
        imp.run_step(st, st.root / 'G', 'G', 1, imp.STEPS[0], empty(step='G/s0', evidence=st.evidence))
    assert not st.root.exists()


def test_runtime_changed_candidate_pin_refused(tmp_path):
    source = pinned_source(tmp_path)
    source['candidate']['chains']['G']['procedures'][0]['source_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='candidate pins differ'):
        imp.final_package('G', 'engineering_fixture', source)


@pytest.mark.parametrize('part', ['order', 'missing', 'source'])
def test_before_read_exact_composition_rejects_any_difference(tmp_path, part):
    source = pinned_source(tmp_path)
    final = imp.final_package('G', 'engineering_fixture', source)
    procedures = list(final.procedures)
    if part == 'order':
        procedures[-2:] = reversed(procedures[-2:])
    elif part == 'missing':
        procedures.pop()
    else:
        procedures[-1] = replace(procedures[-1], source=procedures[-1].source + '\n# drift\n')
    altered = replace(final, procedures=tuple(procedures))
    with pytest.raises(ValueError, match='exactly main-v6 order'):
        imp.check_read_package('G', altered, source)


def test_existing_candidate_id_cannot_be_appended_as_new(tmp_path):
    root = main_v6_root(tmp_path / 'main-v6')
    data = imp.fixture_pins()['chains']['G']
    program = Procedure.from_json(data['procedures'][0]['record'])
    collision = Package((program,), 'G/s5-alfworld', imp.SOURCE_EVIDENCE)
    save(root / 'G', collision)
    complete = p.record('chain-complete', imp.SOURCE_EVIDENCE,
        {'identity': {'run': 'authored-main-v6', 'chain': 'G'}, 'package_sha256': collision.sha256, 'steps': []})
    (root / 'G' / 'chain-complete.json').write_text(json.dumps(complete))
    source = imp.pins(root)
    with pytest.raises(ValueError, match='must be NEW'):
        imp.final_package('G', 'engineering_fixture', source)


@pytest.mark.parametrize('configuration,chain,k,bench', [
    (p.MAIN_V6, 'G', 1, 'main-v6-final'), (p.SEARCHQA_HP_V6, 'H', 1, 'main-v6-final'),
    (p.SEARCHQA_HP_V6, 'G', 3, 'searchqa-candidate'), (p.SEARCHQA_HP_V6, 'G', 1, 'searchqa')])
def test_unregistered_import_scope_refused(tmp_path, configuration, chain, k, bench):
    st = SimpleNamespace(root=tmp_path, evidence='engineering_fixture', extra={'configuration': configuration})
    with pytest.raises(ValueError, match='only main-v6-final and searchqa-candidate'):
        imp.run_step(st, tmp_path / chain, chain, k, bench, empty(step='G/s0', evidence=st.evidence))


def test_structural_smoke_checks_both_import_chains_with_no_clients(tmp_path):
    source = pinned_source(tmp_path)
    shutil.rmtree(source['main_v6_root'])
    result = imp.structural_smoke(tmp_path / 'smoke', source)
    assert result['passed'] and result['steps'] == list(imp.STEPS)
    assert set(result['packages']) == {'G', 'D'}
    assert result['model_calls'] == result['sealed_reads'] == result['learning_units'] == 0
    for chain in p.CHAINS:
        assert result['orders'][chain][-2:] == list(imp.PROCEDURE_IDS[chain])
