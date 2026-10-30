"""Mixed-step inheritance exercised with authored cells and in-process workers only."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json
from skillopt.execskill import (acceptance, audit, budgets, confirm, engineer, engineer_v211,
                               profiles as p, step, units, v210_import, zebralogic as z)
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes import FakeSolver, engineer_reply
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v212_evaluation import final_package
from tests.test_execskill_zpc_pipeline import SourceWorker, build, fixture_pool, offline, public_grid  # noqa: F401

CHILD = p.MAIN_V5


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_zebra_step_three_uses_v212_slices_and_confirm_supply(tmp_path, monkeypatch, chain):
    setting, services, _, _ = build(tmp_path, monkeypatch)
    setting.extra['configuration'] = CHILD
    parent = empty(step=chain+'/s2-officeqa', evidence='engineering_fixture')
    st = step._Step(setting, services, chain, z.BENCH, 3, parent, setting.root/chain)
    expected = z.slices(setting.pools[z.BENCH])
    cut = step._cut(st, set())
    assert cut['run'] == expected['run'] and len(cut['run']) == 60
    assert cut['accept'] == expected['accept'] and len(cut['accept']) == 100
    assert cut['confirm'] == confirm.slice_items(p.ZEBRA_PC_V13, setting.pools[z.BENCH])[0]
    assert len(cut['confirm']) == 40
    assert not any(key.startswith('confirm-r') for key in cut)
    assert p.namespace_of(setting, chain) == chain+'-v5'


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_zebra_acceptance_step_three_preserves_full_independent_c_and_sealed_v212_rule(
        tmp_path, monkeypatch, fast_statistics, chain):
    setting, services, fake_solver, _ = build(tmp_path, monkeypatch)
    setting.extra['configuration'] = CHILD
    setting.budget = Budget(tmp_path/'v214-ledger', sleep=lambda _: None)
    setting.budget.declare(budgets.chain_caps(chain, CHILD))
    if chain == 'G':
        def answer(system, user):
            return json.dumps({'reasoning': 'Authored response.', 'solution': public_grid(z.parse_user(user))})
        fake_solver = FakeSolver(tmp_path/'glm-solver', [(None, answer)], model=p.CHAINS['G'])
        setting.clients = lambda model, bench: fake_solver.client
    @contextmanager
    def workers(package, item):
        worker = SourceWorker().start(package, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    services = replace(services, item_workers=workers)
    parent = empty(step=chain+'/s2-officeqa', evidence='engineering_fixture')
    candidate = with_(parent, step=chain+'/s3-zebralogic', add=final_package().procedures)
    st = step._Step(setting, services, chain, z.BENCH, 3, parent, setting.root/chain)
    monkeypatch.setattr(st, 'verify', lambda: None)
    monkeypatch.setattr(units, 'drainer', lambda *args, **kwargs: None)
    monkeypatch.setattr(step, '_run_trajectories', lambda *args, **kwargs: pytest.fail('No donor trajectories'))
    result = step._accept(st, {'accept': z.slices(setting.pools[z.BENCH])['accept']}, candidate, None)
    sealed = p.verified(read_json(st.root/'accept/sealed.json'), 'acceptance-sealed')
    assert sealed['configuration'] == CHILD and sealed['bench'] == z.BENCH
    assert sealed['rule'] == p.ACCEPT_RULES[p.ZEBRA_PC_V13]
    assert sealed['freshness'] == p.ACCEPT_FRESHNESS[p.ZEBRA_PC_V13]
    assert sealed['j6_registered'] is True
    assert set(sealed['packages']) == {'candidate', 'parent', 'card'}
    assert sealed['corpus'] is None and sealed['placebo_y'] is None
    assert sealed['reuse']['card_sample']['coverage'] == 'full_independent_astar'
    records = [read_json(path) for path in (st.root/'accept/attempt-1/cells').glob('*.json')]
    cards = [row for row in records if row['cell']['arm'] == 'C']
    assert len(cards) == 100 and all(row['shared_with'] is None for row in cards)
    assert {'P_y', 'P_i'}.isdisjoint(row['cell']['arm'] for row in records)
    calls = len(fake_solver.requests)
    assert step._accept(st, {'accept': z.slices(setting.pools[z.BENCH])['accept']}, candidate, None) == result
    assert len(fake_solver.requests) == calls
    changed = {key:value for key,value in sealed.items() if key not in ('version','evidence',p.RECORD_HASH)}
    changed['rule'] = deepcopy(p.ACCEPT_RULES[p.MAIN_V4])
    with pytest.raises(ValueError, match='exact Zebra pooled rule'):
        acceptance.schedule(p.record('acceptance-sealed', sealed['evidence'], changed))


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench'])
@pytest.mark.parametrize('train', [False, True])
def test_actual_engineer_dispatch_and_result_pin_keep_parent_prompt(bench, train):
    ctx, _ = context(configuration=p.MAIN_V2_3, bench='officeqa', mode='train' if train else 'single')
    ctx = replace(ctx, configuration=CHILD, bench=bench, routing_shared_worker=False,
                  card=z.CARD_TEXT if bench == z.BENCH else __import__('skillopt.execskill.instruction_start',fromlist=['pins']).pins()[bench]['text'])
    replies = ([engineer_reply({'findings': []}, [])] if train else []) + [engineer_reply({'changes': []}, [])]
    ctx.roles = WireRoles(replies)
    _, result = engineer.run_train(ctx) if train else engineer.run(ctx)
    expected = p.engineer_prompt(CHILD, bench, 'train' if train else 'single')
    assert result['prompt_sha256'] == hashlib.sha256(expected.encode()).hexdigest()
    request = next(row for row in ctx.roles.wire if row['label'].endswith('/propose'))
    assert request['system'] == expected
    if bench == z.BENCH:
        assert 'prompt_requests' not in result
        assert result['version'] == p.kind(p.ENGINEER_RECORDS[p.ZEBRA_PC_V13])
    else:
        assert result['prompt_requests'][0]['system_sha256'] == result['prompt_sha256']
    assert ctx.configuration == CHILD


def test_zebra_audit_public_view_and_templates_do_not_use_v211_qa_schema():
    view = {'question': 'Authored puzzle clues', 'columns': ['Name','Color'], 'context': 'not a Zebra field'}
    assert audit.public_view(z.BENCH, view, configuration=CHILD) == audit.public_view(z.BENCH,view,configuration=p.ZEBRA_PC_V13)
    proc = procedure('fx-v214-audit', ('applies','before_call'), origin=z.BENCH)
    extracted = {'templates': [], 'truncated': 0, 'always_check_truncated': 0, 'always_check_P2': []}
    assert audit.template_prompt(proc,z.BENCH,extracted,configuration=CHILD) == audit.template_prompt(proc,z.BENCH,extracted,configuration=p.ZEBRA_PC_V13)
    assert audit.situation_prompt([proc],z.BENCH,[],{},configuration=CHILD) == audit.situation_prompt([proc],z.BENCH,[],{},configuration=p.ZEBRA_PC_V13)


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_alfworld_step_five_uses_unchanged_import_without_learning_calls(tmp_path, monkeypatch, chain):
    setting = SimpleNamespace(root=tmp_path, evidence='engineering_fixture',
        extra={'configuration':CHILD,'alfworld_v11_import':v210_import.pins()})
    parent = empty(step=chain+'/s4-spreadsheetbench', evidence=setting.evidence)
    for name in ('_slices','_run','_diagnose','_generate','_trained','_accept','_freeze'):
        monkeypatch.setattr(step,name,lambda *args,**kwargs: pytest.fail('Import must not learn'))
    result = step.run_step(setting,chain,'alfworld',5,parent,services=None)
    assert result.record['learning'] == result.record['decision'] == 'import'
    assert result.package.order == tuple(row[0] for row in v210_import.PROCEDURES)
    assert result.record['units'] == {}
    assert result.package.sha256 != parent.sha256
    assert step.run_step(setting,chain,'alfworld',5,parent,services=None) == result
