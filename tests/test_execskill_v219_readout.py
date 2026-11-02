"""Authored cross matrices preserve registered contrasts and isolation."""
from copy import deepcopy

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import evaluation, package, profiles as p, readout, v217_implant, v218_read, v219_read
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_readout import cell

CHILD = p.CROSS_V5
EVIDENCE = 'engineering_fixture'


def authored_units():
    out = {}
    for bench in p.MAIN_V5_ORDER:
        values = {}
        for i in range(12):
            for arm in v219_read.labels(bench):
                value = cell('pass' if arm not in ('C', 'B') else 'fail',
                             enabled=('fixed-procedure',) if bench in (p.ZEBRA, 'alfworld') else (),
                             room='authored-room-%d' % (i//3) if bench == 'alfworld' else None)
                value.update(card_source=v219_read.card_source(bench, arm),
                             request_sha256=[digest((i, 'own' if arm == 'C' else arm))])
                if bench == p.ZEBRA and arm.startswith('X_'):
                    value.update(shared_with='source-F-'+str(i), shared_arm='F', request_sha256=[])
                if bench == p.ZEBRA and arm == 'B':
                    value.update(shared_with='source-C-'+str(i), shared_arm='C', request_sha256=[])
                if bench in ('searchqa', 'officeqa', 'spreadsheetbench') and arm == 'F':
                    value.update(v2='fail', shared_with='source-C-'+str(i), shared_arm='C', request_sha256=[])
                # Authored same-request rerun noise to exercise the registered second analysis.
                if bench == 'officeqa' and arm == 'X_searchqa' and i < 6:
                    value['request_sha256'] = [digest((i, 'own'))]
                values[(arm, 'authored-'+str(i), 0)] = value
        out[bench] = values
    return out


def test_registered_cross_matrix_uses_primary_and_identical_request_estimates(fast_statistics):
    units = authored_units()
    found = readout.readout(units, learned=[], procedures={}, label='owner-request-2026-11-02',
                            evidence=EVIDENCE, configuration=CHILD)
    assert found['evidence_kind'] == 'post_hoc_selected_upper_bound_transfer'
    assert found['learned'] == [] and found['imported'] == [p.ZEBRA, 'alfworld']
    assert found['q1_home'] is None and 'stages' not in found and 'stage_questions' not in found
    # Removing stage output must not lose the inherited five-panel exposure classification.
    inherited_units = {}
    for bench, values in units.items():
        inherited = {key: deepcopy(value) for key, value in values.items() if key[0] in ('F', 'C', 'B')}
        inherited.update({('S3', item, run): deepcopy(value)
                          for (arm, item, run), value in values.items() if arm == 'F'})
        inherited_units[bench] = inherited
    parent = readout.readout(inherited_units, learned=[], procedures={}, label='owner-request-2026-11-02',
        evidence=EVIDENCE, configuration=p.IMPLANT_V5, stages=['C', 'C', 'C', 'S3', 'S3', 'F'])
    for key in ('contrasts', 'imported', 'similar', 'dissimilar', 'q1_home', 'q2_similar', 'q3_noninferiority'):
        assert found[key] == parent[key]
    assert set(found['cross']) == set(p.MAIN_V5_ORDER)
    second = found['identical_request_analysis']
    assert 'stages' not in second and second['conclusions_follow'] == 'primary'
    for target in p.MAIN_V5_ORDER:
        assert set(found['cross'][target]) == set(p.MAIN_V5_ORDER)
        assert set(found['contrasts'][target]) == {'F-C', 'C-B', 'F-B'}
        for source, value in found['cross'][target].items():
            arm = 'F' if source == target else 'X_'+source
            assert value['arm'] == arm and value['card_source'] == source and value['n'] == 12
            items = readout._items(units[target], arm, 'C', 'F')
            assert value['accuracy']['L'] == readout._accuracy(units[target], arm, items, 'L')
            assert value['minus_card'] == readout._contrast(units[target], arm, 'C', items,
                                                           bootstrap=True, sensitivity=True)
            assert value['minus_final'] == readout._contrast(units[target], arm, 'F', items,
                                                            bootstrap=True, sensitivity=True)
            if source == target:
                assert value['minus_final']['mean'] == 0
            if target == p.ZEBRA:
                assert value['minus_card'] == found['contrasts'][target]['F-C']
                assert value['minus_final']['mean'] == 0
                assert second['cross'][target][source]['minus_final']['identical_request_items'] == 12
                assert 'by construction' in value['reading'] and 'not transfer' in value['reading']
    own = found['cross']['officeqa']['searchqa']
    tied = second['cross']['officeqa']['searchqa']
    assert own['minus_card']['mean'] == 1 and tied['minus_card']['mean'] == .5
    assert tied['minus_card']['identical_request_items'] == 6
    assert own['minus_final']['mean'] == 1 and tied['minus_final']['mean'] == .5


def test_cross_report_keeps_imports_and_emits_matrix_for_each_chain(tmp_path, monkeypatch, fast_statistics):
    root = tmp_path/'run'
    for chain in p.CHAINS:
        final = v217_implant.final_package(chain, EVIDENCE)
        package.save(root/chain, final)
        write_json(root/chain/'test-read.json', p.record('test-read', EVIDENCE,
            {'status': 'read', 'package_sha256': final.sha256}))
        for bench in p.MAIN_V5_ORDER:
            write_json(root/chain/'test'/bench/'unit.json', {'authored': True})
    opened = []
    def unseal(root, chain_root, chain, unit_roots, **options):
        assert options['configuration'] == CHILD
        assert [path.name for path in unit_roots] == list(p.MAIN_V5_ORDER)
        opened.append(chain)
        return {'units': authored_units(), 'label': 'owner-request-2026-11-02'}
    monkeypatch.setattr(evaluation, 'unseal', unseal)
    result = readout.report({'root': str(root), p.RECORD_HASH: 'authored-run', 'evidence': EVIDENCE,
                             'configuration': CHILD}, out=tmp_path/'reports')
    assert set(result) == set(opened) == set(p.CHAINS)
    for chain in p.CHAINS:
        value = read_json(tmp_path/'reports'/('readout-'+chain+'.json'))
        assert value['evidence_kind'] == 'post_hoc_selected_upper_bound_transfer'
        assert value['learned'] == [] and value['imported'] == [p.ZEBRA, 'alfworld']
        assert len(value['cross']) == 5 and 'stages' not in value


def test_cross_readout_refuses_extra_missing_diagonal_or_stage_arms(fast_statistics):
    values = authored_units()
    values['officeqa'][('X_officeqa', 'authored-0', 0)] = deepcopy(values['officeqa'][('F', 'authored-0', 0)])
    with pytest.raises(ValueError, match='arms must match'):
        readout.readout(values, learned=[], procedures={}, label='authored', evidence=EVIDENCE,
                        configuration=CHILD)
    with pytest.raises(ValueError, match='no stage'):
        readout.readout(authored_units(), learned=[], procedures={}, label='authored', evidence=EVIDENCE,
                        stages=['C','F'], configuration=CHILD)
    with pytest.raises(ValueError, match='no newly learned'):
        readout.readout(authored_units(), learned=['zebralogic'], procedures={}, label='authored',
                        evidence=EVIDENCE, configuration=CHILD)


def test_cross_unseal_requires_both_chains_even_if_other_chain_directory_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, '_ended', lambda root: root.name == 'G')
    monkeypatch.setattr(evaluation, 'continuation', lambda *_: pytest.fail('Cross read opened before chain D ended'))
    with pytest.raises(ValueError, match='both chains have ended'):
        evaluation.unseal(tmp_path, tmp_path/'G', 'G', [], run='authored', evidence=EVIDENCE,
                          configuration=CHILD)
