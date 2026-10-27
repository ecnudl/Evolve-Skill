"""Neutral OS scratch for v2.9.3 tests, including plain pytest without a plugin."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def tmp_path():
    root = Path(os.environ.get('TMPDIR') or '/tmp').resolve()
    repo = Path(__file__).resolve().parents[1]
    assert root != repo and not root.is_relative_to(repo)
    with TemporaryDirectory(prefix='identity-', dir=root) as directory:
        yield Path(directory).resolve()
