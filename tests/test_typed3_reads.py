"""typed-v3 reads (docs/handoff/typed-v3/CHAIN-DECISIONS.md T2; brief P3r): the sealed option ``read_anchors``
(('C0', 'C') = typed-v2's reads, or ('C',): the anchor C0 is never read), the schedule 'interleaved' with the read
plan 'full' run and resumed end to end (after step k the frozen state S<k> is read fresh on all five panels before
step k+1 learns), and the consent of the arms C, S1..S5 -- on fakes only (no network, no Docker, no /data, nothing
paid).

The chains run through the REAL ``chain.run``, ``mount``, ``writers`` and ``reads``: in smoke mode on held-out practice
panels, in run mode (the real run's mode; the synthetic manifest's evidence label) on synthetic panels behind the one
``data.TestAccess`` of ``reads.panel_tasks`` under the owner's consent record. Expected values are computed by hand
(the hand-made read cells of the readout test) or from the raw sealed cells by the test's own arithmetic, never by the
readout's code. A
kill is a real SIGKILL of a child process at a chosen point; the resumed records are compared with those of an
uninterrupted run, and every send of the resumed process is checked against the records that existed after the kill.
"""
import functools
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import pytest

from scripts import run_typed
from skillopt.coevo5 import data
from skillopt.execskill import evaluation, typed as typed_
from skillopt.execskill.typed import (ORDER, READ_ARMS, archives, chain, library as library_, prepare, readout,
                                      readplan, reads, smoke, units)
from skillopt.validator_pilot.api import digest
from tests.test_typed2_base import Capture, exact_embedder
from tests.test_typed_schedule import inputs  # noqa: F401 -- prepare's fixture (pools, machinery record, typed tree)

NEUTRAL = Path('/tmp/typed3-reads-neutral').resolve()  # resolved: route B's safe_path refuses a symlink in any parent
TREE = Path(run_typed.__file__).resolve().parents[1]
C_EVENTS = ('C', 'S1', 'S2', 'S3', 'S4', 'S5')
S_EVENTS = C_EVENTS[1:]
TIME_KEYS = {'at', 'accepted_at', 'updated', 'started', 'saved_at', 'frozen_at', 'created_at', 'seconds', 'applied_at',
             'bound_at', 'finished'}
# besides the clock: the ledger snapshots, the ledger's send numbers (concurrent cells take them in any order) and the
# hashes that cover a clock value (library records, receipts, aggregates)
VOLATILE = TIME_KEYS | {'ledger', 'logical_call', 'record_sha256', 'library_record_sha256', 'library_file_sha256',
                        'aggregate_sha256', 'receipt_sha256'}


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='reads3-', dir=NEUTRAL))
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


@pytest.fixture
def qualified(monkeypatch):
    """The SpreadsheetBench test qualification of a run-mode read, faked: every panel item qualifies."""
    monkeypatch.setattr(evaluation, '_sheet_qualification', lambda shared, tasks, runtime, **kw: {
        'side': 'test', 'task_hashes': {t['task_id']: digest(t) for t in tasks},
        'qualified': [t['task_id'] for t in tasks]})


# ---- the worlds ---------------------------------------------------------------------------------------------------
def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def c_manifest(**extra):
    """The synthetic manifest of the typed-v3 reads: schedule interleaved, read plan full, base historical, memory lock
    unit_shared, the anchor C alone."""
    made = smoke.synthetic_manifest(schedule='interleaved', memory_lock='unit_shared', base_card='historical',
                                    read_plan='full')
    return {**made, 'read_anchors': ['C'], **extra}


def v3_manifest():
    """``c_manifest`` with the typed-v3 program learning of this tree: 'repair' with the archive packages."""
    return c_manifest(program_learning='repair', archive=archives.sealed('index'))


def smoke_services(root, chain_name, manifest=None, *, script=None, order=ORDER):
    """Fake services through the REAL mount, writers and reads on the smoke's practice panels, the smoke's limits,
    exact family embeddings (``v3_manifest`` unless another manifest is given)."""
    script = script if script is not None else Capture()
    services = smoke.fake_services(root, chain_name, v3_manifest() if manifest is None else manifest, scripted=script)
    services.embed, services.order = exact_embedder, order
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(smoke.SMOKE_LIMITS)
    return services


def panel_items(bench, n=2):
    """Two synthetic test-panel stand-ins per bench in the pools' shapes (ALFWorld: a game file; its routing view comes
    from the read's reset)."""
    rows = []
    for i in range(n):
        task_id = '%s-t%d' % (bench, i)
        public, private = smoke.SYNTHETIC_ITEMS[bench](task_id)
        if bench == 'alfworld':
            public = {'game_file': '/fake/json_2.1.1/valid_unseen/pick-Mug-None-Sink-%d/trial_T1/game.tw-pddl' % i}
        rows.append({'benchmark': bench, 'task_id': task_id, 'public': public, 'private': private})
    return rows


def panel_reader(seen):
    """``coevo5.data.test_panel``'s shape behind the one ``data.TestAccess``; every opening is recorded."""
    def panel(pinned, benchmark, *, access):
        assert isinstance(access, data.TestAccess) and 'test-read' in access.unit
        seen.append((benchmark, access.unit))
        tasks = panel_items(benchmark)
        return tasks, {'benchmark': benchmark, 'tasks': len(tasks), 'excluded_without_pages': [],
                       'panel_hash': digest(tasks), 'source_files': None}
    return panel


def alfworld_reset(public):
    """The read's ALFWorld preparation reset (``evaluation.alfworld_reset``'s ``reset(public)``), faked."""
    return 'You are in a kitchen. A sink 1 is here.\n\nYour task is to: put a mug in sink.', ['look', 'go to sink 1']


def sealed_manifest(root, manifest):
    """``manifest`` as ``prepare`` leaves it on disk: sealed, bound to its root, at ``<root>/manifest.json`` (the
    panel boundary takes the planned read events from this file, never from the services). Returns the record."""
    record = prepare.seal({**{k: v for k, v in manifest.items() if k != 'record_sha256'}, 'root': str(root)})
    units.write_json(Path(root) / 'manifest.json', record)
    return record


def run_services(root, chain_name, manifest=None, *, seen, script=None, order=ORDER):
    """Fake services in run mode (the real run's mode: under learn_first the chain checks the consent at its start):
    every read opens its panel through ``reads.panel_tasks`` under the owner's consent into a sealed
    ``test-read-<event>-<bench>`` unit (the panel reader and the ALFWorld reset faked). The manifest is sealed into
    ``<root>/manifest.json`` (as a prepared root has it) and the services carry that record."""
    zebra = {'path': '/fake/sealed-zebra.json', 'sha256': 'f' * 64}  # main-v10 pins its sealed Zebra panel apart
    manifest = sealed_manifest(root, {**(c_manifest() if manifest is None else manifest),
                                      'pinned': {'paths': {}, 'sha256': {}, 'zebralogic': zebra}})
    services = smoke_services(root, chain_name, manifest, script=script, order=order)
    services.mode = 'run'
    services.read_panel = functools.partial(reads.read_panel, panel=panel_reader(seen), alfworld_views=alfworld_reset)
    return services


def consent_value(arms=C_EVENTS, **changes):
    return {'test_evaluation': True, 'sheet_test_qualification': True, 'multi_arm_arms': list(arms), 'by': 'owner',
            'date': '2026-11-15', 'note': 'typed-v3 fixture: practice items stand in for the panels', **changes}


def write_consent(root, arms=C_EVENTS, **changes):
    units.write_json(Path(root) / 'shared' / 'consent.json', consent_value(arms, **changes))


def recovery(root, chain_name='G', decision='continue'):
    units.write_json(Path(root) / chain_name / 'recovery.json',
                     {'by': 'owner', 'date': '2026-11-15', 'decision': decision})


def state_of(root, chain_name='G'):
    return json.loads((Path(root) / chain_name / 'state.json').read_text())


def receipt_of(root, chain_name, k):
    return json.loads((Path(root) / chain_name / ('s%d' % k) / chain.FROZEN).read_text())


def cells_of(unit_dir):
    return {path.stem: json.loads(path.read_text()) for path in sorted((Path(unit_dir) / 'cells').glob('*.json'))}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def snapshot(chain_dir):
    """Every record file of a chain directory, its clock values (and what covers them) stripped; the chain state, the
    ledger and the owner's recovery records apart (they belong to the run's history, not to its results)."""
    out = {}
    for path in sorted(Path(chain_dir).rglob('*')):
        rel = str(path.relative_to(chain_dir))
        if not path.is_file() or rel in ('state.json', 'ledger.json') or rel.startswith('recovery-'):
            continue
        out[rel] = strip(json.loads(path.read_text())) if path.suffix == '.json' else path.read_bytes()
    return out


def state_record(state):
    """What a resumed chain state must share with an uninterrupted one."""
    return {'done_units': state['done_units'], 'reads': strip(state['reads']), 'complete': state['complete'],
            'paused': state['paused'], 'step': state['step'], 'phase': state['phase'],
            'read_anchors': state.get('read_anchors'), 'mounts': {e: m['step'] for e, m in state['read_mounts'].items()}}


def expected_done(done, events, order=ORDER):
    """The done units of a complete interleaved chain from its own learning units: confirm, the anchor events, step-0,
    then per step its learning units, its read event on every panel and step-<k> (typed-v1's order)."""
    out = ['confirm'] + ['read-%s-%s' % (event, bench) for event in events if not event.startswith('S')
                         for bench in order] + ['step-0']
    for k in range(1, len(order) + 1):
        out += [unit for unit in done if unit.startswith('s%d/' % k)]
        out += ['read-S%d-%s' % (k, bench) for bench in order] + ['step-%d' % k]
    return out


def unit_of_request(unit):
    """('learn', k) for a learning unit s<k>/..., ('read', event) for a read unit, else (None, unit)."""
    unit = str(unit)
    if unit.startswith(('practice-read-', 'test-read-')):
        return 'read', unit.split('-')[2]
    if unit[:1] == 's' and '/' in unit and unit.split('/')[0][1:].isdigit():
        return 'learn', int(unit.split('/')[0][1:])
    return None, unit


# ---- the option and its readers ---------------------------------------------------------------------------------------
def test_the_read_anchor_option_its_events_and_its_cross_checks():
    assert readplan.READ_ANCHORS == (('C0', 'C'), ('C',)) and readplan.READ_ANCHORS_DEFAULT == ('C0', 'C')
    assert readplan.read_events() == readplan.EVENTS == tuple(READ_ARMS) == ('C0', 'C') + S_EVENTS
    assert readplan.read_events(['C']) == readplan.read_events(('C',)) == C_EVENTS
    for bad in ('C', 'C0', ('C', 'C0'), ['C0'], [], None, ('C0', 'C', 'S1'), {'C': 1}, ['c']):
        with pytest.raises(ValueError):
            readplan.read_events(bad)
    assert readplan.check_read_anchors(('C0', 'C'), read_plan='economy', base_card='format') == ('C0', 'C')
    assert readplan.check_read_anchors(['C'], read_plan='full', base_card='historical') == ('C',)
    for plan, base, word in (('economy', 'historical', 'read_plan'), ('full', 'format', 'base_card'),
                             (None, 'historical', 'read_plan'), ('full', None, 'base_card')):
        with pytest.raises(ValueError, match=word):
            readplan.check_read_anchors(('C',), read_plan=plan, base_card=base)
    # the manifest reader: absent = typed-v2's anchors (any typed-v2 style manifest, prepared or synthetic)
    assert prepare.read_anchors_of({}) == ('C0', 'C') == prepare.read_anchors_of(smoke.synthetic_manifest())
    assert prepare.read_anchors_of({'arms': list(READ_ARMS)}) == ('C0', 'C')
    assert prepare.read_anchors_of(c_manifest()) == ('C',)
    assert prepare.read_anchors_of({**c_manifest(), 'arms': list(C_EVENTS)}) == ('C',)
    for bad in ({**c_manifest(), 'arms': list(READ_ARMS)}, {'arms': list(C_EVENTS)},
                {**c_manifest(), 'read_plan': 'economy'}, {**c_manifest(), 'base_card': 'format'},
                {**c_manifest(), 'read_anchors': 'C'},
                {**c_manifest(), 'read_anchors': None}, {**c_manifest(), 'read_anchors': ['C0']}, None, ['C']):
        with pytest.raises(ValueError):
            prepare.read_anchors_of(bad)


def test_prepare_seals_the_read_anchors_and_a_default_manifest_stays_typed_v2s(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    default = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', **common)
    assert 'read_anchors' not in default and default['arms'] == list(READ_ARMS)  # typed-v2's fields and values
    assert prepare.read_anchors_of(default) == ('C0', 'C')
    made = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', read_anchors=('C',), base_card='historical',
                           schedule='interleaved', read_plan='full', **common)
    assert made['read_anchors'] == ['C'] and made['arms'] == list(C_EVENTS)
    assert set(made) == set(default) | {'read_anchors'}
    assert prepare.load_manifest(made['root']) == made and prepare.read_anchors_of(made) == ('C',)
    assert (made['schedule'], made['read_plan'], made['base_card']) == ('interleaved', 'full', 'historical')
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    assert prepare.seal({**fields, 'read_anchors': ['C0', 'C']})['record_sha256'] != made['record_sha256']
    # refused before anything is written: economy, base format, an unregistered value
    for n, bad in enumerate(({'read_anchors': ('C',), 'base_card': 'historical', 'schedule': 'learn_first',
                              'read_plan': 'economy'}, {'read_anchors': ('C',)}, {'read_anchors': ('C0',)},
                             {'read_anchors': 'C'}, {'read_anchors': ('C', 'C0'), 'base_card': 'historical'})):
        new = parent / ('execskill-2026112%d-typed-v3-smoke' % n)
        with pytest.raises(ValueError):
            prepare.prepare(new, **common, **bad)
        assert not new.exists()
    # load_manifest refuses a changed value (re-sealed, so only the field differs) and arms that do not match
    root = Path(made['root'])
    for change in ({'read_anchors': ['C0']}, {'base_card': 'format'}, {'arms': list(READ_ARMS)},
                   {'read_anchors': ['C0', 'C']}):
        units.write_json(root / 'manifest.json', prepare.seal({**fields, **change}))
        with pytest.raises(ValueError):
            prepare.load_manifest(root)
    units.write_json(root / 'manifest.json', prepare.seal({k: v for k, v in fields.items() if k != 'read_anchors'}))
    with pytest.raises(ValueError, match='arms'):  # C, S1..S5 arms without the field: the anchors would be C0 and C
        prepare.load_manifest(root)


def test_the_cli_names_read_anchors_on_prepare_only(tmp_path, monkeypatch, environ, capsys):
    assert run_typed.READ_ANCHORS == tuple(','.join(anchors) for anchors in readplan.READ_ANCHORS)
    parse = run_typed.parser().parse_args
    assert parse(['prepare', '--root', '/r', '--read-anchors', 'C']).read_anchors == 'C'
    assert parse(['prepare', '--root', '/r', '--read-anchors', 'C0,C']).read_anchors == 'C0,C'
    assert parse(['prepare', '--root', '/r']).read_anchors is None
    for bad in (['prepare', '--root', '/r', '--read-anchors', 'C0'], ['prepare', '--root', '/r', '--read-anchors', 'S1'],
                ['run', '--root', '/r', '--chain', 'G', '--read-anchors', 'C'],
                ['smoke', '--root', '/r', '--chain', 'G', '--fake', '--read-anchors', 'C']):
        with pytest.raises(SystemExit):
            parse(bad)
    calls = []
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(kw) or {
        'configuration': 'typed-v3', 'read_anchors': ['C'], 'arms': list(C_EVENTS)})
    root = tmp_path / 'run'
    root.mkdir()
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {}}))
    argv = ['prepare', '--root', str(root), '--machinery-manifest', str(machinery), '--read-anchors', 'C',
            '--base-card', 'historical', '--schedule', 'interleaved', '--read-plan', 'full']
    assert run_typed.main(argv) == 0
    assert calls[-1] == {'machinery_manifest': str(machinery), 'roles_repo': typed_.ROLES_REPO,
                         'pools_root': typed_.POOLS_ROOT, 'smoke': False, 'base_card': 'historical',
                         'schedule': 'interleaved', 'read_plan': 'full', 'read_anchors': 'C'}
    printed = json.loads(capsys.readouterr().out)['manifest']
    assert printed['read_anchors'] == ['C'] and printed['arms'] == list(C_EVENTS)
    # the adapter hands prepare the tuple, and nothing when the command names no anchors
    seen = []
    monkeypatch.undo()  # the real adapter again
    monkeypatch.setattr(prepare, 'prepare', lambda root, **kw: seen.append(kw) or {})
    common = dict(machinery_manifest='/m.json', roles_repo='/creds', pools_root='/pools', smoke=True)
    run_typed._prepare('/r', **common)
    run_typed._prepare('/r', read_anchors='C', **common)
    run_typed._prepare('/r', read_anchors='C0,C', **common)
    assert seen == [common, {**common, 'read_anchors': ('C',)}, {**common, 'read_anchors': ('C0', 'C')}]


def test_a_state_started_with_one_anchor_list_refuses_the_other_and_a_bad_manifest_writes_nothing(tmp_path):
    default = chain._open_state(tmp_path / 'a', 'G', 'smoke', False)
    assert 'read_anchors' not in default  # typed-v2's state shape
    made = chain._open_state(tmp_path / 'b', 'G', 'smoke', False, read_anchors=('C',))
    assert made['read_anchors'] == ['C']
    (tmp_path / 'b').mkdir()
    units.write_json(tmp_path / 'b' / 'state.json', made)
    assert chain._open_state(tmp_path / 'b', 'G', 'smoke', True, read_anchors=('C',)) == made
    with pytest.raises(ValueError, match='another read_anchors'):
        chain._open_state(tmp_path / 'b', 'G', 'smoke', True)
    (tmp_path / 'a').mkdir()
    units.write_json(tmp_path / 'a' / 'state.json', default)
    with pytest.raises(ValueError, match='another read_anchors'):
        chain._open_state(tmp_path / 'a', 'G', 'smoke', True, read_anchors=('C',))
    # chain.run refuses before the chain directory, the state or the ledger is written
    for n, change in enumerate(({'read_plan': 'economy', 'schedule': 'learn_first'}, {'base_card': 'format'},
                                {'read_anchors': ['C0']}, {'read_anchors': 'C'})):
        root = tmp_path / ('bad-%d' % n)
        services = smoke_services(root, 'G', {**c_manifest(), **change}, order=('searchqa',))
        with pytest.raises(ValueError):
            chain.run(root, 'G', services=services, sleep=lambda s: None)
        assert not root.exists()


def test_the_default_anchors_read_C0_and_C_and_every_record_keeps_typed_v2s_shape(tmp_path):
    """Without the field the chain reads C0 and C before step 1 (typed-v1's order), its state, readout document and
    status carry no read-anchor key, the 5x5 keeps S<k> - C0, the CL metrics keep C0 and the terminal counts 35."""
    root = tmp_path / 'default-smoke'
    manifest = smoke.synthetic_manifest(schedule='interleaved', base_card='historical', read_plan='full')
    state = chain.run(root, 'G', services=smoke_services(root, 'G', manifest), sleep=lambda s: None)
    assert state['complete'] and 'read_anchors' not in state
    assert state['done_units'] == expected_done(state['done_units'], READ_ARMS)
    assert sorted(state['read_mounts']) == sorted(READ_ARMS)
    doc = readout.build(root, open_sealed=True, now=1)['chains']['G']
    assert 'read_anchors' not in doc and doc['panels']['searchqa']['events'] == list(READ_ARMS)
    assert 'S1-C0' in doc['panels']['searchqa']['pairs'] and 'diff_points_vs_C0' in doc['five_by_five']['S1']
    assert set(doc['cl_metrics']['per_bench']['searchqa']['L']) == set(readout.METRIC_KEYS) | {'final_event'}
    assert 'not_read' not in doc['cl_metrics'] and '- read anchors' not in readout.markdown(doc)
    assert 'read_events' not in readout.status(root)['chains']['G']['read_plan']
    assert run_typed.state_summary(state, root / 'G')['read_plan']['reads']['of'] == 35


# ---- interleaved + full with the anchor C alone, end to end -----------------------------------------------------
@pytest.mark.parametrize('chain_name', ['G', 'D'])
def test_a_chain_reads_C_then_each_frozen_step_fresh_before_the_next_step_learns_and_never_C0(tmp_path, chain_name):
    """Both chains, five steps, the typed-v3 program learning of this tree ('repair' with the archive packages) on the
    smoke's practice panels: the read events are C, S1..S5 (none for C0); S<k> is read from s<k>'s receipt after every
    request of step k and before any request of step k+1; every read cell was solved in this run (fresh, one send)
    and mounts only skills frozen in its step's library."""
    root = tmp_path / 'run-smoke'
    services = smoke_services(root, chain_name)
    script = services.script
    state = chain.run(root, chain_name, services=services, sleep=lambda s: None)
    assert state['complete'] and state['paused'] is None and state['read_anchors'] == ['C']
    assert state['schedule'] == 'interleaved' and state['read_plan']['mode'] == 'full'
    done, chain_dir = state['done_units'], root / chain_name
    assert done == expected_done(done, C_EVENTS)
    assert not [unit for unit in done if 'C0' in unit] and 'C0' not in state['reads']
    assert sorted(state['read_mounts']) == sorted(C_EVENTS)
    assert not [p for p in chain_dir.rglob('*') if 'C0' in p.name]  # no unit, no mirror, no calls file of C0
    assert sorted(p.stem for p in (chain_dir / 'read-status').glob('*.json')) == sorted(
        '%s-%s' % (event, bench) for event in C_EVENTS for bench in ORDER)
    # the timeline of every request: step k's learning < the S<k> read < step k+1's learning
    phases = [unit_of_request(unit) for _, unit, _, _ in script.requests]
    for k in range(1, 6):
        reading = [i for i, phase in enumerate(phases) if phase == ('read', 'S%d' % k)]
        learning = [i for i, phase in enumerate(phases) if phase == ('learn', k)]
        later = [i for i, phase in enumerate(phases) if phase[0] == 'learn' and phase[1] > k]
        assert reading and learning and max(learning) < min(reading), k
        assert not later or max(reading) < min(later), k
    first_learning = min(i for i, phase in enumerate(phases) if phase[0] == 'learn')
    assert max(i for i, phase in enumerate(phases) if phase == ('read', 'C')) < first_learning
    # each event mounts its own frozen state; every read cell is fresh and mounts only its step's skills
    for event in C_EVENTS:
        k = 0 if event == 'C' else int(event[1:])
        receipt = receipt_of(root, chain_name, k)
        assert state['read_mounts'][event] == {'step': k, 'library_file_sha256': receipt['library_file_sha256'],
                                               'typemap_file_sha256': receipt['typemap_file_sha256']}
        known = {skill['skill_id'] for skill in library_.Library.load(chain_dir / ('s%d' % k) / 'library.json').skills}
        for bench in ORDER:
            unit = reads.unit_name(event, bench, smoke=True)
            cells = cells_of(chain_dir / unit)
            assert len(cells) == len(services.slices[bench]['panel']) == 2
            solved = [1 for purpose, found, _, _ in script.requests if purpose == 'solver' and found == unit]
            assert len(solved) == len(cells) and all(len(cell['sends']) == 1 for cell in cells.values())
            for cell in cells.values():
                mounted = {cell['mount'].get('card_skill')} | set(cell['mount'].get('programs_enabled') or [])
                assert mounted - {None} <= known, (event, bench, mounted)
                assert cell['arm'] == ('C' if event == 'C' else 'F')
    assert state['read_mounts']['S5']['library_file_sha256'] != state['read_mounts']['S1']['library_file_sha256']
    # the terminal summary counts 30 planned pairs, all settled
    summary = run_typed.state_summary(state, chain_dir)
    assert summary['read_plan']['reads'] == {'settled': 30, 'of': 30, 'fresh_done': 30, 'fresh_planned': None,
                                             'alias': 0, 'fallbacks': 0, 'void_aliases': 0}
    assert readout.status(root)['chains'][chain_name]['read_plan']['read_events'] == list(C_EVENTS)
    # the open readout: no C0 row anywhere, the contrasts S<k> - C and S<k> - S<k-1> from the raw cells
    doc = readout.build(root, open_sealed=True, now=1)['chains'][chain_name]
    assert doc['read_anchors'] == ['C'] and set(doc['read_units']) == {'%s-%s' % (e, b) for e in C_EVENTS for b in ORDER}
    for bench in ORDER:
        panel = doc['panels'][bench]
        assert panel['events'] == list(C_EVENTS) and set(panel['per_event']) == set(C_EVENTS)
        assert set(panel['pairs']) == {'S%d-C' % k for k in range(1, 6)} | {'S%d-S%d' % (k, k - 1) for k in range(2, 6)}
        assert panel['same_request_noise'] is None
        by_event = {}
        for event in C_EVENTS:
            cells = cells_of(chain_dir / reads.unit_name(event, bench, smoke=True)).values()
            by_event[event] = {cell['item_id']: cell['correct'] for cell in cells}
        for name, pair in panel['pairs'].items():
            first, second = name.split('-')
            known = [item for item in by_event[first]
                     if by_event[first][item] is not None and by_event[second][item] is not None]
            diffs = [int(by_event[first][item]) - int(by_event[second][item]) for item in known]
            assert pair['n'] == len(known) and abs(pair['mean_points'] - 100.0 * sum(diffs) / len(diffs)) < 1e-9, name
    assert all(set(row) == {'step', 'evolved_bench', 'diff_points_vs_C', 'diff_points_vs_previous', 'accuracy_L',
                            'accuracy_H'} for row in doc['five_by_five'].values())
    assert all(set(m['L']) == set(readout.C_METRIC_KEYS) | {'final_event'} for m in doc['cl_metrics']['per_bench'].values())
    assert '"C0"' not in json.dumps({key: doc[key] for key in ('panels', 'five_by_five', 'read_units', 'read_tokens')})


def test_the_open_readout_without_C0_by_hand(tmp_path):
    """Hand-made sealed read cells of a chain with read_anchors C (searchqa evolved at step 1, zebralogic at step 3,
    one unknown cell on zebralogic in S3): the rows C, S1..S5, the contrasts S<k> - C and S<k> - S<k-1>, the 5x5 and
    the CL metrics with S0 := C, every value worked out by hand below; a C0 unit is refused, never tabulated."""
    root = tmp_path / 'hand'
    chain_dir = root / 'G'
    outcomes = {'searchqa': {'C': [1, 0, 0, 0], 'S1': [1, 1, 0, 0], 'S2': [1, 1, 1, 0], 'S3': [1, 0, 1, 0],
                             'S4': [1, 1, 1, 1], 'S5': [1, 1, 0, 0]},
                'zebralogic': {'C': [0, 0, 1, 1], 'S1': [0, 1, 1, 1], 'S2': [0, 1, 1, 0], 'S3': [1, 1, 1, None],
                               'S4': [1, 1, 0, 1], 'S5': [1, 1, 1, 1]}}
    for bench, events in outcomes.items():
        for event, values in events.items():
            unit = chain_dir / reads.unit_name(event, bench, smoke=True)
            for i, value in enumerate(values):
                item = '%s-p%d' % (bench, i)
                units.write_json(unit / 'cells' / ('%s.json' % sha256(item + event)), {
                    'item_id': item, 'arm': 'C' if event == 'C' else 'F', 'correct': None if value is None else bool(value),
                    'token': 'unknown_timeout' if value is None else 'pass' if value else 'fail', 'tokens': 10,
                    'request_sha256': [sha256(event + item)], 'mount': {'type': None, 'unknown_reason': 'unseen',
                                                                          'card_skill': None, 'programs_enabled': []}})
            units.write_json(unit / 'done.json', {'cells': 4, 'expected_cells': 4, 'stop_reason': None})
    units.write_json(chain_dir / 'state.json', {'version': 'typed-v3', 'chain': 'G', 'mode': 'smoke', 'read_anchors': ['C'],
                                                 'base_card': 'historical', 'schedule': 'interleaved',
                                                 'read_plan': {'mode': 'full'}, 'complete': True, 'done_units': []})
    doc = readout.chain_readout(root, 'G', open_sealed=True, stamp='x')
    sq, zb = doc['panels']['searchqa'], doc['panels']['zebralogic']
    assert sq['events'] == zb['events'] == list(C_EVENTS) and sq['items_common'] == zb['items_common'] == 4
    assert {e: sq['per_event'][e]['accuracy']['L'] for e in C_EVENTS} == {
        'C': .25, 'S1': .5, 'S2': .75, 'S3': .5, 'S4': 1.0, 'S5': .5}
    assert (zb['per_event']['S3']['accuracy']['L'], zb['per_event']['S3']['accuracy']['H']) == (.75, 1.0)
    points = lambda panel: {name: round(pair['mean_points'], 6) for name, pair in panel['pairs'].items()}  # noqa: E731
    assert points(sq) == {'S1-C': 25.0, 'S2-C': 50.0, 'S2-S1': 25.0, 'S3-C': 25.0, 'S3-S2': -25.0, 'S4-C': 75.0,
                          'S4-S3': 50.0, 'S5-C': 25.0, 'S5-S4': -50.0}
    assert points(zb) == {'S1-C': 25.0, 'S2-C': 0.0, 'S2-S1': -25.0, 'S3-C': 66.666667, 'S3-S2': 33.333333,
                          'S4-C': 25.0, 'S4-S3': -33.333333, 'S5-C': 50.0, 'S5-S4': 25.0}
    assert (zb['pairs']['S3-C']['n'], zb['pairs']['S3-C']['excluded_unknown']) == (3, 1)
    assert (sq['pairs']['S4-C']['better'], sq['pairs']['S4-C']['worse'], sq['pairs']['S4-C']['tied']) == (3, 0, 1)
    assert sq['same_request_noise'] is None and 'C0' not in sq['per_event']
    five = doc['five_by_five']
    assert [(row['step'], row['evolved_bench']) for row in five.values()] == list(zip(range(1, 6), ORDER))
    assert round(five['S1']['diff_points_vs_C']['searchqa'], 6) == round(five['S1']['diff_points_vs_previous']['searchqa'], 6) == 25.0
    assert round(five['S3']['diff_points_vs_C']['zebralogic'], 6) == 66.666667
    assert round(five['S3']['diff_points_vs_previous']['zebralogic'], 6) == 33.333333
    assert round(five['S5']['diff_points_vs_previous']['searchqa'], 6) == -50.0 and five['S5']['diff_points_vs_C']['officeqa'] is None
    assert five['S3']['accuracy_L']['zebralogic'] == .75  # the unknown cell counts as wrong in L
    assert five['S3']['accuracy_H']['zebralogic'] == 1.0 and 'diff_points_vs_C0' not in five['S1']
    cl = doc['cl_metrics']
    assert cl['not_read'] == ['C0', 'gain_over_C0', 'same_request_noise'] and cl['final_event'] == 'S5'
    s, z = cl['per_bench']['searchqa'], cl['per_bench']['zebralogic']
    rounded = lambda block: {k: v if v is None or isinstance(v, str) else round(v, 9) for k, v in block.items()}  # noqa: E731
    assert rounded(s['L']) == {'final_event': 'S5', 'final': .5, 'C': .25, 'gain_over_C': .25, 'forgetting': .5,
                               'forgetting_after_home': .5, 'backward_transfer': 0.0, 'forward_transfer': None,
                               'plasticity': .25}
    assert rounded(z['L']) == {'final_event': 'S5', 'final': 1.0, 'C': .5, 'gain_over_C': .5, 'forgetting': -.25,
                               'forgetting_after_home': -.25, 'backward_transfer': .25, 'forward_transfer': 0.0,
                               'plasticity': .25}
    assert rounded(z['H']) == {**rounded(z['L']), 'forgetting': 0.0, 'forgetting_after_home': 0.0,
                               'backward_transfer': 0.0, 'plasticity': .5}
    macro = {key: (round(v['mean'], 9) if v['mean'] is not None else None, v['n_benches'])
             for key, v in cl['macro']['L'].items()}
    assert macro == {'final': (.75, 2), 'C': (.375, 2), 'gain_over_C': (.375, 2), 'forgetting': (.125, 2),
                     'forgetting_after_home': (.125, 2), 'backward_transfer': (.125, 2), 'forward_transfer': (0.0, 1),
                     'plasticity': (.25, 2)}
    text = readout.markdown(doc)
    assert '- read anchors: C (sealed `read_anchors`)' in text and 'S<k> - S<k-1> (S0 := C)' in text
    assert 'S<k> - C, mean paired difference' in text and 'S<k> - C0' not in text and 'C0 %' not in text
    assert 'same-request noise (C vs C0): not measured' in text
    # a C0 unit in such a chain is refused, never tabulated or silently left out
    units.write_json(chain_dir / reads.unit_name('C0', 'searchqa', smoke=True) / 'cells' / 'x.json',
                     {'item_id': 'searchqa-p0', 'arm': 'C0', 'correct': True})
    with pytest.raises(ValueError, match='C0-searchqa'):
        readout.chain_readout(root, 'G', open_sealed=True, stamp='y')
    closed = readout.chain_readout(root, 'G', stamp='z')  # the closed readout opens no unit and names the anchors
    assert closed['read_anchors'] == ['C'] and 'panels' not in closed


def test_both_chains_read_the_panels_of_C_and_S1_to_S5_under_their_consent_on_one_root(tmp_path, monkeypatch, qualified):
    """Run mode on one root (chain G, then chain D, as on dl): every read unit opens its panel through the one
    ``data.TestAccess`` after the owner's consent naming exactly C, S1..S5 passed -- 30 units per chain, none of C0 --
    and both chains find the same registered panels."""
    root, seen, checked = tmp_path / 'run', [], []
    real_consent = reads.consent
    monkeypatch.setattr(reads, 'consent', lambda shared, arms=READ_ARMS: checked.append(tuple(arms)) or
                        real_consent(shared, arms=arms))
    write_consent(root)
    for chain_name in ('G', 'D'):
        services = run_services(root, chain_name, v3_manifest(), seen=seen)
        state = chain.run(root, chain_name, services=services, sleep=lambda s: None)
        assert state['complete'] and state['paused'] is None, state['paused']
        assert state['done_units'] == expected_done(state['done_units'], C_EVENTS)
        assert sorted(p.name for p in (root / chain_name).iterdir() if p.name.startswith('test-read')) == sorted(
            reads.unit_name(e, b) for e in C_EVENTS for b in ORDER)
    assert sorted(seen) == sorted((b, '%s/test-read-%s-%s' % (c, e, b)) for c in ('G', 'D') for e in C_EVENTS for b in ORDER)
    assert checked == [C_EVENTS] * 60  # every read unit of both chains checked the consent of the six arms
    for bench in ORDER:
        registry = json.loads((root / 'shared' / 'test' / ('%s.json' % bench)).read_text())
        assert registry['entry']['tasks'] == sorted(t['task_id'] for t in panel_items(bench))
    assert not [p for p in root.rglob('*') if 'C0' in p.name]


def test_the_consent_of_C_and_S1_to_S5_is_accepted_and_one_that_misses_an_arm_is_refused(tmp_path):
    shared = tmp_path / 'shared'
    write_consent(tmp_path)
    assert reads.consent(shared, arms=C_EVENTS) == consent_value() == reads.consent(shared, arms=list(C_EVENTS))
    with pytest.raises(ValueError, match='read arms'):  # typed-v2's seven arms are not covered by six
        reads.consent(shared)
    bad = [consent_value(READ_ARMS), consent_value(reversed(C_EVENTS)), consent_value(C_EVENTS + ('I',)),
           consent_value(('C', 'C') + S_EVENTS)]
    bad += [consent_value(tuple(e for e in C_EVENTS if e != missing)) for missing in C_EVENTS]
    for n, value in enumerate(bad):
        where = tmp_path / ('bad%d' % n)
        units.write_json(where / 'consent.json', value)
        with pytest.raises(ValueError, match='read arms'):
            reads.consent(where, arms=C_EVENTS)
    write_consent(tmp_path / 'seven', READ_ARMS)
    assert reads.consent(tmp_path / 'seven' / 'shared') == consent_value(READ_ARMS)  # the default, unchanged
    # the planned arms are one of the two read-event lists, never any other list
    for arms in (('C', 'S1'), S_EVENTS, READ_ARMS + ('X',), 'C', None):
        with pytest.raises(ValueError, match='planned read events'):
            reads.consent(shared, arms=arms)


def test_a_chain_pauses_at_its_first_read_when_the_consent_misses_an_arm_and_completes_after_the_owner_fixes_it(
        tmp_path, qualified):
    """Interleaved: the first read unit (C) refuses a consent without S5 before any panel opens (and a consent of the
    seven arms just the same); after the owner's consent of C, S1..S5 and the recovery record, the chain completes."""
    root, seen = tmp_path / 'run', []

    def run(resume):
        return chain.run(root, 'G', services=run_services(root, 'G', seen=seen, order=('searchqa',)),
                         sleep=lambda s: None, resume=resume)
    write_consent(root, tuple(e for e in C_EVENTS if e != 'S5'))
    for resume in (False, True):
        state = run(resume)
        assert (state['paused']['reason'], state['paused']['unit']) == ('exception:ValueError', 'read-C')
        assert seen == [] and not (root / 'shared' / 'test').exists() and not (root / 'G' / 'test-read-C-searchqa').exists()
        assert [u for u in state['done_units'] if u.startswith('read-')] == []
        write_consent(root, READ_ARMS)  # the seven arms of typed-v2 do not cover a run of six either
        recovery(root)
    write_consent(root)
    recovery(root)
    state = run(True)
    assert state['complete'] and [unit for _, unit in seen] == ['G/test-read-%s-searchqa' % e for e in ('C', 'S1')]
    assert [r['paused']['reason'] for r in state['recoveries']] == ['exception:ValueError'] * 2


def test_learn_first_with_the_anchor_C_checks_the_six_arm_consent_at_chain_start(tmp_path, qualified):
    """schedule-lock Q2 kept: under learn_first a run-mode chain checks the consent once at start, zero calls; with C
    alone that check names C, S1..S5, so a consent of the seven arms is refused before anything is sent."""
    root, seen = tmp_path / 'run', []
    write_consent(root, READ_ARMS)
    manifest = c_manifest(schedule='learn_first')
    state = chain.run(root, 'G', services=run_services(root, 'G', manifest, seen=seen, order=('searchqa',)),
                      sleep=lambda s: None)
    assert (state['paused']['reason'], state['paused']['unit']) == ('exception:ValueError', 'consent')
    assert not (root / 'G' / 'ledger.json').exists() or json.loads((root / 'G' / 'ledger.json').read_text())['sends'] == 0
    assert not (root / 'G' / 's0').exists() and not (root / 'G' / 'confirm.json').exists() and seen == []
    write_consent(root)
    recovery(root)
    state = chain.run(root, 'G', services=run_services(root, 'G', manifest, seen=seen, order=('searchqa',)),
                      sleep=lambda s: None, resume=True)
    assert state['complete'] and state['schedule'] == 'learn_first'
    done = state['done_units']
    assert done.index('read-C-searchqa') > max(done.index(u) for u in done if u.startswith('s1/'))  # read after learning
    assert [unit for _, unit in seen] == ['G/test-read-%s-searchqa' % e for e in ('C', 'S1')]


def test_a_C0_read_is_refused_before_any_panel_opens_and_the_default_still_reads_it(tmp_path, qualified):
    root, seen = tmp_path / 'run', []
    write_consent(root)
    services = run_services(root, 'G', seen=seen, order=('searchqa',))
    services.ledger = units.Ledger(root / 'G' / 'ledger.json', 10 ** 7)
    empty = (library_.Library(), chain.tasktypes.TypeMap())
    for read in (services.read_panel, reads.read_panel):
        with pytest.raises(ValueError, match='does not read the event C0'):
            read(root, 'G', 'C0', 'searchqa', library=empty[0], typemap=empty[1], services=services)
    assert seen == [] and not (root / 'G' / 'test-read-C0-searchqa').exists() and not (root / 'shared' / 'test').exists()
    # the one panel path refuses a C0 label (and the economy pass's label) under the six arms the root seals, before
    # the consent, whether or not the caller names the arms
    for unit in ('G/test-read-C0-searchqa', 'G/test-read-plan'):
        for arms in (None, C_EVENTS):
            with pytest.raises(ValueError, match='does not plan'):
                reads.panel_tasks(root / 'shared', {'x': 1}, 'searchqa', unit, runtime={}, native=None,
                                  evidence='engineering_fixture', run='r1', panel=panel_reader(seen), arms=arms)
    assert seen == []
    tasks = reads.panel_tasks(root / 'shared', {'x': 1}, 'searchqa', 'G/test-read-C-searchqa', runtime={}, native=None,
                              evidence='engineering_fixture', run='r1', panel=panel_reader(seen))
    assert len(tasks) == 2 and seen == [('searchqa', 'G/test-read-C-searchqa')]
    # a finished C0 unit planted in such a root stays closed: refused before its records are read or a mirror is made
    planted = root / 'G' / 'test-read-C0-searchqa'
    units.write_json(planted / 'done.json', {'cells': 1, 'expected_cells': 1, 'stop_reason': None}, allow_sealed=True)
    units.write_json(planted / 'cells' / 'x.json', {'item_id': 'searchqa-t0', 'arm': 'C0', 'correct': True},
                     allow_sealed=True)
    for read in (services.read_panel, reads.read_panel):
        with pytest.raises(ValueError, match='does not read the event C0'):
            read(root, 'G', 'C0', 'searchqa', library=empty[0], typemap=empty[1], services=services)
    assert not (root / 'G' / 'read-status').exists() and sorted(p.name for p in planted.iterdir()) == ['cells', 'done.json']
    # the default plan still reads C0 under the consent of the seven arms
    other, found = tmp_path / 'other', []
    write_consent(other, READ_ARMS)
    services = run_services(other, 'G', smoke.synthetic_manifest(), seen=found, order=('searchqa',))
    services.ledger = units.Ledger(other / 'G' / 'ledger.json', 10 ** 7)
    status = services.read_panel(other, 'G', 'C0', 'searchqa', library=empty[0], typemap=empty[1], services=services)
    assert status['status'] == 'complete' and found == [('searchqa', 'G/test-read-C0-searchqa')]


# ---- the panel boundary (Codex review P3r): the root's sealed plan, canonical labels -------------------------------
def test_the_panel_boundary_takes_the_planned_events_from_the_root_never_from_the_caller(tmp_path):
    """Review P3r (1): ``panel_tasks`` takes the planned read events from the root's own sealed manifest. On a root
    sealing the anchor C alone with the legacy consent of the seven arms, no label of C0, of the economy pass or of C
    opens a panel, whatever list the caller passes; a caller's list that differs from the sealed one is refused on
    every root (one of the seven events, sealed or without a manifest: typed-v2's seven), and so is a manifest that
    does not verify, one bound to another root and a ``shared`` directory of no root -- all before the one
    ``data.TestAccess``. ``open_panel`` with services whose manifest differs from the root's is refused the same way."""
    seen = []

    def tasks(root, unit, arms=None, shared='shared'):
        return reads.panel_tasks(Path(root) / shared, {'x': 1}, 'searchqa', unit, runtime={}, native=None,
                                 evidence='engineering_fixture', run='r1', panel=panel_reader(seen), arms=arms)
    c_root = tmp_path / 'c-root'
    record = sealed_manifest(c_root, c_manifest())
    write_consent(c_root, READ_ARMS)  # the legacy consent of the seven arms
    for unit, arms in (('G/test-read-C0-searchqa', None), ('G/test-read-C0-searchqa', READ_ARMS),
                       ('G/test-read-plan', None), ('G/test-read-plan', READ_ARMS),
                       ('G/test-read-C-searchqa', READ_ARMS), ('G/test-read-S1-searchqa', list(READ_ARMS))):
        with pytest.raises(ValueError, match='does not plan|root seals'):
            tasks(c_root, unit, arms)
    with pytest.raises(ValueError, match='read arms'):  # C itself: the seven-arm consent does not cover the six
        tasks(c_root, 'G/test-read-C-searchqa')
    assert seen == [] and not (c_root / 'shared' / 'test').exists()
    write_consent(c_root)  # C, S1..S5
    with pytest.raises(ValueError, match='does not plan'):
        tasks(c_root, 'G/test-read-C0-searchqa')
    assert seen == []
    assert len(tasks(c_root, 'G/test-read-C-searchqa')) == len(tasks(c_root, 'D/test-read-S1-searchqa', C_EVENTS)) == 2
    assert seen == [('searchqa', 'G/test-read-C-searchqa'), ('searchqa', 'D/test-read-S1-searchqa')]
    # a root of the seven events, sealed or without a manifest: the caller's six arms are refused, even under their
    # consent, and its own seven are not covered by that consent
    seven = smoke.synthetic_manifest(schedule='interleaved', base_card='historical', read_plan='full')
    for name, made in (('seven-root', seven), ('bare-root', None)):
        root = tmp_path / name
        if made is not None:
            sealed_manifest(root, made)
        write_consent(root)
        with pytest.raises(ValueError, match='root seals'):
            tasks(root, 'G/test-read-C-searchqa', C_EVENTS)
        with pytest.raises(ValueError, match='read arms'):
            tasks(root, 'G/test-read-C-searchqa')
    # services whose manifest plans C alone on a root that seals the seven events: open_panel is refused
    setup = {'manifest': c_manifest(pinned={'paths': {}, 'sha256': {}}), 'runtime': {'searchqa': {}}, 'event': 'C',
             'view_fn': lambda bench, item: item['public'], 'panel': panel_reader(seen)}
    with pytest.raises(ValueError, match='root seals'):
        reads.open_panel(tmp_path / 'seven-root', 'G', 'searchqa', 'test-read-C-searchqa', vectors=False, setup=setup)
    # the C root's manifest edited to the seven events without a new seal, re-sealed for another root, or the
    # shared directory of no root: refused
    units.write_json(c_root / 'manifest.json', {**record, 'read_anchors': ['C0', 'C'], 'arms': list(READ_ARMS)})
    with pytest.raises(ValueError, match='hash'):
        tasks(c_root, 'G/test-read-C-searchqa')
    sealed_manifest(tmp_path / 'elsewhere', c_manifest())
    shutil.copyfile(tmp_path / 'elsewhere' / 'manifest.json', c_root / 'manifest.json')
    with pytest.raises(ValueError, match='another root'):
        tasks(c_root, 'G/test-read-C-searchqa')
    sealed_manifest(c_root, c_manifest())
    (c_root / 'other').mkdir()
    shutil.copyfile(c_root / 'shared' / 'consent.json', c_root / 'other' / 'consent.json')
    with pytest.raises(ValueError, match='shared directory'):
        tasks(c_root, 'G/test-read-C-searchqa', shared='other')
    assert len(seen) == 2 and not (c_root / 'other' / 'test').exists()


def test_a_panel_label_is_the_canonical_unit_of_a_planned_event(tmp_path):
    """Review P3r (2): a panel opens only for ``<chain>/test-read-<event>-<bench>`` of a registered, planned event or
    for exactly ``<chain>/test-read-plan`` (the economy pass: typed-v2's seven events, and on a root with a manifest
    only under its sealed read plan 'economy'); ``open_panel`` opens only the canonical unit of the event its caller
    names. Everything else is refused before the one ``data.TestAccess``, a valid consent present."""
    seen = []

    def tasks(root, unit, bench='searchqa'):
        return reads.panel_tasks(Path(root) / 'shared', {'x': 1}, bench, unit, runtime={}, native=None,
                                 evidence='engineering_fixture', run='r1', panel=panel_reader(seen))
    bare = tmp_path / 'bare'  # no manifest: typed-v2's seven events
    write_consent(bare, READ_ARMS)
    for unit in ('G/test-read-S6-searchqa', 'G/test-read-C-officeqa', 'X/test-read-C-searchqa', 'test-read-C-searchqa',
                 'G/sub/test-read-C-searchqa', 'G/test-read-C-searchqa/x', 'G/test-read-C0-searchqa-2',
                 'G/test-read-plan-x', 'G/test-read-plan/searchqa', 'G/test-read--searchqa', 'G/test-read-c-searchqa',
                 'G/practice-read-C-searchqa/test-read', 'G/test-read-C0-searchqa ', '/G/test-read-C0-searchqa'):
        with pytest.raises(ValueError):
            tasks(bare, unit)
    assert seen == [] and not (bare / 'shared' / 'test').exists()
    for unit in ('G/test-read-C0-searchqa', 'D/test-read-S5-searchqa', 'G/test-read-plan'):
        assert len(tasks(bare, unit)) == 2
    # a root sealing the read plan 'full' never reads the economy pass's label; one sealing 'economy' does
    full, economy = tmp_path / 'full', tmp_path / 'economy'
    record = sealed_manifest(full, smoke.synthetic_manifest(schedule='learn_first', base_card='historical',
                                                            read_plan='full'))
    sealed_manifest(economy, smoke.synthetic_manifest(schedule='learn_first', read_plan='economy'))
    for root in (full, economy):
        write_consent(root, READ_ARMS)
    with pytest.raises(ValueError, match='does not plan'):
        tasks(full, 'G/test-read-plan')
    assert len(tasks(economy, 'G/test-read-plan')) == 2 and len(seen) == 4
    # open_panel: the canonical unit of the event the caller names, nothing else
    setup = {'manifest': {**record, 'pinned': {'paths': {}, 'sha256': {}}}, 'runtime': {'searchqa': {}},
             'view_fn': lambda bench, item: item['public'], 'panel': panel_reader(seen)}
    for unit, event in (('test-read-S2-searchqa', 'S1'), ('test-read-C-searchqa', 'S1'), ('test-read-S1-searchqa', 'C'),
                        ('test-read-S6-searchqa', 'S1'),
                        ('practice-read-C-searchqa', 'C'), ('test-read-C-officeqa', 'C'), ('test-read-plan', 'C'),
                        ('test-read-C-searchqa', None)):
        with pytest.raises(ValueError, match='canonical|not the unit'):
            reads.open_panel(full, 'G', 'searchqa', unit, vectors=False, setup={**setup, 'event': event})
    assert len(seen) == 4
    opened = reads.open_panel(full, 'G', 'searchqa', 'test-read-C-searchqa', vectors=False, setup={**setup, 'event': 'C'})
    assert opened['ids'] == ['searchqa-t0', 'searchqa-t1'] and seen[-1] == ('searchqa', 'G/test-read-C-searchqa')


# ---- kills: a SIGKILL inside a read event, between a read event and the next step -----------------------------------
CHILD = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, %(tree)r)
from skillopt.execskill.typed import chain
from tests import test_typed3_reads as t
root, chain_name = Path(%(root)r), %(chain)r
services = t.smoke_services(root, chain_name, script=t.LoggedCapture(%(log)r))
t.arm_kill(services, root / chain_name, %(point)r)
state = chain.run(root, chain_name, services=services, sleep=lambda s: None)
print(json.dumps({'not_killed': True, 'paused': state['paused']}))
'''


class LoggedCapture(Capture):
    """The scripted clients of ``Capture``; every request is also appended to a file as [purpose, unit, sha256(system
    NUL user)], flushed and fsynced BEFORE the reply, so the sends of a process that is killed are known."""

    def __init__(self, path, scripted=None):
        super().__init__(scripted)
        self.path = Path(path)

    def send(self, purpose, system, user, *, model, unit=None):
        line = json.dumps([purpose, unit, sha256(system + '\x00' + user)])
        with self.lock:
            with open(self.path, 'a', encoding='utf-8') as stream:
                stream.write(line + '\n')
                stream.flush()
                os.fsync(stream.fileno())
        return super().send(purpose, system, user, model=model, unit=unit)


def kill_now():
    sys.stdout.flush()
    os.kill(os.getpid(), signal.SIGKILL)


def arm_kill(services, chain_dir, point):
    """The child's kill point. 'cell:<event>-<bench>': inside that read unit's second panel cell (its first cell has its
    record; another unit of the event has one too), before the cell's send. 'mirror:<event>-<bench>': right after
    that unit sealed its aggregate and published its open mirror, before the event's marks. 'finish:<event>-<bench>':
    after that unit wrote its ``done.json`` (every cell recorded), before it sealed its aggregate or published its
    mirror. 'mark:<unit>': right after the chain persisted that marker (``step-<k>``: between the read event S<k> and
    step k+1's first learning unit)."""
    kind, _, where = point.partition(':')
    if kind == 'finish':
        event, bench = where.split('-', 1)
        finish = reads._finish

        def killing(root, chain_name, event_, bench_, *args, **kw):
            if (event_, bench_) == (event, bench):
                kill_now()
            return finish(root, chain_name, event_, bench_, *args, **kw)
        reads._finish = killing
        return
    if kind == 'cell':
        event, bench = where.split('-', 1)
        target, solve, count = reads.unit_name(event, bench, smoke=True), services.solve_fn, []
        others = [chain_dir / reads.unit_name(event, b, smoke=True) / 'cells' for b in ORDER if b != bench]

        def killing(bench_, item, mounted, *, unit, **kw):
            if unit == target:
                count.append(item['task_id'])
                if len(count) == 2:
                    deadline = time.time() + 60
                    while time.time() < deadline and not any(d.is_dir() and any(d.glob('*.json')) for d in others):
                        time.sleep(0.01)
                    kill_now()
            return solve(bench_, item, mounted, unit=unit, **kw)
        services.solve_fn = killing
    elif kind == 'mirror':
        event, bench = where.split('-', 1)
        finish = reads._finish

        def killing(root, chain_name, event_, bench_, *args, **kw):
            status = finish(root, chain_name, event_, bench_, *args, **kw)
            if (event_, bench_) == (event, bench):
                kill_now()
            return status
        reads._finish = killing
    else:
        assert kind == 'mark', point
        mark = chain._Run.mark

        def killing(self, unit):
            mark(self, unit)
            if unit == where:
                kill_now()
        chain._Run.mark = killing


@pytest.fixture(scope='module')
def clean_runs():
    """One uninterrupted run per chain (the reference records and requests), shared by the kill cases."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='reads3-clean-', dir=NEUTRAL))
    out = {}
    try:
        for chain_name in ('G', 'D'):
            root = base / ('clean-%s-smoke' % chain_name)
            services = smoke_services(root, chain_name)
            state = chain.run(root, chain_name, services=services, sleep=lambda s: None)
            assert state['complete']
            out[chain_name] = {'state': state, 'snapshot': snapshot(root / chain_name),
                               'requests': Counter((p, u, sha256(s + '\x00' + x)) for p, u, s, x in services.script.requests)}
        yield out
    finally:
        shutil.rmtree(base, ignore_errors=True)


KILLS = [('G', 'cell:C-officeqa'), ('G', 'cell:S2-officeqa'), ('D', 'cell:S2-officeqa'), ('G', 'mirror:S2-officeqa'),
         ('G', 'mark:step-2'), ('D', 'mark:step-0')]


@pytest.mark.parametrize('chain_name,point', KILLS)
def test_a_kill_resumes_to_the_records_of_an_uninterrupted_run(tmp_path, clean_runs, chain_name, point):
    """A SIGKILL of the chain process at ``point``, the owner's recovery record, a resume in a new process: the final
    records (every file of the chain directory, clock values stripped), the done units in their order and the read
    entries equal those of an uninterrupted run; the resumed process never builds a cell whose record existed after
    the kill, sends no request that the uninterrupted run did not send except for cells that had no record, and
    leaves no temporary file."""
    root, log = tmp_path / 'killed-smoke', tmp_path / 'sends.jsonl'
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    env['TMPDIR'] = str(NEUTRAL)
    code = CHILD % {'tree': str(TREE), 'root': str(root), 'chain': chain_name, 'log': str(log), 'point': point}
    killed = subprocess.run([sys.executable, '-c', code], cwd=str(TREE), env=env, capture_output=True, text=True,
                            timeout=600)
    assert killed.returncode == -signal.SIGKILL, (killed.stdout[-2000:], killed.stderr[-3000:])
    chain_dir = root / chain_name
    after_kill = {(str(p.parent.parent.relative_to(chain_dir)), p.stem) for p in chain_dir.rglob('cells/*.json')}
    state = state_of(root, chain_name)
    assert state['complete'] is False and state['paused'] is None  # a kill records nothing
    kind, _, where = point.partition(':')
    if kind == 'cell':
        event, bench = where.split('-', 1)
        unit = reads.unit_name(event, bench, smoke=True)
        assert len([1 for found, _ in after_kill if found == unit]) == 1  # in the middle of the unit
        assert 'read-%s-%s' % (event, bench) not in state['done_units']
        assert any(found.startswith('practice-read-%s-' % event) and found != unit for found, _ in after_kill)
    elif kind == 'mirror':
        event, bench = where.split('-', 1)
        assert (chain_dir / 'read-status' / ('%s-%s.json' % (event, bench))).exists()
        assert 'read-%s-%s' % (event, bench) not in state['done_units']
    else:
        k = int(where.split('-')[1])
        assert state['done_units'][-1] == where and not any(u.startswith('s%d/' % (k + 1)) for u in state['done_units'])
    # the owner's recovery and the resume in this process, every cell it builds recorded
    recovery(root, chain_name, 'resume after a kill')
    services = smoke_services(root, chain_name)
    built, solver_call = [], services.solver_call
    services.solver_call = lambda bench, unit, tag, **kw: built.append((unit, tag)) or solver_call(bench, unit, tag, **kw)
    resumed = chain.run(root, chain_name, services=services, sleep=lambda s: None, resume=True)
    clean = clean_runs[chain_name]
    assert resumed['complete'] and resumed['paused'] is None
    assert [r['paused'] for r in resumed['recoveries']] == [None]
    assert state_record(resumed) == state_record(clean['state'])
    assert snapshot(chain_dir) == clean['snapshot']
    assert not set(built) & after_kill  # no cell with a record at the kill was built (no paid call repeated)
    sent = Counter(tuple(json.loads(line)) for line in log.read_text().splitlines())
    sent += Counter((p, u, sha256(s + '\x00' + x)) for p, u, s, x in services.script.requests)
    assert not clean['requests'] - sent  # nothing the uninterrupted run sent is missing
    extra = sent - clean['requests']     # sent twice: only requests of cells that had no record at the kill
    for purpose, unit, request in extra.elements():
        assert purpose in ('solver', 'selection') and kind != 'mark', (purpose, unit)
        key = 'request_sha256' if purpose == 'solver' else 'selection_request_sha256'
        owners = [tag for tag, cell in cells_of(chain_dir / unit).items() if request in (cell.get(key) or [])]
        assert owners and not {(unit, tag) for tag in owners} & after_kill, (purpose, unit)
    assert not [p for p in chain_dir.rglob('*') if p.name.endswith(('.tmp', '.part'))]


CHILD_RUN = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, %(tree)r)
from skillopt.execskill.typed import chain
from tests import test_typed3_reads as t
root = Path(%(root)r)
services = t.run_services(root, 'G', seen=[], order=('searchqa',))
t.arm_kill(services, root / 'G', %(point)r)
state = chain.run(root, 'G', services=services, sleep=lambda s: None)
print(json.dumps({'not_killed': True, 'paused': state['paused']}))
'''


def test_a_finished_read_unit_is_not_read_again_before_the_checks_of_its_first_opening(tmp_path, monkeypatch):
    """Review P3r (3): run mode with the anchor C alone; a SIGKILL after the read unit C wrote its ``done.json`` and
    before it sealed its aggregate and published its mirror. On the resume the unit is answered from its sealed cells
    only after the checks of its first opening: without a consent, with the legacy consent of the seven arms, or with a
    root manifest that no longer seals the services' anchors, the chain pauses at that read before anything of the unit
    is read or reopened (no sealed read, no mirror); after the owner's consent of C, S1..S5 it completes from the kept
    cells, opening no panel and sending no request for C again."""
    root = tmp_path / 'run'
    write_consent(root)
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    env['TMPDIR'] = str(NEUTRAL)
    code = CHILD_RUN % {'tree': str(TREE), 'root': str(root), 'point': 'finish:C-searchqa'}
    killed = subprocess.run([sys.executable, '-c', code], cwd=str(TREE), env=env, capture_output=True, text=True,
                            timeout=600)
    assert killed.returncode == -signal.SIGKILL, (killed.stdout[-2000:], killed.stderr[-3000:])
    unit, mirror = root / 'G' / 'test-read-C-searchqa', root / 'G' / 'read-status' / 'C-searchqa.json'
    assert (unit / 'done.json').exists() and not (unit / 'aggregate.json').exists() and not mirror.exists()
    kept = {p.name: p.read_bytes() for p in (unit / 'cells').glob('*.json')}
    assert len(kept) == 2 and state_of(root)['paused'] is None and 'read-C-searchqa' not in state_of(root)['done_units']
    sealed, existing, reopened, seen = [], [], [], []
    real_read_json, real_existing, real_reopen = units.read_json, reads._existing_status, units.reopen_stopped

    def spy_read_json(path, *, allow_sealed=False):
        if allow_sealed and 'test-read-' in str(path):
            sealed.append(str(path))
        return real_read_json(path, allow_sealed=allow_sealed)
    monkeypatch.setattr(units, 'read_json', spy_read_json)
    monkeypatch.setattr(reads, '_existing_status', lambda *a, **kw: existing.append(str(a[4])) or real_existing(*a, **kw))
    monkeypatch.setattr(units, 'reopen_stopped', lambda *a, **kw: (  # the sealed read units only
        reopened.append(str(a[0])) if kw.get('allow_sealed') else None) or real_reopen(*a, **kw))

    def resume(change):
        recovery(root)
        services = run_services(root, 'G', seen=seen, order=('searchqa',))  # seals the anchor C into the root again
        change()
        return chain.run(root, 'G', services=services, sleep=lambda s: None, resume=True), services

    def seven_root():  # the root's manifest re-sealed with typed-v2's anchors; the services and the consent keep C alone
        fields = {k: v for k, v in json.loads((root / 'manifest.json').read_text()).items()
                  if k not in ('record_sha256', 'read_anchors', 'arms')}
        units.write_json(root / 'manifest.json', prepare.seal(fields))
        write_consent(root)
    for change in (lambda: (root / 'shared' / 'consent.json').unlink(), lambda: write_consent(root, READ_ARMS),
                   seven_root):
        state, services = resume(change)
        assert (state['paused']['reason'], state['paused']['unit']) == ('exception:ValueError', 'read-C'), state['paused']
        assert sealed == existing == reopened == seen == [] and services.script.requests == []
        assert not (unit / 'aggregate.json').exists() and not mirror.exists() and (unit / 'done.json').exists()
    state, services = resume(lambda: write_consent(root))
    assert state['complete'] and state['paused'] is None
    assert state['done_units'] == expected_done(state['done_units'], C_EVENTS, order=('searchqa',))
    assert [r['paused'] and r['paused']['reason'] for r in state['recoveries']] == [None] + ['exception:ValueError'] * 3
    assert existing == reopened == [str(unit)] and sealed  # now the unit is answered from its sealed records
    assert {p.name: p.read_bytes() for p in (unit / 'cells').glob('*.json')} == kept and mirror.exists()
    assert json.loads(mirror.read_text())['status'] == 'complete' and (unit / 'aggregate.json').exists()
    assert seen == [('searchqa', 'G/test-read-S1-searchqa')]  # C is never opened again, S1 is read fresh
    assert not [u for _, u, _, _ in services.script.requests if u == 'test-read-C-searchqa']
