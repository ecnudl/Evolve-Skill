"""Cross-v5 readiness and practice-only cross-arm smoke on authored evidence."""
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, manifest, profiles as p, units, v214_preparation,
                               v214_smoke as v, v214_stages as stages, v219_read, v219_smoke)
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_manifest import reseal
from tests import test_execskill_v217i_smoke as parent

CHILD = p.CROSS_V5


def owner_consent():
    return {'by': 'owner', 'date': '2026-11-02', 'note': 'Authored cross-card transfer consent.',
        'test_evaluation': True, 'sheet_test_qualification': True,
        'multi_arm_arms': ['F', 'C', 'B', 'cross']}


def setup(root, monkeypatch, chain='G'):
    monkeypatch.setattr(parent, 'CHILD', CHILD)
    monkeypatch.setattr(parent, 'owner_consent', owner_consent)
    return parent.setup(root, monkeypatch, chain)


def measured_s2(card_tokens=100, procedure_tokens=160):
    rows = {}
    for bench, n in v.S2_ITEMS.items():
        labels = v219_read.labels(bench)
        sources = {label: None for label in labels}
        if bench == p.ZEBRA:
            sources.update({'B': 'C', **{arm: 'F' for arm in v219_read.cross_labels(bench)}})
        elif bench != 'alfworld':
            sources['F'] = 'C'
        costs, coverage, measured, per_class = {}, {}, {}, {}
        for label in labels:
            source = sources[label]
            identity = {'request_sha256': digest([bench, source or label]),
                'post_call_sha256': digest([]), 'fault_free': True}
            coverage[label] = {'cells': 1, 'cell': digest({'bench': bench, 'arm': label}),
                'card_source': v219_read.card_source(bench, label),
                'shared_with': source and digest({'bench': bench, 'arm': source}),
                'source_arm': source, 'request_sha256': [] if source else [digest([bench, label])],
                'request_reuse': {'version': v219_read.VERSION, 'source_arm': source,
                    'planned_source_arm': source, 'identity': identity, 'source_identity': deepcopy(identity)}
                    if source else None}
            if source:
                continue
            kind = 'procedure' if bench in (p.ZEBRA, 'alfworld') and label not in ('C', 'B') else 'card'
            count = n if label == 'C' else 1
            tokens = (procedure_tokens if kind == 'procedure' else card_tokens) * count
            costs[label] = {kind: {'cells': count, 'tokens': tokens}}
            measured[label] = {'cells': count, 'tokens': tokens}
            entry = per_class.setdefault(kind, {'cells': 0, 'tokens': 0})
            entry['cells'] += count
            entry['tokens'] += tokens
        actual = sum(x['tokens'] for x in measured.values())
        rows[bench] = {'passed': True, 'items': n, 'cells': n+6, 'arms': labels,
            'first_response_confirmed': True, 'sealed_reads': 0, 'cross_coverage': coverage,
            'cost_by_arm': costs, 'dispatched_cells': sum(x['cells'] for x in measured.values()),
            'measurements': {'per_arm': {bench: measured}, 'per_class': {bench: per_class},
                'request_bytes': {bench: 1000}, 'actual': actual}, 'settled_tokens': actual}
    return {'passed': True, 'cells': sum(row['cells'] for row in rows.values()), 'benches': rows, 'sealed_reads': 0}


def receipts(chain, *, m=None):
    m = m or {p.RECORD_HASH: 'a'*64, 'data': {'snapshot_sha256': 'b'*64, 's0_sha256': 'c'*64}}
    probe = parent.probe(chain, m[p.RECORD_HASH])
    bounds = v.solver_bounds(chain, probe, configuration=CHILD)
    s2 = {**measured_s2(), 'solver_bounds': bounds, 'solver_probe': probe}
    outputs = {'S0': {'passed': True, 'model_calls': 0},
        'S1': {'passed': True, 'solver_probe': probe, 'solver_bounds': bounds,
               'solver_confirmation': probe['first_call'][p.RECORD_HASH]},
        'S2': s2, 'SE6': stages.projection(s2, chain, bounds=bounds, configuration=CHILD)}
    records = {name: p.record('v214-smoke-stage', 'smoke', {'configuration': CHILD,
        'chain': chain, 'stage': name, 'manifest_sha256': m[p.RECORD_HASH], 'measured': True,
        'schedule_sha256': digest(v.schedule(CHILD)), 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'result': output}) for name, output in outputs.items()}
    return p.record('v214-smoke-result', 'smoke', {'configuration': CHILD, 'chain': chain,
        'manifest_sha256': m[p.RECORD_HASH], 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'schedule_sha256': digest(v.schedule(CHILD)),
        'stages': {name: row[p.RECORD_HASH] for name, row in records.items()}, 'stage_records': records,
        'passed': True, 'sealed_reads': 0})


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_preparation_manifest_pins_cross_consent_caps_and_sheet_qualification(tmp_path, monkeypatch, chain):
    checked, made, options = setup(tmp_path, monkeypatch, chain)
    assert checked['configuration'] == made['configuration'] == CHILD
    assert checked['consent'] == owner_consent() == read_json(options['root']/'shared/consent.json')
    assert v214_preparation.verify(checked['preparation']) == checked['preparation']
    assert made['sheet_qualification'] == checked['launch_sheet_runtime']['qualification']
    assert made['data']['launch_sheet_runtime']['snapshot_sha256'] == checked['snapshot_sha256']
    assert made['sizes']['v214'] == manifest._plain(p.cross_v5_identity())
    assert made['sizes']['v214']['caps']['test_read_cap'] == 413000000
    for c in p.CHAINS:
        assert made['caps'][c+':test'] == 619000000
        assert made['caps'][c+':solver'] == 620100000
        assert c+':redo' not in made['caps']
    assert manifest.check(made) == made
    old = deepcopy(made)
    old['caps'][chain+':test'] = 662000000
    with pytest.raises(ValueError, match='registered run configuration and carries its caps'):
        manifest.check(reseal(old))


@pytest.mark.parametrize('change', [
    {'by':'agent'}, {'date':''}, {'note':''}, {'test_evaluation':False},
    {'sheet_test_qualification':False}, {'extra':True}, {'multi_arm_arms':['F','C','B','stages']},
    {'multi_arm_arms':['F','C','B']}, {'multi_arm_arms':['C','F','B','cross']},
    {'multi_arm_arms':['F','C','B','cross','stages']},
    {'multi_arm_arms':['F','C','B','X_searchqa','X_officeqa','X_zebralogic','X_spreadsheetbench','X_alfworld']},
])
def test_consent_refuses_every_nonregistered_shape_before_write(tmp_path, change):
    supplied=tmp_path/'owner.json'
    write_json(supplied, {**owner_consent(), **change})
    with pytest.raises(ValueError, match='consent'):
        v.prepare_consent(tmp_path/'root', CHILD, consent_file=supplied)
    assert not (tmp_path/'root/shared/consent.json').exists()


def test_consent_preserves_existing_different_owner_record(tmp_path):
    supplied=tmp_path/'owner.json'
    write_json(supplied, owner_consent())
    target=tmp_path/'root/shared/consent.json'
    write_json(target,{**owner_consent(),'note':'original'})
    before=target.read_bytes()
    with pytest.raises(ValueError, match='replace different'):
        v.prepare_consent(tmp_path/'root', CHILD, consent_file=supplied)
    assert target.read_bytes()==before


@pytest.mark.parametrize('chain', ['G','D'])
def test_measured_readiness_checks_cross_shapes_and_separate_retry(chain):
    found=receipts(chain)
    checked, projected=v.checked_readiness(found,chain=chain,source_sha256='b'*64,s0_sha256='c'*64,configuration=CHILD)
    assert checked==found and projected['passed']
    assert projected['stage_packages']==0
    assert projected['method_cost']=={'model_calls':0,'all_role_caps':0,'learning':'none'}
    panel_costs=[100*cards+160*procedures for cards,procedures in p.TEST_READ_CELLS[CHILD].values()]
    need=sum(panel_costs)+max(panel_costs)+projected['read_reservation']
    assert projected['solver_scopes'][chain+':test']=={'projected':need,'cap':619000000,'passed':True}
    assert projected['solver_scopes'][chain+':solver']=={'projected':need,'cap':620100000,'passed':True}
    assert found['stage_records']['S2']['result']['cells']==106
    assert all(v219_read.cross_labels(b) for b in p.MAIN_V5_ORDER)
    assert v.stages_of(CHILD)==('S0','S1','S2','SE6')
    assert v.schedule(CHILD)['S2_arms']=={b:v219_read.labels(b) for b in p.MAIN_V5_ORDER}


@pytest.mark.parametrize('bench',p.MAIN_V5_ORDER)
@pytest.mark.parametrize('damage',['missing_cross','wrong_card','missing_request','missing_cost'])
def test_se6_refuses_missing_or_misattributed_cross_measurement(bench,damage):
    found=measured_s2()
    row=found['benches'][bench]
    arm=v219_read.cross_labels(bench)[0]
    if damage=='missing_cross':
        del row['cross_coverage'][arm]
    elif damage=='wrong_card':
        row['cross_coverage'][arm]['card_source']=bench
    elif damage=='missing_request':
        row['cross_coverage']['C']['request_sha256']=[]
    else:
        del row['cost_by_arm']['C']
    with pytest.raises(ValueError,match='Cross|cross|dispatched'):
        stages.projection({**found,'solver_probe':parent.probe('G')},'G',bounds=v.solver_bounds('G'),configuration=CHILD)


def test_projection_prices_larger_cross_card_and_procedure_cost_without_shared_dilution():
    row=measured_s2()['benches']['alfworld']
    arm='X_searchqa'
    row['cost_by_arm'][arm]['procedure']['tokens']=900
    row['measurements']['per_arm']['alfworld'][arm]['tokens']=900
    price=v219_smoke.measured_prices(row,'alfworld')
    assert Fraction(price['card'])==100 and Fraction(price['procedure'])==900
    assert price['procedure_assumed'] is False
    shared=measured_s2()['benches']['zebralogic']
    assert set(shared['cost_by_arm'])=={'F','C'}
    assert Fraction(v219_smoke.measured_prices(shared,'zebralogic')['procedure'])==160


@pytest.mark.parametrize('chain',['G','D'])
def test_s2_dispatches_cross_practice_helper_on_every_bench_without_roles(tmp_path,monkeypatch,chain):
    pools={bench:[{'task_id':str(i),'public':{},'private':{}} for i in range(n)] for bench,n in v.S2_ITEMS.items()}
    setting=units.Setting('a'*64,tmp_path,tmp_path/'shared',pools,{}, {},lambda *a: object(),
        Budget(tmp_path/'ledger'),{}, {},'engineering_fixture',
        branch='N' if chain=='D' else None,longest=60000 if chain=='D' else None,extra={'configuration':CHILD})
    monkeypatch.setattr(stages,'fixture_pools',lambda *a:pools)
    monkeypatch.setattr(units,'for_unit',lambda setting,*a:setting)
    monkeypatch.setattr(units,'drainer',lambda *a:None)
    monkeypatch.setattr(units,'role_endpoint',lambda *a,**kw:pytest.fail('No method roles'))
    monkeypatch.setattr(budgets,'endpoint',lambda *a,**kw:object())
    monkeypatch.setattr(units,'run_unit',lambda root,**kw:{'result':kw['work'](tmp_path/'attempt')})
    seen=[]
    def practice(local,attempt,endpoint,unit,bench,tasks,c):
        assert p.configuration_of(local)==CHILD and c==chain
        assert len(tasks)==v.S2_ITEMS[bench]
        seen.append(bench)
        return measured_s2()['benches'][bench]
    monkeypatch.setattr(v219_smoke,'practice',practice)
    found=stages.s2(setting,chain)
    assert seen==list(p.MAIN_V5_ORDER) and found['passed'] and found['cells']==106


@pytest.mark.parametrize('chain',['G','D'])
def test_real_manifest_needs_both_measured_cross_chains(tmp_path,monkeypatch,chain):
    _,made,options=setup(tmp_path,monkeypatch,chain)
    options.update(smoke_chain=None,root=tmp_path/'real')
    monkeypatch.setitem(p.RUN_ROOTS,CHILD,str(options['root']))
    with pytest.raises(ValueError,match='both measured'):
        v.make_manifest(tmp_path/'refused.json',**options)
    paths=[]
    for c in p.CHAINS:
        found=receipts(c,m=made)
        target=tmp_path/'measured'/c
        for name,row in found['stage_records'].items(): write_json(target/(name+'.json'),row)
        path=target/v.RESULT; write_json(path,found); paths.append(path)
    real=v.make_manifest(tmp_path/'manifest-real.json',measured_smoke=paths,**options)
    assert real['evidence']=='cross_v5_test_read' and manifest.check(real)==real
    bad=deepcopy(real)
    row=bad['data']['v214_readiness']['D']['stage_records']['S2']
    row['result']['benches']['alfworld']['cross_coverage'].pop('X_searchqa')
    bad['data']['v214_readiness']['D']['stage_records']['S2']=reseal(row)
    bad['data']['v214_readiness']['D']['stages']['S2']=reseal(row)[p.RECORD_HASH]
    bad['data']['v214_readiness']['D']=reseal(bad['data']['v214_readiness']['D'])
    with pytest.raises(ValueError,match='Cross SE6'):
        manifest.check(reseal(bad))


@pytest.mark.parametrize('action',['snapshot','selftest','s0','manifest','structural-smoke','smoke-run','smoke-summary'])
def test_cli_adds_cross_choice_and_preserves_parent_default(action):
    from scripts.run_execskill import parser
    commands=parser()._subparsers._group_actions[0].choices
    option=next(a for a in commands['v214-'+action]._actions if a.dest=='configuration')
    assert tuple(option.choices)==(p.MAIN_V5,p.IMPLANT_V5,p.MAIN_V6,CHILD,p.SEARCHQA_HP_V6, p.MAIN_V7,p.MAIN_V8,p.MAIN_V9,p.MAIN_V10)
    assert option.default==p.MAIN_V5


@pytest.mark.parametrize('configuration',[p.MAIN_V5,p.IMPLANT_V5,p.MAIN_V6,CHILD])
def test_cli_passes_only_explicit_configuration_without_changing_old_calls(tmp_path,monkeypatch,configuration):
    from scripts.run_execskill import parser,v214_command
    calls=[]
    monkeypatch.setattr(v,'snapshot',lambda out,**kw:calls.append(kw) or {'passed':True})
    args=['v214-snapshot','--out',str(tmp_path/'out'),'--source',str(tmp_path/'source'),'--git-head','a'*40]
    assert v214_command(parser().parse_args(args+['--configuration',configuration]))==0
    assert calls==[{'source':str(tmp_path/'source'),'git_head':'a'*40,
                    **({'configuration':configuration} if configuration!=p.MAIN_V5 else {})}]


def test_cross_structural_smoke_reuses_fixed_chain_without_sx(tmp_path,monkeypatch):
    monkeypatch.setattr(manifest,'load',lambda *a,**kw:{'configuration':CHILD,p.RECORD_HASH:'a'*64})
    monkeypatch.setattr(manifest,'verify_code',lambda *_:None)
    monkeypatch.setattr(stages,'sx',lambda *a,**kw:pytest.fail('No SX'))
    found=v.structural_smoke(tmp_path/'unread',out=tmp_path/'structural.json',configuration=CHILD)
    assert found['passed'] and not found['measured_readiness']
    assert found['model_calls']==found['sealed_reads']==0


@pytest.mark.parametrize('chain',['G','D'])
def test_practice_runs_real_card_substitution_cells_and_sharing_on_authored_officeqa(tmp_path,monkeypatch,chain):
    from skillopt.coevo5.calls import Endpoint, Slots
    from skillopt.coevo5.protocol import RUNTIME
    from skillopt.execskill import cells, rounds
    from tests.fixtures.execskill.items import officeqa_items
    from tests.test_execskill_evaluation import Solver
    from tests.test_execskill_zpc_pipeline import SourceWorker, workers
    fake=Solver()
    endpoint=Endpoint(fake,model=p.CHAINS['D'],max_tokens=100,
        slots=Slots(tmp_path/'slots','authored',2),sleep=lambda _:None)
    attempt=tmp_path/'attempt'
    context=cells.Context(attempt=attempt,endpoint=endpoint,runtime=RUNTIME,cards=v219_read.cards(),
        native=None,episodes=None,worker=lambda _:SourceWorker(),
        evidence='engineering_fixture',configuration=CHILD)
    monkeypatch.setattr(units,'cell_context',lambda *a:context)
    monkeypatch.setattr(rounds,'cell_context',lambda *a:context)
    monkeypatch.setattr(v219_smoke.evaluation,'_route_worker',
        lambda setting,package,item,**kwargs: workers(package,**kwargs))
    setting=SimpleNamespace(extra={'configuration':CHILD},evidence='engineering_fixture',workers=2)
    tasks={rounds.key('officeqa',row['task_id']):{'public':row['public'],'private':row['private']}
           for row in officeqa_items(20)}
    result=v219_smoke.practice(setting,attempt,endpoint,chain+'/v214-smoke/S2/officeqa','officeqa',tasks,chain)
    assert result['passed'] and result['cells']==26 and result['dispatched_cells']==fake.calls==25
    assert result['request_reuse']['shared_cells']==1
    assert result['cross_coverage']['F']['source_arm']=='C'
    assert result['measurements']['per_arm']['officeqa']['C']['cells']==20
    records=[read_json(path) for path in (attempt/'cells').glob('*.json')]
    assert len(records)==26 and len([row for row in records if row['shared_with']])==1
    for label in v219_read.cross_labels('officeqa'):
        row=next(row for row in records if row['cell']['arm']==label)
        assert row['card_source']==label[2:] and row['shared_with'] is None
        assert row['request_reuse']['reason']=='dispatched' and row['logical_calls']
    assert Fraction(v219_smoke.measured_prices(result,'officeqa')['card'])==15


@pytest.mark.parametrize('damage',['identity','source_cell','source_request','source_fault'])
def test_cross_readiness_refuses_mismatched_shared_request_attribution(damage):
    row=measured_s2()['benches']['zebralogic']
    linked=row['cross_coverage']['X_searchqa']
    if damage=='identity': linked['request_reuse']['identity']['post_call_sha256']='f'*64
    elif damage=='source_cell': linked['shared_with']='different-source'
    elif damage=='source_request': row['cross_coverage']['F']['request_sha256']=['f'*64]
    else: linked['request_reuse']['identity']['fault_free']=False
    with pytest.raises(ValueError,match='fault-free request'):
        v219_smoke.measured_prices(row,'zebralogic')
