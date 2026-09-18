"""Host-only, common-obligation verifier comparison and finite-data admission.

No function in this module constructs a model prompt or executes an artifact.
Hashes bind supplied records; they do not authenticate runs or make H infallible.
The ledger prevents accidental reuse within a study directory, not a hostile host
from copying data into a fresh directory. Freeze the directory with the protocol.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, fields
from pathlib import Path

from skillopt.validator_pilot.api import digest, write_immutable_json

from .models import PARTITIONS, PROVENANCES, STATUSES, Record, exact_fields, hash_text, require, text
from .partitions import PartitionManifest


@dataclass(frozen=True)
class CalibrationRow(Record):
    """One common obligation, NOT one verifier-specific generated test.

    ``applicable`` and ``near_miss`` are host adjudications, not model/router
    features. The same contract-obligation universe must appear in both arms.
    Nonapplicable slots represent preregistered applicability controls, not new
    task obligations. An applicable obligation marked NA is uncovered, not pass.
    """
    task_id: str
    original_task_id: str
    family_id: str
    project_id: str
    partition: str
    task_hash: str
    artifact_record_hash: str
    repeat: int
    condition: str
    obligation_id: str
    verifier_status: str
    audit_status: str
    applicable: bool
    near_miss: bool
    provenance_kind: str
    provenance_complete: bool
    historical_only: bool
    rubric_pipeline_hash: str
    report_hash: str
    audit_hash: str

    def __post_init__(self):
        for name in ("task_id", "original_task_id", "family_id", "obligation_id"):
            text(getattr(self, name), maximum=512)
        text(self.project_id, maximum=512, empty=True)
        for name in ("task_hash", "artifact_record_hash", "rubric_pipeline_hash", "report_hash", "audit_hash"):
            hash_text(getattr(self, name))
        require(self.partition in PARTITIONS, "Unknown calibration purpose")
        require(self.provenance_kind in PROVENANCES, "Unknown calibration provenance")
        require(self.verifier_status in STATUSES, "Unknown verifier status")
        require(self.audit_status in {"pass", "fail", "unknown"}, "Unknown host audit status")
        require(self.condition in {"no_skill", "current", "candidate"}, "Paired condition required")
        require(type(self.repeat) is int and self.repeat >= 0, "Nonnegative repeat required")
        for name in ("applicable", "near_miss", "provenance_complete", "historical_only"):
            require(type(getattr(self, name)) is bool, "Explicit host booleans required")
        require(self.applicable or self.audit_status == "unknown", "Inapplicable slot has no correctness label")

    @property
    def identity(self):
        return self.task_hash, self.repeat, self.condition, self.obligation_id

    @property
    def natural(self):
        return self.provenance_kind == "model" and self.provenance_complete and not self.historical_only

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class ActualCost(Record):
    """Measured costs, not claimed equality of budgets or model calls."""
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retrievals: int = 0
    executions: int = 0
    execution_seconds: float = 0.0
    failures: int = 0

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "execution_seconds":
                require(type(value) in {int, float} and math.isfinite(value) and value >= 0,
                        "Finite nonnegative execution cost required")
            else:
                require(type(value) is int and value >= 0, "Nonnegative measured cost required")

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class GateConfig(Record):
    """All thresholds must be declared before reading calibration outcomes.

    Counts are pilot eligibility, not statistical power or a safety guarantee.
    Risk differences use common audited obligations. Unknown is reported and
    bounded through coverage, never forbidden simply because it increased.
    """
    min_independent_families: int
    min_natural_errors: int
    min_natural_correct: int
    min_near_miss: int
    min_coverage: float
    max_false_rejection_increase: float
    max_near_miss_misuse_increase: float
    min_net_new_detection: int

    def __post_init__(self):
        for name in ("min_independent_families", "min_natural_errors", "min_natural_correct", "min_near_miss"):
            require(type(getattr(self, name)) is int and getattr(self, name) >= 1,
                    "Positive independent/sample minimum required")
        require(type(self.min_net_new_detection) is int and self.min_net_new_detection >= 1,
                "Verifier admission requires positive incremental natural detection")
        for name in ("min_coverage", "max_false_rejection_increase", "max_near_miss_misuse_increase"):
            value = getattr(self, name)
            require(type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1,
                    "Risk and coverage thresholds must be in [0, 1]")

    @classmethod
    def from_dict(cls, value):
        return cls(**exact_fields(cls, value))


@dataclass(frozen=True)
class FreezeDeclaration(Record):
    """Declaration for a reusable pipeline, not a task-specific test list.

    All compared pipelines must be listed before the first calibration. Their
    declarations share a batch; later revisions cannot reuse consumed families.
    This records a preregistration assertion, not cryptographic proof of timing.
    """
    proposal_hash: str
    pipeline_hash: str
    baseline_pipeline_hash: str
    comparison_pipeline_hashes: tuple[str, ...]
    protocol_hash: str
    config_hash: str
    development_manifest_hash: str
    development_data_hash: str
    development_tasks: tuple[str, ...]
    development_families: tuple[str, ...]

    def __post_init__(self):
        for name in ("proposal_hash", "pipeline_hash", "baseline_pipeline_hash", "protocol_hash", "config_hash",
                     "development_manifest_hash", "development_data_hash"):
            hash_text(getattr(self, name))
        for name in ("comparison_pipeline_hashes", "development_tasks", "development_families"):
            values = getattr(self, name)
            require(type(values) is tuple and values and tuple(sorted(set(values))) == values,
                    "Freeze identities must be nonempty, unique and sorted")
            for value in values:
                hash_text(value) if name == "comparison_pipeline_hashes" else text(value, maximum=512)
        require(self.pipeline_hash in self.comparison_pipeline_hashes, "Pipeline absent from frozen comparison batch")
        require(self.baseline_pipeline_hash not in self.comparison_pipeline_hashes,
                "Baseline must differ from adaptive pipelines")

    @property
    def batch_hash(self):
        return digest({k: v for k, v in self.to_dict().items() if k not in {"proposal_hash", "pipeline_hash"}})

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        for name in ("comparison_pipeline_hashes", "development_tasks", "development_families"):
            data[name] = tuple(data[name])
        return cls(**data)


@dataclass(frozen=True)
class VerifierDecision(Record):
    status: str
    rubric_pipeline_hash: str
    proposal_hash: str
    freeze_hash: str
    config_hash: str
    calibration_manifest_hash: str
    comparison_hash: str
    reasons: tuple[str, ...]
    calibration_family_ids: tuple[str, ...]
    scope_status: str = "calibration_evidence_only_no_deployment_authority"
    limitation: str = "Finite calibration evidence only; no arbitrary-task or cross-domain safety guarantee."

    def __post_init__(self):
        require(self.status in {"accepted", "rejected", "pending"}, "Invalid Verifier Gate decision")
        for name in ("rubric_pipeline_hash", "proposal_hash", "freeze_hash", "config_hash", "calibration_manifest_hash",
                     "comparison_hash"):
            hash_text(getattr(self, name))
        require(type(self.reasons) is tuple and self.reasons, "Decision needs explicit reasons")
        require(type(self.calibration_family_ids) is tuple, "Typed calibration family identities required")
        for value in (*self.reasons, *self.calibration_family_ids):
            text(value, maximum=2000)
        text(self.limitation, maximum=2000)
        require(self.scope_status == "calibration_evidence_only_no_deployment_authority",
                "Calibration checkpoint cannot grant Skill deployment or cross-domain authority")

    @classmethod
    def from_dict(cls, value):
        data = exact_fields(cls, value)
        for name in ("reasons", "calibration_family_ids"):
            data[name] = tuple(data[name])
        return cls(**data)


_VERIFIER_FIELDS = {"verifier_status", "rubric_pipeline_hash", "report_hash"}


def _index(rows, manifest, purpose):
    require(purpose in {"development", "verifier_calibration", "verifier_audit"},
            "Verifier comparison cannot consume Skill confirmation or final data")
    require(type(manifest) is PartitionManifest, "Partition manifest required")
    manifest.validate()
    indexed, artifacts, tasks, universes, record_owners = {}, {}, {}, defaultdict(dict), {}
    for row in rows:
        require(type(row) is CalibrationRow, "Typed host calibration rows required")
        require(row.partition == purpose, "Calibration row has a different data purpose")
        require(row.identity not in indexed, "Duplicate common obligation; checks/repeats cannot inflate rows")
        entry = manifest.get(row.artifact_record_hash)
        require((entry.original_task_id, entry.near_duplicate_family, entry.project_id, entry.partition,
                 entry.provenance_kind, entry.provenance_complete, entry.legacy_exposed) ==
                (row.original_task_id, row.family_id, row.project_id, row.partition, row.provenance_kind,
                 row.provenance_complete, row.historical_only), "Row provenance differs from partition manifest")
        task_metadata = (row.task_id, row.original_task_id, row.family_id, row.project_id)
        require(tasks.setdefault(row.task_hash, task_metadata) == task_metadata, "Task identity changed between obligations")
        artifact_key = row.task_hash, row.repeat, row.condition
        require(record_owners.setdefault(row.artifact_record_hash, artifact_key) == artifact_key,
                "One artifact record cannot be relabelled as another condition/repeat/task")
        artifact_metadata = row.artifact_record_hash, row.report_hash, row.audit_hash
        require(artifacts.setdefault(artifact_key, artifact_metadata) == artifact_metadata,
                "Artifact/report/audit identity changed between obligations")
        universes[row.task_hash].setdefault(artifact_key, set()).add((row.obligation_id, row.applicable, row.near_miss))
        indexed[row.identity] = row
    for by_artifact in universes.values():
        require(len({frozenset(v) for v in by_artifact.values()}) <= 1,
                "Conditions/repeats must retain a common task-obligation universe")
    return indexed


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _summary(rows):
    applicable = [r for r in rows if r.applicable]
    errors = [r for r in applicable if r.audit_status == "fail"]
    correct = [r for r in applicable if r.audit_status == "pass"]
    near_miss = [r for r in rows if r.near_miss and not r.applicable]
    detected = sum(r.verifier_status == "fail" for r in errors)
    false_rejected = sum(r.verifier_status == "fail" for r in correct)
    known = sum(r.verifier_status in {"pass", "fail"} for r in applicable)
    return {
        "common_obligation_rows": len(rows),
        "task_count": len({r.original_task_id for r in rows}),
        "independent_family_count": len({r.family_id for r in rows}),
        "artifact_count": len({r.artifact_record_hash for r in rows}),
        "statuses": dict(sorted(Counter(r.verifier_status for r in rows).items())),
        "error_detection": _ratio(detected, len(errors)),
        "false_rejection": _ratio(false_rejected, len(correct)),
        "near_miss_misuse": _ratio(sum(r.verifier_status in {"pass", "fail"} for r in near_miss), len(near_miss)),
        "coverage": _ratio(known, len(applicable)),
        "unknown": _ratio(sum(r.verifier_status == "unknown" for r in applicable), len(applicable)),
        "applicable_marked_not_applicable": sum(r.verifier_status == "not_applicable" for r in applicable),
        "audit_unknown": sum(r.audit_status == "unknown" for r in applicable),
        "audited_error_family_count": len({r.family_id for r in errors}),
        "audited_correct_family_count": len({r.family_id for r in correct}),
        "near_miss_family_count": len({r.family_id for r in near_miss}),
    }


def _aggregate(rows, field):
    values = [getattr(r, field) for r in rows if r.applicable]
    if not values:
        return "unknown"
    if "fail" in values:
        return "fail"
    return "pass" if all(v == "pass" for v in values) else "unknown"


def _direction(before, after):
    if "unknown" in {before, after}:
        return "uncertain"
    if before == after:
        return "unchanged"
    return "repair" if after == "pass" else "regression"


def paired_diagnostics(rows):
    """Host-only labels. Repeats remain visible, not independent sample claims."""
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        groups[(row.task_hash, row.repeat)][row.condition].append(row)
    records, categories, agreements = [], Counter(), Counter()
    for (task_hash, repeat), arms in sorted(groups.items()):
        statuses = {arm: {"verifier": _aggregate(arms.get(arm, ()), "verifier_status"),
                          "audit": _aggregate(arms.get(arm, ()), "audit_status")}
                    for arm in ("no_skill", "current", "candidate")}
        h = [statuses[arm]["audit"] for arm in ("no_skill", "current", "candidate")]
        category = ("uncertain" if "unknown" in h else
                    "skill_related_regression" if h[2] == "fail" and "pass" in h[:2] else
                    "skill_repair" if h[2] == "pass" and "fail" in h[:2] else
                    "shared_error" if all(v == "fail" for v in h) else "shared_success")
        comparisons = {}
        for before, after in (("no_skill", "current"), ("no_skill", "candidate"), ("current", "candidate")):
            v = _direction(statuses[before]["verifier"], statuses[after]["verifier"])
            audit = _direction(statuses[before]["audit"], statuses[after]["audit"])
            agreement = "unknown" if "uncertain" in {v, audit} else "agree" if v == audit else "disagree"
            comparisons[f"{after}_vs_{before}"] = {"verifier_direction": v, "audit_direction": audit,
                                                    "agreement": agreement}
            agreements[agreement] += 1
        categories[category] += 1
        records.append({"task_hash": task_hash, "repeat": repeat, "category": category,
                        "statuses": statuses, "comparisons": comparisons,
                        "missing_conditions": sorted({"no_skill", "current", "candidate"} - set(arms)),
                        "report_hashes": sorted({r.report_hash for group in arms.values() for r in group}),
                        "audit_hashes": sorted({r.audit_hash for group in arms.values() for r in group})})
    return {"task_repeat_count": len(records), "categories": dict(sorted(categories.items())),
            "direction_agreement": dict(sorted(agreements.items())), "records": records}


def evaluate_comparison(fixed_rows, candidate_rows, *, manifest, purpose="verifier_audit",
                        fixed_cost=None, candidate_cost=None):
    """Pure replay comparison; has no authority and cannot update a verifier.

    Pass the whole frozen study manifest, not a freshly relabelled audit subset:
    its Stage-1 grouping checks reject development/calibration/audit overlaps.
    Rows are restricted to ``purpose``; other registry entries remain host-only.
    """
    left, right = _index(fixed_rows, manifest, purpose), _index(candidate_rows, manifest, purpose)
    require(set(left) == set(right), "Verifier arms must cover exactly the same common obligations")
    for key in left:
        a, b = left[key].to_dict(), right[key].to_dict()
        require({k: v for k, v in a.items() if k not in _VERIFIER_FIELDS} ==
                {k: v for k, v in b.items() if k not in _VERIFIER_FIELDS},
                "Paired artifact, audit, condition or obligation identity mismatch")
    for group in (left, right):
        require(len({r.rubric_pipeline_hash for r in group.values()}) <= 1,
                "A comparison arm cannot change the reusable verifier pipeline per task")
    natural_keys = sorted(key for key in left if left[key].natural)
    a, b = [left[k] for k in natural_keys], [right[k] for k in natural_keys]
    missed = [key for key in natural_keys if left[key].applicable and left[key].audit_status == "fail"
              and left[key].verifier_status != "fail"]
    newly = [key for key in missed if right[key].verifier_status == "fail"]
    lost = [key for key in natural_keys if left[key].applicable and left[key].audit_status == "fail"
            and left[key].verifier_status == "fail" and right[key].verifier_status != "fail"]
    families = sorted({r.family_id for r in a})
    costs = (fixed_cost, candidate_cost)
    require(all(c is None or type(c) is ActualCost for c in costs), "Typed actual costs required")
    return {
        "version": "skill-validation-calibration-v1", "purpose": purpose,
        "manifest_hash": manifest.to_dict()["manifest_hash"],
        "fixed_pipeline_hash": next(iter(left.values())).rubric_pipeline_hash if left else None,
        "candidate_pipeline_hash": next(iter(right.values())).rubric_pipeline_hash if right else None,
        "paired_data_hash": digest([left[k].to_dict() for k in sorted(left)]),
        "candidate_data_hash": digest([right[k].to_dict() for k in sorted(right)]),
        "full_natural": {"fixed": _summary(a), "candidate": _summary(b)},
        "diagnostic_only": {"fixed": _summary([r for r in left.values() if not r.natural]),
                            "candidate": _summary([r for r in right.values() if not r.natural])},
        "natural_old_missed_subset": {"prevalence_all_natural_obligations": _ratio(len(missed), len(a)),
            "prevalence_natural_audited_errors": _ratio(len(missed), sum(r.applicable and r.audit_status == "fail" for r in a)),
            "candidate_detection": _ratio(len(newly), len(missed))},
        "new_detection_count": len(newly), "lost_detection_count": len(lost),
        "net_new_detection": len(newly) - len(lost),
        "new_detection_evidence": [{"identity": list(k), "fixed_report_hash": left[k].report_hash,
                                    "candidate_report_hash": right[k].report_hash, "audit_hash": right[k].audit_hash}
                                   for k in newly],
        "per_family": {family: {"fixed": _summary([r for r in a if r.family_id == family]),
                                "candidate": _summary([r for r in b if r.family_id == family])} for family in families},
        "paired_diagnostics": {"fixed": paired_diagnostics(a), "candidate": paired_diagnostics(b)},
        "actual_cost": {"fixed": costs[0].to_dict() if costs[0] is not None else None,
                        "candidate": costs[1].to_dict() if costs[1] is not None else None},
        "authority": "none: descriptive comparison, not Verifier Gate acceptance",
    }


def _safe_path(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink calibration ledger unsupported")
    return path


def register_freeze(freeze, *, development_manifest, ledger_dir):
    """Persist the declared proposal before calibration; no model/H access."""
    require(type(freeze) is FreezeDeclaration, "Typed freeze declaration required")
    require(type(development_manifest) is PartitionManifest, "Development manifest required")
    entries = development_manifest.entries
    require(entries and all(e.partition == "development" for e in entries), "Freeze needs development-only manifest")
    require(freeze.development_manifest_hash == development_manifest.to_dict()["manifest_hash"], "Development manifest mismatch")
    require(freeze.development_tasks == tuple(sorted({e.original_task_id for e in entries}))
            and freeze.development_families == tuple(sorted({e.near_duplicate_family for e in entries})),
            "Freeze must bind all development tasks and near-duplicate families")
    path = _safe_path(Path(ledger_dir) / "freezes" / f"{freeze.pipeline_hash}.json")
    write_immutable_json(_safe_path(path.with_suffix(".development.json")), development_manifest.to_dict())
    write_immutable_json(path, freeze.sealed())
    return freeze


def calibrate(fixed_rows, candidate_rows, *, manifest, freeze, config, ledger_dir,
              fixed_cost=None, candidate_cost=None):
    """One frozen calibration batch; audit/final outcomes never approve anything.

    A shared preregistered batch allows multiple frozen verifier arms to use the
    same panel once. Every consumed original task/family is locked against a new
    batch, even if its manifest is subsequently extended or reordered.
    """
    require(type(config) is GateConfig and type(freeze) is FreezeDeclaration, "Frozen gate config/declaration required")
    require(freeze.config_hash == config.content_hash, "Gate thresholds changed after proposal freeze")
    path = _safe_path(Path(ledger_dir) / "freezes" / f"{freeze.pipeline_hash}.json")
    require(path.is_file() and json.loads(path.read_text(encoding="utf-8")) == freeze.sealed(),
            "Proposal must be registered before calibration")
    dev_path = _safe_path(path.with_suffix(".development.json"))
    require(dev_path.is_file(), "Registered development manifest is missing")
    development = PartitionManifest.from_dict(json.loads(dev_path.read_text(encoding="utf-8")))
    require(development.to_dict()["manifest_hash"] == freeze.development_manifest_hash,
            "Registered development manifest changed")
    require(development.project_disjoint == manifest.project_disjoint, "Partition grouping policy changed")
    # Reuse the Stage-1 split guard for all registered data, including project
    # disjointness when that was declared. Unrelated audit/final rows may coexist
    # in this host registry, but never enter the comparison/model view.
    PartitionManifest((*development.entries, *manifest.entries), project_disjoint=manifest.project_disjoint)
    left, right = tuple(fixed_rows), tuple(candidate_rows)
    report = evaluate_comparison(left, right, manifest=manifest, purpose="verifier_calibration",
                                 fixed_cost=fixed_cost, candidate_cost=candidate_cost)
    require({r.artifact_record_hash for r in left} ==
            {e.record_id for e in manifest.entries if e.partition == "verifier_calibration"},
            "Calibration must retain every artifact registered for this frozen panel")
    if left:
        require(report["fixed_pipeline_hash"] == freeze.baseline_pipeline_hash
                and report["candidate_pipeline_hash"] == freeze.pipeline_hash, "Calibration pipeline differs from frozen proposal")
    for row in left:
        require(row.original_task_id not in freeze.development_tasks and row.family_id not in freeze.development_families,
                "Development and calibration tasks/families overlap")
    owner = {"batch_hash": freeze.batch_hash,
             "data_hash": digest([{k: v for k, v in r.to_dict().items() if k not in _VERIFIER_FIELDS}
                                  for r in sorted(left, key=lambda r: r.identity)])}
    # Locks are intentionally tiny. A partially completed/crashed reservation is
    # conservative: replay the same batch, never free it to a different proposal.
    lock_paths = sorted({str(_safe_path(Path(ledger_dir) / "consumed" / f"{digest([kind, value])}.json"))
                         for row in left for kind, value in (("task", row.original_task_id), ("family", row.family_id))})
    for lock in lock_paths:
        lock_path = Path(lock)
        require(not lock_path.exists() or json.loads(lock_path.read_text(encoding="utf-8")) == owner,
                "Calibration task/family was already consumed by another frozen batch or panel")
    for lock in lock_paths:
        write_immutable_json(Path(lock), owner)

    baseline, candidate = report["full_natural"]["fixed"], report["full_natural"]["candidate"]
    insufficient = []
    for value, minimum, reason in (
        (candidate["independent_family_count"], config.min_independent_families, "insufficient_independent_natural_families"),
        (candidate["error_detection"]["denominator"], config.min_natural_errors, "insufficient_natural_errors"),
        (candidate["false_rejection"]["denominator"], config.min_natural_correct, "insufficient_natural_correct"),
        (candidate["near_miss_misuse"]["denominator"], config.min_near_miss, "insufficient_natural_near_miss"),
    ):
        if value < minimum:
            insufficient.append(reason)
    risks = []
    if candidate["coverage"]["value"] is not None and candidate["coverage"]["value"] < config.min_coverage:
        risks.append("coverage_below_frozen_floor")
    for metric, maximum, reason in (
        ("false_rejection", config.max_false_rejection_increase, "false_rejection_risk_increased"),
        ("near_miss_misuse", config.max_near_miss_misuse_increase, "near_miss_misuse_risk_increased"),
    ):
        if candidate[metric]["value"] is not None and candidate[metric]["value"] - baseline[metric]["value"] > maximum + 1e-12:
            risks.append(reason)
    if report["net_new_detection"] < config.min_net_new_detection:
        risks.append("no_sufficient_incremental_natural_detection")
    if insufficient:
        status, reasons = "pending", tuple(insufficient + risks)
    elif risks:
        status, reasons = "rejected", tuple(risks)
    else:
        status, reasons = "accepted", ("passed_preregistered_finite_calibration_constraints",)
    decision = VerifierDecision(status, freeze.pipeline_hash, freeze.proposal_hash, freeze.content_hash,
                               config.content_hash, manifest.to_dict()["manifest_hash"], digest(report), reasons,
                               tuple(sorted(report["per_family"])))
    write_immutable_json(_safe_path(Path(ledger_dir) / "decisions" / f"{freeze.content_hash}.json"), decision.sealed())
    return decision, report
