"""Offline V6 integration with real native/sandbox execution and fake transport.

Fake responses intentionally use known fixture solutions to test plumbing, not
to estimate model ability, human-review quality, or experimental effect sizes.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v6 import experiment as e
from skillopt.coevolution_v6.native import final_native_tasks
from skillopt.coevolution_v6.tasks import calibration_tasks, development_tasks, final_coding_tasks
from skillopt.validator_pilot.api import digest, write_immutable_json


def panel():
    return {"development": development_tasks(), "calibration": calibration_tasks(),
            "final": [a for a in final_coding_tasks() if a.task.metadata["variant"] == 0]
            + [a for a in final_native_tasks() if a.task["metadata"]["parameter_variant"] == 0]}


def rubric_patch(check_id="coding_probe"):
    return {"changes": [{"check_id": check_id,
                         "search": "Check one declared legal public input and retain its concrete execution evidence.",
                         "when": "Only apply under the host-declared task contract.",
                         "limits": "Synthetic integration control; finite evidence does not establish general safety."}],
            "rationale": "Exercise bounded revision wiring without relaxing immutable obligations.", "source_refs": []}


class FakeTransport:
    model = "glm-5.3"
    service = {"max_retries": 2, "fake_transport": "v6-offline-driver-integration"}

    def __init__(self, root, calls, tasks, hook=None):
        self.root, self.calls, self.tasks, self.hook = Path(root), calls, tasks, hook

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        identifier = digest(request)
        path = self.root / "calls" / f"{identifier}.json"
        if path.exists():
            return json.loads(path.read_text())
        payload = json.loads(user)
        if kind in {"v5_coding_generate", "v5_feedback_repair"}:
            task = self.tasks[payload["task"]["id"]].task
            files = task.reference_files if kind == "v5_feedback_repair" or payload["skill"] else task.files
            response = "\n".join("<<<FILE " + name + ">>>\n" + files[name] + "<<<END FILE>>>"
                                  for name in task.editable_paths)
        elif kind in {"v5_coding_revision", "v6_native_revision"}:
            response = "KEEP"
        elif kind == "v6_native_generate":
            # Explicit fake answer key, never a real model evaluation.
            response = json.dumps(self.tasks[payload["task"]["id"]].task["reference_artifact"])
        elif kind == "v6_skill":
            response = ("Preserve explicitly unchanged behavior before a local update. Inspect shared dependencies and "
                        "the public contract, make a bounded edit, then check the affected and unaffected behavior. "
                        "Do not preserve superseded policies when the user requests replacement; abstain for unrelated tasks.")
        elif kind == "v5_validator_probe":
            task = self.tasks[payload["task"]["id"]].task
            response = json.dumps({"inputs": [task.public_cases[0]["input"]]})
        elif kind == "v5_rubric_plan":
            response = json.dumps({"explanations": [
                {"hypothesis": "Public cases may miss a dependency boundary.", "check": "Try a legal boundary input."},
                {"hypothesis": "The contract already covers the case.", "check": "Check the actual host evidence."}],
                "questions": [{"topic": "mapping behavior", "question": "Which dependencies must be preserved?"}],
                "urls": ["https://docs.python.org/3/library/stdtypes.html"]})
        elif kind == "v5_rubric_synthesis":
            response = json.dumps({"findings": [], "limits": ["Offline fixture: no external research evidence obtained."]})
        elif kind == "v5_rubric_patch":
            response = json.dumps(rubric_patch())
        else:
            raise AssertionError(f"Unexpected offline API kind: {kind}")
        if self.hook is not None:
            response = self.hook(request, response)
        record = {"request": request, "request_hash": identifier, "response": response or "", "ok": response is not None,
                  "returned_model": self.model, "finish_reason": "stop", "http_attempt_count": 1,
                  "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}
        write_immutable_json(path, record)
        self.calls.append(record)
        return record

    def parallel(self, jobs, function, label):
        return [function(job) for job in jobs]

    def close(self):
        return None


def setup_study(tmp_path, monkeypatch, *, hook=None):
    tasks = panel()
    indexed = {e.identifier(adapter): adapter for group in tasks.values() for adapter in group}
    source_hash = {"value": digest("frozen-v6-offline-source")}
    fallback = {"rubric": core.apply_rubric_patch(core.initial_rubric(), rubric_patch()),
                "source": "synthetic-predecessor-receipt", "source_sha256": digest("synthetic predecessor")}
    monkeypatch.setattr(e.Study, "_sources", lambda self: {"synthetic_source": source_hash["value"]})
    monkeypatch.setattr(e.Study, "_legacy_rubric", lambda self: deepcopy(fallback))

    def no_network(*args, **kwargs):
        raise OSError("Offline integration intentionally blocks external documentation")

    monkeypatch.setattr(e.research, "fetch_sources", no_network)
    calls = []

    def factory(repo, root, *, max_calls, workers):
        return BudgetedAPI(repo, root, max_calls, workers, api=FakeTransport(root, calls, indexed, hook))

    study = e.Study(tmp_path, tmp_path / "outputs/coevolution_v6/unit", histories=1, blocks=1, max_calls=900, panel=tasks)
    return study, factory, calls, source_hash, fallback


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    with pytest.MonkeyPatch.context() as monkeypatch:
        setup = setup_study(tmp_path_factory.mktemp("v6-offline-integration"), monkeypatch)
        study, factory, calls, source, fallback = setup
        result = study.run(api_factory=factory)
        yield study, factory, calls, source, fallback, result


def test_complete_real_executor_and_native_driver(completed):
    study, _, calls, _, _, result = completed
    assert result["status"] == "complete" and result["engineering_only"]
    assert result["public_benchmark_efficacy_established"] is False
    assert not result["final_feedback_used"] and not result["calibration_feedback_used"]
    assert result["ledger"]["cached_logical_calls"] == len(calls)
    assert result["ledger"]["unresolved_reservations"] == []
    assert result["returned_models"] == {"glm-5.3": len(calls)}
    assert len(result["decisions"]) == 2
    assert {row["round"] for row in result["decisions"]} == {0, 1}
    for path in ("skills_frozen.json", "source_states/r0.json", "source_states/r1.json", "final_frozen.json"):
        core.verify(json.loads((study.root / path).read_text()))


def test_real_calibration_full_grid_equal_cost_and_explicit_hold(completed):
    study, _, calls, _, _, result = completed
    rows = e.read(study.root / "calibration_rows.json")["rows"]
    assert len(study.controls) == 24
    assert len(rows) == 24 * 4
    assert len({row["cluster_id"] for row in rows}) == 6
    assert {row["policy"] for row in rows} == {"old_single", "new_single", "old_double", "portfolio"}
    assert all(row["public_only"] for row in rows)
    summary = result["calibration"]
    assert summary["primary_gate"]["action"] == "Hold"
    assert "fewer_than_four_repeated_blocks" in summary["primary_gate"]["reasons"]
    assert not summary["primary_gate"]["activate"]
    assert summary["cost_audit"]["unique_probe_requests"] == 24 * 3
    assert summary["cost_audit"]["logical_policy_request_references"] == 24 * 6
    records = {record["request_hash"]: record for record in calls}
    assert all(request in records for row in rows for request in row["probe_request_hashes"])
    schedule = e.read(study.root / "calibration_schedule.json")["jobs"]
    assert len(schedule) == 72 and len({tuple(job) for job in schedule}) == 72


def test_source_skill_learning_separate_from_counterfactual_final_candidate(completed):
    study, _, _, _, _, result = completed
    frozen = e.read(study.root / "skills_frozen.json")
    branch = frozen["histories"][0]
    assert branch["candidate"]["valid"]
    assert branch["state"]["approved"] == ""
    assert any(row["local_passed"] for row in result["decisions"])
    assert e.read(study.root / "protocol.json")["unapproved_candidate_counterfactual_not_production_deployment"] is True
    assert all(row["domain"] == "coding" for row in branch["feedback"])


def test_final_routes_use_contract_and_alias_correct_intervention(completed):
    study, _, _, _, _, _ = completed
    rows = e.read(study.root / "final_rows.json")["rows"]
    assert len(rows) == 9 * 3
    assert {row["domain"] for row in rows} == {"coding", "spreadsheet", "rule_reasoning"}
    assert {row["evaluation_group"] for row in rows} == {"same_mechanism", "near_miss", "unrelated"}
    for adapter in study.panel["final"]:
        task_rows = {row["policy"]: row for row in rows if row["task_id"] == e.identifier(adapter)}
        routed = task_rows["mechanism_routed_candidate"]
        expected = "always_candidate" if routed["route"]["apply"] else "no_skill"
        assert routed["request_hashes"] == task_rows[expected]["request_hashes"]
        assert routed["artifact_hash"] == task_rows[expected]["artifact_hash"]
        assert routed["score"] == task_rows[expected]["score"]
        assert set(routed["route"]["routing_inputs"]) == {"change_scope", "preserve_obligations", "supersedes_old_policy"}
        assert routed["route"]["learned_router"] is False
        assert routed["route"]["apply"] == (routed["evaluation_group"] == "same_mechanism")


def test_optimizer_and_research_never_receive_calibration_or_final_labels(completed):
    study, _, calls, _, _, _ = completed
    forbidden = [e.identifier(adapter) for group in ("calibration", "final") for adapter in study.panel[group]]
    last_learning_index = -1
    first_calibration_index = None
    calibration_ids = {e.identifier(adapter) for adapter in study.panel["calibration"]}
    for index, record in enumerate(calls):
        request = record["request"]
        if request["kind"] == "v6_skill" or request["kind"].startswith("v5_rubric_"):
            last_learning_index = index
            assert all(identifier not in request["user"] for identifier in forbidden)
            assert '"truth":' not in request["user"]
            assert '"calibration_rows"' not in request["user"]
            assert '"final_rows"' not in request["user"]
        if request["kind"] == "v5_validator_probe":
            task_id = json.loads(request["user"])["task"]["id"]
            if task_id in calibration_ids and first_calibration_index is None:
                first_calibration_index = index
            assert '"truth":' not in request["user"]
            assert '"semantic_mutant"' not in request["user"]
            assert '"private_cases"' not in request["user"]
        if request["kind"] == "v5_feedback_repair":
            assert all(identifier not in request["user"] for identifier in forbidden)
            assert '"calibration_rows"' not in request["user"]
            assert '"final_rows"' not in request["user"]
        if request["kind"] in {"v5_coding_generate", "v5_coding_revision"}:
            visible = json.loads(request["user"])["task"]
            assert not set(visible) & {"reference_files", "private_cases", "controls"}
        if request["kind"].startswith("v6_native_"):
            data = json.loads(request["user"])
            assert "hidden_cases" not in data["task"]
            assert "reference_artifact" not in data["task"]
    assert first_calibration_index is not None and last_learning_index < first_calibration_index


def test_predeclared_repairs_run_for_every_development_fixture(completed):
    study, _, calls, _, _, result = completed
    repairs = result["repair"]
    assert len(repairs) == len(study.panel["development"])
    assert all(row["artifact_origin"] == "predeclared_buggy_task_fixture_not_agent_generated_failure" for row in repairs)
    repair_calls = [record for record in calls if record["request"]["kind"] == "v5_feedback_repair"]
    assert len(repair_calls) == 2 * len(study.panel["development"])
    assert len({record["request"]["max_tokens"] for record in repair_calls}) == 1
    recorded = e.read(study.root / "repair_results.json")
    assert recorded["no_update"] is True


def test_human_queue_contains_evidence_and_no_invented_review(completed):
    study, _, _, _, _, result = completed
    queue = json.loads((study.root / "human_review/queue.json").read_text())
    assert queue["entries"]
    assert all(entry["evidence"].get("artifact") is not None and entry["evidence"].get("facts") for entry in queue["entries"])
    assert queue["review_performed"] is False
    assert result["human_review"] == "pending_external_human"
    assert not (study.root / "human_review/reviews.json").exists()


def test_completed_resume_opens_no_api(completed):
    study, _, calls, _, _, expected = completed

    def forbidden(*args, **kwargs):
        pytest.fail("Completed V6 resume must not open API transport")

    resumed = e.Study(study.repo, study.root, histories=1, blocks=1, max_calls=900, panel=study.panel)
    count = len(calls)
    assert resumed.run(api_factory=forbidden) == expected
    assert len(calls) == count


def test_frozen_source_drift_blocks_completed_resume(completed):
    study, factory, calls, source, _, _ = completed
    original, count = source["value"], len(calls)
    try:
        source["value"] = digest("changed after freezing")
        with pytest.raises(ValueError, match="Immutable artifact differs|Frozen V6 sources"):
            study.run(api_factory=factory)
        assert len(calls) == count
    finally:
        source["value"] = original


@pytest.mark.parametrize("patch_response,reason", [("{", "invalid_fresh_proposal_fallback_to_frozen_predecessor"),
                                                  (json.dumps(rubric_patch("qa_answer")), "unsupported_qa_patch_fallback_to_frozen_predecessor")])
def test_research_failure_and_unsupported_qa_change_use_prefrozen_fallback(tmp_path, monkeypatch, completed,
                                                                         patch_response, reason):
    completed_study = completed[0]
    packets = e.read(completed_study.root / "source_states/r1.json")["histories"][0]["feedback"]

    def hook(request, default):
        return patch_response if request["kind"] == "v5_rubric_patch" else default

    study, factory, calls, _, fallback = setup_study(tmp_path, monkeypatch, hook=hook)
    protocol = study.prepare()
    with factory(study.repo, study.root / "api", max_calls=900, workers=4) as api:
        candidate, proposal, selection = study._research(api, packets, protocol)
    assert candidate == fallback["rubric"]
    assert selection["selection_reason"] == reason
    assert selection["no_calibration_labels_seen"] is True
    assert len(calls) == 3
    assert proposal["activation"] == "none_requires_independent_calibration_next_round"


def test_same_structural_family_cannot_cross_splits(tmp_path, monkeypatch):
    study, _, calls, _, _ = setup_study(tmp_path, monkeypatch)
    study.panel["final"].append(study.panel["development"][0])
    with pytest.raises(ValueError, match="families must be disjoint"):
        study.prepare()
    assert not calls


def test_native_group_metadata_is_resolved_from_actual_task_factory():
    assert {e.group(adapter) for adapter in final_native_tasks()} == {"same_mechanism", "near_miss", "unrelated"}


def test_public_contract_route_does_not_use_private_gold_or_group(tmp_path, monkeypatch):
    study, _, _, _, _ = setup_study(tmp_path, monkeypatch)
    for adapter in study.panel["final"]:
        frozen_contract = e.contract(adapter)
        assert set(frozen_contract) == {"change_scope", "preserve_obligations", "supersedes_old_policy"}
        if isinstance(adapter, CodingAdapter):
            assert "controls" not in frozen_contract
        else:
            assert "reference_artifact" not in frozen_contract
