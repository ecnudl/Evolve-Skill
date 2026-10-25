"""Explicit experiment extensions; frozen five-benchmark protocol tables remain readable unchanged.

Production consumers use this registry. ``protocol`` remains the historical registration,
including its iterable rosters (and therefore its historical identity serialization).
"""
from __future__ import annotations

from copy import deepcopy

from .protocol import *  # re-export the historical vocabulary, without mutating its tables
from . import protocol as legacy
from .policy import POLICY_VERSION_V24

ZEBRA_PC_V1 = "zebra-pc-v1"
ZEBRA_PC_V2 = "zebra-pc-v2"
ZEBRA = "zebralogic"
SUPPORTED_BENCHES = BENCHES + (ZEBRA,)
FEATURE_FAMILIES = {name: ("v2.3" if name == MAIN_V2_3 else "historical") for name in CONFIGURATIONS}
FEATURE_FAMILIES[ZEBRA_PC_V1] = "v2.3"
FEATURE_FAMILIES[ZEBRA_PC_V2] = "v2.4"


def is_v23(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] in ("v2.3", "v2.4")


def is_v24(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return FEATURE_FAMILIES[configuration] == "v2.4"


def is_zebra(configuration):
    configuration = configuration or PILOT
    require(configuration in FEATURE_FAMILIES, "Unknown run configuration")
    return configuration in (ZEBRA_PC_V1, ZEBRA_PC_V2)


def _extend(table, value, *, v2=None):
    return {**table, ZEBRA_PC_V1: value, ZEBRA_PC_V2: deepcopy(value if v2 is None else v2)}


ZEBRA_PC_ROOT = "/data/execskill-20261025-zebra-pc-v1"
ZEBRA_PC_MANIFEST = "/data/execskill-20261025-zebra-pc-v1-manifest.json"
ZEBRA_PC_NAMESPACES = {"G": "G-zpc1", "D": "D-zpc1"}
ZEBRA_PC_V2_ROOT = "/data/execskill-20261025-zebra-pc-v2"
ZEBRA_PC_V2_MANIFEST = "/data/execskill-20261025-zebra-pc-v2-manifest.json"
ZEBRA_PC_V2_NAMESPACES = {"G": "G-zpc2", "D": "D-zpc2"}
SUPPORTED_NAMESPACES = NAMESPACES + tuple(ZEBRA_PC_NAMESPACES.values()) + tuple(ZEBRA_PC_V2_NAMESPACES.values())
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
REAL_RUN_EVIDENCE = _extend(REAL_RUN_EVIDENCE, "zebra_pc_v1_real_run", v2="zebra_pc_v2_real_run")
RUN_ROOTS = _extend(RUN_ROOTS, ZEBRA_PC_ROOT, v2=ZEBRA_PC_V2_ROOT)
CHAIN_NAMESPACES = _extend(CHAIN_NAMESPACES, ZEBRA_PC_NAMESPACES, v2=ZEBRA_PC_V2_NAMESPACES)
TEST_READ_CELLS = _extend(TEST_READ_CELLS, {ZEBRA: (200, 1_000)})
STAGE_READ = _extend(STAGE_READ, False)  # one step has no intermediate stage
ACCEPT_FRESHNESS = _extend(ACCEPT_FRESHNESS, "zebra_split_v1_slices_first_use_probe_items_excluded",
                           v2="zebra_split_v1_slices_reused_zpc1_acceptance_unused")
for _name in ("LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES",
              "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
              "ENGINEER_RECORDS", "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION",
              "MULTIPLE_PYTHON_BLOCKS"):
    _old = getattr(legacy, _name)
    globals()[_name] = _extend(_old, _old[MAIN_V2_3])
ENGINEER_RECORDS[ZEBRA_PC_V2] = "engineer-v2-4"
POLICY_VERSIONS[ZEBRA_PC_V2] = POLICY_VERSION_V24


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
    return (ZEBRA,) if is_zebra(configuration) else BENCHES


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
    if not is_zebra(pilot):
        return legacy.fired_share(bench, pilot)
    require(bench == ZEBRA, "Only the registered ZebraLogic panel")
    return Fraction(1)


def read_estimate_terms(per_cell, ratio, pilot=PILOT):
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
