"""Count-only child feedback and gate evidence at the acceptance boundary."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import acceptance, engineer, profiles as p, step, v221_rule, v222_cards, v222_feedback


def cross_counts():
    return {'passed': True, 'benches': {bench: {'fired': 0, 'passed': True,
        'fixed': 0, 'broken': 0, 'net': 0} for bench in p.active_benches(p.MAIN_V8) if bench != 'zebralogic'}}


def test_segment_coverage_is_an_exact_count_only_subset():
    found = v222_cards.initial_package(evidence='engineering_fixture')
    proc = found.procedures[0]
    coverage = v222_feedback.coverage(10, ['a'], {proc.id: ['a'], 'other': []}, found)
    assert coverage['segments'] == {proc.id: coverage['procedures'][proc.id]}
    assert v222_feedback.coverage_ok(coverage)
    assert not v221_rule.coverage_ok(coverage)
    coverage['segments'][proc.id]['touched'] = 2
    assert not v222_feedback.coverage_ok(coverage)


@pytest.mark.parametrize('change', ['text', 'float', 'overflow', 'partial', 'inconsistent', 'extra_bench'])
def test_cross_feedback_rejects_raw_evidence_or_invalid_counts(change):
    value = cross_counts()
    assert v222_feedback.cross_gate_ok(value)
    row = value['benches']['officeqa']
    if change == 'text': row['answer'] = 'Authored private answer must not enter the channel.'
    if change == 'float': row['fired'] = 1.0
    if change == 'overflow': row['fired'] = 61
    if change == 'partial': row.pop('broken')
    if change == 'inconsistent': row.update(fired=5, fixed=3, broken=1, net=3)
    if change == 'extra_bench': value['benches']['zebralogic'] = dict(row)
    assert not v222_feedback.cross_gate_ok(value)


def test_production_feedback_enters_next_main_v8_context_but_not_its_parent(monkeypatch):
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v291_engineer import views
    ctx, _ = context(configuration=p.ZEBRA_PC_V15, views=views(3))
    ctx = replace(ctx, configuration=p.MAIN_V8, current=list(ctx.trajectories),
                  card=v222_cards.format_text('zebralogic'))
    keys = [trace['task_id'] for trace in ctx.trajectories]
    cells = {(arm, key): [{'cell': {'id': '%s-%s' % (arm, key), 'run': 1},
        'judge': {'v2': {'token': 'pass' if arm == "S'" else 'fail'}, 'format': {'violation': False}}}]
        for arm in ('S', "S'") for key in keys}
    verdict = step.train_verdict(cells, keys, [], [], predicate_faults=0, routed=3, runs=1,
        identical=[], touched=keys, configuration=p.MAIN_V8)
    st = SimpleNamespace(bench='zebralogic', setting=SimpleNamespace(extra={'configuration': p.MAIN_V8}),
        label=lambda unit: 'D/s1-zebralogic/' + unit, runtime=lambda: {})
    cut = {'run': [{'task_id': key.split('/', 1)[1], 'public': view} for key, view in ctx.routing_items]}
    monkeypatch.setattr(step, '_references', lambda *args, **kwargs: {})
    feedback = step._feedback(st, cut, 'train-r1', verdict, {}, ctx.parent, ctx.parent, cells, {})
    feedback.update(rule=verdict['rule'], coverage=v222_feedback.coverage(3, keys, {}, ctx.parent),
                    cross_gate=cross_counts())
    fields = {key: value for key, value in ctx.trajectories[0].items()
              if key not in (p.RECORD_HASH, 'version', 'evidence')}
    measured = p.record('trajectory', ctx.evidence, {**fields, 'cell': 'authored-cell', 'arm': "S'",
        'arm_kind': 'candidate', 'unit': 'D/s1-zebralogic/train-r1'})
    updated = replace(ctx, round=2, current=[measured], evaluated=[measured], training=feedback)
    assert updated.training['cross_gate'] == cross_counts()
    with pytest.raises(ValueError):
        replace(updated, configuration=p.MAIN_V7)


@pytest.mark.parametrize('field,value', [('configuration', p.MAIN_V7), ('home', 'officeqa'),
    ('unit', 'G/s1-searchqa/accept-r2'), ('phase', 'confirmation'), ('passed', False),
    ('parent_sha256', 'c' * 64), ('candidate_sha256', 'd' * 64)])
def test_acceptance_rejects_cross_evidence_from_another_scope(monkeypatch, field, value):
    sealed = p.record('acceptance-sealed', 'engineering_fixture', {'configuration': p.MAIN_V8,
        'bench': 'searchqa', 'unit': 'G/s1-searchqa/accept-r1',
        'seals': {'parent': 'a' * 64, 'candidate': 'b' * 64}})
    fields = {'configuration': p.MAIN_V8, 'home': sealed['bench'], 'unit': sealed['unit'],
        'phase': 'acceptance', 'passed': True, 'parent_sha256': 'a' * 64, 'candidate_sha256': 'b' * 64}
    fields[field] = value
    gate = p.record('v222-cross-gate', 'engineering_fixture', fields)
    monkeypatch.setattr(acceptance, '_decide', lambda *args: pytest.fail('No home decision before bound cross evidence'))
    with pytest.raises(ValueError, match='bound, passing cross-bench gate'):
        acceptance.decide([], sealed, cross_gate=gate)


def test_bound_acceptance_preserves_the_home_decision_and_stores_cross_evidence(monkeypatch):
    sealed = p.record('acceptance-sealed', 'engineering_fixture', {'configuration': p.MAIN_V8,
        'bench': 'searchqa', 'unit': 'G/s1-searchqa/accept-r1',
        'seals': {'parent': 'a' * 64, 'candidate': 'b' * 64}})
    gate = p.record('v222-cross-gate', 'engineering_fixture', {'configuration': p.MAIN_V8,
        'home': sealed['bench'], 'unit': sealed['unit'], 'phase': 'acceptance', 'passed': True,
        'parent_sha256': 'a' * 64, 'candidate_sha256': 'b' * 64})
    original = p.record('decision', 'engineering_fixture', {'decision': 'reject', 'reason': 'home_harm'})
    monkeypatch.setattr(acceptance, '_decide', lambda *args: original)
    result = acceptance.decide([], sealed, cross_gate=gate)
    assert result['decision'] == 'reject' and result['reason'] == 'home_harm' and result['cross_gate'] == gate
    older = deepcopy(sealed); older['configuration'] = p.MAIN_V7
    assert acceptance.decide([], older) == original
