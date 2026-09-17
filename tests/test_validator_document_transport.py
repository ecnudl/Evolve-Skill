"""Mocked trusted-proxy retrieval; no live network or model calls."""

from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest

from skillopt import validator_document_transport as transport

URL = "https://docs.python.org/3/library/re.html#re.match"
HTML = b'<html><main><h2 id="re.match">re.match</h2><p>Match at the beginning of a string.</p></main></html>'


class Response:
    def __init__(self, status=200, body=HTML, headers=None, *, stall=False):
        self.status_code = status
        self.body = body
        self.headers = {"content-type": "text/html", **(headers or {})}
        self.stall = stall
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def aiter_bytes(self, chunk_size=None):
        if self.stall:
            await asyncio.sleep(60)
        yield self.body


class Client:
    responses = []
    requests = []
    constructor_kwargs = []

    def __init__(self, **kwargs):
        self.constructor_kwargs.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def stream(self, method, url):
        self.requests.append((method, url))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def mock_network(monkeypatch):
    Client.responses = []
    Client.requests = []
    Client.constructor_kwargs = []
    monkeypatch.setattr(transport.httpx, "AsyncClient", Client)
    monkeypatch.setattr(transport.urllib.request, "getproxies", lambda: {"https": transport.PINNED_PROXY})


def test_success_preserves_original_html_excerpt_hashes_and_trust_boundary(tmp_path):
    Client.responses = [Response()]
    sources = transport.fetch_sources([URL], tmp_path)
    source = sources[0]
    assert source["ok"] and source["destination_ip_attested"] is False
    assert source["tls_verification_enabled"] is True
    assert source["raw_html_sha256"] == hashlib.sha256(HTML).hexdigest()
    assert source["text_sha256"] == hashlib.sha256(source["text"].encode()).hexdigest()
    assert "beginning" in source["text"]
    directory = tmp_path / "documents" / source["snapshot_id"]
    assert (directory / "source.html").read_bytes() == HTML
    assert (directory / "excerpt.txt").read_text() == source["text"]
    options = Client.constructor_kwargs[0]
    assert options["proxy"] == transport.PINNED_PROXY
    assert options["verify"] is True and options["trust_env"] is False
    assert options["follow_redirects"] is False
    assert not any(key.lower() in ("authorization", "proxy-authorization") for key in options["headers"])
    before = len(Client.requests)
    assert transport.fetch_sources([URL], tmp_path) == sources
    assert len(Client.requests) == before


@pytest.mark.parametrize(
    "proxy",
    [
        "http://localhost:7890",
        "http://127.0.0.1:7891",
        "http://user:secret@127.0.0.1:7890",
        "https://127.0.0.1:7890",
        "http://example.com:7890",
        "http://127.0.0.1:7890/",
    ],
)
def test_no_alternate_proxy_or_credentials_are_accepted(tmp_path, monkeypatch, proxy):
    monkeypatch.setattr(transport.urllib.request, "getproxies", lambda: {"https": proxy})
    with pytest.raises(ValueError):
        transport.fetch_sources([URL], tmp_path)
    with pytest.raises(ValueError):
        transport.fetch_sources([URL], tmp_path, explicit_proxy=proxy)
    assert Client.requests == []
    assert not (tmp_path / "fetch_protocol.json").exists()


def test_explicit_exact_pin_is_recorded_as_explicit_not_system_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(transport.urllib.request, "getproxies", lambda: {})
    Client.responses = [Response()]
    assert transport.fetch_sources([URL], tmp_path, explicit_proxy=transport.PINNED_PROXY)[0]["ok"]
    assert json.loads((tmp_path / "fetch_protocol.json").read_text())["proxy_selection"] == "explicit_pinned_proxy"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/x",
        "https://198.18.6.28/x",
        "http://docs.python.org/x",
        "https://docs.python.org:8080/x",
        "https://evil.example/x",
        "https://docs.python.org.evil.example/x",
        "https://user:password@docs.python.org/x",
        "https://docs.python.org/x?token=secret",
        "https://docs.python.org/%0d%0ax",
    ],
)
def test_exact_official_https_url_policy_stays_strict(tmp_path, url):
    with pytest.raises(ValueError):
        transport.fetch_sources([url], tmp_path)
    assert Client.requests == []


def test_local_fake_dns_guard_is_not_globally_monkeypatched(tmp_path, monkeypatch):
    import socket

    def forbidden(*_args, **_kwargs):
        raise AssertionError("trusted proxy mode must delegate approved hostname resolution")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    Client.responses = [Response()]
    assert transport.fetch_sources([URL], tmp_path)[0]["ok"]
    assert socket.getaddrinfo is forbidden


def test_every_redirect_is_checked_and_relative_fragment_preserved(tmp_path):
    Client.responses = [Response(302, headers={"location": "/3/library/new.html"}), Response()]
    source = transport.fetch_sources([URL], tmp_path)[0]
    assert source["ok"]
    assert source["final_url"] == "https://docs.python.org/3/library/new.html#re.match"
    assert len(source["attempts"]) == 2


@pytest.mark.parametrize(
    "location",
    [
        "https://127.0.0.1/private",
        "http://docs.python.org/x",
        "https://evil.example/x",
        "https://docs.python.org/x?secret=1",
    ],
)
def test_unsafe_redirect_is_never_requested(tmp_path, location):
    Client.responses = [Response(302, headers={"location": location})]
    source = transport.fetch_sources([URL], tmp_path)[0]
    assert not source["ok"]
    assert len(Client.requests) == 1


def test_two_redirect_limit_is_enforced(tmp_path):
    Client.responses = [
        Response(302, headers={"location": "/one"}),
        Response(302, headers={"location": "/two"}),
        Response(302, headers={"location": "/three"}),
    ]
    source = transport.fetch_sources([URL], tmp_path)[0]
    assert not source["ok"]
    assert len(Client.requests) == 3


@pytest.mark.parametrize(
    "response",
    [
        Response(404),
        Response(headers={"content-type": "application/json"}),
        Response(body=b"x" * 2_000_001),
        Response(headers={"content-length": "2000001"}),
        Response(body=b"<html>missing anchor</html>"),
        Response(302),
    ],
)
def test_status_type_size_anchor_and_redirect_errors_fail_closed(tmp_path, response):
    Client.responses = [response]
    source = transport.fetch_sources([URL], tmp_path)[0]
    assert not source["ok"]
    directory = tmp_path / "documents" / source["snapshot_id"]
    assert not (directory / "source.html").exists()
    assert not (directory / "excerpt.txt").exists()


def test_wall_deadline_cancels_stalled_body_and_closes_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(transport, "DOCUMENT_WALL_SECONDS", 0.01)
    response = Response(stall=True)
    Client.responses = [response]
    source = transport.fetch_sources([URL], tmp_path)[0]
    assert source["error_type"] == "document_timeout"
    assert response.closed
    assert source["wall_seconds"] < 1


def test_transport_errors_are_sanitized_and_never_fallback_direct(tmp_path):
    Client.responses = [httpx.ConnectError("network detail should not be persisted")]
    source = transport.fetch_sources([URL], tmp_path)[0]
    assert source["error_type"] == "document_transport_error"
    assert "network detail" not in json.dumps(source)
    assert len(Client.requests) == 1


def test_snapshot_corruption_and_protocol_changes_are_refused(tmp_path):
    Client.responses = [Response()]
    source = transport.fetch_sources([URL], tmp_path)[0]
    directory = tmp_path / "documents" / source["snapshot_id"]
    (directory / "source.html").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        transport.fetch_sources([URL], tmp_path)
    with pytest.raises(ValueError, match="Immutable"):
        transport.fetch_sources(["https://docs.python.org/3/library/json.html"], tmp_path)


def test_maximum_three_distinct_pages(tmp_path):
    for urls in ([], URL, [URL, URL], [URL] * 4):
        with pytest.raises(ValueError):
            transport.fetch_sources(urls, tmp_path)
    assert Client.requests == []


def test_successful_probe_cli_uses_exact_plan_urls_only(tmp_path, capsys):
    from scripts import validator_document_probe as probe

    plan = tmp_path / "old_run/research/plan.json"
    plan.parent.mkdir(parents=True)
    urls = [URL, "https://docs.python.org/3/library/stdtypes.html", "https://docs.python.org/3/library/sqlite3.html"]
    payload = {"questions": [{"topic": "Contracts", "question": "Which API behavior matters?"}], "urls": urls}
    plan.write_text(json.dumps(payload))
    output = tmp_path / "new_probe"
    Client.responses = [Response(), Response(), Response()]
    assert probe.main(["--plan", str(plan), "--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["requested"] == result["retrieved"] == 3
    assert result["model_calls"] == 0
    assert json.loads(plan.read_text()) == payload
    assert [url for _, url in Client.requests] == [url.split("#")[0] for url in urls]
    assert (output / "probe_result.json").is_file()


def test_probe_cli_cannot_write_inside_original_plan_directory(tmp_path, capsys):
    from scripts import validator_document_probe as probe

    plan = tmp_path / "old_run/research/plan.json"
    plan.parent.mkdir(parents=True)
    plan.write_text(json.dumps({"questions": [{"topic": "API", "question": "Check behavior?"}], "urls": [URL]}))
    output = plan.parent / "new_probe"
    assert probe.main(["--plan", str(plan), "--output", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
    assert not output.exists()
    assert Client.requests == []


def test_partial_stale_html_is_never_silently_overwritten(tmp_path):
    identifier = transport.digest({"url": URL, "transport_version": transport.VERSION, "proxy": transport.PINNED_PROXY})
    directory = tmp_path / "documents" / identifier
    directory.mkdir(parents=True)
    (directory / "source.html").write_bytes(b"older partial acquisition")
    Client.responses = [Response()]
    with pytest.raises(ValueError, match="Immutable document"):
        transport.fetch_sources([URL], tmp_path)
    assert (directory / "source.html").read_bytes() == b"older partial acquisition"
    assert not (directory / "source.json").exists()
