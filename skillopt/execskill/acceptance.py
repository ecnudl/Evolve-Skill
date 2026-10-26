"""One acceptance round: sealing, the dispatch schedule and the one decision (protocol ``fivebench-execskill-v1``;
registration §6.1-§6.5, §3.3 (A*, minimum size, G_acc), §3.4 (sealing, consumption), §5.6; Codex F1, F2, F4, F5, F6,
F18, F22 in §20; implementation plan §1 acceptance.py, §2.6, T-ACC-1..8).

``prepare`` seals everything before the first cell (§3.4): the donor corpus (``donors``), the firing plan (A* per edit
type, twins, yoke pairs, the minimum-size rule; ``router.plan``), the P_y and P_i content (``placebo``), the examiner's
G_acc (one generated item per A* item, generated on the A* public views) and the duplicate arm; the hashes of all of
them are the record's ``seals``. With |A*| < 30 (ALFWorld: or < 20 rooms) nothing runs and nothing is consumed: the
decision is ``not_run_small_astar``, S' is archived, S passes on and ``dispatch`` releases every slice item as
``routed_not_dispatched`` (Codex F1, O9). ``schedule`` lists the round's cells (arms x A* items x runs, twins, G_acc,
the J7 probe, and S' with its twins on the A items outside A* where an inherited procedure's twin was drawn, §6.5,
``twin_only``; Codex review 2026-10-22 #12); ``cell_arm`` gives one cell's package, twin and placebo arguments for
``solver.solve``.

``decide`` is a pure function of the cell records and the sealed record, so the decision is reproducible from the cell
records alone. Item scores (§6.3): per item the mean of its runs' v2 tokens, the candidate arms (S' and its twins) on L
(unknown and ``unknown_fault`` wrong), every other arm on H; items no arm got any reply on (``shared_unanswered``) leave
every contrast. S' is accepted iff J1-J7 all hold (§6.4):

- J1: the one-sided paired t-test (``stats_ext.paired_t``: block-stratified; ALFWorld on room means weighted by games)
  of S' - S on A* has p <= 0.05, and its whole-batch mean (= sum of the A* differences / |A|) is >= 0.02;
- J2: the same test of S' - P_y has p <= 0.05; when the donor-clustered 95 % interval of P_y - S lies below 0 (harmful
  sham) J2 is not informative and J1 is judged at 2.5 %, the report reading "superiority over the parent;
  content/effort explanation not excluded" (Codex F5);
- J3: fault items / |A| <= 2 % (Codex F22): an item of A with >= 1 fault of a changed procedure in S' or P_y, any run,
  routing (the sealed plan, every item of A) or execution, or a re-execution ``unknown_fault``;
- J4: S' format-violating items <= S's + max(2, ceil(0.02 |A*|)), an item violating when any of its runs does;
- J5: per arm infrastructure unknown <= 10 % and reasoning mismatch after resends <= 1 %, shared unanswered <= 10 % of
  A*, the start-time balance of §6.2 -- re-derived for the one uniform seeded order (statistics review 8): the arms'
  median start delays against their places in that order within 5 % of the round's duration, the registered spread
  of their median start times recorded beside it (``_balance``) -- and on OfficeQA the registered gap between its two
  time blocks (``BLOCK_GAP_SECONDS``, §3.3: ``dispatch`` waits for it, ``decide`` checks the recorded block windows;
  statistics review 3);
- J6: EVERY registered same-text duplicate pair (S and C while S has no procedure on the bench; S and S_dup) has a
  two-sided paired t p >= 0.01 (statistics review 2);
- a J5 or J6 miss leaves the round ``undetermined``: the run pauses without a decision (§13 table) -- ``settle``
  raises ``cells.Pause`` and marks nothing decided, so the round's items stay "dispatched", the registry's form of
  "consumed but undecided" (statistics review 4);
- J7 (LiveMath, formal chain): the options-only probe's S' - C is < 10 points or its one-sided p >= 0.05, else the
  shortcut rejects.

v2.2 (``protocol.ACCEPT_RULES``, owner decision 2026-10-24 12:1x): a round prepared with a practical ``rule`` seals it
(``sealed["rule"]``) and its |A*| floor (``minimum_astar``, the plan's ``minimum``); ``decide`` then replaces J1 and J2
(``_practical``): J1 holds when the whole-batch S' - S is at least the rule's points (5), or on a significance bench
(SearchQA) at least its smaller points (2) with the one-sided p <= its alpha; J2 records S' - P_y with the label
"content" (at least the rule's content points) or "form" and never decides. J3-J7 and every recorded contrast stay as
above; a round sealed without a rule is decided exactly as before. Two changes follow the smaller floor (Codex review
2026-10-24): a round whose answered A* items leave the t-test no degree of freedom (no more units -- rooms on
ALFWorld, else items -- than the blocks they fall in; ``_too_few_units``) is ``undetermined`` (paused, consumed but
undecided) instead of raising, and a harmful yoked sham is labelled ``harmful_sham_reported``, J1 no longer tightening
its alpha.

v2.3 (owner request 2026-10-25 T1 and Amendment 1): only rounds carrying ``reuse`` use the sealed exact-request
classes from ``reuse.signature`` / ``from_signatures``. One representative per class runs; a fault-free single class
(``identical_all``) has no physical or logical cells. Its differences are exact zeros in the original A* design and
|A| denominator, and it remains answered. Each arm keeps its registered H/L score across different classes; only
same-item/run contributions sharing one origin are exactly zero (Codex review finding 2, 2026-10-25). When C
is the parent, its independent min(|A*|, 30) sample prefers already-dispatched S items, supplementing with additional
S dispatches when necessary; J6 and the C contrasts name that sample (whole-batch projection None). S_dup is always
independent. These instruments override identical_all. ``shared_unanswered`` considers physical cells only.

J3 includes sealed zero-call faults and the logical source outcomes, over |A|. J4 counts S'/S violations only on
their noninterchangeable items, retaining format_margin(|A*|). J5 infrastructure shares use dispatched real A*
cells by representative (including a twin representative); reasoning mismatch uses dispatched real cells. Balance
and block gaps use the entire physical schedule, including G_acc/probe-only dispatch; an arm with no dispatch has
no timing median, and an entirely empty schedule passes these checks. ALFWorld keeps its full schedule. Without
``reuse`` every recorded field and decision is historical. Virtual cells and ``reused_from`` links reconstruct from
physical records and the sealed plan; decisions store the links, effective zero-cell counts and physical counts by
arm. Provenance hashes physical evidence only. Removing independent re-sends of equal requests reduces noise; these
new p-values are not directly comparable with the registered full-dispatch instrumentation.

The sign-flip and Wilcoxon tests are recorded as sensitivity analyses and never decide; S' - C, S - C, P_y - S (by
donor cluster) and P_i - S are descriptive; withholding and restoration twins give tau per procedure, never deciding.
So is §6.2's 15-minute series (``series``; registrar decision 2026-10-22 on ticket PR-F2-1): per set and arm, the
short-answer share, the answer-tag share and the reply length by the test read's definitions (``readout``'s, the
short answer of registrar decision fixer-2), recorded with the decision and read by no guard. Every acceptance
decision is selection evidence (Codex F2).

A paused round is redone one block at a time (registration §9.3: each redo in its own sub-scope, "a pause redoes only
one block"; owner decision #15, default in force: the block is redone WHOLE, cells of different attempts are never
spliced inside a block; plan §5 recovery; ticket C7c-2). Attempt N >= 2 of the accept unit keeps every block that an
earlier attempt completed -- every scheduled cell of the block has its finished record in that one attempt
(``earlier_blocks``) -- and runs the other blocks in schedule order: a block an earlier attempt started and did not
complete is redone whole through ``dispatch``'s ``redo`` (the redo's own sub-scope and the redo reserve), none of its
earlier records ever read again; a block no attempt started is the round's first run of it. ``runner`` names the unit
attempt in every cell (``unit_attempt``); ``decide`` refuses a round with a missing, doubled or foreign cell or with a
block whose cells come from two attempts, and seals the block -> attempt provenance map, each block with the digest of
its records, into the decision, so ``reproduce`` makes the decision again from the cell records that ``round_cells``
reads back by that map.

Cell record contract (plan §2.8, A8's cells): ``{"arm", "task_id", "run", "set": "real"|"G_acc"|"probe", "judge":
{"v2": {"token"}, "format": {"violation"}, "flags": [...]}, "faults": [{"procedure", "hook", "kind"}],
"logical_calls": [{"purpose"}], "worst_delivery", "sends", "dispatch_ts", "finish_ts"}``. ``runner`` makes these cells
on one thread pool in the schedule's order (``cells.run_cell`` through ``cells.run_parallel``, as ``cells.run_cells``
runs them; integration B3, ticket A9-2): an acceptance round never goes through ``rounds.run_round``, which re-orders
its jobs. The G_acc cells run on the examiner's endpoint, every other cell on the round's (``runner``'s ``examiner``;
§3.3, §9.2, ticket C7e-1).
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import time
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from skillopt.coevo5.evaluation import ATTEMPT, attempts
from skillopt.coevo5.step import answered
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import donors, placebo, router, stats_ext, reuse as request_reuse, profiles
from .cells import Arm, Pause, cell_id, run_cell, run_parallel
from .outcomes_ext import DELIVERED
from .package import Package, empty, restore
from .profiles import (ALPHA, BLOCK_GAP_SECONDS, DUP_ALPHA, FAULT_SHARE_MAX, G_ACC, HARMFUL_SHAM_ALPHA,
                       INFRA_UNKNOWN_MAX,
                       META_PROBE_ALPHA, META_PROBE_GAIN, MIN_WHOLE_BATCH, RECORD_HASH, REASONING_MISMATCH_MAX,
                       SECOND_CALL_FLAG, SEED, SHARED_UNANSWERED_MAX, SLICES, START_BALANCE_MAX, TIME_WINDOW_SECONDS,
                       discourage_tag, fault_items_max, format_margin, record, round_tag, verified)

CANDIDATE, PARENT, CARD, PLACEBO_Y, PLACEBO_I, DUP = "S'", "S", "C", "P_y", "P_i", "S_dup"
SETS = ("real", "G_acc", "probe")
G_ACC_ARMS = (CANDIDATE, PARENT, PLACEBO_Y, CARD)  # §3.3, §7.2 (+ S_dup with the duplicate arm)
ARM_KINDS = {CANDIDATE: "candidate", PARENT: "parent", CARD: "card", PLACEBO_Y: "placebo_y", PLACEBO_I: "placebo_i",
             DUP: "dup"}  # the cell record's arm_kind (plan §2.8)
EVIDENCE_KIND = "selection"  # Codex F2: the test read is the independent generalization evidence
HARMFUL_WORDING = "superiority over the parent; content/effort explanation not excluded"
SMALL = router.SMALL
UNANSWERED = ("unknown",)


# ---------------------------------------------------------------------------------------------------- arms
def twin_arm(kind, procedure_id):
    """A twin arm's label (plan §2.8 ``arm_kind``): ``withhold:<id>`` or ``restore:<id>``."""
    require(kind in ("withhold", "restore"), "A twin withholds or restores")
    return kind + ":" + procedure_id


def side(arm):
    """§6.3: the candidate arms (S' and its twins) are read on L, every other arm on H."""
    return "L" if arm == CANDIDATE or arm.startswith(("withhold:", "restore:")) else "H"


def twin_only(sealed):
    """§6.5 (Codex review 2026-10-22 #12): the items of A outside A* that carry an inherited procedure's twin
    (``router.plan``'s ``twin_only``, in slice order). Each runs S' and its twin cells only -- the two sides of tau_p,
    no decision arm -- and is dispatched and decided with A* (``dispatched``); none when the round does not run."""
    plan = sealed["plan"]
    return [] if plan["decision"] == SMALL else list(plan.get("twin_only") or [])


def dispatched(sealed):
    """The items a running round dispatches, and decides once it is decided: A*, the twin-only items (``twin_only``)
    and the J7 probe; the other A items are released (``routed_not_dispatched``). None when the round does not run."""
    plan = sealed["plan"]
    return [] if plan["decision"] == SMALL else plan["astar"] + twin_only(sealed) + list(sealed["probe"])


# --------------------------------------------------------------------------------------------------- sealing
def minimum_astar(rule, size, blocks, *, alfworld=False):
    """v2.2: the |A*| floor of a round under a practical ``rule`` (``protocol.ACCEPT_RULES``) as {"items", "rooms"}:
    min(cap, max(ceil(share x |A|), blocks + extra)) items -- below the share no edit set could gain the rule's points
    over the whole batch, below blocks + extra the blocked t-test of the recorded contrasts could not be formed once an
    item went unanswered -- and on ALFWorld min(rooms cap, blocks + extra) rooms (the t-test's units)."""
    share = -(-rule["astar_share_percent"] * size // 100)
    items = min(rule["astar_cap"], max(share, blocks + rule["blocks_extra"]))
    return {"items": items, "rooms": min(rule["rooms_cap"], blocks + rule["blocks_extra"]) if alfworld else None}


def prepare(root, *, chain, bench, step, unit, candidate, parent, views, blocks, workers, trajectories, rooms=None,
            generate=None, dup=False, probe=(), freshness=None, mde=None, rule=None, reuse=None, configuration=None):
    """Seal one acceptance round (module docstring) and write it once to ``<root>/sealed.json``. ``views``: {item:
    routing view} of the acceptance slice A in slice order (``solver.routing_view``); ``blocks``: {item: block} for A
    (ALFWorld blocks are whole rooms); ``workers(package, item)``: a context manager yielding a started sandbox worker
    holding ``package`` for ``item`` (acceptance or run-slice item); ``trajectories``: the parent's run-slice
    trajectories (the donors); ``rooms``: {item: room} on ALFWorld; ``generate(astar views) -> [{"id",
    "source_item"}]``: the examiner's frozen generator on the A* public views (G_acc; None without a generator);
    ``dup``: the registered duplicate arm S_dup runs; ``probe``: LiveMath's J7 probe items; ``rule``: v2.2's
    practical rule (``protocol.ACCEPT_RULES``), sealed with its |A*| floor, None for the registered J1-J7. ``reuse``:
    v2.3's {card_text, runtime, views: {G_acc/probe: {item: shell view}}}, None for the historical full dispatch.
    v2.8 seals its configuration so J3 is reported without deciding; earlier records keep their exact shape."""
    require(set(blocks) == set(views), "Every acceptance item has a block")
    if bench == "zebralogic":
        require(generate is None and not dup and not probe,
                "zebra-pc-v1 has no generator, duplicate instrument or LiveMath probe")
    evidence = candidate.evidence
    corpus = donors.donor_corpus(candidate, parent, trajectories, workers)
    minimum = None if rule is None else minimum_astar(rule, len(views), len(set(blocks.values())),
                                                      alfworld=bench == "alfworld")
    plan = router.plan(candidate, parent, bench, views, workers, unit=unit, rooms=rooms, donors=corpus["donors"],
                       minimum=minimum)
    astar = plan["astar"]
    changed = donors.changed(parent, candidate)
    shams = placebo.placebo_package(candidate, parent)[1]
    packages = round_packages(candidate, parent, step=step, twins=plan["twins"])
    placebo_y = placebo_i = g_acc = None
    if plan["decision"] != SMALL:
        lengths = placebo.real_lengths(changed, {i: views[i] for i in astar}, workers, bench=bench,
                                       packages={"candidate": candidate, "parent": parent})
        placebo_y = placebo.build_y(corpus, plan["donors"]["pairs"], lengths, changed=changed)
        placebo_i = placebo.build_i(placebo_y, {p.id: p for _, p, _ in changed}, bench=bench, unit=unit)
        if generate is not None:
            g_acc = [{"id": g["id"], "source_item": g["source_item"]} for g in generate({i: views[i] for i in astar})]
            require(all(g["source_item"] in astar for g in g_acc) and len({g["id"] for g in g_acc}) == len(g_acc)
                    and len({g["source_item"] for g in g_acc}) == len(g_acc) and len(g_acc) <= G_ACC[bench],
                    "G_acc holds one generated item per A* item at most, within the bench's registered maximum")
    fields = {
        "chain": chain, "bench": bench, "step": step, "unit": unit, "runs": SLICES[bench]["accept"][1],
        "A": list(views), "blocks": dict(blocks), "rooms": dict(rooms) if rooms else None,
        "freshness": freshness, "mde_registered": mde, "dup": bool(dup), "probe": list(probe),
        "card_is_parent": not parent.for_bench(bench), "shams": list(shams),
        "packages": {name: package.sha256 for name, package in packages.items()},
        "plan": plan, "corpus": corpus, "placebo_y": placebo_y, "placebo_i": placebo_i, "g_acc": g_acc}
    if rule is not None:  # v2.2: the practical rule ``decide`` reads
        fields["rule"] = dict(rule)
    if profiles.is_v28(configuration):
        fields["configuration"] = configuration
    if bench == "zebralogic":
        fields["j6_registered"] = False
    if reuse is not None:
        fields["seeds"] = {"request_reuse": SEED}
    fields["seals"] = {
        "candidate": candidate.sha256, "parent": parent.sha256, "donor_corpus": corpus[RECORD_HASH],
        "placebo_y": digest(placebo_y), "placebo_i": None if placebo_i is None else digest(placebo_i),
        "plan_sha256": plan[RECORD_HASH], "twins_sha256": digest(plan["twins"]),
        "g_acc_sha256": None if g_acc is None else digest(g_acc)}
    sealed = record("acceptance-sealed", evidence, fields)
    if reuse is not None:
        signatures = {}
        all_views = {"real": views, **reuse.get("views", {})}
        if bench in request_reuse.BENCHES:
            for jobs in schedule(sealed).values():
                for job in jobs:
                    cell_set, item, arm = job["set"], job["item"], job["arm"]
                    rows = signatures.setdefault(cell_set, {}).setdefault(item, {})
                    if arm in rows:
                        continue
                    key, _, keywords = cell_arm(sealed, job, cell=cell_id(unit, arm, item, job["run"]))
                    require(item in all_views.get(cell_set, {}), "Every reuse item has its exact shell view")
                    with workers(packages[key], item) as worker:
                        rows[arm] = request_reuse.signature(bench, packages[key], all_views[cell_set][item], worker,
                                                           card_text=reuse.get("card_text", ""),
                                                           runtime=reuse.get("runtime"), **keywords)
        sealed = with_reuse(sealed, request_reuse.from_signatures(sealed, signatures))
    write_json(safe_path(root) / "sealed.json", sealed)
    return sealed


def with_reuse(sealed, plan):
    """Seal v2.3's zero-call plan, or an explicitly labelled offline counterfactual, without changing an old file."""
    require(plan.get("version") == request_reuse.VERSION, "The registered request reuse plan")
    fields = {k: v for k, v in sealed.items() if k not in ("version", "evidence", RECORD_HASH)}
    fields["reuse"] = plan
    fields["seals"] = {**fields["seals"], "reuse_sha256": digest(plan)}
    return record("acceptance-sealed-v2-3", sealed["evidence"], fields)


def round_packages(candidate, parent, *, step, twins):
    """{key: Package} of a round's arms, keyed as ``cell_arm`` names them: the candidate, the parent, the card (the
    step's empty package), the placebo package of P_y and P_i (``placebo.placebo_package``) and one ``restore:<id>``
    package per restoration twin (``twins``: the plan's {item: [twin]}). ``prepare`` seals their hashes; the dispatch
    driver rebuilds them with the sealed ``step`` and ``plan["twins"]`` (integration B3)."""
    found = {"candidate": candidate, "parent": parent, "card": empty(step=step, evidence=candidate.evidence),
             "placebo": placebo.placebo_package(candidate, parent)[0]}
    for item_twins in twins.values():
        for twin in item_twins:
            if twin["kind"] == "restore":
                found["restore:" + twin["procedure"]] = restore(candidate, parent, [twin["procedure"]])
    return found


def check_packages(sealed, packages):
    """The packages a dispatch uses are the sealed ones (by hash); a changed input is refused."""
    sealed = verified(sealed, "acceptance-sealed")
    require(set(packages) == set(sealed["packages"]) and all(
        isinstance(packages[k], Package) and packages[k].sha256 == sha for k, sha in sealed["packages"].items()),
        "The packages are not the sealed ones")


# -------------------------------------------------------------------------------------------------- dispatch
def _seeded(tag, *parts):
    """The sort key of the round's seeded orders: the sha256 of (SEED, tag, parts), the form of cal-1's ``_order``
    (coevo5/step.py:79-80)."""
    return hashlib.sha256(json.dumps([SEED, tag, *parts]).encode()).hexdigest()


def _ordered(jobs, tag):
    """The one seeded order of a block's jobs (§6.2; registrar decision on statistics review 8, 2026-10-22): every cell
    of the block -- each arm x item x run, the twins, G_acc and the probe -- in the sha256 order of (SEED, tag, set,
    item, run, arm), never grouped by arm or by item."""
    return sorted(jobs, key=lambda job: _seeded(tag, job["set"], job["item"], job["run"], job["arm"]))


def schedule(sealed, *, logical=False):
    """{block: [job]} of the round, each block in its one seeded order (``_ordered``, §6.2). A job is ``{"arm",
    "item", "run", "set", "block", "source_item"}``; a G_acc item runs in its source item's block, the J7 probe items
    are dealt over the blocks in turn in their seeded order (no block of their own; statistics review 8). An item of A
    outside A* with an inherited procedure's twin (``twin_only``, §6.5) runs S' and its twin cells only, in its own
    block (Codex review 2026-10-22 #12). Nothing when the round does not run."""
    sealed = verified(sealed, "acceptance-sealed")
    plan = sealed["plan"]
    if plan["decision"] == SMALL:
        return {}
    arms = [CANDIDATE, PARENT, CARD, PLACEBO_Y] + ([PLACEBO_I] if sealed["placebo_i"] is not None else [])
    arms += [DUP] if sealed["dup"] else []
    jobs, outside = [], twin_only(sealed)
    alone = set(outside)
    for item in plan["astar"] + outside:
        names = ([CANDIDATE] if item in alone else arms) + [twin_arm(t["kind"], t["procedure"])
                                                            for t in plan["twins"].get(item, [])]
        jobs += [{"arm": a, "item": item, "run": r, "set": "real", "block": sealed["blocks"][item],
                  "source_item": item} for a in names for r in range(sealed["runs"])]
    for generated in sealed["g_acc"] or []:
        source = generated["source_item"]
        jobs += [{"arm": a, "item": generated["id"], "run": 0, "set": "G_acc", "block": sealed["blocks"][source],
                  "source_item": source} for a in G_ACC_ARMS + ((DUP,) if sealed["dup"] else ())]
    blocks = sorted(set(sealed["blocks"].values()), key=str)
    probes = sorted(sealed["probe"], key=lambda item: _seeded(round_tag(sealed["unit"]) + ":probe", item))
    jobs += [{"arm": a, "item": item, "run": 0, "set": "probe", "block": blocks[n % len(blocks)], "source_item": None}
             for n, item in enumerate(probes) for a in (CANDIDATE, CARD)]
    out = {}
    for job in jobs:
        out.setdefault(job["block"], []).append(job)
    if sealed.get("reuse") is not None and not logical:
        plan = sealed["reuse"]
        out = {block: [job for job in jobs if request_reuse.reference(plan, job) is None
                      and not request_reuse.skipped(plan, job)] for block, jobs in out.items()}
    return {block: _ordered(out[block], round_tag(sealed["unit"]) + ":" + str(block)) for block in sorted(out, key=str)
            if out[block]}


def cell_arm(sealed, job, *, cell):
    """``(package key, arm kind, solver.solve arm keywords)`` of one cell: the sealed package to run
    (``sealed["packages"]``), the cell record's ``arm_kind`` (plan §2.8, ``cells.ARM_KINDS``; a twin's own label) and
    ``withhold``/``restore``/``placebo`` (the placebo seeded by ``discourage_tag(unit, cell)``)."""
    arm = job["arm"]
    if arm in ARM_KINDS and arm not in (PLACEBO_Y, PLACEBO_I):
        return ("parent" if arm == DUP else ARM_KINDS[arm]), ARM_KINDS[arm], {}
    if arm in (PLACEBO_Y, PLACEBO_I):
        content = sealed["placebo_y"] if arm == PLACEBO_Y else sealed["placebo_i"]
        seed = discourage_tag(sealed["unit"], cell)
        return "placebo", ARM_KINDS[arm], {"placebo": placebo.arm(content, job["source_item"], seed=seed)}
    kind, procedure = arm.split(":", 1)
    if kind == "withhold":
        return "candidate", arm, {"withhold": frozenset({procedure})}
    return "restore:" + procedure, arm, {"restore": frozenset({procedure})}


def dispatch(sealed, registry, run, *, items, attempt=1, earlier=None, redo=None, clock=time.time, sleep=time.sleep):
    """Run the sealed round: the A items outside A* are released (``routed_not_dispatched``) -- except the twin-only
    items, whose S' and twin cells run (§6.5, Codex review 2026-10-22 #12) -- A*, the twin-only and the probe items
    dispatched (``dispatched``), then ``run(block, jobs) -> [cell record]`` per block in order; before a later block,
    the bench's registered gap (``BLOCK_GAP_SECONDS``: OfficeQA's two time blocks >= 2 h apart, §3.3) is waited out
    since the previous block finished. ``items``: {task id: item record} of A and the probe exactly as the unit
    registered them (the registry checks their hashes). A round that does not run releases every slice and probe item
    and returns no cells (nothing consumed, Codex F1). The caller decides with ``decide`` and then ``settle``s the
    decision.

    A redo (``attempt`` >= 2; §9.3, owner decision #15; module docstring): ``earlier`` is ``earlier_blocks`` of this
    attempt. Its reused blocks are not run again -- their records join the returned cells -- and the gap before the
    first block this attempt runs counts from the reused blocks' last recorded finish (``finish_ts``), so the
    registered gap holds between every two blocks of the round whichever attempt ran them. A block an earlier attempt
    started is redone whole through ``redo(block, jobs)`` (the redo's sub-scope and the redo reserve; ``run`` when
    None); the blocks no attempt started go through ``run``. Returns the round's cells, block by block in schedule
    order."""
    sealed = verified(sealed, "acceptance-sealed")
    chain, bench, unit = sealed["chain"], sealed["bench"], sealed["unit"]
    require(set(sealed["A"]) | set(sealed["probe"]) <= set(items), "Every slice and probe item has its record")
    earlier = earlier or {"reused": {}, "cells": {}, "redone": []}
    require(attempt > 1 or not (earlier["reused"] or earlier["redone"]), "A first attempt has no earlier block")
    sent = dispatched(sealed)
    released = [items[i] for i in sealed["A"] + sealed["probe"] if i not in set(sent)]
    if released:
        registry.release(chain, bench, released, unit=unit, attempt=attempt)
    if not sent:
        return []
    registry.dispatch(chain, bench, [items[i] for i in sent], unit=unit, attempt=attempt)
    plan = schedule(sealed)
    reused = {str(block): earlier["cells"][str(block)] for block in plan if str(block) in earlier["reused"]}
    finished = max((_seconds(cell["finish_ts"]) for found in reused.values() for cell in found), default=None)
    by_block = dict(reused)
    for block, jobs in plan.items():
        if str(block) in reused:
            continue
        if finished is not None:
            wait = BLOCK_GAP_SECONDS.get(bench, 0) - (clock() - finished)
            if wait > 0:
                sleep(wait)
        chosen = redo if redo is not None and str(block) in earlier["redone"] else run
        by_block[str(block)] = chosen(block, jobs)
        finished = clock()
    return [cell for block in plan for cell in by_block[str(block)]]


def settle(decision, sealed, registry, items, *, attempt=1):
    """The step driver's use of a round's decision (§13 table; statistics review 4): accept and reject mark the A*,
    twin-only and probe items decided (``dispatched``; ``registry.decide``); an undetermined round marks nothing -- its
    items stay "dispatched", consumed but undecided -- and raises ``cells.Pause`` for the owner's recovery; a round that
    did not run (its items were released by ``dispatch``) has nothing to settle. Returns the decision."""
    decision, sealed = verified(decision, "decision"), verified(sealed, "acceptance-sealed")
    require(decision["sealed"]["record"] == sealed[RECORD_HASH], "The decision of another sealed round")
    if decision["decision"] == SMALL:
        return decision
    if decision["decision"] == "undetermined":
        raise Pause("acceptance_undetermined", decision["reason"], sealed["unit"])
    require(decision["decision"] in ("accept", "reject"), "A decision accepts, rejects or is undetermined")
    registry.decide(sealed["chain"], sealed["bench"], [items[i] for i in dispatched(sealed)],
                    unit=sealed["unit"], attempt=attempt)
    return decision


def runner(context, sealed, packages, tasks, *, workers, store, examiner=None):
    """The ``run(block, jobs)`` of ``dispatch`` (integration B3, ticket A9-2): each job of a block becomes one cell of
    the round's unit -- {id, unit, arm, benchmark, task_id: the job's item, run, set, block, source_item} -- whose
    ``cells.Arm`` is ``cell_arm``'s sealed package, arm kind and keywords; the block's cells run with
    ``cells.run_cell`` on one thread pool (``cells.run_parallel``, as ``cells.run_cells`` runs them) in the schedule's
    order, never re-ordered (``rounds.run_round`` re-orders and is not used here). ``context``: the attempt's
    ``cells.Context``; ``packages``: {key: Package}, the sealed ones (``check_packages``); ``tasks``: {item: {"public",
    "private"}} of the A* items, the G_acc items and the probe items; ``store``: the attempt's
    ``cells.TrainingStore``. ``examiner``: the Context of the G_acc cells -- the registration puts their solver cost
    in the examiner scope (§3.3 "它的做题费用记在考官作用域里（9.2、9.3）", §9.2, calc T6; registrar decision 2026-10-22
    on ticket C7e-1), so the step gives ``context`` with the examiner's endpoint (``units.solver_endpoint(...,
    g_acc=True)``) in the same attempt; None runs them on ``context`` (a round without G_acc, or a fixture with one
    endpoint). Each cell takes its set's Context, so the block keeps its one pool and one seeded order (§6.2). A stop
    pauses the round after the cell's record is stored (``cells.run_cell``). Every cell names its unit attempt
    (``unit_attempt``: the name of ``context.attempt``) so a block's provenance is read from its records (owner
    decision #15)."""
    sealed = verified(sealed, "acceptance-sealed")
    check_packages(sealed, packages)
    unit, bench, attempt = sealed["unit"], sealed["bench"], safe_path(context.attempt).name
    require(examiner is None or safe_path(examiner.attempt) == safe_path(context.attempt),
            "The G_acc cells run in the round's unit attempt")

    def run(block, jobs):
        built = []
        for job in jobs:
            require(str(job["block"]) == str(block), "A job of another block")
            cell = {"id": cell_id(unit, job["arm"], job["item"], job["run"]), "unit": unit, "arm": job["arm"],
                    "benchmark": bench, "task_id": job["item"], "run": job["run"], "set": job["set"],
                    "block": str(block), "source_item": job["source_item"], "unit_attempt": attempt}
            key, kind, keywords = cell_arm(sealed, job, cell=cell["id"])
            task = tasks[job["item"]]
            chosen = examiner if examiner is not None and job["set"] == "G_acc" else context  # C7e-1
            built.append((chosen, cell, {"public": task["public"], "private": task["private"]},
                          Arm(kind, packages[key], **keywords)))
        return run_parallel(lambda entry: run_cell(*entry, store=store), built, workers=workers)

    return run


# --------------------------------------------------------------------------- a redo (§9.3, owner decision #15)
def unit_attempt(cell):
    """The unit attempt a cell record ran in -- ``runner`` names it in the record's cell (``unit_attempt``, the
    attempt directory's name) -- or None for a record without it (a synthetic cell of the unit tests)."""
    inner = cell.get("cell")
    return inner.get("unit_attempt") if isinstance(inner, dict) else None


def _job_key(job):
    return job["set"], job["item"], job["run"], job["arm"]


def _cell_key(cell):
    return cell["set"], cell["task_id"], cell["run"], cell["arm"]


def _finished(record, sealed, job, attempt):
    """Whether ``record`` (a verified cell record, or None when the attempt holds none) is the finished record of
    ``job`` in the attempt named ``attempt``: of the round's unit, the job's set, item, run, arm and block, run in that
    attempt, judged and not stopped."""
    if record is None:
        return False
    inner = record.get("cell") if isinstance(record.get("cell"), dict) else {}
    return (record.get("stop") is None and record.get("final") is not None and isinstance(record.get("judge"), dict)
            and inner.get("unit") == sealed["unit"] and inner.get("unit_attempt") == attempt
            and inner.get("block") == str(job["block"]) and _cell_key(record) == _job_key(job))


def earlier_blocks(sealed, unit_root, attempt):
    """What the earlier attempts of the accept unit at ``unit_root`` leave to ``attempt`` (an ``attempt-N``
    directory; §9.3, owner decision #15): {"reused": {block: attempt name}, "cells": {block: [its records in the
    block's seeded order]}, "redone": [blocks to run again]}. A block is reused when ONE earlier attempt holds the
    finished record of every scheduled cell of it (``_finished``) -- the first such attempt; a block with one cell
    missing, stopped, unjudged or of another job is not complete, so it runs again whole and none of its earlier
    records is read again. A block that is not reused is redone when an earlier attempt claimed or stored any of its
    cells (it started there); the others were never started. A stored record that fails its seal raises."""
    sealed = verified(sealed, "acceptance-sealed")
    unit_root, number = safe_path(unit_root), _attempt_number(attempt)
    earlier = [past for past in attempts(unit_root) if _attempt_number(past) < number]
    found = {"reused": {}, "cells": {}, "redone": []}
    for block, jobs in schedule(sealed).items():
        names = [cell_id(sealed["unit"], job["arm"], job["item"], job["run"]) for job in jobs]
        for past in earlier:
            paths = [past / "cells" / (name + ".json") for name in names]
            records = [verified(read_json(path), "cell") if path.exists() else None for path in paths]
            if all(_finished(record, sealed, job, past.name) for record, job in zip(records, jobs)):
                found["reused"][str(block)], found["cells"][str(block)] = past.name, records
                break
        else:
            if any((past / "cells" / (name + ext)).exists() for past in earlier for name in names
                   for ext in (".claim", ".json")):
                found["redone"].append(str(block))
    return found


def _attempt_number(attempt):
    """N of an ``attempt-N`` directory (the frozen attempt naming, coevo5 evaluation.py)."""
    match = ATTEMPT.fullmatch(safe_path(attempt).name)
    require(match is not None, "Not an attempt directory: %s" % attempt)
    return int(match.group(1))


# a frame of ``decide`` in the traceback ``units.run_unit`` keeps in a paused attempt's diagnostics.log
DECIDE_FRAME = re.compile(r'File "[^"\n]*skillopt[/\\]execskill[/\\]acceptance\.py", line [0-9]+, in decide$', re.M)


def finished_round(attempt):
    """Registrar decision 2026-10-22 13:5x on ticket C7e-2 (choice 1), enforced in code by addendum 14:10 row 17: why
    the paused attempt ``attempt`` of an accept unit is a FINISHED round, else None. A round is finished when every
    scheduled cell of every block holds its finished record (``earlier_blocks`` as a redo would see it: every block
    reused) and the attempt paused as ``acceptance_undetermined`` (its decision is undetermined: J5 or J6) or on an
    error raised by ``decide`` (a ``decide`` frame in the traceback of its ``diagnostics.log``). A redo of it would
    reuse every block and decide, or fail, the same way again -- one of the unit's redos spent for nothing; a fresh
    round needs a v1.1 rule. ``run_execskill.py recover`` refuses such an attempt; the main agent reports it to the
    owner."""
    attempt = safe_path(attempt)
    unit_root = attempt.parent
    if ATTEMPT.fullmatch(attempt.name) is None or not (unit_root / "sealed.json").exists():
        return None  # not an attempt of an accept unit whose round was sealed
    sealed = verified(read_json(unit_root / "sealed.json"), "acceptance-sealed")
    blocks = schedule(sealed)
    following = unit_root / ("attempt-%d" % (_attempt_number(attempt) + 1))
    if not blocks or len(earlier_blocks(sealed, unit_root, following)["reused"]) != len(blocks):
        return None  # a block still runs again in a redo
    status, decided = attempt / "status.json", attempt / "decision" / "decision.json"
    kind = verified(read_json(status), "unit-status")["kind"] if status.exists() else None
    decision = verified(read_json(decided), "decision")["decision"] if decided.exists() else None
    if kind == "acceptance_undetermined" or decision == "undetermined":
        return "acceptance_undetermined"
    log = attempt / "diagnostics.log"
    if log.exists() and DECIDE_FRAME.search(log.read_text(encoding="utf-8", errors="replace")):
        return "an error raised by acceptance.decide"
    return None


def _provenance(cells, sealed):
    """{block: {"attempt", "cells", "cells_sha256"}} of a round's cells (§9.3, owner decision #15; module docstring):
    every scheduled cell exactly once -- a missing, doubled or foreign cell is refused, so a partial block is never
    decided -- and each block's cells from ONE unit attempt (``unit_attempt``; a block is redone whole, never spliced
    across attempts). ``cells_sha256`` is the digest of the block's records in its seeded order, so the decision is
    bound to the exact records it was made from."""
    places = {_job_key(job): (str(block), k) for block, jobs in schedule(sealed).items() for k, job in enumerate(jobs)}
    found = {}
    for cell in cells:
        key = _cell_key(cell)
        require(key in places, "A cell outside the round's schedule: %s" % (key,))
        require(key not in found, "A cell twice in the round (owner decision #15: no splicing): %s" % (key,))
        found[key] = cell
    missing = sorted((key for key in places if key not in found), key=str)
    require(not missing, "Scheduled cells are missing, a partial block is never decided: %d, e.g. %s" % (
        len(missing), missing[0] if missing else None))
    blocks = {}
    for key, (block, k) in places.items():
        blocks.setdefault(block, []).append((k, found[key]))
    out = {}
    for block in sorted(blocks):
        ordered = [cell for _, cell in sorted(blocks[block], key=lambda entry: entry[0])]
        names = sorted({unit_attempt(cell) for cell in ordered}, key=str)
        require(len(names) == 1, "A block's cells come from one unit attempt (owner decision #15: redone whole, never "
                                 "spliced): block %s holds cells of %s" % (block, names))
        out[block] = {"attempt": names[0], "cells": len(ordered), "cells_sha256": digest(ordered)}
    return out


# --------------------------------------------------------------------------------------------- the decision
def _token(cell):
    require(isinstance(cell.get("judge"), dict), "A stopped cell has no judge; its unit pauses and is not decided")
    return cell["judge"]["v2"]["token"]


def table(cells, cell_set="real", *, identical=()):
    """{(arm, item): [v2 token per run]} of one set's cells."""
    out = _ReuseTable(identical, cell_set) if identical or any(c.get("reused_from") for c in cells) else {}
    for cell in sorted((c for c in cells if c["set"] == cell_set), key=lambda c: (c["arm"], c["task_id"], c["run"])):
        out.setdefault((cell["arm"], cell["task_id"]), []).append(_token(cell))
        if isinstance(out, _ReuseTable):
            origin = cell.get("reused_from") or cell
            out.origins[(cell["arm"], cell["task_id"], cell["run"])] = (
                origin["set"], origin["task_id"], origin["run"], origin["arm"])
            out.runs.setdefault((cell["arm"], cell["task_id"]), {})[cell["run"]] = _token(cell)
    return out


class _ReuseTable(dict):
    """Each arm keeps its own H/L score; exact shared origins identify only the paired contributions set to zero."""
    def __init__(self, identical=(), cell_set="real"):
        super().__init__()
        self.origins, self.runs = {}, {}
        self.identical = frozenset(identical)
        self.cell_set = cell_set


def expanded_cells(cells, sealed):
    """Materialize the sealed same-item/run references for scoring; provenance and timings use physical cells."""
    plan = sealed.get("reuse")
    if plan is None:
        return cells
    require(digest(plan) == sealed["seals"]["reuse_sha256"], "The sealed reuse plan is unchanged")
    found = {_cell_key(cell): cell for cell in cells}
    pending = [job for jobs in schedule(sealed, logical=True).values() for job in jobs
               if request_reuse.reference(plan, job) is not None]
    for _ in range(len(pending) + 1):
        if not pending:
            break
        left = []
        for job in pending:
            reference = request_reuse.reference(plan, job)
            require(reference != job["arm"], "An arm cannot reuse itself")
            source_job = {**job, "arm": reference}
            source = found.get(_job_key(source_job))
            if source is None:
                left.append(job)
                continue
            identities = plan["signatures"].get(job["set"], {}).get(job["item"], {})
            require(request_reuse.interchangeable(identities.get(job["arm"]), identities.get(reference),
                                                  bench=sealed["bench"]), "A sealed reuse pair is interchangeable")
            origin = source.get("reused_from") or {"arm": reference, "task_id": job["item"],
                                                   "run": job["run"], "set": job["set"]}
            fields = {k: v for k, v in source.items() if k not in ("version", "evidence", RECORD_HASH)}
            fields.update({"arm": job["arm"], "reused_from": dict(origin)})
            package, kind, keywords = cell_arm(sealed, job, cell=cell_id(
                sealed["unit"], job["arm"], job["item"], job["run"]))
            if "package_sha256" in fields:
                fields.update({"package_sha256": sealed["packages"][package], "arm_kind": kind,
                               "withheld": sorted(keywords.get("withhold", [])),
                               "restored": sorted(keywords.get("restore", []))})
                if "enabled" in identities[job["arm"]]:
                    fields["enabled"] = identities[job["arm"]]["enabled"]
            if "cell" in fields:
                fields["cell"] = {**fields["cell"], "arm": job["arm"],
                                  "id": cell_id(sealed["unit"], job["arm"], job["item"], job["run"])}
            found[_job_key(job)] = record("cell-v2-3", source.get("evidence", sealed["evidence"]), fields)
        require(len(left) < len(pending), "The reuse plan has a missing source or a cycle")
        pending = left
    return [found[_job_key(job)] for jobs in schedule(sealed, logical=True).values() for job in jobs
            if not request_reuse.skipped(plan, job)]


def shared_unanswered(cells, items):
    """§6.3 (frozen step.shared_unanswered on v2 tokens): the items on which no arm got any reply."""
    found = {}
    for cell in cells:
        if cell["set"] == "real":
            found.setdefault(cell["task_id"], []).append(cell)
    return sorted(i for i in set(items) if found.get(i) and all(
        _token(c) in UNANSWERED and not answered(c) for c in found[i]))


def differences(cells_table, first, second, items):
    """Per-item differences first - second (each arm on its §6.3 side), in ``items`` order. V2.3 cancels only the
    contribution of a run whose two arms share the same origin on that item/run, never changing cross-class bounds."""
    identical = getattr(cells_table, "identical", frozenset())
    measured = [item for item in items if item not in identical]
    a = stats_ext.item_scores(cells_table, first, measured, side=side(first))
    b = stats_ext.item_scores(cells_table, second, measured, side=side(second))
    adjusted = {item: a[item] - b[item] for item in measured}
    if isinstance(cells_table, _ReuseTable):
        for item in measured:
            first_runs, second_runs = cells_table.runs[(first, item)], cells_table.runs[(second, item)]
            for run in first_runs.keys() & second_runs.keys():
                origin = cells_table.origins[(first, item, run)]
                other = cells_table.origins[(second, item, run)]
                if origin != other or origin[:3] != (cells_table.cell_set, item, run):
                    continue
                require(first_runs.keys() == second_runs.keys(), "A shared pair has the same registered run indices")
                left = stats_ext.item_scores({(first, item): [first_runs[run]]}, first, [item], side=side(first))[item]
                right = stats_ext.item_scores({(second, item): [second_runs[run]]}, second, [item], side=side(second))[item]
                adjusted[item] -= (left - right) / len(first_runs)
    return [Fraction(0) if i in identical else adjusted[i] for i in items]


def _design(sealed, items):
    bench = sealed["bench"]
    return {"strata": [sealed["blocks"][i] for i in items],
            "clusters": [sealed["rooms"][i] for i in items] if bench == "alfworld" else None}


def _too_few_units(sealed, items):
    """v2.2 (Codex review MAJOR 1): None when the answered A* items leave the t-test a degree of freedom -- more units
    (rooms on ALFWorld, ``_design``'s clusters, else items) than the blocks they fall in -- else the reason they do not."""
    alfworld = sealed["bench"] == "alfworld"
    units = {sealed["rooms"][i] for i in items} if alfworld else set(items)
    blocks = {sealed["blocks"][i] for i in items}
    if len(units) > len(blocks):
        return None
    return "too few answered units for the t-test (%d %s in %d blocks)" % (
        len(units), "rooms" if alfworld else "items", len(blocks))


def _two_sided(test):
    """The two-sided p of a ``paired_t`` result (J6, descriptive intervals)."""
    if test["se"] == 0:
        return 1.0 if test["mean"] == 0 else 0.0
    return min(1.0, 2 * min(test["p"], 1 - test["p"]))


def contrast(d, *, design=None, whole=None, sensitivity=False):
    """One contrast's record: the paired t (``p_t``: one-sided, greater), its 95 % bootstrap interval, the
    up/down/tie counts and, when ``sensitivity``, the sign-flip and Wilcoxon p (never deciding)."""
    design = design or {}
    test = stats_ext.paired_t(d, **design)
    lo, hi = stats_ext.bootstrap_ci(d, **design)
    out = {"n": len(d), "mean": test["mean"], "se": test["se"], "df": test["df"], "p_t": test["p"],
           "p_two_sided": _two_sided(test), "ci95": [lo, hi], "up": sum(x > 0 for x in d),
           "down": sum(x < 0 for x in d), "tie": sum(x == 0 for x in d)}
    if whole is not None:
        out["whole_batch"] = float(sum(d) / whole)
    if sensitivity:
        out["sensitivity"] = {"p_signflip": stats_ext.signflip(d, **design), "p_wilcoxon": stats_ext.wilcoxon(d)}
    return out


def _fault_items(cells, sealed):
    """J3's numerator (Codex F22): items of A with a routing fault of a changed procedure (the sealed plan), or an
    execution fault of one / a re-execution ``unknown_fault`` in an S' or P_y cell of any run."""
    plan, changed = sealed["plan"], set(sealed["shams"])
    items = set(plan["fault_items"])
    for cell in cells:
        if cell["set"] == "real" and cell["arm"] in (CANDIDATE, PLACEBO_Y) and (
                _token(cell) == "unknown_fault" or any(f.get("procedure") in changed for f in cell.get("faults", []))):
            items.add(cell["task_id"])
    if sealed.get("reuse") is not None:
        for item, arms in sealed["reuse"]["signatures"].get("real", {}).items():
            if item in set(sealed["A"]) and any(f.get("procedure") in changed
                                               for arm in (CANDIDATE, PLACEBO_Y)
                                               for f in arms.get(arm, {}).get("faults", [])):
                items.add(item)
    return sorted(items)


def _violating(cells, arm, items):
    """J4: the items of ``items`` with a format violation in any run of ``arm``."""
    members = set(items)
    return sorted({c["task_id"] for c in cells if c["set"] == "real" and c["arm"] == arm and c["task_id"] in members
                   and c["judge"]["format"].get("violation") is True})


def _seconds(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return datetime.fromisoformat(value).timestamp()


def _block_gap(cells, sealed):
    """§3.3 (statistics review 3): each block's dispatch window (first dispatch, last finish; a cell's block is its
    job's in ``schedule``) and, on a bench with a registered gap, whether every block started at least that long
    after the previous one finished."""
    bench = sealed["bench"]
    block_of = {(job["set"], job["item"]): str(block) for block, jobs in schedule(sealed).items() for job in jobs}
    windows = {}
    for cell in cells:
        if cell.get("dispatch_ts") is None or cell.get("finish_ts") is None:
            return {"windows": None, "required_s": BLOCK_GAP_SECONDS.get(bench, 0), "ok": False}
        start, end = _seconds(cell["dispatch_ts"]), _seconds(cell["finish_ts"])
        block = block_of[(cell["set"], cell["task_id"])]
        low, high = windows.get(block, (start, end))
        windows[block] = (min(low, start), max(high, end))
    ordered = sorted(windows.items(), key=lambda kv: kv[1][0])
    gaps = [later[1][0] - earlier[1][1] for earlier, later in zip(ordered, ordered[1:])]
    required = BLOCK_GAP_SECONDS.get(bench, 0)
    return {"windows": {block: list(window) for block, window in ordered}, "gaps_s": gaps, "required_s": required,
            "ok": all(gap >= required for gap in gaps)}


def _balance(cells, arms, sealed):
    """§6.2's start-time balance, re-derived for the one uniform seeded order (statistics review 8, registrar decision
    2026-10-22). A cell's scheduled start is the start time at its place in its block's seeded order (the block's k-th
    earliest start for the cell k-th in the order) and its delay is its actual start minus that. Deciding
    (``spread_s``): the arms' median delays lie within 5 % of the round's duration, so an arm sent out of its seeded
    place -- held back by a slot, or resumed after a pause -- fails. Recorded beside it: ``raw_spread_s``, the
    registered spread of the arms' median start times, and ``order_spread_s``, the part the seeded order alone
    accounts for (under a uniform order the raw spread leaves the 5 % band by chance in most rounds, ticket A9-2).
    Not ok when a start or finish time is missing. The round's duration (``duration_s``) is its real cells' first
    dispatch to last finish within each unit attempt its blocks come from, summed (``attempt_spans`` of them): one
    attempt -- every round that was not redone -- gives the first dispatch to the last finish, as before; a round
    redone across attempts (§9.3, owner decision #15) does not count the pause between them, so the 5 % band keeps
    its width (ticket C7c-2)."""
    real = [(index, cell) for index, cell in enumerate(cells) if cell["set"] == "real"]
    if sealed.get("reuse") is not None:
        real = list(enumerate(cells))
        arms = sorted({cell["arm"] for cell in cells})
        if not cells:
            return {"ok": True, "reason": "no_dispatched_cells", "statistic": "median_delay_spread",
                    "spread_s": 0.0, "raw_spread_s": 0.0, "order_spread_s": 0.0, "duration_s": 0.0,
                    "attempt_spans": 0}
    if not real or any(c.get("dispatch_ts") is None or c.get("finish_ts") is None for c in cells):
        return {"ok": False, "reason": "dispatch or finish time not recorded"}
    places = {(j["set"], j["item"], j["run"], j["arm"]): (str(block), k)
              for block, jobs in schedule(sealed).items() for k, j in enumerate(jobs)}
    by_block = {}
    for index, cell in enumerate(cells):
        place = places.get((cell["set"], cell["task_id"], cell["run"], cell["arm"]))
        require(place is not None, "A cell outside the round's schedule")
        by_block.setdefault(place[0], []).append((place[1], index))
    scheduled = {}
    for entries in by_block.values():
        starts = sorted(_seconds(cells[index]["dispatch_ts"]) for _, index in entries)
        scheduled.update((index, start) for start, (_, index) in zip(starts, sorted(entries)))
    spans = {}  # unit attempt -> (first dispatch, last finish) of its real cells
    for _, cell in real:
        low, high = _seconds(cell["dispatch_ts"]), _seconds(cell["finish_ts"])
        was = spans.get(unit_attempt(cell), (low, high))
        spans[unit_attempt(cell)] = (min(was[0], low), max(was[1], high))
    duration = sum(high - low for low, high in spans.values())

    def spread(value):
        medians = [statistics.median(value(index, cell) for index, cell in real if cell["arm"] == arm) for arm in arms]
        return max(medians) - min(medians)

    found = spread(lambda index, cell: _seconds(cell["dispatch_ts"]) - scheduled[index])
    return {"ok": found <= float(START_BALANCE_MAX) * duration, "statistic": "median_delay_spread",
            "spread_s": found, "raw_spread_s": spread(lambda index, cell: _seconds(cell["dispatch_ts"])),
            "order_spread_s": spread(lambda index, cell: scheduled[index]), "duration_s": duration,
            "attempt_spans": len(spans)}


def _rates(cells, arms, purpose, items):
    """Per arm the share of its real cells on ``items`` (A*: the twin-only items' S' cells are not compared, §6.5) that
    made a call of ``purpose``; flagged when S', P_y and P_i differ by more than 10 points (§6.1)."""
    rates, members = {}, set(items)
    for arm in arms:
        mine = [c for c in cells if c["set"] == "real" and c["arm"] == arm and c["task_id"] in members]
        rates[arm] = (sum(any(call.get("purpose") == purpose for call in c.get("logical_calls", [])) for c in mine)
                      / len(mine)) if mine else 0.0
    compared = [rates[a] for a in (CANDIDATE, PLACEBO_Y, PLACEBO_I) if a in rates]
    return {**rates, "flag_gt_10pt": max(compared) - min(compared) > float(SECOND_CALL_FLAG)}


def series(cells):
    """§6.2's descriptive series of one round ("每格记派发与完成时间；按组、按 15 分钟报告简短回答比例、答案格式比例、回答
    长度"; registrar decision 2026-10-22 on ticket PR-F2-1): per set and arm of the round's cells, by the test read's
    definitions (``readout.windows``, imported, not copied): the 15-minute windows of dispatch counted from the
    round's first dispatch (``TIME_WINDOW_SECONDS``), each with its cells, the answer-tag share, the mean visible
    completion tokens per call and the short-answer share -- registrar decision fixer-2: a cell whose completion tokens
    (the mean over its logical calls) are below ``readout.SHORT_ANSWER`` = 1/4 of the median of the same set and arm
    in the round's first window, ``short_answer_reference``; None, with the reference's status, when that window holds
    no such cell with usage or its median is 0 -- and ``no_usage``, the cells left out. A logical call's count is
    ``evaluation.completion_tokens`` of the receipt of its last send, as ``evaluation.sealed_cell`` reads it (None
    for a call without one, which leaves its cell out whole). Each set is its own series (the generated G_acc items
    and the J7 probe's options-only items are other items than A*'s). Descriptive: no guard reads it and it decides
    nothing (``decides``: False). A redone round's windows count from its first dispatch whichever attempt made it,
    so the pause between attempts shows as empty windows."""
    from . import evaluation, readout  # imported here: readout imports evaluation, which imports manifest -> step -> us

    rows = {}
    for cell in cells:
        sends = cell.get("sends") or []
        tokens = [evaluation.completion_tokens(sends[entry["send_indices"][-1]].get("receipt"))
                  if entry.get("send_indices") else None for entry in cell.get("logical_calls") or []]
        rows.setdefault(cell["set"], {}).setdefault(cell["arm"], []).append({
            "shared_with": cell.get("shared_with"), "dispatch_ts": cell.get("dispatch_ts"),
            "format": (cell.get("judge") or {}).get("format") or {}, "completion_tokens": tokens})
    stamps = [_seconds(cell["dispatch_ts"]) for cell in cells if cell.get("dispatch_ts") is not None]
    start = min(stamps) if stamps else 0.0
    found = {}
    for name in sorted(rows, key=SETS.index):  # an unknown set raises
        for arm, members in sorted(rows[name].items()):
            reference, windows = readout.windows(members, start)
            found.setdefault(name, {})[arm] = {"short_answer_reference": reference, "windows": windows}
    return {"start": start, "window_seconds": TIME_WINDOW_SECONDS, "short_answer": str(readout.SHORT_ANSWER),
            "decides": False, "sets": found}


def _twins(cells_table, sealed, items):
    """tau per twin procedure (§6.5): the mean over its twin items of [with p - without p], never deciding. ``items``:
    the answered A* items and the answered twin-only items (an inherited procedure's twins are drawn on A, Codex review
    2026-10-22 #12); ``n_outside_astar`` counts the latter."""
    plan, kept, out = sealed["plan"], set(items), {}
    outside = set(twin_only(sealed))
    for procedure in plan["twin_priority"]:
        kind = plan["twin_kinds"][procedure]
        members = [i for i, twins in plan["twins"].items() if i in kept
                   and any(t["procedure"] == procedure for t in twins)]
        if not members:
            out[procedure] = {"kind": kind, "n": 0, "n_outside_astar": 0, "tau": None, "ci95": None}
            continue
        arm = twin_arm(kind, procedure)
        with_p, without = (CANDIDATE, arm) if kind == "withhold" else (arm, CANDIDATE)
        d = differences(cells_table, with_p, without, members)
        out[procedure] = {"kind": kind, "n": len(d), "n_outside_astar": sum(i in outside for i in members),
                          "tau": float(sum(d) / len(d)),
                          "ci95": list(stats_ext.bootstrap_ci(d)) if len(d) > 1 else None}
    return out


def _probe(cells, *, identical=()):
    """J7 (LiveMath, formal chain): the options-only probe's S' - C; None without probe cells."""
    probe_table = table(cells, "probe", identical=identical)
    items = sorted(({i for (a, i) in probe_table if a == CANDIDATE} & {i for (a, i) in probe_table if a == CARD})
                   | set(identical))
    if not items:
        return None
    d = differences(probe_table, CANDIDATE, CARD, items)
    test = stats_ext.paired_t(d) if len(d) > 1 else {"mean": float(sum(d) / len(d)), "p": 1.0}
    shortcut = test["mean"] >= float(META_PROBE_GAIN) and test["p"] < META_PROBE_ALPHA
    return {"n": len(d), "gain": test["mean"], "p_t": test["p"], "ok": not shortcut}


def not_run(sealed):
    """The decision of a round whose A* is too small (§3.3, Codex F1): nothing ran, nothing was consumed."""
    plan = sealed["plan"]
    least = plan.get("minimum")  # v2.2: the practical rule's floor
    floor = "the registered minimum" if least is None else "the minimum of %d items%s (%s)" % (
        least["items"], "" if least["rooms"] is None else " and %d rooms" % least["rooms"], sealed["rule"]["name"])
    return record("decision-v2-3" if sealed.get("reuse") is not None else "decision", plan["evidence"], {
        **_header(sealed), "A_star": len(plan["astar"]), "A_star_rooms": plan["astar_rooms"],
        "decision": SMALL, "reason": "|A*| = %d%s below %s; S' archived, S passes on, every slice item released as "
                                     "routed_not_dispatched" % (
                                         len(plan["astar"]), "" if plan["astar_rooms"] is None
                                         else " (%d rooms)" % plan["astar_rooms"], floor)})


def _header(sealed):
    seals = sealed["seals"]
    dispatch_counts = {}
    if sealed.get("reuse") is not None:
        jobs = [job for block in schedule(sealed).values() for job in block]
        names = sorted({job["arm"] for block in schedule(sealed, logical=True).values() for job in block})
        dispatch_counts = {"physical_cells": len(jobs),
                           "dispatched_by_arm": {arm: sum(job["arm"] == arm for job in jobs) for arm in names}}
    return {**({"rule": sealed["rule"]["name"]} if sealed.get("rule") else {}),  # v2.2
            **({"configuration": sealed["configuration"]} if profiles.is_v28(sealed.get("configuration")) else {}),
            **({"reuse": {"plan_sha256": seals["reuse_sha256"], "card_sample": sealed["reuse"]["card_sample"],
                           "timing": "physical_dispatch_schedule", "infrastructure": "dispatched_representatives",
                           "identical_all": {name: len(items) for name, items in sealed["reuse"]["identical_all"].items()},
                           **dispatch_counts}}
               if sealed.get("reuse") is not None else {}),
            "step": sealed["step"], "bench": sealed["bench"], "chain": sealed["chain"], "unit": sealed["unit"],
            "freshness": sealed["freshness"], "evidence_kind": EVIDENCE_KIND, "A": len(sealed["A"]),
            "runs": sealed["runs"], "blocks": sorted(set(sealed["blocks"].values()), key=str),
            "mde_registered": sealed["mde_registered"],
            "sealed": {"record": sealed[RECORD_HASH], "candidate": seals["candidate"], "parent": seals["parent"],
                       "placebo_y": seals["placebo_y"], "placebo_i": seals["placebo_i"],
                       "plan_sha256": seals["plan_sha256"], "twins_sha256": seals["twins_sha256"],
                       "g_acc_sha256": seals["g_acc_sha256"], "donor_corpus": seals["donor_corpus"]},
            "edits": [{"kind": e["kind"], "id": e["id"], "astar_items": len(sealed["plan"]["astar_by_edit"][e["id"]]
                                                                           ["items"])}
                      for e in sealed["plan"]["edits"]]}


def decide(cells, sealed):
    """The round's ``fivebench-execskill-v1-decision`` record from the cell records and the sealed record alone
    (module docstring; plan §2.6)."""
    sealed = verified(sealed, "acceptance-sealed")
    plan = sealed["plan"]
    if plan["decision"] == SMALL:
        require(not cells, "A round that did not run has no cells")
        return not_run(sealed)
    astar, size_a = plan["astar"], len(sealed["A"])
    provenance = _provenance(cells, sealed)  # §9.3, owner #15: the whole schedule, each block from one attempt
    physical = cells
    cells = expanded_cells(cells, sealed)
    reuse = sealed.get("reuse")
    identical = (reuse or {}).get("identical_all", {})
    cells_table = table(cells, identical=identical.get("real", []))
    arms = sorted({a for (a, _) in cells_table if not a.startswith(("withhold:", "restore:"))})
    if reuse is not None:
        arms = sorted({job["arm"] for jobs in schedule(sealed, logical=True).values() for job in jobs
                       if job["set"] == "real" and not job["arm"].startswith(("withhold:", "restore:"))})
    unanswered = shared_unanswered(physical, astar)
    items = [i for i in astar if i not in set(unanswered)]
    if sealed.get("rule") is None:
        require(len(items) > len(set(sealed["blocks"][i] for i in items)), "Too few answered items for the t-test")
    else:  # v2.2 (Codex review MAJOR 1): the smaller floor can leave the t-test no degree of freedom
        short = _too_few_units(sealed, items)
        if short is not None:
            return record("decision-v2-3" if sealed.get("reuse") is not None else "decision", plan["evidence"], {
                **_header(sealed), "A_star": len(astar), "A_star_rooms": plan["astar_rooms"], "analysed": len(items),
                "shared_unanswered": unanswered, "provenance": provenance, "decision": "undetermined",
                "reason": short + "; the run pauses, the batch is consumed but undecided"})
    # §6.5 (Codex review 2026-10-22 #12): the twin-only items (A outside A*) hold S' and twin cells only; they enter
    # tau (``_twins``), J3 (S' runs on A) and the instrument checks over all real cells, never a decision contrast
    outside = twin_only(sealed)
    twin_unanswered = shared_unanswered(physical, outside)
    twin_items = items + [i for i in outside if i not in set(twin_unanswered)]
    in_astar, alone = set(astar), set(outside)
    design = _design(sealed, items)
    pairs = plan["donors"]["pairs"]
    gain, over_sham = (differences(cells_table, CANDIDATE, PARENT, items),
                       differences(cells_table, CANDIDATE, PLACEBO_Y, items))
    sample = (sealed.get("reuse") or {}).get("card_sample")
    card_items = [i for i in items if i in sample["items"]] if sample is not None else items
    if sample is not None and _too_few_units(sealed, card_items) is not None:
        return record("decision-v2-3", plan["evidence"], {
            **_header(sealed), "A_star": len(astar), "A_star_rooms": plan["astar_rooms"], "analysed": len(items),
            "shared_unanswered": unanswered, "provenance": provenance, "decision": "undetermined",
            "reason": "too few answered C instrument sample items for the t-test; the run pauses"})
    card_design = _design(sealed, card_items)
    contrasts = {
        "S'-S": contrast(gain, design=design, whole=size_a, sensitivity=True),
        "S'-P_y": contrast(over_sham, design=design, whole=size_a, sensitivity=True),
        "S'-C": contrast(differences(cells_table, CANDIDATE, CARD, card_items), design=card_design, whole=size_a),
        "S-C": contrast(differences(cells_table, PARENT, CARD, card_items), design=card_design, whole=size_a)}
    if sample is not None:
        for name in ("S'-C", "S-C"):
            contrasts[name].update({"sample": "sealed_C_instrument", "sample_items": card_items,
                                    "sample_size": len(card_items), "whole_batch": None})
    sham = differences(cells_table, PLACEBO_Y, PARENT, items)
    contrasts["P_y-S"] = {**contrast(sham, whole=size_a), "ci95": list(stats_ext.bootstrap_ci(
        sham, clusters=[pairs[i] for i in items])), "by_donor": _by_donor(sham, items, pairs)}
    if PLACEBO_I in arms:
        contrasts["P_i-S"] = contrast(differences(cells_table, PLACEBO_I, PARENT, items), design=design, whole=size_a)
    lo, hi = contrasts["P_y-S"]["ci95"]
    rule = ("harmful_sham_parent_only_2.5pct" if hi < 0 else "helpful_sham_reported" if lo > 0 else "informative")
    if hi < 0 and sealed.get("rule") is not None:  # v2.2 (Codex review MINOR 3): J1 tightens no alpha any more
        rule = "harmful_sham_reported"
    alpha1 = HARMFUL_SHAM_ALPHA if hi < 0 else ALPHA
    first, second = contrasts["S'-S"], contrasts["S'-P_y"]
    j1 = {"p_t": first["p_t"], "alpha": alpha1, "whole_batch": first["whole_batch"],
          "ok": first["p_t"] <= alpha1 and first["whole_batch"] >= float(MIN_WHOLE_BATCH)}
    j2 = {"p_t": second["p_t"], "alpha": ALPHA, "informative": hi >= 0, "ok": hi < 0 or second["p_t"] <= ALPHA}
    gate = sealed.get("rule")
    if gate is not None:  # v2.2: the sealed practical rule replaces J1 and J2 (``rule`` is the placebo reading)
        j1, j2 = _practical(gate, sealed["bench"], gain, over_sham, size_a, first, second)
    faults = _fault_items(cells, sealed)
    j3 = {"fault_items": len(faults), "items": faults, "A": size_a, "share": len(faults) / size_a,
          "max_items": fault_items_max(size_a), "ok": len(faults) * FAULT_SHARE_MAX.denominator
          <= FAULT_SHARE_MAX.numerator * size_a}
    if profiles.is_v28(sealed.get("configuration")):
        j3["informational"] = True
    margin = format_margin(len(astar))
    format_items = astar
    if reuse is not None:
        format_items = [i for i in astar if not request_reuse.interchangeable(
            reuse["signatures"].get("real", {}).get(i, {}).get(CANDIDATE),
            reuse["signatures"].get("real", {}).get(i, {}).get(PARENT), bench=sealed["bench"])]
    violating = {arm: _violating(cells, arm, format_items) for arm in (CANDIDATE, PARENT)}
    j4 = {"S'": len(violating[CANDIDATE]), "S": len(violating[PARENT]), "margin": margin,
          "ok": len(violating[CANDIDATE]) <= len(violating[PARENT]) + margin}
    if reuse is not None:
        j4.update({"compared_items": len(format_items), "interchangeable_items": len(astar) - len(format_items)})
    infrastructure = table(physical) if reuse is not None else cells_table
    measured_arms = sorted({a for (a, i) in infrastructure if i in astar}) if reuse is not None else arms
    infra = {arm: float(stats_ext.infrastructure_share(infrastructure, arm,
                                                       [i for i in astar if (arm, i) in infrastructure]))
             for arm in measured_arms}
    real = [c for c in cells if c["set"] == "real"]
    timing = [c for c in physical if c["set"] == "real"] if reuse is not None else real
    reasoning = sum("reasoning_mismatch" in c["judge"].get("flags", []) for c in timing) / max(1, len(timing))
    timing_arms = sorted({c["arm"] for c in timing}) if reuse is not None else arms
    balance = _balance(physical, timing_arms, sealed)
    gap = _block_gap(physical, sealed)
    j5 = {"infra": infra, "reasoning": reasoning, "unanswered": len(unanswered), "balance": balance,
          "block_gap": gap,
          "ok": max(infra.values(), default=0.0) <= float(INFRA_UNKNOWN_MAX) and reasoning <= float(REASONING_MISMATCH_MAX)
          and len(unanswered) * SHARED_UNANSWERED_MAX.denominator <= SHARED_UNANSWERED_MAX.numerator * len(astar)
          and balance["ok"] and gap["ok"]}
    j5["pause"] = not j5["ok"]  # §13: every broken-instrument case pauses (statistics review 4)
    j6 = _duplicate(cells_table, sealed, items, design)
    j7 = _probe(cells, identical=identical.get("probe", []))
    failed = [name for name, check in (("J1", j1), ("J2", j2), ("J3", j3), ("J4", j4), ("J7", j7))
              if check is not None and not check.get("informational") and not check["ok"]]
    if not j5["ok"] or (j6 is not None and not j6["ok"]):
        verdict = "undetermined"
        reason = "instrument guard failed (%s); the run pauses, the batch is consumed but undecided" % (
            ", ".join(n for n, c in (("J5", j5), ("J6", j6)) if c is not None and not c["ok"]))
    elif failed:
        verdict, reason = "reject", "failed: " + ", ".join(failed)
    else:
        verdict = "accept"
        reason = HARMFUL_WORDING if hi < 0 else "J1-J7 hold"
        if gate is not None:
            reason = "J1 (%s: %+.1f points over the whole batch%s) and J3-J7 hold; placebo label %s" % (
                gate["name"], 100 * first["whole_batch"], "" if j1["practical"] else ", significant", j2["label"])
        if j3.get("informational"):
            reason = reason.replace("J1-J7 hold", "J1, J2 and J4-J7 hold; J3 reported")
            reason = reason.replace("and J3-J7 hold", "and J4-J7 hold; J3 reported")
    calls = (CANDIDATE, PLACEBO_Y) + ((PLACEBO_I,) if PLACEBO_I in arms else ())
    return record("decision-v2-3" if sealed.get("reuse") is not None else "decision", plan["evidence"], {
        **_header(sealed), "A_star": len(astar), "A_star_rooms": plan["astar_rooms"], "analysed": len(items),
        "shared_unanswered": unanswered,
        "donors": {"corpus_sha256": sealed["seals"]["donor_corpus"],
                   "reuse_max": max(plan["donors"]["reuse"].values()) if plan["donors"]["reuse"] else 0},
        "contrasts": contrasts,
        "guards": {"J1": j1, "J2": j2, "J3": j3, "J4_items": j4, "J5": j5, "J6_dup": j6, "J7_meta": j7},
        "placebo_rule": rule,
        "second_call_rates": _rates(cells, calls, "second", astar),
        "repair_call_rates": _rates(cells, calls, "repair", astar),
        "worst_delivery_rates": {arm: sum(c.get("worst_delivery") != DELIVERED for c in real
                                          if c["arm"] == arm and c["task_id"] in in_astar)
                                 / max(1, sum(c["arm"] == arm and c["task_id"] in in_astar for c in real))
                                 for arm in arms},
        "twins_cap": {"max_per_item": max((len(t) for t in plan["twins"].values()), default=0),
                      "not_withheld_items": len(plan["not_withheld"]),
                      "outside_astar": {"items": len(outside), "unanswered": twin_unanswered,
                                        "cells": sum(c["task_id"] in alone for c in real)}},
        "twins": _twins(cells_table, sealed, twin_items), "provenance": provenance,
        "series": series(cells),  # §6.2, ticket PR-F2-1: descriptive, after the verdict, read by no guard
        **({"request_reuse": {"physical_cells": len(physical), "logical_cells": len(cells),
                              "dispatched_by_arm": {arm: sum(c["arm"] == arm for c in physical)
                                                    for arm in sorted({j["arm"] for jobs in schedule(
                                                        sealed, logical=True).values() for j in jobs})},
                              "identical_all": identical,
                              "identical_all_items": sum(len(items) for items in identical.values()),
                              "identical_all_real_astar_items": len(set(identical.get("real", [])) & set(astar)),
                              "cells": [{"arm": c["arm"], "task_id": c["task_id"], "run": c["run"],
                                         "set": c["set"], "reused_from": c["reused_from"]}
                                        for c in cells if c.get("reused_from")]}}
           if sealed.get("reuse") is not None else {}),
        "decision": verdict, "reason": reason})


def _practical(rule, bench, gain, over_sham, size_a, first, second):
    """v2.2's J1 and J2 under a sealed practical rule (module docstring), in exact arithmetic on the per-item
    differences over A* (the whole batch divides by |A|): J1 holds when S' - S reaches the rule's points, or on one of
    its significance benches its smaller points with the one-sided paired t p <= its alpha; J2 labels S' - P_y "content"
    (at least the rule's content points) or "form" and never decides."""
    total, sham = sum(gain), sum(over_sham)
    practical = total * 100 >= rule["gain_points"] * size_a
    significant = (bench in rule["significance_benches"] and first["p_t"] <= rule["alpha"]
                   and total * 100 >= rule["significance_points"] * size_a)
    j1 = {"rule": rule["name"], "whole_batch": first["whole_batch"], "p_t": first["p_t"],
          "gain_points": rule["gain_points"], "practical": practical, "significant": significant,
          "ok": practical or significant}
    j2 = {"rule": rule["name"], "whole_batch": second["whole_batch"], "p_t": second["p_t"], "decides": False,
          "label": "content" if sham * 100 >= rule["content_points"] * size_a else "form", "ok": True}
    return j1, j2


def _by_donor(d, items, pairs):
    """P_y - S per donor cluster (descriptive, §6.1): {donor: {"n", "mean"}}."""
    groups = {}
    for x, item in zip(d, items):
        groups.setdefault(pairs[item], []).append(x)
    return {donor: {"n": len(xs), "mean": float(sum(xs) / len(xs))} for donor, xs in sorted(groups.items())}


def _duplicate(cells_table, sealed, items, design):
    """J6: every registered same-text duplicate pair of this round -- C-S while S has no procedure on the bench,
    S_dup-S when the duplicate arm runs -- each two-sided at 1 % (statistics review 2); None when there is none."""
    if sealed.get("j6_registered") is False:
        require(sealed["bench"] == "zebralogic" and not sealed["dup"], "Only the registered grid control omits J6")
        return None
    pairs = ([(CARD, PARENT)] if sealed["card_is_parent"] else []) + ([(DUP, PARENT)] if sealed["dup"] else [])
    if not pairs:
        return None
    tested = []
    for first, second in pairs:
        sample = (sealed.get("reuse") or {}).get("card_sample") if first == CARD else None
        members = [i for i in items if i in sample["items"]] if sample is not None else items
        d = differences(cells_table, first, second, members)
        p = _two_sided(stats_ext.paired_t(d, **(_design(sealed, members) if sample is not None else design)))
        tested.append({"pair": "%s-%s" % (first, second), "p_two_sided": p, "ok": p >= DUP_ALPHA,
                       **({"sample": "sealed_C_instrument", "sample_items": members, "sample_size": len(members),
                           "runs": sample["runs"]} if sample is not None else {})})
    return {"pairs": tested, "ok": all(t["ok"] for t in tested)}


def write(root, decision):
    """``<root>/decision/decision.json``, written once."""
    path = safe_path(root) / "decision" / "decision.json"
    write_json(path, verified(decision, "decision"))
    return Path(path)


def reproduce(cells, sealed, decision):
    """Whether ``decision`` is what ``decide`` makes from the cell records and the sealed record (plan §8.2). A round
    redone across attempts is reproduced from the records ``round_cells`` reads back by the decision's provenance."""
    return decide(cells, sealed) == decision


def round_cells(unit_root, sealed, decision):
    """The cell records ``decision`` was made from, read back from the accept unit at ``unit_root`` by its provenance
    map (§9.3, owner decision #15): each block's scheduled cells from ``<unit_root>/<attempt>/cells/<cell id>.json``
    of the attempt the map names for it, in schedule order. No cell of a block is read from another attempt. Nothing
    for a round that did not run."""
    sealed, decision = verified(sealed, "acceptance-sealed"), verified(decision, "decision")
    require(decision["sealed"]["record"] == sealed[RECORD_HASH], "The decision of another sealed round")
    provenance, out = decision.get("provenance") or {}, []
    for block, jobs in schedule(sealed).items():
        entry = provenance.get(str(block))
        require(isinstance(entry, dict) and type(entry.get("attempt")) is str,
                "The decision names the unit attempt of block %s" % block)
        folder = safe_path(unit_root) / entry["attempt"] / "cells"
        out += [verified(read_json(folder / (cell_id(sealed["unit"], job["arm"], job["item"], job["run"]) + ".json")),
                         "cell") for job in jobs]
    return out

