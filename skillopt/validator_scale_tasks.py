"""Author-created semantic diagnostics, NOT public benchmark scores.

32 different operation contracts form 8 dependent families; four whole families
are development and four are held out. Cases and mutants are deterministic and
materialized before model responses. Existing sandbox/oracle execution is reused
unchanged. Deliberate mutants are controlled stress, never natural error rates.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from dataclasses import dataclass
from typing import Any

from skillopt.validator_pilot.tasks import Task as CodingTask

VERSION = "author-semantic-validator-scale-v2-output-consistent"
PRELUDE = '''
"""Small in-memory service; preserve the complete stated API contract.
The helpers copy JSON-shaped values while retaining key presence and order.
All operations are local; caller-owned request objects must remain unchanged.
"""

def _copy(value):
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value

def _request(data):
    if not isinstance(data, dict):
        raise TypeError("request must be a dictionary")
    return data

'''


@dataclass(frozen=True)
class Spec:
    family: str
    name: str
    contract: str
    code: str
    bug: tuple[str, str]
    mutant: tuple[str, str]
    cases: list[dict[str, Any]]


def c(
    data: Any,
    expected: Any,
    *,
    new: bool = False,
    public: bool = False,
    unchanged: bool = False,
    exception: str | None = None,
) -> dict[str, Any]:
    return {
        "setup": "data=" + repr(data),
        "expr": "(solve(data),data)" if unchanged else "solve(data)",
        "expected": [expected, data] if unchanged else expected,
        "public": public,
        "dimension": "requested_behavior" if new else "preserved_behavior",
        "exception": exception,
    }


SPECS: list[Spec] = []


def add(
    family: str,
    name: str,
    contract: str,
    code: str,
    bug: tuple[str, str],
    mutant: tuple[str, str],
    cases: list[dict[str, Any]],
) -> None:
    SPECS.append(Spec(family, name, contract, textwrap.dedent(code).strip() + "\n", bug, mutant, cases))


add(
    "transactions",
    "bank_batch",
    "Transfer [source,destination,amount] operations atomically. Unknown accounts, negative amounts, or insufficient source balance reject the ENTIRE batch and return original balances. Zero and self transfers are legal; require sufficient funds even for self transfers. Return {'ok':bool,'balances':dict}. Do not mutate the request.",
    """
def solve(data):
    _request(data)
    before = _copy(data["balances"])
    work = _copy(before)
    for src, dst, amount in data["ops"]:
        invalid = amount < 0 or src not in work or dst not in work
        if invalid or work[src] < amount:
            return {"ok": False, "balances": before}
        work[src] -= amount
        work[dst] += amount
    return {"ok": True, "balances": work}
""",
    ("work = _copy(before)", "work = before"),
    ("amount < 0", "amount <= 0"),
    [
        c(
            {"balances": {"a": 5, "b": 0}, "ops": [["a", "b", 2]]},
            {"ok": True, "balances": {"a": 3, "b": 2}},
            public=True,
            new=True,
        ),
        c({"balances": {"a": 1}, "ops": []}, {"ok": True, "balances": {"a": 1}}, public=True),
        c(
            {"balances": {"a": 5, "b": 0}, "ops": [["a", "b", 2], ["b", "x", 1]]},
            {"ok": False, "balances": {"a": 5, "b": 0}},
            new=True,
        ),
        c(
            {"balances": {"a": 5, "b": 0}, "ops": [["a", "b", 2], ["a", "b", 9]]},
            {"ok": False, "balances": {"a": 5, "b": 0}},
            new=True,
        ),
        c({"balances": {"a": 2}, "ops": [["a", "a", 0]]}, {"ok": True, "balances": {"a": 2}}),
        c({"balances": {"a": 2}, "ops": [["a", "a", 2]]}, {"ok": True, "balances": {"a": 2}}),
        c(
            {"balances": {"a": 3, "b": 0}, "ops": [["a", "b", 1]]},
            {"ok": True, "balances": {"a": 2, "b": 1}},
            unchanged=True,
        ),
    ],
)

add(
    "transactions",
    "stock_reservations",
    "Apply ['take'|'put',sku,quantity] atomically. Invalid operation/sku, negative quantity or insufficient stock rejects all changes. Return ok, stock, and the unique successfully touched SKU names in FIRST-touch order; on failure touched is empty. Quantities zero are legal and count as a touch. Inputs remain unchanged.",
    """
def solve(data):
    _request(data)
    original = _copy(data["stock"])
    work = _copy(original)
    touched = []
    for op, sku, qty in data["ops"]:
        if op not in ["take", "put"] or sku not in work or qty < 0:
            return {"ok":False,"stock":original,"touched":[]}
        if op == "take" and work[sku] < qty:
            return {"ok":False,"stock":original,"touched":[]}
        work[sku] += qty if op == "put" else -qty
        if sku not in touched:
            touched.append(sku)
    return {"ok":True,"stock":work,"touched":touched}
""",
    ('qty if op == "put" else -qty', 'qty if op == "take" else -qty'),
    ('"touched":touched', '"touched":sorted(touched)'),
    [
        c(
            {"stock": {"a": 2}, "ops": [["put", "a", 2]]},
            {"ok": True, "stock": {"a": 4}, "touched": ["a"]},
            new=True,
            public=True,
        ),
        c({"stock": {"a": 2}, "ops": []}, {"ok": True, "stock": {"a": 2}, "touched": []}, public=True),
        c(
            {"stock": {"a": 2}, "ops": [["take", "a", 1], ["take", "a", 9]]},
            {"ok": False, "stock": {"a": 2}, "touched": []},
            new=True,
        ),
        c(
            {"stock": {"a": 2}, "ops": [["put", "a", 3], ["bad", "a", 1]]},
            {"ok": False, "stock": {"a": 2}, "touched": []},
            new=True,
        ),
        c(
            {"stock": {"a": 2, "z": 3}, "ops": [["take", "z", 1], ["put", "a", 1]]},
            {"ok": True, "stock": {"a": 3, "z": 2}, "touched": ["z", "a"]},
        ),
        c(
            {"stock": {"a": 2}, "ops": [["take", "a", 0], ["put", "a", 0]]},
            {"ok": True, "stock": {"a": 2}, "touched": ["a"]},
        ),
        c(
            {"stock": {"a": 3}, "ops": [["take", "a", 2]]},
            {"ok": True, "stock": {"a": 1}, "touched": ["a"]},
            unchanged=True,
        ),
    ],
)

add(
    "transactions",
    "config_transaction",
    "Apply set/delete edits atomically to a flat config. set has a value (including None). Deleting a protected key rejects the whole batch; deleting an absent unprotected key is a no-op. Unknown op rejects. Return {'ok':bool,'config':dict}; copy nested values and do not mutate inputs.",
    """
def solve(data):
    _request(data)
    original = _copy(data["config"])
    work = _copy(original)
    for edit in data["edits"]:
        key = edit["key"]
        if edit["op"] == "set":
            work[key] = _copy(edit["value"])
        elif edit["op"] == "delete" and key not in data["protected"]:
            work.pop(key, None)
        else:
            return {"ok":False,"config":original}
    return {"ok":True,"config":work}
""",
    ('"config":original', '"config":work'),
    ("work.pop(key, None)", "work.pop(key)"),
    [
        c(
            {"config": {"x": 1}, "protected": [], "edits": [{"op": "set", "key": "x", "value": 2}]},
            {"ok": True, "config": {"x": 2}},
            new=True,
            public=True,
        ),
        c({"config": {"x": 1}, "protected": [], "edits": []}, {"ok": True, "config": {"x": 1}}, public=True),
        c(
            {
                "config": {"x": 1, "p": 2},
                "protected": ["p"],
                "edits": [{"op": "set", "key": "x", "value": 9}, {"op": "delete", "key": "p"}],
            },
            {"ok": False, "config": {"x": 1, "p": 2}},
            new=True,
        ),
        c(
            {
                "config": {},
                "protected": [],
                "edits": [{"op": "set", "key": "x", "value": 3}, {"op": "bad", "key": "x"}],
            },
            {"ok": False, "config": {}},
            new=True,
        ),
        c(
            {"config": {"x": 1}, "protected": [], "edits": [{"op": "delete", "key": "missing"}]},
            {"ok": True, "config": {"x": 1}},
        ),
        c(
            {"config": {}, "protected": [], "edits": [{"op": "set", "key": "x", "value": None}]},
            {"ok": True, "config": {"x": None}},
        ),
        c(
            {"config": {}, "protected": [], "edits": [{"op": "set", "key": "x", "value": {"n": 1}}]},
            {"ok": True, "config": {"x": {"n": 1}}},
            unchanged=True,
        ),
    ],
)

add(
    "transactions",
    "idempotent_ledger",
    "Apply [id,delta] entries atomically to an integer balance. Repeated id with the SAME delta is a no-op; a conflicting delta for any old/new id rejects the entire batch. Return ok,balance,applied (new IDs in arrival order),seen. Preserve negative/zero deltas and input immutability.",
    """
def solve(data):
    _request(data)
    balance = data["balance"]
    seen = _copy(data["seen"])
    applied = []
    for key, delta in data["entries"]:
        if key in seen:
            if seen[key] != delta:
                return {"ok":False,"balance":data["balance"],"applied":[],"seen":_copy(data["seen"])}
            continue
        seen[key] = delta
        balance += delta
        applied.append(key)
    return {"ok":True,"balance":balance,"applied":applied,"seen":seen}
""",
    ("if seen[key] != delta:", "if False:"),
    ('"applied":applied', '"applied":sorted(applied)'),
    [
        c(
            {"balance": 0, "seen": {}, "entries": [["a", 2]]},
            {"ok": True, "balance": 2, "applied": ["a"], "seen": {"a": 2}},
            new=True,
            public=True,
        ),
        c(
            {"balance": 2, "seen": {"a": 2}, "entries": [["a", 2]]},
            {"ok": True, "balance": 2, "applied": [], "seen": {"a": 2}},
            public=True,
        ),
        c(
            {"balance": 0, "seen": {}, "entries": [["a", 2], ["a", 3]]},
            {"ok": False, "balance": 0, "applied": [], "seen": {}},
            new=True,
        ),
        c(
            {"balance": 4, "seen": {"old": 4}, "entries": [["new", 3], ["old", 9]]},
            {"ok": False, "balance": 4, "applied": [], "seen": {"old": 4}},
            new=True,
        ),
        c(
            {"balance": 0, "seen": {}, "entries": [["z", 1], ["a", 2]]},
            {"ok": True, "balance": 3, "applied": ["z", "a"], "seen": {"z": 1, "a": 2}},
        ),
        c(
            {"balance": 2, "seen": {}, "entries": [["a", -2], ["b", 0]]},
            {"ok": True, "balance": 0, "applied": ["a", "b"], "seen": {"a": -2, "b": 0}},
        ),
        c(
            {"balance": 1, "seen": {}, "entries": [["x", 1]]},
            {"ok": True, "balance": 2, "applied": ["x"], "seen": {"x": 1}},
            unchanged=True,
        ),
    ],
)

add(
    "copy_semantics",
    "recursive_overlay",
    "Recursively overlay mapping values. If both old/new values are dicts, merge them; otherwise replace with an independent deep copy. Lists replace, not concatenate. None is an explicit value, never deletion. Preserve unrelated keys and do not mutate base or patch.",
    """
def overlay(base, patch):
    result = _copy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = overlay(result[key], value)
        else:
            result[key] = _copy(value)
    return result

def solve(data):
    _request(data)
    base = data["base"]
    patch = data["patch"]
    return overlay(base, patch)
""",
    ("result[key] = overlay(result[key], value)", "result[key] = _copy(value)"),
    ("result[key] = _copy(value)", "\n            if value is not None:\n                result[key] = _copy(value)"),
    [
        c({"base": {"a": 1}, "patch": {"a": 2}}, {"a": 2}, new=True, public=True),
        c({"base": {"a": 1}, "patch": {}}, {"a": 1}, public=True),
        c({"base": {"x": {"a": 1, "b": 2}}, "patch": {"x": {"a": 3}}}, {"x": {"a": 3, "b": 2}}, new=True),
        c(
            {"base": {"x": {"a": {"n": 1, "m": 2}}}, "patch": {"x": {"a": {"n": 8}}}},
            {"x": {"a": {"n": 8, "m": 2}}},
            new=True,
        ),
        c({"base": {"a": 1}, "patch": {"a": None}}, {"a": None}),
        c({"base": {"a": [1, 2]}, "patch": {"a": [3]}}, {"a": [3]}),
        c({"base": {"x": {"n": 1}}, "patch": {"x": {"v": [2]}}}, {"x": {"n": 1, "v": [2]}}, unchanged=True),
    ],
)

add(
    "copy_semantics",
    "path_assignment",
    "Assign a value to a nonempty list of string keys in a nested mapping. Create absent intermediate dicts, but encountering an existing non-dict intermediate raises ValueError. Preserve siblings and None/false/zero leaf values. Return a deep independent tree; never mutate input, including before an error.",
    """
def solve(data):
    _request(data)
    result = _copy(data["tree"])
    path = data["path"]
    if not path:
        raise ValueError("empty path")
    cursor = result
    for key in path[:-1]:
        if key not in cursor:
            cursor[key] = {}
        if not isinstance(cursor[key], dict):
            raise ValueError("nonmapping intermediate")
        cursor = cursor[key]
    cursor[path[-1]] = _copy(data["value"])
    return result
""",
    ("cursor = cursor[key]", "cursor = {}"),
    ('result = _copy(data["tree"])', 'result = data["tree"]'),
    [
        c({"tree": {"a": 1}, "path": ["b"], "value": 2}, {"a": 1, "b": 2}, new=True, public=True),
        c({"tree": {}, "path": ["x"], "value": None}, {"x": None}, public=True),
        c({"tree": {"a": {"keep": 1}}, "path": ["a", "new"], "value": 3}, {"a": {"keep": 1, "new": 3}}, new=True),
        c({"tree": {}, "path": ["a", "b", "c"], "value": False}, {"a": {"b": {"c": False}}}, new=True),
        c({"tree": {"a": 2}, "path": ["a", "b"], "value": 3}, None, exception="ValueError"),
        c({"tree": {}, "path": [], "value": 3}, None, exception="ValueError"),
        c({"tree": {"a": {"x": 1}}, "path": ["a", "x"], "value": 0}, {"a": {"x": 0}}, unchanged=True),
    ],
)

add(
    "copy_semantics",
    "group_records",
    "Group records by their 'group' string. A missing group uses '<missing>' (None is allowed as a distinct group too). Return list of {'group':key,'rows':records} in FIRST-group-appearance order, preserving record order and duplicate records. Groups must have independent row lists; do not mutate the input.",
    """
def solve(data):
    _request(data)
    order = []
    groups = {}
    shared = []
    for row in data["rows"]:
        key = row.get("group", "<missing>")
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(_copy(row))
    result = []
    for key in order:
        result.append({"group":key,"rows":groups[key]})
    return result
""",
    ("groups[key] = []", "groups[key] = shared"),
    ("for key in order:", "for key in sorted(order, key=lambda value:str(value)):"),
    [
        c(
            {"rows": [{"group": "a", "v": 1}]},
            [{"group": "a", "rows": [{"group": "a", "v": 1}]}],
            new=True,
            public=True,
        ),
        c({"rows": []}, [], public=True),
        c(
            {"rows": [{"group": "a"}, {"group": "b"}]},
            [{"group": "a", "rows": [{"group": "a"}]}, {"group": "b", "rows": [{"group": "b"}]}],
            new=True,
        ),
        c(
            {"rows": [{"group": "a", "v": 1}, {"group": "b", "v": 2}, {"group": "a", "v": 3}]},
            [
                {"group": "a", "rows": [{"group": "a", "v": 1}, {"group": "a", "v": 3}]},
                {"group": "b", "rows": [{"group": "b", "v": 2}]},
            ],
            new=True,
        ),
        c(
            {"rows": [{"group": "z"}, {"group": "a"}]},
            [{"group": "z", "rows": [{"group": "z"}]}, {"group": "a", "rows": [{"group": "a"}]}],
        ),
        c(
            {"rows": [{}, {"group": None}]},
            [{"group": "<missing>", "rows": [{}]}, {"group": None, "rows": [{"group": None}]}],
        ),
        c({"rows": [{"group": "a", "x": [1]}]}, [{"group": "a", "rows": [{"group": "a", "x": [1]}]}], unchanged=True),
    ],
)

add(
    "copy_semantics",
    "snapshot_history",
    "Start with a mapping, apply [key,value] updates, and return a history containing the initial state and an independent snapshot AFTER EACH update. No-op updates still produce snapshots. None and false are ordinary values; preserve unrelated keys and input immutability.",
    """
def solve(data):
    _request(data)
    state = _copy(data["state"])
    history = [_copy(state)]
    for key, value in data["updates"]:
        was_same = key in state and state[key] == value
        state[key] = _copy(value)
        history.append(_copy(state))
    return history
""",
    ("history.append(_copy(state))", "history.append(state)"),
    ("history.append(_copy(state))", "\n        if not was_same:\n            history.append(_copy(state))"),
    [
        c({"state": {"x": 1}, "updates": [["x", 2]]}, [{"x": 1}, {"x": 2}], new=True, public=True),
        c({"state": {}, "updates": []}, [{}], public=True),
        c({"state": {"x": 0}, "updates": [["x", 1], ["x", 2]]}, [{"x": 0}, {"x": 1}, {"x": 2}], new=True),
        c(
            {"state": {}, "updates": [["a", 1], ["b", 2], ["a", 3]]},
            [{}, {"a": 1}, {"a": 1, "b": 2}, {"a": 3, "b": 2}],
            new=True,
        ),
        c({"state": {"x": 1}, "updates": [["x", 1]]}, [{"x": 1}, {"x": 1}]),
        c({"state": {}, "updates": [["a", None], ["b", False]]}, [{}, {"a": None}, {"a": None, "b": False}]),
        c({"state": {"a": [1]}, "updates": [["a", [2]]]}, [{"a": [1]}, {"a": [2]}], unchanged=True),
    ],
)

add(
    "stable_ordering",
    "rank_top_k",
    "Return the top k rows by descending integer score, keeping original input order for equal scores. Missing score is zero; negative scores are valid. k<=0 returns empty; k larger than input returns all. Preserve complete row fields and do not mutate inputs.",
    """
def solve(data):
    _request(data)
    limit = data["k"]
    if limit <= 0:
        return []
    indexed = []
    for index, row in enumerate(data["rows"]):
        score = row.get("score", 0)
        indexed.append((score, index, _copy(row)))
    indexed.sort(key=lambda item:(-item[0],item[1]))
    selected = []
    for score, index, row in indexed[:limit]:
        selected.append(row)
    return selected
""",
    ("(-item[0],item[1])", "(item[0],item[1])"),
    ("(-item[0],item[1])", "(-item[0],-item[1])"),
    [
        c(
            {"rows": [{"id": "a", "score": 1}, {"id": "b", "score": 3}], "k": 1},
            [{"id": "b", "score": 3}],
            new=True,
            public=True,
        ),
        c({"rows": [], "k": 2}, [], public=True),
        c({"rows": [{"score": -2}, {"score": -1}], "k": 2}, [{"score": -1}, {"score": -2}], new=True),
        c({"rows": [{"score": 4}, {"score": 2}, {"score": 8}], "k": 2}, [{"score": 8}, {"score": 4}], new=True),
        c(
            {"rows": [{"id": "z", "score": 1}, {"id": "a", "score": 1}], "k": 2},
            [{"id": "z", "score": 1}, {"id": "a", "score": 1}],
        ),
        c({"rows": [{"id": "x"}, {"score": -1}], "k": 10}, [{"id": "x"}, {"score": -1}]),
        c({"rows": [{"score": 1}], "k": 0}, [], unchanged=True),
    ],
)

add(
    "stable_ordering",
    "deadline_queue",
    "Select at most k jobs whose ready time is <= now. Sort eligible jobs by earliest deadline, ties by original order (priority is metadata, not a sort key). Return selected IDs and remaining complete jobs in ORIGINAL order. k<=0 selects none. Do not mutate inputs.",
    """
def solve(data):
    _request(data)
    ready = []
    for index, job in enumerate(data["jobs"]):
        if job["ready"] <= data["now"]:
            ready.append((job["deadline"],index))
    ready.sort(key=lambda item:(item[0],item[1]))
    chosen = [index for deadline,index in ready[:max(0,data["k"])]]
    ids = [data["jobs"][index]["id"] for index in chosen]
    remaining = []
    for index,job in enumerate(data["jobs"]):
        if index not in chosen:
            remaining.append(_copy(job))
    return {"selected":ids,"remaining":remaining}
""",
    ("(item[0],item[1])", "(-item[0],item[1])"),
    ('job["ready"] <= data["now"]', 'job["ready"] < data["now"]'),
    [
        c(
            {"jobs": [{"id": "a", "ready": 0, "deadline": 2}], "now": 1, "k": 1},
            {"selected": ["a"], "remaining": []},
            new=True,
            public=True,
        ),
        c({"jobs": [], "now": 0, "k": 1}, {"selected": [], "remaining": []}, public=True),
        c(
            {
                "jobs": [{"id": "b", "ready": 0, "deadline": 9}, {"id": "a", "ready": 0, "deadline": 2}],
                "now": 1,
                "k": 1,
            },
            {"selected": ["a"], "remaining": [{"id": "b", "ready": 0, "deadline": 9}]},
            new=True,
        ),
        c(
            {
                "jobs": [{"id": "a", "ready": 0, "deadline": 3}, {"id": "b", "ready": 0, "deadline": 1}],
                "now": 1,
                "k": 2,
            },
            {"selected": ["b", "a"], "remaining": []},
            new=True,
        ),
        c({"jobs": [{"id": "a", "ready": 2, "deadline": 3}], "now": 2, "k": 1}, {"selected": ["a"], "remaining": []}),
        c(
            {
                "jobs": [{"id": "z", "ready": 0, "deadline": 3}, {"id": "a", "ready": 0, "deadline": 3}],
                "now": 1,
                "k": 2,
            },
            {"selected": ["z", "a"], "remaining": []},
        ),
        c(
            {"jobs": [{"id": "x", "ready": 3, "deadline": 4}], "now": 2, "k": 4},
            {"selected": [], "remaining": [{"id": "x", "ready": 3, "deadline": 4}]},
            unchanged=True,
        ),
    ],
)

add(
    "stable_ordering",
    "latest_payload_first_position",
    "For each record ID retain the LAST payload, but order IDs by their FIRST appearance. Duplicate identical records do not add rows. None payload is an ordinary retained value, not a tombstone. Preserve all fields of the final row and input immutability.",
    """
def solve(data):
    _request(data)
    order = []
    latest = {}
    for row in data["rows"]:
        key = row["id"]
        if key not in latest:
            order.append(key)
        latest[key] = _copy(row)
    result = []
    for key in order:
        result.append(latest[key])
    return result
""",
    ("if key not in latest:", "if True:\n            if key in order:\n                order.remove(key)"),
    (
        "result.append(latest[key])",
        '\n        if latest[key].get("payload") is not None:\n            result.append(latest[key])',
    ),
    [
        c({"rows": [{"id": "a", "payload": 1}]}, [{"id": "a", "payload": 1}], new=True, public=True),
        c({"rows": []}, [], public=True),
        c(
            {"rows": [{"id": "a", "payload": 1}, {"id": "b", "payload": 2}, {"id": "a", "payload": 3}]},
            [{"id": "a", "payload": 3}, {"id": "b", "payload": 2}],
            new=True,
        ),
        c(
            {"rows": [{"id": "b", "payload": 1}, {"id": "a", "payload": 2}, {"id": "b", "payload": 4}]},
            [{"id": "b", "payload": 4}, {"id": "a", "payload": 2}],
            new=True,
        ),
        c({"rows": [{"id": "a", "payload": None}]}, [{"id": "a", "payload": None}]),
        c({"rows": [{"id": "a", "payload": 0}, {"id": "a", "payload": 0}]}, [{"id": "a", "payload": 0}]),
        c({"rows": [{"id": "x", "payload": {"v": 1}}]}, [{"id": "x", "payload": {"v": 1}}], unchanged=True),
    ],
)

add(
    "stable_ordering",
    "merge_sorted_streams",
    "Merge two already timestamp-sorted streams. Preserve within-stream order; on equal timestamp choose LEFT before RIGHT. Preserve duplicates (including identical records), complete row fields, and inputs. No global reordering by payload or identifier.",
    """
def solve(data):
    _request(data)
    left, right = data["left"], data["right"]
    i, j = 0, 0
    result = []
    while i < len(left) or j < len(right):
        if j == len(right) or (i < len(left) and left[i]["time"] <= right[j]["time"]):
            row = left[i]
            i += 1
        else:
            row = right[j]
            j += 1
        result.append(_copy(row))
    return result
""",
    ('left[i]["time"] <= right[j]["time"]', 'left[i]["time"] < right[j]["time"]'),
    (
        "result.append(_copy(row))",
        "\n        if not result or result[-1] != row:\n            result.append(_copy(row))",
    ),
    [
        c({"left": [{"time": 1}], "right": [{"time": 2}]}, [{"time": 1}, {"time": 2}], public=True, new=True),
        c({"left": [], "right": []}, [], public=True),
        c(
            {"left": [{"time": 1, "id": "L"}], "right": [{"time": 1, "id": "R"}]},
            [{"time": 1, "id": "L"}, {"time": 1, "id": "R"}],
            new=True,
        ),
        c(
            {"left": [{"time": 1, "id": "L1"}, {"time": 1, "id": "L2"}], "right": [{"time": 1, "id": "R"}]},
            [{"time": 1, "id": "L1"}, {"time": 1, "id": "L2"}, {"time": 1, "id": "R"}],
            new=True,
        ),
        c({"left": [{"time": 1}, {"time": 1}], "right": []}, [{"time": 1}, {"time": 1}]),
        c({"left": [], "right": [{"time": -2}, {"time": 0}]}, [{"time": -2}, {"time": 0}]),
        c({"left": [{"time": 1, "v": [1]}], "right": []}, [{"time": 1, "v": [1]}], unchanged=True),
    ],
)

add(
    "missingness",
    "fill_missing_defaults",
    "Fill ONLY absent keys from defaults. Present None, False, 0, empty string/list/dict must remain unchanged. Keep unknown supplied keys and copy all nested values; never mutate input or defaults.",
    """
def solve(data):
    _request(data)
    result = _copy(data["values"])
    defaults = data["defaults"]
    for key, value in defaults.items():
        missing = key not in result
        if missing:
            result[key] = _copy(value)
    preserved = {}
    for key, value in result.items():
        preserved[key] = value
    return preserved
""",
    ("missing = key not in result", "missing = not result.get(key)"),
    ("preserved[key] = value", "\n        if key in defaults:\n            preserved[key] = value"),
    [
        c({"values": {}, "defaults": {"x": 1}}, {"x": 1}, new=True, public=True),
        c({"values": {"x": 2}, "defaults": {"x": 1}}, {"x": 2}, public=True),
        c({"values": {"x": False}, "defaults": {"x": True}}, {"x": False}, new=True),
        c(
            {"values": {"x": None, "y": 0, "z": ""}, "defaults": {"x": 1, "y": 2, "z": "default"}},
            {"x": None, "y": 0, "z": ""},
            new=True,
        ),
        c({"values": {"extra": 3}, "defaults": {"x": 1}}, {"extra": 3, "x": 1}),
        c({"values": {"x": [], "y": {}}, "defaults": {"x": [1], "y": {"n": 1}}}, {"x": [], "y": {}}),
        c({"values": {}, "defaults": {"x": {"n": [1]}}}, {"x": {"n": [1]}}, unchanged=True),
    ],
)

add(
    "missingness",
    "layered_override",
    "Merge base, environment, and request layers in that precedence order. Key presence determines overriding even for None/False/0/empty values. Mapping values replace wholesale (NOT deep merge). Inputs remain unchanged and unrelated base keys survive.",
    """
def solve(data):
    _request(data)
    result = _copy(data["base"])
    for layer in [data["environment"], data["request"]]:
        for key in layer:
            value = layer[key]
            result[key] = _copy(value)
    ordered = {}
    for key in result:
        ordered[key] = result[key]
    return ordered
""",
    ("result[key] = _copy(value)", "\n            if value:\n                result[key] = _copy(value)"),
    ('result = _copy(data["base"])', 'result = data["base"]'),
    [
        c({"base": {"x": 1}, "environment": {"x": 2}, "request": {"x": 3}}, {"x": 3}, new=True, public=True),
        c({"base": {"x": 1}, "environment": {}, "request": {}}, {"x": 1}, public=True),
        c({"base": {"x": 1}, "environment": {"x": False}, "request": {}}, {"x": False}, new=True),
        c({"base": {"x": 1}, "environment": {"x": 2}, "request": {"x": None}}, {"x": None}, new=True),
        c({"base": {"x": {"a": 1}}, "environment": {"x": {"b": 2}}, "request": {}}, {"x": {"b": 2}}),
        c({"base": {"a": 1}, "environment": {"b": 0}, "request": {"c": ""}}, {"a": 1, "b": 0, "c": ""}),
        c({"base": {"x": 1}, "environment": {"x": 2}, "request": {}}, {"x": 2}, unchanged=True),
    ],
)

add(
    "missingness",
    "record_projection",
    "Project rows using ordered [source,target,default] rules. Absent source uses default; a present false-like value remains. Later rules for the same target overwrite earlier ones. Ignore unspecified source fields; preserve row order, duplicates and input objects.",
    """
def solve(data):
    _request(data)
    result = []
    for row in data["rows"]:
        output = {}
        for source, target, default in data["rules"]:
            if source in row:
                value = row[source]
            else:
                value = default
            output[target] = _copy(value)
        result.append(output)
    return result
""",
    ("if source in row:", "if row.get(source):"),
    (
        "output[target] = _copy(value)",
        "\n            if target not in output:\n                output[target] = _copy(value)",
    ),
    [
        c({"rows": [{"a": 2}], "rules": [["a", "x", 1]]}, [{"x": 2}], new=True, public=True),
        c({"rows": [{}], "rules": [["a", "x", 1]]}, [{"x": 1}], public=True),
        c(
            {"rows": [{"a": 0}, {"a": False}, {"a": None}], "rules": [["a", "x", 9]]},
            [{"x": 0}, {"x": False}, {"x": None}],
            new=True,
        ),
        c({"rows": [{"a": ""}, {"a": []}], "rules": [["a", "x", 9]]}, [{"x": ""}, {"x": []}], new=True),
        c({"rows": [{"a": 1, "b": 2}], "rules": [["a", "x", 0], ["b", "x", 0]]}, [{"x": 2}]),
        c({"rows": [{"a": 1}, {"a": 1}], "rules": [["a", "x", 0]]}, [{"x": 1}, {"x": 1}]),
        c({"rows": [{"a": {"n": 1}}], "rules": [["a", "x", {}]]}, [{"x": {"n": 1}}], unchanged=True),
    ],
)

add(
    "missingness",
    "profile_patch",
    "Apply a profile patch. The EXACT object {'delete':True} deletes a key; any other value, including None, False, {'delete':False}, or {'delete':True,'extra':1}, is stored as ordinary data. Deleting a missing key is a no-op. Preserve other fields and never mutate either input.",
    """
def solve(data):
    _request(data)
    result = _copy(data["profile"])
    for key, value in data["patch"].items():
        is_delete = isinstance(value, dict) and set(value) == {"delete"} and value["delete"] is True
        if is_delete:
            result.pop(key, None)
        else:
            result[key] = _copy(value)
    output = {}
    for key in result:
        output[key] = result[key]
    return output
""",
    ('set(value) == {"delete"} and value["delete"] is True', 'value.get("delete") is True'),
    ("result.pop(key, None)", "result.pop(key)"),
    [
        c({"profile": {"x": 1}, "patch": {"x": {"delete": True}}}, {}, new=True, public=True),
        c({"profile": {"x": 1}, "patch": {}}, {"x": 1}, public=True),
        c(
            {"profile": {"x": 1}, "patch": {"x": {"delete": True, "extra": 1}}},
            {"x": {"delete": True, "extra": 1}},
            new=True,
        ),
        c({"profile": {}, "patch": {"x": {"delete": False}}}, {"x": {"delete": False}}, new=True),
        c({"profile": {"x": 1}, "patch": {"missing": {"delete": True}}}, {"x": 1}),
        c({"profile": {"x": 1}, "patch": {"x": None, "y": False}}, {"x": None, "y": False}),
        c({"profile": {"x": {"v": 1}}, "patch": {"y": [2]}}, {"x": {"v": 1}, "y": [2]}, unchanged=True),
    ],
)

add(
    "numeric_boundaries",
    "largest_remainder",
    "Allocate nonnegative integer seats proportionally to nonnegative integer weights. Floor each exact quota, then allocate the remaining seats to descending integer remainders, ties in original index order. Return one integer per weight. Zero seats returns zeros; zero total weight is legal only when seats is zero, otherwise ValueError. Reject negative seats or weights. Preserve input.",
    """
def solve(data):
    _request(data)
    weights, seats = data["weights"], data["seats"]
    if seats < 0 or any(weight < 0 for weight in weights):
        raise ValueError("negative allocation input")
    total = sum(weights)
    if total == 0:
        if seats:
            raise ValueError("no positive weight")
        return [0 for weight in weights]
    allocated = [weight * seats // total for weight in weights]
    missing = seats - sum(allocated)
    order = sorted(range(len(weights)), key=lambda i: (-(weights[i] * seats % total), i))
    for index in order[:missing]:
        allocated[index] += 1
    return allocated
""",
    ("for index in order[:missing]:", "for index in order[:0]:"),
    ("% total), i)", "% total), -i)"),
    [
        c({"weights": [2, 1], "seats": 4}, [3, 1], new=True, public=True),
        c({"weights": [0, 0], "seats": 0}, [0, 0], public=True),
        c({"weights": [1, 2, 4], "seats": 5}, [1, 1, 3], new=True),
        c({"weights": [0, 3, 1], "seats": 3}, [0, 2, 1], new=True),
        c({"weights": [1, 1, 1], "seats": 2}, [1, 1, 0]),
        c({"weights": [0, 0], "seats": 1}, None, exception="ValueError"),
        c({"weights": [4, 2], "seats": 3}, [2, 1], unchanged=True),
    ],
)

add(
    "numeric_boundaries",
    "window_quota",
    "Process nonnegative integer amounts against a fixed-window quota. Start and used describe the current window; events [time,amount] are in nondecreasing time, time>=start and window>0. At time>=start+window reset usage and advance start by whole windows. Accept iff used+amount<=limit; rejection must NOT consume quota. Zero amounts may be accepted. Return start, used and one Boolean per event. Do not mutate input.",
    """
def solve(data):
    _request(data)
    start, used = data["start"], data["used"]
    window, limit = data["window"], data["limit"]
    accepted = []
    for now, amount in data["events"]:
        if now >= start + window:
            start += ((now - start) // window) * window
            used = 0
        ok = used + amount <= limit
        if ok:
            used += amount
        accepted.append(ok)
    return {"start": start, "used": used, "accepted": accepted}
""",
    ("if ok:\n            used += amount", "if True:\n            used += amount"),
    ("if now >= start + window:", "if now > start + window:"),
    [
        c(
            {"start": 0, "used": 0, "window": 10, "limit": 5, "events": [[1, 2]]},
            {"start": 0, "used": 2, "accepted": [True]},
            new=True,
            public=True,
        ),
        c(
            {"start": 0, "used": 0, "window": 10, "limit": 5, "events": []},
            {"start": 0, "used": 0, "accepted": []},
            public=True,
        ),
        c(
            {"start": 0, "used": 3, "window": 10, "limit": 5, "events": [[2, 4], [3, 2]]},
            {"start": 0, "used": 5, "accepted": [False, True]},
            new=True,
        ),
        c(
            {"start": 0, "used": 5, "window": 10, "limit": 5, "events": [[2, 1], [4, 0]]},
            {"start": 0, "used": 5, "accepted": [False, True]},
            new=True,
        ),
        c(
            {"start": 0, "used": 5, "window": 10, "limit": 5, "events": [[10, 1]]},
            {"start": 10, "used": 1, "accepted": [True]},
        ),
        c(
            {"start": 0, "used": 5, "window": 10, "limit": 5, "events": [[35, 2]]},
            {"start": 30, "used": 2, "accepted": [True]},
        ),
        c(
            {"start": 0, "used": 0, "window": 10, "limit": 5, "events": [[1, 5]]},
            {"start": 0, "used": 5, "accepted": [True]},
            unchanged=True,
        ),
    ],
)

add(
    "numeric_boundaries",
    "interval_union",
    "Return total covered length inside [start,end) of half-open integer intervals. Clip each interval, discard nonpositive lengths, and merge overlap without double billing. Adjacent intervals may be merged but a positive gap is never billed. Input order is arbitrary and duplicates are legal; preserve input. The window satisfies start<=end.",
    """
def solve(data):
    _request(data)
    clipped = []
    for left, right in data["intervals"]:
        left = max(left, data["start"])
        right = min(right, data["end"])
        if left < right:
            clipped.append([left, right])
    clipped.sort()
    merged = []
    for left, right in clipped:
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    return sum(right - left for left, right in merged)
""",
    ("if merged and left <= merged[-1][1]:", "if False:"),
    ("left <= merged[-1][1]:", "left <= merged[-1][1] + 1:"),
    [
        c({"start": 0, "end": 10, "intervals": [[1, 4], [3, 6]]}, 5, new=True, public=True),
        c({"start": 0, "end": 10, "intervals": []}, 0, public=True),
        c({"start": 2, "end": 8, "intervals": [[0, 9], [3, 5], [0, 9]]}, 6, new=True),
        c({"start": -5, "end": 5, "intervals": [[-4, 0], [-2, 3]]}, 7, new=True),
        c({"start": 0, "end": 10, "intervals": [[1, 3], [4, 6]]}, 4),
        c({"start": 0, "end": 3, "intervals": [[2, 2], [4, 1], [-3, -1]]}, 0),
        c({"start": 0, "end": 10, "intervals": [[5, 7], [1, 5]]}, 6, unchanged=True),
    ],
)

add(
    "numeric_boundaries",
    "rolling_rational_mean",
    "For each input integer or None, return the mean of non-None values in the last window input positions. window is a positive integer. Zero is a valid value; None consumes a window position but not the divisor. Return a reduced [numerator,positive_denominator] or None if no numeric values; keep output aligned with all inputs and never mutate input.",
    """
def _gcd(a, b):
    a = abs(a)
    while b:
        a, b = b, a % b
    return a

def solve(data):
    _request(data)
    history, result = [], []
    for value in data["values"]:
        history.append(value)
        history = history[-data["window"]:]
        numbers = [item for item in history if item is not None]
        if not numbers:
            result.append(None)
            continue
        numerator, denominator = sum(numbers), len(numbers)
        divisor = _gcd(numerator, denominator)
        result.append([numerator // divisor, denominator // divisor])
    return result
""",
    ("sum(numbers), len(numbers)", "sum(numbers), len(history)"),
    ("if item is not None]", "if item]"),
    [
        c({"values": [2, 4], "window": 2}, [[2, 1], [3, 1]], new=True, public=True),
        c({"values": [], "window": 1}, [], public=True),
        c({"values": [None, 3, None, 6], "window": 2}, [None, [3, 1], [3, 1], [6, 1]], new=True),
        c({"values": [2, None, 4], "window": 3}, [[2, 1], [2, 1], [3, 1]], new=True),
        c({"values": [0, 2, 0], "window": 2}, [[0, 1], [1, 1], [1, 1]]),
        c({"values": [-2, 3, None], "window": 2}, [[-2, 1], [1, 2], [3, 1]]),
        c({"values": [1, 2, 3], "window": 1}, [[1, 1], [2, 1], [3, 1]], unchanged=True),
    ],
)

add(
    "error_recovery",
    "batch_reciprocals",
    "Map each integer x to integer floor quotient 20//x. A zero produces {'index':original_index,'error':'zero'} in errors and does not stop later processing. Successful entries are {'index':original_index,'value':quotient}. Return separate values and errors lists, both in arrival order. Preserve negative floor-division semantics and all input objects.",
    """
def solve(data):
    _request(data)
    values, errors = [], []
    for index, value in enumerate(data["values"]):
        if value == 0:
            errors.append({"index": index, "error": "zero"})
            continue
        quotient = 20 // value
        values.append({"index": index, "value": quotient})
    return {"values": values, "errors": errors}
""",
    ("            continue", "            break"),
    ('"index": index, "error"', '"index": len(values), "error"'),
    [
        c(
            {"values": [2, 4]},
            {"values": [{"index": 0, "value": 10}, {"index": 1, "value": 5}], "errors": []},
            new=True,
            public=True,
        ),
        c({"values": []}, {"values": [], "errors": []}, public=True),
        c(
            {"values": [0, 2]},
            {"values": [{"index": 1, "value": 10}], "errors": [{"index": 0, "error": "zero"}]},
            new=True,
        ),
        c(
            {"values": [4, 0, 5]},
            {"values": [{"index": 0, "value": 5}, {"index": 2, "value": 4}], "errors": [{"index": 1, "error": "zero"}]},
            new=True,
        ),
        c(
            {"values": [0, 0, 2]},
            {
                "values": [{"index": 2, "value": 10}],
                "errors": [{"index": 0, "error": "zero"}, {"index": 1, "error": "zero"}],
            },
        ),
        c({"values": [-3, 6]}, {"values": [{"index": 0, "value": -7}, {"index": 1, "value": 3}], "errors": []}),
        c(
            {"values": [2, 0]},
            {"values": [{"index": 0, "value": 10}], "errors": [{"index": 1, "error": "zero"}]},
            unchanged=True,
        ),
    ],
)

add(
    "error_recovery",
    "fallback_lookup",
    "Process ordered providers with status found, absent, or error. First found stops the chain even when value is False, None, zero or empty. Collect preceding error messages in order; absent is ignored. Return {'found':bool,'value':value-or-None,'errors':list,'visited':count}. If none found visit all providers. Do not mutate input.",
    """
def solve(data):
    _request(data)
    errors = []
    visited = 0
    for provider in data["providers"]:
        visited += 1
        status = provider["status"]
        if status == "error":
            errors.append(provider["message"])
        elif status == "found":
            return {"found": True, "value": _copy(provider["value"]), "errors": errors, "visited": visited}
    return {"found": False, "value": None, "errors": errors, "visited": visited}
""",
    ('elif status == "found":', 'elif status == "found" and provider["value"]:'),
    ('"errors": errors, "visited": visited}', '"errors": [], "visited": visited}'),
    [
        c(
            {"providers": [{"status": "found", "value": 3}]},
            {"found": True, "value": 3, "errors": [], "visited": 1},
            new=True,
            public=True,
        ),
        c({"providers": []}, {"found": False, "value": None, "errors": [], "visited": 0}, public=True),
        c(
            {"providers": [{"status": "found", "value": False}, {"status": "found", "value": 4}]},
            {"found": True, "value": False, "errors": [], "visited": 1},
            new=True,
        ),
        c(
            {"providers": [{"status": "absent"}, {"status": "found", "value": None}]},
            {"found": True, "value": None, "errors": [], "visited": 2},
            new=True,
        ),
        c(
            {"providers": [{"status": "error", "message": "timeout"}, {"status": "found", "value": 2}]},
            {"found": True, "value": 2, "errors": ["timeout"], "visited": 2},
        ),
        c(
            {"providers": [{"status": "error", "message": "a"}, {"status": "error", "message": "b"}]},
            {"found": False, "value": None, "errors": ["a", "b"], "visited": 2},
        ),
        c(
            {"providers": [{"status": "found", "value": {"x": 1}}, {"status": "error", "message": "x"}]},
            {"found": True, "value": {"x": 1}, "errors": [], "visited": 1},
            unchanged=True,
        ),
    ],
)

add(
    "error_recovery",
    "page_checkpoint",
    "Consume pages {'token':str,'rows':list}. Every row must be a dict containing id and value. Commit a page's copied rows and token only after ALL rows validate. On first invalid page stop and return previously committed rows/checkpoint with ok=False. Empty pages are valid and advance checkpoint. Initial checkpoint may be None; duplicate row IDs are retained. Never mutate input.",
    """
def solve(data):
    _request(data)
    committed = []
    checkpoint = data["checkpoint"]
    for page in data["pages"]:
        staged = []
        for row in page["rows"]:
            if not isinstance(row, dict) or "id" not in row or "value" not in row:
                return {"ok": False, "rows": committed, "checkpoint": checkpoint}
            staged.append(_copy(row))
        committed.extend(staged)
        checkpoint = page["token"]
    return {"ok": True, "rows": committed, "checkpoint": checkpoint}
""",
    ("        staged = []", '        staged = []\n        checkpoint = page["token"]'),
    ('checkpoint = page["token"]', 'checkpoint = page["token"] if staged else None'),
    [
        c(
            {"checkpoint": None, "pages": [{"token": "a", "rows": [{"id": 1, "value": 2}]}]},
            {"ok": True, "rows": [{"id": 1, "value": 2}], "checkpoint": "a"},
            new=True,
            public=True,
        ),
        c({"checkpoint": "old", "pages": []}, {"ok": True, "rows": [], "checkpoint": "old"}, public=True),
        c(
            {"checkpoint": "old", "pages": [{"token": "bad", "rows": [{"id": 1, "value": 2}, {}]}]},
            {"ok": False, "rows": [], "checkpoint": "old"},
            new=True,
        ),
        c(
            {
                "checkpoint": None,
                "pages": [{"token": "a", "rows": [{"id": 1, "value": 2}]}, {"token": "bad", "rows": [None]}],
            },
            {"ok": False, "rows": [{"id": 1, "value": 2}], "checkpoint": "a"},
            new=True,
        ),
        c(
            {"checkpoint": "old", "pages": [{"token": "empty", "rows": []}]},
            {"ok": True, "rows": [], "checkpoint": "empty"},
        ),
        c(
            {
                "checkpoint": None,
                "pages": [{"token": "x", "rows": [{"id": 0, "value": False}, {"id": 0, "value": None}]}],
            },
            {"ok": True, "rows": [{"id": 0, "value": False}, {"id": 0, "value": None}], "checkpoint": "x"},
        ),
        c(
            {"checkpoint": None, "pages": [{"token": "x", "rows": [{"id": 1, "value": {"a": 2}}]}]},
            {"ok": True, "rows": [{"id": 1, "value": {"a": 2}}], "checkpoint": "x"},
            unchanged=True,
        ),
    ],
)

add(
    "error_recovery",
    "retry_journal",
    "Read response status integers in order, at most max_attempts (nonnegative). Record {'attempt':1-based,'key':unchanged request key,'status':status} for every attempted call. Status 200 succeeds; 429 and 503 retry; any other status stops fatally. On exhausted responses/attempts return ok=False. Return ok and journal; preserve exact key, order, input and zero-attempt behavior.",
    """
def solve(data):
    _request(data)
    journal = []
    for index, status in enumerate(data["responses"][:data["max_attempts"]]):
        key = data["key"]
        journal.append({"attempt": index + 1, "key": key, "status": status})
        if status == 200:
            return {"ok": True, "journal": journal}
        if status not in (429, 503):
            break
    return {"ok": False, "journal": journal}
""",
    ('key = data["key"]', 'key = data["key"] if index == 0 else data["key"] + str(index)'),
    ("if status not in (429, 503):", "if False:"),
    [
        c(
            {"key": "x", "responses": [200], "max_attempts": 2},
            {"ok": True, "journal": [{"attempt": 1, "key": "x", "status": 200}]},
            new=True,
            public=True,
        ),
        c({"key": "x", "responses": [], "max_attempts": 2}, {"ok": False, "journal": []}, public=True),
        c(
            {"key": "x", "responses": [503, 200], "max_attempts": 3},
            {
                "ok": True,
                "journal": [{"attempt": 1, "key": "x", "status": 503}, {"attempt": 2, "key": "x", "status": 200}],
            },
            new=True,
        ),
        c(
            {"key": "x", "responses": [429, 503], "max_attempts": 2},
            {
                "ok": False,
                "journal": [{"attempt": 1, "key": "x", "status": 429}, {"attempt": 2, "key": "x", "status": 503}],
            },
            new=True,
        ),
        c(
            {"key": "x", "responses": [401, 200], "max_attempts": 3},
            {"ok": False, "journal": [{"attempt": 1, "key": "x", "status": 401}]},
        ),
        c({"key": "x", "responses": [200], "max_attempts": 0}, {"ok": False, "journal": []}),
        c(
            {"key": "", "responses": [503, 200], "max_attempts": 1},
            {"ok": False, "journal": [{"attempt": 1, "key": "", "status": 503}]},
            unchanged=True,
        ),
    ],
)

add(
    "stateful_parsing",
    "escaped_fields",
    "Split text on unescaped commas. Backslash escapes exactly the next character, including comma or backslash, and the escape marker is removed. Preserve all empty fields including a trailing empty field; empty text gives ['']. A final unpaired backslash raises ValueError. Do not trim spaces or mutate input.",
    r"""
def solve(data):
    _request(data)
    fields, current = [], []
    escaped = False
    for char in data["text"]:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ",":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        raise ValueError("incomplete escape")
    fields.append("".join(current))
    return fields
""",
    ("if escaped:\n            current.append(char)", 'if escaped and char != ",":\n            current.append(char)'),
    (
        '    fields.append("".join(current))\n    return fields',
        '    if current:\n        fields.append("".join(current))\n    return fields',
    ),
    [
        c({"text": "a,b"}, ["a", "b"], new=True, public=True),
        c({"text": "x"}, ["x"], public=True),
        c({"text": r"a\,b,c"}, ["a,b", "c"], new=True),
        c({"text": r"x\,y\,z"}, ["x,y,z"], new=True),
        c({"text": "a,"}, ["a", ""]),
        c({"text": "bad\\"}, None, exception="ValueError"),
        c({"text": r" a,\\b"}, [" a", "\\b"], unchanged=True),
    ],
)

add(
    "stateful_parsing",
    "quoted_record",
    "Parse one CSV-like record, no newlines. Quoted fields start with a double quote only at field start; inside, doubled double quotes mean one quote and commas are literal. After closing quote only comma or end is valid. Unquoted quote or unclosed quoted field raises ValueError. Preserve unquoted spaces, empty fields and trailing empties. Return field strings; preserve input.",
    """
def solve(data):
    _request(data)
    fields, current = [], []
    quoted, closed, index = False, False, 0
    text = data["text"]
    while index < len(text):
        char = text[index]
        if quoted:
            if char == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    current.append('"')
                    index += 1
                else:
                    quoted, closed = False, True
            else:
                current.append(char)
        elif char == ",":
            fields.append("".join(current))
            current, closed = [], False
        elif closed:
            raise ValueError("characters after closing quote")
        elif char == '"':
            if current:
                raise ValueError("quote inside unquoted field")
            quoted = True
        else:
            current.append(char)
        index += 1
    if quoted:
        raise ValueError("unclosed quote")
    fields.append("".join(current))
    return fields
""",
    (
        "            else:\n                current.append(char)",
        '            elif char != ",":\n                current.append(char)',
    ),
    ("return fields", "return [field.strip() for field in fields]"),
    [
        c({"text": "a,b"}, ["a", "b"], new=True, public=True),
        c({"text": ""}, [""], public=True),
        c({"text": '"a,b",c'}, ["a,b", "c"], new=True),
        c({"text": '"a,""b,c""",d'}, ['a,"b,c"', "d"], new=True),
        c({"text": " a , b "}, [" a ", " b "]),
        c({"text": '"a"x'}, None, exception="ValueError"),
        c({"text": '"a",,'}, ["a", "", ""], unchanged=True),
    ],
)

add(
    "stateful_parsing",
    "chunked_lines",
    "Feed string chunks into a line buffer. Concatenate across chunk boundaries; each newline emits a line, removing exactly one immediately preceding carriage return (CRLF). Preserve other carriage returns and blank lines. Return {'lines':list,'pending':str}; flush=True emits a nonempty final fragment and clears it, flush=False leaves it pending. No phantom line after a final newline; preserve input.",
    r"""
def solve(data):
    _request(data)
    pending = ""
    lines = []
    for chunk in data["chunks"]:
        pending += chunk
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            if line.endswith("\r"):
                line = line[:-1]
            lines.append(line)
    if data["flush"] and pending:
        lines.append(pending)
        pending = ""
    return {"lines": lines, "pending": pending}
""",
    ("pending += chunk", "pending = chunk"),
    ('"lines": lines', '"lines": [line for line in lines if line]'),
    [
        c({"chunks": ["a\nb\n"], "flush": False}, {"lines": ["a", "b"], "pending": ""}, new=True, public=True),
        c({"chunks": [], "flush": True}, {"lines": [], "pending": ""}, public=True),
        c({"chunks": ["ab", "c\n"], "flush": False}, {"lines": ["abc"], "pending": ""}, new=True),
        c({"chunks": ["x\r", "\ny", "z"], "flush": True}, {"lines": ["x", "yz"], "pending": ""}, new=True),
        c({"chunks": ["\n\r\n"], "flush": False}, {"lines": ["", ""], "pending": ""}),
        c({"chunks": ["a\rb"], "flush": False}, {"lines": [], "pending": "a\rb"}),
        c({"chunks": ["x\n", "tail"], "flush": False}, {"lines": ["x"], "pending": "tail"}, unchanged=True),
    ],
)

add(
    "stateful_parsing",
    "balanced_brackets",
    "Validate (), [] and {} nesting outside single- or double-quoted strings. Inside quotes backslash escapes next character; brackets there are ignored. Return bool. Reject mismatched/extra closers, remaining opens, unclosed quotes or dangling quoted escape. Empty input and text without brackets are balanced. Preserve input.",
    r"""
def solve(data):
    _request(data)
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    quote, escaped = None, False
    for char in data["text"]:
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()
    return not stack and quote is None
""",
    ("if not stack or stack[-1] != pairs[char]:", "if not stack:"),
    ("return not stack and quote is None", 'return bool(data["text"]) and not stack and quote is None'),
    [
        c({"text": "([])"}, True, new=True, public=True),
        c({"text": "hello"}, True, public=True),
        c({"text": "([)]"}, False, new=True),
        c({"text": "{]"}, False, new=True),
        c({"text": ""}, True),
        c({"text": '("[")'}, True),
        c({"text": "'unterminated"}, False, unchanged=True),
    ],
)

add(
    "dependency_consistency",
    "dependency_closure",
    "Return dependency-first DFS postorder for ordered roots and graph dependency lists. Each name appears once. Visit roots and each node's dependencies in their listed order. Unknown names are valid leaf nodes. A reachable cycle raises ValueError, but unreachable cycles do not matter. Preserve graph and roots; duplicate roots/edges do not duplicate output.",
    """
def solve(data):
    _request(data)
    done, active, result = set(), set(), []
    def visit(node):
        if node in active:
            raise ValueError("dependency cycle")
        if node in done:
            return
        active.add(node)
        for dependency in data["graph"].get(node, []):
            visit(dependency)
        active.remove(node)
        done.add(node)
        result.append(node)
    for root in data["roots"]:
        visit(root)
    return result
""",
    ('raise ValueError("dependency cycle")', "return"),
    ("        result.append(node)", '        if node in data["graph"]:\n            result.append(node)'),
    [
        c({"graph": {"a": ["b"], "b": []}, "roots": ["a"]}, ["b", "a"], new=True, public=True),
        c({"graph": {}, "roots": []}, [], public=True),
        c({"graph": {"a": ["b"], "b": ["a"]}, "roots": ["a"]}, None, new=True, exception="ValueError"),
        c({"graph": {"a": ["a"]}, "roots": ["a"]}, None, new=True, exception="ValueError"),
        c({"graph": {"a": ["external"]}, "roots": ["a"]}, ["external", "a"]),
        c({"graph": {"a": ["c", "b", "c"], "b": [], "c": [], "x": ["x"]}, "roots": ["a", "b"]}, ["c", "b", "a"]),
        c({"graph": {"x": []}, "roots": ["x", "x"]}, ["x"], unchanged=True),
    ],
)

add(
    "dependency_consistency",
    "invalidate_dependents",
    "Graph maps each node to its dependencies. Return the transitive reverse-dependency invalidation order: seed names first in listed order (including unknown names), deduplicated, then breadth-first dependent discovery. For each popped name scan graph nodes in insertion order. Cycles terminate and each node appears once. Do not mutate inputs.",
    """
def solve(data):
    _request(data)
    queue, seen = [], set()
    for seed in data["seeds"]:
        if seed not in seen:
            seen.add(seed)
            queue.append(seed)
    index = 0
    while index < len(queue):
        current = queue[index]
        index += 1
        for node, dependencies in data["graph"].items():
            if current in dependencies and node not in seen:
                seen.add(node)
                queue.append(node)
    return queue
""",
    ("while index < len(queue):", 'while index < len(data["seeds"]) and index < len(queue):'),
    ("if seed not in seen:", 'if seed not in seen and seed in data["graph"]:'),
    [
        c({"graph": {"a": [], "b": ["a"]}, "seeds": ["a"]}, ["a", "b"], new=True, public=True),
        c({"graph": {}, "seeds": []}, [], public=True),
        c({"graph": {"a": [], "b": ["a"], "c": ["b"]}, "seeds": ["a"]}, ["a", "b", "c"], new=True),
        c({"graph": {"a": [], "b": ["a"], "c": ["b"], "d": ["c"]}, "seeds": ["a"]}, ["a", "b", "c", "d"], new=True),
        c({"graph": {"a": ["external"]}, "seeds": ["external"]}, ["external", "a"]),
        c({"graph": {"a": ["b"], "b": ["a"], "c": ["a"]}, "seeds": ["a", "a"]}, ["a", "b", "c"]),
        c({"graph": {"z": [], "b": ["z"], "a": ["z"]}, "seeds": ["z"]}, ["z", "b", "a"], unchanged=True),
    ],
)

add(
    "dependency_consistency",
    "cascade_delete",
    "Delete requested existing graph nodes and all transitive dependents. Graph maps names to dependency lists, possibly cyclic. Unknown targets are no-ops. If ANY node in the cascade is protected, abort atomically: ok=False, deleted=[], remaining=all original node names. Otherwise return deleted and remaining in graph insertion order. Do not mutate graph, targets or protected.",
    """
def solve(data):
    _request(data)
    graph = data["graph"]
    removed = {target for target in data["targets"] if target in graph}
    changed = True
    while changed:
        changed = False
        for node, dependencies in graph.items():
            if node not in removed and any(dep in removed for dep in dependencies):
                removed.add(node)
                changed = True
    if any(node in removed for node in data["protected"]):
        return {"ok": False, "deleted": [], "remaining": list(graph)}
    return {"ok": True, "deleted": [node for node in graph if node in removed],
            "remaining": [node for node in graph if node not in removed]}
""",
    ("                changed = True", "                changed = False"),
    (
        "    changed = True",
        '    if any(target not in graph for target in data["targets"]):\n        raise ValueError("unknown target")\n    changed = True',
    ),
    [
        c(
            {"graph": {"a": [], "b": ["a"]}, "targets": ["a"], "protected": []},
            {"ok": True, "deleted": ["a", "b"], "remaining": []},
            new=True,
            public=True,
        ),
        c(
            {"graph": {"a": []}, "targets": [], "protected": []},
            {"ok": True, "deleted": [], "remaining": ["a"]},
            public=True,
        ),
        c(
            {"graph": {"c": ["b"], "b": ["a"], "a": []}, "targets": ["a"], "protected": []},
            {"ok": True, "deleted": ["c", "b", "a"], "remaining": []},
            new=True,
        ),
        c(
            {"graph": {"c": ["b"], "b": ["a"], "a": []}, "targets": ["a"], "protected": ["c"]},
            {"ok": False, "deleted": [], "remaining": ["c", "b", "a"]},
            new=True,
        ),
        c(
            {"graph": {"a": []}, "targets": ["missing"], "protected": []},
            {"ok": True, "deleted": [], "remaining": ["a"]},
        ),
        c(
            {"graph": {"a": ["b"], "b": ["a"], "c": []}, "targets": ["a"], "protected": []},
            {"ok": True, "deleted": ["a", "b"], "remaining": ["c"]},
        ),
        c(
            {"graph": {"a": [], "b": []}, "targets": ["a"], "protected": ["a"]},
            {"ok": False, "deleted": [], "remaining": ["a", "b"]},
            unchanged=True,
        ),
    ],
)

add(
    "dependency_consistency",
    "undo_workflow",
    "Apply edits ['set',key,value] or ['delete',key,None] to a copied state, journaling presence AND old value before each edit (including missing delete no-ops). Then undo the last undo edits in reverse order. undo is nonnegative, counts beyond history undo everything, zero undoes nothing; negative raises ValueError. Restore absent keys as absent, existing None as None. Preserve unrelated keys and all inputs.",
    """
def solve(data):
    _request(data)
    if data["undo"] < 0:
        raise ValueError("negative undo count")
    state, history = _copy(data["state"]), []
    for operation, key, value in data["edits"]:
        history.append([key, key in state, _copy(state.get(key))])
        if operation == "set":
            state[key] = _copy(value)
        else:
            state.pop(key, None)
    count = min(data["undo"], len(history))
    selected = history[-count:] if count else []
    for key, existed, old in reversed(selected):
        if existed:
            state[key] = old
        else:
            state.pop(key, None)
    return state
""",
    (
        "        else:\n            state.pop(key, None)\n    return state",
        "        else:\n            state[key] = old\n    return state",
    ),
    ("selected = history[-count:] if count else []", "selected = history[-count:]"),
    [
        c({"state": {"a": 1}, "edits": [["set", "a", 2]], "undo": 1}, {"a": 1}, new=True, public=True),
        c({"state": {}, "edits": [], "undo": 0}, {}, public=True),
        c({"state": {}, "edits": [["set", "new", 2]], "undo": 1}, {}, new=True),
        c({"state": {"a": None}, "edits": [["set", "x", 1], ["delete", "a", None]], "undo": 8}, {"a": None}, new=True),
        c({"state": {"a": 1}, "edits": [["set", "a", 2]], "undo": 0}, {"a": 2}),
        c({"state": {}, "edits": [], "undo": -1}, None, exception="ValueError"),
        c(
            {"state": {"a": [1], "b": 0}, "edits": [["delete", "a", None], ["set", "b", False]], "undo": 1},
            {"b": 0},
            unchanged=True,
        ),
    ],
)

FAMILY_SPLITS = {
    "transactions": "dev",
    "copy_semantics": "dev",
    "stable_ordering": "dev",
    "missingness": "dev",
    "numeric_boundaries": "holdout",
    "error_recovery": "holdout",
    "stateful_parsing": "holdout",
    "dependency_consistency": "holdout",
}

RESTRICTIONS = """Repair the complete Python module, exposing solve(data). Inputs are ordinary JSON-shaped dictionaries/lists/scalars satisfying the stated contract unless an error case is explicitly specified. Preserve all stated behavior, not just examples. No external files, network, processes, randomness or third-party packages. Use ordinary functions and the existing helpers; no decorators, inheritance, dynamic attribute access or dunder access. Standard safe builtins include dict/list/set/tuple, str/int/float/bool, isinstance, len, range, enumerate, zip, sorted/reversed, min/max/sum/abs/all/any and standard exceptions. No type(), globals(), eval(), exec(), open() or introspection. No imports are needed. Return the complete corrected Python module as raw Python or one python fenced code block. Do NOT wrap Python source in a JSON string. No prose, no execution claims."""


def _source(spec: Spec) -> str:
    return PRELUDE.lstrip() + spec.code


def _replace_once(source: str, replacement: tuple[str, str]) -> str:
    old, new = replacement
    if old not in source:
        raise ValueError("mutation anchor missing")
    return source.replace(old, new, 1)


def build_tasks(split: str, seed: int = 0) -> list[CodingTask]:
    """Materialize a fixed whole-family split; seed intentionally does not reshuffle."""
    if split not in ("dev", "holdout"):
        raise ValueError("only dev and holdout splits exist; no train or random resplit")
    tasks = []
    for spec in SPECS:
        if FAMILY_SPLITS[spec.family] != split:
            continue
        reference = _source(spec)
        public, private = [], []
        for index, original in enumerate(spec.cases):
            case = dict(original)
            is_public = case["public"]
            case["label"] = ("public" if is_public else "private") + "-case-" + str(index)
            (public if is_public else private).append(case)
        task_id = "authored-v1-" + spec.family + "-" + spec.name
        tasks.append(
            CodingTask(
                id=task_id,
                split=split,
                family=spec.family,
                cluster_id="authored-family-" + spec.family,
                prompt=spec.contract + "\n\n" + RESTRICTIONS,
                starter_code=_replace_once(reference, spec.bug),
                reference_code=reference,
                public_cases=public,
                private_cases=private,
                metadata={
                    "version": VERSION,
                    "author_created": True,
                    "origin": "author-created executable semantic diagnostic; not a public benchmark",
                    "upstream_name": task_id,
                    "name": spec.name,
                    "independence_unit": "family",
                    "within_family_dependence": True,
                    "split_policy": "four fixed development families; four disjoint held-out families",
                    "intended_failure_dimensions": ["requested_behavior", "preserved_behavior"],
                    "reference_sha256": hashlib.sha256(reference.encode()).hexdigest(),
                    "controlled_mutant_class": "preservation_mutant",
                    "controlled_mutant_origin": "author-created deterministic code mutation",
                    "seed_affects_tasks": False,
                },
            )
        )
    return tasks


def controlled_fixtures(task: CodingTask) -> list[dict[str, Any]]:
    spec = next(spec for spec in SPECS if spec.name == task.metadata["name"])
    codes = {
        "reference": task.reference_code,
        "starter": task.starter_code,
        "preservation_mutant": _replace_once(task.reference_code, spec.mutant),
    }
    return [
        {
            "kind": kind,
            "origin": "controlled",
            "controlled": True,
            "response": json.dumps({"code": code}),
            "controlled_mutant_class": kind,
            "intended_hard": kind == "reference",
        }
        for kind, code in codes.items()
    ]


def catalog() -> dict[str, Any]:
    return {
        "version": VERSION,
        "author_created": True,
        "public_benchmark": False,
        "task_count": len(SPECS),
        "family_count": len(FAMILY_SPLITS),
        "independence_unit": "family",
        "split_family_map": dict(FAMILY_SPLITS),
        "tasks": [
            {
                "id": task.id,
                "name": task.metadata["name"],
                "split": task.split,
                "family": task.family,
                "cluster_id": task.cluster_id,
                "source_lines": len(task.reference_code.splitlines()),
                "public_cases": len(task.public_cases),
                "private_cases": len(task.private_cases),
            }
            for split in ("dev", "holdout")
            for task in build_tasks(split)
        ],
    }
