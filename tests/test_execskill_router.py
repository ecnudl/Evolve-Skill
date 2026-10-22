"""T-ROUTE-1..5 (implementation plan §8; registration §2.3, §6.1 edit-type table, §6.5, §9.2): the router, with the
in-process FakeSandbox of tests/execskill_fakes_env.py (T-ROUTE-4, the ALFWorld routing view hash, is asserted by the
shell and tested in tests/test_execskill_solver.py). Offline and deterministic."""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from skillopt.execskill import router, solver
from skillopt.execskill.package import Package, with_
from skillopt.execskill.protocol import MAX_TWINS_PER_ITEM, MIN_ASTAR
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.fixtures.execskill.items import officeqa_items, searchqa_items, spreadsheetbench_items

ITEMS = 40
VIEWS = {"q-%02d" % k: {"question": "Which value is listed in row %d?" % k, "context": "row=%d" % k}
         for k in range(ITEMS)}
A = procedure("p-officeqa-1-1", ("applies", "before_call"))
D = procedure("p-officeqa-1-2", ("applies", "before_call"))
N = procedure("p-searchqa-1-1", ("applies", "before_call"))  # inherited on OfficeQA (another origin)
L = procedure("p-livemath-1-1", ("applies", "before_call"))  # inherited on OfficeQA (another origin)
A2 = procedure("p-officeqa-2-1", ("applies", "before_call"),
               lineage={"parent": A.sha256, "revises": A.id, "engineer_call": None})
X = procedure("p-officeqa-2-2", ("applies", "before_call"))
PARENT = Package((A, D, N, L), "s1", "smoke")


def row(view):
    return int(view["context"].split("=")[1])


FIRES = {A.id: lambda k: k % 2 == 0, D.id: lambda k: k % 3 == 0, N.id: lambda k: True, L.id: lambda k: k % 4 != 0,
         A2.id: lambda k: k % 2 == 1, X.id: lambda k: k % 5 == 0}


def hooks(fires=FIRES):
    return {pid: {"applies": (lambda rule: lambda view: rule(row(view)))(rule)} for pid, rule in fires.items()}


def workers(seen=None, table=None):
    @contextmanager
    def worker(package, item):
        sandbox = FakeSandbox(table or hooks()).start(package, kind="cell")
        try:
            yield sandbox
        finally:
            sandbox.close()
            if seen is not None:
                seen.extend(sandbox.calls)
    return worker


def fired(items, pid):
    return [i for i in items if FIRES[pid](row(VIEWS[i]))]


# ---------------------------------------------------------------------------------------- T-ROUTE-1 deterministic
def test_t_route_1_route_and_plan_are_deterministic():
    candidate = with_(PARENT, step="s2", add=[X], revise=[A2], remove=[D.id])
    first = router.plan(candidate, PARENT, "officeqa", VIEWS, workers(), unit="G-s2", donors=["d1", "d2", "d3"])
    again = router.plan(candidate, PARENT, "officeqa", VIEWS, workers(), unit="G-s2", donors=["d1", "d2", "d3"])
    assert first == again and first["version"] == "fivebench-execskill-v1-firing-plan"
    other = router.plan(candidate, PARENT, "officeqa", VIEWS, workers(), unit="G-s3", donors=["d1", "d2", "d3"])
    assert other["twins"] != first["twins"]  # the draws are seeded by the unit
    view = VIEWS["q-04"]
    logs = [router.route(PARENT, "officeqa", view, FakeSandbox(hooks()).start(PARENT, kind="cell")) for _ in range(2)]
    assert logs[0] == logs[1] and logs[0].sha256 == logs[1].sha256
    assert logs[0].enabled == (A.id, N.id) and logs[0].to_json()["order"] == list(PARENT.order)


# ------------------------------------------------------------------------- T-ROUTE-2 predicate fault: disabled
def test_t_route_2_a_predicate_fault_leaves_the_procedure_disabled():
    table = {A.id: {"applies": lambda view: 1 / 0}, D.id: {"applies": lambda view: "yes"},
             N.id: {"applies": lambda view: True}}
    sandbox = FakeSandbox(table, faults={(L.id, "applies"): "timeout"}).start(PARENT, kind="cell")
    log = router.route(PARENT, "officeqa", VIEWS["q-00"], sandbox)
    assert log.enabled == (N.id,) and log.fired == (N.id,)
    assert [(f["procedure"], f["kind"]) for f in log.faults] == [(A.id, "exception"), (D.id, "not_bool"),
                                                                 (L.id, "timeout")]
    assert log.per_procedure[A.id] == {"applies": None, "enabled": False, "withheld": False, "restored": False,
                                       "shadow_fired": False, "fault": "exception"}
    # a withheld procedure still runs its predicate (shadow_fired); a restored one is marked
    log = router.route(PARENT, "officeqa", VIEWS["q-00"], FakeSandbox(hooks()).start(PARENT, kind="cell"),
                       withhold={A.id}, restore={D.id})
    assert log.per_procedure[A.id]["shadow_fired"] is True and A.id not in log.enabled
    assert log.per_procedure[D.id]["restored"] is True and D.id in log.enabled
    with pytest.raises(ValueError):  # a package with procedures for the bench routes in the sandbox
        router.route(PARENT, "officeqa", VIEWS["q-00"], None)
    # a procedure excluded from the bench is not routed there
    narrowed = with_(PARENT, step="s2", narrow={N.id: ["officeqa"]})
    sandbox = FakeSandbox(hooks()).start(narrowed, kind="cell")
    assert N.id not in router.route(narrowed, "officeqa", VIEWS["q-00"], sandbox).per_procedure
    assert N.id not in {pid for pid, _ in sandbox.called("applies")}


# --------------------------------------------------------------------- T-ROUTE-3 A* from public views only
def test_t_route_3_routing_views_are_made_from_public_data_only(tmp_path):
    items = officeqa_items(4) + searchqa_items(4)
    seen = []
    for item in items:  # a caller that leaks private fields into the public mapping still routes on public keys
        public = {**item["public"], **item["private"], "task_id": "PRIVATE-SENTINEL", "label": "PRIVATE-SENTINEL"}
        view = solver.routing_view(item["benchmark"], public)
        assert view == {key: item["public"][key] for key in ("question", "context")}
        sandbox = FakeSandbox(hooks()).start(PARENT, kind="cell")
        router.route(PARENT, item["benchmark"], view, sandbox)
        seen.extend(sandbox.calls)
    assert seen and "PRIVATE-SENTINEL" not in json.dumps(seen)
    sheet = spreadsheetbench_items(tmp_path, 1)[0]
    view = solver.routing_view("spreadsheetbench", {**sheet["public"], "test_files": sheet["private"]["test_files"]})
    assert set(view) == {"instruction", "workbook_preview", "input_path", "required_output_path",
                         "required_answer_position"}
    assert sheet["private"]["test_files"][0] not in json.dumps(view)
    with pytest.raises(ValueError):  # an ALFWorld item routes only on its registered view
        solver.routing_view("alfworld", {"game_file": str(tmp_path / "game.tw-pddl")})


# -------------------------------------------------------- T-ROUTE-5 edit-type A*, twin caps and priority, yoke
def test_t_route_5_astar_by_edit_type_and_the_twin_draws():
    candidate = with_(PARENT, step="s2", add=[X], revise=[A2], remove=[D.id])
    items = list(VIEWS)
    plan = router.plan(candidate, PARENT, "officeqa", VIEWS, workers(), unit="G-s2",
                       donors=["d%d" % k for k in range(10)])
    by_edit = plan["astar_by_edit"]
    assert by_edit[X.id] == {"kind": "new", "items": fired(items, X.id)}
    assert by_edit[A2.id] == {"kind": "revision",
                              "items": [i for i in items if i in fired(items, A.id) or i in fired(items, A2.id)]}
    assert by_edit[D.id] == {"kind": "deletion", "items": fired(items, D.id)}
    assert plan["astar"] == items and plan["decision"] == "run"
    # priority: changed procedures fired on >= 10 A* items, then inherited ones (>= 15) by enable count
    assert plan["twin_priority"] == [A2.id, D.id, N.id, L.id]  # X fires on 8 items only
    assert plan["twin_kinds"] == {A2.id: "withhold", D.id: "restore", N.id: "withhold", L.id: "withhold"}
    twins, skipped = plan["twins"], plan["not_withheld"]
    assert all(len(held) <= MAX_TWINS_PER_ITEM for held in twins.values())
    for pid in plan["twin_priority"]:
        drawn = router.seeded_half(fired(items, pid) if pid != D.id else by_edit[D.id]["items"], "G-s2", pid)
        got = [i for i, held in twins.items() if any(t["procedure"] == pid for t in held)]
        assert sorted(got + [i for i, ids in skipped.items() if pid in ids]) == sorted(drawn)
    for item, held in twins.items():  # changed procedures take the slots before inherited ones
        order = [plan["twin_priority"].index(t["procedure"]) for t in held]
        assert order == sorted(order)
    restore_items = [i for i, held in twins.items() if any(t["kind"] == "restore" for t in held)]
    assert set(restore_items) <= set(router.seeded_half(by_edit[D.id]["items"], "G-s2", D.id))
    # one run-slice donor per A* item, reuse counted
    assert set(plan["donors"]["pairs"]) == set(items) and sum(plan["donors"]["reuse"].values()) == ITEMS
    # a narrowing: A* = where the narrowed-out procedure fired in S; a restoration twin
    narrowing = router.plan(with_(PARENT, step="s2", narrow={N.id: ["officeqa"]}), PARENT, "officeqa", VIEWS,
                            workers(), unit="G-s2", donors=["d1"])
    assert narrowing["astar_by_edit"][N.id] == {"kind": "narrowing", "items": items}
    assert narrowing["twin_kinds"][N.id] == "restore"
    # a single new procedure: its twin estimand is S' - S itself (no changed-procedure twin); small A* not run
    single = router.plan(with_(PARENT, step="s2", add=[X]), PARENT, "officeqa", VIEWS, workers(), unit="G-s2")
    assert X.id not in single["twin_priority"] and len(single["astar"]) < MIN_ASTAR
    assert single["decision"] == "not_run_small_astar" and single["donors"] == {"pairs": {}, "reuse": {}}
    # predicate faults of changed procedures are listed per item
    table = hooks()
    table[X.id] = {"applies": lambda view: 1 / 0 if row(view) == 7 else row(view) % 5 == 0}
    faulty = router.plan(candidate, PARENT, "officeqa", VIEWS, workers(table=table), unit="G-s2", donors=["d1"])
    assert faulty["fault_items"] == ["q-07"]
    # ALFWorld needs rooms; fewer than 20 rooms is not run
    alf = {"g-%02d" % k: {"initial_observation": "room %d" % k, "admissible_commands_at_reset": ["look"],
                          "task_text": "row=%d" % k} for k in range(ITEMS)}
    walker = procedure("p-alfworld-2-1", ("applies", "alf_before_step"))
    start = Package((), "s1", "smoke")
    rooms = {g: "room-%d" % (k % 10) for k, g in enumerate(alf)}
    alf_plan = router.plan(with_(start, step="s2", add=[walker]), start, "alfworld", alf,
                           workers(table={walker.id: {"applies": lambda view: True}}), unit="G-s2", rooms=rooms)
    assert alf_plan["astar_rooms"] == 10 and alf_plan["decision"] == "not_run_small_astar"
    with pytest.raises(ValueError):
        router.plan(with_(start, step="s2", add=[walker]), start, "alfworld", alf, workers(), unit="G-s2")


def test_yoke_pairs_each_item_with_one_donor():
    pairs = router.yoke(["a", "b", "c"], ["d1", "d2"], "G-s2")
    assert set(pairs["pairs"]) == {"a", "b", "c"} and sorted(pairs["reuse"].values()) == [1, 2]
    assert router.yoke([], [], "G-s2") == {"pairs": {}, "reuse": {}}
    with pytest.raises(ValueError):
        router.yoke(["a"], [], "G-s2")


# ------------------------------------------------------------------- M round (Codex review 2026-10-22, #12)
def test_codex_12_inherited_twin_eligibility_and_draw_count_the_acceptance_slice_a():
    """§6.5 "继承来的过程...在本 bench 验收段启用 >= 15 道时": an inherited procedure firing on 50 items of A but on
    only 10 of A* is eligible, its seeded half is drawn from its 50 firing items of A, and the drawn items outside A*
    are listed in ``twin_only`` (they run S' beside the twin, ``acceptance.schedule``)."""
    views = {"q-%02d" % k: {"question": "Which value is listed in row %d?" % k, "context": "row=%d" % k}
             for k in range(80)}
    items = list(views)
    table = hooks({A.id: lambda k: False, D.id: lambda k: False, X.id: lambda k: k < 40, N.id: lambda k: k >= 30,
                   L.id: lambda k: k == 0})
    candidate = with_(PARENT, step="s2", add=[X])
    plan = router.plan(candidate, PARENT, "officeqa", views, workers(table=table), unit="G-s2", donors=["d1", "d2"])
    astar = set(plan["astar"])
    firing = [i for i in items if row(views[i]) >= 30]
    assert len(astar) == 40 and plan["decision"] == "run"
    assert len(firing) == 50 >= 15 > len([i for i in firing if i in astar]) == 10
    assert plan["twin_priority"] == [N.id] and plan["twin_kinds"] == {N.id: "withhold"}  # X: S' - S is its tau
    drawn = router.seeded_half(firing, "G-s2", N.id)
    assert len(drawn) == 25 and sorted(plan["twins"]) == sorted(drawn) and plan["not_withheld"] == {}
    assert all(held == [{"procedure": N.id, "kind": "withhold"}] for held in plan["twins"].values())
    outside = [i for i in items if i in drawn and i not in astar]
    assert plan["twin_only"] == outside and len(outside) > 0 and len(outside) < len(drawn)
    assert list(plan["twins"]) == [i for i in items if i in drawn]  # slice order
