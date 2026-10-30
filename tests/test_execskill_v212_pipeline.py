"""v2.12 acceptance entry and recovery using real units and authored in-process cells only."""
from contextlib import contextmanager
from dataclasses import replace

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import acceptance, budgets, donors, profiles as p, step, units, zebralogic as z
from skillopt.execskill.cells import Pause
from skillopt.execskill.package import empty, with_
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_v212_evaluation import final_package
from tests.test_execskill_zpc_pipeline import SourceWorker, build, offline  # noqa: F401


@pytest.mark.parametrize('resume_after_seal', [False, True])
def test_accept_entry_and_resume_use_three_packages_and_never_load_donors(
        tmp_path, monkeypatch, fast_statistics, resume_after_seal):
    setting, services, fake_solver, _ = build(tmp_path, monkeypatch)
    setting.extra['configuration'] = p.ZEBRA_PC_V13
    setting.budget = Budget(tmp_path / 'v212-ledger', sleep=lambda _: None)
    setting.budget.declare(budgets.chain_caps('D', p.ZEBRA_PC_V13))
    @contextmanager
    def workers(package, item):
        worker = SourceWorker().start(package, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    services = replace(services, item_workers=workers)
    parent = empty(step='D/s0', evidence='engineering_fixture')
    candidate = with_(parent, step='D/s1-zebralogic', add=final_package().procedures)
    st = step._Step(setting, services, 'D', z.BENCH, 1, parent, setting.root / 'D')
    # The seam uses real unit/registry/cell code; no deployment checks or Docker drain.
    monkeypatch.setattr(st, 'verify', lambda: None)
    monkeypatch.setattr(units, 'drainer', lambda *args, **kwargs: None)
    def forbidden(*args, **kwargs):
        pytest.fail('zebra-pc-v13 acceptance never needs a donor corpus or run trajectories')
    monkeypatch.setattr(step, '_run_trajectories', forbidden)
    monkeypatch.setattr(donors, 'verify', forbidden)
    monkeypatch.setattr(donors, 'donor_corpus', forbidden)
    cuts = z.slices(setting.pools[z.BENCH])
    # A mapping that refuses donor-only run views proves _accept does not read that slice.
    class AcceptOnly(dict):
        def __getitem__(self, key):
            assert key != 'run', 'No donor run views in a placebo-free acceptance'
            return super().__getitem__(key)
    cuts = AcceptOnly(accept=cuts['accept'])
    root = st.root / 'accept'
    if resume_after_seal:
        dispatch = acceptance.dispatch
        def interrupted(*args, **kwargs):
            raise Pause('exception', 'authored interruption after seal')
        monkeypatch.setattr(acceptance, 'dispatch', interrupted)
        with pytest.raises(Pause):
            step._accept(st, cuts, candidate, None)
        assert (root / 'sealed.json').exists() and not (root / 'unit.json').exists()
        write_json(root / 'attempt-1/recovery.json',
                   {'by': 'owner', 'date': '2026-10-30', 'decision': 'redo 1'})
        monkeypatch.setattr(acceptance, 'dispatch', dispatch)
    result = step._accept(st, cuts, candidate, None)
    sealed = p.verified(read_json(root / 'sealed.json'), 'acceptance-sealed')
    assert set(sealed['packages']) == {'candidate', 'parent', 'card'}
    assert sealed['corpus'] is None and sealed['placebo_y'] is None
    assert sealed['reuse']['card_sample']['coverage'] == 'full_independent_astar'
    assert result['decision'] in ('accept', 'reject')
    assert result['cells'] >= 300
    attempt = root / ('attempt-2' if resume_after_seal else 'attempt-1')
    records = [read_json(path) for path in (attempt / 'cells').glob('*.json')]
    assert {'P_y', 'P_i'}.isdisjoint(row['cell']['arm'] for row in records)
    card_cells = [row for row in records if row['cell']['arm'] == 'C']
    assert len(card_cells) == 100 and all(row['shared_with'] is None for row in card_cells)
    calls = len(fake_solver.requests)
    assert step._accept(st, cuts, candidate, None) == result
    assert len(fake_solver.requests) == calls
