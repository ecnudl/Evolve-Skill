"""The typed-v2 chain (design §2, §5.7): the first-call probe, the two anchor reads, then per bench a noise
unit, a typing unit (with a no-harm unit per same-signature type), an outcomes unit, card rounds, program
candidates, the frozen step records and the five panel reads.

Shared types (addendum D16). When the step's home type also holds the sources of earlier benches (its other members),
the writers also see each member's learn-slice examples (``s<k>/member-<b'>-outcomes``, after an accepted card
``-outcomes-card``) and every card round or program that passed the home rule is checked on each member's gate slice
(``s<k>/member-<b'>-base``, ``s<k>/card-r<j>-member-<b'>``, ``s<k>/program-<i>-member-<b'>``): accepted only if
no_regress holds on every member, else ``member_harm``. A type of one bench runs none of this.

typed-v3 gates (CHAIN-DECISIONS T7; brief P3b), sealed in the manifest. ``gate_rule`` 'evolution': on a step with made
items a card is accepted iff its gain on E = R + A (the real gate items and the judging-side attack items of the step's
sealed ``items.json``) reaches tau_E from the baseline's repeats on E, more items of E got better than worse, and
no_regress holds on the whole gate list J (``gates.card_decision_evolution``; the record keeps its ``evolution``
block); a step without made items (J = R) decides as typed-v2. ``gate_screen`` True: before the R paid runs of every
card round, program slot and archive package of a step with judging-side attack or guard items, the candidate runs
ONCE on A + G (``s<k>/<stem>-screen``, write-once ``screen.json``) and goes on iff R * c >= b (a program or package:
and it fired there); a candidate refused there gets a decision with zero gate cells, and a card round so refused is
still revised in round 2. The screen's cells are never gate runs. Under either of these two options every card,
program and package decision reloaded on resume is applied only if its decision function, run again on the chain's
own records alone (its own screen unit, the cells of the intended arms, nothing sent or written), gives it again
(``verify_decision``).

Everything paid or machine-bound goes through one injectable ``Services`` object, so the fake end-to-end test and
the fake smoke need no network, Docker or /data; ``real_services`` wires the route-B pieces exactly as design §5.4
says and is exercised on Linux only.

Resume: ``<root>/<chain>/state.json`` keeps the done units, the current step and unit, pauses and recoveries. Cell
units resume through ``units.run_unit`` (finished cells reused); role calls and decisions are write-once phase
records that a resumed step reloads and re-applies in order, so the in-memory library and type map of a step are
rebuilt from records, never from a mutable checkpoint. A unit that stopped early keeps a ``done.json`` with its stop
reason, which ``units.run_unit`` would return as done; the chain archives that marker before the unit runs again.

Pauses (``state['paused'] = {reason, unit, detail, at}``): the ledger cap (inside a cell or a role call), eight
consecutive infrastructure unknowns, a first-cell configuration failure, any route-B stop kind raised by a cell
(``errors.STOP_KINDS``: sandbox, balance_exhausted, package, cleanup, configuration, ...), a unit or a test read that
ended with missing cells (``incomplete_unit`` / ``incomplete_read``: a cell that raised outside the shell leaves no
record and is never silently dropped from a gate's or a panel's denominator), a gate arm with an infrastructure or
configuration unknown left after the unit's attempts (``gate_cells_unknown``: nothing is decided, no item is excluded;
a model-side unknown is a final verdict scored 0 and never re-run, addendum O1), a shared gate arm whose recorded mount
differs from its identity (``shared_arm_mismatch``), a resumed gate unit whose recomputed plan differs from its
write-once ``plan.json`` (``gate_plan_changed``), a describer whose reply never arrived for an infrastructure
reason (``describer_unavailable``: infrastructure never overrides a gate), an unconfirmed first call, or any
exception (its class name only: a pause detail never carries text). A pure infrastructure stop is retried once
automatically after 60 s (learning units and read events alike; the cells whose outcome was an infrastructure
unknown are re-run on that retry and on an owner recovery, ``units.mark_infrastructure_reruns``); every other
continuation needs the owner's ``<chain>/recovery.json`` (``{by: 'owner', date, decision}``), consumed exactly once
by an atomic rename into ``recovery-consumed-<n>.json`` and marked ``recovery-applied-<n>.json`` once applied. The token cap is never cleared by a recovery: a capped chain re-pauses at once.

Schedule (DESIGN 3.6, spec/schedule-lock.md Part A; the manifest's sealed ``schedule``): 'interleaved' (the code
default) is typed-v1's order -- confirm, freeze s0, read C0 and C, then per step learn, freeze and read S<k>;
'learn_first' (addendum D9) learns and freezes all five steps first, then reads C0, C and S1..S5, each event from its
own frozen files. Every freeze ends with a write-once receipt ``s<k>/frozen.json`` (record and file hashes of the
step's library and type map); a read event starts only after ``load_frozen`` matched the files with the receipt and
``bind_read`` recorded (or, on re-entry, compared) the mounted hashes in ``state['read_mounts']``, so a changed
frozen file pauses ``frozen_state_changed`` / ``read_mount_changed`` before any call. Under 'learn_first' learning is
closed once reading has begun (read-plan R79): ``learn`` never runs its body again. The order enters no request, no
cell tag, no unit name and no identity.

Read plan (addenda D9, D10, RP1 to RP13; spec/read-plan.md; the manifest's sealed ``read_plan``): 'full' (the code
default) reads every event on five panels fresh as above. 'economy' (with 'learn_first' only) runs, after the last
freeze, the zero-call planning pass (pseudo-unit ``read-plan``: phase 'read', the seven read mounts, consent, the five
panels through ``reads.open_panel``, sealed inputs and identities under ``test-read-plan/``, the open, self-hashed
``read-plan.json``, bound in ``state['read_plan']``), its automatic zero-call replay in a fresh process (R76; byte
equality, else ``read_plan_changed``), the optional ``stop_after_plan`` (R77), then ``read_classes``: the
representatives of the classes fresh in the order S5 .. C0 (the unchanged read units of 'full'), every other member
settled by a write-once alias record after the representative passed the post-read check (R41; a mismatch voids every
alias of that bench, RP10), a final sweep for every pair left unsettled, the completeness check by kind (R46) and the
markers ``step-0`` .. ``step-5``. At every start and resume the bound plan is verified first (R44); a pass failure
pauses ``read_plan_failed`` and its second occurrence with the same code voids the plan (RP11, Q24): every pair is then
read fresh in the economy order. In both read plans every start writes the credential-free, write-once
``solver-settings.json`` (R75) and binds its hash. typed-v3 (T2): the anchors read before step 1 are the manifest's
sealed ``read_anchors``, ('C0', 'C') by default or ('C',) ('full' and base 'historical' only), with which C0 is never
bound, read, consented to or required for completion.

Machine discipline (design §5.4, as main-v10's ``cells.run_cell``): the memory-heavy lock is held per CELL around
the solve (and the SpreadsheetBench test qualification), never around a whole unit by the chain itself; its mode is
the manifest's sealed ``memory_lock`` (``heavy_for``): 'per_cell_plain' (the code default) is typed-v1's plain lock,
one descriptor per cell; 'unit_shared' (addendum D13) is route B's environment lock (``v218_lock.environment``, as
main-v6 .. main-v10 used it), shared by the threads of one unit, with the ALFWorld preparation resets of read units
locked too (``reads.preparation_reset``). Every unit's sandbox containers are drained after the
unit (``sandbox.drain_unit`` with main-v10's cleanup grace) and the workers carry main-v10's cleanup grace and ready
timeout. Container names and drains are scoped by version and root (``container_scope_of``, DESIGN 3.5), so this run
and a typed-v1 run or a smoke of the same chain letter never drain each other's containers. Every real start passes
``start_checks`` (machinery record and typed code equal to the sealed manifest) before the ledger opens. A cell's
selection call is recorded apart from the shell's sends (``selection_sends``): the writers read a cell's first send
as the solver request, which the selection prompt is not.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from skillopt.continual_eval.core import require
from skillopt.execskill.errors import stop_kind
from skillopt.execskill.protocol import CHAINS as CHAINS_MODELS, FIRST_CALL_SYSTEM, FIRST_CALL_USER

from . import (BASE_CARD_DEFAULT, CARD_ROUNDS, CHAINS, EVIDENCE, GATE_REPEATS, GATE_RULE_DEFAULT, GATE_SCREEN_DEFAULT,
               ITEM_STAGE_DEFAULT, LEARN_WIDTHS, MACHINERY, MAX_PROGRAM_CANDIDATES, MAX_PROGRAM_PROPOSALS, ORDER,
               POOLS_ROOT, PROGRAM_LEARNING_DEFAULT, PROGRAM_SMOKE_ITEMS, READ_PLAN_DEFAULT, REPAIR_LIMITS,
               RESUME_REPLAY_DEFAULT, ROLES_REPO,
               ROUTE_B_EVIDENCE, SCHEDULE_DEFAULT, SEED, TAU_MIN_POINTS, TAU_SE_MULTIPLIER, VERSION)
from . import cards, gates, library as library_, readplan, tasktypes, units

STATE, CONFIRM, RECOVERY, LEDGER = 'state.json', 'confirm.json', 'recovery.json', 'ledger.json'
INFRA_STOP = 'eight_consecutive_infrastructure_unknowns'  # units.Ledger.observe_infrastructure's stop reason
RETRY_SECONDS = 60
READ_WORKERS = 5
WRITER_TOKENS, DESCRIBER_TOKENS = 32_768, 16_384  # design §5.4: GLM-5.3 role bounds (writers / describer)
# DESIGN 3.2 "Limits": the module constants of ``typed`` are the defaults; the run reads them only through
# ``Services.limits`` and ``decisions.json`` records the dict (the smoke lowers some, ``smoke.SMOKE_LIMITS``)
DEFAULT_LIMITS = {'card_rounds': CARD_ROUNDS, 'max_program_proposals': MAX_PROGRAM_PROPOSALS,
                  'max_program_candidates': MAX_PROGRAM_CANDIDATES, 'program_smoke_items': PROGRAM_SMOKE_ITEMS,
                  'gate_repeats': GATE_REPEATS}
# DESIGN 3.2 promotion: the statuses of a ``proposals.json`` row (``writers.PROPOSAL_STATUS``) by what the chain does
# with the row. A slot row runs the units ``s<k>/program-<slot>-smoke`` / ``-gate``; an unpromoted row gets a zero-call
# decision row (no unit; ``candidate`` and ``unit`` null); a ``not_needed`` row stays in ``proposals.json`` only.
SLOT_STATUSES = ('passed', 'passed_after_fix')
ZERO_CALL_STATUSES = ('dropped_screen', 'unreadable', 'kind_not_new', 'no_reply')
PROPOSAL_ONLY_STATUSES = ('not_needed',)
# DESIGN 3.4 (D5) with addendum D17: the learning base arm B (the manifest's base card alone) takes the place of C0 on
# the learning side (noise B#1..3, the no-harm baseline B@noise, the F of a new type without skills); C0 is a read arm.
BASE_ARM = 'B'
PLAN = 'plan.json'  # the write-once sharing decision of a gate unit (DESIGN 3.4 "Shared arms", 4.1)
GATE_PAUSES = ('gate_cells_unknown', 'shared_arm_mismatch', 'gate_plan_changed')
# typed-v3 T7 (brief P3b): the screen before a candidate's gate -- unit ``<gate unit stem>-screen`` (the card round's
# unit, ``s<k>/program-<i>``, ``s<k>/program-0``), its write-once record, the classes it runs on (A + G, in J's order)
# -- and the two pauses of a stored record that the chain's records do not give again: a screen record that its cells
# recompute otherwise (``gate_screen_changed``), and a reloaded card / program / package decision that its decision
# function, run again on the records alone, does not give (``gate_decision_changed``, ``verify_decision``; the detail
# is one of ``DECISION_DIFFERENCES``, ``records_missing`` or ``records_invalid:<error class>``). Both pause before
# anything of the decision is applied.
SCREEN_SUFFIX, SCREEN_RECORD = '-screen', 'screen.json'
SCREEN_CLASSES = ('attack', 'guard')
TYPED_V3_GATE_PAUSES = ('gate_screen_changed', 'gate_decision_changed')
QUALIFICATION_PAUSE = 'qualification_paused'  # route B's Pause kind of a paused SpreadsheetBench test qualification
SHEET_QUALIFICATION = 'spreadsheetbench-qualification'  # evaluation.SHEET_QUALIFICATION (under shared/test/)
# model-facing name stems per structural signature (never a benchmark name; design §1.2)
NAME_STEMS = {'question/context': 'evidence-qa', 'puzzle_template': 'grid-puzzle', 'workbook_preview': 'workbook-edit',
              'admissible_commands': 'household-agent'}
STATUS_BLOCKED_WORDS = ('pass', 'correct', 'accuracy', 'fail', 'won', 'score')  # open mirrors carry counts only
# DESIGN 3.6 (spec/schedule-lock.md S6): the write-once receipt of every freeze, ``s<k>/frozen.json``; the entry a
# read event mounts, ``state['read_mounts'][event]``, has the shape the read plan binds (``readplan.READ_MOUNT_KEYS``)
FROZEN = 'frozen.json'
FROZEN_KEYS = ('version', 'chain', 'step', 'bench', 'library_record_sha256', 'typemap_record_sha256',
               'library_file_sha256', 'typemap_file_sha256', 'at', 'record_sha256')
SCHEDULE_PAUSES = ('frozen_state_changed', 'read_mount_changed')  # members of readplan.PAUSE_REASONS
PHASES = ('learn', 'read')  # state['phase'] (DESIGN 3.6); None before the first unit and at completion
ANCHOR_EVENTS = ('C0', 'C')  # read from the frozen s0 state (step 0); typed-v3 T2: a run reads its sealed read_anchors
# read-plan R79: under 'learn_first' learning is closed once any of these exists in the chain directory
READ_UNIT_PREFIXES = ('test-read-', 'practice-read-')
# read-plan 3.6: the chain state's read-plan block (``state['read_plan']``) of a new state
READ_PLAN_STATE_KEYS = ('mode', 'plan_sha256', 'file_sha256', 'bound_at', 'replay', 'fallbacks', 'failures', 'void',
                        'void_reason', 'recoveries', 'counts')
STEP_MARKERS = tuple('step-%d' % k for k in range(len(ORDER) + 1))  # R46: the markers read_classes ends with
# the frozen description of an accepted card whose describer reply never parsed (Codex review 11/10, finding 5)
CARD_FALLBACK_DESCRIPTION = ('Instruction card mounted on every task of this type (public structure: %s); '
                             'it was learned from practice outcomes of this structure.')


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class Paused(Exception):
    """An internal signal: the chain must stop here and record a pause for the owner."""

    def __init__(self, reason, unit, detail=None):
        super().__init__(reason)
        self.reason, self.unit, self.detail = reason, unit, detail


@dataclass
class Services:
    """Everything the chain needs from outside, injectable for fakes (design §5.7; the assignment's field list,
    plus the defaulted fields below).

    manifest: the run's own manifest (slices, pool pins, runtime, sandbox, slot_root, clients without secrets).
    root / chain / mode: the run root, 'G' | 'D', 'run' | 'smoke' (evidence labels follow ``mode``).
    items: {bench: [practice items]} -- each bench's whole typing source (learn and gate are subsets of it).
    slices: {bench: {'learn': [ids], 'gate': [ids], 'panel': [ids] (smoke only)}}.
    runtime: {bench: runtime table} (copied from the machinery manifest at prepare).
    embed: ``texts -> vectors`` or None for the CPU-venv subprocess (``tasktypes.embed_texts``).
    solver_call(bench, unit, tag, *, transform=None, purpose='solve'): a ``units.CallRecorder`` over the chain's
        solver client; ``purpose`` only names the record file (a cell's selection call keeps the cell tag as its
        ledger key, so an interrupted selection call marks the cell for rerun).
    role_call(purpose, unit, tag, max_tokens): a recorder over the GLM-5.3 role client (32768 / 16384).
    worker_factory(bench, unit, tag): a zero-argument factory of an UNSTARTED sandbox worker; the real one names its
        containers by ``sandbox.unit_tag(chain, container_scope + unit)``.
    native: the spreadsheet-native slot pool (None in fakes). heavy(bench, unit=None): the memory-heavy lock context
        manager, held per cell around the solve (and around the SpreadsheetBench test qualification), never by the
        chain around a unit; every typed call site passes its unit name. ``heavy_for`` builds it from the manifest's
        sealed ``memory_lock``: 'per_cell_plain' ignores the unit (typed-v1's call), 'unit_shared' requires it
        (DESIGN 3.6).
    mount_fn / solve_fn: ``mount.mount`` / ``mount.solve`` (design §5.5); the chain hands every mount the manifest's
        ``base_card`` (addendum D17, ``prepare.base_card_of``). view_fn(bench, item): ``mount.view_of``.
    identity_fn: ``mount.mount_identity`` with the same view / runtime wrapper as ``mount_fn`` (DESIGN 3.4 "Shared
        arms": the zero-call identity of a gate arm on one item, with the same ``base_card``); required by every gate.
    write_card / propose_programs / describe / outcomes_for_writer: ``writers`` (design §5.6); both writers get the
        manifest's ``base_card`` (their base card block, D17);
        outcomes_for_writer(cells, items, *, bench, baseline=None) takes the current arm's outcomes for the
        revision round's ordering (``writers.outcomes_for_writer``).
    read_panel: None for ``reads.read_panel`` (called as ``read_panel(root, chain, event, bench, library=,
        typemap=, services=)``; it opens the real panel itself under consent, or the smoke's ``slices[bench]['panel']``
        practice items), or a fake. There is no injectable panel path: design §5.8's consent gate is the only one.
    drain(unit) -> record | None: the unit drain (``sandbox.drain_unit(chain, container_scope + unit, ...)`` on the
        run's docker with main-v10's cleanup grace), called after every cell unit and read unit; None in fakes.
        worker_options: the non-secret sandbox worker option set, recorded in the state for the audit trail (None in
        fakes).
    nominal_tokens(bench): chain D's nominal M, None for chain G. episodes: the alfworld-episode pool (None in fakes).
    write_card(bench=, corpus=<learn items>, ...) and propose_programs(bench=, parent=<program records>, step=k,
        hook_view=<raw routing view>, ...) take the chain's plain objects; ``card_writer`` / ``program_writer`` wrap
        the real writers (leakage corpus, hook-view excerpt, parent Package).
    limits: the five keys of ``DEFAULT_LIMITS`` (card_rounds, max_program_proposals, max_program_candidates,
        program_smoke_items, gate_repeats; the smoke lowers some, ``smoke.SMOKE_LIMITS``).
    cap: the ledger cap, the manifest's sealed ``caps[chain]`` (``real_services`` sets it; None = ``run`` takes it
        from ``manifest['caps']``, never from the code constant). order: the bench order (``ORDER``; tests shorten it).
    close(): closes the clients at the end of ``run``. ledger: set by ``run`` (one per chain).
    machinery_code: the machinery record sealed in the manifest that these services run with (``real_services``:
        ``manifest['machinery_code']``); ``run`` verifies it with ``start_checks`` before the ledger opens and stores
        it in the chain state. None in fakes: an unbound start (local tests, ``smoke --fake``) runs no machinery
        check, only ``own_root`` (spec identity 1.8).
    container_scope: ``'<VERSION>:<root name>:'`` (``container_scope_of``), the prefix of every unit name given to
        ``sandbox.unit_tag`` / ``sandbox.drain_unit``, so that typed-v1, typed-v2 and a smoke root never share a
        container prefix (DESIGN 3.5, D7); stored in the chain state. None in fakes (no containers).
    lock_setting: the route-B lock setting ``heavy`` was built with (``heavy_for``, DESIGN 3.6): None with
        'per_cell_plain'; with 'unit_shared' the setting of ``v218_lock`` (run root, slot root, machinery
        configuration, chain), which ``reads.preparation_reset`` uses to lock the ALFWorld resets of read units.
    solver_settings: {bench: the eight credential-free keys of read-plan 3.5} of the solver block the chain runs with
        (``real_services``: from the client settings; fakes: their scripted values; None: a placeholder record built
        from the manifest's echo ids), written once to ``<chain>/solver-settings.json`` at every start (R75).
    checkpoint(point): the fakes-only kill seam of read-plan R92 (None in real services: skipped).
    replay(root, chain, *, environ, kill_at=None) -> verdict dict: the automatic replay of a bound plan (R76):
        ``replay_child(...)`` runs ``plan-replay`` in a fresh interpreter (real services and the CLI smoke); None
        runs the same replay core in this process (unit tests with in-memory scripted services, R76).
    probe_call(bench, unit, tag) -> call: typed-v3 (T8), the call function of a zero-call program probe: it records
        each request and answers a failed receipt, never sends and never touches the ledger. None (the default and
        the real services): ``ProbeCall`` (``bank.rejudge.probe`` semantics). Read only under 'repair'.
    repair_program(**kw) -> record: typed-v3 (T8), the program repair writer (``writers.repair_program``; None: that
        function). Read only under 'repair'.
    plan_items(*, call, payload, learn_outcomes, repeats, sheet) -> {'call', 'plan', 'validation'}: typed-v3 (T4,
        brief P2b), the analyst of an item round: ONE request through ``call`` (the role recorder of purpose
        ``item_analyst``) with its one format retry, then the fixed-code plan check (None: ``itemstage.plan_items``,
        i.e. ``items.plan.request_plan`` and ``validate_plan``). Read only under the item stage 'planned'.
    make_items(inp) -> result: typed-v3 (T5), the maker or selector of an item round (``items.MakeInput`` in,
        ``MAKERS[bench].make``'s result out; None: that registry). Read only under 'planned'.
    resume_replay: typed-v3 (B6 d), the run's sealed resume replay ('off' or 'on'), set by ``run`` at its start from
        the sealed manifest (the read cells' recorders, built in ``reads``, read it here); None outside a run.
    """
    manifest: dict
    root: Path
    chain: str
    mode: str
    items: dict
    slices: dict
    runtime: dict
    embed: object
    solver_call: object
    role_call: object
    worker_factory: object
    native: object
    heavy: object
    mount_fn: object
    solve_fn: object
    view_fn: object
    write_card: object
    propose_programs: object
    describe: object
    outcomes_for_writer: object
    read_panel: object = None
    drain: object = None
    worker_options: object = None
    nominal_tokens: object = lambda bench: None
    episodes: object = None
    limits: dict = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    cap: object = None
    order: tuple = ORDER
    close: object = lambda: None
    ledger: object = None
    machinery_code: object = None
    container_scope: object = None
    lock_setting: object = None
    identity_fn: object = None
    solver_settings: object = None
    checkpoint: object = None
    replay: object = None
    probe_call: object = None
    repair_program: object = None
    plan_items: object = None
    make_items: object = None
    resume_replay: object = None


# ---- small helpers -----------------------------------------------------------------------------------------------
def _clear_stop(ledger):
    """Re-open a stopped ledger after an owner recovery or the one automatic infrastructure retry (units.Ledger has
    no reopen method; the chain owns this transition and leaves a trace in the ledger state)."""
    with ledger.lock:
        ledger.state.setdefault('reopened', []).append({'reason': ledger.state.get('stop_reason'), 'at': _now()})
        ledger.state['stopped'], ledger.state['stop_reason'], ledger.state['infra_streak'] = False, None, 0
        ledger.stop_event.clear()
        ledger.persist()


def _reopen(unit_dir):
    """Archive the ``done.json`` of a learning unit that stopped early (``units.reopen_stopped``; the sealed read
    units do the same inside ``reads`` with ``allow_sealed``)."""
    return units.reopen_stopped(unit_dir)


def _counts_only(value):
    """Drop every key that could carry a pass/fail count from a read status before it enters the open state."""
    if isinstance(value, dict):
        return {k: _counts_only(v) for k, v in value.items()
                if not any(word in str(k).lower() for word in STATUS_BLOCKED_WORDS)}
    if isinstance(value, list):
        return [_counts_only(v) for v in value]
    return value


def _pool_pin(manifest, bench):
    """The practice pool's pin ({'path', 'sha256'}) of ``bench`` from the run manifest (``prepare``'s ``pools``)."""
    pin = (manifest.get('pools') or {}).get(bench)
    require(isinstance(pin, dict) and pin, 'The manifest pins the practice pool of ' + bench)
    return {k: pin[k] for k in ('path', 'sha256') if k in pin} or dict(pin)


def _echo_models(manifest, chain):
    """The model ids a confirmed first reply may echo: the manifest's client block, else the registered sets."""
    clients = manifest.get('clients') or {}
    block = ((clients.get('routes') or {}).get('D') or {}).get('B') if chain == 'D' else (clients.get('solver') or {}).get('G')
    ids = (block or {}).get('response_model_ids')
    if ids:
        return frozenset(ids)
    from skillopt.execskill import client  # chain G echoes its model id; chain D runs on northgate route B
    return client.NORTHGATE_RESPONSE_MODEL_IDS if chain == 'D' else frozenset({CHAINS_MODELS['G']})


def _first_call_checks(chain, receipt, charged, echo):
    """Route B's first-call rule (chain.first_call): a reply, the registered echo, a settled ledger charge (the
    reported usage, or the reservation bound kept when the usage is missing or invalid: route B reads the charge,
    not the usage block) and, for chain D, no reasoning (the 'unchecked' sentinel fails a receipt without the
    reasoning fields, as route B does)."""
    return {'reply': receipt.get('ok') is True, 'model': receipt.get('returned_model') in echo,
            'settled': type(charged) is int and charged > 0,
            'reasoning': None if chain == 'G' else (receipt.get('reasoning_tokens', 'unchecked') in (None, 0)
                                                    and receipt.get('reasoning_chars') == 0)}


def _correct(cells, item_id, arm):
    """The outcome of one single-run cell (the learn side: the revision round's ordering of examples); a missing cell
    is an unknown outcome, never a wrong one. The gates read whole arms (``gates.arm_runs``), never this."""
    row = cells.get((item_id, arm))
    return None if row is None else row.get('correct')


def _with_selection(row, arm, selector):
    """Complete a cell record with its selection call (its own recorder), kept APART from the shell's sends: the
    writers read ``sends[0]`` as the solver request, and the selection prompt is not one. ``tokens`` adds both
    parts (``solver_tokens`` / ``selection_tokens``); the infrastructure flag follows ``mount._costs``: only an
    UNKNOWN outcome counts as an infrastructure unknown, whichever call failed (a cell whose selection retry
    succeeded and whose outcome is known never feeds the eight-cell infrastructure stop)."""
    require(isinstance(row, dict), 'solve returns a cell record')
    row['arm'] = arm
    for key, default in (('correct', None), ('failure', None), ('configuration_error', False)):
        row.setdefault(key, default)
    row['selection_sends'] = list(selector.sends)
    row['selection_request_sha256'] = [s.get('request_sha256') for s in selector.sends]
    row['selection_tokens'] = selector.tokens()
    row['selection_infrastructure_unknown'] = bool(selector.infrastructure_unknown())
    row['solver_tokens'] = int(row.get('tokens') or 0)
    row['tokens'] = row['solver_tokens'] + int(row['selection_tokens'] or 0)
    row['infrastructure_unknown'] = row['correct'] is None and (bool(row.get('infrastructure_unknown'))
                                                                or row['selection_infrastructure_unknown'])
    return row


def _read_complete(status):
    """A read event is complete only when its mirror reports every expected cell and no stop."""
    return (isinstance(status, dict) and status.get('stop_reason') is None and not status.get('missing_cells')
            and status.get('status', 'complete') == 'complete')


def _pause_detail(error):
    """What a pause may record of an exception: its class name and, for a route-B ``Pause``, its fixed kind label;
    never ``str(error)`` (an embedder's stderr or a KeyError could carry test text)."""
    kind = getattr(error, 'kind', None)
    return type(error).__name__ + (':' + str(kind)[:64] if isinstance(kind, str) and kind else '')


def _outcome_counts(cells, items, arm='F'):
    """Practice-side denominators of one slice: items, cells present, pass / fail / unknown (missing = unknown)."""
    rows = [cells.get((item['task_id'], arm)) for item in items]
    found = [None if row is None else row.get('correct') for row in rows]
    return {'items': len(items), 'cells': sum(row is not None for row in rows), 'pass': sum(c is True for c in found),
            'fail': sum(c is False for c in found), 'unknown': sum(c is None for c in found)}


def _skill_name(library, kind, signature, step, skill_id):
    """A model-facing kebab-case handle from the signature stem; the skill id when the handle is taken."""
    stem = NAME_STEMS.get(signature) or ''.join(c if c.isalnum() else '-' for c in signature.lower()).strip('-')
    name = '%s-card-s%d' % (stem, step) if kind == 'card' else '%s-program-s%d-%s' % (stem, step, skill_id.rsplit('-', 1)[-1])
    taken = {s['name'] for s in library.skills}
    return name if name not in taken and library_.NAME_PATTERN.match(name) else skill_id


def sheet_readiness(runtime):
    """arch_probes.spreadsheet_probe_readiness: the native/recalculation readiness without the legacy extraction
    gate (main-v10 registers explicit-python-fences-v2, which the execskill shell owns)."""
    from skillopt.continual_eval import backends
    checked = deepcopy(runtime)
    checked.pop('code_extraction_version', None)
    return backends.readiness('spreadsheetbench', runtime=checked)


def _keep_earlier_sends(call):
    """DESIGN 3.3: a programs unit interrupted before its ``proposals.json`` was written starts again from the
    proposal call (with a new retry budget), and every send of every attempt stays in the unit's calls file. The new
    attempt's recorder starts from the sends the earlier attempts wrote to that file (the ledger charged them
    already), so its flushes rewrite the file with all of them. A call without a calls file is returned as is. The
    card writer of a round and the describer use it too (fix-b, review rb-resume 2): their calls file outlives a
    pause in the same way."""
    path = getattr(call, 'out_path', None)
    if path is None or not Path(path).exists():
        return call
    earlier = units.read_json(path)
    require(isinstance(earlier, list) and isinstance(getattr(call, 'sends', None), list) and not call.sends,
            'A calls file holds the list of its sends and a new recorder has sent nothing')
    call.sends.extend(earlier)
    return call


class _Replaying:
    """A role recorder that answers a request from the receipts its calls file already holds (Codex P1 F5), by the
    replay rule of a resumed call (``units.ReplayRule``). ``numbered`` (the resume replay 'on', B6 d, the rule the
    solver cells use too): the k-th call of a request (``request_sha256`` of system NUL user, as
    ``units.CallRecorder`` hashes it) is occurrence k of it, and an occurrence the earlier attempt completed gets its
    own saved outcome -- its delivered receipt, or a failure the earlier flow went past (a later record follows it in
    the file: the writer read the failure and went on, e.g. to its format retry or to the next identical fix
    request); any other call goes to the recorder as that occurrence -- among them an occurrence whose failure ends
    the file (where the earlier process stood: a recovery or resume tries it again). Not ``numbered`` ('repair' with
    the resume replay 'off': cb80dcc's rule, kept exactly; nothing is numbered): a request's delivered receipts in file
    order, then the failures before the file's last delivered receipt. Nothing is sent, charged or written for a
    replayed call. The writers' requests follow from their replies, so an attempt resumed after a receipt was saved
    and before its phase record was written repeats the same calls, failures and format retries included, and sends
    only the missing ones. ``replayed``: the request hashes answered so; every other attribute is the recorder's (its
    ``sends`` hold every earlier send, ``_keep_earlier_sends``)."""

    def __init__(self, call, rule, *, numbered=False):
        self._call, self._rule, self._numbered, self.replayed = call, rule, numbered, []

    def __call__(self, system, user):
        transform = getattr(self._call, 'transform', None)
        shown = transform(system, user) if transform is not None else (system, user)
        sha = units.sha256_text(shown[0] + '\x00' + shown[1])
        k = self._call.next_occurrence(sha) if self._numbered else None
        send = self._rule.answer(sha, k)
        if send is not None:
            self.replayed.append(sha)
            return dict(send['receipt'])
        return self._call(system, user, occurrence=k) if self._numbered else self._call(system, user)

    def __getattr__(self, name):
        return getattr(self._call, name)


def _replay_receipts(call, *, numbered=False):
    """The role recorder under the role-call replay: ``_Replaying`` over it when its calls file holds earlier sends
    (``_keep_earlier_sends`` put them in ``call.sends``) that the rule answers a call with (``units.ReplayRule``);
    else the recorder itself (nothing to replay: every call is sent, as typed-v2). ``numbered`` (the resume replay
    'on'): the recorder names each send's occurrence (``count_occurrences``) and the occurrence rule answers; a calls
    file whose sends do not all name their occurrence raises ``units.ReplayRefused`` before anything is sent. Not
    ``numbered`` ('repair' with 'off'): cb80dcc's role-call replay, unnumbered records, its delivered-first rule."""
    if numbered:
        call.count_occurrences()
    rule = units.ReplayRule(getattr(call, 'sends', None), numbered=numbered)
    return _Replaying(call, rule, numbered=numbered) if rule.replays else call


def _holds_delivered(path):
    """A calls file at ``path`` holds a delivered receipt (``ok``, not interrupted: ``units.replay_queues``)."""
    if path is None or not Path(path).exists():
        return False
    return bool(units.replay_queues(units.read_json(path))[0])


def _check_proposal_rows(rows, max_candidates):
    """The chain's reading of ``proposals.json`` (DESIGN 3.2): every row has a registered status; exactly the
    ``passed`` / ``passed_after_fix`` rows hold a slot and a procedure; the slots are 1, 2, ... in row order and at
    most ``max_candidates``, so no ``program-<n>`` unit beyond the limit can exist."""
    slots = []
    for row in rows:
        status, slot = row.get('status'), row.get('slot')
        require(status in SLOT_STATUSES + ZERO_CALL_STATUSES + PROPOSAL_ONLY_STATUSES, 'A registered proposal status')
        promoted = slot is not None
        require(promoted == (status in SLOT_STATUSES) and promoted == isinstance(row.get('procedure'), dict),
                'A slot exactly for a promoted proposal with its procedure')
        if promoted:
            slots.append(slot)
    require(slots == list(range(1, len(slots) + 1)) and len(slots) <= max_candidates,
            'Proposal slots 1..max_program_candidates in row order')


# ---- typed-v3 program learning (CHAIN-DECISIONS T8, T9; 'repair' only) --------------------------------------------
PROBE, REFINED, WRITER_RECORD, REPAIR_RECORD, ARCHIVE_SKILLS = ('probe.json', 'refined.json', 'writer.json',
                                                               'repair.json', 'skills.json')
PROBE_ERROR = 'program_probe'  # the error_type of a probe's failed receipt (``bank.rejudge.probe`` semantics)
# what of an item a probe runs (T8.2): the first request is built after the note hooks of the first call; ALFWorld's
# episode ends at its first step (the first call fails); SpreadsheetBench runs what precedes its first call (its
# pre-check and sheet_feedback come after it and are not reached)
PROBE_SCOPES = {'searchqa': 'first_request', 'officeqa': 'first_request', 'zebralogic': 'first_request',
                'spreadsheetbench': 'before_first_call', 'alfworld': 'first_step'}
PROBE_SUMMARY_KEYS = ('unit', 'items', 'routed', 'fired', 'noted', 'faults', 'unsent', 'failed', 'selection_unrecorded')


class ProbeCall:
    """The call function of a zero-call probe (T8.2): every request is recorded (its sha256 and its user text's
    length, never the text) and answered with a failed receipt, so the shell builds and records the request and goes
    no further; nothing is sent and nothing is charged (no ledger is reachable from here). ``bank.rejudge.probe``
    semantics, with ``sends`` / ``tokens()`` / ``infrastructure_unknown()`` as a cell's recorder has them (a failed
    probe receipt is no infrastructure outcome)."""

    def __init__(self):
        self.requests, self.sends = [], []

    def __call__(self, system, user):
        sha = units.sha256_text(system + '\x00' + user)
        self.requests.append({'request_sha256': sha, 'user_chars': len(user)})
        receipt = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': PROBE_ERROR}
        self.sends.append({'request_sha256': sha, 'receipt': dict(receipt)})
        return receipt

    @staticmethod
    def tokens():
        return 0

    @staticmethod
    def infrastructure_unknown():
        return False


def _probe_summary(probe):
    """The counts of a probe record (``PROBE_SUMMARY_KEYS``) and its total fault count."""
    return {**{key: probe[key] for key in PROBE_SUMMARY_KEYS}, 'fault_count': sum(probe['faults'].values())}


def _probe_key(probe):
    """The order of T8.3 on probes: more noted items first, then fewer faults (a tie keeps the earlier version)."""
    return probe['noted'], -sum(probe['faults'].values())


def _repairable(probe):
    """A probe leaves something to repair: a routed item (one where the program is mounted) without a shown note, or
    a fault. An item the step's type map routes elsewhere (``not_routed``) is no program's to repair."""
    return probe['noted'] < probe['routed'] or sum(probe['faults'].values()) > 0


def _program_candidate(procedures, home_type, background=()):
    """The cand_program candidate of a comparison arm under 'repair' (Codex P1 F4): the measured ``procedures``
    after the step's forced ``background`` (the records accepted earlier in the step, an archive package). Without a
    background one record keeps typed-v2's shape and identity ``{'procedure', 'home_type'}``; else the package shape
    ``{'procedures': [background..., procedures...], 'home_type'}`` (``mount``: every record forced, in this order).
    None when there is nothing to force (arm F)."""
    records = list(background) + list(procedures)
    if not records:
        return None
    if not background and len(procedures) == 1:
        return {'procedure': procedures[0], 'home_type': home_type}
    return {'procedures': records, 'home_type': home_type}


def _recorded_selection(cell):
    """{'use', 'offered', 'enabled'} of the selection call a learn cell's mount made (the names the solver model
    chose, the program skills offered and enabled), None when the cell made none (no cell, an item of no type, a type
    without programs records no selection to answer from)."""
    mounted = cell.get('mount') if isinstance(cell, dict) else None
    selection = mounted.get('selection') if isinstance(mounted, dict) else None
    if not isinstance(selection, dict) or not isinstance(selection.get('use'), list):
        return None
    return {'use': list(selection['use']), 'offered': list(mounted.get('programs_offered') or []),
            'enabled': list(mounted.get('programs_enabled') or [])}


class RecordedSelection:
    """The selection call of a probe side (Codex P1 F2): answered from ``recorded`` (``_recorded_selection`` of the
    item's cell in the step's learn-slice unit) with no model call -- a delivered receipt naming the recorded choice;
    with nothing recorded a failed receipt (``mount`` then enables no selectable program). ``asked``: the mount made
    the call; ``matches(mount)``: the mount offered and enabled exactly the cell's programs."""

    def __init__(self, recorded):
        self.recorded, self.asked = recorded, False

    def __call__(self, system, user):
        self.asked = True
        if self.recorded is None:
            return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': PROBE_ERROR}
        return {'ok': True, 'response': json.dumps({'use': list(self.recorded['use']), 'why': 'recorded selection'}),
                'finish_reason': 'stop', 'usage': {}, 'error_type': None}

    def matches(self, mounted):
        return (self.recorded is not None and mounted.get('programs_offered') == self.recorded['offered']
                and mounted.get('programs_enabled') == self.recorded['enabled'])


def _unpromoted_reason(row):
    """The reason of the zero-call decision of a proposal that never took a slot (DESIGN 3.2): 'screen:' + the
    screen reason (``dropped_screen``: the first check and the failed fix), 'unreadable:' + the reader's problem code
    (the row's reason is 'unparseable: <code>: <sentence>'), 'kind_not_new', or 'no_reply' (a proposal call that
    delivered no reply; ``writers``' seventh status, which DESIGN 3.2 does not list)."""
    status, reason = row.get('status'), (row.get('screen') or {}).get('reason')
    if status == 'unreadable':
        parts = str(reason).split(': ', 2)
        return 'unreadable:' + (parts[1] if len(parts) >= 2 and parts[0] == 'unparseable' else str(reason))
    if status in ('kind_not_new', 'no_reply'):
        return status
    return 'screen:' + str(reason)


# ---- the run ------------------------------------------------------------------------------------------------------
class _Run:
    """One chain process: holds the services, the open state, the in-memory library/type map and the per-bench
    embedding cache (one batch per bench per process)."""

    def __init__(self, services, state, *, sleep):
        self.s, self.state, self.sleep = services, state, sleep
        self.root = Path(services.root) / services.chain
        self.library, self.typemap, self.vectors, self.views = None, None, {}, {}
        # addendum D17: every mount of this chain composes on the manifest's base and both writers see its block
        self.base_card = _base_card(services)
        self.gate_arms = []  # the gate arms of the current step in run order (DESIGN 3.4 "Shared arms")
        self.bound_here = False  # read-plan R77: this process bound the plan (only it stops after the plan)
        # typed-v3 (T8, T9): read once at run start from the sealed manifest; 'single' runs typed-v2's flow untouched
        self.program_learning = _program_learning(services)
        self.archive = _archive_value(services)
        self.archive_learned = None  # the step's post-archive learn outcomes (``archive_outcomes``), for ``finalize``
        # typed-v3 item stage (T3 to T6, brief P2b): read once from the sealed manifest; 'none' runs typed-v2's steps.
        # ``step_items`` is set by the stage of the current step once its ``items.json`` is sealed (``gate_items``)
        self.item_stage, self.item_quotas = _item_stage(services), _item_quotas(services)
        self.step_items = None
        # typed-v3 (T2): the anchor events read before step 1 and every planned read event, from the sealed manifest
        self.anchor_events = _read_anchors(services)
        self.read_events = readplan.read_events(self.anchor_events)
        # typed-v3 (B6 d): read once from the sealed manifest; 'on' replays the saved receipts of every solver cell
        # (``builder``; the read cells in ``reads``) and of every role call (``role``) on resume
        self.resume_replay = _resume_replay(services)
        # typed-v3 (T7, brief P3b): the gate rule and the screen, read once from the sealed manifest ('whole' and no
        # screen: typed-v2's gates, byte-identical records)
        self.gate_rule, self.gate_screen = _gate_rule(services), _gate_screen(services)
        # typed-v3 T7 (Codex review of P3b): the decision unit whose stored decision is being rebuilt from the chain's
        # own records (``verify_decision``, records-only mode: nothing is sent, run, written, marked or drained -- the
        # replay of B6 d is never reached, ``cells``); None otherwise
        self.verifying = None
        # typed-v3 B7b: {cell file: ((inode, size, mtime), (bench, item id) of a refused row, or None)}, the parse
        # cache of ``refused_ids`` (each cell file is read once per process)
        self.refusals = {}

    # ---- state and records ----------------------------------------------------------------------------------
    def persist(self):
        if self.s.ledger is not None:
            self.state['ledger'] = {k: self.s.ledger.state.get(k) for k in ('charged', 'reported', 'sends', 'stopped',
                                                                             'stop_reason', 'missing_usage')}
        self.state['updated'] = _now()
        units.write_json(self.root / STATE, self.state)

    def done(self, unit):
        return unit in self.state['done_units']

    def mark(self, unit):
        if self.verifying is not None:  # records-only mode (verify_decision): the state is not touched
            return
        if not self.done(unit):
            self.state['done_units'].append(unit)
            self.persist()

    def current(self, unit):
        if self.verifying is not None:  # records-only mode (verify_decision): the state is not touched
            return
        self.state['current_unit'] = unit
        self.persist()

    def record(self, unit, name, compute):
        """A write-once phase record: reloaded when present, else computed and written atomically. In records-only
        mode (``verify_decision``) a record that is not there is never computed: the stored decision being checked
        cannot be given again by the chain's records (``gate_decision_changed``, ``records_missing``)."""
        path = self.root / unit / name
        if path.exists():
            return units.read_json(path)
        self.require_records(unit + '/' + name)
        value = compute()
        units.write_json(path, value)
        return value

    def pause(self, reason, unit, detail=None):
        """Every pause ``run`` records awaits the owner's ``recovery.json`` (the one automatic infrastructure retry
        happened inside the unit), which the CLI reports as route B's exit 5."""
        self.state['paused'] = {'reason': reason, 'unit': unit, 'detail': detail, 'at': _now(), 'awaiting_owner': True}
        self.persist()

    def recover(self):
        """Consume the owner's recovery.json exactly once and re-open the ledger (never past the token cap). When
        the pause was route B's paused SpreadsheetBench test qualification, the owner's decision is forwarded to
        that attempt's own ``recovery.json`` (``coevo5.evaluation._next_attempt`` admits a new attempt only then;
        the chain's record alone would re-raise the same pause at the next sheet read).

        Crash safety (Codex review 11/10, finding 8): the owner's record is consumed by ONE atomic rename into
        ``recovery-consumed-<n>.json`` (it can never be consumed twice), and ``recovery-applied-<n>.json`` is written
        only after the state was persisted; a consumed record without its applied record (a crash in between) is
        applied by the next resume -- every step of the application is idempotent."""
        path, unapplied = self.root / RECOVERY, self.unapplied_recovery()
        if unapplied is not None:
            require(not path.exists(), 'A consumed recovery was never applied and a new recovery.json is present; '
                                       'the owner keeps one of them')
            n, value = unapplied
        else:
            require(path.exists(), 'resume requires the owner recovery record ' + str(path))
            value = units.read_json(path)
            require(isinstance(value, dict) and value.get('by') == 'owner' and str(value.get('date') or '').strip()
                    and str(value.get('decision') or '').strip(), "recovery.json needs by='owner', a date and a decision")
            n = 1 + len(list(self.root.glob('recovery-consumed-*.json')))
            self.bind_qualification_target(n)  # durable BEFORE the record is consumed (second review, 11/10)
            os.replace(path, self.root / ('recovery-consumed-%d.json' % n))
        stop = self.s.ledger.state.get('stop_reason')
        forwarded = self.forward_qualification_recovery(value, self.qualification_target(n))
        if not any(r.get('n') == n for r in self.state['recoveries']):
            self.state['recoveries'].append({'n': n, 'decision': value['decision'], 'paused': self.state.get('paused'),
                                             'qualification_attempt': forwarded, 'at': _now()})
        self.state['paused'] = None
        if stop != 'token_cap' and (self.s.ledger.stopped() or stop):
            _clear_stop(self.s.ledger)
        self.persist()
        units.write_json(self.root / ('recovery-applied-%d.json' % n),
                         {'n': n, 'applied_at': _now(), 'ledger_stop': stop, 'qualification_attempt': forwarded})

    def unapplied_recovery(self):
        """(n, owner record) of a consumed recovery without its applied record, else None."""
        for path in sorted(self.root.glob('recovery-consumed-*.json'), key=lambda p: int(p.stem.rsplit('-', 1)[-1])):
            n = int(path.stem.rsplit('-', 1)[-1])
            if not (self.root / ('recovery-applied-%d.json' % n)).exists():
                return n, units.read_json(path)
        return None

    def bind_qualification_target(self, n):
        """Bind recovery n to the qualification attempt it approves, once (``recovery-target-<n>.json``): the last
        unrecovered attempt when the chain's pause was that qualification's pause, else None. WHY durable and before
        the consumption: a replay after a crash must forward the owner's decision to exactly this attempt, never to a
        later attempt another chain may have started (and failed) in between."""
        path = self.root / ('recovery-target-%d.json' % n)
        if path.exists():
            return units.read_json(path)
        paused, target = self.state.get('paused') or {}, None
        if QUALIFICATION_PAUSE in str(paused.get('detail') or ''):
            root = Path(self.s.root) / 'shared' / 'test' / SHEET_QUALIFICATION
            attempts = sorted((p for p in root.glob('attempt-*') if p.is_dir() and p.name[8:].isdigit()),
                              key=lambda p: int(p.name[8:]))
            if attempts and not (attempts[-1] / 'recovery.json').exists():
                target = attempts[-1].name
        record = {'n': n, 'qualification_attempt': target, 'bound_at': _now()}
        units.write_json(path, record)
        return record

    def qualification_target(self, n):
        """The bound attempt name of recovery n (None without a binding: nothing is forwarded)."""
        path = self.root / ('recovery-target-%d.json' % n)
        return units.read_json(path).get('qualification_attempt') if path.exists() else None

    def forward_qualification_recovery(self, value, target):
        """Write route B's ``{by, date, decision}`` into the BOUND qualification attempt (``bind_qualification_target``)
        when it has no recovery record yet; idempotent (a replay finds the record written and changes nothing).
        Returns the attempt name or None. The attempt directory lives under ``shared/test/`` (a sealed name: it holds
        no test answer, only the qualification's own records)."""
        if not target:
            return None
        attempt = Path(self.s.root) / 'shared' / 'test' / SHEET_QUALIFICATION / target
        if not attempt.is_dir():
            return None
        if not (attempt / 'recovery.json').exists():
            units.write_json(attempt / 'recovery.json', {key: value[key] for key in ('by', 'date', 'decision')},
                             allow_sealed=True)
        return target

    # ---- items, views, vectors ------------------------------------------------------------------------------
    def items(self, bench, part):
        by_id = {item['task_id']: item for item in self.s.items[bench]}
        ids = self.s.slices[bench][part]
        require(all(i in by_id for i in ids), 'Every %s id of %s is in its practice source' % (part, bench))
        return [by_id[i] for i in ids]

    def own_items(self, bench):
        """The sealed item list of the current step when ``bench`` is its bench (typed-v3, brief P2b), else None."""
        found = self.step_items
        if found is None or found['bench'] != bench or found['step'] != self.state.get('step'):
            return None
        return found

    def gate_items(self, bench):
        """THE gate list of ``bench`` in the current step (typed-v3 T3.5, brief P2b: J); every gate unit, identity,
        sharing plan and member check reads its items here. For the step's own bench once its ``items.json`` is sealed
        (``itemstage``): the real gate slice followed by the judging-side attack, guard and calibration items, in that
        order; for every other bench (a member of a shared type, D16) and before the seal, and always under the item
        stage 'none': the real gate slice. A later step never sees an earlier step's items (``learn`` clears them)."""
        real, found = self.items(bench, 'gate'), self.own_items(bench)
        return real if found is None else real + list(found['judging'])

    def shown_items(self, bench):
        """The shown made items of the current step (typed-v3 T6: attack first, then guard), [] without a sealed item
        list of ``bench`` (and always under 'none'). They join the learn items wherever writers' examples come from."""
        found = self.own_items(bench)
        return [] if found is None else [item for group in found['shown'] for item in group]

    def shown_examples(self, bench, cells, label, *, baseline=None):
        """typed-v3 T6: the writers' examples of the shown made items, after the learn examples: the attack items'
        group, then the guard items', each chosen and bounded by ``Services.outcomes_for_writer`` exactly as the learn
        examples are (failures first, seeded order, unknown outcomes never shown), from the cells ``(item, label)``
        of the unit the learn examples come from. [] without shown items."""
        found, out = self.own_items(bench), []
        for group in ([] if found is None else found['shown']):
            rows = [cells[(item['task_id'], label)] for item in group if (item['task_id'], label) in cells]
            if rows:
                out += self.s.outcomes_for_writer(rows, group, bench=bench,
                                                  **({'baseline': baseline} if baseline is not None else {}))
        return out

    def vectors_of(self, bench):
        """Embeddings of the whole practice source of ``bench``, one batch per process (design §5.1); the routing
        views are built once alongside (``views_of``)."""
        if bench not in self.vectors:
            source = self.s.items[bench]
            views = {item['task_id']: self.s.view_fn(bench, item) for item in source}
            texts = [tasktypes.public_text(views[item['task_id']]) for item in source]
            vectors = tasktypes.embed_texts(texts, embedder=self.s.embed)
            self.views[bench] = views
            self.vectors[bench] = {item['task_id']: vector for item, vector in zip(source, vectors)}
        return self.vectors[bench]

    def views_of(self, bench):
        self.vectors_of(bench)
        return self.views[bench]

    def step_label(self):
        """The package step label of the current step (design §5.4: ``typed/<chain>/s<k>``)."""
        return 'typed/%s/s%d' % (self.s.chain, self.state['step'])

    def examples_of(self, bench, count=3):
        """Public practice texts for the describer (exactly three; learn items first, then the source). Under the item
        stage 'planned' (brief P2b) the source part never holds a real gate item or a judging-side item of the step
        (``itemstage.private_ids``): no gate or judging-side item reaches a role call. typed-v3 B7b: no item the
        provider refused in the step either (``refused_ids``); the next texts take their places."""
        seen, texts, views = self.refused_ids(bench), [], self.views_of(bench)
        if self.item_stage != ITEM_STAGE_DEFAULT:
            from . import itemstage
            seen |= set(itemstage.private_ids(self, bench))
        for item in self.items(bench, 'learn') + list(self.s.items[bench]):
            if item['task_id'] not in seen:
                seen.add(item['task_id'])
                texts.append(tasktypes.public_text(views[item['task_id']]))
            if len(texts) == count:
                break
        return texts

    # ---- typed-v3 B7b: refused items never reach a role model --------------------------------------------------------
    def refused_ids(self, bench):
        """The ids of the items of ``bench`` that the provider's content filter refused in the current step (B7: GLM's
        HTTP 400 with code 1301, a final model-side outcome): every solver cell row of a unit of the step
        (``s<k>/<unit>/cells/``: the item stage's diagnose and checks, noise, no-harm, outcomes, card, program, screen,
        learn-round and member units) with a refused send or selection send (``units.cell_refused``). A role request
        carrying such a text may be refused itself (a describer or analyst then pauses, the engineer gets no reply), so
        the role samples that show public text without reading any outcome skip them: the describer's examples
        (``examples_of``), the engineer's hook view (``hook_item``) and a repair request's coverage block
        (``writers.coverage_report``'s ``exclude``); every count and denominator keeps them. The analyst's rows decide
        from the diagnose cells they are built from (``items.plan.learn_rows``). Without a refusal the set is empty and
        every request is typed-v2's / typed-v3's as before.

        WHY read from the step's records, not gathered from the rows this process's ``cells`` returned: a resumed step
        does not re-enter every unit (a sealed ``items.json`` skips diagnose and the checks, a stored typing record
        registers its no-harm arms from disk, a stored program decision whose ``verify_decision`` does not run skips
        its smoke and learn-round units), and a role request rebuilt on resume must be the one the interrupted pass
        built at the same point, else the replay of its saved receipt misses and the call is paid again. The records
        of the step on disk at a role call are the same in both passes (everything the step ran before it). Each cell
        file is parsed once per process (keyed by inode, size and modification time: a re-run cell replaces its
        file)."""
        step_dir, found = self.root / ('s%d' % self.state['step']), set()
        for path in (step_dir.glob('*/cells/*.json') if step_dir.is_dir() else ()):
            stat = path.stat()
            key = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
            cached = self.refusals.get(path)
            if cached is None or cached[0] != key:
                row = units.read_json(path)
                cached = (key, (row.get('bench'), row.get('item_id')) if units.cell_refused(row) else None)
                self.refusals[path] = cached
            if cached[1] is not None and cached[1][0] == bench:
                found.add(cached[1][1])
        return found

    def hook_item(self, bench, learn):
        """The item whose routing view is the engineer's hook view sample: the first of ``learn`` the provider did not
        refuse in this step (``refused_ids``). When it refused every learn item (Codex's second look at B7b): the first
        item of the bench's practice source that is neither refused nor a real gate item of the step nor (under the
        item stage 'planned') a judging-side item (``itemstage.private_ids``), in the source's order; ``learn[0]``
        (typed-v2's sample) only when no such item exists. Without a refused learn item this is ``learn[0]`` as before."""
        refused = self.refused_ids(bench)
        found = next((item for item in learn if item['task_id'] not in refused), None)
        if found is not None:
            return found
        skip = set(refused) | {item['task_id'] for item in self.items(bench, 'gate')}
        if self.item_stage != ITEM_STAGE_DEFAULT:
            from . import itemstage
            skip |= set(itemstage.private_ids(self, bench))
        return next((item for item in self.s.items[bench] if item['task_id'] not in skip), learn[0])

    def load_state(self, k):
        self.library = library_.Library.load(self.root / ('s%d' % k) / 'library.json')
        self.typemap = tasktypes.TypeMap.load(self.root / ('s%d' % k) / 'typemap.json')

    # ---- frozen states and read mounts (DESIGN 3.6; spec/schedule-lock.md S5, S6, S9; read-plan R79) ---------------
    def learned(self, k):
        """Step k (0: the anchor s0) is learned and frozen: its receipt ``s<k>/frozen.json`` exists."""
        return (self.root / ('s%d' % k) / FROZEN).exists()

    def freeze(self, k, bench):
        """The write-once receipt of step k, the last act of its freeze (``finalize``; ``freeze_anchor`` for s0):
        version, chain, step, bench (None for s0) and the record and file hashes of ``s<k>/library.json`` and
        ``s<k>/typemap.json`` as they are on disk, each record verified by its own loader. A receipt is never written
        for a state that a read event has already mounted (its receipt went missing after the read began): that
        pauses ``frozen_state_changed`` instead, so a re-run can never bless changed files."""
        path = self.root / ('s%d' % k) / FROZEN
        if path.exists():
            return units.read_json(path)
        if any(entry.get('step') == k for entry in (self.state.get('read_mounts') or {}).values()):
            raise Paused('frozen_state_changed', 's%d' % k, 'receipt_missing')
        found = _frozen_hashes(self.root / ('s%d' % k))
        require(found is not None, 'The frozen files of s%d are readable and verified' % k)
        record = _sealed({'version': VERSION, 'chain': self.s.chain, 'step': k, 'bench': bench, **found, 'at': _now()})
        units.write_json(path, record)
        return record

    def load_frozen(self, k):
        """Load the frozen state of step k into ``self.library`` / ``self.typemap`` only when it is the state its
        receipt names: the receipt present, with its own hash, version, chain and step; both files' sha256 and their
        loaded records' hashes equal to the receipt's. Any difference (a missing or changed file or receipt) pauses
        ``frozen_state_changed`` before any call; the detail is a fixed code. Returns the receipt."""
        receipt, self.library, self.typemap = frozen_state(self.root, self.s.chain, k)
        return receipt

    def bind_read(self, event, k, receipt):
        """Bind read event ``event`` to the frozen state of step k it mounts (``load_frozen(k)``'s receipt):
        ``state['read_mounts'][event]`` = {step, library_file_sha256, typemap_file_sha256}, set before the event's
        first unit and compared on every re-entry (a difference pauses ``read_mount_changed`` before any call); the
        phase becomes 'read'."""
        entry = {'step': k, 'library_file_sha256': receipt['library_file_sha256'],
                 'typemap_file_sha256': receipt['typemap_file_sha256']}
        mounts = self.state.setdefault('read_mounts', {})
        if event in mounts and mounts[event] != entry:
            raise Paused('read_mount_changed', 'read-' + event, 's%d' % k)
        mounts[event] = entry
        self.state['phase'] = 'read'
        self.persist()
        return entry

    def learning_closed(self):
        """read-plan R79 (schedule 'learn_first' only; under 'interleaved' reading always precedes learning): the
        read phase has begun -- ``state['phase']`` is 'read', the plan pseudo-unit is done, or ``read-plan.json``, a
        sealed plan directory or any read unit directory exists. Learning is then closed for good."""
        if self.state.get('schedule') != 'learn_first':
            return False
        if self.state.get('phase') == 'read' or self.done(readplan.PLAN_UNIT):
            return True
        if any((self.root / name).exists() for name in (readplan.PLAN_FILE, readplan.SEALED_DIR,
                                                         readplan.SMOKE_SEALED_DIR)):
            return True
        return any(path.is_dir() and path.name.startswith(READ_UNIT_PREFIXES) for path in self.root.iterdir())

    # ---- cell units -----------------------------------------------------------------------------------------
    def builder(self, unit, *, arm_of, candidate, typemap, library, vectors, views):
        """``build_cell`` of one unit: the per-item mount from the given type map and library (a gate mounts from
        the step's frozen snapshot, never from a library another candidate just joined), the solve under the
        per-cell memory lock (``Services.heavy(bench, unit)``: the unit names the holder of the shared lock, DESIGN
        3.6), the selection call kept apart. A route-B stop raised by the solve propagates to ``units.run_unit``,
        which stops the unit with its kind. Under the resume replay 'on' (typed-v3 B6 d) both recorders of a cell
        answer from its calls file what an earlier attempt of the cell received (``units.replaying``): a cell whose
        reply was saved before its record was written is completed without a send."""
        s, unit_dir, label = self.s, self.root / unit, self.step_label()
        replay = units.replaying if self.resume_replay == 'on' else (lambda found: found)

        def build(bench, item, arm, tag):
            selector = replay(s.solver_call(bench, unit, tag, purpose='selection'))
            mounted = s.mount_fn(bench, item, arm=arm_of(arm), typemap=typemap, library=library,
                                 vector=vectors.get(item['task_id']), selector=selector, candidate=candidate,
                                 view=views.get(item['task_id']), base_card=self.base_card)
            call = replay(s.solver_call(bench, unit, tag))
            with s.heavy(bench, unit):  # per cell, as main-v10's cells.run_cell holds it (the unit: DESIGN 3.6)
                row = s.solve_fn(bench, item, mounted, call=call, runtime=s.runtime,
                                 worker_factory=s.worker_factory(bench, unit, tag), native=s.native,
                                 nominal_tokens=s.nominal_tokens(bench), unit=unit, tag=tag, scorer_root=unit_dir,
                                 mode=s.mode, step=label, episodes=s.episodes)
            return _with_selection(row, arm, selector)
        return build

    def cells(self, unit, bench, jobs, *, arm_of=gates.arm_of_label, candidate=None, typemap=None, library=None):
        """Run one cell unit of ``bench``; {(item_id, label): cell}. One automatic retry after 60 s on a pure
        infrastructure stop (the infrastructure-unknown cells re-run); any other stop pauses the chain, and so does
        a unit that ended with missing cells (a cell without a record is never dropped from a denominator). The
        unit's containers are drained after it ran, whatever happened. A cell label is a mount arm (a single-run
        cell) or ``<arm>#<r>`` (a gate repeat, DESIGN 3.4); ``arm_of`` (``gates.arm_of_label``) hands the mount
        and the solve the mount arm only, so the label enters the cell tag and never a request. The rerun entries of
        the ledger are this unit's own ``(unit, tag)`` pairs, consumed when their cell has run again.

        Every unit run here is a learning unit and runs at ``LEARN_WIDTHS`` (addendum D15, sealed in the manifest as
        ``learn_widths``); the read units keep ``WIDTHS`` (``reads``). A width enters no request, no cell tag and no
        decision; all arms of a unit run at the same width.

        In records-only mode (``verify_decision``) the unit's stored cells are returned as a complete unit returns
        them (``stored_cells``): nothing is run, marked or drained."""
        if self.verifying is not None:
            return self.stored_cells(unit, jobs)
        self.current(unit)
        unit_dir, vectors, views = self.root / unit, self.vectors_of(bench), self.views_of(bench)
        build = self.builder(unit, arm_of=arm_of, candidate=candidate, typemap=typemap or self.typemap,
                             library=library or self.library, vectors=vectors, views=views)
        meta = {'bench': bench, 'step': self.state['step'], 'chain': self.s.chain, 'mode': self.s.mode}
        for attempt in (1, 2):
            _reopen(unit_dir)
            marked = units.mark_infrastructure_reruns(unit_dir, self.s.ledger, unit=unit)
            try:
                rows, reason = units.run_unit(unit_dir, jobs, unit=unit, widths=LEARN_WIDTHS, build_cell=build,
                                              ledger=self.s.ledger, resume=True, meta=meta)
            except BaseException:
                self.drain(unit, best_effort=True)
                raise
            finally:
                self.s.ledger.consume_reruns(unit, marked)
            self.drain(unit)
            if reason == INFRA_STOP and attempt == 1 and not self.state['infra_retries'].get(unit):
                self.state['infra_retries'][unit] = {'at': _now(), 'seconds': RETRY_SECONDS}
                self.persist()
                self.sleep(RETRY_SECONDS)
                _clear_stop(self.s.ledger)
                continue
            break
        if reason:
            raise Paused(reason, unit)
        expected = sum(len(arms) for _, _, arms in jobs)
        if len(rows) < expected:
            raise Paused('incomplete_unit:missing_cells', unit, '%d of %d cells' % (len(rows), expected))
        self.mark(unit)
        return {(row['item_id'], row['arm']): row for row in rows}

    def drain(self, unit, *, best_effort=False, allow_sealed=False):
        """The unit drain (``Services.drain``; None in fakes): its record goes to ``<unit>/drain.json``; a route-B
        stop it raises (CleanupUnconfirmed, SandboxUnavailable) pauses the chain at this unit unless the drain runs
        while another exception propagates (``best_effort``: recorded, never raised over the original)."""
        if self.s.drain is None:
            return None
        record = {'unit': unit, 'at': _now(), 'result': None, 'error': None}
        try:
            record['result'] = self.s.drain(unit)
        except Exception as error:  # noqa: BLE001 -- recorded; a stop kind pauses the chain below
            record['error'] = _pause_detail(error)
            units.write_json(self.root / unit / 'drain.json', record, allow_sealed=allow_sealed)
            if best_effort:
                return record
            raise Paused(stop_kind(error) or 'exception:' + type(error).__name__, unit, record['error'])
        units.write_json(self.root / unit / 'drain.json', record, allow_sealed=allow_sealed)
        return record

    def consent_first(self):
        """schedule-lock Q2 (kept by read-plan 5.1): under 'learn_first' a real run reads only after all learning,
        so the owner's consent record is checked once at chain start, zero calls, before anything paid. It reads only
        ``shared/consent.json`` (``reads.consent``, rules unchanged); a refusal pauses the chain like a read unit's.
        The per-unit checks of every read unit stay the binding ones."""
        from . import reads
        previous = self.state.get('current_unit')
        self.current('consent')  # a refusal pauses with this unit
        shared = Path(self.s.root) / 'shared'
        # typed-v3 T2: the planned read events (typed-v2's seven keep the one-argument call)
        found = (reads.consent(shared) if self.anchor_events == readplan.READ_ANCHORS_DEFAULT
                 else reads.consent(shared, arms=self.read_events))
        self.current(previous)
        return found

    # ---- the first call -------------------------------------------------------------------------------------
    def confirm(self):
        """One solver call on the fixture prompt before anything paid (route B's first-call rule); the record keeps
        counts and hashes, never the reply."""
        path = self.root / CONFIRM
        if path.exists():
            return units.read_json(path)
        unit, bench = 'confirm', self.s.order[0]
        self.current(unit)
        call, started, receipt, error = self.s.solver_call(bench, unit, 'first-call'), time.time(), {}, None
        try:
            receipt = call(FIRST_CALL_SYSTEM, FIRST_CALL_USER)
        except Exception as failure:  # noqa: BLE001 -- any failure is an unconfirmed first call
            error = type(failure).__name__
        receipt = receipt if isinstance(receipt, dict) else {}
        charged = ((self.s.ledger.state.get('by_unit') or {}).get(unit) or {}).get('charged', 0)
        checks = _first_call_checks(self.s.chain, receipt, charged, _echo_models(self.s.manifest, self.s.chain))
        passed = error is None and all(ok is not False for ok in checks.values())
        fields = {'version': VERSION, 'chain': self.s.chain, 'bench': bench, 'mode': self.s.mode, 'checks': checks,
                  'passed': passed, 'error': error, 'seconds': round(time.time() - started, 1),
                  'request_sha256': call.sends[0]['request_sha256'] if call.sends else None,
                  'returned_model': receipt.get('returned_model'), 'finish_reason': receipt.get('finish_reason'),
                  'error_type': receipt.get('error_type'), 'usage': receipt.get('usage'), 'tokens': call.tokens(),
                  'charged': charged, 'reasoning_chars': receipt.get('reasoning_chars'), 'at': _now()}
        if passed:
            units.write_json(path, fields)
            self.mark(unit)
            return fields
        n = 1 + len(list(self.root.glob('confirm-failed-*.json')))
        units.write_json(self.root / ('confirm-failed-%d.json' % n), fields)
        failed = [name for name, ok in checks.items() if ok is False]
        raise Paused('first_call_unconfirmed', unit, error or ', '.join(failed) or str(receipt.get('error_type')))

    # ---- reads ----------------------------------------------------------------------------------------------
    def read_one(self, event, bench):
        """One panel read (``reads.read_panel`` in its services form: it holds the memory lock per cell and drains
        its own unit)."""
        read = self.s.read_panel
        if read is None:
            from . import reads
            read = reads.read_panel
        return read(self.s.root, self.s.chain, event, bench, library=self.library, typemap=self.typemap,
                    services=self.s)

    def read_event(self, event, pending):
        """The pending panels of the event side by side (a pool of five units; each unit's inner width is the read
        width ``WIDTHS``, never the learning width).
        An interrupt or an exception in one unit stops the ledger, so the other units wind down at their next cell
        boundary instead of reading on for hours; the pool then joins them and the signal propagates."""
        with ThreadPoolExecutor(max_workers=READ_WORKERS, thread_name_prefix='typed-read') as pool:
            futures = {bench: pool.submit(self.read_one, event, bench) for bench in pending}
            try:
                return {bench: future.result() for bench, future in futures.items()}
            except BaseException as error:
                self.s.ledger.stop('interrupted' if not isinstance(error, Exception)
                                   else 'read_unit_exception:' + type(error).__name__)
                raise

    def reads(self, event, benches=None):
        """Read every pending panel of the event (``benches``: only these, read-plan R37; None: all). A read is done
        only when its mirror is complete (every expected cell, no stop): a stop or missing cells pause the chain (the
        owner's recovery reopens the unit through ``units.reopen_stopped`` and completes it), after one automatic
        retry when every incomplete read stopped on the pure infrastructure streak."""
        wanted = [b for b in self.s.order if (benches is None or b in benches)
                  and not self.done('read-%s-%s' % (event, b))]
        if not wanted:
            return
        self.current('read-' + event)
        pending, key = list(wanted), 'read-' + event
        for attempt in (1, 2):
            results = self.read_event(event, pending)
            for bench, status in results.items():
                self.state['reads'].setdefault(event, {})[bench] = _counts_only(status if isinstance(status, dict) else {})
            self.persist()
            incomplete = {b: s for b, s in results.items() if not _read_complete(s)}
            if not incomplete and not self.s.ledger.stopped():
                break
            reasons = {str(s.get('stop_reason')) for s in incomplete.values() if isinstance(s, dict) and s.get('stop_reason')}
            if self.s.ledger.stopped():
                reasons.add(str(self.s.ledger.state.get('stop_reason')))
            if attempt == 1 and reasons == {INFRA_STOP} and not self.state['infra_retries'].get(key):
                self.state['infra_retries'][key] = {'at': _now(), 'seconds': RETRY_SECONDS, 'benches': sorted(incomplete)}
                self.persist()
                self.sleep(RETRY_SECONDS)
                _clear_stop(self.s.ledger)
                pending = [b for b in pending if b in incomplete]
                continue
            reason = sorted(reasons)[0] if reasons else 'incomplete_read:missing_cells'
            named = reason.rsplit(':', 1)[-1]  # a first-cell stop names its bench
            bench = named if named in pending else next(iter(incomplete), pending[0])
            raise Paused(reason, 'read-%s-%s' % (event, bench))
        for bench in wanted:
            self.mark('read-%s-%s' % (event, bench))

    def freeze_anchor(self):
        """Step 0's state: the empty library and type map frozen as s0 with their receipt (both schedules, before any
        read). Once learning is closed (R79) nothing is written: the s0 state must be the receipted one, else the
        chain pauses ``frozen_state_changed``."""
        if self.learning_closed():
            self.load_frozen(0)
            return
        s0 = self.root / 's0'
        if not (s0 / 'library.json').exists():
            library_.Library().save(s0 / 'library.json', step=0)
        if not (s0 / 'typemap.json').exists():
            tasktypes.TypeMap().freeze(s0 / 'typemap.json', step=0)
        self.freeze(0, None)

    def read_anchors(self):
        """The anchor events C0 and C on the five panels, both from the frozen s0 state, then ``step-0``; a done
        ``step-0`` only reloads s0 (as typed-v1's resume skips a finished step). typed-v3 (T2): the manifest's sealed
        anchors (``self.anchor_events``); with ('C',) the event C0 is never bound, read or marked."""
        if self.done('step-0'):
            self.load_state(0)
            return
        receipt = self.load_frozen(0)
        for event in self.anchor_events:
            self.bind_read(event, 0, receipt)
            self.reads(event)
        self.mark('step-0')

    # ---- the economy read plan (addenda D9, D10, RP1 to RP13; spec/read-plan.md) ---------------------------------
    def rp(self):
        return self.state['read_plan']

    def write_solver_settings(self):
        """R75 (RP2): at every start and resume, before ``confirm``, whatever the schedule and read plan: the
        credential-free record of the solver block this process runs with, written once to
        ``<chain>/solver-settings.json``; its bytes' sha256 is bound in ``state['solver_settings_sha256']``. A record
        that is not byte-equal to the stored one (a resume with changed settings) pauses ``solver_settings_changed``
        before any call (Q22)."""
        record = readplan.solver_settings_record(self.s.chain, solver_settings_rows(self.s))
        try:
            digest = readplan.write_once(self.root / readplan.SOLVER_SETTINGS_FILE, record)
        except readplan.WriteOnceMismatch:
            raise Paused('solver_settings_changed', 'solver-settings', 'record_changed') from None
        bound = self.state.get('solver_settings_sha256')
        if bound is not None and bound != digest:
            raise Paused('solver_settings_changed', 'solver-settings', 'binding_changed')
        self.state['solver_settings_sha256'] = digest
        self.persist()
        return digest

    def plan_header(self):
        """The values the plan header binds besides the frozen receipts and the panels (3.2, R32 c); the solver
        settings hash is the bound one, which is the stored file's (``write_solver_settings``)."""
        header = replay_header(self.s, self.root)
        require(header['solver_settings_sha256'] == self.state.get('solver_settings_sha256'),
                'The solver settings file is the bound one')
        return header

    def plan(self):
        """The planning pass (pseudo-unit ``read-plan``; R20 to R34). Skipped once ``read-plan`` is done (bound, or
        void). R20: phase 'read', current unit ``read-plan`` and the seven ``read_mounts`` from the frozen receipts,
        persisted before anything is opened; R21: consent first on a real root; then ``readplan.run_pass`` (zero
        calls). Its result is bound (``plan_sha256``, ``file_sha256``, ``bound_at``) and ``read-plan`` marked in one
        persist. The pass's own detections pause ``read_plan_failed`` (``pass_failed``); stops, pauses and every
        exception of the panel path propagate unchanged (R33 a)."""
        if self.done(readplan.PLAN_UNIT):
            return
        self.state['phase'], self.state['current_unit'] = 'read', readplan.PLAN_UNIT
        receipts = {k: self.load_frozen(k) for k in range(len(self.s.order) + 1)}
        for event in readplan.EVENTS:
            k = readplan.step_of(event)
            self.bind_read(event, k, receipts[k])
        smoke = self.s.mode == 'smoke'
        if not smoke:
            from . import reads
            reads.consent(Path(self.s.root) / 'shared')
        try:
            plan, digest = readplan.run_pass(self.s, self.s.root, self.s.chain, smoke=smoke, header=self.plan_header(),
                                             load=lambda k: frozen_state(self.root, self.s.chain, k))
        except readplan.ReadPlanError as error:
            self.pass_failed(error.code)
            return
        self.rp().update(plan_sha256=plan['plan_sha256'], file_sha256=digest, bound_at=_now(),
                         counts=dict(plan['counts']))
        self.bound_here = True
        self.mark(readplan.PLAN_UNIT)

    def pass_failed(self, code):
        """RP11, R33 d, Q24: the pass's own detected inconsistency. The first occurrence of a code pauses
        ``read_plan_failed`` (its recovery re-runs the pass); a second one with the same code voids the plan
        (``pass_failed``): ``read-plan`` is marked and every pair is read fresh in the economy order."""
        code = code if code in readplan.PASS_FAILURE_CODES else 'pass_exception'
        failures = self.rp()['failures']
        seen = code in failures
        failures.append(code)
        if not seen:
            self.persist()
            raise Paused('read_plan_failed', readplan.PLAN_UNIT, code)
        self.void_plan('pass_failed')
        self.mark(readplan.PLAN_UNIT)

    def void_plan(self, reason):
        """R44 e, R33 d: the plan is void; EVERY alias of the chain, settled or not, becomes ``void_alias`` (its record
        archived, its marker removed) and is read fresh in the sweeps; the representatives' fresh units stay."""
        rp = self.rp()
        rp['void'], rp['void_reason'] = True, reason
        for event, benches in list(self.state['reads'].items()):
            for bench, entry in list(benches.items()):
                if isinstance(entry, dict) and entry.get('kind') == 'alias':
                    self.unsettle(event, bench, kind='void_alias')
        self.persist()

    def unsettle(self, event, bench, *, kind):
        """An alias pair back to unsettled (``kind`` None: its entry removed) or to ``void_alias``: its record moved to
        ``read-alias/archived/<event>-<bench>-<n>.json`` (kept), its ``alias-`` marker removed (R42, R44 b, e)."""
        path = readplan.alias_path(self.s.root, self.s.chain, event, bench)
        if path.exists():
            n = 1
            while readplan.archived_alias_path(self.s.root, self.s.chain, event, bench, n).exists():
                n += 1
            target = readplan.archived_alias_path(self.s.root, self.s.chain, event, bench, n)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
        marker = 'alias-%s-%s' % (event, bench)
        if marker in self.state['done_units']:
            self.state['done_units'].remove(marker)
        entries = self.state['reads'].setdefault(event, {})
        if kind is None:
            entries.pop(bench, None)
        else:
            entries[bench] = {'kind': kind, 'status': kind}

    def replay_plan(self):
        """R76: right after the binding and before any read unit or alias, the zero-call replay of the bound plan in
        a fresh process (``services.replay``; in process when None) with a ``PYTHONHASHSEED`` other than this
        process's; ``equal`` is recorded with its time and seed and the chain goes on. ``different`` or an error
        pauses ``read_plan_changed`` (``replay_different`` / ``replay_error:<code>``). ``different`` once more voids
        the plan (R44 c: ``replay_different``). A replay error voids it (R44 d: ``replay_error``) only when the previous
        recovery outcome was a replay error with the same code, i.e. the pause the last applied recovery resolved
        carried this very detail; an older error that a later replay resolved is no first strike (fix-c, rc-plan-1)."""
        rp = self.rp()
        if rp['void'] or not rp.get('plan_sha256') or (rp.get('replay') or {}).get('verdict') == 'equal':
            return
        seed = readplan.hash_seed(os.environ)
        self.current(readplan.PLAN_UNIT)
        if self.s.replay is not None:
            found = self.s.replay(self.s.root, self.s.chain, environ={**os.environ, 'PYTHONHASHSEED': str(seed)})
        else:
            found = in_process_replay(self.s, self.root)
        verdict = found.get('verdict') if isinstance(found, dict) else None
        reason, n = self.last_recovery_reason()
        pending = reason == 'read_plan_changed' and not any(
            r.get('n') == n and r.get('outcome') in ('replay_equal', 'plan_void', 'paused_again') for r in rp['recoveries'])
        if verdict == 'equal':
            rp['replay'] = {'verdict': 'equal', 'at': _now(), 'hash_seed': seed}
            if pending:
                rp['recoveries'].append({'n': n, 'outcome': 'replay_equal'})
            self.persist()
            return
        if verdict == 'different':
            detail, void = 'replay_different', 'replay_different'
            seen = detail in rp['failures']
        else:
            code = found.get('code') if isinstance(found, dict) else None
            ok = isinstance(code, str) and (code in readplan.READ_PLAN_REASONS or readplan.EXIT_CODE.fullmatch(code))
            detail, void = readplan.replay_error_detail(code if ok else 'replay_exception'), 'replay_error'
            seen = pending and self.last_recovery_detail() == detail  # R44 d: the previous recovery outcome
        rp['failures'].append(detail)
        rp['replay'] = {'verdict': 'different' if verdict == 'different' else 'error', 'at': _now(), 'hash_seed': seed}
        if pending:
            rp['recoveries'].append({'n': n, 'outcome': 'plan_void' if seen else 'paused_again'})
        if seen:
            self.void_plan(void)
            return
        self.persist()
        raise Paused('read_plan_changed', readplan.PLAN_UNIT, detail)

    def last_recovery_reason(self):
        recoveries = self.state.get('recoveries') or []
        paused = (recoveries[-1].get('paused') or {}) if recoveries else {}
        return paused.get('reason'), (recoveries[-1].get('n') if recoveries else None)

    def last_recovery_detail(self):
        """The detail of the pause the last applied recovery resolved (None without one)."""
        recoveries = self.state.get('recoveries') or []
        return (recoveries[-1].get('paused') or {}).get('detail') if recoveries else None

    def verify_read_plan(self):
        """R44 at every start and resume with a bound plan (economy, not void), before the pass, the replay or
        ``read_classes``. (a) The plan file's bytes, self-hash and bound hashes, every sealed file's bound hash, the
        manifest hash; the seven frozen receipts and the solver settings keep their own reasons
        (``frozen_state_changed``, ``solver_settings_changed``). A difference pauses ``read_plan_changed`` -- unless
        the last applied recovery was for ``read_plan_changed`` (b): then the failed plan-owned files are archived
        (never receipts, step files, settings or the manifest), and (c) a failed sealed file voids the plan
        (``sealed_file_invalid``), a failed plan file is recomputed in process from the stored inputs and restored
        when its bytes hash to the bound file hash (else void ``replay_different``); the replay then runs again as
        the check. Every outcome is listed in ``state['read_plan']['recoveries']``."""
        rp = self.rp()
        if rp['mode'] != 'economy' or rp['void'] or not rp.get('plan_sha256'):
            return
        reason, n = self.last_recovery_reason()
        recovering = reason in ('read_plan_changed', 'read_alias_invalid') and not any(
            r.get('n') == n for r in rp['recoveries'])
        root, chain, smoke = self.s.root, self.s.chain, self.s.mode == 'smoke'
        failed, plan = [], None
        try:
            plan = readplan.load_plan(readplan.plan_path(root, chain), file_sha256=rp['file_sha256'],
                                      plan_sha256=rp['plan_sha256'])
        except (readplan.ReadPlanError, OSError):
            failed.append(readplan.PLAN_FILE)
        if plan is not None:
            for k in range(len(self.s.order) + 1):
                receipt = frozen_state(self.root, chain, k)[0]
                for event in readplan.EVENTS:
                    if readplan.step_of(event) == k and plan['frozen'][event] != readplan.frozen_entry(receipt):
                        raise Paused('frozen_state_changed', 's%d' % k, 'plan_receipt')
            if plan['solver_settings_sha256'] != self.state.get('solver_settings_sha256'):
                raise Paused('solver_settings_changed', 'solver-settings', 'plan_binding')
            if plan['manifest_record_sha256'] != readplan.manifest_sha256(self.s.manifest):
                failed.append('manifest')
            for bench in readplan.ORDER:
                for kind, path, key in (('inputs', readplan.inputs_path(root, chain, bench, smoke=smoke), 'inputs_sha256'),
                                        ('identities', readplan.identities_path(root, chain, bench, smoke=smoke),
                                         'identities_sha256')):
                    try:
                        readplan.sealed_from_bytes(readplan.read_bytes(path, allow_sealed=True), kind,
                                                   file_sha256=plan['benches'][bench][key])
                    except (readplan.ReadPlanError, OSError):
                        failed.append(path.name)
        if not failed:
            return
        code = 'plan_file_mismatch' if readplan.PLAN_FILE in failed else 'sealed_file_mismatch'
        if 'manifest' in failed or not recovering:
            raise Paused('read_plan_changed', readplan.PLAN_UNIT, code)
        directory = readplan.sealed_dir(root, chain, smoke=smoke)
        for name in failed:  # (b) archive (rename, keep) only the plan-owned files that failed
            path = (directory / name) if name != readplan.PLAN_FILE else readplan.plan_path(root, chain)
            target = path.with_name(path.name + '.archived-%d' % n)
            if units.checked_path(path, allow_sealed=True).exists():
                os.replace(path, target)
        if any(name != readplan.PLAN_FILE for name in failed):
            rp['recoveries'].append({'n': n, 'outcome': 'plan_void'})
            self.void_plan('sealed_file_invalid')
            return
        files = in_process_replay(self.s, self.root, files_only=True)
        found = None if files is None else files.get(readplan.PLAN_FILE)
        if found is not None and readplan.file_sha256(found) == rp['file_sha256']:
            readplan.write_once(readplan.plan_path(root, chain), found)
            rp['replay'] = None  # (c) the child replay runs again as the check
            rp['recoveries'].append({'n': n, 'outcome': 'plan_restored'})
            self.persist()
            return
        rp['recoveries'].append({'n': n, 'outcome': 'plan_void'})
        self.void_plan('replay_different')

    def recover_aliases(self):
        """R44 b for ``read_alias_invalid``: after that recovery, every alias record that fails its verification is
        archived and its pair returns to unsettled in one persisted step; ``read_classes`` settles it again (P6)."""
        rp = self.rp()
        reason, n = self.last_recovery_reason()
        if reason != 'read_alias_invalid' or any(r.get('n') == n for r in rp['recoveries']) or rp['void']:
            return
        plan = self.bound_plan()
        for event, bench in readplan.alias_pairs(plan):
            entry = (self.state['reads'].get(event) or {}).get(bench)
            if isinstance(entry, dict) and entry.get('kind') == 'alias' and not self.alias_valid(plan, event, bench):
                self.unsettle(event, bench, kind=None)
        rp['recoveries'].append({'n': n, 'outcome': 'alias_unsettled'})
        self.persist()

    def bound_plan(self):
        """The bound plan, loaded and verified against its bound hashes (None when void or unbound)."""
        rp = self.rp()
        if rp['void'] or not rp.get('plan_sha256'):
            return None
        try:
            return readplan.load_plan(readplan.plan_path(self.s.root, self.s.chain), file_sha256=rp['file_sha256'],
                                      plan_sha256=rp['plan_sha256'])
        except (readplan.ReadPlanError, OSError):
            raise Paused('read_plan_changed', readplan.PLAN_UNIT, 'plan_file_mismatch') from None

    def mirror_of(self, event, bench):
        from . import reads
        path = reads.status_path(self.s.root, self.s.chain, event, bench)
        return units.read_json(path) if path.exists() else None

    def alias_valid(self, plan, event, bench):
        """R44 a: the stored alias record verifies against the plan and the representative's current mirror."""
        representative = readplan.class_of(plan, event, bench)['representative']
        mirror = self.mirror_of(representative, bench) or {}
        try:
            readplan.load_alias(readplan.alias_path(self.s.root, self.s.chain, event, bench), plan,
                                representative_aggregate_sha256=mirror.get('aggregate_sha256'),
                                representative_counts={k: mirror.get(k) for k in readplan.COUNT_KEYS})
            return True
        except (readplan.ReadPlanError, OSError):
            return False

    def settled(self, event, bench):
        if self.done('read-%s-%s' % (event, bench)):
            return True
        entry = (self.state['reads'].get(event) or {}).get(bench)
        return isinstance(entry, dict) and entry.get('kind') == 'alias' and self.done('alias-%s-%s' % (event, bench))

    def fresh_wanted(self, plan, event, bench, sweep):
        """R36: in the first sweep the representatives of unsettled classes (every pair its own class when the plan is
        void or the bench's aliases were voided, R42); in the final sweep every pair still unsettled."""
        if self.settled(event, bench):
            return False
        if plan is None or sweep == 'final' or bench in self.rp()['fallbacks']:
            return True
        entry = (self.state['reads'].get(event) or {}).get(bench)
        if isinstance(entry, dict) and entry.get('kind') == 'void_alias':
            return True
        return readplan.class_of(plan, event, bench)['representative'] == event

    def read_classes(self):
        """R35 to R39, R42, R46 under 'economy': the first sweep S5 .. C0 reads, per event, the benches where the
        event represents an unsettled class (each event bound to its frozen state first: ``load_frozen``,
        ``bind_read``; the unchanged ``reads`` with its bench list) and settles the classes it represents; the final
        sweep reads every pair still unsettled as its own class. Each pair is read fresh at most once. Then the
        completeness check by kind (R46) and the markers ``step-0`` .. ``step-5``."""
        plan = self.bound_plan()
        readplan.remove_part_files(Path(self.s.root) / self.s.chain / readplan.ALIAS_DIR)
        for sweep in ('first', 'final'):
            for event in reversed(readplan.EVENTS):
                wanted = [b for b in self.s.order if self.fresh_wanted(plan, event, b, sweep)]
                if wanted:
                    k = readplan.step_of(event)
                    self.bind_read(event, k, self.load_frozen(k))
                    self.reads(event, benches=wanted)
                if plan is not None and not self.rp()['void']:
                    for bench in self.s.order:
                        self.settle(plan, event, bench)
            plan = None if self.rp()['void'] else plan
        self.complete_reads(plan)
        for marker in STEP_MARKERS[:len(self.s.order) + 1]:
            self.mark(marker)

    def settle(self, plan, event, bench):
        """R39: after the representative's unit of (event, bench) is complete, its post-read check (R41); passed:
        each unsettled member's ``read_mounts`` entry checked against the plan's frozen entry (else
        ``read_mount_changed``, nothing written), then its write-once alias record, state entry and marker in one
        persist; failed: R42."""
        if bench in self.rp()['fallbacks'] or readplan.class_of(plan, event, bench)['representative'] != event:
            return
        members = [m for m in readplan.members_of(plan, bench, event) if not self.settled(m, bench)]
        if not self.done('read-%s-%s' % (event, bench)):
            return
        if plan['benches'][bench]['events'][event]['status'] == 'fallback':
            return  # a fallback class has no planned identity to check against and no member to settle
        # every other completed representative is checked, a singleton class too (Codex review round 3): a mismatch
        # of any class voids every alias of its bench (RP10), even when this representative has nothing to settle
        self.load_frozen(readplan.step_of(event))
        try:
            check = readplan.check_representative(self.s.root, self.s.chain, plan, event, bench,
                                                  smoke=self.s.mode == 'smoke', library=self.library)
        except readplan.ReadPlanError as error:
            raise Paused('read_plan_changed', 'read-%s-%s' % (event, bench), error.code) from None
        if not readplan.check_passed(check, plan['benches'][bench]['items']):
            self.void_bench(bench, event, check)
            return
        if not members:
            return
        mirror = self.mirror_of(event, bench) or {}
        for member in members:
            entry = (self.state.get('read_mounts') or {}).get(member)
            if not isinstance(entry, dict) or not readplan.frozen_entry_matches(plan, member, **entry):
                raise Paused('read_mount_changed', 'alias-%s-%s' % (member, bench), 's%d' % readplan.step_of(member))
            record = readplan.build_alias(plan, member, bench, check=check,
                                          representative_aggregate_sha256=mirror.get('aggregate_sha256'),
                                          representative_counts={k: mirror.get(k) for k in readplan.COUNT_KEYS})
            try:
                readplan.write_once(readplan.alias_path(self.s.root, self.s.chain, member, bench), record)
            except readplan.WriteOnceMismatch:
                raise Paused('read_alias_invalid', 'alias-%s-%s' % (member, bench), 'record_differs') from None
            self.state['reads'].setdefault(member, {})[bench] = readplan.alias_state_entry(record)
            self.mark('alias-%s-%s' % (member, bench))

    def void_bench(self, bench, event, check):
        """R42 (RP10): a failed post-read check voids EVERY alias of the bench, settled or not, without a pause;
        every unsettled pair of the bench is then its own class and read fresh (bounded by the full plan); recorded as
        a defect signal. One persisted step."""
        for member, entries in list(self.state['reads'].items()):
            entry = entries.get(bench)
            if isinstance(entry, dict) and entry.get('kind') == 'alias':
                self.unsettle(member, bench, kind='void_alias')
        self.rp()['fallbacks'][bench] = {'event': event, 'reason': 'post_read_mismatch', 'unequal': check['unequal']}
        self.persist()

    def fresh_complete(self, event, bench, plan):
        """R46, fresh kind: the marker, a complete mirror without a stop, and the sealed ``done.json`` with every
        expected cell (equal to the plan's item count when a plan is bound)."""
        from . import reads
        mirror = self.mirror_of(event, bench)
        if not self.done('read-%s-%s' % (event, bench)) or not isinstance(mirror, dict) \
                or mirror.get('status') != 'complete' or mirror.get('stop_reason') is not None:
            return False
        path = reads.unit_dir(self.s.root, self.s.chain, event, bench, smoke=self.s.mode == 'smoke') / 'done.json'
        try:
            done = units.read_json(path, allow_sealed=True)
        except (OSError, ValueError):
            return False
        items = None if plan is None else plan['benches'][bench]['items']
        return done.get('cells') == done.get('expected_cells') and (items is None or done.get('expected_cells') == items)

    def complete_reads(self, plan):
        """R46: every one of the 35 pairs settled by kind before the chain completes, else ``read_plan_incomplete``.
        Alias: its marker, a state entry of kind alias, a record that verifies (R44) and a fresh representative."""
        for event in readplan.EVENTS:
            for bench in self.s.order:
                if self.done('read-%s-%s' % (event, bench)):
                    ok = self.fresh_complete(event, bench, plan)
                elif plan is not None and self.settled(event, bench):
                    representative = readplan.class_of(plan, event, bench)['representative']
                    if not self.alias_valid(plan, event, bench):
                        raise Paused('read_alias_invalid', 'alias-%s-%s' % (event, bench), 'record_invalid')
                    ok = self.fresh_complete(representative, bench, plan)
                else:
                    ok = False
                if not ok:
                    raise Paused('read_plan_incomplete', 'read-%s-%s' % (event, bench))

    # ---- gate arms (DESIGN 3.4 and 4.1, D5; addendum D17: B in place of C0 on the learning side) ----------------
    def repeats(self):
        """R, the fresh runs per item and arm of every gate unit (``limits['gate_repeats']``; R >= 2: the variance of
        the baseline's repeats needs two)."""
        found = self.s.limits.get('gate_repeats')
        require(type(found) is int and found >= 2, 'A gate needs gate_repeats >= 2 runs per item and arm')
        return found

    def identities(self, bench, arm, *, candidate=None, typemap=None, library=None):
        """[(item_id, identity)] of every gate item under ``arm``: ``Services.identity_fn`` (``mount.mount_identity``
        with the manifest's base card, the same view and vector as the mount), zero calls of any kind."""
        require(self.s.identity_fn is not None, 'A gate needs the mount identity function (Services.identity_fn)')
        vectors, views = self.vectors_of(bench), self.views_of(bench)
        typemap, library = typemap or self.typemap, library or self.library
        return [(item['task_id'], self.s.identity_fn(bench, item, arm=arm, typemap=typemap, library=library,
                                                     vector=vectors.get(item['task_id']), candidate=candidate,
                                                     view=views.get(item['task_id']), base_card=self.base_card))
                for item in self.gate_items(bench)]

    def gate_arm(self, unit, bench, arm, *, candidate=None, typemap=None, library=None, extra_jobs=()):
        """One gate arm P of the step (DESIGN 3.4 "Shared arms" and "Cells"); returns its entry (registered in
        ``self.gate_arms``, the step's arms in run order).

        P's identity on every gate item is computed with no call. P is the same arm as an arm Q already run in this
        step iff the identities are equal on EVERY gate item; Q is the first such arm in run order (``B@noise``,
        ``F@noharm-<T>``, ``F@outcomes``, ``cand_card@card-r<j>``, ``F@outcomes-card``,
        ``cand_program@program-<i>-gate``); arms are compared within one bench only, so a shared type's member arms
        (addendum D16) meet only the member bench's earlier arms of the step (``member-<b'>-base``,
        ``card-r<j>-member-<b'>``, ``member-<b'>-outcomes-card``, ``program-<i>-member-<b'>``). The sharing decision is
        written once, before any cell, as
        ``<unit>/plan.json`` (unit, arm, labels, repeats, items, per-item identity digests and their sha256,
        ``shared_from``, the comparison with every earlier arm); a resumed unit recomputes it and must find the same
        plan (else ``gate_plan_changed``). A shared P runs no gate cell and uses Q's R runs, after checking that each
        of Q's rows recorded P's system card (else ``shared_arm_mismatch``). Otherwise R fresh cells per gate item,
        labelled ``<arm>#<r>``, run in this unit together with ``extra_jobs`` (the unit's single-run learn cells).

        Decidable only with all n * R runs present and none an infrastructure or configuration unknown after the
        unit's attempts: a missing run pauses ``incomplete_unit:missing_cells``, an unknown one archives the done
        marker and pauses ``gate_cells_unknown`` (the recovery re-runs exactly those cells, archived under
        ``rerun/``); nothing is decided and no item is excluded. A model-side unknown run is final: scored 0, never
        re-run, counted in ``unknown_final`` (addendum O1)."""
        for q in self.gate_arms:
            if q['unit'] == unit:
                return q
        k, R, gate = self.state['step'], self.repeats(), self.gate_items(bench)
        ids = [item['task_id'] for item in gate]
        raw = self.identities(bench, arm, candidate=candidate, typemap=typemap, library=library)
        digests = [[item_id, _digest(identity)] for item_id, identity in raw]
        earlier = [q for q in self.gate_arms if q['bench'] == bench and q['unit'] != unit]
        source = next((q for q in earlier if q['identities'] == digests), None)
        plan = {'unit': unit, 'bench': bench, 'step': k, 'arm': arm, 'labels': list(gates.repeat_labels(arm, R)),
                'repeats': R, 'items': ids, 'identities': digests, 'identity_sha256': _digest(digests),
                'shared_from': None if source is None else {'unit': source['unit'], 'arm': source['arm']},
                'compared': [{'unit': q['unit'], 'arm': q['arm'], 'equal': q['identities'] == digests,
                              'differing_items': sum(a != b for a, b in zip(q['identities'], digests))}
                             for q in earlier]}
        if self.own_items(bench) is not None:  # typed-v3 (brief P2b): the sealed item list J was read from
            plan['items_sha256'] = self.own_items(bench)['record']['record_sha256']
        path = self.root / unit / PLAN
        if path.exists():
            if units.read_json(path) != plan:
                raise Paused('gate_plan_changed', unit, 'the recomputed sharing plan differs from plan.json')
        else:
            self.require_records(unit + '/' + PLAN)  # records-only mode: a gate that never ran is not run here
            units.write_json(path, plan)
        if source is not None:
            for item_id, identity in raw:
                for label in source['labels']:
                    mounted = (source['cells'].get((item_id, label)) or {}).get('mount') or {}
                    if mounted.get('system_card_sha256') != identity.get('system_card_sha256'):
                        raise Paused('shared_arm_mismatch', unit, 'shared from %s' % source['unit'])
            own = self.cells(unit, bench, list(extra_jobs), candidate=candidate, typemap=typemap,
                             library=library) if extra_jobs else {}
            if not extra_jobs:
                self.mark(unit)  # a shared gate unit runs no cell: its plan.json is its whole record
            entry = _gate_entry(plan, own, source=source)
        else:
            own = self.cells(unit, bench, [(bench, item, tuple(plan['labels'])) for item in gate] + list(extra_jobs),
                             candidate=candidate, typemap=typemap, library=library)
            entry = _gate_entry(plan, own, runs=self.arm_runs(unit, own, plan), reruns=self.reruns(unit, bench, plan))
        self.gate_arms.append(entry)
        return entry

    def arm_runs(self, unit, cells, plan):
        """``gates.arm_runs`` of a fresh arm; an undecidable arm pauses (DESIGN 3.4 "Cells"). In records-only mode
        (``verify_decision``) the stored decision being checked cannot have come from such runs: nothing is archived."""
        try:
            return gates.arm_runs(cells, plan['items'], plan['arm'], plan['repeats'])
        except gates.UndecidableRuns as error:
            self.require_records(unit + '/cells')
            units.archive_done(self.root / unit)  # the recovery re-enters the unit and re-runs exactly those cells
            if error.missing:
                raise Paused('incomplete_unit:missing_cells', unit, '%d of %d runs' % (error.expected - error.missing,
                                                                                      error.expected))
            raise Paused('gate_cells_unknown', unit, '%d of %d runs infrastructure or configuration unknown'
                         % (error.infrastructure, error.expected))

    def reruns(self, unit, bench, plan):
        """The re-run cells of one fresh arm: archived earlier attempts (``rerun/<tag>-<n>.json``) and interrupted
        calls the ledger recovered for this unit's cells of the arm (each one more request for that item and arm)."""
        tags = {units.cell_tag(bench, item_id, label) for item_id in plan['items'] for label in plan['labels']}
        recovered = sum(1 for row in self.s.ledger.state.get('recovered') or []
                        if row.get('unit') == unit and row.get('cell') in tags)
        return units.reruns_of(self.root / unit, tags) + recovered

    def registered(self, unit):
        found = [q for q in self.gate_arms if q['unit'] == unit]
        require(len(found) == 1, 'The gate arm of %s ran in this step' % unit)
        return found[0]

    def register_stored(self, unit):
        """Register again the gate arm of a unit whose phase record is stored (a resumed step reloads typing,
        card and program records without calling their gates, and a later arm must see the same earlier arms when
        its plan is recomputed): its write-once ``plan.json`` and the runs it holds or shares."""
        for q in self.gate_arms:
            if q['unit'] == unit:
                return q
        plan = units.read_json(self.root / unit / PLAN)
        if plan['shared_from'] is not None:
            entry = _gate_entry(plan, {}, source=self.registered(plan['shared_from']['unit']))
        else:
            rows = [units.read_json(path) for path in sorted((self.root / unit / 'cells').glob('*.json'))]
            own = {(row['item_id'], row['arm']): row for row in rows}
            entry = _gate_entry(plan, own, runs=self.arm_runs(unit, own, plan),
                                reruns=self.reruns(unit, plan['bench'], plan))
        self.gate_arms.append(entry)
        return entry

    def compare(self, kind, baseline, candidate, *, fired_cells=None):
        """One decision of DESIGN 3.4 on the item sums of R runs per arm (``gates``): ``kind`` 'card', 'no_harm',
        'program' (``fired_cells``: {item: number of its R candidate cells where the program fired}, O6) or 'member'
        (addendum D16 b: no_regress on a member bench's gate slice). tau comes from the baseline arm's own repeats.
        The record adds where the runs of both arms are (``baseline``, ``candidate_arm``: unit, arm, shared_from),
        ``baseline_selected`` (the baseline's runs are an accepted card round's, selected for being high: addendum
        O5), the re-runs per arm, the items and the cells this unit ran for the candidate (0 for a shared arm).

        typed-v3 T7 (brief P3b): under the sealed gate rule 'evolution' a card of a step with made items is decided by
        ``gates.card_decision_evolution`` on E = R + A of the step's sealed item list (``evolution_items``: the head of
        J), tau_E from the baseline's repeats on E, no_regress on J; the record is the card record plus its
        ``evolution`` block. A step without made items (J = R) keeps ``gates.card_decision``, typed-v2's record."""
        require(baseline['items'] == candidate['items'] and baseline['repeats'] == candidate['repeats'],
                'Both arms of a comparison ran on the same gate items with the same repeats')
        kw = {'items': baseline['items'], 'repeats': baseline['repeats'], 'minimum_points': TAU_MIN_POINTS,
              'multiplier': TAU_SE_MULTIPLIER}
        stats = gates.repeat_statistics(baseline['runs'], candidate['runs'], **kw)
        evolution = self.evolution_items(baseline['bench']) if kind == 'card' else None
        if evolution is not None:
            require(list(kw['items'][:len(evolution)]) == evolution,
                    'A card of the step is compared on J, whose head is E = R + A of its sealed item list')
            found = gates.card_decision_evolution(stats, gates.evolution_statistics(stats, evolution))
        elif kind == 'card':
            found = gates.card_decision(stats)
        elif kind == 'no_harm':
            found = gates.no_harm_decision(stats)
        elif kind == 'member':
            found = gates.member_decision(stats)
        else:
            fired = [item for item in kw['items'] if fired_cells.get(item, 0) > 0]
            found = gates.program_decision(stats, gates.repeat_statistics(baseline['runs'], candidate['runs'],
                                                                          subset=fired, **kw), fired_cells)
        return {**found, 'baseline': _arm_ref(baseline), 'candidate_arm': _arm_ref(candidate),
                'baseline_selected': baseline['run_arm'] == 'cand_card',
                'reruns': {'baseline': baseline['reruns'], 'candidate': candidate['reruns']},
                'items': len(kw['items']), 'cells': candidate['cells_run']}

    # ---- typed-v3 T7: the card rule on E, the screen before the gate (brief P3b) --------------------------------------
    def evolution_items(self, bench):
        """The ids of E = R + A of ``bench`` in the current step under the sealed gate rule 'evolution': the real gate
        slice, then the judging-side attack items of the step's SEALED ``items.json`` (its final lists), in J's order.
        None under 'whole', for another bench (a member keeps its real slice and its rule), and on a step without made
        items (no judging-side item: J = R, the card rule is typed-v2's ``card_decision``, records byte-identical)."""
        if self.gate_rule != 'evolution':
            return None
        found = self.own_items(bench)
        if found is None or not found['judging']:
            return None
        return ([item['task_id'] for item in self.items(bench, 'gate')]
                + [entry['record']['item'] for entry in found['record']['lists']['judging']['attack']])

    def screen_items(self, bench):
        """The screen items of ``bench`` in the current step under the sealed ``gate_screen``: A + G, the judging-side
        attack then guard items in J's order. [] without the screen, for another bench, and on a step without such
        items (then no candidate is screened and every gate runs as typed-v2's)."""
        if not self.gate_screen:
            return []
        found = self.own_items(bench)
        if found is None:
            return []
        return [item for item in found['judging'] if found['classes'][item['task_id']] in SCREEN_CLASSES]

    def gate_rule_block(self, bench):
        """The ``gate_rule`` block of a typed-v3 step's ``decisions.json`` (only under a non-default rule or the screen):
        the sealed ``rule`` and ``screen``, the rule the step's cards were decided by (``card_rule``: 'evolution' on E,
        or 'whole' on a step without made items, where J = R), the sizes of J and of E, and the screen items by class
        (``screened`` False: no candidate of the step was screened). Counts only."""
        evolution, screened = self.evolution_items(bench), self.screen_items(bench)
        found = self.own_items(bench)
        classes = found['classes'] if found is not None else {}
        return {'rule': self.gate_rule, 'screen': self.gate_screen,
                'card_rule': 'whole' if evolution is None else 'evolution', 'gate_items': len(self.gate_items(bench)),
                'evolution_items': None if evolution is None else len(evolution), 'screened': bool(screened),
                'screen_items': {name: sum(1 for item in screened if classes[item['task_id']] == name)
                                 for name in SCREEN_CLASSES}}

    def screen(self, stem, bench, arm, candidate, baseline, *, typemap=None, library=None, procedures=None):
        """The screen of one candidate before its gate (typed-v3 T7): unit ``<stem>-screen`` runs the candidate's arm
        ``arm`` (``cand_card`` / ``cand_program``, mounted exactly as its gate arm will be: ``candidate`` from the same
        ``typemap`` and ``library``) ONCE on the screen items A + G (single-run cells labelled with the bare arm);
        ``screen_record`` gives b (the right runs of ``baseline``, the gate entry the candidate is compared with, over
        its R runs on those items: the step's noise unit, an F arm or an accepted candidate's gate arm -- runs that
        exist, never new ones) and c (the candidate's right runs there), and ``gates.screen_decision`` decides
        (``procedures``: the ids whose firing counts, None for a card). None when the step screens nothing.

        WHY the screen's cells are never gate runs: a candidate that passed the screen by luck would carry that luck
        into its gate; the gate's R runs are all fresh, in their own unit, and the screen unit is never a gate arm
        (it is not registered in ``gate_arms``, so no arm can share its runs). Resumable as every cell unit (finished
        cells reused); the write-once ``screen.json`` is recomputed from the cells at every pass and must be equal.
        The record is bound to its candidate: its own unit (the decision's unit + ``-screen``), the arm, the incumbent
        it is compared with (``baseline``), the ids whose firing counts and ``candidate_sha256``, the canonical hash of
        the candidate as mounted (a card's text and home type; a program's record or records with the step's forced
        background), so no decision can carry another candidate's screen (``verify_decision``)."""
        items = self.screen_items(bench)
        if not items:
            return None
        unit = stem + SCREEN_SUFFIX
        cells = self.cells(unit, bench, [(bench, item, (arm,)) for item in items], candidate=candidate, typemap=typemap,
                           library=library)
        return self.screen_record(unit, bench, arm, baseline, cells, procedures, candidate)

    def screen_record(self, unit, bench, arm, baseline, cells, procedures, candidate):
        """The screen record of ``unit`` from its cells ({(item, arm): cell}) and the baseline entry, checked against
        the write-once ``<unit>/screen.json`` (written when absent; a record that differs pauses
        ``gate_screen_changed``). ``gates.screen_counts`` reads the baseline's R runs per screen item and the
        candidate's one cell per item at the bare ``arm`` (never a gate repeat label); an infrastructure or
        configuration unknown left in a screen cell pauses ``gate_cells_unknown`` as a gate arm's does (the recovery
        re-runs those cells). ``fired``: the screen items on which one of ``procedures`` fired (None for a card).
        The record is ``gates.screen_decision``'s plus the unit, bench, step, arm, the screen items' ids and classes,
        the ids whose firing counts, where the baseline runs are, the candidate's canonical hash and the sealed item
        list's hash. In records-only mode (``verify_decision``) a screen that cannot be decided from its cells, or
        whose screen.json is not there, is never written or archived: the stored decision is not reproduced."""
        found, R = self.own_items(bench), self.repeats()
        ids = [item['task_id'] for item in self.screen_items(bench)]
        require(ids and found is not None, 'A screen runs on the step\'s judging-side attack and guard items')
        try:
            b, c = gates.screen_counts(baseline['cells'], cells, items=ids, baseline_arm=baseline['run_arm'],
                                       candidate_label=arm, repeats=R)
        except gates.UndecidableRuns as error:
            self.require_records(unit + '/cells')
            units.archive_done(self.root / unit)  # the recovery re-enters the unit and re-runs exactly those cells
            if error.missing:
                raise Paused('incomplete_unit:missing_cells', unit, '%d of %d screen runs'
                             % (error.expected - error.missing, error.expected)) from None
            raise Paused('gate_cells_unknown', unit, '%d of %d screen runs infrastructure or configuration unknown'
                         % (error.infrastructure, error.expected)) from None
        counted = None if procedures is None else list(procedures)
        fired = (None if counted is None else
                 sum(1 for item_id in ids if set(counted) & set((cells.get((item_id, arm)) or {}).get('fired') or [])))
        classes = found['classes']
        record = {**gates.screen_decision(b, c, repeats=R, items=len(ids), fired=fired), 'unit': unit, 'bench': bench,
                  'step': self.state['step'], 'arm': arm, 'item_ids': ids,
                  'classes': {name: sum(1 for item_id in ids if classes[item_id] == name) for name in SCREEN_CLASSES},
                  'procedures': counted,
                  'baseline': {'unit': baseline['unit'], 'run_unit': baseline['run_unit'], 'run_arm': baseline['run_arm']},
                  'candidate_sha256': library_.canonical_sha256(candidate),
                  'items_sha256': found['record']['record_sha256']}
        path = self.root / unit / SCREEN_RECORD
        if path.exists():
            if units.read_json(path) != record:
                raise Paused('gate_screen_changed', unit, 'the screen record recomputed from its cells differs')
        else:
            self.require_records(unit + '/' + SCREEN_RECORD)
            units.write_json(path, record)
        return record

    # ---- typed-v3 T7: a stored decision is applied only if the chain's records give it again (Codex review of P3b) ---
    def verify_decision(self, unit, decision, compute, *, stored):
        """A card round's, program slot's, repair version's or archive package's decision RELOADED on resume
        (``stored``: its ``decision.json`` existed before this pass) is applied only if the chain's own records give
        it again; else the chain pauses ``gate_decision_changed`` before anything of it is applied or registered.
        ``compute`` is the very decision function with the arguments the chain uses for this candidate in this pass
        (its own units, the incumbent arm it is compared with, the candidate from the writer's or engineer's stored
        record, the step's snapshot, members and forced background, the sealed repeats, tau constants and items J and
        E = R + A); it runs once more in records-only mode (``records_only``): the screen is rebuilt from the
        candidate's own screen unit, the gate comparison from the cells of the intended baseline and candidate arms
        (each gate plan recomputed and equal to its plan.json), every stage decided by the records alone, and nothing
        is sent, run, written, marked or drained -- a record the stages need and that is not there pauses
        ``records_missing``, one that a stage cannot read ``records_invalid:<error class>``. The result must equal the
        stored decision (both as canonical JSON; a smoke's fault list in any order). Fields a decision leaves out
        establish nothing: a stage ran when its records say so. The
        detail names the first part that differs (``decision_difference``): ``screen_differs`` (the screen record,
        present or not: another candidate's screen, a dropped one), ``evolution_items`` (E), ``stage`` (the verdict,
        its reason, whether a gate ran), ``gate_differs`` (the gate rows and arms, the evolution block) or
        ``not_reproduced`` (any other field). A decision computed in this pass is that function's own result: nothing
        to check. Under typed-v2's options (gate rule 'whole', no screen) nothing is checked (typed-v2 behaviour)."""
        if not stored or (self.gate_rule == GATE_RULE_DEFAULT and not self.gate_screen):
            return decision
        with self.records_only(unit):
            try:
                expected = compute()
            except (ValueError, TypeError, KeyError) as error:  # a stage's record without the shape it reads
                raise Paused('gate_decision_changed', unit, 'records_invalid:' + type(error).__name__) from None
        code = decision_difference(decision, expected)
        if code is not None:
            raise Paused('gate_decision_changed', unit, code)
        return decision

    @contextmanager
    def records_only(self, unit):
        """Records-only mode for the stored decision of ``unit`` (``verify_decision``): ``cells`` returns stored cells
        (``stored_cells``), ``record``, ``gate_arm``, ``screen_record`` and ``probe`` never compute or write what is
        not there (``require_records``), ``current`` and ``mark`` leave the state alone. A gate arm rebuilt here joins
        the step's arms in its place, as ``register_stored`` would have registered it."""
        require(self.verifying is None, 'One stored decision is checked at a time')
        self.verifying = unit
        try:
            yield
        finally:
            self.verifying = None

    def require_records(self, what):
        """In records-only mode: ``what`` (a record or cells the stages of the checked decision need) is not there or
        cannot be decided, so the stored decision is not what the chain's records give (``gate_decision_changed``,
        ``records_missing``). Outside it, nothing."""
        if self.verifying is not None:
            raise Paused('gate_decision_changed', self.verifying, 'records_missing')

    def stored_cells(self, unit, jobs):
        """``cells`` in records-only mode: every stored row of ``unit`` by (item, label), as ``cells`` returns a
        complete unit's, read from disk with nothing run, marked or drained; a job without its row, or a unit that
        stopped, is ``records_missing``."""
        unit_dir = self.root / unit
        done = unit_dir / 'done.json'
        if done.exists() and units.read_json(done).get('stop_reason'):
            self.require_records(unit + '/done.json')
        rows = [units.read_json(path) for path in sorted((unit_dir / 'cells').glob('*.json'))]
        found = {(row['item_id'], row['arm']): row for row in rows}
        if any((item['task_id'], label) not in found for _, item, labels in jobs for label in labels):
            self.require_records(unit + '/cells')
        return found

    # ---- shared types (addendum D16: write for every member, gate on every member) -----------------------------
    def members_of(self, k, tid):
        """The other members M of the home type ``tid`` at step k after typing (addendum D16, widened by RP15), in
        the chain's order: every earlier bench whose practice source is in ``tid`` (``member`` 'source') and every
        other earlier bench with at least one gate item that the step's type map routes into ``tid`` (``member``
        'routed'), as ``[{'bench', 'source', 'member', 'routed_gate_items'}]``; ``source`` is the bench's own source
        id and ``routed_gate_items`` the number of its gate items routed into ``tid`` (``routed_gate_items``, for a
        source member too). Benches not learned yet are never members. [] for a type that holds the current bench
        alone and receives no earlier bench's gate item: then nothing of D16 runs (no unit, cell or request, D16 d)."""
        sources = set(self.typemap.data['types'][tid]['sources'])
        found = []
        for bench in self.s.order[:k - 1]:
            sid = tasktypes.source_id(_pool_pin(self.s.manifest, bench))
            routed = self.routed_gate_items(bench, sid, tid)
            if sid in sources or routed:
                found.append({'bench': bench, 'source': sid, 'member': 'source' if sid in sources else 'routed',
                              'routed_gate_items': routed})
        return found

    def routed_gate_items(self, bench, sid, tid):
        """RP15: how many gate items of the earlier ``bench`` (practice source ``sid``) the current type map routes
        into ``tid``, by ``TypeMap.assign`` on each item's practice vector as every mount routes it (zero model
        calls). 0 when the source has another structural signature: no item of it can reach ``tid`` (a practice
        source has one signature, ``typing``), so no other bench is embedded for nothing."""
        signature = self.typemap.data['types'][tid]['signature']
        source = self.typemap.data['sources'].get(sid)
        if source is None or source['signature'] != signature:
            return 0
        vectors = self.vectors_of(bench)
        return sum(1 for item in self.gate_items(bench)
                   if self.typemap.assign(signature, vectors[item['task_id']])['type'] == tid)

    def member_outcomes(self, k, members, *, card=False):
        """D16 (a): the current mount F once on each member bench's LEARN slice, the source of the writers' member
        examples: ``s<k>/member-<b'>-outcomes``; after an accepted card ``s<k>/member-<b'>-outcomes-card`` (F with the
        card), which, as the current bench's ``s<k>/outcomes-card``, is also a gate arm F#1..R on the member's gate
        slice: by the identity rule it is the accepted round's member arm ``card-r<j>-member-<b'>`` (shared, no gate
        cell) and the program member baseline (O5). Returns the members with ``unit``, ``learned`` ({(item, 'F'):
        cell}) and ``current`` (that gate arm; None before a card)."""
        out = []
        for member in members:
            bench = member['bench']
            jobs = [(bench, item, ('F',)) for item in self.items(bench, 'learn')]
            if card:
                unit = 's%d/member-%s-outcomes-card' % (k, bench)
                current = self.gate_arm(unit, bench, 'F', extra_jobs=jobs)
                learned = {key: row for key, row in current['unit_cells'].items() if key[1] == 'F'}
            else:
                unit, current = 's%d/member-%s-outcomes' % (k, bench), None
                learned = self.cells(unit, bench, jobs)
            out.append({'bench': bench, 'source': member['source'], 'member': member['member'],
                        'routed_gate_items': member['routed_gate_items'], 'unit': unit, 'learned': learned,
                        'current': current})
        return out

    def member_examples(self, members, *, learn_items=False):
        """D16 (a): each member's writer examples, chosen by the current bench's rule (``Services.
        outcomes_for_writer`` over the member's learn cells; the writers cap them at the current bench's counts and
        label the block with the source). Learn cells only: no gate item of any bench reaches a writer. With
        ``learn_items`` (the card writer) each row also carries the member's learn items and ids for its screen. The
        cells are the member's ``learned`` under its ``learned_arm`` ('F' unless typed-v3's ``archive_outcomes`` set
        the package's arm)."""
        out = []
        for member in members:
            bench, learned, arm = member['bench'], member['learned'], member.get('learned_arm', 'F')
            learn = self.items(bench, 'learn')
            cells = [learned[(item['task_id'], arm)] for item in learn if (item['task_id'], arm) in learned]
            row = {'bench': bench, 'source': member['source'],
                   'examples': self.s.outcomes_for_writer(cells, learn, bench=bench)}
            if learn_items:
                row.update(corpus=learn, practice_ids=[item['task_id'] for item in learn])
            out.append(row)
        return out

    def member_base(self, k, member, *, typemap=None, library=None):
        """D16 (b): the member baseline before an accepted card, the current mount F R times on the member bench's
        gate slice (``s<k>/member-<b'>-base``, labels F#1..R). It runs once per step, when a first candidate passed
        the home rule; every later check of the step gets the registered arm back (``gate_arm``)."""
        return self.gate_arm('s%d/member-%s-base' % (k, member['bench']), member['bench'], 'F', typemap=typemap,
                             library=library)

    def member_checks(self, unit, arm, candidate, members, baseline_of, *, typemap=None, library=None):
        """D16 (b): the member checks of one candidate that passed the home rule, in member order. The candidate's
        arm runs R times on each member bench's gate slice (``<unit>-member-<b'>``: cand_card / cand_program; D5's
        arm sharing and the per-(unit, tag) rerun rule hold as for every gate arm) and is compared with the member
        baseline ``baseline_of(member)``: ``gates.member_decision`` (no_regress, tau from that baseline's repeats).
        The first member harm ends the checks (no later member runs a cell). Each check keeps the member's bench and
        source, the units and labels that hold both arms' runs, and ``baseline_selected``."""
        checks = []
        for member in members:
            bench = member['bench']
            baseline = baseline_of(member)
            found = self.gate_arm('%s-member-%s' % (unit, bench), bench, arm, candidate=candidate, typemap=typemap,
                                  library=library)
            check = {**self.compare('member', baseline, found), 'bench': bench, 'source': member['source'],
                     'units': {'baseline': baseline['run_unit'], 'candidate': found['run_unit']},
                     'labels': {'baseline': list(baseline['labels']), 'candidate': list(found['labels'])}}
            checks.append(check)
            if not check['no_regress']:
                break
        return checks

    @staticmethod
    def shared(decision, checks, members):
        """The D16 fields of a card or program record of a shared type: ``shared_with`` (the members, in order, each a
        source or a routed member with the number of its gate items routed into the home type, RP15), ``members``
        (the checks that ran) and the final verdict ``accepted`` / ``reason`` / ``member_harm``
        (``gates.shared_verdict``: the home rule AND no_regress on every member)."""
        shared_with = [{'bench': member['bench'], 'source': member['source'], 'member': member['member'],
                        'routed_gate_items': member['routed_gate_items']} for member in members]
        return {'shared_with': shared_with, 'members': list(checks),
                **gates.shared_verdict(decision, list(checks), shared_with)}

    # ---- one step -------------------------------------------------------------------------------------------
    def learn(self, k, bench):
        """The learning of step k on ``bench`` from the frozen state of step k-1, ending with the freeze of s<k> and
        its receipt (``finalize``). Skipped when step k is learned (its receipt exists; a step interrupted before its
        receipt runs its body again, every finished unit returning its record). Under 'learn_first' learning is
        closed once reading has begun (read-plan R79): the body never runs again, and a missing or changed s<k> file
        or receipt pauses ``frozen_state_changed`` instead of a new learning."""
        if self.learning_closed():
            self.load_frozen(k)
            return
        if self.learned(k):
            return
        self.load_frozen(k - 1)
        self.state['step'], self.state['phase'] = k, 'learn'
        self.persist()
        self.gate_arms = []  # every comparison of the step reads its arms from here (DESIGN 3.4 "Shared arms")
        self.step_items = None  # typed-v3 (brief P2b): no step ever sees another step's items
        if self.item_stage != ITEM_STAGE_DEFAULT:  # typed-v3 T3 steps 1 to 5: the sealed items.json, then J
            from . import itemstage
            itemstage.stage(self, k, bench)
        noise = self.noise(k, bench)
        typing = self.typing(k, bench)
        learned, incumbent = self.outcomes(k, bench, 's%d/outcomes' % k)
        # addendum D16, RP15: the earlier benches of the home type, by source or by routed gate items (none for a type
        # of one bench that receives no earlier gate item: nothing below changes)
        members = self.members_of(k, typing['type'])
        members = self.member_outcomes(k, members) if members else []
        rounds = self.cards(k, bench, typing['type'], learned, incumbent, members)
        programs, current = self.programs(k, bench, typing['type'], learned, incumbent,
                                          any(r.get('accepted') for r in rounds), members)
        self.finalize(k, bench, noise, typing, (learned, incumbent), rounds, programs, current, members)

    def read_step(self, k):
        """Event S<k> on the five panels from the frozen state of step k (its receipt, whatever was learned
        later), then ``step-<k>``; a done ``step-<k>`` only reloads s<k> (typed-v1's skip). ``state['step']`` is not
        changed here."""
        if self.done('step-%d' % k):
            self.load_state(k)
            return
        receipt = self.load_frozen(k)  # the reads use exactly the frozen files
        self.bind_read('S%d' % k, k, receipt)
        self.reads('S%d' % k)
        self.mark('step-%d' % k)

    def noise(self, k, bench):
        """The learning base B (the manifest's base card alone, addendum D17; with 'format' B mounts what C0 mounts)
        R times on the gate slice (labels ``B#1..R``): the step's calibration (``gates.calibration``: Q, se and tau
        from B's own repeats; ``decisions.json['tau_points']``) and the shared baseline ``B@noise`` of every no-harm
        check and of a new type's F without skills (DESIGN 3.4)."""
        unit = 's%d/noise' % k
        entry = self.gate_arm(unit, bench, BASE_ARM)
        record = self.record(unit, 'noise.json', lambda: {
            'unit': unit, 'bench': bench, 'step': k, 'items': len(entry['items']), 'cells': entry['cells_run'],
            'arms': list(entry['labels']), 'mount_arm': BASE_ARM, 'reruns': entry['reruns'],
            **gates.calibration(entry['runs'], items=entry['items'], repeats=entry['repeats'],
                                minimum_points=TAU_MIN_POINTS, multiplier=TAU_SE_MULTIPLIER)})
        self.mark(unit)
        return record

    def typing(self, k, bench):
        """Register the bench's source; join a same-signature type only when its mount does no harm (no-harm
        units), else open a new type; freeze the type map of the typing unit. A resumed step reloads the record and
        registers the no-harm arms again (in their order)."""
        unit = 's%d/typing' % k
        path = self.root / unit / 'typing.json'
        if path.exists():
            self.typemap = tasktypes.TypeMap.load(self.root / unit / 'typemap.json')
            record = units.read_json(path)
            for check in record['no_harm']:
                self.register_stored(check['unit'])
            self.mark(unit)
            return record
        self.current(unit)
        source, vectors, views = self.s.items[bench], self.vectors_of(bench), self.views_of(bench)
        signatures = sorted({tasktypes.structural_signature(views[item['task_id']]) for item in source})
        require(len(signatures) == 1, 'A practice source has one structural signature, found %r' % (signatures,))
        signature = signatures[0]
        sid = self.typemap.add_source(_pool_pin(self.s.manifest, bench), signature,
                                      [vectors[item['task_id']] for item in source], step=k)
        checks, tid = [], None
        for candidate in self.typemap.types_with_signature(signature):
            decision = self.no_harm(k, bench, sid, candidate)
            checks.append({'type': candidate, **decision})
            if decision['merge']:
                evidence = {key: decision.get(key) for key in ('reason', 'n', 'excluded_unknown', 'mean_points',
                                                               'tau_points', 'repeats', 'se_points')}
                tid = self.typemap.merge_source(sid, candidate, step=k, evidence=evidence)
                break
        if tid is None:
            tid = self.typemap.new_type(sid, step=k)
        digest = self.typemap.freeze(self.root / unit / 'typemap.json', step=k)
        record = {'unit': unit, 'bench': bench, 'step': k, 'source': sid, 'signature': signature, 'members': len(source),
                  'type': tid, 'new_type': not checks or not checks[-1]['merge'], 'no_harm': checks,
                  'typemap_sha256': digest}
        units.write_json(path, record)
        self.mark(unit)
        return record

    def no_harm(self, k, bench, sid, tid):
        """That type's current mount (F, with the source provisionally merged so its items route to the type) R
        times on the bench's gate slice (``F#1..R``) against the shared baseline ``B@noise`` (the manifest's base
        alone, addendum D17): merge iff no_regress(D) (``gates.no_harm_decision``, DESIGN 3.4). Returns the STORED
        record (a resumed step reads the decision it wrote, never a recomputation)."""
        unit = 's%d/noharm-%s' % (k, tid)
        scratch = tasktypes.TypeMap(deepcopy(self.typemap.data))
        scratch.merge_source(sid, tid, step=k, evidence={'provisional': True})
        baseline = self.registered('s%d/noise' % k)
        merged = self.gate_arm(unit, bench, 'F', typemap=scratch)
        return self.record(unit, 'decision.json', lambda: {**self.compare('no_harm', baseline, merged), 'unit': unit})

    def outcomes(self, k, bench, unit):
        """Arm F (the current mount) once on the learn items (the writers' examples) and, as a gate arm, R times on
        the gate items (``F#1..R``) unless F is the same arm as an earlier arm of the step (DESIGN 3.4: ``B@noise``
        for a new type without skills, ``F@noharm-<T>`` after a merge, the accepted round's ``cand_card`` after a
        card). Returns ({(item_id, 'F'): learn cell}, the F gate arm). typed-v3 T6: under the item stage 'planned' F
        also runs once on the step's SHOWN made items (``shown_items``), whose cells join the learn cells."""
        learn = self.items(bench, 'learn') + self.shown_items(bench)
        entry = self.gate_arm(unit, bench, 'F', extra_jobs=[(bench, item, ('F',)) for item in learn])
        return {key: row for key, row in entry['unit_cells'].items() if key[1] == 'F'}, entry

    def cards(self, k, bench, tid, learned, incumbent, members=()):
        """Write (round 1) / revise (round 2) -> ``cand_card#1..R`` on the gate slice against the incumbent F arm
        (``gates.card_decision``, DESIGN 3.4; tau from the incumbent's own repeats).

        The revision round's prompt (``CARD_REVISE_SYSTEM``, mandated as is) shows the writer the solver's attempts
        WITH its previous card, so after a rejected round the rejected card is run on the LEARN slice
        (``s<k>/card-r<j>-learn``, single-run; the gate slice never reaches a writer) and the round-2 examples come
        from those cells, ordered as v2.25 orders them (failures the card broke and successes it fixed first, against
        the current arm's learn outcomes). One learn-slice read per rejected round; nothing when round 1 is accepted.
        The gate arm runs (or is shared, or is reloaded) before the write-once decision record, so a resumed step
        registers it again in its place.

        Shared type (addendum D16, ``members`` not empty): both rounds' writer requests also hold every member's
        examples from ``s<k>/member-<b'>-outcomes`` (``member_examples``; ``writers`` caps, labels and fits them), and
        a round that passed the home rule is checked on every member before its decision record
        (``card_member_checks``).

        typed-v3 T6 (item stage 'planned'): the examples are the learn examples followed by the shown made items'
        (``shown_examples``: attack first); the card screen's corpus and practice ids hold the shown items too; a
        rejected round's card also runs on the shown items in ``s<k>/card-r<j>-learn``, so round 2 shows the solver's
        attempts WITH the previous card on both. ``practice`` is the learn slice alone under 'none'."""
        learn = self.items(bench, 'learn')
        practice = learn + self.shown_items(bench)
        examples = self.s.outcomes_for_writer([learned[(i['task_id'], 'F')] for i in learn if (i['task_id'], 'F') in learned],
                                              learn, bench=bench)
        examples += self.shown_examples(bench, learned, 'F')
        examples_unit = 's%d/outcomes' % k
        current = self.library.active_card(tid)
        member_kw = {'members': self.member_examples(members, learn_items=True)} if members else {}
        previous, result, rounds = None, None, []
        for j in range(1, self.s.limits['card_rounds'] + 1):
            unit = 's%d/card-r%d' % (k, j)
            self.current(unit)
            # a resumed round writes again on the same calls file: every earlier send stays in it (fix-b, rb-resume 2)
            written = self.record(unit, 'writer.json', lambda: self.s.write_card(
                bench=bench, runtime=self.s.runtime, current_text=current['body']['text'] if current else '',
                examples=examples, corpus=practice, practice_ids=[item['task_id'] for item in practice],
                call=self.role('card_writer', unit, 'writer', WRITER_TOKENS), round=j,
                previous=previous, result=result, base_card=self.base_card, **member_kw))
            text = written.get('text')
            # typed-v3 T7: the screen first (None when the step screens nothing); a round refused there runs no gate
            screen = (self.screen(unit, bench, 'cand_card', {'text': text, 'home_type': tid}, incumbent)
                      if text else None)
            gated = bool(text) and (screen is None or screen['passed'])
            candidate = (self.gate_arm(unit, bench, 'cand_card', candidate={'text': text, 'home_type': tid})
                         if gated else None)
            checks = self.card_member_checks(k, unit, tid, text, incumbent, candidate, members) if gated else []

            def compute():
                return self.card_decision(k, bench, tid, unit, j, text, written, incumbent, candidate, examples_unit,
                                          members, checks, screen=screen)
            stored = (self.root / unit / 'decision.json').exists()
            decision = self.record(unit, 'decision.json', compute)
            # typed-v3 T7: a reloaded decision must be the one this pass's writer record, screen and gate give
            self.verify_decision(unit, decision, compute, stored=stored)
            rounds.append(decision)
            self.mark(unit)
            if decision['accepted']:
                self.apply_card(k, tid, unit)
                break
            if not text:
                break  # nothing to revise
            if j < self.s.limits['card_rounds']:
                examples_unit = unit + '-learn'
                shown = self.cells(examples_unit, bench, [(bench, item, ('cand_card',)) for item in practice],
                                   candidate={'text': text, 'home_type': tid})
                baseline = {item['task_id']: _correct(learned, item['task_id'], 'F') for item in practice}
                examples = self.s.outcomes_for_writer(
                    [shown[(i['task_id'], 'cand_card')] for i in learn if (i['task_id'], 'cand_card') in shown],
                    learn, bench=bench, baseline=baseline)
                examples += self.shown_examples(bench, shown, 'cand_card', baseline=baseline)
            previous, result = text, decision
        return rounds

    def card_member_checks(self, k, unit, tid, text, incumbent, candidate, members):
        """D16 (b) for one card round: the member checks run only when the round passed the home rule (``compare``
        of the home arms, zero calls), each against the member base F (``member_base``). They run BEFORE the round's
        write-once decision record, as the round's own gate arm does, so a resumed step registers every arm again in
        its place (their cells are reused, nothing is sent twice). [] for a type of one bench."""
        if not members or not self.compare('card', incumbent, candidate)['accepted']:
            return []
        return self.member_checks(unit, 'cand_card', {'text': text, 'home_type': tid}, members,
                                  lambda member: self.member_base(k, member))

    def card_decision(self, k, bench, tid, unit, j, text, written, incumbent, candidate, examples_unit, members=(),
                      checks=(), *, screen=None):
        """The write-once decision of card round j. typed-v3 T7 (brief P3b): ``screen`` is the round's screen record
        (None when the step screens nothing); a round refused there gets a decision with zero gate cells (``accepted``
        False, the screen's reason -- ``screen_below_baseline`` / ``screen_never_fired`` of ``gates.SCREEN_REASONS``
        -- and the record under ``screen_run``); a round that passed it keeps the record beside its gate decision."""
        passed = [a for a in (written.get('attempts') or []) if isinstance(a, dict) and a.get('violation') is None
                  and a.get('request_sha256')]
        base = {'kind': 'card', 'round': j, 'unit': unit, 'attempts': written.get('attempts'),
                'request_sha256': passed[-1]['request_sha256'] if passed else None, 'examples_unit': examples_unit}
        if not text:
            failed = {**base, 'accepted': False, 'reason': 'writer_screens_failed'}
            return {**failed, **self.shared(failed, [], members)} if members else failed
        if screen is not None and not screen['passed']:  # typed-v3 T7: refused at the screen, no gate cell ran
            refused = {**base, 'accepted': False, 'reason': screen['reason'], 'screen_run': screen, 'cells': 0,
                       'text_sha256': _sha(text), 'chars': cards.content_chars(text)}
            return {**refused, **self.shared(refused, [], members)} if members else refused
        # chars: content characters (DESIGN 3.1), the final newline of the stored text not counted
        decision = {**base, **self.compare('card', incumbent, candidate), 'text_sha256': _sha(text),
                    'chars': cards.content_chars(text)}
        if screen is not None:  # typed-v3 T7: the screen it passed
            decision['screen_run'] = screen
        if members:  # addendum D16 (b): the home rule AND no_regress on every member bench
            decision.update(self.shared(decision, checks, members))
        if decision['accepted']:
            self.record(unit, 'skill.json', lambda: self.make_skill('card', tid, k, bench, unit, {'text': text}, decision))
        return decision

    def make_skill(self, kind, tid, k, bench, unit, body, decision, *, library=None, origin=None):
        """A described skill record (design §1.1); a card whose describer failed gets the fallback description
        (it is mounted, never selected), a program is refused then (its description is what the selector sees).
        typed-v3 (T9): ``library`` names the library the id and name are drawn against (default the chain's; an
        archive package draws its ids one after the other on a scratch copy) and ``origin`` adds fields to the
        skill's origin (an archive skill's ``kind`` 'archive' and package); both unset, the record is typed-v2's."""
        library = self.library if library is None else library
        skill_id = library.next_id(kind, tid, k)
        signature = self.typemap.data['types'][tid]['signature']
        # a card's origin also keeps its decision's content characters (DESIGN 3.1: chars in the skill record); every
        # origin keeps the tau of its own decision and its repeats and se (DESIGN 4.1), a program its fired items
        kept = (('reason', 'n', 'excluded_unknown', 'mean_points', 'tau_points', 'repeats', 'se_points')
                + (('chars',) if kind == 'card' else ('gain_points_fired', 'fired_items')))
        origin = {'chain': self.s.chain, 'step': k, 'bench': bench, 'unit': unit, 'accepted_at': _now(),
                  'writer_call_sha256': decision.get('request_sha256'),
                  'decision': {key: decision.get(key) for key in kept}, **(origin or {})}
        skill = library_.make_skill(skill_id=skill_id, name=_skill_name(library, kind, signature, k, skill_id),
                                    kind=kind, home_type=tid, body=body, origin=origin)
        described = self.describe(skill, bench, unit)
        skill['description'] = described.get('description')
        if kind == 'card' and not skill['description']:
            # a gate-accepted card is installed whatever its describer replied (the card is never selected, only
            # mounted); the engineer's index still needs a description, so a parsed-invalid reply gets the frozen,
            # deterministic fallback below (public structure only, no card text) and says so in its origin
            skill['description'] = CARD_FALLBACK_DESCRIPTION % signature
            skill['origin']['description_source'] = 'fallback_after_describer_failure'
        elif skill['description']:
            skill['origin']['description_source'] = 'describer'
        return {'skill': skill, 'description': described}

    def describe(self, skill, bench, unit):
        """The describer call of an accepted skill. A description that never ARRIVED (``writers.describe`` reports
        ``infrastructure``: transport/HTTP failures on the last attempt) is no verdict on the skill: one automatic
        retry after 60 s, then the chain pauses (``describer_unavailable``) before any decision is written, so a
        recovery describes again; only a parsed-but-invalid description is a description failure. A recovery describes
        on the calls file of the earlier attempt with the same tag, and every earlier send stays in it (fix-b,
        review rb-resume 2). Under 'repair' (Codex P1 F5) or the resume replay 'on' (B6 d) a resumed describer goes on
        at the LAST attempt whose calls file holds a delivered receipt (attempt 2 runs only after attempt 1 ended
        without a description for an infrastructure reason) and replays its receipts (``role``), so a saved success of
        the retry is never sent again; with no delivered receipt it starts at attempt 1, as typed-v2."""
        key = unit + '/describe-' + skill['skill_id']
        tags = ['describe-' + skill['skill_id'] + suffix for suffix in ('', '-r2')]
        first = self.delivered_attempt('describer', unit, tags, DESCRIBER_TOKENS) if self.replays_role_calls() else 1
        for attempt in (1, 2):
            if attempt < first:
                continue
            tag = tags[attempt - 1]
            call = self.role('describer', unit, tag, DESCRIBER_TOKENS)
            try:
                found = self.s.describe(skill, self.examples_of(bench), call)
            except ValueError as error:  # a malformed description request (never a reply text)
                return {'description': None, 'error': _pause_detail(error)}
            found = found if isinstance(found, dict) else {'description': None, 'error': 'describer returned no record'}
            if found.get('description') or not found.get('infrastructure'):
                return found
            if attempt == 1 and not self.state['infra_retries'].get(key):
                self.state['infra_retries'][key] = {'at': _now(), 'seconds': RETRY_SECONDS}
                self.persist()
                self.sleep(RETRY_SECONDS)
                continue
            raise Paused('describer_unavailable', unit, skill['skill_id'])

    def apply_card(self, k, tid, unit):
        skill = units.read_json(self.root / unit / 'skill.json')['skill']
        self.library.retire_card(tid, step=k)
        self.library.add(skill)
        self.typemap.set_card(tid, skill['skill_id'], step=k)

    def programs(self, k, bench, tid, learned, incumbent, card_accepted, members=()):
        """Proposals from the engineer (skill index = names + descriptions, outcomes WITH the accepted card), each
        screened -> smoke on learn items -> gate on the gate slice -> gates.program_decision -> describe + add.

        The gate's current side is the mount the candidate is forced into (design §2.5: accepted card + candidate):
        after an accepted card the step runs ``s<k>/outcomes-card`` (F with the card once on the learn items; its
        gate arm is the accepted round's ``cand_card`` runs, DESIGN 3.4 case (e), addendum O5) and judges every
        program against it, so a program is never credited with the card's gain; without a card acceptance the F
        arm of ``s<k>/outcomes`` is that mount already. Returns (decisions, (current unit name or None, its learn
        cells, its gate arm)).

        Promotion (DESIGN 3.2): the writer decides each row's status and slot inside the unit ``s<k>/programs`` (a
        later proposal takes a slot only because an earlier one was unreadable or failed the static screen). The
        chain iterates over ALL rows of ``proposals.json`` in the writer's order: a row with a slot runs its units
        ``s<k>/program-<slot>-smoke`` / ``-gate`` (slots 1..``max_program_candidates``, so no ``program-3*`` unit); a
        ``dropped_screen`` / ``unreadable`` / ``kind_not_new`` / ``no_reply`` row gets a zero-call decision row
        (``candidate`` and ``unit`` null, never a unit directory); a ``not_needed`` row appears in ``proposals.json``
        only. A smoke fault or a gate rejection of a slot candidate promotes nothing. A resumed attempt of the unit
        keeps the earlier attempts' sends in its calls file (DESIGN 3.3, ``_keep_earlier_sends``); under the resume
        replay 'on' (typed-v3 B6 d) it answers the proposal from their saved receipts (``role``), as every role call.

        Shared type (addendum D16): after an accepted card the members' learn outcomes are taken again with the card
        (``s<k>/member-<b'>-outcomes-card``, whose gate arm is the card's member runs); the engineer's payload holds
        every member's examples from there (else from ``s<k>/member-<b'>-outcomes``), and a program that passed the
        home rule is checked on every member against that baseline (before a card: ``s<k>/member-<b'>-base``).
        Returns (decisions, (current unit name or None, its learn cells, its gate arm, the members)).

        typed-v3: under the sealed program learning 'repair' (T8, T9) the step runs ``programs_repair`` instead; the
        'single' flow below is typed-v2's, unchanged under the resume replay 'off'."""
        if self.program_learning == 'repair':
            return self.programs_repair(k, bench, tid, learned, incumbent, card_accepted, members)
        learn = self.items(bench, 'learn')
        current_unit = 's%d/outcomes-card' % k if card_accepted else None
        current_learned, current = self.outcomes(k, bench, current_unit) if card_accepted else (learned, incumbent)
        if members and card_accepted:
            members = self.member_outcomes(k, members, card=True)
        examples = self.s.outcomes_for_writer([current_learned[(i['task_id'], 'F')] for i in learn
                                               if (i['task_id'], 'F') in current_learned], learn, bench=bench)
        examples += self.shown_examples(bench, current_learned, 'F')  # typed-v3 T6 ('planned'; else nothing)
        unit = 's%d/programs' % k
        self.current(unit)
        # design §5.2: the engineer sees the index of ALL types (names, kinds, frozen descriptions, home type; never
        # a body), the selector only its type's programs
        index = [{'name': s['name'], 'kind': s['kind'], 'description': s.get('description') or '', 'home_type': s['home_type']}
                 for s in self.library.active()]

        def propose():
            call = self.role('program_writer', unit, 'writer', WRITER_TOKENS)  # 'off': _keep_earlier_sends alone
            member_kw = ({'members': [{key: row[key] for key in ('bench', 'source', 'examples')}
                                      for row in self.member_examples(members)]} if members else {})
            return self.s.propose_programs(
                bench=bench, runtime=self.s.runtime, skill_index=index, examples=examples,
                hook_view=self.views_of(bench)[self.hook_item(bench, learn)['task_id']],  # B7b: no refused item
                parent=[s['body']['procedure'] for s in self.library.programs(tid)], step=k, call=call,
                max_candidates=self.s.limits['max_program_candidates'], evidence=ROUTE_B_EVIDENCE[self.s.mode],
                base_card=self.base_card, **member_kw)
        proposals = self.record(unit, 'proposals.json', propose)
        self.mark(unit)
        rows = list(proposals or [])
        _check_proposal_rows(rows, self.s.limits['max_program_candidates'])
        # every candidate of the step is gated against the SAME current arm with the same mount: the gate cells
        # mount from this snapshot, so a second candidate never carries an earlier acceptance's gain (design §2.5)
        snapshot = (library_.Library(deepcopy(self.library.data)), tasktypes.TypeMap(deepcopy(self.typemap.data)))
        decisions = []
        for row in rows:
            if row['slot'] is not None:
                decisions.append(self.program(k, bench, tid, current, learn, row['slot'], row, snapshot, members))
            elif row['status'] in ZERO_CALL_STATUSES:
                decisions.append(self.program_decision(k, bench, tid, current, learn, None, None, row, snapshot,
                                                       members))
        return decisions, (current_unit, current_learned, current, members)

    def program(self, k, bench, tid, incumbent, learn, i, proposal, snapshot, members=()):
        unit = 's%d/program-%d' % (k, i)
        self.current(unit)

        def compute():
            return self.program_decision(k, bench, tid, incumbent, learn, i, unit, proposal, snapshot, members)
        stored = (self.root / unit / 'decision.json').exists()
        decision = self.record(unit, 'decision.json', compute)
        self.verify_decision(unit, decision, compute, stored=stored)  # typed-v3 T7 (nothing under typed-v2's options)
        if decision.get('candidate_arm') is not None:  # a stored decision: its gate arm joins the step's arms again
            self.register_stored(unit + '-gate')
            for check in decision.get('members') or []:  # D16: its member arms too, in the order they ran
                self.register_stored(check['baseline']['unit'])
                self.register_stored(check['candidate_arm']['unit'])
        if decision['accepted']:
            skill = units.read_json(self.root / unit / 'skill.json')['skill']
            self.library.add(skill)
            self.typemap.add_program(tid, skill['skill_id'], step=k)
        return decision

    def program_decision(self, k, bench, tid, incumbent, learn, i, unit, proposal, snapshot, members=()):
        """The decision of one ``proposals.json`` row: ``i`` is its slot and ``unit`` its ``s<k>/program-<slot>``;
        both are None for an unpromoted row, which returns at the screen guard with zero calls
        (``_unpromoted_reason``). ``base`` names the proposal (its 1-based number ``n``, None for a whole-reply row)
        and its status (DESIGN 3.2, 4.1). The gate: ``cand_program#1..R`` against the incumbent F arm; an item is
        fired when the program fired in at least one of its R cells and ``fired_cells`` keeps the count per item
        (addendum O6). A gate-accepted program whose describer reply never parsed is not installed: the record says
        ``description_failed`` and keeps the gate's own verdict in ``gate_verdict`` (``recompute_decision``).

        Shared type (addendum D16 b): a program that passed the home rule is checked on every member bench
        (``s<k>/program-<i>-member-<b'>``, mounted from the same snapshot) against the member baseline: after an
        accepted card that card's member runs (``member['current']``, O5), else ``s<k>/member-<b'>-base``. Every
        record of the step then carries ``shared_with``, ``members`` and ``member_harm``."""
        library, typemap = snapshot
        procedure, screen = proposal.get('procedure'), proposal.get('screen') or {}
        base = {'kind': 'program', 'candidate': i, 'unit': unit, 'proposal': proposal.get('n'),
                'status': proposal.get('status'), 'procedure_id': (procedure or {}).get('id'),
                'request_sha256': proposal.get('request_sha256'), 'screen': screen,
                'mount_snapshot': {'library': [s['skill_id'] for s in library.active()], 'typemap_step': typemap.data.get('step')}}

        def unchecked(found):  # a record that never reached the member checks (D16: shared fields, no check)
            return {**found, **self.shared(found, [], members)} if members else found
        if not isinstance(procedure, dict) or not screen.get('passed'):
            return unchecked({**base, 'accepted': False, 'reason': _unpromoted_reason(proposal)})
        smoke_items = learn[:self.s.limits['program_smoke_items']]
        smoke = self.cells(unit + '-smoke', bench, [(bench, item, ('cand_program',)) for item in smoke_items],
                           candidate={'procedure': procedure, 'home_type': tid}, typemap=typemap, library=library)
        faults = [{'item_id': item_id, 'faults': row.get('faults'), 'failure': row.get('failure'),
                   'configuration_error': bool(row.get('configuration_error'))} for (item_id, _), row in smoke.items()
                  if row.get('faults') or row.get('failure') or row.get('configuration_error')]
        summary = {'items': len(smoke_items), 'cells': len(smoke), 'faults': faults}
        if faults or len(smoke) < len(smoke_items):
            return unchecked({**base, 'accepted': False, 'reason': 'smoke_fault', 'smoke': summary})
        candidate = {'procedure': procedure, 'home_type': tid}
        pid = procedure.get('id')
        # typed-v3 T7: the screen before the gate (None when the step screens nothing); refused there, no gate runs
        screen = self.screen(unit, bench, 'cand_program', candidate, incumbent, typemap=typemap, library=library,
                             procedures=[pid])
        if screen is not None and not screen['passed']:
            return unchecked({**base, 'accepted': False, 'reason': screen['reason'], 'smoke': summary,
                              'screen_run': screen, 'cells': 0})
        arm = self.gate_arm(unit + '-gate', bench, 'cand_program', candidate=candidate, typemap=typemap,
                            library=library)
        fired = {item_id: sum(pid in ((arm['cells'].get((item_id, label)) or {}).get('fired') or [])
                              for label in arm['labels']) for item_id in arm['items']}
        decision = {**base, **self.compare('program', incumbent, arm, fired_cells=fired), 'smoke': summary,
                    **({'screen_run': screen} if screen is not None else {})}
        if members:  # addendum D16 (b): the home rule AND no_regress on every member bench
            checks = (self.member_checks(unit, 'cand_program', candidate, members,
                                         lambda member: member['current'] or self.member_base(
                                             k, member, typemap=typemap, library=library),
                                         typemap=typemap, library=library) if decision['accepted'] else [])
            decision.update(self.shared(decision, checks, members))
        if decision['accepted']:
            made = self.record(unit, 'skill.json', lambda: self.make_skill('program', tid, k, bench, unit, {'procedure': procedure}, decision))
            if not made['skill'].get('description'):
                decision = {**decision, 'accepted': False, 'reason': 'description_failed', 'description': made['description'],
                            'gate_verdict': {'accepted': decision['accepted'], 'reason': decision['reason']}}
        return decision

    # ---- typed-v3 program learning: probe, free repair rounds, one paid feedback round, archive (T8, T9) -------------
    def role(self, purpose, unit, tag, max_tokens):
        """A role recorder of ``unit``: its calls file keeps every earlier attempt's sends (``_keep_earlier_sends``,
        typed-v2). Under 'repair' (Codex P1 F5) the completed receipts of those sends are replayed before anything is
        sent (``_replay_receipts``: delivered receipts, and failures the earlier flow went past): a step interrupted
        after a call's receipt was saved and before its phase record (``writer.json``, ``proposals.json``, a skill
        record) was written sends and charges nothing again. Every role call of the chain whose record is written
        after the call returns comes through here (card writer, engineer proposals and fixes, repairs, describers,
        the archive's describers; a describer resumes at its attempt that holds a delivered receipt,
        ``delivered_attempt``); under 'single' typed-v2's resume (each call sent again, every send kept) is
        unchanged unless the run's resume replay is 'on' (typed-v3 B6 d: the same replay). Under 'on' the sends are
        numbered and replayed by occurrence; under 'repair' with 'off' the replay is cb80dcc's (unnumbered sends,
        delivered receipts first; Codex's second look at the replay, point 2). A calls file the replay 'on' cannot
        match (sends without an occurrence) pauses the unit, 'replay_refused', before anything is sent."""
        call = _keep_earlier_sends(self.s.role_call(purpose, unit, tag, max_tokens))
        if not self.replays_role_calls():
            return call
        try:
            return _replay_receipts(call, numbered=self.resume_replay == 'on')
        except units.ReplayRefused as error:
            name = Path(getattr(call, 'out_path', None) or '').name
            raise Paused(units.REPLAY_REFUSED, unit, '%s: sends without an occurrence in %s' % (_pause_detail(error),
                                                                                                name))

    def replays_role_calls(self):
        """The role calls replay their saved receipts on resume: under the program learning 'repair' (P1 F5) or the
        resume replay 'on' (B6 d)."""
        return self.program_learning == 'repair' or self.resume_replay == 'on'

    def delivered_attempt(self, purpose, unit, tags, max_tokens):
        """The number (1-based) of the last of ``tags`` -- the calls files of one role call's attempts, in attempt
        order -- that holds a delivered receipt; 1 when none does. Under 'repair' a resumed call with retry attempts
        goes on there (Codex P1 F5); the describer is the chain's only role call whose infrastructure retry writes
        to a calls file of its own (``describe-<id>-r2``): the card writer, the engineer's proposal and fixes and every
        repair round keep all their attempts in one calls file (``writer``), replayed by ``role``."""
        found = 1
        for n, tag in enumerate(tags, 1):
            if _holds_delivered(getattr(self.s.role_call(purpose, unit, tag, max_tokens), 'out_path', None)):
                found = n
        return found

    def repair_limit(self, key):
        """A 'repair' limit (``REPAIR_LIMITS`` defaults, ``Services.limits`` overrides): a non-negative integer."""
        found = self.s.limits.get(key, REPAIR_LIMITS[key])
        require(type(found) is int and found >= 0, 'The repair limit %s is a non-negative integer' % key)
        require(key != 'program_paid_feedback' or found <= 1, 'At most one paid feedback round per program (T8)')
        return found

    def probe(self, k, bench, unit, procedures, items, *, home_type, typemap, library, learned, background=()):
        """T8.2 (and T9's package probe): the zero-call probe of a candidate -- ``procedures``, the records whose effect
        is measured (a program version, or every record of an archive package) -- on ``items``, the write-once
        ``<unit>/probe.json``. Every item's first request is built twice by the solver shell (``Services.solve_fn``)
        with a probe call (``Services.probe_call``, default ``ProbeCall``): the incumbent side and the candidate side.
        Both mount from the step's comparison snapshot ``(typemap, library)`` with the incumbents a real arm of the
        step mounts (Codex P1 F2, F4): ``background`` -- the programs accepted earlier in this step, an accepted
        archive package -- forced on both sides, and the type's other library programs as the item's RECORDED
        selection: the selection of the item's cell in ``learned`` ({'unit', 'arm', 'cells'}: the learn-slice unit
        where the current side ran once, ``s<k>/outcomes``, ``-outcomes-card`` or ``-outcomes-archive``), answered with
        no model call (``RecordedSelection``). A side whose mount asks for a selection that the record cannot answer
        the same way (no cell, another offer) mounts no selectable program, and the item counts in
        ``selection_unrecorded``. So the two sides differ in the candidate alone, and the shell's note caps act as in
        a cell (a note over the total cap is skipped whole). Nothing at all is sent or charged (the ledger is never
        opened; no cell record, no infrastructure count, no retry). Per item: ``fired`` (a candidate id in the cell's
        fired list), ``note_chars`` (the candidate request's user text minus the incumbent's; a note is shown when
        above 0; 0 when a side sent no request), the kinds of the shell's faults naming a candidate procedure (e.g.
        timeout). ``routed`` counts the items where the mount applied the candidate; ``not_routed`` lists the others
        (an item the step's type map routes to no type -- about 5 % of a bench's own items lie beyond the p95
        threshold -- or to another type: no version of a program can note there, so they are no failure of it,
        ``_repairable``). ``scope``: what of an item is probed (``PROBE_SCOPES``: ALFWorld's episode ends at its first
        step, SpreadsheetBench runs what precedes the first call, its sheet_feedback is not reached). As a cell unit:
        the memory lock around every solve (``Services.heavy(bench, unit)``), a sandbox worker per solve, the unit
        drained after it (best effort when it raised); a route-B stop raised by the shell pauses the chain with its
        kind. Repeated after an interruption before its record (it sends nothing)."""
        path = self.root / unit / PROBE
        if path.exists():
            return units.read_json(path)
        self.require_records(unit + '/' + PROBE)  # records-only mode (verify_decision): a probe is never run there
        self.current(unit)
        procedures, background = list(procedures), list(background)
        ids = {record['id'] for record in procedures}
        sides = (('F', 'cand_program' if background else 'F', _program_candidate([], home_type, background)),
                 ('cand', 'cand_program', _program_candidate(procedures, home_type, background)))
        vectors, views = self.vectors_of(bench), self.views_of(bench)
        factory = self.s.probe_call or (lambda bench_, unit_, tag_: ProbeCall())
        rows, faults, unsent, failed, unrouted, unrecorded = [], {}, 0, 0, [], 0
        try:
            for item in items:
                chars, found, applied, lost = {}, None, False, False
                recorded = _recorded_selection(learned['cells'].get((item['task_id'], learned['arm'])))
                for side, arm, offered in sides:
                    tag = units.cell_tag(bench, item['task_id'], 'probe-' + side)
                    mounted, missing = self.probe_mount(bench, item, arm, offered, recorded, typemap=typemap,
                                                        library=library, vector=vectors.get(item['task_id']),
                                                        view=views.get(item['task_id']))
                    lost = lost or missing
                    call = factory(bench, unit, tag)
                    with self.s.heavy(bench, unit):  # per solve, as a cell holds it
                        row = self.s.solve_fn(bench, item, mounted, call=call, runtime=self.s.runtime,
                                              worker_factory=self.s.worker_factory(bench, unit, tag), native=self.s.native,
                                              nominal_tokens=self.s.nominal_tokens(bench), unit=unit, tag=tag,
                                              scorer_root=self.root / unit, mode=self.s.mode, step=self.step_label(),
                                              episodes=self.s.episodes)
                    chars[side] = call.requests[0]['user_chars'] if call.requests else None
                    found, applied = row, (mounted.get('candidate') or {}).get('applied') is True
                if not applied:  # the candidate side's mount: the item is routed to no type or another type
                    unrouted.append(item['task_id'])
                unrecorded += lost
                kinds = sorted(str(fault.get('kind') or fault.get('fault') or 'unknown')
                               for fault in (found.get('faults') or []) if fault.get('procedure') in ids)
                for kind in kinds:
                    faults[kind] = faults.get(kind, 0) + 1
                if chars['F'] is None or chars['cand'] is None:
                    unsent += 1
                failed += bool(found.get('failure'))
                note = 0 if chars['F'] is None or chars['cand'] is None else chars['cand'] - chars['F']
                rows.append([item['task_id'], bool(ids & set(found.get('fired') or [])), note, kinds])
        except BaseException as error:
            self.drain(unit, best_effort=True)
            kind = stop_kind(error) if isinstance(error, Exception) else None
            if kind:
                raise Paused(kind, unit, _pause_detail(error)) from None
            raise
        self.drain(unit)
        record = {'unit': unit, 'bench': bench, 'step': k, 'scope': PROBE_SCOPES[bench], 'selection': 'recorded',
                  'learned': learned['unit'], 'selection_unrecorded': unrecorded,
                  'background': [[record['id'], record.get('record_sha256')] for record in background],
                  'procedures': [[record['id'], record.get('record_sha256')] for record in procedures],
                  'items': len(rows), 'routed': len(rows) - len(unrouted), 'fired': sum(1 for row in rows if row[1]),
                  'noted': sum(1 for row in rows if row[2] > 0), 'faults': dict(sorted(faults.items())),
                  'unsent': unsent, 'failed': failed, 'not_routed': unrouted, 'per_item': rows}
        units.write_json(path, record)
        self.mark(unit)
        return record

    def probe_mount(self, bench, item, arm, candidate, recorded, *, typemap, library, vector, view):
        """One probe side's mount (Codex P1 F2): the item's recorded selection answers the selection call
        (``RecordedSelection``, no model call). Returns (mount, missing): ``missing`` when the mount asked for a
        selection that the record could not answer the same way (offered and enabled programs as the cell's); that
        side is then mounted again with no selectable program."""
        kw = dict(arm=arm, typemap=typemap, library=library, vector=vector, candidate=candidate, view=view,
                  base_card=self.base_card)
        selector = RecordedSelection(recorded)
        mounted = self.s.mount_fn(bench, item, selector=selector, **kw)
        if not selector.asked or selector.matches(mounted):
            return mounted, False
        return self.s.mount_fn(bench, item, selector=RecordedSelection(None), **kw), True

    def programs_repair(self, k, bench, tid, learned, incumbent, card_accepted, members=()):
        """``programs`` under the sealed program learning 'repair' (typed-v3, CHAIN-DECISIONS T8, T9).

        The current side is typed-v2's (after an accepted card ``s<k>/outcomes-card``, its gate arm the card's runs).
        Every comparison arm of the step's programs mounts from ``base``, the library and type map before any program
        of the step. T9: when the manifest's archive names this chain and bench, candidate 0 runs first
        (``archive_candidate``, unit ``s<k>/program-0``, gated as one forced package against the current arm).
        Accepted, its procedures join the library (the engineer's index and ``parent`` hold them) and, as its gate arm
        had them forced, they are FORCED in every later comparison arm of the step -- probes, learn cells, gate and
        member arms -- and never offered to a selection call there (Codex P1 F4; ``base`` does not hold them): the
        package's gate arm is the current arm of every later candidate and its member arms the members' baselines,
        as an accepted card's runs become the current arm. The package (forced, from ``base``) then runs once more on
        the learn slice (``archive_outcomes``: ``s<k>/outcomes-archive``, with the shown made items below, and per
        member ``s<k>/member-<b'>-outcomes-archive``), as an accepted card's ``s<k>/outcomes-card`` does, so the
        engineer's examples, its members' examples, the probes' recorded selections, the paid round's fixed / broken
        and the learn report's labels are the post-archive ones (Codex P1 F3). A refused package changes nothing (no
        unit, nothing forced). Across steps and in the reads the library's programs are offered to the selection call,
        as in typed-v2. An engineer program accepted at slot 1 is in no later arm of the step (typed-v2: every slot is
        judged against the same current arm), so nothing of it is forced. Then the engineer's proposals and static
        screen as typed-v2 (``proposals.json``); each slot row runs ``program_repair`` (probe, free repair rounds, one
        paid feedback round, gate) and every unpromoted row gets typed-v2's zero-call decision. Returns typed-v2's
        (decisions, (current unit, its learn cells, its gate arm, the members)): the archive's decision is the first
        row of decisions (``origin`` 'archive'); the current tuple stays the card-or-F side (``finalize`` reports it
        as the outcomes with the card, and the post-archive outcomes under ``program_learning``).

        typed-v3 T6 (item stage 'planned', brief P2b): the probes (the archive package's included), repair reports and
        the paid feedback round run on ``practice`` (the learn items, then the shown made items; the learn slice alone
        under 'none'); the post-archive unit runs on ``practice`` too; and the engineer's examples are the learn
        examples followed by the shown items' (``shown_examples``), both from the current side's cells (after an
        accepted package from ``s<k>/outcomes-archive``)."""
        from . import archives
        learn = self.items(bench, 'learn')
        practice = learn + self.shown_items(bench)
        current_unit = 's%d/outcomes-card' % k if card_accepted else None
        current_learned, current = self.outcomes(k, bench, current_unit) if card_accepted else (learned, incumbent)
        if members and card_accepted:
            members = self.member_outcomes(k, members, card=True)
        decisions, against, judged_members, background = [], current, list(members), []
        # the learn-slice side the writers, the probes' recorded selections, the learn report and the paid round use
        # (T8.4): typed-v2's card-or-F side, or after an accepted archive package that package's (``archive_outcomes``)
        learned_side = {'unit': current_unit or 's%d/outcomes' % k, 'arm': 'F', 'cells': current_learned}
        self.archive_learned = None
        base = (library_.Library(deepcopy(self.library.data)), tasktypes.TypeMap(deepcopy(self.typemap.data)))
        if archives.entry_for(self.archive, self.s.chain, bench) is not None:
            archive, against = self.archive_candidate(k, bench, tid, current, practice, members, base, learned_side)
            decisions.append(archive)
            if archive['accepted']:
                background = archives.load_package(self.archive, self.s.chain, bench)['procedures']
                if members:  # the members' baselines become the package's member runs
                    arms = {check['bench']: self.registered(check['candidate_arm']['unit'])
                            for check in archive.get('members') or []}
                    judged_members = [{**member, 'current': arms.get(member['bench'], member['current'])}
                                      for member in members]
                learned_side, judged_members = self.archive_outcomes(k, bench, tid, practice, judged_members, base,
                                                                     background)
        examples = self.s.outcomes_for_writer([learned_side['cells'][(i['task_id'], learned_side['arm'])] for i in learn
                                               if (i['task_id'], learned_side['arm']) in learned_side['cells']], learn,
                                              bench=bench)
        # typed-v3 T6 ('planned'; else nothing): the shown items' examples from the same side's cells
        examples += self.shown_examples(bench, learned_side['cells'], learned_side['arm'])
        unit = 's%d/programs' % k
        self.current(unit)
        index = [{'name': s['name'], 'kind': s['kind'], 'description': s.get('description') or '', 'home_type': s['home_type']}
                 for s in self.library.active()]

        def propose():
            call = self.role('program_writer', unit, 'writer', WRITER_TOKENS)
            member_kw = ({'members': [{key: row[key] for key in ('bench', 'source', 'examples')}
                                      for row in self.member_examples(judged_members)]} if members else {})
            return self.s.propose_programs(
                bench=bench, runtime=self.s.runtime, skill_index=index, examples=examples,
                hook_view=self.views_of(bench)[self.hook_item(bench, learn)['task_id']],  # B7b: no refused item
                parent=[s['body']['procedure'] for s in self.library.programs(tid)], step=k, call=call,
                max_candidates=self.s.limits['max_program_candidates'], evidence=ROUTE_B_EVIDENCE[self.s.mode],
                base_card=self.base_card, **member_kw)
        proposals = self.record(unit, 'proposals.json', propose)
        self.mark(unit)
        rows = list(proposals or [])
        _check_proposal_rows(rows, self.s.limits['max_program_candidates'])
        for row in rows:  # every engineer candidate mounts from ``base`` with the step's forced background
            if row['slot'] is not None:
                decisions.append(self.program_repair(k, bench, tid, against, practice, row['slot'], row, base,
                                                     judged_members, learned_side, background))
            elif row['status'] in ZERO_CALL_STATUSES:
                decisions.append(self.program_decision(k, bench, tid, against, learn, None, None, row, base,
                                                       judged_members))
        return decisions, (current_unit, current_learned, current, members)

    def program_repair(self, k, bench, tid, incumbent, learn, i, proposal, snapshot, members, learned_side, background):
        """``program`` of one slot row under 'repair': the write-once ``s<k>/program-<i>/decision.json``
        (``repair_decision``); a stored decision registers its gate arm and member arms again in their place, and an
        accepted one adds its skill (typed-v2's rule). ``learned_side``: {'unit', 'arm', 'cells'}, the learn cells the
        probes replay selections from and the paid round compares with; ``background``: the records forced in every
        comparison arm of the slot (``programs_repair``)."""
        unit = 's%d/program-%d' % (k, i)
        self.current(unit)

        def compute():
            return self.repair_decision(k, bench, tid, incumbent, learn, i, unit, proposal, snapshot, members,
                                        learned_side, background)
        stored = (self.root / unit / 'decision.json').exists()
        decision = self.record(unit, 'decision.json', compute)
        self.verify_decision(unit, decision, compute, stored=stored)  # typed-v3 T7 (nothing under typed-v2's options)
        if decision.get('candidate_arm') is not None:
            self.register_stored(unit + '-gate')
            for check in decision.get('members') or []:
                self.register_stored(check['baseline']['unit'])
                self.register_stored(check['candidate_arm']['unit'])
        if decision['accepted']:
            skill = units.read_json(self.root / unit / 'skill.json')['skill']
            self.library.add(skill)
            self.typemap.add_program(tid, skill['skill_id'], step=k)
        return decision

    def repair_decision(self, k, bench, tid, incumbent, learn, i, unit, proposal, snapshot, members, learned_side,
                        background):
        """The decision of slot ``i`` under 'repair' (T8): the free repair rounds (``refine``: the probe of the
        proposal, at most ``program_repair_rounds`` repairs, ``refined.json``), then, unless
        ``program_paid_feedback`` is 0, the one paid feedback round (``learn_round``: the kept version once on the
        learn items, compared with ``learned_side``; a fault or failure there refuses it with ``smoke_fault``, the
        role of typed-v2's smoke; when it broke at least as many items as it fixed, one more repair whose revision
        replaces it only if its probe is not worse), then typed-v2's gate and rule on the version that goes on
        (``cand_program#1..R`` against the incumbent, member checks, describe). Every arm mounts the version with the
        step's forced ``background`` (``_program_candidate``). The record is typed-v2's (no ``smoke`` key) plus
        ``repair`` (rounds, kept version, probe summaries), ``learn`` (the paid round's fixed / broken counts and its
        feedback repair, or None) and ``procedure_sha256`` (the version gated); with a background its
        ``mount_snapshot`` also names the forced records (``forced``)."""
        library, typemap = snapshot
        procedure, screen = proposal.get('procedure'), proposal.get('screen') or {}
        base = {'kind': 'program', 'candidate': i, 'unit': unit, 'proposal': proposal.get('n'),
                'status': proposal.get('status'), 'procedure_id': (procedure or {}).get('id'),
                'request_sha256': proposal.get('request_sha256'), 'screen': screen,
                'mount_snapshot': {'library': [s['skill_id'] for s in library.active()], 'typemap_step': typemap.data.get('step'),
                                   **({'forced': [record['id'] for record in background]} if background else {})}}

        def unchecked(found):  # a record that never reached the member checks (D16: shared fields, no check)
            return {**found, **self.shared(found, [], members)} if members else found
        if not isinstance(procedure, dict) or not screen.get('passed'):
            return unchecked({**base, 'accepted': False, 'reason': _unpromoted_reason(proposal)})
        refined = self.record(unit, REFINED, lambda: self.refine(k, bench, tid, i, procedure, learn, snapshot,
                                                                 learned_side, background))
        repair = {'unit': unit + '/' + REFINED, 'rounds': refined['rounds'], 'limit': refined['limit'],
                  'kept_round': refined['round'], 'stop': refined['stop'],
                  'probes': [row['probe'] for row in refined['history']]}
        version, learned_round = refined['procedure'], None
        if self.repair_limit('program_paid_feedback') > 0:
            paid = self.learn_round(k, bench, tid, i, refined, learn, snapshot, learned_side, background)
            learned_round = paid['summary']
            if paid['smoke_fault']:
                return unchecked({**base, 'accepted': False, 'reason': 'smoke_fault', 'repair': repair,
                                  'learn': learned_round, 'procedure_sha256': version.get('record_sha256')})
            version = paid['procedure']
        candidate = _program_candidate([version], tid, background)
        pid = version.get('id')
        # typed-v3 T7: the screen of the version that goes on, mounted as its gate arm (the step's forced background
        # included), before the gate; refused there, no gate runs
        screen = self.screen(unit, bench, 'cand_program', candidate, incumbent, typemap=typemap, library=library,
                             procedures=[pid])
        if screen is not None and not screen['passed']:
            return unchecked({**base, 'accepted': False, 'reason': screen['reason'], 'repair': repair,
                              'learn': learned_round, 'procedure_sha256': version.get('record_sha256'),
                              'screen_run': screen, 'cells': 0})
        arm = self.gate_arm(unit + '-gate', bench, 'cand_program', candidate=candidate, typemap=typemap,
                            library=library)
        fired = {item_id: sum(pid in ((arm['cells'].get((item_id, label)) or {}).get('fired') or [])
                              for label in arm['labels']) for item_id in arm['items']}
        decision = {**base, **self.compare('program', incumbent, arm, fired_cells=fired), 'repair': repair,
                    'learn': learned_round, 'procedure_sha256': version.get('record_sha256'),
                    **({'screen_run': screen} if screen is not None else {})}
        if members:  # addendum D16 (b): the home rule AND no_regress on every member bench
            checks = (self.member_checks(unit, 'cand_program', candidate, members,
                                         lambda member: member['current'] or self.member_base(
                                             k, member, typemap=typemap, library=library),
                                         typemap=typemap, library=library) if decision['accepted'] else [])
            decision.update(self.shared(decision, checks, members))
        if decision['accepted']:
            made = self.record(unit, 'skill.json', lambda: self.make_skill('program', tid, k, bench, unit,
                                                                           {'procedure': version}, decision))
            if not made['skill'].get('description'):
                decision = {**decision, 'accepted': False, 'reason': 'description_failed', 'description': made['description'],
                            'gate_verdict': {'accepted': decision['accepted'], 'reason': decision['reason']}}
        return decision

    def refine(self, k, bench, tid, i, procedure, learn, snapshot, learned_side, background):
        """T8.3, the free repair rounds of slot ``i`` (the compute of ``s<k>/program-<i>/refined.json``). Version 0 is
        the screened proposal, probed in ``s<k>/program-<i>-probe-0``. Round r (at most ``program_repair_rounds``;
        none when the kept version left nothing to repair: every routed item noted, no fault) is one repair call in
        ``s<k>/program-<i>-repair-<r>`` (``repair_round``); a revision that strictly improves the kept version's
        probe -- more noted items, or as many with fewer faults -- is kept and the next round follows; any other
        round (no improvement, the same program, a revision the screen refused, an unreadable reply, no reply) ends
        the repair with the kept version. Every round's records are write-once, so a resumed step repeats no call
        whose record exists. Returns {'slot', 'round' (of the kept version), 'procedure' (its record), 'probe' (its
        summary), 'history' [per version tried: round, status, procedure hash, probe summary, kept], 'stop',
        'rounds' (repair calls made), 'limit'}."""
        library, typemap = snapshot
        limit = self.repair_limit('program_repair_rounds')
        unit_of = lambda r: 's%d/program-%d-probe-%s' % (k, i, r)
        first = self.probe(k, bench, unit_of(0), [procedure], learn, home_type=tid, typemap=typemap, library=library,
                           learned=learned_side, background=background)
        kept = {'round': 0, 'procedure': procedure, 'probe': first}
        history = [{'round': 0, 'status': 'proposal', 'procedure_sha256': procedure.get('record_sha256'),
                    'probe': _probe_summary(first), 'kept': True}]
        stop, made = 'round_limit', 0
        for r in range(1, limit + 1):
            if not _repairable(kept['probe']):
                stop = 'nothing_to_repair'
                break
            made += 1
            found = self.repair_round(k, bench, tid, i, 's%d/program-%d-repair-%d' % (k, i, r), unit_of(r), kept, learn,
                                      snapshot, learned_side, background)
            history.append({'round': r, 'status': found['status'], 'procedure_sha256': found['procedure_sha256'],
                            'probe': found['probe'], 'kept': found['kept']})
            if not found['kept']:
                stop = found['stop']
                break
            kept = {'round': r, 'procedure': found['procedure'],
                    'probe': units.read_json(self.root / unit_of(r) / PROBE)}
        return {'slot': i, 'round': kept['round'], 'procedure': kept['procedure'], 'probe': _probe_summary(kept['probe']),
                'history': history, 'stop': stop, 'rounds': made, 'limit': limit}

    def repair_round(self, k, bench, tid, i, unit, probe_unit, kept, learn, snapshot, learned_side, background, *,
                     report=None, rule='better'):
        """One repair round (T8.3; T8.4's feedback round with ``report`` and ``rule`` 'not_worse'): the repair call,
        write-once ``<unit>/writer.json`` (``Services.repair_program`` with the kept version, its coverage report and
        the learn report; a resumed call keeps the earlier sends of its calls file and replays their completed
        receipts, ``role``), the probe of a revision in ``probe_unit``, then the write-once round record
        ``<unit>/repair.json`` {round unit, request hash, status, reason, reading, format retry, screen, the revision's
        hash, the probe summary, ``kept``, ``stop``}. ``kept``: 'better' -- the revision's probe strictly improves the
        kept version's (more noted items, or as many with fewer faults); 'not_worse' -- it is at least as good on the
        same order. Returns the round record with the revised procedure record under ``procedure`` (None unless a
        revision)."""
        from . import writers
        library, typemap = snapshot
        views, write = self.views_of(bench), self.s.repair_program or writers.repair_program

        def call():
            role = self.role('program_writer', unit, 'writer', WRITER_TOKENS)
            # B7b: a refused practice item counts in its class, its text is never listed (``refused_ids``)
            coverage = writers.coverage_report(kept['probe'], learn, views, exclude=self.refused_ids(bench))
            return write(bench=bench, procedure=kept['procedure'], coverage=coverage,
                         call=role, evidence=ROUTE_B_EVIDENCE[self.s.mode],
                         **({'learn': report} if report is not None else {}))
        self.current(unit)
        written = self.record(unit, WRITER_RECORD, call)
        revised = written.get('procedure') if written.get('status') == 'revised' else None
        probe = (self.probe(k, bench, probe_unit, [revised], learn, home_type=tid, typemap=typemap, library=library,
                            learned=learned_side, background=background) if revised is not None else None)

        def decide():
            kept_ = False
            if probe is not None:
                new, old = _probe_key(probe), _probe_key(kept['probe'])
                kept_ = new > old if rule == 'better' else new >= old
            stop = None if kept_ else ('no_improvement' if probe is not None else
                                       'screen' if written['status'] == 'dropped_screen' else written['status'])
            return {'unit': unit, 'request_sha256': written.get('request_sha256'), 'status': written.get('status'),
                    'reason': written.get('reason'), 'read': written.get('read'), 'format_retry': written.get('format_retry'),
                    'screen': written.get('screen'), 'procedure_sha256': (revised or {}).get('record_sha256'),
                    'probe_unit': probe_unit if probe is not None else None,
                    'probe': _probe_summary(probe) if probe is not None else None, 'rule': rule, 'kept': kept_,
                    'stop': stop}
        found = self.record(unit, REPAIR_RECORD, decide)
        self.mark(unit)
        return {**found, 'procedure': revised}

    def learn_round(self, k, bench, tid, i, refined, learn, snapshot, learned_side, background):
        """T8.4, the one paid feedback round of slot ``i``: the kept version once on the learn items
        (``s<k>/program-<i>-learn``, arm cand_program through ``cells``, mounted from the gate's snapshot with the
        step's forced ``background``), compared per item with the current side's learn attempts (``learned_side``:
        {'unit', 'arm', 'cells'}, what the writers saw: ``s<k>/outcomes``, ``-outcomes-card`` or, after an accepted
        archive package, ``-outcomes-archive``; the summary names it as ``against``): ``fixed`` (the current side
        wrong, the version right), ``broken`` (the current side right, the version wrong); an unknown on either side
        counts in neither. A fault, failure or configuration error in these cells is typed-v2's smoke fault (the
        version is refused before any other call). Else, when ``broken >= fixed`` and ``fixed + broken > 0``: one more
        repair (``s<k>/program-<i>-feedback``, its revision probed in ``s<k>/program-<i>-probe-feedback``) showing the
        broken items, whose revision replaces the version only if its probe is not worse. No second paid round.
        Returns {'summary', 'procedure' (the version that goes on), 'smoke_fault'}."""
        library, typemap = snapshot
        unit, version = 's%d/program-%d-learn' % (k, i), refined['procedure']
        cells = self.cells(unit, bench, [(bench, item, ('cand_program',)) for item in learn],
                           candidate=_program_candidate([version], tid, background), typemap=typemap, library=library)
        faults = [{'item_id': item_id, 'faults': row.get('faults'), 'failure': row.get('failure'),
                   'configuration_error': bool(row.get('configuration_error'))} for (item_id, _), row in sorted(cells.items())
                  if row.get('faults') or row.get('failure') or row.get('configuration_error')]
        fixed, broken = [], []
        for item in learn:
            before = _correct(learned_side['cells'], item['task_id'], learned_side['arm'])
            after = _correct(cells, item['task_id'], 'cand_program')
            if before is False and after is True:
                fixed.append(item['task_id'])
            elif before is True and after is False:
                broken.append(item['task_id'])
        summary = {'unit': unit, 'against': learned_side['unit'], 'items': len(learn), 'cells': len(cells),
                   'fixed': len(fixed), 'broken': len(broken), 'faults': faults,
                   'procedure_sha256': version.get('record_sha256'), 'feedback': None}
        if faults:
            return {'summary': summary, 'procedure': version, 'smoke_fault': True}
        if broken and len(broken) >= len(fixed):
            from . import writers
            kept = {'round': refined['round'], 'procedure': version,
                    'probe': units.read_json(self.root / refined['probe']['unit'] / PROBE)}
            report = writers.learn_report(fixed, broken, learn, self.views_of(bench))
            found = self.repair_round(k, bench, tid, i, 's%d/program-%d-feedback' % (k, i),
                                      's%d/program-%d-probe-feedback' % (k, i), kept, learn, snapshot, learned_side,
                                      background, report=report, rule='not_worse')
            summary['feedback'] = {key: found[key] for key in ('unit', 'status', 'reason', 'procedure_sha256', 'probe',
                                                               'kept', 'stop')}
            if found['kept']:
                version = found['procedure']
        return {'summary': summary, 'procedure': version, 'smoke_fault': False}

    def archive_outcomes(self, k, bench, tid, practice, members, base, background):
        """Codex P1 F3, T9 with T8.4: after an ACCEPTED archive package, the package's arm once on the step's practice
        items -- cand_program with every record forced, from ``base`` (the state before it, where it is never offered),
        as its gate arm ran -- ``s<k>/outcomes-archive``, as an accepted card's ``s<k>/outcomes-card`` replaces F's
        attempts for every later writer; for a shared type (addendum D16) the same arm once on each member's learn slice
        (``s<k>/member-<b'>-outcomes-archive``: forced on the member items routed into the home type, the member's own
        mount elsewhere). ``practice``: the learn items, then under the item stage 'planned' the step's shown made items
        (brief P2b: every outcomes unit of the step holds them, as ``outcomes`` does; a member bench has none). From
        here the engineer's examples (the shown items' and its members' too), the probes' recorded selections, the paid
        round's fixed / broken and the learn report's labels are these post-archive outcomes, against which every later
        candidate (mounted from ``base`` with the same records forced) differs in itself alone. Single-run cells
        through ``cells`` (write-once; a resumed unit runs only its missing cells): no gate arm, the later candidates'
        gate baseline is the package's gate arm (on J). Returns ({'unit', 'arm', 'cells'}, the members with their
        post-archive ``unit``, ``learned`` and ``learned_arm``); keeps both for ``finalize`` (``archive_learned``)."""
        library, typemap = base
        candidate, arm = _program_candidate([], tid, background), 'cand_program'
        unit = 's%d/outcomes-archive' % k
        cells = self.cells(unit, bench, [(bench, item, (arm,)) for item in practice], candidate=candidate,
                           typemap=typemap, library=library)
        out = []
        for member in members:
            member_unit = 's%d/member-%s-outcomes-archive' % (k, member['bench'])
            jobs = [(member['bench'], item, (arm,))
                    for item in self.items(member['bench'], 'learn') + self.shown_items(member['bench'])]
            out.append({**member, 'unit': member_unit, 'learned_arm': arm,
                        'learned': self.cells(member_unit, member['bench'], jobs, candidate=candidate, typemap=typemap,
                                              library=library)})
        self.archive_learned = {'unit': unit, 'arm': arm, 'cells': cells,
                                'members': [(row['bench'], row['unit'], row['learned']) for row in out]}
        return {'unit': unit, 'arm': arm, 'cells': cells}, out

    def archive_candidate(self, k, bench, tid, current, learn, members, base, learned_side):
        """T9: the sealed archive package of this chain and bench as candidate 0 of the step's programs, unit
        ``s<k>/program-0`` with its write-once ``decision.json`` (``archive_decision``, mounted from ``base``). A
        stored decision registers its gate arm and member arms again in their place. Accepted: every procedure joins
        the library as a program skill of the type (``skills.json``, in package order) and the package's gate arm
        becomes the current arm of every later candidate of the step. Returns (decision, the current arm for the later
        candidates)."""
        unit = 's%d/program-0' % k
        self.current(unit)

        def compute():
            return self.archive_decision(k, bench, tid, current, learn, members, unit, base, learned_side)
        stored = (self.root / unit / 'decision.json').exists()
        decision = self.record(unit, 'decision.json', compute)
        self.verify_decision(unit, decision, compute, stored=stored)  # typed-v3 T7 (nothing under typed-v2's options)
        if decision.get('candidate_arm') is not None:
            self.register_stored(unit + '-gate')
            for check in decision.get('members') or []:
                self.register_stored(check['baseline']['unit'])
                self.register_stored(check['candidate_arm']['unit'])
        if decision['accepted']:
            for skill in units.read_json(self.root / unit / ARCHIVE_SKILLS)['skills']:
                self.library.add(skill)
                self.typemap.add_program(tid, skill['skill_id'], step=k)
            current = self.registered(unit + '-gate')
        return decision, current

    def archive_decision(self, k, bench, tid, incumbent, learn, members, unit, base, learned_side):
        """The decision of the archive package (T9). The records come through the verified loader
        (``archives.load_package``: index pin, file bytes, record hashes). Each is screened by the typed static
        screen as a new program's source is (``writers.screen_record``); one failure refuses the WHOLE package
        (``archive_screen``, every record's screen with its evidence; nothing is fixed, no call). Then the zero-call
        probe of the package on the learn items (``s<k>/program-0-probe-0``, recorded; selections replayed from
        ``learned_side``), and the gate: the package as ONE candidate, every procedure forced together
        (``{'procedures': [...]}``), ``cand_program#1..R`` against the step's current arm, mounted from ``base`` (the
        state before it); an item is fired when any procedure of the package fired; the program rule decides
        (``compare('program', ...)``), member checks as for a program. Accepted: every procedure is described as an
        accepted program is (one ``make_skill`` each, origin ``kind`` 'archive' with the package and the archived
        record hash; ``skill-<n>.json`` each, then ``skills.json``, all write-once: ``archive_skills``); a description
        that never parses refuses the package with ``description_failed`` (the gate's verdict kept), as for a program.
        The record is a program row (``kind`` 'program', ``origin`` 'archive', ``candidate`` 0) with the package, its
        procedures, the screens and the probe summary."""
        from . import archives, writers
        package = archives.load_package(self.archive, self.s.chain, bench)
        records = package['procedures']
        library, typemap = base
        record_base = {'kind': 'program', 'origin': 'archive', 'candidate': 0, 'unit': unit, 'package': package['package'],
                       'procedure_ids': [record['id'] for record in records],
                       'procedure_sha256': [record['record_sha256'] for record in records],
                       'mount_snapshot': {'library': [s['skill_id'] for s in library.active()],
                                          'typemap_step': typemap.data.get('step')}}

        def unchecked(found):
            return {**found, **self.shared(found, [], members)} if members else found
        screens = [{'id': record['id'], **writers.screen_record(record, bench)} for record in records]
        if not all(row['passed'] for row in screens):
            return unchecked({**record_base, 'accepted': False, 'reason': 'archive_screen', 'screen': screens})
        candidate = {'procedures': records, 'home_type': tid}
        probe = self.probe(k, bench, 's%d/program-0-probe-0' % k, records, learn, home_type=tid, typemap=typemap,
                           library=library, learned=learned_side)
        # typed-v3 T7: the package's screen (any of its procedures firing counts), before its gate; refused there, no
        # gate runs and nothing of the package is applied
        screen = self.screen(unit, bench, 'cand_program', candidate, incumbent, typemap=typemap, library=library,
                             procedures=record_base['procedure_ids'])
        if screen is not None and not screen['passed']:
            return unchecked({**record_base, 'accepted': False, 'reason': screen['reason'], 'screen': screens,
                              'probe': _probe_summary(probe), 'screen_run': screen, 'cells': 0})
        arm = self.gate_arm(unit + '-gate', bench, 'cand_program', candidate=candidate, typemap=typemap, library=library)
        ids = set(record_base['procedure_ids'])
        fired = {item_id: sum(bool(ids & set((arm['cells'].get((item_id, label)) or {}).get('fired') or []))
                              for label in arm['labels']) for item_id in arm['items']}
        decision = {**record_base, **self.compare('program', incumbent, arm, fired_cells=fired), 'screen': screens,
                    'probe': _probe_summary(probe), **({'screen_run': screen} if screen is not None else {})}
        if members:
            checks = (self.member_checks(unit, 'cand_program', candidate, members,
                                         lambda member: member['current'] or self.member_base(
                                             k, member, typemap=typemap, library=library),
                                         typemap=typemap, library=library) if decision['accepted'] else [])
            decision.update(self.shared(decision, checks, members))
        if decision['accepted']:
            made = self.record(unit, ARCHIVE_SKILLS, lambda: self.archive_skills(k, bench, tid, unit, package, decision))
            if not all(skill.get('description') for skill in made['skills']):
                decision = {**decision, 'accepted': False, 'reason': 'description_failed',
                            'description': made['descriptions'],
                            'gate_verdict': {'accepted': decision['accepted'], 'reason': decision['reason']}}
        return decision

    def archive_skills(self, k, bench, tid, unit, package, decision):
        """The described program skills of an accepted archive package, in package order (one id and name each,
        drawn one after the other on a scratch copy of the library): {'skills': [...], 'descriptions': [...]}. Each
        described skill is its own write-once record ``<unit>/skill-<n>.json`` (n = 1.. in package order), so a step
        interrupted between two describer calls repeats neither a finished call nor an id draw (a stored skill joins
        the scratch library again before the next id is drawn)."""
        scratch, skills, descriptions = library_.Library(deepcopy(self.library.data)), [], []
        for n, record in enumerate(package['procedures'], 1):
            made = self.record(unit, 'skill-%d.json' % n, lambda record=record: self.make_skill(
                'program', tid, k, bench, unit, {'procedure': record}, decision, library=scratch,
                origin={'kind': 'archive', 'package': package['package'],
                        'archive_record_sha256': record['record_sha256']}))
            scratch.add(made['skill'])
            skills.append(made['skill'])
            descriptions.append(made['description'])
        return {'package': package['package'], 'skills': skills, 'descriptions': descriptions}

    def finalize(self, k, bench, noise, typing, outcomes, rounds, programs, current, members=()):
        """decisions.json with every denominator, then the frozen library and type map of the step. ``outcomes``:
        (learn cells of ``s<k>/outcomes``, its F gate arm); ``current``: (the card-mounted unit or None, its learn
        cells, its gate arm, the members after the card). Gate counts are runs (n * R) and name the unit and arm that
        hold them; ``gate`` lists every gate arm of the step with its sharing (DESIGN 3.4, spec/gate.md 3.2). A shared
        type (addendum D16) adds ``shared_type``: the member benches with their sources, whether each is a source or a
        routed member and how many of its gate items route into the home type (RP15), and their learn-slice
        denominators (``s<k>/member-<b'>-outcomes`` and, after an accepted card, ``-outcomes-card`` with its gate runs)."""
        unit = self.root / ('s%d' % k)
        learn = self.items(bench, 'learn')
        (learned, incumbent), (current_unit, current_learned, current_arm, after) = outcomes, current
        with_card = None
        if current_unit is not None:  # the card-mounted outcomes every program of the step was judged against
            with_card = {'unit': current_unit, 'learn': _outcome_counts(current_learned, learn),
                         'gate': _run_counts(current_arm)}
        decisions = {'version': VERSION, 'chain': self.s.chain, 'mode': self.s.mode, 'evidence': EVIDENCE[self.s.mode],
                     'step': k, 'bench': bench, 'tau_points': noise['tau_points'], 'noise': noise, 'typing': typing,
                     'outcomes': {'learn': _outcome_counts(learned, learn), 'gate': _run_counts(incumbent)},
                     'outcomes_with_card': with_card, 'program_gate_current': current_unit or 's%d/outcomes' % k,
                     'gate': {'repeats': self.repeats(), 'arms': [_arm_ref(q) for q in self.gate_arms]},
                     'cards': rounds, 'programs': programs, 'limits': dict(self.s.limits),
                     'library': self.library.summary(), 'typemap': self.typemap.summary(),
                     'ledger': dict(self.state.get('ledger') or {}), 'at': _now()}
        if self.program_learning == 'repair':  # typed-v3 T8, T9 (a typed-v2 style step writes no such key)
            archive = next((row for row in programs if row.get('origin') == 'archive'), None)
            decisions['program_learning'] = {
                'mode': 'repair', 'limits': {key: self.repair_limit(key) for key in REPAIR_LIMITS},
                'archive': None if archive is None else {key: archive.get(key) for key in (
                    'unit', 'package', 'procedure_ids', 'accepted', 'reason')},
                'engineer_gate_current': ('s%d/program-0-gate' % k if archive is not None and archive['accepted']
                                          else current_unit or 's%d/outcomes' % k),
                # the learn side the engineer, the learn report and the paid rounds used after an accepted package
                'outcomes_with_archive': None if self.archive_learned is None else {
                    'unit': self.archive_learned['unit'], 'arm': self.archive_learned['arm'],
                    'learn': _outcome_counts(self.archive_learned['cells'], learn, arm=self.archive_learned['arm']),
                    'members': [{'bench': member, 'unit': name,
                                 'learn': _outcome_counts(cells, self.items(member, 'learn'), arm=self.archive_learned['arm'])}
                                for member, name, cells in self.archive_learned['members']]}}
        if self.item_stage != ITEM_STAGE_DEFAULT:  # typed-v3 T3 to T7 (brief P2b): the items block and by_class
            from . import itemstage
            itemstage.add_to_decisions(self, k, bench, decisions)
        if self.gate_rule != GATE_RULE_DEFAULT or self.gate_screen:  # typed-v3 T7 (brief P3b): the step's rules
            decisions['gate_rule'] = self.gate_rule_block(bench)
        if members:
            carded = {row['bench']: row for row in after if row['current'] is not None}
            decisions['shared_type'] = [
                {'bench': row['bench'], 'source': row['source'], 'member': row['member'],
                 'routed_gate_items': row['routed_gate_items'], 'outcomes': {
                    'unit': row['unit'], 'learn': _outcome_counts(row['learned'], self.items(row['bench'], 'learn'))},
                 'outcomes_with_card': None if row['bench'] not in carded else {
                     'unit': carded[row['bench']]['unit'],
                     'learn': _outcome_counts(carded[row['bench']]['learned'], self.items(row['bench'], 'learn')),
                     'gate': _run_counts(carded[row['bench']]['current'])}}
                for row in members]
        if not (unit / 'decisions.json').exists():
            units.write_json(unit / 'decisions.json', decisions)
        if not (unit / 'library.json').exists():
            self.library.save(unit / 'library.json', step=k)
        if not (unit / 'typemap.json').exists():
            self.typemap.freeze(unit / 'typemap.json', step=k)
        self.freeze(k, bench)  # the receipt, from the files on disk (DESIGN 3.6)


def _sealed(fields):
    """A write-once chain record: the fields plus ``record_sha256`` of their canonical JSON."""
    require(isinstance(fields, dict) and 'record_sha256' not in fields, 'Fields without a record hash')
    return {**fields, 'record_sha256': library_.canonical_sha256(fields)}


def _file_sha256(path):
    """sha256 of a file's bytes, None when it cannot be read."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _frozen_hashes(step_dir):
    """The four hashes of a receipt from the frozen files of ``step_dir`` as they are on disk: each file read once
    (its sha256 and its stored ``record_sha256``), then loaded by its own loader (record hash and version checked),
    whose record must be the one read. None when anything is missing or differs."""
    found = {}
    for part, loader, record_of in (('library', library_.Library.load, library_.canonical_sha256),
                                    ('typemap', tasktypes.TypeMap.load, tasktypes._sha)):
        path = Path(step_dir) / (part + '.json')
        try:
            raw = path.read_bytes()
            stored = json.loads(raw.decode('utf-8')).get('record_sha256')
            loaded = loader(path)
        except (OSError, ValueError, AttributeError):
            return None
        if not isinstance(stored, str) or record_of(loaded.data) != stored:
            return None
        found[part + '_record_sha256'], found[part + '_file_sha256'] = stored, hashlib.sha256(raw).hexdigest()
    return {key: found[key] for key in ('library_record_sha256', 'typemap_record_sha256', 'library_file_sha256',
                                        'typemap_file_sha256')}


def _receipt_valid(receipt, *, chain, step):
    """A receipt of this version, chain and step with exactly ``FROZEN_KEYS``, hex hashes and its own record hash."""
    if not isinstance(receipt, dict) or set(receipt) != set(FROZEN_KEYS):
        return False
    hashes = [receipt[key] for key in FROZEN_KEYS if key.endswith('_sha256')]
    if not all(isinstance(value, str) and readplan.HEX64.match(value) for value in hashes):
        return False
    fields = {key: value for key, value in receipt.items() if key != 'record_sha256'}
    return (receipt['version'] == VERSION and receipt['chain'] == chain and receipt['step'] == step
            and library_.canonical_sha256(fields) == receipt['record_sha256'])


def _digest(value):
    """sha256 of a value's canonical JSON (sorted keys): the per-item identity digest of a gate arm's plan."""
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def _arm_ref(entry):
    """Where a decision's arm is: its unit, its arm and the arm whose runs it shares (None for its own runs)."""
    return {'unit': entry['unit'], 'arm': entry['arm'], 'shared_from': entry['shared_from']}


def _gate_entry(plan, own, *, source=None, runs=None, reruns=0):
    """A registered gate arm: its plan fields, the cells this unit ran (``unit_cells``, learn cells included) and
    where its R runs per item are (``run_unit`` / ``run_arm`` / ``labels`` / ``cells``: its own, or the source arm's
    when it is shared; ``cells_run`` the gate cells this unit ran for it)."""
    entry = {'unit': plan['unit'], 'arm': plan['arm'], 'bench': plan['bench'], 'items': list(plan['items']),
             'repeats': plan['repeats'], 'identities': plan['identities'], 'shared_from': plan['shared_from'],
             'unit_cells': own}
    if source is not None:
        entry.update({key: source[key] for key in ('labels', 'cells', 'runs', 'reruns', 'run_unit', 'run_arm')})
        entry['cells_run'] = 0
    else:
        labels = list(plan['labels'])
        entry.update(labels=labels, cells={key: row for key, row in own.items() if key[1] in labels}, runs=runs,
                     reruns=reruns, run_unit=plan['unit'], run_arm=plan['arm'],
                     cells_run=len(plan['items']) * plan['repeats'])
    return entry


def _run_counts(entry):
    """Gate-side denominators of one arm: items, runs (n * R), correct / wrong / model-side unknown runs, and the
    unit and arm that hold the runs (a shared arm names its source)."""
    n, R = len(entry['items']), entry['repeats']
    correct, unknown = sum(entry['runs']['sums'].values()), entry['runs']['unknown']
    return {'items': n, 'cells': n * R, 'repeats': R, 'pass': correct, 'fail': n * R - correct - unknown,
            'unknown': unknown, 'source': {'unit': entry['run_unit'], 'arm': entry['run_arm']}}


def _comparable(record):
    """A decision as canonical JSON (tuples as lists, the record as stored), with a smoke's fault list in a fixed
    order: ``program_decision`` lists the faults in the order its smoke cells came back, which a resumed unit's
    stored cells do not keep (``verify_decision``)."""
    found = json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True))
    smoke = found.get('smoke') if isinstance(found, dict) else None
    if isinstance(smoke, dict) and isinstance(smoke.get('faults'), list):
        smoke['faults'] = sorted(smoke['faults'], key=lambda row: json.dumps(row, sort_keys=True))
    return found


DECISION_DIFFERENCES = ('screen_differs', 'evolution_items', 'stage', 'gate_differs', 'not_reproduced')


def decision_difference(stored, expected):
    """None when the stored decision equals the one the chain's records give (``verify_decision``; canonical JSON,
    ``_comparable``), else the first part that differs, in ``DECISION_DIFFERENCES`` order: the screen record
    (present or not), the ids of E, the stage (verdict, reason, whether a gate ran), the gate (rows, arms, evolution
    block), any other field."""
    if not isinstance(stored, dict):
        return 'not_reproduced'
    a, b = _comparable(stored), _comparable(expected)
    if a == b:
        return None
    if ('screen_run' in a, a.get('screen_run')) != ('screen_run' in b, b.get('screen_run')):
        return 'screen_differs'
    if (a.get('evolution') or {}).get('item_ids') != (b.get('evolution') or {}).get('item_ids'):
        return 'evolution_items'
    if (a.get('accepted'), a.get('reason'), 'per_item' in a) != (b.get('accepted'), b.get('reason'), 'per_item' in b):
        return 'stage'
    if any(a.get(key) != b.get(key) for key in ('per_item', 'baseline', 'candidate_arm', 'evolution', 'fired_cells')):
        return 'gate_differs'
    return 'not_reproduced'


def recompute_decision(record):
    """``gates.recompute`` of a stored decision of this chain (card round, program with a gate, no-harm check, noise
    record). Returns the recomputed record, equal to the stored one iff the stored decision is reproduced (Codex
    review round 2, finding 1). Where the chain overrode the gate after it (a gate-accepted program whose description
    failed: ``accepted`` False, ``reason`` 'description_failed', the gate's own verdict in ``gate_verdict``), the gate
    is recomputed from the record with that verdict, its fresh verdict goes back into ``gate_verdict``, and the stored
    override is carried forward only when it is the one legal override: the recomputed gate accepted and the stored
    final decision is a rejection for ``description_failed``.

    typed-v3 T7 (brief P3b): a decision's screen record (``screen_run``) is rebuilt by ``gates.recompute`` (its verdict
    and pass rates from b, c, R, the item count and fired). A decision refused at its screen ran no gate (no
    ``per_item``: ``gates.recompute`` cannot rebuild it, review of P3a point 7): it is rebuilt as that refusal --
    ``accepted`` False with the recomputed screen's reason -- and only a screen that did not pass can refuse; any
    other decision gets its gate rebuilt as below and its screen record beside it. An evolution card is rebuilt by
    ``gates.recompute`` from its per_item rows and the stored ids of E (consistency only: that E is R + A of the
    step's sealed items is the chain's check, ``_Run.verify_decision``)."""
    screen = record.get('screen_run') if isinstance(record, dict) else None
    if screen is not None:
        require(isinstance(screen, dict) and screen.get('kind') == 'screen', 'A screen record (kind screen)')
        fresh = gates.recompute(screen)
        if 'per_item' not in record:  # refused at the screen: no gate ran
            require(fresh['passed'] is False, 'A decision without a gate was refused at its screen')
            return {**record, 'screen_run': fresh, 'accepted': False, 'reason': fresh['reason']}
        return {**_recompute_gate_decision(record), 'screen_run': fresh}
    return _recompute_gate_decision(record)


def _recompute_gate_decision(record):
    """``recompute_decision`` of a decision's gate (typed-v2's rules, the description override included)."""
    verdict = record.get('gate_verdict') if isinstance(record, dict) else None
    if not verdict:
        return gates.recompute(record)
    gate = gates.recompute({**record, **verdict})
    fresh = {'accepted': gate['accepted'], 'reason': gate['reason']}
    if not (gate['accepted'] is True and record.get('accepted') is False and record.get('reason') == 'description_failed'):
        return {**gate, 'gate_verdict': fresh}   # an override the gate does not allow is never reproduced
    return {**gate, 'accepted': False, 'reason': 'description_failed', 'gate_verdict': fresh}


def _base_card(services):
    """The manifest's sealed base card (addendum D17; ``prepare.base_card_of``: refused unless one of BASE_CARDS)."""
    from . import prepare
    return prepare.base_card_of(services.manifest)


def _read_plan(services):
    """The manifest's sealed read plan (read-plan R3; ``prepare.read_plan_of``: refused unless one of READ_PLANS
    and allowed with the sealed schedule)."""
    from . import prepare
    return prepare.read_plan_of(services.manifest)


def _program_learning(services):
    """The manifest's sealed program learning (typed-v3 T8; ``prepare.program_learning_of``: 'single', typed-v2's
    flow, when the manifest has none; refused unless one of PROGRAM_LEARNING)."""
    from . import prepare
    return prepare.program_learning_of(services.manifest)


def _resume_replay(services):
    """The manifest's sealed resume replay (typed-v3 B6 d; ``prepare.resume_replay_of``: 'off', typed-v2's resume, when
    the manifest has none; refused unless one of RESUME_REPLAYS)."""
    from . import prepare
    return prepare.resume_replay_of(services.manifest)


def _durable_receipts(root, chain_dir, manifest):
    """The ledger's ``durable`` under the resume replay 'on': the receipts of pending calls found in the calls files
    of their units (``units.durable_receipts``). A sealed read unit (``test-read-<event>-<bench>``) is opened only
    after its read's own checks pass (``reads.unit_gate``: the canonical unit of an event the root seals, the owner's
    consent naming exactly the planned events; Codex's second look at the replay, point 1) and then sealed, as its
    recorders open it; when they fail nothing of it is opened and its pending calls go to the ordinary recovery --
    the read itself then pauses as it would without the reconciliation. The smoke's practice reads and the learning
    units are open."""
    from . import reads

    def opens(unit):
        if not unit.startswith(READ_UNIT_PREFIXES[0]):
            return False
        try:
            reads.unit_gate(root, unit, manifest=manifest)
        except Exception:  # noqa: BLE001 -- any refusal of the read's checks keeps the sealed unit closed
            return None
        return True
    return lambda pending: units.durable_receipts(chain_dir, pending, opens=opens)


def _read_anchors(services):
    """The manifest's sealed read anchors (typed-v3 T2; ``prepare.read_anchors_of``: typed-v2's ('C0', 'C') when the
    manifest has none; ('C',) only with 'full' and 'historical'; refused otherwise)."""
    from . import prepare
    return prepare.read_anchors_of(services.manifest)


def _gate_rule(services):
    """The manifest's sealed gate rule (typed-v3 T7, brief P3b; ``prepare.gate_rule_of``: 'whole', typed-v2's rules,
    when the manifest has none; 'evolution' only with the item stage 'planned'; refused otherwise)."""
    from . import prepare
    return prepare.gate_rule_of(services.manifest)


def _gate_screen(services):
    """The manifest's sealed screen switch (typed-v3 T7, brief P3b; ``prepare.gate_screen_of``: False, no screen, when
    the manifest has none; True only with the item stage 'planned'; refused otherwise)."""
    from . import prepare
    return prepare.gate_screen_of(services.manifest)


def _archive_value(services):
    """The manifest's sealed archive value (``prepare.archive_of``) without loading the records (``_Run`` reads it
    once; ``run`` verified the bytes before the run began, and the step verifies them again at their use)."""
    from . import prepare
    return prepare.archive_of(services.manifest)


def _item_stage(services):
    """The manifest's sealed item stage (typed-v3 T3; ``prepare.item_stage_of``: 'none', typed-v2's step flow, when
    the manifest has none; refused unless one of ITEM_STAGES)."""
    from . import prepare
    return prepare.item_stage_of(services.manifest)


def _item_quotas(services):
    """The manifest's sealed quota table (typed-v3 T5; ``prepare.item_quotas_of``: None under 'none', else the checked
    table; refused otherwise)."""
    from . import prepare
    return prepare.item_quotas_of(services.manifest)


def _archive(services, chain):
    """The manifest's sealed archive value (typed-v3 T9; ``prepare.archive_of``: ``{}`` when the manifest has none,
    'repair' only), with every package of ``chain`` loaded once through the verified loader (``archives.
    load_package``: the index pin, every file's bytes and every record's hash), so a changed byte is refused before
    the chain directory, the state or the ledger is touched. The step loads its package again at its use."""
    from . import archives, prepare
    value = prepare.archive_of(services.manifest)
    for bench in sorted((value.get(chain) or {}) if value else ()):
        archives.load_package(value, chain, bench)
    return value


def frozen_state(chain_dir, chain, k):
    """(receipt, library, typemap) of step k when it is the state its receipt names: the receipt present, with its
    own hash, version, chain and step; both files' sha256 and their loaded records' hashes equal to the receipt's.
    Any difference (a missing or changed file or receipt) pauses ``frozen_state_changed`` before any call; the detail
    is a fixed code. ``_Run.load_frozen`` and the read plan's pass and replay load every frozen state through it
    (read-plan RP13: the pass mounts with exactly these objects)."""
    chain_dir = Path(chain_dir)
    unit, path = 's%d' % k, chain_dir / ('s%d' % k) / FROZEN
    if not path.exists():
        raise Paused('frozen_state_changed', unit, 'receipt_missing')
    try:
        receipt = units.read_json(path)
    except (OSError, ValueError):
        raise Paused('frozen_state_changed', unit, 'receipt_invalid') from None
    if not _receipt_valid(receipt, chain=chain, step=k):
        raise Paused('frozen_state_changed', unit, 'receipt_invalid')
    for part in ('library', 'typemap'):
        if _file_sha256(chain_dir / unit / (part + '.json')) != receipt[part + '_file_sha256']:
            raise Paused('frozen_state_changed', unit, part + '_changed')
    try:
        library = library_.Library.load(chain_dir / unit / 'library.json')
        typemap = tasktypes.TypeMap.load(chain_dir / unit / 'typemap.json')
    except (OSError, ValueError):
        raise Paused('frozen_state_changed', unit, 'state_unreadable') from None
    if library_.canonical_sha256(library.data) != receipt['library_record_sha256']:
        raise Paused('frozen_state_changed', unit, 'library_changed')
    if tasktypes._sha(typemap.data) != receipt['typemap_record_sha256']:
        raise Paused('frozen_state_changed', unit, 'typemap_changed')
    return receipt, library, typemap


def solver_settings_rows(services):
    """R75: the services' credential-free solver settings per bench; without them (in-memory fakes) a placeholder
    with the echo ids the manifest admits and the services' nominal M."""
    if isinstance(services.solver_settings, dict):
        return services.solver_settings
    echo = sorted(_echo_models(services.manifest or {}, services.chain))
    return {bench: {'model': None, 'route': None, 'max_tokens': None, 'nominal_tokens': services.nominal_tokens(bench),
                    'thinking': None, 'reasoning_effort': None, 'response_model_ids': echo, 'read_timeout': None}
            for bench in ORDER}


def replay_header(services, chain_dir):
    """The plan header values of a pass or a replay (3.2, R32 c, R47): the sealed schedule and base card, the
    manifest hash, the stored ``solver-settings.json``'s bytes hash, the smoke probe and the machinery name."""
    from . import prepare
    manifest = services.manifest
    settings = Path(chain_dir) / readplan.SOLVER_SETTINGS_FILE
    return {'schedule': prepare.schedule_of(manifest), 'base_card': prepare.base_card_of(manifest),
            'manifest_record_sha256': readplan.manifest_sha256(manifest),
            'solver_settings_sha256': readplan.bytes_sha256(settings.read_bytes()) if settings.exists() else None,
            'probe': manifest.get('read_plan_probe'), 'machinery': MACHINERY}


def in_process_replay(services, chain_dir, *, files_only=False):
    """The replay core (R47) in this process: the verdict dict of ``readplan.replay``; ``files_only`` (R44 c): the
    recomputed records, None when they cannot be recomputed."""
    chain_dir = Path(chain_dir)
    header = replay_header(services, chain_dir)
    smoke = services.mode == 'smoke'

    def load(k):
        return frozen_state(chain_dir, services.chain, k)
    if files_only:
        try:
            return readplan.recompute_files(services, services.root, services.chain, smoke=smoke, header=header,
                                            load=load)[0]
        except (readplan.ReadPlanError, Paused):
            return None
    return readplan.replay(services, services.root, services.chain, smoke=smoke, header=header, load=load)


def replay_child(*, fake=False, smoke=False, base_card=None, kill_at=None, snapshot=None,
                 timeout=readplan.REPLAY_TIMEOUT_SECONDS):
    """R76: the automatic replay as a child process -- ``run_typed.py [--machinery-snapshot <bound snapshot>]
    plan-replay --root R --chain X [--smoke] [--fake]`` in a fresh interpreter with the given environment (the caller
    sets ``PYTHONHASHSEED``). Returns the child's verdict: ``equal`` (exit 0), ``different`` (exit 3), else an error
    with a fixed code (its own reason, ``timeout`` or ``exit_<n>``). ``kill_at`` 'replay-child' is passed on (R92)."""
    import subprocess
    import sys
    from . import prepare

    def run_child(root, chain, *, environ):
        command = [sys.executable, str(Path(prepare.TYPED_TREE) / 'scripts' / 'run_typed.py')]
        command += ['--machinery-snapshot', str(snapshot)] if snapshot else []
        command += ['plan-replay', '--root', str(root), '--chain', chain] + (['--smoke'] if smoke else [])
        command += (['--fake'] if fake else []) + (['--base-card', base_card] if base_card else [])
        command += ['--fake-kill-at', kill_at] if kill_at == 'replay-child' else []
        try:
            done = subprocess.run(command, env=dict(environ), capture_output=True, text=True, timeout=timeout,
                                  check=False)
        except subprocess.TimeoutExpired:
            return {'verdict': 'error', 'code': 'timeout'}
        try:
            printed = json.loads(done.stdout)
        except ValueError:
            printed = {}
        printed = printed if isinstance(printed, dict) else {}
        if done.returncode == 0 and printed.get('verdict') == 'equal':
            return printed
        if done.returncode == 3 and printed.get('verdict') == 'different':
            return printed
        if done.returncode == 3 and printed.get('verdict') == 'error':
            return {'verdict': 'error', 'code': printed.get('reason') or 'replay_exception'}
        return {'verdict': 'error', 'code': 'exit_%d' % done.returncode}
    return run_child


def worker_options_of(manifest):
    """The non-secret sandbox worker option set of ``real_services`` (manifest.setting_of, main-v10)."""
    from skillopt.execskill import profiles
    return {'image': manifest['sandbox']['image_id'], 'instruction_configuration': MACHINERY,
            'diagnostics_configuration': profiles.ZEBRA_PC_V15, 'hashseed': 0,
            'cleanup_grace_seconds': profiles.cleanup_grace_seconds(MACHINERY),
            'ready_timeout_seconds': profiles.ready_timeout_seconds(MACHINERY),
            'live_unit_caps': dict(profiles.LIVE_SANDBOX_UNIT_CAP)}


def replay_services(root, chain, manifest, *, smoke):
    """The services of a replay child on a prepared root (R47): the frozen runtime's view, mount, identity and solve
    functions as ``real_services`` wires them, no client, no credential file, no slot pool, no lock, no container;
    the nominal M from ``solver-settings.json`` (R75); the smoke's practice panels from its slices."""
    from . import mount, smoke as smoke_module
    root = Path(root)
    runtime = manifest['runtime']
    settings = units.read_json(root / chain / readplan.SOLVER_SETTINGS_FILE)
    nominal = {bench: row.get('nominal_tokens') for bench, row in (settings.get('benches') or {}).items()}
    items = load_items(manifest) if smoke else {bench: [] for bench in ORDER}
    slices = smoke_module.smoke_slices(items, manifest['slices']) if smoke else manifest['slices']
    return Services(
        manifest=manifest, root=root, chain=chain, mode='smoke' if smoke else 'run', items=items, slices=slices,
        runtime=runtime, embed=None, solver_call=None, role_call=None, worker_factory=None, native=None, heavy=None,
        mount_fn=lambda bench, item, **kw: mount.mount(bench, item, **{'runtime': runtime, **kw}),
        solve_fn=mount.solve, view_fn=lambda bench, item: mount.view_of(bench, item, runtime), write_card=None,
        propose_programs=None, describe=None, outcomes_for_writer=None, worker_options=worker_options_of(manifest),
        nominal_tokens=lambda bench: nominal.get(bench), order=ORDER, machinery_code=manifest.get('machinery_code'),
        identity_fn=lambda bench, item, **kw: mount.mount_identity(bench, item, **{'runtime': runtime, **kw}))


def plan_replay(root, chain, *, smoke=False, fake=False, base_card=None, kill_at=None):
    """The ``plan-replay`` command (R47): ``own_root``; a prepared root passes the bound machinery start checks
    and, on a real root, the owner's consent first; then the replay core in this process, zero calls, nothing
    written. ``fake`` (a fake smoke root only): the configured synthetic manifest (``smoke.CONFIGURED``, the base
    ``base_card`` when given) and the fake services, with ``kill_at`` acting inside this child (R92)."""
    from . import prepare, reads, smoke as smoke_module
    require(chain in CHAINS, 'A registered chain')
    require(kill_at is None or fake, 'A kill point exists for a fake replay only (R92)')
    root = smoke_module.smoke_root(root) if smoke else Path(root)
    prepare.own_root(root)
    if fake:
        require(smoke, 'A fake replay replays a fake smoke root')
        manifest = smoke_module.smoke_manifest(root, fake=True, base_card=base_card, configured=True)
        services = smoke_module.fake_services(root, chain, manifest, kill_at=kill_at, child=True)
        services.slices = smoke_module.smoke_slices(services.items, services.slices)
    else:
        manifest = prepare.load_manifest(root)
        require(base_card is None or prepare.base_card_of(manifest) == base_card, 'The prepared base card')
        if (manifest.get('machinery_code') or {}).get('bound') is True:
            start_checks(root, manifest, check=_real_machinery_check, provenance=_current_typed_code)
        if not smoke:
            reads.consent(root / 'shared')
        services = replay_services(root, chain, manifest, smoke=smoke)
    services.root, services.chain, services.mode = root, chain, 'smoke' if smoke else 'run'
    return in_process_replay(services, root / chain)


def _schedule(services):
    """The manifest's sealed schedule (DESIGN 3.6; ``prepare.schedule_of``: refused unless one of SCHEDULES)."""
    from . import prepare
    return prepare.schedule_of(services.manifest)


def heavy_for(manifest, root, chain):
    """``(heavy, lock_setting)`` of the manifest's sealed ``memory_lock`` (DESIGN 3.6, spec/schedule-lock.md L1 to
    L7, addendum D13); ``heavy(bench, unit=None)`` is ``Services.heavy``.

    'per_cell_plain' (the code default): exactly typed-v1's call, ``route_b_chain.heavy`` with ``extra =
    {'slot_root': ..., 'configuration': 'default'}`` -- the plain branch (a new descriptor on
    ``<slot_root>/memory-heavy.lock`` per cell, blocking ``flock``; sheet exclusive, ALFWorld shared); the unit is
    ignored and ``lock_setting`` is None.

    'unit_shared': the same function and lock file with the machinery configuration (``MACHINERY``, whose
    ``uses_environment_lock`` is true), so ``route_b_chain.heavy`` delegates to ``v218_lock.environment`` as main-v6
    .. main-v10 did: the threads of one unit share the exclusive hold, a holder file names the unit, waits are
    written to ``<root>/<chain>/chain.log`` and ``lock-waits.jsonl``. Every call names its unit (``<chain>/<unit>``
    is the holder's name); ``lock_setting`` (run root, slot root, configuration, chain; no unit) serves
    ``v218_lock.call`` for the ALFWorld preparation resets of read units (``reads.preparation_reset``). The lock mode
    enters no request, no cell tag and no identity."""
    from skillopt.execskill import chain as route_b_chain
    from . import prepare
    mode, slot_root = prepare.memory_lock_of(manifest), manifest['slot_root']
    require(chain in CHAINS, 'A registered chain')
    if mode == 'per_cell_plain':
        def plain(bench, unit=None):
            return route_b_chain.heavy(SimpleNamespace(extra={'slot_root': slot_root, 'configuration': 'default'}), bench)
        return plain, None
    setting = SimpleNamespace(root=Path(root), extra={'slot_root': slot_root, 'configuration': MACHINERY,
                                                       'memory_lock_chain': chain})

    def shared(bench, unit=None):
        require(isinstance(unit, str) and unit, 'The shared memory lock names its unit (memory_lock unit_shared)')
        return route_b_chain.heavy(SimpleNamespace(root=setting.root, extra={
            **setting.extra, 'memory_lock_unit': '%s/%s' % (chain, unit)}), bench)
    return shared, setting


def _open_state(chain_dir, chain, mode, resume, *, machinery_code=None, container_scope=None,
                base_card=BASE_CARD_DEFAULT, schedule=SCHEDULE_DEFAULT, read_plan=READ_PLAN_DEFAULT,
                program_learning=PROGRAM_LEARNING_DEFAULT, archive=None, item_stage=ITEM_STAGE_DEFAULT,
                item_quotas=None, read_anchors=readplan.READ_ANCHORS_DEFAULT, resume_replay=RESUME_REPLAY_DEFAULT,
                gate_rule=GATE_RULE_DEFAULT, gate_screen=GATE_SCREEN_DEFAULT):
    """The chain state: a new one records the machinery record, the container scope, the base card (addendum D17)
    and the schedule (DESIGN 3.6) of this start, with ``phase`` None and no ``read_mounts``; a reopened one must
    carry exactly the same four values (DESIGN 3.5, 4.1; schedule-lock S9: a state whose schedule differs from the
    manifest is refused), besides this version, chain and mode (a fake smoke's synthetic manifest is rebuilt at every
    start, so its base and schedule are checked here: one root never mixes two bases or two orders). The read plan
    likewise (read-plan R5, 3.6): a new state gets ``state['read_plan']`` with ``mode`` = the manifest's value and
    ``solver_settings_sha256`` None; a reopened state whose mode differs is refused.

    typed-v3 (T8, T9): a state started under 'repair' records ``program_learning`` and, with an archive, the
    ``archive_sha256`` of the sealed archive value; a reopened state must carry the same two values (absent = the
    typed-v2 flow and no archive), so one root never mixes two program learnings or two archives. A typed-v2 style
    start writes neither key: its state keeps typed-v2's shape. Likewise the item stage (brief P2b): a state started
    under 'planned' records ``item_stage`` and the ``item_quotas_sha256`` of the sealed table, a reopened one must
    carry the same (absent = 'none', no table). Likewise typed-v3 T2: a state started with the read anchors ('C',)
    records ``read_anchors`` ['C'] (the readout and the terminal read the planned events from it), a reopened state
    must carry the same anchors (absent = typed-v2's C0 and C). Likewise typed-v3 B6 d: a state started with the
    resume replay 'on' records ``resume_replay`` 'on', a reopened state must carry the same (absent = 'off'). Likewise
    typed-v3 T7 (brief P3b): a state started under the gate rule 'evolution' or with the screen records ``gate_rule``
    / ``gate_screen``, a reopened one must carry the same (absent = 'whole', no screen)."""
    archive_sha256 = library_.canonical_sha256(archive) if archive else None
    quotas_sha256 = library_.canonical_sha256(item_quotas) if item_quotas is not None else None
    anchors = readplan.anchor_tuple(read_anchors)
    path = chain_dir / STATE
    if path.exists():
        require(resume, 'Existing chain state at %s requires resume=True (with the owner recovery.json)' % chain_dir)
        state = units.read_json(path)
        require(state.get('version') == VERSION and state.get('chain') == chain and state.get('mode') == mode,
                'The chain state belongs to another run')
        changed = [key for key, value in (('machinery_code', machinery_code), ('container_scope', container_scope),
                                          ('base_card', base_card), ('schedule', schedule)) if state.get(key) != value]
        changed += [key for key, value, default in (('program_learning', program_learning, PROGRAM_LEARNING_DEFAULT),
                                                    ('archive_sha256', archive_sha256, None))
                    if state.get(key, default) != value]
        changed += [key for key, value, default in (('item_stage', item_stage, ITEM_STAGE_DEFAULT),
                                                    ('item_quotas_sha256', quotas_sha256, None))
                    if state.get(key, default) != value]
        changed += [key for key, value, default in (('gate_rule', gate_rule, GATE_RULE_DEFAULT),
                                                    ('gate_screen', gate_screen, GATE_SCREEN_DEFAULT))
                    if state.get(key, default) != value or type(state.get(key, default)) is not type(value)]
        if state.get('read_anchors', list(readplan.READ_ANCHORS_DEFAULT)) != list(anchors):
            changed.append('read_anchors')
        if state.get('resume_replay', RESUME_REPLAY_DEFAULT) != resume_replay:
            changed.append('resume_replay')
        require(not changed, 'The chain state at %s was started with another %s: a new root is needed'
                % (chain_dir, ' and '.join(changed)))
        require((state.get('read_plan') or {}).get('mode') == read_plan,
                'The chain state at %s was started with another read_plan: a new root is needed' % chain_dir)
        return state
    require(not resume, 'Nothing to resume at ' + str(chain_dir))
    state = {'version': VERSION, 'chain': chain, 'mode': mode, 'evidence': EVIDENCE[mode],
             'machinery_code': machinery_code, 'container_scope': container_scope, 'base_card': base_card,
             'schedule': schedule, 'started': _now(),
             'updated': None, 'step': 0, 'phase': None, 'current_unit': None, 'done_units': [], 'reads': {},
             'read_mounts': {}, 'paused': None, 'complete': False, 'recoveries': [], 'infra_retries': {}, 'ledger': None,
             'read_plan': {'mode': read_plan, 'plan_sha256': None, 'file_sha256': None, 'bound_at': None, 'replay': None,
                           'fallbacks': {}, 'failures': [], 'void': False, 'void_reason': None, 'recoveries': [],
                           'counts': None},
             'solver_settings_sha256': None}
    if program_learning != PROGRAM_LEARNING_DEFAULT:
        state['program_learning'] = program_learning
    if archive_sha256 is not None:
        state['archive_sha256'] = archive_sha256
    if item_stage != ITEM_STAGE_DEFAULT:
        state['item_stage'] = item_stage
    if quotas_sha256 is not None:
        state['item_quotas_sha256'] = quotas_sha256
    if anchors != readplan.READ_ANCHORS_DEFAULT:
        state['read_anchors'] = list(anchors)
    if resume_replay != RESUME_REPLAY_DEFAULT:
        state['resume_replay'] = resume_replay
    if gate_rule != GATE_RULE_DEFAULT:
        state['gate_rule'] = gate_rule
    if gate_screen is not GATE_SCREEN_DEFAULT:
        state['gate_screen'] = gate_screen
    return state


def container_scope_of(root):
    """The container scope of a run root (DESIGN 3.5, D7): ``'<VERSION>:<root name>:'``. Every unit name handed to
    ``sandbox.unit_tag`` and ``sandbox.drain_unit`` is prefixed with it, so a typed-v1 unit, a typed-v2 unit and its
    smoke twin of the same chain letter and unit name never share a container prefix (the tag is 12 hex of the
    sha256 of that string) and one run's drain can neither remove nor trip over the other's containers."""
    return '%s:%s:' % (VERSION, Path(root).name)


def start_checks(root, manifest, *, check, provenance):
    """The checks of every real start (run, resume, real smoke; DESIGN 3.5), made by ``run`` before the chain
    directory, the state or the ledger is touched, so a refusal changes nothing and sends nothing:

    1. ``prepare.own_root(root)``: the root belongs to this typed version;
    2. the manifest was prepared bound to the machinery snapshot (``machinery_code.bound``) and ``check()`` -- the
       machinery record of this process, ``machinery.check(real=True)`` at a real start -- equals the sealed
       ``manifest['machinery_code']``;
    3. ``provenance()`` -- the typed code of this tree, ``prepare.typed_code()``: ``T/**`` and ``scripts/run_typed.py``
       -- equals the sealed ``manifest['provenance']['typed_code']``. The wide ``typed_tree`` provenance stays
       information only: a touched test or ops helper never blocks a resume, a touched typed file does.

    Returns the verified machinery record. Refusals name keys, never values or file contents."""
    from . import prepare
    prepare.own_root(root)
    require(isinstance(manifest, dict), 'A real start needs the prepared manifest')
    sealed = manifest.get('machinery_code')
    require(isinstance(sealed, dict) and sealed, 'The manifest seals no machinery_code: a real start refuses it')
    require(sealed.get('bound') is True, 'The manifest was prepared without the machinery snapshot (machinery_code '
                                         'bound is not true): a real start refuses it, a new root is needed')
    found = check()
    require(isinstance(found, dict), 'The machinery check returns the machinery record')
    changed = sorted(key for key in set(sealed) | set(found) if sealed.get(key) != found.get(key))
    require(not changed, 'The machinery of this start differs from the record sealed at prepare in %s: a new root is '
                         'needed' % changed)
    typed = (manifest.get('provenance') or {}).get('typed_code')
    require(isinstance(typed, dict) and typed, 'The manifest seals no provenance.typed_code: a real start refuses it')
    current = provenance()
    require(isinstance(current, dict) and current == typed,
            'The typed code (%s) differs from the one sealed at prepare: a new root is needed'
            % ', '.join(prepare.TYPED_CODE))
    return found


def _real_machinery_check():
    from . import machinery
    return machinery.check(real=True)


def _current_typed_code():
    from . import prepare
    return prepare.typed_code()


def _ledger_cap(services, chain):
    """The ledger cap: the services' (``real_services``: the manifest's ``caps[chain]``), else the manifest's sealed
    cap; never the code constant (DESIGN 3.5: a wrong cap means a new root)."""
    cap = services.cap if services.cap is not None else ((services.manifest or {}).get('caps') or {}).get(chain)
    require(type(cap) is int and cap > 0, 'The ledger cap comes from the sealed manifest (caps.%s)' % chain)
    return cap


def run(root, chain, *, services=None, settings=None, clients=None, embedder=None, smoke=False, resume=False,
        sleep=time.sleep, stop_after_plan=False):
    """The resumable state machine of design §5.7. Returns the final state (``complete`` or ``paused``).

    ``services``: ready services (fakes, or the smoke's); without them the design §5.7 form builds the real ones
    from the root's prepared manifest (``real_services`` with the CLI's ``settings`` / ``clients`` factories and
    ``embedder``). Before the chain directory, the state or the ledger is touched: services bound to a sealed
    machinery record (``Services.machinery_code``, every real start) pass ``start_checks``; fakes (no record)
    pass ``prepare.own_root``. ``stop_after_plan`` (read-plan R77, 'economy' only): the process that binds the plan
    pauses ``stopped_after_plan`` once its replay is equal (exit 5); a resumed process never stops there again."""
    require(chain in CHAINS, 'A registered chain')
    root = Path(root)
    if services is None:
        services = real_services(root, chain, None, smoke=smoke, settings=settings, clients=clients, embedder=embedder)
    require(services.mode in EVIDENCE and services.chain == chain, 'Services of this chain with a registered mode')
    if services.machinery_code is None:
        from . import prepare
        prepare.own_root(root)  # an unbound start (local tests, smoke --fake): no machinery check (spec identity 1.8)
    else:
        services.machinery_code = start_checks(root, services.manifest, check=_real_machinery_check,
                                               provenance=_current_typed_code)
    require(services.container_scope in (None, container_scope_of(root)),
            'The services were built for another root (container scope)')
    cap = _ledger_cap(services, chain)
    repeats = (services.limits or {}).get('gate_repeats')
    require(type(repeats) is int and repeats >= 2, 'A gate needs gate_repeats >= 2 runs per item and arm (DESIGN 3.4)')
    base_card = _base_card(services)  # addendum D17: refused before anything is written unless the manifest seals it
    schedule = _schedule(services)  # DESIGN 3.6: the same, for the sealed schedule
    read_plan = _read_plan(services)  # read-plan R3, R5: the same, for the sealed read plan (with its schedule)
    program_learning = _program_learning(services)  # typed-v3 T8: the same, for the sealed program learning
    archive = _archive(services, chain)  # typed-v3 T9: the sealed packages of this chain, every byte verified first
    item_stage, item_quotas = _item_stage(services), _item_quotas(services)  # typed-v3 T3 to T6: the same
    read_anchors = _read_anchors(services)  # typed-v3 T2: the same, for the sealed read anchors
    resume_replay = _resume_replay(services)  # typed-v3 B6 d: the same, for the sealed resume replay
    gate_rule, gate_screen = _gate_rule(services), _gate_screen(services)  # typed-v3 T7: the same, for the gates
    chain_dir = root / chain
    chain_dir.mkdir(parents=True, exist_ok=True)
    services.root = root
    services.resume_replay = resume_replay  # read once here; the read cells' recorders (``reads``) read it there
    state = _open_state(chain_dir, chain, services.mode, resume, machinery_code=services.machinery_code,
                        container_scope=services.container_scope, base_card=base_card, schedule=schedule,
                        read_plan=read_plan, program_learning=program_learning, archive=archive,
                        item_stage=item_stage, item_quotas=item_quotas, read_anchors=read_anchors,
                        resume_replay=resume_replay, gate_rule=gate_rule, gate_screen=gate_screen)
    if state.get('complete'):
        return state
    runner = _Run(services, state, sleep=sleep)
    # a refused ledger (cap changed) or a missing owner recovery is a hard error, never a recorded pause; under the
    # resume replay 'on' a pending call whose receipt reached its calls file is settled from it (Codex review of
    # 9c6d1f7, finding 2), its cell replays that receipt
    services.ledger = units.Ledger(chain_dir / LEDGER, cap, resume=resume,
                                   durable=(_durable_receipts(root, chain_dir, services.manifest)
                                            if resume_replay == 'on' else None))
    if services.worker_options is not None:
        state['worker_options'] = dict(services.worker_options)
    if resume:
        runner.recover()
    try:
        runner.write_solver_settings()  # read-plan R75: every start and resume, both read plans, before confirm
        if schedule == 'learn_first' and services.mode == 'run':
            runner.consent_first()
        runner.confirm()
        runner.freeze_anchor()
        if schedule == 'learn_first':  # DESIGN 3.6: learn and freeze every step, then every read event
            for k, bench in enumerate(services.order, 1):
                runner.learn(k, bench)
            if read_plan == 'economy':  # addendum D10: R44, the pass, its replay, the optional stop, the classes
                runner.verify_read_plan()
                runner.recover_aliases()
                runner.plan()
                runner.replay_plan()
                if stop_after_plan and runner.bound_here:
                    raise Paused('stopped_after_plan', readplan.PLAN_UNIT)
                runner.read_classes()
            else:
                runner.read_anchors()
                for k in range(1, len(services.order) + 1):
                    runner.read_step(k)
        else:  # 'interleaved': typed-v1's order
            runner.read_anchors()
            for k, bench in enumerate(services.order, 1):
                runner.learn(k, bench)
                runner.read_step(k)
        state['complete'], state['current_unit'], state['phase'] = True, None, None
    except Paused as pause:
        runner.pause(pause.reason, pause.unit, pause.detail)
    except units.Stop as stop:  # the ledger stopped inside a role call (cap, reservation breach): its reason, not 'Stop'
        runner.pause(services.ledger.state.get('stop_reason') or 'ledger_stop', state.get('current_unit'), _pause_detail(stop))
    except Exception as error:  # noqa: BLE001 -- every exception is a pause for the owner, never a silent exit
        runner.pause('exception:' + type(error).__name__, state.get('current_unit'), _pause_detail(error))
    finally:
        try:
            services.close()
        finally:
            runner.persist()
    return state


# ---- writer adapters (the chain hands plain objects; the real writers take their own shapes) -------------------
def card_writer(writers_module):
    """``writers.write_card`` with the leakage corpus built from the learn items the chain passes as ``corpus``; a
    shared type's ``members`` rows (addendum D16) get theirs from their own learn items the same way."""
    def write(*, bench, corpus, **kw):
        if kw.get('members'):
            kw['members'] = [{**row, 'corpus': writers_module.corpus_for(row['bench'], row['corpus'])}
                             for row in kw['members']]
        return writers_module.write_card(bench=bench, corpus=writers_module.corpus_for(bench, corpus), **kw)
    return write


def program_writer(mount_module, writers_module, chain):
    """``writers.propose_programs`` with the parent Package built from the type's program records
    (``mount.package_for``, step label ``typed/<chain>/s<k>``) and the hook view excerpted as the engineer sees it."""
    def propose(*, bench, parent, step, evidence, hook_view, **kw):
        package = mount_module.package_for(list(parent), step='typed/%s/s%d' % (chain, step), evidence=evidence)
        return writers_module.propose_programs(bench=bench, parent=package, step=step, evidence=evidence,
                                               hook_view=writers_module.hook_view_for(bench, hook_view), **kw)
    return propose


# ---- the real wiring (Linux only; design §5.4) ----------------------------------------------------------------
def client_settings(roles_repo=ROLES_REPO):
    """The main-v10 client blocks exactly as scripts/arch_probes.solver_settings builds them (credential files by
    path only): G on the roles repository, D on northgate route B with thinking disabled."""
    from skillopt.execskill import client as clients, manifest as route_b_manifest, routes
    blocks = {c: route_b_manifest.solver_block(c, env_path=roles_repo if c == 'G' else clients.NORTHGATE_ENV,
                                               configuration=MACHINERY, branch=None if c == 'G' else routes.BRANCH,
                                               longest=None if c == 'G' else routes.S1B_CEILING) for c in ('G', 'D')}
    pin = routes.pin('D', 'B', env_path=clients.NORTHGATE_ENV, solver_block=blocks['D'], configuration=MACHINERY)
    settings = {'configuration': MACHINERY, 'clients': {'solver': blocks, 'roles': route_b_manifest.role_settings(MACHINERY),
                                                        'routes': {'D': {'B': pin}}}}
    route_b_manifest.check_clients(settings['clients'], configuration=MACHINERY)
    require(pin['thinking'] == {'type': 'disabled'} and pin['reasoning_effort'] == 'none', 'Route B disables thinking')
    return settings


def load_items(manifest, *, pools_root=None):
    """The pinned practice pools exactly as ``prepare`` drew the slices from them (``prepare.load_pool``: sha-checked
    against the manifest's pins; ALFWorld = the games with a registered routing view)."""
    from . import prepare
    pools_root = pools_root or manifest.get('pools_root') or POOLS_ROOT
    items = {}
    for bench in ORDER:
        items[bench] = prepare.load_pool(bench, pools_root, pin=_pool_pin(manifest, bench))[0]
    return items


def _close(client):
    http = getattr(client, 'http', None)
    if callable(getattr(http, 'close', None)):
        try:
            http.close()
        except Exception:  # noqa: BLE001 -- closing is best effort at the end of a run
            pass


def _calls_path(services, unit, tag, purpose):
    name = tag if purpose == 'solve' else '%s-%s' % (tag, purpose)
    return Path(services.root) / services.chain / unit / 'calls' / (name + '.json')


def _client_factories(settings, chain, roles_repo):
    """The chain's solver per bench (cached, one per bench, shared by the unit's threads as main-v10 shares its
    clients) and the GLM-5.3 role client; the CLI's ``run_inputs`` shape: ``solver(bench) -> (client, bound)``,
    ``role(max_tokens) -> client``."""
    from scripts.weak_solver_probe import Client
    from skillopt.execskill import client as clients, manifest as route_b_manifest
    block = settings['clients']['routes']['D']['B'] if chain == 'D' else settings['clients']['solver']['G']
    g, roles = settings['clients']['solver']['G'], settings['clients']['roles']

    def solver(bench):
        return route_b_manifest.make_solver(settings, chain, bench, 'B' if chain == 'D' else None), block['B'][bench]

    def role(max_tokens):
        return clients.unpooled(Client(roles_repo, roles['model'], proxy=g['proxy'], max_tokens=max_tokens,
                                       read_timeout=roles['read_timeout']), proxy=g['proxy'], read_timeout=roles['read_timeout'])
    return {'solver': solver, 'role': role}


def real_services(root, chain, manifest=None, *, smoke, settings=None, clients=None, embedder=None):
    """Wire the route-B pieces (design §5.4) for one chain process; every option named explicitly. ``manifest``:
    the root's prepared manifest (loaded when None); ``settings`` / ``clients``: the CLI's ``run_inputs`` (built
    here when None); ``embedder``: None for the CPU-venv subprocess.

    From the sealed manifest (DESIGN 3.5, 3.6): the ledger cap ``caps[chain]``, the machinery record ``run`` verifies
    (``start_checks``) before the ledger opens, and the memory-lock mode (``heavy_for``: ``heavy`` and
    ``lock_setting``). Every container of this chain is named and drained under the scope
    ``container_scope_of(root)``: ``sandbox.unit_tag(chain, scope + unit)``, ``sandbox.drain_unit(chain, scope +
    unit, ...)``; no request, cell tag or record of a call contains it."""
    from skillopt.execskill import client as route_b_client, manifest as route_b_manifest, profiles, slots
    from skillopt.execskill.sandbox import client as sandbox
    from . import mount, prepare, reads, writers
    require(chain in CHAINS, 'A registered chain')
    mode, root = 'smoke' if smoke else 'run', Path(root)
    manifest = prepare.load_manifest(root) if manifest is None else manifest
    caps, sealed = manifest.get('caps'), manifest.get('machinery_code')
    require(isinstance(caps, dict) and type(caps.get(chain)) is int and caps[chain] > 0,
            'The manifest seals the token cap of chain ' + chain)
    require(isinstance(sealed, dict) and sealed, 'The manifest seals the machinery record (machinery_code)')
    require(manifest.get('tau_rule') == prepare.tau_rule(),
            'The manifest seals another gate rule (tau_rule) than this code: a new root is needed')
    scope = container_scope_of(root)
    recorded = manifest.get('clients') or {}
    roles_repo = recorded.get('roles_repo') or ROLES_REPO
    require(recorded.get('northgate_env', route_b_client.NORTHGATE_ENV) == route_b_client.NORTHGATE_ENV,
            'The manifest names the registered northgate credential file')
    settings = settings or client_settings(roles_repo)
    factories = clients or _client_factories(settings, chain, roles_repo)
    runtime = manifest['runtime']
    require(set(ORDER) <= set(runtime), 'The runtime table covers the five benches')
    require(os.environ.get('ALFWORLD_DATA') == runtime['alfworld'].get('alfworld_data'),
            'ALFWORLD_DATA must equal runtime.alfworld.alfworld_data before the process starts (env processes spawn)')
    ready = sheet_readiness(runtime['spreadsheetbench'])
    require(ready.get('status') == 'ready', 'SpreadsheetBench scorer readiness: %r' % (ready,))
    pools = slots.pools(manifest['slot_root'], sizes=route_b_manifest._slot_sizes(
        {'configuration': MACHINERY, 'sandbox': manifest['sandbox']}))
    capped = {bench: pools[slots.LIVE].limited(cap) for bench, cap in profiles.LIVE_SANDBOX_UNIT_CAP.items()}
    limits, image, docker = route_b_manifest.limits_of(manifest), manifest['sandbox']['image_id'], sandbox.Docker()
    block = settings['clients']['routes']['D']['B'] if chain == 'D' else settings['clients']['solver']['G']
    nominal = {bench: block['M'][bench] for bench in ORDER} if chain == 'D' else {}
    cache, lock = {}, threading.Lock()

    def solver(bench):
        with lock:
            if bench not in cache:
                cache[bench] = factories['solver'](bench)
            return cache[bench]
    role = factories['role'](DESCRIBER_TOKENS)
    writer = copy(role)  # route B's card writer: the role client with the writers' bound
    writer.max_tokens = WRITER_TOKENS
    # manifest.setting_of (main-v10): the v2.9.2 cleanup grace and ready timeout besides docker/limits/image and the
    # instruction/diagnostics configurations; units.for_unit adds the tag and the per-unit event sinks
    grace, ready = profiles.cleanup_grace_seconds(MACHINERY), profiles.ready_timeout_seconds(MACHINERY)
    worker_options = worker_options_of(manifest)
    events = {}

    def unit_events(unit):
        with lock:
            return events.setdefault(unit, {'cleanups': [], 'starts': []})

    def mount_fn(bench, item, **kw):  # a caller without the view gets it from the frozen runtime, never from none
        return mount.mount(bench, item, **{'runtime': runtime, **kw})

    def identity_fn(bench, item, **kw):  # DESIGN 3.4: the same view / runtime wrapper as mount_fn, zero calls
        return mount.mount_identity(bench, item, **{'runtime': runtime, **kw})
    heavy, lock_setting = heavy_for(manifest, root, chain)  # the sealed memory_lock (DESIGN 3.6, addendum D13)
    services = Services(
        manifest=manifest, root=root, chain=chain, mode=mode, items=load_items(manifest), slices=manifest['slices'],
        runtime=runtime, embed=embedder, solver_call=None, role_call=None, worker_factory=None,
        native=pools[slots.NATIVE], episodes=pools[slots.EPISODE], heavy=heavy,
        mount_fn=mount_fn, solve_fn=mount.solve, view_fn=lambda bench, item: mount.view_of(bench, item, runtime),
        write_card=card_writer(writers), propose_programs=program_writer(mount, writers, chain),
        describe=writers.describe,
        outcomes_for_writer=lambda cells, items, *, bench, baseline=None: writers.outcomes_for_writer(
            cells, items, bench=bench, seed=SEED, baseline=baseline),
        read_panel=None, worker_options=worker_options, nominal_tokens=lambda bench: nominal.get(bench), order=ORDER,
        cap=caps[chain], machinery_code=sealed, container_scope=scope, lock_setting=lock_setting, identity_fn=identity_fn,
        # read-plan R75: the credential-free settings of this chain's solver block; R76: the replay child, bound to
        # the same machinery snapshot as this process
        solver_settings={bench: readplan.solver_settings_of_block(block, bench, nominal=chain == 'D') for bench in ORDER},
        replay=replay_child(smoke=smoke, snapshot=sealed.get('snapshot') if sealed.get('bound') is True else None))

    def solver_call(bench, unit, tag, *, transform=None, purpose='solve'):
        client, bound = solver(bench)
        return units.CallRecorder(client.call, services.ledger, max_tokens=bound, tag=tag, unit=unit,
                                  out_path=_calls_path(services, unit, tag, purpose), transform=transform)

    def role_call(purpose, unit, tag, max_tokens):
        require(max_tokens in (WRITER_TOKENS, DESCRIBER_TOKENS), 'A registered role bound')
        client = writer if max_tokens == WRITER_TOKENS else role
        return units.CallRecorder(client.call, services.ledger, max_tokens=max_tokens, tag=tag, unit=unit,
                                  out_path=_calls_path(services, unit, tag, purpose))

    def worker_factory(bench, unit, tag):
        # manifest.setting_of (main-v10) + units.for_unit (tag, event sinks) + units.cell_context (live/per_call pools)
        sinks = unit_events(unit)
        options = {'docker': docker, 'limits': limits, 'image': image, 'instruction_configuration': MACHINERY,
                   'diagnostics_configuration': profiles.ZEBRA_PC_V15, 'tag': sandbox.unit_tag(chain, scope + unit),
                   'hashseed': 0, 'live': capped.get(bench, pools[slots.LIVE]), 'per_call': pools[slots.CALL],
                   'cleanup_grace_seconds': grace, 'cleanup_events': sinks['cleanups'],
                   'ready_timeout_seconds': ready, 'start_events': sinks['starts']}
        return lambda: sandbox.Worker(**options)

    def drain(unit):
        # units.drainer (route B): once every worker of the unit exited, none of its containers remains
        sinks = unit_events(unit)
        sandbox.drain_unit(chain, scope + unit, docker=docker, cleanup_grace_seconds=grace, cleanups=sinks['cleanups'])
        return {'cleanup_grace_seconds': grace, 'cleanups': list(sinks['cleanups']), 'starts': list(sinks['starts'])}

    def close():
        for client in [made for made, _ in cache.values()] + [role]:
            _close(client)
    services.solver_call, services.role_call, services.worker_factory = solver_call, role_call, worker_factory
    services.drain, services.close = drain, close
    return services
