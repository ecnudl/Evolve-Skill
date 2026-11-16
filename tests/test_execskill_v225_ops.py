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
OPS = Path(__file__).resolve().parent / 'fixtures/execskill/v225_ops'
MANIFEST_SHA256 = 'b210767b7e1737ff825e58290a091670596bcdede420ad018eaf6782502b1a44'
SCRIPTS = ('m9-env.sh', 'm9-prep.sh', 'm9-smoke.sh', 'm9-launch.sh', 'm9-run.sh', 'm9-go.sh',
           'run-v225-pre.sh', 'commit-v225.sh')


@pytest.fixture
def tmp_path():
    """Use a plain scratch directory in both source and self-contained snapshots."""
    with tempfile.TemporaryDirectory(prefix='ops-', dir=os.environ.get('TMPDIR') or '/tmp') as directory:
        yield Path(directory).resolve()


def test_operator_fixture_is_pinned_independently_of_documentary_deliverables():
    raw = (OPS / 'manifest.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256
    pinned = json.loads(raw)
    assert pinned['configuration'] == 'main-v9' and pinned['executed_operations'] is False
    assert set(pinned['files']) == {*SCRIPTS, 'patch-consent-v225.py', 'm9-alone.py'}
    for name, sha in pinned['files'].items():
        raw = (OPS / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == sha
    assert pinned['snapshot_optional_prose']['source_directory'].startswith('Optional source-deliverable mirror only;')


def test_optional_documentary_source_mirror_matches_available_deliverables():
    pinned = json.loads((OPS / 'manifest.json').read_text())
    source = ROOT.joinpath(*pinned['source_directory'])
    missing = []
    for name in pinned['files']:
        deliverable = source/name
        if deliverable.is_file():
            assert deliverable.read_bytes() == (OPS/name).read_bytes()
        else:
            missing.append(name)
    if missing:
        pytest.skip('Optional documentary source-deliverable mirror is absent from this source snapshot')


@pytest.mark.parametrize('documentation', ['absent', 'partial', 'mismatch'])
def test_ops_are_self_contained_snapshot_with_optional_documentation(tmp_path, documentation):
    # The nested authored shared-scratch fixture must also have a traversable parent.
    tmp_path.chmod(0o755)
    snapshot = tmp_path / 'snapshot'
    fixture = snapshot / 'tests/fixtures/execskill/v225_ops'
    shutil.copytree(OPS, fixture)
    module = snapshot / 'tests' / Path(__file__).name
    shutil.copy2(__file__, module)
    assert {path.name for path in snapshot.iterdir()} == {'tests'}
    if documentation != 'absent':
        source = snapshot.joinpath(*json.loads((OPS / 'manifest.json').read_text())['source_directory'])
        source.mkdir(parents=True)
        for name in ('m9-env.sh', 'patch-consent-v225.py'):
            shutil.copy2(OPS / name, source / name)
        assert not (source / 'commit-v225.sh').exists()
        if documentation == 'mismatch':
            with (source / 'm9-env.sh').open('ab') as stream:
                stream.write(b'\n# Authored mismatch in an available deliverable.\n')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(tmp_path), 'PYTHONPATH': str(snapshot)}
    env.pop('PYTEST_PLUGINS', None)
    env.pop('PYTEST_ADDOPTS', None)
    found = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        '--basetemp=' + str(tmp_path / 'runtime'), str(module.relative_to(snapshot)),
        '-k', 'not self_contained_snapshot'], cwd=snapshot, env=env, capture_output=True, text=True, timeout=60)
    if documentation == 'mismatch':
        assert found.returncode == 1, found.stdout + found.stderr
        assert '1 failed' in found.stdout and '3 deselected' in found.stdout
        assert 'AssertionError' in found.stdout and 'FileNotFoundError' not in found.stdout
    else:
        assert found.returncode == 0, found.stdout + found.stderr
        assert 'passed' in found.stdout and '3 deselected' in found.stdout
        assert 'skipped' in found.stdout
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
    env = {**os.environ, 'M9_PY': sys.executable, 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(tmp_path)}
    return subprocess.run(['bash', '-c', 'source "$1"; m9_check_last_line "$2"',
        'authored-check', str(OPS / 'm9-env.sh'), str(log)], env=env, capture_output=True, text=True)


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


def test_cli_and_smoke_commands_are_main_v9_and_all_stages_are_present():
    prep, smoke, launch, run = [(OPS / n).read_text() for n in
                              ('m9-prep.sh', 'm9-smoke.sh', 'm9-launch.sh', 'm9-run.sh')]
    assert '--configuration main-v9' in prep and '--configuration main-v8' not in prep
    assert 'for chain in G D' in smoke and 'for stage in S0 S1 S2 S3 SE6 SX' in smoke
    assert '--configuration main-v9' in launch and launch.count('--measured-smoke') == 2
    assert 'm9_step "run-$chain" m9_cli run' in run
    assert 'tail -n' not in run  # the shared final-line parser is the only decision path
    pre = (OPS / 'run-v225-pre.sh').read_text()
    assert 'tests/test_execskill_*.py tests/test_weak_solver_probe.py' in pre
    assert 'rows[-1]' in pre and '-p no:cacheprovider' in pre


def patcher():
    spec = importlib.util.spec_from_file_location('v225_consent_template', OPS / 'patch-consent-v225.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def writer_source():
    return ("from skillopt.execskill.profiles import read_arms_of\n"
            "ALLOWED = ('main-v6', 'main-v8')\n"
            "def make(configuration):\n"
            "    return {'multi_arm_arms': list(read_arms_of(configuration)), 'sheet_test_qualification': True}\n")


def test_consent_patch_extends_one_reviewed_whitelist_without_writing_consent():
    source = writer_source()
    value = patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                           whitelist_line="ALLOWED = ('main-v6', 'main-v8')")
    assert value == source.replace("'main-v8')", "'main-v8', 'main-v9')")
    assert 'test_evaluation' not in value and 'by' not in value
    assert patcher().EXPECTED_ARMS == ('B','C0','C','S1','S2','S3','S4','S5','I','C_end')


@pytest.mark.parametrize('problem', ['hash', 'line', 'not-whitelist', 'no-arms-dispatch',
                                      'already-child', 'no-sheet', 'false-sheet', 'duplicate-line'])
def test_consent_patch_refuses_unreviewed_or_ambiguous_writer(problem):
    line = "ALLOWED = ('main-v6', 'main-v8')"
    source = writer_source()
    if problem == 'not-whitelist':
        source = source.replace(line, "ALLOWED = 'main-v8'")
        line = "ALLOWED = 'main-v8'"
    if problem == 'no-arms-dispatch':
        source = source.replace('list(read_arms_of(configuration))', "['B', 'C']")
    if problem == 'already-child':
        source += "OTHER = 'main-v9'\n"
    if problem == 'no-sheet':
        source = source.replace("'sheet_test_qualification': True", "'unrelated': True")
    if problem == 'false-sheet':
        source = source.replace("'sheet_test_qualification': True", "'sheet_test_qualification': False")
    if problem == 'duplicate-line':
        source += line+'\n'
    digest = hashlib.sha256(source.encode()).hexdigest()
    with pytest.raises(AssertionError):
        patcher().patch(source, sha256='0' * 64 if problem == 'hash' else digest,
                        whitelist_line='missing' if problem == 'line' else line)


def test_commit_template_is_explicitly_approved_and_stages_only_the_reviewed_list():
    text = (OPS / 'commit-v225.sh').read_text()
    assert 'TEMPLATE ONLY' in text and 'V225_COMMIT_AUTHORIZATION' in text
    commands = [line for line in text.splitlines() if line.startswith('git add ')]
    assert len(commands) == 1 and commands[0].startswith('git add --pathspec-from-file=')
    assert Path(commands[0].split('=', 1)[1]).name == 'V225-CHANGED-FILES.txt'
    assert 'git add .' not in text and 'git push' not in text
    assert 'git diff --cached --name-only' in text


def test_launch_consent_and_first_reply_gate_precede_second_chain():
    launch = (OPS / 'm9-launch.sh').read_text()
    assert 'evaluation.consent' in launch and "p.MAIN_V9" in launch
    assert launch.index('m9_step consent') < launch.index('m9_step manifest')
    assert launch.index('m9-run.sh" G') < launch.index('m9_step first-reply') < launch.index('m9-run.sh" D')
    assert "record['checks']['reply'] is True" in launch
    assert "chain.confirmation(root, m[p.RECORD_HASH], 'G'" in launch and 'os.kill' in launch
    assert 'main-v9-reviewed-launch' in launch and 'chain.json' in launch
    run = (OPS / 'm9-run.sh').read_text()
    assert 'main-v9-reviewed-recovery' in run and 'recovery.json' in run


def test_full_suite_is_alone_and_cleans_owned_plain_scratch():
    pre = (OPS / 'run-v225-pre.sh').read_text()
    assert 'operator-confirmed-alone' in pre and 'flock -n 200' in pre
    guard = (OPS / 'm9-alone.py').read_text()
    assert 'evaluate-unit' in guard and 'step-unit' in guard and 'smoke-run' in guard
    assert '"$M9_OPS/m9-alone.py"' in pre
    assert '/tmp/execskill-machine.lock' in pre and 'M9_MACHINE_LOCK' in pre
    assert 'mktemp -d "$TMPDIR/suite-XXXXXX"' in pre
    assert 'trap ' not in pre and 'shutil.rmtree(cases)' in pre
    assert 'if passed:' in pre and 'scratch_preserved' in pre
    assert 'export TMPDIR="$M9_SUITE_SCRATCH"\nm9_prepare_scratch' in pre
    env = (OPS / 'm9-env.sh').read_text()
    assert 'export TMPDIR=/tmp/v225-pre' in env
    assert '/data/execskill-20261104-main-v9' in env
    go = (OPS / 'm9-go.sh').read_text()
    assert 'for phase in prep smoke launch' in go and 'm9_step "go-$phase"' in go


def python_block(script, marker):
    return (OPS/script).read_text().split("<<'"+marker+"'\n", 1)[1].split('\n'+marker, 1)[0]


def execute_block(script, marker, arguments, monkeypatch):
    """Only an extracted pure/local helper runs; no operator script is launched."""
    monkeypatch.setattr(sys, 'argv', ['authored-helper', *map(str, arguments)])
    exec(compile(python_block(script, marker), '<authored-operator-helper>', 'exec'), {'__name__': 'authored_helper'})


def test_scratch_helper_creates_sticky_shared_directory_without_requiring_root(tmp_path, monkeypatch):
    import stat
    tmp_path.chmod(0o755)
    scratch = tmp_path/'shared'
    scratch.mkdir(mode=0o700)
    execute_block('m9-env.sh', 'PY_SCRATCH', [scratch], monkeypatch)
    mode = stat.S_IMODE(scratch.stat().st_mode)
    assert mode == 0o1777 and mode & stat.S_IWOTH and mode & stat.S_IXOTH
    assert all(parent.stat().st_mode & stat.S_IXOTH for parent in scratch.parents)
    source = python_block('m9-env.sh', 'PY_SCRATCH')
    assert 'setuid' not in source and 'geteuid' not in source


@pytest.mark.parametrize('problem', ['mode', 'write_access', 'ancestor', 'symlink', 'plain_name'])
def test_scratch_helper_fails_closed_on_unusable_shared_access(tmp_path, monkeypatch, problem):
    tmp_path.chmod(0o755)
    scratch = tmp_path/'shared'
    if problem == 'plain_name':
        # Rejected before any protected-name directory is created or opened.
        scratch = tmp_path/'reserved'
    elif problem == 'symlink':
        target = tmp_path/'target'
        target.mkdir(mode=0o700)
        scratch.symlink_to(target, target_is_directory=True)
    else:
        scratch.mkdir(mode=0o700)
    if problem == 'mode':
        monkeypatch.setattr(os, 'chmod', lambda *_a, **_kw: None)
    elif problem == 'write_access':
        monkeypatch.setattr(os, 'access', lambda *_a, **_kw: False)
    elif problem == 'ancestor':
        tmp_path.chmod(0o700)
    with pytest.raises(AssertionError):
        execute_block('m9-env.sh', 'PY_SCRATCH', [scratch], monkeypatch)
    if problem == 'symlink':
        assert target.stat().st_mode & 0o777 == 0o700
    elif problem == 'plain_name':
        assert not scratch.exists()


@pytest.mark.parametrize('free_inodes,free_blocks,block_size,passed', [
    (170000, 100, 4096, True), (170001, 100, 4096, True),
    (169999, 100, 4096, False), (-1, 100, 4096, False),
    (200000, 0, 4096, False), (200000, 100, 0, False),
])
def test_s0_admission_rechecks_tmp_inodes_and_available_space(free_inodes, free_blocks, block_size, passed,
                                                            monkeypatch, capsys):
    from types import SimpleNamespace
    queried = []
    def statvfs(path):
        queried.append(path)
        return SimpleNamespace(f_favail=free_inodes, f_bavail=free_blocks, f_frsize=block_size)
    monkeypatch.setattr(os, 'statvfs', statvfs)
    if passed:
        execute_block('m9-prep.sh', 'PY_S0_ADMISSION', [], monkeypatch)
        result = json.loads(capsys.readouterr().out)
        assert result['passed'] and result['minimum_free_inodes'] == 170000
        assert result['tmp_free_inodes'] == free_inodes
    else:
        with pytest.raises(AssertionError):
            execute_block('m9-prep.sh', 'PY_S0_ADMISSION', [], monkeypatch)
        assert capsys.readouterr().out == ''
    assert queried == ['/tmp']


def test_s0_admission_fails_closed_when_filesystem_measurement_is_unavailable(monkeypatch):
    def unavailable(_path):
        raise OSError('Authored unavailable filesystem statistics')
    monkeypatch.setattr(os, 'statvfs', unavailable)
    with pytest.raises(OSError, match='unavailable'):
        execute_block('m9-prep.sh', 'PY_S0_ADMISSION', [], monkeypatch)


@pytest.mark.parametrize('code,last,passed', [
    (0, '7 passed in 1.00s', True), (1, '7 passed in 1.00s', False),
    (0, '1 failed, 7 passed in 1.00s', False), (0, 'truncated', False),
    (2, '3 errors in 1.00s', False),
], ids=['passing_summary', 'nonzero_exit', 'failure_summary', 'truncated_summary', 'error_summary'])
def test_suite_removes_only_owned_cases_after_verified_success(tmp_path, monkeypatch, capsys, code, last, passed):
    scratch = tmp_path/'suite-authored'
    cases = scratch/'cases'
    cases.mkdir(parents=True)
    evidence = cases/'diagnostic.json'
    evidence.write_text('authored cases evidence')
    sibling = scratch/'keep.json'
    sibling.write_text('authored sibling evidence')
    log = tmp_path/'full-suite.log'
    log.write_text('earlier output\n'+last+'\n')
    with pytest.raises(SystemExit) as stopped:
        execute_block('run-v225-pre.sh', 'PY_SUITE_RESULT', [log, code, scratch], monkeypatch)
    assert stopped.value.code == (0 if passed else 3)
    result = json.loads(capsys.readouterr().out)
    assert result['passed'] is passed and result['cases_removed'] is passed
    assert scratch.is_dir() and sibling.read_text() == 'authored sibling evidence'
    assert log.read_text().endswith(last+'\n')
    assert cases.exists() is not passed
    if not passed:
        assert evidence.read_text() == 'authored cases evidence'


def test_success_cleanup_refuses_symlinked_cases(tmp_path, monkeypatch):
    scratch = tmp_path/'suite-authored'
    scratch.mkdir()
    other = tmp_path/'other'
    other.mkdir()
    evidence = other/'keep.json'
    evidence.write_text('keep')
    (scratch/'cases').symlink_to(other, target_is_directory=True)
    log = tmp_path/'full-suite.log'
    log.write_text('7 passed in 1.00s\n')
    with pytest.raises(AssertionError, match='owns the cases'):
        execute_block('run-v225-pre.sh', 'PY_SUITE_RESULT', [log, 0, scratch], monkeypatch)
    assert evidence.read_text() == 'keep'


def test_prep_host_lock_covers_suite_and_s0_admission_with_snapshot_execution():
    prep = (OPS/'m9-prep.sh').read_text()
    lock = prep.index('exec 201>/tmp/execskill-s0.lock')
    assert prep.index('m9_require_paths\n') < lock < prep.index('flock -n 201') < prep.index('case "${M9_SKIP_LINUX_SUITE:-0}"')
    assert prep.count('flock -n 201') == 1 and 'flock -u' not in prep and '201>&-' not in prep
    wrapper = prep.split('m9_s0_locked() (', 1)[1].split('\n)', 1)[0]
    assert wrapper.index('cd -- "$M9_SNAPSHOT"') < wrapper.index('export PYTHONPATH="$M9_SNAPSHOT"')
    assert wrapper.index('export PYTHONPATH="$M9_SNAPSHOT"') < wrapper.index('m9_step s0-admission m9_s0_admission')
    assert wrapper.index('m9_step s0-admission m9_s0_admission') < wrapper.index('m9_step s0 m9_cli v214-s0')
    assert prep.index('m9_step selftest') < prep.index('m9_s0_locked() (')
    assert '\nm9_s0_locked\n' in prep


def test_standalone_suite_shares_s0_lock_before_other_suite_admission():
    source = (OPS/'run-v225-pre.sh').read_text()
    assert source.index('operator-confirmed-alone') < source.index('PY_S0_DESCRIPTOR')
    assert source.index('PY_S0_DESCRIPTOR') < source.index('exec 201>/tmp/execskill-s0.lock')
    assert source.index('exec 201>/tmp/execskill-s0.lock') < source.index('flock -n 201')
    assert source.index('flock -n 201') < source.index('flock -n 200') < source.index('"$M9_OPS/m9-alone.py"')
    assert source.index('flock -n 201') < source.index('mktemp -d')
    assert 'os.fstat(201)' in source and 'os.stat(sys.argv[1])' in source
    assert 'flock -u' not in source and '201>&-' not in source


@pytest.mark.parametrize('kind,expected', [('same', 0), ('other', 1), ('missing', 1), ('path_missing', 1)])
def test_inherited_s0_descriptor_must_name_the_fixed_lock_file(tmp_path, kind, expected):
    helper = python_block('run-v225-pre.sh', 'PY_S0_DESCRIPTOR')
    lock, other = tmp_path/'host.lock', tmp_path/'other.lock'
    lock.touch(); other.touch()
    program = """import os, subprocess, sys
kind, lock, other, helper = sys.argv[1:]
passed = ()
if kind != 'missing':
    descriptor = os.open(other if kind == 'other' else lock, os.O_RDWR)
    os.dup2(descriptor, 201, inheritable=True)
    if descriptor != 201:
        os.close(descriptor)
    passed = (201,)
target = lock + '-absent' if kind == 'path_missing' else lock
result = subprocess.run([sys.executable, '-B', '-c', helper, target], pass_fds=passed)
sys.exit(result.returncode)
"""
    found = subprocess.run([sys.executable, '-B', '-c', program, kind, str(lock), str(other), helper],
                           capture_output=True, text=True)
    assert found.returncode == expected, found.stdout+found.stderr


def test_parent_child_reuse_one_s0_lock_while_independent_suite_contends(tmp_path):
    helper = python_block('run-v225-pre.sh', 'PY_S0_DESCRIPTOR')
    program = """import fcntl, json, os, subprocess, sys
lock, helper = sys.argv[1:]
descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
os.dup2(descriptor, 201, inheritable=True)
if descriptor != 201:
    os.close(descriptor)
fcntl.flock(201, fcntl.LOCK_EX | fcntl.LOCK_NB)
identity = subprocess.run([sys.executable, '-B', '-c', helper, lock], pass_fds=(201,))
reuse = subprocess.run([sys.executable, '-B', '-c', 'import fcntl; fcntl.flock(201, fcntl.LOCK_EX | fcntl.LOCK_NB)'], pass_fds=(201,))
independent = '''import fcntl, os, sys
descriptor = os.open(sys.argv[1], os.O_RDWR)
try:
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(9)
'''
blocked = subprocess.run([sys.executable, '-B', '-c', independent, lock])
os.close(201)
released = subprocess.run([sys.executable, '-B', '-c', independent, lock])
print(json.dumps({'identity': identity.returncode, 'reuse': reuse.returncode,
                  'independent_while_held': blocked.returncode, 'after_release': released.returncode}))
"""
    found = subprocess.run([sys.executable, '-B', '-c', program, str(tmp_path/'host.lock'), helper],
                           capture_output=True, text=True)
    assert found.returncode == 0, found.stdout+found.stderr
    assert json.loads(found.stdout) == {'identity': 0, 'reuse': 0, 'independent_while_held': 9, 'after_release': 0}


def test_optional_standalone_suite_skip_has_a_logged_receipt_and_never_skips_s0():
    prep = (OPS/'m9-prep.sh').read_text()
    helper = prep.split('m9_skip_linux_suite() {\n', 1)[1].split('\n}', 1)[0]
    found = subprocess.run(['bash', '-c', helper], capture_output=True, text=True)
    result = json.loads(found.stdout)
    assert found.returncode == 0 and result['passed'] and result['standalone_linux_suite'] == 'skipped'
    assert result['reason'] == 'M9_SKIP_LINUX_SUITE=1' and result['s0_admission'] == 'still_required'
    assert '1) m9_step pre m9_skip_linux_suite;;' in prep
    assert '0) m9_step pre bash "$M9_OPS/run-v225-pre.sh";;' in prep
    assert 'M9_SKIP_LINUX_SUITE must be 0 or 1' in prep


@pytest.mark.parametrize('expression', [
    "list(read_arms_of('main-v8'))",
    "list(read_arms_of(other_configuration))",
    "['B', 'C']",
    "list(read_arms_of(configuration)) + ['extra']",
    "list(read_arms_of(configuration))[1:]",
])
def test_patcher_checks_actual_consent_arms_despite_unrelated_reader_call(expression):
    source = writer_source().replace('list(read_arms_of(configuration))', expression)
    source += "\nread_arms_of('main-v8')\n"
    with pytest.raises(AssertionError, match='Consent arms'):
        patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                        whitelist_line="ALLOWED = ('main-v6', 'main-v8')")


@pytest.mark.parametrize('expression', [
    "read_arms_of(configuration)", "tuple(read_arms_of(configuration))",
    "list(p.read_arms_of(configuration))", "list(read_arms_of(configuration=configuration))",
    "['B', 'C0', 'C', 'S1', 'S2', 'S3', 'S4', 'S5', 'I', 'C_end']",
])
def test_patcher_accepts_actual_registered_reader_or_exact_literal_arms(expression):
    source = writer_source().replace('list(read_arms_of(configuration))', expression)
    assert "'main-v9'" in patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
        whitelist_line="ALLOWED = ('main-v6', 'main-v8')")


@pytest.mark.parametrize('suffix', [
    ", 'multi_arm_arms': ['B', 'C']", ", **overrides",
])
def test_patcher_refuses_hidden_or_duplicate_consent_arm_overrides(suffix):
    source = writer_source().replace("'sheet_test_qualification': True}",
        "'sheet_test_qualification': True" + suffix + "}")
    with pytest.raises(AssertionError):
        patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                        whitelist_line="ALLOWED = ('main-v6', 'main-v8')")


def alone_guard():
    spec = importlib.util.spec_from_file_location('v225_alone_template', OPS / 'm9-alone.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('comm,command', [
    ('pytest', 'pytest -q'), ('pytest', '/venv/bin/pytest -q'),
    ('python3', '/usr/bin/python3 /venv/bin/pytest -q'),
    ('python3', '/usr/bin/python3 -B /venv/bin/pytest -q'),
    ('py.test', 'py.test -q'), ('python', 'python -B -m pytest -q'),
    ('python3', 'python3 scripts/run_execskill.py run --manifest /authored/m.json'),
    ('python3', 'python3 -m scripts.run_execskill evaluate-unit --spec /authored/s.json'),
    ('python', 'python scripts/run_execskill.py step-unit --spec /authored/s.json'),
    ('python', 'python scripts/run_execskill.py v214-smoke-run --stage S2'),
    ('python', "python -B -c import json; from scripts import run_execskill as cli; cli.main() run --manifest /authored/m.json"),
    ('python', 'python scripts/run_coevo5.py run'),
    ('python', 'python scripts/run_continual_learning.py'),
    ('python', 'python scripts/evaluate_fivebench_test.py --manifest /authored/m.json'),
    ('bash', 'bash /authored/m8-run.sh G'), ('bash', 'bash /authored/m9-smoke.sh'),
    ('bash', 'bash /authored/run-v222-pre.sh'),
    ('bash', 'bash scripts/run_fivebench_g_stage_linux.sh'),
    ('python', 'python scripts/weak_solver_probe.py'),
])
def test_alone_guard_recognizes_plain_pytest_and_registered_experiment_read_drivers(comm, command):
    assert alone_guard().active_driver(comm, command)


@pytest.mark.parametrize('comm,command', [
    ('grep', 'grep pytest logfile'), ('vim', 'vim scripts/run_execskill.py'),
    ('python', 'python report.py --label pytest'),
    ('python', "python -c \"print('pytest')\""),
    ('python', 'python scripts/run_execskill.py verify-snapshot --snapshot /authored/s'),
    ('python', 'python /authored/m9-alone.py'),
])
def test_alone_guard_ignores_unrelated_programs(comm, command):
    assert alone_guard().active_driver(comm, command) is None


def test_alone_guard_ignores_own_wrapper_ancestors_but_never_sibling_reads():
    processes = """10 1 bash bash /authored/m9-go.sh
11 10 bash bash /authored/run-v225-pre.sh
12 11 python3 python3 /authored/m9-alone.py
20 10 python3 python3 scripts/run_execskill.py evaluate-unit --secret ARGUMENT_MUST_NOT_LEAK
21 1 pytest pytest -q
"""
    active = alone_guard().active_processes(processes, own_pid=12)
    assert {row['pid'] for row in active} == {20, 21}
    assert 'ARGUMENT_MUST_NOT_LEAK' not in repr(active)
    assert alone_guard().active_processes('\n'.join(processes.splitlines()[:3]), own_pid=12) == []


def test_alone_guard_fails_closed_on_unparseable_process_listing():
    with pytest.raises(ValueError):
        alone_guard().active_processes('truncated listing', own_pid=12)


@pytest.mark.parametrize('mutation', [
    "result['multi_arm_arms'] = ['B', 'C']",
    "result.update(multi_arm_arms=['B', 'C'])",
])
def test_patcher_rejects_later_overwrites_of_emitted_consent_arms(mutation):
    source = writer_source() + "\n" + mutation + "\n"
    with pytest.raises(AssertionError, match='Later consent arm writes'):
        patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                        whitelist_line="ALLOWED = ('main-v6', 'main-v8')")


@pytest.mark.parametrize('mutation', [
    "result['multi_arm_arms'].clear()",
    "result['multi_arm_arms'].append('extra')",
    "result['sheet_test_qualification'] = False",
    "del result['multi_arm_arms']",
    "del result['sheet_test_qualification']",
    "result.pop('multi_arm_arms')",
    "result.pop('sheet_test_qualification')",
    "result.clear()",
    "result.update(overrides)",
    "result[key] = replacement",
    "alias = result\n    alias.clear()",
    "arms = result['multi_arm_arms']\n    arms.clear()",
    "arms = result.get('multi_arm_arms')\n    arms.append('extra')",
    "arms = result['multi_arm_arms']\n    arms += ['extra']",
])
def test_patcher_rejects_protected_field_mutation_deletion_and_ambiguous_updates(mutation):
    source = writer_source().replace('    return {', '    result = {')
    source += '    ' + mutation + '\n    return result\n'
    with pytest.raises(AssertionError):
        patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                        whitelist_line="ALLOWED = ('main-v6', 'main-v8')")


@pytest.mark.parametrize('assignment', ["configuration = 'main-v8'", 'configuration = other_configuration',
                                         'configuration = args.configuration'])
def test_patcher_rejects_rebinding_the_configuration_parameter(assignment):
    source = writer_source().replace('    return {', '    '+assignment+'\n    return {')
    with pytest.raises(AssertionError, match='configuration'):
        patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                        whitelist_line="ALLOWED = ('main-v6', 'main-v8')")


@pytest.mark.parametrize('assignment,allowed', [
    ('configuration = args.configuration', True), ("configuration = 'main-v8'", False),
    ('configuration = choose_configuration()', False),
])
def test_patcher_accepts_only_explicit_cli_attribute_for_module_configuration(assignment, allowed):
    source = writer_source().replace('def make(configuration):', assignment+'\ndef make():')
    if allowed:
        assert "'main-v9'" in patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
            whitelist_line="ALLOWED = ('main-v6', 'main-v8')")
    else:
        with pytest.raises(AssertionError, match='configuration'):
            patcher().patch(source, sha256=hashlib.sha256(source.encode()).hexdigest(),
                            whitelist_line="ALLOWED = ('main-v6', 'main-v8')")
