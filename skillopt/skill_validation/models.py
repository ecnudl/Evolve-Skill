"""Small immutable records; public evidence and host audit are different types.

Checksums reuse the historical canonical JSON implementation. They establish
content integrity, not the truth of an observation or execution authenticity.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from pathlib import PurePosixPath
from typing import Any

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

PARTITIONS = frozenset({"development", "verifier_calibration", "verifier_audit", "skill_confirmation", "final"})
STATUSES = frozenset({"pass", "fail", "unknown", "not_applicable"})
KINDS = frozenset({"requested_behavior", "input_preservation", "file_preservation"})
PROVENANCES = frozenset({"model", "fixture", "mutant"})


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def text(value: Any, *, maximum: int = 200000, empty: bool = False) -> None:
    require(type(value) is str and (empty or bool(value.strip())) and len(value.encode("utf-8")) <= maximum,
            "Expected bounded UTF-8 text, not an arbitrary nested payload")


def hash_text(value: str) -> None:
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "Expected SHA256")


def file_path(value: str) -> None:
    text(value, maximum=512)
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in value
            and str(path) == value and value != "." and not any(ord(c) < 32 for c in value),
            "Artifact paths must be normalized relative paths")


def exact_fields(cls, value: dict) -> dict:
    require(type(value) is dict and set(value) == {f.name for f in fields(cls)},
            f"Unexpected or missing {cls.__name__} fields")
    return dict(value)


def typed_tuple(value, cls, *, maximum=1000) -> None:
    require(type(value) is tuple and len(value) <= maximum and all(type(v) is cls for v in value),
            f"Expected bounded immutable tuple of {cls.__name__}")


def unique(values, name: str) -> None:
    require(len(values) == len(set(values)), f"Duplicate {name}")


class Record:
    def to_dict(self) -> dict:
        # Detach all nested containers, with tuples serialized consistently.
        return json.loads(json.dumps(asdict(self), ensure_ascii=False, allow_nan=False))

    @property
    def content_hash(self) -> str:
        return digest(self.to_dict())

    def sealed(self) -> dict:
        return seal(self.to_dict())


@dataclass(frozen=True)
class SourceFile(Record):
    path: str
    content: str

    def __post_init__(self):
        file_path(self.path)
        text(self.content, empty=True)

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class Obligation(Record):
    id: str
    kind: str
    statement: str
    contract_quote: str
    target: str = ""
    critical: bool = True

    def __post_init__(self):
        text(self.id, maximum=100)
        require(self.kind in KINDS, "Unsupported obligation kind")
        text(self.statement, maximum=12000)
        text(self.contract_quote, maximum=12000)
        require(type(self.critical) is bool, "Criticality must be boolean")
        text(self.target, maximum=512, empty=True)
        if self.kind == "file_preservation":
            file_path(self.target)

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class TaskContract(Record):
    task_id: str
    original_task_id: str
    family_id: str
    project_id: str
    partition: str
    domain: str
    mechanism: str  # Host annotation, NEVER an answer about applicability.
    prompt: str
    obligations: tuple[Obligation, ...]
    public_files: tuple[SourceFile, ...] = ()

    def __post_init__(self):
        for value in (self.task_id, self.original_task_id, self.family_id, self.project_id, self.domain, self.mechanism):
            text(value, maximum=512)
        require(self.partition in PARTITIONS, "Unknown data purpose")
        text(self.prompt)
        typed_tuple(self.obligations, Obligation, maximum=64)
        require(bool(self.obligations), "A task requires explicit public obligations")
        unique([o.id for o in self.obligations], "obligation ID")
        require(all(o.contract_quote in self.prompt for o in self.obligations), "Obligation lacks a public contract basis")
        typed_tuple(self.public_files, SourceFile, maximum=100)
        unique([f.path for f in self.public_files], "public file")
        for obligation in self.obligations:
            if obligation.kind == "file_preservation":
                require(obligation.target in {f.path for f in self.public_files}, "Preserved file has no public baseline")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["obligations"] = tuple(Obligation.from_dict(v) for v in data["obligations"])
        data["public_files"] = tuple(SourceFile.from_dict(v) for v in data["public_files"])
        return cls(**data)


@dataclass(frozen=True)
class ArtifactRecord(Record):
    task_hash: str
    repeat: int
    condition: str
    skill_version: str
    skill_hash: str
    files: tuple[SourceFile, ...]
    availability: str
    provenance_kind: str
    provenance_complete: bool
    historical_only: bool
    source_ref: str
    source_hash: str

    def __post_init__(self):
        for value in (self.task_hash, self.skill_hash, self.source_hash):
            hash_text(value)
        require(type(self.repeat) is int and self.repeat >= 0, "Repeat must be a nonnegative integer")
        require(self.condition in {"no_skill", "current", "candidate", "unassigned"}, "Unknown host condition")
        if self.condition == "no_skill":
            require(self.skill_hash == hashlib.sha256(b"").hexdigest(), "No-Skill requires the canonical empty Skill hash")
        text(self.skill_version, maximum=512)
        text(self.source_ref, maximum=4096)
        typed_tuple(self.files, SourceFile, maximum=100)
        unique([f.path for f in self.files], "artifact file")
        require(self.availability in {"available", "api_failure", "parse_failure"}, "Unknown delivery availability")
        require(self.availability != "available" or bool(self.files), "Available Coding artifact requires actual files")
        require(self.availability == "available" or not self.files, "Unavailable artifact cannot contain invented files")
        require(self.provenance_kind in PROVENANCES, "Unknown artifact provenance")
        require(type(self.provenance_complete) is bool and type(self.historical_only) is bool, "Typed provenance required")

    @property
    def artifact_hash(self) -> str:
        return digest({f.path: f.content for f in self.files} if self.availability == "available" else None)

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["files"] = tuple(SourceFile.from_dict(v) for v in data["files"])
        return cls(**data)


@dataclass(frozen=True)
class Observation(Record):
    id: str
    obligation_id: str
    kind: str
    passed: bool | None = None
    before_hash: str | None = None
    after_hash: str | None = None

    def __post_init__(self):
        text(self.id, maximum=128)
        text(self.obligation_id, maximum=100)
        require(self.kind in {"public_test", "input_state"}, "Unsupported recorded observation")
        require(self.passed is None or type(self.passed) is bool, "Observed outcome must be boolean or absent")
        for value in (self.before_hash, self.after_hash):
            if value is not None:
                hash_text(value)
        if self.kind == "input_state":
            require(self.passed is None, "State preservation is derived from fingerprints, not claimed in prose")
        else:
            require(self.before_hash is self.after_hash is None, "Public test cannot carry state fingerprints")

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class EvidenceRecord(Record):
    task_hash: str
    artifact_hash: str
    artifact_record_hash: str
    repeat: int
    visibility: str
    execution_status: str
    observations: tuple[Observation, ...]
    source_ref: str
    source_hash: str
    provenance_kind: str

    def __post_init__(self):
        for value in (self.task_hash, self.artifact_hash, self.artifact_record_hash, self.source_hash):
            hash_text(value)
        require(type(self.repeat) is int and self.repeat >= 0, "Invalid evidence repeat")
        require(self.visibility == "public", "Hidden audit receipts must not enter visible evidence")
        require(self.execution_status in {"observed", "unsupported", "api_failure", "parse_failure", "execution_error"},
                "Unknown execution status")
        require(self.provenance_kind in PROVENANCES, "Unknown evidence provenance")
        text(self.source_ref, maximum=4096)
        typed_tuple(self.observations, Observation)
        unique([o.id for o in self.observations], "observation ID")
        require(self.execution_status == "observed" or not self.observations,
                "Unavailable execution cannot supply confirmed observations")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["observations"] = tuple(Observation.from_dict(v) for v in data["observations"])
        return cls(**data)


@dataclass(frozen=True)
class RubricCheck(Record):
    id: str
    obligation_kind: str
    method: str
    applicability: str
    exceptions: str
    evidence_requirement: str

    def __post_init__(self):
        for value in (self.id, self.method, self.applicability, self.exceptions, self.evidence_requirement):
            text(value, maximum=2000)
        require(self.obligation_kind in KINDS, "Unknown obligation kind")

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class RubricVersion(Record):
    version: str
    mechanism: str
    generation_policy: str
    execution_policy: str
    applicability_policy: str
    aggregation_policy: str
    checks: tuple[RubricCheck, ...]
    parent_hash: str | None = None

    def __post_init__(self):
        for value in (self.version, self.mechanism, self.generation_policy, self.execution_policy,
                      self.applicability_policy, self.aggregation_policy):
            text(value, maximum=2000)
        if self.parent_hash is not None:
            hash_text(self.parent_hash)
        typed_tuple(self.checks, RubricCheck, maximum=64)
        require(bool(self.checks), "Rubric requires checks")
        unique([c.id for c in self.checks], "Rubric check ID")

    @property
    def pipeline_hash(self) -> str:
        """Future authorization must bind this, not only per-task test lists."""
        return self.content_hash

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["checks"] = tuple(RubricCheck.from_dict(v) for v in data["checks"])
        return cls(**data)


@dataclass(frozen=True)
class CheckInstance(Record):
    rubric_pipeline_hash: str
    task_hash: str
    artifact_hash: str
    check_id: str
    obligation_id: str | None
    method: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self):
        for value in (self.rubric_pipeline_hash, self.task_hash, self.artifact_hash):
            hash_text(value)
        text(self.check_id, maximum=100)
        text(self.method, maximum=2000)
        if self.obligation_id is not None:
            text(self.obligation_id, maximum=100)
        typed_tuple(self.evidence_refs, str)
        for value in self.evidence_refs:
            text(value, maximum=1024)

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["evidence_refs"] = tuple(data["evidence_refs"])
        return cls(**data)


@dataclass(frozen=True)
class CheckResult(Record):
    instance_hash: str
    check_id: str
    obligation_id: str | None
    status: str
    reason: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self):
        hash_text(self.instance_hash)
        text(self.check_id, maximum=100)
        if self.obligation_id is not None:
            text(self.obligation_id, maximum=100)
        require(self.status in STATUSES, "Invalid check status")
        text(self.reason)
        require(type(self.evidence_refs) is tuple and all(type(v) is str for v in self.evidence_refs), "Typed evidence references required")
        require(self.status not in {"pass", "fail"} or bool(self.evidence_refs), "Confirmed verdict requires evidence")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["evidence_refs"] = tuple(data["evidence_refs"])
        return cls(**data)


@dataclass(frozen=True)
class ValidationReport(Record):
    version: str
    task_hash: str
    artifact_record_hash: str
    rubric_pipeline_hash: str
    instances: tuple[CheckInstance, ...]
    checks: tuple[CheckResult, ...]
    obligation_results: tuple[tuple[str, str], ...]
    status: str
    provenance_kind: str
    complete_provenance: bool
    historical_only: bool
    limitations: tuple[str, ...]

    def __post_init__(self):
        text(self.version, maximum=128)
        for value in (self.task_hash, self.artifact_record_hash, self.rubric_pipeline_hash):
            hash_text(value)
        require(self.status in {"pass", "fail", "unknown"}, "Invalid report status")
        require(self.provenance_kind in PROVENANCES, "Invalid report provenance")
        require(type(self.complete_provenance) is bool and type(self.historical_only) is bool, "Typed report provenance required")
        typed_tuple(self.instances, CheckInstance)
        typed_tuple(self.checks, CheckResult)
        require(len(self.instances) == len(self.checks), "Check results must cover every instance")
        unique([i.content_hash for i in self.instances], "check instance")
        for instance, result in zip(self.instances, self.checks):
            require(instance.content_hash == result.instance_hash and instance.check_id == result.check_id
                    and instance.obligation_id == result.obligation_id and instance.evidence_refs == result.evidence_refs,
                    "Report check result has mismatched evidence")
            require(instance.task_hash == self.task_hash and instance.rubric_pipeline_hash == self.rubric_pipeline_hash,
                    "Report instance has mismatched task or Rubric")
        require(type(self.obligation_results) is tuple, "Immutable obligation results required")
        for row in self.obligation_results:
            require(type(row) is tuple and len(row) == 2 and row[1] in {"pass", "fail", "unknown"}, "Invalid obligation result")
            text(row[0], maximum=100)
        unique([row[0] for row in self.obligation_results], "reported obligation")
        typed_tuple(self.limitations, str, maximum=32)

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        data["instances"] = tuple(CheckInstance.from_dict(v) for v in data["instances"])
        data["checks"] = tuple(CheckResult.from_dict(v) for v in data["checks"])
        data["obligation_results"] = tuple(tuple(v) for v in data["obligation_results"])
        data["limitations"] = tuple(data["limitations"])
        return cls(**data)


@dataclass(frozen=True)
class GateDecision(Record):
    """Interface placeholder only: Stage 1 cannot authorize Rubrics or Skills."""
    gate: str
    status: str
    rubric_pipeline_hash: str
    reason: str = "Stage 1 is replay only; no calibration or Skill admission implemented."

    def __post_init__(self):
        require(self.gate in {"verifier", "skill"} and self.status == "pending", "Stage 1 grants no admission authority")
        hash_text(self.rubric_pipeline_hash)
        text(self.reason)

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


def unseal_record(value: dict, cls):
    checked = verify(value)
    return cls.from_dict({k: v for k, v in checked.items() if k != "record_hash"})
