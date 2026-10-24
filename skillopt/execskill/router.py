"""Deterministic routing of a procedure package (protocol ``fivebench-execskill-v1``; registration §2.3, §6.1 with its
edit-type table, §6.5, §9.2; implementation plan §1 router.py, §2.2, §3; T-ROUTE-1..5).

``route`` runs the ``applies`` predicate of every procedure of a package that may fire on the bench
(``Package.for_bench``: the procedure's own exclusions and the package's narrowings are respected), in package order and
in the sandbox, on one item's routing view. The routing view is the public view the solver shows: on QA and
SpreadsheetBench ``solver.routing_view``; on ALFWorld the registered pre-reset view {initial_observation,
admissible_commands_at_reset, task_text} of the items file (``supply.routing_view``), never a game path or an id. A
predicate that faults, or that returns anything but a bool, leaves its procedure disabled on the item (P2,
``predicate_fault``): counted toward J3, never a pause. A withheld procedure (a withholding twin, §6.5) still runs its
predicate, logged ``shadow_fired``, and is never enabled; a restored one (a restoration twin, §6.1) is marked. The log
is a sealed record ``fivebench-execskill-v1-route`` (its hash is the enable log's ``route_sha256``).

``plan`` is one acceptance round's firing plan, made with zero model calls before dispatch (§6.1, §6.5, §9.2; Codex F1,
F6, F18): the candidate S' and its parent S routed on every item of the acceptance slice; A* per edit -- new: the new
procedure fires in S'; revision: the old version fires in S or the new one in S'; deletion and narrowing: the procedure
fired in S -- and their union; the twin draws (a seeded half of each eligible procedure's firing items, at most
``MAX_TWINS_PER_ITEM`` per item, changed procedures first, then inherited ones by enable count; an inherited
procedure's eligibility and draw count its firing items in the whole acceptance slice A, §6.5, and the A items outside
A* that get a twin are listed in ``twin_only``, Codex review 2026-10-22 #12); the yoke pairs (one
run-slice donor per A* item, §6.1); and the minimum-size rule (|A*| >= 30, ALFWorld >= 20 rooms, else
``not_run_small_astar``; v2.2: a sealed practical rule's ``minimum``, ``acceptance.minimum_astar``).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from skillopt.coevo5.data import ranked
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from .package import Package, edits
from .protocol import (BENCHES, INHERITED_TWIN_MIN_FIRED, MAX_TWINS_PER_ITEM, MIN_ASTAR, MIN_ASTAR_ROOMS, RECORD_HASH,
                       SANDBOX_TIMEOUTS, SEED, TWIN_MIN_FIRED, record, withhold_tag, yoke_tag)

PREDICATE = "applies"
NOT_BOOL = "not_bool"  # a predicate value other than True or False
TWIN_KIND = {"new": "withhold", "revision": "withhold", "deletion": "restore", "narrowing": "restore"}  # §6.1 table
RUN, SMALL = "run", "not_run_small_astar"


@dataclass(frozen=True)
class RouteLog:
    """One item's routing: per procedure {applies, enabled, withheld, restored, shadow_fired, fault}, in package order,
    and the fault details ({procedure, hook, kind, exc_type, message})."""
    bench: str
    package_sha256: str
    routing_view_sha256: str
    per_procedure: dict
    faults: tuple
    evidence: str

    @property
    def enabled(self):
        return tuple(pid for pid, entry in self.per_procedure.items() if entry["enabled"])

    @property
    def fired(self):
        """The procedures whose predicate returned True, withheld ones included."""
        return tuple(pid for pid, entry in self.per_procedure.items() if entry["applies"] is True)

    def to_json(self):
        return record("route", self.evidence, {
            "bench": self.bench, "package_sha256": self.package_sha256,
            "routing_view_sha256": self.routing_view_sha256, "order": list(self.per_procedure),
            "per_procedure": {pid: dict(entry) for pid, entry in self.per_procedure.items()},
            "enabled": list(self.enabled), "faults": [dict(f) for f in self.faults]})

    @property
    def sha256(self):
        return self.to_json()[RECORD_HASH]


def predicate_fault(procedure_id, result):
    """The fault of one ``applies`` call, None when it returned a bool."""
    if result.get("ok") is True and type(result.get("value")) is bool:
        return None
    if result.get("ok") is True:
        return {"procedure": procedure_id, "hook": PREDICATE, "kind": NOT_BOOL, "exc_type": None,
                "message": type(result.get("value")).__name__}
    return {"procedure": procedure_id, "hook": PREDICATE, "kind": result.get("fault"),
            "exc_type": result.get("exc_type"), "message": result.get("message")}


def route(package, bench, routing_view, worker, *, withhold=frozenset(), restore=frozenset()):
    """The ``RouteLog`` of ``package`` on one item. ``worker``: a started sandbox worker holding the package (None only
    when no procedure may fire on the bench); ``withhold`` / ``restore``: procedure ids of the package."""
    require(isinstance(package, Package) and bench in BENCHES, "Route a package on a known bench")
    withhold, restore = frozenset(withhold), frozenset(restore)
    require(withhold <= set(package.order) and restore <= set(package.order) and not withhold & restore,
            "Withheld and restored procedures are distinct procedures of the package")
    procedures = package.for_bench(bench)
    require(not procedures or worker is not None, "A package with procedures for the bench routes in the sandbox")
    per, faults = {}, []
    for procedure in procedures:
        result = worker.call(procedure.id, PREDICATE, [routing_view], timeout_s=SANDBOX_TIMEOUTS["predicate"])
        fault = predicate_fault(procedure.id, result)
        applies = None if fault else result["value"]
        withheld = procedure.id in withhold
        per[procedure.id] = {"applies": applies, "enabled": applies is True and not withheld, "withheld": withheld,
                             "restored": procedure.id in restore, "shadow_fired": withheld and applies is True,
                             "fault": fault["kind"] if fault else None}
        if fault:
            faults.append(fault)
    return RouteLog(bench, package.sha256, digest(routing_view), per, tuple(faults), package.evidence)


def seeded_half(items, unit, procedure_id):
    """A seeded half (rounded down) of ``items``: the first of their ``withhold_tag(unit, procedure)`` order (§6.5)."""
    order = ranked([{"task_id": item} for item in items], SEED, withhold_tag(unit, procedure_id))
    return [entry["task_id"] for entry in order[:len(items) // 2]]


def draw_twins(firing, priority, kinds, unit):
    """``(twins, not_withheld)``: for each procedure in ``priority`` order a seeded half of its firing items
    (``firing[p]``) gets a twin of kind ``kinds[p]`` ("withhold" or "restore"), at most ``MAX_TWINS_PER_ITEM`` per item;
    an item already at the cap records the procedure in ``not_withheld`` (§6.5, Codex F18)."""
    twins, skipped = {}, {}
    for procedure_id in priority:
        for item in seeded_half(firing[procedure_id], unit, procedure_id):
            held = twins.setdefault(item, [])
            if len(held) < MAX_TWINS_PER_ITEM:
                held.append({"procedure": procedure_id, "kind": kinds[procedure_id]})
            else:
                skipped.setdefault(item, []).append(procedure_id)
    return twins, skipped


def yoke(items, donors, unit):
    """One donor per item (§6.1): items and donors each in their ``yoke_tag(unit)`` order, the k-th item paired with
    donor k modulo the number of donors (reuse counted)."""
    items, donors = list(items), list(donors)
    require(len(set(items)) == len(items) and len(set(donors)) == len(donors), "Items and donors are distinct")
    if not items:
        return {"pairs": {}, "reuse": {}}
    require(donors, "Paired placebos need donors")
    tag = yoke_tag(unit)
    donor_order = [v["task_id"] for v in ranked([{"task_id": x} for x in donors], SEED, tag)]
    item_order = [v["task_id"] for v in ranked([{"task_id": x} for x in items], SEED, tag)]
    pairs = {item: donor_order[k % len(donor_order)] for k, item in enumerate(item_order)}
    return {"pairs": {item: pairs[item] for item in items}, "reuse": dict(sorted(Counter(pairs.values()).items()))}


def plan(candidate, parent, bench, views, workers, *, unit, rooms=None, donors=(), minimum=None):
    """The firing plan of one acceptance round (a sealed ``fivebench-execskill-v1-firing-plan`` record). ``views``:
    {item: routing view} of the acceptance slice in slice order, made from public data only; ``workers(package, item)``:
    a context manager yielding a started sandbox worker holding ``package`` for ``item`` (SpreadsheetBench mounts the
    item's workbook); ``rooms``: {item: room}, required on ALFWorld; ``donors``: the run-slice donor ids;
    ``minimum``: v2.2's {"items", "rooms"} floor of |A*| (``acceptance.minimum_astar``, recorded in the plan), None for
    the registered ``MIN_ASTAR`` / ``MIN_ASTAR_ROOMS``."""
    require(isinstance(candidate, Package) and isinstance(parent, Package) and bench in BENCHES,
            "A candidate, its parent and a known bench")
    require(candidate.parent_sha256 == parent.sha256, "The candidate's parent hash is not its parent's")
    require(isinstance(views, dict) and views, "Routing views of the acceptance items")
    require(bench != "alfworld" or (isinstance(rooms, dict) and set(views) <= set(rooms)),
            "An ALFWorld plan needs every game's room")
    changes = edits(parent, candidate)
    items = list(views)
    routed = {}
    for item in items:
        sides = {}
        for side, package in (("candidate", candidate), ("parent", parent)):
            with workers(package, item) as worker:
                sides[side] = route(package, bench, views[item], worker)
        routed[item] = sides
    fired_new = {item: set(routed[item]["candidate"].enabled) for item in items}
    fired_old = {item: set(routed[item]["parent"].enabled) for item in items}
    by_edit, firing, kinds, changed = {}, {}, {}, []
    for change in changes:
        if change.kind == "new":
            members = [i for i in items if change.new.id in fired_new[i]]
        elif change.kind == "revision":
            members = [i for i in items if change.old.id in fired_old[i] or change.new.id in fired_new[i]]
        else:
            members = [i for i in items if change.old.id in fired_old[i]]
        by_edit[change.id] = {"kind": change.kind, "items": members}
        twin_id = change.new.id if change.kind in ("new", "revision") else change.old.id
        twin_fired = ([i for i in items if twin_id in fired_new[i]] if change.kind in ("new", "revision")
                      else members)
        changed.append(twin_id)
        firing[twin_id], kinds[twin_id] = twin_fired, TWIN_KIND[change.kind]
    astar = [i for i in items if any(i in entry["items"] for entry in by_edit.values())]
    in_astar = set(astar)
    shortcut = len(changes) == 1 and changes[0].kind == "new"  # §6.1, §6.5: S' - S is then the twin's estimand
    priority = [p for p in changed if not shortcut and len([i for i in firing[p] if i in in_astar]) >= TWIN_MIN_FIRED]
    touched = {c.id for c in changes} | set(changed)
    inherited = [p.id for p in candidate.for_bench(bench) if p.id in parent.order and p.id not in touched
                 and p.origin != bench]
    for procedure_id in inherited:
        firing[procedure_id] = [i for i in items if procedure_id in fired_new[i]]
        kinds[procedure_id] = "withhold"
    # §6.5 "继承来的过程...在本 bench 验收段启用 >= 15 道时": an inherited procedure is eligible on its firing items in the
    # acceptance slice A, not only those in A*, and its seeded half is drawn from them (Codex review 2026-10-22 #12).
    # An A item outside A* that gets a twin (``twin_only``) runs S' beside its twin cells, the "with p" side of tau_p
    # (``acceptance.schedule``). A changed procedure fires on A* items only (A* is the union of its firing items).
    counts = {p: len(firing[p]) for p in inherited}
    priority += sorted((p for p in inherited if counts[p] >= INHERITED_TWIN_MIN_FIRED),
                       key=lambda p: (-counts[p], candidate.order.index(p)))
    twins, skipped = draw_twins({p: firing[p] if p in counts else [i for i in firing[p] if i in in_astar]
                                 for p in priority}, priority, kinds, unit)
    twin_only = [i for i in items if i in twins and i not in in_astar]
    fault_ids = set(changed) | {c.id for c in changes}
    fault_items = [i for i in items if any(f["procedure"] in fault_ids for side in ("candidate", "parent")
                                           for f in routed[i][side].faults)]
    astar_rooms = len({rooms[i] for i in astar}) if bench == "alfworld" else None
    least, least_rooms = (MIN_ASTAR, MIN_ASTAR_ROOMS) if minimum is None else (minimum["items"], minimum["rooms"])
    small = len(astar) < least or (astar_rooms is not None and astar_rooms < least_rooms)
    fields = {
        "bench": bench, "unit": unit, "candidate_sha256": candidate.sha256, "parent_sha256": parent.sha256,
        "items": items, "edits": [c.to_json() for c in changes],
        "routes": {i: {side: {"enabled": list(routed[i][side].enabled), "fired": list(routed[i][side].fired),
                              "faults": [dict(f) for f in routed[i][side].faults],
                              "route_sha256": routed[i][side].sha256} for side in ("candidate", "parent")}
                   for i in items},
        "astar_by_edit": by_edit, "astar": astar, "astar_rooms": astar_rooms, "fault_items": fault_items,
        "twin_priority": priority, "twin_kinds": {p: kinds[p] for p in priority},
        "twins": {i: twins[i] for i in items if i in twins},
        "not_withheld": {i: skipped[i] for i in items if i in skipped}, "twin_only": twin_only,
        "donors": yoke(astar, donors, unit) if not small else {"pairs": {}, "reuse": {}},
        "decision": SMALL if small else RUN}
    if minimum is not None:  # v2.2: the practical rule's floor, sealed with the plan
        fields["minimum"] = dict(minimum)
    return record("firing-plan", candidate.evidence, fields)
