"""Protocol identity and registered constants of fivebench-execskill-v1 (implementation plan §8: T-ID-1, T-ID-2;
registration §1, §3, §4.1, §6.4, §9.3; calc output T6, T7, T10, T11). Offline and deterministic."""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import math
import re
from fractions import Fraction
from pathlib import Path

import pytest

import scripts.weak_solver_probe as probe
from skillopt.coevo5 import cells, ledger, outcomes
from skillopt.coevo5 import protocol as v3
from skillopt.coevolution_v5.core import seal
from skillopt.execskill import VERSION, client, errors, exclusion, policy, protocol, registry, supply
from skillopt.execskill.errors import (AssumptionBroken, BudgetStop, CleanupUnconfirmed, ConfigurationError,
                                       ConsumptionConflict, LedgerFailure, PackageInvalid, SandboxUnavailable,
                                       stop_kind)
from skillopt.validator_pilot.api import digest

PACKAGE = Path(protocol.__file__).resolve().parent
# the registration's zero-call arithmetic (appendix A): in the build tree, and beside it when a snapshot holds only
# skillopt/, scripts/ and tests/ (plan §10 step 1); pinned by its sha256
CALC_NAME = "docs/handoff/execskill-calc-20261021.py"
CALC_SHA256 = "d4d8a81e36548902b364c30f5cc34d8d773bc38757d4af615a10746df886bb51"
FROZEN = ("AssumptionBroken", "BudgetStop", "CleanupUnconfirmed", "ConfigurationError", "LedgerFailure")
M = 1_000_000


def _sources():
    return sorted(PACKAGE.rglob("*.py"))


# ---------------------------------------------------------------------------------------------------- T-ID-1
def test_t_id_1_one_exception_set_reexported_unchanged():
    for name in FROZEN:
        assert getattr(errors, name) is getattr(outcomes, name)
    for path in _sources():
        defined = {node.name for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.ClassDef)}
        assert not defined & set(FROZEN), path


def test_t_id_1_stop_kinds_extend_the_frozen_table():
    assert {k: v for k, v in errors.STOP_KINDS.items() if k in cells.STOP_KINDS} == cells.STOP_KINDS
    assert {errors.STOP_KINDS[c] for c in (SandboxUnavailable, PackageInvalid, ConsumptionConflict)} == {
        "sandbox", "package", "consumption"}
    assert len(set(errors.STOP_KINDS.values())) == len(errors.STOP_KINDS) == 9  # + route B's balance_exhausted (M4)
    raised = [BudgetStop("budget_stop:D:solver"), AssumptionBroken("ledger_halted:x"), LedgerFailure("x"),
              ConfigurationError("x"), CleanupUnconfirmed("x"), SandboxUnavailable("x"), PackageInvalid("x"),
              ConsumptionConflict("x"), errors.BalanceExhausted("x")]
    expected = ["budget", "assumption", "ledger", "configuration", "cleanup", "sandbox", "package", "consumption",
                "balance_exhausted"]
    # the frozen cell runner's exact-type lookup (cells.py:215-216) and the subclass-aware one agree
    assert [errors.STOP_KINDS[type(exc)] for exc in raised] == expected == [stop_kind(exc) for exc in raised]
    assert stop_kind(ValueError("x")) is None and stop_kind(RuntimeError("x")) is None
    assert issubclass(PackageInvalid, ValueError) and issubclass(SandboxUnavailable, RuntimeError)
    assert issubclass(ConsumptionConflict, RuntimeError)


# ---------------------------------------------------------------------------------------------------- T-ID-2
def test_t_id_2_kind_and_record_stamp():
    assert VERSION == "fivebench-execskill-v1" and protocol.kind("decision") == "fivebench-execskill-v1-decision"
    for bad in ("", "Decision", "a b", "-x", "x-", "x--y", "x:y", None, 3):
        with pytest.raises(ValueError):
            protocol.kind(bad)
    value = protocol.record("decision", "pilot_real_run", {"unit": "D/officeqa/2", "accepted": False})
    assert value["version"] == "fivebench-execskill-v1-decision" and value["evidence"] == "pilot_real_run"
    assert value["record_sha256"] == digest({k: v for k, v in value.items() if k != "record_sha256"})
    assert protocol.verified(value, "decision") == value and protocol.verified(value) == value
    with pytest.raises(ValueError):
        protocol.verified(value, "supply")
    with pytest.raises(ValueError):
        protocol.verified({**value, "accepted": True})
    with pytest.raises(ValueError):
        protocol.record("decision", "pilot", {})
    with pytest.raises(ValueError):
        protocol.record("decision", "smoke", {"version": "x"})
    v3_record = seal({"version": "fivebench-coevolution-v3-decision", "evidence": "smoke"}, field="record_sha256")
    with pytest.raises(ValueError):
        protocol.verified(v3_record)
    unknown = seal({"version": protocol.kind("decision"), "evidence": "guess"}, field="record_sha256")
    with pytest.raises(ValueError):
        protocol.verified(unknown)


def test_t_id_2_no_v3_identity_in_the_package():
    importable = set(protocol.IMPORTABLE) | {protocol.TEXTS_IMPORT}
    for path in _sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("skillopt.coevo"):
                assert "VERSION" not in {alias.name for alias in node.names}, path
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and re.fullmatch(r"fivebench-[a-z0-9.-]+", node.value):
                assert node.value.startswith(VERSION) or node.value in importable, (path, node.value)
    assert all(name.startswith("fivebench-coevolution-v3-") for name in importable)


# ------------------------------------------------------------------------------------- constants vs frozen code
def test_constants_transcribed_from_the_frozen_route():
    assert protocol.GLM_SOLVER_TOKENS == v3.SOLVER_MAX_TOKENS["glm-5.3"]
    assert protocol.GLM_READ_TIMEOUT == v3.READ_TIMEOUT_SECONDS
    assert {name: protocol.SLOTS[name] for name in ("glm-5.3", "spreadsheet-native", "alfworld-episode")} == {
        name: v3.SLOTS[name] for name in ("glm-5.3", "spreadsheet-native", "alfworld-episode")}
    assert (protocol.ROLE_MODEL, protocol.ROLE_MAX_TOKENS, protocol.ROLE_READ_TIMEOUT, protocol.ROLE_INPUT_BYTES) == (
        v3.ROLE_MODEL, v3.ROLE_MAX_TOKENS, v3.ROLE_READ_TIMEOUT_SECONDS, v3.ROLE_INPUT_BYTES)
    assert (protocol.RESEARCH_MAX_ROUNDS, protocol.RESEARCH_MAX_QUERIES, protocol.RESEARCH_MAX_PAGES,
            protocol.RESEARCH_MAX_CALLS) == (v3.RESEARCH_MAX_ROUNDS, v3.RESEARCH_MAX_QUERIES, v3.RESEARCH_MAX_PAGES,
                                             v3.RESEARCH_MAX_CALLS) == (3, 3, 3, 8)
    assert protocol.GATEWAY == probe.GATEWAY
    assert probe.MODELS["glm-5.3"][3] == protocol.GLM_SOLVER_TOKENS
    assert protocol.ALFWORLD_MAX_STEPS == v3.RUNTIME["alfworld"]["max_steps"] == 50
    assert protocol.ALFWORLD_ENV_SEED == v3.RUNTIME["alfworld"]["seed"] == 42
    assert protocol.LIVEMATH_META_OPTION == v3.STRONGER_OPTION == policy.STRONGER_OPTION
    assert protocol.PLACEBO_CORPUS == v3.PLACEBOS_SCREEN + v3.PLACEBOS_CONFIRM and len(protocol.PLACEBO_CORPUS) == 8
    assert len(set(protocol.PLACEBO_CORPUS)) == 8 and re.fullmatch(r"[0-9a-f]{64}", protocol.PLACEBO_CORPUS_SHA256)
    assert protocol.BENCHES == v3.ORDER == policy.BENCHES


def test_sibling_copies_agree_with_the_registration():
    # ticket A2-1: the solver names and settings the client dispatches on
    assert set(protocol.SOLVERS) == set(client.CONFIG_KEYS)
    assert protocol.CHAINS == {"G": client.GLM_SOLVER, "D": client.ELUCID_MODEL}
    assert client.ELUCID_RESPONSE_MODEL_IDS == frozenset({protocol.SMOKE_SOLVER}) == frozenset({protocol.CHAINS["D"]})
    assert client.REASONING_EFFORT == protocol.REASONING_EFFORT == "none"
    # ticket A4-1 and the policy's own copies
    assert set(registry.NAMESPACES) == set(protocol.CHAINS) | {"smoke"}
    assert registry.HISTORY_ROOT == protocol.HISTORY_ROOT == "/data/execskill-history"
    assert set(registry.EVIDENCE) == set(protocol.EVIDENCE)
    assert exclusion.EXCLUSION_RUNS == protocol.EXCLUSION_RUNS
    assert policy.MAX_SOURCE_BYTES == protocol.MAX_PROCEDURE_BYTES == 6000
    assert policy.MAX_CONSTANT_CHARS == protocol.MAX_CONSTANT_CHARS == 2000
    assert supply.REGISTERED_ROOMS == sum(protocol.ROOM_GROUPS.values()) == 108


# ------------------------------------------------------------------------------------- registered data and solvers
def test_registered_tags_and_seeds():
    assert protocol.SEED == 20261021 and protocol.ROOMS_TAG == "execskill-v1:rooms"
    assert protocol.order_tag("officeqa") == "execskill-v1:order:officeqa"
    assert protocol.round_tag("D-officeqa-2") == "execskill-v1:round:D-officeqa-2"
    assert protocol.detsplit_tag("u") == "execskill-v1:detsplit:u"
    assert protocol.withhold_tag("u", "p-officeqa-2-1") == "execskill-v1:withhold:u:p-officeqa-2-1"
    assert protocol.yoke_tag("u") == "execskill-v1:yoke:u"
    assert protocol.discourage_tag("u", "c7") == "execskill-v1:discourage:u:c7"
    assert protocol.research_split_tag("u") == "execskill-v1:research-split:u"
    expected = int(hashlib.sha256(b"execskill-v1:gen:g-officeqa-2-1:2").hexdigest()[:8], 16)
    assert protocol.generator_seed("g-officeqa-2-1", "2") == expected
    for bad in (("a:b",), ("",), ("a b",), (2,)):
        with pytest.raises(ValueError):
            protocol.round_tag(*bad)
    with pytest.raises(ValueError):
        protocol.order_tag("bfcl")


def test_registered_slices_and_smoke_items():
    assert protocol.ORDER == ("spreadsheetbench", "officeqa") and protocol.PILOT == "default"
    assert protocol.PILOTS["recommended"]["order"] == ("spreadsheetbench", "alfworld")
    assert sum(protocol.ROOM_GROUPS.values()) == 108 and protocol.ROOM_GROUPS["spare"] == 28
    assert sum(protocol.PRERESET_GAMES.values()) == 422
    assert protocol.PRERESET_GAMES["smoke"] == sum(protocol.SMOKE_REAL_ITEMS["alfworld"].values()) == 12
    assert sum(protocol.SMOKE_REAL_ITEMS["searchqa"].values()) == 280
    assert sum(protocol.S4_SLICES.values()) == protocol.SMOKE_REAL_ITEMS["searchqa"]["S4"]
    assert sum(protocol.LIVEMATH_RUN.values()) == protocol.SLICES["livemath"]["run"][0] == 119
    for bench in ("spreadsheetbench", "officeqa", "livemath"):
        assert protocol.G_ACC[bench] == protocol.SLICES[bench]["accept"][0]  # one generated item per A* item
    assert protocol.G_ACC["alfworld"] == protocol.G_ACC["searchqa"] == 0
    # §3.3: SB needs A* to be at least half of its 60 acceptance items, OQ at least 60 % of its 50
    assert Fraction(protocol.MIN_ASTAR, protocol.SLICES["spreadsheetbench"]["accept"][0]) == Fraction(1, 2)
    assert Fraction(protocol.MIN_ASTAR, protocol.SLICES["officeqa"]["accept"][0]) == Fraction(3, 5)
    assert protocol.ALFWORLD_ID_PREFIX == "alfworld-xs:" and protocol.ALFWORLD_ID_HEX == 16
    assert (protocol.SEARCHQA_FRESH_SEED, protocol.SEARCHQA_TAIL_START) == ("searchqa-fresh-20261012", 4001)


def test_solver_settings_and_ledger_bound():
    glm, deepseek = protocol.CHAINS["G"], protocol.CHAINS["D"]
    for bench in protocol.BENCHES:
        assert protocol.solver_tokens(glm, bench) == protocol.ledger_bound(glm, bench) == 65_536
        assert protocol.read_timeout(glm, bench) == 2_400
        nominal = protocol.solver_tokens(deepseek, bench)
        assert protocol.ledger_bound(deepseek, bench, branch="E") == 2 * nominal
        assert protocol.ledger_bound(deepseek, bench, branch="N", longest=10) == 4 * nominal
        assert protocol.ledger_bound(deepseek, bench, branch="N", longest=4 * nominal) == 6 * nominal
        assert protocol.ledger_bound(deepseek, bench, branch="N", longest=4 * nominal + 1) == 6 * nominal + 2
    assert [protocol.read_timeout(deepseek, b) for b in protocol.BENCHES] == [600, 600, 600, 900, 180]
    assert [protocol.solver_tokens(deepseek, b) for b in protocol.BENCHES] == [8192, 8192, 8192, 16384, 1024]
    for bad in ({"branch": None}, {"branch": "E", "longest": 5}, {"branch": "N"}, {"branch": "N", "longest": 0}):
        with pytest.raises(ValueError):
            protocol.ledger_bound(deepseek, "officeqa", **bad)
    with pytest.raises(ValueError):
        protocol.ledger_bound(glm, "officeqa", branch="E")
    with pytest.raises(ValueError):
        protocol.solver_tokens("deepseek-v4-flash", "officeqa")


# --------------------------------------------------------------------------------------- J3/J4 (calc T10)
@pytest.mark.parametrize("items, faults, margins", [
    (60, 1, {30: 2, 60: 2}), (50, 1, {30: 2, 50: 2}), (150, 3, {30: 2, 75: 2, 150: 3}),
    (100, 2, {30: 2, 50: 2, 100: 2}), (1000, 20, {30: 2, 500: 10, 1000: 20})])
def test_j3_j4_boundaries_match_calc_t10(items, faults, margins):
    assert protocol.fault_items_max(items) == faults
    assert {astar: protocol.format_margin(astar) for astar in margins} == margins
    assert protocol.format_margin(101) == 3 and protocol.format_margin(100) == 2


# ------------------------------------------------------------------------------------------ caps (calc T6, T11)
HIGH = {  # calc T6: the maximum-schedule high estimates, M tokens (two decimals)
    "spreadsheetbench": {"run": 0.42, "examiner": 1.97, "selftest": 1.33, "accept": 5.13},
    "officeqa": {"run": 1.22, "examiner": 4.55, "selftest": 4.14, "accept": 19.34},
    "alfworld": {"run": 8.64, "examiner": 6.48, "selftest": 12.61, "accept": 60.75},
}
REQUEST_BYTES = {"spreadsheetbench": 64_000, "officeqa": 64_000, "alfworld": 32_000}  # calc T6 [A]


def _ceil(value, step):
    return math.ceil(round(value / step, 9)) * step


def test_step_caps_follow_the_registered_rule():
    deepseek = protocol.CHAINS["D"]
    bound = {bench: protocol.ledger_bound(deepseek, bench, branch="N", longest=1) for bench in REQUEST_BYTES}
    full = {bench: ledger.reservation(REQUEST_BYTES[bench], bound[bench]) for bench in REQUEST_BYTES}
    assert full == {"spreadsheetbench": 520_192, "officeqa": 389_120, "alfworld": 146_432}
    for bench, kinds in protocol.STEP_CAPS.items():
        for kind, cap in kinds.items():
            needed = 1.5 * HIGH[bench][kind] * M + full[bench]
            assert 0 <= cap - needed <= 0.1 * M + 1.5 * 0.005 * M, (bench, kind)
            assert cap % 100_000 == 0
    sums = {bench: sum(kinds.values()) for bench, kinds in protocol.STEP_CAPS.items()}
    assert sums == {"spreadsheetbench": 15_600_000, "officeqa": 45_700_000, "alfworld": 133_500_000}


def test_pilot_caps_add_up():
    for name, expected in (("default", 175_100_000), ("recommended", 298_000_000)):
        plan = protocol.PILOTS[name]
        steps = sum(sum(protocol.STEP_CAPS[bench].values()) for bench in plan["order"])
        block = max(protocol.STEP_CAPS[bench]["accept"] / protocol.SLICES[bench]["blocks"] for bench in plan["order"])
        assert plan["redo_reserve"] == _ceil(block, 100_000)
        assert steps + plan["test_read_cap"] + plan["redo_reserve"] == expected
        assert plan["solver_cap"] == _ceil(expected, 5 * M)
    roles = sum(protocol.ROLE_CAPS.values())  # registrar addendum 2026-10-22, R7b: 8.6M -> 10.1M per step
    assert protocol.ROLE_CAPS == {"engineer": 2_500_000, "examiner": 3_000_000, "examiner_research": 4_600_000}
    assert roles == 10_100_000 and 2 * roles <= protocol.GLM_CAP == 30 * M
    option = protocol.OPTION_PI_ALFWORLD
    assert option["redo_reserve"] == _ceil(option["accept"] / protocol.SLICES["alfworld"]["blocks"], 100_000)
    assert protocol.TEST_START_FACTOR * 54_400_000 <= protocol.PILOTS["default"]["test_read_cap"]
    assert protocol.TEST_START_FACTOR * 68_700_000 <= protocol.PILOTS["recommended"]["test_read_cap"]
    assert protocol.SMOKE_CAPS == {"solver": 14 * M, "glm": 2 * M} and protocol.PROBE_CAP == 500_000


# ------------------------------------------------------------------------------------------ templates and lexicon
def _hits(text, bench):
    hits = []
    for term in protocol.LEXICON[bench]:
        pattern = r"\b%s\b" % re.escape(term) if term[0].isalpha() and term[-1].isalpha() else re.escape(term)
        if re.search(pattern, text, re.I):
            hits.append(term)
    return hits


def test_templates_carry_no_format_instruction():
    for bench in protocol.BENCHES:
        for text in [*protocol.NOTE_HEADERS.values(), protocol.NOT_RECOMMENDED_PREFIX]:
            assert not _hits(text, bench), (bench, text)
            assert len(text) <= protocol.MAX_HEADER_CHARS
    assert not _hits(protocol.REPAIR_FRAME, "spreadsheetbench")
    assert "format" in protocol.LEXICON["officeqa"] and "format" not in protocol.LEXICON["spreadsheetbench"]
    assert set(protocol.NOTE_HEADERS) == {"facts", "table", "candidates", "warnings", "bindings"}
    assert set(protocol.TEMPLATES_SHA256) == set(protocol.TEMPLATES)
    assert protocol.MAX_NOTE_CHARS == {"searchqa": 4000, "officeqa": 4000, "livemath": 4000,
                                       "spreadsheetbench": 4000, "alfworld": 1500}


# --------------------------------------------- tickets A10-1, C1-1, A9-3 (registrar decision 2026-10-22): moved by value
def test_moved_constants_equal_their_module_twins():
    """The constants moved into protocol.py equal the modules' own (and stay equal once the modules import them), so
    the integrator's import switch in replay.py, engineer.py, describer.py and examiner.py changes no value."""
    from skillopt.execskill import describer, engineer, examiner, package, replay
    twins = [(replay, "TRACKER_AGREEMENT", "TRACKER_AGREEMENT"), (replay, "STATE_FACTS", "STATE_FACTS"),
             (replay, "PROPERTY_KINDS", "PROPERTY_KINDS"), (replay, "MUTATIONS", "MUTATIONS"),
             (replay, "MAX_TESTS", "MAX_TESTS"), (replay, "MAX_PROPERTY_TEXT", "MAX_PROPERTY_TEXT"),
             (replay, "MAX_FRAGMENTS", "MAX_FRAGMENTS"), (engineer, "SHOWN_TAG", "SHOWN_TAG"),
             (describer, "DEFAULT_TARGET", "DEFAULT_TARGET"), (package, "NOTE_HOOKS", "NOTE_HOOKS"),
             (examiner, "GENERATOR_CALLS", "GENERATOR_CALLS"), (examiner, "POLICY_CALLS", "POLICY_CALLS"),
             (examiner, "MAX_SPECS", "MAX_SPECS"), (examiner, "PROBE_TAG", "EXAMINER_PROBE_TAG"),
             (examiner, "MAX_RATIONALE", "MAX_RATIONALE"), (examiner, "MAX_CONCEPT_CHARS", "MAX_CONCEPT_CHARS"),
             (examiner, "MAX_QUESTION_CHARS", "MAX_QUESTION_CHARS")]
    for module, name, twin in twins:
        value, registered = getattr(module, name), getattr(protocol, twin)
        assert value == registered and type(value) is type(registered), (module.__name__, name)
    assert protocol.TRACKER_AGREEMENT == Fraction(97, 100) and protocol.MAX_SPECS == protocol.MAX_RESEARCH_REQUESTS
    assert protocol.MUTATIONS["strip_digits"] == protocol.BENCHES and protocol.SHOWN_TAG == "execskill-v1:engineer-shown"
    assert (protocol.GENERATOR_CALLS, protocol.POLICY_CALLS, protocol.MAX_TESTS, protocol.DEFAULT_TARGET) == (2, 1, 8, 600)
    # calc T11: the examiner's calls per step and bench
    assert protocol.DETECTOR_CALLS + protocol.POLICY_CALLS + protocol.GENERATOR_CALLS * protocol.BAND_ROUNDS == 9


def test_registered_mde_points():
    """§3.3, calc T1 (joint 80 % power, rho 0.5, whole-batch convention; LiveMath the high-noise row)."""
    assert protocol.MDE_POINTS == {"spreadsheetbench": 12.1, "officeqa": 10.0, "searchqa": 3.4, "alfworld": 9.7,
                                   "livemath": 10.0}
    assert set(protocol.MDE_POINTS) == set(protocol.BENCHES)
    assert all(type(v) is float and 0 < v < 100 for v in protocol.MDE_POINTS.values())
    assert protocol.EXCLUSION_DIR == "shared/exclusion"


def _calc():
    """The calc module, executed once with its tables printed into a buffer (it reads no file, calls nothing)."""
    found = [path for path in (PACKAGE.parents[1] / CALC_NAME, Path(protocol.BUILD_TREE) / CALC_NAME) if path.exists()]
    if not found:
        pytest.skip("the registration's calc file is not beside this tree")
    assert hashlib.sha256(found[0].read_bytes()).hexdigest() == CALC_SHA256
    spec = importlib.util.spec_from_file_location("execskill_calc", found[0])
    calc = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(calc)
    return calc


def _split(value_at):
    """(card, procedure) cells of one scope and bench from the calc's own function priced with anchor 1 and procedure
    factor 1 and 2 (the procedure cells are the difference)."""
    one, two = value_at(1.0), value_at(2.0)
    return round(2 * one - two, 6), round(two - one, 6)


def test_maximum_schedule_cells_are_the_calc_t4_t5_counts_and_give_the_t6_caps():
    """S-E6's cell counts (§9.2, §9.3; ticket C7b2-2) recomputed from the calc's ``step_cost`` and ``test_read`` at the
    maximum schedule: priced at the high anchors they give T4's and T5's maximum rows to the token and T6's caps."""
    calc = _calc()
    anchors, factor = calc.CELL, calc.PO
    steps = {"SB step 1": "spreadsheetbench", "OQ step 2": "officeqa", "ALF step 2": "alfworld"}

    def priced(bench, procedure):
        calc.CELL, calc.PO = {b: (0, 1 if b == bench else 0) for b in anchors}, (1.0, procedure)

    try:
        for name, step_bench in steps.items():
            for kind in ("run", "examiner", "selftest", "accept"):
                found = {}
                for bench in anchors:
                    def value(procedure, bench=bench):
                        priced(bench, procedure)
                        return calc.step_cost(*calc.STEP_ARGS[name], "max")[kind][1]
                    # T4 prices every run cell at 1.6 whatever the arm, so the run's cells are procedure cells
                    cells = (0, round(value(1.0) / 1.6, 6)) if kind == "run" else _split(value)
                    if any(cells):
                        found[bench] = cells
                assert found == protocol.MAX_SCHEDULE_CELLS[step_bench][kind], (name, kind)
        for name, home in calc.HOMES:
            found = {}
            for bench in anchors:
                def value(procedure, bench=bench, home=home):
                    priced(bench, procedure)
                    read = calc.test_read(home, twins_per=(2.0, 2.0))
                    return read["no_twins"][1] + read["twins"][1]
                found[bench] = _split(value)
            assert found == protocol.TEST_READ_CELLS[name.split()[0]], name
    finally:
        calc.CELL, calc.PO = anchors, factor
    high = float(protocol.PROCEDURE_ARM_FACTOR[1])

    def tokens(cells):
        return sum(protocol.CELL_ANCHORS[b][1] * (card + high * proc) for b, (card, proc) in cells.items())

    for name, step_bench in steps.items():
        for kind, cells in protocol.MAX_SCHEDULE_CELLS[step_bench].items():
            assert tokens(cells) == pytest.approx(calc.STEPS["max"][name][kind][1], rel=1e-12)
            assert calc.up(1.5 * tokens(cells) / M + calc.R[step_bench] / M) * M == pytest.approx(
                protocol.STEP_CAPS[step_bench][kind])
    for name, _ in calc.HOMES:
        pilot = name.split()[0]
        assert tokens(protocol.TEST_READ_CELLS[pilot]) / M == pytest.approx(calc.TRMAX[name], rel=1e-12)
        cap = calc.up(1.5 * calc.TRMAX[name] + max(calc.R.values()) / M, 1.0)
        assert cap * M == protocol.PILOTS[pilot]["test_read_cap"]


# ------------------------------------------- registrar "Owner instructions 2026-10-22 17:0x and 17:3x": main (M1)
MAIN_STEP_ARGS = {  # calc T4 ``step_cost`` arguments of main's steps: SQ -> OQ -> LM -> SB -> ALF (protocol comment)
    "searchqa": ("searchqa", 300, 1, 1_000, 1, True, (), False, 0, False),
    "officeqa": ("officeqa", 24, 2, 50, 4, False, (), True, 50, True),
    "livemath": ("livemath", 119, 1, 100, 2, False, ("officeqa",), True, 100, True),
    "spreadsheetbench": ("spreadsheetbench", 31, 2, 60, 2, False, ("officeqa", "livemath"), True, 60, True),
    "alfworld": ("alfworld", 60, 1, 150, 1, False, ("officeqa", "livemath", "spreadsheetbench"), False, 0, False),
}


def test_main_is_the_five_bench_configuration_with_its_root_label_and_rules():
    assert protocol.MAIN == "main" and protocol.CONFIGURATIONS is protocol.PILOTS
    assert protocol.PILOTS["main"]["order"] == protocol.BENCHES == (
        "searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")
    assert protocol.first_call_bench("main") == "searchqa" and protocol.first_call_bench() == protocol.FIRST_CALL_BENCH
    assert protocol.MAIN_ROOT == "/data/execskill-20261022-main" == protocol.RUN_ROOTS["main"]
    assert "main_real_run" in protocol.EVIDENCE and protocol.REAL_RUN_EVIDENCE == {
        "default": "pilot_real_run", "recommended": "pilot_real_run", "main": "main_real_run"}
    assert protocol.COST_CHECK_PAUSES == {"default": True, "recommended": True, "main": False}
    assert protocol.CONFIG_CAP_FACTOR["main"] == 3 and protocol.CONFIG_CAP_FACTOR["default"] == Fraction(3, 2)
    assert {bench: protocol.fired_share(bench, "main") for bench in protocol.BENCHES} == {
        bench: 1 for bench in protocol.BENCHES}  # all five home
    for name in protocol.CONFIGURATIONS:
        assert set(protocol.CONFIG_STEP_CAPS[name]) >= set(protocol.CONFIGURATIONS[name]["order"])
        assert set(protocol.CONFIG_SCHEDULE_CELLS[name]) >= set(protocol.CONFIGURATIONS[name]["order"])


def test_main_schedule_cells_are_calc_t4s_and_every_main_cap_is_at_least_3_x_its_need():
    """Registrar 17:0x, "Caps (cost no concern)": main's maximum schedule is calc T4's ``step_cost`` of main's five
    steps (J7's 64 options-only items, S' and C once each, added to LiveMath's acceptance); every step scope's cap is
    3 x (its cells at the high anchors + 16 full chain-G reservations), rounded up to 0.1M; the redo reserve, the test
    read, the solver cap and the GLM cap are at least 3 x their needs (notes/M-M1.md has the arithmetic)."""
    calc = _calc()
    anchors, factor = calc.CELL, calc.PO
    try:
        for step_bench, args in MAIN_STEP_ARGS.items():
            for kind in ("run", "examiner", "selftest", "accept"):
                found = {}
                for bench in anchors:
                    def value(procedure, bench=bench, args=args, kind=kind):
                        calc.CELL, calc.PO = {b: (0, 1 if b == bench else 0) for b in anchors}, (1.0, procedure)
                        return calc.step_cost(*args, "max")[kind][1]
                    cells = (0, round(value(1.0) / 1.6, 6)) if kind == "run" else _split(value)
                    if any(cells):
                        found[bench] = cells
                if (step_bench, kind) == ("livemath", "accept"):
                    card, proc = found["livemath"]
                    found["livemath"] = (card + protocol.LIVEMATH_J7_PROBE, proc + protocol.LIVEMATH_J7_PROBE)
                assert found == protocol.MAIN_SCHEDULE_CELLS[step_bench][kind], (step_bench, kind)
    finally:
        calc.CELL, calc.PO = anchors, factor
    high = {b: protocol.CELL_ANCHORS[b][1] for b in protocol.BENCHES}
    full = {b: ledger.reservation(calc.REQ[b], protocol.GLM_SOLVER_TOKENS) for b in protocol.BENCHES}
    assert full["searchqa"] == full["spreadsheetbench"] == 520_192 and full["alfworld"] == 392_192
    assert max(protocol.ledger_bound(protocol.CHAINS["D"], b, branch="N", longest=40_000)
               for b in protocol.BENCHES) <= protocol.GLM_SOLVER_TOKENS  # chain D's reservations are no larger

    def tokens(cells):
        return sum(high[b] * (card + float(protocol.PROCEDURE_ARM_FACTOR[1]) * proc) for b, (card, proc) in cells.items())

    def need(cells, units=1):
        return tokens(cells) + units * protocol.MAIN_RESERVATIONS * max(full[b] for b in cells)

    steps = 0
    for bench in protocol.BENCHES:
        for kind, cells in protocol.MAIN_SCHEDULE_CELLS[bench].items():
            cap = protocol.MAIN_STEP_CAPS[bench][kind]
            assert cap == _ceil(3 * need(cells), 100_000), (bench, kind)
            steps += cap
    assert need(protocol.MAIN_SCHEDULE_CELLS["searchqa"]["accept"]) == 36_883_072
    assert need(protocol.MAIN_SCHEDULE_CELLS["alfworld"]["accept"]) == 67_025_072
    redo = max(need({b: (card / (protocol.SLICES[bench]["blocks"] if kind == "accept" else 1),
                         proc / (protocol.SLICES[bench]["blocks"] if kind == "accept" else 1))
                     for b, (card, proc) in cells.items()})
               for bench in protocol.BENCHES for kind, cells in protocol.MAIN_SCHEDULE_CELLS[bench].items())
    plan = protocol.PILOTS["main"]
    assert round(redo) == 23_982_336 and plan["redo_reserve"] == _ceil(3 * redo, 100_000) == 72_000_000
    test = need(protocol.TEST_READ_CELLS["main"], units=len(protocol.BENCHES))
    assert round(test) == 135_590_984 and plan["test_read_cap"] == _ceil(3 * test, M) == 407 * M
    assert tokens(protocol.TEST_READ_CELLS["main"]) == pytest.approx(93_975_624)
    assert plan["solver_cap"] == _ceil(steps + plan["test_read_cap"] + plan["redo_reserve"], 5 * M) == 1_520 * M
    step_needs = sum(need(cells) for kinds in protocol.MAIN_SCHEDULE_CELLS.values() for cells in kinds.values())
    assert plan["solver_cap"] >= 3 * (step_needs + test + redo)
    roles = protocol.MAIN_ROLE_CAPS
    assert roles == {"engineer": 5 * M, "examiner": 5 * M, "examiner_research": 9_200_000}
    assert protocol.MAIN_GLM_CAP == 3 * len(protocol.BENCHES) * sum(roles.values()) == 288 * M
    for bench in protocol.BENCHES:  # each attempt sub-scope min(kind cap, redo reserve) >= 3 x that kind's redo
        for kind, cells in protocol.MAIN_SCHEDULE_CELLS[bench].items():
            share = protocol.SLICES[bench]["blocks"] if kind == "accept" else 1
            one = need({b: (card / share, proc / share) for b, (card, proc) in cells.items()})
            assert min(protocol.MAIN_STEP_CAPS[bench][kind], plan["redo_reserve"]) >= 3 * one, (bench, kind)


def test_main_test_read_cells_are_five_arms_on_every_home_test_item():
    """§8.1 test read of main: every bench home (f = 1), so each test item has one card cell and 5 procedure cells
    (the arms of ``TEST_READ_CELLS``' rule, ``test_the_fired_shares_are_the_ones_the_test_read_cells_count``)."""
    n = {"searchqa": 400, "officeqa": 172, "livemath": 125, "spreadsheetbench": 279, "alfworld": 134}
    assert protocol.TEST_READ_CELLS["main"] == {bench: (count, 5 * count) for bench, count in n.items()}
    high = {b: {"card": float(protocol.CELL_ANCHORS[b][1]), "procedure": None, "procedure_assumed": True}
            for b in protocol.BENCHES}
    terms = protocol.read_estimate_terms(high, 1, "main")
    assert {b: terms[b] for b in protocol.BENCHES} == {
        b: n[b] * protocol.CELL_ANCHORS[b][1] * (1 + 4 * protocol.PROCEDURE_ARM_FACTOR[1]) for b in protocol.BENCHES}
    assert protocol.estimate_test_read(high, 1, "main") == math.ceil(sum(terms.values()))
    assert 1.3 * protocol.estimate_test_read(high, 1, "main") <= protocol.PILOTS["main"]["test_read_cap"]


# ------------------------------------------------- registrar addendum 2026-10-22 14:10, row 8: the test-read estimate
SE6_HIGH = {b: {"card": float(protocol.CELL_ANCHORS[b][1]), "procedure": None, "procedure_assumed": True}
            for b in protocol.BENCHES}  # S-E6's per_cell at the §9.1 high anchors, no procedure cell measured


def test_the_test_read_estimate_is_calc_t5s_high_row_at_the_high_anchors():
    """Row 8 (pilot-runbook §3.4): ceil(ratio x sum_b n_b (card_b + 4 f_b proc_b)), exact -- at the §9.1 high anchors
    with a procedure cell of 1.6 x the card cell and ratio 1 it is calc T5's 54.4M high row, 272,045,432 / 5 tokens."""
    assert protocol.estimate_test_read(SE6_HIGH, 1) == 54_409_087
    given = {b: {"card": protocol.CELL_ANCHORS[b][1], "procedure": protocol.CELL_ANCHORS[b][1] * Fraction(8, 5),
                 "procedure_assumed": False} for b in protocol.BENCHES}  # the same cells, measured
    assert protocol.estimate_test_read(given, Fraction(1)) == 54_409_087
    flagged = {**SE6_HIGH, "officeqa": {**SE6_HIGH["officeqa"], "procedure": 1.0}}  # S-E6's flag decides
    assert protocol.estimate_test_read(flagged, 1) == 54_409_087
    half = protocol.estimate_test_read(SE6_HIGH, 0.5)
    assert half == protocol.estimate_test_read(SE6_HIGH, Fraction(1, 2)) == 27_204_544  # one ceiling, at the end
    assert protocol.estimate_test_read(SE6_HIGH, 1.25) == math.ceil(Fraction(272_045_432, 5) * Fraction(5, 4))
    one = {b: {"card": 1, "procedure": 1, "procedure_assumed": False} for b in protocol.BENCHES}
    n = {b: protocol.TEST_READ_CELLS["default"][b][0] for b in protocol.BENCHES}
    assert protocol.estimate_test_read(one, 1) == sum(n[b] * (1 + 4 * protocol.fired_share(b)) for b in n) == 4_652
    # the recommended pilot (SB -> ALF) reads the same items with other fired shares
    assert protocol.estimate_test_read(one, 1, pilot="recommended") == math.ceil(
        400 * 3 + 172 * Fraction(19, 5) + 125 * 3 + 279 * 5 + 134 * 5) == 4_294


def test_the_fired_shares_are_the_ones_the_test_read_cells_count():
    """f_b is 1 on a home bench, 0.7 on a bench similar to one (§8.2's pairs), 0.5 elsewhere; T5's procedure cells
    are 5 x n x f, so TEST_READ_CELLS and the estimate agree on every bench of both pilots."""
    assert {b: protocol.fired_share(b) for b in protocol.BENCHES} == {
        "searchqa": Fraction(7, 10), "officeqa": 1, "livemath": Fraction(7, 10), "spreadsheetbench": 1,
        "alfworld": Fraction(1, 2)}
    for pilot in protocol.PILOTS:
        for bench, (n, procedure) in protocol.TEST_READ_CELLS[pilot].items():
            assert 5 * n * protocol.fired_share(bench, pilot) == procedure, (pilot, bench)
    assert protocol.TEST_READ_ESTIMATE_ARMS == 4 and protocol.FIRED_SHARES["other"] == Fraction(1, 2)


@pytest.mark.parametrize("per_cell, ratio, pilot", [
    ({b: SE6_HIGH[b] for b in protocol.BENCHES if b != "alfworld"}, 1, "default"),  # S-E6 measures every bench
    ({**SE6_HIGH, "alfworld": {"procedure": 3.0}}, 1, "default"),
    ({**SE6_HIGH, "alfworld": {**SE6_HIGH["alfworld"], "card": 0}}, 1, "default"),
    ({**SE6_HIGH, "alfworld": {**SE6_HIGH["alfworld"], "card": float("nan")}}, 1, "default"),
    ({**SE6_HIGH, "alfworld": {**SE6_HIGH["alfworld"], "card": "45000"}}, 1, "default"),
    ({**SE6_HIGH, "alfworld": {**SE6_HIGH["alfworld"], "card": True}}, 1, "default"),
    ({**SE6_HIGH, "alfworld": {"card": 1.0, "procedure": -1.0, "procedure_assumed": False}}, 1, "default"),
    (SE6_HIGH, 0, "default"),
    (SE6_HIGH, float("inf"), "default"),
    (SE6_HIGH, 1, "formal"),
])
def test_the_test_read_estimate_refuses_what_s_e6_did_not_measure(per_cell, ratio, pilot):
    with pytest.raises(ValueError):
        protocol.estimate_test_read(per_cell, ratio, pilot=pilot)


def test_the_first_call_confirmation_is_registered():
    """Row 7: the fixture prompt (no pool item), the bench whose settings it uses (the first step's) and the cap of
    its sub-scope -- four full reservations at chain G's B = 65,536, rounded up to 0.1M."""
    assert protocol.FIRST_CALL_BENCH == protocol.ORDER[0] == "spreadsheetbench"
    assert protocol.FIRST_CALL_USER == "Reply with the single word: ready" and protocol.FIRST_CALL_SYSTEM
    four = 4 * ledger.reservation(ledger.request_bytes(protocol.FIRST_CALL_SYSTEM, protocol.FIRST_CALL_USER),
                                  protocol.GLM_SOLVER_TOKENS)
    assert four < protocol.FIRST_CALL_CAP == math.ceil(four / 100_000) * 100_000 == 1_100_000
