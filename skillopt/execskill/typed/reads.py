"""Consent-gated test-panel reads of typed-v2 (design §3, §5.8).

A read unit opens one of the five registered main-v10 test panels only after the owner's consent record passed
(``consent``), through the route-B readers (``coevo5.data.test_panel`` / ``zebralogic.test_panel``) behind the one
``data.TestAccess`` this module constructs (``panel_tasks``), inside a directory whose name carries ``test``
(``test-read-<event>-<bench>``) so that every other typed-v2 writer refuses it (``units.checked_path``). Everything a
read produces -- the cells with their replies, the call records, the aggregate with its pass counts -- stays inside
that directory; the chain sees only the OPEN mirror ``<chain>/read-status/<event>-<bench>.json``, which carries counts
(cells, unknown by kind, tokens, mount fractions) and never a pass/fail count or a text. Nothing from a read flows
back into learning. The smoke replaces the panel by held-out practice items (``practice-read-...``) and needs no
consent. Embeddings for the whole panel are made in ONE batch before any paid cell (the public text goes to the
local CPU embedder, which is allowed; the vectors stay in memory). typed-v3 (T2): the manifest's sealed
``read_anchors`` fix the planned read events (typed-v2's C0, C, S1..S5, or C, S1..S5 without C0); the consent must
name exactly them, and a read of any other event is refused before a panel opens. The panel boundary takes them from
the root's own sealed manifest (``sealed_plan``), never from a caller, admits only the canonical unit label of a
planned event (or the economy pass's), and a finished unit passes the same checks before anything of it is read
again (``_finished_gate``).

Machine and sealing discipline inside a read: the memory-heavy lock is held per CELL around the solve (and around
the SpreadsheetBench test qualification), as main-v10's ``cells.run_cell`` holds it, never around the whole unit by
the read itself (``heavy(bench, unit)``: the manifest's sealed mode, ``chain.heavy_for``; under 'unit_shared' the
ALFWorld preparation resets are locked too, ``preparation_reset``, addendum D13);
the SpreadsheetBench scorer artifacts (they hold the recalculated TEST REFERENCE workbooks, route B
``evaluation.py``) are written under ``<unit>/transient/`` and that directory is deleted once the aggregate is
sealed, with a deletion manifest (``transient-deleted.json``: file count and the sha of the path list, never
content); the unit's sandbox containers are drained after its cells (``drain.json``). A read whose unit ended with
a stop or missing cells reports ``status`` 'incomplete'; the chain pauses on it and the owner's recovery reopens
the unit (``units.reopen_stopped``) so that the panel is completed, never read as a reduced panel.

``read_panel`` takes either the explicit factories of design §5.8 or the chain's ``services`` object
(``chain.Services``; ``chain.read_one`` calls ``read_panel(root, chain, event, bench, library=, typemap=, services=)``).
"""
from __future__ import annotations

import hashlib
import shutil
import time
from collections import Counter
from contextlib import nullcontext
from pathlib import Path

from skillopt.coevo5 import data
from skillopt.continual_eval.core import require
from skillopt.execskill import evaluation, profiles, solver, v218_lock, zebralogic
from skillopt.validator_pilot.api import digest

from . import BASE_CARD_DEFAULT, CHAINS, CONFIGURATION, EVIDENCE, ORDER, READ_ARMS, ROUTE_B_EVIDENCE, VERSION, WIDTHS
from . import prepare, readplan, tasktypes, units
from .library import canonical_sha256

ARM_OF_EVENT = {'C0': 'C0', 'C': 'C'}           # every S<k> event reads the library with the F mount
SHEET_WORKERS = 2                                # the test-side reference qualification's scoring width
TRANSIENT = 'transient'                          # evaluation.TRANSIENT: the scorer artifacts' home, deleted at unit end
MOUNT_KEYS = ('arm', 'signature', 'type', 'source', 'distance', 'unknown_reason', 'card_skill', 'system_card_sha256',
              'programs_offered', 'selection', 'programs_enabled')
# keys that may never appear in the open mirror: a pass/fail count or a text would unseal the panel
MIRROR_FORBIDDEN_KEYS = frozenset({'correct', 'incorrect', 'pass', 'fail', 'passed', 'failed', 'accuracy', 'reply',
                                   'prediction', 'output', 'output_excerpt', 'response', 'item_ids', 'items_list'})
MIRROR_MAX_TEXT = 128                            # a hash is 64 hex characters; nothing longer belongs in the mirror
UNKNOWN_PREFIX = 'unknown'
ROUTE_B_OF_TYPED = {EVIDENCE[mode]: ROUTE_B_EVIDENCE[mode] for mode in EVIDENCE}


# ---- names ----------------------------------------------------------------------------------------------------
def arm_of(event):
    """The mount arm of a read event: the anchors read C0 / C, every step reads the library (F)."""
    require(event in READ_ARMS, 'A registered read event: ' + str(event))
    return ARM_OF_EVENT.get(event, 'F')


def unit_name(event, bench, *, smoke=False):
    """``test-read-<event>-<bench>``: the name itself seals the directory (design §3); the smoke's practice reads
    carry no sealed marker because they hold practice items only."""
    require(event in READ_ARMS and bench in ORDER, 'A registered read event and bench: %s %s' % (event, bench))
    return ('practice-read-' if smoke else 'test-read-') + event + '-' + bench


def unit_dir(root, chain, event, bench, *, smoke=False):
    require(chain in CHAINS, 'A registered chain: ' + str(chain))
    return Path(root) / chain / unit_name(event, bench, smoke=smoke)


def status_path(root, chain, event, bench):
    """The open mirror the chain and the readout may read (counts only)."""
    require(chain in CHAINS and event in READ_ARMS and bench in ORDER, 'A registered chain, event and bench')
    return Path(root) / chain / 'read-status' / (event + '-' + bench + '.json')


def route_b_evidence(label):
    """Route-B records (panel registry, sheet qualification) admit route-B labels only (design §5.4); a typed-v2
    label is translated to its twin so that callers may pass either."""
    found = ROUTE_B_OF_TYPED.get(label, label)
    require(found in ROUTE_B_EVIDENCE.values(), 'An admitted route-B evidence label or its typed-v2 twin: ' + str(label))
    return found


# ---- consent ----------------------------------------------------------------------------------------------------
def consent(shared, arms=READ_ARMS):
    """The owner's recorded consent to typed-v2's test reads: ``shared/consent.json`` with exactly the route-B
    ``CONSENT_FIELDS`` (main-v10's shape), ``by`` owner, test evaluation and the sheet qualification both granted,
    ``multi_arm_arms`` naming exactly ``READ_ARMS`` in order, a nonblank date and note. Refused otherwise, before
    any panel is opened (typed-v2's arms are not registered with route B, so ``evaluation.consent`` cannot judge
    them: this validator is the typed-v2 read gate). The rules are typed-v1's, unchanged (DESIGN 4.4).

    typed-v3 (T2): ``arms`` are the read events the run plans (``readplan.read_events`` of its sealed
    ``read_anchors``: READ_ARMS by default, C, S1..S5 without C0), never any other list; the record must name
    exactly them in order, so a consent for the seven events does not cover a run of six and the reverse."""
    arms = tuple(arms) if isinstance(arms, (list, tuple)) else arms
    require(arms in tuple(readplan.read_events(anchors) for anchors in readplan.READ_ANCHORS),
            'The planned read events of a run (readplan.read_events): ' + repr(arms)[:80])
    path = Path(shared) / 'consent.json'
    require(path.is_file(), 'No recorded owner consent to the typed-v2 test reads: ' + str(path))
    value = units.read_json(path)
    require(isinstance(value, dict) and set(value) == set(profiles.CONSENT_FIELDS),
            'The typed-v2 consent holds exactly the fields ' + str(sorted(profiles.CONSENT_FIELDS)))
    require(value['by'] == 'owner', 'Only the owner consents to a test read')
    require(value['test_evaluation'] is True and value['sheet_test_qualification'] is True,
            'The typed-v2 consent grants the test evaluation and the SpreadsheetBench test qualification')
    require(value['multi_arm_arms'] == list(arms),
            'The typed-v2 consent names exactly the read arms %s in order' % list(arms))
    require(all(isinstance(value[key], str) and value[key].strip() for key in ('date', 'note')),
            'The typed-v2 consent carries a nonblank date and note')
    return value


# ---- the panel --------------------------------------------------------------------------------------------------
def panel_tasks(shared, pinned, bench, unit, *, runtime, native, evidence, run=None, alfworld_views=None, panel=None,
                arms=None):
    """The items of one test panel for one read unit (``evaluation.test_tasks`` for typed-v2): consent first, then
    the only ``data.TestAccess`` of typed-v2, the route-B reader (``zebralogic.test_panel`` on its separately pinned
    sealed panel, ``coevo5.data.test_panel`` otherwise), the write-once panel registry ``shared/test/<bench>.json``
    (``evaluation._registry``: a later read must find the same panel), the test-side SpreadsheetBench reference
    qualification (``evaluation._sheet_qualification``, configuration-free branch, once per root for both chains) with
    the same filtering as ``evaluation.test_tasks``, and ALFWorld routing views built in memory by ``alfworld_views``
    (``evaluation.alfworld_reset``'s ``reset(public)``), never written. ``evidence``: a route-B label or its typed
    twin; ``run``: the manifest's record hash (the registry binds one run to the root); ``panel``: a synthetic reader
    in tests.

    typed-v3 (T2; Codex review P3r): the planned read events are the ones the ROOT seals (``sealed_plan`` of the root
    whose ``shared`` directory this is), never a caller's list: ``arms`` (optional; ``open_panel`` passes its
    manifest's) must be exactly them. The label is the canonical ``<chain>/test-read-<event>-<bench>`` of a planned
    event, or exactly ``<chain>/test-read-plan`` -- the economy pass, only with typed-v2's seven events and, on a root
    with a manifest, its sealed read plan 'economy'; any other label is refused. The consent must name exactly the
    planned events. All of it is checked before the one ``data.TestAccess`` exists."""
    require(bench in ORDER, 'A registered bench: ' + str(bench))
    require(isinstance(unit, str) and 'test-read' in unit, 'A typed-v2 read unit label carries test-read')
    require(Path(shared).name == 'shared', 'The shared directory of a run root (<root>/shared): ' + str(shared))
    chain, _, name = unit.partition('/')
    require(chain in CHAINS, 'A read unit label <chain>/<unit> of a registered chain: ' + unit[:80])
    event = _label_event(name, bench, smoke=False)
    planned, record = _planned(Path(shared).parent, arms)
    if event is None:  # the economy pass's label
        require(planned == READ_ARMS and (record is None or record.get('read_plan') == 'economy'),
                'A panel-plan read the run does not plan (read_plan economy, typed-v2\'s seven events): ' + name)
    else:
        require(event in planned, 'A read of an event the run does not plan (read_anchors): ' + name)
    evidence = route_b_evidence(evidence)
    # nothing below runs without it; typed-v2's seven events keep the one-argument call
    allowed = consent(shared) if planned == READ_ARMS else consent(shared, arms=planned)
    reader = panel if panel is not None else (zebralogic.test_panel if bench == 'zebralogic' else data.test_panel)
    if bench == 'zebralogic':                              # main-v10 pins its sealed Zebra panel separately (evaluation.py:446)
        require(isinstance(pinned, dict) and bench in pinned, 'main-v10 pins its sealed Zebra panel separately')
        pinned = pinned[bench]
    tasks, report = reader(pinned, bench, access=data.TestAccess(unit))
    ids = _task_ids(tasks)
    entry = {'run': run, 'benchmark': bench, 'panel_hash': report['panel_hash'], 'tasks': ids,
             'excluded_without_pages': report.get('excluded_without_pages'), 'source_files': report.get('source_files')}
    evaluation._registry(shared, bench, entry, evidence)
    if bench == 'spreadsheetbench':
        tasks = _qualified(shared, tasks, runtime, allowed=allowed, native=native, evidence=evidence)
    if bench == 'alfworld':
        require(alfworld_views is not None, 'An ALFWorld read builds its routing views with a reset (alfworld_views)')
        tasks = evaluation._with_views(tasks, bench, alfworld_views)
    return tasks


def _label_event(name, bench, *, smoke):
    """The read event of a read unit's name: ``unit_name(event, bench, smoke=smoke)`` of an event of ``READ_ARMS``,
    or None for the economy pass's directory (``readplan.SEALED_DIR``; the smoke's ``SMOKE_SEALED_DIR``). Any other
    name -- an unregistered event (``test-read-S6-<bench>``), another bench's unit, a nested path -- is refused
    (Codex review P3r)."""
    if name == (readplan.SMOKE_SEALED_DIR if smoke else readplan.SEALED_DIR):
        return None
    found = next((event for event in READ_ARMS if name == unit_name(event, bench, smoke=smoke)), None)
    require(found is not None, 'A canonical read unit name (%s<event>-%s of a registered event, or %s): %s'
            % ('practice-read-' if smoke else 'test-read-', bench,
               readplan.SMOKE_SEALED_DIR if smoke else readplan.SEALED_DIR, str(name)[:80]))
    return found


def sealed_plan(root):
    """typed-v3 T2 (Codex review P3r): the read events the root itself seals, read at the panel boundary so that no
    caller's list is trusted. ``<root>/manifest.json`` is hash-verified (``prepare.verify``), of this version and
    configuration and bound to this root; its ``read_anchors`` (``prepare.read_anchors_of``, with its read plan, base
    card and ``arms`` cross-checks) give the events (``readplan.read_events``). A root without a manifest file plans
    typed-v2's seven events (``READ_ARMS``: typed-v2's fixtures; ``prepare`` writes the manifest of every prepared
    root before anything else, so a root with the anchor C alone has one). Returns (events, record or None). It reads
    the open manifest only and leaves the path-name rule (``prepare.own_root``) to its callers, as before: ``read_panel``
    checks it first, the economy pass's tests open panels under a root named after typed-v2."""
    root = Path(root).absolute()
    path = root / prepare.MANIFEST
    if not path.exists() and not path.is_symlink():
        return READ_ARMS, None
    record = prepare.verify(units.read_json(path))
    require(record.get('version') == VERSION and record.get('configuration') == CONFIGURATION,
            'The manifest of the root belongs to another version: ' + str(path))
    recorded = record.get('root')
    require(isinstance(recorded, str) and recorded and (Path(recorded) == root or Path(recorded).resolve(strict=False)
                                                        == root.resolve(strict=False)),
            'The manifest belongs to another root: ' + str(recorded)[:200])
    return readplan.read_events(prepare.read_anchors_of(record)), record


def _planned(root, arms=None):
    """(the planned read events, the sealed record or None) of the root (``sealed_plan``); a caller's list ``arms``
    (its in-memory manifest's events) must be exactly the sealed one, refused otherwise."""
    planned, record = sealed_plan(root)
    if arms is not None:
        found = tuple(arms) if isinstance(arms, (list, tuple)) else arms
        require(found == planned, 'The read events %s are not the ones the root seals (manifest read_anchors): %s'
                % (repr(found)[:80], list(planned)))
    return planned, record


def _task_ids(tasks):
    require(isinstance(tasks, list) and tasks and all(isinstance(t, dict) and isinstance(t.get('task_id'), str)
                                                        and t['task_id'] for t in tasks), 'A nonempty panel of tasks')
    ids = sorted(t['task_id'] for t in tasks)
    require(len(set(ids)) == len(ids), 'Panel task ids are unique')
    return ids


def _qualified(shared, tasks, runtime, *, allowed, native, evidence):
    """SpreadsheetBench reads only its reference-qualified test items (evaluation.test_tasks:456-465)."""
    found = evaluation._sheet_qualification(shared, tasks, runtime['spreadsheetbench'], allowed=allowed,
                                            native=native, workers=SHEET_WORKERS, evidence=evidence)
    require(found['side'] == 'test' and found['task_hashes'] == {t['task_id']: digest(t) for t in tasks},
            'The test qualification belongs to other items')
    require(found['qualified'], 'no_qualified_test_items: spreadsheetbench')
    keep = set(found['qualified'])
    return [t for t in tasks if t['task_id'] in keep]


# ---- embeddings ---------------------------------------------------------------------------------------------------
def view_of(bench, item, runtime):
    """The public routing view the typing sees: route B's ``solver.routing_view`` (the same keys the hooks and
    ``tasktypes.structural_signature`` see; design §5.5)."""
    return solver.routing_view(bench, item['public'], runtime=runtime[bench])


def panel_vectors(bench, items, *, embed, views):
    """{item id: vector} for a whole panel in ONE embedder batch (design §5.8) from the items' routing views
    (``views``: {item id: view}); only public text leaves the process."""
    texts = [tasktypes.public_text(views[item['task_id']]) for item in items]
    vectors = tasktypes.embed_texts(texts, embedder=embed)
    return {item['task_id']: vector for item, vector in zip(items, vectors)}


# ---- the read unit ------------------------------------------------------------------------------------------------
def read_panel(root, chain, event, bench, *, library, typemap, services=None, items=None, mount_fn=None, solve_fn=None,
               embed=None, call_factory=None, worker_factory=None, native=None, ledger=None, widths=None, runtime=None,
               nominal_tokens=None, selector_factory=None, heavy=None, smoke=False, alfworld_views=None, panel=None,
               view_fn=None, resume=False, mode=None, episodes=None, manifest=None, drain=None):
    """One sealed read of one panel with one arm (design §5.8). Returns the open status mirror (counts only).

    Explicit form: ``items`` are injected held-out practice items (the smoke only; ``smoke`` True), otherwise the
    panel comes from ``panel_tasks`` under the owner's consent, pinned by the run's manifest (``manifest`` or
    ``<root>/manifest.json``). ``mount_fn`` / ``solve_fn``: ``mount.mount`` / ``mount.solve`` (design §5.5);
    ``embed``: the embedder callable (None = the CPU venv subprocess); ``call_factory(tag=, unit=, out_path=,
    allow_sealed=)`` and ``selector_factory(...)`` build the recorded ``call(system, user)`` of the solver and of the
    selection call (``units.CallRecorder`` over the chain's solver client; the selector is made for the F arm only);
    ``worker_factory`` (zero-arg, unstarted sandbox worker), ``native``, ``nominal_tokens``, the ``runtime`` table and
    (when given) ``mode`` / ``episodes`` go to ``solve_fn``; ``heavy(bench, unit)``: the memory-heavy lock context,
    held per cell around the solve and around the SpreadsheetBench test qualification (sheet EX / ALFWorld SH;
    ``chain.heavy_for``; ``unit`` is this read unit's name); ``drain()``: the unit drain run after the cells
    (``sandbox.drain_unit``; None in fakes);
    ``alfworld_views``: the reset callable for test games (``evaluation.alfworld_reset``), else built from
    ``episodes``; ``resume``: an interrupted unit reuses its finished cells, and a unit that stopped early (its
    ``done.json`` carries a stop reason or missing cells: a cap, a route-B stop or a cell that raised, which the
    owner has since recovered from) is reopened and completed instead of being reported stopped again.

    Services form (``chain.Services``): everything above is derived from ``services`` (its recorders are admitted to
    the sealed unit, ``mode`` is forwarded, the smoke panel is ``slices[bench]['panel']``, interrupted units
    resume). A complete unit is returned from disk without any call.

    Either form first refuses a root of another typed version (``prepare.own_root``, DESIGN 3.5): the chain checks
    only its own state, and a read must never open, write or report a panel under a typed-v1 root."""
    prepare.own_root(root)
    if services is not None:
        setup = _from_services(services, event, bench, panel=panel, view_fn=view_fn, alfworld_views=alfworld_views)
    else:
        setup = dict(items=items, mount_fn=mount_fn, solve_fn=solve_fn, embed=embed, call_factory=call_factory,
                     worker_factory_for=lambda tag: worker_factory, native=native, ledger=ledger, widths=widths,
                     runtime=runtime, nominal_tokens=nominal_tokens, selector_factory=selector_factory, heavy=heavy,
                     smoke=smoke, alfworld_views=alfworld_views, panel=panel, view_fn=view_fn, resume=resume, mode=mode,
                     episodes=episodes, manifest=manifest, drain=drain)
    return _read(root, chain, event, bench, library=library, typemap=typemap, **setup)


def preparation_reset(services, unit):
    """The ALFWorld preparation reset of a read unit (``evaluation.alfworld_reset`` on the services' episode pool:
    the routing views of the test games, zero model calls), None without an episode pool. Under the manifest's
    'per_cell_plain' (``services.lock_setting`` None) it stays bare, as in typed-v1; under 'unit_shared' it is
    wrapped with ``v218_lock.call(reset, lock_setting, 'alfworld', unit=<chain>/<unit>)`` (addendum D13): the
    environment lock first, then the reset's episode slot, as main-v10's ``v225_read`` locked each reset. The lock
    mode enters no view, request or identity. Shared by every path that opens an ALFWorld panel (the read units and,
    later, the read plan's pass, R23)."""
    episodes = getattr(services, 'episodes', None)
    if episodes is None:
        return None
    reset = evaluation.alfworld_reset(services.runtime['alfworld'], episodes)
    setting = getattr(services, 'lock_setting', None)
    if setting is None:
        return reset
    return v218_lock.call(reset, setting, 'alfworld', unit='%s/%s' % (services.chain, unit))


def _from_services(services, event, bench, *, panel, view_fn, alfworld_views):
    """The explicit read arguments from ``chain.Services``. The chain's recorders write under
    ``<root>/<chain>/<unit>/calls/`` (``chain._calls_path``), i.e. inside the sealed unit, so they are admitted to it
    here; the chain's ``heavy`` is held per cell here (never by the chain around the whole read), the ALFWorld
    preparation reset is ``preparation_reset`` (locked under 'unit_shared'), and the chain's ``drain`` runs for this
    unit after its cells. Under the run's resume replay 'on' (typed-v3 B6 d; ``services.resume_replay``, which
    ``chain.run`` set from the sealed manifest) both recorders of a read cell answer from the cell's calls file what an
    earlier attempt received (``units.replaying``, as the learning cells do): a read cell whose reply was saved before
    its record was written is completed without a send."""
    smoke = services.mode == 'smoke'
    unit = unit_name(event, bench, smoke=smoke)
    replay = getattr(services, 'resume_replay', None) == 'on'

    def recorder(purpose, tag, allow_sealed):
        found = services.solver_call(bench, unit, tag, purpose=purpose)
        if hasattr(found, 'allow_sealed'):
            found.allow_sealed = allow_sealed
        return units.replaying(found) if replay else found
    episodes = getattr(services, 'episodes', None)
    runtime = services.runtime
    if alfworld_views is None and bench == 'alfworld' and not smoke and episodes is not None:
        alfworld_views = preparation_reset(services, unit)
    drain = getattr(services, 'drain', None)
    return dict(items=_smoke_panel(services, bench) if smoke else None, mount_fn=services.mount_fn,
                solve_fn=services.solve_fn, embed=services.embed,
                call_factory=lambda *, tag, unit, out_path, allow_sealed: recorder('solve', tag, allow_sealed),
                selector_factory=lambda *, tag, unit, out_path, allow_sealed: recorder('selection', tag, allow_sealed),
                worker_factory_for=lambda tag: services.worker_factory(bench, unit, tag), native=services.native,
                ledger=services.ledger, widths=WIDTHS, runtime=runtime, nominal_tokens=services.nominal_tokens(bench),
                heavy=getattr(services, 'heavy', None), smoke=smoke, alfworld_views=alfworld_views, panel=panel,
                view_fn=view_fn if view_fn is not None else services.view_fn, resume=True, mode=services.mode,
                episodes=episodes, manifest=services.manifest,
                drain=(lambda: drain(unit)) if drain is not None else None)


def _smoke_panel(services, bench):
    """The smoke's held-out practice items: the ``panel`` slice of the bench (design §5.9), never a test panel."""
    wanted = set((services.slices.get(bench) or {}).get('panel') or [])
    require(wanted, 'The smoke manifest draws a panel slice for ' + bench)
    found = [item for item in services.items[bench] if item['task_id'] in wanted]
    require(len(found) == len(wanted), 'Every panel-slice item of %s is loaded' % bench)
    return found


def _read(root, chain, event, bench, *, library, typemap, items, mount_fn, solve_fn, embed, call_factory,
          worker_factory_for, native, ledger, widths, runtime, nominal_tokens, selector_factory, heavy, smoke,
          alfworld_views, panel, view_fn, resume, mode, episodes, manifest, drain=None):
    root, arm = Path(root), arm_of(event)
    require(chain in CHAINS and bench in ORDER, 'A registered chain and bench')
    require((items is not None) == bool(smoke), 'The smoke injects held-out practice items; a real read opens the panel')
    require(mount_fn is not None and solve_fn is not None and call_factory is not None and ledger is not None,
            'A read needs mount_fn, solve_fn, call_factory and the ledger')
    require(isinstance(widths, dict) and type(widths.get(bench)) is int and widths[bench] > 0, 'A positive width for ' + bench)
    unit = unit_name(event, bench, smoke=smoke)
    where = root / chain / unit
    if units.unit_done(where, allow_sealed=True):
        # Codex review P3r: a finished unit is answered from its sealed records, or reopened, only after the checks of
        # its first opening; nothing of it is read before them
        _finished_gate(root, event, manifest=manifest, smoke=smoke)
        if not (resume and units.reopen_stopped(where, allow_sealed=True)):
            return _existing_status(root, chain, event, bench, where, smoke=smoke)
    opened = open_panel(root, chain, bench, unit, vectors=arm == 'F', setup=dict(
        items=items, manifest=manifest, smoke=smoke, runtime=runtime, view_fn=view_fn, heavy=heavy, native=native,
        alfworld_views=alfworld_views, panel=panel, embed=embed, event=event))
    items, ids, views, vectors = opened['items'], opened['ids'], opened['views'], opened['vectors']
    build = _cell_builder(where, unit, event, vectors, views, library=library, typemap=typemap, mount_fn=mount_fn,
                          solve_fn=solve_fn, call_factory=call_factory, selector_factory=selector_factory,
                          worker_factory_for=worker_factory_for, native=native, runtime=runtime,
                          nominal_tokens=nominal_tokens, mode=mode, episodes=episodes, lock=opened['lock'],
                          base_card=opened['base_card'])
    meta = {'chain': chain, 'event': event, 'bench': bench, 'arm': arm, 'unit': unit, 'smoke': bool(smoke),
            'items': len(ids)}
    # a resumed unit re-runs the cells whose outcome was an infrastructure unknown (no verdict on the item; archived
    # under <unit>/rerun/), as the chain's learning units do on their retry; the rerun entries are this unit's own
    # (unit, tag) pairs (DESIGN 3.4). A read unit runs its arm once per item (a bare label, never a repeat).
    marked = units.mark_infrastructure_reruns(where, ledger, unit=unit, allow_sealed=True) if resume else []
    try:
        cells, stop_reason = units.run_unit(where, [(bench, item, (arm,)) for item in items], unit=unit,
                                            widths={bench: widths[bench]}, build_cell=build, ledger=ledger,
                                            resume=resume, allow_sealed=True, meta=meta)
    except BaseException:
        _drained(where, drain, best_effort=True)
        raise
    finally:
        ledger.consume_reruns(unit, marked)
    _drained(where, drain)
    return _finish(root, chain, event, bench, where, cells, stop_reason=stop_reason, expected=len(ids), smoke=smoke, ids=ids)


def _finished_gate(root, event, *, manifest, smoke):
    """The checks a finished read unit passes before anything of it is read (``_existing_status``: its mirror or its
    sealed cells) or reopened (``units.reopen_stopped``), the ones its first opening passed (Codex review P3r): the
    planned events of its manifest (the given one, else ``<root>/manifest.json`` for a real read, as ``open_panel``),
    on a real root exactly the ones the root seals (``_planned``) and the owner's consent naming exactly them
    (``consent``; typed-v2's seven keep the one-argument call); the event must be one of them. The smoke's practice
    reads need no consent (``open_panel``'s smoke path): the event only."""
    if manifest is None and not smoke:
        manifest = prepare.load_manifest(root)
    arms = readplan.read_events(prepare.read_anchors_of(manifest)) if manifest is not None else READ_ARMS
    if not smoke:
        arms, _ = _planned(root, arms)
    require(event in arms, 'The run does not read the event %s (read_anchors): its finished unit stays closed' % event)
    if not smoke:
        if arms == READ_ARMS:
            consent(root / 'shared')
        else:
            consent(root / 'shared', arms=arms)


def unit_gate(root, unit, *, manifest=None):
    """The checks before anything of a sealed read unit is opened OUTSIDE its read (typed-v3 B6 d; Codex's second look
    at the replay, point 1): the resumed ledger's reconciliation under the resume replay 'on' (``chain.
    _durable_receipts``) reads the saved receipts of the unit's pending calls from its calls files. ``unit``: the
    directory name, which must be the canonical unit of a registered read event of a bench (``_label_event``; the
    economy pass's directory is refused here); then ``_finished_gate``, the gate a finished unit passes before
    anything of it is read: the event is one the root seals (its manifest's read anchors) and the owner's consent
    names exactly the planned events. Raises ValueError otherwise; nothing of the unit is opened here. Returns the
    event."""
    name = str(unit)
    bench = next((b for b in ORDER if name.endswith('-' + b)), None)
    require(name.startswith('test-read-') and bench is not None, 'A sealed read unit test-read-<event>-<bench>: '
            + name[:80])
    event = _label_event(name, bench, smoke=False)
    require(event is not None, 'The economy pass directory is never opened outside its read: ' + name[:80])
    _finished_gate(Path(root), event, manifest=manifest, smoke=False)
    return event


def open_panel(root, chain, bench, unit, *, setup, vectors):
    """The one panel path (read-plan R24): the items of one panel for one unit, their routing views and, when
    ``vectors`` (the F arm), one embedder batch over exactly that list. ``setup``: the arguments ``_read`` receives
    (``read_panel``'s explicit form or ``_from_services``; only ``items``, ``manifest``, ``smoke``, ``runtime``,
    ``view_fn``, ``heavy``, ``native``, ``alfworld_views``, ``panel``, ``embed`` and ``event`` are read here). In
    order: the manifest (``<root>/manifest.json`` for a real read without one), the base card it seals (addendum D17:
    the mount base of an S<k> read; refused before any panel opens; the code default only for the explicit smoke form
    without a manifest), the read events it plans (typed-v3 T2: ``unit`` must be the canonical unit of one of them --
    of ``setup['event']`` when the caller names it, as ``_read`` does -- or the economy pass's directory, which only
    typed-v2's seven events read; ``panel_tasks`` then takes the events from the root's own sealed manifest and
    refuses any difference, and the consent must name exactly them), the view function, the lock
    (``heavy(bench, unit)``; none without one), then the
    panel -- the injected held-out practice items of a smoke, else ``panel_tasks`` under the owner's consent with
    the label ``<chain>/<unit>`` (the SpreadsheetBench test qualification under the memory lock, as its cells are) --
    its ids, the items sorted by id, one view per item and the vectors. Returns {manifest, base_card, items, ids,
    views, vectors, lock}; it sends no model call and writes nothing but what ``panel_tasks`` writes (registry,
    qualification)."""
    root = Path(root)
    items, manifest, smoke, runtime = setup.get('items'), setup.get('manifest'), bool(setup.get('smoke')), setup.get('runtime')
    require(chain in CHAINS and bench in ORDER and isinstance(unit, str) and unit, 'A registered chain, bench and unit')
    require((items is not None) == smoke, 'The smoke injects held-out practice items; a real read opens the panel')
    # Codex review P3r: the canonical unit of its event (or the economy pass's directory), the event the caller names
    event = _label_event(unit, bench, smoke=smoke)
    require('event' not in setup or setup['event'] == event,
            'The read unit %s is not the unit of the event %s' % (unit, setup.get('event')))
    if manifest is None and not smoke:
        manifest = prepare.load_manifest(root)
    # addendum D17: an S<k> read mounts the library on the manifest's base (C0 and C ignore it); only the explicit
    # smoke form without a manifest (tests) mounts on the code default
    base_card = prepare.base_card_of(manifest) if manifest is not None else BASE_CARD_DEFAULT
    # typed-v3 T2: the read events the manifest plans (its sealed read_anchors; typed-v2's seven without a manifest);
    # a read unit's event is one of them, the economy pass reads only with the seven, refused before any panel
    arms = readplan.read_events(prepare.read_anchors_of(manifest)) if manifest is not None else READ_ARMS
    if event is None:
        require(arms == READ_ARMS, 'The run does not read the panel plan (read_anchors %s): %s' % (list(arms), unit))
    else:
        require(event in arms, 'The run does not read the event %s (read_anchors): %s' % (event, unit))
    view_fn, heavy = setup.get('view_fn'), setup.get('heavy')
    view = view_fn if view_fn is not None else (lambda b, item: view_of(b, item, runtime))
    lock = heavy if heavy is not None else (lambda b, unit=None: nullcontext())
    if items is None:
        # the SpreadsheetBench test qualification runs scoring containers: under the memory lock, as its cells are
        with (lock(bench, unit) if bench == 'spreadsheetbench' else nullcontext()):
            items = panel_tasks(root / 'shared', manifest['pinned'], bench, chain + '/' + unit, runtime=runtime,
                                native=setup.get('native'), evidence=_manifest_evidence(manifest),
                                run=manifest.get('record_sha256'), alfworld_views=setup.get('alfworld_views'),
                                panel=setup.get('panel'), arms=arms)
    ids = _task_ids(items)
    items = sorted(items, key=lambda item: item['task_id'])
    views = {item['task_id']: view(bench, item) for item in items}  # built once; the mount gets the same view
    found = panel_vectors(bench, items, embed=setup.get('embed'), views=views) if vectors else {}
    return {'manifest': manifest, 'base_card': base_card, 'items': items, 'ids': ids, 'views': views, 'vectors': found,
            'lock': lock}


def _drained(where, drain, *, best_effort=False):
    """The unit drain after its cells (``drain.json`` inside the unit); a failure is recorded, and re-raised unless
    another exception is already propagating."""
    if drain is None:
        return None
    record = {'unit': where.name, 'at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'result': None, 'error': None}
    try:
        record['result'] = drain()
    except Exception as error:  # noqa: BLE001 -- recorded; a stop kind reaches the chain unless best effort
        record['error'] = type(error).__name__
        units.write_json(where / 'drain.json', record, allow_sealed=True)
        if best_effort:
            return record
        raise
    units.write_json(where / 'drain.json', record, allow_sealed=True)
    return record


def _manifest_evidence(manifest):
    found = manifest.get('route_b_evidence')
    return route_b_evidence(found if found is not None else manifest.get('evidence'))


def _cell_builder(where, unit, event, vectors, views, *, library, typemap, mount_fn, solve_fn, call_factory,
                  selector_factory, worker_factory_for, native, runtime, nominal_tokens, mode, episodes, lock,
                  base_card):
    """``build_cell(bench, item, arm, tag)`` for ``units.run_unit``: a recorded call per cell (its record inside the
    sealed unit), the per-item mount (the view the panel was embedded on, so a SpreadsheetBench workbook is never
    opened twice; the selection recorder on the F arm only; the manifest's ``base_card``, addendum D17), the solve
    under the per-cell memory lock (``lock(bench, unit)``, DESIGN 3.6) with its scorer artifacts under
    ``<unit>/transient/``, the normalized row. A
    route-B stop raised by the solve propagates to ``units.run_unit``, which stops the unit with its kind."""
    calls_dir, scorer_root = where / 'calls', where / TRANSIENT
    extra = {key: value for key, value in (('mode', mode), ('episodes', episodes)) if value is not None}

    def build(bench, item, cell_arm, tag):
        call = call_factory(tag=tag, unit=unit, out_path=calls_dir / (tag + '.json'), allow_sealed=True)
        selector = None
        if cell_arm == 'F' and selector_factory is not None:
            selector = selector_factory(tag=tag, unit=unit, out_path=calls_dir / (tag + '-selection.json'),
                                        allow_sealed=True)
        mounted = mount_fn(bench, item, arm=cell_arm, typemap=typemap, library=library,
                           vector=vectors.get(item['task_id']), selector=selector, view=views.get(item['task_id']),
                           base_card=base_card)
        with lock(bench, unit):
            cell = solve_fn(bench, item, mounted, call=call, runtime=runtime, worker_factory=worker_factory_for(tag),
                            native=native, nominal_tokens=nominal_tokens, unit=unit, tag=tag, scorer_root=scorer_root,
                            **extra)
        return _normalized(cell, bench=bench, item=item, arm=cell_arm, mounted=mounted, call=call, selector=selector,
                           unit=unit, event=event)
    return build


def _normalized(cell, *, bench, item, arm, mounted, call, selector, unit, event):
    """The cell row ``units.run_unit`` stores: the solve's record completed with what the recorders know, the
    unknown rule (an ``unknown*`` token is never scored as wrong: correct None), the mount record, and the selection
    call kept APART from the shell's sends as ``chain._with_selection`` keeps it (``selection_sends``,
    ``selection_request_sha256``, ``selection_tokens``; ``tokens`` adds both parts). The infrastructure flag follows
    ``mount._costs``: only an unknown outcome counts, whichever call failed."""
    require(isinstance(cell, dict), 'solve_fn returns the cell record')
    row = dict(cell)
    row.setdefault('bench', bench)
    row.setdefault('item_id', item['task_id'])
    row['arm'] = arm
    row.setdefault('sends', list(getattr(call, 'sends', [])))
    row.setdefault('tokens', call.tokens() if hasattr(call, 'tokens') else 0)
    row.setdefault('request_sha256', [s.get('request_sha256') for s in row['sends']])
    row.setdefault('failure', None)
    row.setdefault('configuration_error', False)
    row.setdefault('infrastructure_unknown', call.infrastructure_unknown() if hasattr(call, 'infrastructure_unknown') else False)
    row.setdefault('mount', {key: mounted.get(key) for key in MOUNT_KEYS} if isinstance(mounted, dict) else None)
    token = row.get('token')
    if isinstance(token, str) and token.startswith(UNKNOWN_PREFIX):
        row['correct'] = None
    require(row.get('correct') in (True, False, None), 'A cell outcome is True, False or None (unknown)')
    row['solver_tokens'] = int(row['tokens'] or 0)
    row['selection_tokens'] = selector.tokens() if selector is not None and hasattr(selector, 'tokens') else 0
    row['selection_sends'] = list(getattr(selector, 'sends', [])) if selector is not None else []
    row['selection_request_sha256'] = [s.get('request_sha256') for s in row['selection_sends']]
    row['selection_infrastructure_unknown'] = bool(selector is not None and hasattr(selector, 'infrastructure_unknown')
                                                   and selector.infrastructure_unknown())
    row['tokens'] = row['solver_tokens'] + int(row['selection_tokens'] or 0)
    row['infrastructure_unknown'] = row['correct'] is None and (bool(row['infrastructure_unknown'])
                                                                or row['selection_infrastructure_unknown'])
    row['unit'], row['event'] = unit, event
    return row


# ---- aggregate (sealed) and mirror (open) ---------------------------------------------------------------------------
def _unknown_kind(row):
    token = row.get('token')
    if isinstance(token, str) and token.startswith(UNKNOWN_PREFIX):
        return token
    return 'failure:' + str(row['failure']) if row.get('failure') else 'unknown'


def _mount_counts(cells):
    """Routing fractions of a read (design §5.8): typed / unknown by reason, card and program mounts, selection."""
    counts = {'typed': 0, 'unknown': 0, 'unknown_by_reason': Counter(), 'with_card': 0, 'programs_offered': 0,
              'selection_calls': 0, 'selection_status': Counter(), 'programs_enabled': 0, 'enabled_total': 0,
              'missing_mount': 0}
    for row in cells:
        mount = row.get('mount')
        if not isinstance(mount, dict):
            counts['missing_mount'] += 1
            continue
        if mount.get('type'):
            counts['typed'] += 1
        else:
            counts['unknown'] += 1
            counts['unknown_by_reason'][str(mount.get('unknown_reason') or 'none')] += 1
        counts['with_card'] += bool(mount.get('card_skill'))
        counts['programs_offered'] += bool(mount.get('programs_offered'))
        selection = mount.get('selection')
        if isinstance(selection, dict):
            counts['selection_calls'] += 1
            counts['selection_status'][str(selection.get('status') or 'unknown')] += 1
        enabled = mount.get('programs_enabled') or []
        counts['programs_enabled'] += bool(enabled)
        counts['enabled_total'] += len(enabled)
    n = len(cells)
    counts['unknown_by_reason'] = dict(counts['unknown_by_reason'])
    counts['selection_status'] = dict(counts['selection_status'])
    counts['typed_fraction'] = counts['typed'] / n if n else None
    counts['enabled_fraction'] = counts['programs_enabled'] / n if n else None
    return counts


def _tokens(cells):
    solver_tokens = sum(int(row.get('solver_tokens', row.get('tokens')) or 0) for row in cells)
    selection = sum(int(row.get('selection_tokens') or 0) for row in cells)
    return {'solver': solver_tokens, 'selection': selection, 'total': sum(int(row.get('tokens') or 0) for row in cells)}


def aggregate(cells, *, chain, event, bench, unit, expected, stop_reason, smoke, ids, unsubmitted=0):
    """The SEALED aggregate of a read (inside the unit): per arm n, correct / incorrect / unknown counts, tokens,
    mount fractions and the request sha list. Pass counts live here only. ``unsubmitted``: cells that raised before
    any send (no record; they are among the missing cells and make the read incomplete)."""
    by_arm = {}
    for arm in sorted({row['arm'] for row in cells}):
        rows = [row for row in cells if row['arm'] == arm]
        by_arm[arm] = {'n': len(rows), 'correct': sum(row['correct'] is True for row in rows),
                       'incorrect': sum(row['correct'] is False for row in rows),
                       'unknown': sum(row['correct'] is None for row in rows),
                       'unknown_by_kind': dict(Counter(_unknown_kind(row) for row in rows if row['correct'] is None)),
                       'infrastructure_unknown': sum(bool(row.get('infrastructure_unknown')) for row in rows),
                       'configuration_errors': sum(bool(row.get('configuration_error')) for row in rows),
                       'tokens': _tokens(rows), 'mount': _mount_counts(rows),
                       'request_sha256': sorted(sha for row in rows for sha in (row.get('request_sha256') or []) if sha),
                       'selection_request_sha256': sorted(sha for row in rows for sha in (row.get('selection_request_sha256') or []) if sha),
                       'items': sorted(row['item_id'] for row in rows)}
    return {'version': VERSION, 'kind': 'read-aggregate', 'chain': chain, 'event': event, 'bench': bench, 'unit': unit,
            'arm': arm_of(event), 'smoke': bool(smoke), 'items': len(ids), 'item_ids': list(ids),
            'panel_sha256': digest(list(ids)), 'cells': len(cells), 'expected_cells': expected,
            'missing_cells': expected - len(cells), 'unsubmitted': int(unsubmitted), 'stop_reason': stop_reason,
            'by_arm': by_arm, 'finished': time.strftime('%Y-%m-%dT%H:%M:%S')}


def mirror(aggregate_record):
    """The OPEN status mirror: the aggregate's counts without any pass/fail count, id or text (checked)."""
    found = aggregate_record['by_arm'].get(aggregate_record['arm']) or {
        'n': 0, 'unknown': 0, 'unknown_by_kind': {}, 'infrastructure_unknown': 0, 'configuration_errors': 0,
        'tokens': _tokens([]), 'mount': _mount_counts([])}
    complete = aggregate_record['stop_reason'] is None and aggregate_record['missing_cells'] == 0
    status = {'version': VERSION, 'kind': 'read-status', 'chain': aggregate_record['chain'],
              'event': aggregate_record['event'], 'bench': aggregate_record['bench'], 'arm': aggregate_record['arm'],
              'unit': aggregate_record['unit'], 'smoke': aggregate_record['smoke'],
              'status': 'complete' if complete else 'incomplete', 'stop_reason': aggregate_record['stop_reason'],
              'items': aggregate_record['items'], 'cells': aggregate_record['cells'],
              'expected_cells': aggregate_record['expected_cells'], 'missing_cells': aggregate_record['missing_cells'],
              'unsubmitted': aggregate_record.get('unsubmitted', 0),
              'unknown': found['unknown'], 'unknown_by_kind': dict(found['unknown_by_kind']),
              'infrastructure_unknown': found['infrastructure_unknown'],
              'configuration_errors': found['configuration_errors'], 'tokens': dict(found['tokens']),
              'mount': dict(found['mount']), 'aggregate_sha256': canonical_sha256(aggregate_record),
              'finished': aggregate_record['finished']}
    _counts_only(status)
    return status


def _counts_only(value, path=()):
    """The mirror invariant (design §3): no pass/fail key, no id list, no string longer than a hash."""
    if isinstance(value, dict):
        for key, child in value.items():
            require(key not in MIRROR_FORBIDDEN_KEYS, 'The open mirror never carries %r' % key)
            _counts_only(child, path + (key,))
    elif isinstance(value, (list, tuple)):
        for child in value:
            _counts_only(child, path)
    elif isinstance(value, str):
        require(len(value) <= MIRROR_MAX_TEXT, 'The open mirror never carries a text at ' + '/'.join(map(str, path)))


def _finish(root, chain, event, bench, where, cells, *, stop_reason, expected, smoke, ids):
    """Seal the aggregate inside the unit, delete the transient scorer store (route B ``EvaluationStore.finish``:
    every cell scored, or the unit stopped; a resumed unit scores afresh), then publish the open mirror."""
    unsubmitted = len(list((where / 'unsubmitted').glob('*.json'))) if (where / 'unsubmitted').is_dir() else 0
    record = aggregate(cells, chain=chain, event=event, bench=bench, unit=where.name, expected=expected,
                       stop_reason=stop_reason, smoke=smoke, ids=ids, unsubmitted=unsubmitted)
    units.write_json(where / 'aggregate.json', record, allow_sealed=True)
    deleted = delete_transient(where)
    if deleted is not None:
        units.write_json(where / 'transient-deleted.json', {'unit': where.name, 'finished': record['finished'], **deleted},
                         allow_sealed=True)
    status = mirror(record)
    units.write_json(status_path(root, chain, event, bench), status)
    return status


def delete_transient(where):
    """Delete ``<unit>/transient`` (the SpreadsheetBench scorer artifacts: recalculated test reference workbooks)
    and return its deletion manifest's fields (file count, sha256 of the [{path, sha256}] list; paths relative to the
    store, never content), as route B's ``evaluation._delete_tree``; None when there is no store."""
    root = where / TRANSIENT
    if not root.exists():
        return None
    files = []
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        files.append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    shutil.rmtree(root)
    require(not root.exists(), 'The transient store could not be deleted')
    return {'files': len(files), 'manifest_sha256': canonical_sha256(files)}


def _existing_status(root, chain, event, bench, where, *, smoke):
    """A done unit (design §5.3b resume): its mirror, rebuilt from the sealed cells when the mirror is missing."""
    path = status_path(root, chain, event, bench)
    if path.exists():
        return units.read_json(path)
    done = units.read_json(where / 'done.json', allow_sealed=True)
    cells = [units.read_json(p, allow_sealed=True) for p in sorted((where / 'cells').glob('*.json'))]
    ids = sorted({row['item_id'] for row in cells})
    return _finish(root, chain, event, bench, where, cells, stop_reason=done.get('stop_reason'),
                   expected=done.get('expected_cells', len(cells)), smoke=smoke, ids=ids)
