"""Offline public-feedback tests: no API, hidden evaluation or model-code execution."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.coevolution_v8 import feedback as f
from skillopt.validator_pilot.api import digest


def coding():
    return RepoTask("v8-feedback-unit-coding", "development", "feedback-unit", "feedback-unit",
                    "Double the integer, preserving the caller input.",
                    {"api.py": "import logic\ndef solve(data):\n    return logic.answer(data)\n",
                     "logic.py": "def answer(data):\n    return data['n']\n"}, {}, ["logic.py"],
                    {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
                    [{"label": "visible-double", "input": {"n": 7}, "expected": 14,
                      "exception": None, "dimension": "requested_behavior", "public": True}], [], {}).public_task()


def native(domain="spreadsheet", scope="partial_update"):
    task = {"id": "v8-feedback-unit-" + domain, "domain": domain, "split": "development",
            "contract": {"change_scope": scope, "preserve_obligations": ["Preserve unrelated inputs."]
                         if scope == "partial_update" else [], "supersedes_old_policy": scope == "full_replacement"},
            "prompt": "Use the public contract and runtime exactly.", "public_cases": [], "hidden_cases": []}
    if domain == "spreadsheet":
        task.update(inputs={"A1": 7}, formulas={"B1": "=A1"}, editable_cells=["B1"],
                    public_cases=[{"id": "visible-plus-two", "overrides": {}, "expected": {"B1": 9}}])
    else:
        task.update(rules=[{"id": "r", "if": ["ready"], "then": "done"}], editable_rule_ids=["r"],
                    vocabulary=["ready", "done", "checked"], answer_facts=["done", "checked"], initial_facts=["ready"],
                    public_cases=[{"id": "visible-rule", "facts": ["ready"], "expected": ["done"]}])
    if scope == "read_only":
        task["public_cases"] = []
        if domain == "spreadsheet":
            task["answer_cell"] = "B1"
    return NativeAdapter(task)


def receipt(raw, **extra):
    return {"request_hash": digest({"host_fixture": raw}), "ok": True, "response": raw, **extra}


def deliver(public, raw, **kwargs):
    return f.delivery_feedback(public, receipt(raw), task_split="development", **kwargs)


def raw_code(source="def answer(data):\n    return data['n'] * 2\n"):
    return "<<<FILE logic.py>>>\n" + source


def coding_receipt(**updates):
    row = {"label": "visible-double", "input": {"n": 7}, "passed": False, "actual": None,
           "exception": "NameError", "message": "name 'helper' is not defined", "input_unchanged": True,
           "expected": 14, "expected_exception": None}
    row.update(updates)
    return {"execution_ok": True, "public_pass": row["passed"], "error_category": None,
            "delivery_error": None, "observations": [row]}


def execution(public, evaluation, artifact=None, **kwargs):
    return f.execution_feedback(public, evaluation, request_hash=digest("actual-test-receipt"),
                                artifact=public.get("files", {}) if artifact is None else artifact,
                                task_split="development", **kwargs)


@pytest.mark.parametrize("scope", ["partial_update", "full_replacement", "read_only"])
@pytest.mark.parametrize("domain", ["spreadsheet", "rule_reasoning"])
def test_native_unchanged_grammar_valid_artifact_not_semantic_pass(domain, scope):
    adapter = native(domain, scope)
    if scope == "read_only":
        artifact = {"answer": 7 if domain == "spreadsheet" else ["done"]}
    else:
        artifact = {"formulas": {"B1": "=A1+2"}} if domain == "spreadsheet" else {"rules": adapter.task["rules"]}
    report = deliver(adapter.public_task(), json.dumps(artifact))
    assert report["artifact"] == artifact
    assert report["status"] == "pass" and report["semantic_status"] == "unknown"
    assert report["diagnostics"] == []
    f._verify(report)


@pytest.mark.parametrize("function", ["SQRT", "SIN", "CUSTOM", "SUM"])
def test_generic_unsupported_function_has_actual_error_and_public_runtime(function):
    public = native().public_task()
    raw = json.dumps({"formulas": {"B1": f"={function}(A1)"}})
    report = deliver(public, raw)
    diagnostic = report["diagnostics"][0]
    assert report["artifact"] is None and report["status"] == "fail"
    assert report["semantic_status"] == "unknown"
    assert diagnostic["failure_stage"] == "delivery_runtime_contract"
    assert diagnostic["failure_type"] == "unsupported_formula_function_or_arity"
    assert diagnostic["details"]["message"] == "Unsupported function or argument count"
    assert diagnostic["public_constraint"]["runtime"] == public["runtime"]
    assert diagnostic["evidence_ref"]["request_hash"] == receipt(raw)["request_hash"]
    assert receipt(raw)["response"] == raw


@pytest.mark.parametrize("formula", ["=IF(A1)", "=ROUND(A1,1,2)", "=MIN()"])
def test_supported_names_still_reject_invalid_arity(formula):
    report = deliver(native().public_task(), json.dumps({"formulas": {"B1": formula}}))
    assert report["diagnostics"][0]["failure_type"] == "unsupported_formula_function_or_arity"


@pytest.mark.parametrize("raw,kind", [
    ('{"formulas":', "invalid_json"),
    ('{"formulas":{},"formulas":{}}', "duplicate_json_key"),
    ('[]', "native_schema_or_runtime_contract"),
    ('{"answer":7}', "native_schema_or_runtime_contract"),
    ('{"formulas":{"Z9":"=1"}}', "artifact_scope_violation"),
    ('{"formulas":{"B1":"=A1+"}}', "formula_syntax"),
    ('```json\n{"formulas":{"B1":"=1"}}\n```', "invalid_json"),
])
def test_native_json_schema_scope_syntax_errors_are_not_repaired(raw, kind):
    report = deliver(native().public_task(), raw)
    assert report["artifact"] is None
    assert report["diagnostics"][0]["failure_type"] == kind


def test_coding_byte_preservation_and_missing_end_are_frozen_grammar():
    source = "# retain bytes\ndef answer(data):\n    return data['n'] * 2"
    public = coding()
    report = deliver(public, raw_code(source))
    assert report["artifact"]["logic.py"] == source
    assert report["artifact"]["api.py"] == public["files"]["api.py"]
    assert report["domain"] == "coding" and report["semantic_status"] == "unknown"


@pytest.mark.parametrize("raw,kind", [
    (raw_code("def answer(:\n"), "python_syntax"),
    ("<<<FILE api.py>>>\nx=1\n", "artifact_scope_violation"),
    ("<<<FILE other.py>>>\nx=1\n", "artifact_scope_violation"),
    (raw_code("import os\n"), "coding_delivery_or_static_guard"),
    ("preface\n" + raw_code(), "coding_delivery_or_static_guard"),
    (raw_code() + raw_code(), "coding_delivery_or_static_guard"),
])
def test_coding_parse_errors_remain_frozen(raw, kind):
    report = deliver(coding(), raw)
    assert report["artifact"] is None and report["diagnostics"][0]["failure_type"] == kind


@pytest.mark.parametrize("domain", ["coding", "spreadsheet", "rule_reasoning"])
def test_keep_valid_only_after_valid_initial_artifact_on_revision(domain):
    public = coding() if domain == "coding" else native(domain).public_task()
    raw = raw_code() if domain == "coding" else json.dumps(
        {"formulas": {"B1": "=A1+2"}} if domain == "spreadsheet" else {"rules": public["rules"]})
    initial = deliver(public, raw)["artifact"]
    assert deliver(public, "KEEP", previous_artifact=initial)["status"] == "fail"
    assert deliver(public, "KEEP", stage="revision")["status"] == "fail"
    kept = deliver(public, "KEEP", stage="revision", previous_artifact=initial)
    assert kept["artifact"] == initial and kept["status"] == "pass"


def test_native_revision_merges_without_changing_prior_artifact():
    public = native().public_task()
    public["formulas"]["C1"] = "=B1"
    public["editable_cells"].append("C1")
    previous = {"formulas": {"B1": "=A1+2"}}
    snapshot = deepcopy(previous)
    report = deliver(public, '{"formulas":{"C1":"=B1*2"}}', stage="revision", previous_artifact=previous)
    assert report["artifact"] == {"formulas": {"B1": "=A1+2", "C1": "=B1*2"}}
    assert previous == snapshot


@pytest.mark.parametrize("error", ["timeout", "http_status", "truncated_content", "stream_wall_time_limit"])
def test_response_unavailable_is_unknown_not_semantic_failure(error):
    report = f.delivery_feedback(native().public_task(), receipt("", ok=False, error_type=error), task_split="dev")
    assert report["status"] == report["semantic_status"] == "unknown"
    assert not report["diagnostics"][0]["verified"]
    assert f.skill_feedback([report])["verified_failure_diagnostics"] == 0


@pytest.mark.parametrize("field", ["private_cases", "hidden_cases", "reference_files", "reference_artifact", "metadata"])
def test_no_private_task_projection(field):
    public = coding()
    public[field] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="private"):
        deliver(public, raw_code())


@pytest.mark.parametrize("split", ["final", "test", "holdout", "promotion", "calibration", "audit", "gate"])
def test_non_development_provenance_rejected(split):
    for params in ({"phase": split, "task_split": "development"}, {"task_split": split}):
        with pytest.raises(ValueError, match="development"):
            f.delivery_feedback(coding(), receipt(raw_code()), **params)
    with pytest.raises(ValueError):
        deliver({**coding(), "split": split}, raw_code())
    with pytest.raises(ValueError):
        f.delivery_feedback(coding(), receipt(raw_code(), phase=split), task_split="dev")


def test_missing_original_split_or_invalid_request_receipt_rejected():
    with pytest.raises(TypeError):
        f.delivery_feedback(coding(), receipt(raw_code()))
    with pytest.raises(ValueError, match="request hash"):
        f.delivery_feedback(coding(), receipt(raw_code(), request_hash="invented"), task_split="dev")
    with pytest.raises(ValueError, match="mismatch"):
        f.delivery_feedback(coding(), receipt(raw_code(), request={"unbound": True}), task_split="dev")


def test_coding_runtime_exception_reports_actual_public_receipt_not_reexecution(monkeypatch):
    from skillopt.coevolution_v3 import executor

    monkeypatch.setattr(executor, "evaluate", lambda *a, **k: pytest.fail("Feedback must not execute candidate code"))
    report = execution(coding(), coding_receipt())
    diagnostic = report["diagnostics"][0]
    assert report["status"] == "fail"
    assert diagnostic["failure_stage"] == "runtime"
    assert diagnostic["failure_type"] == "unexpected_python_exception"
    assert diagnostic["details"]["exception"] == "NameError"
    assert diagnostic["public_constraint"]["expected"] == 14
    assert diagnostic["evidence_ref"]["case_id"] == "visible-double"


@pytest.mark.parametrize("updates,kind", [
    ({"exception": None, "actual": 7}, "public_case_mismatch"),
    ({"exception": None, "actual": 14, "input_unchanged": False}, "input_preservation_violation"),
])
def test_public_value_and_preservation_errors(updates, kind):
    report = execution(coding(), coding_receipt(**updates))
    assert report["diagnostics"][0]["failure_type"] == kind


def test_expected_exception_pass_is_not_mistaken_for_failure():
    public = coding()
    public["public_cases"][0]["exception"] = "ValueError"
    report = execution(public, coding_receipt(passed=True, exception="ValueError", expected_exception="ValueError"))
    assert report["status"] == "pass" and report["diagnostics"] == []


@pytest.mark.parametrize("error", ["infrastructure_or_resource_failure", "transport_unavailable", None])
def test_missing_runtime_oracle_is_unknown(error):
    report = execution(coding(), {"execution_ok": False, "error_category": error, "observations": []})
    assert report["status"] == "unknown" and report["semantic_status"] == "unknown"


@pytest.mark.parametrize("change", [
    {"label": "PRIVATE_LABEL"}, {"input": {"n": 99}}, {"expected": 999}, {"expected_exception": "Wrong"},
])
def test_coding_foreign_case_evidence_rejected(change):
    with pytest.raises(ValueError):
        execution(coding(), coding_receipt(**change))


def test_full_coding_evaluator_record_with_private_data_is_rejected():
    evaluation = coding_receipt()
    evaluation["private_diagnostics"] = [{"expected": "PRIVATE_SENTINEL"}]
    with pytest.raises(ValueError, match="projection"):
        execution(coding(), evaluation)


@pytest.mark.parametrize("formula,status,error_type", [
    ("=A1+2", "pass", None), ("=A1+1", "fail", "public_case_mismatch"),
    ("=1/(A1-A1)", "fail", "native_execution_failure"),
])
def test_actual_native_public_execution_receipt(formula, status, error_type):
    adapter = native()
    artifact = {"formulas": {"B1": formula}}
    evaluation = adapter.evaluate(artifact, public_only=True)
    report = execution(adapter.public_task(), evaluation, artifact)
    assert report["status"] == status
    if error_type:
        assert report["diagnostics"][0]["failure_type"] == error_type


def test_native_read_only_without_public_oracle_is_unknown():
    adapter = native(scope="read_only")
    artifact = {"answer": 7}
    report = execution(adapter.public_task(), adapter.evaluate(artifact, public_only=True), artifact)
    assert report["status"] == "unknown" and report["public_cases_observed"] == 0


def test_native_hidden_or_mismatched_artifact_evaluation_rejected():
    adapter = native()
    artifact = {"formulas": {"B1": "=A1+2"}}
    with pytest.raises(ValueError, match="public-only"):
        execution(adapter.public_task(), adapter.evaluate(artifact, public_only=False), artifact)
    with pytest.raises(ValueError, match="artifact"):
        execution(adapter.public_task(), adapter.evaluate(artifact, public_only=True), {"formulas": {"B1": "=1"}})


def test_undeclared_execution_fields_cannot_smuggle_private_evidence():
    public = coding()
    evaluation = coding_receipt()
    evaluation["observations"][0]["private_expected"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError, match="undeclared"):
        execution(public, evaluation)
    adapter = native()
    artifact = {"formulas": {"B1": "=A1+2"}}
    evaluation = adapter.evaluate(artifact, public_only=True)
    evaluation["hidden_cases"] = ["PRIVATE_SENTINEL"]
    evaluation = f._seal({k: v for k, v in evaluation.items() if k != "record_hash"})
    with pytest.raises(ValueError, match="undeclared"):
        execution(adapter.public_task(), evaluation, artifact)


def test_skill_feedback_tampering_final_provenance_and_unknown_are_not_approval():
    report = deliver(coding(), raw_code())
    summary = f.skill_feedback([report])
    assert summary["semantic_failures"] == summary["verified_failure_diagnostics"] == 0
    assert summary["scope_expansion_authorized"] is False
    forged = deepcopy(report)
    forged["phase"] = "final"
    with pytest.raises(ValueError, match="modified"):
        f.skill_feedback([forged])
    forged = f._seal({k: v for k, v in forged.items() if k != "record_hash"})
    with pytest.raises(ValueError, match="development"):
        f.skill_feedback([forged])


def test_partial_or_duplicate_public_case_observations_rejected():
    public = coding()
    public["public_cases"].append({**public["public_cases"][0], "label": "visible-second"})
    with pytest.raises(ValueError, match="Partial"):
        execution(public, coding_receipt())
    evaluation = coding_receipt()
    evaluation["observations"] *= 2
    with pytest.raises(ValueError, match="duplicate"):
        execution(coding(), evaluation)
