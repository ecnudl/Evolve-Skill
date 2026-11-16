"""Cross cards require measured five-percent gain and an unoccupied route slot."""
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.execskill import profiles as p, v222_gate as gate, v225_cards as cards, v225_phase as phase
from skillopt.execskill.package import empty, save
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v225_phase import AuthoredStep


def packages(home='searchqa', target='officeqa'):
    base=empty(step='G/s0',evidence='engineering_fixture')
    card=cards.make_card(home,'Compare the evidence and check the requested quantity.',writer_sha256='a'*64)
    parent=phase.place_card(base,card,step='G/s1-'+home)
    copied=cards.make_card(home,cards.metadata(card)['text'],route=target,ordinal=110,writer_sha256='a'*64)
    return parent,phase.place_card(parent,copied,step=parent.step),card


def slices():
    sizes={'searchqa':60,'officeqa':42,'zebralogic':60,'spreadsheetbench':55,'alfworld':20}
    return {b:[{'task_id':b+'-%03d'%i,'benchmark':b,'partition':'practice',
        'public':{'question':'An authored question.'},'private':{'answer':'authored'}} for i in range(n)]
            for b,n in sizes.items()}


def inspector(bench,parent,candidate,items):
    def signature(package):
        return {'request_sha256':digest(cards.compose(bench,'Fixed format.',package)),
                'post_call':[],'faults':[]}
    pairs={row['task_id']:{'S':signature(parent),"S'":signature(candidate)} for row in items}
    fired=[key for key,pair in pairs.items() if not gate.v221_rule.same_request(pair['S'],pair["S'"])]
    return {'bench':bench,'slice_ids':list(pairs),'fired':len(fired),'fired_items':fired,
            'signatures':pairs,'faults':[],'identity_proven':not fired,
            'parent_sha256':parent.sha256,'candidate_sha256':candidate.sha256}


def paired(items,fixed,broken):
    return {(arm,row['task_id']):[{'judge':{'v2':{'token':'pass' if (
        index<fixed and arm=="S'" or fixed<=index<fixed+broken and arm=='S') else 'fail'}}}]
        for index,row in enumerate(items) for arm in ('S',"S'")}


@pytest.mark.parametrize('target,fixed,broken,passed',[
    ('officeqa',3,0,True),('officeqa',2,0,False),('officeqa',5,2,True),('officeqa',4,2,False),
    ('officeqa',0,0,False),('officeqa',8,5,True),('officeqa',9,6,True),('officeqa',10,7,False),
    ('spreadsheetbench',3,0,True),('spreadsheetbench',2,0,False),('searchqa',3,0,True),('searchqa',2,0,False)])
def test_cross_card_gain_cases_are_distinct_from_old_no_harm_rule(target,fixed,broken,passed):
    home='searchqa' if target=='officeqa' else 'officeqa'
    parent,candidate,_=packages(home,target); calls=[]
    def run(bench,before,after,items):
        calls.append((bench,len(items)))
        return paired(items,fixed,broken)
    def forbidden_narrow(*a,**kw): pytest.fail('A rejected cross card must never be narrowed')
    result,record=gate.check(home=home,parent=parent,candidate=candidate,slices=slices(),
        inspector=inspector,run_pairs=run,phase='cross_card',configuration=p.MAIN_V9,narrower=forbidden_narrow)
    assert record['passed'] is passed
    assert (result.sha256 if result else None)==(candidate.sha256 if passed else None)
    assert calls==[(target,len(slices()[target]))]
    assert record['paired_item_calls']==2*len(slices()[target])
    assert record['narrowing'] is None
    assert record['benches'][target]['card_rule']['gain_floor']==3
    assert record['benches'][target]['card_rule']['decision']==('accept' if passed else 'reject')
    assert all(row['identity_proven'] and row['paired_item_calls']==0
               for bench,row in record['benches'].items() if bench!=target)
    assert gate.counts(fired=len(slices()[target]),fixed=0,broken=0,items=len(slices()[target]))['passed']


def test_cross_rule_is_only_registered_for_main_v9():
    parent,candidate,_=packages()
    with pytest.raises(ValueError,match='registered cross-gate phase'):
        gate.check(home='searchqa',parent=parent,candidate=candidate,slices=slices(),
            inspector=inspector,run_pairs=lambda *args:{},phase='cross_card',configuration=p.MAIN_V8)


def test_failed_cross_copy_leaves_package_byte_identical():
    parent,candidate,_=packages()
    result=phase.admit_cross(parent,candidate,'officeqa',{'passed':False})
    assert result is parent and result.to_json()==parent.to_json()


def test_cross_copy_never_overwrites_own_card_or_another_cross_copy():
    parent,candidate,_=packages()
    with pytest.raises(ValueError,match='empty target card slot'):
        phase.admit_cross(candidate,candidate,'officeqa',{'passed':True})
    own=cards.make_card('officeqa','Check arithmetic and dimensions.',k=2)
    occupied=phase.place_card(parent,own,step='G/s2-officeqa')
    with pytest.raises(ValueError,match='empty target card slot'):
        phase.admit_cross(occupied,candidate,'officeqa',{'passed':True})


def test_accepted_own_card_replaces_cross_copy_and_preserves_other_cards():
    parent,candidate,home=packages()
    old=candidate.card_for('officeqa')
    own=cards.make_card('officeqa','Check arithmetic and dimensions.',k=2)
    replaced=phase.place_card(candidate,own,step='G/s2-officeqa')
    assert replaced.card_for('officeqa')==own and old.id not in replaced.order
    assert replaced.card_for('searchqa')==home
    assert cards.metadata(replaced.card_for('officeqa'))['home']=='officeqa'


@pytest.mark.parametrize('passing', [True,False])
def test_production_cross_controller_binds_gate_and_copies_text_exactly(tmp_path,monkeypatch,passing):
    from skillopt.execskill import v222_runtime
    parent,_,home=packages();st=AuthoredStep(tmp_path,parent=parent);seen=[]
    def cross(_st,attempt,*,unit,phase,parent,candidate):
        assert phase=='cross_card' and unit=='card-cross-officeqa'
        copy=candidate.card_for('officeqa')
        assert cards.metadata(copy)['text'].encode()==cards.metadata(home)['text'].encode()
        assert copy.origin=='searchqa' and cards.metadata(copy)['route']=='officeqa'
        assert copy.lineage['engineer_call']==home.lineage['engineer_call']
        found,record=gate.check(home='searchqa',parent=parent,candidate=candidate,slices=slices(),
            inspector=inspector,run_pairs=lambda b,old,new,items:paired(items,3 if passing else 2,0),
            phase=phase,configuration=p.MAIN_V9)
        seen.append(record)
        return found,record
    monkeypatch.setattr(v222_runtime,'cross_gate',cross)
    output,records=phase.cross_cards(st,parent,home)
    assert bool(output.card_for('officeqa')) is passing
    if not passing: assert output.sha256==parent.sha256
    assert records[0]['gate']==seen[0]
    assert seen[0]['configuration']==p.MAIN_V9
    assert seen[0]['parent_sha256']==parent.sha256
    from skillopt.continual_eval.core import read_json
    persisted=read_json(st.root/'card-cross-officeqa'/'attempt-1'/'v225-cross-card.json')
    assert p.verified(persisted,'v222-cross-gate')==seen[0]


def test_occupied_slot_skips_gate_and_cross_copy_is_not_reexported(tmp_path,monkeypatch):
    from skillopt.execskill import v222_runtime
    parent,candidate,home=packages();st=AuthoredStep(tmp_path,parent=candidate)
    monkeypatch.setattr(v222_runtime,'cross_gate',lambda *a,**kw:pytest.fail('Occupied slot invoked gate'))
    output,records=phase.cross_cards(st,candidate,home)
    assert output is candidate and records==[{'target':'officeqa','decision':'occupied_slot','calls':0}]
    foreign=candidate.card_for('officeqa')
    with pytest.raises(ValueError,match='Never re-export'):
        phase.cross_cards(st,candidate,foreign)


@pytest.mark.parametrize('corruption', ['parent','candidate','slice'])
def test_cross_evidence_rejects_wrong_package_or_slice_binding(corruption):
    parent,candidate,_=packages()
    def broken(bench,before,after,items):
        result=inspector(bench,before,after,items)
        if corruption=='slice': result['slice_ids']=list(reversed(result['slice_ids']))
        else: result[corruption+'_sha256']='0'*64
        return result
    with pytest.raises(ValueError,match='binds the same packages and harm slice'):
        gate.check(home='searchqa',parent=parent,candidate=candidate,slices=slices(),inspector=broken,
            run_pairs=lambda *a:pytest.fail('Invalid binding reached paired solver'),phase='cross_card',configuration=p.MAIN_V9)


def test_resumed_cross_unit_cannot_change_its_gated_candidate_binding(tmp_path, monkeypatch):
    from skillopt.execskill import v222_runtime
    from skillopt.continual_eval.core import read_json
    import json
    parent, _, home = packages(); st = AuthoredStep(tmp_path, parent=parent)
    def cross(_st, attempt, *, unit, phase, parent, candidate):
        return gate.check(home='searchqa', parent=parent, candidate=candidate, slices=slices(),
            inspector=inspector, run_pairs=lambda b, old, new, items: paired(items, 3, 0),
            phase=phase, configuration=p.MAIN_V9)
    monkeypatch.setattr(v222_runtime, 'cross_gate', cross)
    phase.cross_cards(st, parent, home)
    path = st.root/'card-cross-officeqa'/'unit.json'
    unit = read_json(path)
    gate_record = unit['result']['gate']
    unit['result']['gate'] = p.record('v222-cross-gate', st.evidence,
        {**{k:v for k,v in gate_record.items() if k not in ('version','evidence',p.RECORD_HASH)},
         'proposed_sha256': '0'*64})
    unit = p.record('unit', st.evidence, {'result': unit['result']})
    path.write_text(json.dumps(unit))
    with pytest.raises(ValueError, match='exact pre-rebase packages'):
        phase.cross_cards(st, parent, home)
