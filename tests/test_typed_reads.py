"""Consent-gated reads and run preparation of typed-v2 (fakes only: no network, no /data, no model calls)."""
import contextlib
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.coevo5 import data
from skillopt.execskill import evaluation, profiles, v218_lock, zebralogic
from skillopt.execskill.typed import ORDER, READ_ARMS, SMOKE_SLICES, chain, machinery, prepare, reads, units
from skillopt.validator_pilot.api import digest

# pytest's tmp_path carries the word "test" (refused by the sealed-path guard) and, on macOS, /tmp is a symlink,
# which route B's safe_path refuses in any parent: the neutral root is used through its resolved spelling.
NEUTRAL = Path('/tmp/typed2-neutral').resolve()


@pytest.fixture
def tmp_path():
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='reads-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def consent_value(**changes):
    value = {'test_evaluation': True, 'sheet_test_qualification': True, 'multi_arm_arms': list(READ_ARMS),
             'by': 'owner', 'date': '2026-11-10', 'note': 'typed-v2 five-panel reads after every step'}
    value.update(changes)
    return value


def write_consent(shared, **changes):
    units.write_json(shared / 'consent.json', consent_value(**changes))


def fake_panel(bench, n=4, seen=None, *, game=False):
    """A synthetic panel reader behind ``data.TestAccess`` (the shape of ``coevo5.data.test_panel``)."""
    def panel(pinned, benchmark, *, access):
        assert isinstance(access, data.TestAccess)
        if seen is not None:
            seen.append((benchmark, access.unit, pinned))
        tasks = []
        for i in range(n):
            if game:
                public = {'game_file': '/x/json_2.1.1/valid_unseen/pick-Book-None-Desk-30%d/trial_T1/game.tw-pddl' % i}
            else:
                public = {'question': 'synthetic panel question %d about rivers?' % i, 'context': 'context %d' % i}
            tasks.append({'task_id': '%s-t%d' % (bench, i), 'family_id': 'f%d' % i, 'partition': 'final',
                          'public': public, 'private': {'answer': 'a%d' % i}})
        return tasks, {'benchmark': benchmark, 'tasks': n, 'excluded_without_pages': [], 'training_items_identical': None,
                       'panel_hash': digest(tasks), 'unit': access.unit, 'source_files': None}
    return panel


# ---- names and consent ---------------------------------------------------------------------------------------
def test_event_arm_mapping_and_unit_names(tmp_path):
    assert [reads.arm_of(e) for e in READ_ARMS] == ['C0', 'C', 'F', 'F', 'F', 'F', 'F']
    assert reads.unit_name('S3', 'officeqa') == 'test-read-S3-officeqa'
    assert reads.unit_name('C0', 'alfworld', smoke=True) == 'practice-read-C0-alfworld'
    assert reads.unit_dir(tmp_path, 'G', 'C', 'zebralogic') == tmp_path / 'G' / 'test-read-C-zebralogic'
    assert reads.status_path(tmp_path, 'D', 'S1', 'searchqa') == tmp_path / 'D' / 'read-status' / 'S1-searchqa.json'
    for bad in (('X', 'searchqa'), ('S1', 'livemath')):
        with pytest.raises(ValueError):
            reads.unit_name(*bad)
    with pytest.raises(ValueError):
        reads.unit_dir(tmp_path, 'E', 'S1', 'searchqa')


def test_consent_refuses_everything_but_the_exact_record(tmp_path):
    shared = tmp_path / 'shared'
    with pytest.raises(ValueError, match='consent'):
        reads.consent(shared)
    bad = [consent_value(extra=1), {k: v for k, v in consent_value().items() if k != 'note'},
           consent_value(multi_arm_arms=list(reversed(READ_ARMS))), consent_value(multi_arm_arms=list(READ_ARMS)[:-1]),
           consent_value(multi_arm_arms=list(READ_ARMS) + ['I']), consent_value(by='operator'),
           consent_value(test_evaluation=False), consent_value(sheet_test_qualification=False),
           consent_value(sheet_test_qualification=1), consent_value(note='  '), consent_value(date='')]
    for n, value in enumerate(bad):
        where = tmp_path / ('bad%d' % n)
        units.write_json(where / 'consent.json', value)
        with pytest.raises(ValueError):
            reads.consent(where)
    write_consent(shared)
    assert reads.consent(shared) == consent_value()


# ---- panel_tasks ----------------------------------------------------------------------------------------------
def test_panel_tasks_refuses_without_consent_and_registers_the_panel(tmp_path):
    shared, seen = tmp_path / 'shared', []
    panel = fake_panel('searchqa', seen=seen)
    with pytest.raises(ValueError, match='consent'):
        reads.panel_tasks(shared, {'x': 1}, 'searchqa', 'G/test-read-C0-searchqa', runtime={}, native=None,
                          evidence='engineering_fixture', run='r1', panel=panel)
    assert seen == []  # no TestAccess exists before the consent passed
    write_consent(shared)
    with pytest.raises(ValueError, match='test-read'):  # the access label must be a sealed read unit
        reads.panel_tasks(shared, {'x': 1}, 'searchqa', 'G/s1/outcomes', runtime={}, native=None,
                          evidence='engineering_fixture', run='r1', panel=panel)
    assert seen == []
    tasks = reads.panel_tasks(shared, {'x': 1}, 'searchqa', 'G/test-read-C0-searchqa', runtime={}, native=None,
                              evidence='engineering_fixture', run='r1', panel=panel)
    assert [t['task_id'] for t in tasks] == ['searchqa-t%d' % i for i in range(4)]
    assert seen == [('searchqa', 'G/test-read-C0-searchqa', {'x': 1})]
    registry = json.loads((shared / 'test' / 'searchqa.json').read_text())
    assert registry['entry']['tasks'] == sorted(t['task_id'] for t in tasks) and registry['entry']['run'] == 'r1'
    assert registry['evidence'] == 'engineering_fixture'
    # the same panel again is fine; a different panel is refused by the write-once registry
    reads.panel_tasks(shared, {'x': 1}, 'searchqa', 'D/test-read-C0-searchqa', runtime={}, native=None,
                      evidence='engineering_fixture', run='r1', panel=panel)
    with pytest.raises(ValueError, match='differs'):
        reads.panel_tasks(shared, {'x': 1}, 'searchqa', 'D/test-read-C-searchqa', runtime={}, native=None,
                          evidence='engineering_fixture', run='r1', panel=fake_panel('searchqa', n=3))
    # ZebraLogic reads its separately pinned sealed panel; ALFWorld needs the in-memory reset for its views
    zebra_seen = []
    pinned = {'paths': {}, 'sha256': {}, 'zebralogic': {'path': '/x/sealed.json', 'sha256': 'a' * 64}}
    reads.panel_tasks(shared, pinned, 'zebralogic', 'G/test-read-C0-zebralogic', runtime={}, native=None,
                      evidence='engineering_fixture', run='r1', panel=fake_panel('zebralogic', seen=zebra_seen))
    assert zebra_seen[0][2] == pinned['zebralogic']
    with pytest.raises(ValueError, match='Zebra'):
        reads.panel_tasks(shared, {'paths': {}}, 'zebralogic', 'G/test-read-C-zebralogic', runtime={}, native=None,
                          evidence='engineering_fixture', run='r1', panel=fake_panel('zebralogic'))
    with pytest.raises(ValueError, match='reset'):
        reads.panel_tasks(shared, pinned, 'alfworld', 'G/test-read-C0-alfworld', runtime={}, native=None,
                          evidence='engineering_fixture', run='r1', panel=fake_panel('alfworld', game=True))
    observation = 'You are in the middle of a room.\n\nYour task is to: put a book on the desk.'
    games = reads.panel_tasks(shared, pinned, 'alfworld', 'G/test-read-C0-alfworld', runtime={}, native=None,
                              evidence='engineering_fixture', run='r1', panel=fake_panel('alfworld', game=True),
                              alfworld_views=lambda public: (observation, ['look', 'go to desk 1']))
    view = games[0]['public']['routing_view']
    assert view['task_text'] == 'put a book on the desk.' and view['admissible_commands_at_reset'] == ['look', 'go to desk 1']
    assert games[0]['public']['routing_view_sha256'] == digest(view)
    assert not any('routing_view' in p.read_text() for p in shared.rglob('*.json'))  # views stay in memory


def test_panel_tasks_filters_spreadsheetbench_by_the_test_qualification(tmp_path, monkeypatch):
    shared = tmp_path / 'shared'
    write_consent(shared)
    seen = {}

    def qualification(shared_dir, tasks, runtime, *, allowed, native, workers, evidence):
        seen.update(shared=shared_dir, runtime=runtime, allowed=allowed, native=native, workers=workers, evidence=evidence)
        ids = [t['task_id'] for t in tasks]
        return {'side': 'test', 'task_hashes': {t['task_id']: digest(t) for t in tasks}, 'qualified': [ids[0], ids[2]]}
    monkeypatch.setattr(evaluation, '_sheet_qualification', qualification)
    native = object()
    tasks = reads.panel_tasks(shared, {'paths': {}}, 'spreadsheetbench', 'G/test-read-S1-spreadsheetbench',
                              runtime={'spreadsheetbench': {'spreadsheet_scorer': 'x'}}, native=native,
                              evidence='engineering_fixture', run='r1', panel=fake_panel('spreadsheetbench'))
    assert [t['task_id'] for t in tasks] == ['spreadsheetbench-t0', 'spreadsheetbench-t2']
    assert seen['workers'] == 2 and seen['native'] is native and seen['allowed'] == consent_value()
    assert seen['runtime'] == {'spreadsheet_scorer': 'x'} and seen['shared'] == shared
    monkeypatch.setattr(evaluation, '_sheet_qualification', lambda *a, **k: {'side': 'test', 'task_hashes': {}, 'qualified': []})
    with pytest.raises(ValueError, match='other items'):
        reads.panel_tasks(shared, {'paths': {}}, 'spreadsheetbench', 'G/test-read-S2-spreadsheetbench',
                          runtime={'spreadsheetbench': {}}, native=native, evidence='engineering_fixture', run='r1',
                          panel=fake_panel('spreadsheetbench'))


# ---- read_panel ------------------------------------------------------------------------------------------------
def practice_items(bench, n=4):
    return [{'benchmark': bench, 'task_id': '%s-p%d' % (bench, i), 'part': 'train',
             'public': {'question': 'practice question %d?' % i, 'context': 'practice context %d' % i},
             'private': {'answer': 'a%d' % i}} for i in range(n)]


class Fakes:
    """Fake mount / solve / embed / clients recording every call; replies carry a marker that must never leak."""

    def __init__(self, ledger):
        self.ledger = ledger
        self.mounts, self.solves, self.embeds, self.heavy, self.details, self.bases = [], [], [], [], [], []

    def embed(self, texts):
        self.embeds.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    def mount(self, bench, item, *, arm, typemap, library, vector, selector=None, view=None, base_card=None):
        assert view == item['public'], 'the read hands the mount the view it embedded (view_fn = the public part here)'
        assert base_card in ('format', 'historical'), 'typed-v2 step 5b: every read mount gets the base card (D17)'
        self.mounts.append((arm, item['task_id'], vector, selector is not None))
        self.bases.append(base_card)
        typed = arm == 'F'
        if selector is not None:  # the real mount makes the selection call through the selector recorder
            selector('select', 'index')
        return {'arm': arm, 'signature': 'question/context', 'type': 't01' if typed else None, 'source': 'src-1' if typed else None,
                'distance': 0.1 if typed else None, 'unknown_reason': None if typed else 'no_lookup',
                'card_skill': 'card-t01-s1' if typed else None, 'system_card_sha256': 'c' * 64,
                'programs_offered': ['grid-solver'] if typed else [],
                'selection': {'use': ['grid-solver'], 'status': 'ok', 'request_sha256': 'd' * 64, 'tokens': 7} if typed else None,
                'programs_enabled': ['prog-t01-s1-a'] if typed else [], 'card_text': 'CARD', 'system_card': 'CARD', 'enabled': []}

    def solve(self, bench, item, mounted, *, call, runtime, worker_factory, native, nominal_tokens, unit, tag, scorer_root,
              **extra):
        self.solves.append((bench, item['task_id'], mounted['arm'], unit, tag, str(scorer_root)))
        self.details.append({'extra': extra, 'nominal': nominal_tokens, 'tag': tag,
                             'worker': worker_factory() if worker_factory is not None else None})
        call('system', 'user ' + item['task_id'])
        number = int(item['task_id'][-1])
        token = 'unknown_fault' if number == 2 else 'pass' if number % 2 == 0 else 'fail'
        return {'bench': bench, 'item_id': item['task_id'], 'arm': mounted['arm'], 'reply': 'SECRET-REPLY-' + item['task_id'],
                'correct': token != 'fail',  # deliberately wrong for the unknown token: reads must make it None
                'token': token, 'tokens': call.tokens(), 'sends': call.sends,
                'request_sha256': [s['request_sha256'] for s in call.sends], 'failure': None,
                'configuration_error': False, 'infrastructure_unknown': call.infrastructure_unknown()}

    def client(self, system, user):
        return {'ok': True, 'response': 'SECRET-REPLY ' + user, 'finish_reason': 'stop',
                'usage': {'prompt_tokens': 50, 'completion_tokens': 10, 'total_tokens': 60}, 'error_type': None}

    def selection_client(self, system, user):
        return {'ok': True, 'response': '{"use": ["grid-solver"], "why": "grid"}', 'finish_reason': 'stop',
                'usage': {'prompt_tokens': 20, 'completion_tokens': 5, 'total_tokens': 25}, 'error_type': None}

    def call_factory(self, **kw):
        return units.CallRecorder(self.client, self.ledger, max_tokens=100, **kw)

    def selector_factory(self, **kw):
        return units.CallRecorder(self.selection_client, self.ledger, max_tokens=50, **kw)

    @contextlib.contextmanager
    def heavy_lock(self, bench, unit=None):  # chain.Services.heavy(bench, unit=None)
        self.heavy.append(bench)
        yield

    def read(self, root, event, bench, **extra):
        return reads.read_panel(root, 'G', event, bench, library=object(), typemap=object(), mount_fn=self.mount,
                                solve_fn=self.solve, embed=self.embed, call_factory=self.call_factory, worker_factory=None,
                                native=None, ledger=self.ledger, widths={bench: 3, 'alfworld': 2}, runtime={bench: {}},
                                nominal_tokens=None, selector_factory=self.selector_factory, heavy=self.heavy_lock, **extra)


def assert_no_pass_counts(value):
    if isinstance(value, dict):
        assert not ({'correct', 'incorrect', 'pass', 'fail', 'reply', 'item_ids'} & set(value))
        for child in value.values():
            assert_no_pass_counts(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_pass_counts(child)


def files_with(root, marker, *, exclude):
    return sorted(str(p) for p in Path(root).rglob('*') if p.is_file() and not str(p).startswith(str(exclude))
                  and marker in p.read_text(encoding='utf-8', errors='replace'))


def test_read_panel_smoke_seals_cells_and_mirrors_counts_only(tmp_path):
    root = tmp_path / 'execskill-20261110-typed-v3-smoke'
    ledger = units.Ledger(root / 'G' / 'ledger.json', 10 ** 7)
    fakes = Fakes(ledger)
    items = practice_items('searchqa')
    status = fakes.read(root, 'S2', 'searchqa', items=items, smoke=True, view_fn=lambda bench, item: item['public'])
    unit = root / 'G' / 'practice-read-S2-searchqa'
    assert unit.is_dir() and len(list((unit / 'cells').glob('*.json'))) == 4 and (unit / 'done.json').exists()
    # one embedder batch with every public text, before any cell; the F arm mounted every item with its vector and selector
    assert fakes.embeds == [[item['public']['question'] + '\n' + item['public']['context'] for item in items]]
    assert sorted(fakes.mounts) == sorted(('F', item['task_id'], [1.0, 0.0], True) for item in items)
    assert all(s[2] == 'F' and s[3] == 'practice-read-S2-searchqa' and s[5] == str(unit / 'transient') for s in fakes.solves)
    assert fakes.heavy == ['searchqa'] * 4  # the memory lock is held per cell, never around the whole unit
    # the sealed aggregate holds the pass counts; the unknown token is never scored as wrong
    sealed = json.loads((unit / 'aggregate.json').read_text())
    arm = sealed['by_arm']['F']
    assert (arm['n'], arm['correct'], arm['incorrect'], arm['unknown']) == (4, 1, 2, 1)
    assert arm['unknown_by_kind'] == {'unknown_fault': 1} and arm['items'] == sorted(i['task_id'] for i in items)
    assert arm['tokens'] == {'solver': 240, 'selection': 100, 'total': 340}
    assert arm['mount']['typed'] == 4 and arm['mount']['selection_calls'] == 4 and arm['mount']['enabled_total'] == 4
    assert len(arm['request_sha256']) == 4 and len(arm['selection_request_sha256']) == 4
    cell = json.loads(next((unit / 'cells').glob('*.json')).read_text())
    assert (cell['solver_tokens'], cell['selection_tokens'], cell['tokens']) == (60, 25, 85) and cell['event'] == 'S2'
    assert len(cell['sends']) == 1 and len(cell['selection_sends']) == 1  # the selection call is kept apart
    assert cell['selection_sends'][0]['request_sha256'] == cell['selection_request_sha256'][0] != cell['request_sha256'][0]
    assert cell['infrastructure_unknown'] is False and cell['selection_infrastructure_unknown'] is False
    assert set(reads.MOUNT_KEYS) <= set(cell['mount']) and 'card_text' not in cell['mount']
    # the open mirror: counts only, no pass count, no text; and it is what read_panel returned
    mirror_path = root / 'G' / 'read-status' / 'S2-searchqa.json'
    mirror = json.loads(mirror_path.read_text())
    assert mirror == status and mirror['status'] == 'complete' and mirror['cells'] == 4 and mirror['unknown'] == 1
    assert mirror['unknown_by_kind'] == {'unknown_fault': 1} and mirror['tokens']['total'] == 340
    assert mirror['mount']['typed_fraction'] == 1.0 and mirror['arm'] == 'F' and mirror['smoke'] is True
    assert_no_pass_counts(mirror)
    assert 'SECRET-REPLY' not in mirror_path.read_text() and 'searchqa-p' not in mirror_path.read_text()
    # no reply text anywhere outside the unit directory (the ledger, the mirror, done.json's copy of the ledger)
    assert files_with(root, 'SECRET-REPLY', exclude=unit) == []
    assert files_with(root, 'SECRET-REPLY', exclude=root / 'nowhere') != []  # it does live inside the unit
    # a done unit is returned from disk: no mount, solve, embed or call again
    fakes.mounts.clear(); fakes.solves.clear(); fakes.embeds.clear()
    again = fakes.read(root, 'S2', 'searchqa', items=items, smoke=True, view_fn=lambda bench, item: item['public'])
    assert again == status and fakes.mounts == [] and fakes.solves == [] and fakes.embeds == []
    # the mirror is rebuilt from the sealed cells when it is missing
    mirror_path.unlink()
    rebuilt = fakes.read(root, 'S2', 'searchqa', items=items, smoke=True, view_fn=lambda bench, item: item['public'])
    assert rebuilt['cells'] == 4 and rebuilt['unknown'] == 1 and fakes.solves == [] and mirror_path.exists()


def test_read_panel_anchor_events_mount_their_own_arm_without_embedding(tmp_path):
    root = tmp_path / 'execskill-20261110-typed-v3-smoke'
    fakes = Fakes(units.Ledger(root / 'G' / 'ledger.json', 10 ** 7))
    items = practice_items('officeqa', 3)
    for event in ('C0', 'C'):
        fakes.mounts.clear()
        status = fakes.read(root, event, 'officeqa', items=items, smoke=True, view_fn=lambda bench, item: item['public'])
        assert {m[0] for m in fakes.mounts} == {event} and all(m[2] is None and m[3] is False for m in fakes.mounts)
        assert fakes.embeds == [] and status['arm'] == event and status['mount']['typed'] == 0
        assert (root / 'G' / ('practice-read-%s-officeqa' % event) / 'aggregate.json').exists()
    with pytest.raises(ValueError, match='smoke'):
        fakes.read(root, 'C0', 'officeqa', items=items, smoke=False)
    with pytest.raises(ValueError, match='smoke'):
        fakes.read(root, 'C0', 'officeqa', items=None, smoke=True)


def sealed_code(**machinery_changes):
    """The code identity a loadable manifest seals (step 1b): a well-formed machinery record carrying this code's
    list pins, and a typed code identity (fixture values; ``chain.start_checks`` compares them at a real start)."""
    record = {'snapshot': '/x/snapshot', 'bound': True, 'typed_from': '/x/typed-code', 'list': machinery.LIST,
              'list_sha256': machinery.LIST_SHA256, 'files': machinery.LIST_FILES,
              'data_list_sha256': machinery.DATA_LIST_SHA256, 'symbols': 145, **machinery_changes}
    return {'machinery_code': record, 'provenance': {'typed_code': {'files': 20, 'sha256_list_sha256': 'c' * 64}}}


def minimal_manifest(root, **extra):
    # typed-v2: a loadable manifest also seals the code constants (caps, draw keys, read and learning widths) and the
    # code identity (machinery_code, provenance.typed_code); step 6s: and the schedule and the memory lock (DESIGN 3.6)
    fields = {'version': 'typed-v3', 'configuration': 'typed-v3', 'root': str(root), 'evidence': 'engineering_fixture',
              'route_b_evidence': 'engineering_fixture', 'pinned': {'paths': {}, 'sha256': {}},
              **prepare.sealed_constants(), **sealed_code(), 'base_card': 'format',  # step 5b: the base card
              'schedule': 'interleaved', 'memory_lock': 'per_cell_plain',
              'read_plan': 'full', **extra}  # step rp-int: a loadable manifest seals its read plan (read-plan R3)
    record = prepare.seal(fields)
    units.write_json(root / 'manifest.json', record)
    return record


def test_read_panel_real_path_needs_consent_and_opens_the_panel_in_a_sealed_unit(tmp_path):
    root = tmp_path / 'execskill-20261110-typed-v3'
    record = minimal_manifest(root)
    fakes = Fakes(units.Ledger(root / 'G' / 'ledger.json', 10 ** 7))
    seen = []
    panel = fake_panel('searchqa', seen=seen)
    with pytest.raises(ValueError, match='consent'):
        fakes.read(root, 'C0', 'searchqa', panel=panel, view_fn=lambda bench, item: item['public'])
    assert seen == [] and fakes.mounts == [] and not (root / 'G' / 'test-read-C0-searchqa').exists()
    write_consent(root / 'shared')
    status = fakes.read(root, 'C0', 'searchqa', panel=panel, view_fn=lambda bench, item: item['public'])
    assert seen == [('searchqa', 'G/test-read-C0-searchqa', record['pinned'])]
    unit = root / 'G' / 'test-read-C0-searchqa'
    assert unit.is_dir() and status['cells'] == 4 and status['unit'] == 'test-read-C0-searchqa' and status['smoke'] is False
    registry = json.loads((root / 'shared' / 'test' / 'searchqa.json').read_text())
    assert registry['entry']['run'] == record['record_sha256'] and registry['evidence'] == 'engineering_fixture'
    assert files_with(root, 'SECRET-REPLY', exclude=unit) == []
    with pytest.raises(ValueError):  # a learning-side writer can never touch the sealed unit
        units.write_json(unit / 'note.json', {})
    # the S<k> event reads the F arm on the same registered panel, embedding it once
    status = fakes.read(root, 'S1', 'searchqa', panel=panel, view_fn=lambda bench, item: item['public'])
    assert status['arm'] == 'F' and len(fakes.embeds) == 1 and len(fakes.embeds[0]) == 4


def test_panel_tasks_accepts_the_typed_evidence_twin(tmp_path):
    shared = tmp_path / 'shared'
    write_consent(shared)
    reads.panel_tasks(shared, {}, 'officeqa', 'G/test-read-S1-officeqa', runtime={}, native=None, evidence='typed_v3_smoke',
                      run='r', panel=fake_panel('officeqa'))
    assert json.loads((shared / 'test' / 'officeqa.json').read_text())['evidence'] == 'smoke'
    assert reads.route_b_evidence('typed_v3_real_run') == 'pilot_real_run' == reads.route_b_evidence('pilot_real_run')
    with pytest.raises(ValueError, match='evidence'):
        reads.route_b_evidence('main_v10_real_run')


def services_for(root, fakes, *, mode, items=None, slices=None, manifest=None):
    """The one fake ``chain.Services`` of this file (every field of every area, the read-relevant ones faked; the
    learning-side callables are None): recorders built as ``chain.solver_call`` builds them (no allow_sealed),
    ``heavy(bench, unit=None)``, no machinery record, no container scope, no lock setting, the default limits."""
    def solver_call(bench, unit, tag, *, transform=None, purpose='solve'):
        name = tag if purpose == 'solve' else '%s-%s' % (tag, purpose)
        client = fakes.client if purpose == 'solve' else fakes.selection_client
        return units.CallRecorder(client, fakes.ledger, max_tokens=100, tag=tag, unit=unit,
                                  out_path=root / 'G' / unit / 'calls' / (name + '.json'), transform=transform)
    # typed-v2 step 5b: a manifest names its base card (addendum D17); the fake one names the code default
    return chain.Services(manifest=manifest or {'base_card': 'format'}, root=root, chain='G', mode=mode, items=items or {},
                          slices=slices or {}, runtime={bench: {} for bench in ORDER}, embed=fakes.embed,
                          solver_call=solver_call, role_call=None,
                          worker_factory=lambda bench, unit, tag: (lambda: 'worker:' + tag), native=None,
                          heavy=fakes.heavy_lock, mount_fn=fakes.mount, solve_fn=fakes.solve,
                          view_fn=lambda bench, item: item['public'], write_card=None, propose_programs=None,
                          describe=None, outcomes_for_writer=None, nominal_tokens=lambda bench: 7, ledger=fakes.ledger,
                          limits=dict(chain.DEFAULT_LIMITS), cap=None, machinery_code=None, container_scope=None,
                          lock_setting=None)


def test_read_panel_services_form_adapts_the_chain_services(tmp_path):
    root = tmp_path / 'execskill-20261110-typed-v3-smoke'
    fakes = Fakes(units.Ledger(root / 'G' / 'ledger.json', 10 ** 7))
    items = practice_items('searchqa', 6)
    ids = [item['task_id'] for item in items]
    services = services_for(root, fakes, mode='smoke', items={'searchqa': items},
                            slices={'searchqa': {'learn': ids[:2], 'gate': ids[2:4], 'panel': ids[4:]}})
    status = reads.read_panel(root, 'G', 'S1', 'searchqa', library=object(), typemap=object(), services=services)
    unit = root / 'G' / 'practice-read-S1-searchqa'
    assert status['cells'] == 2 and {m[1] for m in fakes.mounts} == set(ids[4:]) and status['arm'] == 'F'
    assert all(d['extra'] == {'mode': 'smoke'} and d['nominal'] == 7 and d['worker'] == 'worker:' + d['tag'] for d in fakes.details)
    assert fakes.heavy == ['searchqa'] * 2  # the chain's lock, held per cell by the read itself
    assert len(list((unit / 'calls').glob('*.json'))) == 4  # a solve and a selection record per cell, inside the unit
    assert status['tokens'] == {'solver': 120, 'selection': 50, 'total': 170}
    with pytest.raises(ValueError, match='panel slice'):
        reads.read_panel(root, 'G', 'S1', 'officeqa', library=object(), typemap=object(),
                         services=services_for(root, fakes, mode='smoke', items={'officeqa': items},
                                               slices={'officeqa': {'learn': ids[:2], 'gate': ids[2:4]}}))
    # run mode: consent, the real panel path, the chain's recorders admitted to the sealed unit
    run_root = tmp_path / 'execskill-20261110-typed-v3'
    record = minimal_manifest(run_root)
    runner = Fakes(units.Ledger(run_root / 'G' / 'ledger.json', 10 ** 7))
    services = services_for(run_root, runner, mode='run', manifest=record)
    with pytest.raises(ValueError, match='consent'):
        reads.read_panel(run_root, 'G', 'C0', 'searchqa', library=object(), typemap=object(), services=services,
                         panel=fake_panel('searchqa'))
    write_consent(run_root / 'shared')
    status = reads.read_panel(run_root, 'G', 'C0', 'searchqa', library=object(), typemap=object(), services=services,
                              panel=fake_panel('searchqa'))
    unit = run_root / 'G' / 'test-read-C0-searchqa'
    assert status['cells'] == 4 and len(list((unit / 'calls').glob('*.json'))) == 4 and status['smoke'] is False
    assert all(d['extra'] == {'mode': 'run'} for d in runner.details) and runner.embeds == []
    assert files_with(run_root, 'SECRET-REPLY', exclude=unit) == []
    registry = json.loads((run_root / 'shared' / 'test' / 'searchqa.json').read_text())
    assert registry['entry']['run'] == record['record_sha256']
    # ALFWorld: the views come from a reset the chain must supply (its episodes pool); the pool reaches solve
    observation = 'You are in a room.\n\nYour task is to: put a book on the desk.'
    with pytest.raises(ValueError, match='reset'):
        reads.read_panel(run_root, 'G', 'C0', 'alfworld', library=object(), typemap=object(), services=services,
                         panel=fake_panel('alfworld', game=True))
    services.episodes = SimpleNamespace(hold=contextlib.nullcontext)
    status = reads.read_panel(run_root, 'G', 'C0', 'alfworld', library=object(), typemap=object(), services=services,
                              panel=fake_panel('alfworld', game=True), alfworld_views=lambda public: (observation, ['look']))
    assert status['cells'] == 4 and runner.details[-1]['extra'] == {'mode': 'run', 'episodes': services.episodes}
    assert not any('routing_view' in p.read_text() for p in (run_root / 'shared').rglob('*.json'))


def test_read_panel_drains_the_unit_and_deletes_the_transient_scorer_store(tmp_path, monkeypatch):
    """SpreadsheetBench test reads score under <unit>/transient (the scorer artifacts hold recalculated test
    reference workbooks): the store is deleted once the aggregate is sealed, with a deletion manifest; the unit's
    containers are drained after the cells; the test qualification runs under the memory lock."""
    root = tmp_path / 'execskill-20261110-typed-v3'
    record = minimal_manifest(root)
    write_consent(root / 'shared')
    fakes = Fakes(units.Ledger(root / 'G' / 'ledger.json', 10 ** 7))
    real_solve = fakes.solve

    def scoring_solve(bench, item, mounted, *, scorer_root, **kw):
        artifact = Path(scorer_root) / 'host_only' / 'scorer_artifacts' / ('pos-' + item['task_id']) / 'reference.xlsx'
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b'SECRET-REFERENCE-WORKBOOK')
        return real_solve(bench, item, mounted, scorer_root=scorer_root, **kw)
    fakes.solve = scoring_solve
    monkeypatch.setattr(evaluation, '_sheet_qualification', lambda shared, tasks, runtime, **kw: {
        'side': 'test', 'task_hashes': {t['task_id']: digest(t) for t in tasks}, 'qualified': [t['task_id'] for t in tasks]})
    drains = []
    services = services_for(root, fakes, mode='run', manifest=record)
    services.drain = lambda unit: drains.append(unit) or {'cleanups': [], 'starts': []}
    status = reads.read_panel(root, 'G', 'C0', 'spreadsheetbench', library=object(), typemap=object(), services=services,
                              panel=fake_panel('spreadsheetbench'))
    unit = root / 'G' / 'test-read-C0-spreadsheetbench'
    assert status['status'] == 'complete' and status['cells'] == 4
    assert fakes.heavy == ['spreadsheetbench'] * 5  # the qualification, then one hold per cell
    assert not (unit / 'transient').exists() and files_with(root, 'SECRET-REFERENCE-WORKBOOK', exclude=root / 'nowhere') == []
    deleted = json.loads((unit / 'transient-deleted.json').read_text())
    assert deleted['files'] == 4 and len(deleted['manifest_sha256']) == 64 and 'SECRET' not in json.dumps(deleted)
    assert drains == ['test-read-C0-spreadsheetbench'] and json.loads((unit / 'drain.json').read_text())['result'] == {'cleanups': [], 'starts': []}
    # a drain failure after the cells is recorded in the unit and raised to the chain
    services.drain = lambda unit: (_ for _ in ()).throw(RuntimeError('containers remain'))
    with pytest.raises(RuntimeError):
        reads.read_panel(root, 'G', 'C', 'spreadsheetbench', library=object(), typemap=object(), services=services,
                         panel=fake_panel('spreadsheetbench'))
    assert json.loads((root / 'G' / 'test-read-C-spreadsheetbench' / 'drain.json').read_text())['error'] == 'RuntimeError'


def test_read_panel_cell_raising_on_a_later_item_is_incomplete_and_reopened_on_resume(tmp_path):
    root = tmp_path / 'execskill-20261110-typed-v3-smoke'
    fakes = Fakes(units.Ledger(root / 'G' / 'ledger.json', 10 ** 7))
    items = practice_items('searchqa')
    real_solve = fakes.solve
    broken = {'on': True}

    def solve(bench, item, mounted, **kw):
        if broken['on'] and item['task_id'] == 'searchqa-p3':
            raise KeyError('searchqa-p3')
        return real_solve(bench, item, mounted, **kw)
    fakes.solve = solve
    status = fakes.read(root, 'S1', 'searchqa', items=items, smoke=True, view_fn=lambda bench, item: item['public'])
    unit = root / 'G' / 'practice-read-S1-searchqa'
    assert status['status'] == 'incomplete' and status['missing_cells'] == 1 and status['unsubmitted'] == 1 and status['stop_reason'] is None
    assert len(list((unit / 'cells').glob('*.json'))) == 3 and len(list((unit / 'unsubmitted').glob('*.json'))) == 1
    sealed = json.loads((unit / 'aggregate.json').read_text())
    assert sealed['missing_cells'] == 1 and sealed['unsubmitted'] == 1 and sealed['by_arm']['F']['n'] == 3
    # without resume the stopped unit is reported as it stands; with resume it is reopened and only p3 is solved
    again = fakes.read(root, 'S1', 'searchqa', items=items, smoke=True, view_fn=lambda bench, item: item['public'])
    assert again == status
    broken['on'] = False
    solves = len(fakes.solves)
    done = fakes.read(root, 'S1', 'searchqa', items=items, smoke=True, view_fn=lambda bench, item: item['public'], resume=True)
    assert done['status'] == 'complete' and done['cells'] == 4 and done['missing_cells'] == 0
    assert [s[1] for s in fakes.solves[solves:]] == ['searchqa-p3'] and (unit / 'done-stopped-1.json').exists()


# ---- prepare ----------------------------------------------------------------------------------------------------
def write_pools(root):
    """Fake pinned practice pools in the shape manifest._items loads (ALFWorld: half the games carry a view)."""
    pools = root / 'pools'
    pools.mkdir()
    record = {'pools': {}}
    for bench in ('searchqa', 'officeqa', 'spreadsheetbench', 'alfworld'):
        items = []
        for i in range(16):
            public, private = {'question': 'q%d' % i, 'context': 'c%d' % i}, {'answer': 'a%d' % i}
            item = {'benchmark': bench, 'task_id': '%s-%02d' % (bench, i), 'part': 'train'}
            if bench == 'spreadsheetbench':
                public = {'instruction': 'fill %d' % i, 'input_files': ['/x/in%d.xlsx' % i], 'answer_position': 'A1'}
                private = {'answer_position': 'A1', 'test_files': ['/x/ref%d.xlsx' % i]}
            if bench == 'alfworld':
                public = {'game_file': '/x/json_2.1.1/train/pick-Mug-None-Shelf-3%02d/trial_T1/game.tw-pddl' % i}
                if i % 2 == 0:
                    view = {'initial_observation': 'room %d' % i, 'admissible_commands_at_reset': ['look'], 'task_text': 'put'}
                    public.update(routing_view=view, routing_view_sha256=digest(view))
                item['room'] = '3%02d' % i
            items.append({**item, 'public': public, 'private': private})
        path = pools / (bench + '.json')
        path.write_text(json.dumps(items))
        record['pools'][bench] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (pools / 'pools.json').write_text(json.dumps(record))
    return pools


def zebra_rows(n=12):
    """Normalized-looking ZebraLogic pool rows, one of them a registered excluded id."""
    ids = ['lgp-test-5x3-8'] + ['lgp-pool-5x2-%d' % i for i in range(n - 1)]
    return [{'benchmark': 'zebralogic', 'task_id': i, 'task': '5*2', 'partition': 'pool', 'family_id': 'zebralogic:' + i,
             'public': {'question': 'There are 5 houses %s' % i, 'columns': ['Name', 'Drink']}, 'private': {'answer': {}}}
            for i in ids]


def write_machinery(path):
    value = {'configuration': 'main-v10', 'record_sha256': 'a' * 64, 'evidence': 'smoke',
             'runtime': {b: {'prompt_layout': 'contract-first-v2', 'bench': b} for b in ORDER},
             'data': {'pinned': {'paths': {'test': {'searchqa': '/x/final/searchqa.json'}}, 'sha256': {},
                                 'zebralogic': {'path': '/x/sealed-holdout.json', 'sha256': 'b' * 64}},
                      'pools': {b: {'path': '/x/%s.json' % b, 'sha256': 'c' * 64} for b in ORDER}},
             'sandbox': {'limits': {'cell': {}}, 'measured': {'native_peak_rss_kib': 1}, 'image_id': 'sha256:' + 'd' * 64},
             'slot_root': '/x/slots', 'history_root': '/x/history',
             'provenance': {'snapshot_root': '/x/snapshot', 'git_head': 'e' * 40}}
    path.write_text(json.dumps(value))
    return value


def write_tree(root):
    tree = root / 'tree'
    for name in ('skillopt', 'scripts', 'tests'):
        (tree / name).mkdir(parents=True)
        (tree / name / 'module.py').write_text('# %s\n' % name)
    (tree / '.git' / 'refs' / 'heads').mkdir(parents=True)
    (tree / '.git' / 'HEAD').write_text('ref: refs/heads/typed\n')
    (tree / '.git' / 'refs' / 'heads' / 'typed').write_text('f' * 40 + '\n')
    return tree


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(zebralogic, 'load_pool', lambda *a, **k: zebra_rows())
    machinery = tmp_path / 'machinery.json'
    return {'pools': write_pools(tmp_path), 'machinery': machinery, 'value': write_machinery(machinery),
            'tree': write_tree(tmp_path), 'parent': tmp_path}


def test_check_root_refuses_forbidden_roots(tmp_path):
    good = prepare.check_root('/data/execskill-20261110-typed-v3')
    assert good == Path('/data/execskill-20261110-typed-v3') and not good.exists()
    assert prepare.check_root('/data/execskill-20261110-typed-v3-smoke', smoke=True).name.endswith('-smoke')
    with pytest.raises(ValueError, match='absolute'):
        prepare.check_root('execskill-20261110-typed-v3')
    # typed-v2 roots only (the pin flipped with the version): typed-v1 and typed-v3 names are refused by name
    for bad in ('/data/execskill-2026111-typed-v3', '/data/execskill-20261110-typed-v1', '/data/execskill-20261110-typed-v1-smoke',
                '/data/execskill-20261110-typed-v2', '/data/execskill-20261109-main-v10'):
        with pytest.raises(ValueError, match='named'):
            prepare.check_root(bad, smoke=bad.endswith('-smoke'))
    with pytest.raises(ValueError, match='smoke'):
        prepare.check_root('/data/execskill-20261110-typed-v3-smoke')
    with pytest.raises(ValueError, match='smoke'):
        prepare.check_root('/data/execskill-20261110-typed-v3', smoke=True)
    with pytest.raises(ValueError, match='directly under'):
        prepare.check_root(str(tmp_path / 'execskill-20261110-typed-v3'))
    main_v10 = profiles.RUN_ROOTS['main-v10']
    with pytest.raises(ValueError, match='route-B run root'):
        prepare.check_root(main_v10 + '/execskill-20261110-typed-v3', parent=main_v10)
    never = profiles.NEVER_WRITTEN[0]
    with pytest.raises(ValueError, match='route-B run root'):
        prepare.check_root(never + '/execskill-20261110-typed-v3', parent=never)
    existing = tmp_path / 'execskill-20261110-typed-v3'
    existing.mkdir()
    with pytest.raises(ValueError, match='new'):
        prepare.check_root(str(existing), parent=str(tmp_path))


def test_prepare_writes_a_sealed_manifest_with_disjoint_deterministic_slices(inputs):
    parent = inputs['parent']
    root = parent / 'execskill-20261110-typed-v3-smoke'
    made = prepare.prepare(root, machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                           smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    assert (root / 'manifest.json').exists() and all((root / d).is_dir() for d in ('shared', 'G', 'D'))
    assert made['configuration'] == 'typed-v3' and made['machinery'] == 'main-v10' and made['smoke'] is True
    assert made['evidence'] == 'typed_v3_smoke' and made['route_b_evidence'] == 'smoke' and made['arms'] == list(READ_ARMS)
    for bench in ORDER:
        slices = made['slices'][bench]
        assert set(slices) == {'learn', 'gate', 'panel'}
        assert [len(slices[n]) for n in ('learn', 'gate', 'panel')] == [SMOKE_SLICES[bench][n] for n in ('learn', 'gate', 'panel')]
        assert not (set(slices['learn']) & set(slices['gate'])) and not (set(slices['panel']) & set(slices['learn']) | set(slices['gate']) & set(slices['panel']))
    assert 'lgp-test-5x3-8' not in sum(made['slices']['zebralogic'].values(), [])  # EXCLUDED_IDS stay out
    assert made['pools']['zebralogic']['items'] == 11 and made['pools']['zebralogic']['path'] == zebralogic.POOL_PATH
    assert made['pools']['alfworld']['items'] == 8  # only games with a registered routing view
    assert all(int(i[-2:]) % 2 == 0 for i in sum(made['slices']['alfworld'].values(), []))
    assert made['cards']['zebralogic'] == zebralogic.CARD_TEXT and len(made['cards']['searchqa']) > 100
    assert made['clients'] == {'roles_repo': '/root/roles', 'northgate_env': '/root/.config/weak-solver/northgate.env'}
    assert made['pinned'] == inputs['value']['data']['pinned'] and set(made['runtime']) == set(ORDER)
    assert made['slot_root'] == '/x/slots' and made['provenance']['machinery'] == inputs['value']['provenance']
    assert made['provenance']['typed_tree']['git_head'] == 'f' * 40 and made['provenance']['typed_tree']['files'] == 3
    assert made['caps'] == {'G': 150_000_000, 'D': 170_000_000} and made['seed'] == 20261110
    assert not any('secret' in str(v).lower() for v in made['clients'].values())
    loaded = prepare.load_manifest(root)
    assert loaded == made and loaded['record_sha256'] == made['record_sha256']
    # deterministic: a second preparation draws the same slices
    other = prepare.prepare(parent / 'execskill-20261111-typed-v3-smoke', machinery_manifest=inputs['machinery'],
                            roles_repo='/root/roles', pools_root=inputs['pools'], smoke=True, typed_tree=inputs['tree'],
                            root_parent=str(parent))
    assert other['slices'] == made['slices'] and other['record_sha256'] != made['record_sha256']
    # the root is write-once
    with pytest.raises(ValueError, match='new'):
        prepare.prepare(root, machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                        smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    # an edited manifest no longer verifies
    raw = json.loads((root / 'manifest.json').read_text())
    raw['slices']['searchqa']['gate'][0] = raw['slices']['searchqa']['learn'][0]
    (root / 'manifest.json').write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='hash'):
        prepare.load_manifest(root)
    raw.pop('record_sha256')
    (root / 'manifest.json').write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        prepare.load_manifest(root)


def test_prepare_run_mode_slices_and_pool_pins(inputs):
    parent = inputs['parent']
    root = parent / 'execskill-20261110-typed-v3'
    sizes = {bench: {'learn': 3, 'gate': 4} for bench in ORDER}
    made = prepare.prepare(root, machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                           slices=sizes, typed_tree=inputs['tree'], root_parent=str(parent))
    assert made['evidence'] == 'typed_v3_real_run' and made['route_b_evidence'] == 'pilot_real_run' and made['smoke'] is False
    assert all(set(made['slices'][b]) == {'learn', 'gate'} and len(made['slices'][b]['gate']) == 4 for b in ORDER)
    # run time loads the items again from the pinned file; a changed pin is refused
    items, provenance = prepare.load_pool('searchqa', inputs['pools'], {k: made['pools']['searchqa'][k] for k in ('path', 'sha256')})
    assert len(items) == 16 and provenance['sha256'] == made['pools']['searchqa']['sha256']
    with pytest.raises(ValueError, match='pin changed'):
        prepare.load_pool('searchqa', inputs['pools'], {'path': provenance['path'], 'sha256': '0' * 64})
    with pytest.raises(ValueError, match='pin changed'):
        prepare.load_pool('zebralogic', inputs['pools'], {'path': '/elsewhere.json', 'sha256': zebralogic.POOL_SHA256})
    with pytest.raises(ValueError):  # the registered sizes need pools the fakes do not have
        prepare.prepare(parent / 'execskill-20261112-typed-v3', machinery_manifest=inputs['machinery'], roles_repo='/r',
                        pools_root=inputs['pools'], typed_tree=inputs['tree'], root_parent=str(parent))
    with pytest.raises(ValueError, match='main-v10'):  # another configuration's manifest is not the machinery
        bad = parent / 'bad-machinery.json'
        bad.write_text(json.dumps({**inputs['value'], 'configuration': 'main-v9'}))
        prepare.read_machinery(bad)


def test_validate_items_refuses_test_side_parts_and_fields():
    good = [{'benchmark': 'searchqa', 'task_id': 'a', 'public': {'question': 'q'}, 'private': {'answer': 'x'}, 'part': 'train'}]
    assert prepare.validate_items(good, 'searchqa') == good
    for bad in ([{**good[0], 'part': 'holdout'}], [{**good[0], 'private': {'test_answer': 1}}], [good[0], good[0]],
                [{**good[0], 'benchmark': 'officeqa'}], []):
        with pytest.raises(ValueError):
            prepare.validate_items(bad, 'searchqa')
    sheet = [{'benchmark': 'spreadsheetbench', 'task_id': 's', 'public': {'instruction': 'i'},
              'private': {'test_files': ['/x/ref.xlsx']}, 'part': 'train'}]
    assert prepare.validate_items(sheet, 'spreadsheetbench') == sheet  # the only admitted test-named field
    drawn = prepare.draw_slices([{'task_id': 'i%d' % i} for i in range(10)], 'searchqa', sizes={'learn': 3, 'gate': 4})
    assert len(drawn['learn']) == 3 and len(drawn['gate']) == 4 and not set(drawn['learn']) & set(drawn['gate'])
    assert drawn == prepare.draw_slices([{'task_id': 'i%d' % i} for i in reversed(range(10))], 'searchqa', sizes={'learn': 3, 'gate': 4})
    with pytest.raises(ValueError, match='need'):
        prepare.draw_slices([{'task_id': 'i%d' % i} for i in range(5)], 'searchqa', sizes={'learn': 3, 'gate': 4})


# ---- typed-v2 step 6s: the one panel path (read-plan R24) and the lock of the ALFWorld resets (addendum D13) -------
def test_open_panel_gives_the_items_views_vectors_and_registry_calls_of_the_read(tmp_path, monkeypatch):
    """``open_panel`` is the panel part of ``_read``, taken out unchanged (R24): every read unit calls it once (the
    vectors for the F arm only), and called alone it opens the same panel with the same label under consent, writes
    the same registry entry, sorts the same items, builds the same views and one embedder batch over the same texts."""
    calls, real_open = [], reads.open_panel
    monkeypatch.setattr(reads, 'open_panel', lambda *a, **kw: calls.append((a[1:], kw['vectors'])) or real_open(*a, **kw))
    view = lambda bench, item: item['public']  # noqa: E731
    first = tmp_path / 'a' / 'execskill-20261110-typed-v3'
    minimal_manifest(first)
    write_consent(first / 'shared')
    fakes, seen = Fakes(units.Ledger(first / 'G' / 'ledger.json', 10 ** 7)), []
    held = []

    @contextlib.contextmanager
    def lock(bench, unit=None):
        held.append((bench, unit))
        yield
    status = reads.read_panel(first, 'G', 'S1', 'searchqa', library=object(), typemap=object(), mount_fn=fakes.mount,
                              solve_fn=fakes.solve, embed=fakes.embed, call_factory=fakes.call_factory,
                              worker_factory=None, native=None, ledger=fakes.ledger, widths={'searchqa': 3},
                              runtime={'searchqa': {}}, nominal_tokens=None, selector_factory=fakes.selector_factory,
                              heavy=lock, panel=fake_panel('searchqa', seen=seen), view_fn=view)
    assert status['status'] == 'complete' and calls == [(('G', 'searchqa', 'test-read-S1-searchqa'), True)]
    assert held == [('searchqa', 'test-read-S1-searchqa')] * 4  # every cell's hold names the read unit (DESIGN 3.6)
    fakes.read(first, 'C0', 'searchqa', panel=fake_panel('searchqa'), view_fn=view)
    assert calls[-1] == (('G', 'searchqa', 'test-read-C0-searchqa'), False)  # an anchor event embeds nothing
    second = tmp_path / 'b' / 'execskill-20261110-typed-v3'
    record = minimal_manifest(second)
    write_consent(second / 'shared')
    embeds, alone = [], []
    opened = real_open(second, 'G', 'searchqa', 'test-read-S1-searchqa', vectors=True, setup={
        'manifest': None, 'smoke': False, 'runtime': {'searchqa': {}}, 'view_fn': view, 'heavy': None,
        'panel': fake_panel('searchqa', seen=alone), 'embed': lambda texts: embeds.append(list(texts)) or [[1.0, 0.0]] * len(texts)})
    assert [unit for _, unit, _ in alone] == [unit for _, unit, _ in seen] == ['G/test-read-S1-searchqa']
    assert embeds == fakes.embeds and opened['manifest'] == record and opened['base_card'] == 'format'
    ids = sorted('searchqa-t%d' % i for i in range(4))
    assert opened['ids'] == ids == [item['task_id'] for item in opened['items']]
    assert opened['views'] == {item['task_id']: item['public'] for item in opened['items']}
    assert opened['vectors'] == {i: [1.0, 0.0] for i in ids} and sorted(m[1] for m in fakes.mounts if m[0] == 'F') == ids
    entries = [json.loads((root / 'shared' / 'test' / 'searchqa.json').read_text()) for root in (first, second)]
    assert [{k: v for k, v in e['entry'].items() if k != 'run'} for e in entries][0] == \
        {k: v for k, v in entries[1]['entry'].items() if k != 'run'}
    assert entries[1]['entry']['run'] == record['record_sha256']
    with opened['lock']('spreadsheetbench', 'any'):  # no heavy given: no lock
        pass
    # the smoke: injected held-out practice items, no consent, no manifest, no registry; a real opening never takes them
    items = practice_items('officeqa', 3)
    smoke_root = tmp_path / 'execskill-20261110-typed-v3-smoke'
    opened = real_open(smoke_root, 'G', 'officeqa', 'practice-read-C0-officeqa', vectors=False,
                       setup={'items': list(reversed(items)), 'smoke': True, 'view_fn': view})
    assert opened['ids'] == sorted(i['task_id'] for i in items) and opened['vectors'] == {} and opened['manifest'] is None
    assert opened['base_card'] == 'format' and not (smoke_root / 'shared').exists()
    with pytest.raises(ValueError, match='smoke'):
        real_open(smoke_root, 'G', 'officeqa', 'test-read-C0-officeqa', vectors=False, setup={'items': items, 'smoke': False})


def test_open_panel_holds_the_lock_with_the_unit_around_the_sheet_qualification(tmp_path, monkeypatch):
    root = tmp_path / 'execskill-20261110-typed-v3'
    record = minimal_manifest(root)
    write_consent(root / 'shared')
    held, qualified = [], []
    monkeypatch.setattr(evaluation, '_sheet_qualification', lambda shared, tasks, runtime, **kw: qualified.append(
        list(held)) or {'side': 'test', 'task_hashes': {t['task_id']: digest(t) for t in tasks},
                        'qualified': [t['task_id'] for t in tasks]})

    @contextlib.contextmanager
    def lock(bench, unit=None):
        held.append((bench, unit))
        yield
        held.remove((bench, unit))
    opened = reads.open_panel(root, 'G', 'spreadsheetbench', 'test-read-C0-spreadsheetbench', vectors=False, setup={
        'manifest': record, 'runtime': {'spreadsheetbench': {}}, 'view_fn': lambda bench, item: item['public'],
        'heavy': lock, 'panel': fake_panel('spreadsheetbench')})
    assert qualified == [[('spreadsheetbench', 'test-read-C0-spreadsheetbench')]] and held == []
    assert len(opened['items']) == 4 and opened['lock'] is lock


def test_the_alfworld_preparation_reset_is_locked_only_under_unit_shared(tmp_path, monkeypatch):
    """Addendum D13 (schedule-lock Q4): with per_cell_plain (lock_setting None) the read unit's ALFWorld preparation
    resets stay bare, as in typed-v1; with unit_shared each reset runs inside v218_lock's environment lock (shared,
    holder named <chain>/<unit>), the lock first and the episode slot inside, as main-v10 did."""
    slots = tmp_path / 'slots'
    order, wraps = [], []

    def fake_alfworld_reset(runtime, episodes):
        def reset(public):
            found = sorted(slots.glob('memory-heavy.lock.holder-*.json'))
            with episodes.hold():
                order.append(json.loads(found[0].read_text()) if found else None)
            return 'You are in a room.\n\nYour task is to: put a book on the desk.', ['look']
        return reset
    monkeypatch.setattr(evaluation, 'alfworld_reset', fake_alfworld_reset)
    real_call = v218_lock.call
    monkeypatch.setattr(v218_lock, 'call', lambda function, setting, *benches, **kw: wraps.append((benches, kw)) or
                        real_call(function, setting, *benches, **kw))
    run_root = tmp_path / 'execskill-20261110-typed-v3'
    record = minimal_manifest(run_root)
    write_consent(run_root / 'shared')
    runner = Fakes(units.Ledger(run_root / 'G' / 'ledger.json', 10 ** 7))
    services = services_for(run_root, runner, mode='run', manifest=record)
    services.episodes = SimpleNamespace(hold=contextlib.nullcontext)
    status = reads.read_panel(run_root, 'G', 'C0', 'alfworld', library=object(), typemap=object(), services=services,
                              panel=fake_panel('alfworld', game=True))
    assert status['cells'] == 4 and order == [None] * 4 and wraps == []  # bare: no lock, no wrap
    assert reads.preparation_reset(services, 'test-read-C0-alfworld').__name__ == 'reset'
    heavy, setting = chain.heavy_for({'memory_lock': 'unit_shared', 'slot_root': str(slots)}, run_root, 'G')
    services.heavy, services.lock_setting = heavy, setting
    order.clear()
    status = reads.read_panel(run_root, 'G', 'C', 'alfworld', library=object(), typemap=object(), services=services,
                              panel=fake_panel('alfworld', game=True))
    assert status['cells'] == 4 and wraps == [(('alfworld',), {'unit': 'G/test-read-C-alfworld'})]
    assert [(h['unit'], h['mode']) for h in order] == [('G/test-read-C-alfworld', 'shared')] * 4
    assert not list(slots.glob('memory-heavy.lock.holder-*.json'))
    services.episodes = None
    assert reads.preparation_reset(services, 'test-read-C-alfworld') is None
