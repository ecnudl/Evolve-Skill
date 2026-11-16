"""typed-v2 step 6s: schedule and memory lock (DESIGN 3.6; spec/schedule-lock.md Parts A and B, section 4 T1-T13;
addenda D9, D13; read-plan R24, R79).

Schedule: the sealed manifest field ``schedule`` ('interleaved', the code default: typed-v1's order; 'learn_first':
learn and freeze all five steps, then read C0, C, S1..S5 each from its own frozen files). Every freeze writes the
write-once receipt ``s<k>/frozen.json``; a read event starts only after ``load_frozen`` matched the files with it and
``bind_read`` recorded or compared ``state['read_mounts'][event]``. Lock: the sealed field ``memory_lock``
('per_cell_plain', the code default: typed-v1's call; 'unit_shared': route B's environment lock shared by the threads
of one unit, with the ALFWorld preparation resets of read units locked too).

Fakes only: no network, no Docker, no /data, no model call. Scratch under /tmp/typed2-neutral (resolved: route B's
``safe_path`` refuses a symlink in any parent, and /tmp is one on macOS).
"""
import ast
import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_typed
from skillopt.coevo5 import data
from skillopt.execskill import chain as route_b_chain, typed, v218_lock, zebralogic
from skillopt.execskill.typed import (ORDER, chain, library as library_, prepare, readout, readplan, reads, smoke,
                                      tasktypes, units)
from tests.test_typed2_base import Capture, cell_rows, exact_embedder, request_rows
from tests.test_typed_chain import FakeReads, build, recovery
from tests.test_typed_reads import (fake_panel, sealed_code, write_consent, write_machinery, write_pools, write_tree,
                                    zebra_rows)

NEUTRAL = Path('/tmp/typed2-neutral').resolve()
TREE = Path(run_typed.__file__).resolve().parents[1]
TIME_KEYS = {'at', 'accepted_at', 'updated', 'started', 'saved_at', 'frozen_at', 'created_at', 'seconds', 'applied_at',
             'bound_at', 'finished'}
EVENTS = ('C0', 'C', 'S1', 'S2', 'S3', 'S4', 'S5')


@pytest.fixture
def tmp_path():
    """A neutral, resolved directory: pytest's own tmp_path carries the word 'test' (refused by the sealed-path guard)."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='schedule-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(zebralogic, 'load_pool', lambda *a, **k: zebra_rows())
    machinery = tmp_path / 'machinery.json'
    return {'pools': write_pools(tmp_path), 'machinery': machinery, 'value': write_machinery(machinery),
            'tree': write_tree(tmp_path), 'parent': tmp_path}


# ---- helpers ----------------------------------------------------------------------------------------------------
def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in TIME_KEYS and k != 'ledger'}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def real_run(root, schedule, *, script=None, order=None, services=None, resume=False):
    """The chain through the REAL mount, writers and reads (scripted replies, exact axis embeddings, smoke limits)."""
    if services is None:
        script = script if script is not None else Capture()
        services = smoke.fake_services(root, 'G', smoke.synthetic_manifest(schedule=schedule), scripted=script)
        services.embed = exact_embedder
        services.slices = smoke.smoke_slices(services.items, services.slices)
        services.limits = dict(smoke.SMOKE_LIMITS)
        if order is not None:
            services.order = order
    state = chain.run(root, 'G', services=services, sleep=lambda s: None, resume=resume)
    return state, services.script, services


def fake_run(root, schedule, *, order=ORDER, reads=None, **kw):
    """The chain on the fake mount / writers / reads of tests/test_typed_chain.py, with the given schedule."""
    services, modules, script = build(root, order=order, reads=reads, **kw)
    services.manifest = {**services.manifest, 'schedule': schedule}
    return services, modules, script


def learning_units(done, k):
    return [unit for unit in done if unit.startswith('s%d/' % k)]


def read_units(done, event, order=ORDER):
    found = ['read-%s-%s' % (event, bench) for bench in order]
    assert all(unit in done for unit in found), event
    return found


def expected_done(done, schedule, order=ORDER):
    """The done units of a complete chain rebuilt from its own learning units in the schedule's order (S2, S3)."""
    steps = range(1, len(order) + 1)
    anchors = read_units(done, 'C0', order) + read_units(done, 'C', order) + ['step-0']
    if schedule == 'interleaved':
        rest = [unit for k in steps for unit in learning_units(done, k) + read_units(done, 'S%d' % k, order)
                + ['step-%d' % k]]
        return ['confirm'] + anchors + rest
    learning = [unit for k in steps for unit in learning_units(done, k)]
    reading = [unit for k in steps for unit in read_units(done, 'S%d' % k, order) + ['step-%d' % k]]
    return ['confirm'] + learning + anchors + reading


def receipt_of(root, k):
    return json.loads((Path(root) / 'G' / ('s%d' % k) / chain.FROZEN).read_text())


def file_sha(path):
    return chain._file_sha256(path)


def mounts_and_meta(root):
    """Per cell (unit, tag): its mount record and label; per read unit: its done.json meta and sealed aggregate
    (time keys and ledger snapshots stripped)."""
    base = Path(root) / 'G'
    cells, meta = {}, {}
    for path in sorted(base.rglob('cells/*.json')):
        unit = str(path.parent.parent.relative_to(base))
        row = json.loads(path.read_text())
        cells[(unit, path.stem)] = {'arm': row['arm'], 'mount': row.get('mount'), 'request': row.get('request_sha256'),
                                    'selection': row.get('selection_request_sha256')}
    for unit_dir in sorted(base.glob('practice-read-*')):
        meta[unit_dir.name] = {'done': strip(json.loads((unit_dir / 'done.json').read_text())),
                               'aggregate': strip(json.loads((unit_dir / 'aggregate.json').read_text()))}
    return cells, meta


def step_records(root, n=5):
    """Per step the decisions, the library and the type map, time keys and ledger snapshots stripped (S8); the
    library's own record hash goes too, because it covers the skills' time stamps (the type map's holds none)."""
    base = Path(root) / 'G'
    out = {}
    for k in range(1, n + 1):
        out[k] = {name: strip(json.loads((base / ('s%d' % k) / name).read_text()))
                  for name in ('decisions.json', 'library.json', 'typemap.json')}
        out[k]['library.json'].pop('record_sha256')
    return out


def sends(root):
    """The ledger's send count (0 while no ledger file was written: nothing was sent)."""
    path = Path(root) / 'G' / 'ledger.json'
    return json.loads(path.read_text())['sends'] if path.exists() else 0


def listing(path):
    path = Path(path)
    return sorted((str(p.relative_to(path)), p.stat().st_size, p.stat().st_mtime_ns) for p in path.rglob('*') if p.is_file())


# ---- T1: the sealed manifest fields ---------------------------------------------------------------------------------
def test_prepare_schedule_and_lock_fields(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    default = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', **common)
    assert (default['schedule'], default['memory_lock']) == ('interleaved', 'per_cell_plain')
    assert (typed.SCHEDULE_DEFAULT, typed.MEMORY_LOCK_DEFAULT) == ('interleaved', 'per_cell_plain')
    made = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', schedule='learn_first',
                           memory_lock='unit_shared', **common)
    assert (made['schedule'], made['memory_lock']) == ('learn_first', 'unit_shared')
    assert prepare.load_manifest(made['root']) == made and prepare.schedule_of(made) == 'learn_first'
    assert prepare.memory_lock_of(made) == 'unit_shared'
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    for key, value in (('schedule', 'interleaved'), ('memory_lock', 'per_cell_plain')):  # the hash covers both
        assert prepare.seal({**fields, key: value})['record_sha256'] != made['record_sha256']
    # an unknown value is refused before anything is written
    for bad in ({'schedule': 'economy'}, {'memory_lock': 'unit_exclusive'}, {'schedule': None}, {'memory_lock': 1}):
        new = parent / 'execskill-20261114-typed-v3-smoke'
        with pytest.raises(ValueError, match='registered'):
            prepare.prepare(new, **common, **bad)
        assert not new.exists()
    # load_manifest refuses a missing or unknown value (re-sealed, so only the field differs)
    root = Path(made['root'])
    for key, value in (('schedule', 'economy'), ('memory_lock', 'shared'), ('schedule', None)):
        units.write_json(root / 'manifest.json', prepare.seal({**fields, key: value}))
        with pytest.raises(ValueError, match=key):
            prepare.load_manifest(root)
    for key in ('schedule', 'memory_lock'):
        units.write_json(root / 'manifest.json', prepare.seal({k: v for k, v in fields.items() if k != key}))
        with pytest.raises(ValueError, match=key):
            prepare.load_manifest(root)


def test_the_chain_refuses_a_manifest_without_a_schedule_before_anything_is_written(tmp_path):
    for broken in ({'schedule': None}, {'schedule': 'economy'}):
        services, _, _ = build(tmp_path / 'r', order=('searchqa',))
        services.manifest = {**services.manifest, **broken}
        with pytest.raises(ValueError, match='schedule'):
            chain.run(tmp_path / 'r', 'G', services=services)
        assert not (tmp_path / 'r').exists()
    assert smoke.synthetic_manifest()['schedule'] == 'interleaved'
    assert smoke.synthetic_manifest()['memory_lock'] == 'per_cell_plain'
    made = smoke.synthetic_manifest(schedule='learn_first', memory_lock='unit_shared')
    assert (made['schedule'], made['memory_lock']) == ('learn_first', 'unit_shared')
    with pytest.raises(ValueError, match='schedule'):
        smoke.synthetic_manifest(schedule='first')
    with pytest.raises(ValueError, match='memory lock'):
        smoke.synthetic_manifest(memory_lock='none')


# ---- T2, T3, T4: the two orders ------------------------------------------------------------------------------------
def test_interleaved_done_units_are_the_typed_v1_sequence(tmp_path):
    """The code default is typed-v1's order (the expectations of tests/test_typed_chain.py:190-195), no new unit name;
    every freeze leaves its receipt; the state records the schedule, no phase at completion and all seven mounts."""
    services, _, _ = build(tmp_path, proposals={'searchqa': ['p-sq-1'], 'zebralogic': ['p-zb-1']},
                           scripted={'faults': {'p-zb-1': ['zebralogic-l0']}})
    state = chain.run(tmp_path, 'G', services=services)
    assert state['complete'] and state['schedule'] == 'interleaved' and state['phase'] is None
    done = state['done_units']
    expected_head = ['confirm'] + ['read-C0-%s' % b for b in ORDER] + ['read-C-%s' % b for b in ORDER] + ['step-0']
    assert done[:len(expected_head)] == expected_head
    s1 = done[done.index('s1/noise'):done.index('step-1') + 1]
    assert s1 == ['s1/noise', 's1/typing', 's1/outcomes', 's1/card-r1', 's1/outcomes-card', 's1/programs',
                  's1/program-1-smoke', 's1/program-1-gate'] + ['read-S1-%s' % b for b in ORDER] + ['step-1']
    assert done == expected_done(done, 'interleaved')
    assert sorted(state['read_mounts']) == sorted(EVENTS)
    assert set(chain.SCHEDULE_PAUSES) <= set(readplan.PAUSE_REASONS) and chain.PHASES == ('learn', 'read')
    for k in range(6):
        assert chain._receipt_valid(receipt_of(tmp_path, k), chain='G', step=k)


def test_learn_first_same_units_requests_identities(tmp_path):
    """T3 and T4: one scripted scenario on two roots, two schedules. Equal done units (as sets), requests (purpose,
    unit, sha256(system NUL user)), cells (unit, label, item, request and selection hashes), mount records, read meta
    and aggregates, decisions, libraries and type maps; only the order differs. Every read event mounted its own
    frozen state: C0 and C the s0 receipt, S<k> the s<k> receipt, although s5 existed when S1 was read."""
    roots = {schedule: tmp_path / ('%s-smoke' % schedule) for schedule in typed.SCHEDULES}
    runs = {schedule: real_run(root, schedule) for schedule, root in roots.items()}
    states = {schedule: run[0] for schedule, run in runs.items()}
    assert all(state['complete'] and state['paused'] is None for state in states.values())
    inter, first = states['interleaved']['done_units'], states['learn_first']['done_units']
    assert sorted(inter) == sorted(first) and len(set(inter)) == len(inter) and inter != first
    assert inter == expected_done(inter, 'interleaved') and first == expected_done(first, 'learn_first')
    assert max(first.index(u) for u in first if u.startswith('s5/')) < first.index('read-C0-searchqa')
    requests = {schedule: request_rows(run[1]) for schedule, run in runs.items()}
    assert requests['interleaved'] == requests['learn_first'] and len(requests['learn_first']) > 200
    order = {schedule: [unit for _, unit, _, _ in run[1].requests] for schedule, run in runs.items()}
    assert order['interleaved'] != order['learn_first']  # the same requests, sent in the other order
    assert cell_rows(roots['interleaved'], relabel=False) == cell_rows(roots['learn_first'], relabel=False)
    assert mounts_and_meta(roots['interleaved']) == mounts_and_meta(roots['learn_first'])
    assert step_records(roots['interleaved']) == step_records(roots['learn_first'])
    # T4: the mounts of the read events
    for schedule, root in roots.items():
        mounts = states[schedule]['read_mounts']
        assert sorted(mounts) == sorted(EVENTS)
        for event in EVENTS:
            k = 0 if event in ('C0', 'C') else int(event[1:])
            receipt = receipt_of(root, k)
            assert mounts[event] == {'step': k, 'library_file_sha256': receipt['library_file_sha256'],
                                     'typemap_file_sha256': receipt['typemap_file_sha256']}
            assert receipt['library_file_sha256'] == file_sha(root / 'G' / ('s%d' % k) / 'library.json')
            assert set(mounts[event]) == set(readplan.READ_MOUNT_KEYS)
        steps = [receipt_of(root, k)['library_file_sha256'] for k in range(6)]
        assert len(set(steps)) == 6  # every step saved its own library (its own step number at least)
    # the S<k> read cells mount only skills of steps up to k (a later step's card never reaches an earlier read)
    for (unit, _), row in mounts_and_meta(roots['learn_first'])[0].items():
        if unit.startswith('practice-read-S'):
            k = int(unit.split('-')[2][1:])
            skills = [row['mount'].get('card_skill')] + list(row['mount'].get('programs_enabled') or [])
            assert all(int(s.split('-')[2][1:]) <= k for s in skills if s), (unit, skills)


def test_learn_first_reads_mount_each_steps_frozen_state(tmp_path):
    """T4 with the fake reads: every read event receives the library and type map of its own frozen step (S1 the
    s1 state although s5 exists), C0 and C the empty s0 state."""
    reads_fake = FakeReads()
    services, _, _ = fake_run(tmp_path, 'learn_first', reads=reads_fake,
                              proposals={'searchqa': ['p-sq-1'], 'zebralogic': ['p-zb-1']})
    state = chain.run(tmp_path, 'G', services=services)
    assert state['complete'] and state['schedule'] == 'learn_first'
    seen = {(event, bench): (lib, tm) for event, bench, _, lib, tm in reads_fake.calls}
    for event in EVENTS:
        k = 0 if event in ('C0', 'C') else int(event[1:])
        library = library_.Library.load(tmp_path / 'G' / ('s%d' % k) / 'library.json').summary()
        typemap = tasktypes.TypeMap.load(tmp_path / 'G' / ('s%d' % k) / 'typemap.json').summary()
        for bench in ORDER:
            assert seen[(event, bench)] == (library, typemap), (event, bench)
    assert seen[('S1', 'searchqa')][0] != seen[('S5', 'searchqa')][0]  # s5 differs from s1 and S1 still read s1


# ---- T5: a changed frozen file pauses before any call ---------------------------------------------------------------
def tamper_library(root, k):
    """Another VALID library in s<k>/ (its own record hash holds; only the receipt can tell)."""
    library_.Library().save(Path(root) / 'G' / ('s%d' % k) / 'library.json', step=k)


def reseal_receipt(root, k):
    """A receipt that matches the tampered files (as if someone rewrote it too)."""
    path = Path(root) / 'G' / ('s%d' % k) / chain.FROZEN
    old = json.loads(path.read_text())
    fields = {key: value for key, value in old.items() if key != 'record_sha256'}
    fields.update(chain._frozen_hashes(Path(root) / 'G' / ('s%d' % k)))
    path.write_text(json.dumps(chain._sealed(fields)))


@pytest.mark.parametrize('schedule', typed.SCHEDULES)
def test_changed_frozen_file_pauses_before_any_call(tmp_path, schedule):
    """A read of S2 stopped once (missing cells); meanwhile another valid library replaced s2/library.json: the
    resume pauses frozen_state_changed at s2 with zero calls (interleaved: read_step's load_frozen; learn_first:
    the R79 check in learn(2), learning being closed); with the receipt rewritten to match, the S2 mount bound before
    the first attempt differs: read_mount_changed, again with zero calls."""
    reads_fake = FakeReads()
    reads_fake.missing = {('S2', 'officeqa'): 1}
    services, modules, script = fake_run(tmp_path, schedule, reads=reads_fake)
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'incomplete_read:missing_cells' and state['paused']['unit'] == 'read-S2-officeqa'
    assert state['read_mounts']['S2']['step'] == 2 and state['phase'] == 'read'
    tamper_library(tmp_path, 2)
    before, reads_before, files = sends(tmp_path), len(reads_fake.calls), listing(tmp_path / 'G' / 's2')
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert state['paused']['reason'] == 'frozen_state_changed' and state['paused']['unit'] == 's2'
    assert state['paused']['detail'] == 'library_changed'
    assert sends(tmp_path) == before and len(reads_fake.calls) == reads_before and listing(tmp_path / 'G' / 's2') == files
    reseal_receipt(tmp_path, 2)
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    # learn_first: learning is closed, learn(2) only checks the receipt, which matches now; both orders then reach the
    # S2 read, whose mount was bound before its first attempt
    assert (state['paused']['reason'], state['paused']['unit']) == ('read_mount_changed', 'read-S2')
    assert sends(tmp_path) == before and len(reads_fake.calls) == reads_before


def test_learning_is_closed_once_reading_has_begun(tmp_path):
    """read-plan R79 (T21): under learn_first, a missing s3 receipt once the read phase began is never re-learned: zero
    role, writer and solver calls, no write under s3/, pause frozen_state_changed (unit s3, receipt_missing); a
    missing s0 file pauses the same way instead of a new s0."""
    reads_fake = FakeReads()
    reads_fake.missing = {('C', 'searchqa'): 1}
    services, modules, script = fake_run(tmp_path, 'learn_first', reads=reads_fake)
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['unit'] == 'read-C-searchqa' and state['phase'] == 'read'
    writer_calls = (len(modules.writers.write_calls), len(modules.writers.propose_calls), len(modules.writers.describe_calls))
    (tmp_path / 'G' / 's3' / chain.FROZEN).unlink()
    before, files, calls = sends(tmp_path), listing(tmp_path / 'G' / 's3'), len(script.calls)
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert (state['paused']['reason'], state['paused']['unit'], state['paused']['detail']) == (
        'frozen_state_changed', 's3', 'receipt_missing')
    assert sends(tmp_path) == before and len(script.calls) == calls and listing(tmp_path / 'G' / 's3') == files
    assert (len(modules.writers.write_calls), len(modules.writers.propose_calls),
            len(modules.writers.describe_calls)) == writer_calls
    # the s0 state is never rewritten either
    shutil.copy(tmp_path / 'G' / 's2' / chain.FROZEN, tmp_path / 'G' / 's3' / chain.FROZEN)  # a wrong receipt: invalid
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert (state['paused']['reason'], state['paused']['detail']) == ('frozen_state_changed', 'receipt_invalid')
    (tmp_path / 'G' / 's0' / 'typemap.json').unlink()
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert (state['paused']['reason'], state['paused']['unit']) == ('frozen_state_changed', 's0')
    assert not (tmp_path / 'G' / 's0' / 'typemap.json').exists() and sends(tmp_path) == before


def test_a_receipt_is_never_written_for_a_state_a_read_has_mounted(tmp_path):
    """Under interleaved learning follows reading, so R79 does not apply; still, a receipt missing after its state was
    mounted by a read is never re-made from the files on disk (that could bless changed files): the re-run of the
    step's body ends in frozen_state_changed."""
    reads_fake = FakeReads()
    reads_fake.missing = {('S2', 'searchqa'): 1}
    services, modules, script = fake_run(tmp_path, 'interleaved', reads=reads_fake)
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['unit'] == 'read-S2-searchqa'
    (tmp_path / 'G' / 's2' / chain.FROZEN).unlink()
    before = sends(tmp_path)
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert (state['paused']['reason'], state['paused']['unit'], state['paused']['detail']) == (
        'frozen_state_changed', 's2', 'receipt_missing')
    assert sends(tmp_path) == before and not (tmp_path / 'G' / 's2' / chain.FROZEN).exists()


# ---- T6, T7: resume ----------------------------------------------------------------------------------------------
class BreakOnce(Capture):
    """The scripted clients, failing once on the first send of ``purpose`` in a unit starting with ``prefix``."""

    def __init__(self, scripted=None, *, purpose, prefix):
        super().__init__(scripted)
        self.broken = (purpose, prefix)

    def send(self, purpose, system, user, *, model, unit=None):
        if self.broken and purpose == self.broken[0] and str(unit).startswith(self.broken[1]):
            self.broken = None
            raise RuntimeError('connection lost')
        return super().send(purpose, system, user, model=model, unit=unit)


def test_learn_first_resume_in_learning_and_in_reads(tmp_path):
    """T6: a learn_first chain breaks in s3 (the card writer's connection) and later in S2 (a read cell raises);
    each resume completes what is open and redoes nothing: the requests, cells and done units equal those of an
    uninterrupted run; after the first resume no s1 / s2 unit sends, after the second no learning unit and no
    finished read unit sends."""
    clean, clean_script, _ = real_run(tmp_path / 'clean-smoke', 'learn_first')
    root = tmp_path / 'broken-smoke'
    script = BreakOnce(purpose='card_writer', prefix='s3/')
    services = smoke.fake_services(root, 'G', smoke.synthetic_manifest(schedule='learn_first'), scripted=script)
    services.embed = exact_embedder
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(smoke.SMOKE_LIMITS)
    real_solve, crash = services.solve_fn, {'on': True, 'cells': 0}

    def solve(bench, item, mounted, *, unit, **kw):  # the unit's SECOND cell raises once (a first cell would stop the
        if crash['on'] and unit == 'practice-read-S2-officeqa':  # unit as a configuration failure instead)
            crash['cells'] += 1
            if crash['cells'] == 2:
                crash['on'] = False
                raise KeyError('read cell')
        return real_solve(bench, item, mounted, unit=unit, **kw)
    services.solve_fn = solve
    state = chain.run(root, 'G', services=services, sleep=lambda s: None)
    assert (state['paused']['reason'], state['paused']['unit'], state['phase']) == ('exception:RuntimeError', 's3/card-r1', 'learn')
    assert not any(unit.startswith('read-') for unit in state['done_units'])
    first = len(script.requests)
    recovery(root)
    state = chain.run(root, 'G', services=services, sleep=lambda s: None, resume=True)
    assert (state['paused']['reason'], state['paused']['unit']) == ('incomplete_read:missing_cells', 'read-S2-officeqa')
    after_first = [unit for _, unit, _, _ in script.requests[first:]]
    assert not any(unit.startswith(('s1/', 's2/')) for unit in after_first)
    second = len(script.requests)
    recovery(root)
    state = chain.run(root, 'G', services=services, sleep=lambda s: None, resume=True)
    assert state['complete'] and state['phase'] is None and state['current_unit'] is None
    after_second = [unit for _, unit, _, _ in script.requests[second:]]
    resent = [purpose for purpose, unit, _, _ in script.requests[second:] if unit == 'practice-read-S2-officeqa']
    assert resent.count('solver') == 1 and set(resent) <= {'solver', 'selection'}  # only the missing cell
    assert not any(unit.startswith('s') and '/' in unit for unit in after_second)  # no learning unit
    assert not any(unit.startswith(('practice-read-C', 'practice-read-S1-')) for unit in after_second)
    # the same requests as the uninterrupted run, plus the one the raising read cell had sent before it raised (its
    # selection call: the mount runs before the solve, and a re-run cell is mounted again); the card writer's failed
    # send never reached the script (it failed before), so it adds nothing
    extra = Counter(map(tuple, request_rows(script))) - Counter(map(tuple, request_rows(clean_script)))
    assert not Counter(map(tuple, request_rows(clean_script))) - Counter(map(tuple, request_rows(script)))
    assert [(purpose, unit) for purpose, unit, _ in extra.elements()] == [('selection', 'practice-read-S2-officeqa')]
    assert state['done_units'] == clean['done_units']
    assert cell_rows(root, relabel=False) == cell_rows(tmp_path / 'clean-smoke', relabel=False)
    assert [r['paused']['reason'] for r in state['recoveries']] == ['exception:RuntimeError',
                                                                     'incomplete_read:missing_cells']


def test_resume_refuses_a_different_schedule(tmp_path):
    """S9: a state whose schedule differs from the manifest is refused before the ledger opens (a new root is needed)."""
    reads_fake = FakeReads()
    reads_fake.missing = {('C0', 'searchqa'): 1}
    services, _, _ = fake_run(tmp_path, 'interleaved', order=('searchqa',), reads=reads_fake)
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused'] and state['schedule'] == 'interleaved'
    ledger = (tmp_path / 'G' / 'ledger.json').read_bytes()
    recovery(tmp_path)
    services.manifest = {**services.manifest, 'schedule': 'learn_first'}
    with pytest.raises(ValueError, match='another schedule'):
        chain.run(tmp_path, 'G', services=services, resume=True)
    assert (tmp_path / 'G' / 'ledger.json').read_bytes() == ledger and (tmp_path / 'G' / 'recovery.json').exists()
    services.manifest = {**services.manifest, 'schedule': 'interleaved'}
    assert chain.run(tmp_path, 'G', services=services, resume=True)['complete']


# ---- T8: consent in every read unit, in both orders ----------------------------------------------------------------
@pytest.mark.parametrize('schedule', typed.SCHEDULES)
def test_consent_is_checked_in_every_read_unit_in_both_orders(tmp_path, monkeypatch, schedule):
    """A real-mode chain with the REAL read path (panel_tasks behind data.TestAccess; the panel reader faked): without
    the owner's consent no panel opens (interleaved: the first read unit refuses; learn_first: the zero-call check at
    chain start, schedule-lock Q2, refuses before anything is sent); with it every read unit checks it again."""
    opened, checked, real_consent = [], [], reads.consent
    monkeypatch.setattr(data, 'test_panel', fake_panel('searchqa', seen=opened))
    monkeypatch.setattr(reads, 'consent', lambda shared: checked.append(str(shared)) or real_consent(shared))
    services, _, _ = fake_run(tmp_path, schedule, order=('searchqa',), reads=reads)
    services.mode = 'run'
    services.manifest = {**services.manifest, 'pinned': {'paths': {}, 'sha256': {}}}
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'exception:ValueError' and opened == []
    assert not (tmp_path / 'shared' / 'test').exists() and not (tmp_path / 'G' / 'test-read-C0-searchqa').exists()
    if schedule == 'learn_first':
        assert state['paused']['unit'] == 'consent' and sends(tmp_path) == 0 and not (tmp_path / 'G' / 's0').exists()
    else:
        assert state['paused']['unit'] == 'read-C0' and sends(tmp_path) == 1  # the confirmed first call only
    write_consent(tmp_path / 'shared')
    recovery(tmp_path)
    checked.clear()
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert state['complete'] and state['schedule'] == schedule
    assert [unit for _, unit, _ in opened] == ['G/test-read-%s-searchqa' % event for event in ('C0', 'C', 'S1')]
    assert len(checked) == 3 + (schedule == 'learn_first')  # every read unit (+ the start check of learn_first)
    assert json.loads((tmp_path / 'shared' / 'test' / 'searchqa.json').read_text())['entry']['benchmark'] == 'searchqa'


# ---- T9: status ---------------------------------------------------------------------------------------------------
def test_status_shows_schedule_and_phase(tmp_path):
    reads_fake = FakeReads()
    reads_fake.missing = {('S2', 'searchqa'): 1}
    services, _, _ = fake_run(tmp_path, 'learn_first', reads=reads_fake)
    state = chain.run(tmp_path, 'G', services=services)
    units.write_json(tmp_path / 'manifest.json', {'memory_lock': 'unit_shared'})
    found = readout.status(tmp_path)
    row = found['chains']['G']
    assert (row['schedule'], row['phase'], row['current_unit']) == ('learn_first', 'read', 'read-S2')
    assert row['state']['read_mounts']['S2']['step'] == 2 and found['memory_lock'] == 'unit_shared'
    assert sorted(row['read_status']) == sorted('%s-%s' % (e, b) for e in ('C0', 'C', 'S1', 'S2') for b in ORDER)
    summary = run_typed.state_summary(state)
    assert (summary['schedule'], summary['phase'], summary['exit_code']) == ('learn_first', 'read', 5)
    text = Path(readout.build(tmp_path, now=0)['written']['G']['markdown']).read_text()
    assert '- schedule: learn_first; phase: read; current unit: read-S2' in text and 'no read mirror yet' not in text
    # during learning under learn_first: steps without any mirror are normal, and the markdown says so
    other = tmp_path / 'other'
    services, modules, _ = fake_run(other, 'learn_first', order=('searchqa', 'officeqa'))
    modules.writers.crash = lambda bench, round_: bench == 'officeqa'
    state = chain.run(other, 'G', services=services)
    row = readout.status(other)['chains']['G']
    assert (row['schedule'], row['phase'], row['current_unit']) == ('learn_first', 'learn', 's2/card-r1')
    assert row['read_status'] == {} and row['steps_present'] == [0, 1, 2] and readout.status(other)['memory_lock'] is None
    text = Path(readout.build(other, now=0)['written']['G']['markdown']).read_text()
    assert 'no read mirror yet is normal' in text


# ---- Part B: the memory lock ---------------------------------------------------------------------------------------
def spy_route_b(monkeypatch, *, real=True):
    """Every ``route_b_chain.heavy`` call as (bench, extra, root or None); delegated to the real function."""
    calls, original = [], route_b_chain.heavy

    def spy(setting, bench, *more):
        calls.append((bench, dict(setting.extra), getattr(setting, 'root', None)))
        return original(setting, bench, *more) if real else contextlib.nullcontext()
    monkeypatch.setattr(route_b_chain, 'heavy', spy)
    return calls


def test_default_lock_is_the_typed_v1_call(tmp_path, monkeypatch):
    """T10: per_cell_plain is typed-v1's call for every learning and read cell: route_b_chain.heavy with exactly
    extra = {'slot_root', 'configuration': 'default'} and no root (the plain branch, the unit ignored); the real lock
    leaves no holder and no wait file; T/mount.py and T/units.py hold no lock call."""
    slots = tmp_path / 'slots'
    root = tmp_path / 'plain-smoke'
    calls = spy_route_b(monkeypatch)
    script = Capture()
    manifest = {**smoke.synthetic_manifest(), 'slot_root': str(slots)}
    services = smoke.fake_services(root, 'G', manifest, scripted=script)
    services.embed, services.limits = exact_embedder, dict(smoke.SMOKE_LIMITS)
    services.slices = smoke.smoke_slices(services.items, services.slices)
    plain, setting = chain.heavy_for(manifest, root, 'G')
    assert setting is None
    seen = []
    services.heavy = lambda bench, unit=None: seen.append((bench, unit)) or plain(bench, unit)
    state = chain.run(root, 'G', services=services, sleep=lambda s: None)
    assert state['complete']
    assert calls and len(calls) == len(seen)
    assert all(extra == {'slot_root': str(slots), 'configuration': 'default'} and found is None
               for _, extra, found in calls)
    assert {bench for bench, _ in seen} == set(ORDER) and all(unit for _, unit in seen)
    assert any(unit.startswith('s4/') for _, unit in seen) and any(unit.startswith('practice-read-') for _, unit in seen)
    assert sorted(p.name for p in slots.iterdir()) == ['memory-heavy.lock']  # no holder file
    assert not (root / 'G' / 'lock-waits.jsonl').exists() and not (root / 'G' / 'chain.log').exists()
    for name in ('mount.py', 'units.py'):
        tree = ast.parse((TREE / 'skillopt' / 'execskill' / 'typed' / name).read_text())
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert not names & {'heavy', 'heavy_for', 'flock', 'environment', 'v218_lock', 'lock_setting'}, name


def test_per_cell_plain_cells_of_one_unit_exclude_each_other(tmp_path):
    """L1: the plain lock takes a new descriptor per cell, so two sheet cells of ONE unit run one after the other."""
    heavy, _ = chain.heavy_for({'memory_lock': 'per_cell_plain', 'slot_root': str(tmp_path / 'slots')}, tmp_path, 'G')
    inside, release, second = threading.Event(), threading.Event(), threading.Event()

    def first():
        with heavy('spreadsheetbench', 's4/noise'):
            inside.set()
            release.wait(10)

    def other():
        with heavy('spreadsheetbench', 's4/noise'):
            second.set()
    a = threading.Thread(target=first)
    a.start()
    assert inside.wait(10)
    b = threading.Thread(target=other)
    b.start()
    assert not second.wait(0.3)  # the same unit's second cell waits for the first
    release.set()
    assert second.wait(10)
    a.join(10)
    b.join(10)


def test_unit_shared_two_cells_overlap_and_another_unit_waits(tmp_path):
    """T11: under unit_shared two sheet cells of one unit hold the exclusive lock together (the holder file names the
    unit), the kernel lock is really taken, a cell of another unit waits until both left, and its wait is recorded
    (lock-waits.jsonl, chain.log under <root>/<chain>/); no holder file is left."""
    slots, root = tmp_path / 'slots', tmp_path / 'run'
    heavy, setting = chain.heavy_for({'memory_lock': 'unit_shared', 'slot_root': str(slots)}, root, 'G')
    assert setting.root == root and setting.extra == {'slot_root': str(slots), 'configuration': typed.MACHINERY,
                                                      'memory_lock_chain': 'G'}
    events = {name: threading.Event() for name in ('a', 'b', 'c', 'release')}
    holders = {}

    def cell(name, unit):
        with heavy('spreadsheetbench', unit):
            found = sorted(slots.glob('memory-heavy.lock.holder-*.json'))
            holders[name] = json.loads(found[0].read_text()) if found else None
            events[name].set()
            if name != 'c':
                events['release'].wait(10)
    a = threading.Thread(target=cell, args=('a', 's4/noise'))
    a.start()
    assert events['a'].wait(10)
    b = threading.Thread(target=cell, args=('b', 's4/noise'))
    b.start()
    assert events['b'].wait(10)  # the second cell of the same unit enters while the first is inside
    descriptor = os.open(slots / 'memory-heavy.lock', os.O_RDWR)
    try:
        with pytest.raises(OSError):  # a non-blocking flock from another open file fails: the kernel lock is held
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)
    c = threading.Thread(target=cell, args=('c', 's4/outcomes'))
    c.start()
    assert not events['c'].wait(0.3)  # another unit waits
    events['release'].set()
    assert events['c'].wait(10)
    for thread in (a, b, c):
        thread.join(10)
    assert holders['a']['unit'] == holders['b']['unit'] == 'G/s4/noise' and holders['a']['mode'] == 'exclusive'
    assert holders['c']['unit'] == 'G/s4/outcomes'
    assert not list(slots.glob('memory-heavy.lock.holder-*.json'))
    waits = [json.loads(line) for line in (root / 'G' / 'lock-waits.jsonl').read_text().splitlines()]
    assert [(w['unit'], w['mode']) for w in waits] == [('G/s4/outcomes', 'exclusive')]
    assert 'for G/s4/outcomes' in (root / 'G' / 'chain.log').read_text()


def test_unit_shared_setting_names_root_chain_unit(tmp_path, monkeypatch):
    """T12: every shared hold names the run root, the chain and the unit (``<chain>/<unit>``) with the machinery
    configuration; a call without a unit is refused, and so is the bare setting in v218_lock (X/v218_lock.py:99-100);
    an unknown or missing mode is refused when the services are built."""
    calls = spy_route_b(monkeypatch, real=False)
    slots, root = tmp_path / 'slots', tmp_path / 'run'
    heavy, setting = chain.heavy_for({'memory_lock': 'unit_shared', 'slot_root': str(slots)}, root, 'G')
    with heavy('alfworld', 'test-read-S3-alfworld'):
        pass
    assert calls == [('alfworld', {'slot_root': str(slots), 'configuration': 'main-v10', 'memory_lock_chain': 'G',
                                   'memory_lock_unit': 'G/test-read-S3-alfworld'}, root)]
    for bench in ('spreadsheetbench', 'searchqa'):
        with pytest.raises(ValueError, match='names its unit'):
            heavy(bench)
    assert 'memory_lock_unit' not in setting.extra
    monkeypatch.undo()
    with pytest.raises(ValueError, match='names its chain and unit'):
        with v218_lock.environment(setting, 'spreadsheetbench'):
            pass
    for broken in ({'slot_root': str(slots)}, {'slot_root': str(slots), 'memory_lock': 'plain'}):
        with pytest.raises(ValueError, match='memory_lock'):
            chain.heavy_for(broken, root, 'G')
    plain, none = chain.heavy_for({'slot_root': str(slots), 'memory_lock': 'per_cell_plain'}, root, 'D')
    assert none is None and callable(plain)


# ---- T13: the lock and the schedule under the bound machinery ---------------------------------------------------------
CHILD = r'''
import fcntl, json, os, sys
from pathlib import Path
sys.path.insert(0, %(scripts)r)
import run_typed
run_typed.bind_machinery(%(snapshot)r, %(tree)r)
from skillopt.execskill import chain as rb, v218_lock
from skillopt.execskill.typed import chain as tc, smoke
slots, root = Path(%(slots)r), Path(%(root)r)
out = {'rb': rb.__file__, 'v218': v218_lock.__file__, 'tc': tc.__file__}


def blocked():
    descriptor = os.open(slots / 'memory-heavy.lock', os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return False
    except OSError:
        return True
    finally:
        os.close(descriptor)


heavy, setting = tc.heavy_for({'memory_lock': 'per_cell_plain', 'slot_root': str(slots)}, root, 'G')
with heavy('spreadsheetbench', 's4/noise'):
    out['plain'] = {'blocked': blocked(), 'holders': sorted(p.name for p in slots.glob('*.holder-*')), 'setting': setting}
heavy, setting = tc.heavy_for({'memory_lock': 'unit_shared', 'slot_root': str(slots)}, root, 'G')
with heavy('spreadsheetbench', 's4/noise'):
    found = sorted(slots.glob('memory-heavy.lock.holder-*.json'))
    out['shared'] = {'blocked': blocked(), 'holder': json.loads(found[0].read_text()) if found else None}
out['after'] = sorted(p.name for p in slots.iterdir())
for schedule in ('interleaved', 'learn_first'):
    services = smoke.fake_services(root / schedule, 'G', smoke.synthetic_manifest(schedule=schedule))
    services.order = ('searchqa', 'officeqa')
    state = smoke.run(root / schedule, 'G', services=services, sleep=lambda s: None)
    out[schedule] = {'complete': state['complete'], 'paused': state['paused'], 'done': state['done_units']}
print(json.dumps(out))
'''


def test_the_lock_modes_and_the_schedules_under_the_bound_machinery(tmp_path):
    """T13: a fresh interpreter bound to a stand-in snapshot (this tree's skillopt/ without execskill/typed):
    route_b_chain and v218_lock load from the snapshot; per_cell_plain really locks <slot_root>/memory-heavy.lock (a
    non-blocking flock from another open file fails) without a holder file; unit_shared writes the holder file naming
    <chain>/<unit>; a fake learn_first chain and a fake interleaved chain end with the same done units."""
    snapshot = tmp_path / 'snapshot'
    shutil.copytree(TREE / 'skillopt', snapshot / 'skillopt',
                    ignore=lambda folder, names: [n for n in names if n == '__pycache__' or (
                        n == 'typed' and Path(folder).name == 'execskill')])
    for data_dir in ('docs/handoff/v29-20261026', 'tests/fixtures/execskill/v222_cards'):  # read beside skillopt/
        shutil.copytree(TREE / data_dir, snapshot / data_dir)
    slots, root = tmp_path / 'slots', tmp_path / 'chains'
    code = CHILD % {'scripts': str(TREE / 'scripts'), 'snapshot': str(snapshot), 'tree': str(TREE),
                    'slots': str(slots), 'root': str(root)}
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    env['TMPDIR'] = str(NEUTRAL)
    done = subprocess.run([sys.executable, '-I', '-c', code], cwd=str(tmp_path), env=env, capture_output=True,
                          text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    found = json.loads(done.stdout.strip().splitlines()[-1])
    assert found['rb'].startswith(str(snapshot)) and found['v218'].startswith(str(snapshot))
    assert found['tc'].startswith(str(TREE / 'skillopt' / 'execskill' / 'typed'))
    assert found['plain'] == {'blocked': True, 'holders': [], 'setting': None}
    assert found['shared']['blocked'] is True and found['shared']['holder']['unit'] == 'G/s4/noise'
    assert found['shared']['holder']['mode'] == 'exclusive' and found['after'] == ['memory-heavy.lock']
    inter, first = found['interleaved'], found['learn_first']
    assert inter['complete'] and first['complete'], (inter['paused'], first['paused'])
    assert sorted(inter['done']) == sorted(first['done']) and inter['done'] != first['done']
    order = ('searchqa', 'officeqa')
    assert inter['done'] == expected_done(inter['done'], 'interleaved', order)
    assert first['done'] == expected_done(first['done'], 'learn_first', order)
