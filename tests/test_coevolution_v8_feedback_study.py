"""Offline integration of the paired design; fake outputs are not efficacy data."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.coevolution_v8 import feedback_study as e
from skillopt.validator_pilot.api import digest, write_immutable_json


def panel():
    common = {"split": "development", "contract": {"change_scope": "partial_update",
              "preserve_obligations": ["Retain unrelated input facts/cells."], "supersedes_old_policy": False},
              "prompt": "Implement the public contract with its explicitly listed runtime."}
    sheet = {**deepcopy(common), "id": "v8-integration-sheet", "domain": "spreadsheet", "cluster_id": "sheet-family",
             "inputs": {"A1": 7}, "formulas": {"B1": "=A1"}, "editable_cells": ["B1"],
             "public_cases": [{"id": "visible-sheet", "overrides": {}, "expected": {"B1": 9}}],
             "hidden_cases": [{"id": "PRIVATE_SHEET_CASE_SENTINEL", "overrides": {"A1": 113}, "expected": {"B1": 115}}],
             "reference_artifact": {"formulas": {"B1": "=A1+2"}}}
    rule = {**deepcopy(common), "id": "v8-integration-rule", "domain": "rule_reasoning", "cluster_id": "rule-family",
            "rules": [{"id": "r", "if": ["ready"], "then": "done"}], "editable_rule_ids": ["r"],
            "vocabulary": ["ready", "done", "blocked"], "answer_facts": ["done"],
            "public_cases": [{"id": "visible-rule", "facts": ["ready"], "expected": ["done"]}],
            "hidden_cases": [{"id": "PRIVATE_RULE_CASE_SENTINEL", "facts": ["ready", "done"], "expected": ["done"]}],
            "reference_artifact": {"rules": [{"id": "r", "if": ["ready"], "then": "done"}]}}
    return [NativeAdapter(sheet), NativeAdapter(rule)]


class Fake:
    model = "glm-5.3"
    service = {"max_retries": 2, "fake_transport": "v8-offline-receipt-integration"}

    def __init__(self, root, state, tasks):
        self.root, self.state, self.tasks = Path(root), state, tasks

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        h = digest(request)
        path = self.root / "calls" / f"{h}.json"
        if path.exists():
            return json.loads(path.read_text())
        if self.state.get("before_write"):
            self.state["before_write"](request)
        data = json.loads(user)
        task = self.tasks[data["task"]["id"]]
        structured = "structured_feedback" in data
        if task.domain == "spreadsheet":
            response = json.dumps(task.task["reference_artifact"] if structured else {"formulas": {"B1": "=SQRT(A1)"}})
        elif data["stage"] == "generation":
            response = json.dumps(task.task["reference_artifact"])
        else:
            response = json.dumps({"rules": [{"id": "r", "if": ["ready", "blocked"], "then": "done"}]}) if structured else "KEEP"
        record = {"request": request, "request_hash": h, "ok": True, "response": response,
                  "http_attempt_count": 1, "attempts": [{"attempt": 1, "ok": True, "status": 200}],
                  "usage": {"prompt_tokens": len(user), "completion_tokens": len(response), "total_tokens": len(user) + len(response)},
                  "error_type": None, "status": 200, "finish_reason": "stop", "returned_model": self.model}
        if self.state.get("response_hook"):
            record = self.state["response_hook"](record)
        write_immutable_json(path, record)
        self.state["calls"].append(record)
        if self.state.get("after_write"):
            self.state["after_write"](record)
        return record

    def parallel(self, jobs, fn, label):
        result = [fn(job) for job in jobs]
        return self.state["schedule_hook"](label, result) if self.state.get("schedule_hook") else result

    def close(self):
        pass


def setup(tmp_path, monkeypatch, blocks=2):
    state = {"calls": [], "factories": 0, "source_hash": digest("frozen-offline-source")}
    monkeypatch.setattr(e.FeedbackStudy, "sources", lambda _: {"test_source": state["source_hash"]})
    # Only the native bounded interpreter is used in this unit panel.
    monkeypatch.setattr(e.executor, "sandbox_probe", lambda: {"ok": True, "offline_native_only": True})
    tasks = panel()
    indexed = {a.task["id"]: a for a in tasks}

    def factory(repo, root, max_calls, workers):
        state["factories"] += 1
        return BudgetedAPI(repo, root, max_calls, workers, api=Fake(root, state, indexed))

    study = e.FeedbackStudy(tmp_path, tmp_path / "outputs/coevolution_v8/integration", blocks=blocks, panel=tasks)
    return study, factory, state


@pytest.fixture
def completed(tmp_path, monkeypatch):
    study, factory, state = setup(tmp_path, monkeypatch)
    result = study.run(api_factory=factory)
    return study, factory, state, result


def forbidden(*a, **kw):
    pytest.fail("No API or oracle reconstruction is permitted on completed resume")


def mutate(path, change):
    value = json.loads(path.read_text())
    change(value)
    if "record_hash" in value:
        value = seal({k: v for k, v in value.items() if k != "record_hash"})
    path.write_text(json.dumps(value))


def test_full_grid_uses_three_actual_calls_per_position_and_closes_budget(completed):
    study, _, state, result = completed
    rows = e.read(study.root / "rows.json")["rows"]
    assert result["complete"] is True
    assert len(state["calls"]) == study.max_calls == 12
    assert len(rows) == 8
    assert result["ledger"]["unresolved_reservations"] == []
    assert result["ledger"]["http_attempts_from_cached_records"] == 12
    assert {r["block"] for r in rows} == {0, 1}
    assert result["summary"]["skill_evolution_measured"] is False
    assert result["summary"]["scope_expansion_authorized"] is False


def test_paired_requests_only_change_added_feedback_not_initial_or_budget(completed):
    _, _, state, _ = completed
    grouped = {}
    for record in state["calls"]:
        request = record["request"]
        user = json.loads(request["user"])
        if user["stage"] != "revision":
            continue
        key = user["task"]["id"], request["repeat"]
        grouped.setdefault(key, {})["structured" if "structured_feedback" in user else "generic"] = (request, user)
    assert len(grouped) == 4
    for arms in grouped.values():
        generic, structured = arms["generic"], arms["structured"]
        baseline = deepcopy(structured[1])
        extra = baseline.pop("structured_feedback")
        assert baseline == generic[1]
        assert structured[0]["system"] == generic[0]["system"]
        assert structured[0]["max_tokens"] == generic[0]["max_tokens"] == e.TOKENS
        assert structured[0]["repeat"] == generic[0]["repeat"]
        assert structured[0]["key"] != generic[0]["key"]
        assert extra["phase"] == "development" and extra["scope_expansion_authorized"] is False


def test_structured_diagnostics_have_actual_request_and_public_task_identity(completed):
    study, _, state, _ = completed
    receipts = {r["request_hash"]: r for r in state["calls"]}
    for path in (study.root / "stages").glob("*.json"):
        stage = e.read(path)
        actual = receipts[stage["request_hash"]]
        public = json.loads(actual["request"]["user"])["task"]
        assert stage["receipt_hash"] == digest(actual)
        for kind in ("delivery", "execution"):
            report = stage[kind]
            assert report["evidence_ref"]["request_hash"] == stage["request_hash"]
            assert report["public_task_hash"] == digest(public)
            assert report["artifact_hash"] == digest(stage["delivery"]["artifact"])


def test_hidden_scores_never_in_requests_and_only_run_after_all_revisions(tmp_path, monkeypatch):
    study, factory, state = setup(tmp_path, monkeypatch, blocks=1)
    original = e.evaluate
    observations = []

    def checked(adapter, artifact, *, public_only):
        if not public_only:
            observations.append(len(state["calls"]))
        return original(adapter, artifact, public_only=public_only)

    monkeypatch.setattr(e, "evaluate", checked)
    study.run(api_factory=factory)
    # Host references are preflighted before models; candidate hidden scoring follows the complete grid.
    assert set(observations) == {0, study.max_calls}
    for call in state["calls"]:
        raw = call["request"]["user"]
        assert "PRIVATE_SHEET_CASE_SENTINEL" not in raw and "PRIVATE_RULE_CASE_SENTINEL" not in raw
        assert "hidden_cases" not in raw and "reference_artifact" not in raw and "private_scores" not in raw


def test_initial_success_is_retained_and_revision_regression_reported(completed):
    _, _, _, result = completed
    transitions = result["summary"]["revision_transitions"]
    assert transitions["generic"]["initial_correct"] == transitions["structured"]["initial_correct"] == 2
    assert transitions["structured"]["initial_correct_then_failed"] == 2
    assert transitions["generic"]["initial_correct_then_failed"] == 0
    assert transitions["structured"]["initial_unsuccessful_then_correct"] == 2
    assert result["summary"]["initial"]["positions"] == 4


def test_delivery_unavailable_is_not_native_semantic_failure(completed):
    study, _, _, result = completed
    rows = e.read(study.root / "rows.json")["rows"]
    sheet_generic = [r for r in rows if r["domain"] == "spreadsheet" and r["arm"] == "generic"]
    rule_structured = [r for r in rows if r["domain"] == "rule_reasoning" and r["arm"] == "structured"]
    assert all(r["score"]["semantic_success"] is None and r["api_ok"] for r in sheet_generic)
    assert all(r["score"]["semantic_success"] == 0 and r["score"]["oracle_available"] for r in rule_structured)
    assert result["summary"]["both_oracles_available"]["pairs"] == 2
    assert result["summary"]["both_oracles_available"]["losses"] == 2


def test_completed_resume_is_byte_identical_without_api_or_oracle(completed, monkeypatch):
    study, _, state, result = completed
    before = {str(p.relative_to(study.root)): digest(p.read_text()) for p in study.root.rglob("*.json")}
    count = len(state["calls"])
    monkeypatch.setattr(e, "evaluate", forbidden)
    assert study.run(api_factory=forbidden) == result
    after = {str(p.relative_to(study.root)): digest(p.read_text()) for p in study.root.rglob("*.json")}
    assert before == after and len(state["calls"]) == count


def test_frozen_source_and_panel_mutation_rejected_before_model(completed):
    study, _, state, _ = completed
    state["source_hash"] = digest("changed-source")
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


def test_task_mutation_rejected_before_model(completed):
    study, _, _, _ = completed
    study.panel[0].task["prompt"] += " changed contract"
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


@pytest.mark.parametrize("split", ["final", "holdout", "promotion", "audit"])
def test_non_development_panel_rejected(tmp_path, split):
    tasks = panel()
    tasks[0].task["split"] = split
    with pytest.raises(ValueError, match="development"):
        e.FeedbackStudy(tmp_path, tmp_path / "outputs/coevolution_v8/unit", panel=tasks)


def test_reference_preflight_failure_never_opens_api(tmp_path, monkeypatch):
    study, _, _ = setup(tmp_path, monkeypatch)
    study.panel[0].task["reference_artifact"] = {"formulas": {"B1": "=0"}}
    with pytest.raises(ValueError, match="reference"):
        study.run(api_factory=forbidden)


def test_missing_persisted_response_with_intent_never_resampled(tmp_path, monkeypatch):
    study, factory, state = setup(tmp_path, monkeypatch, blocks=1)

    def stop(request):
        raise RuntimeError("simulated interruption before result persistence")

    state["before_write"] = stop
    with pytest.raises(RuntimeError, match="interruption"):
        study.run(api_factory=factory)
    state.pop("before_write")
    with pytest.raises(ValueError, match="unresolved"):
        study.run(api_factory=factory)
    assert len(state["calls"]) == 0
    assert len(list((study.root / "intents").glob("*.json"))) == 1


def test_persisted_response_after_interrupt_reused_without_resampling(tmp_path, monkeypatch):
    study, factory, state = setup(tmp_path, monkeypatch, blocks=1)

    def stop(record):
        raise RuntimeError("simulated interruption after receipt persisted")

    state["after_write"] = stop
    with pytest.raises(RuntimeError, match="interruption"):
        study.run(api_factory=factory)
    first = state["calls"][0]["request_hash"]
    state.pop("after_write")
    assert study.run(api_factory=factory)["complete"] is True
    assert len(state["calls"]) == study.max_calls
    assert sum(r["request_hash"] == first for r in state["calls"]) == 1


def test_terminal_api_result_kept_in_full_grid_without_semantic_resample(tmp_path, monkeypatch):
    study, factory, state = setup(tmp_path, monkeypatch, blocks=1)

    def failed_generation(record):
        if record["request"]["kind"] == "v8_feedback_generation":
            return {**record, "ok": False, "response": "", "error_type": "timeout", "status": None}
        return record

    state["response_hook"] = failed_generation
    result = study.run(api_factory=factory)
    assert len(state["calls"]) == study.max_calls
    assert result["summary"]["initial"]["all_attempt_success"] == 0
    assert result["summary"]["initial"]["positions"] == 2
    assert len(e.read(study.root / "rows.json")["rows"]) == 4


@pytest.mark.parametrize("kind", ["drop", "duplicate"])
def test_scheduler_cannot_drop_or_duplicate_complete_grid(tmp_path, monkeypatch, kind):
    study, factory, state = setup(tmp_path, monkeypatch, blocks=1)
    state["schedule_hook"] = lambda label, rows: (rows[:-1] if kind == "drop" else rows + rows[:1]) if label == "v8-revision" else rows
    with pytest.raises(ValueError, match="Scheduler|grid|duplicate"):
        study.run(api_factory=factory)


@pytest.mark.parametrize("directory", ["api/calls", "api/budget_reservations", "intents"])
def test_completed_extra_model_cache_entries_rejected(completed, directory):
    study, _, _, _ = completed
    path = study.root / directory / (digest("extra-cache-position") + ".json")
    path.write_text(json.dumps({"extra": True}))
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


@pytest.mark.parametrize("directory", ["api/calls", "api/budget_reservations", "intents", "stages", "private_scores"])
def test_completed_missing_required_entries_rejected_without_reexecution(completed, directory):
    study, _, _, _ = completed
    next((study.root / directory).glob("*.json")).unlink()
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


@pytest.mark.parametrize("field", ["task_id", "block", "stage", "arm"])
def test_resealed_stage_identity_mismatch_rejected(completed, field):
    study, _, _, _ = completed
    path = next((study.root / "stages").glob("*.json"))
    mutate(path, lambda row: row.update({field: 99 if field == "block" else "wrong-stage-identity"}))
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


@pytest.mark.parametrize("field", ["rows_hash", "ledger"])
def test_resealed_completed_bookkeeping_mutation_rejected(completed, field):
    study, _, _, _ = completed
    mutate(study.root / "results.json", lambda row: row.update({field: digest("wrong") if field == "rows_hash" else {}}))
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


def test_resealed_public_diagnostics_cannot_change_request_identity(completed):
    study, _, _, _ = completed
    path = next((study.root / "stages").glob("*.json"))

    def change(row):
        report = row["execution"]
        report["evidence_ref"]["request_hash"] = digest("foreign-response")
        row["execution"] = seal({k: v for k, v in report.items() if k != "record_hash"})

    mutate(path, change)
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


@pytest.mark.parametrize("name", ["protocol.json", "panel.json", "rows.json", "preflight.json"])
def test_completed_missing_top_level_metadata_is_not_reconstructed(completed, name):
    study, _, _, _ = completed
    path = study.root / name
    path.unlink()
    with pytest.raises(ValueError, match="metadata|missing"):
        study.run(api_factory=forbidden)
    assert not path.exists()


@pytest.mark.parametrize("field,value", [("complete", False), ("version", "wrong-version"), ("api_by_arm", {})])
def test_completed_derived_summary_metadata_must_match_actual_grid(completed, field, value):
    study, _, _, _ = completed
    mutate(study.root / "results.json", lambda row: row.update({field: value}))
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


def test_completed_corrupt_preflight_not_ignored(completed):
    study, _, _, _ = completed
    path = study.root / "preflight.json"
    value = json.loads(path.read_text())
    value["rows"][0]["reference_hash"] = digest("wrong-reference")
    # Deliberately leave its original seal: even ordinary file corruption must be detected.
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


def test_cached_private_score_cannot_disagree_with_underlying_evaluation(completed):
    study, _, _, _ = completed
    path = next(p for p in (study.root / "private_scores").glob("*.json")
                if e.read(p)["score"]["all_attempt_success"] == 1)
    mutate(path, lambda row: row["score"].update(all_attempt_success=0, semantic_success=0))
    with pytest.raises(ValueError, match="score|evaluation"):
        study.run(api_factory=forbidden)


def test_private_native_receipt_identity_cannot_be_replaced_with_foreign_task(completed):
    study, _, _, _ = completed
    path = next(p for p in (study.root / "private_scores").glob("*.json")
                if e.read(p)["score"]["all_attempt_success"] == 1)

    def change(row):
        value = row["evaluation"]
        value["task_id"] = "foreign-task"
        row["evaluation"] = seal({k: v for k, v in value.items() if k != "record_hash"})

    mutate(path, change)
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


def test_cached_call_must_match_actual_planned_request_not_only_filename(completed):
    study, _, _, _ = completed
    path = next((study.root / "api/calls").glob("*.json"))
    mutate(path, lambda row: row["request"].update(max_tokens=1))
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)


def test_public_case_identity_cannot_be_resealed_as_private_case(completed):
    study, _, _, _ = completed
    path = next(p for p in (study.root / "stages").glob("*.json")
                if e.read(p)["public_evaluation"]["case_results"])

    def change(row):
        value = row["public_evaluation"]
        value["case_results"][0]["id"] = "PRIVATE_CASE_SENTINEL"
        row["public_evaluation"] = seal({k: v for k, v in value.items() if k != "record_hash"})

    mutate(path, change)
    with pytest.raises(ValueError):
        study.run(api_factory=forbidden)
