"""Zero-model-call final-audit engineering control over actual S3 public snapshots.

The measured snapshots are retained unchanged. A separately marked authored
clone and contradiction, local reviewer JSON and stale-source copies exercise
Audit2 plumbing; they are never evidence of a model judgment or Skill effect.
"""
from copy import deepcopy
from dataclasses import replace
import json
import re

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest
from skillopt.execskill import audit, profiles as p, step, v211_audit
from skillopt.execskill.package import FIXTURE, Package, withhold

CLONE_ID = 'fx-v211-audit2-control-clone'
CLONE_NOTE = 'AUTHORED AUDIT CONTROL: the public task text contains zero characters.'
CLONE_SOURCE = 'def before_call(view, state):\n    return {"facts": [%r]}\n' % CLONE_NOTE


class _AuthoredJudge:
    """A local response function, deliberately with no provider/client or billed sends."""
    def __init__(self):
        self.calls, self.requests = [], []

    def plain(self, role, system, user, *, label, max_tokens):
        self.requests.append({'system_sha256':v211_audit.sha(system),'user_sha256':v211_audit.sha(user)})
        templates = re.findall(r'^(T\d+):',user,re.M)
        if system.startswith('You audit helper programs'):
            return json.dumps({'templates':[{'t':t,'verdict':'ok','reason':'Authored control reply.'} for t in templates],
                              'other':[]})
        situations, owners = [], []
        for part in re.split(r'^Situation ',user,flags=re.M)[1:]:
            sid=part.split()[0]
            notes=[]
            for nid,pid in re.findall(r'^(N\d+) \[([^]]+)\]:',part,re.M):
                notes.append({'n':nid,'truth':'true','policy':'ok','reason':'Authored control reply.','evidence':''})
                owners.append((sid+'/'+nid,pid))
            situations.append({'s':sid,'notes':notes})
        clone=next((name for name,pid in owners if pid==CLONE_ID),None)
        original=next((name for name,pid in owners if pid!=CLONE_ID),None)
        return json.dumps({'situations':situations,'program':{'verdict':'ok','reason':'Authored control reply.'},
            'contradictions':[{'notes':[original,clone],'reason':'AUTHORED CONTROL: the two text-length claims conflict.'}]
                            if original and clone else []})


def audit2_control(st,candidate,rounds=(1,)):
    ledger_before=digest(st.setting.budget.snapshot())
    snapshots=[]
    for number in rounds:
        for kind in ('confirm','train'):
            name='%s-r%d'%(kind,number)
            if st.done(name):
                for trajectory in step._unit_trajectories(st,name):
                    if trajectory.get('arm')!="S'":
                        continue
                    observed=candidate if trajectory['package_sha256']==candidate.sha256 else step._package(st,trajectory['package_sha256'])
                    snapshots.append({**deepcopy(trajectory),'audit_source':kind,
                        'package_procedures':{proc.id:v211_audit.sha(proc.source) for proc in observed.procedures}})
    before=digest(snapshots)
    candidate_before=candidate.sha256
    original=audit.situations_from_cells(snapshots,candidate,configuration=p.MAIN_V4)
    require(original and {row['source'] for row in original}=={'train','confirm'},
            'The Audit2 control needs delivered train and confirm public situations')
    sources={proc.id:v211_audit.sha(proc.source) for proc in candidate.procedures}
    require(all(row['procedure_source_sha256']==sources[row['notes'][0]['procedure']] for row in original),
            'Every original control situation has its observed candidate source')
    stale_counts={}
    for kind in ('note_source','package_source'):
        stale=deepcopy(snapshots)
        for trace in stale:
            if kind=='note_source':
                for row in trace.get('shell',{}).get('notes',[]):
                    row['source_sha256']='authored-stale-source'
            else:
                trace['package_procedures']={pid:'authored-stale-source' for pid in sources}
        stale_counts[kind]=len(audit.situations_from_cells(stale,candidate,configuration=p.MAIN_V4))
    first=original[0]
    base=candidate.get(first['notes'][0]['procedure'])
    clone=replace(base,id=CLONE_ID,source=CLONE_SOURCE,hooks=('before_call',),
        description='AUTHORED Audit2 control contradiction; never adopted.',requests_second_call=False,
        replay_tests=(),evidence=FIXTURE)
    fixture_candidate=replace(candidate,evidence=FIXTURE)
    injected=Package(candidate.procedures+(clone,),candidate.step,FIXTURE,candidate.parent_sha256,
                     candidate.retired,candidate.narrowed,candidate.describer)
    extra=v211_audit._situation(bench=st.bench,item=first['item'],cell=first['cell']+'::authored-audit2-control',
        package=injected.sha256,source_hash=v211_audit.sha(clone.source),hook='before_call',
        request_hash=digest(['authored-audit2-control',first['request_sha256']]),raw_view=first['view'],
        text=CLONE_NOTE,procedure=CLONE_ID,source=first['source'])
    extra['authored_injection']=True
    judges={name:_AuthoredJudge() for name in ('G','D')}
    result=audit.run_audit(injected.procedures,original+[extra],judges,bench=st.bench,
        configuration=p.MAIN_V4,step=st.name+'/authored-audit2-control',change_id='final-control',
        final=True,context_procedures=injected.procedures)
    removed=audit.removed_procedures(result,list(injected.order))
    after=withhold(injected,removed) if removed else injected
    unchanged=digest(snapshots)==before
    ledger_unchanged=digest(st.setting.budget.snapshot())==ledger_before
    passed=(all(result['available'].values()) and removed==[CLONE_ID] and after.sha256==fixture_candidate.sha256
            and all(count==0 for count in stale_counts.values()) and unchanged and ledger_unchanged
            and candidate.sha256==candidate_before
            and any(row['kind']=='contradiction' for row in result['confirmed'])
            and all(row['charged']==0 for row in result['tokens'].values()))
    return {'passed':passed,'evidence':FIXTURE,'model_calls':0,'external_calls':0,'engineer_calls':0,
        'benchmark_effect_evidence':False,'decision_used_for_adoption':False,'excluded_from_cost_projection':True,
        'injections':['separate authored clone procedure and contradictory note derived from a copied public situation',
            'deterministic local reviewer JSON','stale note-source copies','stale package-source copies'],
        'ledger_unchanged':ledger_unchanged,'original_snapshot_sha256':before,'original_snapshots_unchanged':unchanged,'original_situations':original,
        'sources':sorted({row['source'] for row in original}),'phases':sorted({row['phase'] for row in original}),
        'stale_source_situations':stale_counts,'injected_situation':extra,'authored_clone':clone.to_json(),
        'control_audit':result,'removed':removed,'before_package_sha256':candidate.sha256,
        'injected_package_sha256':injected.sha256,'after_package_sha256':after.sha256,
        'expected_fixture_package_sha256':fixture_candidate.sha256,
        'candidate_identity_unchanged':candidate.sha256==candidate_before,
        'local_reviewer_requests':{name:judge.requests for name,judge in judges.items()}}
