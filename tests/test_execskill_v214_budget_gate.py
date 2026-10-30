"""The actual read-budget gate must reserve the complete four-stage transfer read."""
from fractions import Fraction
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import chain, profiles as p
from skillopt.execskill.cells import Pause
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


@pytest.mark.parametrize('solver_chain', ['G', 'D'])
def test_read_gate_refuses_budget_sufficient_for_fcb_but_not_all_stages(tmp_path, monkeypatch, solver_chain):
    per = {b: {'card': p.CELL_ANCHORS[b][1], 'procedure_assumed': True} for b in p.MAIN_V5_ORDER}
    terms = p.read_estimate_terms(per, 1, p.MAIN_V5)
    worst = math.ceil(sum(terms.values()))
    base = sum(p.read_items(p.MAIN_V5, b) * Fraction(per[b]['card']) * (2+p.PROCEDURE_ARM_FACTOR[1])
               for b in p.MAIN_V5_ORDER)
    available = math.ceil(base*p.TEST_START_FACTOR)
    assert available < math.ceil(worst*p.TEST_START_FACTOR)
    scopes = {solver_chain+':'+scope: {'cap': available, 'open': 0, 'settled': 0}
              for scope in ('solver', 'test')}
    setting = SimpleNamespace(root=tmp_path, run='authored', budget=SimpleNamespace(snapshot=lambda: scopes),
        extra={'configuration': p.MAIN_V5, 'test_read_estimate': {solver_chain: worst},
               'test_read_terms': {solver_chain: {b: str(n) for b,n in terms.items()}}})
    monkeypatch.setattr(chain, 'latest_cap_check', lambda _: (Path('authored-cap-check.json'),
        {'per_cell': 1, 'anchor_high': 1, p.RECORD_HASH: 'a'*64}))
    with pytest.raises(Pause, match='test_read_budget'):
        chain.read_budget(setting, solver_chain)
    for row in scopes.values():
        row['cap'] = math.ceil(worst*p.TEST_START_FACTOR)
    gate = chain.read_budget(setting, solver_chain)
    assert gate['estimate'] == gate['part'] == gate['used'] == worst
    assert gate['need'] == math.ceil(worst*p.TEST_START_FACTOR)
    assert gate['units'] == list(p.MAIN_V5_ORDER)
