"""Synthetic completed score tables and immutable report publication tests."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import report_coevolution_v9 as r
from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v9 import analysis
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def completed(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    root = repo / "outputs/coevolution_v9/fixture"
    source = repo / "docs/frozen-protocol.md"
    source.parent.mkdir(parents=True)
    source.write_text("Frozen fixture source.")
    expected = {"fixture_question": {"cluster_id": "fixture_cluster"}}
    rows = [{"task_id": "fixture_question", "cluster_id": "fixture_cluster", "history": 0, "policy": policy,
             "api_ok": policy != "skillopt", "em": None if policy == "skillopt" else 1,
             "f1": None if policy == "skillopt" else 1, "skill_hash": digest(policy), "request_hash": digest([policy, 0])}
            for policy in analysis.POLICIES]
    summary = analysis.summarize_final(rows, expected_tasks=expected, histories=[0],
                                       bootstrap_samples=100, permutation_samples=100)
    gate_rows = [{**row, "history": 0} for row in rows if row["policy"] in ("no_skill", "initial", "ours")]
    gate = analysis.local_gate([gate_rows[1]], [gate_rows[2]], [gate_rows[0]], expected_tasks=expected)
    gate["standard_accept"] = True  # Structural fixture, not efficacy evidence.
    protocol = seal({"model": "glm-5.3", "design": {"histories": 1, "train": 4, "confirmation": 8, "final": 1},
                     "source_hashes": {str(source.relative_to(repo)): hashlib.sha256(source.read_bytes()).hexdigest()}})
    ledger = {"cached_logical_calls": 5, "max_logical_calls": 56, "http_attempts_from_cached_records": 7,
              "successful_calls": 4, "terminal_errors": 1, "prompt_tokens": 10, "completion_tokens": 20,
              "total_tokens": 30, "missing_usage_calls": 1}
    result = seal({"complete": True, "protocol_hash": protocol["record_hash"], "summary": summary, "ledger": ledger,
                   "smoke_not_effect_evidence": True, "histories": [{"history": 0, "candidate_changed": True, "gate": gate}]})
    put(root / "protocol.json", protocol)
    put(root / "results.json", result)
    audited = seal({"complete_integrity_audit": True, "run_files_unchanged": True, "model_api_calls": 0,
                    "result_hash": result["record_hash"], "summary": summary, "ledger": ledger, "verified_run_files": 2})
    calls = []

    def audit(output, actual_repo, *, require_complete):
        assert output == root and actual_repo == repo and require_complete is True
        calls.append(1)
        return audited

    monkeypatch.setattr(r.auditor, "audit", audit)
    return repo, root, protocol, result, audited, calls


def test_default_report_requires_audit_and_is_idempotent(completed):
    repo, root, _, result, _, calls = completed
    before = r.auditor._tree_hashes(root)
    first = r.report(root, repo=repo)
    assert first["created"] is True
    report = Path(first["report"])
    assert report == repo / "docs/coevolution-v9-fixture-report.md"
    second = r.report(root, repo=repo)
    assert second["created"] is False
    assert first["report_sha256"] == second["report_sha256"]
    assert first["result_hash"] == result["record_hash"]
    assert r.auditor._tree_hashes(root) == before and calls == [1, 1]
    text = report.read_text()
    assert "H=1" in text and "T=4" in text and "C=8" in text and "F=1" in text
    assert "Smoke 接口验收，不构成效果证据" in text
    assert "逻辑调用 5" in text and "HTTP attempts 7" in text
    assert "Holm" in text and "初始 Skill 非空" in text
    assert "全部来自 unknown" in text
    assert "fixture_question" not in text


def test_explicit_new_report_outside_repo_is_allowed(completed, tmp_path):
    repo, root, _, _, _, _ = completed
    target = tmp_path / "requested/report.md"
    result = r.report(root, target, repo)
    assert result["created"] and target.is_file()


@pytest.mark.parametrize("target", ["skillopt/report.md", "outputs/report.md", "data/report.md",
                                   "outputs/coevolution_v9/fixture/report.md", ".env", "docs/report.json",
                                   "docs/frozen-protocol.md"])
def test_source_run_and_nonreport_destinations_rejected(completed, target):
    repo, root, _, _, _, _ = completed
    before = r.auditor._tree_hashes(root)
    with pytest.raises(ValueError):
        r.report(root, repo / target, repo)
    assert r.auditor._tree_hashes(root) == before


def test_different_existing_report_is_preserved(completed):
    repo, root, _, _, _, _ = completed
    target = repo / "docs/existing.md"
    target.write_text("User-owned old report")
    with pytest.raises(ValueError, match="Existing report differs"):
        r.report(root, target, repo)
    assert target.read_text() == "User-owned old report"


def test_symlink_destination_cannot_overwrite_target(completed, tmp_path):
    repo, root, _, _, _, _ = completed
    outside = tmp_path / "private.md"
    outside.write_text("Private content")
    target = repo / "docs/link.md"
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        r.report(root, target, repo)
    assert outside.read_text() == "Private content"


def test_incomplete_audit_rejects_before_any_report_write(completed, monkeypatch):
    repo, root, _, _, _, _ = completed
    target = repo / "docs/no-report.md"

    def unfinished(*args, **kw):
        raise ValueError("A completed result is required")

    monkeypatch.setattr(r.auditor, "audit", unfinished)
    with pytest.raises(ValueError, match="completed"):
        r.report(root, target, repo)
    assert not target.exists()


@pytest.mark.parametrize("change", ["not_complete", "changed_result", "changed_source", "new_run_file", "audit_calls_api"])
def test_publication_rechecks_all_completion_bindings_and_hashes(completed, monkeypatch, change):
    repo, root, protocol, result, audited, _ = completed
    target = repo / "docs/must-not-write.md"
    bad_audit = deepcopy(audited)

    def changed(*args, **kw):
        if change == "not_complete":
            bad_audit["complete_integrity_audit"] = False
        elif change == "audit_calls_api":
            bad_audit["model_api_calls"] = 1
        elif change == "changed_result":
            put(root / "results.json", seal({**{k: v for k, v in result.items() if k != "record_hash"}, "extra": True}))
        elif change == "changed_source":
            (repo / next(iter(protocol["source_hashes"]))).write_text("Changed after audit")
        elif change == "new_run_file":
            put(root / "new_unexpected.json", {})
        return seal({k: v for k, v in bad_audit.items() if k != "record_hash"})

    monkeypatch.setattr(r.auditor, "audit", changed)
    with pytest.raises(ValueError):
        r.report(root, target, repo)
    assert not target.exists()


def test_jointly_available_ties_get_explicit_nonsemantic_warning(completed):
    _, _, protocol, result, audited, _ = completed
    result = deepcopy(result)
    pair = result["summary"]["comparisons"]["ours_vs_skillopt"]
    pair["jointly_available_positions"] = 1
    pair["n_question_history_positions"] = 2
    pair["metrics"]["em"]["jointly_available_diagnostic"] = {"n": 1, "wins": 0, "losses": 0}
    text = r.render(protocol, result, audited)
    assert "双方可评子集上没有 EM 胜负" in text
    assert "不是 Skill 语义收益或负迁移证据" in text


def test_source_report_does_not_label_main_run_as_smoke(completed):
    _, _, protocol, result, audited, _ = completed
    result = deepcopy(result)
    result["smoke_not_effect_evidence"] = False
    text = r.render(protocol, result, audited)
    assert "Smoke 接口验收" not in text
    assert "不是跨领域泛化实验" in text


def test_cli_passes_requested_output_and_report_without_api(completed, monkeypatch, capsys):
    _, root, _, _, _, _ = completed
    monkeypatch.setattr(r, "report", lambda output, report_path: {"output": str(output), "report": str(report_path)})
    assert r.main(["--output", str(root), "--report", "docs/chosen.md"]) == 0
    assert json.loads(capsys.readouterr().out)["report"] == "docs/chosen.md"
