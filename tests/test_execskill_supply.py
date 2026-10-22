"""execskill supplies and slices (registration §3.1-§3.4, §10; plan T-SUPPLY-1..6) on synthetic fixtures. The SearchQA
fresh sample is drawn by the frozen builder itself (scripts/make_searchqa_fresh_sample.build) from a fake split, so
the tail builder is checked against the frozen draw. The pool export of tickets C6-3 / C7b1-2 runs on synthetic
frozen pools (``coevo5.data.pool`` replaced; no pool file is opened)."""
import hashlib
import json
from collections import Counter

import pytest

from scripts import make_searchqa_fresh_sample as fresh
from skillopt.coevo5 import data
from skillopt.coevo5.protocol import STRONGER_OPTION
from skillopt.execskill import supply
from skillopt.execskill.protocol import SEARCHQA_FRESH_SEED
from skillopt.validator_pilot.api import digest
from tests.fixtures.execskill import items as fx

REVISION = "fixture0123456789"


class FakeSplit:
    """A Hugging Face split as the builders use it: a column by name, a row by index, its cache files."""

    def __init__(self, rows, cache_file):
        self.rows = rows
        self.cache_files = [{"filename": str(cache_file)}]

    def __getitem__(self, key):
        return [row[key] for row in self.rows] if isinstance(key, str) else dict(self.rows[key])


def _row(n, question=None, context="Fixture context."):
    return {"key": "k%03d" % n, "question": question or "Which fixture item is number %d?" % n,
            "context": context, "answers": ["item %d" % n]}


@pytest.fixture
def source(tmp_path):
    """A fake validation split (60 rows: natives, an invalid row, a duplicate question), the native split files
    and the frozen builder's 8-item sample in four blocks."""
    rows = [_row(n) for n in range(60)]
    rows[20] = _row(20, context=" ")  # invalid
    rows[33] = _row(33, question="WHICH fixture item is number 32?!")  # normalizes to row 32's question
    natives = {part: [{"id": rows[n]["key"], "question": rows[n]["question"]} for n in ns]
               for part, ns in (("train", (3, 40)), ("val", (10, 17)), ("test", (31, 45, 52)))}
    natives["train"].append({"id": "hf-train-only", "question": "Which fixture item is number 7?"})
    native_dir = tmp_path / "native"
    for part, entries in natives.items():
        (native_dir / part).mkdir(parents=True)
        (native_dir / part / "items.json").write_text(json.dumps(entries), encoding="utf-8")
    cache = tmp_path / "hf" / REVISION / "validation.arrow"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"pinned fixture cache")
    split = FakeSplit(rows, cache)
    record, chosen = fresh.build({"validation": split}, native_dir, tmp_path / "fresh", count=8, blocks=4,
                                 seed=SEARCHQA_FRESH_SEED, dataset_name="fixture/searchqa", revision=REVISION)
    everything = [e for entries in natives.values() for e in entries]
    return {"split": split, "rows": rows, "native_dir": native_dir, "record": record, "chosen": chosen,
            "manifest": tmp_path / "fresh" / "sample_manifest.json",
            "pins": {str(cache): hashlib.sha256(cache.read_bytes()).hexdigest()},
            "exclude": {"ids": [e["id"] for e in everything], "questions": [e["question"] for e in everything]}}


def _tail(source, **overrides):
    arguments = {"exclude": source["exclude"], "cache_sha256": source["pins"], "start": 9, **overrides}
    return supply.searchqa_tail(source["manifest"], {"validation": source["split"]}, **arguments)


def test_searchqa_tail_continues_the_frozen_draw_after_the_blocks(source, tmp_path):  # T-SUPPLY-1
    files = sorted(p for p in tmp_path.rglob("*"))
    tail = _tail(source)
    assert sorted(p for p in tmp_path.rglob("*")) == files  # nothing written
    assert [i["position"] for i in tail] == list(range(9, 9 + len(tail))) and tail
    blocks = {i["id"] for i in source["chosen"]}
    assert not {i["task_id"] for i in tail} & (blocks | set(source["exclude"]["ids"]))
    _, longer = fresh.build({"validation": source["split"]}, source["native_dir"], tmp_path / "longer",
                            count=8 + len(tail), blocks=1, seed=SEARCHQA_FRESH_SEED, dataset_name="fixture/searchqa",
                            revision=REVISION)
    assert [i["id"] for i in longer[:8]] == [i["id"] for i in source["chosen"]]
    assert [i["id"] for i in longer[8:]] == [i["task_id"] for i in tail]  # the frozen draw, continued
    first = tail[0]
    assert set(first) == {"benchmark", "task_id", "family_id", "part", "position", "public", "private"}
    assert set(first["public"]) == {"question", "context"} and set(first["private"]) == {"answers"}
    assert "k020" not in {i["task_id"] for i in tail}  # invalid row
    assert _tail(source) == tail


def test_searchqa_tail_checks_every_block_and_its_inputs(source, tmp_path):  # T-SUPPLY-1
    with pytest.raises(ValueError, match="right after"):
        _tail(source, start=4001)
    with pytest.raises(ValueError, match="replay"):  # an exclusion without the test ids
        _tail(source, exclude={"ids": [], "questions": source["exclude"]["questions"]})
    sealed = source["record"]["blocks"]["block_d"]["ids"][0]
    index = [r["key"] for r in source["rows"]].index(sealed)
    source["rows"][index] = dict(source["rows"][index], context="A changed sealed context.")
    with pytest.raises(ValueError, match="block_d"):
        _tail(source)
    source["rows"][index] = _row(index)
    _tail(source)
    manifest = json.loads(source["manifest"].read_text(encoding="utf-8"))
    for change in (lambda m: m["skipped_before_full"].update(native_id=0),
                   lambda m: m["blocks"]["block_c"]["ids"].reverse(),
                   lambda m: m.update(seed="another-seed")):
        edited = json.loads(json.dumps(manifest))
        change(edited)
        path = tmp_path / ("m-%d.json" % len(list(tmp_path.glob("m-*.json"))))
        path.write_text(json.dumps(edited), encoding="utf-8")
        with pytest.raises(ValueError):
            supply.searchqa_tail(path, {"validation": source["split"]}, exclude=source["exclude"],
                                 cache_sha256=source["pins"], start=9)
    cache = next(iter(source["pins"]))
    with pytest.raises(ValueError, match="pinned"):
        _tail(source, cache_sha256={cache: "0" * 64})


def _alfworld(tmp_path):
    root = tmp_path / "alfworld-data"
    games = fx.alfworld_tree(root, 108, lambda r: 6 if r % 4 else 4, first_room=101)
    fx.alfworld_tree(root, 1, lambda r: 1, split="valid_seen", first_room=900)
    pool = {"train:0000": games[0], "train:0001": str(root / games[7]),
            "val:0000": "json_2.1.1/valid_seen/pick_and_place_simple-Obj0-None-Recep0-900/trial_T000_00/game.tw-pddl"}
    return root, games, pool, supply.alfworld_items(root, pool)


def test_alfworld_items_use_the_new_namespace_rooms_and_task_types(tmp_path):  # T-SUPPLY-5
    root, games, pool, items = _alfworld(tmp_path)
    assert len(items) == len(games) - 2 and {games[0], games[7]}.isdisjoint(i["gamefile"] for i in items)
    for item in items:
        assert item["task_id"].startswith("alfworld-xs:") and len(item["task_id"]) == len("alfworld-xs:") + 16
        assert item["task_id"] == supply.xs_id(item["gamefile"]) and item["task_id"] not in pool
        folder = item["gamefile"].split("/")[2]
        assert item["room"] == folder.split("-")[-1] and item["task_type"] == folder.split("-")[0]
        assert item["game_sha256"] == hashlib.sha256((root / item["gamefile"]).read_bytes()).hexdigest()
    assert len({i["room"] for i in items}) == 108 and len({i["task_type"] for i in items}) == 7
    with pytest.raises(FileNotFoundError):
        supply.alfworld_items(root, {"train:0099": "json_2.1.1/train/missing/trial_x/game.tw-pddl"})
    with pytest.raises(ValueError, match="task folder"):
        supply.task_folder("json_2.1.1/train/odd-folder/trial_1/game.tw-pddl")


def test_alfworld_slices_by_room_groups_with_five_games_per_room(tmp_path):  # T-SUPPLY-2, -6
    _, _, _, items = _alfworld(tmp_path)
    order = supply.order("alfworld", items)
    assert supply.order("alfworld", list(reversed(items))) == order
    rooms = list(dict.fromkeys(i["room"] for i in order))
    assert rooms == supply.room_order(items)
    groups = supply.room_groups(rooms)
    assert [len(groups[g]) for g in ("smoke", "run", "accept", "select", "spare")] == [4, 16, 40, 20, 28]
    sizes = {"smoke": 12, "run": 60, "accept": 150, "select": 200}
    cut = supply.slices("alfworld", order, sizes)
    capacity = sum(min(5, sum(i["room"] == room for i in items)) for room in groups["select"])
    assert {name: len(cut[name]) for name in cut} == {"smoke": 12, "run": 60, "accept": 150, "select": capacity}
    seen_rooms = {}
    for name, games in cut.items():
        assert {g["room"] for g in games} <= set(groups[name])
        assert max(Counter(g["room"] for g in games).values()) <= 5
        seen_rooms[name] = {g["room"] for g in games}
        for room in seen_rooms[name]:  # the games of a room are the first ones of its order
            ordered = [g for g in order if g["room"] == room]
            taken = [g for g in games if g["room"] == room]
            assert ordered[:len(taken)] == taken
    names = list(seen_rooms)
    assert all(not seen_rooms[a] & seen_rooms[b] for a in names for b in names if a < b)
    assert len(seen_rooms["accept"]) == 40  # round-robin spreads the acceptance games over all 40 rooms
    held = {cut["run"][0]["task_id"]}
    again = supply.slices("alfworld", order, sizes, consumed=held)
    assert held.isdisjoint(g["task_id"] for g in again["run"]) and len(again["run"]) == 60
    assert again["smoke"] == cut["smoke"]
    assert [len(v) for v in supply.room_groups(rooms[:54]).values()] == [2, 8, 20, 10, 14]


def test_prereset_touches_only_the_cut_slices(tmp_path):  # T-SUPPLY-5
    _, _, _, items = _alfworld(tmp_path)
    cut = supply.slices("alfworld", supply.order("alfworld", items), {"smoke": 12, "run": 60})
    calls = []

    def reset(item):
        calls.append(item["task_id"])
        return ("You are in the middle of a room.\n\nYour task is to: put a mug in fridge.",
                ["go to fridge 1", "look"])

    views = supply.prereset(items, cut, reset=reset)
    wanted = {i["task_id"] for part in cut.values() for i in part}
    assert set(calls) == wanted == set(views) and len(calls) == 72
    view = next(iter(views.values()))
    assert view["view"]["task_text"] == "put a mug in fridge."
    assert view["view_sha256"] == digest(view["view"])
    assert set(view["view"]) == {"initial_observation", "admissible_commands_at_reset", "task_text"}
    with pytest.raises(ValueError, match="outside the supply"):
        supply.prereset(items[:3], cut, reset=reset)


def test_slices_are_consecutive_and_smoke_is_taken_out_first():  # T-SUPPLY-3, -4
    officeqa = fx.officeqa_items()
    order = supply.order("officeqa", officeqa)
    assert order == data.ranked(officeqa, 20261021, "execskill-v1:order:officeqa")
    assert supply.order("officeqa", list(reversed(officeqa))) == order
    cut = supply.slices("officeqa", order, {"run": 6, "accept": 10})
    assert cut == {"run": order[:6], "accept": order[6:16]}
    skipped = supply.slices("officeqa", order, {"run": 6, "accept": 10}, consumed={order[2]["task_id"]})
    assert skipped == {"run": order[:2] + order[3:7], "accept": order[7:17]}
    with pytest.raises(ValueError, match="Too few"):
        supply.slices("officeqa", order, {"run": 6, "accept": 15})
    with pytest.raises(ValueError, match="Unknown slices"):
        supply.slices("officeqa", order, {"smoke": 2})
    pool = fx.searchqa_items()
    order = supply.order("searchqa", pool)
    cut = supply.slices("searchqa", order, {"smoke": 5, "run": 10})
    assert cut == {"smoke": order[-5:], "run": order[:10]}
    with pytest.raises(ValueError, match="Too few"):  # 20 - 12 smoke items leave 8 for a run of 10
        supply.slices("searchqa", order, {"smoke": 12, "run": 10})


def _livemath(n, meta):
    options = ["%d" % (n + k) for k in range(4)] + [STRONGER_OPTION if meta else "%d" % (n + 9)]
    return {"benchmark": "livemath", "task_id": "lm-%03d" % n, "family_id": "lm:%d" % n, "part": "train",
            "public": {"question": "Q%d" % n, "choices": "\n\n".join("%s. %s" % p for p in zip("ABCDE", options))},
            "private": {"answer": "A"}}


def test_livemath_formal_slices_split_the_meta_items():  # T-SUPPLY-6
    pool = [_livemath(n, n % 283 < 129) for n in range(283)]
    order = supply.order("livemath", pool)
    cut = supply.slices("livemath", order, {"run_absent": 54, "run_present": 65, "accept": 100, "accept_probe": 64})
    meta = {i["task_id"] for i in pool if supply.meta_present(i)}
    assert len(meta) == 129
    run = [i["task_id"] for i in cut["run"]]
    assert len(run) == 119 and len(set(run) & meta) == 65
    assert [i for i in order if i["task_id"] in set(run)] == cut["run"]  # the fixed order kept
    assert len(cut["accept"]) == 100 and not {i["task_id"] for i in cut["accept"]} & meta
    assert len(cut["accept_probe"]) == 64 and {i["task_id"] for i in cut["accept_probe"]} <= meta
    present = [i for i in order if i["task_id"] in meta]
    assert cut["accept_probe"] == present[65:]
    ids = run + [i["task_id"] for i in cut["accept"] + cut["accept_probe"]]
    assert len(ids) == len(set(ids)) == 283


def test_registered_sizes_are_the_registered_slices():
    assert supply.registered_sizes("spreadsheetbench") == {"run": 31, "accept": 60}
    assert supply.registered_sizes("officeqa") == {"run": 24, "accept": 50}
    assert supply.registered_sizes("alfworld") == {"smoke": 12, "run": 60, "accept": 150, "select": 200}
    assert supply.registered_sizes("livemath") == {"run_absent": 54, "run_present": 65, "accept": 100,
                                                   "accept_probe": 64}
    assert supply.registered_sizes("searchqa") == {"smoke": 280, "run": 300}
    assert supply.registered_sizes("searchqa", "tail") == {"accept": 1000}
    with pytest.raises(ValueError):
        supply.registered_sizes("officeqa", "tail")


def test_supply_records_are_versioned_and_written_once(tmp_path):
    _, _, _, items = _alfworld(tmp_path)
    record = supply.supply_record("alfworld-xs", "alfworld", items, sources={"data_root_sha256": "x"},
                                  evidence="engineering_fixture")
    assert record["version"] == "fivebench-execskill-v1-supply" and record["evidence"] == "engineering_fixture"
    assert record["counts"]["rooms"] == 108 and sum(record["counts"]["task_types"].values()) == len(items)
    path = supply.write_supply(tmp_path / "history", record)
    assert path == tmp_path / "history" / "supply" / "alfworld-xs.json"
    assert supply.write_supply(tmp_path / "history", record) == path  # byte-equivalent resume
    changed = supply.supply_record("alfworld-xs", "alfworld", items[1:], sources={}, evidence="engineering_fixture")
    with pytest.raises(ValueError, match="differs"):
        supply.write_supply(tmp_path / "history", changed)
    with pytest.raises(ValueError, match="blocks A-D"):
        supply.supply_record("searchqa-tail", "searchqa", [{"task_id": "k1", "position": 4000}], sources={},
                             evidence="smoke")


def test_fixture_items_have_the_frozen_public_views(tmp_path):
    builders = {"searchqa": fx.searchqa_items(), "officeqa": fx.officeqa_items(), "livemath": fx.livemath_items(),
                "spreadsheetbench": fx.spreadsheetbench_items(tmp_path / "sheets"),
                "alfworld": fx.alfworld_items(tmp_path / "alf")}
    for bench, built in builders.items():
        assert len(built) == (12 if bench == "alfworld" else 20)
        assert fx.panel(bench, built)["provenance"] == "fixture"
    livemath = builders["livemath"]
    assert sum(supply.meta_present(i) for i in livemath) == 5
    assert Counter(i["private"]["answer"] for i in livemath)["E"] >= 2
    games = fx.alfworld_games()
    assert len({g["room"] for g in games}) == 6 and len({g["task_type"] for g in games}) == 7
    assert sum(g["won_at"] <= 10 for g in games) == 6
    assert all(supply.task_folder(g["gamefile"]) == (g["room"], g["task_type"]) for g in games)
    assert all(fx.WON in g["terminal_observation"] for g in games)


# ---------------------------------------------------------------------------- pool export (tickets C6-3, C7b1-2)
def _frozen_pool(bench, count):
    """Synthetic items in the shape of the frozen ``coevo5.data.pool``: two thirds train, the rest val; ALFWorld
    items name a game file in the release layout."""
    items = []
    for n in range(count):
        public = {"question": "Synthetic %s question %d?" % (bench, n)}
        if bench == "alfworld":
            public = {"game_file": "/alf/json_2.1.1/%s/pick_and_place_simple-Mug-None-Shelf-%d/trial_T%d/game.tw-pddl"
                                   % ("train" if n % 2 else "valid_seen", 300 + n % 3, n)}
        items.append({"benchmark": bench, "task_id": "%s-%02d" % (bench, n), "family_id": "family-%d" % n,
                      "part": "train" if n < count * 2 // 3 else "val", "public": public, "private": {"answer": n}})
    return items


def test_c6_3_export_pool_is_the_frozen_pool_in_order_sheet_qualified_and_alfworld_with_rooms(monkeypatch):
    sizes = {"searchqa": 9, "officeqa": 6, "livemath": 6, "spreadsheetbench": 6, "alfworld": 6}
    calls = []

    def pool(pinned, bench):
        calls.append((pinned, bench))
        return _frozen_pool(bench, sizes[bench])

    monkeypatch.setattr(data, "pool", pool)
    monkeypatch.setattr(supply, "REGISTERED_POOLS", sizes)
    monkeypatch.setattr(supply, "SHEET_QUALIFIED", 4)
    pinned = {"paths": {}, "sha256": {}}
    items, counts = supply.export_pool(pinned, "searchqa")
    assert calls == [(pinned, "searchqa")] and items == supply.order("searchqa", _frozen_pool("searchqa", 9))
    assert counts == {"pool": 9, "parts": {"train": 6, "val": 3}, "items": 9, "written_parts": {"train": 6, "val": 3}}
    # SpreadsheetBench: the v3 training qualification of exactly these items keeps its qualified ones (data.qualified)
    frozen = _frozen_pool("spreadsheetbench", 6)
    sheet = {"side": "train", "qualified": [i["task_id"] for i in frozen[1:5]],
             "excluded": {frozen[0]["task_id"]: "other", frozen[5]["task_id"]: "other"},
             "task_hashes": {i["task_id"]: digest(i) for i in frozen}}
    items, counts = supply.export_pool(pinned, "spreadsheetbench", sheet=sheet)
    assert items == supply.order("spreadsheetbench", frozen[1:5]) and counts["pool"] == 6 and counts["items"] == 4
    with pytest.raises(ValueError, match="exported qualified"):
        supply.export_pool(pinned, "spreadsheetbench")
    with pytest.raises(ValueError, match="exported qualified"):
        supply.export_pool(pinned, "spreadsheetbench", sheet={**sheet, "side": "test"})
    with pytest.raises(ValueError, match="other items"):
        supply.export_pool(pinned, "spreadsheetbench", sheet={**sheet, "task_hashes": {
            **sheet["task_hashes"], frozen[2]["task_id"]: "0" * 64}})
    monkeypatch.setattr(supply, "SHEET_QUALIFIED", 5)
    with pytest.raises(ValueError, match="registered 5 qualified"):
        supply.export_pool(pinned, "spreadsheetbench", sheet=sheet)
    # ALFWorld: room and task type from the task folder, then the room-grouped order
    items, counts = supply.export_pool(pinned, "alfworld")
    assert all((i["room"], i["task_type"]) == supply.task_folder(i["public"]["game_file"]) for i in items)
    assert items == supply.order("alfworld", items) and {i["room"] for i in items} == {"300", "301", "302"}
    # a pool of another size than the registered one is refused
    monkeypatch.setattr(supply, "REGISTERED_POOLS", {**sizes, "officeqa": 7})
    with pytest.raises(ValueError, match="registered 7"):
        supply.export_pool(pinned, "officeqa")


def test_the_registered_pool_sizes_are_the_frozen_pools_and_the_sheet_slices():
    from skillopt.coevo5.protocol import POOLS
    from skillopt.execskill.protocol import SLICES

    assert supply.REGISTERED_POOLS == {"spreadsheetbench": 120, "officeqa": 74, "livemath": 283, "searchqa": 600,
                                       "alfworld": 57}  # registration §3.1
    assert supply.REGISTERED_POOLS == {bench: sum(parts) for bench, parts in POOLS.items()}
    assert supply.SHEET_QUALIFIED == SLICES["spreadsheetbench"]["run"][0] + SLICES["spreadsheetbench"]["accept"][0]


def test_c6_3_the_export_is_written_once_and_read_back_as_the_data_pools_contract(tmp_path):
    from skillopt.execskill import manifest

    searchqa = supply.order("searchqa", _frozen_pool("searchqa", 9))
    officeqa = supply.order("officeqa", _frozen_pool("officeqa", 6))
    pools = {"searchqa": (searchqa, {"items": 9}), "officeqa": (officeqa, {"items": 6})}
    value = supply.write_pool_export(tmp_path / "pools", pools, source={"manifest": "v3.json"})
    assert value["version"] == "fivebench-execskill-v1-pool-export" and value["evidence"] == "smoke"
    assert sorted(p.name for p in (tmp_path / "pools").iterdir()) == ["officeqa.json", "pools.json", "searchqa.json"]
    entry = value["pools"]["searchqa"]
    assert entry["ids_digest"] == digest([i["task_id"] for i in searchqa]) and entry["items_digest"] == digest(searchqa)
    pins = supply.pool_pins(value)
    assert pins == {bench: {"path": str(tmp_path / "pools" / (bench + ".json")), "sha256": hashlib.sha256(
        (tmp_path / "pools" / (bench + ".json")).read_bytes()).hexdigest()} for bench in ("officeqa", "searchqa")}
    assert supply.load_pool(tmp_path / "pools" / "searchqa.json", "searchqa") == searchqa
    assert manifest._items(pins["officeqa"], "officeqa") == officeqa  # the run adapters' reader of data.pools
    # written once; read back only as the record's own file of that bench
    with pytest.raises(ValueError, match="once"):
        supply.write_pool_export(tmp_path / "pools", pools, source={})
    with pytest.raises(ValueError, match="not the exported file"):
        supply.load_pool(tmp_path / "pools" / "officeqa.json", "searchqa")
    changed = tmp_path / "pools" / "officeqa.json"
    changed.write_text(changed.read_text().replace("question 1?", "question 9?"))
    with pytest.raises(ValueError, match="not the exported file"):
        supply.load_pool(changed, "officeqa")
    with pytest.raises(ValueError, match="once"):  # a duplicate or a foreign item is not a pool
        supply.write_pool_export(tmp_path / "other", {"searchqa": (searchqa + searchqa[:1], {"items": 10})}, source={})
    with pytest.raises(ValueError, match="once"):
        supply.write_pool_export(tmp_path / "third", {"searchqa": (searchqa[:2] + officeqa[:1], {"items": 3})},
                                 source={})
    assert not (tmp_path / "other").exists() and not (tmp_path / "third").exists()  # refused before any write
