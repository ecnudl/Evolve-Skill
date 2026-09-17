"""Phase-explicit, history-independent V18 SearchQA/MBPP execution receipts.

Native V9 QA messages/scoring and V11 Coding messages/sandbox/scoring remain
unchanged. There is one solver draw per task/text/history, without test feedback.
Only development_feedback may project host evaluation facts for learning.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v9 import data as qa_data
from skillopt.coevolution_v9 import learning as qa
from skillopt.coevolution_v11 import assertions, executor
from skillopt.coevolution_v11 import data as code_data
from skillopt.coevolution_v11 import execution as code
from skillopt.validator_artifact_sensitivity import extract_artifact
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v18-explicit-phase-history-runtime-v1"
TOKENS = 4096
PHASES = {"development", "confirmation", "final"}
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_LOCK_GUARD = threading.Lock()
_LOCKS = {}


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def _lock(key):
    with _LOCK_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _path(path):
    path = Path(path).absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Evidence paths must be nonsymlink, traversal-free local paths")
    return path


def _read(path):
    path = _path(path)
    try:
        return verify(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Missing or malformed sealed runtime evidence") from error


def _save(path, value, *, completed=False):
    path, expected = _path(path), seal(value)
    if path.exists():
        if _read(path) != expected:
            raise ValueError("Runtime evidence differs from recomputed closed provenance")
    elif completed:
        raise ValueError("Completed runtime dependency is missing; never reconstruct")
    else:
        write_immutable_json(path, expected)
    return expected


def _task_identity(task):
    if (type(task) is not dict or task.get("domain") not in {"searchqa", "coding"}
            or task.get("phase") not in PHASES or type(task.get("id")) is not str or not task["id"]
            or not _hash(task.get("cluster_id"))
            or ("split" in task and task["split"] != task["phase"])):
        raise ValueError("Explicit domain, phase, ID and question-hash cluster are required")
    try:
        json.dumps(task, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Task must contain only finite JSON host data") from error
    if task["domain"] == "coding":
        public = code_data.public_task(task)
        if (not _hash(task.get("source_row_hash")) or not _hash(task.get("question_sha256"))
                or task["id"] != str(task["task_id"])
                or task["cluster_id"] != task["question_sha256"]
                or code_data.question_fingerprint(task["prompt"]) != task["question_sha256"]
                or type(task.get("reference_code")) is not str
                or task.get("source_split") != code_data.source_split(task["task_id"])):
            raise ValueError("Coding host identity differs from its native source")
        assertions._compiled_checks(task.get("compiled"))
        compiled = task["compiled"]
        if (compiled["entry_point"] != public["entry_point"]
                or compiled["public_interface"] != public["public_interface"]):
            raise ValueError("Compiled Coding interface differs from public projection")
        allowed_source = {"test"} if task["phase"] == "final" else {"train", "validation"}
        if task["source_split"] not in allowed_source:
            raise ValueError("Coding development/confirmation and final source splits cannot be relabeled")
    else:
        item = task.get("item")
        public = qa_data.public_task(item)
        if (task["cluster_id"] != qa_data.question_fingerprint(item["question"])
                or task["id"] != item["key"]
                or type(item.get("answers")) is not list or not item["answers"]
                or any(type(answer) is not str for answer in item["answers"])):
            raise ValueError("SearchQA identity/gold schema differs from native source")
        expected = "train" if task["phase"] == "development" else "validation"
        if task.get("source_split") != expected:
            raise ValueError("SearchQA phase must retain its actual source partition")
    return {"version": VERSION, "task_id": task["id"], "domain": task["domain"],
            "phase": task["phase"], "source_split": task["source_split"],
            "cluster_id": task["cluster_id"], "task_hash": digest(task),
            "public_task_hash": digest(public)}


def messages(task, skill):
    _task_identity(task)
    if type(skill) is not str:
        raise ValueError("Skill must be exact text, including empty No-Skill")
    return (code.messages(task, skill) if task["domain"] == "coding" else
            qa.native_qa_messages(skill, qa_data.public_task(task["item"])))


def _native_once(directory, identifier, task, source, identity, completed):
    for folder in ("execution_intents", "executions"):
        _path(directory / folder / (identifier + ".json"))
    return code._run_once(directory, identifier, task, source, identity, completed=completed)


def reference(task, root, *, completed=False):
    """Calibrate Coding references only in the existing OS executor, once/task.

    Task phases stay development/confirmation/final; no compatibility relabel.
    An invalid reference is retained as unavailable, not replaced or discarded.
    The source contains no model-visible reference code or tests.
    """
    identity = _task_identity(task)
    if task["domain"] != "coding" or type(completed) is not bool:
        raise ValueError("Reference calibration requires an actual Coding task")
    directory = _path(root) / "runtime"
    identity = {**identity, "role": "reference", "compiled_hash": digest(task["compiled"]),
                "reference_code_hash": text_hash(task["reference_code"]),
                "runner_sha256": executor.RUNNER_SHA256}
    identifier = digest(identity)
    path = directory / "references" / (identifier + ".json")
    with _lock((str(directory), "reference", identifier)):
        replay = completed or path.exists()
        execution = _native_once(directory, identifier, task, task["reference_code"], identity, replay)
        score = code._execution_score(task, task["reference_code"], execution)
        return _save(path, {"version": VERSION + "-reference", "identity": identity,
            "execution_id": identifier, "execution": execution, "score": score,
            "oracle_valid": score["hard"] == 1, "reference_never_sent_to_model": True}, completed=completed)


def _api_receipt(api, root, request, identity, completed):
    identifier = digest(request)
    path = _path(root / "api/calls" / (identifier + ".json"))
    intent_path = root / "runtime/api_intents" / (identifier + ".json")
    intent = {"version": VERSION + "-api-intent", "identity_hash": digest(identity),
              "request_hash": identifier, "phase": identity["phase"], "history": identity["history"]}
    if path.exists():
        _save(intent_path, intent, completed=True)
        receipt = json.loads(path.read_text(encoding="utf-8"))
    else:
        if completed or getattr(api, "offline", False) or intent_path.exists():
            raise ValueError("Missing/unresolved API receipt; never silently send another request")
        _save(intent_path, intent)
        receipt = api.call(request["system"], request["user"], request["kind"], request["key"],
                           max_tokens=request["max_tokens"], repeat=request["repeat"])
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != receipt:
            raise ValueError("API response lacks its actual durable transport receipt")
    if (type(receipt) is not dict or receipt.get("request") != request
            or receipt.get("request_hash") != identifier or type(receipt.get("ok")) is not bool
            or type(receipt.get("response")) is not str
            or type(receipt.get("http_attempt_count")) is not int
            or not 1 <= receipt["http_attempt_count"] <= 3
            or (receipt["ok"] and (receipt.get("finish_reason") != "stop"
                                   or receipt.get("stream_complete", True) is not True))):
        raise ValueError("Actual API receipt differs from the closed complete request")
    return receipt


def solve(api, task, skill, history, root, protocol_hash, completed=False):
    """One immutable draw per complete task/text/history/protocol identity.

    Cross-history requests have different keys AND repeat=history. Exact aliases
    within one history reuse the same observation. completed=True reads every
    actual dependency, recomputes all scores and forbids API/child execution.
    An admitted request with no receipt is never resent. Closed lower-level
    receipts may reconstruct a missing solve only when completed=False.
    """
    root, task_identity = _path(root), _task_identity(task)
    if (type(skill) is not str or type(history) is not int or history < 0
            or not _hash(protocol_hash) or type(completed) is not bool
            or api.model != "glm-5.3" or type(api.service) is not dict):
        raise ValueError("Exact Skill/history/protocol and frozen glm-5.3 service required")
    if hasattr(api, "root") and _path(api.root) != root / "api":
        raise ValueError("Actual API ledger must be this run's api directory")
    identity = {**task_identity, "history": history, "protocol_hash": protocol_hash,
                "skill_hash": text_hash(skill), "service_hash": digest(api.service), "model": api.model}
    system, user = messages(task, skill)
    request = {"model": api.model, "service": api.service, "system": system, "user": user,
               "kind": "v18_" + task["domain"] + "_solve", "key": digest(identity),
               "max_tokens": TOKENS, "repeat": history}
    identifier = digest(request)
    path = root / "runtime/solves" / (identifier + ".json")
    with _lock((str(root), "solve", identifier)):
        replay = completed or path.exists()
        calibrated = reference(task, root, completed=replay) if task["domain"] == "coding" else None
        receipt = _api_receipt(api, root, request, identity, replay)
        artifact = execution = execution_id = native_score = None
        if not receipt["ok"]:
            hard, soft, category = None, None, "api_unknown"
        elif task["domain"] == "searchqa":
            native_score = qa.score_qa(receipt["response"], task["item"])
            hard, soft = native_score["hard"], native_score["soft"]
            category = "passed" if hard else "answer_mismatch"
            artifact = {"answer": native_score["predicted_answer"]}
        else:
            try:
                artifact = extract_artifact(receipt["response"])
            except (ValueError, RecursionError):
                artifact = {"ok": False, "syntax_ok": False, "code": None,
                            "error_category": "artifact_parse_bound"}
            if not calibrated["oracle_valid"]:
                hard, soft, category = None, None, "reference_unavailable"
            elif not artifact["ok"] or not artifact["syntax_ok"]:
                hard, soft, category = 0, 0.0, "artifact_contract_violation"
            else:
                native_identity = {"role": "candidate", "identity": identity, "request_hash": identifier,
                    "api_receipt_hash": digest(receipt), "reference_record_hash": calibrated["record_hash"]}
                execution_id = digest(native_identity)
                execution = _native_once(root / "runtime", execution_id, task, artifact["code"],
                                         native_identity, replay)
                native_score = code._execution_score(task, artifact["code"], execution)
                hard, soft, category = native_score["hard"], native_score["soft"], native_score["category"]
        row = {"version": VERSION, "identity": identity, "task_id": task["id"],
            "task_hash": task_identity["task_hash"], "phase": task["phase"], "domain": task["domain"],
            "history": history, "cluster_id": task["cluster_id"], "skill_hash": identity["skill_hash"],
            "protocol_hash": protocol_hash, "request_hash": identifier, "api_receipt_hash": digest(receipt),
            "api_ok": receipt["ok"], "raw_response": receipt["response"],
            "hard": hard, "soft": soft, "category": category, "outcome_category": category,
            "artifact": artifact, "execution": execution, "execution_id": execution_id,
            "native_score": native_score, "reference_record": calibrated,
            "reference_execution_id": calibrated["execution_id"] if calibrated else None,
            "execution_ids": ([calibrated["execution_id"]] if calibrated else [])
                             + ([execution_id] if execution_id else []),
            "oracle_available": hard is not None,
            "reference_available": calibrated["oracle_valid"] if calibrated else True,
            "artifact_valid": (None if not receipt["ok"] else True if task["domain"] == "searchqa"
                               else bool(artifact["ok"] and artifact["syntax_ok"])),
            "model_receives_evaluation_feedback": False, "optimizer_feedback_allowed": task["phase"] == "development",
            "semantic_resampling": False, "request_repeat": history}
        return _save(path, row, completed=completed)


def _closed_binding(task, row, root):
    """Bind learning inputs to every already-durable solve dependency."""
    root = _path(root)
    if _read(root / "runtime/solves" / (row["request_hash"] + ".json")) != row:
        raise ValueError("Feedback solve differs from its actual on-disk runtime receipt")
    path = _path(root / "api/calls" / (row["request_hash"] + ".json"))
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("Feedback requires the closed actual API receipt") from error
    request = receipt.get("request", {})
    identity = row["identity"]
    if (digest(receipt) != row["api_receipt_hash"] or digest(request) != row["request_hash"]
            or receipt.get("request_hash") != row["request_hash"]
            or receipt.get("response") != row["raw_response"] or receipt.get("ok") != row["api_ok"]
            or request.get("key") != digest(identity) or request.get("repeat") != row["history"]
            or request.get("max_tokens") != TOKENS or request.get("model") != "glm-5.3"
            or digest(request.get("service")) != identity["service_hash"]
            or request.get("kind") != "v18_" + task["domain"] + "_solve"
            or request.get("user") != messages(task, "")[1]):
        raise ValueError("Feedback API response/provenance does not match the actual public request")
    intent = {"version": VERSION + "-api-intent", "identity_hash": digest(identity),
              "request_hash": row["request_hash"], "phase": identity["phase"], "history": identity["history"]}
    _save(root / "runtime/api_intents" / (row["request_hash"] + ".json"), intent, completed=True)
    if task["domain"] == "coding":
        calibrated = reference(task, root, completed=True)
        if calibrated != row["reference_record"]:
            raise ValueError("Feedback reference differs from its actual native calibration")
        if row["execution_id"] is not None:
            native_identity = {"role": "candidate", "identity": identity, "request_hash": row["request_hash"],
                "api_receipt_hash": row["api_receipt_hash"], "reference_record_hash": calibrated["record_hash"]}
            if digest(native_identity) != row["execution_id"]:
                raise ValueError("Feedback native execution identity differs")
            execution = _native_once(root / "runtime", row["execution_id"], task, row["artifact"]["code"],
                                     native_identity, True)
            if execution != row["execution"]:
                raise ValueError("Feedback observations differ from actual native execution")


def development_feedback(task, row, root):
    """Recompute a sealed solve's development feedback; NEVER expose reference.

    This read-only projection closes actual on-disk API/execution dependencies,
    rebinds the full task identity and re-scores native observations;
    callers cannot insert an arbitrary score or relabel final as development.
    Executed development input/check/observation tuples may reach the updater.
    QA gold answers are learning labels ONLY for actual development tasks.
    """
    identity, row = _task_identity(task), verify(row)
    if task["phase"] != "development" or row.get("phase") != "development":
        raise ValueError("Only genuine development observations can become learning feedback")
    if (row.get("version") != VERSION or row.get("optimizer_feedback_allowed") is not True
            or any(row["identity"].get(key) != value for key, value in identity.items())
            or row.get("task_hash") != digest(task) or row.get("task_id") != task["id"]
            or row.get("domain") != task["domain"] or row.get("cluster_id") != task["cluster_id"]
            or row.get("skill_hash") != row["identity"].get("skill_hash")
            or row.get("history") != row["identity"].get("history")
            or not _hash(row.get("request_hash")) or not _hash(row.get("api_receipt_hash"))
            or type(row.get("api_ok")) is not bool or type(row.get("raw_response")) is not str):
        raise ValueError("Development feedback does not bind an actual sealed task/history/Skill solve")
    _closed_binding(task, row, root)
    if not row["api_ok"]:
        expected = (None, None, "api_unknown")
    elif task["domain"] == "searchqa":
        rescored = qa.score_qa(row["raw_response"], task["item"])
        if row["artifact"] != {"answer": rescored["predicted_answer"]}:
            raise ValueError("QA artifact differs from its actual response")
        expected = (rescored["hard"], rescored["soft"], "passed" if rescored["hard"] else "answer_mismatch")
    else:
        reference_record = verify(row["reference_record"])
        reference_identity = reference_record["identity"]
        if any(reference_identity.get(key) != value for key, value in identity.items()):
            raise ValueError("Reference calibration is from a different task/phase")
        recalibrated = code._execution_score(task, task["reference_code"], reference_record["execution"])
        if reference_record["oracle_valid"] is not (recalibrated["hard"] == 1):
            raise ValueError("Reference availability differs from executed native checks")
        artifact = row["artifact"]
        try:
            reparsed = extract_artifact(row["raw_response"])
        except (ValueError, RecursionError):
            reparsed = {"ok": False, "syntax_ok": False, "code": None,
                        "error_category": "artifact_parse_bound"}
        if reparsed != artifact:
            raise ValueError("Coding artifact differs from its actual response")
        if not reference_record["oracle_valid"]:
            expected = (None, None, "reference_unavailable")
        elif not artifact["ok"] or not artifact["syntax_ok"]:
            expected = (0, 0.0, "artifact_contract_violation")
        else:
            rescored = code._execution_score(task, artifact["code"], row["execution"])
            expected = (rescored["hard"], rescored["soft"], rescored["category"])
    if (row.get("hard"), row.get("soft"), row.get("category")) != expected:
        raise ValueError("Learning feedback score differs from actual native evidence")
    public = (code_data.public_task(task) if task["domain"] == "coding" else
              {"key": task["item"]["key"], "native_user_message": messages(task, "")[1],
               "context_truncated_at_source": qa.rollout._truncate_context(task["item"]["context"])
                                               != task["item"]["context"]})
    feedback = {"version": VERSION + "-development-feedback", "phase": "development",
        "task_id": task["id"], "domain": task["domain"], "history": row["history"],
        "public_task": public, "artifact": deepcopy(row["artifact"]), "raw_response": row["raw_response"],
        "api_ok": row["api_ok"], "hard": row["hard"], "soft": row["soft"], "category": row["category"],
        "provenance": {"solve_hash": row["record_hash"], "task_hash": row["task_hash"],
            "request_hash": row["request_hash"], "api_receipt_hash": row["api_receipt_hash"],
            "skill_hash": row["skill_hash"], "execution_id": row["execution_id"]},
        "reference_code_included": False, "untrusted_task_and_model_data": True}
    if task["domain"] == "searchqa":
        feedback["development_answers"] = deepcopy(task["item"]["answers"])
    elif row["execution"] is not None and row["execution"].get("status") == "completed":
        feedback["executed_native_checks"] = [
            {"input": deepcopy(case), "check": deepcopy(check), "observation": deepcopy(observation)}
            for case, check, observation in zip(task["compiled"]["cases"], task["compiled"]["checks"],
                                                 row["execution"]["observations"])]
    return seal(feedback)
