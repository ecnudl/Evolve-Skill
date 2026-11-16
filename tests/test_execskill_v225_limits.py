"""Every main-v9 cap is rederived from registered cells, with no discounts."""
from copy import deepcopy
from fractions import Fraction

from skillopt.execskill import budgets, profiles as p, v225_limits as limits


def test_card_phase_and_cross_card_procedure_reservations():
    assert limits.extra_cells(p) == {
        'searchqa': {'selftest': {'searchqa': (0,1800)}, 'accept': {'searchqa': (0,360)},
                     'confirm': {'searchqa': (0,240), 'officeqa': (0,120)}},
        'officeqa': {'selftest': {'officeqa': (0,216)}, 'accept': {'officeqa': (0,256)},
                     'confirm': {'searchqa': (0,120), 'spreadsheetbench': (0,120)}},
        'zebralogic': {'selftest': {'zebralogic': (0,360)}, 'accept': {'zebralogic': (0,80)},
                      'confirm': {}},
        'spreadsheetbench': {'selftest': {'spreadsheetbench': (0,372)},
                            'accept': {'spreadsheetbench': (0,144)}, 'confirm': {'officeqa': (0,120)}}}
    schedule = deepcopy(p.CONFIG_SCHEDULE_CELLS[p.MAIN_V8])
    for home, phases in limits.extra_cells(p).items():
        for phase, additions in phases.items():
            for target, (cards, procedures) in additions.items():
                old_c, old_p = schedule[home][phase].get(target, (0,0))
                schedule[home][phase][target] = (old_c+cards, old_p+procedures)
            derived = p.legacy._round_up(3 * (sum(p.CELL_ANCHORS[b][1]*(c+Fraction(8,5)*q)
                for b,(c,q) in schedule[home][phase].items())+16*520192),100000)
            assert p.CONFIG_STEP_CAPS[p.MAIN_V9][home][phase] == max(
                p.CONFIG_STEP_CAPS[p.MAIN_V8][home][phase], derived)
    assert schedule == p.CONFIG_SCHEDULE_CELLS[p.MAIN_V9]


def test_step_cap_arithmetic_matches_brief():
    expected = {'searchqa': (351300000,530500000,1152700000),
                'officeqa': (234100000,341800000,1040300000),
                'zebralogic': (131800000,280700000,1133200000),
                'spreadsheetbench': (163300000,274200000,1099400000)}
    for bench, values in expected.items():
        assert tuple(p.CONFIG_STEP_CAPS[p.MAIN_V9][bench][k] for k in ('selftest','accept','confirm')) == values
        for unchanged in ('run','examiner'):
            assert p.CONFIG_STEP_CAPS[p.MAIN_V9][bench][unchanged] == p.CONFIG_STEP_CAPS[p.MAIN_V8][bench][unchanged]
    assert limits.identity()['step_caps_sum'] == 6966400000


def test_ten_fresh_arms_include_c_end_and_own_every_read_unit():
    assert p.read_arms_of(p.MAIN_V9) == limits.READ_ARMS == (
        'B','C0','C','S1','S2','S3','S4','S5','I','C_end')
    assert p.TEST_READ_CELLS[p.MAIN_V9] == {b:(4*n,6*n) for b,n in p.MAIN_V5_TEST_ITEMS.items()}
    assert p.stage_arms_max(p.MAIN_V9) == 5 and p.estimate_arms(p.MAIN_V9) == 6
    assert p.read_estimate_terms({b:{'card':11,'procedure':17} for b in p.MAIN_V5_ORDER},
        Fraction(13,10),p.MAIN_V9) == {b:Fraction(13,10)*n*(4*11+6*17)
                                      for b,n in p.MAIN_V5_TEST_ITEMS.items()}
    units = limits.read_unit_caps(p)
    assert len(units) * len(p.MAIN_V5_ORDER) == 40
    assert tuple(units['anchor'].values()) == (38000000,38000000,35000000,36000000,80000000)
    for label in ('s1','s2','s3','s4','s5','i'):
        assert tuple(units[label].values()) == (32000000,32000000,31000000,31000000,54000000)
    assert tuple(units['c_end'].values()) == (30000000,30000000,29000000,29000000,44000000)


def test_overlay_read_stays_inside_parent_cap_and_totals_recompute():
    identity = limits.identity()
    assert identity['read_retry']['base_read_cap'] == 574000000
    assert identity['read_retry']['reserve'] == 80000000
    assert identity['read_retry']['derived_read_cap'] == 654000000
    assert identity['read_retry']['registered_read_cap'] == 743000000
    cfg = p.CONFIGURATIONS[p.MAIN_V9]
    assert cfg['redo_reserve'] == 1152700000
    assert cfg['solver_cap'] == p.legacy._round_up(6966400000+743000000+1152700000,5000000) == 8865000000
    assert limits.WRITER_RESERVATION == 613120
    assert limits.WRITER_CALLS_PER_CHAIN == 24
    assert p.CONFIG_GLM_CAP[p.MAIN_V9] == p.CONFIG_GLM_CAP[p.MAIN_V8]+24*613120 == 7607505664
    for chain in p.CHAINS:
        assert budgets.chain_caps(chain,p.MAIN_V9)['overall'] == 16472505664
        assert budgets.chain_caps(chain,p.MAIN_V9)[chain+':test'] == 743000000
    assert sum(budgets.chain_caps(c,p.MAIN_V9)['overall'] for c in p.CHAINS) == 32945011328
    assert identity['smoke_additions'] == {'writer_calls':3,'solver_cells':60,
                                         'solver_tokens':1000000,'method_tokens':1839360}
    assert not any(identity[key] for key in ('reuse_discount','fresh_pool_discount','overlap_discount'))
