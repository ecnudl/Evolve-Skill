"""Authored supply allocation and one-decision confirmation lifecycle."""
from types import SimpleNamespace

import pytest

from skillopt.execskill import profiles as p, step, supply, v211_allocation as a
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v29_confirm import fake_eval


def allocate(*args, **kwargs):
    kwargs.setdefault('excluded', ['authored-protected-test-id'])
    return a.allocate(*args, **kwargs)


def pool(bench):
    count = {'searchqa': 600, 'officeqa': 74, 'livemath': 283, 'spreadsheetbench': 91}[bench]
    return [{'benchmark': bench, 'task_id': '%s-%04d' % (bench, i), 'part': 'train',
             'public': {'question': 'Authored %d?' % i, 'context': ['Synthetic evidence'],
                        'choices': 'A. 1\n\nB. 2\n\nC. 3\n\nD. 4\n\nE. ' + (p.LIVEMATH_META_OPTION if i >= 154 else '5')},
             'private': {'answer': '1'}} for i in range(count)]


def tail(n=1240):
    items = [{'benchmark': 'searchqa', 'task_id': 'tail-%04d' % i, 'part': 'tail',
              'public': {'question': 'Tail %d?' % i, 'context': 'Synthetic'}, 'private': {'answer': '1'}}
             for i in range(n)]
    return {'tail': items, 'kept': p.record('searchqa-kept', 'engineering_fixture', {'items': items})}


@pytest.mark.parametrize('bench,run,accept,confirm', [('searchqa',300,1000,40),
    ('officeqa',18,32,4), ('livemath',95,100,4), ('spreadsheetbench',31,36,4)])
def test_registered_cuts_and_all_rounds_are_disjoint(bench, run, accept, confirm):
    kwargs = tail() if bench == 'searchqa' else {}
    cuts, pin = allocate(bench, pool(bench), **kwargs)
    assert len(cuts['run']) == run and len(cuts['accept']) == accept
    assert [len(cuts['confirm-r%d' % r]) for r in range(1,7)] == [confirm]*6
    ids = [i['task_id'] for rows in cuts.values() for i in rows]
    assert len(ids) == len(set(ids))
    assert pin['provenance'] == a.PROVENANCE
    assert pin['selection_check'] == 'preregistered'
    assert not pin['cross_round_incumbent_cache'] and not pin['recycle_unused']
    if bench == 'livemath':
        assert sum(supply.meta_present(i) for i in cuts['run']) == 65
        assert len(cuts['accept_probe']) == 64
        assert not any(supply.meta_present(i) for name, rows in cuts.items() if name.startswith('confirm') or name == 'accept' for i in rows)
    if bench == 'officeqa':
        st = SimpleNamespace(bench=bench,setting=SimpleNamespace(extra={'configuration':p.MAIN_V4}))
        blocks = step._blocks(st,cuts['accept'])
        assert list(blocks.values()).count('b1') == list(blocks.values()).count('b2') == 16


def test_searchqa_insufficient_or_unexcluded_tail_is_refused():
    with pytest.raises(ValueError, match='1,240'):
        allocate('searchqa',pool('searchqa'),**tail(1239))
    rows = tail()
    with pytest.raises(ValueError, match='persisted test exclusion'):
        allocate('searchqa',pool('searchqa'),tail=rows['tail'])
    rows['kept'] = p.record('searchqa-kept','engineering_fixture',{'items':rows['tail'][:-1]})
    with pytest.raises(ValueError, match='outside the kept'):
        allocate('searchqa',pool('searchqa'),**rows)


@pytest.mark.parametrize('bench',a.LEARNED)
def test_protected_overlap_and_sealed_inputs_refused_without_recut(bench):
    kwargs = tail() if bench == 'searchqa' else {}
    cuts,_ = allocate(bench,pool(bench),**kwargs)
    with pytest.raises(ValueError,match='overlaps protected'):
        allocate(bench,pool(bench),excluded=[cuts['confirm-r6'][0]['task_id']],**kwargs)
    rows=pool(bench); rows[0]['partition']='test'
    with pytest.raises(ValueError,match='training-side'):
        allocate(bench,rows,**kwargs)


def child_step(monkeypatch,tmp_path):
    st,calls=fake_eval(monkeypatch,tmp_path)
    st.bench='officeqa';st.setting.extra={'configuration':p.MAIN_V4}
    st.root=tmp_path;st.setting.root=tmp_path;st.namespace='D-v4'
    from skillopt.execskill.registry import Registry
    st.services=SimpleNamespace(registry=Registry(tmp_path/'history',evidence='engineering_fixture',run_root=tmp_path))
    def unit(name,work,**kwargs):
        attempt=tmp_path/name/'attempt-1'
        attempt.mkdir(parents=True,exist_ok=True)
        if name not in st.finished: st.finished[name]=work(attempt)
        result=st.finished[name]
        if kwargs.get('settle'): kwargs['settle'](attempt,result)
        return result
    st.unit=unit
    return st,calls


def test_round_specific_confirm_has_no_cross_round_cache_and_same_round_resume(monkeypatch,tmp_path):
    st,calls=child_step(monkeypatch,tmp_path)
    cut,_=allocate('officeqa',pool('officeqa'))
    parent=SimpleNamespace(sha256='parent');candidate=SimpleNamespace(sha256='one')
    one=step._confirm_eval(st,cut,1,parent,candidate)
    again=step._confirm_eval(st,cut,1,parent,candidate)
    two=step._confirm_eval(st,cut,2,parent,SimpleNamespace(sha256='two'))
    assert one==again and [len(c) for c in calls]==[8,8]
    assert two['confirm']['reused_cells']==0
    assert one['selection_check']=='preregistered'
    assert set(one['slice_ids']).isdisjoint(two['slice_ids'])
    with pytest.raises(ValueError,match='same sealed'):
        step._confirm_eval(st,cut,1,parent,SimpleNamespace(sha256='different'))
    bad={**cut,'confirm-r3':cut['confirm-r1']}
    with pytest.raises(ValueError,match='disjoint'):
        step._confirm_eval(st,bad,3,parent,candidate)
    state=st.services.registry.entries('D-v4','officeqa')
    assert len(state)==8 and all(row['state']=='decided' for row in state.values())


def test_infrastructure_failure_preserves_consumption_and_resumable_binding(monkeypatch,tmp_path):
    st,calls=child_step(monkeypatch,tmp_path)
    cut,_=allocate('officeqa',pool('officeqa'))
    original=step._cells
    def fail(*args,**kwargs): raise RuntimeError('authored transport failure')
    monkeypatch.setattr(step,'_cells',fail)
    with pytest.raises(RuntimeError,match='transport'):
        step._confirm_eval(st,cut,1,SimpleNamespace(sha256='parent'),SimpleNamespace(sha256='one'))
    assert {row['state'] for row in st.services.registry.entries('D-v4','officeqa').values()}=={'dispatched'}
    monkeypatch.setattr(step,'_cells',original)
    # The real unit manager resumes its persisted attempt. This small fixture merely permits reentry.
    import shutil
    shutil.rmtree(tmp_path/'confirm-r1')
    result=step._confirm_eval(st,cut,1,SimpleNamespace(sha256='parent'),SimpleNamespace(sha256='one'))
    assert result['confirm']['passed']
