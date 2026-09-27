"""Fabricated receipts test control flow only, never revision effectiveness.

No API, SSH, subprocess, Python eval/exec or candidate execution is used.
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import public_revision as revision
from skillopt.skill_validation.checks import CallableTask, PublicCase
from skillopt.skill_validation.models import ArtifactRecord, Obligation, SourceFile, TaskContract
from skillopt.validator_pilot.api import digest

SECRET = "HOST_AUDIT_PRIVATE_SENTINEL"
CODE = "def solve(values):\n    return sum(values)\n"
REVISED = "def solve(values):\n    return sum(values, 0)\n"


class PublicOnlyRow(dict):
    def __getitem__(self, key):
        assert key in {"task", "public_task", "public_wrapper"}, "Private row access: " + key
        return super().__getitem__(key)


class FixtureCalls:
    def __init__(self, response="KEEP", *, ok=True, error=None):
        self.api = SimpleNamespace(model="fixture-no-model", service={"fixture": True, "provider": "BIGMODEL"})
        self.protocol_hash = digest("fixture-revision-protocol")
        self.response, self.ok, self.error, self.calls = response, ok, error, []

    def call(self, system, user, kind, *, repeat, max_tokens):
        request = {"system": system, "user": user, "kind": kind, "repeat": repeat,
                   "max_tokens": max_tokens, "model": self.api.model, "service": self.api.service}
        self.calls.append(request)
        if self.error:
            raise self.error
        return {"request": request, "request_hash": digest(request), "ok": self.ok,
                "response": self.response, "fixture_only": True, "diagnostics": SECRET}


class FixtureExecutor:
    identity = {"kind": "fabricated-public-revision-fixture", "real_execution": False}

    def __init__(self, *outcomes, error=None):
        self.outcomes, self.calls, self.error = list(outcomes), [], error

    def run(self, files, module, function, args, kwargs):
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        self.calls.append(deepcopy({"files": files, **call}))
        if self.error:
            raise self.error
        response = self.outcomes.pop(0) if self.outcomes else {}
        return seal({"status": "observed", "actual": True, "exception": None,
                     "before_args": deepcopy(args), "after_args": deepcopy(args),
                     "before_kwargs": deepcopy(kwargs), "after_kwargs": deepcopy(kwargs),
                     "input_hash": digest({"files": files, **call}), "source_hash": digest(files),
                     "call_hash": digest(call), "executor_identity": self.identity,
                     "cleanup_confirmed": True, "host_metadata": SECRET, "stdout": SECRET, **response})


def fixture_row():
    prompt = "Return the sum of the values. For [1, 2], the result is 3."
    contract = TaskContract(SECRET, SECRET, SECRET, SECRET, "development", "coding", SECRET, prompt,
                           (Obligation("private-obligation-" + SECRET, "requested_behavior", prompt, prompt),))
    ids = (contract.obligations[0].id,)
    task = CallableTask(contract, "solution", "solve", (
        PublicCase("private-case-" + SECRET, '{"args":[[1,2]],"kwargs":{}}', prompt, ids, "3"),))
    public_task = CallableTask(contract, "public_runner", "check", (
        PublicCase("private-wrapper-case-" + SECRET, '{"args":[],"kwargs":{}}', prompt, ids, "true"),))
    return PublicOnlyRow(task=task, public_task=public_task,
                        public_wrapper={"path": "public_runner.py", "content": "# fixture wrapper " + SECRET},
                        host_audit={"reference_code": SECRET}, identity={"hidden": SECRET})


def artifact(row, *, skill="", condition="no_skill", repeat=2, availability="available"):
    return ArtifactRecord(row["task"].contract.content_hash, repeat, condition,
        "host-version-" + SECRET, hashlib.sha256(skill.encode()).hexdigest(),
        (SourceFile("solution.py", CODE), SourceFile.from_dict(row["public_wrapper"])) if availability == "available" else (),
        availability, "fixture", True, False, "fixture-source:" + SECRET, digest("fixture-source"))


def invoke(tmp_path, *, response="KEEP", outcomes=(), availability="available", skill="", condition="no_skill"):
    row = fixture_row()
    original = artifact(row, skill=skill, condition=condition, availability=availability)
    calls, executor = FixtureCalls(response), FixtureExecutor(*outcomes)
    result = revision.revise_public(row, original, skill, calls, executor, tmp_path)
    return result, row, original, calls, executor


def reseal(record):
    return seal({k: v for k, v in record.items() if k != "record_hash"})


@pytest.mark.parametrize("condition,skill", [("no_skill", ""), ("current", "Parent advice"), ("candidate", "New advice")])
@pytest.mark.parametrize("actual", [True, False])
def test_all_conditions_get_one_keep_opportunity_even_on_public_pass(tmp_path, condition, skill, actual):
    result, row, original, calls, executor = invoke(tmp_path, skill=skill, condition=condition,
                                                  outcomes=({"actual": actual},))
    assert result["artifact"] == original
    assert result["record"]["status"] == "kept"
    assert result["report"]["status"] == ("pass" if actual else "fail")
    assert len(calls.calls) == len(executor.calls) == 1
    request = calls.calls[0]
    assert request["kind"] == "public-revision" and request["repeat"] == original.repeat
    assert request["max_tokens"] == 2048
    assert revision.revise_public(row, original, skill, calls, executor, tmp_path) == result
    assert len(calls.calls) == len(executor.calls) == 1


def test_prompt_whitelist_excludes_all_host_metadata_and_labels(tmp_path):
    result, _, _, calls, _ = invoke(tmp_path, outcomes=({"actual": False, "exception": "ValueError"},))
    request = calls.calls[0]
    assert SECRET not in request["system"] + request["user"]
    payload = json.loads(request["user"])
    assert set(payload) == {"task", "solution.py", "optional_skill", "public_assertions", "public_execution"}
    assert payload["solution.py"] == CODE
    assert payload["public_assertions"][0]["input"] == {"args": [[1, 2]], "kwargs": {}}
    assert payload["public_assertions"][0]["information_origin"] == "public_assertion_not_absolute_ground_truth"
    observation = payload["public_execution"]["observations"][0]
    assert observation["input"] == {"args": [], "kwargs": {}}  # Actual wrapper call, not a fabricated per-case run.
    assert observation["expected"] is True and observation["observed"] is False
    assert observation["expected_origin"] == "public_assertion_not_absolute_ground_truth"
    assert observation["exception"] == "ValueError"
    assert result["record"]["hidden_feedback_used"] is False


@pytest.mark.parametrize("after", [True, False])
def test_revision_has_two_separate_stages_and_is_selected_without_best_of_two(tmp_path, after):
    result, _, original, calls, executor = invoke(tmp_path,
        response=json.dumps({"solution.py": REVISED}), outcomes=({"actual": True}, {"actual": after}))
    record, selected = result["record"], result["artifact"]
    assert record["status"] == "revised" and selected != original
    assert selected.repeat == original.repeat and selected.skill_hash == original.skill_hash
    assert selected.condition == original.condition and selected.task_hash == original.task_hash
    assert selected.files[1] == original.files[1]
    assert len(calls.calls) == 1 and len(executor.calls) == 2
    assert record["draft_stage"]["report"]["status"] == "pass"
    assert record["revised_stage"]["report"]["status"] == ("pass" if after else "fail")
    assert result["report"] == record["revised_stage"]["report"]
    assert record["selected_artifact_hash"] == selected.content_hash
    assert verify(json.loads((tmp_path / "artifacts" / (original.content_hash + ".json")).read_text())) == original.sealed()
    assert (tmp_path / "artifacts" / (selected.content_hash + ".json")).exists()
    assert record["fixture_only"] and not record["formal_effect_estimate"]


@pytest.mark.parametrize("response", [None, "KEEP because it passes", "{}", "not JSON",
    '{"solution.py":"x", "solution.py":"y"}',
    '{"solution.py":""}', '{"solution.py":"pass", "public_runner.py":"pass"}'])
def test_parse_failure_explicitly_retains_draft_without_retry(tmp_path, response):
    result, row, original, calls, executor = invoke(tmp_path, response=response, outcomes=({"actual": False},))
    assert result["record"]["status"] == "fallback"
    assert result["record"]["reason"] == "parse_failure_no_retry"
    assert result["artifact"] == original and result["report"]["status"] == "fail"
    assert revision.revise_public(row, original, "", calls, executor, tmp_path) == result
    assert len(calls.calls) == len(executor.calls) == 1


def test_api_failure_receipt_is_terminal_visible_fallback(tmp_path):
    row, calls, executor = fixture_row(), FixtureCalls(ok=False), FixtureExecutor({"actual": False})
    original = artifact(row)
    result = revision.revise_public(row, original, "", calls, executor, tmp_path)
    assert result["artifact"] == original and result["record"]["status"] == "fallback"
    assert result["record"]["reason"] == "api_failure_no_retry"
    assert not result["record"]["api_receipt"]["ok"]
    assert not result["record"]["revision_opportunity_completed"]
    assert result["record"]["retry_authorized"] is False
    assert revision.revise_public(row, original, "", calls, executor, tmp_path) == result
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("error", [ValueError("Provider request binding changed"),
    AssertionError("fixture protocol assertion"), RuntimeError("fixture unknown failure"),
    OSError("fixture transport failure"), TimeoutError("fixture timeout")])
def test_api_exception_without_receipt_preserves_intent_and_requires_recovery(tmp_path, error):
    row, calls, executor = fixture_row(), FixtureCalls(error=error), FixtureExecutor()
    original = artifact(row)
    with pytest.raises(type(error), match=str(error)):
        revision.revise_public(row, original, "", calls, executor, tmp_path)
    base = tmp_path / "public_revision" / original.content_hash
    assert (base / "intent.json").exists() and (base / "draft.json").exists()
    assert not (base / "record.json").exists()
    with pytest.raises(ValueError, match="explicit recovery required"):
        revision.revise_public(row, original, "", calls, executor, tmp_path)
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("availability", ["api_failure", "parse_failure"])
def test_unavailable_artifact_is_skipped_without_execution(tmp_path, availability):
    result, _, original, calls, executor = invoke(tmp_path, availability=availability)
    assert result["artifact"] == original and result["record"]["status"] == "skipped"
    assert result["record"]["reason"] == "artifact_unavailable" and result["report"] is None
    assert result["record"]["public_status"] == "unknown" and not calls.calls and not executor.calls


@pytest.mark.parametrize("status", ["unsupported", "execution_error"])
def test_unsupported_execution_is_unknown_and_skipped(tmp_path, status):
    result, _, original, calls, executor = invoke(tmp_path, outcomes=({"status": status},))
    assert result["artifact"] == original and result["record"]["status"] == "skipped"
    assert result["report"]["status"] == "unknown"
    assert not calls.calls and len(executor.calls) == 1


def test_executor_exception_is_unknown_and_never_retried(tmp_path):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor(error=RuntimeError("fixture unavailable"))
    original = artifact(row)
    result = revision.revise_public(row, original, "", calls, executor, tmp_path)
    assert result["report"]["status"] == "unknown" and result["record"]["status"] == "skipped"
    assert revision.revise_public(row, original, "", calls, executor, tmp_path) == result
    assert not calls.calls and len(executor.calls) == 1


@pytest.mark.parametrize("task_key", ["task", "public_task"])
def test_conflicting_assertions_abstain_before_execution_or_api(tmp_path, task_key):
    row = fixture_row()
    task, calls, executor = row[task_key], FixtureCalls(), FixtureExecutor()
    contradiction = replace(task.public_cases[0], id="contradiction", expected_json="99")
    row[task_key] = replace(task, public_cases=task.public_cases + (contradiction,))
    result = revision.revise_public(row, artifact(row), "", calls, executor, tmp_path)
    assert result["record"]["reason"] == "conflicting_public_assertions_abstain"
    assert result["record"]["public_status"] == "unknown"
    assert not calls.calls and not executor.calls


def test_missing_expected_is_unknown_and_cannot_trigger_revision(tmp_path):
    row = fixture_row()
    task = row["public_task"]
    row["public_task"] = replace(task, public_cases=(replace(task.public_cases[0], expected_json=None),))
    calls, executor = FixtureCalls(), FixtureExecutor()
    result = revision.revise_public(row, artifact(row), "", calls, executor, tmp_path)
    assert result["report"]["status"] == "unknown" and not calls.calls


def test_same_source_different_skills_has_different_revision_request(tmp_path):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor()
    for skill in ("first advice", "second advice"):
        revision.revise_public(row, artifact(row, skill=skill, condition="candidate"), skill, calls, executor, tmp_path)
    assert len(calls.calls) == 2 and digest(calls.calls[0]) != digest(calls.calls[1])
    assert json.loads(calls.calls[0]["user"])["solution.py"] == json.loads(calls.calls[1]["user"])["solution.py"]


def test_wrong_skill_task_or_wrapper_is_rejected_before_execution(tmp_path):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor()
    original = artifact(row)
    with pytest.raises(ValueError, match="Skill"):
        revision.revise_public(row, original, "wrong", calls, executor, tmp_path)
    with pytest.raises(ValueError, match="another task"):
        revision.revise_public(row, replace(original, task_hash="0" * 64), "", calls, executor, tmp_path)
    row["public_wrapper"] = {"path": "public_runner.py", "content": "# changed wrapper"}
    with pytest.raises(ValueError, match="wrapper"):
        revision.revise_public(row, original, "", calls, executor, tmp_path)
    assert not calls.calls and not executor.calls


def test_bad_execution_source_binding_is_rejected_without_revision(tmp_path):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor({"source_hash": "0" * 64})
    with pytest.raises(ValueError, match="another input, source or executor"):
        revision.revise_public(row, artifact(row), "", calls, executor, tmp_path)
    assert not calls.calls


def test_resealed_report_tampering_is_caught_by_receipt_replay(tmp_path):
    result, row, original, calls, executor = invoke(tmp_path)
    record = deepcopy(result["record"])
    stage = record["draft_stage"]
    stage["report"]["status"] = "fail"
    stage["report"] = reseal(stage["report"])
    record["draft_stage"] = reseal(stage)
    record["public_status"] = "fail"
    path = tmp_path / "public_revision" / original.content_hash / "record.json"
    path.write_text(json.dumps(reseal(record)))
    with pytest.raises(ValueError, match="receipt replay"):
        revision.revise_public(row, original, "", calls, executor, tmp_path)
    assert len(calls.calls) == len(executor.calls) == 1


@pytest.mark.parametrize("response", ["KEEP", json.dumps({"solution.py": REVISED})])
def test_interrupted_operation_preserves_completed_stages_and_requires_recovery(tmp_path, response):
    result, row, original, calls, executor = invoke(tmp_path, response=response)
    base = tmp_path / "public_revision" / original.content_hash
    terminal = base / "record.json"
    terminal.unlink()  # Simulates interruption before the final selection was persisted.
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    executions = len(executor.calls)
    if result["record"]["status"] == "revised":
        assert (base / "revised.json").exists()
        assert (tmp_path / "artifacts" / (result["artifact"].content_hash + ".json")).exists()
    with pytest.raises(ValueError, match="Interrupted public revision retained; explicit recovery"):
        revision.revise_public(row, original, "", calls, executor, tmp_path)
    assert not terminal.exists()
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")} == before
    assert len(calls.calls) == 1 and len(executor.calls) == executions


def test_selected_revision_cannot_receive_another_revision_opportunity(tmp_path):
    result, row, _, calls, executor = invoke(tmp_path, response=json.dumps({"solution.py": REVISED}))
    with pytest.raises(ValueError, match="second revision opportunity"):
        revision.revise_public(row, result["artifact"], "", calls, executor, tmp_path)
    assert len(calls.calls) == 1 and len(executor.calls) == 2


def test_concurrent_calls_share_one_revision_and_check(tmp_path):
    row, calls, executor = fixture_row(), FixtureCalls(), FixtureExecutor()
    original = artifact(row)
    with ThreadPoolExecutor(max_workers=3) as pool:
        values = list(pool.map(lambda _: revision.revise_public(row, original, "", calls, executor, tmp_path), range(3)))
    assert values[0] == values[1] == values[2]
    assert len(calls.calls) == len(executor.calls) == 1


def test_fixture_executor_cannot_be_used_for_production_artifacts(tmp_path):
    row, calls = fixture_row(), FixtureCalls()
    calls.api.service = {"provider": "BIGMODEL"}
    with pytest.raises(ValueError, match="SSH isolated"):
        revision.revise_public(row, replace(artifact(row), provenance_kind="model"), "", calls, FixtureExecutor(), tmp_path)
    assert not calls.calls


@pytest.mark.parametrize("condition,skill", [("no_skill", ""), ("current", "Parent advice"), ("candidate", "New advice")])
def test_initial_solver_declares_public_revision_and_persists_provider_provenance(tmp_path, condition, skill):
    calls = FixtureCalls(json.dumps({"solution.py": CODE}))
    result = revision.solve_public_initial(fixture_row(), skill, condition, 3, calls, tmp_path)
    request = calls.calls[0]
    assert request["kind"] == "public-initial" and request["repeat"] == 3 and request["max_tokens"] == 2048
    assert "one later revision opportunity" in request["system"]
    assert "No hidden audit feedback" in request["system"]
    assert SECRET not in request["system"] + request["user"]
    assert result.availability == "available" and result.provenance_kind == "fixture"
    assert result.source_ref.startswith("bigmodel-request:")
    assert (tmp_path / "artifacts" / (result.content_hash + ".json")).exists()
    assert (tmp_path / "public_initial" / (result.content_hash + ".json")).exists()


@pytest.mark.parametrize("response,ok,availability", [("bad", True, "parse_failure"), (None, False, "api_failure")])
def test_initial_delivery_failures_stay_unavailable(tmp_path, response, ok, availability):
    calls = FixtureCalls(response, ok=ok)
    result = revision.solve_public_initial(fixture_row(), "", "no_skill", 0, calls, tmp_path)
    assert result.availability == availability and not result.files


def test_historical_complete_json_fence_tolerance_is_unchanged(tmp_path):
    response = "```json\n" + json.dumps({"solution.py": REVISED}) + "\n```"
    calls = FixtureCalls(response)
    original = revision.solve_public_initial(fixture_row(), "", "no_skill", 0, calls, tmp_path)
    assert original.availability == "available" and original.files[0].content == REVISED
    result = revision.revise_public(fixture_row(), original, "", calls, FixtureExecutor(), tmp_path)
    assert result["record"]["status"] == "revised" and result["artifact"].files[0].content == REVISED


def test_bad_api_receipt_prompt_binding_is_rejected(tmp_path):
    calls = FixtureCalls()
    call = calls.call

    def wrong(*args, **kwargs):
        receipt = call(*args, **kwargs)
        receipt["request"]["repeat"] += 1
        receipt["request_hash"] = digest(receipt["request"])
        return receipt

    calls.call = wrong
    row = fixture_row()
    with pytest.raises(ValueError, match="another prompt, repeat"):
        revision.revise_public(row, artifact(row), "", calls, FixtureExecutor(), tmp_path)
