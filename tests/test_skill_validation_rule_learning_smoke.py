"""Offline fixture smoke: reproducible plumbing, no natural learning claim."""
import json

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation import rule_learning_smoke as smoke
from skillopt.skill_validation.rule_skill import RuleSkill, render_skill


def _read(root, name):
    return json.loads((root / name).read_text())


def test_complete_cold_fixture_chain_and_explicit_non_results(tmp_path):
    summary = smoke.run(tmp_path / "smoke")
    root = tmp_path / "smoke"
    assert verify(summary) == summary
    assert summary["provenance"] == "fixture_no_research_effect_not_natural"
    assert summary["api_calls"] == summary["research_calls"] == summary["real_executions"] == 0
    assert summary["hidden_audit_reads"] == 0 and summary["scripted_receipt_calls"] == 3
    assert not summary["method_effect_evaluated"] and not summary["deployment_authorized"]
    assert summary["cold_rule_count"] == 0 and summary["candidate_rule_count"] == 1
    assert summary["candidate_status"] == "candidate"
    assert summary["near_miss_disabled"] and summary["deletion_returns_empty"]
    seed = _read(root, "seed.json")
    assert seed["skill_text"] == "" and seed["structured_skill"]["rules"] == []
    candidate = _read(root, "candidate.json")
    assert candidate["semantic_support_verified"] is False
    assert candidate["feedback_use"] == "shadow_diagnostic_only"
    rule = RuleSkill.from_dict(candidate["candidate"]).rules[0]
    assert rule.scope.required_obligation_kinds == ("input_preservation",)
    rendered = _read(root, "rendering.json")
    assert rendered["applicable"]["selected_rule_ids"] == ["preserve_input"]
    assert rendered["near_miss"]["disabled_rule_ids"] == ["preserve_input"]
    assert rendered["near_miss"]["text"] == "" and not rendered["semantic_applicability_verified"]
    for name, expected in summary["artifacts"].items():
        assert verify(_read(root, name))["record_hash"] == expected


def test_same_public_feedback_no_hidden_host_projection_and_unknown_retained(tmp_path):
    smoke.run(tmp_path)
    bundle = _read(tmp_path, "feedback.json")
    assert bundle["coverage"]["paired_repeat_count"] == 2
    assert bundle["coverage"]["stratum_counts"]["loss"] == 1
    assert bundle["coverage"]["stratum_counts"]["unknown"] == 1
    assert bundle["coverage"]["role_counts"]["current"]["unknown"] == 1
    requests = _read(tmp_path, "update_requests.json")["requests"]
    assert requests["rule_patch"]["feedback_view_hash"] == requests["whole_text"]["feedback_view_hash"]
    views = _read(tmp_path, "model_views.json")["views"]
    left, right = (json.loads(views[mode]["user"]) for mode in ("rule_patch", "whole_text"))
    assert left["feedback"] == right["feedback"]
    for view in (left, right):
        assert not {"execution_records", "execution_identity", "source_attestation", "host_audit"} & set(view)
        assert "source_bindings" not in json.dumps(view)
    proposal = json.loads(_read(tmp_path, "proposal.json")["scripted_response"])
    evidence_id = proposal["edits"][0]["evidence_ids"][0]
    ref = next(item for item in left["evidence_catalog"] if item["id"] == evidence_id)
    detail = left["feedback"]["paired_development"][ref["location"][1]]
    assert detail["roles"]["current"]["status"] == "fail"


def test_no_update_and_delete_to_empty_are_structural_not_extra_learning(tmp_path):
    smoke.run(tmp_path)
    edges = _read(tmp_path, "edge_cases.json")
    assert edges["no_update"]["status"] == "no_update"
    assert edges["deletion_is_not_a_second_learning_round"]
    assert render_skill(RuleSkill.from_dict(edges["deletion_format_roundtrip"]["skill"])) == ""
    assert not edges["deletion_format_roundtrip"]["deployment_authorized"]
    whole = _read(tmp_path, "whole_text_candidate.json")
    assert whole["status"] == "candidate" and whole["candidate"] is None
    assert not whole["semantic_support_verified"] and not whole["deployment_authorized"]


def test_replay_is_identical_and_preserves_all_existing_bytes(tmp_path):
    first = smoke.run(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    second = smoke.run(tmp_path)
    assert first == second
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_conflicting_output_is_not_overwritten_or_partially_appended(tmp_path):
    target = tmp_path / "summary.json"
    target.write_text('{"historical":true}\n')
    before = target.read_bytes()
    with pytest.raises(ValueError, match="Immutable smoke artifact"):
        smoke.run(tmp_path)
    assert target.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {"summary.json"}


def test_unrelated_old_output_directory_is_not_reused(tmp_path):
    (tmp_path / "original-log.txt").write_text("old log must survive")
    with pytest.raises(ValueError, match="unrelated historical files"):
        smoke.run(tmp_path)
    assert list(tmp_path.iterdir()) == [tmp_path / "original-log.txt"]
    assert (tmp_path / "original-log.txt").read_text() == "old log must survive"


def test_symlink_destination_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        smoke.run(link)
    assert not list(real.iterdir())


def test_smoke_does_not_construct_live_api_client(tmp_path, monkeypatch):
    from skillopt.validator_pilot.api import CachedAPI

    def forbidden(*args, **kwargs):
        raise AssertionError("An offline fixture must not create a live client")

    monkeypatch.setattr(CachedAPI, "__init__", forbidden)
    assert smoke.run(tmp_path)["api_calls"] == 0


def test_cli_writes_same_summary(tmp_path, capsys):
    smoke.main(["--output", str(tmp_path)])
    assert json.loads(capsys.readouterr().out) == _read(tmp_path, "summary.json")
