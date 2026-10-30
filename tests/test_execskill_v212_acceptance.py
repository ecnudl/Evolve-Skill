"""v2.12 pooled Zebra selection and independent C; authored offline cells only."""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
import functools
from types import SimpleNamespace

import pytest

from skillopt.execskill import acceptance as a, profiles as p, reuse, stats_ext, zebralogic
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import make_cells
from tests.test_execskill_v23_acceptance_amendment import amend, physical
from tests.test_execskill_zpc_pipeline import fixture_pool

CHILD = 'zebra-pc-v13'
POOLED = "S'-(S+C)/2"


@pytest.fixture(autouse=True)
def authored_statistics(monkeypatch):
    monkeypatch.setattr(stats_ext, 'bootstrap_ci', functools.partial(stats_ext.bootstrap_ci, resamples=40))
    monkeypatch.setattr(stats_ext, 'signflip', functools.partial(stats_ext.signflip, n=128))


def seal(root, *, configuration=CHILD, reuse_plan=True, with_packages=False, two=False):
    parent = empty(step='D/s0', evidence='engineering_fixture')
    added = [procedure('fx-v212-' + name, ('applies', 'before_call'), origin='zebralogic')
             for name in (('added', 'second') if two else ('added',))]
    candidate = with_(parent, step='D/s1-zebralogic', add=added)
    hooks = {proc.id: {'applies': lambda view: True,
                       'before_call': lambda view, state: {'facts': ['Inspect all public clues.']}} for proc in added}
    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hooks).start(package, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    tasks = fixture_pool()[:100]
    views = {task['task_id']: task['public'] for task in tasks}
    trajectories = ([{'bench': 'zebralogic', 'arm_kind': 'parent', 'cell': 'donor-' + task['task_id'],
        'task_id': task['task_id'], 'calls': [{'purpose': 'first', 'user': zebralogic.render_user(task['public'])}],
        'shell': {}} for task in tasks[:10]] if configuration != CHILD else [])
    sealed = a.prepare(root, chain='D', bench='zebralogic', step='D/s1-zebralogic',
        unit='D/s1-zebralogic/accept', candidate=candidate, parent=parent, views=views,
        blocks={key: 'b1' for key in views}, workers=workers, trajectories=trajectories,
        configuration=configuration, rule=p.ACCEPT_RULES[configuration],
        freshness=p.ACCEPT_FRESHNESS[configuration],
        reuse={'card_text': zebralogic.CARD_TEXT, 'runtime': {}} if reuse_plan else None)
    if with_packages:
        return sealed, a.round_packages(candidate, parent, step=sealed['step'],
                                       twins=sealed['plan']['twins'], configuration=configuration)
    return sealed


def reseal(value, **changes):
    fields = {key: item for key, item in value.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    return p.record('acceptance-sealed', value['evidence'], {**fields, **changes})


def test_every_astar_card_cell_is_independent_even_for_identical_requests(tmp_path):
    sealed = seal(tmp_path)
    plan = sealed['reuse']
    sample = plan['card_sample']
    assert sample['items'] == sealed['plan']['astar'] and len(sample['items']) == 100
    assert sample['coverage'] == 'full_independent_astar'
    assert sample['tag'].endswith(':full-independent-C-v212')
    assert sealed['card_is_parent'] and sealed['j6_registered'] is True
    assert sealed['corpus'] is sealed['placebo_y'] is sealed['placebo_i'] is None
    assert sealed['seals']['donor_corpus'] is None
    assert set(sealed['packages']) == {'candidate', 'parent', 'card'}
    assert Counter(job['arm'] for job in physical(sealed))['C'] == 100
    for item in sample['items']:
        assert plan['signatures']['real'][item]['S']['request_sha256'] == plan['signatures']['real'][item]['C']['request_sha256']
        assert next(group for group in plan['classes']['real'][item] if 'C' in group['arms']) == {
            'representative': 'C', 'arms': ['C']}
        assert plan['reused'].get('real', {}).get(item, {}).get('C') is None
    assert not plan['identical_all'].get('real')
    assert reuse.from_signatures(sealed, plan['signatures']) == plan
    all_same = amend(sealed, lambda job: 'same')
    assert Counter(job['arm'] for job in physical(all_same)) == {'S': 100, 'C': 100}
    assert all_same['reuse']['identical_all'] == {}
    assert all(row["S'"] == 'S' for row in all_same['reuse']['reused']['real'].values())


def test_runner_dispatches_distinct_s_and_c_cells_for_every_identical_item(tmp_path, monkeypatch):
    sealed, packages = seal(tmp_path / 'sealed', with_packages=True)
    sealed = amend(sealed, lambda job: 'same')
    dispatched = []
    monkeypatch.setattr(a, 'run_parallel', lambda fn, entries, workers: [fn(entry) for entry in entries])
    def record(context, cell, task, arm, store):
        dispatched.append(cell)
        return cell
    monkeypatch.setattr(a, 'run_cell', record)
    tasks = {item: {'public': {}, 'private': {}} for item in sealed['plan']['astar']}
    runner = a.runner(SimpleNamespace(attempt=tmp_path / 'attempt-1'), sealed, packages, tasks, workers=1, store=None)
    for block, jobs in a.schedule(sealed).items():
        runner(block, jobs)
    assert Counter(cell['arm'] for cell in dispatched) == {'S': 100, 'C': 100}
    assert len({cell['id'] for cell in dispatched}) == 200
    for item in sealed['plan']['astar']:
        assert {cell['arm'] for cell in dispatched if cell['task_id'] == item} == {'S', 'C'}


@pytest.mark.parametrize('card_success,accepted', [(80, True), (84, False)])
def test_independent_c_changes_exact_pooled_j1_and_paired_statistics(card_success, accepted, tmp_path):
    sealed = seal(tmp_path)
    index = {item: n for n, item in enumerate(sealed['plan']['astar'])}
    def token(job):
        bound = 80 if job['arm'] == 'S' else card_success if job['arm'] == 'C' else 86
        return 'pass' if index[job['item']] < bound else 'fail'
    cells = make_cells(sealed, token=token)
    result = a.decide(cells, sealed)
    table = a.table(a.expanded_cells(cells, sealed))
    difference = a.pooled_differences(table, sealed['plan']['astar'])
    assert all(type(value) is Fraction for value in difference)
    assert sum(difference) == Fraction(2 * 86 - 80 - card_success, 2)
    assert result['guards']['J1']['whole_batch'] == float(sum(difference) / 100)
    assert result['guards']['J1']['rule'] == 'practical-v2-12-pooled'
    assert result['guards']['J1']['baseline'] == '(S+C)/2'
    assert result['guards']['J1']['pooled'] and result['guards']['J1']['ok'] is accepted
    assert result['guards']['J1']['gain_points'] == 5
    assert result['contrasts'][POOLED] == a.contrast(difference,
        design=a._design(sealed, sealed['plan']['astar']), whole=100, sensitivity=True)
    assert result['guards']['J1']['p_t'] == result['contrasts'][POOLED]['p_t']
    assert result['contrasts']["S'-S"]['whole_batch'] == .06
    assert not result['contrasts']["S'-S"]['decides'] and not result['contrasts']["S'-C"]['decides']
    assert result['contrasts']['S-C']['sample'] == 'full_independent_C'
    assert result['contrasts']['S-C']['whole_batch'] == float(Fraction(80 - card_success, 100))
    assert result['guards']['J2'] == {'removed': True}
    assert result['guards']['J3']['informational'] and result['guards']['J4_items']['ok']
    assert result['guards']['J5']['ok'] and result['guards']['J6_dup']['ok']
    assert result['guards']['J6_dup']['pairs'][0]['sample_size'] == 100
    assert result['guards']['J6_dup']['pairs'][0]['pair'] == 'C-S'
    assert result['guards']['J7_meta'] is None
    assert result['decision'] == ('accept' if accepted else 'reject')
    assert a.reproduce(cells, sealed, result)


@pytest.mark.parametrize('total,size,ok', [(Fraction(9, 2), 100, False), (Fraction(5), 100, True),
                                         (Fraction(5), 101, False)])
def test_practical_bar_uses_exact_whole_batch_denominator(total, size, ok):
    j1, j2 = a._practical(p.ACCEPT_RULES[CHILD], 'zebralogic', [total], [], size,
                         {'whole_batch': float(total / size), 'p_t': 1.0}, None)
    assert j1['ok'] is ok and not j1['significant']
    assert j2 == {'removed': True}


@pytest.mark.parametrize('guard', ['J3', 'J4', 'J6'])
def test_retained_guards_keep_parent_semantics(guard, tmp_path):
    sealed = seal(tmp_path)
    cells = make_cells(sealed,
        token=lambda job: 'fail' if job['arm'] == 'S' or (job['arm'] == 'C' and guard != 'J6') else 'pass',
        violation=lambda job: guard == 'J4' and job['arm'] == "S'",
        faults=lambda job: [{'procedure': 'fx-v212-added', 'hook': 'before_call', 'kind': 'output_shape'}]
            if guard == 'J3' and job['arm'] == "S'" else [])
    result = a.decide(cells, sealed)
    assert result['guards']['J1']['ok']
    if guard == 'J3':
        assert not result['guards']['J3']['ok'] and result['guards']['J3']['informational']
        assert result['decision'] == 'accept'
    elif guard == 'J4':
        assert result['guards']['J4_items']["S'"] == 100 and result['guards']['J4_items']['S'] == 0
        assert result['guards']['J4_items']['margin'] == 2
        assert result['decision'] == 'reject'
    else:
        assert not result['guards']['J6_dup']['ok'] and p.DUP_ALPHA == .01
        assert result['decision'] == 'undetermined'


@pytest.mark.parametrize('damage', ['sample', 'reuse', 'j6'])
def test_resealed_plan_cannot_weaken_full_c_or_duplicate_check(damage, tmp_path):
    sealed = seal(tmp_path)
    plan = deepcopy(sealed['reuse'])
    if damage == 'j6':
        with pytest.raises(ValueError, match='requires the C-S duplicate test'):
            a.schedule(reseal(sealed, j6_registered=False))
        return
    if damage == 'sample':
        plan['card_sample']['items'] = plan['card_sample']['items'][:30]
    else:
        plan['reused'].setdefault('real', {}).setdefault(sealed['plan']['astar'][0], {})['C'] = 'S'
    with pytest.raises(ValueError, match='full independent C'):
        a.with_reuse(sealed, plan)


@pytest.mark.parametrize('bench,rule', [('zebralogic', None), ('zebralogic', 'parent'), ('officeqa', 'child')])
def test_rule_or_benchmark_drift_is_rejected_before_any_work(bench, rule, tmp_path):
    chosen = None if rule is None else p.ACCEPT_RULES['zebra-pc-v12' if rule == 'parent' else CHILD]
    with pytest.raises(ValueError, match='exact Zebra pooled rule'):
        a.prepare(tmp_path / 'no-write', chain='D', bench=bench, step='step', unit='unit',
            candidate=None, parent=None, views={}, blocks={}, workers=None, trajectories=[],
            configuration=CHILD, rule=chosen)
    assert not (tmp_path / 'no-write').exists()


@pytest.mark.parametrize('configuration', [name for name in p.CONFIGURATIONS if name != CHILD])
def test_older_configuration_cannot_select_v212_rule(configuration):
    assert a._v212_rule(configuration, 'zebralogic', p.ACCEPT_RULES.get(configuration)) is False
    with pytest.raises(ValueError, match='only to zebra-pc-v13'):
        a._v212_rule(configuration, 'zebralogic', p.ACCEPT_RULES[CHILD])


def test_v12_keeps_shared_c_no_j6_and_placebo(tmp_path):
    sealed = seal(tmp_path, configuration='zebra-pc-v12')
    assert sealed['j6_registered'] is False
    assert sealed['reuse']['card_sample'] is None
    assert sealed['placebo_y'] is not None and sealed['corpus'] is not None
    assert all(row['C'] == 'S' for row in sealed['reuse']['reused']['real'].values())
    assert not any(job['arm'] == 'C' for job in physical(sealed))


def test_acceptance_withholding_twins_keep_v12_plan(tmp_path):
    parent = seal(tmp_path / 'parent', configuration='zebra-pc-v12', two=True)
    child = seal(tmp_path / 'child', two=True)
    assert child['plan']['twins'] == parent['plan']['twins']
    assert child['plan']['twin_priority'] == parent['plan']['twin_priority']
    assert child['plan']['twins']
    assert any(job['arm'].startswith('withhold:')
               for jobs in a.schedule(child, logical=True).values() for job in jobs)
