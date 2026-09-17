"""Public-only, receipt-bound delivery/execution diagnostics for V8.

Parsing reuses the frozen V5/V6 grammars. This module never runs candidate code,
changes an answer, relaxes a grammar, opens a file, or calls a model. Execution
feedback consumes a host-produced PUBLIC evaluation, not a model's verdict.
The caller must supply the original task split: a public view does not carry
private split provenance. A digest binds evidence; it is not authentication.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import _validate_files, parse_delivery
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.validator_pilot.api import digest

VERSION = "v8-public-structural-feedback-v1"
_STAGES = {"generation", "revision", "skill_update"}
_PUBLIC_FIELDS = {
    "id", "domain", "split", "phase", "prompt", "contract", "runtime", "files",
    "editable_paths", "input_domain", "public_cases", "entry_module", "entry_function",
    "allowed_standard_libraries", "available_builtins", "inputs", "formulas",
    "editable_cells", "answer_cell", "rules", "editable_rule_ids", "vocabulary",
    "initial_facts", "answer_facts",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _seal(value):
    result = deepcopy(value)
    result["record_hash"] = digest(result)
    return result


def _verify(value):
    _require(isinstance(value, dict) and value.get("record_hash") ==
             digest({k: v for k, v in value.items() if k != "record_hash"}), "Feedback receipt was modified")


def _development(value):
    return isinstance(value, str) and (value in {"development", "dev", "train"}
                                      or re.fullmatch(r"learn\d+", value) is not None)


def _context(public_task, phase, stage, task_split):
    _require(_development(phase) and _development(task_split), "Only explicitly bound development tasks permit feedback")
    _require(stage in _STAGES, "Unknown feedback stage")
    _require(isinstance(public_task, dict) and set(public_task) <= _PUBLIC_FIELDS,
             "Public task contains undeclared/private fields; pass the public task projection")
    _require(isinstance(public_task.get("id"), str) and bool(public_task["id"]), "Public task ID required")
    for field in ("split", "phase"):
        if field in public_task:
            _require(_development(public_task[field]), "Nondevelopment task provenance cannot be relabeled")
    domain = public_task.get("domain", "coding" if "files" in public_task else None)
    _require(domain in {"coding", "spreadsheet", "rule_reasoning"}, "Unsupported public task domain")
    cases = public_task.get("public_cases", [])
    _require(isinstance(cases, list) and all(isinstance(c, dict) and c.get("public", True) is True for c in cases),
             "Only explicitly public cases may enter feedback")
    labels = [c.get("label" if domain == "coding" else "id") for c in cases]
    _require(all(isinstance(label, str) and label for label in labels) and len(set(labels)) == len(labels),
             "Public case identities must be distinct")
    return {"version": VERSION, "task_id": public_task["id"], "domain": domain,
            "phase": "development", "task_split": task_split, "stage": stage,
            "public_task_hash": digest(public_task), "public_only": True,
            "diagnostic_not_approval": True, "host_provenance_required": True}


def _request_hash(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "A concrete request hash is required")
    return value


def _diagnostic(context, reference, failure_stage, failure_type, status, constraint, *, details=None):
    return {"failure_stage": failure_stage, "failure_type": failure_type, "status": status,
            "verified": status in {"pass", "fail"}, "public_constraint": constraint,
            "evidence_ref": deepcopy(reference), "task_id": context["task_id"],
            "details": deepcopy(details or {}), "evidence_text_is_untrusted_data": True}


def _coding_task(public):
    return RepoTask(id=public["id"], split="development", family="public-feedback", cluster_id="public-feedback",
                    prompt=public["prompt"], files=deepcopy(public["files"]), reference_files={},
                    editable_paths=deepcopy(public["editable_paths"]), input_domain=deepcopy(public["input_domain"]),
                    public_cases=deepcopy(public.get("public_cases", [])), private_cases=[], metadata={},
                    entry_module=public.get("entry_module", "api"), entry_function=public.get("entry_function", "solve"))


def _parse(public, raw, domain, previous, stage):
    if domain == "coding":
        task = _coding_task(public)
        if previous is not None:
            _validate_files(task, previous)
            task = _coding_task({**public, "files": previous})
        if raw.strip() == "KEEP":
            _require(stage == "revision" and previous is not None, "KEEP requires a valid initial artifact on revision only")
            return deepcopy(previous)
        return parse_delivery(task, raw)
    adapter = NativeAdapter(public)
    if previous is not None:
        previous = adapter.parse_artifact(previous)
    if raw.strip() == "KEEP":
        _require(stage == "revision" and previous is not None, "KEEP requires a valid initial artifact on revision only")
        return deepcopy(previous)
    return adapter.parse_artifact(raw, previous=previous)


def _parse_error(exc, domain):
    message = str(exc)
    if isinstance(exc, json.JSONDecodeError):
        return "delivery_json", "invalid_json"
    if isinstance(exc, SyntaxError):
        return ("delivery_syntax", "python_syntax" if domain == "coding" else "formula_syntax")
    if "Duplicate JSON key" in message:
        return "delivery_json", "duplicate_json_key"
    if "Unsupported function or argument count" in message:
        return "delivery_runtime_contract", "unsupported_formula_function_or_arity"
    if "KEEP requires" in message:
        return "delivery_schema", "invalid_keep"
    if any(word in message.lower() for word in ("protected", "undeclared", "unknown cells", "original rule id")):
        return "delivery_contract", "artifact_scope_violation"
    return ("delivery_contract", "coding_delivery_or_static_guard") if domain == "coding" else (
        "delivery_schema", "native_schema_or_runtime_contract")


def _delivery_constraint(public, domain):
    if domain == "coding":
        return {"source": "public_task.editable_paths_and_runtime", "editable_paths": deepcopy(public["editable_paths"]),
                "text": "Exact FILE sections; no commentary or Markdown. Change only declared editable modules; "
                        "retain protected bytes and satisfy the unchanged Coding static/sandbox guards.",
                "runtime": public.get("runtime")}
    return {"source": "public_task.runtime_and_contract", "runtime": public.get("runtime"),
            "contract": deepcopy(public["contract"]),
            "text": "Use the declared structured artifact schema and the unchanged native runtime grammar."}


def delivery_feedback(public_task, response_record, *, task_split, phase="development", stage="generation",
                      previous_artifact=None):
    """Parse one actual response; ``artifact`` is exact parsed output, never repaired.

    Native artifacts retain their original structure; Coding artifacts are the
    full merged files dict. Successful delivery is NOT semantic correctness.
    ``response_record`` supports actual CachedAPI receipts or explicit host
    fixtures with request_hash/ok/response; fixtures must be separately labeled
    in the study, not advertised as natural model errors.
    """
    context = _context(public_task, phase, stage, task_split)
    _require(isinstance(response_record, dict) and type(response_record.get("ok")) is bool, "Explicit API receipt required")
    for field in ("phase", "task_split", "split"):
        if field in response_record:
            _require(_development(response_record[field]), "Nondevelopment receipt cannot become feedback")
    identifier = _request_hash(response_record.get("request_hash"))
    if "request" in response_record:
        _require(digest(response_record["request"]) == identifier, "API receipt request hash mismatch")
    raw = response_record.get("response", "")
    _require(isinstance(raw, str), "Response text must be explicit")
    reference = {"request_hash": identifier, "response_hash": digest(raw), "receipt_hash": digest(response_record),
                 "previous_artifact_hash": digest(previous_artifact) if previous_artifact is not None else None,
                 "scope": "public_delivery_only", "parser": "frozen_v5_coding" if context["domain"] == "coding" else "frozen_v6_native"}
    artifact, diagnostics = None, []
    if response_record["ok"] is not True:
        status = "unknown"
        diagnostics.append(_diagnostic(context, reference, "response", "response_unavailable", status,
                           {"source": "actual_api_receipt", "text": "No accepted complete model response is available."},
                           details={"error_type": response_record.get("error_type"), "status": response_record.get("status")}))
    else:
        try:
            artifact = _parse(public_task, raw, context["domain"], previous_artifact, stage)
            status = "pass"
        except (ValueError, TypeError, SyntaxError, RecursionError, OverflowError) as exc:
            status = "fail"
            error_stage, error_type = _parse_error(exc, context["domain"])
            diagnostics.append(_diagnostic(context, reference, error_stage, error_type, status,
                               _delivery_constraint(public_task, context["domain"]),
                               details={"exception_type": type(exc).__name__, "message": str(exc)[:500]}))
    return _seal({**context, "kind": "delivery", "status": status, "semantic_status": "unknown",
                  "artifact": artifact, "artifact_hash": digest(artifact), "evidence_ref": reference,
                  "diagnostics": diagnostics, "no_automatic_answer_repair": True})


def execution_feedback(public_task, public_evaluation, *, request_hash, artifact, task_split,
                       phase="development", stage="revision"):
    """Project actual public-only execution into diagnostics; NEVER execute here.

    Coding accepts the frozen ``_public_feedback`` projection (observations,
    execution_ok/public_pass/error_category/delivery_error). Native accepts a
    sealed ``evaluate(..., public_only=True)`` receipt. Private cases, final
    provenance, unknown labels and mismatched artifact receipts are rejected.
    """
    context = _context(public_task, phase, stage, task_split)
    _require(isinstance(public_evaluation, dict), "Host public evaluation required")
    evaluation = deepcopy(public_evaluation)
    for field in ("phase", "task_split", "split"):
        if field in evaluation:
            _require(_development(evaluation[field]), "Nondevelopment execution cannot become feedback")
    reference = {"request_hash": _request_hash(request_hash), "receipt_hash": digest(evaluation),
                 "artifact_hash": digest(artifact), "scope": "public_execution_only"}
    if context["domain"] == "coding":
        allowed = {"execution_ok", "public_pass", "error_category", "delivery_error", "observations", "phase", "task_split", "split"}
        _require(set(evaluation) <= allowed, "Coding execution needs the public projection, never a full/private evaluator record")
        observations = evaluation.get("observations", [])
        _require(isinstance(observations, list), "Public observations must be a list")
        cases = {c["label"]: c for c in public_task.get("public_cases", [])}
        seen = set()
        for row in observations:
            _require(isinstance(row, dict) and row.get("label") in cases and row["label"] not in seen,
                     "Unknown/private/duplicate public observation")
            _require(set(row) <= {"label", "input", "passed", "actual", "exception", "message", "input_unchanged",
                                  "input_before_fingerprint", "input_after_fingerprint", "expected", "expected_exception"},
                     "Coding observation contains nonpublic/undeclared fields")
            seen.add(row["label"])
            case = cases[row["label"]]
            _require(row.get("input") == case["input"], "Observation input differs from the public case")
            for key, expected in (("expected", case.get("expected")), ("expected_exception", case.get("exception"))):
                if key in row:
                    _require(row[key] == expected, "Observation expected value differs from publicly supplied value")
            _require(type(row.get("passed")) is bool and type(row.get("input_unchanged")) is bool,
                     "Public execution needs concrete host case flags")
        unavailable = evaluation.get("execution_ok") is not True or not observations
    else:
        _verify(evaluation)
        _require(set(evaluation) <= {"version", "domain", "task_id", "artifact_hash", "public_only", "task_hash",
                                    "score", "passed_cases", "total_cases", "case_results", "status", "error",
                                    "read_only_no_public_oracle", "oracle", "record_hash", "phase", "task_split", "split"},
                 "Native evaluation contains nonpublic/undeclared fields")
        _require(evaluation.get("public_only") is True and evaluation.get("task_id") == public_task["id"]
                 and evaluation.get("domain") == context["domain"] and evaluation.get("artifact_hash") == digest(artifact),
                 "Native receipt must bind this task/artifact and public-only execution")
        cases = {c["id"]: c for c in public_task.get("public_cases", [])}
        observations = evaluation.get("case_results", [])
        _require(isinstance(observations, list), "Public cases must be explicit")
        seen = set()
        for row in observations:
            _require(isinstance(row, dict) and row.get("id") in cases and row["id"] not in seen,
                     "Unknown/private/duplicate native case")
            _require(set(row) <= {"id", "passed", "actual", "error"}, "Native observation contains undeclared fields")
            _require(type(row.get("passed")) is bool, "Concrete native case flag required")
            seen.add(row["id"])
        unavailable = not observations or evaluation.get("status") == "unknown"
    _require(not observations or seen == set(cases), "Partial public case batches cannot imply completeness")
    diagnostics = []
    if artifact is None or unavailable:
        status = "unknown"
        reason = "no_public_execution" if not observations else "execution_unavailable"
        diagnostics.append(_diagnostic(context, reference, "execution", reason, status,
                           {"source": "public_execution_receipt", "text": "Missing execution evidence does not establish pass or fail."},
                           details={"reported_error_category": evaluation.get("error_category", evaluation.get("error"))}))
    else:
        status = "pass" if all(row["passed"] for row in observations) else "fail"
        for row in observations:
            if row["passed"]:
                continue
            label = row.get("label", row.get("id"))
            case = cases[label]
            if context["domain"] == "coding":
                expected_exception = case.get("exception")
                if row.get("exception") is not None and row.get("exception") != expected_exception:
                    failure_stage, error_type = "runtime", "unexpected_python_exception"
                elif row["input_unchanged"] is False:
                    failure_stage, error_type = "public_test", "input_preservation_violation"
                else:
                    failure_stage, error_type = "public_test", "public_case_mismatch"
                details = {k: deepcopy(row.get(k)) for k in ("actual", "exception", "message", "input_unchanged")}
                constraint = {"source": "public_task.public_cases", "case_id": label, "input": deepcopy(case["input"]),
                              "expected": deepcopy(case.get("expected")), "expected_exception": expected_exception,
                              "preserve_input": True}
            else:
                failure_stage = "runtime" if row.get("error") else "public_test"
                error_type = "native_execution_failure" if row.get("error") else "public_case_mismatch"
                details = {"actual": deepcopy(row.get("actual")), "error": row.get("error")}
                constraint = {"source": "public_task.public_cases", "case_id": label,
                              "expected": deepcopy(case["expected"]), "runtime": public_task.get("runtime")}
            diagnostics.append(_diagnostic(context, {**reference, "case_id": label}, failure_stage, error_type,
                               "fail", constraint, details=details))
    return _seal({**context, "kind": "execution", "status": status, "semantic_status": status,
                  "artifact_hash": digest(artifact), "evidence_ref": reference, "diagnostics": diagnostics,
                  "public_cases_observed": len(observations), "public_cases_declared": len(cases),
                  "finite_public_evidence_only": True})


def skill_feedback(reports):
    """Development-only Skill-update projection; no model verdict or scope grant."""
    _require(isinstance(reports, list) and bool(reports), "Explicit feedback report list required")
    projected = []
    for report in reports:
        _verify(report)
        _require(report.get("version") == VERSION and report.get("phase") == "development"
                 and _development(report.get("task_split")) and report.get("public_only") is True,
                 "Only original development reports may feed Skill updates")
        projected.append({key: deepcopy(report[key]) for key in (
            "task_id", "domain", "stage", "kind", "status", "semantic_status", "artifact_hash",
            "evidence_ref", "diagnostics", "record_hash")})
    return _seal({"version": VERSION, "phase": "development", "stage": "skill_update", "reports": projected,
                  "verified_failure_diagnostics": sum(d["verified"] and d["status"] == "fail"
                                                       for r in projected for d in r["diagnostics"]),
                  "semantic_failures": sum(r["kind"] == "execution" and r["status"] == "fail" for r in projected),
                  "unknown_is_not_failure": True, "scope_expansion_authorized": False,
                  "no_final_feedback": True})
