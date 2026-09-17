"""The auditor never calls a model or executes a submitted artifact.

The shared fixture is generated separately with the existing offline fake-model
integration harness. Its perfect answers are plumbing controls, not results.
"""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v6 import experiment as e
from skillopt.validator_pilot.api import digest

REPO = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


auditor = module("audit_coevolution_v6", REPO / "scripts/audit_coevolution_v6.py")
integration = module("v6_audit_offline_fixture", REPO / "tests/test_coevolution_v6_experiment.py")


@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    with pytest.MonkeyPatch.context() as monkeypatch:
        repo = tmp_path_factory.mktemp("v6-audit-offline-control")
        study, factory, _, source, fallback = integration.setup_study(repo, monkeypatch)
        source_path = repo / "synthetic_source"
        source_path.write_text("# Offline test sentinel, never real frozen runtime.\n", encoding="utf-8")
        source["value"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        fallback_path = repo / fallback["source"]
        fallback_path.write_text(json.dumps(core.seal({"proposed_rubric": fallback["rubric"]})), encoding="utf-8")
        fallback["source_sha256"] = hashlib.sha256(fallback_path.read_bytes()).hexdigest()
        study.run(api_factory=factory)
        yield repo, study.root


@pytest.fixture
def copied(finished, tmp_path):
    repo, run = finished
    shutil.copytree(repo, tmp_path / "repo")
    return tmp_path / "repo", tmp_path / "repo" / run.relative_to(repo)


def rewrite(path, edit, *, sealed=True):
    value = json.loads(path.read_text())
    if sealed:
        value.pop("record_hash", None)
    edit(value)
    path.write_text(json.dumps(core.seal(value) if sealed else value), encoding="utf-8")


def test_complete_recomputed_audit_and_no_writes(finished, monkeypatch):
    repo, run = finished
    before = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in repo.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Audit must not execute artifacts, call API, or write outputs")

    monkeypatch.setattr(e.BudgetedAPI, "__init__", forbidden)
    monkeypatch.setattr(e.CodingAdapter, "evaluate", forbidden)
    monkeypatch.setattr(auditor.NativeAdapter, "evaluate", forbidden)
    monkeypatch.setattr(e.executor, "evaluate", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    result = auditor.audit(run, repo=repo)
    core.verify(result)
    assert result["complete"]
    assert result["verdict"] == "completed_receipts_and_analysis_consistent"
    assert result["source_skills"]["histories"] == 1
    assert result["source_skills"]["valid_proposals"] == 2
    assert result["source_skills"]["unique_valid_skill_contents"] == 1
    assert result["source_skills"]["approved_nonempty_histories"] == 0
    assert result["calibration"]["primary_equal_logical_calls"]
    assert result["calibration"]["costs_overlap_shared_old_a_not_additive"]
    assert result["final"]["logical_rows"] == 3 * result["final"]["task_instances"]
    assert result["final"]["approved_deployment_positions"] == 0
    assert result["repair"]["available"]
    after = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in repo.rglob("*") if p.is_file()}
    assert before == after


def test_incomplete_requires_explicit_opt_in(copied):
    repo, run = copied
    (run / "results.json").unlink()
    with pytest.raises(ValueError, match="Completed results required"):
        auditor.audit(run, repo=repo)
    result = auditor.audit(run, repo=repo, require_complete=False)
    assert not result["complete"] and result["verdict"] == "complete_evidence_without_runtime_result"
    assert result["evidence_complete"] and not result["original_runtime_completed"]


@pytest.mark.parametrize("which", ["source", "fallback", "panel", "protocol", "skills"])
def test_frozen_identity_and_seals_rejected(copied, which):
    repo, run = copied
    if which == "source":
        (repo / "synthetic_source").write_text("Changed runtime", encoding="utf-8")
    elif which == "fallback":
        (repo / "synthetic-predecessor-receipt").write_text("Changed predecessor", encoding="utf-8")
    elif which == "panel":
        rewrite(run / "panel.json", lambda r: r["final"].pop())
    elif which == "protocol":
        rewrite(run / "protocol.json", lambda r: r.update(histories=2), sealed=False)
    else:
        rewrite(run / "skills_frozen.json", lambda r: r["decisions"].pop())
    with pytest.raises(ValueError):
        auditor.audit(run, repo=repo)


@pytest.mark.parametrize("which", ["request", "reservation", "usage"])
def test_api_content_and_reservation_binding(copied, which):
    repo, run = copied
    path = next((run / "api/calls").glob("*.json"))
    if which == "request":
        rewrite(path, lambda r: r["request"].update(key="another request"), sealed=False)
    elif which == "reservation":
        (run / "api/budget_reservations" / path.name).unlink()
    else:
        rewrite(path, lambda r: r["usage"].update(total_tokens=999999), sealed=False)
    with pytest.raises(ValueError):
        auditor.audit(run, repo=repo)


@pytest.mark.parametrize("which", ["outcome", "drop_artifact", "component_phase", "component_rubric", "summary"])
def test_calibration_recomputes_outcomes_and_full_frozen_grid(copied, which):
    repo, run = copied
    if which == "outcome":
        rewrite(run / "calibration_rows.json", lambda r: r["rows"][0].update(outcome="unknown"))
    elif which == "drop_artifact":
        rewrite(run / "calibration_manifest.json", lambda r: r["artifacts"].pop())
    elif which == "summary":
        rewrite(run / "calibration_summary.json", lambda r: r["primary_gate"].update(action="Support"))
    else:
        path = next((run / "calibration_calls").glob("*.json"))

        def mutate(row):
            receipt = row["result"]["assessments"][0]
            receipt.pop("receipt_hash")
            receipt["phase" if which == "component_phase" else "rubric_hash"] = (
                "development" if which == "component_phase" else digest("wrong rubric"))
            receipt["receipt_hash"] = digest(receipt)

        rewrite(path, mutate)
    with pytest.raises(ValueError):
        auditor.audit(run, repo=repo)


@pytest.mark.parametrize("which", ["alias", "missing_task", "route", "repair_metrics", "repair_summary"])
def test_final_aliases_routes_full_grid_and_repair_metrics(copied, which):
    repo, run = copied
    if which == "alias":
        def mutate(row):
            target = next(r for r in row["rows"] if r["policy"] == "mechanism_routed_candidate")
            target["artifact_hash"] = digest("unexecuted artifact")
        rewrite(run / "final_rows.json", mutate)
    elif which == "missing_task":
        def mutate(row):
            task = row["rows"][0]["task_id"]
            row["rows"] = [r for r in row["rows"] if r["task_id"] != task]
        rewrite(run / "final_rows.json", mutate)
    elif which == "route":
        rewrite(run / "final_frozen.json", lambda r: r["routes"][0]["decision"].update(apply=False))
    elif which == "repair_metrics":
        def mutate(row):
            result = row["rows"][0]["result"]
            result.pop("record_hash")
            result["arms"]["score_only"]["metrics"]["repair_success"] = False
            result["record_hash"] = digest(result)
        rewrite(run / "repair_results.json", mutate)
    else:
        rewrite(run / "results.json", lambda r: r["repair_summary"].update(positions=999))
    with pytest.raises(ValueError):
        auditor.audit(run, repo=repo)


def test_report_never_returns_model_prompts_or_response(copied):
    repo, run = copied
    report = auditor.audit(run, repo=repo)
    encoded = json.dumps(report)
    assert '"system"' not in encoded and '"response"' not in encoded and '"files"' not in encoded
    assert "Offline test sentinel" not in encoded
    assert "not establish public benchmark" in encoded


@pytest.mark.parametrize("which", ["candidate", "selection", "stage", "source", "human_queue"])
def test_research_selection_and_review_evidence_are_receipt_bound(copied, which):
    repo, run = copied
    if which == "candidate":
        rewrite(run / "validator_candidate_frozen.json", lambda r: r.update(rubric=core.initial_rubric()))
    elif which == "selection":
        rewrite(run / "research_selection.json", lambda r: r["model_visible"].pop())
    elif which == "stage":
        path = next((run / "research").rglob("plan.json"))
        rewrite(path, lambda r: r["api_receipt"].update(response="Altered research response"))
    elif which == "source":
        path = next((run / "research").rglob("source_receipt.json"))
        rewrite(path, lambda r: r.update(identity_hash=digest("another research run")))
    else:
        path = run / "human_review/queue.json"
        value = json.loads(path.read_text())
        value.pop("queue_hash")
        value["entries"][0]["evidence"] = {}
        value["queue_hash"] = digest(value)
        path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        auditor.audit(run, repo=repo)


@pytest.fixture(scope="module")
def crashed(tmp_path_factory):
    """Faithfully reach the frozen driver's null/string Counter save crash."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        repo = tmp_path_factory.mktemp("v6-null-model-reporting-control")

        def terminal_revision(request, response):
            if request["kind"] == "v6_native_revision":
                payload = json.loads(request["user"])
                if not payload["skill"] and payload["task"]["id"].startswith("v6-sheet-pricing_policy_replacement"):
                    return None
            return response

        study, factory, _, source, fallback = integration.setup_study(repo, monkeypatch, hook=terminal_revision)
        sentinel = repo / "synthetic_source"
        sentinel.write_text("# Frozen offline null-model fixture\n", encoding="utf-8")
        source["value"] = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        predecessor = repo / fallback["source"]
        predecessor.write_text(json.dumps(core.seal({"proposed_rubric": fallback["rubric"]})), encoding="utf-8")
        fallback["source_sha256"] = hashlib.sha256(predecessor.read_bytes()).hexdigest()
        actual_writer = integration.write_immutable_json

        def terminal_receipt_writer(path, value):
            if Path(path).parent.name == "calls" and value.get("ok") is False:
                value.update(returned_model=None, status=429, error_type="http_status", http_attempt_count=3, usage={})
            return actual_writer(path, value)

        monkeypatch.setattr(integration, "write_immutable_json", terminal_receipt_writer)
        with pytest.raises(TypeError):
            study.run(api_factory=factory)
        assert not (study.root / "results.json").exists()
        yield repo, study.root


@pytest.fixture
def failed_copy(crashed, tmp_path):
    repo, run = crashed
    copied_repo = tmp_path / "repo"
    shutil.copytree(repo, copied_repo)
    (copied_repo / "scripts").mkdir()
    for name in ("audit_coevolution_v6.py", "finalize_coevolution_v6.py"):
        shutil.copyfile(REPO / "scripts" / name, copied_repo / "scripts" / name)
    return copied_repo, copied_repo / run.relative_to(repo)


def finalizer():
    return module("v6_reporting_recovery_exporter", REPO / "scripts/finalize_coevolution_v6.py")


def test_complete_evidence_null_model_not_claimed_as_runtime_completion(failed_copy):
    repo, run = failed_copy
    report = auditor.audit(run, repo=repo, require_complete=False, require_evidence_complete=True)
    assert report["evidence_complete"] and not report["complete"]
    assert report["completion_source"] is None and not report["original_runtime_completed"]
    assert report["api"]["returned_models"]["unreported"] == 1
    assert report["api"]["ledger"]["terminal_errors"] == 1
    assert report["api"]["ledger"]["missing_usage_calls"] == 1
    assert report["api"]["ledger"]["unresolved_reservations"] == []


def test_actual_terminal_crash_recovered_index_audits_without_reexecution(failed_copy, monkeypatch):
    repo, run = failed_copy
    before = {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in run.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery must not call models or rescore submitted artifacts")

    monkeypatch.setattr(e.BudgetedAPI, "__init__", forbidden)
    monkeypatch.setattr(e.CodingAdapter, "evaluate", forbidden)
    monkeypatch.setattr(auditor.NativeAdapter, "evaluate", forbidden)
    recovered = finalizer().finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    core.verify(recovered)
    report = auditor.audit(run, repo=repo)
    assert report["complete"] and report["evidence_complete"]
    assert report["completion_source"] == "recovered_results.json"
    assert report["verdict"] == "recovered_reporting_index_and_evidence_consistent"
    assert not report["original_runtime_completed"]
    assert recovered["returned_models"]["unreported"] == 1
    assert not (run / "results.json").exists()
    after = {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in run.rglob("*") if p.is_file()}
    assert {k: v for k, v in after.items() if k != "recovered_results.json"} == before
    assert finalizer().finalize(run, repo=repo, write=True, runtime_failure_confirmed=True) == recovered


@pytest.mark.parametrize("which", ["missing_final", "missing_task", "unresolved", "artifact_tamper"])
def test_recovery_fails_closed_on_incomplete_or_changed_actual_evidence(failed_copy, which):
    repo, run = failed_copy
    if which == "missing_final":
        (run / "final_rows.json").unlink()
    elif which == "missing_task":
        def remove(row):
            task = row["rows"][0]["task_id"]
            row["rows"] = [r for r in row["rows"] if r["task_id"] != task]
        rewrite(run / "final_rows.json", remove)
    elif which == "unresolved":
        identifier = digest("unresolved offline request")
        (run / "api/budget_reservations" / (identifier + ".json")).write_text(
            json.dumps({"request_hash": identifier, "kind": "v6_native_revision"}), encoding="utf-8")
    else:
        rewrite(next((run / "targets").glob("*.json")), lambda row: row["result"].update(artifact_hash=digest("wrong artifact")))
    with pytest.raises((ValueError, FileNotFoundError)):
        finalizer().finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    assert not (run / "recovered_results.json").exists()


@pytest.mark.parametrize("which", ["manifest", "provenance", "model_attribution"])
def test_recovered_result_requires_exact_provenance_and_unreported_bucket(failed_copy, which):
    repo, run = failed_copy
    finalizer().finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    path = run / "recovered_results.json"
    if which == "manifest":
        rewrite(path, lambda r: r["reporting_recovery"]["source_evidence_manifest"].pop("final_rows.json"))
    elif which == "provenance":
        rewrite(path, lambda r: r["reporting_recovery"].update(original_runtime_completed=True))
    else:
        def misattribute(row):
            row["returned_models"]["glm-5.3"] += row["returned_models"].pop("unreported")
        rewrite(path, misattribute)
    with pytest.raises(ValueError):
        auditor.audit(run, repo=repo)
