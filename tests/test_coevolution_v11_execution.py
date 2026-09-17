"""Offline, handwritten execution fixtures with deterministic fake API/child."""

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v10.codec import encode_value
from skillopt.coevolution_v11 import assertions, data, executor
from skillopt.coevolution_v11 import execution as e
from skillopt.validator_pilot.api import digest

REFERENCE = "def solve(x):\n    return x + 1\n# PRIVATE_REFERENCE"
GOOD = "def solve(x):\n    return x + 1\n"
BAD = "def solve(x):\n    return x - 1\n"
PROTO = "a" * 64


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def reseal(value):
    return seal({key: item for key, item in value.items() if key != "record_hash"})


def tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def forbidden(*args, **kwargs):
    pytest.fail("Replay attempted an external call, child execution, or immutable write")


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    compiled = assertions.compile_tests(["assert solve(42424242) == 42424243", "assert solve(-17) == -16"])
    task = {"task_id": 601, "source_split": "train", "split": "confirmation",
        "prompt": "Return one more than the input.", "reference_code": REFERENCE,
        "compiled": compiled, "entry_point": compiled["entry_point"], "public_interface": compiled["public_interface"],
        "source_row_hash": "b" * 64, "question_sha256": data.question_fingerprint("Return one more than the input.")}
    state = {"child_calls": 0, "api_calls": 0, "candidate": GOOD, "api_ok": True,
             "reference_status": "completed", "candidate_status": "completed", "reference_wrong": False,
             "raw_response": None}

    def child(code, entry, cases):
        state["child_calls"] += 1
        is_reference = code == REFERENCE
        status = state["reference_status"] if is_reference else state["candidate_status"]
        result = {"version": executor.VERSION, "runner_sha256": executor.RUNNER_SHA256,
                  "code_hash": e.text_hash(code), "status": status, "observations": [], "error_category": None}
        try:
            executor.validate_code(code)
            payload = executor._payload(code, entry, cases)
        except (ValueError, SyntaxError):
            result["status"] = "candidate_rejected"
            return result
        result["payload_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if status == "completed":
            good = code in (REFERENCE, GOOD) and not (is_reference and state["reference_wrong"])
            values = [42424243, -16] if good else [42424241, -18]
            result["observations"] = [{"value": encode_value(value), "exception": None, "typed": True,
                                       "truthiness": bool(value)} for value in values]
        elif status == "unsupported_output":
            result["observations"] = [{"value": None, "exception": None, "typed": False,
                                       "truthiness": True} for _ in cases]
        return result

    class API:
        model = "glm-5.3"
        service = {"fixture": True, "temperature": 0}

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            state["api_calls"] += 1
            request = {"model": self.model, "service": self.service, "system": system, "user": user,
                       "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
            identifier = digest(request)
            result = {"request": request, "request_hash": identifier, "ok": state["api_ok"],
                      "response": ((state["raw_response"] if state["raw_response"] is not None else
                                    "```python\n" + state["candidate"].rstrip("\n") + "\n```")
                                   if state["api_ok"] else ""),
                      "usage": {"total_tokens": 2}, "attempts": 1}
            put(tmp_path / "api/calls" / (identifier + ".json"), result)
            return result

    monkeypatch.setattr(executor, "run_cases", child)
    return SimpleNamespace(root=tmp_path, task=task, state=state, api=API())


def solve(fixture, *, skill="", completed=False, reference=None):
    ref = reference or e.reference(fixture.task, fixture.root, completed=completed)
    return e.solve(fixture.api, fixture.task, skill, fixture.task["split"], fixture.root, PROTO, ref,
                   completed=completed)


def test_successful_calibration_and_one_draw_bind_all_evidence(fixture):
    row = solve(fixture)
    assert row["hard"] == row["soft"] == 1
    assert row["outcome_category"] == "passed" and row["api_ok"]
    assert row["task_id"] == "601"
    assert row["skill_hash"] == hashlib.sha256(b"").hexdigest()
    assert row["compiled_hash"] == digest(fixture.task["compiled"])
    assert row["runner_sha256"] == executor.RUNNER_SHA256
    assert row["artifact"]["code"] == GOOD
    assert row["execution"]["code_hash"] == e.text_hash(GOOD)
    assert row["hidden_feedback_to_model"] is row["semantic_resampling"] is False
    assert fixture.state["api_calls"] == 1 and fixture.state["child_calls"] == 2
    assert len(list((fixture.root / "executions").glob("*.json"))) == 2


def test_prompts_are_public_only_and_share_run_contract(fixture):
    base_system, user = e.messages(fixture.task, "")
    skill_system, skill_user = e.messages(fixture.task, "A frozen experience.")
    assert user == skill_user
    assert skill_system.startswith(base_system)
    assert "A frozen experience." in skill_system and "A frozen experience." not in base_system
    for secret in ("42424242", "42424243", "PRIVATE_REFERENCE", "assert solve", "return x + 1"):
        assert secret not in base_system + user + skill_system
    assert json.loads(user) == data.public_task(fixture.task)
    assert "fresh module" in base_system and "classes" in base_system.lower()


def test_completed_and_normal_cache_replay_are_byte_exact_without_api_child_or_writes(fixture, monkeypatch):
    expected = solve(fixture)
    before = tree(fixture.root)
    monkeypatch.setattr(fixture.api, "call", forbidden)
    monkeypatch.setattr(executor, "run_cases", forbidden)
    monkeypatch.setattr(e, "write_immutable_json", forbidden)
    assert solve(fixture, completed=True) == expected
    assert solve(fixture) == expected
    assert tree(fixture.root) == before


def test_same_skill_reuses_exact_request_and_changed_skill_has_one_new_draw(fixture):
    first = solve(fixture, skill="shared")
    assert solve(fixture, skill="shared") == first
    second = solve(fixture, skill="changed")
    assert first["request_hash"] != second["request_hash"]
    assert fixture.state["api_calls"] == 2 and fixture.state["child_calls"] == 3


def test_failed_native_assertions_are_semantic_zero(fixture):
    fixture.state["candidate"] = BAD
    result = solve(fixture)
    assert result["hard"] == result["soft"] == 0
    assert result["outcome_category"] == "assertion_failure"
    assert result["score"]["score"]["passed_count"] == 0


def test_api_failure_remains_unknown_without_candidate_execution(fixture):
    fixture.state["api_ok"] = False
    result = solve(fixture)
    assert result["hard"] is result["soft"] is None and not result["api_ok"]
    assert result["outcome_category"] == "api_unknown"
    assert result["artifact"] is result["execution"] is None
    assert fixture.state["child_calls"] == 1


@pytest.mark.parametrize("candidate", ["def solve(:", "", "import os\ndef solve(x): return x", "class C: pass"])
def test_malformed_or_unsupported_candidate_is_zero_without_repair(fixture, candidate):
    fixture.state["candidate"] = candidate
    result = solve(fixture)
    assert result["hard"] == result["soft"] == 0
    assert result["outcome_category"] in {"artifact_contract_violation", "candidate_contract_violation"}
    assert fixture.state["api_calls"] == 1


@pytest.mark.parametrize("status", ["infrastructure_unknown", "unsupported_output"])
def test_candidate_infrastructure_and_encoding_failures_remain_unknown(fixture, status):
    fixture.state["candidate_status"] = status
    result = solve(fixture)
    assert result["api_ok"] and result["hard"] is result["soft"] is None
    assert result["outcome_category"] == status


@pytest.mark.parametrize("status,wrong", [("completed", True), ("infrastructure_unknown", False),
                                        ("unsupported_output", False)])
def test_unavailable_reference_never_turns_into_candidate_semantic_failure(fixture, status, wrong):
    fixture.state["reference_status"], fixture.state["reference_wrong"] = status, wrong
    calibration = e.reference(fixture.task, fixture.root)
    assert not calibration["oracle_valid"]
    result = solve(fixture, reference=calibration)
    assert result["hard"] is result["soft"] is None and result["outcome_category"] == "reference_unavailable"
    assert result["execution"] is None and fixture.state["child_calls"] == 1
    assert fixture.state["api_calls"] == 1


def test_reference_replay_independently_rescores_not_trusting_stored_pass(fixture):
    calibration = e.reference(fixture.task, fixture.root)
    path = fixture.root / "references/confirmation_601.json"
    changed = copy.deepcopy(calibration)
    changed["oracle_valid"] = False
    put(path, reseal(changed))
    with pytest.raises(ValueError, match="recomputed provenance"):
        e.reference(fixture.task, fixture.root, completed=True)
    assert fixture.state["child_calls"] == 1


@pytest.mark.parametrize("part", ["references", "solves", "api/calls", "execution_intents", "executions"])
def test_missing_completed_evidence_is_not_reconstructed_or_reexecuted(fixture, monkeypatch, part):
    solve(fixture)
    path = next((fixture.root / part).glob("*.json"))
    path.unlink()
    before = tree(fixture.root)
    monkeypatch.setattr(fixture.api, "call", forbidden)
    monkeypatch.setattr(executor, "run_cases", forbidden)
    with pytest.raises(ValueError):
        solve(fixture, completed=True)
    assert tree(fixture.root) == before


def test_unresolved_child_admission_is_not_silently_rerun(fixture, monkeypatch):
    monkeypatch.setattr(executor, "run_cases", lambda *args: (_ for _ in ()).throw(RuntimeError("disconnect")))
    with pytest.raises(RuntimeError, match="disconnect"):
        e.reference(fixture.task, fixture.root)
    assert len(list((fixture.root / "execution_intents").glob("*.json"))) == 1
    monkeypatch.setattr(executor, "run_cases", forbidden)
    with pytest.raises(ValueError, match="Unresolved execution admission"):
        e.reference(fixture.task, fixture.root)


@pytest.mark.parametrize("mutation", ["code", "payload", "runner", "version"])
def test_reference_receipt_binding_refuses_resealed_foreign_execution(fixture, mutation):
    e.reference(fixture.task, fixture.root)
    path = next((fixture.root / "executions").glob("*.json"))
    record = json.loads(path.read_text())
    field = {"code": "code_hash", "payload": "payload_hash", "runner": "runner_sha256", "version": "version"}[mutation]
    record["execution"][field] = "c" * 64
    put(path, reseal(record))
    with pytest.raises(ValueError):
        e.reference(fixture.task, fixture.root, completed=True)


def test_candidate_execution_cache_is_bound_to_actual_api_bytes(fixture):
    result = solve(fixture)
    path = fixture.root / "api/calls" / (result["request_hash"] + ".json")
    receipt = json.loads(path.read_text())
    receipt["response"] = json.dumps({"code": BAD})
    put(path, receipt)
    with pytest.raises(ValueError):
        solve(fixture, completed=True)
    assert fixture.state["child_calls"] == 2


def test_solver_score_cannot_be_resealed_to_skip_recomputation(fixture):
    result = solve(fixture)
    path = fixture.root / "solves" / (result["request_hash"] + ".json")
    changed = {**result, "hard": 0, "soft": 0.0}
    put(path, reseal(changed))
    with pytest.raises(ValueError, match="recomputed provenance"):
        solve(fixture, completed=True)


@pytest.mark.parametrize("field,value", [("split", "development"), ("source_row_hash", ""),
                                        ("question_sha256", "a" * 64), ("entry_point", "other")])
def test_changed_or_unregistered_task_identity_refused(fixture, field, value):
    fixture.task[field] = value
    with pytest.raises(ValueError):
        solve(fixture)
    assert fixture.state["child_calls"] == fixture.state["api_calls"] == 0


def test_undeclared_model_refused_without_api(fixture):
    calibration = e.reference(fixture.task, fixture.root)
    fixture.api.model = "different"
    with pytest.raises(ValueError, match="glm-5.3"):
        solve(fixture, reference=calibration)
    assert fixture.state["api_calls"] == 0


def test_different_protocol_cannot_reuse_completion(fixture, monkeypatch):
    solve(fixture)
    calibration = e.reference(fixture.task, fixture.root)
    monkeypatch.setattr(fixture.api, "call", forbidden)
    with pytest.raises(ValueError, match="missing immutable solver"):
        e.solve(fixture.api, fixture.task, "", "confirmation", fixture.root, "d" * 64, calibration, completed=True)


def test_initial_completed_run_cannot_create_any_files(fixture, monkeypatch):
    monkeypatch.setattr(executor, "run_cases", forbidden)
    with pytest.raises(ValueError, match="missing reference"):
        e.reference(fixture.task, fixture.root, completed=True)
    assert tree(fixture.root) == {}


def test_version_and_api_kind_are_independent_from_frozen_v10(fixture):
    result = solve(fixture)
    receipt = json.loads((fixture.root / "api/calls" / (result["request_hash"] + ".json")).read_text())
    assert result["version"].startswith("v11-")
    assert receipt["request"]["kind"] == "v11_coding_solve"
    assert receipt["request"]["max_tokens"] == 4096 and receipt["request"]["repeat"] == 0


def test_only_declared_wrapper_and_truth_value_contract_change_from_v10(fixture):
    from skillopt.coevolution_v10 import execution as previous

    for skill in ("", "Frozen QA skill."):
        old_system, old_user = previous.messages(fixture.task, skill)
        new_system, new_user = e.messages(fixture.task, skill)
        expected = old_system.replace(
            "Return exactly one JSON object with the single key 'code' containing the complete Python source; "
            "do not include explanations.",
            "Return exactly one Python fenced code block containing the complete Python source; "
            "do not wrap the code in JSON or include explanations.",
        ).replace(
            "Return only exact builtins:",
            "Exact-value comparisons require returned results representable as exact builtins:",
        ).replace(
            "or dict of supported values. Classes,",
            "or dict of supported values. Truth-value checks use the Boolean value of the returned result "
            "inside the isolated execution environment. Classes,",
        )
        assert new_system == expected
        assert new_user == old_user
        assert "Return only exact builtins" not in new_system
        assert "re.Match" not in new_system


@pytest.mark.parametrize("raw", [
    '{"code":"def solve(x): return x + 1"',  # Missing closing JSON object.
    '{"code": "def solve(x):\\q return x + 1"}',  # Invalid escape.
    '```python\ndef solve(x):\n    return x + 1\n',  # Missing closing fence.
    '```python\ndef solve(x): return x\n```\n```python\ndef solve(x): return x+1\n```',
])
def test_broken_json_or_fences_are_not_repaired_or_resampled(fixture, raw):
    fixture.state["raw_response"] = raw
    result = solve(fixture)
    assert result["hard"] == result["soft"] == 0
    assert result["outcome_category"] == "artifact_contract_violation"
    assert fixture.state["api_calls"] == 1 and fixture.state["child_calls"] == 1
    assert result["response_hash"] == e.text_hash(raw)
    assert result["artifact"]["ok"] is False


def test_original_artifact_extractor_identity_and_valid_json_compatibility_preserved(fixture):
    from skillopt.validator_artifact_sensitivity import extract_artifact

    assert e.extract_artifact is extract_artifact
    fixture.state["raw_response"] = json.dumps({"code": GOOD})
    result = solve(fixture)
    assert result["hard"] == 1
    assert result["artifact"]["mode"] == "strict_json"
    assert result["artifact"]["code"] == GOOD


def _observed_execution(task, code, observations):
    payload = executor._payload(code, task["entry_point"], task["compiled"]["cases"])
    return {"version": executor.VERSION, "runner_sha256": executor.RUNNER_SHA256,
            "code_hash": e.text_hash(code), "status": "completed", "observations": observations,
            "error_category": None,
            "payload_hash": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}


def test_untyped_native_truthiness_is_scored_without_host_object_execution(fixture):
    task = copy.deepcopy(fixture.task)
    task["compiled"] = assertions.compile_tests(["assert solve(42424242)", "assert not solve(-17)"])
    task["public_interface"] = task["compiled"]["public_interface"]
    observations = [
        {"value": None, "exception": None, "typed": False, "truthiness": True},
        {"value": None, "exception": None, "typed": False, "truthiness": False},
    ]
    scored = e._execution_score(task, GOOD, _observed_execution(task, GOOD, observations))
    assert scored["hard"] == scored["soft"] == 1


def test_untyped_value_required_by_exact_predicate_is_unknown_not_zero(fixture):
    observations = [
        {"value": None, "exception": None, "typed": False, "truthiness": True},
        {"value": encode_value(-16), "exception": None, "typed": True, "truthiness": True},
    ]
    scored = e._execution_score(fixture.task, GOOD, _observed_execution(fixture.task, GOOD, observations))
    assert scored == {"hard": None, "soft": None, "category": "unsupported_output", "score": None}


def test_host_never_invokes_a_foreign_truthiness_hook(fixture):
    class Trap:
        def __bool__(self):
            pytest.fail("Host evaluated a foreign object's truthiness")

        def __eq__(self, other):
            pytest.fail("Host compared a foreign object")

    observations = [
        {"value": Trap(), "exception": None, "typed": False, "truthiness": True},
        {"value": encode_value(-16), "exception": None, "typed": True, "truthiness": True},
    ]
    with pytest.raises(ValueError):
        e._execution_score(fixture.task, GOOD, _observed_execution(fixture.task, GOOD, observations))


def test_untyped_equality_candidate_unknown_retains_completed_receipt_and_replays(fixture, monkeypatch):
    calibration = e.reference(fixture.task, fixture.root)
    observations = [
        {"value": None, "exception": None, "typed": False, "truthiness": True},
        {"value": encode_value(-16), "exception": None, "typed": True, "truthiness": True},
    ]
    monkeypatch.setattr(executor, "run_cases", lambda code, entry, cases:
                        _observed_execution(fixture.task, code, observations))
    result = solve(fixture, reference=calibration)
    assert result["execution"]["status"] == "completed"
    assert result["hard"] is result["soft"] is None
    assert result["outcome_category"] == "unsupported_output"
    monkeypatch.setattr(executor, "run_cases", forbidden)
    monkeypatch.setattr(fixture.api, "call", forbidden)
    assert solve(fixture, reference=calibration, completed=True) == result
