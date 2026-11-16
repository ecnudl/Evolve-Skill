"""Controller proposals use parent outcomes; adoption needs measured comparisons."""
import ast
from fractions import Fraction
import hashlib
import json

import pytest

from skillopt.execskill import notes, profiles as p, v222_cards as cards, v222_hygiene as hygiene
from skillopt.execskill.package import with_
from skillopt.validator_pilot.api import digest


def parent():
    return cards.initial_package(evidence='engineering_fixture', step='G/s0')


def own(package, bench='searchqa'):
    return [procedure.id for procedure in cards.own_segments(package, bench)]


def trajectory(package, ids, key, token='fail', *, run=0, delivered=True):
    """An authored delivered first request with exact pinned seed fields and hashes."""
    stored = []
    for pid in ids:
        procedure = package.get(pid)
        assignment = next(node for node in ast.parse(procedure.source).body
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'SEGMENT_FIELDS'
                                                   for target in node.targets))
        fields = ast.literal_eval(assignment.value)
        kept = notes.Screened(fields, 'An authored public snippet.',
                              outcome_judged=notes.outcome_judged(procedure), audited=notes.audited(procedure))
        text = notes.render(kept, bench=procedure.origin, header=procedure.header)
        stored.append({'id': pid, 'hook': 'before_call', 'fields': fields, 'delivered_text': text,
            'source_sha256': hashlib.sha256(procedure.source.encode()).hexdigest(),
            'procedure_sha256': procedure.sha256})
    view = {'question': 'Who described this tree?', 'context': 'An authored public snippet.',
            p.NOTES_KEY: '\n'.join(row['delivered_text'] for row in stored)}
    return {'cell': digest([key, run, token]), 'unit': 'G/s1-searchqa/run', 'arm': 'S', 'arm_kind': 'parent',
        'bench': 'searchqa', 'task_id': key, 'run': run, 'token': token, 'package_sha256': package.sha256,
        'shell': {'notes': stored, 'faults': []},
        'calls': [{'purpose': 'first', 'user': json.dumps(view), 'request_sha256': digest(view),
                   'receipt': {'delivery': 'delivered' if delivered else 'failed'}}]}


def propose(package, rows, **options):
    return hygiene.propose(package, bench=options.pop('bench', 'searchqa'),
        own_segments=options.pop('own_segments', own(package)), parent_cells=rows, **options)


@pytest.mark.parametrize('tokens,selected', [
    (['fail', 'fail'], False), (['fail'] * 3, True), (['fail', 'fail', 'pass'], True),
    (['fail', 'pass', 'fail', 'pass'], False), (['pass'] * 3, False),
    (['fail', 'fail', 'unknown'], False), (['unknown_fault'] * 4, False)])
def test_trigger_requires_three_distinct_scored_touched_items_and_negative_parent_net(tokens, selected):
    package = parent(); pid = own(package)[0]
    rows = [trajectory(package, [pid], 'searchqa/i%d' % i, token) for i, token in enumerate(tokens)]
    candidate, record = propose(package, rows)
    assert hygiene.MODE == 'measured_candidates'
    assert (candidate is not None) is selected
    assert record['selected'] == (pid if selected else None)
    if selected:
        assert set(package.order) - set(candidate.order) == {pid}


def test_one_worst_deletion_per_round_and_frozen_p0_order_breaks_equal_net_ties():
    package = parent(); first, second = own(package)
    rows = [trajectory(package, [first], 'searchqa/first%d' % i, token)
            for i, token in enumerate(('fail', 'fail', 'pass'))]
    rows += [trajectory(package, [second], 'searchqa/second%d' % i) for i in range(3)]
    candidate, record = propose(package, rows)
    assert record['selected'] == second and len(set(package.order) - set(candidate.order)) == 1
    assert {row['segment']: Fraction(row['net']) for row in record['segments']} == {first: -1, second: -3}
    tied = [trajectory(package, [first, second], 'searchqa/tie%d' % i) for i in range(3)]
    candidate, record = propose(package, tied)
    assert record['selected'] == first and set(package.order) - set(candidate.order) == {first}


def test_repeated_runs_do_not_inflate_the_touched_floor_and_item_means_are_exact():
    package = parent(); pid = own(package)[0]
    rows = [trajectory(package, [pid], 'searchqa/one', run=n) for n in range(7)]
    candidate, record = propose(package, rows)
    assert candidate is None
    assert next(row for row in record['segments'] if row['segment'] == pid)['touched'] == 1
    rows = [trajectory(package, [pid], 'searchqa/a', token, run=i)
            for i, token in enumerate(('pass', 'fail'))]
    rows += [trajectory(package, [pid], 'searchqa/b'), trajectory(package, [pid], 'searchqa/c')]
    candidate, record = propose(package, rows)
    row = next(row for row in record['segments'] if row['segment'] == pid)
    assert candidate is not None and row['touched'] == 3
    assert Fraction(row['passed']) == Fraction(1, 2) and Fraction(row['failed']) == Fraction(5, 2)
    assert Fraction(row['net']) == -2


@pytest.mark.parametrize('problem', ['not-delivered', 'empty', 'absent-request', 'stale-source', 'route-only', 'repair-only'])
def test_enabled_or_assembled_notes_do_not_count_as_delivered_seed_effects(problem):
    package = parent(); pid = own(package)[0]
    rows = [trajectory(package, [pid], 'searchqa/i%d' % i) for i in range(3)]
    for row in rows:
        if problem == 'not-delivered': row['calls'][0]['receipt']['delivery'] = 'failed'
        elif problem == 'empty': row['shell']['notes'][0]['delivered_text'] = ''
        elif problem == 'absent-request':
            request = json.loads(row['calls'][0]['user']); request.pop(p.NOTES_KEY)
            row['calls'][0]['user'] = json.dumps(request)
        elif problem == 'stale-source': row['shell']['notes'][0]['source_sha256'] = '0' * 64
        elif problem == 'route-only': row['route'] = {'enabled': [pid]}; row['shell']['notes'] = []
        else: row['calls'][0]['purpose'] = 'repair'
    candidate, record = propose(package, rows)
    assert candidate is None and record['selected'] is None


def test_only_present_original_own_segments_are_considered():
    package = parent(); first, second = own(package)
    foreign = own(package, 'officeqa')[0]
    learned = cards.make_segment('searchqa', 'Review the provided evidence.', {'kind': 'public_evidence'},
                                 evidence=package.evidence, step=1)
    package = with_(package, step='G/s1-searchqa', add=[learned], remove=[first])
    rows = [trajectory(package, [second, foreign, learned.id], 'searchqa/i%d' % i) for i in range(3)]
    candidate, record = propose(package, rows, own_segments=[first, foreign, learned.id, second])
    assert record['selected'] == second
    assert set(package.order) - set(candidate.order) == {second}
    assert {row['segment'] for row in record['segments']} == {second}


@pytest.mark.parametrize('bench,whole', [('alfworld', False), ('searchqa', True)])
def test_import_only_alfworld_and_whole_card_fallback_never_get_hygiene(bench, whole):
    package = parent(); pid = own(package)[0]
    candidate, record = propose(package, [trajectory(package, [pid], 'searchqa/i%d' % i) for i in range(3)],
                                bench=bench, whole_card=whole)
    assert candidate is None and record['selected'] is None


def test_hygiene_is_child_only_and_a_proposal_never_mutates_the_parent():
    package = parent(); before = package.to_json(); pid = own(package)[0]
    rows = [trajectory(package, [pid], 'searchqa/i%d' % i) for i in range(3)]
    candidate, record = propose(package, rows)
    assert package.to_json() == before and candidate.sha256 != package.sha256
    assert 'fixed' not in record and 'broken' not in record
    with pytest.raises(ValueError):
        propose(package, rows, configuration=p.MAIN_V7)
