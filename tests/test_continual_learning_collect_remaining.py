"""Diagnostic collection fixtures only; no paid models or native containers."""
import json

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, write_json
from skillopt.continual_learning import collect_remaining as collector
from skillopt.continual_learning import feedback_ablation as ablation
from skillopt.continual_learning.ledger import Ledger
from skillopt.validator_pilot.api import digest
from tests import test_continual_learning_feedback_ablation as fixtures


def interrupted(tmp_path, *, arm="generic_summary", closed=16):
    shadow, base, source, original = fixtures.prepare_arm(tmp_path, arm=arm)
    visited = []

    def evaluate(task, skill):
        visited.append(task["task_id"])
        prediction, score = fixtures.parent_fixture.fixture_score(task, skill)
        if len(visited) == closed:
            score = {"status": "unknown", "score": None, "metrics": {}, "reason": "authored_native_timeout"}
        return prediction, score

    result = ablation.run(shadow, fixture_api=fixtures.API(), fixture_evaluate=evaluate)
    assert result["status"] == "pending" and result["selection_closed"] == closed
    return shadow, base, source, result, original


def rewrite(path, value):
    value.pop("record_hash", None)
    path.write_text(json.dumps(seal(value)))


@pytest.mark.parametrize("arm", list(ablation.POLICIES))
def test_only_unsubmitted_suffix_unknown_kept_no_skill_gate_or_reroll(tmp_path, arm):
    shadow, base, source, old, original = interrupted(tmp_path, arm=arm)
    before = {str(p): p.read_bytes() for root in (shadow, base) for p in root.rglob("*") if p.is_file()}
    root = tmp_path / "collection"
    assert collector.prepare(shadow, source, root)["remaining_positions"] == 48
    value = read_json(root / "protocol.json", sealed=True)
    assert value["manifest"]["budget"]["max_reflection_calls"] == 0
    assert value["manifest"]["budget"]["max_api_calls"] == 48
    assert value["manifest"]["budget"]["max_reported_tokens"] == (
        2000000 - original["costs"]["reported_tokens_known_subtotal"] - old["new_costs"]["reported_tokens_known_subtotal"])
    api, visited = fixtures.API(), []

    def evaluate(task, skill):
        visited.append(task["task_id"])
        assert skill == "Check boundaries."
        prediction, score = fixtures.parent_fixture.fixture_score(task, skill)
        if len(visited) == 4:
            score = {"status": "unknown", "score": None, "metrics": {}, "reason": "authored_second_unknown"}
        return prediction, score

    result = collector.run(root, fixture_api=api, fixture_evaluate=evaluate)
    assert result["status"] == "completed" and visited == [str(i) for i in range(81, 129)]
    assert api.calls == [] and result["collection_costs"]["reflection_calls"] == 0
    assert result["collection_total_cost_known"]
    assert result["selection_closed"] == 64 and result["known_denominator"] == 62
    assert result["selection_counts"] == {"pass": 62, "fail": 0, "unknown": 2, "missing": 0}
    assert result["paired_to_same_parent"] == {"wins": 31, "losses": 0, "ties": 31, "unknown": 2, "missing": 0}
    assert result["original_gate_status"] == "pending" and result["diagnostic_only"]
    assert not any(result[k] for k in ("s1_authorized", "deployment_authorized", "scope_authorized", "optimizer_resumed"))
    assert not any(k in result for k in ("selected_skill", "candidate_skill", "gate_action", "candidate_score"))
    assert result["original_arm_costs"] == old["new_costs"] and result["shared_base_costs"] == original["costs"]
    assert collector.run(root, fixture_api=api, fixture_evaluate=evaluate) == result and len(visited) == 48
    assert before == {str(p): p.read_bytes() for root in (shadow, base) for p in root.rglob("*") if p.is_file()}


def test_closed_final_unknown_has_no_remaining_position(tmp_path):
    shadow, _, source, _, _ = interrupted(tmp_path, closed=64)
    with pytest.raises(ValueError, match="first-unknown selection prefix"):
        collector.prepare(shadow, source, tmp_path / "collection")


@pytest.mark.parametrize("target", ["shadow", "base"])
def test_active_original_writer_blocks_prepare(tmp_path, target):
    shadow, base, source, _, _ = interrupted(tmp_path)
    with output_lock(shadow if target == "shadow" else base), pytest.raises(ValueError, match="active writer"):
        collector.prepare(shadow, source, tmp_path / "collection")
    assert not (tmp_path / "collection").exists()


@pytest.mark.parametrize("mutation", ["candidate", "status", "reason", "selected", "gate", "counts", "unclosed", "panel"])
def test_changed_or_started_original_evidence_cannot_be_reused(tmp_path, mutation):
    shadow, _, source, result, _ = interrupted(tmp_path)
    if mutation == "unclosed":
        protocol = read_json(shadow / "protocol.json", sealed=True)
        panel = read_json(shadow / "panel.json")
        request = {"manifest_hash": protocol["manifest"]["record_hash"], "candidate_hash": digest({"skill": "Check boundaries."}),
                   "task_hash": digest(panel["tasks"][81]), "role": "selection", "repeat": 0}
        write_json(shadow / "evaluation_intents" / (digest(request) + ".json"), seal(request))
        result["artifacts"] = ablation._artifacts(shadow, Ledger(shadow, protocol["manifest"], None))
    elif mutation == "panel":
        panel = read_json(shadow / "panel.json")
        panel["tasks"][0]["partition"] = "final"
        (shadow / "panel.json").write_text(json.dumps(panel))
    else:
        key, value = {"candidate": ("candidate_skill", "Different instructions."), "status": ("status", "completed"),
                      "reason": ("reason", "APIError"), "selected": ("selected_skill", "Check boundaries."),
                      "gate": ("gate_action", "accept_new_best"), "counts": ("selection_closed", 15)}[mutation]
        result[key] = value
    rewrite(shadow / "result.json", result)
    with pytest.raises(ValueError):
        collector.prepare(shadow, source, tmp_path / "collection")
    assert not (tmp_path / "collection").exists()


def test_frozen_preparation_detects_original_change_before_any_new_call(tmp_path):
    shadow, _, source, result, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    result["selection_not_closed"] = 0
    rewrite(shadow / "result.json", result)
    api = fixtures.API()
    with pytest.raises(ValueError):
        collector.run(root, fixture_api=api, fixture_evaluate=fixtures.parent_fixture.fixture_score)
    assert api.calls == [] and not (root / "started.json").exists()


def test_new_collection_exception_preserves_missing_and_never_resumes(tmp_path):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    visited = []

    def evaluate(task, skill):
        visited.append(task["task_id"])
        if len(visited) == 3:
            raise RuntimeError("Sensitive provider text must not be persisted")
        return fixtures.parent_fixture.fixture_score(task, skill)

    api = fixtures.API()
    result = collector.run(root, fixture_api=api, fixture_evaluate=evaluate)
    assert result["status"] == "pending" and result["reason"] == "RuntimeError"
    assert result["selection_counts"] == {"pass": 17, "fail": 0, "unknown": 1, "missing": 46}
    assert len(list((root / "evaluation_intents").glob("*.json"))) == 3
    assert len(list((root / "evaluations").glob("*.json"))) == 2
    assert collector.run(root, fixture_api=api, fixture_evaluate=evaluate) == result and len(visited) == 3


def test_preexisting_started_collection_does_not_run(tmp_path):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    value = read_json(root / "protocol.json", sealed=True)
    write_json(root / "started.json", seal({"protocol_hash": value["record_hash"]}))
    api = fixtures.API()
    result = collector.run(root, fixture_api=api, fixture_evaluate=fixtures.parent_fixture.fixture_score)
    assert result["status"] == "pending" and result["model_calls_submitted"] == 0 and api.calls == []


def test_collector_output_cannot_be_old_directory(tmp_path):
    shadow, _, source, _, _ = interrupted(tmp_path)
    for output in (shadow, shadow / "new"):
        with pytest.raises(ValueError, match="independent"):
            collector.prepare(shadow, source, output)


def test_terminal_artifact_tamper_blocks_replay(tmp_path):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    api = fixtures.API()
    collector.run(root, fixture_api=api, fixture_evaluate=fixtures.parent_fixture.fixture_score)
    path = next((root / "evaluations").glob("*.json"))
    row = read_json(path, sealed=True)
    row["score"].update(status="fail", score=0)
    rewrite(path, row)
    with pytest.raises(ValueError, match="evidence changed"):
        collector.run(root, fixture_api=api, fixture_evaluate=fixtures.parent_fixture.fixture_score)
    assert api.calls == []


def test_existing_solver_budget_service_runtime_and_unknown_without_retry(tmp_path, monkeypatch):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    protocol, prior = collector._load(root)
    manifest = protocol["manifest"]
    api = fixtures.API("```python\ndef solve(): return 1\n```")
    ledger, scored = Ledger(root, manifest, api), []

    def score(benchmark, public, private, prediction, *, runtime):
        assert benchmark == "bigcodebench" and runtime == prior["inherited"]["manifest"]["runtime"]
        assert prediction["status"] == "available" and prediction["output"] == "def solve(): return 1"
        scored.append(public)
        return {"status": "unknown", "score": None, "metrics": {}, "reason": "authored_native_timeout"}

    monkeypatch.setattr(collector.backends, "score", score)
    for task in prior["remaining"][:2]:
        collector._execute(root, manifest, ledger, task, prior["candidate"])
    assert len(scored) == len(api.calls) == 2
    assert all(r["max_tokens"] == 65536 and r["repeat"] == 0 and r["service"] == api.service
               and r["kind"] == "continual-learning-solver" for r in api.calls)
    costs = ledger.snapshot()
    assert costs["solver_calls"] == 2 and costs["reflection_calls"] == 0
    assert costs["reported_tokens_known_subtotal"] == 60
    with pytest.raises(ValueError, match="Never resample"):
        collector._execute(root, manifest, ledger, prior["remaining"][0], prior["candidate"])
    assert len(api.calls) == 2


def test_incomplete_new_usage_stops_before_next_position(tmp_path, monkeypatch):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    protocol, prior = collector._load(root)
    manifest = protocol["manifest"]
    api = fixtures.API("def solve(): return 1", usage={})
    ledger = Ledger(root, manifest, api)
    monkeypatch.setattr(collector.backends, "score", lambda *a, **k:
                        {"status": "unknown", "score": None, "metrics": {}, "reason": "authored_unknown"})
    collector._execute(root, manifest, ledger, prior["remaining"][0], prior["candidate"])
    with pytest.raises(ValueError, match="incomplete usage"):
        collector._execute(root, manifest, ledger, prior["remaining"][1], prior["candidate"])
    assert len(api.calls) == len(list((root / "evaluation_intents").glob("*.json"))) == 1


def test_cli_check_performs_zero_model_calls(tmp_path, monkeypatch, capsys):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["collect_remaining", "check", "--output", str(root)])
    collector.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ready_not_launched" and result["model_calls"] == 0
    assert not (root / "started.json").exists()


def test_orphan_cache_and_invalid_receipt_still_allow_honest_pending_audit(tmp_path):
    root = tmp_path / "broken_new_collection"
    root.mkdir()
    write_json(root / "api/calls/orphan.json", {"private_data": "not adopted or exported"})
    manifest = {"record_hash": "authored_manifest", "model": {"provider": "bigmodel", "name": "glm-5.3"},
                "budget": {"solver_max_tokens": 65536}}
    costs, rows, issues = collector._audit_collection(root, manifest, "Frozen skill.", [], {})
    assert costs["logical_calls"] == 0 and rows == {}
    assert issues == {"position_validation_error": "ValueError"}
    assert "private_data" not in json.dumps(issues)
    write_json(root / "calls/malformed.json", seal({"role": "solver", "receipt": {}}))
    costs, rows, issues = collector._audit_collection(root, manifest, "Frozen skill.", [], {})
    assert costs is None and rows == {} and "cost_validation_error" in issues


def test_invalid_new_position_is_pending_not_silently_counted(tmp_path):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    visited = []

    def evaluate(task, skill):
        visited.append(task["task_id"])
        if len(visited) == 2:
            path = next((root / "evaluations").glob("*.json"))
            path.write_text("{}")
            raise RuntimeError("raw private details must not be persisted")
        return fixtures.parent_fixture.fixture_score(task, skill)

    api = fixtures.API()
    result = collector.run(root, fixture_api=api, fixture_evaluate=evaluate)
    assert result["status"] == "pending" and result["reason"] == "RuntimeError"
    assert result["selection_counts"] == {"pass": 15, "fail": 0, "unknown": 1, "missing": 48}
    assert result["evidence_validation_issues"] == {"position_validation_error": "ValueError"}
    assert not result["collection_total_cost_known"]
    assert result["collection_evaluation_intents_on_disk"] == 2
    assert collector.run(root, fixture_api=api, fixture_evaluate=evaluate) == result and len(visited) == 2


@pytest.mark.parametrize("changed", ["continual_eval/native_worker.py", "continual_eval/core.py",
                                    "continual_eval/runner.py"])
def test_changed_native_worker_or_scoring_harness_rejected(tmp_path, monkeypatch, changed):
    shadow, _, source, _, _ = interrupted(tmp_path)
    current = collector.sources()
    current[changed] = "0" * 64
    monkeypatch.setattr(collector, "sources", lambda: current)
    with pytest.raises(ValueError, match="Execution or inheritance code changed"):
        collector.prepare(shadow, source, tmp_path / "collection")
    assert not (tmp_path / "collection").exists()


def test_even_orphan_cache_bytes_bound_on_pending_replay(tmp_path):
    shadow, _, source, _, _ = interrupted(tmp_path)
    root = tmp_path / "collection"
    collector.prepare(shadow, source, root)
    orphan = root / "api/calls/orphan.json"

    def evaluate(*args):
        write_json(orphan, {"safe_fixture": "orphan provider metadata"})
        raise RuntimeError("fixture receipt rejection")

    api = fixtures.API()
    result = collector.run(root, fixture_api=api, fixture_evaluate=evaluate)
    assert result["status"] == "pending" and "api/calls/orphan.json" in result["artifacts"]
    orphan.write_text("{}")
    with pytest.raises(ValueError, match="evidence changed"):
        collector.run(root, fixture_api=api, fixture_evaluate=evaluate)
    assert api.calls == []
