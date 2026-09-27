"""Fixture receipts and fake providers; no API, code execution, or network."""
import json
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import admissibility_study as study
from skillopt.skill_validation.task_probes import execute_probes, parse_probes
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import ScriptedExecutor, artifact, task


class Executor(ScriptedExecutor):
    transport_identity = {"fixture": True}

    def run(self, *args, **kwargs):
        result = super().run(*args, **kwargs)
        return seal({**{k: v for k, v in result.items() if k != "record_hash"}, "cleanup_confirmed": True})


def fixture_source(tmp_path, monkeypatch, *, tasks=1):
    source = tmp_path / "outputs/skill_validation/parent"
    pool, old_rows = {}, {}
    for part in study.PARTS:
        pool[part], old_rows[part] = {}, []
        for index in range(tasks):
            t = task()
            identity = part + str(index)
            t = replace(t, contract=replace(t.contract, partition=part, original_task_id=identity,
                family_id=identity, prompt=t.contract.prompt + " Fixture " + identity))
            group = []
            for condition in ("no_skill", "current") if part == "verifier_calibration" else ("no_skill", "current", "candidate"):
                a = artifact(t, condition=condition)
                host = {"task_id": identity, "family_id": identity, "partition": part, "repeat": 0,
                    "condition": condition, "artifact_hash": a.content_hash, "public_status": "pass",
                    "status": "fail" if condition == "current" else "pass", "audit_hash": digest([identity, condition]),
                    "secret": "H_SECRET"}
                group.append({"task": t, "artifact": a, "host": host})
                old_rows[part].append(host)
            pool[part][t.contract.content_hash] = group
    manifest, old_protocol, freeze = seal({"manifest": "fixture"}), seal({"protocol": "fixture"}), seal({"freeze": "fixture"})
    e = Executor()
    parent_protocol = seal({"source_root": str(tmp_path / "original"), "final_access": False,
        "previously_consumed_panel": True, "manifest_hash": manifest["record_hash"],
        "source_protocol_hash": old_protocol["record_hash"], "candidate_freeze_hash": freeze["record_hash"],
        "source_rows_hash": digest(old_rows), "executor": e.identity})
    study._write(source / "protocol.json", parent_protocol)
    policies = {a: seal({"arm": a, "sources": [{"text": "SHOULD_NOT_BROADCAST"}]}) for a in study.ARMS[1:]}
    study._write(source / "frozen_policies.json", seal({"policies": policies}))
    metrics = {}
    for arm in study.ARMS[1:]:
        metrics[arm] = {}
        for part in study.PARTS:
            rows = []
            for group in pool[part].values():
                t = group[0]["task"]
                proposal = parse_probes({"probes": [{"kind": "expected", "calls": [{"args": [[1, 2]], "kwargs": {}}],
                    "expected": 3, "obligation_id": "returns", "contract_quote": "Return the total for [1, 2].",
                    "rationale": "Public literal example"}]}, t)
                frozen = seal({"proposal": proposal, "status": "valid",
                    "pipeline_hash": digest({"policy": policies[arm], "protocol": parent_protocol["record_hash"]})})
                study._write(source / "probes" / arm / (t.contract.content_hash + ".json"), frozen)
                for p in group:
                    report = execute_probes(t, p["artifact"], proposal, e, source / "probe_execution" / arm)
                    h = p["host"]
                    rows.append({"task_id": h["task_id"], "family_id": h["family_id"], "partition": part, "repeat": 0,
                        "condition": h["condition"], "artifact_hash": h["artifact_hash"], "audit_hash": h["audit_hash"],
                        "audit_status": h["status"], "fixed_status": h["public_status"], "new_status": "pass",
                        "proposal_hash": frozen["record_hash"], "probe_count": 1, "report_hash": report["record_hash"]})
            study._write(source / "host_only" / (arm + "_" + part + ".json"), seal({"rows": rows}))
            metrics[arm][part] = study.describe(rows)
    study._write(source / "results.json", seal({"protocol_hash": parent_protocol["record_hash"],
                 "final_access": False, "metrics": metrics}))
    monkeypatch.setattr(study, "load_frozen", lambda *args: (manifest, old_protocol, freeze, pool, old_rows))
    return source


@pytest.fixture
def provider(monkeypatch):
    state = {"calls": 0, "decision": "keep", "prompts": []}
    class API:
        def __init__(self, repo, root, **kwargs):
            self.root, self.model, self.service = root, "fixture", {"fixture": True}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def parallel(self, jobs, fn, label): return list(map(fn, jobs))
    class Calls:
        def __init__(self, api, root, protocol, cap):
            assert cap == 120
        def call(self, system, user, kind, **kwargs):
            state["calls"] += 1
            prompt = json.loads(user)
            assert prompt["sources"] == []
            assert "H_SECRET" not in user and "SHOULD_NOT_BROADCAST" not in user
            assert "anonymous_implementations" not in user and "condition" not in prompt
            state["prompts"].append(prompt)
            return {"ok": True, "request_hash": digest(user), "response": json.dumps({"checks": [
                {"probe_id": p["probe_id"], "decision": state["decision"],
                 "reason_code": "contract_supported" if state["decision"] == "keep" else "ambiguous_contract",
                 "reason": "Fixture only", "fact_question": ""} for p in prompt["checks"]]})}
        def accounting(self): return {"fixture": True, "logical_requests": state["calls"]}
    monkeypatch.setattr(study, "CachedAPI", API)
    monkeypatch.setattr(study, "BoundedCalls", Calls)
    return state


def test_complete_preexecution_pipeline_and_zero_call_replay(tmp_path, monkeypatch, provider):
    source = fixture_source(tmp_path, monkeypatch)
    root = tmp_path / "outputs/skill_validation/study"
    executor = Executor()
    result = study.run(tmp_path, source, root, executor)
    assert provider["calls"] == 4 and len(executor.calls) == 10
    assert not result["deployment_authorized"] and not result["feedback_authorized"] and not result["final_access"]
    assert result["new_solver_calls"] == result["skill_update_calls"] == 0
    assert (root / "source_snapshot.json").exists()
    for arm in study.ARMS[1:]:
        for part in study.PARTS:
            assert result["coverage"][arm][part]["decisions"] == {"keep": 1}
            assert result["readiness"][arm][part]["panels"][part]["status"] == "pending"
            assert result["metrics"][arm][part]["preexecution_reviewed"]["new_status"]["false_rejections"] == 0
    assert study.run(tmp_path, source, root, executor) == result
    assert provider["calls"] == 4 and len(executor.calls) == 10


def test_abstention_is_not_fake_new_validation_and_retains_public_baseline(tmp_path, monkeypatch, provider):
    source = fixture_source(tmp_path, monkeypatch)
    provider["decision"] = "abstain"
    executor = Executor()
    root = tmp_path / "outputs/skill_validation/abstain"
    result = study.run(tmp_path, source, root, executor)
    assert not executor.calls
    coverage = result["coverage"]["adaptive_no_research"]["verifier_calibration"]
    assert coverage["decisions"] == {"abstain": 1}
    assert coverage["position_probe_statuses"] == {"not_executed": 2}
    rows = study._read(root / "host_only/adaptive_no_research_verifier_calibration.json")["rows"]
    assert all(r["new_execution_report_hash"] is None and r["new_status"] == r["fixed_status"] for r in rows)


def test_execution_failure_blocks_later_paid_batches_and_resume_does_not_resample(tmp_path, monkeypatch, provider):
    source = fixture_source(tmp_path, monkeypatch, tasks=2)
    root = tmp_path / "outputs/skill_validation/failure"
    executor = Executor(crash=True)
    with pytest.raises(ValueError, match="stop paid"):
        study.run(tmp_path, source, root, executor, workers=1)
    assert provider["calls"] == 1 and len(executor.calls) == 1
    with pytest.raises(ValueError, match="stop paid"):
        study.run(tmp_path, source, root, executor, workers=1)
    assert provider["calls"] == 1 and len(executor.calls) == 1
    assert not (root / "results.json").exists()


def test_all_source_receipts_validated_before_any_paid_request(tmp_path, monkeypatch, provider):
    source = fixture_source(tmp_path, monkeypatch)
    path = next((source / "probe_execution/adaptive_research/calls").glob("*.json"))
    path.unlink()  # Deliberately remove a temporary fixture receipt, never real evidence.
    with pytest.raises(FileNotFoundError):
        study.run(tmp_path, source, tmp_path / "outputs/skill_validation/missing", Executor())
    assert provider["calls"] == 0


def test_parent_summary_changes_cannot_be_accepted_by_only_resealing(tmp_path, monkeypatch, provider):
    source = fixture_source(tmp_path, monkeypatch)
    path = source / "results.json"
    record = study._read(path)
    record.pop("record_hash")
    record["metrics"]["adaptive_research"]["skill_confirmation"]["positions"] += 1
    path.write_text(json.dumps(seal(record)))
    with pytest.raises(ValueError, match="summary"):
        study.run(tmp_path, source, tmp_path / "outputs/skill_validation/mismatch", Executor())
    assert provider["calls"] == 0


def test_changed_protocol_cannot_resume_and_source_output_overlap_rejected(tmp_path, monkeypatch, provider):
    source = fixture_source(tmp_path, monkeypatch)
    root = tmp_path / "outputs/skill_validation/study"
    study.run(tmp_path, source, root, Executor())
    count = provider["calls"]
    with pytest.raises(ValueError):
        study.run(tmp_path, source, root, Executor(), workers=1)
    assert provider["calls"] == count
    for output in (source, source / "nested", source.parent):
        with pytest.raises(ValueError, match="non-overlapping"):
            study.run(tmp_path, source, output, Executor())
