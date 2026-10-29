"""Registered constants of protocol ``fivebench-execskill-v1`` (docs/handoff/execskill-registration-v1-20261021.md,
cited as "§n" below; written before any route-B build or run, revised once after the Codex round, §20, and amended with
the owner's rules of 2026-10-21 22:3x, §0 and §21). Each value is transcribed from the registration with its section
next to it; the caps are those of the zero-call arithmetic docs/handoff/execskill-calc-output-20261021.txt (§9.3,
appendix A: T6, T7, T10, T11). Values marked "implementation-time registration" are fixed here because the
implementation plan (docs/handoff/execskill-implementation-plan-v1-20261021.md §11) asks the implementers to register
them; they are frozen by sha256 before S2. Changing any value after launch is a new protocol version
(``fivebench-execskill-v1.1``, §9.4) in a new directory. Where this module and the plan disagree, the registration wins.

The sibling modules import their registered values from here; ``client`` keeps the solver clients and the elucid echo
set (ticket A2-1), ``registry`` the consumption purposes and ``policy`` the procedure source policy, and
tests/test_execskill_protocol.py asserts that their copies agree with this module.

Besides constants the module holds the registered formulas (the J3/J4 boundaries, the ledger bound B, the seed tags)
and the stamp every new record carries (§1): ``version`` = ``kind(<kind>)``, ``evidence`` and ``record_sha256``.
"""
from __future__ import annotations

import hashlib
import math
import re
from fractions import Fraction

from skillopt.coevo5.protocol import PLACEBOS_CONFIRM, PLACEBOS_SCREEN, STRONGER_OPTION
from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import VERSION

MILLION = 1_000_000  # tokens (caps)

# ------------------------------------------------------------------------------------------------------ identity (§1)
KIND = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
RECORD_HASH = "record_sha256"  # plan §2: the canonical digest of the record without this field
# §1 evidence labels; ``main_real_run``: the owner's five-bench main experiment (registrar "Owner instructions
# 2026-10-22 17:0x and 17:3x"), accepted wherever ``pilot_real_run`` is accepted for a real run (``REAL_RUN_EVIDENCE``)
EVIDENCE = ("engineering_fixture", "smoke", "pilot_real_run", "historical_replay", "main_real_run",
            "main_v2_real_run",  # v2 (owner decision 2026-10-23 13:3x): the "train then accept" main experiment
            "main_v2_1_real_run",  # v2.1 (owner decision 2026-10-24 02:2x): main-v2 with two engineer rules
            "main_v2_2_real_run", "main_v2_3_real_run", "zebra_pc_v1_real_run", "zebra_pc_v2_real_run",
            "zebra_pc_v3_real_run", "zebra_pc_v4_real_run", "alfworld_v1_real_run", "zebra_pc_v5_real_run",
            "alfworld_v2_real_run", "zebra_pc_v6_real_run", "alfworld_v3_real_run", "zebra_pc_v7_real_run", "alfworld_v4_real_run",
            "zebra_pc_v8_real_run", "alfworld_v5_real_run", "zebra_pc_v9_real_run", "alfworld_v6_real_run",
            "zebra_pc_v10_real_run", "alfworld_v7_real_run", "zebra_pc_v11_real_run", "alfworld_v8_real_run", "zebra_pc_v12_real_run", "alfworld_v9_real_run", "alfworld_v10_real_run", "alfworld_v11_real_run",
            "baseline_v210_real_run", "main_v3_real_run")
IMPORTABLE = ("fivebench-coevolution-v3-sheet-qualification",)  # §1, owner #7, Codex F15: the one v3 record kind read
TEXTS_IMPORT = "fivebench-coevolution-v3-texts-import"  # §2.2: the v3 task cards, imported by value (plan §6)


def kind(name):
    """The version stamp of a record of kind ``name`` (§1): ``fivebench-execskill-v1-<name>``."""
    require(type(name) is str and KIND.fullmatch(name), "Invalid record kind")
    return VERSION + "-" + name


def record(name, evidence, fields):
    """A new record of this protocol (§1; plan §2): ``fields`` stamped with ``version`` = ``kind(name)`` and the
    ``evidence`` label, sealed with ``record_sha256``."""
    require(evidence in EVIDENCE, "Unknown evidence label")
    require(isinstance(fields, dict) and not {"version", "evidence", RECORD_HASH} & set(fields),
            "A record's fields leave version, evidence and record_sha256 to the stamp")
    return seal({**fields, "version": kind(name), "evidence": evidence}, field=RECORD_HASH)


def verified(value, name=None):
    """``value`` when it is a sealed record of this protocol (of kind ``name`` when given) with a known evidence label;
    a record of another protocol (a v3 stamp included), of another kind or with a broken hash raises ValueError."""
    value = verify(value, field=RECORD_HASH)
    version = value.get("version")
    require(type(version) is str and version.startswith(VERSION + "-")
            and KIND.fullmatch(version[len(VERSION) + 1:]), "Not a %s record" % VERSION)
    revised = {"engineer", "procedure", "acceptance-sealed", "decision", "unit", "unit-started", "unit-status",
               "unit-completed", "manifest", "cell", "judge", "step"}
    require(name is None or version == kind(name) or (name in revised and version == kind(name + "-v2-3"))
            or (name == "judge" and version == kind("judge-v2-9-6"))
            or (name == "engineer" and version in (kind("engineer-v2-3-a2"), kind("engineer-v2-9-1"), kind("engineer-v2-9-2"), kind("engineer-v2-9-3"), kind("engineer-v2-9-4"), kind("engineer-v2-9-5")))
            or (name in {"engineer", "procedure", "manifest"}
                and version in (kind(name + "-v2-4"), kind(name + "-v2-5")))
            or (name in {"engineer", "manifest"}
                and version in (kind(name + "-v2-6"), kind(name + "-alf-v1"), kind(name + "-v2-7"),
                                kind(name + "-alf-v2"), kind(name + "-v2-8"), kind(name + "-v2-9")))
            or (name == "procedure" and version in (kind("procedure-v2-8"), kind("procedure-v2-9"))),
            "A record of another kind")
    require(value.get("evidence") in EVIDENCE, "Unknown evidence label")
    return value


# --------------------------------------------------------------------------------------------- benches and pilots
BENCHES = ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")  # §3.1: the five (v3's order)
QA = ("searchqa", "officeqa", "livemath")  # §2.3, §5.2: the question-answering benches
SIMILAR_PAIRS = (("searchqa", "officeqa"), ("officeqa", "livemath"), ("officeqa", "spreadsheetbench"))  # §8.2
# §11, owner #1 (default taken 22:3x): the pilot is SB -> OQ; the recommended SB -> ALF is kept for the record and the
# code runs either without edits (plan §11). Per chain (§9.3; calc T6, T11): the pilot root's solver cap (steps + one
# test read + the redo reserve, rounded up to a multiple of 5M), the test-read cap and the redo reserve (= the largest
# single acceptance block's cap: one OQ block of 25 items, one ALF block of 10 rooms).
# Registrar "Owner instructions 2026-10-22 17:0x and 17:3x" (they supersede the two-step pilot, owner #1 and #13): the
# run configuration ``main`` -- one chain over all five benches in v3's order (``BENCHES``), both chains G and D, one
# test read per chain at its end; its caps are each at least 3 x their computed maximum need (``MAIN_STEP_CAPS``
# below, with the arithmetic). The three are the run CONFIGURATIONS a launch manifest names (its ``configuration``
# field, carried by the Setting as ``extra["configuration"]``, ``configuration_of``); every consumer follows that
# field, never ``PILOT`` / ``ORDER``, which stay the defaults of fixtures and of a manifest made without one.
PILOTS = {
    "default": {"order": ("spreadsheetbench", "officeqa"), "solver_cap": 180 * MILLION,
                "test_read_cap": 99 * MILLION, "redo_reserve": 14_800_000},
    "recommended": {"order": ("spreadsheetbench", "alfworld"), "solver_cap": 300 * MILLION,
                    "test_read_cap": 126 * MILLION, "redo_reserve": 22_900_000},
    "main": {"order": BENCHES, "solver_cap": 1_520 * MILLION, "test_read_cap": 407 * MILLION,
             "redo_reserve": 72 * MILLION},
}
CONFIGURATIONS = PILOTS  # the same table under the name the manifest's ``configuration`` field uses
PILOT = "default"
ORDER = PILOTS[PILOT]["order"]  # owner #13: the pilot is the chain's first two steps; later steps: formal addendum
MAIN = "main"

# ------------------------------------------------------------------------------- solvers and chains (§0 (c), §4.1)
CHAINS = {"G": "glm-5.3", "D": "deepseek-v4.1-flash-1017"}  # §21: two parallel chains, each its own caps and scopes
SOLVERS = tuple(CHAINS.values())
SMOKE_SOLVER = CHAINS["D"]  # §0 (c), §10: the registered default smoke solver (chain D, elucid)
# registrar addendum 2026-10-23 02:3x ("smoke solver chain"): the smoke specification pins its solver chain -- "D",
# the registered default (unchanged), or "G": GLM-5.3 through its frozen client with chain G's settings, and no S1
SMOKE_SOLVER_CHAINS = ("D", "G")
NAMESPACES = ("G", "D", "smoke", "G-v2", "D-v2", "G-v2-1", "D-v2-1", "G-v2-2", "D-v2-2", "G-v2-3", "D-v2-3")  # §3.4: one consumption namespace per chain,
# the smoke its own;
# v2 (owner decision 2026-10-23 13:3x): each chain of the main-v2 configuration consumes in its own namespace
# (``V2_NAMESPACES``, ``namespace_of``), so it cuts the registered slices from the same fixed order again: its run
# slices are v1 main's training items (reused for training) and its acceptance slices the ones v1 cut but never
# registered (v1 main accepted nothing, so no acceptance item was ever dispatched); the pools hold no other supply
# (OfficeQA 74 = 24 + 50, LiveMath 283 = 119 + 100 + 64, SpreadsheetBench 91 = 31 + 60)
V2_NAMESPACES = {"G": "G-v2", "D": "D-v2"}
# v2.1 (owner decision 2026-10-24 02:2x): main-v2-1's chains consume in namespaces of their own again and cut the same
# slices: main-v2 dispatched no acceptance item either (chain G stopped in step 3's training, chain D in step 1's run)
V21_NAMESPACES = {"G": "G-v2-1", "D": "D-v2-1"}
# v2.2 (owner decision 2026-10-24 12:1x): main-v2-2's chains consume in namespaces of their own and cut the same slices
# again; main-v2-1 did dispatch acceptance items (chain D's LiveMath round), so these slices are reused there
# (``ACCEPT_FRESHNESS``)
V22_NAMESPACES = {"G": "G-v2-2", "D": "D-v2-2"}
V23_NAMESPACES = {"G": "G-v2-3", "D": "D-v2-3"}
ROLE_MODEL = "glm-5.3"  # §4.2, §4.3, §7.2: every method role of both chains
# §4.1 chain G: M = B = 65,536 on every bench and a 2,400 s read timeout (the frozen route, coevo5 protocol.py:327,
# :92), so a chain G receipt is never over nominal.
GLM_SOLVER_TOKENS = 65_536
GLM_READ_TIMEOUT = 2_400
# §4.1 chain D (deepseek through elucid): the nominal M sent in the body and the read timeout, per bench; the ledger
# bound B follows branch E or N, decided by S1-b and written into the manifest (``ledger_bound``).
ELUCID_MAX_TOKENS = {"searchqa": 8_192, "officeqa": 8_192, "livemath": 8_192, "spreadsheetbench": 16_384,
                     "alfworld": 1_024}  # ALFWorld: per step
ELUCID_READ_TIMEOUT = {"searchqa": 600, "officeqa": 600, "livemath": 600, "spreadsheetbench": 900, "alfworld": 180}
BRANCHES = ("E", "N")  # E: the gateway enforces M, B = 2M; N: B = max(4M, ceil(1.5 x the longest probe reply))
B_PROBE = 32_768  # §10 S1-b, c, e (check C15): the probe ledger's bound before B exists
S1D_TOKENS = 64  # §10 S1-d: the 8 concurrent probes use M = B = 64
TRUNCATION_MARGIN = 16  # §4.1: visible completion >= M - 16 with an unclosed tag or fence counts as truncated
REASONING_EFFORT = "none"  # §4.1: chain D's request body; every receipt is checked for reasoning
TEMPERATURE = 0  # §4.1, both chains
GATEWAY = "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"  # §4.1: the explicit PJLAB gateway
ELUCID_ENV = "/root/.config/weak-solver/elucid.env"  # §4.1: address and key, read by path only, never printed
# §4.1 concurrency (plan §1): glm-5.3 10 (coevo5 protocol.py:331), shared by chain G's solver cells and BOTH chains'
# role calls; elucid 8, chain D and the smoke only; the native and episode pools are machine-wide (§11 owner #10).
SLOTS = {"glm-5.3": 10, "deepseek-v4.1-flash-1017": 8, "spreadsheet-native": 3, "alfworld-episode": 6}


def solver_tokens(model, bench):
    """The nominal M a solver request names (§4.1)."""
    require(model in SOLVERS and bench in BENCHES, "Unknown solver or bench")
    return GLM_SOLVER_TOKENS if model == CHAINS["G"] else ELUCID_MAX_TOKENS[bench]


def read_timeout(model, bench):
    """A solver request's read timeout in seconds (§4.1)."""
    require(model in SOLVERS and bench in BENCHES, "Unknown solver or bench")
    return GLM_READ_TIMEOUT if model == CHAINS["G"] else ELUCID_READ_TIMEOUT[bench]


def ledger_bound(model, bench, *, branch=None, longest=None):
    """The ledger bound B a solver endpoint is built with (§4.1): chain G 65,536 (= M); chain D 2M on branch E and
    max(4M, ceil(1.5 x ``longest``)) on branch N, ``longest`` being the longest completion the S1 probes saw."""
    nominal = solver_tokens(model, bench)
    if model == CHAINS["G"]:
        require(branch is None and longest is None, "Chain G has one bound")
        return nominal
    require(branch in BRANCHES, "Branch E or N, from S1-b")
    if branch == "E":
        require(longest is None, "Branch E needs no probe length")
        return 2 * nominal
    require(type(longest) is int and longest > 0, "Branch N needs the longest probe completion")
    return max(4 * nominal, -(-3 * longest // 2))


# Registrar addendum 2026-10-22 14:10, row 7 (implementation-time registration; ``chain.first_call``): before a chain's
# first paid unit, ONE solver call alone through the chain's own solver client with its registered settings on the
# bench of that unit (FIRST_CALL_BENCH: chain G M = B = 65,536, read timeout 2,400 s; chain D the bench's M, read
# timeout and B), on this fixture prompt -- smoke S1-a's (no pool item, nothing consumed; 101 bytes) -- charged to
# ``<c>:solver`` in the sub-scope ``<c>:confirm`` (``budgets.first_call_caps``) with FIRST_CALL_CAP: four full
# reservations at B = 65,536 (4 x 4 x (101 + 512 + 65,536) = 1,058,384) rounded up to 0.1M, so a relaunch after up to
# three calls charged at their full bound (timeouts, server errors) is still admitted. It fits in the solver cap's
# rounding margin (§9.3: 180M - 175.1M).
FIRST_CALL_SYSTEM = "You are a connectivity probe. Follow the user's instruction exactly."
FIRST_CALL_USER = "Reply with the single word: ready"
FIRST_CALL_BENCH = ORDER[0]  # the default configuration's; a run uses ``first_call_bench`` of its configuration
FIRST_CALL_CAP = 1_100_000


def first_call_bench(configuration=PILOT):
    """The bench of a chain's first-call confirmation in ``configuration``: its first step's (``main``: SearchQA)."""
    require(configuration in CONFIGURATIONS, "Unknown run configuration")
    return CONFIGURATIONS[configuration]["order"][0]


# ---------------------------------------------------------------------------------------------- method roles (§4.2-4.3)
ROLE_MAX_TOKENS = 16_384  # M = B for every role call (coevo5 protocol.py:31)
ROLE_READ_TIMEOUT = 900
ROLE_REASONING = "low"
ROLE_INPUT_BYTES = 220_000
ENGINEER_CALLS = 6  # per step
ENGINEER_SHOWN = {"failures": 12, "successes": 6}  # run-slice trajectories shown to the engineer

# --------------------------------------------------------------------------------- procedures and packages (§2.1-2.3)
HOOKS = ("applies", "before_call", "bindings", "sheet_feedback", "alf_before_step", "alf_after_step")  # closed set
MAX_PROCEDURE_BYTES = 6_000  # one procedure module (= policy.MAX_SOURCE_BYTES)
MAX_CONSTANT_CHARS = 2_000  # a module-level literal (= policy.MAX_CONSTANT_CHARS)
MAX_DESCRIPTION_CHARS = 600  # for people only, never shown to the solver
MAX_PROCEDURES = 24  # per package
MAX_PACKAGE_BYTES = 64_000  # all sources of a package
MAX_HEADER_CHARS = 200  # plan §2.1: a procedure's constant note header
NOTES_KEY = "procedure_notes"  # §2.3: the last key of the user JSON, absent when empty
MAX_NOTE_CHARS = {"searchqa": 4_000, "officeqa": 4_000, "livemath": 4_000, "spreadsheetbench": 4_000,
                  "alfworld": 1_500}  # §2.3: QA and sheets per request, ALFWorld per step
ALFWORLD_ROUTING_VIEW = ("initial_observation", "admissible_commands_at_reset", "task_text")  # §2.3

# ------------------------------------------------------------------------------------ exact computation (§2.4, §2.5)
MAX_CALC_TAGS = 8
MAX_CALC_CHARS = 300  # per expression
MAX_EXPONENT = 12  # |integer exponent|
MAX_DEPTH = 20  # nesting
MAX_BITS = 4_096  # numerator or denominator of any intermediate value
NOT_EVALUATED = "not evaluated"  # a failed computation, and every placebo computation (§6.1)
COMPUTE_INVITE = ("If you need arithmetic, you may write <calc>EXPRESSION</calc> tags (at most 8) using these names or "
                  "plain numbers; they will be evaluated exactly and returned to you once.")
COMPUTE_FOLLOWUP = ("The expressions above were evaluated exactly. Use these values if they are relevant and give your "
                    "final answer in the required format.")
MAX_RUN_MESSAGE_CHARS = 500  # §2.5: the pre-check's last traceback line

# Implementation-time registration (plan §11; §2.2 gives the facts header verbatim): the shell's fixed headers of the
# typed note fields, the ALFWorld discouragement prefix and SpreadsheetBench's repair instruction. The headers and the
# prefix carry no LEXICON term of any bench; the repair frame none of SpreadsheetBench's (which exempts "format").
NOTE_HEADERS = {
    "facts": "Facts extracted by a helper program (may be incomplete):",
    "table": "A table extracted by a helper program (may be incomplete):",
    "candidates": "Candidates listed by a helper program (may be incomplete):",
    "warnings": "Cautions noted by a helper program (may be incomplete):",
    "bindings": "Named values quoted from the task by a helper program:",
}
NOT_RECOMMENDED_PREFIX = "Not recommended by a helper program (still admissible): "
REPAIR_FRAME = ("Your program above was executed once on the public input workbook; the run report and a helper "
                "program's notes follow. Revise the program if needed and give the complete program in the required "
                "format.")
TEMPLATES = {"COMPUTE_INVITE": COMPUTE_INVITE, "COMPUTE_FOLLOWUP": COMPUTE_FOLLOWUP, "NOTE_HEADERS": NOTE_HEADERS,
             "NOT_RECOMMENDED_PREFIX": NOT_RECOMMENDED_PREFIX, "REPAIR_FRAME": REPAIR_FRAME}

# §2.2: answer-format instructions a note field may not carry (the field is dropped and counted as a procedure fault);
# SpreadsheetBench exempts "format". Implementation-time registration of the full list and of its matching rule; the
# tag forms come first, so a field is reported under the most specific term it carries.
LEXICON_TERMS = ("<answer", "<action", "```", "answer", "respond", "output", "return", "json", "only the", "just the",
                 "bare", "single letter", "round", "decimal places", "units", "format")
LEXICON_EXEMPT = {"spreadsheetbench": ("format",)}
LEXICON = {bench: tuple(t for t in LEXICON_TERMS if t not in LEXICON_EXEMPT.get(bench, ())) for bench in BENCHES}
# The registrar decision of 2026-10-22 on ticket A3-1 adopts both options: (a) inflections -- a term that ends with a
# letter also matches with one of LEXICON_SUFFIXES (the last letter may be doubled before "ed" and "ing", as in
# "formatted"; a term ending in "s" also matches without it, as in "decimal place", but takes no suffix there, so
# "units" never matches "united"); (b) a binding's quote and a table cell that occur verbatim in the item's public text
# are the item's text, not the procedure's, and are not screened (LEXICON_VERBATIM); every other note text is.
LEXICON_SUFFIXES = ("s", "es", "ed", "d", "ing")
LEXICON_VERBATIM = {"bindings": "quote", "table": "cell"}
LEXICON_MATCH = ("case-insensitive; a term starting and ending with a letter matches on word boundaries (its spaces "
                 "match any whitespace), also with one of the suffixes s, es, ed, d, ing (its last letter optionally "
                 "doubled before ed and ing) and, when it ends in s, also without that s; any other term matches as a "
                 "substring; a binding's quote and a table cell that occur verbatim in the item's public text are not "
                 "screened, every other note text is")

# -------------------------------------------------------------------- engineer, replay and describer (§5.4, §5.7, §8.1)
# Implementation-time registrations of ticket A10-1 (registrar decision 2026-10-22: moved here by value, unchanged; the
# twins in replay.py, engineer.py and describer.py are asserted equal by tests/test_execskill_protocol.py).
NOTE_HOOKS = ("before_call", "bindings", "sheet_feedback", "alf_before_step")  # = package.NOTE_HOOKS
TRACKER_AGREEMENT = Fraction(97, 100)  # §5.4 C7: a state procedure agrees with the reference on >= 97 % of steps
STATE_FACTS = ("reached", "carrying", "nothing_happens")  # the ALFWorld state contract (the D3 hand tracker's facts)
PROPERTY_KINDS = {  # replay-test property kind -> (the hooks it reads, its keys besides "kind" and an ALFWorld "step")
    "applies_true": (("applies",), ()),
    "applies_false": (("applies",), ()),
    "note_contains": (NOTE_HOOKS, ("value",)),
    "note_matches": (NOTE_HOOKS, ("value",)),  # ordered literal fragments: no model-written regex runs on the host
    "discourage_contains": (("alf_before_step",), ("value",)),
    "discourage_excludes": (("alf_before_step",), ("value",)),
    "binding_equals": (("bindings",), ("name", "value")),
    "repair_requested": (("sheet_feedback",), ("value",)),
    "state_equals": (("alf_after_step",), ("key", "value")),
}
MUTATIONS = {  # replay-test mutation -> the benches whose inputs it perturbs
    "strip_digits": BENCHES,
    "drop_exception_message": ("spreadsheetbench",),
    "program_ok": ("spreadsheetbench",),
    "nothing_happens": ("alfworld",),
}
MAX_TESTS = 8  # replay tests per change
MAX_PROPERTY_TEXT = 200  # characters of a property's text value
MAX_FRAGMENTS = 5  # literal fragments of a note_matches property
SHOWN_TAG = "execskill-v1:engineer-shown"  # + ":<unit label>": the seeded order of the trajectories the engineer sees
DEFAULT_TARGET = 600  # the describer's text length when the procedure showed no note on the run slice

# ------------------------------------------------------------------------------------- examiner (§4.3, §7.1, §7.2)
# Implementation-time registrations of ticket C1-1 (registrar decision 2026-10-22: moved here by value, unchanged; the
# twins in examiner.py are asserted equal by tests/test_execskill_protocol.py). The examiner's calls per step and bench
# are at most DETECTOR_CALLS + POLICY_CALLS + GENERATOR_CALLS x BAND_ROUNDS (calc T11).
GENERATOR_CALLS = 2  # per generate unit; the second only after an unparseable reply (as DETECTOR_CALLS)
POLICY_CALLS = 1  # per step and bench; an invalid reply keeps the previous policy, or an empty one
EXAMINER_PROBE_TAG = "execskill-v1:examiner-probe"  # + ":<generator>:<band|shortcut|g_acc>": the seeded item orders
MAX_RATIONALE = 600  # characters of a policy reply's rationale
MAX_CONCEPT_CHARS = 100  # of a research request's concept
MAX_QUESTION_CHARS = 300  # of a research request's question

# ---------------------------------------------------------------------------------------- placebos and donors (§6.1)
PLACEBO_SOURCE = "skillopt/coevo5/protocol.py:105-124"  # P_i: v3's eight irrelevant texts, imported by value
PLACEBO_CORPUS = PLACEBOS_SCREEN + PLACEBOS_CONFIRM
DONOR_LENGTH_BAND = Fraction(1, 5)  # a donor's content is clipped or extended to the item's length +-20 %

# ------------------------------------------------------------------------------------------- seeds and tags (§3.2)
SEED = 20261021  # the fixed order (data.ranked), sign-flip, bootstrap and validity permutations
ROOMS_TAG = "execskill-v1:rooms"  # §3.1: the seeded order of the ALFWorld rooms
ALFWORLD_ENV_SEED = 42  # frozen runtime (coevo5 protocol.py:355)
SEARCHQA_FRESH_SEED = "searchqa-fresh-20261012"  # §3.1: the existing fresh-sample script's fixed order
SEARCHQA_TAIL_START = 4_001  # §3.1: only positions from here on
TAG_PART = re.compile(r"[^:\s]{1,200}")


def _tag(prefix, *parts):
    require(all(type(p) is str and TAG_PART.fullmatch(p) for p in parts), "A tag part is a short name without ':'")
    return ":".join(("execskill-v1", prefix) + parts)


def order_tag(bench):
    """``execskill-v1:order:<bench>``: ``data.ranked(supply, seed=SEED, tag=order_tag(bench))`` (§3.2)."""
    require(bench in BENCHES, "Unknown bench")
    return _tag("order", bench)


def round_tag(unit):
    """``execskill-v1:round:<unit>``: the interleaved order of one round."""
    return _tag("round", unit)


def detsplit_tag(unit):
    """``execskill-v1:detsplit:<unit>``: the detector write and hold halves (§5.2)."""
    return _tag("detsplit", unit)


def withhold_tag(unit, procedure):
    """``execskill-v1:withhold:<unit>:<p>``: the withholding draw of one procedure (§6.5)."""
    return _tag("withhold", unit, procedure)


def yoke_tag(unit):
    """``execskill-v1:yoke:<unit>``: one run-slice donor per acceptance item (§6.1)."""
    return _tag("yoke", unit)


def discourage_tag(unit, cell):
    """``execskill-v1:discourage:<unit>:<cell>``: the ALFWorld discouragement sham, drawn at dispatch (§6.1)."""
    return _tag("discourage", unit, cell)


def research_split_tag(unit):
    """``execskill-v1:research-split:<unit>``: findings split into the G_self and G_acc halves (§7.2)."""
    return _tag("research-split", unit)


def generator_seed(generator, step):
    """A generator's seed (§3.2): the first 8 hexadecimal digits of sha256("execskill-v1:gen:<id>:<step>")."""
    return int(hashlib.sha256(_tag("gen", generator, step).encode()).hexdigest()[:8], 16)


# ----------------------------------------------------------------------------------------------- data (§3.1, §3.3, §10)
ALFWORLD_ID_PREFIX = "alfworld-xs:"  # §3.1: + the first 16 hex digits of sha256(game file's relative path)
ALFWORLD_ID_HEX = 16
ALFWORLD_UNUSED_GAMES = 3_514  # §3.1: train games outside the 57-game pool
ROOM_GROUPS = {"smoke": 4, "run": 16, "accept": 40, "select": 20, "spare": 28}  # §3.1 (O6): 108 rooms, seeded order
MAX_GAMES_PER_ROOM = 5  # per slice
PRERESET_GAMES = {"smoke": 12, "run": 60, "accept": 150, "select": 200}  # §3.1 (O10): the cut slices only; select is
# an upper bound (supply.UPTO): 20 rooms x MAX_GAMES_PER_ROOM = 100, so the 108-room cut is 322 (smoke S0 10/22 22:07)
# §3.3: (items, runs) of the run and acceptance slices, and the acceptance blocks. LiveMath and SearchQA run only in
# the formal chain and are tentative there (fixed by the formal-chain addendum); SearchQA's acceptance slice comes
# from the fresh tail.
SLICES = {
    "spreadsheetbench": {"run": (31, 2), "accept": (60, 2), "blocks": 1},
    "officeqa": {"run": (24, 2), "accept": (50, 4), "blocks": 2},  # two time blocks of 25, >= 2 h apart, stratified
    "alfworld": {"run": (60, 1), "accept": (150, 1), "blocks": 4},  # blocks of whole rooms, 40 rooms <= 5 games
    "livemath": {"run": (119, 1), "accept": (100, 2), "blocks": 1},  # run: 54 meta-absent + 65 meta-present
    "searchqa": {"run": (300, 1), "accept": (1_000, 1), "blocks": 4},
}
TENTATIVE = ("livemath", "searchqa")
LIVEMATH_RUN = {"meta_absent": 54, "meta_present": 65}  # §3.3, §6.4 J7 (O7)
LIVEMATH_J7_PROBE = 64  # the remaining meta-present items, purpose accept_probe
LIVEMATH_META_OPTION = STRONGER_OPTION  # §5.4 C4 static ban, §6.4 J7 (coevo5 protocol.py:222)
BLOCK_GAP_SECONDS = {"officeqa": 7_200}  # §3.3
MIN_ASTAR = 30  # §3.3, Codex F1: fewer -> decision "not_run_small_astar", nothing consumed
MIN_ASTAR_ROOMS = 20  # ALFWorld
ENTRY_READING_SHARE = Fraction(1, 10)  # §5.1: inherited procedures firing on >= 10 % -> the card arm runs once too
G_ACC = {"spreadsheetbench": 60, "officeqa": 50, "livemath": 100, "alfworld": 0, "searchqa": 0}  # §3.3 (O1): maxima
G_ACC_ARMS = ("S'", "S", "P_y", "C")  # one run each
DUP_ARM = "S_dup"  # §7.2, Codex F9: benches with a generator, after step 1
G_SELF_MAX = 60  # §5.5
EARLIER_SET_MAX = 40  # §5.5: each earlier bench's generated set
ALFWORLD_SELECTED_MAX = 40  # §9.2: ALFWorld's self-test games chosen by the examiner
SMOKE_REAL_ITEMS = {"searchqa": {"S2": 20, "SN1": 200, "S4": 60}, "alfworld": {"S2": 6, "SN1": 6}}  # §10, calc T7
S4_SLICES = {"run": 20, "accept": 40}  # §10 S4, on SearchQA smoke items
# §10 S4, plan §10 step 7 (implementation-time registration): the drill's SandboxUnavailable is raised by the 50th
# sandbox call of the acceptance cells on the accept unit's first attempt -- inside its first block (10 items x the
# procedure arms x the candidate's procedures), so the round has started and the redo re-dispatches it whole
S4_DRILL_CALL = 50
SMOKE_FIXTURES = 20  # §10: engineering fixtures each for OfficeQA, LiveMath, SpreadsheetBench
TEST_RUNS = 1  # §8.1 (O3)
OFFICEQA_TEST_BLOCKS = 2  # §8.1: 172 items as two time blocks of 86

# --------------------------------------------------------------------------------- maximum schedule (§9.2, Codex F18)
MAX_CHANGES = 3  # edits per step
MAX_TWINS_PER_ITEM = 2  # acceptance and test read
BAND_ROUNDS = 3  # band probes: the first and at most two adjustments
SELFTEST_PASSES = 2
PREFUNDED_REDOS = 1
MAX_REDOS = 2  # §3.4, §9.3: a second redo needs the owner's recorded cap decision (recovery.json)
TWIN_MIN_FIRED = 10  # §6.5: |F_p| >= 10
INHERITED_TWIN_MIN_FIRED = 15  # §6.5: inherited procedures

# ----------------------------------------------------------------------------------------- acceptance J1-J7 (§6.4)
ALPHA = 0.05  # one-sided paired t-test (J1, J2); large-sample approximate (calc T9)
HARMFUL_SHAM_ALPHA = 0.025  # §6.1: P_y - S upper bound < 0 -> S' - S alone, at 2.5 %
MIN_WHOLE_BATCH = Fraction(1, 50)  # J1: whole-batch mean difference >= 2 points
FAULT_SHARE_MAX = Fraction(1, 50)  # J3: fault items / |A| <= 2 % (Codex F22)
FORMAT_MARGIN_MIN = 2  # J4: S' violating items <= S's + max(2, ceil(0.02 |A*|))
FORMAT_MARGIN_SHARE = Fraction(1, 50)
ALFWORLD_ADMISSIBLE_MIN = Fraction(9, 10)  # J4: an episode with an admissible share < 0.9 violates the format
INFRA_UNKNOWN_MAX = Fraction(1, 10)  # J5 per arm (and §5.1 run slice): else pause
REASONING_MISMATCH_MAX = Fraction(1, 100)  # J5: after resends
SHARED_UNANSWERED_MAX = Fraction(1, 10)  # J5: of A*
START_BALANCE_MAX = Fraction(1, 20)  # §6.2: arms' median dispatch start within 5 % of the round's duration
# §3.3, calc T1 (registrar decision 2026-10-22 on ticket A9-3): the registered minimum detectable effect per bench, in
# accuracy points, at joint 80 % power with rho = 0.5 under the whole-batch convention (LiveMath: the high-noise row);
# ``decision.json`` records it as ``mde_registered``. A written pre-pilot amendment replaces it when S-N1 measures noise
# more than 25 % above the assumption (NOISE_REREGISTER).
MDE_POINTS = {"spreadsheetbench": 12.1, "officeqa": 10.0, "searchqa": 3.4, "alfworld": 9.7, "livemath": 10.0}
DUP_ALPHA = 0.01  # J6: two-sided; below it the run pauses
META_PROBE_GAIN = Fraction(1, 10)  # J7 (LiveMath, formal chain): options-only S' - C >= 10 points ...
META_PROBE_ALPHA = 0.05  # ... with one-sided p < 0.05 -> shortcut, rejected
SECOND_CALL_FLAG = Fraction(1, 10)  # §6.1, Codex F5: second-call or repair-call rates differing by > 10 points
TIME_WINDOW_SECONDS = 900  # §6.2, §8.3: short-answer share and others per 15 minutes
SELFTEST_FAULT_MAX = Fraction(1, 50)  # §5.5 (a)
SELFTEST_FORMAT_MARGIN = Fraction(1, 20)  # §5.5 (b): >= 5 points worse ...
SELFTEST_ALPHA = 0.05  # ... with a one-sided sign test p < 0.05
SIGNFLIP_FLIPS = 100_000  # §3.2: sensitivity analyses only, never deciding
BOOTSTRAP_RESAMPLES = 10_000


def fault_items_max(accept_items):
    """J3 (§6.4; calc T10): the most fault items an acceptance slice A of this size admits."""
    require(type(accept_items) is int and accept_items > 0, "Invalid acceptance size")
    return accept_items * FAULT_SHARE_MAX.numerator // FAULT_SHARE_MAX.denominator


def format_margin(astar_items):
    """J4 (§6.4; calc T10): max(2, ceil(0.02 |A*|)) items."""
    require(type(astar_items) is int and astar_items > 0, "Invalid decision subset size")
    share = FORMAT_MARGIN_SHARE
    return max(FORMAT_MARGIN_MIN, -(-astar_items * share.numerator // share.denominator))


# ----------------------------------------------------------------------------------------------- detectors (§7.1)
DETECTORS_PER_STEP = 3
DETECTOR_CALLS = 2
DETECTOR_MIN_FIRED = 10  # cells
DETECTOR_MIN_ITEMS = 6
DETECTOR_MIN_ROOMS = 4  # ALFWorld
DETECTOR_LIFT = Fraction(1, 10)  # null: precision - residual base failure rate <= 0.10
HOLM_FAMILY = 0.10  # Holm over the step's <= 3 candidates (Codex F11)
DETECTOR_MIN_RECALL = Fraction(3, 20)
DETECTOR_MAX_JACCARD = Fraction(4, 5)  # on the full masked hold half, before residualization
MIN_ROOMS_PER_HALF = 8  # ALFWorld halves split by room; fewer -> cannot be decided
DETECTOR_RETIRE_MISSES = 2  # consecutive misses on later hold halves of the bench
LANDMARK_STEPS = 10  # Codex F10: episodes still active before step 10, their first 10 steps
ALFWORLD_MAX_STEPS = 50  # frozen runtime (coevo5 protocol.py:355)

# ------------------------------------------------------------------------------- research and generators (§7.2, §21)
RESEARCH_MAX_ROUNDS = 3  # per request (coevo5 protocol.py:254)
RESEARCH_MAX_QUERIES = 3  # per round (:255)
RESEARCH_MAX_PAGES = 3  # per request (:256)
RESEARCH_MAX_CALLS = 8  # model calls per request, invalid replies included (:257)
RESEARCH_REQUESTS = ("family_material", "parameter_choice", "selection_hint")  # the request kinds (plan research)
MAX_RESEARCH_REQUESTS = 24  # per step and bench (calc T11)
MAX_SPECS = MAX_RESEARCH_REQUESTS  # specs per generator reply: one research request yields at most one material (C1-1)
MAX_ITEMS_PER_FINDING = 10
BAND = (Fraction(1, 5), Fraction(4, 5))  # the parent's pass rate on the band probe
BAND_PROBE_ITEMS = 30  # one run each
SHORTCUT_PROBE_ITEMS = 30  # card arm, two runs (§9.2)
SHORTCUT_RUNS = 2  # items right in both runs are dropped
SHORTCUT_DROP_MAX = Fraction(1, 4)  # a larger dropped share discards the whole set
KEY_SHARE = Fraction(1, 5)  # LiveMath: each answer letter 20 % +- 5 %
KEY_TOLERANCE = Fraction(1, 20)
LIVEMATH_DIGITS = 50  # the fixed checker's precision
LIVEMATH_DEFINITION_CHARS = 1_500  # a verbatim Wikipedia definition or theorem
OFFICEQA_TABLE_ROWS = (2, 60)  # an eligible numeric table (coevo5 research.py:59)
OFFICEQA_TABLE_COLUMNS = (2, 15)
VALIDITY_MIN_ROUNDS = 8  # Codex F9: refuted and validated both need >= 8 acceptance rounds
VALIDITY_SE_MULTIPLE = 2  # |d_gen - d_real| > 2 sqrt(se_gen^2 + se_real^2 - 2 cov)
VALIDITY_MIN_DISAGREEMENTS = 2  # rounds
VALIDITY_ALPHA = 0.05  # Spearman > 0 with a permutation p over rounds (seed SEED)
VALIDITY_PERMUTATIONS = 10_000
VALIDITY_STATUSES = ("refuted", "validated", "not_evaluable")  # precedence in this order

# ------------------------------------------------------------------------------------------ the test read (§8.1-8.2)
TEST_ARMS = ("F", "C", "P_F", "T_F", "twins")
TEXT_LENGTH_BAND = Fraction(1, 5)  # T_F: the description within +-20 % of the procedure's median note length
NI_MARGIN = Fraction(1, 20)  # Q3 and the code-vs-text readings: -5 points
NI_MIN_FIRED = Fraction(1, 10)  # Q3: fired on < 10 % -> "cannot act by construction", never "non-inferior"
CANNOT_ACT_FIRED = Fraction(1, 20)  # label 4: fired on < 5 % of every other bench
TEST_START_FACTOR = Fraction(13, 10)  # §9.3: remaining solver budget >= 1.3 x the corrected test-read estimate
CONSENT_FIELDS = frozenset({"test_evaluation", "sheet_test_qualification", "multi_arm_arms", "by", "date", "note"})
EXCLUSION_CONSENT_FIELDS = frozenset({"exclusion_runs", "by", "date", "note"})  # §8.1 (O4): a separate file
EXCLUSION_RUNS = ("alfworld_test_identity_check", "searchqa_test_exclusion")
# run-root relative files (§8.1; plan §2.10). CANARIES: implementation-time registration of where the test-content
# canaries (sha256 fragments only, Codex F16) are kept.
EXCLUSION_CONSENT = "shared/exclusion-consent.json"
OWNER_CONTINUATION = "shared/owner-continuation.json"
FORMAL_ADDENDUM = "shared/formal-addendum.json"  # the sealed record of the document below (evaluation.seal_addendum)
FORMAL_ADDENDUM_DOCUMENT = "shared/formal-addendum.md"  # §8.1, owner #32: the owner's formal-chain addendum
CANARIES = "shared/test-canaries.json"
# registrar addendum 2026-10-23 05:3x: the owner's smoke waiver (smoke-root relative; only the owner writes it) and the
# only smoke rows it may waive (smoke.waiver, chain.read_estimate_record)
SMOKE_WAIVER = "shared/owner-smoke-waiver.json"
WAIVABLE_SMOKE_ROWS = frozenset({"S2.format"})
EXCLUSION_DIR = "shared/exclusion"  # ``exclude-tests`` writes the two S0 exclusion records here (fixer-8, C3-2)
LEDGER = "shared/ledger"  # the smoke's ledger; chains G and D each have their own (budgets.ledger_root, C2-1)

# ---------------------------------------------------------------------------------- budgets (§9.1-9.3; calc T6-T11)
# §9.1 per-cell solver tokens (prompt + reply), low / high; ALFWorld per episode; arms with procedures x1.25 / x1.6.
CELL_ANCHORS = {"searchqa": (1_535, 3_400), "officeqa": (5_246, 7_927), "livemath": (1_602, 3_969),
                "spreadsheetbench": (2_561, 4_273), "alfworld": (36_000, 45_000)}
PROCEDURE_ARM_FACTOR = (Fraction(5, 4), Fraction(8, 5))
# §9.3, calc T6: per chain and step: run / examiner (incl. G_acc) / self-test / acceptance; every cap = 1.5 x the
# maximum-schedule high estimate + one full next reservation, rounded up to 0.1M. LiveMath and SearchQA steps
# get theirs from the formal-chain addendum.
STEP_CAPS = {
    "spreadsheetbench": {"run": 1_200_000, "examiner": 3_500_000, "selftest": 2_600_000, "accept": 8_300_000},
    "officeqa": {"run": 2_300_000, "examiner": 7_300_000, "selftest": 6_600_000, "accept": 29_500_000},
    "alfworld": {"run": 13_200_000, "examiner": 9_900_000, "selftest": 19_100_000, "accept": 91_300_000},
}
# §9.2 maximum schedule (Codex F18) in cells, the counts the caps above derive from and S-E6 projects (§9.3, §10):
# step bench -> step kind -> {bench of the cells: (card cells, procedure cells)}. Calc T4's "max" rows price each cell
# at its bench's high anchor (CELL_ANCHORS) times 1 (card) or the high procedure factor 1.6 (PROCEDURE_ARM_FACTOR):
# S', P_y, P_i and the twins, the parent S and S_dup after step 1, every run cell (T4 prices the run at 1.6), the band
# probe of a parent with procedures, the self-test (which also runs the earlier bench's generated set, at that bench's
# anchor); C, the empty parent S of step 1 and the shortcut probe are card cells. T6's cap of a scope = 1.5 x these
# cells' high tokens + one full next reservation, rounded up to 0.1M. Copied by value from the calc
# (docs/handoff/execskill-calc-20261021.py; tests/test_execskill_protocol.py recomputes them from its functions).
MAX_SCHEDULE_CELLS = {
    "spreadsheetbench": {"run": {"spreadsheetbench": (0, 62)}, "examiner": {"spreadsheetbench": (270, 120)},
                         "selftest": {"spreadsheetbench": (120, 120)}, "accept": {"spreadsheetbench": (240, 600)}},
    "officeqa": {"run": {"officeqa": (0, 96)}, "examiner": {"officeqa": (110, 290)},
                 "selftest": {"officeqa": (0, 240), "spreadsheetbench": (0, 160)},
                 "accept": {"officeqa": (200, 1_400)}},
    "alfworld": {"run": {"alfworld": (0, 120)}, "examiner": {"alfworld": (0, 90)},
                 "selftest": {"alfworld": (0, 160), "spreadsheetbench": (0, 160)},
                 "accept": {"alfworld": (150, 750)}},
}
# §8.1, §9.2: the one test read of a pilot at its maximum (calc T5 "MAXIMUM schedule" rows: the high fired shares --
# home 1.0, similar 0.7, other 0.5 -- and 2 twins per fired item): C on every test item (card); F, P_F, T_F and the two
# twins on the fired items (procedure). LiveMath's 0.7 or 0.5 of 125 items gives half cells, kept as the calc has them.
TEST_READ_CELLS = {
    "default": {"searchqa": (400, 1_400), "officeqa": (172, 860), "livemath": (125, 437.5),
                "spreadsheetbench": (279, 1_395), "alfworld": (134, 335)},
    "recommended": {"searchqa": (400, 1_000), "officeqa": (172, 602), "livemath": (125, 312.5),
                    "spreadsheetbench": (279, 1_395), "alfworld": (134, 670)},
    # main: every bench is a home bench (f = 1), so 5 x n procedure cells (calc T5's ``test_read`` with all five
    # benches home and 2 twins per fired item, as tests/test_execskill_protocol.py recomputes it)
    "main": {"searchqa": (400, 2_000), "officeqa": (172, 860), "livemath": (125, 625),
             "spreadsheetbench": (279, 1_395), "alfworld": (134, 670)},
}
# Registrar addendum 2026-10-22 14:10, row 8 (pilot-runbook §3.4): the S-E6-corrected high estimate of the one test
# read that ``chain.read_budget`` gates the read on (§9.3). FIRED_SHARES: the high fired share f_b of §9.2 / calc
# T5 -- 1 on a home bench (the pilot's order), 0.7 on a bench similar to a home bench (SIMILAR_PAIRS), 0.5 on any
# other, the shares TEST_READ_CELLS counts (procedure cells = 5 x n x f); TEST_READ_ESTIMATE_ARMS: F, P_F and T_F on a
# fired item plus one twin (calc T5's high row "with twins"; the maximum schedule's second twin is not priced).
FIRED_SHARES = {"home": Fraction(1), "similar": Fraction(7, 10), "other": Fraction(1, 2)}
TEST_READ_ESTIMATE_ARMS = 4


def fired_share(bench, pilot=PILOT):
    """f_b of ``bench`` in the test read of ``pilot`` (registrar addendum 2026-10-22 14:10, row 8; ``FIRED_SHARES``):
    home, similar to a home bench, or other."""
    require(bench in BENCHES and pilot in PILOTS, "Unknown bench or pilot")
    home = PILOTS[pilot]["order"]
    if bench in home:
        return FIRED_SHARES["home"]
    similar = any(bench in pair and set(pair) & set(home) for pair in SIMILAR_PAIRS)
    return FIRED_SHARES["similar" if similar else "other"]


def _exact(value, name):
    """A positive finite number (an int, a float as stored, or a Fraction) as a Fraction."""
    require(type(value) in (int, float, Fraction) and math.isfinite(value) and value > 0,
            "%s: a positive number" % name)
    return Fraction(value)


def read_estimate_terms(per_cell, ratio, pilot=PILOT):
    """The per-bench terms of ``estimate_test_read``, exact: {bench: ratio x n_b x (card_b + a x f_b x proc_b)} as
    Fractions, a = ``estimate_arms(pilot)`` (4; with main-v2's stage arms 8), from the same inputs with the same
    refusals. A read gate re-applied after some read units completed
    prices only the units still to run, by their terms (registrar addendum 2026-10-22 15:3x, ticket P2C-2;
    ``chain.read_budget``). Named without a ``test_`` prefix, so pytest never collects it."""
    require(pilot in PILOTS and isinstance(per_cell, dict) and set(per_cell) == set(BENCHES)
            and all(isinstance(entry, dict) for entry in per_cell.values()), "S-E6's per-cell tokens of every bench")
    terms = {}
    for bench in BENCHES:
        entry = per_cell[bench]
        card = _exact(entry.get("card"), "%s card cell" % bench)
        assumed = entry.get("procedure_assumed") is True or entry.get("procedure") is None
        proc = card * PROCEDURE_ARM_FACTOR[1] if assumed else _exact(entry["procedure"], "%s procedure cell" % bench)
        terms[bench] = TEST_READ_CELLS[pilot][bench][0] * (card + estimate_arms(pilot) * fired_share(bench, pilot)
                                                           * proc)
    ratio = _exact(ratio, "ratio")
    return {bench: ratio * term for bench, term in terms.items()}


def estimate_test_read(per_cell, ratio, pilot=PILOT):
    """Registrar addendum 2026-10-22 14:10, row 8 (§9.3; pilot-runbook §3.4): the S-E6-corrected high estimate of the
    one test read in ledger tokens, ceil(ratio x sum_b n_b x (card_b + a x f_b x proc_b)) over the five benches (a =
    ``estimate_arms(pilot)``: 4, with main-v2's stage arms 8): n_b the
    bench's test items (``TEST_READ_CELLS``), card_b and proc_b S-E6's measured tokens per card and per procedure cell
    (``per_cell`` = S-E6's ``result.per_cell`` {bench: {"card", "procedure", "procedure_assumed"}}; a procedure cell
    S-E6 did not measure -- ``procedure_assumed`` true or no ``procedure`` -- is 1.6 x the card cell,
    ``PROCEDURE_ARM_FACTOR``), f_b the high fired share (``fired_share``), ``ratio`` S-E6's ledger/actual ratio. Exact:
    every input is taken as a Fraction (a float as stored) and the ceiling is taken once, over the sum of the per-bench
    terms (``read_estimate_terms``)."""
    return math.ceil(sum(read_estimate_terms(per_cell, ratio, pilot).values()))


GLM_CAP = 30 * MILLION  # §9.3: the method roles of one chain (pilot root)
# §9.3, calc T11: per step; registrar addendum 2026-10-22, R7 decision 16:1x (R7b): engineer 1.5M -> 2.5M and examiner
# 2.5M -> 3.0M (admission under the conservative reservation only; GLM_CAP and the chain totals unchanged)
ROLE_CAPS = {"engineer": 2_500_000, "examiner": 3_000_000, "examiner_research": 4_600_000}
SMOKE_CAPS = {"solver": 14 * MILLION, "glm": 2 * MILLION}  # §9.3, calc T7: the smoke's own ledger (elucid only)
PROBE_CAP = 500_000  # §10 S1: the probe's own ledger root
CAP_FACTOR = Fraction(3, 2)  # §9.3: S-E6 admits a ledger/actual ratio up to 1.5
# §9.3 owner #9 (NOT taken; recommended pilot only): with P_i on ALFWorld acceptance these would replace the above.
OPTION_PI_ALFWORLD = {"accept": 107_500_000, "redo_reserve": 26_900_000, "solver_cap": 320 * MILLION}
NOISE_REREGISTER = Fraction(5, 4)  # §3.3, §10 S-N1/S-E6: measured > 1.25 x the assumption -> re-register before pilot

# ---------------------------------------------- the main configuration's caps (registrar 17:0x / 17:3x, "Caps" row)
# "Every cap of the main configuration is set to at least 3 x its computed maximum need" (cost no concern). The
# maximum schedule of main's five steps, in cells as MAX_SCHEDULE_CELLS: calc T4's ``step_cost`` (the registered
# maximum-schedule function, A* 100 %, 2 twins per A* cell, 3 band rounds, 2 self-test passes) applied to main's
# steps -- SearchQA step 1 (run 300 x 1, accept 1,000 x 1, first step, no P_i, no generator, no S_dup), OfficeQA step 2
# (24 x 2 / 50 x 4, P_i, G_acc 50, S_dup; no earlier generated set), LiveMath step 3 (119 x 1 / 100 x 2, P_i, G_acc 100,
# S_dup; OfficeQA's set) with §6.4 J7's options-only probe added to its acceptance (64 items, S' and C once each),
# SpreadsheetBench step 4 (31 x 2 / 60 x 2, P_i, G_acc 60, S_dup; the OfficeQA and LiveMath sets) and ALFWorld step 5
# (60 x 1 / 150 x 1, no P_i, no G_acc; the OfficeQA, LiveMath and SpreadsheetBench sets). SearchQA's examiner and
# self-test rows are the function's band, shortcut and G_self cells although SearchQA generates nothing: kept, as a
# conservative bound (tests/test_execskill_protocol.py recomputes every row from the calc).
MAIN_SCHEDULE_CELLS = {
    "searchqa": {"run": {"searchqa": (0, 300)}, "examiner": {"searchqa": (150, 0)},
                 "selftest": {"searchqa": (120, 120)}, "accept": {"searchqa": (2_000, 4_000)}},
    "officeqa": {"run": {"officeqa": (0, 96)}, "examiner": {"officeqa": (110, 290)},
                 "selftest": {"officeqa": (0, 240)}, "accept": {"officeqa": (200, 1_400)}},
    "livemath": {"run": {"livemath": (0, 238)}, "examiner": {"livemath": (160, 490)},
                 "selftest": {"officeqa": (0, 160), "livemath": (0, 240)}, "accept": {"livemath": (264, 1_464)}},
    "spreadsheetbench": {"run": {"spreadsheetbench": (0, 124)}, "examiner": {"spreadsheetbench": (120, 330)},
                         "selftest": {"officeqa": (0, 160), "livemath": (0, 160), "spreadsheetbench": (0, 240)},
                         "accept": {"spreadsheetbench": (120, 840)}},
    "alfworld": {"run": {"alfworld": (0, 120)}, "examiner": {"alfworld": (0, 90)},
                 "selftest": {"officeqa": (0, 160), "livemath": (0, 160), "spreadsheetbench": (0, 160),
                              "alfworld": (0, 160)}, "accept": {"alfworld": (150, 750)}},
}
# The computed maximum need of a scope = its maximum-schedule cells at the §9.1 high anchors (card x1, procedure x1.6)
# + MAIN_RESERVATIONS full chain-G reservations at once (4 x (request bytes + 512 + 65,536), calc T6's request bytes:
# QA and SpreadsheetBench 64,000 -> 520,192, ALFWorld 32,000 -> 392,192; the dearest bench of the scope's cells): 16
# workers (``units.Setting.workers``) may hold their reservations together. Chain D's B never exceeds 65,536, so the
# same caps serve both chains. Cap = 3 x need, rounded up to 0.1M. E.g. SearchQA accept: 2,000 x 3,400 + 4,000 x 3,400
# x 1.6 + 16 x 520,192 = 36,883,072 -> 110.7M; ALFWorld accept: 150 x 45,000 + 750 x 45,000 x 1.6 + 16 x 392,192 =
# 67,025,072 -> 201.1M (the needs of all twenty scopes are in tests/test_execskill_protocol.py and notes/M-M1.md).
MAIN_RESERVATIONS = 16
MAIN_CAP_FACTOR = 3
MAIN_STEP_CAPS = {
    "searchqa": {"run": 29_900_000, "examiner": 26_500_000, "selftest": 28_200_000, "accept": 110_700_000},
    "officeqa": {"run": 28_700_000, "examiner": 38_700_000, "selftest": 34_200_000, "accept": 83_000_000},
    "livemath": {"run": 29_600_000, "examiner": 36_300_000, "selftest": 35_700_000, "accept": 56_100_000},
    "spreadsheetbench": {"run": 27_600_000, "examiner": 33_300_000, "selftest": 39_100_000, "accept": 43_800_000},
    "alfworld": {"run": 44_800_000, "examiner": 38_300_000, "selftest": 72_000_000, "accept": 201_100_000},
}
# main's other caps (PILOTS["main"]), the same rule:
# - redo reserve 72.0M = 3 x the dearest single redo: ALFWorld's whole self-test, 23,982,336 (an acceptance redo is one
#   block: SearchQA's 15.46M, ALFWorld's 21.46M); each attempt sub-scope is min(kind cap, redo reserve) >= 3 x its redo;
# - test read 407M = 3 x (93,975,624 = the maximum read, TEST_READ_CELLS["main"] at the high anchors, + 5 read units x
#   16 reservations x 520,192 = 41,615,360) = 406,772,952, rounded up to 1M; the 1.3 x estimate start rule at the high
#   anchors needs 100.5M (chain G: x its measured cost factor, ``chain.read_budget``);
# - solver 1,520M = the twenty step caps 1,037.6M + test read 407M + redo reserve 72M = 1,516.6M, rounded up to 5M
#   (>= 3 x the summed needs of the steps, the test read and one redo: 3 x 505.05M = 1,515.15M);
# - GLM: the owner's per-step role scopes engineer 5M, examiner 5M, examiner research 9.2M (19.2M per step) bound the
#   method roles' spend, so their maximum need over the five steps is 96M and ``<c>:glm`` is 3 x 96M = 288M;
# - overall = solver + GLM = 1,808M per chain (``budgets.chain_caps``).
MAIN_ROLE_CAPS = {"engineer": 5_000_000, "examiner": 5_000_000, "examiner_research": 9_200_000}
MAIN_GLM_CAP = 288 * MILLION

# -------------------------------------------------------------------------- sandbox and slots (§2.6, §4.4; plan §4)
SANDBOX_SLOTS = {"execskill-sandbox-live": 6, "execskill-sandbox": 4}  # live (O12); per call: start value until S0
LIVE_SANDBOX_UNIT_CAP = {"spreadsheetbench": 2}  # §2.6: live sandboxes of one SpreadsheetBench unit
NATIVE_SLOTS_LOW_MEMORY = 2  # plan §5: native 3 -> 2 when the S0 native peak RSS exceeds 2 GiB
SANDBOX_TIMEOUTS = {"predicate": 2, "hook": 5, "detector": 5, "generator": 60}  # §2.6: wall seconds per request
SANDBOX_READY_SECONDS = 20  # plan §4: the first ping
CLEANUP_SECONDS = 10  # plan §4: the docker rm --force bound
SHORT_HOLD_SECONDS = 600  # §4.4 P4: the per-call sandbox slot, logged and retried once
WAIT_LOG_SECONDS = 300  # plan §4: every other slot waits untimed, with a log line this often

# ---------------------------------------------------------------------------------------------------- smoke (§10)
S1_MAX_CALLS = 60
S1B_TOKENS = (16, 64, 256)  # ten long-output requests each
S1B_REPEATS = 10
S1C_TOKENS = 16_384
S1_CONCURRENCY = 8
PROMPT_OVERHEAD_MAX = 512  # prompt tokens - request bytes
SMOKE_FORMAT_FLOOR = Fraction(9, 10)  # per bench and arm (coevo5 smoke.py:69-77)
SMOKE_FORMAT_MARGIN = Fraction(1, 20)  # X and P no lower than C by more than 1/20
MIN_PRODUCTION_RECEIPTS = 300  # Codex F19: registered body and registered M and B, zero reasoning leaks

# ---------------------------------------------------------------------------------------------- places (§1, §10)
BUILD_TREE = "/data/execskill-dev"
SNAPSHOT_ROOT = "/data/execskill-20261021-source-e"  # v2 (owner decision 2026-10-23 13:3x): snapshot e, the smoke
# with v2's example SX; snapshot d (/data/execskill-20261021-source-d, registrar addendum 10/23 05:3x: the chain-G
# re-smoke with the research User-Agent and the owner smoke waiver, and the v1 main) stays untouched; snapshot c (/data/execskill-20261021-source-c, the chain-G smoke of
# addendum 10/23 02:3x) and snapshot b (/data/execskill-20261021-source-b, after the S0 supply-row fix of 10/22 22:1x)
# stay untouched as the chain-G and elucid smoke attempts' records, snapshot a (/data/execskill-20261021-source) as
# the failed S0 attempt's
OPS_ROOT = "/data/execskill-20261021-ops"
PRE_ROOT = "/data/execskill-20261021-pre"
SMOKE_ROOT = PRE_ROOT + "/smoke"  # §10: the smoke's run root, its own ledger
PROBE_ROOT = PRE_ROOT + "/probe"  # §9.3, §10 S1: the probe's own ledger root ...
PROBE_LEDGER = PROBE_ROOT + "/ledger"  # ... whose budget.Budget directory is this (plan §10 step 4)
PILOT_ROOT = "/data/execskill-20261021-pilot"
PILOT_MANIFEST = "/data/execskill-20261021-pilot-manifest.json"
# registrar 17:0x / 17:3x: the main experiment's run root (the owner writes shared/consent.json there) and manifest
MAIN_ROOT = "/data/execskill-20261022-main"
MAIN_MANIFEST = "/data/execskill-20261022-main-manifest.json"
HISTORY_ROOT = "/data/execskill-history"  # §3.4: consumption registry and supply files, independent of any run root
SLOT_ROOT = "/data/execskill-slots"  # owner #10: machine-wide slot locks of every route-B process
NEVER_WRITTEN = ("/data/execskill-ops", "/data/skillopt-work")  # another probe's root; not a git repo, holds a .env
INTERPRETER = "/root/continual-alf-prep-20260928/env/bin/python"  # run with -B and PYTHONDONTWRITEBYTECODE=1

# ------------------------------------------------- run configurations: what each consumer looks up (registrar 17:0x)
# Per configuration (``CONFIGURATIONS``): the step caps and the maximum schedule they derive from, the per-step role
# caps and the chain's GLM cap (§9.3; main: the owner's 17:0x caps), the factor every cap carries over its maximum
# need (§9.3 1.5; main 3, which ``step.cost_projection`` divides by), whether chain G's cost check after its first run
# unit pauses (§9.3; main: it records its factor and never pauses -- the read gate still applies the factor,
# ``chain.read_budget``), the evidence label of a real run and the run root.
# ------------------------------------------- v2 "train then accept" (owner decision 2026-10-23 13:3x; spec-v2.md)
# The owner, after chain G's v1 main ended all five steps ``no_surviving_change``: "好的，那就按照你的建议来修改". The
# run configuration ``main-v2`` is ``main`` with the learning mode ``train``: per step a training loop of at most
# TRAIN_ROUNDS rounds replaces the v1 engineer / engineer-2 / selftest-2 path -- the engineer revises the incumbent
# package from the previous round's training evaluation (which training items each changed procedure fixed or broke,
# with its notes), up to TRAIN_FIXES fix calls per failing change, C7 replay tests advisory, the description cut to
# MAX_DESCRIPTION_CHARS; each candidate is evaluated paired against the incumbent on the run-slice items whose routing
# differs (and on G_self), fresh, and adopted when it fixes more training items than it breaks by at least
# max(1, ceil(TRAIN_ADOPT_SHARE x evaluated)). The last incumbent, if it differs from the parent, takes the v1
# self-test and the unchanged acceptance. Training cells are self-training: they are charged to the step's
# ``...:selftest`` scope, whose main-v2 cap adds their maximum schedule.
MAIN_V2 = "main-v2"
LEARNING = {"default": "single", "recommended": "single", "main": "single", MAIN_V2: "train"}
TRAIN_ROUNDS = 6
TRAIN_PATIENCE = 2  # consecutive rounds without an adopted candidate end the loop
TRAIN_FIXES = 3  # fix calls per failing change (v1: one)
TRAIN_ENGINEER_CALLS = 10  # engineer calls per engineer-r<r> unit
TRAIN_ADOPT_SHARE = Fraction(1, 50)
TRAIN_ALPHA = Fraction(1, 4)  # and fixed vs broken items: the one-sided exact sign test p <= 1/4
TRAIN_FORMAT_MARGIN = (2, Fraction(1, 50))  # S' format-violating cells above S's by more than max(2, 2 %) block
TRAIN_EXAMPLES = 3  # fixed and broken examples per changed procedure in the feedback
TRAIN_TEXT_CHARS = {"question": 400, "note": 700, "answer": 240}  # feedback excerpts (references whole)
GENERATING = ("officeqa", "livemath", "spreadsheetbench")  # benches with registered generator families (§7.2)
TOPUP_ROUNDS = 2  # v2: further generator calls while G_self holds fewer than BAND_PROBE_ITEMS items (before the band)
# v2, SkillOpt's multi-round feedback (owner suggestion 2026-10-23 15:1x, "可以参考一下skillopt那种多轮反馈的"): before
# each round's proposal the engineer role analyses the incumbent's failed run-slice items in groups, as SkillOpt's
# minibatch reflection does (skillopt/gradient/reflect.py): TRAIN_ANALYST_BATCH items per call, at most
# TRAIN_ANALYST_CALLS calls per engineer-r unit, items no earlier round of the step analysed first, each reply at most
# TRAIN_FINDINGS findings with texts of at most TRAIN_FINDING_CHARS characters; and the history shows every earlier
# proposal's kind, target, description excerpt (TRAIN_PROPOSAL_CHARS) and fate, as SkillOpt's step buffer does.
TRAIN_ANALYST_BATCH = 6
TRAIN_ANALYST_CALLS = 4
TRAIN_FINDINGS = 3
TRAIN_FINDING_CHARS = 300
TRAIN_PROPOSAL_CHARS = 200
ANALYST_TAG = "execskill-v2:analyst"  # + ":<unit label>": the seeded order of the failed cells the analysts see
# the training cells of one step at the maximum schedule: every round, both arms, every run-slice cell and G_self
TRAIN_CELLS = {bench: TRAIN_ROUNDS * 2 * (SLICES[bench]["run"][0] * SLICES[bench]["run"][1]
                                          + (G_SELF_MAX if bench in GENERATING else 0)) for bench in BENCHES}


def _round_up(value, step):
    return int(math.ceil(Fraction(value) / step) * step)


MAIN_V2_SCHEDULE_CELLS = {bench: {kind: dict(rows) for kind, rows in kinds.items()}
                          for bench, kinds in MAIN_SCHEDULE_CELLS.items()}
for _bench in BENCHES:  # the training cells are procedure cells of the step's own bench in its self-test row
    _card, _proc = MAIN_V2_SCHEDULE_CELLS[_bench]["selftest"].get(_bench, (0, 0))
    MAIN_V2_SCHEDULE_CELLS[_bench]["selftest"][_bench] = (_card, _proc + TRAIN_CELLS[_bench])
# the self-test cap grows by MAIN_CAP_FACTOR x the training cells at the bench's high procedure anchor, to 0.1M
MAIN_V2_STEP_CAPS = {bench: {**caps, "selftest": caps["selftest"] + _round_up(
    MAIN_CAP_FACTOR * TRAIN_CELLS[bench] * CELL_ANCHORS[bench][1] * PROCEDURE_ARM_FACTOR[1], 100_000)}
    for bench, caps in MAIN_STEP_CAPS.items()}
# engineer 20M per step (TRAIN_ROUNDS engineer units of at most TRAIN_ENGINEER_CALLS calls, the leakage adjudications
# and the describer), examiner 10M (the TOPUP_ROUNDS further generator calls); GLM = 3 x the five steps' role ceilings
MAIN_V2_ROLE_CAPS = {"engineer": 20 * MILLION, "examiner": 10 * MILLION, "examiner_research": 9_200_000}
MAIN_V2_GLM_CAP = MAIN_CAP_FACTOR * len(BENCHES) * sum(MAIN_V2_ROLE_CAPS.values())
MAIN_V2_ROOT = "/data/execskill-20261023-main-v2"
MAIN_V2_MANIFEST = "/data/execskill-20261023-main-v2-manifest.json"
PILOTS[MAIN_V2] = {"order": BENCHES, "redo_reserve": PILOTS["main"]["redo_reserve"]}
# v2 stage reads (owner decision 2026-10-23 16:0x: "我说的主实验是指在五个bench上逐个进化，并且每个进化之后都在所有的五个bench
# 上评测的意思"): the test read of a stage-read configuration -- still one read per chain, at its end, one unit per bench
# -- also runs the package every step passed on, on all five test sets: one stage arm "S<k>" per package that step k
# passed on, that holds a procedure, is not F and was not passed on by an earlier step, in the same seeded interleaved
# order as F, C, P_F, T_F and the twins. Row k of the stage table (k = 0 .. the order's length) reads C where the
# package after step k holds no procedure, F where it is F, else the stage arm of the first step that passed it on.
# A stage cell sends nothing where its enabled procedures -- ids and byte-identical procedures, in order -- are those
# of a cell the unit runs (none: C's; F's; an earlier stage arm's): the solver request is then the same, so the rows
# differ only on the items whose enabled procedures differ (``evaluation.stage_plan``).
STAGE_READ = {"default": False, "recommended": False, "main": False, MAIN_V2: True}
STAGE_ARM = "S"  # + the step position k: "S1" .. "S4" (step 5's package is F)
STAGES = "stages"  # the name the owner's read consent gives the stage arms (``read_arms_of``)


def stage_arms_max(configuration):
    """The most stage arms a read of ``configuration`` runs: one per step before the last (whose package is F)."""
    require(configuration in STAGE_READ, "Unknown run configuration")
    return len(CONFIGURATIONS[configuration]["order"]) - 1 if STAGE_READ[configuration] else 0


def read_arms_of(configuration):
    """The arms the owner's read consent names for ``configuration`` (``multi_arm_arms``): ``TEST_ARMS``, with
    ``STAGES`` in a stage-read configuration. Named without a ``test_`` prefix, so pytest never collects it."""
    if configuration in ('baseline-v210', 'main-v3'):
        return ('C', 'B') if configuration == 'baseline-v210' else ('F', 'C', 'B')
    require(configuration in STAGE_READ, "Unknown run configuration")
    return TEST_ARMS + ((STAGES,) if STAGE_READ[configuration] else ())


def estimate_arms(pilot):
    """The procedure arms per fired test item the read estimate prices (``read_estimate_terms``):
    ``TEST_READ_ESTIMATE_ARMS`` plus every stage arm (``stage_arms_max``) at a full procedure cell, though a stage cell
    sends nothing where its procedures are another cell's."""
    return TEST_READ_ESTIMATE_ARMS + stage_arms_max(pilot)


# main-v2's read cells: main's (every bench home, f = 1) plus the stage arms' procedure cells on every test item; its
# test-read cap by main's rule (3 x (the maximum read at the high anchors + 5 read units x MAIN_RESERVATIONS x the
# dearest full reservation, calc T6's 4 x (64,000 + 512 + 65,536) = 520,192), rounded up to 1M) and its solver cap
# (the twenty step caps + the test read + the redo reserve, rounded up to 5M)
TEST_READ_CELLS[MAIN_V2] = {bench: (n, proc + stage_arms_max(MAIN_V2) * n)
                            for bench, (n, proc) in TEST_READ_CELLS["main"].items()}
READ_RESERVATION = 520_192
MAIN_V2_READ_TOKENS = sum(CELL_ANCHORS[b][1] * (card + PROCEDURE_ARM_FACTOR[1] * proc)
                          for b, (card, proc) in TEST_READ_CELLS[MAIN_V2].items())
PILOTS[MAIN_V2]["test_read_cap"] = _round_up(MAIN_CAP_FACTOR * (MAIN_V2_READ_TOKENS + len(BENCHES) * MAIN_RESERVATIONS
                                                                * READ_RESERVATION), MILLION)
PILOTS[MAIN_V2]["solver_cap"] = _round_up(sum(sum(c.values()) for c in MAIN_V2_STEP_CAPS.values())
                                          + PILOTS[MAIN_V2]["test_read_cap"] + PILOTS[MAIN_V2]["redo_reserve"],
                                          5 * MILLION)
# The smoke's example stage SX (owner 2026-10-23 13:3x: "最好真正的跑通了一个示例再开始正式实验"): the v2 step of SearchQA
# with real GLM-5.3 roles on the smoke's own SearchQA items that its trimmed stages leave unused (S-N1's 200 and S4's
# 60, after S2's 20): run 100, acceptance 160. It runs after S-E6, on raised smoke caps (``SMOKE_SX_CAPS``).
SX_SLICES = {"run": 100, "accept": 160}
SMOKE_SX_CAPS = {"solver": 80 * MILLION, "glm": 40 * MILLION}
SMOKE_WAIVER_V2 = "shared/owner-smoke-waiver-v2.json"  # a v2 smoke's (SX listed) owner waiver; v1's file stays put
# ------------------------------------------- v2.1 (owner decision 2026-10-24 02:2x: "好的，那就按照你的说法来，先修，修好之后继续跑")
# main-v2 stopped on 2026-10-23/24: chain D on the httpcore tunnel-pool leak (``client.POOL_LIMITS``, every
# configuration), chain G on a model-written replay test whose mutation was an object (``replay.validate_test`` now
# refuses any value of the wrong type, every configuration), and LiveMath's round 2 had adopted a procedure keyed on
# the meta option after its fix calls echoed the screen's matched phrase and the adjudicator's reason. The run
# configuration ``main-v2-1`` is ``main-v2`` with two engineer rules: its fix calls never show a flagged text, a
# matched term, a static ban's detail or the adjudicator's reason -- the sealed records keep them (``FIX_ECHO``,
# ``engineer._redacted``) -- and C4 replays every procedure on its in-scope LiveMath trajectories whose view holds the
# meta option with that option's text replaced by ``META_FILLER``: a procedure that behaves differently there --
# predicate, notes, bindings, repair request or fault kinds, the filler mapped back -- fails C4
# (``META_COUNTERFACTUAL``, ``replay.meta_counterfactual``). Prompts, slices, caps and every other rule are main-v2's;
# its run root and consumption namespaces (``V21_NAMESPACES``) are new.
MAIN_V2_1 = "main-v2-1"
LEARNING[MAIN_V2_1] = "train"
FIX_ECHO = {"default": True, "recommended": True, "main": True, MAIN_V2: True, MAIN_V2_1: False}
META_COUNTERFACTUAL = {"default": False, "recommended": False, "main": False, MAIN_V2: False, MAIN_V2_1: True}
META_FILLER = "This option's wording is withheld and replaced by this neutral sentence."
MAIN_V2_1_ROOT = "/data/execskill-20261024-main-v2-1"
MAIN_V2_1_MANIFEST = "/data/execskill-20261024-main-v2-1-manifest.json"
PILOTS[MAIN_V2_1] = dict(PILOTS[MAIN_V2])
STAGE_READ[MAIN_V2_1] = STAGE_READ[MAIN_V2]
TEST_READ_CELLS[MAIN_V2_1] = dict(TEST_READ_CELLS[MAIN_V2])
CHAIN_NAMESPACES = {MAIN_V2: V2_NAMESPACES, MAIN_V2_1: V21_NAMESPACES}
# ------------- v2.2 (owner decision 2026-10-24 12:1x: "你的门槛设的太高了，请你根据具体的进化情况重新设计一下门槛怎么样才合适，
# 我觉得acc变化五个点以上都可以算是有效果，不用要求那么高"; the owner then chose the proposed gates, the stop of main-v2-1
# once main-v2-2 is ready and a delegated test-read consent)
# main-v2-1's gates let 3 of 12 training candidates through and decided no acceptance: chain G's LiveMath candidate
# fired on 12 acceptance items (< MIN_ASTAR), chain D's gained 9.9 points over S on A* but 1.1 over the yoked sham
# (J2), and the registered MDE (``MDE_POINTS``) is the joint power of J1 and J2, about 10 points. The run
# configuration ``main-v2-2`` is ``main-v2-1`` with the owner's practical gates:
# - training (``TRAIN_SIGN``): fixed > broken and net >= max(1, ceil(2 %)) adopt; the sign test is recorded only;
# - a candidate's new procedure that no evaluated training item enables is pruned before the training cells
#   (``PRUNE_NON_FIRING``, ``step.prune_idle``), so it cannot ride along with one that fires (main-v2-1's chain D
#   adopted a meta-option detector that fired on no item beside a procedure that did);
# - acceptance (``ACCEPT_RULES``, sealed into the round by ``acceptance.prepare`` and read by ``acceptance.decide``):
#   S' is accepted when its whole-batch gain over S is >= 5 points, or on SearchQA (1,000 items) >= 2 points with the
#   one-sided p <= 0.05; P_y and P_i run and are reported, the decision labelling the gain "content" when S' - P_y is
#   >= 5 points, else "form", and never deciding; J3, J4, J5, J6 and J7 are unchanged; |A*| must reach
#   min(30, max(ceil(5 % of |A|), blocks + 2)) items (ALFWorld also min(20, blocks + 2) rooms), below which no
#   procedure set could reach 5 points or the blocked t-test could not be formed (``acceptance.minimum_astar``).
# The gates were chosen after reading main-v2-1's step-3 acceptance, and main-v2-2 cuts the same slices (its pools hold
# no other supply), so its acceptance rounds reuse items main-v2-1 dispatched (chain D's LiveMath acceptance and probe
# items at least); its method side sees none of main-v2-1's records. Its acceptance decisions are selection evidence
# labelled ``ACCEPT_FRESHNESS``; the method effect is read on the untouched test split only. Slices, prompts, caps
# and every other rule are main-v2-1's; its run root and consumption namespaces (``V22_NAMESPACES``) are new.
MAIN_V2_2 = "main-v2-2"
LEARNING[MAIN_V2_2] = "train"
FIX_ECHO[MAIN_V2_2] = False
META_COUNTERFACTUAL[MAIN_V2_2] = True
TRAIN_SIGN = {"default": True, "recommended": True, "main": True, MAIN_V2: True, MAIN_V2_1: True, MAIN_V2_2: False}
PRUNE_NON_FIRING = {"default": False, "recommended": False, "main": False, MAIN_V2: False, MAIN_V2_1: False,
                    MAIN_V2_2: True}
PRACTICAL_RULE = {"name": "practical-v2-2", "gain_points": 5, "significance_benches": ["searchqa"],
                  "significance_points": 2, "alpha": ALPHA, "content_points": 5, "astar_share_percent": 5,
                  "astar_cap": MIN_ASTAR, "rooms_cap": MIN_ASTAR_ROOMS, "blocks_extra": 2}
ACCEPT_RULES = {"default": None, "recommended": None, "main": None, MAIN_V2: None, MAIN_V2_1: None,
                MAIN_V2_2: PRACTICAL_RULE}
ACCEPT_FRESHNESS = {MAIN_V2_2: "route_b_v2_1_slices_reused"}  # every other configuration: ``step.FRESHNESS``
MAIN_V2_2_ROOT = "/data/execskill-20261024-main-v2-2"
MAIN_V2_2_MANIFEST = "/data/execskill-20261024-main-v2-2-manifest.json"
PILOTS[MAIN_V2_2] = dict(PILOTS[MAIN_V2])
STAGE_READ[MAIN_V2_2] = STAGE_READ[MAIN_V2]
TEST_READ_CELLS[MAIN_V2_2] = dict(TEST_READ_CELLS[MAIN_V2])
CHAIN_NAMESPACES[MAIN_V2_2] = V22_NAMESPACES


# v2.3 (owner 2026-10-24 21:5x; REQUEST-v23.md): repair engineer delivery and structure, widen only
# pure module constants, version the sheet extractor, and seal zero-call request reuse before paired dispatch.
# The fixed cut is reused again; acceptance is selection evidence, not independent method-effect evidence.
MAIN_V2_3 = "main-v2-3"
MAIN_V2_3_ROOT = "/data/execskill-20261025-main-v2-3"
MAIN_V2_3_MANIFEST = "/data/execskill-20261025-main-v2-3-manifest.json"
for _table in (PILOTS, STAGE_READ, TEST_READ_CELLS, LEARNING, FIX_ECHO, META_COUNTERFACTUAL,
               TRAIN_SIGN, PRUNE_NON_FIRING, ACCEPT_RULES):
    _table[MAIN_V2_3] = _table[MAIN_V2_2].copy() if isinstance(_table[MAIN_V2_2], dict) else _table[MAIN_V2_2]
CHAIN_NAMESPACES[MAIN_V2_3] = V23_NAMESPACES
ACCEPT_FRESHNESS[MAIN_V2_3] = "route_b_v2_2_slices_reused"
ENGINEER_MAX_TOKENS = {name: 32_768 if name == MAIN_V2_3 else ROLE_MAX_TOKENS for name in CONFIGURATIONS}
TRIM_CHARS = 6_000
TRIM_PAYLOADS = {name: name == MAIN_V2_3 for name in CONFIGURATIONS}
NORMALIZE_STRUCTURE = dict(TRIM_PAYLOADS)
CHECK_NON_FIRING = dict(TRIM_PAYLOADS)  # Amendment 2: repairable C6b on the round's training routing views
ENGINEER_RECORDS = {name: "engineer-v2-3-a2" if name == MAIN_V2_3 else "engineer" for name in CONFIGURATIONS}
IDENTICAL_REQUEST_REUSE = dict(TRIM_PAYLOADS)
POLICY_VERSIONS = {name: "fivebench-execskill-v2-3-policy" if name == MAIN_V2_3
                   else "fivebench-execskill-v1-policy" for name in CONFIGURATIONS}
CODE_EXTRACTION = {name: "explicit-python-fences-v2" if name == MAIN_V2_3
                   else "explicit-python-fences-v1" for name in CONFIGURATIONS}
MULTIPLE_PYTHON_BLOCKS = {name: "refuse" for name in CONFIGURATIONS}  # owner must choose before launch

def namespace_of(setting, chain):
    """The consumption namespace of ``chain`` in the Setting's run configuration: the chain itself, or its own
    namespace in main-v2 (``V2_NAMESPACES``), main-v2-1 (``V21_NAMESPACES``) and main-v2-2 (``V22_NAMESPACES``)."""
    found = CHAIN_NAMESPACES.get(configuration_of(setting))
    return found[chain] if found is not None else chain

CONFIG_STEP_CAPS = {"default": STEP_CAPS, "recommended": STEP_CAPS, "main": MAIN_STEP_CAPS, MAIN_V2: MAIN_V2_STEP_CAPS,
                    MAIN_V2_1: MAIN_V2_STEP_CAPS, MAIN_V2_2: MAIN_V2_STEP_CAPS}
CONFIG_SCHEDULE_CELLS = {"default": MAX_SCHEDULE_CELLS, "recommended": MAX_SCHEDULE_CELLS, "main": MAIN_SCHEDULE_CELLS,
                         MAIN_V2: MAIN_V2_SCHEDULE_CELLS, MAIN_V2_1: MAIN_V2_SCHEDULE_CELLS,
                         MAIN_V2_2: MAIN_V2_SCHEDULE_CELLS}
CONFIG_ROLE_CAPS = {"default": ROLE_CAPS, "recommended": ROLE_CAPS, "main": MAIN_ROLE_CAPS, MAIN_V2: MAIN_V2_ROLE_CAPS,
                    MAIN_V2_1: MAIN_V2_ROLE_CAPS, MAIN_V2_2: MAIN_V2_ROLE_CAPS}
CONFIG_GLM_CAP = {"default": GLM_CAP, "recommended": GLM_CAP, "main": MAIN_GLM_CAP, MAIN_V2: MAIN_V2_GLM_CAP,
                  MAIN_V2_1: MAIN_V2_GLM_CAP, MAIN_V2_2: MAIN_V2_GLM_CAP}
CONFIG_CAP_FACTOR = {"default": Fraction(3, 2), "recommended": Fraction(3, 2), "main": Fraction(MAIN_CAP_FACTOR),
                     MAIN_V2: Fraction(MAIN_CAP_FACTOR), MAIN_V2_1: Fraction(MAIN_CAP_FACTOR),
                     MAIN_V2_2: Fraction(MAIN_CAP_FACTOR)}
COST_CHECK_PAUSES = {"default": True, "recommended": True, "main": False, MAIN_V2: False, MAIN_V2_1: False,
                     MAIN_V2_2: False}
REAL_RUN_EVIDENCE = {"default": "pilot_real_run", "recommended": "pilot_real_run", "main": "main_real_run",
                     MAIN_V2: "main_v2_real_run", MAIN_V2_1: "main_v2_1_real_run", MAIN_V2_2: "main_v2_2_real_run"}
RUN_ROOTS = {"default": PILOT_ROOT, "recommended": PILOT_ROOT, "main": MAIN_ROOT, MAIN_V2: MAIN_V2_ROOT,
             MAIN_V2_1: MAIN_V2_1_ROOT, MAIN_V2_2: MAIN_V2_2_ROOT}


for _table in (CONFIG_STEP_CAPS, CONFIG_SCHEDULE_CELLS, CONFIG_ROLE_CAPS, CONFIG_GLM_CAP, CONFIG_CAP_FACTOR,
               COST_CHECK_PAUSES):
    _table[MAIN_V2_3] = _table[MAIN_V2_2]
REAL_RUN_EVIDENCE[MAIN_V2_3] = "main_v2_3_real_run"
RUN_ROOTS[MAIN_V2_3] = MAIN_V2_3_ROOT


def configuration_of(setting):
    """The run configuration a chain process follows: ``setting.extra["configuration"]``, which ``manifest.setting_of``
    sets from the verified manifest's ``configuration`` field; a fixture Setting without one is the default ``PILOT``."""
    found = (getattr(setting, "extra", None) or {}).get("configuration", PILOT)
    require(found in CONFIGURATIONS, "Unknown run configuration: %r" % (found,))
    return found


def learning_of(setting):
    """The learning mode of the Setting's run configuration (``LEARNING``): "single" (v1) or "train" (v2)."""
    return LEARNING[configuration_of(setting)]


def order_of(setting):
    """The step order of the Setting's run configuration (``configuration_of``): its benches, step 1 first."""
    return CONFIGURATIONS[configuration_of(setting)]["order"]


# ------------------------------------------------------------------------------------- hashes bound in the manifest
# The lexicon's one hash (plan §2.9 ``lexicon_sha``) is ``notes.lexicon_sha256()``: it covers LEXICON and
# LEXICON_MATCH above together with what the screen applies besides them (headers, field types, caps, the LiveMath
# meta-option terms), so this module defines no second lexicon hash.
PLACEBO_CORPUS_SHA256 = digest(list(PLACEBO_CORPUS))
TEMPLATES_SHA256 = {name: digest(text) for name, text in TEMPLATES.items()}
