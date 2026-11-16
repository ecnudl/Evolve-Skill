"""typed-v3 resume replay (docs/handoff/typed-v3/CHAIN-DECISIONS.md B6 d): the sealed option ``resume_replay`` ('off' =
typed-v2's resume, the code default; 'on' = a solver cell whose reply was saved before its record was written is
completed from its calls file, never sent again) and its one mechanism (``units.replaying`` for every solver cell:
the learning cells through ``chain._Run.builder``, the read cells through ``reads``; a replayed receipt is the one the
shell saw, its keys outside ``RECEIPT_KEYS`` kept as ``receipt_rest``; the role calls through P1's replay, which 'on'
turns on as 'repair' does) -- on fakes only (no network, no Docker, no /data, nothing paid). After Codex's review of
9c6d1f7: under 'on' every send names its occurrence and each occurrence is answered by its own outcome
(``units.ReplayRule``), and a pending call whose receipt reached its calls file is settled from it when the resumed
ledger opens. After its second look: a sealed read unit is opened for that only after its read's own checks; 'repair'
with 'off' keeps cb80dcc's unnumbered role-call replay; under 'on' a calls file without occurrences is refused.

A kill is a ``Kill`` (a BaseException, as a process death: nothing records a pause) raised right after a cell's solve
returned -- its receipt is in the cell's calls file, the cell record is not written -- or, for a role call, right after
the call returned and before its phase record. The resumed records are compared with an uninterrupted run's, the calls
files included; the ledger's counts and the scripted clients' sends too. Harnesses: P1's
(``tests/test_typed3_program_learning.py``) for the learning cell units and the role calls under 'single', P2b's
(``tests/test_typed3_item_stage.py``) for diagnose and items-check, P3r's (``tests/test_typed3_reads.py``) for a read
cell in run mode under the consent.
"""
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from scripts import run_typed
from skillopt.execskill import judge, typed as typed_
from skillopt.execskill.typed import chain, gates, prepare, smoke, units, writers
from skillopt.execskill.typed import reads as reads_module
from tests import test_typed2_gate as gate_v2
from tests import test_typed3_item_stage as stage
from tests import test_typed3_program_learning as learning
from tests import test_typed3_reads as reading
from tests import test_typed_chain as chain_v2
from tests.test_typed3_program_learning import Kill
from tests.test_typed3_program_learning import environ  # noqa: F401 -- main() cleans os.environ; this restores it
from tests.test_typed3_reads import qualified  # noqa: F401 -- the faked sheet qualification of run-mode reads
from tests.test_typed_chain import recovery
from tests.test_typed_schedule import inputs  # noqa: F401 -- prepare's fixture (pools, machinery record, typed tree)

NEUTRAL = Path('/tmp/typed3-replay-neutral').resolve()  # resolved: route B's safe_path refuses a symlink in any parent
NOW = '2026-11-15T00:00:00'
VOLATILE = {'logical_call', 'ledger', 'at', 'started', 'finished', 'updated'}
LEDGER_KEYS = ('sends', 'charged', 'reported', 'missing_usage', 'recovered', 'by_unit')


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='replay-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def every_record(root, chain_name='G'):
    """Every JSON record of the chain directory, the calls files included, but the state, the ledger, the first call's
    receipt and the owner's recovery files; send numbers, ledger snapshots and wall-clock stamps stripped."""
    base, out = Path(root, chain_name), {}
    for path in sorted(base.rglob('*.json')):
        rel = path.relative_to(base).as_posix()
        if rel not in ('state.json', 'ledger.json', 'confirm.json') and not rel.startswith('recovery'):
            out[rel] = strip(json.loads(path.read_text()))
    return out


def ledger_of(root, chain_name='G'):
    found = json.loads((Path(root) / chain_name / 'ledger.json').read_text())
    return {key: found[key] for key in LEDGER_KEYS}


def assert_same(found, expected):
    assert sorted(found) == sorted(expected)
    for rel in expected:
        assert found[rel] == expected[rel], rel


def kill_after_solve(services, unit, *, item_id=None):
    """``services.solve_fn`` that dies right after the first solve of ``unit`` (of ``item_id`` when given) returned:
    its reply is in the cell's calls file, the cell record is not written. Returns the list of hits."""
    solve, hit = services.solve_fn, []

    def dying(bench, item, mounted, **rest):
        row = solve(bench, item, mounted, **rest)
        if rest['unit'] == unit and (item_id is None or item['task_id'] == item_id) and not hit:
            hit.append((item['task_id'], rest['tag']))
            raise Kill()
        return row
    services.solve_fn = dying
    return hit


def calls_file(root, unit, tag, chain_name='G'):
    return json.loads((Path(root) / chain_name / unit / 'calls' / (tag + '.json')).read_text())


# ---- the option ----------------------------------------------------------------------------------------------------
def test_the_option_its_default_and_its_reader():
    assert (typed_.RESUME_REPLAYS, typed_.RESUME_REPLAY_DEFAULT) == (('off', 'on'), 'off')
    assert run_typed.RESUME_REPLAYS == typed_.RESUME_REPLAYS
    assert prepare.resume_replay_of({}) == 'off' == prepare.resume_replay_of(smoke.synthetic_manifest())
    assert prepare.resume_replay_of({'resume_replay': 'on'}) == 'on'
    for bad in ({'resume_replay': None}, {'resume_replay': 'yes'}, {'resume_replay': True}, {'resume_replay': ['on']},
                None, ['on']):
        with pytest.raises(ValueError):
            prepare.resume_replay_of(bad)


def test_prepare_seals_the_resume_replay_only_when_on(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    default = prepare.prepare(parent / 'execskill-20261114-typed-v3-smoke', **common)
    assert 'resume_replay' not in default and prepare.resume_replay_of(default) == 'off'
    made = prepare.prepare(parent / 'execskill-20261115-typed-v3-smoke', resume_replay='on', **common)
    assert made['resume_replay'] == 'on' and set(made) == set(default) | {'resume_replay'}
    assert prepare.load_manifest(made['root']) == made and prepare.resume_replay_of(made) == 'on'
    for n, bad in enumerate(('yes', None, True, 'ON')):
        new = parent / ('execskill-2026113%d-typed-v3-smoke' % n)
        with pytest.raises(ValueError):
            prepare.prepare(new, resume_replay=bad, **common)
        assert not new.exists()
    root, fields = Path(made['root']), {key: value for key, value in made.items() if key != 'record_sha256'}
    units.write_json(root / 'manifest.json', prepare.seal({**fields, 'resume_replay': 'maybe'}))
    with pytest.raises(ValueError, match='resume_replay'):
        prepare.load_manifest(root)


def test_the_cli_names_resume_replay_on_prepare_only(tmp_path, monkeypatch, environ, capsys):  # noqa: F811
    parse = run_typed.parser().parse_args
    assert parse(['prepare', '--root', '/r', '--resume-replay', 'on']).resume_replay == 'on'
    assert parse(['prepare', '--root', '/r']).resume_replay is None
    for bad in (['prepare', '--root', '/r', '--resume-replay', 'yes'],
                ['run', '--root', '/r', '--chain', 'G', '--resume-replay', 'on'],
                ['smoke', '--root', '/r', '--chain', 'G', '--fake', '--resume-replay', 'on']):
        with pytest.raises(SystemExit):
            parse(bad)
    calls, adapter = [], run_typed._prepare
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(kw) or {  # sealed only when 'on'
        'configuration': 'typed-v3', **({'resume_replay': 'on'} if kw.get('resume_replay') == 'on' else {})})
    root, machinery = tmp_path / 'run', tmp_path / 'machinery.json'
    root.mkdir()
    machinery.write_text(json.dumps({'runtime': {}}))
    expected = {'machinery_manifest': str(machinery), 'roles_repo': typed_.ROLES_REPO, 'pools_root': typed_.POOLS_ROOT,
                'smoke': False}
    for flag, named in (([], {}), (['--resume-replay', 'on'], {'resume_replay': 'on'}),
                        (['--resume-replay', 'off'], {'resume_replay': 'off'})):
        assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery), *flag]) == 0
        assert calls[-1] == {**expected, **named}
        printed = json.loads(capsys.readouterr().out)['manifest']
        assert printed.get('resume_replay') == ('on' if named.get('resume_replay') == 'on' else None)
        assert ('resume_replay' in printed) == (named.get('resume_replay') == 'on')
    seen = []  # the adapter hands prepare only what the command names (the code default otherwise)
    monkeypatch.setattr(prepare, 'prepare', lambda root, **kw: seen.append(kw) or {})
    common = dict(machinery_manifest='/m.json', roles_repo='/creds', pools_root='/pools', smoke=True)
    adapter('/r', **common)
    adapter('/r', resume_replay='on', **common)
    assert seen == [common, {**common, 'resume_replay': 'on'}]


def test_a_state_started_with_one_resume_replay_refuses_the_other_and_a_bad_manifest_writes_nothing(tmp_path):
    default = chain._open_state(tmp_path / 'a', 'G', 'smoke', False)
    assert 'resume_replay' not in default  # typed-v2's state shape
    made = chain._open_state(tmp_path / 'b', 'G', 'smoke', False, resume_replay='on')
    assert made['resume_replay'] == 'on'
    for name, state in (('a', default), ('b', made)):
        (tmp_path / name).mkdir()
        units.write_json(tmp_path / name / 'state.json', state)
    assert chain._open_state(tmp_path / 'b', 'G', 'smoke', True, resume_replay='on') == made
    with pytest.raises(ValueError, match='another resume_replay'):
        chain._open_state(tmp_path / 'b', 'G', 'smoke', True)
    with pytest.raises(ValueError, match='another resume_replay'):
        chain._open_state(tmp_path / 'a', 'G', 'smoke', True, resume_replay='on')
    root = tmp_path / 'bad'
    services = learning.build(root, learning.Engineer(learning.program('v0', note=['l0'])))
    services.manifest['resume_replay'] = 'yes'
    with pytest.raises(ValueError, match='resume_replay'):
        chain.run(root, 'G', services=services, sleep=lambda s: None)
    assert not root.exists()


# ---- the mechanism ------------------------------------------------------------------------------------------------
def test_a_cell_recorder_replays_its_saved_receipts_and_reports_its_own_path(tmp_path):
    """``units.replaying`` over the recorder of a cell. No calls file: the recorder itself, set to keep each receipt's
    keys outside ``RECEIPT_KEYS`` (``receipt_rest``; a recorder never wrapped keeps typed-v2's send record). A calls
    file of an earlier attempt: each delivered receipt of a request answered once, in file order, as the shell saw it
    (``receipt_rest`` included: chain D's ``over_nominal``, which the judge flags) -- no send, no charge, the file
    unchanged -- and a call beyond them sent and appended after the earlier sends; the request hash is the transformed
    request's, as the recorder saved it. Only a failure (an infrastructure timeout at the end of the file): sent again,
    the earlier send stays in the file, and the cell's sends, tokens and infrastructure flag are the new send's alone
    (as typed-v2's resend, which rewrote the file with the new send only)."""
    system = 'solver system'
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 6)
    fresh = []

    def client(system_, user):
        fresh.append(user)
        made = smoke.receipt('%s-%d' % (user, len(fresh)), model='m', system=system_, user=user)
        return {**made, 'route': 'B', 'over_nominal': user == 'A'}  # as route B's client adds them

    def recorder(name, transform=None):
        return units.CallRecorder(client, ledger, max_tokens=50, tag=name, unit='s1/noise',
                                  out_path=tmp_path / 'calls' / (name + '.json'), transform=transform)

    def file(name):
        return json.loads((tmp_path / 'calls' / (name + '.json')).read_text())
    plain = recorder('plain')
    assert plain(system, 'P')['response'] == 'P-1' and set(file('plain')[0]) == {
        'request_sha256', 'system', 'user', 'logical_call', 'receipt', 'charge_bound', 'reserved'}  # typed-v2's shape
    first = units.replaying(recorder('delivered'))
    assert type(first) is units.CallRecorder and first.keep_rest is True
    originals = [first(system, 'A'), first(system, 'A')]
    assert [row['response'] for row in originals] == ['A-2', 'A-3'] and originals[0]['over_nominal'] is True
    saved = file('delivered')
    assert saved[0]['receipt_rest'] == {key: originals[0][key] for key in originals[0] if key not in units.RECEIPT_KEYS}
    assert {'over_nominal', 'route', 'status', 'usage_valid'} <= set(saved[0]['receipt_rest'])
    again = units.replaying(recorder('delivered'))
    assert isinstance(again, units.ReplayingRecorder) and again.unit == 's1/noise'  # the rest is the recorder's
    shown = [again(system, 'A'), again(system, 'A')]
    blank = dict.fromkeys(units.RECEIPT_KEYS)  # the saved projection names every RECEIPT_KEYS key
    assert shown == [{**blank, **row} for row in originals] and again.receipts == shown
    assert len(fresh) == 3 and ledger.state['sends'] == 3 and file('delivered') == saved
    assert again.sends == saved and again.tokens() == first.tokens() > 0 and len(again.replayed) == 2
    assert again(system, 'A')['response'] == 'A-4' and again(system, 'B')['response'] == 'B-5'
    grown = file('delivered')
    assert grown[:2] == saved and [row['user'] for row in grown] == ['A'] * 3 + ['B'] and again.sends == grown
    assert ledger.state['sends'] == 5 and len(again.receipts) == 4
    shout = lambda system_, user: (system_, user.upper())  # noqa: E731
    assert units.replaying(recorder('loud', shout))(system, 'c')['response'] == 'C-6'
    assert units.replaying(recorder('loud', shout))(system, 'c')['response'] == 'C-6' and len(fresh) == 6
    failed = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'timeout'}
    units.write_json(tmp_path / 'calls' / 'failed.json', [{**saved[0], 'receipt': failed}])
    retry = units.replaying(recorder('failed'))
    assert retry(system, 'A')['response'] == 'A-7' and len(fresh) == 7 and ledger.state['sends'] == 7
    kept = file('failed')
    assert [row['receipt']['ok'] for row in kept] == [False, True] and retry.replayed == []
    assert retry.sends == kept[1:] and not retry.infrastructure_unknown()
    assert retry.tokens() == units.tokens_of(kept[1:])
    used = recorder('used')
    used.sends.append(saved[0])
    units.write_json(tmp_path / 'calls' / 'used.json', saved)
    with pytest.raises(ValueError):
        units.replaying(used)  # a recorder that already sent is never preloaded


def test_a_cell_run_again_after_its_record_was_archived_replays_its_delivered_receipts_only(tmp_path):
    """A cell's calls file [A failed, B delivered]: its flow went past A's failure (a selection call, then its
    delivered format retry). The cell never recorded (a kill after B): A's failure and B are replayed, nothing is sent
    -- the attempt completes as the uninterrupted one did. The same cell with an earlier record archived for a re-run
    (``rerun/<tag>-1.json``: its outcome was an infrastructure unknown): A is sent again -- the re-run exists to heal
    that failure -- and B is still replayed. The archive is found for the selection's calls file too."""
    system, tag = 'solver system', 'c' * 64
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 6)
    fresh, unit = [], tmp_path / 's1' / 'noise'

    def client(system_, user):
        fresh.append(user)
        return smoke.receipt('new ' + user, model='m', system=system_, user=user)

    earlier, path = [saved_send(system, 'A', 1), saved_send(system, 'B', 1, 'RB')], unit / 'calls' / (tag + '.json')

    def resumed():
        units.write_json(path, earlier)
        return units.replaying(units.CallRecorder(client, ledger, max_tokens=50, tag=tag, unit='s1/noise',
                                                  out_path=path))
    call = resumed()
    assert [call(system, 'A')['ok'], call(system, 'B')['response']] == [False, 'RB'] and fresh == []
    assert call.sends == earlier and call.infrastructure_unknown()  # the uninterrupted attempt's path
    assert not units.archived_for_rerun(path, tag)
    units.write_json(unit / 'rerun' / (tag + '-1.json'), {'tag': tag, 'correct': None, 'infrastructure_unknown': True})
    assert units.archived_for_rerun(path, tag)
    assert units.archived_for_rerun(unit / 'calls' / (tag + '-selection.json'), tag)
    assert not units.archived_for_rerun(path, 'd' * 64)
    call = resumed()
    assert [call(system, 'A')['response'], call(system, 'B')['response']] == ['new A', 'RB'] and fresh == ['A']
    assert [row['user'] for row in call.sends] == ['A', 'B'] and not call.infrastructure_unknown()
    assert [row['user'] for row in units.read_json(path)] == ['A', 'B', 'A']  # the failure stays in the calls file


def saved_send(system, user, occurrence=None, response=None):
    """A send record as an earlier attempt saved it: delivered ``response``, else a timeout."""
    made = (smoke.receipt(response, model='m', system=system, user=user) if response is not None
            else dict(learning.INFRA_FAILURE))
    return {'request_sha256': units.sha256_text(system + '\x00' + user), 'system': system, 'user': user,
            'logical_call': 'earlier', 'receipt': {key: made.get(key) for key in units.RECEIPT_KEYS},
            'charge_bound': 100, 'reserved': 400, **({'occurrence': occurrence} if occurrence is not None else {})}


def test_each_occurrence_of_a_request_is_answered_by_its_own_outcome(tmp_path):
    """Codex's review of 9c6d1f7, finding 1, on the rule itself: the k-th call of a request is its occurrence k, and
    occurrence k is answered by its own saved outcome. A file [A#1 timed out, B#1 delivered, A#2 delivered, C#1 timed
    out]: A#1 gets its failure (the flow went past it), B#1 and A#2 their receipts, C#1 (the end of the file, where the
    earlier process stood) and A#3 (never made) are sent -- in order A B A C A the calls get the failure, RB, RA2,
    then two sends, the resends numbered as the occurrences they replace (C#1, A#3). A second resume answers every
    call from the file. Without occurrences the old rule would give A's delivered receipt to its FIRST call."""
    system = 'solver system'

    def sha(user):
        return units.sha256_text(system + '\x00' + user)
    earlier = [saved_send(system, 'A', 1), saved_send(system, 'B', 1, 'RB'), saved_send(system, 'A', 2, 'RA2'),
               saved_send(system, 'C', 1)]
    rule = units.ReplayRule(earlier, numbered=True)
    assert rule.numbered and rule.replays
    assert [rule.answer(sha('A'), 1), rule.answer(sha('B'), 1), rule.answer(sha('A'), 2)] == earlier[:3]
    assert rule.answer(sha('C'), 1) is None and rule.answer(sha('A'), 3) is None
    assert units.ReplayRule(earlier, failures=False, numbered=True).answer(sha('A'), 1) is None  # an archived re-run
    unnumbered = [{key: value for key, value in send.items() if key != 'occurrence'} for send in earlier]
    legacy = units.ReplayRule(unnumbered)  # 'repair' with 'off': cb80dcc's rule, delivered receipts first
    assert not legacy.numbered and legacy.answer(sha('A'))['receipt']['response'] == 'RA2'
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 6)
    fresh, path = [], tmp_path / 's1' / 'noise' / 'calls' / ('e' * 64 + '.json')
    units.write_json(path, earlier)

    def client(system_, user):
        fresh.append(user)
        return smoke.receipt('new ' + user, model='m', system=system_, user=user)

    def resumed():
        return units.replaying(units.CallRecorder(client, ledger, max_tokens=50, tag='e' * 64, unit='s1/noise',
                                                  out_path=path))
    call = resumed()
    replies = [call(system, user).get('response') for user in ('A', 'B', 'A', 'C', 'A')]
    assert replies == [None, 'RB', 'RA2', 'new C', 'new A'] and fresh == ['C', 'A']
    kept = units.read_json(path)
    assert [(row['user'], row['occurrence']) for row in kept[4:]] == [('C', 1), ('A', 3)]
    assert [row['occurrence'] for row in call.sends] == [1, 1, 2, 1, 3]  # this attempt's path, in call order
    call = resumed()
    assert [call(system, user).get('response') for user in ('A', 'B', 'A', 'C', 'A')] == replies
    assert fresh == ['C', 'A'] and units.read_json(path) == kept


def test_the_resumed_ledger_settles_a_saved_receipt_once_and_recovers_every_other_pending_call(tmp_path):
    """Finding 2 of the review of 9c6d1f7 on the ledger itself: three calls reserved and never settled -- 'saved' (its
    delivered receipt reached its calls file), 'cut' (the process died inside the client: the record holds no receipt
    and no exception) and 'raised' (the client raised: no receipt). Resumed with ``durable_receipts``: 'saved' is
    settled from its receipt exactly as ``Ledger.settle`` settles it (the reference below), the other two are
    recovered as before (kept reservation, missing usage, a re-run mark); resumed without, all three are recovered."""
    system, chain_dir = 'solver system', tmp_path / 'G'
    receipt = smoke.receipt('R', model='m', system=system, user='saved')

    def reserve(path):
        ledger = units.Ledger(path, 10 ** 6)
        return ledger, {name: ledger.before_send(system, name, 50, cell='t-' + name, unit='s1/noise')
                        for name in ('saved', 'cut', 'raised')}
    _, keys = reserve(chain_dir / 'ledger.json')
    calls = chain_dir / 's1' / 'noise' / 'calls'
    for name, extra in (('saved', {'receipt': {key: receipt.get(key) for key in units.RECEIPT_KEYS}}), ('cut', {}),
                        ('raised', {'exception': 'RuntimeError'})):
        key, bound = keys[name]
        units.write_json(calls / ('t-%s.json' % name), [{
            'request_sha256': units.sha256_text(system + '\x00' + name), 'system': system, 'user': name,
            'logical_call': key, 'receipt': None, 'charge_bound': bound, 'reserved': 4 * bound, 'occurrence': 1,
            **extra}])
    expected, made = reserve(tmp_path / 'expected.json')
    expected.settle(made['saved'][0], receipt)
    expected = units.Ledger(tmp_path / 'expected.json', 10 ** 6, resume=True)  # the two others recovered as before
    resumed = units.Ledger(chain_dir / 'ledger.json', 10 ** 6, resume=True,
                           durable=lambda pending: units.durable_receipts(chain_dir, pending))
    def timeless(rows):
        return [{key: value for key, value in row.items() if key != 'at'} for row in rows]
    assert timeless(resumed.state['recovered']) == timeless(expected.state['recovered'])
    assert [row['cell'] for row in resumed.state['recovered']] == ['t-cut', 't-raised']
    assert {key: resumed.state[key] for key in LEDGER_KEYS if key != 'recovered'} == {
        key: expected.state[key] for key in LEDGER_KEYS if key != 'recovered'}
    assert resumed.state['pending'] == {} and resumed.state['reported'] == receipt['usage']['total_tokens']
    assert resumed.rerun_cells == expected.rerun_cells == {('s1/noise', 't-cut'), ('s1/noise', 't-raised')}
    plain = units.Ledger(chain_dir / 'ledger.json', 10 ** 6, resume=True)  # nothing pending is left to settle
    assert plain.state['recovered'] == resumed.state['recovered']
    _, again = reserve(tmp_path / 'G2' / 'ledger.json')
    unsettled = units.Ledger(tmp_path / 'G2' / 'ledger.json', 10 ** 6, resume=True)  # typed-v2: no durable
    assert [row['cell'] for row in unsettled.state['recovered']] == ['t-saved', 't-cut', 't-raised']


def test_the_role_call_replay_numbers_its_resends_as_the_occurrences_they_replace(tmp_path):
    """The same rule for a role recorder under 'on' (``chain._replay_receipts(numbered=True)`` over
    ``_keep_earlier_sends``, P1 F5): a writer file [A#1 delivered R1, B#1 timed out] (B ends the file: where the
    earlier process stood). Resumed, the flow A B A gets R1, then B sent again as occurrence 1 and the second A sent
    as occurrence 2; a second resume answers the whole flow from the file. A recorder that is not replaying still
    names each occurrence under 'on' -- and none under 'repair' with 'off' (cb80dcc's unnumbered records)."""
    system = 'role system'
    earlier = [saved_send(system, 'A', 1, 'R1'), saved_send(system, 'B', 1)]
    path, fresh = tmp_path / 'calls' / 'writer-program_writer.json', []
    units.write_json(path, earlier)
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 6)

    def client(system_, user):
        fresh.append(user)
        return smoke.receipt('new ' + user, model='m', system=system_, user=user)

    def resumed():
        return chain._replay_receipts(chain._keep_earlier_sends(units.CallRecorder(
            client, ledger, max_tokens=50, tag='writer', unit='s1/programs', out_path=path)), numbered=True)
    call = resumed()
    assert [writers.reply_of(call(system, user)) for user in ('A', 'B', 'A')] == ['R1', 'new B', 'new A']
    kept = units.read_json(path)
    assert fresh == ['B', 'A'] and [(row['user'], row['occurrence']) for row in kept[2:]] == [('B', 1), ('A', 2)]
    call = resumed()
    assert [writers.reply_of(call(system, user)) for user in ('A', 'B', 'A')] == ['R1', 'new B', 'new A']
    assert fresh == ['B', 'A'] and units.read_json(path) == kept
    for numbered, expected in ((True, [1, 2]), (False, [None, None])):
        out = tmp_path / 'calls' / ('w-%s.json' % numbered)
        plain = chain._replay_receipts(units.CallRecorder(client, ledger, max_tokens=50, tag='w', unit='s1/programs',
                                                          out_path=out), numbered=numbered)
        assert isinstance(plain, units.CallRecorder)  # nothing to replay: the recorder itself ...
        plain(system, 'A'), plain(system, 'A')
        assert [row.get('occurrence') for row in units.read_json(out)] == expected  # ... counting under 'on' only


def test_a_replayed_chain_d_receipt_keeps_what_the_judge_flags(tmp_path):
    """Codex's review of 9c6d1f7, finding 3: route B's client (chain D) adds keys outside ``RECEIPT_KEYS`` that the
    frozen judge reads -- ``subtype`` 'reasoning_mismatch' on a reply with reasoning, ``over_nominal`` on a reply above
    the nominal M. A cell's flow: the request answered with a mismatch, sent again (its occurrence 2) and delivered
    above M. Replayed after a kill, both receipts are the ones the shell saw (the receipts below, the projection's
    absent keys as None), and the judge flags 'over_nominal' and 'reasoning_mismatch' on them as on the originals."""
    usage = {'prompt_tokens': 30, 'completion_tokens': 9, 'total_tokens': 39}
    mismatch = {'ok': False, 'response': None, 'finish_reason': 'stop', 'usage': usage, 'usage_valid': True,
                'returned_model': 'deepseek-flash', 'reasoning_chars': 0, 'reasoning_tokens': 4,
                'visible_completion_tokens': 5, 'over_nominal': False, 'error_type': 'thinking_mismatch',
                'subtype': 'reasoning_mismatch', 'status': 200, 'attempts': [{'status': 200, 'seconds': 0.1}],
                'seconds': 0.1, 'route': 'B', 'route_model': 'deepseek-v4-flash'}
    delivered = {key: value for key, value in mismatch.items() if key != 'subtype'}
    delivered.update(ok=True, response='The answer is 42.', error_type=None, reasoning_tokens=0,
                     visible_completion_tokens=9, over_nominal=True)
    script = [mismatch, delivered]
    ledger, path = units.Ledger(tmp_path / 'ledger.json', 10 ** 6), tmp_path / 's1' / 'noise' / 'calls' / 'f.json'

    def recorder():
        return units.replaying(units.CallRecorder(lambda system, user: dict(script.pop(0)), ledger, max_tokens=50,
                                                  tag='f', unit='s1/noise', out_path=path))
    first = recorder()
    seen = [first('solver system', 'Q'), first('solver system', 'Q')]
    assert seen == [mismatch, delivered] and not script
    call = recorder()  # the resumed cell: both answered from the calls file
    replayed = [call('solver system', 'Q'), call('solver system', 'Q')]
    blank = dict.fromkeys(units.RECEIPT_KEYS)
    assert replayed == [{**blank, **mismatch}, {**blank, **delivered}] and ledger.state['sends'] == 2

    def flags(receipts):
        return judge._flags('searchqa', {'answer': '42'}, {'reason': 'model_response_available'}, receipts, 1,
                            'pass', 'pass', None)
    assert flags(replayed) == flags(seen) == ['over_nominal', 'reasoning_mismatch']


class _Seen:
    """``call`` with every receipt it returned noted in ``receipts``; every other attribute is read from ``call``."""

    def __init__(self, call):
        self._call, self.receipts = call, []

    def __call__(self, system, user):
        found = self._call(system, user)
        self.receipts.append(found)
        return found

    def __getattr__(self, name):
        return getattr(self._call, name)


class Flagged(learning.Engineer):
    """P1's scripted clients whose solver receipts carry route B's ``over_nominal`` (chain D's client adds it when a
    completion is above the nominal M): a key outside ``RECEIPT_KEYS``, which the frozen judge flags."""

    def send(self, purpose, system, user, *, model, unit=None):
        found = super().send(purpose, system, user, model=model, unit=unit)
        return {**found, 'over_nominal': True} if purpose == 'solver' else found


def flagging(solve):
    """``solve`` whose row flags 'over_nominal' when a receipt the shell saw says so (as ``judge._flags``)."""
    def run(bench, item, mounted, *, call, **rest):
        seen = _Seen(call)
        row = solve(bench, item, mounted, call=seen, **rest)
        flagged = any(isinstance(r, dict) and r.get('over_nominal') is True for r in seen.receipts)
        return {**row, 'flags': sorted(set(row.get('flags') or ()) | ({'over_nominal'} if flagged else set()))}
    return run


# ---- (1) a learning cell unit: the noise calibration, a program's gate --------------------------------------------
@pytest.mark.parametrize('mode', ['off', 'on'])
@pytest.mark.parametrize('unit', ['s1/noise', 's1/program-1-gate'])
def test_a_cell_killed_after_its_reply_was_saved_resumes_without_a_send_under_on(tmp_path, monkeypatch, unit, mode):
    """P1's harness (SearchQA, 'repair'; the solver's receipts carry ``over_nominal``, which the cell row flags): the
    process dies right after the first cell of s1/noise, or of the program's gate s1/program-1-gate, was solved. 'on':
    the resumed cell is answered from its calls file as the shell first saw it (``over_nominal`` included, so the
    row's flags too) -- zero new sends, the ledger as an uninterrupted run's, every record and calls file the same.
    'off' (typed-v2): the cell is solved again -- one more send and one more charged call for that unit; the fake's
    reply is the same, so the records are too."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    v0 = learning.program('v0', note=['l0', 'g0', 'g1', 'g2'])
    reference, resumed = tmp_path / 'a', tmp_path / 'b'

    def services_of(root, script):
        services = learning.build(root, script)
        services.solve_fn = flagging(services.solve_fn)
        if mode == 'on':
            services.manifest['resume_replay'] = 'on'
        return services
    script_a = Flagged(v0)
    state = chain.run(reference, 'G', services=services_of(reference, script_a), sleep=lambda s: None)
    assert state['complete'], state['paused']
    script_b = Flagged(v0)
    services = services_of(resumed, script_b)
    hit = kill_after_solve(services, unit)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    (item_id, tag), = hit
    cell = Path(resumed, 'G', *unit.split('/'), 'cells', tag + '.json')
    assert not cell.exists()
    assert calls_file(resumed, unit, tag)[0]['receipt']['ok'] is True  # the reply was saved
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert json.loads(cell.read_text())['flags'] == ['over_nominal']
    assert_same(every_record(resumed), every_record(reference))
    extra = 0 if mode == 'on' else 1
    assert Counter(script_b.calls) == Counter(script_a.calls) + Counter({('solver', unit): extra})
    ledger_a, ledger_b = ledger_of(reference), ledger_of(resumed)
    assert ledger_b['sends'] == ledger_a['sends'] + extra
    assert ledger_b['by_unit'][unit]['calls'] == ledger_a['by_unit'][unit]['calls'] + extra
    if mode == 'on':
        assert ledger_b == ledger_a
        assert 'receipt_rest' in calls_file(resumed, unit, tag)[0]
    else:
        assert 'receipt_rest' not in calls_file(resumed, unit, tag)[0]  # typed-v2's calls file


# ---- re-runs under 'on': an archived infrastructure unknown, typed-v2's SIGINT and outage cases -------------------
EXTRA = ('extra system', 'extra request')


class Flaky(learning.Engineer):
    """P1's scripted clients; the first send of the request ``EXTRA`` fails (a timeout receipt), every later one is
    delivered."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra = 0

    def send(self, purpose, system, user, *, model, unit=None):
        found = super().send(purpose, system, user, model=model, unit=unit)
        if (system, user) == EXTRA:
            with self.lock:
                self.extra += 1
                first = self.extra == 1
            if first:
                return dict(learning.INFRA_FAILURE)
        return found


def going_past(solve, unit, item_id):
    """``solve`` whose cells of ``unit`` on ``item_id`` first send ``EXTRA`` -- a call whose failure the shell goes past
    (the solve's own call follows) -- and whose verdict is unknown when that call failed (a shell that needs both
    replies): such a cell is an infrastructure unknown with the calls file [EXTRA failed, the solve's reply]."""
    def run(bench, item, mounted, *, call, **rest):
        if rest['unit'] != unit or item['task_id'] != item_id:
            return solve(bench, item, mounted, call=call, **rest)
        extra = call(*EXTRA)
        row = solve(bench, item, mounted, call=call, **rest)
        return row if extra.get('ok') else {**row, 'correct': None, 'token': 'unknown_timeout'}
    return run


@pytest.mark.parametrize('mode', ['off', 'on'])
def test_an_infrastructure_unknown_cell_whose_flow_went_past_a_failure_is_healed_by_its_rerun(tmp_path, monkeypatch,
                                                                                            mode):
    """P1's harness: one noise cell of searchqa-g0 is an infrastructure unknown whose flow went past the failure (its
    calls file [EXTRA failed, the solve's reply delivered]); the arm is undecidable, the chain pauses
    'gate_cells_unknown', the owner's recovery archives the cell (``rerun/<tag>-1.json``) and runs it again. 'on':
    EXTRA is sent again (a failure is never replayed in a re-run: replayed, it would make the same unknown after
    every recovery), the solve's delivered reply is replayed -- one send; the calls file keeps all three sends and the
    healed cell records its own path. 'off' (typed-v2): both are sent again, the calls file holds the re-run's
    sends."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = Flaky(learning.program('v0', note=['l0', 'g0', 'g1', 'g2']))
    services = learning.build(tmp_path, script)
    services.solve_fn = going_past(services.solve_fn, 's1/noise', 'searchqa-g0')
    if mode == 'on':
        services.manifest['resume_replay'] = 'on'
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'gate_cells_unknown' and state['paused']['unit'] == 's1/noise'
    unit = tmp_path / 'G' / 's1' / 'noise'
    [tag] = [p.stem for p in (unit / 'cells').glob('*.json') if json.loads(p.read_text())['infrastructure_unknown']]

    def sends():
        return [(send['user'] == EXTRA[1], send['receipt']['ok']) for send in calls_file(tmp_path, 's1/noise', tag)]
    assert sends() == [(True, False), (False, True)]
    calls = ledger_of(tmp_path)['by_unit']['s1/noise']['calls']
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert [p.name for p in (unit / 'rerun').glob('*.json')] == [tag + '-1.json']
    healed = json.loads((unit / 'cells' / (tag + '.json')).read_text())
    assert healed['correct'] is not None and not healed['infrastructure_unknown']
    assert script.extra == 4  # the item's three noise cells, then the re-run's EXTRA (sent again in both modes)
    assert [send['user'] == EXTRA[1] for send in healed['sends']] == [True, False]
    again = ledger_of(tmp_path)['by_unit']['s1/noise']['calls'] - calls
    if mode == 'on':
        assert again == 1 and sends() == [(True, False), (False, True), (True, True)]
        found = calls_file(tmp_path, 's1/noise', tag)
        assert healed['sends'] == [found[2], found[1]]  # this attempt's path: the new EXTRA, then the replayed reply
    else:
        assert again == 2 and sends() == [(True, True), (False, True)]


@pytest.mark.parametrize('unit', ['s1/card-r1', 's1/noise'])
def test_under_on_a_sigint_inside_a_cell_call_is_sent_again_and_counted_as_a_rerun(tmp_path, unit):
    """typed-v2's fix-b case (``tests/test_typed2_gate.py``) under 'on': the call interrupted inside the client has no
    receipt, so nothing is replayed: the cell is sent again (R + 1 requests for that item and label), the decision or
    noise record counts the re-run and the ledger recovers the call, as under 'off' -- and the cell's calls file keeps
    the interrupted send before the new one, while the cell records the new send only."""
    services, modules, script = chain_v2.build(tmp_path, order=('searchqa',), proposals={'searchqa': ['p-sq-1']})
    services.manifest['resume_replay'] = 'on'
    fired = gate_v2.interrupt_once(services, unit)
    seen = gate_v2.counting(services)
    with pytest.raises(KeyboardInterrupt):
        chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert [count for key, count in seen.items() if key[0] == unit and key[3] == fired['tag']] == [2]
    assert all(count == 1 for key, count in seen.items() if key[3] != fired['tag'])
    decisions = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())
    if unit == 's1/noise':
        assert decisions['noise']['reruns'] == 1
    else:
        card = decisions['cards'][0]
        assert card['reruns'] == {'baseline': 0, 'candidate': 1} and gates.recompute(card) == card
    recovered = json.loads((tmp_path / 'G' / 'ledger.json').read_text())['recovered']
    assert [(row['unit'], row['cell']) for row in recovered] == [(unit, fired['tag'])]
    kept = calls_file(tmp_path, unit, fired['tag'])
    assert [(send.get('exception'), (send['receipt'] or {}).get('ok')) for send in kept] == [
        ('KeyboardInterrupt', None), (None, True)]
    assert json.loads(Path(tmp_path, 'G', *unit.split('/'), 'cells', fired['tag'] + '.json').read_text())[
        'sends'] == kept[1:]


def test_under_on_the_cells_of_an_outage_are_rerun_and_their_failures_sent_again(tmp_path):
    """typed-v2's outage case (``tests/test_typed_chain.py``: every other send fails, nine of the eighteen noise
    cells are infrastructure unknowns, the chain pauses 'gate_cells_unknown') under 'on': the recovery re-runs the nine
    cells, each sends its failed request again (nothing delivered to replay), the calibration completes with no
    unknown left, and each calls file keeps the failure before the delivered reply."""
    counter = {'n': 0, 'healthy': False}

    def alternating(system, user):
        counter['n'] += 1
        if not counter['healthy'] and counter['n'] % 2 == 0:
            return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'transport'}
        return 'The answer is 42.'
    sizes = {bench: {'learn': 2, 'gate': 6, 'panel': 2} for bench in typed_.ORDER}
    services, modules, script = chain_v2.build(tmp_path, order=('searchqa',),
                                               scripted={'replies': {'solver': alternating}}, sizes=sizes)
    services.manifest['resume_replay'] = 'on'
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'gate_cells_unknown' and state['paused']['unit'] == 's1/noise'
    counter['healthy'] = True
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    noise_dir = tmp_path / 'G' / 's1' / 'noise'
    noise = json.loads((noise_dir / 'noise.json').read_text())
    assert noise['n'] == 6 and noise['unknown_final'] == 0 and noise['reruns'] == 9 and noise['cells'] == 18
    tags = [p.name.rsplit('-', 1)[0] for p in (noise_dir / 'rerun').glob('*.json')]
    assert len(tags) == 9
    for tag in tags:
        assert [send['receipt']['ok'] for send in calls_file(tmp_path, 's1/noise', tag)] == [False, True]


# ---- the role calls under typed-v2's program learning 'single' ----------------------------------------------------
# point: (unit, phase record, purpose of the role call made inside it)
ROLE_WINDOWS = {'card': ('s1/card-r1', 'writer.json', 'card_writer'),
                'proposal': ('s1/programs', 'proposals.json', 'program_writer'),
                'describer': ('s1/program-1', 'skill.json', 'describer')}


@pytest.mark.parametrize('mode', ['off', 'on'])
@pytest.mark.parametrize('point', sorted(ROLE_WINDOWS))
def test_under_single_a_role_call_saved_before_its_record_is_replayed_under_on_only(tmp_path, monkeypatch, point,
                                                                                   mode):
    """The program learning 'single' (typed-v2's, where P1's replay of role calls is off): the process dies after a role
    call's receipt reached its calls file and before the phase record that holds what it returned -- the card writer
    (s1/card-r1/writer.json), the engineer's proposal (s1/programs/proposals.json), the describer of the accepted
    program (s1/program-1/skill.json). 'on': the resumed step answers the call from its saved receipt -- no send, and
    every record, every calls file and the ledger's counts as an uninterrupted run's. 'off' (typed-v2): it is sent
    again, once."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    v0 = learning.program('v0', note=['l0', 'g0', 'g1', 'g2'])
    unit, name, purpose = ROLE_WINDOWS[point]
    reference, resumed = tmp_path / 'a', tmp_path / 'b'

    def services_of(root, script):
        services = learning.build(root, script, mode='single')
        if mode == 'on':
            services.manifest['resume_replay'] = 'on'
        return services
    script_a = learning.Engineer(v0)
    state = chain.run(reference, 'G', services=services_of(reference, script_a), sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert learning.read(reference, 's1', 'program-1', 'decision.json')['accepted']
    original, hit = chain._Run.record, []

    def record(self, unit_, name_, compute):
        if (unit_, name_) == (unit, name) and not hit:
            compute()            # the call is made and its receipt saved in the unit's calls file ...
            hit.append(unit_)
            raise Kill()         # ... and the process dies before the record is written
        return original(self, unit_, name_, compute)
    monkeypatch.setattr(chain._Run, 'record', record)
    script_b = learning.Engineer(v0)
    services = services_of(resumed, script_b)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit and not (resumed / 'G' / unit / name).exists()
    assert Counter(script_b.calls)[(purpose, unit)] == Counter(script_a.calls)[(purpose, unit)] == 1
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    extra = 0 if mode == 'on' else 1
    assert Counter(script_b.calls) == Counter(script_a.calls) + Counter({(purpose, unit): extra})
    ledger_a, ledger_b = ledger_of(reference), ledger_of(resumed)
    assert ledger_b['sends'] == ledger_a['sends'] + extra
    if mode == 'on':
        assert_same(every_record(resumed), every_record(reference))
        assert ledger_b == ledger_a


class TwinFixes(learning.Engineer):
    """P1's scripted clients for Codex's case (review of 9c6d1f7, finding 1): the proposal holds two identical
    records that fail the static screen ([import] os), so their two fix requests are identical (a fix request names
    no ordinal); the first fix send times out, every later one returns the screened program."""

    def __init__(self, good):
        super().__init__(good)
        self.good, self.fixes = good, 0

    def program_writer(self, system, user):
        kind = json.loads(user).get('request')
        if kind == 'propose':
            bad = 'import os\n\n\n' + self.good
            return smoke.program_reply([(learning.ENTRY, bad), (learning.ENTRY, bad)])
        if kind == 'fix':
            with self.lock:
                self.fixes += 1
                first = self.fixes == 1
            return dict(learning.INFRA_FAILURE) if first else smoke.program_reply([(learning.ENTRY, self.good)])
        return super().program_writer(system, user)


def test_two_identical_fix_requests_whose_first_timed_out_resume_in_their_own_order(tmp_path, monkeypatch):
    """Codex's exact case (review of 9c6d1f7, finding 1): 'on' with the program learning 'single'; two identical
    proposals fail the screen, their identical fix requests are occurrences 1 and 2 of one request; fix 1 times out
    (proposal 1 is dropped), fix 2 returns a valid repair (proposal 2 passes after its fix and takes slot 1 as
    p-searchqa-1-2); the process dies before proposals.json. The resumed unit answers occurrence 1 with its timeout and
    occurrence 2 with its repair -- the delivered receipt no longer goes to the first call (which made p-searchqa-1-1)
    -- so it writes the uninterrupted proposals.json, sends nothing, and every record and the ledger are the same."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    good = learning.program('v0', note=['l0', 'g0', 'g1', 'g2'])
    reference, resumed = tmp_path / 'a', tmp_path / 'b'

    def services_of(root, script):
        services = learning.build(root, script, mode='single')
        services.manifest['resume_replay'] = 'on'
        return services
    script_a = TwinFixes(good)
    state = chain.run(reference, 'G', services=services_of(reference, script_a), sleep=lambda s: None)
    assert state['complete'], state['paused']
    rows = learning.read(reference, 's1', 'programs', 'proposals.json')
    assert [(row['status'], row['slot']) for row in rows] == [('dropped_screen', None), ('passed_after_fix', 1)]
    assert rows[0]['fix']['reason'] == 'no_reply' and rows[1]['procedure']['id'] == 'p-searchqa-1-2'
    writer = calls_file(reference, 's1/programs', 'writer-program_writer')
    fixes = [send for send in writer if json.loads(send['user']).get('request') == 'fix']
    assert len({send['request_sha256'] for send in fixes}) == 1  # one request, two occurrences
    assert [(send['occurrence'], send['receipt']['ok']) for send in fixes] == [(1, False), (2, True)]
    original, hit = chain._Run.record, []

    def record(self, unit_, name_, compute):
        if (unit_, name_) == ('s1/programs', 'proposals.json') and not hit:
            compute()            # the proposal and both fixes are made and saved in the unit's calls file ...
            hit.append(unit_)
            raise Kill()         # ... and the process dies before proposals.json is written
        return original(self, unit_, name_, compute)
    monkeypatch.setattr(chain._Run, 'record', record)
    script_b = TwinFixes(good)
    services = services_of(resumed, script_b)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit and not (resumed / 'G' / 's1' / 'programs' / 'proposals.json').exists()
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert learning.read(resumed, 's1', 'programs', 'proposals.json') == rows
    assert_same(every_record(resumed), every_record(reference))
    assert Counter(script_b.calls) == Counter(script_a.calls) and script_b.fixes == script_a.fixes == 2
    assert ledger_of(resumed) == ledger_of(reference)


class TwinTimeouts(TwinFixes):
    """``TwinFixes`` whose first TWO fix sends time out (both identical fix requests of the first attempt); every
    later one returns the screened program."""

    def program_writer(self, system, user):
        if json.loads(user).get('request') == 'fix':
            with self.lock:
                self.fixes += 1
                early = self.fixes <= 2
            return dict(learning.INFRA_FAILURE) if early else smoke.program_reply([(learning.ENTRY, self.good)])
        return super().program_writer(system, user)


def kill_before_proposals(monkeypatch):
    """The process dies after the proposals unit made (and saved) every call and before ``proposals.json``."""
    original, hit = chain._Run.record, []

    def record(self, unit_, name_, compute):
        if (unit_, name_) == ('s1/programs', 'proposals.json') and not hit:
            compute()
            hit.append(unit_)
            raise Kill()
        return original(self, unit_, name_, compute)
    monkeypatch.setattr(chain._Run, 'record', record)
    return hit


@pytest.mark.parametrize('mode', ['off', 'on'])
def test_under_repair_the_role_call_replay_stays_cb80dcc_s_unless_the_resume_replay_is_on(tmp_path, monkeypatch,
                                                                                         mode):
    """Codex's second look at the replay, point 2: the program learning 'repair' (P1's role-call replay), two
    identical proposals that fail the screen, BOTH fixes time out, the process dies before proposals.json; the
    resumed fixes are delivered. 'off': exactly cb80dcc's replay -- unnumbered records, delivered receipts first: no
    delivered receipt follows the two timeouts, so both fixes are sent again and both proposals pass after their fix
    (5 sends of the unit, 2 repaired candidates). 'on': the occurrence rule -- fix 1's timeout was gone past (fix 2
    followed it), it is replayed and proposal 1 dropped; fix 2's ends the file and is sent again (4 sends, 1
    candidate); every record numbered."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    root, script = tmp_path / 'b', TwinTimeouts(learning.program('v0', note=['l0', 'g0', 'g1', 'g2']))
    services = learning.build(root, script)  # 'repair'
    if mode == 'on':
        services.manifest['resume_replay'] = 'on'
    hit = kill_before_proposals(monkeypatch)
    with pytest.raises(Kill):
        chain.run(root, 'G', services=services, sleep=lambda s: None)
    assert hit and [send['receipt']['ok'] for send in calls_file(root, 's1/programs', 'writer-program_writer')] == [
        True, False, False]
    recovery(root)
    state = chain.run(root, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    rows = [(row['status'], row['slot']) for row in learning.read(root, 's1', 'programs', 'proposals.json')]
    writer = calls_file(root, 's1/programs', 'writer-program_writer')
    sends = Counter(script.calls)[('program_writer', 's1/programs')]
    if mode == 'off':
        assert (sends, rows) == (5, [('passed_after_fix', 1), ('passed_after_fix', 2)])
        assert all('occurrence' not in send for send in writer)
    else:
        assert (sends, rows) == (4, [('dropped_screen', None), ('passed_after_fix', 1)])
        assert [send['occurrence'] for send in writer] == [1, 1, 2, 2]


def unnumber(path, *, keep_first=False):
    """Rewrite a calls file as one written before sends were numbered: no record names its occurrence -- or, with
    ``keep_first``, a mixed file: its first record unnumbered, then a numbered copy of it as occurrence 2."""
    rows = json.loads(path.read_text())
    bare = [{key: value for key, value in row.items() if key != 'occurrence'} for row in rows]
    units.write_json(path, bare[:1] + [{**rows[0], 'occurrence': 2}] if keep_first else bare)
    return json.loads(path.read_text())


@pytest.mark.parametrize('case', ['unnumbered', 'mixed'])
def test_under_on_a_solver_calls_file_without_occurrences_is_refused_and_the_unit_pauses(tmp_path, monkeypatch, case):
    """Codex's second look at the replay, point 3: under 'on' a cell's calls file whose sends do not all name their
    occurrence (written before sends were numbered, or mixing numbered and unnumbered records) is never guessed at:
    the resumed cell sends nothing, its unit stops with 'replay_refused' (stop.json names the refusal), the chain
    pauses there for the owner, and the file stays as it was."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = learning.Engineer(learning.program('v0', note=['l0', 'g0', 'g1', 'g2']))
    services = learning.build(tmp_path, script)
    services.manifest['resume_replay'] = 'on'
    hit = kill_after_solve(services, 's1/noise')
    with pytest.raises(Kill):
        chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    (item_id, tag), = hit
    path = tmp_path / 'G' / 's1' / 'noise' / 'calls' / (tag + '.json')
    saved = unnumber(path, keep_first=case == 'mixed')
    before = Counter(script.calls)
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert (state['paused']['reason'], state['paused']['unit']) == ('replay_refused', 's1/noise')
    stop = json.loads((tmp_path / 'G' / 's1' / 'noise' / 'stop.json').read_text())
    assert (stop['reason'], stop['failure'], stop['cell']) == ('replay_refused', 'ReplayRefused', tag)
    assert Counter(script.calls)[('solver', 's1/noise')] == before[('solver', 's1/noise')]  # nothing sent
    assert json.loads(path.read_text()) == saved and not (path.parent.parent / 'cells' / (tag + '.json')).exists()


def test_under_on_a_role_calls_file_without_occurrences_is_refused_and_the_unit_pauses(tmp_path, monkeypatch):
    """Point 3 for a role call ('single' with 'on'): the engineer's calls file of s1/programs rewritten without
    occurrences after a kill before proposals.json; the resume pauses the unit with 'replay_refused' before the
    proposal is sent again, and the file stays as it was."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = learning.Engineer(learning.program('v0', note=['l0', 'g0', 'g1', 'g2']))
    services = learning.build(tmp_path, script, mode='single')
    services.manifest['resume_replay'] = 'on'
    hit = kill_before_proposals(monkeypatch)
    with pytest.raises(Kill):
        chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert hit
    path = tmp_path / 'G' / 's1' / 'programs' / 'calls' / 'writer-program_writer.json'
    saved, before = unnumber(path), Counter(script.calls)
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    paused = state['paused']
    assert (paused['reason'], paused['unit']) == ('replay_refused', 's1/programs')
    assert paused['detail'] == 'ReplayRefused: sends without an occurrence in writer-program_writer.json'
    assert Counter(script.calls) == before and json.loads(path.read_text()) == saved


@pytest.mark.parametrize('mode', ['off', 'on'])
@pytest.mark.parametrize('unit', ['s1/noise', 's1/card-r1'])
def test_a_call_killed_after_its_receipt_was_saved_and_before_its_charge_was_settled(tmp_path, monkeypatch, unit,
                                                                                   mode):
    """Codex's review of 9c6d1f7, finding 2: the process dies after a call's receipt reached its calls file and before
    the ledger settled its reservation -- the first solver cell of s1/noise, or the card writer of s1/card-r1 (P1's
    harness). 'on': the resumed ledger settles that pending call from its saved receipt, once, before the ordinary
    recovery: no recovered entry, no missing usage, no re-run counted, nothing sent again -- the ledger's sends,
    charged, reported, missing_usage, recovered and by_unit and every record equal an uninterrupted run's. 'off'
    (typed-v2): the reservation is recovered (one recovered entry, one more missing usage)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    v0 = learning.program('v0', note=['l0', 'g0', 'g1', 'g2'])
    reference, resumed = tmp_path / 'a', tmp_path / 'b'

    def services_of(root, script):
        services = learning.build(root, script)
        if mode == 'on':
            services.manifest['resume_replay'] = 'on'
        return services
    script_a = learning.Engineer(v0)
    state = chain.run(reference, 'G', services=services_of(reference, script_a), sleep=lambda s: None)
    assert state['complete'], state['paused']
    original, hit = units.Ledger.settle, []

    def settle(self, key, receipt, **kwargs):
        entry = self.state['pending'].get(key) or {}
        if entry.get('unit') == unit and not hit:
            hit.append((key, entry['cell']))
            raise Kill()  # the receipt is in the calls file; the ledger still holds the reservation
        return original(self, key, receipt, **kwargs)
    monkeypatch.setattr(units.Ledger, 'settle', settle)
    script_b = learning.Engineer(v0)
    services = services_of(resumed, script_b)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    (key, cell), = hit
    assert key in json.loads((resumed / 'G' / 'ledger.json').read_text())['pending']
    saved = [send for path in Path(resumed, 'G', *unit.split('/'), 'calls').glob('*.json')
             for send in json.loads(path.read_text()) if send['logical_call'] == key]
    assert [send['receipt']['ok'] for send in saved] == [True]
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    ledger_a, ledger_b = ledger_of(reference), ledger_of(resumed)
    if mode == 'on':
        assert ledger_b == ledger_a and ledger_b['recovered'] == []
        assert_same(every_record(resumed), every_record(reference))
        assert Counter(script_b.calls) == Counter(script_a.calls)
    else:
        assert [(row['unit'], row['cell']) for row in ledger_b['recovered']] == [(unit, cell)]
        assert ledger_b['missing_usage'] == ledger_a['missing_usage'] + 1


# ---- (2) diagnose and (3) items-check under the item stage --------------------------------------------------------
def stage_services(root, script, *, mode, rule=stage.strict, solve=None):
    services = stage.build(root, script, rule=rule)
    if solve is not None:
        services.solve_fn = solve
    if mode == 'on':
        services.manifest['resume_replay'] = 'on'
    return services


def test_a_diagnose_cell_killed_after_its_reply_was_saved_resumes_without_a_send(tmp_path, monkeypatch):
    """P2b's SearchQA scenario under 'planned' with the replay 'on': the process dies right after the first diagnose
    cell (B on a learn item) was solved; the resumed step answers it from its calls file -- zero new sends, the ledger
    as an uninterrupted run's, every record (diagnose.json, the plan, the items, J) the same."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = stage.Script()
    state = chain.run(reference, 'G', services=stage_services(reference, script_a, mode='on'), sleep=lambda s: None)
    assert state['complete'], state['paused']
    script_b = stage.Script()
    services = stage_services(resumed, script_b, mode='on')
    hit = kill_after_solve(services, 's1/diagnose')
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit and not (resumed / 'G' / 's1' / 'diagnose' / 'diagnose.json').exists()
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert_same(every_record(resumed), every_record(reference))
    assert Counter(script_b.calls) == Counter(script_a.calls) and len(script_b.requests) == len(script_a.requests)
    assert ledger_of(resumed) == ledger_of(reference)


class Resent(stage.Script):
    """P2b's scripted clients with a model that answers a RESENT request of the items check differently: the second
    send of one request within s1/items-check gets the reply 'FLIPPED' (``flipping`` reads it as the opposite
    verdict), as a sampled model may answer a resent request otherwise."""

    def __init__(self):
        super().__init__()
        self.seen = Counter()

    def send(self, purpose, system, user, *, model, unit=None):
        found = super().send(purpose, system, user, model=model, unit=unit)
        if purpose == 'solver' and unit == 's1/items-check':
            self.seen[units.sha256_text(system + '\x00' + user)] += 1
            if self.seen[units.sha256_text(system + '\x00' + user)] > 1:
                return {**found, 'response': 'FLIPPED'}
        return found


def flipping(rule):
    """P2b's fake solve whose verdict is the opposite of ``rule`` when the reply is 'FLIPPED'."""
    solve = stage.solve(rule)

    def run(bench, item, mounted, *, call, **rest):
        seen = _Seen(call)
        row = solve(bench, item, mounted, call=seen, **rest)
        if seen.receipts and seen.receipts[0].get('response') == 'FLIPPED' and row['correct'] is not None:
            row = {**row, 'correct': not row['correct'], 'token': 'fail' if row['correct'] else 'pass'}
        return row
    return run


@pytest.mark.parametrize('mode', ['off', 'on'])
def test_an_items_check_cell_resent_after_a_kill_would_flip_the_check_and_is_replayed_under_on(tmp_path, monkeypatch,
                                                                                             mode):
    """Codex's case (review of P2b): B is wrong on the six attack items and right on the first calibration item only
    (1 of 3: 0 % + 5 points <= 33.3 %, the check holds). The process dies right after that calibration item's cell of
    s1/items-check was solved; the model would answer the resent request otherwise ('FLIPPED': wrong). 'off'
    (typed-v2): the resumed check sends it again and reads it wrong -- 0 of 3, the check no longer holds and the step
    goes on to a replacement round: the items, and so J, are not those of the uninterrupted run. 'on': the saved reply
    is replayed -- zero new sends, the check holds, every record and the ledger as an uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    calibration = stage.round_1_calibration()
    first = stage.sq_id(calibration[0])
    assert stage.strict('searchqa', {'task_id': first}, {}) == 'pass'

    def rule(bench, item, mounted):
        if bench == 'searchqa' and stage.index(item['task_id']) in calibration[1:]:
            return 'fail'
        return stage.strict(bench, item, mounted)
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = Resent()
    state = chain.run(reference, 'G', services=stage_services(reference, script_a, mode=mode, rule=rule,
                                                               solve=flipping(rule)), sleep=lambda s: None)
    assert state['complete'], state['paused']
    check_a = stage.read(reference, 's1', 'items-check', 'check.json')
    assert (check_a['holds'], check_a['attack']['pass'], check_a['calibration']['pass']) == (True, 0, 1)
    script_b = Resent()
    services = stage_services(resumed, script_b, mode=mode, rule=rule, solve=flipping(rule))
    hit = kill_after_solve(services, 's1/items-check', item_id=first)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit and not (resumed / 'G' / 's1' / 'items-check' / 'check.json').exists()
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    check_b = stage.read(resumed, 's1', 'items-check', 'check.json')
    if mode == 'off':
        assert (check_b['holds'], check_b['calibration']['pass']) == (False, 0)  # the resent cell flipped the check
        assert Counter(script_b.calls)[('solver', 's1/items-check')] == Counter(script_a.calls)[
            ('solver', 's1/items-check')] + 1
        assert (resumed / 'G' / 's1' / 'items-plan-2').exists()  # a replacement round the reference never made
        assert not (reference / 'G' / 's1' / 'items-plan-2').exists()
        return
    assert state['complete'], state['paused']
    assert check_b == check_a
    assert_same(every_record(resumed), every_record(reference))
    assert Counter(script_b.calls) == Counter(script_a.calls) and ledger_of(resumed) == ledger_of(reference)


# ---- (4) a read cell in run mode, under the consent ---------------------------------------------------------------
@pytest.mark.parametrize('mode', ['off', 'on'])
def test_a_read_cell_killed_after_its_reply_was_saved_resumes_without_a_send_under_on(tmp_path, monkeypatch,
                                                                                     qualified, mode):  # noqa: F811
    """P3r's run mode (interleaved, full, base historical, the anchor C alone, the consent of C..S5; SearchQA only):
    the process dies right after the first cell of the sealed read unit test-read-S1-searchqa was solved (its reply is
    in the unit's calls file; the cell, the unit's done record and its mirror are not written). 'on': the resumed
    read opens its panel again under the consent and answers the cell from its calls file -- zero new sends, the ledger
    as an uninterrupted run's, every file of the chain the same. 'off' (typed-v2): the cell is read again -- one more
    send; the fake's reply is the same, so the files are too."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    unit = 'test-read-S1-searchqa'

    def services_of(root, script, seen):
        manifest = reading.c_manifest(**({'resume_replay': 'on'} if mode == 'on' else {}))
        return reading.run_services(root, 'G', manifest, seen=seen, script=script, order=('searchqa',))
    reference, resumed, seen_a, seen_b = tmp_path / 'a', tmp_path / 'b', [], []
    for root in (reference, resumed):
        reading.write_consent(root)
    script_a = reading.Capture()
    state = chain.run(reference, 'G', services=services_of(reference, script_a, seen_a), sleep=lambda s: None)
    assert state['complete'], state['paused']
    script_b = reading.Capture()
    services = services_of(resumed, script_b, seen_b)
    hit = kill_after_solve(services, unit)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    (item_id, tag), = hit
    where = resumed / 'G' / unit
    assert not (where / 'cells' / (tag + '.json')).exists() and not (where / 'done.json').exists()
    assert json.loads((where / 'calls' / (tag + '.json')).read_text())[0]['receipt']['ok'] is True
    reading.recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert reading.snapshot(resumed / 'G') == reading.snapshot(reference / 'G')
    assert [u for _, u in seen_b] == [u for _, u in seen_a] + ['G/' + unit]  # the panel opened once more on resume
    extra = 0 if mode == 'on' else 1
    assert Counter(script_b.calls) == Counter(script_a.calls) + Counter({('solver', unit): extra})
    ledger_a, ledger_b = ledger_of(reference), ledger_of(resumed)
    assert ledger_b['sends'] == ledger_a['sends'] + extra
    if mode == 'on':
        assert ledger_b == ledger_a


@pytest.mark.parametrize('mode', ['off', 'on'])
def test_a_read_call_killed_before_its_charge_was_settled_is_settled_from_its_sealed_calls_file(tmp_path, monkeypatch,
                                                                                               qualified,  # noqa: F811
                                                                                               mode):
    """Finding 2 of the review of 9c6d1f7 for a read cell (P3r's run mode as above): the process dies after the first
    read call of test-read-S1-searchqa returned its receipt to the unit's (sealed) calls file and before the ledger
    settled it. 'on': the resumed ledger finds the receipt in the sealed unit and settles it once -- the ledger and
    every file of the chain as an uninterrupted run's, nothing sent again. 'off' (typed-v2): recovered, as before."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    unit = 'test-read-S1-searchqa'

    def services_of(root, script, seen):
        manifest = reading.c_manifest(**({'resume_replay': 'on'} if mode == 'on' else {}))
        return reading.run_services(root, 'G', manifest, seen=seen, script=script, order=('searchqa',))
    reference, resumed, seen_a, seen_b = tmp_path / 'a', tmp_path / 'b', [], []
    for root in (reference, resumed):
        reading.write_consent(root)
    script_a = reading.Capture()
    state = chain.run(reference, 'G', services=services_of(reference, script_a, seen_a), sleep=lambda s: None)
    assert state['complete'], state['paused']
    original, hit = units.Ledger.settle, []

    def settle(self, key, receipt, **kwargs):
        entry = self.state['pending'].get(key) or {}
        if entry.get('unit') == unit and not hit:
            hit.append((key, entry['cell']))
            raise Kill()
        return original(self, key, receipt, **kwargs)
    monkeypatch.setattr(units.Ledger, 'settle', settle)
    script_b = reading.Capture()
    services = services_of(resumed, script_b, seen_b)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    (key, cell), = hit
    assert key in json.loads((resumed / 'G' / 'ledger.json').read_text())['pending']
    reading.recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    ledger_a, ledger_b = ledger_of(reference), ledger_of(resumed)
    if mode == 'on':
        assert ledger_b == ledger_a and ledger_b['recovered'] == []
        assert reading.snapshot(resumed / 'G') == reading.snapshot(reference / 'G')
        assert Counter(script_b.calls) == Counter(script_a.calls)
    else:
        assert [(row['unit'], row['cell']) for row in ledger_b['recovered']] == [(unit, cell)]


@pytest.mark.parametrize('revoked', ['removed', 'other_events'])
def test_a_resumed_ledger_opens_no_sealed_read_unit_whose_consent_was_revoked(tmp_path, monkeypatch,
                                                                             qualified, revoked):  # noqa: F811
    """Codex's second look at the replay, point 1: the process dies inside the sealed read unit test-read-S1-searchqa
    after a read call's receipt reached the unit's calls file and before the ledger settled it; then the owner
    revokes the consent (the file removed, or replaced by one naming other events). The resumed ledger runs the read's
    own checks (``reads.unit_gate``) before it would open the unit: they fail, so nothing of the sealed unit is opened
    (no read of any file under a test-read- directory during the whole resume), the pending call goes to the ordinary
    recovery, and the chain pauses exactly as the same resume without any reconciliation does (same pause, same
    ledger)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    unit, original, read_json = 'test-read-S1-searchqa', units.Ledger.settle, units.read_json
    armed, opened, found = {'on': False}, [], {}

    def settle(self, key, receipt, **kwargs):
        entry = self.state['pending'].get(key) or {}
        if armed['on'] and entry.get('unit') == unit:
            armed['on'] = False
            raise Kill()  # the receipt is in the sealed unit's calls file; the reservation is not settled
        return original(self, key, receipt, **kwargs)

    def watching(path, *, allow_sealed=False):
        if 'test-read-' in str(path):
            opened.append(Path(path).name)
        return read_json(path, allow_sealed=allow_sealed)
    monkeypatch.setattr(units.Ledger, 'settle', settle)
    for name in ('reconciled', 'plain'):
        root = tmp_path / name
        reading.write_consent(root)
        services = reading.run_services(root, 'G', reading.c_manifest(resume_replay='on'), seen=[],
                                        script=reading.Capture(), order=('searchqa',))
        armed['on'] = True
        with pytest.raises(Kill):
            chain.run(root, 'G', services=services, sleep=lambda s: None)
        assert not armed['on']
        pending = json.loads((root / 'G' / 'ledger.json').read_text())['pending']
        assert [entry['unit'] for entry in pending.values()] == [unit]
        if revoked == 'removed':
            (root / 'shared' / 'consent.json').unlink()
        else:
            reading.write_consent(root, arms=list(reads_module.READ_ARMS))  # names C0 too: not this run's events
        reading.recovery(root)
        del opened[:]
        with monkeypatch.context() as patch:
            patch.setattr(units, 'read_json', watching)
            if name == 'plain':
                patch.setattr(chain, '_durable_receipts', lambda *args: None)  # no reconciliation at all
            state = chain.run(root, 'G', services=services, resume=True, sleep=lambda s: None)
        found[name] = (state['paused'], ledger_of(root), list(opened))
    (paused, ledger, opened_reconciled), (paused_plain, ledger_plain, opened_plain) = (found['reconciled'],
                                                                                       found['plain'])
    assert opened_reconciled == [] == opened_plain  # nothing sealed opened
    assert paused is not None and paused == paused_plain
    assert strip(ledger) == strip(ledger_plain)  # the recovery stamps ('at') of the two resumes left out
    assert [row['unit'] for row in ledger['recovered']] == [unit]
