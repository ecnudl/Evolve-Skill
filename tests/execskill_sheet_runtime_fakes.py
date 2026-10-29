"""Authored v7 qualification records; real binding validation, no Docker execution."""
from pathlib import Path

import pytest

from skillopt.continual_eval import backends, sheet_recalc_v7
from skillopt.continual_eval.core import write_json
from tests.test_continual_eval_sheet_numeric_adapter import qualified_fixture


def make_runtime(root, monkeypatch):
    """A real-schema qualification with authored control judgments and image readiness.

    The existing fixture retains the actual current scorer's absolute source
    identity and all 23 sealed control/receipt bindings. Neither qualified_engine
    nor readiness is replaced; only the image-inspection boundary is supplied.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    runtime, _ = qualified_fixture(root, monkeypatch)
    monkeypatch.setattr(backends, '_image_ready', lambda value: {
        'status': 'ready', 'reason': 'authored_pinned_image_inspection', 'image_id': value['image']})
    monkeypatch.setattr(sheet_recalc_v7.Recalculator, 'run',
                        lambda *args, **kwargs: pytest.fail('Qualification validation must not run Calc'))
    path = root / 'sheet-runtime.json'
    write_json(path, runtime)
    return path
