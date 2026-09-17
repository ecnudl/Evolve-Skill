"""Independent metadata-only progress and fail-closed audit wrapper tests."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import audit_coevolution_v9 as a
from skillopt.coevolution_v5.core import seal


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def run(tmp_path):
    repo = tmp_path / "repo"
    root = repo / "outputs/coevolution_v9/test"
    manifest = seal({"settings": {"sources": {"train": {"path": "/fixture/train.arrow"},
                                               "validation": {"path": "/fixture/validation.arrow"}}}})
    protocol = seal({"version": a.VERSION, "design_name": "smoke", "design": deepcopy(a.DESIGNS["smoke"]),
                     "max_calls": 56, "data_manifest_hash": manifest["record_hash"]})
    put(root / "protocol.json", protocol)
    put(root / "data_manifest.json", manifest)
    receipt = {"request_hash": "a" * 64, "request": {"kind": "v9_searchqa_solve", "user": "TASK_PAYLOAD_SECRET"},
               "response": "ANSWER_PAYLOAD_SECRET", "ok": True, "http_attempt_count": 1,
               "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}
    put(root / "api/calls" / ("a" * 64 + ".json"), receipt)
    put(root / "api/budget_reservations" / ("a" * 64 + ".json"), {})
    put(root / "api/budget_reservations" / ("b" * 64 + ".json"), {})
    return repo, root, protocol, manifest


def completed(run):
    _, root, protocol, _ = run
    result = seal({"version": a.VERSION, "complete": True, "protocol_hash": protocol["record_hash"],
                   "summary": {"fixture_summary": True}, "ledger": {"fixture_ledger": True}})
    put(root / "results.json", result)
    return result


def test_progress_reads_no_task_learning_or_gate_payload(run, monkeypatch):
    repo, root, _, _ = run
    for relative in ("histories/0.json", "learning/history_0/result.json", "solves/one.json", "final_rows.json"):
        put(root / relative, {"GOLD_OR_SCORE_DO_NOT_OPEN": True})
    original = Path.read_text
    opened = []

    def guard(path, *args, **kw):
        relative = path.relative_to(root)
        assert str(relative) == "protocol.json" or str(relative).startswith("api/calls/")
        opened.append(relative)
        return original(path, *args, **kw)

    monkeypatch.setattr(Path, "read_text", guard)
    monkeypatch.setattr(a, "Study", lambda *args, **kw: pytest.fail("Progress must not create Study"))
    result = a.audit(root, repo)
    assert result["progress"]["gate_history_records_present"] == 1
    assert result["progress"]["completed_logical_calls"] == 1
    assert result["progress"]["pending_reservations"] == 1
    assert result["progress"]["total_tokens"] == 7
    assert result["progress"]["intermediate_scores_computed"] is False
    assert result["complete_integrity_audit"] is False
    assert len(opened) == 2
    assert "PAYLOAD_SECRET" not in json.dumps(result)


def test_terminal_failures_missing_usage_and_free_form_errors(run):
    repo, root, _, _ = run
    receipt = {"request_hash": "b" * 64, "request": {"kind": "v9_native_analyst"}, "ok": False,
               "error_type": "timeout", "http_attempt_count": 3, "usage": {}, "status": None}
    put(root / "api/calls" / ("b" * 64 + ".json"), receipt)
    result = a.audit(root, repo)["progress"]
    assert result["api_ok"] == 1 and result["terminal_calls"] == 1
    assert result["http_attempts"] == 4
    assert result["failure_categories"] == {"timeout": 1}
    assert result["terminal_http_statuses"] == {"no_http_status": 1}
    assert result["missing_usage_calls"] == 1
    assert result["missing_usage_fields"]["total_tokens"] == 1
    receipt["error_type"] = "PRIVATE_PROVIDER_ERROR_CONTAINING_KEY"
    receipt["request"]["kind"] = "PRIVATE_REQUEST_KEY"
    put(root / "api/calls" / ("b" * 64 + ".json"), receipt)
    result = a.audit(root, repo)
    assert "PRIVATE_" not in json.dumps(result)
    assert result["progress"]["failure_categories"] == {"other_or_missing_error": 1}


@pytest.mark.parametrize("marker,stage", [
    ("learning/history_0/identity.json", "native_skillopt_update"),
    ("learning/history_0/result.json", "source_confirmation"),
    ("final_freeze.json", "frozen_final_execution"),
    ("results.json", "completed_record_present_not_yet_audited"),
])
def test_progress_stage_does_not_open_stage_record(run, marker, stage):
    repo, root, _, _ = run
    put(root / marker, {"not_read_or_used_as_a_score": True})
    assert a.audit(root, repo)["progress"]["stage"] == stage


def test_require_complete_never_resumes_missing_result(run, monkeypatch):
    repo, root, _, _ = run
    monkeypatch.setattr(a, "Study", lambda *args, **kw: pytest.fail("Do not instantiate an incomplete runner"))
    before = a._tree_hashes(root)
    with pytest.raises(ValueError, match="completed result is required"):
        a.audit(root, repo, require_complete=True)
    assert a._tree_hashes(root) == before


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(complete=False), lambda r: r.update(complete=1),
    lambda r: r.update(protocol_hash="b" * 64), lambda r: r.update(version="wrong"),
])
def test_require_complete_rejects_false_or_unbound_completion(run, mutation, monkeypatch):
    repo, root, _, _ = run
    result = completed(run)
    mutation(result)
    put(root / "results.json", seal({k: v for k, v in result.items() if k != "record_hash"}))
    monkeypatch.setattr(a, "Study", lambda *args, **kw: pytest.fail("Do not reconstruct invalid completion"))
    with pytest.raises(ValueError, match="sealed completed result"):
        a.audit(root, repo, require_complete=True)


def test_completed_wrapper_uses_frozen_design_forbidden_api_and_byte_check(run, monkeypatch, capsys):
    repo, root, _, _ = run
    expected = completed(run)
    calls = []

    class Offline:
        completed = True

        def __init__(self, actual_repo, actual_root, *, design, cache_paths):
            assert actual_repo == repo and actual_root == root
            assert design == "smoke"
            assert cache_paths == {"train": "/fixture/train.arrow", "validation": "/fixture/validation.arrow"}

        def run(self, *, api_factory):
            assert api_factory is a.forbidden_api
            with pytest.raises(RuntimeError, match="forbids"):
                api_factory()
            calls.append(1)
            print("CAPTURED_DRIVER_OUTPUT")
            return expected

    monkeypatch.setattr(a, "Study", Offline)
    before = a._tree_hashes(root)
    report = a.audit(root, repo, require_complete=True)
    assert calls == [1]
    assert a._tree_hashes(root) == before
    assert report["complete_integrity_audit"] is report["run_files_unchanged"] is True
    assert report["result_hash"] == expected["record_hash"]
    assert report["model_api_calls"] == 0
    assert "CAPTURED_DRIVER_OUTPUT" not in capsys.readouterr().out


@pytest.mark.parametrize("behavior", ["writes", "different_result", "tries_api", "loses_completion"])
def test_completed_wrapper_fails_closed_on_nonreadonly_or_inconsistent_replay(run, monkeypatch, behavior):
    repo, root, _, _ = run
    expected = completed(run)

    class Broken:
        completed = behavior != "loses_completion"

        def __init__(self, *args, **kw):
            pass

        def run(self, *, api_factory):
            if behavior == "writes":
                put(root / "unexpected.json", {})
            if behavior == "tries_api":
                return api_factory()
            return {**expected, "wrong": True} if behavior == "different_result" else expected

    monkeypatch.setattr(a, "Study", Broken)
    with pytest.raises((ValueError, RuntimeError)):
        a.audit(root, repo, require_complete=True)


@pytest.mark.parametrize("field,value", [("ok", 1), ("request_hash", "b" * 64), ("http_attempt_count", 0),
                                        ("http_attempt_count", 4), ("usage", None),
                                        ("usage", {"total_tokens": -1}), ("usage", {"total_tokens": True})])
def test_progress_rejects_invalid_transport_metadata(run, field, value):
    repo, root, _, _ = run
    path = root / "api/calls" / ("a" * 64 + ".json")
    row = json.loads(path.read_text())
    row[field] = value
    put(path, row)
    with pytest.raises(ValueError):
        a.audit(root, repo)


@pytest.mark.parametrize("location", ["outputs/coevolution_v9", "outputs/another_run", "outputs/coevolution_v9/missing"])
def test_audit_target_must_be_existing_isolated_v9_run(run, location):
    repo, _, _, _ = run
    with pytest.raises(ValueError):
        a.audit(repo / location, repo)


def test_symlink_inside_run_rejected_without_reading_target(run, tmp_path):
    repo, root, _, _ = run
    target = tmp_path / "private"
    target.write_text("SECRET")
    (root / "symlink").symlink_to(target)
    with pytest.raises(ValueError, match="Symlink"):
        a.audit(root, repo)


def test_resealed_design_changes_rejected(run):
    repo, root, protocol, _ = run
    modified = deepcopy(protocol)
    modified["design"]["confirmation"] = 2
    put(root / "protocol.json", seal({k: v for k, v in modified.items() if k != "record_hash"}))
    with pytest.raises(ValueError, match="recognized"):
        a.audit(root, repo)


def test_cli_only_prints_audit_result(run, monkeypatch, capsys):
    _, root, _, _ = run
    monkeypatch.setattr(a, "audit", lambda output, require_complete: {"output_is_expected": output == root,
                                                                    "require_complete": require_complete})
    assert a.main(["--output", str(root), "--require-complete"]) == 0
    assert json.loads(capsys.readouterr().out) == {"output_is_expected": True, "require_complete": True}
