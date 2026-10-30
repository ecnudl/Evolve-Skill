"""main-v4 full independent C and pooled selection; synthetic cells only."""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
import functools

import pytest

from skillopt.execskill import acceptance as a, profiles as p, reuse, stats_ext
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import make_cells
from tests.test_execskill_v23_acceptance_amendment import amend, physical


@pytest.fixture(autouse=True)
def authored_statistics(monkeypatch):
    monkeypatch.setattr(stats_ext, 'bootstrap_ci', functools.partial(stats_ext.bootstrap_ci, resamples=40))
    monkeypatch.setattr(stats_ext, 'signflip', functools.partial(stats_ext.signflip, n=128))


def seal(root, bench='officeqa', *, card_parent=True, dup=False, probe=False, reuse_plan=False, deletion=False):
    from skillopt.execskill.instruction_start import pins
    parent = empty(step='D/s0', evidence='engineering_fixture')
    old = procedure('fx-v211-parent', ('applies', 'before_call'), origin=bench)
    new = procedure('fx-v211-added', ('applies', 'before_call'), origin=bench)
    if not card_parent:
        parent = with_(parent, step='D/s0', add=[old])
    candidate = with_(parent, step='D/s1-' + bench, add=[new], remove=[old.id] if deletion else ())
    hooks = {proc.id: {'applies': lambda view: True,
        'before_call': lambda view, state: {'facts': ['The public input was inspected.']}} for proc in (old, new)}
    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hooks).start(package, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    count, runs = p.slice_spec(p.MAIN_V4, bench)['accept']
    items = ['authored-%04d' % i for i in range(count)]
    view = {'question': 'What is the public value?', 'context': ['The public value is 7.']}
    if bench == 'livemath':
        view = {'question': 'Compute 2 + 5.', 'choices': {'A': '6', 'B': '7', 'C': '8'}}
    if bench == 'spreadsheetbench':
        view = {'instruction': 'Copy the public value.', 'workbook_preview': [], 'input_path': 'input.xlsx',
                'required_output_path': 'output.xlsx', 'required_answer_position': 'A1'}
    views = {key: dict(view) for key in items}
    blocks = {key: 'b%d' % (i // (count // 2) + 1 if bench == 'officeqa' else 1)
              for i, key in enumerate(items)}
    probes = ['probe-%04d' % i for i in range(64)] if probe else []
    reuse_args = {'card_text': pins()[bench]['text'], 'runtime': {'prompt_layout': 'contract-first-v2'},
                  'views': {'probe': {key: dict(view) for key in probes}}} if reuse_plan else None
    return a.prepare(root, chain='D', bench=bench, step='D/s1-' + bench, unit='D/s1-' + bench + '/accept',
        candidate=candidate, parent=parent, views=views, blocks=blocks, workers=workers, trajectories=[],
        configuration=p.MAIN_V4, rule=p.ACCEPT_RULES[p.MAIN_V4], dup=dup, probe=probes,
        freshness=p.ACCEPT_FRESHNESS[p.MAIN_V4], reuse=reuse_args)


@pytest.mark.parametrize('bench,cells,floor', [('searchqa', 1000, 30), ('officeqa', 128, 4),
    ('livemath', 200, 5), ('spreadsheetbench', 72, 3)])
@pytest.mark.parametrize('card_parent', [True, False])
def test_full_c_physical_schedule_on_every_astar_with_actual_request_signatures(bench, cells, floor, card_parent, tmp_path):
    sealed = seal(tmp_path, bench, card_parent=card_parent, reuse_plan=True)
    assert a.minimum_astar(sealed['rule'], len(sealed['A']), len(set(sealed['blocks'].values())))['items'] == floor
    plan = sealed['reuse']
    sample = plan['card_sample']
    assert sample['coverage'] == 'full_independent_astar'
    assert sample['items'] == sealed['plan']['astar']
    counts = Counter(job['arm'] for job in physical(sealed) if job['set'] == 'real')
    assert counts['C'] == cells
    for item in sealed['plan']['astar']:
        assert next(group for group in plan['classes']['real'][item] if 'C' in group['arms']) == {
            'representative': 'C', 'arms': ['C']}
        assert plan['reused'].get('real', {}).get(item, {}).get('C') is None
    assert not plan['identical_all'].get('real')
    assert {'P_y', 'P_i'}.isdisjoint(counts)
    assert reuse.from_signatures(sealed, plan['signatures']) == plan


@pytest.mark.parametrize('card_parent', [True, False])
def test_identical_class_forces_s_plus_independent_full_c_and_keeps_sdup(card_parent, tmp_path):
    old = seal(tmp_path, card_parent=card_parent, dup=True)
    sealed = amend(old, lambda job: 'same')
    assert Counter(job['arm'] for job in physical(sealed)) == {'S': 128, 'C': 128, 'S_dup': 128}
    assert sealed['reuse']['identical_all'] == {}
    assert all(row["S'"] == 'S' for row in sealed['reuse']['reused']['real'].values())
    found = a.decide(make_cells(sealed, token=lambda job: 'fail'), sealed)
    assert found['guards']['J1']['baseline'] == ('(S+C)/2' if card_parent else 'S')
    assert found['guards']['J2'] == {'removed': True}
    assert found['guards']['J3']['informational']
    assert found['guards']['J4_items']['compared_items'] == 0
    assert found['contrasts']["S'-S"]['whole_batch'] == 0
    if card_parent:
        assert found['contrasts']["S'-(S+C)/2"]['whole_batch'] == 0
    assert a.reproduce(make_cells(sealed, token=lambda job: 'fail'), sealed, found)


@pytest.mark.parametrize('card_parent', [True, False])
def test_pooled_vs_parent_gain_uses_exact_denominator_and_retained_guards(card_parent, tmp_path):
    sealed = seal(tmp_path, card_parent=card_parent)
    def token(job):
        n = int(job['item'].rsplit('-', 1)[1])
        bound = 16 if job['arm'] == 'S' else 18 if job['arm'] == 'C' else 18
        return 'pass' if n < bound else 'fail'
    cells = make_cells(sealed, token=token)
    found = a.decide(cells, sealed)
    assert found['guards']['J1']['whole_batch'] == float(Fraction(1 if card_parent else 2, 32))
    assert found['guards']['J1']['pooled'] is card_parent
    assert found['guards']['J1']['ok'] is (not card_parent)
    assert found['guards']['J2'] == {'removed': True}
    assert found['guards']['J3']['informational']
    assert found['guards']['J4_items']['ok']
    assert found['guards']['J5']['block_gap']['ok']
    assert found['guards']['J5']['block_gap']['required_s'] == 7200
    if card_parent:
        assert found['guards']['J6_dup']['pairs'][0]['pair'] == 'C-S'
        assert not found['contrasts']["S'-S"]['decides']
        assert not found['contrasts']["S'-C"]['decides']
        assert a.pooled_differences(a.table(cells), sealed['plan']['astar']) == [
            Fraction(0)] * 16 + [Fraction(1, 2)] * 2 + [Fraction(0)] * 14
    else:
        assert "S'-(S+C)/2" not in found['contrasts']
    assert a.reproduce(cells, sealed, found)


@pytest.mark.parametrize('points,pvalue,ok', [(Fraction(199, 100), .001, False),
    (Fraction(2), .05, True), (Fraction(2), .050001, False), (Fraction(5), 1., True)])
def test_searchqa_significance_alternative_remains_registered(points, pvalue, ok):
    first = {'whole_batch': float(points / 100), 'p_t': pvalue}
    j1, j2 = a._practical(p.ACCEPT_RULES[p.MAIN_V4], 'searchqa', [points * 10], [], 1000, first, None)
    assert j1['ok'] is ok and j2 == {'removed': True}
    j1_other, _ = a._practical(p.ACCEPT_RULES[p.MAIN_V4], 'officeqa', [points * 10], [], 1000, first, None)
    assert j1_other['ok'] is (points >= 5)


def test_j7_probe_and_acceptance_twins_stay_scheduled(tmp_path):
    sealed = seal(tmp_path, 'livemath', card_parent=False, probe=True, dup=True, reuse_plan=True, deletion=True)
    logical = [job for jobs in a.schedule(sealed, logical=True).values() for job in jobs]
    assert Counter(job['arm'] for job in logical if job['set'] == 'probe') == {"S'": 64, 'C': 64}
    assert any(job['arm'].startswith('withhold:') for job in logical)
    assert any(job['arm'].startswith('restore:') for job in logical)
    assert sum(job['arm'] == 'S_dup' for job in physical(sealed)) == 200
    found = a.decide(make_cells(sealed, token=lambda job: 'pass'), sealed)
    assert found['guards']['J7_meta'] is not None
    assert found['guards']['J7_meta']['ok']


@pytest.mark.parametrize('configuration', [name for name in p.CONFIGURATIONS if name != p.MAIN_V4 and not p.is_v214(name)])
def test_historical_configurations_cannot_select_the_new_rule(configuration):
    assert a._v211_rule(configuration, 'officeqa', p.ACCEPT_RULES[configuration]) is False
    with pytest.raises(ValueError, match='only to main-v4'):
        a._v211_rule(configuration, 'officeqa', p.ACCEPT_RULES[p.MAIN_V4])


@pytest.mark.parametrize('bench,rule', [('officeqa', None), ('officeqa', p.ACCEPT_RULES[p.MAIN_V3]),
    ('officeqa', {**p.ACCEPT_RULES[p.MAIN_V4], 'gain_points': 4}),
    ('alfworld', p.ACCEPT_RULES[p.MAIN_V4])])
def test_child_refuses_rule_or_benchmark_drift_before_any_work(bench, rule, tmp_path):
    with pytest.raises(ValueError, match='exact four-bench pooled rule'):
        a.prepare(tmp_path / 'no-write', chain='D', bench=bench, step='step', unit='unit',
            candidate=None, parent=None, views={}, blocks={}, workers=None, trajectories=[],
            configuration=p.MAIN_V4, rule=rule)
    assert not (tmp_path / 'no-write').exists()


def test_self_consistently_resealed_sample_cannot_weaken_full_c(tmp_path):
    sealed = seal(tmp_path, reuse_plan=True)
    damaged = deepcopy(sealed['reuse'])
    damaged['card_sample']['items'] = damaged['card_sample']['items'][:30]
    with pytest.raises(ValueError, match='full independent C'):
        a.with_reuse(sealed, damaged)
    damaged = deepcopy(sealed['reuse'])
    first = sealed['plan']['astar'][0]
    damaged['reused'].setdefault('real', {}).setdefault(first, {})['C'] = 'S'
    with pytest.raises(ValueError, match='full independent C'):
        a.with_reuse(sealed, damaged)


@pytest.mark.parametrize('guard', ['J3', 'J4', 'J6', 'J7'])
def test_retained_guards_act_on_their_original_parent_or_instrument(guard, tmp_path):
    bench = 'livemath' if guard == 'J7' else 'officeqa'
    sealed = seal(tmp_path, bench, probe=guard == 'J7')
    def token(job):
        if guard == 'J6':
            return 'fail' if job['arm'] == 'S' else 'pass'
        if job['set'] == 'probe':
            return 'pass' if job['arm'] == "S'" else 'fail'
        return 'pass' if job['arm'] == "S'" else 'fail'
    cells = make_cells(sealed, token=token,
        violation=lambda job: guard == 'J4' and job['arm'] == "S'",
        faults=lambda job: [{'procedure': 'fx-v211-added', 'hook': 'before_call', 'kind': 'output_shape'}]
            if guard == 'J3' and job['arm'] == "S'" else [])
    found = a.decide(cells, sealed)
    assert found['guards']['J1']['ok'] and found['guards']['J2'] == {'removed': True}
    if guard == 'J3':
        assert not found['guards']['J3']['ok'] and found['guards']['J3']['informational']
        assert found['decision'] == 'accept'
    elif guard == 'J4':
        assert found['guards']['J4_items']["S'"] == 32 and found['guards']['J4_items']['S'] == 0
        assert not found['guards']['J4_items']['ok'] and found['decision'] == 'reject'
    elif guard == 'J6':
        assert found['guards']['J6_dup']['pairs'][0]['pair'] == 'C-S'
        assert not found['guards']['J6_dup']['ok'] and found['decision'] == 'undetermined'
    else:
        assert found['guards']['J7_meta']['n'] == 64
        assert not found['guards']['J7_meta']['ok'] and found['decision'] == 'reject'
