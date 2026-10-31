"""Main-v6 CLI, preparation and six-stage readiness on authored inputs only."""
from copy import deepcopy

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import manifest, profiles as p, v214_preparation, v214_smoke as v, v214_stages as stages
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests import test_execskill_v217i_smoke as implant
from tests.test_execskill_v214_preparation import prepared
from tests.test_execskill_v214_smoke import measured_probe, measured_s2

CHILD = p.MAIN_V6


def receipts(chain, m):
    probe = measured_probe(60000) if chain == 'D' else None
    bounds = v.solver_bounds(chain, probe, configuration=CHILD)
    s2 = {**measured_s2(), 'solver_bounds': bounds}
    s3 = {'passed': True, 'engineer_calls': 1, 'tokens': 100, 'solver_bounds': bounds}
    outputs = {'S0': {'passed': True},
        'S1': {'passed': True, 'solver_probe': probe, 'solver_bounds': bounds}, 'S2': s2, 'S3': s3,
        'SE6': stages.projection(s2, chain, s3=s3, bounds=bounds, configuration=CHILD),
        'SX': {'passed': True, 'model_calls': 0, 'solver_bounds': bounds}}
    rows = {name: p.record('v214-smoke-stage', 'smoke', {'configuration': CHILD,
        'chain': chain, 'stage': name, 'manifest_sha256': m[p.RECORD_HASH], 'measured': True,
        'schedule_sha256': digest(v.schedule(CHILD)), 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'result': output}) for name, output in outputs.items()}
    return p.record('v214-smoke-result', 'smoke', {'configuration': CHILD, 'chain': chain,
        'manifest_sha256': m[p.RECORD_HASH], 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'schedule_sha256': digest(v.schedule(CHILD)),
        'stages': {name: row[p.RECORD_HASH] for name, row in rows.items()}, 'stage_records': rows,
        'passed': True, 'sealed_reads': 0})


def test_preparation_keeps_parent_data_and_changes_only_zebra_machinery_and_freshness(tmp_path, monkeypatch):
    _, path, kwargs, _ = prepared(tmp_path, monkeypatch)
    parent = v214_preparation.preparation(path, **kwargs)
    child = v214_preparation.preparation(path, **kwargs, configuration=CHILD)
    expected = deepcopy(parent)
    expected['registration']['configuration'] = CHILD
    expected['confirm'] = {**parent['confirm'], 'configuration': p.ZEBRA_PC_V15,
        'freshness': p.confirm_freshness(CHILD, p.ZEBRA)}
    expected['data']['confirm'] = deepcopy(expected['confirm'])
    assert child == expected
    assert child['confirm']['configuration'] == p.ZEBRA_PC_V15
    assert child['confirm']['freshness'].endswith('_and_main_v5_G_D')
    assert v214_preparation.verify(child) == child


def test_s0_consent_runtime_worker_pins_and_real_manifest_gate(tmp_path, monkeypatch):
    from skillopt.execskill.sandbox.client import worker_sha256
    monkeypatch.setattr(implant, 'CHILD', CHILD)
    checked, made, options = implant.setup(tmp_path, monkeypatch)
    assert checked['configuration'] == made['configuration'] == CHILD
    assert checked['sealed_reads'] == 0
    assert checked['smoke_schedule']['stages'] == list(v.STAGES)
    assert read_json(tmp_path/'real/shared/consent.json') == implant.owner_consent()
    assert read_json(options['root']/'shared/consent.json') == implant.owner_consent()
    assert made['data']['launch_sheet_runtime']['snapshot_sha256'] == checked['snapshot_sha256']
    assert made['sandbox']['worker_sha256_by_bench'] == {
        b: worker_sha256(p.ZEBRA_PC_V15 if b == p.ZEBRA else None) for b in p.MAIN_V5_ORDER}
    assert manifest.check(made) == made
    options.update(smoke_chain=None, root=tmp_path/'real')
    monkeypatch.setitem(p.RUN_ROOTS, CHILD, str(options['root']))
    with pytest.raises(ValueError, match='both measured'):
        v.make_manifest(tmp_path/'refused.json', **options)
    paths = []
    for chain in ('G', 'D'):
        found = receipts(chain, made)
        checked, projected = v.checked_readiness(found, chain=chain,
            source_sha256=made['data']['snapshot_sha256'], s0_sha256=made['data']['s0_sha256'], configuration=CHILD)
        assert checked == found and projected['passed']
        assert set(projected['per_cell']) == set(p.MAIN_V5_ORDER)
        root = tmp_path/'measured'/chain
        for name, row in found['stage_records'].items(): write_json(root/(name+'.json'), row)
        path = root/v.RESULT
        write_json(path, found)
        paths.append(path)
    real = v.make_manifest(tmp_path/'real-manifest.json', measured_smoke=paths, **options)
    assert real['evidence'] == 'main_v6_real_run'
    assert real['data']['launchable_chains'] == ['G', 'D']
    assert manifest.check(real) == real


@pytest.mark.parametrize('change', [
    {'sheet_test_qualification': False}, {'test_evaluation': False}, {'by': 'agent'},
    {'multi_arm_arms': ['F', 'C']}, {'multi_arm_arms': ['C', 'F', 'B', 'stages']},
    {'date': ''}, {'note': ''}, {'extra': True},
])
def test_exact_owner_consent_is_written_before_launch(tmp_path, change):
    source = tmp_path/'consent.json'
    write_json(source, {**implant.owner_consent(), **change})
    with pytest.raises(ValueError, match='consent'):
        v.prepare_consent(tmp_path/'run', CHILD, consent_file=source)
    assert not (tmp_path/'run/shared/consent.json').exists()


def test_sx_and_structural_smoke_exercise_split_and_read_without_calls(tmp_path, monkeypatch):
    result = stages.sx(tmp_path/'sx', configuration=CHILD)
    assert result['passed'] and result['model_calls'] == result['sealed_reads'] == 0
    assert result['split']['adopted_by_split'] and result['read_reuse']['passed']
    assert result['stage_rows']['rows'] == ['C', 'C', 'S2', 'S2', 'S4', 'F']
    assert result['stage_rows']['sources']['officeqa']['S4']['stage-only'] == 'S2'
    assert stages.sx(tmp_path/'sx', configuration=CHILD) == result
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: {'configuration': CHILD, p.RECORD_HASH: 'a'*64})
    monkeypatch.setattr(manifest, 'verify_code', lambda *_: None)
    found = v.structural_smoke(tmp_path/'unread', out=tmp_path/'structural.json', configuration=CHILD)
    assert found['passed'] and not found['measured_readiness']
    assert found['model_calls'] == found['sealed_reads'] == 0


@pytest.mark.parametrize('action', ['snapshot','selftest','s0','manifest','structural-smoke','smoke-run','smoke-summary'])
def test_v214_cli_preserves_defaults_and_both_older_choices(action):
    from scripts.run_execskill import parser
    command = parser()._subparsers._group_actions[0].choices['v214-'+action]
    option = next(a for a in command._actions if a.dest == 'configuration')
    assert tuple(option.choices) == (p.MAIN_V5, p.IMPLANT_V5, CHILD)
    assert option.default == p.MAIN_V5


@pytest.mark.parametrize('configuration', [p.MAIN_V5, p.IMPLANT_V5, CHILD])
def test_cli_configuration_forwarding_and_main_v5_default(tmp_path, monkeypatch, configuration):
    from scripts.run_execskill import parser, v214_command
    calls = []
    monkeypatch.setattr(v, 'snapshot', lambda out, **kw: calls.append(kw) or {'passed': True})
    args = ['v214-snapshot','--out',str(tmp_path/'out'),'--source',str(tmp_path/'source'),'--git-head','a'*40]
    assert v214_command(parser().parse_args(args+['--configuration',configuration])) == 0
    expected = {'source':str(tmp_path/'source'),'git_head':'a'*40}
    if configuration != p.MAIN_V5: expected['configuration'] = configuration
    assert calls == [expected]
    assert v.stages_of(CHILD) == v.STAGES
