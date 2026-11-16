"""Post-hoc F/C and request-tie analyses with explicit note-emission counts."""
from copy import deepcopy

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import evaluation, package, profiles as p, readout, v218_read, v220_import, v220_read
from skillopt.validator_pilot.api import digest
from tests.execskill_v220_fakes import pinned_source
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_readout import cell

CHILD = p.SEARCHQA_HP_V6
EVIDENCE = 'engineering_fixture'


def authored_units(chain='G'):
    ids = list(v220_import.PROCEDURE_IDS[chain])
    found = {}
    for i in range(12):
        for arm in ('F', 'C'):
            emitted = ids if arm == 'F' and i >= 6 else []
            enabled = ids if arm == 'F' else []
            row = cell('pass' if arm == 'F' else 'fail', enabled=enabled)
            row.update(request_sha256=[digest((i, 'C' if i < 6 else arm))],
                searchqa_fired={'procedure_ids': ids, 'enabled': enabled, 'emitted_note_ids': emitted})
            found[(arm, 'authored-' + str(i), 0)] = row
    return {'searchqa': found}


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_readout_has_primary_and_request_tie_estimates_beside_fired_counts(fast_statistics, chain):
    units = authored_units(chain)
    procedures = {pid: 'searchqa' for pid in v220_import.PROCEDURE_IDS[chain]}
    procedures['p-officeqa-existing'] = 'officeqa'
    found = readout.readout(units, learned=[], procedures=procedures, label='owner-requested',
                            evidence=EVIDENCE, configuration=CHILD)
    assert found['evidence_kind'] == 'post_hoc_selected_upper_bound'
    assert found['learned'] == [] and found['imported'] == ['searchqa', 'officeqa']
    assert found['q1_home'] is found['q2_similar'] is found['q3_noninferiority'] is None
    assert 'stages' not in found and 'cross' not in found and 'stage_questions' not in found
    assert set(found['contrasts']) == {'searchqa'} and set(found['contrasts']['searchqa']) == {'F-C'}
    primary = found['contrasts']['searchqa']['F-C']
    secondary = found['identical_request_analysis']
    assert primary['mean'] == 1 and secondary['contrasts']['searchqa']['F-C']['mean'] == .5
    assert secondary['contrasts']['searchqa']['F-C']['identical_request_items'] == 6
    assert secondary['conclusions_follow'] == 'primary' and 'stages' not in secondary
    assert primary == readout._contrast(units['searchqa'], 'F', 'C',
        readout._items(units['searchqa'], 'F', 'C'), bootstrap=True, sensitivity=True)
    counts = found['searchqa_fired']
    assert counts['items'] == counts['enabled_items'] == 12 and counts['fired_items'] == 6
    assert counts['per_procedure'] == {pid: {'enabled_items': 12, 'fired_items': 6} for pid in procedures
                                      if pid != 'p-officeqa-existing'}
    assert 'never method evidence' in found['honesty']['interpretation']
    assert 'failed J1' in found['honesty']['acceptance']
    assert 'Fifth or sixth' in found['honesty']['panel_exposure']


def test_fired_counts_use_unique_items_and_ignore_enabled_but_silent_notes():
    units = authored_units()
    cells = units['searchqa']
    cells.update({(arm, item, 1): deepcopy(row) for (arm, item, run), row in list(cells.items())})
    value = v220_read.fired_counts(cells, dict.fromkeys(v220_import.PROCEDURE_IDS['G'], 'searchqa'))
    assert value['items'] == value['enabled_items'] == 12 and value['fired_items'] == 6
    assert all(row['fired_items'] == 6 for row in value['per_procedure'].values())
    notes = [{'id': v220_import.PROCEDURE_IDS['G'][0], 'rendered_chars': 99, 'delivered_text': ''},
             {'id': v220_import.PROCEDURE_IDS['G'][1], 'rendered_chars': 15, 'delivered_text': 'Visible note.'}]
    assert v220_read.fired_notes(notes, v220_import.PROCEDURE_IDS['G']) == [v220_import.PROCEDURE_IDS['G'][1]]


@pytest.mark.parametrize('fault', ['other_bench', 'blank_arm', 'stage_arm', 'stage_rows', 'learned',
                                   'missing_firing_metadata', 'wrong_candidate_ids'])
def test_readout_refuses_unregistered_panels_arms_or_missing_firing_records(fast_statistics, fault):
    units = authored_units()
    procedures = dict.fromkeys(v220_import.PROCEDURE_IDS['G'], 'searchqa')
    stages, learned = None, []
    if fault == 'other_bench':
        units['officeqa'] = deepcopy(units['searchqa'])
    elif fault in ('blank_arm', 'stage_arm'):
        units['searchqa'][('B' if fault == 'blank_arm' else 'S1', 'authored-0', 0)] = cell('pass')
    elif fault == 'stage_rows':
        stages = ['C', 'F']
    elif fault == 'learned':
        learned = ['searchqa']
    elif fault == 'missing_firing_metadata':
        del units['searchqa'][('F', 'authored-0', 0)]['searchqa_fired']
    elif fault == 'wrong_candidate_ids':
        procedures = {'not-a-fixed-candidate': 'searchqa'}
    with pytest.raises(ValueError):
        readout.readout(units, learned=learned, procedures=procedures, label='authored', evidence=EVIDENCE,
                        stages=stages, configuration=CHILD)


def test_report_marks_both_chain_imports_as_post_hoc_not_learned(tmp_path, monkeypatch, fast_statistics):
    source = pinned_source(tmp_path / 'source')
    root = tmp_path / 'run'
    for chain in p.CHAINS:
        final = v220_import.final_package(chain, EVIDENCE, source)
        package.save(root / chain, final)
        write_json(root / chain / 'test-read.json', p.record('test-read', EVIDENCE,
            {'status': 'read', 'package_sha256': final.sha256}))
        write_json(root / chain / 'test/searchqa/unit.json', {'authored': True})
    called = []
    def unseal(root, chain_root, chain, unit_roots, **options):
        called.append(chain)
        assert options['configuration'] == CHILD and [path.name for path in unit_roots] == ['searchqa']
        return {'units': authored_units(chain), 'label': 'owner-requested'}
    monkeypatch.setattr(evaluation, 'unseal', unseal)
    found = readout.report({'configuration': CHILD, 'root': str(root), p.RECORD_HASH: 'authored-run',
                           'evidence': EVIDENCE}, out=tmp_path / 'report')
    assert set(found) == set(called) == set(p.CHAINS)
    for chain in p.CHAINS:
        value = read_json(tmp_path / 'report' / ('readout-' + chain + '.json'))
        assert value['learned'] == [] and value['evidence_kind'] == 'post_hoc_selected_upper_bound'
        assert set(value['contrasts']) == {'searchqa'}
        assert set(value['searchqa_fired']['per_procedure']) == set(v220_import.PROCEDURE_IDS[chain])


def test_unseal_requires_both_chains_before_any_score_is_opened(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, '_ended', lambda root: root.name == 'G')
    monkeypatch.setattr(evaluation, 'continuation', lambda *_: pytest.fail('No score release before D ends'))
    with pytest.raises(ValueError, match='both chains have ended'):
        evaluation.unseal(tmp_path, tmp_path / 'G', 'G', [], run='authored', evidence=EVIDENCE, configuration=CHILD)
