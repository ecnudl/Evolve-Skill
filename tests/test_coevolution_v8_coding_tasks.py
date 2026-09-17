"""Independent development-fixture checks; no model or historical final data.

Host oracles intentionally use different algorithms from the frozen task
references. Candidate/reference execution stays inside the existing OS sandbox.
These are correctness tests, not evidence that feedback or Skills improve an LLM.
"""

import itertools
import json
import random
from collections import Counter
from copy import deepcopy

import pytest

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v8 import coding_tasks as t
from skillopt.validator_pilot.api import digest

FAMILIES = (
    "atomic-transfer-journal",
    "capacity-event-sweep",
    "three-way-record-merge",
    "dependency-blackout-scheduler",
)


@pytest.fixture(scope="module")
def panel():
    return t.development_coding_tasks()


def oracle(family, data):
    """Recalculate semantics without importing or executing a reference module."""
    if family == FAMILIES[0]:
        balances, consumed, states = list(data["balances"]), set(), []
        for transaction in data["transactions"]:
            key = transaction["id"]
            if key in consumed:
                states.append("duplicate")
                continue
            moves = transaction["moves"]
            valid = True
            for index, move in enumerate(moves):
                if max(move["src"], move["dst"]) >= len(balances):
                    valid = False
                    break
                # Balance before this move comes from the *original* account
                # balance and prefix cash flows, not an in-place simulation.
                available = balances[move["src"]] + sum(
                    prior["amount"] * (int(prior["dst"] == move["src"]) - int(prior["src"] == move["src"]))
                    for prior in moves[:index]
                )
                if available < move["amount"]:
                    valid = False
                    break
            if not valid:
                states.append("rejected")
                continue
            balances = [balance + sum(
                move["amount"] * (int(move["dst"] == account) - int(move["src"] == account))
                for move in moves
            ) for account, balance in enumerate(balances)]
            consumed.add(key)
            states.append("committed")
        return {"balances": balances, "states": states}

    if family == FAMILIES[1]:
        bookings = [r for r in data["reservations"] if r["start"] < r["end"] and r["units"] > 0]
        boundaries = sorted({r[k] for r in bookings for k in ("start", "end")})
        # Direct interval membership avoids the reference's event accumulator.
        intervals = [(left, right, sum(r["units"] for r in bookings if r["start"] <= left < r["end"]))
                     for left, right in zip(boundaries, boundaries[1:])]
        over = []
        for left, right, load in intervals:
            if load <= data["capacity"]:
                continue
            if over and over[-1][1] == left and over[-1][2] == load:
                over[-1][1] = right
            else:
                over.append([left, right, load])
        return {"peak": max([0] + [load for _, _, load in intervals]), "overload": over}

    if family == FAMILIES[2]:
        maps = [{row["key"]: row["value"] for row in data[k]} for k in ("base", "left", "right")]
        missing = object()
        merged, conflicts = [], []
        for key in sorted(set().union(*(set(table) for table in maps))):
            base, left, right = (table.get(key, missing) for table in maps)
            changed = [value for value in (left, right) if value != base]
            conflict = len(changed) == 2 and changed[0] != changed[1]
            chosen = base if conflict or not changed else changed[0]
            if conflict:
                conflicts.append(key)
            if chosen is not missing:
                merged.append({"key": key, "value": chosen})
        return {"merged": merged, "conflicts": conflicts}

    if family == FAMILIES[3]:
        jobs = {row["id"]: row for row in data["jobs"]}
        visiting, complete = set(), {}

        def solve(key):
            if key in visiting:
                raise ValueError("cycle")
            if key in complete:
                return complete[key]["end"]
            visiting.add(key)
            row = jobs[key]
            lower = max([0] + [solve(dep) for dep in row["deps"]])
            # Integer inputs guarantee an integer earliest start. Exhaustive
            # candidate times are independent of the reference's sorted sweep.
            for start in range(lower, lower + 101):
                end = start + row["duration"]
                occupied = row["duration"] > 0 and any(
                    start < window["end"] and end > window["start"]
                    for window in data["blackouts"] if window["start"] < window["end"]
                )
                if not occupied:
                    break
            else:
                raise AssertionError("test oracle bound exceeded")
            complete[key] = {"id": key, "start": start, "end": end}
            visiting.remove(key)
            return end

        try:
            for key in jobs:
                solve(key)
        except ValueError as exc:
            assert str(exc) == "cycle"
            return {"error": "cycle"}
        return {"schedule": [complete[key] for key in sorted(complete)]}
    raise ValueError("unknown development family")


def native(adapter, files, *, public_only=False):
    return executor.evaluate(adapter.task, {"files": {p: files[p] for p in adapter.task.editable_paths}},
                             public_only=public_only)


def ledger(balances, transactions):
    return {"balances": balances, "transactions": [
        {"id": key, "moves": [{"src": src, "dst": dst, "amount": amount} for src, dst, amount in moves]}
        for key, moves in transactions]}


def reservations(capacity, rows):
    return {"capacity": capacity, "reservations": [
        {"start": start, "end": end, "units": units} for start, end, units in rows]}


def records(rows):
    return [{"key": key, "value": value} for key, value in rows]


def jobs(rows, windows=()):
    return {"jobs": [{"id": key, "duration": duration, "deps": deps} for key, duration, deps in rows],
            "blackouts": [{"start": start, "end": end} for start, end in windows]}


def test_eight_variants_are_four_independent_development_families(panel):
    assert len(panel) == len({a.task.id for a in panel}) == 8
    assert Counter(a.task.family for a in panel) == dict.fromkeys(FAMILIES, 2)
    assert sorted(Counter(a.task.cluster_id for a in panel).values()) == [2, 2, 2, 2]
    assert all(a.domain == "coding" and a.task.split == "development" for a in panel)
    for first, second in zip(panel[::2], panel[1::2]):
        assert first.task.cluster_id == second.task.cluster_id
        assert first.task.files == second.task.files
        assert first.task.reference_files == second.task.reference_files
        assert first.task.public_cases != second.task.public_cases
        for adapter in (first, second):
            task = adapter.task
            assert task.metadata["historical_final_assets_used"] is False
            assert task.metadata["independence_unit"] == "project_family"
            assert len(task.public_cases) == 1 and len(task.private_cases) >= 5
            assert task.editable_paths == ["logic.py"]
            assert task.files["api.py"] == task.reference_files["api.py"]


@pytest.mark.parametrize("index", range(8))
def test_literal_gold_is_schema_legal_and_independently_correct(panel, index):
    adapter = panel[index]
    cases = adapter.task.public_cases + adapter.task.private_cases
    assert len({case["label"] for case in cases}) == len(cases)
    assert len({digest(case["input"]) for case in cases}) == len(cases)
    for case in cases:
        before = deepcopy(case["input"])
        assert adapter._input_valid(before), case["label"]
        assert oracle(adapter.task.family, before) == case["expected"], case["label"]
        assert before == case["input"]
        assert case["exception"] is None


@pytest.mark.parametrize("index", range(8))
def test_reference_passes_all_oracles_and_starter_has_real_semantic_defect(panel, index):
    adapter = panel[index]
    reference = native(adapter, adapter.task.reference_files)
    assert reference["execution_ok"] and reference["artifact_execution_ok"]
    assert reference["correct"] is True
    starter = native(adapter, adapter.task.files)
    assert starter["execution_ok"] and starter["artifact_execution_ok"]
    assert starter["correct"] is False and starter["hard"] is False
    # Coding public examples intentionally do not expose the planted defect.
    # Unlike native tasks, a parseable artifact can need no public-error repair.
    assert starter["public_pass"] is True
    assert any(not row["passed"] and row["id"].endswith(":behavior") for row in starter["case_results"])
    assert all(row["passed"] for row in starter["case_results"] if row["id"].endswith(":input_unchanged"))


def test_public_task_has_no_private_cases_or_reference_or_cluster_label(panel):
    for adapter in panel:
        public = adapter.public_task()
        assert not {"private_cases", "reference_files", "metadata", "family", "cluster_id"}.intersection(public)
        assert public["public_cases"] == adapter.task.public_cases
        assert all(case["label"] not in json.dumps(public) for case in adapter.task.private_cases)
        public["files"]["api.py"] = "changed public copy"
        assert adapter.task.files["api.py"] == t.ENTRY


def test_schema_rejects_missing_extra_out_of_bounds_or_wrong_primitive_types(panel):
    for adapter in panel:
        example = deepcopy(adapter.task.public_cases[0]["input"])
        missing = deepcopy(example)
        del missing[next(iter(missing))]
        assert not adapter._input_valid(missing)
        assert not adapter._input_valid({**example, "hidden_expected": 0})
        assert not adapter._input_valid([])
    assert not panel[0]._input_valid(ledger([-1], []))
    assert not panel[0]._input_valid(ledger([True], []))
    assert not panel[2]._input_valid(reservations(0, [(-21, 2, 1)]))
    assert not panel[2]._input_valid(reservations(0, [(0, 21, 1)]))
    assert not panel[4]._input_valid({k: records([("z", 0)]) for k in ("base", "left", "right")})
    assert not panel[6]._input_valid(jobs([("a", 21, [])]))


@pytest.mark.parametrize("data,expected", [
    (ledger([5, 0], [("a", [(0, 1, 3), (1, 0, 4)]), ("a", [(0, 1, 2)])]),
     {"balances": [3, 2], "states": ["rejected", "committed"]}),
    (ledger([2], [("a", [(0, 0, 3)]), ("a", [(0, 0, 2)]), ("a", [(5, 5, 100)])]),
     {"balances": [2], "states": ["rejected", "committed", "duplicate"]}),
    (ledger([0, 4], [("b", [(1, 0, 4), (0, 1, 4)])]),
     {"balances": [0, 4], "states": ["committed"]}),
    (ledger([], [("a", []), ("a", []), ("b", [(0, 0, 0)])]),
     {"balances": [], "states": ["committed", "duplicate", "rejected"]}),
])
def test_ledger_hand_values_cover_rollback_retry_self_transfer_and_duplicate(data, expected):
    assert oracle(FAMILIES[0], data) == expected


@pytest.mark.parametrize("data,expected", [
    (reservations(2, [(0, 2, 3), (2, 5, 3)]), {"peak": 3, "overload": [[0, 5, 3]]}),
    (reservations(2, [(-2, 0, 2), (0, 3, 4), (0, 1, 2)]),
     {"peak": 6, "overload": [[0, 1, 6], [1, 3, 4]]}),
    (reservations(0, [(0, 0, 20), (4, -3, 10), (-20, 20, 0)]), {"peak": 0, "overload": []}),
    (reservations(2, [(0, 2, 2)]), {"peak": 2, "overload": []}),
])
def test_sweep_hand_values_cover_aggregates_half_open_and_strict_capacity(data, expected):
    assert oracle(FAMILIES[1], data) == expected


@pytest.mark.parametrize("base,left,right,expected,conflicts", [
    ([("a", 0)], [], [("a", 0)], [], []),
    ([("a", 0)], [], [("a", 2)], [("a", 0)], ["a"]),
    ([], [("a", 0)], [], [("a", 0)], []),
    ([], [("a", 1)], [("a", 2)], [], ["a"]),
    ([("b", 3), ("a", 1)], [("a", 2)], [("b", 4), ("a", 2)], [("a", 2), ("b", 3)], ["b"]),
])
def test_merge_hand_values_distinguish_absence_zero_and_conflicting_deletion(base, left, right, expected, conflicts):
    data = {k: records(value) for k, value in zip(("base", "left", "right"), (base, left, right))}
    assert oracle(FAMILIES[2], data) == {"merged": records(expected), "conflicts": conflicts}


@pytest.mark.parametrize("data,expected", [
    (jobs([("a", 3, [])], [(5, 7), (2, 4)]), {"schedule": [{"id": "a", "start": 7, "end": 10}]}),
    (jobs([("a", 0, []), ("b", 2, [])], [(0, 2), (2, 4)]),
     {"schedule": [{"id": "a", "start": 0, "end": 0}, {"id": "b", "start": 4, "end": 6}]}),
    (jobs([("a", 2, []), ("b", 2, []), ("c", 1, ["a", "b"])], [(3, 5)]),
     {"schedule": [{"id": "a", "start": 0, "end": 2}, {"id": "b", "start": 0, "end": 2},
                   {"id": "c", "start": 2, "end": 3}]}),
    (jobs([("a", 1, ["b"]), ("b", 0, ["a"])]), {"error": "cycle"}),
    (jobs([("a", 2, [])], [(1, 3), (2, 8), (8, 9), (4, 4)]),
     {"schedule": [{"id": "a", "start": 9, "end": 11}]}),
])
def test_scheduler_hand_values_cover_overlap_chains_parallelism_cycles_and_zero_duration(data, expected):
    assert oracle(FAMILIES[3], data) == expected


def generated_inputs(family):
    """Fixed pre-model input grid; never selected after observing performance."""
    rng = random.Random(20260913)
    if family == FAMILIES[0]:
        return [ledger([rng.randrange(6) for _ in range(rng.randrange(4))], [
            (rng.choice("abc"), [(rng.randrange(5), rng.randrange(5), rng.randrange(8))
                                 for _ in range(rng.randrange(4))])
            for _ in range(rng.randrange(7))]) for _ in range(120)]
    if family == FAMILIES[1]:
        return [reservations(rng.randrange(8), [
            (rng.randrange(-3, 6), rng.randrange(-3, 6), rng.randrange(5))
            for _ in range(rng.randrange(8))]) for _ in range(120)]
    if family == FAMILIES[2]:
        # Exhaustive single-key presence/value triples, including -1 and zero.
        return [{k: ([] if value is None else [{"key": "a", "value": value}])
                 for k, value in zip(("base", "left", "right"), triple)}
                for triple in itertools.product((None, -1, 0, 2), repeat=3)]
    if family == FAMILIES[3]:
        rows = []
        for _ in range(120):
            keys = list("abcde"[:rng.randrange(6)])
            tasks = [(key, rng.randrange(6), [dep for dep in keys if rng.random() < 0.15]) for key in keys]
            windows = [(rng.randrange(9), rng.randrange(9)) for _ in range(rng.randrange(6))]
            rows.append(jobs(tasks, windows))
        return rows
    raise ValueError("unknown family")


@pytest.mark.parametrize("family", FAMILIES)
def test_reference_in_os_sandbox_matches_independent_fixed_grid_and_preserves_inputs(panel, family):
    adapter = next(a for a in panel if a.task.family == family)
    inputs = generated_inputs(family)
    before = deepcopy(inputs)
    assert all(adapter._input_valid(value) for value in inputs)
    # Generated job dependencies and merge keys additionally satisfy constraints
    # described in the prompt, which this simple JSON schema cannot express.
    actual = executor.execute_inputs(adapter.task, adapter.task.reference_files, inputs)
    assert len(actual) == len(inputs)
    for data, row in zip(inputs, actual):
        assert row["ok"] and row["exception"] is None, row
        assert row["value"] == oracle(family, data)
        assert row["input_unchanged"] is True
    assert inputs == before


def test_panel_builds_are_deterministic_and_not_mutably_shared(panel):
    other = t.development_coding_tasks()
    assert [a.task.to_dict() for a in other] == [a.task.to_dict() for a in panel]
    other[0].task.files["logic.py"] = "changed"
    other[0].task.public_cases[0]["input"]["balances"][0] = 999
    assert other[1].task.files["logic.py"] == panel[1].task.files["logic.py"]
    assert panel[0].task.public_cases[0]["input"]["balances"][0] == 8


def test_protected_file_cannot_be_replaced_even_with_reference_bytes(panel):
    for adapter in panel:
        with pytest.raises(ValueError, match="protected"):
            executor.parse_patch(adapter.task, {"files": adapter.task.reference_files})

