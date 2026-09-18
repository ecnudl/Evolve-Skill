"""Public-check/cache engineering tests. Scripted receipts never execute code."""
import copy
import hashlib
import json
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.checks import (
    CallableTask,
    ContractRelation,
    ExecutionCache,
    PublicCase,
    compare_frozen,
    json_value,
    pipeline_hash,
    validate_callable,
)
from skillopt.skill_validation.models import (
    ArtifactRecord,
    Obligation,
    RubricCheck,
    RubricVersion,
    SourceFile,
    TaskContract,
)
from skillopt.validator_pilot.api import digest


class ScriptedExecutor:
    """Fabricated fixture evidence; no eval/exec, subprocess, network or Docker."""
    def __init__(self, responses=(), *, identity="scripted-fixture-v1", crash=False):
        self.responses = list(responses)
        self.identity = {"fixture_executor": identity, "real_execution": False}
        self.calls = []
        self.crash = crash

    def run(self, files, module, function, args, kwargs):
        invocation = copy.deepcopy({"files": files, "module": module, "function": function, "args": args, "kwargs": kwargs})
        self.calls.append(invocation)
        if self.crash:
            raise RuntimeError("simulated interruption before durable receipt")
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        payload = {"status": "observed", "actual": 3, "exception": None,
                   "before_args": copy.deepcopy(args), "after_args": copy.deepcopy(args),
                   "before_kwargs": copy.deepcopy(kwargs), "after_kwargs": copy.deepcopy(kwargs),
                   "input_hash": digest(invocation), "source_hash": digest(files), "call_hash": digest(call),
                   "executor_identity": self.identity, "duration_seconds": 0.25,
                   "fixture_only": True}
        if self.responses:
            payload.update(copy.deepcopy(self.responses.pop(0)))
        return seal(payload)


def task(*, inplace=False, invariant=False, expected="3"):
    prompt = "Return the total for [1, 2]. "
    prompt += "Modify the input in place." if inplace else "Do not modify the input."
    if invariant:
        prompt += " Identical calls must return equal results."
    obligations = (Obligation("returns", "requested_behavior", "Return the total", "Return the total for [1, 2]."),)
    if not inplace:
        obligations += (Obligation("input", "input_preservation", "Keep input unchanged", "Do not modify the input."),)
    contract = TaskContract("fixture-task", "fixture-original", "fixture-family", "fixture-project", "development",
                            "coding", "constraint_preservation", prompt, obligations,
                            (SourceFile("solution.py", "# Fixture source is never executed\n"),))
    case = PublicCase("example", json.dumps({"args": [[1, 2]], "kwargs": {}}), "Return the total for [1, 2].",
                      tuple(o.id for o in obligations), expected_json=expected)
    relations = (ContractRelation("returns", "repeat_equal", "Identical calls must return equal results."),) if invariant else ()
    return CallableTask(contract, "solution", "solve", (case,), relations)


def artifact(callable_task, *, condition="candidate", repeat=0, availability="available"):
    skill_hash = hashlib.sha256(b"").hexdigest() if condition == "no_skill" else digest(["fixture-skill", condition])
    files = (SourceFile("solution.py", "# Fixture candidate source, not executed\n"),) if availability == "available" else ()
    return ArtifactRecord(callable_task.contract.content_hash, repeat, condition, "fixture-skill-version", skill_hash,
                          files, availability, "fixture", True, False, "fixture:scripted-executor", digest("fixture-source"))


def rubric(methods=("public_examples", "input_state")):
    kinds = {"public_examples": "requested_behavior", "input_state": "input_preservation", "public_invariant": "requested_behavior"}
    checks = tuple(RubricCheck(method, kinds[method], method, "explicit_obligation", "absent_obligation", "actual public execution")
                   for method in methods)
    return RubricVersion("scripted-rubric", "constraint_preservation", "registered-public-cases",
                         "stage2-contract-checks-v1", "explicit-contract", "common-obligations", checks)


def three_conditions(callable_task):
    return tuple(artifact(callable_task, condition=c) for c in ("no_skill", "current", "candidate"))


def three_rubrics(*, invariant=False):
    return {"fixed": rubric(("public_examples",)),
            "adaptive_no_research": rubric(("public_examples", "input_state")),
            "adaptive_research": rubric(("public_examples", "input_state", "public_invariant") if invariant
                                         else ("public_examples", "input_state"))}


def test_return_correct_but_input_mutation_fails_only_preservation():
    t = task()
    executor = ScriptedExecutor([{"after_args": [[1, 2, 99]]}])
    report = validate_callable(t, artifact(t), rubric(), ExecutionCache(executor))
    assert report["obligations"] == {"returns": "pass", "input": "fail"}
    assert report["status"] == "fail" and len(executor.calls) == 1
    assert all(check["evidence_refs"] for check in report["checks"])


def test_return_failure_is_not_mislabeled_input_mutation():
    t = task()
    report = validate_callable(t, artifact(t), rubric(), ExecutionCache(ScriptedExecutor([{"actual": 99}])))
    assert report["obligations"] == {"returns": "fail", "input": "pass"}


def test_inplace_near_miss_does_not_impose_preservation():
    t = task(inplace=True)
    report = validate_callable(t, artifact(t), rubric(), ExecutionCache(ScriptedExecutor([{"after_args": [[1, 2, 99]]}])))
    assert report["status"] == "pass" and report["obligations"] == {"returns": "pass"}
    check = next(c for c in report["checks"] if c["check_id"] == "input_state")
    assert check["status"] == "not_applicable" and check["obligation_id"] is None and not check["evidence_refs"]


@pytest.mark.parametrize("status", ["unsupported", "execution_error"])
def test_execution_unavailability_is_unknown_not_wrong_answer(status):
    t = task()
    report = validate_callable(t, artifact(t), rubric(), ExecutionCache(ScriptedExecutor([{"status": status}])))
    assert report["obligations"] == {"returns": "unknown", "input": "unknown"}
    assert report["status"] == "unknown"


@pytest.mark.parametrize("availability", ["api_failure", "parse_failure"])
def test_delivery_failure_never_attempts_candidate_execution(availability):
    t, executor = task(), ScriptedExecutor()
    report = validate_callable(t, artifact(t, availability=availability), rubric(), ExecutionCache(executor))
    assert report["status"] == "unknown" and not executor.calls
    assert all(not c["evidence_refs"] for c in report["checks"])


def test_no_public_expected_answer_is_not_supplied_by_hidden_oracle():
    t = task(expected=None)
    report = validate_callable(t, artifact(t), rubric(), ExecutionCache(ScriptedExecutor()))
    assert report["obligations"] == {"returns": "unknown", "input": "pass"}


def test_public_exception_and_side_effect_checked_independently():
    t = task(expected=None)
    t = replace(t, public_cases=(replace(t.public_cases[0], expected_exception="ValueError"),))
    result = {"exception": "ValueError", "actual": None, "after_args": [[99]]}
    report = validate_callable(t, artifact(t), rubric(), ExecutionCache(ScriptedExecutor([result])))
    assert report["obligations"] == {"returns": "pass", "input": "fail"}


def test_missing_or_mismatched_state_cannot_be_invented():
    t = task()
    with pytest.raises(ValueError, match="initial input differs"):
        validate_callable(t, artifact(t), rubric(), ExecutionCache(ScriptedExecutor([{"before_args": [[999]]}])))
    executor = ScriptedExecutor()
    cache = ExecutionCache(executor)
    result = cache.run(t, artifact(t), t.public_cases[0])
    raw = dict(result["execution"])
    raw.pop("record_hash")
    raw.pop("before_args")
    cache.records[next(iter(cache.records))] = seal({"request": result["request"], "execution": seal(raw)})
    report = validate_callable(t, artifact(t), rubric(), cache)
    assert report["obligations"]["input"] == "unknown"


@pytest.mark.parametrize("second,expected", [(3, "pass"), (4, "fail")])
def test_explicit_repeat_invariant_has_two_actual_receipts(second, expected):
    t = task(inplace=True, invariant=True, expected=None)
    executor = ScriptedExecutor([{"actual": 3}, {"actual": second}])
    report = validate_callable(t, artifact(t), rubric(("public_invariant",)), ExecutionCache(executor))
    assert len(executor.calls) == 2
    assert report["obligations"] == {"returns": expected}
    assert len(report["checks"][0]["evidence_refs"]) == 2


def test_invariant_without_public_relation_remains_unknown():
    t, executor = task(inplace=True), ScriptedExecutor()
    report = validate_callable(t, artifact(t), rubric(("public_invariant",)), ExecutionCache(executor))
    assert report["status"] == "unknown" and not executor.calls


def test_common_evidence_does_not_run_research_only_extra_probe(tmp_path):
    t, executor = task(invariant=True), ScriptedExecutor()
    result = compare_frozen(t, three_conditions(t), three_rubrics(invariant=True), executor, root=tmp_path,
                            common_evidence=True)
    assert len(executor.calls) == result["shared_execution_cost"] == 3
    assert all(c["execution_requests"] == 0 for c in result["costs"].values())
    reports = result["reports"]["adaptive_research"]
    assert all(next(c for c in r["checks"] if c["check_id"] == "public_invariant")["status"] == "unknown" for r in reports)
    assert result["model_calls"] == 0 and result["formal_effect_estimate"] is False


def test_common_evidence_missing_counts_do_not_leak_between_arms(tmp_path):
    t = task(invariant=True)
    rubrics = three_rubrics(invariant=True)
    result = compare_frozen(t, three_conditions(t), dict(reversed(list(rubrics.items()))),
                            ScriptedExecutor(), root=tmp_path, common_evidence=True)
    assert result["costs"]["adaptive_research"]["missing_execution_records"] == 3
    assert result["costs"]["fixed"]["missing_execution_records"] == 0
    assert result["costs"]["adaptive_no_research"]["missing_execution_records"] == 0


def test_partial_input_target_cannot_silently_mean_all_inputs():
    t = task()
    obligations = tuple(replace(o, target="first_argument") if o.kind == "input_preservation" else o
                        for o in t.contract.obligations)
    with pytest.raises(ValueError, match="whole-call"):
        replace(t, contract=replace(t.contract, obligations=obligations))


def test_end_to_end_arms_have_separate_execution_and_costs(tmp_path):
    t, executor = task(invariant=True), ScriptedExecutor()
    result = compare_frozen(t, three_conditions(t), three_rubrics(invariant=True), executor, root=tmp_path)
    assert len(executor.calls) == 12  # 3 fixed + 3 adaptive + 6 Research invariant repetitions
    assert [result["costs"][a]["execution_requests"] for a in three_rubrics()] == [3, 3, 6]
    assert all(r["obligations"] == {"returns": "pass", "input": "pass"} for r in result["reports"]["adaptive_research"])
    assert len(result["execution_records_host_only"]["adaptive_research"]) == 6


@pytest.mark.parametrize("fault", ["missing", "duplicate", "repeat", "arms"])
def test_paired_comparison_rejects_noncomparable_conditions(fault):
    t, executor = task(), ScriptedExecutor()
    artifacts, rubrics = three_conditions(t), three_rubrics()
    if fault == "missing":
        artifacts = artifacts[:-1]
    elif fault == "duplicate":
        artifacts = (artifacts[0], artifacts[0], artifacts[2])
    elif fault == "repeat":
        artifacts = (*artifacts[:2], replace(artifacts[2], repeat=1))
    else:
        rubrics = {"fixed": rubrics["fixed"]}
    with pytest.raises(ValueError):
        compare_frozen(t, artifacts, rubrics, executor)
    assert not executor.calls


def test_exact_persistent_replay_makes_no_new_calls(tmp_path):
    t = task()
    first = compare_frozen(t, three_conditions(t), three_rubrics(), ScriptedExecutor(), root=tmp_path)
    snapshot = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    executor = ScriptedExecutor(crash=True)
    second = compare_frozen(t, three_conditions(t), three_rubrics(), executor, root=tmp_path)
    assert second == first and not executor.calls
    assert snapshot == {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_identical_source_different_run_has_distinct_receipt():
    t, executor = task(), ScriptedExecutor()
    cache = ExecutionCache(executor)
    first = cache.run(t, artifact(t), t.public_cases[0])
    second = cache.run(t, artifact(t, repeat=1), t.public_cases[0])
    third = cache.run(t, artifact(t, condition="current"), t.public_cases[0])
    assert len(executor.calls) == 3
    assert len({r["record_hash"] for r in (first, second, third)}) == 3
    assert len({r["execution"]["input_hash"] for r in (first, second, third)}) == 1


@pytest.mark.parametrize("field", ["input_hash", "source_hash", "call_hash", "executor_identity"])
def test_wrong_executor_binding_rejected(field):
    t = task()
    wrong = {} if field == "executor_identity" else digest("unrelated-input")
    with pytest.raises(ValueError, match="another input"):
        ExecutionCache(ScriptedExecutor([{field: wrong}])).run(t, artifact(t), t.public_cases[0])


def test_memory_cache_tampering_detected_before_reuse():
    t = task()
    cache = ExecutionCache(ScriptedExecutor())
    cache.run(t, artifact(t), t.public_cases[0])
    cache.records[next(iter(cache.records))]["execution"]["actual"] = "tampered"
    with pytest.raises(ValueError):
        cache.run(t, artifact(t), t.public_cases[0])


def test_disk_cache_request_and_intent_required(tmp_path):
    t = task()
    cache = ExecutionCache(ScriptedExecutor(), tmp_path)
    cache.run(t, artifact(t), t.public_cases[0])
    (tmp_path / "intents" / (next(iter(cache.records)) + ".json")).unlink()
    with pytest.raises(ValueError, match="original request intent"):
        ExecutionCache(ScriptedExecutor(), tmp_path).run(t, artifact(t), t.public_cases[0])


@pytest.mark.parametrize("tamper", ["unsealed_result", "resealed_request", "resealed_binding", "intent_request"])
def test_disk_cache_tamper_rejected_before_new_execution(tmp_path, tamper):
    t = task()
    cache = ExecutionCache(ScriptedExecutor(), tmp_path)
    record = cache.run(t, artifact(t), t.public_cases[0])
    key = next(iter(cache.records))
    path = tmp_path / (key + ".json")
    if tamper == "unsealed_result":
        modified = copy.deepcopy(record)
        modified["execution"]["actual"] = 999
    elif tamper == "resealed_request":
        modified = {"request": {**record["request"], "attempt": 1}, "execution": record["execution"]}
        modified = seal(modified)
    elif tamper == "resealed_binding":
        execution = {k: v for k, v in record["execution"].items() if k != "record_hash"}
        execution["input_hash"] = digest("different-public-input")
        modified = seal({"request": record["request"], "execution": seal(execution)})
    else:
        path = tmp_path / "intents" / (key + ".json")
        modified = seal({"request": {**record["request"], "attempt": 1}})
    path.write_text(json.dumps(modified), encoding="utf-8")
    executor = ScriptedExecutor()
    with pytest.raises(ValueError):
        ExecutionCache(executor, tmp_path).run(t, artifact(t), t.public_cases[0])
    assert not executor.calls


def test_terminal_failed_receipt_is_not_retried(tmp_path):
    t = task()
    first_executor = ScriptedExecutor([{"status": "execution_error"}])
    first = ExecutionCache(first_executor, tmp_path).run(t, artifact(t), t.public_cases[0])
    later_executor = ScriptedExecutor()
    replayed = ExecutionCache(later_executor, tmp_path).run(t, artifact(t), t.public_cases[0])
    assert replayed == first and replayed["execution"]["status"] == "execution_error"
    assert not later_executor.calls


def test_interrupted_execution_not_retried_on_resume(tmp_path):
    t = task()
    with pytest.raises(RuntimeError, match="simulated interruption"):
        ExecutionCache(ScriptedExecutor(crash=True), tmp_path).run(t, artifact(t), t.public_cases[0])
    executor = ScriptedExecutor()
    cache = ExecutionCache(executor, tmp_path)
    result = cache.run(t, artifact(t), t.public_cases[0])
    assert result["execution"]["status"] == "unsupported"
    assert result["execution"]["reason"] == "interrupted_execution_no_receipt"
    assert not executor.calls and len(cache.missing_records) == 1
    report = validate_callable(t, artifact(t), rubric(), cache)
    assert report["status"] == "unknown"


def test_persistent_budget_cannot_reset_by_restarting_process(tmp_path):
    t = task()
    first = ExecutionCache(ScriptedExecutor(), tmp_path, max_executions=1)
    first.run(t, artifact(t), t.public_cases[0])
    executor = ScriptedExecutor()
    resumed = ExecutionCache(executor, tmp_path, max_executions=1)
    result = resumed.run(t, artifact(t, repeat=1), t.public_cases[0])
    assert result["execution"]["reason"] == "execution_budget_exhausted" and not executor.calls
    assert resumed.run(t, artifact(t, repeat=1), t.public_cases[0]) == result
    assert len(resumed.missing_records) == 1


def test_read_only_missing_execution_is_visible_unknown():
    t, executor = task(), ScriptedExecutor()
    cache = ExecutionCache(executor, read_only=True, mode="common_evidence")
    report = validate_callable(t, artifact(t), rubric(), cache)
    assert report["status"] == "unknown" and not executor.calls
    assert len(cache.missing_records) == 1


def test_reusable_pipeline_binds_mode_budget_and_executor():
    r = rubric()
    hashes = [pipeline_hash(r, ExecutionCache(ScriptedExecutor())),
              pipeline_hash(r, ExecutionCache(ScriptedExecutor(), max_executions=10)),
              pipeline_hash(r, ExecutionCache(ScriptedExecutor(), mode="common_evidence")),
              pipeline_hash(r, ExecutionCache(ScriptedExecutor(identity="changed-executor"))),
              pipeline_hash(replace(r, generation_policy="changed-generation"), ExecutionCache(ScriptedExecutor()))]
    assert len(set(hashes)) == len(hashes)


def test_illegal_method_or_unexecuted_applicability_cannot_enter_report():
    t, r = task(), rubric()
    for changes in ({"method": "shell_exec"}, {"applicability": "model_says_applicable"},
                    {"exceptions": "ignore_failures"}, {"obligation_kind": "file_preservation"}):
        modified = replace(r, checks=(replace(r.checks[0], **changes), *r.checks[1:]))
        with pytest.raises(ValueError):
            validate_callable(t, artifact(t), modified, ExecutionCache(ScriptedExecutor()))


def test_unregistered_inputs_and_hidden_relations_rejected():
    t = task()
    with pytest.raises(ValueError, match="Unregistered test input"):
        ExecutionCache(ScriptedExecutor()).run(t, artifact(t), replace(t.public_cases[0], id="secret-input"))
    with pytest.raises(ValueError, match="public-contract basis"):
        replace(t, relations=(ContractRelation("returns", "repeat_equal", "hidden audit says deterministic"),))
    with pytest.raises(ValueError):
        replace(t, public_cases=(replace(t.public_cases[0], obligation_ids=("hidden-obligation",)),))


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', 'NaN', 'Infinity', '1e999', '[' * 15 + '0' + ']' * 15])
def test_public_json_duplicate_nonfinite_and_depth_rejected(raw):
    with pytest.raises(ValueError):
        json_value(raw)


def test_public_types_roundtrip_exact_and_no_answer_extras():
    t = task(invariant=True)
    assert CallableTask.from_dict(t.to_dict()) == t
    bad = t.public_cases[0].to_dict()
    bad["hidden_expected"] = 999
    with pytest.raises(ValueError):
        PublicCase.from_dict(bad)


def test_execution_cache_symlink_refuses_writes(tmp_path):
    t = task()
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    executor = ScriptedExecutor()
    with pytest.raises(ValueError, match="Symlink"):
        ExecutionCache(executor, link).run(t, artifact(t), t.public_cases[0])
    assert not executor.calls
