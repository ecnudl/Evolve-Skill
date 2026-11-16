"""Real main-v9 labels pass each production constructor without services."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from skillopt.execskill import cells, engines, precheck, profiles as p, registry
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


@pytest.mark.parametrize('evidence', ['main_v9_real_run', 'main_v8_real_run', 'engineering_fixture'])
def test_real_evidence_reaches_cells_consumption_sheet_engines_and_precheck(tmp_path, evidence):
    context = cells.Context(attempt=tmp_path/'attempt-1', endpoint=None, runtime={}, cards={},
        native=None, episodes=None, worker=None, evidence=evidence)
    assert context.evidence == evidence
    history = registry.Registry(tmp_path/'history', evidence=evidence)
    assert history.evidence == evidence
    native = SimpleNamespace(hold=lambda *_a, **_k: nullcontext())
    engine = engines.sheet_engines({}, native=native, evidence=evidence)
    assert engine.qualify.keywords['evidence'] == evidence
    assert precheck.report('ok', evidence=evidence)['evidence'] == evidence


@pytest.mark.parametrize('constructor', ['cell', 'registry', 'engine', 'precheck'])
def test_unknown_evidence_still_fails_closed(tmp_path, constructor):
    invalid = 'main_v11_real_run'
    with pytest.raises(ValueError):
        if constructor == 'cell':
            cells.Context(attempt=tmp_path/'attempt-1', endpoint=None, runtime={}, cards={},
                native=None, episodes=None, worker=None, evidence=invalid)
        elif constructor == 'registry':
            registry.Registry(tmp_path/'history', evidence=invalid)
        elif constructor == 'engine':
            engines.sheet_engines({}, native=SimpleNamespace(hold=lambda: nullcontext()), evidence=invalid)
        else:
            precheck.report('ok', evidence=invalid)


def test_frozen_evidence_table_is_unchanged():
    assert 'main_v9_real_run' not in p.EVIDENCE
    assert 'main_v8_real_run' in p.EVIDENCE
