"""Offline staged-routing tests; no real source payload or API is accessed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skillopt.scope_evolution_v2 import retention_routing as routing
from skillopt.scope_evolution_v2 import source_data

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_run(tmp_path, monkeypatch):
    source, root = tmp_path / "source", tmp_path / "routing"
    monkeypatch.setattr(routing, "_deps", lambda repo: source_data)
    full = "A fixed full Skill for relational clue answering."
    full_sha = hashlib.sha256(full.encode()).hexdigest()
    monkeypatch.setattr(routing, "HISTORICAL_BEST_SHA256", full_sha)
    tasks = [{"id": f"source-{i}", "question": f"Who has role {i}?", "context": f"The answer for role {i} is alpha.", "answers": ["alpha"]} for i in range(3)]
    held = [{"id": f"held-{i}", "question": f"Who has new role {i}?", "context": "The answer is alpha.", "answers": ["alpha"]} for i in range(4)]
    manifest = {"splits": {"calibration": [{"id": t["id"]} for t in tasks], "holdout": [{"id": t["id"]} for t in held]}}
    arms = {}
    for name, text in [("base", "initial"), ("full", full)]:
        relative = f"skills/{name}.md"
        source_data.write_immutable_text(source / relative, text)
        arms[name] = {"snapshot": relative, "sha256": source_data.file_hash(source / relative)}
    protocol = {"manifest_hash": source_data.digest(manifest), "arms": arms, "code_hashes": {},
                "model": "gpt-5.5", "required_provider_host": "free-router.opendatalab.com",
                "effective_max_tokens_cap": 8000, "requested_max_completion_tokens": 16384}
    source_data.write_immutable_json(source / "source_manifest.json", manifest)
    source_data.write_immutable_json(source / "source_protocol.json", protocol)
    source_data.write_immutable_json(source / "datasets/calibration.json", tasks)
    materialized = []
    def materialize(manifest, split):
        materialized.append(split)
        assert split == "holdout"
        return held
    monkeypatch.setattr(source_data, "materialize_source_split", materialize)
    settings = {"workers": 2, "n_per_group": 2, "execution_mode": "injected_test_double"}
    return {"source": source, "root": root, "tasks": tasks, "held": held, "source_protocol": protocol,
            "materialized": materialized, "settings": settings}


class Router:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def call(self, system, user, **kwargs):
        self.calls.append((system, user, kwargs))
        assert "secret_gold" not in user
        assert '"domain":' not in user and '"mechanism":' not in user
        return {"ok": not self.fail, "response": json.dumps({"domain_score": .8, "mechanism_score": .9, "reason": "input-only"}),
                "request_hash": f"route-{len(self.calls)}", "usage": {}}


class Target:
    def __init__(self, root, split):
        self.calls = []
        tasks = source_data.read_json(root / f"datasets/controls_{split}.json")
        self.answers = {t["id"]: t["gold"] for t in tasks}

    def call(self, system, user, *, key, arm, split):
        self.calls.append({"system": system, "user": user, "key": key, "arm": arm, "split": split})
        return {"ok": True, "response": f"<answer>{self.answers[key]}</answer>",
                "request_hash": f"target-{len(self.calls)}", "usage": {}}


def phase(fixture, name, **kwargs):
    return routing.run_phase(REPO, fixture["root"], fixture["source"], name, **fixture["settings"], **kwargs)


def source_outcomes(fixture, split="calibration"):
    source = fixture["source"]
    tasks = fixture["tasks"] if split == "calibration" else fixture["held"]
    for arm in ["base", "full"]:
        rows = []
        for index, task in enumerate(tasks):
            correct = arm == "full" or index != 0
            rows.append({"id": task["id"], "arm": arm, "split": split, "agent_ok": True,
                         "response": "<answer>alpha</answer>" if correct else "<answer>wrong</answer>",
                         "hard": int(correct), "skill_sha256": fixture["source_protocol"]["arms"][arm]["sha256"],
                         "request_hash": f"{split}-{arm}-{index}"})
        source_data.write_immutable_text(source / f"searchqa_rollouts/{split}/{arm}/results.jsonl",
                                         "".join(json.dumps(row) + "\n" for row in rows))
    if split == "calibration":
        source_data.write_immutable_json(source / "calibration_summary.json", {"execution_mode": "injected_test_double"})
        relatives = [f"searchqa_rollouts/calibration/{arm}/results.jsonl" for arm in ["base", "full"]] + ["calibration_summary.json"]
        source_data.write_immutable_json(source / "frozen_source_protocol.json", {
            "protocol_hash": source_data.digest(fixture["source_protocol"]), "code_hashes": {},
            "arms": fixture["source_protocol"]["arms"], "execution_mode": "injected_test_double",
            "calibration_artifact_hashes": {name: source_data.file_hash(source / name) for name in relatives},
        })


def test_prepare_and_routing_do_not_materialize_holdout_or_access_source_results(fixture_run):
    prepared = phase(fixture_run, "prepare")
    assert not prepared["holdout_materialized"]
    assert fixture_run["materialized"] == []
    router = Router()
    seal = phase(fixture_run, "route-calibration", router_api=router)
    assert len(seal["routes"]) == 3 + 6
    assert len(router.calls) == 9
    assert fixture_run["materialized"] == []
    assert not (fixture_run["root"] / "datasets/source_holdout.json").exists()
    assert (fixture_run["root"] / "routes/calibration_seal.json").exists()
    assert all(len(set(item["enabled"][method])) == item["k"] for item in seal["matched_coverage_diagnostic"] for method in item["enabled"])


def test_route_payload_matches_target_visibility_and_excludes_metadata():
    task = {"question": "Which role?", "context": "[DOC]" + "a" * 4000 + "[DOC]" + "target_cannot_see" * 1000,
            "domain": "secret_domain", "gold": "secret_gold", "group": "secret_group", "id": "secret_id"}
    text = routing.route_payload(task)
    assert "a" * 100 in text
    assert "target_cannot_see" not in text
    assert all(value not in text for value in ["secret_domain", "secret_gold", "secret_group", "secret_id"])


def test_initial_fail_fast_never_fans_out(fixture_run):
    bad = Router(fail=True)
    with pytest.raises(RuntimeError, match="initial real request failed"):
        phase(fixture_run, "route-calibration", router_api=bad)
    assert len(bad.calls) == 1
    assert not (fixture_run["root"] / "routes/calibration.json").exists()


def test_consecutive_fail_fast_stops_before_entire_batch():
    called = []
    def one(number):
        called.append(number)
        return {"agent_ok": number == 0}
    with pytest.raises(RuntimeError, match="three consecutive"):
        routing._fail_fast_map(list(range(30)), one, workers=1, success_field="agent_ok", label="unit")
    assert len(called) <= 5


def test_target_before_routes_is_forbidden_including_single_call_cache(fixture_run):
    phase(fixture_run, "prepare")
    source_data.write_immutable_json(fixture_run["source"] / "calls/one.json", {
        "request_hash": "hash", "request": {"split": "calibration"}, "ok": True, "response": "DO_NOT_READ_OUTCOME",
    })
    with pytest.raises(ValueError, match="after target outcomes"):
        phase(fixture_run, "route-calibration", router_api=Router())
    assert routing._cached_request_split(fixture_run["source"] / "calls/one.json") == "calibration"


def test_control_targets_require_sealed_masks(fixture_run):
    phase(fixture_run, "prepare")
    target = Target(fixture_run["root"], "calibration")
    with pytest.raises(ValueError, match="Seal input-only"):
        phase(fixture_run, "control-calibration", target_api=target)
    assert not target.calls


def test_resume_reuses_masks_without_reading_or_requerying_outcomes(fixture_run):
    router = Router()
    first = phase(fixture_run, "route-calibration", router_api=router)
    source_outcomes(fixture_run)
    before = len(router.calls)
    assert phase(fixture_run, "route-calibration", router_api=router) == first
    assert len(router.calls) == before


def test_complete_offline_flow_preserves_same_skill_and_shared_draws(fixture_run):
    phase(fixture_run, "route-calibration", router_api=Router())
    target = Target(fixture_run["root"], "calibration")
    phase(fixture_run, "control-calibration", target_api=target)
    assert len(target.calls) == 12
    for arm in ["base", "full"]:
        assert len({r["system"] for r in target.calls if r["arm"] == arm}) == 1
    source_outcomes(fixture_run)
    frozen = phase(fixture_run, "freeze")
    assert not frozen["commit_authorized"]
    assert fixture_run["materialized"] == []
    phase(fixture_run, "route-test", router_api=Router())
    assert fixture_run["materialized"] == ["holdout"]
    held_target = Target(fixture_run["root"], "holdout")
    phase(fixture_run, "control-test", target_api=held_target)
    source_outcomes(fixture_run, "holdout")
    report = phase(fixture_run, "report")
    assert report["execution_mode"] == "injected_test_double"
    assert not report["commit_authorized"]
    for split in ["calibration", "holdout"]:
        source = report["splits"][split]["deployment"]["mechanism"]["source"]
        assert source["coverage"] == 1
        assert source["net_gain_retention"] == 1
        assert source["wins_retained"] == 1
        assert source["gain_retention_target_met"]


def test_mask_tampering_detected_before_target_calls(fixture_run):
    phase(fixture_run, "route-calibration", router_api=Router())
    path = fixture_run["root"] / "routes/calibration.json"
    value = source_data.read_json(path)
    value["deployment"]["mechanism"] = []
    path.write_text(json.dumps(value))
    target = Target(fixture_run["root"], "calibration")
    with pytest.raises(ValueError, match="Frozen route artifact"):
        phase(fixture_run, "control-calibration", target_api=target)
    assert not target.calls


def test_freeze_requires_complete_external_source_freeze(fixture_run):
    phase(fixture_run, "route-calibration", router_api=Router())
    phase(fixture_run, "control-calibration", target_api=Target(fixture_run["root"], "calibration"))
    with pytest.raises(ValueError, match="Complete routing"):
        phase(fixture_run, "freeze")
    with pytest.raises(FileNotFoundError):
        phase(fixture_run, "route-test", router_api=Router())
    assert fixture_run["materialized"] == []


def test_mock_real_mode_cannot_be_mixed(fixture_run):
    with pytest.raises(ValueError, match="Mock API requires"):
        routing.run_phase(REPO, fixture_run["root"], fixture_run["source"], "route-calibration", router_api=Router())
    for name in ["route-calibration", "control-calibration"]:
        with pytest.raises(ValueError, match="no real API fallback"):
            phase(fixture_run, name)


def test_retention_accounting_does_not_reward_zero_coverage_or_clip_negative_gain():
    rows = [{"id": str(i), "base": b, "full": f, "base_ok": True, "full_ok": True}
            for i, (b, f) in enumerate([(0, 1), (0, 1), (1, 0), (1, 1)])]
    base = routing.policy_summary(rows, [])
    assert base["coverage"] == 0 and base["net_gain_retention"] == 0
    harmful = routing.policy_summary(rows, ["2"])
    assert harmful["net_gain_retention"] == -1
    assert harmful["losses_used"] == 1 and harmful["wins_retained"] == 0
    assert routing.policy_summary(rows[2:], ["2"])["net_gain_retention"] is None
    assert routing.policy_summary([], [])["net_gain_retention"] is None


def test_api_failures_excluded_from_shared_denominator_not_scored_zero():
    rows = [{"id": "ok", "base": 0, "full": 1, "base_ok": True, "full_ok": True},
            {"id": "failed", "base": 1, "full": None, "base_ok": True, "full_ok": False}]
    result = routing.policy_summary(rows, ["ok", "failed"])
    assert result["n_common_api_success"] == 1
    assert result["full_api_errors"] == 1 and result["excluded_api_ids"] == ["failed"]
    assert result["policy_correct"] == 1


@pytest.mark.parametrize("score", [True, -1, 1.1, float("nan"), float("inf")])
def test_router_scores_must_be_finite_probabilities(score):
    with pytest.raises(ValueError):
        routing._parse_route(json.dumps({"domain_score": score, "mechanism_score": .5, "reason": "x"}))
