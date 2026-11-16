#!/usr/bin/env python3
"""Command line of typed-v2 (design §5.9): prepare, smoke, run, readout, status, plan-replay.

Every invocation first cleans its environment like ``scripts/run_execskill.py`` (``prelaunch.launch_env``: no
OPENAI_API_KEY / OPENAI_BASE_URL, PYTHONDONTWRITEBYTECODE=1, ``sys.dont_write_bytecode``), sets ``ALFWORLD_DATA``
from the manifest's runtime before any ALFWorld work (its environment processes spawn, hence the ``__main__``
guard) and exits with route B's codes: 0 complete, 3 paused, 5 awaiting the owner (``typed.EXIT_*``). Every command
first refuses a root of another typed version (``own_roots``: ``prepare.own_root``, DESIGN 3.5).

``--machinery-snapshot P`` (dl): ``skillopt`` is imported from the main-v10 code snapshot P, inserted at
``sys.path[0]`` BEFORE the first ``import skillopt``, and ``skillopt.execskill.__path__`` is then extended with this
tree's ``skillopt/execskill`` so that ``skillopt.execskill.typed`` resolves here. WHY: the SpreadsheetBench scorer's
recalculation qualification is bound to the main-v10 snapshot's engine source (design §5.4, §7); importing the
engine from any other tree would require a new qualification. Without the option this tree serves everything
(tests, dry runs on the Mac). A snapshot that holds its own ``skillopt/execskill/typed`` is refused: it would come
first on the package path and shadow this tree's typed package (a typed-v1 code snapshot would run typed-v1).

The work is delegated through small adapters (``_prepare``, ``_smoke_run``, ``_chain_run``, ``_readout_build``,
``_status``, ``_plan_replay``) so the CLI test can monkeypatch them without running a chain; the adapters import
lazily because the snapshot binding must precede every ``skillopt`` import.

Read plan (addendum D9, D10; spec/read-plan.md R4, R47, R47b, R76, R77, R92): ``prepare --read-plan {full,economy}``
(sealed; 'economy' needs ``--schedule learn_first``) and, for a smoke root only, ``--read-plan-probe <event>:<bench>``;
``run`` and ``smoke`` read the sealed manifest and take ``--stop-after-plan`` (the process that binds the plan pauses
``stopped_after_plan``, exit 5, once its automatic replay is equal); ``smoke --fake --configured`` runs a fake smoke on
the synthetic manifest with the typed-v2 smoke's values (economy reads, the probe), ``--fake-kill-at <point>`` kills
it at one of the three kill points (fakes only). ``plan-replay --root R --chain X [--smoke] [--fake]`` recomputes the
bound plan zero-call from the stored sealed inputs and compares bytes: it prints counts and fixed codes only and exits
0 (equal) or 3 (different, or an error: every exception is caught, its class name and a fixed code printed, no
traceback). The chain starts it itself, as a child process with another PYTHONHASHSEED, right after the binding.

Read anchors (typed-v3 T2): ``prepare --read-anchors C`` seals the anchor C alone (C0 is never read; the consent names
C, S1..S5; with ``--read-plan full`` and ``--base-card historical`` only); without the flag typed-v2's C0 and C.

The typed-v3 preset (brief P3b D): ``prepare --typed-v3`` (with ``--smoke`` for the smoke root) seals every typed-v3
option at once (``prepare.typed_v3_preset``): base card historical, schedule interleaved, read plan full, read anchors
C, memory lock unit_shared, program learning repair, the chain's archive packages of the tree's index, item stage
planned with the quota table of T5 (the smoke: its tiny table), gate rule evolution, the screen, resume replay on. It
refuses every single-option flag beside it (the preset is the whole set); without it a manifest stays typed-v2 style.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
EXIT_COMPLETE, EXIT_PAUSED, EXIT_AWAITING = 0, 3, 5
COMMANDS = ('prepare', 'smoke', 'run', 'readout', 'status', 'plan-replay')
CHAINS = ('G', 'D')
# typed.BASE_CARDS (addendum D17), written out because the parser runs before the snapshot binding (no skillopt import
# here); a test holds the two equal. The typed-v2 smoke and real run prepare with --base-card historical.
BASE_CARDS = ('format', 'historical')
# typed.SCHEDULES and typed.MEMORY_LOCKS (DESIGN 3.6), written out for the same reason and held equal by a test. The
# typed-v2 smoke and real run prepare with --schedule learn_first --memory-lock unit_shared (addenda D9, D13).
SCHEDULES = ('interleaved', 'learn_first')
MEMORY_LOCKS = ('per_cell_plain', 'unit_shared')
# typed.READ_PLANS (read-plan R1, R4) and readplan.CHECKPOINTS (R92), written out for the same reason, held equal by a
# test; the typed-v2 smoke and real run prepare with --read-plan economy (addendum D9).
READ_PLANS = ('full', 'economy')
CHECKPOINTS = ('after-first-inputs', 'after-plan-file', 'replay-child')
# typed.PROGRAM_LEARNING and typed.ARCHIVE_CHOICES (typed-v3, CHAIN-DECISIONS T8, T9), written out for the same reason,
# held equal by a test: ``prepare --program-learning {single,repair}`` and ``--archive {none,index}`` (sealed; 'index'
# needs 'repair'); the code defaults 'single' and 'none' are typed-v2's flow.
PROGRAM_LEARNING = ('single', 'repair')
ARCHIVE_CHOICES = ('none', 'index')
# typed.ITEM_STAGES (typed-v3, CHAIN-DECISIONS T3 to T6; brief P2b), written out for the same reason, held equal by a
# test: ``prepare --item-stage {none,planned}`` (sealed; 'planned' seals the default quota table of
# ``prepare.default_item_quotas`` too); the code default 'none' is typed-v2's step flow.
ITEM_STAGES = ('none', 'planned')
# readplan.READ_ANCHORS (typed-v3 T2) as the CLI spells them, held equal by a test: ``prepare --read-anchors C`` seals
# the anchor C alone (no C0 read; needs --read-plan full, the code default, and --base-card historical); the code
# default 'C0,C' is typed-v2's two anchors.
READ_ANCHORS = ('C0,C', 'C')
# typed.RESUME_REPLAYS (typed-v3, CHAIN-DECISIONS B6 d), written out for the same reason, held equal by a test:
# ``prepare --resume-replay on`` seals the replay of saved receipts on resume (every solver cell and role call); the
# code default 'off' is typed-v2's resume (no field written).
RESUME_REPLAYS = ('off', 'on')
# The single-option flags of prepare (argparse destinations) that the typed-v3 preset refuses beside it (brief P3b D)
PRESET_EXCLUSIVE = ('base_card', 'schedule', 'memory_lock', 'read_plan', 'read_plan_probe', 'program_learning', 'archive',
                    'item_stage', 'read_anchors', 'resume_replay')


# ---- import binding ----------------------------------------------------------------------------------------------
def bind_machinery(snapshot, tree=TREE):
    """Import ``skillopt`` from ``snapshot`` and ``skillopt.execskill.typed`` from ``tree`` (module docstring).
    Refused once ``skillopt`` is imported from anywhere, because the binding could no longer take effect, and for a
    snapshot that holds a ``typed`` package or module under ``skillopt/execskill`` (it would shadow this tree's)."""
    snapshot, tree = Path(snapshot).resolve(), Path(tree).resolve()
    if not (snapshot / 'skillopt' / 'execskill').is_dir():
        raise ValueError('The machinery snapshot holds no skillopt/execskill package: ' + str(snapshot))
    shadowing = sorted(entry.name for entry in (snapshot / 'skillopt' / 'execskill').iterdir()
                       if entry.name.split('.')[0] == 'typed')
    if shadowing:
        raise ValueError('The machinery snapshot holds its own skillopt/execskill/typed (%s), which would shadow this '
                         "tree's typed package: %s" % (', '.join(shadowing), snapshot))
    if not (tree / 'skillopt' / 'execskill' / 'typed').is_dir():
        raise ValueError('This tree holds no skillopt/execskill/typed package: ' + str(tree))
    loaded = [name for name in sys.modules if name == 'skillopt' or name.startswith('skillopt.')]
    if loaded:
        raise ValueError('skillopt is already imported; bind the machinery snapshot before any skillopt import')
    sys.path.insert(0, str(snapshot))
    import skillopt.execskill as execskill
    own = str(tree / 'skillopt' / 'execskill')
    if own not in execskill.__path__:
        execskill.__path__.append(own)
    if str(tree) not in sys.path:
        sys.path.append(str(tree))  # ``scripts.weak_solver_probe`` and the tree's tests stay importable, after the snapshot
    return {'snapshot': str(snapshot), 'tree': str(tree), 'execskill_file': execskill.__file__,
            'execskill_path': list(execskill.__path__), 'sys_path_0': sys.path[0]}


def ensure_tree_importable(tree=TREE):
    """Without a snapshot the tree itself is the import root (``python scripts/run_typed.py`` puts only scripts/ there)."""
    if str(tree) not in sys.path:
        sys.path.insert(0, str(tree))


# ---- environment -------------------------------------------------------------------------------------------------
def clean_environment(environ=None):
    """``run_execskill.clean_environment``: OPENAI_API_KEY / OPENAI_BASE_URL removed, PYTHONDONTWRITEBYTECODE=1,
    no bytecode written by this process or any child it starts."""
    from skillopt.execskill import prelaunch
    environ = os.environ if environ is None else environ
    cleaned = prelaunch.launch_env(environ)
    for key in list(environ):
        if key not in cleaned:
            del environ[key]
    environ.update(cleaned)
    sys.dont_write_bytecode = True


def alfworld_data_of(manifest):
    """``runtime['alfworld']['alfworld_data']`` of a typed manifest (top-level ``runtime``) or of the machinery
    manifest it copies from (same key); None when the manifest carries no ALFWorld runtime."""
    runtime = manifest.get('runtime') if isinstance(manifest, dict) else None
    if not isinstance(runtime, dict):
        runtime = (manifest.get('machinery') or {}).get('runtime') if isinstance(manifest, dict) else None
    alfworld = (runtime or {}).get('alfworld') if isinstance(runtime, dict) else None
    found = alfworld.get('alfworld_data') if isinstance(alfworld, dict) else None
    return str(found) if found else None


def set_alfworld_data(manifest_path, environ=None):
    """Set ALFWORLD_DATA from the manifest before any ALFWorld work (design §5.4); returns the value or None."""
    environ = os.environ if environ is None else environ
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return None
    found = alfworld_data_of(json.loads(manifest_path.read_text(encoding='utf-8')))
    if found is not None:
        environ['ALFWORLD_DATA'] = found
    return found


def manifest_path_for(args):
    """The manifest whose runtime applies: the smoke root's own ``<root>-smoke/manifest.json`` for the smoke
    command, the run's own ``<root>/manifest.json`` once prepared, else the machinery manifest (prepare copies its
    runtime, so every candidate names the same ALFWorld data)."""
    candidates = [Path(args.root) / 'manifest.json']
    if args.command == 'smoke':
        from skillopt.execskill.typed import smoke
        candidates.insert(0, smoke.smoke_root(args.root) / 'manifest.json')
    for own in candidates:
        if own.exists():
            return own
    if getattr(args, 'machinery_manifest', None):
        return Path(args.machinery_manifest)
    from skillopt.execskill.typed import MACHINERY_MANIFEST
    return Path(MACHINERY_MANIFEST)


# ---- adapters (monkeypatched by the CLI test) --------------------------------------------------------------------
def _prepare(root, *, machinery_manifest, roles_repo, pools_root, smoke, base_card=None, schedule=None,
             memory_lock=None, read_plan=None, read_plan_probe=None, program_learning=None, archive=None,
             item_stage=None, read_anchors=None, resume_replay=None, typed_v3=False):
    """``prepare.prepare``; ``base_card`` (addendum D17), ``schedule`` and ``memory_lock`` (DESIGN 3.6), ``read_plan``
    and ``read_plan_probe`` (read-plan R2, R7), ``program_learning`` and ``archive`` (typed-v3 T8, T9), ``item_stage``
    (typed-v3 T3 to T6), ``read_anchors`` (typed-v3 T2: 'C0,C' or 'C', passed on as the tuple) and ``resume_replay``
    (typed-v3 B6 d) only when the command names them, else the code defaults. ``typed_v3`` (brief P3b D): the
    arguments of ``prepare.typed_v3_preset`` (the smoke's with ``smoke``) and no single option beside them."""
    from skillopt.execskill.typed import prepare
    named = {key: value for key, value in (('base_card', base_card), ('schedule', schedule),
                                           ('memory_lock', memory_lock), ('read_plan', read_plan),
                                           ('read_plan_probe', read_plan_probe), ('program_learning', program_learning),
                                           ('archive', archive), ('item_stage', item_stage),
                                           ('resume_replay', resume_replay)) if value is not None}
    if read_anchors is not None:
        named['read_anchors'] = tuple(read_anchors.split(','))
    if typed_v3:
        if named:
            raise ValueError('The typed-v3 preset seals every typed-v3 option itself; no single option beside it: '
                             + ', '.join(sorted(named)))
        named = prepare.typed_v3_preset(smoke=bool(smoke))
    return prepare.prepare(root, machinery_manifest=machinery_manifest, roles_repo=roles_repo, pools_root=pools_root,
                           smoke=smoke, **named)


def _smoke_run(root, chain, *, fake, base_card=None, resume=False, configured=False, stop_after_plan=False,
               fake_kill_at=None):
    """``smoke.run``; ``base_card`` (addendum D17) only when the command names one: the base of a fake smoke's
    synthetic manifest, and for a prepared smoke root a check against the base its manifest seals. ``resume``: a
    paused smoke root resumes with the owner's recovery.json, as ``run --resume`` does (fix-b, review rb-resume 4).
    ``configured``, ``stop_after_plan``, ``fake_kill_at``: read-plan 4.3 S2, R77, R92, passed only when given."""
    from skillopt.execskill.typed import smoke
    return smoke.run(root, chain, **({'fake': True} if fake else {}),
                     **({'base_card': base_card} if base_card is not None else {}), **({'resume': True} if resume else {}),
                     **({'configured': True} if configured else {}),
                     **({'stop_after_plan': True} if stop_after_plan else {}),
                     **({'fake_kill_at': fake_kill_at} if fake_kill_at else {}))


def run_inputs(root, chain, *, roles_repo=None):
    """The chain's client settings and factories (design §5.4; ``scripts/arch_probes.py:323-343``): the route-B
    solver blocks of the machinery configuration (chain D on route B, thinking disabled) and the GLM-5.3 role client
    built as ``manifest._clients`` builds it. Credential repositories are passed by path only, never read here."""
    from skillopt.execskill import client as clients, manifest, routes
    from skillopt.execskill.typed import MACHINERY, ROLES_REPO
    roles_repo = roles_repo or ROLES_REPO
    blocks = {c: manifest.solver_block(c, env_path=roles_repo if c == 'G' else clients.NORTHGATE_ENV,
                                       configuration=MACHINERY, branch=None if c == 'G' else routes.BRANCH,
                                       longest=None if c == 'G' else routes.S1B_CEILING) for c in CHAINS}
    pin = routes.pin('D', 'B', env_path=clients.NORTHGATE_ENV, solver_block=blocks['D'], configuration=MACHINERY)
    settings = {'configuration': MACHINERY, 'clients': {'solver': blocks, 'roles': manifest.role_settings(MACHINERY),
                                                        'routes': {'D': {'B': pin}}}}
    manifest.check_clients(settings['clients'], configuration=MACHINERY)

    def solver(bench):
        made = manifest.make_solver(settings, chain, bench, 'B' if chain == 'D' else None)
        bound = (settings['clients']['solver']['G']['B'][bench] if chain == 'G'
                 else settings['clients']['routes']['D']['B']['B'][bench])
        return made, bound

    def role(max_tokens):
        from scripts.weak_solver_probe import Client
        g, roles = settings['clients']['solver']['G'], settings['clients']['roles']
        return clients.unpooled(Client(roles_repo, roles['model'], proxy=g['proxy'], max_tokens=max_tokens,
                                       read_timeout=roles['read_timeout']),
                                proxy=g['proxy'], read_timeout=roles['read_timeout'])
    return {'settings': settings, 'clients': {'solver': solver, 'role': role}}


def _chain_run(root, chain, *, resume, roles_repo=None, stop_after_plan=False):
    from skillopt.execskill.typed import chain as chain_module
    inputs = run_inputs(root, chain, roles_repo=roles_repo)
    return chain_module.run(root, chain, settings=inputs['settings'], clients=inputs['clients'], embedder=None,
                            resume=resume, **({'stop_after_plan': True} if stop_after_plan else {}))


def _plan_replay(root, chain, *, smoke, fake, base_card=None, kill_at=None):
    """``chain.plan_replay`` (read-plan R47)."""
    from skillopt.execskill.typed import chain as chain_module
    return chain_module.plan_replay(root, chain, smoke=smoke, fake=fake, base_card=base_card, kill_at=kill_at)


def _readout_build(root, *, open_sealed):
    from skillopt.execskill.typed import readout
    return readout.build(root, open_sealed=open_sealed)


def _status(root, *, chains=None):
    from skillopt.execskill.typed import readout
    return readout.status(root, chains=chains)


# ---- state -> exit code ------------------------------------------------------------------------------------------
def exit_code(state):
    """0 for a complete chain, 5 when the pause needs the owner's recovery.json (every pause ``chain.run`` records
    carries ``awaiting_owner``), 3 for every other state (a stop without a pause record, an unknown state)."""
    state = state if isinstance(state, dict) else {}
    status = str(state.get('status') or '')
    if status == 'complete' or state.get('complete') is True:
        return EXIT_COMPLETE
    paused = state.get('paused') if isinstance(state.get('paused'), dict) else {}
    reason = str(paused.get('reason') or '')
    if status.startswith('awaiting') or reason.startswith('awaiting') or paused.get('awaiting_owner') is True:
        return EXIT_AWAITING
    return EXIT_PAUSED


def read_counts(state, chain_dir=None):
    """read-plan R73: the read plan's mode, the short plan hash and the read counts of a chain state (counts only):
    settled pairs of 35, fresh units done and planned, aliases, fallbacks, voided aliases. None for a state without a
    read-plan block. With the chain directory (``run`` and ``smoke`` pass it) an economy chain's counts are
    ``readout.read_counts`` of the chain resolved as the readout and ``status`` resolve it, so the terminal and the
    status print one set of numbers under one set of labels (fix-c, rc-readout-7); without it, the state's own
    markers and entries."""
    block = state.get('read_plan') if isinstance(state, dict) else None
    if not isinstance(block, dict):
        return None
    if chain_dir is not None and block.get('mode') == 'economy':
        from skillopt.execskill.typed import readout
        return {'mode': block.get('mode'), 'plan': (block.get('plan_sha256') or '')[:12] or None,
                'void': block.get('void'),
                'reads': readout.read_counts(readout._resolve_chain(Path(chain_dir), state), state)}
    done = [unit for unit in state.get('done_units') or [] if isinstance(unit, str)]
    fresh = sum(1 for unit in done if unit.startswith('read-') and unit != 'read-plan')
    entries = [entry for benches in (state.get('reads') or {}).values() if isinstance(benches, dict)
               for entry in benches.values() if isinstance(entry, dict)]
    alias = sum(1 for unit in done if unit.startswith('alias-'))
    # typed-v3 T2: the planned pairs, 35 for typed-v2's seven events, 30 without C0 (the state's read_anchors)
    from skillopt.execskill.typed import ORDER, readplan
    pairs = len(readplan.read_events(state.get('read_anchors') or readplan.READ_ANCHORS_DEFAULT)) * len(ORDER)
    return {'mode': block.get('mode'), 'plan': (block.get('plan_sha256') or '')[:12] or None,
            'void': block.get('void'), 'reads': {
                'settled': fresh + alias, 'of': pairs, 'fresh_done': fresh,
                'fresh_planned': (block.get('counts') or {}).get('fresh'), 'alias': alias,
                'fallbacks': len(block.get('fallbacks') or {}),
                'void_aliases': sum(1 for entry in entries if entry.get('kind') == 'void_alias')}}


def state_summary(state, chain_dir=None):
    """What the terminal shows of a chain state: status, step, schedule and phase (DESIGN 3.6), pause and counts,
    and with a read-plan block its mode, plan hash and read counts (read-plan R73; ``read_counts``, through the
    readout's resolver when ``chain_dir`` is given); never a reply or a test number."""
    state = state if isinstance(state, dict) else {}
    done = state.get('done') or state.get('done_units') or []
    status = state.get('status') or ('complete' if state.get('complete') is True else 'paused' if state.get('paused')
                                     else None)
    summary = {'status': status, 'step': state.get('step', state.get('current_step')),
               'schedule': state.get('schedule'), 'phase': state.get('phase'),
               'paused': state.get('paused'), 'done_units': len(done) if isinstance(done, (list, dict)) else done,
               'ledger': state.get('ledger'), 'exit_code': exit_code(state)}
    counts = read_counts(state, chain_dir)
    if counts is not None:
        summary['read_plan'] = counts
    return summary


def _print(value):
    print(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False, default=str))


# ---- commands ----------------------------------------------------------------------------------------------------
def own_roots(args):
    """Every command first refuses a root of another typed version (``prepare.own_root``, DESIGN 3.5) before it reads
    or writes anything there: the given root and, for the smoke, its ``<root>-smoke`` root as well."""
    from skillopt.execskill.typed import prepare as prepare_module
    roots = [Path(args.root)]
    if args.command == 'smoke' or (args.command == 'plan-replay' and args.smoke):
        from skillopt.execskill.typed import smoke as smoke_module
        roots.append(smoke_module.smoke_root(args.root))
    return [prepare_module.own_root(root) for root in roots]


def prepare(args):
    from skillopt.execskill.typed import MACHINERY_MANIFEST, POOLS_ROOT, ROLES_REPO
    own_roots(args)
    machinery_manifest = args.machinery_manifest or MACHINERY_MANIFEST
    set_alfworld_data(machinery_manifest)
    named = {key: getattr(args, key) for key in ('base_card', 'schedule', 'memory_lock', 'read_plan', 'program_learning',
                                                 'archive', 'item_stage', 'read_anchors', 'resume_replay')
             if getattr(args, key)}
    if args.read_plan_probe:
        named['read_plan_probe'] = args.read_plan_probe.split(':')
    if args.typed_v3:  # brief P3b D: the preset is the whole set of typed-v3 options
        given = [key for key in PRESET_EXCLUSIVE if getattr(args, key)]
        if given:
            raise SystemExit('prepare: --typed-v3 seals every typed-v3 option itself; drop --%s'
                             % ', --'.join(key.replace('_', '-') for key in given))
        named = {'typed_v3': True}
    made = _prepare(args.root, machinery_manifest=machinery_manifest, roles_repo=args.roles_repo or ROLES_REPO,
                    pools_root=args.pools_root or POOLS_ROOT, smoke=args.smoke, **named)
    # base_card: the sealed base of the run (D17); schedule and memory_lock: its sealed order and lock mode (DESIGN
    # 3.6; the launcher checks learn_first and unit_shared, D9, D13); machinery_code: the sealed machinery record, so
    # the launcher stops at once unless machinery_code.bound is true (spec/identity.md 1.10; fix-b, review F3)
    summary = ({key: made.get(key) for key in ('configuration', 'machinery', 'record_sha256', 'evidence', 'seed',
                                               'base_card', 'schedule', 'memory_lock', 'machinery_code')}
               if isinstance(made, dict) else made)
    if isinstance(made, dict) and (made.get('read_plan') or 'read_plan_probe' in made):
        summary.update(read_plan=made.get('read_plan'), read_plan_probe=made.get('read_plan_probe'))
    if isinstance(made, dict) and ('program_learning' in made or 'archive' in made):  # typed-v3 T8, T9: what is sealed
        summary.update(program_learning=made.get('program_learning'),
                       archive={chain: {bench: entry.get('package') for bench, entry in sorted(benches.items())}
                                for chain, benches in sorted((made.get('archive') or {}).items())})
    if isinstance(made, dict) and 'item_stage' in made:  # typed-v3 T3 to T6: the stage and the sealed table's totals
        quotas = made.get('item_quotas') or {}
        summary.update(item_stage=made.get('item_stage'),
                       item_quotas={bench: {side: sum((row.get(side) or {}).values()) for side in ('judging', 'shown')}
                                    for bench, row in sorted(quotas.items())} if quotas else None)
    if isinstance(made, dict) and 'read_anchors' in made:  # typed-v3 T2: sealed only when C0 is not read
        summary.update(read_anchors=made.get('read_anchors'), arms=made.get('arms'))
    if isinstance(made, dict) and 'resume_replay' in made:  # typed-v3 B6 d: sealed only when 'on'
        summary.update(resume_replay=made.get('resume_replay'))
    if isinstance(made, dict) and ('gate_rule' in made or 'gate_screen' in made):  # typed-v3 T7: sealed only when set
        # a field left out is its code default ('whole', no screen)
        summary.update(gate_rule=made.get('gate_rule', 'whole'), gate_screen=made.get('gate_screen', False))
    _print({'command': 'prepare', 'root': args.root, 'manifest': summary})
    return EXIT_COMPLETE


def smoke(args):
    own_roots(args)
    set_alfworld_data(manifest_path_for(args))
    if (args.configured or args.fake_kill_at) and not args.fake:
        raise SystemExit('smoke: --configured and --fake-kill-at exist for a fake smoke only (--fake)')
    state = _smoke_run(args.root, args.chain, fake=args.fake,
                       **({'base_card': args.base_card} if args.base_card else {}),
                       **({'resume': True} if args.resume else {}),
                       **({'configured': True} if args.configured else {}),
                       **({'stop_after_plan': True} if args.stop_after_plan else {}),
                       **({'fake_kill_at': args.fake_kill_at} if args.fake_kill_at else {}))
    from skillopt.execskill.typed import smoke as smoke_module
    _print({'command': 'smoke', 'root': args.root, 'chain': args.chain, 'fake': args.fake,
            **state_summary(state, _chain_dir(smoke_module.smoke_root(args.root), args.chain))})
    return exit_code(state)


def _chain_dir(root, chain):
    """The chain directory the terminal summary resolves its read counts in (None when it does not exist)."""
    path = Path(root) / chain
    return path if path.is_dir() else None


def run(args):
    own_roots(args)
    set_alfworld_data(manifest_path_for(args))
    state = _chain_run(args.root, args.chain, resume=args.resume, roles_repo=args.roles_repo,
                       **({'stop_after_plan': True} if args.stop_after_plan else {}))
    _print({'command': 'run', 'root': args.root, 'chain': args.chain,
            **state_summary(state, _chain_dir(args.root, args.chain))})
    return exit_code(state)


def readout(args):
    own_roots(args)
    result = _readout_build(args.root, open_sealed=args.open_sealed)
    _print({'command': 'readout', 'root': args.root, 'mode': result['mode'], 'out': result['out'],
            'written': result['written']})
    return EXIT_COMPLETE


def status(args):
    own_roots(args)
    _print({'command': 'status', **_status(args.root, chains=[args.chain] if args.chain else None)})
    return EXIT_COMPLETE


REPLAY_PRINTED = ('verdict', 'files', 'equal', 'different', 'missing', 'reason', 'code', 'reembedded')


def plan_replay(args):
    """read-plan R47, R47b: the zero-call replay of a bound plan; exit 0 equal, 3 otherwise. Every exception,
    BaseException included, prints only the command, the chain, verdict 'error', the class name and a fixed code."""
    try:
        if args.fake_kill_at and not args.fake:
            raise ValueError('--fake-kill-at exists for a fake replay only')
        own_roots(args)
        found = _plan_replay(args.root, args.chain, smoke=args.smoke, fake=args.fake, base_card=args.base_card,
                             kill_at=args.fake_kill_at)
        found = found if isinstance(found, dict) else {}
        verdict = found.get('verdict') if found.get('verdict') in ('equal', 'different') else 'error'
        _print({'command': 'plan-replay', 'chain': args.chain, **{key: found.get(key) for key in REPLAY_PRINTED},
                'verdict': verdict})
        return EXIT_COMPLETE if verdict == 'equal' else EXIT_PAUSED
    except BaseException as error:  # noqa: BLE001 -- R47b: never a traceback, never a message
        _print({'command': 'plan-replay', 'chain': args.chain, 'verdict': 'error', 'error_class': type(error).__name__,
                'reason': 'replay_exception'})
        return EXIT_PAUSED


HANDLERS = {'prepare': prepare, 'smoke': smoke, 'run': run, 'readout': readout, 'status': status,
            'plan-replay': plan_replay}


def parser():
    top = argparse.ArgumentParser(description='typed-v2: prepare, smoke, run, readout, status')
    top.add_argument('--machinery-snapshot', help='main-v10 code snapshot to import skillopt from (dl; design §5.4)')
    sub = top.add_subparsers(dest='command', required=True)
    for name in COMMANDS:
        p = sub.add_parser(name)
        p.add_argument('--root', required=True, help='the run root (a new, real directory for prepare)')
        if name in ('smoke', 'run', 'plan-replay'):
            p.add_argument('--chain', required=True, choices=CHAINS)
        else:
            p.add_argument('--chain', choices=CHAINS)
        p.add_argument('--machinery-manifest', help='the main-v10 smoke manifest (runtime, pins, sandbox, slot root)')
        p.add_argument('--roles-repo', help='chain G / role credential repository, passed by path only')
        p.add_argument('--pools-root', help='the pinned practice pools directory')
        if name == 'prepare':
            p.add_argument('--smoke', action='store_true', help='prepare the smoke root (held-out practice panels)')
        if name == 'prepare':
            p.add_argument('--schedule', choices=SCHEDULES,
                           help='the sealed order of the run (DESIGN 3.6; the typed-v2 smoke and real run use '
                                'learn_first; default: the code default interleaved). Set only here: run and smoke '
                                'read it from the manifest')
            p.add_argument('--memory-lock', choices=MEMORY_LOCKS,
                           help='the sealed memory-lock mode (DESIGN 3.6, addendum D13; the typed-v2 smoke and real run '
                                'use unit_shared; default: the code default per_cell_plain). Set only here')
            p.add_argument('--read-plan', choices=READ_PLANS,
                           help='the sealed read plan (addendum D9, read-plan R2; the typed-v2 smoke and real run use '
                                'economy, which needs --schedule learn_first; default: the code default full). Set only '
                                'here: run and smoke read it from the manifest')
            p.add_argument('--read-plan-probe', metavar='EVENT:BENCH',
                           help='smoke roots only (read-plan R7, Q20): the pair the real pass makes a fallback class '
                                '(the typed-v2 smoke uses C0:zebralogic); refused on a real root and with full')
            p.add_argument('--program-learning', choices=PROGRAM_LEARNING,
                           help='the sealed program learning (typed-v3 T8): single = the typed-v2 flow (the code '
                                'default), repair = probe, free repair rounds, one paid feedback round. Set only here')
            p.add_argument('--archive', choices=ARCHIVE_CHOICES,
                           help='the sealed archive packages (typed-v3 T9): none (the code default) or index = every '
                                'package of the verified archive index, per chain; needs --program-learning repair')
            p.add_argument('--item-stage', choices=ITEM_STAGES,
                           help='the sealed item stage (typed-v3 T3 to T6): none = the typed-v2 step flow (the code '
                                'default), planned = items made or picked after each step\'s diagnosis, sealed with '
                                'the default quota table (OfficeQA and SpreadsheetBench at zero). Set only here')
            p.add_argument('--read-anchors', choices=READ_ANCHORS,
                           help='the sealed anchor events read before step 1 (typed-v3 T2): C0,C (the code default, '
                                'typed-v2) or C = no C0 read (rows C, S1..S5; the consent names C, S1..S5); C needs '
                                '--read-plan full and --base-card historical. Set only here')
            p.add_argument('--resume-replay', choices=RESUME_REPLAYS,
                           help='the sealed resume replay (typed-v3 B6 d): off = typed-v2 (the code default: a cell '
                                'interrupted after its reply was saved is solved again), on = every solver cell and '
                                'role call replays its saved receipts on resume. Set only here')
            p.add_argument('--typed-v3', action='store_true',
                           help='the typed-v3 preset (brief P3b D): seals base card historical, schedule interleaved, '
                                'read plan full, read anchors C, memory lock unit_shared, program learning repair, the '
                                'archive index, item stage planned with the quota table of T5 (with --smoke the smoke\'s '
                                'tiny table), gate rule evolution, the screen and resume replay on; no single-option '
                                'flag beside it. Set only here')
        if name in ('prepare', 'smoke', 'plan-replay'):
            p.add_argument('--base-card', choices=BASE_CARDS,
                           help='the sealed base of every learned mount (addendum D17; the typed-v2 smoke and real run '
                                'use historical; default: the code default format). smoke: the base of a fake smoke '
                                'without a prepared manifest, else checked against the prepared one')
        if name in ('smoke', 'run'):
            p.add_argument('--stop-after-plan', action='store_true',
                           help='read-plan R77: the process that binds the economy read plan pauses (exit 5) once its '
                                'automatic replay is equal; resume with the owner recovery.json (default off)')
        if name in ('smoke', 'plan-replay'):
            p.add_argument('--fake-kill-at', choices=CHECKPOINTS,
                           help='fakes only (read-plan R92): SIGKILL to the own process group at this point')
        if name == 'plan-replay':
            p.add_argument('--smoke', action='store_true', help='replay the plan of the smoke root <root>-smoke')
            p.add_argument('--fake', action='store_true', help='replay a fake smoke root (its configured synthetic '
                                                               'manifest and fake services)')
        if name == 'smoke':
            p.add_argument('--configured', action='store_true',
                           help='fake smoke without a prepared manifest: the synthetic manifest carries the typed-v2 '
                                'smoke values (learn_first, unit_shared, historical, economy, probe C0:zebralogic)')
            p.add_argument('--fake', action='store_true', help='fake solve/judge/embedder: no Docker, no network')
            p.add_argument('--resume', action='store_true',
                           help='resume the paused smoke root; requires the owner recovery.json of its chain (consumed '
                                'once), as run --resume does')
        if name == 'run':
            p.add_argument('--resume', action='store_true',
                           help='requires the owner recovery.json of the chain (consumed once; after a paused '
                                'SpreadsheetBench test qualification it is forwarded to that attempt\'s own record)')
        if name == 'readout':
            p.add_argument('--open-sealed', action='store_true', help='the owner opens the sealed test reads')
    return top


def main(argv=None):
    args = parser().parse_args(argv)
    if args.machinery_snapshot:
        bind_machinery(args.machinery_snapshot)
    else:
        ensure_tree_importable()
    clean_environment()
    code = HANDLERS[args.command](args)
    return code if type(code) is int else EXIT_COMPLETE


if __name__ == '__main__':  # ALFWorld environment processes spawn: every entry point needs this guard
    sys.exit(main())
