"""New, hand-authored Coding families for V6 engineering experiments.

No historical task assets or recorded failures are imported. Families differ in
algorithms/contracts, not just constants. Their fixed expected values are literal
host fixtures, never outputs copied from candidate/reference execution. These
synthetic tasks are not a public benchmark or a claim of unseen model training.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from textwrap import dedent

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter

VERSION = "coevolution-v6-new-coding-families-v1"
_ENTRY = "import logic\n\ndef solve(data):\n    return logic.run(data)\n"
_INT = {"type": "integer", "minimum": -10000, "maximum": 10000}
_NAME = {"type": "string", "minLength": 1, "maxLength": 40}
_TEXT = {"type": "string", "maxLength": 120}
_NULL_INT = {"type": ["integer", "null"], "minimum": -10000, "maximum": 10000}


def _obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _array(items, maximum=16):
    return {"type": "array", "items": items, "maxItems": maximum}


def _source(value):
    return dedent(value).strip() + "\n"


def _change(source, old, new):
    if source.count(old) != 1:
        raise ValueError("A controlled defect must replace exactly one declared expression")
    return source.replace(old, new, 1)


def _task(name, split, contract, schema, reference, equivalent, semantic, mutation_when, public, private,
          *, mechanism="constraint_preservation", group="same_mechanism"):
    def files(source):
        return {"api.py": _ENTRY, "logic.py": source}

    ref = _source(reference)
    eq = _source(equivalent)
    bad = _source(semantic)
    mutated = _change(ref, "def run(data):", "def original_result(data):") + (
        "\ndef run(data):\n    result = original_result(data)\n"
        f"    if {mutation_when}:\n        data['v6_unrequested_marker'] = True\n    return result\n"
    )
    if len({ref, eq, bad, mutated}) != 4:
        raise ValueError("Each calibration control must have distinct code")

    def cases(values, visible):
        return [{"label": f"{name}-{'public' if visible else 'private'}-{i}", "input": deepcopy(value),
                 "expected": deepcopy(expected), "exception": None, "public": visible,
                 "dimension": dimension} for i, (value, expected, dimension) in enumerate(values)]

    change_scope = "full_replacement" if group == "near_miss" else (
        "new_implementation" if split == "final" and group == "unrelated" else (
            "partial_update" if split == "development" or split == "final" and group == "same_mechanism" else "read_only"
        )
    )
    obligations = ["Do not mutate the supplied input object or any nested value.", "Preserve the protected api.py entrypoint."]
    if name == "invoice-local-extension":
        obligations += ["Keep legacy subtotal and currency fields and their meaning.",
                        "The legacy operation must not acquire a due field."]
    public_contract = {"change_scope": change_scope, "preserve_obligations": obligations,
                       "supersedes_old_policy": change_scope == "full_replacement"}
    task = RepoTask(
        id=f"repo-v6-{name}", split=split, family=name, cluster_id=f"v6-family-{name}",
        prompt=contract + "\nPUBLIC CONTRACT: " + json.dumps(public_contract, sort_keys=True, ensure_ascii=False)
        + "\nINPUT IMMUTABILITY: Do not mutate the supplied input object or any nested value. "
        "Only logic.py may change; api.py is protected. Inputs obey input_domain. Return only the requested "
        "JSON-compatible value. No file, network, process, dynamic execution or undeclared imports.",
        files=files(bad), reference_files=files(ref), editable_paths=["logic.py"], input_domain=deepcopy(schema),
        public_cases=cases(public, True), private_cases=cases(private, False),
        metadata={"version": VERSION, "domain": "coding", "evaluation_group": group, "mechanism": mechanism,
                  "public_contract": public_contract,
                  "origin": "new_hand_authored_v6_synthetic_engineering_not_public_benchmark",
                  "previous_experiment_assets_used": False,
                  "independence_unit": "structurally_distinct_algorithm_and_contract_family_not_fixture_or_parameter",
                  "oracle": "literal_manually_calculated_fixtures_crosschecked_in_tests",
                  "equivalent_kind": "separately_written_compliant_implementation_not_AST_rendering",
                  "input_preservation": "protected_entry_passes_original_input_directly_without_copy",
                  "controls": {"reference": files(ref), "equivalent": files(eq),
                               "semantic_mutant": files(bad), "preservation_mutant": files(mutated)}},
    )
    return CodingAdapter(task)


def calibration_tasks() -> list[CodingAdapter]:
    """Six structurally distinct, new promotion-only project families."""
    tasks = []
    ref = _source('''
        def run(data):
            initial = data['balance']
            balance = initial
            for index, delta in enumerate(data['deltas']):
                proposed = balance + delta
                if proposed < 0:
                    return {'balance': initial, 'committed': False, 'failed_index': index}
                balance = proposed
            return {'balance': balance, 'committed': True, 'failed_index': None}
    ''')
    tasks.append(_task(
        "atomic-batch-rollback", "promotion",
        "Apply signed deltas in order to a nonnegative initial balance. Commit the entire batch if every "
        "intermediate balance is nonnegative. On the first negative intermediate result, discard ALL prior "
        "changes: return the ORIGINAL balance, committed=false and the zero-based failing delta index. "
        "A successful (including empty) batch returns committed=true and failed_index=null.",
        _obj({"balance": {"type": "integer", "minimum": 0, "maximum": 1000}, "deltas": _array(_INT)}), ref,
        '''
        def run(data):
            values = [data['balance'] + sum(data['deltas'][:i + 1]) for i in range(len(data['deltas']))]
            failures = [i for i, value in enumerate(values) if value < 0]
            if failures:
                return {'balance': data['balance'], 'committed': False, 'failed_index': failures[0]}
            return {'balance': values[-1] if values else data['balance'], 'committed': True, 'failed_index': None}
        ''', _change(ref, "'balance': initial, 'committed': False", "'balance': balance, 'committed': False"),
        "len(data['deltas']) > 1",
        [({"balance": 4, "deltas": [3]}, {"balance": 7, "committed": True, "failed_index": None}, "requested_behavior"),
         ({"balance": 0, "deltas": []}, {"balance": 0, "committed": True, "failed_index": None}, "preserved_behavior")],
        [({"balance": 5, "deltas": [2, -9]}, {"balance": 5, "committed": False, "failed_index": 1}, "requested_behavior"),
         ({"balance": 3, "deltas": [-3, 1, -2]}, {"balance": 3, "committed": False, "failed_index": 2}, "requested_behavior"),
         ({"balance": 1, "deltas": [-1, 2]}, {"balance": 2, "committed": True, "failed_index": None}, "preserved_behavior")],
        mechanism="error_recovery"))

    ref = _source('''
        def run(data):
            dependencies = data['dependencies']
            remaining = set(dependencies)
            order = []
            while remaining:
                ready = [name for name in remaining if not any(dep in remaining for dep in dependencies[name])]
                if not ready:
                    break
                name = min(ready)
                order.append(name)
                remaining.remove(name)
            return {'order': order, 'blocked': sorted(remaining)}
    ''')
    tasks.append(_task(
        "priority-topological-readiness", "promotion",
        "dependencies maps task names to prerequisite names. Only map keys are scheduled; a prerequisite not "
        "present as a key is already satisfied. Repeatedly execute the lexicographically SMALLEST currently "
        "ready task, reconsidering readiness after EACH task. Cycles leave tasks blocked; return the executed "
        "order and sorted remaining blocked names. Duplicate prerequisites impose no extra requirements.",
        _obj({"dependencies": {"type": "object", "maxProperties": 8, "additionalProperties": _array(_NAME, 8)}}), ref,
        '''
        def run(data):
            pending = sorted(data['dependencies'])
            completed = []
            while pending:
                selected = None
                for name in pending:
                    if all(dep not in pending for dep in data['dependencies'][name]):
                        selected = name
                        break
                if selected is None:
                    return {'order': completed, 'blocked': pending}
                completed.append(selected)
                pending = [name for name in pending if name != selected]
            return {'order': completed, 'blocked': []}
        ''', _change(ref, "name = min(ready)", "name = max(ready)"), "len(data['dependencies']) > 2",
        [({"dependencies": {"x": []}}, {"order": ["x"], "blocked": []}, "requested_behavior"),
         ({"dependencies": {"a": ["b"], "b": []}}, {"order": ["b", "a"], "blocked": []}, "preserved_behavior")],
        [({"dependencies": {"c": [], "a": ["b"], "b": []}}, {"order": ["b", "a", "c"], "blocked": []}, "requested_behavior"),
         ({"dependencies": {"a": ["b"], "b": ["a"], "c": []}}, {"order": ["c"], "blocked": ["a", "b"]}, "preserved_behavior"),
         ({"dependencies": {"z": ["external"], "a": []}}, {"order": ["a", "z"], "blocked": []}, "requested_behavior")]))

    event = _obj({"kind": {"type": "string", "enum": ["set", "get"]}, "key": _NAME,
                  "time": {"type": "integer", "minimum": 0, "maximum": 1000}, "value": _INT,
                  "ttl": {"type": "integer", "minimum": 0, "maximum": 1000}})
    ref = _source('''
        def run(data):
            stored = {}
            answers = []
            for event in data['events']:
                key = event['key']
                if event['kind'] == 'set':
                    stored[key] = (event['value'], event['time'] + event['ttl'])
                else:
                    item = stored.get(key)
                    answers.append(item[0] if item is not None and event['time'] < item[1] else None)
            return answers
    ''')

    def ev(kind, key, time, value=0, ttl=0):
        return {"kind": kind, "key": key, "time": time, "value": value, "ttl": ttl}

    tasks.append(_task(
        "per-key-expiration", "promotion",
        "Process events in list order. A set replaces only that key with value and expires_at=time+ttl. "
        "A get appends the latest preceding value for its key only if get.time is STRICTLY LESS THAN expires_at; "
        "otherwise append null. A missing key returns null. Gets do not delete stored entries; event times may "
        "be nonmonotonic. Zero TTL is expired at its set time. value/ttl fields on get events are ignored.",
        _obj({"events": _array(event)}), ref,
        '''
        def run(data):
            previous_sets = []
            result = []
            for event in data['events']:
                if event['kind'] == 'set':
                    previous_sets.append(event)
                    continue
                latest = next((item for item in reversed(previous_sets) if item['key'] == event['key']), None)
                result.append(None if latest is None or event['time'] >= latest['time'] + latest['ttl'] else latest['value'])
            return result
        ''', _change(ref, "event['time'] < item[1]", "event['time'] <= item[1]"), "len(data['events']) > 2",
        [({"events": [ev("set", "a", 1, 7, 5), ev("get", "a", 3)]}, [7], "requested_behavior"),
         ({"events": [ev("get", "missing", 0)]}, [None], "preserved_behavior")],
        [({"events": [ev("set", "a", 1, 7, 2), ev("get", "a", 3), ev("get", "a", 2)]}, [None, 7], "requested_behavior"),
         ({"events": [ev("set", "a", 2, 8, 0), ev("get", "a", 2)]}, [None], "requested_behavior"),
         ({"events": [ev("set", "a", 0, 2, 8), ev("set", "b", 0, 9, 1), ev("get", "a", 2), ev("get", "b", 2)]}, [2, None], "preserved_behavior")],
        mechanism="evidence_verification"))

    ref = _source('''
        def run(data):
            lower = min(data['left'], data['right'])
            upper = max(data['left'], data['right'])
            return [min(upper, max(lower, value)) for value in data['values']]
    ''')
    tasks.append(_task(
        "signed-inclusive-clipping", "promotion",
        "Normalize unordered endpoints left/right into lower=min(left,right), upper=max(left,right). "
        "Clamp every SIGNED integer value into that closed interval, preserving order and multiplicity. "
        "Values already on either endpoint stay unchanged. An empty values list returns an empty list.",
        _obj({"left": _INT, "right": _INT, "values": _array(_INT)}), ref,
        '''
        def run(data):
            endpoints = sorted([data['left'], data['right']])
            output = []
            for value in data['values']:
                if value < endpoints[0]:
                    output.append(endpoints[0])
                elif value > endpoints[1]:
                    output.append(endpoints[1])
                else:
                    output.append(value)
            return output
        ''', _change(ref, "max(lower, value)", "max(lower, abs(value))"), "any(value < 0 for value in data['values'])",
        [({"left": 0, "right": 3, "values": [0, 2, 4]}, [0, 2, 3], "requested_behavior"),
         ({"left": 2, "right": 2, "values": []}, [], "preserved_behavior")],
        [({"left": -3, "right": 2, "values": [-4, -3, -2, 0, 3]}, [-3, -3, -2, 0, 2], "requested_behavior"),
         ({"left": 1, "right": -2, "values": [-3, -1, 2]}, [-2, -1, 1], "requested_behavior"),
         ({"left": -2, "right": -2, "values": [-9, 0, 9]}, [-2, -2, -2], "preserved_behavior")]))

    mapping = {"type": "object", "maxProperties": 12, "additionalProperties": _NULL_INT}
    ref = _source('''
        def run(data):
            result = dict(data['base'])
            for key, value in data['patch'].items():
                result[key] = value
            return result
    ''')
    tasks.append(_task(
        "missing-versus-null-merge", "promotion",
        "Return a shallow copy of base updated by every key PRESENT in patch. An explicitly present null "
        "is a real replacement value, NOT deletion and NOT absence. Keys missing from patch retain their "
        "old values. New patch keys are included. Neither base nor patch may be changed.",
        _obj({"base": mapping, "patch": mapping}), ref,
        '''
        def run(data):
            keys = set(data['base']) | set(data['patch'])
            return {key: data['patch'][key] if key in data['patch'] else data['base'][key] for key in keys}
        ''', _change(ref, "result[key] = value", "if value is not None:\n            result[key] = value"),
        "any(value is None for value in data['patch'].values())",
        [({"base": {"a": 1}, "patch": {"b": 2}}, {"a": 1, "b": 2}, "requested_behavior"),
         ({"base": {"a": None}, "patch": {}}, {"a": None}, "preserved_behavior")],
        [({"base": {"a": 1, "b": 2}, "patch": {"a": None}}, {"a": None, "b": 2}, "requested_behavior"),
         ({"base": {}, "patch": {"new": None}}, {"new": None}, "requested_behavior"),
         ({"base": {"a": 1, "b": None}, "patch": {"a": 0, "c": -2}}, {"a": 0, "b": None, "c": -2}, "preserved_behavior")]))

    records = _array(_obj({"id": _NAME, "score": _INT, "active": {"type": "boolean"}}))
    ref = _source('''
        def run(data):
            eligible = [(i, row) for i, row in enumerate(data['records']) if row['active']]
            eligible.sort(key=lambda item: (-item[1]['score'], item[0]))
            return [row['id'] for _, row in eligible[:data['limit']]]
    ''')
    tasks.append(_task(
        "stable-filtered-ranking", "promotion",
        "Ignore inactive records. Sort active records by score descending and, for equal scores, retain "
        "their ORIGINAL INPUT ORDER (not ID order). Return IDs of at most limit records. Duplicate IDs are "
        "allowed and not deduplicated. limit=0 returns []; negative scores are valid.",
        _obj({"records": records, "limit": {"type": "integer", "minimum": 0, "maximum": 16}}), ref,
        '''
        def run(data):
            pool = [row for row in data['records'] if row['active']]
            result = []
            while pool and len(result) < data['limit']:
                best = 0
                for index in range(1, len(pool)):
                    if pool[index]['score'] > pool[best]['score']:
                        best = index
                result.append(pool.pop(best)['id'])
            return result
        ''', _change(ref, "(-item[1]['score'], item[0])", "(-item[1]['score'], item[1]['id'])"),
        "len(data['records']) > 1",
        [({"records": [{"id": "x", "score": 4, "active": True}], "limit": 1}, ["x"], "requested_behavior"),
         ({"records": [], "limit": 3}, [], "preserved_behavior")],
        [({"records": [{"id": "z", "score": 5, "active": True}, {"id": "a", "score": 5, "active": True}], "limit": 2}, ["z", "a"], "requested_behavior"),
         ({"records": [{"id": "off", "score": 99, "active": False}, {"id": "n", "score": -2, "active": True}, {"id": "m", "score": -1, "active": True}], "limit": 1}, ["m"], "preserved_behavior"),
         ({"records": [{"id": "same", "score": 0, "active": True}, {"id": "same", "score": 0, "active": True}], "limit": 2}, ["same", "same"], "preserved_behavior")]))
    return tasks


def development_tasks() -> list[CodingAdapter]:
    """Three source families, disjoint from calibration and final identities."""
    tasks = []
    ref = _source('''
        def run(data):
            stream = data['stream']
            index = 0
            frames = []
            while index < len(stream):
                size = stream[index]
                if size < 0 or index + 1 + size > len(stream):
                    return {'frames': frames, 'error_index': index}
                frames.append(stream[index + 1:index + 1 + size])
                index += size + 1
            return {'frames': frames, 'error_index': None}
    ''')
    tasks.append(_task(
        "length-prefixed-frame-decoding", "development",
        "Decode stream as repeated [length, payload items...] frames. A zero length is a valid empty frame. "
        "A negative length or insufficient payload stops decoding and reports the zero-based LENGTH position "
        "as error_index; retain all earlier complete frames. Payload values may be negative. Successful empty "
        "or complete input has error_index=null.", _obj({"stream": _array(_INT, 24)}), ref,
        '''
        def run(data):
            rest = list(data['stream'])
            consumed = 0
            output = []
            while rest:
                size = rest.pop(0)
                if size < 0 or size > len(rest):
                    return {'frames': output, 'error_index': consumed}
                output.append(rest[:size])
                rest = rest[size:]
                consumed += 1 + size
            return {'frames': output, 'error_index': None}
        ''', _change(ref, "if size < 0 or", "if size <= 0 or"), "len(data['stream']) > 2",
        [({"stream": [2, 7, 8]}, {"frames": [[7, 8]], "error_index": None}, "requested_behavior"),
         ({"stream": []}, {"frames": [], "error_index": None}, "preserved_behavior")],
        [({"stream": [0, 1, -2]}, {"frames": [[], [-2]], "error_index": None}, "requested_behavior"),
         ({"stream": [1, 9, 3, 4]}, {"frames": [[9]], "error_index": 2}, "preserved_behavior"),
         ({"stream": [1, 2, -1]}, {"frames": [[2]], "error_index": 2}, "preserved_behavior")],
        mechanism="error_recovery"))

    interval = {"type": "array", "items": _INT, "minItems": 2, "maxItems": 2}
    ref = _source('''
        def run(data):
            intervals = sorted([sorted(pair) for pair in data['intervals']])
            result = []
            for left, right in intervals:
                if result and left <= result[-1][1]:
                    result[-1][1] = max(result[-1][1], right)
                else:
                    result.append([left, right])
            return result
    ''')
    tasks.append(_task(
        "closed-interval-union", "development",
        "Normalize each pair to a closed interval [min,max]. Return their union as sorted disjoint closed "
        "intervals; shared endpoints count as overlap. Retain isolated zero-width intervals. Normalize and "
        "merge copies, never the original nested lists.", _obj({"intervals": _array(interval)}), ref,
        '''
        def run(data):
            pending = [[min(pair), max(pair)] for pair in data['intervals']]
            output = []
            while pending:
                current = min(pending)
                pending.remove(current)
                changed = True
                while changed:
                    changed = False
                    for other in list(pending):
                        if other[0] <= current[1] and current[0] <= other[1]:
                            current = [min(current[0], other[0]), max(current[1], other[1])]
                            pending.remove(other)
                            changed = True
                output.append(current)
            return sorted(output)
        ''', _change(ref, "left <= result[-1][1]", "left < result[-1][1]"), "len(data['intervals']) > 1",
        [({"intervals": [[1, 4], [2, 6]]}, [[1, 6]], "requested_behavior"),
         ({"intervals": []}, [], "preserved_behavior")],
        [({"intervals": [[1, 2], [2, 3]]}, [[1, 3]], "requested_behavior"),
         ({"intervals": [[5, 3], [0, 0], [-1, -3]]}, [[-3, -1], [0, 0], [3, 5]], "preserved_behavior"),
         ({"intervals": [[4, 4], [1, 5], [5, 6]]}, [[1, 6]], "requested_behavior")]))

    ref = _source(r'''
        def run(data):
            encoded = []
            for token in data['tokens']:
                parts = []
                for character in token:
                    if character in ('\\', '|'):
                        parts.append('\\')
                    parts.append(character)
                encoded.append(''.join(parts))
            return '|'.join(encoded)
    ''')
    tasks.append(_task(
        "delimiter-preserving-escaping", "development",
        "Encode the token list by prefixing every literal backslash and every literal vertical bar in EACH "
        "token with one backslash, then join encoded tokens using one unescaped vertical bar. Preserve empty "
        "tokens and character order. Empty token list returns an empty string. This is escaping, not stripping.",
        _obj({"tokens": _array(_TEXT)}), ref,
        r'''
        def run(data):
            return '|'.join(token.replace('\\', '\\\\').replace('|', '\\|') for token in data['tokens'])
        ''', _change(ref, "if character in ('\\\\', '|'):", "if character == '|':"), "len(data['tokens']) > 1",
        [({"tokens": ["red", "blue"]}, "red|blue", "requested_behavior"),
         ({"tokens": []}, "", "preserved_behavior")],
        [({"tokens": ["a\\b"]}, "a\\\\b", "requested_behavior"),
         ({"tokens": ["|", "", "\\"]}, "\\|||\\\\", "requested_behavior"),
         ({"tokens": ["", "tail", ""]}, "|tail|", "preserved_behavior")]))
    return tasks


def _final_families() -> list[CodingAdapter]:
    """Three prospective final Coding categories; never optimizer feedback."""
    tasks = []
    ref = _source('''
        def run(data):
            subtotal = sum(item['quantity'] * item['price'] for item in data['items'])
            result = {'subtotal': subtotal, 'currency': data['currency']}
            if data['operation'] == 'discount':
                result['due'] = max(0, subtotal - data['discount'])
            return result
    ''')
    tasks.append(_task(
        "invoice-local-extension", "final",
        "Extend the invoice function with operation='discount': retain the legacy subtotal and currency fields "
        "and ADD due=max(0,subtotal-discount). For operation='legacy', return exactly subtotal and currency, "
        "without due. subtotal is the sum of integer quantity*price; items, prices, quantities and discount are "
        "nonnegative. Existing currency text must be unchanged.",
        _obj({"items": _array(_obj({"quantity": {"type": "integer", "minimum": 0, "maximum": 100},
                                   "price": {"type": "integer", "minimum": 0, "maximum": 1000}})),
              "currency": _NAME, "operation": {"type": "string", "enum": ["legacy", "discount"]},
              "discount": {"type": "integer", "minimum": 0, "maximum": 10000}}), ref,
        '''
        def run(data):
            amount = 0
            for item in data['items']:
                amount += item['price'] * item['quantity']
            if data['operation'] == 'legacy':
                return {'currency': data['currency'], 'subtotal': amount}
            return {'currency': data['currency'], 'subtotal': amount, 'due': amount - min(amount, data['discount'])}
        ''', _change(ref, "result['due'] = max(0, subtotal - data['discount'])", "result = {'due': max(0, subtotal - data['discount'])}"),
        "data['operation'] == 'discount'",
        [({"items": [{"quantity": 2, "price": 3}], "currency": "EUR", "operation": "legacy", "discount": 1},
          {"subtotal": 6, "currency": "EUR"}, "preserved_behavior")],
        [({"items": [{"quantity": 2, "price": 3}], "currency": "EUR", "operation": "discount", "discount": 1},
          {"subtotal": 6, "currency": "EUR", "due": 5}, "requested_behavior"),
         ({"items": [], "currency": "USD", "operation": "discount", "discount": 20},
          {"subtotal": 0, "currency": "USD", "due": 0}, "requested_behavior"),
         ({"items": [{"quantity": 0, "price": 99}], "currency": "JPY", "operation": "legacy", "discount": 9},
          {"subtotal": 0, "currency": "JPY"}, "preserved_behavior")], group="same_mechanism"))

    ref = _source('''
        def run(data):
            counts = {}
            for event in data['events']:
                counts[event['kind']] = counts.get(event['kind'], 0) + 1
            return {'counts': counts, 'total': len(data['events'])}
    ''')
    tasks.append(_task(
        "explicit-redacted-replacement", "final",
        "REPLACE the legacy event echo output, do not preserve its events/raw/detail fields. The new output "
        "must have EXACTLY counts (a mapping from kind to event count) and total (number of events). No raw "
        "event objects or detail values may appear anywhere in the output, even though the old implementation "
        "returned them. Kind labels are intentionally retained. Input data must still remain unchanged.",
        _obj({"events": _array(_obj({"kind": _NAME, "detail": _TEXT}))}), ref,
        '''
        def run(data):
            kinds = [event['kind'] for event in data['events']]
            return {'counts': {kind: kinds.count(kind) for kind in set(kinds)}, 'total': len(kinds)}
        ''', _change(ref, "return {'counts': counts, 'total': len(data['events'])}",
                    "result = {'counts': counts, 'total': len(data['events'])}\n    if data['events']:\n        result['events'] = data['events']\n    return result"),
        "bool(data['events'])", [({"events": []}, {"counts": {}, "total": 0}, "requested_behavior")],
        [({"events": [{"kind": "open", "detail": "confidential-1"}, {"kind": "open", "detail": "confidential-2"}]},
          {"counts": {"open": 2}, "total": 2}, "requested_behavior"),
         ({"events": [{"kind": "b", "detail": "x"}, {"kind": "a", "detail": "y"}]},
          {"counts": {"a": 1, "b": 1}, "total": 2}, "requested_behavior")], group="near_miss"))

    ref = _source('''
        def run(data):
            limit = data['n']
            possible = [True] * (limit + 1)
            if limit >= 0:
                possible[0] = False
            if limit >= 1:
                possible[1] = False
            for number in range(2, limit + 1):
                if possible[number]:
                    for multiple in range(number * number, limit + 1, number):
                        possible[multiple] = False
            primes = [value for value, prime in enumerate(possible) if prime]
            return {'count': len(primes), 'sum': sum(primes)}
    ''')
    tasks.append(_task(
        "prime-prefix-summary", "final",
        "Compute count and sum of all prime integers in the INCLUSIVE interval [2,n]. A prime is an integer "
        "greater than one with exactly two positive divisors. n is between0 and200. Return exactly count and "
        "sum; no legacy interface or incremental update behavior is involved. Implement the requested standalone "
        "computation; no prior behavior is being preserved or replaced.",
        _obj({"n": {"type": "integer", "minimum": 0, "maximum": 200}}), ref,
        '''
        def run(data):
            primes = []
            for value in range(2, data['n'] + 1):
                if all(value % divisor != 0 for divisor in range(2, value)):
                    primes.append(value)
            return {'count': len(primes), 'sum': sum(primes)}
        ''', _change(ref, "possible[1] = False", "possible[1] = True"), "data['n'] > 1",
        [({"n": 0}, {"count": 0, "sum": 0}, "requested_behavior")],
        [({"n": 1}, {"count": 0, "sum": 0}, "requested_behavior"),
         ({"n": 2}, {"count": 1, "sum": 2}, "requested_behavior"),
         ({"n": 10}, {"count": 4, "sum": 17}, "requested_behavior"),
         ({"n": 20}, {"count": 8, "sum": 77}, "requested_behavior")], group="unrelated"))
    return tasks


def final_coding_tasks() -> list[CodingAdapter]:
    """Nine final task instances in THREE structural families, not nine clusters."""
    families = _final_families()
    extra = {
        "invoice-local-extension": [
            ([({"items": [{"quantity": 3, "price": 7}], "currency": "CNY", "operation": "legacy", "discount": 4},
               {"subtotal": 21, "currency": "CNY"})],
             [({"items": [{"quantity": 3, "price": 7}], "currency": "CNY", "operation": "discount", "discount": 4},
               {"subtotal": 21, "currency": "CNY", "due": 17}),
              ({"items": [], "currency": "CHF", "operation": "discount", "discount": 0},
               {"subtotal": 0, "currency": "CHF", "due": 0})]),
            ([({"items": [{"quantity": 1, "price": 11}, {"quantity": 2, "price": 4}], "currency": "GBP", "operation": "legacy", "discount": 25},
               {"subtotal": 19, "currency": "GBP"})],
             [({"items": [{"quantity": 1, "price": 11}, {"quantity": 2, "price": 4}], "currency": "GBP", "operation": "discount", "discount": 25},
               {"subtotal": 19, "currency": "GBP", "due": 0}),
              ({"items": [{"quantity": 4, "price": 5}], "currency": "AUD", "operation": "discount", "discount": 2},
               {"subtotal": 20, "currency": "AUD", "due": 18})]),
        ],
        "explicit-redacted-replacement": [
            ([({"events": []}, {"counts": {}, "total": 0})],
             [({"events": [{"kind": "arrive", "detail": "private-A"}, {"kind": "depart", "detail": "private-B"},
                           {"kind": "arrive", "detail": "private-C"}]}, {"counts": {"arrive": 2, "depart": 1}, "total": 3})]),
            ([({"events": []}, {"counts": {}, "total": 0})],
             [({"events": [{"kind": "write", "detail": "secret-D"}, {"kind": "read", "detail": "secret-E"},
                           {"kind": "read", "detail": "secret-F"}, {"kind": "read", "detail": "secret-G"}]},
               {"counts": {"write": 1, "read": 3}, "total": 4})]),
        ],
        "prime-prefix-summary": [
            ([({"n": 0}, {"count": 0, "sum": 0})],
             [({"n": 3}, {"count": 2, "sum": 5}), ({"n": 11}, {"count": 5, "sum": 28}),
              ({"n": 30}, {"count": 10, "sum": 129})]),
            ([({"n": 0}, {"count": 0, "sum": 0})],
             [({"n": 5}, {"count": 3, "sum": 10}), ({"n": 13}, {"count": 6, "sum": 41}),
              ({"n": 40}, {"count": 12, "sum": 197})]),
        ],
    }
    result = []
    for adapter in families:
        task = adapter.task
        for variant in range(3):
            metadata = {**deepcopy(task.metadata), "variant": variant, "variants_are_not_independent_families": True}
            public, private = deepcopy(task.public_cases), deepcopy(task.private_cases)
            if variant:
                provided, hidden = extra[task.family][variant - 1]

                def cases(rows, visible):
                    return [{"label": f"{task.family}-v{variant}-{'public' if visible else 'private'}-{index}",
                             "input": deepcopy(value), "expected": deepcopy(expected), "exception": None,
                             "public": visible, "dimension": "preserved_behavior" if visible and task.family == "invoice-local-extension"
                             else "requested_behavior"} for index, (value, expected) in enumerate(rows)]

                public, private = cases(provided, True), cases(hidden, False)
            result.append(CodingAdapter(replace(task, id=task.id + f"-v{variant}",
                                                 public_cases=public, private_cases=private, metadata=metadata)))
    return result
