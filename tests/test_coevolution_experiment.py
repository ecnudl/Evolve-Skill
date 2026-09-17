from __future__ import annotations

import json
import sys

import pytest

from skillopt.coevolution.experiment import (
    FINAL_ARMS,
    Study,
    decide,
    optimizer_messages,
    parse_skill,
    public_only,
    target_messages,
)
from skillopt.coevolution.validator import evaluate_shared_probes, initial_state
from skillopt.validator_pilot.api import digest, write_immutable_json
from skillopt.validator_pilot.tasks import Task


def tiny_task(identifier="tiny", split="dev"):
    return Task(identifier, split, identifier, identifier,
                "For a valid input x return x plus one. Preserve the input dictionary.",
                'def solve(data):\n    return data["x"]\n',
                'def solve(data):\n    return data["x"] + 1\n', [], [],
                {"upstream_name": "authored-coevolution-unit"})


def candidate(valid=True):
    return {"valid": valid, "content": "Use the explicit current contract and preserve still-valid constraints."}


def pair(**overrides):
    return {"mode": "local-update", "noskill": False, "current": False, "candidate": True, **overrides}


@pytest.mark.parametrize(("source", "gate", "action", "reason"), [
    ([pair()], [pair()], "Commit", "positive_source_gain_no_observed_gate_harm"),
    ([pair(current=True)], [pair()], "Restrict", "no_observed_source_gain"),
    ([pair()], [pair(candidate=None)], "Restrict", "unknown_or_unavailable_evidence"),
    ([pair(candidate=False, current=True)], [pair()], "Reject", "observed_harm"),
    ([pair()], [pair(candidate=False, noskill=True)], "Reject", "observed_harm"),
    ([pair(), pair(), pair(mode="full-policy-replacement", current=True, candidate=False)],
     [pair()], "Reject", "observed_harm"),
    ([pair(), pair(), pair(mode="local-update", current=True, candidate=False)],
     [pair()], "Commit", "positive_source_gain_no_observed_gate_harm"),
    ([], [pair()], "Restrict", "missing_evidence"),
])
def test_operational_gate(source, gate, action, reason):
    result = decide(candidate(), source, gate)
    assert result["action"] == action
    assert result["reason"] == reason
    assert result.get("statistical_safety_certified") is not True


def test_invalid_skill_rejected_before_scores():
    assert decide(candidate(False), [pair()], [pair()])["action"] == "Reject"


def test_private_cases_removed_for_gate_execution():
    task = tiny_task()
    task.private_cases.append({"secret_answer": 55})
    assert public_only(task).private_cases == []
    assert task.private_cases == [{"secret_answer": 55}]


def test_native_delivery_and_plain_bounded_skill():
    system, user = target_messages({"prompt": "contract"}, "fallible advice")
    assert "never JSON-encoded source" in system
    assert json.loads(user)["skill"] == "fallible advice"
    assert parse_skill({"ok": True, "response": candidate()["content"], "request_hash": "a"})["valid"]
    for value in ("short", "```skill\n" + "s" * 60 + "```", "a" * 5001):
        assert not parse_skill({"ok": True, "response": value, "request_hash": "a"})["valid"]


def test_optimizer_never_silently_clips_code():
    cases = [{"candidate_code": "a" * 120000}]
    with pytest.raises(ValueError, match="refusing silent code clipping"):
        optimizer_messages(cases, "", initial_state())


class FakeAPI:
    def __init__(self, root, response):
        self.root, self.response = root, response
        self.model, self.service = "glm-5.3", {"unit_test": True}

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        record = {"request": request, "request_hash": digest(request), "ok": True, "response": self.response}
        write_immutable_json(self.root / "calls" / (record["request_hash"] + ".json"), record)
        return record


@pytest.mark.skipif(sys.platform != "darwin", reason="existing fail-closed macOS sandbox")
def test_driver_grounded_claim_reaches_executor_and_shared_phase(tmp_path, monkeypatch):
    from skillopt.coevolution import tasks
    task = tiny_task()
    wrapper = {"task": task, "phase": "gate0", "context": "unit", "mode": "local-update"}
    study = Study.__new__(Study)
    study.root, study.tasks = tmp_path, {task.id: wrapper}
    monkeypatch.setattr(tasks, "input_valid", lambda identifier, value: identifier == "tiny" and value == {"x": 1})
    monkeypatch.setattr(tasks, "public_task", lambda value: {"prompt": value.prompt,
                        "starter_code": "DO NOT LEAK STARTER", "public_cases": [], "input_domain": {"x": [1]}})
    raw = json.dumps({"claims": [{"clause_quote": "return x plus one", "candidate_quote": 'return data["x"]',
                                   "input": {"x": 1}}], "search_note": "boundary"})
    api = FakeAPI(tmp_path / "api", raw)
    row = {"id": task.id, "target_ok": True, "code": task.starter_code, "repeat": 0}
    result = study._claims(api, row, initial_state(), 0, "evolving_validator", 0)
    assert result["receipts"][0]["status"] == "verified_mismatch"
    assert result["receipts"][0]["phase"] == "gate0"
    public = {"execution_ok": True, "public_pass": True}
    assert evaluate_shared_probes(wrapper, task.reference_code, result["receipts"], public)["score"] == 1
    assert evaluate_shared_probes(wrapper, task.starter_code, result["receipts"], public)["score"] == 0
    call = json.loads(next((api.root / "calls").glob("*.json")).read_text())
    assert "DO NOT LEAK STARTER" not in call["request"]["user"]
    assert study._claims(api, row, initial_state(), 0, "evolving_validator", 0) == result


def test_private_audit_requires_written_decision(tmp_path):
    study = Study.__new__(Study)
    with pytest.raises(RuntimeError, match="decision seal"):
        study._full_audit({}, tmp_path / "missing.json")


def test_direct_holdout_target_requires_valid_frozen_protocol(tmp_path, monkeypatch):
    study = Study.__new__(Study)
    task = tiny_task("holdout", "holdout")
    study.root, study.tasks = tmp_path, {task.id: {"task": task, "phase": "holdout"}}
    job = study._job(task.id, "", 0, "final", 0, "noskill")
    with pytest.raises(RuntimeError, match="final freeze seal"):
        study._target(None, job)
    write_immutable_json(tmp_path / "final_frozen.json", {"freeze_before_holdout": True, "protocol_hash": "wrong"})
    monkeypatch.setattr(study, "_verify", lambda: {"unit": True})
    with pytest.raises(ValueError, match="freeze seal"):
        study._target(None, job)


@pytest.mark.skipif(sys.platform != "darwin", reason="existing fail-closed macOS sandbox")
def test_target_cache_fields_bound_to_job_and_response(tmp_path, monkeypatch):
    from skillopt.coevolution import tasks
    from skillopt.validator_scale_experiment import read_record, write_record
    task = tiny_task()
    study = Study.__new__(Study)
    study.root, study.tasks = tmp_path, {task.id: {"task": task, "phase": "learn0", "context": "unit", "mode": "local-update"}}
    monkeypatch.setattr(tasks, "public_task", lambda value: {"prompt": value.prompt})
    api = FakeAPI(tmp_path / "api", task.reference_code)
    job = study._job(task.id, "", 0, "learn0", 0)
    row = study._target(api, job)
    assert study._target(api, job) == row
    path = next((tmp_path / "targets").glob("*.json"))
    corrupt = {**read_record(path), "stream": 99}
    path.unlink()
    write_record(path, corrupt)
    with pytest.raises(ValueError, match="Cached target fields"):
        study._target(api, job)


def test_complete_two_round_flow_freezes_before_720_final_draws(tmp_path, monkeypatch):
    """Injected model/oracle double tests ordering and accounting, not performance."""
    from skillopt.coevolution import budget
    study = Study.__new__(Study)
    study.repo, study.root = tmp_path, tmp_path / "run"
    study.tasks = {}
    for phase, count in (("learn0", 6), ("gate0", 6), ("learn1", 6), ("gate1", 6), ("holdout", 24)):
        for index in range(count):
            identifier = phase + "_" + str(index)
            task = tiny_task(identifier, "holdout" if phase == "holdout" else "dev")
            task = Task.from_dict({**task.to_dict(), "cluster_id": phase + "_cluster_" + str(index // 2),
                                   "family": phase + "_cluster_" + str(index // 2)})
            study.tasks[identifier] = {"task": task, "phase": phase, "context": "unit",
                                      "mode": "local-update" if index % 2 == 0 else "full-policy-replacement"}
    monkeypatch.setattr(study, "prepare", lambda: {"unit": True})
    monkeypatch.setattr(study, "_verify", lambda: {"unit": True})
    class NoNetwork:
        def __init__(self, *_, **__):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def parallel(self, jobs, fn, label):
            return [fn(job) for job in jobs]
        def ledger(self):
            return {"injected_test_double": True, "model_calls": 0}
    monkeypatch.setattr(budget, "BudgetedAPI", NoNetwork)
    monkeypatch.setattr(study, "_proposal", lambda *args: {**candidate(), "request_hash": digest(str(args[1:4]))})
    monkeypatch.setattr(study, "_claims", lambda *args: {"receipts": []})
    import skillopt.coevolution.validator as validator
    monkeypatch.setattr(validator, "evaluate_shared_probes", lambda *args: {"score": 1})
    audit_count = []
    def audit(row, seal):
        assert seal.exists()
        audit_count.append(row["request_hash"])
        return {"hard": True}
    monkeypatch.setattr(study, "_full_audit", audit)
    def targets(api, jobs, label):
        result = {}
        if label == "final_frozen_test":
            frozen = json.loads((study.root / "final_frozen.json").read_text())
            assert frozen["freeze_before_holdout"] and len(frozen["states"]) == 4
            assert len(jobs) == 720
        for job in jobs:
            wrapper = study.tasks[job["id"]]
            task = wrapper["task"]
            result[digest(job)] = {"id": task.id, "cluster_id": task.cluster_id, "family": task.family,
                "context": wrapper["context"], "mode": wrapper["mode"], "phase": wrapper["phase"],
                "stream": job["stream"], "arm": job["arm"], "repeat": job["repeat"],
                "skill_active": bool(job["skill"]), "skill_hash": digest(job["skill"]),
                "target_ok": True, "execution_ok": True, "hard": bool(job["skill"]),
                "code": task.reference_code if job["skill"] else task.starter_code,
                "request_hash": digest(job), "evaluation": {"private_diagnostics": [], "public_observations": []}}
        return result
    monkeypatch.setattr(study, "_targets", targets)
    result = study.run()
    assert result["status"] == "complete"
    assert len(result["decisions"]) == 8
    assert len(audit_count) == 288
    rows = json.loads((study.root / "final_rows.json").read_text())
    assert len(rows) == 720 and set(row["arm"] for row in rows) == set(FINAL_ARMS)
    assert all(row["skill_active"] for row in rows if row["arm"] in ("fixed_validator", "evolving_validator"))
