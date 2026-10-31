"""Read retries spend the implant test scope; authored ledgers and smoke only."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import budgets, chain, manifest, profiles as p, v214_stages
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_manifest import reseal
from tests.test_execskill_v217i_smoke import receipts, setup

CHILD = p.IMPLANT_V5


def read_setting(root, chain_id):
    caps = budgets.chain_caps(chain_id, CHILD)
    ledger = {scope: {'cap': cap, 'open': 0, 'settled': 0} for scope, cap in caps.items()}
    # Four completed panels total 150M; the failed ALFWorld unit's estimate is 150M.
    terms = {bench: 37500000 for bench in p.MAIN_V5_ORDER[:-1]}
    terms['alfworld'] = 150000000
    setting = SimpleNamespace(root=root, budget=SimpleNamespace(snapshot=lambda: ledger), extra={
        'configuration': CHILD, 'test_read_estimate': {chain_id: 300000000},
        'test_read_terms': {chain_id: terms}})
    return setting, ledger


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_failed_alf_read_can_spend_the_registered_reserve_on_relaunch(tmp_path, chain_id):
    setting, ledger = read_setting(tmp_path, chain_id)
    first = chain.read_budget(setting, chain_id)
    assert first['part'] == 300000000 and first['need'] == 390000000
    assert first['units'] == list(p.MAIN_V5_ORDER)
    # The same first-attempt gate passed with the original isolated 456M read cap.
    ledger[chain_id + ':test']['cap'] = 456000000
    assert chain.read_budget(setting, chain_id) == first
    ledger[chain_id + ':test']['cap'] = 662000000

    for bench in p.MAIN_V5_ORDER[:-1]:
        write_json(chain.unit_root(setting, chain_id, bench) / 'unit.json',
                   {'authored_completion_marker': True})
    for scope in ('overall', chain_id + ':solver', chain_id + ':test'):
        ledger[scope]['settled'] = 300000000
    assert ledger[chain_id + ':solver']['cap'] - ledger[chain_id + ':solver']['settled'] == 363100000
    # Reproduce the review failure with the old uncharged redo scope.
    ledger[chain_id + ':test']['cap'] = 456000000
    ledger[chain_id + ':redo'] = {'cap': 206000000, 'open': 0, 'settled': 0}
    assert ledger[chain_id + ':test']['cap'] - ledger[chain_id + ':test']['settled'] == 156000000
    with pytest.raises(chain.Pause, match=chain_id + ':test'):
        chain.read_budget(setting, chain_id)

    ledger[chain_id + ':test']['cap'] = 662000000
    del ledger[chain_id + ':redo']
    retried = chain.read_budget(setting, chain_id)
    assert retried['units'] == ['alfworld']
    assert retried['part'] == 150000000 and retried['need'] == 195000000
    assert ledger[chain_id + ':test']['cap'] - ledger[chain_id + ':test']['settled'] == 362000000
    assert budgets.solver_scopes(chain_id, None, None, 'test') == (
        'overall', chain_id + ':solver', chain_id + ':test')
    assert set(ledger) == {'overall', chain_id + ':solver', chain_id + ':test'}


@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('suffix', [':test', ':solver'])
def test_read_gate_keeps_exact_1_3_requirement_after_open_reservations(tmp_path, chain_id, suffix):
    setting, ledger = read_setting(tmp_path, chain_id)
    row = ledger[chain_id + suffix]
    row['settled'] = 100000000
    row['open'] = row['cap'] - row['settled'] - 390000000
    assert chain.read_budget(setting, chain_id)['need'] == 390000000
    row['open'] += 1
    with pytest.raises(chain.Pause, match=chain_id + suffix):
        chain.read_budget(setting, chain_id)


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_se6_checks_one_read_plus_largest_retry_in_the_charged_test_scope(monkeypatch, chain_id):
    found = receipts(chain_id)
    s2 = found['stage_records']['S2']['result']
    bounds = found['stage_records']['S1']['result']['solver_bounds']
    projected = v214_stages.projection(s2, chain_id, bounds=bounds, configuration=CHILD)
    scopes = projected['solver_scopes']
    assert set(scopes) == {chain_id + ':test', chain_id + ':solver'}
    # The authored measurement is 100 tokens/card, 160/procedure, ratio 1.
    panel_costs = [100 * cards + 160 * procedures
                   for cards, procedures in p.TEST_READ_CELLS[CHILD].values()]
    needed = sum(panel_costs) + max(panel_costs) + projected['read_reservation']
    assert needed > projected['read_estimate'] + projected['read_reservation']
    assert scopes[chain_id + ':test'] == {'projected': needed, 'cap': 662000000, 'passed': True}
    assert scopes[chain_id + ':solver'] == {'projected': needed, 'cap': 663100000, 'passed': True}
    assert projected['read_scopes'][chain_id + ':test']['cap'] == 662000000
    assert projected['passed']

    original_caps = budgets.chain_caps
    def capped(c, configuration):
        return {**original_caps(c, configuration), c + ':test': needed - 1}
    monkeypatch.setattr(budgets, 'chain_caps', capped)
    limited = v214_stages.projection(s2, chain_id, bounds=bounds, configuration=CHILD)
    assert not limited['passed']
    assert not limited['solver_scopes'][chain_id + ':test']['passed']
    assert limited['solver_scopes'][chain_id + ':solver']['passed']


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_manifest_pins_the_combined_read_cap_and_refuses_old_caps(tmp_path, monkeypatch, chain_id):
    _, made, _ = setup(tmp_path, monkeypatch, chain=chain_id)
    assert manifest.check(made) == made
    assert made['caps']['overall'] == 2 * 663100000  # manifests list both independent chain ledgers
    for c in p.CHAINS:
        assert made['caps'][c + ':test'] == 662000000
        assert made['caps'][c + ':solver'] == 663100000
        assert made['caps'][c + ':confirm'] == 1100000
        assert c + ':redo' not in made['caps']
    identity = made['sizes']['v214']['caps']
    assert identity['test_read_cap'] == 662000000 and identity['redo_reserve'] == 0
    assert identity['solver_cap'] == 663100000

    old = deepcopy(made)
    old['caps'][chain_id + ':test'] = 456000000
    old['caps'][chain_id + ':redo'] = 206000000
    with pytest.raises(ValueError, match='registered run configuration and carries its caps'):
        manifest.check(reseal(old))
