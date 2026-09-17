"""Fresh V7 synthetic native tasks; no historical task or failure assets.

Literal host fixtures and independently authored controls are private.  These
bounded engineering projects are not a public benchmark. Parameter variants
share a structural family and must never be counted as independent projects.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from textwrap import dedent

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v6.native import NativeAdapter

VERSION = "coevolution-v7-fresh-native-projects-v1"
ENTRY = "import logic\n\ndef solve(data):\n    return logic.run(data)\n"
INTEGER = {"type": "integer", "minimum": -100, "maximum": 100}


def obj(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def arr(item, maximum=8, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum}


def integer(low=0, high=20):
    return {"type": "integer", "minimum": low, "maximum": high}


def src(value):
    return dedent(value).strip() + "\n"


def changed(value, old, new):
    if value.count(old) != 1:
        raise ValueError("Each controlled defect must match exactly one source anchor")
    return value.replace(old, new, 1)


def public_contract(scope, obligations=()):
    return {"change_scope": scope, "preserve_obligations": list(obligations),
            "supersedes_old_policy": scope == "full_replacement"}


def coding(name, split, prompt, schema, reference, equivalent, semantic, mutation_when, public, private,
           *, group="same_mechanism", obligations=()):
    reference, equivalent, semantic = map(src, (reference, equivalent, semantic))
    preservation = changed(reference, "def run(data):", "def compute(data):") + (
        "\ndef run(data):\n    result = compute(data)\n"
        f"    if {mutation_when}:\n        data['v7_unrequested_write'] = 1\n    return result\n"
    )
    controls = {name: {"api.py": ENTRY, "logic.py": code} for name, code in (
        ("reference", reference), ("equivalent", equivalent), ("semantic_mutant", semantic),
        ("preservation_mutant", preservation))}
    if len({reference, equivalent, semantic, preservation}) != 4:
        raise ValueError("Four distinct authored control artifacts required")
    scope = "read_only" if split == "promotion" else (
        "full_replacement" if group == "near_miss" else
        "new_implementation" if group == "unrelated" else "partial_update")
    contract = public_contract(scope, ["Do not mutate any supplied input value.",
                                      "Keep the protected api.py entrypoint unchanged.", *obligations])

    def fixtures(rows, visible):
        return [{"label": f"{name}-{'public' if visible else 'private'}-{i}", "input": deepcopy(value),
                 "expected": deepcopy(expected), "exception": None, "public": visible,
                 "dimension": "requested_behavior"} for i, (value, expected) in enumerate(rows)]

    task = RepoTask(
        id="repo-v7-" + name, family=name, cluster_id="v7-family-" + name, split=split,
        prompt=prompt + "\nPUBLIC CONTRACT: " + json.dumps(contract, sort_keys=True, ensure_ascii=False)
        + "\nInput obeys input_domain. Do not mutate the original input or any nested value. "
        "Only logic.py is editable; api.py is protected and passes the actual input without copying. "
        "Return the requested JSON value. No file/network/process access, dynamic execution, or undeclared imports.",
        files=deepcopy(controls["semantic_mutant"]), reference_files=deepcopy(controls["reference"]),
        editable_paths=["logic.py"], input_domain=deepcopy(schema), public_cases=fixtures(public, True),
        private_cases=fixtures(private, False), metadata={
            "version": VERSION, "domain": "coding", "mechanism": "constraint_preservation",
            "evaluation_group": group, "public_contract": contract, "controls": controls,
            "origin": "independently_authored_v7_synthetic_not_public_benchmark",
            "historical_task_assets_used": False, "oracle": "independent_host_oracles_and_literal_fixtures",
            "independence_unit": "structural_project_family_not_parameter_or_history",
        })
    return CodingAdapter(task)


def calibration_tasks() -> list[CodingAdapter]:
    tasks = []
    reference = src('''
        def run(data):
            choices, size = data['choices'], data['right_size']
            best = None
            def visit(i, used, assignment):
                nonlocal best
                if i == len(choices):
                    key = (-len(used), assignment)
                    if best is None or key < best:
                        best = key
                    return
                for right in sorted(set(choices[i])):
                    if 0 <= right < size and right not in used:
                        visit(i + 1, used | {right}, assignment + [right])
                visit(i + 1, used, assignment + [size])
            visit(0, set(), [])
            return {'matched': -best[0], 'assignment': [None if x == size else x for x in best[1]]}
    ''')
    tasks.append(coding(
        "maximum-bipartite-assignment", "promotion",
        "Assign each left item at most one distinct right index drawn from its choices. Ignore duplicate choices "
        "and right indices >= right_size. Maximize matched count, then choose lexicographically smallest full "
        "assignment, treating unmatched as a sentinel LARGER than every right. Return matched and assignment "
        "with null for unmatched. Choosing greedily is not sufficient.",
        obj({"choices": arr(arr(integer(0, 4), 5), 5), "right_size": integer(1, 5)}), reference,
        '''
        def run(data):
            size = data['right_size']
            states = {0: []}
            for options in data['choices']:
                next_states = {}
                for mask, prefix in states.items():
                    for right in [size] + sorted(set(options)):
                        if right > size or right < size and mask & (1 << right):
                            continue
                        newmask = mask if right == size else mask | (1 << right)
                        row = prefix + [right]
                        if newmask not in next_states or row < next_states[newmask]:
                            next_states[newmask] = row
                states = next_states
            answer = min(states.values(), key=lambda row: (sum(x == size for x in row), row))
            return {'matched': sum(x != size for x in answer), 'assignment': [None if x == size else x for x in answer]}
        ''',
        '''
        def run(data):
            used, result = set(), []
            for options in data['choices']:
                available = sorted(x for x in set(options) if x < data['right_size'] and x not in used)
                chosen = available[0] if available else None
                result.append(chosen)
                if chosen is not None:
                    used.add(chosen)
            return {'matched': len(used), 'assignment': result}
        ''', "len(data['choices']) > 1",
        [({"choices": [[1, 0]], "right_size": 2}, {"matched": 1, "assignment": [0]})],
        [({"choices": [[0, 1], [0]], "right_size": 2}, {"matched": 2, "assignment": [1, 0]}),
         ({"choices": [[0], [0], []], "right_size": 1}, {"matched": 1, "assignment": [0, None, None]}),
         ({"choices": [[4], [1, 1]], "right_size": 2}, {"matched": 1, "assignment": [None, 1]}),
         ({"choices": [], "right_size": 3}, {"matched": 0, "assignment": []})]))

    reference = src('''
        def run(data):
            weights, seats = data['weights'], data['seats']
            total = sum(weights)
            if not total:
                return {'allocation': [0 for _ in weights], 'unallocated': seats}
            counts = [seats * value // total for value in weights]
            rank = sorted(range(len(weights)), key=lambda i: (-(seats * weights[i] % total), i))
            for i in rank[:seats - sum(counts)]:
                counts[i] += 1
            return {'allocation': counts, 'unallocated': 0}
    ''')
    tasks.append(coding(
        "integer-largest-remainder-allocation", "promotion",
        "Allocate integer seats proportionally to nonnegative weights using largest remainders. First floor each "
        "exact rational share; assign remaining seats by descending fractional remainder, breaking ties by original "
        "index ASCENDING. No floating point rounding. If total weight is zero return all-zero allocation and all "
        "seats unallocated; otherwise allocations sum exactly to seats and unallocated=0.",
        obj({"weights": arr(integer(), 6), "seats": integer(0, 30)}), reference,
        '''
        def run(data):
            weights, seats = data['weights'], data['seats']
            denominator = sum(weights)
            if denominator == 0:
                return {'allocation': [0] * len(weights), 'unallocated': seats}
            base = [divmod(seats * weight, denominator) for weight in weights]
            extras = seats - sum(pair[0] for pair in base)
            result = []
            for i, (whole, remainder) in enumerate(base):
                position = sum(other[1] > remainder or other[1] == remainder and j < i for j, other in enumerate(base))
                result.append(whole + (1 if position < extras else 0))
            return {'allocation': result, 'unallocated': 0}
        ''', changed(reference, "weights[i] % total), i)", "weights[i] % total), -i)"),
        "len(data['weights']) > 1",
        [({"weights": [3], "seats": 4}, {"allocation": [4], "unallocated": 0})],
        [({"weights": [1, 1, 1], "seats": 2}, {"allocation": [1, 1, 0], "unallocated": 0}),
         ({"weights": [0, 0], "seats": 5}, {"allocation": [0, 0], "unallocated": 5}),
         ({"weights": [5, 3, 2], "seats": 7}, {"allocation": [4, 2, 1], "unallocated": 0}),
         ({"weights": [], "seats": 2}, {"allocation": [], "unallocated": 2})]))

    reference = src('''
        def run(data):
            offset, width = data['offset'], data['width']
            if offset + width > 16:
                return {'error': 'range'}
            first, second = data['bytes']
            word = first * 256 + second if data['order'] == 'big' else second * 256 + first
            value = (word >> offset) & ((1 << width) - 1)
            if data['signed'] and value & (1 << (width - 1)):
                value -= 1 << width
            return {'value': value}
    ''')
    tasks.append(coding(
        "endian-twos-complement-bitfield", "promotion",
        "Interpret exactly two bytes in the requested big/little byte order. Extract width bits starting at "
        "zero-based offset from the LEAST significant bit of that interpreted 16-bit word. If signed, interpret "
        "the EXTRACTED field (not whole word) as two's complement. offset+width>16 returns {'error':'range'}, "
        "otherwise return {'value':integer}. Input order and byte values remain unchanged.",
        obj({"bytes": arr(integer(0, 255), 2, 2), "order": {"type": "string", "enum": ["big", "little"]},
             "offset": integer(0, 15), "width": integer(1, 16), "signed": {"type": "boolean"}}), reference,
        '''
        def run(data):
            start, length = data['offset'], data['width']
            if start + length > 16:
                return {'error': 'range'}
            low, high = data['bytes'] if data['order'] == 'little' else list(reversed(data['bytes']))
            bits = [(low // (2 ** i)) % 2 for i in range(8)] + [(high // (2 ** i)) % 2 for i in range(8)]
            selected = bits[start:start + length]
            result = sum(bit * (2 ** i) for i, bit in enumerate(selected))
            if data['signed'] and selected[-1]:
                result = -sum((1 - bit) * (2 ** i) for i, bit in enumerate(selected)) - 1
            return {'value': result}
        ''', changed(reference, "value -= 1 << width", "value -= 1 << 16"), "data['signed']",
        [({"bytes": [0, 7], "order": "big", "offset": 0, "width": 4, "signed": False}, {"value": 7})],
        [({"bytes": [0, 240], "order": "big", "offset": 4, "width": 4, "signed": True}, {"value": -1}),
         ({"bytes": [1, 128], "order": "little", "offset": 0, "width": 16, "signed": True}, {"value": -32767}),
         ({"bytes": [12, 0], "order": "big", "offset": 8, "width": 4, "signed": True}, {"value": -4}),
         ({"bytes": [1, 2], "order": "little", "offset": 15, "width": 2, "signed": False}, {"error": "range"})]))

    reference = src('''
        def run(data):
            a, b = data['left'], data['right']
            table = [[''] * (len(b) + 1) for _ in range(len(a) + 1)]
            for i in range(len(a) - 1, -1, -1):
                for j in range(len(b) - 1, -1, -1):
                    options = [table[i + 1][j], table[i][j + 1]]
                    if a[i] == b[j]:
                        options.append(a[i] + table[i + 1][j + 1])
                    table[i][j] = min(options, key=lambda text: (-len(text), text))
            return table[0][0]
    ''')
    tasks.append(coding(
        "canonical-longest-common-subsequence", "promotion",
        "Return the lexicographically SMALLEST longest common subsequence of left and right, not substring. "
        "Characters may repeat; preserve order without reusing a character position. The empty string is valid. "
        "Alphabet is a,b,c; inputs are bounded to 8 characters.",
        obj({"left": {"type": "string", "pattern": "^[abc]*$", "maxLength": 8},
             "right": {"type": "string", "pattern": "^[abc]*$", "maxLength": 8}}), reference,
        '''
        def run(data):
            possibilities = {''}
            for char in data['left']:
                possibilities |= {prefix + char for prefix in list(possibilities)}
            valid = []
            for text in possibilities:
                cursor = 0
                for char in data['right']:
                    if cursor < len(text) and text[cursor] == char:
                        cursor += 1
                if cursor == len(text):
                    valid.append(text)
            return sorted(valid, key=lambda text: (-len(text), text))[0]
        ''', changed(reference, "min(options, key=lambda text: (-len(text), text))",
                     "max(options, key=lambda text: (len(text), text))"), "len(data['left']) > 1",
        [({"left": "a", "right": "a"}, "a")],
        [({"left": "ab", "right": "ba"}, "a"), ({"left": "aacb", "right": "abac"}, "aac"),
         ({"left": "", "right": "abc"}, ""), ({"left": "abcabc", "right": "acbacb"}, "abab")]))

    reference = src('''
        def run(data):
            grid = data['grid']
            if not grid or any(len(row) != len(grid[0]) for row in grid) or not grid[0]:
                return None
            start, goal = tuple(data['start']), tuple(data['goal'])
            def legal(node):
                return 0 <= node[0] < len(grid) and 0 <= node[1] < len(grid[0]) and grid[node[0]][node[1]] > 0
            if not legal(start) or not legal(goal):
                return None
            distance, visited = {start: 0}, set()
            while any(node not in visited for node in distance):
                node = min((node for node in distance if node not in visited), key=lambda p: distance[p])
                if node == goal:
                    return distance[node]
                visited.add(node)
                for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nxt = (node[0] + dr, node[1] + dc)
                    if legal(nxt):
                        proposed = distance[node] + grid[nxt[0]][nxt[1]]
                        if nxt not in distance or proposed < distance[nxt]:
                            distance[nxt] = proposed
            return None
    ''')
    tasks.append(coding(
        "weighted-orthogonal-grid-routing", "promotion",
        "Return minimum total ENTERED-cell cost from start to goal using orthogonal moves. The start cell costs "
        "zero, including start==goal. Positive cells have their integer entry cost; zero cells are blocked. "
        "No diagonal/wrap moves. Empty/ragged grid, out-of-range/blocked endpoints or unreachable goal return null.",
        obj({"grid": arr(arr(integer(0, 9), 4), 4), "start": arr(integer(0, 3), 2, 2),
             "goal": arr(integer(0, 3), 2, 2)}), reference,
        '''
        def run(data):
            g = data['grid']
            if not g or not g[0] or any(len(row) != len(g[0]) for row in g):
                return None
            nodes = [(r, c) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] > 0]
            start, goal = tuple(data['start']), tuple(data['goal'])
            if start not in nodes or goal not in nodes:
                return None
            distances = {start: 0}
            for _ in nodes:
                old = dict(distances)
                for a in nodes:
                    if a not in old:
                        continue
                    for b in nodes:
                        if abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
                            candidate = old[a] + g[b[0]][b[1]]
                            if b not in distances or candidate < distances[b]:
                                distances[b] = candidate
            return distances.get(goal)
        ''', changed(reference, "distance[node] + grid[nxt[0]][nxt[1]]", "distance[node] + 1"),
        "sum(len(row) for row in data['grid']) > 2",
        [({"grid": [[1, 1]], "start": [0, 0], "goal": [0, 1]}, 1)],
        [({"grid": [[1, 9, 1], [1, 1, 1]], "start": [0, 0], "goal": [0, 2]}, 4),
         ({"grid": [[2, 0], [0, 3]], "start": [0, 0], "goal": [1, 1]}, None),
         ({"grid": [[7]], "start": [0, 0], "goal": [0, 0]}, 0),
         ({"grid": [[1], [1, 2]], "start": [0, 0], "goal": [1, 0]}, None)]))

    reference = src(r'''
        def run(data):
            text, tokens, i = data['text'], [], 0
            while i < len(text):
                if text[i].isspace():
                    i += 1
                elif text[i:i + 2] == '--':
                    end = text.find('\n', i)
                    i = len(text) if end < 0 else end + 1
                elif text[i] == "'":
                    start, value = i, ''
                    i += 1
                    while i < len(text):
                        if text[i:i + 2] == "''":
                            value += "'"
                            i += 2
                        elif text[i] == "'":
                            i += 1
                            tokens.append(['string', value])
                            break
                        else:
                            value += text[i]
                            i += 1
                    else:
                        return {'tokens': tokens, 'error': start}
                elif text[i].isascii() and (text[i].isalpha() or text[i] == '_'):
                    end = i + 1
                    while end < len(text) and text[end].isascii() and (text[end].isalnum() or text[end] == '_'):
                        end += 1
                    tokens.append(['id', text[i:end]])
                    i = end
                elif text[i] in '0123456789':
                    end = i + 1
                    while end < len(text) and text[end] in '0123456789':
                        end += 1
                    tokens.append(['integer', text[i:end]])
                    i = end
                elif text[i] == '=':
                    width = 2 if text[i:i + 2] == '==' else 1
                    tokens.append(['operator', text[i:i + width]])
                    i += width
                else:
                    return {'tokens': tokens, 'error': i}
            return {'tokens': tokens, 'error': None}
    ''')
    equivalent = src(r'''
        import re
        def run(data):
            value, out, cursor = data['text'], [], 0
            pattern = re.compile(r"(?P<space>\s+)|(?P<comment>--[^\n]*(?:\n|$))|(?P<string>'(?:[^']|'')*'(?!'))|(?P<id>[A-Za-z_][A-Za-z_0-9]*)|(?P<integer>[0-9]+)|(?P<operator>==|=)")
            while cursor < len(value):
                match = pattern.match(value, cursor)
                if match is None:
                    return {'tokens': out, 'error': cursor}
                kind, token = match.lastgroup, match.group()
                if kind == 'string':
                    out.append([kind, token[1:-1].replace("''", "'")])
                elif kind not in ['space', 'comment']:
                    out.append([kind, token])
                cursor = match.end()
            return {'tokens': out, 'error': None}
    ''')
    tasks.append(coding(
        "quoted-comment-shielding-lexer", "promotion",
        "Tokenize ASCII identifiers [A-Za-z_][A-Za-z_0-9]*, digit runs as integer TEXT preserving leading zeros, "
        "operators '=' or '==' by longest match, and single-quoted strings whose doubled quotes denote one literal "
        "quote. '--' starts a comment to newline ONLY outside a quoted string. Ignore whitespace/comments. "
        "Return {'tokens':[[kind,value],...], 'error':null}; on unknown symbol stop with its character index, "
        "or on unterminated string with the opening quote index, preserving previously completed tokens.",
        obj({"text": {"type": "string", "maxLength": 120}}), reference, equivalent,
        changed(reference, "width = 2 if text[i:i + 2] == '==' else 1", "width = 1"),
        "len(data['text']) > 5",
        [({"text": "x=01"}, {"tokens": [["id", "x"], ["operator", "="], ["integer", "01"]], "error": None})],
        [({"text": "a=='x--y' -- ignored\nz"}, {"tokens": [["id", "a"], ["operator", "=="], ["string", "x--y"], ["id", "z"]], "error": None}),
         ({"text": "'it''s'"}, {"tokens": [["string", "it's"]], "error": None}),
         ({"text": "a 'bad"}, {"tokens": [["id", "a"]], "error": 2}),
         ({"text": "x@"}, {"tokens": [["id", "x"]], "error": 1})]))
    return tasks


def development_tasks() -> list[CodingAdapter]:
    tasks = []
    reference = src('''
        def run(data):
            text, edits = data['text'], data['edits']
            for i, edit in enumerate(edits):
                if not 0 <= edit['start'] <= edit['end'] <= len(text):
                    return {'error': 'range', 'index': i}
            for i, a in enumerate(edits):
                for b in edits[i + 1:]:
                    overlap = max(a['start'], b['start']) < min(a['end'], b['end'])
                    inside = (a['start'] == a['end'] and b['start'] < a['start'] < b['end'] or
                              b['start'] == b['end'] and a['start'] < b['start'] < a['end'])
                    if overlap or inside:
                        return {'error': 'overlap'}
            order = sorted(range(len(edits)), key=lambda i: (edits[i]['start'], edits[i]['end'] != edits[i]['start'], i))
            cursor, pieces = 0, []
            for i in order:
                edit = edits[i]
                pieces += [text[cursor:edit['start']], edit['value']]
                cursor = edit['end']
            return {'text': ''.join(pieces) + text[cursor:]}
    ''')
    semantic = changed(reference, "pieces += [text[cursor:edit['start']], edit['value']]",
                       "pieces += [text[cursor:edit['start']], edit['value']] if edit['end'] > edit['start'] else []")
    tasks.append(coding(
        "original-coordinate-multi-edit", "development",
        "Extend the text patcher with zero-width insertions while retaining simultaneous ORIGINAL-coordinate "
        "replacement semantics. Every edit replaces text[start:end] with value. Validate all ranges first, returning "
        "{'error':'range','index':first_invalid_input_index}. Reject overlapping nonempty spans or insertions "
        "strictly inside a nonempty span as {'error':'overlap'}. Adjacent spans and endpoint insertions are legal. "
        "At one coordinate emit insertions in original edit order BEFORE a replacement starting there. "
        "Otherwise sort by original coordinate, never shift later coordinates after earlier edits. "
        "Success returns {'text':result}; unchanged characters and caller's edit order must be preserved.",
        obj({"text": {"type": "string", "maxLength": 40}, "edits": arr(obj({"start": integer(0, 45),
             "end": integer(0, 45), "value": {"type": "string", "maxLength": 12}}), 8)}), reference,
        '''
        def run(data):
            original, changes = data['text'], data['edits']
            for i in range(len(changes)):
                a = changes[i]
                if a['start'] > a['end'] or a['end'] > len(original):
                    return {'error': 'range', 'index': i}
            occupied = {}
            insertions = {}
            replacements = {}
            for item in changes:
                start, end = item['start'], item['end']
                if start == end:
                    insertions.setdefault(start, []).append(item['value'])
                else:
                    for position in range(start, end):
                        if position in occupied:
                            return {'error': 'overlap'}
                        occupied[position] = start
                    replacements[start] = item['value']
            if any(position in occupied and occupied[position] < position for position in insertions):
                return {'error': 'overlap'}
            output = []
            for position in range(len(original) + 1):
                output += insertions.get(position, [])
                if position in replacements:
                    output.append(replacements[position])
                elif position < len(original) and position not in occupied:
                    output.append(original[position])
            return {'text': ''.join(output)}
        ''', semantic, "len(data['edits']) > 1",
        [({"text": "abcd", "edits": [{"start": 1, "end": 3, "value": "X"}]}, {"text": "aXd"})],
        [({"text": "abcd", "edits": [{"start": 2, "end": 2, "value": "I"},
             {"start": 0, "end": 1, "value": "LONG"}, {"start": 2, "end": 2, "value": "J"}]}, {"text": "LONGbIJcd"}),
         ({"text": "abc", "edits": [{"start": 1, "end": 2, "value": "R"},
             {"start": 1, "end": 1, "value": "I"}, {"start": 2, "end": 2, "value": "E"}]}, {"text": "aIREc"}),
         ({"text": "abcd", "edits": [{"start": 0, "end": 3, "value": "x"},
             {"start": 2, "end": 2, "value": "y"}]}, {"error": "overlap"}),
         ({"text": "a", "edits": [{"start": 0, "end": 0, "value": "x"},
             {"start": 2, "end": 2, "value": "y"}]}, {"error": "range", "index": 1})],
        obligations=["Preserve original-coordinate replacement and unaffected text when adding insertions."]))

    reference = src('''
        def match(pattern, path):
            if not pattern:
                return not path
            if pattern[0] == '**':
                return any(match(pattern[1:], path[i:]) for i in range(len(path) + 1))
            return bool(path) and (pattern[0] == '*' or pattern[0] == path[0]) and match(pattern[1:], path[1:])
        def run(data):
            matching = [i for i, rule in enumerate(data['rules']) if match(rule['pattern'], data['path'])]
            if not matching:
                return {'allowed': False, 'matched': []}
            def priority(i):
                rule = data['rules'][i]
                return (sum(part not in ['*', '**'] for part in rule['pattern']), rule['priority'])
            best = max(priority(i) for i in matching)
            winners = [i for i in matching if priority(i) == best]
            allowed = all(data['rules'][i]['effect'] == 'allow' for i in winners)
            return {'allowed': allowed, 'matched': winners}
    ''')
    tasks.append(coding(
        "hierarchical-wildcard-policy-resolution", "development",
        "Extend the policy engine with '**' matching ZERO OR MORE path segments; '*' still matches exactly one "
        "segment, literals exactly one equal segment. Patterns must match the FULL path. Among matching rules "
        "maximize (number of literal pattern segments, numeric priority), in that order. All tied winners appear "
        "as original zero-based indices in matched; DENY wins any tie. No match means allowed=false, matched=[]. "
        "Adding recursive wildcard support must preserve specificity, priority, deny ties and input ordering.",
        obj({"path": arr({"type": "string", "enum": ["a", "b", "c"]}, 6), "rules": arr(obj({
            "pattern": arr({"type": "string", "enum": ["a", "b", "c", "*", "**"]}, 6),
            "priority": integer(-3, 3), "effect": {"type": "string", "enum": ["allow", "deny"]}}), 6)}), reference,
        '''
        def matches(pattern, path):
            frontier, seen = [(0, 0)], set()
            while frontier:
                i, j = frontier.pop()
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                if i == len(pattern):
                    if j == len(path):
                        return True
                    continue
                if pattern[i] == '**':
                    frontier.append((i + 1, j))
                    if j < len(path):
                        frontier.append((i, j + 1))
                elif j < len(path) and pattern[i] in ['*', path[j]]:
                    frontier.append((i + 1, j + 1))
            return False
        def run(data):
            groups = {}
            for index, rule in enumerate(data['rules']):
                if matches(rule['pattern'], data['path']):
                    rank = (len([part for part in rule['pattern'] if part not in ['*', '**']]), rule['priority'])
                    groups.setdefault(rank, []).append(index)
            if not groups:
                return {'allowed': False, 'matched': []}
            winners = groups[sorted(groups)[-1]]
            return {'allowed': not any(data['rules'][i]['effect'] == 'deny' for i in winners), 'matched': winners}
        ''', changed(reference, "range(len(path) + 1)", "range(1, len(path) + 1)"), "len(data['rules']) > 1",
        [({"path": ["a", "b"], "rules": [{"pattern": ["a", "*"], "priority": 0, "effect": "allow"}]},
          {"allowed": True, "matched": [0]})],
        [({"path": ["a"], "rules": [{"pattern": ["a", "**"], "priority": 0, "effect": "allow"},
              {"pattern": ["*"], "priority": 3, "effect": "deny"}]}, {"allowed": True, "matched": [0]}),
         ({"path": ["a", "b"], "rules": [{"pattern": ["a", "**"], "priority": 0, "effect": "allow"},
              {"pattern": ["a", "*"], "priority": 0, "effect": "deny"}]}, {"allowed": False, "matched": [0, 1]}),
         ({"path": [], "rules": [{"pattern": ["**"], "priority": 0, "effect": "allow"}]},
          {"allowed": True, "matched": [0]}),
         ({"path": ["b"], "rules": [{"pattern": ["a"], "priority": 3, "effect": "allow"}]},
          {"allowed": False, "matched": []})], obligations=["Preserve specificity ordering and deny-overrides tie behavior."]))

    reference = src('''
        def norm(a, b):
            if b == 0:
                return (0, 0)
            x, y = abs(a), abs(b)
            while y:
                x, y = y, x % y
            common = x
            sign = -1 if b < 0 else 1
            return (sign * a // common, abs(b) // common)
        def combine(a, op, b):
            if op == '+':
                return norm(a[0] * b[1] + b[0] * a[1], a[1] * b[1])
            if op == '-':
                return norm(a[0] * b[1] - b[0] * a[1], a[1] * b[1])
            if op == '*':
                return norm(a[0] * b[0], a[1] * b[1])
            return norm(a[0] * b[1], a[1] * b[0])
        def run(data):
            tokens, cursor = data['tokens'], 0
            def atom():
                nonlocal cursor
                token = tokens[cursor]
                cursor += 1
                if isinstance(token, int):
                    return (token, 1)
                if token in ['+', '-']:
                    value = atom()
                    return value if token == '+' else (-value[0], value[1])
                if token != '(':
                    raise ValueError()
                value = expression()
                if tokens[cursor] != ')':
                    raise ValueError()
                cursor += 1
                return value
            def term():
                nonlocal cursor
                value = atom()
                while cursor < len(tokens) and tokens[cursor] in ['*', '/']:
                    op = tokens[cursor]
                    cursor += 1
                    value = combine(value, op, atom())
                return value
            def expression():
                nonlocal cursor
                value = term()
                while cursor < len(tokens) and tokens[cursor] in ['+', '-']:
                    op = tokens[cursor]
                    cursor += 1
                    value = combine(value, op, term())
                return value
            try:
                value = expression()
                if cursor != len(tokens):
                    return {'error': 'syntax'}
                if value[1] == 0:
                    return {'error': 'division_by_zero'}
                return {'numerator': value[0], 'denominator': value[1]}
            except ZeroDivisionError:
                return {'error': 'division_by_zero'}
            except (ValueError, IndexError):
                return {'error': 'syntax'}
    ''')
    equivalent = src('''
        def gcd(a, b):
            return a if b == 0 else gcd(b, a % b)
        def run(data):
            tokens = data['tokens']
            def parse(low, high):
                if low >= high:
                    raise ValueError()
                depth, binary = 0, []
                for i in range(low, high):
                    token = tokens[i]
                    if token == '(':
                        depth += 1
                    elif token == ')':
                        depth -= 1
                    if depth < 0:
                        raise ValueError()
                    if depth == 0 and token in ['+', '-', '*', '/'] and i > low and (isinstance(tokens[i - 1], int) or tokens[i - 1] == ')'):
                        binary.append(i)
                if depth != 0:
                    raise ValueError()
                weak = [i for i in binary if tokens[i] in ['+', '-']]
                choices = weak or binary
                if choices:
                    i = choices[-1]
                    a, b = parse(low, i), parse(i + 1, high)
                    if tokens[i] == '+':
                        return a[0] * b[1] + b[0] * a[1], a[1] * b[1]
                    if tokens[i] == '-':
                        return a[0] * b[1] - b[0] * a[1], a[1] * b[1]
                    if tokens[i] == '*':
                        return a[0] * b[0], a[1] * b[1]
                    if b[0] == 0:
                        return 0, 0
                    return a[0] * b[1], a[1] * b[0]
                if tokens[low] in ['+', '-']:
                    a, b = parse(low + 1, high)
                    return (-a if tokens[low] == '-' else a), b
                if tokens[low] == '(' and tokens[high - 1] == ')':
                    return parse(low + 1, high - 1)
                if high == low + 1 and isinstance(tokens[low], int):
                    return tokens[low], 1
                raise ValueError()
            try:
                a, b = parse(0, len(tokens))
                if b == 0:
                    return {'error': 'division_by_zero'}
                common = gcd(abs(a), abs(b))
                return {'numerator': a // common if b > 0 else -a // common, 'denominator': abs(b) // common}
            except ZeroDivisionError:
                return {'error': 'division_by_zero'}
            except ValueError:
                return {'error': 'syntax'}
    ''')
    tasks.append(coding(
        "exact-rational-expression-extension", "development",
        "Extend integer +,-,* expression evaluation with exact rational division. tokens are integer tokens and "
        "operators/parentheses. Preserve standard precedence (*,/ before +,-), LEFT associativity of binary operators, "
        "nested parentheses and recursive unary +/- at atom positions. Return reduced numerator/positive denominator; "
        "zero is 0/1. Return {'error':'division_by_zero'} on division by a zero expression or {'error':'syntax'} "
        "on malformed tokens. Malformed syntax takes precedence over any zero division in the same input. "
        "Never use Python eval or floating point.",
        obj({"tokens": arr({"oneOf": [integer(-20, 20), {"type": "string", "enum": ["+", "-", "*", "/", "(", ")"]}]}, 25)}),
        reference, equivalent, changed(reference, "a[1] * b[0])", "a[1] * abs(b[0]))"), "len(data['tokens']) > 3",
        [({"tokens": [6, "/", 4]}, {"numerator": 3, "denominator": 2})],
        [({"tokens": [1, "/", "-", 2, "+", 1, "/", 3]}, {"numerator": -1, "denominator": 6}),
         ({"tokens": ["-", "(", 2, "+", 3, ")", "*", 4]}, {"numerator": -20, "denominator": 1}),
         ({"tokens": [8, "/", 4, "/", 2]}, {"numerator": 1, "denominator": 1}),
         ({"tokens": [1, "/", "(", 2, "-", 2, ")"]}, {"error": "division_by_zero"}),
         ({"tokens": [1, "+"]}, {"error": "syntax"}),
         ({"tokens": [2, "+", 3, "*", 4]}, {"numerator": 14, "denominator": 1})],
        obligations=["Preserve precedence, unary signs, left associativity and exact rational normalization."]))
    return tasks


def final_coding_tasks() -> list[CodingAdapter]:
    families = []
    reference = src('''
        def run(data):
            order, latest = [], {}
            for record in data['events']:
                key = record['id']
                if key not in latest:
                    order.append(key)
                if key not in latest or record['version'] >= latest[key]['version']:
                    latest[key] = record
            alive = [key for key in order if not latest[key]['deleted']]
            start, limit = data['offset'], data['limit']
            chosen = alive[start:start + limit]
            return {'items': [{'id': key, 'value': latest[key]['value']} for key in chosen],
                    'total': len(alive), 'next': start + len(chosen) if start + len(chosen) < len(alive) else None}
    ''')
    families.append(coding(
        "event-sourced-snapshot-pagination", "final",
        "Extend snapshot pagination to support deletion tombstones. For each id choose greatest version; ties use "
        "the LAST event. Order distinct ids by FIRST occurrence, independent of winning event position. Remove ids "
        "whose winning event has deleted=true BEFORE applying offset/limit; older live events never resurrect them. "
        "Return items [{id,value}], total live-id count, next offset if more remain else null. limit>=1. "
        "Preserve deduplication, stable order and pagination meanings when adding tombstones.",
        obj({"events": arr(obj({"id": {"type": "string", "enum": ["a", "b", "c"]}, "version": integer(0, 9),
             "deleted": {"type": "boolean"}, "value": INTEGER}), 10), "offset": integer(0, 12), "limit": integer(1, 5)}), reference,
        '''
        def run(data):
            events = data['events']
            keys = []
            for event in events:
                if event['id'] not in keys:
                    keys.append(event['id'])
            active = []
            for key in keys:
                positions = [i for i, event in enumerate(events) if event['id'] == key]
                winner = max(positions, key=lambda i: (events[i]['version'], i))
                if not events[winner]['deleted']:
                    active.append({'id': key, 'value': events[winner]['value']})
            end = data['offset'] + data['limit']
            return {'items': active[data['offset']:end], 'total': len(active),
                    'next': end if end < len(active) else None}
        ''', changed(reference, "alive = [key for key in order if not latest[key]['deleted']]", "alive = list(order)"),
        "len(data['events']) > 1",
        [({"events": [{"id": "a", "version": 0, "deleted": False, "value": 4}], "offset": 0, "limit": 1},
          {"items": [{"id": "a", "value": 4}], "total": 1, "next": None})],
        [({"events": [{"id": "a", "version": 2, "deleted": True, "value": 1},
                      {"id": "b", "version": 1, "deleted": False, "value": 2},
                      {"id": "a", "version": 1, "deleted": False, "value": 8},
                      {"id": "c", "version": 0, "deleted": False, "value": 3}], "offset": 0, "limit": 1},
          {"items": [{"id": "b", "value": 2}], "total": 2, "next": 1}),
         ({"events": [{"id": "a", "version": 1, "deleted": True, "value": 4},
                      {"id": "b", "version": 0, "deleted": False, "value": 7},
                      {"id": "a", "version": 1, "deleted": False, "value": 9}], "offset": 0, "limit": 1},
          {"items": [{"id": "a", "value": 9}], "total": 2, "next": 1}),
         ({"events": [], "offset": 3, "limit": 2}, {"items": [], "total": 0, "next": None})],
        obligations=["Preserve winning-version selection, first-occurrence order and live-view offset meanings."]))

    reference = src('''
        def run(data):
            parts, escaped = [], 0
            for segment in data['path'].split('/'):
                if segment in ['', '.']:
                    continue
                if segment == '..':
                    if parts:
                        parts.pop()
                    else:
                        escaped += 1
                else:
                    parts.append(segment)
            return {'path': '/' + '/'.join(parts), 'root_escape_attempts': escaped}
    ''')
    families.append(coding(
        "virtual-path-root-confinement", "final",
        "Fully REPLACE the previous virtual-path rendering policy with root-confined normalization. Pure strings, "
        "never filesystem resolution: treat both relative and leading-slash inputs as rooted. Ignore empty and '.' "
        "segments; '..' removes the latest ordinary segment if present, otherwise increments root_escape_attempts "
        "and never appears in output. Other segments are literal, case-sensitive (no decoding). Return exactly "
        "{'path':'/'+normalized_segments,'root_escape_attempts':count}; root is '/'. Old policy preserving parent "
        "segments is obsolete, and the new output schema replaces any old rendering.",
        obj({"path": {"type": "string", "maxLength": 100}}), reference,
        '''
        def run(data):
            segments = [segment for segment in data['path'].split('/') if segment not in ['', '.']]
            result, count = [], 0
            for segment in segments:
                if segment != '..':
                    result = result + [segment]
                elif len(result) == 0:
                    count += 1
                else:
                    result = result[:-1]
            return {'root_escape_attempts': count, 'path': '/' + '/'.join(result)}
        ''', changed(reference, "escaped += 1", "parts.append('..')"), "'..' in data['path']",
        [({"path": "a//b/./"}, {"path": "/a/b", "root_escape_attempts": 0})],
        [({"path": "../../a/../b/../../c"}, {"path": "/c", "root_escape_attempts": 3}),
         ({"path": "/a/../.."}, {"path": "/", "root_escape_attempts": 1}),
         ({"path": "a/.../B"}, {"path": "/a/.../B", "root_escape_attempts": 0})], group="near_miss"))

    reference = src('''
        def run(data):
            inventory = {}
            for entry in data['coins']:
                inventory[entry['value']] = inventory.get(entry['value'], 0) + entry['count']
            target = data['target']
            ways = [1] + [0] * target
            for value, stock in sorted(inventory.items()):
                updated = [0] * (target + 1)
                for previous in range(target + 1):
                    for count in range(min(stock, (target - previous) // value) + 1):
                        updated[previous + count * value] += ways[previous]
                ways = updated
            return ways[target]
    ''')
    families.append(coding(
        "bounded-denomination-combinations", "final",
        "Implement a new standalone combinatorial computation; no prior behavior is being preserved or replaced. "
        "coins lists positive denomination value and nonnegative stock count. Merge stock for duplicate denominations "
        "FIRST. Count unordered denomination-count vectors summing exactly to target without exceeding merged stock. "
        "Coins with equal value are indistinguishable, not different types; orderings are not distinct. target=0 has "
        "one empty combination. Return the integer count and never mutate the inventory.",
        obj({"coins": arr(obj({"value": integer(1, 8), "count": integer(0, 4)}), 6), "target": integer(0, 20)}), reference,
        '''
        def run(data):
            values = sorted(set(row['value'] for row in data['coins']))
            stocks = [sum(row['count'] for row in data['coins'] if row['value'] == value) for value in values]
            def enumerate_counts(index, remaining):
                if index == len(values):
                    return int(remaining == 0)
                return sum(enumerate_counts(index + 1, remaining - number * values[index])
                           for number in range(min(stocks[index], remaining // values[index]) + 1))
            return enumerate_counts(0, data['target'])
        ''', changed(reference, "inventory.get(entry['value'], 0) + entry['count']", "entry['count']"),
        "len(data['coins']) > 1",
        [({"coins": [{"value": 2, "count": 2}], "target": 4}, 1)],
        [({"coins": [{"value": 1, "count": 1}, {"value": 1, "count": 1}], "target": 2}, 1),
         ({"coins": [{"value": 1, "count": 3}, {"value": 2, "count": 2}, {"value": 3, "count": 1}], "target": 4}, 3),
         ({"coins": [], "target": 0}, 1), ({"coins": [{"value": 3, "count": 1}], "target": 4}, 0)], group="unrelated"))

    result = []
    for adapter in families:
        for variant in range(2):
            task = adapter.task
            public_cases = deepcopy(task.public_cases)
            private_cases = deepcopy(task.private_cases)
            if variant:
                for case in public_cases + private_cases:
                    value, expected = case['input'], case['expected']
                    if task.family == 'event-sourced-snapshot-pagination':
                        for record in value['events']:
                            record['value'] += 7
                        for item in expected['items']:
                            item['value'] += 7
                    elif task.family == 'virtual-path-root-confinement':
                        value['path'] = value['path'].translate(str.maketrans('abcB', 'qrsQ'))
                        expected['path'] = expected['path'].translate(str.maketrans('abcB', 'qrsQ'))
                    else:
                        for coin in value['coins']:
                            coin['value'] *= 2
                        value['target'] *= 2
            result.append(CodingAdapter(replace(task, id=task.id + f"-v{variant}",
                public_cases=public_cases, private_cases=private_cases,
                metadata={**deepcopy(task.metadata), "parameter_variant": variant,
                          "variant_not_independent_family": True})))
    return result


def _native_task(name, family, domain, scope, prompt, values):
    contract = public_contract(scope, (
        ["Preserve all explicitly unchanged downstream outputs and protected relationships."]
        if scope == "partial_update" else []))
    return NativeAdapter({
        "id": "v7-" + domain + "-" + name, "cluster_id": "v7-" + domain + "-" + family,
        "split": "final", "domain": domain, "contract": contract,
        "prompt": prompt + "\nPUBLIC CONTRACT: " + json.dumps(contract, sort_keys=True),
        "metadata": {"version": VERSION, "synthetic_engineering": True, "public_benchmark": False,
                     "family": family, "group": "same_mechanism" if scope == "partial_update" else (
                         "near_miss" if scope == "full_replacement" else "unrelated"),
                     "independence_unit": "shared_project_substrate_not_contract_variation",
                     "historical_task_assets_used": False}, **deepcopy(values)})


def final_native_tasks() -> list[NativeAdapter]:
    """Two new native structural substrates/domain, three contracts/substrate."""
    tasks = []
    inputs = {"B2": 8, "B3": 5, "B4": 4, "B5": 0, "B6": 2, "B7": 3}
    formulas = {"C2": "=B3*B4", "C3": "=MIN(B2,C2)", "C4": "=MAX(0,B2-C3)", "C5": "=C3*B6+B7"}
    scenarios = [{}, {"B2": 25, "B5": 6}, {"B2": 4, "B5": 100},
                 {"B2": 0, "B4": 0, "B7": 7}, {"B2": 11, "B3": 3, "B4": 5, "B5": 2, "B6": 4}]
    # Independent scalar obligations, not evaluation of the reference formulas.
    def capacity_expected(data, scope):
        gross = data['B3'] * data['B4']
        usable = max(0, gross - data['B5'])
        processed = min(data['B2'], usable)
        return {'C2': gross if scope == 'partial_update' else usable, 'C3': processed,
                'C4': max(0, data['B2'] - processed),
                'C5': (processed if scope == 'partial_update' else usable) * data['B6'] + data['B7']}
    for scope in ('partial_update', 'full_replacement'):
        reference = ({"C3": "=MIN(B2,MAX(0,C2-B5))"} if scope == 'partial_update' else
                     {"C2": "=MAX(0,B3*B4-B5)", "C3": "=MIN(B2,C2)", "C4": "=MAX(0,B2-C3)", "C5": "=C2*B6+B7"})
        cases = [{"id": f"capacity-recompute-{i}", "overrides": override,
                  "expected": capacity_expected({**inputs, **override}, scope)} for i, override in enumerate(scenarios)]
        tasks.append(_native_task('capacity-' + scope, 'production-capacity-workbook', 'spreadsheet', scope,
            "B2 demand units, B3 throughput/hour, B4 hours, B5 unavailable units, B6 energy/unit, B7 fixed energy. "
            "C2 capacity, C3 processed units, C4 backlog, C5 energy. " + (
                "Add unavailable-unit support ONLY to C3: processed=min(demand,max(0,gross capacity-unavailable)). "
                "Preserve C2 as GROSS capacity, C4 backlog, and C5 energy charged only on actually processed units. "
                "C2,C4,C5 formulas are protected, even when their recomputed values change."
                if scope == 'partial_update' else
                "Fully replace capacity/accounting meanings: C2 is NET available capacity=max(0,B3*B4-B5), "
                "C3=min(demand,net capacity), C4=max(0,demand-processed), and C5 charges ALL NET capacity "
                "times energy/unit plus fixed energy, including idle capacity. Old gross capacity and processed-only energy are obsolete."),
            {"inputs": inputs, "formulas": formulas, "editable_cells": ['C3'] if scope == 'partial_update' else list(formulas),
             "public_cases": cases[:1], "hidden_cases": cases[1:], "reference_artifact": {"formulas": reference}}))
    readonly_inputs = {**inputs, 'B2': 24, 'B4': 3}
    tasks.append(_native_task('capacity-readonly', 'production-capacity-workbook', 'spreadsheet', 'read_only',
        "Do not edit formulas. With the provided ORIGINAL workbook compute C4+C5 (backlog plus energy). Return only answer.",
        {"inputs": readonly_inputs, "formulas": formulas, "answer_cell": 'C4+C5', "public_cases": [],
         "hidden_cases": [{"id": 'capacity-fixed-answer', "expected": 42}], "reference_artifact": {"answer": 42}}))

    inputs = {"B2": 10, "B3": 6, "B4": 0.5, "B5": 2, "B6": 0, "B7": 12, "B8": 3}
    formulas = {"C2": "=(B2+B3)/2", "C3": "=C2+B5", "C4": "=MAX(B6,MIN(B7,C3))", "C5": "=C3-C4"}
    scenarios = [{}, {"B4": 0.25, "B5": -20}, {"B2": -2, "B3": 7, "B8": -2},
                 {"B6": 11, "B7": -1, "B2": 20}, {"B2": 0, "B3": 0, "B4": 1, "B5": 0}]
    def sensor_expected(data, scope):
        if scope == 'partial_update':
            center = data['B2'] * data['B4'] + data['B3'] * (1 - data['B4'])
            calibrated = center + data['B5']
            clipped = max(data['B6'], min(data['B7'], calibrated))
            rejected = calibrated - clipped
        else:
            center = data['B2'] - data['B3']
            calibrated = center * data['B8']
            clipped = min(max(data['B6'], data['B7']), max(min(data['B6'], data['B7']), calibrated))
            rejected = abs(calibrated - clipped)
        return {'C2': center, 'C3': calibrated, 'C4': clipped, 'C5': rejected}
    for scope in ('partial_update', 'full_replacement'):
        reference = ({"C2": "=B2*B4+B3*(1-B4)"} if scope == 'partial_update' else
                     {"C2": "=B2-B3", "C3": "=C2*B8", "C4": "=MIN(MAX(B6,B7),MAX(MIN(B6,B7),C3))",
                      "C5": "=MAX(C3-C4,C4-C3)"})
        cases = [{"id": f"sensor-recompute-{i}", "overrides": override,
                  "expected": sensor_expected({**inputs, **override}, scope)} for i, override in enumerate(scenarios)]
        tasks.append(_native_task('sensor-' + scope, 'sensor-calibration-workbook', 'spreadsheet', scope,
            "B2/B3 sensor readings, B4 first-sensor weight, B5 offset, B6/B7 bounds, B8 new gain. "
            "C2 fusion, C3 calibration, C4 clipped value, C5 rejected difference. " + (
                "Replace ONLY C2 with weighted fusion B2*B4+B3*(1-B4). Preserve C3 as fusion+offset, "
                "C4's EXACT existing MAX(B6,MIN(B7,C3)) behavior even if bounds are reversed, and C5 as SIGNED "
                "calibration-minus-clipped difference. Other cells are protected; do not introduce the new gain."
                if scope == 'partial_update' else
                "Fully replace the old fusion/offset policy: C2=B2-B3, C3=C2*B8 (old offset obsolete), "
                "C4 clamps C3 between NORMALIZED min/max(B6,B7), C5 is ABSOLUTE calibration-minus-clipped. "
                "The prior average, additive offset, unnormalized bounds and signed residual must not survive."),
            {"inputs": inputs, "formulas": formulas, "editable_cells": ['C2'] if scope == 'partial_update' else list(formulas),
             "public_cases": cases[:1], "hidden_cases": cases[1:], "reference_artifact": {"formulas": reference}}))
    tasks.append(_native_task('sensor-readonly', 'sensor-calibration-workbook', 'spreadsheet', 'read_only',
        "Use the provided ORIGINAL workbook without edits. Return C3+C4+C5 for these inputs; signed residual keeps its sign.",
        {"inputs": {**inputs, 'B5': -20}, "formulas": formulas, "answer_cell": 'C3+C4+C5', "public_cases": [],
         "hidden_cases": [{"id": 'sensor-fixed-answer', "expected": -24}], "reference_artifact": {"answer": -24}}))

    def rule(identifier, facts, then):
        return {'id': identifier, 'if': facts.split(), 'then': then}
    def rules_task(family, scope, initial, reference, facts_cases, expected, prompt, answers):
        vocabulary = sorted(set(answers) | {f for row in initial + reference for f in row['if']} |
                            {row['then'] for row in initial + reference} | {f for fs in facts_cases for f in fs})
        cases = [{'id': f'{family}-closure-{i}', 'facts': facts, 'expected': value}
                 for i, (facts, value) in enumerate(zip(facts_cases, expected))]
        task = _native_task(family + '-' + scope, family, 'rule_reasoning', scope, prompt,
            {'rules': initial, 'editable_rule_ids': [row['id'] for row in initial], 'vocabulary': vocabulary,
             'initial_facts': facts_cases[0], 'answer_facts': answers,
             'public_cases': [] if scope == 'read_only' else cases[:1],
             'hidden_cases': cases if scope == 'read_only' else cases[1:],
             'reference_artifact': {'answer': expected[0]} if scope == 'read_only' else {'rules': reference}})
        tasks.append(task)

    initial = [rule('r1', 'draft signed', 'reviewable'), rule('r2', 'reviewable peer', 'approved'),
               rule('r3', 'approved clean', 'released'), rule('r4', 'emergency', 'approved'),
               rule('r5', 'released', 'archived')]
    answers = ['reviewable', 'approved', 'released', 'archived']
    facts = [['draft', 'signed', 'peer', 'clean', 'legal'], ['emergency', 'clean'],
             ['emergency', 'signed', 'peer', 'clean', 'legal'], ['draft', 'signed', 'peer', 'clean'],
             ['emergency', 'signed', 'legal', 'clean'], ['draft', 'signed', 'peer', 'legal']]
    partial = deepcopy(initial)
    partial[2] = rule('r3', 'approved clean legal', 'released')
    replacement = [initial[0], rule('r2', 'reviewable peer legal', 'approved'), initial[2],
                   rule('r4', 'emergency signed', 'reviewable'), initial[4]]
    rules_task('document-release-workflow', 'partial_update', initial, partial, facts,
        [answers, ['approved'], ['approved', 'released', 'archived'], ['reviewable', 'approved'],
         ['approved', 'released', 'archived'], ['reviewable', 'approved']],
        "Add a legal-review requirement ONLY to release rule r3: approved AND clean AND legal -> released. "
        "Keep r1/r2's draft review chain, r4 emergency->approved (emergency approval itself does NOT need legal), "
        "and r5 released->archived exactly unchanged. Report all requested derived facts. "
        "Rules are positive; do not add closed-world negation.", answers)
    rules_task('document-release-workflow', 'full_replacement', initial, replacement, facts,
        [answers, [], answers, ['reviewable'], ['reviewable'], ['reviewable', 'approved']],
        "Replace the emergency shortcut policy. r1 remains draft+signed->reviewable. New r4 is emergency+signed "
        "->reviewable, NEVER directly approved. r2 now requires reviewable+peer+legal -> approved. "
        "r3 approved+clean -> released; r5 released -> archived. The previous emergency approval bypass is obsolete.", answers)
    rules_task('document-release-workflow', 'read_only', initial, initial, [['emergency', 'clean']],
        [['approved', 'released', 'archived']], "Do not edit any rules. Compute closure of the original rules on "
        "initial_facts and return exactly the requested derived facts, not input facts.", answers)

    initial = [rule('r1', 'raw scrubbed', 'sanitized'), rule('r2', 'sanitized consent', 'eligible'),
               rule('r3', 'eligible expired hold_clear', 'purged'), rule('r4', 'legal_hold', 'retained'),
               rule('r5', 'purged', 'audit_required')]
    answers = ['sanitized', 'eligible', 'purged', 'retained', 'audit_required']
    facts = [['raw', 'scrubbed', 'consent', 'expired', 'hold_clear', 'request'],
             ['raw', 'scrubbed', 'consent', 'expired', 'hold_clear'],
             ['raw', 'expired', 'hold_clear', 'request'], ['raw', 'request', 'expired', 'legal_hold'],
             ['raw', 'scrubbed', 'consent', 'request', 'legal_hold'], ['raw', 'request', 'hold_clear']]
    partial = deepcopy(initial)
    partial[2] = rule('r3', 'eligible expired hold_clear request', 'purged')
    replacement = [initial[0], rule('r2', 'raw request', 'eligible'), initial[2], initial[3], initial[4]]
    rules_task('retention-consent-workflow', 'partial_update', initial, partial, facts,
        [['sanitized', 'eligible', 'purged', 'audit_required'], ['sanitized', 'eligible'], [], ['retained'],
         ['sanitized', 'eligible', 'retained'], []],
        "Add request as an additional conjunct to r3 purging, preserving all other rule bodies and conclusions. "
        "Sanitization/consent eligibility, explicit hold_clear and expiry requirements, legal-hold retained flag "
        "and purge audit consequences remain unchanged. A request alone cannot bypass sanitization/consent.", answers)
    rules_task('retention-consent-workflow', 'full_replacement', initial, replacement, facts,
        [['sanitized', 'eligible', 'purged', 'audit_required'], ['sanitized'],
         ['eligible', 'purged', 'audit_required'], ['eligible', 'retained'],
         ['sanitized', 'eligible', 'retained'], ['eligible']],
        "Fully replace the eligibility policy: r2 becomes raw AND request -> eligible, regardless of consent or "
        "scrubbed state. r1 still computes sanitized; r3 eligible+expired+hold_clear -> purged, "
        "r4 legal_hold -> retained, r5 purged -> audit_required. Old sanitized+consent gate must not remain.", answers)
    rules_task('retention-consent-workflow', 'read_only', initial, initial,
        [['raw', 'scrubbed', 'consent', 'expired', 'hold_clear', 'legal_hold']],
        [answers], "Do not edit rules. Compute the original positive-rule closure on the supplied facts. "
        "hold_clear and legal_hold may both be present; do not invent negation or discard either consequence.", answers)
    return tasks
