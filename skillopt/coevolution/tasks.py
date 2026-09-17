"""Finite cross-application Python policy migrations, not public/domain benchmarks.

Forty-eight contracts are paired requests on 24 operation clusters. The legal
input universe is stated publicly and exhaustively checked, including preserved
archives and caller nonmutation. Handwritten native implementations and a
separate trusted procedural oracle are compared before any model responses.
"""

from __future__ import annotations

import itertools
import json
import textwrap
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from skillopt.coevolution.executor import AVAILABLE_BUILTINS
from skillopt.validator_pilot.tasks import Task

VERSION = "coevolution-finite-applications-v1"
CONTEXTS = ("commerce", "tabular_reporting", "policy_routing")
MODES = ("local-update", "full-policy-replacement")
PHASES = ("learn0", "gate0", "learn1", "gate1", "holdout", "holdout", "holdout", "holdout")
DOMAIN = {
    "items": [[], [0, 1, 2], [3, 1, -1, 2, -1], [2, -1, -1, 0, 1], [2, 2, 0, 1]],
    "limit": [2, 4],
    "enabled": [False, True],
    "priority": [False, True],
}
PUBLIC_INDICES = (11, 16)


@dataclass(frozen=True)
class Spec:
    context: str
    index: int
    name: str
    old_contract: str
    local_contract: str
    replacement_contract: str
    legacy: str
    local: str
    replacement: str


SPECS: list[Spec] = []


def add(context, index, name, old_contract, local_contract, replacement_contract, legacy, local, replacement):
    SPECS.append(
        Spec(
            context,
            index,
            name,
            old_contract,
            local_contract,
            replacement_contract,
            textwrap.dedent(legacy).strip(),
            textwrap.dedent(local).strip(),
            textwrap.dedent(replacement).strip(),
        )
    )


add(
    "commerce",
    0,
    "tiered_checkout",
    "Each signed order amount a is quoted as max(0,a-1) when a>=limit, otherwise max(0,a).",
    "Only when enabled, for each original amount a>=limit OR priority=True, subtract min(old quoted amount,2+int(priority)) from that row's quote. Other rows retain their old quote.",
    "Ignore all old discounts and eligibility flags. Charge max(0,2*a+int(priority)) for every original amount a; enabled no longer controls collection.",
    "return [max(0, a - (1 if a >= limit else 0)) for a in items]",
    "return [v - min(v, 2 + int(priority)) if enabled and (a >= limit or priority) else v for a, v in zip(items, old)]",
    "return [max(0, 2 * a + int(priority)) for a in items]",
)

add(
    "commerce",
    1,
    "bounded_settlement",
    "Start balance=limit. Apply signed amounts in order, clamping balance to [0,2*limit] after EACH amount. Report the balance after each event.",
    "When enabled, double only positive amounts before replay; when priority is also true use upper cap 3*limit instead of 2*limit. Retain the starting balance, zero floor, and event order.",
    "Start balance=0 and replay every raw signed amount without any cap or floor. Report every resulting balance; enabled and priority are obsolete.",
    """balance = limit
out = []
for a in items:
    balance = max(0, min(2 * limit, balance + a))
    out.append(balance)
return out""",
    """balance = limit
out = []
for a in items:
    delta = a * 2 if enabled and a > 0 else a
    cap = (3 if enabled and priority else 2) * limit
    balance = max(0, min(cap, balance + delta))
    out.append(balance)
return out""",
    """balance = 0
out = []
for a in items:
    balance += a
    out.append(balance)
return out""",
)

add(
    "commerce",
    2,
    "refund_waterfall",
    "Allocate a total refund budget=limit to max(0,a) claims in original order. Each gets min(remaining budget,claim); decrement the budget. Output allocations at original indices.",
    "When enabled AND priority, allocate in reverse claim order while keeping output indices in original order. Otherwise keep the old waterfall.",
    "Replace demand-based allocation with equal integer shares: q,r=divmod(limit,number of claims), the first r positions get q+1, all others q. Empty input yields an empty vector. Negative/zero amounts and both flags do not affect shares.",
    """budget = limit
out = []
for a in items:
    used = min(budget, max(0, a))
    out.append(used)
    budget -= used
return out""",
    """out = [0] * len(items)
budget = limit
order = list(range(len(items)))
if enabled and priority:
    order.reverse()
for i in order:
    out[i] = min(budget, max(0, items[i]))
    budget -= out[i]
return out""",
    """if not items:
    return []
q = limit // len(items)
r = limit % len(items)
return [q + int(i < r) for i in range(len(items))]""",
)

add(
    "commerce",
    3,
    "shipment_partition",
    "Assign nonnegative weights max(0,a) in order to numbered batches starting at 1. Before adding an item, if the current batch already has positive weight and adding it exceeds limit, start a new batch. Oversized first items are allowed. Emit each item's batch number.",
    "When enabled, change capacity to limit+1, or limit+2 when priority. Repartition the entire CURRENT stream with the same positive-weight rollover rule; inactive requests retain capacity=limit.",
    "Discard weight capacity. Group consecutive input positions in pairs: positions 0,1 go to batch1; 2,3 to batch2. All values and flags are ignored for current partitioning.",
    """batch, weight = 1, 0
out = []
for a in items:
    value = max(0, a)
    if weight > 0 and weight + value > limit:
        batch += 1
        weight = 0
    weight += value
    out.append(batch)
return out""",
    """cap = limit + (1 + int(priority) if enabled else 0)
batch, weight = 1, 0
out = []
for a in items:
    value = max(0, a)
    if weight > 0 and weight + value > cap:
        batch += 1
        weight = 0
    weight += value
    out.append(batch)
return out""",
    "return [i // 2 + 1 for i in range(len(items))]",
)

add(
    "commerce",
    4,
    "credit_replay",
    "Start credit=limit. For each signed debit a, set credit=max(0,min(2*limit,credit-a)) and emit remaining credit. Negative amounts replenish credit.",
    "When enabled, double negative replenishments only; when priority is also true the ceiling becomes 3*limit. Keep positive debit semantics, the zero floor, starting credit and ordered replay.",
    "Remove carry-over completely. Each input independently yields max(0,limit-a), without the old upper ceiling or flags.",
    """credit = limit
out = []
for a in items:
    credit = max(0, min(2 * limit, credit - a))
    out.append(credit)
return out""",
    """credit = limit
out = []
for a in items:
    debit = 2 * a if enabled and a < 0 else a
    cap = limit * (3 if enabled and priority else 2)
    credit = max(0, min(cap, credit - debit))
    out.append(credit)
return out""",
    "return [max(0, limit - a) for a in items]",
)

add(
    "commerce",
    5,
    "cumulative_tax",
    "Tax each row independently as ceil(max(0,a)/limit), using exact integer arithmetic. Emit row taxes.",
    "When enabled, tax the running cumulative nonnegative base instead, emitting INCREMENTS of cumulative tax so the taxes telescope. Priority increases the divisor to limit+1 only for enabled collection; inactive requests retain independent row taxes.",
    "Replace proportional taxation by a flat unit levy for each strictly positive amount, zero otherwise. Ignore limit and flags.",
    "return [(max(0, a) + limit - 1) // limit for a in items]",
    """if not enabled:
    return list(old)
divisor = limit + int(priority)
base, prior_tax = 0, 0
out = []
for a in items:
    base += max(0, a)
    tax = (base + divisor - 1) // divisor
    out.append(tax - prior_tax)
    prior_tax = tax
return out""",
    "return [int(a > 0) for a in items]",
)

add(
    "commerce",
    6,
    "proportional_pool",
    "Allocate budget=limit proportionally to weights=max(0,a). Floor exact quotas and distribute residual units by descending remainder, ties by earliest index. If total weight is zero return all zeros.",
    "Retain proportional allocation; when enabled AND priority change only residual tie-breaking to LATEST index. Keep budget, floor quotas, zero-weight behavior and original output positions unchanged.",
    "Use equal integer shares across all positions instead of weights: first limit%N positions get limit//N+1, remaining get limit//N. Empty input returns empty. Ignore amounts and flags.",
    """weights = [max(0, a) for a in items]
total = sum(weights)
if not total:
    return [0] * len(items)
out = [limit * a // total for a in weights]
order = sorted(range(len(items)), key=lambda i: (-(limit * weights[i] % total), i))
for i in order[:limit - sum(out)]:
    out[i] += 1
return out""",
    """weights = [max(0, a) for a in items]
total = sum(weights)
if not total:
    return [0] * len(items)
out = [limit * a // total for a in weights]
order = sorted(range(len(items)), key=lambda i: (-(limit * weights[i] % total), -i if enabled and priority else i))
for i in order[:limit - sum(out)]:
    out[i] += 1
return out""",
    """if not items:
    return []
return [limit // len(items) + int(i < limit % len(items)) for i in range(len(items))]""",
)

add(
    "commerce",
    7,
    "cancellation_stack",
    "Positive amounts append an open order; negative amounts cancel the MOST RECENT open order, if any. Zero is a no-op. Emit sum of open amounts after each event.",
    "When enabled AND priority, a cancellation removes the OLDEST open order instead. Preserve positive orders, zeros, unmatched-cancel no-ops, and event-aligned outputs.",
    "Every negative event now cancels ALL open orders. Positive appends and zero no-ops remain; limit and flags do not affect this replacement policy.",
    """pending = []
out = []
for a in items:
    if a > 0:
        pending.append(a)
    elif a < 0 and pending:
        pending.pop()
    out.append(sum(pending))
return out""",
    """pending = []
out = []
for a in items:
    if a > 0:
        pending.append(a)
    elif a < 0 and pending:
        pending.pop(0 if enabled and priority else -1)
    out.append(sum(pending))
return out""",
    """pending = []
out = []
for a in items:
    if a > 0:
        pending.append(a)
    elif a < 0:
        pending = []
    out.append(sum(pending))
return out""",
)

add(
    "tabular_reporting",
    0,
    "rolling_aggregation",
    "At each row emit the sum of the last limit input POSITIONS, including negative and zero values.",
    "When enabled exclude negative values from the aggregate but still count their positions in the window. Priority additionally widens an enabled window to limit+1. Inactive reports keep the old rule.",
    "Replace sliding windows by the complete signed prefix sum at every row; flags and limit no longer affect current aggregates.",
    "return [sum(items[max(0, i - limit + 1):i + 1]) for i in range(len(items))]",
    """width = limit + int(enabled and priority)
out = []
for i in range(len(items)):
    window = items[max(0, i - width + 1):i + 1]
    out.append(sum(a for a in window if not enabled or a >= 0))
return out""",
    "return [sum(items[:i + 1]) for i in range(len(items))]",
)

add(
    "tabular_reporting",
    1,
    "run_length_annotation",
    "For every row emit its length so far within the current contiguous run of equal values; a different value resets length to 1.",
    "When enabled, zero rows do NOT alter the last nonzero run state. Emit 0 at skipped zero rows, or the current run length when priority; nonzero rows compare with the last nonzero value. Inactive behavior stays unchanged.",
    "Replace contiguous-run counting by cumulative occurrence counts of each signed value over the whole prefix, including zeros.",
    """out = []
previous = None
count = 0
for a in items:
    count = count + 1 if a == previous else 1
    previous = a
    out.append(count)
return out""",
    """out = []
previous = None
count = 0
for a in items:
    if enabled and a == 0:
        out.append(count if priority else 0)
        continue
    count = count + 1 if a == previous else 1
    previous = a
    out.append(count)
return out""",
    """counts = {}
out = []
for a in items:
    counts[a] = counts.get(a, 0) + 1
    out.append(counts[a])
return out""",
)

add(
    "tabular_reporting",
    2,
    "dense_rank_column",
    "Dense-rank distinct signed values in ascending order starting at 1; ties get the same rank, output stays in row order.",
    "When enabled rank by absolute value, ascending normally but descending when priority. Equal magnitudes tie. Inactive requests retain signed ascending ranks.",
    "Discard numeric ordering. Dense ranks follow the FIRST appearance of each signed value, starting at 1; duplicates retain their first rank.",
    """unique = sorted(set(items))
return [unique.index(a) + 1 for a in items]""",
    """keys = [abs(a) if enabled else a for a in items]
unique = sorted(set(keys), reverse=enabled and priority)
return [unique.index(a) + 1 for a in keys]""",
    """seen = []
out = []
for a in items:
    if a not in seen:
        seen.append(a)
    out.append(seen.index(a) + 1)
return out""",
)

add(
    "tabular_reporting",
    3,
    "duplicate_provenance",
    "Emit each signed value's cumulative occurrence number in original row order.",
    "When enabled, group by absolute value when priority and by max(0,value) otherwise, retaining original rows and counting canonical keys. Inactive requests retain signed-value keys.",
    "Replace duplicate annotations by 1-based row ordinals; all values and flags become irrelevant.",
    """counts = {}
out = []
for a in items:
    counts[a] = counts.get(a, 0) + 1
    out.append(counts[a])
return out""",
    """counts = {}
out = []
for a in items:
    key = (abs(a) if priority else max(0, a)) if enabled else a
    counts[key] = counts.get(key, 0) + 1
    out.append(counts[key])
return out""",
    "return list(range(1, len(items) + 1))",
)

add(
    "tabular_reporting",
    4,
    "bounded_smoothing",
    "Clamp each signed cell independently to [-limit,+limit].",
    "When enabled, first add the PREVIOUS raw input cell (zero before the first row), or the NEXT raw cell when priority (zero after the last row), then clamp to the same bounds. Do not use already smoothed cells. Inactive behavior is unchanged.",
    "Replace smoothing and clamping by a nonnegative indicator: 1 when the raw cell is >=0, otherwise 0.",
    "return [max(-limit, min(limit, a)) for a in items]",
    """out = []
for i, a in enumerate(items):
    neighbor = i + 1 if priority else i - 1
    extra = items[neighbor] if enabled and 0 <= neighbor < len(items) else 0
    out.append(max(-limit, min(limit, a + extra)))
return out""",
    "return [int(a >= 0) for a in items]",
)

add(
    "tabular_reporting",
    5,
    "sign_pivot_counts",
    "Group cells by sign (-1,0,1) and emit that sign group's prefix count at each original position.",
    "When enabled, a zero cell inherits the latest nonzero sign (initially 0). Priority changes only inherited-zero rows: they display the existing count without incrementing it. Nonzero rows still increment their sign group.",
    "Replace prefix sign grouping by FINAL frequencies of absolute values: each row displays the total number of rows with its magnitude.",
    """counts = {-1: 0, 0: 0, 1: 0}
out = []
for a in items:
    sign = int(a > 0) - int(a < 0)
    counts[sign] += 1
    out.append(counts[sign])
return out""",
    """counts = {-1: 0, 0: 0, 1: 0}
last = 0
out = []
for a in items:
    sign = int(a > 0) - int(a < 0)
    if enabled and a == 0:
        sign = last
    elif a != 0:
        last = sign
    if not (enabled and priority and a == 0):
        counts[sign] += 1
    out.append(counts[sign])
return out""",
    "return [sum(abs(b) == abs(a) for b in items) for a in items]",
)

add(
    "tabular_reporting",
    6,
    "lagged_difference",
    "Emit raw cell minus the previous raw cell, using zero before the first row.",
    "When enabled use lag=limit, except priority uses lag=2. Missing earlier positions still contribute zero. Inactive requests retain lag=1; keep signed values and row alignment.",
    "Replace differencing by absolute magnitude of each independent raw cell.",
    "return [a - (items[i - 1] if i else 0) for i, a in enumerate(items)]",
    """lag = (2 if priority else limit) if enabled else 1
return [a - (items[i - lag] if i >= lag else 0) for i, a in enumerate(items)]""",
    "return [abs(a) for a in items]",
)

add(
    "tabular_reporting",
    7,
    "directional_imputation",
    "Replace zero cells by the latest preceding NONZERO raw value, initially limit. Nonzero values remain unchanged.",
    "When enabled AND priority, fill zeros with the nearest following NONZERO raw value if one exists; otherwise fall back to the old preceding-value rule. Never let imputed cells become raw evidence. Other settings retain old behavior.",
    "Replace every zero independently by limit; leave nonzero values unchanged and ignore neighbors and flags.",
    """last = limit
out = []
for a in items:
    if a != 0:
        last = a
    out.append(last)
return out""",
    """last = limit
out = []
for i, a in enumerate(items):
    if a != 0:
        last = a
        out.append(a)
    elif enabled and priority:
        following = [b for b in items[i + 1:] if b != 0]
        out.append(following[0] if following else last)
    else:
        out.append(last)
return out""",
    "return [a if a != 0 else limit for a in items]",
)

add(
    "policy_routing",
    0,
    "threshold_dispatch",
    "Signal<=0 routes to 0; positive signal<limit routes to 1; signal>=limit routes to 2.",
    "When enabled AND priority add two exceptions: exact signal==limit routes to 3, negative signals route to 4. Keep zero and all other routing boundaries unchanged.",
    "Replace thresholds by parity: zero routes to 0, nonzero even magnitude routes to 2, nonzero odd magnitude routes to 1. Ignore limit and flags.",
    "return [0 if a <= 0 else (1 if a < limit else 2) for a in items]",
    "return [3 if enabled and priority and a == limit else (4 if enabled and priority and a < 0 else v) for a, v in zip(items, old)]",
    "return [0 if a == 0 else (2 if abs(a) % 2 == 0 else 1) for a in items]",
)

add(
    "policy_routing",
    1,
    "ordered_rule_priority",
    "First match wins: negative->9; even->2; value>=limit->3; otherwise->1. Preserve the listed order.",
    "When enabled AND priority, move the >=limit rule BEFORE the even rule, but keep the negative-deny rule first. Other settings preserve old precedence.",
    "Discard the old rules. Every odd signed value routes to 7 and every even value to 8, including negatives and zero.",
    "return [9 if a < 0 else (2 if a % 2 == 0 else (3 if a >= limit else 1)) for a in items]",
    "return [9 if a < 0 else (3 if enabled and priority and a >= limit else (2 if a % 2 == 0 else (3 if a >= limit else 1))) for a in items]",
    "return [7 if a % 2 else 8 for a in items]",
)

add(
    "policy_routing",
    2,
    "sticky_session_route",
    "Start route=0. Every nonzero signal sets route=abs(signal)%3+1; zero retains the existing route. Emit route after each signal.",
    "When enabled, negative signals clear route to 0 instead of choosing a route. In enabled priority mode only, a zero seen while route=0 selects fallback route=2. Positive signals and ordinary sticky zeros retain old behavior.",
    "Remove session memory: each nonzero signal independently routes to abs(signal)%2+1; zero routes to 0.",
    """route = 0
out = []
for a in items:
    if a != 0:
        route = abs(a) % 3 + 1
    out.append(route)
return out""",
    """route = 0
out = []
for a in items:
    if enabled and a < 0:
        route = 0
    elif enabled and priority and a == 0 and route == 0:
        route = 2
    elif a != 0:
        route = abs(a) % 3 + 1
    out.append(route)
return out""",
    "return [abs(a) % 2 + 1 if a != 0 else 0 for a in items]",
)

add(
    "policy_routing",
    3,
    "admission_tokens",
    "Start used=0. Negative signals reset used=0 and emit9. Nonnegative demand is accepted iff used+demand<=limit; accepted demand consumes tokens and emits1, rejected emits0 without consumption.",
    "When enabled, negative signals release exactly one used token (floor zero) instead of resetting all usage, still emitting9. Priority additionally makes enabled zero-demand requests emit2 without consuming tokens. Keep ordinary admission and rejection behavior.",
    "Disable token accounting. Nonnegative signals emit1 and negative signals emit0 independently; limits and flags are obsolete.",
    """used = 0
out = []
for a in items:
    if a < 0:
        used = 0
        out.append(9)
    elif used + a <= limit:
        used += a
        out.append(1)
    else:
        out.append(0)
return out""",
    """used = 0
out = []
for a in items:
    if a < 0:
        used = max(0, used - 1) if enabled else 0
        out.append(9)
    elif enabled and priority and a == 0:
        out.append(2)
    elif used + a <= limit:
        used += a
        out.append(1)
    else:
        out.append(0)
return out""",
    "return [int(a >= 0) for a in items]",
)

add(
    "policy_routing",
    4,
    "circuit_recovery",
    "Track failures starting0. Negative signals increment failures; positive resets failures to0; zero leaves it unchanged. Emit int(failures>=limit) after each signal.",
    "Only when enabled AND priority, require two consecutive positive signals to clear failures. Negative resets the positive streak and increments failures; zero breaks the streak without changing failures. Retain the threshold and aligned binary outputs.",
    "Replace accumulated failure state by direct classification: negative emits1, all other signals emit0.",
    """failures = 0
out = []
for a in items:
    if a < 0:
        failures += 1
    elif a > 0:
        failures = 0
    out.append(int(failures >= limit))
return out""",
    """failures, streak = 0, 0
out = []
for a in items:
    if a < 0:
        failures += 1
        streak = 0
    elif a > 0:
        streak += 1
        if not (enabled and priority) or streak >= 2:
            failures = 0
    else:
        streak = 0
    out.append(int(failures >= limit))
return out""",
    "return [int(a < 0) for a in items]",
)

add(
    "policy_routing",
    5,
    "version_pin_selection",
    "Start version0. Positive signals select max(current,signal); negative decrements current by1, floored at0; zero keeps it. Emit version after each event.",
    "When enabled, ignore positive candidate versions above limit. Priority additionally prevents negative rollback while enabled. Accepted positive maxima and zeros keep their original semantics.",
    "Remove version memory and rollback semantics: emit abs(signal) independently at every event.",
    """version = 0
out = []
for a in items:
    if a > 0:
        version = max(version, a)
    elif a < 0:
        version = max(0, version - 1)
    out.append(version)
return out""",
    """version = 0
out = []
for a in items:
    if a > 0 and not (enabled and a > limit):
        version = max(version, a)
    elif a < 0 and not (enabled and priority):
        version = max(0, version - 1)
    out.append(version)
return out""",
    "return [abs(a) for a in items]",
)

add(
    "policy_routing",
    6,
    "dispatch_backpressure",
    "Positive signals enqueue a job with that priority at the tail; negative dequeues the head if present; zero does nothing. Emit current queue head, or0 if empty, after every event.",
    "When enabled AND priority, positive arrivals are inserted by descending priority (stable for equal priorities). Dequeue still removes the head; preserve zero/no-job semantics and event order.",
    "Discard the queue. Emit the current positive signal itself, or0 for nonpositive signals.",
    """queue = []
out = []
for a in items:
    if a > 0:
        queue.append(a)
    elif a < 0 and queue:
        queue.pop(0)
    out.append(queue[0] if queue else 0)
return out""",
    """queue = []
out = []
for a in items:
    if a > 0:
        queue.append(a)
        if enabled and priority:
            queue.sort(reverse=True)
    elif a < 0 and queue:
        queue.pop(0)
    out.append(queue[0] if queue else 0)
return out""",
    "return [max(0, a) for a in items]",
)

add(
    "policy_routing",
    7,
    "permission_dependencies",
    "Maintain a set of granted positive IDs, initially empty. Positive signals grant themselves; negative revokes abs(signal); zero does nothing. Emit sum of granted IDs after each event.",
    "When enabled, revoking ID k revokes ALL granted IDs<=k. When enabled AND priority, granting ID2 also grants ID1. Other grants, duplicate grants, zero and event alignment retain old behavior.",
    "Replace persistent grants by per-request authorization: output the positive signal or0; all earlier grants and flags become irrelevant.",
    """grants = set()
out = []
for a in items:
    if a > 0:
        grants.add(a)
    elif a < 0:
        grants.discard(abs(a))
    out.append(sum(grants))
return out""",
    """grants = set()
out = []
for a in items:
    if a > 0:
        grants.add(a)
        if enabled and priority and a == 2:
            grants.add(1)
    elif a < 0:
        if enabled:
            grants = {k for k in grants if k > abs(a)}
        else:
            grants.discard(abs(a))
    out.append(sum(grants))
return out""",
    "return [max(0, a) for a in items]",
)


def _allocation(weights, budget, reverse=False):
    """Trusted independent selection oracle, not source execution."""
    if not sum(weights):
        return [0 for _ in weights]
    denominator = sum(weights)
    quotients = [divmod(budget * weight, denominator) for weight in weights]
    answer = [pair[0] for pair in quotients]
    eligible = list(range(len(weights)))
    for _ in range(budget - sum(answer)):
        chosen = max(eligible, key=lambda i: (quotients[i][1], i if reverse else -i))
        answer[chosen] += 1
        eligible.remove(chosen)
    return answer


def _commerce(index, data, policy):
    xs, limit = data["items"], data["limit"]
    active = policy == "local-update" and data["enabled"]
    priority = active and data["priority"]
    replace = policy == "full-policy-replacement"
    if index == 0:
        answer = []
        for x in xs:
            if replace:
                value = 2 * x + int(data["priority"])
            else:
                value = max(0, x - int(x >= limit))
                if active and (x >= limit or data["priority"]):
                    value -= min(value, 2 + int(data["priority"]))
            answer.append(max(value, 0))
        return answer
    if index in (1, 4):
        if replace and index == 4:
            return [max(limit - x, 0) for x in xs]
        state, answer = (0 if replace else limit), []
        upper = limit * (3 if priority else 2)
        for x in xs:
            change = x if index == 1 else -x
            if active and change > 0:
                change *= 2
            state += change
            if not replace:
                if state < 0:
                    state = 0
                elif state > upper:
                    state = upper
            answer.append(state)
        return answer
    if index in (2, 6) and replace:
        return [limit // len(xs) + (1 if i < limit % len(xs) else 0) for i in range(len(xs))]
    if index == 2:
        answer, remaining = [0] * len(xs), limit
        order = range(len(xs) - 1, -1, -1) if priority else range(len(xs))
        for i in order:
            demand = max(xs[i], 0)
            allocated = demand if demand <= remaining else remaining
            remaining -= allocated
            answer[i] = allocated
        return answer
    if index == 3:
        if replace:
            return [(i + 2) // 2 for i in range(len(xs))]
        capacity = limit + (1 + int(data["priority"]) if active else 0)
        groups, mass, answer = 1, 0, []
        for x in xs:
            next_mass = mass + max(x, 0)
            if mass != 0 and next_mass > capacity:
                groups += 1
                mass = max(x, 0)
            else:
                mass = next_mass
            answer.append(groups)
        return answer
    if index == 5:
        if replace:
            return [1 if x > 0 else 0 for x in xs]
        if not active:
            return [max(x, 0) // limit + int(max(x, 0) % limit != 0) for x in xs]
        divisor = limit + int(data["priority"])
        cumulative = [sum(max(x, 0) for x in xs[: i + 1]) for i in range(len(xs))]
        bills = [value // divisor + int(value % divisor != 0) for value in cumulative]
        return [value - (bills[i - 1] if i else 0) for i, value in enumerate(bills)]
    if index == 6:
        return _allocation([max(x, 0) for x in xs], limit, priority)
    if index == 7:
        orders, answer = [], []
        for x in xs:
            if x > 0:
                orders = orders + [x]
            elif x < 0:
                if replace:
                    orders = []
                elif orders:
                    orders = orders[1:] if priority else orders[:-1]
            answer.append(sum(orders))
        return answer
    raise ValueError("unknown commerce operation")


def _reporting(index, data, policy):
    xs, limit = data["items"], data["limit"]
    active = policy == "local-update" and data["enabled"]
    priority = active and data["priority"]
    replace = policy == "full-policy-replacement"
    if index == 0:
        width = len(xs) + 1 if replace else limit + int(priority)
        answer = []
        for end in range(len(xs)):
            selected = [x for i, x in enumerate(xs) if end - width < i <= end]
            answer.append(sum(x for x in selected if not active or x >= 0))
        return answer
    if index == 1:
        if replace:
            return [xs[: i + 1].count(x) for i, x in enumerate(xs)]
        effective, answer = [], []
        for x in xs:
            if active and x == 0:
                if not priority:
                    answer.append(0)
                    continue
            else:
                effective.append(x)
            run = 0
            for prior in reversed(effective):
                if prior != effective[-1]:
                    break
                run += 1
            answer.append(run)
        return answer
    if index == 2:
        if replace:
            first_seen = list(dict.fromkeys(xs))
            return [first_seen.index(x) + 1 for x in xs]
        keys = [abs(x) if active else x for x in xs]
        answer = []
        for x in keys:
            predecessors = {y for y in keys if (y > x if priority else y < x)}
            answer.append(len(predecessors) + 1)
        return answer
    if index == 3:
        if replace:
            return [i + 1 for i, _ in enumerate(xs)]
        canonical = [abs(x) if data["priority"] else max(x, 0) for x in xs] if active else list(xs)
        return [canonical[: i + 1].count(x) for i, x in enumerate(canonical)]
    if index == 4:
        if replace:
            return [0 if x < 0 else 1 for x in xs]
        answer = []
        for i, x in enumerate(xs):
            other = i + (1 if data["priority"] else -1)
            value = x + (xs[other] if active and 0 <= other < len(xs) else 0)
            answer.append(-limit if value < -limit else (limit if value > limit else value))
        return answer
    if index == 5:
        if replace:
            magnitudes = [abs(x) for x in xs]
            return [magnitudes.count(value) for value in magnitudes]
        counts, previous, answer = {}, 0, []
        for x in xs:
            sign = -1 if x < 0 else (1 if x > 0 else 0)
            key = previous if active and x == 0 else sign
            counts[key] = counts.get(key, 0) + (0 if priority and x == 0 else 1)
            answer.append(counts[key])
            if x:
                previous = sign
        return answer
    if index == 6:
        if replace:
            return [abs(x) for x in xs]
        distance = (2 if data["priority"] else limit) if active else 1
        shifted = [0] * distance + xs
        return [x - shifted[i] for i, x in enumerate(xs)]
    if index == 7:
        answer = []
        for i, x in enumerate(xs):
            if x != 0:
                answer.append(x)
                continue
            prior = [value for value in xs[:i] if value != 0]
            after = [value for value in xs[i + 1 :] if value != 0]
            if replace:
                answer.append(limit)
            elif priority and after:
                answer.append(after[0])
            else:
                answer.append(prior[-1] if prior else limit)
        return answer
    raise ValueError("unknown reporting operation")


def _routing(index, data, policy):
    xs, limit = data["items"], data["limit"]
    active = policy == "local-update" and data["enabled"]
    priority = active and data["priority"]
    replace = policy == "full-policy-replacement"
    if index == 0:
        answer = []
        for x in xs:
            if replace:
                value = 0 if x == 0 else 2 - abs(x) % 2
            elif priority and x < 0:
                value = 4
            elif priority and x == limit:
                value = 3
            else:
                value = 0 if x <= 0 else 1 + int(x >= limit)
            answer.append(value)
        return answer
    if index == 1:
        answer = []
        for x in xs:
            if replace:
                answer.append(8 - x % 2)
                continue
            tests = [(x < 0, 9), (x % 2 == 0, 2), (x >= limit, 3), (True, 1)]
            if priority:
                tests[1], tests[2] = tests[2], tests[1]
            answer.append(next(value for matches, value in tests if matches))
        return answer
    if index == 2:
        state, answer = 0, []
        for x in xs:
            if replace:
                state = 0 if x == 0 else 1 + abs(x) % 2
            elif active and x < 0:
                state = 0
            elif priority and x == 0 and state == 0:
                state = 2
            elif x:
                state = 1 + abs(x) % 3
            answer.append(state)
        return answer
    if index == 3:
        remaining, answer = limit, []
        for x in xs:
            if replace:
                answer.append(0 if x < 0 else 1)
            elif x < 0:
                remaining = min(limit, remaining + 1) if active else limit
                answer.append(9)
            elif priority and x == 0:
                answer.append(2)
            elif x <= remaining:
                remaining -= x
                answer.append(1)
            else:
                answer.append(0)
        return answer
    if index == 4:
        if replace:
            return [int(x < 0) for x in xs]
        failures, positives, answer = 0, 0, []
        for x in xs:
            positives = positives + 1 if x > 0 else 0
            if x < 0:
                failures += 1
            if x > 0 and positives >= (2 if priority else 1):
                failures = 0
            answer.append(int(failures >= limit))
        return answer
    if index == 5:
        selected, answer = 0, []
        for x in xs:
            if replace:
                selected = abs(x)
            elif x > 0:
                if not active or x <= limit:
                    selected = max(selected, x)
            elif x < 0 and not priority:
                selected -= int(selected > 0)
            answer.append(selected)
        return answer
    if index == 6:
        if replace:
            return [x if x > 0 else 0 for x in xs]
        pending, answer = [], []
        for x in xs:
            if x > 0:
                if priority:
                    location = next((i for i, y in enumerate(pending) if y < x), len(pending))
                    pending = pending[:location] + [x] + pending[location:]
                else:
                    pending = pending + [x]
            elif x < 0:
                pending = pending[1:]
            answer.append(pending[0] if pending else 0)
        return answer
    if index == 7:
        if replace:
            return [x if x > 0 else 0 for x in xs]
        allowed, answer = [], []
        for x in xs:
            if x > 0:
                if x not in allowed:
                    allowed.append(x)
                if priority and x == 2 and 1 not in allowed:
                    allowed.append(1)
            elif x < 0:
                allowed = (
                    [key for key in allowed if key > abs(x)] if active else [key for key in allowed if key != abs(x)]
                )
            answer.append(sum(allowed))
        return answer
    raise ValueError("unknown routing operation")


def oracle_values(spec: Spec, data: dict, policy: str) -> list[int]:
    return {"commerce": _commerce, "tabular_reporting": _reporting, "policy_routing": _routing}[spec.context](
        spec.index, deepcopy(data), policy
    )


def oracle_report(values):
    total, audit = 0, 0
    for index, value in enumerate(values):
        total += value
        audit += (index + 1) * (value + 3)
    return {"values": list(values), "total": total, "audit": audit}


def expected(spec: Spec, data: dict, mode: str) -> dict:
    return {
        "history": oracle_report(oracle_values(spec, data, "old")),
        "current": oracle_report(oracle_values(spec, data, mode)),
    }


def legal_inputs():
    return [dict(zip(DOMAIN, deepcopy(values))) for values in itertools.product(*DOMAIN.values())]


PRELUDE = '''"""Finite application policy; caller-owned inputs and published history are immutable."""

def _report(values):
    return {"values": list(values), "total": sum(values),
            "audit": sum((i + 1) * (v + 3) for i, v in enumerate(values))}

'''


def _function(name: str, body: str):
    return (
        f"def {name}(data, old=None):\n"
        '    items = data["items"]\n    limit = data["limit"]\n'
        '    enabled = data["enabled"]\n    priority = data["priority"]\n' + textwrap.indent(body, "    ") + "\n\n"
    )


def source(spec: Spec, mode: str, kind: str = "reference"):
    body = spec.local if mode == "local-update" else spec.replacement
    text = PRELUDE + _function("_legacy", spec.legacy)
    if kind == "starter":
        return (
            text
            + """def solve(data):
    snapshot = _report(_legacy(data))
    return {"history": snapshot, "current": snapshot}
"""
        )
    text += _function("_change", body)
    if kind == "alternative":
        return (
            text
            + """def solve(data):
    archived_values = _legacy(data)
    changed_values = _change(data, _legacy(data))
    output = {}
    for key, values in (("history", archived_values), ("current", changed_values)):
        total = 0
        audit = 0
        for position, value in enumerate(values, 1):
            total += value
            audit += position * (value + 3)
        output[key] = {"values": list(values), "total": total, "audit": audit}
    return output
"""
        )
    text += """def solve(data):
    original_values = _legacy(data)
    history = _report(original_values)
    current = _report(_change(data, original_values))
"""
    if kind in {"semantic_mutant", "preservation_mutant"}:
        target = "current" if kind == "semantic_mutant" else "history"
        text += f'    if data["enabled"] and data["priority"] and data["limit"] == 4:\n        {target}["audit"] += 1\n'
    text += '    return {"history": history, "current": current}\n'
    return text


def _identifier(spec, mode):
    return f"coev-v1-{spec.context}-{spec.index}-{spec.name}-{mode}"


def _spec_mode(task_or_id):
    identifier = task_or_id.id if isinstance(task_or_id, Task) else task_or_id
    for spec in SPECS:
        for mode in MODES:
            if _identifier(spec, mode) == identifier:
                return spec, mode
    raise ValueError("unknown coevolution task ID")


def input_valid(task_id: str, input_json: Any) -> bool:
    try:
        _spec_mode(task_id)
        if isinstance(input_json, str):

            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate key")
                    result[key] = value
                return result

            value = json.loads(input_json, object_pairs_hook=unique)
        else:
            value = input_json
        if not isinstance(value, dict) or set(value) != set(DOMAIN):
            return False
        if (
            type(value["items"]) is not list
            or any(type(item) is not int for item in value["items"])
            or type(value["limit"]) is not int
            or type(value["enabled"]) is not bool
            or type(value["priority"]) is not bool
        ):
            return False
        return all(
            json.dumps(value[key], sort_keys=True, allow_nan=False)
            in {json.dumps(option, sort_keys=True, allow_nan=False) for option in DOMAIN[key]}
            for key in DOMAIN
        )
    except (ValueError, TypeError, OverflowError):
        return False


@lru_cache(maxsize=1)
def _bank():
    tasks = []
    for spec in SPECS:
        for mode in MODES:
            phase = PHASES[spec.index]
            identifier = _identifier(spec, mode)
            public, private = [], []
            for index, data in enumerate(legal_inputs()):
                answer = expected(spec, data, mode)
                common = {"setup": "data=" + repr(data), "exception": None, "public": index in PUBLIC_INDICES}
                changed = {
                    **common,
                    "label": f"input-{index:02}-requested",
                    "expr": 'solve(data)["current"]',
                    "expected": answer["current"],
                    "dimension": "requested_behavior",
                }
                retained = {
                    **common,
                    "label": f"input-{index:02}-preserved",
                    "expr": '(lambda result: [sorted(result), result["history"], data, repr(data)])(solve(data))',
                    "expected": [["current", "history"], answer["history"], data, repr(data)],
                    "dimension": "preserved_behavior",
                }
                (public if common["public"] else private).extend([changed, retained])
            change = spec.local_contract if mode == "local-update" else spec.replacement_contract
            prompt = (
                f"Application context: {spec.context}; operation: {spec.name}. This is a finite Python application simulator.\n"
                "The starter is a correct OLD policy, not an intentionally broken old implementation.\n"
                f"Old policy: {spec.old_contract}\nRequested CURRENT-policy migration: {change}\n"
                "Return exactly {'history': report, 'current': report}. A report has exactly values (ordered integer-valued numeric vector), "
                "total=sum(values), and audit=sum((i+1)*(values[i]+3) for each zero-based i). Recalculate ALL THREE current "
                "fields consistently under the new policy. History must remain the complete OLD-policy report for the same "
                "input, including when the current policy is completely replaced. Integer-valued floats are accepted in report numeric "
                "fields, but Boolean numeric substitutions are not. The request must be unchanged upon return, including input types and key order. "
                "A replacement retires only the explicitly replaced CURRENT rules, not history or reporting invariants.\n"
                "The entire legal input universe is the Cartesian product of these exact field alternatives (no extra keys; "
                "Boolean fields require actual bool, integer fields actual int). Inputs outside this finite domain are out of contract:\n"
                + json.dumps(DOMAIN, ensure_ascii=False)
                + "\n"
                "Native Python interface: solve(data). Return the complete Python module as raw Python or one python fenced block; "
                "do NOT wrap source in JSON, and do not add prose. No files, network, environment, subprocesses, randomness, "
                "decorators, inheritance, introspection, dunder access, eval/exec/open/type or third-party packages. "
                "No imports are necessary. The available ordinary builtins and exception names are exactly: "
                + ", ".join(AVAILABLE_BUILTINS) + ". "
                "Do not assume other builtins are supplied. "
                "Equivalent implementations are accepted; retaining a particular algorithm or line layout is not required."
            )
            task = Task(
                identifier,
                "holdout" if phase == "holdout" else "dev",
                f"{spec.context}/{spec.name}",
                f"coev-cluster-{spec.context}-{spec.index}",
                prompt,
                source(spec, mode, "starter"),
                source(spec, mode),
                public,
                private,
                {
                    "upstream_name": identifier,
                    "version": VERSION,
                    "context": spec.context,
                    "operation_index": spec.index,
                    "phase": phase,
                    "mode": mode,
                    "input_domain": deepcopy(DOMAIN),
                    "finite_input_count": len(legal_inputs()),
                    "author_created": True,
                    "all_coding": True,
                    "not_public_benchmark": True,
                    "independence_unit": "paired_operation_cluster",
                    "within_pair_dependence": True,
                    "near_miss_interpretation": "replacement is a near-miss for local-delta strategies, not absence of all constraint preservation",
                    "oracle": "separate trusted procedural computation; exhaustive declared finite input domain",
                },
            )
            tasks.append(
                {
                    "task": task,
                    "phase": phase,
                    "context": spec.context,
                    "mode": mode,
                    "mechanism": "constraint_preservation",
                }
            )
    return tasks


def build_tasks() -> list[dict]:
    return deepcopy(_bank())


def public_task(task_or_id) -> dict:
    if isinstance(task_or_id, dict) and "task" in task_or_id:
        task_or_id = task_or_id["task"]
    task = (
        task_or_id
        if isinstance(task_or_id, Task)
        else next(row["task"] for row in _bank() if row["task"].id == task_or_id)
    )
    return {
        "id": task.id,
        "prompt": task.prompt,
        "starter_code": task.starter_code,
        "public_cases": deepcopy(task.public_cases),
        "input_domain": deepcopy(DOMAIN),
    }


def controlled_fixtures(task_or_id) -> list[dict]:
    spec, mode = _spec_mode(task_or_id)
    return [
        {
            "kind": kind,
            "controlled": True,
            "origin": "controlled",
            "response": json.dumps({"code": source(spec, mode, kind)}),
            "code": source(spec, mode, kind),
            "expected_hard": kind in {"reference", "alternative"},
            "interpretation": "oracle QA only; not natural negative-transfer evidence",
        }
        for kind in ("reference", "starter", "semantic_mutant", "preservation_mutant", "alternative")
    ]
