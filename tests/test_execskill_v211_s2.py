"""Successful five-bench S2 through production cells, with only authored providers/native outcomes."""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json
from skillopt.execskill import (fixtures, profiles as p, rounds, supply, units, v211_fixtures,
    v211_smoke, v211_smoke_controls, v211_stages)
from skillopt.execskill.sandbox import worker as sandbox_worker
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import FakeSolver, tagged
from tests.execskill_fakes_env import FakeAlfEnv, FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_rehearsal import build, offline  # noqa: F401


class AuthoredWorker(FakeSandbox):
    """Execute only the frozen fixture/import source; read the actual authored public workbook."""
    def start(self, package, *, kind, inputs_dir=None):
        def public_workbook():
            with patch.object(sandbox_worker,'INPUT_WORKBOOK',str(Path(inputs_dir)/'input.xlsx')):
                return sandbox_worker.public_workbook()
        for procedure in package.procedures:
            namespace={'public_workbook':public_workbook,'print':lambda *args,**kwargs:None}
            exec(compile(procedure.source,'<authored-s2-fixture>','exec'),namespace)
            self.hooks[procedure.id]={hook:namespace[hook] for hook in procedure.hooks}
        self.rejected={}
        return super().start(package,kind=kind,inputs_dir=inputs_dir)


def test_s2_all_five_production_adapters_and_separate_zero_call_controls(tmp_path,monkeypatch):
    setting,_,fakes=build(tmp_path,monkeypatch)
    root=tmp_path/'authored-fixtures'
    v211_fixtures.make(root)
    pools={bench:fixtures.load_items(root,bench) for bench in fixtures.BENCHES}
    pools['searchqa']=setting.pools['searchqa'][:20]
    games={}
    pools['alfworld']=[]
    for n in range(6):
        name='authored-game-%d'%n
        initial='You are in an authored room.\nYour task is to: look around.'
        view=supply.routing_view(initial,['look'])
        games[name]={'initial_observation':initial,'admissible_commands':['look'],'plan':['look'],
            'expert_plan':['look'],'gamefile':name,'terminal_observation':'The authored task is complete.'}
        pools['alfworld'].append({'benchmark':'alfworld','task_id':name,'part':'authored',
            'public':{'game_file':name,'routing_view':view,'routing_view_sha256':digest(view)},'private':{}})
    sessions=[]
    def environment(public,runtime):
        sessions.append(FakeAlfEnv(games[public['game_file']]))
        return sessions[-1]
    monkeypatch.setattr(backends,'_new_alfworld',environment)
    original_context=units.cell_context
    def context(st,attempt,endpoint,**kwargs):
        made=original_context(st,attempt,endpoint,**kwargs)
        made.worker=lambda bench:AuthoredWorker()
        return made
    monkeypatch.setattr(units,'cell_context',context)
    monkeypatch.setattr(rounds,'cell_context',context)
    def answer(system,user):
        view=json.loads(user)
        if 'initial_observation' in view:
            return 'look'
        if 'required_answer_position' in view:
            return '```python\n# AUTHOR_%s\nx=17\n```'%('PASS' if 'previous_program' in view else 'FAIL')
        if 'computed' in view:
            return tagged('17')
        if 'bindings' in view.get(p.NOTES_KEY,'').lower():
            return '<calc>1+1</calc>'
        return tagged('A' if 'choices' in view else '17')
    provider=FakeSolver(tmp_path/'s2-provider',[(None,answer)],model=p.CHAINS['G'])
    old_clients=setting.clients
    setting=replace(setting,pools=pools,clients=lambda model,bench:
        provider.client if bench is not None else old_clients(model,bench))
    monkeypatch.setattr(v211_stages,'fixture_pools',lambda st:pools)
    local=v211_smoke._stage_setting(setting,'S2')
    controls=v211_smoke_controls.controls(root)
    assert controls['passed'] and controls['model_calls']==controls['external_calls']==0
    assert not provider.requests
    result=v211_stages.s2(local)
    assert result['passed'] and set(result['benches'])==set(p.BENCHES)
    assert sum(row['cells'] for row in result['benches'].values())==172
    for bench,row in result['benches'].items():
        expected=6 if bench=='alfworld' else 20
        assert row['items']==expected and row['cells']==2*expected and row['first_response_confirmed']
        assert row['sealed_reads']==0 and row['settled_tokens']>0
        assert row['measurements']['per_arm'][bench]['C']['cells']==expected
        assert row['measurements']['per_arm'][bench]['X']['cells']==expected
        assert row['measurements']['actual']>0 and row['measurements']['request_bytes'][bench]>0
    assert len(sessions)==12 and all(env.closed for env in sessions)
    ledger=local.budget.snapshot()
    assert all(row['open']==0 and row['settled']<=row['cap'] for row in ledger.values())
    assert not fakes['D'].requests and not fakes['roles'].seen
    assert controls['bindings_calculator']['shell']['compute'] is not None
    assert controls['requested_repair']['shell']['deciding_receipt']==1
    assert controls['repair_fallback']['shell']['deciding_receipt']==0
    assert controls['repair_fallback']['shell']['fallback']=='second_call_fallback'
    cells=[p.verified(read_json(path),'cell') for path in local.root.rglob('cells/*.json')]
    assert len(cells)==172 and all(cell['final'] is not None and cell['stop'] is None for cell in cells)
    counts=len(provider.requests)
    assert v211_stages.s2(local)==result and len(provider.requests)==counts
