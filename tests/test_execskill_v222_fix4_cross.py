"""Unknown native scores remain measured method outcomes; no services or data."""
from copy import deepcopy

import pytest

from skillopt.coevo5.outcomes import ARTIFACT, SCORED, UNCLASSIFIED, UNKNOWN, Verdict
from skillopt.execskill import judge, outcomes_ext, v221_rule, v222_gate as gate
from tests.test_execskill_v222_gate import packages, pools, simple_inspector


def cell(token, bench='officeqa'):
    """Use the real judge's verdict/format shape with an authored scorer result."""
    unknown = token.startswith('unknown')
    kind = {'unknown': UNCLASSIFIED, 'unknown_artifact': ARTIFACT,
            'unknown_fault': outcomes_ext.FAULT}.get(token, SCORED)
    verdict = Verdict(UNKNOWN if unknown else token, kind, 'authored score', '11')
    prediction = {'status': 'unknown' if unknown else 'available',
                  'output': None if unknown else '<answer>1</answer>',
                  'reason': 'authored_scorer_unknown' if unknown else 'model_response_available'}
    if bench == 'spreadsheetbench':
        prediction.update(status='available', output={'code': 'value = 1', 'cases': []})
    found = judge.judge(bench, {'question': 'Authored quantity?'}, {'answer': '1'}, prediction,
        runtime={}, score={'status': 'unavailable' if unknown else token, 'reason': 'authored scorer'},
        verdict=verdict)
    assert found['v2']['token'] == token
    return {'judge': found, 'final': found['final']}


def inspection(bench='officeqa', *, total=20, fired=1):
    parent, candidate = packages()
    found = simple_inspector(bench, parent, candidate, pools()[bench][:total])
    found.update(fired=fired, fired_items=found['slice_ids'][:fired])
    return found


@pytest.mark.parametrize('parent,candidate,fixed,broken', [
    ('unknown', 'unknown', 0, 0), ('unknown', 'pass', 1, 0), ('unknown', 'fail', 0, 0),
    ('pass', 'unknown', 0, 1), ('fail', 'unknown', 0, 0), ('pass', 'pass', 0, 0),
    ('pass', 'fail', 0, 1), ('fail', 'pass', 1, 0), ('fail', 'fail', 0, 0),
])
def test_cross_unknowns_keep_both_method_arms_on_the_existing_l_side(parent, candidate, fixed, broken):
    found = inspection(); key = found['fired_items'][0]
    cells = {('S', key): [cell(parent)], ("S'", key): [cell(candidate)]}
    original = deepcopy(cells)
    measured = gate.measured(found, cells)
    assert (measured['fixed'], measured['broken'], measured['net']) == (fixed, broken, fixed - broken)
    assert measured['whole_slice'] == (fixed - broken) / 20
    assert measured['items'] == 20 and measured['fired'] == 1 and measured['paired_item_calls'] == 2
    assert measured['scoring_sides'] == {'S': 'L', "S'": 'L'}
    assert measured['unknown'] == {'S': int(parent == 'unknown'), "S'": int(candidate == 'unknown')}
    assert measured['unknown_by_token'] == {
        'S': {'unknown': 1} if parent == 'unknown' else {},
        "S'": {'unknown': 1} if candidate == 'unknown' else {}}
    assert measured['fixed_items'] == v221_rule.item_changes(cells, found['slice_ids'],
                                                            touched=found['fired_items'])['fixed']
    assert cells == original


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
def test_cross_reports_all_registered_unknown_subtypes_and_ignores_none_format_flags(bench):
    found = inspection(bench, fired=3)
    cells = {(arm, key): [cell(token, bench)] for key, token in zip(found['fired_items'],
        ('unknown', 'unknown_artifact', 'unknown_fault')) for arm in ('S', "S'")}
    assert all(row[0]['judge']['format']['violation'] is None for row in cells.values())
    result = gate.measured(found, cells)
    assert result['passed'] and result['fixed'] == result['broken'] == result['net'] == 0
    assert result['paired_item_calls'] == 6 and result['items'] == 20
    assert result['unknown'] == {'S': 3, "S'": 3}
    assert result['unknown_by_token'] == {arm: {'unknown': 1, 'unknown_artifact': 1, 'unknown_fault': 1}
                                          for arm in ('S', "S'")}


@pytest.mark.parametrize('bad', [None, {}, 'unknown', 'pass', {'judge': {'v2': {}}},
    {'judge': {'v2': {'token': 'unregistered'}}}])
def test_cross_requires_an_actual_record_with_a_registered_outcome(bad):
    found = inspection(); key = found['fired_items'][0]
    with pytest.raises(ValueError, match='One scored run'):
        gate.measured(found, {('S', key): [cell('unknown')], ("S'", key): [bad]})


def test_cross_gate_can_measure_unknown_workbook_pairs_without_inventing_harm():
    parent, candidate = packages()
    slices = gate.harm_slices(pools())
    def paired(bench, before, after, items):
        return {(arm, item['task_id']): [cell('unknown', 'spreadsheetbench')]
                for arm in ('S', "S'") for item in items}
    final, record = gate.check(home='searchqa', parent=parent, candidate=candidate, slices=slices,
        inspector=simple_inspector, run_pairs=paired, phase='confirmation')
    assert final == candidate and record['passed'] and record['narrowing'] is None
    assert all(row['unknown'] == {'S': row['fired'], "S'": row['fired']}
               and row['fixed'] == row['broken'] == 0 for row in record['benches'].values())


@pytest.mark.parametrize('change', ['none', 'overflow', 'subtype_count', 'invalid_subtype',
                                  'parent_h', 'unknown_candidate_pass'])
def test_measured_smoke_revalidates_unknown_counts_and_method_sides(change):
    from skillopt.execskill import profiles as p, v222_smoke as smoke
    from tests.test_execskill_v222_smoke import cross_probe_receipt, decomposition_receipt
    parent, candidate = packages()
    def paired(bench, before, after, items):
        def token(arm):
            if bench == 'officeqa':
                return 'pass' if arm == 'S' else 'unknown'
            return 'unknown' if bench == 'spreadsheetbench' else 'fail'
        return {(arm, row['task_id']): [cell(token(arm),
                    'spreadsheetbench' if bench == 'spreadsheetbench' else 'officeqa')]
                for row in items for arm in ('S', "S'")}
    _, record = gate.check(home='searchqa', parent=parent, candidate=candidate,
        slices=gate.harm_slices(pools()), inspector=simple_inspector, run_pairs=paired, phase='confirmation')
    value = {'passed': True, 'decomposition': decomposition_receipt(),
             'cross_narrowing': cross_probe_receipt(record)}
    assert record['narrowing']['benches'] == ['officeqa']
    assert smoke.check_measured(value) == value
    if change == 'none':
        return
    fields = {key: deepcopy(row) for key, row in record.items()
              if key not in ('version', 'evidence', p.RECORD_HASH)}
    row = fields['benches']['spreadsheetbench']
    if change == 'overflow':
        row['unknown']["S'"] = row['fired'] + 1
        row['unknown_by_token']["S'"] = {'unknown': row['fired'] + 1}
    elif change == 'subtype_count':
        row['unknown_by_token']["S'"]['unknown'] -= 1
    elif change == 'invalid_subtype':
        row['unknown_by_token']["S'"] = {'unknown_unregistered': row['fired']}
    elif change == 'parent_h':
        row['scoring_sides']['S'] = 'H'
    else:
        row.update(gate.counts(fired=row['fired'], fixed=1, broken=0, items=row['items']))
    value['cross_narrowing']['cases']['harmful_format']['gate'] = p.record('v222-cross-gate', 'engineering_fixture', fields)
    with pytest.raises(ValueError, match='unknown|Unknown'):
        smoke.check_measured(value)
