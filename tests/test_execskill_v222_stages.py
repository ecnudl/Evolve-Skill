"""P0 is C; an empty learned package is a distinct format-only stage."""
import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import evaluation, package, profiles as p, v222_cards


def test_p0_and_empty_intermediate_stages_are_not_confused(tmp_path):
    initial = v222_cards.initial_package(evidence='engineering_fixture', step='G/s0')
    vacant = package.empty(step='G/s2', evidence=initial.evidence)
    proc = v222_cards.make_segment('searchqa', 'Use only supplied evidence.', {'kind': 'public_evidence'},
                                  evidence=initial.evidence, step=2, ordinal=9)
    final = package.with_(initial, step='G/s5', add=[proc])
    for value in (vacant, final):
        package.save(tmp_path, value)
    order = p.active_benches(p.MAIN_V8)
    for k, (bench, value) in enumerate(zip(order, (initial, vacant, initial, final, final)), 1):
        write_json(tmp_path / ('s%d-%s' % (k, bench)) / 'step.json', p.record('step', initial.evidence,
            {'chain': 'G', 'k': k, 'bench': bench, 'package_sha256': value.sha256}))
    result = evaluation.stage_rows(tmp_path, 'G', order, final, initial, configuration=p.MAIN_V8)
    assert result['rows'] == ['C', 'C', 'S2', 'C', 'F', 'F']
    assert result['packages'] == {'S2': vacant}
    assert evaluation._stage_arms(result, final, configuration=p.MAIN_V8) == (result['rows'], {'S2': vacant})
    with pytest.raises(ValueError, match='stage arms'):
        evaluation._stage_arms(result, final)


def test_unchanged_p0_stays_c_in_every_stage(tmp_path):
    initial = v222_cards.initial_package(evidence='engineering_fixture', step='G/s0')
    order = p.active_benches(p.MAIN_V8)
    for k, bench in enumerate(order, 1):
        write_json(tmp_path / ('s%d-%s' % (k, bench)) / 'step.json', p.record('step', initial.evidence,
            {'chain': 'G', 'k': k, 'bench': bench, 'package_sha256': initial.sha256}))
    result = evaluation.stage_rows(tmp_path, 'G', order, initial, initial, configuration=p.MAIN_V8)
    assert result == {'rows': ['C'] * 6, 'packages': {}}
