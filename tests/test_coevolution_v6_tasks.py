"""New-task contract tests with independent host oracles and real OS isolation."""

import itertools
import json
import random
from copy import deepcopy

import pytest

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v5.core import feedback_packet, initial_rubric
from skillopt.coevolution_v6 import tasks as t
from skillopt.validator_pilot.api import digest

CALIBRATION = t.calibration_tasks()
DEVELOPMENT = t.development_tasks()
FINAL = t.final_coding_tasks()
ALL = CALIBRATION + DEVELOPMENT + FINAL


def native(adapter, files, public_only=False):
    return executor.evaluate(adapter.task, {"files": {path: files[path] for path in adapter.task.editable_paths}},
                             public_only=public_only)


def oracle(family, data):
    """Independent host calculations, not candidate/reference execution."""
    if family == "atomic-batch-rollback":
        path = [data["balance"] + sum(data["deltas"][:end]) for end in range(1, len(data["deltas"]) + 1)]
        bad = next((index for index, balance in enumerate(path) if balance < 0), None)
        return {"balance": data["balance"] if bad is not None else data["balance"] + sum(data["deltas"]),
                "committed": bad is None, "failed_index": bad}
    if family == "priority-topological-readiness":
        names = set(data["dependencies"])
        valid = [()]
        # Exhaustive valid prefixes, not another Kahn/ready-queue implementation.
        for size in range(1, len(names) + 1):
            for prefix in itertools.permutations(names, size):
                if all((set(data["dependencies"][name]) & names) <= set(prefix[:index])
                       for index, name in enumerate(prefix)):
                    valid.append(prefix)
        best = min(valid, key=lambda prefix: (-len(prefix), prefix))
        return {"order": list(best), "blocked": sorted(names - set(best))}
    if family == "per-key-expiration":
        output = []
        for position, event in enumerate(data["events"]):
            if event["kind"] == "get":
                writes = [i for i in range(position) if data["events"][i]["kind"] == "set"
                          and data["events"][i]["key"] == event["key"]]
                last = data["events"][max(writes)] if writes else None
                output.append(last["value"] if last and last["time"] + last["ttl"] - event["time"] > 0 else None)
        return output
    if family == "signed-inclusive-clipping":
        return [sorted([data["left"], value, data["right"]])[1] for value in data["values"]]
    if family == "missing-versus-null-merge":
        entries = list(data["base"].items()) + list(data["patch"].items())
        return {key: next(value for name, value in reversed(entries) if name == key) for key, _ in entries}
    if family == "stable-filtered-ranking":
        active = [(i, row) for i, row in enumerate(data["records"]) if row["active"]]
        by_rank = {}
        for index, row in active:
            rank = sum(other["score"] > row["score"] or other["score"] == row["score"] and pos < index
                       for pos, other in active)
            by_rank[rank] = row["id"]
        return [by_rank[rank] for rank in range(min(data["limit"], len(active)))]
    if family == "length-prefixed-frame-decoding":
        result, position = [], 0
        while position < len(data["stream"]):
            length = data["stream"][position]
            end = position + length + 1
            if length < 0 or end > len(data["stream"]):
                return {"frames": result, "error_index": position}
            result.append([data["stream"][index] for index in range(position + 1, end)])
            position = end
        return {"frames": result, "error_index": None}
    if family == "closed-interval-union":
        # Every integer/half-integer point in these integer-endpoint intervals;
        # connected runs exactly characterize their continuous closed union.
        occupied = sorted({point for pair in data["intervals"] for point in range(2 * min(pair), 2 * max(pair) + 1)})
        groups = []
        for point in occupied:
            if groups and point == groups[-1][-1] + 1:
                groups[-1].append(point)
            else:
                groups.append([point])
        return [[group[0] // 2, group[-1] // 2] for group in groups]
    if family == "delimiter-preserving-escaping":
        return "|".join("".join({"\\": "\\\\", "|": "\\|"}.get(character, character) for character in token)
                        for token in data["tokens"])
    if family == "invoice-local-extension":
        subtotal = sum(row["price"] for row in data["items"] for _ in range(row["quantity"]))
        result = {"subtotal": subtotal, "currency": data["currency"]}
        if data["operation"] == "discount":
            result["due"] = subtotal - min(subtotal, data["discount"])
        return result
    if family == "explicit-redacted-replacement":
        kinds = [event["kind"] for event in data["events"]]
        return {"counts": {key: sum(kind == key for kind in kinds) for key in kinds}, "total": len(kinds)}
    if family == "prime-prefix-summary":
        primes = [value for value in range(2, data["n"] + 1)
                  if sum(value % divisor == 0 for divisor in range(1, value + 1)) == 2]
        return {"count": len(primes), "sum": sum(primes)}
    raise AssertionError("Missing independent host oracle")


def test_twelve_structural_families_not_eighteen_independent_tasks():
    assert len(CALIBRATION) == 6 and len(DEVELOPMENT) == 3 and len(FINAL) == 9
    assert len({a.task.family for a in ALL}) == len({a.task.cluster_id for a in ALL}) == 12
    assert len({a.task.id for a in ALL}) == 18
    assert len({a.task.cluster_id for a in FINAL}) == 3
    assert {a.task.metadata["evaluation_group"] for a in FINAL} == {"same_mechanism", "near_miss", "unrelated"}
    assert {a.task.split for a in CALIBRATION} == {"promotion"}
    assert {a.task.split for a in DEVELOPMENT} == {"development"}
    assert {a.task.split for a in FINAL} == {"final"}


def test_all_calibration_artifacts_unique_across_families_and_variants():
    hashes = [digest(files) for adapter in CALIBRATION for files in adapter.task.metadata["controls"].values()]
    assert len(hashes) == len(set(hashes)) == 24
    for group in (CALIBRATION, DEVELOPMENT, FINAL):
        assert not {a.task.cluster_id for a in group} & {
            a.task.cluster_id for other in (CALIBRATION, DEVELOPMENT, FINAL) if other is not group for a in other}


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.task.id)
def test_literal_fixtures_independently_recalculated_and_legal(adapter):
    for case in adapter.task.public_cases + adapter.task.private_cases:
        assert adapter._input_valid(case["input"])
        assert oracle(adapter.task.family, case["input"]) == case["expected"]
        assert case["exception"] is None


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.task.id)
def test_reference_and_separate_equivalent_pass_real_sandbox(adapter):
    for name in ("reference", "equivalent"):
        result = native(adapter, adapter.task.metadata["controls"][name])
        assert result["hard"] is True, (name, result)
        assert result["execution_ok"] is True
        assert all(row["passed"] for row in result["case_results"])


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.task.id)
def test_both_bad_controls_rejected_by_independent_private_fixtures(adapter):
    for name in ("semantic_mutant", "preservation_mutant"):
        result = native(adapter, adapter.task.metadata["controls"][name])
        assert result["hard"] is False and result["execution_ok"] is True, (name, result)
        if name == "preservation_mutant":
            assert any(not row["passed"] and row["id"].endswith(":input_unchanged") for row in result["case_results"])


@pytest.mark.parametrize("adapter", CALIBRATION, ids=lambda a: a.task.family)
def test_public_tests_do_not_trivially_disclose_calibration_mutants(adapter):
    for name in ("semantic_mutant", "preservation_mutant"):
        assert native(adapter, adapter.task.metadata["controls"][name], public_only=True)["hard"] is True


@pytest.mark.parametrize("adapter", CALIBRATION, ids=lambda a: a.task.family)
def test_legal_differential_probes_can_independently_expose_hidden_defects(adapter):
    inputs = [case["input"] for case in adapter.task.private_cases]
    for name in ("semantic_mutant", "preservation_mutant"):
        rows = adapter.evaluate(adapter.task.metadata["controls"][name], initial_rubric(), phase="promotion",
                                public_only=True, extra_inputs=inputs)
        assert rows[0]["status"] == "pass" and rows[1]["status"] == "fail"
        assert rows[1]["verified"] is True


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.task.id)
def test_public_contract_is_visible_and_contains_no_oracle_or_group_labels(adapter):
    task = adapter.task
    public = task.public_task()
    contract = task.metadata["public_contract"]
    serialized = json.dumps(contract, ensure_ascii=False, sort_keys=True)
    assert serialized in public["prompt"]
    assert set(contract) == {"change_scope", "preserve_obligations", "supersedes_old_policy"}
    assert contract["change_scope"] in {"partial_update", "full_replacement", "read_only", "new_implementation"}
    assert contract["preserve_obligations"]
    assert contract["supersedes_old_policy"] == (contract["change_scope"] == "full_replacement")
    assert all(key not in public for key in ("metadata", "reference_files", "private_cases", "evaluation_group"))
    for case in task.private_cases:
        assert case["label"] not in json.dumps(public)
    assert "copy" not in task.files["api.py"]  # Mutation signal is not neutralized by wrapper copies.


def test_unrelated_standalone_implementation_is_not_mislabeled_read_only():
    for adapter in FINAL:
        task = adapter.task
        if task.metadata["evaluation_group"] == "unrelated":
            assert task.metadata["public_contract"]["change_scope"] == "new_implementation"
            assert "Implement the requested standalone computation; no prior behavior is being preserved or replaced." in task.prompt
            assert task.metadata["public_contract"]["supersedes_old_policy"] is False
    assert all(adapter.task.metadata["public_contract"]["change_scope"] == "read_only" for adapter in CALIBRATION)


@pytest.mark.parametrize("adapter", CALIBRATION + FINAL, ids=lambda a: a.task.id)
def test_reserved_phase_cannot_enter_skill_feedback(adapter):
    with pytest.raises(ValueError, match="phase"):
        adapter.evaluate(adapter.task.reference_files, initial_rubric(), phase="development")
    rows = adapter.evaluate(adapter.task.reference_files, initial_rubric(), phase=adapter.task.split)
    with pytest.raises(ValueError):
        feedback_packet(task_id=adapter.task.id, cluster_id=adapter.task.cluster_id, domain="coding",
                        assessments=rows, artifact=adapter.task.reference_files, contract=adapter.task.prompt)


def random_inputs(family, seed=17):
    rng = random.Random(seed)
    result = []
    for _ in range(30):
        if family == "atomic-batch-rollback":
            value = {"balance": rng.randrange(8), "deltas": [rng.randrange(-5, 6) for _ in range(rng.randrange(6))]}
        elif family == "priority-topological-readiness":
            names = list("abcd")[:rng.randrange(1, 5)]
            value = {"dependencies": {name: rng.sample(names + ["external"], rng.randrange(len(names) + 1)) for name in names}}
        elif family == "per-key-expiration":
            value = {"events": [{"kind": rng.choice(["set", "get"]), "key": rng.choice(["a", "b"]),
                                 "time": rng.randrange(5), "value": rng.randrange(-3, 4), "ttl": rng.randrange(4)}
                                for _ in range(rng.randrange(1, 8))]}
        elif family == "signed-inclusive-clipping":
            value = {"left": rng.randrange(-4, 5), "right": rng.randrange(-4, 5),
                     "values": [rng.randrange(-6, 7) for _ in range(rng.randrange(6))]}
        elif family == "missing-versus-null-merge":
            value = {field: {key: rng.choice([None, -1, 0, 2]) for key in rng.sample(list("abcd"), rng.randrange(5))}
                     for field in ("base", "patch")}
        elif family == "stable-filtered-ranking":
            value = {"records": [{"id": rng.choice(list("xyz")), "score": rng.randrange(-2, 3), "active": rng.choice([True, False])}
                                  for _ in range(rng.randrange(7))], "limit": rng.randrange(7)}
        elif family == "length-prefixed-frame-decoding":
            value = {"stream": [rng.randrange(-1, 4) for _ in range(rng.randrange(10))]}
        elif family == "closed-interval-union":
            value = {"intervals": [[rng.randrange(-3, 4), rng.randrange(-3, 4)] for _ in range(rng.randrange(6))]}
        elif family == "delimiter-preserving-escaping":
            value = {"tokens": ["".join(rng.choices("ab|\\", k=rng.randrange(6))) for _ in range(rng.randrange(5))]}
        else:
            raise AssertionError("Missing randomized family")
        result.append(value)
    return result


@pytest.mark.parametrize("adapter", CALIBRATION + DEVELOPMENT, ids=lambda a: a.task.family)
def test_thirty_generated_legal_inputs_against_independent_host_oracle(adapter):
    inputs = random_inputs(adapter.task.family)
    before = deepcopy(inputs)
    assert all(adapter._input_valid(value) for value in inputs)
    expected = [oracle(adapter.task.family, value) for value in inputs]
    for name in ("reference", "equivalent"):
        rows = executor.execute_inputs(adapter.task, adapter.task.metadata["controls"][name], inputs)
        assert len(rows) == 30 and all(row["ok"] and row["exception"] is None for row in rows)
        assert all(row["input_unchanged"] is True for row in rows)
        assert [row["value"] for row in rows] == expected
    assert before == inputs


def test_builders_return_independent_copies_and_do_not_alias_protected_modules():
    left, right = t.calibration_tasks(), t.calibration_tasks()
    left[0].task.metadata["controls"]["reference"]["logic.py"] = "mutated"
    assert right[0].task.metadata["controls"]["reference"]["logic.py"] != "mutated"
    assert left[0].task.reference_files["logic.py"] != "mutated"
