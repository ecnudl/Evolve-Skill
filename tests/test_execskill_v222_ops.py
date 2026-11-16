"""Operator templates are inspected locally; no deployment or external calls."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPS = Path(__file__).resolve().parent / 'fixtures/execskill/v222_ops'
MANIFEST_SHA256 = '098d96e8420a8ce64f5ef972aa8134584dfee41d14344b6a6a7481a749951eba'
SCRIPTS = ('m8-env.sh', 'm8-prep.sh', 'm8-smoke.sh', 'm8-launch.sh', 'm8-run.sh',
           'run-v222-pre.sh', 'commit-v222.sh')


@pytest.fixture
def tmp_path():
    """Use a plain scratch directory in both source and self-contained snapshots."""
    with tempfile.TemporaryDirectory(prefix='ops-', dir=os.environ.get('TMPDIR') or '/tmp') as directory:
        yield Path(directory).resolve()


def test_operator_fixture_is_pinned_and_equals_source_deliverables_when_available():
    raw = (OPS / 'manifest.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256
    pinned = json.loads(raw)
    assert pinned['configuration'] == 'main-v8' and pinned['executed_operations'] is False
    assert set(pinned['files']) == {*SCRIPTS, 'patch-consent-v222.py'}
    source = ROOT.joinpath(*pinned['source_directory'])
    for name, sha in pinned['files'].items():
        raw = (OPS / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == sha
        deliverable = source / name
        # Code snapshots may include only some files from the handoff directory.
        if deliverable.is_file():
            assert deliverable.read_bytes() == raw


@pytest.mark.parametrize('documentation', ['absent', 'partial', 'mismatch'])
def test_ops_are_self_contained_snapshot_with_optional_documentation(tmp_path, documentation):
    snapshot = tmp_path / 'snapshot'
    fixture = snapshot / 'tests/fixtures/execskill/v222_ops'
    shutil.copytree(OPS, fixture)
    module = snapshot / 'tests' / Path(__file__).name
    shutil.copy2(__file__, module)
    assert {path.name for path in snapshot.iterdir()} == {'tests'}
    if documentation != 'absent':
        source = snapshot.joinpath(*json.loads((OPS / 'manifest.json').read_text())['source_directory'])
        source.mkdir(parents=True)
        for name in ('m8-env.sh', 'patch-consent-v222.py'):
            shutil.copy2(OPS / name, source / name)
        assert not (source / 'commit-v222.sh').exists()
        if documentation == 'mismatch':
            with (source / 'm8-env.sh').open('ab') as stream:
                stream.write(b'\n# Authored mismatch in an available deliverable.\n')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(tmp_path), 'PYTHONPATH': str(snapshot)}
    env.pop('PYTEST_PLUGINS', None)
    env.pop('PYTEST_ADDOPTS', None)
    found = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        '--basetemp=' + str(tmp_path / 'runtime'), str(module.relative_to(snapshot)),
        '-k', 'not self_contained_snapshot'], cwd=snapshot, env=env, capture_output=True, text=True, timeout=60)
    if documentation == 'mismatch':
        assert found.returncode == 1, found.stdout + found.stderr
        assert re.search(r'\b1 failed, 22 passed, 3 deselected\b', found.stdout)
        assert 'AssertionError' in found.stdout and 'FileNotFoundError' not in found.stdout
    else:
        assert found.returncode == 0, found.stdout + found.stderr
        assert re.search(r'\b23 passed, 3 deselected\b', found.stdout)
    assert not list(snapshot.rglob('*.pyc')) and not list(snapshot.rglob('__pycache__'))


@pytest.mark.parametrize('name', SCRIPTS)
def test_operator_shell_templates_parse_without_executing(name):
    result = subprocess.run(['bash', '-n', str(OPS / name)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_python_c_bodies_use_single_quoted_strings_inside_outer_double_quotes():
    bodies = []
    for name in SCRIPTS:
        for line in (OPS / name).read_text().splitlines():
            if ' -c "' not in line:
                continue
            body = line.split(' -c "', 1)[1].split('"', 1)[0]
            ast.parse(body)
            assert '"' not in body
            bodies.append(body)
    assert len(bodies) >= 4


def check_last(log, tmp_path):
    env = {**os.environ, 'M8_PY': sys.executable, 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(tmp_path)}
    return subprocess.run(['bash', '-c', 'source "$1"; m8_check_last_line "$2"',
        'authored-check', str(OPS / 'm8-env.sh'), str(log)], env=env, capture_output=True, text=True)


@pytest.mark.parametrize('last,passes', [
    ('{"passed":true,"exit_code":0}', True),
    ('{"passed":false,"exit_code":0}', False),
    ('{"passed":true,"exit_code":3}', False),
    ('{"status":"complete"}', False),
    ('truncated record', False),
    ('', False),
])
def test_driver_judges_last_log_line_not_an_earlier_success(tmp_path, last, passes):
    log = tmp_path / 'authored.log'
    log.write_text('{"passed":true,"exit_code":0}\n' + last + '\n')
    assert (check_last(log, tmp_path).returncode == 0) is passes


def test_cli_and_smoke_commands_are_main_v8_and_all_stages_are_present():
    prep, smoke, launch, run = [(OPS / n).read_text() for n in
                              ('m8-prep.sh', 'm8-smoke.sh', 'm8-launch.sh', 'm8-run.sh')]
    assert '--configuration main-v8' in prep and '--configuration main-v7' not in prep
    assert 'for chain in G D' in smoke and 'for stage in S0 S1 S2 S3 SE6 SX' in smoke
    assert '--configuration main-v8' in launch and launch.count('--measured-smoke') == 2
    assert 'm8_step "run-$chain" m8_cli run' in run
    assert 'tail -n' not in run  # the shared final-line parser is the only decision path
    pre = (OPS / 'run-v222-pre.sh').read_text()
    assert 'tests/test_execskill_*.py tests/test_weak_solver_probe.py' in pre
    assert 'rows[-1]' in pre and '-p no:cacheprovider' in pre


def patcher():
    spec = importlib.util.spec_from_file_location('v222_consent_template', OPS / 'patch-consent-v222.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_consent_patch_extends_one_reviewed_whitelist_without_writing_consent():
    source = "from skillopt.execskill.profiles import read_arms_of\nALLOWED = ('main-v6', 'main-v7')\n"
    value = patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                           whitelist_line="ALLOWED = ('main-v6', 'main-v7')")
    assert value == source.replace("'main-v7')", "'main-v7', 'main-v8')")
    assert 'test_evaluation' not in value and 'by' not in value


@pytest.mark.parametrize('problem', ['hash', 'line', 'not-whitelist', 'no-arms-dispatch', 'already-child'])
def test_consent_patch_refuses_unreviewed_or_ambiguous_writer(problem):
    line = "ALLOWED = ('main-v6', 'main-v7')"
    source = 'from skillopt.execskill.profiles import read_arms_of\n' + line + '\n'
    if problem == 'not-whitelist':
        line = "ALLOWED = 'main-v7'"
        source = 'from skillopt.execskill.profiles import read_arms_of\n' + line + '\n'
    if problem == 'no-arms-dispatch':
        source = line + '\n'
    if problem == 'already-child':
        source += "OTHER = 'main-v8'\n"
    digest = hashlib.sha256(source.encode()).hexdigest()
    with pytest.raises(AssertionError):
        patcher().patch(source, sha256='0' * 64 if problem == 'hash' else digest,
                        whitelist_line='missing' if problem == 'line' else line)


def test_commit_template_is_explicitly_approved_and_stages_only_the_reviewed_list():
    text = (OPS / 'commit-v222.sh').read_text()
    assert 'TEMPLATE ONLY' in text and 'V222_COMMIT_AUTHORIZATION' in text
    commands = [line for line in text.splitlines() if line.startswith('git add ')]
    assert len(commands) == 1 and commands[0].startswith('git add --pathspec-from-file=')
    assert Path(commands[0].split('=', 1)[1]).name == 'V222-CHANGED-FILES.txt'
    assert 'git add .' not in text and 'git push' not in text
    assert 'git diff --cached --name-only' in text
