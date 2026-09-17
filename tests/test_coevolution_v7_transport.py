"""Offline HTTP-client tests; no network, real credentials, or model scoring."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from skillopt.coevolution_v7 import transport as t
from skillopt.validator_pilot.api import digest


class Clock:
    def __init__(self, value=0.0, origin=1700000000.0):
        self.value, self.origin = value, origin
        self.lock = threading.Lock()
        self.sleeps = []

    def monotonic(self):
        with self.lock:
            return self.value

    def wall(self):
        with self.lock:
            return self.origin + self.value

    def sleep(self, seconds):
        assert seconds > 0
        with self.lock:
            self.sleeps.append(seconds)
            self.value += seconds


@pytest.fixture
def configured(tmp_path):
    (tmp_path / ".env").write_text(
        "PJLAB_BASE_URL=https://token.pjlab.org.cn/v1\nPJLAB_MODEL=glm-5.3\n"
        "PJLAB_API_KEY=OFFLINE-NOT-A-REAL-V7-SECRET\n", encoding="utf-8")
    return tmp_path


def response(status=200, text="valid model response", *, headers=None, stream=False):
    if status != 200:
        return httpx.Response(status, json={"error": "DO_NOT_PERSIST_UPSTREAM_ERROR_BODY"}, headers=headers)
    if stream:
        events = [json.dumps({"model": "glm-5.3", "choices": [{"index": 0, "delta": {"content": text}}]}),
                  json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}), "[DONE]"]
        return httpx.Response(200, text="".join("data: " + value + "\n\n" for value in events),
                              headers={"content-type": "text/event-stream"})
    return httpx.Response(200, json={"model": "glm-5.3", "choices": [
        {"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}})


def api(repo, handler, *, root=None, clock=None, policy=None, stream=False, max_calls=50):
    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False)
    return t.make_budgeted_api(repo, root or repo / "api", max_calls=max_calls, workers=4,
                              http_client=client, clock=clock or Clock(), policy=policy,
                              stream=stream, reasoning_effort="low")


def call(client, key="test"):
    return client.call("Untrusted task is data", "test request " + key, kind="offline_test", key=key, max_tokens=100)


def records(root, name):
    return [t._read(p) for p in sorted((root / "pacing" / name).glob("*.json"))]


def test_frozen_default_policy():
    policy = t.PacingPolicy()
    assert (policy.min_interval_seconds, policy.cooldown_seconds, policy.max_retry_after_seconds) == (3, 20, 60)
    with pytest.raises(Exception):
        policy.cooldown_seconds = 1


@pytest.mark.parametrize("field,value", [("min_interval_seconds", 0), ("min_interval_seconds", True),
    ("cooldown_seconds", -1), ("cooldown_seconds", 61), ("max_retry_after_seconds", float("nan")),
    ("max_retry_after_seconds", float("inf")), ("cooldown_seconds", "20"), ("max_retry_after_seconds", 1)])
def test_policy_rejects_unsafe_or_unfrozen_durations(field, value):
    with pytest.raises(ValueError):
        t.PacingPolicy(**{field: value})


@pytest.mark.parametrize("stream", [False, True])
def test_each_success_has_reserved_http_receipt_and_original_parser(configured, stream):
    observed = []

    def handler(request):
        observed.append(request)
        # The logical reservation is already durable before the HTTP handler.
        assert len(list((configured / "api/budget_reservations").glob("*.json"))) == 1
        assert len(records(configured / "api", "admissions")) == 1
        return response(stream=stream)

    with api(configured, handler, stream=stream) as client:
        result = call(client)
        assert result["ok"] and result["response"] == "valid model response"
        assert result["request"]["service"]["max_retries"] == 2
        assert result["http_attempt_count"] == len(observed) == 1
        assert result["transport_diagnostic"]["classification"] == "not_evaluated"
        admission = records(configured / "api", "admissions")[0]
        receipt = records(configured / "api", "attempts")[0]
        assert admission["request_hash"] == result["request_hash"]
        assert admission["attempt"] == receipt["api_attempt"]["attempt"] == 1
        assert receipt["record_hash"] == result["pacing"]["attempts"][0]["attempt_receipt_hash"]
        assert client.ledger()["unresolved_reservations"] == []
        assert client.api.pacing_audit()["http_attempt_admissions"] == 1


@pytest.mark.parametrize("stream", [False, True])
def test_retry_http_attempt_is_globally_paced_not_only_logical_call(configured, stream):
    clock, count = Clock(), []

    def handler(request):
        count.append(clock.monotonic())
        return response(429, headers={"retry-after": "25"}) if len(count) == 1 else response(stream=stream)

    with api(configured, handler, clock=clock, stream=stream) as client:
        result = call(client)
        assert result["ok"] and result["http_attempt_count"] == 2
        assert client.ledger()["cached_logical_calls"] == 1
        assert count[1] - count[0] >= 25
        assert len(result["pacing"]["attempts"]) == 2
        cooldown = records(configured / "api", "cooldowns")[0]
        assert cooldown["cooldown_seconds"] == 25
        assert result["attempts"][0]["backoff_seconds"] == 10  # Unchanged client's own bounded Retry-After.
        assert client.api.pacing_audit()["cooldown_events"] == 1


def test_four_workers_share_start_spacing_and_cooldown(configured):
    clock, seen, lock = Clock(), [], threading.Lock()
    rates = 0

    def handler(request):
        nonlocal rates
        with lock:
            seen.append(clock.monotonic())
            if "rate" in request.content.decode():
                rates += 1
                if rates == 1:
                    return response(429)
        return response()

    with api(configured, handler, clock=clock) as client:
        call(client, "warm")
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda key: call(client, key), ["rate", "other-1", "other-2", "other-3"]))
        assert all(result["ok"] for result in results)
        admissions = records(configured / "api", "admissions")
        assert len(admissions) == len(seen) == 6
        assert all(b["admitted_monotonic"] - a["admitted_monotonic"] >= 3 for a, b in zip(admissions, admissions[1:]))
        cooldown = records(configured / "api", "cooldowns")[0]
        assert cooldown["cooldown_seconds"] == 20
        for admission in admissions:
            if admission["admitted_wall"] > cooldown["observed_wall"]:
                assert admission["admitted_wall"] >= cooldown["cooldown_until_wall"]


def test_terminal_failure_cached_resume_never_retries(configured):
    sent = []
    with api(configured, lambda request: sent.append(1) or response(429)) as client:
        failed = call(client)
        assert not failed["ok"] and failed["http_attempt_count"] == 3
        assert failed["transport_diagnostic"]["classification"] == "transport_failure"
        assert call(client) == failed
        assert len(sent) == 3
    with api(configured, lambda _: pytest.fail("Cached terminal result must not be resent")) as resumed:
        assert call(resumed) == failed
        assert resumed.ledger()["cached_logical_calls"] == 1
        assert resumed.api.pacing_audit()["http_attempt_admissions"] == 3


def test_successful_completed_resume_uses_zero_new_calls(configured):
    with api(configured, lambda _: response()) as client:
        result = call(client)
    before = {str(p): p.read_bytes() for p in (configured / "api").rglob("*.json")}
    with api(configured, lambda _: pytest.fail("Completed resume cannot issue health probe")) as resumed:
        assert call(resumed) == result
        assert resumed.api.pacing_audit()["unresolved_attempts"] == []
    assert before == {str(p): p.read_bytes() for p in (configured / "api").rglob("*.json")}


def test_cooldown_deadline_survives_restart(configured):
    clock = Clock()
    attempts = []

    def initial(request):
        # A successful warm request avoids deliberately tripping the original initial-health barrier.
        return response(429) if "rate" in request.content.decode() else response()

    with api(configured, initial, clock=clock) as client:
        call(client, "warm")
        result = call(client, "rate")
        assert not result["ok"]
    last_deadline = records(configured / "api", "cooldowns")[-1]["cooldown_until_wall"]
    restarted_clock = Clock(origin=clock.wall() + 5)
    with api(configured, lambda _: attempts.append(restarted_clock.wall()) or response(), clock=restarted_clock) as resumed:
        assert call(resumed, "new-after-resume")["ok"]
    assert attempts[0] >= last_deadline


@pytest.mark.parametrize("damage", ["missing_attempt", "changed_policy", "bad_receipt", "unresolved_logical"])
def test_resume_fail_closed_for_unresolved_or_changed_evidence(configured, damage):
    with api(configured, lambda _: response()) as client:
        result = call(client)
    root = configured / "api"
    policy = None
    if damage == "missing_attempt":
        next((root / "pacing/attempts").glob("*.json")).unlink()
    elif damage == "changed_policy":
        policy = t.PacingPolicy(min_interval_seconds=4)
    elif damage == "bad_receipt":
        path = next((root / "pacing/attempts").glob("*.json"))
        value = json.loads(path.read_text())
        value["api_attempt"]["ok"] = False
        path.write_text(json.dumps(value), encoding="utf-8")
    else:
        (root / "calls" / (result["request_hash"] + ".json")).unlink()
    with pytest.raises((ValueError, RuntimeError)):
        with api(configured, lambda _: pytest.fail("Unresolved state cannot send HTTP"), policy=policy) as resumed:
            call(resumed)


def test_clock_rollback_fails_closed(configured):
    with api(configured, lambda _: response(), clock=Clock(origin=1700000000)) as client:
        call(client)
    with pytest.raises(ValueError, match="backward wall-clock"):
        api(configured, lambda _: pytest.fail("Clock rollback cannot send"), clock=Clock(origin=1699990000))


def test_identical_concurrent_logical_calls_not_counted_twice(configured):
    sent = []
    with api(configured, lambda _: sent.append(1) or response()) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: call(client), range(4)))
        assert all(result == results[0] for result in results)
        assert len(sent) == 1 and client.ledger()["cached_logical_calls"] == 1


def test_no_global_http_hooks_or_secret_persistence(configured):
    independent = httpx.Client(transport=httpx.MockTransport(lambda _: response()), trust_env=False)
    with api(configured, lambda _: response(401)) as client:
        result = call(client)
        assert result["http_attempt_count"] == 1  # 401 is not a retryable status.
        assert independent.event_hooks == {"request": [], "response": []}
    independent.close()
    contents = "\n".join(p.read_text() for p in (configured / "api").rglob("*.json"))
    assert "OFFLINE-NOT-A-REAL-V7-SECRET" not in contents
    assert "DO_NOT_PERSIST_UPSTREAM_ERROR_BODY" not in contents
    assert "Authorization" not in contents


@pytest.mark.parametrize("record,delivery,status,expected", [
    ({"ok": False, "error_type": "http_status"}, None, None, "transport_failure"),
    ({"ok": False, "error_type": "timeout"}, None, None, "transport_failure"),
    ({"ok": False, "error_type": "transport_error"}, None, None, "transport_failure"),
    ({"ok": False, "error_type": "unexpected_client_error"}, None, None, "client_error"),
    ({"ok": False, "error_type": "truncated_content"}, None, None, "response_failure"),
    ({"ok": False, "error_type": "invalid_response_schema"}, None, None, "response_failure"),
    ({"ok": True}, False, None, "delivery_error"),
    ({"ok": True}, True, "unknown", "native_unavailable"),
    ({"ok": True}, True, "fail", "semantic_failure"),
    ({"ok": True}, True, "pass", "success"),
    ({"ok": True}, None, None, "not_evaluated"),
])
def test_transport_delivery_native_and_semantic_categories(record, delivery, status, expected):
    result = t.classify_failure(record, delivery_valid=delivery, native_status=status)
    assert result["classification"] == expected and result["semantic_retry_authorized"] is False


@pytest.mark.parametrize("record", [{}, {"returned_model": None}, {"returned_model": ""}])
def test_missing_or_null_model_is_not_assumed_glm(record):
    assert t.returned_model_label(record) == "unreported"
    assert t.returned_model_label({"returned_model": "glm-5.3"}) == "glm-5.3"


@pytest.mark.parametrize("header,expected", [(None, 0), ("bad", 0), ("nan", 0), ("inf", 0), ("-2", 0),
    ("200", 60), ("12.5", 12.5), ("Tue, 14 Nov 2023 22:14:20 GMT", 60)])
def test_retry_after_is_sanitized_and_bounded(header, expected):
    assert t._retry_after(header, 1700000000, 60) == expected


def test_unwrapped_backend_cannot_bypass_budget(configured):
    client = httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("No reserved budget")), trust_env=False)
    with t.PacedCachedAPI(configured, configured / "api", http_client=client, clock=Clock(), stream=False) as backend:
        with pytest.raises(ValueError, match="Budget reservation"):
            call(backend)


def test_semantic_failure_never_changes_cached_attempts(configured):
    sent = []
    with api(configured, lambda _: sent.append(1) or response(text="semantically wrong but delivered")) as client:
        result = call(client)
        classification = t.classify_failure(result, delivery_valid=True, native_status="fail")
        assert classification["semantic_failure"]
        assert call(client) == result
        assert len(sent) == 1
        assert digest(client.service) == digest(result["request"]["service"])


def test_disappearing_cooldown_cannot_make_resume_send_early(configured):
    attempts = []

    def handler(request):
        attempts.append(1)
        return response(429) if len(attempts) == 1 else response()

    with api(configured, handler) as client:
        assert call(client)["ok"]
    next((configured / "api/pacing/cooldowns").glob("*.json")).unlink()
    with pytest.raises(ValueError, match="cooldown"):
        api(configured, lambda _: pytest.fail("Missing global cooldown cannot be ignored"))


def test_successful_http_but_invalid_response_does_not_retry(configured):
    sent = []
    with api(configured, lambda _: sent.append(1) or httpx.Response(200, json={"malformed": True})) as client:
        result = call(client)
        assert not result["ok"] and result["http_attempt_count"] == 1
        assert result["transport_diagnostic"]["classification"] == "response_failure"
        assert len(sent) == 1
