"""Nonexecuting fixtures; no API, Docker, hidden oracle or candidate exec."""
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.checks import VERSION as CHECK_VERSION
from skillopt.skill_validation.checks import ExecutionCache, PublicCase
from skillopt.skill_validation.models import Obligation, SourceFile
from skillopt.skill_validation.public_case_feedback import MAX_EXECUTIONS, collect, model_view
from skillopt.validator_pilot.api import digest, write_immutable_json
from tests.test_skill_validation_public_revision import (
    SECRET,
    FixtureExecutor,
    artifact,
    fixture_row,
    reseal,
)


def source_row(*, preserve=False, inplace=False, expected="3", exception=None):
    row = fixture_row()
    task = row["task"]
    state_text = " Do not modify the input." if preserve else (
        " Modify the input in place." if inplace else " Input mutation is allowed, not required.")
    contract = replace(task.contract, prompt=task.contract.prompt + state_text)
    if preserve:
        obligation = Obligation("hidden-state-" + SECRET, "input_preservation", state_text, state_text)
        contract = replace(contract, obligations=contract.obligations + (obligation,))
    case = replace(task.public_cases[0], expected_json=expected, expected_exception=exception,
                   obligation_ids=tuple(o.id for o in contract.obligations))
    row["task"] = replace(task, contract=contract, public_cases=(case,))
    row["public_task"] = replace(row["public_task"], contract=contract)
    return row


def invoke(tmp_path, *, row=None, outcomes=(), availability="available", executor=None):
    row = row if row is not None else source_row()
    a = artifact(row, availability=availability)
    e = executor if executor is not None else FixtureExecutor(*outcomes)
    record = collect(row, a, e, tmp_path / "feedback")
    return record, row, a, e


def test_direct_case_executes_real_registered_arguments_not_boolean_wrapper(tmp_path):
    record, row, a, executor = invoke(tmp_path, outcomes=({"actual": 3},))
    verify(record)
    assert len(executor.calls) == 1
    assert executor.calls[0]["module"] == "solution" and executor.calls[0]["function"] == "solve"
    assert executor.calls[0]["args"] == [[1, 2]] and executor.calls[0]["kwargs"] == {}
    case = record["cases"][0]
    assert case["public_input"] == {"args": [[1, 2]], "kwargs": {}}
    assert case["expected"] == 3 and case["observation"]["actual"] == 3
    assert case["return_check"]["status"] == "pass"
    assert case["case_hash"] == row["task"].public_cases[0].content_hash
    assert case["artifact_record_hash"] == a.content_hash
    assert case["execution_receipt_hash"] == record["execution_records"][0]["record_hash"]
    assert record["fixture_only"] and not record["research_increment"]
    assert record["full_contract_correctness"] == "not_established"
    assert not record["learning_authorized"] and not record["deployment_authorized"]


def test_model_projection_replays_and_hides_host_labels_receipts_and_wrapper(tmp_path):
    record, _, _, executor = invoke(tmp_path, outcomes=({"actual": 3},))
    before = len(executor.calls)
    view = model_view(record)
    assert len(executor.calls) == before
    raw = json.dumps(view)
    assert SECRET not in raw  # Host metadata, semantic IDs and public wrapper fixture marker.
    for field in ("condition", "family_id", "task_hash", "source_ref", "source_hash", "host_audit", "execution_identity"):
        assert json.dumps(field) + ":" not in raw
    assert view["cases"][0]["id"] == "case_000"
    assert view["cases"][0]["obligation_ids"] == ["obligation_0"]
    assert view["cases"][0]["evidence_ref"] == record["cases"][0]["evidence_ref"]
    assert [f["path"] for f in view["artifact"]["files"]] == ["solution.py"]
    assert view["information_origins"] == ["registered_public_example_recovery", "recorded_public_execution"]
    assert not view["research_increment"] and not view["learning_authorized"]


@pytest.mark.parametrize("preserve,inplace,expected", [(True, False, "fail"),
    (False, True, "not_applicable"), (False, False, "not_applicable")])
def test_mutation_is_only_failure_under_explicit_preservation(tmp_path, preserve, inplace, expected):
    row = source_row(preserve=preserve, inplace=inplace)
    record, _, _, _ = invoke(tmp_path, row=row, outcomes=({"actual": 3, "after_args": [[9]]},))
    case = model_view(record)["cases"][0]
    assert case["return_check"]["status"] == "pass"
    assert case["input_state_changed"] is True
    assert case["preservation_check"]["status"] == expected
    assert case["other_state_requirements"]["status"] == "unknown"


def test_inplace_target_is_not_inferred_even_from_public_prose_or_host_answers(tmp_path):
    row = source_row(inplace=True)
    row["host_only"] = {"expected_after": [[9]], "reference_code": SECRET}
    record, _, _, _ = invoke(tmp_path, row=row, outcomes=({"actual": 3},))
    case = model_view(record)["cases"][0]
    assert case["input_state_changed"] is False
    assert case["preservation_check"]["status"] == "not_applicable"
    assert case["other_state_requirements"]["status"] == "unknown"
    assert SECRET not in json.dumps(model_view(record))


def test_preservation_must_bind_current_public_case(tmp_path):
    row = source_row(preserve=True)
    task = row["task"]
    row["task"] = replace(task, public_cases=(replace(task.public_cases[0],
        obligation_ids=(task.contract.obligations[0].id,)),))
    record, _, _, _ = invoke(tmp_path, row=row, outcomes=({"actual": 3, "after_args": [[9]]},))
    assert record["cases"][0]["preservation_check"]["status"] == "unknown"


def test_return_and_state_are_separate_and_strictly_typed(tmp_path):
    record, _, _, _ = invoke(tmp_path, row=source_row(preserve=True, expected="1"), outcomes=({"actual": True},))
    case = record["cases"][0]
    assert case["return_check"]["status"] == "fail"
    assert case["preservation_check"]["status"] == "pass"


def test_registered_exception_can_pass_while_preservation_fails(tmp_path):
    row = source_row(preserve=True, expected=None, exception="ValueError")
    record, _, _, _ = invoke(tmp_path, row=row,
        outcomes=({"actual": None, "exception": "ValueError", "after_args": [[9]]},))
    case = record["cases"][0]
    assert case["return_check"]["status"] == "pass"
    assert case["preservation_check"]["status"] == "fail"


@pytest.mark.parametrize("exception", ["MemoryError", "TimeoutError"])
@pytest.mark.parametrize("changed", [False, True])
def test_unexpected_resource_exception_is_unknown_but_observed_state_stays_independent(tmp_path, exception, changed):
    outcome = {"actual": None, "exception": exception}
    if changed:
        outcome["after_args"] = [[9]]
    record, _, _, _ = invoke(tmp_path, row=source_row(preserve=True), outcomes=(outcome,))
    case = model_view(record)["cases"][0]
    assert record["version"] == "registered-public-case-observations-v2"
    assert case["return_check"] == {
        "status": "unknown", "reason": "resource_limited_execution_not_semantic_failure"}
    assert case["preservation_check"]["status"] == ("fail" if changed else "pass")
    assert case["input_state_changed"] is changed


@pytest.mark.parametrize("expected,observed,status", [
    ("MemoryError", "MemoryError", "pass"), ("TimeoutError", "TimeoutError", "pass"),
    ("MemoryError", "TimeoutError", "unknown"), ("TimeoutError", "MemoryError", "unknown"),
    ("ValueError", "MemoryError", "unknown"), ("ValueError", "TimeoutError", "unknown"),
    (None, "ValueError", "fail"), (None, "TypeError", "fail"),
])
def test_explicit_exception_contract_and_ordinary_errors_keep_exact_public_semantics(tmp_path, expected, observed, status):
    row = source_row(expected=None if expected else "3", exception=expected)
    record, _, _, _ = invoke(tmp_path, row=row, outcomes=({"actual": None, "exception": observed},))
    assert model_view(record)["cases"][0]["return_check"]["status"] == status


def test_missing_public_expected_result_does_not_use_host_oracle(tmp_path):
    record, _, _, _ = invoke(tmp_path, row=source_row(expected=None), outcomes=({"actual": 3},))
    case = model_view(record)["cases"][0]
    assert case["return_check"]["status"] == "unknown"
    assert not case["expected_is_provided"] and case["expected"] is None


def test_explicit_json_null_is_not_missing_expected_value(tmp_path):
    record, _, _, _ = invoke(tmp_path, row=source_row(expected="null"), outcomes=({"actual": None},))
    case = model_view(record)["cases"][0]
    assert case["return_check"]["status"] == "pass"
    assert case["expected_is_provided"] and case["expected"] is None


def test_each_registered_public_case_gets_its_own_input_and_receipt(tmp_path):
    row = source_row()
    task = row["task"]
    new_quote = " For [4], the result is 4."
    contract = replace(task.contract, prompt=task.contract.prompt + new_quote)
    second = PublicCase("second", '{"args":[[4]],"kwargs":{}}', new_quote,
                        (contract.obligations[0].id,), "4")
    row["task"] = replace(task, contract=contract, public_cases=task.public_cases + (second,))
    row["public_task"] = replace(row["public_task"], contract=contract)
    record, _, _, executor = invoke(tmp_path, row=row, outcomes=({"actual": 3}, {"actual": 99}))
    assert [r["args"] for r in executor.calls] == [[[1, 2]], [[4]]]
    assert [c["return_check"]["status"] for c in record["cases"]] == ["pass", "fail"]
    assert len({c["execution_receipt_hash"] for c in record["cases"]}) == 2
    assert record["counts"]["return_check"] == {"pass": 1, "fail": 1, "unknown": 0, "not_applicable": 0}


def test_no_registered_examples_does_not_manufacture_a_success(tmp_path):
    row = source_row()
    row["task"] = replace(row["task"], public_cases=())
    record, _, _, executor = invoke(tmp_path, row=row)
    assert not executor.calls and record["cases"] == []
    assert record["counts"]["registered_cases"] == 0
    assert record["full_contract_correctness"] == "not_established"


@pytest.mark.parametrize("availability", ["api_failure", "parse_failure"])
def test_unavailable_artifact_is_unknown_without_executor_call(tmp_path, availability):
    record, _, _, executor = invoke(tmp_path, availability=availability)
    assert not executor.calls and not record["execution_records"]
    case = model_view(record)["cases"][0]
    assert case["return_check"]["status"] == "unknown"
    assert case["observation"]["unavailable_reason"] == "artifact_" + availability


@pytest.mark.parametrize("outcome", [
    {"status": "unsupported"}, {"status": "execution_error"}, {"cleanup_confirmed": False},
])
def test_failed_or_unclean_execution_is_unknown_not_semantic_failure(tmp_path, outcome):
    record, _, _, _ = invoke(tmp_path, row=source_row(preserve=True), outcomes=(outcome,))
    case = model_view(record)["cases"][0]
    assert case["return_check"]["status"] == case["preservation_check"]["status"] == "unknown"
    assert case["input_state_changed"] is None


def test_thrown_transport_exception_uses_existing_terminal_unavailable_receipt(tmp_path):
    executor = FixtureExecutor(error=RuntimeError("PRIVATE_EXCEPTION_DETAILS"))
    record, row, a, _ = invoke(tmp_path, executor=executor)
    assert record["cases"][0]["return_check"]["status"] == "unknown"
    assert "PRIVATE_EXCEPTION_DETAILS" not in json.dumps(model_view(record))
    assert collect(row, a, executor, tmp_path / "feedback") == record
    assert len(executor.calls) == 1


def test_interrupted_cache_entry_stays_unknown_and_is_never_reexecuted(tmp_path):
    row, executor = source_row(), FixtureExecutor()
    a = artifact(row)
    cache_root = tmp_path / "feedback" / "executions"
    cache = ExecutionCache(executor, cache_root, max_executions=MAX_EXECUTIONS)
    request = {"version": CHECK_VERSION, "callable_task_hash": row["task"].content_hash,
        "artifact_record_hash": a.content_hash, "case_hash": row["task"].public_cases[0].content_hash,
        "attempt": 0, "execution_identity": cache.identity}
    write_immutable_json(cache_root / "intents" / (digest(request) + ".json"), seal({"request": request}))
    record = collect(row, a, executor, tmp_path / "feedback")
    assert not executor.calls
    assert record["cases"][0]["return_check"]["status"] == "unknown"
    assert model_view(record)["cases"][0]["observation"]["unavailable_reason"] == "interrupted_no_receipt"


def test_conflicting_public_examples_keep_observations_but_abstain_on_return_judgment(tmp_path):
    row = source_row()
    case = row["task"].public_cases[0]
    row["task"] = replace(row["task"], public_cases=(case, replace(case, id="conflict", expected_json="99")))
    record, _, _, executor = invoke(tmp_path, row=row, outcomes=({"actual": 3}, {"actual": 3}))
    assert len(executor.calls) == 2
    assert all(c["return_check"]["status"] == "unknown" for c in record["cases"])
    assert all(c["return_check"]["reason"] == "conflicting_registered_public_expectations" for c in record["cases"])


def test_concurrent_collection_and_replay_never_duplicate_calls(tmp_path):
    row, executor = source_row(), FixtureExecutor({"actual": 3})
    a = artifact(row)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda _: collect(row, a, executor, tmp_path / "feedback"), range(2)))
    assert records[0] == records[1] and len(executor.calls) == 1
    assert model_view(records[0]) == model_view(records[1])


def test_mismatched_wrapper_and_task_fail_before_execution(tmp_path):
    row, executor = source_row(), FixtureExecutor()
    a = artifact(row)
    row["public_wrapper"] = {"path": "public_runner.py", "content": "# different registration"}
    with pytest.raises(ValueError, match="source/wrapper"):
        collect(row, a, executor, tmp_path / "feedback")
    assert not executor.calls


def test_an_existing_directory_cannot_rebind_another_artifact(tmp_path):
    record, row, a, executor = invoke(tmp_path, outcomes=({"actual": 3},))
    changed = replace(a, files=(SourceFile("solution.py", "# changed fixture"), a.files[1]))
    with pytest.raises(ValueError):
        collect(row, changed, executor, tmp_path / "feedback")
    assert len(executor.calls) == 1


@pytest.mark.parametrize("change", ["derived", "missing_receipt", "extra_receipt", "source", "case", "artifact", "private"])
def test_outer_resealing_cannot_bypass_receipt_replay(tmp_path, change):
    record, _, _, _ = invoke(tmp_path, outcomes=({"actual": 99},))
    record = deepcopy(record)
    if change == "derived":
        record["cases"][0]["return_check"]["status"] = "pass"
    elif change == "missing_receipt":
        record["execution_records"] = []
    elif change == "extra_receipt":
        record["execution_records"] *= 2
    elif change == "source":
        receipt = record["execution_records"][0]
        receipt["execution"]["source_hash"] = digest("different-source")
        receipt["execution"] = reseal(receipt["execution"])
        record["execution_records"][0] = reseal(receipt)
    elif change == "case":
        record["task"]["public_cases"][0]["expected_json"] = "99"
    elif change == "artifact":
        record["artifact"]["condition"] = "candidate"
    else:
        record["host_audit"] = SECRET
    with pytest.raises(ValueError):
        model_view(reseal(record))


def test_observed_initial_state_must_match_exact_registered_input(tmp_path):
    with pytest.raises(ValueError, match="initial state differs"):
        invoke(tmp_path, outcomes=({"actual": 3, "before_args": [[True, 2]]},))


def test_missing_state_is_unknown_without_hiding_available_return(tmp_path):
    class MissingStateExecutor(FixtureExecutor):
        def run(self, *args, **kwargs):
            record = super().run(*args, **kwargs)
            del record["after_args"]
            return reseal(record)
    record, _, _, _ = invoke(tmp_path, row=source_row(preserve=True),
                              executor=MissingStateExecutor({"actual": 3}))
    case = model_view(record)["cases"][0]
    assert case["return_check"]["status"] == "pass"
    assert case["preservation_check"]["status"] == "unknown" and case["input_state_changed"] is None


def test_unregistered_nonisolated_executor_is_rejected_before_run(tmp_path):
    class UnsafeExecutor(FixtureExecutor):
        identity = {"kind": "arbitrary-host-executor"}
    executor = UnsafeExecutor()
    with pytest.raises(ValueError, match="Only isolated"):
        invoke(tmp_path, executor=executor)
    assert not executor.calls
