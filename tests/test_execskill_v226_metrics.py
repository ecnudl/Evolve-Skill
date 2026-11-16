"""The historical card gap cannot create or mask main-v10 learning harm."""
from copy import deepcopy
import hashlib

import pytest

from skillopt.execskill import profiles as p, v225_metrics as old, v226_metrics as m
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_v225_read import synthetic_aggregate


def estimate(block, pair, mean, ci):
    for side in ('primary', 'secondary'):
        block['pairs'][pair][side]['estimate'].update(mean=mean, ci95=ci)


def aggregate(c, c0, s1):
    value = synthetic_aggregate()
    value['configuration'] = p.MAIN_V10
    value['chains']['G']['package_changed'] = [True, False, False, False, False]
    for block in value['chains']['G']['per_bench'].values():
        block['acc'].update(C=c, C0=c0, S1=s1)
        for anchor, base in [('C', c), ('C0', c0)]:
            delta = s1 - base
            estimate(block, 'S1-' + anchor, delta, [delta - .01, delta + .01])
    return value


@pytest.mark.parametrize('c,c0,s1,old_harm,new_harm', [(.8, .2, .3, 4, 0), (.2, .8, .7, 0, 4)])
def test_c0_reanchoring_removes_false_harm_and_exposes_masked_harm(fast_statistics, c, c0, s1, old_harm, new_harm):
    value = aggregate(c, c0, s1)
    before = deepcopy(value)
    historical = old.compute({**value, 'configuration': p.MAIN_V9}, 'G')
    result = m.compute(value, 'G')
    for side in ('P', 'S'):
        assert historical['changed_only'][side]['harmed'] == old_harm
        assert result['changed_only'][side]['harmed'] == new_harm
        assert result['incremental_changed'][side]['harmed'] == new_harm
        assert result['changed_only'][side]['TS'] == pytest.approx(s1 - c0)
        assert result['changed_only'][side]['TD'] == pytest.approx(s1 - c0)
        assert result['anchor_C'][side] == historical['anchor_C'][side]
    assert result['anchor_readings']['anchor_C'] == 'descriptive historical comparison only'
    assert result['version'] == 'main-v10-cl-metrics-v1'
    assert value == before


def test_later_incremental_harm_is_distinct_from_cumulative_start_harm(fast_statistics):
    value = aggregate(.4, .2, .9)
    value['chains']['G']['package_changed'] = [False, True, False, False, False]
    for block in value['chains']['G']['per_bench'].values():
        block['acc']['S2'] = .8
        estimate(block, 'S2-C', .4, [.39, .41])
        estimate(block, 'S2-C0', .6, [.59, .61])
        estimate(block, 'S2-S1', -.1, [-.11, -.09])
    result = m.compute(value, 'G')
    for side in ('P', 'S'):
        assert result['changed_only'][side]['harmed'] == 0
        assert result['incremental_changed'][side]['harmed'] == 4
        assert result['changed_only'][side]['TS'] == -.1
        assert result['changed_only'][side]['TD'] == -.1
        assert result['incremental_changed'][side]['per_step'][0]['contrast'] == 'S2-S1'


def test_ts_td_use_registered_secondary_pairs_not_differences_of_reanchored_means(fast_statistics):
    value = aggregate(.4, .2, .3)
    value['chains']['G']['package_changed'] = [False, True, False, False, False]
    for block in value['chains']['G']['per_bench'].values():
        estimate(block, 'S2-C0', .25, [.2, .3])
        estimate(block, 'S2-S1', .07, [.06, .08])
        block['pairs']['S2-S1']['secondary']['estimate']['mean'] = .03
    result = m.compute(value, 'G')
    for side, expected in [('P', .07), ('S', .03)]:
        assert result['changed_only'][side]['TS'] == expected
        assert result['changed_only'][side]['TD'] == expected


@pytest.mark.parametrize('ci,uncertain,harmed', [(None, 4, 0), ([-.2, .1], 0, 0), ([-.2, -.01], 0, 4)])
def test_incremental_uses_the_same_registered_uncertainty_rule(fast_statistics, ci, uncertain, harmed):
    value = aggregate(.4, .8, .7)
    for block in value['chains']['G']['per_bench'].values():
        estimate(block, 'S1-C0', -.1, ci)
    result = m.compute(value, 'G')
    assert result['incremental_changed']['P']['uncertain'] == uncertain
    assert result['incremental_changed']['P']['harmed'] == harmed


def test_main_v9_metrics_source_is_byte_identical_and_new_definition_is_registered():
    from pathlib import Path
    assert hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest() == (
        '5c3fb6c3a23b53503e7ecfdc0569f01bda7a215b8b67e21a6db455feefe5aafd')
    assert p.main_v10_identity()['cl_metrics']['version'] == m.VERSION
    assert old.VERSION == 'main-v9-cl-metrics-v1'
