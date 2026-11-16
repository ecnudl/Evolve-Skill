"""scripts/run_typed.py: parsing, the machinery-snapshot binding, exit codes, adapters and a sealed-free status."""
import builtins
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from scripts import run_typed
from skillopt.execskill.typed import EXIT_AWAITING, EXIT_COMPLETE, EXIT_PAUSED, units

TREE = Path(run_typed.__file__).resolve().parents[1]


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='cli-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


@pytest.fixture
def environ():
    """main() cleans os.environ in place; the test restores it."""
    saved = dict(os.environ)
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_parser_accepts_the_five_commands_and_their_flags():
    parse = run_typed.parser().parse_args
    args = parse(['--machinery-snapshot', '/snap', 'run', '--root', '/r', '--chain', 'G', '--resume'])
    assert (args.command, args.machinery_snapshot, args.chain, args.resume) == ('run', '/snap', 'G', True)
    assert parse(['smoke', '--root', '/r', '--chain', 'D', '--fake']).fake is True
    assert parse(['prepare', '--root', '/r', '--machinery-manifest', '/m.json', '--roles-repo', '/creds',
                  '--pools-root', '/pools', '--smoke']).smoke is True
    assert parse(['readout', '--root', '/r', '--open-sealed']).open_sealed is True
    assert parse(['status', '--root', '/r']).chain is None
    for bad in (['run', '--root', '/r'], ['run', '--root', '/r', '--chain', 'G', '--fake'],
                ['status', '--root', '/r', '--open-sealed'], ['run', '--root', '/r', '--chain', 'X']):
        with pytest.raises(SystemExit):
            parse(bad)


def test_exit_codes_follow_the_chain_state():
    assert run_typed.exit_code({'status': 'complete'}) == EXIT_COMPLETE == 0
    assert run_typed.exit_code({'status': 'paused', 'paused': {'reason': 'token_cap', 'unit': 's2/outcomes'}}) == EXIT_PAUSED == 3
    assert run_typed.exit_code({'status': 'paused', 'paused': {'reason': 'awaiting_owner_decision', 'unit': 's1'}}) == EXIT_AWAITING == 5
    assert run_typed.exit_code({'status': 'awaiting_owner'}) == 5 and run_typed.exit_code(None) == 3
    summary = run_typed.state_summary({'status': 'paused', 'step': 2, 'done': ['a', 'b'], 'paused': {'reason': 'x'}})
    assert summary == {'status': 'paused', 'step': 2, 'paused': {'reason': 'x'}, 'done_units': 2, 'ledger': None, 'exit_code': 3,
                       'schedule': None, 'phase': None}  # typed-v2 step 6s: the schedule and phase are shown (DESIGN 3.6)


def test_clean_environment_and_alfworld_data(tmp_path):
    environ = {'OPENAI_API_KEY': 'k', 'OPENAI_BASE_URL': 'u', 'HOME': '/h'}
    run_typed.clean_environment(environ)
    assert environ == {'HOME': '/h', 'PYTHONDONTWRITEBYTECODE': '1'} and sys.dont_write_bytecode
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'runtime': {'alfworld': {'alfworld_data': '/data/alf'}}}))
    found = {}
    assert run_typed.set_alfworld_data(manifest, found) == '/data/alf' and found == {'ALFWORLD_DATA': '/data/alf'}
    assert run_typed.alfworld_data_of({'machinery': {'runtime': {'alfworld': {'alfworld_data': '/m/alf'}}}}) == '/m/alf'
    assert run_typed.alfworld_data_of({'runtime': {'searchqa': {}}}) is None
    assert run_typed.set_alfworld_data(tmp_path / 'absent.json', found) is None


def test_machinery_snapshot_binding_in_a_fresh_interpreter(tmp_path):
    snapshot = tmp_path / 'snapshot'
    (snapshot / 'skillopt' / 'execskill').mkdir(parents=True)
    (snapshot / 'skillopt' / '__init__.py').write_text('MARKER = "snapshot-skillopt"\n')
    (snapshot / 'skillopt' / 'execskill' / '__init__.py').write_text('MARKER = "snapshot-execskill"\n')
    code = '\n'.join([
        'import json, sys',
        'sys.path.insert(0, %r)' % str(TREE / 'scripts'),
        'import run_typed',
        'bound = run_typed.bind_machinery(%r, %r)' % (str(snapshot), str(TREE)),
        'import skillopt, skillopt.execskill',
        'from skillopt.execskill import typed',
        'print(json.dumps({"bound": bound, "skillopt": skillopt.__file__, "marker": skillopt.execskill.MARKER,',
        '                  "typed": typed.__file__, "version": typed.VERSION, "path0": sys.path[0]}))'])
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    done = subprocess.run([sys.executable, '-I', '-c', code], cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    found = json.loads(done.stdout)
    assert found['path0'] == str(snapshot.resolve()) and found['skillopt'].startswith(str(snapshot.resolve()))
    assert found['marker'] == 'snapshot-execskill' and found['version'] == 'typed-v3'
    assert found['typed'].startswith(str(TREE / 'skillopt' / 'execskill' / 'typed'))
    assert str(TREE / 'skillopt' / 'execskill') in found['bound']['execskill_path']
    assert found['bound']['execskill_file'].startswith(str(snapshot.resolve()))
    # in this process skillopt is already imported: the binding is refused instead of silently not taking effect
    with pytest.raises(ValueError):
        run_typed.bind_machinery(snapshot, TREE)
    with pytest.raises(ValueError):
        run_typed.bind_machinery(tmp_path / 'nowhere', TREE)


def test_run_smoke_prepare_go_through_the_adapters(tmp_path, monkeypatch, environ, capsys):
    calls = []
    monkeypatch.setattr(run_typed, '_chain_run', lambda root, chain, **kw: calls.append(('run', root, chain, kw)) or
                        {'status': 'paused', 'paused': {'reason': 'awaiting_owner_decision', 'unit': 's1/outcomes'}})
    monkeypatch.setattr(run_typed, '_smoke_run', lambda root, chain, **kw: calls.append(('smoke', root, chain, kw)) or {'status': 'complete'})
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(('prepare', root, kw)) or
                        {'configuration': 'typed-v2', 'record_sha256': 'abc', 'secret': 'never printed'})
    root = tmp_path / 'run'
    root.mkdir()
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {'alfworld': {'alfworld_data': '/data/alf-machinery'}}}))
    os.environ.pop('ALFWORLD_DATA', None)
    assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery), '--roles-repo', '/creds',
                           '--pools-root', '/pools']) == 0
    assert os.environ['ALFWORLD_DATA'] == '/data/alf-machinery'
    out = json.loads(capsys.readouterr().out)
    assert out['manifest'] == {'configuration': 'typed-v2', 'machinery': None, 'record_sha256': 'abc', 'evidence': None, 'seed': None,
                               'base_card': None,  # typed-v2 step 5b: the sealed base card is printed (addendum D17)
                               'schedule': None, 'memory_lock': None,  # step 6s: and the sealed order and lock (DESIGN 3.6)
                               'machinery_code': None}  # fix-b (F3): and the sealed machinery record
    assert calls[-1] == ('prepare', str(root), {'machinery_manifest': str(machinery), 'roles_repo': '/creds',
                                               'pools_root': '/pools', 'smoke': False})
    (root / 'manifest.json').write_text(json.dumps({'runtime': {'alfworld': {'alfworld_data': '/data/alf-run'}}}))
    assert run_typed.main(['run', '--root', str(root), '--chain', 'G', '--resume']) == 5
    assert calls[-1] == ('run', str(root), 'G', {'resume': True, 'roles_repo': None})
    assert os.environ['ALFWORLD_DATA'] == '/data/alf-run' and json.loads(capsys.readouterr().out)['exit_code'] == 5
    assert run_typed.main(['smoke', '--root', str(root), '--chain', 'D', '--fake']) == 0
    assert calls[-1] == ('smoke', str(root), 'D', {'fake': True})
    assert 'OPENAI_API_KEY' not in os.environ and os.environ['PYTHONDONTWRITEBYTECODE'] == '1'


def test_status_and_readout_commands_without_sealed_access(tmp_path, monkeypatch, environ, capsys):
    root = tmp_path / 'run'
    chain_dir = root / 'G'
    units.write_json(chain_dir / 'state.json', {'status': 'paused', 'step': 1, 'done': [], 'paused': {'reason': 'token_cap', 'unit': 'u'}})
    ledger = units.Ledger(chain_dir / 'ledger.json', 10_000)
    key, bound = ledger.before_send('s', 'u', 10, cell='c', unit='s1/outcomes')
    ledger.settle(key, {'ok': True, 'usage': {'prompt_tokens': 5, 'completion_tokens': 1, 'total_tokens': 6}}, max_tokens=10, prompt_bound=bound - 10)
    units.write_json(chain_dir / 'read-status' / 'C0-searchqa.json', {'cells': 3, 'unknown_by_kind': {}, 'mount': {'typed_fraction': 0.0},
                     'pass_count': 2})
    sealed = chain_dir / 'test-read-C0-searchqa' / 'cells'
    sealed.mkdir(parents=True)
    (sealed / 'x.json').write_text(json.dumps({'item_id': 'i0', 'correct': True, 'reply': 'SEALED-TEXT'}))
    real_open, real_read_text = io.open, Path.read_text

    def guarded_open(file, *args, **kwargs):
        assert 'test-read' not in str(file), 'sealed path opened by status: ' + str(file)
        return real_open(file, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        assert 'test-read' not in str(self), 'sealed path opened by status: ' + str(self)
        return real_read_text(self, *args, **kwargs)
    monkeypatch.setattr(io, 'open', guarded_open)
    monkeypatch.setattr(builtins, 'open', guarded_open)
    monkeypatch.setattr(Path, 'read_text', guarded_read_text)
    assert run_typed.main(['status', '--root', str(root)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['command'] == 'status' and out['chains']['G']['ledger']['reported'] == 6
    assert out['chains']['G']['read_status']['C0-searchqa'] == {'cells': 3, 'unknown_by_kind': {}, 'mount': {'typed_fraction': 0.0}}
    assert 'SEALED-TEXT' not in json.dumps(out)
    assert run_typed.main(['readout', '--root', str(root)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['mode'] == 'closed' and Path(out['written']['G']['markdown']).exists()
    assert 'SEALED-TEXT' not in Path(out['written']['G']['json']).read_text()


def test_prepare_prints_the_sealed_machinery_record_for_the_launcher(tmp_path, monkeypatch, environ, capsys):
    """fix-b (review F3), spec/identity.md 1.10: a manifest prepared unbound (machinery_code.bound false) is refused by
    every real start, and the prepare command prints the record so the launcher stops at once (its row: stop unless
    the printed machinery_code.bound is true)."""
    record = {'snapshot': '/data/snap', 'bound': False, 'typed_from': '/data/tree', 'list': 'l', 'list_sha256': 'a' * 64,
              'files': 564, 'data_list_sha256': 'b' * 64, 'symbols': 12}
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: {'configuration': 'typed-v2', 'machinery_code': record,
                                                                   'base_card': 'historical'})
    root = tmp_path / 'run'
    root.mkdir()
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {}}))
    assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery)]) == 0
    printed = json.loads(capsys.readouterr().out)['manifest']
    assert printed['machinery_code'] == record and printed['machinery_code']['bound'] is False
    assert printed['base_card'] == 'historical'


def test_a_paused_fake_smoke_resumes_through_the_command_line_and_sends_no_finished_call_again(
        tmp_path, monkeypatch, environ, capsys):
    """fix-b (review rb-resume 4): ``smoke --resume`` resumes a paused smoke root with the owner's recovery.json (it
    was refused before: the smoke command took no --resume, the run command refuses a smoke state). Here the card
    writer's connection fails once: the fake smoke pauses for the owner (exit 5); after the recovery the resumed smoke
    completes (exit 0) and its ledger counts exactly one send more than a smoke that never paused (the failed call
    sent again); nothing finished is sent twice. Without the recovery the resume is refused."""
    from skillopt.execskill.typed import smoke as smoke_module
    parse = run_typed.parser().parse_args
    assert parse(['smoke', '--root', '/r', '--chain', 'G', '--fake', '--resume']).resume is True
    assert parse(['smoke', '--root', '/r', '--chain', 'G']).resume is False
    real_send, broken = smoke_module.Script.send, {'on': False}

    def send(self, purpose, system, user, *, model, unit=None):
        if broken['on'] and purpose == 'card_writer':
            broken['on'] = False
            raise RuntimeError('writer connection lost')
        return real_send(self, purpose, system, user, model=model, unit=unit)
    monkeypatch.setattr(smoke_module.Script, 'send', send)
    clean, paused = tmp_path / 'clean', tmp_path / 'paused'
    assert run_typed.main(['smoke', '--root', str(clean), '--chain', 'G', '--fake']) == 0
    clean_sends = json.loads((smoke_module.smoke_root(clean) / 'G' / 'ledger.json').read_text())['sends']
    broken['on'] = True
    assert run_typed.main(['smoke', '--root', str(paused), '--chain', 'G', '--fake']) == 5
    capsys.readouterr()
    chain_dir = smoke_module.smoke_root(paused) / 'G'
    assert json.loads((chain_dir / 'state.json').read_text())['paused']['reason'] == 'exception:RuntimeError'
    with pytest.raises(ValueError, match='requires the owner recovery'):  # refused: a hard error, no pause
        run_typed.main(['smoke', '--root', str(paused), '--chain', 'G', '--fake', '--resume'])
    units.write_json(chain_dir / 'recovery.json', {'by': 'owner', 'date': '2026-11-12', 'decision': 'continue'})
    assert run_typed.main(['smoke', '--root', str(paused), '--chain', 'G', '--fake', '--resume']) == 0
    ledger = json.loads((chain_dir / 'ledger.json').read_text())
    assert ledger['sends'] == clean_sends + 1 and ledger['pending'] == {}
    assert json.loads((chain_dir / 'state.json').read_text())['complete'] is True


def test_prepare_takes_the_schedule_and_the_memory_lock(tmp_path, monkeypatch, environ, capsys):
    """typed-v2 step 6s (DESIGN 3.6; schedule-lock S1, change row 3): --schedule and --memory-lock exist on prepare
    only (run and smoke read both from the manifest), are passed to prepare only when named and are printed with the
    sealed manifest, so the launcher can check learn_first and unit_shared (addenda D9, D13)."""
    from skillopt.execskill import typed
    from skillopt.execskill.typed import prepare as prepare_module
    assert run_typed.SCHEDULES == typed.SCHEDULES and run_typed.MEMORY_LOCKS == typed.MEMORY_LOCKS
    parse = run_typed.parser().parse_args
    args = parse(['prepare', '--root', '/r', '--schedule', 'learn_first', '--memory-lock', 'unit_shared'])
    assert (args.schedule, args.memory_lock) == ('learn_first', 'unit_shared')
    args = parse(['prepare', '--root', '/r'])
    assert (args.schedule, args.memory_lock) == (None, None)
    for bad in (['prepare', '--root', '/r', '--schedule', 'economy'], ['prepare', '--root', '/r', '--memory-lock', 'plain'],
                ['run', '--root', '/r', '--chain', 'G', '--schedule', 'learn_first'],
                ['smoke', '--root', '/r', '--chain', 'G', '--fake', '--memory-lock', 'unit_shared']):
        with pytest.raises(SystemExit):
            parse(bad)
    calls, adapter = [], run_typed._prepare
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(kw) or {
        'configuration': 'typed-v2', 'schedule': kw.get('schedule', 'interleaved'),
        'memory_lock': kw.get('memory_lock', 'per_cell_plain')})
    root = tmp_path / 'run'
    root.mkdir()
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {}}))
    assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery), '--schedule',
                           'learn_first', '--memory-lock', 'unit_shared', '--base-card', 'historical']) == 0
    assert calls[-1] == {'machinery_manifest': str(machinery), 'roles_repo': typed.ROLES_REPO,
                         'pools_root': typed.POOLS_ROOT, 'smoke': False, 'base_card': 'historical',
                         'schedule': 'learn_first', 'memory_lock': 'unit_shared'}
    printed = json.loads(capsys.readouterr().out)['manifest']
    assert (printed['schedule'], printed['memory_lock']) == ('learn_first', 'unit_shared')
    # the adapter hands prepare only what the command names (the code defaults otherwise)
    seen = []
    monkeypatch.setattr(prepare_module, 'prepare', lambda root, **kw: seen.append(kw) or {})
    common = dict(machinery_manifest='/m.json', roles_repo='/creds', pools_root='/pools', smoke=True)
    adapter('/r', **common)
    adapter('/r', schedule='learn_first', memory_lock='unit_shared', **common)
    assert seen == [common, {**common, 'schedule': 'learn_first', 'memory_lock': 'unit_shared'}]


# ---- typed-v2 step rp-int: the read plan on the command line (read-plan R4, R47, R47b, R76, R77, R92; T24) ----------
def test_the_read_plan_options_parse_and_reach_their_adapters(tmp_path, monkeypatch, environ, capsys):
    from skillopt.execskill import typed
    from skillopt.execskill.typed import readplan
    assert run_typed.READ_PLANS == typed.READ_PLANS and run_typed.CHECKPOINTS == readplan.CHECKPOINTS
    assert 'plan-replay' in run_typed.COMMANDS
    parse = run_typed.parser().parse_args
    args = parse(['prepare', '--root', '/r', '--read-plan', 'economy', '--read-plan-probe', 'C0:zebralogic'])
    assert (args.read_plan, args.read_plan_probe) == ('economy', 'C0:zebralogic')
    assert parse(['run', '--root', '/r', '--chain', 'G', '--stop-after-plan']).stop_after_plan is True
    args = parse(['smoke', '--root', '/r', '--chain', 'G', '--fake', '--configured', '--fake-kill-at', 'after-plan-file'])
    assert (args.configured, args.fake_kill_at, args.stop_after_plan) == (True, 'after-plan-file', False)
    args = parse(['plan-replay', '--root', '/r', '--chain', 'D', '--smoke', '--fake'])
    assert (args.smoke, args.fake, args.fake_kill_at) == (True, True, None)
    for bad in (['run', '--root', '/r', '--chain', 'G', '--read-plan', 'economy'],
                ['smoke', '--root', '/r', '--chain', 'G', '--read-plan', 'economy'],
                ['prepare', '--root', '/r', '--read-plan', 'cheap'],
                ['run', '--root', '/r', '--chain', 'G', '--fake-kill-at', 'after-plan-file'],
                ['smoke', '--root', '/r', '--chain', 'G', '--fake-kill-at', 'nowhere'],
                ['plan-replay', '--root', '/r']):
        with pytest.raises(SystemExit):
            parse(bad)
    calls = []
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(kw) or {
        'configuration': 'typed-v2', 'read_plan': kw.get('read_plan', 'full'), 'read_plan_probe': kw.get('read_plan_probe')})
    monkeypatch.setattr(run_typed, '_chain_run', lambda root, chain, **kw: calls.append(kw) or {'status': 'complete'})
    monkeypatch.setattr(run_typed, '_smoke_run', lambda root, chain, **kw: calls.append(kw) or {'status': 'complete'})
    root = tmp_path / 'run'
    root.mkdir()
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {}}))
    assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery), '--smoke',
                           '--schedule', 'learn_first', '--read-plan', 'economy', '--read-plan-probe', 'C0:zebralogic']) == 0
    assert calls[-1]['read_plan'] == 'economy' and calls[-1]['read_plan_probe'] == ['C0', 'zebralogic']
    printed = json.loads(capsys.readouterr().out)['manifest']
    assert (printed['read_plan'], printed['read_plan_probe']) == ('economy', ['C0', 'zebralogic'])
    assert run_typed.main(['run', '--root', str(root), '--chain', 'G', '--stop-after-plan']) == 0
    assert calls[-1] == {'resume': False, 'roles_repo': None, 'stop_after_plan': True}
    assert run_typed.main(['smoke', '--root', str(root), '--chain', 'G', '--fake', '--configured', '--fake-kill-at',
                           'after-first-inputs']) == 0
    assert calls[-1] == {'fake': True, 'configured': True, 'fake_kill_at': 'after-first-inputs'}
    with pytest.raises(SystemExit):
        run_typed.main(['smoke', '--root', str(root), '--chain', 'G', '--configured'])  # fakes only


def test_state_summary_shows_the_read_plan_counts_only():
    state = {'complete': True, 'done_units': ['read-plan', 'read-S5-searchqa', 'alias-S4-searchqa', 'step-0'],
             'reads': {'S3': {'officeqa': {'kind': 'void_alias', 'status': 'void_alias'}}},
             'read_plan': {'mode': 'economy', 'plan_sha256': 'a' * 64, 'void': False, 'fallbacks': {'officeqa': {}},
                           'counts': {'fresh': 9}}}
    summary = run_typed.state_summary(state)
    assert summary['read_plan'] == {'mode': 'economy', 'plan': 'a' * 12, 'void': False, 'reads': {
        'settled': 2, 'of': 35, 'fresh_done': 1, 'fresh_planned': 9, 'alias': 1, 'fallbacks': 1, 'void_aliases': 1}}


def test_a_fake_smoke_stops_after_the_plan_and_resumes_with_the_owner_record(tmp_path, monkeypatch, environ, capsys):
    """T24 and S2 (a): ``smoke --fake --configured --stop-after-plan`` exits 5 (paused, stopped_after_plan) after the
    binding and an equal replay by the REAL child process; a resume without recovery.json is a hard error; with it
    the smoke completes, and a resumed process with the flag does not stop again. ``plan-replay`` on the finished
    root prints equal (exit 0), with another base different (exit 3), on a missing root an error with its class
    name only (exit 3); nothing printed carries an item id or a text."""
    from skillopt.execskill.typed import smoke as smoke_module
    root = tmp_path / 'run'
    assert run_typed.main(['smoke', '--root', str(root), '--chain', 'G', '--fake', '--configured',
                           '--stop-after-plan']) == 5
    out = json.loads(capsys.readouterr().out)
    assert out['paused']['reason'] == 'stopped_after_plan' and out['status'] == 'paused'
    chain_dir = smoke_module.smoke_root(root) / 'G'
    state = json.loads((chain_dir / 'state.json').read_text())
    assert state['read_plan']['replay']['verdict'] == 'equal' and out['read_plan']['reads']['fresh_done'] == 0
    with pytest.raises(ValueError, match='requires the owner recovery'):
        run_typed.main(['smoke', '--root', str(root), '--chain', 'G', '--fake', '--configured', '--resume'])
    units.write_json(chain_dir / 'recovery.json', {'by': 'owner', 'date': '2026-11-12', 'decision': 'read'})
    assert run_typed.main(['smoke', '--root', str(root), '--chain', 'G', '--fake', '--configured', '--resume',
                           '--stop-after-plan']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['status'] == 'complete' and out['read_plan']['reads']['settled'] == 35
    ids = [i for rows in smoke_module.synthetic_items(smoke_module.smoke_manifest(root, fake=True, configured=True)).values()
           for i in (row['task_id'] for row in rows)]
    printed = []
    for argv, code in ((['plan-replay', '--root', str(smoke_module.smoke_root(root)), '--chain', 'G', '--smoke', '--fake'], 0),
                       (['plan-replay', '--root', str(root), '--chain', 'G', '--smoke', '--fake', '--base-card', 'format'], 3),
                       (['plan-replay', '--root', str(tmp_path / 'nowhere'), '--chain', 'G'], 3),  # no manifest
                       (['plan-replay', '--root', str(root), '--chain', 'G', '--smoke', '--fake-kill-at', 'replay-child'], 3)):
        assert run_typed.main(argv) == code, argv
        captured = capsys.readouterr()
        printed.append(captured.out + captured.err)
    found = [json.loads(text) for text in printed]
    assert [f['verdict'] for f in found] == ['equal', 'different', 'error', 'error']
    assert found[0]['different'] == 0 and found[0]['files'] == 11
    assert set(found[2]) == {'command', 'chain', 'verdict', 'error_class', 'reason'} and found[2]['reason'] == 'replay_exception'
    assert not any(i in text for i in ids for text in printed) and 'Traceback' not in ''.join(printed)


@pytest.mark.parametrize('point', ['after-first-inputs', 'after-plan-file', 'replay-child'])
def test_a_kill_at_each_point_resumes_without_reading_a_class_twice_or_never(tmp_path, point):
    """R92, S2 (c): ``smoke --fake --configured --fake-kill-at <point>`` in its own session dies by SIGKILL (the
    parent with its replay child at 'replay-child'); after recovery.json, ``smoke --fake --configured --resume``
    completes: no .part file remains, the plan is bound and replays equal, its classes equal an uninterrupted
    smoke's, every pair is settled exactly once and every fresh cell holds one send."""
    script = str(TREE / 'scripts' / 'run_typed.py')
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    roots = {name: tmp_path / name for name in ('clean', 'killed')}

    def cli(*argv, session=False):
        return subprocess.run([sys.executable, script, *argv], cwd=str(tmp_path), env=env, capture_output=True,
                              text=True, timeout=600, start_new_session=session)
    assert cli('smoke', '--root', str(roots['clean']), '--chain', 'G', '--fake', '--configured').returncode == 0
    killed = cli('smoke', '--root', str(roots['killed']), '--chain', 'G', '--fake', '--configured', '--fake-kill-at',
                 point, session=True)
    assert killed.returncode == -9, killed.stderr[-2000:]
    base = Path(str(roots['killed']) + '-smoke') / 'G'
    units.write_json(base / 'recovery.json', {'by': 'owner', 'date': '2026-11-12', 'decision': 'resume after a kill',
                                              'same_phase': True})
    resumed = cli('smoke', '--root', str(roots['killed']), '--chain', 'G', '--fake', '--configured', '--resume')
    assert resumed.returncode == 0, resumed.stdout[-2000:] + resumed.stderr[-2000:]
    plans = {name: json.loads((Path(str(r) + '-smoke') / 'G' / 'read-plan.json').read_text()) for name, r in roots.items()}
    states = {name: json.loads((Path(str(r) + '-smoke') / 'G' / 'state.json').read_text()) for name, r in roots.items()}
    assert {b: e['classes'] for b, e in plans['killed']['benches'].items()} == \
        {b: e['classes'] for b, e in plans['clean']['benches'].items()}
    assert plans['killed']['counts'] == plans['clean']['counts']
    for name, state in states.items():
        assert state['complete'] and state['read_plan']['replay']['verdict'] == 'equal', name
        settled = [u.split('-', 1)[1] for u in state['done_units'] if (u.startswith('read-') and u != 'read-plan')
                   or u.startswith('alias-')]
        assert len(settled) == len(set(settled)) == 35, name
    assert sorted(states['killed']['done_units']) == sorted(states['clean']['done_units'])
    assert not [p for p in base.rglob('*.part')]
    for unit in (u for u in states['killed']['done_units'] if u.startswith('read-') and u != 'read-plan'):
        for cell in (base / ('practice-' + unit)).glob('cells/*.json'):
            assert len(json.loads(cell.read_text())['sends']) == 1
