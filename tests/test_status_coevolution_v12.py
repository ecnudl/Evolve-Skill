"""Status is aggregate, read-only and incapable of resuming model execution."""

import json
from pathlib import Path

import pytest

from scripts import status_coevolution_v12 as progress
from skillopt.coevolution_v5.core import seal


def put(path, value, sealed=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seal(value) if sealed else value))


def tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "outputs/coevolution_v12/synthetic"
    put(root / "protocol.json", {"design": "smoke", "model": "glm-5.3", "max_calls": 96}, True)
    return tmp_path, root


def test_unprepared_status_creates_no_directories(tmp_path):
    root = tmp_path / "outputs/coevolution_v12/not-created"
    assert progress.status(root, repo=tmp_path) == {"prepared": False, "complete": False, "output": str(root)}
    assert not root.exists() and list(tmp_path.iterdir()) == []


def test_aggregate_calls_pending_and_proposals(fixture):
    repo, root = fixture
    good, bad, pending = "a"*64, "b"*64, "c"*64
    put(root / "api/calls" / (good + ".json"), {"request_hash": good, "ok": True, "http_attempt_count": 1})
    put(root / "api/calls" / (bad + ".json"), {"request_hash": bad, "ok": False,
        "http_attempt_count": 3, "error_type": "synthetic_timeout"})
    for identifier in (good, bad, pending):
        put(root / "runtime/request_intents" / (identifier + ".json"), {"request_hash": identifier})
    put(root / "runtime/stages" / (good + ".json"), {"request_hash": good})
    put(root / "learning/one.json", {"valid": True, "skill": "SHOULD_NOT_BE_PRINTED"}, True)
    put(root / "learning/two.json", {"valid": False}, True)
    put(root / "events/000001.json", {"stage": "learning_round", "history": 0}, True)
    before = tree(root)
    result = progress.status(root, repo=repo)
    assert result["closed_logical_calls"] == 2 and result["successful_calls"] == 1
    assert result["http_attempts_in_closed_calls"] == 4
    assert result["terminal_errors"] == {"synthetic_timeout": 1}
    assert result["pending_solver_receipts"] == 1 and result["pending_solver_stages"] == 2
    assert result["pending_counts_may_be_normal_inflight_not_resume_authority"]
    assert result["skill_proposals"] == 2 and result["valid_proposals"] == 1
    assert "SHOULD_NOT_BE_PRINTED" not in json.dumps(result)
    assert tree(root) == before


def test_complete_status_exposes_only_result_hash_not_scores(fixture):
    repo, root = fixture
    value = {"summary": {"PRIVATE_FINAL_SCORE": 0.987654321}, "private_result": "FINAL_ANSWER_SENTINEL"}
    put(root / "results.json", value, True)
    put(root / "final_frozen.json", {"deployment": "PRIVATE_SKILL_SENTINEL"}, True)
    before = tree(root)
    result = progress.status(root, repo=repo)
    encoded = json.dumps(result)
    assert result["complete"] and result["frozen_final"]
    assert result["result_hash"] == seal(value)["record_hash"]
    assert result["final_scores_not_exposed"]
    assert all(secret not in encoded for secret in ("PRIVATE_FINAL_SCORE", "0.987654321", "FINAL_ANSWER_SENTINEL", "PRIVATE_SKILL_SENTINEL"))
    assert tree(root) == before


def test_pause_marker_is_observed_not_consumed(fixture):
    repo, root = fixture
    (root / "PAUSE_REQUESTED").touch()
    before = tree(root)
    assert progress.status(root, repo=repo)["pause_requested"]
    assert tree(root) == before


def test_no_clients_no_model_api_and_no_writes(fixture, monkeypatch):
    from skillopt.coevolution.budget import BudgetedAPI
    from skillopt.validator_pilot.api import CachedAPI

    repo, root = fixture
    def forbidden(*args, **kwargs):
        pytest.fail("Read-only status attempted client construction or filesystem write")
    before = tree(root)
    monkeypatch.setattr(CachedAPI, "__init__", forbidden)
    monkeypatch.setattr(BudgetedAPI, "__init__", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    result = progress.status(root, repo=repo)
    assert result["no_model_api_calls"] and result["read_only"]
    assert result["process_liveness_checked"] is False
    assert tree(root) == before


@pytest.mark.parametrize("path", ["outputs/coevolution_v12", "outside", "outputs/another/run"])
def test_unsafe_root_rejected_before_access(tmp_path, path):
    with pytest.raises(ValueError):
        progress.status(tmp_path / path, repo=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_symlink_evidence_root_rejected(fixture):
    repo, root = fixture
    (root / "redirect").symlink_to(root.parent, target_is_directory=True)
    before = tree(root)
    with pytest.raises(ValueError, match="Symlink"):
        progress.status(root, repo=repo)
    assert tree(root) == before


def test_changed_sealed_protocol_refused(fixture):
    repo, root = fixture
    path = root / "protocol.json"
    value = json.loads(path.read_text())
    value["model"] = "unregistered-model"
    path.write_text(json.dumps(value))
    before = tree(root)
    with pytest.raises(ValueError, match="checksum"):
        progress.status(root, repo=repo)
    assert tree(root) == before
