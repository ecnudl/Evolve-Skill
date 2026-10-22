"""Route-B learning units (implementation plan §1 units row; registration §3.4, §4.1, §9.3, §21) and T-ID-1 in the
copied unit loop: attempts, owner decisions and the redo limit, the stamped records, the stop kinds, the two chains'
endpoints with the ledger bound, and the cells' context. Offline and deterministic: no model, no docker."""
from __future__ import annotations

import functools
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, protocol, slots, units
from skillopt.execskill.cells import Pause
from skillopt.execskill.errors import (AssumptionBroken, BudgetStop, CleanupUnconfirmed, ConfigurationError,
                                       ConsumptionConflict, PackageInvalid, SandboxUnavailable, stop_kind)
from skillopt.execskill.protocol import kind, verified
from skillopt.execskill.registry import Registry
from skillopt.execskill.sandbox import client
from skillopt.execskill.sandbox.client import Limits, Worker
from skillopt.execskill.slots import CALL, LIVE, UnitCap
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_docker import FakeDocker
from tests.fixtures.execskill.items import searchqa_items

EVIDENCE = "engineering_fixture"
IDENTITY = {"unit": "D/s1-spreadsheetbench/run", "chain": "D", "k": 1}


def _client(model, bench):
    tokens = protocol.ROLE_MAX_TOKENS if bench is None else protocol.solver_tokens(model, bench)
    return SimpleNamespace(model=model, max_tokens=tokens, call=lambda system, user: None)


def _setting(tmp_path, branch="E", longest=None):
    budget = Budget(tmp_path / "ledger", sleep=lambda _: None)
    budget.declare(budgets.caps())
    pools = slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None)
    return units.Setting(run="fixture-run", root=tmp_path, shared=tmp_path / "shared", pools={}, cards={},
                         runtime={}, clients=_client, budget=budget, slots=pools, sandbox={"scratch": str(tmp_path)},
                         evidence=EVIDENCE, branch=branch, longest=longest, cooldown=0)


# ------------------------------------------------------------------------------------------------ the unit loop
def test_a_unit_completes_once_with_stamped_records(tmp_path):
    root, calls = tmp_path / "unit", []

    def work(attempt):
        calls.append(attempt.name)
        return {"cells": 3}

    done = units.run_unit(root, run="r", identity=IDENTITY, work=work, evidence=EVIDENCE)
    assert done["version"] == kind("unit") and verified(done, "unit") and done["attempt"] == "attempt-1"
    assert verified(read_json(root / "attempt-1" / "started.json"), "unit-started")["identity"] == IDENTITY
    assert units.run_unit(root, run="r", identity=IDENTITY, work=work, evidence=EVIDENCE) == done
    assert calls == ["attempt-1"] and units.complete(root, run="r", identity=IDENTITY) == done
    with pytest.raises(ValueError):
        units.complete(root, run="r", identity={**IDENTITY, "k": 2})


@pytest.mark.parametrize("error,expected", [
    (PackageInvalid("x"), "package"), (ConsumptionConflict("x"), "consumption"), (SandboxUnavailable("x"), "sandbox"),
    (BudgetStop("x"), "budget"), (AssumptionBroken("x"), "assumption"), (ConfigurationError("x"), "configuration"),
    (ValueError("x"), "configuration"), (RuntimeError("x"), "exception")])
def test_t_id_1_the_unit_loop_pauses_with_the_stop_kind(tmp_path, error, expected):
    def work(attempt):
        raise error

    with pytest.raises(Pause) as stop:
        units.run_unit(tmp_path / "unit", run="r", identity=IDENTITY, work=work, evidence=EVIDENCE)
    assert stop.value.kind == expected and stop.value.cell == IDENTITY["unit"]
    status = verified(read_json(tmp_path / "unit" / "attempt-1" / "status.json"), "unit-status")
    assert (status["status"], status["kind"], status["reason"]) == ("paused", expected, type(error).__name__)
    assert type(error).__name__ in (tmp_path / "unit" / "attempt-1" / "diagnostics.log").read_text()


def test_a_paused_unit_waits_for_the_owner_and_redoes_at_most_twice(tmp_path):
    root = tmp_path / "unit"

    def pause(attempt):
        raise Pause("infrastructure_incomplete", "S: 3 of 10 cells", IDENTITY["unit"])

    with pytest.raises(Pause):
        units.run_unit(root, run="r", identity=IDENTITY, work=pause, evidence=EVIDENCE)
    status = verified(read_json(root / "attempt-1" / "status.json"), "unit-status")
    assert (status["kind"], status["cell"]) == ("infrastructure_incomplete", IDENTITY["unit"])
    with pytest.raises(Pause) as waiting:
        units.run_unit(root, run="r", identity=IDENTITY, work=pause, evidence=EVIDENCE)
    assert waiting.value.kind == "awaiting_owner_decision"
    for n in (1, 2):
        write_json(root / ("attempt-%d" % n) / "recovery.json", {"by": "owner", "date": "2026-10-22",
                                                                 "decision": "redo %d" % n})
        with pytest.raises(Pause):
            units.run_unit(root, run="r", identity=IDENTITY, work=pause, evidence=EVIDENCE)
    assert sorted(p.name for p in root.glob("attempt-*")) == ["attempt-1", "attempt-2", "attempt-3"]
    write_json(root / "attempt-3" / "recovery.json", {"by": "owner", "date": "2026-10-22", "decision": "redo 3"})
    with pytest.raises(Pause) as limit:
        units.run_unit(root, run="r", identity=IDENTITY, work=lambda attempt: {}, evidence=EVIDENCE)
    assert limit.value.kind == "redo_limit" and not (root / "attempt-4").exists()
    assert units.attempt_number(root / "attempt-3") == 3 and protocol.MAX_REDOS == 2
    with pytest.raises(ValueError):
        units.attempt_number(root / "attempt-0")


# -------------------------------------------------------------------------------------------------- endpoints
def test_solver_endpoints_carry_the_ledger_bound_and_the_attempts_scopes(tmp_path):
    setting = _setting(tmp_path)
    attempt = tmp_path / "unit" / "attempt-1"
    glm = units.solver_endpoint(setting, "G", "spreadsheetbench", 1, "run", attempt)
    assert glm.model == "glm-5.3" and glm.max_tokens == protocol.GLM_SOLVER_TOKENS
    assert glm.scopes == ("overall", "G:solver", "G:xs:spreadsheetbench:1:run")
    deepseek = units.solver_endpoint(setting, "D", "officeqa", 2, "accept", tmp_path / "unit" / "attempt-2")
    assert deepseek.model == protocol.CHAINS["D"]
    assert deepseek.max_tokens == 2 * protocol.ELUCID_MAX_TOKENS["officeqa"]  # branch E: B = 2M
    assert deepseek.scopes == ("overall", "D:solver", "D:redo", "D:xs:officeqa:2:accept:attempt-2")
    narrow = units.solver_endpoint(_setting(tmp_path / "n", branch="N", longest=40_000), "D", "officeqa", 2, "run",
                                   attempt)
    assert narrow.max_tokens == max(4 * protocol.ELUCID_MAX_TOKENS["officeqa"], 60_000)
    role = units.role_endpoint(setting, "D", "examiner_research", "officeqa", 2)
    assert role.model == protocol.ROLE_MODEL and role.max_tokens == protocol.ROLE_MAX_TOKENS
    assert role.scopes == ("overall", "D:glm", "D:xs:officeqa:2:role:examiner:research")
    wrong = _setting(tmp_path / "w")
    wrong.clients = lambda model, bench: _client("glm-5.3", "officeqa")
    with pytest.raises(ValueError):
        units.solver_endpoint(wrong, "D", "officeqa", 2, "run", attempt)
    with pytest.raises(ValueError):  # a fourth attempt has no scope
        units.solver_endpoint(setting, "G", "officeqa", 2, "run", tmp_path / "unit" / "attempt-4")


def test_c7e_an_acceptance_redo_charges_its_first_run_blocks_to_the_kinds_own_scope(tmp_path):
    """Ticket C7c-2 (§9.3, owner decision #15): in attempt N >= 2 of an accept unit the ONE redone block goes to the
    redo's sub-scope and the redo reserve; the blocks no attempt started (``first_run``) to the kind's own scope."""
    setting = _setting(tmp_path)
    second = tmp_path / "unit" / "attempt-2"
    redo = units.solver_endpoint(setting, "D", "officeqa", 2, "accept", second)
    first = units.solver_endpoint(setting, "D", "officeqa", 2, "accept", second, first_run=True)
    assert redo.scopes == ("overall", "D:solver", "D:redo", "D:xs:officeqa:2:accept:attempt-2")
    assert first.scopes == ("overall", "D:solver", "D:xs:officeqa:2:accept") and first.max_tokens == redo.max_tokens
    assert units.solver_endpoint(setting, "G", "officeqa", 2, "accept", tmp_path / "unit" / "attempt-1",
                                 first_run=True).scopes == ("overall", "G:solver", "G:xs:officeqa:2:accept")
    caps = budgets.chain_caps("D")  # the sub-scope's cap is one acceptance block: min(kind cap, redo reserve)
    assert caps["D:xs:officeqa:2:accept:attempt-2"] == min(protocol.STEP_CAPS["officeqa"]["accept"],
                                                            protocol.PILOTS["default"]["redo_reserve"]) == 14_800_000
    with pytest.raises(ValueError, match="Only an acceptance round"):
        units.solver_endpoint(setting, "D", "officeqa", 2, "run", second, first_run=True)
    with pytest.raises(ValueError, match="Not an attempt directory"):
        units.solver_endpoint(setting, "D", "officeqa", 2, "accept", tmp_path / "unit", first_run=True)


def test_c7e_1_an_acceptance_rounds_g_acc_cells_go_to_the_examiners_own_scope_in_every_attempt(tmp_path):
    """Ticket C7e-1 (registrar decision 2026-10-22; registration §3.3 "它的做题费用记在考官作用域里（9.2、9.3）", §9.2,
    calc T6): the G_acc cells of an accept unit's attempt are charged to the examiner's own scope -- never to an
    accept scope, a redo sub-scope or the redo reserve -- whichever attempt of the accept unit runs them; the
    examiner unit's own redo keeps its redo scopes."""
    setting = _setting(tmp_path)
    for chain in ("G", "D"):
        for name in ("attempt-1", "attempt-2", "attempt-3"):
            found = units.solver_endpoint(setting, chain, "officeqa", 2, "examiner", tmp_path / "accept" / name,
                                          g_acc=True)
            assert found.scopes == ("overall", chain + ":solver", chain + ":xs:officeqa:2:examiner")
    redo = units.solver_endpoint(setting, "D", "officeqa", 2, "examiner", tmp_path / "generate" / "attempt-2")
    assert redo.scopes == ("overall", "D:solver", "D:redo", "D:xs:officeqa:2:examiner:attempt-2")
    for kind in ("accept", "run", "selftest"):
        with pytest.raises(ValueError, match="Only the examiner scope"):
            units.solver_endpoint(setting, "D", "officeqa", 2, kind, tmp_path / "accept" / "attempt-2", g_acc=True)
    with pytest.raises(ValueError, match="Not an attempt directory"):
        units.solver_endpoint(setting, "D", "officeqa", 2, "examiner", tmp_path / "accept", g_acc=True)


def test_the_cell_context_gives_workers_pools_and_chain_ds_nominal_m(tmp_path):
    setting = _setting(tmp_path)
    attempt = tmp_path / "unit" / "attempt-1"
    d = units.cell_context(setting, attempt, units.solver_endpoint(setting, "D", "officeqa", 2, "run", attempt))
    g = units.cell_context(setting, attempt, units.solver_endpoint(setting, "G", "officeqa", 2, "run", attempt))
    assert d.nominal == {b: protocol.solver_tokens(protocol.CHAINS["D"], b) for b in protocol.BENCHES}
    assert g.nominal == {} and d.evidence == EVIDENCE and d.native is setting.slots["spreadsheet-native"]
    assert d.episodes is setting.slots["alfworld-episode"]
    sheet, other = d.worker("spreadsheetbench"), d.worker("officeqa")
    assert isinstance(sheet, Worker) and isinstance(other, Worker) and sheet is not d.worker("spreadsheetbench")
    assert isinstance(sheet.live, UnitCap) and sheet.live.cap == protocol.LIVE_SANDBOX_UNIT_CAP["spreadsheetbench"]
    assert sheet.live is d.worker("spreadsheetbench").live  # one cap per unit attempt
    assert other.live is setting.slots[LIVE] and other.per_call is setting.slots[CALL] and other.package is None
    assert units.unit_path(tmp_path, 2, "officeqa", "accept") == tmp_path / "s2-officeqa" / "accept"
    assert units.CHAINS == {"G": {"solver": "glm-5.3", "start": "empty"},
                            "D": {"solver": protocol.CHAINS["D"], "start": "empty"}}
    assert json.dumps(units.CHAINS)


# ------------------------------------------------------------------------- unit tags and the unit drain (C5-1)
EMPTY = SimpleNamespace(sha256=digest([]), procedures=())
BOX_LIMITS = {k: Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=512, frame_bytes=1 << 20)
              for k in client.KINDS}
G_UNIT = "G/s1-spreadsheetbench/run"


@pytest.fixture
def docker(tmp_path):
    fake = FakeDocker(tmp_path / "containers")
    yield fake
    fake.close()


def _boxed(tmp_path, docker):
    """A Setting whose sandbox options start FakeDocker workers and whose ``extra`` drain is the unit drain (what
    ``manifest.setting_of`` binds)."""
    return replace(_setting(tmp_path), sandbox={"docker": docker, "limits": BOX_LIMITS, "scratch": str(tmp_path)},
                   extra={"drain": functools.partial(client.drain_unit, docker=docker)})


def _started(sandbox):
    worker = Worker(**sandbox).start(EMPTY, kind="cell")
    worker.ping()  # the container starts with the worker's first request
    return worker


def _listing(chain, unit):
    return ["ps", "-a", "--filter", "name=^/%s%s-" % (client.PREFIX, client.unit_tag(chain, unit)), "--format",
            "{{.Names}}"]


def test_c5_1_a_units_workers_carry_its_tag_and_alfworld_keeps_its_episode_slots(tmp_path, docker):
    setting = _boxed(tmp_path, docker)
    own = units.for_unit(setting, "D", "spreadsheetbench", IDENTITY["unit"])
    assert own.sandbox["tag"] == client.unit_tag("D", IDENTITY["unit"]) and "tag" not in setting.sandbox
    assert own.workers == setting.workers and own.budget is setting.budget and own.slots is setting.slots
    assert units.for_unit(setting, "G", "alfworld", "G/s2-alfworld/run").workers == units.ALFWORLD_WORKERS == 6
    worker = _started(own.sandbox)
    try:
        assert worker.names[0].startswith(client.PREFIX + own.sandbox["tag"] + "-")
    finally:
        worker.close()
    assert units.drainer(_setting(tmp_path / "plain"), "D", IDENTITY["unit"]) is None  # no drain bound: none runs
    with pytest.raises(ValueError):
        units.for_unit(setting, "D", "unknown", IDENTITY["unit"])


def test_c5_1_the_drain_runs_at_unit_end_and_a_remaining_container_pauses_the_unit(tmp_path, docker):
    setting, unit = _boxed(tmp_path, docker), IDENTITY["unit"]
    own = units.for_unit(setting, "D", "spreadsheetbench", unit)
    other = _started(units.for_unit(setting, "G", "spreadsheetbench", G_UNIT).sandbox)
    left = []

    def clean(attempt):
        _started(own.sandbox).close()
        return {"cells": 1}

    def leaves_one(attempt):
        left.append(_started(own.sandbox))
        return {"cells": 1}

    try:
        done = units.run_unit(tmp_path / "clean", run="fixture-run", identity=IDENTITY, work=clean, evidence=EVIDENCE,
                              drain=units.drainer(setting, "D", unit))
        assert done["status"] == "complete" and docker.commands[-1] == _listing("D", unit)  # the other chain's lives
        with pytest.raises(Pause) as paused:
            units.run_unit(tmp_path / "left", run="fixture-run", identity=IDENTITY, work=leaves_one,
                           evidence=EVIDENCE, drain=units.drainer(setting, "D", unit))
        assert paused.value.kind == stop_kind(CleanupUnconfirmed("x")) and paused.value.reason == "CleanupUnconfirmed"
        assert not (tmp_path / "left" / "unit.json").exists()
        assert read_json(tmp_path / "left" / "attempt-1" / "status.json")["reason"] == "CleanupUnconfirmed"
    finally:
        for worker in left + [other]:
            worker.close()


def test_c5_1_the_drain_also_runs_when_the_unit_pauses(tmp_path, docker):
    setting, unit = _boxed(tmp_path, docker), IDENTITY["unit"]
    own = units.for_unit(setting, "D", "spreadsheetbench", unit)
    left = []

    def pauses(attempt):
        _started(own.sandbox).close()
        raise Pause("solver_unavailable", "the endpoint is down", "cell-1")

    def pauses_leaving_one(attempt):
        left.append(_started(own.sandbox))
        raise Pause("solver_unavailable", "the endpoint is down", "cell-1")

    try:
        with pytest.raises(Pause) as paused:
            units.run_unit(tmp_path / "paused", run="fixture-run", identity=IDENTITY, work=pauses, evidence=EVIDENCE,
                           drain=units.drainer(setting, "D", unit))
        assert paused.value.kind == "solver_unavailable" and docker.commands[-1] == _listing("D", unit)
        with pytest.raises(Pause) as stopped:
            units.run_unit(tmp_path / "paused-left", run="fixture-run", identity=IDENTITY, work=pauses_leaving_one,
                           evidence=EVIDENCE, drain=units.drainer(setting, "D", unit))
        assert stopped.value.reason == "CleanupUnconfirmed"  # a remaining container outranks the work's own pause
    finally:
        for worker in left:
            worker.close()


# ------------------------------------------------------------ the completion and consumption commit (Codex #8)
RUN_UNIT = {"unit": "D/s1-searchqa/run", "chain": "D", "k": 1}
RECOVERY = {"by": "owner", "date": "2026-10-22", "decision": "finish the commit"}


class Killed(BaseException):
    """The process dies (no handler runs, no status is written)."""


def _consuming(tmp_path):
    """(work, settle, registry, calls, settled): a unit whose work -- the paid part, counted in ``calls`` -- registers
    and dispatches three items of a run root's bound registry, and whose settlement decides them."""
    registry = Registry(tmp_path / "history", evidence=EVIDENCE).bound(tmp_path / "run-root")
    items, calls, settled = searchqa_items(3), [], []

    def work(attempt):
        calls.append(attempt.name)
        n = units.attempt_number(attempt)
        registry.register("D", "searchqa", items, unit=RUN_UNIT["unit"], purpose="run", attempt=n)
        registry.dispatch("D", "searchqa", items, unit=RUN_UNIT["unit"], attempt=n)
        return {"cells": 3}

    def settle(attempt, result):
        settled.append((attempt.name, result, registry.decide("D", "searchqa", items, unit=RUN_UNIT["unit"],
                                                              attempt=units.attempt_number(attempt))))

    return work, settle, registry, calls, settled


def _remains():
    raise CleanupUnconfirmed("a container of the unit remains")


def _decided(registry):
    lines = registry.path("D", "searchqa").read_text(encoding="utf-8").splitlines()
    return len(lines), {line["state"] for line in registry.entries("D", "searchqa").values()}


def test_codex8_a_failure_right_after_the_settlement_is_finished_by_a_commit_that_repeats_no_work(tmp_path):
    """Codex finding #8 (§3.4: decided after the decision is written; §5: a completed unit is never run again): the
    work's result is the attempt's completion evidence before the settlement runs. A drain failing right after the
    settlement pauses the unit; after the owner's decision the next attempt is a commit -- it settles again
    (idempotent: nothing written), drains and writes unit.json naming the attempt whose work completed -- and the
    paid work never runs again (no redo limit for a commit, which spends nothing)."""
    root, (work, settle, registry, calls, settled) = tmp_path / "unit", _consuming(tmp_path)
    drains = []

    def drain():
        drains.append(len(settled))
        if len(drains) == 1:
            raise CleanupUnconfirmed("a container of the unit remains")

    with pytest.raises(Pause) as stop:
        units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, drain=drain, settle=settle)
    assert stop.value.kind == stop_kind(CleanupUnconfirmed("x")) and not (root / "unit.json").exists()
    evidence = verified(read_json(root / "attempt-1" / units.COMPLETED), "unit-completed")
    assert (evidence["attempt"], evidence["result"], evidence["identity"]) == ("attempt-1", {"cells": 3}, RUN_UNIT)
    assert settled == [("attempt-1", {"cells": 3}, 3)] and drains == [1]  # the drain ran after the settlement
    assert _decided(registry) == (9, {"decided"})
    assert units.completed(root, run="r", identity=RUN_UNIT) == (root / "attempt-1", {"cells": 3})
    with pytest.raises(ValueError, match="another run"):
        units.completed(root, run="r", identity={**RUN_UNIT, "k": 2})
    with pytest.raises(Pause) as waiting:  # no commit without the owner's recorded decision
        units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, drain=drain, settle=settle)
    assert waiting.value.kind == "awaiting_owner_decision"
    write_json(root / "attempt-1" / "recovery.json", RECOVERY)
    done = units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, drain=drain, settle=settle)
    assert (done["attempt"], done["committed_in"], done["result"]) == ("attempt-1", "attempt-2", {"cells": 3})
    assert verified(done, "unit") and calls == ["attempt-1"]  # the commit ran no work
    assert settled[-1] == ("attempt-1", {"cells": 3}, 0) and drains == [1, 2] and _decided(registry) == (9, {"decided"})
    started = verified(read_json(root / "attempt-2" / "started.json"), "unit-started")
    assert started["commit_of"] == "attempt-1" and not (root / "attempt-2" / units.COMPLETED).exists()
    assert units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, settle=settle) == done
    assert calls == ["attempt-1"] and len(settled) == 2  # complete: read back, nothing settled again


def test_codex8_a_failure_between_the_settlement_and_unit_json_is_committed_after_the_owners_decision(
        tmp_path, monkeypatch):
    """Codex finding #8: the process dies after the settlement, before unit.json (no status written: an interrupted
    attempt). The unit waits for the owner's decision, then a commit attempt finishes it without the paid work; a
    commit that pauses again (its drain fails) is committed by the next attempt -- even past the redo limit -- from
    the same completion evidence."""
    root, (work, settle, registry, calls, settled) = tmp_path / "unit", _consuming(tmp_path)
    real = units.write_json

    def dies_at_unit_json(path, value):
        if path.name == "unit.json":
            raise Killed()
        return real(path, value)

    monkeypatch.setattr(units, "write_json", dies_at_unit_json)
    with pytest.raises(Killed):
        units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, settle=settle)
    monkeypatch.setattr(units, "write_json", real)
    assert sorted(p.name for p in (root / "attempt-1").iterdir()) == ["completed.json", "started.json"]
    assert settled == [("attempt-1", {"cells": 3}, 3)] and _decided(registry) == (9, {"decided"})
    with pytest.raises(Pause) as waiting:
        units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, settle=settle)
    assert waiting.value.kind == "awaiting_owner_decision"
    for n in (1, 2, 3):  # commits whose drain fails, each followed by the owner's decision
        write_json(root / ("attempt-%d" % n) / "recovery.json", RECOVERY)
        if n < 3:
            with pytest.raises(Pause):
                units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, settle=settle,
                               drain=_remains)
    done = units.run_unit(root, run="r", identity=RUN_UNIT, work=work, evidence=EVIDENCE, settle=settle)
    assert units.attempt_number(root / done["committed_in"]) == 4 > 1 + protocol.MAX_REDOS
    assert done["attempt"] == "attempt-1" and done["result"] == {"cells": 3} and calls == ["attempt-1"]
    assert [entry[2] for entry in settled] == [3, 0, 0, 0] and _decided(registry) == (9, {"decided"})


def test_codex4_a_cell_bench_endpoint_has_its_benchs_client_and_bound_on_the_steps_scopes(tmp_path):
    """Codex finding #4 (§4.1, §5.5, §9.3): the endpoint of an earlier bench's cells in a later step's self-test --
    ``cell_bench`` -- has that bench's chain-D client (its nominal M) and ledger bound B, and the scopes of the step,
    kind and attempt that run it; chain G's B is 65,536 on every bench."""
    setting, attempt, d = _setting(tmp_path), tmp_path / "selftest" / "attempt-2", protocol.CHAINS["D"]
    own = units.solver_endpoint(setting, "D", "spreadsheetbench", 1, "selftest", attempt)
    scopes = ("overall", "D:solver", "D:redo", "D:xs:spreadsheetbench:1:selftest:attempt-2")
    assert own.scopes == scopes and own.max_tokens == 2 * protocol.ELUCID_MAX_TOKENS["spreadsheetbench"]
    for bench in ("officeqa", "livemath", "alfworld"):
        mixed = units.solver_endpoint(setting, "D", "spreadsheetbench", 1, "selftest", attempt, cell_bench=bench)
        bound = protocol.ledger_bound(d, bench, branch="E", longest=None)
        assert mixed.client.max_tokens == protocol.solver_tokens(d, bench) and mixed.scopes == scopes
        assert mixed.max_tokens == bound == 2 * protocol.ELUCID_MAX_TOKENS[bench] != own.max_tokens
    glm = units.solver_endpoint(setting, "G", "officeqa", 2, "selftest", attempt, cell_bench="spreadsheetbench")
    assert glm.max_tokens == protocol.GLM_SOLVER_TOKENS and glm.scopes[-1] == "G:xs:officeqa:2:selftest:attempt-2"
    with pytest.raises(ValueError, match="A cell bench"):
        units.solver_endpoint(setting, "D", "officeqa", 2, "selftest", attempt, cell_bench="webshop")
