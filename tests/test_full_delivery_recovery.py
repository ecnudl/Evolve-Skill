"""Closed-panel fixtures only: no paid API, Docker, or natural effect claim."""
import json
from pathlib import Path

import pytest

from scripts import recover_full_delivery_unknowns as recovery
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, load_checkpoint, read_json, write_json
from skillopt.continual_eval.fixtures import fixture_panel
from skillopt.validator_pilot.api import digest, long_stream_service


class API:
    model = "fixture"

    def __init__(self, root, service, finishes=("stop",), crash=False, attempts=1, usage=True):
        self.root, self.service, self.finishes = root, service, list(finishes)
        self.crash, self.attempts, self.usage, self.calls = crash, attempts, usage, []

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        self.calls.append((system, user, max_tokens, repeat))
        if self.crash:
            raise RuntimeError("Authored crash")
        finish = self.finishes.pop(0)
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        receipt = {"request": request, "request_hash": digest(request), "ok": finish == "stop",
            "response": "[[fixture_answer]]" if finish in {"stop", "length"} else "",
            "finish_reason": finish, "status": 200, "returned_model": self.model,
            "stream_complete": True, "http_attempt_count": self.attempts,
            "error_type": "truncated_content" if finish == "length" else None,
            "usage": {"prompt_tokens": 2, "completion_tokens": 3} if self.usage else {}}
        write_json(self.root / "api/calls" / (receipt["request_hash"] + ".json"), receipt)
        return receipt

    @staticmethod
    def _initial_ready(receipt):
        return receipt["finish_reason"] in {"stop", "length"}


def setup(tmp_path, benchmark="korbench", finishes=("length", "network_error")):
    (tmp_path / "native.lock").touch()
    parent, root = tmp_path / "old", tmp_path / "new"
    panel = fixture_panel(benchmark)
    panel["tasks"][0]["partition"] = "development"
    if benchmark == "korbench":
        panel["tasks"][0]["private"]["answer"] = "PRIVATE_GOLD_MUST_NOT_REACH_API"
    path = tmp_path / "panel.json"
    write_json(path, panel)
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
        "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                      "initial_health_policy": "completed_response_v1"}}
    config = {"version": "continual-eval-v2", "order": list(BENCHMARKS), "partition": "development",
        "methods": ["no_skill"], "histories": ["h0"], "repeats": 2, "model": model,
        "panels": {b: str(path) if b == benchmark else None for b in BENCHMARKS},
        "runtime": {benchmark: {}}, "project_disjoint": False, "exposure_manifest": None}
    plan = freeze_plan(config, parent)
    cp = load_checkpoint(parent, "no_skill", "h0", 0, plan)
    service = long_stream_service({"provider": "fixture", "model": "fixture", "reasoning_effort": "low",
        "timeout_seconds": {"connect": 20, "read": 300, "write": 30, "pool": 20},
        "initial_health_policy": "completed_response_v1"}, read_timeout_seconds=300, stream_wall_seconds=1800)
    write_json(parent / "model_service.json", seal(service))
    api, predictions = API(parent, service, finishes=finishes), []
    for repeat in range(2):
        task = panel["tasks"][0]
        base, position = runner.position(parent, cp, benchmark, task, repeat)
        predictions.append(backends.solve(benchmark, task["public"], "", runner.PositionCalls(api, base, position, 65536, 1)))
    runner.generate(parent, method="no_skill", history="h0", stage=0, benchmark=benchmark,
                    fixture_solve=lambda *a, **k: predictions.pop(0))
    runner.score_checkpoint(parent, method="no_skill", history="h0", stage=0, benchmark=benchmark,
                            fixture_score=score)
    runner.report(parent)
    return parent, Path(__file__).resolve().parents[1], root


def score(benchmark, public, private, prediction, *, runtime=None):
    unknown = prediction["status"] == "unknown"
    return {"status": "unknown" if unknown else "pass", "score": None if unknown else 1.,
            "reason": prediction["reason"] if unknown else "authored_fixture", "metrics": {}}


def prepared(tmp_path, *, reason="length", **kwargs):
    parent, source, root = setup(tmp_path, **kwargs)
    recovery.prepare(parent, source, root, reason=reason, native_lock=tmp_path / "native.lock")
    return parent, root, read_json(root / "protocol.json", sealed=True)


def run(root, value, **kwargs):
    api = API(root, value["service"], **kwargs)
    return recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=score), api


def test_length_exact_prompts_full_roster_once_and_original_unchanged(tmp_path):
    parent, root, value = prepared(tmp_path)
    before = {str(p): p.read_bytes() for p in parent.rglob("*.json")}
    item = value["snapshot"]["selected"][0]
    old = read_json(parent / item["call_path"])["receipt"]["request"]
    result, api = run(root, value)
    assert value["snapshot"]["original_positions"] == 2 and len(value["snapshot"]["selected"]) == 1
    assert result["counts"] == {"pass": 1} and result["new_costs"]["logical_calls"] == 1
    assert api.calls == [(old["system"], old["user"], 131072, old["repeat"])]
    assert "PRIVATE_GOLD_MUST_NOT_REACH_API" not in json.dumps(api.calls)
    assert "PRIVATE_GOLD_MUST_NOT_REACH_API" not in json.dumps(value)
    assert value["service"]["stream_max_wall_seconds"] == 3600
    again = recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=score)
    assert again == result and len(api.calls) == 1
    assert before == {str(p): p.read_bytes() for p in parent.rglob("*.json")}
    assert not result["whole_benchmark_accuracy_claimed"] and not result["old_scores_replaced"]


def test_network_retains_original_budget_and_service(tmp_path):
    _, root, value = prepared(tmp_path, reason="network_error")
    result, api = run(root, value)
    assert result["counts"] == {"pass": 1} and api.calls[0][2] == 65536
    assert value["service"] == value["snapshot"]["service"]


def test_qa_sensitive_is_archived_never_resubmitted(tmp_path):
    _, root, value = prepared(tmp_path, benchmark="searchqa", finishes=("sensitive", "content_filter"), reason="archive_filters")
    result, api = run(root, value)
    assert result["blocked"] == 2 and result["selected"] == 0 and result["status"] == "completed"
    assert not api.calls and result["new_costs"]["logical_calls"] == 0


def test_repeated_truncation_retained_no_retry(tmp_path):
    _, root, value = prepared(tmp_path)
    result, api = run(root, value, finishes=("length",))
    assert result["counts"] == {"unknown": 1}
    recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=score)
    assert len(api.calls) == 1


def test_open_call_blocks_future_resampling(tmp_path):
    _, root, value = prepared(tmp_path)
    with pytest.raises(ValueError, match="retain any open"):
        run(root, value, crash=True)
    assert recovery.report(root)["new_costs"]["unclosed_calls"] == 1
    with pytest.raises(ValueError, match="Open recovery intent"):
        run(root, value)


def test_prompt_mismatch_prevents_paid_call(tmp_path):
    _, root, value = prepared(tmp_path)
    api = API(root, value["service"])
    def wrong(benchmark, public, skill, callback, *, runtime):
        return backends.solve(benchmark, {**public, "question": "CHANGED"}, skill, callback, runtime=runtime)
    with pytest.raises(ValueError, match="Solver call unavailable"):
        recovery.run(root, fixture_api=api, fixture_solve=wrong, fixture_score=score)
    assert api.calls == []


@pytest.mark.parametrize("mutation", ["open", "cache", "score", "report", "source", "panel"])
def test_bad_source_prevents_output(tmp_path, mutation):
    parent, source, root = setup(tmp_path)
    if mutation == "source":
        source = tmp_path / "missing"
    elif mutation == "open":
        write_json(next((parent / "predictions").iterdir()) / "call_intents/extra.json", seal({"open": True}))
    elif mutation == "panel":
        # Changing the roster can never be silently treated as a new denominator.
        plan = read_json(parent / "plan.json")
        plan["tasks"] = []
        plan.pop("record_hash")
        (parent / "plan.json").write_text(json.dumps(seal(plan)))
    else:
        glob = {"cache": "api/calls/*.json", "score": "host_only/scores/*.json", "report": "host_only/reports/*.json"}[mutation]
        next(parent.glob(glob)).write_text("{}")
    with pytest.raises((ValueError, FileNotFoundError, KeyError)):
        recovery.prepare(parent, source, root, reason="length", native_lock=tmp_path / "native.lock")
    assert not root.exists()


def test_closed_scores_not_selected(tmp_path):
    _, root, value = prepared(tmp_path, finishes=("stop", "stop"))
    result, api = run(root, value)
    assert result["selected"] == 0 and api.calls == []


def test_cost_missing_usage_and_existing_transport_attempts(tmp_path):
    _, root, value = prepared(tmp_path)
    result, _ = run(root, value, usage=False, attempts=3)
    assert result["new_costs"]["http_attempts"] == 3
    assert result["usage_missing_calls"] == 1 and result["new_costs"]["reported_tokens"] is None
    assert result["known_reported_tokens"] == 0 and not result["new_costs"]["retry_inclusive_usage_known"]


def test_resealed_published_result_cannot_change(tmp_path):
    _, root, value = prepared(tmp_path)
    run(root, value)
    path = next(root.glob("positions/*/result.json"))
    row = read_json(path)
    row.pop("record_hash")
    row["score"].update(status="fail", score=0.)
    path.write_text(json.dumps(seal(row)))
    with pytest.raises(ValueError, match="Published result changed"):
        run(root, value)


def test_scorer_exception_does_not_resample_closed_api(tmp_path):
    _, root, value = prepared(tmp_path)
    api = API(root, value["service"])
    def broken(*a, **k):
        raise RuntimeError("Authored scoring interruption")
    with pytest.raises(RuntimeError, match="scoring interruption"):
        recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=broken)
    with pytest.raises(ValueError, match="Open recovery intent"):
        run(root, value)
    assert len(api.calls) == 1


@pytest.mark.parametrize("field,value", [("max_tokens", 262144), ("max_new_logical_calls", 4),
                                        ("feedback_allowed", True), ("max_http_attempts_per_call", 99)])
def test_resealed_changed_limits_blocked(tmp_path, field, value):
    _, root, _ = prepared(tmp_path)
    path = root / "protocol.json"
    protocol = read_json(path)
    protocol.pop("record_hash")
    protocol[field] = value
    path.write_text(json.dumps(seal(protocol)))
    with pytest.raises(ValueError, match="Frozen recovery limits"):
        recovery.report(root)


def test_pause_does_not_reserve_or_submit(tmp_path):
    _, root, value = prepared(tmp_path)
    (root / "PAUSE").touch()
    result, api = run(root, value)
    assert result["status"] == "pending" and not api.calls
    assert not (root / "positions").exists()


def test_prior_cleanup_failure_stops_remaining_calls(tmp_path):
    _, root, value = prepared(tmp_path, finishes=("length", "length"))
    api = API(root, value["service"])
    def bad_cleanup(*a, **k):
        return {"status": "unknown", "score": None, "metrics": {}, "reason": "cleanup_failed", "cleanup_confirmed": False}
    with pytest.raises(ValueError, match="cleanup unconfirmed"):
        recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=bad_cleanup)
    with pytest.raises(ValueError, match="Prior native cleanup"):
        run(root, value)
    assert len(api.calls) == 1


@pytest.mark.parametrize("finishes,selected", [(("length", "length"), 2), (("length", "network_error"), 1)])
def test_actual_native_cleanup_error_shape_without_boolean_stops_and_reports_cost(tmp_path, finishes, selected):
    _, root, value = prepared(tmp_path, finishes=finishes)
    api = API(root, value["service"])
    def bad_cleanup(*a, **k):
        return {"status": "unknown", "score": None, "metrics": {}, "reason": "container_cleanup_unconfirmed",
                "execution_costs": {"container_calls": 1, "wall_seconds": 12.5, "includes_cleanup": True}}
    with pytest.raises(ValueError, match="cleanup unconfirmed"):
        recovery.run(root, fixture_api=api, fixture_solve=backends.solve, fixture_score=bad_cleanup)
    result = recovery.report(root)
    assert result["completed"] == 1 and result["selected"] == selected and len(api.calls) == 1
    assert result["status"] == "blocked" and result["blocked_reason"] == "native_cleanup_unconfirmed"
    native = result["native_execution"]
    assert native["reported_container_calls"] == 1 and native["reported_wall_seconds"] == 12.5
    assert native["cleanup_unconfirmed_results"] == 1
    with pytest.raises(ValueError, match="Prior native cleanup"):
        run(root, value)


@pytest.mark.parametrize("change", [None, "image", "source"])
def test_natural_preflight_inspects_only_never_launches_container(monkeypatch, change):
    def forbidden(*args, **kwargs):
        pytest.fail("Readiness/native probe must not run outside accounted scoring")
    monkeypatch.setattr(backends, "readiness", forbidden)
    monkeypatch.setattr(backends, "_native", forbidden)
    seen = []
    def image_ready(runtime):
        seen.append("inspect")
        return {"status": "unsupported" if change == "image" else "ready"}
    def sources(runtime):
        seen.append("sources")
        return {"source": "changed" if change == "source" else "original"}
    monkeypatch.setattr(backends, "_image_ready", image_ready)
    monkeypatch.setattr(backends, "_kor_sources", sources)
    value = {"snapshot": {"benchmark": "korbench", "native_sources_hash": digest({"source": "original"})}}
    if change:
        with pytest.raises(ValueError, match="image unavailable|source changed"):
            recovery._read_only_native_preflight(value, {})
    else:
        recovery._read_only_native_preflight(value, {})
        assert seen == ["inspect", "sources"]
