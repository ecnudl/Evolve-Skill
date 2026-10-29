"""The real child selftest-to-S0 connection, with only sandbox I/O authored locally."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts import run_execskill
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import manifest, prelaunch, profiles as p, s0, smoke, v211_smoke as v
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.fixtures.execskill.items import alfworld_items, spreadsheetbench_items
from tests.test_execskill_smoke import escape_report
from tests.test_execskill_v210_manifest import consent
from tests.test_execskill_v211_manifest import ROOT, prepared, reseal


def preparation(root, monkeypatch):
    _, original = prepared(root, monkeypatch)
    alf = root / 'alf-pool.json'
    write_json(alf, [dict(item, room='authored-room', part='fresh') for item in alfworld_items(root / 'alf')])
    original['data']['pools']['alfworld'] = {'path': str(alf), 'sha256': v._sha(alf)}
    books = spreadsheetbench_items(root / 'books', count=2)
    entry = original['data']['pools']['spreadsheetbench']
    items = read_json(entry['path'])
    for item, workbook in zip(items, books):
        item['public']['input_files'] = workbook['public']['input_files']
    entry['path'] = str(root / 'sheet-selftest-pool.json')
    write_json(entry['path'], items)
    entry['sha256'] = v._sha(entry['path'])
    source = root / 'selftest-preparation.json'
    write_json(source, reseal(original))
    paths = [Path(item['public']['input_files'][0]) for item in books]
    return source, max(paths, key=lambda path: path.stat().st_size)


def sandbox_io(monkeypatch, workbook, *, native_result=None):
    """Replace only the Docker transport and worker handshake, never a receipt/measurement adapter."""
    result = {'returncode': 0, 'peak_rss_kib': 417_024} if native_result is None else native_result
    seen = {'argv': [], 'native_inputs': [], 'worker_options': [], 'closed': 0}

    class Docker:
        binary = 'docker'

        def run(self, argv, timeout):
            seen['argv'].append(argv)
            if argv[1] != 'run':
                return sandbox.Completed(0, b'')
            if argv[-1] == '/runner/escape_probe.py':
                return sandbox.Completed(0, json.dumps(escape_report()).encode())
            assert argv[-1] == '/input/worker.py' and timeout == s0.NATIVE_SECONDS
            assert {'--network=none', '--read-only', '--memory=4096m', '--cpus=1'} <= set(argv)
            mount = next(value for value in argv if value.startswith('type=bind,source='))
            folder = Path(mount.split('source=', 1)[1].split(',target=', 1)[0])
            assert (folder / 'worker.py').read_text() == s0.NATIVE_PROBE
            seen['native_inputs'].append((folder / 'input.xlsx').read_bytes())
            assert seen['native_inputs'][-1] == workbook.read_bytes()
            return sandbox.Completed(0, json.dumps(result).encode())

    class Worker:
        def __init__(self, **options):
            seen['worker_options'].append(options)

        def start(self, package, *, kind):
            assert kind == 'cell' and package.procedures == ()
            return self

        def ping(self):
            return {'vsz_kib': 173_792, 'rss_kib': 111_932}

        def close(self):
            seen['closed'] += 1

    monkeypatch.setattr(sandbox, 'Docker', Docker)
    monkeypatch.setattr(sandbox, 'Worker', Worker)
    return seen


def command(argv):
    args = run_execskill.parser().parse_args(argv)
    return run_execskill.HANDLERS[args.command](args)


def test_real_selftest_cli_receipt_is_accepted_by_s0_cli(tmp_path, monkeypatch):
    source, workbook = preparation(tmp_path, monkeypatch)
    seen = sandbox_io(monkeypatch, workbook)
    out, run = tmp_path / 'selftest', tmp_path / 'run'
    consent(run, p.MAIN_V4)
    assert command(['v211-selftest', '--preparation', str(source), '--out', str(out)]) == 0
    tested = p.verified(read_json(out / smoke.SELFTEST), 'sandbox-selftest')
    inherited = p.verified(read_json(out / 'worker-selftest' / smoke.SELFTEST), 'sandbox-selftest')
    assert tested['passed'] and tested['escape_rows'] == {row: True for row in smoke.ESCAPE_ROWS}
    assert set(tested['measured']) == manifest.MEASURED_FIELDS
    assert tested['measured'] == {'vsz_kib': 173_792, 'rss_kib': 111_932,
        'view_bytes_p99': inherited['measured']['view_bytes_p99'], 'native_peak_rss_kib': 417_024}
    assert 'start_seconds' in inherited['measured'] and inherited['measured']['views'] > 0
    assert tested['measurement_sources']['worker_selftest']['record_sha256'] == inherited[p.RECORD_HASH]
    native = tested['measurement_sources']['native_peak']
    assert native['collector'] == 'skillopt.execskill.s0.native_peak'
    assert native['workbook'] == {'path': str(workbook), 'sha256': v._sha(workbook)}
    assert len(seen['native_inputs']) == seen['closed'] == 1
    options = seen['worker_options'][0]
    assert options['cleanup_grace_seconds'] == p.cleanup_grace_seconds(p.MAIN_V4)
    assert options['ready_timeout_seconds'] == p.ready_timeout_seconds(p.MAIN_V4)
    assert {path.stem for path in (out / 'training-views').glob('*.json')} == set(p.BENCHES)
    # The registered full suite belongs to the operator's S0, never inside a test.
    checked_calls = []
    monkeypatch.setattr(prelaunch, 'zero_call_checks', lambda source, **options:
        checked_calls.append((source, options)) or {'passed': True, 'summary': 'authored bounded check receipt'})
    assert command(['v211-s0', '--preparation', str(source), '--root', str(run),
        '--out', str(tmp_path / 's0'), '--snapshot', str(ROOT), '--selftest', str(out / smoke.SELFTEST)]) == 0
    checked = p.verified(read_json(tmp_path / 's0' / v.S0_FILE), 'v211-s0')
    assert checked['passed'] and checked['measured'] == tested['measured']
    assert checked['sandbox'] == tested[p.RECORD_HASH] and len(checked_calls) == 1
    assert not list(tmp_path.rglob('*unopened-test.json'))
    before = deepcopy(seen['argv'])
    with pytest.raises(ValueError, match='written once'):
        v.selftest(out, preparation_file=source)
    assert seen['argv'] == before


@pytest.mark.parametrize('native_result', [
    {'returncode': 1, 'peak_rss_kib': 417_024},
    {'returncode': 0, 'peak_rss_kib': None},
    {'returncode': 0, 'peak_rss_kib': 0},
])
def test_failed_or_missing_native_measurement_cannot_produce_child_receipt(tmp_path, monkeypatch, native_result):
    source, workbook = preparation(tmp_path, monkeypatch)
    seen = sandbox_io(monkeypatch, workbook, native_result=native_result)
    out = tmp_path / 'selftest'
    with pytest.raises(ValueError, match='native peak'):
        v.selftest(out, preparation_file=source)
    assert not (out / smoke.SELFTEST).exists()
    assert (out / 'worker-selftest' / smoke.SELFTEST).exists()
    assert len(seen['native_inputs']) == 1
    assert sum(argv[1] == 'rm' for argv in seen['argv']) == 2
