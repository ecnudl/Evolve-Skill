"""Direct, bounded PJLAB calls with immutable, credential-free request caches."""

from __future__ import annotations

import hashlib
import json
import os
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


def _configuration(repo: Path, model: str) -> tuple[str, str]:
    # Read only the three dedicated PJLAB entries; never mutate process environment.
    values = dotenv_values(Path(repo) / ".env")
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


def _stream_body(response: httpx.Response) -> dict[str, Any]:
    """Parse SSE event boundaries independently of HTTP byte chunk boundaries."""
    if "text/event-stream" not in response.headers.get("content-type", "").casefold():
        raise _StreamResponseError("unexpected_stream_content_type")
    started = time.monotonic()
    parts: list[str] = []
    event_lines: list[str] = []
    usage: dict[str, Any] = {}
    model, finish = None, None
    done, events, text_chars, stream_chars = False, 0, 0, 0

    def consume() -> None:
        nonlocal usage, model, finish, done, events, text_chars
        if not event_lines:
            return
        payload = "\n".join(event_lines)
        event_lines.clear()
        if payload.strip() == "[DONE]":
            done = True
            return
        body = json.loads(payload)
        if not isinstance(body, dict):
            raise _StreamResponseError("invalid_stream_event")
        if "error" in body:
            raise _StreamResponseError("upstream_stream_error")
        events += 1
        if body.get("model") is not None:
            if not isinstance(body["model"], str) or (model is not None and body["model"] != model):
                raise _StreamResponseError("inconsistent_stream_model")
            model = body["model"]
        if body.get("usage") is not None:
            if not isinstance(body["usage"], dict):
                raise _StreamResponseError("invalid_stream_usage")
            usage = body["usage"]
        choices = body.get("choices", [])
        if not isinstance(choices, list) or len(choices) > 1:
            raise _StreamResponseError("invalid_stream_choices")
        if choices:
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                raise _StreamResponseError("invalid_stream_choice")
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise _StreamResponseError("invalid_stream_delta")
            content = delta.get("content")
            # reasoning_content is intentionally neither used as answer nor persisted.
            if content is not None:
                if not isinstance(content, str):
                    raise _StreamResponseError("invalid_stream_content")
                if finish is not None and content:
                    raise _StreamResponseError("content_after_stream_finish")
                parts.append(content)
                text_chars += len(content)
                if text_chars > 200_000:
                    raise _StreamResponseError("stream_content_limit")
            incoming_finish = choice.get("finish_reason")
            if incoming_finish is not None:
                if not isinstance(incoming_finish, str) or (finish is not None and finish != incoming_finish):
                    raise _StreamResponseError("inconsistent_stream_finish")
                finish = incoming_finish

    for line in response.iter_lines():
        stream_chars += len(line)
        if stream_chars > 8_000_000:
            raise _StreamResponseError("stream_size_limit")
        if time.monotonic() - started > 300:
            raise _StreamResponseError("stream_wall_time_limit")
        if not line:
            consume()
            if done:
                break
        elif line.startswith("data:"):
            event_lines.append(line[5:].removeprefix(" "))
        # SSE comments, id, retry and event-name fields are not model payload.
    if not done and event_lines:
        consume()
    return {"choices": [{"message": {"content": "".join(parts)}, "finish_reason": finish}],
            "usage": usage, "model": model, "_stream_complete": done,
            "_stream_event_count": events, "_stream_chars": stream_chars}


class CachedAPI:
    """One-process thread-safe cache, health barrier and explicit bounded retries.

    A cached terminal failure is returned unchanged, never silently retried. A new
    process must not share this output directory while requests are in flight.
    Successful resumed records satisfy the initial health barrier without a new
    probe; an actual new batch should use its explicit first connectivity call.
    """

    def __init__(self, repo: Path, root: Path, model: str = MODEL, workers: int = 8, *, stream: bool = False,
                 reasoning_effort: str | None = None):
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 12:
            raise ValueError("workers must be an integer in [1, 12]")
        if type(stream) is not bool:
            raise ValueError("stream must be an explicit boolean")
        if reasoning_effort is not None and (
                not isinstance(reasoning_effort, str) or reasoning_effort not in {"low", "high", "max"}):
            raise ValueError("GLM-5.3 reasoning_effort must be None, low, high, or max")
        endpoint, api_key = _configuration(Path(repo), model)
        self.root, self.model, self.workers = Path(root), model, workers
        self.stream = stream
        self.reasoning_effort = reasoning_effort
        self.service = {
            "provider": "PJLAB", "host": PROVIDER_HOST, "path": "/v1/chat/completions",
            "model": model, "temperature": 0, "trust_env": False,
            "follow_redirects": False, "generation_seed": "not sent",
            "timeout_seconds": {"connect": 20, "read": 120, "write": 30, "pool": 20},
            "max_retries": 2, "retry_statuses": [429, 500, 502, 503, 504],
            "retry_backoff_seconds": [2, 4], "max_retry_after_seconds": 10,
            "protocol": "pjlab-validator-pilot-v1",
        }
        if stream:
            self.service.update(stream=True, stream_options={"include_usage": True},
                                stream_max_wall_seconds=300, stream_max_characters=8_000_000,
                                stream_max_content_characters=200_000,
                                stream_completion_rule="[DONE] plus finish_reason=stop")
        if reasoning_effort is not None:
            self.service["reasoning_effort"] = reasoning_effort
        write_immutable_json(self.root / "service.json", self.service)
        self._endpoint = endpoint
        self._client = httpx.Client(
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(120, connect=20, write=30, pool=20),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=12),
        )
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

    def call(self, system: str, user: str, kind: str, key: str,
             max_tokens: int = 6000, repeat: int = 0) -> dict[str, Any]:
        if not all(isinstance(item, str) for item in (system, user, kind, key)):
            raise ValueError("system, user, kind and key must be strings")
        if (isinstance(max_tokens, bool) or not isinstance(max_tokens, int)
                or not 1 <= max_tokens <= 16000 or not isinstance(repeat, int) or repeat < 0):
            raise ValueError("Invalid token budget or repeat index")
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
                return record
            # All first real callers queue here until the first actual response.
            with self._health_lock:
                if self._health == "failed":
                    raise RuntimeError("PJLAB initial health barrier failed; no further requests sent")
                if self._health == "unchecked":
                    record = self._perform(request, identifier)
                    write_immutable_json(path, record)
                    self._health = "ready" if record["ok"] else "failed"
                    return record
            record = self._perform(request, identifier)
            write_immutable_json(path, record)
            return record

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
        attempts: list[dict[str, Any]] = []
        for attempt in range(self.service["max_retries"] + 1):
            # Never concatenate a previous failed attempt's partial response into a retry.
            outcome: dict[str, Any] = {"ok": False, "response": "", "usage": {},
                                      "finish_reason": None, "error_type": None, "status": None}
            attempt_start = time.monotonic()
            status, retry_after, retryable, error_type = None, 0.0, False, None
            try:
                if self.stream:
                    with self._client.stream("POST", self._endpoint, json=payload) as response:
                        status = response.status_code
                        headers = response.headers
                        body = _stream_body(response) if status == 200 else None
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
                    if self.stream and not body["_stream_complete"]:
                        error_type = "incomplete_stream"
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
            except httpx.TimeoutException:
                error_type, retryable = "timeout", True
            except httpx.TransportError:
                error_type, retryable = "transport_error", True
            except _StreamResponseError as error:
                error_type = error.category
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                error_type = "invalid_response_schema"
            except Exception:
                # Never serialize exception text: it can embed request headers or keys.
                error_type = "unexpected_client_error"
            attempts.append({"attempt": attempt + 1, "ok": outcome["ok"], "status": status,
                             "error_type": error_type, "wall_seconds": time.monotonic() - attempt_start})
            outcome.update(error_type=error_type, status=status)
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
        if isinstance(first, dict) and first.get("ok") is False:
            raise RuntimeError("PJLAB batch health barrier failed; remaining jobs were not submitted")
        if len(items) == 1:
            return [first]
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="pjlab-pilot") as pool:
            rest = list(pool.map(fn, items[1:]))
        return [first, *rest]
