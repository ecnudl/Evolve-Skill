"""Neutral OS scratch for v2.9.3 tests, including plain pytest without a plugin."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def tmp_path():
    root = Path(os.environ.get('TMPDIR') or '/tmp').resolve()
    repo = Path(__file__).resolve().parents[1]
    # A source-only audit may authorize writes only inside its working copy.
    # Any neutral scratch name is valid; protected panel names remain refused.
    assert root != repo and not any(word in root.name.lower()
        for word in ('test', 'final', 'holdout', 'reserve', 'sealed'))
    with TemporaryDirectory(prefix='identity-', dir=root) as directory:
        yield Path(directory).resolve()
