"""Explicit experiment extensions; frozen five-benchmark protocol tables remain readable unchanged.

Production consumers use this registry. ``protocol`` remains the historical registration,
including its iterable rosters (and therefore its historical identity serialization).
"""
from __future__ import annotations

from copy import deepcopy

from .protocol import *  # re-export the historical vocabulary, without mutating its tables
from . import protocol as legacy
from .policy import POLICY_VERSION_V24, POLICY_VERSION_V25

ZEBRA_PC_V1 = "zebra-pc-v1"
ZEBRA_PC_V2 = "zebra-pc-v2"
ZEBRA_PC_V3 = "zebra-pc-v3"
ZEBRA_PC_V4 = "zebra-pc-v4"
ZEBRA_PC_V5 = "zebra-pc-v5"
ALFWORLD_V1 = "alfworld-v1"
ALFWORLD_V2 = "alfworld-v2"
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


def is_v23(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.3", "v2.4", "v2.5", "v2.6", "v2.7")


def is_v24(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.4", "v2.5", "v2.6", "v2.7")


def is_v25(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.5", "v2.6", "v2.7")


def is_v26(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.6", "v2.7")


def is_v27(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] == "v2.7"


def is_zebra(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (ZEBRA_PC_V1, ZEBRA_PC_V2, ZEBRA_PC_V3, ZEBRA_PC_V4, ZEBRA_PC_V5)


def is_alfworld(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (ALFWORLD_V1, ALFWORLD_V2)


def is_alfworld_v2(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration == ALFWORLD_V2


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


def launchable_chains(configuration):
    require(configuration in CONFIGURATIONS, "Unknown run configuration")
    return ("D",) if is_alfworld(configuration) or is_v27(configuration) else tuple(CHAINS)


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
    return TEST_ARMS + ((STAGES,) if STAGE_READ[configuration] else ())


def estimate_arms(configuration):
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
    if is_alfworld(pilot):
        require(bench == "alfworld", "Only the registered ALFWorld panel")
        return FIRED_SHARES["home"]
    if not is_zebra(pilot):
        return legacy.fired_share(bench, pilot)
    require(bench == ZEBRA, "Only the registered ZebraLogic panel")
    return Fraction(1)


def read_estimate_terms(per_cell, ratio, pilot=PILOT):
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
