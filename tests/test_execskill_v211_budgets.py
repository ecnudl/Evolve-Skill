"""Exact §7 arithmetic and complete benchmark-specific maximum projections."""
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace

import pytest
from skillopt.execskill import budgets, profiles as p, smoke, v211_limits as v, v29_route_probe as probe
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def test_all_registered_numbers_are_reproduced_from_reservations():
    assert (v.RE,v.RO,v.RJ)==(1077120,947584,914816)
    assert v.ENGINEER==445408128
    assert [v.role_caps(b)['audit_g'] for b in v.LEARNED]==[549804416]*3+[769360256]
    assert v.METHOD_CAP==7009579520 and v.SOLVER_CAP==1250000000
    caps=p.CONFIG_STEP_CAPS[p.MAIN_V4]
    assert [caps[b]['confirm'] for b in v.LEARNED]==[32900000,26800000,25900000,26000000]
    assert sum(sum(row.values()) for row in p.CONFIG_STEP_CAPS[p.MAIN_V3].values())==811600000
    assert sum(caps[b]['confirm'] for b in v.LEARNED)==111600000
    assert p.CONFIGURATIONS[p.MAIN_V4]['redo_reserve']==87000000
    assert p.CONFIGURATIONS[p.MAIN_V4]['test_read_cap']==238000000
    for b in v.LEARNED:
        for k in ('run','examiner','selftest','accept'):
            assert caps[b][k]==p.CONFIG_STEP_CAPS[p.MAIN_V3][b][k]
    ident=v.identity()
    assert ident['judge_calls_per_chain']==5280
    assert ident['confirm_total']==624
    assert sum(ident['acceptance_sp_s_c'].values())==4200
    assert sum(ident['independent_c'].values())==1400
    assert ident['test_logical_cells_both_chains']==6660


@pytest.mark.parametrize('chain',p.CHAINS)
def test_benchmark_scopes_and_no_import_learning_scopes(chain):
    caps=budgets.chain_caps(chain,p.MAIN_V4)
    assert caps['overall']==8259579520
    assert caps[chain+':glm']==v.METHOD_CAP and caps[chain+':solver']==v.SOLVER_CAP
    assert not any(':alfworld:' in name for name in caps)
    for k,b in enumerate(v.LEARNED,1):
        assert budgets.role_scope_caps(p.MAIN_V4,b)['audit_g']==v.role_caps(b)['audit_g']
        assert caps[budgets.audit_scopes(chain,'G',b,k)[-1]]==v.role_caps(b)['audit_g']
        assert smoke.max_role_calls(p.MAIN_V4,b)['leakage']==144
        assert smoke.max_role_calls(p.MAIN_V4,b)['audit_g']==(840 if b=='spreadsheetbench' else 600)
    assert set(smoke._scope_cells(chain,p.MAIN_V4))=={key for key in caps if key!='overall'
        and key!=chain+':glm' and ':role:' not in key}


def test_method_projection_requires_each_benchmark_and_auditor_and_uses_own_calls():
    measured={b:{role:{'calls':1,'per_call':1,'request_bytes':220000} for role in v.role_calls(b)} for b in v.LEARNED}
    result=smoke.glm_projection(measured,p.MAIN_V4)
    for chain in p.CHAINS:
        for k,b in enumerate(v.LEARNED,1):
            row=result[budgets.audit_scopes(chain,'D',b,k)[-1]]
            assert row['settled']==v.JUDGE_CALLS[b] and row['fits'] and row['assumed']==[]
        row=result[budgets.glm_scopes(chain,'engineer','officeqa',2)[-1]]
        assert row['settled']==432 and row['reservation']==1077120
    bad=deepcopy(measured);del bad['officeqa']['audit_d']
    with pytest.raises(ValueError,match='both auditors'):
        smoke.glm_projection(bad,p.MAIN_V4)
    with pytest.raises(ValueError,match='every learned'):
        smoke.glm_projection({'searchqa':measured['searchqa']},p.MAIN_V4)


def test_alf_only_format_capability_preserves_historical_default():
    from skillopt.execskill import alfworld_format as f
    runtime={'authored':'runtime'}
    bound=f.bind(runtime,p.MAIN_V4)
    assert f.validate(bound,p.MAIN_V4)
    assert f.environment_runtime(bound)==runtime
    assert p.alfworld_format_rule(p.MAIN_V4,'alfworld')==f.RULE
    assert p.alfworld_format_rule(p.MAIN_V4)=='alfworld-admissible-9-10'
    assert p.train_rounds(p.MAIN_V4,'alfworld')==0
    with pytest.raises(ValueError): f.validate(bound,p.MAIN_V3)


def test_route_probe_has_five_distinct_bench_bound_units_and_reuses_completed_units(tmp_path,monkeypatch):
    from skillopt.execskill import client
    from skillopt.validator_pilot.api import digest
    from skillopt.continual_eval.core import write_json
    seen,done=[],{}
    setting=SimpleNamespace(root=tmp_path,run='a'*64,extra={'configuration':p.MAIN_V4},evidence='engineering_fixture',
        branch='N',longest=512,clients=lambda model,bench:SimpleNamespace(route=client.ROUTE_B,max_tokens=p.solver_tokens(model,bench)))
    class Endpoint:
        def recorder(self,label): return SimpleNamespace(sends=[],label=label)
        def send(self,system,user,recorder):
            recorder.sends.append({'request_sha256':digest([system,user]),'charged':10})
            return {'ok':True,'response':'Authored actual reply','returned_model':client.NORTHGATE_MODEL,
                    'usage':{'completion_tokens':50},'reasoning_chars':0,'reasoning_tokens':0}
    monkeypatch.setattr(probe.budgets,'endpoint',lambda *a,**kw:Endpoint())
    def run(root,**kw):
        key=str(root)
        if key not in done:
            attempt=root/'attempt-1';attempt.mkdir(parents=True)
            seen.append(kw['identity']);done[key]={'result':kw['work'](attempt)}
        return done[key]
    monkeypatch.setattr(probe.units,'run_unit',run)
    value=probe.measure_all(setting)
    assert len(seen)==5 and set(value['benches'])==set(p.BENCHES)
    assert len({row['unit'] for row in seen})==5
    assert all(row['bench'] in p.BENCHES and row['request_ceiling']>=row['max_tokens'] for row in seen)
    assert all(row['calls']==3 and row['first_response_confirmed'] for row in value['benches'].values())
    assert probe.measure_all(setting)==value and len(seen)==5
    from skillopt.execskill import v211_smoke
    measured = p.record('v211-route-probes', 'smoke', {
        k: v for k, v in value.items() if k not in ('version', 'evidence', p.RECORD_HASH)})
    assert v211_smoke.check_route_probes(measured) == measured
    for mutation in ('ceiling', 'completion', 'model', 'longest', 'request_hash'):
        changed = deepcopy(measured)
        row = changed['benches']['officeqa']
        if mutation == 'ceiling': row['request_ceiling'] = row['max_tokens'] - 1
        elif mutation == 'completion': row['receipts'][0]['usage']['completion_tokens'] = row['request_ceiling'] + 1
        elif mutation == 'model': row['receipts'][0]['returned_model'] = 'unregistered-model'
        elif mutation == 'longest': row['longest'] += 1
        else: row['receipts'][0]['request_sha256'] = 'not-a-request-hash'
        changed = p.record('v211-route-probes', 'smoke', {
            k: v for k, v in changed.items() if k not in ('version', 'evidence', p.RECORD_HASH)})
        with pytest.raises(ValueError, match='probe receipts'):
            v211_smoke.check_route_probes(changed)
    with pytest.raises(ValueError,match='explicit benchmark'):
        probe.measure(setting)


def test_smoke_caps_are_derived_separately_and_pin_every_stage_maximum():
    ident=v.smoke_identity()
    assert set(ident['stages'])=={'S2','S3','SX'}
    assert sum(sum(cells) for cells in ident['stages']['S2']['solver_cells'].values())==172
    for stage in ident['stages']:
        row=v.smoke_caps(stage)
        assert row['solver']==sum(row['solver_by_bench'].values())
        assert row['method']==sum(row['method_by_bench'].values())
        assert row['overall']==row['solver']+row['method']
    assert ident['overall']==sum(row['overall'] for row in ident['stages'].values())
    assert ident['stages']['SX']['solver_cells']['searchqa']==[730,2764]
    assert ident['stages']['S3']['method_calls']['officeqa']['audit_g']==361
    assert ident['stages']['S3']['method_calls']['spreadsheetbench']['audit_g']==505
    assert ident['stages']['S3']['method_calls']['officeqa']['engineer']==87
