"""main-v4 fixture materialization with the frozen ElementTree workbook writer.

A fresh interpreter selects the serializer before openpyxl import. This keeps
historical fixture code and bytes intact even when the caller has loaded lxml.
The child record discloses the serializer and binds the inherited fixture hash.
"""
import os
import subprocess
import sys

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from . import fixtures, profiles as p

RECORD = 'v211-fixtures.json'


def make(root):
    root = safe_path(root)
    recipe = 'from skillopt.execskill import fixtures; import sys; fixtures.make_fixtures(sys.argv[1])'
    source = str(__import__('pathlib').Path(__file__).resolve().parents[2])
    result = subprocess.run([sys.executable, '-c', recipe, str(root)], cwd=source,
        env={**os.environ, 'OPENPYXL_LXML': 'False', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': source},
        text=True, capture_output=True, timeout=120)
    require(result.returncode == 0, 'Child authored fixture materialization failed: ' + result.stderr[-1000:])
    fixtures.verify(root)
    parent = read_json(root / fixtures.RECORD_FILE)
    value = p.record('v211-fixtures', 'engineering_fixture', {'configuration': p.MAIN_V4,
        'serializer': 'OPENPYXL_LXML=False', 'inherited_recipe': 'fivebench-execskill-v1-fixtures',
        'fixture_record_sha256': parent[p.RECORD_HASH], 'model_calls': 0, 'external_calls': 0})
    if (root / RECORD).exists():
        require(read_json(root / RECORD) == value, 'The child fixture identity is immutable')
    else:
        write_json(root / RECORD, value)
    return value


def verify(root):
    root = safe_path(root)
    fixtures.verify(root)
    value = p.verified(read_json(root / RECORD), 'v211-fixtures')
    require(value['configuration'] == p.MAIN_V4 and value['serializer'] == 'OPENPYXL_LXML=False'
        and value['fixture_record_sha256'] == read_json(root / fixtures.RECORD_FILE)[p.RECORD_HASH],
        'The child fixture serializer and inherited artifact identity are pinned')
    return value
