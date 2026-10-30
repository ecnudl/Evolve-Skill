"""Mixed-chain selftest work is included in main-v5's schedule and smoke gate."""
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, profiles as p, smoke, step, v214_smoke, v214_stages


def test_zebra_inherits_the_parent_step_three_predecessor_schedule_and_rounding():
    earlier = p.MAIN_V5_ORDER[:2]
    parent = p.CONFIG_SCHEDULE_CELLS[p.MAIN_V4]['livemath']['selftest']
    inherited = {bench: cells for bench, cells in parent.items() if bench in earlier}
    assert inherited == {'officeqa': (0, 160)}
    expected = {**p.CONFIG_SCHEDULE_CELLS[p.ZEBRA_PC_V13][p.ZEBRA]['selftest'], **inherited}
    assert p.CONFIG_SCHEDULE_CELLS[p.MAIN_V5][p.ZEBRA]['selftest'] == expected
    weighted = sum(p.CELL_ANCHORS[bench][1] * (card + p.PROCEDURE_ARM_FACTOR[1] * procedure)
                   for bench, (card, procedure) in expected.items())
    unrounded = p.MAIN_CAP_FACTOR * (weighted + p.MAIN_RESERVATIONS * p.READ_RESERVATION)
    assert unrounded == 49_373_952
    assert p.CONFIG_STEP_CAPS[p.MAIN_V5][p.ZEBRA]['selftest'] == p.legacy._round_up(unrounded, 100_000) == 49_400_000
    assert sum(p.CONFIG_STEP_CAPS[p.MAIN_V5][p.ZEBRA].values()) == 173_900_000
    assert p.CONFIG_STEP_CAPS[p.ZEBRA_PC_V13][p.ZEBRA]['selftest'] == 43_300_000
    assert p.CONFIG_SCHEDULE_CELLS[p.ZEBRA_PC_V13][p.ZEBRA]['selftest'] == {p.ZEBRA: (0, 720)}


def test_non_generating_predecessors_contribute_no_sheet_selftest_cells(tmp_path, monkeypatch):
    generated = {}
    for bench in ('searchqa', p.ZEBRA):
        current = SimpleNamespace(bench=bench, label=lambda unit: unit,
                                  unit=lambda unit, work: work(tmp_path))
        generated[bench] = step._generate(current, {})
        assert generated[bench]['mode'] == 'selection_only'
        assert not generated[bench].get('g_self')
    office = [{'id': 'office-%d' % n, 'task_id': 'office-%d' % n} for n in range(60)]
    own = [{'id': 'sheet-%d' % n, 'task_id': 'sheet-%d' % n} for n in range(70)]
    monkeypatch.setattr(step, '_earlier', lambda st, unit: [
        (1, 'searchqa', generated['searchqa']), (2, 'officeqa', {'g_self': office}),
        (3, p.ZEBRA, generated[p.ZEBRA])])
    sets = step._sets(SimpleNamespace(bench='spreadsheetbench'), {'g_self': own})
    assert {bench: len(items) for bench, items in sets.items()} == {'officeqa': 40, 'spreadsheetbench': 60}
    schedule = p.CONFIG_SCHEDULE_CELLS[p.MAIN_V5]['spreadsheetbench']['selftest']
    assert schedule == {'officeqa': (0, 2 * 40 * p.SELFTEST_PASSES), 'spreadsheetbench': (0, 1704)}
    assert p.CONFIG_STEP_CAPS[p.MAIN_V5]['spreadsheetbench'] == p.CONFIG_STEP_CAPS[p.MAIN_V4]['spreadsheetbench']


def _review_measurements():
    # These authored averages reproduce the reviewed 42,892,192 projection and
    # 43,852,000-token dispatch: 720 Zebra procedure cells plus one 80-cell OQ pass.
    cards = {bench: Fraction(100) for bench in p.MAIN_V5_ORDER}
    cards.update(zebralogic=Fraction(37_000), officeqa=Fraction(38_375, 4))
    result = {'passed': True, 'benches': {}}
    for bench, n in v214_smoke.S2_ITEMS.items():
        tokens = cards[bench] * n
        assert tokens.denominator == 1
        result['benches'][bench] = {'passed': True, 'items': n, 'cells': n, 'arms': ['C'],
            'measurements': {'per_class': {bench: {'card': {'cells': n, 'tokens': int(tokens)}}},
                             'request_bytes': {bench: 1000}, 'actual': int(tokens)},
            'settled_tokens': int(tokens)}
    return result, cards


@pytest.mark.parametrize('chain', ('G', 'D'))
def test_se6_prices_the_full_zebra_selftest_and_reproduces_the_reviewed_gap(chain, monkeypatch):
    s2, cards = _review_measurements()
    s3 = {'passed': True, 'engineer_calls': 1, 'tokens': 100}
    bounds = v214_smoke.solver_bounds(chain, {'passed': True, 'route': 'B', 'longest': 256}
                                       if chain == 'D' else None)
    scope = budgets.solver_scopes(chain, p.ZEBRA, 3, 'selftest')[-1]
    old_schedule = p.CONFIG_SCHEDULE_CELLS[p.ZEBRA_PC_V13][p.ZEBRA]['selftest']
    old_cap = p.CONFIG_STEP_CAPS[p.ZEBRA_PC_V13][p.ZEBRA]['selftest']
    with monkeypatch.context() as old:
        old.setitem(p.CONFIG_SCHEDULE_CELLS[p.MAIN_V5][p.ZEBRA], 'selftest', deepcopy(old_schedule))
        old.setitem(p.CONFIG_STEP_CAPS[p.MAIN_V5][p.ZEBRA], 'selftest', old_cap)
        underpriced = v214_stages.projection(s2, chain, s3=s3, bounds=bounds)
    assert underpriced['passed']
    assert underpriced['solver_scopes'][scope] == {'projected': 42_892_192, 'cap': 43_300_000, 'passed': True}
    one_pass_dispatch = p.PROCEDURE_ARM_FACTOR[1] * (720 * cards[p.ZEBRA] + 80 * cards['officeqa'])
    assert one_pass_dispatch == 43_852_000 > old_cap

    # Retaining the old cap while fixing only the schedule must refuse readiness.
    with monkeypatch.context() as old:
        old.setitem(p.CONFIG_STEP_CAPS[p.MAIN_V5][p.ZEBRA], 'selftest', old_cap)
        refused = v214_stages.projection(s2, chain, s3=s3, bounds=bounds)
    assert not refused['passed'] and not refused['solver_scopes'][scope]['passed']
    fixed = v214_stages.projection(s2, chain, s3=s3, bounds=bounds)
    assert fixed['passed']
    assert fixed['solver_scopes'][scope] == {'projected': 45_348_192, 'cap': 49_400_000, 'passed': True}
    assert smoke._scope_cells(chain, p.MAIN_V5)[scope] == [{p.ZEBRA: (0, 720), 'officeqa': (0, 160)}]


def test_chain_totals_and_redo_scopes_follow_only_the_repriced_solver_scope():
    assert sum(sum(scopes.values()) for scopes in p.CONFIG_STEP_CAPS[p.MAIN_V5].values()) == 882_100_000
    config = p.CONFIGURATIONS[p.MAIN_V5]
    assert config['test_read_cap'] == 456_000_000 and config['redo_reserve'] == 87_000_000
    assert config['solver_cap'] == p.legacy._round_up(882_100_000 + 456_000_000 + 87_000_000, 5_000_000) == 1_430_000_000
    assert p.CONFIG_GLM_CAP[p.MAIN_V5] == 7_070_923_008
    for chain in p.CHAINS:
        caps = budgets.chain_caps(chain, p.MAIN_V5)
        assert caps['overall'] == 8_500_923_008
        assert caps[chain + ':solver'] == 1_430_000_000
        for attempt in (None, 2, 3):
            scope = budgets.solver_scopes(chain, p.ZEBRA, 3, 'selftest', attempt)[-1]
            assert caps[scope] == 49_400_000
    for bench in p.MAIN_V5_ORDER[:-1]:
        parent = p.machinery_configuration(p.MAIN_V5, bench)
        assert budgets.role_scope_caps(p.MAIN_V5, bench) == budgets.role_scope_caps(parent, bench)
