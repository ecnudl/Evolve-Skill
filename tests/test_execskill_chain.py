"""T-CHAINS-1 subset (implementation plan §8.2, §5; registration §5, §8.1, §9.3, §9.4): the route-B chain runner --
one runner per chain, markers that name their run and chain, the pinned files verified before the start and before
every stage, a pause that returns, the one test read (not read when F = C; started only within 1.3 x its estimate;
five children under the machine-wide memory lock), a child that dies before its attempt, chain G's cost check and an
owner termination of an idle chain only; registrar addendum 2026-10-22 14:10: the first-call confirmation before the
first unit (row 7), chain G's read gate corrected by its cost factor (row 8) and the chain-level read consent check
(row 9). Offline and deterministic: a fake step, fake read children and fake solvers behind the real clients."""
from __future__ import annotations

import fcntl
import json
import os
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import weak_solver_probe
from skillopt.coevo5.budget import Budget
from skillopt.coevo5.cells import exclusive
from skillopt.coevo5.evaluation import attempts
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, chain, protocol
from skillopt.execskill.cells import Pause
from skillopt.execskill.errors import ConfigurationError
from skillopt.execskill.package import with_
from skillopt.execskill.protocol import (BENCHES, CELL_ANCHORS, CHAINS, ELUCID_MAX_TOKENS, FIRST_CALL_BENCH,
                                         FIRST_CALL_CAP, FIRST_CALL_SYSTEM, FIRST_CALL_USER, GLM_SOLVER_TOKENS, ORDER,
                                         TEST_ARMS, record, verified)
from skillopt.execskill.units import Setting
from tests.execskill_fakes import Reply, first_call_solvers, undelivered, usage, with_first_call, with_reasoning
from tests.execskill_fakes_env import procedure

EVIDENCE = "engineering_fixture"
RUN = "fixture-run"
N = procedure("p-officeqa-1-1", ("applies", "before_call"), header="Row helper notes.", evidence=EVIDENCE)
GLM, DEEPSEEK = CHAINS["G"], CHAINS["D"]
ANCHOR = CELL_ANCHORS[ORDER[0]][1]  # chain G's cost check measures its first (SpreadsheetBench) run unit
CONSENT = {"test_evaluation": True, "sheet_test_qualification": False, "multi_arm_arms": list(TEST_ARMS),
           "by": "owner", "date": "2026-10-22", "note": "fixture: read the test sets once"}


def setting(tmp_path, *, verify=None, estimate=1000, chain_="G", solvers=None, consent=True):
    """A chain's Setting on its own ledger (``budgets.ledger_root``, ticket fixer-5), whose solver clients answer the
    first-call confirmation (registrar addendum 14:10, row 7; ``solvers``: ``first_call_solvers``, "ready" by
    default), with the owner's read consent written (row 9) unless ``consent`` is False."""
    root = tmp_path / "root"
    if consent:
        write_json(root / "shared" / "consent.json", CONSENT)
    base = Setting(run=RUN, root=root, shared=root / "shared", pools={}, cards={}, runtime={}, clients=None,
                   budget=Budget(budgets.ledger_root(root, chain_)), slots={}, sandbox={}, evidence=EVIDENCE,
                   extra={"verify": verify or (lambda: None), "slot_root": str(tmp_path / "slots"),
                          "test_read_estimate": {"G": estimate, "D": estimate}})
    return with_first_call(base, solvers or first_call_solvers(tmp_path), tmp_path / "call-slots")


class Learn:
    """A fake step: step 1 accepts N, later steps accept nothing (``accept=False``: nothing at all). Chain G's step 1
    ends with its cost check (``chain.cap_check``, as ``step._run`` makes it), passed at ``per_cell`` ledger tokens per
    run cell (None: no check)."""

    def __init__(self, *, accept=True, pause_at=None, per_cell=0.25 * ANCHOR):
        self.accept, self.pause_at, self.per_cell, self.calls = accept, pause_at, per_cell, []

    def __call__(self, setting_, root, chain_, k, bench, parent):
        self.calls.append((chain_, k, bench, parent.sha256))
        if k == self.pause_at:
            raise Pause("exception", "fake_step_pause", "%s/s%d-%s" % (chain_, k, bench))
        if chain_ == "G" and k == 1 and self.per_cell is not None:
            chain.cap_check(setting_, "G", 1, {"ok": True, "per_cell": self.per_cell, "anchor_high": ANCHOR,
                                               "scopes": {"G:solver": {"cap": 10, "projected": 1}}})
        package = with_(parent, step="%s/s%d" % (chain_, k), add=[N]) if self.accept and k == 1 else parent
        return package, record("step", EVIDENCE, {"chain": chain_, "k": k, "bench": bench})


def probe(path, mode):
    """True when ``mode`` can be taken on the lock file at once (another open file description)."""
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, mode | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(descriptor)


class Launch:
    """A fake read child: writes the unit's record; on SpreadsheetBench and ALFWorld it checks the memory lock."""

    def __init__(self, tmp_path, *, code=0, write=True):
        self.lock = tmp_path / "slots" / chain.HEAVY_LOCK
        self.code, self.write, self.specs, self.locks = code, write, [], {}

    def __call__(self, setting_, spec):
        self.specs.append(spec)
        if spec["bench"] == "spreadsheetbench":
            self.locks["spreadsheetbench"] = (probe(self.lock, fcntl.LOCK_SH), probe(self.lock, fcntl.LOCK_EX))
        if spec["bench"] == "alfworld":
            self.locks["alfworld"] = (probe(self.lock, fcntl.LOCK_SH), probe(self.lock, fcntl.LOCK_EX))
        if self.write:
            root = Path(spec["unit_root"])
            root.mkdir(parents=True, exist_ok=True)
            write_json(root / "unit.json", record("evaluation", EVIDENCE, {
                "run": setting_.run, "chain": spec["chain"], "bench": spec["bench"],
                "packages": {"F": spec["package_sha256"]}}))
        return self.code


def test_chain_runs_its_steps_then_reads_once_under_the_memory_lock(tmp_path):
    verified_calls = []
    s = setting(tmp_path, verify=lambda: verified_calls.append(1))
    learn, launch = Learn(), Launch(tmp_path)
    assert chain.run(s, "G", learn=learn, launch=launch) == {"status": "complete"}
    assert [(c, k, b) for c, k, b, _ in learn.calls] == [("G", k, b) for k, b in enumerate(ORDER, 1)]
    assert len(verified_calls) == 1 + len(ORDER) + 1  # before the start, before every step, before the read
    root = tmp_path / "root" / "G"
    assert verified(read_json(root / "chain.json"), "chain")["identity"] == {"run": RUN, "chain": "G"}
    final = verified(read_json(root / "chain-complete.json"), "chain-complete")
    assert verified(read_json(root / "test-read.json"), "test-read")["status"] == "read"
    assert sorted(spec["bench"] for spec in launch.specs) == sorted(BENCHES)
    assert {spec["package_sha256"] for spec in launch.specs} == {final["package_sha256"]}
    # SpreadsheetBench holds the lock alone; ALFWorld shares it (another ALFWorld unit may run), never with SB
    assert launch.locks == {"spreadsheetbench": (False, False), "alfworld": (True, False)}
    assert chain.run(s, "G", learn=Learn(), launch=Launch(tmp_path)) == {"status": "complete"}  # ended: no rerun
    assert Budget(budgets.ledger_root(tmp_path / "root", "G")).snapshot()["G:test"]["settled"] == 0


def test_one_runner_per_chain_and_markers_of_another_run_stop(tmp_path):
    s = setting(tmp_path)
    root = tmp_path / "root" / "G"
    root.mkdir(parents=True)
    with exclusive(root / chain.RUNNER_LOCK):
        with pytest.raises(ValueError, match="Another process owns"):
            chain.run(s, "G", learn=Learn(), launch=Launch(tmp_path))
    write_json(root / "chain.json", record("chain", EVIDENCE, {"identity": {"run": "other", "chain": "G"}}))
    with pytest.raises(ValueError, match="A chain of another run"):
        chain.run(s, "G", learn=Learn(), launch=Launch(tmp_path))
    with pytest.raises(ValueError, match="Unknown chain"):
        chain.run(s, "E", learn=Learn(), launch=Launch(tmp_path))


def test_a_mismatch_refuses_the_start_and_terminates_a_started_chain(tmp_path):
    def broken():
        raise ValueError("pinned file differs")

    learn = Learn()
    with pytest.raises(ValueError, match="pinned file differs"):
        chain.run(setting(tmp_path, verify=broken), "D", learn=learn, launch=Launch(tmp_path))
    assert learn.calls == [] and [p.name for p in (tmp_path / "root" / "D").iterdir()] == [chain.RUNNER_LOCK]

    calls = []

    def later():  # route B's check (manifest.verify_unit) raises ConfigurationError
        calls.append(1)
        if len(calls) == 3:  # the check before step 2
            raise ConfigurationError("image differs")

    s = setting(tmp_path, verify=later, chain_="D")
    assert chain.run(s, "D", learn=learn, launch=Launch(tmp_path)) == {"status": "terminated",
                                                                        "reason": "manifest_mismatch"}
    assert len(learn.calls) == 1
    ended = verified(read_json(tmp_path / "root" / "D" / "chain-terminated.json"), "chain-terminated")
    assert ended["by"] == "protocol" and ended["decision"].startswith("manifest_mismatch")
    assert chain.run(s, "D", learn=Learn(), launch=Launch(tmp_path)) == {"status": "terminated"}


def test_nothing_accepted_is_not_read_and_a_pause_returns(tmp_path):
    launch = Launch(tmp_path)
    assert chain.run(setting(tmp_path, chain_="D"), "D", learn=Learn(accept=False), launch=launch) == {
        "status": "complete"}
    found = verified(read_json(tmp_path / "root" / "D" / "test-read.json"), "test-read")
    assert found["status"] == "not_read" and launch.specs == []

    result = chain.run(setting(tmp_path), "G", learn=Learn(pause_at=2), launch=launch)
    assert result == {"status": "paused", "kind": "exception", "reason": "fake_step_pause",
                      "unit": "G/s2-%s" % ORDER[1]}
    assert not (tmp_path / "root" / "G" / "chain-complete.json").exists()


def test_the_read_starts_only_within_its_budget(tmp_path):
    s = setting(tmp_path, estimate=10 ** 12)
    launch = Launch(tmp_path)
    result = chain.run(s, "G", learn=Learn(), launch=launch)
    assert result["status"] == "paused" and result["kind"] == "test_read_budget" and launch.specs == []
    assert not (tmp_path / "root" / "G" / "test-read.json").exists()
    with pytest.raises(ValueError, match="estimate"):
        chain.read_budget(setting(tmp_path, estimate=0), "G")


def test_a_child_that_dies_before_its_attempt_leaves_a_paused_attempt(tmp_path):
    s = setting(tmp_path)
    result = chain.run(s, "G", learn=Learn(), launch=Launch(tmp_path, code=1, write=False))
    assert result == {"status": "paused", "kind": "exception", "reason": "child_failed_before_its_attempt",
                      "unit": "G/test/%s" % BENCHES[0]}
    for bench in BENCHES:
        status = verified(read_json(tmp_path / "root" / "G" / "test" / bench / "attempt-1" / "status.json"),
                          "unit-status")
        assert status["exit"] == 1 and status["kind"] == "exception"
    again = chain.run(s, "G", learn=Learn(), launch=Launch(tmp_path, code=chain.EXIT_AWAITING, write=False))
    assert again["kind"] == "awaiting_owner_decision" and again["reason"] == "attempt-1"
    assert not (tmp_path / "root" / "G" / "test" / BENCHES[0] / "attempt-2").exists()


def test_chain_g_cost_check_pauses_chain_g_only(tmp_path):
    s = setting(tmp_path)
    breach = {"ok": False, "scopes": {"G:solver": {"cap": 10, "projected": 12}}}
    assert chain.cap_check(s, "D", 1, breach) is None and chain.cap_check(s, "G", 2, breach) is None
    with pytest.raises(ValueError, match="chain-G scopes"):
        chain.cap_check(s, "G", 1, {"ok": True, "scopes": {"D:solver": {"cap": 10, "projected": 1}}})
    with pytest.raises(Pause) as paused:
        chain.cap_check(s, "G", 1, breach)
    assert paused.value.kind == "cap_check" and paused.value.cell == "G/s1"
    assert verified(read_json(tmp_path / "root" / "G" / chain.CAP_CHECK), "cap-check")["ok"] is False
    passed = setting(tmp_path / "other")
    assert chain.cap_check(passed, "G", 1, {"ok": True, "scopes": {"G:solver": {"cap": 10, "projected": 9}}})["ok"]


def test_an_owner_raise_lets_chain_g_pass_its_cost_check_again(tmp_path):
    """Ticket C2-2: a restart with unchanged caps rewrites the same check and pauses again; after an owner's raise_cap
    the re-check is a new record next to the first, and the chain goes on."""
    s = setting(tmp_path)
    breach = {"ok": False, "scopes": {"G:solver": {"cap": 10, "projected": 12}}}
    for _ in range(2):
        with pytest.raises(Pause):
            chain.cap_check(s, "G", 1, breach)
    raised = {"ok": True, "scopes": {"G:solver": {"cap": 15, "projected": 12}}}
    assert chain.cap_check(s, "G", 1, raised)["ok"] and chain.cap_check(s, "G", 1, raised)["ok"]
    root = tmp_path / "root" / "G"
    assert sorted(p.name for p in root.glob("cap-check-G*.json")) == ["cap-check-G-2.json", chain.CAP_CHECK]
    assert verified(read_json(root / chain.CAP_CHECK), "cap-check")["ok"] is False
    assert verified(read_json(root / "cap-check-G-2.json"), "cap-check")["scopes"]["G:solver"]["cap"] == 15


def test_only_an_idle_chain_is_terminated(tmp_path):
    s = setting(tmp_path)
    root = tmp_path / "root" / "D"
    with exclusive(root / "test" / "officeqa" / ".lock"):
        with pytest.raises(ValueError, match="still running"):
            chain.terminate(s, "D", decision="stop the pilot")
    with exclusive(root / chain.RUNNER_LOCK):
        with pytest.raises(ValueError, match="Another process owns"):
            chain.terminate(s, "D", decision="stop the pilot")
    with pytest.raises(ValueError, match="decision"):
        chain.terminate(s, "D", decision=" ")
    chain.terminate(s, "D", decision="stop the pilot")
    ended = verified(read_json(root / "chain-terminated.json"), "chain-terminated")
    assert ended["by"] == "owner" and ended["identity"] == {"run": RUN, "chain": "D"}
    with pytest.raises(ValueError, match="The chain has ended"):
        chain.terminate(s, "D", decision="again")
    assert chain.run(s, "D", learn=Learn(), launch=Launch(tmp_path)) == {"status": "terminated"}


# ---------------------------------------------- registrar addendum 2026-10-22 14:10, row 7: first-call confirmation
def test_row7_one_confirmed_reply_alone_before_the_first_unit_and_a_relaunch_reuses_it(tmp_path):
    solvers = first_call_solvers(tmp_path)
    s = setting(tmp_path, solvers=solvers)
    root, seen = tmp_path / "root" / "G", []

    class Watch(Learn):  # what each step finds when it starts
        def __call__(self, setting_, chain_root, chain_, k, bench, parent):
            seen.append((k, len(solvers[GLM].requests), (chain_root / chain.CONFIRM).exists()))
            return super().__call__(setting_, chain_root, chain_, k, bench, parent)

    assert chain.run(s, "G", learn=Watch(pause_at=2), launch=Launch(tmp_path))["reason"] == "fake_step_pause"
    assert seen == [(1, 1, True), (2, 1, True)]  # one call, confirmed before step 1, nothing sent beside it
    assert solvers[DEEPSEEK].requests == []  # through the chain's own solver only
    request = solvers[GLM].requests[0]
    assert [m["content"] for m in request["messages"]] == [FIRST_CALL_SYSTEM, FIRST_CALL_USER]  # no pool item
    assert request["max_tokens"] == GLM_SOLVER_TOKENS  # chain G's registered M (= B)
    found = verified(read_json(root / chain.CONFIRM), "first-call")
    assert found["passed"] is True and found["identity"] == {"run": RUN, "chain": "G"} and found["error"] is None
    assert (found["model"], found["returned_model"], found["bench"]) == (GLM, GLM, FIRST_CALL_BENCH)
    assert (found["max_tokens"], found["bound"], found["charged"]) == (GLM_SOLVER_TOKENS, GLM_SOLVER_TOKENS, 15)
    assert found["reserved"] == 4 * (len((FIRST_CALL_SYSTEM + FIRST_CALL_USER).encode()) + 512 + GLM_SOLVER_TOKENS)
    assert found["scopes"] == ["overall", "G:solver", "G:confirm"] and found["usage"]["total_tokens"] == 15
    assert found["checks"] == {"reply": True, "model": True, "settled": True, "reasoning": None}
    assert found["attempts"] == [200] and type(found["seconds"]) is float
    assert "ready" not in json.dumps(found) and len(found["reply_sha256"]) == 64  # hashes, never the reply
    ledger = Budget(budgets.ledger_root(tmp_path / "root", "G")).snapshot()
    assert (ledger["G:confirm"]["cap"], ledger["G:confirm"]["settled"], ledger["G:confirm"]["open"]) == (
        FIRST_CALL_CAP, 15, 0)
    assert ledger["G:solver"]["settled"] == 15
    # a relaunch reuses confirm.json: no second call
    assert chain.run(s, "G", learn=Watch(), launch=Launch(tmp_path)) == {"status": "complete"}
    assert len(solvers[GLM].requests) == 1 and not list(root.glob("confirm-failed-*"))


@pytest.mark.parametrize("chain_, reply, failed", [
    ("G", undelivered("http_400"), ["reply", "model", "settled"]),  # refused: nothing settled
    ("D", Reply(text=None, usage=None, failure="transport"), ["reply", "model", "settled", "reasoning"]),
    ("G", undelivered("http_503"), ["reply", "model"]),  # four server errors, each charged at its full bound
    ("G", Reply(text="ready", model="glm-4.6"), ["reply", "model"]),  # another model's echo
    ("D", Reply(text=""), ["reply"]),
    ("G", Reply(text="rea", finish="length"), ["reply"]),
    ("D", with_reasoning("ready"), ["reply", "reasoning"]),  # chain D's reasoning receipt check
    ("D", Reply(text="ready", usage=usage(0, prompt=0)), ["settled"]),
], ids=["refused", "transport", "server-error", "model-echo", "empty", "truncated", "reasoning", "zero-settled"])
def test_row7_each_failure_stops_the_chain_before_its_first_unit_and_a_relaunch_calls_again(
        tmp_path, monkeypatch, chain_, reply, failed):
    monkeypatch.setattr(weak_solver_probe.time, "sleep", lambda seconds: None)  # the frozen client's retry backoff
    solvers, learn, model = first_call_solvers(tmp_path, reply), Learn(), CHAINS[chain_]
    result = chain.run(setting(tmp_path, chain_=chain_, solvers=solvers), chain_, learn=learn, launch=Launch(tmp_path))
    assert result["status"] == "paused" and result["kind"] == "first_call_unconfirmed"
    assert result["unit"] == "%s/confirm" % chain_ and learn.calls == []  # stopped before its first unit
    root = tmp_path / "root" / chain_
    kept = verified(read_json(root / (chain.CONFIRM_FAILED % 1)), "first-call")
    assert kept["passed"] is False and [name for name, ok in kept["checks"].items() if ok is False] == failed
    assert sorted(p.name for p in root.iterdir()) == sorted(  # no unit attempt was opened
        [chain.RUNNER_LOCK, "chain.json", chain.CONFIRM_FAILED % 1])
    assert solvers[model].requests and {r["messages"][1]["content"] for r in solvers[model].requests} == {
        FIRST_CALL_USER}
    # the main agent checks network and TLS and relaunches run: the chain calls again and goes on
    good = first_call_solvers(tmp_path)
    assert chain.run(setting(tmp_path, chain_=chain_, solvers=good), chain_, learn=learn,
                     launch=Launch(tmp_path)) == {"status": "complete"}
    assert len(good[model].requests) == 1 and verified(read_json(root / chain.CONFIRM), "first-call")["passed"]
    if chain_ == "D":
        assert good[model].requests[0]["max_tokens"] == ELUCID_MAX_TOKENS[FIRST_CALL_BENCH]


def test_row7_a_configuration_or_cap_failure_pauses_too_and_nothing_is_sent(tmp_path):
    solvers = first_call_solvers(tmp_path)
    s = setting(tmp_path, solvers=solvers)
    root = tmp_path / "root" / "G"
    result = chain.run(replace(s, slots={}), "G", learn=Learn(), launch=Launch(tmp_path))  # no slot pool
    assert result["kind"] == "first_call_unconfirmed" and "ConfigurationError: No slot pool" in result["reason"]
    kept = verified(read_json(root / (chain.CONFIRM_FAILED % 1)), "first-call")
    assert kept["error"] == "ConfigurationError" and kept["request_sha256"] is None and solvers[GLM].requests == []
    # the confirmation's own cap bounds the relaunches: spent (here by earlier full-bound charges), it is refused
    rid = s.budget.reserve(budgets.first_call_scopes("G"), FIRST_CALL_CAP - 1_000, label="earlier",
                           generation=s.budget.generation())
    s.budget.settle(rid, FIRST_CALL_CAP - 1_000, detail={})
    result = chain.run(s, "G", learn=Learn(), launch=Launch(tmp_path))
    assert result["kind"] == "first_call_unconfirmed" and "BudgetStop" in result["reason"]
    assert verified(read_json(root / (chain.CONFIRM_FAILED % 2)), "first-call")["error"] == "BudgetStop"
    assert solvers[GLM].requests == [] and not (root / chain.CONFIRM).exists()


def test_row7_a_relaunch_checks_the_pins_before_it_calls_again(tmp_path):
    solvers, checked = first_call_solvers(tmp_path, undelivered("http_400")), []
    s = setting(tmp_path, verify=lambda: checked.append(len(solvers[GLM].requests)), solvers=solvers)
    assert chain.run(s, "G", learn=Learn(), launch=Launch(tmp_path))["kind"] == "first_call_unconfirmed"
    assert checked == [0]  # the start's check only: the first launch had just made it

    def broken():
        raise ConfigurationError("image differs")

    assert chain.run(setting(tmp_path, verify=broken, solvers=solvers), "G", learn=Learn(),
                     launch=Launch(tmp_path)) == {"status": "terminated", "reason": "manifest_mismatch"}
    assert len(solvers[GLM].requests) == 1  # no second call on a changed snapshot


class Stub:
    """A solver client whose every receipt claims a delivered reply (``receipt``): the confirmation's own checks,
    apart from the real clients' refusals."""

    def __init__(self, model, receipt):
        self.model, self.receipt, self.calls = model, receipt, 0
        self.max_tokens = GLM_SOLVER_TOKENS if model == GLM else ELUCID_MAX_TOKENS[FIRST_CALL_BENCH]

    def call(self, system, user):
        self.calls += 1
        return dict(self.receipt)


def delivered(model, **changes):
    """A receipt of the registered model's delivered reply, as the chain's client builds one, with ``changes``
    (None removes a field)."""
    receipt = {"status": 200, "ok": True, "response": "ready", "finish_reason": "stop",
               "usage": usage(5), "usage_valid": True, "returned_model": model, "reasoning_chars": 0,
               "attempts": [{"status": 200, "seconds": 0.1}], "seconds": 0.1}
    if model == DEEPSEEK:
        receipt.update(reasoning_tokens=None, visible_completion_tokens=5, over_nominal=False)
    receipt.update(changes)
    return {key: value for key, value in receipt.items() if not (key in changes and value is None)}


@pytest.mark.parametrize("chain_, changes, failed", [
    ("G", {"returned_model": "glm-4.6"}, ["model"]),
    ("D", {"returned_model": "deepseek-v4-flash"}, ["model"]),
    ("D", {"reasoning_tokens": 7}, ["reasoning"]),
    ("D", {"reasoning_chars": 12}, ["reasoning"]),
    ("D", {"reasoning_tokens": None}, ["reasoning"]),  # a receipt the elucid reasoning check never saw
], ids=["g-echo", "d-echo", "d-reasoning-tokens", "d-reasoning-text", "d-unchecked"])
def test_row7_the_confirmations_own_checks_hold_whatever_the_client_reports(tmp_path, chain_, changes, failed):
    model = CHAINS[chain_]
    stub = Stub(model, delivered(model, **changes))
    s = with_first_call(setting(tmp_path, chain_=chain_), {model: SimpleNamespace(client=stub)}, tmp_path / "slots2")
    result = chain.run(s, chain_, learn=Learn(), launch=Launch(tmp_path))
    assert result["kind"] == "first_call_unconfirmed" and stub.calls == 1
    kept = verified(read_json(tmp_path / "root" / chain_ / (chain.CONFIRM_FAILED % 1)), "first-call")
    assert [name for name, ok in kept["checks"].items() if ok is False] == failed
    stub.receipt = delivered(model)  # the registered receipt passes
    assert chain.run(s, chain_, learn=Learn(), launch=Launch(tmp_path)) == {"status": "complete"}


# ---------------------------------------- registrar addendum 2026-10-22 14:10, row 8: chain G's corrected read gate
def test_row8_chain_g_reads_within_1_3_x_its_estimate_corrected_by_its_cost_factor(tmp_path):
    estimate = 1_000_001
    s = setting(tmp_path, estimate=estimate)
    assert chain.run(s, "G", learn=Learn(per_cell=1.5 * ANCHOR), launch=Launch(tmp_path)) == {"status": "complete"}
    root = tmp_path / "root" / "G"
    gate = verified(read_json(root / chain.TEST_READ), "test-read")["gate"]
    check = verified(read_json(root / chain.CAP_CHECK), "cap-check")
    assert gate == {"estimate": estimate, "units": list(BENCHES), "part": estimate, "factor": 1.5, "used": 1_500_002,
                    "need": 1_950_003,  # ceil, then ceil(1.3 x used) (registrar addendum 15:3x: no 1-token shortfall)
                    "cap_check": {"file": chain.CAP_CHECK, "record_sha256": check["record_sha256"]}}
    low = setting(tmp_path / "low", estimate=estimate)  # a factor below 1 never lowers the estimate
    assert chain.run(low, "G", learn=Learn(per_cell=0.5 * ANCHOR), launch=Launch(tmp_path / "low")) == {
        "status": "complete"}
    gate = verified(read_json(tmp_path / "low" / "root" / "G" / chain.TEST_READ), "test-read")["gate"]
    assert (gate["factor"], gate["used"], gate["need"]) == (0.5, estimate, 1_300_002)


def test_row8_chain_gs_factor_can_pause_its_read_and_chain_d_reads_its_estimate(tmp_path):
    estimate = 50 * 10 ** 6  # 1.3 x 50M fits the 99M test-read cap; 1.3 x 2 x 50M does not
    launch = Launch(tmp_path / "g")
    paused = chain.run(setting(tmp_path / "g", estimate=estimate), "G", learn=Learn(per_cell=2.0 * ANCHOR),
                       launch=launch)
    assert paused["kind"] == "test_read_budget" and "100000000" in paused["reason"] and launch.specs == []
    d = setting(tmp_path / "d", estimate=estimate, chain_="D")
    assert chain.run(d, "D", learn=Learn(), launch=Launch(tmp_path / "d")) == {"status": "complete"}
    gate = verified(read_json(tmp_path / "d" / "root" / "D" / chain.TEST_READ), "test-read")["gate"]
    assert gate == {"estimate": estimate, "units": list(BENCHES), "part": estimate, "factor": None, "cap_check": None,
                    "used": estimate, "need": 65_000_000}


def test_row8_the_gate_reads_chain_gs_latest_passed_cost_check_and_needs_one(tmp_path):
    s = setting(tmp_path, estimate=1000)
    s.budget.declare(budgets.chain_caps("G"))
    with pytest.raises(ValueError, match="cost check"):
        chain.read_budget(s, "G")
    breach = {"ok": False, "per_cell": 9.0 * ANCHOR, "anchor_high": ANCHOR,
              "scopes": {"G:solver": {"cap": 10, "projected": 12}}}
    with pytest.raises(Pause):
        chain.cap_check(s, "G", 1, breach)
    with pytest.raises(ValueError, match="cost check"):  # the latest check did not pass
        chain.read_budget(s, "G")
    raised = chain.cap_check(s, "G", 1, {"ok": True, "per_cell": 3.0 * ANCHOR, "anchor_high": ANCHOR,
                                         "scopes": {"G:solver": {"cap": 15, "projected": 12}}})
    gate = chain.read_budget(s, "G")
    assert gate["cap_check"] == {"file": "cap-check-G-2.json", "record_sha256": raised["record_sha256"]}
    assert (gate["factor"], gate["used"], gate["need"]) == (3.0, 3000, 3900)
    path, found = chain.latest_cap_check(s)
    assert path.name == "cap-check-G-2.json" and found == raised


class PartLaunch(Launch):
    """A fake read child that completes the units of ``done`` only; the others end before their attempt."""

    def __init__(self, tmp_path, done):
        super().__init__(tmp_path)
        self.done = set(done)

    def __call__(self, setting_, spec):
        if spec["bench"] in self.done:
            return super().__call__(setting_, spec)
        self.specs.append(spec)
        return chain.EXIT_PAUSED


def test_p2c_2_a_relaunched_read_gate_prices_only_the_read_units_still_to_run(tmp_path):
    """Registrar addendum 2026-10-22 15:3x, ticket P2C-2: after some read units completed and the read spent part of
    ``D:test``, a relaunch gates 1.3 x the estimate of the units not yet complete -- ceil of the sum of their
    per-bench terms (``data.test_read_terms``) -- not the whole estimate again; the completing launch's gate is
    recorded. A first start gates the whole estimate (the terms are not read)."""
    estimate = 70 * 10 ** 6  # 1.3 x 70M = 91M fits the 99M test-read cap once
    terms = {"searchqa": "30000000/1", "officeqa": "20000000/1", "livemath": "9999999/1",
             "spreadsheetbench": "6000001/2", "alfworld": "7000000/1"}  # sum 69,999,999.5: its ceiling is the estimate
    s = setting(tmp_path, estimate=estimate, chain_="D")
    s = replace(s, extra={**s.extra, "test_read_terms": {"D": terms}})
    first = PartLaunch(tmp_path, done=("searchqa", "officeqa", "livemath"))
    assert chain.run(s, "D", learn=Learn(), launch=first)["status"] == "paused"
    assert sorted(spec["bench"] for spec in first.specs) == sorted(BENCHES)
    rid = s.budget.reserve((budgets.ROOT, "D:solver", "D:test"), 60 * 10 ** 6, label="the read so far",
                           generation=s.budget.generation())
    s.budget.settle(rid, 60 * 10 ** 6, detail={})  # 39M left on D:test < 91M, the whole estimate's need
    rest = [b for b in BENCHES if b in ("spreadsheetbench", "alfworld")]
    gate = chain.read_budget(s, "D")
    assert gate == {"estimate": estimate, "units": rest, "part": 10_000_001, "factor": None, "cap_check": None,
                    "used": 10_000_001, "need": 13_000_002}  # ceil(3,000,000.5 + 7M), then ceil(1.3 x)
    again = Launch(tmp_path)
    assert chain.run(s, "D", learn=Learn(), launch=again) == {"status": "complete"}
    assert sorted(spec["bench"] for spec in again.specs) == sorted(rest)
    read = verified(read_json(tmp_path / "root" / "D" / chain.TEST_READ), "test-read")
    assert read["status"] == "read" and read["gate"] == gate
    lean = setting(tmp_path / "lean", estimate=estimate, chain_="D")  # a part that no longer fits still pauses
    lean = replace(lean, extra={**lean.extra, "test_read_terms": {"D": terms}})
    assert chain.run(lean, "D", learn=Learn(), launch=PartLaunch(tmp_path / "lean", done=("searchqa",)))[
        "status"] == "paused"
    rid = lean.budget.reserve((budgets.ROOT, "D:solver", "D:test"), 60 * 10 ** 6, label="the read so far",
                              generation=lean.budget.generation())
    lean.budget.settle(rid, 60 * 10 ** 6, detail={})  # 39M left < 1.3 x ceil(39,999,999.5)
    paused = chain.run(lean, "D", learn=Learn(), launch=Launch(tmp_path / "lean"))
    assert paused["kind"] == "test_read_budget" and "officeqa, livemath, spreadsheetbench, alfworld" in paused["reason"]
    missing = setting(tmp_path / "missing", estimate=estimate, chain_="D")  # no terms: a relaunch cannot be priced
    (chain.unit_root(missing, "D", "searchqa")).mkdir(parents=True)
    write_json(chain.unit_root(missing, "D", "searchqa") / "unit.json", {})
    missing.budget.declare(budgets.chain_caps("D"))
    with pytest.raises(ValueError, match="per-bench terms"):
        chain.read_budget(missing, "D")


# ------------------------------------------- registrar addendum 2026-10-22 14:10, row 9: the chain's read consent
def test_row9_a_missing_consent_opens_no_read_attempt_and_the_relaunch_reads(tmp_path):
    s = setting(tmp_path, consent=False)
    launch, consent = Launch(tmp_path), tmp_path / "root" / "shared" / "consent.json"
    root = tmp_path / "root" / "G"
    for _ in range(2):  # a relaunch while the consent is still missing rewrites the same record
        result = chain.run(s, "G", learn=Learn(), launch=launch)
        assert (result["status"], result["kind"], result["unit"]) == ("paused", "consent_missing", "G/test")
    assert launch.specs == [] and all(attempts(chain.unit_root(s, "G", bench)) == [] for bench in BENCHES)
    waiting = verified(read_json(root / chain.READ_WAITING), "read-waiting")
    assert waiting["identity"] == {"run": RUN, "chain": "G"} and {
        key: waiting[key] for key in ("kind", "read_units", "read_attempts", "units_complete")} == {
        "kind": "consent_missing", "read_units": 5, "read_attempts": 0, "units_complete": 0}
    assert not (root / chain.TEST_READ).exists()
    write_json(consent, {**CONSENT, "by": "operator"})  # an invalid consent is no consent
    assert chain.run(s, "G", learn=Learn(), launch=launch)["kind"] == "consent_missing"
    consent.unlink()
    (chain.unit_root(s, "G", "officeqa") / "attempt-1").mkdir(parents=True)  # the counts changed: never rewritten
    with pytest.raises(ValueError, match="differs"):
        chain.run(s, "G", learn=Learn(), launch=launch)
    (chain.unit_root(s, "G", "officeqa") / "attempt-1").rmdir()
    write_json(consent, CONSENT)  # the owner writes the consent; the main agent relaunches run
    assert chain.run(s, "G", learn=Learn(), launch=launch) == {"status": "complete"}
    assert sorted(spec["bench"] for spec in launch.specs) == sorted(BENCHES)
    assert verified(read_json(root / chain.TEST_READ), "test-read")["status"] == "read"


# ------------------------------------------- registrar "Owner instructions 2026-10-22 17:0x and 17:3x": main (M1)
def main_setting(tmp_path, **options):
    """A chain Setting of the ``main`` configuration (``manifest.setting_of`` sets ``extra["configuration"]``)."""
    found = setting(tmp_path, **options)
    found.extra["configuration"] = protocol.MAIN
    return found


MAIN_BREACH = {"ok": False, "per_cell": 2.0 * ANCHOR, "anchor_high": ANCHOR,
               "scopes": {"G:solver": {"cap": 10, "projected": 12}}}


def test_m1_main_runs_its_five_steps_in_mains_order_on_mains_caps_after_a_searchqa_confirmation(tmp_path):
    s = main_setting(tmp_path, estimate=1000)
    learn = Learn()
    assert chain.run(s, "G", learn=learn, launch=Launch(tmp_path)) == {"status": "complete"}
    assert [(c, k, b) for c, k, b, _ in learn.calls] == [("G", k, b) for k, b in enumerate(BENCHES, 1)]
    root = tmp_path / "root" / "G"
    started = verified(read_json(root / "chain.json"), "chain")
    assert started["order"] == list(BENCHES) and started["configuration"] == "main"
    assert verified(read_json(root / chain.CONFIRM), "first-call")["bench"] == "searchqa" != FIRST_CALL_BENCH
    snapshot = Budget(budgets.ledger_root(tmp_path / "root", "G")).snapshot()
    assert snapshot["G:solver"]["cap"] == protocol.PILOTS["main"]["solver_cap"] == 1_520_000_000
    assert snapshot["G:glm"]["cap"] == protocol.MAIN_GLM_CAP
    run_scope = budgets.solver_scopes("G", "alfworld", 5, "run")[-1]
    assert snapshot[run_scope]["cap"] == protocol.MAIN_STEP_CAPS["alfworld"]["run"]
    assert snapshot["G:xs:alfworld:5:role:examiner:research"]["cap"] == 9_200_000  # registrar 17:0x role scopes
    assert snapshot["G:xs:searchqa:1:role:engineer"]["cap"] == snapshot["G:xs:searchqa:1:role:examiner"]["cap"] == (
        5_000_000)
    check = verified(read_json(root / chain.CAP_CHECK), "cap-check")
    assert (check["configuration"], check["pauses"]) == ("main", False)


def test_m1_mains_cost_check_records_a_breach_never_pauses_and_the_read_gate_applies_its_factor(tmp_path):
    """Registrar 17:0x: in main chain G's cost check records its factor and never pauses; the read gate still applies
    the factor (``read_budget``). A pilot's gate never takes such a record-only check, and a pilot still pauses."""
    s = main_setting(tmp_path, estimate=1000)
    inner = Learn(per_cell=None)

    def learn(setting_, root, chain_, k, bench, parent):
        if k == 1:
            found = chain.cap_check(setting_, "G", 1, MAIN_BREACH)  # no Pause in main
            assert found["ok"] is False and found["pauses"] is False and found["configuration"] == "main"
        return inner(setting_, root, chain_, k, bench, parent)

    assert chain.run(s, "G", learn=learn, launch=Launch(tmp_path)) == {"status": "complete"}
    gate = verified(read_json(tmp_path / "root" / "G" / chain.TEST_READ), "test-read")["gate"]
    assert (gate["factor"], gate["used"], gate["need"]) == (2.0, 2000, 2600)
    path, found = chain.latest_cap_check(s)
    assert path.name == chain.CAP_CHECK and found["ok"] is False
    pilot = setting(tmp_path)  # the same run root read as the default configuration: not its check
    with pytest.raises(ValueError, match="cost check"):
        chain.latest_cap_check(pilot)
    other = setting(tmp_path / "pilot")
    with pytest.raises(Pause) as paused:
        chain.cap_check(other, "G", 1, MAIN_BREACH)
    assert paused.value.kind == "cap_check"
    with pytest.raises(ValueError, match="cost check"):  # a pilot's breach is no passed check
        chain.latest_cap_check(other)


def test_m1_mains_cost_projection_prices_each_cap_at_a_third(tmp_path):
    """``step.cost_projection`` divides every chain-G cap by its configuration's factor (main 3, the pilots 3/2)."""
    from skillopt.execskill import step

    ledger = Budget(budgets.ledger_root(tmp_path, "G"), sleep=lambda _: None)
    ledger.declare({**budgets.chain_caps("G", "main"), **budgets.first_call_caps("G")})
    found_setting = SimpleNamespace(budget=ledger, extra={"configuration": protocol.MAIN})
    high = CELL_ANCHORS["searchqa"][1]
    scopes = budgets.solver_scopes("G", "searchqa", 1, "run")
    rid = ledger.reserve(scopes, 2 * high, label="cell", generation=ledger.generation())
    ledger.settle(rid, 2 * high, detail={})  # one cell at twice the anchor
    found = step.cost_projection(found_setting, "G", "searchqa", 1, 1)
    assert found["per_cell"] == 2 * high and found["anchor_high"] == high
    assert all(row["projected"] == -(-row["cap"] * 2 // 3) for row in found["scopes"].values())
    assert found["ok"] is True  # twice the anchor fits caps of 3 x the need
    assert budgets.solver_scopes("G", "searchqa", 1, "run")[-1] in found["scopes"]


# -------------------------------------------------------------------------- the memory lock of a mixed unit (#5)
def test_codex5_a_unit_takes_the_strongest_memory_lock_of_every_bench_it_runs():
    """Codex finding #5 (registration §2.6, §11): the lock follows every bench whose cells a unit runs -- exclusive
    with any SpreadsheetBench cell, shared with ALFWorld cells, none for question-answer benches only."""
    assert chain.heavy_mode(("searchqa",)) is None and chain.heavy_mode(("officeqa", "livemath", "searchqa")) is None
    assert chain.heavy_mode(("alfworld",)) == chain.heavy_mode(("livemath", "alfworld")) == fcntl.LOCK_SH
    assert chain.heavy_mode(("officeqa", "spreadsheetbench")) == fcntl.LOCK_EX  # an OQ self-test with an SB set
    assert chain.heavy_mode(("alfworld", "officeqa", "livemath", "spreadsheetbench")) == fcntl.LOCK_EX
    assert chain.heavy_mode(BENCHES) == fcntl.LOCK_EX
    for benches in ((), ("webshop",)):
        with pytest.raises(ValueError, match="The benches a unit runs"):
            chain.heavy_mode(benches)


def test_codex5_a_self_test_with_a_spreadsheet_set_never_overlaps_the_other_chains_heavy_units(tmp_path):
    """Codex finding #5 (§2.6, §11: a SpreadsheetBench unit alone on the machine's memory, ALFWorld units beside
    ALFWorld units only): chain G's later-step self-test that runs its earlier SpreadsheetBench set holds the lock
    exclusively, so chain D's ALFWorld and SpreadsheetBench units -- another chain, the same machine-wide lock file --
    wait until it ends; a self-test of question-answer sets holds nothing, one with an ALFWorld set shares it."""
    lock, g, d = tmp_path / "slots" / chain.HEAVY_LOCK, *(
        SimpleNamespace(extra={"slot_root": str(tmp_path / "slots")}) for _ in range(2))
    events, entered = [], {bench: threading.Event() for bench in ("alfworld", "spreadsheetbench")}

    def heavy_unit(bench):  # chain D's unit
        with chain.heavy(d, bench):
            events.append(("D", bench))
            entered[bench].set()

    with chain.heavy(g, "officeqa", "spreadsheetbench", "livemath"):
        assert (probe(lock, fcntl.LOCK_SH), probe(lock, fcntl.LOCK_EX)) == (False, False)
        threads = [threading.Thread(target=heavy_unit, args=(bench,)) for bench in sorted(entered)]
        for thread in threads:
            thread.start()
        assert not any(event.wait(0.3) for event in entered.values())  # both wait for the self-test
        events.append(("G", "selftest ends"))
    for thread in threads:
        thread.join(10)
    assert all(event.is_set() for event in entered.values()) and events[0] == ("G", "selftest ends")
    assert sorted(events[1:]) == [("D", "alfworld"), ("D", "spreadsheetbench")]
    with chain.heavy(g, "officeqa", "livemath", "searchqa"):  # question-answer sets only: no lock
        assert (probe(lock, fcntl.LOCK_SH), probe(lock, fcntl.LOCK_EX)) == (True, True)
    with chain.heavy(g, "livemath", "alfworld"):  # an ALFWorld set: shared with chain D's ALFWorld unit only
        assert (probe(lock, fcntl.LOCK_SH), probe(lock, fcntl.LOCK_EX)) == (True, False)
