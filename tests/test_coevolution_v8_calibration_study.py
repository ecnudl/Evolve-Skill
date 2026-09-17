"""Offline driver wiring with real probe construction and synthetic host receipts.

Fake model proposals use only the task's public example. Host execution is an
explicit test fixture: these tests make no native correctness/efficacy claim.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v7.tasks import calibration_tasks
from skillopt.coevolution_v8 import calibration_study as e
from skillopt.validator_pilot.api import digest, write_immutable_json
from tests.test_coevolution_v8_research_calibration import imported_fixture, private_preflight


def forbidden(*a, **kw):
    pytest.fail("Completed screen must not call models or execute native code")


class Fake:
    model = "glm-5.3"

    def __init__(self, root, service, state):
        self.root, self.service, self.state = Path(root), service, state

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        h = digest(request)
        path = self.root / "calls" / f"{h}.json"
        if path.exists():
            return json.loads(path.read_text())
        if self.state.get("before_write"):
            self.state["before_write"](request)
        public = json.loads(user)["task"]
        response = json.dumps({"inputs": [public["public_cases"][0]["input"]]})
        record = {"request": request, "request_hash": h, "ok": True, "response": response,
                  "http_attempt_count": 1, "attempts": [{"attempt": 1, "ok": True, "status": 200}],
                  "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                  "finish_reason": "stop", "returned_model": self.model, "error_type": None, "status": 200}
        if self.state.get("response_hook"):
            record = self.state["response_hook"](record)
        write_immutable_json(path, record)
        self.state["calls"].append(record)
        if self.state.get("after_write"):
            self.state["after_write"](record)
        return record

    def parallel(self, jobs, fn, label):
        rows = [fn(job) for job in jobs]
        return self.state["scheduler"](rows) if self.state.get("scheduler") else rows

    def close(self):
        pass


def public_execution_fixture(self, files, rubric, *, phase, public_only, extra_inputs=None, **kwargs):
    """Explicit synthetic host fixture; do not mistake for sandbox execution."""
    assert phase == "promotion" and public_only is True
    inputs = extra_inputs or []
    rows = []
    for check in rubric["checks"]:
        details = {"task_split": "promotion", "requested_phase": "promotion"}
        if check["id"] == "coding_contract":
            status = "pass"
            details.update(public_only=True, facts={"execution_ok": True, "private_diagnostics": []},
                           case_results=[{"id": c["label"] + ":behavior", "public": True, "passed": True}
                                         for c in self.task.public_cases])
        elif check["id"] == "coding_probe":
            status = "pass" if inputs else "unknown"
            if inputs:
                value = self.task.public_cases[0]["expected"]
                result = {"ok": True, "value": value, "exception": None, "input_unchanged": True}
                details["receipts"] = [{"input": i, "actual": deepcopy(result), "reference": deepcopy(result), "passed": True}
                                       for i in inputs]
            else:
                details["reason"] = "no_bounded_probe_inputs"
        else:
            status = "not_applicable"
        hard = status in {"pass", "fail"}
        rows.append(core.make_assessment(check_id=check["id"], task_id=self.task.id, domain="coding", phase="promotion",
            artifact_hash=digest(files), rubric_hash=rubric["rubric_hash"], status=status, evidence_kind="execution",
            verified=hard, gate_eligible=hard, details=details))
    return rows


def setup(tmp_path, monkeypatch, *, valid=True):
    repo, diagnostic, _ = imported_fixture(tmp_path, monkeypatch, valid=valid)
    state = {"calls": [], "factories": 0, "source_hash": digest("calibration-offline-source")}
    monkeypatch.setattr(e, "_sources", lambda _: {"test_source": state["source_hash"]})
    monkeypatch.setattr(e, "_preflight", private_preflight)
    monkeypatch.setattr(CodingAdapter, "evaluate", public_execution_fixture)
    adapters = calibration_tasks()[:2]
    proposal = e.bridge.load_proposal(repo, diagnostic)

    def factory(repo, root, max_calls, workers):
        state["factories"] += 1
        return BudgetedAPI(repo, root, max_calls, workers, api=Fake(root, proposal["service"], state))

    root = repo / "outputs/coevolution_v8/calibration-integration"

    def run(**kwargs):
        return e.run(repo, diagnostic, root, blocks=1, adapters=adapters, api_factory=kwargs.pop("api_factory", factory), **kwargs)

    return run, root, state, repo, diagnostic, adapters


@pytest.fixture
def completed(tmp_path, monkeypatch):
    args = setup(tmp_path, monkeypatch)
    result = args[0]()
    return *args, result


def mutate(path, change):
    value = json.loads(path.read_text())
    change(value)
    if "record_hash" in value:
        value = core.seal({k: v for k, v in value.items() if k != "record_hash"})
    path.write_text(json.dumps(value))


def test_complete_two_families_one_block_twenty_four_real_probe_receipts(completed):
    _, root, state, _, _, _, result = completed
    assert result["complete"] is True and len(state["calls"]) == 24
    assert result["ledger"]["cached_logical_calls"] == result["ledger"]["http_attempts_from_cached_records"] == 24
    assert result["ledger"]["unresolved_reservations"] == []
    decision = result["decision"]
    assert decision["expected_components"] == decision["observed_components"] == 24
    assert decision["old_retained"] and not decision["activate_next_round"]
    assert not decision["deployment_approval"] and not decision["raw_calibration_labels_returned"]
    assert len(list((root / "components").glob("*.json"))) == 24


def test_model_requests_only_contain_public_task_artifact_and_rubric(completed):
    _, root, state, _, _, _, _ = completed
    screen = e._read(root / "screen.json")
    expected = {digest(e.bridge.request_for_job(screen, j)) for j in screen["jobs"]}
    assert expected == {r["request_hash"] for r in state["calls"]}
    for record in state["calls"]:
        request, user = record["request"], json.loads(record["request"]["user"])
        assert set(user) == {"task", "current_code", "rubric"}
        assert not {"private_cases", "reference_files", "metadata", "truth", "artifact_id"}.intersection(user["task"])
        assert request["max_tokens"] == 6000 and request["kind"] == "v5_validator_probe"
        assert request["repeat"] == 0


def test_component_api_execution_and_registry_are_one_bound_grid(completed):
    _, root, state, _, _, _, result = completed
    screen = e._read(root / "screen.json")
    receipts = {r["request_hash"]: r for r in state["calls"]}
    components = [e._read(p) for p in (root / "components").glob("*.json")]
    for c in components:
        artifact, rubric, inputs = e.bridge._probe_result(screen, c, receipts[c["search"]["request_hash"]])
        assert e.bridge._execution_outcome(c, artifact, rubric, inputs)[0] == "not_detected"
    directory = Path(screen["registry_root"]) / screen["screen_id"]
    assert e._read(directory / "v8_decision.json") == result["decision"]
    assert e._read(directory / "v8_screen.json") == screen


def test_completed_offline_no_models_or_native_execution_and_byte_identical(completed, monkeypatch):
    run, root, state, repo, _, _, result = completed
    before = {str(p.relative_to(repo)): digest(p.read_text()) for p in repo.rglob("*.json")}
    monkeypatch.setattr(e, "_preflight", forbidden)
    monkeypatch.setattr(CodingAdapter, "evaluate", forbidden)
    monkeypatch.setattr(e.executor, "execute_inputs", forbidden)
    assert run(api_factory=forbidden) == result
    assert len(state["calls"]) == 24
    after = {str(p.relative_to(repo)): digest(p.read_text()) for p in repo.rglob("*.json")}
    assert before == after and root.exists()


def test_source_freeze_mutation_rejected_before_api(completed):
    run, _, state, _, _, _, _ = completed
    state["source_hash"] = digest("changed-calibration-source")
    with pytest.raises(ValueError):
        run(api_factory=forbidden)


def test_task_panel_mutation_rejected_before_api(completed):
    run, _, _, _, _, adapters, _ = completed
    adapters[0].task.files["logic.py"] += "\n# changed panel\n"
    with pytest.raises(ValueError):
        run(api_factory=forbidden)


def test_same_cluster_cannot_be_reserved_again_under_new_screen(completed):
    _, _, _, repo, diagnostic, adapters, _ = completed
    with pytest.raises(ValueError, match="already reserved"):
        e.run(repo, diagnostic, repo / "outputs/coevolution_v8/second-screen", blocks=1,
              adapters=adapters, api_factory=forbidden)


@pytest.mark.parametrize("damage", ["job", "request", "input", "rubric"])
def test_component_cannot_rebind_job_or_execution_receipt(completed, damage):
    run, root, _, _, _, _, _ = completed
    path = next((root / "components").glob("*.json"))

    def change(row):
        if damage == "job":
            row["job"]["block"] = 99
        elif damage == "request":
            row["search"]["request_hash"] = digest("foreign-model-response")
            row["search"] = core.seal({k: v for k, v in row["search"].items() if k != "record_hash"})
        elif damage == "input":
            row["search"]["inputs"] = [{"invented": True}]
            row["search"] = core.seal({k: v for k, v in row["search"].items() if k != "record_hash"})
        else:
            row["assessments"][0]["rubric_hash"] = digest("different-rubric")
            row["assessments"][0] = core.seal({k: v for k, v in row["assessments"][0].items() if k != "receipt_hash"}, "receipt_hash")

    mutate(path, change)
    with pytest.raises(ValueError):
        run(api_factory=forbidden)


@pytest.mark.parametrize("directory", ["components", "api/calls", "api/budget_reservations"])
def test_completed_missing_or_extra_grid_entries_rejected(completed, directory):
    run, root, _, _, _, _, _ = completed
    extra = root / directory / (digest("extra-position") + ".json")
    extra.write_text(next((root / directory).glob("*.json")).read_text())
    with pytest.raises(ValueError):
        run(api_factory=forbidden)


@pytest.mark.parametrize("name", ["identity.json", "screen.json"])
def test_completed_missing_frozen_identity_not_rebuilt(completed, name):
    run, root, _, _, _, _, _ = completed
    path = root / name
    path.unlink()
    with pytest.raises(ValueError):
        run(api_factory=forbidden)
    assert not path.exists()


def test_missing_completed_component_not_silently_rerun(completed):
    run, root, _, _, _, _, _ = completed
    path = next((root / "components").glob("*.json"))
    path.unlink()
    with pytest.raises(ValueError, match="missing"):
        run(api_factory=forbidden)
    assert not path.exists()


@pytest.mark.parametrize("name", ["v8_decision.json", "v8_private_calibration.json"])
def test_completed_missing_registry_decision_evidence_not_silently_recreated(completed, name):
    run, root, _, _, _, _, _ = completed
    screen = e._read(root / "screen.json")
    path = Path(screen["registry_root"]) / screen["screen_id"] / name
    path.unlink()
    with pytest.raises(ValueError):
        run(api_factory=forbidden)
    assert not path.exists()


@pytest.mark.parametrize("kind", ["drop", "duplicate"])
def test_scheduler_partial_or_duplicate_components_do_not_close_screen(tmp_path, monkeypatch, kind):
    run, root, state, _, _, _ = setup(tmp_path, monkeypatch)
    state["scheduler"] = lambda rows: rows[:-1] if kind == "drop" else rows + rows[:1]
    with pytest.raises(ValueError, match="Incomplete|duplicate|matrix"):
        run()
    assert not (root / "results.json").exists()


def test_unresolved_api_reservation_never_resampled(tmp_path, monkeypatch):
    run, root, state, _, _, _ = setup(tmp_path, monkeypatch)

    def stop(request):
        raise RuntimeError("interrupted logical probe")

    state["before_write"] = stop
    with pytest.raises(RuntimeError, match="interrupted"):
        run()
    state.pop("before_write")
    with pytest.raises(RuntimeError, match="Unresolved"):
        run()
    assert state["calls"] == [] and not (root / "results.json").exists()


def test_persisted_receipt_after_interrupt_not_resampled(tmp_path, monkeypatch):
    run, _, state, _, _, _ = setup(tmp_path, monkeypatch)

    def stop(receipt):
        raise RuntimeError("interrupted after persistence")

    state["after_write"] = stop
    with pytest.raises(RuntimeError, match="interrupted"):
        run()
    h = state["calls"][0]["request_hash"]
    state.pop("after_write")
    assert run()["complete"] is True
    assert len(state["calls"]) == 24 and sum(r["request_hash"] == h for r in state["calls"]) == 1


@pytest.mark.parametrize("error", ["schema", "truncated", "transport"])
def test_terminal_or_invalid_proposals_remain_unknown_without_resampling(tmp_path, monkeypatch, error):
    run, _, state, _, _, _ = setup(tmp_path, monkeypatch)

    def response(row):
        if error == "schema":
            return {**row, "response": '{"inputs":[]}'}
        return {**row, "ok": False, "response": "", "error_type": "truncated_content" if error == "truncated" else "timeout",
                "finish_reason": "length" if error == "truncated" else None}

    state["response_hook"] = response
    result = run()
    assert len(state["calls"]) == 24 and result["decision"]["complete_calibration_grid"]
    assert result["decision"]["old_retained"] and not result["decision"]["activate_next_round"]
    assert result["decision"]["execution_unknown_counts"]["no_bounded_probe_inputs"] == 24


def test_invalid_source_candidate_does_not_allocate_api_or_registry(tmp_path, monkeypatch):
    run, root, state, repo, _, _ = setup(tmp_path, monkeypatch, valid=False)
    result = run(api_factory=forbidden)
    assert result["calls"] == 0 and result["status"] == "no_valid_candidate_no_calibration"
    assert state["calls"] == [] and not (repo / "outputs/coevolution_v8/validator_calibration_registry").exists()
    assert run(api_factory=forbidden) == result and not (root / "api").exists()


def test_invalid_candidate_cannot_hide_unexpected_model_cache(tmp_path, monkeypatch):
    run, root, _, _, _, _ = setup(tmp_path, monkeypatch, valid=False)
    path = root / "api/calls" / (digest("unexpected-call") + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"unexpected": True}))
    with pytest.raises(ValueError):
        run(api_factory=forbidden)


def test_actual_source_freeze_covers_input_legality_and_bound_functions():
    repo = Path(__file__).resolve().parents[1]
    hashes = e._sources(repo)
    assert "skillopt/coevolution_v3/tasks.py" in hashes
    assert "skillopt/coevolution_v3/validator.py" in hashes
