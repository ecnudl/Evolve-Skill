"""Deterministic public inputs for main-v10's resumable request plans."""
from __future__ import annotations

import hashlib


def workbook_digests(bench, publics):
    """Bind complete public workbook bytes, including cells outside the preview.

    Preserve item and input-file order and use the same byte adapter as the
    sandbox mount. This also binds later public workbooks solved by an item.
    """
    if bench != 'spreadsheetbench':
        return {}
    from . import solver, v226_candidates
    with v226_candidates.arm('system'):
        return {key: [hashlib.sha256(solver._xlsx_bytes(path)).hexdigest()
                      for path in solver._public_view(bench, public)['input_files']]
                for key, public in publics.items()}


def json_observations(value):
    """Give fresh and resumed coverage consumers the identical JSON shape."""
    if isinstance(value, dict):
        return {key: json_observations(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [json_observations(item) for item in sorted(value)]
    if isinstance(value, (tuple, list)):
        return [json_observations(item) for item in value]
    return value
