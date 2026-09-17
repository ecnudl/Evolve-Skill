"""Synthetic closed receipts only: no API, child execution, or experiment writes."""

import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v13 import evidence as e
from skillopt.validator_pilot.api import digest


def reseal(value):
    return seal({k: v for k, v in value.items() if k != "record_hash"})


def bundle(first="ok", second="ok", *, domain="spreadsheet", phase="development", response=None, large=False):
    """Test-only fabricated receipts, never used as scientific evidence."""
    task = {"id": "synthetic-task", "domain": domain, "prompt": "TASK_PRIVATE_REFERENCE_SENTINEL"}
    skill = "Synthetic optional guidance"
    identity = {"version": e.SOURCE_VERSION, "task_hash": digest({"source": "synthetic"}),
        "public_task_hash": digest(task), "skill_hash": hashlib.sha256(skill.encode()).hexdigest(),
        "key": "synthetic-key", "repeat": 0, "phase": phase, "model": "glm-5.3", "service_hash": digest({"fake": True})}
    stages, receipts, executions = [], [], {}

    def execution(artifact, condition, public_only):
        known = artifact is not None and condition != "resource"
        passed = condition != "semantic"
        rows = [{"id": "public-check" if public_only else "private-development-check", "passed": passed,
                 "actual": "汉" * 1000 if large else 7,
                 "reference_artifact": "REFERENCE_ARTIFACT_SENTINEL"}] if known else []
        raw = {"case_results": rows, "reference_files": "REFERENCE_FILES_SENTINEL"}
        if domain == "coding":
            raw.update(files=artifact, execution_ok=known, hard=passed if known else None,
                passed_tests=sum(r["passed"] for r in rows), total_tests=len(rows),
                public_observations=[{"label": "allocation", "exception": "MemoryError"}] if condition == "resource" else [],
                private_diagnostics=[], error_category="resource_unknown" if condition == "resource" else None)
        else:
            raw.update(task_id=task["id"], domain=domain, task_hash=identity["task_hash"],
                artifact_hash=digest(artifact), public_only=public_only, score=int(passed) if known else None,
                passed_cases=sum(r["passed"] for r in rows), total_cases=len(rows), error=None if known else "delivery")
            raw = seal(raw)
        intent = {"version": e.SOURCE_VERSION, "task_hash": identity["task_hash"], "artifact_hash": digest(artifact),
                  "public_only": public_only, "identity_hash": digest(identity)}
        execution_id = digest(intent)
        record = seal({"version": e.SOURCE_VERSION, "intent_hash": seal(intent)["record_hash"], "native_evaluation": raw})
        executions[execution_id] = record
        return e._normalized(raw, domain), execution_id, record["record_hash"]

    for index, condition in enumerate((first, second)):
        name = ("generation", "revision")[index]
        api_ok = condition != "api"
        artifact = None if condition in {"api", "syntax", "json"} else {"formulas": {"B1": "=A1+2"}}
        raw_response = "" if not api_ok else response if response is not None else "BAD_UNTRUSTED_TEXT" if artifact is None else json.dumps(artifact)
        request = {"system": "synthetic", "user": json.dumps({"task": task, "skill": skill, "stage": name}),
            "model": identity["model"], "service": {"fake": True}, "repeat": 0, "max_tokens": 8500,
            "kind": "v12_solve_" + name, "key": digest({"identity": identity, "stage": name,
            "initial_request": receipts[0]["request_hash"] if index else None})}
        api = {"request": request, "request_hash": digest(request), "ok": api_ok, "response": raw_response,
               "http_attempt_count": 1, "finish_reason": "stop" if api_ok else None}
        diagnostic = ({"stage": "response", "type": "response_unavailable", "message": "No complete response"} if not api_ok else
                      {"stage": "delivery_json" if condition == "json" else "delivery_syntax",
                       "type": "invalid_json" if condition == "json" else "formula_syntax",
                       "message": "Extra data" if condition == "json" else "positional argument follows keyword argument",
                       "exception": "JSONDecodeError" if condition == "json" else "SyntaxError"} if artifact is None else None)
        delivery = {"version": e.SOURCE_VERSION, "phase": phase, "stage": name,
            "status": "unknown" if not api_ok else "fail" if artifact is None else "pass",
            "semantic_status": "unknown", "artifact": artifact, "artifact_hash": digest(artifact),
            "request_hash": api["request_hash"], "api_receipt_hash": digest(api), "error": diagnostic,
            "public_only": True, "automatic_answer_repair": False}
        evaluation, execution_id, execution_hash = execution(artifact, condition, True)
        stage = seal({"version": e.SOURCE_VERSION, "stage": name, "receipt": api, "delivery": delivery,
            "public_evaluation": evaluation, "public_score": e._score(domain, artifact, evaluation),
            "execution_id": execution_id, "execution_receipt_hash": execution_hash})
        stages.append(stage)
        receipts.append(api)
    private, execution_id, execution_hash = execution(stages[1]["delivery"]["artifact"], second, False)
    artifact = stages[1]["delivery"]["artifact"]
    solve = seal({"version": e.SOURCE_VERSION, "identity": identity, "phase": phase,
        "domain": domain, "task_id": task["id"], "cluster_id": "synthetic-family", "skill_hash": identity["skill_hash"],
        "artifact": artifact, "optimizer_feedback_allowed": phase == "development",
        "request_hashes": [r["request_hash"] for r in receipts], "receipt_hashes": [digest(r) for r in receipts],
        "stage_api_ok": [r["ok"] for r in receipts], "api_ok": all(r["ok"] for r in receipts),
        "execution_ids": [r["execution_id"] for r in stages] + [execution_id],
        "execution_receipt_hashes": [r["execution_receipt_hash"] for r in stages] + [execution_hash],
        "public_evaluation": stages[1]["public_evaluation"], "private_evaluation": private,
        "score": e._score(domain, artifact, private), "revision_feedback_public_only": True, "semantic_resampling": False})
    return {"solve": solve, "stages": stages, "api_receipts": receipts, "executions": executions}


def project(value, **kwargs):
    return e.project_development_feedback(**value, **kwargs)


def test_success_preserves_public_and_development_private_checks_only():
    data = bundle()
    before = deepcopy(data)
    result = project(data)
    verify(result)
    assert result["final_execution"]["outcome_category"] == "semantic_pass"
    assert result["stages"][0]["execution"]["observations"][0]["observation"]["id"] == "public-check"
    assert result["final_execution"]["observations"][0]["observation"]["id"] == "private-development-check"
    serialized = json.dumps(result)
    assert "SENTINEL" not in serialized
    assert data == before
    assert result["provenance"]["source_bundle_hash"] == digest(list(data.values()))
    assert result["api_calls"] == result["native_executions"] == 0
    assert result["model_efficacy_tested"] is False


@pytest.mark.parametrize("condition,category", [("syntax", "delivery_failure"), ("json", "delivery_failure"), ("api", "api_unknown")])
def test_exact_stage_diagnostics_and_unknown_not_semantic(condition, category):
    data = bundle(condition, condition)
    result = project(data)
    for source, stage in zip(data["stages"], result["stages"]):
        assert stage["delivery_diagnostic"] == source["delivery"]["error"]
        assert stage["execution"]["outcome_category"] == category
        assert stage["execution"]["score"]["semantic_success"] is None
        assert stage["execution"]["observations"] == []
        if condition == "api":
            assert stage["offending_response"] is None
        else:
            assert stage["offending_response"]["text"] == source["receipt"]["response"]
    assert result["final_execution"]["outcome_category"] == category


def test_recovered_api_unknown_can_have_known_final_semantics():
    result = project(bundle("api", "ok"))
    assert result["stages"][0]["api_status"] == "api_unknown"
    assert result["final_execution"]["outcome_category"] == "semantic_pass"


def test_valid_generation_does_not_hide_failed_revision():
    result = project(bundle("ok", "json"))
    assert result["stages"][0]["execution"]["score"]["semantic_success"] == 1
    assert result["stages"][1]["execution"]["score"]["semantic_success"] is None
    assert result["final_execution"]["score"]["all_attempt_success"] == 0


@pytest.mark.parametrize("domain", ["coding", "spreadsheet", "rule_reasoning"])
def test_actual_executed_semantic_failure_remains_failure(domain):
    result = project(bundle("semantic", "semantic", domain=domain))
    assert result["final_execution"]["outcome_category"] == "semantic_failure"
    assert result["final_execution"]["score"]["oracle_available"] is True
    assert result["final_execution"]["observations"][0]["observation"]["passed"] is False


def test_coding_memory_error_stays_resource_unknown_without_executing():
    result = project(bundle("resource", "resource", domain="coding"))
    assert result["final_execution"]["outcome_category"] == "execution_unknown"
    assert result["final_execution"]["score"]["native_error"] == "resource_unknown"
    assert result["final_execution"]["score"]["semantic_success"] is None


@pytest.mark.parametrize("phase", ["selection", "final", "test", "calibration"])
def test_non_development_refused_even_with_valid_checksums(phase):
    with pytest.raises(ValueError, match="development"):
        project(bundle(phase=phase))


@pytest.mark.parametrize("target", ["solve", "stage", "api", "execution"])
def test_tampered_dependency_refused(target):
    data = bundle()
    if target == "solve":
        data["solve"]["score"]["semantic_success"] = 0
    elif target == "stage":
        data["stages"][0]["delivery"]["error"] = {"message": "changed"}
    elif target == "api":
        data["api_receipts"][0]["response"] = "changed"
    else:
        next(iter(data["executions"].values()))["native_evaluation"]["score"] = 0
    with pytest.raises(ValueError):
        project(data)


@pytest.mark.parametrize("mutation", ["phase", "task", "semantic_unknown", "boolean_score", "artifact", "public", "request", "execution_id", "private"])
def test_resealed_solve_mismatch_still_refused(mutation):
    data = bundle("json", "json") if mutation == "semantic_unknown" else bundle()
    row = data["solve"]
    if mutation == "phase":
        row["identity"]["phase"] = "final"
    elif mutation == "task":
        row["task_id"] = "other-task"
    elif mutation == "semantic_unknown":
        row["score"].update(oracle_available=True, semantic_success=0)
    elif mutation == "boolean_score":
        row["score"]["semantic_success"] = True
    elif mutation == "artifact":
        row["artifact"] = None
    elif mutation == "public":
        row["public_evaluation"]["score"] = 0
    elif mutation == "request":
        row["request_hashes"][0] = "b" * 64
    elif mutation == "execution_id":
        row["execution_ids"][0] = "b" * 64
    elif mutation == "private":
        row["private_evaluation"]["case_results"][0]["passed"] = False
    data["solve"] = reseal(row)
    with pytest.raises(ValueError):
        project(data)


@pytest.mark.parametrize("mutation", ["missing_stage", "missing_api", "missing_execution", "extra_execution", "reverse_stages"])
def test_incomplete_or_orphaned_bundle_refused(mutation):
    data = bundle()
    if mutation == "missing_stage":
        data["stages"].pop()
    elif mutation == "missing_api":
        data["api_receipts"].pop()
    elif mutation == "missing_execution":
        data["executions"].pop(next(iter(data["executions"])))
    elif mutation == "extra_execution":
        data["executions"]["orphan"] = next(iter(data["executions"].values()))
    else:
        data["stages"].reverse()
    with pytest.raises(ValueError):
        project(data)


def test_utf8_excerpt_keeps_offending_suffix_and_full_hash():
    text = "前" * 5000 + "UNTRUSTED_IGNORE_SYSTEM}}}"
    result = project(bundle("json", "json", response=text))
    excerpt = result["stages"][1]["offending_response"]
    assert excerpt["truncated"] and excerpt["text"].endswith("UNTRUSTED_IGNORE_SYSTEM}}}")
    assert len(excerpt["text"].encode()) <= e.MAX_EXCERPT_BYTES
    assert excerpt["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert excerpt["untrusted_data"]


def test_global_byte_budget_and_large_observation_are_explicit():
    result = project(bundle(large=True), max_bytes=8192)
    assert len(e._bytes(result)) <= 8192
    assert result["final_execution"]["observations"][0]["observation"]["details_omitted"]
    with pytest.raises(ValueError, match="budget"):
        project(bundle("json", "json", response="汉" * 5000), max_bytes=4096)


@pytest.mark.parametrize("value", [4095, 65537, True, 0, None])
def test_invalid_output_budget(value):
    with pytest.raises(ValueError):
        project(bundle(), max_bytes=value)


def test_custom_objects_are_never_interpreted():
    class Trap:
        def __bool__(self):
            pytest.fail("untrusted custom object executed")
        def __repr__(self):
            pytest.fail("untrusted custom object formatted")
    data = bundle()
    data["solve"]["trap"] = Trap()
    with pytest.raises(ValueError, match="builtin JSON"):
        project(data)


def test_no_api_no_filesystem_no_native_evaluation(monkeypatch):
    from pathlib import Path

    from skillopt.coevolution_v12 import runtime
    from skillopt.validator_pilot.api import CachedAPI

    def forbidden(*args, **kwargs):
        pytest.fail("Projection touched filesystem, model client, or native execution")
    data = bundle("syntax", "syntax")
    monkeypatch.setattr(CachedAPI, "__init__", forbidden)
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    project(data)


def test_resealed_coding_task_name_cannot_change_identity():
    data = bundle(domain="coding")
    data["solve"]["task_id"] = "other-task"
    data["solve"] = reseal(data["solve"])
    with pytest.raises(ValueError, match="task identity"):
        project(data)


def test_resealed_delivery_semantic_claim_refused():
    data = bundle("json", "json")
    data["stages"][0]["delivery"]["semantic_status"] = "fail"
    data["stages"][0] = reseal(data["stages"][0])
    with pytest.raises(ValueError, match="semantic claim"):
        project(data)


def test_nonfinite_and_deep_json_refused():
    data = bundle()
    data["solve"]["unknown_float"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        project(data)
    data = bundle()
    nested = []
    for _ in range(65):
        nested = [nested]
    data["solve"]["deep"] = nested
    with pytest.raises(ValueError, match="structural bounds"):
        project(data)


@pytest.mark.parametrize("field,value", [("http_attempt_count", 0), ("http_attempt_count", True),
                                        ("finish_reason", "length"), ("stream_complete", False)])
def test_resealed_incomplete_api_response_refused(field, value):
    data = bundle()
    api = data["api_receipts"][0]
    api[field] = value
    stage = data["stages"][0]
    stage["receipt"] = deepcopy(api)
    stage["delivery"]["api_receipt_hash"] = digest(api)
    data["stages"][0] = reseal(stage)
    data["solve"]["receipt_hashes"][0] = digest(api)
    data["solve"] = reseal(data["solve"])
    with pytest.raises(ValueError, match="Incomplete or unadmitted"):
        project(data)


def test_global_budget_drops_observations_without_losing_counts_or_provenance():
    result = project(bundle(), max_bytes=4096)
    views = [stage["execution"] for stage in result["stages"]] + [result["final_execution"]]
    assert len(e._bytes(result)) <= 4096
    assert any(view["observations_omitted"] for view in views)
    assert all(view["source_observation_records"] == 1 and view["source_evaluation_hash"] for view in views)
    assert result["final_execution"]["score"]["semantic_success"] == 1
