"""v2.9 held-out practice confirmation. No source or sealed-panel file is opened here.

The slice builder receives the already pinned practice pool. Public/count-only
boundaries are explicit so confirm examples never enter the engineer's context.
"""
from __future__ import annotations

import math

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import profiles, supply, zebralogic

ITEMS = 40
FRESHNESS = {
    "zebra-pc-v7": "zebra_split_v1_confirm_spare_probe_smoke_first_use",
    "alfworld-v4": "alfworld_split_v1_confirm_spare_rooms_first_use",
    "zebra-pc-v8": "zebra_split_v1_confirm_spare_probe_smoke_first_use",
    "alfworld-v5": "alfworld_split_v1_confirm_spare_rooms_reused_after_alfworld_v4",
    "zebra-pc-v9": "zebra_split_v1_confirm_after_zebra_pc_v8",
    "alfworld-v6": "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v5",
    "zebra-pc-v10": "zebra_split_v1_confirm_after_zebra_pc_v9",
    "alfworld-v7": "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v5_v6_not_launched",
    "zebra-pc-v11": "zebra_split_v1_confirm_after_zebra_pc_v9_v10_not_launched",
    "alfworld-v8": "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7",
    "zebra-pc-v12": "zebra_split_v1_confirm_after_zebra_pc_v9_v11",
    "alfworld-v9": "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7_v8_not_launched",
    "alfworld-v10": "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v7_v9_stopped",
    "alfworld-v11": "alfworld_split_v1_confirm_spare_rooms_after_alfworld_v10",
}
COUNT_FIELDS = ("items", "evaluated", "fixed", "broken", "net", "format_cells", "format_margin",
                "candidate_cells", "passed", "reason", "reused_cells", "tokens", "exercise")


def slice_items(configuration, pool, *, excluded=()):
    """Exactly 40 distinct practice items, with deterministic IDs and provenance.

    ALFWorld uses whole capped room queues in the registered seeded room order.
    If their sizes do not sum to 40 greedily, the first deterministic exact subset
    is used; a room is never partially cut just to hit 40. Insufficient material
    fails preparation, rather than silently changing the registered denominator.
    """
    require(configuration in FRESHNESS, "Confirmation belongs only to v2.9")
    by_id = {item["task_id"]: item for item in pool}
    require(len(by_id) == len(pool), "Duplicate confirmation pool item")
    require(not any(item.get("partition") in ("test", "sealed") for item in pool),
            "Confirmation uses practice pool items only")
    if profiles.is_zebra(configuration):
        split = zebralogic.slices(pool)
        require(len(split["spare"]) == 3 and len(split["smoke"]) == 10,
                "Zebra confirmation needs the registered 3 spare and 10 smoke items")
        require(set(zebralogic.EXCLUDED_IDS) <= set(by_id), "Missing registered confirmation probe item")
        rows = [(item, "spare") for item in split["spare"]]
        rows += [(by_id[key], "excluded_probe") for key in zebralogic.EXCLUDED_IDS]
        rows += [(item, "smoke") for item in split["smoke"]]
        require(all(item.get("task") in zebralogic.DOMAIN for item, _ in rows),
                "Confirmation stays in the registered 5-6-house domain")
        blocked = {item["task_id"] for name in ("run", "accept") for item in split[name]}
        provenance = {"parts": {name: [item["task_id"] for item, part in rows if part == name]
                                for name in ("spare", "excluded_probe", "smoke")},
                      "probe_ids_sha256": zebralogic.EXCLUDED_IDS_SHA256,
                      "seed": zebralogic.SLICE_SEED}
        selected = [item for item, _ in rows]
    else:
        ordered = supply.order("alfworld", pool)
        rooms = supply.room_order(ordered)
        groups = supply.room_groups(rooms)
        queues = [(room, [item for item in ordered if item["room"] == room][:profiles.MAX_GAMES_PER_ROOM])
                  for room in groups["spare"]]
        sums = {0: ()}
        for index, (_, queue) in enumerate(queues):
            for total, indices in list(sums.items()):
                new = total + len(queue)
                if queue and new <= ITEMS and new not in sums:
                    sums[new] = indices + (index,)
        require(ITEMS in sums, "ALFWorld spare rooms cannot supply exactly 40 whole capped-room games")
        chosen = [queues[index] for index in sums[ITEMS]]
        selected = [item for _, queue in chosen for item in queue]
        blocked_rooms = {room for name in ("smoke", "run", "accept", "select") for room in groups[name]}
        blocked = {item["task_id"] for item in pool if item["room"] in blocked_rooms}
        provenance = {"group": "spare", "seed": profiles.SEED,
                      "room_order": [room for room, _ in chosen],
                      "room_games": {room: [item["task_id"] for item in queue] for room, queue in chosen},
                      "max_games_per_room": profiles.MAX_GAMES_PER_ROOM}
    ids = [item["task_id"] for item in selected]
    require(len(ids) == len(set(ids)) == ITEMS, "Confirmation has exactly 40 distinct items")
    require(not set(ids) & (blocked | set(excluded)), "Confirmation overlaps a protected practice/sealed slice")
    return selected, {"configuration": configuration, "freshness": FRESHNESS[configuration],
                      "items": ITEMS, "ids": ids, "ids_sha256": digest(ids), "provenance": provenance}


def identity(configuration, pool):
    return slice_items(configuration, pool)[1]


def verdict(cells, evaluated, *, identical=(), items=ITEMS):
    """One run per differently routed item; exact-request skips contribute zero.

    ``cells`` maps (arm, item) to a one-element cell list, as training does.
    Identical-request pairs remain in the format denominator, never a fix/break.
    """
    evaluated, skipped = list(evaluated), set(identical)
    require(len(evaluated) == len(set(evaluated)) and skipped <= set(evaluated),
            "Confirmation evaluated items and identical requests are distinct")
    require(not any(key in skipped for _, key in cells), "An identical confirm pair is undispatched")
    def token(arm, key):
        found = cells[(arm, key)]
        require(len(found) == 1, "Confirmation runs each item once per arm")
        cell = found[0]
        return ((cell.get("judge") or {}).get("v2") or {}).get("token", (cell.get("final") or {}).get("token"))
    fixed = sum(token("S'", key) == "pass" and token("S", key) != "pass"
                for key in evaluated if key not in skipped)
    broken = sum(token("S'", key) != "pass" and token("S", key) == "pass"
                 for key in evaluated if key not in skipped)
    formats = {arm: sum(bool(((cell.get("judge") or {}).get("format") or {}).get("violation"))
                        for (side, _), found in cells.items() if side == arm for cell in found)
               for arm in ("S'", "S")}
    margin = max(profiles.TRAIN_FORMAT_MARGIN[0],
                 math.ceil(profiles.TRAIN_FORMAT_MARGIN[1] * len(evaluated)))
    reason = ("no_item_routes_differently" if not evaluated else
              "guard:format" if formats["S'"] - formats["S"] > margin else
              "gain:fixed_over_broken" if fixed <= broken else None)
    return {"items": items, "evaluated": len(evaluated), "fixed": fixed, "broken": broken,
            "net": fixed - broken, "format_cells": formats, "format_margin": margin,
            "candidate_cells": len(evaluated), "passed": reason is None, "reason": reason}


def counts_only(value):
    """The only confirmation information allowed in an engineer context."""
    return {key: value[key] for key in COUNT_FIELDS if key in value}


def tokens(cells):
    """Actual new transport usage, never reused-cell usage, without responses."""
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    total = {key: 0 for key in fields}
    for cell in cells:
        for send in cell.get("sends") or ():
            usage = (send.get("receipt") or {}).get("usage") or {}
            for key in fields:
                if type(usage.get(key)) is int:
                    total[key] += usage[key]
    return total
