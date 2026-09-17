"""One-call structural diagnostic; source stages, model and documents are fake."""

import json
from copy import deepcopy

import pytest

from skillopt import research_contract_repair as previous
from skillopt.coevolution_v7 import research
from skillopt.coevolution_v8 import patch_diagnostic as patch
from tests.test_research_contract_repair import FakeAPI, bytes_under, outputs, source_fixture

BROKEN = ('{"changes":[{"check_id":"coding_probe","finding_ids":["f1"],"search":"Try boundary probes.",'
          '"when":"Only where explicitly applicable.","limits":"Finite evidence only.",'
          '"rationale":"Investigate unknown evidence."],"source_refs":[]}')


def setup(tmp_path, monkeypatch):
    repo, original, source, packets, _ = source_fixture(tmp_path)
    values = outputs(packets)
    values[2] = BROKEN
    first = FakeAPI(source / "api", values)
    monkeypatch.setattr(research, "fetch_sources", lambda *_: [])
    previous.run(repo, original, source, api_factory=lambda *_a, **_k: first, original_run_stopped=True)
    root = repo / "outputs/research_patch_diagnostic/patch-only"
    api = FakeAPI(root / "api", [outputs(packets)[2]])
    return repo, original, source, root, api


def test_one_call_keeps_source_plan_findings_and_receipts_unchanged(tmp_path, monkeypatch):
    repo, original, source, root, api = setup(tmp_path, monkeypatch)
    before, original_before = bytes_under(source), bytes_under(original)
    result = patch.run(repo, source, root, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    assert result["status"] == "diagnostic_proposal_ready" and result["calls_used"] == len(api.calls) == 1
    assert result["activation"] == "never" and not result["original_result_replacement"]
    assert not result["historical_fallback_used"] and result["findings_unchanged"] and result["new_document_fetches"] == 0
    previous_result = json.loads((source / "result.json").read_text())
    assert result["research"] == previous_result["research"]
    assert result["source_chain"][1]["record_hash"] == previous_result["record_hash"]
    payload = json.loads(api.calls[0]["request"]["user"])
    assert payload["patch_contract_diagnostic"]["original_invalid_response"] == BROKEN
    assert payload["findings"] == previous_result["research"]["findings"]
    assert api.calls[0]["request"]["max_tokens"] == 6000
    assert bytes_under(source) == before and bytes_under(original) == original_before


def test_complete_resume_is_strictly_readonly_no_clients_or_fetch(tmp_path, monkeypatch):
    repo, _, source, root, api = setup(tmp_path, monkeypatch)
    result = patch.run(repo, source, root, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    before = bytes_under(root)

    def prohibited(*_a, **_k):
        raise AssertionError("No API, source fetch, or writes on completed resume")

    monkeypatch.setattr(previous, "write_immutable_json", prohibited)
    monkeypatch.setattr(patch, "write_immutable_json", prohibited)
    monkeypatch.setattr(research, "fetch_sources", prohibited)
    assert patch.run(repo, source, root, api_factory=prohibited) == result
    assert bytes_under(root) == before


@pytest.mark.parametrize("response", [None, "malformed", BROKEN, {"changes": [], "rationale": "x", "source_refs": []}])
def test_new_invalid_patch_is_terminal_no_second_repair(tmp_path, monkeypatch, response):
    repo, _, source, root, api = setup(tmp_path, monkeypatch)
    api.responses = [response]
    result = patch.run(repo, source, root, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    assert result["proposed_rubric"] is None and len(api.calls) == 1
    assert patch.run(repo, source, root, api_factory=lambda *_a, **_k: pytest.fail("no retry")) == result


@pytest.mark.parametrize("kind", ["duplicate_check", "unknown_finding", "invented_source"])
def test_strict_patch_evidence_guards_not_relaxed(tmp_path, monkeypatch, kind):
    repo, _, source, root, api = setup(tmp_path, monkeypatch)
    value = deepcopy(api.responses[0])
    if kind == "duplicate_check":
        value["changes"] *= 2
    elif kind == "unknown_finding":
        value["changes"][0]["finding_ids"] = ["f99"]
    else:
        value["source_refs"] = ["https://docs.python.org/3/library/stdtypes.html"]
    api.responses = [value]
    result = patch.run(repo, source, root, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    assert result["proposed_rubric"] is None and result["calls_used"] == 1


@pytest.mark.parametrize("missing", ["identity.json", "structural_feedback.json", "evidence_view.json", "patch_repair.json", "call_intent.json"])
def test_completed_missing_metadata_is_not_reconstructed(tmp_path, monkeypatch, missing):
    repo, _, source, root, api = setup(tmp_path, monkeypatch)
    patch.run(repo, source, root, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    (root / missing).unlink()
    before = bytes_under(root)
    with pytest.raises(ValueError):
        patch.run(repo, source, root, api_factory=lambda *_a, **_k: pytest.fail("no network"))
    assert bytes_under(root) == before


def test_output_symlink_and_overlap_are_rejected_before_new_call(tmp_path, monkeypatch):
    repo, _, source, root, api = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        patch.run(repo, source, source, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    root.mkdir(parents=True)
    (root / "link").symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        patch.run(repo, source, root, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    assert api.calls == []


def test_attestation_and_syntax_specific_eligibility(tmp_path, monkeypatch):
    repo, _, source, root, api = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="attestation"):
        patch.run(repo, source, root, api_factory=lambda *_a, **_k: api)
    with pytest.raises(ValueError, match="only for"):
        patch.structural_feedback('{"changes":[]}')
    assert not root.exists() and api.calls == []


def test_unresolved_new_call_is_not_reissued(tmp_path, monkeypatch):
    repo, _, source, root, api = setup(tmp_path, monkeypatch)
    patch.run(repo, source, root, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    (root / "result.json").unlink()
    (root / "patch_repair.json").unlink()
    next((root / "api/calls").glob("*.json")).unlink()
    with pytest.raises(ValueError, match="unresolved"):
        patch.run(repo, source, root, api_factory=lambda *_a, **_k: pytest.fail("no retry"), source_run_stopped=True)
