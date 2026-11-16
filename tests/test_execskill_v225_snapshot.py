"""Source snapshots retain all required tests; documentary paths are explicit."""
import ast
import builtins
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from skillopt.execskill import prelaunch, v210_smoke, v225_metrics
from tests.execskill_v225_snapshot_guard import audit_source, audit_tree, scan_source
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_v225_read import synthetic_aggregate

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/execskill'
POLICY = FIXTURES/'v225_snapshot_policy.json'
POLICY_SHA256 = '4d27aba30ba5886588ee9402c3e9b0ffec477ca300a8c34070154c6a477b43f1'
EXAMPLES = json.loads((FIXTURES/'v225_snapshot_examples.json').read_text())['cases']


def policy():
    raw = POLICY.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == POLICY_SHA256
    value = json.loads(raw)
    assert value['live_documentation_inputs_allowed'] is False
    assert value['scope'] == 'v225 test modules and v225 fixtures; literal and ordinary joined paths only'
    proofs = {node.name for path in (ROOT/'tests').glob('test_execskill_v225_*.py')
              for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef)}
    for row in value['documentary_exceptions'].values():
        assert row['live_input'] is False and row['reason'] and row['proof_tests']
        assert row['category'] in {'vendored_reference','operator_template','optional_deliverable_mirror','authored_negative_input'}
        assert set(row['proof_tests']) <= proofs
    return value


def test_every_v225_module_and_fixture_documentation_reference_is_registered_or_documentary():
    value = policy()
    result = audit_tree(ROOT,value)
    assert result['files'] >= 40
    assert not result['problems'], '\n'.join(result['problems'])
    assert all((ROOT/name).is_file() for name in value['documentary_exceptions'])
    assert len(result['findings']) > 10  # The fixture audit really visits dormant upstream references.


def test_only_the_actual_snapshot_kept_instruction_path_is_registered():
    value = policy()
    tree = ast.parse(Path(v210_smoke.__file__).read_text())
    snapshot = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name == 'snapshot')
    supplemental = next(node.value.right.value for node in ast.walk(snapshot)
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id == 'instruction_file'
                                              for target in node.targets))
    assert value['snapshot_kept_paths'] == [supplemental.split('/')]
    assert prelaunch.SNAPSHOT_DIRS == ('skillopt','scripts','tests')
    assert ROOT.joinpath(*value['snapshot_kept_paths'][0]).is_file()
    for module in (prelaunch,v210_smoke,v225_metrics):
        assert Path(module.__file__).resolve().is_relative_to(ROOT)


@pytest.mark.parametrize('case', [row for row in EXAMPLES if row['name'] != 'registered'], ids=lambda row:row['name'])
def test_guard_rejects_hidden_provenance_literals_joined_paths_and_unregistered_prose(case):
    problems, findings = audit_source(case['file'],case['source'],policy())
    assert findings and any('unregistered documentation reference' in problem for problem in problems)


def test_guard_accepts_only_registered_kept_path_and_exact_documentary_exception():
    value = policy()
    kept = next(row for row in EXAMPLES if row['name'] == 'registered')
    assert audit_source(kept['file'],kept['source'],value)[0] == []
    prose = next(row for row in EXAMPLES if row['name'] == 'new_prose')
    marked = deepcopy(value)
    marked['documentary_exceptions'][prose['file']] = {
        'sha256':hashlib.sha256(prose['source'].encode()).hexdigest(),
        'findings':[row['fingerprint'] for row in scan_source(prose['file'],prose['source'])],
        'reason':'Authored documentary example, never evaluated as a path.', 'live_input':False,
        'category':'authored_negative_input', 'proof_tests':['this authored scanner test']}
    assert audit_source(prose['file'],prose['source'],marked)[0] == []
    hidden = next(row for row in EXAMPLES if row['name'] == 'literal')
    errors,_ = audit_source(prose['file'],prose['source']+hidden['source'],marked)
    assert any('bytes changed' in error for error in errors)
    assert any('unregistered documentation reference' in error for error in errors)


def test_pinned_cl_import_and_actual_compute_never_access_documentation(monkeypatch,fast_statistics):
    accesses = []
    def guard(original):
        def wrapped(path,*args,**kwargs):
            if isinstance(path,(str,bytes,os.PathLike)) and 'docs' in Path(os.fsdecode(path)).parts:
                accesses.append(os.fsdecode(path))
                raise AssertionError('The tested CL path attempted an external documentary input')
            return original(path,*args,**kwargs)
        return wrapped
    for module,name in ((builtins,'open'),(io,'open'),(os,'open'),(os,'stat'),(os,'lstat')):
        monkeypatch.setattr(module,name,guard(getattr(module,name)))
    v225_metrics.reference.cache_clear()
    reference = v225_metrics.reference()
    assert Path(reference.__file__).resolve().is_relative_to(FIXTURES)
    for name in ('main','load_json','first_existing','sha16'):
        monkeypatch.setattr(reference,name,lambda *_args,**_kwargs:pytest.fail('Dormant reference CLI/input reader was invoked'))
    aggregate = synthetic_aggregate()
    result = v225_metrics.compute(aggregate,'G')
    chain = reference.chains_from_readout(aggregate,'main-v9','authored')['G']
    for analysis in ('P','S'):
        assert result['anchor_C'][analysis] == reference.cl_metrics(chain,analysis,result['similar'])
    assert result['reference_sha256'] == '587883bf35392fd3d7739fce98407519515c2090fa4eef705d4b5f59bfb0a994'
    assert accesses == []
