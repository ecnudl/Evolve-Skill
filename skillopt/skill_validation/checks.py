"""Registered public-contract checks, with no access to hidden audit answers.

This callable adapter is an engineering step towards repository benchmarks,
not a SWE-bench agent. Its input examples and invariant relations must already
belong to the public contract; a model cannot manufacture their authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from .models import (
    ArtifactRecord,
    Record,
    RubricVersion,
    TaskContract,
    exact_fields,
    require,
    text,
    typed_tuple,
    unique,
)
from .views import bind

VERSION = "skill-validation-public-checks-v1"
METHOD_KINDS = {"public_examples": "requested_behavior", "input_state": "input_preservation",
                "public_invariant": "requested_behavior"}


def json_value(raw: str):
    text(raw, maximum=32768)

    def pairs(items):
        output = {}
        for key, value in items:
            require(key not in output, "Duplicate public-input JSON key")
            output[key] = value
        return output

    def finite(_):
        raise ValueError("Nonfinite public-input JSON")

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=finite)

    def bounded(value, depth=0):
        require(depth <= 12, "Public input exceeds nesting budget")
        require(type(value) is not float or math.isfinite(value), "Nonfinite public-input JSON")
        if isinstance(value, (list, dict)):
            require(len(value) <= 128, "Public input exceeds item budget")
            for child in (value.values() if isinstance(value, dict) else value):
                bounded(child, depth + 1)
    bounded(result)
    return result


@dataclass(frozen=True)
class PublicCase(Record):
    """Host-registered exact-JSON example, not Python loose numeric equality."""
    id: str
    arguments_json: str  # exactly {args: [...], kwargs: {...}}
    contract_quote: str
    obligation_ids: tuple[str, ...]
    expected_json: str | None = None
    expected_exception: str | None = None

    def __post_init__(self):
        text(self.id, maximum=100)
        text(self.contract_quote, maximum=12000)
        arguments = json_value(self.arguments_json)
        require(type(arguments) is dict and set(arguments) == {"args", "kwargs"}
                and type(arguments["args"]) is list and type(arguments["kwargs"]) is dict,
                "Public arguments require explicit args and kwargs")
        typed_tuple(self.obligation_ids, str, maximum=64)
        unique(self.obligation_ids, "case obligation")
        if self.expected_json is not None:
            json_value(self.expected_json)
        if self.expected_exception is not None:
            require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", self.expected_exception) is not None,
                    "Expected exception must be a public type name")
        require(self.expected_json is None or self.expected_exception is None, "Specify one expected outcome")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        require(type(data["obligation_ids"]) is list, "Case obligations require a JSON array")
        data["obligation_ids"] = tuple(data["obligation_ids"])
        return cls(**data)


@dataclass(frozen=True)
class ContractRelation(Record):
    obligation_id: str
    relation: str
    contract_quote: str

    def __post_init__(self):
        text(self.obligation_id, maximum=100)
        text(self.contract_quote, maximum=12000)
        require(self.relation == "repeat_equal", "Only explicit repeat-equality is implemented; no inferred metamorphisms")

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class CallableTask(Record):
    contract: TaskContract
    module: str
    function: str
    public_cases: tuple[PublicCase, ...]
    relations: tuple[ContractRelation, ...] = ()

    def __post_init__(self):
        require(type(self.contract) is TaskContract and self.contract.domain == "coding", "Typed Coding contract required")
        for value in (self.module, self.function):
            require(type(value) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", value) is not None,
                    "This bounded adapter requires a simple Python module/function name")
        typed_tuple(self.public_cases, PublicCase, maximum=16)
        unique([c.id for c in self.public_cases], "public case ID")
        typed_tuple(self.relations, ContractRelation, maximum=16)
        unique([r.obligation_id for r in self.relations], "invariant obligation")
        ids = {o.id for o in self.contract.obligations}
        require(not any(o.target for o in self.contract.obligations if o.kind == "input_preservation"),
                "Callable adapter supports whole-call input preservation only; targeted state checks unsupported")
        for case in self.public_cases:
            require(case.contract_quote in self.contract.prompt and set(case.obligation_ids) <= ids,
                    "Case requires a public-contract basis and existing obligations")
        for relation in self.relations:
            require(relation.contract_quote in self.contract.prompt and relation.obligation_id in ids,
                    "Invariant requires a public-contract basis and existing obligation")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["contract"] = TaskContract.from_dict(data["contract"])
        data["public_cases"] = tuple(PublicCase.from_dict(c) for c in data["public_cases"])
        data["relations"] = tuple(ContractRelation.from_dict(r) for r in data["relations"])
        return cls(**data)


class ExecutionCache:
    """Per-arm (or explicit common-evidence) execution cache, never cross-run alias.

Failed calls are terminal cached evidence, not automatically retried. Resumed
execution requires the original request and receipt to match exactly.
"""
    def __init__(self, executor, root=None, *, max_executions=192, read_only=False, mode="per_arm"):
        require(type(max_executions) is int and 1 <= max_executions <= 10000, "Explicit execution budget required")
        self.executor, self.root = executor, Path(root) if root is not None else None
        self.max_executions, self.read_only = max_executions, read_only
        require(mode in {"per_arm", "common_evidence"}, "Explicit evidence mode required")
        self.mode = mode
        self.records = {}
        self.missing_records = {}
        self.new_executions = 0
        self.cache_hits = 0

    @property
    def identity(self):
        return {"executor": self.executor.identity, "max_executions": self.max_executions,
                "evidence_mode": self.mode,
                "cache_policy": "same-exact-artifact-record-case-repetition-v1"}

    def _verify(self, record, request, task, artifact, case):
        record = verify(record)
        require(record["request"] == request, "Execution cache request mismatch")
        result = verify(record["execution"])
        arguments = json_value(case.arguments_json)
        files = {f.path: f.content for f in artifact.files}
        call = {"module": task.module, "function": task.function, **arguments}
        require(result["input_hash"] == digest({"files": files, **call}) and result["source_hash"] == digest(files)
                and result["call_hash"] == digest(call) and result["executor_identity"] == self.executor.identity,
                "Execution observation is bound to another input, source or executor")
        return record

    def run(self, task: CallableTask, artifact: ArtifactRecord, case: PublicCase, *, attempt=0):
        bind(task.contract, artifact, ())
        require(type(attempt) is int and attempt in {0, 1}, "Only original plus explicit invariant repeat allowed")
        require(case in task.public_cases, "Unregistered test input")
        request = {"version": VERSION, "callable_task_hash": task.content_hash,
                   "artifact_record_hash": artifact.content_hash, "case_hash": case.content_hash,
                   "attempt": attempt, "execution_identity": self.identity}
        key = digest(request)
        if key in self.records:
            self.cache_hits += 1
            return self._verify(self.records[key], request, task, artifact, case)
        if key in self.missing_records:
            return verify(self.missing_records[key])
        path = self.root / (key + ".json") if self.root else None
        intent = self.root / "intents" / (key + ".json") if self.root else None
        if path is not None and path.exists():
            require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink execution cache unsupported")
            record = verify(json.loads(path.read_text()))
            record = self._verify(record, request, task, artifact, case)
            require(not any(p.is_symlink() for p in (intent, *intent.parents)), "Symlink execution intent unsupported")
            require(intent is not None and intent.is_file() and verify(json.loads(intent.read_text()))["request"] == request,
                    "Cached execution requires its original request intent")
            self.records[key] = record
            self.cache_hits += 1
            return record
        interrupted = intent is not None and intent.exists()
        reserved = len(list((self.root / "intents").glob("*.json"))) if self.root is not None else len(self.records)
        if self.read_only or reserved >= self.max_executions or interrupted:
            placeholder = seal({"request": request, "execution": seal({"status": "unsupported",
                         "reason": "interrupted_execution_no_receipt" if interrupted else
                         "common_evidence_missing" if self.read_only else "execution_budget_exhausted"})})
            self.missing_records[key] = placeholder
            return verify(placeholder)
        args = json_value(case.arguments_json)
        if intent is not None:
            require(not any(p.is_symlink() for p in (intent, *intent.parents)), "Symlink execution intent unsupported")
            write_immutable_json(intent, seal({"request": request}))
        self.new_executions += 1
        result = self.executor.run({f.path: f.content for f in artifact.files}, task.module, task.function,
                                   args["args"], args["kwargs"])
        verify(result)
        require(result.get("status") in {"observed", "unsupported", "execution_error"}, "Unexpected executor outcome")
        record = seal({"request": request, "execution": result})
        record = self._verify(record, request, task, artifact, case)
        if path is not None:
            require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink execution output unsupported")
            write_immutable_json(path, record)
        self.records[key] = record
        return verify(record)


def pipeline_hash(rubric: RubricVersion, cache: ExecutionCache):
    return digest({"rubric": rubric.content_hash, "execution_identity": cache.identity,
                   "implementation": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                      for name in ("checks.py", "research.py", "models.py", "stage2.py")},
                   "public_comparison": "exact_json_types_and_values", "version": VERSION})


def _aggregate(statuses):
    if "fail" in statuses:
        return "fail"
    if not statuses or "unknown" in statuses or all(s == "not_applicable" for s in statuses):
        return "unknown"
    return "pass"


def _outcome(record, method, case):
    observed = record["execution"]
    if observed["status"] != "observed":
        return "unknown"
    if method == "public_examples":
        if case.expected_exception is not None:
            return "pass" if observed.get("exception") == case.expected_exception else "fail"
        if case.expected_json is None:
            return "unknown"
        if observed.get("exception") is not None:
            return "fail"
        require("actual" in observed, "Observed execution lacks actual return value")
        return "pass" if digest(observed["actual"]) == digest(json_value(case.expected_json)) else "fail"
    required = {"before_args", "after_args", "before_kwargs", "after_kwargs"}
    if not required <= set(observed):
        return "unknown"
    before = json_value(case.arguments_json)
    require(observed["before_args"] == before["args"] and observed["before_kwargs"] == before["kwargs"],
            "Observed initial input differs from public input")
    return "pass" if (digest(observed["before_args"]) == digest(observed["after_args"])
                      and digest(observed["before_kwargs"]) == digest(observed["after_kwargs"])) else "fail"


def validate_callable(task: CallableTask, artifact: ArtifactRecord, rubric: RubricVersion, cache: ExecutionCache):
    bind(task.contract, artifact, ())
    require(rubric.execution_policy == "stage2-contract-checks-v1", "Unsupported check-execution policy")
    for rule in rubric.checks:
        require(rule.method in METHOD_KINDS and METHOD_KINDS[rule.method] == rule.obligation_kind,
                "Illegal method or changed correctness semantics")
        require(rule.applicability == "explicit_obligation" and rule.exceptions == "absent_obligation",
                "Applicability is executable contract logic, not arbitrary model prose")
    instances = []
    for rule in rubric.checks:
        applicable = [o for o in task.contract.obligations if o.kind == rule.obligation_kind]
        if not applicable:
            instances.append({"check_id": rule.id, "method": rule.method, "obligation_kind": rule.obligation_kind,
                              "obligation_id": None, "status": "not_applicable",
                              "evidence_refs": [], "reason": "No explicit matching obligation; not a missing-evidence pass."})
        for obligation in applicable:
            statuses, refs = [], []
            cases = [c for c in task.public_cases if obligation.id in c.obligation_ids]
            relation = next((r for r in task.relations if r.obligation_id == obligation.id), None)
            if artifact.availability == "available" and (rule.method != "public_invariant" or relation is not None):
                for case in cases:
                    record = cache.run(task, artifact, case)
                    refs.append(record["record_hash"])
                    if rule.method == "public_invariant":
                        repeated = cache.run(task, artifact, case, attempt=1)
                        refs.append(repeated["record_hash"])
                        first, second = record["execution"], repeated["execution"]
                        if first["status"] != "observed" or second["status"] != "observed":
                            statuses.append("unknown")
                        elif first.get("exception") is not None or second.get("exception") is not None:
                            statuses.append("unknown")
                        elif "actual" not in first or "actual" not in second:
                            statuses.append("unknown")
                        else:
                            statuses.append("pass" if digest(first["actual"]) == digest(second["actual"]) else "fail")
                    else:
                        statuses.append(_outcome(record, rule.method, case))
            instances.append({"check_id": rule.id, "method": rule.method, "obligation_kind": rule.obligation_kind,
                              "obligation_id": obligation.id, "status": _aggregate(statuses),
                              "evidence_refs": refs,
                              "reason": "Only registered public examples/relations and observed execution are used."})
    obligations = {o.id: _aggregate([r["status"] for r in instances if r["obligation_id"] == o.id])
                   for o in task.contract.obligations}
    return seal({"version": VERSION, "task_hash": task.contract.content_hash, "callable_task_hash": task.content_hash,
                 "artifact_record_hash": artifact.content_hash, "pipeline_hash": pipeline_hash(rubric, cache),
                 "rubric_hash": rubric.content_hash, "checks": instances, "obligations": obligations,
                 "status": _aggregate([obligations[o.id] for o in task.contract.obligations if o.critical]),
                 "limitations": ["Not a full repository agent or universal correctness proof.",
                                  "Registered return examples use exact JSON equality, including numeric representation.",
                                  "Public contract annotations are host assertions, not quotation entailment proofs.",
                                  "Execution measurements do not prove robustness to adversarial in-process tampering."]})


def compare_frozen(task: CallableTask, artifacts: tuple[ArtifactRecord, ...], rubrics: dict[str, RubricVersion],
                   executor, *, root=None, max_executions=192, common_evidence=False):
    require(type(artifacts) is tuple and len(artifacts) == 3
            and {a.condition for a in artifacts} == {"no_skill", "current", "candidate"},
            "Exactly the same three frozen conditions are required")
    require(len({a.repeat for a in artifacts}) == 1, "Paired artifacts require the same repeat")
    for artifact in artifacts:
        bind(task.contract, artifact, ())
    require(set(rubrics) == {"fixed", "adaptive_no_research", "adaptive_research"}, "Three preregistered verifier arms required")
    # Shared public examples are never selected based on H or a verifier's success.
    shared = None
    if common_evidence:
        shared = ExecutionCache(executor, Path(root) / "common" if root else None,
                                max_executions=max_executions, mode="common_evidence")
        for artifact in artifacts:
            if artifact.availability == "available":
                for case in task.public_cases:
                    shared.run(task, artifact, case)
        shared.read_only = True
    reports, costs, execution_records = {}, {}, {}
    for arm, rubric in rubrics.items():
        cache = shared or ExecutionCache(executor, Path(root) / arm if root else None, max_executions=max_executions)
        reports[arm] = [validate_callable(task, a, rubric, cache) for a in artifacts]
        used_refs = {ref for report in reports[arm] for check in report["checks"] for ref in check["evidence_refs"]}
        used_records = [r for r in cache.records.values() if r["record_hash"] in used_refs]
        used_missing = [r for r in cache.missing_records.values() if r["record_hash"] in used_refs]
        # Stable historical cost on replay, not the number of this invocation's
        # cache reads. Preparation is charged separately for common evidence.
        costs[arm] = {"execution_requests": 0 if common_evidence else len(used_records),
                      "missing_execution_records": len(used_missing),
                      "observed_executions": 0 if common_evidence else sum(
                          r["execution"]["status"] == "observed" for r in used_records),
                      "execution_seconds": 0 if common_evidence else sum(
                          r["execution"].get("duration_seconds", 0) for r in used_records)}
        execution_records[arm] = [verify(r) for r in sorted((*used_records, *used_missing), key=lambda r: r["record_hash"])]
    return seal({"version": VERSION, "mode": "common_evidence" if common_evidence else "end_to_end_checks",
                 "task_hash": task.contract.content_hash, "reports": reports, "costs": costs,
                 "execution_records_host_only": execution_records,
                 "shared_execution_cost": len(shared.records) if shared else 0,
                 "shared_execution_records_host_only": list(shared.records.values()) if shared else [],
                 "condition_mapping_host_only": {a.content_hash: a.condition for a in artifacts},
                 "task_specific_expected_values_from": "public_contract_only",
                 "common_evidence_limit": "Only original public calls; new invariant repetitions are unknown in common mode.",
                 "model_calls": 0, "formal_effect_estimate": False})
