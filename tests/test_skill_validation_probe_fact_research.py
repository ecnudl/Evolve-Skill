"""Scripted research transport fixtures; no model, network or task code runs."""
import copy
import hashlib
import json
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import probe_fact_research as research
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_checks import task

URL = "https://docs.python.org/3.11/library/stdtypes.html#str.split"
TEXT = "Fixture document: Python split with an explicit separator preserves empty fields."


def probe():
    return {"kind": "expected", "calls": [{"args": [[1, 2]], "kwargs": {}}], "expected": 12345,
            "obligation_id": "returns", "contract_quote": "Return the total for [1, 2].",
            "rationale": "Fallible proposed answer; research cannot repair it."}


def plan(status="investigate", urls=None):
    return {"status": status, "urls": ([URL] if status == "investigate" else []) if urls is None else urls,
            "reason": "Fixture missing external fact."}


def selection(status="evidence_selected", citations=None):
    return {"status": status, "citations": ([{"source_id": "fixture-document", "span_id": "s0"}]
            if status == "evidence_selected" else []) if citations is None else citations,
            "reason": "Selected one public document fragment.", "uncertainty": "Fixture selection is not task truth."}


class Calls:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def call(self, system, user, kind, **kwargs):
        self.requests.append((system, json.loads(user), kind, kwargs))
        answer = next(self.responses)
        if answer is None:
            return {"ok": False, "request_hash": digest([kind, user])}
        return {"ok": True, "request_hash": digest([kind, user]),
                "response": answer if isinstance(answer, str) else json.dumps(answer)}


class Fetcher:
    identity = {"kind": "scripted-document-fixture", "real_network": False}

    def __init__(self, transform=None, error=None):
        self.requests = []
        self.transform = transform
        self.error = error

    def __call__(self, urls, root):
        self.requests.append((urls, root))
        if self.error:
            raise self.error
        result = [{"source_id": "fixture-document", "url": URL, "status": "available", "text": TEXT,
                   "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
                   "retrieved_text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
                   "retrieved_utc": "fixture-no-real-retrieval", "source_version": "Python 3.11",
                   "hidden_extra": "HOST_ONLY_FETCHER_SENTINEL"}]
        if self.transform:
            self.transform(result)
        return result


def run(root, calls, fetcher, *, question="What is the documented separator behavior?", pipeline="fixture-pipeline"):
    return research.resolve_gap(task(), probe(), question, calls, root, pipeline_hash=digest(pipeline), source_fetcher=fetcher)


def test_selects_exact_bounded_source_without_modifying_probe(tmp_path):
    calls, fetcher = Calls([plan(), selection()]), Fetcher()
    original = copy.deepcopy(probe())
    result = run(tmp_path, calls, fetcher)
    assert verify(result) == result and result["status"] == "evidence_selected"
    assert len(calls.requests) == 2 and all(r[3]["max_tokens"] == 2048 for r in calls.requests)
    assert len(fetcher.requests) == 1 and result["probe"] == original
    source = result["sources"][0]
    assert source["text"] == TEXT and source["parent_source_id"] == "fixture-document"
    assert source["source_id"] == "fixture-document-s0" and source["information_origin"] == "research_document"
    assert source["url"] == URL and source["retrieved_text_sha256"] == hashlib.sha256(TEXT.encode()).hexdigest()
    assert result["verified"] is result["semantic_authority"] is result["deployment_authorized"] is False
    assert "HOST_ONLY_FETCHER_SENTINEL" not in json.dumps(result)


def test_model_view_has_no_host_identity_source_files_or_fetcher_extras(tmp_path):
    t = task()
    t = replace(t, contract=replace(t.contract, task_id="HOST_TASK_SENTINEL", family_id="HOST_FAMILY_SENTINEL"))
    calls, fetcher = Calls([plan(), selection()]), Fetcher()
    research.resolve_gap(t, probe(), "What fact is missing?", calls, tmp_path,
                         pipeline_hash=digest("fixture"), source_fetcher=fetcher)
    public = json.dumps(calls.requests)
    assert all(token not in public for token in ("HOST_TASK_SENTINEL", "HOST_FAMILY_SENTINEL",
                                                "HOST_ONLY_FETCHER_SENTINEL", "public_files", "canonical_solution"))
    assert all(r[1]["probe"]["expected"] == 12345 for r in calls.requests)
    assert "evidence_spans" in calls.requests[1][1]["sources"][0]


def test_frozen_replay_does_not_call_model_or_transport_again(tmp_path):
    calls, fetcher = Calls([plan(), selection()]), Fetcher()
    first = run(tmp_path, calls, fetcher)
    assert run(tmp_path, calls, fetcher) == first
    assert len(calls.requests) == 2 and len(fetcher.requests) == 1


@pytest.mark.parametrize("changed", ["question", "pipeline", "probe"])
def test_replay_namespace_binds_question_pipeline_and_probe(tmp_path, changed):
    calls, fetcher = Calls([plan("no_update"), plan("no_update")]), Fetcher()
    first = run(tmp_path, calls, fetcher)
    if changed == "probe":
        new_probe = {**probe(), "expected": 3}
        second = research.resolve_gap(task(), new_probe, "What is the documented separator behavior?", calls, tmp_path,
                                      pipeline_hash=digest("fixture-pipeline"), source_fetcher=fetcher)
    else:
        second = run(tmp_path, calls, fetcher, **{changed: "changed-input"})
    assert len(calls.requests) == 2 and first["binding"] != second["binding"]


@pytest.mark.parametrize("status", ["no_update", "insufficient_evidence"])
def test_planner_may_abstain_without_retrieval_or_synthesis(tmp_path, status):
    calls, fetcher = Calls([plan(status)]), Fetcher()
    result = run(tmp_path, calls, fetcher)
    assert result["status"] == status and not result["sources"]
    assert len(calls.requests) == 1 and not fetcher.requests


@pytest.mark.parametrize("status", ["no_update", "insufficient_evidence"])
def test_selector_can_decline_even_after_valid_document_retrieval(tmp_path, status):
    calls, fetcher = Calls([plan(), selection(status)]), Fetcher()
    result = run(tmp_path, calls, fetcher)
    assert result["status"] == status and result["sources"] == []
    assert len(result["retrieved_sources"]) == 1 and len(calls.requests) == 2


@pytest.mark.parametrize("urls", [[URL, URL], [URL, URL + "-a", URL + "-b"]])
def test_planner_url_count_and_uniqueness_are_enforced(tmp_path, urls):
    calls, fetcher = Calls([plan(urls=urls)]), Fetcher()
    result = run(tmp_path, calls, fetcher)
    assert result["status"] == "invalid" and not fetcher.requests


@pytest.mark.parametrize("url", [
    "https://github.com/project/answers/pull/1", "https://docs.python.org/3.12/library/stdtypes.html",
    "https://docs.python.org/3.11/library/stdtypes.html?answer=private", "https://127.0.0.1/3.11/library/stdtypes.html",
    "https://user:secret@docs.python.org/3.11/library/stdtypes.html", "http://docs.python.org/3.11/library/stdtypes.html",
])
def test_answer_destinations_wrong_versions_and_private_routes_fail_before_fetch(tmp_path, url):
    calls, fetcher = Calls([plan(urls=[url])]), Fetcher()
    result = run(tmp_path, calls, fetcher)
    assert result["status"] == "invalid" and not result["sources"] and not fetcher.requests


@pytest.mark.parametrize("citations", [
    [{"source_id": "invented", "span_id": "s0"}],
    [{"source_id": "fixture-document", "span_id": "s999"}],
    [{"source_id": "fixture-document", "quote": "invented quote"}],
    [{"source_id": "fixture-document", "span_id": "s0"}] * 2,
])
def test_invented_or_duplicate_citations_fail_closed(tmp_path, citations):
    result = run(tmp_path, Calls([plan(), selection(citations=citations)]), Fetcher())
    assert result["status"] == "invalid" and not result["sources"]


@pytest.mark.parametrize("field,value", [("url", "https://github.com/answers"), ("text_sha256", "bad"),
                                        ("source_version", "Python 3.12")])
def test_injected_transport_is_validated_before_model_receives_documents(tmp_path, field, value):
    calls = Calls([plan()])
    result = run(tmp_path, calls, Fetcher(lambda sources: sources[0].update({field: value})))
    assert result["status"] == "retrieval_failed" and len(calls.requests) == 1 and not result["sources"]


def test_failed_retrieval_is_a_normal_cached_outcome(tmp_path):
    calls, fetcher = Calls([plan()]), Fetcher(error=OSError("fixture network unavailable"))
    first = run(tmp_path, calls, fetcher)
    assert first["status"] == "retrieval_failed" and run(tmp_path, calls, fetcher) == first
    assert len(fetcher.requests) == 1


def test_api_failure_has_no_fabricated_research_fact(tmp_path):
    calls, fetcher = Calls([None]), Fetcher()
    result = run(tmp_path, calls, fetcher)
    assert result["status"] == "api_failure" and not result["sources"] and not fetcher.requests
    assert result["trace"][0]["ok"] is False


def test_selection_api_failure_cannot_expose_all_retrieved_sources_as_accepted(tmp_path):
    result = run(tmp_path, Calls([plan(), None]), Fetcher())
    assert result["status"] == "api_failure" and not result["sources"]
    assert len(result["retrieved_sources"]) == 1 and len(result["trace"]) == 2


def test_cached_result_integrity_is_checked_before_replay(tmp_path):
    calls, fetcher = Calls([plan("no_update")]), Fetcher()
    run(tmp_path, calls, fetcher)
    path = next(tmp_path.glob("gaps/*/result.json"))
    changed = json.loads(path.read_text())
    changed["status"] = "evidence_selected"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        run(tmp_path, calls, fetcher)
    assert len(calls.requests) == 1


def assert_terminal_invalid_and_replay(tmp_path, calls, fetcher, stage):
    result = run(tmp_path, calls, fetcher)
    assert verify(result) == result and result["status"] == "invalid"
    assert result["sources"] == [] and result["selection"] is None
    assert result["probe"] == probe()
    assert all(result[field] is False for field in (
        "hidden_or_artifact_access", "probe_modified", "verified", "semantic_authority", "deployment_authorized"))
    assert result["plan"] == (None if stage == "plan" else plan())
    assert len(result["retrieved_sources"]) == (0 if stage == "plan" else 1)
    assert [item["stage"] for item in result["trace"]] == (["plan"] if stage == "plan" else ["plan", "select"])
    assert len(calls.requests) == (1 if stage == "plan" else 2)
    assert len(fetcher.requests) == (0 if stage == "plan" else 1)
    requests_before, fetches_before = copy.deepcopy(calls.requests), copy.deepcopy(fetcher.requests)
    assert run(tmp_path, calls, fetcher) == result
    assert calls.requests == requests_before and fetcher.requests == fetches_before
    return result


@pytest.mark.parametrize("stage", ["plan", "selection"])
def test_deeply_nested_model_json_is_terminal_invalid_not_a_crash_or_retry(tmp_path, stage):
    nested = '{"nested":' + '[' * 2000 + '0' + ']' * 2000 + '}'
    responses = [nested] if stage == "plan" else [plan(), nested]
    # CPython versions may reject during decoding or decode successfully and
    # reject the wrong schema. The observable safety contract is the same.
    assert_terminal_invalid_and_replay(tmp_path, Calls(responses), Fetcher(), stage)


@pytest.mark.parametrize("stage", ["plan", "selection"])
@pytest.mark.parametrize("error_type", [RecursionError, ValueError])
def test_decode_failures_are_terminal_invalid_at_each_stage(tmp_path, monkeypatch, stage, error_type):
    sentinel = "fixture-targeted-decoder-failure"
    original_decode = research._decode
    injected = []

    def decode(raw):
        if raw == sentinel:
            injected.append(error_type)
            raise error_type("fixture parser rejection")
        return original_decode(raw)

    monkeypatch.setattr(research, "_decode", decode)
    responses = [sentinel] if stage == "plan" else [plan(), sentinel]
    result = assert_terminal_invalid_and_replay(tmp_path, Calls(responses), Fetcher(), stage)
    assert result["failure_type"] == error_type.__name__
    assert injected == [error_type]  # The valid plan and cached replay use the real decoder.


@pytest.mark.parametrize("corruption", ["probe", "question", "verified", "semantic_authority", "status", "sources",
                                         "selection", "retrieved_source", "non_success_sources"])
def test_valid_hash_does_not_authorize_inconsistent_cached_evidence(tmp_path, corruption):
    calls, fetcher = Calls([plan(), selection()]), Fetcher()
    run(tmp_path, calls, fetcher)
    path = next(tmp_path.glob("gaps/*/result.json"))
    changed = json.loads(path.read_text())
    if corruption == "probe": changed["probe"]["expected"] = 3
    if corruption == "question": changed["question"] = "Another question"
    if corruption in {"verified", "semantic_authority"}: changed[corruption] = True
    if corruption == "status": changed["status"] = "no_update"
    if corruption == "sources": changed["sources"][0]["text"] = "Invented quote"
    if corruption == "selection": changed["selection"]["citations"][0]["span_id"] = "s999"
    if corruption == "retrieved_source": changed["retrieved_sources"][0]["text"] = "Changed original text"
    if corruption == "non_success_sources":
        changed.update(status="api_failure", selection=None)
    changed.pop("record_hash")
    path.write_text(json.dumps(seal(changed)))
    with pytest.raises(ValueError):
        run(tmp_path, calls, fetcher)
    assert len(calls.requests) == 2


def test_runtime_budget_failure_is_named_and_not_retried(tmp_path):
    class BudgetCalls:
        count = 0

        def call(self, *args, **kwargs):
            self.count += 1
            raise RuntimeError("Frozen logical request budget exhausted")

    calls, fetcher = BudgetCalls(), Fetcher()
    result = run(tmp_path, calls, fetcher)
    assert result["status"] == "api_failure" and result["failure_code"] == "model_budget_exhausted"
    assert result["failure_stage"] == "model_plan"
    assert run(tmp_path, calls, fetcher) == result and calls.count == 1


def test_selection_cannot_change_expected_or_add_code(tmp_path):
    attempted = {**selection(), "expected": 3, "script": "print('never execute')"}
    result = run(tmp_path, Calls([plan(), attempted]), Fetcher())
    assert result["status"] == "invalid" and not result["sources"] and result["probe"]["expected"] == 12345


def test_duplicate_json_fields_are_not_silently_normalized(tmp_path):
    raw = '{"status":"no_update","status":"investigate","urls":[],"reason":"bad"}'
    result = run(tmp_path, Calls([raw]), Fetcher())
    assert result["status"] == "invalid"


def test_whole_document_json_fence_is_supported_without_semantic_repair(tmp_path):
    raw = "```json\n" + json.dumps(plan("no_update")) + "\n```"
    result = run(tmp_path, Calls([raw]), Fetcher())
    assert result["status"] == "no_update"


def test_custom_document_transport_requires_bound_identity(tmp_path):
    with pytest.raises(ValueError, match="explicit identity"):
        run(tmp_path, Calls([]), lambda urls, root: [])


@pytest.mark.parametrize("origin", [None, False, [], {}, "", "caller_declared", "hidden_audit", "autonomous_discovery"])
def test_invalid_question_origin_is_rejected_before_any_model_or_retrieval(tmp_path, origin):
    calls, fetcher = Calls([]), Fetcher()
    with pytest.raises(ValueError, match="question origin"):
        research.resolve_gap(task(), probe(), "What fact is missing?", calls, tmp_path,
            pipeline_hash=digest("fixture"), source_fetcher=fetcher, question_origin=origin)
    assert not calls.requests and not fetcher.requests and not list(tmp_path.rglob("result.json"))


def test_caller_declared_origin_has_its_own_bound_cache_namespace(tmp_path):
    calls, fetcher = Calls([plan("no_update"), plan("no_update")]), Fetcher()
    kwargs = {"pipeline_hash": digest("fixture"), "source_fetcher": fetcher}
    default = research.resolve_gap(task(), probe(), "What fact is missing?", calls, tmp_path, **kwargs)
    explicit = research.resolve_gap(task(), probe(), "What fact is missing?", calls, tmp_path,
        question_origin="caller_declared_fixture_gap", **kwargs)
    assert default["question_origin"] == default["binding"]["question_origin"] == research.REVIEW_QUESTION_ORIGIN
    assert explicit["question_origin"] == explicit["binding"]["question_origin"] == "caller_declared_fixture_gap"
    assert default["binding"] != explicit["binding"] and len(calls.requests) == 2
    assert research.resolve_gap(task(), probe(), "What fact is missing?", calls, tmp_path, **kwargs) == default
    assert research.resolve_gap(task(), probe(), "What fact is missing?", calls, tmp_path,
        question_origin="caller_declared_fixture_gap", **kwargs) == explicit
    assert len(calls.requests) == 2 and not fetcher.requests


@pytest.mark.parametrize("corruption", ["record", "binding", "both", "missing"])
def test_resealed_question_origin_mismatch_cannot_be_reused(tmp_path, corruption):
    calls, fetcher = Calls([plan("no_update")]), Fetcher()
    run(tmp_path, calls, fetcher)
    path = next(tmp_path.glob("gaps/*/result.json"))
    changed = json.loads(path.read_text())
    if corruption in {"record", "both"}:
        changed["question_origin"] = "caller_declared_fixture_gap"
    if corruption in {"binding", "both"}:
        changed["binding"]["question_origin"] = "caller_declared_fixture_gap"
    if corruption == "missing":
        changed.pop("question_origin")
    changed.pop("record_hash")
    path.write_text(json.dumps(seal(changed)))
    with pytest.raises(ValueError, match="identity|question origin"):
        run(tmp_path, calls, fetcher)
    assert len(calls.requests) == 1 and not fetcher.requests
