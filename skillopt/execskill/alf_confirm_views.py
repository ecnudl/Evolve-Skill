"""Write-once, zero-model-call reset views for v2.9's forty spare-room games.

Historical preparation files and pool exports are inputs only. The new record
is pinned by value in S0 and the v2.9 manifest, then attached to confirm items.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import confirm, profiles as p, supply

KIND = "alfworld-confirm-views-v2-9"


def _profile(configuration):
    require(p.is_v29(configuration) and p.is_alfworld(configuration),
            "Confirm pre-reset views belong only to v2.9 ALFWorld")


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")


def preparation_sources(imported, items):
    """Verify the supply/views provenance beside the main preparation's pool.

    The original runtime digest is checked before any reset. Only supply/pool
    metadata and the original public views are read; no test panel is opened.
    """
    pin, runtime = imported["pool"], imported["runtime"]["alfworld"]
    exported = p.verified(read_json(safe_path(pin["path"]).parent / supply.POOL_RECORD), supply.POOL_KIND)
    entry = exported["pools"].get("alfworld", {})
    require(all(entry.get(key) == pin[key] for key in ("path", "sha256"))
            and entry.get("items_digest") == digest(items)
            and entry.get("ids_digest") == digest([item["task_id"] for item in items]),
            "The confirm preparation must use the main preparation's intact exported pool")
    source = exported.get("source", {}).get("alfworld", {})
    require(set(source) == {"supply", "supply_sha256", "views", "views_sha256"},
            "The pool export pins the original ALFWorld supply and views")
    fresh = p.verified(read_json(source["supply"]), supply.RECORD_KIND)
    views = p.verified(read_json(source["views"]), supply.VIEWS_KIND)
    require(fresh.get("name") == "alfworld-xs" and fresh.get("bench") == "alfworld"
            and source["supply_sha256"] == fresh[p.RECORD_HASH] == views.get("supply_sha256")
            == entry.get("counts", {}).get("supply_sha256"),
            "The confirm preparation uses the original ALFWorld supply sha256")
    require(source["views_sha256"] == views[p.RECORD_HASH] == entry["counts"].get("views_sha256"),
            "The original ALFWorld views identity is intact")
    require(views.get("runtime_sha256") == entry["counts"].get("views_runtime_sha256") == digest(runtime),
            "Confirm views must use the preparation's views runtime digest")
    root = safe_path(fresh["sources"]["data_root"])
    require(type(runtime.get("alfworld_data")) is str and safe_path(runtime["alfworld_data"]) == root,
            "Confirm games use the preparation's runtime data root")
    games = {row["task_id"]: row for row in fresh["items"]}
    require(len(games) == len(fresh["items"]) == len(items)
            and set(games) == {item["task_id"] for item in items},
            "The preparation pool and original supply have the same games")
    for item in items:
        game = games[item["task_id"]]
        path = safe_path(root / game["gamefile"])
        require(path.is_relative_to(root) and safe_path(item["public"]["game_file"]) == path
                and item.get("room") == game["room"] and item.get("task_type") == game["task_type"]
                and item.get("private", {}).get("game_sha256") == game["game_sha256"],
                "The preparation's game mapping differs from its original supply")
    cut = supply.slices("alfworld", supply.order("alfworld", fresh["items"]),
                        supply.registered_sizes("alfworld"))
    require(views.get("slices") == {name: [row["task_id"] for row in part] for name, part in sorted(cut.items())}
            and set(views.get("views", {})) == {row["task_id"] for part in cut.values() for row in part},
            "The original views cover exactly the registered preparation slices")
    by_id = {item["task_id"]: item for item in items}
    for key, viewed in views["views"].items():
        _view(viewed)
        item = by_id[key]
        require(item.get("views_runtime_sha256") == digest(runtime)
                and item["public"].get("routing_view") == viewed["view"]
                and item["public"].get("routing_view_sha256") == viewed["view_sha256"],
                "The preparation pool's original routing views are intact")
    return fresh, {"supply_sha256": fresh[p.RECORD_HASH], "original_views_sha256": views[p.RECORD_HASH],
                   "views_runtime_sha256": views["runtime_sha256"], "pool_export_sha256": exported[p.RECORD_HASH]}


def _view(value):
    require(isinstance(value, dict) and set(value) == {"view", "view_sha256"},
            "Each confirm routing view carries its sha256")
    view = value["view"]
    require(isinstance(view, dict) and set(view) == set(p.ALFWORLD_ROUTING_VIEW)
            and isinstance(view["initial_observation"], str) and isinstance(view["task_text"], str)
            and isinstance(view["admissible_commands_at_reset"], list)
            and all(isinstance(command, str) for command in view["admissible_commands_at_reset"])
            and digest(view) == value["view_sha256"], "A confirm routing view differs from its hash or schema")


def validate(value, *, configuration, runtime, confirm_pin, preparation=None, pool=None, source=None):
    """Validate a by-value sealed record, including exactly the forty expected IDs."""
    _profile(configuration)
    require(isinstance(value, dict), "v2.9 ALFWorld requires sealed confirm views before S0")
    value = p.verified(value, KIND)
    require(value.get("configuration") == configuration and value.get("runtime_sha256") == digest(runtime),
            "Confirm views must use the configured preparation runtime digest")
    ids = value.get("ids")
    require(isinstance(ids, list) and len(ids) == len(set(ids)) == confirm.ITEMS
            and ids == confirm_pin["ids"] and value.get("confirm_ids_sha256") == confirm_pin["ids_sha256"] == digest(ids)
            and value.get("confirm") == confirm_pin, "Confirm views cover exactly the forty pinned confirm ids")
    require(isinstance(value.get("views"), dict) and set(value["views"]) == set(ids),
            "Confirm views cover exactly the forty pinned confirm ids")
    provenance = value.get("source")
    require(isinstance(provenance, dict) and set(provenance) == {
        "supply_sha256", "original_views_sha256", "views_runtime_sha256", "pool_export_sha256"}
        and all(_sha(item) for item in provenance.values())
        and provenance["views_runtime_sha256"] == value["runtime_sha256"],
        "Confirm views pin the original supply sha256 and views runtime digest")
    if preparation is not None:
        require(value.get("preparation") == preparation, "Confirm views belong to another preparation")
    if pool is not None:
        require(value.get("pool") == pool, "Confirm views belong to another preparation pool")
    if source is not None:
        require(provenance == source, "Confirm views differ from the preparation supply sha256 or views pins")
    for row in value["views"].values():
        _view(row)
    return value


def load_for_preparation(path, *, configuration, imported, items):
    require(path is not None, "v2.9 ALFWorld S0 requires --confirm-views")
    _, source = preparation_sources(imported, items)
    return validate(read_json(path), configuration=configuration, runtime=imported["runtime"]["alfworld"],
                    confirm_pin=confirm.identity(configuration, items),
                    preparation=imported["registration"]["preparation"], pool=imported["pool"], source=source)


def prepare(out, *, configuration, preparation_file, data_root):
    """Reset exactly the confirm games once with make-items' production reset."""
    from . import alf_smoke, manifest

    _profile(configuration)
    out = safe_path(out)
    require(not out.exists(), "Confirm routing views are written once to a new file")
    imported = alf_smoke.preparation(preparation_file)
    items = manifest._items(imported["pool"], "alfworld")
    fresh, source = preparation_sources(imported, items)
    runtime = imported["runtime"]["alfworld"]
    root = safe_path(data_root)
    require(root == safe_path(runtime["alfworld_data"]), "--data-root must match the preparation runtime")
    selected, pin = confirm.slice_items(configuration, items)
    games = {row["task_id"]: row for row in fresh["items"]}
    chosen = [games[row["task_id"]] for row in selected]
    for game in chosen:
        require(hashlib.sha256(safe_path(root / game["gamefile"]).read_bytes()).hexdigest() == game["game_sha256"],
                "A confirm game differs from the original supply sha256")
    views = supply.prereset(fresh["items"], {"confirm": chosen}, reset=supply.alfworld_reset(root, runtime))
    value = p.record(KIND, "smoke", {"configuration": configuration,
        "preparation": imported["registration"]["preparation"], "pool": imported["pool"], "source": source,
        "runtime_sha256": digest(runtime), "confirm": pin, "ids": pin["ids"],
        "confirm_ids_sha256": pin["ids_sha256"], "views": views})
    validate(value, configuration=configuration, runtime=runtime, confirm_pin=pin,
             preparation=imported["registration"]["preparation"], pool=imported["pool"], source=source)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, value)
    return value


def attach(items, value, *, configuration, runtime, confirm_pin=None):
    """Attach only sealed confirm views to copies of the selected pool items."""
    require(isinstance(confirm_pin, dict), "The ALFWorld confirm slice identity is pinned")
    value = validate(value, configuration=configuration, runtime=runtime, confirm_pin=confirm_pin)
    require([row["task_id"] for row in items] == value["ids"], "Attach exactly the pinned confirm games")
    rows = deepcopy(items)
    for item in rows:
        viewed = value["views"][item["task_id"]]
        item["public"].update(routing_view=deepcopy(viewed["view"]), routing_view_sha256=viewed["view_sha256"])
        item["views_runtime_sha256"] = value["runtime_sha256"]
    return rows
