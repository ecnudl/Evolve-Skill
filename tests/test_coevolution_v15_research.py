"""Hand-authored local document fixtures; all transports are replaced."""

import hashlib
import json

import pytest

from skillopt.coevolution_v15 import research as r
from skillopt.coevolution_v15 import validator as v
from skillopt.validator_pilot.api import write_immutable_json
from tests.test_coevolution_v15_validator import API, evidence, tree


def fetcher(urls, root):
    assert tuple(urls) == r.URLS
    text = "Comparisons evaluate operands under Python semantics. Conditional expressions evaluate only their selected branch."
    sources = [{"requested_url": url, "ok": True, "text": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest()} for url in urls]
    write_immutable_json(root / "sources.json", sources)
    return sources


def test_actual_snapshot_binding_and_zero_fetch_replay(tmp_path):
    bundle = r.retrieve(tmp_path, fetcher=fetcher)
    assert len(bundle["documents"]) == 2 and bundle["available"]
    assert bundle["api_calls"] == 0 and not bundle["oracle_authority"] and not bundle["autonomous_research"]
    before = tree(tmp_path)
    assert r.retrieve(tmp_path, completed=True, fetcher=lambda *a: pytest.fail("Fetch on replay")) == bundle
    assert tree(tmp_path) == before


def test_snapshot_tampering_fails_replay(tmp_path):
    r.retrieve(tmp_path, fetcher=fetcher)
    path = tmp_path / "validator/research/snapshots/sources.json"
    write_immutable_json(path.parent / "unexpected.json", {"unexpected": True})
    with pytest.raises(ValueError, match="snapshot"):
        r.retrieve(tmp_path, completed=True)


def test_failed_fetch_is_cached_not_silent_retry(tmp_path):
    def failed(*_):
        raise ValueError("Sanitized failure")
    bundle = r.retrieve(tmp_path, fetcher=failed)
    assert not bundle["available"] and bundle["error"] == "document_transport_unavailable"
    assert r.retrieve(tmp_path, fetcher=lambda *a: pytest.fail("Unexpected retry")) == bundle


def test_pending_fetch_or_missing_completed_never_retries(tmp_path):
    with pytest.raises(ValueError):
        r.retrieve(tmp_path, completed=True)
    r._save(tmp_path / "validator/research/intent.json", {"pending": True})
    with pytest.raises(ValueError):
        r.retrieve(tmp_path, fetcher=lambda *a: pytest.fail("Unexpected retry"))


def test_exact_quote_and_unseen_quotes_rejected(tmp_path):
    bundle = r.retrieve(tmp_path, fetcher=fetcher)
    good = [{"url": r.URLS[0], "quote": "Comparisons evaluate operands"}]
    assert r.validate_citations(good, bundle, required=True) == good
    for bad in ([], [{"url": r.URLS[0], "quote": "Fabricated reference text"}],
                [{"url": "https://example.org", "quote": "Comparisons evaluate operands"}], good + good):
        with pytest.raises(ValueError):
            r.validate_citations(bad, bundle, required=True)
    with pytest.raises(ValueError):
        r.validate_citations(good, None, required=False)


def test_research_single_proposal_call_quote_provenance(tmp_path, monkeypatch):
    bundle = r.retrieve(tmp_path, fetcher=fetcher)
    monkeypatch.setattr(r, "retrieve", lambda root, completed=False: bundle)
    api = API(tmp_path)
    api.raw = json.dumps({"search_policy": "Test equal operands and conditional boundaries", "when": "When legal",
        "citations": [{"url": r.URLS[0], "quote": "Comparisons evaluate operands"}]})
    row = v.propose(api, v.initial_state(), evidence(), arm="adaptive_research", root=tmp_path, key="research")
    assert row["valid"] and len(api.calls) == 1
    assert row["candidate_state"]["provenance"]["research_hash"] == bundle["record_hash"]
    assert row["citations"] == json.loads(api.raw)["citations"]
    assert not row["activation_authorized"]


def test_research_missing_or_false_quote_retains_old(tmp_path, monkeypatch):
    bundle = r.retrieve(tmp_path, fetcher=fetcher)
    monkeypatch.setattr(r, "retrieve", lambda root, completed=False: bundle)
    api = API(tmp_path)
    row = v.propose(api, v.initial_state(), evidence(), arm="adaptive_research", root=tmp_path, key="missing")
    assert not row["valid"] and row["candidate_state"] == v.initial_state() and len(api.calls) == 1


def test_context_is_only_predeclared_official_pages_and_bounded(tmp_path):
    bundle = r.retrieve(tmp_path, fetcher=fetcher)
    assert all(d["url"] in r.URLS and len(d["text"]) <= r.EXCERPT_CHARS for d in bundle["documents"])
    assert "docs.python.org" in r.URLS[0] and "conditional-expressions" in r.URLS[1]
