"""The separate plan repair uses fake models/docs and never touches real runs."""

import hashlib
import json

import pytest

from skillopt import research_contract_repair as repair
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v7 import research as frozen
from skillopt.validator_pilot.api import digest, write_immutable_json

URL = "https://docs.python.org/3/library/functions.html#sorted"
QUOTE = "Return a new sorted list from the items in iterable."


class FakeAPI:
    model = "glm-5.3"
    service = {"fake": "contract-repair", "max_retries": 2}

    def __init__(self, root, responses):
        self.root, self.responses, self.calls = root, list(responses), []

    def call(self, system, user, *, kind, key, max_tokens):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": 0}
        response = self.responses.pop(0)
        row = {"request": request, "request_hash": digest(request), "ok": response is not None,
               "response": json.dumps(response) if isinstance(response, dict) else response,
               "http_attempt_count": 1, "finish_reason": "stop", "usage": {"completion_tokens": 100}}
        write_immutable_json(self.root / "calls" / f"{row['request_hash']}.json", row)
        self.calls.append(row)
        return row

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def packet(i):
    initial = {"logic.py": "def touch(a, b): return a < b"}
    artifact = initial if i >= 3 else {"logic.py": "def touch(a, b): return a <= b"}
    task, status = f"development-{i % 3}", "fail" if i >= 3 else "pass"
    rows = [core.make_assessment(check_id=check, task_id=task, domain="coding", phase="development",
        artifact_hash=digest(artifact), rubric_hash=core.initial_rubric()["rubric_hash"],
        status=status if check == "coding_contract" else "unknown", evidence_kind="execution",
        verified=check == "coding_contract", gate_eligible=check == "coding_contract",
        details={"actual": i < 3, "expected": True, "requested_phase": "development"})
        for check in ("coding_contract", "coding_probe")]
    return core.feedback_packet(task_id=task, cluster_id=f"cluster-{i % 3}", domain="coding", assessments=rows,
        artifact=artifact, contract="Touching endpoints satisfy the contract.",
        research_context={"audit": {"preselected": True, "selection": "pre_execution_random"},
                          "artifact_origin": "host_fixture" if i >= 3 else "actual_solver"},
        task_context={"id": task, "files": initial, "public_cases": [{"input": [2, 2], "expected": True}]})


def source_fixture(tmp_path):
    repo, source = tmp_path, tmp_path / "outputs/original"
    packets = [packet(i) for i in range(6)]
    raw = {"explanations": [{"hypothesis": f"Coverage explanation {i}", "check": "Inspect existing development receipts.",
            "evidence_refs": ["receipt_hash:" + packets[i % 6]["observations"][0]["receipt_hash"]]} for i in range(13)]}
    api = FakeAPI(source / "api", [raw])
    frozen.evolve(api, core.initial_rubric(), packets, source / "research", "original-research", True, 0)
    evidence = frozen.prepare_evidence(packets)
    write_immutable_json(source / "research_inputs.json", core.seal({"actual_solver_packets": packets[:3],
                                                                   "host_fixture_packets": packets[3:]}))
    write_immutable_json(source / "research_selection.json", core.seal({"packet_hashes": evidence["packet_hashes"],
        "complete_views": evidence["views"], "no_calibration_or_final_feedback": True}))
    return repo, source, repo / "outputs/research_contract_repair/test", packets, raw


def outputs(packets, *, external=False):
    p, row = packets[0], packets[0]["observations"][0]
    ref = {"packet_hash": p["record_hash"], "artifact_hash": row["artifact_hash"],
           "check_id": row["check_id"], "receipt_hash": row["receipt_hash"], "arm": "evaluated"}
    plan = {"explanations": [{"hypothesis": f"Coverage explanation {i}", "check": "Inspect existing development receipts.",
                             "evidence_refs": [ref]} for i in range(2)],
            "questions": [{"topic": "Sorting", "question": "Does sorting return a new list?"}], "urls": [URL]}
    findings = {"findings": [{"finding_id": "f1", "check_id": "coding_probe", "kind": "coverage_hypothesis",
        "hypothesis": "A boundary case may add coverage; existing passing evidence proves no defect.",
        "proposedtest": "Use a legal touching-boundary input.", "uncertainty": "An unverified hypothesis.",
        "evidence_refs": [ref], "evidenceurls": [URL] if external else [],
        "evidencequotes": [{"url": URL, "quote": QUOTE}] if external else []}],
        "limits": ["Finite development evidence only; local hashes and quotes are not semantic proof."]}
    patch = {"changes": [{"check_id": "coding_probe", "search": "Try a legal touching-boundary probe.",
        "when": "Only where explicitly applicable.", "limits": "No counterexample is not completeness.",
        "finding_ids": ["f1"]}], "rationale": "Investigate coverage, not inferred defects.",
        "source_refs": [URL] if external else []}
    return [plan, findings, patch]


def fetch(urls, root):
    assert urls == [URL]
    raw, identifier = f"<p>{QUOTE}</p>".encode(), digest(URL)
    record = {"ok": True, "requested_url": URL, "retrieved_utc": "offline", "snapshot_id": identifier,
              "text": QUOTE, "text_sha256": hashlib.sha256(QUOTE.encode()).hexdigest(),
              "raw_html_sha256": hashlib.sha256(raw).hexdigest()}
    directory = root / "documents" / identifier
    directory.mkdir(parents=True)
    (directory / "source.html").write_bytes(raw)
    (directory / "excerpt.txt").write_text(QUOTE)
    write_immutable_json(directory / "source.json", record)
    return [record]


def setup_run(tmp_path, monkeypatch, *, responses=None, external=False):
    repo, source, root, packets, raw = source_fixture(tmp_path)
    api = FakeAPI(root / "api", outputs(packets, external=external) if responses is None else responses)
    factories = []

    def factory(repo_arg, root_arg, *, max_calls, workers):
        assert repo_arg == repo and root_arg == api.root and max_calls == 3 and workers == 4
        factories.append(True)
        return api

    monkeypatch.setattr(frozen, "fetch_sources", fetch if external else lambda *_: [])
    return repo, source, root, packets, raw, api, factory, factories


def bytes_under(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_full_diagnostic_preserves_exact_evidence_original_prompt_and_source(tmp_path, monkeypatch):
    repo, source, root, packets, raw, api, factory, _ = setup_run(tmp_path, monkeypatch, external=True)
    before = bytes_under(source)
    result = repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    assert result["status"] == "diagnostic_proposal_ready" and result["calls_used"] == 3
    assert result["activation"] == "never" and result["original_result_replacement"] is False
    assert result["historical_fallback_used"] is False
    assert [r["request"]["kind"] for r in api.calls] == ["research_contract_diagnostic_" + s for s in ("plan_repair", "synthesis", "patch")]
    original = next((source / "api/calls").glob("*.json"))
    original_request = json.loads(original.read_text())["request"]
    assert api.calls[0]["request"]["system"] == original_request["system"]
    payload = json.loads(api.calls[0]["request"]["user"])
    assert payload["development_evidence"] == frozen.prepare_evidence(packets)
    assert json.loads(payload["contract_repair_diagnostic"]["original_invalid_response"]) == raw
    errors = payload["contract_repair_diagnostic"]["host_structural_errors"]
    assert {e["error"] for e in errors} == {"missing_required_field", "count_outside_contract", "reference_must_be_five_field_object"}
    assert all("hypothesis" not in e and "question" not in e and "url" not in e for e in errors)
    assert result["research"]["quotes"][0]["source_support"] == "verified_provenance_only"
    assert result["research"]["semantic_support"] == "pending"
    assert bytes_under(source) == before
    assert not (root / "results.json").exists()


def test_completed_resume_is_exactly_offline_and_idempotent(tmp_path, monkeypatch):
    repo, source, root, _, _, _, factory, _ = setup_run(tmp_path, monkeypatch, external=True)
    result = repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    before = bytes_under(root)

    def prohibited(*_args, **_kwargs):
        raise AssertionError("No network/client/credentials on completed resume")

    monkeypatch.setattr(frozen, "fetch_sources", prohibited)
    monkeypatch.setattr(repair, "make_budgeted_api", prohibited)
    monkeypatch.setattr(repair, "write_immutable_json", prohibited)
    assert repair.run(repo, source, root, api_factory=prohibited) == result
    assert bytes_under(root) == before


@pytest.mark.parametrize("stage", [0, 1, 2])
@pytest.mark.parametrize("invalid", [None, "not JSON", {"unexpected": "schema"}])
def test_invalid_stage_is_terminal_no_retry_no_fallback(tmp_path, monkeypatch, stage, invalid):
    repo, source, root, packets, _, api, factory, _ = setup_run(tmp_path, monkeypatch)
    api.responses = outputs(packets)
    api.responses[stage] = invalid
    result = repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    assert len(api.calls) == result["calls_used"] == stage + 1
    assert result["status"] == "diagnostic_no_valid_proposal" and result["proposed_rubric"] is None
    assert result["historical_fallback_used"] is False
    assert repair.run(repo, source, root, api_factory=lambda *_: pytest.fail("no retry")) == result


@pytest.mark.parametrize("mode", ["unknown_ref", "fixture_as_baseline", "pass_as_fail", "duplicate_check", "fake_quote"])
def test_frozen_receipt_and_patch_guards_not_relaxed(tmp_path, monkeypatch, mode):
    repo, source, root, packets, _, api, factory, _ = setup_run(tmp_path, monkeypatch)
    values = outputs(packets)
    if mode == "unknown_ref":
        values[0]["explanations"][0]["evidence_refs"][0]["receipt_hash"] = digest("invented")
    elif mode == "fixture_as_baseline":
        values[1]["findings"][0]["evidence_refs"][0]["arm"] = "baseline"
    elif mode == "pass_as_fail":
        values[1]["findings"][0]["kind"] = "verified_behavior_failure"
    elif mode == "duplicate_check":
        values[2]["changes"] *= 2
    else:
        values[1]["findings"][0]["evidenceurls"] = [URL]
        values[1]["findings"][0]["evidencequotes"] = [{"url": URL, "quote": QUOTE}]
    api.responses = values
    result = repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    assert result["proposed_rubric"] is None


def test_operator_attestation_required_before_writes_or_client(tmp_path, monkeypatch):
    repo, source, root, _, _, api, factory, factories = setup_run(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="attestation"):
        repair.run(repo, source, root, api_factory=factory)
    assert not root.exists() and not api.calls and not factories


@pytest.mark.parametrize("kind", ["transport", "length", "incomplete_json", "duplicate_json", "valid_plan", "missing_api", "changed_evidence", "wrong_phase"])
def test_original_ineligible_or_changed_records_rejected(tmp_path, monkeypatch, kind):
    repo, source, root, packets, _, _, factory, factories = setup_run(tmp_path, monkeypatch)
    stage_path = next((source / "research/research_evolution").glob("*/plan.json"))
    stage = json.loads(stage_path.read_text())
    receipt = stage["api_receipt"]
    api_path = source / "api/calls" / f"{receipt['request_hash']}.json"
    if kind == "missing_api":
        api_path.unlink()
    elif kind == "changed_evidence":
        path = stage_path.parent / "evidence_view.json"
        data = json.loads(path.read_text())
        data["views"][0]["evaluated_artifact"]["artifact"]["logic.py"] = "changed"
        path.write_text(json.dumps(data))
    elif kind == "wrong_phase":
        path = source / "research_inputs.json"
        data = json.loads(path.read_text())
        data["actual_solver_packets"][0]["phase"] = "final"
        path.write_text(json.dumps(data))
    else:
        if kind == "transport":
            receipt["ok"] = False
        elif kind == "length":
            receipt["finish_reason"] = "length"
        elif kind == "incomplete_json":
            receipt["response"] = '{"explanations":['
        elif kind == "duplicate_json":
            receipt["response"] = '{"explanations":[],"explanations":[]}'
        else:
            receipt["response"] = json.dumps(outputs(packets)[0])
        api_path.write_text(json.dumps(receipt))
        stage.pop("record_hash")
        stage_path.write_text(json.dumps(core.seal(stage)))
    with pytest.raises((ValueError, FileNotFoundError)):
        repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    assert not factories and not root.exists()


@pytest.mark.parametrize("name", ["plan_repair.json", "synthesis.json", "patch.json", "source_receipt.json", "evidence_view.json", "identity.json"])
def test_completed_tamper_rejected_without_client(tmp_path, monkeypatch, name):
    repo, source, root, _, _, _, factory, _ = setup_run(tmp_path, monkeypatch)
    repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    path = root / name
    data = json.loads(path.read_text())
    data["tamper"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        repair.run(repo, source, root, api_factory=lambda *_: pytest.fail("no network"))


@pytest.mark.parametrize("target", ["original", "broad", "outside"])
def test_output_cannot_overlap_original_or_escape_diagnostic_namespace(tmp_path, monkeypatch, target):
    repo, source, root, _, _, _, factory, _ = setup_run(tmp_path, monkeypatch)
    destination = {"original": source, "broad": root.parent, "outside": repo / "elsewhere"}[target]
    before = bytes_under(source)
    with pytest.raises(ValueError):
        repair.run(repo, source, destination, api_factory=factory, original_run_stopped=True)
    assert bytes_under(source) == before


def test_unresolved_call_intent_never_reissued(tmp_path, monkeypatch):
    repo, source, root, _, _, _, factory, _ = setup_run(tmp_path, monkeypatch)
    repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    (root / "result.json").unlink()
    stage = json.loads((root / "patch.json").read_text())
    (root / "patch.json").unlink()
    (root / "api/calls" / f"{stage['api_receipt']['request_hash']}.json").unlink()
    with pytest.raises(ValueError, match="Unresolved"):
        repair.run(repo, source, root, api_factory=lambda *_: pytest.fail("no retry"), original_run_stopped=True)


def test_full_context_over_budget_rejected_not_truncated(tmp_path, monkeypatch):
    repo, source, _, _, _ = source_fixture(tmp_path)
    context = repair.inspect_source(repo, source)
    monkeypatch.setattr(frozen, "MAX_PROMPT_CHARS", 100)
    with pytest.raises(ValueError, match="Full repair context"):
        repair._messages("plan_repair", context)


def test_missing_question_or_url_does_not_allow_host_to_pick_content(tmp_path):
    repo, source, _, _, _ = source_fixture(tmp_path)
    context = repair.inspect_source(repo, source)
    errors = context["structural_errors"]
    assert errors[:2] == [{"path": "questions", "error": "missing_required_field"},
                          {"path": "urls", "error": "missing_required_field"}]
    assert all(set(e) <= {"path", "error", "observed", "minimum", "maximum", "required_fields", "observed_type"} for e in errors)


@pytest.mark.parametrize("mutation", ["nondevelopment", "qa", "final_results", "calibration_label", "reference_implementation"])
def test_resealed_non_development_or_private_payload_is_not_forwarded(tmp_path, monkeypatch, mutation):
    repo, source, root, _, _, _, factory, factories = setup_run(tmp_path, monkeypatch)
    path = source / "research_inputs.json"
    inputs = json.loads(path.read_text())
    p = inputs["actual_solver_packets"][0]
    old_hash = p.pop("record_hash")
    if mutation == "nondevelopment":
        p["phase"] = "final"
    elif mutation == "qa":
        p["domain"] = "qa"
    else:
        p["task_context"][mutation] = {"private": "must never become research context"}
    p = core.seal(p)
    inputs["actual_solver_packets"][0] = p
    inputs.pop("record_hash")
    path.write_text(json.dumps(core.seal(inputs)))
    path = source / "research_selection.json"
    selection = json.loads(path.read_text())
    selection["packet_hashes"] = [p["record_hash"] if h == old_hash else h for h in selection["packet_hashes"]]
    selection.pop("record_hash")
    path.write_text(json.dumps(core.seal(selection)))
    with pytest.raises(ValueError):
        repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    assert not factories and not root.exists()


@pytest.mark.parametrize("missing", ["synthesis.json", "source_receipt.json", "api_receipt"])
def test_completed_missing_evidence_never_triggers_network_reconstruction(tmp_path, monkeypatch, missing):
    repo, source, root, _, _, _, factory, _ = setup_run(tmp_path, monkeypatch)
    repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    path = root / missing
    if missing == "api_receipt":
        stage = json.loads((root / "synthesis.json").read_text())
        path = root / "api/calls" / f"{stage['api_receipt']['request_hash']}.json"
    path.unlink()

    def prohibited(*_args, **_kwargs):
        raise AssertionError("Completed diagnostics are offline, including missing evidence")

    monkeypatch.setattr(frozen, "fetch_sources", prohibited)
    with pytest.raises(ValueError):
        repair.run(repo, source, root, api_factory=prohibited)


@pytest.mark.parametrize("name", ["identity.json", "evidence_view.json", "structural_feedback.json"])
def test_completed_missing_metadata_is_not_recreated(tmp_path, monkeypatch, name):
    repo, source, root, _, _, _, factory, _ = setup_run(tmp_path, monkeypatch)
    repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    (root / name).unlink()
    before = bytes_under(root)

    def prohibited(*_args, **_kwargs):
        raise AssertionError("Completed resume must not write or create a client")

    monkeypatch.setattr(repair, "write_immutable_json", prohibited)
    monkeypatch.setattr(frozen, "fetch_sources", prohibited)
    with pytest.raises(ValueError, match="missing"):
        repair.run(repo, source, root, api_factory=prohibited)
    assert not (root / name).exists() and bytes_under(root) == before


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("kind", ["directory", "file", "dangling", "cycle"])
def test_any_existing_output_subtree_symlink_is_rejected_before_writes_or_client(tmp_path, monkeypatch, completed, kind):
    repo, source, root, _, _, _, factory, _ = setup_run(tmp_path, monkeypatch)
    if completed:
        repair.run(repo, source, root, api_factory=factory, original_run_stopped=True)
    holder = root / "arbitrary/nested"
    holder.mkdir(parents=True)
    outside = repo / "outside"
    outside.mkdir()
    (outside / "file.json").write_text('{"unchanged":true}')
    target = {"directory": outside, "file": outside / "file.json", "dangling": outside / "missing",
              "cycle": holder}[kind]
    (holder / "link").symlink_to(target, target_is_directory=kind in {"directory", "cycle"})
    external_before = bytes_under(outside)
    source_before = bytes_under(source)

    def prohibited(*_args, **_kwargs):
        raise AssertionError("Tree validation must precede all writes, source reads and network")

    monkeypatch.setattr(repair, "write_immutable_json", prohibited)
    monkeypatch.setattr(repair, "inspect_source", prohibited)
    monkeypatch.setattr(frozen, "fetch_sources", prohibited)
    with pytest.raises(ValueError, match="Symlink"):
        repair.run(repo, source, root, api_factory=prohibited, original_run_stopped=True)
    assert bytes_under(outside) == external_before and bytes_under(source) == source_before
