"""Same algorithm, single changed document presentation; zero live model calls."""

import json
from pathlib import Path

import pytest

from skillopt.coevolution_v15 import research as old_research
from skillopt.coevolution_v15 import validator as old
from skillopt.coevolution_v16 import research
from skillopt.coevolution_v16 import validator as v
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v15_validator import API, evidence, tree
from tests.test_coevolution_v16_research import fetch


def test_unchanged_algorithms_are_the_original_functions():
    for name in ("initial_state", "validate_state", "search", "assess", "calibrate"):
        assert getattr(v, name) is getattr(old, name)
    assert v.STATE_VERSION == old.VERSION != v.VERSION
    assert v.SEARCH_TOKENS == old.SEARCH_TOKENS == v.PROPOSAL_TOKENS == old.PROPOSAL_TOKENS


def test_no_document_prompt_exactly_unchanged_but_requests_distinct(tmp_path):
    first, second = API(tmp_path / "v15"), API(tmp_path / "v16")
    old_row = old.propose(first, old.initial_state(), evidence(), arm="adaptive", root=tmp_path / "v15", key="same")
    new_row = v.propose(second, v.initial_state(), evidence(), arm="adaptive", root=tmp_path / "v16", key="same")
    assert first.calls[0]["system"] == second.calls[0]["system"]
    assert first.calls[0]["user"] == second.calls[0]["user"]
    assert first.calls[0]["kind"] == "v15_validator_proposal"
    assert second.calls[0]["kind"] == "v16_validator_proposal"
    assert old_row["request_hash"] != new_row["request_hash"]
    assert new_row["candidate_state"]["version"] == old.VERSION
    assert new_row["candidate_state"]["provenance"]["proposal_version"] == v.VERSION
    assert not new_row["activation_authorized"]


def test_research_only_visible_text_changes_no_repair_and_exact_provenance(tmp_path):
    first_root, second_root = tmp_path / "v15", tmp_path / "v16"
    old_research.retrieve(first_root, fetcher=fetch)
    shown = research.retrieve(second_root, fetcher=fetch)
    first, second = API(first_root), API(second_root)
    response = json.dumps({"search_policy": "Compare legal branch-sensitive controls", "when": "Only within schema",
        "citations": [{"url": research.URLS[0], "quote": "expressions evaluate only the selected branch."}]})
    first.raw = second.raw = response
    rejected = old.propose(first, old.initial_state(), evidence(), arm="adaptive_research", root=first_root, key="p")
    accepted_delivery = v.propose(second, v.initial_state(), evidence(), arm="adaptive_research", root=second_root, key="p")
    assert not rejected["valid"] and accepted_delivery["valid"]
    assert len(first.calls) == len(second.calls) == 1
    assert first.calls[0]["system"] == second.calls[0]["system"]
    a, b = json.loads(first.calls[0]["user"]), json.loads(second.calls[0]["user"])
    assert set(a) == set(b)
    assert all(a[k] == b[k] for k in a if k != "official_excerpts")
    for old_doc, new_doc in zip(a["official_excerpts"], b["official_excerpts"]):
        assert new_doc == {**old_doc, "text": " ".join(old_doc["text"].split())}
    assert accepted_delivery["research"] == shown
    assert accepted_delivery["candidate_state"]["provenance"]["presentation_hash"] == shown["record_hash"]
    receipt = json.loads((second.root / "calls" / (accepted_delivery["request_hash"] + ".json")).read_text())
    assert receipt["response"] == response and digest(receipt) == accepted_delivery["receipt_hash"]


@pytest.mark.parametrize("response", [
    '{"search_policy":"good","when":"legal","citations":[]}',
    '{"search_policy":"good","when":"legal","citations":[{"url":"bad","quote":"made up document words"}]}',
    '```json\n{"search_policy":"good","when":"legal","citations":[]}\n```',
    '{truncated',
])
def test_invalid_citations_or_delivery_remain_invalid_no_resampling(tmp_path, response):
    research.retrieve(tmp_path, fetcher=fetch)
    api = API(tmp_path)
    api.raw = response
    row = v.propose(api, v.initial_state(), evidence(), arm="adaptive_research", root=tmp_path, key="p")
    assert not row["valid"] and row["candidate_state"] == v.initial_state() and len(api.calls) == 1


def test_completed_proposal_replay_zero_api_fetch_and_byte_identical(tmp_path, monkeypatch):
    research.retrieve(tmp_path, fetcher=fetch)
    api = API(tmp_path)
    api.raw = json.dumps({"search_policy": "Check branches", "when": "Where legal",
                         "citations": [{"url": research.URLS[0], "quote": "Numbers have precise meanings."}]})
    result = v.propose(api, v.initial_state(), evidence(), arm="adaptive_research", root=tmp_path, key="p")
    assert result["valid"]
    before = tree(tmp_path)
    monkeypatch.setattr(api, "call", lambda **k: pytest.fail("No API during replay"))
    monkeypatch.setattr(research, "fetch_sources", lambda *a: pytest.fail("No fetch during replay"))
    assert v.propose(api, v.initial_state(), evidence(), arm="adaptive_research", root=tmp_path, key="p", completed=True) == result
    assert before == tree(tmp_path)


def test_failure_receipt_cached_not_retried(tmp_path):
    api = API(tmp_path)
    api.ok = False
    row = v.propose(api, v.initial_state(), evidence(), arm="adaptive", root=tmp_path, key="p")
    assert row["error"] == "api_unknown"
    assert v.propose(api, v.initial_state(), evidence(), arm="adaptive", root=tmp_path, key="p") == row
    assert len(api.calls) == 1


def test_non_development_rejected_before_request(tmp_path):
    api = API(tmp_path)
    with pytest.raises(ValueError):
        v.propose(api, v.initial_state(), evidence(nested={"phase": "final"}), arm="adaptive", root=tmp_path, key="p")
    assert not api.calls


def test_pause_callback_before_any_intent(tmp_path):
    api = API(tmp_path)

    def paused():
        raise RuntimeError("paused fixture")

    api.before_validator_request = paused
    with pytest.raises(RuntimeError, match="paused"):
        v.propose(api, v.initial_state(), evidence(), arm="adaptive", root=tmp_path, key="p")
    assert not api.calls and not list(tmp_path.rglob("*.json"))


def test_frozen_v15_module_sources_not_modified_by_v16_calls(tmp_path):
    paths = [Path(old.__file__), Path(old_research.__file__)]
    before = {p: p.read_bytes() for p in paths}
    functions = (old.propose, old_research.retrieve, old_research.fetch_sources)
    api = API(tmp_path)
    v.propose(api, v.initial_state(), evidence(), arm="adaptive", root=tmp_path, key="p")
    assert before == {p: p.read_bytes() for p in paths}
    assert functions == (old.propose, old_research.retrieve, old_research.fetch_sources)
