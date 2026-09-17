"""Metadata-only progress never opens score files or constructs model clients."""

import json

import pytest

from scripts import audit_coevolution_v11 as audit
from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "outputs/coevolution_v11/progress"
    put(root / "protocol.json", seal({"design_name": "smoke", "max_calls": 24}))
    request = {"kind": "v11_coding_solve", "system": "DO_NOT_PRINT_SECRET", "user": "PRIVATE_PROMPT"}
    identifier = digest(request)
    put(root / "api/calls" / (identifier + ".json"), {"request": request, "request_hash": identifier,
        "ok": True, "response": "DO_NOT_PRINT_ANSWER", "usage": {"total_tokens": 5}})
    put(root / "api/budget_reservations" / (identifier + ".json"), {})
    put(root / "api/pacing/admissions/00000001.json", seal({"admitted_wall": 1000.0}))
    put(root / "api/pacing/attempts/00000001.json", seal({"finished_wall": 1001.0}))
    return tmp_path, root


def test_progress_projects_only_transport_metadata(run):
    repo, root = run
    result = audit.progress(root, repo)
    assert result["cached_logical_calls"] == result["api_ok"] == 1
    assert result["http_admissions"] == result["http_outcomes"] == 1
    assert result["unclosed_http_attempt_count"] == 0
    assert result["reported_total_tokens"] == 5
    assert result["last_http_completion_utc"] == "1970-01-01T00:16:41+00:00"
    assert not result["effect_scores_opened"]
    assert all(s not in json.dumps(result) for s in ("SECRET", "PRIVATE_PROMPT", "ANSWER"))


def test_progress_never_opens_final_scores(run):
    repo, root = run
    (root / "results.json").write_text("NOT VALID JSON")
    (root / "final_rows.json").write_text("PRIVATE_SCORES")
    result = audit.progress(root, repo)
    assert result["stage"] == "completed_record_present_not_audited"


def test_unclosed_requests_are_not_classed_as_failures(run):
    repo, root = run
    put(root / "api/budget_reservations" / ("a" * 64 + ".json"), {})
    result = audit.progress(root, repo)
    assert result["unclosed_logical_requests"] == ["a" * 64]
    assert result["terminal_errors"] == {}


def test_invalid_actual_request_refused(run):
    repo, root = run
    path = next((root / "api/calls").glob("*.json"))
    row = json.loads(path.read_text())
    row["request"]["system"] = "changed"
    put(path, row)
    with pytest.raises(ValueError, match="receipt"):
        audit.progress(root, repo)


def test_symlink_evidence_refused(run, tmp_path):
    repo, root = run
    target = tmp_path / "outside"
    target.write_text("private")
    (root / "linked").symlink_to(target)
    with pytest.raises(ValueError, match="symlinks"):
        audit.progress(root, repo)

