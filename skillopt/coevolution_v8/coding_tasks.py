"""New development-only engineering fixtures, not a public benchmark.

Two prompt instances share each project family. Neither variants nor repeated
model draws are new independent projects. Expected results are host fixtures;
the model receives only the explicitly public examples.
"""

from copy import deepcopy
from textwrap import dedent

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter

VERSION = "v8-new-development-coding-projects-v1"
ENTRY = "import logic\n\ndef solve(data):\n    return logic.run(data)\n"


def source(value):
    return dedent(value).strip() + "\n"


def obj(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def arr(item, maximum=12):
    return {"type": "array", "items": item, "maxItems": maximum}


def integer(low=0, high=100):
    return {"type": "integer", "minimum": low, "maximum": high}


def word(values):
    return {"type": "string", "enum": list(values)}


def make(name, variant, prompt, schema, reference, starter, cases):
    fixtures = [{"label": f"{name}-case-{i}", "input": deepcopy(value), "expected": deepcopy(expected),
                 "exception": None, "public": i == variant, "dimension": "requested_behavior"}
                for i, (value, expected) in enumerate(cases)]
    return CodingAdapter(RepoTask(
        id=f"repo-v8-dev-{name}-{variant}", family=name, cluster_id=f"v8-development-{name}", split="development",
        prompt=prompt + " Input is guaranteed to satisfy input_domain. Preserve every supplied input value, "
            "including nested lists. Only logic.py is editable; api.py is protected. Return the specified JSON value. "
            "No files, network, processes or dynamic execution. Example selection is a parameter variant, not a new project.",
        files={"api.py": ENTRY, "logic.py": source(starter)},
        reference_files={"api.py": ENTRY, "logic.py": source(reference)}, editable_paths=["logic.py"],
        input_domain=schema, public_cases=[c for c in fixtures if c["public"]],
        private_cases=[c for c in fixtures if not c["public"]],
        metadata={"version": VERSION, "parameter_variant": variant, "domain": "coding",
                  "origin": "new_host_authored_development_not_model_failure_or_public_benchmark",
                  "historical_final_assets_used": False, "independence_unit": "project_family"} ))


def development_coding_tasks():
    result = []
    reference = '''
    def run(data):
        balances = list(data['balances'])
        committed, states = set(), []
        for transaction in data['transactions']:
            key = transaction['id']
            if key in committed:
                states.append('duplicate')
                continue
            tentative = list(balances)
            ok = True
            for move in transaction['moves']:
                a, b, amount = move['src'], move['dst'], move['amount']
                if a >= len(tentative) or b >= len(tentative) or tentative[a] < amount:
                    ok = False
                    break
                tentative[a] -= amount
                tentative[b] += amount
            if ok:
                balances = tentative
                committed.add(key)
                states.append('committed')
            else:
                states.append('rejected')
        return {'balances': balances, 'states': states}
    '''
    starter = reference.replace("tentative = list(balances)", "tentative = balances")

    def move(a, b, amount):
        return {"src": a, "dst": b, "amount": amount}

    def tx(key, *moves):
        return {"id": key, "moves": list(moves)}

    ledger = [
        ({"balances": [8, 0], "transactions": [tx("a", move(0, 1, 3))]},
         {"balances": [5, 3], "states": ["committed"]}),
        ({"balances": [4, 2], "transactions": [tx("b", move(1, 0, 1))]},
         {"balances": [5, 1], "states": ["committed"]}),
        ({"balances": [5, 0], "transactions": [tx("a", move(0, 1, 3), move(0, 1, 4))]},
         {"balances": [5, 0], "states": ["rejected"]}),
        ({"balances": [5, 0], "transactions": [tx("a", move(0, 1, 9)), tx("a", move(0, 1, 2))]},
         {"balances": [3, 2], "states": ["rejected", "committed"]}),
        ({"balances": [5, 0], "transactions": [tx("a", move(0, 1, 2)), tx("a", move(0, 1, 3))]},
         {"balances": [3, 2], "states": ["committed", "duplicate"]}),
        ({"balances": [7], "transactions": [tx("b", move(0, 0, 5)), tx("c", move(0, 2, 0))]},
         {"balances": [7], "states": ["committed", "rejected"]}),
        ({"balances": [], "transactions": [tx("a"), tx("a"), tx("b", move(0, 0, 0))]},
         {"balances": [], "states": ["committed", "duplicate", "rejected"]}),
    ]
    schema = obj({"balances": arr(integer(), 5), "transactions": arr(obj({"id": word("abcde"),
        "moves": arr(obj({"src": integer(0, 5), "dst": integer(0, 5), "amount": integer()}), 5)}), 8)})
    prompt = ("Implement an atomic idempotent transfer journal. Process transactions in order, and moves within each "
        "transaction in order. A move rejects its entire transaction if either account index is absent or the source "
        "has insufficient balance at that step (including self-transfers). Rejection rolls back EVERY earlier move "
        "in that transaction. Only successful commits consume a transaction id; a previously committed id is a "
        "duplicate and ignores all its new moves. Empty transactions commit. Return balances and per-transaction "
        "states: committed/rejected/duplicate.")
    for variant in range(2):
        result.append(make("atomic-transfer-journal", variant, prompt, schema, reference, starter, ledger))

    reference = '''
    def run(data):
        events = {}
        for row in data['reservations']:
            if row['start'] >= row['end'] or row['units'] == 0:
                continue
            events[row['start']] = events.get(row['start'], 0) + row['units']
            events[row['end']] = events.get(row['end'], 0) - row['units']
        points = sorted(events)
        load, peak, segments = 0, 0, []
        for i in range(len(points) - 1):
            left, right = points[i], points[i + 1]
            load += events[left]
            peak = max(peak, load)
            if load > data['capacity']:
                if segments and segments[-1][1] == left and segments[-1][2] == load:
                    segments[-1][1] = right
                else:
                    segments.append([left, right, load])
        return {'peak': peak, 'overload': segments}
    '''
    starter = reference.replace("events.get(row['start'], 0) + row['units']", "row['units']").replace(
        "events.get(row['end'], 0) - row['units']", "-row['units']")

    def reservations(capacity, rows):
        return {"capacity": capacity, "reservations": [dict(zip(("start", "end", "units"), row)) for row in rows]}

    cases = [
        (reservations(2, [(0, 4, 3)]), {"peak": 3, "overload": [[0, 4, 3]]}),
        (reservations(5, [(1, 3, 2)]), {"peak": 2, "overload": []}),
        (reservations(2, [(0, 2, 3), (2, 4, 3)]), {"peak": 3, "overload": [[0, 4, 3]]}),
        (reservations(3, [(0, 5, 2), (0, 3, 4)]), {"peak": 6, "overload": [[0, 3, 6]]}),
        (reservations(3, [(-2, 2, 4), (0, 4, 2)]),
         {"peak": 6, "overload": [[-2, 0, 4], [0, 2, 6]]}),
        (reservations(0, [(3, 3, 9), (4, 1, 5), (0, 8, 0)]), {"peak": 0, "overload": []}),
        (reservations(3, [(0, 4, 3)]), {"peak": 3, "overload": []}),
        (reservations(1, [(0, 4, 2), (1, 3, 1)]),
         {"peak": 3, "overload": [[0, 1, 2], [1, 3, 3], [3, 4, 2]]}),
    ]
    schema = obj({"capacity": integer(), "reservations": arr(obj({"start": integer(-20, 20),
        "end": integer(-20, 20), "units": integer(0, 20)}))})
    prompt = ("Repair a reservation capacity sweep. Each reservation occupies the half-open interval [start,end) "
        "with its units. Ignore start>=end and zero units. Simultaneous starts/ends must be aggregated at the same "
        "instant. Return peak load (0 if empty) and sorted overload segments [start,end,load] where load is "
        "strictly greater than capacity. Output maximal adjacent segments with identical load, merging zero-net "
        "event boundaries. Negative times are legal; do not enumerate individual integer time ticks.")
    for variant in range(2):
        result.append(make("capacity-event-sweep", variant, prompt, schema, reference, starter, cases))

    reference = '''
    def run(data):
        maps = [{row['key']: row['value'] for row in data[name]} for name in ('base', 'left', 'right')]
        base, left, right = maps
        keys = sorted(set(base) | set(left) | set(right))
        merged, conflicts = [], []
        for key in keys:
            b, l, r = [(key in table, table.get(key)) for table in maps]
            if l == r:
                chosen = l
            elif l == b:
                chosen = r
            elif r == b:
                chosen = l
            else:
                conflicts.append(key)
                chosen = b
            if chosen[0]:
                merged.append({'key': key, 'value': chosen[1]})
        return {'merged': merged, 'conflicts': conflicts}
    '''
    starter = reference.replace("b, l, r = [(key in table, table.get(key)) for table in maps]",
        "b, l, r = [(True, table.get(key, 0)) for table in maps]")

    def records(pairs):
        return [{"key": key, "value": value} for key, value in pairs]

    def merge_case(base, left, right, merged, conflicts):
        return ({k: records(v) for k, v in zip(("base", "left", "right"), (base, left, right))},
                {"merged": records(merged), "conflicts": conflicts})

    cases = [
        merge_case([("a", 1)], [("a", 1)], [("a", 2)], [("a", 2)], []),
        merge_case([("b", 2)], [("b", 3)], [("b", 2)], [("b", 3)], []),
        merge_case([("a", 0)], [], [("a", 0)], [], []),
        merge_case([("a", 1)], [], [("a", 2)], [("a", 1)], ["a"]),
        merge_case([], [("b", 0)], [], [("b", 0)], []),
        merge_case([], [("a", 1)], [("a", 2)], [], ["a"]),
        merge_case([("c", 3), ("a", 1)], [("c", 4)], [("c", 4), ("a", 1)], [("c", 4)], []),
        merge_case([("a", 9)], [], [], [], []),
    ]
    entries = arr(obj({"key": word("abcde"), "value": integer(-20, 20)}), 5)
    prompt = ("Implement a three-way merge of flat key/value records. Each input list has unique keys. For each "
        "key in the union, missing is distinct from every integer including 0. If left equals right use it; "
        "otherwise if left equals base use right; otherwise if right equals base use left; otherwise record a "
        "conflict and keep base (including base absence). Absence means deletion. Return merged records sorted "
        "by key and conflicts sorted by key. Do not mutate or reorder input lists in place.")
    for variant in range(2):
        result.append(make("three-way-record-merge", variant, prompt, obj({k: deepcopy(entries) for k in
            ("base", "left", "right")}), reference, starter, cases))

    reference = '''
    def run(data):
        jobs = {row['id']: row for row in data['jobs']}
        done, result = {}, []
        windows = sorted((row['start'], row['end']) for row in data['blackouts'] if row['start'] < row['end'])
        while len(done) < len(jobs):
            ready = sorted(key for key, row in jobs.items() if key not in done and
                all(dependency in done for dependency in row['deps']))
            if not ready:
                return {'error': 'cycle'}
            key = ready[0]
            row = jobs[key]
            start = max([0] + [done[d] for d in row['deps']])
            if row['duration']:
                for a, b in windows:
                    if start < b and start + row['duration'] > a:
                        start = b
            done[key] = start + row['duration']
            result.append({'id': key, 'start': start, 'end': done[key]})
        return {'schedule': sorted(result, key=lambda row: row['id'])}
    '''
    starter = reference.replace("if start < b and start + row['duration'] > a:", "if a <= start < b:")

    def jobs(rows, windows=()):
        return {"jobs": [dict(zip(("id", "duration", "deps"), row)) for row in rows],
                "blackouts": [dict(zip(("start", "end"), row)) for row in windows]}

    def schedule(rows):
        return {"schedule": [dict(zip(("id", "start", "end"), row)) for row in rows]}

    cases = [
        (jobs([("a", 2, [])]), schedule([("a", 0, 2)])),
        (jobs([("b", 3, [])]), schedule([("b", 0, 3)])),
        (jobs([("a", 4, [])], [(2, 5)]), schedule([("a", 5, 9)])),
        (jobs([("a", 3, [])], [(2, 4), (5, 7)]), schedule([("a", 7, 10)])),
        (jobs([("a", 2, []), ("b", 3, ["a"]), ("c", 1, ["a", "b"])], [(3, 5)]),
         schedule([("a", 0, 2), ("b", 5, 8), ("c", 8, 9)])),
        (jobs([("a", 0, []), ("b", 2, [])], [(0, 2), (2, 4)]),
         schedule([("a", 0, 0), ("b", 4, 6)])),
        (jobs([("a", 1, ["b"]), ("b", 1, ["a"])]), {"error": "cycle"}),
        (jobs([("a", 2, [])], [(2, 5)]), schedule([("a", 0, 2)])),
        (jobs([]), schedule([])),
    ]
    prompt = ("Repair a precedence scheduler with a shared blackout calendar and unlimited parallel resources. "
        "All job ids are unique and all dependency ids exist. A job's earliest start is max(0, dependency finishes). "
        "Jobs are nonpreemptive; their half-open [start,start+duration) must not overlap any nonempty blackout. "
        "Shift forward to the earliest feasible start, including when a blackout begins DURING the job or a shift "
        "causes another overlap. Zero-duration jobs occupy no time and need not move. Blackouts may overlap or be "
        "unsorted; ignore start>=end. Return schedule sorted by id; any dependency cycle returns only error:cycle. "
        "No resource contention between jobs beyond dependencies and blackouts.")
    schema = obj({"jobs": arr(obj({"id": word("abcde"), "duration": integer(0, 20),
        "deps": arr(word("abcde"), 5)}), 5), "blackouts": arr(obj({"start": integer(0, 40), "end": integer(0, 40)}), 8)})
    for variant in range(2):
        result.append(make("dependency-blackout-scheduler", variant, prompt, schema, reference, starter, cases))
    return result
