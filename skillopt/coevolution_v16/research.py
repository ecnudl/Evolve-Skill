"""A versioned whitespace-only presentation of frozen V15 document excerpts.

Raw retrieval, URL allowlist, byte snapshots and truncation are unchanged.
Normalize ONLY the already selected <=3500-character display excerpt, never
the complete source before truncating. Model quotations still require an exact
span of the actual displayed text; quotations themselves are not normalized.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v15 import research as raw_research
from skillopt.coevolution_v15.research import (
    EXCERPT_CHARS as EXCERPT_CHARS,
)
from skillopt.coevolution_v15.research import (
    URLS as URLS,
)
from skillopt.coevolution_v15.research import (
    _save,
)
from skillopt.coevolution_v15.research import (
    validate_citations as validate_citations,
)
from skillopt.validator_pilot.api import digest

VERSION = "v16-whitespace-only-document-presentation-v1"
PROJECTION_VERSION = "unicode-whitespace-split-join-after-v15-truncation-v1"
fetch_sources = raw_research.fetch_sources


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def present(raw_bundle):
    """Pure projection retaining raw excerpts/source hashes; no broader context."""
    raw = verify(raw_bundle)
    if raw.get("version") != raw_research.VERSION:
        raise ValueError("Presentation requires a verified original V15 retrieval bundle")
    sources = {s["requested_url"]: s for s in raw["sources"]}
    documents, projections = [], []
    for document in raw["documents"]:
        source = sources.get(document["url"])
        original = document["text"]
        if (document["url"] not in URLS or type(original) is not str or len(original) > EXCERPT_CHARS
                or source is None or source.get("ok") is not True
                or original != source["text"][:EXCERPT_CHARS]
                or document["source_hash"] != digest(source)
                or document["text_sha256"] != _sha(source["text"])):
            raise ValueError("Raw excerpt does not match the original bounded source projection")
        displayed = " ".join(original.split())
        if not displayed:
            raise ValueError("Successful source has no nonwhitespace display content")
        # Keep the public document envelope unchanged: only the text differs.
        documents.append({**deepcopy(document), "text": displayed})
        projections.append({"url": document["url"], "source_record_hash": document["source_hash"],
            "source_text_sha256": document["text_sha256"], "raw_excerpt_sha256": _sha(original),
            "presented_excerpt_sha256": _sha(displayed), "raw_excerpt_chars": len(original),
            "presented_excerpt_chars": len(displayed), "projection_version": PROJECTION_VERSION})
    inherited = {k: deepcopy(value) for k, value in raw.items()
                 if k not in {"record_hash", "version", "identity", "documents"}}
    return seal({**inherited, "version": VERSION,
        "identity": {"version": VERSION, "raw_bundle_hash": raw["record_hash"],
                     "projection_version": PROJECTION_VERSION, "maximum_raw_excerpt_chars": EXCERPT_CHARS},
        "raw_bundle_hash": raw["record_hash"], "raw_documents": deepcopy(raw["documents"]),
        "documents": documents, "projections": projections, "projection_version": PROJECTION_VERSION,
        "visible_content_expanded": False, "model_quotes_normalized": False,
        "quote_validation": "exact_span_of_actual_presented_text_not_entailment"})


def retrieve(root, *, completed=False, fetcher=None):
    """Reuse the original immutable retriever, then persist a distinct projection.

    In a fresh run this retains its ordinary once-per-run real retrieval. In a
    cached/completed run it verifies the existing snapshots without fetching.
    No old run is rewritten, no response repaired and no citation is relaxed.
    """
    raw = raw_research.retrieve(root, completed=completed, fetcher=fetcher or fetch_sources)
    expected = present(raw)
    return _save(Path(root) / "validator/research_presentation/bundle.json",
                 {k: v for k, v in expected.items() if k != "record_hash"}, completed=completed)
