import json

import pytest

from scripts import continue_coevolution_v15 as queue
from skillopt.coevolution_v12.study import save
from skillopt.coevolution_v15 import study


@pytest.fixture
def completed(tmp_path, monkeypatch):
    protocol = save(tmp_path / "protocol.json", {"design": "smoke", "source_hashes": {"fixture": "hash"}})
    result = {"design": "smoke", "complete": True, "protocol_hash": protocol["record_hash"],
              "ledger": {"cached_logical_calls": 20, "terminal_errors": 0},
              "learning": {"valid": 6}, "validator_evolution": {"valid_proposals": 2, "accepted": 0}}
    save(tmp_path / "results.json", result)
    (tmp_path / "supervisor.log").write_text(json.dumps({"stage": "finished", "returncode": 0}) + "\n")
    monkeypatch.setattr(study, "source_hashes", lambda repo: {"fixture": "hash"})
    return tmp_path, result


def test_readiness_does_not_require_positive_score_or_validator_acceptance(completed):
    root, _ = completed
    assert queue.ready(root, root)[0] == "ready"


def test_pause_prevents_automatic_launch(completed):
    root, _ = completed
    (root / "PAUSE").touch()
    assert queue.ready(root, root) == ("stop", "explicit_pause")


def test_scientific_finish_event_without_supervisor_audit_is_not_enough(tmp_path):
    (tmp_path / "supervisor.log").write_text('not json\n{"stage":"finished","result_hash":"x"}\n')
    assert queue.last_supervisor_terminal(tmp_path) is None
    assert queue.ready(tmp_path, tmp_path)[0] == "wait"


@pytest.mark.parametrize("code", [1, 75])
def test_operational_failure_does_not_resume_or_launch(completed, code):
    root, _ = completed
    (root / "supervisor.log").write_text(json.dumps({"stage": "stopped", "returncode": code}) + "\n")
    assert queue.ready(root, root)[0] == "stop"


def test_frozen_source_drift_stops(completed, monkeypatch):
    root, _ = completed
    monkeypatch.setattr(study, "source_hashes", lambda repo: {"fixture": "different"})
    assert queue.ready(root, root)[0] == "stop"
