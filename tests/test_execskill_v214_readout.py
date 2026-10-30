"""The owner's per-step home/related/unrelated table, using authored scores only."""
import pytest

from skillopt.execskill import profiles as p, readout
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_readout import cell

CONFIG = 'main-v5'
ROWS = ['C', 'C', 'S2', 'S2', 'S4', 'F']


def authored_units():
    return {bench: {(arm, 'authored-%d' % i, 0): cell(
        'pass' if arm != 'B' and (arm != 'C' or i % 3) else 'fail',
        enabled=('authored-procedure',) if arm not in ('B', 'C') else (),
        room='room-%d' % (i // 3) if bench == 'alfworld' else None)
        for arm in ('F', 'C', 'B', 'S2', 'S4') for i in range(12)}
        for bench in p.read_benches(CONFIG)}


def test_map_changes_interpretation_but_never_the_five_bench_table(fast_statistics):
    units = authored_units()
    result = readout.readout(units, learned=['officeqa'], procedures={}, label='authored',
        evidence='engineering_fixture', stages=ROWS, configuration=CONFIG)
    assert set(result['stages']) == set(p.read_benches(CONFIG))
    assert all(len(entries) == 6 for entries in result['stages'].values())
    questions = result['stage_questions']
    assert len(questions) == 5
    assert [row['home_bench'] for row in questions] == list(p.CONFIGURATIONS[CONFIG]['order'])
    assert questions[0]['related_benches'] == ['officeqa']
    assert questions[1]['related_benches'] == ['searchqa', 'spreadsheetbench']
    assert questions[2]['related_benches'] == []
    assert set(questions[2]['unrelated_benches']) == set(p.read_benches(CONFIG)) - {'zebralogic'}
    assert questions[4]['related_benches'] == []
    for row in questions:
        assert {row['home_bench'], *row['related_benches'], *row['unrelated_benches']} == set(p.read_benches(CONFIG))
    assert result['imported'] == ['alfworld'] and result['learned'] == ['officeqa']
    assert all(set(contrasts) == {'F-C', 'C-B', 'F-B'} for contrasts in result['contrasts'].values())


def test_empty_rows_are_explicit_zero_without_inference_and_duplicate_rows_remain(fast_statistics):
    result = readout.readout(authored_units(), learned=[], procedures={}, label='authored',
        evidence='engineering_fixture', stages=ROWS, configuration=CONFIG)
    empty = result['stage_questions'][0]
    assert empty['q1_home']['searchqa'] == {'mean': 0.0, 'reading': 'no program accepted at this step'}
    assert empty['q2_similar']['officeqa'] == empty['q1_home']['searchqa']
    assert empty['q3_noninferiority']['mean'] == 0
    assert 'adverse' not in empty['q3_noninferiority']
    assert all(row[1]['minus_card'] == empty['q1_home']['searchqa'] for row in result['stages'].values())
    assert result['stage_questions'][2]['arm'] == 'S2'
    assert result['stage_questions'][2]['reuses_row'] == 2
    assert result['stage_questions'][2]['q1_home']['zebralogic']['mean'] == pytest.approx(1 / 3)


def test_each_nonempty_row_uses_its_arm_for_home_related_and_each_unrelated_bench(fast_statistics):
    units = authored_units()
    # Make S2 worse and leave F strong, so silently using F for stage inference is visible.
    for data in units.values():
        for (arm, _, _), value in data.items():
            if arm == 'S2':
                value['v2'] = value['token'] = 'fail'
    result = readout.stage_questions(units, ROWS, configuration=CONFIG)
    row = result[1]
    assert row['q1_home']['officeqa']['mean'] == pytest.approx(-2 / 3)
    assert set(row['q2_similar']) == {'searchqa', 'spreadsheetbench'}
    for contrast in row['q2_similar'].values():
        assert contrast['reading'] == 'descriptive' and len(contrast['ci95']) == 2
        assert contrast['mean'] == pytest.approx(-2 / 3)
    ni = row['q3_noninferiority']
    assert set(ni['per_bench']) == {'zebralogic', 'alfworld'}
    assert ni['margin'] == -0.05 and ni['reading'] == 'noninferiority_not_established'
    for contrast in ni['per_bench'].values():
        assert contrast['margin'] == -0.05
        assert contrast['adverse']['mean'] == pytest.approx(-2 / 3)
        assert contrast['complete_case']['lower95_one_sided'] < -0.05
        assert contrast['reading'] == 'noninferiority_not_established'


def test_per_bench_low_fire_keeps_registered_noninferiority_interpretation(fast_statistics):
    units = authored_units()
    for (arm, _, _), value in units['zebralogic'].items():
        if arm == 'S2':
            value['enabled'] = []
    result = readout.q3_noninferiority(units, ['officeqa'], arm='S2', configuration=CONFIG)
    low = result['per_bench']['zebralogic']
    assert low['enable_rate'] == 0 and low['margin'] == -0.05 and low['n'] == 12
    assert low['reading'] == 'cannot_act_by_construction' and low['mean'] == pytest.approx(1 / 3)
    assert result['per_bench']['alfworld']['reading'] == 'noninferiority_established'


def test_zebra_blank_contrasts_are_exactly_zero_even_for_shared_unknowns(fast_statistics):
    units = authored_units()
    for (arm, item, run), value in units['zebralogic'].items():
        if arm in ('C', 'B'):
            value['v2'] = value['token'] = 'unknown' if item.endswith('0') else 'pass'
            if arm == 'B':
                value.update(shared_with='authored-C-' + item, shared_arm='C')
    result = readout.readout(units, learned=[], procedures={}, label='authored', evidence='engineering_fixture',
                            stages=ROWS, configuration=CONFIG)
    assert result['contrasts']['zebralogic']['C-B']['mean'] == 0
    assert result['arms']['zebralogic']['B']['shared'] == 12


def test_legacy_similarity_and_stage_table_shape_stay_unchanged():
    assert readout.similar(['officeqa']) == ['searchqa', 'livemath', 'spreadsheetbench']
    assert readout.similar(['officeqa'], 'main-v4') == readout.similar(['officeqa'])
    assert readout.dissimilar(['zebralogic'], 'zebra-pc-v13') == []
    table = readout.stage_table({'searchqa': authored_units()['searchqa']}, ['C', 'C'])
    assert 'minus_card' not in table['searchqa'][1]
