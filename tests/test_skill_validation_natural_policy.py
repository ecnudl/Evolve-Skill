"""Offline policy/probe boundary tests with scripted API and document receipts."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import httpx
import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import natural_policy as policy
from skillopt.skill_validation.models import SourceFile
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import artifact, task

URL = "https://docs.python.org/3.11/library/stdtypes.html"
QUOTE = "Empty sequences and collections are considered false."


class FakeCalls:
    """Never opens a connection; unexpected retries exhaust the scripted list."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def call(self, system, user, stage, *, max_tokens):
        self.requests.append({"system": system, "user": user, "stage": stage, "max_tokens": max_tokens})
        response = self.responses.pop(0)
        if isinstance(response, dict):
            return {"request_hash": digest(self.requests[-1]), **response}
        return {"request_hash": digest(self.requests[-1]), "ok": True, "response": response}


def plan(status="investigate", urls=None, **extra):
    return json.dumps({"status": status, "questions": ["Which public contract boundary is uncovered?"],
                       "urls": urls or [], **extra})


def proposal(*, status="update", citations=None, **extra):
    return {"status": status, "policy": deepcopy(policy.DEFAULT_POLICY) if status == "update" else None,
            "citations": citations or [], "reason": "A conditional boundary mechanism is a hypothesis.", **extra}


def source_record(**extra):
    return {"requested_url": URL, "ok": True, "final_url": URL, "text": QUOTE,
            "text_sha256": hashlib.sha256(QUOTE.encode()).hexdigest(), "retrieved_utc": "2026-09-20T00:00:00Z",
            "attempts": [{"url": URL, "status": 200}], **extra}


def public_source():
    return {"source_id": "source-1", "url": URL, "status": "available", "text": QUOTE}


def frozen_policy(**extra):
    return seal({"version": policy.VERSION, "arm": "adaptive_no_research", **proposal(), **extra})


def development_view():
    return {"public_feedback": {"public_task": "Return the requested value."},
            "unlinked_development_gap_counts": {"pass/fail": 1},
            "gap_origin": "development_audit_summary_not_research_discovery"}


def test_both_adaptive_arms_receive_identical_development_evidence_and_two_call_cap(tmp_path):
    snapshots = {}
    for arm in ("adaptive_no_research", "adaptive_research"):
        calls = FakeCalls([plan(), json.dumps(proposal())])
        result = policy.propose_policy(arm, development_view(), calls, tmp_path)
        verify(result)
        assert result["status"] == "update" and result["requires_calibration"] is True
        assert result["hypotheses_are_not_task_truth"] is True
        assert len(calls.requests) == 2
        assert all(request["max_tokens"] == 2048 for request in calls.requests)
        snapshots[arm] = [json.loads(request["user"])["development"] for request in calls.requests]
    assert snapshots["adaptive_no_research"] == snapshots["adaptive_research"] == [development_view()] * 2


def test_fixed_never_calls_api_and_identical_replay_never_calls_again(tmp_path):
    assert policy.propose_policy("fixed", development_view(), FakeCalls([]), tmp_path)["status"] == "fixed"
    calls = FakeCalls([plan(), json.dumps(proposal())])
    original = policy.propose_policy("adaptive_no_research", development_view(), calls, tmp_path)
    assert policy.propose_policy("adaptive_no_research", development_view(), FakeCalls([]), tmp_path) == original
    with pytest.raises(ValueError, match="replay changed"):
        policy.propose_policy("adaptive_no_research", {"changed": True}, FakeCalls([]), tmp_path)


@pytest.mark.parametrize("status", ["no_update", "insufficient_evidence"])
def test_planner_abstention_is_legal_and_carries_no_policy_modification(status, tmp_path):
    calls = FakeCalls([plan(status)])
    result = policy.propose_policy("adaptive_research", development_view(), calls, tmp_path)
    assert result["status"] == status and len(calls.requests) == 1
    assert result["policy"] is None and result["citations"] == []


@pytest.mark.parametrize("status", ["no_update", "insufficient_evidence"])
def test_synthesis_abstention_is_legal_without_repair(status, tmp_path):
    calls = FakeCalls([plan(), json.dumps(proposal(status=status))])
    result = policy.propose_policy("adaptive_no_research", development_view(), calls, tmp_path)
    assert result["status"] == status and result["policy"] is None and len(calls.requests) == 2


@pytest.mark.parametrize("responses,expected_calls", [
    ([{"ok": False, "response": None}], 1),
    ([plan(), {"ok": False, "response": "PRIVATE_TRANSPORT_BODY"}], 2),
    (["{unquoted_key: true}"], 1),
    ([plan(H="UNUSED_PRIVATE_FIELD")], 1),
    ([plan(), json.dumps(proposal(hidden_tests="UNUSED_PRIVATE_FIELD"))], 2),
])
def test_api_or_strict_validation_failure_is_terminal_sanitized_and_not_retried(responses, expected_calls, tmp_path):
    calls = FakeCalls(responses)
    result = policy.propose_policy("adaptive_no_research", development_view(), calls, tmp_path)
    assert result["status"] == "invalid" and result["policy"] is None
    assert len(calls.requests) == expected_calls
    assert "PRIVATE_TRANSPORT_BODY" not in json.dumps(result)
    assert "UNUSED_PRIVATE_FIELD" not in json.dumps(result)


@pytest.mark.parametrize("raw", [
    '{"status":"no_update","status":"update","policy":null,"citations":[],"reason":"x"}',
    '{"status":"no_update","policy":null,"citations":[],"reason":NaN}',
    "[]", "not JSON", "x" * 100001,
    json.dumps({**proposal(), "H": "PRIVATE_SENTINEL"}),
])
def test_strict_policy_json_rejects_duplicates_nonfinite_nonobject_and_private_fields(raw):
    with pytest.raises(ValueError):
        policy.parse_policy(raw, [], "adaptive_no_research")


@pytest.mark.parametrize("raw", [proposal(), "```json\n" + json.dumps(proposal()) + "\n```"])
def test_strict_policy_json_is_a_json_document_not_mapping_or_markdown(raw):
    with pytest.raises(ValueError):
        policy.parse_policy(raw, [], "adaptive_no_research")


def test_strict_planner_json_does_not_accept_markdown_fence(tmp_path):
    calls = FakeCalls(["```json\n" + plan("no_update") + "\n```"])
    result = policy.propose_policy("adaptive_research", development_view(), calls, tmp_path)
    assert result["status"] == "invalid"


def test_conditional_policy_cannot_smuggle_unused_private_fields_or_new_obligations():
    payload = proposal()
    payload["policy"]["H"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="Exact conditional"):
        policy.parse_policy(json.dumps(payload), [], "adaptive_no_research")
    payload = proposal()
    payload["policy"]["obligation"] = "input_preservation"
    with pytest.raises(ValueError, match="new task obligation"):
        policy.parse_policy(json.dumps(payload), [], "adaptive_no_research")


def test_research_citations_require_available_exact_source_excerpts():
    payload = proposal(citations=[{"source_id": "source-1", "quote": QUOTE}])
    assert policy.parse_policy(json.dumps(payload), [public_source()], "adaptive_research") == payload
    with pytest.raises(ValueError, match="No-Research"):
        policy.parse_policy(json.dumps(payload), [public_source()], "adaptive_no_research")
    for sources in ([], [{**public_source(), "status": "retrieval_failed"}], [{**public_source(), "text": "different"}]):
        with pytest.raises(ValueError, match="exact available"):
            policy.parse_policy(json.dumps(payload), sources, "adaptive_research")
    payload["citations"][0]["private_notes"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="Exact citation"):
        policy.parse_policy(json.dumps(payload), [public_source()], "adaptive_research")


def test_research_fetches_only_requested_sources_before_synthesis(monkeypatch, tmp_path):
    fetched = []
    def fetch(urls, root):
        fetched.append((urls, root))
        return [public_source()]
    monkeypatch.setattr(policy, "fetch_sources", fetch)
    calls = FakeCalls([plan(urls=[URL]), json.dumps(proposal(citations=[{"source_id": "source-1", "quote": QUOTE}]))])
    result = policy.propose_policy("adaptive_research", development_view(), calls, tmp_path)
    assert result["status"] == "update"
    assert len(fetched) == 1 and fetched[0][0] == [URL]
    assert json.loads(calls.requests[1]["user"])["sources"] == [public_source()]


def test_failed_retrieval_stops_before_synthesis_and_no_research_cannot_fetch(monkeypatch, tmp_path):
    fetched = []
    def fetch(urls, root):
        fetched.append(urls)
        return [{"source_id": "failed", "url": URL, "status": "retrieval_failed"}]
    monkeypatch.setattr(policy, "fetch_sources", fetch)
    for arm in ("adaptive_no_research", "adaptive_research"):
        calls = FakeCalls([plan(urls=[URL])])
        result = policy.propose_policy(arm, development_view(), calls, tmp_path)
        assert result["status"] == "invalid" and len(calls.requests) == 1
    assert fetched == [[URL]]


@pytest.mark.parametrize("url", [
    "http://docs.python.org/3.11/library/stdtypes.html", "https://evil.invalid/3.11/library/stdtypes.html",
    "https://docs.python.org/3.14/library/stdtypes.html", "https://docs.python.org/3.11/tutorial/index.html",
    "https://docs.python.org/3.11/library/stdtypes.html?answer=secret", "https://u:p@docs.python.org/3.11/library/stdtypes.html",
    "https://docs.python.org:444/3.11/library/stdtypes.html", "https://127.0.0.1/3.11/library/stdtypes.html",
    "https://docs.python.org/3.11/library/%73tdtypes.html", "https://docs.python.org/3.11/library/stdtypes.html#%0a",
])
def test_url_whitelist_is_exact_and_rejected_before_fetch(url, monkeypatch, tmp_path):
    monkeypatch.setattr(policy.legacy, "_fetch_one", lambda *args: pytest.fail("Rejected URL reached fetch"))
    with pytest.raises(ValueError):
        policy.approved(url)
    with pytest.raises(ValueError):
        policy.fetch_sources([url], tmp_path)


def test_fetch_projection_excludes_unused_private_receipt_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(policy.legacy, "_fetch_one", lambda *args: source_record(H="PRIVATE_SENTINEL", raw_html="RAW_SENTINEL"))
    source = policy.fetch_sources([URL], tmp_path)[0]
    assert source["text"] == QUOTE and source["source_version"] == "Python 3.11"
    assert "PRIVATE_SENTINEL" not in json.dumps(source) and "RAW_SENTINEL" not in json.dumps(source)


@pytest.mark.parametrize("changed", [
    {"requested_url": "https://docs.python.org/3.11/library/math.html"},
    {"final_url": "https://docs.python.org/3.14/library/stdtypes.html"},
    {"attempts": [{"url": "https://other.invalid/redirect", "status": 302}]},
    {"text_sha256": "0" * 64},
])
def test_cached_receipt_revalidates_requests_redirects_and_excerpt_hash(changed, monkeypatch, tmp_path):
    monkeypatch.setattr(policy.legacy, "_fetch_one", lambda *args: source_record(**changed))
    with pytest.raises(ValueError):
        policy.fetch_sources([URL], tmp_path)


def test_disallowed_live_redirect_is_never_requested_and_failure_replays_offline(monkeypatch, tmp_path):
    requested = []
    real_client = httpx.Client
    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://docs.python.org/3.14/library/stdtypes.html"})
    monkeypatch.setattr(policy.legacy, "_public_dns", lambda host: None)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    failed = policy.fetch_sources([URL], tmp_path)
    assert failed[0]["status"] == "retrieval_failed"
    assert requested == [URL]
    assert policy.fetch_sources([URL], tmp_path) == failed
    assert requested == [URL]


def test_probe_projection_excludes_host_audit_and_all_condition_skill_identity():
    t = task()
    artifacts = tuple(replace(artifact(t, condition=condition), skill_version="SKILL_ID_SENTINEL",
                              source_ref="HOST_EXECUTOR_SENTINEL", source_hash=digest("PRIVATE_H_SENTINEL"))
                      for condition in ("no_skill", "current"))
    frozen = frozen_policy(host_audit={"H": "PRIVATE_H_SENTINEL"}, sources=[{"private": "SOURCE_H_SENTINEL"}])
    system, user = policy.probe_messages(t, artifacts, frozen)
    payload = json.loads(user)
    assert set(payload) == {"task", "entry_point", "rubric", "citations", "anonymous_implementations"}
    for secret in ("PRIVATE_H_SENTINEL", "SOURCE_H_SENTINEL", "HOST_EXECUTOR_SENTINEL", "SKILL_ID_SENTINEL",
                   "fixture-task", "fixture-family", '"no_skill"', '"current"'):
        assert secret not in user
    assert "fallible hypothesis" in system and "same probes" in system
    assert payload["anonymous_implementations"] == [artifacts[0].files[0].content]


def test_probe_prompt_is_invariant_to_role_swaps_artifact_order_and_duplicate_code():
    t = task()
    first = artifact(t, condition="no_skill")
    second = replace(artifact(t, condition="current"), files=(SourceFile("solution.py", "def solve(values): return sum(values)"),))
    frozen = frozen_policy()
    original = policy.probe_messages(t, (first, second), frozen)
    swapped = (replace(second, condition="no_skill", skill_hash=first.skill_hash),
               replace(first, condition="current", skill_hash=second.skill_hash))
    assert policy.probe_messages(t, swapped, frozen) == original
    assert policy.probe_messages(t, (second, first, second), frozen) == original


def test_probe_prompt_revalidates_nested_policy_against_private_field_injection():
    value = proposal()
    value["policy"]["H"] = "PRIVATE_H_SENTINEL"
    frozen = seal({"version": policy.VERSION, "arm": "adaptive_no_research", **value})
    with pytest.raises(ValueError):
        policy.probe_messages(task(), (), frozen)


def test_probe_requires_actual_update_and_immutable_policy_hash():
    t = task()
    with pytest.raises(ValueError, match="proposed policy"):
        policy.probe_messages(t, (), seal({"status": "no_update"}))
    frozen = frozen_policy()
    frozen["policy"]["mechanism"] = "Changed after freeze."
    with pytest.raises(ValueError, match="checksum"):
        policy.probe_messages(t, (), frozen)
