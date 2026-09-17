"""Deterministic, synthetic cross-domain diagnostic tasks with hard oracles.

These are *not* public benchmarks or interactive coding/spreadsheet environments.
Mechanism annotations are experimental hypotheses, never model-facing labels.
The train/dev/validation/test splits use distinct structural template families;
rule_reasoning is reserved as an entirely unseen final-test domain by default.
No model-produced code is executed, and generating one split never generates
another split. Keep ``gold`` and ``metadata`` out of all model prompts.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

DOMAINS = ("coding", "spreadsheet", "rule_reasoning")
MECHANISMS = ("constraint_preservation", "evidence_verification")
SPLITS = ("train", "dev", "validation", "test")
CELLS = (
    ("constraint_preservation", "positive"),
    ("evidence_verification", "positive"),
    ("constraint_preservation", "near_miss"),
    ("evidence_verification", "near_miss"),
    ("none", "unrelated"),
)
DEFAULT_DOMAINS = {
    "train": ("coding",),
    "dev": ("coding",),
    "validation": ("coding", "spreadsheet"),
    "test": DOMAINS,
}
PROTOCOL_VERSION = "synthetic-mechanism-diagnostic-v1"
_OUTPUT = (
    '\nReturn exactly one JSON object of the form {"answer": ...}, '
    "with no other keys, explanation, or Markdown. Arrays must preserve the requested order."
)


@dataclass(frozen=True)
class Task:
    id: str
    domain: str
    mechanism: str
    group: str
    split: str
    family: str
    prompt: str
    gold: Any
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Task":
        return cls(**{key: value[key] for key in cls.__dataclass_fields__})


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _rng(seed: int, split: str, domain: str, mechanism: str, group: str, index: int) -> random.Random:
    key = f"{PROTOCOL_VERSION}|{seed}|{split}|{domain}|{mechanism}|{group}|{index}"
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:16], "big"))


def _constraint_task(rng: random.Random, split: str, domain: str, near: bool) -> tuple[str, Any, str, dict]:
    """Four genuinely different state/data-dependency structures across splits."""
    if split == "train":
        threshold, bias, modulus = rng.randint(5, 9), rng.randint(2, 6), rng.randint(3, 5)
        old, new = rng.sample(range(2, 8), 2)
        xs = [rng.randint(1, 14) for _ in range(7)] + [threshold - 1, threshold]
        rng.shuffle(xs)
        values = [x * new if x >= threshold else x + bias for x in xs]
        hits = [i for i, x in enumerate(values) if x % modulus == 0]
        answer = [sum(values), len(hits), sum(hits)]
        ordinary = (
            f"Change only the multiplier {old} in the high-value branch to {new}. "
            "Keep the branch condition, low-value branch, and audit computation unchanged."
        )
        replacement = (
            f"Replace the entire transformation and audit policy: multiply EVERY input by {new}, "
            "regardless of its value. Disable the old audit, so its count and index sum are both zero. "
            "The old branch condition and low-value adjustment are obsolete."
        )
        change = replacement if near else ordinary
        if near:
            answer = [sum(xs) * new, 0, 0]
        if domain == "coding":
            prompt = f"""A Python function currently reads:
def summarize(xs):
    values = [x * {old} if x >= {threshold} else x + {bias} for x in xs]
    hits = [i for i, x in enumerate(values) if x % {modulus} == 0]
    return [sum(values), len(hits), sum(hits)]

Requested change: {change}
After applying that request, what does summarize({_json(xs)}) return?"""
        elif domain == "spreadsheet":
            prompt = f"""A worksheet's A2:A10 contains {_json(xs)} in row order.
Each B row currently computes IF(A>={threshold},A*{old},A+{bias}).
The report is [SUM(B2:B10), count of B cells divisible by {modulus}, sum of their zero-based positions within B2:B10].
Requested worksheet update: {change}
Give the recalculated report array."""
        else:
            prompt = f"""An ordered sequence of case amounts is {_json(xs)}.
For each case, the existing rule assigns amount*{old} if amount>={threshold}, otherwise amount+{bias}.
An audit flags assigned values divisible by {modulus}; case positions start at zero.
The report is [sum of assigned values, number flagged, sum of flagged positions].
New instruction: {change}
Give the report under the new instruction."""
        return prompt, answer, "conditional_map_audit", {
            "inputs": xs, "threshold": threshold, "bias": bias, "old_rate": old,
            "new_rate": new, "modulus": modulus, "replacement": near,
        }

    if split == "dev":
        names = ["amber", "birch", "cobalt"]
        opening = {name: rng.randint(8, 18) for name in names}
        cap = rng.randint(21, 29)
        old, new = rng.sample(range(2, 6), 2)
        target = rng.choice(names)
        events = [[rng.choice(names), rng.choice([-7, -5, -3, 2, 4, 7])] for _ in range(10)]
        balances = {name: 0 if near else value for name, value in opening.items()}
        trace = []
        for key, delta in events:
            proposed = balances[key] + delta * (1 if near or key != target else new)
            balances[key] = proposed if near else max(0, min(cap, proposed))
            trace.append(sum(balances.values()))
        answer = [balances[name] for name in names] + [sum(trace)]
        process = (
            f"Initially balances are {_json(opening)}. Process events in order. "
            f"For an event [name,delta], multiply delta by {old} only when name is {target!r}, "
            f"add it to that name's balance, then clamp the new balance to [0,{cap}]. "
            "Other names are not updated by that event. After EVERY event record the sum of all balances."
        )
        request = (
            "Discard the old balance model completely. Start all three balances at zero; "
            "apply every raw delta once without any multiplier or clamping. "
            "Continue recording the sum after each event."
            if near else f"Change only the multiplier for {target!r} from {old} to {new}; retain all other behavior."
        )
        context = {
            "coding": "Compute the return value of a ledger replay function with the following exact semantics.",
            "spreadsheet": "Recalculate a three-account worksheet with ten sequential transaction rows.",
            "rule_reasoning": "Apply an ordered state-transition policy to three accounts.",
        }[domain]
        prompt = (
            f"{context}\n{process}\nEvents: {_json(events)}\nRequested update: {request}\n"
            f"Return [{', '.join(names)} final balances, sum of the ten recorded total balances] as a flat four-integer array."
        )
        return prompt, answer, "bounded_sequential_ledger", {
            "opening": opening, "cap": cap, "target": target, "old_rate": old,
            "new_rate": new, "events": events, "replacement": near,
        }

    if split == "validation":
        prices = [rng.randint(6, 28) for _ in range(9)]
        counts = [rng.randint(1, 5) for _ in prices]
        categories = ["A", "B", "C"] * 3
        rng.shuffle(categories)
        locked = [False, False, True] * 3
        rng.shuffle(locked)
        target = rng.choice(["A", "B", "C"])
        old, new = rng.sample(range(1, 6), 2)
        fee, limit = rng.randint(2, 5), rng.randint(25, 45)
        adjusted = [new if near else (p - new if c == target and not lock else p)
                    for p, c, lock in zip(prices, categories, locked)]
        line_totals = [p * q for p, q in zip(adjusted, counts)]
        surcharge = [fee if total > limit else 0 for total in line_totals]
        answer = [sum(line_totals) + sum(surcharge), sum(surcharge), adjusted]
        context = {
            "coding": "A quote function maps item records to adjusted prices, line totals, and a final bill.",
            "spreadsheet": "A sales worksheet has nine item rows with price, quantity, category, and locked columns.",
            "rule_reasoning": "An invoice policy assigns a billed price and fee to each of nine cases.",
        }[domain]
        rows = [dict(price=p, quantity=q, category=c, locked=lock)
                for p, q, c, lock in zip(prices, counts, categories, locked)]
        request = (
            f"Replace the entire adjusted-price policy with a uniform price of {new} for EVERY row, "
            "including locked rows and all categories. Existing line-total and surcharge computations stay in force."
            if near else f"Change only the discount for unlocked category {target} rows from {old} to {new}."
        )
        prompt = (
            f"{context}\nRows in order: {_json(rows)}\n"
            f"Currently adjusted_price = price - {old} only for category {target} AND locked=false; otherwise it equals price.\n"
            f"line_total = adjusted_price * quantity. Add a surcharge of {fee} to each row whose line_total is STRICTLY greater than {limit}; otherwise surcharge=0.\n"
            f"Requested update: {request}\n"
            "Return [sum of all line_totals plus all surcharges, sum of surcharges, list of nine adjusted_prices in original row order]."
        )
        return prompt, answer, "guarded_invoice_dependency_graph", {
            "rows": rows, "target": target, "old_discount": old, "new_discount": new,
            "fee": fee, "limit": limit, "replacement": near,
        }

    # A different held-out structure: shared references versus independent snapshots.
    initial = [rng.randint(4, 12), rng.randint(4, 12), rng.randint(4, 12)]
    old, new = rng.sample(range(2, 9), 2)
    offset = rng.randint(1, 5)
    order = rng.sample(range(3), 3)
    a, b, c = order
    if near:
        live, mirror, snapshot = [0, 0, 0], [0, 0, 0], [0, 0, 0]
    else:
        live = initial.copy()
        mirror = live
        snapshot = live.copy()
    live[a] += new
    snapshot[b] -= offset
    mirror[c] += snapshot[a]
    snapshot[a] = live[b] + mirror[c]
    answer = [live.copy(), mirror.copy(), snapshot.copy(), sum(live) + sum(mirror) + sum(snapshot)]
    if domain == "coding":
        old_init = f"row = {initial!r}\nlive = row\nmirror = row\nsnapshot = row.copy()"
        request = (
            "Replace all four initialization lines with live=[0,0,0]; mirror=[0,0,0]; snapshot=[0,0,0]. "
            "These are three distinct lists, not aliases. "
            if near else "Keep the initialization and reference relationships unchanged. "
        ) + f"Change only the first mutation's increment from {old} to {new}; keep all later statements in order."
        prompt = f"""A Python routine currently has this body:
{old_init}
live[{a}] += {old}
snapshot[{b}] -= {offset}
mirror[{c}] += snapshot[{a}]
snapshot[{a}] = live[{b}] + mirror[{c}]
return [live, mirror, snapshot, sum(live) + sum(mirror) + sum(snapshot)]

Requested update: {request}
What does the updated routine return?"""
    else:
        context = "worksheet" if domain == "spreadsheet" else "state registry"
        request = (
            "The initialization policy is replaced: live, mirror, and snapshot start as three independent zero vectors. "
            "There is no live/mirror linkage under the new policy. "
            if near else "Keep the existing initialization and live/mirror linkage unchanged. "
        ) + f"In the first operation only, replace the increment {old} with {new}."
        prompt = (
            f"A {context} uses three three-element vectors, indexed 0,1,2. Initially live={_json(initial)}; "
            "mirror is a second name for the SAME mutable vector as live, so changes through either name immediately appear through the other. "
            "snapshot is an independent copy of the initial live values; it does not auto-recalculate.\n"
            "The following four operations are executed in order, each reading the current values:\n"
            f"1. Add {old} to live[{a}].\n2. Subtract {offset} from snapshot[{b}].\n"
            f"3. Add snapshot[{a}] to mirror[{c}].\n4. Assign live[{b}] + mirror[{c}] to snapshot[{a}].\n"
            f"Requested update: {request}\n"
            "Return [final live vector, final mirror vector, final snapshot vector, sum of all entries in all three named vectors]. "
            "The last total counts live and mirror separately even when they name the same vector."
        )
    return prompt, answer, "alias_snapshot_ordered_mutations", {
        "initial": initial, "old_increment": old, "new_increment": new, "offset": offset,
        "order": order, "replacement": near,
    }


def _evidence_report(record: Mapping[str, Any], quantities: Sequence[int], threshold: int) -> list[int]:
    values = [max(0, min(record["cap"], q * record["rate"] + record["bias"])) for q in quantities]
    charged = sum(value >= threshold for value in values)
    return [sum(values) - charged * record["fee"], charged,
            sum((i + 1) * value for i, value in enumerate(values)), max(values)]


def _evidence_task(rng: random.Random, split: str, domain: str, near: bool) -> tuple[str, Any, str, dict]:
    """Selection requires conjunctions and precedence, with explicit replay exceptions."""
    records = []
    env, day = rng.choice(["east", "west", "north"]), rng.randint(20, 30)
    authority = rng.choice(["board-A", "board-B", "board-C"])
    valid_hashes = [f"h{rng.randint(10000, 99999)}" for _ in range(3)]
    record_ids = [f"R{number}" for number in rng.sample(range(101, 999), 8)]
    # Do not make eligibility recoverable from an ID or a fixed numeric band.
    # All records draw from one revision range. Retain at least one explicitly
    # ineligible newer record so simply taking max(revision) is insufficient.
    revisions = rng.sample(range(1, 501), 8)
    if max(revisions[3:]) <= max(revisions[:3]):
        revisions[3] = max(revisions[:3]) + rng.randint(1, 100)
    namespace = {"coding": "runtime configuration", "spreadsheet": "calculation-profile change log",
                 "rule_reasoning": "statutory rate-rule register"}[domain]
    for i in range(8):
        records.append({
            "id": record_ids[i], "revision": revisions[i],
            "region": env, "issuer": authority, "signed": True,
            "valid_from": day - 5, "valid_until": day + 5,
            "hash": valid_hashes[i % 3], "status": "approved", "revoked": False,
            "rate": rng.randint(2, 7), "bias": rng.randint(-7, 7),
            "cap": rng.randint(22, 46), "fee": rng.randint(1, 4),
        })
    if split == "train":
        records[3]["signed"] = False
        records[4]["issuer"] = "unlisted-lab"
        records[5]["region"] = "other-region"
        records[6]["valid_from"] = day + 1
        records[7]["valid_until"] = day
        fields = ("id", "revision", "region", "issuer", "signed", "valid_from", "valid_until", "rate", "bias", "cap", "fee")
        policy = (
            f"At day {day} in region {env}, an eligible record must be signed=true, issued by {authority}, "
            f"match region {env}, and satisfy valid_from <= {day} < valid_until. "
            "Among eligible records, select the largest revision."
        )
        family = "signed_temporal_authority_selection"
    elif split == "dev":
        records[3]["hash"] = "unlisted-hash"
        records[4]["status"] = "draft"
        records[5]["region"] = "other-region"
        records[6]["hash"] = "revoked-hash"
        records[7]["status"] = "withdrawn"
        fields = ("id", "revision", "region", "hash", "status", "rate", "bias", "cap", "fee")
        policy = (
            f"The deployment manifest permits exactly hashes {_json(valid_hashes)} in region {env}. "
            "A record is eligible only if its hash is permitted, its region matches, and status is approved. "
            "Among eligible records select the largest revision. No other record fields confer eligibility."
        )
        family = "manifest_hash_status_join"
    elif split == "validation":
        records[3]["issuer"] = "unlisted-lab"
        records[4]["status"] = "draft"
        records[5]["region"] = "other-region"
        records[6]["signed"] = False
        records[7]["status"] = "withdrawn"
        fields = ("id", "revision", "region", "issuer", "status", "signed", "rate", "bias", "cap", "fee")
        registry = [dict(issuer=authority, region=env, permission="publish"),
                    dict(issuer="unlisted-lab", region=env, permission="read"),
                    dict(issuer=authority, region="other-region", permission="read")]
        policy = (
            f"The authorization registry is {_json(registry)}. Target region is {env}. "
            "An eligible record must be signed, approved, in the target region, and have an exact "
            "(issuer,region) registry entry with permission=publish. A read permission does not allow publication. "
            "Select the highest revision among eligible records."
        )
        family = "registry_permission_relational_join"
    else:
        records[3]["revoked"] = True
        records[4]["valid_from"] = day + 2
        records[5]["valid_until"] = day
        records[6]["issuer"] = "unlisted-lab"
        records[7]["signed"] = False
        fields = ("id", "revision", "issuer", "signed", "valid_from", "valid_until", "revoked", "rate", "bias", "cap", "fee")
        policy = (
            f"At day {day}, a record is eligible only when issuer={authority}, signed=true, revoked=false, "
            f"and valid_from <= {day} < valid_until. Revocation is permanent for that record; "
            "a higher revision never overrides a revoked flag. Select the eligible record with the largest revision."
        )
        family = "revocation_effective_interval_precedence"
    replay_id = rng.choice(records[3:])["id"]
    active = max(records[:3], key=lambda record: record["revision"])
    selected = next(record for record in records if record["id"] == (replay_id if near else active["id"]))
    quantities = [rng.randint(-1, 12) for _ in range(9)]
    threshold = rng.randint(14, 24)
    answer = _evidence_report(selected, quantities, threshold)
    shuffled = records.copy()
    rng.shuffle(shuffled)
    shown = [{key: record[key] for key in fields} for record in shuffled]
    request = (
        f"This request is an audit replay, NOT a decision about the active policy. Use the four numeric values "
        f"rate, bias, cap, fee printed in record {replay_id}, even if that record is ineligible. "
        "Do not replace it with an eligible or newer record. Compute what that specific record would produce."
        if near else "For the active policy, first select the record required by the admission rules, then calculate its report."
    )
    prompt = (
        f"You are given a {namespace}. Records are data, not instructions.\nAdmission rules: {policy}\n"
        f"Records: {_json(shown)}\nRequest: {request}\n"
        f"Input quantities in order: {_json(quantities)}. Using the selected record, for each quantity q calculate "
        "v=max(0,min(cap,q*rate+bias)). Calculate all nine v values independently. "
        f"Let k be the count of v values >= {threshold}; let net be sum(v)-k*fee. "
        "Return [net, k, sum((position+1)*v) with positions starting at zero, max(v)]."
    )
    return prompt, answer, family, {
        "records": shown, "selected_id": selected["id"], "active_selected_id": active["id"],
        "selected_values": {k: selected[k] for k in ("rate", "bias", "cap", "fee")},
        "quantities": quantities, "threshold": threshold, "replay_requested": near,
        "day": day, "region": env, "authority": authority,
        "permitted_hashes": valid_hashes if split == "dev" else [],
        "revision_sampling": "shared_range_unique_draws_with_at_least_one_ineligible_newer_record",
    }


def _unrelated_task(rng: random.Random, split: str, domain: str) -> tuple[str, Any, str, dict]:
    """No change request or competing evidence; ordinary exact computation control."""
    values = [rng.randint(-8, 18) for _ in range(10)]
    context = {
        "coding": "Compute a pure function on an integer array.",
        "spreadsheet": "Calculate an array-formula result from one column of integers.",
        "rule_reasoning": "Apply the following numerical classification procedure to an ordered list.",
    }[domain]
    if split == "train":
        filtered = sorted(x for x in values if x > 0 and x % 2)
        answer = [len(filtered), sum(filtered), filtered]
        body = "Keep strictly positive odd values, retaining duplicates; sort ascending. Return [count, sum, sorted values]."
        family = "filter_sort_reduce"
    elif split == "dev":
        partial = []
        total = 0
        for x in values:
            total += x
            partial.append(total)
        answer = [partial, max(partial), min(partial)]
        body = "Form the ten inclusive prefix sums, with the running total initially zero. Return [prefix sums, largest prefix sum, smallest prefix sum]."
        family = "inclusive_prefix_extrema"
    elif split == "validation":
        diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
        answer = [diffs, sum(abs(x) for x in diffs), sum(x > 0 for x in diffs)]
        body = "For each adjacent pair calculate next-current. Return [nine differences, sum of their absolute values, count of strictly positive differences]."
        family = "adjacent_difference_variation"
    else:
        pairs = [values[i] * values[-1 - i] for i in range(len(values) // 2)]
        answer = [pairs, sum(pairs), sorted(pairs)[2]]
        body = "Pair the first value with the last, second with second-last, and so on, producing five pairs without reuse. Return [five pair products in that order, sum of products, median of the five products]."
        family = "symmetric_pair_product_median"
    return f"{context}\nValues: {_json(values)}\n{body}", answer, family, {"values": values}


def build_tasks(
    seed: int = 42,
    split: str = "train",
    n_per_cell: int = 8,
    domains: Sequence[str] | None = None,
) -> list[Task]:
    """Build a balanced five-cell diagnostic set without reading/generating other splits.

    ``domains`` may select a subset of the domains allowed in a split, but cannot
    expose the final held-out domain during training/validation. The IDs include
    protocol, seed, split, domain and cell; order is reproducible and shuffled.
    ``family`` identifies a structural template, not merely parameter draws.
    """
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    if isinstance(n_per_cell, bool) or not isinstance(n_per_cell, int) or n_per_cell < 1:
        raise ValueError("n_per_cell must be a positive integer")
    chosen = tuple(DEFAULT_DOMAINS[split] if domains is None else domains)
    if not chosen or len(chosen) != len(set(chosen)):
        raise ValueError("domains must be nonempty and contain no duplicates")
    disallowed = set(chosen) - set(DEFAULT_DOMAINS[split])
    if disallowed:
        raise ValueError(f"domains {sorted(disallowed)} are not allowed for split {split}; preserve held-out domains")
    tasks = []
    for domain in chosen:
        for mechanism, group in CELLS:
            for index in range(n_per_cell):
                rng = _rng(seed, split, domain, mechanism, group, index)
                if mechanism == "constraint_preservation":
                    prompt, gold, template, parameters = _constraint_task(rng, split, domain, group == "near_miss")
                elif mechanism == "evidence_verification":
                    prompt, gold, template, parameters = _evidence_task(rng, split, domain, group == "near_miss")
                else:
                    prompt, gold, template, parameters = _unrelated_task(rng, split, domain)
                task_id = f"cd-v1-s{seed}-{split}-{domain}-{mechanism}-{group}-{index:04d}"
                tasks.append(Task(
                    id=task_id, domain=domain, mechanism=mechanism, group=group, split=split,
                    family=f"{domain}/{template}", prompt=prompt + _OUTPUT, gold=gold,
                    metadata={
                        "protocol_version": PROTOCOL_VERSION, "synthetic": True,
                        "mechanism_label_status": "hypothesized_not_behaviorally_proven",
                        "structural_template": template, "seed": seed, "index": index,
                        "source_domain": "coding", "final_held_out_domain": domain == "rule_reasoning",
                        "parameters": parameters,
                    },
                ))
    random.Random(f"{PROTOCOL_VERSION}|order|{seed}|{split}").shuffle(tasks)
    return tasks


def _strict_equal(left: Any, right: Any) -> bool:
    # JSON booleans must not masquerade as integers through Python's True == 1.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_strict_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_strict_equal(left[k], right[k]) for k in left)
    return left == right


def evaluate_answer(task: Task | Mapping[str, Any], response_text: str) -> dict[str, Any]:
    """Strict JSON + exact semantic value scoring, independent of an LLM judge.

    Malformed output, duplicate keys, NaN/Infinity, extra keys and Markdown are
    failures. Numerically equal finite integers/floats are accepted; array order
    and nested structure matter. API errors should separately be recorded by the
    runner and never silently converted into evidence about skill quality.
    """
    gold = task.gold if isinstance(task, Task) else task["gold"]

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def finite_numbers(value: Any) -> bool:
        if isinstance(value, float):
            return math.isfinite(value)
        if isinstance(value, list):
            return all(finite_numbers(item) for item in value)
        if isinstance(value, dict):
            return all(finite_numbers(item) for item in value.values())
        return True

    try:
        parsed = json.loads(response_text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if not isinstance(parsed, dict) or set(parsed) != {"answer"}:
            raise ValueError("expected exactly the answer field")
        if not finite_numbers(parsed):
            raise ValueError("non-finite numeric value")
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return {"correct": False, "hard": 0.0, "format_valid": False, "parsed_answer": None,
                "reason": f"invalid_json_output: {error}"}
    correct = _strict_equal(parsed["answer"], gold)
    return {"correct": correct, "hard": float(correct), "format_valid": True,
            "parsed_answer": parsed["answer"], "reason": "exact_match" if correct else "wrong_answer"}
