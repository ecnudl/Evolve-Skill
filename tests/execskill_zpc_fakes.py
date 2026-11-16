"""Temporary pool paths without the reserved tokens enforced by the Zebra reader."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os

import pytest


@pytest.fixture
def tmp_path():
    # pytest's default directory includes "test"; success-path pool fixtures need a neutral path.
    with TemporaryDirectory(prefix="zpc-", dir=os.environ.get('TMPDIR') or '/tmp') as directory:
        yield Path(directory).resolve()
