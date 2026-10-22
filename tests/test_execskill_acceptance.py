"""T-ACC-1..8 (implementation plan §8; registration §6.1-§6.5, §3.3, §3.4; Codex F1, F2, F5, F6, F22): one acceptance
round sealed with the in-process FakeSandbox of tests/execskill_fakes_env.py and decided on synthetic cell tables.
Offline and deterministic; no model call anywhere (the round's cells are written by hand)."""
from __future__ import annotations

import functools
import json
import traceback
from contextlib import contextmanager

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import acceptance, donors, stats_ext
from skillopt.execskill.errors import ConfigurationError
from skillopt.execskill.package import Package, empty, with_
from skillopt.execskill.protocol import MIN_ASTAR, fault_items_max, format_margin, record, round_tag, verified
from skillopt.execskill.registry import Registry
from tests.execskill_fakes_env import FakeSandbox, procedure

EVIDENCE = "smoke"
BENCH = "officeqa"
UNIT = "pilot/s2-officeqa/accept"
STEP = "pilot/s2-officeqa/t1"
A = procedure("p-officeqa-1-1", ("applies", "before_call"), header="Parent helper notes.")
D = procedure("p-officeqa-1-2", ("applies", "before_call"))
N = procedure("p-officeqa-2-1", ("applies", "before_call"), header="Row helper notes.")
ITEMS = ["acc-%02d" % k for k in range(60)]
VIEWS = {item: {"question": "What is listed in acc-row-%d?" % k, "context": "acc-row-%d | %d" % (k, 100 + k)}
         for k, item in enumerate(ITEMS)}
BLOCKS = {item: "b1" if k < 30 else "b2" for k, item in enumerate(ITEMS)}
RECORDS = {item: {"task_id": item, **VIEWS[item]} for item in ITEMS}


def row(view):
    return int(view["context"].split(" | ")[0].rsplit("-", 1)[1])


def note(view, state):
    return {"facts": ["Listed in the row: " + view["context"], "Question topic: " + view["question"][:40]]}


def hooks(fires_n=lambda k: k % 4 != 3):
    """N fires on 45 of the 60 items by default; D (deleted in the ``delete`` packages) on the even rows."""
    return {A.id: {"applies": lambda view: True, "before_call": lambda view, state: {"facts": ["parent note"]}},
            D.id: {"applies": lambda view: row(view) % 2 == 0, "before_call": note},
            N.id: {"applies": lambda view: fires_n(row(view)), "before_call": note}}


def workers(table):
    @contextmanager
    def worker(package, item):
        sandbox = FakeSandbox(table).start(package, kind="cell")
        try:
            yield sandbox
        finally:
            sandbox.close()
    return worker


def trajectory(k, run):
    view = {"question": "What is listed in run-row-%d?" % k, "context": "run-row-%d | %d" % (k, 900 + k)}
    return {"cell": "pilot/s2-officeqa/run/S/run-%02d/%d" % (k, run), "task_id": "run-%02d" % k, "bench": BENCH,
            "arm_kind": "parent", "calls": [{"purpose": "first", "user": json.dumps(view)}],
            "shell": {"precheck": None}}


TRAJECTORIES = [trajectory(k, r) for k in range(6) for r in range(2)]


def packages(kind="new"):
    """(parent, candidate): ``new`` adds N to a parent holding A; ``empty`` adds N to the empty package; ``delete``
    adds N and deletes D."""
    if kind == "empty":
        parent = empty(step="s1", evidence=EVIDENCE)
        return parent, with_(parent, step="s2", add=[N])
    parent = Package((A, D) if kind == "delete" else (A,), "s1", EVIDENCE)
    return parent, with_(parent, step="s2", add=[N], remove=[D.id] if kind == "delete" else ())


def seal(root, kind="new", *, table=None, fires_n=lambda k: k % 4 != 3, unit=UNIT, blocks=None, **options):
    parent, candidate = packages(kind)
    return acceptance.prepare(root, chain="D", bench=BENCH, step=STEP, unit=unit, candidate=candidate,
                              parent=parent, views=VIEWS, blocks=blocks or BLOCKS,
                              workers=workers(table or hooks(fires_n)),
                              trajectories=TRAJECTORIES, freshness="route_b_fresh_method_side_reused", mde=0.10,
                              **options)


def k_of(item):
    return int(item.rsplit("-", 1)[-1])


# per arm: (row, run) -> True (pass), False (fail) or a token; twins follow S'
PATTERNS = {"S'": lambda k, r: (k + r) % 5 != 0, "S": lambda k, r: (k + r) % 2 == 0,
            "P_y": lambda k, r: (k + r) % 2 == 1, "C": lambda k, r: (k + r) % 2 == 0,
            "S_dup": lambda k, r: (k + r) % 2 == 0, "P_i": lambda k, r: (k + r) % 2 == 0}


def outcome(patterns):
    def token(job):
        found = patterns.get(job["arm"], patterns["S'"])(k_of(job["item"]), job["run"])
        return found if isinstance(found, str) else "pass" if found else "fail"
    return token


def make_cells(sealed, token=None, *, faults=lambda job: (), violation=lambda job: False, calls=lambda job: (),
               flags=lambda job: ()):
    """One synthetic cell record per scheduled job, sent one per second in the schedule's order, each block the
    registered gap after the previous one (§3.3)."""
    token = token or outcome(PATTERNS)
    schedule = acceptance.schedule(sealed)
    jobs = [job for block in schedule.values() for job in block]
    cells = []
    for t, job in enumerate(jobs):
        t = float(t) + acceptance.BLOCK_GAP_SECONDS.get(BENCH, 0) * list(schedule).index(job["block"])
        cells.append({"arm": job["arm"], "task_id": job["item"], "run": job["run"], "set": job["set"],
                      "judge": {"v2": {"token": token(job)}, "format": {"violation": violation(job)},
                                "flags": list(flags(job))},
                      "faults": list(faults(job)),
                      "logical_calls": [{"purpose": "first"}] + [{"purpose": p} for p in calls(job)],
                      "worst_delivery": "delivered", "sends": [{"receipt": {"ok": True}}],
                      "dispatch_ts": t, "finish_ts": t + 1.0})
    return cells


@pytest.fixture(autouse=True)
def fast_statistics(monkeypatch):
    """Fewer sign flips and resamples than registered (sensitivity and interval figures; T-STATS covers the registered
    counts); every decision rule is unchanged."""
    monkeypatch.setattr(stats_ext, "signflip", functools.partial(stats_ext.signflip, n=2_000))
    monkeypatch.setattr(stats_ext, "bootstrap_ci", functools.partial(stats_ext.bootstrap_ci, resamples=400))


@pytest.fixture(scope="module")
def sealed(tmp_path_factory):
    return seal(tmp_path_factory.mktemp("round"))


def plain(value):
    return json.loads(json.dumps(value))


# ------------------------------------------------------------------------------------ T-ACC-1 sealed inputs
def test_t_acc_1_sealed_inputs_are_hashed_written_once_and_immutable(tmp_path, sealed):
    assert sealed["version"] == "fivebench-execskill-v1-acceptance-sealed" and sealed["evidence"] == EVIDENCE
    parent, candidate = packages()
    seals = sealed["seals"]
    assert seals["candidate"] == candidate.sha256 and seals["parent"] == parent.sha256
    assert seals["donor_corpus"] == donors.seal(sealed["corpus"])
    assert seals["plan_sha256"] == sealed["plan"]["record_sha256"]
    again = seal(tmp_path)  # the same inputs seal to the same record, written once
    assert again == sealed and json.loads((tmp_path / "sealed.json").read_text()) == plain(sealed)
    assert seal(tmp_path) == sealed  # a redo with the same inputs reuses the file
    with pytest.raises(ValueError):  # other content under the same path is refused
        seal(tmp_path, unit=UNIT + "-other")
    tampered = plain(sealed)
    item = sealed["plan"]["astar"][0]
    tampered["placebo_y"][item]["procedures"][N.id]["before_call"] = {"facts": ["other"]}
    with pytest.raises(ValueError):
        acceptance.decide([], tampered)
    moved = plain(TRAJECTORIES)
    moved[0]["calls"][0]["user"] = json.dumps({"question": "changed", "context": "x"})
    with pytest.raises(ConfigurationError, match="sealed_input_changed"):
        donors.verify(sealed["corpus"], moved)
    donors.verify(sealed["corpus"], TRAJECTORIES)
    keys = {"candidate": candidate, "parent": parent, "card": empty(step=STEP, evidence=EVIDENCE),
            "placebo": candidate}
    acceptance.check_packages(sealed, keys)
    with pytest.raises(ValueError):
        acceptance.check_packages(sealed, {**keys, "candidate": parent})


# --------------------------------------------------------------------------------- T-ACC-2 J1, J2, J5, J6, J7
def test_t_acc_2_one_seeded_order_per_block_over_every_cell(sealed):
    """Statistics review 8 (registrar decision 2026-10-22): within a block every cell is in ONE seeded order, the
    form of cal-1 (coevo5/step.py:79-80), neither blocked by (item, run) nor grouped by arm."""
    schedule = acceptance.schedule(sealed)
    assert list(schedule) == ["b1", "b2"] and schedule == acceptance.schedule(plain(sealed))
    jobs = [job for block in schedule.values() for job in block]
    assert len(jobs) == len(sealed["plan"]["astar"]) * 5 * 4  # S', S, C, P_y, P_i x A* x 4 runs; no twin here
    for block, ordered in schedule.items():
        keys = [acceptance._seeded(round_tag(UNIT) + ":" + block, j["set"], j["item"], j["run"], j["arm"])
                for j in ordered]
        assert keys == sorted(keys) and {BLOCKS[j["item"]] for j in ordered} == {block}
    units = [(job["item"], job["run"]) for job in jobs]
    assert sum(units[k] == units[k - 1] for k in range(1, len(units))) < len(units) // 10  # not blocked by unit
    arms = [job["arm"] for job in jobs]
    assert sum(arms[k] == arms[k - 1] for k in range(1, len(arms))) < len(arms) // 3  # nor grouped by arm


def test_t_acc_2_probe_g_acc_and_twin_cells_are_interleaved_in_the_blocks_order(tmp_path):
    probe = ["probe-%02d" % k for k in range(30)]
    sealed = seal(tmp_path, "delete", probe=probe,
                  generate=lambda views: [{"id": "gen-" + i, "source_item": i} for i in sorted(views)[::4][:10]])
    schedule = acceptance.schedule(sealed)
    kinds = {"probe": lambda job: job["set"] == "probe", "G_acc": lambda job: job["set"] == "G_acc",
             "twin": lambda job: ":" in job["arm"]}
    for name, member in kinds.items():
        runs = {block: [k for k, job in enumerate(ordered) if member(job)] for block, ordered in schedule.items()}
        assert sum(map(len, runs.values())) >= 10, name
        assert all(found != list(range(found[0], found[0] + len(found))) for found in runs.values()
                   if len(found) > 1), name  # never a run of their own
    dealt = {block: {j["item"] for j in ordered if j["set"] == "probe"} for block, ordered in schedule.items()}
    assert [len(dealt[b]) for b in ("b1", "b2")] == [15, 15] and dealt["b1"] | dealt["b2"] == set(probe)
    assert acceptance.decide(make_cells(sealed), sealed)["guards"]["J5"]["balance"]["ok"]


def test_t_acc_2_the_balance_guard_reads_start_delays_against_the_seeded_order(sealed):
    cells = make_cells(sealed)  # one per second in the seeded order
    balance = acceptance.decide(cells, sealed)["guards"]["J5"]["balance"]
    assert balance["ok"] and balance["statistic"] == "median_delay_spread" and balance["spread_s"] == 0.0
    assert balance["raw_spread_s"] == balance["order_spread_s"]
    # a pool stall just after one arm's median cell: the arms' median start times move apart (the registered raw
    # spread leaves the 5 % band) while every cell still starts in its seeded place, so the guard holds
    places = {}
    for k, cell in enumerate(cells):
        if cell["set"] == "real":
            places.setdefault(cell["arm"], []).append(k)
    cut = min(found[len(found) // 2] for found in places.values()) + 1
    stalled = plain(cells)
    for cell in stalled[cut:]:
        cell["dispatch_ts"] += 4000.0
        cell["finish_ts"] += 4000.0
    balance = acceptance.decide(stalled, sealed)["guards"]["J5"]["balance"]
    assert balance["ok"] and balance["spread_s"] == 0.0
    assert balance["raw_spread_s"] > 0.05 * balance["duration_s"]
    # an arm held back behind its seeded places is a delay: the round is undetermined
    held = plain(cells)
    for cell in held:
        if cell["arm"] == "C":
            cell["dispatch_ts"] += 900.0
    decision = acceptance.decide(held, sealed)
    assert not decision["guards"]["J5"]["balance"]["ok"] and decision["decision"] == "undetermined"


def test_t_acc_2_accept_needs_j1_and_j2_by_the_paired_t_test(sealed):
    cells = make_cells(sealed)
    decision = acceptance.decide(cells, sealed)
    assert decision["version"] == "fivebench-execskill-v1-decision" and decision["decision"] == "accept"
    assert decision["A"] == 60 and decision["A_star"] == 45 and decision["analysed"] == 45
    items = sealed["plan"]["astar"]
    d = acceptance.differences(acceptance.table(cells), "S'", "S", items)
    test = stats_ext.paired_t(d, strata=[BLOCKS[i] for i in items])
    first = decision["contrasts"]["S'-S"]
    assert first["p_t"] == test["p"] and first["df"] == 45 - 2 and first["mean"] == test["mean"]
    assert first["whole_batch"] == pytest.approx(float(sum(d)) / 60) and decision["guards"]["J1"]["ok"]
    assert set(first["sensitivity"]) == {"p_signflip", "p_wilcoxon"}  # recorded, never deciding
    assert decision["placebo_rule"] == "informative" and decision["guards"]["J2"]["ok"]
    assert decision["guards"]["J6_dup"] is None and decision["guards"]["J7_meta"] is None
    # J2 fails when the paired placebo does as well as S'
    same = acceptance.decide(make_cells(sealed, outcome(dict(PATTERNS, P_y=PATTERNS["S'"]))), sealed)
    assert same["decision"] == "reject" and "J2" in same["reason"] and same["guards"]["J1"]["ok"]
    # J1's whole-batch floor: two items gaining one run in four is below 2 points of the whole batch
    small_gain = dict(PATTERNS, **{"S'": lambda k, r: (k + r) % 2 == 0 or (k % 30 == 0 and r == 1)})
    floor = acceptance.decide(make_cells(sealed, outcome(small_gain)), sealed)
    assert floor["guards"]["J1"]["whole_batch"] < 0.02 and not floor["guards"]["J1"]["ok"]
    assert floor["decision"] == "reject"


def test_t_acc_2_instrument_guards_leave_the_round_undetermined(tmp_path, sealed):
    unknown = acceptance.decide(make_cells(sealed, outcome(dict(PATTERNS, C=lambda k, r: "unknown"))), sealed)
    assert unknown["decision"] == "undetermined" and unknown["guards"]["J5"]["pause"]
    assert unknown["guards"]["J5"]["infra"]["C"] == 1.0
    flagged = acceptance.decide(make_cells(sealed, flags=lambda job: ("reasoning_mismatch",) if job["run"] == 0
                                           and k_of(job["item"]) % 5 == 0 else ()), sealed)
    assert flagged["decision"] == "undetermined" and flagged["guards"]["J5"]["reasoning"] > 0.01
    late = make_cells(sealed)
    for cell in late:  # S' sent long before the other arms
        if cell["arm"] == "S'":
            cell["dispatch_ts"] -= 1000.0
    balance = acceptance.decide(late, sealed)["guards"]["J5"]["balance"]
    assert balance["ok"] is False and balance["spread_s"] > 0.05 * balance["duration_s"]
    untimed = make_cells(sealed)
    untimed[0]["finish_ts"] = None
    assert acceptance.decide(untimed, sealed)["decision"] == "undetermined"
    # J6: S and C are the same text while S has no procedure on the bench
    first = seal(tmp_path, "empty")
    assert first["card_is_parent"]
    ok = acceptance.decide(make_cells(first), first)
    assert ok["guards"]["J6_dup"] == {"pairs": [{"pair": "C-S", "p_two_sided": 1.0, "ok": True}], "ok": True}
    assert ok["decision"] == "accept"
    broken = acceptance.decide(make_cells(first, outcome(dict(PATTERNS, C=lambda k, r: True))), first)
    assert broken["decision"] == "undetermined" and not broken["guards"]["J6_dup"]["ok"]
    assert "the run pauses" in broken["reason"]


def test_t_acc_2_j7_options_only_probe_rejects_a_shortcut(tmp_path):
    probe = ["probe-%02d" % k for k in range(30)]
    sealed = seal(tmp_path, probe=probe)
    jobs = [j for block in acceptance.schedule(sealed).values() for j in block if j["set"] == "probe"]
    assert sorted({j["arm"] for j in jobs}) == ["C", "S'"] and len(jobs) == 60
    shortcut = acceptance.decide(make_cells(sealed), sealed)  # S' 80 % against C 50 % on the options alone
    assert shortcut["guards"]["J7_meta"]["gain"] >= 0.1 and shortcut["decision"] == "reject"
    assert shortcut["reason"] == "failed: J7"
    token = outcome(PATTERNS)
    fair = acceptance.decide(make_cells(sealed, lambda job: "pass" if job["set"] == "probe" else token(job)), sealed)
    assert fair["guards"]["J7_meta"]["ok"] and fair["decision"] == "accept"


# ----------------------------------------------------------------------------- T-ACC-3 J3 at calc T10 boundaries
def faulty(*items, arm="S'", procedure=N.id):
    return lambda job: ([{"procedure": procedure, "hook": "before_call", "kind": "exception"}]
                        if job["item"] in items and job["arm"] == arm and job["run"] == 0 else [])


def test_t_acc_3_fault_items_over_the_whole_slice(sealed):
    astar = sealed["plan"]["astar"]
    assert [fault_items_max(n) for n in (60, 50, 150, 100, 1000)] == [1, 1, 3, 2, 20]
    one = acceptance.decide(make_cells(sealed, faults=faulty(astar[0])), sealed)
    assert one["guards"]["J3"]["fault_items"] == 1 and one["guards"]["J3"]["ok"] and one["decision"] == "accept"
    two = acceptance.decide(make_cells(sealed, faults=faulty(astar[0], astar[1], arm="P_y")), sealed)
    assert two["guards"]["J3"]["fault_items"] == 2 and not two["guards"]["J3"]["ok"] and two["decision"] == "reject"
    # faults of an unchanged procedure, or in the parent's arm, are not the candidate's
    other = acceptance.decide(make_cells(sealed, faults=faulty(*astar[:5], procedure=A.id)), sealed)
    parent_arm = acceptance.decide(make_cells(sealed, faults=faulty(*astar[:5], arm="S")), sealed)
    assert other["guards"]["J3"]["fault_items"] == 0 and parent_arm["guards"]["J3"]["fault_items"] == 0
    # a re-execution unknown_fault in S' counts
    token = outcome(PATTERNS)
    replay = acceptance.decide(make_cells(sealed, lambda job: "unknown_fault" if job["arm"] == "S'" and job[
        "item"] in astar[:2] and job["run"] == 1 else token(job)), sealed)
    assert replay["guards"]["J3"]["items"] == sorted(astar[:2]) and not replay["guards"]["J3"]["ok"]


def test_t_acc_3_routing_faults_on_items_outside_astar_count(tmp_path):
    table = hooks()
    table[N.id]["applies"] = lambda view: 1 / 0 if row(view) in (3, 7) else row(view) % 4 != 3
    sealed = seal(tmp_path, table=table)
    assert sealed["plan"]["fault_items"] == ["acc-03", "acc-07"] and "acc-03" not in sealed["plan"]["astar"]
    decision = acceptance.decide(make_cells(sealed), sealed)
    assert decision["guards"]["J3"]["items"] == ["acc-03", "acc-07"] and decision["decision"] == "reject"


# ----------------------------------------------------------------------------------- T-ACC-4 J4 item counts
def test_t_acc_4_format_guard_compares_item_counts_with_the_registered_margin(sealed):
    astar = sealed["plan"]["astar"]
    assert [format_margin(n) for n in (30, 45, 100, 150, 1000)] == [2, 2, 2, 3, 20]

    def bad(n, arm="S'"):
        return lambda job: job["arm"] == arm and job["item"] in astar[:n] and job["run"] == 1

    two = acceptance.decide(make_cells(sealed, violation=bad(2)), sealed)
    assert two["guards"]["J4_items"] == {"S'": 2, "S": 0, "margin": 2, "ok": True}
    three = acceptance.decide(make_cells(sealed, violation=bad(3)), sealed)
    assert not three["guards"]["J4_items"]["ok"] and three["decision"] == "reject"
    both = acceptance.decide(make_cells(sealed, violation=lambda job: bad(3)(job) or bad(1, "S")(job)), sealed)
    assert both["guards"]["J4_items"]["ok"]  # 3 <= 1 + 2: items, not cells or points


# ----------------------------------------------------------------- T-ACC-5 harmful sham, call-rate reports
def test_t_acc_5_harmful_sham_decides_on_s_prime_minus_s_at_2_5_percent(sealed):
    harmful = acceptance.decide(make_cells(sealed, outcome(dict(PATTERNS, P_y=lambda k, r: False))), sealed)
    assert harmful["contrasts"]["P_y-S"]["ci95"][1] < 0
    assert harmful["placebo_rule"] == "harmful_sham_parent_only_2.5pct"
    assert harmful["guards"]["J1"]["alpha"] == 0.025 and harmful["guards"]["J2"]["informative"] is False
    assert harmful["decision"] == "accept" and harmful["reason"] == acceptance.HARMFUL_WORDING
    assert "content/effort explanation not excluded" in harmful["reason"]
    assert set(harmful["contrasts"]["P_y-S"]["by_donor"]) <= set(sealed["corpus"]["donors"])
    helpful = acceptance.decide(make_cells(sealed, outcome(dict(PATTERNS, P_y=lambda k, r: True))), sealed)
    assert helpful["placebo_rule"] == "helpful_sham_reported" and helpful["decision"] == "reject"
    seconds = acceptance.decide(make_cells(sealed, calls=lambda job: ("second",) if job["arm"] == "S'" and job[
        "run"] < 2 else ()), sealed)
    rates = seconds["second_call_rates"]
    assert rates["S'"] == 0.5 and rates["P_y"] == 0.0 and rates["flag_gt_10pt"] is True
    assert seconds["repair_call_rates"]["flag_gt_10pt"] is False and seconds["decision"] == "accept"


# ------------------------------------------------------------------- T-ACC-6 edit types and restoration twins
def test_t_acc_6_deletion_estimands_placebo_package_and_restoration_twins(tmp_path):
    sealed = seal(tmp_path, "delete")
    plan = sealed["plan"]
    assert {e["kind"] for e in plan["edits"]} == {"new", "deletion"} and len(plan["astar"]) == 45
    assert plan["twin_kinds"] == {N.id: "withhold", D.id: "restore"}
    assert sealed["shams"] == [N.id, D.id] and "restore:" + D.id in sealed["packages"]
    parent, candidate = packages("delete")
    assert sealed["packages"]["placebo"] != candidate.sha256  # P_y holds the deleted procedure again, shammed
    jobs = [j for block in acceptance.schedule(sealed).values() for j in block]
    restored = [j for j in jobs if j["arm"] == "restore:" + D.id]
    assert restored and all(D.id in [t["procedure"] for t in plan["twins"][j["item"]]] for j in restored)
    assert acceptance.cell_arm(sealed, restored[0], cell="cell-1") == (
        "restore:" + D.id, "restore:" + D.id, {"restore": frozenset({D.id})})
    assert acceptance.cell_arm(sealed, {**restored[0], "arm": "withhold:" + N.id}, cell="cell-1") == (
        "candidate", "withhold:" + N.id, {"withhold": frozenset({N.id})})
    assert [acceptance.cell_arm(sealed, {**restored[0], "arm": arm}, cell="c")[:2] for arm in ("S'", "S", "C")] == [
        ("candidate", "candidate"), ("parent", "parent"), ("card", "card")]
    key, kind, kwargs = acceptance.cell_arm(sealed, {**restored[0], "arm": "P_y"}, cell="cell-2")
    assert (key, kind) == ("placebo", "placebo_y") and set(kwargs["placebo"]["procedures"]) == {N.id, D.id}
    assert kwargs["placebo"]["seed"] == "execskill-v1:discourage:%s:cell-2" % UNIT
    assert max(len(t) for t in plan["twins"].values()) <= 2
    decision = acceptance.decide(make_cells(sealed), sealed)
    assert {e["id"]: e["kind"] for e in decision["edits"]} == {e["id"]: e["kind"] for e in plan["edits"]}
    assert set(decision["twins"]) == set(plan["twin_priority"]) and decision["twins_cap"]["max_per_item"] <= 2
    assert all(entry["n"] > 0 and entry["tau"] is not None for entry in decision["twins"].values())


# --------------------------------------------------------------- T-ACC-7 small A*: nothing runs or is consumed
def test_t_acc_7_small_astar_is_not_run_and_releases_every_item(tmp_path):
    assert MIN_ASTAR == 30 and acceptance.SMALL == "not_run_small_astar"
    assert seal(tmp_path / "thirty", fires_n=lambda k: k < 30)["plan"]["decision"] == "run"
    sealed = seal(tmp_path / "small", fires_n=lambda k: k < 29)
    assert len(sealed["plan"]["astar"]) == 29 and sealed["placebo_y"] is None and acceptance.schedule(sealed) == {}
    registry = Registry(tmp_path / "history", evidence=EVIDENCE)
    registry.register("D", BENCH, list(RECORDS.values()), unit=UNIT, purpose="accept", run_root=str(tmp_path))
    ran = []
    assert acceptance.dispatch(sealed, registry, lambda block, jobs: ran.append(block) or [], items=RECORDS) == []
    assert not ran and registry.consumed("D", BENCH) == frozenset()
    assert {e["state"] for e in registry.entries("D", BENCH).values()} == {"routed_not_dispatched"}
    decision = acceptance.decide([], sealed)
    assert decision["decision"] == "not_run_small_astar" and "routed_not_dispatched" in decision["reason"]
    assert decision["evidence_kind"] == "selection"
    path = acceptance.write(tmp_path / "unit", decision)
    assert path.name == "decision.json" and json.loads(path.read_text()) == plain(decision)


def test_t_acc_7_dispatch_releases_items_outside_astar_and_runs_blocks(tmp_path, sealed):
    registry = Registry(tmp_path / "history", evidence=EVIDENCE)
    registry.register("D", BENCH, list(RECORDS.values()), unit=UNIT, purpose="accept", run_root=str(tmp_path))
    blocks = []
    waits = []
    cells = acceptance.dispatch(sealed, registry, lambda block, jobs: blocks.append(block) or [{"n": len(jobs)}],
                                items=RECORDS, sleep=waits.append)
    assert len(waits) == 1 and 7_190 < waits[0] <= 7_200  # OfficeQA's second block waits out the gap (§3.3)
    assert blocks == ["b1", "b2"] and len(cells) == 2
    states = {i: e["state"] for i, e in registry.entries("D", BENCH).items()}
    astar = set(sealed["plan"]["astar"])
    assert all(states[i] == ("dispatched" if i in astar else "routed_not_dispatched") for i in ITEMS)
    assert registry.consumed("D", BENCH) == frozenset(astar)


# ----------------------------------------------------------- T-ACC-8 selection evidence, reproducibility
def test_t_acc_8_selection_evidence_and_reproducible_from_cell_records(sealed):
    cells = make_cells(sealed)
    decision = acceptance.decide(cells, sealed)
    assert decision["evidence_kind"] == "selection" and decision["evidence"] == EVIDENCE
    assert acceptance.reproduce(plain(cells), plain(sealed), decision)
    stopped = plain(cells)
    stopped[0]["judge"] = None  # a stopped cell pauses the unit; it is never decided
    with pytest.raises(ValueError, match="judge"):
        acceptance.decide(stopped, sealed)
    changed = plain(cells)
    first = next(c for c in changed if c["arm"] == "S'" and c["set"] == "real")
    first["judge"]["v2"]["token"] = "fail" if first["judge"]["v2"]["token"] == "pass" else "pass"
    assert not acceptance.reproduce(changed, plain(sealed), decision)
    assert decision["sealed"]["record"] == sealed["record_sha256"] and decision["sealed"]["placebo_i"] is not None
    assert decision["sealed"]["donor_corpus"] == sealed["corpus"]["record_sha256"]
    assert decision["contrasts"]["P_i-S"]["n"] == 45  # OfficeQA runs P_i, descriptive
    assert set(decision) >= {"step", "bench", "chain", "unit", "freshness", "A", "A_star", "runs", "blocks",
                             "mde_registered", "sealed", "edits", "contrasts", "guards", "placebo_rule",
                             "second_call_rates", "twins", "decision", "reason"}


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_statistics_2_j6_tests_every_byte_identical_pair(tmp_path):
    first = seal(tmp_path, "empty", dup=True)  # an empty parent (S = C) and the registered S_dup
    assert first["card_is_parent"] and first["dup"]
    drift = acceptance.decide(make_cells(first, outcome(dict(PATTERNS, C=lambda k, r: True))), first)
    pairs = {p["pair"]: p for p in drift["guards"]["J6_dup"]["pairs"]}
    assert set(pairs) == {"C-S", "S_dup-S"} and pairs["S_dup-S"]["ok"] and not pairs["C-S"]["ok"]
    assert drift["decision"] == "undetermined" and "J6" in drift["reason"]


def test_statistics_3_officeqa_blocks_keep_the_registered_gap(tmp_path, sealed):
    cells = make_cells(sealed)
    assert acceptance.decide(cells, sealed)["guards"]["J5"]["block_gap"]["ok"]
    back_to_back = plain(cells)
    for cell in back_to_back:  # the second block sent right after the first
        if cell["dispatch_ts"] >= acceptance.BLOCK_GAP_SECONDS[BENCH]:
            cell["dispatch_ts"] -= acceptance.BLOCK_GAP_SECONDS[BENCH]
            cell["finish_ts"] -= acceptance.BLOCK_GAP_SECONDS[BENCH]
    decision = acceptance.decide(back_to_back, sealed)
    gap = decision["guards"]["J5"]["block_gap"]
    assert not gap["ok"] and gap["required_s"] == 7_200 and set(gap["windows"]) == {"b1", "b2"}
    assert decision["decision"] == "undetermined"
    # dispatch waits out the gap since the previous block finished
    registry = Registry(tmp_path / "history", evidence=EVIDENCE)
    registry.register("D", BENCH, list(RECORDS.values()), unit=UNIT, purpose="accept", run_root=str(tmp_path))
    now, waits = [0.0], []

    def run(block, jobs):
        now[0] += 100.0  # the block takes 100 s
        return []

    acceptance.dispatch(sealed, registry, run, items=RECORDS, clock=lambda: now[0],
                        sleep=lambda s: waits.append(s) or now.__setitem__(0, now[0] + s))
    assert waits == [7_200.0]


def test_statistics_4_an_undetermined_round_pauses_and_stays_consumed_but_undecided(tmp_path, sealed):
    registry = Registry(tmp_path / "history", evidence=EVIDENCE)
    registry.register("D", BENCH, list(RECORDS.values()), unit=UNIT, purpose="accept", run_root=str(tmp_path))
    acceptance.dispatch(sealed, registry, lambda block, jobs: [], items=RECORDS, sleep=lambda s: None)
    late = make_cells(sealed)
    for cell in late:  # a start-balance failure (§13 lists an imbalance among the pause cases)
        if cell["arm"] == "S'":
            cell["dispatch_ts"] -= 5000.0
    undetermined = acceptance.decide(late, sealed)
    assert undetermined["decision"] == "undetermined" and undetermined["guards"]["J5"]["pause"]
    with pytest.raises(acceptance.Pause) as stop:
        acceptance.settle(undetermined, sealed, registry, RECORDS)
    assert stop.value.kind == "acceptance_undetermined"
    astar = set(sealed["plan"]["astar"])
    states = {i: e["state"] for i, e in registry.entries("D", BENCH).items()}
    assert all(states[i] == "dispatched" for i in astar)
    decided = acceptance.decide(make_cells(sealed), sealed)
    assert decided["decision"] in ("accept", "reject")
    acceptance.settle(decided, sealed, registry, RECORDS)
    states = {i: e["state"] for i, e in registry.entries("D", BENCH).items()}
    assert all(states[i] == "decided" for i in astar)


# ------------------------------------------------------------- ticket C7c-2: a paused round redoes ONE block
# Registration §9.3 ("a pause redoes only one block", each redo in its own sub-scope) and owner decision #15 (default
# in force: the block is redone whole, cells of different attempts never spliced inside a block); plan §5 recovery.
BLOCKS3 = {item: "b%d" % (1 + k // 20) for k, item in enumerate(ITEMS)}  # three blocks of 20 items, 15 of A* each


class Clock:
    """Seconds that only cells (1 s each) and the dispatch's waits move."""

    def __init__(self, now=0.0):
        self.now, self.waits = now, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def stored_run(sealed, attempt, clock, *, log=None, stop_at=None, token=None):
    """A ``run(block, jobs)`` that stores one sealed cell record per job in ``<attempt>/cells`` -- the claim first, as
    ``cells.TrainingStore`` does -- naming its unit attempt as ``acceptance.runner`` does. ``stop_at`` = (block, n):
    the block's n-th job stops (its record stored without a verdict) and the round pauses there."""
    token = token or outcome(PATTERNS)

    def run(block, jobs):
        if log is not None:
            log.append(block)
        out = []
        for n, job in enumerate(jobs):
            stop = stop_at == (block, n)
            cell = {"id": acceptance.cell_id(sealed["unit"], job["arm"], job["item"], job["run"]),
                    "unit": sealed["unit"], "arm": job["arm"], "benchmark": BENCH, "task_id": job["item"],
                    "run": job["run"], "set": job["set"], "block": str(block), "source_item": job["source_item"],
                    "unit_attempt": attempt.name}
            (attempt / "cells").mkdir(parents=True, exist_ok=True)
            (attempt / "cells" / (cell["id"] + ".claim")).touch()
            judged = None if stop else {"v2": {"token": token(job)}, "format": {"violation": False}, "flags": []}
            value = record("cell", EVIDENCE, {
                "cell": cell, "arm": job["arm"], "task_id": job["item"], "run": job["run"], "set": job["set"],
                "block": str(block), "judge": judged, "final": None if stop else {"token": judged["v2"]["token"]},
                "stop": {"kind": "sandbox", "reason": "drill"} if stop else None, "faults": [],
                "logical_calls": [{"purpose": "first"}], "worst_delivery": "delivered", "sends": [{"n": 1}],
                "dispatch_ts": clock(), "finish_ts": clock() + 1.0})
            clock.now += 1.0
            write_json(attempt / "cells" / (cell["id"] + ".json"), value)
            if stop:
                raise acceptance.Pause("sandbox", "the test's stop inside " + str(block), cell["id"])
            out.append(value)
        return out

    return run


def no_run(block, jobs):
    raise AssertionError("block %s runs again" % block)


def attempts_of(decision):
    return {block: entry["attempt"] for block, entry in decision["provenance"].items()}


@pytest.fixture()
def three(tmp_path):
    """A sealed three-block OfficeQA round and its accept unit's root, registered in a fresh registry."""
    sealed = seal(tmp_path / "seal", blocks=BLOCKS3)
    registry = Registry(tmp_path / "history", evidence=EVIDENCE)
    registry.register("D", BENCH, list(RECORDS.values()), unit=UNIT, purpose="accept", run_root=str(tmp_path))
    return sealed, tmp_path / "unit", registry


def test_c7e_a_pause_inside_block_2_keeps_block_1_and_redoes_block_2_whole_then_block_3(three):
    sealed, root, registry = three
    plan = acceptance.schedule(sealed)
    assert list(plan) == ["b1", "b2", "b3"] and all(len(jobs) == 15 * 5 * 4 for jobs in plan.values())
    clock = Clock()
    with pytest.raises(acceptance.Pause):  # attempt 1: block 1 complete, paused at the 101st cell of block 2
        acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-1", clock, stop_at=("b2", 100)),
                            items=RECORDS, clock=clock, sleep=clock.sleep)
    assert clock.waits == [7_200.0]
    earlier = acceptance.earlier_blocks(sealed, root, root / "attempt-2")
    assert earlier["reused"] == {"b1": "attempt-1"} and earlier["redone"] == ["b2"]
    assert [acceptance.unit_attempt(c) for c in earlier["cells"]["b1"]] == ["attempt-1"] * 300
    ran = {"run": [], "redo": []}
    later = Clock(clock.now + 86_400.0)  # the owner's recovery a day later
    cells = acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-2", later, log=ran["run"]),
                                items=RECORDS, attempt=2, earlier=earlier, clock=later, sleep=later.sleep,
                                redo=stored_run(sealed, root / "attempt-2", later, log=ran["redo"]))
    assert ran == {"run": ["b3"], "redo": ["b2"]}  # blocks 2..3 only; block 2 on the redo's scopes
    assert later.waits == [7_200.0]  # the registered gap before block 3; block 1 finished a day earlier
    assert len(cells) == 900 and [acceptance.unit_attempt(c) for c in cells] == (
        ["attempt-1"] * 300 + ["attempt-2"] * 600)
    stored = sorted(p.name for p in (root / "attempt-2" / "cells").glob("*.json"))
    assert len(stored) == 600 and not {c["cell"]["id"] + ".json" for c in earlier["cells"]["b1"]} & set(stored)
    decision = acceptance.decide(cells, sealed)
    assert attempts_of(decision) == {"b1": "attempt-1", "b2": "attempt-2", "b3": "attempt-2"}
    assert decision["decision"] in ("accept", "reject") and decision["guards"]["J5"]["block_gap"]["ok"]
    balance = decision["guards"]["J5"]["balance"]
    assert balance["ok"] and balance["attempt_spans"] == 2 and balance["duration_s"] < 86_400.0
    # attempt 1's cells of block 2 are never read by the decision: removed, the decision is made again unchanged
    for path in (root / "attempt-1" / "cells").glob("*.json"):
        if verified(read_json(path), "cell")["cell"]["block"] == "b2":
            path.unlink()
    again = acceptance.round_cells(root, sealed, decision)
    assert again == plain(cells) and acceptance.reproduce(again, sealed, decision)


def test_c7e_a_pause_inside_block_1_redoes_block_1_whole_and_runs_the_rest(three):
    sealed, root, registry = three
    clock = Clock()
    with pytest.raises(acceptance.Pause):
        acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-1", clock, stop_at=("b1", 49)),
                            items=RECORDS, clock=clock, sleep=clock.sleep)
    earlier = acceptance.earlier_blocks(sealed, root, root / "attempt-2")
    assert earlier == {"reused": {}, "cells": {}, "redone": ["b1"]}  # nothing kept: block 1 is redone whole
    ran = {"run": [], "redo": []}
    cells = acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-2", clock, log=ran["run"]),
                                items=RECORDS, attempt=2, earlier=earlier, clock=clock, sleep=clock.sleep,
                                redo=stored_run(sealed, root / "attempt-2", clock, log=ran["redo"]))
    assert ran == {"run": ["b2", "b3"], "redo": ["b1"]}
    decision = acceptance.decide(cells, sealed)
    assert attempts_of(decision) == {"b1": "attempt-2", "b2": "attempt-2", "b3": "attempt-2"}
    assert decision["guards"]["J5"]["balance"]["attempt_spans"] == 1
    assert acceptance.reproduce(acceptance.round_cells(root, sealed, decision), sealed, decision)


def test_c7e_a_block_with_one_missing_cell_is_not_reused_and_runs_again_whole(three):
    sealed, root, registry = three
    clock = Clock()
    with pytest.raises(acceptance.Pause):
        acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-1", clock, stop_at=("b2", 0)),
                            items=RECORDS, clock=clock, sleep=clock.sleep)
    assert acceptance.earlier_blocks(sealed, root, root / "attempt-2")["reused"] == {"b1": "attempt-1"}
    job = acceptance.schedule(sealed)["b1"][123]  # one finished record of block 1 lost (its claim stays)
    (root / "attempt-1" / "cells" / (acceptance.cell_id(UNIT, job["arm"], job["item"], job["run"]) + ".json")).unlink()
    earlier = acceptance.earlier_blocks(sealed, root, root / "attempt-2")
    assert earlier == {"reused": {}, "cells": {}, "redone": ["b1", "b2"]}
    ran = {"run": [], "redo": []}
    cells = acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-2", clock, log=ran["run"]),
                                items=RECORDS, attempt=2, earlier=earlier, clock=clock, sleep=clock.sleep,
                                redo=stored_run(sealed, root / "attempt-2", clock, log=ran["redo"]))
    assert ran == {"run": ["b3"], "redo": ["b1", "b2"]} and len(cells) == 900
    assert set(attempts_of(acceptance.decide(cells, sealed)).values()) == {"attempt-2"}
    # a stopped (unjudged) record is not finished either; nor a record of another attempt's directory name
    records = {p.name: verified(read_json(p), "cell") for p in (root / "attempt-2" / "cells").glob("*.json")}
    first = acceptance.schedule(sealed)["b1"][0]
    name = acceptance.cell_id(UNIT, first["arm"], first["item"], first["run"]) + ".json"
    assert acceptance._finished(records[name], sealed, first, "attempt-2")
    assert not acceptance._finished(records[name], sealed, first, "attempt-1")
    assert not acceptance._finished({**records[name], "judge": None}, sealed, first, "attempt-2")
    assert not acceptance._finished(records[name], sealed, {**first, "block": "b2"}, "attempt-2")


def test_c7e_a_round_complete_in_an_earlier_attempt_is_reused_whole_and_nothing_runs(three):
    sealed, root, registry = three
    clock = Clock()
    cells = acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-1", clock), items=RECORDS,
                                clock=clock, sleep=clock.sleep)
    earlier = acceptance.earlier_blocks(sealed, root, root / "attempt-2")
    assert earlier["reused"] == {"b1": "attempt-1", "b2": "attempt-1", "b3": "attempt-1"} and not earlier["redone"]
    again = acceptance.dispatch(sealed, registry, no_run, items=RECORDS, attempt=2, earlier=earlier, redo=no_run,
                                clock=clock, sleep=clock.sleep)
    assert plain(again) == plain(cells) and acceptance.decide(again, sealed) == acceptance.decide(cells, sealed)
    with pytest.raises(ValueError, match="no earlier block"):  # a first attempt never reuses
        acceptance.dispatch(sealed, registry, no_run, items=RECORDS, earlier=earlier, clock=clock, sleep=clock.sleep)


def test_c7e_mutations_splicing_one_cell_or_reusing_a_partial_block_fail_loudly(three, monkeypatch):
    sealed, root, registry = three
    clock = Clock()
    last = len(acceptance.schedule(sealed)["b2"]) - 1
    with pytest.raises(acceptance.Pause):  # block 2: every cell stored, the last one stopped
        acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-1", clock, stop_at=("b2", last)),
                            items=RECORDS, clock=clock, sleep=clock.sleep)
    earlier = acceptance.earlier_blocks(sealed, root, root / "attempt-2")
    assert earlier["reused"] == {"b1": "attempt-1"} and earlier["redone"] == ["b2"]
    cells = acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-2", clock), items=RECORDS,
                                attempt=2, earlier=earlier, redo=stored_run(sealed, root / "attempt-2", clock),
                                clock=clock, sleep=clock.sleep)
    decision = acceptance.decide(cells, sealed)
    # splicing: one cell of block 2 taken from attempt 1 (same job, judged there) instead of attempt 2
    job = acceptance.schedule(sealed)["b2"][7]
    name = acceptance.cell_id(UNIT, job["arm"], job["item"], job["run"]) + ".json"
    old = verified(read_json(root / "attempt-1" / "cells" / name), "cell")
    spliced = [old if c["cell"]["id"] + ".json" == name else c for c in cells]
    with pytest.raises(ValueError, match="one unit attempt"):
        acceptance.decide(spliced, sealed)
    tweaked = plain(cells)  # a field no statistic reads: the block's record digest still binds the decision to it
    tweaked[400]["sends"] = [{"n": 2}]
    assert acceptance.decide(tweaked, sealed)["decision"] == decision["decision"]
    assert not acceptance.reproduce(tweaked, sealed, decision) and acceptance.reproduce(plain(cells), sealed, decision)
    # a partial block: one cell missing, or one cell twice
    with pytest.raises(ValueError, match="missing"):
        acceptance.decide([c for c in cells if c["cell"]["id"] + ".json" != name], sealed)
    with pytest.raises(ValueError, match="twice"):
        acceptance.decide(cells + [cells[400]], sealed)
    # the mutation "a stored record is a finished one": block 2 of attempt 1 (its last cell stopped) is reused
    monkeypatch.setattr(acceptance, "_finished", lambda record, *args: record is not None)
    partial = acceptance.earlier_blocks(sealed, root, root / "attempt-3")
    assert partial["reused"]["b2"] == "attempt-1"
    reused = acceptance.dispatch(sealed, registry, no_run, items=RECORDS, attempt=3, earlier=partial, redo=no_run,
                                 clock=clock, sleep=clock.sleep)
    with pytest.raises(ValueError, match="judge"):  # the stopped cell reaches the decision and is refused
        acceptance.decide(reused, sealed)


# --------------------------------------------------------------- ticket PR-F2-1: the §6.2 15-minute series
# Registration §6.2 ("每格记派发与完成时间；按组、按 15 分钟报告简短回答比例、答案格式比例、回答长度"); registrar decision
# 2026-10-22 (14:1x) on ticket PR-F2-1: the series by readout's definitions (the short answer of decision fixer-2),
# descriptive, deciding nothing.
def usage_cells(sealed, tokens, *, tagged=lambda cell: True):
    """``make_cells`` whose one logical call per cell has a last send whose receipt reports ``tokens(cell)`` completion
    tokens (None: a receipt without usage), with the answer tag present where ``tagged(cell)``."""
    cells = make_cells(sealed)
    for cell in cells:
        count = tokens(cell)
        cell["logical_calls"] = [{"purpose": "first", "send_indices": [1]}]
        cell["sends"] = [{"receipt": None}, {"receipt": {"ok": True, **(
            {} if count is None else {"usage": {"prompt_tokens": 100, "completion_tokens": count}})}}]
        cell["judge"]["format"]["tag_present"] = tagged(cell)
    return cells


def window_of(cell, start):
    return int((cell["dispatch_ts"] - start) // acceptance.TIME_WINDOW_SECONDS)


def test_pr_f2_1_every_round_records_the_15_minute_series_per_set_and_arm(tmp_path):
    probe = ["probe-%02d" % k for k in range(30)]
    sealed = seal(tmp_path, "delete", probe=probe,
                  generate=lambda views: [{"id": "gen-" + i, "source_item": i} for i in sorted(views)[::4][:10]])

    def tokens(cell):  # C: a 4-token reply on every third item, else 40; P_i: no usage; the rest 40 or 80
        if cell["arm"] == "P_i":
            return None
        if cell["arm"] == "C":
            return 4 if k_of(cell["task_id"]) % 3 == 0 else 40
        return 40 if cell["run"] % 2 == 0 else 80

    cells = usage_cells(sealed, tokens, tagged=lambda cell: cell["arm"] != "S")
    decision = acceptance.decide(cells, sealed)
    found = decision["series"]
    start = min(c["dispatch_ts"] for c in cells)
    assert found["decides"] is False and found["start"] == start == 0.0 and found["short_answer"] == "1/4"
    assert found["window_seconds"] == acceptance.TIME_WINDOW_SECONDS == 900
    expected = {}
    for cell in cells:
        expected.setdefault(cell["set"], {}).setdefault(cell["arm"], []).append(cell)
    assert set(found["sets"]) == {"real", "G_acc", "probe"} == set(expected)
    for name, arms in expected.items():
        assert set(found["sets"][name]) == set(arms)
        for arm, members in arms.items():
            windows = found["sets"][name][arm]["windows"]
            counts = {}
            for cell in members:
                counts[window_of(cell, start)] = counts.get(window_of(cell, start), 0) + 1
            assert {w["window"]: w["cells"] for w in windows} == counts  # each cell in its own 15-minute window
            assert len(counts) >= 2  # OfficeQA's two time blocks, 2 h apart
            for w in windows:
                share = w["answer_tag_share"]
                assert share == (0.0 if arm == "S" else 1.0)
    real = found["sets"]["real"]
    # the card arm: the median of its first-window cells is 40, so a 4-token reply (< 10) is short
    assert real["C"]["short_answer_reference"] == {"window": 0, "cells": real["C"]["windows"][0]["cells"],
                                                   "no_usage": 0, "median": 40.0, "status": "defined"}
    for w in real["C"]["windows"]:
        members = [c for c in expected["real"]["C"] if window_of(c, start) == w["window"]]
        short = sum(k_of(c["task_id"]) % 3 == 0 for c in members)
        assert w["short_answer_share"] == short / len(members) and w["no_usage"] == 0
        assert w["mean_completion_tokens"] == sum(tokens(c) for c in members) / len(members)
    assert all(w["short_answer_share"] == 0.0 for w in real["S'"]["windows"])  # 40 and 80: never below a quarter
    # P_i reported no usage: no reference, no share, every cell counted as without usage; nothing stands in
    assert real["P_i"]["short_answer_reference"]["status"] == "no_cell_with_usage"
    assert all(w["short_answer_share"] is None and w["no_usage"] == w["cells"] for w in real["P_i"]["windows"])
    # the stored record and the decision made again from the cells carry the same series
    assert acceptance.reproduce(plain(cells), plain(sealed), plain(decision))
    path = acceptance.write(tmp_path / "unit", decision)
    assert verified(read_json(path), "decision")["series"] == plain(found)


def test_pr_f2_1_the_series_decides_nothing(sealed):
    normal = usage_cells(sealed, lambda cell: 40)
    short = usage_cells(sealed, lambda cell: 4 if cell["arm"] == "S'" and cell["dispatch_ts"] > 900 else 40,
                        tagged=lambda cell: cell["arm"] != "S'")
    first, second = acceptance.decide(normal, sealed), acceptance.decide(short, sealed)
    assert first["series"] != second["series"]
    assert second["series"]["sets"]["real"]["S'"]["windows"][-1]["short_answer_share"] == 1.0
    assert second["series"]["sets"]["real"]["S'"]["windows"][-1]["answer_tag_share"] == 0.0
    ignored = {"series", "provenance", "record_sha256"}  # provenance digests the records themselves (C7e)
    assert {k: v for k, v in first.items() if k not in ignored} == {k: v for k, v in second.items() if k not in ignored}
    # nor whether the shares exist at all: the same calls without usage leave every share None, the decision as it was
    missing = acceptance.decide(usage_cells(sealed, lambda cell: None), sealed)
    assert all(w["short_answer_share"] is None and w["mean_completion_tokens"] is None
               for arms in missing["series"]["sets"].values() for arm in arms.values() for w in arm["windows"])
    assert {k: v for k, v in first.items() if k not in ignored} == {k: v for k, v in missing.items() if k not in ignored}
    # without usage or dispatch times the series is empty or None-valued, and the verdict is the same
    plain_cells = make_cells(sealed)  # no send indices: every cell is without usage
    third = acceptance.decide(plain_cells, sealed)
    assert third["decision"] == first["decision"] and third["guards"] == first["guards"]
    assert all(w["short_answer_share"] is None and w["no_usage"] == w["cells"]
               for arms in third["series"]["sets"].values() for arm in arms.values() for w in arm["windows"])



# ------------------------------------- registrar addendum 2026-10-22 14:10, row 17: a round paused after its last cell
def paused(attempt, kind, reason="drill"):
    """The status ``units.run_unit`` leaves in a paused attempt."""
    attempt.mkdir(parents=True, exist_ok=True)
    write_json(attempt / "status.json", record("unit-status", EVIDENCE, {"status": "paused", "kind": kind,
                                                                         "reason": reason, "cell": None}))


def stored_round(root, registry, **stop):
    """An accept unit as ``step._accept`` lays it out -- the sealed round in its root, beside its attempts -- whose
    first attempt dispatched the three-block round (paused at ``stop_at`` when given). Returns (sealed, cells)."""
    sealed, clock = seal(root, blocks=BLOCKS3), Clock()
    registry.register("D", BENCH, list(RECORDS.values()), unit=UNIT, purpose="accept", run_root=str(root))
    try:
        return sealed, acceptance.dispatch(sealed, registry, stored_run(sealed, root / "attempt-1", clock, **stop),
                                           items=RECORDS, clock=clock, sleep=clock.sleep)
    except acceptance.Pause:
        return sealed, None


def test_row17_a_round_whose_cells_are_all_done_and_that_paused_undetermined_or_in_decide_is_final(tmp_path):
    """Registrar decision C7e-2 (choice 1), addendum 14:10 row 17: ``finished_round`` names why a paused attempt of an
    accept unit is a finished round -- every block complete (a redo would reuse them all) and the pause is
    ``acceptance_undetermined`` or an error raised by ``decide`` -- and is None for anything else."""
    root = tmp_path / "unit"
    sealed, cells = stored_round(root, Registry(tmp_path / "history", evidence=EVIDENCE))
    first = root / "attempt-1"
    assert len(cells) == 900 and acceptance.finished_round(first) is None  # every cell done, no pause recorded
    try:  # an error raised by decide (a round missing one cell), as units.run_unit keeps its traceback
        acceptance.decide(cells[:-1], sealed)
    except ValueError:
        (first / "diagnostics.log").write_text(traceback.format_exc(), encoding="utf-8")
    paused(first, "configuration", "ValueError")
    assert acceptance.finished_round(first) == "an error raised by acceptance.decide"
    second = root / "attempt-2"  # a redo of it reuses every block and decides undetermined (J5: start balance)
    late = make_cells(sealed)
    for cell in late:
        if cell["arm"] == "S'":
            cell["dispatch_ts"] -= 5000.0
    undetermined = acceptance.decide(late, sealed)
    assert undetermined["decision"] == "undetermined"
    acceptance.write(second, undetermined)
    assert acceptance.finished_round(second) == "acceptance_undetermined"
    paused(root / "attempt-3", "acceptance_undetermined", "J6")  # the pause kind alone says it too
    assert acceptance.finished_round(root / "attempt-3") == "acceptance_undetermined"
    # an error raised elsewhere in acceptance.py is not decide's; nor is a pause of another kind
    try:
        acceptance.earlier_blocks(sealed, root, root / "not-an-attempt")
    except ValueError:
        (root / "attempt-4").mkdir()
        (root / "attempt-4" / "diagnostics.log").write_text(traceback.format_exc(), encoding="utf-8")
    assert "acceptance.py" in (root / "attempt-4" / "diagnostics.log").read_text()
    paused(root / "attempt-4", "configuration", "ValueError")
    paused(root / "attempt-5", "sandbox")
    assert acceptance.finished_round(root / "attempt-4") is acceptance.finished_round(root / "attempt-5") is None
    assert acceptance.finished_round(root) is None  # not an attempt


def test_row17_a_round_with_a_block_still_to_run_or_without_a_sealed_round_is_not_final(tmp_path):
    root = tmp_path / "unit"
    sealed, cells = stored_round(root, Registry(tmp_path / "history", evidence=EVIDENCE), stop_at=("b3", 7))
    assert cells is None and acceptance.earlier_blocks(sealed, root, root / "attempt-2")["redone"] == ["b3"]
    paused(root / "attempt-1", "acceptance_undetermined")  # whatever it says, block b3 runs again in a redo
    assert acceptance.finished_round(root / "attempt-1") is None
    run = tmp_path / "s2-officeqa" / "run" / "attempt-1"  # a unit without a sealed round
    paused(run, "acceptance_undetermined")
    assert acceptance.finished_round(run) is None


# ------------------------------------------------------------------- M round (Codex review 2026-10-22, #12)
INHERITED = procedure("p-spreadsheetbench-1-1", ("applies", "before_call"), header="Sheet helper notes.")


def test_codex_12_inherited_twins_on_a_run_s_prime_and_the_twin_outside_astar_and_count_in_tau(tmp_path):
    """§6.5: an inherited procedure (from SpreadsheetBench) fires on 34 items of A but on 14 of A*: it is eligible on
    A (>= 15), its twins are drawn there, and each twin item outside A* runs S' and the twin only, every run, in its own
    block. Those items are dispatched and decided with A*; tau counts them (``n_outside_astar``); no decision contrast
    reads them and the per-arm rates stay on A*."""
    from skillopt.execskill import router

    parent = Package((INHERITED,), "s1", EVIDENCE)
    candidate = with_(parent, step="s2", add=[N])  # one new procedure: S' - S on A* is its own tau, no twin
    table = {INHERITED.id: {"applies": lambda view: row(view) >= 26, "before_call": note},
             N.id: {"applies": lambda view: row(view) < 40, "before_call": note}}
    sealed = acceptance.prepare(tmp_path / "round", chain="D", bench=BENCH, step=STEP, unit=UNIT, candidate=candidate,
                                parent=parent, views=VIEWS, blocks=BLOCKS, workers=workers(table),
                                trajectories=TRAJECTORIES, freshness="route_b_fresh_method_side_reused", mde=0.10)
    plan, runs = sealed["plan"], sealed["runs"]
    astar = set(plan["astar"])
    firing = [i for i in ITEMS if k_of(i) >= 26]
    assert len(astar) == 40 and plan["decision"] == "run"
    assert len(firing) == 34 >= 15 > len([i for i in firing if i in astar]) == 14
    assert plan["twin_priority"] == [INHERITED.id] and plan["twin_kinds"] == {INHERITED.id: "withhold"}
    drawn = router.seeded_half(firing, UNIT, INHERITED.id)
    outside = [i for i in ITEMS if i in drawn and i not in astar]
    assert sorted(plan["twins"]) == sorted(drawn) and outside and len(outside) < len(drawn)
    assert plan["twin_only"] == outside == acceptance.twin_only(sealed)
    assert acceptance.dispatched(sealed) == plan["astar"] + outside + list(sealed["probe"])
    twin = "withhold:" + INHERITED.id
    jobs = [j for block in acceptance.schedule(sealed).values() for j in block]
    assert {j["item"] for j in jobs if j["set"] == "real"} == astar | set(outside)
    for item in outside:  # S' and the twin, every run, in the item's own block; no S, C or placebo
        mine = [j for j in jobs if j["item"] == item]
        assert sorted((j["arm"], j["run"]) for j in mine) == sorted((a, r) for a in ("S'", twin) for r in range(runs))
        assert {j["block"] for j in mine} == {BLOCKS[item]}
    registry = Registry(tmp_path / "history", evidence=EVIDENCE)
    registry.register("D", BENCH, list(RECORDS.values()), unit=UNIT, purpose="accept", run_root=str(tmp_path))
    acceptance.dispatch(sealed, registry, lambda block, jobs: [], items=RECORDS, sleep=lambda seconds: None)
    sent = astar | set(outside)
    states = {i: e["state"] for i, e in registry.entries("D", BENCH).items()}
    assert all(states[i] == ("dispatched" if i in sent else "routed_not_dispatched") for i in ITEMS)
    cells = make_cells(sealed, calls=lambda job: ("second",) if job["arm"] == "S'" and job["item"] in outside else ())
    decision = acceptance.decide(cells, sealed)
    tau = decision["twins"][INHERITED.id]
    assert tau["n"] == len(drawn) and tau["n_outside_astar"] == len(outside) and tau["tau"] == 0.0  # twins follow S'
    assert decision["twins_cap"]["outside_astar"] == {"items": len(outside), "unanswered": [],
                                                      "cells": 2 * runs * len(outside)}
    assert decision["A_star"] == decision["analysed"] == 40 and decision["contrasts"]["S'-S"]["n"] == 40
    assert decision["second_call_rates"]["S'"] == 0.0  # the twin-only S' cells are not compared with P_y and P_i
    assert acceptance.reproduce(plain(cells), plain(sealed), decision)
    assert decision["decision"] in ("accept", "reject")
    acceptance.settle(decision, sealed, registry, RECORDS)
    states = {i: e["state"] for i, e in registry.entries("D", BENCH).items()}
    assert all(states[i] == ("decided" if i in sent else "routed_not_dispatched") for i in ITEMS)
