"""Fund main-v6 read retries in their charged scope without using learning redo."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import budgets, chain, manifest, profiles as p, smoke, v214_stages, v218_limits
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_manifest import reseal
from tests import test_execskill_v217i_smoke as parent_smoke
from tests.test_execskill_v218_smoke import receipts

CHILD = p.MAIN_V6


def read_setting(root, c, monkeypatch):
    ledger = {scope: {'cap': cap, 'open': 0, 'settled': 0}
              for scope, cap in budgets.chain_caps(c, CHILD).items()}
    terms = {b: 37500000 for b in p.MAIN_V5_ORDER[:-1]}
    terms['alfworld'] = 150000000
    setting = SimpleNamespace(root=root, budget=SimpleNamespace(snapshot=lambda: ledger), extra={
        'configuration': CHILD, 'test_read_estimate': {c: 300000000}, 'test_read_terms': {c: terms}})
    monkeypatch.setattr(chain, 'latest_cap_check', lambda _: (Path('authored-cap-check.json'),
        {'per_cell': 1, 'anchor_high': 1, p.RECORD_HASH: 'a'*64}))
    return setting, ledger


def test_largest_registered_read_unit_adds_206m_without_changing_learning_caps():
    caps = v218_limits.read_unit_caps(p)
    assert caps == p.IMPLANT_READ_UNIT_CAPS
    assert max(caps, key=caps.get) == 'alfworld'
    assert caps['alfworld'] == 206000000
    cards, procedures = p.TEST_READ_CELLS[CHILD]['alfworld']
    assert caps['alfworld'] == p.legacy._round_up(3 * (
        p.CELL_ANCHORS['alfworld'][1] * (cards + Fraction(8, 5) * procedures)
        + 16 * 520192), 1000000)
    plan = p.CONFIGURATIONS[CHILD]
    assert plan['test_read_cap'] == 456000000 + 206000000 == 662000000
    assert plan['redo_reserve'] == 263200000
    assert plan['solver_cap'] == p.legacy._round_up(1352700000+662000000+263200000,5000000) == 2280000000
    assert p.CONFIG_GLM_CAP[CHILD] == 7592790784
    for c in p.CHAINS:
        limits = budgets.chain_caps(c, CHILD)
        assert limits['overall'] == 9872790784
        assert limits[c+':redo'] == 263200000


@pytest.mark.parametrize('c', ['G', 'D'])
def test_review_scenario_relaunches_and_keeps_learning_redo_unspent(tmp_path, monkeypatch, c):
    setting, ledger = read_setting(tmp_path, c, monkeypatch)
    first = chain.read_budget(setting, c)
    assert first['part'] == 300000000 and first['need'] == 390000000
    assert first['units'] == list(p.MAIN_V5_ORDER)
    ledger[c+':test']['cap'] = 456000000
    assert chain.read_budget(setting, c) == first
    for b in p.MAIN_V5_ORDER[:-1]:
        write_json(chain.unit_root(setting, c, b)/'unit.json', {'authored_completion_marker': True})
    for scope in budgets.solver_scopes(c, None, None, 'test'):
        ledger[scope]['settled'] = 300000000
    redo = deepcopy(ledger[c+':redo'])
    with pytest.raises(chain.Pause, match=c+':test'):
        chain.read_budget(setting, c)
    ledger[c+':test']['cap'] = 662000000
    retried = chain.read_budget(setting, c)
    assert retried['units'] == ['alfworld']
    assert retried['part'] == 150000000 and retried['need'] == 195000000
    assert ledger[c+':test']['cap'] - ledger[c+':test']['settled'] == 362000000
    # Read retries use the same chain scopes; only learning kinds take an attempt number.
    assert budgets.solver_scopes(c, None, None, 'test') == ('overall',c+':solver',c+':test')
    for scope in budgets.solver_scopes(c, None, None, 'test'):
        ledger[scope]['settled'] += 150000000
    assert ledger[c+':test']['settled'] == 450000000
    assert ledger[c+':redo'] == redo == {'cap':263200000,'settled':0,'open':0}
    assert c+':redo' in budgets.solver_scopes(c, 'searchqa', 1, 'selftest', 2)


@pytest.mark.parametrize('c', ['G', 'D'])
@pytest.mark.parametrize('suffix', [':test', ':solver'])
def test_first_attempt_keeps_exact_1_3_gate_after_open_reservations(tmp_path, monkeypatch, c, suffix):
    setting, ledger = read_setting(tmp_path, c, monkeypatch)
    row = ledger[c+suffix]
    row['settled'] = 100000000
    row['open'] = row['cap'] - row['settled'] - 390000000
    assert chain.read_budget(setting, c)['need'] == 390000000
    row['open'] += 1
    with pytest.raises(chain.Pause, match=c+suffix):
        chain.read_budget(setting, c)


@pytest.mark.parametrize('c', ['G', 'D'])
def test_se6_prices_read_retry_and_learning_redo_independently(monkeypatch, c):
    found = receipts(c, {p.RECORD_HASH:'a'*64, 'data':{'snapshot_sha256':'b'*64,'s0_sha256':'c'*64}})
    stages = found['stage_records']
    kwargs = {'s3':stages['S3']['result'], 'bounds':stages['S1']['result']['solver_bounds'], 'configuration':CHILD}
    projected = v214_stages.projection(stages['S2']['result'], c, **kwargs)
    price = lambda cells: sum(100*cards+160*procedures for cards,procedures in cells.values())
    panels = p.TEST_READ_CELLS[CHILD]
    read_cost = price(panels)
    retry_cost = max(price({b:cells}) for b,cells in panels.items())
    learning = sum(price(cells) for kinds in p.CONFIG_SCHEDULE_CELLS[CHILD].values() for cells in kinds.values())
    scopes = smoke._scope_cells(c, CHILD)
    learning_redo = max(price(cells) for cells in scopes[c+':redo'])
    needed = read_cost+retry_cost+projected['read_reservation']
    assert projected['solver_scopes'][c+':test'] == {'projected':needed,'cap':662000000,'passed':True}
    assert projected['solver_scopes'][c+':solver'] == {
        'projected':learning+learning_redo+needed,'cap':2280000000,'passed':True}
    assert projected['solver_scopes'][c+':redo']['cap'] == 263200000
    assert projected['passed']
    old_caps = budgets.chain_caps
    monkeypatch.setattr(budgets, 'chain_caps', lambda chain_id, config:
        {**old_caps(chain_id,config),chain_id+':test':needed-1})
    refused = v214_stages.projection(stages['S2']['result'], c, **kwargs)
    assert not refused['passed'] and not refused['solver_scopes'][c+':test']['passed']


@pytest.mark.parametrize('c', ['G', 'D'])
def test_manifest_binds_new_caps_and_refuses_pre_fix_read_caps(tmp_path, monkeypatch, c):
    monkeypatch.setattr(parent_smoke, 'CHILD', CHILD)
    _, made, _ = parent_smoke.setup(tmp_path, monkeypatch, chain=c)
    assert manifest.check(made) == made
    for arm in p.CHAINS:
        assert made['caps'][arm+':test'] == 662000000
        assert made['caps'][arm+':redo'] == 263200000
        assert made['caps'][arm+':solver'] == 2280000000
    assert made['sizes']['v214']['caps']['test_read_cap'] == 662000000
    retry = made['sizes']['v214']['changes']['split']['read_retry']
    assert retry['reserve'] == 206000000 and retry['charged_scope'] == '<chain>:test'
    old = deepcopy(made)
    old['caps'][c+':test'] = 456000000
    old['caps'][c+':solver'] = 2075000000
    with pytest.raises(ValueError, match='registered run configuration and carries its caps'):
        manifest.check(reseal(old))
