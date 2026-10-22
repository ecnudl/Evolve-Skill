"""Route-B rounds (implementation plan §1 rounds row; registration §6.2, §6.3, §6.4 J5, §4.4 P3): the seeded
interleaved order and the blocks of a round run through real cells, the v2 token table, the infrastructure guard
(``unknown_fault`` excluded) and the shared-unanswered mask. The start-time balance is ``acceptance._balance`` alone
(registrar decision 2026-10-22, ticket C5-5; tests/test_execskill_acceptance.py). Offline and deterministic."""
from __future__ import annotations

import json
from fractions import Fraction

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.coevo5.calls import Endpoint
from skillopt.coevo5.protocol import RUNTIME
from skillopt.coevo5.stats import unknown_share
from skillopt.execskill import budgets, rounds, slots, units
from skillopt.execskill.cells import Arm, Pause
from skillopt.execskill.package import empty
from skillopt.execskill.protocol import BENCHES, round_tag
from tests.fixtures.execskill.items import searchqa_items

EVIDENCE = "engineering_fixture"
UNIT = "G/s1-searchqa/run"
EMPTY = empty(step="s0", evidence=EVIDENCE)
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class _Client:
    def __init__(self):
        self.requests = []

    def call(self, system, user):
        self.requests.append((system, user))
        question = json.loads(user)["question"]
        number = question.split("number ")[1].rstrip("?")
        return {"ok": True, "response": "<answer>Fixtown %s</answer>" % number, "finish_reason": "stop",
                "error_type": None, "usage": dict(USAGE), "attempts": [{"status": 200}]}


def _setting(tmp_path):
    budget = Budget(tmp_path / "ledger", sleep=lambda _: None)
    budget.declare(budgets.caps())
    pools = slots.pools(tmp_path / "slots", poll=0.01, log=lambda line: None)
    return units.Setting(run="fixture-run", root=tmp_path, shared=tmp_path / "shared",
                         pools={"searchqa": searchqa_items(4)}, cards={b: "Read the clue." for b in BENCHES},
                         runtime=RUNTIME, clients=None, budget=budget, slots=pools, sandbox={}, evidence=EVIDENCE,
                         workers=1, cooldown=0)


def _counting(monkeypatch):
    """Cells get a counter clock (dispatch and finish times are ticks in dispatch order)."""
    ticks = iter(range(10_000))
    real = units.cell_context

    def context(*args, **kwargs):
        found = real(*args, **kwargs)
        found.clock = lambda: float(next(ticks))
        return found

    monkeypatch.setattr(rounds, "cell_context", context)


def _round(tmp_path, name, *, blocks=None, arms=None):
    setting = _setting(tmp_path)
    endpoint = Endpoint(_Client(), model="glm-5.3", max_tokens=100, slots=setting.slots["glm-5.3"],
                        sleep=lambda _: None)
    tasks = rounds.pool_tasks(setting, ["searchqa"])
    items = sorted(tasks)
    arms = arms or {"S": Arm("parent", EMPTY), "C": lambda cell: Arm("card", EMPTY)}
    schedule = {arm: [(item, 2 if arm == "S" else 1) for item in items] for arm in arms}
    attempt = tmp_path / name / "attempt-1"
    return rounds.run_round(setting, attempt, endpoint, UNIT, arms, schedule, tasks, tag="run", blocks=blocks), items


def _dispatch_order(cells):
    found = [r for rs in cells.values() for r in rs]
    return [(r["arm"], r["task_id"], r["run"]) for r in sorted(found, key=lambda r: r["dispatch_ts"])]


# ---------------------------------------------------------------------------------------------- run_round
def test_a_round_runs_every_cell_in_one_seeded_interleaved_order(tmp_path, monkeypatch):
    _counting(monkeypatch)
    cells, items = _round(tmp_path, "a")
    assert sorted(cells) == sorted((arm, item) for arm in ("S", "C") for item in items)
    assert all(len(cells[("S", i)]) == 2 and len(cells[("C", i)]) == 1 for i in items)
    assert all(r["judge"]["v2"]["token"] == "pass" for rs in cells.values() for r in rs)
    order = _dispatch_order(cells)
    jobs = [(arm, item, run) for arm, runs in (("S", 2), ("C", 1)) for item in items for run in range(runs)]
    assert order == [jobs[i] for i in rounds._order(list(range(len(jobs))), round_tag(UNIT) + ":run")]
    assert [a for a, _, _ in order] != sorted(a for a, _, _ in order)  # interleaved, never by arm
    again, _ = _round(tmp_path, "b")
    assert _dispatch_order(again) == order  # the same seed, the same order
    assert rounds.tokens(cells)[("C", items[0])] == ["pass"]
    assert rounds.table_of(cells)[("S", items[0])] == (Fraction(1), Fraction(1), 0, 2, 0)
    ran = [r for rs in cells.values() for r in rs]  # one cell per clock tick pair: dispatch, finish
    assert max(r["finish_ts"] for r in ran) - min(r["dispatch_ts"] for r in ran) == 2 * len(jobs) - 1
    assert not hasattr(rounds, "balance")  # ticket C5-5: no second J5 guard


def test_blocks_are_dispatched_one_after_the_other(tmp_path, monkeypatch):
    _counting(monkeypatch)
    setting_items = sorted(rounds.pool_tasks(_setting(tmp_path / "s"), ["searchqa"]))
    blocks = {item: ("b1" if n < 2 else "b2") for n, item in enumerate(setting_items)}
    cells, _ = _round(tmp_path, "a", blocks=blocks)
    found = [r for rs in cells.values() for r in rs]
    assert all(r["block"] == r["cell"]["block"] == blocks[r["task_id"]] for r in found)
    last_b1 = max(r["dispatch_ts"] for r in found if r["block"] == "b1")
    assert last_b1 < min(r["dispatch_ts"] for r in found if r["block"] == "b2")


def test_an_arm_function_must_give_an_arm(tmp_path):
    with pytest.raises(ValueError):
        _round(tmp_path, "a", arms={"S": lambda cell: "not an arm"})


def test_item_keys_name_a_bench():
    assert rounds.key("officeqa", "fx-officeqa-01") == "officeqa/fx-officeqa-01"
    assert rounds.bench_of("officeqa/fx-officeqa-01") == "officeqa"
    for bad in ("fwd:rule:officeqa:1", "bfcl/x", "officeqa/"):
        with pytest.raises(ValueError):
            rounds.bench_of(bad)


# ----------------------------------------------------------------------------------------------- guard and mask
def _cell(arm, item, token, *, kind="scored", answered=True):
    outcome = "unknown" if token.startswith("unknown") else token
    receipt = {"ok": True} if answered else {"ok": False, "error_type": "transport"}
    return {"cell": {"arm": arm, "task_id": item}, "final": {"outcome": outcome, "kind": kind},
            "judge": {"v2": {"token": token}}, "sends": [{"receipt": receipt}], "dispatch_ts": 0.0,
            "finish_ts": 1.0, "shared_with": None}


def test_the_guard_counts_infrastructure_unknowns_never_p3_faults():
    faults = {("S", "i%d" % n): [_cell("S", "i%d" % n, "unknown_fault", kind="fault")] for n in range(10)}
    rounds.guard(faults, ["S"], UNIT)  # every cell P3: no pause (§4.4)
    one = {**{("S", "i%d" % n): [_cell("S", "i%d" % n, "pass")] for n in range(9)},
           ("S", "i9"): [_cell("S", "i9", "unknown", kind="infrastructure")]}
    rounds.guard(one, ["S"], UNIT)  # 1 of 10 = 10 %: still allowed
    two = {**one, ("S", "i8"): [_cell("S", "i8", "unknown", kind="unclassified")]}
    with pytest.raises(Pause) as stop:
        rounds.guard(two, ["S"], UNIT)
    assert stop.value.kind == "infrastructure_incomplete" and "2 of 10" in stop.value.reason
    rounds.guard(two, ["C"], UNIT)  # only the named arms are guarded
    table = rounds.table_of(faults)
    assert table[("S", "i0")] == (Fraction(0), Fraction(1), 1, 1, 0)  # wrong on L, right on H, not infrastructure
    assert unknown_share(table, "S", ["i%d" % n for n in range(10)], infrastructure_only=True) == 0
    assert rounds.table_of(two)[("S", "i9")] == (Fraction(0), Fraction(1), 1, 1, 1)


def test_shared_unanswered_needs_every_cell_unknown_and_unanswered():
    cells = {("S", "a"): [_cell("S", "a", "unknown", answered=False)],
             ("C", "a"): [_cell("C", "a", "unknown", answered=False)],
             ("S", "b"): [_cell("S", "b", "unknown", answered=False)],
             ("C", "b"): [_cell("C", "b", "unknown", answered=True)],
             ("S", "c"): [_cell("S", "c", "unknown_fault", answered=False)]}
    assert rounds.shared_unanswered(cells, ["a", "b", "c", "d"]) == ["a"]

