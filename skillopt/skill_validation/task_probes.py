"""Bounded task-level model hypotheses and isolated observations, never H answers.

An expected value or equal-output relation is a model hypothesis, including
after an execution disagrees with it. This module does not certify its contract
interpretation, authorize a verifier, or label a semantic task failure. Hosts
must calibrate a frozen generation policy separately before using its feedback.
No proposed code is interpreted; only JSON calls to the host's fixed callable
are sent to the existing isolated executor.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from .checks import CallableTask
from .models import ArtifactRecord, require, text

VERSION = "skill-validation-task-probes-v1"
MAX_PROBES = 8
MAX_JSON_BYTES = 65536
_PROBE_FIELDS = {"kind", "calls", "expected", "obligation_id", "contract_quote", "rationale"}
_OBSERVED_FIELDS = ("actual", "before_args", "after_args", "before_kwargs", "after_kwargs")


def _json(value, depth=0):
    """Reject tuples, custom objects, non-string keys and nonfinite numbers."""
    require(depth <= 12, "Probe JSON exceeds depth budget")
    if type(value) in {type(None), bool, int}:
        return
    if type(value) is str:
        text(value, maximum=32768, empty=True)
        return
    if type(value) is float:
        require(math.isfinite(value), "Probe JSON must be finite")
        return
    require(type(value) in {list, dict} and len(value) <= 128, "Probe accepts bounded plain JSON only")
    if type(value) is dict:
        require(all(type(key) is str for key in value), "Probe JSON keys must be strings")
        for key in value:
            text(key, maximum=1024, empty=True)
    for child in value.values() if type(value) is dict else value:
        _json(child, depth + 1)


def _detached(value):
    _json(value)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
    require(len(raw.encode()) <= MAX_JSON_BYTES, "Probe JSON exceeds byte budget")
    return json.loads(raw)


def _load_json(raw, maximum):
    text(raw, maximum=maximum)

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate probe JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("Nonfinite probe JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def _decode(raw):
    if type(raw) is str:
        raw = _load_json(raw, MAX_JSON_BYTES)
    return _detached(raw)


def execution_policy_hash(*, max_probes=2):
    """Execution/schema fingerprint, not the host's complete generation policy."""
    require(type(max_probes) is int and 1 <= max_probes <= MAX_PROBES, "Invalid probe budget")
    return digest({"version": VERSION, "max_probes": max_probes,
                   "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "comparison": "exact_json_types_and_values", "semantic_authority": "none"})


def parse_probes(raw, task: CallableTask, *, max_probes=2):
    """Parse {probes: [...]} without accepting executable model instructions.

    Each probe has exactly kind, calls, expected, obligation_id, contract_quote,
    rationale. Empty proposals are valid abstentions. Quote matching establishes
    public provenance only, never entailment or input-domain validity.
    """
    require(type(task) is CallableTask, "Typed host callable required")
    policy = execution_policy_hash(max_probes=max_probes)
    value = _decode(raw)
    require(type(value) is dict and set(value) == {"probes"}, "Only a probes array is accepted")
    probes = value["probes"]
    require(type(probes) is list and len(probes) <= max_probes, "Probe count exceeds frozen budget")
    obligations = {o.id for o in task.contract.obligations if o.kind == "requested_behavior"}
    for probe in probes:
        require(type(probe) is dict and set(probe) == _PROBE_FIELDS, "Unexpected probe fields")
        require(type(probe["kind"]) is str and probe["kind"] in {"expected", "equal_relation"},
                "Unsupported probe kind")
        require(type(probe["obligation_id"]) is str and probe["obligation_id"] in obligations,
                "Probes may only test an existing requested-behavior obligation")
        text(probe["contract_quote"], maximum=12000)
        require(probe["contract_quote"] in task.contract.prompt, "Probe quote is absent from public contract")
        text(probe["rationale"], maximum=4000)
        calls = probe["calls"]
        count = 1 if probe["kind"] == "expected" else 2
        require(type(calls) is list and len(calls) == count, "Wrong number of calls for probe kind")
        require(probe["kind"] == "expected" or probe["expected"] is None,
                "Equal relations cannot supply an expected answer")
        for call in calls:
            require(type(call) is dict and set(call) == {"args", "kwargs"}, "Only JSON args/kwargs are accepted")
            require(type(call["args"]) is list and type(call["kwargs"]) is dict,
                    "Calls require an args array and kwargs object")
    return seal({"version": VERSION, "task_hash": task.contract.content_hash,
                 "callable_task_hash": task.content_hash, "max_probes": max_probes,
                 "pipeline_hash": policy, "pipeline_scope": "execution_schema_only_not_generator_authorization",
                 "probes": probes, "information_origin": "model_hypothesis",
                 "contract_validation": "literal_quote_only_not_entailment",
                 "semantic_authority": False, "status": "proposed" if probes else "abstained"})


def _path(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink probe evidence path unsupported")
    return path


def _read(path, maximum=1048576):
    # Receipts wrap several separately bounded observations and executor metadata;
    # they must not inherit the smaller model-proposal depth/string budgets.
    return verify(_load_json(_path(path).read_text(encoding="utf-8"), maximum))


def _write(path, value):
    write_immutable_json(_path(path), value)


def _bindings(task, files, call, identity):
    invocation = {"module": task.module, "function": task.function, **call}
    return {"input_hash": digest({"files": files, **invocation}), "source_hash": digest(files),
            "call_hash": digest(invocation), "executor_identity": identity}


def _check_execution(execution, bindings):
    execution = verify(execution)
    require(execution.get("status") in {"observed", "unsupported", "execution_error"},
            "Unknown executor state")
    require(all(execution.get(key) == value for key, value in bindings.items()),
            "Probe execution bound to different input, source, callable or executor")
    return execution


def _observe(execution, call):
    """Project only bounded JSON observations; missing state stays unknown."""
    public = {key: None for key in _OBSERVED_FIELDS}
    public["exception"] = None
    if execution["status"] != "observed":
        return public, "unknown", execution.get("reason", "execution_unavailable")
    if execution.get("cleanup_confirmed") is not True:
        return public, "unknown", "isolation_cleanup_not_confirmed"
    try:
        for key in _OBSERVED_FIELDS:
            if key in execution:
                public[key] = _detached(execution[key])
        exception = execution.get("exception")
        require(exception is None or type(exception) is str, "Nonprimitive exception")
        if exception is not None:
            text(exception, maximum=256)
        public["exception"] = exception
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {**{key: None for key in _OBSERVED_FIELDS}, "exception": None}, "unknown", "unsupported_observation"
    if not all(key in execution for key in (*_OBSERVED_FIELDS, "exception")):
        return public, "unknown", "missing_observation_fields"
    if (type(public["before_args"]) is not list or type(public["after_args"]) is not list
            or type(public["before_kwargs"]) is not dict or type(public["after_kwargs"]) is not dict):
        return public, "unknown", "unavailable_input_state"
    require(digest({"args": public["before_args"], "kwargs": public["before_kwargs"]}) == digest(call),
            "Recorded before-state differs from proposed input")
    if public["exception"] is not None:
        return public, "unknown", "call_raised_exception"
    return public, "observed", "bounded_call_observed"


def execute_probes(task, artifact, proposal, executor, root):
    """Execute each call independently, cache intent/terminal, report hypotheses.

    Interrupted calls are never resampled. Unexpected transport exceptions get
    durable unknown terminals. Invalid/tampered bindings raise with the intent
    retained; no observation is accepted under the wrong evidence identity.
    """
    require(type(task) is CallableTask and type(artifact) is ArtifactRecord, "Typed task and artifact required")
    require(artifact.task_hash == task.contract.content_hash, "Artifact belongs to another task")
    proposal = verify(proposal)
    parsed = parse_probes({"probes": proposal.get("probes")}, task, max_probes=proposal.get("max_probes"))
    require(proposal == parsed, "Changed probe policy, task or proposal metadata")
    root = _path(root)
    identity = _detached(executor.identity)
    files = {f.path: f.content for f in artifact.files}
    request = {"version": VERSION, "task_hash": task.contract.content_hash, "callable_task_hash": task.content_hash,
               "artifact_record_hash": artifact.content_hash, "proposal_hash": proposal["record_hash"],
               "pipeline_hash": proposal["pipeline_hash"], "executor_identity": identity}
    report_path = _path(root / "reports" / (digest(request) + ".json"))
    completed = _read(report_path, maximum=8388608) if report_path.exists() else None
    _write(root / "proposals" / (proposal["record_hash"] + ".json"), proposal)
    rows = []
    for index, probe in enumerate(proposal["probes"]):
        observations, references = [], []
        for call_index, call in enumerate(probe["calls"]):
            call_request = {**request, "probe_index": index, "call_index": call_index, "call": call}
            key = digest(call_request)
            terminal, intent = root / "calls" / (key + ".json"), root / "intents" / (key + ".json")
            bindings = _bindings(task, files, call, identity)
            terminal, intent = _path(terminal), _path(intent)
            intent_value = seal({"request": call_request})
            if terminal.exists():
                record = _read(terminal)
                require(record.get("request") == call_request and intent.is_file()
                        and _read(intent) == intent_value, "Cached probe call/intent mismatch")
            else:
                require(completed is None, "Completed probe report is missing its execution receipt; no resampling")
                interrupted = intent.exists()
                _write(intent, intent_value)
                performed = False
                if artifact.availability != "available" or interrupted:
                    reason = "interrupted_call_no_resampling" if interrupted else "artifact_unavailable"
                    execution = seal({**bindings, "status": "unsupported", "reason": reason})
                else:
                    performed = True
                    try:
                        execution = executor.run(dict(files), task.module, task.function,
                                                 _detached(call["args"]), _detached(call["kwargs"]))
                    except Exception as error:
                        execution = seal({**bindings, "status": "execution_error",
                                          "reason": "executor_exception_" + type(error).__name__})
                execution = _check_execution(execution, bindings)
                record = seal({"request": call_request, "execution": execution, "execution_performed": performed})
                _write(terminal, record)
            execution = _check_execution(record["execution"], bindings)
            require(type(record.get("execution_performed")) is bool, "Unknown execution provenance")
            public, state, reason = _observe(execution, call)
            references.append(record["record_hash"])
            observations.append({"call_index": call_index, "status": state, "reason": reason,
                                 "execution_performed": record["execution_performed"],
                                 "execution_ref": execution["record_hash"], "receipt_ref": record["record_hash"],
                                 "public_observation": public})
        if any(o["status"] != "observed" for o in observations):
            outcome = "unknown"
        else:
            actual = observations[0]["public_observation"]["actual"]
            expected = (probe["expected"] if probe["kind"] == "expected"
                        else observations[1]["public_observation"]["actual"])
            outcome = "match" if digest(actual) == digest(expected) else "mismatch"
        rows.append({"probe_index": index, "probe": probe, "status": outcome, "observations": observations,
                     "evidence_refs": references, "information_origin": "model_hypothesis",
                     "confirmed_semantic_failure": False, "semantic_status": "unknown"})
    statuses = [row["status"] for row in rows]
    overall = "mismatch" if "mismatch" in statuses else "unknown" if not statuses or "unknown" in statuses else "match"
    report = seal({"version": VERSION, "request": request, "task_hash": task.contract.content_hash,
                   "artifact_record_hash": artifact.content_hash, "proposal_hash": proposal["record_hash"],
                   "pipeline_hash": proposal["pipeline_hash"], "status": overall, "probes": rows,
                   "information_origin": "model_hypothesis", "confirmed_semantic_failure": False,
                   "semantic_status": "unknown", "deployment_authorized": False,
                   "limitation": "Observed agreement with proposed expectations is not semantic correctness; no H answer used."})
    require(completed is None or completed == report, "Completed probe report disagrees with execution receipts")
    _write(report_path, report)
    return report
