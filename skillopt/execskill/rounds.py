"""The rounds of a route-B unit (protocol ``fivebench-execskill-v1``; registration §5.1, §6.2, §6.3, §6.4 J5, §4.4
P3; implementation plan §1 rounds row): copies of ``coevo5.step``'s round helpers (step.py:71-157) with procedure
packages as arms.

- ``run_round`` (step.py:105-121): every cell of a round, its jobs in one seeded interleaved order, never by arm
  (§6.2): the sha256 of (SEED, ``round_tag(unit)`` + ":" + tag, job index). With ``blocks`` the items are dispatched
  block after block, each block in its own seeded order and every cell naming its block; the time between blocks
  (§3.3) is the caller's. An arm is an ``Arm`` or a function of the cell giving one (a placebo arm's per-cell seed,
  ``discourage_tag(unit, cell)``). The training-side rounds use it (the run slice, the examiner's probes, the
  self-test); an acceptance round does not: it runs in ``acceptance.schedule``'s order -- one seeded order per block
  over every cell (registrar decision 2026-10-22, ticket C5-5) -- through ``acceptance.runner``.
- ``tokens`` / ``table_of`` (step.py:124-125): the v2 token per run -- the judge's decision metric (§4.4, ticket A7-2;
  the table ``stats_ext.item_scores`` reads) -- and its frozen bounds tuple, P3's ``unknown_fault`` counted as an
  unknown that is never infrastructure (§6.3, §4.4 P3).
- ``guard`` (step.py:150-157): a round whose parent or controls have more than 10 % infrastructure-unknown cells
  pauses the chain (§6.4 J5). P3's kind is "fault", never infrastructure, so ``unknown_fault`` cells do not count.
- ``shared_unanswered`` (step.py:139-147) on the v2 tokens.

The start-balance guard of §6.2 / J5 is ``acceptance._balance`` alone (registrar decision 2026-10-22, ticket C5-5).
"""
from __future__ import annotations

import hashlib
import json

from skillopt.coevo5.stats import bounds
from skillopt.coevo5.step import answered
from skillopt.continual_eval.core import require

from .cells import Arm, Pause, TrainingStore, cell_id, run_cells
from .outcomes_ext import UNKNOWN_FAULT
from .profiles import SUPPORTED_BENCHES, BENCHES, INFRA_UNKNOWN_MAX, SEED, round_tag
from .units import cell_context

INFRASTRUCTURE = ("infrastructure", "unclassified")  # the frozen guard's kinds (step.py:128-130)


# --------------------------------------------------------------------------------------------------- items
def key(bench, task_id):
    require(bench in SUPPORTED_BENCHES and type(task_id) is str and task_id, "A known bench and a task id")
    return "%s/%s" % (bench, task_id)


def bench_of(item):
    """The bench of an item key ``<bench>/<task id>`` (route B has no forward items, step.py:75-76)."""
    bench, _, task_id = item.partition("/")
    require(bench in SUPPORTED_BENCHES and task_id, "An item key is <bench>/<task id>")
    return bench


def _order(values, tag):
    return sorted(values, key=lambda v: hashlib.sha256(json.dumps([SEED, tag, v]).encode()).hexdigest())


def pool_tasks(setting, benches):
    return {key(b, t["task_id"]): {"public": t["public"], "private": t["private"], "task_id": t["task_id"]}
            for b in benches for t in setting.pools[b]}


# ---------------------------------------------------------------------------------------------- the cells
def run_round(setting, attempt, endpoint, unit, arms, schedule, tasks, *, tag, blocks=None, store=None):
    """Every cell of a round. ``arms``: {arm: Arm, or a function of the cell giving its Arm}; ``schedule``: {arm:
    [(item, runs)]}; ``tasks``: {item: {"public", "private"}}; ``blocks``: {item: block} or None; ``store``: the
    attempt's ``TrainingStore`` by default. Returns {(arm, item): [record per run]}; a stop of the run pauses the unit
    after the cell's record is written."""
    jobs = []
    for arm, plan in schedule.items():
        for item, runs in plan:
            for run in range(runs):
                cell = {"id": cell_id(unit, arm, item, run), "unit": unit, "arm": arm, "benchmark": bench_of(item),
                        "task_id": item, "run": run}
                if blocks is not None:
                    cell["block"] = str(blocks[item])
                chosen = arms[arm] if isinstance(arms[arm], Arm) else arms[arm](cell)
                require(isinstance(chosen, Arm), "An arm is an Arm or gives one per cell")
                jobs.append((cell, {"public": tasks[item]["public"], "private": tasks[item]["private"]}, chosen))
    context = cell_context(setting, attempt, endpoint)
    store = store or TrainingStore(attempt)
    done = []
    for block in sorted({cell.get("block") for cell, _, _ in jobs}, key=str):
        members = [job for job in jobs if job[0].get("block") == block]
        order = round_tag(unit) + ":" + tag + ("" if block is None else ":" + block)
        members = [members[i] for i in _order(list(range(len(members))), order)]
        done += zip(members, run_cells(context, members, workers=setting.workers, store=store))
    out = {}
    for (cell, _, _), found in sorted(done, key=lambda pair: (pair[0][0]["arm"], pair[0][0]["task_id"],
                                                              pair[0][0]["run"])):
        out.setdefault((cell["arm"], cell["task_id"]), []).append(found)
    return out


def _token(found):
    return found["judge"]["v2"]["token"]


def tokens(cells):
    """{(arm, item): [v2 token per run]}."""
    return {k: [_token(r) for r in v] for k, v in cells.items()}


def table_of(cells):
    """{(arm, item): (L, H, unknown runs, runs, infrastructure-unknown runs)} of the v2 tokens (frozen
    ``stats.bounds``). P3's ``unknown_fault`` enters as ``unknown_artifact``: an unknown (wrong on L, right on H) that
    is never infrastructure (§4.4 P3), so the frozen ``unknown_share(..., infrastructure_only=True)`` agrees with
    ``guard``."""
    return bounds({k: ["unknown_artifact" if t == UNKNOWN_FAULT else t for t in v] for k, v in tokens(cells).items()})


def _infrastructure(records):
    return sum(r["final"]["outcome"] == "unknown" and r["final"]["kind"] in INFRASTRUCTURE for r in records)


def shared_unanswered(cells, items):
    """The items on which no arm of the round that scheduled them got any reply (step.py:139-147 on v2 tokens): every
    cell unknown and none delivered a reply. Such an item leaves every criterion of the round; the guard still counts
    its cells."""
    records = {}
    for (_, item), found in cells.items():
        records.setdefault(item, []).extend(found)
    return sorted(i for i in set(items) if records.get(i) and all(
        _token(r) == "unknown" and not answered(r) for r in records[i]))


def guard(cells, arms, unit):
    """§6.4 J5: a round whose ``arms`` (the parent and the controls) have more than 10 % infrastructure-unknown cells
    is infrastructure-incomplete: the chain pauses. A P3 ``unknown_fault`` (kind "fault") never counts."""
    for arm in arms:
        records = [r for (a, _), rs in cells.items() if a == arm for r in rs]
        if records and _infrastructure(records) > INFRA_UNKNOWN_MAX * len(records):
            raise Pause("infrastructure_incomplete", "%s: %d of %d cells" % (arm, _infrastructure(records),
                                                                             len(records)), unit)

