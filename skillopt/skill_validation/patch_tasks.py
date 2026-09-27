"""Twelve host-curated starter-module patch families, development diagnosis only.

These are synthetic modules by one author, not twelve natural projects or an
official benchmark. Preserve/replace variants share a family. Hidden cases and
the independent reference template never enter the public task prompt. Only
trusted finite host functions compute expectations; submitted Python runs via
the existing isolated execution adapter, never exec/eval on the host.
"""
from __future__ import annotations

import heapq
import json
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

from .checks import CallableTask, PublicCase
from .curriculum_tasks import _execute
from .models import ArtifactRecord, Obligation, SourceFile, TaskContract, require
from .views import bind

VERSION = "curated-starter-patch-development-v1"
ORIGIN = "single_author_host_curated_synthetic_modules"
ROLES = ("preserve", "replace")
DIMENSIONS = ("target", "retained", "replaced", "state")

# Every list has eight distinct bounded data objects. The first two are public;
# the remaining six are reserved host audits. No selection reads model output.
DATA = {
    "config_overlay": [
        {"base": {}, "override": {}}, {"base": {"a": 1}, "override": {"a": None, "b": 2}},
        {"base": {"x": 3, "y": None}, "override": {"x": None}}, {"base": {}, "override": {"z": None}},
        {"base": {"x": 0}, "override": {"x": 2}}, {"base": {"a": 1, "b": 2}, "override": {"b": None}},
        {"base": {"n": None}, "override": {"n": 5}}, {"base": {"p": 3}, "override": {"q": None, "r": 0}}],
    "inventory_reservation": [
        {"stock": {}, "orders": []}, {"stock": {"a": 2}, "orders": [["a", 3]]},
        {"stock": {"x": 3}, "orders": [["x", 2], ["x", 2]]}, {"stock": {}, "orders": [["a", 1]]},
        {"stock": {"x": 0}, "orders": [["x", 2]]}, {"stock": {"a": 4}, "orders": [["a", 4]]},
        {"stock": {"a": 2, "b": 1}, "orders": [["a", 3], ["b", 2]]},
        {"stock": {"a": 1}, "orders": [["a", 0], ["a", 2], ["a", 1]]}],
    "stable_priority": [[], [["a", 1], ["b", 3], ["c", 1]], [["x", 0]], [["a", -1], ["b", 2]],
        [["x", 2], ["y", 2]], [["a", 0], ["b", -1], ["c", 0]],
        [["a", 3], ["b", 1], ["c", 2]], [["x", -2], ["y", -2], ["z", 1]]],
    "path_normalization": ["", "/A/./B/../C", "a//B/c", "/X/../../Y", "/a/B/", "/../Q", "A/a/A", "/Z/./z/.."],
    "csv_serialization": [[], ["a,b", 'x"y', "plain"], [""], ["a", "b"], ["a\nb", "c"],
        ['"', ","], ["x,y", ""], ["normal", 'a"b,c']],
    "topological_order": [
        {"nodes": [], "edges": []}, {"nodes": ["a", "b", "c"], "edges": [["a", "c"], ["b", "c"]]},
        {"nodes": ["z"], "edges": []}, {"nodes": ["a", "b"], "edges": [["a", "b"]]},
        {"nodes": ["a", "b"], "edges": [["a", "b"], ["b", "a"]]},
        {"nodes": ["c", "b", "a"], "edges": []},
        {"nodes": ["a", "b", "c"], "edges": [["a", "b"], ["a", "b"]]},
        {"nodes": ["a", "b", "c", "d"], "edges": [["a", "d"], ["b", "d"]]}],
    "cache_eviction": [
        {"capacity": 0, "events": []},
        {"capacity": 2, "events": [["put", "a", 1], ["put", "b", 2], ["get", "a"], ["put", "c", 3]]},
        {"capacity": 0, "events": [["put", "x", 1], ["get", "x"]]},
        {"capacity": 1, "events": [["put", "a", 1], ["put", "b", 2], ["get", "a"]]},
        {"capacity": 2, "events": [["put", "a", 1], ["put", "b", 2], ["put", "a", 3]]},
        {"capacity": 2, "events": [["get", "z"], ["put", "z", 0]]},
        {"capacity": 3, "events": [["put", "c", 3], ["put", "a", 1], ["put", "b", 2], ["get", "c"]]},
        {"capacity": 2, "events": [["put", "a", 1], ["put", "b", 2], ["get", "b"], ["put", "c", 3]]}],
    "log_redaction": [[], [{"password": "p", "token": "t", "user": "u"}], [{"message": "ok"}],
        [{"token": "a"}], [{"password": "a"}, {"token": "b"}], [{"token": "", "message": "token"}],
        [{"user": "u", "password": "q", "extra": 3}], [{"token": "x"}, {"user": "v"}]],
    "pagination_cursor": [
        {"items": [], "offset": 0, "limit": 2},
        {"items": [{"id": "a", "deleted": True}, {"id": "b", "deleted": False}], "offset": 0, "limit": 1},
        {"items": [{"id": "a", "deleted": False}], "offset": 0, "limit": 0},
        {"items": [{"id": "a", "deleted": False}], "offset": 2, "limit": 2},
        {"items": [{"id": "a", "deleted": True}], "offset": 0, "limit": 2},
        {"items": [{"id": "a", "deleted": False}, {"id": "b", "deleted": True}, {"id": "c", "deleted": False}], "offset": 1, "limit": 1},
        {"items": [{"id": "x", "deleted": True}, {"id": "y", "deleted": False}, {"id": "z", "deleted": False}], "offset": 1, "limit": 2},
        {"items": [{"id": "x", "deleted": False}, {"id": "y", "deleted": False}], "offset": 0, "limit": 3}],
    "group_aggregation": [[], [["a", 1], ["a", -1], ["b", 2]], [["x", 0]], [["b", 2], ["a", 1]],
        [["x", -2], ["x", 1]], [["a", 0], ["b", 0]], [["z", 3], ["z", -3], ["y", 0]], [["a", 1], ["a", 2]]],
    "interval_policy": [[], [[0, 0], [1, 1]], [[-2, 0], [0, 2]], [[-3, -2], [0, 1]],
        [[2, 3], [0, 1]], [[0, 3], [1, 2]], [[-2, -1], [0, 0], [1, 3]], [[0, 0], [2, 2]]],
    "nested_record_update": [
        {"base": {}, "updates": []}, {"base": {"a": {"x": 1}}, "updates": [["b", "y", 2]]},
        {"base": {"a": {"x": 1}}, "updates": [["a", "x", 2]]},
        {"base": {}, "updates": [["x", "y", 1], ["x", "z", 2]]},
        {"base": {"a": {}}, "updates": [["a", "x", 0]]},
        {"base": {"a": {"x": 1}, "b": {"y": 2}}, "updates": [["a", "x", 3]]},
        {"base": {}, "updates": [["a", "x", 1], ["a", "x", 2]]},
        {"base": {"a": {"z": 9}}, "updates": [["b", "x", -1], ["a", "y", 0]]}],
}

DESCRIPTIONS = {
    "config_overlay": ("data has base/override string-key dictionaries of integers or null. Overlay assigns override values, including null.",
                       "Ignore null-valued override entries; preserve the corresponding base key/value, or absence."),
    "inventory_reservation": ("data has stock quantities and ordered [item,quantity] requests. Reserve each request wholly if available, otherwise reserve zero; never create absent stock keys.",
                              "Partially satisfy each request with min(requested, available); absent stock still supplies zero."),
    "stable_priority": ("data is a list of [name, integer_priority]. Return names sorted by ascending priority, stable within ties.",
                        "Sort by descending priority while keeping the original order within equal priorities."),
    "path_normalization": ("data is a slash-separated path. Remove empty and dot components; dot-dot pops a component if present. Return an absolute path, case-sensitive, without trailing slash except root.",
                           "Lowercase retained path components while applying the same normalization and root rules."),
    "csv_serialization": ("data is a list of strings. Join fields with commas, with no escaping or trailing newline.",
                          "Quote fields containing comma, double quote, or newline; double every embedded double quote. Other fields, including empty strings, stay unquoted."),
    "topological_order": ("data has unique string nodes and directed edges using those nodes. Repeated edges count once. Repeatedly choose the lexicographically smallest currently ready node; return null on any cycle.",
                          "Choose the lexicographically largest currently ready node instead; dependency and cycle rules do not change."),
    "cache_eviction": ("data has capacity 0..3 and put/get events. Return reads (null for misses) and [key,value] items oldest-first. FIFO: reads and overwrites do not refresh position; evict oldest when over capacity.",
                       "Use LRU: successful gets and overwrites refresh position to newest; missing gets do not. Capacity-zero behavior stays empty."),
    "log_redaction": ("data is a list of flat log dictionaries. Replace password values by the literal '[REDACTED]'; retain all other fields and record order.",
                      "Also redact token values; do not alter message text merely containing these words or unrelated keys."),
    "pagination_cursor": ("data has items with id/deleted fields, and nonnegative offset/limit. Slice raw items at [offset:offset+limit], then remove deleted entries; return the remaining ids in order.",
                          "Filter out deleted entries first, then apply offset/limit to that live-item sequence."),
    "group_aggregation": ("data is a list of [string_key, integer_value]. Sum values by key; return [key,sum] pairs sorted by key, omitting groups with zero sum.",
                          "Keep zero-sum groups that occurred in the input; do not invent absent groups."),
    "interval_policy": ("data is a list of closed integer [lo,hi] intervals, lo<=hi. Return their sorted union as lists; merge overlap or equal endpoint, not merely consecutive integer endpoints.",
                        "Also merge intervals when the next lower endpoint is exactly previous upper endpoint plus one."),
    "nested_record_update": ("data has base mapping outer keys to inner integer dictionaries and ordered [outer,inner,value] updates. Update existing outer groups only; later writes win and untouched fields stay unchanged.",
                             "Create missing outer groups when an update first uses them; existing groups and later-write ordering otherwise behave as before."),
}


def _host_result(name, data, new):
    """Trusted oracle over bounded host-defined values, not submitted code."""
    if name == "config_overlay":
        return {**data["base"], **{k: v for k, v in data["override"].items() if v is not None or not new}}
    if name == "inventory_reservation":
        stock, accepted = dict(data["stock"]), []
        for item, quantity in data["orders"]:
            available = stock.get(item, 0)
            take = min(quantity, available) if new else quantity if quantity <= available else 0
            accepted.append(take)
            if item in stock:
                stock[item] -= take
        return {"accepted": accepted, "remaining": stock}
    if name == "stable_priority":
        return [data[i][0] for i in sorted(range(len(data)), key=lambda i: ((-1 if new else 1) * data[i][1], i))]
    if name == "path_normalization":
        stack = []
        for part in data.split("/"):
            if part == "..":
                if stack:
                    stack.pop()
            elif part and part != ".":
                stack.append(part.lower() if new else part)
        return "/" + "/".join(stack)
    if name == "csv_serialization":
        return ",".join(('"' + s.replace('"', '""') + '"') if new and any(c in s for c in ',"\n') else s for s in data)
    if name == "topological_order":
        edges = set(map(tuple, data["edges"]))
        indegree = {v: sum(b == v for _, b in edges) for v in data["nodes"]}
        # Heap oracle and scan-based reference below are separately written.
        order = sorted(data["nodes"], reverse=new)
        rank = {v: i for i, v in enumerate(order)}
        ready = [(rank[v], v) for v in order if indegree[v] == 0]
        heapq.heapify(ready)
        out = []
        while ready:
            _, v = heapq.heappop(ready)
            out.append(v)
            for a, b in edges:
                if a == v:
                    indegree[b] -= 1
                    if indegree[b] == 0:
                        heapq.heappush(ready, (rank[b], b))
        return out if len(out) == len(order) else None
    if name == "cache_eviction":
        order, values, reads = [], {}, []
        for event in data["events"]:
            op, key = event[:2]
            if op == "get":
                reads.append(values.get(key))
            else:
                if key not in values:
                    order.append(key)
                values[key] = event[2]
            if new and key in values:
                order.remove(key)
                order.append(key)
            while len(order) > data["capacity"]:
                del values[order.pop(0)]
        return {"reads": reads, "items": [[k, values[k]] for k in order]}
    if name == "log_redaction":
        keys = {"password", "token"} if new else {"password"}
        return [{k: "[REDACTED]" if k in keys else v for k, v in row.items()} for row in data]
    if name == "pagination_cursor":
        items = [x for x in data["items"] if not x["deleted"]] if new else data["items"]
        return [x["id"] for x in items[data["offset"]:data["offset"] + data["limit"]] if not x["deleted"]]
    if name == "group_aggregation":
        return [[key, sum(v for k, v in data if k == key)] for key in sorted({k for k, _ in data})
                if new or sum(v for k, v in data if k == key) != 0]
    if name == "interval_policy":
        # Connected-component closure, independent of reference's sorted sweep.
        pending, out = [list(pair) for pair in data], []
        while pending:
            lo, hi = pending.pop()
            changed = True
            while changed:
                changed = False
                for i, (a, b) in enumerate(pending):
                    if a <= hi + int(new) and lo <= b + int(new):
                        lo, hi = min(lo, a), max(hi, b)
                        pending.pop(i)
                        changed = True
                        break
            out.append([lo, hi])
        return sorted(out)
    require(name == "nested_record_update", "Unknown patch family")
    result = deepcopy(data["base"])
    for outer, inner, value in data["updates"]:
        if new:
            result.setdefault(outer, {})
        if outer in result:
            result[outer][inner] = value
    return result


# Existing modules contain only OLD behavior, never the desired implementation.
LEGACY = {
    "config_overlay": "    out = dict(data['base'])\n    out.update(data['override'])\n    return out\n",
    "inventory_reservation": "    stock = dict(data['stock'])\n    accepted = []\n    for key, amount in data['orders']:\n        take = amount if amount <= stock.get(key, 0) else 0\n        accepted.append(take)\n        if key in stock:\n            stock[key] -= take\n    return {'accepted': accepted, 'remaining': stock}\n",
    "stable_priority": "    return [row[0] for row in sorted(data, key=lambda row: row[1])]\n",
    "path_normalization": "    parts = []\n    for part in data.split('/'):\n        if part == '..':\n            if parts: parts.pop()\n        elif part not in ('', '.'):\n            parts.append(part)\n    return '/' + '/'.join(parts)\n",
    "csv_serialization": "    return ','.join(data)\n",
    "topological_order": "    remaining = set(data['nodes'])\n    edges = set(map(tuple, data['edges']))\n    result = []\n    while remaining:\n        ready = sorted(v for v in remaining if not any(b == v and a in remaining for a, b in edges))\n        if not ready: return None\n        result.append(ready[0])\n        remaining.remove(ready[0])\n    return result\n",
    "cache_eviction": "    from collections import OrderedDict\n    cache = OrderedDict()\n    reads = []\n    for event in data['events']:\n        if event[0] == 'get':\n            reads.append(cache.get(event[1]))\n        else:\n            cache[event[1]] = event[2]\n            while len(cache) > data['capacity']: cache.popitem(last=False)\n    return {'reads': reads, 'items': [[k, v] for k, v in cache.items()]}\n",
    "log_redaction": "    rows = [dict(row) for row in data]\n    for row in rows:\n        if 'password' in row: row['password'] = '[REDACTED]'\n    return rows\n",
    "pagination_cursor": "    selected = data['items'][data['offset']:data['offset'] + data['limit']]\n    return [item['id'] for item in selected if not item['deleted']]\n",
    "group_aggregation": "    sums = {}\n    for key, value in data: sums[key] = sums.get(key, 0) + value\n    return [[key, sums[key]] for key in sorted(sums) if sums[key] != 0]\n",
    "interval_policy": "    result = []\n    for lo, hi in sorted(data):\n        if result and lo <= result[-1][1]: result[-1][1] = max(result[-1][1], hi)\n        else: result.append([lo, hi])\n    return result\n",
    "nested_record_update": "    result = {key: dict(value) for key, value in data['base'].items()}\n    for outer, inner, value in data['updates']:\n        if outer in result: result[outer][inner] = value\n    return result\n",
}
NEW_REFERENCE = {
    "config_overlay": "    result = data['base'].copy()\n    for key, value in data['override'].items():\n        if value is not None: result[key] = value\n    return result\n",
    "inventory_reservation": "    stock = data['stock'].copy()\n    answer = []\n    for key, count in data['orders']:\n        available = stock.get(key, 0)\n        if count > available: count = available\n        answer.append(count)\n        if key in stock: stock[key] = available - count\n    return {'accepted': answer, 'remaining': stock}\n",
    "stable_priority": "    return [row[0] for row in sorted(data, key=lambda row: row[1], reverse=True)]\n",
    "path_normalization": "    parts = []\n    for piece in data.lower().split('/'):\n        if piece == '..': parts = parts[:-1]\n        elif piece not in ('', '.'): parts += [piece]\n    return '/' + '/'.join(parts)\n",
    "csv_serialization": "    fields = []\n    for item in data:\n        if ',' in item or '\\n' in item or '\"' in item:\n            item = '\"' + item.replace('\"', '\"\"') + '\"'\n        fields.append(item)\n    return ','.join(fields)\n",
    "topological_order": "    todo = set(data['nodes'])\n    edges = set(map(tuple, data['edges']))\n    result = []\n    while todo:\n        ready = [v for v in todo if not any(a in todo and b == v for a, b in edges)]\n        if not ready: return None\n        v = max(ready)\n        result.append(v)\n        todo.remove(v)\n    return result\n",
    "cache_eviction": "    from collections import OrderedDict\n    cache = OrderedDict()\n    reads = []\n    for event in data['events']:\n        key = event[1]\n        if event[0] == 'get':\n            reads.append(cache.get(key))\n            if key in cache: cache.move_to_end(key)\n        else:\n            cache[key] = event[2]\n            cache.move_to_end(key)\n            while len(cache) > data['capacity']: cache.popitem(last=False)\n    return {'reads': reads, 'items': [[k, v] for k, v in cache.items()]}\n",
    "log_redaction": "    result = []\n    for source in data:\n        row = source.copy()\n        for key in ('password', 'token'):\n            if key in row: row[key] = '[REDACTED]'\n        result.append(row)\n    return result\n",
    "pagination_cursor": "    live = []\n    for item in data['items']:\n        if not item['deleted']: live.append(item['id'])\n    return live[data['offset']:data['offset'] + data['limit']]\n",
    "group_aggregation": "    result = {}\n    for key, value in data: result[key] = result.get(key, 0) + value\n    return [[key, result[key]] for key in sorted(result)]\n",
    "interval_policy": "    out = []\n    for left, right in sorted(data):\n        if out and left <= out[-1][1] + 1:\n            out[-1][1] = max(out[-1][1], right)\n        else: out.append([left, right])\n    return out\n",
    "nested_record_update": "    result = {key: dict(value) for key, value in data['base'].items()}\n    for outer, inner, value in data['updates']:\n        if outer not in result: result[outer] = {}\n        result[outer][inner] = value\n    return result\n",
}


def _module(name, role=None):
    source = "def _apply(data):\n" + LEGACY[name]
    if role is not None:
        source += "\ndef _new(data):\n" + NEW_REFERENCE[name]
    source += "\ndef _summary(payload):\n    return {'size': len(payload['data']), 'tag': payload.get('tag', '')}\n"
    source += "\ndef solve(payload):\n    summary = _summary(payload)\n"
    if role is None:
        source += "    result = _apply(payload['data'])\n"
    else:
        flag = "True" if role == "replace" else "payload.get('use_new_policy', False)"
        source += "    result = (_new if " + flag + " else _apply)(payload['data'])\n"
    return source + "    return {'result': result, 'summary': summary}\n"


def _cases(name, role, indexes):
    values = []
    for index in indexes:
        for enabled in (False, True):
            payload = {"data": deepcopy(DATA[name][index])}
            if index % 3:
                payload["tag"] = "batch-" + str(index)
            # Both omitted and explicit-false compatibility are tested.
            if enabled or index % 2:
                payload["use_new_policy"] = enabled
            summary = {"size": len(payload["data"]), "tag": payload.get("tag", "")}
            new = enabled or role == "replace"
            expected = {"result": _host_result(name, payload["data"], new), "summary": summary}
            legacy = {"result": _host_result(name, payload["data"], False), "summary": summary}
            values.append({"id": f"case-{index}-{int(enabled)}", "input": payload, "expected": expected,
                "legacy_expected": legacy, "kind": "target" if enabled else "replaced" if role == "replace" else "retained"})
    return values


def _runner(cases):
    # Fixed host-owned observer. Four independently reported obligations avoid
    # treating every changed legacy result as a violation on replacement tasks.
    return ("from copy import deepcopy\nimport importlib\nCASES = " + repr(cases) + "\n"
        "def equal(a,b):\n    if type(a) is not type(b): return False\n"
        "    if isinstance(b,list): return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))\n"
        "    if isinstance(b,dict): return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in b)\n"
        "    return a==b\n"
        "def evaluate(fn):\n    rows=[]\n    for case in CASES:\n        payload=deepcopy(case['input'])\n"
        "        try:\n            out=fn(payload)\n            shape=type(out) is dict and set(out)=={'result','summary'}\n"
        "            result=shape and equal(out['result'],case['expected']['result'])\n"
        "            retained=shape and equal(out['summary'],case['expected']['summary'])\n"
        "            if case['kind']=='retained': retained=retained and result\n"
        "            error=None\n"
        "        except (MemoryError,TimeoutError): raise\n"
        "        except Exception as exc:\n            result,retained=False,False\n            error=type(exc).__name__\n"
        "        state=equal(payload,case['input'])\n"
        "        rows.append({'id':case['id'],'target':result if case['kind']=='target' else None,\n"
        "            'retained':retained,'replaced':result if case['kind']=='replaced' else None,'state':state,'exception':error})\n"
        "    return rows\n"
        "def audit():\n    return {'cases':evaluate(importlib.import_module('solution').solve)}\n"
        "def check():\n    return all(all(r[k] is not False for k in ('target','retained','replaced','state')) for r in audit()['cases'])\n")


def _row(name, role):
    require(name in DATA and role in ROLES, "Unknown fixed patch family/role")
    old, change = DESCRIPTIONS[name]
    starter = _module(name)
    public, hidden = _cases(name, role, range(2)), _cases(name, role, range(2, 8))
    instruction = ("Add optional boolean use_new_policy, default false. Apply the requested rule only when true; "
                   "omitted/false must keep the existing result behavior." if role == "preserve" else
                   "Replace the old result rule with the requested rule unconditionally. The optional legacy "
                   "use_new_policy field is now ignored, including omitted/false. Do not retain the obsolete result rule.")
    retained = ("Return exactly result and summary. Retain summary={'size':len(payload['data']), "
                "'tag':payload.get('tag','')} computed from the original payload. Do not mutate payload or any nested input. "
                "All input data follow the described types; strings use ASCII plus explicitly permitted CSV newlines. "
                "Collections contain at most eight entries, integer magnitudes at most nine, nonnegative counts/offsets/limits at most eight.")
    prompt = ("Modify the existing Python module below and return the full updated solution.py implementing solve(payload). "
        "payload is a dictionary with data, optional string tag, and optional boolean use_new_policy.\n"
        "Existing behavior: " + old + "\nRequested change: " + change + "\n" + instruction + "\n" + retained
        + "\nSTARTER SOURCE (public, not a solution to the requested change):\n" + starter
        + "\nREGISTERED PUBLIC EXAMPLES:\n" + json.dumps([{k: c[k] for k in ("input", "expected")} for c in public], sort_keys=True))
    family = "curated-patch-" + name
    obligations = [Obligation("requested_behavior", "requested_behavior", prompt, prompt),
        Obligation("new_target", "requested_behavior", change, change, critical=False),
        Obligation("retained_behavior", "requested_behavior", retained, retained, critical=False),
        Obligation("input_preservation", "input_preservation", "Do not mutate payload or any nested input.",
                   "Do not mutate payload or any nested input.", critical=False)]
    if role == "replace":
        obligations.append(Obligation("replaced_behavior", "requested_behavior", instruction, instruction, critical=False))
    contract = TaskContract(family + "-" + role, family, family, "single-author-curated-patch-catalog", "development",
        "coding", "constraint_preservation_during_source_edit", prompt, tuple(obligations), (SourceFile("starter.py", starter),))
    task = CallableTask(contract, "solution", "solve", tuple(PublicCase(c["id"],
        json.dumps({"args": [c["input"]], "kwargs": {}}), prompt,
        ("requested_behavior", "input_preservation"), json.dumps(c["expected"])) for c in public))
    public_task = CallableTask(contract, "public_runner", "check", (PublicCase("registered-public-contract",
        '{"args":[],"kwargs":{}}', prompt, ("requested_behavior",), "true"),))
    # Public observer does not carry legacy_expected or ANY hidden case.
    public_cases = [{k: c[k] for k in ("id", "input", "expected", "kind")} for c in public]
    return {"task": task, "public_task": public_task,
        "public_wrapper": SourceFile("public_runner.py", _runner(public_cases)).to_dict(),
        "family_id": family, "region": role, "family_origin": ORIGIN, "task_kind": "starter_module_patch",
        "host_only": {"family": name, "role": role, "starter": starter, "reference": _module(name, role),
                      "public_cases": public, "audit_cases": hidden, "audit_runner": _runner(hidden)}}


def serialize_row(row):
    return {**deepcopy({k: v for k, v in row.items() if k not in {"task", "public_task"}}),
            "task": row["task"].to_dict(), "public_task": row["public_task"].to_dict()}


def deserialize_row(value):
    row = deepcopy(value)
    for key in ("task", "public_task"):
        row[key] = CallableTask.from_dict(row[key])
    return _validate(row)


def _validate(row):
    require(type(row) is dict and row.get("family_origin") == ORIGIN, "Expected frozen curated patch task")
    expected = _row(row["host_only"]["family"], row["host_only"]["role"])
    require(serialize_row(row) == serialize_row(expected), "Frozen patch registration changed")
    return row


def build_development_panel(seed=20260926):
    require(type(seed) is int and 0 <= seed < 2**64, "Nonnegative bounded seed required")
    names = sorted(DATA, key=lambda name: digest([VERSION, seed, name]))
    rows = [_row(name, role) for name in names for role in ROLES]
    manifest = seal({"version": VERSION, "seed": seed, "source_family_count": 12, "task_count": 24,
        "roles": list(ROLES), "families": names, "row_hashes": [digest(serialize_row(r)) for r in rows],
        "public_cases_per_task": 4, "hidden_cases_per_task": 12,
        "source_type": ORIGIN, "partition": "development", "official_benchmark": False,
        "natural_independent_projects": False, "role_variants_are_independent_families": False,
        "prior_development_overlap": {"interval_policy": "Related to A interval_union; not an independent unseen-family claim."},
        "selection": "all_twelve_families_ordered_before_model_calls_no_outcome_filter",
        "purpose": "No-Skill difficulty and regression-opportunity diagnosis, not method comparison",
        "deployment_authorized": False})
    return {"development": rows, "manifest": manifest}


def qualify_panel(panel, executor, root):
    manifest = verify(panel["manifest"])
    require(manifest == build_development_panel(manifest["seed"])["manifest"]
            and len(panel["development"]) == 24, "Qualification requires the entire canonical patch manifest")
    require([digest(serialize_row(_validate(r))) for r in panel["development"]] == manifest["row_hashes"],
            "Patch panel differs from manifest")
    results = []
    for row in panel["development"]:
        host = row["host_only"]
        cases = host["public_cases"] + host["audit_cases"]
        old_cases = [{**c, "expected": c["legacy_expected"]} for c in cases]
        files = {"reference.py": host["reference"], "starter.py": host["starter"],
                 "opposite.py": _module(host["family"], "replace" if host["role"] == "preserve" else "preserve"),
                 "checks.py": _runner(cases), "oldchecks.py": _runner(old_cases),
                 "public_checks.py": row["public_wrapper"]["content"]}
        files["qualify.py"] = ("import reference,starter,opposite,checks,oldchecks,public_checks,sys,types\n"
            "def all_ok(rows):\n    return all(all(r[k] is not False for k in ('target','retained','replaced','state')) for r in rows)\n"
            "def bad_state(p):\n    out=reference.solve(p)\n    p.clear()\n    return out\n"
            "def bad_summary(p):\n    out=reference.solve(p)\n    out['summary']['tag']='WRONG'\n    return out\n"
            "def pure_raise(p):\n    raise ValueError('controlled')\n"
            "def mutate_raise(p):\n    p.clear()\n    raise ValueError('controlled')\n"
            "def qualify():\n    correct=checks.evaluate(reference.solve)\n    old=checks.evaluate(starter.solve)\n"
            "    sys.modules['solution']=reference\n    public_ok=public_checks.check() is True\n"
            "    sys.modules['solution']=types.SimpleNamespace(solve=bad_state)\n    public_state=public_checks.check() is False\n"
            "    sys.modules['solution']=types.SimpleNamespace(solve=bad_summary)\n    public_summary=public_checks.check() is False\n"
            "    return {'reference_matches_oracle':all_ok(correct),'starter_matches_old_contract':all_ok(oldchecks.evaluate(starter.solve)),\n"
            "        'old_rule_is_insufficient':not all_ok(old),'state_mutant_detected':not all_ok(checks.evaluate(bad_state)),\n"
            "        'retained_mutant_detected':not all_ok(checks.evaluate(bad_summary)),\n"
            "        'policy_reversal_mutant_detected':not all_ok(checks.evaluate(opposite.solve)),\n"
            "        'exception_state_separated':all(r['state'] for r in checks.evaluate(pure_raise)) and not any(r['state'] for r in checks.evaluate(mutate_raise)),\n"
            "        'public_wrapper_valid':public_ok and public_state and public_summary,'cases':len(correct)}\n")
        receipt = _execute(files, "qualify", "qualify", executor, Path(root) / row["task"].contract.task_id,
                           bindings={"task_hash": row["task"].content_hash, "manifest_hash": manifest["record_hash"]})
        execution = receipt["execution"] or {}
        actual = execution.get("actual")
        flags = ("reference_matches_oracle", "starter_matches_old_contract", "old_rule_is_insufficient",
                 "state_mutant_detected", "retained_mutant_detected", "public_wrapper_valid",
                 "policy_reversal_mutant_detected", "exception_state_separated")
        complete = execution.get("status") == "observed" and execution.get("exception") is None and type(actual) is dict
        complete = complete and all(type(actual.get(k)) is bool for k in flags) and actual.get("cases") == len(cases)
        status = "unknown" if not complete else "qualified" if all(actual[k] for k in flags) else "rejected"
        results.append(seal({"task_id": row["task"].contract.task_id, "family_id": row["family_id"],
            "region": row["region"], "status": status, "receipt": receipt,
            "formal_eligible": status == "qualified" and receipt["real_isolated_execution"]}))
    qualified = all(r["formal_eligible"] for r in results)
    return seal({"version": VERSION, "panel_hash": manifest["record_hash"],
        "status": "qualified" if qualified else "rejected" if any(r["status"] == "rejected" for r in results) else "pending",
        "formal_eligible": qualified, "families": 12, "tasks": 24, "results": results,
        "reference_count_per_task": 1, "independently_written_host_oracle": True,
        "not_verifier_calibration": True, "not_proof_of_correctness": True, "deployment_authorized": False})


def audit_row(row, artifact, executor, root):
    _validate(row)
    require(type(artifact) is ArtifactRecord, "Bound artifact required")
    bind(row["task"].contract, artifact, ())
    code = next((f.content for f in artifact.files if f.path == "solution.py"), None)
    receipt = None
    if artifact.availability == "available" and code is not None:
        receipt = _execute({"solution.py": code, "hidden_audit.py": row["host_only"]["audit_runner"]},
            "hidden_audit", "audit", executor, Path(root) / "audit",
            bindings={"task_hash": row["task"].content_hash, "artifact_record_hash": artifact.content_hash})
    execution = receipt["execution"] if receipt and receipt["execution"] else {}
    actual, cases = execution.get("actual"), row["host_only"]["audit_cases"]
    complete = execution.get("status") == "observed" and execution.get("exception") is None and type(actual) is dict
    complete = complete and type(actual.get("cases")) is list and len(actual["cases"]) == len(cases)
    if complete:
        for observed, case in zip(actual["cases"], cases):
            if type(observed) is not dict or observed.get("id") != case["id"]:
                complete = False
                break
            for dim in DIMENSIONS:
                applicable = dim in ("retained", "state") or dim == case["kind"]
                if (applicable and type(observed.get(dim)) is not bool) or (not applicable and observed.get(dim) is not None):
                    complete = False
    statuses, counts = {}, {}
    for dim in DIMENSIONS:
        count = sum(dim in ("retained", "state") or dim == c["kind"] for c in cases)
        observations = [r[dim] for r in actual["cases"] if r[dim] is not None] if complete else []
        statuses[dim] = "not_applicable" if not count else "unknown" if not complete else "pass" if all(observations) else "fail"
        counts[dim] = {"applicable": count, "observed": len(observations),
                       "pass": sum(v is True for v in observations), "fail": sum(v is False for v in observations)}
    status = "unknown" if not complete else "fail" if "fail" in statuses.values() else "pass"
    return seal({"version": VERSION, "task_hash": row["task"].content_hash, "artifact_hash": artifact.content_hash,
        "family_id": row["family_id"], "region": row["region"], "status": status,
        **{dim + "_status": value for dim, value in statuses.items()}, "obligation_statuses": statuses,
        "coverage": counts, "receipt": receipt, "audit_outcomes": actual if complete else None,
        "information_origin": "host_only_patch_audit_not_solver_feedback", "deployment_authorized": False})
