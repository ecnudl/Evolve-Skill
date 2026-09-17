import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v4 import runtime as rt
from skillopt.validator_pilot.api import digest


def task_for():
    files = {"api.py": "import calculation\ndef solve(data):\n    return calculation.double(data['x'])\n",
             "calculation.py": "def double(value):\n    return value\n"}
    reference = {**files, "calculation.py": "def double(value):\n    return value * 2\n"}
    def case(label, value, public):
        return {"label": label, "input": {"x": value}, "expected": value * 2, "exception": None,
                "public": public, "dimension": "requested_behavior" if public else "preserved_behavior"}
    return RepoTask("runtime_unit", "dev", "unit", "unit", "Return twice x without mutating the input.",
                    files, reference, list(files), {}, [case("public", 2, True)],
                    [case("private_DO_NOT_SEND", 617, False)], {"private_metadata": "NEVER_SEND"})


class FakeAPI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, dict):
            return {"request_hash": digest(self.calls[-1]), **response}
        return {"ok": True, "response": response, "request_hash": digest(self.calls[-1])}


def delivery(code="def double(value):\n    return value * 2\n"):
    return rt.serialize_delivery({"calculation.py": code})


def test_roundtrip_real_code_without_json_escaping():
    task = task_for()
    raw = delivery("def double(value):\n    text='quoted \\\"record\\\"'\n    return value * 2\n")
    assert "\\n" not in raw
    files = rt.parse_delivery(task, raw)
    assert files["api.py"] == task.files["api.py"]
    assert "text='quoted" in files["calculation.py"]


@pytest.mark.parametrize("raw", [
    "", "KEEP", '{"files":{}}', "```python\n" + delivery() + "```",
    "Explanation\n" + delivery(), delivery() + "Commentary", delivery() + delivery(),
    "<<<FILE ../calculation.py>>>\nx=1\n<<<END FILE>>>\n",
    "<<<FILE new.py>>>\nx=1\n<<<END FILE>>>\n",
    "<<<FILE calculation.py>>>\nx=1\n",
    "<<<FILE calculation.py>>>\n<<<FILE api.py>>>\nx=1\n<<<END FILE>>>\n<<<END FILE>>>\n",
    "<<<FILE calculation.py>>>\n\n<<<END FILE>>>\n",
    "<<<FILE calculation.py>>>\nimport os\n<<<END FILE>>>\n",
])
def test_delivery_rejects_ambiguity_and_unsafe_code(raw):
    with pytest.raises((ValueError, SyntaxError)):
        rt.parse_delivery(task_for(), raw)


def test_protected_file_not_accepted():
    task = replace(task_for(), editable_paths=["calculation.py"])
    with pytest.raises(ValueError, match="protected"):
        rt.parse_delivery(task, rt.serialize_delivery({"api.py": task.files["api.py"]}))


@pytest.mark.parametrize("files", [{}, {"../x.py": "a=1"}, {"x.py": ""}, {"x.py": "<<<END FILE>>>\n"}])
def test_serialize_rejects_unsafe_or_ambiguous_delimiters(files):
    with pytest.raises(ValueError):
        rt.serialize_delivery(files)


def test_invalid_delivery_is_known_failure_without_process(monkeypatch):
    monkeypatch.setattr(rt.executor, "run_payload", lambda _: pytest.fail("invalid code was executed"))
    result = rt.evaluate_delivery(task_for(), "bad", public_only=False)
    assert result["execution_ok"] is True
    assert result["hard"] is False
    assert result["passed_tests"] == 0 and result["total_tests"] == 4
    assert result["delivery_error"]


def test_real_two_turn_public_repair_and_no_private_leak():
    task = task_for()
    api = FakeAPI([delivery("def double(value):\n    return value\n"), delivery()])
    record = rt.solve(api, task, "Check public examples.", key="unit", repeat=0)
    assert len(api.calls) == 2 and record["solver_calls"] == 2
    assert record["initial_evaluation"]["hard"] is False
    assert record["evaluation"]["hard"] is True
    assert record["evaluation"]["total_tests"] == 4
    for call in api.calls:
        assert "private_DO_NOT_SEND" not in call["user"]
        assert "617" not in call["user"]
        assert "1234" not in call["user"]
        assert "reference_files" not in call["user"]
        assert "NEVER_SEND" not in call["user"]
        assert call["max_tokens"] == rt.TARGET_TOKENS
    repair = json.loads(api.calls[1]["user"])
    observed = repair["public_test_feedback"]["observations"][0]
    assert observed["actual"] == 2 and observed["expected"] == 4
    assert record["initial_evaluation"]["private_diagnostics"] == []
    assert record["response"] == rt.serialize_delivery(record["files"])


def test_public_pass_still_uses_revision_and_keep():
    api = FakeAPI([delivery(), "KEEP"])
    record = rt.solve(api, task_for(), "", key="unit", repeat=1, public_only=True)
    assert len(api.calls) == 2 and record["revision_kept"] is True
    assert record["evaluation"]["total_tests"] == 2
    assert record["evaluation"]["hard"] is True


def test_revision_omissions_keep_initial_files_not_original_starter():
    task = task_for()
    api = FakeAPI([delivery(), rt.serialize_delivery({"api.py": task.files["api.py"]})])
    record = rt.solve(api, task, "", key="unit", repeat=0)
    assert record["evaluation"]["hard"] is True
    assert record["files"]["calculation.py"] == task.reference_files["calculation.py"]


def test_invalid_initial_can_be_fixed_but_not_kept():
    api = FakeAPI(["bad first response", delivery()])
    record = rt.solve(api, task_for(), "", key="unit", repeat=0)
    assert record["evaluation"]["hard"] is True
    api = FakeAPI(["bad first response", "KEEP"])
    record = rt.solve(api, task_for(), "", key="unit", repeat=0)
    assert record["evaluation"]["hard"] is False and record["files"] is None


@pytest.mark.parametrize("first", [True, False])
def test_unavailable_call_is_not_a_silent_extra_retry(first):
    responses = [{"ok": False, "response": "truncated"}, delivery()] if first else [delivery(), {"ok": False, "response": ""}]
    api = FakeAPI(responses)
    record = rt.solve(api, task_for(), "", key="unit", repeat=0)
    assert len(api.calls) == 2
    if first:
        assert record["initial_evaluation"]["hard"] is None
        assert record["evaluation"]["hard"] is True
    else:
        assert record["evaluation"]["hard"] is None
        assert record["target_ok"] is False


def test_identical_content_has_identical_keys_but_repetition_and_skill_are_bound():
    calls = []
    for skill, repeat in [("", 0), ("", 0), ("new skill", 0), ("", 1)]:
        api = FakeAPI([delivery(), "KEEP"])
        rt.solve(api, task_for(), skill, key="policy_free", repeat=repeat)
        calls.append(api.calls)
    assert calls[0] == calls[1]
    assert len({calls[i][0]["key"] for i in (0, 2, 3)}) == 3


def test_failed_private_input_reaches_learning_packet_only():
    task = task_for()
    api = FakeAPI([delivery("def double(value):\n    return 4\n"), "KEEP"])
    record = rt.solve(api, task, "Avoid mutation.", key="unit", repeat=0)
    learn = rt.failure_packet(task, record, phase="learn2")
    gate = rt.failure_packet(task, record, phase="gate2")
    assert learn["classification"] == "semantic"
    assert learn["failed_cases"][0]["input"] == {"x": 617}
    assert learn["failed_cases"][0]["expected"] == 1234
    assert learn["failed_cases"][0]["actual"] == 4
    assert learn["files"] == record["files"]
    assert learn["skill"] == "Avoid mutation."
    assert "reference_files" not in learn
    assert gate["classification"] == "no_observed_failure" and gate["failed_cases"] == []
    assert "private_DO_NOT_SEND" not in json.dumps(gate)
    copied = dict(learn)
    assert copied.pop("evidence_hash") == digest(copied)


@pytest.mark.parametrize("phase", ["holdout", "final", "shadow", "calibration", "test", "learn", "source"])
def test_no_feedback_from_sealed_phases(phase):
    with pytest.raises(ValueError, match="development"):
        rt.failure_packet(task_for(), {}, phase=phase)


@pytest.mark.parametrize("split", ["test", "holdout", "final", "shadow", "calibration", "eval"])
def test_wrongly_relabelled_heldout_task_not_accepted(split):
    with pytest.raises(ValueError, match="held-out"):
        rt.failure_packet(replace(task_for(), split=split), {}, phase="learn0")


def test_failure_packet_task_provenance():
    with pytest.raises(ValueError, match="provenance"):
        rt.failure_packet(task_for(), {"id": "other"}, phase="learn0")


def test_delivery_and_unknown_classifications():
    task = task_for()
    for responses, expected in [(["bad", "bad"], "delivery"),
                                (["bad", {"ok": False, "response": ""}], "unknown")]:
        record = rt.solve(FakeAPI(responses), task, "", key="unit", repeat=0)
        packet = rt.failure_packet(task, record, phase="learn0")
        assert packet["classification"] == expected
        assert packet["raw_delivery"] == record["revision_response"]


def decision(candidate, passed):
    return {"candidate_hash": digest(candidate), "passed": passed, "action": "Commit" if passed else "Reject"}


def test_rejected_candidate_is_repair_parent_never_execution_parent():
    candidate = {"valid": True, "content": "Improve the failed edge case."}
    state = rt.initial_state("feedback")
    state = rt.advance_state(state, candidate, decision(candidate, False), decision(candidate, False), round_index=0)
    assert state["working_local"] == state["approved_deployed"] == ""
    assert state["repair_parent"]["candidate"] == candidate
    assert state["repair_parent"]["eligible_as_execution_parent"] is False
    assert state["revision"] == 0
    assert rt.initial_state("feedback")["repair_parent"] is None


def test_local_commit_is_not_deployment_and_full_commit_clears_repair():
    candidate = {"valid": True, "content": "local"}
    state = rt.advance_state(rt.initial_state("research"), candidate, decision(candidate, True),
                             decision(candidate, False), round_index=0)
    assert state["working_local"] == "local" and state["approved_deployed"] == ""
    final = {"valid": True, "content": "broader"}
    state = rt.advance_state(state, final, decision(final, True), decision(final, True), round_index=1)
    assert state["working_local"] == state["approved_deployed"] == "broader"
    assert state["repair_parent"] is None and len(state["repair_history"]) == 1


def test_rejection_preserves_previous_working_and_approved():
    first, second = {"valid": True, "content": "accepted"}, {"valid": True, "content": "rejected"}
    state = rt.advance_state(rt.initial_state("fixed"), first, decision(first, True), decision(first, True), round_index=0)
    state = rt.advance_state(state, second, decision(second, False), decision(second, False), round_index=1)
    assert state["working_local"] == state["approved_deployed"] == "accepted"
    assert state["repair_parent"]["candidate"] == second


def test_state_refuses_tampering_and_nonmonotonic_rounds():
    candidate = {"valid": True, "content": "candidate"}
    state = rt.initial_state("fixed")
    tampered = deepcopy(state)
    tampered["working_local"] = "injected"
    with pytest.raises(ValueError, match="integrity"):
        rt.advance_state(tampered, candidate, decision(candidate, False), decision(candidate, False), round_index=0)
    state = rt.advance_state(state, candidate, decision(candidate, False), decision(candidate, False), round_index=0)
    with pytest.raises(ValueError, match="monotonically"):
        rt.advance_state(state, candidate, decision(candidate, False), decision(candidate, False), round_index=0)
    with pytest.raises(ValueError, match="provenance"):
        rt.advance_state(state, candidate, {"passed": False}, decision(candidate, False), round_index=1)


def test_scope_needs_local_and_invalid_candidate_cannot_inherit():
    candidate = {"valid": True, "content": "candidate"}
    with pytest.raises(ValueError, match="local"):
        rt.advance_state(rt.initial_state("fixed"), candidate, decision(candidate, False), decision(candidate, True), round_index=0)
    candidate["valid"] = False
    with pytest.raises(ValueError, match="invalid"):
        rt.advance_state(rt.initial_state("fixed"), candidate, decision(candidate, True), decision(candidate, True), round_index=0)


def test_failure_packets_bound_and_hashed_in_repair_state():
    task = task_for()
    record = rt.solve(FakeAPI(["bad", "bad"]), task, "", key="unit", repeat=0)
    packet = rt.failure_packet(task, record, phase="learn0")
    candidate = {"valid": True, "content": "candidate"}
    state = rt.initial_state("fixed")
    for i in range(6):
        state = rt.advance_state(state, candidate, decision(candidate, False), decision(candidate, False),
                                 round_index=i, failure_packets=[packet])
    assert len(state["repair_history"]) == rt.MAX_REPAIR_HISTORY
    assert state["repair_parent"]["failure_packets"] == [packet]
    bad = {**packet, "classification": "injected"}
    with pytest.raises(ValueError, match="packet integrity"):
        rt.advance_state(state, candidate, decision(candidate, False), decision(candidate, False),
                         round_index=7, failure_packets=[bad])
