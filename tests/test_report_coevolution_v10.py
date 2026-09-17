"""Aggregate-only report rendering and immutable offline publication tests."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import report_coevolution_v10 as reporter
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v10 import analysis
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def reseal(value):
    return core.seal({key: item for key, item in value.items() if key != "record_hash"})


@pytest.fixture
def completed(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    root = repo / "outputs/coevolution_v10/fixture"
    source = repo / "docs/frozen-protocol.md"
    source.parent.mkdir(parents=True)
    source.write_text("Frozen fixture source.")
    expected = {f"PRIVATE_TASK_{i}": {"cluster_id": f"PRIVATE_CLUSTER_{i}"} for i in range(2)}
    source_skills = {0: {"skill_hash": digest("initial"), "learned": False},
                     1: {"skill_hash": digest("alpha"), "learned": True},
                     2: {"skill_hash": digest("beta"), "learned": True}}
    rows = []
    for task, identity in expected.items():
        for history in range(3):
            for policy in analysis.POLICIES:
                key = ("" if policy in {"no_skill", "scope_gated"} else "initial" if policy == "initial" else
                       {0: "initial", 1: "alpha", 2: "beta"}[history])
                unknown = task.endswith("1") and key == "beta"
                rows.append({"task_id": task, "cluster_id": identity["cluster_id"], "history": history,
                    "policy": policy, "skill_hash": digest(key), "request_hash": digest([task, key]),
                    "api_ok": not unknown, "hard": None if unknown else 1, "soft": None if unknown else 1.0})
    gate = analysis.portfolio_gate([row for row in rows if row["policy"] != "scope_gated"],
                                   expected_tasks=expected, source_skills=source_skills)
    summary = analysis.summarize_final(rows, expected_tasks=expected, histories=[0, 1, 2], bootstrap_samples=100)
    learned = {row["skill_hash"] for row in source_skills.values() if row["learned"]}
    summary["actual_learned_usage"] = {policy: sum(row["policy"] == policy and row["skill_hash"] in learned for row in rows)
                                       for policy in analysis.POLICIES}
    summary["scope_fallback_positions"] = 6
    protocol = core.seal({"design_name": "smoke", "model": "glm-5.3", "histories": [0, 1, 2],
        "counts": {"confirmation": 2, "final": 2},
        "source_hashes": {str(source.relative_to(repo)): hashlib.sha256(source.read_bytes()).hexdigest()}})
    ledger = {"cached_logical_calls": 16, "max_logical_calls": 16, "http_attempts_from_cached_records": 17,
              "successful_calls": 15, "terminal_errors": 1, "prompt_tokens": 10,
              "completion_tokens": 20, "total_tokens": 30, "missing_usage_calls": 1}
    result = core.seal({"complete": True, "protocol_hash": protocol["record_hash"], "summary": summary,
        "gate": gate, "ledger": ledger, "smoke_not_effect_evidence": True,
        "reference_summary": {"confirmation": {"total": 2, "valid": 2, "unknown": 0},
                              "final": {"total": 2, "valid": 2, "unknown": 0}},
        "outcome_categories": {"passed": 15, "api_unknown": 1},
        "private_reference": "NEVER_PRINT_REFERENCE"})
    audit = core.seal({"complete_integrity_audit": True, "run_files_unchanged": True, "model_api_calls": 0,
                      "result_hash": result["record_hash"], "protocol_hash": protocol["record_hash"],
                      "verified_run_files": 2})
    put(root / "protocol.json", protocol)
    put(root / "results.json", result)
    calls = []

    def replay(output, actual_repo):
        assert output == root and actual_repo == repo
        calls.append(1)
        return {"protocol": protocol, "result": result, "audit": audit}

    monkeypatch.setattr(reporter.runner, "completed_replay", replay)
    return repo, root, protocol, result, audit, calls


def test_complete_report_aggregates_only_actual_usage_and_unknowns(completed):
    repo, root, _, result, _, calls = completed
    before = reporter.runner.tree_hashes(root)
    reported = reporter.report(root, repo=repo)
    path = Path(reported["report"])
    assert path == repo / "docs/coevolution-v10-fixture-report.md" and reported["created"]
    text = path.read_text()
    assert "Smoke 接口验收，不构成效果证据" in text
    assert "真正新 Skill 使用位置" in text and "全部回退 No-Skill" in text
    assert "不是学到跨域能力" in text and "旧 SearchQA final" in text
    assert "不补抽、不换题" in text and "仅涉及不可评" not in text
    assert "只涉及不可评位置" in text and "unknown 损失" in text
    assert "Holm" in text and "bootstrap" in text and "mtime" in text
    assert "逻辑调用 16" in text and "HTTP attempts 17" in text
    assert "PRIVATE_TASK" not in text and "PRIVATE_CLUSTER" not in text and "NEVER_PRINT_REFERENCE" not in text
    assert reported["result_hash"] == result["record_hash"] and calls == [1]
    assert reporter.runner.tree_hashes(root) == before


def test_report_publication_is_idempotent_and_existing_different_content_is_preserved(completed):
    repo, root, _, _, _, calls = completed
    first = reporter.report(root, repo=repo)
    second = reporter.report(root, repo=repo)
    assert first["created"] is True and second["created"] is False
    assert first["report_sha256"] == second["report_sha256"] and calls == [1, 1]
    Path(first["report"]).write_text("user-owned modification")
    with pytest.raises(ValueError, match="Existing report differs"):
        reporter.report(root, repo=repo)
    assert Path(first["report"]).read_text() == "user-owned modification"


def test_explicit_outside_repo_new_md_report_is_allowed(completed, tmp_path):
    repo, root, _, _, _, _ = completed
    target = tmp_path / "presentation/report.md"
    assert reporter.report(root, target, repo)["created"] and target.is_file()


@pytest.mark.parametrize("location", ["skillopt/report.md", "outputs/report.md", "data/report.md",
                                     "outputs/coevolution_v10/fixture/report.md", ".env", "docs/report.json",
                                     "docs/frozen-protocol.md"])
def test_frozen_source_run_and_nonmarkdown_destinations_rejected(completed, location):
    repo, root, _, _, _, _ = completed
    with pytest.raises(ValueError):
        reporter.report(root, repo / location, repo)


def test_symlink_destination_is_rejected(completed, tmp_path):
    repo, root, _, _, _, _ = completed
    target = tmp_path / "outside.md"
    target.write_text("unrelated user content")
    link = repo / "docs/link.md"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlinks"):
        reporter.report(root, link, repo)
    assert target.read_text() == "unrelated user content"


@pytest.mark.parametrize("field,value", [("complete_integrity_audit", False), ("run_files_unchanged", False),
                                          ("model_api_calls", 1), ("result_hash", "0" * 64)])
def test_invalid_completed_audit_refuses_report(completed, monkeypatch, field, value):
    repo, root, protocol, result, audit, _ = completed
    audit = deepcopy(audit)
    audit[field] = value
    monkeypatch.setattr(reporter.runner, "completed_replay", lambda *args: {
        "protocol": protocol, "result": result, "audit": reseal(audit)})
    with pytest.raises(ValueError, match="audited result"):
        reporter.report(root, repo=repo)
    assert not (repo / "docs/coevolution-v10-fixture-report.md").exists()


def test_changed_source_refuses_publication(completed):
    repo, root, _, _, _, _ = completed
    (repo / "docs/frozen-protocol.md").write_text("changed")
    with pytest.raises(ValueError, match="Frozen source changed"):
        reporter.report(root, repo=repo)


def test_result_changes_after_completed_audit_refuse_publication(completed, monkeypatch):
    repo, root, protocol, result, audit, _ = completed

    def replay(*args):
        put(root / "results.json", core.seal({"complete": True, "changed": True}))
        return {"protocol": protocol, "result": result, "audit": audit}

    monkeypatch.setattr(reporter.runner, "completed_replay", replay)
    with pytest.raises(ValueError, match="audited result"):
        reporter.report(root, repo=repo)


def test_run_artifact_change_after_audit_is_detected(completed, monkeypatch):
    repo, root, protocol, result, audit, _ = completed

    def replay(*args):
        put(root / "unexpected.json", {"mutation": True})
        return {"protocol": protocol, "result": result, "audit": audit}

    monkeypatch.setattr(reporter.runner, "completed_replay", replay)
    with pytest.raises(ValueError, match="Run changed"):
        reporter.report(root, repo=repo)


def test_report_propagates_active_run_rejection_without_writes(completed, monkeypatch):
    repo, root, _, _, _, _ = completed

    def active(*args):
        raise ValueError("Another process is actively running this experiment")

    monkeypatch.setattr(reporter.runner, "completed_replay", active)
    before = reporter.runner.tree_hashes(root)
    with pytest.raises(ValueError, match="actively running"):
        reporter.report(root, repo=repo)
    assert reporter.runner.tree_hashes(root) == before


def test_formal_render_is_not_labeled_smoke(completed):
    _, _, protocol, result, audit, _ = completed
    result = deepcopy(result)
    result["smoke_not_effect_evidence"] = False
    text = reporter.render(protocol, result, audit)
    assert "Smoke 接口验收" not in text and "不是完整 MBPP 复现" in text


def test_unknown_reference_counts_are_explicit(completed):
    _, _, protocol, result, audit, _ = completed
    result = deepcopy(result)
    result["reference_summary"]["final"] = {"total": 2, "valid": 1, "unknown": 1}
    text = reporter.render(protocol, result, audit)
    assert "最终审计参考校准：1/2 可用，1 unknown" in text


def test_cli_reports_only_new_file_metadata(completed, monkeypatch, capsys):
    repo, root, _, _, _, _ = completed
    called = []

    def report(output, target):
        called.append((output, target))
        return {"report": str(repo / "docs/report.md"), "model_api_calls": 0}

    monkeypatch.setattr(reporter, "report", report)
    assert reporter.main(["--output", str(root)]) == 0
    assert called == [(root, None)]
    assert json.loads(capsys.readouterr().out)["model_api_calls"] == 0
