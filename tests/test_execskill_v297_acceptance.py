"""Exact pooled ALF baseline arithmetic and synthetic design-based decisions; offline only."""
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
import functools
import hashlib
import itertools
import json
from pathlib import Path

import pytest

from skillopt.execskill import acceptance as a, profiles as p, stats_ext
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import make_cells

CHILD, PARENT = 'alfworld-v11', 'alfworld-v10'
POOLED = "S'-(S+C)/2"
FIXTURE = Path(__file__).parent / 'fixtures/execskill/v297_alf10_acceptance_outcomes.json'
FIXTURE_SHA256 = '896fc9f33b5372f39832ed31a3a90c695cec1b8c676401d461ca64b122de64ef'


@pytest.fixture(autouse=True)
def authored_resamples(monkeypatch):
    """Only authored CI/sensitivity test work is shortened; design and gate are unchanged."""
    monkeypatch.setattr(stats_ext, 'bootstrap_ci', functools.partial(stats_ext.bootstrap_ci, resamples=80))
    monkeypatch.setattr(stats_ext, 'signflip', functools.partial(stats_ext.signflip, n=256))


def seal(root, configuration=CHILD, *, card_is_parent=True, rule=None):
    parent = empty(step='D/s0', evidence='engineering_fixture')
    old = procedure('fx-alf-pooled-parent', ('applies', 'alf_before_step'), origin='alfworld')
    new = procedure('fx-alf-pooled-added', ('applies', 'alf_before_step'), origin='alfworld')
    if not card_is_parent:
        parent = with_(parent, step='D/s0', add=[old])
    candidate = with_(parent, step='D/s1-alfworld', add=[new])
    hooks = {proc.id: {'applies': lambda view: True,
                      'alf_before_step': lambda view, state: {
                          'fields': {'facts': ['Authored observation.']}, 'discourage': []}}
             for proc in (old, new)}
    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hooks).start(package, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    items = ['authored-%02d' % i for i in range(60)]
    views = {key: {'task_text': 'Inspect the authored room.', 'initial_observation': 'Authored room.',
                   'admissible_commands_at_reset': ['look']} for key in items}
    rooms = {key: 'room-%02d' % (i // 5) for i, key in enumerate(items)}
    blocks = {key: 'block-%d' % (i // 15) for i, key in enumerate(items)}
    trajectories = [{'bench': 'alfworld', 'arm_kind': 'parent', 'cell': 'donor-%d' % i,
        'task_id': 'donor-%d' % i, 'calls': [{'purpose': 'step', 'user': json.dumps({
            'step': 0, 'initial_observation': 'Authored room.', 'observation': 'Authored room.',
            'admissible_commands': ['look']})}], 'alfworld_steps': [{'action': 'look'}], 'shell': {}}
        for i in range(12)]
    return a.prepare(root, chain='D', bench='alfworld', step='D/s1-alfworld', unit='D/s1-alfworld/accept',
        candidate=candidate, parent=parent, views=views, blocks=blocks, rooms=rooms, workers=workers,
        trajectories=trajectories, configuration=configuration, freshness=p.ACCEPT_FRESHNESS[configuration],
        rule=p.ACCEPT_RULES[configuration] if rule is None else rule)


def synthetic_cells(sealed, *, card_noisier=True):
    def token(job):
        n = int(job['item'].rsplit('-', 1)[1])
        if job['arm'] == "S'" or job['arm'].startswith(('withhold:', 'restore:')):
            passed = n < 34
        elif job['arm'] == 'C' and card_noisier:
            passed = 15 <= n < 51
        else:
            passed = n < 30
        return 'pass' if passed else 'fail'
    return make_cells(sealed, token=token)


def reseal(value, **changes):
    fields = {key: val for key, val in value.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    return p.record('acceptance-sealed', value['evidence'], {**fields, **changes})


def fixture_replay():
    """Replay arithmetic/J1 only: the real fixture has no room labels for new statistics."""
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    fixture = json.loads(FIXTURE.read_text())
    items = [row['task_id'] for row in fixture['items']]
    table = {(arm, row['task_id']): ['pass' if value else 'fail']
             for row in fixture['items'] for arm, value in row['outcomes'].items()}
    parent = a.differences(table, "S'", 'S', items)
    card = a.differences(table, "S'", 'C', items)
    pooled = a.pooled_differences(table, items)
    sham = a.differences(table, "S'", 'P_y', items)
    old_contrasts = fixture['recorded']['contrasts']
    old_j1, _ = a._practical(p.ACCEPT_RULES[PARENT], 'alfworld', parent, sham, len(items),
                             old_contrasts["S'-S"], old_contrasts["S'-P_y"])
    new_first = {'whole_batch': float(sum(pooled) / len(items)), 'p_t': None,
                 'ci95': None, 'sensitivity': None, 'statistics': 'unavailable_missing_room_labels'}
    new_j1, _ = a._practical(p.ACCEPT_RULES[CHILD], 'alfworld', pooled, sham, len(items),
                             new_first, old_contrasts["S'-P_y"])
    return fixture, table, items, parent, card, pooled, old_j1, new_j1, new_first


def test_real_fixture_replays_six_point_parent_gain_but_pooled_gain_fails_five_point_bar():
    fixture, table, items, parent, card, pooled, old_j1, new_j1, new_first = fixture_replay()
    assert len(items) == 150 and all(row['room'] is None for row in fixture['items'])
    assert {arm: sum(table[(arm, key)] == ['pass'] for key in items) for arm in ('S', 'C', 'P_y', "S'")} == {
        'S': 83, 'C': 93, 'P_y': 85, "S'": 92}
    assert sum(parent) == 9 and sum(card) == -1 and sum(pooled) == 4
    assert sum(parent) / len(items) == Fraction(3, 50)
    assert sum(pooled) / len(items) == Fraction(2, 75)
    assert old_j1 == fixture['recorded']['J1']
    assert new_j1['rule'] == a.POOLED_RULE_NAME and not new_j1['ok']
    assert new_j1['whole_batch'] == pytest.approx((92 - 88) / 150)
    assert new_j1['p_t'] is None and new_first['statistics'] == 'unavailable_missing_room_labels'
    assert fixture['recorded']['J6_dup']['ok']
    assert fixture['recorded']['J6_dup']['pairs'][0]['p_two_sided'] == pytest.approx(.012544176512929932)
    # The real decision was accept; the unchanged instrument check passes, and
    # the new deciding practical J1 fails. No new design statistics are invented.
    assert fixture['recorded']['decision'] == 'accept' and old_j1['ok']


@pytest.mark.parametrize('candidate,parent,card', itertools.product((0, 1), repeat=3))
def test_every_binary_outcome_uses_exact_half_weight(candidate, parent, card):
    table = {(arm, 'item'): ['pass' if won else 'fail']
             for arm, won in (("S'", candidate), ('S', parent), ('C', card))}
    found = a.pooled_differences(table, ['item'])
    assert found == [Fraction(2 * candidate - parent - card, 2)]
    assert type(found[0]) is Fraction


@pytest.mark.parametrize('candidate,parent,card,expected', [
    (['pass', 'fail'], ['pass', 'fail'], ['fail', 'fail'], Fraction(1, 4)),
    (['unknown'], ['fail'], ['fail'], Fraction(0)),
    (['pass'], ['unknown'], ['fail'], Fraction(1, 2)),
    (['pass'], ['fail'], ['unknown'], Fraction(1, 2)),
    (['unknown_fault'], ['unknown_artifact'], ['unknown'], Fraction(-1)),
])
def test_run_means_and_conservative_unknown_bounds_remain_exact(candidate, parent, card, expected):
    table = {("S'", 'item'): candidate, ('S', 'item'): parent, ('C', 'item'): card}
    assert a.pooled_differences(table, ['item']) == [expected]


@pytest.mark.parametrize('total,size,ok', [(Fraction(5, 2), 60, False), (Fraction(3), 60, True),
    (Fraction(7, 2), 60, True), (Fraction(3), 120, False), (Fraction(6), 120, True)])
def test_practical_threshold_is_exact_and_divides_by_whole_batch(total, size, ok):
    gain = [Fraction(1, 2)] * int(2 * total)
    first = {'whole_batch': float(total / size), 'p_t': 1.0}
    j1, j2 = a._practical(p.ACCEPT_RULES[CHILD], 'alfworld', gain, [Fraction(0)], size,
                          first, {'whole_batch': 0., 'p_t': 1.})
    assert j1['ok'] is ok and j1['practical'] is ok and not j1['significant']
    assert j1['gain_points'] == 5 and j2['ok'] and not j2['decides']


@pytest.mark.parametrize('noisier', [False, True])
def test_full_prepare_and_decide_use_pooled_j1_only_with_same_text_parent(noisier, tmp_path):
    old = seal(tmp_path / 'parent', PARENT)
    child = seal(tmp_path / 'child')
    cells = synthetic_cells(child, card_noisier=noisier)
    before, found = a.decide(cells, old), a.decide(cells, child)
    assert old['rule']['name'] == 'practical-v2-2'
    assert child['rule']['name'] == found['rule'] == a.POOLED_RULE_NAME
    assert old['card_is_parent'] and child['card_is_parent']
    assert before['guards']['J1']['whole_batch'] == pytest.approx(4 / 60)
    assert before['guards']['J1']['ok'] and before['decision'] == 'accept'
    assert found['guards']['J1']['baseline'] == '(S+C)/2' and found['guards']['J1']['pooled']
    assert found['guards']['J1']['whole_batch'] == pytest.approx((1 if noisier else 4) / 60)
    assert found['guards']['J1']['ok'] is (not noisier)
    assert found['decision'] == ('reject' if noisier else 'accept')
    for key in ('J3', 'J4_items', 'J5', 'J6_dup', 'J7_meta'):
        assert found['guards'][key] == before['guards'][key]
    assert {k: v for k, v in found['guards']['J2'].items() if k != 'rule'} == {
        k: v for k, v in before['guards']['J2'].items() if k != 'rule'}
    for name in ("S'-S", "S'-C"):
        assert found['contrasts'][name] == {**before['contrasts'][name], 'decides': False}
    assert found['guards']['J6_dup']['pairs'][0]['pair'] == 'C-S'
    assert p.DUP_ALPHA == .01
    assert a.reproduce(cells, child, found)


def test_pooled_statistics_use_the_same_authored_room_block_design(tmp_path):
    sealed = seal(tmp_path)
    cells = synthetic_cells(sealed)
    found = a.decide(cells, sealed)
    items = sealed['plan']['astar']
    d = a.pooled_differences(a.table(cells), items)
    design = a._design(sealed, items)
    assert len(set(design['clusters'])) == 12 and len(set(design['strata'])) == 4
    assert found['contrasts'][POOLED] == a.contrast(d, design=design, whole=60, sensitivity=True)
    assert found['contrasts'][POOLED]['df'] == 8
    assert found['guards']['J1']['p_t'] == found['contrasts'][POOLED]['p_t']
    assert found['contrasts'][POOLED]['sensitivity'] == {
        'p_signflip': stats_ext.signflip(d, **design), 'p_wilcoxon': stats_ext.wilcoxon(d)}


def test_nonidentical_parent_keeps_its_original_deciding_contrast(tmp_path):
    old = seal(tmp_path / 'old', PARENT, card_is_parent=False)
    child = seal(tmp_path / 'new', CHILD, card_is_parent=False)
    cells = synthetic_cells(child)
    before, found = a.decide(cells, old), a.decide(cells, child)
    assert not old['card_is_parent'] and not child['card_is_parent']
    assert POOLED not in found['contrasts'] and found['contrasts'] == before['contrasts']
    assert found['guards']['J1'] == {**before['guards']['J1'], 'rule': a.POOLED_RULE_NAME,
                                    'baseline': 'S', 'pooled': False}
    assert found['decision'] == before['decision'] == 'accept'


@pytest.mark.parametrize('damage', ['missing', 'old_rule', 'different_bar', 'wrong_bench'])
def test_child_refuses_unsealed_or_mismatched_rule_before_deciding(damage, tmp_path):
    sealed = seal(tmp_path)
    fields = {'rule': None} if damage == 'missing' else {'rule': p.ACCEPT_RULES[PARENT]} if damage == 'old_rule' else {
        'rule': {**sealed['rule'], 'gain_points': 4}} if damage == 'different_bar' else {'bench': 'officeqa'}
    changed = reseal(sealed, **fields)
    with pytest.raises(ValueError, match='exact pooled rule'):
        a.decide([], changed)


@pytest.mark.parametrize('configuration', [name for name in p.CONFIGURATIONS if name != CHILD])
def test_no_older_configuration_can_select_the_pooled_rule(configuration):
    assert a._v297_rule(configuration, 'alfworld', p.ACCEPT_RULES.get(configuration)) is False
    with pytest.raises(ValueError, match='only to ALFWorld v2.9.7'):
        a._v297_rule(configuration, 'alfworld', p.ACCEPT_RULES[CHILD])


def test_prepare_rejects_wrong_child_rule_before_workers_or_files(tmp_path):
    with pytest.raises(ValueError, match='exact pooled rule'):
        a.prepare(tmp_path / 'must-not-write', chain='D', bench='alfworld', step='D/s1-alfworld',
            unit='D/s1-alfworld/accept', candidate=None, parent=None, views={}, blocks={}, workers=None,
            trajectories=[], configuration=CHILD, rule=p.ACCEPT_RULES[PARENT])
    assert not (tmp_path / 'must-not-write').exists()


def test_shared_origin_cancellation_and_identical_all_remain_pairwise():
    rows = []
    for arm in ("S'", 'S', 'C'):
        rows.append({'arm': arm, 'task_id': 'shared', 'run': 0, 'set': 'real',
                     'judge': {'v2': {'token': 'unknown'}},
                     'reused_from': {'arm': 'S', 'task_id': 'shared', 'run': 0, 'set': 'real'}})
    table = a.table(rows, identical=['omitted'])
    assert a.pooled_differences(table, ['shared', 'omitted']) == [Fraction(0), Fraction(0)]


def test_unequal_answered_astar_uses_whole_a_denominator_in_full_decision(tmp_path):
    sealed = seal(tmp_path)
    # A contains more items than A*. Existing zero contribution outside A* is
    # preserved: a pooled 4-item net is below 5 points over 90 total items.
    enlarged = reseal(sealed, A=sealed['A'] + ['not-routed-%d' % i for i in range(30)])
    cells = synthetic_cells(enlarged, card_noisier=False)
    found = a.decide(cells, enlarged)
    assert found['A_star'] == 60 and found['A'] == 90
    assert found['contrasts'][POOLED]['whole_batch'] == pytest.approx(4 / 90)
    assert not found['guards']['J1']['ok']
