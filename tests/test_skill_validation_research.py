"""Engineering fixtures only: proposal acceptance is not verifier authorization."""
from __future__ import annotations

import hashlib
import json

import pytest

from skillopt.skill_validation.fixtures import smoke_cases
from skillopt.skill_validation.models import RubricVersion
from skillopt.skill_validation.research import (
    BoundedResearch,
    ModelReply,
    ResearchBudget,
    approved_url,
    fetch_documents,
    fixed_rubric,
    validate_development_view,
)
from skillopt.skill_validation.views import DevelopmentGap, research_development_view

URL = "https://docs.python.org/3.11/library/copy.html"
QUOTE = "Assignment statements in Python do not copy objects."


def view():
    _, task, artifact, evidence = next(iter(smoke_cases()))
    gap = DevelopmentGap(task.content_hash, artifact.artifact_hash, "input", "missed_error", "host-only-audit")
    return research_development_view(task, artifact, evidence, gaps=(gap,))


def rule(method="input_state", citations=None):
    return {
        "id": method.replace("_", "-"),
        "obligation_kind": "input_preservation" if method == "input_state" else "requested_behavior",
        "method": method, "applicability": "explicit_obligation", "exception": "absent_obligation",
        "evidence_requirement": "Require actual public execution evidence; no language-only claim.",
        "citations": citations or [], "uncertainty": "Independent calibration is still required.",
    }


def update(rules=None):
    return {"status": "update", "rules": [rule()] if rules is None else rules, "reason": "Investigate the omitted state check."}


class Model:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, system, user, max_output_tokens):
        self.calls.append((system, json.loads(user), max_output_tokens))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(json.loads(user))
        return value if isinstance(value, ModelReply) else ModelReply(value, 100, 50)


def plan(urls=None):
    return {"status": "investigate", "questions": ["Does a public input-preservation obligation lack executed state evidence?"],
            "urls": urls or []}


def source_fetch(urls, root):
    return [{"requested_url": url, "final_url": url, "ok": True, "text": QUOTE,
             "text_sha256": hashlib.sha256(QUOTE.encode()).hexdigest(), "retrieved_utc": "2026-09-18T00:00:00Z"}
            for url in urls]


def test_fixed_has_no_model_or_retrieval():
    def forbidden(*args):
        raise AssertionError("No model/retrieval in fixed arm")
    result = BoundedResearch(model=forbidden, fetcher=forbidden).propose("fixed", fixed_rubric(), [view()])
    assert result.status == "no_update" and result.rubric == fixed_rubric()
    assert result.costs["model_calls"] == result.costs["execution_calls"] == 0
    assert result.requires_calibration is True


def test_no_research_has_same_recipe_interface_no_docs():
    model = Model([plan(), update()])
    result = BoundedResearch(model=model).propose("adaptive_no_research", fixed_rubric(), [view()])
    assert result.status == "update"
    assert result.rubric.checks[0].method == "input_state"
    assert result.rubric.parent_hash == fixed_rubric().content_hash
    assert result.costs["input_tokens"] == 200 and result.costs["output_tokens"] == 100
    assert result.costs["retrieval_requests"] == 0
    assert result.findings[0]["execution_confirmed"] is False
    assert result.findings[0]["independent_discovery_established"] is False
    assert len(model.calls) == 2


def test_research_source_gap_recipe_trace_and_serialization(tmp_path):
    def synthesis(payload):
        citation = {"source_id": payload["sources"][0]["source_id"], "quote": QUOTE}
        return update([rule(citations=[citation])])
    model = Model([plan([URL]), synthesis])
    result = BoundedResearch(model=model, fetcher=source_fetch, cache_root=tmp_path).propose(
        "adaptive_research", fixed_rubric(), [view()])
    assert result.status == "update"
    assert result.sources[0]["source_version"] == "Python 3.11"
    assert result.findings[0]["citation_validation"] == "provenance_only"
    assert result.costs["retrieval_requests"] == 1
    assert [row["stage"] for row in result.trace] == ["input", "plan", "retrieval", "proposal"]
    assert RubricVersion.from_dict(result.to_dict()["rubric"]) == result.rubric
    manifests = list(tmp_path.glob("*/namespace.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    assert manifest["purpose"] == "proposal_development_not_blind_evaluation"
    assert manifest["questions"] and manifest["source_version"] == "Python 3.11"
    assert "host-only-audit" not in json.dumps(result.to_dict())
    assert model.calls[1][1]["development"][0]["development_gaps"][0]["research_independent_discovery"] is False


def test_both_adaptive_arms_share_evidence_and_project_context(tmp_path):
    context = [{"path": "README.md", "content": "Public project API description.",
                "information_origin": "shared_public_project_context"}]
    a = Model([plan(), update()])
    b = Model([plan([URL]), update()])
    outputs = [BoundedResearch(model=m, fetcher=source_fetch, cache_root=tmp_path).propose(
        arm, fixed_rubric(), [view()], project_context=context)
        for m, arm in ((a, "adaptive_no_research"), (b, "adaptive_research"))]
    for field in ("development", "shared_project_context", "public_recipe_methods"):
        assert a.calls[0][1][field] == b.calls[0][1][field]
    assert outputs[0].trace[0]["shared_evidence_hash"] == outputs[1].trace[0]["shared_evidence_hash"]
    assert outputs[0].costs["budget"] == outputs[1].costs["budget"]
    assert outputs[1].costs["equal_budget_cap_not_equal_realized_cost"]


@pytest.mark.parametrize("position", ["root", "task", "artifact", "obligation", "file", "receipt", "observation", "gap"])
def test_nested_hidden_metadata_never_reaches_model(position):
    sample = view()
    sample["artifact"]["files"] = [{"path": "solution.py", "content": "pass"}]
    target = {"root": sample, "task": sample["task"], "artifact": sample["artifact"],
              "obligation": sample["task"]["obligations"][0], "file": sample["artifact"]["files"][0],
              "receipt": sample["public_execution"][0], "observation": sample["public_execution"][0]["observations"][0],
              "gap": sample["development_gaps"][0]}[position]
    target["hidden_expected"] = "SENTINEL-ANSWER"
    model = Model([])
    with pytest.raises(ValueError):
        BoundedResearch(model=model).propose("adaptive_no_research", fixed_rubric(), [sample])
    assert not model.calls


@pytest.mark.parametrize("purpose", ["final", "verifier_calibration", "skill_confirmation", "development", None])
def test_wrong_purpose_rejected(purpose):
    sample = view()
    sample["purpose"] = purpose
    with pytest.raises(ValueError):
        validate_development_view(sample)


def test_audit_summary_cannot_claim_research_discovery():
    sample = view()
    sample["development_gaps"][0]["research_independent_discovery"] = True
    with pytest.raises(ValueError, match="discovery"):
        validate_development_view(sample)


@pytest.mark.parametrize("url", [
    "https://github.com/org/repo/pull/1", "https://docs.python.org/3.12/library/copy.html",
    "https://docs.python.org/3.11/library/copy.html?task=answer", "https://docs.python.org/3.11/../library/copy.html",
    "https://docs.python.org/3.11/library/copy.html#section?answer", "https://developer.mozilla.org/en-US/docs/Web",
    "https://user:password@docs.python.org/3.11/library/copy.html", "http://docs.python.org/3.11/library/copy.html",
    "https://docs.python.org/3.11/library/copy.html#%0A", "https://127.0.0.1/3.11/library/copy.html",
])
def test_answer_wrong_version_and_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        approved_url(url)


def test_fetch_redirect_is_checked_before_network(monkeypatch, tmp_path):
    def bad_redirect(url, root, client):
        client.stream("GET", "https://docs.python.org/3.11/benchmark-solutions.html")
        raise AssertionError("must be unreachable")
    monkeypatch.setattr("skillopt.skill_validation.research.legacy._fetch_one", bad_redirect)
    with pytest.raises(ValueError, match="preregistered"):
        fetch_documents([URL], tmp_path)


def test_cache_redirect_is_rechecked(monkeypatch, tmp_path):
    def cached(url, root, client):
        return {"requested_url": url, "ok": True, "final_url": "https://docs.python.org/3.12/library/copy.html"}
    monkeypatch.setattr("skillopt.skill_validation.research.legacy._fetch_one", cached)
    with pytest.raises(ValueError, match="preregistered"):
        fetch_documents([URL], tmp_path)


def test_no_research_cannot_use_document_tool(tmp_path):
    model = Model([plan([URL])])
    def forbidden(*args):
        raise AssertionError("Cannot fetch")
    result = BoundedResearch(model=model, fetcher=forbidden, cache_root=tmp_path).propose(
        "adaptive_no_research", fixed_rubric(), [view()])
    assert result.status == "invalid" and len(model.calls) == 1


@pytest.mark.parametrize("status", ["no_update", "insufficient_evidence"])
def test_valid_non_update_paths(status):
    for responses in ([{"status": status, "questions": [], "urls": []}],
                      [plan(), {"status": status, "rules": [], "reason": "No supported new check."}]):
        model = Model(responses)
        result = BoundedResearch(model=model).propose("adaptive_no_research", fixed_rubric(), [view()])
        assert result.status == status and result.rubric == fixed_rubric()


@pytest.mark.parametrize("failure", ["unavailable", "exception", "hash", "mismatched_url"])
def test_retrieval_failures_not_fabricated_as_findings(tmp_path, failure):
    def fetch(urls, root):
        if failure == "exception":
            raise RuntimeError("SECRET-KEY")
        if failure == "unavailable":
            return [{"requested_url": URL, "ok": False}]
        records = source_fetch(urls, root)
        records[0]["text_sha256" if failure == "hash" else "requested_url"] = "invalid"
        return records
    model = Model([plan([URL])])
    result = BoundedResearch(model=model, fetcher=fetch, cache_root=tmp_path).propose(
        "adaptive_research", fixed_rubric(), [view()])
    assert result.status == "retrieval_failed" and not result.findings and result.rubric is None
    assert result.costs["retrieval_requests"] == 1 and len(model.calls) == 1
    assert "SECRET-KEY" not in json.dumps(result.to_dict())


def test_unknown_token_usage_is_not_zero_and_failure_not_dropped():
    model = Model([ModelReply(plan()), RuntimeError("SECRET-KEY")])
    result = BoundedResearch(model=model).propose("adaptive_no_research", fixed_rubric(), [view()])
    assert result.status == "invalid" and result.costs["model_calls"] == 2
    assert result.costs["usage_complete"] is False and result.costs["input_tokens"] is None
    assert result.costs["calls"][-1]["status"] == "failed"
    assert "SECRET-KEY" not in json.dumps(result.to_dict())


@pytest.mark.parametrize("modification", ["script", "invented_obligation", "unconditional", "fake_citation", "expected", "empty_rules"])
def test_invalid_recipe_not_accepted(modification):
    proposed = update()
    if modification == "script":
        proposed["rules"][0]["method"] = "exec_python"
    elif modification == "invented_obligation":
        proposed["rules"][0]["obligation_kind"] = "must_follow_skill"
    elif modification == "unconditional":
        proposed["rules"][0]["applicability"] = "always"
    elif modification == "fake_citation":
        proposed["rules"][0]["citations"] = [{"source_id": "fake-source", "quote": QUOTE}]
    elif modification == "expected":
        proposed["rules"][0]["expected"] = [1, 2]
    else:
        proposed["rules"] = []
    result = BoundedResearch(model=Model([plan(), proposed])).propose(
        "adaptive_no_research", fixed_rubric(), [view()])
    assert result.status == "invalid" and result.rubric is None


def test_wrong_exact_quote_fails(tmp_path):
    def response(payload):
        citation = {"source_id": payload["sources"][0]["source_id"], "quote": "An invented quote longer than twenty characters."}
        return update([rule(citations=[citation])])
    result = BoundedResearch(model=Model([plan([URL]), response]), fetcher=source_fetch, cache_root=tmp_path).propose(
        "adaptive_research", fixed_rubric(), [view()])
    assert result.status == "invalid" and result.rubric is None


def test_quote_cannot_establish_entailment_or_authorize(tmp_path):
    def response(payload):
        citation = {"source_id": payload["sources"][0]["source_id"], "quote": QUOTE}
        # Copy docs do not establish that *this task* requires deterministic
        # outputs. The proposal remains untrusted and cannot register a relation.
        return update([rule("public_invariant", citations=[citation])])
    result = BoundedResearch(model=Model([plan([URL]), response]), fetcher=source_fetch, cache_root=tmp_path).propose(
        "adaptive_research", fixed_rubric(), [view()])
    assert result.status == "update" and result.requires_calibration
    assert result.findings[0]["task_obligation_authority"] == "public_contract_only"
    assert result.findings[0]["execution_confirmed"] is False
    assert not hasattr(result, "authorized")


def test_pipeline_binds_research_source_version(tmp_path):
    one = BoundedResearch(model=Model([plan([URL]), update()]), fetcher=source_fetch, cache_root=tmp_path).propose(
        "adaptive_research", fixed_rubric(), [view()])
    def changed_fetch(urls, root):
        result = source_fetch(urls, root)
        result[0]["text"] += " Public documentation snapshot revision."
        result[0]["text_sha256"] = hashlib.sha256(result[0]["text"].encode()).hexdigest()
        return result
    two = BoundedResearch(model=Model([plan([URL]), update()]), fetcher=changed_fetch, cache_root=tmp_path).propose(
        "adaptive_research", fixed_rubric(), [view()])
    assert one.rubric.checks == two.rubric.checks
    assert one.rubric.pipeline_hash != two.rubric.pipeline_hash


def test_cache_namespace_separates_question_and_evidence(tmp_path):
    for question in ("What visible obligation is missed?", "When is this check not applicable?"):
        p = plan([URL])
        p["questions"] = [question]
        result = BoundedResearch(model=Model([p, update()]), fetcher=source_fetch, cache_root=tmp_path).propose(
            "adaptive_research", fixed_rubric(), [view()])
        assert result.status == "update"
    assert len(list(tmp_path.glob("*/namespace.json"))) == 2


def test_call_cap_and_usage_cap_preserve_unknown_instead_of_retry():
    model = Model([plan(), update()])
    result = BoundedResearch(model=model, budget=ResearchBudget(max_model_calls=1)).propose(
        "adaptive_no_research", fixed_rubric(), [view()])
    assert result.status == "invalid" and len(model.calls) == 1
    model = Model([ModelReply(plan(), 10000, 10000)])
    result = BoundedResearch(model=model).propose("adaptive_no_research", fixed_rubric(), [view()])
    assert result.status == "invalid" and result.costs["calls"][0]["output_tokens"] == 10000


def test_prompt_size_cap_applies_before_any_model():
    sample = view()
    sample["artifact"]["files"][0]["content"] = "x" * 15000
    model = Model([])
    with pytest.raises(ValueError, match="budget"):
        BoundedResearch(model=model, budget=ResearchBudget(max_prompt_bytes=10000)).propose(
            "adaptive_no_research", fixed_rubric(), [sample])
    assert not model.calls


def test_mutating_original_development_cannot_mutate_projection():
    sample = view()
    checked = validate_development_view(sample)
    sample["task"]["prompt"] = "changed"
    assert checked["task"]["prompt"] != "changed"


def test_model_json_duplicate_keys_fail():
    raw = '{"status":"no_update","status":"investigate","questions":[],"urls":[]}'
    result = BoundedResearch(model=Model([raw])).propose("adaptive_no_research", fixed_rubric(), [view()])
    assert result.status == "invalid"


def test_full_rule_replacement_does_not_claim_removed_task_obligations_passed():
    result = BoundedResearch(model=Model([plan(), update()])).propose(
        "adaptive_no_research", fixed_rubric(), [view()])
    assert {c.obligation_kind for c in result.rubric.checks} == {"input_preservation"}
    assert result.rubric.aggregation_policy == "common-task-obligations-v1"
    assert result.rubric.parent_hash == fixed_rubric().content_hash


@pytest.mark.parametrize("location", ["root", "documents", "snapshot", "source.json", "source.html", "excerpt.txt"])
def test_source_cache_symlinks_rejected_before_legacy_fetch(tmp_path, monkeypatch, location):
    from skillopt.validator_pilot.api import digest
    root = tmp_path / "cache"
    outside = tmp_path / "outside"
    outside.mkdir()
    identifier = digest({"url": URL, "protocol": "bounded-research-v1"})
    snapshot = root / "documents" / identifier
    link = {"root": root, "documents": root / "documents", "snapshot": snapshot}.get(location, snapshot / location)
    link.parent.mkdir(parents=True, exist_ok=True)
    if location.endswith((".json", ".html", ".txt")):
        target = outside / "protected"
        target.write_bytes(b"private unchanged bytes")
        link.symlink_to(target)
    else:
        link.symlink_to(outside, target_is_directory=True)
    before = {p.name: p.read_bytes() for p in outside.iterdir()}
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise AssertionError("Symlink must fail before any old cache read or network")
    monkeypatch.setattr("skillopt.skill_validation.research.legacy._fetch_one", forbidden)
    with pytest.raises(ValueError, match="Symlink research cache"):
        fetch_documents([URL], root)
    assert not calls
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == before


@pytest.mark.parametrize("location", ["root", "namespace_directory", "namespace_file"])
def test_proposal_namespace_symlink_cannot_redirect_write(tmp_path, location):
    cache = tmp_path / "cache"
    initial = BoundedResearch(model=Model([plan([URL]), update()]), fetcher=source_fetch, cache_root=cache).propose(
        "adaptive_research", fixed_rubric(), [view()])
    assert initial.status == "update"
    namespace = next(cache.glob("*/namespace.json"))
    outside = tmp_path / "outside"
    outside.mkdir()
    if location == "namespace_file":
        target = outside / "protected.json"
        target.write_text("private unchanged bytes")
        namespace.unlink()
        namespace.symlink_to(target)
    elif location == "namespace_directory":
        directory = namespace.parent
        directory.rename(tmp_path / "original_namespace")
        directory.symlink_to(outside, target_is_directory=True)
    else:
        cache.rename(tmp_path / "original_cache")
        cache.symlink_to(outside, target_is_directory=True)
    before = {p.name: p.read_bytes() for p in outside.iterdir()}
    fetched = []
    def forbidden(*args):
        fetched.append(args)
        raise AssertionError("Namespace must fail before document fetch")
    model = Model([plan([URL])])
    result = BoundedResearch(model=model, fetcher=forbidden, cache_root=cache).propose(
        "adaptive_research", fixed_rubric(), [view()])
    assert result.status == "invalid" and result.rubric is None
    assert not fetched and len(model.calls) == 1
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == before
