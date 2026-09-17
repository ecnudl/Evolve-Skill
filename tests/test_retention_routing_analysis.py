"""No model calls or local benchmark artifacts are needed for paired analysis tests."""

import json
import math

import pytest

from scripts.analyze_retention_routing import _population, freeze_plan, paired_comparison


def row(identifier, base, full, **kwargs):
    return {"id": identifier, "base": base, "full": full, "base_ok": True, "full_ok": True,
            "origin": "source", "domain": "searchqa", "group": "source", **kwargs}


def test_paired_sign_direction_and_same_task_resampling():
    rows = [row("win", 0, 1), row("loss", 1, 0), row("tie", 1, 1)]
    result = paired_comparison(rows, ["win"], ["loss"], bootstrap_n=100)
    assert result["delta_em_left_minus_right"] == pytest.approx(2 / 3)
    assert result["left_better_ids"] == ["win", "loss"]
    assert result["left_worse_ids"] == []
    assert result["n_independent_common_tasks"] == 3
    assert result["paired_bootstrap95"][0] >= 0


def test_api_errors_are_not_model_mistakes_or_different_denominators():
    rows = [row("ok", 0, 1), row("failed", 1, None, full_ok=False)]
    result = paired_comparison(rows, ["ok", "failed"], [], bootstrap_n=10)
    assert result["n_expected"] == 2
    assert result["n_independent_common_tasks"] == 1
    assert result["excluded_api_ids"] == ["failed"]
    assert result["delta_em_left_minus_right"] == 1


def test_identical_masks_have_zero_replay_difference_not_safety_proof():
    result = paired_comparison([row("x", 0, 1)], [], [], bootstrap_n=10)
    assert result["identical_observed_policy_masks"] is True
    assert result["paired_bootstrap95"] == [0, 0]


def test_empty_group_is_explicitly_undefined():
    result = paired_comparison([], [], [], bootstrap_n=10)
    assert result["left_em"] is None
    assert result["delta_em_left_minus_right"] is None
    assert result["paired_bootstrap95"] == [None, None]
    assert result["identical_observed_policy_masks"] is None


@pytest.mark.parametrize("bad", [math.nan, math.inf, True, "1", .5])
def test_invalid_scores_cannot_become_evidence(bad):
    with pytest.raises(ValueError, match="finite binary"):
        paired_comparison([row("x", bad, 1)], [], [], bootstrap_n=10)


def test_duplicate_task_observations_rejected():
    with pytest.raises(ValueError, match="independent"):
        paired_comparison([row("x", 0, 1), row("x", 0, 1)], [], [])


def test_strata_do_not_mix_source_qa_and_source_appearance_controls():
    rows = [row("s", 1, 1), row("n", 1, 0, origin="control", group="near_miss"),
            row("p", 0, 1, origin="control", group="positive", domain="coding"),
            row("u", 1, 1, origin="control", group="unrelated")]
    assert [r["id"] for r in _population(rows, "source")] == ["s"]
    assert [r["id"] for r in _population(rows, "source_appearance_near_miss")] == ["n"]
    assert [r["id"] for r in _population(rows, "cross_domain_positive")] == ["p"]
    assert _population(rows, "cross_domain_near_miss") == []
    assert [r["id"] for r in _population(rows, "unrelated")] == ["u"]


def _plan_fixture(tmp_path):
    root = tmp_path / "routing"
    source = tmp_path / "source"
    root.mkdir()
    source.mkdir()
    (root / "routing_protocol.json").write_text(json.dumps({
        "source_protocol_sha256": "test-only", "settings": {"source_dir": str(source)}
    }))
    return root, source


def test_analysis_plan_is_immutable_and_does_not_open_heldout_payloads(tmp_path):
    root, _ = _plan_fixture(tmp_path)
    plan = freeze_plan(root)
    assert freeze_plan(root) == plan
    assert not (root / "datasets").exists()
    protocol = root / "routing_protocol.json"
    protocol.write_text(protocol.read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        freeze_plan(root)


@pytest.mark.parametrize("location", ["source", "routing"])
def test_no_backdated_analysis_plan_after_holdout_access(tmp_path, location):
    root, source = _plan_fixture(tmp_path)
    path = source / "datasets/holdout.json" if location == "source" else root / "routes/holdout.json"
    path.parent.mkdir(parents=True)
    path.write_text("payload deliberately not parsed")
    with pytest.raises(ValueError, match="holdout"):
        freeze_plan(root)


def test_analysis_uses_validated_route_seal_and_current_matched_schema(tmp_path, monkeypatch):
    from scripts import analyze_retention_routing as analysis
    from skillopt.scope_evolution_v2 import retention_routing as routing

    root, source = _plan_fixture(tmp_path)
    (root / "routing_protocol.json").write_text(json.dumps({
        "source_protocol_sha256": "test-only",
        "settings": {"source_dir": str(source), "execution_mode": "injected_test_double"}
    }))
    freeze_plan(root)
    checks = []
    seal = {"routes": [{"id": "x"}], "deployment": {"base": [], "unconditional": ["x"], "domain": [], "mechanism": ["x"]},
            "matched_coverage_diagnostic": [{"mechanism_score_threshold": .5, "k": 1, "n": 1,
                "enabled": {"mechanism_topk": ["x"], "domain_topk": ["x"], "hash_random_topk": ["x"]}}]}
    monkeypatch.setattr(routing, "_validate", lambda *args: None)
    monkeypatch.setattr(routing, "_verify_source_freeze", lambda *args: None)
    monkeypatch.setattr(routing, "_verify_freeze", lambda *args: None)

    def load(*args):
        checks.append("validated_route_seal")
        return seal

    def paired(*args):
        assert checks == ["validated_route_seal"]
        return [row("x", 0, 1)]

    monkeypatch.setattr(routing, "_load_route", load)
    monkeypatch.setattr(routing, "_paired_rows", paired)
    monkeypatch.setattr(analysis, "paired_comparison", lambda *args: paired_comparison(*args, bootstrap_n=10))
    result = analysis.analyze(root)
    assert result["execution_mode"] == "injected_test_double"
    assert result["matched_coverage_diagnostic"][0]["mechanism_score_threshold"] == .5
    assert result["deployment"]["source"]["mechanism_minus_domain"]["delta_em_left_minus_right"] == 1
