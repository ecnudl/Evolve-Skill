"""Auditor fail-closed tests; synthetic receipts are not actual model outcomes."""

import json

import pytest

from scripts import audit_coevolution_v8_feedback as audit
from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v8 import feedback_study as e
from tests.test_coevolution_v8_feedback_study import setup


@pytest.fixture
def completed(tmp_path, monkeypatch):
    study, factory, state = setup(tmp_path, monkeypatch, blocks=1)
    result = study.run(api_factory=factory)
    # Fake integration transport has no genuine global HTTP clock. Skip only
    # this separate pacing reader, and label that fact in its returned report.
    monkeypatch.setattr(audit, "_pacing", lambda *a, **k: {"offline_test_stub_not_http_audit": True})
    return study, state, result


def check(study, **kwargs):
    return audit.audit(study.root, repo=study.repo, panel=study.panel, **kwargs)


def rewrite(path, transform):
    value = json.loads(path.read_text())
    transform(value)
    if "record_hash" in value:
        value = seal({k: v for k, v in value.items() if k != "record_hash"})
    path.write_text(json.dumps(value))


def test_actual_fake_native_grid_replays_without_api_or_run_writes(completed, monkeypatch):
    study, state, result = completed
    before = audit.tree_hashes(study.root)
    calls = len(state["calls"])
    monkeypatch.setattr(e, "make_budgeted_api", lambda *a, **k: pytest.fail("Auditor must not create API"))
    report = check(study)
    assert report["passed"] and report["model_calls_by_auditor"] == 0
    assert report["native_reexecution_performed"]
    assert report["native_private_replays"] == report["native_public_replays"] == 6
    assert report["reference_replays"] == 2
    assert report["summary"] == result["summary"]
    assert report["source_evidence_manifest_hash"] == audit.digest(before)
    assert before == audit.tree_hashes(study.root) and len(state["calls"]) == calls
    assert report["costs_by_stage"]["generic"]["logical_calls"] == 2
    assert report["costs_by_stage"]["structured"]["logical_calls"] == 2
    assert report["sensitivities"]["post_treatment_diagnostic_not_causal_or_primary"]
    assert report["skill_evolution_measured"] is False


def test_provenance_only_mode_never_claims_fresh_semantic_replay(completed, monkeypatch):
    study, _, _ = completed
    monkeypatch.setattr(e, "evaluate", lambda *a, **k: pytest.fail("No native execution in provenance-only mode"))
    report = check(study, reexecute=False)
    assert report["native_reexecution_performed"] is False
    assert report["native_private_replays"] == report["native_public_replays"] == report["reference_replays"] == 0


@pytest.mark.parametrize("directory", ["api/calls", "private_scores", "stages", "intents"])
def test_missing_completed_evidence_fails_instead_of_reconstructing(completed, directory):
    study, state, _ = completed
    path = next((study.root / directory).glob("*.json"))
    path.unlink()
    before, calls = audit.tree_hashes(study.root), len(state["calls"])
    with pytest.raises(ValueError):
        check(study)
    assert before == audit.tree_hashes(study.root) and len(state["calls"]) == calls


def test_source_drift_rejected_before_native_execution(completed):
    study, state, _ = completed
    state["source_hash"] = audit.digest("changed source")
    with pytest.raises(ValueError, match="source hashes"):
        check(study)


def test_resealed_wrong_stage_identity_rejected(completed):
    study, _, _ = completed
    path = next((study.root / "stages").glob("*.json"))
    rewrite(path, lambda r: r.update(block=99))
    with pytest.raises(ValueError, match="Stage cache"):
        check(study)


def test_resealed_native_case_claim_cannot_survive_actual_replay(completed):
    study, _, _ = completed
    path = next(p for p in (study.root / "private_scores").glob("*.json")
                if json.loads(p.read_text())["evaluation"]["case_results"])

    def corrupt(row):
        inner = row["evaluation"]
        inner["case_results"][0]["passed"] = not inner["case_results"][0]["passed"]
        row["evaluation"] = seal({k: v for k, v in inner.items() if k != "record_hash"})

    rewrite(path, corrupt)
    with pytest.raises(ValueError, match="Private oracle replay"):
        check(study)


def test_resealed_derived_result_cannot_replace_preregistered_pair_summary(completed):
    study, _, _ = completed
    rewrite(study.root / "results.json", lambda r: r["summary"]["arms"]["structured"].update(task_micro_success=0.9))
    with pytest.raises(ValueError, match="summary/result"):
        check(study)


def test_sensitivity_keeps_api_selection_separate_from_primary(completed):
    study, _, result = completed
    report = check(study)
    sensitivity = report["sensitivities"]
    assert sensitivity["never_replace_preregistered_all_attempt_metric"] is True
    assert report["summary"] == result["summary"]
    assert sensitivity["both_revision_api_ok"]["pairs"] == 2
    assert sensitivity["both_oracles_available"]["pairs"] < 2
