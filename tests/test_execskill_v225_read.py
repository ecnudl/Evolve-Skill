"""Authored main-v9 aggregate matrices, all registered contrasts and side rules."""
from copy import deepcopy

import pytest

from skillopt.execskill import package, profiles as p, v225_read as r, v225_cards
from tests.test_execskill_readout import cell
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401

EVIDENCE='engineering_fixture'


def synthetic_units():
    units={}
    for b,bench in enumerate(p.MAIN_V5_ORDER):
        rows={}
        for a,arm in enumerate(r.ARMS):
            for item in range(12):
                row=cell('pass' if (item+b)%12 < 2+a else 'fail')
                row.update(request_sha256=['same' if arm in ('S1','C0') else arm+str(item)],
                           room='room-'+str(item%3),block='authored')
                rows[arm,str(item),0]=row
        units[bench]=rows
    return units


def synthetic_aggregate():
    final=package.empty(step='G/s5',evidence=EVIDENCE)
    return r.aggregates(synthetic_units(),chain='G',run='authored',run_root='/authored',label='authored',
                        evidence=EVIDENCE,final=final,package_changed=[False,True,False,True,False])


def test_every_registered_pair_present_and_f_alias_has_no_extra_cells(fast_statistics):
    units=synthetic_units()
    agg=synthetic_aggregate()
    pb=agg['chains']['G']['per_bench']
    for bench,block in pb.items():
        assert set(block['pairs'])=={a+'-'+b for a,b in r.registered_pairs()}
        assert block['acc']['F']==block['acc']['S5']
        assert block['items_all_arms']==12
        assert len(units[bench])==10*12
    assert agg['arm_map']['F']=='alias of S5'
    assert agg['chains']['G']['stage_rows']==['C','S1','S2','S3','S4','S5']
    assert agg['chains']['G']['stage_row_kinds']==['anchor']+['measured']*5
    assert len(agg['chains']['G']['readout']['stage_questions'])==5


def test_i_uses_l_and_c_end_uses_h_unknown_sensitivity(fast_statistics):
    units=synthetic_units()
    assert r.side('I')=='L' and r.side('C_end')=='H'
    for arm in ('I','C0','C_end'):
        units['officeqa'][arm,'0',0]['v2']='unknown_infrastructure'
    # A registered unknown token is read conservatively on L, permissively on H.
    from skillopt.execskill.readout import UNKNOWN
    token=next(iter(UNKNOWN))
    for arm in ('I','C0','C_end'):
        units['officeqa'][arm,'0',0]['v2']=token
    assert r.differences(units['officeqa'],'I','C0',['0'])==[-1]
    assert r.differences(units['officeqa'],'C_end','C0',['0'])==[0]


def test_secondary_ties_identical_requests_even_with_fresh_flips(fast_statistics):
    agg=synthetic_aggregate()
    pair=agg['chains']['G']['per_bench']['officeqa']['pairs']['S1-C0']
    assert pair['items_reading_one_cell']==0
    assert pair['items_tied_by_identical_requests']==12
    assert pair['secondary']['tied']==12
    assert pair['secondary']['estimate']['mean']==0


def test_i_contains_cards_only_and_learned_own_card_counts(fast_statistics):
    from tests.execskill_fakes_env import procedure
    card=v225_cards.make_card('searchqa','Read evidence carefully.',evidence=EVIDENCE)
    final=package.Package((card,procedure('fx-read-procedure',('applies','before_call'),origin='officeqa')),
                          'G/s5',EVIDENCE)
    assert r.cards_only(final).procedures==(card,)
    assert r.arms(final,'i',chain='G',evidence=EVIDENCE)['I'].package.procedures==(card,)
    agg=r.aggregates(synthetic_units(),chain='G',run='authored',run_root='/authored',label='authored',
                    evidence=EVIDENCE,final=final,package_changed=[True]*5)
    assert agg['chains']['G']['learned']==['searchqa','officeqa']
    assert agg['chains']['G']['cards']['searchqa']['chars']==len('Read evidence carefully.')


def test_first_call_touch_is_distinct_from_full_sequence_tie_rule():
    units=r.with_alias(synthetic_units())
    rows=units['alfworld']
    for item in ('0','1'):
        rows['C',item,0]['request_sha256']=['same-first','historical-later']
        rows['F',item,0]['request_sha256']=['same-first','fresh-later']
    assert r.first_call_touch(rows,'F','C',['0','1'])=={'touched':0,'n':2,'unknown':0}
    rows['F','1',0]['request_sha256']=[]
    assert r.first_call_touch(rows,'F','C',['0','1'])=={'touched':0,'n':2,'unknown':1}


def test_each_arm_has_own_short_answer_origin_and_absolute_alignment(fast_statistics):
    from skillopt.execskill import readout
    units=synthetic_units()
    for rows in units.values():
        for (arm,item,run),row in rows.items():
            origin=1_700_000_000+3600*r.ARMS.index(arm)
            later=int(item)>=6
            row.update(dispatch_ts=origin+(1000 if later else 0)+10*int(item),
                       completion_tokens=[10 if later else 100])
    before=deepcopy(units)
    result=r.readout(units,learned=[],procedures={},label='authored',evidence=EVIDENCE)
    for rows in result['arms'].values():
        for arm,entry in rows.items():
            actual='S5' if arm=='F' else arm
            origin=1_700_000_000+3600*r.ARMS.index(actual)
            assert entry['diagnostic_origin']==origin
            assert entry['short_answer_reference']['status']=='defined'
            assert entry['short_answer_reference']['median']==100
            assert [w['window'] for w in entry['windows']]==[0,1]
            assert [w['short_answer_share'] for w in entry['windows']]==[0,1]
            assert entry['windows'][1]['start_unix_seconds']==origin+900
            assert entry['windows'][1]['end_unix_seconds']==origin+1800
    assert units==before  # absolute dispatch timestamps remain unchanged
    old=readout.arm_table(units['officeqa'],configuration=p.MAIN_V8)
    assert old==readout.arm_table(units['officeqa'])
    assert old['C0']['short_answer_reference']['status']=='no_cell_with_usage'
    assert 'diagnostic_origin' not in old['C0']
