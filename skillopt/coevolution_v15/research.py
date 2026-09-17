"""Bounded official-document retrieval, never an oracle or autonomous research.

Two preregistered Python semantics pages inform input-search policy only. Exact
quotes attest provenance, not entailment. The model cannot choose destinations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_document_transport import fetch_sources
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v15-bounded-official-documents-v1"
URLS = (
    "https://docs.python.org/3/library/stdtypes.html#comparisons",
    "https://docs.python.org/3/reference/expressions.html#conditional-expressions",
)
EXCERPT_CHARS = 3500


def _read(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Symlink evidence is forbidden")
    return verify(json.loads(path.read_text(encoding="utf-8")))


def _save(path, value, *, completed=False):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink evidence is forbidden")
    row = seal(value)
    if path.exists():
        if _read(path) != row:
            raise ValueError("Immutable V15 evidence differs")
    elif completed:
        raise ValueError("Completed evidence missing; never reconstruct")
    else:
        write_immutable_json(path, row)
    return row


def _manifest(root):
    result = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlink document snapshots are forbidden")
            if path.is_file():
                if path.stat().st_size > 3_000_000:
                    raise ValueError("Oversized document snapshot")
                result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def retrieve(root, *, completed=False, fetcher=None):
    """Fetch once globally per run; offline replay verifies every snapshot byte.

    A terminal fetch failure is cached, not silently retried. An interrupted
    unresolved fetch intent fails closed. No task, artifact or credential is
    transmitted to the document service.
    """
    directory = Path(root) / "validator" / "research"
    path, intent_path = directory / "bundle.json", directory / "intent.json"
    snapshot_root = directory / "snapshots"
    intent = {"version": VERSION, "urls": list(URLS), "excerpt_chars": EXCERPT_CHARS,
              "transport": "official-document-trusted-local-proxy-v1"}
    if path.exists():
        _save(intent_path, intent, completed=True)
        row = _read(path)
        if row["identity"] != intent or row["snapshot_files"] != _manifest(snapshot_root):
            raise ValueError("Document identity or snapshot bytes differ")
        return row
    if completed or intent_path.exists():
        raise ValueError("Missing or unresolved document retrieval; never refetch")
    _save(intent_path, intent)
    try:
        sources = (fetcher or fetch_sources)(URLS, snapshot_root)
        error = None
    except (OSError, ValueError, RuntimeError):
        sources, error = [], "document_transport_unavailable"
    if (type(sources) is not list or len(sources) > 2
            or any(type(s) is not dict or s.get("requested_url") not in URLS for s in sources)
            or len({s["requested_url"] for s in sources}) != len(sources)):
        raise ValueError("Document transport returned unapproved or duplicate sources")
    documents = []
    for source in sources:
        text = source.get("text", "")
        if type(text) is not str or len(text) > 12000 or type(source.get("ok")) is not bool:
            raise ValueError("Invalid bounded document source")
        if source["ok"]:
            if not text.strip() or hashlib.sha256(text.encode()).hexdigest() != source.get("text_sha256"):
                raise ValueError("Document source text digest differs")
            documents.append({"url": source["requested_url"], "text": text[:EXCERPT_CHARS],
                              "source_hash": digest(source), "text_sha256": source["text_sha256"]})
    return _save(path, {"version": VERSION, "identity": intent, "documents": documents,
        "sources": sources, "snapshot_files": _manifest(snapshot_root), "error": error,
        "available": bool(documents), "api_calls": 0, "autonomous_research": False,
        "oracle_authority": False, "quote_validation": "exact_span_not_entailment"})


def validate_citations(citations, bundle, *, required):
    """Strict, bounded exact quotation within the actual supplied excerpt."""
    if type(citations) is not list or len(citations) > 2 or (required and not citations):
        raise ValueError("One or two provenance quotes required for Research")
    if bundle is None:
        if citations:
            raise ValueError("No-document reflection cannot cite unseen documents")
        return []
    verify(bundle)
    texts = {d["url"]: d["text"] for d in bundle["documents"]}
    seen = set()
    for item in citations:
        if (type(item) is not dict or set(item) != {"url", "quote"}
                or type(item["url"]) is not str or item["url"] not in texts
                or type(item["quote"]) is not str or not 12 <= len(item["quote"]) <= 300
                or item["quote"] not in texts[item["url"]]
                or (item["url"], item["quote"]) in seen):
            raise ValueError("Quote is not an exact distinct bounded supplied span")
        seen.add((item["url"], item["quote"]))
    return citations
