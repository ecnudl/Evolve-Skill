"""typed-v3 (类型技能库): a skill library routed by task type, learned bench by bench on practice data.

Design: docs/handoff/typed-v3/CHAIN-DECISIONS.md (owner-approved 2026-11-14) on top of typed-v2
(docs/handoff/typed-v2/DESIGN.md with DECISIONS.md and DECISIONS-ADDENDUM-20261112.md beside it); typed-v2 is the
typed-v1 design (docs/handoff/typed-v1/DESIGN.md, run 2026-11-10 to 11-12) with the pipeline losses of that run
removed. Evidence: docs/handoff/arch-probes-20261109/README.md (the three practice-only probes of 2026-11-09).
Everything here reuses the route-B solver shells, judge/scorers, sandbox, client factories and consent-gated test
reads; none of route B's chain/step/acceptance machinery is used.

typed-v3 (CHAIN-DECISIONS T1) keeps every typed-v2 behaviour as the default of a sealed manifest option, as typed-v2
kept typed-v1's (``BASE_CARD_DEFAULT``, ``SCHEDULE_DEFAULT``, ``READ_PLAN_DEFAULT``): a manifest without the typed-v3
options (``program_learning``, ``archive``, ``item_stage``, ``read_anchors``, ``gate_rule``, ``gate_screen``,
``resume_replay``) runs typed-v2's flow with byte-identical records. Only the version, the configuration, the evidence
labels and the root name change. The preset of the typed-v3 run and smoke (``prepare.typed_v3_preset``, CLI
``prepare --typed-v3``) seals all of them at once.
"""
from __future__ import annotations

VERSION = 'typed-v3'
CONFIGURATION = 'typed-v3'
ORDER = ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld')
CHAINS = ('G', 'D')
SEED = 20261110  # draw key, typed-v1's value (addendum O4): practice slices and writer examples stay the same draw

# Practice slices per bench (disjoint, seeded at prepare; design §2). The typing source of a bench is its whole
# practice pool (ALFWorld: the 322 games with a registered routing view).
SLICES = {
    'searchqa': {'learn': 100, 'gate': 100},
    'officeqa': {'learn': 34, 'gate': 40},
    'zebralogic': {'learn': 73, 'gate': 100},
    'spreadsheetbench': {'learn': 41, 'gate': 50},
    'alfworld': {'learn': 20, 'gate': 40},
}

# Hard token caps per chain (pause at cap; design §2).
CAPS = {'G': 150_000_000, 'D': 170_000_000}

# Gate threshold rule: tau_b = max(TAU_MIN_POINTS, TAU_SE_MULTIPLIER * SE(noise)) in accuracy points (design §2.1).
TAU_MIN_POINTS = 3.0
TAU_SE_MULTIPLIER = 2.0

# Typing (design §1.2): unknown beyond this percentile of within-source distances to the centroid.
UNKNOWN_PERCENTILE = 95
EMBED_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
EMBED_REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
EMBED_PYTHON = '/data/arch-probe-env/bin/python'
EMBED_HF_HOME = '/data/arch-probe-env/hf'
EMBED_DIM = 384
PUBLIC_TEXT_CONTEXT_CHARS = 1500

# Learning per step (design §2.4-2.5).
CARD_ROUNDS = 2            # write + one revision
MAX_PROGRAM_CANDIDATES = 2
MAX_PROGRAM_PROPOSALS = 3  # DESIGN 3.2: up to 3 proposals per programs unit, the first CANDIDATES that pass are tested
GATE_REPEATS = 3           # DESIGN 3.4 (D5): fresh runs per item and arm inside one gate unit
PROGRAM_SMOKE_ITEMS = 3
DESCRIPTION_PROMPT_CHARS = 300
DESCRIPTION_CHAR_CAP = 450
SELECTION_PUBLIC_CHARS = 6000

# Concurrency per chain and bench (design §4, units.py): WIDTHS serves the read units (five panels side by side),
# LEARN_WIDTHS the learning units (addendum D15). Both are sealed in the manifest; a width enters no request, no cell
# tag, no identity and no decision.
WIDTHS = {'searchqa': 3, 'officeqa': 3, 'zebralogic': 3, 'spreadsheetbench': 2, 'alfworld': 2}
LEARN_WIDTHS = {'searchqa': 6, 'officeqa': 6, 'zebralogic': 6, 'spreadsheetbench': 2, 'alfworld': 2}

# Schedule and memory lock (DESIGN 3.6): sealed manifest fields set at prepare; the defaults keep typed-v1's order
# and per-cell lock (the real run and the smoke seal 'unit_shared', addendum D13).
SCHEDULES = ('interleaved', 'learn_first')
SCHEDULE_DEFAULT = 'interleaved'
MEMORY_LOCKS = ('per_cell_plain', 'unit_shared')
MEMORY_LOCK_DEFAULT = 'per_cell_plain'

FORBIDDEN_PATH_WORDS = ('test', 'holdout', 'held_out', 'final', 'sealed', 'reserve', 'verifier_calibration',
                        'test_panel', 'testaccess')

# Route-B machinery borrowed by value (design §5.4): typed-v2 is NOT a route-B configuration; the machinery is still
# main-v10 (DESIGN 3.5).
MACHINERY = 'main-v10'
MACHINERY_SNAPSHOT = '/data/execskill-code-20261109-main-v10'
MACHINERY_MANIFEST = '/data/execskill-20261109-main-v10-smoke/G-manifest.json'
ROLES_REPO = '/root/continual-noskill-bcb-20260928-a'        # chain G credential repository, read by path only
POOLS_ROOT = '/data/execskill-20261021-pre/pools'
# Evidence labels: route-B objects (Package/Procedure/protocol.record) need an admitted label; typed records use EVIDENCE.
ROUTE_B_EVIDENCE = {'run': 'pilot_real_run', 'smoke': 'smoke', 'test': 'engineering_fixture'}
EVIDENCE = {'run': 'typed_v3_real_run', 'smoke': 'typed_v3_smoke', 'test': 'engineering_fixture'}
# Read events/arms (design §5.8): anchors C0 (format block only) and C (historical card), then the library after step k.
READ_ARMS = ('C0', 'C', 'S1', 'S2', 'S3', 'S4', 'S5')
# Mount arms: F (the library), the read anchors C0 and C, the learning base B (addendum D17: the base card alone under
# the manifest's ``base_card``; with 'format' B mounts what C0 mounts), and the two gate candidates.
MOUNT_ARMS = ('F', 'B', 'C0', 'C', 'cand_card', 'cand_program')
# The base of every learned mount (addendum D17), a sealed manifest field: 'format' composes a learned card with the
# format block (the code default: the behaviour before D17, kept for the golden tests), 'historical' with the whole
# historical card C (the typed-v2 smoke and real run). The read arms C0 and C never depend on it.
BASE_CARDS = ('format', 'historical')
BASE_CARD_DEFAULT = 'format'
# Smoke slices (design §5.9): tiny, every unit type exercised; panels are held-out practice items (no consent).
SMOKE_SLICES = {bench: {'learn': 2, 'gate': 3, 'panel': 2} for bench in ORDER}
EXIT_COMPLETE, EXIT_PAUSED, EXIT_AWAITING = 0, 3, 5


def is_typed_v3(configuration):
    """One version mechanism (DESIGN 3.5): true for this version's configuration only, no compatibility switch (the
    typed-v2 name ``is_typed_v2`` went with the version, as typed-v1's ``is_typed_v1`` did; nothing outside ``typed``
    used it)."""
    return configuration == CONFIGURATION


# typed-v3 program learning (CHAIN-DECISIONS T8), a sealed manifest field set at prepare (CLI --program-learning):
# 'single' (the code default) is typed-v2's flow -- proposals, one smoke unit, the gate -- with byte-identical records;
# 'repair' runs the zero-call probe, the free repair rounds, the one paid feedback round and the gate (``chain``).
PROGRAM_LEARNING = ('single', 'repair')
PROGRAM_LEARNING_DEFAULT = 'single'
# The limits of 'repair' (read through ``Services.limits`` with these defaults; under 'single' they are never read
# and never recorded, so a typed-v2 style ``decisions.json`` keeps its five limit keys): free repair rounds per
# program slot, and paid feedback rounds (0 switches the paid round off; T8 allows one).
PROGRAM_REPAIR_ROUNDS = 3
PROGRAM_PAID_FEEDBACK = 1
REPAIR_LIMITS = {'program_repair_rounds': PROGRAM_REPAIR_ROUNDS, 'program_paid_feedback': PROGRAM_PAID_FEEDBACK}
# typed-v3 archive packages (CHAIN-DECISIONS T9), a sealed manifest field set at prepare (CLI --archive): {} (the code
# default: no archive) or, per chain, the packages of ``archive/index.json`` (``archive.sealed``); only with 'repair'.
ARCHIVE_CHOICES = ('none', 'index')
ARCHIVE_DEFAULT = 'none'
# typed-v3 item stage (CHAIN-DECISIONS T3 to T6; build brief P2b), a sealed manifest field set at prepare (CLI
# --item-stage): 'none' (the code default) is typed-v2's step flow with byte-identical records; 'planned' runs, before
# the gate units of each step, the item stage (``itemstage``: diagnose, the analyst's plan, the made or selected items,
# their check, at most one replacement round, the write-once ``s<k>/items.json``), and the step's gate units then run
# on the gate list J. Under 'planned' the manifest also seals the quota table ``item_quotas`` (``prepare``).
ITEM_STAGES = ('none', 'planned')
ITEM_STAGE_DEFAULT = 'none'
# The benches without made items in typed-v3 and why (CHAIN-DECISIONS, last section: OfficeQA after the audit B36,
# reading 丙; build decision B3: no SpreadsheetBench maker in this version). Their rows of the sealed quota table are
# zero (``prepare`` refuses any other), their steps make no call of the stage and record the reason (J = R).
ITEM_ZERO_REASONS = {'officeqa': 'audit_bing_B36', 'spreadsheetbench': 'maker_not_built'}
# typed-v3 gate rule (CHAIN-DECISIONS T7; build brief P3b), a sealed manifest field set at prepare (the preset
# ``--typed-v3``), written only when not 'whole': 'whole' (the code default) is typed-v2's rules on the step's whole
# gate list with byte-identical records; 'evolution' accepts a card on E = R + A (the real gate items and the
# judging-side attack items: the gain on E reaches tau_E from the baseline's repeats on E, more items of E better than
# worse) when ``no_regress`` holds on the whole list J. On a step without made items (J = R: OfficeQA,
# SpreadsheetBench) it IS 'whole' (``card_decision``). Programs, typing no-harm and member checks keep their rules. Only
# with the item stage 'planned'.
GATE_RULES = ('whole', 'evolution')
GATE_RULE_DEFAULT = 'whole'
# typed-v3 screen (T7), a sealed manifest field (bool), written only when True: True runs, before the R paid runs of
# every candidate's gate on a step with judging-side attack or guard items (card rounds, engineer program slots, the
# archive package), the candidate ONCE on A + G (unit ``<gate unit stem>-screen``); it goes on iff R * c >= b (and, for
# a program or package, it fired on at least one of those items). False (the code default) runs no screen. Only with
# the item stage 'planned'.
GATE_SCREENS = (False, True)
GATE_SCREEN_DEFAULT = False
# typed-v3 resume replay (CHAIN-DECISIONS B6 d), a sealed manifest field set at prepare (CLI --resume-replay), written
# only when 'on': 'off' (the code default) is typed-v2's resume, where a solver cell interrupted after its reply was
# saved and before its record was written is solved (sent and charged) again; 'on' answers such a cell's saved
# receipts from its calls file (gate, noise, outcomes, diagnose, items-check, learn, screen and read cells;
# ``units.replaying``; each occurrence of a request by its own saved outcome, ``units.ReplayRule``; a file whose sends
# name no occurrence is refused, the unit pauses 'replay_refused'; a cell re-run after an archived infrastructure or
# configuration outcome replays its delivered receipts only; a provider's content-filter refusal, B7's final
# model-side outcome, is replayed wherever it stands, B7b), replays the role calls' saved receipts by the same rule
# (``chain._Run.role``; 'repair' with 'off' keeps cb80dcc's unnumbered role-call replay), and settles a pending call
# from its saved receipt when the resumed ledger opens (``units.durable_receipts``; a sealed read unit only after its
# read's own checks, ``reads.unit_gate``). The typed-v3 preset turns it on.
RESUME_REPLAYS = ('off', 'on')
RESUME_REPLAY_DEFAULT = 'off'

# The economy read plan (addenda D9, D10, RP1 to RP13; spec/read-plan.md R1): its constants are defined in
# ``readplan`` and re-exported here -- the read plans with the code default 'full' (typed-v1's reads; the typed-v2
# smoke and real run seal 'economy', which requires 'learn_first'), the identity and record versions of section 3 and
# the pause reasons of 3.6. Resolved on first access (PEP 562): importing this package stays free of the frozen
# machinery that ``readplan`` imports (``units``), so the snapshot binding of ``scripts/run_typed.py`` can import it.
READ_PLAN_EXPORTS = ('READ_PLANS', 'READ_PLAN_DEFAULT', 'IDENTITY_VERSION', 'PLAN_VERSION', 'ALIAS_VERSION',
                     'INPUTS_VERSION', 'IDENTITIES_VERSION', 'SOLVER_SETTINGS_VERSION', 'READ_PLAN_PAUSES',
                     'READ_PLAN_REASONS')


def __getattr__(name):
    if name in READ_PLAN_EXPORTS:
        from . import readplan
        return getattr(readplan, name)
    raise AttributeError('module %r has no attribute %r' % (__name__, name))


def __dir__():
    return sorted(list(globals()) + list(READ_PLAN_EXPORTS))
