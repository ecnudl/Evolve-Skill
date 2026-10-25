"""v2.2 (owner decision 2026-10-24 12:1x, "你的门槛设的太高了，请你根据具体的进化情况重新设计一下门槛怎么样才合适，我觉得acc变化五个
点以上都可以算是有效果，不用要求那么高"; the proposed scheme approved as is): the run configuration ``main-v2-2`` -- main-v2-1
whose training round records the sign test without requiring it (``protocol.TRAIN_SIGN``) and prunes, before its cells,
every procedure it wrote that fires on no evaluated item and faults on none (``step.prune_idle``,
``protocol.PRUNE_NON_FIRING``), and whose acceptance round is decided by the sealed practical rule
(``protocol.PRACTICAL_RULE``): J1 holds when the whole-batch S' - S is at least 5 points, or on SearchQA at least 2
points with the one-sided paired t p <= 0.05; S' - P_y only labels the effect ("content" from 5 points, else "form");
|A*| needs min(30, max(ceil(5 % of |A|), blocks + 2)) items (ALFWorld also min(20, blocks + 2) rooms); J3-J7 as before.
Offline: synthetic cell tables on T-ACC's FakeSandbox round, synthetic route logs, T-STEP-V2's fixtures (every role a
FakeGLM, chain G's solver a FakeSolver, the cells' procedures FakeSandbox hooks); no model call."""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import acceptance, budgets, engineer, manifest, protocol, routes, smoke, step
from skillopt.execskill.package import Package, edits, load, with_
from skillopt.execskill.protocol import verified
from tests import test_execskill_v2_step as v2_step
from tests.execskill_fakes_env import procedure
from tests.test_execskill_acceptance import (A, EVIDENCE, N, PATTERNS, fast_statistics, make_cells,  # noqa: F401
                                             outcome, seal)
from tests.test_execskill_integration_b3 import PARENT, sandboxes
from tests.test_execskill_replay import fake, workers  # noqa: F401  (FakeDocker workers)
from tests.test_execskill_step import BENCH, CHAIN, HOOKS_STEP, K, NEW, result
from tests.test_execskill_v2 import cell, cells_of

V21, V22 = protocol.MAIN_V2_1, protocol.MAIN_V2_2
RULE = protocol.PRACTICAL_RULE
M = procedure("p-officeqa-2-2", ("applies", "before_call"), header="Column helper notes.")


def configured(name):
    return SimpleNamespace(extra={"configuration": name})


# ------------------------------------------------------------------------------------------- the configuration
def test_main_v2_2_is_main_v2_1_with_the_practical_gates_and_its_own_root_and_namespaces():
    assert V22 == "main-v2-2" and protocol.KIND.fullmatch(V22) and V22 in protocol.CONFIGURATIONS
    assert protocol.LEARNING[V22] == "train" and protocol.STAGE_READ[V22] is True
    for table in (protocol.PILOTS, protocol.TEST_READ_CELLS, protocol.CONFIG_STEP_CAPS, protocol.CONFIG_SCHEDULE_CELLS,
                  protocol.CONFIG_ROLE_CAPS, protocol.CONFIG_GLM_CAP, protocol.CONFIG_CAP_FACTOR,
                  protocol.COST_CHECK_PAUSES, protocol.FIX_ECHO, protocol.META_COUNTERFACTUAL):
        assert table[V22] == table[V21]
    assert all(budgets.chain_caps(chain, V22) == budgets.chain_caps(chain, V21) for chain in protocol.CHAINS)
    assert manifest.prompt_sha(V22) == manifest.prompt_sha(V21)
    assert smoke.max_role_calls(V22) == smoke.max_role_calls(V21)
    assert smoke.engineer_request_floor(V22) == smoke.engineer_request_floor(V21)
    assert protocol.read_arms_of(V22) == protocol.read_arms_of(V21)
    assert protocol.REAL_RUN_EVIDENCE[V22] == "main_v2_2_real_run" and "main_v2_2_real_run" in protocol.EVIDENCE
    assert protocol.RUN_ROOTS[V22] == protocol.MAIN_V2_2_ROOT == "/data/execskill-20261024-main-v2-2"
    assert protocol.MAIN_V2_2_MANIFEST == "/data/execskill-20261024-main-v2-2-manifest.json"
    assert protocol.MAIN_V2_2_ROOT not in (protocol.MAIN_ROOT, protocol.MAIN_V2_ROOT, protocol.MAIN_V2_1_ROOT)
    assert [protocol.namespace_of(configured(V22), c) for c in ("G", "D")] == ["G-v2-2", "D-v2-2"]
    assert [protocol.namespace_of(configured(V21), c) for c in ("G", "D")] == ["G-v2-1", "D-v2-1"]
    assert set(protocol.V22_NAMESPACES.values()) <= set(protocol.NAMESPACES)
    assert set(protocol.TRAIN_SIGN) == set(protocol.PRUNE_NON_FIRING) == set(protocol.ACCEPT_RULES) == set(
        protocol.CONFIGURATIONS)
    assert {name for name, required in protocol.TRAIN_SIGN.items() if not required} == {V22, protocol.MAIN_V2_3}
    assert {name for name, on in protocol.PRUNE_NON_FIRING.items() if on} == {V22, protocol.MAIN_V2_3}
    assert {name: rule for name, rule in protocol.ACCEPT_RULES.items() if rule} == {V22: RULE, protocol.MAIN_V2_3: RULE}
    assert protocol.ACCEPT_FRESHNESS == {V22: "route_b_v2_1_slices_reused",
                                         protocol.MAIN_V2_3: "route_b_v2_2_slices_reused"}
    assert RULE == {"name": "practical-v2-2", "gain_points": 5, "significance_benches": ["searchqa"],
                    "significance_points": 2, "alpha": protocol.ALPHA, "content_points": 5, "astar_share_percent": 5,
                    "astar_cap": protocol.MIN_ASTAR, "rooms_cap": protocol.MIN_ASTAR_ROOMS, "blocks_extra": 2}
    assert protocol.ALPHA == 0.05 and protocol.MIN_ASTAR == 30 and protocol.MIN_ASTAR_ROOMS == 20
    with pytest.raises(ValueError, match="route B"):
        routes.check_pins({}, configuration=V22)  # main's chains: chain D pins its route B


def test_the_astar_floor_of_each_bench_under_the_rule():
    floors = {bench: acceptance.minimum_astar(RULE, protocol.SLICES[bench]["accept"][0],
                                               protocol.SLICES[bench]["blocks"], alfworld=bench == "alfworld")
              for bench in protocol.BENCHES}
    assert floors == {"livemath": {"items": 5, "rooms": None}, "officeqa": {"items": 4, "rooms": None},
                      "spreadsheetbench": {"items": 3, "rooms": None}, "searchqa": {"items": 30, "rooms": None},
                      "alfworld": {"items": 8, "rooms": 6}}
    # ceil(5 % of |A|) items, at least blocks + 2, at most the registered 30 (ALFWorld rooms: blocks + 2, at most 20)
    assert acceptance.minimum_astar(RULE, 61, 1) == {"items": 4, "rooms": None}
    assert acceptance.minimum_astar(RULE, 20, 1) == {"items": 3, "rooms": None}
    assert acceptance.minimum_astar(RULE, 5_000, 30, alfworld=True) == {"items": 30, "rooms": 20}


# ------------------------------------------------------------------------------------------- training
def test_the_training_round_records_the_sign_test_without_requiring_it():
    one = cells_of({"a": ("pp", "ff")})
    required = step.train_verdict(one, ["a"], [], {"p1"}, predicate_faults=0, routed=1)
    assert not required["adopted"] and required["reason"] == "gain:sign" and "sign_required" not in required
    recorded = step.train_verdict(one, ["a"], [], {"p1"}, predicate_faults=0, routed=1, sign=False)
    assert recorded["adopted"] and recorded["reason"] is None and recorded["p_sign"] == 1 / 2
    assert recorded["gain"] == {"fixed_over_broken": True, "net": True} and recorded["sign_required"] is False
    mixed = cells_of({"a": ("pp", "ff"), "b": ("pp", "ff"), "c": ("ff", "pp")})
    assert step.train_verdict(mixed, ["a", "b", "c"], [], set(), predicate_faults=0, routed=3)["reason"] == "gain:sign"
    assert step.train_verdict(mixed, ["a", "b", "c"], [], set(), predicate_faults=0, routed=3, sign=False)["adopted"]
    # the other criteria and every guard are unchanged
    tie = cells_of({"a": ("pp", "ff"), "b": ("ff", "pp")})
    assert step.train_verdict(tie, ["a", "b"], [], set(), predicate_faults=0, routed=2,
                              sign=False)["reason"] == "gain:fixed_over_broken"
    rows = {"i%03d" % n: ("pp", "pp") for n in range(98)} | {"h1": ("pf", "ff"), "h2": ("pf", "ff")}
    assert step.train_verdict(cells_of(rows), sorted(rows), [], set(), predicate_faults=0, routed=100,
                              sign=False)["reason"] == "gain:net"
    faulty = cells_of({"a": ("pp", "ff"), "b": ("pp", "ff"), "c": ("pp", "ff")})
    faulty[("S'", "a")][0]["faults"] = [{"procedure": "p1"}]
    assert step.train_verdict(faulty, ["a", "b", "c"], [], {"p1"}, predicate_faults=0, routed=3,
                              sign=False)["reason"] == "guard:own_faults"
    formats = cells_of({k: ("pp", "ff") for k in "abc"})
    for k in "abc":
        formats[("S'", k)] = [cell("pass", violation=True)] * 2
    assert step.train_verdict(formats, ["a", "b", "c"], [], set(), predicate_faults=0, routed=3,
                              sign=False)["reason"] == "guard:format"
    nothing = step.train_verdict({}, [], [], set(), predicate_faults=0, routed=5, sign=False)
    assert not nothing["adopted"] and nothing["reason"] == "no_item_routes_differently"


def logs(*rows):
    """{key: route-log stand-in} from (enabled ids, faulting ids) per evaluated item."""
    return {"i%d" % n: SimpleNamespace(enabled=tuple(on), faults=[{"procedure": p, "kind": "predicate"} for p in bad])
            for n, (on, bad) in enumerate(rows)}


def test_prune_idle_drops_only_this_rounds_procedures_that_fire_and_fault_nowhere():
    base = Package((A,), "s1", EVIDENCE)
    candidate = with_(base, step="s2", add=[N, M])
    pruned, ids = step.prune_idle(candidate, base, base, logs(((A.id, N.id), ()), ((A.id,), ())))
    assert ids == [M.id] and pruned.order == (A.id, N.id) and pruned.parent_sha256 == base.sha256
    assert (pruned.step, pruned.evidence) == (candidate.step, candidate.evidence)
    assert [(e.kind, e.new.id) for e in edits(base, pruned)] == [("new", N.id)]
    # a procedure that faults on an item is not idle (its faults are the round's evidence)
    kept, none = step.prune_idle(candidate, base, base, logs(((A.id, N.id), (M.id,))))
    assert kept is candidate and none == []
    # the incumbent's procedures (the parent's, or adopted in an earlier round) are never pruned
    incumbent = with_(base, step="s2", add=[N])
    later, ids = step.prune_idle(candidate, incumbent, base, logs(((), ())))
    assert ids == [M.id] and later.order == (A.id, N.id)
    everything, ids = step.prune_idle(candidate, base, base, logs(((A.id,), ())))
    assert ids == [N.id, M.id] and everything.order == (A.id,) and edits(base, everything) == []
    # a revision firing nowhere is pruned and its old version stays retired: the round tests the deletion it routed
    revised = procedure("p-officeqa-2-3", ("applies", "before_call"),
                        lineage={"parent": A.sha256, "revises": A.id, "engineer_call": None})
    rewrite = with_(base, step="s2", revise=[revised])
    dropped, ids = step.prune_idle(rewrite, base, base, logs(((), ())))
    assert ids == [revised.id] and dropped.order == () and A.sha256 in dropped.retired
    assert [(e.kind, e.old.id) for e in edits(base, dropped)] == [("deletion", A.id)]


# ------------------------------------------------------------------------------------------- acceptance
@pytest.fixture(scope="module")
def ruled(tmp_path_factory):
    return seal(tmp_path_factory.mktemp("ruled"), rule=RULE)


@pytest.fixture(scope="module")
def registered(tmp_path_factory):
    return seal(tmp_path_factory.mktemp("registered"))


def gaining(rows):
    """S' as S (one run of two passing on every row) but passing both runs on ``rows``: +1/2 per row."""
    return dict(PATTERNS, **{"S'": lambda k, r: k in rows or (k + r) % 2 == 0})


def test_a_round_prepared_with_the_rule_seals_it_and_its_floor(ruled, registered):
    assert ruled["rule"] == RULE and ruled["plan"]["minimum"] == {"items": 4, "rooms": None}  # 60 items, 2 blocks
    assert "rule" not in registered and "minimum" not in registered["plan"]
    assert ruled["plan"]["astar"] == registered["plan"]["astar"] and len(ruled["plan"]["astar"]) == 45
    assert ruled["freshness"] == registered["freshness"]  # the caller's label (the step passes ACCEPT_FRESHNESS)


def test_the_rule_accepts_from_five_points_over_the_whole_batch_and_only_labels_the_placebo(ruled, registered):
    decision = acceptance.decide(make_cells(ruled), ruled)
    old = acceptance.decide(make_cells(registered), registered)
    for name in ("S'-S", "S'-P_y", "S'-C", "S-C"):  # every recorded contrast is the registered one
        assert all(decision["contrasts"][name][key] == old["contrasts"][name][key]
                   for key in ("mean", "p_t", "whole_batch"))
    gain = decision["contrasts"]["S'-S"]["whole_batch"]
    assert old["decision"] == decision["decision"] == "accept" and decision["rule"] == RULE["name"]
    assert "rule" not in old
    assert decision["guards"]["J1"] == {"rule": RULE["name"], "whole_batch": gain,
                                        "p_t": decision["contrasts"]["S'-S"]["p_t"], "gain_points": 5,
                                        "practical": True, "significant": False, "ok": True}
    j2 = decision["guards"]["J2"]
    assert j2["decides"] is False and j2["label"] == "content" and j2["ok"]
    assert decision["reason"] == ("J1 (practical-v2-2: %+.1f points over the whole batch) and J3-J7 hold; placebo "
                                  "label content" % (100 * gain))
    # a yoked sham doing as well as S' rejects under the registered J2; under the rule it labels the gain "form"
    same = outcome(dict(PATTERNS, P_y=PATTERNS["S'"]))
    before, after = acceptance.decide(make_cells(registered, same), registered), acceptance.decide(
        make_cells(ruled, same), ruled)
    assert before["decision"] == "reject" and "J2" in before["reason"]
    assert after["decision"] == "accept" and after["guards"]["J2"]["label"] == "form"
    assert after["reason"].endswith("placebo label form")


def test_five_points_over_the_whole_batch_is_the_bar_and_the_other_guards_still_hold(ruled):
    six = acceptance.decide(make_cells(ruled, outcome(gaining({0, 1, 2, 4, 5, 6}))), ruled)  # 3 of 60 items
    assert six["contrasts"]["S'-S"]["whole_batch"] == pytest.approx(0.05) and six["decision"] == "accept"
    five = acceptance.decide(make_cells(ruled, outcome(gaining({0, 1, 2, 4, 5}))), ruled)  # 2.5 of 60 items
    assert five["contrasts"]["S'-S"]["whole_batch"] == pytest.approx(2.5 / 60) and five["decision"] == "reject"
    assert "J1" in five["reason"] and not five["guards"]["J1"]["practical"] and not five["guards"]["J1"]["significant"]
    # J4 (format) still rejects a gain made of format violations
    violating = acceptance.decide(make_cells(ruled, violation=lambda job: job["arm"] == "S'"), ruled)
    assert violating["decision"] == "reject" and "J4" in violating["reason"]


def unanswered(cells, gone):
    """``cells`` with every cell of the items ``gone`` unanswered: an unknown token and no delivered reply (§6.3)."""
    for one in cells:
        if one["task_id"] in gone:
            one["judge"]["v2"]["token"], one["sends"] = "unknown", [{"receipt": None}]
    return cells


def test_too_few_answered_units_leave_a_ruled_round_undetermined_instead_of_raising(ruled, registered):
    astar = ruled["plan"]["astar"]
    kept = {"acc-00", "acc-32"}  # one answered item in each block: the t-test keeps no degree of freedom
    assert kept <= set(astar) and {ruled["blocks"][i] for i in kept} == {"b1", "b2"}
    gone = set(astar) - kept
    decision = acceptance.decide(unanswered(make_cells(ruled), gone), ruled)
    assert decision["decision"] == "undetermined" and decision["analysed"] == 2 and decision["rule"] == RULE["name"]
    assert decision["shared_unanswered"] == sorted(gone) and "guards" not in decision
    assert decision["reason"] == ("too few answered units for the t-test (2 items in 2 blocks); the run pauses, the "
                                  "batch is consumed but undecided")
    assert acceptance.reproduce(unanswered(make_cells(ruled), gone), ruled, decision)
    with pytest.raises(acceptance.Pause) as stop:  # settle pauses before it marks anything decided
        acceptance.settle(decision, ruled, None, None)
    assert stop.value.kind == "acceptance_undetermined"
    with pytest.raises(ValueError, match="Too few answered items for the t-test"):  # sealed without a rule: as before
        acceptance.decide(unanswered(make_cells(registered), gone), registered)
    # one more answered item gives the t-test its degree of freedom: the round is decided (J5 counts the unanswered)
    decided = acceptance.decide(unanswered(make_cells(ruled), gone - {"acc-01"}), ruled)
    assert decided["decision"] == "undetermined" and decided["guards"]["J5"]["pause"] and decided["analysed"] == 3


def test_on_alfworld_the_units_of_the_floor_check_are_rooms():
    sealed = {"bench": "alfworld", "blocks": {"g1": "b1", "g2": "b1", "g3": "b2", "g4": "b2"},
              "rooms": {"g1": "r1", "g2": "r1", "g3": "r2", "g4": "r3"}}
    assert acceptance._too_few_units(sealed, ["g1", "g2", "g3"]) == ("too few answered units for the t-test (2 rooms "
                                                                    "in 2 blocks)")
    assert acceptance._too_few_units(sealed, ["g1", "g3", "g4"]) is None  # rooms r1, r2, r3 in blocks b1, b2
    assert acceptance._too_few_units(dict(sealed, bench="officeqa"), ["g1", "g2", "g3"]) is None  # items are units


def test_a_harmful_sham_is_reported_under_the_rule_without_the_parent_only_label(ruled, registered):
    harmful = outcome(dict(PATTERNS, P_y=lambda k, r: False))  # the yoked sham fails everywhere: P_y - S < 0
    old = acceptance.decide(make_cells(registered, harmful), registered)
    new = acceptance.decide(make_cells(ruled, harmful), ruled)
    assert old["contrasts"]["P_y-S"]["ci95"] == new["contrasts"]["P_y-S"]["ci95"] and new["contrasts"]["P_y-S"][
        "ci95"][1] < 0
    assert old["placebo_rule"] == "harmful_sham_parent_only_2.5pct" and new["placebo_rule"] == "harmful_sham_reported"
    assert "alpha" in old["guards"]["J1"] and "alpha" not in new["guards"]["J1"]


def test_the_rule_runs_a_round_from_its_floor(tmp_path):
    four = seal(tmp_path / "four", fires_n=lambda k: k < 4, rule=RULE)
    assert len(four["plan"]["astar"]) == 4 and four["plan"]["decision"] == "run" and four["placebo_y"] is not None
    rows = dict(PATTERNS, **{"S'": lambda k, r: True, "S": lambda k, r: k == 3 and r == 0})  # +3.5 of 60 items
    small = acceptance.decide(make_cells(four, outcome(rows)), four)
    assert small["A_star"] == 4 and small["decision"] == "accept" and small["guards"]["J1"]["practical"]
    three = seal(tmp_path / "three", fires_n=lambda k: k < 3, rule=RULE)
    assert three["plan"]["decision"] == acceptance.SMALL and acceptance.schedule(three) == {}
    skipped = acceptance.decide([], three)
    assert skipped["decision"] == acceptance.SMALL and skipped["rule"] == RULE["name"]
    assert "below the minimum of 4 items (practical-v2-2)" in skipped["reason"]
    registered = seal(tmp_path / "registered", fires_n=lambda k: k < 4)
    assert registered["plan"]["decision"] == acceptance.SMALL
    assert "below the registered minimum" in acceptance.decide([], registered)["reason"]


def first(p, whole):
    return {"p_t": p, "whole_batch": whole}


def test_searchqa_alone_also_accepts_a_significant_gain_of_two_points():
    size, content = 100, [Fraction(1, 2)] * 10  # S' - P_y: +5 points of 100 items, "content"
    three = [Fraction(1)] * 3 + [Fraction(0)] * 27  # S' - S: +3 points
    j1, j2 = acceptance._practical(RULE, "searchqa", three, content, size, first(0.01, 0.03), first(0.2, 0.05))
    assert j1 == {"rule": RULE["name"], "whole_batch": 0.03, "p_t": 0.01, "gain_points": 5, "practical": False,
                  "significant": True, "ok": True}
    assert j2 == {"rule": RULE["name"], "whole_batch": 0.05, "p_t": 0.2, "decides": False, "label": "content",
                  "ok": True}
    assert not acceptance._practical(RULE, "officeqa", three, content, size, first(0.01, 0.03), first(0.2, 0.05))[0][
        "ok"]  # the significance path is SearchQA's alone
    assert not acceptance._practical(RULE, "searchqa", three, content, size, first(0.051, 0.03), first(0.2, 0.05))[0][
        "ok"]
    edge = acceptance._practical(RULE, "searchqa", [Fraction(1)] * 2, content, size, first(0.05, 0.02),
                                 first(0.2, 0.05))[0]
    assert edge["ok"] and edge["significant"]  # both bounds are inclusive, in exact arithmetic
    below = [Fraction(1)] * 2 + [Fraction(-1, 100)]
    assert not acceptance._practical(RULE, "searchqa", below, content, size, first(0.001, 0.0199), first(0.2, 0.05))[
        0]["ok"]
    j1, j2 = acceptance._practical(RULE, "alfworld", [Fraction(1, 2)] * 10, [Fraction(49, 10)], size,
                                   first(0.4, 0.05), first(0.5, 0.049))
    assert j1["ok"] and j1["practical"] and not j1["significant"] and j2["label"] == "form"


# ------------------------------------------------------------------------------------------- one step
@pytest.fixture()
def v22(monkeypatch):
    """T-STEP-V2's fixtures in the configuration ``main-v2-2``."""
    monkeypatch.setattr(v2_step, "CONFIGURATION", V22)


def step_root(setting):
    return setting.root / CHAIN / ("s%d-%s" % (K, BENCH))


def test_step_v2_2_trains_without_the_sign_test_and_accepts_under_the_practical_rule(tmp_path, monkeypatch, workers,
                                                                                    v22):
    setting, services, solver_fake, glm, waited = v2_step.build_v2(tmp_path, monkeypatch, workers)
    found = step.run_step(setting, CHAIN, BENCH, K, PARENT, services=services)
    root = step_root(setting)
    record = verified(read_json(root / step.STEP_FILE), "step")
    assert found.record == record and record["learning"] == "train" and record["decision"] == "accept"
    trained = result(root, "train-r1")["result"]
    assert trained["adopted"] and trained["pruned"] == [] and trained["proposed_sha256"] == trained["candidate_sha256"]
    assert trained["verdict"]["sign_required"] is False and set(trained["verdict"]["gain"]) == {"fixed_over_broken",
                                                                                                 "net"}
    sealed = verified(read_json(root / "accept" / "sealed.json"), "acceptance-sealed")
    assert sealed["chain"] == "G-v2-2" and sealed["rule"] == RULE and sealed["freshness"] == "route_b_v2_1_slices_reused"
    assert sealed["plan"]["minimum"] == acceptance.minimum_astar(RULE, len(sealed["A"]),
                                                                 len(set(sealed["blocks"].values())))
    decision = result(root, "accept")["result"]
    assert decision["decision"] == "accept"
    first_round = record["training"]["rounds"][0]  # Codex review MINOR 2: the package the cells ran, and its proposal
    assert first_round["candidate_sha256"] == first_round["proposed_sha256"] == trained["candidate_sha256"]
    assert first_round["pruned"] == []
    lines = services.registry.entries("G-v2-2", BENCH)
    assert lines and not services.registry.entries(CHAIN, BENCH)


def test_step_v2_2_prunes_a_procedure_that_fires_on_no_evaluated_item(tmp_path, monkeypatch, workers, v22):
    setting, services, solver_fake, glm, waited = v2_step.build_v2(tmp_path, monkeypatch, workers)
    idle = dict(HOOKS_STEP, **{NEW: dict(HOOKS_STEP[NEW], applies=lambda view: False)})  # the routing pass only
    found = step.run_step(setting, CHAIN, BENCH, K, PARENT,
                          services=dataclasses.replace(services, item_workers=sandboxes(idle)))
    root = step_root(setting)
    record = verified(read_json(root / step.STEP_FILE), "step")
    engineered = result(root, "engineer-r1")["result"]["engineer"]
    trained = result(root, "train-r1")["result"]
    assert trained["pruned"] == [NEW] and trained["proposed_sha256"] == engineered["candidate_sha256"]
    assert trained["candidate_sha256"] != trained["proposed_sha256"] and trained["differs"] == 0
    assert trained["cells"] == 0 and not trained["adopted"]
    assert trained["verdict"]["reason"] == "no_item_routes_differently"
    pruned = load(next(setting.root.rglob("packages/%s.json" % trained["candidate_sha256"])))
    assert pruned.order == PARENT.order and pruned.parent_sha256 == PARENT.sha256
    first_round = record["training"]["rounds"][0]  # Codex review MINOR 2: the pruned package the cells would run
    assert first_round["candidate_sha256"] == trained["candidate_sha256"] and first_round["pruned"] == [NEW]
    assert first_round["proposed_sha256"] == engineered["candidate_sha256"]
    proposals = [p for s, p in glm.seen if s == engineer.ENGINEER_SYSTEM_V2 and p["request"] == "propose"]
    line = proposals[1]["history"][0]
    assert not line["adopted"] and [p["fate"] for p in line["proposals"]] == ["pruned_no_firing"]
    assert record["training"]["adopted"] == 0 and "accept" not in record["units"] and found.package == PARENT
