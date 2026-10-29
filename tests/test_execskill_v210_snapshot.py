"""Bounded snapshot membership and collection checks; full execution belongs to S0."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pytest

from skillopt.execskill import prelaunch, profiles, v210_smoke

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = (profiles.BASELINE_V210, profiles.MAIN_V3)
INSTRUCTION = Path('docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json')


def _files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()
            and path.name not in ('snapshot-provenance.json', 'sha256-list.txt')}


def _registered_files(root):
    return sorted(path.relative_to(root).as_posix()
                  for pattern in prelaunch.TEST_FILES for path in root.glob(pattern))


def _collect(snapshot):
    command = [sys.executable, '-B', '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider',
               *_registered_files(snapshot)]
    env = prelaunch.launch_env()
    env.update(PYTHONPATH=str(snapshot), OPENPYXL_LXML='False')
    for name in ('PYTEST_PLUGINS', 'PYTEST_ADDOPTS'):
        env.pop(name, None)
    done = subprocess.run(command, cwd=snapshot, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=120, check=False, text=True)
    assert done.returncode == 0, done.stdout
    assert not re.search(r'ERROR collecting|\b[1-9]\d* errors?\b', done.stdout, re.IGNORECASE), done.stdout
    collected = re.search(r'(?m)^(\d+) tests? collected\b.*$', done.stdout)
    assert collected and int(collected.group(1)) > 0, done.stdout
    return {'command': command, 'returncode': done.returncode, 'summary': collected.group(0),
            'tests_collected': int(collected.group(1))}


@pytest.fixture(scope='module')
def registered_snapshot_checks():
    with tempfile.TemporaryDirectory(prefix='execskill-v210-snapshot-',
                                     dir=os.environ.get('TMPDIR') or '/tmp') as directory:
        scratch = Path(directory).resolve()
        snapshots = {configuration: scratch / configuration for configuration in CONFIGURATIONS}
        registered = _registered_files(ROOT)
        assert registered
        checks = {}
        for configuration, target in snapshots.items():
            v210_smoke.snapshot(target, source=ROOT, git_head='a' * 40, configuration=configuration)
            assert _registered_files(target) == registered
            assert all((target / path).is_file() for path in registered)
            assert (target / INSTRUCTION).is_file()
            assert sorted(path.relative_to(target).as_posix()
                          for path in (target / INSTRUCTION.parent.parent).rglob('*') if path.is_file()) == [
                              INSTRUCTION.as_posix()]
            checks[configuration] = _collect(target)
        baseline, main = (snapshots[configuration] for configuration in CONFIGURATIONS)
        assert _files(baseline) == _files(main)
        yield snapshots, checks


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_snapshot_collects_the_registered_zero_call_checks(configuration, registered_snapshot_checks):
    snapshots, checks = registered_snapshot_checks
    assert snapshots[configuration].is_dir()
    assert checks[configuration]['returncode'] == 0


def test_registered_modules_do_not_depend_on_handoff_files():
    references = []
    pattern = re.compile(r'docs[/\\]handoff|V210[-]')
    for path in sorted((ROOT / 'tests').glob('test_execskill_*.py')):
        source = path.read_text(encoding='utf-8').replace(INSTRUCTION.as_posix(), '')
        references.extend(f'{path.relative_to(ROOT)}:{number}: {line.strip()}'
                          for number, line in enumerate(source.splitlines(), 1) if pattern.search(line))
    assert not references, '\n'.join(references)
