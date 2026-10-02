"""Offline learner transport controls, never natural learning-effect evidence.

The HTTP tests use authored panels with a natural-shaped label to exercise the
production client branch, local MockTransport, and a fake native scorer. The
GEPA transport harness is an authored optimizer; official-engine tests remain
in test_continual_learning_gepa.py. No credentials, network or Docker are used.
"""
import importlib
import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning import VERSION, gepa, skillopt
from skillopt.continual_learning.contracts import LONG_RESPONSE_VERSION, manifest, validate_manifest
from skillopt.continual_learning.ledger import Ledger
from skillopt.validator_pilot import api as provider
from skillopt.validator_pilot.api import digest

TRANSPORT = {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
             "initial_health_policy": "completed_response_v1"}


def inputs(*, version=LONG_RESPONSE_VERSION, method="skillopt", natural=False,
           solver=65536, reflection=16000):
    panel = {"version": "continual-panel-v1", "benchmark": "bigcodebench", "dataset_revision": "authored-transport-v1",
             "provenance": "natural" if natural else "fixture", "tasks": [
                 {"task_id": str(i), "family_id": str(i), "project_id": "", "partition": "development",
                  "public": {"prompt": "Authored fixture: implement solve.", "entry_point": "solve"},
                  "private": {"test": "HOST_ONLY_TRANSPORT_CANARY"}} for i in range(4)]}
    model = {"provider": "bigmodel" if natural else "fixture", "name": "glm-5.3" if natural else "fixture",
             "reasoning_effort": "low", "max_tokens": solver}
    if version == LONG_RESPONSE_VERSION:
        model["transport"] = deepcopy(TRANSPORT)
    kwargs = {"version": version, "method": method, "model": model,
              "train_families": ["0", "1"], "selection_families": ["2", "3"],
              "budget": {"max_metric_calls": 32, "max_reflection_calls": 10, "max_api_calls": 40,
                         "max_reported_tokens": 100000, "max_iterations": 1, "minibatch_size": 2,
                         "solver_max_tokens": solver, "reflection_max_tokens": reflection}}
    return panel, kwargs


def http_harness(monkeypatch, *, method, solver, finish="stop"):
    # SDK classes subclass httpx.Client at import time; import native modules
    # before replacing the constructor with our offline transport factory.
    if method == "skillopt":
        importlib.import_module("skillopt.engine.trainer")
    calls, clients = [], []
    sync_client, async_client = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(provider, "_configuration", lambda *args, **kwargs: (
        "https://open.bigmodel.cn/api/paas/v4/chat/completions", "AUTHORED_NOT_A_SECRET"))

    def handler(request):
        body = json.loads(request.content)
        assert "HOST_ONLY_TRANSPORT_CANARY" not in json.dumps(body)
        calls.append(body)
        solving = body["max_tokens"] == solver
        if solving:
            content = "```python\ndef solve(): return 0\n```" if finish == "stop" else ""
        elif method == "skillopt":
            content = json.dumps({"batch_size": 2, "patch": {"reasoning": "Authored fixture",
                                  "edits": [{"op": "append", "content": "Check empty inputs."}]}})
        else:
            content = "```\nCheck empty inputs.\n```"
        stop = finish if solving else "stop"
        usage = {"prompt_tokens": 10, "completion_tokens": 20}
        if body.get("stream"):
            event = {"model": "glm-5.3", "choices": [{"index": 0, "delta": {"content": content},
                     "finish_reason": stop}], "usage": usage}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode())
        return httpx.Response(200, json={"model": "glm-5.3", "choices": [
            {"message": {"content": content}, "finish_reason": stop}], "usage": usage})

    def sync_factory(**kwargs):
        clients.append(("sync", kwargs))
        return sync_client(transport=httpx.MockTransport(handler), **kwargs)

    def async_factory(**kwargs):
        clients.append(("async", kwargs))
        return async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(provider.httpx, "Client", sync_factory)
    monkeypatch.setattr(provider.httpx, "AsyncClient", async_factory)
    monkeypatch.setattr(backends, "readiness", lambda *args, **kwargs: {"status": "ready"})

    def scorer(benchmark, public, private, prediction, **kwargs):
        unknown = prediction["status"] == "unknown"
        return {"status": "unknown" if unknown else "fail", "score": None if unknown else 0.0,
                "reason": "authored_scorer_not_native_execution", "metrics": {}}

    monkeypatch.setattr(backends, "score", scorer)

    def optimize(**kwargs):
        # Exercise both production callbacks without claiming official GEPA.
        adapter = kwargs["adapter"]
        candidate = kwargs["seed_candidate"]
        adapter.evaluate_rows(kwargs["valset"], candidate)
        adapter.evaluate_rows(kwargs["trainset"], candidate)
        kwargs["reflection_lm"]("Authored optimizer public feedback.")
        candidate = {"skill": "Check empty inputs."}
        adapter.evaluate_rows(kwargs["valset"], candidate)
        return SimpleNamespace(best_candidate=candidate, to_dict=lambda: {"engineering_transport_control": True})

    monkeypatch.setattr(gepa, "official_gepa", lambda source: (SimpleNamespace(optimize=optimize), {}))
    return calls, clients


def run(method, value, panel, root):
    kwargs = {"repo": root}
    if method == "gepa":
        kwargs["gepa_source"] = root / "authored-official-stub"
    return (skillopt if method == "skillopt" else gepa).run_stage(value, panel, root, **kwargs)


def test_legacy_default_manifest_and_reconstruction_are_unchanged():
    panel, kwargs = inputs(version=VERSION, solver=4096, reflection=4096)
    explicit = manifest(panel, **kwargs)
    kwargs.pop("version")
    assert manifest(panel, **kwargs) == explicit
    assert validate_manifest(explicit, panel) == explicit
    assert explicit["version"] == "continual-learning-gepa-v1"
    assert "transport" not in explicit["model"]
    kwargs["model"]["transport"] = deepcopy(TRANSPORT)
    with pytest.raises(ValueError, match="unsupported fields"):
        manifest(panel, **kwargs)


@pytest.mark.parametrize("cap", [1, 8192, 32768, 65536])
@pytest.mark.parametrize("method", ["skillopt", "gepa"])
def test_v2_solver_budgets_and_version_round_trip(cap, method):
    panel, kwargs = inputs(solver=cap, method=method)
    value = manifest(panel, **kwargs)
    assert value["version"] == LONG_RESPONSE_VERSION
    assert validate_manifest(value, panel) == value
    assert value["resume_policy"] == "completed_replay_only_interruption_pending"


@pytest.mark.parametrize("version,key,cap", [
    (VERSION, "solver_max_tokens", 16001), (VERSION, "reflection_max_tokens", 16001),
    (LONG_RESPONSE_VERSION, "solver_max_tokens", 65537),
    (LONG_RESPONSE_VERSION, "reflection_max_tokens", 16001),
    (LONG_RESPONSE_VERSION, "reflection_max_tokens", 16384),
    (LONG_RESPONSE_VERSION, "solver_max_tokens", True),
    (LONG_RESPONSE_VERSION, "solver_max_tokens", 8192.0),
    (LONG_RESPONSE_VERSION, "reflection_max_tokens", 0)])
def test_out_of_protocol_budgets_are_rejected(version, key, cap):
    panel, kwargs = inputs(version=version, solver=4096, reflection=4096)
    kwargs["budget"][key] = cap
    if key == "solver_max_tokens":
        kwargs["model"]["max_tokens"] = cap
    with pytest.raises(ValueError):
        manifest(panel, **kwargs)


@pytest.mark.parametrize("mutation", ["unknown_version", "missing_transport", "wrong_transport", "pjlab", "solver_mismatch"])
def test_invalid_v2_protocol_rejected(mutation):
    panel, kwargs = inputs(natural=True)
    if mutation == "unknown_version":
        kwargs["version"] = "continual-learning-v999"
    elif mutation == "missing_transport":
        kwargs["model"].pop("transport")
    elif mutation == "wrong_transport":
        kwargs["model"]["transport"]["stream"] = False
    elif mutation == "pjlab":
        kwargs["model"]["provider"] = "pjlab"
    else:
        kwargs["model"]["max_tokens"] = 8192
    with pytest.raises(ValueError):
        manifest(panel, **kwargs)


@pytest.mark.parametrize("method", ["skillopt", "gepa"])
@pytest.mark.parametrize("version", [VERSION, LONG_RESPONSE_VERSION])
def test_actual_client_budget_service_cache_and_no_fail_resampling(tmp_path, monkeypatch, version, method):
    solver = 65536 if version == LONG_RESPONSE_VERSION else 4096
    panel, kwargs = inputs(version=version, method=method, natural=True, solver=solver)
    value = manifest(panel, **kwargs)
    calls, clients = http_harness(monkeypatch, method=method, solver=solver)
    result = run(method, value, panel, tmp_path)
    assert result["status"] == "completed", result
    assert result["version"] == version and not result["resume_supported"]
    assert not result["deployment_authorized"]
    assert len(calls) == 7  # Six Solver calls, one optimizer call; no semantic retries.
    assert [call["max_tokens"] for call in calls].count(solver) == 6
    assert [call["max_tokens"] for call in calls].count(16000) == 1
    assert all(call["reasoning_effort"] == "low" and call["thinking"] == {"type": "enabled"} for call in calls)
    service = read_json(tmp_path / "model_service.json", sealed=True)
    if version == LONG_RESPONSE_VERSION:
        assert all(call["stream"] is True for call in calls)
        assert all(options["timeout"].read == 300 for _, options in clients)
        assert service["stream_transport"] == "async-whole-attempt-deadline-v1"
        assert service["stream_max_wall_seconds"] == 1800
        assert service["timeout_seconds"]["read"] == 300
    else:
        assert all("stream" not in call for call in calls)
        assert len(clients) == 1 and clients[0][1]["timeout"].read == 120
        assert "stream" not in service and service["timeout_seconds"]["read"] == 120
    service.pop("record_hash")
    for path in (tmp_path / "calls").glob("*.json"):
        receipt = read_json(path, sealed=True)["receipt"]
        assert receipt["request"]["service"] == service
        assert receipt["request_hash"] == digest(receipt["request"])
    before = (len(calls), len(clients))
    assert run(method, value, panel, tmp_path) == result
    assert before == (len(calls), len(clients))


@pytest.mark.parametrize("method", ["skillopt", "gepa"])
def test_v2_length_remains_unknown_pending_and_replays_without_retry(tmp_path, monkeypatch, method):
    panel, kwargs = inputs(method=method, natural=True)
    value = manifest(panel, **kwargs)
    calls, clients = http_harness(monkeypatch, method=method, solver=65536, finish="length")
    result = run(method, value, panel, tmp_path)
    assert result["status"] == "pending" and result["reason"] == "evaluation_unknown"
    assert result["candidate_skill"] == "" and result["version"] == LONG_RESPONSE_VERSION
    assert len(calls) == 1
    evidence = read_json(next((tmp_path / "evaluations").glob("*.json")), sealed=True)
    assert evidence["score"]["status"] == "unknown" and evidence["score"]["score"] is None
    assert run(method, value, panel, tmp_path) == result
    assert len(calls) == 1


@pytest.mark.parametrize("method", ["skillopt", "gepa"])
def test_v2_started_stage_does_not_resume_or_call_client(tmp_path, monkeypatch, method):
    panel, kwargs = inputs(method=method, natural=True)
    value = manifest(panel, **kwargs)
    calls, clients = http_harness(monkeypatch, method=method, solver=65536)
    write_json(tmp_path / "started.json", seal({"authored_interrupted_fixture": True}))
    result = run(method, value, panel, tmp_path)
    assert result["status"] == "pending" and result["model_calls_submitted"] == 0
    assert not calls and not clients


@pytest.mark.parametrize("mutation", ["transport", "version", "solver"])
def test_changed_protocol_blocked_before_client(tmp_path, monkeypatch, mutation):
    panel, kwargs = inputs(natural=True)
    value = manifest(panel, **kwargs)
    value.pop("record_hash")
    if mutation == "transport":
        value["model"]["transport"]["read_timeout_seconds"] = 600
    elif mutation == "version":
        value["version"] = VERSION
    else:
        value["model"]["max_tokens"] = 8192
    calls, clients = http_harness(monkeypatch, method="skillopt", solver=65536)
    with pytest.raises(ValueError):
        run("skillopt", seal(value), panel, tmp_path)
    assert not calls and not clients


def test_service_forgery_still_rejected_by_unchanged_ledger(tmp_path):
    panel, kwargs = inputs()
    value = manifest(panel, **kwargs)

    class Forged:
        model = "fixture"
        service = {"transport": "expected-fixture-long-stream"}

        def call(self, system, user, kind, key, max_tokens, repeat):
            request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                       "max_tokens": max_tokens, "repeat": repeat, "service": {"transport": "legacy-wrong"}}
            return {"request": request, "request_hash": digest(request), "ok": True,
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "http_attempt_count": 1}

    ledger = Ledger(tmp_path, value, Forged())
    with pytest.raises(ValueError, match="does not bind"):
        ledger.call("solver", "authored", "system", "user", 65536)
    assert ledger.snapshot()["unclosed_calls"] == 1


def test_example_is_unsealed_template_not_ready_manifest():
    value = read_json(Path(__file__).parents[1] / "configs/continual_learning/long_stream_v2.example.json")
    assert value["version"] == LONG_RESPONSE_VERSION
    assert "record_hash" not in value and "panel_hash" not in value
    assert all(name.startswith("REPLACE_") for name in value["train_families"] + value["selection_families"])
    panel, _ = inputs(natural=True, solver=8192, reflection=8192)
    value["train_families"], value["selection_families"] = ["0", "1"], ["2", "3"]
    assert validate_manifest(manifest(panel, **value), panel)["model"]["transport"] == TRANSPORT


def test_v2_official_gepa_fixture_engine_and_replay(tmp_path):
    """Exercise the reviewed official optimizer, still with authored responses."""
    from scripts.run_continual_learning import _fixture_evaluate, _FixtureAPI

    source = Path(os.environ.get("GEPA_OFFICIAL_SOURCE", Path(__file__).parents[1] /
                                 "outputs/continual_eval/baseline_preparation_20260928/gepa"))
    if not source.is_dir() or importlib.util.find_spec("gepa") is None:
        pytest.skip("Optional pinned GEPA not installed; use the dedicated baseline preparation venv")
    panel, kwargs = inputs(method="gepa")
    kwargs["budget"]["max_iterations"] = 2
    value = manifest(panel, **kwargs)
    api = _FixtureAPI("gepa")
    result = gepa.run_stage(value, panel, tmp_path, gepa_source=source,
                            fixture_api=api, fixture_evaluate=_fixture_evaluate)
    assert result["status"] == "completed", result
    assert result["version"] == LONG_RESPONSE_VERSION
    assert result["candidate_skill"] == "Handle empty inputs."
    assert result["evidence_kind"] == "engineering_fixture"
    assert not result["deployment_authorized"]
    receipt = read_json(next((tmp_path / "calls").glob("*.json")), sealed=True)["receipt"]
    assert receipt["request"]["max_tokens"] == 16000
    assert gepa.run_stage(value, panel, tmp_path, gepa_source=source,
                          fixture_api=api, fixture_evaluate=_fixture_evaluate) == result
