"""Post-hoc import reaches the inherited F/C read, with explicit consent and evidence."""
import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import chain, evaluation, package, profiles as p, readout, v213_import as imp
from tests import test_execskill_v212_evaluation as parent_tests
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_chain import Launch, setting as chain_setting
from tests.test_execskill_readout import cell
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CHILD = p.ZEBRA_HP_V3R4


@pytest.fixture(autouse=True)
def child_configuration(monkeypatch):
    monkeypatch.setattr(parent_tests, 'CONFIG', CHILD)


def test_explicit_fc_consent_and_no_implicit_authorization(tmp_path):
    parent_tests.test_exact_owner_consent_and_legacy_implicit_consent_stays_frozen(tmp_path)


@pytest.mark.parametrize('changes', [
    {'multi_arm_arms': ['F', 'C', 'B']}, {'multi_arm_arms': ['F', 'C', 'P_F']},
    {'multi_arm_arms': ['F', 'C', 'T_F']}, {'multi_arm_arms': ['F', 'C', 'withholding']},
    {'multi_arm_arms': ['F', 'C', 'C']}, {'multi_arm_arms': ['C']},
    {'test_evaluation': False}, {'sheet_test_qualification': True}, {'by': 'agent'}, {'note': ''},
])
def test_import_read_refuses_other_consent(tmp_path, changes):
    parent_tests.test_v13_rejects_any_other_consent(tmp_path, changes)


def test_fc_single_run_interleaving_and_zero_dispatch_share_on_authored_tasks(tmp_path):
    parent_tests.test_real_evaluation_dispatches_only_f_c_and_no_test_twins(tmp_path)


def test_read_entry_constructs_only_fc_without_donors(tmp_path, monkeypatch):
    parent_tests.test_unit_entry_constructs_f_c_without_loading_donors(tmp_path, monkeypatch)


def test_chain_import_reads_once_without_acceptance(tmp_path, monkeypatch):
    setting = chain_setting(tmp_path, chain_='D', consent=False)
    setting.extra.update(configuration=CHILD, test_read_terms={'D': {p.ZEBRA: '1000'}},
                         **{imp.PIN_KEY: imp.pins()})
    write_json(setting.shared / 'consent.json', parent_tests.consent())
    monkeypatch.setattr(chain, 'first_call', lambda *args, **kwargs: None)
    launch = Launch(tmp_path)
    assert chain.run(setting, 'D', learn=imp.import_step, launch=launch) == {'status': 'complete'}
    step = p.verified(read_json(setting.root / 'D/s1-zebralogic/step.json'), 'step')
    result = p.verified(read_json(setting.root / 'D/test-read.json'), 'test-read')
    assert step['decision'] == step['learning'] == result['learning'] == 'import'
    assert step['decision_sha256'] is None and step['units'] == {}
    assert result['status'] == 'read' and result['arms'] == ['F', 'C']
    assert result['evidence_kind'] == imp.EVIDENCE_KIND
    assert result['gate']['cost_check'] == 'not_applicable_no_learning_run'
    assert [spec['bench'] for spec in launch.specs] == [p.ZEBRA]
    assert chain.run(setting, 'D', learn=imp.import_step, launch=launch) == {'status': 'complete'}
    assert len(launch.specs) == 1


def test_readout_and_report_call_imported_program_an_upper_bound(tmp_path, monkeypatch, fast_statistics):
    root = tmp_path / 'root'
    setting = chain_setting(tmp_path, chain_='D', consent=False)
    setting.extra.update(configuration=CHILD, **{imp.PIN_KEY: imp.pins()})
    final, _ = imp.import_step(setting, root / 'D', 'D', 1, p.ZEBRA,
                               package.empty(step='D/s0', evidence=setting.evidence))
    write_json(root / 'D/test-read.json', p.record('test-read', setting.evidence,
        {'status': 'read', 'package_sha256': final.sha256}))
    data = {(arm, 'authored-%d' % i, 0): cell('pass' if arm == 'F' else 'fail')
            for arm in ('F', 'C') for i in range(4)}
    def unseal(*args, **kwargs):
        assert kwargs['configuration'] == CHILD
        return {'units': {p.ZEBRA: data}, 'label': 'engineering'}
    monkeypatch.setattr(evaluation, 'unseal', unseal)
    out = tmp_path / 'readout'
    result = readout.report({'root': str(root), p.RECORD_HASH: 'authored-v213', 'evidence': setting.evidence,
        'configuration': CHILD, 'data': {'launchable_chains': ['D']}}, out=out)
    value = p.verified(read_json(out / 'readout-D.json'), 'readout')
    assert result == {'D': value[p.RECORD_HASH]}
    assert value['evidence_kind'] == imp.EVIDENCE_KIND and value['configuration'] == CHILD
    assert value['imported'] == [p.ZEBRA] and value['learned'] == [] and value['q1_home'] is None
    assert set(value['contrasts'][p.ZEBRA]) == {'F-C'}
    assert set(value['arms'][p.ZEBRA]) == {'F', 'C'}
    assert value['placebo'] == value['code_vs_text'] == value['twins'] == {'removed': True}


def test_serialized_authored_cells_keep_route_and_model_metadata(tmp_path):
    parent_tests.test_sealed_cells_preserve_inherited_route_keyword_and_model_metadata(tmp_path)
