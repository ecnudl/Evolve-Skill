"""Read-only audit tests; mock host execution/pacing are explicitly offline fixtures."""

import json
from pathlib import Path

import pytest

from scripts import audit_coevolution_v8_calibration as a
from skillopt.coevolution_v5 import core
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v8_calibration_study import setup


def forbidden(*args, **kwargs):
    pytest.fail("Audit must not mutate artifacts, send requests, or run native code")


@pytest.fixture
def completed(tmp_path, monkeypatch):
    run, root, state, repo, _, _ = setup(tmp_path, monkeypatch)
    result = run()
    service = state["calls"][0]["request"]["service"]
    (root / "api/service.json").write_text(json.dumps(service))
    pacing_calls = []

    def pacing(run_root, protocol, calls, *, require_complete):
        pacing_calls.append((run_root, protocol, len(calls), require_complete))
        return {"offline_fixture_pacing_not_provider_evidence": True, "checked_calls": len(calls)}

    monkeypatch.setattr(a, "_pacing", pacing)
    return root, repo, result, state, pacing_calls


def mutate(path, change):
    row = json.loads(path.read_text())
    change(row)
    if "record_hash" in row:
        row = core.seal({k: v for k, v in row.items() if k != "record_hash"})
    path.write_text(json.dumps(row))


def test_complete_metrics_gate_cost_and_exact_shared_budget(completed):
    root, repo, result, _, pacing_calls = completed
    report = a.audit(root, repo, require_complete=True)
    assert report["status"] == "verified_complete"
    assert report["metrics_computed"] and report["gate_computed"]
    assert report["expected_calls"] == report["verified_components"] == 24
    assert report["ledger"] == result["ledger"]
    assert report["gate"] == result["decision"]["gate"]
    assert report["result_hash"] == result["record_hash"]
    assert report["cost"]["policy_calls"] == {"old_single": 8, "new_single": 8, "old_double": 16, "portfolio": 16}
    assert report["cost"]["equal_call_caps_not_equal_tokens_or_invoice"]
    assert all(v["bad_detection"] == v["good_false_rejection"] == v["unknown"] == 0
               for v in report["policy_metrics_cluster_equal_weight"].values())
    assert pacing_calls[-1][2:] == (24, True)
    assert pacing_calls[-1][1]["pacing_policy"] == vars(a.driver.PACING)


def test_read_only_complete_does_not_call_any_writer_model_or_oracle(completed, monkeypatch):
    root, repo, _, _, _ = completed
    before = {str(p.relative_to(repo)): digest(p.read_text()) for p in repo.rglob("*.json")}
    monkeypatch.setattr(a.driver, "run", forbidden)
    monkeypatch.setattr(a.bridge, "assess_screen", forbidden)
    monkeypatch.setattr(a.bridge, "prepare_screen", forbidden)
    monkeypatch.setattr(a.bridge, "write_immutable_json", forbidden)
    monkeypatch.setattr(a.driver.executor, "execute_inputs", forbidden)
    monkeypatch.setattr(a.driver.executor, "evaluate", forbidden)
    monkeypatch.setattr(a.bridge.CodingAdapter, "evaluate", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    report = a.audit(root, repo, require_complete=True)
    assert report["read_only"] and report["new_api_calls"] == 0 and not report["native_code_reexecuted"]
    after = {str(p.relative_to(repo)): digest(p.read_text()) for p in repo.rglob("*.json")}
    assert before == after


def test_pending_never_computes_or_reads_performance_or_decision(completed, monkeypatch):
    root, repo, _, _, _ = completed
    (root / "results.json").unlink()
    next((root / "components").glob("*.json")).unlink()
    monkeypatch.setattr(a.statistics, "summarize_validator", forbidden)
    monkeypatch.setattr(a, "validator_activation", forbidden)
    monkeypatch.setattr(a.bridge, "assess_screen", forbidden)
    original = Path.read_text

    def no_results(path, *args, **kwargs):
        assert path.name not in {"v8_decision.json", "v8_private_calibration.json"}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", no_results)
    report = a.audit(root, repo)
    assert report["status"] == "pending" and report["verified_components"] == 23
    assert not report["metrics_computed"] and not report["gate_computed"]
    assert "policy_metrics_cluster_equal_weight" not in report and "gate" not in report


def test_pending_explicit_require_complete_fails_without_writing(completed):
    root, repo, _, _, _ = completed
    path = root / "results.json"
    path.unlink()
    with pytest.raises(ValueError, match="Pending"):
        a.audit(root, repo, require_complete=True)
    assert not path.exists()


@pytest.mark.parametrize("name", ["results.json", "registry_gate", "registry_evidence"])
def test_resealed_result_and_registry_mutation_rejected(completed, name):
    root, repo, _, _, _ = completed
    if name == "results.json":
        mutate(root / name, lambda row: row.update(components_hash=digest("wrong-components")))
    else:
        screen = a._read(root / "screen.json")
        directory = Path(screen["registry_root"]) / screen["screen_id"]
        if name == "registry_gate":
            mutate(directory / "v8_decision.json", lambda row: row.update(activate_next_round=True))
        else:
            mutate(directory / "v8_private_calibration.json", lambda row: row["rows"].pop())
    with pytest.raises(ValueError):
        a.audit(root, repo, require_complete=True)


@pytest.mark.parametrize("directory", ["components", "api/calls", "api/budget_reservations"])
def test_extra_and_duplicate_artifacts_not_hidden(completed, directory):
    root, repo, _, _, _ = completed
    original = next((root / directory).glob("*.json"))
    (root / directory / (digest("extra-position") + ".json")).write_text(original.read_text())
    with pytest.raises(ValueError):
        a.audit(root, repo, require_complete=True)


def test_same_model_profile_and_cost_fields_are_enforced(completed):
    root, repo, _, _, _ = completed
    mutate(root / "api/service.json", lambda row: row.update(max_retries=999))
    with pytest.raises(ValueError, match="profile"):
        a.audit(root, repo, require_complete=True)


def test_source_mutation_fails_before_gate(completed, monkeypatch):
    root, repo, _, state, _ = completed
    state["source_hash"] = digest("changed-source")
    monkeypatch.setattr(a, "_reconstruct", forbidden)
    with pytest.raises(ValueError, match="source"):
        a.audit(root, repo, require_complete=True)


def test_missing_registry_gate_is_not_recreated(completed):
    root, repo, _, _, _ = completed
    screen = a._read(root / "screen.json")
    path = Path(screen["registry_root"]) / screen["screen_id"] / "v8_decision.json"
    path.unlink()
    with pytest.raises(FileNotFoundError):
        a.audit(root, repo, require_complete=True)
    assert not path.exists()


def test_call_payload_and_component_schema_are_bound(completed):
    root, repo, _, _, _ = completed
    path = next((root / "api/calls").glob("*.json"))
    mutate(path, lambda row: row["request"].update(max_tokens=1))
    with pytest.raises(ValueError, match="payload"):
        a.audit(root, repo, require_complete=True)


def test_pacing_enforcement_uses_real_shared_auditor_not_completion_timestamps():
    from scripts.audit_coevolution_v7 import _pacing

    assert a._pacing is _pacing


def test_cli_has_no_write_option_and_prints_pending_json(monkeypatch, capsys):
    monkeypatch.setattr(a.sys, "argv", ["audit", "--output", "existing-run"])
    monkeypatch.setattr(a, "audit", lambda *args, **kwargs: {"status": "pending", "metrics_computed": False})
    a.main()
    assert json.loads(capsys.readouterr().out)["status"] == "pending"


def test_cli_failure_has_nonzero_exit_no_recovery(monkeypatch, capsys):
    monkeypatch.setattr(a.sys, "argv", ["audit", "--output", "existing-run", "--require-complete"])

    def fail(*args, **kwargs):
        raise ValueError("broken immutable evidence")

    monkeypatch.setattr(a, "audit", fail)
    with pytest.raises(SystemExit) as exc:
        a.main()
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "audit_failed"
