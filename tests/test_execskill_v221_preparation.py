"""Authored main-v7 S0/manifest/consent integration; no live inputs or clients."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import manifest, profiles as p, v214_preparation, v214_smoke as v
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests import test_execskill_v217i_smoke as inherited
from tests.test_execskill_v214_preparation import prepared
needs_capture = pytest.mark.skipif(not (Path(__file__).parent / 'fixtures/execskill/v221_parents_before.json').exists(),
                                   reason='parent capture not published (it holds ALFWorld game text)')

CHILD = p.MAIN_V7


def test_preparation_copies_main_v6_inputs_without_new_pool_reads(tmp_path, monkeypatch):
    _, source, kwargs, _ = prepared(tmp_path, monkeypatch)
    parent = v214_preparation.preparation(source, **kwargs, configuration=p.MAIN_V6)
    child = v214_preparation.preparation(source, **kwargs, configuration=CHILD)
    expected = deepcopy(parent)
    expected['registration']['configuration'] = CHILD
    assert child == expected
    assert v214_preparation.verify(child) == child


@needs_capture
def test_s0_binds_new_rule_prompts_caps_capture_and_inherited_worker_shapes(tmp_path, monkeypatch):
    from skillopt.execskill.sandbox.client import worker_sha256
    monkeypatch.setattr(inherited, 'CHILD', CHILD)
    checked, made, options = inherited.setup(tmp_path, monkeypatch)
    assert checked['configuration'] == made['configuration'] == CHILD
    assert checked['sealed_reads'] == 0
    assert checked['smoke_schedule']['stages'] == list(v.STAGES)
    assert checked['parents_before_sha256'] == hashlib.sha256(
        Path('tests/fixtures/execskill/v221_parents_before.json').read_bytes()).hexdigest()
    assert checked['prompt_pins'] == manifest.prompt_sha(CHILD)
    assert made['sizes']['v214']['decision_rule']['name'] == 'gain-and-no-harm-v2-21'
    assert made['sandbox']['worker_sha256_by_bench'] == {
        b: worker_sha256(p.ZEBRA_PC_V15 if b == p.ZEBRA else None) for b in p.MAIN_V5_ORDER}
    assert manifest.check(made) == made
    assert read_json(options['root'] / 'shared/consent.json') == inherited.owner_consent()
    options.update(smoke_chain=None, root=tmp_path / 'real')
    monkeypatch.setitem(p.RUN_ROOTS, CHILD, str(options['root']))
    with pytest.raises(ValueError, match='both measured'):
        v.make_manifest(tmp_path / 'refused.json', **options)


@pytest.mark.parametrize('change', [
    {'sheet_test_qualification': False}, {'test_evaluation': False}, {'by': 'agent'},
    {'multi_arm_arms': ['F', 'C']}, {'multi_arm_arms': ['C', 'F', 'B', 'stages']},
    {'date': ''}, {'note': ''}, {'extra': True},
])
def test_exact_main_v6_owner_consent_shape_is_preserved(tmp_path, change):
    supplied = tmp_path / 'owner.json'
    write_json(supplied, {**inherited.owner_consent(), **change})
    with pytest.raises(ValueError, match='consent'):
        v.prepare_consent(tmp_path / 'run', CHILD, consent_file=supplied)
    assert not (tmp_path / 'run/shared/consent.json').exists()


def test_new_prompt_is_pinned_and_older_prompt_records_stay_exact():
    from skillopt.execskill import engineer_v221
    old = manifest.prompt_sha(p.MAIN_V6)
    found = manifest.prompt_sha(CHILD)
    assert found['parents'] == old['parents']
    assert found['dispatch'] == old['dispatch']
    assert found['v221'] == engineer_v221.prompt_pins()
    for bench in p.MAIN_V5_ORDER[:-1]:
        for mode, block in (('single', found), ('train', found['v2'])):
            prompt = p.engineer_prompt(CHILD, bench, mode)
            assert block['engineer'][bench] == hashlib.sha256(prompt.encode()).hexdigest()
            assert block['engineer'][bench] != (old if mode == 'single' else old['v2'])['engineer'][bench]
    assert v.stages_of(CHILD) == ('S0', 'S1', 'S2', 'S3', 'SE6', 'SX')
