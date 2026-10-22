"""Route-B ledger scopes and the solver endpoint on the frozen ledger (implementation plan §8: T-LEDGER-1..3;
registration §4.1, §9.3). Receipts come from the real elucid client behind a scripted gateway
(tests/execskill_fakes.py); offline and deterministic."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from skillopt.coevo5 import ledger
from skillopt.coevo5.budget import Budget, rooted
from skillopt.coevo5.calls import BREACH, Slots
from skillopt.execskill import budgets, protocol
from skillopt.execskill.errors import AssumptionBroken, ConfigurationError
from tests.execskill_fakes import FakeSolver, Reply, over_nominal, usage

DEEPSEEK = protocol.CHAINS["D"]
M = 1_000_000
SYSTEM, USER = "Answer with <answer>...</answer>.", json.dumps({"question": "What is 2 + 2?"})


def _setting(tmp_path, pilot="default"):
    budget = Budget(tmp_path / "ledger", sleep=lambda _: None)
    budget.declare(budgets.caps(pilot))
    slots = {model: Slots(tmp_path / "slots", model, 2) for model in protocol.SOLVERS}
    return SimpleNamespace(budget=budget, slots=slots, cooldown=0)


def _solver(tmp_path, reply, bench="officeqa"):
    return FakeSolver(tmp_path, [(None, reply)], max_tokens=protocol.solver_tokens(DEEPSEEK, bench),
                      read_timeout=protocol.read_timeout(DEEPSEEK, bench))


def _events(budget_root):
    return [json.loads(line) for line in (budget_root / "events.jsonl").read_text().splitlines()]


# ------------------------------------------------------------------------------------------------ scopes
def _every_scope_set(pilot):
    out = []
    for chain in protocol.CHAINS:
        out.append(budgets.solver_scopes(chain, None, None, "test"))
        for k, bench in enumerate(protocol.PILOTS[pilot]["order"], 1):
            for kind in budgets.STEP_KINDS:
                out += [budgets.solver_scopes(chain, bench, k, kind, attempt)
                        for attempt in range(1, protocol.MAX_REDOS + 2)]
            out += [budgets.glm_scopes(chain, role, bench, k) for role in budgets.ROLES]
    return out


@pytest.mark.parametrize("pilot", sorted(protocol.PILOTS))
def test_every_scope_set_is_rooted_declared_and_names_one_total(pilot):
    declared = budgets.caps(pilot)
    for scopes in _every_scope_set(pilot):
        assert rooted(scopes) and scopes[0] == budgets.ROOT and set(scopes) <= set(declared), scopes
        assert len(budgets.TOTALS.intersection(scopes)) == 1, scopes
        assert all(scope.split(":")[0] in protocol.CHAINS for scope in scopes[1:]), scopes
        chain = scopes[1].split(":")[0]
        assert all(scope.startswith(chain + ":") for scope in scopes[1:]), scopes  # one chain per call
    smoke = (budgets.solver_scopes("smoke", None, None, "smoke"), budgets.glm_scopes("smoke", "examiner", None, None))
    for scopes in smoke:
        assert rooted(scopes) and set(scopes) <= set(budgets.smoke_caps())
    assert set(budgets.solver_scopes("smoke", None, None, "probe")) == set(budgets.probe_caps())


def test_scope_names_and_caps():
    assert budgets.solver_scopes("D", "officeqa", 2, "accept") == ("overall", "D:solver", "D:xs:officeqa:2:accept")
    assert budgets.solver_scopes("G", "officeqa", 2, "accept", 2) == (
        "overall", "G:solver", "G:redo", "G:xs:officeqa:2:accept:attempt-2")
    assert budgets.glm_scopes("D", "examiner_research", "officeqa", 2) == (
        "overall", "D:glm", "D:xs:officeqa:2:role:examiner:research")
    assert budgets.glm_scopes("G", "describer", "spreadsheetbench", 1)[-1] == "G:xs:spreadsheetbench:1:role:engineer"
    caps = budgets.caps()
    assert caps["overall"] == 2 * (180 * M + 30 * M) and caps["D:solver"] == 180 * M and caps["G:glm"] == 30 * M
    assert caps["G:test"] == 99 * M and caps["D:redo"] == 14_800_000
    assert caps["D:xs:officeqa:2:accept"] == 29_500_000 and caps["D:xs:officeqa:2:accept:attempt-3"] == 14_800_000
    assert caps["G:xs:spreadsheetbench:1:accept:attempt-2"] == 8_300_000
    assert caps["G:xs:spreadsheetbench:1:role:examiner:research"] == 4_600_000
    assert budgets.caps("recommended")["D:xs:alfworld:2:accept"] == 91_300_000
    assert budgets.smoke_caps() == {"overall": 16 * M, "smoke:solver": 14 * M, "smoke:glm": 2 * M}
    assert budgets.probe_caps() == {"overall": 500_000, "smoke:probe": 500_000}
    for bad in (("D", "officeqa", 2, "accept", 4), ("D", "officeqa", 0, "run"), ("E", "officeqa", 1, "run"),
                ("D", "bfcl", 1, "run"), ("D", "officeqa", 2, "test"), ("D", None, None, "smoke"),
                ("smoke", "officeqa", 1, "run"), ("D", "officeqa", 2, "learning")):
        with pytest.raises(ValueError):
            budgets.solver_scopes(*bad)
    with pytest.raises(ValueError):
        budgets.glm_scopes("D", "researcher", "officeqa", 2)


def test_caps_declare_cleanly_and_again_after_a_restart(tmp_path):
    budget = Budget(tmp_path / "ledger")
    for _ in range(2):
        budget.declare(budgets.caps())
    snapshot = budget.snapshot()
    assert {scope: entry["cap"] for scope, entry in snapshot.items()} == budgets.caps()


# --------------------------------------------------------------------------------------------- T-LEDGER-1..3
def test_t_ledger_1_endpoint_reserves_with_the_ledger_bound(tmp_path):
    setting = _setting(tmp_path)
    solver = _solver(tmp_path, Reply(text="<answer>4</answer>", usage=usage(7, prompt=40)))
    bound = protocol.ledger_bound(DEEPSEEK, "officeqa", branch="E")
    scopes = budgets.solver_scopes("D", "officeqa", 2, "run")
    endpoint = budgets.endpoint(setting, scopes, client=solver.client, max_tokens_bound=bound, sleep=lambda _: None)
    recorder = endpoint.recorder(label="D/officeqa/2/run")
    receipt = recorder(SYSTEM, USER)
    assert receipt["ok"] and solver.requests[0]["max_tokens"] == 8192  # the request names M ...
    size = ledger.request_bytes(SYSTEM, USER)
    sent = recorder.sends[0]
    assert sent["max_tokens"] == bound == 16_384  # ... the ledger reserves with B
    assert sent["reserved"] == 4 * (size + 512 + bound) and sent["charged"] == 47
    reserve = [e for e in _events(tmp_path / "ledger") if e["event"] == "reserve"]
    assert [(e["amount"], tuple(e["scopes"])) for e in reserve] == [(sent["reserved"], tuple(sorted(scopes)))]
    snapshot = setting.budget.snapshot()
    assert all(snapshot[scope]["settled"] == 47 and snapshot[scope]["open"] == 0 for scope in scopes)
    assert snapshot["D:glm"]["settled"] == 0 and "halted" not in snapshot


def test_t_ledger_2_completion_between_m_and_b_does_not_halt(tmp_path):
    setting = _setting(tmp_path)
    solver = _solver(tmp_path, over_nominal("<answer>4</answer>", 9_000))
    bound = protocol.ledger_bound(DEEPSEEK, "officeqa", branch="E")
    endpoint = budgets.endpoint(setting, budgets.solver_scopes("D", "officeqa", 2, "accept"), client=solver.client,
                                max_tokens_bound=bound, sleep=lambda _: None)
    recorder = endpoint.recorder(label="D/officeqa/2/accept")
    receipt = recorder(SYSTEM, USER)
    assert receipt["over_nominal"] and recorder.broken is None and endpoint.halted is None
    assert "halted" not in setting.budget.snapshot()
    assert setting.budget.snapshot()["D:xs:officeqa:2:accept"]["settled"] == 9_010
    budgets.endpoint(setting, budgets.solver_scopes("D", "officeqa", 2, "accept"), client=solver.client,
                     max_tokens_bound=bound)  # the ledger still admits new attempts


def test_t_ledger_3_completion_above_b_breaks_the_assumption_and_halts(tmp_path):
    setting = _setting(tmp_path)
    bound = protocol.ledger_bound(DEEPSEEK, "officeqa", branch="E")
    solver = _solver(tmp_path, over_nominal("<answer>4</answer>", bound + 1))
    scopes = budgets.solver_scopes("D", "officeqa", 2, "accept")
    endpoint = budgets.endpoint(setting, scopes, client=solver.client, max_tokens_bound=bound, sleep=lambda _: None)
    recorder = endpoint.recorder(label="D/officeqa/2/accept")
    with pytest.raises(AssumptionBroken):
        recorder(SYSTEM, USER)
    assert recorder.broken == BREACH and len(solver.requests) == 1  # no resend
    snapshot = setting.budget.snapshot()
    assert snapshot["halted"]["reason"] == BREACH and snapshot["D:solver"]["settled"] == 10 + bound + 1
    with pytest.raises(AssumptionBroken):  # every process: no new attempt begins
        budgets.endpoint(setting, budgets.solver_scopes("G", "officeqa", 2, "run"), client=solver.client,
                         max_tokens_bound=bound)


# ------------------------------------------------------------------------------------------ endpoint refusals
def test_endpoint_refuses_before_the_ledger_can_quarantine(tmp_path):
    setting = _setting(tmp_path)
    solver = _solver(tmp_path, "<answer>4</answer>")
    bound = protocol.ledger_bound(DEEPSEEK, "officeqa", branch="E")
    refused = [
        (budgets.solver_scopes("D", "livemath", 3, "run"), bound),  # not a step of the default pilot: undeclared
        (("overall", "D:solver", "D:glm", "D:xs:officeqa:2:run"), bound),  # two totals
        (("D:solver", "overall", "D:xs:officeqa:2:run"), bound),  # the root first
        (("overall", "D:xs:officeqa:2:run"), bound),  # no total
        (budgets.solver_scopes("D", "officeqa", 2, "run"), 8_191),  # B below M
        (budgets.solver_scopes("D", "officeqa", 2, "run"), 16_384.0),
    ]
    for scopes, max_tokens_bound in refused:
        with pytest.raises(ConfigurationError):
            budgets.endpoint(setting, scopes, client=solver.client, max_tokens_bound=max_tokens_bound)
    setting.slots.pop(DEEPSEEK)
    with pytest.raises(ConfigurationError):
        budgets.endpoint(setting, budgets.solver_scopes("D", "officeqa", 2, "run"), client=solver.client,
                         max_tokens_bound=bound)
    assert "halted" not in setting.budget.snapshot() and not [
        e for e in _events(tmp_path / "ledger") if e["event"] != "declare"]


# ------------------------------------------------------------------------------------------- ticket C7e-1
def test_c7e_1_the_maximum_schedule_counts_g_acc_in_the_examiner_scope_as_s_e6_prices_it():
    """Ticket C7e-1 (registrar decision 2026-10-22): the registration puts G_acc's solver cost in the examiner scope
    (§3.3, §9.2; calc T4/T6), and ``protocol.MAX_SCHEDULE_CELLS`` -- the cells T6's caps and S-E6
    (``smoke._scope_cells``) price -- counts it there: OfficeQA's examiner row is the band probe (S with procedures,
    30 items x 3 probes), the shortcut probe (C, 30 items x 2 runs) and G_acc (one item per A* item at most, C plus
    S', S, P_y and S_dup), its accept row the A* cells alone (C plus S', S, P_y, P_i, S_dup and two twins, x 4 runs).
    So the scopes the step charges (G_acc on ``...:examiner``, ``units.solver_endpoint(..., g_acc=True)``) are the
    scopes S-E6 prices, and the redo sub-scope and the redo reserve price one acceptance block without G_acc."""
    cells, g_acc = protocol.MAX_SCHEDULE_CELLS["officeqa"], protocol.G_ACC["officeqa"]
    band = (0, protocol.BAND_PROBE_ITEMS * protocol.BAND_ROUNDS)
    shortcut = (protocol.SHORTCUT_PROBE_ITEMS * protocol.SHORTCUT_RUNS, 0)
    procedure_arms = [arm for arm in protocol.G_ACC_ARMS if arm != "C"] + ["S_dup"]  # C runs the card
    generated = (g_acc, g_acc * len(procedure_arms))
    assert cells["examiner"]["officeqa"] == tuple(map(sum, zip(band, shortcut, generated))) == (110, 290)
    runs, astar = protocol.SLICES["officeqa"]["accept"][1], 50
    assert cells["accept"]["officeqa"] == (astar * runs, astar * runs * (5 + protocol.MAX_TWINS_PER_ITEM)) == (
        200, 1_400)
    # the redo reserve is the dearest single acceptance block of the pilot (calc T6), G_acc not in it
    caps = budgets.chain_caps("G")
    block = protocol.STEP_CAPS["officeqa"]["accept"] / protocol.SLICES["officeqa"]["blocks"]
    assert caps["G:redo"] == protocol.PILOTS["default"]["redo_reserve"] >= block
    assert caps["G:xs:officeqa:2:accept:attempt-2"] == min(protocol.STEP_CAPS["officeqa"]["accept"], caps["G:redo"])


def test_m1_mains_chain_caps_are_its_registered_caps_and_the_pilots_are_unchanged():
    """Registrar 17:0x: each chain of a ``main`` root declares main's step caps, role scopes (engineer 5M, examiner 5M,
    research 9.2M per step), GLM cap and totals; the pilots' caps stay the R7b ones."""
    assert budgets.role_scope_caps() == budgets.ROLE_SCOPE_CAPS == budgets.role_scope_caps("recommended")
    assert budgets.role_scope_caps("main") == {"engineer": 5_000_000, "examiner": 5_000_000,
                                               "examiner:research": 9_200_000}
    for chain in protocol.CHAINS:
        caps, plan = budgets.chain_caps(chain, "main"), protocol.PILOTS["main"]
        assert caps[chain + ":solver"] == plan["solver_cap"] and caps[chain + ":glm"] == protocol.MAIN_GLM_CAP
        assert caps[budgets.ROOT] == plan["solver_cap"] + protocol.MAIN_GLM_CAP == 1_808_000_000
        for k, bench in enumerate(protocol.BENCHES, 1):
            for kind in budgets.STEP_KINDS:
                cap = protocol.MAIN_STEP_CAPS[bench][kind]
                assert caps[budgets.solver_scopes(chain, bench, k, kind)[-1]] == cap
                assert caps[budgets.solver_scopes(chain, bench, k, kind, 2)[-1]] == min(cap, plan["redo_reserve"])
            assert caps["%s:xs:%s:%d:role:examiner:research" % (chain, bench, k)] == 9_200_000
    assert budgets.caps("main")[budgets.ROOT] == 2 * 1_808_000_000
    assert budgets.chain_caps("G") == budgets.chain_caps("G", "default") != budgets.chain_caps("G", "main")
