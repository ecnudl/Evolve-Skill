"""Offline engineering checks; no model, generated code or network runs here."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import admissibility as a
from skillopt.skill_validation.task_probes import parse_probes
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import ScriptedExecutor, artifact, task


def proposal(t, *, expected=3, duplicate=False):
    p = {"kind": "expected", "calls": [{"args": [[1, 2]], "kwargs": {}}], "expected": expected,
         "obligation_id": "returns", "contract_quote": "Return the total for [1, 2].", "rationale": "Public example"}
    return parse_probes({"probes": [p, deepcopy(p)] if duplicate else [p]}, t)


class Calls:
    def __init__(self, *, decision="keep", code="contract_supported", question="", invalid=False, ok=True):
        self.requests = []
        self.decision, self.code, self.question, self.invalid, self.ok = decision, code, question, invalid, ok

    def call(self, system, user, kind, **kwargs):
        self.requests.append((system, user, kind))
        rows = [{"probe_id": p["probe_id"], "decision": self.decision, "reason_code": self.code,
                 "reason": "Fixture judgment", "fact_question": self.question} for p in json.loads(user)["checks"]]
        return {"ok": self.ok, "request_hash": digest(user),
                "response": "not JSON" if self.invalid else json.dumps({"checks": rows})}


def test_blind_view_excludes_artifact_identity_and_source_extras():
    t = task()
    source = {"source_id": "public", "text": "Some public fact", "information_origin": "research_document",
              "private": "HIDDEN_SENTINEL"}
    system, user = a.messages(t, a.inventory(t, proposal(t)), [source])
    assert "HIDDEN_SENTINEL" not in user and "condition" not in user
    assert "No implementation" in system and "Never repair" in system
    assert "solution.py" not in user


def test_content_ids_duplicate_checks_and_public_conflict(tmp_path):
    t = task()
    p = proposal(t, duplicate=True)
    inv = a.inventory(t, p)
    assert inv["original_checks"] == 2 and inv["unique_checks"] == 1 and inv["duplicate_checks"] == 1
    assert inv["items"][0]["probe_id"] == a.inventory(t, proposal(t))["items"][0]["probe_id"]
    calls = Calls()
    rejected = a.review_proposal(t, proposal(t, expected=99), calls, tmp_path, pipeline_hash=digest("pipeline"))
    assert not calls.requests
    assert rejected["decisions"][0]["reason_code"] == "conflicts_with_public_example"
    assert rejected["decisions"][0]["decision"] == "abstain"


def test_conflicting_public_examples_are_not_resolved_by_reference_or_reviewer(tmp_path):
    t = task()
    t = replace(t, public_cases=t.public_cases + (replace(t.public_cases[0], id="conflict", expected_json="4"),))
    r = a.review_proposal(t, proposal(t), Calls(), tmp_path, pipeline_hash=digest("pipeline"))
    assert r["decisions"][0]["reason_code"] == "conflicting_public_examples"


@pytest.mark.parametrize("expected,public", [
    (20, 20.0), (20.0, 20), (0, -0.0),
    ([20, {"value": [1, 2.5, True, None]}], [20.0, {"value": [1.0, 2.5, True, None]}]),
    ({"a": 3, "b": [4, 5]}, {"b": [4.0, 5.0], "a": 3.0}),
])
def test_numeric_representation_difference_is_eligible_not_coerced_or_certified(expected, public):
    t = task(expected=json.dumps(public))
    p = proposal(t, expected=expected)
    original_hash = p["record_hash"]
    result = a.inventory(t, p)
    assert result["items"][0]["mechanical_status"] == "eligible"
    assert result["items"][0]["mechanical_reason"] is None
    assert digest(result["items"][0]["probe"]["expected"]) == digest(expected)
    assert p["record_hash"] == original_hash and t.public_cases[0].expected_json == json.dumps(public)
    assert result["public_call_binding"] == "exact_json_types_and_values"


@pytest.mark.parametrize("expected,public", [
    (True, 1), (1, True), (False, 0.0), ({"a": [True]}, {"a": [1.0]}),
    (20, 20.5), ("20", 20), ([1, 2], [2.0, 1.0]), ([1], [1.0, 2]),
    ({"a": 1}, {"b": 1.0}), (2**53 + 1, float(2**53)),
])
def test_bool_structure_and_true_value_disagreements_remain_blocked(expected, public):
    t = task(expected=json.dumps(public))
    result = a.inventory(t, proposal(t, expected=expected))
    assert result["items"][0]["mechanical_status"] == "blocked"
    assert result["items"][0]["mechanical_reason"] == "conflicts_with_public_example"


def test_equivalent_public_numeric_encodings_do_not_create_fake_public_conflict():
    t = task(expected="20")
    t = replace(t, public_cases=t.public_cases + (replace(t.public_cases[0], id="float-copy", expected_json="20.0"),))
    assert a.inventory(t, proposal(t, expected=20))["items"][0]["mechanical_status"] == "eligible"
    t = replace(t, public_cases=t.public_cases + (replace(t.public_cases[0], id="actual-conflict", expected_json="21"),))
    assert a.inventory(t, proposal(t, expected=20))["items"][0]["mechanical_reason"] == "conflicting_public_examples"


def test_numeric_input_types_remain_exactly_bound_not_assumed_equivalent():
    t = task(expected="99")
    t = replace(t, public_cases=(replace(t.public_cases[0], arguments_json='{"args":[[1.0,2]],"kwargs":{}}'),))
    # The int-input hypothesis cannot be mechanically judged from a float-input
    # public example: user programs are allowed to distinguish their types.
    assert a.inventory(t, proposal(t, expected=3))["items"][0]["mechanical_status"] == "eligible"


def test_numeric_precheck_does_not_change_actual_probe_execution_comparator(tmp_path):
    t, pipeline = task(expected="20.0"), digest("pipeline")
    p = proposal(t, expected=20)
    review = a.review_proposal(t, p, Calls(), tmp_path / "review", pipeline_hash=pipeline)
    executed = a.execute_admitted(t, artifact(t), p, review,
        ScriptedExecutor([{"actual": 20.0, "cleanup_confirmed": True}]), tmp_path / "execution", pipeline_hash=pipeline)
    assert executed["probe_status"] == "mismatch"  # Still the existing exact JSON probe comparator.


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_values_are_never_numerically_equivalent(value):
    assert not a._public_values_equivalent(value, value)


def test_duplicate_or_missing_ids_do_not_invalidate_unambiguous_other_rows():
    first = {"probe_id": "a", "decision": "keep", "reason_code": "contract_supported", "reason": "ok", "fact_question": ""}
    second = {**first, "probe_id": "b"}
    parsed = a.parse_decisions(json.dumps({"checks": [first, first, second]}), ["a", "b"])
    assert [r["decision"] for r in parsed] == ["unknown", "keep"]
    with pytest.raises(ValueError):
        a.parse_decisions(json.dumps({"checks": [{**first, "probe_id": "unbound"}]}), ["a"])
    assert a.parse_decisions(json.dumps({"checks": [first]}), ["a", "b"])[1]["decision"] == "unknown"


@pytest.mark.parametrize("override", [
    {"expected": 3}, {"decision": "replace"}, {"decision": True}, {"reason_code": []},
    {"reason_code": "missing_external_fact"}, {"fact_question": "invented unnecessary question"},
    {"reason_code": "document_supported"},
])
def test_invalid_individual_semantics_are_unknown_not_repaired(override):
    row = {"probe_id": "a", "decision": "keep", "reason_code": "contract_supported", "reason": "ok", "fact_question": ""}
    result = a.parse_decisions(json.dumps({"checks": [{**row, **override}]}), ["a"])
    assert result[0]["decision"] == "unknown"


@pytest.mark.parametrize("raw", ['{"checks":[],"checks":[]}', '```json\n{}', 'prefix {"checks":[]}', '{"checks":NaN}'])
def test_broken_json_is_not_repaired(raw):
    with pytest.raises(ValueError): a.parse_decisions(raw, ["a"])


@pytest.mark.parametrize("options,state,decision", [
    ({"invalid": True}, "format_invalid", "unknown"),
    ({"ok": False}, "review_unavailable", "unknown"),
    ({"decision": "abstain", "code": "ambiguous_contract"}, "reviewed", "abstain"),
    ({"decision": "abstain", "code": "missing_external_fact", "question": "Does this API mutate its argument?"},
     "reviewed", "abstain"),
])
def test_review_failure_semantic_abstain_and_missing_fact_are_distinct(tmp_path, options, state, decision):
    t, calls = task(), Calls(**options)
    r = a.review_proposal(t, proposal(t), calls, tmp_path, pipeline_hash=digest("pipeline"))
    assert r["status"] == state and r["decisions"][0]["decision"] == decision
    assert a.review_proposal(t, proposal(t), calls, tmp_path, pipeline_hash=digest("pipeline")) == r
    assert len(calls.requests) == 1
    e = ScriptedExecutor()
    execution = a.execute_admitted(t, artifact(t), proposal(t), r, e, tmp_path, pipeline_hash=digest("pipeline"))
    assert not e.calls and execution["probe_status"] == "not_executed"
    assert execution["execution_report"] is None and execution["feedback_authorized"] is False


def test_kept_checks_execute_after_review_and_replay_without_new_calls(tmp_path):
    t, calls, e = task(), Calls(), ScriptedExecutor([{"cleanup_confirmed": True}])
    p = proposal(t, duplicate=True)
    r = a.review_proposal(t, p, calls, tmp_path, pipeline_hash=digest("pipeline"))
    result = a.execute_admitted(t, artifact(t), p, r, e, tmp_path, pipeline_hash=digest("pipeline"))
    assert result["retained_checks"] == 1 and result["original_checks"] == 2
    assert result["probe_status"] == "match" and len(e.calls) == 1
    assert a.execute_admitted(t, artifact(t), p, r, e, tmp_path, pipeline_hash=digest("pipeline")) == result
    assert len(e.calls) == 1
    with pytest.raises(ValueError, match="pipeline"):
        a.execute_admitted(t, artifact(t), p, r, e, tmp_path, pipeline_hash=digest("changed"))


def test_wrong_artifact_is_rejected_even_when_nothing_is_retained(tmp_path):
    t, calls = task(), Calls(decision="abstain", code="ambiguous_contract")
    p = proposal(t)
    r = a.review_proposal(t, p, calls, tmp_path, pipeline_hash=digest("pipeline"))
    other = replace(t, contract=replace(t.contract, prompt=t.contract.prompt + " Other task."))
    with pytest.raises(ValueError, match="Artifact/task"):
        a.execute_admitted(t, artifact(other), p, r, ScriptedExecutor(), tmp_path, pipeline_hash=digest("pipeline"))


def test_review_cannot_be_rebound_to_a_different_proposal(tmp_path):
    t = task()
    r = a.review_proposal(t, proposal(t), Calls(), tmp_path, pipeline_hash=digest("pipeline"))
    with pytest.raises(ValueError, match="Mismatched"):
        a.execute_admitted(t, artifact(t), proposal(t, expected=99), r, ScriptedExecutor(), tmp_path,
                           pipeline_hash=digest("pipeline"))


def test_deeply_nested_json_is_recorded_invalid_not_retried(tmp_path):
    class Nested(Calls):
        def call(self, *args, **kwargs):
            receipt = super().call(*args, **kwargs)
            return {**receipt, "response": '{"checks":' + '[' * 2000 + '0' + ']' * 2000 + '}'}
    t, calls = task(), Nested()
    r = a.review_proposal(t, proposal(t), calls, tmp_path, pipeline_hash=digest("pipeline"))
    assert r["status"] == "format_invalid" and r["decisions"][0]["decision"] == "unknown"
    assert len(calls.requests) == 1


@pytest.mark.parametrize("change", [
    {"status": "review_unavailable"}, {"status": "format_invalid"}, {"status": "no_eligible_checks"},
    {"request_hash": None}, {"feedback_authorized": True}, {"deployment_authorized": True},
])
def test_resealed_inconsistent_review_is_rejected(tmp_path, change):
    t, p = task(), proposal(task())
    r = a.review_proposal(t, p, Calls(), tmp_path, pipeline_hash=digest("pipeline"))
    invalid = seal({**{k:v for k,v in r.items() if k != "record_hash"}, **change})
    with pytest.raises(ValueError):
        a.execute_admitted(t, artifact(t), p, invalid, ScriptedExecutor(), tmp_path, pipeline_hash=digest("pipeline"))


def test_research_is_not_called_for_arithmetic_or_ambiguous_rejections(tmp_path, monkeypatch):
    from skillopt.skill_validation import probe_fact_research as facts
    monkeypatch.setattr(facts, "resolve_gap", lambda *args, **kwargs: pytest.fail("No external fact gap"))
    t, p = task(), proposal(task())
    calls = Calls(decision="abstain", code="expected_inconsistent")
    r = a.review_proposal(t, p, calls, tmp_path, pipeline_hash=digest("pipeline"))
    result = a.resolve_external_gaps(t, p, r, calls, tmp_path, pipeline_hash=digest("pipeline"))
    assert result["trigger_count"] == 0 and len(calls.requests) == 1


def test_specific_fact_can_only_trigger_review_of_unchanged_check(tmp_path, monkeypatch):
    from tests.test_skill_validation_probe_fact_research import Calls as FactCalls, Fetcher, plan, selection
    t, p, pipeline = task(), proposal(task()), digest("pipeline")
    question = "What does the relevant language operation guarantee?"
    initial = a.review_proposal(t, p, Calls(decision="abstain", code="missing_external_fact", question=question),
                                tmp_path, pipeline_hash=pipeline)
    pid = initial["decisions"][0]["probe_id"]
    calls = FactCalls([plan(), selection(), {"checks": [{"probe_id": pid, "decision": "keep",
        "reason_code": "document_supported", "reason": "Fixture judgment, not real research efficacy", "fact_question": ""}]}])
    fetcher = Fetcher()
    resolution = a.resolve_external_gaps(t, p, initial, calls, tmp_path, pipeline_hash=pipeline, source_fetcher=fetcher)
    assert calls.requests[0][1]["probe"] == p["probes"][0] and resolution["rescued_check_count"] == 1
    assert resolution["gaps"][0]["proposal"]["probes"] == p["probes"]
    assert len(calls.requests) == 3 and calls.requests[2][1]["sources"][0]["source_id"] == "fixture-document-s0"
    e = ScriptedExecutor([{"cleanup_confirmed": True}])
    result = a.execute_resolved(t, artifact(t), p, initial, resolution, e, tmp_path, pipeline_hash=pipeline)
    assert result["base"]["probe_status"] == "not_executed" and result["probe_status"] == "match"
    assert result["retained_checks"] == 1 and len(e.calls) == 1
    changed = deepcopy(resolution)
    changed["gaps"][0]["proposal"]["probes"][0]["expected"] = 100
    changed = seal({k:v for k,v in changed.items() if k != "record_hash"})
    with pytest.raises(ValueError, match="cannot rewrite"):
        a.execute_resolved(t, artifact(t), p, initial, changed, e, tmp_path / "invalid", pipeline_hash=pipeline)
    assert len(e.calls) == 1
    changed = deepcopy(resolution)
    fact = changed["gaps"][0]["fact_result"]
    fact["sources"][0]["text"] = "Unbound invented fact"
    changed["gaps"][0]["fact_result"] = seal({k:v for k,v in fact.items() if k != "record_hash"})
    changed = seal({k:v for k,v in changed.items() if k != "record_hash"})
    with pytest.raises(ValueError, match="disagree"):
        a.execute_resolved(t, artifact(t), p, initial, changed, e, tmp_path / "invalid2", pipeline_hash=pipeline)
    assert len(e.calls) == 1
    fetcher.identity = {"kind": "changed"}
    with pytest.raises(ValueError):
        a.resolve_external_gaps(t, p, initial, calls, tmp_path, pipeline_hash=pipeline, source_fetcher=fetcher)
    assert len(calls.requests) == 3


def test_caller_declared_fact_cannot_impersonate_review_discovered_resolution(tmp_path):
    from skillopt.skill_validation import probe_fact_research as facts
    from tests.test_skill_validation_probe_fact_research import Calls as FactCalls, Fetcher, plan
    t, p, pipeline = task(), proposal(task()), digest("pipeline")
    question = "What does the relevant language operation guarantee?"
    initial = a.review_proposal(t, p, Calls(decision="abstain", code="missing_external_fact", question=question),
                                tmp_path / "initial", pipeline_hash=pipeline)
    fetcher = Fetcher()
    resolution = a.resolve_external_gaps(t, p, initial, FactCalls([plan("no_update")]),
        tmp_path / "resolved", pipeline_hash=pipeline, source_fetcher=fetcher)
    assert resolution["research_binding"]["question_origin"] == facts.REVIEW_QUESTION_ORIGIN
    declared = facts.resolve_gap(t, p["probes"][0], question, FactCalls([plan("no_update")]),
        tmp_path / "caller", pipeline_hash=pipeline, source_fetcher=fetcher,
        question_origin="caller_declared_fixture_gap")
    changed = deepcopy(resolution)
    changed["gaps"][0]["fact_result"] = declared
    changed = seal({k: v for k, v in changed.items() if k != "record_hash"})
    executor = ScriptedExecutor()
    with pytest.raises(ValueError, match="identity"):
        a.execute_resolved(t, artifact(t), p, initial, changed, executor, tmp_path / "execute", pipeline_hash=pipeline)
    assert not executor.calls
    changed["research_binding"]["question_origin"] = "caller_declared_fixture_gap"
    changed = seal({k: v for k, v in changed.items() if k != "record_hash"})
    with pytest.raises(ValueError, match="question origin"):
        a.execute_resolved(t, artifact(t), p, initial, changed, executor, tmp_path / "execute", pipeline_hash=pipeline)
    assert not executor.calls
