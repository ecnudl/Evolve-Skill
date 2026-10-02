"""Offline v2 launch contracts; authored metadata and HTTP MockTransport only.

Tests exercising the natural launch branch deliberately label authored metadata
as natural inside a temporary directory. They are not natural model runs or
method-effect evidence. No credential file, network, or native container is used.
"""
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import cli, runner
from skillopt.continual_eval.core import (
    BENCHMARKS,
    LONG_RESPONSE_VERSION,
    freeze_plan,
    load_checkpoint,
    load_plan,
    read_json,
    validate_config,
    write_json,
)
from skillopt.continual_eval.fixtures import fixture_config, fixture_panel
from skillopt.validator_pilot import api as provider

TRANSPORT = {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
             "initial_health_policy": "completed_response_v1"}


def configuration(tmp_path, *, version=LONG_RESPONSE_VERSION):
    value = fixture_config(tmp_path / "fixture-data")
    value["version"] = version
    if version == LONG_RESPONSE_VERSION:
        value["model"].update(max_tokens=65536, transport=deepcopy(TRANSPORT))
    return value


def mock_launch_config(tmp_path, *, version=LONG_RESPONSE_VERSION):
    value = configuration(tmp_path, version=version)
    panel = fixture_panel("searchqa")
    panel["provenance"] = "natural"  # Test-only launch shape; see module docstring.
    panel["tasks"][0]["partition"] = "development"
    panel["tasks"][0]["private"]["answers"] = ["PRIVATE_ORACLE_SENTINEL"]
    second = deepcopy(panel["tasks"][0])
    second.update(task_id="fixture-second", family_id="fixture-family-second")
    panel["tasks"].append(second)
    panel_path = tmp_path / "authored-panel.json"
    write_json(panel_path, panel)
    value.update(partition="development", panels={name: str(panel_path) if name == "searchqa" else None
                                                  for name in BENCHMARKS})
    value["model"].update(provider="bigmodel", name="glm-5.3")
    return value


def http_clients(monkeypatch, *, finish="stop", response="<answer>wrong</answer>"):
    """Use the actual CachedAPI parsing/request path with a local HTTP transport."""
    calls, clients = [], []
    sync_client, async_client = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(provider, "_configuration", lambda *args, **kwargs: (
        "https://open.bigmodel.cn/api/paas/v4/chat/completions", "AUTHORED_NOT_A_SECRET"))

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert "PRIVATE_ORACLE_SENTINEL" not in json.dumps(body)
        usage = {"prompt_tokens": 3, "completion_tokens": 10}
        if body.get("stream"):
            event = {"model": "glm-5.3", "choices": [{"index": 0,
                     "delta": {"content": response}, "finish_reason": finish}], "usage": usage}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode())
        return httpx.Response(200, json={"model": "glm-5.3", "choices": [
            {"message": {"content": response}, "finish_reason": finish}], "usage": usage})

    def sync_factory(**kwargs):
        clients.append(("sync", kwargs))
        return sync_client(transport=httpx.MockTransport(handler), **kwargs)

    def async_factory(**kwargs):
        clients.append(("async", kwargs))
        return async_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(provider.httpx, "Client", sync_factory)
    monkeypatch.setattr(provider.httpx, "AsyncClient", async_factory)
    return calls, clients


def test_v1_keeps_old_schema_and_budget(tmp_path):
    value = configuration(tmp_path, version="continual-eval-v1")
    assert validate_config(value) == value
    value["model"]["transport"] = deepcopy(TRANSPORT)
    with pytest.raises(ValueError, match="unsupported fields"):
        validate_config(value)
    value["model"].pop("transport")
    value["model"]["max_tokens"] = 16001
    with pytest.raises(ValueError, match="output budget"):
        validate_config(value)


@pytest.mark.parametrize("cap", [1, 8192, 32768, 65536])
def test_v2_explicit_token_budgets_are_valid(tmp_path, cap):
    value = configuration(tmp_path)
    value["model"]["max_tokens"] = cap
    assert validate_config(value) == value


@pytest.mark.parametrize("cap", [0, 65537, True, 8192.0])
def test_v2_invalid_budget_is_rejected(tmp_path, cap):
    value = configuration(tmp_path)
    value["model"]["max_tokens"] = cap
    with pytest.raises(ValueError, match="output budget"):
        validate_config(value)


@pytest.mark.parametrize("field,value", [("stream", False), ("stream", 1),
    ("read_timeout_seconds", 300.0), ("read_timeout_seconds", 600),
    ("stream_wall_seconds", 300), ("initial_health_policy", "legacy_success_only")])
def test_v2_transport_is_a_frozen_not_arbitrary_profile(tmp_path, field, value):
    config = configuration(tmp_path)
    config["model"]["transport"][field] = value
    with pytest.raises(ValueError, match="v2 transport"):
        validate_config(config)


@pytest.mark.parametrize("kind", ["missing", "extra_secret", "extra_key", "pjlab"])
def test_v2_rejects_unbound_transport_or_provider(tmp_path, kind):
    value = configuration(tmp_path)
    if kind == "missing":
        value["model"].pop("transport")
    elif kind == "pjlab":
        value["model"].update(provider="pjlab", name="glm-5.3")
    else:
        value["model"]["transport"]["api_key" if kind == "extra_secret" else "other"] = "not_allowed"
    with pytest.raises(ValueError):
        validate_config(value)


@pytest.mark.parametrize("version", ["continual-eval-v1", LONG_RESPONSE_VERSION])
def test_plan_checkpoint_and_readiness_keep_declared_version(tmp_path, version):
    value = configuration(tmp_path, version=version)
    root = tmp_path / "run"
    plan = freeze_plan(value, root)
    checkpoint = load_checkpoint(root, "no_skill", "h0", 0, plan)
    assert plan["version"] == version and checkpoint["version"] == version + "-checkpoint"
    assert load_plan(root) == plan
    assert cli.readiness(value)["version"] == version


@pytest.mark.parametrize("finish,expected", [("stop", "fail"), ("length", "unknown")])
def test_v2_real_request_path_budget_service_and_no_semantic_resampling(tmp_path, monkeypatch, finish, expected):
    calls, clients = http_clients(monkeypatch, finish=finish, response="" if finish == "length" else "<answer>wrong</answer>")
    root = tmp_path / "run"
    plan = freeze_plan(mock_launch_config(tmp_path), root)
    kwargs = dict(method="no_skill", history="h0", stage=0, benchmark="searchqa", repo=tmp_path, workers=1)
    first = runner.generate(root, **kwargs)
    assert first["new_positions"] == 2 and len(calls) == 2
    assert all(call["max_tokens"] == 65536 and call["stream"] is True for call in calls)
    assert all(call["thinking"] == {"type": "enabled"} for call in calls)
    assert all(options["timeout"].read == 300 for _, options in clients)
    assert sum(kind == "async" for kind, _ in clients) == 2
    service = read_json(root / "model_service.json", sealed=True)
    assert service["stream"] and service["stream_max_wall_seconds"] == 1800
    assert service["stream_transport"] == "async-whole-attempt-deadline-v1"
    assert service["timeout_seconds"]["read"] == 300
    assert service["initial_health_policy"] == "completed_response_v1"
    original = {str(path): path.read_bytes() for path in (root / "predictions").rglob("*.json")}
    runner.score_checkpoint(root, method="no_skill", history="h0", stage=0, benchmark="searchqa")
    assert {read_json(path, sealed=True)["status"] for path in (root / "host_only/scores").glob("*.json")} == {expected}
    clients_before = len(clients)
    assert runner.generate(root, **kwargs)["new_positions"] == 0
    assert len(calls) == 2 and len(clients) == clients_before
    assert original == {str(path): path.read_bytes() for path in (root / "predictions").rglob("*.json")}
    assert runner.report(root)["run_accounting"]["logical_calls"] == 2
    assert plan["version"] == LONG_RESPONSE_VERSION


def test_v1_actual_client_still_nonstream_read120(tmp_path, monkeypatch):
    calls, clients = http_clients(monkeypatch)
    root = tmp_path / "run"
    freeze_plan(mock_launch_config(tmp_path, version="continual-eval-v1"), root)
    runner.generate(root, method="no_skill", history="h0", stage=0, benchmark="searchqa", repo=tmp_path)
    service = read_json(root / "model_service.json", sealed=True)
    assert "stream" not in service and "stream_transport" not in service
    assert service["timeout_seconds"]["read"] == 120
    assert all(call["max_tokens"] == 4096 and "stream" not in call for call in calls)
    assert len(clients) == 1 and clients[0][0] == "sync"


def test_changed_frozen_v2_transport_blocks_before_client(tmp_path, monkeypatch):
    root = tmp_path / "run"
    freeze_plan(configuration(tmp_path), root)
    path = root / "plan.json"
    plan = read_json(path, sealed=True)
    plan.pop("record_hash")
    plan["config"]["model"]["transport"]["read_timeout_seconds"] = 600
    path.write_text(json.dumps(seal(plan)))  # Deliberately authored test corruption.
    with pytest.raises(ValueError, match="v2 transport"):
        load_plan(root)


def test_v2_open_position_still_cannot_be_resampled(tmp_path):
    root = tmp_path / "run"
    freeze_plan(configuration(tmp_path), root)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        runner.generate(root, method="no_skill", history="h0", stage=0, benchmark="searchqa",
                        fixture_solve=interrupted)
    with pytest.raises(ValueError, match="Interrupted position"):
        runner.generate(root, method="no_skill", history="h0", stage=0, benchmark="searchqa",
                        fixture_solve=interrupted)


def test_example_is_explicit_development_only_and_not_a_ready_baseline():
    path = Path(__file__).parents[1] / "configs/continual_eval/noskill_long_stream_v2.example.json"
    value = validate_config(read_json(path))
    assert value["version"] == LONG_RESPONSE_VERSION
    assert value["partition"] == "development" and value["methods"] == ["no_skill"]
    assert all(path is None for path in value["panels"].values())
