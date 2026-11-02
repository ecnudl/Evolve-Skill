"""Cross arms are scoped before dispatch; authored in-memory items and scripted calls only."""
from pathlib import Path

import pytest

from skillopt.execskill import cells, package, profiles as p, v219_read
from tests.execskill_fakes_env import Script
from tests.fixtures.execskill.items import searchqa_items


def probe(unit, *, configuration=p.CROSS_V5, label='X_officeqa'):
    task = searchqa_items(1)[0]
    context = cells.Context(attempt=Path('/tmp').resolve(), endpoint=None, runtime={'searchqa': {}},
        cards=v219_read.cards(), native=None, episodes=None, worker=None,
        evidence='engineering_fixture', configuration=configuration)
    cell = {'id': cells.cell_id(unit, label, task['task_id'], 0), 'unit': unit, 'arm': label,
            'benchmark': 'searchqa', 'task_id': task['task_id'], 'run': 0}
    cells._check_cell(cell)
    arm = cells.Arm('blank' if label == 'B' else 'card' if label == 'C' else 'candidate',
                    package.empty(step='G/card', evidence='engineering_fixture'))
    return context, cell, task, arm


def assert_refused_before_dispatch(monkeypatch, unit):
    context, cell, task, arm = probe(unit)
    dispatches = []

    def forbidden(*args, **kwargs):
        dispatches.append((args, kwargs))
        pytest.fail('A refused cross arm reached the worker or shell')

    context.solve = forbidden
    monkeypatch.setattr(cells, '_worker', forbidden)
    call = Script([])
    with pytest.raises(ValueError) as caught:
        cells._shell(context, cell, task, arm, call)
    assert str(caught.value) == (
        'Cross arm X_officeqa is not allowed in unit ' + unit
        + '; only registered test-read and S2 practice units accept cross arms')
    assert dispatches == [] and call.requests == [] and call.receipts == []


def test_reviewer_training_probe_refused_before_dispatch(monkeypatch):
    assert_refused_before_dispatch(monkeypatch, 'G/s1-searchqa/train-r1')


@pytest.mark.parametrize('unit', [
    'D/s1-searchqa/train-r1', 'G/s1-searchqa/confirm', 'G/s1-searchqa/accept',
    'G/s1-searchqa/audit', 'G/s1-searchqa/engineer', 'G/v214-smoke/S1/searchqa',
    'G/v214-smoke/S2/officeqa', 'G/test/officeqa', 'H/test/searchqa',
    'G/test/searchqa/extra', 'G/v214-smoke/S2/searchqa/extra', 'G/test',
])
def test_other_unregistered_units_refused_before_dispatch(monkeypatch, unit):
    assert_refused_before_dispatch(monkeypatch, unit)


def assert_office_card_sent(unit):
    context, cell, task, arm = probe(unit)
    call = Script(['<answer>Fixtown 0</answer>'])
    prediction = cells._shell(context, cell, task, arm, call)
    assert len(call.requests) == len(call.receipts) == 1
    system, user = call.requests[0]
    assert v219_read.cards()['officeqa'] in system
    assert context.cards['searchqa'] not in system
    assert task['public']['question'] in user
    assert prediction['shell']['calls']


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_registered_test_read_sends_office_card_to_search_shell(chain):
    assert_office_card_sent(chain + '/test/searchqa')


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_registered_s2_practice_sends_office_card_to_search_shell(chain):
    assert_office_card_sent(chain + '/v214-smoke/S2/searchqa')


@pytest.mark.parametrize('configuration', [p.MAIN_V5, p.MAIN_V6, p.IMPLANT_V5])
def test_non_cross_configurations_keep_existing_dispatch(configuration):
    context, cell, task, arm = probe('G/s1-searchqa/train-r1', configuration=configuration)
    call = Script(['<answer>Fixtown 0</answer>'])
    cells._shell(context, cell, task, arm, call)
    assert len(call.requests) == len(call.receipts) == 1
    assert context.cards['searchqa'] in call.requests[0][0]
    assert v219_read.cards()['officeqa'] not in call.requests[0][0]


@pytest.mark.parametrize('label', ['F', 'C', 'B'])
def test_non_cross_arms_keep_existing_cards_and_scope(label):
    context, cell, task, arm = probe('G/s1-searchqa/train-r1', label=label)
    expected = '' if label == 'B' else context.cards['searchqa']
    assert v219_read.card_text(context, 'searchqa', label) == expected
    call = Script(['<answer>Fixtown 0</answer>'])
    cells._shell(context, cell, task, arm, call)
    assert len(call.requests) == len(call.receipts) == 1
    if label == 'B':
        assert context.cards['searchqa'] not in call.requests[0][0]
    else:
        assert expected in call.requests[0][0]
