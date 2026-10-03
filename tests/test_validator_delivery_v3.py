"""Offline transport regressions; no provider calls or method-effect claims."""

import asyncio
import json

import httpx
import pytest

from skillopt.validator_pilot import api as provider


class SyncEvents(httpx.SyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks, self.error = chunks, error

    def __iter__(self):
        yield from self.chunks
        if self.error:
            raise self.error("PRIVATE_UPSTREAM_EXCEPTION")


class AsyncEvents(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks, self.error = chunks, error

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error("PRIVATE_UPSTREAM_EXCEPTION")


def event(finish="stop", *, content="answer", model="glm-5.3", usage=True):
    body = {"model": model, "choices": [{"index": 0, "delta": {"content": content},
                                          "finish_reason": finish}]}
    if usage:
        body["usage"] = {"prompt_tokens": 10, "completion_tokens": 2}
    return ("data: " + json.dumps(body) + "\n\n").encode()


def client(tmp_path, monkeypatch, replies, *, policy="closed_delivery_error_v3", long=True):
    monkeypatch.setattr(provider, "_configuration", lambda *a, **k: (
        "https://open.bigmodel.cn/api/paas/v4/chat/completions", "FIXTURE_NOT_A_KEY"))
    monkeypatch.setattr(provider.time, "sleep", lambda _: None)
    requests = []
    sync_client, async_client = httpx.Client, httpx.AsyncClient

    def handle(request):
        index = len(requests)
        requests.append(json.loads(request.content))
        chunks, error = replies[min(index, len(replies) - 1)]
        stream = AsyncEvents(chunks, error) if long else SyncEvents(chunks, error)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    monkeypatch.setattr(provider.httpx, "Client", lambda **k: sync_client(transport=httpx.MockTransport(handle), **k))
    monkeypatch.setattr(provider.httpx, "AsyncClient",
                        lambda **k: async_client(transport=httpx.MockTransport(handle), **k))
    api = provider.CachedAPI(tmp_path, tmp_path / "api", provider="bigmodel", stream=True,
                            read_timeout_seconds=300, stream_wall_seconds=3600 if long else None,
                            initial_health_policy="completed_response_v1", delivery_retry_policy=policy)
    return api, requests


@pytest.mark.parametrize("long", [False, True])
@pytest.mark.parametrize("error", [None, httpx.ReadError, httpx.ReadTimeout])
@pytest.mark.parametrize("finish", ["sensitive", "content_filter"])
def test_observed_filter_is_terminal_even_if_stream_does_not_complete(tmp_path, monkeypatch, long, error, finish):
    api, requests = client(tmp_path, monkeypatch,
                           [([event(finish, content="PRIVATE_FILTERED_CONTENT")], error),
                            ([event(), b"data: [DONE]\n\n"], None)], long=long)
    with api:
        receipt = api.call("system", "user", "fixture", "0", max_tokens=100)
        assert not receipt["ok"]
        assert receipt["error_type"] == "provider_content_filter"
        assert receipt["finish_reason"] == finish
        assert receipt["stream_complete"] is False
        assert receipt["response"] == ""
        assert len(requests) == receipt["http_attempt_count"] == 1
        assert receipt["usage"] == receipt["attempts"][0]["usage"] == {"prompt_tokens": 10, "completion_tokens": 2}
        assert "PRIVATE_" not in json.dumps(receipt)
        with pytest.raises(RuntimeError, match="health barrier"):
            api.call("system", "different", "fixture", "1", max_tokens=100)
        assert len(requests) == 1


@pytest.mark.parametrize("policy,attempts,ok", [
    ("closed_delivery_error_v2", 2, True),
    ("closed_delivery_error_v3", 1, False),
])
@pytest.mark.parametrize("error", [None, httpx.ReadError, httpx.ReadTimeout, asyncio.TimeoutError])
def test_old_incomplete_filtered_stream_behavior_is_preserved(tmp_path, monkeypatch, policy, attempts, ok, error):
    api, requests = client(tmp_path, monkeypatch,
                           [([event("content_filter")], error), ([event(), b"data: [DONE]\n\n"], None)], policy=policy)
    with api:
        receipt = api.call("system", "user", "fixture", "0", max_tokens=100)
    assert len(requests) == receipt["http_attempt_count"] == attempts
    assert receipt["ok"] is ok


def test_filter_remains_terminal_after_malformed_later_event(tmp_path, monkeypatch):
    api, requests = client(tmp_path, monkeypatch,
                           [([event("content_filter", content="PRIVATE_CONTENT"), b"data: invalid JSON\n\n"], None)])
    with api:
        receipt = api.call("s", "u", "fixture", "0", max_tokens=100)
    assert receipt["error_type"] == "provider_content_filter" and not receipt["ok"]
    assert receipt["response"] == "" and receipt["stream_complete"] is False
    assert len(requests) == 1 and "PRIVATE_" not in json.dumps(receipt)


def test_whole_attempt_deadline_retains_previously_observed_filter(tmp_path, monkeypatch):
    real_wait_for = asyncio.wait_for

    async def deadline(awaitable, *, timeout):
        assert timeout == 3600
        return await real_wait_for(awaitable, timeout=0.02)

    async def stalled_stream(self):
        for chunk in self.chunks:
            yield chunk
        await asyncio.sleep(60)

    monkeypatch.setattr(provider.asyncio, "wait_for", deadline)
    monkeypatch.setattr(AsyncEvents, "__aiter__", stalled_stream)
    api, requests = client(tmp_path, monkeypatch,
                           [([event("sensitive", content="PRIVATE_CONTENT")], None)])
    with api:
        receipt = api.call("s", "u", "fixture", "0", max_tokens=100)
    assert receipt["error_type"] == "provider_content_filter" and not receipt["ok"]
    assert receipt["stream_complete"] is False and receipt["response"] == ""
    assert receipt["attempts"][0]["usage"] == {"prompt_tokens": 10, "completion_tokens": 2}
    assert len(requests) == 1 and "PRIVATE_" not in json.dumps(receipt)


@pytest.mark.parametrize("finish", ["sensitive", "content_filter"])
@pytest.mark.parametrize("long", [False, True])
def test_complete_filtered_response_releases_health_for_different_tasks(tmp_path, monkeypatch, finish, long):
    api, requests = client(tmp_path, monkeypatch,
                           [([event(finish, content="PRIVATE_FILTERED_CONTENT"), b"data: [DONE]\n\n"], None),
                            ([event(), b"data: [DONE]\n\n"], None)], long=long)
    with api:
        rows = api.parallel(["0", "1"], lambda key: api.call("s", "u", "fixture", key, max_tokens=100), "fixture")
        assert not rows[0]["ok"] and rows[0]["response"] == ""
        assert rows[0]["error_type"] == "provider_content_filter"
        assert rows[1]["ok"]
        assert len(requests) == 2
        assert api.call("s", "u", "fixture", "0", max_tokens=100) == rows[0]
        assert len(requests) == 2


def test_old_complete_filter_still_blocks_health(tmp_path, monkeypatch):
    api, requests = client(tmp_path, monkeypatch,
                           [([event("sensitive"), b"data: [DONE]\n\n"], None)], policy="closed_delivery_error_v2")
    with api:
        receipt = api.call("s", "u", "fixture", "0", max_tokens=100)
        assert not receipt["ok"]
        with pytest.raises(RuntimeError, match="health barrier"):
            api.call("s", "u", "fixture", "1", max_tokens=100)
    assert len(requests) == 1


def test_wrong_model_filter_never_passes_health(tmp_path, monkeypatch):
    api, requests = client(tmp_path, monkeypatch,
                           [([event("sensitive", model="other"), b"data: [DONE]\n\n"], None)])
    with api:
        receipt = api.call("s", "u", "fixture", "0", max_tokens=100)
        assert not receipt["ok"]
        with pytest.raises(RuntimeError, match="health barrier"):
            api.call("s", "u", "fixture", "1", max_tokens=100)
    assert len(requests) == 1


@pytest.mark.parametrize("finish,error", [(None, None), ("network_error", None), (None, httpx.ReadError)])
def test_normal_delivery_retries_and_per_attempt_usage_remain_available(tmp_path, monkeypatch, finish, error):
    first = [event(finish, content="PARTIAL")]
    if finish == "network_error":
        first.append(b"data: [DONE]\n\n")
    api, requests = client(tmp_path, monkeypatch,
                           [(first, error),
                            ([event(), b"data: [DONE]\n\n"], None)])
    with api:
        receipt = api.call("s", "u", "fixture", "0", max_tokens=100)
    assert receipt["ok"] and receipt["response"] == "answer"
    assert len(requests) == receipt["http_attempt_count"] == 2
    assert receipt["attempts"][0]["usage"] == {"prompt_tokens": 10, "completion_tokens": 2}


def test_resumed_complete_filter_releases_health_without_reissuing_it(tmp_path, monkeypatch):
    api, requests = client(tmp_path, monkeypatch,
                           [([event("sensitive"), b"data: [DONE]\n\n"], None),
                            ([event(), b"data: [DONE]\n\n"], None)])
    with api:
        filtered = api.call("s", "u", "fixture", "0", max_tokens=100)
        # A new process starts unchecked; replaying a cached completed receipt
        # may prove connectivity but must not resubmit the filtered request.
        api._health = "unchecked"
        assert api.call("s", "u", "fixture", "0", max_tokens=100) == filtered
        assert api._health == "ready" and len(requests) == 1
        assert api.call("s", "u", "fixture", "1", max_tokens=100)["ok"]
        assert len(requests) == 2
