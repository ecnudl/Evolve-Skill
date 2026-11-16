"""typed-v2 identity (DESIGN 3.5, 4.4; addendum O4, D15): the version literals, the refusal of every typed-v1 root,
manifest, chain state, library and type map, ``prepare.own_root`` for every command and for ``reads.read_panel``,
the draw keys kept at their typed-v1 values, and the code constants the manifest seals and every load compares
(caps, draw keys, read widths, learning widths). Fakes only: no network, no /data, no model call."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from scripts import run_typed
from skillopt.coevo5 import data
from skillopt.execskill import typed, zebralogic
from skillopt.execskill.typed import chain, library, prepare, readout, reads, tasktypes, units, writers
from tests.test_typed_reads import sealed_code, write_machinery, write_pools, write_tree, zebra_rows

# pytest's tmp_path carries the word "test" (refused by the sealed-path guard): a plain-named scratch parent
NEUTRAL = Path('/tmp/typed2-neutral').resolve()
V1_SLICE_TAG, V1_EXAMPLE_TAG, V1_SEED = 'typed-v1:%s:slices', 'typed-v1:writer-examples', 20261110
POOL_IDS = ['item-%02d' % i for i in range(12)]
# stored draws of the 12-id fixture pool under typed-v1's keys (sha256 order of [seed, tag, id])
V1_SEARCHQA_SLICE_ORDER = ['item-10', 'item-01', 'item-07', 'item-11', 'item-09', 'item-06', 'item-08', 'item-02',
                           'item-00', 'item-03', 'item-05', 'item-04']
V1_SEARCHQA_EXAMPLE_ORDER = ['item-00', 'item-07', 'item-06', 'item-03', 'item-08', 'item-01', 'item-09', 'item-04',
                             'item-11', 'item-10', 'item-02', 'item-05']
COMMANDS = ('prepare', 'smoke', 'run', 'readout', 'status')


@pytest.fixture
def tmp_path():
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='identity-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


@pytest.fixture
def environ():
    """run_typed.main() cleans os.environ in place; the test restores it."""
    saved = dict(os.environ)
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(zebralogic, 'load_pool', lambda *a, **k: zebra_rows())
    machinery = tmp_path / 'machinery.json'
    return {'pools': write_pools(tmp_path), 'machinery': machinery, 'value': write_machinery(machinery),
            'tree': write_tree(tmp_path), 'parent': tmp_path}


def listing(path):
    """Names, kinds, sizes and mtimes of everything under ``path`` (None when absent): a refusal changes nothing."""
    path = Path(path)
    if not path.exists():
        return None
    rows = [(str(p.relative_to(path)), p.is_dir(), p.stat().st_size if p.is_file() else 0, p.stat().st_mtime_ns)
            for p in path.rglob('*')]
    return path.stat().st_mtime_ns, sorted(rows)


def v1_manifest(root):
    units.write_json(root / 'manifest.json', prepare.seal({'version': 'typed-v1', 'configuration': 'typed-v1',
                                                           'root': str(root), 'evidence': 'typed_v1_real_run'}))


def v1_state(root, chain_name='G'):
    units.write_json(root / chain_name / 'state.json',
                     {'version': 'typed-v1', 'chain': chain_name, 'mode': 'run', 'evidence': 'typed_v1_real_run',
                      'step': 4, 'done_units': [], 'paused': None, 'complete': False})


def typed_v1_roots(base):
    """The three typed-v1 cases each entry must refuse: a typed-v1 name, a typed-v2 name holding a typed-v1
    manifest, a typed-v2 name holding a typed-v1 chain state."""
    named = base / 'execskill-20261110-typed-v1'
    (named / 'G').mkdir(parents=True)
    manifest = base / 'm' / 'execskill-20261112-typed-v3'
    manifest.mkdir(parents=True)
    v1_manifest(manifest)
    state = base / 's' / 'execskill-20261112-typed-v3'
    v1_state(state)
    return {'name': named, 'manifest': manifest, 'state': state}


# ---- literals ---------------------------------------------------------------------------------------------------
def test_version_literals_and_new_constants():
    assert typed.VERSION == typed.CONFIGURATION == 'typed-v3'
    assert typed.EVIDENCE == {'run': 'typed_v3_real_run', 'smoke': 'typed_v3_smoke', 'test': 'engineering_fixture'}
    assert library.LIBRARY_VERSION == 'typed-v2-library' and tasktypes.TYPEMAP_VERSION == 'typed-v2-typemap'
    assert readout.READOUT_VERSION == 'typed-v3-readout-v1'  # typed-v3 (T1): VERSION + '-readout-v1'
    # typed-v3 (T1): the version function went with the version, as typed-v1's did
    assert typed.is_typed_v3('typed-v3') and not typed.is_typed_v3('typed-v2') and not hasattr(typed, 'is_typed_v2')
    # the machinery is still main-v10 (DESIGN 3.5); route-B labels unchanged
    assert (typed.MACHINERY, typed.MACHINERY_SNAPSHOT) == ('main-v10', '/data/execskill-code-20261109-main-v10')
    assert typed.ROUTE_B_EVIDENCE == {'run': 'pilot_real_run', 'smoke': 'smoke', 'test': 'engineering_fixture'}
    assert typed.MAX_PROGRAM_PROPOSALS == 3 and typed.MAX_PROGRAM_CANDIDATES == 2 and typed.GATE_REPEATS == 3
    assert typed.SCHEDULES == ('interleaved', 'learn_first') and typed.SCHEDULE_DEFAULT == 'interleaved'
    assert typed.MEMORY_LOCKS == ('per_cell_plain', 'unit_shared') and typed.MEMORY_LOCK_DEFAULT == 'per_cell_plain'
    assert typed.CAPS == {'G': 150_000_000, 'D': 170_000_000}
    for name in ('execskill-20261112-typed-v3', 'execskill-20261112-typed-v3-smoke'):
        assert prepare.ROOT_NAME.match(name)
    for name in ('execskill-20261110-typed-v1', 'execskill-20261110-typed-v1-smoke', 'execskill-20261112-typed-v2',
                 'execskill-20261112-typed-v20', 'execskill-20261112-typed-v30'):
        assert not prepare.ROOT_NAME.match(name)


def test_widths_and_learning_widths():
    """Addendum D15: learning units 6/6/6/2/2, read units keep 3/3/3/2/2."""
    assert typed.WIDTHS == {'searchqa': 3, 'officeqa': 3, 'zebralogic': 3, 'spreadsheetbench': 2, 'alfworld': 2}
    assert typed.LEARN_WIDTHS == {'searchqa': 6, 'officeqa': 6, 'zebralogic': 6, 'spreadsheetbench': 2, 'alfworld': 2}
    assert set(typed.WIDTHS) == set(typed.LEARN_WIDTHS) == set(typed.ORDER)
    sealed = prepare.sealed_constants()
    assert sealed == {'caps': typed.CAPS, 'draw_keys': prepare.draw_keys(), 'widths': typed.WIDTHS,
                      'learn_widths': typed.LEARN_WIDTHS}
    sealed['widths']['searchqa'] = 99  # a copy: the code constants never change through a manifest
    assert typed.WIDTHS['searchqa'] == 3


# ---- draw keys (addendum O4) --------------------------------------------------------------------------------------
def test_draw_keys_keep_their_typed_v1_values():
    assert (typed.SEED, prepare.SLICE_TAG, writers.EXAMPLE_TAG) == (V1_SEED, V1_SLICE_TAG, V1_EXAMPLE_TAG)
    assert prepare.draw_keys() == {'seed': V1_SEED, 'slices': V1_SLICE_TAG, 'examples': V1_EXAMPLE_TAG}
    pool = [{'task_id': i} for i in reversed(POOL_IDS)]
    # the slice draw equals the stored typed-v1 draw and an independent recomputation with the literal keys
    recomputed = sorted(POOL_IDS, key=lambda i: hashlib.sha256(
        json.dumps([V1_SEED, V1_SLICE_TAG % 'searchqa', i]).encode()).hexdigest())
    assert recomputed == V1_SEARCHQA_SLICE_ORDER
    drawn = prepare.draw_slices(pool, 'searchqa', sizes={'learn': 4, 'gate': 5})
    assert drawn == {'learn': V1_SEARCHQA_SLICE_ORDER[:4], 'gate': V1_SEARCHQA_SLICE_ORDER[4:9]}
    # the writers rank their examples with the same seed and the typed-v1 example tag
    examples = [row['task_id'] for row in data.ranked(pool, typed.SEED, writers.EXAMPLE_TAG + ':searchqa')]
    assert examples == V1_SEARCHQA_EXAMPLE_ORDER
    # a typed-v2 tag would have drawn other items: the keys are what keeps typed-v2 on typed-v1's practice items
    assert [r['task_id'] for r in data.ranked(pool, V1_SEED, 'typed-v2:searchqa:slices')] != V1_SEARCHQA_SLICE_ORDER


# ---- own_root -----------------------------------------------------------------------------------------------------
def test_own_root_accepts_this_version_and_unjudged_roots(tmp_path):
    fresh = tmp_path / 'execskill-20261112-typed-v3'
    assert prepare.own_root(fresh) == fresh and not fresh.exists()       # not created, nothing written
    assert prepare.own_root(str(tmp_path / 'run')) == tmp_path / 'run'    # a neutral name, no file yet
    fresh.mkdir()
    units.write_json(fresh / 'manifest.json', {'version': 'typed-v3', 'configuration': 'typed-v3'})
    units.write_json(fresh / 'G' / 'state.json', {'version': 'typed-v3', 'chain': 'G'})
    units.write_json(fresh / 'D' / 'state.json', {'version': 'typed-v3', 'chain': 'D'})
    before = listing(fresh)
    assert prepare.own_root(fresh) == fresh and listing(fresh) == before
    # a missing key is left to the full checks: own_root passes, load_manifest refuses
    bare = tmp_path / 'bare'
    units.write_json(bare / 'manifest.json', prepare.seal({'root': str(bare)}))
    units.write_json(bare / 'G' / 'state.json', {'chain': 'G'})
    assert prepare.own_root(bare) == bare
    with pytest.raises(ValueError, match='typed-v3 manifest'):
        prepare.load_manifest(bare)


def test_own_root_refuses_every_other_typed_version(tmp_path):
    cases = {
        'v1 name': tmp_path / 'execskill-20261110-typed-v1',
        'v1 smoke name': tmp_path / 'execskill-20261110-typed-v1-smoke',
        'v2 name': tmp_path / 'execskill-20261112-typed-v2',
        'v20 name': tmp_path / 'execskill-20261112-typed-v20',
        'v30 name': tmp_path / 'execskill-20261112-typed-v30',
        'v1 parent': tmp_path / 'typed-v1-ops' / 'execskill-20261112-typed-v3',
    }
    for label, root in cases.items():
        with pytest.raises(ValueError, match='another typed version'):
            prepare.own_root(root)
        assert not root.exists(), label
    # a neutral name that resolves into a typed-v1 root
    target = tmp_path / 'execskill-20261110-typed-v1-target'
    target.mkdir()
    link = tmp_path / 'neutral-link'
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='another typed version'):
        prepare.own_root(link)
    # files of another version under a typed-v2 name: manifest version or configuration, either chain's state
    variants = {
        'manifest version': ('manifest.json', {'version': 'typed-v1', 'configuration': 'typed-v3'}),
        'manifest configuration': ('manifest.json', {'version': 'typed-v3', 'configuration': 'typed-v1'}),
        'G state': ('G/state.json', {'version': 'typed-v1', 'chain': 'G'}),
        'D state': ('D/state.json', {'version': 'typed-v1', 'chain': 'D'}),
        'route-B manifest': ('manifest.json', {'configuration': 'main-v10'}),
    }
    for n, (label, (name, value)) in enumerate(variants.items()):
        root = tmp_path / ('v%d' % n) / 'execskill-20261112-typed-v3'
        units.write_json(root / name, value)
        before = listing(root)
        with pytest.raises(ValueError, match='belongs to another version'):
            prepare.own_root(root)
        assert listing(root) == before, label
    # a file that cannot show its version is refused, never skipped
    for n, text in enumerate(('{not json', '["typed-v3"]')):
        root = tmp_path / ('bad%d' % n) / 'execskill-20261112-typed-v3'
        root.mkdir(parents=True)
        (root / 'manifest.json').write_text(text)
        with pytest.raises(ValueError, match='cannot show its version'):
            prepare.own_root(root)
    root = tmp_path / 'badstate' / 'execskill-20261112-typed-v3'
    (root / 'D').mkdir(parents=True)
    (root / 'D' / 'state.json').write_text('')
    with pytest.raises(ValueError, match='cannot show its version'):
        prepare.own_root(root)


def test_every_command_refuses_a_typed_v1_root_before_touching_it(tmp_path, monkeypatch, environ):
    calls = []
    for name in ('_prepare', '_smoke_run', '_chain_run', '_readout_build', '_status'):
        monkeypatch.setattr(run_typed, name, lambda *a, _name=name, **k: calls.append((_name, a, k)) or {})
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {'alfworld': {'alfworld_data': '/data/alf'}}}))
    argv = {'prepare': ['--machinery-manifest', str(machinery), '--roles-repo', '/creds', '--pools-root', '/pools'],
            'smoke': ['--chain', 'G', '--fake'], 'run': ['--chain', 'G'], 'readout': [], 'status': []}
    for kind, root in typed_v1_roots(tmp_path).items():
        for command in COMMANDS:
            before = listing(root)
            with pytest.raises(ValueError, match='another typed version|belongs to another version'):
                run_typed.main([command, '--root', str(root)] + argv[command])
            assert calls == [] and listing(root) == before, (kind, command)
    # the smoke also refuses a typed-v1 state in its <root>-smoke root
    run_root = tmp_path / 'x' / 'execskill-20261112-typed-v3'
    v1_state(run_root.with_name(run_root.name + '-smoke'), 'D')
    with pytest.raises(ValueError, match='belongs to another version'):
        run_typed.main(['smoke', '--root', str(run_root), '--chain', 'D', '--fake'])
    assert calls == [] and not run_root.exists()
    # a root of this version goes through to the command
    good = tmp_path / 'y' / 'execskill-20261112-typed-v3'
    units.write_json(good / 'G' / 'state.json', {'version': 'typed-v3', 'chain': 'G', 'status': 'paused'})
    assert run_typed.main(['status', '--root', str(good)]) == 0 and calls[-1][0] == '_status'


class Untouchable:
    def __getattr__(self, name):
        raise AssertionError('the chain services were used before the root check: ' + name)


def untouchable(*args, **kwargs):
    raise AssertionError('called before the root check')


def test_read_panel_refuses_a_typed_v1_root_before_any_read(tmp_path):
    for kind, root in typed_v1_roots(tmp_path).items():
        before = listing(root)
        with pytest.raises(ValueError, match='another typed version|belongs to another version'):
            reads.read_panel(root, 'G', 'C0', 'searchqa', library=object(), typemap=object(), services=Untouchable())
        smoke_root = root.with_name(root.name + '-smoke')   # the same three cases for the smoke's explicit form
        if kind == 'manifest':
            v1_manifest(smoke_root)
        elif kind == 'state':
            v1_state(smoke_root)
        smoke_before = listing(smoke_root)
        item = {'benchmark': 'searchqa', 'task_id': 'p0', 'part': 'train', 'public': {'question': 'q'}, 'private': {}}
        with pytest.raises(ValueError, match='another typed version|belongs to another version'):
            reads.read_panel(smoke_root, 'G', 'S1', 'searchqa', library=object(), typemap=object(), items=[item],
                             smoke=True, mount_fn=untouchable, solve_fn=untouchable, embed=untouchable,
                             call_factory=untouchable, ledger=object(), widths={'searchqa': 1}, runtime={})
        assert listing(root) == before and listing(smoke_root) == smoke_before, kind


# ---- manifest -----------------------------------------------------------------------------------------------------
def test_prepare_seals_the_code_constants_and_load_refuses_any_difference(inputs):
    parent = inputs['parent']
    root = parent / 'execskill-20261112-typed-v3-smoke'
    made = prepare.prepare(root, machinery_manifest=inputs['machinery'], roles_repo='/root/roles',
                           pools_root=inputs['pools'], smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    assert made['version'] == made['configuration'] == 'typed-v3' and made['evidence'] == 'typed_v3_smoke'
    assert made['draw_keys'] == {'seed': 20261110, 'slices': 'typed-v1:%s:slices', 'examples': 'typed-v1:writer-examples'}
    assert made['caps'] == {'G': 150_000_000, 'D': 170_000_000} and made['seed'] == 20261110
    assert made['widths'] == {'searchqa': 3, 'officeqa': 3, 'zebralogic': 3, 'spreadsheetbench': 2, 'alfworld': 2}
    assert made['learn_widths'] == {'searchqa': 6, 'officeqa': 6, 'zebralogic': 6, 'spreadsheetbench': 2, 'alfworld': 2}
    assert prepare.load_manifest(root) == made
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    changes = {
        'caps': {'G': 150_000_000, 'D': 160_000_000},
        'draw_keys': {**made['draw_keys'], 'seed': 20261112},
        'widths': {**made['widths'], 'searchqa': 6},
        'learn_widths': {**made['learn_widths'], 'zebralogic': 3},
    }
    for key, value in changes.items():
        units.write_json(root / 'manifest.json', prepare.seal({**fields, key: value}))  # re-sealed: only the value differs
        with pytest.raises(ValueError, match='seals other values'):
            prepare.load_manifest(root)
    for key in ('learn_widths', 'draw_keys', 'caps', 'widths'):
        units.write_json(root / 'manifest.json', prepare.seal({k: v for k, v in fields.items() if k != key}))
        with pytest.raises(ValueError, match='seals other values'):
            prepare.load_manifest(root)
    for tag_key, tag in (('slices', 'typed-v2:%s:slices'), ('examples', 'typed-v2:writer-examples')):
        units.write_json(root / 'manifest.json', prepare.seal({**fields, 'draw_keys': {**made['draw_keys'], tag_key: tag}}))
        with pytest.raises(ValueError, match='seals other values'):
            prepare.load_manifest(root)
    # another seed draws other slices: the manifest records it, and no run loads it
    other = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', machinery_manifest=inputs['machinery'],
                            roles_repo='/root/roles', pools_root=inputs['pools'], smoke=True, seed=7,
                            typed_tree=inputs['tree'], root_parent=str(parent))
    assert other['draw_keys']['seed'] == 7 == other['seed']
    with pytest.raises(ValueError, match='seals other values'):
        prepare.load_manifest(parent / 'execskill-20261113-typed-v3-smoke')


def test_load_manifest_refuses_a_typed_v1_manifest_and_root(tmp_path):
    for kind, root in typed_v1_roots(tmp_path).items():
        if kind == 'name':
            units.write_json(root / 'manifest.json', prepare.seal({'version': 'typed-v3', 'configuration': 'typed-v3',
                                                                   'root': str(root), **prepare.sealed_constants(),
                                                                   **sealed_code()}))
        before = listing(root)
        with pytest.raises(ValueError, match='another typed version|belongs to another version'):
            prepare.load_manifest(root)
        assert listing(root) == before, kind
    # the same kind of root holding a typed-v2 manifest that seals this code's constants loads (step 5b: and a base card;
    # step 6s: and a schedule and a memory lock)
    root = tmp_path / 'execskill-20261112-typed-v3'
    units.write_json(root / 'manifest.json', prepare.seal({'version': 'typed-v3', 'configuration': 'typed-v3',
                                                           'root': str(root), **prepare.sealed_constants(),
                                                           **sealed_code(), 'base_card': 'format',
                                                           'schedule': 'interleaved', 'memory_lock': 'per_cell_plain',
                                                           'read_plan': 'full'}))  # step rp-int: and the read plan
    assert prepare.load_manifest(root)['version'] == 'typed-v3'
    with pytest.raises(ValueError, match='new'):  # prepare never reuses an existing root
        prepare.check_root(str(root), parent=str(tmp_path))


# ---- chain state, library, type map --------------------------------------------------------------------------------
def test_a_typed_v1_chain_state_is_refused(tmp_path):
    v1_state(tmp_path, 'G')
    with pytest.raises(ValueError, match='another run'):
        chain._open_state(tmp_path / 'G', 'G', 'run', True)
    fresh = chain._open_state(tmp_path / 'D', 'D', 'run', False)
    assert fresh['version'] == 'typed-v3' and fresh['evidence'] == 'typed_v3_real_run'


def test_a_library_or_type_map_of_another_version_is_refused(tmp_path):
    lib = library.Library()
    assert (lib.data['version'], lib.data['module']) == ('typed-v2-library', 'typed-v3')
    lib.save(tmp_path / 'ok' / 'library.json', step=0)
    assert library.Library.load(tmp_path / 'ok' / 'library.json').data['version'] == 'typed-v2-library'
    for n, (version, module) in enumerate((('typed-v1-library', 'typed-v1'), ('typed-v2-library', 'typed-v1'),
                                           ('typed-v1-library', 'typed-v3'), ('typed-v2-library', 'typed-v2'))):
        path = tmp_path / ('lib%d' % n) / 'library.json'
        library.Library({'version': version, 'module': module, 'step': 0, 'skills': []}).save(path, step=0)
        with pytest.raises(ValueError, match='Library version differs'):
            library.Library.load(path)
    typemap = tasktypes.TypeMap()
    assert (typemap.data['version'], typemap.data['module']) == ('typed-v2-typemap', 'typed-v3')
    typemap.freeze(tmp_path / 'ok' / 'typemap.json', step=0)
    assert tasktypes.TypeMap.load(tmp_path / 'ok' / 'typemap.json').data['version'] == 'typed-v2-typemap'
    for n, (version, module) in enumerate((('typed-v1-typemap', 'typed-v1'), ('typed-v2-typemap', 'typed-v1'),
                                           ('typed-v1-typemap', 'typed-v3'), ('typed-v2-typemap', 'typed-v2'))):
        other = tasktypes.TypeMap()
        other.data.update(version=version, module=module)
        path = tmp_path / ('map%d' % n) / 'typemap.json'
        other.freeze(path, step=0)
        with pytest.raises(ValueError, match='Type map version differs'):
            tasktypes.TypeMap.load(path)


# ---- the machinery binding ------------------------------------------------------------------------------------------
def test_bind_machinery_refuses_a_snapshot_with_its_own_typed_package(tmp_path):
    tree = Path(run_typed.TREE)
    for n, shadow in enumerate(('typed/__init__.py', 'typed.py')):
        snapshot = tmp_path / ('snap%d' % n)
        (snapshot / 'skillopt' / 'execskill').mkdir(parents=True)
        (snapshot / 'skillopt' / 'execskill' / '__init__.py').write_text('')
        target = snapshot / 'skillopt' / 'execskill' / shadow
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('VERSION = "typed-v1"\n')
        with pytest.raises(ValueError, match='shadow'):
            run_typed.bind_machinery(snapshot, tree)
    clean = tmp_path / 'clean'
    (clean / 'skillopt' / 'execskill').mkdir(parents=True)
    with pytest.raises(ValueError, match='already imported'):  # past the typed check; refused only for this process
        run_typed.bind_machinery(clean, tree)
