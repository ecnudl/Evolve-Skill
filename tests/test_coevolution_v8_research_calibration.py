"""Synthetic offline bridge tests, not native-oracle or model efficacy evidence."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from skillopt import research_contract_repair
from skillopt.coevolution_v5 import core, evaluation
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v7 import research
from skillopt.coevolution_v7.tasks import calibration_tasks
from skillopt.coevolution_v8 import research_calibration as bridge
from skillopt.validator_pilot.api import digest
from tests.test_research_contract_repair import FakeAPI, outputs, source_fixture


def reseal(value, field="record_hash"):
    value = deepcopy(value)
    value.pop(field, None)
    return core.seal(value, field)


def imported_fixture(tmp_path, monkeypatch, *, valid=True):
    repo, _, diagnostic, packets, _ = source_fixture(tmp_path)
    source = repo / "outputs/original"
    values = outputs(packets) if valid else ["invalid repaired plan"]
    api = FakeAPI(diagnostic / "api", values)
    monkeypatch.setattr(research, "fetch_sources", lambda *_: [])
    research_contract_repair.run(repo, source, diagnostic, api_factory=lambda *_a, **_k: api,
                                 original_run_stopped=True)
    return repo, diagnostic, api


def private_preflight(adapters):
    _, artifacts = bridge._controls(adapters)
    rows = []
    for a in artifacts:
        row = core.make_assessment(check_id="coding_contract", task_id=a["task_id"], domain="coding", phase="promotion",
            artifact_hash=a["artifact_hash"], rubric_hash=core.initial_rubric()["rubric_hash"],
            status="pass" if a["truth"] == "good" else "fail", evidence_kind="execution", verified=True, gate_eligible=True,
            details={"public_only": False, "task_split": "calibration", "requested_phase": "promotion"})
        rows.append({"artifact_id": a["artifact_id"], "assessment": row})
    return core.seal({"calibration": rows, "never_model_feedback": True})


def setup(tmp_path, monkeypatch, *, clusters=2, blocks=1):
    repo, diagnostic, api = imported_fixture(tmp_path, monkeypatch)
    adapters = calibration_tasks()[:clusters]
    preflight = private_preflight(adapters)
    registry = repo / "outputs/coevolution_v8/calibration_registry"
    screen = bridge.prepare_screen(repo, diagnostic, adapters, preflight, registry,
                                   screen_id="candidate-0", round_index=1, blocks=blocks)
    return screen, adapters, preflight, api


def make_components(screen, *, benefit=True, unavailable=False):
    components, api = [], {}
    for job in screen["jobs"]:
        request = bridge.request_for_job(screen, job)
        adapter, artifact, rubric, key = bridge._job_parts(screen, job)
        value = adapter.task.public_cases[0]["input"]
        failure = unavailable and job["channel"] == "new"
        inputs = [] if failure else [value]
        raw = {"request": request, "request_hash": digest(request), "ok": not failure,
               "response": "" if failure else json.dumps({"inputs": inputs}),
               "http_attempt_count": 1, "usage": {"total_tokens": 6000 if failure else 30},
               "finish_reason": "length" if failure else "stop", "error_type": "response_error" if failure else None}
        api[raw["request_hash"]] = raw
        search = core.seal({"identity": {"version": evaluation.VERSION, "task_hash": digest(adapter.public_task()),
            "artifact_hash": artifact["artifact_hash"], "rubric_hash": rubric["rubric_hash"], "key": key, "repeat": job["block"]},
            "inputs": inputs, "schema_valid": not failure, "error": "terminal_api_result" if failure else None,
            "model_calls": 1, **evaluation._receipt_metadata(raw)})
        detects = benefit and artifact["truth"] == "bad" and job["channel"] == "new" and not failure
        rows = []
        for check in rubric["checks"]:
            details = {"task_split": "calibration", "requested_phase": "promotion"}
            if check["id"] == "coding_contract":
                status = "pass"
                details.update(public_only=True, facts={"execution_ok": True, "private_diagnostics": []},
                               case_results=[{"id": "public:behavior", "public": True, "passed": True}])
            elif check["id"] == "coding_probe":
                status = "unknown" if failure else "fail" if detects else "pass"
                if failure:
                    details["reason"] = "no_bounded_probe_inputs"
                else:
                    details["receipts"] = [{"input": value, "reference": {"ok": True, "value": 1,
                        "exception": None, "input_unchanged": True}, "actual": {"ok": True,
                        "value": 2 if detects else 1, "exception": None, "input_unchanged": True}, "passed": not detects}]
            else:
                status = "not_applicable"
            hard = status in {"pass", "fail"}
            rows.append(core.make_assessment(check_id=check["id"], task_id=artifact["task_id"], domain="coding", phase="promotion",
                artifact_hash=artifact["artifact_hash"], rubric_hash=rubric["rubric_hash"], status=status,
                evidence_kind="execution", verified=hard, gate_eligible=hard, details=details))
        components.append(core.seal({"job": job, "search": search, "assessments": rows}))
    return components, api


def test_import_schema_valid_never_activates_and_completed_revalidation_is_offline(tmp_path, monkeypatch):
    repo, diagnostic, api = imported_fixture(tmp_path, monkeypatch)

    def prohibited(*_a, **_k):
        raise AssertionError("No network, writes or final reads in import")

    monkeypatch.setattr(research_contract_repair, "make_budgeted_api", prohibited)
    monkeypatch.setattr(research_contract_repair, "write_immutable_json", prohibited)
    monkeypatch.setattr(research, "fetch_sources", prohibited)
    imported = bridge.load_proposal(repo, diagnostic)
    assert imported["candidate_rubric"] is not None and imported["proposal_only"]
    assert not imported["semantic_claims_verified"]
    assert len(api.calls) == 3


def test_invalid_diagnostic_retains_old_without_reserving_or_generating_jobs(tmp_path, monkeypatch):
    repo, diagnostic, _ = imported_fixture(tmp_path, monkeypatch, valid=False)
    registry = repo / "registry"
    result = bridge.prepare_screen(repo, diagnostic, [], {}, registry, screen_id="invalid", round_index=0)
    assert result["status"] == "no_valid_candidate_keep_old" and result["jobs"] == []
    assert result["active_rubric"] == core.initial_rubric() and not registry.exists()


def test_public_request_has_no_private_labels_reference_alternative_or_tests(tmp_path, monkeypatch):
    screen, _, _, _ = setup(tmp_path, monkeypatch)
    request = bridge.request_for_job(screen, screen["jobs"][0])
    value = json.loads(request["user"])
    assert set(value) == {"task", "current_code", "rubric"}
    assert "reference_files" not in value["task"] and "private_cases" not in value["task"]
    assert "metadata" not in value["task"] and "truth" not in value and "artifact_id" not in value
    assert request["max_tokens"] == 6000 and request["kind"] == "v5_validator_probe"
    assert screen["status"] == "reserved_not_activated"


def test_one_use_shard_rejects_new_screen_overlap_and_identical_prepare_resumes(tmp_path, monkeypatch):
    screen, adapters, preflight, _ = setup(tmp_path, monkeypatch)
    args = (screen["proposal"]["repo"], screen["proposal"]["diagnostic_root"], adapters, preflight, screen["registry_root"])
    assert bridge.prepare_screen(*args, screen_id="candidate-0", round_index=1, blocks=1) == screen
    with pytest.raises(ValueError, match="already reserved"):
        bridge.prepare_screen(*args, screen_id="another-candidate", round_index=1, blocks=1)


@pytest.mark.parametrize("overlap", ["task", "cluster", "final", "development"])
def test_calibration_must_have_independent_role_and_identity(tmp_path, monkeypatch, overlap):
    repo, diagnostic, _ = imported_fixture(tmp_path, monkeypatch)
    adapters = calibration_tasks()[:2]
    changes = {"task": {"id": "development-0"}, "cluster": {"cluster_id": "cluster-0"},
               "final": {"split": "final"}, "development": {"split": "development"}}[overlap]
    adapters[0] = CodingAdapter(replace(adapters[0].task, **changes))
    preflight = private_preflight(adapters) if overlap not in {"final", "development"} else {}
    expected = "overlap" if overlap in {"task", "cluster"} else "No development"
    with pytest.raises(ValueError, match=expected):
        bridge.prepare_screen(repo, diagnostic, adapters, preflight, repo / "outputs/coevolution_v8/registry",
                              screen_id="x", round_index=1)


@pytest.mark.parametrize("damage", ["unavailable", "wrong_rubric", "wrong_split", "missing_artifact"])
def test_preflight_label_cannot_be_model_claim_or_execution_failure(tmp_path, monkeypatch, damage):
    repo, diagnostic, _ = imported_fixture(tmp_path, monkeypatch)
    adapters = calibration_tasks()[:2]
    preflight = private_preflight(adapters)
    if damage == "missing_artifact":
        preflight["calibration"].pop()
    else:
        row = preflight["calibration"][0]["assessment"]
        if damage == "unavailable":
            row["details"]["reason"] = "infrastructure_or_resource_failure"
        elif damage == "wrong_rubric":
            row["rubric_hash"] = digest("not the current rubric")
        else:
            row["phase"] = "development"
        preflight["calibration"][0]["assessment"] = reseal(row, "receipt_hash")
    with pytest.raises(ValueError, match="preflight|calibration truth"):
        bridge.prepare_screen(repo, diagnostic, adapters, reseal(preflight), repo / "outputs/coevolution_v8/registry",
                              screen_id="x", round_index=1)


def test_full_cluster_gain_authorizes_next_round_only_not_skill_deployment(tmp_path, monkeypatch):
    screen, _, _, _ = setup(tmp_path, monkeypatch, clusters=6, blocks=4)
    components, receipts = make_components(screen)
    decision = bridge.assess_screen(screen, components, receipts)
    assert decision["activate_next_round"] and decision["active_from_round"] == 2
    assert decision["active_rubric"] == screen["proposal"]["candidate_rubric"]
    assert not decision["deployment_approval"] and not decision["raw_calibration_labels_returned"]
    assert decision["expected_components"] == decision["observed_components"] == 288
    assert "rows" not in decision and "components" not in decision and "truth" not in decision
    assert bridge.assess_screen(screen, components, receipts) == decision


def test_schema_valid_without_independent_coverage_or_gain_keeps_old(tmp_path, monkeypatch):
    screen, _, _, _ = setup(tmp_path, monkeypatch)
    components, receipts = make_components(screen, benefit=False)
    decision = bridge.assess_screen(screen, components, receipts)
    assert not decision["activate_next_round"] and decision["old_retained"]
    assert decision["active_rubric"] == screen["proposal"]["old_rubric"]
    assert "fewer_than_six_project_clusters" in decision["gate"]["reasons"]


def test_model_output_budget_unknowns_remain_in_grid_and_do_not_become_defects(tmp_path, monkeypatch):
    screen, _, _, _ = setup(tmp_path, monkeypatch)
    components, receipts = make_components(screen, unavailable=True)
    decision = bridge.assess_screen(screen, components, receipts)
    assert decision["old_retained"] and decision["complete_calibration_grid"]
    assert decision["api_diagnostic_counts"]["output_budget_exhausted_not_semantic_defect"] == 8
    assert decision["execution_unknown_counts"]["no_bounded_probe_inputs"] == 8


def test_incomplete_grid_is_terminal_hold_not_missing_cell_resampling(tmp_path, monkeypatch):
    screen, _, _, _ = setup(tmp_path, monkeypatch)
    components, receipts = make_components(screen)
    partial = components[:-1]
    used = {c["search"]["request_hash"] for c in partial}
    decision = bridge.assess_screen(screen, partial, {h: r for h, r in receipts.items() if h in used})
    assert decision["old_retained"] and not decision["complete_calibration_grid"]
    assert "independent_screen_unavailable" in decision["gate"]["reasons"]
    with pytest.raises(ValueError, match="Immutable artifact differs"):
        bridge.assess_screen(screen, components, receipts)


@pytest.mark.parametrize("damage", ["infra_as_fail", "reference_unavailable", "wrong_verdict", "private_tests", "phase", "rubric", "input"])
def test_bad_attribution_or_provenance_never_enters_gate(tmp_path, monkeypatch, damage):
    screen, _, _, _ = setup(tmp_path, monkeypatch)
    components, receipts = make_components(screen)
    first = components[0]
    index = 0 if damage == "private_tests" else 1
    row = first["assessments"][index]
    if damage == "infra_as_fail":
        row["status"] = "fail"
        row["details"]["reason"] = "infrastructure_or_resource_failure"
    elif damage == "reference_unavailable":
        row["details"]["receipts"][0]["reference"]["ok"] = False
    elif damage == "wrong_verdict":
        row["details"]["receipts"][0]["passed"] = not row["details"]["receipts"][0]["passed"]
    elif damage == "private_tests":
        row["details"]["public_only"] = False
    elif damage == "phase":
        row["details"]["requested_phase"] = "final"
    elif damage == "rubric":
        row["rubric_hash"] = digest("forged")
    else:
        row["details"]["receipts"][0]["input"] = {"invented_input": True}
    first["assessments"][index] = reseal(row, "receipt_hash")
    components[0] = reseal(first)
    with pytest.raises(ValueError):
        bridge.assess_screen(screen, components, receipts)
    assert not (Path(screen["registry_root"]) / screen["screen_id"] / "v8_decision.json").exists()


@pytest.mark.parametrize("damage", ["model", "private_payload", "duplicate_request", "extra_receipt"])
def test_exact_public_model_requests_are_required(tmp_path, monkeypatch, damage):
    screen, _, _, _ = setup(tmp_path, monkeypatch)
    components, receipts = make_components(screen)
    h = components[0]["search"]["request_hash"]
    if damage == "model":
        receipts[h]["request"]["model"] = "another-model"
    elif damage == "private_payload":
        receipts[h]["request"]["user"] += "PRIVATE_EXPECTED_LABEL"
    elif damage == "duplicate_request":
        components.append(components[0])
    else:
        receipts[digest("extra")] = receipts[h]
    with pytest.raises(ValueError):
        bridge.assess_screen(screen, components, receipts)


def test_bridge_never_reads_final_or_constructs_api_or_runs_native_oracles(tmp_path, monkeypatch):
    screen, _, _, _ = setup(tmp_path, monkeypatch)
    components, receipts = make_components(screen)

    def forbidden(*_a, **_k):
        raise AssertionError("Bridge is offline and calibration-only")

    original = Path.read_text

    def read_allowed(path, *args, **kwargs):
        assert not path.name.startswith(".env") and path.name not in {"results.json", "final_rows.json", "final_summary.json"}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_allowed)
    monkeypatch.setattr(bridge.executor, "execute_inputs", forbidden)
    monkeypatch.setattr(bridge.executor, "evaluate", forbidden)
    monkeypatch.setattr(research_contract_repair, "make_budgeted_api", forbidden)
    assert bridge.assess_screen(screen, components, receipts)["old_retained"]


@pytest.mark.parametrize("valid", [True, False])
def test_explicit_patch_diagnostic_import_requires_entire_failed_predecessor_chain(tmp_path, monkeypatch, valid):
    from skillopt.coevolution_v8 import patch_diagnostic
    from tests.test_coevolution_v8_patch_diagnostic import setup as patch_setup

    repo, _, source, diagnostic, api = patch_setup(tmp_path, monkeypatch)
    if not valid:
        api.responses = ["invalid"]
    patch_diagnostic.run(repo, source, diagnostic, api_factory=lambda *_a, **_k: api, source_run_stopped=True)
    loaded = bridge.load_proposal(repo, diagnostic)
    assert loaded["source_type"] == "completed_separate_patch_diagnostic_with_verified_failed_predecessor"
    assert (loaded["candidate_rubric"] is not None) is valid
    assert json.loads((source / "result.json").read_text())["proposed_rubric"] is None
    (source / "patch.json").unlink()
    with pytest.raises(ValueError):
        bridge.load_proposal(repo, diagnostic)


def test_task_payload_status_words_are_not_host_execution_errors():
    assert not bridge._unavailable({"receipts": [{"input": {"reason": "delivery"},
        "actual": {"ok": True, "value": {"error_category": "infrastructure_or_resource_failure"}},
        "reference": {"ok": True, "value": {"reason": "transport"}}}]})
    assert bridge._unavailable({"receipts": [{"actual": {"ok": False, "error_category": "infrastructure_or_resource_failure"}}]})


def test_registry_cannot_write_into_a_completed_diagnostic(tmp_path, monkeypatch):
    repo, diagnostic, _ = imported_fixture(tmp_path, monkeypatch)
    adapters = calibration_tasks()[:2]
    with pytest.raises(ValueError, match="isolated"):
        bridge.prepare_screen(repo, diagnostic, adapters, private_preflight(adapters), diagnostic,
                              screen_id="do-not-modify", round_index=1)
    assert not (diagnostic / "do-not-modify").exists()
