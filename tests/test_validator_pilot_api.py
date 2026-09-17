"""No-network tests of the dedicated PJLAB client and bounded load pilot."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from scripts import validator_pilot_preflight as preflight
from skillopt.validator_pilot import api as module


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "dotenv_values", lambda path: {
        "PJLAB_BASE_URL": "https://token.pjlab.org.cn/v1",
        "PJLAB_API_KEY": "SYNTHETIC_TEST_CREDENTIAL_NOT_REAL",
        "PJLAB_MODEL": "glm-5.3"})
    return tmp_path


def response(text='{"valid":true}', *, status=200, finish="stop", headers=None):
    return httpx.Response(status, json={"choices": [{"message": {"content": text}, "finish_reason": finish}],
                                       "model": "glm-5.3", "usage": {"prompt_tokens": 3,
                                       "completion_tokens": 7, "total_tokens": 10}}, headers=headers)


def install_client(monkeypatch, handler):
    real_client = httpx.Client
    configurations = []
    def client(**kwargs):
        configurations.append(kwargs)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(module.httpx, "Client", client)
    return configurations


def call(api, key="a"):
    return api.call("system", "user", "unit_test", key, max_tokens=100)


def test_direct_client_cache_and_credential_free_artifacts(configured, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return response()
    configurations = install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "run") as api:
        first = call(api)
        assert call(api) == first
        second = call(api, "b")
        assert first["ok"] and second["ok"]
        assert first["http_attempt_count"] == 1
    assert len(requests) == 2
    assert configurations[0]["trust_env"] is False
    assert configurations[0]["follow_redirects"] is False
    payload = json.loads(requests[0].content)
    assert payload == {"model": "glm-5.3", "temperature": 0, "max_tokens": 100,
                       "messages": [{"role": "system", "content": "system"},
                                    {"role": "user", "content": "user"}]}
    assert requests[0].url == "https://token.pjlab.org.cn/v1/chat/completions"
    for path in (configured / "run").rglob("*.json"):
        assert "SYNTHETIC_TEST_CREDENTIAL" not in path.read_text()
        assert "Authorization" not in path.read_text()


@pytest.mark.parametrize("field,value", [
    ("PJLAB_BASE_URL", "https://other.invalid/v1"),
    ("PJLAB_BASE_URL", "http://token.pjlab.org.cn/v1"),
    ("PJLAB_BASE_URL", "https://token.pjlab.org.cn/v1?credential=anything"),
    ("PJLAB_BASE_URL", "https://user:pass@token.pjlab.org.cn/v1"),
    ("PJLAB_BASE_URL", "https://token.pjlab.org.cn:444/v1"),
    ("PJLAB_BASE_URL", "https://token.pjlab.org.cn/wrong"),
    ("PJLAB_MODEL", "other-model"), ("PJLAB_API_KEY", ""),
])
def test_rejects_other_services_models_and_missing_keys(configured, monkeypatch, field, value):
    values = module.dotenv_values(None)
    values[field] = value
    monkeypatch.setattr(module, "dotenv_values", lambda _: values)
    with pytest.raises(ValueError):
        module.CachedAPI(configured, configured / "run")


@pytest.mark.parametrize("workers", [0, 13, True, 2.5])
def test_worker_limits(configured, workers):
    with pytest.raises(ValueError):
        module.CachedAPI(configured, configured / "run", workers=workers)


def test_429_retry_explicit_and_bounded(configured, monkeypatch):
    counts, sleeps = [], []
    def handler(request):
        counts.append(1)
        return response(status=429, headers={"retry-after": "900"}) if len(counts) < 3 else response()
    install_client(monkeypatch, handler)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    with module.CachedAPI(configured, configured / "run") as api:
        result = call(api)
    assert result["ok"] and result["http_attempt_count"] == 3
    assert [row["status"] for row in result["attempts"]] == [429, 429, 200]
    assert sleeps == [10, 10]


def test_terminal_failure_cached_and_health_barrier(configured, monkeypatch):
    counts = []
    def handler(request):
        counts.append(1)
        return response(status=401)
    install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "run") as api:
        failed = call(api)
        assert not failed["ok"] and failed["error_type"] == "http_status"
        assert call(api) == failed
        with pytest.raises(RuntimeError, match="health barrier"):
            call(api, "different")
    assert len(counts) == 1


def test_timeout_retry_no_exception_secrets(configured, monkeypatch):
    sleeps = []
    def handler(request):
        raise httpx.ReadTimeout("SENSITIVE_EXCEPTION_WITH_HEADER", request=request)
    install_client(monkeypatch, handler)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    with module.CachedAPI(configured, configured / "run") as api:
        result = call(api)
    assert result["error_type"] == "timeout" and result["http_attempt_count"] == 3
    assert sleeps == [2, 4]
    assert "SENSITIVE_EXCEPTION" not in json.dumps(result)


@pytest.mark.parametrize("text,finish,error", [
    ("", "stop", "empty_content"), ("partial", "length", "truncated_content"),
    (None, "stop", "empty_content"), ("x", "tool_calls", "unexpected_finish_reason"),
])
def test_invalid_generation_is_not_scored_success(configured, monkeypatch, text, finish, error):
    install_client(monkeypatch, lambda _: response(text, finish=finish))
    with module.CachedAPI(configured, configured / "run") as api:
        result = call(api)
    assert not result["ok"] and result["error_type"] == error
    assert result["usage"]["total_tokens"] == 10
    assert result["http_attempt_count"] == 1


def test_malformed_schema_sanitized(configured, monkeypatch):
    install_client(monkeypatch, lambda _: httpx.Response(200, json={"error": "PRIVATE_BODY"}))
    with module.CachedAPI(configured, configured / "run") as api:
        result = call(api)
    assert result["error_type"] == "invalid_response_schema"
    assert "PRIVATE_BODY" not in json.dumps(result)


def test_duplicate_concurrent_calls_send_once(configured, monkeypatch):
    counts = []
    def handler(request):
        counts.append(1)
        return response()
    install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "run") as api:
        with ThreadPoolExecutor(max_workers=8) as pool:
            records = list(pool.map(lambda _: call(api), range(16)))
    assert len(counts) == 1 and all(record == records[0] for record in records)


def test_first_real_request_is_serial_health_barrier(configured, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    active, counts = [], []
    def handler(request):
        counts.append(1)
        if len(counts) == 1:
            entered.set()
            assert release.wait(2)
        else:
            active.append(True)
        return response()
    install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "run") as api:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(call, api, "first")
            assert entered.wait(2)
            second = pool.submit(call, api, "second")
            time.sleep(.01)
            assert not active
            release.set()
            assert first.result()["ok"] and second.result()["ok"]


def test_parallel_preserves_order(configured, monkeypatch):
    install_client(monkeypatch, lambda _: response())
    with module.CachedAPI(configured, configured / "run") as api:
        records = api.parallel(["c", "a", "b"], lambda key: call(api, key), "unit")
    assert [record["request"]["key"] for record in records] == ["c", "a", "b"]


def test_parallel_first_failure_stops_fanout(configured, monkeypatch):
    counts = []
    install_client(monkeypatch, lambda _: counts.append(1) or response(status=401))
    with module.CachedAPI(configured, configured / "run") as api:
        with pytest.raises(RuntimeError, match="batch health barrier"):
            api.parallel(["a", "b", "c"], lambda key: call(api, key), "unit")
    assert len(counts) == 1


def test_cache_tampering_fails_closed(configured, monkeypatch):
    install_client(monkeypatch, lambda _: response())
    with module.CachedAPI(configured, configured / "run") as api:
        result = call(api)
        path = configured / "run" / "calls" / (result["request_hash"] + ".json")
        result["request"]["system"] = "altered"
        path.write_text(json.dumps(result))
        with pytest.raises(ValueError, match="integrity"):
            call(api)


def test_immutable_write_and_conflict(tmp_path):
    path = tmp_path / "artifact.json"
    module.write_immutable_json(path, {"a": 1})
    module.write_immutable_json(path, {"a": 1})
    with pytest.raises(ValueError, match="Immutable"):
        module.write_immutable_json(path, {"a": 2})
    assert json.loads(path.read_text()) == {"a": 1}
    assert not list(tmp_path.glob(".pending-*"))


def test_preflight_bounded_and_one_level_margin(configured, monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        text = payload["messages"][1]["content"]
        index = int(text.split('"probe": ')[1].split("}")[0])
        return response(json.dumps({"valid": True, "reason": "empty sum stays zero", "probe": index}))
    install_client(monkeypatch, handler)
    monkeypatch.setattr(preflight.time, "sleep", lambda _: None)
    result = preflight.run(configured, configured / "run")
    assert result["logical_calls"] == result["http_attempts"] == 51
    assert result["stable_levels"] == [1, 4, 8, 12]
    assert result["recommended_workers"] == 8
    assert result["terminal_errors"] == 0
    assert preflight.run(configured, configured / "run") == result


def test_preflight_stops_even_when_retry_recovers(configured, monkeypatch):
    counts = []
    def handler(request):
        counts.append(1)
        if len(counts) == 3:
            return response(status=429)
        text = json.loads(request.content)["messages"][1]["content"]
        index = int(text.split('"probe": ')[1].split("}")[0])
        return response(json.dumps({"valid": True, "reason": "ok", "probe": index}))
    install_client(monkeypatch, handler)
    monkeypatch.setattr(preflight.time, "sleep", lambda _: None)
    result = preflight.run(configured, configured / "run")
    assert result["logical_calls"] == 3 and result["http_attempts"] == 4
    assert result["recommended_workers"] is None
    assert result["stopped_reason"] == "request_or_response_error"


def test_preflight_json_validation_failure_stops(configured, monkeypatch):
    install_client(monkeypatch, lambda _: response("not json"))
    result = preflight.run(configured, configured / "run")
    assert result["logical_calls"] == 1
    assert result["status"] == "failed" and result["recommended_workers"] is None


def sse_event(content=None, *, finish=None, usage=None, reasoning=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    value = {"model": "glm-5.3", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage is not None:
        value["usage"] = usage
    return ("data: " + json.dumps(value, ensure_ascii=False) + "\n\n").encode()


class StreamBytes(httpx.SyncByteStream):
    def __init__(self, chunks, fail=None):
        self.chunks, self.fail = chunks, fail

    def __iter__(self):
        yield from self.chunks
        if self.fail:
            raise self.fail


def stream_response(chunks, *, fail=None, status=200):
    return httpx.Response(status, headers={"content-type": "text/event-stream"},
                          stream=StreamBytes(chunks, fail))


def test_stream_collects_content_usage_and_ignores_reasoning(configured, monkeypatch):
    requests = []
    body = [sse_event(reasoning="PRIVATE_REASONING_NOT_AN_ANSWER"), sse_event('{"ready":'),
            sse_event("true}"), sse_event(finish="stop"),
            b'data: {"model":"glm-5.3","choices":[],"usage":{"prompt_tokens":3,"completion_tokens":9,"total_tokens":12}}\n\n',
            b"data: [DONE]\n\n"]
    def handler(request):
        requests.append(json.loads(request.content))
        return stream_response(body)
    install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "stream", stream=True) as api:
        result = call(api)
        assert call(api) == result
        assert api.service["stream"] is True
    assert result["ok"] and result["stream_complete"] and result["finish_reason"] == "stop"
    assert result["response"] == '{"ready":true}'
    assert result["usage"]["total_tokens"] == 12
    assert result["stream_event_count"] == 5
    assert "PRIVATE_REASONING" not in json.dumps(result)
    assert requests[0]["stream"] is True and requests[0]["stream_options"] == {"include_usage": True}
    assert len(requests) == 1


def test_stream_http_byte_boundaries_unicode_and_sse_multiline(configured, monkeypatch):
    text = (b": heartbeat\r\n\r\n" + sse_event("中文")
            + b'data: {"choices":\n'
            + b'data: [{"index":0,"delta":{"content":" result"},"finish_reason":"stop"}]}\n\n'
            + b"data: [DONE]")
    chunks = [text[index:index + 1] for index in range(len(text))]
    install_client(monkeypatch, lambda _: stream_response(chunks))
    with module.CachedAPI(configured, configured / "stream", stream=True) as api:
        result = call(api)
    assert result["ok"] and result["response"] == "中文 result"


@pytest.mark.parametrize("parts,error", [
    ([sse_event("partial"), sse_event(finish="stop")], "incomplete_stream"),
    ([sse_event("partial"), b"data: [DONE]\n\n"], "missing_stream_finish"),
    ([sse_event("partial", finish="length"), b"data: [DONE]\n\n"], "truncated_content"),
    ([sse_event("", finish="stop"), b"data: [DONE]\n\n"], "empty_content"),
    ([b'data: {"error":{"message":"PRIVATE_ERROR_BODY"}}\n\n'], "upstream_stream_error"),
    ([b"data: NOT_JSON\n\n"], "invalid_response_schema"),
    ([sse_event("x", finish="stop"), sse_event("after"), b"data: [DONE]\n\n"], "content_after_stream_finish"),
])
def test_stream_invalid_completions_fail_without_silent_retry(configured, monkeypatch, parts, error):
    install_client(monkeypatch, lambda _: stream_response(parts))
    with module.CachedAPI(configured, configured / "stream", stream=True) as api:
        result = call(api)
    assert not result["ok"] and result["error_type"] == error
    assert result["http_attempt_count"] == 1
    assert "PRIVATE_ERROR_BODY" not in json.dumps(result)


def test_stream_partial_timeout_retry_never_concatenates_attempts(configured, monkeypatch):
    requests, sleeps = [], []
    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return stream_response([sse_event("WRONG_PARTIAL_PREFIX")],
                                   fail=httpx.ReadTimeout("PRIVATE_ERROR", request=request))
        return stream_response([sse_event("complete", finish="stop"), b"data: [DONE]\n\n"])
    install_client(monkeypatch, handler)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    with module.CachedAPI(configured, configured / "stream", stream=True) as api:
        result = call(api)
    assert result["ok"] and result["response"] == "complete"
    assert result["http_attempt_count"] == 2 and sleeps == [2]
    assert result["attempts"][0]["error_type"] == "timeout"
    assert "WRONG_PARTIAL_PREFIX" not in json.dumps(result) and "PRIVATE_ERROR" not in json.dumps(result)


def test_stream_plain_json_error_body_not_accepted(configured, monkeypatch):
    install_client(monkeypatch, lambda _: httpx.Response(200, json={"error": "PRIVATE_ERROR_BODY"}))
    with module.CachedAPI(configured, configured / "stream", stream=True) as api:
        result = call(api)
    assert not result["ok"] and result["error_type"] == "unexpected_stream_content_type"
    assert "PRIVATE_ERROR_BODY" not in json.dumps(result)


def test_stream_http_504_retries_are_explicit_and_terminal_cached(configured, monkeypatch):
    requests, sleeps = [], []
    def handler(request):
        requests.append(request)
        return httpx.Response(504, json={"error": "PRIVATE_GATEWAY_BODY"})
    install_client(monkeypatch, handler)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)
    with module.CachedAPI(configured, configured / "stream", stream=True) as api:
        result = call(api)
        assert call(api) == result
    assert not result["ok"] and result["http_attempt_count"] == 3
    assert [r["status"] for r in result["attempts"]] == [504, 504, 504]
    assert len(requests) == 3 and sleeps == [2, 4]
    assert "PRIVATE_GATEWAY_BODY" not in json.dumps(result)


def test_stream_mode_change_requires_new_cache_directory(configured, monkeypatch):
    install_client(monkeypatch, lambda _: response())
    with module.CachedAPI(configured, configured / "run"):
        pass
    with pytest.raises(ValueError, match="Immutable"):
        module.CachedAPI(configured, configured / "run", stream=True)


def test_stream_content_limit(configured, monkeypatch):
    install_client(monkeypatch, lambda _: stream_response([sse_event("x" * 200001)]))
    with module.CachedAPI(configured, configured / "stream", stream=True) as api:
        result = call(api)
    assert not result["ok"] and result["error_type"] == "stream_content_limit"


def test_stream_bool_required(configured):
    with pytest.raises(ValueError, match="explicit boolean"):
        module.CachedAPI(configured, configured / "stream", stream="true")


@pytest.mark.parametrize("effort", ["low", "high", "max"])
@pytest.mark.parametrize("stream", [False, True])
def test_reasoning_effort_explicit_passthrough_and_cache_metadata(configured, monkeypatch, effort, stream):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return (stream_response([sse_event("answer", finish="stop"), b"data: [DONE]\n\n"])
                if stream else response("answer"))
    install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "run", stream=stream, reasoning_effort=effort) as api:
        result = call(api)
        assert result["ok"]
        assert api.service["reasoning_effort"] == effort
    assert requests[0]["reasoning_effort"] == effort
    assert "thinking" not in requests[0]
    assert result["request"]["service"]["reasoning_effort"] == effort


@pytest.mark.parametrize("effort", ["disabled", "none", "medium", "minimal", "LOW", "", True, 0, []])
def test_invalid_reasoning_effort_rejected_before_configuration(configured, effort):
    with pytest.raises(ValueError, match="reasoning_effort"):
        module.CachedAPI(configured, configured / "run", reasoning_effort=effort)


def test_none_reasoning_effort_keeps_old_service_and_payload(configured, monkeypatch):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return response("answer")
    install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "run", reasoning_effort=None) as api:
        result = call(api)
    assert "reasoning_effort" not in requests[0]
    assert "reasoning_effort" not in result["request"]["service"]


def test_reasoning_effort_change_requires_new_cache_directory(configured, monkeypatch):
    install_client(monkeypatch, lambda _: response())
    with module.CachedAPI(configured, configured / "run", stream=True):
        pass
    with pytest.raises(ValueError, match="Immutable"):
        module.CachedAPI(configured, configured / "run", stream=True, reasoning_effort="low")


@pytest.mark.parametrize("stream", [False, True])
def test_empty_content_with_length_is_reported_as_truncation(configured, monkeypatch, stream):
    def handler(_):
        return (stream_response([sse_event(reasoning="thinking only", finish="length"), b"data: [DONE]\n\n"])
                if stream else response("", finish="length"))
    install_client(monkeypatch, handler)
    with module.CachedAPI(configured, configured / "run", stream=stream) as api:
        result = call(api)
    assert not result["ok"] and result["error_type"] == "truncated_content"
    assert result["finish_reason"] == "length" and result["response"] == ""
