"""Offline v2.10 frozen-package import and no-learning baseline orchestration."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import chain, instruction_start, manifest, profiles as p, step, v210_import as imp
from skillopt.execskill.package import empty, load
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_chain import CONSENT, setting as chain_setting


def setting(tmp_path, *, evidence=None):
    return SimpleNamespace(root=tmp_path, evidence=evidence or p.REAL_RUN_EVIDENCE[p.MAIN_V3],
        extra={'configuration': p.MAIN_V3, 'alfworld_v11_import': imp.pins()})


def test_frozen_import_pins_order_records_and_verbatim_sources():
    pins = imp.pins()
    assert pins['origin'] == 'alfworld_v11_real_run'
    assert pins['package_record_sha256'] == imp.PACKAGE_SHA256
    assert pins['package']['order'] == ['p-alfworld-1-15', 'p-alfworld-1-14', 'p-alfworld-1-6']
    for row in pins['procedures']:
        assert hashlib.sha256(row['record']['source'].encode()).hexdigest() == row['source_sha256']
        assert row['record']['record_sha256'] == row['record_sha256']


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_import_step_copies_by_value_rebinds_evidence_and_makes_no_learning_units(tmp_path, monkeypatch, chain_id):
    st = setting(tmp_path)
    parent = empty(step=chain_id + '/s4-spreadsheetbench', evidence=st.evidence)
    def forbidden(*args, **kwargs):
        pytest.fail('Import invoked a learning service')
    for name in ('_slices', '_run', '_diagnose', '_generate', '_trained', '_accept', '_freeze'):
        monkeypatch.setattr(step, name, forbidden)
    found = step.run_step(st, chain_id, 'alfworld', 5, parent, services=None)
    record = found.record
    assert record['learning'] == record['decision'] == record['evidence_kind'] == 'import'
    assert record['units'] == {} and record['candidate_sha256'] is None and record['decision_sha256'] is None
    assert record['chain_parent_sha256'] == parent.sha256
    root = tmp_path / chain_id
    imported = load(root / 'packages' / (record['parent_sha256'] + '.json'))
    assert imported.parent_sha256 == imp.PACKAGE_SHA256
    assert found.package.procedures == imported.procedures
    assert found.package.evidence == imported.evidence == st.evidence
    for source, copied in zip(imp.pins()['procedures'], imported.procedures):
        assert copied.evidence == st.evidence
        assert copied.sha256 != source['record_sha256']
        without_stamp = lambda value: {k: v for k, v in value.items() if k not in ('evidence', 'record_sha256')}
        assert without_stamp(copied.to_json()) == without_stamp(source['record'])
    provenance = p.verified(read_json(root / 's5-alfworld/import.json'), 'import-v2-10')
    assert provenance['source'] == imp.pins() and provenance['origin'] == imp.ORIGIN
    again = step.run_step(st, chain_id, 'alfworld', 5, parent, services=None)
    assert again == found
    assert not list(root.glob('s5-alfworld/*/unit.json'))


def test_import_preserves_all_earlier_procedures_order_metadata_and_package_link(tmp_path):
    from tests.execskill_fakes_env import procedure
    from skillopt.execskill.package import Package
    st = setting(tmp_path)
    prior = procedure('p-officeqa-2-1', ('applies', 'before_call'), evidence=st.evidence)
    parent = Package((prior,), 'G/s4-spreadsheetbench', st.evidence, narrowed={prior.id: ('searchqa',)})
    result, record = imp.import_step(st, tmp_path / 'G', 'G', 5, 'alfworld', parent)
    assert result.order == (prior.id,) + tuple(row[0] for row in imp.PROCEDURES)
    assert result.procedures[0] is prior and result.narrowed == parent.narrowed
    assert result.parent_sha256 == parent.sha256 and record['chain_parent_sha256'] == parent.sha256


@pytest.mark.parametrize('field', ['source_sha256', 'record_sha256', 'file_sha256'])
def test_manifest_import_pin_tampering_refused_before_any_write(tmp_path, field):
    st = setting(tmp_path)
    st.extra['alfworld_v11_import']['procedures'][0][field] = '0' * 64
    parent = empty(step='G/s4-spreadsheetbench', evidence=st.evidence)
    with pytest.raises(ValueError, match='pins differ'):
        imp.import_step(st, tmp_path / 'G', 'G', 5, 'alfworld', parent)
    assert not (tmp_path / 'G').exists()


def test_source_fixture_tampering_refused_even_if_resealed(tmp_path):
    source = tmp_path / 'fixture'
    shutil.copytree(imp.FIXTURE, source)
    path = source / 'procedures' / (imp.PROCEDURES[0][1] + '.json')
    value = read_json(path)
    value['source'] += '\n# changed\n'
    from skillopt.execskill.package import Procedure
    changed = replace(Procedure.from_json(imp.pins()['procedures'][0]['record']), source=value['source'])
    path.write_text(__import__('json').dumps(changed.to_json()))
    with pytest.raises((ValueError, RuntimeError), match='hash|record|sealed|Package'):
        imp.pins(fixture=source)


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_baseline_chain_reads_five_units_once_without_learning_or_cost_check(tmp_path, monkeypatch, chain_id):
    base = chain_setting(tmp_path, chain_=chain_id, consent=False)
    st = replace(base, extra={**base.extra, 'configuration': p.BASELINE_V210})
    write_json(st.shared / 'consent.json', {**CONSENT, 'multi_arm_arms': ['C', 'B']})
    monkeypatch.setattr(chain, 'first_call', lambda *args, **kwargs: None)
    called = []
    def forbidden(*args, **kwargs):
        pytest.fail('The baseline invoked learning or its run cost check')
    monkeypatch.setattr(chain, 'latest_cap_check', forbidden)
    def launch(setting_, spec):
        called.append(spec)
        loaded = load(Path(setting_.root) / chain_id / 'packages' / (spec['package_sha256'] + '.json'))
        assert not loaded.procedures
        write_json(Path(spec['unit_root']) / 'unit.json', p.record('evaluation', st.evidence, {
            'run': st.run, 'chain': chain_id, 'bench': spec['bench'],
            'packages': {'C': loaded.sha256, 'B': loaded.sha256}}))
        return chain.EXIT_COMPLETE
    assert chain.run(st, chain_id, learn=forbidden, launch=launch) == {'status': 'complete'}
    assert {row['bench'] for row in called} == set(p.BENCHES) and len(called) == 5
    root = Path(st.root) / chain_id
    complete = p.verified(read_json(root / 'chain-complete.json'), 'chain-complete')
    read = p.verified(read_json(root / 'test-read.json'), 'test-read')
    assert complete['steps'] == [] and read['status'] == 'read'
    assert read['arms'] == ['C', 'B'] and read['learning'] == 'none'
    assert read['instruction_start'] == 'historical_card_is_the_instruction'
    assert read['blank_arm'] == {'card': '', 'kind': 'blank'}
    assert read['gate']['factor'] == 1 and read['gate']['cap_check'] is None
    assert not list(root.glob('s[1-5]-*'))
    assert chain.run(st, chain_id, learn=forbidden, launch=forbidden) == {'status': 'complete'}
    assert step.training_units(p.BASELINE_V210) == ()


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_main_chain_test_read_pins_blank_guidance_and_historical_instruction(tmp_path, monkeypatch, chain_id):
    base = chain_setting(tmp_path, chain_=chain_id, consent=False)
    st = replace(base, cards={b: row['text'] for b, row in instruction_start.pins().items()},
                 extra={**base.extra, 'configuration': p.MAIN_V3, 'alfworld_v11_import': imp.pins()})
    write_json(st.shared / 'consent.json', {**CONSENT, 'multi_arm_arms': ['F', 'C', 'B']})
    monkeypatch.setattr(chain, 'first_call', lambda *args, **kwargs: None)
    monkeypatch.setattr(chain, 'read_budget', lambda *args: {'fixture': 'budget already checked'})
    reads = []
    monkeypatch.setattr(chain, 'evaluate', lambda setting_, chain_, package, **kwargs:
                        reads.append((chain_, package.order, setting_.cards)))

    def learn(setting_, root, chain_, k, bench, parent):
        if bench == 'alfworld':
            return imp.import_step(setting_, root, chain_, k, bench, parent)
        return parent, p.record('step', st.evidence, {'chain': chain_, 'bench': bench, 'k': k})

    assert chain.run(st, chain_id, learn=learn) == {'status': 'complete'}
    read = p.verified(read_json(st.root / chain_id / 'test-read.json'), 'test-read')
    assert read['arms'] == ['F', 'C', 'B']
    assert read['instruction_start'] == 'historical_card_is_the_instruction'
    assert read['blank_arm'] == {'card': '', 'kind': 'blank'}
    assert reads == [(chain_id, tuple(row[0] for row in imp.PROCEDURES), st.cards)]


def test_baseline_manifest_runner_does_not_construct_learning_services(tmp_path, monkeypatch):
    st = SimpleNamespace()
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    monkeypatch.setattr(manifest, 'services_of', lambda *args, **kwargs: pytest.fail('learning services constructed'))
    monkeypatch.setattr(chain, 'run', lambda setting, chain_id, **kwargs: {
        'status': 'complete', 'services': kwargs['learn'].keywords['services']})
    result = chain.run_manifest({'configuration': p.BASELINE_V210, 'evidence': 'engineering_fixture'},
                                chain='G', path=tmp_path / 'manifest.json')
    assert result == {'status': 'complete', 'services': None}


def test_baseline_rejects_direct_learning_entry_point(tmp_path):
    st = setting(tmp_path)
    st.extra['configuration'] = p.BASELINE_V210
    with pytest.raises(ValueError, match='no learning'):
        step.run_step(st, 'G', 'searchqa', 1, empty(step='G/s0', evidence=st.evidence), services=None)
    with pytest.raises(ValueError, match='no learning'):
        step.run_unit_spec({'configuration': p.BASELINE_V210}, spec=tmp_path / 'not-opened.json')


def test_import_step_child_confirms_northgate_without_constructing_learning_services(tmp_path, monkeypatch):
    st = setting(tmp_path)
    parent = empty(step='D/s4-spreadsheetbench', evidence=st.evidence)
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': 'D', 'bench': 'alfworld', 'k': 5})
    confirmed = []
    monkeypatch.setattr(step, 'confirmation', lambda *args, **kwargs: confirmed.append(kwargs))
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    monkeypatch.setattr(manifest, 'services_of', lambda *args, **kwargs: pytest.fail('learning services constructed'))
    monkeypatch.setattr(step.budgets, 'own_ledger', lambda *args: SimpleNamespace(declare=lambda caps: None))
    monkeypatch.setattr(step, 'parent_of', lambda *args: parent)
    result = step.run_unit_spec({'configuration': p.MAIN_V3, 'root': str(tmp_path), p.RECORD_HASH: 'authored'}, spec=spec)
    assert result == chain.EXIT_COMPLETE and confirmed == [{'configuration': p.MAIN_V3}]
    assert p.verified(read_json(tmp_path / 'D/s5-alfworld/step.json'), 'step')['learning'] == 'import'
