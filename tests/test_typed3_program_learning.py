"""typed-v3 program learning (docs/handoff/typed-v3/CHAIN-DECISIONS.md T1, T8, T9; brief P1; Codex review of P1,
findings F2 to F6): the version switch's sealed options, the zero-call probe with the incumbents mounted, the free
repair rounds, the one paid feedback round, the archive candidate with its forced background and post-archive learn
outcomes, the replay of completed role receipts, and resume -- on fakes only (no network, no Docker, no /data,
nothing paid).

The chain runs through the REAL ``chain.run``, ``mount`` (package candidates included), ``writers`` (prompts, reader,
static screen, ``repair_program``) and ``engineer_prompt``; the solver shell is a scripted fake (``shell_solve``) that
reads what a program does from marker comments in its source (``# note: l0 l1`` -- a note on those items, ``# silent:``
-- applies without a note, ``# timeout:`` -- a timeout fault, ``# wrong:`` -- a note that makes the solver wrong,
``# size: n`` -- notes of n characters; an item is named by its suffix or in full), or, for an archived record, from
``ARCHIVE_BEHAVIOUR`` / ``ARCHIVE_SIZE``. It assembles the shown notes with the REAL ``notes.assemble`` (package
order, the declared cap of each record -- over it a fault -- and the bench's total cap -- over it a note is skipped
whole) and renders them into the request as the shell does (``solver._user``; ALFWorld's first-step view with its
notes key), so a probe's ``note_chars`` is what ``chars`` computes from the same text. One test runs the probe through
the REAL solver shell (``mount.solve``) with an in-process deterministic sandbox worker. Expected values are worked out
by hand from the markers in each test: without a program the solver is right on the learn items l2 and l3 only
(``BASE_PASS``) and wrong on every gate item; a shown note makes it right, a ``wrong`` note wrong.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_typed
from skillopt.execskill import notes as notes_, profiles, solver, typed as typed_
from skillopt.execskill.package import Procedure
from skillopt.execskill.sandbox import worker_v222
from skillopt.execskill.typed import archives, chain, engineer_prompt, library as library_, mount, prepare, smoke, units, writers
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import Script as SelectorScript
from tests.test_typed_chain import FakeReads, recovery
from tests.test_typed_mount import program_record, qa_item, typed_world
from tests.test_typed_schedule import inputs  # noqa: F401 -- prepare's fixture (pools, machinery record, typed tree)

NEUTRAL = Path('/tmp/typed3-neutral').resolve()  # resolved: route B's safe_path refuses a symlink in any parent
ENTRY = {'kind': 'new', 'description': 'Computes a note from the task text.', 'hooks': ['applies', 'before_call'],
         'header': '', 'max_note_chars': 600}
WIDE = {**ENTRY, 'max_note_chars': 4000}   # an entry whose notes may use the whole total cap
MARKER = re.compile(r'^# (note|silent|timeout|wrong|size): (.*)$', re.M)
BASE_PASS = ('l2', 'l3')   # items the solver gets right without any program (the learn items l2 and l3 of every bench)
NOW = '2026-11-15T00:00:00'


class Kill(BaseException):
    """A process death in the middle of a step: no ``Exception``, so ``chain.run`` records no pause and nothing after
    it runs (the test then resumes with the owner's recovery, as after a real kill)."""


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='pl-', dir=NEUTRAL))
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


# ---- scripted programs ------------------------------------------------------------------------------------------------
def program(tag, size=None, **marks):
    """A program text that passes the real static screen; its behaviour is in its marker comments."""
    lines = ['# version: %s' % tag]
    for kind in ('note', 'silent', 'timeout', 'wrong'):
        if marks.get(kind):
            lines.append('# %s: %s' % (kind, ' '.join(marks[kind])))
    if size is not None:
        lines.append('# size: %d' % size)
    return '\n'.join(lines) + '\n\n\ndef before_call(view, state):\n    return {"warnings": ["Read the whole task."]}\n'


def short(item_id):
    return item_id.rsplit('-', 1)[-1]


ARCHIVE_BEHAVIOUR = {}   # {procedure id: {item id, item suffix or '*': kind}} for archived records; set by a test
ARCHIVE_SIZE = {}        # {procedure id: note characters} for archived records; set by a test


def behaviour(record, item_id):
    """What a program does on an item: 'note', 'silent', 'timeout', 'wrong' or None (it does not apply)."""
    if record['id'] in ARCHIVE_BEHAVIOUR:
        table = ARCHIVE_BEHAVIOUR[record['id']]
        return table.get(item_id, table.get(short(item_id), table.get('*')))
    for kind, items in MARKER.findall(record['source']):
        if kind != 'size' and (item_id in items.split() or short(item_id) in items.split()):
            return kind
    return None


def note_size(record):
    if record['id'] in ARCHIVE_SIZE:
        return ARCHIVE_SIZE[record['id']]
    sizes = [int(value) for kind, value in MARKER.findall(record.get('source') or '') if kind == 'size']
    return sizes[0] if sizes else None


def note_text(procedure_id, item_id, size=None):
    """The note a scripted program writes on an item (``size`` characters when given)."""
    text = '[%s] computed for %s' % (procedure_id, item_id)
    return text if size is None else (text + ' ' + '.' * size)[:size]


def item_of(bench, item_id):
    public, private = smoke.SYNTHETIC_ITEMS[bench](item_id)
    return {'benchmark': bench, 'task_id': item_id, 'public': public, 'private': private}


def fake_user(bench, item, text=''):
    """The first request's user text as the shell renders it with the notes ``text`` (``solver._user``: the
    registered ZebraLogic template with its notes appendix, the QA / sheet view JSON with its notes key; ALFWorld's
    first-step view with the notes key)."""
    if bench == 'alfworld':
        request = json.loads(smoke.fake_request(bench, item, {}))
        if text:
            request[solver.NOTES_KEY] = text
        return json.dumps(request, ensure_ascii=False)
    return solver._user(bench, smoke.synthetic_view(bench, item), text)


def chars(text, bench, item_id):
    """The characters the notes ``text`` add to an item's first request."""
    item = item_of(bench, item_id)
    return len(fake_user(bench, item, text)) - len(fake_user(bench, item, ''))


def shown(bench, item_id, records):
    """The notes text the scripted shell shows on an item for ``records`` ([(procedure id, size or None, declared
    cap)], package order): assembled by the real ``notes.assemble``."""
    entries = [(pid + '/before_call', note_text(pid, item_id, size), cap) for pid, size, cap in records]
    return notes_.assemble(entries, bench=bench)[0]


def added(bench, item_id, before, after):
    """A probe's ``note_chars`` worked out by hand: the characters the candidate side's notes (``after``) add to the
    item's first request over the incumbent side's (``before``)."""
    return chars(shown(bench, item_id, after), bench, item_id) - chars(shown(bench, item_id, before), bench, item_id)


def shell_solve(bench, item, mounted, *, call, runtime, worker_factory=None, native=None, nominal_tokens=None, unit,
                tag, scorer_root, mode=None, step=None, episodes=None):
    """``mount.solve``'s cell record from a scripted shell: per enabled record (package order) its behaviour on the
    item; the notes are assembled by the real ``notes.assemble`` (a note over its record's declared cap is a fault,
    one over the bench's total cap is skipped whole) and rendered into the request's user text (``fake_user``); a
    timeout is a fault of the record and no note."""
    fired, faults, entries, wrong = [], [], [], set()
    for record in mounted.get('enabled') or []:
        kind = behaviour(record, item['task_id'])
        if kind is None:
            continue
        fired.append(record['id'])
        if kind == 'timeout':
            faults.append({'procedure': record['id'], 'hook': 'before_call', 'kind': 'timeout', 'exc_type': None,
                           'message': 'wall timeout of 5 s'})
        elif kind in ('note', 'wrong'):
            entries.append((record['id'] + '/before_call', note_text(record['id'], item['task_id'], note_size(record)),
                            record.get('max_note_chars') or 0))
            if kind == 'wrong':
                wrong.add(record['id'] + '/before_call')
    text, skipped = notes_.assemble(entries, bench=bench)
    gone = {row['procedure'] for row in skipped}
    for row in skipped:
        if row['reason'] == 'over_declared_cap':
            faults.append({'procedure': row['procedure'].split('/')[0], 'hook': 'notes', 'kind': 'note_over_declared_cap',
                           'exc_type': None, 'message': row['chars']})
    shown = [label for label, note, _ in entries if note and label not in gone]
    found = call(mounted.get('system_card') or '', fake_user(bench, item, text))
    if not found.get('ok'):
        token = 'unknown_' + str(found.get('error_type'))
    elif wrong & set(shown):
        token = 'fail'
    elif shown:
        token = 'pass'
    else:
        token = 'pass' if short(item['task_id']) in BASE_PASS else 'fail'
    reply = found.get('response')
    return {'bench': bench, 'item_id': item['task_id'], 'arm': mounted.get('arm'),
            'mount': {k: v for k, v in mounted.items() if k not in ('enabled', 'card_text', 'system_card')},
            'public_hash': library_.canonical_sha256(item['public']), 'prediction_status': 'available' if found.get('ok')
            else 'unknown', 'output_excerpt': (reply or '')[:2000], 'reply': reply,
            'correct': None if token.startswith('unknown') else token == 'pass', 'token': token,
            'official': {'status': token, 'reason': 'scripted'}, 'format': {}, 'flags': [], 'fired': fired,
            'faults': faults, 'tokens': call.tokens(), 'sends': call.sends,
            'request_sha256': [s['request_sha256'] for s in call.sends], 'configuration_error': False,
            'infrastructure_unknown': call.infrastructure_unknown(), 'failure': None}


class Engineer(smoke.Script):
    """The scripted clients with a program writer that answers by request: a proposal (and a fix, and a format retry)
    gets ``propose`` (a program text, or {bench: text}); with ``prose_first`` the first proposal of each bench gets
    prose instead (no JSON: the format retry follows); a repair of the program text ``s`` gets ``revisions[s]`` (the
    same text when absent, so the revision is 'unchanged'). ``entry``: the entry of every reply. ``broken``:
    {(purpose, unit)} whose first send raises (an interruption, before the send reaches the script); every request
    is kept, the interrupted ones included."""

    def __init__(self, propose, revisions=(), *, broken=(), scripted=None, entry=ENTRY, prose_first=False):
        self.propose, self.revisions, self.entry = propose, dict(revisions), entry
        self.broken, self.requests, self.prose = set(broken), [], set() if prose_first else None
        replies = {'program_writer': self.program_writer, 'card_writer': smoke.DEFAULT_CARD}
        super().__init__({**(scripted or {}), 'replies': {**replies, **((scripted or {}).get('replies') or {})}})

    def program_writer(self, system, user):
        request = json.loads(user)  # every program-writer request is JSON naming its kind and bench
        kind, bench = request.get('request'), request.get('bench')
        if kind == 'repair':
            return smoke.program_reply([(self.entry, self.revisions.get(request['source'], request['source']))])
        if self.prose is not None and kind == 'propose' and bench not in self.prose:
            self.prose.add(bench)
            return smoke.UNREADABLE_PROPOSAL
        source = self.propose.get(bench) if isinstance(self.propose, dict) else self.propose
        return smoke.program_reply([(self.entry, source)])

    def send(self, purpose, system, user, *, model, unit=None):
        with self.lock:
            self.requests.append((purpose, unit, system, user))
            if (purpose, unit) in self.broken:
                self.broken.discard((purpose, unit))
                raise RuntimeError('connection lost')
        return super().send(purpose, system, user, model=model, unit=unit)

    def users(self, purpose, unit):
        return [json.loads(user) for p, u, _, user in self.requests if p == purpose and u == unit]


def build(root, script, *, bench='searchqa', learn=5, gate=3, limits=None, archive=None, mode='repair', order=None):
    """Fake services through the real mount / writers and the scripted shell, under the sealed program learning
    ``mode`` (and the sealed ``archive`` value); one card round (the card never gains: the scripted shell ignores
    cards, so a step's programs are judged against F of ``s<k>/outcomes``). One bench, or the benches of ``order``
    (each with ``learn`` and ``gate`` items)."""
    order = tuple(order or (bench,))
    manifest = {**smoke.synthetic_manifest(sizes={b: {'learn': learn, 'gate': gate, 'panel': 2} for b in order}),
                'program_learning': mode, **({'archive': archive} if archive is not None else {})}
    modules = SimpleNamespace(mount=mount, writers=writers, reads=FakeReads())
    services = smoke.fake_services(root, 'G', manifest, scripted=script, modules=modules)
    services.order, services.solve_fn = order, shell_solve
    services.limits = {**chain.DEFAULT_LIMITS, 'card_rounds': 1, **(limits or {})}
    return services


def run(root, script, **kw):
    services = build(root, script, **kw)
    return chain.run(root, 'G', services=services, sleep=lambda s: None), services


def read(root, *parts):
    return json.loads(Path(root, 'G', *parts).read_text())


# ---- shared expectations ------------------------------------------------------------------------------------------------
def requests_of(script):
    """(unit, request kind) of every program-writer send in order (an interrupted send included)."""
    return [(unit, json.loads(user).get('request')) for purpose, unit, _, user in script.requests
            if purpose == 'program_writer']


def program_dirs(root, k=1):
    return sorted(p.name for p in Path(root, 'G', 's%d' % k).iterdir() if p.name.startswith('program'))


def summary(unit, items, fired, noted, faults=None, routed=None, unrecorded=0):
    """A probe summary as the records carry it, worked out from the markers by hand (every item routed unless
    ``routed``)."""
    faults = faults or {}
    return {'unit': unit, 'items': items, 'routed': items if routed is None else routed, 'fired': fired, 'noted': noted,
            'faults': faults, 'unsent': 0, 'failed': 0, 'selection_unrecorded': unrecorded,
            'fault_count': sum(faults.values())}


def view_text(bench, item_id):
    """The public text of a synthetic QA learn item as the writers see it: the question, then the context."""
    public, _ = smoke.SYNTHETIC_ITEMS[bench](item_id)
    return public['question'] + '\n' + public['context']


def tasks(bench, *names):
    return [{'task_id': '%s-%s' % (bench, name), 'view': view_text(bench, '%s-%s' % (bench, name))} for name in names]


def type_of(root, k=1):
    return read(root, 's%d' % k, 'decisions.json')['typing']['type']


def programs_of(root, k=1):
    return library_.Library.load(Path(root, 'G', 's%d' % k, 'library.json')).programs(type_of(root, k))


def gate_cells(root, unit):
    return [json.loads(p.read_text()) for p in sorted(Path(root, 'G', *unit.split('/'), 'cells').glob('*.json'))]


# ---- T1: the two sealed options ---------------------------------------------------------------------------------------
def test_the_version_and_the_option_defaults():
    assert (typed_.VERSION, typed_.CONFIGURATION) == ('typed-v3', 'typed-v3')
    assert typed_.EVIDENCE == {'run': 'typed_v3_real_run', 'smoke': 'typed_v3_smoke', 'test': 'engineering_fixture'}
    assert typed_.is_typed_v3('typed-v3') and not typed_.is_typed_v3('typed-v2')
    assert (typed_.PROGRAM_LEARNING, typed_.PROGRAM_LEARNING_DEFAULT) == (('single', 'repair'), 'single')
    assert (typed_.ARCHIVE_CHOICES, typed_.ARCHIVE_DEFAULT) == (('none', 'index'), 'none')
    assert typed_.REPAIR_LIMITS == {'program_repair_rounds': 3, 'program_paid_feedback': 1}
    # the five typed-v2 limits stay the decisions' limits; the repair limits are never read under 'single'
    assert set(chain.DEFAULT_LIMITS) == {'card_rounds', 'max_program_proposals', 'max_program_candidates',
                                         'program_smoke_items', 'gate_repeats'}
    # a typed-v2 style manifest (neither field) runs typed-v2's flow without an archive
    assert prepare.program_learning_of({}) == 'single' and prepare.archive_of({}) == {}
    sealed = archives.sealed('index')
    assert prepare.archive_of({'program_learning': 'repair', 'archive': sealed}) == sealed
    for bad in ({'program_learning': 'multi'}, {'program_learning': None}, {'archive': sealed},
                {'program_learning': 'single', 'archive': sealed}, {'program_learning': 'repair', 'archive': 'index'}):
        with pytest.raises(ValueError):
            prepare.archive_of(bad) if 'archive' in bad else prepare.program_learning_of(bad)


def test_prepare_seals_the_program_learning_and_the_archive(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    default = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', **common)
    assert (default['program_learning'], default['archive']) == ('single', {})
    made = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', program_learning='repair', archive='index',
                           **common)
    assert made['program_learning'] == 'repair' and made['archive'] == archives.sealed('index')
    assert sorted(made['archive']) == ['D', 'G'] and sorted(made['archive']['G']) == ['alfworld', 'zebralogic']
    assert made['archive']['G']['zebralogic']['package'] == 'main-v6-G-s3-p-zebralogic-3-5'
    assert made['archive']['D']['zebralogic']['package'] == 'main-v6-D-s3-p-zebralogic-3-3'
    assert [row['id'] for row in made['archive']['D']['alfworld']['procedures']] == [
        'p-alfworld-1-6', 'p-alfworld-1-14', 'p-alfworld-1-15']
    assert prepare.load_manifest(made['root']) == made
    assert prepare.program_learning_of(made) == 'repair' and prepare.archive_of(made) == made['archive']
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    for key, value in (('program_learning', 'single'), ('archive', {})):  # the hash covers both
        assert prepare.seal({**fields, key: value})['record_sha256'] != made['record_sha256']
    # an unknown value, or an archive without 'repair', is refused before anything is written
    for bad in ({'program_learning': 'multi'}, {'program_learning': None}, {'archive': 'index'},
                {'program_learning': 'repair', 'archive': 'all'}):
        new = parent / 'execskill-20261114-typed-v3-smoke'
        with pytest.raises(ValueError):
            prepare.prepare(new, **common, **bad)
        assert not new.exists()
    # load_manifest refuses a changed value (re-sealed, so only the field differs)
    root = Path(made['root'])
    other = json.loads(json.dumps(made['archive']))
    other['G']['zebralogic']['procedures'][0]['record_sha256'] = '0' * 64
    for key, value in (('program_learning', 'multi'), ('program_learning', 'single'), ('archive', other),
                       ('archive', {'G': {'searchqa': made['archive']['G']['zebralogic']}})):
        units.write_json(root / 'manifest.json', prepare.seal({**fields, key: value}))
        with pytest.raises(ValueError):
            prepare.load_manifest(root)
    # a manifest without both fields (typed-v2's shape) reads as 'single' without an archive
    units.write_json(root / 'manifest.json', prepare.seal({key: value for key, value in fields.items()
                                                           if key not in ('program_learning', 'archive')}))
    loaded = prepare.load_manifest(root)
    assert prepare.program_learning_of(loaded) == 'single' and prepare.archive_of(loaded) == {}


def test_the_cli_names_both_options_on_prepare_only(tmp_path, monkeypatch, environ, capsys):
    assert run_typed.PROGRAM_LEARNING == typed_.PROGRAM_LEARNING and run_typed.ARCHIVE_CHOICES == typed_.ARCHIVE_CHOICES
    parse = run_typed.parser().parse_args
    args = parse(['prepare', '--root', '/r', '--program-learning', 'repair', '--archive', 'index'])
    assert (args.program_learning, args.archive) == ('repair', 'index')
    args = parse(['prepare', '--root', '/r'])
    assert (args.program_learning, args.archive) == (None, None)
    for bad in (['prepare', '--root', '/r', '--program-learning', 'multi'], ['prepare', '--root', '/r', '--archive', 'all'],
                ['run', '--root', '/r', '--chain', 'G', '--program-learning', 'repair'],
                ['smoke', '--root', '/r', '--chain', 'G', '--fake', '--archive', 'index']):
        with pytest.raises(SystemExit):
            parse(bad)
    calls, adapter = [], run_typed._prepare
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(kw) or {
        'configuration': 'typed-v3', 'program_learning': kw.get('program_learning', 'single'),
        'archive': archives.sealed(kw.get('archive', 'none'))})
    root = tmp_path / 'run'
    root.mkdir()
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {}}))
    assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery),
                           '--program-learning', 'repair', '--archive', 'index']) == 0
    assert calls[-1] == {'machinery_manifest': str(machinery), 'roles_repo': typed_.ROLES_REPO,
                         'pools_root': typed_.POOLS_ROOT, 'smoke': False, 'program_learning': 'repair',
                         'archive': 'index'}
    printed = json.loads(capsys.readouterr().out)['manifest']
    assert printed['program_learning'] == 'repair' and printed['archive'] == {
        'D': {'alfworld': 'alfworld-v11-accepted', 'zebralogic': 'main-v6-D-s3-p-zebralogic-3-3'},
        'G': {'alfworld': 'alfworld-v11-accepted', 'zebralogic': 'main-v6-G-s3-p-zebralogic-3-5'}}
    # the adapter hands prepare only what the command names (the code defaults otherwise)
    seen = []
    monkeypatch.setattr(prepare, 'prepare', lambda root, **kw: seen.append(kw) or {})
    common = dict(machinery_manifest='/m.json', roles_repo='/creds', pools_root='/pools', smoke=True)
    adapter('/r', **common)
    adapter('/r', program_learning='repair', archive='index', **common)
    assert seen == [common, {**common, 'program_learning': 'repair', 'archive': 'index'}]


def test_a_state_started_under_one_program_learning_refuses_the_other(tmp_path):
    """One root never mixes two program learnings or two archives; a 'single' start writes typed-v2's state shape."""
    single = chain._open_state(tmp_path / 'a', 'G', 'smoke', False)
    assert 'program_learning' not in single and 'archive_sha256' not in single
    sealed = archives.sealed('index')
    made = chain._open_state(tmp_path / 'b', 'G', 'smoke', False, program_learning='repair', archive=sealed)
    assert made['program_learning'] == 'repair' and made['archive_sha256'] == library_.canonical_sha256(sealed)
    (tmp_path / 'b').mkdir()
    units.write_json(tmp_path / 'b' / 'state.json', made)
    reopened = chain._open_state(tmp_path / 'b', 'G', 'smoke', True, program_learning='repair', archive=sealed)
    assert reopened == made
    for kw in ({}, {'program_learning': 'repair'}, {'archive': sealed}):
        with pytest.raises(ValueError, match='another'):
            chain._open_state(tmp_path / 'b', 'G', 'smoke', True, **kw)


# ---- T8.2: the zero-call probe ------------------------------------------------------------------------------------------
def test_the_probe_sends_nothing_charges_nothing_and_counts_fired_noted_and_faults(tmp_path):
    """A proposal that notes on l0 and l1, applies silently on l2, times out on l3 and does not apply on l4: the probe
    records items 5, fired 4, noted 2, faults {timeout: 1}. It builds every first request twice through probe calls
    (F, then the candidate), under the memory lock with a worker per solve and the unit drain, and never asks for a
    solver or role client: no send, no ledger row, no calls file."""
    v0 = program('v0', note=['l0', 'l1'], silent=['l2'], timeout=['l3'])
    script = Engineer(v0)
    services = build(tmp_path, script, limits={'program_repair_rounds': 0, 'program_paid_feedback': 0})
    probes, clients, locks, workers, drained = [], [], [], [], []

    def probe_call(bench, unit, tag):
        made = chain.ProbeCall()
        probes.append((unit, tag, made))
        return made

    def guarded(factory):
        def client(*args, **kw):
            unit = args[1]
            clients.append(unit)
            if '-probe-' in unit:
                raise AssertionError('a probe asked for a model client: ' + unit)
            return factory(*args, **kw)
        return client

    def heavy(bench, unit=None):
        locks.append(unit)
        return nullcontext()

    def worker_factory(bench, unit, tag):
        workers.append(unit)
        return lambda: None
    services.probe_call, services.heavy, services.worker_factory = probe_call, heavy, worker_factory
    services.solver_call, services.role_call = guarded(services.solver_call), guarded(services.role_call)
    services.drain = lambda unit: drained.append(unit) or {'drained': unit}
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    pid, unit = 'p-searchqa-1-1', 's1/program-1-probe-0'
    proposal = read(tmp_path, 's1', 'programs', 'proposals.json')[0]['procedure']
    probe = read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')
    noted = {i: chars(note_text(pid, 'searchqa-' + i), 'searchqa', 'searchqa-' + i) for i in ('l0', 'l1')}
    assert probe == {'unit': unit, 'bench': 'searchqa', 'step': 1, 'scope': 'first_request', 'selection': 'recorded',
                     'learned': 's1/outcomes', 'selection_unrecorded': 0, 'background': [],
                     'procedures': [[pid, proposal['record_sha256']]], 'items': 5, 'routed': 5, 'fired': 4, 'noted': 2,
                     'faults': {'timeout': 1}, 'unsent': 0, 'failed': 0, 'not_routed': [],
                     'per_item': [['searchqa-l0', True, noted['l0'], []], ['searchqa-l1', True, noted['l1'], []],
                                  ['searchqa-l2', True, 0, []], ['searchqa-l3', True, 0, ['timeout']],
                                  ['searchqa-l4', False, 0, []]]}
    # nothing sent, nothing charged: no model client for the unit, no scripted send, no ledger row, no calls file
    assert unit in state['done_units'] and not [u for u in clients if 'probe' in u]
    assert not [c for c in script.calls if c[1] and 'probe' in c[1]]
    ledger = json.loads((tmp_path / 'G' / 'ledger.json').read_text())
    assert not [u for u in ledger['by_unit'] if 'probe' in u]
    assert sorted(p.name for p in (tmp_path / 'G' / 's1' / 'program-1-probe-0').iterdir()) == ['drain.json', 'probe.json']
    # one probe call per side and item, each building one request (a selection would be answered from the record of
    # the item's outcomes cell; with no program in the type yet the mounts asked for none)
    mine = [(tag, made) for u, tag, made in probes if u == unit]
    assert len(mine) == 10 and all(len(made.requests) == 1 for _, made in mine)
    assert all(send['receipt']['ok'] is False and send['receipt']['error_type'] == chain.PROBE_ERROR
               for _, made in mine for send in made.sends)
    # the cell discipline: the memory lock and a sandbox worker per solve, the drain once after the unit
    assert locks.count(unit) == 10 and workers.count(unit) == 10 and drained.count(unit) == 1
    # without repair rounds and the paid round: no repair or learn unit, the proposal goes to the gate
    assert program_dirs(tmp_path) == ['program-1', 'program-1-gate', 'program-1-probe-0', 'programs']
    decision = read(tmp_path, 's1', 'decisions.json')['programs'][0]
    assert decision['repair'] == {'unit': 's1/program-1/refined.json', 'rounds': 0, 'limit': 0, 'kept_round': 0,
                                  'stop': 'round_limit', 'probes': [summary(unit, 5, 4, 2, {'timeout': 1})]}
    assert decision['learn'] is None and decision['procedure_sha256'] == proposal['record_sha256']
    assert (decision['accepted'], decision['reason']) == (False, 'never_fired') and 'smoke' not in decision


def test_the_probe_call_answers_with_a_failed_receipt_and_counts_nothing():
    probe = chain.ProbeCall()
    receipt = probe('system text', 'user text')
    assert receipt == {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'program_probe'}
    assert probe.requests == [{'request_sha256': units.sha256_text('system text\x00user text'), 'user_chars': 9}]
    assert probe.tokens() == 0 and probe.infrastructure_unknown() is False and len(probe.sends) == 1
    assert writers.reply_of(receipt) is None  # a writer reading it would see no reply


# ---- T8.3: the free repair rounds ---------------------------------------------------------------------------------------
def test_the_repair_loop_keeps_the_best_version_and_ends_at_the_first_round_without_improvement(tmp_path):
    """v0 notes 2 of 5 learn items with one fault; v1 notes 3 with one fault (kept: more noted); v2 notes 3 with one
    fault too (not strictly better: the repair ends, v1 stays). v1 also notes on every gate item, so the version that
    goes on to the gate (and into the library) is v1. Each round's request shows its kept version's coverage."""
    v0 = program('v0', note=['l0', 'l1'], silent=['l2'], timeout=['l3'])
    v1 = program('v1', note=['l0', 'l1', 'l2', 'g0', 'g1', 'g2'], timeout=['l3'])
    v2 = program('v2', note=['l0', 'l1', 'l2'], timeout=['l3'])
    script = Engineer(v0, {v0: v1, v1: v2})
    state, _ = run(tmp_path, script, limits={'program_paid_feedback': 0})
    assert state['complete'], state['paused']
    assert requests_of(script) == [('s1/programs', 'propose'), ('s1/program-1-repair-1', 'repair'),
                                   ('s1/program-1-repair-2', 'repair')]
    first, second = (script.users('program_writer', 's1/program-1-repair-%d' % r)[0] for r in (1, 2))
    assert (first['source'], second['source']) == (v0, v1)
    assert set(first) == {'request', 'bench', 'change', 'source', 'coverage'}
    assert first['coverage'] == {'items': 5, 'routed': 5, 'fired': 4, 'noted': 2, 'faults': {'timeout': 1},
                                 'scope': 'first_request',
                                 'classes': [{'class': 'fired_without_note', 'count': 1, 'tasks': tasks('searchqa', 'l2')},
                                             {'class': 'not_fired', 'count': 1, 'tasks': tasks('searchqa', 'l4')},
                                             {'class': 'fault:timeout', 'count': 1, 'tasks': tasks('searchqa', 'l3')}]}
    assert second['coverage']['classes'] == [{'class': 'not_fired', 'count': 1, 'tasks': tasks('searchqa', 'l4')},
                                             {'class': 'fault:timeout', 'count': 1, 'tasks': tasks('searchqa', 'l3')}]
    # no gate item reaches the engineer (the gate items' public text names them): only learn items' public text
    writer = [(unit, system, user) for purpose, unit, system, user in script.requests if purpose == 'program_writer']
    assert writer and not [unit for unit, _, user in writer if 'searchqa-g' in user]
    assert all(system == engineer_prompt.repair_system('searchqa') for unit, system, _ in writer
               if unit.startswith('s1/program-1-repair'))
    refined = read(tmp_path, 's1', 'program-1', 'refined.json')
    assert (refined['slot'], refined['round'], refined['stop'], refined['rounds'], refined['limit']) == (
        1, 1, 'no_improvement', 2, 3)
    assert refined['procedure']['source'] == v1 and refined['procedure']['id'] == 'p-searchqa-1-1'
    assert [(row['round'], row['status'], row['kept'], row['probe']) for row in refined['history']] == [
        (0, 'proposal', True, summary('s1/program-1-probe-0', 5, 4, 2, {'timeout': 1})),
        (1, 'revised', True, summary('s1/program-1-probe-1', 5, 4, 3, {'timeout': 1})),
        (2, 'revised', False, summary('s1/program-1-probe-2', 5, 4, 3, {'timeout': 1}))]
    rounds = [read(tmp_path, 's1', 'program-1-repair-%d' % r, 'repair.json') for r in (1, 2)]
    assert [(r['status'], r['kept'], r['stop'], r['rule'], r['probe_unit']) for r in rounds] == [
        ('revised', True, None, 'better', 's1/program-1-probe-1'),
        ('revised', False, 'no_improvement', 'better', 's1/program-1-probe-2')]
    # a revision keeps its id; its lineage names the repair call whose reply gave it
    assert refined['procedure']['lineage']['engineer_call'] == rounds[0]['request_sha256']
    assert rounds[0]['procedure_sha256'] == refined['procedure']['record_sha256']
    assert program_dirs(tmp_path) == ['program-1', 'program-1-gate', 'program-1-probe-0', 'program-1-probe-1',
                                      'program-1-probe-2', 'program-1-repair-1', 'program-1-repair-2', 'programs']
    decision = read(tmp_path, 's1', 'decisions.json')['programs'][0]
    assert decision['accepted'] and decision['procedure_sha256'] == refined['procedure']['record_sha256']
    assert decision['repair'] == {'unit': 's1/program-1/refined.json', 'rounds': 2, 'limit': 3, 'kept_round': 1,
                                  'stop': 'no_improvement', 'probes': [row['probe'] for row in refined['history']]}
    assert [s['body']['procedure']['source'] for s in programs_of(tmp_path)] == [v1]
    assert read(tmp_path, 's1', 'decisions.json')['program_learning'] == {
        'mode': 'repair', 'limits': {'program_repair_rounds': 3, 'program_paid_feedback': 0}, 'archive': None,
        'engineer_gate_current': 's1/outcomes', 'outcomes_with_archive': None}


def test_the_repair_loop_never_exceeds_its_limit(tmp_path):
    """Every revision notes one more learn item (1, 2, 3, 4 of 5): all three rounds improve, the fourth revision is
    never asked for, the third is kept."""
    versions = [program('w%d' % r, note=['l%d' % i for i in range(r + 1)]) for r in range(5)]
    script = Engineer(versions[0], dict(zip(versions, versions[1:])))
    state, _ = run(tmp_path, script, limits={'program_paid_feedback': 0})
    assert state['complete'], state['paused']
    assert requests_of(script) == [('s1/programs', 'propose')] + [
        ('s1/program-1-repair-%d' % r, 'repair') for r in (1, 2, 3)]
    refined = read(tmp_path, 's1', 'program-1', 'refined.json')
    assert (refined['round'], refined['stop'], refined['rounds']) == (3, 'round_limit', 3)
    assert refined['procedure']['source'] == versions[3]
    assert [(row['probe']['noted'], row['kept']) for row in refined['history']] == [(1, True), (2, True), (3, True),
                                                                                  (4, True)]
    assert not (tmp_path / 'G' / 's1' / 'program-1-repair-4').exists()
    assert not (tmp_path / 'G' / 's1' / 'program-1-probe-4').exists()


@pytest.mark.parametrize('case', ['screen', 'unchanged', 'nothing_to_repair'])
def test_a_round_without_a_new_version_ends_the_repair_with_the_last_good_one(tmp_path, case):
    """A revision the static screen refuses ([import] os) is reported and ends the repair: no fix call, no probe. The
    same program again ends it as 'unchanged' (no probe). A proposal that notes on every learn item without a fault
    leaves nothing to repair: no repair call at all."""
    v0 = program('v0', note=['l0', 'l1'])
    revisions = {v0: 'import os\n\n\n' + v0} if case == 'screen' else {}
    if case == 'nothing_to_repair':
        v0 = program('v0', note=['l0', 'l1', 'l2', 'l3', 'l4'])
    script = Engineer(v0, revisions)
    state, _ = run(tmp_path, script, limits={'program_paid_feedback': 0})
    assert state['complete'], state['paused']
    refined = read(tmp_path, 's1', 'program-1', 'refined.json')
    assert refined['round'] == 0 and refined['procedure']['source'] == v0
    if case == 'nothing_to_repair':
        assert requests_of(script) == [('s1/programs', 'propose')]
        assert (refined['stop'], refined['rounds']) == ('nothing_to_repair', 0)
        assert program_dirs(tmp_path) == ['program-1', 'program-1-gate', 'program-1-probe-0', 'programs']
        return
    assert requests_of(script) == [('s1/programs', 'propose'), ('s1/program-1-repair-1', 'repair')]
    written = read(tmp_path, 's1', 'program-1-repair-1', 'writer.json')
    record = read(tmp_path, 's1', 'program-1-repair-1', 'repair.json')
    assert (record['kept'], record['probe'], record['probe_unit'], record['procedure_sha256']) == (False, None, None, None)
    assert [row['status'] for row in refined['history']] == ['proposal', written['status']]
    if case == 'screen':
        assert (written['status'], record['stop']) == ('dropped_screen', 'screen')
        assert written['screen'] == {'passed': False, 'check': 'policy', 'rules': ['import']}
        assert written['reason'].startswith('policy: ') and written['procedure'] is None
    else:
        assert (written['status'], written['reason'], record['stop']) == ('unchanged', 'unchanged', 'unchanged')
    assert refined['stop'] == record['stop'] and refined['rounds'] == 1
    assert not (tmp_path / 'G' / 's1' / 'program-1-probe-1').exists()


def far_embedder(item_id):
    """``smoke.hash_embedder`` with the public text of ``item_id`` moved far from its bench's family: in a source of
    25 items the nearest-rank p95 threshold is the 24th distance, so that item alone is beyond it (unknown)."""
    def embed(texts):
        rows = smoke.hash_embedder(texts)
        return [[x + (8.0 if 'item %s?' % item_id in text else 0.0) for x in row] for row, text in zip(rows, texts)]
    return embed


@pytest.mark.parametrize('case', ['all_noted', 'three_noted'])
def test_a_learn_item_the_type_map_routes_elsewhere_is_no_failure_of_the_program(tmp_path, case):
    """20 learn items, l4 beyond the type's p95 threshold (as about 5 % of a bench's own items are): the candidate is
    never mounted there, whatever its version. 'all_noted': a program noting on all 20 notes on the 19 routed ones --
    nothing to repair. 'three_noted': notes on l0..l2 -- the repair request's not_fired class holds the 16 other routed
    items (l3, l5, ..., l19), never l4."""
    marks = ['l%d' % i for i in range(20)] if case == 'all_noted' else ['l0', 'l1', 'l2']
    script = Engineer(program('v0', note=marks))
    services = build(tmp_path, script, learn=20, limits={'program_paid_feedback': 0})
    services.embed = far_embedder('searchqa-l4')
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    probe = read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')
    noted = 19 if case == 'all_noted' else 3
    assert {key: probe[key] for key in ('items', 'routed', 'fired', 'noted', 'faults', 'not_routed')} == {
        'items': 20, 'routed': 19, 'fired': noted, 'noted': noted, 'faults': {}, 'not_routed': ['searchqa-l4']}
    assert probe['per_item'][4] == ['searchqa-l4', False, 0, []]
    refined = read(tmp_path, 's1', 'program-1', 'refined.json')
    if case == 'all_noted':
        assert (refined['stop'], refined['rounds']) == ('nothing_to_repair', 0)
        assert requests_of(script) == [('s1/programs', 'propose')]
        return
    assert (refined['stop'], refined['rounds']) == ('unchanged', 1)
    coverage = script.users('program_writer', 's1/program-1-repair-1')[0]['coverage']
    assert (coverage['items'], coverage['routed'], coverage['noted']) == (20, 19, 3)
    assert coverage['classes'] == [{'class': 'not_fired', 'count': 16,
                                    'tasks': tasks('searchqa', 'l3', 'l5', 'l6', 'l7', 'l8')}]


# ---- T8.4: the one paid feedback round ----------------------------------------------------------------------------------
@pytest.mark.parametrize('case', ['kept', 'worse', 'no_feedback', 'nothing_changed'])
def test_the_paid_round_repairs_once_when_it_broke_at_least_as_many_as_it_fixed(tmp_path, case):
    """F is right on l2 and l3 only. 'kept'/'worse': v0 notes on l0 (fixed 1) and writes a wrong note on l2 and l3
    (broken 2): one feedback repair shows the two broken items; v1 notes on l0, l1, l4 (3 noted, as v0) -- not worse,
    it replaces v0 and wins the gate; a revision noting l0 only (1 noted) is worse and v0 goes on. 'no_feedback': fixed
    2, broken 1. 'nothing_changed': silent everywhere, fixed 0, broken 0. No free round here (limit 0)."""
    v0 = {'kept': program('v0', note=['l0'], wrong=['l2', 'l3']), 'worse': program('v0', note=['l0'], wrong=['l2', 'l3']),
          'no_feedback': program('v0', note=['l0', 'l1'], wrong=['l2']),
          'nothing_changed': program('v0', silent=['l0', 'l1', 'l2', 'l3', 'l4'])}[case]
    v1 = program('v1', note=['l0', 'l1', 'l4', 'g0', 'g1', 'g2']) if case == 'kept' else program('v1', note=['l0'])
    script = Engineer(v0, {v0: v1})
    state, _ = run(tmp_path, script, limits={'program_repair_rounds': 0})
    assert state['complete'], state['paused']
    refined = read(tmp_path, 's1', 'program-1', 'refined.json')
    decision = read(tmp_path, 's1', 'decisions.json')['programs'][0]
    learn = decision['learn']
    fixed, broken = {'kept': (1, 2), 'worse': (1, 2), 'no_feedback': (2, 1), 'nothing_changed': (0, 0)}[case]
    assert {key: learn[key] for key in ('unit', 'items', 'cells', 'fixed', 'broken', 'faults', 'procedure_sha256')} == {
        'unit': 's1/program-1-learn', 'items': 5, 'cells': 5, 'fixed': fixed, 'broken': broken, 'faults': [],
        'procedure_sha256': refined['procedure']['record_sha256']}
    cells = gate_cells(tmp_path, 's1/program-1-learn')
    assert sorted((c['item_id'], c['arm']) for c in cells) == [('searchqa-l%d' % i, 'cand_program') for i in range(5)]
    if case in ('no_feedback', 'nothing_changed'):
        assert requests_of(script) == [('s1/programs', 'propose')] and learn['feedback'] is None
        assert decision['procedure_sha256'] == refined['procedure']['record_sha256']
        assert 'program-1-feedback' not in program_dirs(tmp_path)
        return
    # exactly one more repair, showing the broken items with their labels (learn items only), then no second paid round
    assert requests_of(script) == [('s1/programs', 'propose'), ('s1/program-1-feedback', 'repair')]
    request = script.users('program_writer', 's1/program-1-feedback')[0]
    assert request['source'] == v0 and request['learn'] == {
        'fixed': 1, 'broken': 2, 'broken_tasks': [{**row, 'outcome': 'fail', 'without_program': 'pass'}
                                                  for row in tasks('searchqa', 'l2', 'l3')]}
    assert request['coverage']['classes'] == [{'class': 'not_fired', 'count': 2, 'tasks': tasks('searchqa', 'l1', 'l4')}]
    feedback = read(tmp_path, 's1', 'program-1-feedback', 'repair.json')
    noted = 3 if case == 'kept' else 1
    assert (feedback['rule'], feedback['status'], feedback['probe']) == (
        'not_worse', 'revised', summary('s1/program-1-probe-feedback', 5, 3 if case == 'kept' else 1, noted))
    assert [p for p in program_dirs(tmp_path) if p.endswith('-learn')] == ['program-1-learn']
    if case == 'kept':
        assert (feedback['kept'], feedback['stop']) == (True, None)
        assert learn['feedback'] == {key: feedback[key] for key in ('unit', 'status', 'reason', 'procedure_sha256',
                                                                    'probe', 'kept', 'stop')}
        assert decision['procedure_sha256'] == feedback['procedure_sha256'] != refined['procedure']['record_sha256']
        assert decision['accepted'] and [s['body']['procedure']['source'] for s in programs_of(tmp_path)] == [v1]
    else:
        assert (feedback['kept'], feedback['stop']) == (False, 'no_improvement')
        assert decision['procedure_sha256'] == refined['procedure']['record_sha256']
        assert not decision['accepted'] and programs_of(tmp_path) == []


def test_a_fault_in_the_paid_round_refuses_the_version_as_a_smoke_fault(tmp_path):
    """v0 would win the gate (notes on every gate item) but times out on the learn item l1: refused with smoke_fault
    before any gate cell or feedback repair; the probe's fault was the engineer's to repair (limit 0 here)."""
    v0 = program('v0', note=['l0', 'g0', 'g1', 'g2'], timeout=['l1'])
    script = Engineer(v0)
    state, _ = run(tmp_path, script, limits={'program_repair_rounds': 0})
    assert state['complete'], state['paused']
    decision = read(tmp_path, 's1', 'decisions.json')['programs'][0]
    assert (decision['accepted'], decision['reason']) == (False, 'smoke_fault') and 'candidate_arm' not in decision
    assert decision['learn']['faults'] == [{'item_id': 'searchqa-l1', 'configuration_error': False, 'failure': None,
                                            'faults': [{'procedure': 'p-searchqa-1-1', 'hook': 'before_call',
                                                        'kind': 'timeout', 'exc_type': None,
                                                        'message': 'wall timeout of 5 s'}]}]
    assert decision['learn']['feedback'] is None and requests_of(script) == [('s1/programs', 'propose')]
    assert program_dirs(tmp_path) == ['program-1', 'program-1-learn', 'program-1-probe-0', 'programs']
    assert programs_of(tmp_path) == []


# ---- T9: the archive candidate ------------------------------------------------------------------------------------------
def archive_copy(monkeypatch, base, *, alfworld=None):
    """A copy of the tree's archive directory under ``base`` (the test's own scratch directory) that the loader reads
    instead (``ARCHIVE_DIR``). ``alfworld``: records that replace the ALFWorld package of both chains (file names,
    index rows and the index pin follow)."""
    copy = Path(base) / 'archive-copy'
    shutil.copytree(archives.ARCHIVE_DIR, copy)
    monkeypatch.setattr(archives, 'ARCHIVE_DIR', copy)
    if alfworld is not None:
        package = archives.PACKAGES[('G', 'alfworld')]
        shutil.rmtree(copy / 'alfworld' / package)
        (copy / 'alfworld' / package).mkdir()
        rows = []
        for record in alfworld:
            name = 'alfworld/%s/%s.procedure.json' % (package, record['id'])
            raw = (json.dumps(record, indent=1, sort_keys=True) + '\n').encode('utf-8')
            (copy / name).write_bytes(raw)
            rows.append({'id': record['id'], 'file': name, 'sha256': hashlib.sha256(raw).hexdigest(),
                         'record_sha256': record['record_sha256'], 'source_file': 'fixture'})
        index = json.loads((copy / archives.INDEX).read_text())
        for chain_name in ('G', 'D'):
            index['chains'][chain_name]['alfworld']['procedures'] = rows
        raw = json.dumps(index, indent=1, sort_keys=True).encode('utf-8')
        (copy / archives.INDEX).write_bytes(raw)
        monkeypatch.setattr(archives, 'INDEX_SHA256', hashlib.sha256(raw).hexdigest())
    return copy


def test_a_changed_archive_byte_is_refused_before_anything_is_written(tmp_path, monkeypatch):
    """One byte added to an archived ALFWorld record: the run of chain G on ZebraLogic refuses to start (every package
    of the chain is verified first) -- no chain directory, no state, no ledger, no call."""
    sealed = archives.sealed('index')
    copy = archive_copy(monkeypatch, tmp_path)
    path = copy / 'alfworld' / 'alfworld-v11-accepted' / 'p-alfworld-1-14.procedure.json'
    path.write_bytes(path.read_bytes() + b'\n')
    script = Engineer(program('e0', note=['l0']))
    services = build(tmp_path, script, bench='zebralogic', archive=sealed)
    with pytest.raises(ValueError, match='differs from the index'):
        chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert not (tmp_path / 'G').exists() and script.calls == [] and script.requests == []
    # a changed index byte is refused by its pin, a refused or unknown package by the index check
    (copy / archives.INDEX).write_bytes((copy / archives.INDEX).read_bytes() + b' ')
    with pytest.raises(ValueError, match='INDEX_SHA256'):
        archives.load_index()


def test_the_archive_package_is_candidate_zero_and_holds_the_incumbent_of_later_candidates(tmp_path, monkeypatch):
    """The G ZebraLogic package (one archived record, scripted to note on every item) is gated first as
    s1/program-0 against F and accepted: its record joins the library as a program skill with origin 'archive'. It
    then runs once on the learn slice (s1/outcomes-archive, forced from the state before it: every learn item right),
    and from there it is FORCED in every comparison arm of the step and offered in none (Codex P1 F3, F4): the
    engineer sees it in the index and the post-archive outcomes as its examples; its candidate is probed with the
    package forced on both sides, its paid round compares with s1/outcomes-archive, and its gate arm forces both
    against the package's gate arm: it notes on g0 only, where the package already makes the solver right, so it
    gains nothing there (gain_below_tau)."""
    pid, eid = 'p-zebralogic-3-5', 'p-zebralogic-1-1'
    monkeypatch.setitem(ARCHIVE_BEHAVIOUR, pid, {'*': 'note'})
    e0 = program('e0', note=['l0', 'g0'])
    script = Engineer(e0)
    sealed = archives.sealed('index')
    state, _ = run(tmp_path, script, bench='zebralogic', archive=sealed)
    assert state['complete'], state['paused']
    record = archives.load_package(sealed, 'G', 'zebralogic')['procedures'][0]
    tid, cap = type_of(tmp_path), record['max_note_chars']
    done = state['done_units']
    assert done.index('s1/program-0-gate') < done.index('s1/outcomes-archive') < done.index('s1/programs')
    archive, engineer = read(tmp_path, 's1', 'decisions.json')['programs']
    assert {key: archive[key] for key in ('kind', 'origin', 'candidate', 'unit', 'package', 'procedure_ids',
                                          'procedure_sha256', 'accepted', 'reason', 'fired_items')} == {
        'kind': 'program', 'origin': 'archive', 'candidate': 0, 'unit': 's1/program-0',
        'package': 'main-v6-G-s3-p-zebralogic-3-5', 'procedure_ids': [pid], 'procedure_sha256': [record['record_sha256']],
        'accepted': True, 'reason': 'accepted', 'fired_items': 3}
    assert archive['screen'] == [{'id': pid, 'passed': True, 'check': None, 'rules': [], 'evidence': None}]
    assert archive['probe'] == summary('s1/program-0-probe-0', 5, 5, 5)
    assert archive['baseline']['unit'] == 's1/outcomes' and archive['candidate_arm'] == {
        'unit': 's1/program-0-gate', 'arm': 'cand_program', 'shared_from': None}
    forced = {'kind': 'program', 'applied': True, 'ids': [pid], 'sha256': [record['record_sha256']], 'home_type': tid}
    for cell in gate_cells(tmp_path, 's1/program-0-gate'):  # the package as one candidate, every record forced
        assert cell['fired'] == [pid] and cell['mount']['candidate'] == forced
    # accepted: the archived record itself, described as an accepted program, with origin 'archive'
    skills = read(tmp_path, 's1', 'program-0', 'skills.json')['skills']
    assert [s['body']['procedure'] for s in skills] == [record] and skills[0]['kind'] == 'program'
    assert {key: skills[0]['origin'][key] for key in ('kind', 'package', 'archive_record_sha256', 'unit', 'step')} == {
        'kind': 'archive', 'package': 'main-v6-G-s3-p-zebralogic-3-5', 'archive_record_sha256': record['record_sha256'],
        'unit': 's1/program-0', 'step': 1}
    assert skills[0]['description'] and [s['skill_id'] for s in programs_of(tmp_path)] == [skills[0]['skill_id']]
    # the package once more on the learn slice, as its gate arm ran: forced, from the state before it (no offer)
    learned = gate_cells(tmp_path, 's1/outcomes-archive')
    assert sorted((c['item_id'], c['arm'], c['fired'], c['correct']) for c in learned) == [
        ('zebralogic-l%d' % n, 'cand_program', [pid], True) for n in range(5)]
    assert all(c['mount']['candidate'] == forced and not c['mount'].get('programs_offered') for c in learned)
    # the engineer's index holds it; its examples are the post-archive outcomes (every learn item right)
    request = script.users('program_writer', 's1/programs')[0]
    assert request['skill_index'] == [{'name': skills[0]['name'], 'kind': 'program',
                                       'description': skills[0]['description'], 'home_type': tid}]
    assert request['trajectories'] and {row['token'] for row in request['trajectories']} == {'pass'}
    # its candidate mounts from the state before the package, with the package forced (never offered)
    assert engineer['procedure_id'] == eid and archive['mount_snapshot']['library'] == []
    assert engineer['mount_snapshot'] == {**archive['mount_snapshot'], 'forced': [pid]}
    assert engineer['baseline'] == {'unit': 's1/program-0-gate', 'arm': 'cand_program', 'shared_from': None}
    assert (engineer['accepted'], engineer['reason'], engineer['fired_items']) == (False, 'gain_below_tau', 1)
    cells = gate_cells(tmp_path, 's1/program-1-gate')
    assert {(c['item_id'], tuple(c['fired'])) for c in cells} == {
        ('zebralogic-g0', (pid, eid)), ('zebralogic-g1', (pid,)), ('zebralogic-g2', (pid,))}
    assert all(c['mount']['candidate']['ids'] == [pid, eid] and not c['mount'].get('programs_offered') for c in cells)
    # the probe: the package forced on both sides, so the difference is the candidate's note alone
    probe = read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')
    assert (probe['learned'], probe['background'], probe['selection_unrecorded']) == (
        's1/outcomes-archive', [[pid, record['record_sha256']]], 0)
    assert probe['per_item'] == [['zebralogic-l0', True, added('zebralogic', 'zebralogic-l0', [(pid, None, cap)],
                                                                [(pid, None, cap), (eid, None, 600)]), []]] + [
        ['zebralogic-l%d' % n, False, 0, []] for n in range(1, 5)]
    # the paid round: against the post-archive outcomes, nothing fixed or broken there
    assert {key: engineer['learn'][key] for key in ('unit', 'against', 'fixed', 'broken', 'feedback')} == {
        'unit': 's1/program-1-learn', 'against': 's1/outcomes-archive', 'fixed': 0, 'broken': 0, 'feedback': None}
    assert all(c['mount']['candidate']['ids'] == [pid, eid] for c in gate_cells(tmp_path, 's1/program-1-learn'))
    assert read(tmp_path, 's1', 'decisions.json')['program_learning'] == {
        'mode': 'repair', 'limits': {'program_repair_rounds': 3, 'program_paid_feedback': 1},
        'archive': {'unit': 's1/program-0', 'package': 'main-v6-G-s3-p-zebralogic-3-5', 'procedure_ids': [pid],
                    'accepted': True, 'reason': 'accepted'},
        'engineer_gate_current': 's1/program-0-gate',
        'outcomes_with_archive': {'unit': 's1/outcomes-archive', 'arm': 'cand_program',
                                  'learn': {'items': 5, 'cells': 5, 'pass': 5, 'fail': 0, 'unknown': 0}, 'members': []}}


def test_a_refused_archive_package_leaves_the_library_as_it_was(tmp_path):
    """The package never applies (no behaviour scripted): never_fired. Nothing joins; the engineer's candidate is
    judged against F of s1/outcomes and its index is empty."""
    script = Engineer(program('e0', note=['l0', 'g0', 'g1', 'g2']))
    state, _ = run(tmp_path, script, bench='zebralogic', archive=archives.sealed('index'))
    assert state['complete'], state['paused']
    archive, engineer = read(tmp_path, 's1', 'decisions.json')['programs']
    assert (archive['origin'], archive['accepted'], archive['reason']) == ('archive', False, 'never_fired')
    assert archive['probe'] == summary('s1/program-0-probe-0', 5, 0, 0)
    assert sorted(p.name for p in (tmp_path / 'G' / 's1' / 'program-0').iterdir()) == ['decision.json']
    assert engineer['baseline']['unit'] == 's1/outcomes' and engineer['mount_snapshot']['library'] == []
    assert script.users('program_writer', 's1/programs')[0]['skill_index'] == []
    assert engineer['accepted'] and [s['body']['procedure']['id'] for s in programs_of(tmp_path)] == ['p-zebralogic-1-1']
    learning = read(tmp_path, 's1', 'decisions.json')['program_learning']
    assert (learning['engineer_gate_current'], learning['outcomes_with_archive']) == ('s1/outcomes', None)
    # a refused package adds no post-archive unit and forces nothing: the engineer's arms are typed-v2's
    assert not (tmp_path / 'G' / 's1' / 'outcomes-archive').exists() and 'forced' not in engineer['mount_snapshot']
    probe = read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')
    assert (probe['learned'], probe['background']) == ('s1/outcomes', [])
    assert engineer['learn']['against'] == 's1/outcomes'
    assert all(c['mount']['candidate']['id'] == 'p-zebralogic-1-1' for c in gate_cells(tmp_path, 's1/program-1-gate'))


def test_the_alfworld_package_is_gated_as_one_candidate_and_joins_whole(tmp_path):
    """The three ALFWorld records enabled together in every gate cell; fired = any of them fired (p-alfworld-1-14
    notes on l0, g0 and g1; p-alfworld-1-15 applies silently on g2; p-alfworld-1-6 never applies). Accepted: all
    three join the library in package order, each with its own skill id and origin 'archive'."""
    ARCHIVE_BEHAVIOUR.update({'p-alfworld-1-14': {'l0': 'note', 'g0': 'note', 'g1': 'note'},
                              'p-alfworld-1-15': {'g2': 'silent'}, 'p-alfworld-1-6': {}})
    try:
        script = Engineer(program('e0', note=['l0']))  # a before_call program: not an ALFWorld note hook
        sealed = archives.sealed('index')
        state, _ = run(tmp_path, script, bench='alfworld', archive=sealed)
    finally:
        for pid in ('p-alfworld-1-14', 'p-alfworld-1-15', 'p-alfworld-1-6'):
            ARCHIVE_BEHAVIOUR.pop(pid, None)
    assert state['complete'], state['paused']
    records = archives.load_package(sealed, 'G', 'alfworld')['procedures']
    ids = ['p-alfworld-1-6', 'p-alfworld-1-14', 'p-alfworld-1-15']
    assert [r['id'] for r in records] == ids
    archive = read(tmp_path, 's1', 'decisions.json')['programs'][0]
    assert (archive['accepted'], archive['fired_items'], archive['procedure_ids']) == (True, 3, ids)
    assert [row['passed'] for row in archive['screen']] == [True, True, True]
    assert archive['probe'] == summary('s1/program-0-probe-0', 5, 1, 1)
    hashes = [r['record_sha256'] for r in records]
    for cell in gate_cells(tmp_path, 's1/program-0-gate'):
        assert cell['mount']['candidate']['ids'] == ids and cell['mount']['candidate']['sha256'] == hashes
    skills = read(tmp_path, 's1', 'program-0', 'skills.json')['skills']
    assert [s['body']['procedure'] for s in skills] == records
    assert [s['origin']['archive_record_sha256'] for s in skills] == hashes
    assert len({s['skill_id'] for s in skills}) == 3 and len({s['name'] for s in skills}) == 3
    assert [s['skill_id'] for s in programs_of(tmp_path)] == [s['skill_id'] for s in skills]
    assert [read(tmp_path, 's1', 'program-0', 'skill-%d.json' % n)['skill'] for n in (1, 2, 3)] == skills


def state_only_record():
    """An ALFWorld record that keeps state and writes no note (alf_after_step only): it passes the frozen structure
    check but not the typed screen (no ALFWorld note hook, addendum O7)."""
    return Procedure(id='p-alfworld-1-14', origin='alfworld', description='Keeps the places it visited in its state.',
                     hooks=('alf_after_step',), source='def alf_after_step(view, state):\n    return {"visited": 1}\n',
                     evidence='smoke', state_bytes=256, policy_version=writers.POLICY_VERSION,
                     lineage={'parent': None, 'revises': None, 'engineer_call': 'b' * 64}).to_json()


def test_a_package_with_one_record_the_screen_refuses_is_refused_whole(tmp_path, monkeypatch):
    clean, failed = writers.build_procedure(smoke.ALFWORLD_ENTRY, smoke.ALFWORLD_SOURCE, bench='alfworld',
                                            evidence='smoke', engineer_call='a' * 64, step=1, ordinal=6)
    assert failed is None
    archive_copy(monkeypatch, tmp_path, alfworld=[clean.to_json(), state_only_record()])
    sealed = archives.sealed('index')
    monkeypatch.setitem(ARCHIVE_BEHAVIOUR, 'p-alfworld-1-6', {'*': 'note'})  # it would win the gate alone
    script = Engineer(program('e0', note=['l0']))
    state, _ = run(tmp_path, script, bench='alfworld', archive=sealed)
    assert state['complete'], state['paused']
    archive = read(tmp_path, 's1', 'decisions.json')['programs'][0]
    assert (archive['accepted'], archive['reason'], archive['procedure_ids']) == (
        False, 'archive_screen', ['p-alfworld-1-6', 'p-alfworld-1-14'])
    first, second = archive['screen']
    assert first == {'id': 'p-alfworld-1-6', 'passed': True, 'check': None, 'rules': [], 'evidence': None}
    assert (second['id'], second['passed'], second['check'], second['rules']) == (
        'p-alfworld-1-14', False, 'hooks', ['no_hook_function'])
    assert second['evidence'] is not None and 'probe' not in archive and 'candidate_arm' not in archive
    assert 'program-0-probe-0' not in program_dirs(tmp_path) and 'program-0-gate' not in program_dirs(tmp_path)
    assert programs_of(tmp_path) == [] and not [c for c in script.calls if c[1] and c[1].startswith('s1/program-0')]


def test_a_paid_round_that_fixed_as_many_as_it_broke_gets_its_one_feedback_repair(tmp_path):
    """Codex P1 F6, the positive tie: v0 notes on l0 (F wrong there: fixed 1) and writes a wrong note on l2 (F right
    there: broken 1). broken >= fixed and fixed + broken > 0, so the one feedback repair follows, showing l2; its
    revision v1 (notes on l0 and l1: noted 2, as v0's two shown notes) is not worse and replaces v0."""
    v0, v1 = program('v0', note=['l0'], wrong=['l2']), program('v1', note=['l0', 'l1'])
    script = Engineer(v0, {v0: v1})
    state, _ = run(tmp_path, script, limits={'program_repair_rounds': 0})
    assert state['complete'], state['paused']
    learn = read(tmp_path, 's1', 'decisions.json')['programs'][0]['learn']
    assert (learn['against'], learn['fixed'], learn['broken']) == ('s1/outcomes', 1, 1)
    assert requests_of(script) == [('s1/programs', 'propose'), ('s1/program-1-feedback', 'repair')]
    request = script.users('program_writer', 's1/program-1-feedback')[0]
    assert request['source'] == v0 and request['learn'] == {
        'fixed': 1, 'broken': 1, 'broken_tasks': [{**tasks('searchqa', 'l2')[0], 'outcome': 'fail',
                                                   'without_program': 'pass'}]}
    assert (learn['feedback']['kept'], learn['feedback']['probe']) == (
        True, summary('s1/program-1-probe-feedback', 5, 2, 2))


# ---- Codex P1 F3: after an accepted package, the post-archive learn outcomes -------------------------------------------
HAND = {'l0': 'note', 'l1': 'note', 'g0': 'note', 'g1': 'note', 'g2': 'note'}   # the archived record's behaviour


def hand_case(monkeypatch):
    """The archived G ZebraLogic record notes on l0, l1 and every gate item; the engineer's e0 notes on l4 and writes
    a wrong note on l1; its feedback revision e1 notes on l1 and l4. By hand: F is right on l2 and l3; with the
    package on l0..l3 (s1/outcomes-archive). e0 with the package forced is right on l0, l2, l3 (the package's notes or
    none), on l4 (its note), wrong on l1 (its wrong note). Against the post-archive outcomes: fixed 1 (l4), broken 1
    (l1), a tie, so one feedback repair; against F's pre-archive outcomes it would be fixed 2 (l0, l4), broken 0."""
    monkeypatch.setitem(ARCHIVE_BEHAVIOUR, 'p-zebralogic-3-5', dict(HAND))
    e0, e1 = program('e0', note=['l4'], wrong=['l1']), program('e1', note=['l1', 'l4'])
    return e0, {e0: e1}


def learn_outcomes(root, unit):
    """{learn item: correct} of a unit's learn cells."""
    return {c['item_id']: c['correct'] for c in gate_cells(root, unit) if '-l' in c['item_id']}


def test_after_an_accepted_package_the_writers_and_the_paid_round_use_the_post_archive_outcomes(tmp_path, monkeypatch):
    """The hand case (``hand_case``): the package's learn unit runs once (five cells, five sends); the engineer's
    examples carry its labels (l0 and l1 right), the paid round's fixed / broken are counted against it (1 / 1, not F's
    2 / 0) and its tie brings the feedback repair, whose learn report shows l1 as broken (right with the package
    alone)."""
    e0, revisions = hand_case(monkeypatch)
    script = Engineer(e0, revisions)
    state, _ = run(tmp_path, script, bench='zebralogic', archive=archives.sealed('index'),
                   limits={'program_repair_rounds': 0})
    assert state['complete'], state['paused']
    before, after = learn_outcomes(tmp_path, 's1/outcomes'), learn_outcomes(tmp_path, 's1/outcomes-archive')
    assert before == {'zebralogic-l0': False, 'zebralogic-l1': False, 'zebralogic-l2': True, 'zebralogic-l3': True,
                      'zebralogic-l4': False}
    assert after == {**before, 'zebralogic-l0': True, 'zebralogic-l1': True}
    assert Counter(unit for purpose, unit in script.calls)['s1/outcomes-archive'] == 5  # once, one send per cell
    # the engineer's examples: the post-archive labels
    request = script.users('program_writer', 's1/programs')[0]
    assert {row['task_id']: row['token'] for row in request['trajectories']} == {
        item: 'pass' if ok else 'fail' for item, ok in after.items()}
    # the paid round, by hand from the cells: a tie against the post-archive outcomes, (2, 0) against F's
    paid = learn_outcomes(tmp_path, 's1/program-1-learn')
    assert paid == {**after, 'zebralogic-l1': False, 'zebralogic-l4': True}

    def fixed_broken(side):
        return (sum(side[i] is False and paid[i] is True for i in paid),
                sum(side[i] is True and paid[i] is False for i in paid))
    assert (fixed_broken(after), fixed_broken(before)) == ((1, 1), (2, 0))
    decision = read(tmp_path, 's1', 'decisions.json')['programs'][1]
    assert {key: decision['learn'][key] for key in ('unit', 'against', 'fixed', 'broken')} == {
        'unit': 's1/program-1-learn', 'against': 's1/outcomes-archive', 'fixed': 1, 'broken': 1}
    assert requests_of(script) == [('s1/programs', 'propose'), ('s1/program-1-feedback', 'repair')]
    report = script.users('program_writer', 's1/program-1-feedback')[0]['learn']
    assert (report['fixed'], report['broken']) == (1, 1)
    assert [(row['task_id'], row['outcome'], row['without_program']) for row in report['broken_tasks']] == [
        ('zebralogic-l1', 'fail', 'pass')]
    assert decision['learn']['feedback']['kept'] and decision['procedure_sha256'] == decision['learn']['feedback'][
        'procedure_sha256']
    assert read(tmp_path, 's1', 'decisions.json')['program_learning']['outcomes_with_archive']['learn'] == {
        'items': 5, 'cells': 5, 'pass': 4, 'fail': 1, 'unknown': 0}


@pytest.mark.parametrize('point', ['inside', 'after'])
def test_a_step_killed_inside_or_right_after_the_post_archive_unit_resumes_to_the_same_records(tmp_path, monkeypatch,
                                                                                             point):
    """The hand case, killed (a process death, no pause) 'inside' s1/outcomes-archive -- at the solve of l2, before
    its send -- or right 'after' the unit's cells were all written. The resumed step runs only the missing cells, makes
    no call twice, and every record equals an uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    e0, revisions = hand_case(monkeypatch)
    kw = dict(bench='zebralogic', archive=archives.sealed('index'), limits={'program_repair_rounds': 0})
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = Engineer(e0, revisions)
    state, _ = run(reference, script_a, **kw)
    assert state['complete'], state['paused']
    script_b = Engineer(e0, revisions)
    services, hit = build(resumed, script_b, **kw), []
    if point == 'inside':
        def solve(bench, item, mounted, **rest):
            if rest['unit'] == 's1/outcomes-archive' and item['task_id'] == 'zebralogic-l2' and not hit:
                hit.append(item['task_id'])
                raise Kill()
            return shell_solve(bench, item, mounted, **rest)
        services.solve_fn = solve
    else:
        original = chain._Run.cells

        def cells(self, unit, *args, **rest):
            found = original(self, unit, *args, **rest)
            if unit == 's1/outcomes-archive' and not hit:
                hit.append(unit)
                raise Kill()
            return found
        monkeypatch.setattr(chain._Run, 'cells', cells)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    step = resumed / 'G' / 's1'
    written = len(list((step / 'outcomes-archive' / 'cells').glob('*.json')))
    assert hit and not (step / 'programs').exists()
    assert written == 5 if point == 'after' else 0 < written < 5
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert_same_run(reference, resumed, script_a, script_b, failed_sends=0, named=(
        's1/outcomes-archive/done.json', 's1/programs/proposals.json', 's1/program-1/decision.json'))
    assert Counter(unit for purpose, unit in script_b.calls)['s1/outcomes-archive'] == 5


# ---- Codex P1 F2: the probe mounts the incumbents ----------------------------------------------------------------------
def capped_scenario():
    """Step 1 (SearchQA): P1 writes notes of 3,500 characters (its cap 4,000) on SearchQA's gate items and on the
    OfficeQA learn item l0; it wins the gate. Step 2 (OfficeQA joins SearchQA's type, so P1 is offered there): vA writes
    a 1,000-character note on l0, its revision vB a 200-character one."""
    p1 = program('p1', size=3500, note=['searchqa-g0', 'searchqa-g1', 'searchqa-g2', 'officeqa-l0'])
    va, vb = program('va', size=1000, note=['officeqa-l0']), program('vb', size=200, note=['officeqa-l0'])
    return {'searchqa': p1, 'officeqa': va}, {va: vb}


@pytest.mark.parametrize('case', ['recorded', 'unrecorded'])
def test_the_probe_mounts_an_earlier_program_by_its_recorded_selection_so_the_total_note_cap_acts_as_in_a_cell(
        tmp_path, monkeypatch, case):
    """Codex P1 F2 (the 4,000-character total cap). The selection call of every s2/outcomes cell enabled P1; the probe
    answers both sides' selection calls from that record (no call). On l0 P1's 3,500-character note comes first, and
    with vA's 1,000 characters the total would pass the cap: vA's note is skipped whole, the two sides' requests are
    the same -- noted 0 -- so vA is repaired; vB's 200 characters fit beside P1's note (noted, kept). 'unrecorded': no
    learn cell's selection is on record; each of the five items of the type counts in selection_unrecorded and both
    sides mount no selectable program, so vA's note is shown alone (noted) and vB is no improvement."""
    if case == 'unrecorded':
        monkeypatch.setattr(chain, '_recorded_selection', lambda cell: None)
    propose, revisions = capped_scenario()
    script = Engineer(propose, revisions, entry=WIDE)
    state, _ = run(tmp_path, script, order=('searchqa', 'officeqa'))
    assert state['complete'], state['paused']
    (p1,) = programs_of(tmp_path, 1)
    pid = p1['body']['procedure']['id']
    assert p1['body']['procedure']['source'] == propose['searchqa'] and type_of(tmp_path, 2) == type_of(tmp_path, 1)
    l0 = next(c for c in gate_cells(tmp_path, 's2/outcomes') if c['item_id'] == 'officeqa-l0')
    assert l0['mount']['selection']['use'] == [p1['name']] and l0['mount']['programs_enabled'] == [p1['skill_id']]
    vid, alone = 'p-officeqa-2-1', added('officeqa', 'officeqa-l0', [], [('p-officeqa-2-1', 1000, 4000)])
    first, second = (read(tmp_path, 's2', 'program-1-probe-%d' % r, 'probe.json') for r in (0, 1))
    assert (first['learned'], first['background'], first['selection']) == ('s2/outcomes', [], 'recorded')
    refined = read(tmp_path, 's2', 'program-1', 'refined.json')
    if case == 'recorded':
        assert (first['selection_unrecorded'], first['fired'], first['noted']) == (0, 1, 0)
        assert first['per_item'][0] == ['officeqa-l0', True, 0, []] and alone > 0
        assert second['per_item'][0] == ['officeqa-l0', True, added(
            'officeqa', 'officeqa-l0', [(pid, 3500, 4000)], [(pid, 3500, 4000), (vid, 200, 4000)]), []]
        assert (refined['round'], refined['procedure']['source']) == (1, revisions[propose['officeqa']])
    else:
        assert (first['selection_unrecorded'], first['fired'], first['noted']) == (5, 1, 1)
        assert first['per_item'][0] == ['officeqa-l0', True, alone, []] and second['selection_unrecorded'] == 5
        assert (refined['round'], refined['stop'], refined['procedure']['source']) == (
            0, 'no_improvement', propose['officeqa'])
    # the probes asked no model for a selection and charged nothing
    assert not [c for c in script.calls if c[1] and '-probe-' in c[1]]
    ledger = json.loads((tmp_path / 'G' / 'ledger.json').read_text())
    assert not [u for u in ledger['by_unit'] if '-probe-' in u]


# ---- Codex P1 F4: a package accepted earlier in the step is forced, never offered ---------------------------------------
def test_an_accepted_package_is_forced_in_every_later_arm_of_the_step_and_offered_in_none(tmp_path, monkeypatch):
    """The solver model's selection call would choose nothing ('{"use": []}'). The package (notes on g0 and g1) is
    accepted; the engineer's e0 notes on g2. Every later comparison arm of the step (probe, paid round, gate) forces
    the package and offers no program, so no selection call is made there and e0's gate arm differs from the package's
    in e0 alone: right on g0, g1 as the package, and on g2 -- a gain, no loss: accepted. (Offered to that selection
    call, the package would have been dropped from e0's arms: a loss on g0 and g1.)"""
    pid, eid = 'p-zebralogic-3-5', 'p-zebralogic-1-1'
    monkeypatch.setitem(ARCHIVE_BEHAVIOUR, pid, {'g0': 'note', 'g1': 'note'})
    script = Engineer(program('e0', note=['g2']), scripted={'replies': {'selection': '{"use": [], "why": "none"}'}})
    state, _ = run(tmp_path, script, bench='zebralogic', archive=archives.sealed('index'))
    assert state['complete'], state['paused']
    archive, engineer = read(tmp_path, 's1', 'decisions.json')['programs']
    assert (archive['accepted'], engineer['accepted'], engineer['reason']) == (True, True, 'accepted')
    assert engineer['mount_snapshot']['forced'] == [pid] and engineer['mount_snapshot']['library'] == []

    def outcomes(unit):
        return Counter((c['item_id'], c['correct']) for c in gate_cells(tmp_path, unit))
    assert outcomes('s1/program-0-gate') == {('zebralogic-g0', True): 3, ('zebralogic-g1', True): 3,
                                             ('zebralogic-g2', False): 3}
    assert outcomes('s1/program-1-gate') == {('zebralogic-g%d' % n, True): 3 for n in range(3)}
    for unit in ('s1/program-1-learn', 's1/program-1-gate'):
        for cell in gate_cells(tmp_path, unit):
            assert cell['mount']['candidate']['ids'] == [pid, eid] and cell['mount']['programs_offered'] == []
            assert cell['mount']['selection']['status'] == 'not_needed'
    assert read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')['background'] == [[pid, archive['procedure_sha256'][0]]]
    assert not [c for c in script.calls if c[0] == 'selection']


# ---- resume: kill inside a repair loop, after a probe before its round record, after an accepted archive -------------------
VOLATILE = {'logical_call', 'ledger', 'at', 'started', 'finished', 'updated'}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def records(root):
    """Every JSON record of the chain directory but the state, the ledger, the owner's recovery files, the first
    call's receipt and the calls files (an interrupted send stays in its calls file and the ledger, DESIGN 3.3),
    without the send counters, ledger snapshots and wall-clock stamps."""
    base, out = Path(root, 'G'), {}
    for path in sorted(base.rglob('*.json')):
        rel = path.relative_to(base).as_posix()
        if (rel in ('state.json', 'ledger.json', 'confirm.json') or rel.startswith('recovery')
                or '/calls/' in '/' + rel):
            continue
        out[rel] = strip(json.loads(path.read_text()))
    return out


def loop_scenario():
    """v0 (noted 2, one fault) -> v1 (noted 3, no fault: kept, wins the gate) -> v2 (noted 2: the repair ends); the
    paid round on v1 fixes l0 and l1 and breaks nothing (no feedback repair)."""
    v0 = program('v0', note=['l0', 'l1'], silent=['l2'], timeout=['l3'])
    v1 = program('v1', note=['l0', 'l1', 'l2', 'g0', 'g1', 'g2'])
    v2 = program('v2', note=['l0', 'l1'])
    return v0, {v0: v1, v1: v2}


def assert_same_run(reference, resumed, script_a, script_b, *, failed_sends, named=()):
    found, expected = records(resumed), records(reference)
    assert sorted(found) == sorted(expected)
    assert {'s1/decisions.json', 's1/library.json', 's1/typemap.json', 's1/frozen.json', *named} <= set(expected)
    for rel in expected:
        assert found[rel] == expected[rel], rel
    # no call whose record exists was repeated: the scripted sends are the uninterrupted run's
    assert Counter(script_b.calls) == Counter(script_a.calls)
    assert len(script_b.requests) == len(script_a.requests) + failed_sends


@pytest.mark.parametrize('point', ['repair_call', 'repair_record'])
def test_a_repair_loop_resumes_without_repeating_a_call_or_changing_a_record(tmp_path, monkeypatch, point):
    """'repair_call': the engineer's call of round 2 is interrupted; 'repair_record': the process dies after round 1's
    writer record and the probe of its revision, before its round record. The resumed step makes the missing call
    (once) or only writes the missing record, and every record equals an uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    propose, revisions = loop_scenario()
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = Engineer(propose, revisions)
    state, _ = run(reference, script_a)
    assert state['complete'], state['paused']
    assert read(reference, 's1', 'program-1', 'refined.json')['stop'] == 'no_improvement'
    assert read(reference, 's1', 'decisions.json')['programs'][0]['accepted']
    broken = {('program_writer', 's1/program-1-repair-2')} if point == 'repair_call' else set()
    script_b = Engineer(propose, revisions, broken=broken)
    if point == 'repair_record':
        original, hit = chain._Run.record, []

        def record(self, unit, name, compute):
            if (unit, name) == ('s1/program-1-repair-1', chain.REPAIR_RECORD) and not hit:
                hit.append(unit)
                raise RuntimeError('killed before the round record')
            return original(self, unit, name, compute)
        monkeypatch.setattr(chain._Run, 'record', record)
    services = build(resumed, script_b)
    state = chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:RuntimeError', state['paused']
    step = resumed / 'G' / 's1'
    if point == 'repair_record':
        assert (step / 'program-1-repair-1' / 'writer.json').exists() and (step / 'program-1-probe-1' / 'probe.json').exists()
        assert not (step / 'program-1-repair-1' / 'repair.json').exists()
    else:
        assert (step / 'program-1-repair-1' / 'repair.json').exists()
        assert not (step / 'program-1-repair-2' / 'writer.json').exists()
    assert not (step / 'program-1' / 'refined.json').exists()
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert_same_run(reference, resumed, script_a, script_b, failed_sends=len(broken), named=(
        's1/program-1/decision.json', 's1/program-1/refined.json', 's1/program-1-repair-1/writer.json',
        's1/program-1-repair-1/repair.json', 's1/program-1-repair-2/repair.json', 's1/program-1-probe-1/probe.json',
        's1/program-1-probe-2/probe.json', 's1/program-1/skill.json'))
    rounds = Counter(unit for unit, _ in requests_of(script_b))
    assert rounds['s1/program-1-repair-1'] == 1 and rounds['s1/program-1-repair-2'] == 1 + len(broken)
    # a later resume of the complete chain sends nothing and changes nothing
    before, files = len(script_b.requests), records(resumed)
    assert chain.run(resumed, 'G', services=services, resume=True)['complete']
    assert len(script_b.requests) == before and records(resumed) == files


def test_a_step_resumes_after_an_accepted_archive_candidate(tmp_path, monkeypatch):
    """The process dies at the engineer's proposal call, after the archive package was gated, accepted and described:
    the resumed step reloads the stored decision (its gate arm registered again, its skills added) and proposes once
    more; nothing of the archive runs again and every record equals an uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    monkeypatch.setitem(ARCHIVE_BEHAVIOUR, 'p-zebralogic-3-5', {'*': 'note'})
    e0, sealed = program('e0', note=['l0', 'g0']), archives.sealed('index')
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = Engineer(e0)
    state, _ = run(reference, script_a, bench='zebralogic', archive=sealed)
    assert state['complete'], state['paused']
    script_b = Engineer(e0, broken={('program_writer', 's1/programs')})
    services = build(resumed, script_b, bench='zebralogic', archive=sealed)
    state = chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:RuntimeError' and state['paused']['unit'] == 's1/programs'
    assert (resumed / 'G' / 's1' / 'program-0' / 'decision.json').exists()
    assert read(resumed, 's1', 'program-0', 'decision.json')['accepted']
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert_same_run(reference, resumed, script_a, script_b, failed_sends=1, named=(
        's1/program-0/decision.json', 's1/program-0/skills.json', 's1/program-0-probe-0/probe.json',
        's1/program-0-gate/plan.json', 's1/programs/proposals.json', 's1/program-1/decision.json'))
    assert requests_of(script_b).count(('s1/programs', 'propose')) == 2
    assert read(resumed, 's1', 'decisions.json')['programs'][1]['baseline']['unit'] == 's1/program-0-gate'


def test_a_package_interrupted_between_two_describer_calls_describes_only_the_rest(tmp_path, monkeypatch):
    """The ALFWorld package is accepted; the process dies before the describer call of its second record. The resumed
    step keeps the first described skill (its write-once record), describes the second and third once, and every
    record (skill ids and names included) equals an uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    for pid, kinds in (('p-alfworld-1-14', {'g0': 'note', 'g1': 'note'}), ('p-alfworld-1-6', {}),
                       ('p-alfworld-1-15', {})):
        monkeypatch.setitem(ARCHIVE_BEHAVIOUR, pid, kinds)
    sealed, e0 = archives.sealed('index'), program('e0', note=['l0'])
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = Engineer(e0)
    state, _ = run(reference, script_a, bench='alfworld', archive=sealed)
    assert state['complete'], state['paused']
    assert read(reference, 's1', 'program-0', 'decision.json')['accepted']
    second = archives.load_package(sealed, 'G', 'alfworld')['procedures'][1]['record_sha256']
    original, hit = chain._Run.describe, []

    def describe(self, skill, bench, unit):
        if skill['origin'].get('archive_record_sha256') == second and not hit:
            hit.append(skill['skill_id'])
            raise RuntimeError('killed before the second describer call')
        return original(self, skill, bench, unit)
    monkeypatch.setattr(chain._Run, 'describe', describe)
    script_b = Engineer(e0)
    services = build(resumed, script_b, bench='alfworld', archive=sealed)
    state = chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:RuntimeError', state['paused']
    unit = resumed / 'G' / 's1' / 'program-0'
    assert (unit / 'skill-1.json').exists() and not (unit / 'skill-2.json').exists()
    assert not (unit / 'skills.json').exists() and not (unit / 'decision.json').exists()
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert_same_run(reference, resumed, script_a, script_b, failed_sends=0, named=(
        's1/program-0/skill-1.json', 's1/program-0/skill-2.json', 's1/program-0/skill-3.json',
        's1/program-0/skills.json', 's1/program-0/decision.json'))
    assert Counter(script_b.calls)[('describer', 's1/program-0')] == 3


def fixture_package(monkeypatch, base, bench, record, package):
    """``archive_copy`` with one more package: chain G on ``bench``, named ``package``, holding ``record`` (the package
    table, the index rows and the index pin follow; restored after the test)."""
    copy = archive_copy(monkeypatch, base)
    monkeypatch.setitem(archives.PACKAGES, ('G', bench), package)
    name = '%s/%s/%s.procedure.json' % (bench, package, record['id'])
    (copy / bench / package).mkdir(parents=True)
    raw = (json.dumps(record, indent=1, sort_keys=True) + '\n').encode('utf-8')
    (copy / name).write_bytes(raw)
    index = json.loads((copy / archives.INDEX).read_text())
    index['chains']['G'][bench] = {'package': package, 'procedures': [
        {'id': record['id'], 'file': name, 'sha256': hashlib.sha256(raw).hexdigest(),
         'record_sha256': record['record_sha256'], 'source_file': 'fixture'}]}
    raw = json.dumps(index, indent=1, sort_keys=True).encode('utf-8')
    (copy / archives.INDEX).write_bytes(raw)
    monkeypatch.setattr(archives, 'INDEX_SHA256', hashlib.sha256(raw).hexdigest())
    return package


def test_in_a_shared_type_the_accepted_package_member_arms_become_the_member_baselines(tmp_path, monkeypatch):
    """Codex P1 F3 and F6 (addendum D16 with T9). SearchQA learns at step 1 (its program never applies on a gate item:
    refused, its type holds no skill); OfficeQA joins that type at step 2 with SearchQA as its member, and a fixture
    package of chain G on OfficeQA (one record: notes on OfficeQA g0, g1, l0 and on SearchQA g0, l0) is candidate 0:
    a gain at home, no harm on SearchQA (a gain on g0): accepted. Its member arm becomes SearchQA's member baseline and
    s2/member-searchqa-outcomes-archive refreshes SearchQA's examples (l0 right). The engineer's e0 notes on OfficeQA
    g2 (a gain against the package's gate arm) and writes a wrong note on SearchQA g0: against the package's member arm
    that is harm (g0 right there, wrong with e0): member_harm -- against the member base before the package (every
    SearchQA gate item wrong) it would have been none."""
    made, failed = writers.build_procedure(ENTRY, program('oqa'), bench='officeqa', evidence='smoke',
                                           engineer_call='a' * 64, step=1, ordinal=7)
    assert failed is None
    record = made.to_json()
    package = fixture_package(monkeypatch, tmp_path, 'officeqa', record, 'oqa-fixture-accepted')
    rid, eid = record['id'], 'p-officeqa-2-1'
    monkeypatch.setitem(ARCHIVE_BEHAVIOUR, rid, {'officeqa-g0': 'note', 'officeqa-g1': 'note', 'officeqa-l0': 'note',
                                                 'searchqa-g0': 'note', 'searchqa-l0': 'note'})
    s0, e0 = program('s0', note=['searchqa-l0']), program('e0', note=['officeqa-g2'], wrong=['searchqa-g0'])
    script = Engineer({'searchqa': s0, 'officeqa': e0})
    state, _ = run(tmp_path, script, order=('searchqa', 'officeqa'), archive=archives.sealed('index'))
    assert state['complete'], state['paused']
    assert programs_of(tmp_path, 1) == [] and type_of(tmp_path, 2) == type_of(tmp_path, 1)
    decisions = read(tmp_path, 's2', 'decisions.json')
    archive, engineer = decisions['programs']
    assert (archive['origin'], archive['package'], archive['accepted'], archive['reason']) == (
        'archive', package, True, 'accepted')
    (check,) = archive['members']
    assert (check['bench'], check['no_regress'], check['units']) == (
        'searchqa', True, {'baseline': 's2/member-searchqa-base', 'candidate': 's2/program-0-member-searchqa'})
    # the package's runs on SearchQA's learn slice: its examples for the engineer's member block
    member = learn_outcomes(tmp_path, 's2/member-searchqa-outcomes-archive')
    assert member == {**learn_outcomes(tmp_path, 's2/member-searchqa-outcomes'), 'searchqa-l0': True}
    assert all(c['mount']['candidate']['ids'] == [rid]
               for c in gate_cells(tmp_path, 's2/member-searchqa-outcomes-archive'))
    request = script.users('program_writer', 's2/programs')[0]
    (source,) = request['members']['sources']
    assert {row['task_id']: row['token'] for row in source['trajectories']} == {
        item: 'pass' if ok else 'fail' for item, ok in member.items()}
    # the engineer's candidate: the package forced at home and on the member; the member baseline is the package's arm
    assert (engineer['accepted'], engineer['reason']) == (False, 'member_harm')
    assert engineer['baseline']['unit'] == 's2/program-0-gate' and engineer['mount_snapshot']['forced'] == [rid]
    (harm,) = engineer['members']
    assert (harm['bench'], harm['no_regress'], harm['units']) == (
        'searchqa', False, {'baseline': 's2/program-0-member-searchqa', 'candidate': 's2/program-1-member-searchqa'})

    def outcomes(unit):
        return Counter((c['item_id'], c['correct']) for c in gate_cells(tmp_path, unit))
    wrong = {('searchqa-g%d' % n, False): 3 for n in range(3)}
    assert outcomes('s2/program-1-member-searchqa') == wrong == outcomes('s2/member-searchqa-base')
    assert outcomes('s2/program-0-member-searchqa') == {**{k: v for k, v in wrong.items() if k[0] != 'searchqa-g0'},
                                                        ('searchqa-g0', True): 3}
    assert all(c['mount']['candidate']['ids'] == [rid, eid]
               for c in gate_cells(tmp_path, 's2/program-1-member-searchqa'))
    assert decisions['program_learning']['outcomes_with_archive'] == {
        'unit': 's2/outcomes-archive', 'arm': 'cand_program',
        'learn': {'items': 5, 'cells': 5, 'pass': 3, 'fail': 2, 'unknown': 0},
        'members': [{'bench': 'searchqa', 'unit': 's2/member-searchqa-outcomes-archive',
                     'learn': {'items': 5, 'cells': 5, 'pass': 3, 'fail': 2, 'unknown': 0}}]}


# ---- Codex P1 F5: a completed role call is replayed, not sent again -----------------------------------------------------
# point: (unit, phase record, failed describer sends before the description arrives, sends of that call)
WINDOWS = {'proposal': ('s1/programs', 'proposals.json', 0, 2), 'repair': ('s1/program-1-repair-1', 'writer.json', 0, 1),
           'describer': ('s1/program-0', 'skill-1.json', 0, 1),
           'describer_format_retry': ('s1/program-0', 'skill-1.json', 1, 2),
           'describer_retry_attempt': ('s1/program-0', 'skill-1.json', 2, 3)}
INFRA_FAILURE = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'timeout'}


def failing_describer(failures):
    """The scripted describer: its first ``failures`` sends get an infrastructure failure (a timeout receipt), every
    later one the scripted description."""
    count = []

    def reply(system, user):
        count.append(user)
        return dict(INFRA_FAILURE) if len(count) <= failures else smoke.DEFAULT_DESCRIPTION
    return reply


def every_record(root):
    """``records`` with every calls file (each send of each role and solver call; ``logical_call`` stripped)."""
    base, out = Path(root, 'G'), {}
    for path in sorted(base.rglob('*.json')):
        rel = path.relative_to(base).as_posix()
        if rel not in ('state.json', 'ledger.json', 'confirm.json') and not rel.startswith('recovery'):
            out[rel] = strip(json.loads(path.read_text()))
    return out


@pytest.mark.parametrize('point', sorted(WINDOWS))
def test_a_role_call_whose_receipt_was_saved_before_its_record_is_replayed_not_sent_again(tmp_path, monkeypatch,
                                                                                        point):
    """Codex P1 F5: the process dies after a role call's receipt reached its calls file and before the phase record
    that holds what the call returned -- the engineer's proposal (a prose reply, then its one format retry: two
    receipts), a repair round's call, the describer call of the accepted archive record: delivered at once
    ('describer'), after a timeout of its first send (its format retry delivers: 'describer_format_retry'), or after
    two timeouts (the describer's attempt 1 fails for infrastructure, the chain's one retry ``describe-<id>-r2``
    delivers: 'describer_retry_attempt', the window of Codex's second look). The resumed step answers those calls from
    their saved receipts, in order -- a failure the flow went past included, the describer at its attempt that holds
    the delivered receipt: no send, no charge, and every record, every calls file and the ledger's counts equal an
    uninterrupted run's."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    monkeypatch.setitem(ARCHIVE_BEHAVIOUR, 'p-zebralogic-3-5', {'*': 'note'})
    e0, e1 = program('e0', note=['l0', 'g0']), program('e1', note=['l0', 'l1', 'g0'])
    kw = dict(bench='zebralogic', archive=archives.sealed('index'))
    unit, name, failures, calls = WINDOWS[point]
    reference, resumed = tmp_path / 'a', tmp_path / 'b'

    def engineer():
        return Engineer(e0, {e0: e1}, prose_first=True, scripted={'replies': {'describer': failing_describer(failures)}})
    script_a = engineer()
    state, _ = run(reference, script_a, **kw)
    assert state['complete'], state['paused']
    assert read(reference, 's1', 'programs', 'proposals.json')[0]['format_retry'] is not None
    skill_id = read(reference, 's1', 'program-0', 'skills.json')['skills'][0]['skill_id']
    retry_file = Path(reference, 'G', 's1', 'program-0', 'calls', 'describe-%s-r2-describer.json' % skill_id)
    assert retry_file.exists() == (point == 'describer_retry_attempt')
    original, hit = chain._Run.record, []

    def record(self, unit_, name_, compute):
        if (unit_, name_) == (unit, name) and not hit:
            compute()            # the call is made and its receipt saved in the unit's calls file ...
            hit.append(unit_)
            raise Kill()         # ... and the process dies before the record is written
        return original(self, unit_, name_, compute)
    monkeypatch.setattr(chain._Run, 'record', record)
    script_b = engineer()
    services = build(resumed, script_b, **kw)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit and not (resumed / 'G' / unit / name).exists()
    purpose = 'describer' if point.startswith('describer') else 'program_writer'
    sent = Counter(script_b.calls)[(purpose, unit)]
    assert sent == Counter(script_a.calls)[(purpose, unit)] == calls
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert Counter(script_b.calls)[(purpose, unit)] == sent  # replayed: nothing sent again
    assert Counter(script_b.calls) == Counter(script_a.calls) and len(script_b.requests) == len(script_a.requests)
    found, expected = every_record(resumed), every_record(reference)
    assert sorted(found) == sorted(expected) and any('/calls/' in rel for rel in expected)
    for rel in expected:
        assert found[rel] == expected[rel], rel
    ledgers = [json.loads((root / 'G' / 'ledger.json').read_text()) for root in (reference, resumed)]
    keys = ('sends', 'charged', 'reported', 'missing_usage', 'recovered', 'by_unit')
    assert [{key: ledger[key] for key in keys} for ledger in ledgers][0] == {key: ledgers[1][key] for key in keys}


def test_a_replay_answers_each_delivered_receipt_of_a_request_once_in_file_order(tmp_path):
    """Codex P1 F5 / F6 (second look), the replay itself over a real calls file, recorder and ledger. The earlier
    attempt's file: A delivered R1, B delivered RB, A failed, A delivered R2, C failed (the last send: where the earlier
    process stood). Resumed, A B A A C A get R1, RB, R2 (the delivered receipts of A, each once, in file order), then
    A's failure (the flow went past it: a delivered receipt follows it), and only C and the third A are sent -- and
    charged, and appended to the file after the earlier sends. With nothing delivered in the file nothing is replayed
    (a recovery after failures sends again)."""
    system = 'role system'

    def send(user, response=None):
        made = (smoke.receipt(response, model='m', system=system, user=user) if response is not None
                else dict(INFRA_FAILURE))
        return {'request_sha256': units.sha256_text(system + '\x00' + user), 'system': system, 'user': user,
                'logical_call': 'earlier', 'receipt': {key: made.get(key) for key in units.RECEIPT_KEYS},
                'charge_bound': 100, 'reserved': 400}
    earlier = [send('A', 'R1'), send('B', 'RB'), send('A'), send('A', 'R2'), send('C')]
    path, fresh = tmp_path / 'calls' / 'writer-program_writer.json', []
    units.write_json(path, earlier)

    def client(system_, user):
        fresh.append(user)
        return smoke.receipt('new ' + user, model='m', system=system_, user=user)
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 6)
    call = chain._replay_receipts(chain._keep_earlier_sends(units.CallRecorder(
        client, ledger, max_tokens=50, tag='writer', unit='s1/programs', out_path=path)))
    assert [writers.reply_of(call(system, user)) for user in ('A', 'B', 'A', 'A', 'C', 'A')] == [
        'R1', 'RB', 'R2', None, 'new C', 'new A']
    assert fresh == ['C', 'A'] and ledger.state['sends'] == 2 and len(call.replayed) == 4
    kept = units.read_json(path)
    assert kept[:5] == earlier and [row['user'] for row in kept[5:]] == ['C', 'A']
    # nothing delivered in the file: the recorder itself, every call sent
    units.write_json(tmp_path / 'failed.json', [send('A'), send('B')])
    plain = units.CallRecorder(client, ledger, max_tokens=50, tag='writer', unit='s1/programs',
                               out_path=tmp_path / 'failed.json')
    assert chain._replay_receipts(chain._keep_earlier_sends(plain)) is plain


# ---- Codex P1 F6: the probe through the real solver shell ---------------------------------------------------------------
REAL_SOURCE = ('def applies(view):\n'
               '    return "searchqa-l4" not in str(view)\n\n\n'
               'def before_call(view, state):\n'
               '    if "searchqa-l2" in str(view):\n'
               '        return {}\n'
               '    return {"warnings": ["Quote the author named in the snippet."]}\n')


class InProcessWorker:
    """A deterministic sandbox worker in this process: each hook call runs through route B's own executor
    (``worker_v222.execute``, the code path of the container's child) and returns the client's result shape, except
    the calls of ``timeouts`` ({(procedure id, hook, text in the arguments)}), answered with the client's wall-timeout
    fault. ``calls``: (procedure id, hook) of every call."""

    def __init__(self, timeouts=()):
        self.timeouts, self.calls, self.package = set(timeouts), [], None

    def start(self, package, **options):
        self.package = package
        return self

    def ping(self):
        return {'ok': True}

    def call(self, proc_id, fn, args, *, timeout_s, diagnostics_v215=False):
        self.calls.append((proc_id, fn))
        if any((proc_id, fn) == (pid, hook) and marker in json.dumps(args) for pid, hook, marker in self.timeouts):
            return worker_v222.fault('timeout', None, 'wall timeout of %s s' % timeout_s)
        proc = next(row for row in self.package.procedures if row.id == proc_id)
        result = worker_v222.execute(compile(proc.source, '<in-process>', 'exec'), fn, list(args), 65536)
        return {**result, 'value_sha256': digest(result['value']) if result.get('ok') else None, 'cpu_ms': 0,
                'rss_kib': 1}

    def close(self):
        pass


def test_the_probe_runs_through_the_real_solver_shell_with_a_deterministic_sandbox_worker(tmp_path):
    """The probe through the REAL ``mount.solve`` and ``solver.solve`` (the learn and gate cells keep the scripted
    shell) with an in-process sandbox worker; before_call on l3 is answered with the wall-timeout fault. The program
    applies everywhere but on l4 and writes a caution, except on l2 (an empty return). By hand: fired 4, noted 2 (l0,
    l1: the caution as ``notes.render`` renders it), one timeout on l3; nothing sent or charged, no failure (the shell
    stops at the probe's failed receipt); the incumbent side (no program) starts no worker."""
    script = Engineer(REAL_SOURCE)
    services = build(tmp_path, script, limits={'program_repair_rounds': 0, 'program_paid_feedback': 0})
    pid, workers = 'p-searchqa-1-1', []

    def solve(bench, item, mounted, **rest):
        return (mount.solve if '-probe-' in rest['unit'] else shell_solve)(bench, item, mounted, **rest)

    def worker_factory(bench, unit, tag):
        def make():
            workers.append((unit, InProcessWorker({(pid, 'before_call', 'searchqa-l3')})))
            return workers[-1][1]
        return make
    services.solve_fn, services.worker_factory = solve, worker_factory
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    probe = read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')
    caution = notes_.render({'warnings': ['Quote the author named in the snippet.']}, bench='searchqa', header='')
    noted = {i: chars(caution, 'searchqa', 'searchqa-' + i) for i in ('l0', 'l1')}
    assert {key: probe[key] for key in ('items', 'routed', 'fired', 'noted', 'faults', 'unsent', 'failed')} == {
        'items': 5, 'routed': 5, 'fired': 4, 'noted': 2, 'faults': {'timeout': 1}, 'unsent': 0, 'failed': 0}
    assert probe['per_item'] == [['searchqa-l0', True, noted['l0'], []], ['searchqa-l1', True, noted['l1'], []],
                                 ['searchqa-l2', True, 0, []], ['searchqa-l3', True, 0, ['timeout']],
                                 ['searchqa-l4', False, 0, []]]
    mine = [w for unit, w in workers if unit == 's1/program-1-probe-0']
    assert [w.calls for w in mine] == [[(pid, 'applies'), (pid, 'before_call')]] * 4 + [[(pid, 'applies')]]
    assert not [c for c in script.calls if c[1] and '-probe-' in c[1]]
    ledger = json.loads((tmp_path / 'G' / 'ledger.json').read_text())
    assert not [u for u in ledger['by_unit'] if '-probe-' in u]


# ---- the pieces: the repair text, the reports, the repair call, the archive loader, the package mount -------------------
@pytest.mark.parametrize('bench', typed_.ORDER)
def test_the_repair_text_shares_the_propose_texts_rules_and_states_the_run_limits(bench):
    text = engineer_prompt.repair_system(bench)
    paragraphs = text.rstrip('\n').split('\n\n')
    heads = [p.split('.', 1)[0] for p in paragraphs[3:]]
    assert len(paragraphs) == 8 and heads == ['HOOKS', 'NOTES', 'RUN LIMITS', 'CONTENT', 'STATIC SCREEN']
    propose = {p.split('.', 1)[0]: p for p in engineer_prompt.system(bench, 'propose').rstrip('\n').split('\n\n')}
    for head, paragraph in zip(heads, paragraphs[3:]):
        if head != 'RUN LIMITS':
            assert paragraph == propose[head], head  # word for word the propose text's (the bound screen's rules)
    limits = paragraphs[5]
    assert 'wall limit of %d s (applies: %d s)' % (profiles.SANDBOX_TIMEOUTS['hook'],
                                                   profiles.SANDBOX_TIMEOUTS['predicate']) in limits
    assert profiles.SANDBOX_TIMEOUTS['hook'] == 5 and 'must prune' in limits
    assert paragraphs[1].count('up to 5 ') == 2 and writers.REPAIR_SHOWN_ITEMS == 5
    assert paragraphs[2].startswith('WHAT YOU RETURN. ')
    assert hashlib.sha256(text.encode('utf-8')).hexdigest() == engineer_prompt.REPAIR_PINS[(bench, 'repair')]
    with pytest.raises(ValueError):
        engineer_prompt.system(bench, 'repair')  # the two typed-v2 purposes stay the only ones of ``system``
    assert set(engineer_prompt.verify()['pins']) == {'%s.%s' % key for key in engineer_prompt.PINS}


def probe_row(item_id, fired, note, kinds=()):
    return [item_id, fired, note, list(kinds)]


def test_the_coverage_and_learn_reports_show_learn_items_only():
    items = [{'task_id': 'searchqa-l%d' % i, 'public': {}} for i in range(9)]
    views = {item['task_id']: smoke.SYNTHETIC_ITEMS['searchqa'](item['task_id'])[0] for item in items}
    rows = ([probe_row('searchqa-l%d' % i, False, 0) for i in range(7)]                    # 7 not fired, l1 unrouted
            + [probe_row('searchqa-l7', True, 30, ['timeout', 'exception', 'timeout'])]   # a fault, though noted
            + [probe_row('searchqa-l8', True, 0)])                                           # fired, no note
    probe = {'items': 9, 'routed': 8, 'fired': 2, 'noted': 1, 'faults': {'exception': 1, 'timeout': 2},
             'scope': 'first_request', 'not_routed': ['searchqa-l1'], 'per_item': rows}
    report = writers.coverage_report(probe, items, views)
    assert [(c['class'], c['count'], [t['task_id'][-2:] for t in c['tasks']]) for c in report['classes']] == [
        ('fired_without_note', 1, ['l8']), ('not_fired', 6, ['l0', 'l2', 'l3', 'l4', 'l5']),
        ('fault:exception', 1, ['l7']), ('fault:timeout', 1, ['l7'])]
    assert report['classes'][0]['tasks'] == tasks('searchqa', 'l8')
    assert {key: report[key] for key in ('items', 'routed', 'fired', 'noted', 'faults', 'scope')} == {
        'items': 9, 'routed': 8, 'fired': 2, 'noted': 1, 'faults': {'exception': 1, 'timeout': 2},
        'scope': 'first_request'}
    with pytest.raises(ValueError):  # a row of an item outside the supplied learn items
        writers.coverage_report({**probe, 'per_item': rows + [probe_row('searchqa-g0', True, 0)]}, items, views)
    learn = writers.learn_report(['searchqa-l0'], ['searchqa-l%d' % i for i in (1, 2, 3, 4, 5, 6)], items, views)
    assert (learn['fixed'], learn['broken'], len(learn['broken_tasks'])) == (1, 6, 5)
    assert learn['broken_tasks'][0] == {**tasks('searchqa', 'l1')[0], 'outcome': 'fail', 'without_program': 'pass'}
    with pytest.raises(ValueError):
        writers.learn_report([], ['searchqa-g0'], items, views)


class Replies:
    """A role call that answers from a list (a text is delivered, None is a failed receipt) and keeps every request."""

    def __init__(self, *texts):
        self.texts, self.requests = list(texts), []

    def __call__(self, system, user):
        self.requests.append((system, json.loads(user)))
        text = self.texts.pop(0)
        return (smoke.receipt(text, model='m', system=system, user=user) if text is not None
                else {'ok': False, 'response': None, 'finish_reason': None, 'error_type': 'timeout'})


@pytest.mark.parametrize('case', ['revised', 'unchanged', 'dropped_screen', 'unreadable', 'no_reply'])
def test_one_repair_call_reads_one_revision_with_one_format_retry_and_never_fixes(case):
    v0, v1 = program('v0', note=['l0']), program('v1', note=['l0', 'l1'])
    procedure, failed = writers.build_procedure(ENTRY, v0, bench='searchqa', evidence='smoke', engineer_call='c' * 64,
                                                step=2, ordinal=3)
    assert failed is None
    procedure = procedure.to_json()
    replies = {'revised': [smoke.program_reply([(ENTRY, v1)])], 'unchanged': [smoke.program_reply([(ENTRY, v0)])],
               'dropped_screen': [smoke.program_reply([(ENTRY, 'import os\n\n\n' + v1)])],
               'unreadable': ['A better program would note on more tasks.'] * 2, 'no_reply': [None]}[case]
    call = Replies(*replies)
    coverage = {'items': 1, 'fired': 1, 'noted': 1, 'faults': {}, 'scope': 'first_request', 'classes': []}
    found = writers.repair_program(bench='searchqa', procedure=procedure, coverage=coverage, call=call, evidence='smoke',
                                   learn={'fixed': 0, 'broken': 0, 'broken_tasks': []})
    assert found['status'] == case and len(call.requests) == (2 if case == 'unreadable' else 1)
    system, user = call.requests[0]
    assert system == engineer_prompt.repair_system('searchqa') and user == {
        'request': 'repair', 'bench': 'searchqa', 'change': writers.repair_entry(procedure, 'searchqa'), 'source': v0,
        'coverage': coverage, 'learn': {'fixed': 0, 'broken': 0, 'broken_tasks': []}}
    assert user['change'] == {'kind': 'new', 'description': ENTRY['description'], 'hooks': ['before_call'], 'header': '',
                              'max_note_chars': 600}
    if case == 'revised':
        assert found['procedure']['id'] == 'p-searchqa-2-3' and found['procedure']['source'] == v1
        assert found['procedure']['lineage']['engineer_call'] == found['request_sha256']
        assert found['screen'] == {'passed': True, 'check': None, 'rules': []}
    else:
        assert found['procedure'] is None
    if case == 'dropped_screen':
        assert found['screen']['rules'] == ['import'] and found['reason'].startswith('policy: ')
    if case == 'unreadable':
        assert found['format_retry'] is not None and found['reason'].startswith('unparseable: ')


def test_the_archive_index_pins_the_five_records_and_the_loader_refuses_any_other():
    index = archives.load_index()
    assert {(chain_name, bench): entry['package'] for chain_name, benches in index['chains'].items()
            for bench, entry in benches.items()} == archives.PACKAGES
    # the record hashes of the SkillOpt skill-archive manifest (2026-11-09), independent of the loader
    expected = {'p-zebralogic-3-5': '55b36369be79659892f4810172d4e6504c03c9fd81d2334e74502e1fc3855cfb',
                'p-alfworld-1-6': 'a93758eae5454350a6cbb1301032f4de94c05d82159edc699e72d065e530f262',
                'p-alfworld-1-14': '9ab7ff8b708e0992ffa1ecaa8a68334587e63e6523e0fe61d8960992709fa919',
                'p-alfworld-1-15': '768778bd771e5c9470f8faf1e36e51af33418503c492e77b8db8044f02ac689c'}
    sealed = archives.sealed('index')
    for chain_name in ('G', 'D'):
        for bench in ('zebralogic', 'alfworld'):
            package = archives.load_package(sealed, chain_name, bench)
            for record in package['procedures']:
                assert writers.screen_record(record, bench)['passed'], record['id']
                if record['id'] in expected:
                    assert record['record_sha256'] == expected[record['id']]
    assert archives.load_package(sealed, 'D', 'zebralogic')['procedures'][0]['id'] == 'p-zebralogic-3-3'
    files = sorted(p.relative_to(archives.ARCHIVE_DIR).as_posix() for p in archives.ARCHIVE_DIR.rglob('*.json'))
    assert files == ['alfworld/alfworld-v11-accepted/p-alfworld-1-14.procedure.json',
                     'alfworld/alfworld-v11-accepted/p-alfworld-1-15.procedure.json',
                     'alfworld/alfworld-v11-accepted/p-alfworld-1-6.procedure.json', 'index.json',
                     'zebralogic/main-v6-D-s3-p-zebralogic-3-3/p-zebralogic-3-3.procedure.json',
                     'zebralogic/main-v6-G-s3-p-zebralogic-3-5/p-zebralogic-3-5.procedure.json']
    assert not any(word in name for name in files for word in archives.REFUSED_NAMES)
    # a sealed value must be the index's entry: a changed hash, order, package, bench or chain is refused
    reordered = json.loads(json.dumps(sealed))
    reordered['G']['alfworld']['procedures'].reverse()
    renamed = json.loads(json.dumps(sealed))
    renamed['G']['zebralogic']['package'] = 'zebra-pc-v4'
    for bad in (reordered, renamed, {'G': {'searchqa': sealed['G']['zebralogic']}}, {'X': sealed['G']},
                {'G': {'zebralogic': sealed['D']['zebralogic']}}, ['index'], 'index'):
        with pytest.raises((ValueError, TypeError)):
            archives.check_sealed(bad)
    with pytest.raises(ValueError):
        archives.load_package(sealed, 'G', 'searchqa')
    with pytest.raises(ValueError):
        archives.sealed('all')


def test_a_package_candidate_mounts_every_record_and_keeps_the_single_shape():
    tm, library, tid, centroid = typed_world(programs=0)
    first, second = program_record('fx-pack-a'), program_record('fx-pack-b')
    never = SelectorScript([])
    package = {'procedures': [first, second], 'home_type': tid}
    rec = mount.mount('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library, vector=centroid,
                      selector=never, candidate=package)
    assert rec['enabled'] == [first, second] and not never.requests
    assert rec['candidate'] == {'kind': 'program', 'applied': True, 'ids': ['fx-pack-a', 'fx-pack-b'],
                                'sha256': [first['record_sha256'], second['record_sha256']], 'home_type': tid}
    identity = mount.mount_identity('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library,
                                    vector=centroid, candidate=package)
    assert identity['forced'] == [first['record_sha256'], second['record_sha256']]
    single = {'procedure': first, 'home_type': tid}
    assert mount.mount_identity('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library, vector=centroid,
                                candidate=single)['forced'] == first['record_sha256']
    one = mount.mount('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library, vector=centroid,
                      selector=never, candidate=single)
    assert one['candidate'] == {'kind': 'program', 'applied': True, 'id': 'fx-pack-a', 'sha256': first['record_sha256'],
                                'home_type': tid}
    for bad in ({'procedures': [], 'home_type': tid}, {'procedures': [first], 'procedure': first, 'home_type': tid},
                {'procedures': [first, first], 'home_type': tid}, {'procedures': first, 'home_type': tid},
                {'procedures': [first]}):
        with pytest.raises(ValueError):
            mount.mount('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library, vector=centroid,
                        selector=never, candidate=bad)
    # a package record already mounted through the selection is refused, as a single candidate's is
    tm2, library2, tid2, centroid2 = typed_world(programs=1)
    chosen = SelectorScript(['{"use": ["snippet-scanner-a"], "why": "x"}'])
    with pytest.raises(ValueError):
        mount.mount('searchqa', qa_item(), arm='cand_program', typemap=tm2, library=library2, vector=centroid2,
                    selector=chosen, candidate={'procedures': [program_record('fx-typed-a')], 'home_type': tid2})
