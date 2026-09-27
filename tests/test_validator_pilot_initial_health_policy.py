"""Opt-in transport readiness, never task success; all HTTP is synthetic."""
from __future__ import annotations

import json

import httpx
import pytest

from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot import api as module
from tests.test_validator_pilot_api import install_client, sse_event, stream_response

POLICY = "completed_response_v1"


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "dotenv_values", lambda _: {
        "BIGMODEL_CHAT_URL": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "BIGMODEL_API_KEY": "SYNTHETIC_TEST_CREDENTIAL_NOT_REAL",
        "BIGMODEL_MODEL": "glm-5.3"})
    return tmp_path


def completion(*, finish="stop", content="ok", done=True, model="glm-5.3"):
    event = sse_event(content, finish=finish,
                      usage={"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10})
    event = event.replace(b'"model": "glm-5.3"', ('"model": "' + model + '"').encode())
    return stream_response([event] + ([b"data: [DONE]\n\n"] if done else []))


def client(root, name="run", **kwargs):
    return module.CachedAPI(root, root / name, provider="bigmodel", stream=True,
                            reasoning_effort="low", **kwargs)


def call(api, key="first"):
    return api.call("system", "user", "health-policy-fixture", key, max_tokens=100)


def test_legacy_service_and_failure_barrier_unchanged(configured, monkeypatch):
    requests = []
    install_client(monkeypatch, lambda request: requests.append(request) or completion(finish="length", content=""))
    with client(configured) as api:
        assert "initial_health_policy" not in api.service
        failed = call(api)
        assert not failed["ok"] and failed["error_type"] == "truncated_content"
        assert call(api) == failed
        with pytest.raises(RuntimeError, match="health barrier"):
            call(api, "next")
    assert len(requests) == 1


def test_only_service_policy_changes_not_model_payload(configured, monkeypatch):
    payloads = []
    install_client(monkeypatch, lambda request: payloads.append(json.loads(request.content)) or completion())
    with client(configured, "legacy") as api:
        legacy = call(api)
    with client(configured, "opt-in", initial_health_policy=POLICY) as api:
        opt_in = call(api)
    old, new = legacy["request"]["service"], dict(opt_in["request"]["service"])
    assert new.pop("initial_health_policy") == POLICY
    assert new == old and payloads[0] == payloads[1]
    assert "initial_health_policy" not in payloads[1]
    assert opt_in["request_hash"] != legacy["request_hash"]


@pytest.mark.parametrize("finish,content,error", [
    ("length", "", "truncated_content"),
    ("length", "partial", "truncated_content"),
    ("stop", "", "empty_content"),
])
def test_task_failure_stays_terminal_but_transport_allows_next_request(configured, monkeypatch, finish, content, error):
    requests = []
    def handler(request):
        requests.append(request)
        return completion(finish=finish, content=content) if len(requests) == 1 else completion()
    install_client(monkeypatch, handler)
    with client(configured, initial_health_policy=POLICY) as api:
        failed = call(api)
        assert not failed["ok"] and failed["error_type"] == error
        assert failed["http_attempt_count"] == 1 and failed["usage"]["total_tokens"] == 10
        assert failed["response"] == content and failed["stream_complete"] is True
        assert call(api) == failed
        assert call(api, "next")["ok"]
        terminal = configured / "run/calls" / (failed["request_hash"] + ".json")
        assert json.loads(terminal.read_text()) == failed
    assert len(requests) == 2


@pytest.mark.parametrize("first_ok", [False, True])
def test_transport_ready_cached_record_no_retry_or_new_probe(configured, monkeypatch, first_ok):
    requests = []
    def handler(request):
        requests.append(request)
        return completion() if first_ok or len(requests) > 1 else completion(finish="length", content="")
    install_client(monkeypatch, handler)
    with client(configured, initial_health_policy=POLICY) as api:
        original = call(api)
    assert len(requests) == 1
    with client(configured, initial_health_policy=POLICY) as api:
        assert call(api) == original
        assert api._health == "ready"
        assert len(requests) == 1
        assert call(api, "new")["ok"]
    assert len(requests) == 2


@pytest.mark.parametrize("kind,expected", [
    ("auth", "http_status"), ("model", "unexpected_response_model"),
    ("incomplete", "incomplete_stream"), ("schema", "invalid_response_schema"),
    ("tool_calls", "unexpected_finish_reason"),
])
def test_transport_or_protocol_failures_still_block(configured, monkeypatch, kind, expected):
    requests = []
    def handler(request):
        requests.append(request)
        if kind == "auth":
            return httpx.Response(401)
        if kind == "model":
            return completion(model="wrong-model", finish="length", content="")
        if kind == "incomplete":
            return completion(done=False, finish="length", content="")
        if kind == "schema":
            return stream_response([b"data: NOT_JSON\n\n"])
        return completion(finish="tool_calls")
    install_client(monkeypatch, handler)
    with client(configured, initial_health_policy=POLICY) as api:
        failed = call(api)
        assert not failed["ok"] and failed["error_type"] == expected
        assert call(api) == failed
        with pytest.raises(RuntimeError, match="health barrier"):
            call(api, "blocked")
    assert len(requests) == 1


def test_parallel_raw_failed_receipt_retained_without_false_batch_barrier(configured, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return completion(finish="length", content="") if len(requests) == 1 else completion()
    install_client(monkeypatch, handler)
    with client(configured, initial_health_policy=POLICY) as api:
        records = api.parallel(["first", "next", "last"], lambda key: call(api, key), "fixture")
    assert [r["ok"] for r in records] == [False, True, True]
    assert records[0]["error_type"] == "truncated_content"
    assert len(requests) == 3


def test_bounded_calls_preserve_failed_receipt_and_all_reserved_calls_finish(configured, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return completion(finish="length", content="") if len(requests) == 1 else completion()
    install_client(monkeypatch, handler)
    with client(configured, initial_health_policy=POLICY) as api:
        calls = BoundedCalls(api, configured / "budget", module.digest("fixture-protocol"), 2)
        failed = calls.call("same system", "one", "public-initial")
        passed = calls.call("same system", "two", "public-initial")
        assert not failed["ok"] and passed["ok"]
        assert calls.call("same system", "one", "public-initial") == failed
        stats = calls.accounting()
        assert stats["reserved_logical_requests"] == stats["terminal_logical_requests"] == 2
        assert stats["terminal_failures"] == 1 and stats["http_attempts"] == 2
    assert len(requests) == 2


@pytest.mark.parametrize("policy", [None, "", "relaxed", True, [], {}])
def test_unknown_health_policy_rejected_before_configuration(configured, monkeypatch, policy):
    monkeypatch.setattr(module, "_configuration", lambda *a, **k: pytest.fail("Invalid policy reached configuration"))
    with pytest.raises(ValueError, match="health policy"):
        client(configured, initial_health_policy=policy)


def test_policy_change_cannot_resume_same_service_directory(configured, monkeypatch):
    install_client(monkeypatch, lambda _: completion())
    with client(configured):
        pass
    with pytest.raises(ValueError, match="Immutable"):
        client(configured, initial_health_policy=POLICY)
