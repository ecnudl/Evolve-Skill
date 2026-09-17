"""Offline contracts for V4 probes, research separation, and promotion."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v4 import validator as v
from skillopt.validator_pilot.api import digest


@pytest.fixture
def task():
    return {"id": "development-pipeline", "prompt": "Preserve input types.\n\nOnly requested mode may change.\n",
            "public_cases": [{"input": {"value": 1}, "expected": 2}],
            "input_domain": {"value": "integer 0..10"},
            "private_cases": [{"input": {"SECRET_FINAL": 1}}],
            "reference_files": {"secret.py": "PRIVATE_REFERENCE"}}


@pytest.fixture
def files():
    return {"api.py": "from worker import work\n\ndef solve(payload):\n    return work(payload)\n",
            "worker.py": "def work(payload):\n    return payload['value'] + 1\n"}


def legal(_task, value):
    return isinstance(value, dict) and set(value) == {"value"} and type(value["value"]) is int and 0 <= value["value"] <= 10


def claim(value=1):
    return {"clause_id": "C0001", "path": "worker.py", "line_start": 1, "line_end": 2,
            "input": {"value": value}}


def revision(state=None):
    state = state or v.initial_state()
    strategies = deepcopy(state["strategies"])
    strategies[0]["search"] += " Contrast integer and Boolean inputs only where the contract admits both."
    return {"strategies": strategies, "rationale": "Development showed a contract-sensitive type boundary; applicability remains local."}


def packets(kind="behavior"):
    return [{"split": "development", "source_phase": "learn0", "failure_kind": kind,
             "task_id": "development-pipeline", "contract": "Preserve input types.",
             "actual": 1, "expected": True}]


def test_initial_state_sealed_independent_copies():
    first = v.initial_state()
    assert v.checked_state(first) == first
    first["strategies"][0]["search"] = "tampered"
    assert v.initial_state()["strategies"][0]["search"] != "tampered"
    with pytest.raises(ValueError, match="integrity"):
        v.checked_state(first)


@pytest.mark.parametrize("field,value", [
    ("version", "other"), ("revision", True), ("revision", -1),
    ("parent_hash", "0" * 64), ("guardrails", []), ("rationale", ""),
    ("strategies", []), ("extra", 1),
])
def test_resealed_state_still_requires_schema(field, value):
    state = v.initial_state()
    state.pop("state_hash")
    state[field] = value
    with pytest.raises(ValueError):
        v.checked_state(v._seal(state))


def test_clause_ids_preserve_original_lines(task):
    rows = v.clauses(task["prompt"])
    assert [row["clause_id"] for row in rows] == ["C0001", "C0003"]
    assert rows[1]["line_start"] == rows[1]["line_end"] == 3
    assert rows[0]["text_hash"] == digest("Preserve input types.")


def test_claim_prompt_has_numbered_files_and_no_private_data(task, files):
    system, user = v.claim_messages(task, files, v.initial_state())
    payload = json.loads(user)
    assert payload["candidate_files"]["worker.py"][0] == {"line": 1, "text": "def work(payload):"}
    assert payload["candidate_artifact_hash"] == digest(files)
    assert "SECRET_FINAL" not in user and "PRIVATE_REFERENCE" not in user
    assert "unknown" in system.lower()
    assert "expected answers" in system


@pytest.mark.parametrize("fence", [False, True])
def test_claims_use_ids_and_spans_without_quote_copying(task, files, fence):
    raw = json.dumps({"claims": [claim()], "search_note": "A discriminating input, not a verdict."})
    if fence:
        raw = "```json\n" + raw + "\n```"
    result = v.parse_claims(raw, task, files, legal)
    assert result["schema_valid"] and len(result["claims"]) == 1
    row = result["claims"][0]
    assert row["artifact_hash"] == digest(files)
    assert row["clause_hash"] == digest("Preserve input types.")
    assert row["source_span_hash"] == digest(files["worker.py"].rstrip("\n"))


@pytest.mark.parametrize("field,value,reason", [
    ("clause_id", "C0002", "clause_id_not_grounded"),
    ("clause_id", [], "clause_id_not_grounded"),
    ("path", "secret.py", "candidate_path_not_grounded"),
    ("path", [], "candidate_path_not_grounded"),
    ("line_start", True, "source_span_not_grounded"),
    ("line_start", 0, "source_span_not_grounded"),
    ("line_end", 3, "source_span_not_grounded"),
    ("line_end", "2", "source_span_not_grounded"),
    ("input", {"value": -1}, "input_outside_task_domain"),
    ("input", {"value": True}, "input_outside_task_domain"),
    ("input", [], "input_invalid_or_unbounded"),
    ("input", {"value": 1000001}, "input_invalid_or_unbounded"),
])
def test_invalid_claim_grounding_is_unknown(task, files, field, value, reason):
    row = claim()
    row[field] = value
    result = v.parse_claims(json.dumps({"claims": [row]}), task, files, legal)
    assert result["schema_valid"] and not result["claims"]
    assert result["invalid_claims"] == [{"index": 0, "reason": reason}]
    assert result["errors"] == ["no_usable_probe_unknown"]


def test_claim_partial_validity_and_duplicate_input_explicit(task, files):
    extra = {**claim(2), "expected": 3}
    result = v.parse_claims(json.dumps({"claims": [claim(), claim(), extra, claim(3)]}), task, files, legal)
    assert len(result["claims"]) == 2
    assert result["invalid_claims"] == [{"index": 1, "reason": "duplicate_input"},
                                         {"index": 2, "reason": "claim_fields_invalid"}]


@pytest.mark.parametrize("raw", [
    "not json", "[]", '{"claims":[],"claims":[]}', '{"claims":NaN}',
    '{"claims":[],"verdict":"pass"}', '{"claims":[],"search_note":null}',
    json.dumps({"claims": [claim()] * 5}), "x" * 60001,
])
def test_bad_batch_no_usable_claims(task, files, raw):
    result = v.parse_claims(raw, task, files, legal)
    assert not result["schema_valid"] and not result["claims"]


def test_empty_claims_unknown(task, files):
    result = v.parse_claims('{"claims":[]}', task, files, legal)
    assert result["schema_valid"] and result["errors"] == ["no_usable_probe_unknown"]


def test_blank_source_span_invalid(task, files):
    row = {**claim(), "path": "api.py", "line_start": 2, "line_end": 2}
    result = v.parse_claims(json.dumps({"claims": [row]}), task, files, legal)
    assert result["invalid_claims"][0]["reason"] == "source_span_empty_or_unbounded"


def test_input_callback_cannot_mutate_record(task, files):
    def malicious(_task, value):
        value["value"] = 10
        return True
    result = v.parse_claims(json.dumps({"claims": [claim(2)]}), task, files, malicious)
    assert result["claims"][0]["input"] == {"value": 2}


def test_revision_bounded_sealed_and_parent_linked():
    before = v.initial_state()
    after = v.parse_revision(revision(before), before)
    assert after["revision"] == 1 and after["parent_hash"] == before["state_hash"]
    assert v.checked_state(after) == after
    assert before == v.initial_state()


@pytest.mark.parametrize("mutation", ["unchanged", "drop", "duplicate", "too_many_changes", "bad_id", "extra"])
def test_bad_revision_rejected(mutation):
    state = v.initial_state()
    value = revision(state)
    if mutation == "unchanged":
        value["strategies"] = state["strategies"]
    elif mutation == "drop":
        value["strategies"].pop()
    elif mutation == "duplicate":
        value["strategies"][1]["id"] = value["strategies"][0]["id"]
    elif mutation == "too_many_changes":
        for row in value["strategies"]:
            row["limits"] += " Modified."
    elif mutation == "bad_id":
        value["strategies"][0]["id"] = "Bad ID"
    elif mutation == "extra":
        value["approved"] = True
    with pytest.raises(ValueError):
        v.parse_revision(value, state)


@pytest.mark.parametrize("split", ["holdout", "calibration", "test", "final", "eval", "test_dev"])
def test_revision_and_research_refuse_nested_forbidden_splits(split):
    data = packets()
    data[0]["nested"] = {"partition": split}
    with pytest.raises(ValueError):
        v.revision_messages(v.initial_state(), data)
    with pytest.raises(ValueError):
        v.research_trigger(data)


@pytest.mark.parametrize("data", [[], [{"failure_kind": "behavior"}], [{"split": "learn0"}]])
def test_evolution_requires_explicit_development(data):
    with pytest.raises(ValueError):
        v.revision_messages(v.initial_state(), data)


@pytest.mark.parametrize("phase", ["holdout", "calibration", "final", "final_r1", "shadow", "test"])
def test_source_phase_cannot_relabel_final_as_development(phase):
    data = packets()
    data[0]["source_phase"] = phase
    with pytest.raises(ValueError, match="source phase"):
        v.revision_messages(v.initial_state(), data)


@pytest.mark.parametrize("kind,triggered", [("behavior", True), ("semantic", True),
                                            ("validator_gap", True), ("delivery", False),
                                            ("schema", False), ("transport", False)])
def test_research_trigger_distinguishes_delivery(kind, triggered):
    assert v.research_trigger(packets(kind))["triggered"] is triggered


def source():
    text = "The bool class is a subclass of int. Explicit task requirements still govern handling."
    return {"ok": True, "requested_url": "https://docs.python.org/3/library/stdtypes.html",
            "retrieved_utc": "2026-09-09T00:00:00+00:00", "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "raw_html_sha256": "0" * 64, "snapshot_id": "test-source", "transport_version": "offline_test"}


class FakeAPI:
    def __init__(self, research=False, invalid=None, bad_quote=False, no_sources=False):
        self.calls = []
        self.research, self.invalid, self.bad_quote, self.no_sources = research, invalid, bad_quote, no_sources

    def call(self, system, user, kind, key, max_tokens, **_):
        self.calls.append({"system": system, "user": user, "kind": kind, "key": key, "max_tokens": max_tokens})
        stage = kind.removeprefix("v4_validator_revision_")
        if stage == "plan":
            value = {"questions": [{"topic": "types", "question": "Does the explicit task distinguish booleans?"}]}
            if self.research:
                value["urls"] = [source()["requested_url"]]
        elif stage == "synthesis":
            row = {"topic": "types", "gap": "Check task-specific type obligations.",
                   "proposedtest": "Compare admissible numeric values under the exact task contract.",
                   "uncertainty": "General language behavior does not prescribe this task's policy."}
            if self.research:
                row.update(oldcriterion="contract", evidenceurls=[source()["requested_url"]],
                           evidencequotes=[{"url": source()["requested_url"],
                                            "quote": "This quote is fabricated for a rejection test." if self.bad_quote
                                            else "The bool class is a subclass of int."}])
            value = {"findings": [] if self.no_sources else [row], "limits": ["Calibration is still required."]}
        else:
            value = revision()
        return {"ok": self.invalid != "transport", "response": "bad JSON" if self.invalid == stage else json.dumps(value),
                "request_hash": digest(self.calls[-1]), "usage": {"total_tokens": 11}, "finish_reason": "stop"}


def test_feedback_evolution_three_calls_no_fetch_and_no_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "fetch_sources", lambda *_: pytest.fail("Feedback cannot fetch"))
    api = FakeAPI()
    record = v.evolve(api, v.initial_state(), packets(), tmp_path, "stream0-round0-B", False)
    assert record["status"] == "proposal_ready" and record["calls_used"] == 3
    assert len(api.calls) == 3 and all(row["max_tokens"] == 6000 for row in api.calls)
    assert record["research"]["method"] == "feedback_only"
    assert record["research"]["sources_available"] == 0
    assert record["activation"] == "none_requires_independent_calibration"
    assert not any("approved" in row for row in record)
    assert v.evolve(api, v.initial_state(), packets(), tmp_path, "stream0-round0-B", False) == record
    assert len(api.calls) == 3  # Immutable resume does not re-call.


def test_research_evolution_provenance_and_equal_budget(tmp_path, monkeypatch):
    calls = []
    def fetch(urls, root):
        calls.append((urls, root))
        return [source()]
    monkeypatch.setattr(v, "fetch_sources", fetch)
    api = FakeAPI(research=True)
    record = v.evolve(api, v.initial_state(), packets(), tmp_path, "stream0-round0-C", True)
    assert len(calls) == 1 and len(api.calls) == 3
    assert record["research"]["executed"]
    assert record["research"]["fetch_status"] == "complete"
    assert record["research"]["sources_available"] == 1
    assert record["research"]["findings"]["findings"][0]["evidencequotes"][0]["quote"] in source()["text"]
    assert not record["research"]["autonomous_open_web_deepresearch"]
    assert record["status"] == "proposal_ready"


def test_delivery_only_research_arm_uses_explicit_feedback_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "fetch_sources", lambda *_: pytest.fail("Delivery-only failure is not a web gap"))
    api = FakeAPI()
    record = v.evolve(api, v.initial_state(), packets("delivery"), tmp_path, "delivery", True)
    assert record["research"]["requested"] and not record["research"]["executed"]
    assert record["research"]["method"] == "feedback_only"
    assert record["research"]["fetch_status"] == "not_requested"


def test_missing_proxy_recorded_without_exception_or_configuration_leak(tmp_path, monkeypatch):
    def fail(*_):
        raise ValueError("pretend_secret_proxy_configuration")
    monkeypatch.setattr(v, "fetch_sources", fail)
    api = FakeAPI(research=True, no_sources=True)
    record = v.evolve(api, v.initial_state(), packets(), tmp_path, "fetch-failed", True)
    assert record["research"]["fetch_status"] == "trusted_transport_unavailable"
    assert record["research"]["sources_available"] == 0
    assert record["status"] == "proposal_ready"  # Proposal, never promotion.
    assert "pretend_secret" not in json.dumps(record)


def test_research_fabricated_quote_does_not_enter_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "fetch_sources", lambda *_: [source()])
    api = FakeAPI(research=True, bad_quote=True)
    record = v.evolve(api, v.initial_state(), packets(), tmp_path, "bad-quote", True)
    assert record["stages"][1]["error"] == "invalid_stage_schema"
    assert record["research"]["findings"] is None
    assert "fabricated for" not in api.calls[-1]["user"]


@pytest.mark.parametrize("invalid,expected", [("plan", "proposal_ready"), ("synthesis", "proposal_ready"),
                                               ("revision", "proposal_invalid"), ("transport", "proposal_invalid")])
def test_stage_failure_is_terminal_not_rerolled(tmp_path, invalid, expected):
    api = FakeAPI(invalid=invalid)
    record = v.evolve(api, v.initial_state(), packets(), tmp_path, invalid, False)
    assert len(api.calls) == record["calls_used"] == 3
    assert record["status"] == expected


def test_bad_cached_evolution_integrity_rejected(tmp_path):
    api = FakeAPI()
    v.evolve(api, v.initial_state(), packets(), tmp_path, "cache", False)
    path = next(tmp_path.glob("validator_evolution/*/proposal.json"))
    value = json.loads(path.read_text())
    value["research"]["sources_available"] = 99
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="integrity"):
        v.evolve(api, v.initial_state(), packets(), tmp_path, "cache", False)


def calibration():
    rows = []
    for truth in ("good", "bad"):
        for artifact in range(2):
            for repeat in range(2):
                rows.append({"artifact_id": f"{truth}{artifact}r{repeat}",
                             "artifact_hash": digest({"truth": truth, "artifact": artifact}),
                             "truth": truth, "outcome": "not_detected" if truth == "good" else "unknown",
                             "case_kind": "equivalent" if truth == "good" else "semantic_mutant",
                             "repeat": repeat, "task_id": "development-calibration"})
    return rows


def test_promotion_strict_gain_on_same_artifacts():
    old = calibration()
    new = deepcopy(old)
    new[4]["outcome"] = "detected"
    result = v.promotion(old, new)
    assert result["promote"] and not result["reasons"]
    assert result["old"]["unique_good_artifacts"] == result["old"]["unique_bad_artifacts"] == 2
    assert result["new"]["detected_bad"] == 1 and result["new"]["unknown"] == 3
    assert result["activation"] == "next_round_only"
    assert "not_statistical_safety" in result["interpretation"]


def test_promotion_availability_gain_not_mislabelled_detection():
    old = calibration()
    new = deepcopy(old)
    new[4]["outcome"] = "not_detected"
    result = v.promotion(old, new)
    assert result["promote"] and result["new"]["detected_bad"] == 0
    assert result["new"]["usable_missed_bad"] == 1


def test_equal_validator_never_promoted():
    result = v.promotion(calibration(), calibration())
    assert not result["promote"]
    assert result["reasons"] == ["no_strict_detection_or_availability_improvement"]


def test_aggregate_gain_cannot_hide_new_false_rejection():
    old, new = calibration(), calibration()
    new[0]["outcome"] = "detected"
    for row in new[4:]:
        row["outcome"] = "detected"
    result = v.promotion(old, new)
    assert not result["promote"] and "new_paired_false_rejection" in result["reasons"]


def test_known_detection_loss_blocks_despite_aggregate_gain():
    old, new = calibration(), calibration()
    old[4]["outcome"] = "detected"
    new[4]["outcome"] = "not_detected"
    for row in new[5:]:
        row["outcome"] = "detected"
    result = v.promotion(old, new)
    assert not result["promote"] and "lost_paired_defect_detection" in result["reasons"]


def test_paired_new_unknown_blocks_despite_total_reduction():
    old, new = calibration(), calibration()
    new[0]["outcome"] = "unknown"
    for row in new[4:]:
        row["outcome"] = "detected"
    result = v.promotion(old, new)
    assert result["new"]["unknown"] < result["old"]["unknown"]
    assert not result["promote"] and "new_paired_unknown" in result["reasons"]


def test_repeated_same_artifact_does_not_satisfy_unique_coverage():
    old, new = calibration(), calibration()
    for rows in (old, new):
        for row in rows:
            row["artifact_hash"] = digest(row["truth"])
    new[4]["outcome"] = "detected"
    result = v.promotion(old, new)
    assert not result["promote"]
    assert "insufficient_unique_good_or_bad_artifacts" in result["reasons"]


@pytest.mark.parametrize("change", ["hash", "truth", "repeat", "project", "missing", "duplicate", "invalid_outcome"])
def test_unpaired_or_invalid_calibration_refused(change):
    old, new = calibration(), calibration()
    if change == "hash":
        new[0]["artifact_hash"] = "a" * 64
    elif change == "truth":
        new[0]["truth"] = "bad"
    elif change == "repeat":
        new[0]["repeat"] = 20
    elif change == "project":
        new[0]["project"] = "other-project"
    elif change == "missing":
        new.pop()
    elif change == "duplicate":
        new.append(new[0])
    elif change == "invalid_outcome":
        new[0]["outcome"] = "pass"
    with pytest.raises(ValueError):
        v.promotion(old, new)


@pytest.mark.parametrize("minimum", [0, -1, True, 1.5])
def test_invalid_promotion_minima_refused(minimum):
    with pytest.raises(ValueError):
        v.promotion(calibration(), calibration(), min_good=minimum)
