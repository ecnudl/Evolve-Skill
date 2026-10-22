"""Supplies and slices (registration §3.1-§3.4, §10 smoke items; plan §1 supply.py, T-SUPPLY-1..6).

- SearchQA new block (``searchqa_tail``): the frozen fresh-sample draw (scripts/make_searchqa_fresh_sample.py:57-84)
  replayed on the pinned Hugging Face cache, TAIL ONLY. Blocks A-D (positions 1-4,000) are replayed only to check every
  id and every block hash against ``sample_manifest.json``; nothing of them is returned or written, so the sealed
  blocks C and D never reach a file on the development machine. The tail (positions 4,001 on) follows the same rule:
  the native items (ids; questions where readable) and every earlier drawn question are excluded. The test set's
  question-level exclusion runs separately under TestAccess (``exclusion.exclude_tests``).
- ALFWorld new games (``alfworld_items``): the ``json_2.1.1/train`` games outside the 57-game pool, ids in the new
  namespace ``alfworld-xs:<sha256(game file relative path)[:16]>`` (never a pool id); the room is the task folder's
  scene number, the task type its prefix. The id -> game-file mapping lives only in the registrar's supply file
  (``write_supply``), never in a role's view.
- ``prereset``: the zero-call reset that writes the ALFWorld routing view only for the cut slices (§3.1, O10).
- ``order``: one fixed order per bench, ``data.ranked(supply, 20261021, "execskill-v1:order:<bench>")``; ALFWorld
  groups the games by room (rooms in the seeded order ``execskill-v1:rooms``) and ranks the games within a room.
- ``slices``: consecutive slices of that order, each used once (§3.2, §3.3): the smoke items are taken out first
  (SearchQA: the last 280 of the pool order; ALFWorld: 12 games of the smoke room group), consumed items are skipped,
  then run / acceptance / probe / selection slices follow in the registered order. ALFWorld: the 108 rooms go, in the
  room order, to smoke 4, run 16, acceptance 40, selection 20 and spare 28 (in the same proportions when a recount
  differs), at most 5 games per room per slice, taken round-robin over the slice's rooms. LiveMath (formal chain):
  run = 54 meta-absent + the first 65 meta-present items, J7 probe = the remaining 64 meta-present items (purpose
  ``accept_probe``), acceptance = 100 meta-absent items. SearchQA tail items (part ``tail``) are cut only together
  with the sealed ``searchqa-kept`` record of their persisted test exclusion (``exclusion.apply_exclusion``; ticket
  C3-2), every one of them among its kept items: a tail never reaches a slice without its exclusion.
- The pools (tickets C6-3, C7b1-2; ``export_pool``, ``write_pool_export``, ``load_pool``): per bench the frozen
  ``coevo5.data.pool`` of the v3 data pins (historical train + val; it refuses every test id), its registered size
  checked (§3.1: SpreadsheetBench 120, OfficeQA 74, LiveMath 283, SearchQA 600, ALFWorld 57), SpreadsheetBench reduced
  to its 91 reference-qualified items as v3's manifest did (``data.qualified`` with the v3 training qualification:
  the run 31 + acceptance 60 slices), ALFWorld items given ``room`` and ``task_type`` from the game's task folder; each
  list in ``order``, written once as ``<bench>.json`` beside the sealed ``pools.json`` record. These files are the
  ``data.pools`` pins the run adapters read (``manifest._items``) and ``smoke-items --searchqa-pool``.
- ALFWorld's pool of the five-bench main experiment (registrar addendum 2026-10-22 17:0x, "ALFWorld step"; closes
  ticket I1-1): ``alfworld_pool`` turns the persisted fresh supply (``alfworld-xs``, all of its rooms) and the
  pre-reset routing views of its cut slices into the ``data.pools.alfworld`` export; ``views_record`` is the views
  record ``make-items`` writes, bound to the frozen runtime the resets ran with (``runtime_sha256``), so the views
  match the runtime a run pins.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from scripts.make_searchqa_fresh_sample import SOURCE_SPLIT, normalized
from skillopt.coevo5 import data as frozen_data
from skillopt.coevo5.data import ranked
from skillopt.continual_eval import datasets
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from .protocol import (
    ALFWORLD_ID_HEX,
    ALFWORLD_ID_PREFIX,
    ALFWORLD_ROUTING_VIEW,
    BENCHES,
    LIVEMATH_J7_PROBE,
    LIVEMATH_META_OPTION,
    LIVEMATH_RUN,
    MAX_GAMES_PER_ROOM,
    PRERESET_GAMES,
    RECORD_HASH,
    ROOM_GROUPS,
    ROOMS_TAG,
    SEARCHQA_FRESH_SEED,
    SEARCHQA_TAIL_START,
    SEED,
    SLICES,
    SMOKE_REAL_ITEMS,
    order_tag,
    record,
    verified,
)

RECORD_KIND = "supply"  # version fivebench-execskill-v1-supply
FRESH_VERSION = "searchqa-fresh-sample-v1"  # the frozen builder's manifest (make_searchqa_fresh_sample.py:86)
FRESH_BLOCKS = ("block_a", "block_b", "block_c", "block_d")
RELEASE = "json_2.1.1"
TASK_PREFIX = "Your task is to:"
REGISTERED_ROOMS = sum(ROOM_GROUPS.values())  # 108; a recount keeps the proportions
GROUPS = tuple(name for name in ROOM_GROUPS if name != "spare")
VIEWS_KIND = "alfworld-views"  # version fivebench-execskill-v1-alfworld-views: make-items' pre-reset views
FRESH_PART = "fresh"  # the part of ALFWorld's fresh-supply pool items (registrar addendum 2026-10-22 17:0x, I1-1)

# slice names per bench, in cutting order; "smoke" is taken out first, "select" is an upper bound (<= 200)
SLICE_NAMES = {"searchqa": ("smoke", "run", "accept"), "officeqa": ("run", "accept"),
          "spreadsheetbench": ("run", "accept"), "livemath": ("run_absent", "run_present", "accept", "accept_probe"),
          "alfworld": ("smoke", "run", "accept", "select")}
UPTO = frozenset({"select"})
# §3.1 table: each bench's pool (= the frozen coevo5 POOLS: historical train + val), SpreadsheetBench's qualified part
REGISTERED_POOLS = {"spreadsheetbench": 120, "officeqa": 74, "livemath": 283, "searchqa": 600, "alfworld": 57}
SHEET_QUALIFIED = 91  # §3.1 "120（91 道判分合格）": the v3 training qualification's (= SB run 31 + accept 60)
POOL_KIND = "pool-export"  # version fivebench-execskill-v1-pool-export
POOL_RECORD = "pools.json"  # the export record beside the pool files


# ----------------------------------------------------------------------------------------------- SearchQA tail
def _valid(row):
    """The frozen builder's eligibility rule (make_searchqa_fresh_sample.py:71-76)."""
    answers = row.get("answers")
    return bool(isinstance(row.get("question"), str) and row["question"].strip() and isinstance(row.get("context"), str)
                and row["context"].strip() and isinstance(answers, list) and answers
                and all(isinstance(a, str) and a.strip() for a in answers))


def _skip(key, row, ids, seen):
    """Why the frozen builder skips a row, in its order of checks (native id, invalid, duplicate), or None."""
    if key in ids:
        return "native_id"
    if not _valid(row):
        return "invalid"
    if normalized(row["question"]) in seen:
        return "duplicate_question"
    return None


def _pinned_cache(rows, revision, cache_sha256):
    files = [str(entry["filename"]) for entry in rows.cache_files]
    require(files and all(("/" + revision + "/") in name for name in files),
            "The dataset is not the cached revision the fresh sample was drawn from")
    require(set(files) == set(cache_sha256), "The cache files differ from the pinned list")
    for name in files:
        require(hashlib.sha256(safe_path(name).read_bytes()).hexdigest() == cache_sha256[name],
                "A cache file is not the pinned file")


def searchqa_tail(manifest_path, hf_cache, *, exclude, cache_sha256, start=SEARCHQA_TAIL_START):
    """SearchQA items at positions >= ``start`` of the frozen fresh-sample draw, as pool-shaped items with their
    ``position`` (part ``tail``). ``hf_cache``: the loaded dataset (its ``validation`` split, with ``cache_files``);
    ``cache_sha256``: {cache file: sha256} pinned by the registrar; ``exclude``: {"ids", "questions"} -- every native
    id (the pool, the test part and the reserve, ids only) and every readable native question (the pool's).
    Returns a list and writes nothing."""
    manifest = read_json(manifest_path)
    blocks = manifest.get("blocks")
    require(manifest.get("version") == FRESH_VERSION and manifest.get("seed") == SEARCHQA_FRESH_SEED
            and manifest.get("source_split") == SOURCE_SPLIT and isinstance(blocks, dict)
            and tuple(blocks) == FRESH_BLOCKS, "Unexpected fresh-sample manifest")
    count = manifest["count"]
    size = count // len(FRESH_BLOCKS)
    expected = [str(i) for name in FRESH_BLOCKS for i in blocks[name]["ids"]]
    require(all(len(blocks[name]["ids"]) == blocks[name]["items"] == size for name in FRESH_BLOCKS)
            and len(expected) == count == len(set(expected)), "The manifest's blocks are not four equal id lists")
    require(start == count + 1, "The tail starts right after the four blocks")
    require(type(exclude) is dict and set(exclude) == {"ids", "questions"}, "Exclusion needs ids and questions")
    rows = hf_cache[SOURCE_SPLIT]
    _pinned_cache(rows, manifest["source_revision"], cache_sha256)
    keys = [str(k) for k in rows["key"]]
    require(len(set(keys)) == len(keys) == manifest["source_rows"], "The source split differs from the manifest")
    order = sorted(range(len(keys)), key=lambda i: keys[i])
    random.Random(SEARCHQA_FRESH_SEED).shuffle(order)
    ids = frozenset(str(i) for i in exclude["ids"])
    seen = {normalized(q) for q in exclude["questions"]}
    walk, drawn, skipped = iter(order), [], Counter()
    for index in walk:  # blocks A-D: replayed and checked, never kept
        key, row = keys[index], rows[index]
        if key == expected[len(drawn)]:
            require(_skip(key, row, ids, seen) is None, "A block item fails the frozen selection rule")
            seen.add(normalized(row["question"]))
            drawn.append({"id": key, "question": row["question"], "context": row["context"], "answers": row["answers"]})
            if len(drawn) == count:
                break
        else:
            reason = _skip(key, row, ids, seen)
            require(reason is not None, "The replay does not reproduce blocks A-D")
            skipped[reason] += 1
    require(len(drawn) == count, "Blocks A-D were not found in the source order")
    require(dict(skipped) == {k: v for k, v in manifest["skipped_before_full"].items() if v},
            "The replay skipped other rows than the frozen draw")
    for number, name in enumerate(FRESH_BLOCKS):
        text = json.dumps(drawn[number * size:(number + 1) * size], ensure_ascii=False, indent=2)
        require(hashlib.sha256(text.encode("utf-8")).hexdigest() == blocks[name]["sha256"],
                "Block hash differs from the manifest: " + name)
    del drawn  # the sealed blocks' content is dropped here, before anything is returned
    tail = []
    for index in walk:
        key, row = keys[index], rows[index]
        if _skip(key, row, ids, seen) is None:
            seen.add(normalized(row["question"]))
            tail.append({"id": key, "question": row["question"], "context": row["context"], "answers": row["answers"]})
    if not tail:
        return []
    tasks = datasets.import_searchqa(tail, revision="searchqa-fresh-tail:" + manifest["source_revision"])["tasks"]
    items = [{"benchmark": "searchqa", "task_id": task["task_id"], "family_id": task["family_id"], "part": "tail",
              "position": start + n, "public": task["public"], "private": {"answers": task["private"]["answers"]}}
             for n, task in enumerate(tasks)]
    require(not {i["task_id"] for i in items} & set(expected), "A block item reached the tail")
    return items


# ----------------------------------------------------------------------------------------------- ALFWorld games
def task_folder(gamefile):
    """(room, task type) of a ``json_2.1.1/<split>/<type>-<object>-<movable>-<receptacle>-<scene>/trial_*/game.tw-pddl``
    path: the scene number is the room, the folder prefix the task type."""
    parts = Path(gamefile).parts
    require(len(parts) >= 3 and parts[-1] == "game.tw-pddl" and parts[-2].startswith("trial_"),
            "Unexpected ALFWorld game path")
    fields = parts[-3].split("-")
    require(len(fields) == 5 and fields[-1].isdigit() and fields[0], "Unexpected ALFWorld task folder: " + parts[-3])
    return fields[-1], fields[0]


def xs_id(relative):
    return ALFWORLD_ID_PREFIX + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:ALFWORLD_ID_HEX]


def alfworld_items(data_root, pool_games):
    """The new ALFWorld games: every ``json_2.1.1/train`` game outside the pool. ``pool_games``: {pool id: game file}
    of the 57-game pool (absolute, or relative to ``data_root``); each must exist. Items carry the relative game file
    (the registrar's supply only), room, task type and the game file's sha256."""
    root = Path(data_root).resolve(strict=True)
    pool = set()
    for game in pool_games.values():
        path = Path(game) if Path(game).is_absolute() else root / game
        pool.add(path.resolve(strict=True).relative_to(root).as_posix())
    items = []
    for game in sorted(root.glob(RELEASE + "/train/*/trial_*/game.tw-pddl")):
        relative = game.relative_to(root).as_posix()
        if relative in pool:
            continue
        room, task_type = task_folder(relative)
        items.append({"benchmark": "alfworld", "task_id": xs_id(relative), "gamefile": relative, "room": room,
                      "task_type": task_type, "game_sha256": hashlib.sha256(game.read_bytes()).hexdigest()})
    ids = [i["task_id"] for i in items]
    require(len(set(ids)) == len(ids), "Two game files share an id prefix")
    require(not set(ids) & {str(i) for i in pool_games}, "A new id equals a pool id")
    return items


def routing_view(initial_observation, admissible_commands):
    """The ALFWorld routing view (plan §3): the reset observation, the admissible commands at reset and the task text
    (the last "Your task is to:" line of the observation, else empty)."""
    require(type(initial_observation) is str and type(admissible_commands) is list
            and all(type(c) is str for c in admissible_commands), "Unexpected ALFWorld reset view")
    lines = [line.strip() for line in initial_observation.splitlines() if line.strip().startswith(TASK_PREFIX)]
    task_text = lines[-1][len(TASK_PREFIX):].strip() if lines else ""
    return dict(zip(ALFWORLD_ROUTING_VIEW, (initial_observation, list(admissible_commands), task_text)))


def alfworld_reset(data_root, runtime):
    """The production reset for ``prereset``: one reset of the frozen ALFWorld session (backends._new_alfworld with the
    frozen runtime; ALFWORLD_DATA set by the launch script), closed at once. Zero model calls."""
    from skillopt.continual_eval import backends

    root = Path(data_root).resolve(strict=True)

    def reset(item):
        env = backends._new_alfworld({"game_file": str(root / item["gamefile"])}, runtime)
        try:
            observations, _, infos = env.reset()
        finally:
            env.close()
        return str(observations[0]), list(infos[0].get("admissible_commands", []))

    return reset


def prereset(items, cut, *, reset):
    """{task id: {"view", "view_sha256"}} for the games of the cut slices only (``cut``: {slice: [items]}), in supply
    order; ``reset(item) -> (initial observation, admissible commands)``."""
    wanted = {i["task_id"] for part in cut.values() for i in part}
    require(wanted <= {i["task_id"] for i in items}, "The cut names games outside the supply")
    views = {}
    for item in items:
        if item["task_id"] in wanted:
            view = routing_view(*reset(item))
            views[item["task_id"]] = {"view": view, "view_sha256": digest(view)}
    return views


# ----------------------------------------------------------------------------------------------- order and slices
def room_order(supply):
    """The supply's rooms in the seeded room order."""
    return [r["task_id"] for r in ranked([{"task_id": room} for room in sorted({i["room"] for i in supply})],
                                         SEED, ROOMS_TAG)]


def order(bench, supply):
    """The bench's one fixed order (registration §3.2)."""
    ranked_items = ranked(supply, SEED, order_tag(bench))
    if bench != "alfworld":
        return ranked_items
    by_room = {}
    for item in ranked_items:
        by_room.setdefault(item["room"], []).append(item)
    return [item for room in room_order(supply) for item in by_room[room]]


def room_groups(rooms):
    """{group: rooms} of the rooms in room order: smoke, run, acceptance, selection, spare (registered counts for 108
    rooms; floor of the same proportions otherwise, the rest spare)."""
    groups, start = {}, 0
    for name in GROUPS:
        count = ROOM_GROUPS[name]
        take = count if len(rooms) == REGISTERED_ROOMS else count * len(rooms) // REGISTERED_ROOMS
        groups[name] = list(rooms[start:start + take])
        start += take
    groups["spare"] = list(rooms[start:])
    return groups


def meta_present(item):
    """LiveMath: the item offers the meta option (a stronger result can be proven)."""
    options = datasets.livemath_options(item["public"]["choices"])
    require(options is not None, "LiveMath choices are five labelled options")
    return any(text == LIVEMATH_META_OPTION for text in options)


def _take(name, rest, size):
    require(len(rest) >= size or name in UPTO, "Too few items for the %s slice" % name)
    return rest[:size], rest[size:]


def _alfworld(order_items, sizes, consumed):
    rooms = list(dict.fromkeys(i["room"] for i in order_items))
    groups = room_groups(rooms)
    games = {}
    for item in order_items:
        games.setdefault(item["room"], []).append(item)
    out = {}
    for name in SLICE_NAMES["alfworld"]:
        if name not in sizes:
            continue
        queues = [[g for g in games[room] if name == "smoke" or g["task_id"] not in consumed][:MAX_GAMES_PER_ROOM]
                  for room in groups[name]]
        picked = [queue[depth] for depth in range(MAX_GAMES_PER_ROOM) for queue in queues if depth < len(queue)]
        out[name], _ = _take(name, picked, sizes[name])
    return out


def slices(bench, order_items, sizes, consumed=frozenset(), *, kept=None):
    """{slice: [items]} cut from the bench's fixed order (``order``). ``sizes``: {slice: size} with the bench's slice
    names (``SLICE_NAMES``; ``registered_sizes`` gives the registered ones); ``consumed``: item ids that must not enter
    a slice (e.g. the smoke namespace's items), removed before the run / acceptance / probe / selection slices are cut
    consecutively. ``kept``: the sealed ``searchqa-kept`` record of ``exclusion.apply_exclusion``, required when any
    item is a SearchQA tail item, every one of which must be among its kept items (ticket C3-2)."""
    require(bench in SLICE_NAMES and set(sizes) <= set(SLICE_NAMES[bench]), "Unknown slices for this benchmark")
    require(all(type(v) is int and v >= 0 for v in sizes.values()), "Slice sizes are counts")
    tail = {i["task_id"] for i in order_items if i.get("part") == "tail"}
    if tail:
        require(kept is not None, "A SearchQA tail supply is cut only after its persisted test exclusion "
                "(exclusion.apply_exclusion)")
        require(tail <= {i["task_id"] for i in verified(kept, "searchqa-kept")["items"]},
                "A tail item outside the kept supply of its test exclusion")
    consumed = frozenset(consumed)
    if bench == "alfworld":
        return _alfworld(order_items, sizes, consumed)
    out, rest = {}, list(order_items)
    if "smoke" in sizes:  # the tail of the order, taken out first
        out["smoke"] = rest[len(rest) - sizes["smoke"]:] if sizes["smoke"] else []
        rest = rest[:len(rest) - sizes["smoke"]]
    rest = [i for i in rest if i["task_id"] not in consumed]
    if bench == "livemath":
        absent = [i for i in rest if not meta_present(i)]
        present = [i for i in rest if meta_present(i)]
        run_absent, absent = _take("run_absent", absent, sizes.get("run_absent", 0))
        run_present, present = _take("run_present", present, sizes.get("run_present", 0))
        chosen = {i["task_id"] for i in run_absent + run_present}
        out["run"] = [i for i in rest if i["task_id"] in chosen]
        out["accept"], _ = _take("accept", absent, sizes.get("accept", 0))
        out["accept_probe"], _ = _take("accept_probe", present, sizes.get("accept_probe", 0))
        return out
    for name in SLICE_NAMES[bench]:
        if name in sizes and name != "smoke":
            out[name], rest = _take(name, rest, sizes[name])
    return out


def registered_sizes(bench, part="pool"):
    """The registered slice sizes of ``protocol`` in the form ``slices`` takes (§3.3, §3.4, §10; LiveMath and SearchQA
    are the formal chain's tentative numbers). SearchQA: ``part`` "pool" (smoke 280 + run) or "tail" (acceptance)."""
    require(bench in BENCHES and part in ("pool", "tail") and (part == "pool" or bench == "searchqa"),
            "Unknown supply part")
    if bench == "alfworld":
        require(PRERESET_GAMES["smoke"] == sum(SMOKE_REAL_ITEMS["alfworld"].values())
                and all(PRERESET_GAMES[s] == SLICES["alfworld"][s][0] for s in ("run", "accept")),
                "The registered ALFWorld slices disagree")
        return dict(PRERESET_GAMES)
    if bench == "livemath":
        return {"run_absent": LIVEMATH_RUN["meta_absent"], "run_present": LIVEMATH_RUN["meta_present"],
                "accept": SLICES["livemath"]["accept"][0], "accept_probe": LIVEMATH_J7_PROBE}
    if bench == "searchqa" and part == "tail":
        return {"accept": SLICES["searchqa"]["accept"][0]}
    sizes = {"run": SLICES[bench]["run"][0]}
    if bench == "searchqa":
        return {"smoke": sum(SMOKE_REAL_ITEMS["searchqa"].values()), **sizes}
    return {**sizes, "accept": SLICES[bench]["accept"][0]}


# ----------------------------------------------------------------------------------------------- supply file
def supply_record(name, bench, items, *, sources, evidence):
    """The registrar's supply record (write-once; ``protocol.record`` of kind "supply"): the items, their counts and
    the pinned sources."""
    require(name in ("alfworld-xs", "searchqa-tail") and bench == name.split("-")[0], "Unknown supply")
    require(bench != "searchqa" or all(i["position"] >= SEARCHQA_TAIL_START for i in items),
            "A position of blocks A-D reached the SearchQA supply")
    require(len({i["task_id"] for i in items}) == len(items), "Duplicate supply ids")
    counts = {"items": len(items)}
    if bench == "alfworld":
        counts["rooms"] = len({i["room"] for i in items})
        counts["task_types"] = dict(sorted(Counter(i["task_type"] for i in items).items()))
    return record(RECORD_KIND, evidence, {"name": name, "bench": bench, "items": items, "counts": counts,
                                          "sources": sources})


def write_supply(history_root, value):
    """Write a supply record once under ``<history root>/supply/<name>.json``; returns the path."""
    value = verified(value, RECORD_KIND)
    path = safe_path(history_root) / "supply" / (value["name"] + ".json")
    write_json(path, value)
    return path


# ----------------------------------------------------------------------------------------------- pool export
def export_pool(pinned, bench, *, sheet=None):
    """(items, counts) of one bench's pool for ``data.pools`` (tickets C6-3, C7b1-2; zero calls): the frozen
    ``coevo5.data.pool(pinned, bench)`` -- the historical train and val parts of the v3 data pins, each item labelled
    with its part; it refuses a test id and checks the frozen sizes -- of the registered size (§3.1). SpreadsheetBench:
    ``sheet`` (the v3 training qualification, verified by the caller) must cover exactly these items (its task hashes),
    and only its reference-qualified items are kept (``data.qualified``, coevo5 manifest.py:129). ALFWorld: each item
    gets ``room`` and ``task_type`` from its game's task folder. The items are returned in ``order(bench, ...)``."""
    require(bench in REGISTERED_POOLS, "Unknown benchmark")
    items = frozen_data.pool(pinned, bench)
    require(len(items) == REGISTERED_POOLS[bench], "The %s pool is not the registered %d items"
            % (bench, REGISTERED_POOLS[bench]))
    counts = {"pool": len(items), "parts": dict(sorted(Counter(i["part"] for i in items).items()))}
    if bench == "spreadsheetbench":
        require(sheet is not None and sheet.get("side") == "train", "SpreadsheetBench is exported qualified, by the "
                "v3 training qualification")
        require({i["task_id"]: digest(i) for i in items} == sheet["task_hashes"],
                "The SpreadsheetBench qualification belongs to other items")
        items = frozen_data.qualified(items, sheet)
        require(len(items) == SHEET_QUALIFIED, "SpreadsheetBench keeps the registered %d qualified items"
                % SHEET_QUALIFIED)
    if bench == "alfworld":
        items = [{**item, **dict(zip(("room", "task_type"), task_folder(item["public"]["game_file"])))}
                 for item in items]
    ordered = order(bench, items)
    counts.update(items=len(ordered), written_parts=dict(sorted(Counter(i["part"] for i in ordered).items())))
    return ordered, counts


def _sha256(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def write_pool_export(out, pools, *, source, evidence="smoke"):
    """Write the pools once into the new directory ``out``: ``<bench>.json`` per bench (a JSON list of pool items in
    the bench's order: the ``data.pools`` contract, ticket C6-3) and the sealed ``pools.json`` record (each file's path,
    sha256, counts, and the digests of its ids and of its items). ``pools``: {bench: (items, counts)}
    (``export_pool``); ``source``: what they were read from. Returns the record."""
    out = safe_path(out)
    require(not out.exists(), "The pools are exported once, into a new directory")
    require(pools and set(pools) <= set(REGISTERED_POOLS), "Pools of known benchmarks")
    for bench, (items, counts) in pools.items():
        require(isinstance(items, list) and items and all(i.get("benchmark") == bench for i in items)
                and len({i["task_id"] for i in items}) == len(items) == counts["items"],
                "A %s pool lists each of its items once" % bench)
    out.mkdir(parents=True)
    entries = {}
    for bench, (items, counts) in sorted(pools.items()):
        path = out / (bench + ".json")
        write_json(path, items)
        entries[bench] = {"path": str(path), "sha256": _sha256(path), "counts": counts,
                          "ids_digest": digest([i["task_id"] for i in items]), "items_digest": digest(items)}
    value = record(POOL_KIND, evidence, {"pools": entries, "source": source})
    write_json(out / POOL_RECORD, value)
    return value


def pool_pins(export):
    """The ``data.pools`` pins block of an export record: {bench: {"path", "sha256"}} (``manifest._items``)."""
    value = verified(export, POOL_KIND)
    return {bench: {"path": entry["path"], "sha256": entry["sha256"]}
            for bench, entry in sorted(value["pools"].items())}


def load_pool(path, bench):
    """The items of an exported pool file (``write_pool_export``), checked against the sealed ``pools.json`` beside it:
    the file is the record's entry for ``bench`` (path and sha256), and lists that many items of ``bench``."""
    path = safe_path(path)
    require((path.parent / POOL_RECORD).is_file(), "Not an exported pool: no %s beside %s" % (POOL_RECORD, path.name))
    entry = verified(read_json(path.parent / POOL_RECORD), POOL_KIND)["pools"].get(bench)
    require(entry is not None and entry["path"] == str(path) and entry["sha256"] == _sha256(path),
            "The %s pool is not the exported file" % bench)
    items = read_json(path)
    require(isinstance(items, list) and len(items) == entry["counts"]["items"]
            and all(isinstance(i, dict) and i.get("benchmark") == bench for i in items),
            "The %s pool file lists its exported items" % bench)
    return items


# ------------------------------------------------------------------------------- ALFWorld pool from the fresh supply
def views_record(supply_value, views, cut, *, runtime, evidence="smoke"):
    """The sealed ``alfworld-views`` record that ``make-items`` writes once beside the ALFWorld supply (§3.1 O10): the
    pre-reset routing views of exactly the cut slices' games (``prereset``), the slices' ids and ``runtime_sha256``,
    the digest of the frozen ALFWorld runtime the resets ran with (registrar addendum 2026-10-22 17:0x, ALFWorld step:
    the views must match the runtime the run pins; ``alfworld_pool`` refuses views of another runtime)."""
    supply_value = verified(supply_value, RECORD_KIND)
    require(supply_value["name"] == "alfworld-xs" and isinstance(runtime, dict) and runtime,
            "The ALFWorld fresh supply and the runtime its views were reset with")
    wanted = {i["task_id"] for part in cut.values() for i in part}
    require(isinstance(views, dict) and set(views) == wanted
            and all(digest(v["view"]) == v["view_sha256"] for v in views.values()),
            "The views of exactly the cut games, each with its hash")
    return record(VIEWS_KIND, evidence, {
        "supply_sha256": supply_value[RECORD_HASH], "views": views, "runtime_sha256": digest(runtime),
        "slices": {name: [i["task_id"] for i in part] for name, part in sorted(cut.items())}})


def alfworld_pool(supply_value, views_value, *, runtime):
    """``(items, counts)`` of ALFWorld's ``data.pools`` entry from the fresh supply (registrar addendum 2026-10-22
    17:0x, "ALFWorld step: Pool: the fresh supply $HIST/supply/alfworld-xs.json with rooms, exported as
    data.pools.alfworld"; closes ticket I1-1), in the form ``export_pool`` returns for ``write_pool_export``. Every
    game of the persisted ``alfworld-xs`` supply, in ``order`` -- all of its rooms, so a step's ``slices`` gives the
    registered room groups (§3.1 O6; the groups are counted over the supply's rooms) -- as a pool item: its
    alfworld-xs ``task_id``, ``room``, ``task_type``, part ``fresh``, public ``game_file`` under the supply's data root
    and private game metadata, as the smoke's ALFWorld items (s0.py ``_alfworld_item``). The games of the registered
    cut (smoke 12, run 60, accept 150, select <= 200; ``registered_sizes``) also carry their pre-reset routing view and
    its hash in ``public`` (``views_value``, ``make-items``) and ``views_runtime_sha256``, the runtime the step checks
    against its pin (step ``_cut``). Refused unless the views record is this supply's, covers exactly its registered
    cut with intact view hashes, was reset with ``runtime`` -- the frozen ALFWorld runtime the run pins
    (``runtime.alfworld``) -- whose ``alfworld_data`` is the supply's data root, and every viewed game file is the
    supply's (sha256). Zero calls; nothing is written."""
    supply_value, views_value = verified(supply_value, RECORD_KIND), verified(views_value, VIEWS_KIND)
    require(supply_value["name"] == "alfworld-xs" and supply_value["bench"] == "alfworld",
            "The ALFWorld fresh supply (alfworld-xs)")
    require(views_value["supply_sha256"] == supply_value[RECORD_HASH], "The ALFWorld views belong to another supply")
    pinned = digest(runtime) if isinstance(runtime, dict) and runtime else None
    require(pinned is not None and views_value.get("runtime_sha256") == pinned,
            "The pre-reset routing views were made with another runtime than the one the run pins")
    root = safe_path(supply_value["sources"]["data_root"])
    require(type(runtime.get("alfworld_data")) is str and safe_path(runtime["alfworld_data"]) == root,
            "The supply's games are not under the pinned runtime's alfworld_data")
    ordered = order("alfworld", supply_value["items"])
    cut = slices("alfworld", ordered, registered_sizes("alfworld"))
    views = views_value["views"]
    require(views_value["slices"] == {name: [i["task_id"] for i in part] for name, part in sorted(cut.items())}
            and set(views) == {i["task_id"] for part in cut.values() for i in part},
            "The views are not those of the supply's registered cut")
    items = []
    for game in ordered:
        public, bound = {"game_file": str(root / game["gamefile"])}, {}
        view = views.get(game["task_id"])
        if view is not None:
            require(isinstance(view.get("view"), dict) and set(view["view"]) == set(ALFWORLD_ROUTING_VIEW)
                    and digest(view["view"]) == view["view_sha256"], "A pre-reset routing view does not match its hash")
            require(hashlib.sha256(safe_path(public["game_file"]).read_bytes()).hexdigest() == game["game_sha256"],
                    "A viewed game file is not the supply's")
            public.update(routing_view=view["view"], routing_view_sha256=view["view_sha256"])
            bound["views_runtime_sha256"] = pinned
        items.append({"benchmark": "alfworld", "task_id": game["task_id"], "family_id": game["task_id"],
                      "part": FRESH_PART, "room": game["room"], "task_type": game["task_type"], "public": public,
                      "private": {"game_metadata": {"source_split": "train", "task_type": game["task_type"],
                                                    "asset_files": []}, "game_sha256": game["game_sha256"]},
                      **bound})
    counts = {"pool": len(items), "parts": {FRESH_PART: len(items)}, "items": len(items),
              "written_parts": {FRESH_PART: len(items)}, "rooms": len({i["room"] for i in items}),
              "viewed": len(views), "supply_sha256": supply_value[RECORD_HASH],
              "views_sha256": views_value[RECORD_HASH], "views_runtime_sha256": pinned}
    return items, counts
