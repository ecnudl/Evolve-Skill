"""Zero-call paired-request identity (route B v2.3, owner request 2026-10-25 T1/T2).

The shell itself routes and renders the first request. A fault forbids reuse even if its dropped note leaves the
request unchanged. SpreadsheetBench additionally keeps the ordered versions and sham content of its post-call
hooks; QA keeps the calculator inputs, since the same invitation must not hide a different second call. ALFWorld
is never interchangeable: its hooks depend on observations. Amendment 1 partitions all scheduled arms per item:
representatives are S, S', C, P_y, P_i, then twins in sealed order; a single fault-free class has no cells and exact
zero differences. C's independent sample first draws from items already dispatching S, supplementing with new S
dispatches only when needed; S_dup is always independent. These instruments override the no-dispatch rule, so
``identical_all`` lists only the effective zero-cell items. Plans contain the classes, identities, same-item
references and instrument sample before dispatch; no model function is called here.
"""
from __future__ import annotations

import hashlib
import json

from skillopt.coevo5.calls import _request_hash
from skillopt.continual_eval.core import require

from . import solver
from .protocol import NOTES_KEY, SEED, round_tag

VERSION = "identical-request-classes-v2-3"
BENCHES = ("searchqa", "officeqa", "livemath", "spreadsheetbench")


def signature(bench, package, view, worker, *, card_text="", runtime=None, withhold=(), restore=(), placebo=None):
    """The exact first request hash, post-call identity and faults using an already started item worker."""
    require(bench in BENCHES, "ALFWorld has no zero-call request identity")

    def no_call(*args, **kwargs):
        raise AssertionError("Request identity never calls a model")

    shell = solver._Shell(bench, package, no_call, worker, withhold=withhold, restore=restore, placebo=placebo,
                          text=None, native=None, nominal=None)
    shell.started = worker is not None
    shell.route_on(view)
    text, names = shell.before(view, solver._public_text(view))
    request = dict(view)
    if text:
        request[NOTES_KEY] = text
    post = []
    if bench == "spreadsheetbench":
        for procedure in shell.enabled(("sheet_feedback",)):
            post.append({"hook": "sheet_feedback", "procedure": procedure.id, "version": procedure.sha256,
                         "sham": shell.sham(procedure.id, "sheet_feedback") if procedure.id in shell.shams else None})
    elif names is not None:
        post.append({"hook": "second", "bindings": names,
                     "sham": any(p.id in shell.shams for p in shell.enabled(("bindings",)))})
    return {"request_sha256": _request_hash(solver._system(bench, card_text, runtime or {}),
                                            json.dumps(request, ensure_ascii=False)),
            "post_call": post, "faults": [dict(f) for f in shell.faults], "enabled": list(shell.route.enabled)}


def interchangeable(first, second, *, bench):
    """Only complete, fault-free identities on a supported bench can share the same item's runs."""
    return bool(bench in BENCHES and first and second and first.get("faults") == [] and second.get("faults") == []
                and first.get("request_sha256") and first.get("request_sha256") == second.get("request_sha256")
                and isinstance(first.get("post_call"), list) and isinstance(second.get("post_call"), list)
                and first["post_call"] == second["post_call"])


def card_sample(sealed, preferred=None):
    """The seeded C instrument sample, taking already-dispatched S items before supplemental S dispatches."""
    if sealed["bench"] not in BENCHES or not sealed["card_is_parent"]:
        return None
    if preferred is None and sealed.get("reuse") is not None:
        return dict(sealed["reuse"]["card_sample"])
    tag = round_tag(sealed["unit"]) + ":reuse-card"
    seed = sealed.get("seeds", {}).get("request_reuse", SEED)
    order = sorted(sealed["plan"]["astar"], key=lambda item: hashlib.sha256(
        json.dumps([seed, tag, item]).encode()).hexdigest())
    preferred = set(preferred or [])
    first = [item for item in order if item in preferred][:30]
    extra = [item for item in order if item not in preferred][:min(len(order), 30) - len(first)]
    return {"items": first + extra, "runs": sealed["runs"], "seed": seed, "tag": tag,
            "preferred_items": first, "supplemental_items": extra}


def _item_arms(sealed, signatures):
    """Every scheduled arm, including ones whose replay identity is missing, in the representative priority order."""
    items = {name: {item: list(arms) for item, arms in entries.items()} for name, entries in signatures.items()}
    main = ["S", "S'", "C", "P_y"] + (["P_i"] if sealed["placebo_i"] is not None else [])
    main += ["S_dup"] if sealed["dup"] else []
    for item in sealed["plan"]["astar"] + sealed["plan"].get("twin_only", []):
        twins = [t["kind"] + ":" + t["procedure"] for t in sealed["plan"]["twins"].get(item, [])]
        items.setdefault("real", {})[item] = (main if item in sealed["plan"]["astar"] else ["S'"]) + twins
    for generated in sealed["g_acc"] or []:
        items.setdefault("G_acc", {})[generated["id"]] = ["S", "S'", "C", "P_y"] + (["S_dup"] if sealed["dup"] else [])
    for item in sealed["probe"]:
        items.setdefault("probe", {})[item] = ["S'", "C"]
    priority = {arm: n for n, arm in enumerate(("S", "S'", "C", "P_y", "P_i"))}
    priority["S_dup"] = 6  # independent, after the shareable arms' registered representative order
    return {name: {item: sorted(arms, key=lambda arm: priority.get(arm, 5)) for item, arms in entries.items()}
            for name, entries in items.items()}


def _partition(arms, identities, bench, *, independent=()):
    """Faulting/missing identities and instrument arms are singleton classes; the first member represents a class."""
    groups = []
    for arm in arms:
        group = next((group for group in groups if arm not in independent and group["representative"] not in independent
                      and interchangeable(identities.get(arm), identities.get(group["representative"]), bench=bench)), None)
        if group is None:
            groups.append({"representative": arm, "arms": [arm]})
        else:
            group["arms"].append(arm)
    return groups


def from_signatures(sealed, signatures):
    """Amendment 1: all-arm classes, no-dispatch identical items, and independent C/S_dup instruments, sealed once."""
    classes, reused, identical = {}, {}, {}
    item_arms = _item_arms(sealed, signatures)
    for cell_set, items in item_arms.items():
        for item, arms in items.items():
            identities = signatures.get(cell_set, {}).get(item, {})
            classes.setdefault(cell_set, {})[item] = _partition(arms, identities, sealed["bench"], independent=("S_dup",))
    preferred = [item for item, groups in classes.get("real", {}).items()
                 if len(groups) > 1 and any(group["representative"] == "S" for group in groups)]
    sample = card_sample(sealed, preferred)
    for cell_set, items in item_arms.items():
        for item, arms in items.items():
            identities = signatures.get(cell_set, {}).get(item, {})
            if sample is not None and cell_set == "real" and item in sample["items"]:
                classes[cell_set][item] = _partition(arms, identities, sealed["bench"], independent=("C", "S_dup"))
            groups = classes[cell_set][item]
            if (len(groups) == 1 and len(arms) > 1
                    and interchangeable(identities.get(arms[0]), identities.get(arms[0]), bench=sealed["bench"])):
                identical.setdefault(cell_set, []).append(item)
                continue
            for group in groups:
                for arm in group["arms"][1:]:
                    reused.setdefault(cell_set, {}).setdefault(item, {})[arm] = group["representative"]
    return {"version": VERSION, "signatures": signatures, "classes": classes, "reused": reused,
            "identical_all": identical, "card_sample": sample}


def reference(plan, job):
    """The same-set/item/run source arm of a logical job, None when it dispatches independently."""
    return plan["reused"].get(job["set"], {}).get(job["item"], {}).get(job["arm"])


def skipped(plan, job):
    """An identical_all item has neither physical nor logical cells; its differences remain exact zero."""
    return job["item"] in plan["identical_all"].get(job["set"], [])
