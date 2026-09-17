"""Explicit trusted-proxy retrieval of allowlisted public documentation.

This NEW transport does not modify the frozen validator_pilot.research module.
It handles hosts mapped to fake IPs by the user's local proxy DNS, without ever
allowing private addresses for direct requests or accepting arbitrary URLs.

Trust boundary: exactly http://127.0.0.1:7890 is an explicitly trusted existing
local CONNECT proxy. It resolves approved official hostnames; destination IPs are
not attested locally. HTTPS certificate/hostname verification remains enabled.
No API key, environment proxy, automatic redirect, or direct-network fallback is
used. Callers must preserve this distinction in research claims.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urldefrag, urljoin

import httpx

from skillopt.validator_pilot.api import digest, write_immutable_json
from skillopt.validator_pilot.research import (
    ALLOWED_HOSTS,
    MAX_HTML_BYTES,
    MAX_PAGES,
    MAX_TEXT_CHARS,
    _extract,
    _safe_url,
    _write_bytes,
)

VERSION = "official-document-trusted-local-proxy-v1"
PINNED_PROXY = "http://127.0.0.1:7890"
DOCUMENT_WALL_SECONDS = 45.0
MAX_REDIRECTS = 2
TRUST_BOUNDARY = (
    "Only the explicitly pinned existing local proxy resolves approved official HTTPS hostnames. "
    "TLS certificate/hostname verification is enabled; remote DNS/destination public IP is not "
    "independently attested. No direct fallback, arbitrary URL, private-IP allowance, proxy "
    "credential, API credential, or global DNS/settings change."
)


def resolve_proxy(explicit_proxy: str | None = None) -> tuple[str, str]:
    """Use only the exact pin, never emit a discovered proxy credential/value."""
    if explicit_proxy is not None:
        if explicit_proxy != PINNED_PROXY:
            raise ValueError("explicit proxy must equal the approved local endpoint")
        return PINNED_PROXY, "explicit_pinned_proxy"
    discovered = urllib.request.getproxies().get("https")
    if discovered != PINNED_PROXY:
        raise ValueError("existing system HTTPS proxy does not match the approved local endpoint")
    return PINNED_PROXY, "existing_system_https_proxy_exact_match"


def _cached(directory: Path, url: str) -> dict[str, Any] | None:
    path = directory / "source.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("requested_url") != url or record.get("transport_version") != VERSION:
        raise ValueError("immutable document cache identity mismatch")
    if record.get("ok"):
        raw = (directory / "source.html").read_bytes()
        excerpt = (directory / "excerpt.txt").read_text(encoding="utf-8")
        if (
            hashlib.sha256(raw).hexdigest() != record.get("raw_html_sha256")
            or hashlib.sha256(excerpt.encode()).hexdigest() != record.get("text_sha256")
            or excerpt != record.get("text")
        ):
            raise ValueError("immutable document snapshot failed integrity check")
    return record


async def _download(
    url: str, client: httpx.AsyncClient, attempts: list[dict[str, Any]]
) -> tuple[bytes, str, str, int, int]:
    current, fragment = urldefrag(url)
    for hop in range(MAX_REDIRECTS + 1):
        # Validate every requested authority, including EVERY redirect. Unlike
        # the direct transport, no local DNS resolution is used in this mode.
        current = _safe_url(current)
        start = time.monotonic()
        async with client.stream("GET", current) as response:
            attempts.append(
                {"url": current, "status": response.status_code, "wall_seconds_to_headers": time.monotonic() - start}
            )
            if response.status_code in (301, 302, 303, 307, 308):
                if hop == MAX_REDIRECTS:
                    raise ValueError("redirect_limit")
                location = response.headers.get("location")
                if not location:
                    raise ValueError("missing_redirect_location")
                approved = _safe_url(urljoin(current, location))
                current, redirected_fragment = urldefrag(approved)
                fragment = redirected_fragment or fragment
                continue
            if response.status_code != 200:
                raise ValueError("document_http_status")
            if "text/html" not in response.headers.get("content-type", "").casefold():
                raise ValueError("document_not_html")
            length = response.headers.get("content-length")
            if length and length.isdecimal() and int(length) > MAX_HTML_BYTES:
                raise ValueError("document_size_limit")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes(chunk_size=65_536):
                size += len(chunk)
                if size > MAX_HTML_BYTES:
                    raise ValueError("document_size_limit")
                chunks.append(chunk)
            raw = b"".join(chunks)
            text, offset, total = _extract(raw.decode("utf-8", errors="replace"), fragment)
            if not text.strip():
                raise ValueError("document_empty_text")
            final_url = current + ("#" + fragment if fragment else "")
            return raw, text, final_url, offset, total
    raise ValueError("redirect_limit")


async def _fetch_one(url: str, root: Path, client: httpx.AsyncClient) -> dict[str, Any]:
    identifier = digest({"url": url, "transport_version": VERSION, "proxy": PINNED_PROXY})
    directory = root / "documents" / identifier
    previous = _cached(directory, url)
    if previous is not None:
        return previous
    start = time.monotonic()
    attempts: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "transport_version": VERSION,
        "requested_url": url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "text": "",
        "error_type": None,
        "snapshot_id": identifier,
        "proxy_endpoint": PINNED_PROXY,
        "tls_verification_enabled": True,
        "destination_ip_attested": False,
        "local_dns_check": "not_used_in_explicit_trusted_proxy_mode",
        "trust_boundary": TRUST_BOUNDARY,
        "max_text_chars": MAX_TEXT_CHARS,
        "hard_async_wall_deadline_seconds": DOCUMENT_WALL_SECONDS,
    }
    try:
        # Cancellation wraps the entire async request/redirect/body operation,
        # not just a per-read inactivity timeout. No snapshot writes occur until
        # this bounded coroutine has completed successfully.
        raw, text, final_url, offset, total = await asyncio.wait_for(
            _download(url, client, attempts), timeout=DOCUMENT_WALL_SECONDS
        )
        if time.monotonic() - start > DOCUMENT_WALL_SECONDS:
            raise asyncio.TimeoutError
    except (asyncio.TimeoutError, httpx.TimeoutException):
        record["error_type"] = "document_timeout"
    except httpx.TransportError:
        record["error_type"] = "document_transport_error"
    except (ValueError, OSError):
        record["error_type"] = "document_safety_or_fetch_failure"
    else:
        record.update(
            ok=True,
            final_url=final_url,
            text=text,
            excerpt_start=offset,
            full_extracted_characters=total,
            html_bytes=len(raw),
            raw_html_sha256=hashlib.sha256(raw).hexdigest(),
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            encoding="UTF-8 with replacement for undecodable bytes",
            html_representation="HTTP-decoded HTML body, not compressed wire bytes",
        )
        _write_bytes(directory / "source.html", raw)
        _write_bytes(directory / "excerpt.txt", text.encode())
    record.update(attempts=attempts, wall_seconds=time.monotonic() - start)
    write_immutable_json(directory / "source.json", record)
    return record


async def _fetch_all(urls: Sequence[str], root: Path, proxy: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(
        proxy=proxy,
        verify=True,
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(20, connect=10),
        headers={"User-Agent": "SkillOpt-Validator-Document-Proxy-Probe/1.0", "Accept-Encoding": "identity"},
    ) as client:
        # Sequential and bounded: at most three pages, each at most three HTTP
        # requests including redirects. No model call or blanket retry loop.
        return [await _fetch_one(url, root, client) for url in urls]


def fetch_sources(urls: Sequence[str], root: Path, *, explicit_proxy: str | None = None) -> list[dict[str, Any]]:
    """Fetch public docs into a NEW immutable diagnostic snapshot directory."""
    if isinstance(urls, str) or not 1 <= len(urls) <= MAX_PAGES:
        raise ValueError("one to three official-document URLs are required")
    approved = [_safe_url(url) for url in urls]
    if len(set(approved)) != len(approved):
        raise ValueError("duplicate document URLs")
    proxy, provenance = resolve_proxy(explicit_proxy)
    root = Path(root)
    protocol = {
        "version": VERSION,
        "urls": approved,
        "proxy_endpoint": proxy,
        "proxy_selection": provenance,
        "tls_verification_enabled": True,
        "trust_env": False,
        "allowed_hosts": sorted(ALLOWED_HOSTS),
        "automatic_redirects": False,
        "max_redirects_per_page": MAX_REDIRECTS,
        "max_html_bytes": MAX_HTML_BYTES,
        "max_text_chars": MAX_TEXT_CHARS,
        "document_wall_deadline_seconds": DOCUMENT_WALL_SECONDS,
        "deadline_enforcement": "asyncio.wait_for cancellation across request/redirect/body operation",
        "max_pages": MAX_PAGES,
        "destination_ip_attested": False,
        "trust_boundary": TRUST_BOUNDARY,
        "no_api_keys": True,
        "no_model_calls": True,
        "no_proxy_or_dns_settings_changes": True,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "shared_policy_source_sha256": hashlib.sha256(
            (Path(__file__).parent / "validator_pilot/research.py").read_bytes()
        ).hexdigest(),
    }
    write_immutable_json(root / "fetch_protocol.json", protocol)
    sources = asyncio.run(_fetch_all(approved, root, proxy))
    write_immutable_json(root / "sources.json", sources)
    return sources
