"""Deterministic fixed-artifact replay, not a runtime or a learned validator.

Recorded public test outcomes, recorded state fingerprints and public file
bytes are the only evidence used. No eval/exec/subprocess/reference oracle.
Unavailable execution stays unknown; there is no unsandboxed fallback.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import VERSION
from .models import (
    ArtifactRecord,
    CheckInstance,
    CheckResult,
    EvidenceRecord,
    RubricCheck,
    RubricVersion,
    TaskContract,
    ValidationReport,
    require,
)
from .views import bind

GENERATION = "fixed-explicit-obligations-v1"
APPLICABILITY = "explicit-contract-kind-only-v1"
AGGREGATION = "common-task-obligations-critical-unknown-v1"
METHODS = {"recorded_public_tests", "recorded_input_state", "public_file_bytes"}


def execution_policy() -> str:
    # Bind future authorization to the actual generation/check/view machinery,
    # not just a mutable text label or task-specific list of test cases.
    hashes = [hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
              for name in ("models.py", "views.py", "engine.py", "importers.py", "legacy.py")]
    return "offline-replay-only:" + hashlib.sha256("".join(hashes).encode()).hexdigest()


def fixed_rubric() -> RubricVersion:
    return RubricVersion(
        version="constraint-preservation-fixed-v1", mechanism="constraint_preservation",
        generation_policy=GENERATION, execution_policy=execution_policy(),
        applicability_policy=APPLICABILITY, aggregation_policy=AGGREGATION,
        checks=(
            RubricCheck("public_behavior", "requested_behavior", "recorded_public_tests",
                        "Only explicit requested behavior with recorded public checks.",
                        "Missing receipts are unknown, not a pass.", "Bound public execution receipt."),
            RubricCheck("input_preservation", "input_preservation", "recorded_input_state",
                        "Only an explicit requirement not to change input state.",
                        "An in-place task without that obligation is not applicable.",
                        "Execution-before and execution-after fingerprints from the same public case."),
            RubricCheck("file_preservation", "file_preservation", "public_file_bytes",
                        "Only a file explicitly required to remain byte-identical.",
                        "Authorized replacements are not implicit preservation obligations.",
                        "Public baseline file and delivered file bytes."),
        ),
    )


def _aggregate(statuses):
    if "fail" in statuses:
        return "fail"
    if not statuses or "unknown" in statuses or all(s == "not_applicable" for s in statuses):
        return "unknown"
    return "pass"


def validate(task: TaskContract, artifact: ArtifactRecord, evidence: tuple[EvidenceRecord, ...],
             rubric: RubricVersion | None = None) -> ValidationReport:
    bind(task, artifact, evidence)
    rubric = fixed_rubric() if rubric is None else rubric
    require(type(rubric) is RubricVersion, "Typed reusable Rubric required")
    require(rubric.generation_policy == GENERATION and rubric.execution_policy == execution_policy()
            and rubric.applicability_policy == APPLICABILITY and rubric.aggregation_policy == AGGREGATION,
            "Unsupported or changed validation pipeline; do not inherit old authorization")
    expected_kind = {"recorded_public_tests": "requested_behavior", "recorded_input_state": "input_preservation",
                     "public_file_bytes": "file_preservation"}
    for check in rubric.checks:
        require(check.method in METHODS and expected_kind[check.method] == check.obligation_kind,
                "Unsupported method or changed obligation semantics")
    instances, results = [], []
    for check in rubric.checks:
        obligations = [o for o in task.obligations if o.kind == check.obligation_kind]
        if not obligations:
            instance = CheckInstance(rubric.pipeline_hash, task.content_hash, artifact.artifact_hash,
                                     check.id, None, check.method, ())
            instances.append(instance)
            results.append(CheckResult(instance.content_hash, check.id, None, "not_applicable",
                                       "No corresponding explicit obligation in the public contract.", ()))
        for obligation in obligations:
            refs, outcomes = [], []
            if artifact.availability != "available":
                reason = artifact.availability + ": delivery problem, not a confirmed semantic error."
            elif check.method == "public_file_bytes":
                before = {f.path: f.content for f in task.public_files}[obligation.target]
                after = {f.path: f.content for f in artifact.files}.get(obligation.target)
                refs = (f"contract:{task.content_hash}", f"artifact:{artifact.artifact_hash}")
                outcomes = ["pass" if after == before else "fail"]
                reason = "Compared explicitly protected file bytes; no code was executed."
            else:
                target_kind = "public_test" if check.method == "recorded_public_tests" else "input_state"
                for receipt in evidence:
                    if receipt.execution_status != "observed":
                        continue
                    for observation in receipt.observations:
                        if observation.obligation_id != obligation.id or observation.kind != target_kind:
                            continue
                        refs.append(f"evidence:{receipt.content_hash}:{observation.id}")
                        if target_kind == "input_state":
                            outcome = (None if observation.before_hash is None or observation.after_hash is None
                                       else observation.before_hash == observation.after_hash)
                        else:
                            outcome = observation.passed
                        outcomes.append("unknown" if outcome is None else "pass" if outcome else "fail")
                unavailable = sorted({e.execution_status for e in evidence if e.execution_status != "observed"})
                if unavailable:
                    outcomes.append("unknown")
                reason = ("Only recorded public observations were replayed; untested cases remain unverified."
                          if refs else "Missing admissible public evidence; execution is not attempted.")
                if unavailable:
                    reason += " Unavailable execution: " + ", ".join(unavailable) + "."
            status = _aggregate(outcomes)
            instance = CheckInstance(rubric.pipeline_hash, task.content_hash, artifact.artifact_hash,
                                     check.id, obligation.id, check.method, tuple(refs))
            instances.append(instance)
            results.append(CheckResult(instance.content_hash, check.id, obligation.id, status, reason, tuple(refs)))
    # The denominator is the task's obligations, NEVER the Rubric's check count.
    per_obligation = tuple((o.id, _aggregate([r.status for r in results if r.obligation_id == o.id]))
                           for o in task.obligations)
    critical_ids = {o.id for o in task.obligations if o.critical}
    status = _aggregate([s for oid, s in per_obligation if oid in critical_ids])
    return ValidationReport(
        VERSION, task.content_hash, artifact.content_hash, rubric.pipeline_hash,
        tuple(instances), tuple(results), per_obligation, status,
        artifact.provenance_kind, artifact.provenance_complete, artifact.historical_only,
        ("Replay only: no model calls, Research, new execution, calibration or Skill admission.",
         "Pass is bounded to recorded observations, not proof of complete correctness.",
         "Hashes establish content binding, not authentic execution or independent audit truth.",
         "Unknown, coverage and cost are separate quantities; no unknown-monotonicity gate.",
         "Fixture and exposed historical replay are not evidence of method effectiveness."),
    )


def metrics(report: ValidationReport) -> dict:
    statuses = [status for _, status in report.obligation_results]
    counts = {status: statuses.count(status) for status in ("pass", "fail", "unknown")}
    return {
        "unit": "task_obligation", "obligations": len(statuses), **counts,
        "coverage": (counts["pass"] + counts["fail"]) / len(statuses) if statuses else 0.0,
        "check_instances": len(report.checks),
        "not_applicable_checks": sum(c.status == "not_applicable" for c in report.checks),
        "model_calls": 0, "retrievals": 0, "new_executions": 0,
        "formal_effect_estimate": False,
    }
