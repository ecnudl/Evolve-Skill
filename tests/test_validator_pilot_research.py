"""Offline tests of research isolation, official-document fetching and provenance."""

from __future__ import annotations

import hashlib
import json
import socket
from copy import deepcopy

import httpx
import pytest

from skillopt.validator_pilot import research
from skillopt.validator_pilot.rubrics import initial_rubric

URL = "https://docs.python.org/3/library/stdtypes.html#truth-value-testing"
HTML = b"""<!doctype html><html><head><style>IGNORE CSS</style></head><body>
<nav>IGNORE NAVIGATION</nav><script>IGNORE SCRIPT</script>
<main><h1>Python standard types</h1><section id="truth-value-testing">
<h2>Truth Value Testing</h2><p>Any object can be tested for truth value.</p>
<p>Empty sequences and collections are considered false.</p></section></main>
</body></html>"""


def cases():
    return [{"split": "development", "task": {"id": "development-1", "request": "preserve false values"},
             "candidate_code": "return x or default", "audit": {"requested_behavior": False}}]


@pytest.fixture
def source():
    text = "Any object can be tested for truth value.\nEmpty sequences and collections are considered false."
    return {"ok": True, "requested_url": URL, "retrieved_utc": "2026-09-08T00:00:00+00:00",
            "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


def finding(source):
    return {"findings": [{"topic": "Truthiness is not absence", "oldcriterion": "preserved_behavior",
                           "gap": "A truthiness check can discard a contractually valid false-like value.",
                           "evidenceurls": [URL], "proposedtest": "Add a development case retaining zero.",
                           "uncertainty": "Language behavior alone does not determine this task's contract.",
                           "evidencequotes": [{"url": URL, "quote": "Any object can be tested for truth value."}]}],
            "limits": ["This proposal still requires independent calibration."]}


def mock_network(monkeypatch, handler):
    configurations = []
    actual = httpx.Client
    def client(**kwargs):
        configurations.append(kwargs)
        return actual(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(research.httpx, "Client", client)
    monkeypatch.setattr(research.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("151.101.0.223", 443))])
    return configurations


def test_plan_prompt_is_development_only_without_self_approval():
    system, user = research.plan_messages(initial_rubric(), cases())
    assert "DEVELOPMENT" in system and "not the judge" in system
    assert "benchmark test sets" in system
    assert json.loads(user)["development_audit_cases"] == cases()


@pytest.mark.parametrize("split", ["test", "holdout", "held_out", "held-out", "confirmation",
                                   "calibration", "TEST", "pilot_holdout", "final", "evaluation"])
def test_recursive_split_isolation(split, source):
    contaminated = cases()
    contaminated[0]["nested"] = [{"task": {"dataset_split": split}}]
    with pytest.raises(ValueError, match="held-out"):
        research.plan_messages(initial_rubric(), contaminated)
    with pytest.raises(ValueError, match="held-out"):
        research.synthesis_messages(initial_rubric(), contaminated, [source])


def test_missing_split_cannot_be_authenticated_is_documented():
    unknown = [{"candidate_code": "return 0"}]
    _, user = research.plan_messages(initial_rubric(), unknown)
    assert "mislabelled" in user


def test_plan_schema_and_precise_fragment():
    raw = {"questions": [{"topic": "Truth values", "question": "Does false imply missing?"}], "urls": [URL]}
    assert research.parse_plan(raw) == raw
    assert research.parse_plan("```json\n" + json.dumps(raw) + "\n```") == raw


@pytest.mark.parametrize("url", ["http://docs.python.org/3/", "https://other.invalid/", "https://127.0.0.1/",
                                 "https://docs.python.org@127.0.0.1/", "https://user:pass@docs.python.org/3/",
                                 "https://docs.python.org/3/?token=x", "https://docs.python.org:444/3/",
                                 "https://docs.python.org/3/%0a", "https://docs.python.org/3/ bad"])
def test_unsafe_urls_rejected_before_fetch(url, tmp_path):
    raw = {"questions": [{"topic": "x", "question": "y"}], "urls": [url]}
    with pytest.raises(ValueError):
        research.parse_plan(raw)
    with pytest.raises(ValueError):
        research.fetch_sources([url], tmp_path)


def test_plan_limit_duplicate_and_unknown_fields():
    base = {"questions": [{"topic": "x", "question": "y"}], "urls": [URL]}
    for updated in ({"urls": [URL] * 4}, {"urls": [URL, URL]}, {"questions": []}, {"approved": True}):
        with pytest.raises(ValueError):
            research.parse_plan({**base, **updated})


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        research.parse_plan('{"questions":[],"questions":[],"urls":[]}')


def test_fetch_snapshots_exact_bytes_text_hashes_and_resume(tmp_path, monkeypatch):
    requested = []
    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=HTML, headers={"content-type": "text/html; charset=utf-8"})
    config = mock_network(monkeypatch, handler)
    sources = research.fetch_sources([URL], tmp_path)
    record = sources[0]
    assert record["ok"] and record["requested_url"] == URL and record["final_url"] == URL
    assert "Truth Value Testing" in record["text"]
    assert "IGNORE" not in record["text"]
    assert config[0]["trust_env"] is False and config[0]["follow_redirects"] is False
    folder = tmp_path / "documents" / record["snapshot_id"]
    assert (folder / "source.html").read_bytes() == HTML
    assert (folder / "excerpt.txt").read_text() == record["text"]
    assert record["raw_html_sha256"] == hashlib.sha256(HTML).hexdigest()
    assert record["text_sha256"] == hashlib.sha256(record["text"].encode()).hexdigest()
    assert research.fetch_sources([URL], tmp_path) == sources
    assert len(requested) == 1


def test_anchor_excerpt_skips_large_irrelevant_prefix(tmp_path, monkeypatch):
    html = ("<html><body><p>" + "irrelevant " * 3000 + "</p><section id='target'>"
            "<h2>Desired Topic</h2><p>Required normative detail.</p>" + "tail " * 5000 + "</section></body></html>").encode()
    mock_network(monkeypatch, lambda _: httpx.Response(200, content=html, headers={"content-type": "text/html"}))
    record = research.fetch_sources(["https://docs.python.org/3/library/example.html#target"], tmp_path)[0]
    assert record["ok"] and record["excerpt_start"] > 20_000
    assert len(record["text"]) == research.MAX_TEXT_CHARS
    assert "Desired Topic" in record["text"] and "Required normative detail" in record["text"]


def test_missing_anchor_fails_instead_of_silently_using_wrong_excerpt(tmp_path, monkeypatch):
    mock_network(monkeypatch, lambda _: httpx.Response(200, content=HTML, headers={"content-type": "text/html"}))
    record = research.fetch_sources(["https://docs.python.org/3/library/stdtypes.html#not-present"], tmp_path)[0]
    assert not record["ok"] and record["text"] == ""


def test_outside_redirect_is_not_requested(tmp_path, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request.url)
        return httpx.Response(302, headers={"location": "https://other.invalid/private"})
    mock_network(monkeypatch, handler)
    record = research.fetch_sources([URL], tmp_path)[0]
    assert not record["ok"] and len(requests) == 1


def test_allowed_redirect_is_bounded_and_recorded(tmp_path, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request.url)
        if len(requests) == 1:
            return httpx.Response(302, headers={"location": "/3.14/library/stdtypes.html"})
        return httpx.Response(200, content=HTML, headers={"content-type": "text/html"})
    mock_network(monkeypatch, handler)
    record = research.fetch_sources([URL], tmp_path)[0]
    assert record["ok"] and len(requests) == 2
    assert record["final_url"] == "https://docs.python.org/3.14/library/stdtypes.html#truth-value-testing"
    assert [row["status"] for row in record["attempts"]] == [302, 200]


def test_redirect_loop_stops_at_three_requests(tmp_path, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request.url)
        return httpx.Response(302, headers={"location": "/3/library/stdtypes.html"})
    mock_network(monkeypatch, handler)
    record = research.fetch_sources([URL], tmp_path)[0]
    assert not record["ok"] and len(requests) == 3


def test_private_dns_prevents_any_request(tmp_path, monkeypatch):
    requests = []
    mock_network(monkeypatch, lambda request: requests.append(request))
    monkeypatch.setattr(research.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    record = research.fetch_sources([URL], tmp_path)[0]
    assert not record["ok"] and not requests


@pytest.mark.parametrize("status,content_type", [(404, "text/html"), (200, "application/json")])
def test_bad_http_and_nonhtml_fail_sanitized(tmp_path, monkeypatch, status, content_type):
    mock_network(monkeypatch, lambda _: httpx.Response(status, content=b"PRIVATE_ERROR_BODY",
                                                      headers={"content-type": content_type}))
    record = research.fetch_sources([URL], tmp_path)[0]
    assert not record["ok"] and "PRIVATE_ERROR_BODY" not in json.dumps(record)


def test_timeout_sanitized(tmp_path, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("PRIVATE_EXCEPTION", request=request)
    mock_network(monkeypatch, handler)
    record = research.fetch_sources([URL], tmp_path)[0]
    assert record["error_type"] == "document_timeout"
    assert "PRIVATE_EXCEPTION" not in json.dumps(record)


def test_oversized_document_fails_before_snapshot(tmp_path, monkeypatch):
    mock_network(monkeypatch, lambda _: httpx.Response(200, content=b"x" * (research.MAX_HTML_BYTES + 1),
                                                      headers={"content-type": "text/html"}))
    record = research.fetch_sources([URL], tmp_path)[0]
    assert not record["ok"] and not list(tmp_path.rglob("source.html"))


def test_tampered_document_cache_fails(tmp_path, monkeypatch):
    mock_network(monkeypatch, lambda _: httpx.Response(200, content=HTML, headers={"content-type": "text/html"}))
    record = research.fetch_sources([URL], tmp_path)[0]
    (tmp_path / "documents" / record["snapshot_id"] / "excerpt.txt").write_text("altered")
    with pytest.raises(ValueError, match="integrity"):
        research.fetch_sources([URL], tmp_path)


def test_synthesis_shows_only_bounded_evidence_not_raw_html(source):
    source["raw_html"] = "RAW_HTML_MUST_NOT_ENTER_PROMPT"
    system, user = research.synthesis_messages(initial_rubric(), cases(), [source])
    assert "never approve" in system and "Independent calibration" in system
    assert "RAW_HTML_MUST_NOT_ENTER_PROMPT" not in user
    assert json.loads(user)["sources"][0]["text"] == source["text"]


def test_findings_exact_citations_accepted_but_not_semantically_certified(source):
    proposal = finding(source)
    assert research.parse_findings(proposal, [source]) == proposal
    proposal["findings"][0]["gap"] = "A speculative claim not semantically verified by this parser."
    assert research.parse_findings(proposal, [source]) == proposal


@pytest.mark.parametrize("mutation", ["unknown_url", "fake_quote", "missing_quote", "self_approval", "empty_uncertainty"])
def test_invalid_findings_fail_closed(source, mutation):
    proposal = finding(source)
    row = proposal["findings"][0]
    if mutation == "unknown_url":
        row["evidenceurls"] = ["https://docs.python.org/3/other.html"]
    elif mutation == "fake_quote":
        row["evidencequotes"][0]["quote"] = "Invented official documentation statement."
    elif mutation == "missing_quote":
        row["evidencequotes"] = []
    elif mutation == "self_approval":
        proposal["approved"] = True
    else:
        row["uncertainty"] = ""
    with pytest.raises(ValueError):
        research.parse_findings(proposal, [source])


def test_no_supported_findings_is_valid(source):
    proposal = {"findings": [], "limits": ["No documented gap established; do not revise on this evidence."]}
    assert research.parse_findings(proposal, [source]) == proposal
    assert research.parse_findings(proposal, []) == proposal


def test_failed_source_cannot_be_cited(source):
    failed = deepcopy(source)
    failed["ok"] = False
    with pytest.raises(ValueError, match="unavailable"):
        research.parse_findings(finding(source), [failed])


def test_changed_excerpt_hash_rejected(source):
    source["text"] += " An unverified extension."
    with pytest.raises(ValueError, match="hash"):
        research.synthesis_messages(initial_rubric(), cases(), [source])


def test_all_cited_urls_require_quotes(source):
    second = deepcopy(source)
    second["requested_url"] = "https://docs.python.org/3/library/functions.html"
    proposal = finding(source)
    proposal["findings"][0]["evidenceurls"].append(second["requested_url"])
    with pytest.raises(ValueError, match="Every cited"):
        research.parse_findings(proposal, [source, second])
