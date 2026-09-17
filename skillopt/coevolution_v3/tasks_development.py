"""Six original development repositories with independently written case oracles.

Native reference source is never executed to manufacture expected outcomes.
The shared API scaffolding is intentional and recorded as a dependence limit;
the six application operations and boundary contracts are different.
"""

from __future__ import annotations

import itertools
import textwrap
from copy import deepcopy


def _object(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


def _integer(low=0, high=20):
    return {"type": "integer", "minimum": low, "maximum": high}


def _array(items, maximum=6):
    return {"type": "array", "items": items, "maxItems": maximum}


def _enum(*values):
    return {"enum": list(values)}


def _function(name, body):
    return "def " + name + "(data):\n" + textwrap.indent(textwrap.dedent(body).strip(), "    ") + "\n"


def _files(old, new=None, *, alternative=False, preservation_mutant=False):
    policy = "from copy import deepcopy\n\n" + _function("old_policy", old)
    if new is None:
        policy += "\ndef plan(data):\n    return old_policy(data)\n"
        engine = "from policy import plan\n\ndef run(data):\n    result = plan(data)\n    return {'result': result, 'api_version': 1}\n"
        api = "import engine\nimport policy\n\ndef solve(data):\n    if data['action'] == 'direct':\n        return policy.plan(data)\n    return engine.run(data)\n"
    else:
        policy += "\n" + _function("new_policy", new)
        dispatch = "new_policy(data)" if preservation_mutant else "new_policy(data) if current else old_policy(data)"
        policy += "\ndef plan(data, current=False):\n    return " + dispatch + "\n"
        engine = "from policy import plan\n\ndef run(data, current=False):\n    result = plan(data, current=current)\n    return {'result': result, 'api_version': 1}\n"
        api = "import engine\nimport policy\n\ndef solve(data):\n    if data['action'] == 'direct':\n        return policy.plan(data)\n    return engine.run(data, current=data['action'] == 'apply')\n"
        if alternative:
            api = "import engine\nimport policy\n\ndef solve(data):\n    requested = data['action'] == 'apply'\n    if data['action'] == 'direct':\n        return policy.plan(data)\n    if not requested:\n        return engine.run(data)\n    value = policy.plan(data, current=True)\n    return {'api_version': 1, 'result': value}\n"
    return {"api.py": api, "engine.py": engine, "policy.py": policy}


def _project(slug, context, schema, samples, old, local, replacement, contracts, oracle, validator=None):
    inputs = [{"action": action, **deepcopy(sample)} for sample in samples for action in ("apply", "legacy", "direct")]
    domain = _object({"action": _enum("apply", "legacy", "direct"), **schema})
    modes = {}
    common = (
        "This repository has three independently imported modules: api dispatches requests, engine "
        "wraps the published result, and policy owns the operation. action='apply' uses the requested "
        "new policy; action='legacy' must retain the old engine.run(data) behavior and wrapper; "
        "action='direct' must retain policy.plan(data)'s old default behavior and unwrapped result. "
        "engine.run(data) and policy.plan(data) remain callable with their original signatures. "
        "Non-direct results are exactly {'result': policy_result, 'api_version': 1}. No undocumented "
        "requirements may be inferred from application names. "
    )
    for mode, body, contract in (
        ("local-update", local, contracts[0]),
        ("full-policy-replacement", replacement, contracts[1]),
    ):
        expected = []
        for value in inputs:
            effective = mode if value["action"] == "apply" else "old"
            answer = oracle(deepcopy(value), effective)
            exceptional = isinstance(answer, dict) and set(answer) == {"__expected_exception__"}
            expected.append(
                answer if value["action"] == "direct" or exceptional else {"result": answer, "api_version": 1}
            )
        modes[mode] = {
            "contract": common + contract,
            "reference_files": _files(old, body),
            "alternative_files": _files(old, body, alternative=True),
            "semantic_mutant_files": _files(old, old),
            "preservation_mutant_files": _files(old, body, preservation_mutant=True),
            "expected": expected,
        }
    result = {
        "slug": slug,
        "context": context,
        "files": _files(old),
        "editable_paths": ["api.py", "engine.py", "policy.py"],
        "input_domain": domain,
        "inputs": inputs,
        "public_indices": [0, 1, 2, 3],
        "preserved_indices": [i for i, value in enumerate(inputs) if value["action"] != "apply"],
        "modes": modes,
    }
    if validator:
        result["input_validator"] = validator
    return result


LEDGER_OLD = """
balances = dict(data['balances'])
statuses = []
for row in data['entries']:
    src, dst, amount = row['from'], row['to'], row['amount']
    valid = amount > 0 and src != dst and balances[src] >= amount
    if valid:
        balances[src] -= amount
        balances[dst] += amount
    statuses.append('posted' if valid else 'rejected')
return {'balances': balances, 'statuses': statuses}
"""
LEDGER_LOCAL = """
balances = dict(data['balances'])
for row in data['entries']:
    src, dst, amount = row['from'], row['to'], row['amount']
    if amount <= 0 or src == dst or balances[src] < amount:
        return {'balances': dict(data['balances']), 'statuses': ['rolled_back'] * len(data['entries'])}
    balances[src] -= amount
    balances[dst] += amount
return {'balances': balances, 'statuses': ['posted'] * len(data['entries'])}
"""
LEDGER_REPLACE = """
balances = dict(data['balances'])
valid = True
for row in data['entries']:
    src, dst, amount = row['from'], row['to'], row['amount']
    if amount <= 0 or src == dst:
        valid = False
    balances[src] -= amount
    balances[dst] += amount
if not valid or any(value < 0 for value in balances.values()):
    return {'balances': dict(data['balances']), 'statuses': ['rolled_back'] * len(data['entries'])}
return {'balances': balances, 'statuses': ['posted'] * len(data['entries'])}
"""


def _ledger_oracle(data, mode):
    initial, events = data["balances"], data["entries"]
    if mode == "full-policy-replacement":
        totals = {
            account: initial[account]
            + sum(e["amount"] * (int(e["to"] == account) - int(e["from"] == account)) for e in events)
            for account in initial
        }
        valid = all(e["amount"] > 0 and e["from"] != e["to"] for e in events) and min(totals.values()) >= 0
        return {
            "balances": totals if valid else dict(initial),
            "statuses": ["posted" if valid else "rolled_back"] * len(events),
        }
    snapshots, decisions = [dict(initial)], []
    for event in events:
        before = snapshots[-1]
        accepted = event["amount"] > 0 and event["from"] != event["to"] and before[event["from"]] >= event["amount"]
        after = {
            k: v + (event["amount"] * (int(k == event["to"]) - int(k == event["from"])) if accepted else 0)
            for k, v in before.items()
        }
        snapshots.append(after)
        decisions.append("posted" if accepted else "rejected")
    if mode == "local-update" and "rejected" in decisions:
        return {"balances": dict(initial), "statuses": ["rolled_back"] * len(events)}
    return {"balances": snapshots[-1], "statuses": decisions}


def ledger():
    def transfer(source, target, amount):
        return {"from": source, "to": target, "amount": amount}

    samples = [
        {"balances": {"a": 3, "b": 1}, "entries": []},
        {"balances": {"a": 3, "b": 1}, "entries": [transfer("a", "b", 1)]},
        {"balances": {"a": 3, "b": 0}, "entries": [transfer("a", "b", 2), transfer("a", "b", 2)]},
        {"balances": {"a": 0, "b": 0}, "entries": [transfer("a", "b", 2), transfer("b", "a", 2)]},
        {"balances": {"a": 2, "b": 3}, "entries": [transfer("a", "a", 1)]},
        {"balances": {"a": 2, "b": 3}, "entries": [transfer("a", "b", -1), transfer("b", "a", 1)]},
        {"balances": {"a": 1, "b": 0}, "entries": [transfer("a", "b", 1), transfer("b", "a", 1)]},
        {"balances": {"a": 1, "b": 0}, "entries": [transfer("a", "b", 0), transfer("a", "b", 1)]},
    ]
    schema = {
        "balances": _object({"a": _integer(), "b": _integer()}),
        "entries": _array(_object({"from": _enum("a", "b"), "to": _enum("a", "b"), "amount": _integer(-2, 20)})),
    }
    common = "A posting is valid iff amount>0, accounts differ and the applicable funds rule holds. Old policy processes in order, skips each invalid posting, and emits posted/rejected per input row. "
    return _project(
        "double_entry_journal",
        "accounting",
        schema,
        samples,
        LEDGER_OLD,
        LEDGER_LOCAL,
        LEDGER_REPLACE,
        (
            common
            + "For apply, add atomic sequential posting: evaluate funds after each previous posting. If ANY row fails, restore ALL balances and emit rolled_back for EVERY row. Otherwise emit posted for all. Empty batch succeeds unchanged.",
            common
            + "For apply, replace sequential funds checks by simultaneous NET settlement: every row must have positive amount and different accounts, and only FINAL account balances must be nonnegative. Intermediate overdrafts are permitted. If invalid, restore the original balances and emit rolled_back for every row; otherwise post all, preserving row count.",
        ),
        _ledger_oracle,
    )


INVENTORY_OLD = """
stock = dict(data['stock'])
cache, receipts = {}, []
for row in data['requests']:
    key = row['id']
    if key in cache:
        receipts.append({'status': 'replayed', 'accepted': cache[key]})
        continue
    accepted = stock[row['sku']] >= row['qty']
    if accepted:
        stock[row['sku']] -= row['qty']
    cache[key] = accepted
    receipts.append({'status': 'reserved' if accepted else 'unavailable', 'accepted': accepted})
return {'stock': stock, 'receipts': receipts}
"""
INVENTORY_NEW = """
stock = dict(data['stock'])
cache, receipts = {}, []
for row in data['requests']:
    key = KEY_EXPRESSION
    signature = (row['sku'], row['qty'])
    if key in cache:
        previous, accepted = cache[key]
        if signature != previous:
            receipts.append({'status': 'conflict', 'accepted': False})
        else:
            receipts.append({'status': 'replayed', 'accepted': accepted})
        continue
    accepted = stock[row['sku']] >= row['qty']
    if accepted:
        stock[row['sku']] -= row['qty']
    cache[key] = (signature, accepted)
    receipts.append({'status': 'reserved' if accepted else 'unavailable', 'accepted': accepted})
return {'stock': stock, 'receipts': receipts}
"""


def _inventory_oracle(data, mode):
    left, prior, answers = dict(data["stock"]), [], []
    for row in data["requests"]:
        matches = [
            (request, outcome)
            for request, outcome in prior
            if request["id"] == row["id"] and (mode != "full-policy-replacement" or request["sku"] == row["sku"])
        ]
        if matches:
            first, accepted = matches[0]
            conflict = mode != "old" and (first["sku"], first["qty"]) != (row["sku"], row["qty"])
            answers.append(
                {"status": "conflict" if conflict else "replayed", "accepted": False if conflict else accepted}
            )
        else:
            accepted = row["qty"] <= left[row["sku"]]
            left = {sku: count - (row["qty"] if sku == row["sku"] and accepted else 0) for sku, count in left.items()}
            prior.append((row, accepted))
            answers.append({"status": "reserved" if accepted else "unavailable", "accepted": accepted})
    return {"stock": left, "receipts": answers}


def inventory():
    def request(token, sku, qty):
        return {"id": token, "sku": sku, "qty": qty}

    streams = [
        [],
        [request("x", "a", 1)],
        [request("x", "a", 1), request("x", "a", 2)],
        [request("x", "a", 1), request("x", "b", 1)],
        [request("x", "a", 4), request("x", "a", 1)],
        [request("x", "a", 2), request("x", "a", 2), request("y", "a", 2)],
        [request("x", "a", 0), request("x", "a", 0)],
        [request("x", "a", 1), request("y", "a", 2), request("x", "b", 2), request("x", "a", 1)],
    ]
    schema = {
        "stock": _object({"a": _integer(0, 20), "b": _integer(0, 20)}),
        "requests": _array(
            _object(
                {
                    "id": {"type": "string", "minLength": 1, "maxLength": 12},
                    "sku": _enum("a", "b"),
                    "qty": _integer(0, 20),
                }
            )
        ),
    }
    common = "The old reservation cache is global by request id and stores the first accepted/unavailable result, even on failure; later same-id requests replay it without checking payload. A first request deducts qty only if stock>=qty; zero is legal. Return stock and receipts in request order. "
    return _project(
        "inventory_idempotency",
        "inventory",
        schema,
        [{"stock": {"a": 3, "b": 2}, "requests": stream} for stream in streams],
        INVENTORY_OLD,
        INVENTORY_NEW.replace("KEY_EXPRESSION", "row['id']"),
        INVENTORY_NEW.replace("KEY_EXPRESSION", "(row['sku'], row['id'])"),
        (
            common
            + "For apply, retain global idempotency but bind each first id to (sku,qty). Equal payload replays the original outcome; unequal payload returns {'status':'conflict','accepted':False}, without stock/cache modification. An unavailable first attempt is also binding.",
            common
            + "For apply, replace GLOBAL idempotency with a per-SKU (sku,id) namespace. A previously used id on a different SKU is a new request. Within one key, equal qty replays and different qty conflicts without mutation. Cache both accepted and unavailable first outcomes.",
        ),
        _inventory_oracle,
    )


CONFIG_OLD = """
result = {}
for layer in data['layers']:
    result.update(deepcopy(layer))
return result
"""
CONFIG_LOCAL = """
def merge(left, right):
    out = deepcopy(left)
    for key, value in right.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict):
            out[key] = merge(out.get(key, {}) if isinstance(out.get(key), dict) else {}, value)
        else:
            out[key] = deepcopy(value)
    return out
result = {}
for layer in data['layers']:
    result = merge(result, layer)
return result
"""
CONFIG_REPLACE = """
return deepcopy(data['layers'][-1]) if data['layers'] else {}
"""


def _config_oracle(data, mode):
    layers = data["layers"]
    if mode == "full-policy-replacement":
        return deepcopy(next(iter(reversed(layers)), {}))
    values = {}
    for layer in layers:
        for key in layer:
            value = layer[key]
            if mode == "old":
                values[key] = deepcopy(value)
            elif value is None:
                if key in values:
                    del values[key]
            elif key != "labels":
                values[key] = value
            else:
                existing = values.get("labels", {})
                values["labels"] = {k: v for k, v in existing.items() if k not in value}
                values["labels"].update({k: v for k, v in value.items() if v is not None})
    return values


def configuration():
    layers = [
        [],
        [{"enabled": True}],
        [{"labels": {"x": 1}}, {"labels": {"y": 2}}],
        [{"enabled": True, "timeout": 2}, {"enabled": None}],
        [{"enabled": True}, {"enabled": False, "timeout": 0}],
        [{"labels": {"x": 1, "y": 2}}, {"labels": {"x": None}}],
        [{"timeout": 2}, {}],
        [{"labels": None}, {"labels": {"x": None, "y": 0}}],
        [{"labels": {"x": 2}}, {"labels": None}, {"labels": {"y": 3}}],
    ]
    layer_schema = _object(
        {
            "enabled": {"type": ["boolean", "null"]},
            "timeout": {"type": ["integer", "null"], "minimum": 0, "maximum": 20},
            "labels": {
                "type": ["object", "null"],
                "additionalProperties": {"type": ["integer", "null"], "minimum": 0, "maximum": 20},
                "maxProperties": 6,
            },
        },
        [],
    )
    common = "Old configuration merges layers left-to-right with shallow last-key-wins replacement, retaining null literally. Missing keys are absent, not false. "
    return _project(
        "layered_configuration",
        "configuration",
        {"layers": _array(layer_schema, 4)},
        [{"layers": value} for value in layers],
        CONFIG_OLD,
        CONFIG_LOCAL,
        CONFIG_REPLACE,
        (
            common
            + "For apply, add recursive merging for labels objects and null tombstones at both top and labels levels: a null deletes that key; deleting absent keys is a no-op. Merge dictionaries into an empty dictionary if no prior dictionary exists. Retain False and integer 0 literally. Never mutate layer objects.",
            common
            + "For apply, replace ALL inheritance/merge behavior with complete-snapshot semantics: result is a deep independent copy of the LAST layer only, or {} for no layers. Keys absent from the last layer must disappear, null is literal (NOT a tombstone), and empty last layer clears everything.",
        ),
        _config_oracle,
    )


BUILD_OLD = """
graph = data['graph']
done, active, order = set(), set(), []
def visit(node):
    if node in active:
        raise ValueError('cycle')
    if node in done:
        return
    active.add(node)
    for dependency in sorted(graph[node]):
        visit(dependency)
    active.remove(node)
    done.add(node)
    order.append(node)
for target in sorted(data['targets']):
    visit(target)
return order
"""
BUILD_LOCAL = """
graph = data['graph']
needed = old_policy(data)
dirty = set(data['changed'])
again = True
while again:
    again = False
    for node in needed:
        if node not in dirty and any(dep in dirty for dep in graph[node]):
            dirty.add(node)
            again = True
return [node for node in needed if node in dirty]
"""
BUILD_REPLACE = """
graph = data['graph']
chosen = set(data['targets'])
order = []
while chosen:
    available = sorted(node for node in chosen if not any(dep in chosen for dep in graph[node]))
    if not available:
        raise ValueError('cycle')
    node = available[0]
    order.append(node)
    chosen.remove(node)
return order
"""


def _build_oracle(data, mode):
    graph = data["graph"]
    required = set(data["targets"])
    if mode != "full-policy-replacement":
        while True:
            expanded = required | {dep for key in required for dep in graph[key]}
            if expanded == required:
                break
            required = expanded
    # Independent cycle oracle: enumerate all permutations of the bounded node
    # set and check edge constraints, rather than reuse reference traversal.
    legal = [
        list(order)
        for order in itertools.permutations(sorted(required))
        if all(order.index(dep) < order.index(node) for node in required for dep in graph[node] if dep in required)
    ]
    if not legal:
        return {"__expected_exception__": "ValueError"}
    if mode == "full-policy-replacement":
        return min(legal)
    # Old traversal order is specified by deterministic DFS. Derive it from
    # recursively expanded dependency paths, independently of candidate source.
    sequence = []

    def expand(node):
        for dep in sorted(graph[node]):
            expand(dep)
        if node not in sequence:
            sequence.append(node)

    for target in sorted(data["targets"]):
        expand(target)
    if mode == "old":
        return sequence

    def depends_on_changed(node, seen):
        return node in data["changed"] or any(
            depends_on_changed(dep, seen | {node}) for dep in graph[node] if dep not in seen
        )

    return [node for node in sequence if depends_on_changed(node, set())]


def _graph_valid(data):
    graph = data["graph"]
    return (
        set(data["targets"]) <= set(graph)
        and set(data["changed"]) <= set(graph)
        and all(set(deps) <= set(graph) for deps in graph.values())
    )


def dependency_build():
    samples = [
        {"graph": {}, "targets": [], "changed": []},
        {"graph": {"a": []}, "targets": ["a"], "changed": ["a"]},
        {"graph": {"a": [], "b": ["a"], "c": ["b"]}, "targets": ["c"], "changed": ["a"]},
        {"graph": {"a": [], "b": ["a"], "c": []}, "targets": ["b", "c"], "changed": ["c"]},
        {"graph": {"a": [], "b": ["a"]}, "targets": ["b"], "changed": []},
        {"graph": {"a": ["b"], "b": ["a"]}, "targets": ["a"], "changed": ["a"]},
        {"graph": {"a": [], "b": ["a"], "c": ["a"]}, "targets": ["c", "b"], "changed": ["b"]},
        {"graph": {"a": ["b"], "b": [], "c": []}, "targets": ["c", "a"], "changed": ["a"]},
    ]
    names = {"type": "string", "enum": ["a", "b", "c", "d"]}
    sequence = {"type": "array", "items": names, "maxItems": 4, "uniqueItems": True}
    schema = {
        "graph": {"type": "object", "properties": {name: sequence for name in "abcd"}, "additionalProperties": False},
        "targets": sequence,
        "changed": sequence,
    }
    common = "Graph maps node->prerequisite nodes. All targets, changed nodes and dependency names must exist as graph keys. Old engine ignores changed and returns deterministic dependency-first DFS postorder: sorted targets, sorted dependency lists, each node once; a cycle reachable from a target raises ValueError. Unreachable cycles do not matter. "
    return _project(
        "incremental_build_graph",
        "build_system",
        schema,
        samples,
        BUILD_OLD,
        BUILD_LOCAL,
        BUILD_REPLACE,
        (
            common
            + "For apply, retain the old reachable-cycle error and DFS ordering, but emit only reachable dirty nodes: changed nodes are dirty, and a node is dirty if any transitive prerequisite is changed. Unchanged prerequisite nodes need not be emitted. No changed reachable nodes yields [].",
            common
            + "For apply, replace automatic dependency closure with EXPLICIT-target-only scheduling. Ignore prerequisite nodes outside targets (even if they form cycles). Among remaining target nodes repeatedly choose the lexicographically smallest node with no prerequisite still remaining. Cycle among targets raises ValueError. Ignore changed. Do not include unrequested prerequisites.",
        ),
        _build_oracle,
        _graph_valid,
    )


CURSOR_OLD = """
rows = sorted(deepcopy(data['rows']), key=lambda row: (row['score'], row['id']))
cursor = data['cursor']
if cursor is not None:
    rows = [row for row in rows if row['score'] > cursor['score']]
page = rows[:data['limit']]
return {'rows': page, 'next': {'score': page[-1]['score'], 'id': page[-1]['id']} if page else None}
"""
CURSOR_LOCAL = """
rows = sorted(deepcopy(data['rows']), key=lambda row: (row['score'], row['id']))
cursor = data['cursor']
if cursor is not None:
    key = (cursor['score'], cursor['id'])
    rows = [row for row in rows if (row['score'], row['id']) > key]
page = rows[:data['limit']]
return {'rows': page, 'next': {'score': page[-1]['score'], 'id': page[-1]['id']} if page else None}
"""
CURSOR_REPLACE = """
rows = sorted(deepcopy(data['rows']), key=lambda row: (-row['score'], row['id']))
cursor = data['cursor']
if cursor is not None:
    key = (-cursor['score'], cursor['id'])
    rows = [row for row in rows if (-row['score'], row['id']) > key]
page = rows[:data['limit']]
return {'rows': page, 'next': {'score': page[-1]['score'], 'id': page[-1]['id']} if page else None}
"""


def _cursor_oracle(data, mode):
    sign = -1 if mode == "full-policy-replacement" else 1
    cursor = data["cursor"]
    candidates = []
    for row in data["rows"]:
        eligible = cursor is None
        if cursor is not None:
            if mode == "old":
                eligible = row["score"] > cursor["score"]
            else:
                eligible = sign * row["score"] > sign * cursor["score"] or (
                    row["score"] == cursor["score"] and row["id"] > cursor["id"]
                )
        if eligible:
            candidates.append(row)
    ordered = []
    while candidates:
        selected = min(candidates, key=lambda row: (sign * row["score"], row["id"]))
        ordered.append(deepcopy(selected))
        candidates.remove(selected)
    page = ordered[: data["limit"]]
    return {"rows": page, "next": {key: page[-1][key] for key in ("score", "id")} if page else None}


def _cursor_valid(data):
    return len({row["id"] for row in data["rows"]}) == len(data["rows"])


def cursor_pagination():
    def row(identifier, score):
        return {"id": identifier, "score": score, "label": identifier.upper()}

    samples = [
        {"rows": [], "cursor": None, "limit": 2},
        {"rows": [row("a", 1)], "cursor": None, "limit": 2},
        {"rows": [row("c", 1), row("a", 1), row("b", 1)], "cursor": {"id": "a", "score": 1}, "limit": 2},
        {"rows": [row("a", 0), row("c", 2), row("b", 1)], "cursor": None, "limit": 2},
        {"rows": [row("a", -1), row("b", 0), row("c", 2)], "cursor": {"id": "b", "score": 0}, "limit": 2},
        {"rows": [row("a", 2), row("b", 2)], "cursor": {"id": "z", "score": 2}, "limit": 1},
        {"rows": [row("b", 1), row("a", 1)], "cursor": None, "limit": 1},
        {"rows": [row("a", 2), row("b", 1)], "cursor": {"id": "z", "score": 0}, "limit": 3},
    ]
    identifier = {"type": "string", "minLength": 1, "maxLength": 12}
    position = _object({"id": identifier, "score": _integer(-5, 20)})
    schema = {
        "rows": _array(
            _object({"id": identifier, "score": _integer(-5, 20), "label": {"type": "string", "maxLength": 30}})
        ),
        "cursor": {"anyOf": [position, {"type": "null"}]},
        "limit": _integer(1, 6),
    }
    common = "Rows have unique id strings; labels are opaque and must survive unchanged. Cursor need not identify an existing row. Old pagination sorts ascending (score,id), keeps only score>cursor.score when cursor exists, and takes limit rows. next is exactly the last returned row's {score,id}, including on a final partial page; empty page has next=null. "
    return _project(
        "compound_cursor_pages",
        "query_service",
        schema,
        samples,
        CURSOR_OLD,
        CURSOR_LOCAL,
        CURSOR_REPLACE,
        (
            common
            + "For apply, fix tied-score loss by making cursor exclusion lexicographic and exclusive: retain (score,id) > (cursor.score,cursor.id). Keep ascending ordering, page bound, opaque row fields and next schema.",
            common
            + "For apply, replace ordering with score DESCENDING but id ASCENDING for ties. Compare cursor in that same order: retain (-score,id) > (-cursor.score,cursor.id). Do not retain the old ascending score filter. Keep limit and next schema.",
        ),
        _cursor_oracle,
        _cursor_valid,
    )


CODEC_OLD = """
rows = []
for message in data['messages']:
    rows.append({'id': message['id'], 'duration': message['duration'], 'extras': deepcopy(message['extras'])})
return rows
"""
CODEC_LOCAL = """
rows = []
for message in data['messages']:
    duration = message['duration'] * (1000 if message['version'] == 1 else 1)
    rows.append({'id': message['id'], 'duration': duration, 'extras': deepcopy(message['extras'])})
return rows
"""
CODEC_REPLACE = """
rows = []
for message in data['messages']:
    duration = message['duration'] if message['version'] == 1 else (message['duration'] + 999) // 1000
    rows.append({'id': message['id'], 'duration': duration, 'extras': deepcopy(message['extras'])})
return rows
"""


def _codec_oracle(data, mode):
    answers = []
    for message in data["messages"]:
        raw, version = message["duration"], message["version"]
        if mode == "old":
            value = raw
        elif mode == "local-update":
            value = sum([raw] * 1000) if version == 1 else raw
        elif version == 1:
            value = raw
        else:
            quotient, remainder = divmod(raw, 1000)
            value = quotient + int(remainder > 0)
        answers.append({"id": message["id"], "duration": value, "extras": deepcopy(message["extras"])})
    return answers


def wire_codec():
    def message(identifier, version, duration, extras=None):
        return {
            "id": identifier,
            "version": version,
            "duration": duration,
            "extras": {} if extras is None else extras,
        }

    streams = [
        [],
        [message("a", 2, 0)],
        [message("a", 1, 2)],
        [message("a", 2, 1)],
        [message("a", 2, 1001)],
        [message("a", 2, 1000)],
        [message("a", 1, 0, {"flag": False, "count": 0})],
        [message("a", 1, 2, {"unit": "opaque"}), message("a", 2, 2500, {"duration": 7, "missing": None})],
    ]
    scalar = {"type": ["string", "integer", "boolean", "null"], "maxLength": 30, "minimum": -10, "maximum": 20}
    schema = {
        "messages": _array(
            _object(
                {
                    "id": {"type": "string", "maxLength": 12, "minLength": 1},
                    "version": _enum(1, 2),
                    "duration": _integer(0, 9999),
                    "extras": {"type": "object", "additionalProperties": scalar, "maxProperties": 6},
                }
            )
        )
    }
    common = "Wire v1 durations mean whole seconds and v2 durations mean integer milliseconds; duration is nonnegative. Old decoder intentionally passes each numeric duration through unchanged, drops version, and emits {id,duration,extras}. Preserve message order and duplicates, extras exactly (including null/False/zero and keys named duration/unit), and the output schema. "
    return _project(
        "versioned_duration_codec",
        "wire_protocol",
        schema,
        [{"messages": stream} for stream in streams],
        CODEC_OLD,
        CODEC_LOCAL,
        CODEC_REPLACE,
        (
            common
            + "For apply, normalize ALL duration outputs to integer MILLISECONDS: multiply v1 by 1000, leave v2 unchanged. No float conversion and no modification of extras.",
            common
            + "For apply, replace normalization target with conservative whole SECONDS: leave v1 unchanged and round each v2 value UP to the next whole second using exact integer arithmetic (0 stays 0, 1000 stays 1, 1001 becomes 2). Never change opaque extras.",
        ),
        _codec_oracle,
    )


def build_projects():
    return [ledger(), inventory(), configuration(), dependency_build(), cursor_pagination(), wire_codec()]
