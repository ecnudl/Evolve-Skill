import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from skillopt.skill_validation import natural_documents as docs
from skillopt.validator_pilot.api import digest

URL = "https://docs.python.org/3.11/library/stdtypes.html#str.split"


def snapshot():
    raw = b"<html><p>Fixture only: words are split.</p></html>"
    text = "Fixture only: words are split."
    record = {"ok": True, "requested_url": URL, "final_url": URL, "attempts": [{"url": URL, "status": 200}],
              "snapshot_id": digest({"url": URL, "protocol": "bounded-research-v1"}),
              "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
              "raw_html_sha256": hashlib.sha256(raw).hexdigest(), "retrieved_utc": "fixture"}
    return {"snapshots": [{"record": record, "html_base64": base64.b64encode(raw).decode()}],
            "fetch_module_sha256": "fixture"}


def test_remote_documents_are_bounded_copied_verified_and_replayed(tmp_path, monkeypatch):
    commands = []
    def run(cmd, **kwargs):
        commands.append(cmd)
        assert json.loads(kwargs["input"]) == [URL]
        assert kwargs["timeout"] == 200 and "proxy_on" in cmd[-1]
        return SimpleNamespace(returncode=0, stdout=json.dumps(snapshot()))
    monkeypatch.setattr(docs.subprocess, "run", run)
    fetch = docs.SSHDocumentFetcher("/root/frozen-repo")
    sources = fetch([URL], tmp_path)
    assert sources[0]["status"] == "available" and sources[0]["information_origin"] == "research_document"
    assert fetch([URL], tmp_path) == sources and len(commands) == 1
    source_html = next(tmp_path.glob("documents/*/source.html"))
    source_html.write_bytes(b"tampered")
    # Restoring/corrupting an immutable snapshot is not a network retry.
    with pytest.raises(ValueError, match="snapshot differs"):
        fetch([URL], tmp_path)


@pytest.mark.parametrize("corruption", ["url", "redirect", "text", "html", "identity"])
def test_remote_document_tampering_is_rejected(tmp_path, monkeypatch, corruption):
    value = snapshot()
    record = value["snapshots"][0]["record"]
    if corruption == "url": record["requested_url"] = "https://example.com/answers"
    if corruption == "redirect": record["attempts"][0]["url"] = "https://docs.python.org/3.11/answers.html"
    if corruption == "text": record["text"] = "replacement"
    if corruption == "html": value["snapshots"][0]["html_base64"] = base64.b64encode(b"replacement").decode()
    if corruption == "identity": record["snapshot_id"] = "../../escape"
    monkeypatch.setattr(docs.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(value)))
    with pytest.raises(ValueError): docs.SSHDocumentFetcher("/root/frozen-repo")([URL], tmp_path)
    assert not (tmp_path / "remote_snapshots.json").exists()


def test_illegal_source_is_rejected_before_ssh(tmp_path, monkeypatch):
    monkeypatch.setattr(docs.subprocess, "run", lambda *a, **k: pytest.fail("network should not run"))
    with pytest.raises(ValueError):
        docs.SSHDocumentFetcher("/root/frozen-repo")(["https://github.com/task/solution"], tmp_path)
