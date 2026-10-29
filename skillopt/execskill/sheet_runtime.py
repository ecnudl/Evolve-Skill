"""Snapshot-owned SpreadsheetBench qualification for v2.10 / v2.11 launches."""
from copy import deepcopy
import hashlib

from skillopt.continual_eval import sheet_numeric_adapter
from skillopt.continual_eval.core import read_json, require, safe_path
from skillopt.validator_pilot.api import digest
from . import prelaunch, qualify, profiles as p


def check(runtime, qualification=None, *, snapshot_root):
    """Revalidate the unchanged scorer and image readiness before any model work."""
    root = safe_path(snapshot_root)
    try:
        engine, record = sheet_numeric_adapter.qualified_engine(runtime)
        require(str(qualify.snapshot_root(engine.identity['sources'])) == str(root),
                'Qualification belongs to another source tree')
        ready = sheet_numeric_adapter.readiness(runtime)
        require(ready.get('status') is not None and ready['status'] != 'unsupported',
                'Scorer readiness is unsupported: ' + str(ready.get('reason')))
        pin = {'path': str(safe_path(runtime['recalculation']['qualification_path'])),
               'record_hash': record['record_hash']}
        require(qualification is None or qualification == pin, 'Qualification record pin differs')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('SpreadsheetBench qualification must match the current snapshot: ' + str(error)) from error
    return {'qualification': pin, 'snapshot_root': str(root),
            'snapshot_sha256': hashlib.sha256(prelaunch.sha256_list(root).encode()).hexdigest(),
            'engine_sha256': digest(engine.identity), 'readiness': ready['status']}


def read(path, *, snapshot_root):
    require(path is not None, '--sheet-runtime is required for a launch manifest')
    path = safe_path(path)
    runtime = read_json(path)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'runtime': runtime, **check(runtime, snapshot_root=snapshot_root)}


def inherited(imported):
    return {'runtime': deepcopy(imported['runtime']['spreadsheetbench']),
            'sheet_qualification': deepcopy(imported['sheet_qualification'])}


def for_manifest(path, s0, *, snapshot_root):
    require(isinstance(s0.get('launch_sheet_runtime'), dict),
            'S0 must be collected with --sheet-runtime before creating a manifest')
    current = read(path, snapshot_root=snapshot_root)
    require(current == s0['launch_sheet_runtime'], 'S0 and manifest --sheet-runtime identities differ')
    require(current['snapshot_sha256'] == s0['snapshot_sha256'],
            'Sheet qualification and S0 certify the same snapshot')
    return current


def verify_manifest(value, *, snapshot_root):
    """Load-time validation is restricted to the three instruction-start profiles."""
    data = value['data']
    bound = data.get('launch_sheet_runtime')
    require(isinstance(bound, dict), 'Manifest requires its S0 --sheet-runtime qualification')
    path = safe_path(bound['path'])
    require(hashlib.sha256(path.read_bytes()).hexdigest() == bound['sha256']
            and read_json(path) == bound['runtime'], 'The pinned --sheet-runtime file changed')
    runtime = value['runtime']['spreadsheetbench']
    expected = deepcopy(bound['runtime'])
    # The generic manifest writer retains the registered shell/extraction policy.
    if p.is_v23(value['configuration']):
        expected.update(code_extraction_version=p.CODE_EXTRACTION[value['configuration']],
                        multiple_python_blocks=p.MULTIPLE_PYTHON_BLOCKS[value['configuration']])
    require(runtime == expected, 'The manifest must use its pinned --sheet-runtime block')
    current = check(runtime, value['sheet_qualification'], snapshot_root=snapshot_root)
    require(all(bound.get(key) == found for key, found in current.items())
            and bound['snapshot_sha256'] == data.get('snapshot_sha256')
            and bound['snapshot_root'] == value['provenance']['snapshot_root'],
            'Sheet qualification and manifest certify the current snapshot')
    historical = data.get('inherited_sheet_runtime')
    require(isinstance(historical, dict) and set(historical) == {'runtime', 'sheet_qualification'},
            'Inherited sheet runtime and qualification are retained for provenance only')
    return bound
