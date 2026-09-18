"""Small immutable JSON replay entry; audit data never share the input schema."""
from __future__ import annotations

import json
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import write_immutable_json

from . import VERSION
from .engine import fixed_rubric, metrics, validate
from .models import ArtifactRecord, EvidenceRecord, GateDecision, TaskContract, require
from .partitions import PartitionEntry, PartitionManifest
from .views import bind, verifier_view


def partition_entry(task, artifact):
    return PartitionEntry(artifact.content_hash, task.original_task_id, task.family_id, task.project_id,
                          task.partition, artifact.provenance_kind, artifact.provenance_complete, artifact.historical_only)


def case_record(task, artifact, evidence, manifest=None):
    bind(task, artifact, evidence)
    manifest = PartitionManifest() if manifest is None else manifest
    manifest.register(partition_entry(task, artifact))
    return seal({"version": VERSION, "task": task.to_dict(), "artifact": artifact.to_dict(),
                 "evidence": [e.to_dict() for e in evidence], "partition_manifest": manifest.to_dict()})


def read_case(path):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink replay input unsupported")
    require(path.is_file() and path.stat().st_size <= 16 * 1024 * 1024, "Missing or oversized replay case")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON field")
            result[key] = value
        return result

    def finite(_):
        raise ValueError("Nonfinite replay JSON")

    data = verify(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=finite))
    require(set(data) == {"version", "task", "artifact", "evidence", "partition_manifest", "record_hash"}
            and data["version"] == VERSION, "Unexpected replay fields; H is not a replay input")
    task, artifact = TaskContract.from_dict(data["task"]), ArtifactRecord.from_dict(data["artifact"])
    require(type(data["evidence"]) is list, "Expected evidence array")
    evidence = tuple(EvidenceRecord.from_dict(row) for row in data["evidence"])
    manifest = PartitionManifest.from_dict(data["partition_manifest"])
    require(manifest.get(artifact.content_hash) == partition_entry(task, artifact), "Manifest differs from actual record")
    bind(task, artifact, evidence)
    return task, artifact, evidence, manifest


def _write(root, name, value):
    path = Path(root) / name
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink replay output unsupported")
    write_immutable_json(path, value)


def run_case(task, artifact, evidence, *, output, manifest=None):
    rubric = fixed_rubric()
    report = validate(task, artifact, evidence, rubric)
    case = case_record(task, artifact, evidence, manifest)
    _write(output, "case.json", case)
    _write(output, "rubric.json", rubric.sealed())
    _write(output, "verifier_view.json", verifier_view(task, artifact, evidence))
    _write(output, "report.json", report.sealed())
    summary = {"version": VERSION, "status": report.status, "metrics": metrics(report),
               "case_hash": case["record_hash"], "report_hash": report.content_hash,
               "source_kind": artifact.provenance_kind, "historical_only": artifact.historical_only,
               "provenance_complete": artifact.provenance_complete,
               "verifier_gate": GateDecision("verifier", "pending", rubric.pipeline_hash).to_dict(),
               "skill_gate": GateDecision("skill", "pending", rubric.pipeline_hash).to_dict()}
    _write(output, "summary.json", seal(summary))
    return summary


def save_host_audit(output, audit):
    _write(output, "host_only/audit.json", seal(audit))
