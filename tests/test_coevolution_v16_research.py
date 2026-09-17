"""New presentation fixtures only; no mutation of frozen V15 modules or files."""

import hashlib
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v15 import research as old
from skillopt.coevolution_v16 import research as r
from skillopt.validator_pilot.api import write_immutable_json
from tests.test_coevolution_v15_validator import tree

TEXT = "Numbers have precise meanings.\n Conditional expressions evaluate\nonly the selected branch."


def fetch(urls, root):
    records = [{"requested_url": url, "ok": True, "text": TEXT,
                "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest()} for url in urls]
    write_immutable_json(root / "sources.json", records)
    return records


def test_projection_changes_only_presented_whitespace_and_preserves_raw(tmp_path):
    raw = old.retrieve(tmp_path, fetcher=fetch)
    raw_tree = tree(tmp_path / "validator/research")
    shown = r.retrieve(tmp_path, fetcher=lambda *a: pytest.fail("Cached source must not refetch"))
    assert tree(tmp_path / "validator/research") == raw_tree
    assert shown["raw_bundle_hash"] == raw["record_hash"]
    assert shown["raw_documents"] == raw["documents"]
    assert shown["sources"] == raw["sources"] and shown["snapshot_files"] == raw["snapshot_files"]
    assert not shown["visible_content_expanded"] and not shown["model_quotes_normalized"]
    for original, document, projection in zip(raw["documents"], shown["documents"], shown["projections"]):
        assert document["text"] == " ".join(original["text"].split())
        assert set(document) == set(original)
        assert all(document[k] == original[k] for k in original if k != "text")
        assert projection["raw_excerpt_sha256"] == hashlib.sha256(original["text"].encode()).hexdigest()
        assert projection["presented_excerpt_sha256"] == hashlib.sha256(document["text"].encode()).hexdigest()
        assert projection["projection_version"] == r.PROJECTION_VERSION


def test_visible_exact_citation_passes_without_relaxing_checker(tmp_path):
    raw = old.retrieve(tmp_path, fetcher=fetch)
    shown = r.retrieve(tmp_path)
    citation = [{"url": r.URLS[0], "quote": "expressions evaluate only the selected branch."}]
    assert r.validate_citations is old.validate_citations
    with pytest.raises(ValueError):
        old.validate_citations(citation, raw, required=True)
    assert r.validate_citations(citation, shown, required=True) == citation
    for quote in ("expressions evaluate\nonly the selected branch.", "expressions evaluate every branch.",
                  "Expressions evaluate only the selected branch."):
        with pytest.raises(ValueError):
            r.validate_citations([{"url": r.URLS[0], "quote": quote}], shown, required=True)


def test_normalize_after_truncation_never_admits_later_source_content(tmp_path):
    sentinel = "UNSEEN source sentence must never enter the visible context."
    raw_text = "Earlier sentence. " + "\n " * 1741 + sentinel

    def long_fetch(urls, root):
        records = [{"requested_url": url, "ok": True, "text": raw_text,
                    "text_sha256": hashlib.sha256(raw_text.encode()).hexdigest()} for url in urls]
        write_immutable_json(root / "sources.json", records)
        return records

    shown = r.retrieve(tmp_path, fetcher=long_fetch)
    assert all(sentinel not in d["text"] and "UNSEEN" not in d["text"] for d in shown["documents"])
    assert all(len(d["text"]) <= 3500 for d in shown["raw_documents"])
    with pytest.raises(ValueError):
        r.validate_citations([{"url": r.URLS[0], "quote": sentinel}], shown, required=True)


def test_completed_projection_replay_zero_fetch_and_same_bytes(tmp_path, monkeypatch):
    expected = r.retrieve(tmp_path, fetcher=fetch)
    before = tree(tmp_path)
    monkeypatch.setattr(r, "fetch_sources", lambda *a: pytest.fail("No document fetch in completed replay"))
    assert r.retrieve(tmp_path, completed=True) == expected
    assert before == tree(tmp_path)


def test_completed_missing_projection_does_not_reconstruct(tmp_path):
    old.retrieve(tmp_path, fetcher=fetch)
    before = tree(tmp_path)
    with pytest.raises(ValueError, match="missing"):
        r.retrieve(tmp_path, completed=True)
    assert before == tree(tmp_path)


def test_raw_snapshot_and_presentation_tampering_rejected(tmp_path):
    r.retrieve(tmp_path, fetcher=fetch)
    write_immutable_json(tmp_path / "validator/research/snapshots/extra.json", {"unexpected": True})
    with pytest.raises(ValueError, match="snapshot"):
        r.retrieve(tmp_path, completed=True)


def test_presentation_no_reference_or_fetched_text_extension(tmp_path):
    raw = old.retrieve(tmp_path, fetcher=fetch)
    altered = {k: deepcopy(v) for k, v in raw.items() if k != "record_hash"}
    altered["documents"][0]["text"] += " Extra undocumented requirement."
    with pytest.raises(ValueError, match="original bounded"):
        r.present(seal(altered))


def test_failed_raw_retrieval_stays_unavailable_no_retry(tmp_path):
    def unavailable(*_):
        raise ValueError("fixture unavailable")

    shown = r.retrieve(tmp_path, fetcher=unavailable)
    assert not shown["available"] and shown["documents"] == [] and shown["projections"] == []
    assert r.retrieve(tmp_path, completed=True) == shown


@pytest.mark.parametrize("text", ["a\tb\nc", " a\u00a0b\r\nc ", " a\v\fb  c "])
def test_registered_unicode_whitespace_projection(text, tmp_path):
    def whitespace_fetch(urls, root):
        records = [{"requested_url": url, "ok": True, "text": text,
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest()} for url in urls]
        write_immutable_json(root / "sources.json", records)
        return records

    shown = r.retrieve(tmp_path, fetcher=whitespace_fetch)
    assert all(d["text"] == "a b c" for d in shown["documents"])
