"""One step of a route-B chain on one bench (protocol ``fivebench-execskill-v1``; registration §5.1-§5.8, §6, §7,
§9.2, §9.3, §21; implementation plan §1 step row, §5, T-STEP-1): new orchestration over the copied units.

``run_step(setting, chain, bench, k, parent)`` runs the eight sub-steps of §5 on the parent package S. Every sub-step
is a copied unit (``units.run_unit``: its lock, ``attempt-N`` directories, a write-once ``unit.json``; a pause is
never resumed by itself) at ``<chain root>/s<k>-<bench>/<name>``, run under the machine-wide memory lock of every
bench whose cells it runs (``chain.heavy``: SpreadsheetBench exclusive, ALFWorld shared; a self-test's earlier
SpreadsheetBench set takes the spreadsheet lock, Codex finding #5) after the pinned files are verified again
(``chain.check_pins``, plan §2.9), its consumption registry bound to the run root (a unit is its label and its run
root, Codex finding #7). A completed unit is read back, so a restarted chain passes through finished units
without a model call. The step's slices are sealed once (``slices.json``) before its first unit; on the five benches
of the main configuration (registrar addendum 2026-10-22 17:0x) SearchQA's acceptance slice comes from its kept fresh
tail (``_tail``), ALFWorld's slices from the room groups of the fresh supply (``_cut``), and LiveMath's J7 probe
cells are sent options-only (``_options_only``).

- 5.1 ``run``: S on the run slice for the registered runs (``rounds.run_round``, solver scope ``...:run``); when S's
  inherited procedures fire on >= 10 % of the run slice (zero-call routing, ``ENTRY_READING_SHARE``) the card arm C
  runs once beside it, read only descriptively as the entry reading S - C. The slice is registered, dispatched and
  decided in the chain's consumption namespace -- decided by the unit's settlement once the work's completion
  evidence is persisted, and again (writing nothing) by the commit attempt that finishes a unit interrupted after its
  work (``units.run_unit``, Codex finding #8); infrastructure unknown > 1/10 pauses (``rounds.guard``). After chain
  G's first run unit, the cost check of §9.3 (``cost_projection`` -> ``chain.cap_check``) may pause chain G only.
- 5.2 ``diagnose``: the run slice's parent trajectories split into write and hold halves (``detectors.split``; ALFWorld
  by room); the examiner sees the write half only (``examiner.detector_payload``) and writes <= 3 candidates
  (``examiner.detector_write``), sealed (``detectors.seal_candidates``) before the hold half is read
  (``detectors.validate``, residual cells on the masked view, Holm at 10 %).
- 5.3 ``generate`` (benches with registered families): the examiner's policy (``examiner.policy_revise``), the
  mandatory research (``examiner.research_requests`` through ``research.Researcher``, charged to
  ``...:examiner:research``), the findings split into G_self and G_acc halves by seed (``research.split``, sealed in
  the unit), the parameter specs on the G_self half (``examiner.generator_write``), the items by the fixed reference
  functions (``examiner.build``; the ten items per finding counted across the attempt's builds and adjustments,
  ``finding-counts-<n>.json``, Codex finding #10), the band probe (S, one run, at most ``BAND_ROUNDS`` probes, each
  adjustment a new ``generator_write``; only on a set of 30 qualified probe items, ``examiner.sufficient``: a smaller
  set is recorded as insufficient material, never probed or admitted, Codex finding #9) and the shortcut probe (C, two
  runs on the shortcut variants, each cell in its bench's probe mode ``examiner.probe_mode``: SpreadsheetBench without
  the workbook, registrar decision on ticket C1-2, wired by ticket PR-C12-1), both charged to ``...:examiner``; then
  the four gates (``examiner.gates``) and the generator record. SearchQA generates nothing and ALFWorld's selection
  path is not part of this module (``generators.mode``); their unit records why.
- 5.4 ``engineer``: one proposal of <= 3 changes through the fixed checks C1-C9 with one fix each
  (``engineer.run``) on the run-slice trajectories of this chain (this bench and the earlier ones), the run slices'
  reference answers of the failures (never on ALFWorld), the detector counts and the previous step's outcome (counts).
  ``ENGINEER_CALLS`` counts the engineer calls of the whole step: ``engineer-2`` gets what the first unit left
  (registrar addendum 2026-10-22, R7 decision 16:1x, R7a).
  No surviving change ends the step: the acceptance slice is never registered, nothing is consumed.
- 5.5 ``selftest``: S' and S once on G_self (<= 60) and on each earlier bench's generated set (<= 40), interleaved,
  charged to ``...:selftest``, each set's cells on its own bench's client, M, timeout and bound B (Codex finding #4).
  Only two blocks (§5.5): S' fault share > 2 % -- cells with a fault of a procedure the step changed, J3's rule (Codex
  F22); an inherited procedure faults in S alike and is reported only -- or on any set S' format-violating share >= 5
  points above S's with a one-sided exact sign test p < 0.05; accuracy is recorded, never blocking. A block gives the
  engineer one more proposal (unit ``engineer-2``, its ``previous`` the self-test's counts) and a second self-test
  (``selftest-2``); a second block ends the step without registering the acceptance slice (``SELFTEST_PASSES``).
- 5.6 ``accept``: the acceptance slice (and LiveMath's J7 probe) registered, the round sealed
  (``acceptance.prepare``: donors, A* per edit type, twins, P_y, P_i, G_acc from the frozen generator on the g_acc
  half, S_dup on a bench with an admitted generator after step 1), dispatched (``acceptance.dispatch`` through
  ``acceptance.runner`` in the sealed order; OfficeQA's block gap waited out), decided (``acceptance.decide``), written
  once in the attempt and settled (``acceptance.settle``: accept and reject decide the items -- once the unit's
  completion evidence is persisted, and again by a recovery's commit attempt, Codex finding #8; undetermined pauses
  in the work; |A*| < 30 released them). A redo reuses the sealed record after ``donors.verify`` and redoes ONE block (§9.3;
  owner decision #15, default in force: a block is redone whole, never spliced across attempts; ticket C7c-2): the
  blocks an earlier attempt completed are kept (``acceptance.earlier_blocks``), the block it started and did not
  complete is redone whole on the redo's own sub-scope ``...:accept:attempt-N`` and the redo reserve, and the blocks
  no attempt started run as the round's first run of them on ``...:accept``, so the sub-scope never holds more than
  the one block its cap (min(kind cap, redo reserve = the largest single acceptance block cap), calc T6) and S-E6's
  pricing (``smoke._scope_cells``) are made for. The decision reads the union by its sealed block -> attempt map.
  The G_acc cells, interleaved with the real ones, are the examiner's: their solver cost goes to ``...:examiner`` in
  every attempt (§3.3 "它的做题费用记在考官作用域里（9.2、9.3）", §9.2, calc T6; registrar decision on ticket C7e-1). The
  decision also records §6.2's descriptive 15-minute series per set and arm (``acceptance.series``; ticket PR-F2-1).
- 5.7 ``freeze``: accepted, S' plus the describer's frozen text twin of each procedure the step adds or revises (one
  call each, ``describer.describe`` on the procedure's note lengths replayed on the run slice, charged to the
  engineer's scope) becomes the new parent; otherwise S passes on unchanged and S' stays archived (``package.save``).
- 5.8: nothing in the pilot; the chain reads the test sets once at its end (§8.1).

The step's sealed record ``fivebench-execskill-v1-step`` (``step.json``, write-once) names every unit's record hash, the
decision and the package passed on; ``StepRecord`` carries it with that package. ``learn`` is the step in the form
``chain.run`` calls (``functools.partial(learn, services=...)``); ``run_unit_spec`` is the ``step-unit`` child of the
command line (ticket A13-1), one step from the verified manifest.

The smoke's S4 mini-step (registration §10 S4; plan §10 step 7; ticket C7b2-1) is ``run_step`` with chain
``budgets.SMOKE`` and a ``SmokeStep``: SearchQA step 1 from the empty parent on the 60 S4 smoke items (run 20, accept
40, ``S4_SLICES``), sub-steps run, accept and freeze only, the candidate S' given (the registrar's fixture package X;
the method roles that write one are S3's). Its solver calls go to the smoke ledger's one solver scope with the smoke
solver's model and bound B (``SmokeStep.model``: chain D's, or glm-5.3 in a chain-G smoke, registrar addendum
2026-10-23 02:3x), its role calls (the describer at freeze) to ``smoke:glm``, its consumption to the smoke namespace,
whose one purpose is ``smoke``, and the registered fault switch (``SmokeStep.drill``) gives the acceptance cells of
the accept unit's first attempt their workers.

v2 (configuration ``main-v2``, learning mode "train": ``protocol.learning_of``; owner decision 2026-10-23 13:3x,
spec-v2): after run, diagnose and generate the engineer works over training rounds instead of engineer / engineer-2 /
selftest-2 (``_trained``). Round r (at most ``TRAIN_ROUNDS``) is the unit ``engineer-r<r>`` (``engineer.run_train``:
proposals against the incumbent T_{r-1}, T_0 = S, with the incumbent's latest trajectories, the earlier rounds, the
last evaluation and its lint; the candidate re-expressed against S, ``engineer.rebase``) and, when it made a
candidate, the unit ``train-r<r>`` (``_train_eval``): the zero-call routing of every run-slice item and admitted
G_self item under T_{r-1} and the candidate, then both packages on the items they route differently (run items with
the registered runs, generated items once), one seeded order, charged to the step's ``...:selftest`` scope; the
candidate is adopted by ``train_verdict`` (guards: own faults and predicate faults of the changed procedures <= 2 %,
format-violating cells not above the incumbent's by more than max(2, 2 %); gain: more items fixed than broken, a net
gain of at least max(1, 2 % of the evaluated items) and the one-sided sign test p <= ``TRAIN_ALPHA``). The loop stops
after ``TRAIN_PATIENCE`` rounds in a row without adoption (a round without a candidate counts). A final package
without an edit against S ends the step ``no_training_gain``; else it takes v1's self-test once (a block ends the step
``selftest_blocked``) and v1's acceptance and freeze unchanged. The examiner's v2 policy and generator prompts ask for
more material and a short G_self gets up to ``TOPUP_ROUNDS`` top-up calls after each build (``_topup``). main-v2
consumes in its own namespaces (``protocol.V2_NAMESPACES``, ``_Step.namespace``): its slices are cut as v1's from the
same supply, so its run slices are v1's (training items, reused) and its acceptance slices v1's never registered ones.
The smoke's v2 example SX is the same step on SearchQA smoke items (``SmokeStep.train``, ``protocol.SX_SLICES``); if
no round adopts there, the last evaluated candidate takes the self-test and acceptance so that they run end to end,
recorded as ``exercise``.

v2.2 (configuration ``main-v2-2``, owner decision 2026-10-24 12:1x): ``train_verdict`` records the sign test without
requiring it (``protocol.TRAIN_SIGN``); ``_train_eval`` prunes from the candidate, before its cells, every procedure
the round wrote that its routing pass enables on no evaluated item and faults on none (``prune_idle``,
``protocol.PRUNE_NON_FIRING``; the pruned package is saved and evaluated, its unit records the proposed hash and the
pruned ids, the round's history the fate ``pruned_no_firing``); the acceptance round is prepared with the practical
rule (``protocol.ACCEPT_RULES``, ``acceptance.prepare``) and labelled ``protocol.ACCEPT_FRESHNESS``.

v2.3 (owner request 2026-10-25 T1/T2, ``protocol.IDENTICAL_REQUEST_REUSE``): the self-test seals full-view request
identities and its skipped items before dispatch, reusing the same plan on resume. An interchangeable item runs
neither arm, counts as an unchanged item in the fault and format denominators, and has no measured accuracy (the
accuracy denominator explicitly lists only dispatched items). An entirely identical self-test passes without an
endpoint or call. Training prunes idle procedures first, then skips the enabled-list differences whose exact
requests and post-call behavior are identical, listing them as ``identical`` with neither a fix nor a break.
Amendment 1 (2026-10-25): those skipped training items remain evaluated with exact zero differences. The adoption
threshold counts them, and the format/fault denominator includes their registered runs (generated items once).
Zero-call rendering faults prevent either skip and remain in the guards even if the later execution succeeds.
ALFWorld preserves its enabled-list rule. Acceptance receives the configuration's sealed reuse inputs; the test
reads and stage reads keep their registered behavior.
Amendment 2 (2026-10-25): the engineer receives exactly this round's run and admitted G_self routing views for its
repairable C6b predicate-firing check. ``_training_publics`` supplies both passes; idle pruning remains the backstop.

While a sub-step runs, the step's Setting and worker factories are that unit's (``units.for_unit``; registrar decision
on safety review 3, ticket C5-1): every sandbox container of the unit carries its tag, and the unit is drained
(``units.drainer``) before it is marked complete or paused. At the end of each unit attempt its role calls (reply
text, label, request hash, the leakage adjudicator's reason) are appended once to ``<unit>/role-calls.jsonl``
(``role_calls``; registrar addendum 2026-10-22 15:5x R5). On SpreadsheetBench the engineer's references are the
answer-position cell values of the failed run items (``_sheet_reference``, R1), and every stored SpreadsheetBench
trajectory a replay may run on gets its own workbook at any step (``_inputs_dirs``, R2).
"""
from __future__ import annotations

import functools
import hashlib
import json
import math
import shutil
import time
import xml.etree.ElementTree as ET
import zipfile
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from statistics import fmean

from skillopt.coevo5.data import ranked
from skillopt.coevo5.roles import Invalid, Roles, parse as parse_reply
from skillopt.continual_eval import spreadsheet_compat
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import (acceptance, budgets, describer, detectors, donors, engineer, examiner, exclusion, generators,
               profiles as protocol,
               replay, research, rounds, router, solver, supply, trajectories, units, reuse as request_reuse)
from .corpus import Corpus
from .cells import Arm, Pause, TrainingStore, cell_id, run_cells
from .chain import EXIT_AWAITING, EXIT_COMPLETE, EXIT_PAUSED, cap_check, check_pins, confirmation, heavy
from .package import EDIT_KINDS, Package, edits, empty, load, save, validate, with_describer, withhold
from .profiles import (BAND_ROUNDS, BENCHES, CELL_ANCHORS, CHAINS, EARLIER_SET_MAX, ENTRY_READING_SHARE, G_SELF_MAX,
                       MDE_POINTS, CONFIG_CAP_FACTOR, CONFIGURATIONS, NOTES_KEY, RECORD_HASH, ROLE_MAX_TOKENS,
                       ROLE_MODEL, S4_SLICES, SEED, SX_SLICES, TOPUP_ROUNDS, TRAIN_ADOPT_SHARE, TRAIN_ALPHA,
                       TRAIN_EXAMPLES, TRAIN_FORMAT_MARGIN, TRAIN_PATIENCE, TRAIN_ROUNDS, TRAIN_TEXT_CHARS,
                       configuration_of, learning_of, namespace_of, order_of, FIX_ECHO, META_COUNTERFACTUAL,
                       ACCEPT_FRESHNESS, ACCEPT_RULES, PRUNE_NON_FIRING, TRAIN_SIGN, IDENTICAL_REQUEST_REUSE,
                       SELFTEST_ALPHA, SELFTEST_FAULT_MAX, SELFTEST_FORMAT_MARGIN, SELFTEST_PASSES, SLICES,
                       SMOKE_SOLVER, generator_seed, ledger_bound, record, round_tag, verified)
from .registry import HELD, run_identity
from .slots import CALL, LIVE

__all__ = ("FRESHNESS", "ROLE_CALLS", "SLICES_FILE", "STEP_FILE", "Services", "SmokeStep", "StepRecord",
           "cost_projection", "learn", "role_calls", "run_step", "run_unit_spec", "selftest_verdict")

STEP_FILE = "step.json"
SLICES_FILE = "slices.json"
FRESHNESS = "route_b_fresh_method_side_reused"  # plan §2.6: fresh items, method-side material reused
UNITS = ("run", "diagnose", "generate", "engineer", "selftest", "engineer-2", "selftest-2", "accept", "freeze")
COST_FACTOR = Fraction(3, 2)  # §9.3: every cap = 1.5 x its maximum-schedule high estimate (+ one reservation)
# (the pilots'; a run divides by its configuration's factor, ``protocol.CONFIG_CAP_FACTOR``: main 3, registrar 17:0x)
SPEC_FIELDS = frozenset({"chain", "k", "bench"})  # a step-unit child's spec
# registrar decision 2026-10-22 on ticket C1-3 (option b): no SpreadsheetBench G_acc in v1, disclosed in the record
SHEET_VALIDITY = {"status": "not_evaluable", "reason": "no SpreadsheetBench G_acc in v1 (registrar decision, C1-3)"}
SMOKE_BENCH = "searchqa"  # §10 S4: the mini-step runs on SearchQA smoke items
SMOKE_UNITS = ("run", "accept", "freeze")  # §10 S4: run 20, accept 40 (A*, twins, the decision), freeze
ROLE_CALLS = "role-calls.jsonl"  # registrar addendum 2026-10-22 15:5x R5: <unit>/role-calls.jsonl
FINDING_COUNTS = "finding-counts-%s.json"  # Codex finding #10: a build's finding-keyed counter, in its attempt
ADJUDICATOR = "leak_adjudicate"  # the leakage adjudicator's role name (coevo5 ``leakage.adjudicate``)
TRAIN = engineer.TRAIN  # v2's learning mode (module docstring)
UNITS_V2 = ("run", "diagnose", "generate",
            *("%s-r%d" % (kind, r) for r in range(1, TRAIN_ROUNDS + 1) for kind in ("engineer", "train")),
            "selftest", "accept", "freeze")
QUESTION_FIELDS = {"searchqa": "question", "officeqa": "question", "livemath": "question",
                   "spreadsheetbench": "instruction", "alfworld": "task_text",
                   "zebralogic": "question"}  # v2 feedback: the item's question
FEEDBACK_TAG = "execskill-v2:feedback"  # the seeded order of a round's examples
EXERCISE = "exercise_last_candidate"  # SX only: no round adopted; the last evaluated candidate takes the acceptance


@dataclass(frozen=True)
class Services:
    """What a step uses besides the ``units.Setting`` (built from the verified manifest in a run; fakes in tests).
    ``registry``: the consumption registry (§3.4, ``registry.Registry``); ``sources``: the frozen research sources
    (``research.Sources``, §7.2); ``workers(package, *, kind, hashseed=0, inputs_dir=None, tag=None)``: a context
    manager yielding a started sandbox worker (``sandbox.client.with_worker`` with the Setting's sandbox options; the
    step binds ``tag`` to the running unit's, ticket C5-1) for the engineer's checks, the detectors and the replays;
    ``item_workers(package, item)``: the router's and the donors'
    factory (None: derived from ``workers``, mounting a SpreadsheetBench item's public workbook); ``checker`` /
    ``engine``: LiveMath's fixed checker and SpreadsheetBench's recalculation engine (``generators.generate``);
    ``clock`` / ``sleep``: the acceptance dispatch's time (OfficeQA's block gap, §3.3)."""

    registry: object
    sources: object
    workers: object
    item_workers: object = None
    checker: object = None
    engine: object = None
    clock: object = time.time
    sleep: object = time.sleep


@dataclass(frozen=True)
class SmokeStep:
    """The S4 mini-step (module docstring; §10 S4). ``items``: the 60 S4 SearchQA smoke items in their order -- the
    run slice is the first ``S4_SLICES["run"]``, the acceptance slice the next ``S4_SLICES["accept"]``;
    ``candidate``: the registered candidate S' (the registrar's fixture package X of S2, an engineering fixture);
    ``drill``: the registered fault switch (``smoke.FaultSwitch``) whose ``worker(**options)`` gives the acceptance
    cells of the accept unit's first attempt their workers, or None; ``model``: the smoke solver's model
    (``smoke.solver_of``: chain D's by default, glm-5.3 in a chain-G smoke, registrar addendum 2026-10-23 02:3x).
    ``train`` (v2, module docstring): the smoke's example SX -- run, diagnose, generate, the training rounds, the
    self-test, accept and freeze on its 260 SearchQA smoke items (run the first ``SX_SLICES["run"]``, acceptance the
    next ``SX_SLICES["accept"]``), no candidate given and no drill."""

    items: tuple
    candidate: Package
    drill: object = None
    model: str = SMOKE_SOLVER
    train: bool = False  # v2's example SX: the whole v2 step, ``protocol.SX_SLICES``; ``candidate`` None


@dataclass(frozen=True)
class StepRecord:
    """A finished step: the package passed on (S' when accepted, else S) and the sealed step record."""

    package: Package
    record: dict


@dataclass
class _Step:
    setting: object
    services: Services
    chain: str
    bench: str
    k: int
    parent: Package
    chain_root: Path
    smoke: SmokeStep | None = None
    calls: list | None = None  # the Roles of the unit attempt running now (``unit``), for its role-calls.jsonl

    @property
    def root(self):
        return safe_path(self.chain_root) / ("s%d-%s" % (self.k, self.bench))

    @property
    def name(self):
        """The step's label: ``<chain>/s<k>-<bench>`` (package steps, run units, consumption units)."""
        return "%s/s%d-%s" % (self.chain, self.k, self.bench)

    @property
    def evidence(self):
        return self.setting.evidence

    @property
    def learning(self):
        """The step's learning mode: its run configuration's (``protocol.learning_of``); the smoke's S4 "single", its
        v2 example SX "train"."""
        if self.smoke is None:
            return learning_of(self.setting)
        return TRAIN if self.smoke.train else "single"

    @property
    def namespace(self):
        """The consumption namespace of the step's items (registry.py, §3.4): the chain's own -- main-v2's
        ``protocol.V2_NAMESPACES`` (``namespace_of``) -- or the smoke's."""
        return self.chain if self.smoke is not None else namespace_of(self.setting, self.chain)

    @property
    def units(self):
        """The step's sub-step units: v1's, the S4 mini-step's or v2's (``UNITS_V2``)."""
        if self.learning == TRAIN:
            return UNITS_V2
        return UNITS if self.smoke is None else SMOKE_UNITS

    def label(self, unit):
        return "%s/%s" % (self.name, unit)

    def roles(self, role):
        """GLM-5.3 roles of this step charged to ``budgets.glm_scopes`` of ``role`` (§4.2-§4.3, §9.3); in the smoke
        to ``smoke:glm``."""
        if self.smoke is None:
            made = units.roles(units.role_endpoint(self.setting, self.chain, role, self.bench, self.k),
                               configuration=configuration_of(self.setting))
        else:
            made = units.roles(budgets.endpoint(self.setting, budgets.glm_scopes(budgets.SMOKE, role, None, None),
                                               client=self.setting.clients(ROLE_MODEL, None),
                                               max_tokens_bound=ROLE_MAX_TOKENS),
                               configuration=configuration_of(self.setting))
        if self.calls is not None:
            self.calls.append(made)
        return made

    def solver(self, kind, attempt, *, first_run=False, g_acc=False, cell_bench=None):
        """The solver endpoint of one unit attempt (``units.solver_endpoint``; ``first_run``: an acceptance round's
        blocks that no earlier attempt started, on the kind's own scope in any attempt, §9.3; ``g_acc``: the round's
        G_acc cells, on the examiner's own scope in any attempt, §3.3, §9.2, ticket C7e-1; ``cell_bench``: the bench
        the cells run on when it is not the step's -- its client, M, timeout and B on the step's scopes, Codex finding
        #4); in the smoke the smoke solver's model (``SmokeStep.model``: chain D's, or glm-5.3 in a chain-G smoke) on
        the smoke ledger's one solver scope, with its ledger bound B (§4.1, §9.3, §10)."""
        if self.smoke is None:
            return units.solver_endpoint(self.setting, self.chain, self.bench, self.k, kind, attempt,
                                         first_run=first_run, g_acc=g_acc, cell_bench=cell_bench)
        on, model = (self.bench if cell_bench is None else cell_bench), self.smoke.model
        bound = ledger_bound(model, on, branch=self.setting.branch, longest=self.setting.longest)
        return budgets.endpoint(self.setting, budgets.solver_scopes(budgets.SMOKE, None, None, "smoke"),
                                client=self.setting.clients(model, on), max_tokens_bound=bound)

    def purpose(self, name):
        """A registration's purpose: the slice's (``run``, ``accept``); in the smoke namespace its one purpose
        ``smoke`` (registry.py, §3.4)."""
        return name if self.smoke is None else budgets.SMOKE

    def verify(self):
        """The pinned files before every unit: the chain's ``check_pins`` (a mismatch terminates the chain); in the
        smoke the manifest check itself (``setting.extra["verify"]``), whose mismatch is raised."""
        if self.smoke is None:
            check_pins(self.setting, self.chain)
        else:
            self.setting.extra.get("verify", lambda: None)()

    def runtime(self, bench=None):
        return self.setting.runtime.get(bench or self.bench)

    def card(self):
        return empty(step=self.name, evidence=self.evidence)

    def unit(self, name, work, *, benches=(), settle=None):
        """Run one sub-step as a copied unit; returns its result (§5: a completed unit is read back). While it runs,
        ``setting`` and ``services.workers`` are the unit's (``units.for_unit``: its tag on every container), the
        consumption registry is bound to the run root (``registry.Registry.bound``: a unit is its label and its run
        root, Codex finding #7) and the unit is drained at its end, completed or paused (``units.drainer``; ticket
        C5-1). ``benches``: the other benches whose cells the unit runs (a self-test's earlier generated sets, §5.5):
        the machine-wide memory lock is the strongest any of them or the step's bench needs (``chain.heavy``; Codex
        finding #5). ``settle(attempt, result)``: the unit's consumption settlement, run by ``units.run_unit`` after the
        attempt's completion evidence is persisted and again by a commit attempt after a recovery (idempotent; Codex
        finding #8)."""
        require(name in self.units, "Unknown sub-step unit")
        self.verify()
        label = self.label(name)
        identity = {"unit": label, "chain": self.chain, "k": self.k, "bench": self.bench,
                    "parent": self.parent.sha256}
        base, services = self.setting, self.services
        self.setting = units.for_unit(base, self.chain, self.bench, label)
        self.services = replace(services, workers=functools.partial(services.workers,
                                                                    tag=self.setting.sandbox["tag"]),
                                registry=services.registry.bound(base.root))
        root = units.unit_path(self.chain_root, self.k, self.bench, name)

        def logged(attempt):  # registrar addendum 15:5x R5: the attempt's role calls, once, whatever its end
            self.calls = []
            try:
                return work(attempt)
            finally:
                role_calls(root, attempt, self.calls)
                self.calls = None

        try:
            with heavy(base, self.bench, *benches):
                found = units.run_unit(root, run=base.run, identity=identity, work=logged, evidence=self.evidence,
                                       configuration=configuration_of(base),
                                       drain=units.drainer(base, self.chain, label), settle=settle)
        finally:
            self.setting, self.services = base, services
        return found["result"]

    def done(self, name):
        """The result of a completed unit of this step, else None."""
        path = units.unit_path(self.chain_root, self.k, self.bench, name) / "unit.json"
        return verified(read_json(path), "unit")["result"] if path.exists() else None


# --------------------------------------------------------------------------------------------------- helpers
def _adjudicator_reason(reply):
    try:
        reason = parse_reply(reply).get("reason")
    except Invalid:
        return None
    return reason if type(reason) is str else None


def role_calls(unit_root, attempt, made):
    """Registrar addendum 2026-10-22 15:5x R5: every role call of one unit attempt (``made``: the attempt's Roles),
    appended once, at the attempt's end, to ``<unit>/role-calls.jsonl``, one JSON object per line: the attempt, role,
    label, request hash, whether the reply was valid and why not, the reply text (the last receipt's response; None
    without one) and, for the leakage adjudicator, its reason. Training side only; no receipt, usage or ledger figure
    and nothing of a consent."""
    n, rows = units.attempt_number(attempt), []
    for roles in made or ():
        for call in roles.calls:
            receipts = [send["receipt"] for send in call.get("sends") or () if isinstance(send.get("receipt"), dict)]
            reply = receipts[-1].get("response") if receipts else None
            reply = reply if type(reply) is str else None
            row = {"attempt": n, "role": call["role"], "label": call["label"], "request_sha256": call["request_sha256"],
                   "valid": call["valid"], "reason": call["reason"], "reply": reply}
            if call["role"] == ADJUDICATOR:
                row["adjudicator_reason"] = _adjudicator_reason(reply)
            rows.append(row)
    if rows:
        with open(safe_path(unit_root) / ROLE_CALLS, "a", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


def _items_of(st, ids):
    """The items of ``ids``: the bench's pool; on SearchQA also its kept fresh tail (acceptance slice, ``_tail``)."""
    by_id = {item["task_id"]: item for item in st.setting.pools[st.bench]}
    if st.smoke is None and st.bench == "searchqa" and not set(ids) <= set(by_id):
        by_id.update((item["task_id"], item) for item in _tail(st)[0])
    return [by_id[i] for i in ids]


TAIL = "searchqa_tail"  # Setting.extra: {"path", "sha256", "exclusion": {"path", "record_sha256"}} (manifest)


def _tail(st):
    """SearchQA's acceptance supply (§3.1 "SearchQA 新块", §3.3; registrar addendum 2026-10-22 17:0x, "SearchQA step:
    ... from the kept fresh tail (exclusion.apply_exclusion -> supply.slices(kept=))"): the tail supply that S0's
    make-items wrote once (``$HIST/supply/searchqa-tail.json``), pinned by the manifest's ``data.searchqa_tail``
    {path, sha256}, without the items its persisted test exclusion dropped -- ``exclusion.apply_exclusion`` with the
    manifest's ``data.exclusion.searchqa_test_exclusion.record_sha256`` on the record ``exclude-tests`` persisted at
    that bound path, so no other exclusion record and no unexcluded tail item reaches a slice (ticket C3-2). Returns
    (the kept items, the sealed ``searchqa-kept`` record that ``supply.slices(kept=)`` requires)."""
    pin = st.setting.extra.get(TAIL)
    require(isinstance(pin, dict) and set(pin) == {"path", "sha256", "exclusion"}
            and isinstance(pin["exclusion"], dict) and {"path", "record_sha256"} <= set(pin["exclusion"]),
            "SearchQA's acceptance slice needs the pinned tail supply and its test exclusion (data.searchqa_tail, "
            "data.exclusion.searchqa_test_exclusion)")
    path = safe_path(pin["path"])
    require(hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"], "The SearchQA tail supply differs from "
            "its pin")
    tail = verified(read_json(path), supply.RECORD_KIND)
    require(tail["name"] == "searchqa-tail" and tail["bench"] == "searchqa", "Not the SearchQA tail supply")
    bound = safe_path(pin["exclusion"]["path"])
    root = bound.parents[2]  # <root>/shared/exclusion/<run>.json, where exclude-tests persisted it
    require(bound == safe_path(root / exclusion.EXCLUSION_DIR / (exclusion.SEARCHQA_RUN + ".json")),
            "The bound SearchQA exclusion record is not a persisted exclude-tests record")
    kept = exclusion.apply_exclusion(tail["items"], root, record_sha256=pin["exclusion"]["record_sha256"])
    return list(kept["items"]), kept


def _alfworld_views(st, cut):
    """Registrar addendum 2026-10-22 17:0x (ALFWorld step on the fresh supply, ticket I1-1): every game of the run and
    acceptance slices carries its registered pre-reset routing view with an intact hash (``solver.routing_view``) and
    was reset with the frozen runtime this run pins (``views_runtime_sha256`` of ``supply.alfworld_pool`` = the digest
    of ``setting.runtime["alfworld"]``); refused before anything is registered. The live reset re-checks each view
    (``solver._solve_alfworld``)."""
    pinned = digest(st.runtime())
    for name in ("run", "accept"):
        for item in cut[name]:
            solver.routing_view(st.bench, item["public"], runtime=st.runtime())
            require(item.get("views_runtime_sha256") == pinned, "An ALFWorld game's pre-reset routing view was not "
                    "made with the runtime this run pins (supply.alfworld_pool)")


def _cut(st, held):
    """The step's slices from its supply (§3.2, §3.3; registrar addendum 2026-10-22 17:0x, the five-bench main
    configuration), ``held`` never entering one: SpreadsheetBench, OfficeQA and LiveMath (run 54 meta-absent + 65
    meta-present, acceptance 100 meta-absent, J7 probe 64 meta-present, purpose ``accept_probe``) by
    ``supply.slices`` on the pool; SearchQA's run slice (300 x 1) from the pool after the smoke's 280, its acceptance
    slice (1,000 x 1) from the kept fresh tail (``_tail``, ``supply.slices(kept=)``); ALFWorld's run (60) and
    acceptance (150) slices from the registered room groups of the fresh-supply pool (§3.1 O6: 16 and 40 rooms of the
    seeded room order, <= 5 games per room; ``supply.alfworld_pool``), each game with its view (``_alfworld_views``)."""
    bench, pool = st.bench, st.setting.pools[st.bench]
    if bench == "zebralogic":
        from . import zebralogic
        sliced = zebralogic.slices(pool)
        cut = {name: sliced[name] for name in ("run", "accept")}
        require(not set(held) & {item["task_id"] for items in cut.values() for item in items},
                "ZebraLogic's registered slices contain already held or consumed items")
        return cut
    sizes = supply.registered_sizes(st.bench)
    if bench == "searchqa":
        items, kept = _tail(st)
        accept = supply.slices(bench, supply.order(bench, items), supply.registered_sizes(bench, "tail"), held,
                               kept=kept)["accept"]
        return {"run": supply.slices(bench, pool, sizes, held)["run"], "accept": accept}
    if bench == "alfworld":
        cut = supply.slices(bench, pool, {name: sizes[name] for name in ("run", "accept")}, held)
        _alfworld_views(st, cut)
        return cut
    return supply.slices(bench, pool, sizes, held)


def _slices(st):
    """{slice: [pool items]} of the step, sealed once in ``slices.json`` (§3.2: consecutive slices of the bench's fixed
    order, ``supply.slices``; per bench ``_cut``: SearchQA's acceptance slice from its kept fresh tail, ALFWorld's by
    room groups). Items another unit of this chain holds, and the smoke's items, never enter a slice; this step's own
    registrations do not shift its slices when it is resumed."""
    path = st.root / SLICES_FILE
    if path.exists():
        value = verified(read_json(path), "step-slices")
        require(value["chain"] == st.chain and value["k"] == st.k and value["bench"] == st.bench,
                "The slices of another step")
        return {name: _items_of(st, ids) for name, ids in value["slices"].items()}
    if st.smoke is not None:  # §10 S4: the mini-step's own cut of its 60 smoke items (v2's SX: of its 260)
        sizes = SX_SLICES if st.smoke.train else S4_SLICES
        items, run = list(st.smoke.items), sizes["run"]
        require(len(items) == run + sizes["accept"], "The smoke step runs on its %d smoke items"
                % (run + sizes["accept"]))
        cut = {"run": items[:run], "accept": items[run:]}
    else:
        # Codex finding #7 (§3.1-§3.4): a unit is its label and its run root; the same labels under another run root
        # are other units, whose held items never enter a slice
        registry, own, here = st.services.registry, {st.label(name) for name in st.units}, run_identity(st.setting.root)
        held = {i for i, line in registry.entries(st.namespace, st.bench).items() if line["state"] in HELD
                and not (line["unit"] in own and line["run_root"] == here)} | set(registry.consumed("smoke", st.bench))
        cut = _cut(st, held)
    require(cut.get("run") and cut.get("accept"), "The bench's supply holds a run and an acceptance slice")
    write_json(path, record("step-slices", st.evidence, {
        "chain": st.chain, "k": st.k, "bench": st.bench,
        "slices": {name: [item["task_id"] for item in items] for name, items in sorted(cut.items())}}))
    return _slices(st)


@contextmanager
def _sheet_inputs(public):
    """A SpreadsheetBench item's public workbook as the sandbox's read-only input directory (``solver._inputs_dir``),
    removed afterwards."""
    directory = solver._inputs_dir(solver._public_view("spreadsheetbench", public)["input_files"][0])
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _item_workers(st, publics):
    """``workers(package, item)`` of the router and the donors: the step's factory, or one derived from
    ``Services.workers`` that mounts a SpreadsheetBench item's public workbook (plan §4)."""
    if st.services.item_workers is not None:
        return st.services.item_workers

    @contextmanager
    def factory(package, item):
        sheet = st.bench == "spreadsheetbench" and item in publics
        with (_sheet_inputs(publics[item]) if sheet else nullcontext()) as inputs:
            with st.services.workers(package, kind="cell", inputs_dir=inputs) as worker:
                yield worker

    return factory


def _cells(st, attempt, endpoint, unit, jobs, *, tag):
    """Cells of generated items (probes, self-test): ``jobs`` = [(arm label, Arm, item id, run, task)], run with
    ``cells.run_cells`` in one seeded order of the unit (§6.2); task ids are the generated ids. ``endpoint``: the
    attempt's endpoint when every job is on the step's bench, else {bench: endpoint} with one per job bench (a
    self-test's earlier generated sets: each cell its own bench's client, M, timeout and B on the step's scopes,
    ``cells.Context.endpoints``; Codex finding #4). A task's ``shortcut``
    (a shortcut-probe cell's mode, ``examiner.probe_mode``) becomes the cell's, which ``cells.run_cell`` hands to the
    shell and states in the record (registrar decision on ticket C1-2; ticket PR-C12-1); a cell without one has no
    such key."""
    endpoints = dict(endpoint) if isinstance(endpoint, dict) else {st.bench: endpoint}
    require(endpoints and {task["benchmark"] for *_, task in jobs} <= set(endpoints),
            "An endpoint for every cell's bench")
    built = []
    for arm, chosen, item, run, task in jobs:
        cell = {"id": cell_id(unit, arm, item, run), "unit": unit, "arm": arm, "benchmark": task["benchmark"],
                "task_id": item, "run": run,
                **({"shortcut": task["shortcut"]} if task.get("shortcut") is not None else {})}
        built.append((cell, {"public": task["public"], "private": task["private"]}, chosen))
    order = rounds._order(list(range(len(built))), round_tag(unit) + ":" + tag)
    built = [built[i] for i in order]
    first = endpoints[st.bench] if st.bench in endpoints else endpoints[min(endpoints)]
    context = replace(units.cell_context(st.setting, attempt, first), endpoints=endpoints)
    return run_cells(context, built, workers=st.setting.workers, store=TrainingStore(attempt))


def _task(item):
    item = verified(item, "generated-item")
    return {"benchmark": item["benchmark"], "public": item["public"], "private": item["private"]}


def _run_trajectories(st, k=None, bench=None, *, parent_only=False):
    root = units.unit_path(st.chain_root, k or st.k, bench or st.bench, "run")
    found = trajectories.load_run(root)
    return [t for t in found if t["arm_kind"] == "parent"] if parent_only else found


def _earlier(st, unit):
    """[(k, bench, unit result)] of the earlier steps' completed ``unit`` in this chain, in step order."""
    out = []
    for path in sorted(st.chain_root.glob("s*-*/%s/unit.json" % unit)):
        step_dir = path.parent.parent.name
        k, bench = step_dir[1:].split("-", 1)
        if int(k) < st.k:
            out.append((int(k), bench, verified(read_json(path), "unit")["result"]))
    return sorted(out, key=lambda entry: entry[0])


# ------------------------------------------------------------------------------------------------- 5.1 run
def _firing_share(st, items, workers):
    """The share of run-slice items on which S's procedures for the bench fire (zero calls, ``router.route``)."""
    if not st.parent.for_bench(st.bench):
        return Fraction(0)
    fired = 0
    for item in items:
        view = solver.routing_view(st.bench, item["public"], runtime=st.runtime())
        with workers(st.parent, item["task_id"]) as worker:
            fired += bool(router.route(st.parent, st.bench, view, worker).enabled)
    return Fraction(fired, len(items))


def _entry_reading(cells):
    """§5.1: the descriptive S - C on the run slice (never a decision)."""
    tokens = rounds.tokens(cells)
    items = sorted(i for (arm, i) in tokens if arm == "C")

    def rate(arm, item):
        found = tokens[(arm, item)]
        return sum(t == "pass" for t in found) / len(found)

    differences = [rate("S", i) - rate("C", i) for i in items]
    return {"items": len(items), "mean_s_minus_c": fmean(differences) if differences else None, "decides": False}


def cost_projection(setting, chain, bench, k, cells, attempt=1):
    """§9.3, owner rule 22:3x (c): the zero-call projection of chain G's scopes after its first run unit. The measured
    tokens per cell (settled on the run scope of the attempt that completed the unit / that attempt's cells; after a
    redo, ``attempt`` >= 2 and its own redo scope, registrar addendum 2026-10-22 15:5x R6 (e)) over the bench's
    registered high anchor rescale every chain-G cap's maximum-schedule estimate (cap / 1.5; cap / the run
    configuration's factor, ``protocol.CONFIG_CAP_FACTOR``: main's caps are 3 x their need); a scope whose projection
    exceeds its cap is a breach. The first-call confirmation's scope ``G:confirm`` (registrar addendum 14:10, row 7) was
    spent before the first unit and has no schedule: it is not projected. Returns ``chain.cap_check``'s ``measured``."""
    snapshot = setting.budget.snapshot()
    run_scope = budgets.solver_scopes(chain, bench, k, "run", attempt)[-1]
    require(cells > 0 and run_scope in snapshot, "The first run unit's cells and its scope")
    per_cell = Fraction(snapshot[run_scope]["settled"], cells)
    factor = per_cell / CELL_ANCHORS[bench][1]
    cap_factor = CONFIG_CAP_FACTOR[configuration_of(setting)]  # registrar 17:0x: the configuration's caps
    scopes = {}
    for scope, entry in snapshot.items():
        if scope.startswith(chain + ":") and isinstance(entry, dict) and not scope.startswith(chain + ":glm") \
                and ":role:" not in scope and scope != "%s:%s" % (chain, budgets.CONFIRM):
            projected = math.ceil(entry["cap"] / cap_factor * factor)
            scopes[scope] = {"cap": entry["cap"], "projected": projected}
    return {"ok": all(v["projected"] <= v["cap"] for v in scopes.values()), "per_cell": float(per_cell),
            "anchor_high": CELL_ANCHORS[bench][1], "scopes": scopes}


def _run(st, cut):
    bench, items = st.bench, cut["run"]
    runs = SLICES[bench]["run"][1]
    tasks = {rounds.key(bench, item["task_id"]): {"public": item["public"], "private": item["private"]}
             for item in items}
    name = st.label("run")

    def work(attempt):
        n, endpoint = units.attempt_number(attempt), st.solver("run", attempt)  # refused before anything is held
        registry = st.services.registry
        registry.register(st.namespace, bench, items, unit=name, purpose=st.purpose("run"),
                          run_root=str(st.setting.root), attempt=n)
        share = _firing_share(st, items, _item_workers(st, {i["task_id"]: i["public"] for i in items}))
        arms, schedule = {"S": Arm("parent", st.parent)}, {"S": [(key, runs) for key in sorted(tasks)]}
        if share >= ENTRY_READING_SHARE:
            arms["C"] = Arm("card", st.card())
            schedule["C"] = [(key, 1) for key in sorted(tasks)]
        registry.dispatch(st.namespace, bench, items, unit=name, attempt=n)
        cells = rounds.run_round(st.setting, attempt, endpoint, name, arms, schedule, tasks, tag="run")
        rounds.guard(cells, list(arms), name)
        return {"items": len(items), "runs": runs, "cells": sum(len(found) for found in cells.values()),
                "firing_share": float(share), "entry_reading": _entry_reading(cells) if "C" in arms else None}

    def settle(attempt, result):  # Codex finding #8: after the completion evidence; again, idempotent, on a recovery
        st.services.registry.decide(st.namespace, bench, items, unit=name, attempt=units.attempt_number(attempt))

    result = st.unit("run", work, settle=settle)
    if st.chain == "G" and st.k == 1:  # the attempt that completed the unit: its spend and its cells (15:5x R6 (e))
        root = units.unit_path(st.chain_root, st.k, bench, "run")
        done = verified(read_json(root / "unit.json"), "unit")
        cap_check(st.setting, "G", 1, cost_projection(st.setting, st.chain, bench, st.k, result["cells"],
                                                      attempt=units.attempt_number(root / done["attempt"])))
    return result


# --------------------------------------------------------------------------------------------- 5.2 diagnose
def _rooms(st, cut):
    if st.bench != "alfworld":
        return None
    return {rounds.key(st.bench, item["task_id"]): item["room"] for item in cut["run"]}


def _library(st):
    """The bench's accepted detectors from earlier steps of this chain (§7.1)."""
    out = []
    for _, bench, result in _earlier(st, "diagnose"):
        if bench == st.bench:
            out += [detectors.Detector(id=d["id"], bench=d["bench"], source=d["source"], description=d["description"])
                    for d in result["detectors"] if d["validation"].get("accepted")]
    return out


def _diagnose(st, cut):
    name = st.label("diagnose")

    def work(attempt):
        stored = _run_trajectories(st, parent_only=True)
        rooms = _rooms(st, cut)
        halves = detectors.split(stored, bench=st.bench, unit=name, rooms=rooms)
        library = _library(st)
        payload = examiner.detector_payload(halves, bench=st.bench, library=library, workers=st.services.workers)
        candidates, written = examiner.detector_write(st.roles("examiner"), payload, k=st.k, label=name,
                                                      evidence=st.evidence)
        split = {key: value for key, value in halves.items() if key not in ("write", "hold")}
        out = {"split": split, "written": written, "validation": None, "detectors": []}
        if candidates:
            source = name + "/write-half"
            sealed = detectors.seal_candidates(attempt, candidates, unit=name, written_from=source,
                                               evidence=st.evidence)
            validation = detectors.validate(sealed, candidates, halves, bench=st.bench, library=library,
                                            workers=st.services.workers, rooms=rooms, evidence=st.evidence)
            out["validation"] = validation
            out["detectors"] = detectors.detector_records(validation, candidates, written_from=source,
                                                          evidence=st.evidence)
        return out

    return st.unit("diagnose", work)


# --------------------------------------------------------------------------------------------- 5.3 generate
def _generator_id(st):
    return "g-%s-%d-1" % (st.bench, st.k)


def _derived(attempt, set_name):
    """The finding-keyed counter persisted by the attempt's latest build of ``set_name`` ({} before its first; Codex
    finding #10)."""
    latest = None
    for path in safe_path(attempt).glob(FINDING_COUNTS % "*"):
        value = verified(read_json(path), "finding-counts")
        if value["set"] == set_name and (latest is None or value["build"] > latest["build"]):
            latest = value
    return dict(latest["derived"]) if latest else {}


def _build(st, specs, materials, set_name, sources, attempt, start):
    """One ``examiner.build`` of this step's generator, its items numbered from ``start`` (ticket C4-1). The ten items
    per finding (§7.2, plan T-GEN-6) count across the attempt's builds of the set: the build continues the counter its
    previous build persisted and persists its own (``finding-counts-<n>.json``, write-once per build), so the band
    adjustments, which rebuild from the same findings, never derive more than ten items from one (Codex finding #10).
    On LiveMath the whole build holds one checker session (``WorkerChecker.session``: one generator worker for every
    solve, from the unit's tag-bound workers while ``_Step.unit`` runs; ticket I1-2, registrar addenda 14:3x row
    C7d-2, 14:4x)."""
    generator = _generator_id(st)
    out_dir = attempt / ("generated-" + set_name) if st.bench == "spreadsheetbench" else None
    checker = st.services.checker
    session = checker.session() if st.bench == "livemath" and hasattr(checker, "session") else nullcontext()
    with session:
        built = examiner.build(specs, materials, bench=st.bench, generator=generator, set_name=set_name,
                               seed=generator_seed(generator, st.name), evidence=st.evidence, start=start,
                               derived=_derived(attempt, set_name),
                               sources=sources if st.bench == "spreadsheetbench" else None,
                               checker=checker, engine=st.services.engine, out_dir=out_dir)
    if isinstance(built, examiner.Generated):  # a stand-in for ``examiner.build`` (a test fake) carries no counter
        n = 1 + len(list(safe_path(attempt).glob(FINDING_COUNTS % "*")))
        write_json(attempt / (FINDING_COUNTS % n), record("finding-counts", st.evidence, {
            "generator": generator, "set": set_name, "build": n, "start": start, "derived": built.derived}))
    return built


def _probe_band(st, attempt, endpoint, built, n):
    """One band probe: S once on at most 30 probe items of the set (§7.2), charged to ``...:examiner``."""
    probe = examiner.probe_items(built.items, generator=built.generator, purpose="band")
    jobs = [("S", Arm("parent", st.parent), item["id"], 0, _task(item)) for item in probe]
    return _cells(st, attempt, endpoint, st.label("generate/band-%d" % n), jobs, tag="band")


def _probe_shortcut(st, attempt, endpoint, built):
    """The shortcut probe: C twice on the shortcut variants of at most 30 items (§7.2 "表格题去掉工作簿, 2 次都答对的题
    丢掉"; §9.2: the card arm, 30 items x 2 runs), each cell in its bench's probe mode (``examiner.probe_mode``):
    SpreadsheetBench's variant keeps its real input files and is solved without the workbook (``solver.NO_WORKBOOK``,
    registrar decision on ticket C1-2; wired here by ticket PR-C12-1), OfficeQA's and LiveMath's variants blank a
    public field and run in no mode. ``examiner.shortcut`` refuses a probe cell that did not run in its bench's mode.
    None when the set holds no item."""
    if not built.items:
        return None
    probe = examiner.probe_items(built.items, generator=built.generator, purpose="shortcut")
    variants = [examiner.shortcut_variant(item) for item in probe]
    card = Arm("card", st.card())
    jobs = [("C", card, variant["id"], run, {**_task(variant), "shortcut": examiner.probe_mode(variant)})
            for variant in variants for run in (0, 1)]
    return _cells(st, attempt, endpoint, st.label("generate/shortcut"), jobs, tag="shortcut")


def _sources(cut, bench):
    """SpreadsheetBench specs edit run-slice source tasks, never an acceptance or test item (ticket C1-3)."""
    if bench != "spreadsheetbench":
        return None
    return {item["task_id"]: item for item in cut["run"]}


def _generate(st, cut):
    name = st.label("generate")
    if generators.mode(st.bench) != "families":
        return st.unit("generate", lambda attempt: {"mode": generators.mode(st.bench), "generator": None,
                                                     "reason": "no registered family on this bench (§7.2)"})

    def work(attempt):
        previous = [result for _, bench, result in _earlier(st, "generate") if bench == st.bench]
        last = previous[-1] if previous else None
        payload = examiner.policy_payload(st.bench, previous=last and last["policy"],
                                          outcomes=last and last["outcomes"])
        roles, train = st.roles("examiner"), st.learning == TRAIN
        policy, policy_record = examiner.policy_revise(roles, payload, label=name, evidence=st.evidence, train=train)
        researcher = research.Researcher(st.roles("examiner_research"), st.services.sources,
                                         Corpus(st.bench, cut["run"]), bench=st.bench, label=name + "/research")
        sent = examiner.research_requests(policy, researcher)
        found = [finding for _, finding in sent if finding["status"] == "found"]
        halves = research.split(found, name, evidence=st.evidence)
        write_json(attempt / "research-split.json", halves)  # sealed before the engineer step (§5.3)
        sources = _sources(cut, st.bench)
        shown = {key: solver.routing_view(st.bench, item["public"], runtime=st.runtime())
                 for key, item in (sources or {}).items()} or None
        endpoint = st.solver("examiner", attempt)
        specs, written = examiner.generator_write(roles, examiner.generator_payload(st.bench, halves["g_self"],
                                                                                  sources=shown),
                                                  label=name, evidence=st.evidence, train=train)
        built, probes, fresh = _build(st, specs, halves["g_self"], "G_self", sources, attempt, 0), [], True
        topups = []
        if train:  # v2: a short set gets up to TOPUP_ROUNDS top-up calls (``_topup``)
            built, specs, made = _topup(st, roles, built, specs, halves, shown, sources, attempt, name)
            topups += made
        for n in range(1, BAND_ROUNDS + 1):
            if not examiner.sufficient(built):  # §7.2, Codex finding #9: 30 qualified probe items, else no paid probe
                break
            probes.append(_probe_band(st, attempt, endpoint, built, n))
            band, fresh = examiner.band(probes, [item["id"] for item in built.items]), False
            if band["in_band"] or n == BAND_ROUNDS:
                break
            adjusted = examiner.generator_payload(st.bench, halves["g_self"], sources=shown, band=band)
            specs, written = examiner.generator_write(roles, adjusted, label="%s/band-%d" % (name, n),
                                                      evidence=st.evidence, train=train)
            built, fresh = _build(st, specs, halves["g_self"], "G_self", sources, attempt, built.next_number), True
            if train:
                built, specs, made = _topup(st, roles, built, specs, halves, shown, sources, attempt,
                                            "%s/band-%d" % (name, n))
                topups += made
        enough = examiner.sufficient(built)  # an insufficient final set is recorded as such, never probed or admitted
        gated = examiner.gates(built, {"band": probes if enough and not fresh else [],
                                       "shortcut": _probe_shortcut(st, attempt, endpoint, built) if enough else None},
                               evidence=st.evidence)
        frozen = examiner.generator_record(gated, specs, evidence=st.evidence)
        kept = [item for item in built.items if item["id"] in set(gated["kept"])]
        return {"mode": "families", "policy": policy, "policy_record": policy_record[RECORD_HASH],
                "research": [finding for _, finding in sent], "split": halves, "specs_record": written,
                "outcomes": examiner.outcome_counts([gated], research=sent, generator_records=[frozen]),
                "generator": frozen, "gates": gated, "g_self": kept, "numbered": built.next_number,
                "derived": built.derived, **({"learning": TRAIN, "topups": topups} if train else {})}

    return st.unit("generate", work)


def _topup(st, roles, built, specs, halves, shown, sources, attempt, label):
    """v2: up to ``TOPUP_ROUNDS`` further generator calls (``GENERATOR_SYSTEM_V2`` with ``examiner.topup``'s hint)
    while the set ``built`` holds fewer items than its band probe needs (``examiner.sufficient``); each call's specs
    are built on -- numbered from the set's next number, the per-finding counter continued (``_build``) -- and joined
    to the set (``examiner.joined``). Returns (the set, its specs renumbered, the calls' sealed records)."""
    made = []
    for n in range(1, TOPUP_ROUNDS + 1):
        if examiner.sufficient(built):
            break
        payload = examiner.generator_payload(st.bench, halves["g_self"], sources=shown, topup=examiner.topup(built, n))
        more, written = examiner.generator_write(roles, payload, label="%s/topup-%d" % (label, n),
                                                 evidence=st.evidence, train=True)
        made.append(written)
        if more:
            built = examiner.joined(built, _build(st, more, halves["g_self"], "G_self", sources, attempt,
                                                  built.next_number))
            specs = [{**spec, "n": i} for i, spec in enumerate(list(specs) + list(more), 1)]
    return built, specs, made


# --------------------------------------------------------------------------------------------- 5.4 engineer
def _scalar(value):
    """A reference cell value in the frozen answer shape: a text or a finite number (an empty cell "", a boolean
    TRUE/FALSE, a date or time in ISO form, anything else as text)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if type(value) in (int, float) and math.isfinite(value):
        return value
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _sheet_reference(private):
    """§4.2 on SpreadsheetBench (registrar addendum 2026-10-22 15:5x R1): a failed run item's reference is the cell
    values at its answer position in its first answer workbook (the pair of the input the solver's preview shows), read
    as the frozen scorer reads a reference (``spreadsheet_compat.evaluate``: openpyxl's cached values, the targets of
    ``resolve_targets``, the official cell order; a formula cell's explicit empty-string cache is ""):
    {"<sheet>!<cell>": ``_scalar`` value}, the table shape ``engineer._answer_shape`` takes. None when the workbook
    gives no complete reading (an unavailable formula cache, an unresolved target, an unreadable file)."""
    from openpyxl import load_workbook

    path = private["test_files"][0]
    try:
        blanks = spreadsheet_compat.explicit_empty_formula_strings(path)
        values = load_workbook(path, data_only=True, keep_links=False)
        formulas = load_workbook(path, data_only=False, keep_links=False)
        try:
            out = {}
            targets = spreadsheet_compat.resolve_targets(private["answer_position"], values.sheetnames)["targets"]
            for sheet, region in targets:
                for coordinate in spreadsheet_compat._legacy()._iter_cell_names(region):
                    value = values[sheet][coordinate].value
                    if formulas[sheet][coordinate].data_type == "f" and value is None:
                        if (sheet, coordinate) not in blanks:
                            return None  # the frozen scorer's "unavailable": no complete reading
                        value = ""
                    out["%s!%s" % (sheet, coordinate)] = _scalar(value)
            return out or None
        finally:
            values.close()
            formulas.close()
    except (spreadsheet_compat.CompatibilityError, OSError, ValueError, KeyError, TypeError, ET.ParseError,
            zipfile.BadZipFile):
        return None


def _references(st, cut, parents, also=()):
    """§4.2: the reference answers of this bench's run-slice items the parent failed (v2: and of the items ``also``,
    whose references earlier training rounds disclosed), never on ALFWorld; a frozen answer shape only: an answer text
    or SearchQA's answer list, and on SpreadsheetBench the answer-position cell values of the item's answer workbook
    (``_sheet_reference``; registrar addendum 2026-10-22 15:5x R1). ZebraLogic retains its grid references, verified
    against this run unit's decided consumption entries before any reference is selected."""
    if st.bench == "alfworld":
        return {}
    failed = {t["task_id"] for t in parents if t["token"] == "fail"} | set(also)
    if st.bench == "zebralogic":
        from skillopt.coevo5.data import item_hash
        consumed = st.services.registry.entries(st.namespace, st.bench)
        for item in cut["run"]:
            entry = consumed.get(item["task_id"], {})
            require(entry.get("state") == "decided" and entry.get("unit") == st.label("run")
                    and entry.get("purpose") == st.purpose("run")
                    and entry.get("run_root") == run_identity(st.setting.root)
                    and entry.get("item_hash") == item_hash(item),
                    "Zebra references require this unit's consumed run items with their registered identities")
    out = {}
    for item in cut["run"]:
        key = rounds.key(st.bench, item["task_id"])
        if key not in failed:
            continue
        if st.bench == "spreadsheetbench":
            reference = _sheet_reference(item["private"])
        else:
            reference = item["private"].get("answer", item["private"].get("answers"))
        if isinstance(reference, (str, list, dict)) and reference:
            out[key] = reference
    return out


def _previous(st):
    """§4.2: the previous step's outcome as counts -- accepted / not accepted, its fault items and S' format-violating
    items (None at the chain's first step)."""
    steps = sorted(st.chain_root.glob("s%d-*/%s" % (st.k - 1, STEP_FILE))) if st.k > 1 else []
    if not steps:
        return None
    value = verified(read_json(steps[0]), "step")
    return {"decision": "accepted" if value["decision"] == "accept" else "not_accepted",
            "faults": {"fault_items": value["fault_items"]}, "format": {"violating_items": value["violating_items"]}}


def _corpora(st, cut):
    """Current corpus under its benchmark identity; repeated earlier slices retain their step provenance.
    A chain without repeated benchmarks retains exactly its historical keys, order and corpus contents."""
    out = {st.bench: Corpus(st.bench, cut["run"])}
    for k, bench, _ in _earlier(st, "run"):
        value = verified(read_json(st.chain_root / ("s%d-%s" % (k, bench)) / SLICES_FILE), "step-slices")
        by_id = {item["task_id"]: item for item in st.setting.pools[bench]}
        corpus = Corpus(bench, [by_id[i] for i in value["slices"]["run"]])
        if bench in out:
            corpus.provenance = {"bench": bench, "k": k, "step": "s%d-%s" % (k, bench),
                                 "slices_sha256": value[RECORD_HASH]}
            out["%s@s%d" % (bench, k)] = corpus
        else:
            out[bench] = corpus
    return out


@contextmanager
def _inputs_dirs(st, stored, cut):
    """{cell: the public input directory} of every stored SpreadsheetBench trajectory the replays may run on (their
    /input), removed afterwards; None when ``stored`` holds none. Whatever this step's bench: a later step's C6/C7
    replay of a procedure in SpreadsheetBench's scope runs on an earlier SpreadsheetBench step's trajectories too, each
    with its own item's workbook (registrar addendum 2026-10-22 15:5x R2). The publics, by item key (a trajectory's
    ``task_id`` is ``rounds.key``): the bench's pool, and this step's run slice on SpreadsheetBench."""
    sheet = "spreadsheetbench"
    sheets = [trajectory for trajectory in stored if trajectory["bench"] == sheet]
    if not sheets:
        yield None
        return
    publics = {rounds.key(sheet, item["task_id"]): item["public"] for item in st.setting.pools.get(sheet, ())}
    if st.bench == sheet:
        publics.update({rounds.key(sheet, item["task_id"]): item["public"] for item in cut["run"]})
    made = {}
    try:
        for trajectory in sheets:
            require(trajectory["task_id"] in publics, "A stored SpreadsheetBench trajectory of a known item")
            view = solver._public_view(sheet, publics[trajectory["task_id"]])
            made[trajectory["cell"]] = solver._inputs_dir(view["input_files"][0])
        yield made
    finally:
        for directory in made.values():
            shutil.rmtree(directory, ignore_errors=True)


def _engineer(st, cut, unit, previous):
    name = st.label(unit)

    def work(attempt):
        # R7a (registrar addendum 2026-10-22, R7 decision 16:1x): ENGINEER_CALLS is per step; engineer-2 gets the
        # calls the completed first engineer unit left, and a redo attempt restarts its own count
        spent = 0 if unit == "engineer" else st.done("engineer")["engineer"]["calls"]
        stored = []
        for k, bench, _ in _earlier(st, "run"):
            stored += _run_trajectories(st, k, bench)
        own = _run_trajectories(st)
        stored += own
        parents = [t for t in own if t["arm_kind"] == "parent"]
        with _inputs_dirs(st, stored, cut) as inputs:
            ctx = engineer.Context(bench=st.bench, k=st.k, step=st.name, evidence=st.evidence, parent=st.parent,
                                   trajectories=stored, corpora=_corpora(st, cut), workers=st.services.workers,
                                   roles=st.roles("engineer"), label=name,
                                   card=st.setting.cards.get(st.bench, ""), references=_references(st, cut, parents),
                                   inputs_dirs=inputs,
                                   detectors=detectors.counts(detectors.diagnosis(parents, bench=st.bench)),
                                   previous=previous, spent=spent, configuration=configuration_of(st.setting))
            candidate, sealed = engineer.run(ctx)
        if candidate is not None:
            save(st.chain_root, candidate)
        return {"engineer": sealed, "candidate_sha256": candidate.sha256 if candidate is not None else None}

    return st.unit(unit, work)


def _package(st, sha):
    return load(st.chain_root / "packages" / (sha + ".json"))


# --------------------------------------------------------------------------------------------- 5.5 self-test
def _sets(st, generated):
    """{bench: [generated items]} of the self-test: G_self of this step (<= 60) and each earlier bench's set (<= 40,
    the first in the seeded order)."""
    out = {}
    if generated and generated.get("g_self"):
        out[st.bench] = generated["g_self"][:G_SELF_MAX]
    for _, bench, result in _earlier(st, "generate"):
        if bench != st.bench and result.get("g_self"):
            out[bench] = ranked(list(result["g_self"]), SEED, "execskill-v1:selftest:" + bench)[:EARLIER_SET_MAX]
    return out


def _one_sided_sign(worse, better):
    """P(X >= worse) for X ~ Binomial(worse + better, 1/2): the exact one-sided sign test (§5.5 (b))."""
    n = worse + better
    if n == 0:
        return 1.0
    return sum(math.comb(n, j) for j in range(worse, n + 1)) / 2 ** n


def _changed_ids(parent, candidate):
    """The ids of the procedures ``candidate`` adds or revises against ``parent`` (§6.1 edits)."""
    return {edit.new.id for edit in edits(parent, candidate) if edit.kind in ("new", "revision")}


def _token(cell):
    return ((cell.get("judge") or {}).get("v2") or {}).get("token")


def selftest_verdict(cells, sets, changed, *, identical=None, request_faults=None):
    """§5.5: the two registered blocks, from the cell records alone. ``cells``: the self-test's cell records (arms
    S' and S, one run); ``sets``: {bench: [item ids]}; ``changed``: the ids of the procedures the step adds or revises.
    (a) S' cells with a fault of a changed procedure or a re-execution ``unknown_fault`` (J3's rule, Codex F22) > 2 %;
    S' cells with only an inherited procedure's fault are counted apart, never blocking; (b) on any set, S's
    format-violating share exceeded by >= 5 points with a one-sided exact sign test p < 0.05. Accuracy is recorded,
    never blocking."""
    by = {(c["cell"]["arm"], c["cell"]["task_id"]): c for c in cells}
    candidate = [c for c in cells if c["cell"]["arm"] == "S'"]

    def own_fault(cell):
        return (_token(cell) == "unknown_fault" or cell["cell"]["task_id"] in (request_faults or [])
                or any(f.get("procedure") in changed for f in cell.get("faults") or []))

    faulted = sum(1 for c in candidate if own_fault(c))
    inherited = sum(1 for c in candidate if c.get("faults") and not own_fault(c))
    skipped = sum(len(ids) for ids in (identical or {}).values())
    total = len(candidate) + skipped
    fault_share = Fraction(faulted, total) if total else Fraction(0)
    rows = {}
    for bench, ids in sorted(sets.items()):
        evaluated = [i for i in ids if i not in (identical or {}).get(bench, [])]
        def violates(arm, item):
            judge = by[(arm, item)].get("judge") or {}
            return bool((judge.get("format") or {}).get("violation"))

        def passed(arm, item):
            return _token(by[(arm, item)]) == "pass"

        worse = sum(1 for i in evaluated if violates("S'", i) and not violates("S", i))
        better = sum(1 for i in evaluated if violates("S", i) and not violates("S'", i))
        gap = Fraction(sum(violates("S'", i) for i in evaluated) - sum(violates("S", i) for i in evaluated), len(ids))
        p = _one_sided_sign(worse, better)
        rows[bench] = {"items": len(ids), "format_gap": float(gap), "worse": worse, "better": better, "p_sign": p,
                       "blocks": gap >= SELFTEST_FORMAT_MARGIN and p < SELFTEST_ALPHA,
                       "accuracy": {arm: sum(passed(arm, i) for i in evaluated) / len(evaluated)
                                    if evaluated else None for arm in ("S'", "S")},
                       **({"identical": len(ids) - len(evaluated), "accuracy_items": len(evaluated)}
                          if identical is not None else {})}
    blocked = fault_share > SELFTEST_FAULT_MAX or any(row["blocks"] for row in rows.values())
    return {"fault_cells": faulted, "inherited_fault_cells": inherited, "candidate_cells": len(candidate),
            "fault_share": float(fault_share), "fault_blocks": fault_share > SELFTEST_FAULT_MAX, "sets": rows,
            "blocked": blocked, **({"identical": identical, "skipped_items": skipped, "fault_items_denominator": total}
                                   if identical is not None else {})}


def _pair_signatures(st, candidate, parent, publics, views):
    """v2.3: the two exact requests and post-call identities on full public views, with zero model calls."""
    if st.bench not in request_reuse.BENCHES:
        return {}
    workers, out = _item_workers(st, publics), {}
    for item, view in views:
        out[item] = {}
        for arm, package in (("S'", candidate), ("S", parent)):
            with workers(package, item) as worker:
                out[item][arm] = request_reuse.signature(st.bench, package, view, worker,
                                                       card_text=st.setting.cards.get(st.bench, ""), runtime=st.runtime())
    return out


def _selftest(st, unit, candidate, generated):
    def work(attempt):
        sets = _sets(st, generated)
        if not sets:
            return {"sets": {}, "blocked": False, "reason": "no_generated_items", "cells": 0}
        identical, sealed = None, None
        if IDENTICAL_REQUEST_REUSE[configuration_of(st.setting)]:
            path = units.unit_path(st.chain_root, st.k, st.bench, unit) / "request-plan.json"
            identity = {"candidate": candidate.sha256, "parent": st.parent.sha256,
                        "sets": {b: [i["id"] for i in items] for b, items in sets.items()}, "sets_sha256": digest(sets)}
            if path.exists():
                sealed = verified(read_json(path), "selftest-requests-v2-3")
                require(sealed["identity"] == identity, "A resumed self-test keeps its sealed requests")
            else:
                signatures, identical = {}, {}
                for bench, items in sets.items():
                    public = {item["id"]: item["public"] for item in items}
                    views = [(key, solver.routing_view(bench, value, runtime=st.runtime(bench)))
                             for key, value in public.items()] if bench in request_reuse.BENCHES else []
                    signatures[bench] = _pair_signatures(replace(st, bench=bench), candidate, st.parent, public, views)
                    identical[bench] = [key for key, arms in signatures[bench].items()
                                        if request_reuse.interchangeable(arms["S'"], arms["S"], bench=bench)]
                sealed = record("selftest-requests-v2-3", st.evidence,
                                {"identity": identity, "signatures": signatures, "identical": identical})
                write_json(path, sealed)
            identical = sealed["identical"]
        jobs = [(arm, Arm(kind, package), item["id"], 0, _task(item))
                for bench, items in sets.items() for item in items
                if item["id"] not in (identical or {}).get(bench, [])
                for arm, kind, package in (("S'", "candidate", candidate), ("S", "parent", st.parent))]
        # Codex finding #4: each set's cells on its own bench's client, M, timeout and B, charged to this step's
        # ...:selftest scope, in the one seeded interleaving
        endpoints = {bench: st.solver("selftest", attempt, cell_bench=bench) for bench in sorted(sets)} if jobs else {}
        cells = _cells(st, attempt, endpoints, st.label(unit), jobs, tag="selftest") if jobs else []
        changed = _changed_ids(st.parent, candidate)
        request_faults = (sorted({item for items in sealed["signatures"].values() for item, arms in items.items()
                                 if any(f.get("procedure") in changed for f in arms["S'"]["faults"])})
                          if sealed is not None else None)
        verdict = selftest_verdict(cells, {b: [i["id"] for i in items] for b, items in sets.items()},
                                   changed, identical=identical, request_faults=request_faults)
        return {**verdict, "cells": len(cells), "reason": "identical_requests_no_calls" if not jobs else None,
                **({"request_plan_sha256": sealed[RECORD_HASH], "version": "paired-selftest-v2-3",
                    "request_fault_items": request_faults}
                   if sealed is not None else {})}

    # Codex finding #5: the memory lock of every bench the self-test's cells run on (an earlier SpreadsheetBench set)
    return st.unit(unit, work, benches=tuple(sorted(_sets(st, generated))))


def _candidate(st, cut, generated):
    """5.4-5.5: ``(S', None)`` when a candidate passed the self-test, else ``(the last S' or None, the not-run
    outcome)``: no surviving change, no surviving change after a first block, or a second block (two self-tests,
    ``SELFTEST_PASSES``)."""
    require(SELFTEST_PASSES == 2, "Two self-tests per step (§5.5)")
    engineered = _engineer(st, cut, "engineer", _previous(st))
    if engineered["candidate_sha256"] is None:
        return None, _release("no_surviving_change")
    candidate = _package(st, engineered["candidate_sha256"])
    verdict = _selftest(st, "selftest", candidate, generated)
    if not verdict["blocked"]:
        return candidate, None
    counts = {"decision": "not_accepted", "faults": {"selftest_fault_cells": verdict["fault_cells"]},
              "format": {b: {"worse_items": row["worse"]} for b, row in verdict["sets"].items()}}
    again = _engineer(st, cut, "engineer-2", counts)
    if again["candidate_sha256"] is None:
        return candidate, _release("no_surviving_change_after_selftest")
    candidate = _package(st, again["candidate_sha256"])
    if _selftest(st, "selftest-2", candidate, generated)["blocked"]:
        return candidate, _release("selftest_blocked_twice")
    return candidate, None


# ------------------------------------------------------------------------------------- v2: the training rounds
def _unit_trajectories(st, name):
    return trajectories.load_run(units.unit_path(st.chain_root, st.k, st.bench, name))


def _run_keys(st, cut):
    return {rounds.key(st.bench, item["task_id"]) for item in cut["run"]}


def _current(st, done):
    """v2: the incumbent's latest cells of the run-slice items: the run unit's parent cells, replaced item by item by
    the S' cells of each adopting training round and the S cells of each other one (each the incumbent of its time), in
    round order (``done``: [(train unit, adopted)])."""
    by_item = {}
    for trajectory in _run_trajectories(st, parent_only=True):
        by_item.setdefault(trajectory["task_id"], []).append(trajectory)
    for name, adopted in done:
        fresh = {}
        for trajectory in _unit_trajectories(st, name):
            if trajectory["task_id"] in by_item and trajectory["arm"] == ("S'" if adopted else "S"):
                fresh.setdefault(trajectory["task_id"], []).append(trajectory)
        by_item.update(fresh)
    return [trajectory for item in sorted(by_item) for trajectory in by_item[item]]


def _evaluated(st, cut, fed):
    """v2: the run-slice cells (both arms) of the training unit ``fed`` whose feedback the engineer is shown."""
    if fed is None:
        return []
    keys = _run_keys(st, cut)
    return [trajectory for trajectory in _unit_trajectories(st, fed) if trajectory["task_id"] in keys]


def _distinct(found):
    """The trajectories once per cell, in order."""
    return list({trajectory["cell"]: trajectory for trajectory in found}.values())


def _training_publics(cut, generated, bench):
    """v2.3 Amendment 2: the identical run/admitted G_self set for C6b and the later training routing pass."""
    admitted = bool(generated and generated.get("generator") and generated["generator"]["status"] == "admitted")
    g_self = list(generated.get("g_self") or [])[:G_SELF_MAX] if admitted else []
    items = {rounds.key(bench, item["task_id"]): item for item in cut["run"]}
    made = {g["id"]: g for g in g_self}
    publics = {**{key: item["public"] for key, item in items.items()},
               **{key: g["public"] for key, g in made.items()}}
    return items, made, publics


def _engineer_train(st, cut, r, incumbent, *, done, fed, history, training, lint, reserved, analysed, disclosed,
                    generated=None):
    """v2's unit ``engineer-r<r>`` (``engineer.run_train``): the engineer on the incumbent with the round's inputs; the
    candidate (re-expressed against S) is saved with the chain's packages."""
    unit = "engineer-r%d" % r
    name = st.label(unit)

    def work(attempt):
        stored = []
        for k, bench, _ in _earlier(st, "run"):
            stored += _run_trajectories(st, k, bench)
        own = _run_trajectories(st)
        stored += own
        parents = [t for t in own if t["arm_kind"] == "parent"]
        current, evaluated = _current(st, done), _evaluated(st, cut, fed)
        routing = {}
        if protocol.CHECK_NON_FIRING[configuration_of(st.setting)]:
            _, _, publics = _training_publics(cut, generated, st.bench)
            routing = {"routing_items": [(key, solver.routing_view(st.bench, public, runtime=st.runtime()))
                                         for key, public in publics.items()],
                       "routing_workers": _item_workers(st, publics),
                       "routing_shared_worker": st.bench != "spreadsheetbench"
                                                and st.services.item_workers is None}
        with _inputs_dirs(st, _distinct(stored + current + evaluated), cut) as inputs:
            ctx = engineer.Context(bench=st.bench, k=st.k, step=st.name, evidence=st.evidence, parent=incumbent,
                                   trajectories=stored, corpora=_corpora(st, cut), workers=st.services.workers,
                                   roles=st.roles("engineer"), label=name, card=st.setting.cards.get(st.bench, ""),
                                   references=_references(st, cut, parents + current + evaluated, also=disclosed),
                                   inputs_dirs=inputs,
                                   detectors=detectors.counts(detectors.diagnosis(parents, bench=st.bench)),
                                   previous=_previous(st), mode=TRAIN, round=r, base=st.parent, current=current,
                                   evaluated=evaluated, history=list(history), training=training, lint=list(lint),
                                   reserved=frozenset(reserved), analysed=frozenset(analysed),
                                   disclosed=frozenset(disclosed),
                                   configuration=configuration_of(st.setting),
                                   echo=FIX_ECHO[configuration_of(st.setting)],  # v2.1: main-v2-1 redacts
                                   counterfactual=META_COUNTERFACTUAL[configuration_of(st.setting)], **routing)
            candidate, sealed = engineer.run_train(ctx)
        if candidate is not None:
            save(st.chain_root, candidate)
        return {"engineer": sealed, "candidate_sha256": candidate.sha256 if candidate is not None else None,
                "learning": TRAIN, "round": r}

    return st.unit(unit, work)


def _routes(st, package, entries, publics):
    """v2: {key: ``router.RouteLog``} of ``package`` on ``entries`` [(key, routing view)], zero calls: no worker when
    no procedure of the package runs on the bench; on SpreadsheetBench one worker per item with its workbook mounted
    (``_item_workers``, ``publics`` by key); else one worker holding the package for every item (a predicate is a pure
    function of the view: C6 replayed every procedure in two orders and hash seeds)."""
    if not package.for_bench(st.bench):
        return {key: router.route(package, st.bench, view, None) for key, view in entries}
    if st.bench == "spreadsheetbench" or st.services.item_workers is not None:
        factory, out = _item_workers(st, publics), {}
        for key, view in entries:
            with factory(package, key) as worker:
                out[key] = router.route(package, st.bench, view, worker)
        return out
    with st.services.workers(package, kind="cell", inputs_dir=None) as worker:
        return {key: router.route(package, st.bench, view, worker) for key, view in entries}


def _token_share(found):
    return Fraction(sum(_token(cell) == "pass" for cell in found), len(found))


def train_verdict(cells, items, generated, changed, *, predicate_faults, routed, sign=True, request_faults=None,
                  identical=None, runs=1):
    """v2: the adoption rule of one training round from its cell records (module docstring). ``cells``: {(arm, item):
    [cell records]} of arms S' (the candidate) and S (the incumbent); ``items`` / ``generated``: the run-slice and
    G_self items evaluated (those routed differently); ``changed``: the ids of the procedures the candidate adds or
    revises against the incumbent; ``predicate_faults``: their predicate faults in the routing pass of ``routed``
    items. Per item the pass share of each arm; fixed (S' above S), broken (S' below S), net (the sum of S' - S).
    Adopted iff every guard holds -- S' cells with a fault of a changed procedure or an ``unknown_fault`` <= 2 %, the
    predicate faults <= 2 % of the routed items, S' format-violating cells above S's by at most max(2, 2 % of its
    cells) -- and every gain criterion: fixed > broken, net >= max(1, ceil(2 % of the evaluated items)) and the
    one-sided exact sign test of fixed against broken p <= ``TRAIN_ALPHA``. v2.2 (``protocol.TRAIN_SIGN``): with
    ``sign`` False the sign test is recorded and not required (``sign_required``). v2.3 Amendment 1: ``identical``
    names evaluated items skipped for both arms, with zero difference; their ``runs`` registered run-slice cells
    (one per generated item) remain in the format/fault denominator. None preserves the frozen verdict shape."""
    evaluated = list(items) + list(generated)
    skipped = set(identical or ())
    if identical is not None:
        require(type(runs) is int and runs > 0 and len(skipped) == len(identical) and skipped <= set(evaluated)
                and not any(item in skipped for _, item in cells)
                and not skipped & set(request_faults or ()), "Identical training items are fault-free and undispatched")
    diff = {i: Fraction(0) if i in skipped else _token_share(cells[("S'", i)]) - _token_share(cells[("S", i)])
            for i in evaluated}
    fixed = sorted(i for i in evaluated if diff[i] > 0)
    broken = sorted(i for i in evaluated if diff[i] < 0)
    net = sum(diff.values(), Fraction(0))
    candidate = [c for (arm, _), found in sorted(cells.items()) if arm == "S'" for c in found]
    skipped_cells = sum(runs if i in items else 1 for i in evaluated if i in skipped)
    candidate_denominator = len(candidate) + skipped_cells

    def own_fault(cell):
        return _token(cell) == "unknown_fault" or any(f.get("procedure") in changed for f in cell.get("faults") or [])

    def violating(arm):
        return sum(1 for (name, _), found in cells.items() if name == arm for cell in found
                   if ((cell.get("judge") or {}).get("format") or {}).get("violation"))

    own = sum(1 for (arm, item), found in cells.items() if arm == "S'" for c in found
              if own_fault(c) or item in (request_faults or []))
    formats = {"S": violating("S"), "S'": violating("S'")}
    margin = max(TRAIN_FORMAT_MARGIN[0], math.ceil(TRAIN_FORMAT_MARGIN[1] * candidate_denominator))
    need = max(1, math.ceil(TRAIN_ADOPT_SHARE * len(evaluated)))
    p = _one_sided_sign(len(fixed), len(broken))
    guards = {"own_faults": own <= SELFTEST_FAULT_MAX * candidate_denominator,
              "predicate_faults": predicate_faults <= SELFTEST_FAULT_MAX * routed,
              "format": formats["S'"] - formats["S"] <= margin}
    gain = {"fixed_over_broken": len(fixed) > len(broken), "net": net >= need}
    if sign:
        gain["sign"] = p <= TRAIN_ALPHA
    adopted = bool(evaluated) and all(guards.values()) and all(gain.values())
    reason = None
    if not adopted:
        failed = ["guard:" + k for k, ok in guards.items() if not ok] + ["gain:" + k for k, ok in gain.items() if not ok]
        reason = failed[0] if evaluated else "no_item_routes_differently"
    return {"adopted": adopted, "reason": reason, "items": len(items), "generated": len(generated),
            "fixed": fixed, "broken": broken, "net": "%d/%d" % (net.numerator, net.denominator), "need": need,
            "p_sign": p, "guards": guards, "gain": gain, "own_fault_cells": own, "candidate_cells": len(candidate),
            "predicate_faults": predicate_faults, "routed": routed, "format_cells": formats, "format_margin": margin,
            **({} if sign else {"sign_required": False}),
            **({"identical": list(identical), "skipped_candidate_cells": skipped_cells,
                "candidate_cells_denominator": candidate_denominator} if identical is not None else {})}


def prune_idle(candidate, incumbent, base, after):
    """v2.2 (``protocol.PRUNE_NON_FIRING``): ``candidate`` -- one candidate of the step's parent ``base`` -- without the
    procedures this round wrote (not in ``incumbent``) that ``after`` ({key: route log of the candidate on every
    evaluated item}) enables on no item and faults on none -> ``(package, pruned ids)``. Such a procedure changes no
    training cell (a predicate is a pure function of the view, C6), so pruning keeps the round's evidence and drops only
    code without any; a procedure it replaced stays retired (a revision that fires nowhere leaves the old version
    deleted). The pruned package is ``package.withhold``'s, re-validated against ``base``."""
    active = ({pid for log in after.values() for pid in log.enabled}
              | {f.get("procedure") for log in after.values() for f in log.faults})
    idle = [pid for pid in candidate.order if pid not in set(incumbent.order) and pid not in active]
    if not idle:
        return candidate, []
    pruned = withhold(candidate, idle)
    validate(pruned, base)
    return pruned, idle


def _attempt_trajectories(attempt):
    """{cell: trajectory} of the cells an attempt ran (``<attempt>/trajectories``)."""
    directory = safe_path(attempt) / trajectories.TRAJECTORIES
    return {t["cell"]: t for t in (verified(read_json(path), "trajectory") for path in sorted(directory.glob("*.json")))}


def _notes_text(trajectory):
    """The procedure notes the solver saw: the first request's (QA, SpreadsheetBench), every step's distinct ones
    (ALFWorld)."""
    if trajectory["bench"] == "alfworld":
        return "\n".join(dict.fromkeys(step["notes"] for step in trajectory.get("alfworld_steps") or ()
                                       if step.get("notes")))
    if not trajectory["calls"]:
        return ""
    if trajectory["bench"] == "zebralogic":
        from .zebralogic import parse_user
        return str(parse_user(trajectory["calls"][0]["user"]).get(NOTES_KEY) or "")
    return str(json.loads(trajectory["calls"][0]["user"]).get(NOTES_KEY) or "")


def _last_reply(trajectory):
    """The solver's final reply (QA, SpreadsheetBench), or ALFWorld's outcome and step count."""
    if trajectory["bench"] == "alfworld":
        steps = len(trajectory.get("alfworld_steps") or ())
        return "%s after %d steps" % ("won" if trajectory["token"] == "pass" else "not won", steps)
    replies = [reply for reply in trajectory["replies"] if type(reply) is str]
    return replies[-1] if replies else ""


def _feedback(st, cut, unit, verdict, routed, incumbent, candidate, cells, made):
    """v2: the engineer's view of one training round (module docstring): the totals and, per procedure the candidate
    adds, removes or narrows against the incumbent, the evaluated run-slice items it is enabled on (the candidate's
    routing; the incumbent's for a removed or narrowed one) with how many it fixed and broke and up to
    ``TRAIN_EXAMPLES`` fixed and broken examples each (seeded order): the question, the notes the solver saw with the
    candidate, the last replies with the incumbent ("current") and with the candidate, both pass shares and -- for an
    item a cell of the round failed, never on ALFWorld -- its reference (``_references``). Generated items are counted
    only. ``made``: the round's {cell: trajectory}."""
    by_key = {rounds.key(st.bench, item["task_id"]): item for item in cut["run"]}
    fixed, broken = set(verdict["fixed"]) & set(by_key), set(verdict["broken"]) & set(by_key)
    evaluated = [key for key in by_key if (("S", key) in cells)]
    references = _references(st, cut, [made[c["cell"]["id"]] for key in evaluated for arm in ("S", "S'")
                                       for c in cells[(arm, key)] if c["cell"]["id"] in made])
    evaluated += [key for key in verdict.get("identical", ()) if key in by_key and key not in evaluated]
    before, after = set(incumbent.order), set(candidate.order)
    entries = [(pid, "added", "candidate") for pid in candidate.order if pid not in before]
    entries += [(pid, "removed", "incumbent") for pid in incumbent.order if pid not in after]
    entries += [(pid, "narrowed", "incumbent") for pid in incumbent.order if pid in after
                and set(candidate.narrowed.get(pid, ())) - set(incumbent.narrowed.get(pid, ()))]

    def example(key, outcome):
        current = [made[c["cell"]["id"]] for c in cells[("S", key)] if c["cell"]["id"] in made]
        new = [made[c["cell"]["id"]] for c in cells[("S'", key)] if c["cell"]["id"] in made]
        if not current or not new:  # a cell that stored no trajectory gives no example
            return None
        view = solver.routing_view(st.bench, by_key[key]["public"], runtime=st.runtime())
        question = view.get(QUESTION_FIELDS[st.bench]) or donors.public_text(view)
        entry = {"task_id": key, "cell": new[-1]["cell"], "outcome": outcome,
                 "question": str(question)[:TRAIN_TEXT_CHARS["question"]],
                 "notes": _notes_text(new[-1])[:TRAIN_TEXT_CHARS["note"]],
                 "current_reply": _last_reply(current[-1])[:TRAIN_TEXT_CHARS["answer"]],
                 "candidate_reply": _last_reply(new[-1])[:TRAIN_TEXT_CHARS["answer"]],
                 "current_pass": "%d/%d" % (sum(t["token"] == "pass" for t in current), len(current)),
                 "candidate_pass": "%d/%d" % (sum(t["token"] == "pass" for t in new), len(new))}
        if key in references:
            entry["reference"] = references[key]
        return entry

    procedures = []
    for pid, change, side in entries:
        on = [key for key in evaluated if pid in routed[key][side]]
        tag = "%s:%s:%s" % (FEEDBACK_TAG, st.label(unit), pid)
        shown = []
        for outcome, members in (("fixed", fixed), ("broken", broken)):
            chosen = ranked([{"task_id": key} for key in on if key in members], SEED, tag + ":" + outcome)
            found = (example(entry["task_id"], outcome) for entry in chosen)
            shown += [entry for entry in found if entry is not None][:TRAIN_EXAMPLES]
        procedures.append({"id": pid, "change": change, "enabled_items": len(on),
                           "fixed": sum(key in fixed for key in on), "broken": sum(key in broken for key in on),
                           "examples": shown})
    generated = [i for i in verdict["fixed"] + verdict["broken"] if i not in by_key]
    return {"adopted": verdict["adopted"], "reason": verdict["reason"], "items": verdict["items"],
            "fixed": len(fixed), "broken": len(broken), "net": verdict["net"], "need": verdict["need"],
            "p_sign": verdict["p_sign"], "guards": verdict["guards"],
            "generated": {"items": verdict["generated"], "fixed": sum(i in set(verdict["fixed"]) for i in generated),
                          "broken": sum(i in set(verdict["broken"]) for i in generated)},
            "procedures": procedures}


def _train_eval(st, cut, r, incumbent, candidate, generated):
    """v2's unit ``train-r<r>`` (module docstring): the routing pass, both packages on the items they route
    differently (run items with the registered runs, the admitted G_self items once), ``train_verdict`` and the
    feedback. Returns the unit's result."""
    unit = "train-r%d" % r
    name = st.label(unit)
    runs = SLICES[st.bench]["run"][1]
    admitted = bool(generated and generated.get("generator") and generated["generator"]["status"] == "admitted")
    g_self = list(generated.get("g_self") or [])[:G_SELF_MAX] if admitted else []

    def work(attempt):
        items = {rounds.key(st.bench, item["task_id"]): item for item in cut["run"]}
        made = {g["id"]: g for g in g_self}
        publics = {**{key: item["public"] for key, item in items.items()},
                   **{key: g["public"] for key, g in made.items()}}
        if protocol.CHECK_NON_FIRING[configuration_of(st.setting)]:
            items, made, publics = _training_publics(cut, generated, st.bench)
        views = [(key, solver.routing_view(st.bench, public, runtime=st.runtime())) for key, public in publics.items()]
        before, after = _routes(st, incumbent, views, publics), _routes(st, candidate, views, publics)
        trained, pruned = candidate, []
        if PRUNE_NON_FIRING[configuration_of(st.setting)]:  # v2.2: an idle procedure never rides along
            trained, pruned = prune_idle(candidate, incumbent, st.parent, after)
            if pruned:
                save(st.chain_root, trained)
        changed = {pid for pid in trained.order if pid not in set(incumbent.order)}
        routed = {key: {"incumbent": list(before[key].enabled), "candidate": list(after[key].enabled)}
                  for key, _ in views}
        differs = [key for key, _ in views if before[key].enabled != after[key].enabled]
        evaluated = list(differs)
        identical, signatures = [], None
        if IDENTICAL_REQUEST_REUSE[configuration_of(st.setting)]:
            signatures = _pair_signatures(st, trained, incumbent, publics,
                                         [(key, view) for key, view in views if key in differs])
            identical = [key for key, arms in signatures.items()
                         if request_reuse.interchangeable(arms["S'"], arms["S"], bench=st.bench)]
            differs = [key for key in differs if key not in identical]
        faults = sum(1 for key, _ in views for f in after[key].faults if f.get("procedure") in changed)
        jobs = []
        for key in differs:
            source = items.get(key)
            task = ({"benchmark": st.bench, "public": source["public"], "private": source["private"]}
                    if source is not None else _task(made[key]))
            for arm, kind, package in (("S'", "candidate", trained), ("S", "parent", incumbent)):
                jobs += [(arm, Arm(kind, package), key, run, task) for run in range(runs if source else 1)]
        found = _cells(st, attempt, st.solver("selftest", attempt), name, jobs, tag="train") if jobs else []
        cells = {}
        for cell in found:
            cells.setdefault((cell["cell"]["arm"], cell["cell"]["task_id"]), []).append(cell)
        rounds.guard(cells, ["S", "S'"], name)
        verdict = train_verdict(cells, [k for k in evaluated if k in items], [k for k in evaluated if k in made],
                                changed, predicate_faults=faults, routed=len(views),
                                sign=TRAIN_SIGN[configuration_of(st.setting)],
                                request_faults=([key for key, arms in signatures.items()
                                                 if any(f.get("procedure") in changed for f in arms["S'"]["faults"])]
                                                if signatures is not None else None),
                                **({"identical": identical, "runs": runs} if signatures is not None else {}))
        feedback = _feedback(st, cut, unit, verdict, routed, incumbent, trained, cells,
                             _attempt_trajectories(attempt))
        out = {"learning": TRAIN, "round": r, "incumbent_sha256": incumbent.sha256,
               "candidate_sha256": trained.sha256, "routed": len(views), "differs": len(differs),
               "cells": len(found), "adopted": verdict["adopted"], "verdict": verdict, "feedback": feedback}
        if PRUNE_NON_FIRING[configuration_of(st.setting)]:
            out.update({"proposed_sha256": candidate.sha256, "pruned": pruned})
        if signatures is not None:
            out.update({"version": "training-requests-v2-3", "identical": identical, "request_signatures": signatures})
        return out

    return st.unit(unit, work)


def _line(r, engineered, evaluated):
    """v2: one round of the history the engineer sees: counts and flags, and per proposed change (SkillOpt's step
    buffer, owner suggestion 2026-10-23 15:1x) its kind (a registered edit kind, else None), registrar id, target,
    description excerpt -- only for a change whose final version passed the leakage check C4, i.e. survived or stopped
    at C7, C8 or C9 (Codex review 2026-10-23 #3) -- and fate: the check that stopped it, ``dropped_in_combination``
    (``engineer._combined_train``), ``pruned_no_firing`` (v2.2, ``prune_idle``), or the round's verdict."""
    line = {"round": r, "candidate": engineered["candidate_sha256"] is not None, "adopted": False, "items": 0,
            "generated": 0, "fixed": 0, "broken": 0, "net": "0/1", "p_sign": None, "reason": "no_candidate"}
    if evaluated is not None:
        verdict = evaluated["verdict"]
        line.update({"adopted": verdict["adopted"], "items": verdict["items"], "generated": verdict["generated"],
                     "fixed": len(verdict["fixed"]), "broken": len(verdict["broken"]), "net": verdict["net"],
                     "p_sign": verdict["p_sign"], "reason": verdict["reason"]})
    sealed, proposals = engineered["engineer"], []
    for change in sealed["changes"]:
        stopped = change["attempts"][-1]["failed"] if not change["survived"] else None
        if stopped is not None:
            fate = "check_failed:" + stopped
        elif change["n"] in sealed["dropped"]:
            fate = "dropped_in_combination"
        elif evaluated is not None and change["id"] in evaluated.get("pruned", ()):
            fate = "pruned_no_firing"
        else:
            fate = "adopted" if line["adopted"] else "not_adopted:" + line["reason"]
        leak_checked = stopped is None or stopped in ("C7", "C8", "C9")
        proposals.append({"kind": change["kind"] if change["kind"] in EDIT_KINDS else None, "id": change["id"],
                          "target": change["target"], "description": change["summary"] if leak_checked else "",
                          "fate": fate})
    line["proposals"] = proposals
    return line


def _train(st, cut, generated):
    """v2's training rounds (module docstring) -> ``(T_final, the rounds' records, the last evaluated candidate or
    None)``. Completed round units are read back, so a restarted step passes through finished rounds without a call."""
    incumbent, done, fed, history, training, lint, reserved = st.parent, [], None, [], None, [], frozenset()
    out, last, misses, analysed, disclosed = [], None, 0, frozenset(), frozenset()
    for r in range(1, TRAIN_ROUNDS + 1):
        engineered = _engineer_train(st, cut, r, incumbent, done=done, fed=fed, history=history, training=training,
                                     lint=lint, reserved=reserved, analysed=analysed, disclosed=disclosed,
                                     **({"generated": generated}
                                        if protocol.CHECK_NON_FIRING[configuration_of(st.setting)] else {}))
        sealed = engineered["engineer"]
        reserved = reserved | {c["id"] for c in sealed["changes"] if c.get("id")}
        analysed = analysed | set(sealed["analysis"]["items"])
        disclosed = disclosed | set(sealed["disclosed"])  # Codex review 2026-10-23 #3: read back on a restart too
        lint, evaluated = list(sealed["lint"]), None
        if engineered["candidate_sha256"] is not None:
            candidate = _package(st, engineered["candidate_sha256"])
            evaluated = _train_eval(st, cut, r, incumbent, candidate, generated)
            if evaluated["candidate_sha256"] != candidate.sha256:  # v2.2: idle procedures were pruned
                candidate = _package(st, evaluated["candidate_sha256"])
            done.append(("train-r%d" % r, evaluated["adopted"]))
            fed, training = "train-r%d" % r, evaluated["feedback"]
            if evaluated["cells"]:
                last = candidate
            if evaluated["adopted"]:
                incumbent = candidate
        line = _line(r, engineered, evaluated)
        history.append(line)
        out.append({**line, "candidate_sha256": engineered["candidate_sha256"] if evaluated is None
                    else evaluated["candidate_sha256"],  # v2.2 (Codex review MINOR 2): the package the cells ran
                    **({key: evaluated[key] for key in ("proposed_sha256", "pruned")}
                       if evaluated is not None and "proposed_sha256" in evaluated else {}),
                    "incumbent_sha256": incumbent.sha256})
        misses = 0 if line["adopted"] else misses + 1
        if misses >= TRAIN_PATIENCE:
            break
    return incumbent, out, last


def _trained(st, cut, generated):
    """v2 (module docstring): the training rounds, then one self-test of the final package -> ``(S' or None, the
    not-run outcome or None, the training record)``. No edit against S: ``no_training_gain`` (SX only: the last
    evaluated candidate takes the self-test and acceptance, recorded as ``exercise``); a block: ``selftest_blocked``."""
    final, rounds_done, last = _train(st, cut, generated)
    training = {"rounds": rounds_done, "final_sha256": final.sha256, "adopted": sum(r["adopted"] for r in rounds_done),
                "exercise": False}
    if edits(st.parent, final):
        candidate = final
    elif st.smoke is not None and last is not None:
        candidate, training["exercise"] = last, EXERCISE
    else:
        return last, _release("no_training_gain"), training
    if _selftest(st, "selftest", candidate, generated)["blocked"]:
        return candidate, _release("selftest_blocked"), training
    return candidate, None, training


# ------------------------------------------------------------------------------------------------ 5.6 accept
def _blocks(st, items):
    """{item: block}: the bench's registered acceptance blocks as consecutive parts of the slice order (§3.3, §6.2;
    ALFWorld: whole rooms, consecutive in the seeded room order ``supply.room_order``, §3.1 O6 -- not in the rooms'
    names, whose scene numbers group the room types)."""
    count = SLICES[st.bench]["blocks"]
    if st.bench == "alfworld":
        rooms = supply.room_order(items)
        return {item["task_id"]: "b%d" % (1 + rooms.index(item["room"]) * count // len(rooms)) for item in items}
    return {item["task_id"]: "b%d" % (1 + n * count // len(items)) for n, item in enumerate(items)}


def _g_acc(st, generated, attempt):
    """The frozen generator's G_acc items (§7.2, ticket C1-3), built by the registrar after the engineer: each frozen
    spec's family and parameter sets applied to every usable material of the g_acc research half. The two halves never
    share a material (``research.split``), so a spec is rebound from its G_self material to each g_acc material of its
    family's kind (e2e test, C4); its items are numbered after every G_self item of the generate unit (ticket C4-1).
    None without an admitted generator, on SpreadsheetBench (no G_acc in v1: its acceptance result carries
    ``SHEET_VALIDITY``, registrar decision on ticket C1-3) or without G_acc items."""
    if (not generated or generated.get("generator") is None or generated["generator"]["status"] != "admitted"
            or st.bench == "spreadsheetbench"):
        return None
    materials = generated["split"]["g_acc"]
    usable = examiner.usable(st.bench, materials)
    specs = [{**spec, "material": material_id} for spec in generated["generator"]["specs"]
             for material_id, material in sorted(usable.items())
             if material["kind"] == generators.MATERIAL_KINDS[generators.family(spec["family"]).material]]
    if not specs:
        return None
    built = _build(st, specs, materials, "G_acc", None, attempt, generated["numbered"])
    return built.items or None


def _options_only(item):
    """§6.4 J7 (registrar addendum 2026-10-22 17:0x, LiveMath step: "64 meta-present items are sent options-only
    (examiner.shortcut_variant's stem-hiding transform)"): a J7 probe item as its options-only cells (S' and C, one run
    each) see it -- the stem hidden by the shortcut probe's own transform (``examiner.shortcut_public``, the one
    ``examiner.shortcut_variant`` applies), the five options and the private answer unchanged. Only LiveMath's
    meta-present items are probed."""
    require(item["benchmark"] == "livemath" and supply.meta_present(item), "J7 probes LiveMath's meta-present items")
    return {"public": examiner.shortcut_public("livemath", item["public"]), "private": item["private"]}


def _round_tasks(records, probe, acc):
    """{item: {"public", "private"}} of a round's cells (``acceptance.runner``): the acceptance items as registered,
    the J7 probe items options-only (``_options_only``; their registry records stay the items themselves) and the
    G_acc items (``_task``)."""
    return {**{i: {"public": r["public"], "private": r["private"]} for i, r in records.items()},
            **{item["task_id"]: _options_only(item) for item in probe},
            **{g["id"]: _task(g) for g in acc or []}}


def _accept(st, cut, candidate, generated):
    name = st.label("accept")
    root = units.unit_path(st.chain_root, st.k, st.bench, "accept")
    accept, probe = cut["accept"], cut.get("accept_probe", [])
    records = {item["task_id"]: item for item in accept + probe}

    def work(attempt):
        n = units.attempt_number(attempt)
        # all refused before anything is held: the blocks no earlier attempt started go to the kind's own scope; a
        # redo's one started block to its own sub-scope ...:accept:attempt-N and the redo reserve (§9.3, ticket C7c-2);
        # the G_acc cells of every block to the examiner's own scope (§3.3, §9.2, calc T6; ticket C7e-1)
        first = st.solver("accept", attempt, first_run=True)
        endpoint = st.solver("accept", attempt) if n > 1 else first
        examining = st.solver("examiner", attempt, g_acc=True)
        registry = st.services.registry
        registry.register(st.namespace, st.bench, accept, unit=name, purpose=st.purpose("accept"),
                          run_root=str(st.setting.root), attempt=n)
        if probe:
            registry.register(st.namespace, st.bench, probe, unit=name, purpose="accept_probe",
                              run_root=str(st.setting.root), attempt=n)
        donors_ = _run_trajectories(st, parent_only=True)
        acc = _g_acc(st, generated, attempt)
        publics = {item["task_id"]: item["public"] for item in accept + probe}
        publics.update({rounds.key(st.bench, item["task_id"]): item["public"] for item in cut["run"]})  # donors
        if IDENTICAL_REQUEST_REUSE[configuration_of(st.setting)]:
            publics.update({g["id"]: g["public"] for g in acc or []})
        workers = _item_workers(st, publics)
        if (root / "sealed.json").exists():
            sealed = verified(read_json(root / "sealed.json"), "acceptance-sealed")
            donors.verify(sealed["corpus"], donors_)
        else:
            views = {item["task_id"]: solver.routing_view(st.bench, item["public"], runtime=st.runtime())
                     for item in accept}
            admitted = bool(generated and generated.get("generator")
                            and generated["generator"]["status"] == "admitted")
            generate = None if acc is None else (
                lambda astar: examiner.g_acc(acc, list(astar), bench=st.bench, generator=_generator_id(st)))
            reuse = None
            if IDENTICAL_REQUEST_REUSE[configuration_of(st.setting)]:
                extra = {"G_acc": {g["id"]: g["public"] for g in acc or []},
                         "probe": {i["task_id"]: _options_only(i)["public"] for i in probe}}
                reuse = {"card_text": st.setting.cards.get(st.bench, ""), "runtime": st.runtime(),
                         "views": {name: {key: solver.routing_view(st.bench, public, runtime=st.runtime())
                                          for key, public in entries.items()} for name, entries in extra.items()}}
            sealed = acceptance.prepare(  # the sealed "chain" is the namespace dispatch and settle register in
                root, chain=st.namespace, bench=st.bench, step=st.name, unit=name, candidate=candidate, parent=st.parent,
                views=views, blocks=_blocks(st, accept), workers=workers, trajectories=donors_,
                rooms={i["task_id"]: i["room"] for i in accept} if st.bench == "alfworld" else None,
                generate=generate, dup=admitted and st.k > 1, probe=[item["task_id"] for item in probe],
                freshness=ACCEPT_FRESHNESS.get(configuration_of(st.setting), FRESHNESS),
                mde=MDE_POINTS[st.bench],  # A9-3: the registered MDE in decision.json
                rule=ACCEPT_RULES[configuration_of(st.setting)], reuse=reuse)  # v2.2: the practical rule, None before
        packages = acceptance.round_packages(candidate, st.parent, step=sealed["step"], twins=sealed["plan"]["twins"])
        tasks = _round_tasks(records, probe, acc)  # §6.4 J7: the probe items options-only
        earlier = acceptance.earlier_blocks(sealed, root, attempt) if n > 1 else None  # §9.3, owner decision #15
        context = units.cell_context(st.setting, attempt, first)
        if st.smoke is not None and st.smoke.drill is not None and n == 1:  # §10 S4: the drill, first attempt only
            context = replace(context, worker=functools.partial(_drilled_worker, st))
        store = TrainingStore(attempt)
        g_acc = replace(context, endpoint=examining)  # the same workers and pools, the examiner's scope (C7e-1)
        run = acceptance.runner(context, sealed, packages, tasks, workers=st.setting.workers, store=store,
                                examiner=g_acc)
        redo = None if n == 1 else acceptance.runner(replace(context, endpoint=endpoint), sealed, packages, tasks,
                                                     workers=st.setting.workers, store=store, examiner=g_acc)
        cells = acceptance.dispatch(sealed, registry, run, items=records, attempt=n, earlier=earlier, redo=redo,
                                    clock=st.services.clock, sleep=st.services.sleep)
        decision = acceptance.decide(cells, sealed)
        acceptance.write(attempt, decision)
        if decision["decision"] == "undetermined":  # pauses in the work: the owner's recovery redoes the round (§13)
            acceptance.settle(decision, sealed, registry, records, attempt=n)
        provenance = decision.get("provenance") or {}
        return {"decision": decision["decision"], "reason": decision["reason"],
                "decision_sha256": decision[RECORD_HASH], "sealed_sha256": sealed[RECORD_HASH], "cells": len(cells),
                "dup": sealed["dup"], "g_acc": len(sealed["g_acc"] or []),
                "fault_items": _guard(decision, "J3", "fault_items"),
                "violating_items": _guard(decision, "J4_items", "S'"),
                "validity": SHEET_VALIDITY if st.bench == "spreadsheetbench" else None,
                "provenance": {block: entry["attempt"] for block, entry in provenance.items()},
                "reused": dict(earlier["reused"]) if earlier else {},
                "redone": list(earlier["redone"]) if earlier else []}

    def settle(attempt, result):  # Codex finding #8: the round's items are decided once the unit's completion evidence
        # is persisted, and again (nothing written) by the commit attempt of a recovery -- never before it
        acceptance.settle(read_json(attempt / "decision" / "decision.json"), read_json(root / "sealed.json"),
                          st.services.registry, records, attempt=units.attempt_number(attempt))

    return st.unit("accept", work, settle=settle)


def _drilled_worker(st, bench):
    """An acceptance cell's unstarted worker through the S4 fault switch (``SmokeStep.drill``), with the Setting's
    sandbox options and pools (``units.cell_context``; SearchQA has no per-unit live cap)."""
    return st.smoke.drill.worker(**st.setting.sandbox, live=st.setting.slots[LIVE], per_call=st.setting.slots[CALL])


def _guard(decision, name, key):
    guard = (decision.get("guards") or {}).get(name) or {}
    return guard.get(key, 0) or 0


def _release(reason):
    """The acceptance outcome of a step whose candidate never reached the acceptance (§5.4, §5.5): nothing ran."""
    return {"decision": "not_run", "reason": reason, "decision_sha256": None, "sealed_sha256": None, "cells": 0,
            "dup": False, "g_acc": 0, "fault_items": 0, "violating_items": 0}


# ------------------------------------------------------------------------------------------------ 5.7 freeze
def _freeze(st, cut, candidate, accepted):
    name = st.label("freeze")

    def work(attempt):
        if not accepted:
            return {"accepted": False, "package_sha256": st.parent.sha256, "archived": candidate and candidate.sha256,
                    "descriptions": []}
        roles, stored = st.roles("describer"), _run_trajectories(st, parent_only=True)
        entries = [entry for entry in (replay.inputs_of(t) for t in stored) if entry is not None]
        records = []
        with _inputs_dirs(st, stored, cut) as inputs:
            for procedure in [p for p in candidate.procedures if p.id in _changed_ids(st.parent, candidate)]:
                runs_here = st.bench not in candidate.excluded(procedure.id)
                outcomes = (replay.replay_many(procedure, entries, st.services.workers, inputs_dirs=inputs)
                            if runs_here else {})
                lengths = [len(note["text"]) for outcome in outcomes.values() for note in outcome.notes
                           if note["text"]]
                records.append(describer.describe(roles, procedure, lengths=lengths,
                                                  label="%s/%s" % (name, procedure.id), evidence=st.evidence,
                                                  excluded=candidate.excluded(procedure.id)))
        frozen = with_describer(candidate, describer.entries(records)) if records else candidate
        save(st.chain_root, frozen)
        return {"accepted": True, "package_sha256": frozen.sha256, "archived": None, "descriptions": records}

    return st.unit("freeze", work)


# ----------------------------------------------------------------------------------------------------- the step
def run_step(setting, chain, bench, k, parent, *, services, chain_root=None, smoke=None):
    """The eight sub-steps of one step (module docstring) -> ``StepRecord``. ``chain_root``: ``<run root>/<chain>``
    by default. ``smoke``: a ``SmokeStep`` -- the S4 mini-step (chain ``budgets.SMOKE``, SearchQA step 1 from the
    empty parent; run, accept and freeze with the given candidate). Raises ``cells.Pause`` (a unit paused; nothing
    resumes by itself) or ``chain.Terminated``."""
    if smoke is None:
        require(chain in CHAINS and bench in protocol.SUPPORTED_BENCHES and type(k) is int and k >= 1
                and isinstance(parent, Package),
                "A chain, a bench, a step position and the parent package")
    else:
        require(isinstance(smoke, SmokeStep) and chain == budgets.SMOKE and bench == SMOKE_BENCH and k == 1
                and isinstance(parent, Package) and not parent.procedures and smoke.model in CHAINS.values()
                and (smoke.candidate is None and smoke.drill is None if smoke.train else
                     isinstance(smoke.candidate, Package) and smoke.candidate.parent_sha256 == parent.sha256),
                "The S4 mini-step: the smoke's SearchQA step 1 from the empty parent with its candidate (the v2 "
                "example SX: without one)")
    st = _Step(setting, services, chain, bench, k, parent, safe_path(chain_root or Path(setting.root) / chain), smoke)
    final = st.root / STEP_FILE
    if final.exists():
        value = verified(read_json(final), "step")
        require(value["parent_sha256"] == parent.sha256, "A finished step of another parent")
        return StepRecord(_package(st, value["package_sha256"]) if value["package_sha256"] != parent.sha256
                          else parent, value)
    cut = _slices(st)
    _run(st, cut)
    training = None
    if smoke is None or smoke.train:
        _diagnose(st, cut)
        generated = _generate(st, cut)
        if st.learning == TRAIN:  # v2: the training rounds (module docstring)
            candidate, outcome, training = _trained(st, cut, generated)
        else:
            candidate, outcome = _candidate(st, cut, generated)
    else:  # §10 S4: no generation on SearchQA (§7.2); the candidate is given, kept with the chain's packages
        generated, candidate, outcome = None, smoke.candidate, None
        save(st.chain_root, candidate)
    if outcome is None:
        outcome = _accept(st, cut, candidate, generated)
    accepted = outcome["decision"] == "accept"
    frozen = _freeze(st, cut, candidate, accepted)
    package = _package(st, frozen["package_sha256"]) if accepted else parent
    value = record("step-v2-3" if IDENTICAL_REQUEST_REUSE[configuration_of(setting)] else "step", st.evidence, {
        "chain": chain, "k": k, "bench": bench, "step": st.name, "parent_sha256": parent.sha256,
        "candidate_sha256": candidate.sha256 if candidate is not None else None,
        "package_sha256": package.sha256, "decision": outcome["decision"], "reason": outcome["reason"],
        "decision_sha256": outcome["decision_sha256"], "fault_items": outcome["fault_items"],
        "violating_items": outcome["violating_items"],
        "units": {name: _unit_hash(st, name) for name in st.units if (units.unit_path(
            st.chain_root, k, bench, name) / "unit.json").exists()},
        "evidence_kind": "selection", **({"learning": TRAIN, "training": training} if st.learning == TRAIN else {})})
    write_json(final, value)
    return StepRecord(package, verified(read_json(final), "step"))


def _unit_hash(st, name):
    path = units.unit_path(st.chain_root, st.k, st.bench, name) / "unit.json"
    return verified(read_json(path), "unit")[RECORD_HASH]


def learn(setting, chain_root, chain, k, bench, parent, *, services):
    """The step in the form ``chain.run`` calls (``learn(setting, chain_root, chain, k, bench, parent)``, with
    ``services`` bound): ``(package passed on, sealed step record)``."""
    found = run_step(setting, chain, bench, k, parent, services=services, chain_root=chain_root)
    return found.package, found.record


def parent_of(setting, chain_root, chain, k):
    """The parent package of step ``k``: the empty package at k = 1 (§5, as ``chain.run`` starts), else the package
    the chain's step k - 1 passed on (its ``step.json``)."""
    start = empty(step="%s/s0" % chain, evidence=setting.evidence)
    if k == 1:
        return start
    path = safe_path(chain_root) / ("s%d-%s" % (k - 1, order_of(setting)[k - 2])) / STEP_FILE
    require(path.exists(), "Step %d of chain %s has not finished" % (k - 1, chain))
    sha = verified(read_json(path), "step")["package_sha256"]
    return start if sha == start.sha256 else load(safe_path(chain_root) / "packages" / (sha + ".json"))


def run_unit_spec(manifest, *, spec):
    """``run_execskill.py step-unit --manifest M --spec S`` (ticket A13-1 item 5, C2-1): one step of a chain in a
    child process. ``spec``: a JSON file {"chain", "k", "bench"} naming step k of the order of the manifest's run
    configuration (registrar 17:0x); the parent is
    ``parent_of``. Nothing starts unless the chain root holds the chain's verified, passed ``confirm.json`` of this
    run (``chain.confirmation``; registrar addendum 2026-10-22 15:3x, ticket P2C-1: the first-call confirmation does
    not depend on the entry point; a step the chain runner starts has it, the runner confirmed first). The Setting and
    Services come from the verified manifest (``manifest.setting_of`` / ``services_of``); the chain's own ledger
    declares its registered caps first, as ``chain.run`` does (``chain_caps`` and ``first_call_caps``). Returns
    ``chain.EXIT_COMPLETE``, ``EXIT_AWAITING`` (an attempt awaits the owner's recorded decision) or ``EXIT_PAUSED`` (a
    unit paused); ``chain.Terminated`` propagates."""
    from . import manifest as manifests  # imported here: manifest imports this module (services_of)

    found = read_json(spec)
    require(isinstance(found, dict) and set(found) == SPEC_FIELDS, "A step-unit spec names chain, k and bench")
    chain, k, bench = found["chain"], found["k"], found["bench"]
    configuration = manifest["configuration"]
    order = CONFIGURATIONS[configuration]["order"]
    require(chain in CHAINS and type(k) is int and 1 <= k <= len(order) and order[k - 1] == bench,
            "A step of the order of the manifest's run configuration")
    confirmation(manifest["root"], manifest[RECORD_HASH], chain)  # ticket P2C-1: before anything is touched
    setting = manifests.setting_of(manifest, chain)
    budgets.own_ledger(setting, chain).declare({**budgets.chain_caps(chain, configuration),
                                                **budgets.first_call_caps(chain)})
    services = manifests.services_of(manifest, chain, setting=setting)
    chain_root = safe_path(setting.root) / chain
    try:
        run_step(setting, chain, bench, k, parent_of(setting, chain_root, chain, k), services=services,
                 chain_root=chain_root)
    except Pause as pause:
        return EXIT_AWAITING if pause.kind == "awaiting_owner_decision" else EXIT_PAUSED
    return EXIT_COMPLETE

