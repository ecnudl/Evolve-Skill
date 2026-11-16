"""The additive read configuration never falls back to a main-v9 record."""
from skillopt.execskill import package, profiles as p, readout, v225_read
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_v225_read import synthetic_units
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from pathlib import Path as _CapturePath
import pytest as _capture_pytest
_PARENT_CAPTURES = [_CapturePath(__file__).parent / f'fixtures/execskill/v{v}_parents_before.json'
                    for v in ('220', '221', '222', '225', '226')]
needs_parent_captures = _capture_pytest.mark.skipif(
    not all(capture.exists() for capture in _PARENT_CAPTURES),
    reason='parent captures not published (they hold ALFWorld game text)')


def test_main_v10_aggregate_and_readout_keep_the_new_configuration(fast_statistics):
    units = synthetic_units()
    aggregate = v225_read.aggregates(units, chain='G', run='authored', run_root='/authored-v10',
        label='authored', evidence='engineering_fixture', final=package.empty(step='G/s5',
        evidence='engineering_fixture'), package_changed=[False] * 5, configuration=p.MAIN_V10)
    assert aggregate['configuration'] == p.MAIN_V10
    assert aggregate['chains']['G']['readout']['configuration'] == p.MAIN_V10
    record = readout.readout(units, learned=[], procedures={}, label='authored',
        evidence='engineering_fixture', configuration=p.MAIN_V10)
    assert record['configuration'] == p.MAIN_V10
    assert set(record['arms']) == set(p.MAIN_V5_ORDER)


def test_main_v9_readout_defaults_remain_exact(fast_statistics):
    units = synthetic_units()
    arguments = dict(learned=[], procedures={}, label='authored', evidence='engineering_fixture')
    assert v225_read.readout(units, **arguments) == v225_read.readout(
        units, **arguments, configuration=p.MAIN_V9)


def test_main_v10_structural_readout_demo_uses_the_pinned_reference(fast_statistics):
    v225_read.structural_readout_demo.cache_clear()
    result = v225_read.structural_readout_demo(configuration=p.MAIN_V10)
    assert result['passed'] and result['anchor_C_equal']
    assert result['model_calls'] == result['sealed_reads'] == 0


@needs_parent_captures
def test_main_v10_full_structural_smoke_uses_real_registration_paths(tmp_path, fast_statistics, monkeypatch):
    from skillopt.execskill import v225_smoke
    monkeypatch.setitem(p.RUN_ROOTS, p.MAIN_V10, str(tmp_path/'v226'))
    result = v225_smoke.structural_smoke(tmp_path/'v226-scratch', configuration=p.MAIN_V10)
    assert v225_smoke.check_structural(result) == result
    assert result['configuration'] == p.MAIN_V10 and result['passed']
    assert result['model_calls'] == result['sealed_reads'] == 0
    assert result['card_phase']['consumed_acceptance'] == 100
    assert result['readout']['anchor_C_equal'] and len(result['read_plans']['units']) == 40
