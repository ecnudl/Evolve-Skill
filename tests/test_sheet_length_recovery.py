"""Offline fixtures only; never submit API calls or execute generated code."""
import fcntl
import json
from pathlib import Path

import openpyxl
import pytest

from scripts import recover_sheet_length as recovery
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, load_checkpoint, read_json, write_json
from skillopt.continual_eval.datasets import load_panel
from skillopt.continual_eval.fixtures import fixture_panel
from skillopt.validator_pilot.api import long_stream_service
from tests.test_full_delivery_recovery import API, score


def setup(tmp_path, monkeypatch, finishes=("length", "stop")):
    lock = tmp_path / "native.lock"
    lock.touch()
    parent, root = tmp_path / "old", tmp_path / "new"
    book = tmp_path / "input.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = 0
    wb.save(book)
    panel = fixture_panel("spreadsheetbench")
    panel["tasks"][0]["partition"] = "development"
    panel["tasks"][0]["public"]["input_files"] = [str(book)]
    panel["tasks"][0]["private"]["test_files"] = ["PRIVATE_GOLD_MUST_NOT_REACH_API.xlsx"]
    panel_path = tmp_path / "panel.json"
    write_json(panel_path, panel)
    panel = load_panel(panel_path)
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
        "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                      "initial_health_policy": "completed_response_v1"}}
    config = {"version": "continual-eval-v2", "order": list(BENCHMARKS), "partition": "development",
        "methods": ["no_skill"], "histories": ["h0"], "repeats": 2, "model": model,
        "panels": {b: str(panel_path) if b == "spreadsheetbench" else None for b in BENCHMARKS},
        "runtime": {"spreadsheetbench": {}}, "project_disjoint": False, "exposure_manifest": None}
    plan = freeze_plan(config, parent)
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    service = long_stream_service({"provider": "fixture", "model": "fixture", "reasoning_effort": "low",
        "timeout_seconds": {"connect": 20, "read": 300, "write": 30, "pool": 20},
        "initial_health_policy": "completed_response_v1"}, read_timeout_seconds=300, stream_wall_seconds=1800)
    write_json(parent / "model_service.json", seal(service))
    monkeypatch.setattr(backends, "_native", lambda *a: {"status": "available", "output_base64": "Zml4dHVyZQ=="})
    api, predictions = API(parent, service, finishes=finishes), []
    for repeat in range(2):
        task = panel["tasks"][0]
        base, position = runner.position(parent, cp, "spreadsheetbench", task, repeat)
        predictions.append(backends.solve("spreadsheetbench", task["public"], "",
            runner.PositionCalls(api, base, position, 65536, 1)))
    runner.generate(parent, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench",
                    fixture_solve=lambda *a, **k: predictions.pop(0))
    runner.score_checkpoint(parent, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench", fixture_score=score)
    runner.report(parent)
    source = Path(__file__).resolve().parents[1]
    recovery.prepare(parent, source, root, lock)
    return parent, root, read_json(root / "protocol.json", sealed=True), lock


def run(root, protocol, **kwargs):
    api = API(root, protocol["service"], **kwargs)
    result = recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=score)
    return result, api


def test_exact_prompts_once_unknown_or_known_old_scores_unchanged(tmp_path, monkeypatch):
    parent, root, protocol, _ = setup(tmp_path, monkeypatch)
    before = {str(p): p.read_bytes() for p in parent.rglob("*.json")}
    item = protocol["snapshot"]["selected"]
    original = read_json(parent / item["call_path"])["receipt"]["request"]
    result, api = run(root, protocol)
    assert api.calls == [(original["system"], original["user"], 131072, original["repeat"])]
    assert "PRIVATE_GOLD" not in json.dumps(api.calls)
    assert result["counts"] == {"pass": 1} and result["new_costs"]["logical_calls"] == 1
    assert result["old_scores_replaced"] is False and result["feedback_allowed"] is False
    again = recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=score)
    assert result == again and len(api.calls) == 1
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*.json")}


def test_api_outside_native_lock_generation_scoring_inside_and_both_costed(tmp_path, monkeypatch):
    _, root, protocol, lock_path = setup(tmp_path, monkeypatch)
    api = API(root, protocol["service"])
    paid_call = api.call
    seen = []

    def call(*args, **kwargs):
        with lock_path.open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return paid_call(*args, **kwargs)

    def native(request, runtime):
        with lock_path.open("rb") as lock, pytest.raises(BlockingIOError):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        seen.append("generation")
        return {"status": "available", "output_base64": "Zml4dHVyZQ==", "cleanup_confirmed": True,
                "execution_costs": {"container_calls": 1, "wall_seconds": 2}}

    def scoring(benchmark, public, private, prediction, *, runtime):
        with lock_path.open("rb") as lock, pytest.raises(BlockingIOError):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        seen.append("scoring")
        context = runtime["_score_context"]
        assert context["artifact_dir"].startswith(str(root / "host_only/scorer_artifacts"))
        assert context["request"]["original_position"] == protocol["snapshot"]["selected"]["position"]
        return {**score(benchmark, public, private, prediction),
                "execution_costs": {"container_calls": 2, "wall_seconds": 5}}

    api.call = call
    monkeypatch.setattr(backends, "_native", native)
    result = recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=scoring)
    assert seen == ["generation", "scoring"]
    assert result["native_container_calls"] == 3 and result["native_wall_seconds"] == 7


@pytest.mark.parametrize("finish", ["length", "network_error", "sensitive"])
def test_unknown_retained_and_closed_errors_never_resampled(tmp_path, monkeypatch, finish):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(backends, "_native", lambda *a: pytest.fail("No program to execute"))
    result, api = run(root, protocol, finishes=(finish,))
    assert result["counts"] == {"unknown": 1}
    assert recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=score) == result
    assert len(api.calls) == 1


def test_open_intent_blocks_resampling(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="Authored crash"):
        run(root, protocol, crash=True)
    assert recovery.report(root)["new_costs"]["unclosed_calls"] == 1
    with pytest.raises(ValueError, match="no automatic resampling"):
        run(root, protocol)


def test_prompt_change_blocks_before_api(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    api = API(root, protocol["service"])
    def wrong(benchmark, public, skill, callback, *, runtime):
        return backends.solve(benchmark, {**public, "instruction": "WRONG"}, skill, callback, runtime=runtime)
    with pytest.raises(ValueError, match="prompt reconstruction"):
        recovery.run(root, fixture_api=api, fixture_solve=wrong, fixture_score=score)
    assert api.calls == [] and not (root / "intent.json").exists()


def test_cleanup_failure_blocks_scoring(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(backends, "_native", lambda *a: {"status": "unknown",
        "reason": "container_cleanup_unconfirmed", "execution_costs": {"container_calls": 1, "wall_seconds": 2}})
    api = API(root, protocol["service"])
    result = recovery.run(root, fixture_api=api, fixture_solve=backends.solve,
                          fixture_score=lambda *a, **k: pytest.fail("Unsafe cleanup must stop scoring"))
    assert result["status"] == "blocked" and result["counts"] == {"unknown": 1}
    assert result["native_container_calls"] == 1


def test_pause_before_any_api_submission(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    (root / "PAUSE").touch()
    result, api = run(root, protocol)
    assert result["status"] == "pending" and api.calls == []
    assert not (root / "intent.json").exists()


def test_changed_public_input_blocks_before_call(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    (tmp_path / "input.xlsx").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Original evidence changed|Panel changed"):
        run(root, protocol)


def test_resealed_published_result_rejected(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    run(root, protocol)
    path = root / "result.json"
    row = read_json(path)
    row.pop("record_hash")
    row["score"].update(status="fail", score=0.)
    path.write_text(json.dumps(seal(row)))
    with pytest.raises(ValueError, match="Published result changed"):
        run(root, protocol)


def test_zero_or_multiple_length_positions_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="exactly one"):
        setup(tmp_path, monkeypatch, finishes=("length", "length"))
    assert not (tmp_path / "new").exists()


def test_missing_usage_and_http_retry_budget_preserved(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    result, _ = run(root, protocol, usage=False, attempts=3)
    assert result["new_costs"]["http_attempts"] == 3
    assert result["new_costs"]["reported_tokens"] is None
    assert not result["new_costs"]["retry_inclusive_usage_known"]


def test_closed_call_with_interrupted_scoring_not_resampled(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    api = API(root, protocol["service"])
    def interrupted(*args, **kwargs):
        raise RuntimeError("Scorer interruption")
    with pytest.raises(RuntimeError, match="Scorer interruption"):
        recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=interrupted)
    result = recovery.report(root)
    assert result["new_costs"]["logical_calls"] == 1 and result["completed"] == 0
    assert result["native_accounting_complete"] is False
    with pytest.raises(ValueError, match="no automatic resampling"):
        run(root, protocol)
    assert len(api.calls) == 1


def test_scorer_artifact_mutation_is_rejected(tmp_path, monkeypatch):
    _, root, protocol, _ = setup(tmp_path, monkeypatch)
    api = API(root, protocol["service"])
    def recording(benchmark, public, private, prediction, *, runtime):
        path = Path(runtime["_score_context"]["artifact_dir"]) / "fixture_receipt.json"
        write_json(path, seal({"fixture": "original"}))
        return score(benchmark, public, private, prediction)
    recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=recording)
    next(root.glob("host_only/scorer_artifacts/*/fixture_receipt.json")).write_text("{}")
    with pytest.raises(ValueError, match="Scorer evidence changed"):
        recovery.report(root)


@pytest.mark.parametrize("field,value", [("max_tokens", 262144), ("feedback_allowed", True),
                                        ("max_new_logical_calls", 2), ("max_http_attempts_per_call", 4)])
def test_resealed_changed_limits_blocked(tmp_path, monkeypatch, field, value):
    _, root, _, _ = setup(tmp_path, monkeypatch)
    path = root / "protocol.json"
    protocol = read_json(path)
    protocol.pop("record_hash")
    protocol[field] = value
    path.write_text(json.dumps(seal(protocol)))
    with pytest.raises(ValueError, match="Frozen limits changed"):
        recovery.report(root)


@pytest.mark.parametrize("component", ["generation", "scoring"])
@pytest.mark.parametrize("field,value", [("cleanup_confirmed", False), ("runtime_image_id", "wrong-image")])
def test_wrong_native_image_or_cleanup_cannot_be_passed(component, field, value):
    prediction = {"output": {"cases": [{"status": "available", "cleanup_confirmed": True, "runtime_image_id": "generation"}]}}
    scoring = {"status": "pass", "cleanup_confirmed": True, "runtime_image_id": "scoring"}
    if component == "generation":
        prediction["output"]["cases"][0][field] = value
    else:
        scoring[field] = value
    with pytest.raises(ValueError, match="identity or cleanup unverified"):
        recovery._validate_native(prediction, scoring, {"image": "generation", "recalculation": {"image": "scoring"}}, False)
