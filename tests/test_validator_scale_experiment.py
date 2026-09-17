import json
from copy import deepcopy

import pytest

from skillopt.validator_pilot.tasks import Task
from skillopt.validator_scale_experiment import (
    ARMS,
    SKILLS,
    ScaleStudy,
    apply_public_guard,
    check_cached_call,
    expected_call,
    judge_instability,
    native_evaluation,
    read_record,
    solver_messages,
    target_schedule,
    visible,
    write_record,
)


def task():
    return Task("fresh", "dev", "family", "cluster", "Repair f, no files.", "def f(x): return x",
                "SECRET_REFERENCE", [], [], {"upstream_name": "fresh", "secret": "HIDDEN"})


def test_public_prompt_no_private_content():
    value = task()
    value.private_cases.append({"expected": "SECRET_EXPECTATION"})
    for arm in ARMS:
        system, user = solver_messages(value, arm)
        assert "SECRET" not in system + user
        assert "HIDDEN" not in user
        assert "raw Python" in system
        assert json.loads(user)["skill"] == SKILLS[arm]
    assert set(visible(value)) == {"id", "prompt", "starter_code", "public_cases"}


def test_schedule_fixed_and_balanced():
    values = []
    for identifier in range(32):
        item = task().to_dict()
        item["id"] = str(identifier)
        values.append(Task.from_dict(item))
    waves = target_schedule(values)
    assert waves == target_schedule(list(reversed(values)))
    assert len(waves) == 4
    assert len({job for wave in waves for job in wave}) == 384
    for repeat, wave in enumerate(waves):
        assert len(wave) == 96
        for offset in range(0, 96, 3):
            block = wave[offset:offset + 3]
            assert len({job[0] for job in block}) == 1
            assert {job[1] for job in block} == set(ARMS)
            assert {job[2] for job in block} == {repeat}


@pytest.mark.parametrize("reason", ["visible_test_failure", "python_syntax_or_runtime_contract"])
def test_public_guard_overrides_pass_without_private_truth(reason):
    artifact = {"target_ok": True, "evaluation": {"execution_ok": True}, "guard_reason": reason}
    judged = {"decision": "pass", "schema_valid": True}
    result, forced = apply_public_guard(judged, artifact)
    assert forced and result["decision"] == "fail"
    assert judged["decision"] == "pass"


def test_guard_does_not_peek_at_private_failure():
    artifact = {"target_ok": True, "evaluation": {"execution_ok": True, "hard": False}, "guard_reason": None}
    judged = {"decision": "pass", "schema_valid": True}
    assert apply_public_guard(judged, artifact) == (judged, False)


@pytest.mark.parametrize("target_ok,exec_ok", [(False, False), (True, False)])
def test_unavailable_is_not_false_failure(target_ok, exec_ok):
    artifact = {"target_ok": target_ok, "evaluation": {"execution_ok": exec_ok}, "guard_reason": None}
    result, forced = apply_public_guard({"decision": "pass"}, artifact)
    assert result["decision"] == "unknown" and not forced


def test_target_failure_no_code_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("mustnotexecute")
    monkeypatch.setattr("skillopt.validator_scale_experiment.evaluate", forbidden)
    row = native_evaluation(task(), "", False)
    assert row["evaluation"]["hard"] is None


def test_unextractable_is_observable_contract_error():
    row = native_evaluation(task(), "I cannot provide an artifact.", True)
    assert row["evaluation"]["execution_ok"]
    assert row["evaluation"]["hard"] is False


def test_native_code_not_rewritten(monkeypatch):
    code = "def f(x):\n    return x\n"
    seen = []
    monkeypatch.setattr("skillopt.validator_scale_experiment.evaluate",
                        lambda t, response: seen.append(response) or {"execution_ok": True, "hard": True, "public_pass": True})
    row = native_evaluation(task(), "```python\n" + code + "```", True)
    assert seen[0]["code"].strip() == code.strip()
    assert row["guard_reason"] is None


def test_judge_flips_count_once_per_artifact():
    base = {"id": "a", "skill_version": "noskill", "origin": "natural", "judge_ok": True,
            "judgment": {"decision": "pass", "schema_valid": True}}
    second = deepcopy(base)
    second["judgment"]["decision"] = "fail"
    report = judge_instability([base, second])["by_origin"]["natural"]
    assert report["artifact_pairs"] == 1
    assert report["raw_pass_fail_flip"] == 1


def test_holdout_generation_requires_frozen_rubrics(tmp_path):
    study = ScaleStudy(tmp_path, tmp_path / "out")
    with pytest.raises(RuntimeError, match="rubricsmustbefrozen"):
        study._generate(None, "holdout")


def test_repair_selection_rejects_holdout(tmp_path):
    study = ScaleStudy(tmp_path, tmp_path / "out")
    with pytest.raises(ValueError, match="development_only"):
        study._development_cases([{"split": "holdout"}], [])


def test_derived_cache_checksum_and_identity(tmp_path):
    path = tmp_path / "row.json"
    write_record(path, {"id": "one"})
    assert read_record(path) == {"id": "one"}
    # Simulate corruption through the test fixture API, not production writes.
    path.write_text(json.dumps({"id": "two", "record_sha256": "wrong"}))
    with pytest.raises(ValueError, match="integrity"):
        read_record(path)


def test_cache_requires_exact_call_and_never_sends_request(tmp_path):
    from types import SimpleNamespace
    api = SimpleNamespace(model="glm-5.3", root=tmp_path, service={"temperature": 0})
    identifier, request = expected_call(api, ("system", "user"), "kind", "key", 2000, 1)
    with pytest.raises(ValueError, match="missing"):
        check_cached_call(api, ("system", "user"), "kind", "key", 2000, 1, identifier)
    from skillopt.validator_pilot.api import write_immutable_json
    write_immutable_json(tmp_path / "calls" / (identifier + ".json"),
                         {"request": request, "request_hash": identifier})
    assert check_cached_call(api, ("system", "user"), "kind", "key", 2000, 1, identifier)["request"] == request
    with pytest.raises(ValueError, match="missing"):
        check_cached_call(api, ("system", "changed"), "kind", "key", 2000, 1, identifier)
