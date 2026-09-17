"""Immutable reference calibration and one-shot Coding observations.

Only the isolated runner executes code. The host compiles native predicates,
checks actual typed observations, and reconstructs every completed score from
immutable receipts. Hidden tests/reference code never enter model messages.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_artifact_sensitivity import extract_artifact
from skillopt.validator_pilot.api import digest, write_immutable_json

from . import assertions, data, executor

VERSION = "v11-one-shot-coding-evidence-v1"
TOKENS = 4096
KIND = "v11_coding_solve"
_HASH = re.compile(r"[a-f0-9]{64}\Z")


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def _read(path):
    try:
        return verify(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Missing or malformed immutable execution evidence") from error


def _save(path, value, *, completed=False):
    expected = seal(value)
    path = Path(path)
    if path.exists():
        if _read(path) != expected:
            raise ValueError("Immutable execution evidence differs from recomputed provenance")
    elif completed:
        raise ValueError("Completed run missing immutable execution evidence")
    else:
        write_immutable_json(path, expected)
    return expected


def _task_identity(task):
    public = data.public_task(task)
    if task.get("split") not in {"confirmation", "final"}:
        raise ValueError("Execution requires an explicit reserved confirmation/final split")
    if (not _hash(task.get("source_row_hash")) or not _hash(task.get("question_sha256"))
            or data.question_fingerprint(task["prompt"]) != task["question_sha256"]
            or type(task.get("reference_code")) is not str):
        raise ValueError("Task source identity or question fingerprint is invalid")
    compiled = task.get("compiled")
    assertions._compiled_checks(compiled)
    if (compiled["entry_point"] != public["entry_point"]
            or compiled["public_interface"] != public["public_interface"]):
        raise ValueError("Private compiled entry/interface differs from public task")
    return {"task_id": task["task_id"], "split": task["split"],
            "source_row_hash": task["source_row_hash"], "question_sha256": task["question_sha256"],
            "public_task_hash": digest(public), "compiled_hash": digest(compiled),
            "reference_code_hash": text_hash(task["reference_code"]), "runner_sha256": executor.RUNNER_SHA256}


def messages(task, skill_text):
    """Shared value-free execution contract; raw Skill bytes are not rewritten."""
    if type(skill_text) is not str:
        raise ValueError("Skill must be exact text, including empty No-Skill")
    contract = (
        "Implement the requested Python pure function. Return exactly one Python fenced code block "
        "containing the complete Python source; do not wrap the code in JSON or include explanations. Define the declared entry point "
        "and any needed helper functions. Each invocation starts from a fresh module environment. "
        "Input arguments and return values preserve native Python types. Exact-value comparisons require "
        "returned results representable as exact builtins: None, bool, "
        "int (at most 1024 bits), float, str, list, tuple, set, or dict of supported values. "
        "Truth-value checks use the Boolean value of the returned result inside the isolated execution environment. "
        "Classes, asynchronous code, decorators, private/dunder attributes, introspection, dynamic execution, "
        "filesystem, network and process access are unsupported. Candidate print output is discarded. "
        "Execution is bounded to 5 CPU seconds, 12 wall seconds and monitored 384 MiB RSS for all tests. "
        "Do not rely on cross-invocation global or mutable-default state. Tests and reference solutions are withheld.\n"
        "Available builtin names: " + ", ".join(executor.AVAILABLE_BUILTINS) + ".\n"
        "Allowlisted imported modules and members: "
        + json.dumps(executor.IMPORT_MEMBERS, sort_keys=True) + "."
    )
    if skill_text:
        contract += "\n\nFrozen source-domain Skill (apply only when relevant):\"\"\"\n" + skill_text + "\n\"\"\""
    user = json.dumps(data.public_task(task), sort_keys=True, ensure_ascii=False)
    return contract, user


def _execution_score(task, code, execution):
    """Bind an actual executor receipt before independently scoring its rows."""
    if (type(execution) is not dict or execution.get("version") != executor.VERSION
            or execution.get("runner_sha256") != executor.RUNNER_SHA256
            or execution.get("code_hash") != text_hash(code)):
        raise ValueError("Executor receipt differs from the intended runner or original artifact")
    status = execution.get("status")
    if status not in {"completed", "candidate_rejected", "infrastructure_unknown", "unsupported_output"}:
        raise ValueError("Unknown executor outcome category")
    if status != "candidate_rejected":
        expected_payload = executor._payload(code, task["entry_point"], task["compiled"]["cases"])
        if execution.get("payload_hash") != hashlib.sha256(
                json.dumps(expected_payload, sort_keys=True).encode()).hexdigest():
            raise ValueError("Executor payload differs from the frozen invocation")
    else:
        try:
            executor.validate_code(code)
            executor._payload(code, task["entry_point"], task["compiled"]["cases"])
        except (ValueError, TypeError, SyntaxError, RecursionError):
            pass
        else:
            raise ValueError("Executor claimed a contract rejection for a valid static invocation")
    if status == "completed":
        try:
            score = assertions.evaluate_observations(task["compiled"], execution.get("observations"))
        except assertions.ObservationUnavailable:
            return {"hard": None, "soft": None, "category": "unsupported_output", "score": None}
        return {"hard": int(score["passed"]), "soft": score["passed_count"] / score["total"],
                "category": "passed" if score["passed"] else "assertion_failure", "score": score}
    if status == "candidate_rejected":
        return {"hard": 0, "soft": 0.0, "category": "candidate_contract_violation", "score": None}
    return {"hard": None, "soft": None, "category": status, "score": None}


def _run_once(root, identifier, task, code, identity, *, completed=False):
    """Persist admission before execution; an unresolved admission is not replayed."""
    root = Path(root)
    intent_path = root / "execution_intents" / (identifier + ".json")
    receipt_path = root / "executions" / (identifier + ".json")
    intent_value = {"version": VERSION + "-intent", "identity": identity,
                    "code_hash": text_hash(code), "compiled_hash": digest(task["compiled"]),
                    "runner_sha256": executor.RUNNER_SHA256}
    intent = seal(intent_value)
    if receipt_path.exists():
        _save(intent_path, intent_value, completed=True)
        receipt = _read(receipt_path)
        if receipt.get("intent_hash") != intent["record_hash"]:
            raise ValueError("Execution receipt belongs to another admitted invocation")
        execution = receipt.get("execution")
        _save(receipt_path, {"version": VERSION + "-executor-receipt",
                            "intent_hash": intent["record_hash"], "execution": execution}, completed=True)
    else:
        if completed:
            raise ValueError("Completed run missing executor receipt; execution is forbidden")
        if intent_path.exists():
            raise ValueError("Unresolved execution admission; never silently rerun candidate/reference")
        _save(intent_path, intent_value)
        execution = executor.run_cases(code, task["entry_point"], task["compiled"]["cases"])
        _save(receipt_path, {"version": VERSION + "-executor-receipt",
                            "intent_hash": intent["record_hash"], "execution": execution})
    _execution_score(task, code, execution)
    return execution


def reference(task, root, *, completed=False):
    """Calibrate one frozen host-only reference once, replay scores without child."""
    identity = _task_identity(task)
    path = Path(root) / "references" / f"{task['split']}_{task['task_id']}.json"
    cached = _read(path) if path.exists() else None
    if cached is None and completed:
        raise ValueError("Completed run missing reference calibration")
    identifier = digest({"role": "reference", "task": identity})
    execution = _run_once(root, identifier, task, task["reference_code"], identity,
                          completed=completed or cached is not None)
    score = _execution_score(task, task["reference_code"], execution)
    value = {"version": VERSION + "-reference", "identity": identity, "identity_hash": digest(identity),
             "execution_id": identifier, "execution": execution, "score": score,
             "oracle_valid": score["hard"] == 1, "reference_never_sent_to_model": True}
    return _save(path, value, completed=completed)


def _reference_binding(task, root, record):
    checked = verify(record)
    path = Path(root) / "references" / f"{task['split']}_{task['task_id']}.json"
    if _read(path) != checked:
        raise ValueError("Reference record differs from its actual calibration cache")
    expected = reference(task, root, completed=True)
    if expected != checked:
        raise ValueError("Reference evidence does not bind this exact task")
    return checked


def _raw_receipt(root, request, *, api=None, completed=False):
    identifier = digest(request)
    path = Path(root) / "api/calls" / (identifier + ".json")
    if path.exists():
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Malformed actual API receipt") from error
    else:
        if completed or api is None:
            raise ValueError("Missing actual API receipt; completed replay cannot call API")
        receipt = api.call(request["system"], request["user"], request["kind"], request["key"],
                           max_tokens=request["max_tokens"], repeat=request["repeat"])
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("API call lacks its actual immutable receipt") from error
        if actual != receipt:
            raise ValueError("API response differs from the on-disk transport receipt")
    if (type(receipt) is not dict or receipt.get("request") != request
            or receipt.get("request_hash") != identifier or type(receipt.get("ok")) is not bool
            or type(receipt.get("response")) is not str):
        raise ValueError("API receipt differs from the intended public-only request")
    return receipt


def solve(api, task, skill_text, split, root, protocol_hash, reference_record, *, completed=False):
    """One API draw and at most one isolated execution; no test feedback/revision."""
    identity = _task_identity(task)
    if split != task["split"] or not _hash(protocol_hash):
        raise ValueError("Explicit split/protocol must match the frozen task")
    if api.model != "glm-5.3" or type(api.service) is not dict:
        raise ValueError("This experiment requires the frozen glm-5.3 service")
    calibration = _reference_binding(task, root, reference_record)
    system, user = messages(task, skill_text)
    skill_hash = text_hash(skill_text)
    key = digest({"protocol_hash": protocol_hash, "split": split,
                  "task_id": task["task_id"], "skill_hash": skill_hash})
    request = {"model": api.model, "service": api.service, "system": system, "user": user,
               "kind": KIND, "key": key, "max_tokens": TOKENS, "repeat": 0}
    request_hash = digest(request)
    path = Path(root) / "solves" / (request_hash + ".json")
    cached = _read(path) if path.exists() else None
    if cached is None and completed:
        raise ValueError("Completed run missing immutable solver observation")
    receipt = _raw_receipt(root, request, api=api, completed=completed or cached is not None)
    artifact, execution, execution_id, score = None, None, None, None
    if not receipt["ok"]:
        hard, soft, category = None, None, "api_unknown"
    else:
        try:
            artifact = extract_artifact(receipt["response"])
        except (RecursionError, ValueError):
            artifact = {"ok": False, "code": None, "syntax_ok": False,
                        "error_category": "artifact_parse_bound", "raw_sha256": text_hash(receipt["response"])}
        if not calibration["oracle_valid"]:
            hard, soft, category = None, None, "reference_unavailable"
        elif not artifact["ok"] or not artifact["syntax_ok"]:
            hard, soft, category = 0, 0.0, "artifact_contract_violation"
        else:
            code = artifact["code"]
            execution_identity = {"role": "candidate", "protocol_hash": protocol_hash,
                "request_hash": request_hash, "api_receipt_hash": digest(receipt),
                "reference_record_hash": calibration["record_hash"], "task": identity}
            execution_id = digest(execution_identity)
            execution = _run_once(root, execution_id, task, code, execution_identity,
                                  completed=completed or cached is not None)
            score = _execution_score(task, code, execution)
            hard, soft, category = score["hard"], score["soft"], score["category"]
    value = {"version": VERSION + "-solve", "task_id": str(task["task_id"]),
        "cluster_id": task["question_sha256"], "split": split, "skill_hash": skill_hash,
        "request_hash": request_hash, "api_receipt_hash": digest(receipt),
        "response_hash": text_hash(receipt["response"]), "protocol_hash": protocol_hash,
        "task_identity_hash": digest(identity), "compiled_hash": digest(task["compiled"]),
        "runner_sha256": executor.RUNNER_SHA256, "reference_record_hash": calibration["record_hash"],
        "api_ok": receipt["ok"], "hard": hard, "soft": soft, "outcome_category": category,
        "artifact": artifact, "execution_id": execution_id, "execution": execution, "score": score,
        "hidden_feedback_to_model": False, "semantic_resampling": False}
    return _save(path, value, completed=completed)
