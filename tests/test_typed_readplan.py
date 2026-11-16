"""typed-v2 step rp-int: the economy read plan wired into prepare, the chain, the smoke and the replay (addendum D9,
D10, RP1 to RP13; spec/read-plan.md 1.A to 1.D, 4.2: T1-T6, T9-T12, T16-T19, T21, T23, T25, T26 at the integration
level). The pure core has its own tests (tests/test_typed_readplan_core.py).

Fakes only: the REAL pass, mount, identity, capture, reads, alias settling and replay code on the fake smoke services
(scripted replies, hash embeddings, ``fake_solve``); no network, no Docker, no /data, no model call. Scratch under
/tmp/typed2-neutral (resolved: route B's ``safe_path`` refuses a symlink in any parent, and /tmp is one on macOS).
"""
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from scripts import run_typed
from skillopt.execskill import typed, zebralogic
from skillopt.execskill.typed import ORDER, chain, library as library_, prepare, readplan, smoke, tasktypes, units
from tests.test_typed_reads import write_machinery, write_pools, write_tree, zebra_rows

NEUTRAL = Path('/tmp/typed2-neutral').resolve()
PROBE = ['C0', 'zebralogic']
NON_ZEBRA = [b for b in ORDER if b != 'zebralogic']


@pytest.fixture
def tmp_path():
    """A neutral, resolved directory: pytest's own tmp_path carries the word 'test' (refused by the sealed-path guard)."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='readplan-', dir=NEUTRAL))
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
def economy_manifest(base_card='historical', probe=PROBE, read_plan='economy'):
    return smoke.synthetic_manifest(schedule='learn_first', memory_lock='unit_shared', base_card=base_card,
                                    read_plan=read_plan, read_plan_probe=probe if read_plan == 'economy' else None)


def services_for(root, *, base_card='historical', probe=PROBE, read_plan='economy', scripted=None):
    root = smoke.smoke_root(root)
    return smoke.fake_services(root, 'G', economy_manifest(base_card, probe, read_plan), scripted=scripted)


def go(root, services=None, *, resume=False, stop_after_plan=False, **kw):
    services = services if services is not None else services_for(root, **kw)
    state = smoke.run(root, 'G', services=services, sleep=lambda s: None, resume=resume,
                      stop_after_plan=stop_after_plan)
    return state, services


def chain_dir(root):
    return smoke.smoke_root(root) / 'G'


def recovery(root, decision='continue'):
    units.write_json(chain_dir(root) / 'recovery.json', {'by': 'owner', 'date': '2026-11-12', 'decision': decision,
                                                         'same_phase': True})


def plan_of(root):
    return json.loads((chain_dir(root) / readplan.PLAN_FILE).read_text())


def sends(root):
    return json.loads((chain_dir(root) / 'ledger.json').read_text())['sends']


def fresh_units(state):
    return [u for u in state['done_units'] if u.startswith('read-') and u != readplan.PLAN_UNIT]


def alias_units(state):
    return [u for u in state['done_units'] if u.startswith('alias-')]


def classes(plan):
    return {bench: [(c['members'], c['representative']) for c in plan['benches'][bench]['classes']] for bench in ORDER}


def freeze_empty(directory, chain_name='G'):
    """s0..s5 frozen with an empty library and type map and their receipts (as ``_Run.freeze`` writes them): every
    step learned nothing, so ``learn(k)`` skips every step (its receipt exists)."""
    for k in range(6):
        step = Path(directory) / ('s%d' % k)
        library_.Library().save(step / 'library.json', step=k)
        tasktypes.TypeMap().freeze(step / 'typemap.json', step=k)
        units.write_json(step / chain.FROZEN, chain._sealed({
            'version': typed.VERSION, 'chain': chain_name, 'step': k, 'bench': None if k == 0 else ORDER[k - 1],
            **chain._frozen_hashes(step), 'at': '2026-11-12T00:00:00'}))


@pytest.fixture(scope='module')
def finished():
    """One uninterrupted economy fake smoke (base 'historical', the probe, in-process replay), read only."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='readplan-done-', dir=NEUTRAL))
    root = made / 'run'
    state, services = go(root)
    try:
        yield {'root': root, 'state': state, 'services': services}
    finally:
        shutil.rmtree(made, ignore_errors=True)


def copied(finished, tmp_path):
    """A copy of the finished smoke root to change."""
    target = tmp_path / 'run'
    shutil.copytree(smoke.smoke_root(finished['root']), smoke.smoke_root(target))
    return target


# ---- T1: manifest fields, constants -----------------------------------------------------------------------------
def test_read_plan_constants_are_re_exported_and_written_out():
    assert typed.READ_PLANS == readplan.READ_PLANS == ('full', 'economy') and typed.READ_PLAN_DEFAULT == 'full'
    assert typed.IDENTITY_VERSION == readplan.IDENTITY_VERSION and typed.PLAN_VERSION == readplan.PLAN_VERSION
    assert typed.READ_PLAN_PAUSES == readplan.PAUSE_REASONS and typed.READ_PLAN_REASONS is readplan.READ_PLAN_REASONS
    assert typed.SOLVER_SETTINGS_VERSION == 'typed-v2-solver-settings-1'
    assert run_typed.READ_PLANS == typed.READ_PLANS and run_typed.CHECKPOINTS == readplan.CHECKPOINTS
    assert set(chain.SCHEDULE_PAUSES) <= set(readplan.PAUSE_REASONS)
    assert smoke.CONFIGURED == {'schedule': 'learn_first', 'memory_lock': 'unit_shared', 'base_card': 'historical',
                                'read_plan': 'economy', 'read_plan_probe': ['C0', 'zebralogic']}
    with pytest.raises(AttributeError):
        typed.NOT_A_READ_PLAN_NAME


def test_prepare_seals_the_read_plan_and_refuses_forbidden_pairs(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  typed_tree=inputs['tree'], root_parent=str(parent))
    default = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', smoke=True, **common)
    assert default['read_plan'] == 'full' and default['read_plan_probe'] is None
    real = {'schedule': 'learn_first', 'read_plan': 'economy', 'smoke': False}  # a real manifest carries no probe key
    assert prepare.read_plan_of(real) == 'economy' and prepare.read_plan_probe_of(real) is None
    with pytest.raises(ValueError, match='smoke-only'):
        prepare.read_plan_of({**real, 'read_plan_probe': None})
    made = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', smoke=True, schedule='learn_first',
                           read_plan='economy', read_plan_probe=['C0', 'zebralogic'], **common)
    assert (made['read_plan'], made['read_plan_probe']) == ('economy', ['C0', 'zebralogic'])
    assert prepare.load_manifest(made['root']) == made and prepare.read_plan_probe_of(made) == ['C0', 'zebralogic']
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    assert prepare.seal({**fields, 'read_plan_probe': None})['record_sha256'] != made['record_sha256']
    refused = ({'read_plan': 'economy'},                                         # economy needs learn_first
               {'read_plan': 'cheap', 'schedule': 'learn_first'},
               {'read_plan': 'economy', 'schedule': 'learn_first', 'read_plan_probe': ['C0', 'zebralogic']},  # real
               {'read_plan_probe': ['C0', 'zebralogic'], 'smoke': True},           # probe with full
               {'read_plan': 'economy', 'schedule': 'learn_first', 'smoke': True, 'read_plan_probe': ['C9', 'x']})
    for n, bad in enumerate(refused):
        new = parent / ('execskill-2026112%d-typed-v3%s' % (n, '-smoke' if bad.get('smoke') else ''))
        with pytest.raises(ValueError):
            prepare.prepare(new, **{'smoke': False, **common, **bad})
        assert not new.exists()
    root = Path(made['root'])
    for change in ({'read_plan': None}, {'schedule': 'interleaved'}, {'read_plan': 'full'}):  # probe with full refused
        units.write_json(root / 'manifest.json', prepare.seal({**fields, **change}))
        with pytest.raises(ValueError, match='read_plan|read plan'):
            prepare.load_manifest(root)
    units.write_json(root / 'manifest.json', prepare.seal({k: v for k, v in fields.items() if k != 'read_plan'}))
    with pytest.raises(ValueError, match='read_plan'):
        prepare.load_manifest(root)


def test_a_resume_with_another_read_plan_is_a_hard_error(tmp_path):
    state = chain._open_state(tmp_path / 'G', 'G', 'smoke', False, schedule='learn_first', read_plan='economy')
    assert state['read_plan']['mode'] == 'economy' and set(state['read_plan']) == set(chain.READ_PLAN_STATE_KEYS)
    units.write_json(tmp_path / 'G' / 'state.json', state)
    with pytest.raises(ValueError, match='read_plan'):
        chain._open_state(tmp_path / 'G', 'G', 'smoke', True, schedule='learn_first', read_plan='full')
    assert chain._open_state(tmp_path / 'G', 'G', 'smoke', True, schedule='learn_first', read_plan='economy')


# ---- the configured smoke end to end (T3 class table, T11, T18, R46, S2 b) ---------------------------------------
def test_economy_smoke_reads_each_class_once_and_settles_every_other_pair(finished):
    root, state = finished['root'], finished['state']
    assert state['complete'] and state['paused'] is None and state['phase'] is None
    plan = readplan.verify_plan(plan_of(root), plan_sha256=state['read_plan']['plan_sha256'])
    counts = plan['counts']
    assert counts['pairs'] == 35 and counts['fresh'] == len(fresh_units(state)) and counts['alias'] == len(alias_units(state))
    assert counts['fresh'] + counts['alias'] == 35 and state['read_plan']['replay']['verdict'] == 'equal'
    # every pair settled exactly once, the plan unit first, the step markers last
    done = state['done_units']
    pairs = [u.split('-', 1)[1] for u in fresh_units(state) + alias_units(state)]
    assert len(pairs) == len(set(pairs)) == 35
    assert done.index(readplan.PLAN_UNIT) < min(done.index(u) for u in fresh_units(state))
    assert done[-6:] == ['step-%d' % k for k in range(6)]
    # the read order: S5 on the five panels first (D10 e), then the rest in descending event order
    order = [u for u in done if u.startswith('read-') and u != readplan.PLAN_UNIT]
    assert order[:5] == ['read-S5-%s' % b for b in ORDER]
    events = [u.split('-')[1] for u in order]
    assert events == sorted(events, key=lambda e: -readplan.EVENTS.index(e))
    # the representatives are exactly the fresh units; every alias names its representative and verifies
    for bench in ORDER:
        for members, representative in classes(plan)[bench]:
            assert 'read-%s-%s' % (representative, bench) in done
            for member in members:
                if member != representative:
                    assert 'alias-%s-%s' % (member, bench) in done
                    entry = state['reads'][member][bench]
                    assert entry['kind'] == 'alias' and entry['alias_of'] == representative
                    mirror = json.loads((chain_dir(root) / 'read-status' / ('%s-%s.json' % (representative, bench))).read_text())
                    record = readplan.load_alias(readplan.alias_path(smoke.smoke_root(root), 'G', member, bench), plan,
                                                 representative_aggregate_sha256=mirror['aggregate_sha256'])
                    assert record['check'] == {'items': 2, 'equal': 2, 'unequal': 0}
                    assert not (chain_dir(root) / ('practice-read-%s-%s' % (member, bench))).exists()
    # the probe (S1 c): C0 on ZebraLogic is its own class with reason smoke_probe, its lists equal to C's
    zebra = plan['benches']['zebralogic']['events']
    assert zebra['C0']['reason'] == 'smoke_probe' and zebra['C0']['status'] == 'fallback'
    assert zebra['C0']['identity_list_sha256'] == zebra['C']['identity_list_sha256']
    assert zebra['C0']['first_request_list_sha256'] == zebra['C']['first_request_list_sha256']
    assert counts['fallback'] == 1 and ['C0'] in [m for m, _ in classes(plan)['zebralogic']]
    # base 'historical' (R91 b): C0 is a class of its own on every other bench, C never with C0
    for bench in NON_ZEBRA:
        assert (['C0'], 'C0') in classes(plan)[bench]


def test_fresh_units_are_the_full_units_and_their_first_requests_are_the_captures(finished):
    """T18, X2: a fresh unit under economy is the unit full would run (name, cell tags, items) and every fresh cell
    of an item without offered programs sent exactly the captured first request."""
    root, state = finished['root'], finished['state']
    base = chain_dir(root)
    plan = plan_of(root)
    checked = 0
    for unit in fresh_units(state):
        _, event, bench = unit.split('-', 2)
        identities = readplan.load_sealed(readplan.identities_path(smoke.smoke_root(root), 'G', bench, smoke=True),
                                          'identities', file_sha256=plan['benches'][bench]['identities_sha256'])
        entry = identities['events'][event]
        folder = base / ('practice-read-%s-%s' % (event, bench))
        assert folder.is_dir()
        for item_id, first in zip(identities['item_ids'], entry['first_request'] or [None] * len(identities['item_ids'])):
            row = json.loads((folder / 'cells' / (units.cell_tag(bench, item_id, readplan.arm_of(event)) + '.json')).read_text())
            assert row['unit'] == 'practice-read-%s-%s' % (event, bench)
            if first is not None:
                assert row['request_sha256'][0] == first
                checked += 1
    assert checked >= 20


def test_the_pass_sends_nothing_and_writes_only_its_files(tmp_path):
    """T11 with the R77 stop: the ledger is unchanged across the pass (no unit 'read-plan', no read unit yet), the
    only new files are the sealed inputs and identities, read-plan.json and the state."""
    root = tmp_path / 'run'
    state, services = go(root, stop_after_plan=True)
    assert state['paused']['reason'] == 'stopped_after_plan' and state['paused']['unit'] == readplan.PLAN_UNIT
    ledger = json.loads((chain_dir(root) / 'ledger.json').read_text())
    assert readplan.PLAN_UNIT not in (ledger.get('by_unit') or {})
    assert not any(str(unit).startswith(('practice-read-', 'read-')) for unit in (ledger.get('by_unit') or {}))
    assert not any(p.name.startswith('practice-read-C') or p.name.startswith('practice-read-S') for p in chain_dir(root).iterdir())
    sealed = sorted(p.name for p in (chain_dir(root) / readplan.SMOKE_SEALED_DIR).iterdir())
    assert sealed == sorted([readplan.inputs_name(b) for b in ORDER] + [readplan.identities_name(b) for b in ORDER])
    assert (chain_dir(root) / readplan.PLAN_FILE).is_file() and not (chain_dir(root) / readplan.ALIAS_DIR).exists()
    calls = list(services.script.calls)
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['complete'] and services.script.calls[:len(calls)] == calls


def test_open_records_and_the_state_hold_hashes_and_counts_only(finished):
    """T23: read-plan.json, every alias record, solver-settings.json and the read-plan parts of state.json hold no
    item id, no text over 64 characters outside hashes and no reason outside READ_PLAN_REASONS."""
    root, state = finished['root'], finished['state']
    base = chain_dir(root)
    ids = [item['task_id'] for rows in finished['services'].items.values() for item in rows]
    texts = [json.dumps(item['public'], sort_keys=True)[:40] for rows in finished['services'].items.values()
             for item in rows]
    records = [json.loads((base / readplan.PLAN_FILE).read_text())]
    records += [json.loads(p.read_text()) for p in sorted((base / readplan.ALIAS_DIR).glob('*.json'))]
    records.append({'read_plan': state['read_plan'], 'reads': {  # the read-plan parts of the state (RP13 on T23)
        e: {b: v for b, v in r.items() if v.get('kind') in ('alias', 'void_alias')} for e, r in state['reads'].items()}})
    for record in records:
        assert readplan.open_record_violations(record, item_ids=ids, texts=texts) == []
    settings = json.loads((base / readplan.SOLVER_SETTINGS_FILE).read_text())
    assert readplan.open_record_violations(settings, item_ids=ids, texts=texts, allow_floats=True) == []
    for path in [base / readplan.PLAN_FILE, base / readplan.SOLVER_SETTINGS_FILE, base / 'state.json',
                 *sorted((base / readplan.ALIAS_DIR).glob('*.json'))]:
        text = path.read_text()
        assert not any(i in text for i in ids), path.name


# ---- T3: every event identical, both base values (R91 a, b; R40 best case) -------------------------------------
@pytest.mark.parametrize('base_card', ['historical', 'format'])
def test_an_empty_library_at_every_step_reads_nine_units(tmp_path, base_card):
    root = tmp_path / 'run'
    freeze_empty(chain_dir(root))
    state, services = go(root, base_card=base_card, probe=None)
    assert state['complete'], state['paused']
    plan = plan_of(root)
    found = classes(plan)
    assert found['zebralogic'] == [(list(readplan.EVENTS), 'S5')]
    for bench in NON_ZEBRA:
        if base_card == 'historical':
            assert found[bench] == [(['C0'], 'C0'), (['C', 'S1', 'S2', 'S3', 'S4', 'S5'], 'S5')]
        else:
            assert found[bench] == [(['C0', 'S1', 'S2', 'S3', 'S4', 'S5'], 'S5'), (['C'], 'C')]
    assert plan['counts'] == {'pairs': 35, 'fresh': 9, 'alias': 26, 'fallback': 0}
    assert len(fresh_units(state)) == 9 and len(alias_units(state)) == 26
    assert not any(u.startswith('s') and '/' in u for u in state['done_units'])  # nothing learned, nothing re-learned


# ---- RP13: the pass mounts with exactly the loaded frozen objects -----------------------------------------------
def during_pass(monkeypatch):
    """A flag that is on while ``readplan.run_pass`` runs (the pass's own calls only)."""
    flag, real = {'on': False}, readplan.run_pass

    def run_pass(*a, **kw):
        flag['on'] = True
        try:
            return real(*a, **kw)
        finally:
            flag['on'] = False
    monkeypatch.setattr(readplan, 'run_pass', run_pass)
    return flag


def test_the_pass_mounts_every_item_with_the_frozen_objects_it_records(tmp_path, monkeypatch):
    root = tmp_path / 'run'
    loaded, real = [], chain.frozen_state  # the loaded objects themselves (kept alive: compared by identity)

    def recording(directory, chain_name, k):
        found = real(directory, chain_name, k)
        loaded.append((k, found[1], found[2]))
        return found
    monkeypatch.setattr(chain, 'frozen_state', recording)
    flag = during_pass(monkeypatch)
    services = services_for(root)
    used, mount, identity = [], services.mount_fn, services.identity_fn

    def mount_fn(bench, item, **kw):
        if flag['on']:
            assert kw['selector'] is readplan.capture_selector
            used.append(('mount', kw['arm'], kw['library'], kw['typemap']))
        return mount(bench, item, **kw)

    def identity_fn(bench, item, **kw):
        if flag['on']:
            used.append(('identity', kw['arm'], kw['library'], kw['typemap']))
        return identity(bench, item, **kw)
    services.mount_fn, services.identity_fn = mount_fn, identity_fn
    state, _ = go(root, services, stop_after_plan=True)
    assert state['paused']['reason'] == 'stopped_after_plan'
    assert used and {kind for kind, *_ in used} == {'mount', 'identity'}

    def step_of(library, typemap):
        found = [k for k, lib, tm in loaded if lib is library and tm is typemap]
        assert found, 'a mount call got a library / type map pair the loader did not return'
        return found[0]
    steps = Counter((arm == 'F', step_of(lib, tm)) for _, arm, lib, tm in used)
    # C0 and C mount the s0 objects, F the objects of each S step: all six loaded states used, none mixed or foreign
    assert {k for (f, k) in steps if not f} == {0} and {k for (f, k) in steps if f} == {1, 2, 3, 4, 5}
    assert {arm for _, arm, *_ in used} == {'C0', 'C', 'F'}


# ---- T19: fallbacks without a removed read ---------------------------------------------------------------------
def test_an_identity_exception_makes_its_pair_a_class_of_its_own(tmp_path):
    root = tmp_path / 'run'
    services = services_for(root)
    identity = services.identity_fn

    def broken(bench, item, **kw):
        if bench == 'officeqa' and kw['arm'] == 'C':
            raise RuntimeError('identity failed')
        return identity(bench, item, **kw)
    services.identity_fn = broken
    state, _ = go(root, services)
    assert state['complete'], state['paused']
    events = plan_of(root)['benches']['officeqa']['events']
    assert events['C']['status'] == 'fallback' and events['C']['reason'] == 'identity_exception'
    assert 'read-C-officeqa' in state['done_units']


def test_a_capture_without_exactly_one_send_is_capture_failed(tmp_path, monkeypatch):
    root = tmp_path / 'run'
    monkeypatch.setattr(readplan.CaptureCall, 'first_request', lambda self: None)
    state, _ = go(root)
    assert state['complete'], state['paused']
    plan = plan_of(root)
    for bench in readplan.FIRST_REQUEST_BENCHES:
        reasons = {e: plan['benches'][bench]['events'][e]['reason'] for e in readplan.EVENTS}
        assert 'capture_failed' in reasons.values(), bench
    assert all(plan['benches']['alfworld']['events'][e]['reason'] != 'capture_failed' for e in readplan.EVENTS)


def test_an_unstable_second_embedder_run_reads_its_events_fresh(tmp_path, monkeypatch):
    """R30: the pass's second embedder batch moves every item far from every source; the S events whose identity
    lists change are embedder_unstable fallbacks and read fresh."""
    root = tmp_path / 'run'
    flag = during_pass(monkeypatch)
    services = services_for(root)
    calls = {'n': 0}

    def embed(texts):
        rows = smoke.hash_embedder(texts)
        if flag['on']:
            calls['n'] += 1
            if calls['n'] % 2 == 0:  # the second run of each bench
                return [[-x for x in row] for row in rows]
        return rows
    services.embed = embed
    state, _ = go(root, services)
    assert state['complete'], state['paused']
    plan = plan_of(root)
    unstable = [(b, e) for b in ORDER for e, row in plan['benches'][b]['events'].items()
                if row['reason'] == 'embedder_unstable']
    assert unstable and all(e.startswith('S') for _, e in unstable)
    assert all('read-%s-%s' % (e, b) in state['done_units'] for b, e in unstable)
    assert calls['n'] == 10


def test_a_post_read_mismatch_voids_every_alias_of_its_bench_and_reads_them_fresh(tmp_path, monkeypatch):
    """RP10, R42: no pause; every alias of the bench (the ones an earlier representative settled included) voided
    and read fresh; the representative already read is not read again (each pair at most once). In the scripted
    smoke SpreadsheetBench has the classes {C0}, {C, S1, S2, S3} > S3 and {S4, S5} > S5: S5 settles S4 first, then
    S3's check fails."""
    root = tmp_path / 'run'
    real = readplan.check_representative

    def check(root_, chain_, plan, event, bench, **kw):
        found = real(root_, chain_, plan, event, bench, **kw)
        if bench == 'spreadsheetbench' and event == 'S3':
            return {**found, 'equal': found['equal'] - 1, 'unequal': found['unequal'] + 1}
        return found
    monkeypatch.setattr(readplan, 'check_representative', check)
    state, services = go(root)
    assert state['complete'], state['paused']
    plan = plan_of(root)
    assert classes(plan)['spreadsheetbench'] == [(['C0'], 'C0'), (['C', 'S1', 'S2', 'S3'], 'S3'), (['S4', 'S5'], 'S5')]
    fallbacks = state['read_plan']['fallbacks']
    assert fallbacks == {'spreadsheetbench': {'event': 'S3', 'reason': 'post_read_mismatch', 'unequal': 1}}
    for event in readplan.EVENTS:  # every sheet pair fresh exactly once; S4's settled alias was voided and archived
        assert state['done_units'].count('read-%s-spreadsheetbench' % event) == 1
        assert 'alias-%s-spreadsheetbench' % event not in state['done_units']
        folder = chain_dir(root) / ('practice-read-%s-spreadsheetbench' % event)
        assert json.loads((folder / 'done.json').read_text())['cells'] == 2
    archived = sorted(p.name for p in (chain_dir(root) / readplan.ALIAS_DIR / readplan.ARCHIVE_DIR).glob('*.json'))
    assert archived == ['S4-spreadsheetbench-1.json']
    order = [u for u in state['done_units'] if u.endswith('-spreadsheetbench') and u.startswith('read-')]
    assert order[-1] == 'read-S4-spreadsheetbench'  # passed in the first sweep: read in the final sweep
    assert alias_units(state) and not any(u.endswith('-spreadsheetbench') for u in alias_units(state))


def test_a_failing_check_of_a_singleton_representative_voids_its_bench(tmp_path, monkeypatch):
    """Codex review round 3: a representative without members (SpreadsheetBench's C0 in the scripted smoke) is still
    checked after its read; its mismatch voids every alias of the bench (RP10) exactly as for a representative with
    members, and every sheet pair is then read fresh exactly once."""
    root = tmp_path / 'run'
    real = readplan.check_representative
    calls = []

    def check(root_, chain_, plan, event, bench, **kw):
        found = real(root_, chain_, plan, event, bench, **kw)
        calls.append((event, bench))
        if bench == 'spreadsheetbench' and event == 'C0':
            return {**found, 'equal': found['equal'] - 1, 'unequal': found['unequal'] + 1}
        return found
    monkeypatch.setattr(readplan, 'check_representative', check)
    state, services = go(root)
    assert state['complete'], state['paused']
    assert classes(plan_of(root))['spreadsheetbench'][0] == (['C0'], 'C0') and ('C0', 'spreadsheetbench') in calls
    assert state['read_plan']['fallbacks'] == {
        'spreadsheetbench': {'event': 'C0', 'reason': 'post_read_mismatch', 'unequal': 1}}
    for event in readplan.EVENTS:
        assert state['done_units'].count('read-%s-spreadsheetbench' % event) == 1
        assert 'alias-%s-spreadsheetbench' % event not in state['done_units']


def test_a_pass_failing_twice_with_one_code_voids_the_plan_and_reads_all_35_pairs(tmp_path, monkeypatch):
    """RP11, Q24 option A: a non-stop exception of the pass's own code is read_plan_failed (pass_exception); the
    recovery re-runs the pass; the second failure with the same code voids the plan and the chain completes."""
    root = tmp_path / 'run'
    monkeypatch.setattr(readplan, 'compute_files', lambda *a, **k: (_ for _ in ()).throw(KeyError('PLANTED-ID')))
    state, services = go(root)
    assert state['paused']['reason'] == 'read_plan_failed' and state['paused']['detail'] == 'pass_exception'
    assert 'PLANTED' not in json.dumps(state)
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['complete'], state['paused']
    assert state['read_plan']['void'] is True and state['read_plan']['void_reason'] == 'pass_failed'
    assert state['read_plan']['failures'] == ['pass_exception', 'pass_exception']
    assert len(fresh_units(state)) == 35 and not alias_units(state)


# ---- T21: learning closed once reading has begun -----------------------------------------------------------------
def test_a_missing_receipt_after_the_plan_pauses_without_any_learning(tmp_path):
    root = tmp_path / 'run'
    state, services = go(root, stop_after_plan=True)
    before = len(services.script.calls)
    (chain_dir(root) / 's3' / chain.FROZEN).unlink()
    listing = sorted(p.name for p in (chain_dir(root) / 's3').iterdir())
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['paused']['reason'] == 'frozen_state_changed' and state['paused']['unit'] == 's3'
    assert len(services.script.calls) == before and sorted(p.name for p in (chain_dir(root) / 's3').iterdir()) == listing


# ---- T9: tampering and recovery ---------------------------------------------------------------------------------
def test_an_edited_plan_pauses_and_is_restored_by_the_recovery(tmp_path):
    root = tmp_path / 'run'
    state, services = go(root, stop_after_plan=True)
    path = chain_dir(root) / readplan.PLAN_FILE
    original = path.read_bytes()
    path.write_bytes(original.replace(b'"fresh": ', b'"fresh":  '))
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['paused']['reason'] == 'read_plan_changed' and state['paused']['detail'] == 'plan_file_mismatch'
    recovery(root, 'restore the plan')
    state, services = go(root, services, resume=True)
    assert state['complete'], state['paused']
    assert path.read_bytes() == original and state['read_plan']['void'] is False
    outcomes = [r['outcome'] for r in state['read_plan']['recoveries']]
    assert 'plan_restored' in outcomes and 'replay_equal' in outcomes
    assert list(chain_dir(root).glob(readplan.PLAN_FILE + '.archived-*'))


def test_an_edited_sealed_file_voids_the_plan_after_the_recovery(tmp_path):
    root = tmp_path / 'run'
    state, services = go(root, stop_after_plan=True)
    path = readplan.identities_path(smoke.smoke_root(root), 'G', 'officeqa', smoke=True)
    path.write_bytes(path.read_bytes().replace(b'"status": "ok"', b'"status":  "ok"', 1))
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['paused']['reason'] == 'read_plan_changed' and state['paused']['detail'] == 'sealed_file_mismatch'
    recovery(root, 'void it')
    state, services = go(root, services, resume=True)
    assert state['complete'], state['paused']
    assert state['read_plan']['void_reason'] == 'sealed_file_invalid' and len(fresh_units(state)) == 35


def test_a_deleted_alias_record_pauses_and_is_settled_again_with_equal_bytes(tmp_path, monkeypatch):
    root = tmp_path / 'run'
    real, stops = chain._Run.complete_reads, {'n': 1}

    def stop_once(self, plan):
        if stops['n']:
            stops['n'] -= 1
            raise chain.Paused('read_plan_incomplete', 'read-plan', 'scripted')
        return real(self, plan)
    monkeypatch.setattr(chain._Run, 'complete_reads', stop_once)
    state, services = go(root)
    assert state['paused']['detail'] == 'scripted'
    victim = sorted((chain_dir(root) / readplan.ALIAS_DIR).glob('*.json'))[0]
    stored = victim.read_bytes()
    victim.unlink()
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['paused']['reason'] == 'read_alias_invalid'
    recovery(root, 'settle again')
    state, services = go(root, services, resume=True)
    assert state['complete'], state['paused']
    assert victim.read_bytes() == stored
    assert 'alias_unsettled' in [r['outcome'] for r in state['read_plan']['recoveries']]


# ---- T10, T26: the replay -------------------------------------------------------------------------------------------
def test_the_in_process_replay_is_equal_and_finds_every_planted_difference(finished, tmp_path):
    root = copied(finished, tmp_path)
    services = services_for(root)
    services.root = smoke.smoke_root(root)
    services.slices = smoke.smoke_slices(services.items, services.slices)
    found = chain.in_process_replay(services, chain_dir(root))
    assert found['verdict'] == 'equal' and found['different'] == found['missing'] == 0 and found['files'] == 11
    assert found['reembedded'] == 0
    # the heavy lock is never entered by a replay (ADV5)
    services.heavy = lambda bench, unit=None: (_ for _ in ()).throw(AssertionError('heavy entered'))
    assert chain.in_process_replay(services, chain_dir(root))['verdict'] == 'equal'
    # mounts built on another base than the manifest's: different
    other = services_for(root, base_card='format')
    other.root, other.slices = services.root, smoke.smoke_slices(other.items, other.slices)
    assert chain.in_process_replay(other, chain_dir(root))['verdict'] == 'different'
    # a changed inputs file, a changed frozen file: different (with a fixed code)
    inputs = readplan.inputs_path(services.root, 'G', 'searchqa', smoke=True)
    saved = inputs.read_bytes()
    inputs.write_bytes(saved.replace(b'"chain": "G"', b'"chain":  "G"'))
    assert chain.in_process_replay(services, chain_dir(root))['code'] == 'inputs_mismatch'
    inputs.write_bytes(saved)
    library = chain_dir(root) / 's3' / 'library.json'
    library.write_bytes(library.read_bytes() + b'\n')
    found = chain.in_process_replay(services, chain_dir(root))
    assert found['verdict'] == 'different' and found['code'] == 'frozen_state_changed'


def test_a_real_root_replay_without_the_qualification_is_different_and_starts_nothing(tmp_path):
    services = services_for(tmp_path / 'run')
    found = readplan.replay(services, tmp_path, 'G', smoke=False, header={}, load=None)
    assert (found['verdict'], found['code']) == ('different', 'qualification_missing')
    assert not (tmp_path / 'shared').exists()


def test_the_automatic_replay_runs_in_a_fresh_process_with_another_hash_seed(tmp_path, monkeypatch):
    """T26 with the real child process: equal, then a planted difference pauses read_plan_changed (replay_different)
    and the second difference after the recovery voids the plan; the seed is recorded and differs from the parent's."""
    monkeypatch.setenv('PYTHONHASHSEED', '41')
    root = tmp_path / 'run'
    services = smoke.fake_services(smoke.smoke_root(root), 'G', smoke.smoke_manifest(smoke.smoke_root(root), fake=True,
                                                                                    configured=True))
    services.replay = chain.replay_child(fake=True, smoke=True)
    state, services = go(root, services, stop_after_plan=True)
    assert state['paused']['reason'] == 'stopped_after_plan'
    assert state['read_plan']['replay'] == {'verdict': 'equal', 'at': state['read_plan']['replay']['at'], 'hash_seed': 42}
    # a second root: the child sees another base (a mount built with 'format'): different, then void
    other = tmp_path / 'other'
    services = smoke.fake_services(smoke.smoke_root(other), 'G', smoke.smoke_manifest(smoke.smoke_root(other), fake=True,
                                                                                     configured=True))
    services.replay = chain.replay_child(fake=True, smoke=True, base_card='format')
    state, services = go(other, services)
    assert state['paused']['reason'] == 'read_plan_changed' and state['paused']['detail'] == 'replay_different'
    assert not fresh_units(state)  # no read unit before the replay is equal
    recovery(other)
    state, services = go(other, services, resume=True)
    assert state['complete'] and state['read_plan']['void_reason'] == 'replay_different'
    assert len(fresh_units(state)) == 35


def test_a_replay_error_pauses_and_the_same_error_again_voids_the_plan(tmp_path):
    root = tmp_path / 'run'
    services = services_for(root)
    services.replay = lambda root_, chain_, *, environ: {'verdict': 'error', 'code': 'exit_-9'}
    state, services = go(root, services)
    assert state['paused']['reason'] == 'read_plan_changed' and state['paused']['detail'] == 'replay_error:exit_-9'
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['complete'] and state['read_plan']['void_reason'] == 'replay_error'
    assert state['read_plan']['failures'] == ['replay_error:exit_-9'] * 2


def test_a_replay_error_after_an_equal_replay_and_a_restored_plan_is_a_first_strike_again(tmp_path):
    """R44 d (fix-c, rc-plan-1): a replay error voids the plan only when the PREVIOUS recovery outcome was a replay
    error with the same code, never because an older, resolved one is in the failure history. Error, recovery, equal
    replay, reads settle aliases and stop inside C0's fresh unit; then the plan file fails its check, the recovery
    restores it and the check replay errs with the first error's code: that pauses again (every settled alias kept),
    and only a recovery after it reads on (here with an equal replay; the plan is never void)."""
    root = tmp_path / 'run'
    services = services_for(root)
    verdicts = [{'verdict': 'error', 'code': 'timeout'}, {'verdict': 'equal'}, {'verdict': 'error', 'code': 'timeout'},
                {'verdict': 'equal'}]
    services.replay = lambda root_, chain_, *, environ: verdicts.pop(0)
    solve, broken = services.solve_fn, {'on': True}

    def flaky(bench, item, mounted, *, call, unit, **kw):   # the read cell, not the pass's zero-call capture
        if broken['on'] and unit == 'practice-read-C0-searchqa' and not isinstance(call, readplan.CaptureCall):
            broken['on'] = False
            raise units.Stop('scripted stop inside a fresh unit')
        return solve(bench, item, mounted, call=call, unit=unit, **kw)
    services.solve_fn = flaky
    state, services = go(root, services)
    assert (state['paused']['reason'], state['paused']['detail']) == ('read_plan_changed', 'replay_error:timeout')
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['paused']['unit'] == 'read-C0-searchqa' and state['read_plan']['replay']['verdict'] == 'equal'
    settled = alias_units(state)
    assert settled and not state['read_plan']['void']
    path = chain_dir(root) / readplan.PLAN_FILE
    original = path.read_bytes()
    path.chmod(0o644)
    path.write_bytes(original.replace(b'"fresh": ', b'"fresh":  '))
    recovery(root)
    state, services = go(root, services, resume=True)
    assert (state['paused']['reason'], state['paused']['detail']) == ('read_plan_changed', 'plan_file_mismatch')
    recovery(root, 'restore the plan')
    state, services = go(root, services, resume=True)
    assert state['paused'] is not None, 'the restored plan was voided by an old, resolved replay error'
    assert (state['paused']['reason'], state['paused']['detail']) == ('read_plan_changed', 'replay_error:timeout')
    assert path.read_bytes() == original and not state['read_plan']['void'] and alias_units(state) == settled
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['complete'] and not state['read_plan']['void'] and verdicts == []
    assert state['read_plan']['failures'] == ['replay_error:timeout'] * 2
    assert [(r['n'], r['outcome']) for r in state['read_plan']['recoveries']] == [
        (1, 'replay_equal'), (3, 'plan_restored'), (3, 'paused_again'), (4, 'replay_equal')]


# ---- T25: the solver settings record ------------------------------------------------------------------------------
def test_the_solver_settings_record_is_credential_free_write_once_and_written_under_full(tmp_path):
    block = {'backend': 'northgate', 'model': 'deepseek-v4-flash', 'url_host': 'api.example.org', 'route': 'B',
             'env_path': '/root/secret/northgate.env', 'proxy': 'http://user:pw@proxy:3128', 'reasoning_effort': 'none',
             'thinking': {'type': 'disabled'}, 'M': {b: 4096 for b in ORDER}, 'B': {b: 8192 for b in ORDER},
             'read_timeout': {b: 300 for b in ORDER}, 'response_model_ids': ['deepseek-v4-flash'],
             'client_source_sha': 'a' * 64}
    rows = {b: readplan.solver_settings_of_block(block, b, nominal=True) for b in ORDER}
    record = readplan.solver_settings_record('D', rows)
    text = json.dumps(record)
    assert 'secret' not in text and 'proxy' not in text and 'example.org' not in text and 'pw' not in text
    assert record['benches']['searchqa'] == {'model': 'deepseek-v4-flash', 'route': 'northgate/B', 'max_tokens': 8192,
                                             'nominal_tokens': 4096, 'thinking': {'type': 'disabled'},
                                             'reasoning_effort': 'none', 'response_model_ids': ['deepseek-v4-flash'],
                                             'read_timeout': 300}
    with pytest.raises(ValueError):
        readplan.solver_settings_record('D', {**rows, 'searchqa': {**rows['searchqa'], 'route': 'https://x.org/v1'}})
    # under 'full' too, and a resume with a changed value pauses before any call
    root = tmp_path / 'run'
    services = services_for(root, read_plan='full', probe=None)
    state, services = go(root, services)
    assert state['complete'] and (chain_dir(root) / readplan.SOLVER_SETTINGS_FILE).is_file()
    assert not (chain_dir(root) / readplan.PLAN_FILE).exists() and not (chain_dir(root) / readplan.ALIAS_DIR).exists()
    assert state['solver_settings_sha256'] == readplan.bytes_sha256((chain_dir(root) / readplan.SOLVER_SETTINGS_FILE).read_bytes())
    state['complete'] = False
    units.write_json(chain_dir(root) / 'state.json', state)
    before = sends(root)
    services.solver_settings = {b: {**row, 'max_tokens': 1} for b, row in services.solver_settings.items()}
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['paused']['reason'] == 'solver_settings_changed' and sends(root) == before


# ---- T17: learn_first with full keeps the schedule-lock reads ------------------------------------------------------
def test_learn_first_with_full_reads_every_pair_fresh_and_writes_no_plan(tmp_path):
    root = tmp_path / 'run'
    freeze_empty(chain_dir(root))
    state, _ = go(root, read_plan='full', probe=None)
    assert state['complete'] and len(fresh_units(state)) == 35 and not alias_units(state)
    assert readplan.PLAN_UNIT not in state['done_units'] and not (chain_dir(root) / readplan.SMOKE_SEALED_DIR).exists()
    assert state['read_plan'] == {**state['read_plan'], 'mode': 'full', 'plan_sha256': None, 'void': False}


# ---- T16: a stop inside a fresh unit (P5) -------------------------------------------------------------------------
def test_a_stop_inside_a_fresh_unit_resumes_without_sending_a_finished_cell_again(tmp_path):
    root = tmp_path / 'run'
    services = services_for(root)
    solve, broken = services.solve_fn, {'on': True}

    def flaky(bench, item, mounted, *, call, unit, **kw):
        if broken['on'] and unit == 'practice-read-S5-searchqa' and item['task_id'].endswith('1'):
            broken['on'] = False
            raise units.Stop('scripted stop inside a fresh unit')
        return solve(bench, item, mounted, call=call, unit=unit, **kw)
    services.solve_fn = flaky
    state, services = go(root, services)
    assert state['paused'] is not None and state['paused']['unit'].startswith('read-S5')
    cells_dir = chain_dir(root) / 'practice-read-S5-searchqa' / 'cells'
    done_cells = {p.name: p.read_bytes() for p in cells_dir.glob('*.json')}
    sent = len(services.script.calls)
    recovery(root)
    state, services = go(root, services, resume=True)
    assert state['complete'], state['paused']
    rows = [json.loads(p.read_text()) for p in (chain_dir(root) / 'practice-read-S5-searchqa' / 'cells').glob('*.json')]
    assert len(rows) == 2 and all(len(row['sends']) == 1 for row in rows) and done_cells
    # fix-c (review F2): a re-solved cell would rewrite its file with a new one-send row, so the rows above cannot tell
    # a kept cell from a re-sent one. The resume sends exactly the solver requests of the cells missing at the stop,
    # and every cell finished before the stop keeps its file byte for byte.
    resent = [purpose for purpose, unit in services.script.calls[sent:] if unit == 'practice-read-S5-searchqa']
    assert resent.count('solver') == len(rows) - len(done_cells) == 1 and set(resent) <= {'solver', 'selection'}
    assert {name: (cells_dir / name).read_bytes() for name in done_cells} == done_cells


# ---- T12: consent, registry, qualification and the ALFWorld resets of the pass on a real root ----------------------
def test_the_pass_opens_real_panels_under_consent_with_registry_qualification_and_locked_resets(tmp_path, monkeypatch):
    """R21-R23 (ADV13, I-15): on a real root nothing is opened without consent; with it the pass's panel path writes
    the five registry entries, runs the SpreadsheetBench qualification once under the heavy lock with the plan's
    label, and wraps every ALFWorld preparation reset with ``v218_lock.call`` under 'unit_shared' (bare under
    'per_cell_plain'); a re-run with stored inputs starts no environment; the replay then finds the registry and the
    qualification pointer."""
    import contextlib
    from types import SimpleNamespace
    from skillopt.coevo5 import data
    from skillopt.execskill import evaluation, v218_lock
    from skillopt.validator_pilot.api import digest
    from tests.test_typed_reads import fake_panel, minimal_manifest, write_consent
    root = tmp_path / 'execskill-20261112-typed-v2'
    record = minimal_manifest(root, pinned={'paths': {}, 'sha256': {}, 'zebralogic': {}}, schedule='learn_first',
                              read_plan='economy', memory_lock='unit_shared')
    opened, resets, wraps, held, qualified = [], [], [], [], []
    monkeypatch.setattr(data, 'test_panel', lambda pinned, bench, *, access: opened.append((bench, access.unit)) or
                        fake_panel(bench, game=bench == 'alfworld')(pinned, bench, access=access))
    monkeypatch.setattr(zebralogic, 'test_panel', lambda pinned, bench, *, access: opened.append((bench, access.unit)) or
                        fake_panel(bench)(pinned, bench, access=access))

    def qualification(shared, tasks, runtime, **kw):
        qualified.append(list(held))
        (Path(shared) / 'test' / 'spreadsheetbench-qualification.json').write_text('{}')
        return {'side': 'test', 'task_hashes': {t['task_id']: digest(t) for t in tasks},
                'qualified': [t['task_id'] for t in tasks]}
    monkeypatch.setattr(evaluation, '_sheet_qualification', qualification)

    def fake_reset(runtime, episodes):
        def reset(public):
            resets.append(public['game_file'])
            return 'You are in a room.\n\nYour task is to: put a book on the desk.', ['look']
        return reset
    monkeypatch.setattr(evaluation, 'alfworld_reset', fake_reset)
    monkeypatch.setattr(v218_lock, 'call', lambda function, setting, *benches, **kw: wraps.append((benches, kw)) or function)

    @contextlib.contextmanager
    def heavy(bench, unit=None):
        held.append((bench, unit))
        yield
        held.remove((bench, unit))
    services = SimpleNamespace(order=ORDER, manifest=record, runtime={b: {} for b in ORDER}, native=None,
                               view_fn=lambda bench, item: item['public'].get('routing_view', item['public']),
                               heavy=heavy, embed=smoke.hash_embedder, chain='G', mode='run',
                               episodes=SimpleNamespace(hold=contextlib.nullcontext), lock_setting=object())
    with pytest.raises(ValueError, match='consent'):
        readplan.open_plan_panels(services, root, 'G', smoke=False, stored={}, lock=True)
    assert opened == [] and not (root / 'shared' / 'test').exists() and resets == []
    write_consent(root / 'shared')
    panels = readplan.open_plan_panels(services, root, 'G', smoke=False, stored={}, lock=True)
    assert sorted(opened) == sorted((b, 'G/test-read-plan') for b in ORDER)
    assert qualified == [[('spreadsheetbench', 'test-read-plan')]] and held == []
    assert len(resets) == 4 and wraps == [(('alfworld',), {'unit': 'G/test-read-plan'})]
    hashes = readplan.registry_hashes(root, smoke=False)
    assert all(readplan.is_hash(hashes[b]) for b in ORDER) and readplan.qualification_present(root)
    # per_cell_plain: the reset stays bare
    wraps.clear()
    services.lock_setting = None
    readplan.open_plan_panels(services, root, 'G', smoke=False, stored={}, lock=True)
    assert wraps == [] and len(resets) == 8
    # a re-run (or a replay) with stored inputs: the stored ALFWorld views, no live reset, no lock for a replay
    inputs = readplan.plan_inputs(services, 'G', panels, {})
    again = readplan.open_plan_panels(services, root, 'G', smoke=False, stored=inputs, lock=False)
    assert len(resets) == 8 and len(qualified) == 3 and qualified[-1] == []  # the replay form takes no heavy lock
    assert {i: readplan.view_sha256(v) for i, v in again['alfworld']['views'].items()} == \
        dict(zip(inputs['alfworld']['item_ids'], inputs['alfworld']['view_sha256']))
    assert readplan.plan_inputs(services, 'G', again, inputs) == inputs
