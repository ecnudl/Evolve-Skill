"""Full practice S2 with authored cells, production gates and a fake writer."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.validator_pilot.api import digest
from skillopt.execskill import profiles as p, units, rounds, v214_smoke, v214_stages, v222_cards, v222_smoke
from skillopt.execskill import v225_cards as cards, v225_smoke as smoke, v225_writer, v225_phase, v222_gate
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v225_writer import FakeRoles
from tests.test_execskill_v225_routing import VIEWS
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401


def authored_s2(root, monkeypatch, chain, *, cross_card_accept=True):
    pools = {bench: [{'task_id': f'{bench}-{i:03d}', 'benchmark': bench, 'partition': 'practice',
        'public': deepcopy(VIEWS[bench]), 'private': {'answers': ['Authored reference']} if bench == 'searchqa' else {}}
        for i in range(42 if bench == 'officeqa' else 20)] for bench in p.MAIN_V5_ORDER}
    harms = v222_gate.harm_slices(pools, configuration=p.MAIN_V9)
    registration = {'smoke_practice_draws': v222_cards.decomposition_slices({b: [r['task_id'] for r in rows] for b, rows in pools.items()}),
        'harm': v222_gate.registration(harms, configuration=p.MAIN_V9),
        v222_smoke.SUPPLY_FLAG: v222_gate.practice_supply(pools)}
    setting = units.Setting(run=digest(['authored-v225', chain, cross_card_accept]), root=root, shared=root/'shared',
        pools=pools, cards={b: v222_cards.format_text(b) for b in p.MAIN_V5_ORDER}, runtime={b: {} for b in p.MAIN_V5_ORDER},
        clients=None, budget=None, slots={}, sandbox={}, evidence='engineering_fixture',
        extra={'configuration': p.MAIN_V9, 'v222_practice': registration})
    monkeypatch.setattr(v222_smoke, 'practice', lambda _: (deepcopy(pools), deepcopy(harms), deepcopy(registration)))
    monkeypatch.setattr(v222_smoke, 'decomposition', lambda *_: pytest.fail('Main-v9 never decomposes cards'))
    monkeypatch.setattr(v222_smoke, '_endpoint', lambda *_: None)
    monkeypatch.setattr(v222_smoke, '_workers', lambda *_: lambda *args: nullcontext(None))
    monkeypatch.setattr(v214_stages, 'fixture_pools', lambda *_: {b: rows[:v214_smoke.S2_ITEMS[b]] for b, rows in pools.items()})
    roles = FakeRoles(['Compare the supplied evidence carefully.'])
    monkeypatch.setattr(units, 'role_endpoint', lambda *args: None)
    monkeypatch.setattr(smoke, 'probe_endpoint', lambda *args, **kwargs: None)
    monkeypatch.setattr(units, 'roles', lambda *args, **kwargs: roles)
    sent = []
    def inspection(bench, before, after, items, *args, **kwargs):
        def signature(package):
            own = package.card_for(bench)
            procs = [r.sha256 for r in package.for_bench(bench)] if bench == 'officeqa' else []
            return {'request_sha256': digest([procs, cards.metadata(own)['text'] if own else '']),
                    'post_call': [], 'faults': []}
        pairs = {r['task_id']: {'S': signature(before), "S'": signature(after)} for r in items}
        fired = [key for key, pair in pairs.items() if pair['S'] != pair["S'"]]
        return {'bench': bench, 'items': len(items), 'slice_ids': list(pairs), 'fired': len(fired), 'fired_items': fired,
            'faults': [], 'identity_proven': not fired, 'signatures': pairs,
            'parent_sha256': before.sha256, 'candidate_sha256': after.sha256}
    monkeypatch.setattr(v222_gate, 'inspect', inspection)
    def run(local, attempt, endpoint, unit, arms, schedule, tasks, *, tag):
        found = {}
        for arm, jobs in schedule.items():
            for key, _ in jobs:
                bench = rounds.bench_of(key)
                n = int(key.rsplit('-', 1)[1])
                token = 'pass'
                if '/cross-narrowing/' in unit:
                    assert not any(proc for proc in arms['S'].package.procedures) if 'S' in arms else True
                    if '/harmful_format/' in unit:
                        token = 'fail' if arm == "S'" else 'pass'
                    elif n < 3:
                        token = 'fail' if arm == 'S' else 'pass'
                    elif n < 5:
                        token = 'pass' if arm == 'S' else 'fail'
                elif '/card-probe/cross' in unit:
                    pos = list(tasks).index(key)
                    if cross_card_accept and pos < 5:
                        token = 'fail' if arm == 'S' else 'pass'
                    elif cross_card_accept and pos < 7:
                        token = 'pass' if arm == 'S' else 'fail'
                elif '/card-probe/home' in unit:
                    token = 'fail' if arm == 'S' and n < 5 else 'pass'
                elif arm == 'C0' and n < 12:
                    token = 'fail'
                enabled = [proc.id for proc in arms[arm].package.for_bench(bench)]
                payload = {'cell': {'id': digest([unit, arm, key]), 'unit': unit, 'benchmark': bench,
                    'arm': arm, 'task_id': key, 'run': 0}, 'stop': None, 'faults': [], 'enabled': enabled,
                    'sends': [{'request_bytes': 1000, 'charged': 150, 'receipt': {'usage': {'prompt_tokens': 80, 'completion_tokens': 20}}}],
                    'final': {'token': token, 'outcome': token, 'kind': 'authored_answer', 'remedy': None},
                    'judge': {'v2': {'token': token}, 'format': {'grid' if bench == 'zebralogic' else 'violation'
                        if bench == 'alfworld' else v222_smoke.COUNTERS[bench]: bench != 'alfworld'}}}
                cell = p.record('cell', 'engineering_fixture', payload)
                write_json(Path(attempt)/'cells'/(cell['cell']['id']+'.json'), cell)
                if '/price/searchqa/C0' in unit:
                    trace = p.record('trajectory', 'engineering_fixture', {'cell': cell['cell']['id'], 'unit': unit,
                        'arm': arm, 'arm_kind': 'card', 'bench': bench, 'task_id': key, 'run': 0, 'token': token,
                        'calls': [{'purpose': 'first', 'user': '{"question": "An authored question", "context": "An authored snippet"}'}],
                        'replies': ['An authored answer'], 'deciding_receipt': 0})
                    write_json(Path(attempt)/'trajectories'/(cell['cell']['id']+'.json'), trace)
                sent.append((unit, arm, key))
                found[(arm, key)] = [cell]
        return found
    monkeypatch.setattr(rounds, 'run_round', run)
    return setting, registration, sent, roles


@pytest.mark.parametrize('chain', ['G', 'D'])
@pytest.mark.parametrize('cross_card_accept', [True, False])
def test_s2_writes_card_exercises_both_cross_cases_prices_four_arms_without_decomposition(
        tmp_path, monkeypatch, chain, cross_card_accept):
    setting, registered, sent, roles = authored_s2(tmp_path/'fresh', monkeypatch, chain, cross_card_accept=cross_card_accept)
    value = smoke.s2(setting, chain)
    assert smoke.check_bound_practice(value, registered) == value
    assert value['passed'] and value['v222_fallbacks'] == {} and value['sealed_reads'] == 0
    assert set(value['cross_narrowing']['cases']) == {'harmful_format', 'benign'}
    assert value['cross_narrowing']['paired_item_calls'] == 168
    assert value['cross_narrowing']['cases']['harmful_format']['narrowing_exercised'] is True
    assert value['cross_narrowing']['cases']['benign']['narrowing_exercised'] is False
    assert value['card_probe']['writer_calls'] == 1 and len(roles.calls) == 1
    assert value['card_probe']['solver_cells'] == 60
    assert value['card_probe']['cross_card']['gate']['passed'] is cross_card_accept
    assert value['card_probe']['home']['decision'] == 'accept'
    assert len(sent) == 4*sum(v214_smoke.S2_ITEMS.values())+168+60 == 532
    assert len(set(sent)) == len(sent)
    assert len(list(setting.root.rglob('unit.json'))) == 8
    for bench, row in value['benches'].items():
        assert row['passed'] and row['cells'] == 4*row['items']
        assert set(row['arms']) == {'B','C0','C','P'}
        assert row['arms']['P']['measurements']['per_class'][bench]['procedure']['cells'] == row['items']
    # Completed units do not make another writer request or solver dispatch.
    monkeypatch.setattr(rounds, 'run_round', lambda *_a, **_k: pytest.fail('Complete S2 units must resume without calls'))
    assert smoke.s2(setting, chain) == value


def test_price_packages_pin_maximal_card_and_actual_alf_import_without_card():
    from skillopt.execskill import v210_import
    for bench in p.MAIN_V5_ORDER:
        pkg = smoke.price_package(bench, 'G', 'engineering_fixture')
        assert pkg.for_bench(bench)
        if bench == 'alfworld':
            assert pkg.card_for(bench) is None
            assert [proc.source for proc in pkg.procedures] == [row['record']['source'] for row in v210_import.pins()['procedures']]
        else:
            assert len(cards.metadata(pkg.card_for(bench))['text']) == 3000
            assert pkg.for_bench(bench)[0].source == smoke.PRICE_SOURCE


def test_se6_uses_four_card_and_six_procedure_arms_with_actual_measured_prices(tmp_path, monkeypatch):
    from fractions import Fraction
    from skillopt.execskill import v225_read
    setting, _, _, _ = authored_s2(tmp_path/'projection', monkeypatch, 'G')
    value = smoke.s2(setting, 'G')
    bounds = v214_smoke.solver_bounds('G', configuration=p.MAIN_V9)
    result = smoke.projection(value, 'G', s3={'passed': True, 'engineer_calls': 1, 'tokens': 200}, bounds=bounds)
    assert result['passed'] and result['stage_packages'] == 5
    assert all(row['card'] == row['procedure'] == '100' and row['procedure_assumed'] is False
               for row in result['per_cell'].values())
    terms = v225_read.estimate_unit_terms({b: {'card': Fraction(100), 'procedure': Fraction(100)} for b in p.MAIN_V5_ORDER}, Fraction(3,2))
    assert result['read_terms'] == {k: str(v) for k,v in terms.items()}
    assert result['read_estimate'] == sum(terms.values())


def test_s0_pins_writer_policy_template_task_cards_and_ten_read_arms():
    from skillopt.execskill import policy
    pins = smoke.pins({b: {} for b in p.MAIN_V5_ORDER})
    assert pins['prompts'] == cards.prompt_pins()
    assert pins['card_policy'] == policy.POLICY_V225
    assert pins['card_policy_sha256'] == policy.policy_sha256(version=policy.POLICY_VERSION_V225)
    assert pins['read_arms'] == ['B','C0','C','S1','S2','S3','S4','S5','I','C_end']
    assert len(pins['task_cards']) == 4 and pins['fresh_reads'] and pins['overlapped_reads']
    assert pins['constants']['gain_share'] == '1/20'
    assert pins['price_card_sha256'] == cards.sha256(smoke.PRICE_CARD)


def test_smoke_writer_preserves_c0_provenance_and_cannot_be_used_by_learner():
    trace = p.record('trajectory', 'engineering_fixture', {'unit': 'G/v225-smoke/price/searchqa/C0',
        'arm': 'C0', 'bench': 'searchqa', 'task_id': 'practice-1', 'run': 0, 'token': 'pass',
        'calls': [{'purpose':'first','user':'A public view'}], 'replies':['A reply'], 'deciding_receipt':0})
    kwargs = {'chain':'G','bench':'searchqa','k':1,'c':1,'references':{},'allowed_ids':['practice-1']}
    with pytest.raises(ValueError, match='practice run/card-train'):
        v225_writer.select_examples([trace], **kwargs)
    assert len(v225_writer.select_examples([trace], smoke=True, incumbent_evidence='engineering_fixture', **kwargs)) == 1
    with pytest.raises(ValueError, match='reserved SearchQA C0'):
        v225_writer.select_examples([{**trace,'arm':'C'}], smoke=True, incumbent_evidence='engineering_fixture', **kwargs)


def test_sx_real_card_controller_precedes_procedure_rounds_and_all_authored_read_plans(tmp_path, fast_statistics):
    result = smoke.structural_smoke(tmp_path/'sx')
    assert smoke.check_structural(result) == result
    controller = result['card_phase']
    assert controller['units'][:4] == ['card-write-c1','card-train-c1','card-confirm-c1','card-accept-c1']
    assert 'card-cross-officeqa' in controller['units']
    assert controller['writer_calls_authored'] == 1 and controller['consumed_acceptance'] == 100
    assert controller['procedure_round_count'] == 6 and controller['patience'] == 4
    assert all(row['items'] == 300 and row['source'] == 'card-train-c1' for row in controller['procedure_rounds'])
    edges = result['card_edges']
    assert edges['scenarios']['static']['rounds'][0]['decision'] == 'card_rejected_static'
    assert edges['scenarios']['all_training']['consumed_acceptance'] == 0
    assert edges['scenarios']['confirmation']['consumed_acceptance'] == 140
    assert edges['scenarios']['acceptance']['consumed_acceptance'] == 200
    assert edges['scenarios']['exhausted']['procedure_phase'] == 'skipped_pool_exhausted'
    assert edges['scenarios']['cross_reject']['cross_cards'][0]['gate']['passed'] is False
    assert {b:r['consumed_acceptance'] for b,r in edges['supply'].items()} == {
        'officeqa':32,'zebralogic':40,'spreadsheetbench':36}
    plans = result['read_plans']
    assert len(plans['units']) == 40 and plans['fresh_cells'] == plans['logical_cells'] == 50
    assert all(source is None for unit in plans['units'] for row in unit['sources'].values() for source in row.values())
    assert result['readout']['authored_cells'] == 300 and result['readout']['anchor_C_equal'] is True
    assert result['readout']['same_text_steps'] == [1,3,5]
    assert result['readout']['C_end'] == 'descriptive_only'


def test_measured_readiness_rejects_corrupted_card_cross_and_price_receipts(tmp_path, monkeypatch):
    setting, _, _, _ = authored_s2(tmp_path/'bound', monkeypatch, 'G')
    value = smoke.s2(setting, 'G')
    corruptions = [
        lambda row: row['card_probe'].__setitem__('delivered', False),
        lambda row: row['card_probe'].__setitem__('solver_cells', 59),
        lambda row: row['card_probe']['home'].__setitem__('fixed', 1),
        lambda row: row['cross_narrowing'].__setitem__('paired_item_calls', 0),
        lambda row: row['cross_narrowing']['cases']['benign'].__setitem__('probe_source_sha256', '0'*64),
        lambda row: row['benches']['officeqa']['arms']['P'].__setitem__('package_sha256', '0'*64),
        lambda row: row['benches']['zebralogic']['arms']['C0']['measurements'].__setitem__('actual', 0),
        lambda row: row['benches']['alfworld']['arms']['B'].__setitem__('cell_sha256',
            row['benches']['alfworld']['arms']['C0']['cell_sha256']),
    ]
    for corrupt in corruptions:
        broken = deepcopy(value)
        corrupt(broken)
        with pytest.raises(ValueError):
            smoke.check_measured(broken)


@pytest.mark.parametrize('writer,cap', [(False,1_000_000),(True,1_839_360)])
def test_probe_endpoints_add_exact_ledger_cap_and_refuse_overspend(tmp_path, monkeypatch, writer, cap):
    from skillopt.coevo5.budget import Budget
    from skillopt.execskill.errors import BudgetStop
    budget = Budget(tmp_path/'ledger')
    total = 'G:glm' if writer else 'G:solver'
    scopes = ('overall',total)
    budget.declare({scope:10_000_000 for scope in scopes})
    original = SimpleNamespace(scopes=scopes)
    monkeypatch.setattr(units, 'role_endpoint', lambda *_args: original)
    monkeypatch.setattr(v222_smoke, '_endpoint', lambda *_args: original)
    endpoint = smoke.probe_endpoint(SimpleNamespace(budget=budget), 'G','searchqa',writer=writer)
    scope = 'G:v225-smoke:card-probe:'+('method' if writer else 'solver')
    assert endpoint.scopes == scopes+(scope,) and original.scopes == scopes
    assert budget.snapshot()[scope]['cap'] == cap
    token = budget.reserve(endpoint.scopes,cap,label='authored-entire-cap',generation=budget.generation())
    budget.settle(token,cap,detail={'evidence':'engineering_fixture'})
    with pytest.raises(BudgetStop):
        budget.reserve(endpoint.scopes,1,label='authored-over-cap',generation=budget.generation())


def test_dispatch_limits_are_durable_and_checked_before_calls(tmp_path, monkeypatch):
    from skillopt.execskill.errors import BudgetStop
    roles = FakeRoles(['An authored valid reply.']*4)
    wrapped = smoke.ProbeWriter(roles,tmp_path/'probe','engineering_fixture')
    for index in range(3):
        wrapped.plain('card_writer','system','user',label=str(index),max_tokens=32768)
    with pytest.raises(BudgetStop,match='writer dispatch cap'):
        smoke.ProbeWriter(roles,tmp_path/'probe','engineering_fixture').plain(
            'card_writer','system','user',label='fourth',max_tokens=32768)
    assert len(roles.calls) == 3
    smoke.reserve_probe_dispatch(tmp_path/'probe','solver',60,evidence='engineering_fixture')
    setting = SimpleNamespace(extra={'configuration':p.MAIN_V9,
        'v225_smoke_probe_root':str(tmp_path/'probe')},evidence='engineering_fixture')
    monkeypatch.setattr(rounds,'cell_context',lambda *_:pytest.fail('A rejected dispatch cannot construct cells'))
    from skillopt.execskill.cells import Arm
    from skillopt.execskill.package import empty
    with pytest.raises(BudgetStop,match='solver dispatch cap'):
        rounds.run_round(setting,tmp_path/'attempt-1',None,'G/v225-smoke/card-probe/home',
            {'S':Arm('parent',empty(step='G/s0',evidence='engineering_fixture'))},
            {'S':[('searchqa/authored',1)]},{'searchqa/authored':{'public':{},'private':{}}},tag='authored')
