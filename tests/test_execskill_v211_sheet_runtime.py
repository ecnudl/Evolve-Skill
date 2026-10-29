"""Snapshot-owned sheet qualification at CLI S0/manifest and manifest load."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from scripts import run_execskill
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, sheet_numeric_adapter
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import manifest, prelaunch, profiles as p, v211_smoke
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_sheet_runtime_fakes import make_runtime
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_manifest import MEASURED, fake_environment
from tests.test_execskill_v210_manifest import consent, preparation
from tests.test_execskill_v211_manifest import ROOT, prepared

CONFIGURATIONS = (p.BASELINE_V210, p.MAIN_V3, p.MAIN_V4)


def command(argv):
    args = run_execskill.parser().parse_args(argv)
    return run_execskill.HANDLERS[args.command](args)


def launch_inputs(root, monkeypatch, configuration):
    source, original = (prepared(root, monkeypatch) if configuration == p.MAIN_V4
                        else preparation(root / 'source', monkeypatch)[:2])
    env = fake_environment()
    monkeypatch.setattr(manifest, 'environment', lambda **kwargs: deepcopy(env))
    monkeypatch.setattr(manifest, 'REPO', ROOT)
    checked_calls = []
    monkeypatch.setattr(prelaunch, 'zero_call_checks', lambda *args, **kwargs:
        checked_calls.append((args, kwargs)) or {'passed': True, 'summary': 'authored bounded fixture checks'})
    runtime = make_runtime(root / 'own-qualification', monkeypatch)
    run = root / 'run'
    consent(run, configuration)
    prefix = 'v211' if configuration == p.MAIN_V4 else 'v210'
    extra = [] if configuration == p.MAIN_V4 else ['--configuration', configuration]
    s0 = [prefix + '-s0', *extra, '--out', str(root / 's0'), '--root', str(run),
          '--preparation', str(source), '--snapshot', str(ROOT)]
    if configuration != p.BASELINE_V210:
        tested = root / 'selftest.json'
        write_json(tested, p.record('sandbox-selftest', 'smoke', {'passed': True,
            'measured': MEASURED, 'limits': {key: asdict(value) for key, value in sandbox.LIMITS.items()}}))
        s0 += ['--selftest', str(tested)]
    made = [prefix + '-manifest', *extra, '--out', str(root / 'manifest.json'), '--root', str(run),
            '--s0', str(root / 's0' / (prefix + '-s0.json')), '--provenance', str(root / 'provenance.json'),
            '--roles-repo', str(root / 'roles'), '--route-b-env', str(root / 'route.env'), '--smoke-chain', 'G']
    return {'runtime': runtime, 'original': original, 's0_command': s0, 'manifest_command': made,
            'checks': checked_calls, 's0_file': root / 's0' / (prefix + '-s0.json')}


def finish_s0(root, launch, *, with_runtime=True):
    argv = launch['s0_command'] + (['--sheet-runtime', str(launch['runtime'])] if with_runtime else [])
    assert command(argv) == 0
    checked = read_json(launch['s0_file'])
    write_json(root / 'provenance.json', {'build_tree': str(ROOT), 'git_head': 'f' * 40,
        'snapshot_root': str(ROOT), 'sha256_list_sha256': checked['snapshot_sha256'], 'env_files_absent': True})
    return checked


def foreign_qualification(runtime_path, root):
    """Make the sealed fixture name identical scorer bytes under another tree."""
    runtime = read_json(runtime_path)
    qualification_path = Path(runtime['recalculation']['qualification_path'])
    protocol_path = qualification_path.parent / 'protocol.json'
    protocol = read_json(protocol_path, sealed=True)
    qualification = read_json(qualification_path, sealed=True)
    sources = protocol['engine']['sources']
    foreign = {str(root / Path(path).relative_to(ROOT)): value for path, value in sources.items()}
    protocol['engine']['sources'] = foreign
    protocol.pop('record_hash')
    protocol = seal(protocol)
    protocol_path.write_text(json.dumps(protocol))
    qualification['engine']['sources'] = foreign
    qualification['protocol_hash'] = protocol['record_hash']
    qualification.pop('record_hash')
    qualification = seal(qualification)
    qualification_path.write_text(json.dumps(qualification))
    runtime['recalculation'].update(qualification_hash=qualification['record_hash'],
                                   qualification_sha256=manifest._sha(qualification_path))
    runtime_path.write_text(json.dumps(runtime))


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_cli_s0_to_manifest_accepts_snapshot_owned_qualification(tmp_path, monkeypatch, configuration):
    launch = launch_inputs(tmp_path, monkeypatch, configuration)
    runtime = read_json(launch['runtime'])
    engine, qualification = sheet_numeric_adapter.qualified_engine(runtime)
    assert len(qualification['controls']) == 23
    checked = finish_s0(tmp_path, launch)
    assert checked['launch_sheet_runtime']['snapshot_root'] == str(ROOT)
    assert checked['launch_sheet_runtime']['runtime'] == runtime
    assert len(launch['checks']) == 1
    assert command(launch['manifest_command'] + ['--sheet-runtime', str(launch['runtime'])]) is None
    made = manifest.load(tmp_path / 'manifest.json', verify=False)
    assert made['runtime']['spreadsheetbench']['recalculation'] == runtime['recalculation']
    assert made['sheet_qualification'] == {'path': runtime['recalculation']['qualification_path'],
                                            'record_hash': qualification['record_hash']}
    assert made['data']['launch_sheet_runtime'] == checked['launch_sheet_runtime']
    assert made['data']['inherited_sheet_runtime'] == {
        'runtime': launch['original']['runtime']['spreadsheetbench'],
        'sheet_qualification': launch['original']['sheet_qualification']}
    assert engine.identity['sources']
    for bench in ('searchqa', 'officeqa', 'livemath'):
        assert made['runtime'][bench] == launch['original']['runtime'][bench]


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_s0_refuses_foreign_qualification_before_checks(tmp_path, monkeypatch, configuration):
    launch = launch_inputs(tmp_path, monkeypatch, configuration)
    foreign_qualification(launch['runtime'], tmp_path / 'different-snapshot')
    with pytest.raises(ValueError, match='(?i)(sheet|qualification|snapshot)'):
        command(launch['s0_command'] + ['--sheet-runtime', str(launch['runtime'])])
    assert not launch['checks'] and not launch['s0_file'].exists()


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_manifest_refuses_foreign_qualification_before_writing(tmp_path, monkeypatch, configuration):
    launch = launch_inputs(tmp_path, monkeypatch, configuration)
    finish_s0(tmp_path, launch)
    foreign_qualification(launch['runtime'], tmp_path / 'different-snapshot')
    with pytest.raises(ValueError, match='(?i)(sheet|qualification|snapshot)'):
        command(launch['manifest_command'] + ['--sheet-runtime', str(launch['runtime'])])
    assert not (tmp_path / 'manifest.json').exists()


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_load_revalidates_qualification_against_current_snapshot(tmp_path, monkeypatch, configuration):
    launch = launch_inputs(tmp_path, monkeypatch, configuration)
    finish_s0(tmp_path, launch)
    command(launch['manifest_command'] + ['--sheet-runtime', str(launch['runtime'])])
    # Keep the pinned runtime and qualification files byte-identical. Only the
    # qualification protocol's engine source identity moves to another tree;
    # the actual qualified_engine revalidation must discover this at load time.
    runtime = read_json(launch['runtime'])
    protocol_path = Path(runtime['recalculation']['qualification_path']).parent / 'protocol.json'
    protocol = read_json(protocol_path, sealed=True)
    protocol['engine']['sources'] = {str(tmp_path / 'different-snapshot' / Path(path).relative_to(ROOT)): value
                                    for path, value in protocol['engine']['sources'].items()}
    protocol.pop('record_hash')
    protocol_path.write_text(json.dumps(seal(protocol)))
    with pytest.raises(ValueError, match='current snapshot: Engine/source/image changed'):
        manifest.load(tmp_path / 'manifest.json', verify=False)


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_optional_s0_runtime_omission_cannot_authorize_manifest(tmp_path, monkeypatch, configuration):
    launch = launch_inputs(tmp_path, monkeypatch, configuration)
    checked = finish_s0(tmp_path, launch, with_runtime=False)
    assert checked.get('launch_sheet_runtime') is None
    with pytest.raises(ValueError, match='(?i)(sheet|qualification|snapshot)'):
        command(launch['manifest_command'] + ['--sheet-runtime', str(launch['runtime'])])
    assert not (tmp_path / 'manifest.json').exists()


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_unsupported_image_readiness_stops_s0(tmp_path, monkeypatch, configuration):
    launch = launch_inputs(tmp_path, monkeypatch, configuration)
    monkeypatch.setattr(backends, '_image_ready', lambda runtime:
                        {'status': 'unsupported', 'reason': 'authored_missing_image'})
    with pytest.raises(ValueError, match='(?i)(sheet|qualification|snapshot|unsupported)'):
        command(launch['s0_command'] + ['--sheet-runtime', str(launch['runtime'])])
    assert not launch['checks'] and not launch['s0_file'].exists()


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_manifest_cli_requires_sheet_runtime(tmp_path, monkeypatch, configuration):
    launch = launch_inputs(tmp_path, monkeypatch, configuration)
    with pytest.raises(SystemExit):
        run_execskill.parser().parse_args(launch['manifest_command'])


def test_old_historical_configuration_fingerprints_are_unchanged():
    history = v211_smoke.historical_fingerprints(ROOT)
    assert history['passed'] and history['count'] == 32
