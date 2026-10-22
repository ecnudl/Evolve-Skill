"""The five-bench step wiring of the main configuration (registrar addendum 2026-10-22 "Owner instructions 17:0x and
17:3x": SearchQA, LiveMath and ALFWorld steps; registration §3.1, §3.3, §6.4; tickets I1-1, C3-2) on synthetic
engineering fixtures, zero model calls:

- SearchQA: the run slice (300 x 1) comes from the pool after the smoke's 280; the acceptance slice (1,000 x 1, four
  blocks) from the kept fresh tail -- the pinned tail supply cut only through ``exclusion.apply_exclusion`` with the
  manifest-bound record and ``supply.slices(kept=)``; a resumed step reads its tail items back; a missing or changed
  pin, another exclusion record or an unpersisted one is refused before anything is sealed.
- LiveMath J7: run 54 meta-absent + 65 meta-present, acceptance 100 meta-absent, probe 64 meta-present; the accept unit
  registers the probe items as themselves (purpose ``accept_probe``) and sends them options-only -- the stem hidden by
  ``examiner.shortcut_public``, the transform of ``examiner.shortcut_variant`` -- while the acceptance items go as
  registered.
- ALFWorld: ``supply.alfworld_pool`` turns the fresh supply and its pre-reset views (bound to their runtime by
  ``supply.views_record``) into the ``data.pools.alfworld`` export; the step cuts run 60 and acceptance 150 from the
  registered room groups (<= 5 games per room) exactly as the views were cut, refuses games without a view or with a
  view of another runtime, and blocks the acceptance slice into four blocks of whole rooms, consecutive in the seeded
  room order. No P_i on ALFWorld (owner #9 not taken).
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from skillopt.coevo5.data import item_hash
from skillopt.coevo5.protocol import STRONGER_OPTION
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import examiner, exclusion, placebo, protocol, solver, step, supply
from skillopt.execskill.package import FIXTURE, empty
from skillopt.execskill.registry import Registry
from skillopt.validator_pilot.api import digest
from tests.fixtures.execskill import items as fx

CHAIN = "G"


def _step(tmp_path, bench, pools, *, extra=None, runtime=None, k=1):
    """A chain-G step of ``bench`` on fixture pools: the Setting's parts the slicing reads, a real registry."""
    setting = SimpleNamespace(root=tmp_path / "root", pools=pools, extra=dict(extra or {}), runtime=runtime or {},
                              evidence=FIXTURE, workers=1)
    services = SimpleNamespace(registry=Registry(tmp_path / "history", evidence=FIXTURE), item_workers=None,
                               clock=lambda: 0.0, sleep=lambda seconds: None)
    parent = empty(step="%s/s0" % CHAIN, evidence=FIXTURE)
    return step._Step(setting, services, CHAIN, bench, k, parent, tmp_path / "root" / CHAIN)


# ----------------------------------------------------------------------------------------------------- SearchQA
def _searchqa(n, part):
    return {"benchmark": "searchqa", "task_id": "sq-%s-%05d" % (part, n), "family_id": "sq:%s:%d" % (part, n),
            "part": part, "public": {"question": "Which fixture town keeps bell %s %d?" % (part, n),
                                     "context": "Fixture note: bell %s %d is kept in Fixtown %d." % (part, n, n)},
            "private": {"answers": ["Fixtown %d" % n]}}


def _persist_exclusion(root, items, dropped_ids):
    """The record ``exclude-tests`` persists under ``<root>/shared/exclusion/`` (counts and hashes only)."""
    dropped = sorted(hashlib.sha256(i.encode("utf-8")).hexdigest() for i in dropped_ids)
    value = protocol.record(exclusion.RECORD_KIND, exclusion.EVIDENCE, {
        "run": exclusion.SEARCHQA_RUN, "bench": "searchqa", "unit": "smoke/s0/test-exclusion",
        "consent_sha256": "0" * 64,
        "counts": {"supply": len(items), "test_items": 9, "dropped_by_id": len(dropped), "dropped_by_question": 0,
                   "kept": len(items) - len(dropped)},
        "dropped": dropped, "exclusion_sha256": digest(dropped), "supply_sha256": exclusion._supply_sha256(items)})
    path = root / protocol.EXCLUSION_DIR / (exclusion.SEARCHQA_RUN + ".json")
    write_json(path, value)
    return path, value


def _searchqa_step(tmp_path, *, tail=1_100, dropped=60):
    """A SearchQA step: the 600-item pool in its order; the tail supply of make-items, pinned; its persisted test
    exclusion dropping the first ``dropped`` items of the tail order (they would head the acceptance slice)."""
    pool = supply.order("searchqa", [_searchqa(n, "train") for n in range(600)])
    items = [{**_searchqa(n, "tail"), "position": protocol.SEARCHQA_TAIL_START + n} for n in range(tail)]
    gone = [i["task_id"] for i in supply.order("searchqa", items)[:dropped]]
    path = supply.write_supply(tmp_path / "history", supply.supply_record(
        "searchqa-tail", "searchqa", items, sources={"fixture": True}, evidence="smoke"))
    bound, value = _persist_exclusion(tmp_path / "smoke-root", items, gone)
    pin = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
           "exclusion": {"path": str(bound), "record_sha256": value[protocol.RECORD_HASH]}}
    return _step(tmp_path, "searchqa", {"searchqa": pool}, extra={step.TAIL: pin}), pool, items, gone


def test_searchqa_runs_on_the_pool_and_accepts_on_the_kept_tail(tmp_path):
    st, pool, items, gone = _searchqa_step(tmp_path)
    cut = step._slices(st)
    assert set(cut) == {"run", "accept"}
    smoke = {i["task_id"] for i in pool[len(pool) - 280:]}  # the smoke's items: the last 280 of the pool order
    assert cut["run"] == pool[:300] and not smoke & {i["task_id"] for i in cut["run"]}
    kept = [i for i in supply.order("searchqa", items) if i["task_id"] not in set(gone)]
    assert cut["accept"] == kept[:1_000] and all(i["part"] == "tail" for i in cut["accept"])
    assert not set(gone) & {i["task_id"] for i in cut["accept"]}  # no test item reaches the acceptance slice
    assert Counter(step._blocks(st, cut["accept"]).values()) == {"b1": 250, "b2": 250, "b3": 250, "b4": 250}
    sealed = read_json(st.root / step.SLICES_FILE)["slices"]
    assert sealed == {"run": [i["task_id"] for i in pool[:300]], "accept": [i["task_id"] for i in kept[:1_000]]}
    assert step._slices(st) == cut  # a resumed step reads its tail items back from the kept supply


def test_searchqa_tail_is_cut_only_with_its_pin_and_the_bound_exclusion(tmp_path):
    st, _, _, _ = _searchqa_step(tmp_path)
    pin = st.setting.extra[step.TAIL]
    elsewhere = str(tmp_path / "elsewhere" / "searchqa_test_exclusion.json")
    for extra, match in (({}, "pinned tail supply"),
                         ({step.TAIL: {**pin, "sha256": "0" * 64}}, "differs from its pin"),
                         ({step.TAIL: {**pin, "exclusion": {**pin["exclusion"], "record_sha256": "0" * 64}}},
                          "the manifest binds"),
                         ({step.TAIL: {**pin, "exclusion": {**pin["exclusion"], "path": elsewhere}}},
                          "persisted exclude-tests record")):
        st.setting.extra = extra
        with pytest.raises(ValueError, match=match):
            step._slices(st)
        assert not (st.root / step.SLICES_FILE).exists()
    assert st.services.registry.entries(CHAIN, "searchqa") == {}


# ----------------------------------------------------------------------------------------------------- LiveMath
def _livemath(n, meta):
    options = ["%d" % (n + k) for k in range(4)] + [STRONGER_OPTION if meta else "%d" % (n + 9)]
    return {"benchmark": "livemath", "task_id": "lm-%03d" % n, "family_id": "lm:%d" % n, "part": "train",
            "public": {"question": "Fixture stem %d: which statement about f holds?" % n,
                       "choices": "\n\n".join("%s. %s" % pair for pair in zip("ABCDE", options))},
            "private": {"answer": "ABCDE"[n % 5]}}


def _livemath_step(tmp_path):
    pool = supply.order("livemath", [_livemath(n, n % 283 < 129) for n in range(283)])  # 129 meta-present, as §3.1
    return _step(tmp_path, "livemath", {"livemath": pool}), pool


def test_livemath_cuts_the_j7_probe_and_its_cells_see_the_options_only(tmp_path):
    st, pool = _livemath_step(tmp_path)
    cut = step._slices(st)
    meta = {i["task_id"] for i in pool if supply.meta_present(i)}
    assert {name: len(items) for name, items in cut.items()} == {"run": 119, "accept": 100, "accept_probe": 64}
    assert sum(i["task_id"] in meta for i in cut["run"]) == 65
    assert not meta & {i["task_id"] for i in cut["accept"]} and {i["task_id"] for i in cut["accept_probe"]} <= meta
    records = {i["task_id"]: i for i in cut["accept"] + cut["accept_probe"]}
    tasks = step._round_tasks(records, cut["accept_probe"], None)
    for item in cut["accept_probe"]:  # §6.4 J7: the stem hidden, the options and the answer unchanged
        assert tasks[item["task_id"]] == {"public": {"question": "", "choices": item["public"]["choices"]},
                                          "private": item["private"]}
        assert records[item["task_id"]]["public"]["question"]  # the item itself is unchanged
    for item in cut["accept"]:
        assert tasks[item["task_id"]] == {"public": item["public"], "private": item["private"]}
    generated = protocol.record("generated-item", FIXTURE, {"id": "g-1", "benchmark": "livemath", "set": "G_self",
                                                            "public": dict(pool[0]["public"]), "private": {}})
    assert examiner.shortcut_variant(generated)["public"] == examiner.shortcut_public("livemath", pool[0]["public"])
    with pytest.raises(ValueError, match="meta-present"):
        step._round_tasks(records, cut["accept"][:1], None)


@dataclass(frozen=True)
class _Context:
    endpoint: object = None


def test_j7_the_accept_unit_registers_the_probe_and_sends_it_options_only(tmp_path, monkeypatch):
    """``step._accept`` on the LiveMath slices with the round's machinery replaced by recorders: the sealed probe is
    the 64 meta-present items, the acceptance views route the acceptance items only, the probe items are registered as
    themselves (purpose accept_probe) and the runner's tasks show them options-only."""
    st, _ = _livemath_step(tmp_path)
    cut = step._slices(st)
    seen = {}
    sealed = {"step": st.name, "plan": {"twins": {}}, "dup": False, "g_acc": None, protocol.RECORD_HASH: "s" * 64}
    decision = {"decision": "reject", "reason": "failed: J7", protocol.RECORD_HASH: "d" * 64, "guards": {}}

    def prepare(root, **options):
        seen.update(probe=options["probe"], views=options["views"])
        return sealed

    def runner(context, sealed_, packages, tasks, **options):
        seen["tasks"] = tasks
        return lambda block, jobs: []

    st.services = SimpleNamespace(**{**vars(st.services), "item_workers": lambda package, item: None})
    monkeypatch.setattr(st, "unit", lambda name, work, **options: work(tmp_path / "accept" / "attempt-1"))
    monkeypatch.setattr(st, "solver", lambda *args, **kwargs: None)
    monkeypatch.setattr(step, "_run_trajectories", lambda *args, **kwargs: [])
    monkeypatch.setattr(step.units, "cell_context", lambda *args, **kwargs: _Context())
    for name, value in (("prepare", prepare), ("round_packages", lambda *a, **k: {}), ("runner", runner),
                        ("dispatch", lambda *a, **k: []), ("decide", lambda cells, value: decision),
                        ("write", lambda attempt, value: None), ("settle", lambda *a, **k: decision)):
        monkeypatch.setattr(step.acceptance, name, value)
    found = step._accept(st, cut, object(), None)
    assert found["decision"] == "reject" and found["decision_sha256"] == "d" * 64
    assert seen["probe"] == [i["task_id"] for i in cut["accept_probe"]]
    assert list(seen["views"]) == [i["task_id"] for i in cut["accept"]]
    for item in cut["accept_probe"]:
        assert seen["tasks"][item["task_id"]]["public"] == {"question": "", "choices": item["public"]["choices"]}
    for item in cut["accept"]:
        assert seen["tasks"][item["task_id"]]["public"] == item["public"]
    lines = st.services.registry.entries(CHAIN, "livemath")
    assert {i: lines[i]["purpose"] for i in seen["probe"]} == {i: "accept_probe" for i in seen["probe"]}
    assert all(lines[i["task_id"]]["item_hash"] == item_hash(i) for i in cut["accept_probe"] + cut["accept"])
    assert {lines[i["task_id"]]["purpose"] for i in cut["accept"]} == {"accept"}


# ----------------------------------------------------------------------------------------------------- ALFWorld
def _runtime(root):
    return {"alfworld_data": str(root), "alfworld_split": "train", "alfworld_trace_version": "fixture-v1",
            "max_steps": 50, "seed": 42, "timeout_seconds": 60}


def _reset(item):
    return ("You are in room %s.\n\nYour task is to: look at the fixture %s." % (item["room"], item["task_id"]),
            ["look", "inventory", "go to desk 1"])


def _alfworld(tmp_path):
    """The fresh supply over 108 rooms (4 or 6 games each), make-items' pre-reset views of its registered cut, bound
    to the runtime the resets used."""
    root = tmp_path / "alfworld-data"
    fx.alfworld_tree(root, 108, lambda r: 6 if r % 4 else 4, first_room=101)
    games = supply.alfworld_items(root, {})
    value = supply.supply_record("alfworld-xs", "alfworld", games,
                                 sources={"data_root": str(root), "pool_games_sha256": "0" * 64}, evidence="smoke")
    runtime = _runtime(root)
    cut = supply.slices("alfworld", supply.order("alfworld", games), supply.registered_sizes("alfworld"))
    views = supply.views_record(value, supply.prereset(games, cut, reset=_reset), cut, runtime=runtime)
    return root, value, views, runtime, cut


def test_alfworld_pool_is_the_fresh_supply_with_views_of_the_pinned_runtime(tmp_path):
    root, value, views, runtime, cut = _alfworld(tmp_path)
    assert views["runtime_sha256"] == digest(runtime) and views["supply_sha256"] == value[protocol.RECORD_HASH]
    items, counts = supply.alfworld_pool(value, views, runtime=runtime)
    games = {g["task_id"]: g for g in value["items"]}
    assert [i["task_id"] for i in items] == [g["task_id"] for g in supply.order("alfworld", value["items"])]
    viewed = {i["task_id"] for part in cut.values() for i in part}
    assert counts["items"] == counts["pool"] == len(items) == len(games) and counts["rooms"] == 108
    assert counts["viewed"] == len(viewed) and counts["views_runtime_sha256"] == digest(runtime)
    for item in items:
        game = games[item["task_id"]]
        assert item["public"]["game_file"] == str(root / game["gamefile"]) and item["part"] == supply.FRESH_PART
        assert (item["room"], item["task_type"]) == (game["room"], game["task_type"])
        if item["task_id"] in viewed:
            assert solver.routing_view("alfworld", item["public"]) == views["views"][item["task_id"]]["view"]
            assert item["views_runtime_sha256"] == digest(runtime)
        else:
            assert "routing_view" not in item["public"] and "views_runtime_sha256" not in item
    supply.write_pool_export(tmp_path / "pools", {"alfworld": (items, counts)}, source={"fixture": True})
    assert supply.load_pool(tmp_path / "pools" / "alfworld.json", "alfworld") == items  # a data.pools file

    other = {**runtime, "seed": 7}
    with pytest.raises(ValueError, match="another runtime"):
        supply.alfworld_pool(value, views, runtime=other)
    moved = {**runtime, "alfworld_data": str(tmp_path)}
    with pytest.raises(ValueError, match="alfworld_data"):
        supply.alfworld_pool(value, supply.views_record(value, views["views"], cut, runtime=moved), runtime=moved)
    part = {name: cut[name] for name in ("smoke", "run")}
    fewer = supply.views_record(value, {i["task_id"]: views["views"][i["task_id"]] for p in part.values() for i in p},
                                part, runtime=runtime)
    with pytest.raises(ValueError, match="registered cut"):
        supply.alfworld_pool(value, fewer, runtime=runtime)
    another = supply.supply_record("alfworld-xs", "alfworld", value["items"][1:], sources=value["sources"],
                                   evidence="smoke")
    with pytest.raises(ValueError, match="another supply"):
        supply.alfworld_pool(another, views, runtime=runtime)
    changed = root / cut["accept"][0]["gamefile"]
    changed.write_text("another game", encoding="utf-8")
    with pytest.raises(ValueError, match="not the supply's"):
        supply.alfworld_pool(value, views, runtime=runtime)


def test_alfworld_step_cuts_the_run_and_acceptance_room_groups_and_blocks_whole_rooms(tmp_path):
    _, value, views, runtime, _ = _alfworld(tmp_path)
    items, _ = supply.alfworld_pool(value, views, runtime=runtime)
    st = _step(tmp_path, "alfworld", {"alfworld": supply.order("alfworld", items)}, runtime={"alfworld": runtime},
               k=5)
    cut = step._slices(st)
    assert set(cut) == {"run", "accept"}
    assert {name: [i["task_id"] for i in cut[name]] for name in cut} == {
        name: views["slices"][name] for name in ("run", "accept")}  # the games make-items reset, in that order
    groups = supply.room_groups(supply.room_order(items))
    assert len(cut["run"]) == 60 and {i["room"] for i in cut["run"]} == set(groups["run"])
    assert len(cut["accept"]) == 150 and {i["room"] for i in cut["accept"]} == set(groups["accept"])
    assert max(Counter(i["room"] for i in cut["run"] + cut["accept"]).values()) <= 5
    blocks = step._blocks(st, cut["accept"])
    rooms = {}
    for item in cut["accept"]:
        rooms.setdefault(blocks[item["task_id"]], set()).add(item["room"])
    assert sorted(rooms) == ["b1", "b2", "b3", "b4"] and [len(rooms[b]) for b in sorted(rooms)] == [10, 10, 10, 10]
    block_of = {room: block for block, members in rooms.items() for room in members}  # whole rooms
    labels = [block_of[room] for room in supply.room_order(cut["accept"])]
    assert labels == sorted(labels)  # consecutive in the seeded room order
    assert placebo.build_i({}, {}, bench="alfworld", unit="G/s5-alfworld/accept") is None  # no P_i (owner #9)


def test_alfworld_step_refuses_games_without_a_view_of_the_pinned_runtime(tmp_path):
    _, value, views, runtime, _ = _alfworld(tmp_path)
    items, _ = supply.alfworld_pool(value, views, runtime=runtime)
    pool = supply.order("alfworld", items)
    other = _step(tmp_path / "other", "alfworld", {"alfworld": pool}, runtime={"alfworld": {**runtime, "seed": 7}})
    with pytest.raises(ValueError, match="runtime this run pins"):
        step._slices(other)
    bare = [{key: value_ for key, value_ in item.items() if key != "views_runtime_sha256"}
            | {"public": {"game_file": item["public"]["game_file"]}} for item in pool]  # v3-shaped: no view
    viewless = _step(tmp_path / "bare", "alfworld", {"alfworld": bare}, runtime={"alfworld": runtime})
    with pytest.raises(ValueError, match="registered routing view"):
        step._slices(viewless)
    for st in (other, viewless):
        assert not (st.root / step.SLICES_FILE).exists() and st.services.registry.entries(CHAIN, "alfworld") == {}
