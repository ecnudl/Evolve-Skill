"""Synthetic compiler boundaries; generated Python is never executed on host."""
import ast
import hashlib
import json
import threading
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import curriculum_tasks as curriculum
from skillopt.skill_validation.models import ArtifactRecord, SourceFile
from skillopt.skill_validation.checks import ExecutionCache, validate_callable
from skillopt.skill_validation.public_revision import _parts
from skillopt.skill_validation.research import fixed_rubric
from skillopt.validator_pilot.api import digest


SPEC = {"steps": [{"op": "filter", "kind": "nonzero"}, {"op": "map", "kind": "abs"},
                  {"op": "reorder", "kind": "unique_stable"}], "aggregate": "weighted_sum"}


class ScriptedExecutor:
    identity = {"fixture_executor": "curriculum-test", "real_execution": False}

    def __init__(self, *, unavailable=False, rejection=False, returns=True, state=True):
        self.calls = 0
        self.unavailable, self.rejection, self.returns, self.state = unavailable, rejection, returns, state

    def run(self, files, module, function, args, kwargs):
        # Fabricated fixture receipt only: no eval/exec of source, no subprocess.
        self.calls += 1
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        if module == "screen":
            count = len(curriculum._audit_inputs()) + 1  # first four-element public example is extra
            actual = {"reference_agreement": not self.rejection, "contract_states_valid": True,
                      "wrong_return_detected": True, "wrong_state_detected": True, "nonconstant_return": True,
                      "public_wrappers_valid": True, "public_mutants_detected": True,
                      "comparisons": count * 3, "inputs": count, "roles": 3}
        else:
            actual = {"cases": [{"return_pass": self.returns, "state_pass": self.state, "exception": None}
                                for _ in curriculum._audit_inputs()]}
        return seal({"status": "unsupported" if self.unavailable else "observed", "actual": actual,
                     "exception": None, "executor_identity": self.identity,
                     "input_hash": digest({"files": files, **call}), "source_hash": digest(files),
                     "call_hash": digest(call), "fixture_only": True})


def _artifact(row, *, unavailable=False, repeat=0):
    return ArtifactRecord(row["task"].contract.content_hash, repeat, "no_skill", "none",
        hashlib.sha256(b"").hexdigest(), () if unavailable else (SourceFile("solution.py", "# never executed fixture"),),
        "parse_failure" if unavailable else "available", "fixture", True, False, "fixture:curriculum", digest("fixture"))


def test_strict_model_spec_is_not_code_or_expected_answer():
    raw = json.dumps({"families": [SPEC]})
    assert curriculum.parse_families(raw, 2, expected_count=1) == [SPEC]
    for added in ({"expected": 999}, {"code": "arbitrary()"}, {"wording": "new task"}, {"constant": 6}):
        with pytest.raises(ValueError):
            curriculum.parse_families(json.dumps({"families": [{**SPEC, **added}]}))
    with pytest.raises(ValueError, match="Duplicate"):
        curriculum.parse_families('{"families":[],"families":[]}')


@pytest.mark.parametrize("spec", [
    {"steps": [], "aggregate": "sum"},
    {"steps": [{"op": "map", "kind": "square"}], "aggregate": "sum"},
    {"steps": [{"op": "map", "kind": "square"}] * 2, "aggregate": "sum"},
    {"steps": [{"op": "map", "kind": "square"}, {"op": "exec", "kind": "code"}], "aggregate": "sum"},
    {"steps": [{"op": "filter", "kind": "even"}, {"op": "filter", "kind": "odd"}], "aggregate": "sum"},
    {"steps": [{"op": "reorder", "kind": "ascending"}, {"op": "reorder", "kind": "descending"}], "aggregate": "sum"},
    {"steps": [{"op": "map", "kind": "abs"}, {"op": "filter", "kind": "positive"}], "aggregate": "eval"},
])
def test_invalid_or_degenerate_structural_spec_rejected(spec):
    with pytest.raises(ValueError):
        curriculum.compile_family(spec, "development")


def test_generation_count_is_not_padded_and_aliases_not_new_families():
    with pytest.raises(ValueError, match="Incomplete"):
        curriculum.parse_families(json.dumps({"families": [SPEC]}), 3, expected_count=2)
    with pytest.raises(ValueError, match="Duplicate structural"):
        curriculum.parse_families(json.dumps({"families": [SPEC, deepcopy(SPEC)]}), 2)
    reordered_keys = {"aggregate": SPEC["aggregate"], "steps": [dict(reversed(list(s.items()))) for s in SPEC["steps"]]}
    assert curriculum.family_fingerprint(reordered_keys) == curriculum.family_fingerprint(SPEC)


def test_finite_behavior_signature_catches_different_structural_aliases():
    left = {"steps": [{"op": "map", "kind": "abs"}, {"op": "filter", "kind": "positive"}], "aggregate": "sum"}
    right = {"steps": [{"op": "filter", "kind": "nonzero"}, {"op": "map", "kind": "abs"}], "aggregate": "sum"}
    assert curriculum.family_fingerprint(left) != curriculum.family_fingerprint(right)
    assert curriculum.behavior_fingerprint(left) == curriculum.behavior_fingerprint(right)
    assert curriculum.behavior_fingerprint(left) == curriculum.behavior_fingerprint(deepcopy(left))


def test_behavior_signature_includes_state_not_only_return_value():
    left = {"steps": [{"op": "filter", "kind": "positive"}, {"op": "reorder", "kind": "ascending"}], "aggregate": "sum"}
    right = {"steps": [{"op": "filter", "kind": "positive"}, {"op": "reorder", "kind": "descending"}], "aggregate": "sum"}
    assert all(curriculum._evaluate(left, values)[0] == curriculum._evaluate(right, values)[0]
               for values in curriculum._audit_inputs())
    assert curriculum.behavior_fingerprint(left) != curriculum.behavior_fingerprint(right)


def test_canonical_family_roles_share_structure_across_partition_but_not_contract_hash():
    development = curriculum.compile_family(SPEC, "development")
    heldout = curriculum.compile_family(SPEC, "skill_confirmation")
    assert len(development) == 3
    assert {row["host_only"]["role"] for row in development} == set(curriculum.ROLES)
    assert len({row["task"].contract.family_id for row in development + heldout}) == 1
    assert all(a["task"].contract.content_hash != b["task"].contract.content_hash for a, b in zip(development, heldout))
    assert all(row["family_origin"] == "synthetic_generated_spec" for row in development)
    assert all(row["host_only"]["semantic_family_independence_certified"] is False for row in development)
    for row in development:
        task, public_task, wrapper = _parts(row)
        assert task.contract == public_task.contract and task.function == "solve"
        assert wrapper.path == "public_runner.py"
        assert "public_learning_goal" not in task.contract.prompt
        assert "near_miss" not in task.contract.prompt and "targeted" not in task.contract.prompt


def test_contract_and_public_wrapper_cover_return_and_explicit_mutation():
    preserve, inplace, unconstrained = curriculum.compile_family(SPEC, "development")
    assert "input_preservation" in {o.kind for o in preserve["task"].contract.obligations}
    assert next(o for o in preserve["task"].contract.obligations if o.kind == "input_preservation").critical is False
    assert "input_preservation" not in {o.kind for o in inplace["task"].contract.obligations}
    assert "input_preservation" not in {o.kind for o in unconstrained["task"].contract.obligations}
    assert "same input list" in inplace["task"].contract.prompt
    assert "mutation is permitted but not required" in unconstrained["task"].contract.prompt
    for row in (preserve, inplace, unconstrained):
        wrapper = row["public_wrapper"]["content"]
        assert "return_pass" in wrapper and "state_pass" in wrapper
        assert "case['transformed']" in wrapper and "case['input']" in wrapper
        assert "type(result) is int" in wrapper


@pytest.mark.parametrize("role_index,combined_pass", [(0, True), (0, False), (1, True), (1, False)])
def test_registered_joint_wrapper_boolean_reaches_fixed_feedback_without_fake_state_observation(role_index, combined_pass):
    row = curriculum.compile_family(SPEC, "development")[role_index]
    class PublicReceipt(ScriptedExecutor):
        def run(self, files, module, function, args, kwargs):
            value = super().run(files, module, function, args, kwargs)
            payload = {key: item for key, item in value.items() if key != "record_hash"}
            return seal({**payload, "actual": combined_pass})
    report = validate_callable(row["public_task"], _artifact(row), fixed_rubric(), ExecutionCache(PublicReceipt()))
    assert report["status"] == ("pass" if combined_pass else "fail")
    if role_index == 0:
        assert report["obligations"]["input_preservation"] == "unknown"
        assert all(check["method"] != "input_state" for check in report["checks"])


def test_host_oracle_derives_examples_from_fixed_semantics_not_model_expected():
    assert curriculum._evaluate(SPEC, [2, -1, 2, 0]) == (4, [2, 1])
    assert curriculum._evaluate(SPEC, []) == (0, [])
    ascending = {"steps": [{"op": "filter", "kind": "odd"}, {"op": "reorder", "kind": "ascending"}],
                 "aggregate": "alternating_sum"}
    assert curriculum._evaluate(ascending, [3, -1, 2, -3]) == (1, [-3, -1, 3])
    assert json.loads(curriculum.compile_family(SPEC, "development")[0]["task"].public_cases[0].expected_json) == 4


@pytest.mark.parametrize("value", [-531441, -729, -65, -64, -63, -28, -27, -26, -10, -9, -8, -7,
                                   -2, -1, 0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 26, 27, 28, 63, 64, 65,
                                   80, 81, 82, 728, 729, 730, 531440, 531441])
def test_exact_integer_power_boundaries_against_independent_finite_sets(value):
    squares = {root * root for root in range(730)}
    cubes = {root * root * root for root in range(-81, 82)}
    assert curriculum._perfect_integer_power(value, 2) is (value in squares)
    assert curriculum._perfect_integer_power(value, 3) is (value in cubes)


@pytest.mark.parametrize("value,power", [(True, 2), (1.0, 2), ("8", 3), (8, 1), (8, True)])
def test_power_predicate_does_not_coerce_floats_booleans_or_unregistered_powers(value, power):
    with pytest.raises(ValueError):
        curriculum._perfect_integer_power(value, power)


def test_signed_cube_zero_and_negative_square_semantics_survive_composition():
    values = [-9, -8, -1, 0, 1, 4, 8, 9]
    cubes = {"steps": [{"op": "filter", "kind": "perfect_cube"}, {"op": "map", "kind": "negate"}], "aggregate": "count"}
    squares = {"steps": [{"op": "filter", "kind": "perfect_square"}, {"op": "map", "kind": "negate"}], "aggregate": "sum"}
    mapped = {"steps": [{"op": "map", "kind": "cube"}, {"op": "filter", "kind": "perfect_square"}], "aggregate": "sum"}
    assert curriculum._evaluate(cubes, values) == (5, [8, 1, 0, -1, -8])
    assert curriculum._evaluate(squares, values) == (-14, [0, -1, -4, -9])
    assert curriculum._evaluate(mapped, values) == (794, [0, 1, 64, 729])
    assert curriculum.parse_families(json.dumps({"families": [cubes, squares, mapped]}), 3, expected_count=3)


def test_cube_map_and_three_step_maximum_stay_integer_bounded():
    spec = {"steps": [{"op": "map", "kind": "cube"}, {"op": "map", "kind": "square"},
                      {"op": "map", "kind": "negate"}], "aggregate": "sum"}
    value, transformed = curriculum._evaluate(spec, [-9, 0, 9])
    assert transformed == [-531441, 0, -531441] and value == -1062882
    assert all(type(item) is int for item in transformed)
    for row in curriculum.compile_family(spec, "development"):
        ast.parse(row["host_only"]["reference_a"])
        ast.parse(row["host_only"]["reference_b"])


def test_power_references_use_distinct_integer_algorithms_and_no_float_root():
    spec = {"steps": [{"op": "map", "kind": "cube"}, {"op": "filter", "kind": "perfect_square"}], "aggregate": "sum"}
    for row in curriculum.compile_family(spec, "development"):
        a, b = row["host_only"]["reference_a"], row["host_only"]["reference_b"]
        assert "_binary_power" in a and "_enumerated_power" not in a
        assert "_enumerated_power" in b and "_binary_power" not in b
        assert "root += 1" in b and "middle = (low + high) // 2" in a
        for source in (a, b):
            tree = ast.parse(source)  # Parse only; generated source is never host-executed.
            assert not any(isinstance(node, ast.Constant) and type(node.value) is float for node in ast.walk(tree))
            assert not any(isinstance(node, ast.Div) for node in ast.walk(tree))


def test_v2_audit_inputs_include_all_domain_singletons_and_signed_cube_boundary():
    inputs = curriculum._audit_inputs()
    assert curriculum.VERSION == "synthetic-list-curriculum-v2"
    assert all([value] in inputs for value in range(-9, 10))
    assert [-9, -8, -1, 0, 1, 4, 8, 9] in inputs
    assert len(inputs) == len({tuple(values) for values in inputs}) == 175
    spec = {"steps": [{"op": "filter", "kind": "perfect_cube"}, {"op": "map", "kind": "negate"}], "aggregate": "count"}
    row = curriculum.compile_family(spec, "development")[0]
    assert "negative cubes and zero qualify" in row["task"].contract.prompt
    assert len(row["task"].public_cases) == 4


def test_all_generated_python_parses_but_is_never_executed_on_host():
    specs = []
    for op, kinds in curriculum.OPERATIONS.items():
        for kind in kinds:
            other = {"op": "filter", "kind": "positive"} if op != "filter" else {"op": "map", "kind": "abs"}
            specs.append({"steps": [{"op": op, "kind": kind}, other], "aggregate": "weighted_sum"})
    for spec in specs:
        for row in curriculum.compile_family(spec, "development"):
            sources = [row["public_wrapper"]["content"], row["host_only"]["audit_runner"],
                       row["host_only"]["reference_a"], row["host_only"]["reference_b"]]
            for source in sources:
                ast.parse(source)
            assert sources[2] != sources[3]
    assert len(curriculum._audit_inputs()) == 175
    assert [] in curriculum._audit_inputs() and [0] * 8 in curriculum._audit_inputs()


def test_generator_views_are_symmetric_except_optional_public_goal_and_exclusions():
    fingerprint = curriculum.family_fingerprint(SPEC)
    left, left_user = curriculum.generate_messages("Respect explicit mutation contracts", [fingerprint], 4,
                                                   excluded_specs=[SPEC])
    right, right_user = curriculum.generate_messages(None, [fingerprint], 4, "generic", excluded_specs=[SPEC])
    assert left == right
    left_data, right_data = json.loads(left_user), json.loads(right_user)
    assert left_data.pop("public_learning_goal") == "Respect explicit mutation contracts"
    assert right_data.pop("public_learning_goal") is None
    assert left_data == right_data
    with pytest.raises(ValueError, match="Generic"):
        curriculum.generate_messages("leak", [], 1, "generic")
    with pytest.raises(ValueError, match="match registered"):
        curriculum.generate_messages(None, [], 1, "generic", excluded_specs=[SPEC])


def test_screen_fixture_is_not_formal_calibration_and_replays_same_receipt(tmp_path):
    executor = ScriptedExecutor()
    first = curriculum.screen_family(SPEC, executor, tmp_path)
    assert first["status"] == "qualified" and not first["formal_eligible"]
    assert not first["deployment_authorized"]
    assert first["receipt"]["engineering_fixture_only"]
    assert first["qualification"]["comparisons"] == 528
    second = curriculum.screen_family(SPEC, executor, tmp_path)
    assert first == second and executor.calls == 1


@pytest.mark.parametrize("kwargs,status", [({"unavailable": True}, "unknown"), ({"rejection": True}, "rejected")])
def test_screen_infrastructure_and_reference_disagreement_are_distinct(tmp_path, kwargs, status):
    result = curriculum.screen_family(SPEC, ScriptedExecutor(**kwargs), tmp_path)
    assert result["status"] == status and not result["formal_eligible"]


@pytest.mark.parametrize("returns,state,expected", [(True, True, "pass"), (False, True, "fail"), (True, False, "fail")])
def test_audit_keeps_all_inputs_and_separate_return_state_outcomes(tmp_path, returns, state, expected):
    row = curriculum.compile_family(SPEC, "development")[0]
    artifact = _artifact(row)
    executor = ScriptedExecutor(returns=returns, state=state)
    result = curriculum.audit_artifact(row, artifact, executor, tmp_path)
    assert result["status"] == expected and len(result["audit_inputs"]) == len(result["audit_outcomes"]) == 175
    assert result["return_status"] == ("pass" if returns else "fail")
    assert result["state_status"] == ("pass" if state else "fail")
    assert result["artifact_hash"] == artifact.content_hash
    assert result["receipt"]["request"]["bindings"]["artifact_record_hash"] == artifact.content_hash
    assert result == curriculum.audit_artifact(row, artifact, executor, tmp_path)
    assert executor.calls == 1
    other = replace(artifact, repeat=1)
    curriculum.audit_artifact(row, other, executor, tmp_path)
    assert executor.calls == 2  # repeat/condition identity cannot silently share its receipt


def test_undelivered_artifact_and_unsupported_runtime_remain_unknown(tmp_path):
    row = curriculum.compile_family(SPEC, "development")[0]
    executor = ScriptedExecutor()
    result = curriculum.audit_artifact(row, _artifact(row, unavailable=True), executor, tmp_path)
    assert result["status"] == "unknown" and result["audit_outcomes"] is None and executor.calls == 0
    unsupported = curriculum.audit_artifact(row, _artifact(row), ScriptedExecutor(unavailable=True), tmp_path)
    assert unsupported["status"] == unsupported["return_status"] == unsupported["state_status"] == "unknown"


def test_changed_task_or_host_oracle_is_rejected(tmp_path):
    row = curriculum.compile_family(SPEC, "development")[0]
    artifact = _artifact(row)
    changed = deepcopy(row)
    changed["host_only"]["audit_runner"] += "\n# changed answer"
    with pytest.raises(ValueError, match="frozen contract"):
        curriculum.audit_artifact(changed, artifact, ScriptedExecutor(), tmp_path)
    other_task = curriculum.compile_family(SPEC, "development")[1]
    with pytest.raises(ValueError):
        curriculum.audit_artifact(other_task, artifact, ScriptedExecutor(), tmp_path)


def test_arbitrary_nonisolated_executor_cannot_run_references(tmp_path):
    executor = ScriptedExecutor()
    executor.identity = {"real_execution": True, "not_a_sandbox": True}
    with pytest.raises(ValueError, match="Only isolated"):
        curriculum.screen_family(SPEC, executor, tmp_path)
    assert executor.calls == 0


def test_corrupt_nested_replayed_execution_is_rejected(tmp_path):
    executor = ScriptedExecutor()
    curriculum.screen_family(SPEC, executor, tmp_path)
    path = next(p for p in (tmp_path / "screen").glob("*.json") if not p.name.endswith(".intent.json"))
    value = json.loads(path.read_text())
    execution = {k: v for k, v in value["execution"].items() if k != "record_hash"}
    execution["input_hash"] = "0" * 64
    value = {k: v for k, v in value.items() if k != "record_hash"}
    value["execution"] = seal(execution)
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="binding mismatch"):
        curriculum.screen_family(SPEC, executor, tmp_path)
    assert executor.calls == 1


def test_interrupted_call_is_unknown_without_resampling(tmp_path):
    executor = ScriptedExecutor()
    curriculum.screen_family(SPEC, executor, tmp_path)
    path = next(p for p in (tmp_path / "screen").glob("*.json") if not p.name.endswith(".intent.json"))
    path.unlink()  # Test fixture only: emulate a prior intent without terminal receipt.
    replay = curriculum.screen_family(SPEC, executor, tmp_path)
    assert replay["status"] == "unknown" and executor.calls == 1
    assert replay["receipt"]["reason"] == "interrupted_execution_no_resampling"


def test_same_inflight_screen_waits_for_receipt_instead_of_marking_interrupted(tmp_path):
    started, release = threading.Event(), threading.Event()
    class BlockingExecutor(ScriptedExecutor):
        def run(self, *args, **kwargs):
            started.set()
            assert release.wait(3)
            return super().run(*args, **kwargs)
    executor = BlockingExecutor()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(curriculum.screen_family, SPEC, executor, tmp_path)
        assert started.wait(2)
        second = pool.submit(curriculum.screen_family, SPEC, executor, tmp_path)
        try:
            with pytest.raises(FutureTimeout):
                second.result(timeout=.05)
        finally:
            release.set()
        assert first.result(timeout=3) == second.result(timeout=3)
    assert executor.calls == 1


def test_real_observation_cannot_claim_qualification_without_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(curriculum, "_is_real_executor", lambda executor: True)
    with pytest.raises(ValueError, match="cleanup"):
        curriculum.screen_family(SPEC, ScriptedExecutor(), tmp_path)
