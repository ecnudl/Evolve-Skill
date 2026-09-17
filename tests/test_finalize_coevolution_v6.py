"""Fast exporter unit tests; the auditor's separate tests cover real fake-run grids.

The complete-audit result here is stubbed deliberately to isolate reporting
construction, filesystem scope, attestation, and immutable/idempotent writes.
"""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5 import core
from skillopt.validator_pilot.api import digest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("finalize_coevolution_v6", REPO / "scripts/finalize_coevolution_v6.py")
finalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalizer)


def put(path, value, *, sealed=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(core.seal(value) if sealed else value), encoding="utf-8")


def snapshot(repo):
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in repo.rglob("*") if p.is_file()}


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    repo, run = tmp_path / "repo", tmp_path / "repo/run"
    run.mkdir(parents=True)
    for relative in (finalizer.EXPORTER_SOURCE, finalizer.AUDITOR_SOURCE):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPO / relative).read_bytes())
    for relative in finalizer.ROOT_EVIDENCE:
        put(run / relative, {})
    protocol = {"source_rounds": 1, "version": finalizer.VERSION}
    put(run / "protocol.json", protocol)
    put(run / "skills_frozen.json", {"decisions": [{"action": "Restrict"}]})
    put(run / "validator_candidate_frozen.json", {"proposal_hash": digest("proposal")})
    put(run / "repair_results.json", {"no_update": True, "rows": [{"score": None, "error": "transport_unavailable"}]})
    packet = core.seal({"phase": "development", "task_id": "unit-dev"})
    put(run / "source_states/r0.json", {"histories": [{"feedback": [packet]}]})
    for relative in ("human_review/queue.json", "human_review/queue.json.private.json"):
        put(run / relative, {})
    for number, model in enumerate(("glm-5.3", None)):
        put(run / f"api/calls/{number}.json", {"returned_model": model, "ok": number == 0}, sealed=False)
        put(run / f"api/budget_reservations/{number}.json", {"reserved": True}, sealed=False)
    report = {
        "evidence_complete": True,
        "api": {"ledger": {"unresolved_reservations": [], "cached_logical_calls": 2},
                "returned_models": {"glm-5.3": 1, "unreported": 1}},
        "calibration": {"complete": True, "summary": {"action": "Hold"}},
        "final": {"complete": True, "summary": {"native": {"score": None, "unknown": 1}}},
        "research": {"complete": True, "proposal_hash": digest("proposal")},
        "repair": {"summary": {"unknown": 1}},
        "source_skills": {"unique_retained_feedback": 1},
        "human_review": {"status": "pending_external_human"},
    }
    calls = []

    def audited(*args, **kwargs):
        calls.append(kwargs)
        return core.seal(report)

    monkeypatch.setattr(finalizer.auditor, "audit", audited)
    return repo, run, report, calls


def test_dry_run_is_complete_offline_index_without_any_writes(prepared, monkeypatch):
    repo, run, _, calls = prepared
    before = snapshot(repo)

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery must not write, execute, call an API, or read credentials")

    monkeypatch.setattr(finalizer, "write_immutable_json", forbidden)
    monkeypatch.setattr(finalizer.auditor.CodingAdapter, "evaluate", forbidden)
    monkeypatch.setattr(finalizer.auditor.NativeAdapter, "evaluate", forbidden)
    result = finalizer.finalize(run, repo=repo)
    core.verify(result)
    assert result["status"] == "complete"
    assert result["returned_models"] == {"glm-5.3": 1, "unreported": 1}
    assert result["final"]["native"]["score"] is None
    assert result["repair"][0]["score"] is None
    assert result["reporting_recovery"]["original_runtime_completed"] is False
    assert result["reporting_recovery"]["runtime_failure_confirmation"]["confirmed"] is False
    assert calls == [{"repo": repo, "require_complete": False, "require_evidence_complete": True}]
    assert snapshot(repo) == before


def test_write_requires_operator_attestation_and_creates_only_new_recovery_file(prepared):
    repo, run, _, _ = prepared
    before = snapshot(repo)
    with pytest.raises(ValueError, match="operator confirmation"):
        finalizer.finalize(run, repo=repo, write=True)
    assert snapshot(repo) == before
    result = finalizer.finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    after = snapshot(repo)
    assert set(after) - set(before) == {"run/recovered_results.json"}
    assert all(after[k] == v for k, v in before.items())
    assert not (run / "results.json").exists()
    assert json.loads((run / "recovered_results.json").read_text()) == result
    assert result["reporting_recovery"]["runtime_failure_confirmation"] == {
        "kind": "operator_attestation", "confirmed": True, "independently_verified_process_exit": False}


def test_idempotent_second_write_and_dry_run_reuse_confirmed_recovery(prepared):
    repo, run, _, _ = prepared
    first = finalizer.finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    before = snapshot(repo)
    assert finalizer.finalize(run, repo=repo, write=True, runtime_failure_confirmed=True) == first
    assert finalizer.finalize(run, repo=repo) == first
    assert snapshot(repo) == before


@pytest.mark.parametrize("missing", ["final_rows.json", "calibration_summary.json", "repair_results.json",
                                     "human_review/queue.json.private.json", "source_states/r0.json"])
def test_missing_completed_stage_cannot_be_reported_complete(prepared, missing):
    repo, run, _, _ = prepared
    (run / missing).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        finalizer.finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    assert not (run / "recovered_results.json").exists()


@pytest.mark.parametrize("stage", ["calibration", "final", "research"])
def test_incomplete_independent_stage_proof_rejected(prepared, stage):
    repo, run, report, _ = prepared
    report[stage]["complete"] = False
    with pytest.raises(ValueError, match="incomplete"):
        finalizer.finalize(run, repo=repo)


def test_unresolved_api_requests_rejected(prepared):
    repo, run, report, _ = prepared
    report["api"]["ledger"]["unresolved_reservations"] = [digest("unresolved")]
    with pytest.raises(ValueError, match="Unresolved"):
        finalizer.finalize(run, repo=repo)


def test_tampered_sealed_source_record_rejected_even_after_stub_audit(prepared):
    repo, run, _, _ = prepared
    path = run / "skills_frozen.json"
    value = json.loads(path.read_text())
    value["decisions"] = [{"action": "Commit"}]
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="checksum"):
        finalizer.finalize(run, repo=repo)


def test_original_results_are_never_overwritten(prepared):
    repo, run, _, _ = prepared
    put(run / "results.json", {"status": "complete"})
    before = snapshot(repo)
    with pytest.raises(ValueError, match="Original results already exist"):
        finalizer.finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    assert snapshot(repo) == before


def test_specific_null_counter_failure_must_be_present(prepared):
    repo, run, report, _ = prepared
    put(run / "api/calls/1.json", {"returned_model": "glm-5.3", "ok": False}, sealed=False)
    report["api"]["returned_models"] = {"glm-5.3": 2}
    with pytest.raises(ValueError, match="mixed null/string"):
        finalizer.finalize(run, repo=repo)


def test_successful_call_missing_model_is_not_the_confirmed_terminal_failure(prepared):
    repo, run, _, _ = prepared
    put(run / "api/calls/1.json", {"returned_model": None, "ok": True}, sealed=False)
    with pytest.raises(ValueError, match="mixed null/string"):
        finalizer.finalize(run, repo=repo)


def test_full_evidence_manifest_covers_probes_and_excludes_reporting_products(prepared):
    repo, run, _, _ = prepared
    put(run / "probes/example.json", {"probe": "retained"})
    put(run / "research/snapshot/source.json", {"source": "retained"})
    put(run / "unrelated_report.json", {"report": "not an experimental input"})
    result = finalizer.finalize(run, repo=repo)
    manifest = result["reporting_recovery"]["source_evidence_manifest"]
    assert "probes/example.json" in manifest and "research/snapshot/source.json" in manifest
    assert "unrelated_report.json" not in manifest
    assert "recovered_results.json" not in manifest
    assert result["reporting_recovery"]["exporter_source_sha256"] == hashlib.sha256(
        (repo / finalizer.EXPORTER_SOURCE).read_bytes()).hexdigest()


def test_symlinked_evidence_rejected(prepared, tmp_path):
    repo, run, _, _ = prepared
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (run / "final_rows.json").unlink()
    (run / "final_rows.json").symlink_to(outside)
    with pytest.raises(ValueError, match="unsafe"):
        finalizer.finalize(run, repo=repo)


def test_mutation_during_validation_prevents_write(prepared, monkeypatch):
    repo, run, report, _ = prepared

    def mutate(*args, **kwargs):
        put(run / "final_rows.json", {"rows": ["changed while auditing"]})
        return core.seal(deepcopy(report))

    monkeypatch.setattr(finalizer.auditor, "audit", mutate)
    with pytest.raises(ValueError, match="changed during verification"):
        finalizer.finalize(run, repo=repo, write=True, runtime_failure_confirmed=True)
    assert not (run / "recovered_results.json").exists()


def test_cli_dry_run_output_has_no_artifacts_or_false_runtime_success(prepared, monkeypatch, capsys):
    repo, run, _, _ = prepared
    before = snapshot(repo)
    monkeypatch.setattr("sys.argv", ["finalize_coevolution_v6", "--run", str(run), "--repo", str(repo)])
    finalizer.main()
    output = json.loads(capsys.readouterr().out)
    assert output["recovery_valid"] and not output["written"]
    assert output["original_runtime_completed"] is False
    assert "artifact" not in output
    assert snapshot(repo) == before
