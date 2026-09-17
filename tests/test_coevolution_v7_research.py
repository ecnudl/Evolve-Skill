"""V7 attribution, bounded stages and isolation; all model/document IO is fake."""

import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v7 import research
from skillopt.validator_pilot.api import digest, write_immutable_json

URL = "https://docs.python.org/3/library/functions.html#sorted"
QUOTE = "Return a new sorted list from the items in iterable."
STARTER = {"logic.py": "def touching(left, right):\n    return left < right\n"}
BASE = {"logic.py": "def touching(left, right):\n    return left <= right  # actual base\n"}
CANDIDATE = {"logic.py": "def touching(left, right):\n    return left <= right\n"}


def reseal(value, field="record_hash"):
    value = deepcopy(value)
    value.pop(field, None)
    return core.seal(value, field)


def assessment(artifact, *, status="pass", check_id="coding_contract", details=None):
    return core.make_assessment(check_id=check_id, task_id="development-interval", domain="coding", phase="development",
        artifact_hash=digest(artifact), rubric_hash=core.initial_rubric()["rubric_hash"], status=status,
        evidence_kind="execution", verified=status in {"pass", "fail"}, gate_eligible=status in {"pass", "fail"},
        details=details or {"actual": True, "expected": True})


def packet(*, status="pass", artifact=CANDIDATE, details=None, audit=True):
    rows = [assessment(artifact, status=status, details=details),
            assessment(artifact, status="unknown", check_id="coding_probe")]
    base = assessment(BASE)

    def ref(row):
        return {k: row[k] for k in ("check_id", "status", "receipt_hash", "artifact_hash")}

    return core.feedback_packet(task_id="development-interval", cluster_id="interval-substrate", domain="coding",
        assessments=rows, artifact=artifact, contract="Closed endpoints touch; preserve caller input.",
        comparisons=[{"repeat": 0, "arms": {"baseline": [ref(base)], "current": [ref(base)], "candidate": [ref(rows[0])]},
                      "interpretation": "paired_observation_not_causation"}],
        hypotheses=["Fixture boundaries may leave behavior untested; not a confirmed defect."],
        research_context={"audit": {"preselected": audit, "selection": "pre_execution_random"}},
        task_context={"id": "development-interval", "files": STARTER, "public_cases": [{"input": [2, 2], "expected": True}]})


def registries(p):
    record = core.seal({"phase": "development", "task_id": p["task_id"], "artifact_hash": digest(BASE),
                       "artifact": BASE, "request_hashes": [digest("actual-base-request")],
                       "assessments": [assessment(BASE)]})
    return {p["record_hash"]: {digest(BASE): record}}


def reference(p, *, arm="evaluated", check_id="coding_contract"):
    row = next(r for r in p["observations"] if r["check_id"] == check_id) if arm != "baseline" else assessment(BASE)
    return {"packet_hash": p["record_hash"], "artifact_hash": row["artifact_hash"], "check_id": check_id,
            "receipt_hash": row["receipt_hash"], "arm": arm}


def plan(p, external=False):
    return {"explanations": [
        {"hypothesis": "Existing checks might miss an endpoint boundary.", "check": "Try a legal endpoint input.",
         "evidence_refs": [reference(p)]},
        {"hypothesis": "The implementation may already satisfy the boundary contract.", "check": "Inspect actual receipts, not starter code.",
         "evidence_refs": [reference(p)]}],
        "questions": [{"topic": "sorting", "question": "Does sorted return a new list?"}],
        "urls": [URL] if external else []}


def findings(p, *, external=False, kind="coverage_hypothesis", refs=None):
    return {"findings": [{"finding_id": "f1", "check_id": "coding_probe", "kind": kind,
        "hypothesis": "An endpoint input could test coverage; existing passing receipts do not show a defect.",
        "proposedtest": "Add an allowed touching-endpoint diagnostic and preserve input immutability.",
        "uncertainty": "Neither this idea nor the quote establishes an actual regression.",
        "evidence_refs": refs or [reference(p)], "evidenceurls": [URL] if external else [],
        "evidencequotes": [{"url": URL, "quote": QUOTE}] if external else []}],
        "limits": ["Finite development receipts and byte provenance do not establish semantic completeness."]}


def patch(external=False):
    return {"changes": [{"check_id": "coding_probe", "search": "Try an allowed touching-endpoint input with an unaffected control.",
                         "when": "Only when the explicit current contract includes closed endpoint union.",
                         "limits": "No counterexample is not completeness; re-execute all proposed diagnostics.", "finding_ids": ["f1"]}],
            "rationale": "Test a coverage hypothesis without converting the starter fixture into baseline evidence.",
            "source_refs": [URL] if external else []}


class FakeAPI:
    model = "glm-5.3"
    service = {"fake": "v7-research-test", "max_retries": 2}

    def __init__(self, root, responses):
        self.root, self.responses, self.calls = root / "api", list(responses), []

    def call(self, system, user, *, kind, key, max_tokens):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": 0}
        response = self.responses.pop(0)
        row = {"request": request, "request_hash": digest(request), "ok": response is not None,
               "response": json.dumps(response) if isinstance(response, dict) else response,
               "http_attempt_count": 1, "finish_reason": "stop", "usage": {}}
        write_immutable_json(self.root / "calls" / f"{row['request_hash']}.json", row)
        self.calls.append(row)
        return row


def fake_fetch(urls, directory):
    assert urls == [URL]
    raw, identifier = f"<p>{QUOTE}</p>".encode(), digest(URL)
    source = {"ok": True, "requested_url": URL, "retrieved_utc": "offline-fixture", "snapshot_id": identifier,
              "text": QUOTE, "text_sha256": hashlib.sha256(QUOTE.encode()).hexdigest(),
              "raw_html_sha256": hashlib.sha256(raw).hexdigest()}
    snapshot = directory / "documents" / identifier
    snapshot.mkdir(parents=True)
    (snapshot / "source.html").write_bytes(raw)
    (snapshot / "excerpt.txt").write_text(QUOTE)
    write_immutable_json(snapshot / "source.json", source)
    return [source]


def run(tmp_path, monkeypatch, *, p=None, external=False, responses=None, registry=None):
    p = p or packet()
    monkeypatch.setattr(research, "fetch_sources", fake_fetch)
    api = FakeAPI(tmp_path, responses or [plan(p, external), findings(p, external=external), patch(external)])
    result = research.evolve(api, core.initial_rubric(), [p], tmp_path, "branch-0", external, 0,
                             artifact_registries=registry)
    return result, api, p


def test_three_stages_actual_evidence_view_unique_patch_no_fallback_or_activation(tmp_path, monkeypatch):
    result, api, p = run(tmp_path, monkeypatch)
    assert len(api.calls) == result["calls_used"] == 3
    assert [r["request"]["kind"] for r in api.calls] == ["v7_rubric_plan", "v7_rubric_synthesis", "v7_rubric_patch"]
    assert all(r["request"]["max_tokens"] == 6000 for r in api.calls)
    assert result["proposed_rubric"]["revision"] == 1
    assert result["historical_fallback_used"] is False
    assert result["activation"] == "none_requires_independent_calibration_next_round"
    assert result["effective_round_if_independently_promoted"] == 1
    assert "finding_ids" not in result["revision_patch"]["changes"][0]
    assert result["revision_evidence"]["changes"][0]["finding_ids"] == ["f1"]
    for request in api.calls:
        payload = json.loads(request["request"]["user"])
        view = payload["development_evidence"]["views"][0]
        assert view["initial_task_fixture"]["artifact"] == STARTER
        assert view["evaluated_artifact"]["artifact"] == CANDIDATE
        assert view["observations"] == p["observations"]
        assert view["paired_observations"][0]["reference_checks"]["baseline"][0]["artifact_content_available"] is False
        assert "fixture is NOT a Base/Baseline execution" in request["request"]["system"]


def test_base_can_be_cited_only_with_real_matching_artifact_and_receipt_registry(tmp_path, monkeypatch):
    p = packet()
    f = findings(p, refs=[reference(p, arm="baseline"), reference(p)])
    result, api, _ = run(tmp_path, monkeypatch, p=p, registry=registries(p), responses=[plan(p), f, patch()])
    assert result["proposed_rubric"] is not None
    view = json.loads(api.calls[0]["request"]["user"])["development_evidence"]["views"][0]
    assert "<= right" in view["supplied_solver_artifact_registry"][digest(BASE)]["artifact"]["logic.py"]
    host = result["research"]["findings"]["findings"][0]["host_observations"]
    assert [r["observation"]["status"] for r in host] == ["pass", "pass"]
    assert all(r["artifact_content_available"] for r in host)


def test_unresolved_base_reference_invalidates_synthesis_without_patch_or_reroll(tmp_path, monkeypatch):
    p = packet()
    result, api, _ = run(tmp_path, monkeypatch, p=p,
        responses=[plan(p), findings(p, refs=[reference(p, arm="baseline")]), patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 2
    assert result["stages"][-1]["schema_valid"] is False


@pytest.mark.parametrize("status", ["pass", "unknown"])
def test_pass_or_unknown_cannot_be_promoted_to_discovered_semantic_failure(tmp_path, monkeypatch, status):
    p = packet(status=status)
    result, api, _ = run(tmp_path, monkeypatch, p=p,
        responses=[plan(p), findings(p, kind="verified_behavior_failure"), patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 2
    assert result["historical_fallback_used"] is False


@pytest.mark.parametrize("category", ["delivery", "transport", "infrastructure", "format", "schema"])
def test_even_verified_fail_delivery_is_not_a_semantic_defect(tmp_path, monkeypatch, category):
    p = packet(status="fail", details={"reason": category}, audit=False)
    result, api, _ = run(tmp_path, monkeypatch, p=p,
        responses=[plan(p), findings(p, kind="verified_behavior_failure"), patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 2


def test_verified_hard_failure_supports_kind_not_free_text_truth(tmp_path, monkeypatch):
    p = packet(status="fail", details={"actual": False, "expected": True})
    result, _, _ = run(tmp_path, monkeypatch, p=p,
        responses=[plan(p), findings(p, kind="verified_behavior_failure"), patch()])
    assert result["proposed_rubric"] is not None
    finding = result["research"]["findings"]["findings"][0]
    assert finding["host_observations"][0]["observation"]["status"] == "fail"
    assert finding["hypothesis_status"] == "unverified_even_when_references_and_quotes_match"
    assert result["research"]["free_text_claims_verified"] is False


def test_host_evaluated_fixture_without_solver_identity_is_never_named_base(tmp_path, monkeypatch):
    p = packet(status="fail", artifact=STARTER, details={"actual": False, "expected": True})
    p["comparisons"] = []
    p = reseal(p)
    result, api, _ = run(tmp_path, monkeypatch, p=p,
        responses=[plan(p), findings(p, kind="verified_behavior_failure"), patch()])
    assert result["proposed_rubric"] is not None
    evidence = json.loads(api.calls[0]["request"]["user"])["development_evidence"]
    assert {r["reference"]["arm"] for r in evidence["evidence_catalog"].values()} == {"evaluated"}
    view = evidence["views"][0]
    assert view["initial_task_fixture"]["artifact"] == view["evaluated_artifact"]["artifact"] == STARTER
    assert view["initial_task_fixture"]["role"] == "original_task_fixture_NOT_execution"
    assert view["evaluated_artifact"]["role"] == "actual_packet_evaluated_artifact"
    assert all("solver_request_hashes" not in row["details"] for row in view["observations"])


def test_missing_evidence_and_delivery_kinds_require_matching_observations(tmp_path, monkeypatch):
    p = packet()
    result, _, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p),
        findings(p, kind="missing_evidence", refs=[reference(p, check_id="coding_probe")]), patch()])
    assert result["proposed_rubric"] is not None
    p = packet(status="unknown", details={"reason": "delivery"}, audit=False)
    result, _, _ = run(tmp_path / "delivery", monkeypatch, p=p,
        responses=[plan(p), findings(p, kind="delivery_problem"), patch()])
    assert result["proposed_rubric"] is not None


@pytest.mark.parametrize("kind", ["missing_evidence", "delivery_problem"])
def test_kind_cannot_invent_an_unknown_or_delivery_observation(tmp_path, monkeypatch, kind):
    p = packet()
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p), findings(p, kind=kind), patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 2


@pytest.mark.parametrize("field,value", [("packet_hash", digest("other")), ("artifact_hash", digest(STARTER)),
                                         ("check_id", "qa_answer"), ("receipt_hash", digest("invented")),
                                         ("arm", "initial_task_fixture")])
def test_wrong_packet_artifact_check_receipt_or_fixture_role_rejected(tmp_path, monkeypatch, field, value):
    p = packet()
    f = findings(p)
    f["findings"][0]["evidence_refs"][0][field] = value
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p), f, patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 2


def test_plan_requires_two_anchored_competing_explanations(tmp_path, monkeypatch):
    p = packet()
    broken = plan(p)
    broken["explanations"][0].pop("evidence_refs")
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[broken, findings(p), patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 1


@pytest.mark.parametrize("broken", [None, '{"explanations":[', '{"x":1,"x":2}', '```json\n{"x":1}', '[]'])
def test_bad_plan_is_terminal_without_json_repair_or_later_stage(tmp_path, monkeypatch, broken):
    p = packet()
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[broken, findings(p), patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 1


def test_duplicate_check_id_terminal_and_never_replaced_with_historical_rubric(tmp_path, monkeypatch):
    p = packet()
    duplicate = patch()
    duplicate["changes"].append(deepcopy(duplicate["changes"][0]))
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p), findings(p), duplicate])
    assert len(api.calls) == 3 and result["proposed_rubric"] is None
    assert result["revision_patch"] is None and result["revision_evidence"] is None
    assert result["status"] == "no_valid_fresh_proposal" and not result["historical_fallback_used"]


@pytest.mark.parametrize("field,value", [("finding_ids", ["invented"]), ("check_id", "qa_citation"),
                                         ("finding_ids", []), ("criterion", "self_certified")])
def test_patch_requires_real_findings_and_cannot_edit_foundation(tmp_path, monkeypatch, field, value):
    p = packet()
    broken = patch()
    broken["changes"][0][field] = value
    result, _, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p), findings(p), broken])
    assert result["proposed_rubric"] is None


def test_no_supported_findings_abstains_without_spending_patch_call(tmp_path, monkeypatch):
    p = packet()
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p), {"findings": [], "limits": ["No supported change."]}, patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 2


def test_official_snapshots_and_exact_quotes_are_only_provenance(tmp_path, monkeypatch):
    result, api, _ = run(tmp_path, monkeypatch, external=True)
    assert result["proposed_rubric"] is not None and len(api.calls) == 3
    assert result["research"]["status"] == "complete"
    assert result["research"]["quotes"][0]["quote"] == QUOTE
    assert result["research"]["source_support"] == "verified_provenance_only"
    assert result["research"]["semantic_support"] == "pending"
    assert result["revision_patch"]["source_refs"] == [URL]


def test_document_transport_unavailable_is_honest_and_never_a_historical_fallback(tmp_path, monkeypatch):
    p = packet()

    def unavailable(*args, **kwargs):
        raise OSError("offline control")

    monkeypatch.setattr(research, "fetch_sources", unavailable)
    api = FakeAPI(tmp_path, [plan(p, True), findings(p), patch()])
    result = research.evolve(api, core.initial_rubric(), [p], tmp_path, "no-docs", True, 0)
    assert result["research"]["status"] == "trusted_transport_unavailable"
    assert result["research"]["sources"] == result["research"]["quotes"] == []
    assert result["research"]["source_support"] == "pending"
    assert result["proposed_rubric"] is not None and not result["historical_fallback_used"]


def test_fabricated_quote_rejected_before_patch(tmp_path, monkeypatch):
    p = packet()
    f = findings(p, external=True)
    f["findings"][0]["evidencequotes"][0]["quote"] = "This task has definitely suffered a demonstrated defect."
    result, api, _ = run(tmp_path, monkeypatch, p=p, external=True, responses=[plan(p, True), f, patch(True)])
    assert result["proposed_rubric"] is None and len(api.calls) == 2


def test_feedback_only_cannot_invent_external_sources(tmp_path, monkeypatch):
    p = packet()
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p), findings(p, external=True), patch(True)])
    assert result["proposed_rubric"] is None and len(api.calls) == 2


@pytest.mark.parametrize("url", ["https://example.com/benchmark-answer", "https://docs.python.org/?secret=answer", "http://docs.python.org/"])
def test_external_research_allowlist_is_enforced_before_fetch(tmp_path, monkeypatch, url):
    p = packet()
    invalid = plan(p, True)
    invalid["urls"] = [url]
    result, api, _ = run(tmp_path, monkeypatch, p=p, external=True, responses=[invalid, findings(p), patch()])
    assert result["proposed_rubric"] is None and len(api.calls) == 1


@pytest.mark.parametrize("phase", ["final", "promotion", "calibration", "heldout", "held-out", "validation"])
def test_non_development_nested_data_rejected_before_api_or_outputs(tmp_path, phase):
    p = packet()
    p["task_context"]["source_phase"] = phase
    p = reseal(p)
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError):
        research.evolve(api, core.initial_rubric(), [p], tmp_path, "safe", True, 0)
    assert api.calls == [] and not (tmp_path / "research_evolution").exists()


@pytest.mark.parametrize("key", ["final_results", "calibration_label", "reference_implementation", "truth"])
def test_heldout_payload_objects_rejected_not_redacted(tmp_path, key):
    p = packet()
    p["task_context"][key] = "private heldout sentinel"
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError):
        research.evolve(api, core.initial_rubric(), [reseal(p)], tmp_path, "safe", True, 0)
    assert not api.calls


def test_qa_answer_bearing_context_never_enters_any_research_stage(tmp_path):
    p = packet()
    p["domain"] = "qa"
    p["task_context"] = {"question": "PRIVATE QUESTION SENTINEL", "context": "PRIVATE ANSWER SENTINEL"}
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="Only Coding"):
        research.evolve(api, core.initial_rubric(), [reseal(p)], tmp_path, "safe", True, 0)
    assert not api.calls and not (tmp_path / "research_evolution").exists()


def test_tampered_packet_and_mismatched_rubric_rejected_before_model(tmp_path):
    p = packet()
    p["artifact"] = STARTER
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError):
        research.evolve(api, core.initial_rubric(), [p], tmp_path, "safe", False, 0)
    current = core.apply_rubric_patch(core.initial_rubric(), {"changes": [
        {k: v for k, v in patch()["changes"][0].items() if k != "finding_ids"}],
        "rationale": "new check", "source_refs": []})
    with pytest.raises(ValueError, match="Rubric do not match"):
        research.evolve(api, current, [packet()], tmp_path, "safe", False, 0)
    assert not api.calls


def test_complete_context_budget_fails_closed_not_silently_truncated(tmp_path):
    p = packet()
    p["task_context"]["large_public_context"] = "x" * 110000
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="budget"):
        research.evolve(api, core.initial_rubric(), [reseal(p)], tmp_path, "safe", False, 0)
    assert not api.calls


def test_tampered_solver_registry_is_rejected_before_any_model(tmp_path):
    p = packet()
    records = registries(p)
    records[p["record_hash"]][digest(BASE)]["artifact"] = STARTER
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="checksum"):
        research.evolve(api, core.initial_rubric(), [p], tmp_path, "safe", False, 0, artifact_registries=records)
    assert not api.calls


def test_cached_resume_revalidates_receipts_and_snapshots_without_calls(tmp_path, monkeypatch):
    result, api, p = run(tmp_path, monkeypatch, external=True)
    again = research.evolve(api, core.initial_rubric(), [p], tmp_path, "branch-0", True, 0)
    assert again == result and len(api.calls) == 3
    snapshot = next((tmp_path / "research_evolution").rglob("excerpt.txt"))
    snapshot.write_text("tampered source snapshot")
    with pytest.raises(ValueError, match="snapshot changed"):
        research.evolve(api, core.initial_rubric(), [p], tmp_path, "branch-0", True, 0)
    assert len(api.calls) == 3


def test_missing_saved_api_receipt_does_not_trigger_model_reroll(tmp_path, monkeypatch):
    result, api, p = run(tmp_path, monkeypatch)
    (api.root / "calls" / f"{result['stages'][0]['request_hash']}.json").unlink()
    with pytest.raises(ValueError, match="receipt missing"):
        research.evolve(api, core.initial_rubric(), [p], tmp_path, "branch-0", False, 0)
    assert len(api.calls) == 3


def test_invalid_cached_patch_stays_invalid_without_fallback_or_extra_calls(tmp_path, monkeypatch):
    p = packet()
    broken = patch()
    broken["changes"].append(deepcopy(broken["changes"][0]))
    result, api, _ = run(tmp_path, monkeypatch, p=p, responses=[plan(p), findings(p), broken])
    assert research.evolve(api, core.initial_rubric(), [p], tmp_path, "branch-0", False, 0) == result
    assert result["proposed_rubric"] is None and len(api.calls) == 3
