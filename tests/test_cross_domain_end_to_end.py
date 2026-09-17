"""Small offline orchestration exercises with synthetic model responses only.

No API transport or credentials are configured. The real dataset construction,
partitioning, paired policy replay, validation gate, freezing, and report code run.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.cross_domain import experiment
from skillopt.cross_domain.runtime import read_json, write_json


@pytest.fixture
def harness(tmp_path, monkeypatch):
    root = tmp_path / "offline-experiment"
    repo = Path(__file__).resolve().parents[1]
    api = SimpleNamespace(root=root)
    protocol = {
        "protocol_version": "offline-runner-test", "model": "offline-model", "seed": 13,
        "validation_per_cell": 4, "test_per_cell": 1, "test_repeats": 2,
        "router_threshold": 0.75, "shuffled_seed": 1701,
        "gate": {"source_domains": ["coding"], "min_group_n": 16},
    }
    skill = {
        "id": "constraint_v1", "mechanism": "constraint_preservation", "source_domain": "coding",
        "content": "Respect the explicitly stated invariant.", "parent_content": "",
        "accepted_local_point_gate": True,
        "scope": {"description": "A procedural constraint.", "apply_if": ["An invariant is specified"], "avoid_if": []},
    }
    candidates = {"selected": [skill], "pool": [skill]}
    write_json(root / "candidates.json", candidates)
    state = {"failure": None, "events": [], "assert_frozen_masks": True}

    def propose(_api, selected):
        state["events"].append("scope")
        return selected

    def router(_api, tasks, skills, label):
        state["events"].append("route:" + label)
        # This is a deterministic transport stub, not an evaluated router.
        return {t.id: {"ok": True, "domain": t.domain,
                       "scores": {s["id"]: 0.9 for s in skills}, "request_hash": "offline"}
                for t in tasks}

    def rollout(_api, tasks, content, label, repeat=0):
        is_test = label.startswith("test_")
        if is_test and state["assert_frozen_masks"]:
            assert (root / "frozen_policies.json").exists()
            assert (root / "test_masks_before_outcomes.json").exists()
            masks = read_json(root / "test_masks_before_outcomes.json")
            assert set(masks[skill["id"]]["no_skill"]) == {t.id for t in tasks}
        state["events"].append("rollout:" + label)
        rows = []
        for task in tasks:
            fail = bool(is_test and content and (
                state["failure"] == "all"
                or state["failure"] == "held_out" and task.domain == "rule_reasoning"
                or state["failure"] == "one_repeat" and repeat == 1 and task.id == tasks[0].id
            ))
            rows.append({"id": task.id, "agent_ok": not fail,
                         "hard": None if fail else int(bool(content) or task.group != "positive")})
        return rows

    monkeypatch.setattr(experiment, "propose_mechanism_scopes", propose)
    monkeypatch.setattr(experiment, "route_inputs", router)
    monkeypatch.setattr(experiment, "rollout", rollout)
    return SimpleNamespace(api=api, protocol=protocol, repo=repo, root=root,
                           state=state, sid=skill["id"], candidates=candidates)


def test_validate_freeze_test_and_report_without_api(harness):
    h = harness
    frozen = experiment.validate(h.api, h.protocol, h.repo)
    assert frozen["test_accessed"] is False
    assert set(frozen["fit_ids"]).isdisjoint(frozen["confirmation_ids"])
    assert not (h.root / "datasets" / "test.json").exists()
    assert h.state["events"].index("route:validation") < h.state["events"].index("rollout:validation_base")
    assert set(frozen["tracks"][h.sid]["methods"]) == {"mechanism", "domain", "shuffled"}
    assert all(m["mode"] == "fallback" for m in frozen["tracks"][h.sid]["methods"].values())
    frozen_bytes = (h.root / "frozen_policies.json").read_bytes()

    summary = experiment.test(h.api, h.protocol, h.repo)
    assert h.state["events"].index("route:test") < h.state["events"].index("rollout:test_r0_base")
    assert (h.root / "frozen_policies.json").read_bytes() == frozen_bytes
    assert summary["test_tasks"] == 15
    assert summary["public_benchmark"] is False
    assert summary["held_out_domain"] == "rule_reasoning"
    assert summary["tracks"][h.sid]["no_skill"]["n_unique_tasks"] == 15
    assert summary["tracks"][h.sid]["safe_mechanism"]["coverage"] == 0.0
    assert summary["tracks"][h.sid]["safe_mechanism"]["delta_em"] == 0.0
    assert read_json(h.root / "summary.json") == summary
    assert "离线策略回放" in (h.root / "report.md").read_text(encoding="utf-8")
    json.dumps(frozen, allow_nan=False)
    json.dumps(summary, allow_nan=False)


def test_entire_missing_subdomain_is_unknown_and_all_policies_share_denominators(harness):
    h = harness
    experiment.validate(h.api, h.protocol, h.repo)
    h.state["failure"] = "held_out"
    summary = experiment.test(h.api, h.protocol, h.repo)
    policies = summary["tracks"][h.sid]
    assert {r["n_unique_tasks"] for r in policies.values()} == {10}
    assert {r["excluded_tasks_missing_any_repeat"] for r in policies.values()} == {5}
    for policy in policies.values():
        held_out = policy["domains"]["rule_reasoning"]
        assert held_out["n_unique_tasks"] == 0
        assert held_out["em"] is None
        assert held_out["delta_em"] is None
        assert held_out["delta_bootstrap95"] == [None, None]
        assert held_out["excluded_tasks_missing_any_repeat"] == 5
    # Even no-skill/fallback excludes these candidate API failures for a common
    # comparison set, although its base responses themselves succeeded.
    assert policies["no_skill"]["n_unique_tasks"] == policies["unconditional"]["n_unique_tasks"]
    json.dumps(summary, allow_nan=False)
    assert (h.root / "report.md").exists()


def test_one_failed_repeat_excludes_the_original_task_for_every_policy(harness):
    h = harness
    experiment.validate(h.api, h.protocol, h.repo)
    h.state["failure"] = "one_repeat"
    summary = experiment.test(h.api, h.protocol, h.repo)
    assert {r["n_unique_tasks"] for r in summary["tracks"][h.sid].values()} == {14}
    assert {r["excluded_tasks_missing_any_repeat"] for r in summary["tracks"][h.sid].values()} == {1}
    assert {r["n_generation_repeats"] for r in summary["tracks"][h.sid].values()} == {2}


def test_all_domains_missing_still_write_null_summary_and_report(harness):
    h = harness
    experiment.validate(h.api, h.protocol, h.repo)
    h.state["failure"] = "all"
    summary = experiment.test(h.api, h.protocol, h.repo)
    for metrics in summary["tracks"][h.sid].values():
        assert metrics["n_unique_tasks"] == 0
        assert metrics["excluded_tasks_missing_any_repeat"] == 15
        assert metrics["em"] is None
        assert metrics["delta_em"] is None
        assert metrics["coverage"] is None
        assert all(d["em"] is None for d in metrics["domains"].values())
    json.dumps(summary, allow_nan=False)
    assert read_json(h.root / "summary.json") == summary
    report = (h.root / "report.md").read_text(encoding="utf-8")
    assert "no_skill" in report and "safe_mechanism" in report
    assert "nan" not in report.lower()


@pytest.mark.parametrize("changed", ["code", "candidate", "protocol"])
def test_mismatched_frozen_inputs_are_rejected_before_test_data_or_rollouts(harness, monkeypatch, changed):
    h = harness
    experiment.validate(h.api, h.protocol, h.repo)
    if changed == "code":
        monkeypatch.setattr(experiment, "_code_hashes", lambda _repo: {"changed.py": "new-code"})
    elif changed == "candidate":
        write_json(h.root / "candidates.json", {**h.candidates, "mutated": True})
    else:
        h.protocol["router_threshold"] = 0.99
    events_before = list(h.state["events"])
    with pytest.raises(ValueError, match="Frozen"):
        experiment.test(h.api, h.protocol, h.repo)
    assert h.state["events"] == events_before
    assert not (h.root / "datasets" / "test.json").exists()
    assert not (h.root / "test_masks_before_outcomes.json").exists()


def test_summary_of_zero_complete_cases_is_json_null_not_nan():
    result = experiment.summarize_repeats([[], []], expected_ids=["missing-a", "missing-b"])
    assert result["n_unique_tasks"] == 0
    assert result["excluded_tasks_missing_any_repeat"] == 2
    assert result["em"] is None
    assert result["repeat_em"] == [None, None]
    json.dumps(result, allow_nan=False)
