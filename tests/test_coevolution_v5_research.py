"""Offline research protocol, leakage, receipt and snapshot regression tests."""

import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5 import research
from skillopt.coevolution_v5.core import feedback_packet, initial_rubric, make_assessment, seal
from skillopt.validator_pilot.api import digest, write_immutable_json

URL = "https://docs.python.org/3/library/functools.html"
QUOTE = "The cache is threadsafe so that the wrapped function can be used in multiple threads."


def packet(*, domain="coding", status="fail", verified=True, category=None, context=None, secret=""):
    artifact = {"answer": secret} if domain == "qa" else {"main.py": "def run(x): return x"}
    rubric = initial_rubric()
    details = {"actual": secret or "observed", "expected": "expected", "category": category}
    check_id = "qa_answer" if domain == "qa" else "coding_probe"
    assessment = make_assessment(
        check_id=check_id, task_id="task-" + secret, domain=domain, phase="development",
        artifact_hash=digest(artifact), rubric_hash=rubric["rubric_hash"], status=status,
        evidence_kind="native_oracle" if domain == "qa" else "execution", verified=verified,
        gate_eligible=verified and status in {"pass", "fail"}, details=details)
    return feedback_packet(task_id="task-" + secret, cluster_id="cluster-" + secret, domain=domain,
                           assessments=[assessment], artifact=artifact, contract=secret or "Preserve contract",
                           hypotheses=[secret or "Shared dependency may be skipped"], research_context=context)


def plan(external=False):
    return {"explanations": [{"hypothesis": "Shared dependency cache is wrong", "check": "Compare both paths"},
                             {"hypothesis": "Contract intentionally excludes a path", "check": "Check applicability"}],
            "questions": [{"topic": "memoization", "question": "What state does a cache preserve?"}],
            "urls": [URL] if external else []}


def findings(external=False):
    if not external:
        return {"findings": [{"check_id": "coding_probe", "gap": "Shared dependencies uncovered",
                               "proposedtest": "Compare both paths", "uncertainty": "Task may exempt a path"}],
                "limits": ["Development observations only"]}
    return {"findings": [{"topic": "cache semantics", "oldcriterion": "coding_probe",
                           "gap": "Cache semantics require checking the actual contract", "evidenceurls": [URL],
                           "proposedtest": "Use two paths with a shared dependency",
                           "uncertainty": "This quote does not establish task-specific correctness",
                           "evidencequotes": [{"url": URL, "quote": QUOTE}]}],
            "limits": ["Exact provenance is not entailment"]}


def patch(refs=()):
    return {"changes": [{"check_id": "coding_probe", "when": "Shared dependencies exist",
                          "search": "Compare both paths with a single-path control",
                          "limits": "Only task-promised paths matter"}],
            "rationale": "Investigate a demonstrated gap, without relaxing the obligation",
            "source_refs": list(refs)}


class FakeAPI:
    model = "glm-5.3"
    service = {"test": True, "max_retries": 2}

    def __init__(self, root, responses):
        self.root = root / "api"
        self.responses = list(responses)
        self.calls = []

    def call(self, system, user, kind, key, max_tokens):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": 0}
        raw = self.responses.pop(0)
        record = {"request": request, "request_hash": digest(request), "ok": raw is not None,
                  "response": json.dumps(raw) if isinstance(raw, dict) else raw,
                  "http_attempt_count": 1, "finish_reason": "stop", "usage": {}}
        self.calls.append(record)
        write_immutable_json(self.root / "calls" / f"{record['request_hash']}.json", record)
        return record


def fake_fetch(urls, root):
    assert urls == [URL]
    raw = f"<p>{QUOTE}</p>".encode()
    identifier = digest(URL)
    source = {"ok": True, "requested_url": URL, "retrieved_utc": "frozen", "snapshot_id": identifier,
              "text": QUOTE, "text_sha256": hashlib.sha256(QUOTE.encode()).hexdigest(),
              "raw_html_sha256": hashlib.sha256(raw).hexdigest()}
    directory = root / "documents" / identifier
    directory.mkdir(parents=True)
    (directory / "source.html").write_bytes(raw)
    (directory / "excerpt.txt").write_text(QUOTE)
    write_immutable_json(directory / "source.json", source)
    return [source]


def run(tmp_path, monkeypatch, *, external=False, packets=None, responses=None):
    monkeypatch.setattr(research, "fetch_sources", fake_fetch)
    api = FakeAPI(tmp_path, responses or [plan(external), findings(external), patch([URL] if external else [])])
    packets = packets or [packet()]
    result = research.evolve(api, initial_rubric(), packets, tmp_path, "history0", external, 0)
    return result, api, packets


def test_feedback_three_stages_no_external_or_activation(tmp_path, monkeypatch):
    result, api, _ = run(tmp_path, monkeypatch)
    assert len(api.calls) == result["calls_used"] == 3
    assert all(row["request"]["max_tokens"] == 6000 for row in api.calls)
    assert result["proposed_rubric"]["revision"] == 1
    assert result["proposed_rubric"]["parent_hash"] == initial_rubric()["rubric_hash"]
    assert result["research"]["status"] == "not_requested"
    assert result["research"]["sources"] == result["research"]["quotes"] == []
    assert "none_requires" in result["activation"]
    assert result["effective_round_if_independently_promoted"] == 1


def test_actual_research_requires_quotes_and_reports_only_provenance(tmp_path, monkeypatch):
    result, api, _ = run(tmp_path, monkeypatch, external=True)
    assert len(api.calls) == 3
    assert result["research"]["status"] == "complete"
    assert result["research"]["source_support"] == "verified_provenance_only"
    assert result["research"]["semantic_support"] == "pending"
    assert result["research"]["quotes"][0]["quote"] == QUOTE
    assert result["revision_patch"]["source_refs"] == [URL]


@pytest.mark.parametrize("category", ["delivery", "transport", "infrastructure", "format", "schema"])
def test_delivery_and_infrastructure_do_not_trigger(category):
    assert not research.research_trigger([packet(category=category)])["triggered"]


def test_unknown_requires_repeat_or_distinct_artifacts():
    assert not research.research_trigger([packet(status="unknown")])["triggered"]
    assert not research.research_trigger([packet(status="unknown"), packet(status="unknown")])["triggered"]
    assert research.research_trigger([packet(status="unknown", context={"unknown_count": 2})])["triggered"]
    left, right = packet(status="unknown"), packet(status="unknown")
    right = {k: v for k, v in right.items() if k != "record_hash"}
    right["artifact_hash"] = digest("second artifact")
    assert research.research_trigger([left, seal(right)])["triggered"]


def test_unverified_failure_does_not_trigger():
    assert not research.research_trigger([packet(verified=False)])["triggered"]


def test_new_domain_and_preselected_passed_audit_trigger():
    assert research.research_trigger([packet(status="pass", context={"domain_unfamiliar": True})])["triggered"]
    context = {"audit": {"preselected": True, "selection": "pre_execution_random"}}
    assert research.research_trigger([packet(status="pass", context=context)])["triggered"]
    context["audit"]["selection"] = "picked_after_scores"
    assert not research.research_trigger([packet(status="pass", context=context)])["triggered"]


@pytest.mark.parametrize("phase", ["promotion", "audit", "final", "train_holdout", "calibration", "shadow"])
def test_nested_forbidden_provenance_rejected_before_api(tmp_path, phase):
    value = {k: v for k, v in packet().items() if k != "record_hash"}
    value["nested"] = [{"source_phase": phase}]
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="provenance"):
        research.evolve(api, initial_rubric(), [seal(value)], tmp_path, "x", True, 0)
    assert api.calls == []


@pytest.mark.parametrize("alias", ["requested_phase", "task_split"])
def test_adapter_phase_alias_cannot_hide_heldout(alias):
    value = {k: v for k, v in packet().items() if k != "record_hash"}
    value["observations"][0]["details"][alias] = "audit"
    with pytest.raises(ValueError, match="provenance"):
        research.development_packets([seal(value)])


@pytest.mark.parametrize("reason", ["delivery", "transport_unavailable", "infrastructure_or_resource_failure"])
def test_adapter_reason_failure_not_external_research_trigger(reason):
    value = {k: v for k, v in packet(status="unknown", context={"unknown_count": 2}).items() if k != "record_hash"}
    value["observations"][0]["details"].pop("category")
    value["observations"][0]["details"]["reason"] = reason
    assert research.research_trigger([seal(value)])["triggered"] is False


@pytest.mark.parametrize("key", ["truth", "calibration_label", "promotion_result", "audit_result",
                                  "final_results", "calibration", "promotion", "audit"])
def test_label_or_heldout_objects_without_phase_rejected(key):
    value = {k: v for k, v in packet().items() if k != "record_hash"}
    value["nested"] = {key: "good"}
    with pytest.raises(ValueError):
        research.development_packets([seal(value)])


@pytest.mark.parametrize("external", [True, False])
def test_qa_question_context_answers_never_enter_any_stage(tmp_path, monkeypatch, external):
    sentinel = "CONFIDENTIAL_QUESTION_CONTEXT_GOLD_9174"
    value = packet(domain="qa", secret=sentinel)
    result, api, _ = run(tmp_path, monkeypatch, external=external, packets=[value])
    assert result["calls_used"] == 3
    for row in api.calls:
        assert sentinel not in row["request"]["user"]
        assert "context_grounded_short_answer" in row["request"]["user"]
    visible = research.research_view([value])[0]
    assert not {"task_id", "artifact", "contract", "facts", "hypotheses", "repair_guidance"} & set(visible)


def test_qa_editable_rubric_cannot_carry_task_answers():
    current = initial_rubric()
    for row in current["checks"]:
        if row["id"].startswith("qa_"):
            row["search"] = "LEAKED_ANSWER"
            row["source_refs"] = ["LEAKED_ANSWER"]
    current["rationale"] = "LEAKED_ANSWER"
    assert "LEAKED_ANSWER" not in json.dumps(research._public_rubric(current))


@pytest.mark.parametrize("bad", ['{"changes":', '{"a":1,"a":2}', '{"changes":NaN}', 'prose {"changes":[]}'])
def test_invalid_patch_is_terminal_no_json_repair_or_reroll(tmp_path, monkeypatch, bad):
    result, api, packets = run(tmp_path, monkeypatch, responses=[plan(), findings(), bad])
    assert result["proposed_rubric"] is None
    assert result["stages"][-1]["error"] == "invalid_stage_schema"
    resumed = research.evolve(api, initial_rubric(), packets, tmp_path, "history0", False, 0)
    assert resumed == result
    assert len(api.calls) == 3


def test_valid_json_fence_not_arbitrary_repair(tmp_path, monkeypatch):
    result, _, _ = run(tmp_path, monkeypatch, responses=[plan(), findings(), "```json\n" + json.dumps(patch()) + "\n```"])
    assert result["status"] == "proposal_ready"


def test_corrupt_stage_stops_resume(tmp_path, monkeypatch):
    _, api, packets = run(tmp_path, monkeypatch)
    path = next((tmp_path / "research_evolution").glob("*/plan.json"))
    value = json.loads(path.read_text())
    value["parsed"]["questions"][0]["question"] = "tampered"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="hash mismatch"):
        research.evolve(api, initial_rubric(), packets, tmp_path, "history0", False, 0)
    assert len(api.calls) == 3


def test_changed_underlying_api_receipt_stops_resume(tmp_path, monkeypatch):
    _, api, packets = run(tmp_path, monkeypatch)
    path = api.root / "calls" / f"{api.calls[0]['request_hash']}.json"
    value = json.loads(path.read_text())
    value["response"] = "tampered"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="receipt missing or changed"):
        research.evolve(api, initial_rubric(), packets, tmp_path, "history0", False, 0)


def test_corrupt_document_bytes_stop_resume(tmp_path, monkeypatch):
    _, api, packets = run(tmp_path, monkeypatch, external=True)
    path = next((tmp_path / "research_evolution").glob("*/research_sources/documents/*/source.html"))
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="snapshot changed"):
        research.evolve(api, initial_rubric(), packets, tmp_path, "history0", True, 0)
    assert len(api.calls) == 3


def test_invalid_plan_has_no_fetch_and_unparsed_text_not_reused(tmp_path, monkeypatch):
    result, api, _ = run(tmp_path, monkeypatch, external=True,
                         responses=['{"urls":"SENTINEL_BAD_PLAN"', {"findings": [], "limits": ["No sources"]}, patch()])
    assert result["research"]["status"] == "plan_invalid"
    assert result["research"]["sources"] == []
    assert "SENTINEL_BAD_PLAN" not in api.calls[1]["request"]["user"]
    assert result["proposed_rubric"] is not None


def test_transport_failure_no_automatic_reroll(tmp_path, monkeypatch):
    result, api, _ = run(tmp_path, monkeypatch, responses=[None, findings(), patch()])
    assert result["stages"][0]["error"] == "terminal_api_result"
    assert len(api.calls) == 3


def test_fake_external_citation_rejected_in_feedback_arm(tmp_path, monkeypatch):
    result, _, _ = run(tmp_path, monkeypatch, responses=[plan(), findings(), patch([URL])])
    assert result["proposed_rubric"] is None


def test_non_exact_quote_rejects_synthesis_and_dependent_patch(tmp_path, monkeypatch):
    invalid = findings(True)
    invalid["findings"][0]["evidencequotes"][0]["quote"] = "This quote never occurred in the document."
    result, _, _ = run(tmp_path, monkeypatch, external=True, responses=[plan(True), invalid, patch([URL])])
    assert result["stages"][1]["error"] == "invalid_stage_schema"
    assert result["research"]["quotes"] == []
    assert result["proposed_rubric"] is None


def test_obligation_mutation_rejected(tmp_path, monkeypatch):
    invalid = patch()
    invalid["changes"][0]["criterion"] = "Always pass"
    result, _, _ = run(tmp_path, monkeypatch, responses=[plan(), findings(), invalid])
    assert result["proposed_rubric"] is None


def test_plan_needs_distinct_competing_explanations():
    value = plan()
    value["explanations"][1] = deepcopy(value["explanations"][0])
    with pytest.raises(ValueError, match="distinct"):
        research._parse_plan(value, False)


@pytest.mark.parametrize("url", ["http://docs.python.org/3/", "https://example.com/", URL + "?answer=gold"])
def test_document_url_boundary(url):
    value = plan(True)
    value["urls"] = [url]
    with pytest.raises(ValueError):
        research._parse_plan(value, True)


def test_triggers_absent_research_arm_keeps_three_feedback_stages(tmp_path, monkeypatch):
    result, api, _ = run(tmp_path, monkeypatch, external=True, packets=[packet(category="delivery")],
                         responses=[plan(), findings(), patch()])
    assert result["research"]["requested"] is True
    assert result["research"]["executed"] is False
    assert len(api.calls) == 3


def test_feedback_packet_hash_checked():
    value = packet()
    value["contract"] = "mutated"
    with pytest.raises(ValueError, match="hash mismatch"):
        research.development_packets([value])


def test_partial_run_resume_reuses_completed_stage_without_new_call(tmp_path, monkeypatch):
    result, api, packets = run(tmp_path, monkeypatch)
    directory = next((tmp_path / "research_evolution").iterdir())
    # Simulate death immediately before outer result persistence; stage receipts
    # remain immutable and are sufficient to reconstruct the same result.
    (directory / "proposal.json").unlink()
    resumed = research.evolve(api, initial_rubric(), packets, tmp_path, "history0", False, 0)
    assert result == resumed
    assert len(api.calls) == 3


def test_fetch_failure_is_explicit_and_not_retried_on_resume(tmp_path, monkeypatch):
    fetched = []

    def unavailable(urls, root):
        fetched.append(urls)
        raise ValueError("Private transport configuration must not leak")

    monkeypatch.setattr(research, "fetch_sources", unavailable)
    api = FakeAPI(tmp_path, [plan(True), {"findings": [], "limits": ["No source available"]}, patch()])
    packets = [packet()]
    result = research.evolve(api, initial_rubric(), packets, tmp_path, "x", True, 0)
    assert result["research"]["status"] == "trusted_transport_unavailable"
    assert "Private transport" not in json.dumps(result)
    assert research.evolve(api, initial_rubric(), packets, tmp_path, "x", True, 0) == result
    assert len(fetched) == 1


def test_unknown_check_cannot_gain_source_authority(tmp_path, monkeypatch):
    invalid = findings(True)
    invalid["findings"][0]["oldcriterion"] = "invented_check"
    result, _, _ = run(tmp_path, monkeypatch, external=True, responses=[plan(True), invalid, patch([URL])])
    assert result["stages"][1]["error"] == "invalid_stage_schema"
    assert result["proposed_rubric"] is None
