"""Two-chain authored rehearsal through production units and gates; no external service.

Reduced authored cuts (12 run/12 acceptance; registered 40/4 confirm counts) keep this
control-flow fixture small. It is not the registered supply, measured smoke, or method evidence.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import itertools
import json
from pathlib import Path

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest
from skillopt.execskill import (acceptance, audit, budgets, chain, client, describer, engineer, engineer_v211,
    examiner, instruction_start, profiles as p, rounds, slots, solver, step, units, v210_import)
from skillopt.execskill.package import FIXTURE, load
from skillopt.execskill.registry import Registry
from tests.execskill_fakes import FakeGLM, FakeSolver, FakeProvider, engineer_reply, tagged
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_chain import CONSENT
from tests.test_execskill_routes import route_b_config
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_zpc_pipeline import SourceWorker, offline  # noqa: F401
from tests.test_execskill_shortcut_sb import workbook, DELIVERED

LEARNED = ('searchqa', 'officeqa', 'livemath', 'spreadsheetbench')
QA_SOURCE = '''import re
def applies(view):
    return "Fixture record" in view.get("question", "")
def before_call(view, state):
    values = re.findall(r"value ([0-9]+)", view["question"])
    return {"facts": ["Computed public value " + values[0]]} if values else {}
'''
SHEET_SOURCE = '''def sheet_feedback(view, run_report, state):
    failed = run_report.get("status") == "exception"
    return {"fields": {"facts": ["The public execution raised an exception."]} if failed else {}, "request_repair": failed}
'''


@contextmanager
def workers(package, *, kind='cell', inputs_dir=None, **kwargs):
    instance = SourceWorker().start(package, kind=kind, inputs_dir=inputs_dir)
    try:
        yield instance
    finally:
        instance.close()


def build(tmp_path, monkeypatch, chain_id='G'):
    """Reusable offline Setting/Services plus observable real-client fake providers."""
    public_book, reference_book = tmp_path / 'public.xlsx', tmp_path / 'reference.xlsx'
    workbook(public_book, 'public')
    workbook(reference_book, 'reference')
    pools, cuts = {}, {}
    for bench in LEARNED:
        confirms = 40 if bench == 'searchqa' else 4
        entries = []
        for i in range(24 + 6 * confirms):
            if bench == 'spreadsheetbench':
                public = {'instruction': 'Fixture record %d: copy public value 17 to B1.' % i,
                          'input_files': [str(public_book)], 'answer_position': 'B1'}
                private = {'test_files': [str(reference_book)], 'answer_position': 'B1'}
            elif bench == 'livemath':
                public = {'question': 'Fixture record %d: identify public value 17.' % i,
                          'choices': 'A. 17\n\nB. 18\n\nC. 19\n\nD. 20\n\nE. 21'}
                private = {'answer': 'A'}
            else:
                public = {'question': 'Fixture record %d: identify public value 17.' % i,
                          'context': ['The visible value is 17.'] if bench == 'searchqa' else 'The visible value is 17.'}
                private = {'answers': ['17']} if bench == 'searchqa' else {'answer': '17'}
            entries.append({'benchmark': bench, 'task_id': bench + '-fixture-%03d' % i,
                            'part': 'authored', 'public': public, 'private': private})
        pools[bench] = entries
        cuts[bench] = {'run': entries[:12], 'accept': entries[12:24],
                      **{'confirm-r%d' % r: entries[24 + (r-1)*confirms:24+r*confirms] for r in range(1,7)}}
    root = tmp_path / 'root'
    auditor = Judge()
    def audit_reply(system, user):
        return auditor.plain('audit', system, user, label='authored-judge', max_tokens=8192)
    def answer(system, user):
        if system.startswith(('You audit helper programs', 'You check helper notes')):
            return audit_reply(system, user)
        if user == p.FIRST_CALL_USER:
            return 'ready'
        view = json.loads(user)
        if 'instruction' in view:
            return '```python\n# AUTHOR_%s\nx = 17\n```' % ('PASS' if 'previous_program' in view else 'FAIL')
        effective = 'Computed public value 17' in view.get(p.NOTES_KEY, '')
        return tagged(('A' if effective else 'B') if 'choices' in view else ('17' if effective else '0'))
    def roles(system, payload):
        if system.startswith(('You audit helper programs', 'You check helper notes')):
            return audit_reply(system, payload)
        if system == examiner.DETECTOR_SYSTEM:
            return engineer_reply({'detectors': []}, [])
        if system == engineer.ANALYST_SYSTEM:
            return engineer_reply({'findings': []}, [])
        if isinstance(payload, dict) and payload.get('request') == 'policy':
            return {'families': [], 'requests': [], 'rationale': 'No authored generation material.'}
        if isinstance(payload, dict) and payload.get('request') in ('generator', 'generate', 'topup'):
            return {'specs': []}
        if system == describer.DESCRIBER_SYSTEM:
            return 'Extract the visible numeric quantity or request repair after a public execution exception.'
        if isinstance(payload, dict) and payload.get('bench') in LEARNED and payload.get('round'):
            if payload['round'] > 1:
                return engineer_reply({'changes': []}, [])
            bench = payload['bench']
            return engineer_reply({'changes': [{'kind': 'new', 'description': 'Compute from the current public input.',
                'max_note_chars': 1500, 'requests_second_call': bench == 'spreadsheetbench',
                'excluded_benches': [b for b in p.BENCHES if b != bench]}]},
                [SHEET_SOURCE if bench == 'spreadsheetbench' else QA_SOURCE])
        return {'verdict': 'no', 'reason': 'Authored generic public-input computation.'}
    glm = FakeGLM(tmp_path / 'roles', roles)
    gsolver = FakeSolver(tmp_path / 'solver-g', [(None, answer)], model=p.CHAINS['G'])
    dprovider = FakeProvider(client.NORTHGATE_MODEL, answer)
    dclients = {bench: client.solver_client(p.CHAINS['D'], config=route_b_config(tmp_path / ('d-' + bench),
                    max_tokens=units.solver_tokens(p.CHAINS['D'], bench), read_timeout=600),
                    transport=dprovider.transport) for bench in p.BENCHES}
    ledger = Budget(budgets.ledger_root(root, chain_id), sleep=lambda _: None)
    ledger.declare(budgets.chain_caps(chain_id, p.MAIN_V4))
    runtime = {bench: {} for bench in p.BENCHES}
    setting = units.Setting(run='v211-authored-rehearsal', root=root, shared=root/'shared', pools=pools,
        cards={b: row['text'] for b, row in instruction_start.pins().items()}, runtime=runtime,
        clients=lambda model, bench: glm.client if bench is None else gsolver.client if model == p.CHAINS['G'] else dclients[bench],
        budget=ledger, slots=slots.pools(tmp_path/'slots',poll=.01,log=lambda _:None), sandbox={},
        evidence=FIXTURE, workers=1, cooldown=0, branch='E', extra={'configuration':p.MAIN_V4,
        'alfworld_v11_import':v210_import.pins(),'v211_prompt_pins':engineer_v211.pins(),
        'slot_root':str(tmp_path/'slots'),'test_read_estimate':{'G':1000,'D':1000}})
    ticks, waits = itertools.count(), []
    clock = lambda: float(next(ticks)) + sum(waits)
    original_context = units.cell_context
    def cell_context(st, attempt, endpoint, **kwargs):
        found = original_context(st, attempt, endpoint, **kwargs)
        found.worker, found.clock = lambda bench: SourceWorker(), clock
        return found
    monkeypatch.setattr(units,'cell_context',cell_context)
    monkeypatch.setattr(rounds,'cell_context',cell_context)
    monkeypatch.setattr(step,'_cut',lambda st, held: deepcopy(cuts[st.bench]))
    monkeypatch.setattr(solver._Shell,'run_precheck',lambda self,program,*args: {
        'status':'exception' if 'AUTHOR_FAIL' in program else 'ok','exc_type':'ValueError' if 'AUTHOR_FAIL' in program else None,
        'message':'Authored public execution exception' if 'AUTHOR_FAIL' in program else '', 'answer_cells':{}})
    monkeypatch.setattr(backends, '_native', lambda request, runtime: dict(DELIVERED))
    score = backends.score
    def scored(bench, public, private, prediction, **kwargs):
        if bench == 'spreadsheetbench':
            ok = 'AUTHOR_PASS' in str(prediction.get('output'))
            status = 'pass' if ok else 'fail'
            return {'status':status,'score':int(ok),'reason':'authored_native_scorer',
                    'cleanup_confirmed':True,'metrics':{'cases':[{'status':status,'reason':'fixture'}]}}
        return score(bench,public,private,prediction,**kwargs)
    monkeypatch.setattr(backends,'score',scored)
    services = step.Services(registry=Registry(tmp_path/'registry',evidence=FIXTURE),sources=None,
        workers=workers,clock=clock,sleep=waits.append)
    return setting, services, {'G':gsolver,'D':dprovider,'roles':glm,'auditor':auditor,'cuts':cuts,'waits':waits}


def exercise(setting, services, fakes, chain_id):
    """Run production control flow and return a compact, reproducible authored receipt."""
    initial_counts = (len(fakes['G'].requests),len(fakes['D'].requests),len(fakes['roles'].seen))
    write_json(setting.shared/'consent.json',{**CONSENT,'multi_arm_arms':['F','C','B']})
    records, read_specs = [], []
    def learn(st,root,chain_,k,bench,parent):
        result = step.run_step(st,chain_,bench,k,parent,services=services,chain_root=root)
        records.append(result.record)
        return result.package,result.record
    def launch(st,spec):
        read_specs.append(spec)
        write_json(Path(spec['unit_root'])/'unit.json',p.record('evaluation',FIXTURE,{
            'run':st.run,'chain':chain_id,'bench':spec['bench'],
            'packages':{arm:spec['package_sha256'] for arm in ('F','C','B')},
            'synthetic_fixture':True}))
        return chain.EXIT_COMPLETE
    outcome = chain.run(setting,chain_id,learn=learn,launch=launch)
    assert outcome == {'status':'complete'}, (outcome, [path.read_text() for path in setting.root.rglob('diagnostics.log')])
    assert [r['bench'] for r in records] == list(p.BENCHES)
    assert all(r['decision']=='accept' for r in records[:4]), [(r['bench'],r['reason']) for r in records]
    assert records[-1]['learning']=='import' and records[-1]['units']=={}
    assert len(read_specs)==5 and {r['bench'] for r in read_specs}==set(p.BENCHES)
    learned = []
    for k,bench in enumerate(LEARNED,1):
        root=setting.root/chain_id/('s%d-%s'%(k,bench))
        result=lambda name:p.verified(read_json(root/name/'unit.json'),'unit')['result']
        assert result('train-r1')['adopted'] and result('confirm-r1')['confirm']['passed']
        assert result('audit-final')['audit_final']['coverage_by_bench'][bench]
        assert result('accept')['decision']=='accept'
        sealed=p.verified(read_json(root/'accept/sealed.json'),'acceptance-sealed')
        assert sealed['rule']['name']=='practical-v2-11-pooled' and sealed['placebo_y'] is None
        attempt=root/'accept/attempt-1'
        cells=[p.verified(read_json(path),'cell') for path in sorted((attempt/'cells').glob('*.json'))]
        decision=acceptance.decide(cells,sealed)
        stored=p.verified(read_json(attempt/'decision/decision.json'),'decision')
        assert decision==stored and decision['guards']['J2']=={'removed':True}
        learned.append({'bench':bench,'decision':records[k-1]['decision'],
            'adopted_round':1,'confirmed_round':1,'confirm_passed':True,
            'run_items':len(fakes['cuts'][bench]['run']),'accept_items':len(fakes['cuts'][bench]['accept']),
            'confirm_items':len(fakes['cuts'][bench]['confirm-r1']), 'acceptance_cells':len(cells),
            'final_audit_coverage':result('audit-final')['audit_final']['coverage_by_bench'][bench],
            'decision_sha256':stored['record_sha256'],'rule':sealed['rule']['name']})
    root=setting.root/chain_id
    complete=p.verified(read_json(root/'chain-complete.json'),'chain-complete')
    final=load(root/'packages'/(complete['package_sha256']+'.json'))
    assert len(final.procedures)==7 and final.order[-3:]==tuple(row[0] for row in v210_import.PROCEDURES)
    read=p.verified(read_json(root/'test-read.json'),'test-read')
    assert read['arms']==['F','C','B'] and read['status']=='read'
    counts=(len(fakes['G'].requests),len(fakes['D'].requests),len(fakes['roles'].seen))
    assert chain.run(setting,chain_id,learn=learn,launch=launch)=={'status':'complete'}
    assert counts==(len(fakes['G'].requests),len(fakes['D'].requests),len(fakes['roles'].seen)) and len(read_specs)==5
    assert not any(row['open'] for row in setting.budget.snapshot().values())
    namespace = p.namespace_of(setting,chain_id)
    assert namespace == chain_id+'-v4'
    registered = {bench:sorted(services.registry.entries(namespace,bench)) for bench in LEARNED}
    assert all(registered.values())
    return {'chain':chain_id,'namespace':namespace,'status':'complete','learned':learned,
        'registered_item_ids_sha256':digest(registered),'final_package_sha256':final.sha256,
        'final_procedures':len(final.procedures),'import':{'learning':'import','units':0,
        'source_package_sha256':records[-1]['source_package_sha256'],
        'procedure_source_sha256':{row[0]:row[3] for row in v210_import.PROCEDURES}},
        'read':{'benches':sorted(row['bench'] for row in read_specs),'arms':['F','C','B'],
                'launcher':'synthetic_fixture','units':len(read_specs),'resume_additional_calls':0},
        'call_counts':dict(zip(('solver_G','solver_D','roles'),
                              (after-before for after,before in zip(counts,initial_counts)))),
        'ledger':setting.budget.snapshot()}


def rehearse(tmp_path,monkeypatch):
    """Same authored items, independent G-v4/D-v4 registries and budgets, both actual chains."""
    setting, services, fakes = build(tmp_path,monkeypatch,'G')
    receipts = [exercise(setting,services,fakes,'G')]
    ledger = Budget(budgets.ledger_root(setting.root,'D'),sleep=lambda _:None)
    ledger.declare(budgets.chain_caps('D',p.MAIN_V4))
    receipts.append(exercise(replace(setting,budget=ledger),services,fakes,'D'))
    assert receipts[0]['registered_item_ids_sha256']==receipts[1]['registered_item_ids_sha256']
    return {'evidence':'authored_engineering_fixture','configuration':p.MAIN_V4,
        'limitations':['Reduced 12 run and 12 acceptance items; not registered supply or measured smoke.',
            'Authored source worker, fake native/scorer/providers, synthetic read launcher; not method-effect evidence.'],
        'chains':receipts}


def test_two_chains_four_learning_steps_import_and_once_only_fivebench_read(tmp_path,monkeypatch):
    report = rehearse(tmp_path,monkeypatch)
    assert [row['namespace'] for row in report['chains']]==['G-v4','D-v4']
