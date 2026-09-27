"""Replayable observations of already registered public examples, not Research.

This standalone adapter does not alter the solver, infer new tests/expected
states, inspect host audit fields, or authorize learning. Candidate Python runs
only through the existing isolated executor and ExecutionCache. Host records
retain identity bindings; model_view replays receipts before whitelisting data.
Input mutation is an observation, not an error unless an explicit preservation
obligation applies. Arbitrary in-place postconditions are deliberately unknown.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

from .checks import CallableTask, ExecutionCache, _outcome, json_value
from .curriculum_tasks import _is_real_executor
from .models import ArtifactRecord, require, text
from .panel import checked_path
from .public_revision import _parts, _read, _revision_lock, _UnavailableOnException, _write
from .single_round_feedback import _ReceiptReplay
from .views import bind, verifier_view

VERSION = "registered-public-case-observations-v2"
MAX_EXECUTIONS = 16
MAX_MODEL_VIEW_BYTES = 180000
ORIGINS = ["registered_public_example_recovery", "recorded_public_execution"]
_FIELDS = {"version", "request", "task", "public_task", "public_wrapper", "artifact",
           "execution_identity", "execution_records", "cases", "counts", "information_origins",
           "fixture_only", "research_increment", "full_contract_correctness", "shadow_only",
           "learning_authorized", "deployment_authorized", "record_hash"}
_STATE_FIELDS = ("before_args", "after_args", "before_kwargs", "after_kwargs")


def _bound_parts(row, artifact):
    # _parts reads only these three public keys; never enumerate the input row.
    task, public_task, wrapper = _parts(row)
    bind(task.contract, artifact, ())
    if artifact.availability == "available":
        require({f.path for f in artifact.files} == {task.module + ".py", wrapper.path}
                and wrapper in artifact.files, "Artifact source/wrapper differs from the public registration")
    return task, public_task, wrapper


def _request(task, public_task, wrapper, artifact, identity):
    return {"version": VERSION, "task_hash": task.contract.content_hash,
            "callable_task_hash": task.content_hash, "public_task_hash": public_task.content_hash,
            "public_wrapper_hash": wrapper.content_hash, "artifact_record_hash": artifact.content_hash,
            "artifact_hash": artifact.artifact_hash, "execution_identity": identity,
            "implementation_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _conflicting_inputs(task):
    expected = {}
    for case in task.public_cases:
        if case.expected_json is not None or case.expected_exception is not None:
            key = digest(json_value(case.arguments_json))
            value = {"exception": case.expected_exception} if case.expected_exception is not None else {
                "value": json_value(case.expected_json)}
            expected.setdefault(key, set()).add(digest(value))
    return {key for key, values in expected.items() if len(values) > 1}


def _case_result(task, artifact, case, receipt, conflict):
    expected = json_value(case.expected_json) if case.expected_json is not None else None
    public_input = json_value(case.arguments_json)
    execution = receipt["execution"] if receipt else {}
    observed = execution.get("status") == "observed"
    complete = observed and execution.get("cleanup_confirmed") is True
    observation = {"status": execution.get("status", "not_executed"),
                   "actual_is_available": observed and "actual" in execution,
                   "information_origin": "recorded_public_execution" if receipt else "no_execution"}
    if not complete:
        observation["unavailable_reason"] = ("artifact_" + artifact.availability if not receipt else
            "interrupted_no_receipt" if execution.get("reason") == "interrupted_execution_no_receipt" else
            "cleanup_unconfirmed" if observed else "execution_" + execution.get("status", "unknown"))
    if observed:
        require("exception" not in execution or execution["exception"] is None
                or type(execution["exception"]) is str, "Invalid observed exception type")
        for field in ("actual", "exception", *_STATE_FIELDS):
            if field in execution:
                observation[field] = deepcopy(execution[field])
    state_complete = complete and all(field in execution for field in _STATE_FIELDS)
    if state_complete:
        require(type(execution["before_args"]) is list and type(execution["after_args"]) is list
                and type(execution["before_kwargs"]) is dict and type(execution["after_kwargs"]) is dict,
                "Observed input states need args lists and kwargs objects")
        require(digest(execution["before_args"]) == digest(public_input["args"])
                and digest(execution["before_kwargs"]) == digest(public_input["kwargs"]),
                "Observed initial state differs from registered public input")
    changed = (digest([execution["before_args"], execution["before_kwargs"]]) !=
               digest([execution["after_args"], execution["after_kwargs"]])) if state_complete else None

    return_status, return_reason = "unknown", "missing_or_incomplete_execution"
    if artifact.availability != "available":
        return_reason = "artifact_" + artifact.availability
    elif conflict:
        return_reason = "conflicting_registered_public_expectations"
    elif complete and "exception" in execution:
        if case.expected_json is None and case.expected_exception is None:
            return_reason = "no_registered_public_expected_outcome"
        elif (execution["exception"] in {"MemoryError", "TimeoutError"}
              and execution["exception"] != case.expected_exception):
            # Resource exhaustion is not an execution-confirmed wrong answer.
            # Only an explicitly expected matching resource exception uses
            # the public comparison below; observed input state stays separate.
            return_reason = "resource_limited_execution_not_semantic_failure"
        elif execution["exception"] is None and "actual" not in execution:
            return_reason = "missing_observed_return_value"
        else:
            return_status = _outcome(receipt, "public_examples", case)
            return_reason = "registered_public_expected_outcome_only"
    preservation = [o for o in task.contract.obligations if o.kind == "input_preservation"]
    applicable = [o for o in preservation if o.id in case.obligation_ids]
    preservation_status = "not_applicable" if not preservation else "unknown"
    preservation_reason = "no_explicit_input_preservation_obligation" if not preservation else (
        "case_not_bound_to_preservation_obligation" if not applicable else "missing_or_incomplete_state")
    if applicable and state_complete:
        preservation_status = _outcome(receipt, "input_state", case)
        preservation_reason = "explicit_public_whole_input_preservation"
    return {"case_hash": case.content_hash,
            "artifact_record_hash": artifact.content_hash,
            "execution_receipt_hash": receipt["record_hash"] if receipt else None,
            "evidence_ref": "public_case_" + digest([task.content_hash, artifact.content_hash,
                case.content_hash, receipt["record_hash"] if receipt else None])[:24],
            "public_input": public_input, "expected": expected,
            "expected_is_provided": case.expected_json is not None,
            "expected_exception": case.expected_exception,
            "expected_origin": "registered_public_example_not_hidden_oracle",
            "observation": observation,
            "return_check": {"status": return_status, "reason": return_reason},
            "input_state_changed": changed,
            "preservation_check": {"status": preservation_status, "reason": preservation_reason},
            "other_state_requirements": {"status": "unknown",
                "reason": "No typed expected post-state is registered; in-place goals are not inferred from prose."}}


def _assemble(task, public_task, wrapper, artifact, identity, records):
    replay = _ReceiptReplay(identity, records)
    require(type(identity["executor"]) is dict and type(identity["max_executions"]) is int
            and identity["max_executions"] == MAX_EXECUTIONS and identity["evidence_mode"] == "per_arm"
            and identity["cache_policy"] == "same-exact-artifact-record-case-repetition-v1",
            "Public-case execution cache policy changed")
    conflicts, cases = _conflicting_inputs(task), []
    for case in task.public_cases:
        receipt = replay.run(task, artifact, case) if artifact.availability == "available" else None
        cases.append(_case_result(task, artifact, case, receipt,
                                  digest(json_value(case.arguments_json)) in conflicts))
    require(replay.used == set(replay.records), "Extra or unreferenced public execution receipt")
    counts = {name: {status: sum(c[name]["status"] == status for c in cases)
                    for status in ("pass", "fail", "unknown", "not_applicable")}
              for name in ("return_check", "preservation_check")}
    return seal({"version": VERSION, "request": _request(task, public_task, wrapper, artifact, identity),
        "task": task.to_dict(), "public_task": public_task.to_dict(), "public_wrapper": wrapper.to_dict(),
        "artifact": artifact.to_dict(), "execution_identity": deepcopy(identity),
        "execution_records": sorted((deepcopy(r) for r in records), key=lambda r: r["record_hash"]),
        "cases": cases, "counts": {"registered_cases": len(cases), **counts},
        "information_origins": ORIGINS,
        "fixture_only": artifact.provenance_kind == "fixture" or identity["executor"].get("real_execution") is False,
        "research_increment": False, "full_contract_correctness": "not_established",
        "shadow_only": True, "learning_authorized": False, "deployment_authorized": False})


def _replay(record):
    verify(record)
    require(set(record) == _FIELDS and record["version"] == VERSION, "Unexpected public-case record fields/version")
    row = {"task": CallableTask.from_dict(record["task"]),
           "public_task": CallableTask.from_dict(record["public_task"]), "public_wrapper": record["public_wrapper"]}
    artifact = ArtifactRecord.from_dict(record["artifact"])
    task, public_task, wrapper = _bound_parts(row, artifact)
    require(type(record["execution_records"]) is list, "Explicit public execution receipt list required")
    rebuilt = _assemble(task, public_task, wrapper, artifact, record["execution_identity"],
                        tuple(record["execution_records"]))
    require(record == rebuilt, "Public-case observations differ from bound receipt replay")
    return rebuilt, task, artifact


def collect(row, artifact, executor, root):
    """Execute only registered direct public calls; cached failures are terminal.

    A missing receipt from a previously interrupted cache entry yields an
    explicit unsupported placeholder, never a guessed result or implicit retry.
    Thrown transport errors use the existing unavailable-on-exception adapter.
    """
    _is_real_executor(executor)
    task, public_task, wrapper = _bound_parts(row, artifact)
    base = checked_path(root)
    with _revision_lock(base):
        cache = ExecutionCache(_UnavailableOnException(executor), base / "executions",
                               max_executions=MAX_EXECUTIONS)
        binding = _request(task, public_task, wrapper, artifact, cache.identity)
        _write(base / "binding.json", seal({"request": binding}))
        terminal = base / "record.json"
        if terminal.exists():
            record, _, _ = _replay(_read(terminal))
            require(record["request"] == binding, "Public-case root belongs to another task/artifact/executor")
            return record
        if artifact.availability == "available":
            for case in task.public_cases:
                cache.run(task, artifact, case)
        record = _assemble(task, public_task, wrapper, artifact, cache.identity,
                           tuple(cache.records.values()) + tuple(cache.missing_records.values()))
        _write(terminal, record)
        return record


def model_view(record):
    """Replay first, then project public observations without host condition/H.

    Hashes establish binding/consistency, not observation authenticity. This is
    not an authorized Skill-updater interface, even for development examples.
    """
    record, task, artifact = _replay(record)
    visible = verifier_view(task.contract, artifact, ())
    ids = {o.id: f"obligation_{i}" for i, o in enumerate(task.contract.obligations)}
    cases = []
    omitted = {"case_hash", "artifact_record_hash", "execution_receipt_hash"}
    for index, (case, result) in enumerate(zip(task.public_cases, record["cases"])):
        cases.append({**{k: deepcopy(v) for k, v in result.items() if k not in omitted},
                      "id": f"case_{index:03d}", "contract_quote": case.contract_quote,
                      "obligation_ids": [ids[o] for o in case.obligation_ids]})
    view = {"purpose": "registered_public_case_observations_only",
            "task": visible["task"], "artifact": {"information_origin": "submitted_artifact",
                "availability": artifact.availability, "files": [f.to_dict() for f in artifact.files
                                                                   if f.path == task.module + ".py"]},
            "cases": cases, "counts": deepcopy(record["counts"]),
            "information_origins": ORIGINS, "research_increment": False,
            "full_contract_correctness": "not_established", "learning_authorized": False,
            "limitations": ["Only already registered public examples were executed; no new test or hidden answer was acquired.",
                "Return matches do not prove the whole contract or unregistered in-place postconditions.",
                "Input mutation is not a failure without an applicable explicit preservation obligation.",
                "Unknown is not a semantic failure. References prove identity, not semantic support or authenticity.",
                "This module does not expose initial-to-revised trajectories or authorize Skill updates."]}
    text(json.dumps(view, ensure_ascii=False, sort_keys=True, allow_nan=False), maximum=MAX_MODEL_VIEW_BYTES)
    return view
