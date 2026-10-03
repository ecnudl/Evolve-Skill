"""Direct, bounded provider calls with immutable, credential-free request caches.

The historical PJLAB configuration remains the default.  The optional
``provider="bigmodel"`` path is an explicit new-run adapter for local GLM-5.3
experiments; it never changes the identity of an existing PJLAB run.
"""

from __future__ import annotations

import asyncio
import codecs
import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

T = TypeVar("T")
R = TypeVar("R")
MODEL = "glm-5.3"
PROVIDER_HOST = "token.pjlab.org.cn"
BIGMODEL_HOST = "open.bigmodel.cn"
PJLAB_HTTP_PROXY_HOST = "httpproxy-headless.kubebrain.svc.pjlab.local"
PJLAB_MAX_TOKENS = 16_000
BIGMODEL_GLM53_STANDARD_MAX_TOKENS = 65_536
BIGMODEL_GLM53_MAX_TOKENS = 131_072
LONG_STREAM_MAX_BYTES = 32_000_000


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def write_immutable_json(path: Path, value: Any) -> None:
    """Atomically publish once; allow byte-equivalent JSON on resume."""
    # Dataclass tuples serialize as arrays; compare their JSON representation on resume.
    value = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError("Immutable artifact differs; use a new output directory")
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".pending-", suffix=".json", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if json.loads(path.read_text(encoding="utf-8")) != value:
                raise ValueError("Concurrent artifact differs; do not share output directories") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _configuration(repo: Path, model: str, provider: str = "pjlab") -> tuple[str, str]:
    # Read only the provider-specific entries; never mutate process environment.
    values = dotenv_values(Path(repo) / ".env")
    if provider == "bigmodel":
        endpoint = str(values.get("BIGMODEL_CHAT_URL") or "").strip()
        key = str(values.get("BIGMODEL_API_KEY") or "").strip()
        configured_model = str(values.get("BIGMODEL_MODEL") or MODEL).strip()
        if model != MODEL or configured_model != MODEL:
            raise ValueError("BigModel adapter requires BIGMODEL_MODEL=glm-5.3")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or parsed.hostname != BIGMODEL_HOST
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.port not in (None, 443)
                or parsed.path.rstrip("/") != "/api/paas/v4/chat/completions"):
            raise ValueError("BIGMODEL_CHAT_URL must be the approved HTTPS BigModel chat endpoint")
        if not key:
            raise ValueError("BIGMODEL_API_KEY is missing from the repository .env")
        return endpoint, key
    if provider != "pjlab":
        raise ValueError("provider must be pjlab or bigmodel")
    base = str(values.get("PJLAB_BASE_URL") or "").strip()
    key = str(values.get("PJLAB_API_KEY") or "").strip()
    configured_model = str(values.get("PJLAB_MODEL") or MODEL).strip()
    if model != MODEL or configured_model != MODEL:
        raise ValueError("This frozen pilot requires PJLAB_MODEL=glm-5.3")
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or parsed.hostname != PROVIDER_HOST
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.port not in (None, 443) or parsed.path.rstrip("/") != "/v1"):
        raise ValueError("PJLAB_BASE_URL must be the approved HTTPS PJLAB /v1 endpoint")
    if not key:
        raise ValueError("PJLAB_API_KEY is missing from the repository .env")
    return base.rstrip("/") + "/chat/completions", key


class _StreamResponseError(ValueError):
    """Only a fixed diagnostic category; never carry upstream error text."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


class _StreamAccumulator:
    """Shared SSE validation; reasoning text is never accumulated as an answer."""

    def __init__(self, *, max_stream_chars: int = 8_000_000,
                 diagnostic: dict[str, Any] | None = None) -> None:
        self.parts: list[str] = []
        self.event_lines: list[str] = []
        self.usage: dict[str, Any] = {}
        self.model: str | None = None
        self.finish: str | None = None
        self.done = False
        self.events = self.text_chars = self.stream_chars = 0
        self.max_stream_chars = max_stream_chars
        # Opt-in metadata survives a read error / deadline cancellation without
        # retaining partial content, reasoning, or exception strings.
        self.diagnostic = diagnostic
        self.observed_filter: str | None = None

    def consume(self) -> None:
        try:
            self._consume()
        finally:
            if self.diagnostic is not None:
                self.diagnostic["stream_observation"] = {
                    "returned_model": self.model, "usage": dict(self.usage),
                    "finish_reason": self.observed_filter or self.finish,
                    "stream_complete": self.done, "stream_event_count": self.events,
                    "stream_characters": self.stream_chars,
                }
                if self.observed_filter is not None:
                    self.diagnostic["observed_filter"] = self.observed_filter

    def _consume(self) -> None:
        if not self.event_lines:
            return
        payload = "\n".join(self.event_lines)
        self.event_lines.clear()
        if payload.strip() == "[DONE]":
            self.done = True
            return
        body = json.loads(payload)
        if not isinstance(body, dict):
            raise _StreamResponseError("invalid_stream_event")
        if "error" in body:
            raise _StreamResponseError("upstream_stream_error")
        self.events += 1
        if body.get("model") is not None:
            if not isinstance(body["model"], str) or (self.model is not None and body["model"] != self.model):
                raise _StreamResponseError("inconsistent_stream_model")
            self.model = body["model"]
        if body.get("usage") is not None:
            if not isinstance(body["usage"], dict):
                raise _StreamResponseError("invalid_stream_usage")
            self.usage = body["usage"]
        choices = body.get("choices", [])
        if not isinstance(choices, list) or len(choices) > 1:
            raise _StreamResponseError("invalid_stream_choices")
        if choices:
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                raise _StreamResponseError("invalid_stream_choice")
            incoming_finish = choice.get("finish_reason")
            if self.diagnostic is not None and incoming_finish in ("sensitive", "content_filter"):
                # Once observed, a filter is terminal even if content/another
                # event is malformed or the connection fails before [DONE].
                self.observed_filter = incoming_finish
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise _StreamResponseError("invalid_stream_delta")
            content = delta.get("content")
            # reasoning_content is intentionally neither used as answer nor persisted.
            if content is not None:
                if not isinstance(content, str):
                    raise _StreamResponseError("invalid_stream_content")
                if self.finish is not None and content:
                    raise _StreamResponseError("content_after_stream_finish")
                self.parts.append(content)
                self.text_chars += len(content)
                if self.text_chars > 200_000:
                    raise _StreamResponseError("stream_content_limit")
            if incoming_finish is not None:
                if (not isinstance(incoming_finish, str)
                        or (self.finish is not None and self.finish != incoming_finish)):
                    raise _StreamResponseError("inconsistent_stream_finish")
                self.finish = incoming_finish

    def feed_line(self, line: str) -> None:
        self.stream_chars += len(line)
        if self.stream_chars > self.max_stream_chars:
            raise _StreamResponseError("stream_size_limit")
        if not line:
            self.consume()
        elif line.startswith("data:"):
            self.event_lines.append(line[5:].removeprefix(" "))
        # SSE comments, id, retry and event-name fields are not model payload.

    def result(self) -> dict[str, Any]:
        if not self.done and self.event_lines:
            self.consume()
        return {"choices": [{"message": {"content": "".join(self.parts)}, "finish_reason": self.finish}],
                "usage": self.usage, "model": self.model, "_stream_complete": self.done,
                "_stream_event_count": self.events, "_stream_chars": self.stream_chars}


def _stream_body(response: httpx.Response, *, diagnostic: dict[str, Any] | None = None) -> dict[str, Any]:
    """Historical stream path: retain its default timing/cache contract."""
    if "text/event-stream" not in response.headers.get("content-type", "").casefold():
        raise _StreamResponseError("unexpected_stream_content_type")
    started = time.monotonic()
    accumulator = _StreamAccumulator(diagnostic=diagnostic)

    for line in response.iter_lines():
        if time.monotonic() - started > 300:
            raise _StreamResponseError("stream_wall_time_limit")
        accumulator.feed_line(line)
        if accumulator.done:
            break
    return accumulator.result()


def long_stream_service(service: dict[str, Any], *, read_timeout_seconds: int,
                        stream_wall_seconds: int) -> dict[str, Any]:
    """Pure protocol overlay shared by the client and frozen-run preparation.

    This is opt-in. It never changes the historical default service identity.
    The deadline covers each attempt including connection, headers and body;
    bounded retries remain separately recorded and may each incur model cost.
    """
    if type(read_timeout_seconds) is not int or not 120 <= read_timeout_seconds <= 1200:
        raise ValueError("read_timeout_seconds must be an integer in [120, 1200]")
    if type(stream_wall_seconds) is not int or not 300 <= stream_wall_seconds <= 3600:
        raise ValueError("stream_wall_seconds must be an integer in [300, 3600]")
    if not isinstance(service, dict) or not isinstance(service.get("timeout_seconds"), dict):
        raise ValueError("Expected a client service with timeout_seconds")
    value = copy.deepcopy(service)
    value["timeout_seconds"]["read"] = read_timeout_seconds
    value.update(stream=True, stream_options={"include_usage": True},
                 stream_max_wall_seconds=stream_wall_seconds,
                 stream_max_characters=LONG_STREAM_MAX_BYTES, stream_max_content_characters=200_000,
                 stream_max_bytes=LONG_STREAM_MAX_BYTES, stream_completion_rule="[DONE] plus finish_reason=stop",
                 stream_transport="async-whole-attempt-deadline-v1",
                 stream_deadline_scope="per_attempt_connect_headers_body")
    return value


async def _long_stream_body(response: httpx.Response, *,
                            diagnostic: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bound bytes even before an event/line ends; honor split UTF-8 and CRLF."""
    if "text/event-stream" not in response.headers.get("content-type", "").casefold():
        raise _StreamResponseError("unexpected_stream_content_type")
    accumulator = _StreamAccumulator(max_stream_chars=LONG_STREAM_MAX_BYTES, diagnostic=diagnostic)
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    byte_count = 0

    def feed(text: str, *, final: bool = False) -> None:
        nonlocal buffer
        buffer += text
        cursor = 0
        for match in re.finditer(r"\r\n|\r|\n", buffer):
            # A terminal CR may be the first half of a split CRLF delimiter.
            if match.group() == "\r" and match.end() == len(buffer) and not final:
                break
            accumulator.feed_line(buffer[cursor:match.start()])
            cursor = match.end()
            if accumulator.done:
                break
        buffer = buffer[cursor:]
        if final and buffer and not accumulator.done:
            accumulator.feed_line(buffer)
            buffer = ""

    async for chunk in response.aiter_bytes():
        byte_count += len(chunk)
        if byte_count > LONG_STREAM_MAX_BYTES:
            raise _StreamResponseError("stream_size_limit")
        feed(decoder.decode(chunk))
        if accumulator.done:
            break
    if not accumulator.done:
        feed(decoder.decode(b"", final=True), final=True)
    return accumulator.result()


def _timeout_subtype(error: httpx.TimeoutException) -> str:
    # Fixed names, never str(error), which can include credentials or bodies.
    for kind, label in ((httpx.ConnectTimeout, "connect"), (httpx.ReadTimeout, "read"),
                        (httpx.WriteTimeout, "write"), (httpx.PoolTimeout, "pool")):
        if isinstance(error, kind):
            return label
    return "unspecified"


# Opt-in closed delivery retries. v2 adds incomplete HTTP 200 streams to v1;
# v3 makes an observed filter terminal, including subsequently broken streams.
HARDENED_DELIVERY_RETRY_POLICY = "closed_delivery_error_v3"
DELIVERY_RETRY_POLICIES = ("closed_network_error_v1", "closed_delivery_error_v2", HARDENED_DELIVERY_RETRY_POLICY)


class CachedAPI:
    """One-process thread-safe cache, health barrier and explicit bounded retries.

    A cached terminal failure is returned unchanged, never silently retried. A new
    process must not share this output directory while requests are in flight.
    Successful resumed records satisfy the initial health barrier without a new
    probe; an actual new batch should use its explicit first connectivity call.
    """

    def __init__(self, repo: Path, root: Path, model: str = MODEL, workers: int = 8, *, stream: bool = False,
                 reasoning_effort: str | None = None, provider: str = "pjlab", proxy: str | None = None,
                 initial_health_policy: str = "legacy_success_only", read_timeout_seconds: int = 120,
                 stream_wall_seconds: int | None = None, delivery_retry_policy: str | None = None):
        if delivery_retry_policy not in (None, *DELIVERY_RETRY_POLICIES):
            raise ValueError("Unknown delivery retry policy")
        if delivery_retry_policy is not None and (provider != "bigmodel" or model != MODEL or not stream):
            raise ValueError("Delivery retries require streaming BigModel glm-5.3")
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 12:
            raise ValueError("workers must be an integer in [1, 12]")
        if type(stream) is not bool:
            raise ValueError("stream must be an explicit boolean")
        if type(read_timeout_seconds) is not int or not 120 <= read_timeout_seconds <= 1200:
            raise ValueError("read_timeout_seconds must be an integer in [120, 1200]")
        if stream_wall_seconds is not None:
            if not stream:
                raise ValueError("stream_wall_seconds requires stream=True")
            if type(stream_wall_seconds) is not int or not 300 <= stream_wall_seconds <= 3600:
                raise ValueError("stream_wall_seconds must be an integer in [300, 3600]")
        if type(initial_health_policy) is not str or initial_health_policy not in {"legacy_success_only", "completed_response_v1"}:
            raise ValueError("Unknown initial API health policy")
        if reasoning_effort is not None and (
                not isinstance(reasoning_effort, str) or reasoning_effort not in {"low", "high", "max"}):
            raise ValueError("GLM-5.3 reasoning_effort must be None, low, high, or max")
        if proxy is not None:
            valid_proxy = False
            if provider == "bigmodel" and type(proxy) is str and proxy == proxy.strip():
                try:
                    parsed_proxy = urlsplit(proxy)
                    valid_proxy = (
                        parsed_proxy.scheme == "http"
                        and (parsed_proxy.hostname in {"127.0.0.1", "::1"}
                             or (parsed_proxy.hostname == PJLAB_HTTP_PROXY_HOST and parsed_proxy.port == 3128))
                        and parsed_proxy.port is not None and 1 <= parsed_proxy.port <= 65535
                        and parsed_proxy.username is None and parsed_proxy.password is None
                        and not parsed_proxy.query and not parsed_proxy.fragment
                        and parsed_proxy.path in {"", "/"})
                except ValueError:
                    pass
            if not valid_proxy:
                raise ValueError("An explicit proxy requires BigModel and a credential-free loopback HTTP endpoint "
                                 "or the approved PJLAB gateway on port 3128")
        endpoint, api_key = _configuration(Path(repo), model, provider=provider)
        self.root, self.model, self.workers = Path(root), model, workers
        self.provider = provider
        self.stream = stream
        self.stream_wall_seconds = stream_wall_seconds
        self.reasoning_effort = reasoning_effort
        self.initial_health_policy = initial_health_policy
        host = PROVIDER_HOST if provider == "pjlab" else BIGMODEL_HOST
        path = "/v1/chat/completions" if provider == "pjlab" else "/api/paas/v4/chat/completions"
        self.service = {
            "provider": "PJLAB" if provider == "pjlab" else "BIGMODEL",
            "host": host, "path": path,
            "model": model, "temperature": 0, "trust_env": False,
            "follow_redirects": False, "generation_seed": "not sent",
            "timeout_seconds": {"connect": 20, "read": read_timeout_seconds, "write": 30, "pool": 20},
            "max_retries": 2, "retry_statuses": [429, 500, 502, 503, 504],
            "retry_backoff_seconds": [2, 4], "max_retry_after_seconds": 10,
            "protocol": ("pjlab-validator-pilot-v1" if provider == "pjlab"
                         else "bigmodel-glm53-validator-pilot-v1"),
        }
        if stream:
            self.service.update(stream=True, stream_options={"include_usage": True},
                                stream_max_wall_seconds=300, stream_max_characters=8_000_000,
                                stream_max_content_characters=200_000,
                                stream_completion_rule="[DONE] plus finish_reason=stop")
        if stream_wall_seconds is not None:
            self.service = long_stream_service(self.service, read_timeout_seconds=read_timeout_seconds,
                                               stream_wall_seconds=stream_wall_seconds)
        if reasoning_effort is not None:
            self.service["reasoning_effort"] = reasoning_effort
        if provider == "bigmodel":
            self.service["thinking"] = {"type": "enabled"}
            self.service["returned_model_rule"] = "exact_requested_model"
        if proxy is not None:
            self.service["proxy"] = proxy
        # The legacy default retains byte-identical historical request/cache
        # identities. Only an explicitly new protocol opts into this policy.
        if initial_health_policy != "legacy_success_only":
            self.service["initial_health_policy"] = initial_health_policy
        if delivery_retry_policy is not None:
            self.service["delivery_retry_policy"] = delivery_retry_policy
        write_immutable_json(self.root / "service.json", self.service)
        self._endpoint = endpoint
        # These private construction options are never serialized. New long
        # streams use one async client per attempt (independent event loops).
        self._client_options = {
            "headers": {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            "trust_env": False, "follow_redirects": False,
            "timeout": httpx.Timeout(read_timeout_seconds, connect=20, write=30, pool=20),
            "limits": httpx.Limits(max_connections=12, max_keepalive_connections=12),
            **({"proxy": proxy} if proxy is not None else {}),
        }
        self._client = httpx.Client(**self._client_options)
        self._health = "unchecked"
        self._health_lock = threading.Lock()
        self._locks_lock = threading.Lock()
        self._request_locks: dict[str, threading.Lock] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CachedAPI:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _initial_ready(self, record: dict[str, Any]) -> bool:
        """Task-budget failure is not necessarily a failed API connection.

        This changes only the initial network barrier, never delivery status,
        retries, output budgets or the persisted terminal response. Wrong
        models, incomplete streams and malformed responses remain blocking.
        """
        if record.get("ok") is True:
            return True
        return (self.initial_health_policy == "completed_response_v1"
                and record.get("status") == 200
                and record.get("returned_model") == self.model
                and (not self.stream or record.get("stream_complete") is True)
                and ((record.get("error_type") == "truncated_content" and record.get("finish_reason") == "length")
                     or (record.get("error_type") == "empty_content" and record.get("finish_reason") == "stop")
                     or (self.service.get("delivery_retry_policy") == HARDENED_DELIVERY_RETRY_POLICY
                         and record.get("error_type") == "provider_content_filter"
                         and record.get("finish_reason") in {"sensitive", "content_filter"})))

    def call(self, system: str, user: str, kind: str, key: str,
             max_tokens: int = 6000, repeat: int = 0) -> dict[str, Any]:
        if not all(isinstance(item, str) for item in (system, user, kind, key)):
            raise ValueError("system, user, kind and key must be strings")
        token_limit = (BIGMODEL_GLM53_MAX_TOKENS
                       if self.provider == "bigmodel" and self.model == MODEL else PJLAB_MAX_TOKENS)
        if (isinstance(max_tokens, bool) or not isinstance(max_tokens, int)
                or not 1 <= max_tokens <= token_limit or not isinstance(repeat, int) or repeat < 0):
            raise ValueError("Invalid token budget or repeat index")
        if max_tokens > BIGMODEL_GLM53_STANDARD_MAX_TOKENS and (
                self.provider != "bigmodel" or self.model != MODEL
                or not self.stream or self.stream_wall_seconds != 3600):
            # Explicit one-hour whole-attempt transport is required for the
            # diagnostic extended budget. Normal evaluation/learning protocols
            # retain their independent 65536-token ceiling. Existing service
            # identity and request shapes at <=65536 remain unchanged.
            raise ValueError("Extended token budgets require BigModel glm-5.3 streaming with stream_wall_seconds=3600")
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        identifier = digest(request)
        with self._locks_lock:
            request_lock = self._request_locks.setdefault(identifier, threading.Lock())
        with request_lock:
            path = self.root / "calls" / (identifier + ".json")
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("request_hash") != identifier or record.get("request") != request:
                    raise ValueError("Frozen request cache failed integrity check")
                if self.initial_health_policy != "legacy_success_only" and self._initial_ready(record):
                    with self._health_lock:
                        if self._health == "unchecked":
                            self._health = "ready"
                return record
            # All first real callers queue here until the first actual response.
            with self._health_lock:
                if self._health == "failed":
                    raise RuntimeError("PJLAB initial health barrier failed; no further requests sent")
                if self._health == "unchecked":
                    record = self._perform(request, identifier)
                    write_immutable_json(path, record)
                    self._health = "ready" if self._initial_ready(record) else "failed"
                    return record
            record = self._perform(request, identifier)
            write_immutable_json(path, record)
            return record

    async def _long_stream_request(self, payload: dict[str, Any], diagnostic: dict[str, Any]) -> tuple[int, Any, Any]:
        """Cancel an entire HTTP attempt, including a stalled/no-newline body.

        httpx's read timeout is an idle timeout, not a total deadline. wait_for
        is supported by Python 3.10 and also covers headers/connect; cancellation
        unwinds both async context managers before returning a terminal failure.
        """
        async def request() -> tuple[int, Any, Any]:
            async with httpx.AsyncClient(**self._client_options) as client:
                diagnostic["timeout_phase"] = "connect_or_headers"
                async with client.stream("POST", self._endpoint, json=payload) as response:
                    diagnostic["status"] = response.status_code
                    diagnostic["timeout_phase"] = "body"
                    if response.status_code == 200:
                        body = (await _long_stream_body(response, diagnostic=diagnostic)
                                if self.service.get("delivery_retry_policy") == HARDENED_DELIVERY_RETRY_POLICY
                                else await _long_stream_body(response))
                    else:
                        body = None
                    return response.status_code, response.headers, body

        return await asyncio.wait_for(request(), timeout=self.stream_wall_seconds)

    def _perform(self, request: dict[str, Any], identifier: str) -> dict[str, Any]:
        start = time.monotonic()
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": request["system"]},
            {"role": "user", "content": request["user"]}],
            "temperature": 0, "max_tokens": request["max_tokens"]}
        if self.stream:
            payload.update(stream=True, stream_options={"include_usage": True})
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.provider == "bigmodel":
            # GLM-5.3 always enables thinking; omitting this field is not
            # equivalent to the frozen PJLAB request contract.
            payload["thinking"] = {"type": "enabled"}
        attempts: list[dict[str, Any]] = []
        hardened_delivery = self.service.get("delivery_retry_policy") == HARDENED_DELIVERY_RETRY_POLICY
        for attempt in range(self.service["max_retries"] + 1):
            # Never concatenate a previous failed attempt's partial response into a retry.
            outcome: dict[str, Any] = {"ok": False, "response": "", "usage": {},
                                      "finish_reason": None, "error_type": None, "status": None}
            attempt_start = time.monotonic()
            status, retry_after, retryable, error_type = None, 0.0, False, None
            diagnostic: dict[str, Any] = {}
            try:
                if self.stream_wall_seconds is not None:
                    # CachedAPI remains a synchronous worker API. Reject use in
                    # a caller's running async loop before creating a coroutine.
                    try:
                        asyncio.get_running_loop()
                    except RuntimeError:
                        pass
                    else:
                        raise _StreamResponseError("sync_client_in_async_loop")
                    status, headers, body = asyncio.run(self._long_stream_request(payload, diagnostic))
                elif self.stream:
                    with self._client.stream("POST", self._endpoint, json=payload) as response:
                        status = response.status_code
                        headers = response.headers
                        if status == 200:
                            body = (_stream_body(response, diagnostic=diagnostic)
                                    if hardened_delivery else _stream_body(response))
                        else:
                            body = None
                else:
                    response = self._client.post(self._endpoint, json=payload)
                    status = response.status_code
                    headers = response.headers
                    body = response.json() if status == 200 else None
                if status != 200:
                    error_type = "http_status"
                    retryable = status in self.service["retry_statuses"]
                    try:
                        retry_after = max(0, min(10, float(headers.get("retry-after", "0"))))
                    except (ValueError, TypeError):
                        retry_after = 0
                else:
                    choice = body["choices"][0]
                    content = choice["message"].get("content")
                    finish = choice.get("finish_reason")
                    usage = body.get("usage") or {}
                    if not isinstance(usage, dict):
                        raise ValueError("Invalid usage schema")
                    outcome.update(usage=usage, finish_reason=finish,
                                   response=content if isinstance(content, str) else "",
                                   returned_model=body.get("model"))
                    if self.stream:
                        outcome.update(stream_complete=body["_stream_complete"],
                                       stream_event_count=body["_stream_event_count"],
                                       stream_characters=body["_stream_chars"])
                    if self.provider == "bigmodel" and body.get("model") != self.model:
                        error_type = "unexpected_response_model"
                    elif self.stream and not body["_stream_complete"]:
                        error_type = "incomplete_stream"
                        # V2/V3: an HTTP 200 stream that ended before its
                        # completion marker is an undelivered response, never
                        # an answer. Retry it within the same frozen bound.
                        retryable = self.service.get("delivery_retry_policy") in {
                            "closed_delivery_error_v2", HARDENED_DELIVERY_RETRY_POLICY}
                    elif (finish == "network_error"
                          and self.service.get("delivery_retry_policy") in DELIVERY_RETRY_POLICIES):
                        # The provider can terminate an otherwise complete HTTP
                        # 200 stream with a transport error. Retry only this
                        # named delivery state, never filters or wrong answers.
                        error_type, retryable = "provider_network_error", True
                    elif (finish in {"sensitive", "content_filter"}
                          and self.service.get("delivery_retry_policy") in DELIVERY_RETRY_POLICIES):
                        error_type = "provider_content_filter"
                    elif finish == "length":
                        error_type = "truncated_content"
                    elif not isinstance(content, str) or not content.strip():
                        error_type = "empty_content"
                    elif finish in ("content_filter", "tool_calls", "function_call"):
                        error_type = "unexpected_finish_reason"
                    elif self.stream and finish != "stop":
                        error_type = "missing_stream_finish"
                    else:
                        outcome["ok"] = True
            except httpx.TimeoutException as error:
                error_type, retryable = "timeout", True
                diagnostic["timeout_subtype"] = _timeout_subtype(error)
                diagnostic.setdefault("timeout_phase", "request")
            except asyncio.TimeoutError:
                error_type, retryable = "timeout", True
                diagnostic["timeout_subtype"] = "wall"
                diagnostic.setdefault("timeout_phase", "request")
            except httpx.TransportError:
                error_type, retryable = "transport_error", True
            except _StreamResponseError as error:
                error_type = error.category
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                error_type = "invalid_response_schema"
            except Exception:
                # Never serialize exception text: it can embed request headers or keys.
                error_type = "unexpected_client_error"
            if hardened_delivery:
                # These fields are emitted by our parser, not copied from a
                # provider error payload. In particular no partial answer is
                # recovered after a failed attempt.
                observation = diagnostic.get("stream_observation", {})
                outcome.update(observation)
                if diagnostic.get("observed_filter") in {"sensitive", "content_filter"}:
                    error_type, retryable = "provider_content_filter", False
                    outcome.update(ok=False, response="", finish_reason=diagnostic["observed_filter"])
            status = status if status is not None else diagnostic.get("status")
            # Store only fixed classifications. Partial answers and reasoning
            # from failed attempts never become a successful final response.
            timeout_info = ({name: diagnostic[name] for name in ("timeout_subtype", "timeout_phase")}
                            if error_type == "timeout" else {})
            attempts.append({"attempt": attempt + 1, "ok": outcome["ok"], "status": status,
                             "error_type": error_type, "wall_seconds": time.monotonic() - attempt_start,
                             **timeout_info})
            if self.service.get("delivery_retry_policy") in DELIVERY_RETRY_POLICIES:
                # Preserve reported usage even on a failed provider attempt.
                # Empty usage remains unknown, not a zero-cost HTTP request.
                attempts[-1]["usage"] = dict(outcome.get("usage", {}))
            outcome.update(error_type=error_type, status=status, **timeout_info)
            if outcome["ok"] or not retryable or attempt == self.service["max_retries"]:
                break
            delay = max(self.service["retry_backoff_seconds"][attempt], retry_after)
            attempts[-1]["backoff_seconds"] = delay
            time.sleep(delay)
        return {"request_hash": identifier, "request": request, **outcome,
                "wall_seconds": time.monotonic() - start, "attempts": attempts,
                "http_attempt_count": len(attempts)}

    def parallel(self, jobs: Iterable[T], fn: Callable[[T], R], label: str) -> list[R]:
        """Preserve order; first job completes before any fan-out in this batch."""
        items = list(jobs)
        if not items:
            return []
        first = fn(items[0])
        if isinstance(first, dict) and first.get("ok") is False and not self._initial_ready(first):
            raise RuntimeError("PJLAB batch health barrier failed; remaining jobs were not submitted")
        if len(items) == 1:
            return [first]
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="pjlab-pilot") as pool:
            rest = list(pool.map(fn, items[1:]))
        return [first, *rest]
