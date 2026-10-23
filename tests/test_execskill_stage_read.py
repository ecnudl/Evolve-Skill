"""v2 stage reads (owner decision 2026-10-23 16:0x: "我说的主实验是指在五个bench上逐个进化，并且每个进化之后都在所有的五个
bench上评测的意思"; ``protocol.STAGE_READ``, main-v2): the end-of-chain read unit also runs the package every step passed
on (the stage arms "S<k>"), each stage cell running or sharing exactly the cell of the unit whose procedures it would
run (C's, F's, an earlier stage arm's); a fallback where the source cell did not run with them or recorded a fault;
F's routes reused only where they hold no fault; the stage record of a read whose rows are C and F alone; the rows of
the stage table from the chain's step records; the consent naming the stage arms, checked in the unit before its
attempt opens; the chain's read rule; the unseal and the stage table readout; main-v2's read cells, caps and estimate
(Codex stage review #1-#4 each has its test). Offline and deterministic: the fixtures of
tests/test_execskill_evaluation.py (a stateless fake solver right exactly when the request carries notes,
FakeSandbox procedures, a synthetic OfficeQA panel)."""
from __future__ import annotations

import itertools
import math
from fractions import Fraction

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, safe_path, write_json
from skillopt.execskill import budgets, chain, evaluation, manifest, package, protocol, readout
from skillopt.execskill.cells import Arm, Context
from skillopt.execskill.package import empty, with_
from skillopt.execskill.protocol import BENCHES, TEST_ARMS, record, verified
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.test_execskill_evaluation import (BENCH, CARD, CARD_PACKAGE, CHAIN, EVIDENCE, FINAL, HOOKS, ITEMS, RUN,
                                             ZERO, M, N, Solver, arms, consent_value, page, panel,
                                             register_canaries)

# two procedures no F holds: Q fires on every fourth page, K never
Q = procedure("p-officeqa-2-1", ("applies", "before_call"), header="Quarter helper notes.", evidence=EVIDENCE)
K = procedure("p-officeqa-3-1", ("applies", "before_call"), header="Silent helper notes.", evidence=EVIDENCE)
EXTRA = {Q.id: {"applies": lambda view: page(view) % 4 == 0,
                "before_call": lambda view, state: {"facts": ["Read the quarter's row."]}},
         K.id: {"applies": lambda view: False, "before_call": lambda view, state: {"facts": ["Never shown."]}}}
S1 = with_(CARD_PACKAGE, step="pilot/s1-officeqa/t1", add=[N])  # N alone: a part of F, routed from F's routes
S2 = with_(CARD_PACKAGE, step="pilot/s2-officeqa/t1", add=[Q])  # not F's: routed in its own workers
S3 = with_(S1, step="pilot/s3-officeqa/t1", add=[K])  # N and a silent K: S1's procedures wherever N fires
STAGES = {"rows": ["C", "S1", "S2", "S3", "S3", "F"], "packages": {"S1": S1, "S2": S2, "S3": S3}}
STAGE_CONSENT = consent_value(multi_arm_arms=list(TEST_ARMS) + ["stages"])
PAGES = {item["task_id"]: page(item["public"]) for item in ITEMS}


def rewrite(path, value):
    """Records are write-once (``write_json``); a test that changes the owner's file removes it first."""
    path.unlink(missing_ok=True)
    write_json(path, value)


def by_page(pages):
    return {item for item, n in PAGES.items() if n in pages}


N_ONLY, BOTH, M_ONLY = by_page({1, 5, 7, 11}), by_page({2, 4, 8, 10}), by_page({0, 6})
QUARTER = by_page({0, 4, 8})
assert ZERO == by_page({3, 9})


def hooks(**changes):
    return {**HOOKS, **EXTRA, **changes}


def read(tmp_path, *, stages=STAGES, solver=None, table=None, consent=STAGE_CONSENT, configuration=protocol.MAIN_V2,
         panel_=panel):
    root = tmp_path / "run-root"
    shared = root / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    rewrite(shared / "consent.json", consent)
    table = table or hooks()
    workers = []

    def route_workers(package_, item):
        from contextlib import contextmanager

        @contextmanager
        def started():
            worker = FakeSandbox(table).start(package_, kind="cell")
            workers.append(package_.sha256)
            try:
                yield worker
            finally:
                worker.close()
        return started()

    endpoint = Endpoint(solver or Solver(), model="deepseek-v4.1-flash-1017", max_tokens=100,
                        slots=Slots(tmp_path / "slots", "deepseek", 2), sleep=lambda _: None)
    unit_root = root / CHAIN / "test" / BENCH
    ticks = itertools.count()
    context = Context(attempt=unit_root / "attempt-1", endpoint=endpoint, runtime=RUNTIME,
                      cards={b: CARD for b in BENCHES}, native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                      episodes=Slots(tmp_path / "slots", "alfworld-episode", 1),
                      worker=lambda bench: FakeSandbox(table), evidence=EVIDENCE, clock=lambda: float(next(ticks)))
    found = evaluation.evaluate(unit_root, run=RUN, shared=shared, pinned=None, chain=CHAIN, bench=BENCH, arms=arms(),
                                context=context, workers=2, route_workers=route_workers, canaries=[], panel=panel_,
                                stages=stages, run_configuration=configuration)
    cells = {(c["cell"]["arm"], c["cell"]["task_id"]): c for c in (
        verified(read_json(p), "evaluation-cell") for p in (unit_root / found["attempt"] / "cells").glob("*.json"))}
    return root, unit_root, found, cells, workers


# ------------------------------------------------------------------------------------------ the read unit
def test_stage_cells_run_or_share_exactly_the_cell_whose_procedures_they_would_run(tmp_path):
    solver = Solver()
    root, unit_root, found, cells, workers = read(tmp_path, solver=solver)
    assert verified(found, "evaluation")["status"] == "complete"
    ids = {key: c["cell"]["id"] for key, c in cells.items()}
    for item in PAGES:
        s1, s2, s3 = cells[("S1", item)], cells[("S2", item)], cells[("S3", item)]
        # S1 (N): F's cell where F enables N alone, its own where F enables N and M, C's where N is silent
        assert s1["shared_with"] == (ids[("F", item)] if item in N_ONLY else None if item in BOTH else ids[("C", item)])
        # S2 (Q): its own cell where Q fires, else C's
        assert s2["shared_with"] == (None if item in QUARTER else ids[("C", item)])
        # S3 (N and a silent K): F's where F enables N alone, S1's running cell where F enables N and M, else C's
        assert s3["shared_with"] == (ids[("F", item)] if item in N_ONLY else ids[("S1", item)] if item in BOTH
                                     else ids[("C", item)])
        for cell in (s1, s2, s3):
            assert cell["arm_kind"] == "candidate" and (cell["calls"] == []) == (cell["shared_with"] is not None)
        assert s1["enabled"] == ([N.id] if item in N_ONLY | BOTH else [])
        assert s3["enabled"] == s1["enabled"] and s2["enabled"] == ([Q.id] if item in QUARTER else [])
    # one call per cell that ran: C 12, F/P_F/T_F on the 10 non-zero items, the twins, S1 4 and S2 3
    twins = [c for (arm, _), c in cells.items() if arm.startswith("withhold:")]
    assert solver.calls == 12 + 3 * 10 + len(twins) + len(BOTH) + len(QUARTER)
    assert found["packages"] == {"F": FINAL.sha256, "C": CARD_PACKAGE.sha256, "S1": S1.sha256, "S2": S2.sha256,
                                 "S3": S3.sha256}
    stages = found["stages"]
    assert stages["rows"] == STAGES["rows"] and stages["derived"] == {"S1": len(PAGES), "S2": 0, "S3": 0}
    assert stages["sources"] == {"S1": {"C": 4, "F": 4, "sent": 4}, "S2": {"C": 9, "sent": 3},
                                 "S3": {"C": 4, "F": 4, "S1": 4}} and stages["fallback"] == 0
    assert found["counts"]["by_arm"]["S1"] == found["counts"]["by_arm"]["S3"] == len(PAGES)
    # S1's routes came from F's (no worker); S2 and S3 were routed in workers holding them, one per item
    assert workers.count(S1.sha256) == 0 and workers.count(S2.sha256) == workers.count(S3.sha256) == len(PAGES)
    assert workers.count(FINAL.sha256) >= len(PAGES)


def test_a_source_cell_that_did_not_run_with_the_planned_procedures_makes_the_stage_cell_run(tmp_path):
    flaky = sorted(N_ONLY)[0]
    seen = []

    def applies(view):  # N fires on the flaky item's page only the first time it is asked (the plan's route)
        n = page(view)
        if n == PAGES[flaky]:
            seen.append(n)
            return len(seen) == 1
        return n % 3 != 0

    table = hooks(**{N.id: {**HOOKS[N.id], "applies": applies}})
    root, unit_root, found, cells, _ = read(tmp_path, table=table)
    assert cells[("F", flaky)]["enabled"] == []  # F's cell ran without N there: not the plan's procedures
    assert cells[("S1", flaky)]["shared_with"] is None and len(cells[("S1", flaky)]["calls"]) == 1
    assert found["stages"]["fallback"] == 1 and found["stages"]["sources"]["S1"]["F"] == 4  # planned F, ran itself
    for item in N_ONLY - {flaky}:
        assert cells[("S1", item)]["shared_with"] == cells[("F", item)]["cell"]["id"]


def test_a_source_cell_that_recorded_a_fault_is_never_shared(tmp_path, monkeypatch):
    # Codex stage review #1: F ran N on the flaky item but N's notes failed (a transient fault): the shell drops them
    # and F's ``enabled`` still names N, so S1 and S3, planned to share F's cell there, run themselves
    flaky, healed = sorted(N_ONLY)[0], []

    def before_call(view, state):  # fails on the flaky item until the blocks have run
        if page(view) == PAGES[flaky] and not healed:
            raise TimeoutError("transient")
        return HOOKS[N.id]["before_call"](view, state)

    linked = evaluation._linked

    def after_the_blocks(*args, **kwargs):
        healed.append(True)
        return linked(*args, **kwargs)

    monkeypatch.setattr(evaluation, "_linked", after_the_blocks)
    root, unit_root, found, cells, _ = read(tmp_path, table=hooks(**{N.id: {**HOOKS[N.id], "before_call": before_call}}))
    assert healed == [True]
    faulted = cells[("F", flaky)]
    assert faulted["enabled"] == [N.id] and faulted["shared_with"] is None and faulted["fault_kinds"] == {"exception": 1}
    assert faulted["judge"]["v2"] != "pass"  # without N's notes the fake solver is wrong
    for label in ("S1", "S3"):
        cell = cells[(label, flaky)]
        assert cell["shared_with"] is None and len(cell["calls"]) == 1 and cell["faults"] == []
        assert cell["enabled"] == [N.id] and cell["judge"]["v2"] == "pass"
        assert cell["calls"][0]["request_sha256"] != faulted["calls"][0]["request_sha256"]  # another request
    assert found["stages"]["fallback"] == 2 and found["stages"]["sources"]["S1"] == {"C": 4, "F": 4, "sent": 4}
    for item in N_ONLY - {flaky}:
        assert cells[("S1", item)]["shared_with"] == cells[("F", item)]["cell"]["id"]


def test_an_item_where_fs_routing_faulted_is_routed_in_the_stage_packages_own_worker(tmp_path):
    # Codex stage review #2: N's predicate faults on the flaky item when F is routed (the plan) and answers after: F
    # enables nothing there (a structural zero, a fault on its route), S1's route there is not taken from F's
    flaky, seen = sorted(N_ONLY)[0], []

    def applies(view):
        if page(view) == PAGES[flaky]:
            seen.append(1)
            if len(seen) == 1:
                raise TimeoutError("transient")
            return True
        return page(view) % 3 != 0

    root, unit_root, found, cells, workers = read(tmp_path, table=hooks(**{N.id: {**HOOKS[N.id], "applies": applies}}))
    assert cells[("F", flaky)]["shared_with"] == cells[("C", flaky)]["cell"]["id"]  # F enabled nothing there
    assert cells[("F", flaky)]["fault_kinds"] == {"exception": 1}
    s1 = cells[("S1", flaky)]
    assert s1["enabled"] == [N.id] and s1["shared_with"] is None and len(s1["calls"]) == 1 and s1["faults"] == []
    assert cells[("S3", flaky)]["shared_with"] == s1["cell"]["id"]  # S3 enables N alone there too: S1's cell
    assert found["stages"]["derived"]["S1"] == len(PAGES) - 1 and workers.count(S1.sha256) == 1
    assert found["stages"]["sources"]["S1"] == {"C": 4, "F": 3, "sent": 5} and found["stages"]["fallback"] == 0


def test_a_stage_read_whose_rows_are_c_and_f_alone_records_its_stage_table(tmp_path):
    # Codex stage review #3: step 1 already passed F on (or only the last step accepted): no stage arm runs, the
    # unit still records the rows and the unseal hands the stage table on
    for n, rows in enumerate((["C", "F", "F", "F", "F", "F"], ["C", "C", "C", "C", "C", "F"])):
        root, unit_root, found, cells, workers = read(tmp_path / str(n), stages={"rows": rows, "packages": {}})
        assert found["stages"] == {"rows": rows, "plan_sha256": None, "derived": {}, "sources": {}, "fallback": 0}
        assert {arm for arm, _ in cells} == {"C", "F", "P_F", "T_F"} | {a for a, _ in cells if a.startswith("withhold:")}
        register_canaries(root)
        chain_root = root / CHAIN
        write_json(chain_root / "chain-complete.json", record("chain-complete", EVIDENCE, {"chain": CHAIN}))
        write_json(root / "shared" / "owner-continuation.json",
                   {"by": "owner", "date": "2026-10-23", "decision": "stop", "note": "fixture"})
        opened = evaluation.unseal(root, chain_root, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE,
                                   clock=lambda: "2026-10-23T12:00:00Z")
        assert opened["stages"] == {BENCH: rows}
        table = readout.stage_table(opened["units"], rows)[BENCH]
        assert [row["arm"] for row in table] == rows
        assert [row["accuracy"]["L"] for row in table] == [pytest.approx({"C": 0, "F": 10 / 12}[arm]) for arm in rows]


def test_the_unit_reads_stage_arms_only_under_their_configurations_exact_consent(tmp_path):
    # Codex stage review #4: the evaluator itself refuses a stage read outside a stage-read configuration or under a
    # consent that does not name the stage arms -- before an attempt opens or a panel is read
    touched = []

    def watched(*args, **kwargs):
        touched.append(1)
        return panel(*args, **kwargs)

    for n, (configuration, consent, match) in enumerate((
            (None, STAGE_CONSENT, "stage-read configuration"), ("main", STAGE_CONSENT, "stage-read configuration"),
            (protocol.MAIN_V2, consent_value(), "consent"))):
        with pytest.raises(ValueError, match=match):
            read(tmp_path / str(n), configuration=configuration, consent=consent, panel_=watched)
        assert not (tmp_path / str(n) / "run-root" / CHAIN / "test" / BENCH / "attempt-1").exists()
    assert touched == []
    read(tmp_path / "ok", panel_=watched)  # main-v2 under the stage consent reads
    assert touched == [1]


def test_the_read_refuses_stage_arms_that_are_not_the_chains_rows(tmp_path):
    bad = [{"rows": ["S1", "F"], "packages": {"S1": S1}},  # row 0 is the card arm
           {"rows": ["C", "F"], "packages": {"S1": S1}},  # a stage package no row reads
           {"rows": ["C", "S1", "F"], "packages": {"S1": FINAL}},  # F is no stage arm
           {"rows": ["C", "S1", "F"], "packages": {"S1": empty(step="x", evidence=EVIDENCE)}},  # no procedure
           {"rows": ["C", "S1", "S2", "F"], "packages": {"S1": S1, "S2": S1}},  # one package, two arms
           {"rows": ["C", "X1", "F"], "packages": {"X1": S1}}]  # not S<k>
    for n, stages in enumerate(bad):
        with pytest.raises(ValueError, match="stage arms"):
            read(tmp_path / str(n), stages=stages)


# ------------------------------------------------------------------------------- unseal and the stage table
def test_the_unseal_names_the_shared_arm_and_the_stage_table_reads_each_row(tmp_path):
    root, unit_root, found, cells, _ = read(tmp_path)
    register_canaries(root)
    chain_root = root / CHAIN
    write_json(chain_root / "chain-complete.json", record("chain-complete", EVIDENCE, {"chain": CHAIN}))
    write_json(root / "shared" / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-23", "decision": "stop", "note": "fixture"})
    opened = evaluation.unseal(root, chain_root, CHAIN, [unit_root], run=RUN, evidence=EVIDENCE,
                               clock=lambda: "2026-10-23T12:00:00Z")
    assert opened["stages"] == {BENCH: STAGES["rows"]}
    table = opened["units"][BENCH]
    for item in PAGES:
        assert table[("S1", item, 0)]["shared_arm"] == ("F" if item in N_ONLY else None if item in BOTH else "C")
        assert table[("S3", item, 0)]["shared_arm"] == ("F" if item in N_ONLY else "S1" if item in BOTH else "C")
        assert table[("C", item, 0)]["shared_arm"] is None
    rows = readout.stage_table(opened["units"], opened["stages"][BENCH])[BENCH]
    assert [row["arm"] for row in rows] == STAGES["rows"] and {row["n"] for row in rows} == {len(PAGES)}
    # right exactly where some procedure wrote notes: C 0, S1 and S3 where N fires (8), S2 where Q fires (3), F 10
    expected = {"C": 0, "S1": 8, "S2": 3, "S3": 8, "F": 10}
    for row in rows:
        assert row["accuracy"] == {"L": pytest.approx(expected[row["arm"]] / 12),
                                   "H": pytest.approx(expected[row["arm"]] / 12)}
        if row["arm"] == "C":
            assert "minus_card" not in row
        else:
            assert row["minus_card"]["mean"] == pytest.approx(expected[row["arm"]] / 12)
    assert "minus_previous" not in rows[0] and "minus_previous" not in rows[4]  # row 4 reads row 3's arm
    assert rows[3]["minus_previous"]["mean"] == pytest.approx((8 - 3) / 12)
    assert rows[5]["minus_previous"]["mean"] == pytest.approx((10 - 8) / 12)  # F - S3: the M-only items
    # one cell, one outcome: where S3 reads F's or S1's cell its difference to that arm is 0 on every item
    assert readout.differences(table, "S3", "S1", sorted(PAGES)) == [0] * len(PAGES)
    assert set(readout.differences(table, "F", "S3", sorted(PAGES))) == {0, 1}
    assert readout.side("S3") == readout.side("F") == "L" and readout.side("P_F") == "H"
    # the readout carries the stage table; F learned OfficeQA, so its own readings stay
    value = readout.readout(opened["units"], learned=["officeqa"], procedures={N.id: "officeqa", M.id: "officeqa"},
                            label=opened["label"], evidence=EVIDENCE, stages=STAGES["rows"])
    assert value["stages"][BENCH] == rows and value["q1_home"]["officeqa"]["n"] == len(PAGES)
    plain = readout.readout(opened["units"], learned=["officeqa"], procedures={N.id: "officeqa", M.id: "officeqa"},
                            label=opened["label"], evidence=EVIDENCE)
    assert "stages" not in plain


# ------------------------------------------------------------------------------------- the stage table's rows
def step_record(chain_root, chain_, k, bench, sha):
    path = chain_root / ("s%d-%s" % (k, bench)) / "step.json"
    write_json(path, record("step", EVIDENCE, {"chain": chain_, "k": k, "bench": bench, "package_sha256": sha}))


def test_the_rows_come_from_the_chains_step_records(tmp_path):
    chain_root = tmp_path / "G"
    start = empty(step="G/s0", evidence=EVIDENCE)
    first = with_(start, step="G/s2", add=[N])
    final = with_(first, step="G/s4", add=[M])
    for found in (first, final):
        package.save(chain_root, found)
    passed = [start, first, first, final, final]  # step 1 and 3 accept nothing new, step 5 nothing at all
    for k, (bench, found) in enumerate(zip(BENCHES, passed), 1):
        step_record(chain_root, "G", k, bench, found.sha256)
    rows = evaluation.stage_rows(chain_root, "G", BENCHES, final, start)
    assert rows["rows"] == ["C", "C", "S2", "S2", "F", "F"] and rows["packages"] == {"S2": first}
    # a later step deleting every procedure: F is that empty package, the rows still read S2 where it was passed on
    deleted = with_(first, step="G/s5", remove=[N.id])
    package.save(chain_root, deleted)
    (chain_root / ("s5-%s" % BENCHES[4]) / "step.json").unlink()  # a fixture's other chain: records are write-once
    step_record(chain_root, "G", 5, BENCHES[4], deleted.sha256)
    assert evaluation.stage_rows(chain_root, "G", BENCHES, deleted, start)["rows"] == ["C", "C", "S2", "S2", "S4",
                                                                                       "C"]
    with pytest.raises(ValueError, match="final package"):
        evaluation.stage_rows(chain_root, "G", BENCHES, final, start)
    with pytest.raises(ValueError, match="record of step"):
        evaluation.stage_rows(chain_root, "D", BENCHES, deleted, start)
    (chain_root / ("s3-%s" % BENCHES[2]) / "step.json").unlink()
    with pytest.raises(ValueError, match="finished before its read"):
        evaluation.stage_rows(chain_root, "G", BENCHES, deleted, start)


# --------------------------------------------------------------------------------------------- the consent
def test_a_stage_read_needs_a_consent_naming_its_stage_arms(tmp_path):
    shared = tmp_path / "shared"
    rewrite(shared / "consent.json", consent_value())  # TEST_ARMS only
    assert evaluation.consent(shared)["multi_arm_arms"] == list(TEST_ARMS)
    assert evaluation.consent(shared, "main") and evaluation.consent(shared, "default")
    with pytest.raises(ValueError, match="consent"):
        evaluation.consent(shared, "main-v2")
    rewrite(shared / "consent.json", STAGE_CONSENT)
    assert evaluation.consent(shared, "main-v2")["multi_arm_arms"][-1] == "stages" and evaluation.consent(shared)
    with pytest.raises(ValueError, match="consent"):
        evaluation.consent(shared, "main")
    for bad in (consent_value(multi_arm_arms=list(TEST_ARMS) + ["stages", "stages"]),
                consent_value(multi_arm_arms=list(TEST_ARMS) + [["stages"]]),
                consent_value(multi_arm_arms=["F", "C", "P_F", "T_F", "stages"])):
        rewrite(shared / "consent.json", bad)
        with pytest.raises(ValueError, match="consent"):
            evaluation.consent(shared, "main-v2")
    assert protocol.read_arms_of("main-v2") == TEST_ARMS + ("stages",) and protocol.read_arms_of("main") == TEST_ARMS


# --------------------------------------------------------------------------------------- the chain's read rule
def v2_setting(tmp_path, *, arms_=None):
    from tests.execskill_fakes import first_call_solvers, with_first_call
    from skillopt.execskill.units import Setting

    root = tmp_path / "root"
    if arms_ is not None:
        write_json(root / "shared" / "consent.json", consent_value(multi_arm_arms=list(arms_)))
    base = Setting(run=RUN, root=root, shared=root / "shared", pools={}, cards={}, runtime={}, clients=None,
                   budget=Budget(budgets.ledger_root(root, "G")), slots={}, sandbox={}, evidence=EVIDENCE,
                   extra={"verify": lambda: None, "slot_root": str(tmp_path / "slots"), "configuration": "main-v2",
                          "test_read_estimate": {"G": 1000, "D": 1000}})
    return with_first_call(base, first_call_solvers(tmp_path), tmp_path / "call-slots")


class Learn:
    """A fake main-v2 step: step ``add_at`` accepts N, step ``delete_at`` deletes it (None: never)."""

    def __init__(self, *, add_at=2, delete_at=None):
        self.add_at, self.delete_at = add_at, delete_at

    def __call__(self, setting_, root, chain_, k, bench, parent):
        if k == 1:
            anchor = protocol.CELL_ANCHORS[bench][1]
            chain.cap_check(setting_, "G", 1, {"ok": True, "per_cell": 0.25 * anchor, "anchor_high": anchor,
                                               "scopes": {"G:solver": {"cap": 10, "projected": 1}}})
        package_ = parent
        if k == self.add_at:
            package_ = with_(parent, step="%s/s%d" % (chain_, k), add=[N])
        elif k == self.delete_at:
            package_ = with_(parent, step="%s/s%d" % (chain_, k), remove=[N.id])
        return package_, record("step", EVIDENCE, {"chain": chain_, "k": k, "bench": bench})


class Launch:
    def __init__(self):
        self.specs = []

    def __call__(self, setting_, spec):
        self.specs.append(spec)
        unit = safe_path(spec["unit_root"])
        unit.mkdir(parents=True, exist_ok=True)
        write_json(unit / "unit.json", record("evaluation", EVIDENCE, {
            "run": setting_.run, "chain": spec["chain"], "bench": spec["bench"],
            "packages": {"F": spec["package_sha256"]}}))
        return 0


def test_a_stage_read_chain_reads_unless_no_step_passed_on_a_procedure(tmp_path):
    launch = Launch()
    assert chain.run(v2_setting(tmp_path / "none", arms_=protocol.read_arms_of("main-v2")), "G",
                     learn=Learn(add_at=None), launch=launch) == {"status": "complete"}
    found = verified(read_json(tmp_path / "none" / "root" / "G" / "test-read.json"), "test-read")
    assert found["status"] == "not_read" and "v2 stage reads" in found["reason"] and launch.specs == []
    # step 2 accepts N and step 4 deletes it: F holds no procedure, but the stage arms do -- the read is made
    assert chain.run(v2_setting(tmp_path / "deleted", arms_=protocol.read_arms_of("main-v2")), "G",
                     learn=Learn(delete_at=4), launch=launch) == {"status": "complete"}
    found = verified(read_json(tmp_path / "deleted" / "root" / "G" / "test-read.json"), "test-read")
    assert found["status"] == "read" and sorted(spec["bench"] for spec in launch.specs) == sorted(BENCHES)
    # a consent without the stage arms leaves the chain waiting before any read child starts
    waiting = Launch()
    result = chain.run(v2_setting(tmp_path / "v1-consent", arms_=TEST_ARMS), "G", learn=Learn(), launch=waiting)
    assert result["status"] == "paused" and result["kind"] == "consent_missing" and waiting.specs == []


# ------------------------------------------------------------------------------------ the read child's wiring
def test_the_read_child_of_main_v2_hands_the_unit_the_chains_stage_rows(tmp_path, monkeypatch):
    from tests.test_execskill_evaluation import ReadPanel, s0_canaries
    from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment, main_given

    m = manifest.make(tmp_path / "main-v2.json", evidence="engineering_fixture", configuration="main-v2",
                      environment_found=fake_environment(), measured=MEASURED, **main_given(tmp_path, monkeypatch))
    root = safe_path(m["root"])
    write_json(root / "shared" / "consent.json", consent_value())  # without the stage arms
    s0_canaries(root)
    Budget(budgets.ledger_root(root, "G")).declare(budgets.chain_caps("G", "main-v2"))  # as chain.run declares it
    chain_root = root / "G"
    start = empty(step="G/s0", evidence=m["evidence"])
    first = with_(start, step="G/s1", add=[N])
    final = with_(first, step="G/s3", add=[M])
    for found in (first, final):
        package.save(chain_root, found)
    for k, (bench, found) in enumerate(zip(BENCHES, [first, first, final, final, final]), 1):
        step_record(chain_root, "G", k, bench, found.sha256)
    # the read unit itself is tested above; P_F's corpora and T_F's texts need accepted steps this fixture lacks
    monkeypatch.setattr(evaluation, "donor_corpora", lambda root_: {})
    monkeypatch.setattr(evaluation, "placebo_arm", lambda *args, **kwargs: (lambda cell, task: None))
    monkeypatch.setattr(evaluation, "frozen_texts", lambda root_, final_: {})
    seen = []
    monkeypatch.setattr(evaluation, "evaluate",
                        lambda unit_root, **given: seen.append((given["stages"], given["run_configuration"])))
    spec = tmp_path / "read.json"
    write_json(spec, {"chain": "G", "bench": "officeqa", "package_sha256": final.sha256,
                      "unit_root": str(chain_root / "test" / "officeqa")})
    with pytest.raises(ValueError, match="consent"):
        evaluation.run_unit_spec(m, spec=spec, docker=FakeDockerCLI(), transport=NO_CALLS, panel=ReadPanel())
    assert seen == []
    rewrite(root / "shared" / "consent.json", STAGE_CONSENT)
    assert evaluation.run_unit_spec(m, spec=spec, docker=FakeDockerCLI(), transport=NO_CALLS,
                                    panel=ReadPanel()) == chain.EXIT_COMPLETE
    assert seen == [({"rows": ["C", "S1", "S1", "F", "F", "F"], "packages": {"S1": first}}, "main-v2")]


# ---------------------------------------------------------------------------- main-v2's read cells and caps
def test_main_v2_prices_every_stage_arm_on_every_test_item():
    n = {b: protocol.TEST_READ_CELLS["main"][b][0] for b in BENCHES}
    assert protocol.stage_arms_max("main-v2") == len(BENCHES) - 1 == 4 and protocol.stage_arms_max("main") == 0
    assert all(protocol.fired_share(b, "main-v2") == 1 for b in BENCHES)  # every bench home
    assert protocol.TEST_READ_CELLS["main-v2"] == {b: (n[b], (5 + 4) * n[b]) for b in BENCHES}
    assert protocol.estimate_arms("main-v2") == 8 and protocol.estimate_arms("main") == 4
    high = {b: {"card": float(protocol.CELL_ANCHORS[b][1]), "procedure": None, "procedure_assumed": True}
            for b in BENCHES}
    terms = protocol.read_estimate_terms(high, 1, "main-v2")
    assert terms == {b: n[b] * protocol.CELL_ANCHORS[b][1] * (1 + 8 * protocol.PROCEDURE_ARM_FACTOR[1])
                     for b in BENCHES}
    assert protocol.estimate_test_read(high, 1, "main-v2") == math.ceil(sum(terms.values()))
    # main's cap rule over the stage-read cells: 3 x (the maximum read + 5 units x 16 x 520,192), to 1M
    tokens = sum(protocol.CELL_ANCHORS[b][1] * (card + protocol.PROCEDURE_ARM_FACTOR[1] * proc)
                 for b, (card, proc) in protocol.TEST_READ_CELLS["main-v2"].items())
    need = tokens + len(BENCHES) * protocol.MAIN_RESERVATIONS * protocol.READ_RESERVATION
    plan = protocol.PILOTS["main-v2"]
    assert plan["test_read_cap"] == math.ceil(Fraction(3 * need) / 10 ** 6) * 10 ** 6 == 608_000_000
    assert plan["solver_cap"] == math.ceil(Fraction(sum(sum(c.values()) for c in protocol.MAIN_V2_STEP_CAPS.values())
                                                    + plan["test_read_cap"] + plan["redo_reserve"]) / (5 * 10 ** 6)) \
        * 5 * 10 ** 6
    assert 1.3 * protocol.estimate_test_read(high, 1, "main-v2") <= plan["test_read_cap"]
    assert budgets.chain_caps("G", "main-v2")["G:test"] == plan["test_read_cap"]
    assert protocol.PILOTS["main"]["test_read_cap"] == 407_000_000  # v1 untouched
