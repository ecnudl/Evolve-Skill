"""Cross-module invariants for the V4 driver (no model or network calls)."""

import json
import threading
from dataclasses import replace

import pytest

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v4 import experiment as ex
from skillopt.coevolution_v4 import gates, runtime, validator
from skillopt.validator_pilot.api import digest, write_immutable_json


def task_for(identifier="driver_unit", split="learn0"):
    files = {"api.py": "import calculation\ndef solve(data):\n    return calculation.double(data['x'])\n",
             "calculation.py": "def double(value):\n    return value\n"}
    reference = {**files, "calculation.py": "def double(value):\n    return value * 2\n"}
    public = {"label": "public", "input": {"x": 2}, "expected": 4, "exception": None,
              "dimension": "requested_behavior", "public": True}
    private = {**public, "label": "PRIVATE_SENTINEL", "input": {"x": 617}, "expected": 1234, "public": False}
    controls = {
        "equivalent": {**reference, "calculation.py": "def double(value):\n    return value + value\n"},
        "semantic_mutant": {**reference, "calculation.py": "def double(value):\n    return 0\n"},
        "preservation_mutant": {**reference, "api.py": "def solve(data):\n    data['extra'] = 1\n    return data['x'] * 2\n"},
    }
    return RepoTask(identifier, split, "unit", identifier, "Return twice x and leave the input unchanged.",
                    files, reference, list(files), {}, [public], [private], {"controls": controls})


def study_for(tmp_path, *tasks):
    study = object.__new__(ex.Study)
    study.repo = tmp_path
    study.root = tmp_path / "run"
    study.tasks = {t.id: t for t in (tasks or [task_for()])}
    study.mutex, study.locks = threading.Lock(), {}
    return study


class FakeAPI:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def call(self, system, user, **kwargs):
        row = {"system": system, "user": user, **kwargs}
        self.calls.append(row)
        return {"ok": True, "response": self.responses.pop(0), "request_hash": digest(row)}

    def parallel(self, jobs, fn, _label):
        return [fn(j) for j in jobs]


class PersistingAPI(FakeAPI):
    def __init__(self, root, responses=None):
        super().__init__(responses)
        self.root = root
        self.service = {"model": "glm-5.3", "test_only": True}

    def call(self, system, user, **kwargs):
        request = {"system": system, "user": user, "service": self.service, **kwargs}
        self.calls.append(request)
        row = {"request": request, "request_hash": digest(request), "ok": True,
               "response": self.responses.pop(0)}
        write_immutable_json(self.root / "calls" / f"{row['request_hash']}.json", row)
        return row


def delivered_reference(task):
    return runtime.serialize_delivery({p: task.reference_files[p] for p in task.editable_paths})


def solved(task, skill="candidate"):
    api = FakeAPI([delivered_reference(task), "KEEP"])
    return runtime.solve(api, task, skill, key="unit", repeat=0)


def packet_for(task, skill="candidate"):
    return runtime.failure_packet(task, solved(task, skill), "gate0" if task.split == "gate" else task.split)


@pytest.mark.parametrize("reference,candidate,expected", [
    ({"ok": False}, {"ok": True}, None),
    ({"ok": True}, {"ok": False}, None),
    ({"ok": True, "value": 1, "input_unchanged": True}, {"ok": True, "value": 1, "input_unchanged": True}, True),
    ({"ok": True, "value": 1, "input_unchanged": True}, {"ok": True, "value": True, "input_unchanged": True}, False),
    ({"ok": True, "value": 1, "input_unchanged": True}, {"ok": True, "value": 1, "input_unchanged": False}, False),
    ({"ok": True, "exception": "ValueError", "input_unchanged": True},
     {"ok": True, "exception": "ValueError", "input_unchanged": True}, True),
])
def test_observation_matching_keeps_unknown_types_and_mutation_distinct(reference, candidate, expected):
    assert ex.observation_matches(reference, candidate) is expected


def test_reference_contract_violation_is_not_a_trusted_oracle():
    reference = {"ok": True, "value": 1, "input_unchanged": False}
    candidate = {"ok": True, "value": 1, "input_unchanged": True}
    assert ex.observation_matches(reference, candidate) is None


def test_immutable_save_detects_corruption_and_refuses_overwrite(tmp_path):
    path = tmp_path / "record.json"
    ex.save(path, {"result": 1})
    assert ex.read(path) == {"result": 1}
    ex.save(path, {"result": 1})
    with pytest.raises(ValueError):
        ex.save(path, {"result": 2})
    path.write_text('{"record":{"result":2},"record_hash":"wrong"}')
    with pytest.raises(ValueError, match="integrity"):
        ex.read(path)


def test_packet_selection_keeps_full_packets_and_deduplicates():
    packets = [{"evidence_hash": str(i), "classification": "semantic", "task_id": str(i),
                "files": {"api.py": "line\n" * (i + 1)}} for i in range(4)]
    chosen = ex.select_packets(packets + [packets[0]], limit=2, max_chars=1000)
    assert chosen == packets[:2]
    assert ex.select_packets(packets, max_chars=1) == []


def test_optimizer_gets_rejected_skill_actual_files_and_exact_failed_case():
    task = task_for()
    api = FakeAPI([runtime.serialize_delivery(task.files), "KEEP"])
    packet = runtime.failure_packet(task, runtime.solve(api, task, "rejected", key="unit", repeat=0), "learn0")
    candidate = {"valid": True, "content": "rejected"}
    decision = {"passed": False, "candidate_hash": digest(candidate), "reasons": ["known_loss"], "action": "Reject"}
    state = runtime.advance_state(runtime.initial_state("feedback"), candidate, decision, decision,
                                   round_index=0, failure_packets=[packet])
    system, user = ex.optimizer_messages(state, [])
    payload = json.loads(user)
    repair = payload["repair_parent"]
    assert repair["candidate"] == candidate
    assert repair["eligible_as_execution_parent"] is False
    assert payload["working_local"] == ""
    failure = repair["complete_failure_packets"][0]
    assert failure["files"] == task.files
    assert failure["failed_cases"][1]["expected"] == 1234
    assert failure["failed_cases"][1]["actual"] == 617
    assert "REJECTED optimizer" in system


def test_policy_free_target_jobs_share_two_calls(tmp_path):
    task = task_for()
    study = study_for(tmp_path, task)
    api = FakeAPI([delivered_reference(task), "KEEP"])
    job = study._job(task.id, "", 0, "r0", 0)
    rows = study._targets(api, [job, dict(job), dict(job)], "same_content")
    assert len(rows) == 1 and len(api.calls) == 2
    row = rows[digest(job)]
    assert row["job_hash"] == digest(job)
    assert row["request_hashes"] == [digest(api.calls[0]), digest(api.calls[1])]
    assert row["evaluation"]["hard"] is True


def test_completed_target_cache_requires_both_original_call_receipts(tmp_path):
    task = task_for()
    study = study_for(tmp_path, task)
    api = PersistingAPI(tmp_path / "api", [delivered_reference(task), "KEEP"])
    job = study._job(task.id, "", 0, "r0", 0)
    row = study._target(api, job)
    assert study._target(api, job) == row
    assert len(api.calls) == 2
    (api.root / "calls" / f"{row['initial_request_hash']}.json").unlink()
    with pytest.raises(RuntimeError, match="Missing cached API receipt"):
        study._target(api, job)
    assert len(api.calls) == 2


def test_cached_target_cannot_be_relabelled_as_another_job(tmp_path):
    task = task_for()
    study = study_for(tmp_path, task)
    api = PersistingAPI(tmp_path / "api", [delivered_reference(task), "KEEP"])
    job = study._job(task.id, "", 0, "r0", 0)
    row = study._target(api, job)
    wrong = {**job, "skill": "different skill"}
    ex.save(study.root / "targets" / f"{digest(wrong)}.json", row)
    with pytest.raises(ValueError, match="frozen job"):
        study._target(api, wrong)


def test_nested_api_receipts_bind_service_and_request_hash(tmp_path):
    api = PersistingAPI(tmp_path / "api", ["response"])
    row = api.call("system", "user", kind="test", key="key")
    nested = {"repair_history": [{"candidate": {"request_hash": row["request_hash"]}}]}
    ex.require_cached_calls(api, nested)
    api.service = {"other_service": True}
    with pytest.raises(ValueError, match="provenance"):
        ex.require_cached_calls(api, nested)


def test_gate_target_solver_runs_public_only(tmp_path):
    task = task_for(split="gate")
    study = study_for(tmp_path, task)
    api = FakeAPI([delivered_reference(task), "KEEP"])
    row = study._target(api, study._job(task.id, "", 0, "r0", 0))
    assert row["public_only"] is True
    assert row["evaluation"]["private_diagnostics"] == []
    assert row["evaluation"]["total_tests"] == 2
    assert all("PRIVATE_SENTINEL" not in call["user"] for call in api.calls)


def test_transport_health_barrier_is_not_semantic_retry(tmp_path, monkeypatch):
    task = task_for()
    study = study_for(tmp_path, task)
    monkeypatch.setattr(study, "_target", lambda api, job: {"target_ok": False})
    with pytest.raises(RuntimeError, match="20%"):
        study._targets(FakeAPI(), [study._job(task.id, "", 0, "r0", 0)], "unavailable")


def basis(requested):
    flags = {"requested": requested, "preservation": True}
    return {"available": True, "hard": all(flags.values()), "case_results": flags,
            "preserved": {"preservation": True}, "case_total": 2, "case_passes": sum(flags.values())}


@pytest.mark.parametrize("probe_group", ["source", "replay"])
def test_local_gate_rejects_shared_probe_loss_even_with_finite_source_gain(probe_group):
    candidate = {"valid": True, "content": "candidate"}
    source = {"id": "source", "repeat": 0, "base": basis(False), "working": basis(False), "candidate": basis(True)}
    replay = {"id": "old", "repeat": 0, "base": basis(True), "working": basis(True), "candidate": basis(True)}
    target = source if probe_group == "source" else replay
    target["probe_results"] = {"base": {"probe": True}, "working": {"probe": True}, "candidate": {"probe": False}}
    decision = gates.decide_local(candidate, [source], [replay])
    assert decision["passed"] is False
    assert decision["action"] == "Reject"
    assert "verified_local_probe_regression" in decision["reasons"]


def test_unknown_probe_does_not_erase_known_finite_source_evidence():
    candidate = {"valid": True, "content": "candidate"}
    source = {"id": "source", "repeat": 0, "base": basis(False), "working": basis(False), "candidate": basis(True),
              "probe_results": {"base": {"probe": True}, "working": {"probe": True}, "candidate": {"probe": None}}}
    result = gates.decide_local(candidate, [source])
    assert result["passed"] is True
    assert result["evidence"]["shared_probe_audit"]["unknown"]


def test_shared_probe_inputs_are_identical_across_all_three_arms(tmp_path, monkeypatch):
    task = task_for()
    study = study_for(tmp_path, task)
    record = solved(task)
    observed = []
    def execute(task, files, inputs):
        observed.append(inputs)
        return [{"ok": True, "value": 4, "exception": None, "input_unchanged": True} for _ in inputs]
    monkeypatch.setattr(ex, "execute_inputs", execute)
    reference = {"ok": True, "value": 4, "exception": None, "input_unchanged": True}
    claim = {"receipts": [{"reference": reference, "input": {"x": 2}, "receipt_hash": "one"}]}
    pair = study._pair(task, 0, {arm: record for arm in ("base", "working", "candidate")}, claim)
    assert observed == [[{"x": 2}]] * 3
    assert pair["probe_results"] == {arm: {"one": True} for arm in ("base", "working", "candidate")}


def test_verified_probe_mismatch_is_retained_in_repair_packet(tmp_path):
    task = task_for()
    study = study_for(tmp_path, task)
    receipt = {"matched": False, "input": {"x": 9}, "actual": {"value": 9}, "reference": {"value": 18}}
    packet = study._packet(solved(task), "learn0", {"receipts": [receipt], "parsed": {"errors": []}})
    assert packet["classification"] == "semantic"
    assert packet["probe_mismatches"] == [receipt]
    value = dict(packet)
    assert value.pop("evidence_hash") == digest(value)


def test_final_tasks_cannot_feed_optimizer_packet_even_when_relabelled(tmp_path):
    task = task_for(split="holdout")
    study = study_for(tmp_path, task)
    with pytest.raises(ValueError, match="held-out"):
        study._packet(solved(task), "learn0")


def test_final_checks_sealed_state_before_any_api_call(tmp_path):
    study = study_for(tmp_path)
    ex.save(study.root / "final_frozen.json", {"states": {"different": True}})
    with pytest.raises(ValueError, match="state changed"):
        study._final(FakeAPI(), {})


def test_validator_revision_cannot_see_calibration_task_or_artifacts(tmp_path, monkeypatch):
    """Regression: the gate candidate could be the exact Base calibration alias."""
    source, calibration = task_for(), task_for("calibration_gate", split="gate")
    # Distinct module bytes ensure source evidence survives an artifact embargo.
    source = replace(source, files={**source.files, "calculation.py": source.files["calculation.py"] + "\n# source"},
                     reference_files={**source.reference_files, "calculation.py": source.reference_files["calculation.py"] + "\n# source"})
    study = study_for(tmp_path, source, calibration)
    packets = [packet_for(source), packet_for(calibration)]
    seen = []
    def evolve(api, state, development, root, key, use_research):
        seen.extend(development)
        return {"proposed_state": None, "status": "proposal_invalid"}
    monkeypatch.setattr(validator, "evolve", evolve)
    branch = {"learning": runtime.initial_state("feedback"), "validator": validator.initial_state()}
    study._evolve(FakeAPI(), branch, packets, calibration, [solved(calibration)], 0, "feedback", 0)
    assert seen and all(p["task_id"] != calibration.id for p in seen)
    calibration_hashes = {digest(calibration.reference_files), *(digest(v) for v in calibration.metadata["controls"].values())}
    assert all(p["artifact_hash"] not in calibration_hashes for p in seen)


def test_natural_finite_pass_is_not_an_equivalence_certificate(tmp_path, monkeypatch):
    """Regression: detecting a real untested natural defect is not a false alarm."""
    task = task_for(split="gate")
    study = study_for(tmp_path, task)
    observed = []
    def assessment(api, task, files, state, stream, stage, repeat, artifact_id, truth, kind):
        observed.append((kind, truth))
        return {"artifact_id": artifact_id, "artifact_hash": digest(files), "truth": truth,
                "outcome": "not_detected" if truth == "good" else "detected", "case_kind": kind, "repeat": repeat}
    monkeypatch.setattr(study, "_assessment", assessment)
    result = study._calibrate(FakeAPI(), task, validator.initial_state(), validator.initial_state(), 0, 0, [solved(task)])
    assert not any(kind == "natural" and truth == "good" for kind, truth in observed)
    assert result["diagnostic_only"]["new"][0]["truth"] == "oracle_pass_unproven"
    assert all(row["case_kind"] != "natural" for row in result["selection_rows"]["new"])


def test_fixed_panel_content_sharing_bounds_logical_calls_below_budget():
    # r0 has one common proposal per stream (same V0 and evidence). r1 proposal
    # inputs still share: V1 is not an optimizer input, and r0 gates were equal.
    # From r2 onward we pessimistically allow all three arms to diverge.
    assert ex.STREAMS == (0, 1) and ex.ROUNDS == (0, 1, 2)
    assert ex.TRAIN_REPEATS == (0, 1) and ex.FINAL_REPEATS == (0, 1, 2)
    streams, repeats, policies = 2, 2, 3
    r0_targets = streams * repeats * (2 + 1) * 2 * 2
    r1_targets = streams * repeats * (4 + 2) * 3 * 2
    r2_targets = streams * repeats * (6 * (1 + policies + policies) + 3 * (1 + policies + policies)) * 2
    final_targets = streams * 3 * 3 * (1 + policies + policies) * 2
    probe_calls = streams * repeats * (3 + 6 * policies + 9 * policies)
    proposal_calls = streams * (1 + 1 + policies)
    update_attempts = streams * (policies - 1) * 2
    calibration_calls = update_attempts * (4 * repeats + repeats) * 2
    evolution_calls = update_attempts * validator.MAX_EVOLUTION_CALLS
    maximum = sum([r0_targets, r1_targets, r2_targets, final_targets,
                   probe_calls, proposal_calls, calibration_calls, evolution_calls])
    assert maximum == 1334
    assert maximum <= ex.MAX_CALLS
