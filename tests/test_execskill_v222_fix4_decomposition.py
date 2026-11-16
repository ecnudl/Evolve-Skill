"""Completed unknowns and inapplicable format flags in the main-v8 smoke."""
from copy import deepcopy

import pytest

from skillopt.coevo5.outcomes import ARTIFACT, INFRASTRUCTURE, UNKNOWN, Verdict
from skillopt.execskill import judge, v222_cards as cards, v222_smoke as smoke
from skillopt.validator_pilot.api import digest
from tests.test_execskill_judge import ITEMS, receipt
from tests.test_execskill_v222_smoke import cross_receipt, decomposition_receipt


def cell(bench, token='pass', flag=True):
    field = 'violation' if bench == 'alfworld' else 'grid' if bench == 'zebralogic' else smoke.COUNTERS[bench]
    return {'judge': {'v2': {'token': token}, 'format': {field: flag}},
            'final': {'token': token}}


def measure(bench, historical, segmented):
    assert len(historical) == len(segmented) == 20
    return smoke.measure_decomposition(bench, list(range(20)),
        lambda labels, package: {'C_hist': deepcopy(historical), 'C': deepcopy(segmented)},
        initial=cards.initial_package(evidence='engineering_fixture'), registered_count=20)


@pytest.mark.parametrize('kind,token', [(INFRASTRUCTURE, 'unknown'), (ARTIFACT, 'unknown_artifact')])
def test_real_sheet_unknown_judge_counts_right_on_both_decomposition_card_arms(kind, token):
    prediction = {'status': 'available', 'output': {'code': 'pass', 'cases': []},
                  'costs': {'calls': 1}, 'reason': 'authored_workbook_scorer_unavailable'}
    judged = judge.judge('spreadsheetbench', {}, {}, prediction, [receipt('```python\npass\n```')],
        runtime={}, score={'status': 'unknown', 'reason': 'authored_unscorable_workbook'},
        verdict=Verdict(UNKNOWN, kind, 'authored_unscorable_workbook', '9c'))
    assert judged['v2']['token'] == token and judged['format']['violation'] is None
    unknown = {'judge': judged, 'final': {'token': token}}
    result = measure('spreadsheetbench', [unknown] * 20, [unknown] * 20)
    assert result['decision'] == 'accept_split' and result['whole_slice_gain'] == 0
    for arm in ('historical', 'segmented'):
        row = result[arm]
        assert row['scoring_side'] == 'H'
        assert row['items'] == row['passed'] == row['unknown'] == 20
        assert row['observed_passed'] == 0 and row['unknown_by_token'] == {token: 20}
        assert row['format']['program_delivered'] == row['format_applicable']['program_delivered'] == 20
        assert row['format_not_applicable']['program_delivered'] == 0


@pytest.mark.parametrize('token', ['unknown', 'unknown_artifact', 'unknown_fault'])
@pytest.mark.parametrize('unknown_arm', ['C_hist', 'C'])
def test_unknown_card_scores_equal_passes_in_either_decomposition_arm(token, unknown_arm):
    known = [cell('spreadsheetbench')] * 20
    unknown = [cell('spreadsheetbench', token)] * 20
    result = measure('spreadsheetbench', unknown if unknown_arm == 'C_hist' else known,
                     unknown if unknown_arm == 'C' else known)
    assert result['decision'] == 'accept_split' and result['whole_slice_gain'] == 0
    assert result['historical']['unknown'] == (20 if unknown_arm == 'C_hist' else 0)
    assert result['segmented']['unknown'] == (20 if unknown_arm == 'C' else 0)


@pytest.mark.parametrize('unknown_arm,gain,decision', [
    ('C_hist', -1.0, 'whole_card_fallback'), ('C', 1.0, 'accept_split')])
def test_unknown_card_scores_still_contrast_with_known_failures(unknown_arm, gain, decision):
    failed = [cell('spreadsheetbench', 'fail')] * 20
    unknown = [cell('spreadsheetbench', 'unknown')] * 20
    result = measure('spreadsheetbench', unknown if unknown_arm == 'C_hist' else failed,
                     unknown if unknown_arm == 'C' else failed)
    assert result['whole_slice_gain'] == gain and result['decision'] == decision


@pytest.mark.parametrize('truncated', [False, True])
def test_real_office_judge_without_single_number_counter_is_reported_not_applicable(truncated):
    public, private = ITEMS['officeqa']
    prediction = {'status': 'unknown', 'output': None, 'costs': {'calls': 1},
                  'reason': 'model_response_truncated' if truncated else 'model_call_unavailable'}
    sent = (receipt('<answer>12', finish='length', ok=False, error='finish_length') if truncated else
            {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'status': 503,
             'attempts': [], 'error_type': 'http_503', 'seconds': 0.1})
    judged = judge.judge('officeqa', public, private, prediction, [sent], runtime={})
    assert 'single_number' not in judged['format']
    assert judged['format']['violation'] is (True if truncated else None)
    actual = {'judge': judged, 'final': {'token': judged['v2']['token']}}
    result = measure('officeqa', [actual] * 20, [actual] * 20)
    assert result['decision'] == 'accept_split'
    assert result['format_compared'] is False and result['format_not_worse'] is None
    for arm in ('historical', 'segmented'):
        row = result[arm]
        assert row['unknown'] == (0 if truncated else 20)
        assert row['format']['single_number'] == row['format_applicable']['single_number'] == 0
        assert row['format_not_applicable']['single_number'] == 20


@pytest.mark.parametrize('bench', cards.BENCHES)
def test_none_counters_do_not_create_false_format_harm_when_applicable_rates_are_equal(bench):
    flag = False if bench == 'alfworld' else True
    before = [cell(bench, flag=flag)] * 20
    after = [cell(bench, flag=flag)] * 10 + [cell(bench, flag=None)] * 10
    result = measure(bench, before, after)
    assert result['decision'] == 'accept_split'
    assert result['format_compared'] is True and result['format_not_worse'] is True
    key = smoke.COUNTERS[bench]
    assert result['segmented']['format_applicable'][key] == result['segmented']['format_not_applicable'][key] == 10


@pytest.mark.parametrize('bench', ['officeqa', 'alfworld'])
@pytest.mark.parametrize('unavailable_arm', ['C_hist', 'C', 'both'])
def test_zero_applicable_counters_exclude_the_comparison_instead_of_inventing_a_format_result(bench, unavailable_arm):
    before = [cell(bench, flag=None if unavailable_arm in ('C_hist', 'both') else True)] * 20
    after = [cell(bench, flag=None if unavailable_arm in ('C', 'both') else False)] * 20
    result = measure(bench, before, after)
    assert result['decision'] == 'accept_split'
    assert result['format_compared'] is False and result['format_not_worse'] is None


@pytest.mark.parametrize('bench', ['officeqa', 'alfworld'])
def test_an_applicable_format_regression_is_not_hidden_by_none_counters(bench):
    good, bad = (False, True) if bench == 'alfworld' else (True, False)
    before = [cell(bench, flag=good)] * 20
    after = [cell(bench, flag=good)] * 9 + [cell(bench, flag=bad)] + [cell(bench, flag=None)] * 10
    result = measure(bench, before, after)
    assert result['decision'] == 'whole_card_fallback'
    assert result['format_compared'] is True and result['format_not_worse'] is False


def readiness_with_unknowns():
    found = decomposition_receipt()
    for bench in cards.BENCHES:
        count = found['benches'][bench]['items']
        flag = False if bench == 'alfworld' else True
        historical = [cell(bench, 'unknown', flag=None)] * (count // 2) + [cell(bench, flag=flag)] * (count // 2)
        segmented = [cell(bench, 'unknown_artifact', flag=None)] * (count // 2) + [cell(bench, flag=flag)] * (count // 2)
        measured = smoke.measure_decomposition(bench, list(range(count)),
            lambda labels, package, historical=historical, segmented=segmented:
                {'C_hist': deepcopy(historical), 'C': deepcopy(segmented)},
            initial=cards.initial_package(evidence='engineering_fixture'), registered_count=count)
        found['benches'][bench] = {**measured, 'cards_sha256': found['cards_sha256'],
            'slice_sha256': digest(found['slices'][bench])}
    return {'passed': True, 'decomposition': found, 'cross_narrowing': cross_receipt()}


def test_readiness_recomputes_unknown_and_not_applicable_measurements_without_old_cells():
    value = readiness_with_unknowns()
    assert smoke.check_decomposition(value['decomposition']) == value['decomposition']
    assert smoke.check_measured(value) == value


@pytest.mark.parametrize('change', ['unknown', 'unknown_by_token', 'observed_passed', 'scoring_side',
                                    'format_applicable', 'format_not_applicable', 'format_count', 'format_compared',
                                    'summary_unknown', 'summary_scoring_side', 'summary_not_applicable', 'format_rate'])
def test_readiness_refuses_inconsistent_unknown_or_not_applicable_counts(change):
    value = readiness_with_unknowns()
    row = value['decomposition']['benches']['officeqa']
    aggregate = row['historical']
    if change == 'unknown':
        aggregate['unknown'] -= 1
    elif change == 'unknown_by_token':
        aggregate['unknown_by_token']['unknown'] -= 1
    elif change == 'observed_passed':
        aggregate['observed_passed'] -= 1
    elif change == 'scoring_side':
        aggregate['scoring_side'] = 'L'
    elif change in ('format_applicable', 'format_not_applicable'):
        aggregate[change]['single_number'] -= 1
    elif change == 'format_count':
        aggregate['format']['single_number'] = aggregate['format_applicable']['single_number'] + 1
    elif change == 'summary_unknown':
        row['unknown']['C_hist'] -= 1
    elif change == 'summary_scoring_side':
        row['scoring_sides']['C'] = 'L'
    elif change == 'summary_not_applicable':
        row['format_not_applicable']['C'] -= 1
    elif change == 'format_rate':
        row['segmented_format_rate'] = 0.9
    else:
        row['format_compared'] = False
    with pytest.raises(ValueError):
        smoke.check_measured(value)


@pytest.mark.parametrize('token,flag', [(None, True), ('unregistered-outcome', True), ('pass', 1), ('pass', 'yes')])
def test_missing_outcomes_and_nonboolean_counter_values_remain_invalid(token, flag):
    with pytest.raises(ValueError):
        smoke._aggregates('officeqa', [cell('officeqa', token, flag)])


@pytest.mark.parametrize('format_record', [None, {}, [], {'single_number': 0}])
def test_unknown_does_not_hide_an_absent_or_malformed_judge_format_record(format_record):
    row = cell('officeqa', 'unknown')
    row['judge']['format'] = format_record
    with pytest.raises(ValueError):
        smoke._aggregates('officeqa', [row])
