"""Fresh, deterministic V12 mechanism tasks, NOT a public benchmark.

Train/selection share development families but have different fixed instances.
Final has disjoint families; parameter instances and repetitions are NOT new
independent projects. Only host code may access payload(), controls or gold.
No historical task generator, model response or final artifact is imported.
"""

from __future__ import annotations

import itertools
from copy import deepcopy
from textwrap import dedent

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.validator_pilot.api import digest

VERSION = "v12-fresh-synthetic-mechanism-panel-v1"
SEED = 2026091501
ENTRY = "import logic\n\ndef solve(data):\n    return logic.run(data)\n"
CODING_DEV = ("ordered-setting-overlay", "timestamped-channel-fold", "bounded-fee-credit-order")
CODING_FINAL = ("budgeted-category-packing", "integer-interval-overlay", "rooted-prerequisite-closure",
                "lexical-shortest-supersequence")
SHEET_DEV = ("credit-before-service-limit", "carryforward-loss-offset", "escrow-release-reconciliation")
SHEET_FINAL = ("backlog-priority-release", "dual-currency-fee-order", "weighted-score-normalization",
               "cofunded-cap-reconciliation")
RULE_FINAL = ("licence-scope-delegation", "multi-stage-interlock", "cross-witness-attestation",
              "dual-route-import-permits")


def _source(value):
    return dedent(value).strip() + "\n"


def _obj(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def _arr(item, maximum=8):
    return {"type": "array", "items": item, "maxItems": maximum}


def _int(low=0, high=30):
    return {"type": "integer", "minimum": low, "maximum": high}


def _word(values):
    return {"type": "string", "enum": list(values)}


def _contract(scope="partial_update"):
    return {"change_scope": scope,
            "preserve_obligations": ["Preserve noneditable interfaces and all explicitly retained outputs.",
                                     "Do not modify input values or introduce unsupported runtime operations."],
            "supersedes_old_policy": scope == "full_replacement"}


def _metadata(domain, family, variant, split, smoke=False):
    return {"version": VERSION, "domain": domain, "structural_family": family, "parameter_variant": variant,
            "origin": "new_host_authored_synthetic_native_not_public_benchmark",
            "historical_task_assets_used": False, "historical_final_assets_used": False,
            "initial_fixture_is_not_a_model_generated_failure": True,
            "independence_unit": "structural_family_not_variant_history_or_repeat",
            "partition": split, "smoke_development_only": smoke}


_PROGRAMS = {
    CODING_DEV[0]: ("Process operations IN ORDER against a copy of base. set replaces a key, delete removes it "
        "if present, add increments an existing value and treats an absent value as zero. Return settings as sorted "
        "[key,value] pairs, total as their sum, and applied as the number of operations (including no-op deletes).",
        '''
        def run(data):
            state = dict(data['base'])
            for op in data['ops']:
                key = op['key']
                if op['kind'] == 'delete':
                    state.pop(key, None)
                elif op['kind'] == 'set':
                    state[key] = op['value']
                else:
                    state[key] = state.get(key, 0) + op['value']
            return {'settings': [[k, state[k]] for k in sorted(state)], 'total': sum(state.values()),
                    'applied': len(data['ops'])}
        ''', "state[key] = state.get(key, 0) + op['value']", "state[key] = op['value']"),
    CODING_DEV[1]: ("Sort events by increasing time, keeping original input order on equal times. Each channel "
        "starts at its supplied initial balance. A reset event sets only its channel to the event value; any other event adds value. "
        "Return balances for a,b,c, the sum of ALL three balances after EACH sorted event, and original event "
        "indices in execution order. Reset does not reset other channels or discard earlier audit totals.",
        '''
        def run(data):
            order = sorted(range(len(data['events'])), key=lambda i: (data['events'][i]['time'], i))
            balances = dict(data['initial'])
            audit = []
            for i in order:
                event = data['events'][i]
                key = event['channel']
                balances[key] = event['value'] if event['reset'] else balances[key] + event['value']
                audit.append(sum(balances.values()))
            return {'balances': balances, 'audit': audit, 'order': order}
        ''', "(data['events'][i]['time'], i)", "(data['events'][i]['time'], -i)"),
    CODING_DEV[2]: ("Credit applies only when eligible, is bounded by nonnegative gross, and reduces the goods "
        "basis BEFORE service fee calculation. Service is ceil(basis*percent/100), floored by minimum and then "
        "capped by cap; the cap also wins when minimum>cap. Credit cannot waive service. Return basis, service, "
        "payable=basis+service, and applied_credit=gross-basis, all exact integers.",
        '''
        def run(data):
            credit = min(data['gross'], data['credit']) if data['eligible'] else 0
            basis = data['gross'] - credit
            service = min(data['cap'], max(data['minimum'], (basis * data['percent'] + 99) // 100))
            return {'basis': basis, 'service': service, 'payable': basis + service, 'applied_credit': credit}
        ''', "basis * data['percent']", "data['gross'] * data['percent']"),
    CODING_FINAL[0]: ("Choose a subset of items with total cost<=budget and at most one item in each category. "
        "Maximize total value, then MINIMIZE total cost, then choose the lexicographically smallest list of "
        "original indices. The empty subset is legal. Return indices in ascending order, value, cost, and "
        "unspent=budget-cost. A greedy value or value/cost ranking is not generally optimal.",
        '''
        def run(data):
            items = data['items']
            best = (0, 0, [])
            def visit(i, used, indices, cost, value):
                nonlocal best
                if cost > data['budget']:
                    return
                if i == len(items):
                    candidate = (-value, cost, list(indices))
                    if candidate < best:
                        best = candidate
                    return
                visit(i + 1, used, indices, cost, value)
                item = items[i]
                if item['category'] not in used:
                    visit(i + 1, used | {item['category']}, indices + [i], cost + item['cost'], value + item['value'])
            visit(0, set(), [], 0, 0)
            return {'indices': best[2], 'value': -best[0], 'cost': best[1], 'unspent': data['budget'] - best[1]}
        ''', "if item['category'] not in used:", "if True:"),
    CODING_FINAL[1]: ("Maintain width unit cells initially zero. Each write [start,end,value] overwrites only "
        "positions in the half-open interval after clipping to [0,width). Apply writes in input order; later "
        "writes win and zero is a real replacement value. Return the final values, their total, and maximal "
        "runs [start,end,value] including zero runs. Empty width has no runs. End is always exclusive.",
        '''
        def run(data):
            values = [0] * data['width']
            for start, end, value in data['writes']:
                for i in range(max(0, start), min(data['width'], end)):
                    values[i] = value
            runs = []
            for i, value in enumerate(values):
                if not runs or runs[-1][2] != value:
                    runs.append([i, i + 1, value])
                else:
                    runs[-1][1] = i + 1
            return {'values': values, 'total': sum(values), 'runs': runs}
        ''', "min(data['width'], end)", "min(data['width'], end + 1)"),
    CODING_FINAL[2]: ("deps[i] lists prerequisite indices of i (all in range, cycles and duplicates allowed). "
        "Find the transitive prerequisite closure of roots, including roots themselves. In that induced graph "
        "perform Kahn ordering, always picking the smallest ready index. Return order, blocked (remaining "
        "required indices sorted), and unused (indices outside closure sorted). A reachable cycle blocks its "
        "dependants but must not erase the already emitted acyclic prefix. Never schedule unrelated nodes.",
        '''
        def run(data):
            deps = [set(row) for row in data['deps']]
            needed, stack = set(), list(data['roots'])
            while stack:
                node = stack.pop()
                if node not in needed:
                    needed.add(node)
                    stack.extend(deps[node])
            remaining = set(needed)
            order = []
            while remaining:
                ready = sorted(node for node in remaining if not (deps[node] & remaining))
                if not ready:
                    break
                node = ready[0]
                remaining.remove(node)
                order.append(node)
            return {'order': order, 'blocked': sorted(remaining),
                    'unused': sorted(set(range(len(deps))) - needed)}
        ''', "stack.extend(deps[node])", "stack.extend([])"),
    CODING_FINAL[3]: ("Return the lexicographically smallest SHORTEST common supersequence of left and right. "
        "A subsequence preserves ordering but need not be contiguous. Also return greedy earliest embedding "
        "indices for left and right in the returned sequence. Repeated symbols must use distinct increasing "
        "positions. Empty sequences are legal. Alphabet ordering is normal a<b<c.",
        '''
        def run(data):
            left, right = data['left'], data['right']
            memo = {}
            def suffix(i, j):
                if i == len(left):
                    return right[j:]
                if j == len(right):
                    return left[i:]
                if (i, j) not in memo:
                    if left[i] == right[j]:
                        value = left[i] + suffix(i + 1, j + 1)
                    else:
                        options = [left[i] + suffix(i + 1, j), right[j] + suffix(i, j + 1)]
                        value = min(options, key=lambda item: (len(item), item))
                    memo[i, j] = value
                return memo[i, j]
            sequence = suffix(0, 0)
            def embed(word):
                cursor, indices = 0, []
                for char in word:
                    while sequence[cursor] != char:
                        cursor += 1
                    indices.append(cursor)
                    cursor += 1
                return indices
            return {'sequence': sequence, 'left_indices': embed(left), 'right_indices': embed(right)}
        ''', "key=lambda item: (len(item), item)", "key=lambda item: (item, len(item))"),
}

# One uniform, prospectively authorized pre-API adjustment. Each Coding starter
# has its original requested-behavior defect plus these two independently
# testable auxiliary/preservation defects. No reference, oracle, task count or
# scoring rule is changed. Never alter this bank after observing model results.
_EXTRA_STARTER_FAULTS = {
    CODING_DEV[0]: [
        ("len(data['ops'])", "len(set(op['key'] for op in data['ops']))", "operation_audit_count"),
        ("for k in sorted(state)", "for k in sorted(state, reverse=True)", "canonical_output_order")],
    CODING_DEV[1]: [
        ("balances = dict(data['initial'])", "balances = data['initial']", "input_preservation"),
        ("audit.append(sum(balances.values()))", "audit.append(balances[key])", "cross_channel_audit")],
    CODING_DEV[2]: [
        ("min(data['gross'], data['credit']) if data['eligible'] else 0", "min(data['gross'], data['credit'])", "credit_eligibility"),
        ("min(data['cap'], max(data['minimum'],", "max(data['minimum'], min(data['cap'],", "cap_precedence")],
    CODING_FINAL[0]: [
        ("'unspent': data['budget'] - best[1]", "'unspent': data['budget']", "budget_reconciliation"),
        ("'indices': best[2]", "'indices': list(reversed(best[2]))", "canonical_index_order")],
    CODING_FINAL[1]: [
        ("values[i] = value", "values[i] = value if value else values[i]", "zero_is_a_real_update"),
        ("'total': sum(values)", "'total': len(values)", "value_reconciliation")],
    CODING_FINAL[2]: [
        ("'unused': sorted(set(range(len(deps))) - needed)", "'unused': []", "unaffected_nodes_inventory"),
        ("'blocked': sorted(remaining)", "'blocked': []", "blocked_nodes_inventory")],
    CODING_FINAL[3]: [
        ("indices.append(cursor)", "indices.append(cursor + 1)", "embedding_index_contract"),
        ("sequence = suffix(0, 0)", "sequence = suffix(0, 0) + 'a'", "minimal_output_length")],
}


def _coding_inputs(family, variant):
    """Fixed covariates, never chosen from model results."""
    v = variant + 1
    if family == CODING_DEV[0]:
        schema = _obj({"base": _obj({key: _int(-20, 20) for key in "abc"}), "ops": _arr(_obj({
            "key": _word("abc"), "kind": _word(("set", "add", "delete")), "value": _int(-20, 20)}))})
        sequences = [[("a", "add", 2), ("a", "add", -1)], [("b", "delete", 0), ("b", "add", v)],
                     [("c", "set", 0), ("c", "add", 3)], [], [("a", "delete", 0), ("a", "delete", 0)],
                     [("b", "add", -3), ("a", "set", 7), ("b", "add", 5)],
                     [("c", "delete", 0), ("c", "set", -2), ("c", "add", -2)], [("a", "add", 0)]]
        return schema, [{"base": {"a": v, "b": 2, "c": -1},
                         "ops": [{"key": k, "kind": m, "value": x} for k, m, x in seq]} for seq in sequences]
    if family == CODING_DEV[1]:
        schema = _obj({"initial": _obj({key: _int(-10, 10) for key in "abc"}),
                       "events": _arr(_obj({"time": _int(), "channel": _word("abc"),
                                           "value": _int(-10, 10), "reset": {"type": "boolean"}}))})
        rows = [[(1, "a", v, False), (1, "a", 2, True)], [(3, "b", v, True), (3, "b", -1, False)],
                [(2, "a", 2, False), (1, "c", 3, False)], [], [(0, "b", 0, True)],
                [(2, "a", 1, True), (1, "a", 3, True), (2, "b", 4, False)],
                [(1, "a", 4, False), (1, "b", 2, True), (1, "a", -2, True)],
                [(2, "c", 2, True), (0, "c", 3, False), (2, "c", v, False)]]
        return schema, [{"initial": {"a": variant, "b": -variant, "c": variant + 1},
                         "events": [{"time": t, "channel": c, "value": x, "reset": r} for t, c, x, r in row]}
                        for row in rows]
    if family == CODING_DEV[2]:
        schema = _obj({**{k: _int(0, 200) for k in ("gross", "credit", "percent", "minimum", "cap")},
                       "eligible": {"type": "boolean"}})
        rows = [(40 + v, 20, 25, 0, 50, True), (20, 20, 80, 2, 30, True),
                (0, 5, 20, 4, 3, True), (10, 99, 25, 0, 100, False), (1, 0, 1, 0, 10, True),
                (100, 90, 100, 0, 3, True), (7, 8, 10, 6, 20, True), (35, 6, 17, 4, 10, True)]
        return schema, [dict(zip(("gross", "credit", "percent", "minimum", "cap", "eligible"),
                                (row[0] + variant, *row[1:]))) for row in rows]
    if family == CODING_FINAL[0]:
        schema = _obj({"items": _arr(_obj({"category": _word("abc"), "cost": _int(), "value": _int()}), 6),
                       "budget": _int()})
        rows = [([("a", 1, 5), ("a", 2, 6), ("b", 2, 4)], 4 + v),
                ([("b", 0, 3), ("b", 0, 4), ("c", 1, 2)], 1),
                ([("a", 3, 7), ("b", 2, 5), ("c", 2, 5)], 4), ([], 5),
                ([("a", 1, 0), ("b", 0, 0)], 1), ([("a", 2, 3), ("b", 2, 3)], 2),
                ([("a", 4, 7), ("a", 1, 2), ("b", 3, 6), ("c", 2, 3)], 5),
                ([("a", 1, 2), ("b", 1, 2)], 0)]
        return schema, [{"items": [dict(zip(("category", "cost", "value"), x)) for x in items], "budget": budget}
                        for items, budget in rows]
    if family == CODING_FINAL[1]:
        schema = _obj({"width": _int(0, 12), "writes": _arr({"type": "array", "items": _int(-5, 15),
                                                           "minItems": 3, "maxItems": 3})})
        rows = [(5 + v, [[0, 2, 3], [2, 4, 7]]), (5, [[0, 5, 4], [1, 3, 0]]),
                (0, [[-2, 3, 8]]), (4, [[-3, 8, 2]]), (4, [[1, 1, 9]]),
                (6, [[1, 5, -1], [2, 4, 2], [3, 6, 0]]), (3, []), (3, [[0, 3, 0]])]
        return schema, [{"width": width, "writes": writes} for width, writes in rows]
    if family == CODING_FINAL[2]:
        schema = _obj({"deps": _arr(_arr(_int(0, 5)), 6), "roots": _arr(_int(0, 5), 6)})
        rows = [([[], [0], [0], [1, 2]], [3]), ([[], [0], [1], []], [2]),
                ([[1], [0], [], [2], [1, 3]], [4]), ([[], []], []), ([[]], [0, 0]),
                ([[0]], [0]), ([[], [0, 0], [1], [0]], [2, 3]), ([], [])]
        return schema, [{"deps": deps, "roots": roots} for deps, roots in rows]
    schema = _obj({"left": {"type": "string", "enum": ["", "a", "b", "c", "ab", "ba", "ac", "ca", "aab", "bac", "aba", "bca"]},
                   "right": {"type": "string", "enum": ["", "a", "b", "c", "ab", "ba", "ac", "ca", "aab", "bac", "aba", "bca"]}})
    rows = [("ab", "ba"), ("bac", "aab"), ("", "aba"), ("aba", "aba"), ("ac", "ca"),
            ("bca", "aba"), ("aab", "ab"), ("c", "a"), ("", "")]
    if variant:
        rows = [(b, a) for a, b in rows]
    return schema, [{"left": a, "right": b} for a, b in rows]


def _coding_oracle(family, data):
    """Independent host algorithms; never eval/exec the reference source."""
    if family == CODING_DEV[0]:
        result = []
        for key in "abc":
            value = data["base"][key]
            for op in [x for x in data["ops"] if x["key"] == key]:
                value = None if op["kind"] == "delete" else op["value"] if op["kind"] == "set" else (
                    (0 if value is None else value) + op["value"])
            if value is not None:
                result.append([key, value])
        return {"settings": result, "total": sum(x[1] for x in result), "applied": len(data["ops"])}
    if family == CODING_DEV[1]:
        order = [i for time in sorted({e["time"] for e in data["events"]})
                 for i, event in enumerate(data["events"]) if event["time"] == time]
        history = {c: [data["initial"][c]] for c in "abc"}
        totals = []
        for i in order:
            event = data["events"][i]
            if event["reset"]:
                history[event["channel"]] = []
            history[event["channel"]].append(event["value"])
            totals.append(sum(sum(xs) for xs in history.values()))
        return {"balances": {key: sum(xs) for key, xs in history.items()}, "audit": totals, "order": order}
    if family == CODING_DEV[2]:
        applied = 0 if not data["eligible"] else sorted([data["gross"], data["credit"]])[0]
        basis = data["gross"] - applied
        whole, remainder = divmod(basis * data["percent"], 100)
        fee = max(whole + int(remainder != 0), data["minimum"])
        fee = data["cap"] if fee > data["cap"] else fee
        return {"basis": basis, "service": fee, "payable": basis + fee, "applied_credit": applied}
    if family == CODING_FINAL[0]:
        rows = []
        for flags in itertools.product((False, True), repeat=len(data["items"])):
            chosen = [i for i, yes in enumerate(flags) if yes]
            items = [data["items"][i] for i in chosen]
            cost = sum(x["cost"] for x in items)
            if len({x["category"] for x in items}) == len(items) and cost <= data["budget"]:
                rows.append((-sum(x["value"] for x in items), cost, chosen))
        value, cost, indices = min(rows)
        return {"indices": indices, "value": -value, "cost": cost, "unspent": data["budget"] - cost}
    if family == CODING_FINAL[1]:
        values = []
        for i in range(data["width"]):
            matching = [row[2] for row in data["writes"] if row[0] <= i < row[1]]
            values.append(matching[-1] if matching else 0)
        ends = [i for i in range(len(values)) if i == 0 or values[i] != values[i - 1]] + [len(values)]
        runs = [[a, b, values[a]] for a, b in zip(ends, ends[1:])]
        return {"values": values, "total": sum(values), "runs": runs}
    if family == CODING_FINAL[2]:
        needed = set(data["roots"])
        for _ in range(len(data["deps"])):
            needed |= {p for i in list(needed) for p in data["deps"][i]}
        order = []
        while True:
            choices = [i for i in sorted(needed) if i not in order and all(p in order for p in data["deps"][i])]
            if not choices:
                break
            order.append(choices[0])
        return {"order": order, "blocked": sorted(needed - set(order)),
                "unused": [i for i in range(len(data["deps"])) if i not in needed]}
    left, right = data["left"], data["right"]
    states = {(0, 0): ""}
    for size in range(len(left) + len(right) + 1):
        next_states = {}
        for (i, j), prefix in states.items():
            if i == len(left) and j == len(right):
                sequence = prefix
                def embedding(word):
                    cursor, positions = -1, []
                    for character in word:
                        cursor = sequence.index(character, cursor + 1)
                        positions.append(cursor)
                    return positions
                return {"sequence": sequence, "left_indices": embedding(left), "right_indices": embedding(right)}
            options = sorted(set(left[i:i + 1] + right[j:j + 1]))
            for character in options:
                key = (i + int(left[i:i + 1] == character), j + int(right[j:j + 1] == character))
                proposal = prefix + character
                if key not in next_states or proposal < next_states[key]:
                    next_states[key] = proposal
        states = dict(sorted(next_states.items(), key=lambda row: row[1]))
    raise AssertionError("Finite supersequence oracle failed")


def _coding(family, variant, split):
    description, source, old, new = _PROGRAMS[family]
    reference = _source(source)
    if reference.count(old) != 1:
        raise ValueError("Controlled starter anchor must be unique")
    starter = reference.replace(old, new, 1)
    for before, after, _role in _EXTRA_STARTER_FAULTS[family]:
        if reference.count(before) != 1 or starter.count(before) != 1:
            raise ValueError("Independent starter defect must match one unmodified reference anchor")
        starter = starter.replace(before, after, 1)
    schema, inputs = _coding_inputs(family, variant)
    # Instances differ in public examples/covariates, not independent family identity.
    public_indices = {variant % len(inputs), (variant + 1) % len(inputs)}
    cases = [{"label": f"v12-{family}-v{variant}-case{i}", "input": value,
              "expected": _coding_oracle(family, value), "exception": None, "public": i in public_indices,
              "dimension": "requested_behavior"} for i, value in enumerate(inputs)]
    contract = _contract()
    metadata = _metadata("coding", family, variant, split)
    metadata["public_contract"] = contract
    metadata["authored_starter_fault_count"] = 3
    metadata["starter_fault_roles"] = ["requested_behavior", *(row[2] for row in _EXTRA_STARTER_FAULTS[family])]
    metadata["prespecified_pre_api_adjustment"] = "v12-three-fault-starters-v1"
    return CodingAdapter(RepoTask(id=f"repo-v12-{split}-{family}-{variant}", split=split, family=family,
        cluster_id=f"v12-coding-{family}", prompt="Repair the supplied implementation. " + description +
            " Preserve the supplied input recursively, the protected api.py bytes, and every specified auxiliary "
            "output. Only logic.py is editable. Input obeys input_domain; graph indices are additionally in range. "
            "No I/O, dynamic execution, external packages or additional modules. "
            "A starter is a deliberately imperfect public fixture, not a previous model answer.",
        files={"api.py": ENTRY, "logic.py": starter}, reference_files={"api.py": ENTRY, "logic.py": reference},
        editable_paths=["logic.py"], input_domain=schema,
        public_cases=[row for row in cases if row["public"]], private_cases=[row for row in cases if not row["public"]],
        metadata=metadata))


_SHEETS = {
    SHEET_DEV[0]: (
        "A1 is goods, A2 credit, A3 eligibility flag (0/1), A4 fixed service, A5 service cap, A6 tax rate, "
        "A7 audit multiplier. B1 applies eligible credit to GOODS ONLY, never service or tax, capped by A1. "
        "Protected B2 is remaining goods. B3 is min(service,service cap). B4 taxes remaining goods, not service. "
        "Protected C1 totals B2+B3+B4; C2 reconciles C1*A7+B1.",
        {"B1": "=IF(A3==1,MIN(A1,A2),0)", "B2": "=A1-B1", "B3": "=MIN(A4,A5)",
         "B4": "=B2*A6", "C1": "=B2+B3+B4", "C2": "=C1*A7+B1"},
        {"B1": "=MIN(A1+A4,A2)", "B3": "=A4", "B4": "=A1*A6"}),
    SHEET_DEV[1]: (
        "A1 is current nonnegative profit, A2 old loss bank, A3 newly recognized loss, A4 deduction cap, "
        "A5 tax rate, A6 prepaid tax, A7 audit multiplier. B1 deduction is limited by profit, TOTAL old+new "
        "loss, and cap. Protected B2 is taxable profit. B3 is unused total loss carried forward (not negative). "
        "B4 is extra tax due after prepaid tax, floored at zero; unused prepayment is NOT a new carried loss. "
        "Protected C1=B2*A5 and C2=B3+B1 reconcile tax and loss conservation.",
        {"B1": "=MIN(A1,A2+A3,A4)", "B2": "=A1-B1", "B3": "=A2+A3-B1",
         "B4": "=MAX(0,B2*A5-A6)", "C1": "=B2*A5", "C2": "=B3+B1"},
        {"B1": "=MIN(A1,A2,A4)", "B3": "=MAX(0,A2-B1)", "B4": "=B2*A5-A6"}),
    SHEET_DEV[2]: (
        "A1 is old escrow, A2 submitted bill, A3 disputed amount, A4 new deposit, A5 release cap, "
        "A6 penalty request, A7 audit multiplier. Protected B1 is old escrow plus deposit. B2 is undisputed "
        "bill floored at zero. B3 release is capped by B2, available escrow, AND A5. B4 penalty is taken "
        "AFTER release and capped by remaining escrow. Protected C1 is ending escrow; C2 is ending+release+"
        "penalty-deposit and must equal old escrow. Unused bill is not an escrow deduction.",
        {"B1": "=A1+A4", "B2": "=MAX(0,A2-A3)", "B3": "=MIN(B1,B2,A5)",
         "B4": "=MIN(A6,MAX(0,B1-B3))", "C1": "=B1-B3-B4", "C2": "=C1+B3+B4-A4"},
        {"B2": "=A2-A3", "B3": "=MIN(B1,B2)", "B4": "=MIN(A6,B1)"}),
    SHEET_FINAL[0]: (
        "A1 is daily capacity, A2 reserved capacity unavailable to all work, A3 old urgent backlog, "
        "A4 new urgent arrivals, A5 old normal backlog, A6 new normal arrivals, A7 audit multiplier. "
        "Protected B1 is usable capacity max(A1-A2,0). B2 serves old urgent first. B3 serves new urgent from "
        "remaining capacity. B4 serves OLD normal next; B5 serves new normal last. Each service is capped by "
        "its own demand and remaining capacity. C1 protected total served and C2 unserved count retain all classes.",
        {"B1": "=MAX(0,A1-A2)", "B2": "=MIN(A3,B1)", "B3": "=MIN(A4,MAX(0,B1-B2))",
         "B4": "=MIN(A5,MAX(0,B1-B2-B3))", "B5": "=MIN(A6,MAX(0,B1-B2-B3-B4))",
         "C1": "=B2+B3+B4+B5", "C2": "=A3+A4+A5+A6-C1"},
        {"B2": "=MIN(A3,A1)", "B3": "=MIN(A4,B1)", "B4": "=MIN(A5,B1)", "B5": "=MIN(A6,B1)"}),
    SHEET_FINAL[1]: (
        "A1 is foreign principal, A2 foreign discount, A3 foreign-to-local exchange rate (>0), "
        "A4 local fixed fee, A5 local fee cap, A6 local flat rebate, A7 audit multiplier. B1 foreign net is "
        "max(principal-discount,0); B2 converts net then rounds ONCE to two decimals using runtime ties-to-even. "
        "B3 caps the LOCAL fee without converting it. B4 applies local rebate only to converted principal, "
        "capped by B2; it cannot rebate the fee. Protected C1 payable=B2+B3-B4, C2=C1*A7+B4.",
        {"B1": "=MAX(0,A1-A2)", "B2": "=ROUND(B1*A3,2)", "B3": "=MIN(A4,A5)",
         "B4": "=MIN(A6,B2)", "C1": "=B2+B3-B4", "C2": "=C1*A7+B4"},
        {"B1": "=A1-A2", "B2": "=ROUND(A1*A3,2)-A2", "B3": "=MIN(A4*A3,A5)", "B4": "=MIN(A6,B2+B3)"}),
    SHEET_FINAL[2]: (
        "A1/A2 are component scores (nonnegative), A3/A4 their weights, A5 penalty, A6 score ceiling, "
        "A7 audit multiplier. B1 includes each score capped at ceiling then weighted. Protected B2 is total "
        "weight. B3 is zero if weight sum is zero, otherwise B1/B2. B4 subtracts penalty AFTER normalization "
        "and clamps at zero; penalty does not change weights. Protected C1=B4*A7 and C2=B1+B2 retain audits.",
        {"B1": "=MIN(A1,A6)*A3+MIN(A2,A6)*A4", "B2": "=A3+A4", "B3": "=IF(B2==0,0,B1/B2)",
         "B4": "=MAX(0,B3-A5)", "C1": "=B4*A7", "C2": "=B1+B2"},
        {"B1": "=MIN(A1*A3+A2*A4,A6)", "B3": "=IF(B2==0,0,(B1-A5)/B2)", "B4": "=B3-A5"}),
    SHEET_FINAL[3]: (
        "A1 is eligible project cost, A2 already funded cost, A3 match ratio, A4 sponsor cap, "
        "A5 own-funds balance, A6 minimum own-funds reserve, A7 audit multiplier. B1 unfunded cost is "
        "max(cost-already funded,0). B2 own contribution is limited by unfunded cost and own funds AFTER "
        "protecting the reserve. B3 sponsor contribution is limited by B2*ratio, sponsor cap, AND residual "
        "unfunded cost after own contribution. B4 remains unfunded; C1 ending own funds and C2 funding "
        "conservation are protected. Sponsor never causes total contributions to exceed unfunded cost.",
        {"B1": "=MAX(0,A1-A2)", "B2": "=MIN(B1,MAX(0,A5-A6))", "B3": "=MIN(B2*A3,A4,MAX(0,B1-B2))",
         "B4": "=B1-B2-B3", "C1": "=A5-B2", "C2": "=B2+B3+B4"},
        {"B1": "=A1-A2", "B2": "=MIN(B1,A5)", "B3": "=MIN(B2*A3,A4)", "B4": "=MAX(0,B1-B3)"}),
}


def _sheet_oracle(family, a):
    x = [a[f"A{i}"] for i in range(1, 8)]
    if family == SHEET_DEV[0]:
        goods, credit, eligible, fee, cap, tax, factor = x
        deduction = sorted([goods, credit])[0] if eligible else 0
        b = [deduction, goods - deduction, sorted([fee, cap])[0], (goods - deduction) * tax]
        c = [b[1] + b[2] + b[3], (b[1] + b[2] + b[3]) * factor + deduction]
    elif family == SHEET_DEV[1]:
        profit, old, new, cap, tax, prepaid, _ = x
        deduction = sorted([profit, old + new, cap])[0]
        due = (profit - deduction) * tax - prepaid
        b = [deduction, profit - deduction, old + new - deduction, due if due > 0 else 0]
        c = [b[1] * tax, old + new]
    elif family == SHEET_DEV[2]:
        old, bill, dispute, deposit, cap, penalty, _ = x
        available = old + deposit
        claim = bill - dispute if bill > dispute else 0
        release = sorted([available, claim, cap])[0]
        taken_penalty = sorted([penalty, available - release])[0]
        b = [available, claim, release, taken_penalty]
        c = [available - release - taken_penalty, old]
    elif family == SHEET_FINAL[0]:
        capacity, reserve, *rest = x
        available = capacity - reserve if capacity > reserve else 0
        remaining, services = available, []
        for demand in rest[:4]:
            given = demand if demand < remaining else remaining
            services.append(given)
            remaining -= given
        b, c = [available, *services], [sum(services), sum(rest[:4]) - sum(services)]
    elif family == SHEET_FINAL[1]:
        principal, discount, rate, fee, cap, rebate, factor = x
        net = principal - discount if principal > discount else 0
        converted = round(net * rate, 2)
        local_fee, actual_rebate = sorted([fee, cap])[0], sorted([rebate, converted])[0]
        b = [net, converted, local_fee, actual_rebate]
        payable = converted + local_fee - actual_rebate
        c = [payable, payable * factor + actual_rebate]
    elif family == SHEET_FINAL[2]:
        left, right, wleft, wright, penalty, cap, factor = x
        weighted = sum((score if score < cap else cap) * weight for score, weight in ((left, wleft), (right, wright)))
        average = weighted / (wleft + wright) if wleft + wright else 0
        final = average - penalty if average > penalty else 0
        b, c = [weighted, wleft + wright, average, final], [final * factor, weighted + wleft + wright]
    else:
        cost, funded, ratio, cap, own, reserve, _ = x
        unfunded, usable = max(cost - funded, 0), max(own - reserve, 0)
        contribution = min(unfunded, usable)
        sponsor = min(contribution * ratio, cap, unfunded - contribution)
        b = [unfunded, contribution, sponsor, unfunded - contribution - sponsor]
        c = [own - contribution, unfunded]
    return {**{f"B{i + 1}": value for i, value in enumerate(b)}, "C1": c[0], "C2": c[1]}


def _sheet_inputs(family, variant):
    v = variant + 1
    rows = [(20 + v, 8, 1, 5, 3, 0.2, 3), (3, 10, 1, 4, 2, 0.5, 2),
            (0, 0, 0, 0, 0, 0, 1), (50, 4, 0, 10, 7, 0.1, 5),
            (12, 5, 1, 2, 8, 0, 1), (7, 6, 1, 3, 0, 1, 4),
            (100, 200, 0, 30, 20, 0.15, 2), (11, 11, 1, 7, 6, 0.3, 3)]
    if family == SHEET_DEV[1]:
        rows = [(20 + v, 4, 8, 30, 0.2, 1, 2), (5, 0, 10, 4, 0.4, 0, 3),
                (0, 10, 4, 30, 0.2, 3, 1), (12, 2, 0, 3, 0.3, 8, 2),
                (30, 5, 10, 4, 0.5, 0, 4), (10, 20, 20, 0, 0.1, 0, 1),
                (10, 0, 0, 20, 0.2, 4, 5), (20, 10, 5, 30, 0.25, 0, 3)]
    elif family == SHEET_DEV[2]:
        rows = [(10 + v, 20, 3, 4, 6, 8, 1), (3, 20, 5, 0, 30, 7, 2),
                (10, 4, 8, 2, 5, 20, 3), (0, 3, 0, 0, 4, 6, 1),
                (20, 5, 0, 10, 30, 2, 2), (5, 20, 1, 3, 0, 4, 4),
                (12, 7, 7, 0, 3, 0, 1), (10, 30, 10, 10, 30, 5, 3)]
    elif family == SHEET_FINAL[0]:
        rows = [(20 + v, 5, 6, 7, 8, 9, 1), (10, 20, 5, 3, 8, 2, 2),
                (30, 0, 0, 20, 8, 9, 3), (5, 0, 10, 10, 10, 10, 1),
                (50, 5, 2, 3, 4, 5, 2), (10, 2, 2, 0, 7, 7, 4),
                (0, 0, 3, 0, 0, 4, 1), (11, 3, 2, 2, 2, 2, 2)]
    elif family == SHEET_FINAL[1]:
        rows = [(20 + v, 5, 1.25, 3, 2, 30, 2), (4, 8, 2, 5, 8, 2, 3),
                (0, 0, 1.5, 3, 1, 4, 2), (1.01, 0.2, 1.234, 2, 3, 0.4, 1),
                (20, 2, 0.5, 5, 3, 0, 4), (2, 0, 3, 8, 0, 20, 2),
                (10, 10, 1, 4, 4, 4, 1), (7.5, 3.2, 1.125, 3, 4, 1, 3)]
    elif family == SHEET_FINAL[2]:
        rows = [(80 + v, 30, 2, 3, 7, 50, 2), (10, 20, 0, 0, 3, 100, 3),
                (5, 8, 2, 1, 30, 10, 1), (100, 100, 1, 1, 0, 30, 4),
                (0, 90, 0, 2, 3, 100, 2), (10, 20, 3, 2, 4, 0, 1),
                (100, 0, 0, 3, 0, 20, 5), (30, 50, 2, 5, 8, 40, 3)]
    elif family == SHEET_FINAL[3]:
        rows = [(30 + v, 5, 2, 30, 12, 3, 1), (10, 20, 1, 5, 8, 2, 3),
                (20, 0, 3, 30, 8, 20, 2), (20, 5, 2, 30, 30, 0, 1),
                (100, 10, 0, 10, 20, 5, 4), (0, 0, 2, 30, 10, 0, 3),
                (40, 5, 3, 2, 10, 4, 2), (10, 0, 10, 100, 3, 0, 1)]
    # Change a semantically used input in EVERY development instance; selection
    # does not merely relabel an identical bank of training test inputs.
    return [{f"A{i + 1}": value + (variant if i == 0 else 0) for i, value in enumerate(row)} for row in rows]


def _sheet(family, variant, split):
    description, reference, defects = _SHEETS[family]
    inputs = _sheet_inputs(family, variant)
    public_indices = {variant % len(inputs), (variant + 1) % len(inputs)}
    identifier = f"v12-sheet-{split}-{family}-{variant}"
    cases = [{"id": f"{identifier}-case{i}", "overrides": deepcopy(row), "expected": _sheet_oracle(family, row)}
             for i, row in enumerate(inputs)]
    return NativeAdapter({"id": identifier, "domain": "spreadsheet", "split": split,
        "family": family, "cluster_id": f"v12-sheet-{family}", "contract": _contract(),
        "prompt": "Repair this workbook under the following exact new specification. " + description +
            " All quantities are nonnegative, except no negative quantity is needed here. "
            "Every listed editable formula may require a repair. All noneditable formulas must remain unchanged. "
            "Check intermediate values and downstream audits, not just the answer cell. "
            "The corrected formula graph must work for every legal input substitution.",
        "inputs": deepcopy(inputs[0]), "formulas": {**reference, **defects}, "editable_cells": list(defects),
        "answer_cell": "C1", "reference_artifact": {"formulas": {k: reference[k] for k in defects}},
        "public_cases": [row for i, row in enumerate(cases) if i in public_indices],
        "hidden_cases": [row for i, row in enumerate(cases) if i not in public_indices],
        "metadata": _metadata("spreadsheet", family, variant, split)})


_RULES = {
    RULE_FINAL[0]: (
        ("owner_ok", "identity_ok", "trained", "local_scope", "delegated", "sponsor_ok", "export_scope", "custody_ok"),
        [("identity", ["owner_ok", "identity_ok"], "identified"),
         ("training", ["identified", "trained"], "qualified"),
         ("local", ["qualified", "local_scope"], "local_allowed"),
         ("delegate", ["identified", "delegated", "sponsor_ok"], "delegation_allowed"),
         ("export_local", ["local_allowed", "export_scope", "custody_ok"], "export_allowed"),
         ("export_delegate", ["delegation_allowed", "export_scope", "custody_ok"], "export_allowed"),
         ("custody_audit", ["identified", "custody_ok"], "custody_auditable"),
         ("sponsor_audit", ["qualified", "sponsor_ok"], "sponsor_auditable")],
        {"training": ["owner_ok", "trained"], "delegate": ["delegated", "sponsor_ok"],
         "export_local": ["local_allowed", "export_scope"], "export_delegate": ["delegation_allowed", "custody_ok"]},
        "identified needs owner_ok AND identity_ok. qualified additionally needs trained. local_allowed needs "
        "qualified AND local_scope. delegation_allowed instead needs identified AND delegated AND sponsor_ok, "
        "and does not require trained/local_scope. Either local_allowed OR delegation_allowed can support export, "
        "but export_allowed ALWAYS additionally requires BOTH export_scope and custody_ok. Independently, "
        "custody_auditable needs identified AND custody_ok; sponsor_auditable needs qualified AND sponsor_ok."),
    RULE_FINAL[1]: (
        ("power_ok", "sensor_ok", "safe_mode", "manual_key", "operator_ok", "audit_ok", "warm", "cool"),
        [("ready", ["power_ok", "sensor_ok"], "machine_ready"),
         ("operator", ["operator_ok", "audit_ok"], "authorized"),
         ("normal", ["machine_ready", "safe_mode", "warm"], "normal_path"),
         ("override", ["machine_ready", "manual_key", "authorized"], "override_path"),
         ("run_normal", ["normal_path", "authorized"], "run_allowed"),
         ("run_override", ["override_path", "cool"], "run_allowed"),
         ("log", ["operator_ok", "audit_ok", "sensor_ok"], "log_allowed"),
         ("service", ["machine_ready", "cool", "safe_mode"], "service_allowed")],
        {"normal": ["machine_ready", "warm"], "override": ["manual_key", "authorized"],
         "run_normal": ["normal_path"], "run_override": ["override_path"]},
        "machine_ready needs power_ok AND sensor_ok; authorized needs operator_ok AND audit_ok. normal_path "
        "needs machine_ready AND safe_mode AND warm. override_path needs machine_ready AND manual_key AND "
        "authorized. run_allowed requires either normal_path AND authorized, or override_path AND cool. "
        "Manual override replaces normal safe/warm conditions, not readiness, operator/audit, or cooling. "
        "Independent log_allowed requires operator_ok, audit_ok and sensor_ok, even without power. "
        "service_allowed requires machine_ready AND cool AND safe_mode, not authorization or warm."),
    RULE_FINAL[2]: (
        ("left_id", "left_check", "right_id", "right_check", "distinct_sources", "timestamp_ok", "review_seal", "permit"),
        [("left", ["left_id", "left_check"], "left_valid"),
         ("right", ["right_id", "right_check"], "right_valid"),
         ("cross", ["left_valid", "right_valid", "distinct_sources"], "cross_valid"),
         ("timely", ["cross_valid", "timestamp_ok"], "timely_valid"),
         ("action", ["timely_valid", "permit"], "action_allowed"),
         ("archive_left", ["left_valid", "review_seal"], "archive_allowed"),
         ("archive_right", ["right_valid", "review_seal"], "archive_allowed"),
         ("audit", ["cross_valid", "review_seal"], "cross_auditable")],
        {"cross": ["left_valid", "right_valid"], "timely": ["cross_valid"],
         "action": ["timely_valid"], "archive_right": ["right_id", "review_seal"]},
        "left_valid requires left_id AND left_check; right_valid requires right_id AND right_check. "
        "cross_valid requires BOTH valid sources AND distinct_sources. timely_valid additionally requires "
        "timestamp_ok. action_allowed needs timely_valid AND permit, not review_seal. archive_allowed needs "
        "at least one individually VALID source AND review_seal; it does not require distinct_sources, timestamp "
        "or permit. cross_auditable needs cross_valid AND review_seal, even if timestamp/permit are absent."),
    RULE_FINAL[3]: (
        ("origin_ok", "destination_ok", "customs_ok", "bond_posted", "bond_reviewed", "health_ok", "insurance_ok", "audit_signed"),
        [("route", ["origin_ok", "destination_ok"], "route_ready"),
         ("ordinary", ["route_ready", "customs_ok"], "ordinary_ready"),
         ("bond", ["bond_posted", "bond_reviewed"], "bond_ready"),
         ("bonded_route", ["route_ready", "bond_ready"], "bonded_ready"),
         ("import_ordinary", ["ordinary_ready", "health_ok", "insurance_ok"], "import_allowed"),
         ("import_bonded", ["bonded_ready", "health_ok", "insurance_ok"], "import_allowed"),
         ("audit", ["route_ready", "audit_signed"], "route_auditable"),
         ("claim", ["bond_ready", "insurance_ok"], "bond_claimable")],
        {"bond": ["bond_posted"], "bonded_route": ["bond_ready"],
         "import_ordinary": ["ordinary_ready", "health_ok"], "import_bonded": ["bonded_ready", "insurance_ok"]},
        "route_ready requires origin_ok AND destination_ok. ordinary_ready also needs customs_ok. bond_ready "
        "requires BOTH bond_posted and bond_reviewed. bonded_ready needs route_ready AND bond_ready. "
        "import_allowed needs either ordinary_ready OR bonded_ready, plus BOTH health_ok AND insurance_ok. "
        "Bond replaces customs approval only, not route, health or insurance obligations. Independent "
        "route_auditable needs route_ready AND audit_signed; bond_claimable needs bond_ready AND insurance_ok "
        "without requiring route/customs/health.")}


def _rule_oracle(family, facts):
    """Independent Boolean definitions, not the reference forward-chain engine."""
    has = set(facts).__contains__
    if family == RULE_FINAL[0]:
        identified = has("owner_ok") and has("identity_ok")
        qualified = identified and has("trained")
        local = qualified and has("local_scope")
        delegated = identified and has("delegated") and has("sponsor_ok")
        result = {"identified": identified, "qualified": qualified, "local_allowed": local,
                  "delegation_allowed": delegated, "export_allowed": (local or delegated) and has("export_scope") and has("custody_ok"),
                  "custody_auditable": identified and has("custody_ok"), "sponsor_auditable": qualified and has("sponsor_ok")}
    elif family == RULE_FINAL[1]:
        ready = has("power_ok") and has("sensor_ok")
        authorized = has("operator_ok") and has("audit_ok")
        normal = ready and has("safe_mode") and has("warm")
        override = ready and has("manual_key") and authorized
        result = {"machine_ready": ready, "authorized": authorized, "normal_path": normal, "override_path": override,
                  "run_allowed": (normal and authorized) or (override and has("cool")),
                  "log_allowed": authorized and has("sensor_ok"),
                  "service_allowed": ready and has("cool") and has("safe_mode")}
    elif family == RULE_FINAL[2]:
        left, right = has("left_id") and has("left_check"), has("right_id") and has("right_check")
        cross = left and right and has("distinct_sources")
        timely = cross and has("timestamp_ok")
        result = {"left_valid": left, "right_valid": right, "cross_valid": cross, "timely_valid": timely,
                  "action_allowed": timely and has("permit"), "archive_allowed": (left or right) and has("review_seal"),
                  "cross_auditable": cross and has("review_seal")}
    else:
        route = has("origin_ok") and has("destination_ok")
        ordinary = route and has("customs_ok")
        bond = has("bond_posted") and has("bond_reviewed")
        bonded = route and bond
        result = {"route_ready": route, "ordinary_ready": ordinary, "bond_ready": bond, "bonded_ready": bonded,
                  "import_allowed": (ordinary or bonded) and has("health_ok") and has("insurance_ok"),
                  "route_auditable": route and has("audit_signed"), "bond_claimable": bond and has("insurance_ok")}
    return sorted(key for key, value in result.items() if value)


def _rule(family, variant, split):
    primitives, declarations, defects, description = _RULES[family]
    # A fixed permutation changes public starting facts and file order only;
    # these instances deliberately remain in ONE common structural cluster.
    reference = [{"id": identifier, "if": list(premises), "then": conclusion}
                 for identifier, premises, conclusion in declarations]
    if variant:
        reference = reference[variant:] + reference[:variant]
    initial = [{**rule, "if": defects.get(rule["id"], rule["if"])} for rule in reference]
    derived = sorted({rule["then"] for rule in reference})
    identifier = f"v12-rule-{split}-{family}-{variant}"
    facts = [[key for key, flag in zip(primitives, flags) if flag]
             for flags in itertools.product((False, True), repeat=len(primitives))]
    public_indices = {0, len(facts) - 1, 1 << variant}
    cases = [{"id": f"{identifier}-case{i}", "facts": row, "expected": _rule_oracle(family, row)}
             for i, row in enumerate(facts)]
    return NativeAdapter({"id": identifier, "domain": "rule_reasoning", "split": split,
        "family": family, "cluster_id": f"v12-rule-{family}", "contract": _contract(),
        "prompt": "Repair the bounded positive-rule policy to this complete contract. " + description +
            " Primitive facts may be present independently in any subset; absence is not a negative fact. "
            "Preserve every protected rule exactly. Return every original rule ID once. Only editable premises "
            "or conclusions may change. All requested intermediate AND terminal facts are evaluated, not just "
            "a single end permission. The artifact must work after every legal primitive-fact substitution.",
        "rules": initial, "editable_rule_ids": list(defects), "vocabulary": list(primitives) + derived,
        "initial_facts": deepcopy(facts[(1 << variant)]), "answer_facts": derived,
        "reference_artifact": {"rules": reference},
        "public_cases": [row for i, row in enumerate(cases) if i in public_indices],
        "hidden_cases": [row for i, row in enumerate(cases) if i not in public_indices],
        "metadata": _metadata("rule_reasoning", family, variant, split)})


def payload(adapter):
    """HOST-ONLY complete source; includes references/hidden cases, never model input."""
    return adapter.task.to_dict() if isinstance(adapter, CodingAdapter) else deepcopy(adapter.task)


def public_payload(adapter):
    """The frozen V8 public projection, plus explicit public Coding contract."""
    from skillopt.coevolution_v8.feedback_study import public_task

    public = public_task(adapter)
    if isinstance(adapter, CodingAdapter):
        public["domain"] = "coding"
        public["contract"] = deepcopy(adapter.task.metadata["public_contract"])
    return public


def build_panel(smoke=False):
    if type(smoke) is not bool:
        raise ValueError("smoke must be an explicit boolean")
    train, selection = [], []
    for round_index in range(3):
        train.append([_coding(CODING_DEV[round_index], variant, "development") for variant in (0, 1)] +
                     [_sheet(SHEET_DEV[round_index], variant, "development") for variant in (0, 1)])
        selection.append([_coding(CODING_DEV[round_index], variant, "selection") for variant in (2, 3)] +
                         [_sheet(SHEET_DEV[round_index], variant, "selection") for variant in (2, 3)])
    if smoke:
        # Never construct the formal final pool for smoke. The audit examples
        # are additional development instances, explicitly marked as such.
        small_train = [train[0][0], train[0][2]]
        small_selection = [_coding(CODING_DEV[0], 2, "selection"), _sheet(SHEET_DEV[0], 2, "selection")]
        small_final = [_coding(CODING_DEV[0], 3, "final"), _sheet(SHEET_DEV[0], 3, "final")]
        for adapter in [*small_train, *small_selection, *small_final]:
            meta = adapter.task.metadata if isinstance(adapter, CodingAdapter) else adapter.task["metadata"]
            meta["smoke_development_only"] = True
            meta["origin"] = "development_family_smoke_control_not_formal_heldout"
        return {"train": [small_train], "selection": [small_selection], "final": small_final}
    final = ([_coding(family, variant, "final") for family in CODING_FINAL for variant in range(3)] +
             [_sheet(family, variant, "final") for family in SHEET_FINAL for variant in range(3)] +
             [_rule(family, variant, "final") for family in RULE_FINAL for variant in range(3)])
    return {"train": train, "selection": selection, "final": final}


def panel_manifest(panel):
    """Identity-only provenance. Does not serialize questions, artifacts or gold."""
    def record(adapter):
        row = payload(adapter)
        return {"task_id": row["id"], "domain": adapter.domain, "family": row["family"],
                "cluster_id": row["cluster_id"], "split": row["split"], "task_hash": digest(row),
                "public_hash": digest(public_payload(adapter))}
    return {"version": VERSION, "seed": SEED, "synthetic_not_public_benchmark": True,
            "development_selection_shares_family_not_unseen_family_evidence": True,
            "train": [[record(a) for a in batch] for batch in panel["train"]],
            "selection": [[record(a) for a in batch] for batch in panel["selection"]],
            "final": [record(a) for a in panel["final"]]}


def artifact_controls(adapter):
    """Host-only controls for sandbox/native preflight, never sent to a solver."""
    if isinstance(adapter, CodingAdapter):
        reference = deepcopy(adapter.task.reference_files)
        semantic = {**reference, "logic.py": "def run(data):\n    return {'v12_control_wrong': True}\n"}
        preserved = reference["logic.py"].replace("def run(data):", "def compute(data):", 1)
        preservation = {**reference, "logic.py": preserved +
            "\ndef run(data):\n    result = compute(data)\n    data['v12_forbidden_write'] = 1\n    return result\n"}
        return {"reference": reference, "starter": deepcopy(adapter.task.files),
                "semantic_mutant": semantic, "preservation_mutant": preservation}
    reference = deepcopy(adapter.task["reference_artifact"])
    if adapter.domain == "spreadsheet":
        starter = {"formulas": {k: adapter.task["formulas"][k] for k in adapter.task["editable_cells"]}}
        semantic = deepcopy(reference)
        first = adapter.task["editable_cells"][0]
        semantic["formulas"][first] = "=999999"
        preservation = deepcopy(reference)
        protected = next(k for k in adapter.task["formulas"] if k not in adapter.task["editable_cells"])
        preservation["formulas"][protected] = "=0"
    else:
        starter = {"rules": deepcopy(adapter.task["rules"])}
        semantic = deepcopy(reference)
        first = adapter.task["editable_rule_ids"][0]
        next(rule for rule in semantic["rules"] if rule["id"] == first)["if"] = [adapter.task["answer_facts"][0]]
        preservation = deepcopy(reference)
        protected = next(rule for rule in preservation["rules"] if rule["id"] not in adapter.task["editable_rule_ids"])
        protected["if"] = [adapter.task["answer_facts"][0]]
    return {"reference": reference, "starter": starter, "semantic_mutant": semantic, "preservation_mutant": preservation}


def self_check(panel, *, coding=True):
    """Pre-API host check. Python references/controls run ONLY in existing OS sandbox.

    Returns aggregate/identity diagnostics only. Does not call a model, resample
    tasks, select by performance, write artifacts or suppress failing controls.
    """
    from skillopt.coevolution_v3 import executor

    seen, rows = set(), []
    all_tasks = [a for group in (panel["train"], panel["selection"]) for batch in group for a in batch] + panel["final"]
    for adapter in all_tasks:
        task = payload(adapter)
        if task["id"] in seen:
            raise ValueError("Duplicate task ID across partitions")
        seen.add(task["id"])
        controls = artifact_controls(adapter)
        if adapter.domain == "coding" and not coding:
            continue
        scores = {}
        for name, artifact in controls.items():
            if adapter.domain == "coding":
                result = executor.evaluate(adapter.task, {"files": {k: artifact[k] for k in adapter.task.editable_paths}})
                good = result.get("hard") is True
                available = result.get("execution_ok") is True and result.get("hard") is not None
            else:
                result = adapter.evaluate(artifact)
                good, available = result["score"] == 1, result["score"] is not None
            scores[name] = {"passed": good, "available": available}
        if not scores["reference"]["passed"] or scores["starter"]["passed"] or scores["semantic_mutant"]["passed"]:
            raise ValueError("Reference/starter/semantic preflight failed: " + task["id"])
        if scores["preservation_mutant"]["passed"]:
            raise ValueError("Preservation control passed unexpectedly: " + task["id"])
        if not scores["starter"]["available"] or not scores["semantic_mutant"]["available"]:
            raise ValueError("Semantic controls must be valid executable artifacts: " + task["id"])
        rows.append({"task_id": task["id"], "domain": adapter.domain, "task_hash": digest(task), "controls": scores})
    return {"version": VERSION + "-preflight", "all_checked": True, "checked_tasks": len(rows),
            "coding_checked": bool(coding), "model_api_calls": 0, "records": rows}
