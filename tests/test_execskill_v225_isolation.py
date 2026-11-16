"""Protected read roots can never be opened through a learning reader."""
from pathlib import Path
import pytest
from skillopt.execskill import v225_read as r
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


@pytest.mark.parametrize('part',['test','holdout','held_out','final','sealed','reserve','TestAccess','test_panel','block_c','block_d'])
def test_learner_refuses_every_protected_path_component_before_open(tmp_path,part):
    path=tmp_path/'G'/part/'s1'/'officeqa'/'cells.json'
    with pytest.raises(ValueError,match='learner cannot open'):
        r.assert_learning_path(path)


def test_authored_next_step_does_not_open_prior_read(tmp_path,monkeypatch):
    prior=tmp_path/'G'/'test'/'s1'/'officeqa'/'scores.json'
    # The directory can exist; none of its bytes is needed by step k+1.
    prior.parent.mkdir(parents=True)
    prior.write_text('AUTHORED SECRET SCORE')
    opened=[]
    original=Path.open
    def trap(path,*args,**kwargs):
        if 'test' in path.parts:
            opened.append(path)
            raise AssertionError('learner opened read directory')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',trap)
    with pytest.raises(ValueError):
        r.assert_learning_path(prior).read_text()
    safe=tmp_path/'G'/'s2-officeqa'/'rounds.json'
    assert r.assert_learning_path(safe)==safe
    assert opened==[]


def test_authored_next_step_current_and_run_readers_never_open_prior_read(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from skillopt.continual_eval.core import write_json
    from skillopt.execskill import profiles as p,step,units,trajectories
    chain_root=tmp_path/'G'
    prior=chain_root/'test'/'s1'/'officeqa'/'scores.json'
    prior.parent.mkdir(parents=True)
    prior.write_text('AUTHORED PRIOR READ RESULT')
    st=SimpleNamespace(chain_root=chain_root,k=2,bench='officeqa',
        setting=SimpleNamespace(extra={'configuration':p.MAIN_V9}),
        card_phase_record={'accepted_training_unit':'card-train-c1'})
    for name,arm,kind in [('run','S','parent'),('card-train-c1',"S'",'candidate')]:
        base=units.unit_path(chain_root,2,'officeqa',name)
        write_json(base/'unit.json',p.record('unit','engineering_fixture',{
            'status':'complete','attempt':'attempt-1'}))
        trajectories.write(base/'attempt-1',name,p.record('trajectory','engineering_fixture',{
            'cell':name,'arm':arm,'arm_kind':kind,'task_id':'authored-item','run':0}))
    opened=[]
    original=Path.open
    def trap(path,*args,**kwargs):
        assert 'test' not in path.parts, 'learner opened a prior read'
        opened.append(path)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',trap)
    assert step._run_trajectories(st,parent_only=True)[0]['arm_kind']=='parent'
    assert step._current(st,[])[0]['cell']=='card-train-c1'
    assert opened and all('test' not in path.parts for path in opened)


@pytest.mark.parametrize('name',['selftest','selftest-1','selftest-2','audit-final','sandbox-selftest'])
def test_registered_learner_unit_names_are_allowed_without_allowing_test_subtree(tmp_path,name):
    assert r.assert_learning_path(tmp_path/'G'/'s2-officeqa'/name).name==name
    with pytest.raises(ValueError): r.assert_learning_path(tmp_path/'G'/'test'/'s1'/name)


def test_real_selftest_trajectory_reader_is_not_mistaken_for_test_data(tmp_path):
    from types import SimpleNamespace
    from skillopt.continual_eval.core import write_json
    from skillopt.execskill import profiles as p,step,units,trajectories
    st=SimpleNamespace(chain_root=tmp_path/'G',k=2,bench='officeqa',
        setting=SimpleNamespace(extra={'configuration':p.MAIN_V9}))
    base=units.unit_path(st.chain_root,st.k,st.bench,'selftest')
    write_json(base/'unit.json',p.record('unit','engineering_fixture',{'status':'complete','attempt':'attempt-1'}))
    trajectories.write(base/'attempt-1','authored',p.record('trajectory','engineering_fixture',{
        'cell':'authored','arm':"S'",'arm_kind':'candidate','task_id':'authored-item','run':0}))
    assert step._unit_trajectories(st,'selftest')[0]['cell']=='authored'


def test_root_scan_distinguishes_each_read_event_and_practice_leaks(tmp_path):
    from skillopt.execskill import evaluation as e,profiles as p
    text='An authored canary phrase is long enough for an isolated source scan.'
    inside=tmp_path/'G/test/s1/officeqa/content.json'
    outside=tmp_path/'G/s2-officeqa/train-r1/content.json'
    for path in (inside,outside):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)
    _,hits=e.root_scan(tmp_path,[e.canary(text)],configuration=p.MAIN_V9)
    assert {row['where'] for row in hits}=={'G/test/s1/officeqa','G/s2-officeqa'}


def test_orphaned_stage_read_blocks_owner_termination_and_unseal(tmp_path):
    from skillopt.coevo5.cells import exclusive
    from skillopt.execskill import chain,evaluation,profiles as p
    root=tmp_path/'run'
    chain_root=root/'G'
    manifest={'root':str(root),p.RECORD_HASH:'authored-run','evidence':'engineering_fixture',
              'configuration':p.MAIN_V9}
    child=chain_root/'test/s3/officeqa'
    # The parent runner is absent, but a launched read still owns its nested unit.
    with exclusive(child/'.lock'):
        with pytest.raises(ValueError,match='Test-read units are still running'):
            chain.terminate_manifest(manifest,chain='G',decision='Stop after the learning pause')
        assert not (chain_root/'chain-terminated.json').exists()
        with pytest.raises(ValueError,match='Test-read units are still running'):
            evaluation.unseal(root,chain_root,'G',[child],run='authored-run',
                evidence='engineering_fixture',configuration=p.MAIN_V9)
    assert chain.terminate_manifest(manifest,chain='G',decision='Read child has now exited')['status']=='terminated'


@pytest.mark.parametrize('active_chain',['G','D'])
def test_unseal_independently_refuses_active_read_even_with_terminal_markers(tmp_path,monkeypatch,active_chain):
    from skillopt.coevo5.cells import exclusive
    from skillopt.continual_eval.core import write_json
    from skillopt.execskill import evaluation,profiles as p
    root=tmp_path/'run'
    for name in ('G','D'):
        write_json(root/name/'chain-terminated.json',p.record('chain-terminated','engineering_fixture',{
            'identity':{'run':'authored','chain':name},'by':'protocol','decision':'authored stale marker'}))
    monkeypatch.setattr(evaluation,'continuation',lambda *a:pytest.fail('must refuse before continuation or score access'))
    with exclusive(root/active_chain/'test/s2/officeqa/.lock'):
        with pytest.raises(ValueError,match='Test-read units are still running'):
            evaluation.unseal(root,root/'G','G',[],run='authored',evidence='engineering_fixture',
                              configuration=p.MAIN_V9)


def test_protocol_termination_waits_for_overlapping_reads_before_terminal_marker(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from skillopt.coevo5.cells import exclusive
    from skillopt.continual_eval.core import read_json
    from skillopt.execskill import chain,budgets,evaluation,profiles as p,v222_runtime,v221_recovery
    launched,release,mismatch,completed=Event(),Event(),Event(),Event()
    drift=False
    def verify():
        if drift:
            raise ValueError('authored manifest drift during the second learning step')
    setting=SimpleNamespace(root=tmp_path,shared=tmp_path/'shared',run='authored',evidence='engineering_fixture',
        extra={'configuration':p.MAIN_V9,'verify':verify})
    monkeypatch.setattr(budgets,'own_ledger',lambda *a:SimpleNamespace(declare=lambda *a:None))
    monkeypatch.setattr(chain,'first_call',lambda *a,**k:None)
    monkeypatch.setattr(chain,'read_consent',lambda *a:None)
    monkeypatch.setattr(v222_runtime,'preflight',lambda *a:None)
    monkeypatch.setattr(v221_recovery,'records',lambda *a:[])
    monkeypatch.setattr(r,'read_budget',lambda *a:{'need':1})
    def event(setting,ch,found,*,label,launch):
        if label=='s1':
            with exclusive(tmp_path/'D/test/s1/officeqa/.lock'):
                launched.set()
                assert release.wait(5), 'authored read was not released'
            completed.set()
    monkeypatch.setattr(r,'evaluate_event',event)
    def learn(setting,root,ch,k,bench,parent):
        nonlocal drift
        if k==2:
            assert launched.wait(5)
            drift=True
            try:
                chain.check_pins(setting,ch)  # real protocol-triggered termination path
            finally:
                mismatch.set()
        return parent,{p.RECORD_HASH:str(k)*64}
    with ThreadPoolExecutor(max_workers=1) as executor:
        future=executor.submit(r.run,setting,'D',learn=learn,launch=lambda *a:None)
        try:
            assert mismatch.wait(5)
            assert (tmp_path/'D/chain-termination-pending.json').exists()
            assert not (tmp_path/'D/chain-terminated.json').exists()
            assert not future.done()
            with pytest.raises(ValueError,match='Test-read units are still running'):
                evaluation.unseal(tmp_path,tmp_path/'D','D',[],run='authored',
                    evidence='engineering_fixture',configuration=p.MAIN_V9)
        finally:
            release.set()
        assert future.result(timeout=5)=={'status':'terminated','reason':'manifest_mismatch'}
    assert completed.is_set()
    terminal=p.verified(read_json(tmp_path/'D/chain-terminated.json'),'chain-terminated')
    assert terminal['by']=='protocol' and terminal['read_units_joined'] is True
    assert terminal['decision'].startswith('manifest_mismatch: authored manifest drift')
