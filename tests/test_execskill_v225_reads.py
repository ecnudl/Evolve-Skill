"""Authored fresh dispatch, exact consent, event scheduling, and remaining-unit budget."""
from copy import deepcopy
from types import SimpleNamespace
from threading import Event

import pytest
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json,write_json
from skillopt.execskill import cells,evaluation,package,profiles as p,v225_read as r,v222_cards
from tests.execskill_fakes_env import FakeSandbox
from tests.test_execskill_evaluation import ITEMS,Solver
from skillopt.validator_pilot.api import digest

def panel(pinned, bench, *, access):
    assert bench == 'officeqa' and '/test/' in access.unit
    return deepcopy(ITEMS), {'panel_hash':digest(ITEMS),'excluded_without_pages':[],'source_files':[]}
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

EVIDENCE='engineering_fixture'


def consent():
    return {'test_evaluation':True,'sheet_test_qualification':True,'multi_arm_arms':list(r.ARMS),
            'by':'owner','date':'2026-11-04','note':'Authored main-v9 consent fixture.'}


@pytest.mark.parametrize('change',[{}, {'multi_arm_arms':list(reversed(r.ARMS))},
    {'multi_arm_arms':['B','C0','C','F','stages']},{'multi_arm_arms':list(r.ARMS[:-1])},
    {'test_evaluation':False},{'sheet_test_qualification':False},{'date':''},{'note':''},{'by':'writer'},{'extra':1}])
def test_exact_ten_arm_consent_fails_closed(tmp_path,change):
    write_json(tmp_path/'consent.json',{**consent(),**change})
    if change:
        with pytest.raises(ValueError): evaluation.consent(tmp_path,p.MAIN_V9)
    else:
        assert evaluation.consent(tmp_path,p.MAIN_V9)==consent()
        with pytest.raises(ValueError): evaluation.consent(tmp_path,p.MAIN_V8)


def test_read_layout_has_forty_units_fifty_arms_and_each_stage_on_all_panels():
    rows=r.plan_events()
    assert len(rows)==40 and sum(len(row['arms']) for row in rows)==50
    assert all(sum(row['label']=='s'+str(k) for row in rows)==5 for k in range(1,6))
    assert r.labels('anchor')==('B','C0','C') and r.labels('c_end')==('C_end',)
    setting=SimpleNamespace(root='/authored')
    assert str(r.unit_root(setting,'G','s2','officeqa'))=='/authored/G/test/s2/officeqa'


@pytest.mark.parametrize('event',['anchor','s1','s2','s3','s4','s5','i','c_end'])
def test_fresh_authored_read_dispatches_all_cells_even_unchanged_package(tmp_path,event):
    root=tmp_path/'run'
    blank=package.empty(step='D/s0',evidence=EVIDENCE)
    fake=Solver()
    endpoint=Endpoint(fake,model=p.CHAINS['D'],max_tokens=100,slots=Slots(root/'slots','deepseek',2),sleep=lambda _:None)
    unit=root/'D/test'/event/'officeqa'
    context=cells.Context(attempt=unit/'attempt-1',endpoint=endpoint,runtime=RUNTIME,
        cards={'officeqa':v222_cards.format_text('officeqa')},native=None,episodes=None,
        worker=lambda _:FakeSandbox(),evidence=EVIDENCE,configuration=p.MAIN_V9)
    write_json(root/'shared/consent.json',consent())
    result=r.evaluate_unit(unit,event=event,run='authored',shared=root/'shared',pinned=None,
        chain='D',bench='officeqa',chosen=r.arms(blank,event,chain='D',evidence=EVIDENCE),
        context=context,workers=2,canaries=[],panel=panel)
    rows=[read_json(path) for path in (unit/'attempt-1/cells').glob('*.json')]
    assert len(rows)==len(r.labels(event))*len(ITEMS)*p.TEST_RUNS
    assert fake.calls==len(rows)
    assert all(row['shared_with'] is None for row in rows)
    assert result['request_reuse']['shared_cells']==0 and result['structural_zero']==0
    assert not (unit/'attempt-1/transient').exists()


def test_production_dispatch_is_fresh_for_identical_arms_and_unchanged_stages(tmp_path,monkeypatch):
    root=tmp_path/'run'
    blank=package.empty(step='D/s0',evidence=EVIDENCE)
    fake=Solver()
    endpoint=Endpoint(fake,model=p.CHAINS['D'],max_tokens=100,
        slots=Slots(root/'slots','deepseek',2),sleep=lambda _:None)
    write_json(root/'shared/consent.json',consent())
    # Force identical authored requests across the anchor labels as well as the
    # unchanged stage packages. The production cell runner remains real.
    monkeypatch.setattr(r,'context_for',lambda context,bench,label:context)
    identities={}
    count=0
    for event in r.EVENTS:
        unit=root/'D/test'/event/'officeqa'
        context=cells.Context(attempt=unit/'attempt-1',endpoint=endpoint,runtime=RUNTIME,
            cards={'officeqa':v222_cards.format_text('officeqa')},native=None,episodes=None,
            worker=lambda _:FakeSandbox(),evidence=EVIDENCE,configuration=p.MAIN_V9)
        chosen={label:cells.Arm('candidate',blank) for label in r.labels(event)}
        result=r.evaluate_unit(unit,event=event,run='authored',shared=root/'shared',pinned=None,
            chain='D',bench='officeqa',chosen=chosen,context=context,workers=2,canaries=[],panel=panel)
        rows=[read_json(path) for path in (unit/'attempt-1/cells').glob('*.json')]
        expected=len(chosen)*len(ITEMS)*p.TEST_RUNS
        count+=expected
        assert len(rows)==expected and fake.calls==count
        assert result['request_reuse']=={'shared_cells':0,'dispatched_cells':expected}
        for row in rows:
            assert row['shared_with'] is None
            key=(row['cell']['task_id'],row['cell']['run'])
            identities.setdefault(key,set()).add(tuple(call['request_sha256'] for call in row['calls']))
    assert count==len(r.ARMS)*len(ITEMS)*p.TEST_RUNS
    assert identities and all(len(signatures)==1 for signatures in identities.values())


def test_remaining_unit_budget_exact_measured_terms_and_retry(tmp_path):
    measurements={b:{'card':11,'procedure':17} for b in p.MAIN_V5_ORDER}
    terms=r.estimate_unit_terms(measurements,1)
    assert len(terms)==40
    assert sum(terms.values())==sum(p.MAIN_V5_TEST_ITEMS.values())*(4*11+6*17)
    setting=SimpleNamespace(root=tmp_path,run='authored',evidence=EVIDENCE,
        extra={'test_read_terms':{'D':{k:str(v) for k,v in terms.items()}},
               'test_read_estimate':{'D':int(sum(terms.values()))}},
        budget=SimpleNamespace(snapshot=lambda:{'D:solver':{'cap':10**9,'settled':0,'open':0},
                                               'D:test':{'cap':10**9,'settled':0,'open':0}}))
    before=r.read_budget(setting,'D')
    assert len(before['units'])==40
    write_json(r.status_path(setting,'D','anchor','officeqa'),p.record('read-status',EVIDENCE,{
        'run':'authored','chain':'D','label':'anchor','bench':'officeqa','status':'complete'}))
    after=r.read_budget(setting,'D')
    assert len(after['units'])==39 and after['part']==before['part']-terms['anchor/officeqa']
    setting.budget=SimpleNamespace(snapshot=lambda:{scope:{'cap':0,'settled':0,'open':0} for scope in ('D:solver','D:test')})
    with pytest.raises(cells.Pause,match='estimate'): r.read_budget(setting,'D')


def test_stage_read_overlaps_next_step_and_unchanged_steps_all_read(tmp_path,monkeypatch):
    from skillopt.execskill import chain,budgets,v222_runtime,v221_recovery
    setting=SimpleNamespace(root=tmp_path,shared=tmp_path/'shared',run='authored',evidence=EVIDENCE,
                            extra={'configuration':p.MAIN_V9})
    monkeypatch.setattr(budgets,'own_ledger',lambda *a:SimpleNamespace(declare=lambda *a:None))
    monkeypatch.setattr(chain,'first_call',lambda *a,**k:None)
    monkeypatch.setattr(chain,'read_consent',lambda *a:None)
    monkeypatch.setattr(v222_runtime,'preflight',lambda *a:None)
    monkeypatch.setattr(v221_recovery,'records',lambda *a:[])
    monkeypatch.setattr(r,'read_budget',lambda *a:{'need':1})
    first_read=Event()
    next_learning=Event()
    events=[]
    def event(setting,ch,found,*,label,launch):
        events.append(label)
        if label=='s1':
            first_read.set()
            assert next_learning.wait(5), 'step 2 must learn while step 1 read remains in flight'
    monkeypatch.setattr(r,'evaluate_event',event)
    def learn(setting,root,ch,k,bench,parent):
        if k==2:
            assert first_read.wait(5)
            next_learning.set()
        # Every step rejects: still five real stage events.
        return parent,{p.RECORD_HASH:str(k)*64}
    result=r.run(setting,'D',learn=learn,launch=lambda *a:None)
    assert result=={'status':'complete'}
    assert set(events)==set(r.EVENTS) and len(events)==8
    assert events[0]=='anchor' and events[-2:]==['i','c_end']


def test_learning_pause_does_not_cancel_launched_reads(tmp_path,monkeypatch):
    from skillopt.execskill import chain,budgets,v222_runtime,v221_recovery
    setting=SimpleNamespace(root=tmp_path,shared=tmp_path/'shared',run='authored',evidence=EVIDENCE,
                            extra={'configuration':p.MAIN_V9})
    monkeypatch.setattr(budgets,'own_ledger',lambda *a:SimpleNamespace(declare=lambda *a:None))
    monkeypatch.setattr(chain,'first_call',lambda *a,**k:None)
    monkeypatch.setattr(chain,'read_consent',lambda *a:None)
    monkeypatch.setattr(v222_runtime,'preflight',lambda *a:None)
    monkeypatch.setattr(v221_recovery,'records',lambda *a:[])
    monkeypatch.setattr(r,'read_budget',lambda *a:{'need':1})
    launched,paused,completed=Event(),Event(),Event()
    def event(setting,ch,found,*,label,launch):
        if label=='s1':
            launched.set()
            assert paused.wait(5)
            completed.set()
    monkeypatch.setattr(r,'evaluate_event',event)
    def learn(setting,root,ch,k,bench,parent):
        if k==2:
            assert launched.wait(5)
            paused.set()
            raise cells.Pause('authored_pause','practice only','D/s2-officeqa')
        return parent,{p.RECORD_HASH:str(k)*64}
    result=r.run(setting,'D',learn=learn,launch=lambda *a:None)
    assert result['status']=='paused' and completed.is_set()


def test_stage_status_receipt_never_opens_read_cells(tmp_path,monkeypatch):
    from pathlib import Path
    setting=SimpleNamespace(root=tmp_path,run='authored',evidence=EVIDENCE)
    blank=package.empty(step='G/s0',evidence=EVIDENCE)
    seen=[]
    def launch(setting,spec):
        seen.append(spec)
        write_json(r.status_path(setting,'G',spec['label'],spec['bench']),p.record('read-status',EVIDENCE,{
            'run':'authored','chain':'G','label':spec['label'],'bench':spec['bench'],
            'status':'complete','package_sha256':blank.sha256}))
        return 0
    original=Path.open
    def trap(path,*args,**kwargs):
        if 'test' in path.parts:
            pytest.fail('parent opened child read data: '+str(path))
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',trap)
    r.evaluate_event(setting,'G',blank,label='s1',launch=launch)
    assert len(seen)==5
    r.evaluate_event(setting,'G',blank,label='s1',launch=launch)
    assert len(seen)==5


def test_read_plan_never_shares_identical_requests(tmp_path):
    from skillopt.execskill import v218_read
    blank=package.empty(step='G/s0',evidence=EVIDENCE)
    context=SimpleNamespace(configuration=p.MAIN_V9,runtime=RUNTIME,cards={'officeqa':v222_cards.format_text('officeqa')})
    chosen={'S1':cells.Arm('candidate',blank),'S2':cells.Arm('candidate',blank)}
    planned=v218_read.plan({'tasks':ITEMS},chosen,{},bench='officeqa',context=context,
        workers=lambda *a,**k:pytest.fail('empty package never starts a worker'))
    assert planned['identities']['S1']==planned['identities']['S2']
    assert all(source is None for rows in planned['sources'].values() for source in rows.values())
    assert len(planned['sources']['S1'])==len(ITEMS)


def test_failed_read_and_relaunch_parent_open_only_mirrored_status(tmp_path,monkeypatch):
    from pathlib import Path
    setting=SimpleNamespace(root=tmp_path,run='authored',evidence=EVIDENCE)
    blank=package.empty(step='G/s0',evidence=EVIDENCE)
    fail=True
    def launch(setting,spec):
        path=r.status_path(setting,'G',spec['label'],spec['bench'])
        fields={'run':'authored','chain':'G','label':spec['label'],'bench':spec['bench'],
                'package_sha256':blank.sha256}
        if fail:
            path=path.with_name(path.stem+'-paused-1.json')
            fields.update(status='paused',kind='authored_fault',reason='authored pause')
        else:
            fields.update(status='complete')
        write_json(path,p.record('read-status',EVIDENCE,fields))
        return 3 if fail else 0
    original=Path.open
    def trap(path,*args,**kwargs):
        assert 'test' not in path.parts, 'parent opened paused child state'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',trap)
    with pytest.raises(cells.Pause,match='authored pause'):
        r.evaluate_event(setting,'G',blank,label='s1',launch=launch)
    fail=False
    r.evaluate_event(setting,'G',blank,label='s1',launch=launch)
    assert all(r.status(setting,'G','s1',bench)['status']=='complete' for bench in p.MAIN_V5_ORDER)


@pytest.mark.parametrize('event',['s1','s2','s3','s4','s5','i','c_end'])
def test_child_package_matches_exact_completed_step_before_panel_open(tmp_path,event):
    setting=SimpleNamespace(root=tmp_path,evidence=EVIDENCE)
    k=int(event[1:]) if event.startswith('s') else 5
    bench=p.MAIN_V5_ORDER[k-1]
    blank=package.empty(step='G/s0',evidence=EVIDENCE)
    write_json(tmp_path/'G'/('s%d-%s'%(k,bench))/'step.json',p.record('step',EVIDENCE,{
        'chain':'G','k':k,'bench':bench,'package_sha256':blank.sha256}))
    r.bind_event_package(setting,'G',event,blank)
    wrong=package.empty(step='G/other',evidence=EVIDENCE)
    with pytest.raises(ValueError,match='immutable completed step'):
        r.bind_event_package(setting,'G',event,wrong)
