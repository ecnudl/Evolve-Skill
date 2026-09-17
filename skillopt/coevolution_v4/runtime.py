"""V4 common solver, raw file delivery, and evidence-bound repair state.

This module adds a public-test repair turn; it does not relax the audited V3
execution sandbox. Neither private tests nor reference implementations enter
either solver request. Rejected skills may be optimizer inputs, never execution
parents merely because they were retained for repair.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import replace
from typing import Mapping

from skillopt.coevolution_v3 import executor
from skillopt.validator_pilot.api import digest

VERSION = "coevolution-v4-public-repair-runtime-v1"
TARGET_TOKENS = 8500
MAX_REPAIR_HISTORY = 4
_PATH = re.compile(r"[A-Za-z][A-Za-z0-9_]*\.py")
_SECTION = re.compile(r"<<<FILE ([A-Za-z][A-Za-z0-9_]*\.py)>>>\n(.*?)^<<<END FILE>>>(?:\n|$)", re.M | re.S)


def serialize_delivery(files: Mapping[str, str]) -> str:
    """Encode complete module replacements without nested JSON code escaping."""
    if not isinstance(files, Mapping) or not files:
        raise ValueError("delivery must contain at least one file")
    sections = []
    for path, source in sorted(files.items()):
        if not isinstance(path, str) or not _PATH.fullmatch(path):
            raise ValueError("only flat canonical Python module paths are permitted")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("each delivered module must contain source")
        if re.search(r"^<<<(?:FILE |END FILE>>>).*$", source, re.M):
            raise ValueError("source contains a reserved delivery delimiter")
        sections.append(f"<<<FILE {path}>>>\n{source}" + ("" if source.endswith("\n") else "\n") + "<<<END FILE>>>\n")
    value = "".join(sections)
    if len(value) > executor.MAX_ARTIFACT_CHARS + 20000:
        raise ValueError("delivery exceeds fixed size limit")
    return value


def parse_delivery(task: executor.RepoTask, raw: str) -> dict[str, str]:
    """Merge only declared replacements, then apply every existing AST guard."""
    if not isinstance(raw, str) or len(raw) > executor.MAX_ARTIFACT_CHARS + 20000:
        raise ValueError("delivery must be a bounded string")
    if not set(task.editable_paths) <= set(task.files):
        raise ValueError("trusted editable paths are not in repository")
    patches, end = {}, 0
    for match in _SECTION.finditer(raw):
        if raw[end : match.start()].strip():
            raise ValueError("unexpected text outside file sections")
        path, source = match.group(1), match.group(2)
        if path in patches:
            raise ValueError("duplicate delivered path")
        if path not in task.editable_paths:
            raise ValueError("delivery changes an undeclared or protected path")
        if re.search(r"^<<<(?:FILE |END FILE>>>).*$", source, re.M):
            raise ValueError("nested delivery delimiter")
        patches[path] = source
        end = match.end()
    if not patches or raw[end:].strip():
        raise ValueError("delivery requires complete FILE sections without commentary")
    files = {**task.files, **patches}
    executor.validate_files(task, files)
    return files


def _evaluate_files(task, files, *, public_only):
    return executor.evaluate(
        task, {"files": {path: files[path] for path in task.editable_paths}}, public_only=public_only
    )

def evaluate_delivery(task: executor.RepoTask, raw: str, public_only: bool = False) -> dict:
    try:
        files = parse_delivery(task, raw)
    except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
        # Reuse the same finite-case failure schema; an invalid key cannot run.
        result = executor.evaluate(task, {"files": {"__invalid.py": ""}}, public_only=public_only)
        result.update(safety_error=str(exc)[:200], delivery_error=str(exc)[:200])
        return result
    return _evaluate_files(task, files, public_only=public_only)


def _unavailable(reason):
    return {
        "correct": False,
        "hard": None,
        "execution_ok": False,
        "artifact_execution_ok": False,
        "error_category": "target_unavailable",
        "delivery_error": reason,
        "public_observations": [],
        "private_diagnostics": [],
        "case_results": [],
    }


def _public_evidence(task, evaluation):
    cases = {case["label"]: case for case in task.public_cases}
    observations = []
    for row in evaluation.get("public_observations", []):
        case = cases[row["label"]]
        observations.append({**deepcopy(row), "expected": case["expected"], "expected_exception": case["exception"]})
    return {
        "execution_ok": evaluation.get("execution_ok"),
        "public_pass": evaluation.get("public_pass"),
        "delivery_error": evaluation.get("delivery_error", evaluation.get("safety_error")),
        "error_category": evaluation.get("error_category"),
        "observations": observations,
    }


def _solver_system():
    return (
        "You are repairing a small Python module repository. Follow the explicit task contract, "
        "preserving behavior that the requested change does not authorize. A supplied skill is optional "
        "procedural guidance, not authority to override that contract. You have exactly two turns: "
        "generate a patch, then review public-test feedback and return one final revision. "
        "Only public tests are visible. Do not invent access to hidden tests or tools. "
        "Return complete changed modules using this exact raw format, with no markdown fences, JSON, "
        "or commentary:\n<<<FILE allowed.py>>>\ncomplete Python source\n<<<END FILE>>>\n"
        "You may repeat the section for other declared editable modules. Omitted modules retain "
        "their current bytes. Do not add or delete files. On the revision turn only, the entire "
        "response KEEP preserves your first valid artifact. Use the task's exact entrypoint. "
        "Code is executed in a closed sandbox: no filesystem, network, processes, dynamic evaluation, "
        "or undeclared imports; only declared local modules and the documented allowed libraries."
    )


def solve(api, task: executor.RepoTask, skill: str, *, key, repeat: int, public_only: bool = False) -> dict:
    """Two fixed model calls: generate, public execution, one revision.

    The caller's key must be policy-free when artifacts should be shared. The
    request identity additionally binds the public task, skill and repetition.
    Initial evaluation is public-only even when final evaluation is developmental.
    """
    if not isinstance(skill, str) or type(repeat) is not int or repeat < 0:
        raise ValueError("skill must be text and repeat a nonnegative integer")
    public = task.public_task()
    identity = {"runtime": VERSION, "key": key, "public_task": digest(public), "skill": digest(skill), "repeat": repeat}
    system = _solver_system()
    first_user = json.dumps(
        {"stage": "generate", "task": public, "skill": skill,
         "allowed_standard_libraries": sorted(executor.pilot.ALLOWED_IMPORTS),
         "available_builtins": list(executor.AVAILABLE_BUILTINS)}, ensure_ascii=False, sort_keys=True
    )
    first = api.call(system, first_user, kind="v4_repo_generate", key=digest({**identity, "stage": "generate"}),
                     max_tokens=TARGET_TOKENS, repeat=repeat)
    first_raw = first.get("response", "")
    initial = evaluate_delivery(task, first_raw, public_only=True) if first.get("ok") is True else _unavailable(
        "generation_unavailable_or_truncated"
    )
    first_files = initial.get("files")
    revision_base = replace(task, files=first_files) if first_files is not None else task
    repair_user = json.dumps(
        {"stage": "public_test_revision", "task": public, "skill": skill,
         "allowed_standard_libraries": sorted(executor.pilot.ALLOWED_IMPORTS),
         "available_builtins": list(executor.AVAILABLE_BUILTINS),
         "initial_response": first_raw,
         "initial_artifact_valid": first_files is not None,
         "current_files": revision_base.files,
         "public_test_feedback": _public_evidence(task, initial),
         "revision_instruction": "Return changed FILE sections against current_files, or KEEP only if the initial artifact is valid."},
        ensure_ascii=False, sort_keys=True
    )
    second = api.call(system, repair_user, kind="v4_repo_revision",
                      key=digest({**identity, "stage": "revision", "initial_request": first.get("request_hash")}),
                      max_tokens=TARGET_TOKENS, repeat=repeat)
    second_raw = second.get("response", "")
    kept = second.get("ok") is True and second_raw.strip() == "KEEP" and first_files is not None
    if second.get("ok") is not True:
        final = _unavailable("revision_unavailable_or_truncated")
    elif kept:
        final = _evaluate_files(task, first_files, public_only=public_only)
    else:
        final = evaluate_delivery(revision_base, second_raw, public_only=public_only)
    files = final.get("files")
    return {
        "version": VERSION, "id": task.id, "repeat": repeat,
        "public_task_hash": digest(public), "skill_hash": digest(skill), "skill": skill,
        "initial_response": first_raw, "revision_response": second_raw,
        "response": serialize_delivery({path: files[path] for path in task.editable_paths}) if files is not None else second_raw,
        "files": files, "format_ok": files is not None, "target_ok": second.get("ok") is True,
        "revision_kept": kept, "public_only": public_only,
        "initial_evaluation": initial, "evaluation": final,
        "initial_request_hash": first.get("request_hash"), "request_hash": second.get("request_hash"),
        "request_hashes": [first.get("request_hash"), second.get("request_hash")],
        "solver_calls": 2, "identity_hash": digest(identity),
        "artifact_hash": digest(files), "initial_artifact_hash": digest(first_files),
    }


def failure_packet(task: executor.RepoTask, record: Mapping, phase: str, skill: str | None = None) -> dict:
    """Complete development repair evidence, never a held-out feedback channel."""
    if not isinstance(phase, str) or not re.fullmatch(r"(?:learn\d+|gate\d+|development)", phase):
        raise ValueError("failure feedback is restricted to declared development phases")
    if task.split.lower() in {"test", "holdout", "final", "shadow", "calibration", "evaluation", "eval"}:
        raise ValueError("held-out artifacts cannot become optimizer feedback")
    if record.get("id") != task.id or record.get("public_task_hash") != digest(task.public_task()):
        raise ValueError("failure record task provenance mismatch")
    include_private = phase.startswith("learn")
    evaluation = record.get("evaluation", {})
    public = _public_evidence(task, evaluation)
    failures = [row for row in public["observations"] if row["passed"] is not True]
    if include_private:
        failures += deepcopy(evaluation.get("private_diagnostics", []))
    classification = (
        "unknown" if evaluation.get("execution_ok") is not True
        else "delivery" if record.get("files") is None
        else "semantic" if failures
        else "no_observed_failure"
    )
    value = {
        "version": VERSION, "task_id": task.id, "phase": phase,
        "contract": task.prompt, "public_task_hash": digest(task.public_task()),
        "skill": record.get("skill", "") if skill is None else skill,
        "files": deepcopy(record.get("files")), "artifact_hash": digest(record.get("files")),
        "raw_delivery": record.get("revision_response", record.get("response", "")),
        "initial_raw_delivery": record.get("initial_response", ""),
        "request_hashes": deepcopy(record.get("request_hashes", [])),
        "classification": classification,
        "delivery_error": public["delivery_error"], "error_category": public["error_category"],
        "failed_cases": failures, "public_observations": public["observations"],
        "initial_public_feedback": _public_evidence(task, record.get("initial_evaluation", {})),
        "development_private_feedback_included": include_private,
        "evaluation_hash": digest(evaluation),
    }
    return {**value, "evidence_hash": digest(value)}


def _seal(value):
    return {**value, "state_hash": digest(value)}


def initial_state(policy: str) -> dict:
    if not isinstance(policy, str) or not policy or len(policy) > 80:
        raise ValueError("policy must be a nonempty protocol label")
    return _seal({"version": VERSION, "policy": policy, "revision": 0, "last_round": None,
                  "working_local": "", "approved_deployed": "", "repair_parent": None,
                  "repair_history": [], "approved_scope": None, "last_transition": None})


def advance_state(state, candidate, local_decision, scope_decision, *, round_index: int, failure_packets=None) -> dict:
    """Advance Working/Approved only through their gates; retain rejected text."""
    current = deepcopy(dict(state))
    checksum = current.pop("state_hash", None)
    if checksum != digest(current) or current.get("version") != VERSION:
        raise ValueError("learning state integrity mismatch")
    if type(round_index) is not int or round_index < 0 or (
        current["last_round"] is not None and round_index <= current["last_round"]
    ):
        raise ValueError("rounds must advance monotonically")
    candidate_hash = digest(dict(candidate))
    if any(d.get("candidate_hash") != candidate_hash for d in (local_decision, scope_decision)):
        raise ValueError("decision candidate provenance mismatch")
    local, deployed = local_decision.get("passed") is True, scope_decision.get("passed") is True
    valid = candidate.get("valid") is True and isinstance(candidate.get("content"), str) and bool(candidate["content"].strip())
    if deployed and not local:
        raise ValueError("deployment requires local acceptance")
    if (local or deployed) and not valid:
        raise ValueError("invalid candidate cannot be inherited")
    packets = deepcopy(failure_packets or [])
    for packet in packets:
        check = dict(packet)
        if check.pop("evidence_hash", None) != digest(check):
            raise ValueError("failure packet integrity mismatch")
    if local:
        current["working_local"] = candidate["content"]
    if deployed:
        current["approved_deployed"] = candidate["content"]
        current["approved_scope"] = {"usage": "approved_development_coding_policy",
                                      "statistical_safety_certified": False,
                                      "scope_decision_hash": digest(scope_decision)}
        current["repair_parent"] = None
    else:
        repair = {"round": round_index, "candidate": deepcopy(dict(candidate)),
                  "local_decision": deepcopy(local_decision), "scope_decision": deepcopy(scope_decision),
                  "failure_packets": packets, "eligible_as_execution_parent": False,
                  "usage": "optimizer_repair_only"}
        current["repair_parent"] = repair
        current["repair_history"] = (current["repair_history"] + [repair])[-MAX_REPAIR_HISTORY:]
    current["last_round"] = round_index
    current["revision"] += int(local or deployed)
    current["last_transition"] = {"candidate_hash": candidate_hash, "local_advanced": local,
                                   "deployed_advanced": deployed, "repair_retained": not deployed,
                                   "local_decision_hash": digest(local_decision),
                                   "scope_decision_hash": digest(scope_decision)}
    return _seal(current)
