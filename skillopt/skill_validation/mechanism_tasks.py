"""Deterministic, pre-solver Coding panels for input/state preservation.

The host chooses from a finite declarative catalog; a language-model task
teacher is not a prerequisite. Related families reuse curriculum_tasks and its
isolated qualification. Twelve separate algorithm contracts supply six
unrelated controls per partition. These are synthetic Coding tasks, not new
domains, certified independent semantic families, or a calibrated verifier.
Only trusted finite oracle functions run on the host. Reference and candidate
Python strings are passed to the existing isolated executor, never eval/exec.
"""
from __future__ import annotations

import itertools
import json
import math
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

from . import curriculum_tasks as curriculum
from .checks import CallableTask, PublicCase
from .models import ArtifactRecord, Obligation, TaskContract, require
from .views import bind

VERSION = "deterministic-mechanism-panel-v2"
ORIGIN = "host_deterministic_synthetic_catalog"
REGIONS = {"preserve": "target_related", "inplace": "near_miss", "unconstrained": "boundary_control"}
UNRELATED = (
    "balanced_parentheses", "run_length_encoding", "wildcard_matching", "key_value_parsing",
    "directed_reachability", "undirected_components", "directed_cycle",
    "coprime_integers", "prime_integer", "binary_addition", "base_conversion", "interval_union",
)
LIMITATIONS = [
    "Synthetic Coding only; no cross-domain claim and no automatic deployment authorization.",
    "Role variants and repeats are clustered, not independent tasks.",
    "Role-observable finite-behavior exclusion is not certified full-domain equivalence or semantic family independence.",
    "Six unrelated algorithm families per partition do not establish statistical non-inferiority.",
    "Finite host oracles and agreeing reference implementations are not universal correctness proofs.",
    "Task engineering qualification is not Verifier Gate calibration.",
]


def _observable_signatures(inputs, observed):
    """Compare only each role's actual return/state obligations, not internals."""
    values = {
        "preserve": [[returned, before] for (returned, _), before in zip(observed, inputs)],
        "inplace": [[returned, transformed] for returned, transformed in observed],
        # Mutation is optional here: no single post-state is required by this
        # contract. Different internal transformations cannot distinguish two
        # otherwise equal unconstrained tasks (or two preserve tasks).
        "unconstrained": [returned for returned, _ in observed],
    }
    return {role: digest({"version": VERSION + "-role-observable", "role": role,
                          "inputs": inputs, "required_observations": required})
            for role, required in values.items()}


def role_behavior_fingerprints(spec):
    """Pre-solver finite signatures, not model outcomes or equivalence proofs.

    Same-role aliases are excluded both within and across partitions. Different
    roles deliberately remain paired conditions of one family; a preserve and
    an in-place obligation are not interchangeable just because returns agree.
    """
    spec = curriculum._spec(spec)
    inputs = curriculum._audit_inputs()
    return _observable_signatures(inputs, [curriculum._evaluate(spec, values) for values in inputs])


@lru_cache(maxsize=1)
def _catalog():
    """Immutable JSON entries; selection never reads solver outcomes."""
    steps = [{"op": op, "kind": kind} for op, kinds in curriculum.OPERATIONS.items() for kind in kinds]
    combinations = list(itertools.permutations(steps, 2))
    combinations += [(a, b, c) for a in steps for b in steps for c in steps
                     if a["op"] == "filter" and b["op"] == "map" and c["op"] == "reorder"]
    specs = {}
    for sequence in combinations:
        for aggregate in curriculum.AGGREGATES:
            spec = {"steps": list(sequence), "aggregate": aggregate}
            try:
                fingerprint = curriculum.family_fingerprint(spec)
            except ValueError:
                continue
            specs[fingerprint] = spec
    selected, behaviors = [], set()
    role_behaviors = {role: set() for role in REGIONS}
    inputs = curriculum._audit_inputs()
    for fingerprint, spec in sorted(specs.items()):
        observed = [curriculum._evaluate(spec, values) for values in inputs]
        if len({v[0] for v in observed}) < 2 or all(v[1] == values for v, values in zip(observed, inputs)):
            continue  # Pre-solver oracle degeneracy, not model-performance selection.
        behavior = curriculum.behavior_fingerprint(spec)
        role_signatures = _observable_signatures(inputs, observed)
        if behavior not in behaviors and all(signature not in role_behaviors[role]
                                            for role, signature in role_signatures.items()):
            behaviors.add(behavior)
            for role, signature in role_signatures.items():
                role_behaviors[role].add(signature)
            selected.append((fingerprint, behavior, json.dumps(spec, sort_keys=True)))
    return tuple(selected)


def _related(spec, partition):
    return [{**row, "family_origin": ORIGIN, "task_kind": "list_pipeline",
             "region": REGIONS[row["host_only"]["role"]], "family_id": row["task"].contract.family_id}
            for row in curriculum.compile_family(spec, partition)]


def _closure(n, edges, *, undirected=False, reflexive=False):
    connected = [[reflexive and a == b for b in range(n)] for a in range(n)]
    for a, b in edges:
        connected[a][b] = True
        if undirected:
            connected[b][a] = True
    for mid in range(n):
        for a in range(n):
            for b in range(n):
                connected[a][b] = connected[a][b] or (connected[a][mid] and connected[mid][b])
    return connected


def _oracle(name, args):
    """Trusted functions over host-owned finite inputs; no submitted source."""
    if name == "balanced_parentheses":
        total = 0
        for char in args[0]:
            total += 1 if char == "(" else -1
            if total < 0:
                return False
        return total == 0
    if name == "run_length_encoding":
        return [[char, len(tuple(group))] for char, group in itertools.groupby(args[0])]
    if name == "wildcard_matching":
        text, pattern = args
        @lru_cache(maxsize=None)
        def match(i, j):
            if j == len(pattern):
                return i == len(text)
            if pattern[j] == "*":
                return match(i, j + 1) or (i < len(text) and match(i + 1, j))
            return i < len(text) and pattern[j] in ("?", text[i]) and match(i + 1, j + 1)
        return match(0, 0)
    if name == "key_value_parsing":
        return {part[0]: int(part[2]) for part in args[0].split(";")} if args[0] else {}
    if name == "directed_reachability":
        n, edges, source, target = args
        return _closure(n, edges, reflexive=True)[source][target]
    if name == "undirected_components":
        n, edges = args
        reach = _closure(n, edges, undirected=True, reflexive=True)
        return len({tuple(row) for row in reach})
    if name == "directed_cycle":
        n, edges = args
        reach = _closure(n, edges)
        return any(reach[i][i] for i in range(n))
    if name == "coprime_integers":
        return math.gcd(*args) == 1
    if name == "prime_integer":
        n = args[0]
        return n >= 2 and all(n % d for d in range(2, math.isqrt(max(n, 0)) + 1))
    if name == "binary_addition":
        return bin(int(args[0], 2) + int(args[1], 2))[2:]
    if name == "base_conversion":
        n, base = args
        digits = []
        while n:
            n, digit = divmod(n, base)
            digits.append(str(digit))
        return "".join(reversed(digits)) or "0"
    require(name == "interval_union", "Unknown host oracle")
    # Half-integer lattice encodes closed intervals with integer endpoints.
    # Unlike the submitted/reference sort-and-merge algorithm, gaps remain gaps.
    points = sorted({point for lo, hi in args[0] for point in range(2 * lo, 2 * hi + 1)})
    result = []
    for _, group in itertools.groupby(enumerate(points), lambda item: item[1] - item[0]):
        values = [v for _, v in group]
        result.append([values[0] // 2, values[-1] // 2])
    return result


def _words(alphabet, maximum):
    return ["".join(chars) for length in range(maximum + 1) for chars in itertools.product(alphabet, repeat=length)]


def _inputs(name):
    if name == "balanced_parentheses":
        return [[value] for value in _words("()", 8)]
    if name == "run_length_encoding":
        return [[value] for value in _words("abc", 4) + ["a" * 8, "ab" * 4, "aabccbaa"]]
    if name == "wildcard_matching":
        return [[text, pattern] for text in _words("ab", 3) for pattern in _words("ab?*", 2)] + [
            ["ababab", "a*b"], ["", "***"], ["aaab", "a??*b"], ["abab", "*a*b*"]]
    if name == "key_value_parsing":
        tokens = [key + "=" + str(value) for key in "ab" for value in range(3)]
        return [[";".join(parts)] for length in range(4) for parts in itertools.product(tokens, repeat=length)] + [
            ["c=9;a=0;c=1;b=2"], ["a=9;a=9;a=0;a=1"]]
    if name in {"directed_reachability", "directed_cycle", "undirected_components"}:
        possible = [(a, b) for a in range(3) for b in range(3)
                    if a != b and (name != "undirected_components" or a < b)]
        graphs = [[list(edge) for i, edge in enumerate(possible) if mask & (1 << i)]
                  for mask in range(2 ** len(possible))]
        if name == "directed_reachability":
            return [[3, edges, a, b] for edges in graphs for a in range(3) for b in range(3)] + [
                [1, [], 0, 0], [2, [[0, 0]], 0, 1], [4, [[0, 1], [1, 2], [2, 3]], 0, 3]]
        return [[3, edges] for edges in graphs] + [[1, []], [1, [[0, 0]]], [4, []],
            [4, [[0, 1], [1, 2], [2, 3]]], [4, [[0, 1], [1, 2], [2, 0], [3, 3]]]]
    if name == "coprime_integers":
        return [[a, b] for a in range(-12, 13) for b in range(-12, 13)]
    if name == "prime_integer":
        return [[n] for n in range(-3, 64)]
    if name == "binary_addition":
        return [[bin(a)[2:], bin(b)[2:]] for a in range(16) for b in range(16)]
    if name == "base_conversion":
        return [[n, base] for n in range(64) for base in range(2, 9)] + [[255, 2], [255, 7], [255, 8]]
    intervals = [[lo, hi] for lo in range(-3, 4) for hi in range(lo, 4)]
    return [[[]]] + [[[interval]] for interval in intervals] + [
        [[a, b]] for a, b in itertools.combinations_with_replacement(intervals, 2)] + [
        [[[2, 3], [-3, -1], [-1, 2]]], [[[1, 1], [0, 0]]]]


_DESCRIPTIONS = {
    "balanced_parentheses": "Implement solve(text). text contains only '(' and ')' and has length 0..8. Return bool: whether every opening parenthesis is closed in the correct order. Empty text is balanced.",
    "run_length_encoding": "Implement solve(text). text uses alphabet abc and has length 0..8. Return a list of [character, positive integer run_length] lists for maximal consecutive runs, in encounter order. Empty text returns [].",
    "wildcard_matching": "Implement solve(text, pattern). text uses alphabet ab; pattern uses alphabet ab?*. Each length is 0..6. Return bool for a match of the WHOLE text. '?' matches exactly one character; '*' matches any number including zero. Other characters are literal.",
    "key_value_parsing": "Implement solve(text). text is empty or 1..4 tokens separated by ';'. Each token is a single key a/b/c, '=', and a single decimal digit 0..9. Return a dict mapping keys to int values; the LAST occurrence of a key wins. Empty text returns {}. All inputs follow this grammar.",
    "directed_reachability": "Implement solve(n, edges, source, target). n is 1..4. edges is a list of up to 8 directed [u,v] pairs with vertices 0..n-1; loops and repeated edges are permitted. source/target are valid vertices. Return bool: a directed path exists from source to target. A zero-edge path counts when source equals target.",
    "undirected_components": "Implement solve(n, edges). n is 1..4. edges is a list of up to 8 undirected [u,v] pairs with vertices 0..n-1; loops and repeated edges are permitted. Return int: number of connected components, including isolated vertices. Return int, not bool.",
    "directed_cycle": "Implement solve(n, edges). n is 1..4. edges is a list of up to 8 directed [u,v] pairs with vertices 0..n-1; loops and repeated edges are permitted. Return bool: the graph has a directed cycle of positive length. A self-loop is a cycle; a zero-edge path is not.",
    "coprime_integers": "Implement solve(a, b). a and b are integers in [-12,12], not bool. Return bool: gcd(abs(a),abs(b)) equals 1. gcd(0,0) is defined as 0.",
    "prime_integer": "Implement solve(n). n is an integer in [-3,63], not bool. Return bool: n is prime (at least 2 with no positive divisors other than 1 and itself).",
    "binary_addition": "Implement solve(a, b). a,b are canonical unsigned binary strings representing integers 0..15; '0' is the only zero representation, no leading zeros otherwise. Return their sum as a canonical unsigned binary string, without a prefix.",
    "base_conversion": "Implement solve(n, base). n is an integer in [0,255], base an integer in [2,8], neither bool. Return n in that base as a digit string, with no prefix or leading zeros, except zero is '0'.",
    "interval_union": "Implement solve(intervals). intervals contains 0..4 closed intervals [lo,hi] with integer endpoints -3<=lo<=hi<=3. Return a list of lists representing the union as sorted disjoint closed intervals. Merge overlapping intervals and intervals touching at the same endpoint; [0,0] and [1,1] do NOT touch. Return [] for empty input.",
}


def _references(name):
    # Registered host templates only. Never execute these strings on the host.
    return {
        "balanced_parentheses": (
            "def solve(text):\n    count = 0\n    for ch in text:\n        count += 1 if ch == '(' else -1\n        if count < 0: return False\n    return count == 0\n",
            "def solve(text):\n    while '()' in text: text = text.replace('()', '')\n    return text == ''\n"),
        "run_length_encoding": (
            "from itertools import groupby\ndef solve(text):\n    return [[c, sum(1 for _ in g)] for c, g in groupby(text)]\n",
            "def solve(text):\n    out = []\n    for c in text:\n        if out and out[-1][0] == c: out[-1][1] += 1\n        else: out.append([c, 1])\n    return out\n"),
        "wildcard_matching": (
            "from fnmatch import fnmatchcase\ndef solve(text, pattern):\n    return fnmatchcase(text, pattern)\n",
            "def solve(text, pattern):\n    row = [True] + [False] * len(text)\n    for p in pattern:\n        nxt = [row[0] and p == '*'] + [False] * len(text)\n        for i, ch in enumerate(text, 1):\n            nxt[i] = (row[i] or nxt[i-1]) if p == '*' else row[i-1] and p in ('?', ch)\n        row = nxt\n    return row[-1]\n"),
        "key_value_parsing": (
            "def solve(text):\n    if not text: return {}\n    return {p.split('=')[0]: int(p.split('=')[1]) for p in text.split(';')}\n",
            "def solve(text):\n    result = {}\n    for index in range(0, len(text), 4): result[text[index]] = ord(text[index+2]) - ord('0')\n    return result\n"),
        "directed_reachability": (
            "def solve(n, edges, source, target):\n    seen, todo = set(), [source]\n    while todo:\n        v = todo.pop()\n        if v == target: return True\n        if v in seen: continue\n        seen.add(v)\n        todo.extend(b for a,b in edges if a == v)\n    return False\n",
            "def solve(n, edges, source, target):\n    reached = {source}\n    for _ in range(n): reached |= {b for a,b in edges if a in reached}\n    return target in reached\n"),
        "undirected_components": (
            "def solve(n, edges):\n    groups = [{i} for i in range(n)]\n    for a,b in edges:\n        left = next(g for g in groups if a in g)\n        right = next(g for g in groups if b in g)\n        if left is not right: left.update(right); groups.remove(right)\n    return len(groups)\n",
            "def solve(n, edges):\n    unseen, count = set(range(n)), 0\n    while unseen:\n        todo = [unseen.pop()]\n        count += 1\n        while todo:\n            v = todo.pop()\n            neighbors = {b for a,b in edges if a == v} | {a for a,b in edges if b == v}\n            found = neighbors & unseen\n            unseen -= found\n            todo.extend(found)\n    return count\n"),
        "directed_cycle": (
            "def solve(n, edges):\n    edges = set(map(tuple, edges))\n    indeg = [sum(b == v for a,b in edges) for v in range(n)]\n    todo, visited = [v for v in range(n) if not indeg[v]], 0\n    while todo:\n        v = todo.pop(); visited += 1\n        for a,b in edges:\n            if a == v:\n                indeg[b] -= 1\n                if not indeg[b]: todo.append(b)\n    return visited != n\n",
            "def solve(n, edges):\n    color = [0] * n\n    def visit(v):\n        if color[v] == 1: return True\n        if color[v] == 2: return False\n        color[v] = 1\n        if any(visit(b) for a,b in edges if a == v): return True\n        color[v] = 2\n        return False\n    return any(visit(v) for v in range(n))\n"),
        "coprime_integers": (
            "from math import gcd\ndef solve(a, b):\n    return gcd(a, b) == 1\n",
            "def solve(a, b):\n    a,b = abs(a),abs(b)\n    while b: a,b = b,a%b\n    return a == 1\n"),
        "prime_integer": (
            "from math import isqrt\ndef solve(n):\n    return n >= 2 and all(n%d != 0 for d in range(2, isqrt(max(n,0))+1))\n",
            "def solve(n):\n    if n < 2: return False\n    return sum(n%d == 0 for d in range(1,n+1)) == 2\n"),
        "binary_addition": (
            "def solve(a, b):\n    return format(int(a,2)+int(b,2), 'b')\n",
            "def solve(a, b):\n    out, carry, i, j = [], 0, len(a)-1, len(b)-1\n    while i >= 0 or j >= 0 or carry:\n        v = carry + (int(a[i]) if i>=0 else 0) + (int(b[j]) if j>=0 else 0)\n        out.append(str(v%2)); carry = v//2; i -= 1; j -= 1\n    return ''.join(reversed(out)).lstrip('0') or '0'\n"),
        "base_conversion": (
            "def solve(n, base):\n    out = ''\n    while n:\n        n,r = divmod(n, base); out = str(r)+out\n    return out or '0'\n",
            "def solve(n, base):\n    if n < base: return str(n)\n    return solve(n//base, base) + str(n%base)\n"),
        "interval_union": (
            "def solve(intervals):\n    out = []\n    for lo,hi in sorted(intervals):\n        if out and lo <= out[-1][1]: out[-1][1] = max(out[-1][1],hi)\n        else: out.append([lo,hi])\n    return out\n",
            "def solve(intervals):\n    pending, out = [list(v) for v in intervals], []\n    while pending:\n        lo,hi = pending.pop()\n        changed = True\n        while changed:\n            changed = False\n            for i,(a,b) in enumerate(pending):\n                if a <= hi and lo <= b:\n                    lo,hi = min(lo,a),max(hi,b); pending.pop(i); changed = True; break\n        out.append([lo,hi])\n    return sorted(out)\n"),
    }[name]


def _runner(cases, *, audit):
    source = ("import importlib\nfrom copy import deepcopy\nCASES = " + repr(cases) + "\n"
        "def equal(a, b):\n    if type(a) is not type(b): return False\n"
        "    if isinstance(b, list): return len(a) == len(b) and all(equal(x,y) for x,y in zip(a,b))\n"
        "    if isinstance(b, dict): return a.keys() == b.keys() and all(equal(a[k],b[k]) for k in b)\n"
        "    return a == b\n"
        "def outcomes():\n    candidate = importlib.import_module('solution').solve\n    rows = []\n"
        "    for case in CASES:\n        try:\n            value = candidate(*deepcopy(case['args']))\n"
        "            passed, error = equal(value,case['expected']), None\n"
        "        except (MemoryError, TimeoutError):\n            raise\n"
        "        except Exception as exc:\n            passed, error = False, type(exc).__name__\n"
        "        rows.append({'return_pass': passed, 'state_pass': True, 'exception': error})\n"
        "    return rows\n")
    return source + ("def audit():\n    return {'cases': outcomes()}\n" if audit else
                     "def check():\n    return all(row['return_pass'] for row in outcomes())\n")


@lru_cache(maxsize=24)
def _unrelated_json(name, partition):
    require(name in UNRELATED and partition in {"development", "skill_confirmation"}, "Unknown unrelated task/partition")
    cases = [{"args": args, "expected": _oracle(name, args)} for args in _inputs(name)]
    require(len({digest(c["args"]) for c in cases}) == len(cases), "Duplicate host audit input")
    require(len({digest(c["expected"]) for c in cases}) > 1, "Unrelated oracle is degenerate")
    # Public examples fixed by input index, never by model success/failure.
    public = [cases[i] for i in sorted({0, len(cases) // 3, 2 * len(cases) // 3, len(cases) - 1})]
    prompt = _DESCRIPTIONS[name] + "\nPublic examples: " + json.dumps(public, sort_keys=True)
    family = "synthetic-unrelated-" + name
    contract = TaskContract(family, family, family, "synthetic-unrelated-coding-catalog", partition,
        "coding", "independent_algorithm_control", prompt,
        (Obligation("requested_behavior", "requested_behavior", _DESCRIPTIONS[name], _DESCRIPTIONS[name]),))
    task = CallableTask(contract, "solution", "solve", tuple(PublicCase("example-" + str(i),
        json.dumps({"args": c["args"], "kwargs": {}}), prompt, ("requested_behavior",),
        json.dumps(c["expected"])) for i, c in enumerate(public)))
    public_task = CallableTask(contract, "public_runner", "check", (PublicCase("all-public-checks",
        '{"args":[],"kwargs":{}}', prompt, ("requested_behavior",), "true"),))
    a, b = _references(name)
    row = {"task": task.to_dict(), "public_task": public_task.to_dict(),
        "public_wrapper": {"path": "public_runner.py", "content": _runner(public, audit=False)},
        "host_only": {"catalog_id": name, "reference_a": a, "reference_b": b,
            "audit_inputs": [c["args"] for c in cases], "audit_cases": cases,
            "audit_runner": _runner(cases, audit=True), "family_fingerprint": digest({"version": VERSION, "name": name}),
            "no_state_preservation_requirement": True, "semantic_family_independence_certified": False},
        "task_kind": "unrelated", "family_origin": ORIGIN, "region": "unrelated", "family_id": family}
    return json.dumps(row, sort_keys=True)


def _unrelated(name, partition):
    value = json.loads(_unrelated_json(name, partition))
    for key in ("task", "public_task"):
        value[key] = CallableTask.from_dict(value[key])
    return value


def serialize_row(row):
    return {**deepcopy({k: v for k, v in row.items() if k not in {"task", "public_task"}}),
            "task": row["task"].to_dict(), "public_task": row["public_task"].to_dict()}


def deserialize_row(value):
    require(type(value) is dict, "Serialized task row required")
    row = deepcopy(value)
    for name in ("task", "public_task"):
        row[name] = CallableTask.from_dict(row[name])
    return _validate_row(row)


def build_panel(seed, development_families=8, confirmation_families=24):
    require(type(seed) is int and 0 <= seed < 2**64, "Explicit bounded integer panel seed required")
    require(all(type(n) is int and 1 <= n <= 64 for n in (development_families, confirmation_families)),
            "Related family budgets must be 1..64")
    catalog = _catalog()
    ranked = sorted(catalog, key=lambda entry: digest([VERSION, seed, entry[0]]))
    require(len(ranked) >= development_families + confirmation_families, "Insufficient host-screened catalog; do not pad")
    # Confirmation reservation has priority; all selection precedes solver use.
    choices = {"confirmation": ranked[:confirmation_families],
               "development": ranked[confirmation_families:confirmation_families + development_families]}
    unrelated = sorted(UNRELATED, key=lambda name: digest([VERSION, seed, "unrelated", name]))
    selected_unrelated = {"confirmation": unrelated[:6], "development": unrelated[6:]}
    rows = {}
    for part, families in choices.items():
        partition = "skill_confirmation" if part == "confirmation" else "development"
        rows[part] = [row for _, _, raw in families for row in _related(json.loads(raw), partition)]
        rows[part] += [_unrelated(name, partition) for name in selected_unrelated[part]]
    manifest = seal({"version": VERSION, "seed": seed, "mechanism": "input_state_preservation",
        "selection": "deterministic_role_observable_catalog_before_solver_no_model_performance_filter",
        "alias_screen": "same_role_observable_finite_behavior_unique_within_and_across_partitions",
        "finite_alias_input_hash": digest(curriculum._audit_inputs()),
        "semantic_family_independence_certified": False,
        "development_related_families": development_families, "confirmation_related_families": confirmation_families,
        "catalog_entries": len(catalog), "catalog_hash": digest(catalog),
        "related": {part: [{"structural_hash": a, "finite_behavior_hash": b,
                            "role_behavior_hashes": role_behavior_fingerprints(json.loads(raw)), "spec": json.loads(raw)}
                            for a, b, raw in values] for part, values in choices.items()},
        "unrelated_catalog_ids": selected_unrelated,
        "row_hashes": {part: [digest(serialize_row(r)) for r in values] for part, values in rows.items()},
        "counts": {part: {"tasks": len(values), "related_structural_families": len(choices[part]),
                           "unrelated_algorithm_families": len(selected_unrelated[part]),
                           "regions": {region: sum(r["region"] == region for r in values)
                                       for region in (*REGIONS.values(), "unrelated")}}
                   for part, values in rows.items()},
        "source_type": ORIGIN, "all_tasks_frozen_before_solver": True,
        "statistical_noninferiority_established": False, "cross_domain_evaluated": False,
        "deployment_authorized": False, "limitations": LIMITATIONS})
    return {**rows, "manifest": manifest}


def _validate_row(row):
    require(type(row) is dict and row.get("family_origin") == ORIGIN, "Expected host-catalog row")
    require(type(row.get("task")) is CallableTask and type(row.get("public_task")) is CallableTask,
            "Typed callable tasks required")
    partition = row["task"].contract.partition
    require(partition in {"development", "skill_confirmation"}, "Unsupported mechanism panel partition")
    if row.get("task_kind") == "list_pipeline":
        expected = next((r for r in _related(row["host_only"]["spec"], partition)
                         if r["host_only"]["role"] == row["host_only"]["role"]), None)
    else:
        require(row.get("task_kind") == "unrelated", "Unknown host task adapter")
        expected = _unrelated(row["host_only"]["catalog_id"], partition)
    require(expected is not None and serialize_row(row) == serialize_row(expected), "Frozen host task changed")
    return row


def qualify_row(row, executor, root):
    _validate_row(row)
    root = Path(root)
    if row["task_kind"] == "list_pipeline":
        record = curriculum.screen_family(row["host_only"]["spec"], executor, root)
        return seal({**{k: v for k, v in record.items() if k != "record_hash"},
                     "evidence_origin": ORIGIN, "mechanism_panel_origin": ORIGIN,
                     "not_verifier_calibration": True, "family_id": row["family_id"]})
    host = row["host_only"]
    files = {"ref_a.py": host["reference_a"], "ref_b.py": host["reference_b"],
             "audit_check.py": host["audit_runner"], "public_check.py": row["public_wrapper"]["content"]}
    files["screen.py"] = (
        "import sys\nimport types\nimport ref_a\nimport ref_b\nimport audit_check\nimport public_check\n"
        "def screen():\n    good, public, comparisons = True, True, 0\n"
        "    for fn in (ref_a.solve, ref_b.solve):\n        sys.modules['solution'] = types.SimpleNamespace(solve=fn)\n"
        "        rows = audit_check.audit()['cases']\n        comparisons += len(rows)\n"
        "        good = good and all(r['return_pass'] for r in rows)\n        public = public and public_check.check()\n"
        "    sys.modules['solution'] = types.SimpleNamespace(solve=lambda *args: None)\n"
        "    wrong = audit_check.audit()['cases']\n"
        "    return {'references_pass': good, 'public_wrappers_pass': public,\n"
        "            'wrong_return_detected': all(not r['return_pass'] for r in wrong) and not public_check.check(),\n"
        "            'audit_cases': len(wrong), 'reference_case_comparisons': comparisons}\n")
    receipt = curriculum._execute(files, "screen", "screen", executor, root / "unrelated_screen",
                                  bindings={"family_id": row["family_id"], "row_hash": digest(serialize_row(row))})
    execution = receipt["execution"] or {}
    actual = execution.get("actual")
    flags = ("references_pass", "public_wrappers_pass", "wrong_return_detected")
    supported = execution.get("status") == "observed" and execution.get("exception") is None and type(actual) is dict
    supported = supported and all(type(actual.get(key)) is bool for key in flags)
    supported = supported and type(actual.get("audit_cases")) is int and actual["audit_cases"] == len(host["audit_cases"])
    supported = supported and type(actual.get("reference_case_comparisons")) is int and actual["reference_case_comparisons"] == 2 * len(host["audit_cases"])
    status = "unknown" if not supported else "qualified" if all(actual[key] for key in flags) else "rejected"
    return seal({"version": VERSION, "family_id": row["family_id"], "status": status, "receipt": receipt,
        "qualification": actual if supported else None, "formal_eligible": status == "qualified" and receipt["real_isolated_execution"],
        "evidence_origin": ORIGIN, "not_verifier_calibration": True, "deployment_authorized": False})


def qualify_panel(panel, executor, root):
    manifest = verify(panel["manifest"])
    expected = build_panel(manifest["seed"], manifest["development_related_families"], manifest["confirmation_related_families"])
    require(manifest == expected["manifest"], "Panel manifest differs from deterministic reservation")
    require(all([digest(serialize_row(r)) for r in panel[part]] == manifest["row_hashes"][part]
                for part in ("development", "confirmation")), "Panel rows differ from frozen reservation")
    unique = {r["family_id"]: r for part in ("development", "confirmation") for r in panel[part]}
    results = [qualify_row(row, executor, Path(root) / digest(family)) for family, row in sorted(unique.items())]
    formal = all(r["status"] == "qualified" and r["formal_eligible"] for r in results)
    status = "qualified" if formal else "rejected" if any(r["status"] == "rejected" for r in results) else "pending"
    return seal({"version": VERSION, "panel_hash": manifest["record_hash"], "status": status,
        "formal_eligible": formal, "families": len(results), "results": results,
        "not_verifier_calibration": True, "deployment_authorized": False, "limitations": LIMITATIONS})


def audit_row(row, artifact, executor, root):
    _validate_row(row)
    require(type(artifact) is ArtifactRecord, "Bound ArtifactRecord required")
    bind(row["task"].contract, artifact, ())
    if row["task_kind"] == "list_pipeline":
        return curriculum.audit_artifact({**row, "family_origin": curriculum.PROVENANCE}, artifact, executor, root)
    host = row["host_only"]
    code = next((f.content for f in artifact.files if f.path == "solution.py"), None)
    receipt = None
    if artifact.availability == "available" and code is not None:
        receipt = curriculum._execute({"solution.py": code, "hidden_audit.py": host["audit_runner"]},
            "hidden_audit", "audit", executor, Path(root) / "audit",
            bindings={"task_hash": row["task"].content_hash, "artifact_record_hash": artifact.content_hash})
    execution = receipt["execution"] if receipt and receipt["execution"] else {}
    actual = execution.get("actual")
    complete = execution.get("status") == "observed" and execution.get("exception") is None and type(actual) is dict
    complete = complete and type(actual.get("cases")) is list and len(actual["cases"]) == len(host["audit_cases"])
    complete = complete and all(type(case) is dict and type(case.get("return_pass")) is bool
                                and case.get("state_pass") is True for case in actual["cases"])
    status = "unknown" if not complete else "pass" if all(case["return_pass"] for case in actual["cases"]) else "fail"
    return seal({"version": VERSION, "task_hash": row["task"].content_hash, "artifact_hash": artifact.content_hash,
        "family_id": row["family_id"], "region": "unrelated", "status": status,
        "return_status": status, "state_status": "not_applicable", "receipt": receipt,
        "audit_inputs": deepcopy(host["audit_inputs"]), "audit_outcomes": actual["cases"] if complete else None,
        "information_origin": "host_only_synthetic_unrelated_audit",
        "real_isolated_execution": bool(receipt and receipt["real_isolated_execution"]), "deployment_authorized": False})
