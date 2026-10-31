"""Explicit experiment extensions; frozen five-benchmark protocol tables remain readable unchanged.

Production consumers use this registry. ``protocol`` remains the historical registration,
including its iterable rosters (and therefore its historical identity serialization).
"""
from __future__ import annotations

from copy import deepcopy

from .protocol import *  # re-export the historical vocabulary, without mutating its tables
from . import protocol as legacy
from .policy import POLICY_VERSION_V24, POLICY_VERSION_V25, POLICY_VERSION_V28, POLICY_VERSION_V29, MAX_SOURCE_BYTES_V28, MAX_SOURCE_BYTES_V29

MAIN_V4 = "main-v4"
MAIN_V5 = "main-v5"
ZEBRA_PC_V1 = "zebra-pc-v1"
ZEBRA_PC_V2 = "zebra-pc-v2"
ZEBRA_PC_V3 = "zebra-pc-v3"
ZEBRA_PC_V4 = "zebra-pc-v4"
ZEBRA_PC_V5 = "zebra-pc-v5"
ZEBRA_PC_V6 = "zebra-pc-v6"
ZEBRA_PC_V7 = "zebra-pc-v7"
ZEBRA_PC_V8 = "zebra-pc-v8"
ZEBRA_PC_V9 = "zebra-pc-v9"
ZEBRA_PC_V10 = "zebra-pc-v10"
ZEBRA_PC_V11 = "zebra-pc-v11"
ZEBRA_PC_V12 = "zebra-pc-v12"
ZEBRA_PC_V13 = "zebra-pc-v13"
ZEBRA_PC_V14 = "zebra-pc-v14"
ZEBRA_PC_V15 = "zebra-pc-v15"
ZEBRA_HP_V3R4 = "zebra-hp-v3r4"
ALFWORLD_V1 = "alfworld-v1"
ALFWORLD_V2 = "alfworld-v2"
ALFWORLD_V3 = "alfworld-v3"
ALFWORLD_V4 = "alfworld-v4"
ALFWORLD_V5 = "alfworld-v5"
ALFWORLD_V6 = "alfworld-v6"
ALFWORLD_V7 = "alfworld-v7"
ALFWORLD_V8 = "alfworld-v8"
ALFWORLD_V9 = "alfworld-v9"
ALFWORLD_V10 = "alfworld-v10"
ALFWORLD_V11 = "alfworld-v11"
ZEBRA = "zebralogic"
SUPPORTED_BENCHES = BENCHES + (ZEBRA,)
FEATURE_FAMILIES = {name: ("v2.3" if name == MAIN_V2_3 else "historical") for name in CONFIGURATIONS}
FEATURE_FAMILIES[ZEBRA_PC_V1] = "v2.3"
FEATURE_FAMILIES[ZEBRA_PC_V2] = "v2.4"
FEATURE_FAMILIES[ZEBRA_PC_V3] = "v2.5"
FEATURE_FAMILIES[ZEBRA_PC_V4] = "v2.6"
FEATURE_FAMILIES[ALFWORLD_V1] = "v2.6"
FEATURE_FAMILIES[ZEBRA_PC_V5] = "v2.7"
FEATURE_FAMILIES[ALFWORLD_V2] = "v2.7"
FEATURE_FAMILIES[ZEBRA_PC_V6] = "v2.8"
FEATURE_FAMILIES[ALFWORLD_V3] = "v2.8"
FEATURE_FAMILIES[ZEBRA_PC_V7] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V4] = "v2.9"
FEATURE_FAMILIES[ZEBRA_PC_V8] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V5] = "v2.9"
FEATURE_FAMILIES[ZEBRA_PC_V9] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V6] = "v2.9"
FEATURE_FAMILIES[ZEBRA_PC_V10] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V7] = "v2.9"
FEATURE_FAMILIES[ZEBRA_PC_V11] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V8] = "v2.9"
FEATURE_FAMILIES[ZEBRA_PC_V12] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V9] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V10] = "v2.9"
FEATURE_FAMILIES[ALFWORLD_V11] = "v2.9"


def is_v23(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.3", "v2.4", "v2.5", "v2.6", "v2.7", "v2.8", "v2.9")


def is_v24(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.4", "v2.5", "v2.6", "v2.7", "v2.8", "v2.9")


def is_v25(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.5", "v2.6", "v2.7", "v2.8", "v2.9")


def is_v26(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.6", "v2.7", "v2.8", "v2.9")


def is_v27(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.7", "v2.8", "v2.9")


def is_v28(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.8", "v2.9")


def is_v29(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] == "v2.9"


def is_v291(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (MAIN_V4, MAIN_V5, ZEBRA_PC_V8, ALFWORLD_V5, ZEBRA_PC_V9, ALFWORLD_V6, ZEBRA_PC_V10, ALFWORLD_V7, ZEBRA_PC_V11, ALFWORLD_V8, ZEBRA_PC_V12, ZEBRA_PC_V13, ZEBRA_PC_V14, ZEBRA_PC_V15, ZEBRA_HP_V3R4, ALFWORLD_V9, ALFWORLD_V10, ALFWORLD_V11)


def is_v292(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (MAIN_V4, MAIN_V5, ZEBRA_PC_V9, ALFWORLD_V6, ZEBRA_PC_V10, ALFWORLD_V7, ZEBRA_PC_V11, ALFWORLD_V8, ZEBRA_PC_V12, ZEBRA_PC_V13, ZEBRA_PC_V14, ZEBRA_PC_V15, ZEBRA_HP_V3R4, ALFWORLD_V9, ALFWORLD_V10, ALFWORLD_V11)


def is_v293(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (MAIN_V4, MAIN_V5, ZEBRA_PC_V10, ALFWORLD_V7, ZEBRA_PC_V11, ALFWORLD_V8, ZEBRA_PC_V12, ZEBRA_PC_V13, ZEBRA_PC_V14, ZEBRA_PC_V15, ZEBRA_HP_V3R4, ALFWORLD_V9, ALFWORLD_V10, ALFWORLD_V11)


def is_v294(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (MAIN_V4, MAIN_V5, ZEBRA_PC_V11, ALFWORLD_V8, ZEBRA_PC_V12, ZEBRA_PC_V13, ZEBRA_PC_V14, ZEBRA_PC_V15, ZEBRA_HP_V3R4, ALFWORLD_V9, ALFWORLD_V10, ALFWORLD_V11)


def is_v295(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (MAIN_V4, MAIN_V5, ZEBRA_PC_V12, ZEBRA_PC_V13, ZEBRA_PC_V14, ZEBRA_PC_V15, ZEBRA_HP_V3R4, ALFWORLD_V9, ALFWORLD_V10, ALFWORLD_V11)


def is_v215(configuration):
    return configuration in (ZEBRA_PC_V14, ZEBRA_PC_V15)


def is_v216(configuration):
    return configuration == ZEBRA_PC_V15


def is_v296(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (ALFWORLD_V10, ALFWORLD_V11)


def is_v297(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration == ALFWORLD_V11


def alfworld_format_rule(configuration, bench=None):
    """The format rule for this run; the historical admissible-share rule stays frozen."""
    return "alfworld-readable-action-v2-9-6" if is_v296(configuration) or (configuration in (MAIN_V4, MAIN_V5) and bench == "alfworld") else "alfworld-admissible-9-10"


def train_rounds(configuration, bench=None):
    """The historical six-round limit, extended only for the Zebra v12 search."""
    return 0 if configuration == ZEBRA_HP_V3R4 or (configuration in (MAIN_V4, MAIN_V5) and bench == "alfworld") else 10 if configuration == ZEBRA_PC_V12 else TRAIN_ROUNDS


def cleanup_grace_seconds(configuration):
    """Only v2.9.2 waits beyond the frozen sandbox removal attempts."""
    return 120 if is_v292(configuration) else 0


def ready_timeout_seconds(configuration):
    """Only v2.9.2 allows slow container starts to answer their first ping."""
    return 90 if is_v292(configuration) else SANDBOX_READY_SECONDS


def train_patience(configuration, bench=None):
    return 0 if configuration == ZEBRA_HP_V3R4 else 8 if configuration == ZEBRA_PC_V12 else 4 if is_v291(configuration) else TRAIN_PATIENCE


FAULT_REPAIRS = 2
INERT_REPAIRS = 1
V216_INERT_REPAIRS = 3
V216_AUDIT_FIXES = 2


def is_zebra(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (ZEBRA_PC_V1, ZEBRA_PC_V2, ZEBRA_PC_V3, ZEBRA_PC_V4, ZEBRA_PC_V5, ZEBRA_PC_V6, ZEBRA_PC_V7, ZEBRA_PC_V8, ZEBRA_PC_V9, ZEBRA_PC_V10, ZEBRA_PC_V11, ZEBRA_PC_V12, ZEBRA_PC_V13, ZEBRA_PC_V14, ZEBRA_PC_V15, ZEBRA_HP_V3R4)


def is_alfworld(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (ALFWORLD_V1, ALFWORLD_V2, ALFWORLD_V3, ALFWORLD_V4, ALFWORLD_V5, ALFWORLD_V6, ALFWORLD_V7, ALFWORLD_V8, ALFWORLD_V9, ALFWORLD_V10, ALFWORLD_V11)


def is_alfworld_v2(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (ALFWORLD_V2, ALFWORLD_V3, ALFWORLD_V4, ALFWORLD_V5, ALFWORLD_V6, ALFWORLD_V7, ALFWORLD_V8, ALFWORLD_V9, ALFWORLD_V10, ALFWORLD_V11)


def _extend(table, value, *, v2=None, v3=None, v4=None):
    previous = value if v2 is None else v2
    third = previous if v3 is None else v3
    return {**table, ZEBRA_PC_V1: value, ZEBRA_PC_V2: deepcopy(previous),
            ZEBRA_PC_V3: deepcopy(third), ZEBRA_PC_V4: deepcopy(third if v4 is None else v4)}


ZEBRA_PC_ROOT = "/data/execskill-20261025-zebra-pc-v1"
ZEBRA_PC_MANIFEST = "/data/execskill-20261025-zebra-pc-v1-manifest.json"
ZEBRA_PC_NAMESPACES = {"G": "G-zpc1", "D": "D-zpc1"}
ZEBRA_PC_V2_ROOT = "/data/execskill-20261025-zebra-pc-v2"
ZEBRA_PC_V2_MANIFEST = "/data/execskill-20261025-zebra-pc-v2-manifest.json"
ZEBRA_PC_V2_NAMESPACES = {"G": "G-zpc2", "D": "D-zpc2"}
ZEBRA_PC_V3_ROOT = "/data/execskill-20261025-zebra-pc-v3"
ZEBRA_PC_V3_MANIFEST = "/data/execskill-20261025-zebra-pc-v3-manifest.json"
ZEBRA_PC_V3_NAMESPACES = {"G": "G-zpc3", "D": "D-zpc3"}
ZEBRA_PC_V4_ROOT = "/data/execskill-20261026-zebra-pc-v4"
ZEBRA_PC_V4_MANIFEST = "/data/execskill-20261026-zebra-pc-v4-manifest.json"
ZEBRA_PC_V4_NAMESPACES = {"G": "G-zpc4", "D": "D-zpc4"}
SUPPORTED_NAMESPACES = (NAMESPACES + tuple(ZEBRA_PC_NAMESPACES.values())
                        + tuple(ZEBRA_PC_V2_NAMESPACES.values()) + tuple(ZEBRA_PC_V3_NAMESPACES.values())
                        + tuple(ZEBRA_PC_V4_NAMESPACES.values()))
SLICES = {**SLICES, ZEBRA: {"run": (60, 1), "accept": (100, 1), "blocks": 1}}
G_ACC = {**G_ACC, ZEBRA: 0}
MDE_POINTS = {**MDE_POINTS, ZEBRA: 10.0}
MAX_NOTE_CHARS = {**MAX_NOTE_CHARS, ZEBRA: 4_000}
LEXICON = {**LEXICON, ZEBRA: LEXICON_TERMS}
MUTATIONS = {**MUTATIONS, "strip_digits": SUPPORTED_BENCHES}
ELUCID_MAX_TOKENS = {**ELUCID_MAX_TOKENS, ZEBRA: 16_384}
ELUCID_READ_TIMEOUT = {**ELUCID_READ_TIMEOUT, ZEBRA: 600}
CELL_ANCHORS = {**CELL_ANCHORS, ZEBRA: (3_400, 5_300)}
TRAIN_CELLS = {**TRAIN_CELLS, ZEBRA: TRAIN_ROUNDS * 2 * 60}

# Maximum logical schedule, before T1/T2 savings: run 60, training 720, acceptance
# S/C 200 + S'/P_y/two twins 400. No generator, P_i, S_dup, or J7. Read 200 C
# and 1,000 procedure cells at the historical five-arm conservative bound.
ZEBRA_SCHEDULE = {ZEBRA: {"run": {ZEBRA: (0, 60)}, "examiner": {},
                         "selftest": {ZEBRA: (0, 720)}, "accept": {ZEBRA: (200, 400)}}}
ZEBRA_STEP_CAPS = {ZEBRA: {
    name: legacy._round_up(MAIN_CAP_FACTOR * (
        sum(5_300 * (card + PROCEDURE_ARM_FACTOR[1] * proc) for card, proc in cells.values())
        + MAIN_RESERVATIONS * READ_RESERVATION), 100_000)
    for name, cells in ZEBRA_SCHEDULE[ZEBRA].items()}}
ZEBRA_READ_CAP = legacy._round_up(MAIN_CAP_FACTOR * (
    5_300 * (200 + PROCEDURE_ARM_FACTOR[1] * 1_000) + MAIN_RESERVATIONS * READ_RESERVATION), MILLION)
ZEBRA_REDO_CAP = max(ZEBRA_STEP_CAPS[ZEBRA].values())
ZEBRA_SOLVER_CAP = legacy._round_up(sum(ZEBRA_STEP_CAPS[ZEBRA].values()) + ZEBRA_READ_CAP + ZEBRA_REDO_CAP,
                                   5 * MILLION)
CONFIGURATIONS = _extend(CONFIGURATIONS, {"order": (ZEBRA,), "solver_cap": ZEBRA_SOLVER_CAP,
                                         "test_read_cap": ZEBRA_READ_CAP, "redo_reserve": ZEBRA_REDO_CAP})
PILOTS = CONFIGURATIONS
CONFIG_STEP_CAPS = _extend(CONFIG_STEP_CAPS, ZEBRA_STEP_CAPS)
CONFIG_SCHEDULE_CELLS = _extend(CONFIG_SCHEDULE_CELLS, ZEBRA_SCHEDULE)
CONFIG_ROLE_CAPS = _extend(CONFIG_ROLE_CAPS, dict(MAIN_V2_ROLE_CAPS))
CONFIG_GLM_CAP = _extend(CONFIG_GLM_CAP, MAIN_CAP_FACTOR * sum(MAIN_V2_ROLE_CAPS.values()))
CONFIG_CAP_FACTOR = _extend(CONFIG_CAP_FACTOR, Fraction(MAIN_CAP_FACTOR))
COST_CHECK_PAUSES = _extend(COST_CHECK_PAUSES, False)
REAL_RUN_EVIDENCE = _extend(REAL_RUN_EVIDENCE, "zebra_pc_v1_real_run", v2="zebra_pc_v2_real_run",
                            v3="zebra_pc_v3_real_run", v4="zebra_pc_v4_real_run")
RUN_ROOTS = _extend(RUN_ROOTS, ZEBRA_PC_ROOT, v2=ZEBRA_PC_V2_ROOT, v3=ZEBRA_PC_V3_ROOT, v4=ZEBRA_PC_V4_ROOT)
CHAIN_NAMESPACES = _extend(CHAIN_NAMESPACES, ZEBRA_PC_NAMESPACES, v2=ZEBRA_PC_V2_NAMESPACES,
                           v3=ZEBRA_PC_V3_NAMESPACES, v4=ZEBRA_PC_V4_NAMESPACES)
TEST_READ_CELLS = _extend(TEST_READ_CELLS, {ZEBRA: (200, 1_000)})
STAGE_READ = _extend(STAGE_READ, False)  # one step has no intermediate stage
ACCEPT_FRESHNESS = _extend(ACCEPT_FRESHNESS, "zebra_split_v1_slices_first_use_probe_items_excluded",
                           v2="zebra_split_v1_slices_reused_zpc1_acceptance_unused",
                           v3="zebra_split_v1_slices_reused_zpc2_acceptance_used_once",
                           v4="zebra_split_v1_slices_reused_zpc3_acceptance_used_twice")
for _name in ("LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES",
              "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
              "ENGINEER_RECORDS", "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION",
              "MULTIPLE_PYTHON_BLOCKS"):
    _old = getattr(legacy, _name)
    globals()[_name] = _extend(_old, _old[MAIN_V2_3])
ENGINEER_RECORDS[ZEBRA_PC_V2] = "engineer-v2-4"
POLICY_VERSIONS[ZEBRA_PC_V2] = POLICY_VERSION_V24
ENGINEER_RECORDS[ZEBRA_PC_V3] = "engineer-v2-5"
POLICY_VERSIONS[ZEBRA_PC_V3] = POLICY_VERSION_V25
ENGINEER_RECORDS[ZEBRA_PC_V4] = "engineer-v2-6"
POLICY_VERSIONS[ZEBRA_PC_V4] = POLICY_VERSION_V25

# One ALFWorld step, with the historical maximum ALF schedule. The former
# cross-benchmark self-test rows and intermediate stage reads have no work here.
# The old acceptance row is conservative for an empty parent: 150 card + 750
# procedure cells costs more than the actual 300 card + 600 procedure cells.
ALFWORLD_V1_ROOT = "/data/execskill-20261026-alfworld-v1"
ALFWORLD_V1_MANIFEST = ALFWORLD_V1_ROOT + "-manifest.json"
ALFWORLD_V1_NAMESPACES = {"G": "G-alf1", "D": "D-alf1"}
SUPPORTED_NAMESPACES += tuple(ALFWORLD_V1_NAMESPACES.values())
ALFWORLD_V1_RESERVATION = 4 * (32_000 + PROMPT_OVERHEAD_MAX + GLM_SOLVER_TOKENS)
ALFWORLD_V1_SCHEDULE = {"alfworld": {
    name: {"alfworld": tuple(cells["alfworld"])}
    for name, cells in legacy.CONFIG_SCHEDULE_CELLS[MAIN_V2_2]["alfworld"].items()}}


def _alfworld_cap(cells, rounding):
    return legacy._round_up(MAIN_CAP_FACTOR * (
        sum(CELL_ANCHORS[bench][1] * (card + PROCEDURE_ARM_FACTOR[1] * proc)
            for bench, (card, proc) in cells.items())
        + MAIN_RESERVATIONS * ALFWORLD_V1_RESERVATION), rounding)


ALFWORLD_V1_STEP_CAPS = {"alfworld": {
    name: _alfworld_cap(cells, 100_000) for name, cells in ALFWORLD_V1_SCHEDULE["alfworld"].items()}}
ALFWORLD_V1_READ_CELLS = {"alfworld": tuple(legacy.TEST_READ_CELLS["main"]["alfworld"])}
ALFWORLD_V1_READ_CAP = _alfworld_cap(ALFWORLD_V1_READ_CELLS, MILLION)
ALFWORLD_V1_REDO_CAP = max(
    _alfworld_cap({bench: (Fraction(card, SLICES["alfworld"]["blocks"]),
                          Fraction(proc, SLICES["alfworld"]["blocks"]))
                  for bench, (card, proc) in cells.items()} if name == "accept" else cells, 100_000)
    for name, cells in ALFWORLD_V1_SCHEDULE["alfworld"].items())
ALFWORLD_V1_SOLVER_CAP = legacy._round_up(
    sum(ALFWORLD_V1_STEP_CAPS["alfworld"].values()) + ALFWORLD_V1_READ_CAP + ALFWORLD_V1_REDO_CAP, 5 * MILLION)
CONFIGURATIONS[ALFWORLD_V1] = {"order": ("alfworld",), "solver_cap": ALFWORLD_V1_SOLVER_CAP,
                              "test_read_cap": ALFWORLD_V1_READ_CAP, "redo_reserve": ALFWORLD_V1_REDO_CAP}
CONFIG_STEP_CAPS[ALFWORLD_V1] = ALFWORLD_V1_STEP_CAPS
CONFIG_SCHEDULE_CELLS[ALFWORLD_V1] = ALFWORLD_V1_SCHEDULE
CONFIG_ROLE_CAPS[ALFWORLD_V1] = deepcopy(MAIN_V2_ROLE_CAPS)
CONFIG_GLM_CAP[ALFWORLD_V1] = MAIN_CAP_FACTOR * sum(MAIN_V2_ROLE_CAPS.values())
CONFIG_CAP_FACTOR[ALFWORLD_V1] = Fraction(MAIN_CAP_FACTOR)
COST_CHECK_PAUSES[ALFWORLD_V1] = False
REAL_RUN_EVIDENCE[ALFWORLD_V1] = "alfworld_v1_real_run"
RUN_ROOTS[ALFWORLD_V1] = ALFWORLD_V1_ROOT
CHAIN_NAMESPACES[ALFWORLD_V1] = ALFWORLD_V1_NAMESPACES
TEST_READ_CELLS[ALFWORLD_V1] = ALFWORLD_V1_READ_CELLS
STAGE_READ[ALFWORLD_V1] = False
ACCEPT_FRESHNESS[ALFWORLD_V1] = "alfworld_main_accept_slice_first_use"
for _name in ("LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES",
              "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
              "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS"):
    globals()[_name][ALFWORLD_V1] = deepcopy(globals()[_name][ZEBRA_PC_V4])
ENGINEER_RECORDS[ALFWORLD_V1] = "engineer-alf-v1"


# v2.7 changes engineer replay-test guidance and feedback only. Its experiment,
# policy and per-chain caps inherit v4 by value; only chain D may launch.
ZEBRA_PC_V5_ROOT = "/data/execskill-20261026-zebra-pc-v5"
ZEBRA_PC_V5_MANIFEST = ZEBRA_PC_V5_ROOT + "-manifest.json"
ZEBRA_PC_V5_NAMESPACES = {"G": "G-zpc5", "D": "D-zpc5"}
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V5_NAMESPACES.values())
for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
              "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
              "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
              "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
              "POLICY_VERSIONS", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS"):
    globals()[_name][ZEBRA_PC_V5] = deepcopy(globals()[_name][ZEBRA_PC_V4])
REAL_RUN_EVIDENCE[ZEBRA_PC_V5] = "zebra_pc_v5_real_run"
RUN_ROOTS[ZEBRA_PC_V5] = ZEBRA_PC_V5_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V5] = ZEBRA_PC_V5_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V5] = "zebra_split_v1_slices_reused_zpc4_acceptance_used_twice"
ENGINEER_RECORDS[ZEBRA_PC_V5] = "engineer-v2-7"


# The second ALFWorld experiment preserves v1's panels, schedule and policy by
# value, while enabling v2.7 replay guidance and the ALF-specific tracker feedback.
ALFWORLD_V2_ROOT = "/data/execskill-20261026-alfworld-v2"
ALFWORLD_V2_MANIFEST = ALFWORLD_V2_ROOT + "-manifest.json"
ALFWORLD_V2_NAMESPACES = {"G": "G-alf2", "D": "D-alf2"}
ALFWORLD_V2_FRESHNESS = "alfworld_split_v1_slices_reused_alf1_acceptance_used_once"
SUPPORTED_NAMESPACES += tuple(ALFWORLD_V2_NAMESPACES.values())
for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
              "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
              "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
              "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
              "POLICY_VERSIONS", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS"):
    globals()[_name][ALFWORLD_V2] = deepcopy(globals()[_name][ALFWORLD_V1])
REAL_RUN_EVIDENCE[ALFWORLD_V2] = "alfworld_v2_real_run"
RUN_ROOTS[ALFWORLD_V2] = ALFWORLD_V2_ROOT
CHAIN_NAMESPACES[ALFWORLD_V2] = ALFWORLD_V2_NAMESPACES
ACCEPT_FRESHNESS[ALFWORLD_V2] = ALFWORLD_V2_FRESHNESS
ENGINEER_RECORDS[ALFWORLD_V2] = "engineer-alf-v2"


# v2.8 inherits panels, acceptance bars and token ledgers by value. Only the
# outcome-judged engineer/worker contract and experiment identity change.
ZEBRA_PC_V6_ROOT = "/data/execskill-20261026-zebra-pc-v6"
ZEBRA_PC_V6_MANIFEST = ZEBRA_PC_V6_ROOT + "-manifest.json"
ZEBRA_PC_V6_NAMESPACES = {"G": "G-zpc6", "D": "D-zpc6"}
ALFWORLD_V3_ROOT = "/data/execskill-20261026-alfworld-v3"
ALFWORLD_V3_MANIFEST = ALFWORLD_V3_ROOT + "-manifest.json"
ALFWORLD_V3_NAMESPACES = {"G": "G-alf3", "D": "D-alf3"}
ALFWORLD_V3_FRESHNESS = "alfworld_split_v1_slices_reused_acceptance_used_once"
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V6_NAMESPACES.values()) + tuple(ALFWORLD_V3_NAMESPACES.values())
for _child, _parent in ((ZEBRA_PC_V6, ZEBRA_PC_V5), (ALFWORLD_V3, ALFWORLD_V2)):
    for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
                  "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
                  "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
                  "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
                  "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS"):
        globals()[_name][_child] = deepcopy(globals()[_name][_parent])
    ENGINEER_RECORDS[_child] = "engineer-v2-8"
    POLICY_VERSIONS[_child] = POLICY_VERSION_V28
REAL_RUN_EVIDENCE[ZEBRA_PC_V6] = "zebra_pc_v6_real_run"
REAL_RUN_EVIDENCE[ALFWORLD_V3] = "alfworld_v3_real_run"
RUN_ROOTS[ZEBRA_PC_V6] = ZEBRA_PC_V6_ROOT
RUN_ROOTS[ALFWORLD_V3] = ALFWORLD_V3_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V6] = ZEBRA_PC_V6_NAMESPACES
CHAIN_NAMESPACES[ALFWORLD_V3] = ALFWORLD_V3_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V6] = "zebra_split_v1_slices_reused_accept_used_three_times_plus_ub_probe"
ACCEPT_FRESHNESS[ALFWORLD_V3] = ALFWORLD_V3_FRESHNESS

# v2.9 is a fresh identity; frozen parent tables are copied by value. Extra
# judge/confirmation ledger formulas are defined separately in v29_limits.
ZEBRA_PC_V7_ROOT = "/data/execskill-20261027-zebra-pc-v7"
ZEBRA_PC_V7_MANIFEST = ZEBRA_PC_V7_ROOT + "-manifest.json"
ZEBRA_PC_V7_NAMESPACES = {"G": "G-zpc7", "D": "D-zpc7"}
ALFWORLD_V4_ROOT = "/data/execskill-20261027-alfworld-v4"
ALFWORLD_V4_MANIFEST = ALFWORLD_V4_ROOT + "-manifest.json"
ALFWORLD_V4_NAMESPACES = {"G": "G-alf4", "D": "D-alf4"}
ALFWORLD_V4_FRESHNESS = "alfworld_split_v1_slices_reused_acceptance_used_once"
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V7_NAMESPACES.values()) + tuple(ALFWORLD_V4_NAMESPACES.values())
for _child, _parent in ((ZEBRA_PC_V7, ZEBRA_PC_V6), (ALFWORLD_V4, ALFWORLD_V3)):
    for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
                  "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
                  "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
                  "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
                  "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS"):
        globals()[_name][_child] = deepcopy(globals()[_name][_parent])
    ENGINEER_RECORDS[_child] = "engineer-v2-9"
    POLICY_VERSIONS[_child] = POLICY_VERSION_V29
REAL_RUN_EVIDENCE[ZEBRA_PC_V7] = "zebra_pc_v7_real_run"
REAL_RUN_EVIDENCE[ALFWORLD_V4] = "alfworld_v4_real_run"
RUN_ROOTS[ZEBRA_PC_V7] = ZEBRA_PC_V7_ROOT
RUN_ROOTS[ALFWORLD_V4] = ALFWORLD_V4_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V7] = ZEBRA_PC_V7_NAMESPACES
CHAIN_NAMESPACES[ALFWORLD_V4] = ALFWORLD_V4_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V7] = "zebra_split_v1_slices_reused_accept_used_four_times_plus_ub_probe"
ACCEPT_FRESHNESS[ALFWORLD_V4] = ALFWORLD_V4_FRESHNESS
CONFIRM_FRESHNESS = {
    ZEBRA_PC_V7: "zebra_split_v1_confirm_spare_probe_smoke_first_use",
    ALFWORLD_V4: "alfworld_split_v1_confirm_spare_rooms_first_use"}


# Conservative extra calls reserve one whole-proposal retry, one format retry
# per change, and one after each ordinary fix. They do not consume TRAIN_FIXES.
ENGINEER_CALL_BUDGETS = {name: ENGINEER_CALLS + (1 + MAX_CHANGES * 2 if is_v28(name) else 0)
                       for name in CONFIGURATIONS}
TRAIN_ENGINEER_CALL_BUDGETS = {
    name: TRAIN_ENGINEER_CALLS + (1 + MAX_CHANGES * (TRAIN_FIXES + 1) if is_v28(name) else 0)
    for name in CONFIGURATIONS}
for _configuration in (ZEBRA_PC_V7, ALFWORLD_V4):
    ENGINEER_CALL_BUDGETS[_configuration] += MAX_CHANGES
    TRAIN_ENGINEER_CALL_BUDGETS[_configuration] += MAX_CHANGES
V28_HASHSEED = 0


def launchable_chains(configuration):
    require(configuration in CONFIGURATIONS, "Unknown run configuration")
    return tuple(CHAINS) if is_v211(configuration) else (("D",) if is_alfworld(configuration) or is_v27(configuration) else tuple(CHAINS))


def supports_configuration(name):
    return name in CONFIGURATIONS


def configuration_registry():
    return CONFIGURATIONS


def configuration_of(setting):
    value = (getattr(setting, "extra", None) or {}).get("configuration", PILOT)
    require(supports_configuration(value), "Unknown run configuration: %r" % (value,))
    return value


def active_benches(configuration):
    configuration = configuration or PILOT
    require(supports_configuration(configuration), "Unknown run configuration")
    if is_v214(configuration):
        return CONFIGURATIONS[configuration]["order"]
    # Historical clients/cards/read rosters were all five, even in two-step pilots.
    return (ZEBRA,) if is_zebra(configuration) else ("alfworld",) if is_alfworld(configuration) else BENCHES


def read_benches(configuration):
    return active_benches(configuration)


def order_of(setting):
    return CONFIGURATIONS[configuration_of(setting)]["order"]


def learning_of(setting):
    return LEARNING[configuration_of(setting)]


def namespace_of(setting, chain):
    require(chain in CHAINS, "Unknown chain")
    found = CHAIN_NAMESPACES.get(configuration_of(setting))
    return found[chain] if found is not None else chain


def first_call_bench(configuration=PILOT):
    require(supports_configuration(configuration), "Unknown run configuration")
    return CONFIGURATIONS[configuration]["order"][0]


def order_tag(bench):
    require(bench in SUPPORTED_BENCHES, "Unknown bench")
    return legacy._tag("order", bench)


def stage_arms_max(configuration):
    require(supports_configuration(configuration), "Unknown run configuration")
    return len(CONFIGURATIONS[configuration]["order"]) - 1 if STAGE_READ[configuration] else 0


def read_arms_of(configuration):
    require(supports_configuration(configuration), "Unknown run configuration")
    if is_v214(configuration):
        return ("F", "C", "B", STAGES)
    if is_zebra_fc(configuration):
        return ("F", "C")
    if is_v210(configuration):
        return ("C", "B") if configuration == BASELINE_V210 else ("F", "C", "B")
    return TEST_ARMS + ((STAGES,) if STAGE_READ[configuration] else ())


def estimate_arms(configuration):
    if is_v214(configuration):
        return 1 + stage_arms_max(configuration)
    if is_zebra_fc(configuration):
        return 1
    if is_v210(configuration):
        return 0 if configuration == BASELINE_V210 else 1
    return TEST_READ_ESTIMATE_ARMS + stage_arms_max(configuration)


def solver_tokens(model, bench):
    require(model in SOLVERS and bench in SUPPORTED_BENCHES, "Unknown solver or bench")
    return GLM_SOLVER_TOKENS if model == CHAINS["G"] else ELUCID_MAX_TOKENS[bench]


def read_timeout(model, bench):
    require(model in SOLVERS and bench in SUPPORTED_BENCHES, "Unknown solver or bench")
    return GLM_READ_TIMEOUT if model == CHAINS["G"] else ELUCID_READ_TIMEOUT[bench]


def ledger_bound(model, bench, *, branch=None, longest=None):
    if bench != ZEBRA:
        return legacy.ledger_bound(model, bench, branch=branch, longest=longest)
    nominal = solver_tokens(model, bench)
    if model == CHAINS["G"]:
        require(branch is None and longest is None, "Chain G has one bound")
        return nominal
    require(branch in BRANCHES, "Branch E or N, from S1")
    if branch == "E":
        require(longest is None, "Branch E needs no probe length")
        return 2 * nominal
    require(type(longest) is int and longest > 0, "Branch N needs the longest probe completion")
    return max(4 * nominal, -(-3 * longest // 2))


def fired_share(bench, pilot=PILOT):
    if is_v214(pilot):
        require(bench in active_benches(pilot), "Only the registered mixed panel")
        home = CONFIGURATIONS[pilot]["order"]
        if bench in home:
            return FIRED_SHARES["home"]
        related = any(bench in pair and set(pair) & set(home) for pair in similar_pairs(pilot))
        return FIRED_SHARES["similar" if related else "other"]
    if is_alfworld(pilot):
        require(bench == "alfworld", "Only the registered ALFWorld panel")
        return FIRED_SHARES["home"]
    if not is_zebra(pilot):
        return legacy.fired_share(bench, pilot)
    require(bench == ZEBRA, "Only the registered ZebraLogic panel")
    return Fraction(1)


def read_estimate_terms(per_cell, ratio, pilot=PILOT):
    if is_v214(pilot):
        require(isinstance(per_cell, dict) and set(per_cell) == set(read_benches(pilot)),
                'Five-bench main-v5 per-cell measurement required')
        terms = {}
        for bench in read_benches(pilot):
            entry = per_cell[bench]
            card = legacy._exact(entry['card'], 'card cell')
            proc = (card * PROCEDURE_ARM_FACTOR[1]
                    if entry.get('procedure_assumed') is True or entry.get('procedure') is None
                    else legacy._exact(entry['procedure'], 'procedure cell'))
            stages = stage_arms_max(pilot) * fired_share(bench, pilot)
            terms[bench] = legacy._exact(ratio, 'ratio') * read_items(pilot, bench) * (2 * card + (1 + stages) * proc)
        return terms
    if is_v210(pilot):
        require(isinstance(per_cell, dict) and set(per_cell) == set(BENCHES), 'Five-bench per-cell measurement required')
        terms = {}
        for bench in BENCHES:
            entry = per_cell[bench]
            card = legacy._exact(entry['card'], 'card cell')
            proc = (card * PROCEDURE_ARM_FACTOR[1]
                    if entry.get('procedure_assumed') is True or entry.get('procedure') is None
                    else legacy._exact(entry['procedure'], 'procedure cell'))
            c, p = TEST_READ_CELLS[pilot][bench]
            terms[bench] = legacy._exact(ratio, 'ratio') * (c * card + p * proc)
        return terms
    if is_alfworld(pilot):
        require(isinstance(per_cell, dict) and set(per_cell) == {"alfworld"}
                and isinstance(per_cell["alfworld"], dict), "ALFWorld per-cell measurement required")
        entry = per_cell["alfworld"]
        card = legacy._exact(entry.get("card"), "card cell")
        proc = (card * PROCEDURE_ARM_FACTOR[1]
                if entry.get("procedure_assumed") is True or entry.get("procedure") is None
                else legacy._exact(entry["procedure"], "procedure cell"))
        return {"alfworld": legacy._exact(ratio, "ratio") * TEST_READ_CELLS[pilot]["alfworld"][0]
                * (card + estimate_arms(pilot) * fired_share("alfworld", pilot) * proc)}
    if not is_zebra(pilot):
        return legacy.read_estimate_terms(per_cell, ratio, pilot)
    require(isinstance(per_cell, dict) and set(per_cell) == {ZEBRA}, "ZebraLogic per-cell measurement required")
    entry = per_cell[ZEBRA]
    card = legacy._exact(entry.get("card"), "card cell")
    proc = (card * PROCEDURE_ARM_FACTOR[1] if entry.get("procedure_assumed") is True or entry.get("procedure") is None
            else legacy._exact(entry["procedure"], "procedure cell"))
    return {ZEBRA: legacy._exact(ratio, "ratio") * 200 * (card + estimate_arms(pilot) * proc)}


def estimate_test_read(per_cell, ratio, pilot=PILOT):
    return math.ceil(sum(read_estimate_terms(per_cell, ratio, pilot).values()))


# Apply only the additional v2.9 reservations after constructing inherited tables.
from . import v29_limits as _v29_limits
import sys as _sys
_v29_limits.extend_profiles(_sys.modules[__name__])


# v2.9.1 copies the fully extended v2.9 parents, including audit and confirm caps.
ZEBRA_PC_V8_ROOT = "/data/execskill-20261027-zebra-pc-v8"
ZEBRA_PC_V8_MANIFEST = ZEBRA_PC_V8_ROOT + "-manifest.json"
ZEBRA_PC_V8_NAMESPACES = {"G": "G-zpc8", "D": "D-zpc8"}
ALFWORLD_V5_ROOT = "/data/execskill-20261027-alfworld-v5"
ALFWORLD_V5_MANIFEST = ALFWORLD_V5_ROOT + "-manifest.json"
ALFWORLD_V5_NAMESPACES = {"G": "G-alf5", "D": "D-alf5"}
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V8_NAMESPACES.values()) + tuple(ALFWORLD_V5_NAMESPACES.values())
for _child, _parent in ((ZEBRA_PC_V8, ZEBRA_PC_V7), (ALFWORLD_V5, ALFWORLD_V4)):
    for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
                  "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
                  "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
                  "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
                  "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "POLICY_VERSIONS", "ENGINEER_CALL_BUDGETS",
                  "TRAIN_ENGINEER_CALL_BUDGETS"):
        globals()[_name][_child] = deepcopy(globals()[_name][_parent])
    ENGINEER_RECORDS[_child] = "engineer-v2-9-1"
    # A format retry after every new fault repair, plus the parent's audit fix.
    ENGINEER_CALL_BUDGETS[_child] += MAX_CHANGES * (FAULT_REPAIRS * 2 + 1)
    TRAIN_ENGINEER_CALL_BUDGETS[_child] += MAX_CHANGES * (FAULT_REPAIRS * 2 + 1)
REAL_RUN_EVIDENCE[ZEBRA_PC_V8] = "zebra_pc_v8_real_run"
REAL_RUN_EVIDENCE[ALFWORLD_V5] = "alfworld_v5_real_run"
RUN_ROOTS[ZEBRA_PC_V8] = ZEBRA_PC_V8_ROOT
RUN_ROOTS[ALFWORLD_V5] = ALFWORLD_V5_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V8] = ZEBRA_PC_V8_NAMESPACES
CHAIN_NAMESPACES[ALFWORLD_V5] = ALFWORLD_V5_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V8] = "zebra_split_v1_slices_reused_accept_used_four_times_plus_ub_probe"
ACCEPT_FRESHNESS[ALFWORLD_V5] = "alfworld_split_v1_slices_reused_after_alfworld_v4"
CONFIRM_FRESHNESS[ZEBRA_PC_V8] = "zebra_split_v1_confirm_spare_probe_smoke_first_use"
CONFIRM_FRESHNESS[ALFWORLD_V5] = "alfworld_split_v1_confirm_spare_rooms_reused_after_alfworld_v4"
_v29_limits.extend_v291_profiles(_sys.modules[__name__])


# v2.9.2 inherits the fully reserved v2.9.1 profiles without adding any calls.
ZEBRA_PC_V9_ROOT = "/data/execskill-20261027-zebra-pc-v9"
ZEBRA_PC_V9_MANIFEST = ZEBRA_PC_V9_ROOT + "-manifest.json"
ZEBRA_PC_V9_NAMESPACES = {"G": "G-zpc9", "D": "D-zpc9"}
ALFWORLD_V6_ROOT = "/data/execskill-20261027-alfworld-v6"
ALFWORLD_V6_MANIFEST = ALFWORLD_V6_ROOT + "-manifest.json"
ALFWORLD_V6_NAMESPACES = {"G": "G-alf6", "D": "D-alf6"}
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V9_NAMESPACES.values()) + tuple(ALFWORLD_V6_NAMESPACES.values())
for _child, _parent in ((ZEBRA_PC_V9, ZEBRA_PC_V8), (ALFWORLD_V6, ALFWORLD_V5)):
    for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
                  "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
                  "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
                  "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
                  "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "POLICY_VERSIONS", "ENGINEER_CALL_BUDGETS",
                  "TRAIN_ENGINEER_CALL_BUDGETS"):
        globals()[_name][_child] = deepcopy(globals()[_name][_parent])
    ENGINEER_RECORDS[_child] = "engineer-v2-9-2"
REAL_RUN_EVIDENCE[ZEBRA_PC_V9] = "zebra_pc_v9_real_run"
REAL_RUN_EVIDENCE[ALFWORLD_V6] = "alfworld_v6_real_run"
RUN_ROOTS[ZEBRA_PC_V9] = ZEBRA_PC_V9_ROOT
RUN_ROOTS[ALFWORLD_V6] = ALFWORLD_V6_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V9] = ZEBRA_PC_V9_NAMESPACES
CHAIN_NAMESPACES[ALFWORLD_V6] = ALFWORLD_V6_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V9] = "zebra_split_v1_slices_accept_after_zebra_pc_v8"
ACCEPT_FRESHNESS[ALFWORLD_V6] = "alfworld_split_v1_slices_after_alfworld_v5"
CONFIRM_FRESHNESS[ZEBRA_PC_V9] = "zebra_split_v1_confirm_after_zebra_pc_v8"
CONFIRM_FRESHNESS[ALFWORLD_V6] = "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v5"


# v2.9.3 inherits every v2.9.2 table; only identities and retry prompting change.
ZEBRA_PC_V10_ROOT = "/data/execskill-20261027-zebra-pc-v10"
ZEBRA_PC_V10_MANIFEST = ZEBRA_PC_V10_ROOT + "-manifest.json"
ZEBRA_PC_V10_NAMESPACES = {"G": "G-zpc10", "D": "D-zpc10"}
ALFWORLD_V7_ROOT = "/data/execskill-20261027-alfworld-v7"
ALFWORLD_V7_MANIFEST = ALFWORLD_V7_ROOT + "-manifest.json"
ALFWORLD_V7_NAMESPACES = {"G": "G-alf7", "D": "D-alf7"}
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V10_NAMESPACES.values()) + tuple(ALFWORLD_V7_NAMESPACES.values())
for _child, _parent in ((ZEBRA_PC_V10, ZEBRA_PC_V9), (ALFWORLD_V7, ALFWORLD_V6)):
    for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
                  "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
                  "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
                  "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
                  "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "POLICY_VERSIONS", "ENGINEER_CALL_BUDGETS",
                  "TRAIN_ENGINEER_CALL_BUDGETS"):
        globals()[_name][_child] = deepcopy(globals()[_name][_parent])
    ENGINEER_RECORDS[_child] = "engineer-v2-9-3"
REAL_RUN_EVIDENCE[ZEBRA_PC_V10] = "zebra_pc_v10_real_run"
REAL_RUN_EVIDENCE[ALFWORLD_V7] = "alfworld_v7_real_run"
RUN_ROOTS[ZEBRA_PC_V10] = ZEBRA_PC_V10_ROOT
RUN_ROOTS[ALFWORLD_V7] = ALFWORLD_V7_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V10] = ZEBRA_PC_V10_NAMESPACES
CHAIN_NAMESPACES[ALFWORLD_V7] = ALFWORLD_V7_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V10] = "zebra_split_v1_slices_accept_after_zebra_pc_v9"
ACCEPT_FRESHNESS[ALFWORLD_V7] = "alfworld_split_v1_slices_after_alfworld_v5_v6_not_launched"
CONFIRM_FRESHNESS[ZEBRA_PC_V10] = "zebra_split_v1_confirm_after_zebra_pc_v9"
CONFIRM_FRESHNESS[ALFWORLD_V7] = "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v5_v6_not_launched"


# v2.9.4 inherits every v2.9.3 table and call cap; inert repair uses that existing budget.
ZEBRA_PC_V11_ROOT = "/data/execskill-20261027-zebra-pc-v11"
ZEBRA_PC_V11_MANIFEST = ZEBRA_PC_V11_ROOT + "-manifest.json"
ZEBRA_PC_V11_NAMESPACES = {"G": "G-zpc11", "D": "D-zpc11"}
ALFWORLD_V8_ROOT = "/data/execskill-20261027-alfworld-v8"
ALFWORLD_V8_MANIFEST = ALFWORLD_V8_ROOT + "-manifest.json"
ALFWORLD_V8_NAMESPACES = {"G": "G-alf8", "D": "D-alf8"}
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V11_NAMESPACES.values()) + tuple(ALFWORLD_V8_NAMESPACES.values())
for _child, _parent in ((ZEBRA_PC_V11, ZEBRA_PC_V10), (ALFWORLD_V8, ALFWORLD_V7)):
    for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
                  "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
                  "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
                  "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
                  "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "POLICY_VERSIONS", "ENGINEER_CALL_BUDGETS",
                  "TRAIN_ENGINEER_CALL_BUDGETS"):
        globals()[_name][_child] = deepcopy(globals()[_name][_parent])
    ENGINEER_RECORDS[_child] = "engineer-v2-9-4"
REAL_RUN_EVIDENCE[ZEBRA_PC_V11] = "zebra_pc_v11_real_run"
REAL_RUN_EVIDENCE[ALFWORLD_V8] = "alfworld_v8_real_run"
RUN_ROOTS[ZEBRA_PC_V11] = ZEBRA_PC_V11_ROOT
RUN_ROOTS[ALFWORLD_V8] = ALFWORLD_V8_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V11] = ZEBRA_PC_V11_NAMESPACES
CHAIN_NAMESPACES[ALFWORLD_V8] = ALFWORLD_V8_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V11] = "zebra_split_v1_slices_accept_after_zebra_pc_v9_v10_not_launched"
ACCEPT_FRESHNESS[ALFWORLD_V8] = "alfworld_split_v1_slices_after_alfworld_v7"
CONFIRM_FRESHNESS[ZEBRA_PC_V11] = "zebra_split_v1_confirm_after_zebra_pc_v9_v10_not_launched"
CONFIRM_FRESHNESS[ALFWORLD_V8] = "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7"


# v2.9.5 inherits v2.9.4; only Zebra search rounds expand the step reservations.
ZEBRA_PC_V12_ROOT = "/data/execskill-20261027-zebra-pc-v12"
ZEBRA_PC_V12_MANIFEST = ZEBRA_PC_V12_ROOT + "-manifest.json"
ZEBRA_PC_V12_NAMESPACES = {"G": "G-zpc12", "D": "D-zpc12"}
ALFWORLD_V9_ROOT = "/data/execskill-20261027-alfworld-v9"
ALFWORLD_V9_MANIFEST = ALFWORLD_V9_ROOT + "-manifest.json"
ALFWORLD_V9_NAMESPACES = {"G": "G-alf9", "D": "D-alf9"}
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V12_NAMESPACES.values()) + tuple(ALFWORLD_V9_NAMESPACES.values())
for _child, _parent in ((ZEBRA_PC_V12, ZEBRA_PC_V11), (ALFWORLD_V9, ALFWORLD_V8)):
    for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
                  "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
                  "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
                  "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
                  "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "POLICY_VERSIONS", "ENGINEER_CALL_BUDGETS",
                  "TRAIN_ENGINEER_CALL_BUDGETS"):
        globals()[_name][_child] = deepcopy(globals()[_name][_parent])
    ENGINEER_RECORDS[_child] = "engineer-v2-9-5"
REAL_RUN_EVIDENCE[ZEBRA_PC_V12] = "zebra_pc_v12_real_run"
REAL_RUN_EVIDENCE[ALFWORLD_V9] = "alfworld_v9_real_run"
RUN_ROOTS[ZEBRA_PC_V12] = ZEBRA_PC_V12_ROOT
RUN_ROOTS[ALFWORLD_V9] = ALFWORLD_V9_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V12] = ZEBRA_PC_V12_NAMESPACES
CHAIN_NAMESPACES[ALFWORLD_V9] = ALFWORLD_V9_NAMESPACES
ACCEPT_FRESHNESS[ZEBRA_PC_V12] = "zebra_split_v1_slices_accept_after_zebra_pc_v9_v11"
ACCEPT_FRESHNESS[ALFWORLD_V9] = "alfworld_split_v1_slices_after_alfworld_v7_v8_not_launched"
CONFIRM_FRESHNESS[ZEBRA_PC_V12] = "zebra_split_v1_confirm_after_zebra_pc_v9_v11"
CONFIRM_FRESHNESS[ALFWORLD_V9] = "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7_v8_not_launched"

_v29_limits.extend_v295_profiles(_sys.modules[__name__])


# v2.9.6 changes only the ALFWorld judge rule; the v2.9.5 engineer and limits stay exact.
ALFWORLD_V10_ROOT = "/data/execskill-20261028-alfworld-v10"
ALFWORLD_V10_MANIFEST = ALFWORLD_V10_ROOT + "-manifest.json"
ALFWORLD_V10_NAMESPACES = {"G": "G-alf10", "D": "D-alf10"}
SUPPORTED_NAMESPACES += tuple(ALFWORLD_V10_NAMESPACES.values())
for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
              "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
              "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
              "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
              "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "POLICY_VERSIONS", "ENGINEER_CALL_BUDGETS",
              "TRAIN_ENGINEER_CALL_BUDGETS", "ENGINEER_RECORDS"):
    globals()[_name][ALFWORLD_V10] = deepcopy(globals()[_name][ALFWORLD_V9])
REAL_RUN_EVIDENCE[ALFWORLD_V10] = "alfworld_v10_real_run"
RUN_ROOTS[ALFWORLD_V10] = ALFWORLD_V10_ROOT
CHAIN_NAMESPACES[ALFWORLD_V10] = ALFWORLD_V10_NAMESPACES
ACCEPT_FRESHNESS[ALFWORLD_V10] = "alfworld_split_v1_slices_after_alfworld_v7_accept_v9_stopped"
CONFIRM_FRESHNESS[ALFWORLD_V10] = "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7_v9_stopped"


# v2.9.7 extends the audit disclosure and pools same-text acceptance baselines only.
ALFWORLD_V11_ROOT = "/data/execskill-20261028-alfworld-v11"
ALFWORLD_V11_MANIFEST = ALFWORLD_V11_ROOT + "-manifest.json"
ALFWORLD_V11_NAMESPACES = {"G": "G-alf11", "D": "D-alf11"}
SUPPORTED_NAMESPACES += tuple(ALFWORLD_V11_NAMESPACES.values())
for _name in ("CONFIGURATIONS", "CONFIG_STEP_CAPS", "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP",
              "CONFIG_CAP_FACTOR", "COST_CHECK_PAUSES", "TEST_READ_CELLS", "STAGE_READ", "LEARNING", "FIX_ECHO",
              "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES", "ENGINEER_MAX_TOKENS",
              "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "IDENTICAL_REQUEST_REUSE",
              "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "POLICY_VERSIONS", "ENGINEER_CALL_BUDGETS",
              "TRAIN_ENGINEER_CALL_BUDGETS", "ENGINEER_RECORDS"):
    globals()[_name][ALFWORLD_V11] = deepcopy(globals()[_name][ALFWORLD_V10])
ACCEPT_RULES[ALFWORLD_V11]["name"] = "practical-v2-9-7-pooled"
REAL_RUN_EVIDENCE[ALFWORLD_V11] = "alfworld_v11_real_run"
RUN_ROOTS[ALFWORLD_V11] = ALFWORLD_V11_ROOT
CHAIN_NAMESPACES[ALFWORLD_V11] = ALFWORLD_V11_NAMESPACES
ACCEPT_FRESHNESS[ALFWORLD_V11] = "alfworld_split_v1_slices_after_alfworld_v10_accept_test_read"
CONFIRM_FRESHNESS[ALFWORLD_V11] = "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v10"


# v2.10 inherits the five-bench v2.3 family; no single-bench v2.4+ behavior is ported.
BASELINE_V210 = 'baseline-v210'
MAIN_V3 = 'main-v3'
BASELINE_V210_ROOT = '/data/execskill-20261029-baseline-v210'
MAIN_V3_ROOT = '/data/execskill-20261029-main-v3'
BASELINE_V210_MANIFEST = BASELINE_V210_ROOT + '-manifest.json'
MAIN_V3_MANIFEST = MAIN_V3_ROOT + '-manifest.json'
BASELINE_V210_NAMESPACES = {'G': 'G-base210', 'D': 'D-base210'}
MAIN_V3_NAMESPACES = {'G': 'G-v3', 'D': 'D-v3'}


def is_v210(configuration):
    return configuration in (BASELINE_V210, MAIN_V3, MAIN_V4, MAIN_V5)


def read_items(configuration, bench):
    """Number of test items; TEST_READ_CELLS instead counts card/procedure work."""
    if is_v214(configuration):
        return MAIN_V5_TEST_ITEMS[bench]
    return TEST_READ_CELLS[MAIN_V2_3 if is_v210(configuration) else configuration][bench][0]


for _child in (BASELINE_V210, MAIN_V3):
    for _name in ('CONFIGURATIONS', 'CONFIG_STEP_CAPS', 'CONFIG_SCHEDULE_CELLS', 'CONFIG_ROLE_CAPS',
                  'CONFIG_GLM_CAP', 'CONFIG_CAP_FACTOR', 'COST_CHECK_PAUSES', 'TEST_READ_CELLS', 'STAGE_READ',
                  'LEARNING', 'FIX_ECHO', 'META_COUNTERFACTUAL', 'TRAIN_SIGN', 'PRUNE_NON_FIRING', 'ACCEPT_RULES',
                  'ENGINEER_MAX_TOKENS', 'TRIM_PAYLOADS', 'NORMALIZE_STRUCTURE', 'CHECK_NON_FIRING',
                  'IDENTICAL_REQUEST_REUSE', 'CODE_EXTRACTION', 'MULTIPLE_PYTHON_BLOCKS', 'POLICY_VERSIONS',
                  'ENGINEER_CALL_BUDGETS', 'TRAIN_ENGINEER_CALL_BUDGETS', 'ENGINEER_RECORDS'):
        globals()[_name][_child] = deepcopy(globals()[_name][MAIN_V2_3])
    FEATURE_FAMILIES[_child] = 'v2.3'
    STAGE_READ[_child] = False
    ACCEPT_FRESHNESS[_child] = 'fivebench_slices_after_main_v2_2_v2_3_not_launched'
    TEST_READ_CELLS[_child] = {b: (2 * n, n if _child == MAIN_V3 else 0)
                              for b, (n, _) in TEST_READ_CELLS[MAIN_V2_3].items()}
    _tokens = sum(CELL_ANCHORS[b][1] * (c + PROCEDURE_ARM_FACTOR[1] * p)
                  for b, (c, p) in TEST_READ_CELLS[_child].items())
    CONFIGURATIONS[_child]['test_read_cap'] = legacy._round_up(MAIN_CAP_FACTOR * (
        _tokens + len(BENCHES) * MAIN_RESERVATIONS * READ_RESERVATION), MILLION)

# Subtract P_y from acceptance and G_acc, and P_i on the three generating benches.
# Keep the S_dup instrument, J7 probes and acceptance withholding cells unchanged.
for _bench in BENCHES[:-1]:
    _n, _runs = SLICES[_bench]['accept']
    _removed = _n * _runs * (2 if _bench in GENERATING else 1)
    _card, _proc = CONFIG_SCHEDULE_CELLS[MAIN_V3][_bench]['accept'][_bench]
    CONFIG_SCHEDULE_CELLS[MAIN_V3][_bench]['accept'][_bench] = (_card, _proc - _removed)
    _card, _proc = CONFIG_SCHEDULE_CELLS[MAIN_V3][_bench]['examiner'][_bench]
    CONFIG_SCHEDULE_CELLS[MAIN_V3][_bench]['examiner'][_bench] = (_card, _proc - G_ACC[_bench])
    for _kind in ('accept', 'examiner'):
        _cells = CONFIG_SCHEDULE_CELLS[MAIN_V3][_bench][_kind]
        CONFIG_STEP_CAPS[MAIN_V3][_bench][_kind] = legacy._round_up(MAIN_CAP_FACTOR * (
            sum(CELL_ANCHORS[b][1] * (c + PROCEDURE_ARM_FACTOR[1] * p) for b, (c, p) in _cells.items())
            + MAIN_RESERVATIONS * READ_RESERVATION), 100_000)
CONFIG_SCHEDULE_CELLS[MAIN_V3].pop('alfworld')
CONFIG_STEP_CAPS[MAIN_V3].pop('alfworld')
CONFIG_SCHEDULE_CELLS[BASELINE_V210] = {}
CONFIG_STEP_CAPS[BASELINE_V210] = {}
CONFIG_ROLE_CAPS[BASELINE_V210] = {key: 0 for key in CONFIG_ROLE_CAPS[MAIN_V2_3]}
CONFIG_GLM_CAP[BASELINE_V210] = 0
CONFIG_GLM_CAP[MAIN_V3] = MAIN_CAP_FACTOR * 4 * sum(CONFIG_ROLE_CAPS[MAIN_V3].values())
LEARNING[BASELINE_V210] = 'none'
ENGINEER_CALL_BUDGETS[BASELINE_V210] = TRAIN_ENGINEER_CALL_BUDGETS[BASELINE_V210] = 0
CONFIGURATIONS[BASELINE_V210]['redo_reserve'] = 0
# One redo: largest retained whole non-accept unit or single acceptance block.
CONFIGURATIONS[MAIN_V3]['redo_reserve'] = max(
    legacy._round_up(MAIN_CAP_FACTOR * (
        sum(CELL_ANCHORS[b][1] * (c + PROCEDURE_ARM_FACTOR[1] * p)
            / (SLICES[bench]['blocks'] if kind == 'accept' else 1) for b, (c, p) in cells.items())
        + MAIN_RESERVATIONS * READ_RESERVATION), 100_000)
    for bench, kinds in CONFIG_SCHEDULE_CELLS[MAIN_V3].items() for kind, cells in kinds.items())
for _child, _root, _names, _evidence in (
        (BASELINE_V210, BASELINE_V210_ROOT, BASELINE_V210_NAMESPACES, 'baseline_v210_real_run'),
        (MAIN_V3, MAIN_V3_ROOT, MAIN_V3_NAMESPACES, 'main_v3_real_run')):
    RUN_ROOTS[_child], CHAIN_NAMESPACES[_child], REAL_RUN_EVIDENCE[_child] = _root, _names, _evidence
    SUPPORTED_NAMESPACES += tuple(_names.values())
    CONFIGURATIONS[_child]['solver_cap'] = legacy._round_up(
        sum(sum(c.values()) for c in CONFIG_STEP_CAPS[_child].values())
        + CONFIGURATIONS[_child]['test_read_cap'] + CONFIGURATIONS[_child]['redo_reserve'], 5 * MILLION)
PLACEBO_ARMS = {name: not is_v210(name) for name in CONFIGURATIONS}
TEST_WITHHOLDING = {name: not is_v210(name) for name in CONFIGURATIONS}


def is_v214(configuration):
    return configuration == MAIN_V5


def machinery_configuration(configuration, bench):
    """Select an inherited method without changing the run or record identity."""
    return (ZEBRA_PC_V13 if bench == ZEBRA else MAIN_V4) if is_v214(configuration) else configuration


def uses_v211(configuration, bench):
    return machinery_configuration(configuration, bench) == MAIN_V4


def uses_v212(configuration, bench):
    return is_v212(machinery_configuration(configuration, bench))


def acceptance_rule(configuration, bench):
    return deepcopy(ACCEPT_RULES[machinery_configuration(configuration, bench)])


def accept_freshness(configuration, bench):
    return ACCEPT_FRESHNESS[machinery_configuration(configuration, bench)]


def confirm_freshness(configuration, bench):
    return CONFIRM_FRESHNESS[machinery_configuration(configuration, bench)]


def similar_pairs(configuration=PILOT):
    return SIMILAR_PAIRS_BY_CONFIGURATION.get(configuration, SIMILAR_PAIRS)


# v2.11 is copied only after every historical table has been fully constructed.
MAIN_V4_ROOT = '/data/execskill-20261029-main-v4'
MAIN_V4_MANIFEST = MAIN_V4_ROOT + '-manifest.json'
MAIN_V4_NAMESPACES = {'G': 'G-v4', 'D': 'D-v4'}


def is_v211(configuration):
    return configuration in (MAIN_V4, MAIN_V5)


def uses_readable_alf_format(configuration, bench):
    return bench == 'alfworld' and (is_v296(configuration) or is_v211(configuration))


def uses_episode_audit(configuration, bench):
    return bench == 'alfworld' and (is_v297(configuration) or is_v211(configuration))


def uses_pooled_j1(configuration, bench):
    return (is_v297(configuration) or (uses_v211(configuration, bench) and bench in BENCHES[:-1])
            or (uses_v212(configuration, bench) and bench == ZEBRA))


for _name, _table in list(globals().items()):
    if _name.isupper() and isinstance(_table, dict) and MAIN_V3 in _table:
        _table[MAIN_V4] = deepcopy(_table[MAIN_V3])
FEATURE_FAMILIES[MAIN_V4] = 'v2.9'
RUN_ROOTS[MAIN_V4] = MAIN_V4_ROOT
CHAIN_NAMESPACES[MAIN_V4] = MAIN_V4_NAMESPACES
SUPPORTED_NAMESPACES += tuple(MAIN_V4_NAMESPACES.values())
REAL_RUN_EVIDENCE[MAIN_V4] = 'main_v4_real_run'
ACCEPT_FRESHNESS[MAIN_V4] = 'v211_training_supply_historical_exposure_disclosed_accept_once_in_run'
CONFIRM_FRESHNESS[MAIN_V4] = 'v211_training_supply_disjoint_confirm_round_once_in_run'
ACCEPT_RULES[MAIN_V4]['name'] = 'practical-v2-11-pooled'
POLICY_VERSIONS[MAIN_V4] = POLICY_VERSION_V29
ENGINEER_RECORDS[MAIN_V4] = 'engineer-v2-11'
ENGINEER_CALL_BUDGETS[MAIN_V4] = 31
TRAIN_ENGINEER_CALL_BUDGETS[MAIN_V4] = 41
ENGINEER_MAX_TOKENS[MAIN_V4] = 32768

V211_SLICES = {
    'searchqa': {'run': (300, 1), 'accept': (1000, 1), 'blocks': 1},
    'officeqa': {'run': (18, 2), 'accept': (32, 4), 'blocks': 2},
    'livemath': {'run': (95, 1), 'accept': (100, 2), 'blocks': 1},
    'spreadsheetbench': {'run': (31, 2), 'accept': (36, 2), 'blocks': 1},
}


def slice_spec(configuration, bench):
    return deepcopy(V211_SLICES[bench] if uses_v211(configuration, bench) else SLICES[bench])


def confirm_spec(configuration, bench, round):
    require(type(round) is int and 1 <= round <= train_rounds(configuration, bench), 'Registered confirm round')
    if uses_v211(configuration, bench):
        require(bench in V211_SLICES, 'Only learned benchmarks have confirmation')
        return {'items': 40 if bench == 'searchqa' else 4, 'runs': 1, 'round': round,
                'selection_check': 'preregistered', 'freshness': confirm_freshness(configuration, bench)}
    return {'items': 40, 'runs': 1, 'round': round, 'freshness': confirm_freshness(configuration, bench)}


def audit_spec(configuration, bench):
    if uses_v211(configuration, bench) and bench in V211_SLICES:
        sheet = bench == 'spreadsheetbench'
        return {'base_items': 8 if sheet else 12, 'extra_items': 4,
                'batch_items': 2 if sheet else 4, 'max_batches': 6 if sheet else 4,
                'group_bytes': 64000 if sheet else 32000, 'request_bytes': 220000,
                'field_limits': {'question': 8000, 'context': 24000, 'choice': 2000, 'instruction': 8000,
                    'report_message': 2000, 'answer_cells': 100, 'qa_group_bytes': 32000,
                    'sheet_group_bytes': 64000, 'judge_input_bytes': 220000}}
    return {'base_items': 12 if bench == ZEBRA else 8, 'extra_items': 4,
            'batch_items': 4 if bench == ZEBRA else 6}


def engineer_prompt(configuration, bench, mode='single', purpose='propose'):
    require(mode in ('single', 'train'), 'Registered engineer mode')
    if uses_v211(configuration, bench):
        from . import engineer_v211
        return engineer_v211.system(bench, train=mode == 'train', purpose=purpose)
    from types import SimpleNamespace
    from . import engineer
    context = SimpleNamespace(configuration=machinery_configuration(configuration, bench), bench=bench, mode=mode)
    return engineer._legacy_system(context, {'request': purpose})


from . import v211_limits as _v211_limits
_v211_limits.extend(_sys.modules[__name__])


# v2.12: a single Zebra child; never extend the five-bench/ALF-only feature families.
def is_v212(configuration):
    return configuration in (ZEBRA_PC_V13, ZEBRA_PC_V14, ZEBRA_PC_V15)


ZEBRA_PC_V13_ROOT = '/data/execskill-20261030-zebra-pc-v13'
ZEBRA_PC_V13_MANIFEST = ZEBRA_PC_V13_ROOT + '-manifest.json'
ZEBRA_PC_V13_NAMESPACES = {'G': 'G-zpc13', 'D': 'D-zpc13'}
for _name, _table in list(globals().items()):
    if _name.isupper() and isinstance(_table, dict) and ZEBRA_PC_V12 in _table:
        _table[ZEBRA_PC_V13] = deepcopy(_table[ZEBRA_PC_V12])
RUN_ROOTS[ZEBRA_PC_V13] = ZEBRA_PC_V13_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V13] = ZEBRA_PC_V13_NAMESPACES
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V13_NAMESPACES.values())
REAL_RUN_EVIDENCE[ZEBRA_PC_V13] = 'zebra_pc_v13_real_run'
ACCEPT_FRESHNESS[ZEBRA_PC_V13] = 'zebra_split_v1_slices_accept_after_zebra_pc_v9_v12_and_upper_bound_probes'
CONFIRM_FRESHNESS[ZEBRA_PC_V13] = 'zebra_split_v1_confirm_after_zebra_pc_v9_v12'
ACCEPT_RULES[ZEBRA_PC_V13]['name'] = 'practical-v2-12-pooled'
PLACEBO_ARMS[ZEBRA_PC_V13] = TEST_WITHHOLDING[ZEBRA_PC_V13] = False
TEST_READ_CELLS[ZEBRA_PC_V13] = {ZEBRA: (200, 200)}
_v29_limits.extend_v212_profiles(_sys.modules[__name__])


# v2.13 is a fixed, post-hoc-selected import with no learning work.
def is_v213(configuration):
    return configuration == ZEBRA_HP_V3R4


def is_zebra_fc(configuration):
    return is_v212(configuration) or is_v213(configuration)


ZEBRA_HP_V3R4_ROOT = '/data/execskill-20261030-zebra-hp-v3r4'
ZEBRA_HP_V3R4_MANIFEST = ZEBRA_HP_V3R4_ROOT + '-manifest.json'
ZEBRA_HP_V3R4_NAMESPACES = {'G': 'G-zhp', 'D': 'D-zhp'}
for _name, _table in list(globals().items()):
    if _name.isupper() and isinstance(_table, dict) and ZEBRA_PC_V13 in _table:
        _table[ZEBRA_HP_V3R4] = deepcopy(_table[ZEBRA_PC_V13])
RUN_ROOTS[ZEBRA_HP_V3R4] = ZEBRA_HP_V3R4_ROOT
CHAIN_NAMESPACES[ZEBRA_HP_V3R4] = ZEBRA_HP_V3R4_NAMESPACES
SUPPORTED_NAMESPACES += tuple(ZEBRA_HP_V3R4_NAMESPACES.values())
REAL_RUN_EVIDENCE[ZEBRA_HP_V3R4] = 'zebra_hp_v3r4_test_read'
LEARNING[ZEBRA_HP_V3R4] = 'import'
ACCEPT_RULES[ZEBRA_HP_V3R4] = None
ACCEPT_FRESHNESS[ZEBRA_HP_V3R4] = 'not_applicable_fixed_post_hoc_v3r4_import'
CONFIRM_FRESHNESS[ZEBRA_HP_V3R4] = 'not_applicable_fixed_post_hoc_v3r4_import'
ENGINEER_CALL_BUDGETS[ZEBRA_HP_V3R4] = TRAIN_ENGINEER_CALL_BUDGETS[ZEBRA_HP_V3R4] = 0
CONFIG_STEP_CAPS[ZEBRA_HP_V3R4] = {}
CONFIG_SCHEDULE_CELLS[ZEBRA_HP_V3R4] = {}
CONFIG_ROLE_CAPS[ZEBRA_HP_V3R4] = {role: 0 for role in CONFIG_ROLE_CAPS[ZEBRA_PC_V13]}
CONFIG_GLM_CAP[ZEBRA_HP_V3R4] = 0
CONFIGURATIONS[ZEBRA_HP_V3R4]['redo_reserve'] = 0
# Reserve the complete read cap plus only the existing first-call subcap.
CONFIGURATIONS[ZEBRA_HP_V3R4]['solver_cap'] = CONFIGURATIONS[ZEBRA_HP_V3R4]['test_read_cap'] + FIRST_CALL_CAP


# v2.14 composes the finalized main-v4 and zebra-pc-v13 registrations by value.
MAIN_V5_ROOT = '/data/execskill-20261031-main-v5'
MAIN_V5_MANIFEST = MAIN_V5_ROOT + '-manifest.json'
MAIN_V5_NAMESPACES = {'G': 'G-v5', 'D': 'D-v5'}
MAIN_V5_ORDER = ('searchqa', 'officeqa', ZEBRA, 'spreadsheetbench', 'alfworld')
MAIN_V5_TEST_ITEMS = {'searchqa': 400, 'officeqa': 172, ZEBRA: 200,
                      'spreadsheetbench': 279, 'alfworld': 134}
# Owner decision main_v5_similarity: Zebra and ALFWorld have no related benchmark.
SIMILAR_PAIRS_BY_CONFIGURATION = {MAIN_V5: (('searchqa', 'officeqa'),
                                           ('officeqa', 'spreadsheetbench'))}
for _name, _table in list(globals().items()):
    if _name.isupper() and isinstance(_table, dict) and MAIN_V4 in _table:
        _table[MAIN_V5] = deepcopy(_table[MAIN_V4])
CONFIGURATIONS[MAIN_V5]['order'] = MAIN_V5_ORDER
RUN_ROOTS[MAIN_V5] = MAIN_V5_ROOT
CHAIN_NAMESPACES[MAIN_V5] = MAIN_V5_NAMESPACES
SUPPORTED_NAMESPACES += tuple(MAIN_V5_NAMESPACES.values())
REAL_RUN_EVIDENCE[MAIN_V5] = 'main_v5_real_run'
STAGE_READ[MAIN_V5] = True
PLACEBO_ARMS[MAIN_V5] = TEST_WITHHOLDING[MAIN_V5] = False
for _name in ('CONFIG_STEP_CAPS', 'CONFIG_SCHEDULE_CELLS'):
    globals()[_name][MAIN_V5] = {
        bench: deepcopy(globals()[_name][machinery_configuration(MAIN_V5, bench)][bench])
        for bench in MAIN_V5_ORDER[:-1]}
# The single-benchmark Zebra parent has no earlier generated sets. Main-v5's
# third step inherits main-v4's step-3 predecessor cells: OfficeQA's two arms,
# 40 items and two self-test passes. SearchQA generates no G_self set.
_main_v5_zebra_selftest = CONFIG_SCHEDULE_CELLS[MAIN_V5][ZEBRA]['selftest']
_main_v4_step3_selftest = CONFIG_SCHEDULE_CELLS[MAIN_V4]['livemath']['selftest']
for _bench in MAIN_V5_ORDER[:MAIN_V5_ORDER.index(ZEBRA)]:
    if _bench in _main_v4_step3_selftest:
        _main_v5_zebra_selftest[_bench] = deepcopy(_main_v4_step3_selftest[_bench])
CONFIG_STEP_CAPS[MAIN_V5][ZEBRA]['selftest'] = legacy._round_up(MAIN_CAP_FACTOR * (
    sum(CELL_ANCHORS[b][1] * (card + PROCEDURE_ARM_FACTOR[1] * proc)
        for b, (card, proc) in _main_v5_zebra_selftest.items())
    + MAIN_RESERVATIONS * READ_RESERVATION), 100_000)
# Zebra has no generated G_self set, so the removed LiveMath predecessor contributes
# no SpreadsheetBench self-test cells. Preserve the parent's step cap as headroom.
CONFIG_SCHEDULE_CELLS[MAIN_V5]['spreadsheetbench']['selftest'].pop('livemath')
TEST_READ_CELLS[MAIN_V5] = {b: (2 * n, 5 * n) for b, n in MAIN_V5_TEST_ITEMS.items()}
_main_v5_read_tokens = sum(CELL_ANCHORS[b][1] * (c + PROCEDURE_ARM_FACTOR[1] * q)
                           for b, (c, q) in TEST_READ_CELLS[MAIN_V5].items())
CONFIGURATIONS[MAIN_V5]['test_read_cap'] = legacy._round_up(MAIN_CAP_FACTOR * (
    _main_v5_read_tokens + len(MAIN_V5_ORDER) * MAIN_RESERVATIONS * READ_RESERVATION), MILLION)
CONFIGURATIONS[MAIN_V5]['solver_cap'] = legacy._round_up(
    sum(sum(row.values()) for row in CONFIG_STEP_CAPS[MAIN_V5].values())
    + CONFIGURATIONS[MAIN_V5]['test_read_cap'] + CONFIGURATIONS[MAIN_V5]['redo_reserve'], 5 * MILLION)
# Preserve parent aggregate headroom while replacing only the LiveMath method step.
CONFIG_GLM_CAP[MAIN_V5] = (CONFIG_GLM_CAP[MAIN_V4] - sum(_v211_limits.role_caps('livemath').values())
                         + CONFIG_GLM_CAP[ZEBRA_PC_V13])


def main_v5_identity():
    """Preregistered mixed method, worst read and existing G-Zebra route pins."""
    return {'configuration': MAIN_V5, 'order': MAIN_V5_ORDER,
            'machinery': {b: machinery_configuration(MAIN_V5, b) for b in MAIN_V5_ORDER},
            'similarity': {'name': 'main_v5_similarity', 'pairs': similar_pairs(MAIN_V5)},
            'stage_timing': 'main_v5_stage_timing_chain_end_after_both_chains',
            'freshness': {b: {'accept': accept_freshness(MAIN_V5, b),
                              'confirm': confirm_freshness(MAIN_V5, b)} for b in MAIN_V5_ORDER},
            'acceptance_rules': {b: acceptance_rule(MAIN_V5, b) for b in MAIN_V5_ORDER[:-1]},
            'read_items': MAIN_V5_TEST_ITEMS, 'read_cells': TEST_READ_CELLS[MAIN_V5],
            'read_arms': read_arms_of(MAIN_V5), 'stage_arms_max': stage_arms_max(MAIN_V5),
            'fired_shares': {b: fired_share(b, MAIN_V5) for b in MAIN_V5_ORDER},
            'read_formula': 'ratio * sum(n_b * (2*card_b + (1+4*f_b)*procedure_b))',
            'read_logical_cells_per_chain': 8295, 'read_base_cells_per_chain': 3555,
            'zebra_blank_shared_cells_per_chain': 200, 'scope_caps': CONFIG_STEP_CAPS[MAIN_V5],
            'caps': {**CONFIGURATIONS[MAIN_V5], 'method': CONFIG_GLM_CAP[MAIN_V5]},
            'glm_zebra': {'model': CHAINS['G'], 'max_tokens': solver_tokens(CHAINS['G'], ZEBRA),
                          'read_timeout': read_timeout(CHAINS['G'], ZEBRA),
                          'branch': None, 'longest': None, 'nominal_M': None,
                          'ledger_bound': ledger_bound(CHAINS['G'], ZEBRA)}}


# v2.15 adds only an engineer diagnostics channel to the finalized Zebra v13 method.
ZEBRA_PC_V14_ROOT = '/data/execskill-20261031-zebra-pc-v14'
ZEBRA_PC_V14_MANIFEST = ZEBRA_PC_V14_ROOT + '-manifest.json'
ZEBRA_PC_V14_NAMESPACES = {'G': 'G-zpc14', 'D': 'D-zpc14'}
ZEBRA_PC_V14_TEST_FRESHNESS = 'zebra_split_v1_holdout_after_one_zebra_hp_v3r4_v213_read'
for _name, _table in list(globals().items()):
    if _name.isupper() and isinstance(_table, dict) and ZEBRA_PC_V13 in _table:
        _table[ZEBRA_PC_V14] = deepcopy(_table[ZEBRA_PC_V13])
RUN_ROOTS[ZEBRA_PC_V14] = ZEBRA_PC_V14_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V14] = ZEBRA_PC_V14_NAMESPACES
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V14_NAMESPACES.values())
REAL_RUN_EVIDENCE[ZEBRA_PC_V14] = 'zebra_pc_v14_real_run'
ACCEPT_FRESHNESS[ZEBRA_PC_V14] = (
    'zebra_split_v1_accept_after_zebra_pc_v9_v10_v11_v12_v13_upper_bound_probes_and_main_v5_D')
CONFIRM_FRESHNESS[ZEBRA_PC_V14] = (
    'zebra_split_v1_confirm_after_zebra_pc_v9_v10_v11_v12_v13_and_main_v5_D')
_old_v215_engineer_cap = CONFIG_ROLE_CAPS[ZEBRA_PC_V14]['engineer']
CONFIG_ROLE_CAPS[ZEBRA_PC_V14]['engineer'] = _v29_limits.v291_engineer_cap(_sys.modules[__name__], ZEBRA_PC_V14)
CONFIG_GLM_CAP[ZEBRA_PC_V14] += CONFIG_ROLE_CAPS[ZEBRA_PC_V14]['engineer'] - _old_v215_engineer_cap


# v2.16 extends only the per-change repair cycle of the finalized Zebra v14.
ZEBRA_PC_V15_ROOT = '/data/execskill-20261031-zebra-pc-v15'
ZEBRA_PC_V15_MANIFEST = ZEBRA_PC_V15_ROOT + '-manifest.json'
ZEBRA_PC_V15_NAMESPACES = {'G': 'G-zpc15', 'D': 'D-zpc15'}
ZEBRA_PC_V15_TEST_FRESHNESS = ZEBRA_PC_V14_TEST_FRESHNESS
for _name, _table in list(globals().items()):
    if _name.isupper() and isinstance(_table, dict) and ZEBRA_PC_V14 in _table:
        _table[ZEBRA_PC_V15] = deepcopy(_table[ZEBRA_PC_V14])
RUN_ROOTS[ZEBRA_PC_V15] = ZEBRA_PC_V15_ROOT
CHAIN_NAMESPACES[ZEBRA_PC_V15] = ZEBRA_PC_V15_NAMESPACES
SUPPORTED_NAMESPACES += tuple(ZEBRA_PC_V15_NAMESPACES.values())
REAL_RUN_EVIDENCE[ZEBRA_PC_V15] = 'zebra_pc_v15_real_run'
ACCEPT_FRESHNESS[ZEBRA_PC_V15] = ACCEPT_FRESHNESS[ZEBRA_PC_V14] + '_and_zebra_pc_v14'
CONFIRM_FRESHNESS[ZEBRA_PC_V15] = CONFIRM_FRESHNESS[ZEBRA_PC_V14] + '_and_zebra_pc_v14'
_extra_v216_repairs = MAX_CHANGES * (V216_INERT_REPAIRS - INERT_REPAIRS + V216_AUDIT_FIXES - 1)
ENGINEER_CALL_BUDGETS[ZEBRA_PC_V15] += _extra_v216_repairs
TRAIN_ENGINEER_CALL_BUDGETS[ZEBRA_PC_V15] += _extra_v216_repairs
_v29_limits.extend_v216_profiles(_sys.modules[__name__])
