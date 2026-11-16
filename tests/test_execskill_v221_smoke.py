"""SX must prove each main-v7 mechanism with authored zero-model records."""
from copy import deepcopy

import pytest

from skillopt.execskill import profiles as p, v214_smoke, v214_stages, v221_smoke
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def test_automatic_retry_demo_uses_production_unit_runner_and_is_idempotent(tmp_path):
    first = v221_smoke.recovery_demo(tmp_path)
    assert first['passed'] and first['elapsed_seconds'] == 60
    assert first['attempts'] == ['attempt-1', 'attempt-2']
    assert first['recovery']['by'] == 'system'
    assert first == v221_smoke.recovery_demo(tmp_path)


def test_sx_exercises_all_learning_changes_and_retains_main_v6_mechanisms(tmp_path):
    found = v214_stages.sx(tmp_path, configuration=p.MAIN_V7)
    assert v221_smoke.check_result(found) == found
    assert found['inherited']['configuration'] == p.MAIN_V6
    assert found['model_calls'] == found['sealed_reads'] == 0
    assert found['automatic_retry']['elapsed_seconds'] == 60
    assert set(found['learning']['decisions']) == {'training', 'confirmation', 'acceptance'}
    assert v214_smoke.stages_of(p.MAIN_V7) == v214_smoke.stages_of(p.MAIN_V6)


@pytest.mark.parametrize('path', [
    ('learning', 'decisions', 'training'),
    ('learning', 'decisions', 'confirmation'),
    ('learning', 'decisions', 'acceptance'),
    ('learning', 'early_acceptance'),
    ('learning', 'split_merge'),
    ('learning', 'audit_non_drop'),
    ('automatic_retry',),
    ('inherited', 'stage_rows'),
    ('inherited', 'read_reuse'),
])
def test_passed_bit_does_not_replace_required_mechanism_evidence(tmp_path, path):
    found = deepcopy(v221_smoke.structural_smoke(tmp_path))
    branch = found
    for part in path[:-1]:
        branch = branch[part]
    del branch[path[-1]]
    with pytest.raises(ValueError):
        v221_smoke.check_result(found)


def test_modified_rule_constants_or_skipped_retry_delay_refuse_readiness(tmp_path):
    found = v221_smoke.structural_smoke(tmp_path)
    bad = deepcopy(found)
    for record in bad['learning']['decisions'].values():
        record['constants']['GAIN_MIN_ITEMS'] = 2
    with pytest.raises(ValueError, match='identical gain-and-no-harm'):
        v221_smoke.check_result(bad)
    bad = deepcopy(found)
    bad['automatic_retry']['elapsed_seconds'] = 0
    with pytest.raises(ValueError, match='simulated 60-second'):
        v221_smoke.check_result(bad)
