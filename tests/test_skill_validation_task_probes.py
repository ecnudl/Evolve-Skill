"""Task probe schema, isolation boundary, uncertainty and durable replay tests."""
import copy
import json
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.checks import CallableTask
from skillopt.skill_validation.models import ArtifactRecord, Obligation, SourceFile, TaskContract
from skillopt.skill_validation.task_probes import execute_probes, parse_probes
from skillopt.validator_pilot.api import digest


def task():
    prompt = "Return whether z appears inside a word."
    contract = TaskContract("task", "task", "family", "project", "development", "coding", "return_contract",
                            prompt, (Obligation("result", "requested_behavior", prompt, prompt),))
    return CallableTask(contract, "solution", "solve", ())


def artifact(t, *, available=True):
    files = (SourceFile("solution.py", "# Never executed by these fixture tests\n"),) if available else ()
    return ArtifactRecord(t.contract.content_hash, 0, "candidate", "fixture", digest("skill"), files,
                          "available" if available else "parse_failure", "fixture", True, False,
                          "fixture:probe-test", digest("source"))


def raw(*, relation=False, expected=False):
    calls = [{"args": ["abz."], "kwargs": {}}]
    if relation:
        calls.append({"args": ["cdz."], "kwargs": {}})
    return {"probes": [{"kind": "equal_relation" if relation else "expected", "calls": calls,
                        "expected": None if relation else expected, "obligation_id": "result",
                        "contract_quote": "inside a word", "rationale": "A terminal z is not inside a word."}]}


class Executor:
    """Sealed scripted receipts, no candidate code execution."""
    identity = {"fixture": "task-probe-unit-tests", "real_execution": False}

    def __init__(self, responses=(), error=None):
        self.responses, self.error, self.calls = list(responses), error, []

    def run(self, files, module, function, args, kwargs):
        invocation = copy.deepcopy({"files": files, "module": module, "function": function,
                                    "args": args, "kwargs": kwargs})
        self.calls.append(invocation)
        if self.error:
            raise self.error
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        result = {"status": "observed", "actual": False, "exception": None, "cleanup_confirmed": True,
                  "before_args": copy.deepcopy(args), "after_args": copy.deepcopy(args),
                  "before_kwargs": copy.deepcopy(kwargs), "after_kwargs": copy.deepcopy(kwargs),
                  "input_hash": digest(invocation), "source_hash": digest(files), "call_hash": digest(call),
                  "executor_identity": self.identity}
        if self.responses:
            patch = self.responses.pop(0)
            for key in patch.pop("omit", []):
                result.pop(key)
            result.update(patch)
        return seal(result)


def run(tmp_path, *, proposal=None, executor=None, available=True):
    t = task()
    return execute_probes(t, artifact(t, available=available), parse_probes(proposal or raw(), t),
                          executor or Executor(), tmp_path)


def test_parse_records_hypothesis_and_detaches_input():
    value = raw()
    proposal = parse_probes(json.dumps(value), task())
    assert verify(proposal) == proposal
    assert proposal["information_origin"] == "model_hypothesis"
    assert proposal["semantic_authority"] is False
    assert proposal["contract_validation"] == "literal_quote_only_not_entailment"
    value["probes"][0]["expected"] = True
    assert proposal["probes"][0]["expected"] is False


@pytest.mark.parametrize("field", ["code", "script", "function", "module", "oracle", "host_audit", "id"])
def test_rejects_code_or_dynamic_dispatch_fields(field):
    value = raw()
    value["probes"][0][field] = "__import__('os').system('anything')"
    with pytest.raises(ValueError):
        parse_probes(value, task())


def test_script_payload_and_duplicate_keys_rejected():
    for value in ["print('not json')", '{"probes": [], "probes": []}', {"probes": [], "code": "pass"}]:
        with pytest.raises(ValueError):
            parse_probes(value, task())


@pytest.mark.parametrize("change", [
    {"kind": "python_assert"}, {"kind": []}, {"obligation_id": "input_preservation"},
    {"contract_quote": "Do not modify the input."}, {"rationale": ""},
    {"calls": []}, {"calls": [{"args": [], "kwargs": {}, "function": "eval"}]},
    {"calls": [{"args": "not an array", "kwargs": {}}]},
    {"calls": [{"args": [], "kwargs": []}]},
    {"calls": [{"args": [float("inf")], "kwargs": {}}]},
    {"expected": float("nan")}, {"expected": (1, 2)}, {"expected": {1: "not a string key"}},
])
def test_rejects_unsupported_proposals(change):
    value = raw()
    value["probes"][0].update(change)
    with pytest.raises(ValueError):
        parse_probes(value, task())


def test_budget_and_bounded_json():
    value = raw()
    value["probes"] *= 3
    with pytest.raises(ValueError):
        parse_probes(value, task())
    for invalid in (True, 0, 9):
        with pytest.raises(ValueError):
            parse_probes(raw(), task(), max_probes=invalid)
    for expected in ("a" * 32769, [0] * 129):
        with pytest.raises(ValueError):
            parse_probes(raw(expected=expected), task())
    nested = None
    for _ in range(15):
        nested = [nested]
    with pytest.raises(ValueError):
        parse_probes(raw(expected=nested), task())
    with pytest.raises(ValueError):
        parse_probes(json.dumps(raw()).replace("false", "1e999"), task())


def test_relation_requires_two_calls_and_no_expected_answer():
    value = raw(relation=True)
    assert parse_probes(value, task())["probes"][0]["kind"] == "equal_relation"
    value["probes"][0]["expected"] = False
    with pytest.raises(ValueError):
        parse_probes(value, task())


@pytest.mark.parametrize("actual,expected,status", [(False, False, "match"), (True, False, "mismatch"),
                                                   (None, None, "match"), (1, True, "mismatch")])
def test_execution_compares_json_but_never_confirms_semantic_failure(tmp_path, actual, expected, status):
    executor = Executor([{"actual": actual}])
    report = run(tmp_path, proposal=raw(expected=expected), executor=executor)
    assert report["status"] == status
    assert not report["confirmed_semantic_failure"] and not report["deployment_authorized"]
    assert report["semantic_status"] == "unknown"
    assert report["probes"][0]["semantic_status"] == "unknown"
    assert report["probes"][0]["evidence_refs"]
    observed = report["probes"][0]["observations"][0]["public_observation"]
    assert observed["actual"] == actual and observed["before_args"] == ["abz."]
    assert executor.calls[0]["module"] == "solution" and executor.calls[0]["function"] == "solve"
    assert set(executor.calls[0]["files"]) == {"solution.py"}


def test_relation_uses_two_separate_isolated_calls(tmp_path):
    executor = Executor([{"actual": [1]}, {"actual": [1]}])
    report = run(tmp_path, proposal=raw(relation=True), executor=executor)
    assert report["status"] == "match" and len(executor.calls) == 2
    assert len(set(report["probes"][0]["evidence_refs"])) == 2
    assert executor.calls[0]["args"] != executor.calls[1]["args"]


@pytest.mark.parametrize("response", [
    {"status": "unsupported"}, {"status": "execution_error"}, {"exception": "ValueError"},
    {"omit": ["actual"]}, {"omit": ["exception"]}, {"omit": ["before_args"]},
    {"before_args": None}, {"after_kwargs": None}, {"cleanup_confirmed": False},
    {"omit": ["cleanup_confirmed"]},
])
def test_missing_state_exceptions_and_infrastructure_are_unknown(tmp_path, response):
    report = run(tmp_path, executor=Executor([response]))
    assert report["status"] == "unknown"
    assert report["probes"][0]["observations"][0]["status"] == "unknown"


def test_state_change_is_observed_but_not_an_implicit_preservation_error(tmp_path):
    report = run(tmp_path, executor=Executor([{"after_args": ["changed"]}]))
    assert report["status"] == "match"
    assert report["probes"][0]["observations"][0]["public_observation"]["after_args"] == ["changed"]


def test_string_looking_like_code_remains_literal_data(tmp_path):
    value = raw()
    code = "__import__('os').system('not executed')"
    value["probes"][0]["calls"][0]["args"] = [code]
    executor = Executor()
    run(tmp_path, proposal=value, executor=executor)
    assert executor.calls[0]["args"] == [code]


def test_absent_artifact_is_unknown_without_executor_call(tmp_path):
    executor = Executor()
    report = run(tmp_path, executor=executor, available=False)
    assert report["status"] == "unknown" and not executor.calls


def test_empty_proposal_abstains_without_execution(tmp_path):
    executor = Executor()
    report = run(tmp_path, proposal={"probes": []}, executor=executor)
    assert report["status"] == "unknown" and not report["probes"] and not executor.calls


def test_replay_never_calls_executor_and_preserves_every_byte(tmp_path):
    executor = Executor()
    original = run(tmp_path, executor=executor)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    again = run(tmp_path, executor=Executor(error=AssertionError("must not execute")))
    assert again == original
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.json")} == before


def test_nested_and_large_executor_metadata_remains_replayable(tmp_path):
    actual = 1
    for _ in range(11):
        actual = [actual]
    original = run(tmp_path, executor=Executor([{"actual": actual, "diagnostic": "x" * 60000}]))
    assert original["status"] == "mismatch"
    assert run(tmp_path, executor=Executor(error=AssertionError("no retry"))) == original


def test_missing_receipt_after_completed_report_does_not_rerun(tmp_path):
    run(tmp_path)
    next((tmp_path / "calls").glob("*.json")).unlink()
    executor = Executor()
    with pytest.raises(ValueError, match="missing its execution receipt"):
        run(tmp_path, executor=executor)
    assert not executor.calls


def test_executor_exception_becomes_durable_unknown(tmp_path):
    executor = Executor(error=RuntimeError("private transport diagnostic must not escape"))
    original = run(tmp_path, executor=executor)
    again = run(tmp_path, executor=Executor(error=AssertionError("no retry")))
    assert original["status"] == "unknown" and original == again
    assert "private transport" not in json.dumps(original)


def test_interrupted_intent_is_not_resampled(tmp_path):
    executor = Executor(error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, executor=executor)
    resumed = Executor()
    report = run(tmp_path, executor=resumed)
    assert report["status"] == "unknown" and not resumed.calls
    assert report["probes"][0]["observations"][0]["reason"] == "interrupted_call_no_resampling"


@pytest.mark.parametrize("field", ["input_hash", "source_hash", "call_hash", "executor_identity"])
def test_execution_binding_mismatch_is_rejected(tmp_path, field):
    with pytest.raises(ValueError, match="different input"):
        run(tmp_path, executor=Executor([{field: "wrong"}]))


def test_unknown_executor_status_and_wrong_before_state_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown executor state"):
        run(tmp_path / "state", executor=Executor([{"status": "success"}]))
    with pytest.raises(ValueError, match="before-state"):
        run(tmp_path / "before", executor=Executor([{"before_args": ["wrong"]}]))


def test_proposal_cannot_rebind_task_callable_or_policy(tmp_path):
    t = task()
    proposal = parse_probes(raw(), t)
    changed = replace(t, function="other")
    with pytest.raises(ValueError, match="Changed probe"):
        execute_probes(changed, artifact(changed), proposal, Executor(), tmp_path)
    payload = {k: v for k, v in proposal.items() if k != "record_hash"}
    payload["semantic_authority"] = True
    with pytest.raises(ValueError, match="Changed probe"):
        execute_probes(t, artifact(t), seal(payload), Executor(), tmp_path)


def test_tampered_cached_execution_rejected(tmp_path):
    run(tmp_path)
    path = next((tmp_path / "calls").glob("*.json"))
    value = json.loads(path.read_text())
    value["execution"]["actual"] = "tampered"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="checksum"):
        run(tmp_path)


def test_symlink_cache_root_rejected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        run(link)
