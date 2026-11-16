"""Run preparation of typed-v2 (design §5.9): a NEW run root with its own sealed manifest.

The manifest copies, by value, what the run borrows from main-v10's machinery manifest (the per-bench runtime table,
the pinned data map the panel readers check files against, the practice-pool pins, the sandbox limits and image,
the slot and history roots, the snapshot provenance), pins the practice pools typed-v2 learns from, draws the
seeded, disjoint learn / gate (/ panel for the smoke) slices per bench once, records the format blocks, the caps,
the arms and the credential locations (paths only, never contents), and seals everything with ``record_sha256`` so
that every later process verifies the same preparation (``load_manifest``). Items are loaded again at run time from
the pinned pool files (``load_pool`` with the stored pin); the manifest stores ids only. Root guards: a typed-v2
root is a new absolute directory named ``execskill-<8 digits>-typed-v2[-smoke]`` under ``/data``, never equal to or
under a registered route-B run root or a never-written root (``manifest._check_frozen_paths``' pattern).

Identity (DESIGN 3.5, addendum O4 and D15): ``own_root`` refuses a root of another typed version before a command
reads or writes anything in it; the manifest seals the code constants the run depends on (``sealed_constants``: the
caps, the draw keys, the read and learning widths) and ``load_manifest`` refuses any difference from this code. The
draw keys keep typed-v1's values on purpose, so typed-v2 learns and gates on the same practice items. The manifest
also seals the code identity of the preparing process: ``machinery_code`` (``machinery.check(real=False)``) and
``provenance.typed_code`` (``typed_code``: the typed package and the launcher); ``load_manifest`` checks their form
and the machinery list pins, and every real start compares them with its own process (``chain.start_checks``).
The manifest also seals the run's ``base_card`` (addendum D17, a ``prepare`` parameter: 'format', the code default,
or 'historical', which the typed-v2 smoke and real run set): the base every learned mount composes on and the base
card block the writers see; ``load_manifest`` refuses a manifest without one of ``BASE_CARDS``.
It also seals the run's ``schedule`` and ``memory_lock`` (DESIGN 3.6, ``prepare`` parameters, CLI ``--schedule``,
``--memory-lock``; the code defaults 'interleaved' and 'per_cell_plain' keep typed-v1's order and lock, the typed-v2
smoke and real run set 'learn_first' and 'unit_shared', addenda D9, D13); ``load_manifest`` refuses a manifest
without one of ``SCHEDULES`` and one of ``MEMORY_LOCKS``. There is no run-time option: a resume never changes them.
Likewise the ``read_plan`` (addendum D9, read-plan R2, R3; CLI ``--read-plan``): 'full' (the code default, every
event reads five panels fresh) or 'economy' (the typed-v2 smoke and real run), which requires 'learn_first'; a smoke
manifest also seals ``read_plan_probe`` (``[event, bench]`` or null; R7, Q20: the smoke's forced fallback pair,
refused on a real root and with 'full'). typed-v3 (T2): ``read_anchors`` (CLI ``--read-anchors``), written only when
it is C alone (no C0 read; 'full' and 'historical' only), with the read arms ``arms`` C, S1..S5 beside it. typed-v3
(B6 d): ``resume_replay`` (CLI ``--resume-replay``), written only when 'on' (saved receipts replayed on resume).
typed-v3 T7 (brief P3b): ``gate_rule`` ('whole' | 'evolution') and ``gate_screen`` (bool), written only when not at
their code defaults ('evolution', True; both need the item stage 'planned'), so a default manifest is the one before
them. The preset of the typed-v3 run and smoke (``typed_v3_preset``; CLI ``prepare --typed-v3`` [``--smoke``]) seals
every typed-v3 option at once.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path

from skillopt.coevo5 import data
from skillopt.continual_eval.core import require
from skillopt.execskill import client, manifest as route_b_manifest, prelaunch, profiles, v222_cards, zebralogic

from . import (ARCHIVE_DEFAULT, BASE_CARD_DEFAULT, BASE_CARDS, CAPS, CHAINS, CONFIGURATION, EMBED_DIM, EMBED_MODEL,
               EMBED_REVISION, EVIDENCE, FORBIDDEN_PATH_WORDS, GATE_REPEATS, GATE_RULE_DEFAULT, GATE_RULES,
               GATE_SCREEN_DEFAULT, GATE_SCREENS, ITEM_STAGE_DEFAULT, ITEM_STAGES, ITEM_ZERO_REASONS, LEARN_WIDTHS,
               MACHINERY, MEMORY_LOCK_DEFAULT, MEMORY_LOCKS, MOUNT_ARMS, ORDER, PROGRAM_LEARNING,
               PROGRAM_LEARNING_DEFAULT, READ_ARMS, READ_PLAN_DEFAULT, RESUME_REPLAY_DEFAULT, RESUME_REPLAYS,
               ROUTE_B_EVIDENCE, SCHEDULE_DEFAULT, SCHEDULES, SEED, SLICES, SMOKE_SLICES, TAU_MIN_POINTS,
               TAU_SE_MULTIPLIER, VERSION, WIDTHS)
from . import archives, readplan, units
from .library import canonical_sha256

ROOT_PARENT = '/data'
# typed-v3 (T1): execskill-<date>-typed-v3; B7 (2026-11-15): one optional lowercase letter after the date names a
# further root of the same day (execskill-20261115b-typed-v3)
ROOT_NAME = re.compile(r'^execskill-\d{8}[a-z]?-%s(-smoke)?$' % re.escape(VERSION))
OTHER_TYPED = re.compile(r'typed-v\d+')                # a path component naming a typed version (own_root)
MANIFEST = 'manifest.json'
STATE = 'state.json'                                   # chain.STATE: <root>/<chain>/state.json (own_root)
RECORD_HASH = 'record_sha256'
MACHINERY_FIELDS = ('runtime', 'sandbox', 'slot_root', 'history_root', 'provenance')
POOLS_RECORD = 'pools.json'
SLICE_TAG = 'typed-v1:%s:slices'  # draw key, typed-v1's value (addendum O4): the practice slices stay the same draw
SLICE_NAMES = ('learn', 'gate', 'panel')
TYPED_TREE = Path(__file__).resolve().parents[3]      # skillopt/execskill/typed/prepare.py -> the typed tree
HEX40 = re.compile(r'^[0-9a-f]{40}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
# What this tree contributes to a bound run (DESIGN 3.5): every file under the typed package and the launcher
TYPED_CODE = ('skillopt/execskill/typed/', 'scripts/run_typed.py')
MACHINERY_CODE_KEYS = ('snapshot', 'bound', 'typed_from', 'list', 'list_sha256', 'files', 'data_list_sha256', 'symbols')
TYPED_CODE_KEYS = ('files', 'sha256_list_sha256')


# ---- root guards ------------------------------------------------------------------------------------------------
def own_root(root):
    """The root belongs to this typed version (DESIGN 3.5), checked by every command of ``scripts/run_typed.py``,
    by ``reads.read_panel`` and by ``load_manifest`` before anything in the root is read further or written: no
    component of the path (as given and resolved) names another typed version (``typed-v<n>``, n not this
    version's), and neither ``<root>/manifest.json`` (``version``, ``configuration``) nor any
    ``<root>/<chain>/state.json`` (``version``) that exists carries another version. A file that exists but is not
    a readable JSON object is refused (it cannot show its version); a missing file or key is left to the full checks
    (``load_manifest``, the chain's state check). Reads only; returns the root as a ``Path``."""
    require(isinstance(root, (str, Path)) and str(root).strip(), 'A run root path')
    path = Path(root)
    for candidate in (path, path.resolve(strict=False)):
        for part in candidate.parts:
            for found in OTHER_TYPED.findall(part):
                require(found == VERSION, 'A %s command refuses a root of another typed version (%s): %s'
                        % (VERSION, found, path))
    manifest = _own_record(path / MANIFEST)
    if manifest is not None:
        for key, value in (('version', VERSION), ('configuration', CONFIGURATION)):
            require(manifest.get(key, value) == value,
                    'The manifest at %s belongs to another version (%s %r): a %s command refuses it'
                    % (path, key, manifest.get(key), VERSION))
    for chain in CHAINS:
        state = _own_record(path / chain / STATE)
        if state is not None:
            require(state.get('version', VERSION) == VERSION,
                    'The chain state at %s belongs to another version (%r): a %s command refuses it'
                    % (path / chain, state.get('version'), VERSION))
    return path


def _own_record(path):
    """A JSON object file of the root, or None when absent; an unreadable or non-object file is refused."""
    if not path.exists() and not path.is_symlink():
        return None
    try:
        found = units.read_json(path)
    except (OSError, ValueError) as error:  # the class name only: a refusal never carries file content
        raise ValueError('An unreadable %s cannot show its version: %s (%s)'
                         % (path.name, path, type(error).__name__)) from None
    require(isinstance(found, dict), 'A %s that is not a JSON object cannot show its version: %s' % (path.name, path))
    return found


def check_root(root, *, smoke=False, parent=ROOT_PARENT):
    """The new run root (design §3): absolute, named ``execskill-<date>-typed-v3`` (``-smoke`` for the smoke root)
    directly under ``parent``, never a registered route-B root or under one, never under a never-written root,
    not existing yet, and owned by this version (``own_root``). ``parent`` is overridden by tests only."""
    require(isinstance(root, (str, Path)) and Path(root).is_absolute(), 'An absolute %s run root' % VERSION)
    path = Path(root)
    require('..' not in path.parts, 'A run root without parent traversal')
    match = ROOT_NAME.match(path.name)
    require(match is not None, 'A %s run root is named execskill-<8 digits>-%s[-smoke]: %s' % (VERSION, VERSION, path.name))
    require(bool(match.group(1)) == bool(smoke), 'The smoke root ends with -smoke, the run root does not')
    require(str(path.parent) == str(Path(parent).absolute()), 'A %s run root lives directly under %s' % (VERSION, parent))
    own_root(path)
    _refuse_registered(path)
    require(not path.exists() and not path.is_symlink(), 'The %s run root is new: %s' % (VERSION, path))
    return path


def _refuse_registered(path):
    """Lexical and resolved comparison against every route-B run root and never-written root."""
    registered = list(profiles.RUN_ROOTS.values()) + list(profiles.NEVER_WRITTEN)
    for candidate in (Path(os.path.abspath(path)), path.resolve(strict=False)):
        for known in registered:
            for frozen in (Path(os.path.abspath(known)), Path(known).resolve(strict=False)):
                require(candidate != frozen and frozen not in candidate.parents,
                        'A typed-v2 root is never a route-B run root or under one: ' + str(known))


# ---- machinery ----------------------------------------------------------------------------------------------------
def read_machinery(path):
    """The main-v10 machinery manifest, read as plain JSON (its own tree verifies its record): the fields typed-v2
    copies by value (design §5.4). Never a credential, never an item."""
    found = units.read_json(path)
    require(isinstance(found, dict) and found.get('configuration') == MACHINERY,
            'The machinery manifest is a %s manifest' % MACHINERY)
    missing = [key for key in MACHINERY_FIELDS if key not in found]
    require(not missing, 'The machinery manifest lacks ' + str(missing))
    found_data = found.get('data')
    require(isinstance(found_data, dict) and isinstance(found_data.get('pinned'), dict),
            'The machinery manifest pins its data map (data.pinned)')
    runtime = found['runtime']
    require(isinstance(runtime, dict) and set(ORDER) <= set(runtime), 'The runtime table names the five benches')
    return {'path': str(Path(path).absolute()), 'record_sha256': found.get(RECORD_HASH),
            'evidence': found.get('evidence'), 'configuration': found['configuration'],
            'runtime': {bench: deepcopy(runtime[bench]) for bench in ORDER}, 'pinned': deepcopy(found_data['pinned']),
            'pools': deepcopy(found_data.get('pools')), 'sandbox': deepcopy(found['sandbox']),
            'slot_root': found['slot_root'], 'history_root': found['history_root'],
            'provenance': deepcopy(found['provenance'])}


# ---- practice pools -----------------------------------------------------------------------------------------------
def load_pool(bench, pools_root, pin=None):
    """One bench's pinned practice pool (scripts/arch_probes.py ``load_practice_pool``): ZebraLogic through
    ``zebralogic.load_pool()`` minus ``EXCLUDED_IDS``; the others from ``<pools_root>/<bench>.json`` pinned by
    ``<pools_root>/pools.json`` and loaded by ``manifest._items`` (sha check, the bench's fixed order); ALFWorld keeps
    the games with a registered routing view only. ``pin``: the expected {path, sha256} (the manifest's, at run
    time); a different pin is refused. Returns (items, provenance)."""
    require(bench in ORDER, 'A registered bench: ' + str(bench))
    if bench == 'zebralogic':
        found = {'path': zebralogic.POOL_PATH, 'sha256': zebralogic.POOL_SHA256}
        _same_pin(found, pin)
        items = [item for item in zebralogic.load_pool() if item['task_id'] not in zebralogic.EXCLUDED_IDS]
        provenance = {**found, 'excluded_ids': len(zebralogic.EXCLUDED_IDS),
                      'excluded_ids_sha256': zebralogic.EXCLUDED_IDS_SHA256}
    else:
        root = Path(pools_root).absolute()
        record_path = root / POOLS_RECORD
        record = units.read_json(record_path)
        require(isinstance(record, dict) and bench in record.get('pools', {}), 'pools.json pins ' + bench)
        found = {'path': str(root / (bench + '.json')), 'sha256': record['pools'][bench]['sha256']}
        _same_pin(found, pin)
        items = route_b_manifest._items(found, bench)
        provenance = {**found, 'pools_record': str(record_path), 'pools_record_sha256': _file_sha256(record_path)}
    items = validate_items(items, bench)
    if bench == 'alfworld':
        items = [item for item in items if isinstance(item['public'].get('routing_view'), dict)
                 and isinstance(item['public'].get('routing_view_sha256'), str)]
        require(items, 'ALFWorld practice items with a registered routing view')
    provenance['items'] = len(items)
    return items, provenance


def _same_pin(found, pin):
    if pin is not None:
        require(all(found[key] == pin.get(key) for key in ('path', 'sha256')), 'The practice pool pin changed')


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_items(items, bench):
    """arch_probes ``validate_practice_items``: shape, bench, unique ids, no test-side part, no sealed field name
    (a sheet item's private ``test_files`` reference workbooks excepted, design §3)."""
    require(isinstance(items, list) and items, 'A nonempty practice pool for ' + bench)
    seen = set()
    for item in items:
        require(isinstance(item, dict) and item.get('benchmark') == bench and isinstance(item.get('task_id'), str)
                and item['task_id'] and isinstance(item.get('public'), dict) and isinstance(item.get('private'), dict),
                'Invalid practice item in ' + bench)
        part = item.get('part', item.get('partition', ''))
        require(isinstance(part, str) and not any(word in part.lower() for word in FORBIDDEN_PATH_WORDS),
                'Forbidden practice item part in ' + bench)
        _check_fields(item, bench)
        require(item['task_id'] not in seen, 'Duplicate practice task id: ' + item['task_id'])
        seen.add(item['task_id'])
    return items


def _check_fields(value, bench, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            exempt = bench == 'spreadsheetbench' and path == ('private',) and key == 'test_files'
            require(exempt or not any(word in str(key).lower() for word in FORBIDDEN_PATH_WORDS),
                    'Forbidden practice item field: ' + str(key))
            _check_fields(child, bench, path + (key,))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _check_fields(child, bench, path + (index,))


def draw_slices(items, bench, *, sizes, seed=SEED):
    """Disjoint seeded slices of one pool: the first ``learn`` ids of ``data.ranked(items, seed, SLICE_TAG)``, then
    ``gate``, then ``panel`` (the smoke only). Deterministic in the seed and the ids; never overlapping."""
    names = [name for name in SLICE_NAMES if name in sizes]
    require(set(sizes) <= set(SLICE_NAMES) and names and all(type(sizes[n]) is int and sizes[n] > 0 for n in names),
            'Slice sizes are positive integers among ' + str(SLICE_NAMES))
    ordered = [item['task_id'] for item in data.ranked(items, seed, SLICE_TAG % bench)]
    require(len(ordered) == len(set(ordered)), 'Unique practice ids')
    need = sum(sizes[name] for name in names)
    require(len(ordered) >= need, 'The %s pool holds %d items; the slices need %d' % (bench, len(ordered), need))
    out, start = {}, 0
    for name in names:
        out[name] = ordered[start:start + sizes[name]]
        start += sizes[name]
    return out


def slice_sizes(slices=None, *, smoke=False):
    """The registered sizes (design §2 / ``SMOKE_SLICES``) or an explicit {bench: {learn, gate[, panel]}} table."""
    if slices is None:
        base = SMOKE_SLICES if smoke else SLICES
        return {bench: dict(base[bench]) for bench in ORDER}
    require(isinstance(slices, dict) and set(slices) == set(ORDER), 'Slice sizes for every bench of ORDER')
    for bench in ORDER:
        sizes = slices[bench]
        require(isinstance(sizes, dict) and {'learn', 'gate'} <= set(sizes) <= set(SLICE_NAMES)
                and all(type(v) is int and v > 0 for v in sizes.values()), 'learn/gate[/panel] sizes for ' + bench)
    return {bench: dict(slices[bench]) for bench in ORDER}


# ---- cards, provenance, sealing ---------------------------------------------------------------------------------
def format_block(bench):
    """The format-only shell card of a bench (design §5.5 ``mount.format_block``): ``zebralogic.CARD_TEXT`` for
    ZebraLogic, ``v222_cards.format_text`` otherwise; defined here so that the manifest never imports the mount."""
    require(bench in ORDER, 'A registered bench: ' + str(bench))
    return zebralogic.CARD_TEXT if bench == 'zebralogic' else v222_cards.format_text(bench)


def git_head(tree):
    """The 40-hex HEAD of a checkout (ref, loose ref file or packed-refs); None for a tree without ``.git``."""
    git = Path(tree) / '.git'
    head = git / 'HEAD'
    if not head.is_file():
        return None
    text = head.read_text(encoding='utf-8').strip()
    if not text.startswith('ref: '):
        return text if HEX40.match(text) else None
    ref = text[len('ref: '):].strip()
    loose = git / ref
    if loose.is_file():
        value = loose.read_text(encoding='utf-8').strip()
        return value if HEX40.match(value) else None
    packed = git / 'packed-refs'
    if packed.is_file():
        for line in packed.read_text(encoding='utf-8').splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref and HEX40.match(parts[0]):
                return parts[0]
    return None


def tree_provenance(tree):
    """The typed tree's identity (``prelaunch.sha256_list`` over skillopt/ scripts/ tests/, no .env file, git HEAD):
    the run records which code made it, as route B's provenance block does for its snapshot."""
    tree = Path(tree).absolute()
    require(all((tree / name).is_dir() for name in prelaunch.SNAPSHOT_DIRS),
            'A code tree with ' + '/'.join(prelaunch.SNAPSHOT_DIRS))
    require(not prelaunch.env_files(tree), 'The code tree holds .env files')
    listing = prelaunch.sha256_list(tree)
    return {'root': str(tree), 'files': listing.count('\n'),
            'sha256_list_sha256': hashlib.sha256(listing.encode('utf-8')).hexdigest(), 'git_head': git_head(tree),
            'env_files_absent': True}


def _typed_code_path(path):
    return any(path.startswith(entry) if entry.endswith('/') else path == entry for entry in TYPED_CODE)


def typed_code(tree=None):
    """The typed code identity of a tree (DESIGN 3.5): the ``prelaunch.sha256_list`` lines of the files under
    ``skillopt/execskill/typed/`` and of ``scripts/run_typed.py`` (same format and file rule: no ``__pycache__``, no
    ``.pyc``), as ``{files, sha256_list_sha256}``. Sealed at ``prepare`` as ``provenance.typed_code`` and compared at
    every real start (``chain.start_checks``): a changed typed module or launcher refuses the start, a changed test
    or ops helper does not (``typed_tree`` stays information only). ``tree``: this tree when None."""
    tree = Path(TYPED_TREE if tree is None else tree).absolute()
    kept = [line for line in prelaunch.sha256_list(tree).splitlines(keepends=True)
            if _typed_code_path(line.rstrip('\n').split('  ', 1)[-1])]
    return {'files': len(kept), 'sha256_list_sha256': hashlib.sha256(''.join(kept).encode('utf-8')).hexdigest()}


def machinery_code():
    """The machinery record sealed at ``prepare`` (DESIGN 3.5, 4.1): ``machinery.check(real=False)`` of this process
    (checks 1, 3, 5, 6; the bound ``prepare`` on dl records the snapshot it is bound to, an unbound one records
    ``bound: false``, which every real start refuses)."""
    from . import machinery
    return machinery.check(real=False)


def _check_code_identity(record):
    """``load_manifest``'s check of the sealed code identity: ``machinery_code`` with exactly its keys, the machinery
    lists pinned by this code and well-formed values; ``provenance.typed_code`` with its two keys. The values that
    depend on the process (snapshot, bound, typed tree, typed code) are compared by every real start
    (``chain.start_checks``), never here: a readout or a status of a root needs no bound process."""
    from . import machinery
    code = record.get('machinery_code')
    require(isinstance(code, dict) and set(code) == set(MACHINERY_CODE_KEYS),
            'The manifest seals the machinery record (machinery_code with %s)' % ', '.join(MACHINERY_CODE_KEYS))
    pins = {'list': machinery.LIST, 'list_sha256': machinery.LIST_SHA256, 'files': machinery.LIST_FILES,
            'data_list_sha256': machinery.DATA_LIST_SHA256}
    changed = sorted(key for key, value in pins.items() if code.get(key) != value)
    require(not changed, 'The manifest seals other machinery lists than this code for %s: a new root is needed' % changed)
    require(type(code['bound']) is bool and all(isinstance(code[key], str) and code[key] for key in ('snapshot', 'typed_from'))
            and type(code['symbols']) is int and code['symbols'] > 0, 'A well-formed machinery_code in the manifest')
    typed = (record.get('provenance') or {}).get('typed_code')
    require(isinstance(typed, dict) and set(typed) == set(TYPED_CODE_KEYS) and type(typed['files']) is int
            and typed['files'] >= 0 and isinstance(typed['sha256_list_sha256'], str)
            and HEX64.match(typed['sha256_list_sha256']) is not None,
            'The manifest seals the typed code identity (provenance.typed_code with files, sha256_list_sha256)')


def draw_keys(seed=SEED):
    """The keys of the seeded draws (addendum O4): the seed, the slice tag of ``draw_slices`` and the writer-example
    tag of ``writers.outcomes_for_writer``. They keep typed-v1's values on purpose, so typed-v2 learns and gates on
    the same practice items and shows its writers the examples in the same order."""
    from .writers import EXAMPLE_TAG  # lazily: the writers import the engineer machinery, the manifest needs one tag
    return {'seed': seed, 'slices': SLICE_TAG, 'examples': EXAMPLE_TAG}


def sealed_constants(*, seed=SEED):
    """The code constants a manifest seals and ``load_manifest`` compares with this code (DESIGN 3.5, addendum D15):
    the token caps (the ledger takes the cap from the manifest), the draw keys, the read widths and the learning
    widths. A different value means a new root, never an adapted run."""
    return {'caps': dict(CAPS), 'draw_keys': draw_keys(seed), 'widths': dict(WIDTHS),
            'learn_widths': dict(LEARN_WIDTHS)}


def tau_rule():
    """The gate rule a manifest seals (DESIGN 3.4, 4.1): tau = max(minimum_points, se_multiplier * se) with se from
    the baseline arm's own ``repeats`` fresh runs per item (``se: 'baseline_repeats'``). ``chain.real_services``
    refuses a manifest whose rule differs from this code's."""
    return {'minimum_points': TAU_MIN_POINTS, 'se_multiplier': TAU_SE_MULTIPLIER, 'repeats': GATE_REPEATS,
            'se': 'baseline_repeats'}


def base_card_of(manifest):
    """The run's sealed base card (addendum D17): ``manifest['base_card']``, one of ``BASE_CARDS``; a manifest
    without it, or with any other value, is refused (``load_manifest``, ``chain.run`` before it writes anything, and
    the chain's mounts and writers take the base from here, never from a code default)."""
    found = manifest.get('base_card') if isinstance(manifest, dict) else None
    require(type(found) is str and found in BASE_CARDS,
            'The manifest seals the base card of the run (base_card, one of %s; found %s): a new root is needed'
            % (BASE_CARDS, repr(found)[:40]))
    return found


def schedule_of(manifest):
    """The run's sealed schedule (DESIGN 3.6, schedule-lock S1): ``manifest['schedule']``, one of ``SCHEDULES``
    ('interleaved': typed-v1's order, the code default; 'learn_first': all five steps learned and frozen, then every
    read event from its frozen state). A manifest without it, or with any other value, is refused (``load_manifest``,
    and ``chain.run`` before it writes anything)."""
    found = manifest.get('schedule') if isinstance(manifest, dict) else None
    require(type(found) is str and found in SCHEDULES,
            'The manifest seals the schedule of the run (schedule, one of %s; found %s): a new root is needed'
            % (SCHEDULES, repr(found)[:40]))
    return found


def memory_lock_of(manifest):
    """The run's sealed memory-lock mode (DESIGN 3.6, schedule-lock L1 to L7, addendum D13):
    ``manifest['memory_lock']``, one of ``MEMORY_LOCKS`` ('per_cell_plain': typed-v1's plain lock per cell, the code
    default; 'unit_shared': route B's environment lock, shared by the threads of one unit). A manifest without it, or
    with any other value, is refused (``load_manifest``, and ``chain.heavy_for`` when the services are built)."""
    found = manifest.get('memory_lock') if isinstance(manifest, dict) else None
    require(type(found) is str and found in MEMORY_LOCKS,
            'The manifest seals the memory lock of the run (memory_lock, one of %s; found %s): a new root is needed'
            % (MEMORY_LOCKS, repr(found)[:40]))
    return found


def read_plan_of(manifest):
    """The run's sealed read plan (addendum D9, read-plan R3): ``manifest['read_plan']``, one of ``READ_PLANS`` and
    allowed with the sealed schedule ('economy' only with 'learn_first'); a smoke manifest's ``read_plan_probe`` must
    be null or ``[event, bench]`` under 'economy', and a real manifest carries none (Q20). Refused otherwise
    (``load_manifest``, and ``chain.run`` before it writes anything)."""
    found = manifest.get('read_plan') if isinstance(manifest, dict) else None
    require(type(found) is str and found in readplan.READ_PLANS,
            'The manifest seals the read plan of the run (read_plan, one of %s; found %s): a new root is needed'
            % (readplan.READ_PLANS, repr(found)[:40]))
    smoke = manifest.get('smoke') is True or manifest.get('mode') == 'smoke'
    require(smoke or 'read_plan_probe' not in manifest, 'read_plan_probe is a smoke-only field: a real root refuses it')
    readplan.check_read_plan(manifest.get('schedule'), found, manifest.get('read_plan_probe'), smoke=smoke)
    return found


def read_plan_probe_of(manifest):
    """The smoke's probe pair (R7) or None."""
    read_plan_of(manifest)
    found = manifest.get('read_plan_probe')
    return None if found is None else list(found)


def program_learning_of(manifest):
    """The run's sealed program learning (typed-v3, CHAIN-DECISIONS T8): ``manifest['program_learning']``, one of
    ``PROGRAM_LEARNING``. A manifest without the field runs typed-v2's flow ('single', the code default: a typed-v2
    style manifest behaves as it did); any other value is refused (``load_manifest``, and ``chain.run`` before it
    writes anything). There is no run-time option: a resume never changes it."""
    found = (manifest.get('program_learning', PROGRAM_LEARNING_DEFAULT) if isinstance(manifest, dict) else None)
    require(type(found) is str and found in PROGRAM_LEARNING,
            'The manifest seals the program learning of the run (program_learning, one of %s; found %s): a new root '
            'is needed' % (PROGRAM_LEARNING, repr(found)[:40]))
    return found


def read_anchors_of(manifest):
    """The run's sealed read anchors (typed-v3, CHAIN-DECISIONS T2) as a tuple: ``manifest['read_anchors']``, one of
    ``readplan.READ_ANCHORS``; a manifest without the field reads typed-v2's anchors C0 and C (the code default: a
    typed-v2 style manifest behaves as it did). C alone needs the read plan 'full' and the base card 'historical'
    (``readplan.check_read_anchors``), and a manifest that names its read arms (``arms``: every prepared one) names
    exactly the read events of its anchors, the arms its consent must name. Refused otherwise (``load_manifest``, and
    ``chain.run`` before it writes anything). There is no run-time option: a resume never changes it."""
    manifest = manifest if isinstance(manifest, dict) else {'read_anchors': None}
    anchors = readplan.check_read_anchors(manifest.get('read_anchors', list(readplan.READ_ANCHORS_DEFAULT)),
                                          read_plan=manifest.get('read_plan'), base_card=manifest.get('base_card'))
    require('arms' not in manifest or manifest['arms'] == list(readplan.read_events(anchors)),
            'The manifest\'s read arms (arms) are the read events of its read_anchors: a new root is needed')
    return anchors


def resume_replay_of(manifest):
    """The run's sealed resume replay (typed-v3, CHAIN-DECISIONS B6 d): ``manifest['resume_replay']``, one of
    ``RESUME_REPLAYS``; a manifest without the field resumes as typed-v2 ('off', the code default: an interrupted
    solver cell is solved again). Refused otherwise (``load_manifest``, and ``chain.run`` before it writes anything).
    There is no run-time option: a resume never changes it."""
    found = manifest.get('resume_replay', RESUME_REPLAY_DEFAULT) if isinstance(manifest, dict) else None
    require(type(found) is str and found in RESUME_REPLAYS,
            'The manifest seals the resume replay of the run (resume_replay, one of %s; found %s): a new root is '
            'needed' % (RESUME_REPLAYS, repr(found)[:40]))
    return found


def archive_of(manifest):
    """The run's sealed archive packages (typed-v3, CHAIN-DECISIONS T9): ``manifest['archive']``, ``{}`` when absent
    (the code default: no archive), else per chain and bench exactly the entry of the tree's verified archive index
    (``archives.check_sealed``); an archive is refused unless the program learning is 'repair' (T9 runs inside it).
    The records' bytes are verified again by every run start (``archives.load_package``)."""
    found = manifest.get('archive', {}) if isinstance(manifest, dict) else None
    archives.check_sealed(found)
    require(not found or program_learning_of(manifest) == 'repair',
            'An archive package is a candidate of the repair program learning only (T9): program_learning repair')
    return found


def item_stage_of(manifest):
    """The run's sealed item stage (typed-v3, CHAIN-DECISIONS T3; brief P2b): ``manifest['item_stage']``, one of
    ``ITEM_STAGES``. A manifest without the field runs typed-v2's step flow ('none', the code default); any other value
    is refused (``load_manifest``, and ``chain.run`` before it writes anything). No run-time option: a resume never
    changes it."""
    found = manifest.get('item_stage', ITEM_STAGE_DEFAULT) if isinstance(manifest, dict) else None
    require(type(found) is str and found in ITEM_STAGES,
            'The manifest seals the item stage of the run (item_stage, one of %s; found %s): a new root is needed'
            % (ITEM_STAGES, repr(found)[:40]))
    return found


def default_item_quotas():
    """The quota table a 'planned' prepare seals unless it is given one: the table of T5 (``items.ITEM_QUOTAS``,
    owner-approved 4 : 3 : 3) with the rows of ``ITEM_ZERO_REASONS`` (OfficeQA after the audit B36, SpreadsheetBench
    without a maker, B3) at zero."""
    from .items import ITEM_QUOTAS, SHOWN_CLASSES, CLASSES
    table = deepcopy(ITEM_QUOTAS)
    for bench in ITEM_ZERO_REASONS:
        table[bench] = {'judging': {name: 0 for name in CLASSES}, 'shown': {name: 0 for name in SHOWN_CLASSES}}
    return {bench: table[bench] for bench in ORDER}


def check_item_quotas(table):
    """A sealed quota table: one row per bench of ``ORDER`` (judging attack / guard / calibration and shown attack /
    guard, integers >= 0: ``items.quota_row``), the rows of ``ITEM_ZERO_REASONS`` all zero (typed-v3 makes no items
    for them; their steps record the reason). Returns the table; refused otherwise."""
    from .items import quota_row
    require(isinstance(table, dict) and set(table) == set(ORDER), 'An item quota table holds one row per bench of '
                                                                  'the order')
    for bench in ORDER:
        quota_row(bench, table)  # the shape and the counts of the row
    for bench, reason in sorted(ITEM_ZERO_REASONS.items()):
        require(quota_row(bench, table) is None, 'typed-v3 makes no items for %s (%s): its quota row is zero'
                % (bench, reason))
    return table


def item_quotas_of(manifest):
    """The run's sealed quota table (typed-v3 T5; brief P2b): None under the item stage 'none' (the field absent or
    null: a typed-v2 style manifest has none), else ``manifest['item_quotas']`` checked by ``check_item_quotas``; a
    table without 'planned', or 'planned' without a table, is refused."""
    stage = item_stage_of(manifest)
    found = manifest.get('item_quotas') if isinstance(manifest, dict) else None
    if stage == ITEM_STAGE_DEFAULT:
        require(found is None, 'An item quota table is sealed with the planned item stage only (item_stage planned)')
        return None
    return check_item_quotas(found)


def gate_rule_of(manifest):
    """The run's sealed gate rule (typed-v3, CHAIN-DECISIONS T7; brief P3b): ``manifest['gate_rule']``, one of
    ``GATE_RULES``. A manifest without the field decides by typed-v2's rules ('whole', the code default); 'evolution'
    needs the item stage 'planned' (a step without made items has nothing to apply it to). Refused otherwise
    (``load_manifest``, and ``chain.run`` before it writes anything). No run-time option: a resume never changes it."""
    found = manifest.get('gate_rule', GATE_RULE_DEFAULT) if isinstance(manifest, dict) else None
    require(type(found) is str and found in GATE_RULES,
            'The manifest seals the gate rule of the run (gate_rule, one of %s; found %s): a new root is needed'
            % (GATE_RULES, repr(found)[:40]))
    require(found == GATE_RULE_DEFAULT or item_stage_of(manifest) == 'planned',
            'The gate rule evolution decides on made items: it needs the item stage planned')
    return found


def gate_screen_of(manifest):
    """The run's sealed screen switch (typed-v3 T7; brief P3b): ``manifest['gate_screen']``, a bool (``GATE_SCREENS``).
    A manifest without the field runs no screen (False, the code default); True needs the item stage 'planned' (the
    screen runs on the judging-side attack and guard items). Refused otherwise (``load_manifest``, ``chain.run``)."""
    found = manifest.get('gate_screen', GATE_SCREEN_DEFAULT) if isinstance(manifest, dict) else None
    require(type(found) is bool and found in GATE_SCREENS,
            'The manifest seals the screen switch of the run (gate_screen, true or false; found %s): a new root is '
            'needed' % repr(found)[:40])
    require(not found or item_stage_of(manifest) == 'planned',
            'The screen runs on made items (gate_screen true): it needs the item stage planned')
    return found


# ---- the typed-v3 preset (brief P3b D; CHAIN-DECISIONS T1 to T9) ---------------------------------------------------
# What ``prepare --typed-v3`` seals besides the run's root, slices and machinery: the base card of D17, typed-v1's
# order with every read fresh after every step (T2), the anchor C alone (no C0 read; the consent names C, S1..S5), the
# environment lock of D13, the program learning with repair rounds (T8) and the chain's archive packages of the tree's
# index (T9), the item stage (T3 to T6) with the quota table of T5 (OfficeQA and SpreadsheetBench at zero), the gate
# rule on E with the screen (T7) and the resume replay of B6 (d).
TYPED_V3_PRESET = {'base_card': 'historical', 'schedule': 'interleaved', 'read_plan': 'full', 'read_anchors': ('C',),
                   'memory_lock': 'unit_shared', 'program_learning': 'repair', 'archive': 'index',
                   'item_stage': 'planned', 'gate_rule': 'evolution', 'gate_screen': True, 'resume_replay': 'on'}
# The smoke's row of every bench with made items (SearchQA, ZebraLogic, ALFWorld): judging attack / guard /
# calibration 1 / 2 / 2 and shown attack / guard 1 / 4. The smoke's 2 learn items can never keep a weakness (T4 needs 3
# evidence items), so the 20 % rule always applies; these counts are its fixed point (judging 5 -> attack 1, guard 2,
# calibration 2; shown 5 -> attack 1, guard 4), so every made class, the check, the shown items and the screen on A + G
# run in the smoke.
SMOKE_ITEM_QUOTA_ROW = {'judging': {'attack': 1, 'guard': 2, 'calibration': 2}, 'shown': {'attack': 1, 'guard': 4}}


def smoke_item_quotas():
    """The quota table of the typed-v3 smoke: ``SMOKE_ITEM_QUOTA_ROW`` for every bench with made items, the rows of
    ``ITEM_ZERO_REASONS`` at zero (``check_item_quotas`` admits it)."""
    table = default_item_quotas()
    for bench in ORDER:
        if bench not in ITEM_ZERO_REASONS:
            table[bench] = deepcopy(SMOKE_ITEM_QUOTA_ROW)
    return check_item_quotas(table)


def typed_v3_preset(*, smoke=False):
    """The ``prepare`` arguments of the typed-v3 real run (``smoke`` False: ``TYPED_V3_PRESET`` with the default quota
    table of T5, ``item_quotas`` None) or of its smoke (the same values with ``smoke_item_quotas``; the smoke slices
    and limits are the smoke's own, ``SMOKE_SLICES`` and ``smoke.SMOKE_LIMITS``). A manifest prepared without the preset
    stays a typed-v2 style manifest (every option at its code default)."""
    return {**deepcopy(TYPED_V3_PRESET), 'item_quotas': smoke_item_quotas() if smoke else None}


def seal(fields):
    """A typed-v2 record: the fields plus ``record_sha256`` of their canonical JSON (tuples become lists first)."""
    require(isinstance(fields, dict) and RECORD_HASH not in fields, 'Fields without a record hash')
    record = json.loads(json.dumps(fields, ensure_ascii=False, allow_nan=False))
    record[RECORD_HASH] = canonical_sha256(record)
    return record


def verify(record):
    require(isinstance(record, dict) and isinstance(record.get(RECORD_HASH), str), 'A sealed typed-v2 record')
    fields = {key: value for key, value in record.items() if key != RECORD_HASH}
    require(canonical_sha256(fields) == record[RECORD_HASH], 'The typed-v2 record hash differs')
    return record


# ---- prepare / load -----------------------------------------------------------------------------------------------
def prepare(root, *, machinery_manifest, roles_repo, pools_root, smoke=False, seed=SEED, slices=None, typed_tree=None,
            root_parent=ROOT_PARENT, base_card=BASE_CARD_DEFAULT, schedule=SCHEDULE_DEFAULT,
            memory_lock=MEMORY_LOCK_DEFAULT, read_plan=READ_PLAN_DEFAULT, read_plan_probe=None,
            program_learning=PROGRAM_LEARNING_DEFAULT, archive=ARCHIVE_DEFAULT, item_stage=ITEM_STAGE_DEFAULT,
            item_quotas=None, read_anchors=readplan.READ_ANCHORS_DEFAULT, gate_rule=GATE_RULE_DEFAULT,
            gate_screen=GATE_SCREEN_DEFAULT, resume_replay=RESUME_REPLAY_DEFAULT):
    """Make the run root and its sealed manifest (design §5.9). ``roles_repo``: chain G's credential repository,
    recorded by path only; ``typed_tree`` / ``root_parent``: test seams (the typed tree this module lives in, /data);
    ``base_card``: the base of every learned mount (addendum D17; the typed-v2 smoke and real run pass
    'historical'), refused before anything is written unless it is one of ``BASE_CARDS``; ``schedule`` and
    ``memory_lock`` (DESIGN 3.6; the typed-v2 smoke and real run pass 'learn_first' and 'unit_shared', addenda D9,
    D13), refused before anything is written unless one of ``SCHEDULES`` and one of ``MEMORY_LOCKS``; ``read_plan``
    (addendum D9; read-plan R2: 'economy' only with 'learn_first') and the smoke-only ``read_plan_probe`` (R7, Q20:
    ``[event, bench]``, only with ``smoke`` and 'economy'), refused before anything is written. typed-v3 (T8, T9):
    ``program_learning`` (one of ``PROGRAM_LEARNING``; the code default 'single' is typed-v2's flow) and ``archive``
    ('none', the code default, or 'index': every package of the tree's verified archive index, per chain; 'repair'
    only), both sealed in every manifest and refused before anything is written. typed-v3 item stage (T3 to T6, brief
    P2b): ``item_stage`` (one of ``ITEM_STAGES``; the code default 'none' is typed-v2's step flow) and, under
    'planned', ``item_quotas`` (None: ``default_item_quotas``; else a table ``check_item_quotas`` admits); both sealed
    in every manifest (``item_quotas`` null under 'none', where a table is refused) before anything is written.
    ``read_anchors`` (typed-v3 T2; ``readplan.READ_ANCHORS``): ('C0', 'C'), the code default, writes typed-v2's
    manifest; ('C',) seals the field ``read_anchors`` and the read arms ``arms`` C, S1..S5 (the arms the owner's
    consent must name), refused before anything is written unless the read plan is 'full' and the base card
    'historical'. ``resume_replay`` (typed-v3 B6 d; ``RESUME_REPLAYS``): 'off', the code default, writes no field;
    'on' seals ``resume_replay`` 'on' (every solver cell and role call replays its saved receipts on resume), refused
    before anything is written unless one of the two. typed-v3 T7 (brief P3b): ``gate_rule`` (one of ``GATE_RULES``;
    'whole', the code default, is typed-v2's rules and writes no field; 'evolution' needs 'planned') and
    ``gate_screen`` (a bool; False, the code default, writes no field; True needs 'planned'), refused before anything
    is written. ``typed_v3_preset`` gives the arguments of the typed-v3 run and smoke."""
    require(type(resume_replay) is str and resume_replay in RESUME_REPLAYS,
            'A registered resume replay %s: %s' % (RESUME_REPLAYS, repr(resume_replay)[:40]))
    require(type(item_stage) is str and item_stage in ITEM_STAGES,
            'A registered item stage %s: %s' % (ITEM_STAGES, repr(item_stage)[:40]))
    require(type(gate_rule) is str and gate_rule in GATE_RULES,
            'A registered gate rule %s: %s' % (GATE_RULES, repr(gate_rule)[:40]))
    require(gate_rule == GATE_RULE_DEFAULT or item_stage == 'planned',
            'The gate rule evolution decides on made items: it needs the item stage planned')
    require(type(gate_screen) is bool, 'The screen switch is true or false: %s' % repr(gate_screen)[:40])
    require(not gate_screen or item_stage == 'planned',
            'The screen runs on made items (gate_screen true): it needs the item stage planned')
    require(item_stage != ITEM_STAGE_DEFAULT or item_quotas is None,
            'An item quota table is sealed with the planned item stage only (item_stage planned)')
    sealed_quotas = (None if item_stage == ITEM_STAGE_DEFAULT
                     else check_item_quotas(deepcopy(default_item_quotas() if item_quotas is None else item_quotas)))
    anchors = readplan.check_read_anchors(read_anchors, read_plan=read_plan, base_card=base_card)
    require(type(base_card) is str and base_card in BASE_CARDS,
            'A registered base card %s: %s' % (BASE_CARDS, repr(base_card)[:40]))
    require(type(schedule) is str and schedule in SCHEDULES, 'A registered schedule %s: %s' % (SCHEDULES, repr(schedule)[:40]))
    require(type(memory_lock) is str and memory_lock in MEMORY_LOCKS,
            'A registered memory lock %s: %s' % (MEMORY_LOCKS, repr(memory_lock)[:40]))
    readplan.check_read_plan(schedule, read_plan, read_plan_probe, smoke=bool(smoke))
    require(type(program_learning) is str and program_learning in PROGRAM_LEARNING,
            'A registered program learning %s: %s' % (PROGRAM_LEARNING, repr(program_learning)[:40]))
    sealed_archive = archives.sealed(archive)
    require(not sealed_archive or program_learning == 'repair',
            'An archive package is a candidate of the repair program learning only (T9): program_learning repair')
    root = check_root(root, smoke=smoke, parent=root_parent)
    require(type(seed) is int, 'An integer seed')
    sizes = slice_sizes(slices, smoke=smoke)
    code = machinery_code()  # the machinery guard first: a refused machinery leaves no root behind
    tree = TYPED_TREE if typed_tree is None else typed_tree
    machinery = read_machinery(machinery_manifest)
    pools, drawn = {}, {}
    for bench in ORDER:
        items, provenance = load_pool(bench, pools_root)
        pools[bench] = provenance
        drawn[bench] = draw_slices(items, bench, sizes=sizes[bench], seed=seed)
    mode = 'smoke' if smoke else 'run'
    fields = {
        'version': VERSION, 'configuration': CONFIGURATION, 'machinery': MACHINERY, 'smoke': bool(smoke),
        'root': str(root), 'evidence': EVIDENCE[mode], 'route_b_evidence': ROUTE_B_EVIDENCE[mode],
        'prepared_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'order': list(ORDER), 'chains': list(CHAINS),
        'arms': list(READ_ARMS) if anchors == readplan.READ_ANCHORS_DEFAULT else list(readplan.read_events(anchors)),
        'mount_arms': list(MOUNT_ARMS), **sealed_constants(seed=seed),
        **({'read_anchors': list(anchors)} if anchors != readplan.READ_ANCHORS_DEFAULT else {}),
        'seed': seed, 'slice_sizes': sizes, 'slices': drawn, 'pools': pools, 'pools_root': str(Path(pools_root).absolute()),
        'cards': {bench: format_block(bench) for bench in ORDER}, 'base_card': base_card,
        'schedule': schedule, 'memory_lock': memory_lock, 'read_plan': read_plan,
        **({'read_plan_probe': None if read_plan_probe is None else list(read_plan_probe)} if smoke else {}),
        'program_learning': program_learning, 'archive': sealed_archive,
        'item_stage': item_stage, 'item_quotas': sealed_quotas,
        **({'resume_replay': resume_replay} if resume_replay != RESUME_REPLAY_DEFAULT else {}),
        # typed-v3 T7: written only when not at their defaults (a default manifest is the one before them)
        **({'gate_rule': gate_rule} if gate_rule != GATE_RULE_DEFAULT else {}),
        **({'gate_screen': gate_screen} if gate_screen is not GATE_SCREEN_DEFAULT else {}),
        'clients': {'roles_repo': str(roles_repo), 'northgate_env': client.NORTHGATE_ENV},
        'machinery_manifest': {'path': machinery['path'], 'record_sha256': machinery['record_sha256'],
                               'evidence': machinery['evidence']},
        'runtime': machinery['runtime'], 'pinned': machinery['pinned'], 'machinery_pools': machinery['pools'],
        'sandbox': machinery['sandbox'], 'slot_root': machinery['slot_root'], 'history_root': machinery['history_root'],
        'machinery_code': code,
        'provenance': {'machinery': machinery['provenance'], 'typed_tree': tree_provenance(tree),
                       'typed_code': typed_code(tree)},
        'tau_rule': tau_rule(),
        'embedding': {'model': EMBED_MODEL, 'revision': EMBED_REVISION, 'dim': EMBED_DIM},
    }
    record = seal(fields)
    for name in ('shared', *CHAINS):
        (root / name).mkdir(parents=True, exist_ok=False)
    units.write_json(root / MANIFEST, record)
    return record


def load_manifest(root):
    """The root's sealed manifest: the root owned by this version first (``own_root``), then hash-verified, bound to
    this root and version, sealing exactly this code's constants (``sealed_constants``), a registered base card
    (``base_card_of``, addendum D17), a registered schedule and memory lock (``schedule_of``, ``memory_lock_of``,
    DESIGN 3.6), a read plan allowed with that schedule (``read_plan_of``, read-plan R3), a registered program
    learning and archive (``program_learning_of``, ``archive_of``; typed-v3 T8, T9: absent means the typed-v2 flow)
    and a well-formed code identity (``machinery_code``, ``provenance.typed_code``:
    ``_check_code_identity``); refused otherwise."""
    root = own_root(Path(root).absolute())
    record = verify(units.read_json(root / MANIFEST))
    require(record.get('configuration') == CONFIGURATION and record.get('version') == VERSION,
            'A %s manifest' % VERSION)
    recorded = Path(record.get('root', ''))
    require(recorded == root or recorded.resolve(strict=False) == root.resolve(strict=False),
            'The manifest belongs to another root: ' + str(recorded))
    changed = [key for key, value in sealed_constants().items() if record.get(key) != value]
    require(not changed, 'The manifest seals other values than this code for %s: a new root is needed' % changed)
    base_card_of(record)
    schedule_of(record)
    memory_lock_of(record)
    read_plan_of(record)
    program_learning_of(record)
    archive_of(record)
    item_quotas_of(record)  # and item_stage_of (typed-v3 T3 to T6: absent means typed-v2's step flow)
    read_anchors_of(record)
    gate_rule_of(record)  # typed-v3 T7 (brief P3b): absent means typed-v2's rules and no screen
    gate_screen_of(record)
    resume_replay_of(record)  # typed-v3 B6 d: absent means typed-v2's resume
    _check_code_identity(record)
    return record
