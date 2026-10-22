"""Integration B5 (orchestration and ops): the chain runner, the multi-arm test read, the unseal and the readout wired
together for the two chains G and D (registration §8.1, §8.2, §9.3, §21; implementation plan §8.2 subset).

This is NOT the plan §8.2 end-to-end test: ``step.py`` and ``examiner.py`` are not delivered (tickets A12-2, B4 open
item 1), so each chain's steps are a stand-in that accepts the two OfficeQA fixture procedures. What runs for real:
``chain.run`` (markers, the 1.3 x budget start rule, the memory lock), ``evaluation.evaluate`` on OfficeQA through the
real cells, shell, judge, FakeSandbox, evaluation store and canary scan, the owner's continuation file with the formal
addendum, ``evaluation.unseal`` and ``readout.readout``. The other four benches' read units are stand-in records (their
fixture panels need the test qualification or the ALFWorld environment). Each chain first makes its one confirmed
first call (registrar addendum 2026-10-22 14:10, row 7) and chain G's stand-in step 1 writes its passed cost check
(row 8). Offline and deterministic: fixture items, a stateless fake solver per chain, no model call."""
from __future__ import annotations

import itertools
import json
from dataclasses import replace
from pathlib import Path

from skillopt.coevo5.budget import Budget
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, chain, evaluation, readout
from skillopt.execskill.cells import Arm, Context
from skillopt.execskill.package import empty, with_
from skillopt.execskill.protocol import BENCHES, CELL_ANCHORS, CHAINS, ORDER, record, verified
from skillopt.execskill.units import Setting
from skillopt.validator_pilot.api import digest
from tests import test_execskill_evaluation as ev
from tests.execskill_fakes import first_call_solvers, with_first_call
from tests.execskill_fakes_env import FakeSandbox

EVIDENCE = "engineering_fixture"
RUN = "fixture-run-b5"
BENCH = "officeqa"
OWNER_FILES = {"consent.json", "owner-continuation.json"}


def panel(pinned, bench, *, access):
    assert bench == BENCH and access.unit in ("G/test/" + BENCH, "D/test/" + BENCH)
    tasks = [{"task_id": i["task_id"], "public": i["public"], "private": i["private"]} for i in ev.ITEMS]
    return tasks, {"panel_hash": digest(tasks), "excluded_without_pages": 0, "source_files": None}


class Pilot:
    """The stand-in steps (accept N and M on OfficeQA) and the in-process read children of both chains."""

    def __init__(self, tmp_path, canaries):
        self.tmp_path, self.canaries, self.finals, self.solvers = tmp_path, canaries, {}, {}

    def learn(self, setting_, chain_root, chain_, k, bench, parent):
        if chain_ == "G" and k == 1:  # chain G's passed cost check (as step._run makes it), at half the anchor
            anchor = CELL_ANCHORS[ORDER[0]][1]
            chain.cap_check(setting_, "G", 1, {"ok": True, "per_cell": anchor / 2, "anchor_high": anchor,
                                               "scopes": {"G:solver": {"cap": 10, "projected": 5}}})
        package = with_(parent, step="%s/s%d" % (chain_, k), add=[ev.N, ev.M]) if bench == BENCH else parent
        self.finals[chain_] = package
        return package, record("step", EVIDENCE, {"chain": chain_, "k": k, "bench": bench})

    def launch(self, setting_, spec):
        unit_root = Path(spec["unit_root"])
        if spec["bench"] != BENCH:  # a stand-in unit: it names its run, chain and package like a real one
            unit_root.mkdir(parents=True, exist_ok=True)
            write_json(unit_root / "unit.json", record("evaluation", EVIDENCE, {
                "run": setting_.run, "chain": spec["chain"], "bench": spec["bench"],
                "packages": {"F": spec["package_sha256"]}}))
            return chain.EXIT_COMPLETE
        name = spec["chain"]
        final = self.finals[name]
        assert final.sha256 == spec["package_sha256"]
        solver = self.solvers[name] = ev.Solver()
        slots = self.tmp_path / "slots"
        endpoint = Endpoint(solver, model=CHAINS[name], max_tokens=100, slots=Slots(slots, "solver-" + name, 2),
                            sleep=lambda _: None)
        ticks = itertools.count()
        context = Context(attempt=unit_root / "attempt-1", endpoint=endpoint, runtime=RUNTIME,
                          cards={b: ev.CARD for b in BENCHES}, native=Slots(slots, "spreadsheet-native", 1),
                          episodes=Slots(slots, "alfworld-episode", 1), worker=lambda bench: FakeSandbox(ev.HOOKS),
                          evidence=EVIDENCE, clock=lambda: float(next(ticks)))

        def placebo(cell, task):
            return Arm("placebo_y", final, placebo={"procedures": {
                ev.N.id: {"before_call": {"facts": ["A donor's row note."]}},
                ev.M.id: {"before_call": {"facts": ["A donor's column note."]}}}, "seed": "seed:" + cell["id"]})

        arms = {"F": Arm("candidate", final), "C": Arm("card", empty(step="%s/card" % name, evidence=EVIDENCE)),
                "P_F": placebo, "T_F": Arm("text", final, text={ev.N.id: "Points at the row of the year.",
                                                                ev.M.id: "Names the columns."})}
        evaluation.evaluate(unit_root, run=setting_.run, shared=setting_.shared, pinned=None, chain=name, bench=BENCH,
                            arms=arms, context=context, workers=2, route_workers=ev.route_workers,
                            canaries=self.canaries, panel=panel)
        return chain.EXIT_COMPLETE


def test_chains_g_and_d_read_once_then_unseal_and_read_out(tmp_path):
    root = tmp_path / "root"
    shared = root / "shared"
    shared.mkdir(parents=True)
    write_json(shared / "consent.json", ev.consent_value())
    canaries = [evaluation.canary(item["public"]["question"]) for item in ev.ITEMS]
    pilot = Pilot(tmp_path, canaries)
    ledgers = {name: Budget(budgets.ledger_root(root, name)) for name in ("G", "D")}  # one per chain (fixer-5)
    setting = Setting(run=RUN, root=root, shared=shared, pools={}, cards={}, runtime={}, clients=None, budget=None,
                      slots={}, sandbox={}, evidence=EVIDENCE,
                      extra={"verify": lambda: None, "slot_root": str(tmp_path / "slots"),
                             "test_read_estimate": {"G": 10 ** 6, "D": 10 ** 6}})
    setting = with_first_call(setting, first_call_solvers(tmp_path), tmp_path / "call-slots")
    for name in ("G", "D"):
        assert chain.run(replace(setting, budget=ledgers[name]), name, learn=pilot.learn,
                         launch=pilot.launch) == {"status": "complete"}
    units = {}
    for name in ("G", "D"):
        chain_root = root / name
        final = pilot.finals[name]
        done = verified(read_json(chain_root / "chain-complete.json"), "chain-complete")
        assert done["identity"] == {"run": RUN, "chain": name} and done["package_sha256"] == final.sha256
        assert verified(read_json(chain_root / chain.TEST_READ), "test-read")["status"] == "read"
        unit = verified(read_json(chain.unit_root(setting, name, BENCH) / "unit.json"), "evaluation")
        assert (unit["chain"], unit["run"], unit["packages"]["F"]) == (name, RUN, final.sha256)
        assert unit["structural_zero"] == len(ev.ZERO) and unit["counts"]["infrastructure"] == 0
        units[name] = unit
    # both chains read the same items with the same arms; each solver was called once per sent cell
    assert len(units["G"]["cells"]) == len(units["D"]["cells"])
    assert pilot.solvers["G"].calls == pilot.solvers["D"].calls > 0
    # Codex F16: no raw reply anywhere; every protocol file is a versioned record with its evidence
    for path in root.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert ev.RAW not in text and "Fixture bulletin page" not in text
            in_ledger = any(ledger.root in path.parents for ledger in ledgers.values())  # the frozen ledger's files
            if path.suffix == ".json" and path.name not in OWNER_FILES and not in_ledger:
                value = json.loads(text)
                assert value["version"].startswith("fivebench-execskill-v1-") and value["evidence"] == EVIDENCE
    # registrar decisions C3-1 (b), PR-C31-3: the run root's two canary records (S0's, and the test read's checked
    # against synthetic training pools pinned outside the root); the unseal scans the whole root for them first
    ev.s0_canaries(root)
    evaluation.make_read_canaries(root, None, pools=ev.pool_pins(tmp_path / "pools"), run=RUN, evidence=EVIDENCE,
                                  panel=ev.ReadPanel())
    # Codex F17: the owner's continuation file and an addendum hashed before the unseal -> confirmatory later reads
    write_json(shared / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "go on to the formal chain"})
    # isolation review 12: the owner writes the addendum document; this code seals its sha256 and the sealing time
    (shared / "formal-addendum.md").write_text("# Formal-chain addendum\n\nThe formal chain reads ...\n",
                                               encoding="utf-8")
    sealed = evaluation.seal_addendum(root, evidence=EVIDENCE, clock=lambda: "2026-10-22T09:00:00Z")
    assert verified(read_json(shared / "formal-addendum.json"), "formal-addendum") == sealed
    keys = {}
    for name in ("G", "D"):
        assert evaluation.continuation_check({"root": str(root)}, chain=name,
                                             clock=lambda: "2026-10-22T10:00:00Z")["label"] == \
            "interim_read_addendum_before_unseal"
        opened = evaluation.unseal(root, root / name, name, [chain.unit_root(setting, name, BENCH)], run=RUN,
                                   evidence=EVIDENCE, clock=lambda: "2026-10-22T10:00:00Z")
        assert (opened["label"], opened["later_reads"]) == ("interim_read_addendum_before_unseal", "confirmatory")
        table = opened["units"][BENCH]
        assert len(table) == len(units[name]["cells"]) and all(len(key) == 3 for key in table)
        keys[name] = sorted(key for key in table if not key[0].startswith("withhold:"))
        found = readout.readout(opened["units"], learned=[BENCH], procedures={ev.N.id: BENCH, ev.M.id: BENCH},
                                label=opened["later_reads"], evidence=EVIDENCE)
        found = verified(found, "readout")
        assert found["evidence_kind"] == "generalization" and found["learned"] == [BENCH]
        assert set(found["q1_home"]) == {BENCH} and found["q1_home"][BENCH]["mean"] > 0
        assert found["q3_noninferiority"] is None  # no dissimilar bench in this fixture read
    # the same items and the same F, C, P_F and T_F cells in both chains; the twins' seeded halves are drawn per unit
    # (router.draw_twins with the unit "<chain>/test/<bench>"), so they may differ between the chains
    assert keys["G"] == keys["D"]
    assert evaluation.read_label([root / "G", root / "D"]) == "confirmatory"
    # the ledgers: one per chain, each declaring its own chain's scopes only (ticket fixer-5)
    for name, other in (("G", "D"), ("D", "G")):
        snapshot = ledgers[name].snapshot()
        assert {name + ":solver", name + ":test"} <= set(snapshot)
        assert not any(scope.startswith(other + ":") for scope in snapshot)
