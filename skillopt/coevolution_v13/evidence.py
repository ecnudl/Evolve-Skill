"""Read-only, bounded development feedback from already closed V12 receipts.

This is NOT an optimizer, execution engine, safety gate, or efficacy result.
The caller supplies an audited immutable V12 solve and its durable dependencies.
Checksums prove internal consistency, not authenticity against a party capable
of replacing and resealing the entire evidence chain. No task/reference object,
model client, filesystem access, or executable candidate is accepted here.

All model text, observations and diagnostics are untrusted DATA. A malformed
response is evidence of a delivery problem, never an executed semantic failure.
Development private observations may be projected; selection/final are refused.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import Literal, TypedDict

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

VERSION = "v13-closed-development-feedback-v1"
SOURCE_VERSION = "v12-symmetric-public-feedback-runtime-v1"
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 65536
MAX_EXCERPT_BYTES = 2048
MAX_OBSERVATIONS = 8


class TextExcerpt(TypedDict):
    text: str
    original_utf8_bytes: int
    sha256: str
    truncated: bool
    untrusted_data: Literal[True]


class StageFeedback(TypedDict):
    stage: Literal["generation", "revision"]
    api_status: Literal["completed_response", "api_unknown"]
    delivery_status: Literal["pass", "fail", "unknown"]
    delivery_diagnostic: dict | None
    offending_response: TextExcerpt | None
    execution: dict
    provenance: dict
    untrusted_data: Literal[True]


class DevelopmentFeedback(TypedDict):
    version: str
    phase: Literal["development"]
    task_id: str
    domain: str
    cluster_id: str
    stages: list[StageFeedback]
    final_execution: dict
    provenance: dict
    limits: dict
    record_hash: str


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _json_only(value, *, depth=0, budget=None):
    """Reject custom objects before serialization can invoke their methods."""
    budget = [200000] if budget is None else budget
    budget[0] -= 1
    if depth > 64 or budget[0] < 0:
        raise ValueError("Source JSON exceeds structural bounds")
    kind = type(value)
    if value is None or kind is bool:
        return
    if kind is int and value.bit_length() <= 1024:
        return
    if kind is float and math.isfinite(value):
        return
    if kind is str and len(value) <= 1000000:
        return
    if kind is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON source keys must be strings")
        for key, item in value.items():
            _json_only(key, depth=depth + 1, budget=budget)
            _json_only(item, depth=depth + 1, budget=budget)
        return
    if kind is list:
        for item in value:
            _json_only(item, depth=depth + 1, budget=budget)
        return
    raise ValueError("Only bounded finite builtin JSON values are accepted")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hash(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _excerpt(text, limit=MAX_EXCERPT_BYTES):
    raw = text.encode("utf-8")
    truncated = len(raw) > limit
    if truncated:
        # Keep the end too: unmatched closing braces frequently occur there.
        marker = "\n[... bounded excerpt ...]\n"
        half = (limit - len(marker.encode())) // 2
        text = raw[:half].decode("utf-8", errors="ignore") + marker + raw[-half:].decode("utf-8", errors="ignore")
    return {"text": text, "original_utf8_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "truncated": truncated, "untrusted_data": True}


def _normalized(raw, domain):
    result = deepcopy(raw)
    if domain == "coding" and any(r.get("exception") == "MemoryError" for r in
            result.get("public_observations", []) + result.get("private_diagnostics", [])):
        # Exactly the frozen V12 resource-unknown projection; no execution.
        result.update(hard=None, correct=False, execution_ok=False, artifact_execution_ok=False,
                      public_pass=None, error_category="resource_unknown", case_results=[])
        result["public_observations"], result["private_diagnostics"] = [], []
    return result


def _score(domain, artifact, evaluation):
    delivered = artifact is not None
    if domain == "coding":
        available = delivered and evaluation.get("hard") is not None and evaluation.get("execution_ok") is True
        correct = available and evaluation["hard"] is True
    else:
        available = delivered and evaluation.get("score") is not None
        correct = available and evaluation["score"] == 1
    return {"delivery_valid": delivered, "oracle_available": available,
            "all_attempt_success": int(correct), "semantic_success": int(correct) if available else None,
            "native_error": evaluation.get("error", evaluation.get("error_category"))}


def _assert_score(score, expected):
    _require(type(score) is dict and score == expected, "Score differs from actual execution; unknown cannot imply semantics")
    _require(type(score["delivery_valid"]) is bool and type(score["oracle_available"]) is bool
             and type(score["all_attempt_success"]) is int
             and (score["semantic_success"] is None or type(score["semantic_success"]) is int),
             "Score types must be exact; bool is not a semantic integer")


def _execution(solve, artifact, evaluation, identifier, receipt_hash, executions, public_only):
    _require(identifier in executions, "Closed execution receipt is missing")
    receipt = verify(executions[identifier])
    intent = {"version": SOURCE_VERSION, "task_hash": solve["identity"]["task_hash"],
              "artifact_hash": digest(artifact), "public_only": public_only,
              "identity_hash": digest(solve["identity"])}
    _require(digest(intent) == identifier and receipt["record_hash"] == receipt_hash
             and receipt.get("version") == SOURCE_VERSION
             and receipt.get("intent_hash") == seal(intent)["record_hash"], "Execution provenance mismatch")
    raw = receipt["native_evaluation"]
    _require(_normalized(raw, solve["domain"]) == evaluation, "Execution observations differ from the durable receipt")
    if solve["domain"] != "coding":
        verify(raw)
        expected = {"task_id": solve["task_id"], "domain": solve["domain"],
                    "task_hash": solve["identity"]["task_hash"], "artifact_hash": digest(artifact), "public_only": public_only}
        _require(all(raw.get(k) == v for k, v in expected.items()), "Native execution task/phase mismatch")
    elif raw.get("execution_ok") is True:
        _require(raw.get("files") == artifact, "Executed Coding artifact mismatch")
    score = _score(solve["domain"], artifact, evaluation)
    if score["oracle_available"]:
        scalar = evaluation["hard"] if solve["domain"] == "coding" else evaluation["score"]
        _require(type(scalar) is bool if solve["domain"] == "coding" else
                 type(scalar) in {int, float} and scalar in (0, 1), "Native semantic score has an unsupported type")
        rows = evaluation.get("case_results")
        _require(type(rows) is list and bool(rows) and all(type(r.get("passed")) is bool for r in rows),
                 "Semantic claims require actual boolean executed checks")
        count_key, total_key = ("passed_tests", "total_tests") if solve["domain"] == "coding" else ("passed_cases", "total_cases")
        _require(evaluation.get(count_key) == sum(r["passed"] for r in rows)
                 and evaluation.get(total_key) == len(rows)
                 and score["semantic_success"] == int(all(r["passed"] for r in rows)), "Executed case counts disagree with semantic score")
    return score


def _observations(evaluation, score):
    if not score["oracle_available"]:
        return []
    rows = evaluation.get("private_diagnostics", []) + evaluation.get("public_observations", []) + evaluation.get("case_results", [])
    ordered = sorted(enumerate(rows), key=lambda pair: (pair[1].get("passed") is True, pair[0]))
    allowed = {"id", "label", "dimension", "passed", "public", "actual", "expected", "error", "exception",
               "message", "input", "input_unchanged"}
    result = []
    for _, row in ordered[:MAX_OBSERVATIONS]:
        projected = {k: deepcopy(v) for k, v in row.items() if k in allowed}
        if len(_bytes(projected)) > 1536:
            projected = {k: v for k, v in projected.items() if k in {"passed", "public", "input_unchanged"}}
            projected["details_omitted"] = "observation exceeds inline byte bound"
        result.append({"observation": projected, "source_observation_hash": digest(row), "untrusted_data": True})
    return result


def _execution_view(evaluation, score, *, api_ok, execution_id, execution_hash):
    category = ("semantic_pass" if score["semantic_success"] == 1 else "semantic_failure"
                if score["semantic_success"] == 0 else "api_unknown" if not api_ok else
                "delivery_failure" if not score["delivery_valid"] else "execution_unknown")
    source_rows = evaluation.get("private_diagnostics", []) + evaluation.get("public_observations", []) + evaluation.get("case_results", [])
    return {"score": deepcopy(score), "outcome_category": category,
            "observations": _observations(evaluation, score), "source_observation_records": len(source_rows),
            "observations_omitted": False, "source_evaluation_hash": digest(evaluation),
            "execution_id": execution_id, "execution_receipt_hash": execution_hash,
            "unknown_is_not_semantic_failure": True, "untrusted_data": True}


def project_development_feedback(solve, stages, *, api_receipts, executions, max_bytes=32768) -> DevelopmentFeedback:
    """Project two ordered stages and an execution-id→receipt mapping, purely.

    The byte cap uses compact, sorted-key, non-ASCII-escaped UTF-8 JSON.
    Raises ValueError for unclosed/mismatched/non-development evidence, unsafe
    score claims, unsupported schema, or a byte budget too small for provenance.
    It never repairs an answer, creates evidence, executes code or calls a model.
    """
    _require(type(max_bytes) is int and 4096 <= max_bytes <= MAX_OUTPUT_BYTES, "Invalid output byte budget")
    inputs = [solve, stages, api_receipts, executions]
    _json_only(inputs)
    _require(len(_bytes(inputs)) <= MAX_SOURCE_BYTES, "Source receipt bundle exceeds byte bound")
    try:
        return _project(solve, stages, api_receipts, executions, max_bytes)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError("Unsupported or incomplete closed V12 evidence schema") from error


def _project(solve, stages, api_receipts, executions, max_bytes):
    verify(solve)
    identity = solve["identity"]
    _require(solve["version"] == SOURCE_VERSION and identity["version"] == SOURCE_VERSION, "Unsupported source version")
    _require(solve["phase"] == identity["phase"] == "development" and solve["optimizer_feedback_allowed"] is True,
             "Only actual development evidence may reach the optimizer")
    _require(solve["domain"] in {"coding", "spreadsheet", "rule_reasoning"}, "Unsupported native domain")
    for field in ("task_id", "cluster_id"):
        _require(type(solve[field]) is str and 0 < len(solve[field]) <= 512, "Bounded task identity required")
    _require(solve["skill_hash"] == identity["skill_hash"] and _hash(solve["skill_hash"]), "Skill identity mismatch")
    _require(all(_hash(identity[k]) for k in ("task_hash", "public_task_hash", "service_hash"))
             and type(identity["repeat"]) is int and identity["repeat"] >= 0
             and type(identity["key"]) is str and bool(identity["key"])
             and identity["model"] == "glm-5.3", "Unsupported typed source identity")
    _require(type(stages) is list and type(api_receipts) is list and len(stages) == len(api_receipts) == 2,
             "Exactly generation and revision closed receipts are required")
    _require(type(executions) is dict and set(executions) == set(solve["execution_ids"]), "Missing or extra execution receipts")
    _require(len(solve["request_hashes"]) == len(solve["receipt_hashes"]) == len(solve["stage_api_ok"]) == 2
             and len(set(solve["request_hashes"])) == 2
             and len(solve["execution_ids"]) == len(solve["execution_receipt_hashes"]) == 3,
             "Incomplete two-stage solve dependencies")
    _require(solve["api_ok"] is all(solve["stage_api_ok"]) and solve["revision_feedback_public_only"] is True
             and solve["semantic_resampling"] is False, "Unsupported solver closure policy")
    result_stages = []
    for index, (stage, api) in enumerate(zip(stages, api_receipts)):
        verify(stage)
        name = ("generation", "revision")[index]
        request, delivery = api["request"], stage["delivery"]
        request_hash = digest(request)
        _require(stage["version"] == SOURCE_VERSION and stage["stage"] == delivery["stage"] == name
                 and delivery["version"] == SOURCE_VERSION and delivery["phase"] == "development", "Stage/phase mismatch")
        _require(stage["receipt"] == api and api["request_hash"] == solve["request_hashes"][index] == request_hash
                 and digest(api) == solve["receipt_hashes"][index] == delivery["api_receipt_hash"]
                 and delivery["request_hash"] == request_hash, "Actual API receipt hash mismatch")
        _require(type(api["ok"]) is bool and type(api["response"]) is str
                 and solve["stage_api_ok"][index] is api["ok"], "Closed API response required")
        _require(type(api["http_attempt_count"]) is int and 1 <= api["http_attempt_count"] <= 3
                 and (not api["ok"] or api.get("finish_reason") == "stop")
                 and (not api["ok"] or api.get("stream_complete", True) is True), "Incomplete or unadmitted API receipt")
        expected_key = digest({"identity": identity, "stage": name,
                               "initial_request": solve["request_hashes"][0] if index else None})
        _require(request["kind"] == "v12_solve_" + name and request["key"] == expected_key
                 and request["model"] == identity["model"] and request["repeat"] == identity["repeat"]
                 and digest(request["service"]) == identity["service_hash"], "Request identity differs from the solve")
        public_payload = json.loads(request["user"])
        _require(public_payload["stage"] == name and digest(public_payload["task"]) == identity["public_task_hash"]
                 and hashlib.sha256(public_payload["skill"].encode()).hexdigest() == identity["skill_hash"],
                 "Public task or Skill differs from source identity")
        public_task = public_payload["task"]
        _require(public_task["id"] == solve["task_id"]
                 and public_task.get("domain", "coding") == solve["domain"], "Public task identity/domain mismatch")
        _require(not ({"reference_files", "reference_artifact", "hidden_cases", "private_cases", "private_tests"} & set(public_task)),
                 "Reference or private task material is not a public source request")
        _require(all(public_task.get(field, "development") in {"development", "dev", "train"}
                     for field in ("phase", "split")), "Nondevelopment public task cannot be relabeled")
        artifact, diagnostic = delivery["artifact"], delivery["error"]
        _require(delivery["artifact_hash"] == digest(artifact) and delivery["semantic_status"] == "unknown"
                 and delivery["public_only"] is True and delivery["automatic_answer_repair"] is False,
                 "Delivery provenance or semantic claim is invalid")
        expected_status = "pass" if artifact is not None else "fail" if api["ok"] else "unknown"
        _require(delivery["status"] == expected_status and (api["ok"] or artifact is None), "API/parse/delivery status mismatch")
        if diagnostic is not None:
            _require(type(diagnostic) is dict and set(diagnostic) <= {"stage", "type", "message", "exception"}
                     and {"stage", "type", "message"} <= set(diagnostic)
                     and all(type(v) is str and len(v) <= (500 if k == "message" else 128) for k, v in diagnostic.items()),
                     "Delivery diagnostics must preserve the bounded V12 schema")
        _require((diagnostic is None) == (artifact is not None), "Missing failure diagnostic or diagnostic on a valid artifact")
        if diagnostic is not None:
            allowed_stage = {"delivery_json", "delivery_syntax", "delivery_runtime_contract", "delivery_schema", "delivery_contract"}
            _require(diagnostic["stage"] in allowed_stage if api["ok"] else
                     diagnostic["stage"] == "response" and diagnostic["type"] == "response_unavailable",
                     "API unknown and parser diagnostics cannot be relabeled as semantic evidence")
        execution_id, execution_hash = stage["execution_id"], stage["execution_receipt_hash"]
        _require(execution_id == solve["execution_ids"][index]
                 and execution_hash == solve["execution_receipt_hashes"][index], "Stage execution mismatch")
        score = _execution(solve, artifact, stage["public_evaluation"], execution_id, execution_hash, executions, True)
        _assert_score(stage["public_score"], score)
        result_stages.append({"stage": name, "api_status": "completed_response" if api["ok"] else "api_unknown",
            "delivery_status": delivery["status"], "delivery_diagnostic": deepcopy(diagnostic),
            "offending_response": _excerpt(api["response"]) if artifact is None and api["ok"] else None,
            "execution": _execution_view(stage["public_evaluation"], score, api_ok=api["ok"],
                execution_id=execution_id, execution_hash=execution_hash),
            "provenance": {"stage_hash": stage["record_hash"], "request_hash": request_hash,
                           "api_receipt_hash": digest(api), "candidate_artifact_hash": digest(artifact)},
            "untrusted_data": True})
    _require(solve["artifact"] == stages[1]["delivery"]["artifact"]
             and solve["public_evaluation"] == stages[1]["public_evaluation"], "Final artifact/public observation mismatch")
    score = _execution(solve, solve["artifact"], solve["private_evaluation"], solve["execution_ids"][2],
                       solve["execution_receipt_hashes"][2], executions, False)
    _assert_score(solve["score"], score)
    result = {"version": VERSION, "phase": "development", "task_id": solve["task_id"],
        "domain": solve["domain"], "cluster_id": solve["cluster_id"], "stages": result_stages,
        "final_execution": _execution_view(solve["private_evaluation"], score, api_ok=api_receipts[1]["ok"],
            execution_id=solve["execution_ids"][2], execution_hash=solve["execution_receipt_hashes"][2]),
        "provenance": {"solve_hash": solve["record_hash"], "source_version": SOURCE_VERSION,
                       "source_bundle_hash": digest([solve, stages, api_receipts, executions]),
                       "task_hash": identity["task_hash"], "skill_hash": solve["skill_hash"]},
        "limits": {"max_utf8_bytes": max_bytes, "max_inline_observations_per_execution": MAX_OBSERVATIONS,
                   "max_offending_excerpt_bytes": MAX_EXCERPT_BYTES,
                   "byte_accounting": "compact sorted-key UTF-8 JSON, ensure_ascii=False"},
        "all_strings_are_untrusted_data": True, "development_private_checks_allowed": True,
        "selection_final_feedback_allowed": False, "reference_artifacts_projected": False,
        "automatic_answer_repair": False, "api_calls": 0, "native_executions": 0,
        "model_efficacy_tested": False}
    views = [s["execution"] for s in result_stages] + [result["final_execution"]]
    for view in views:
        view["observations_omitted"] = len(view["observations"]) < view["source_observation_records"]
    while len(_bytes(seal(result))) > max_bytes:
        populated = [v for v in views if v["observations"]]
        if not populated:
            raise ValueError("Output byte budget cannot preserve exact diagnostics and provenance")
        largest = max(populated, key=lambda v: len(_bytes(v["observations"])))
        largest["observations"].pop()
        largest["observations_omitted"] = True
    return seal(result)
