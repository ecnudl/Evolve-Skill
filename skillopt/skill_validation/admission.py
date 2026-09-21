"""Small, evidence-bound Coding Skill admission; no model calls or hidden oracle.

Engineering simulation exercises decisions but can NEVER authorize deployment.
Content hashes detect accidental substitution; they do not authenticate a host.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from .calibration import FreezeDeclaration, GateConfig, VerifierDecision
from .checks import CallableTask
from .models import KINDS, ArtifactRecord, Record, require
from .partitions import PartitionManifest


def _safe(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink admission ledger unsupported")
    return path


def _read(path):
    return json.loads(_safe(path).read_text(encoding="utf-8"))


def _sha(value):
    require(type(value) is str, "Skill text required")
    return hashlib.sha256(value.encode()).hexdigest()


def _calibration_constraints(metrics, config):
    left, right = metrics["fixed"], metrics["candidate"]
    insufficient = any(value < minimum for value, minimum in (
        (right["independent_family_count"], config.min_independent_families),
        (right["error_detection"]["denominator"], config.min_natural_errors),
        (right["false_rejection"]["denominator"], config.min_natural_correct),
        (right["near_miss_misuse"]["denominator"], config.min_near_miss),
    ))
    risk = right["coverage"]["value"] is None or right["coverage"]["value"] < config.min_coverage
    for key, maximum in (("false_rejection", config.max_false_rejection_increase),
                         ("near_miss_misuse", config.max_near_miss_misuse_increase)):
        a, b = left[key]["value"], right[key]["value"]
        risk |= a is None or b is None or b - a > maximum + 1e-12
    gain = right["error_detection"]["numerator"] - left["error_detection"]["numerator"]
    risk |= gain < config.min_net_new_detection
    return "pending" if insufficient else "rejected" if risk else "accepted"


def derive_authority(decision, comparison, freeze, config, *, calibration_manifest,
                     development_manifest, obligation_kinds, engineering_simulation=False):
    """Bind actual calibration objects to a *reusable* pipeline and limited scope.

    Simulation recomputes thresholds on explicitly non-natural diagnostics. It
    does not relabel fixture rows, alter VerifierDecision, or grant real rights.
    The host declares supported obligation kinds; calibration rows contain IDs,
    not kind annotations, so this declaration is NOT automatically semantically
    certified by calibration. The host must match it to the actual calibration
    task contracts. No domain generality follows.
    """
    require(type(decision) is VerifierDecision and type(freeze) is FreezeDeclaration
            and type(config) is GateConfig, "Typed calibration objects required")
    require(type(calibration_manifest) is PartitionManifest and type(development_manifest) is PartitionManifest,
            "Typed calibration/development manifests required")
    require(type(engineering_simulation) is bool, "Explicit simulation flag required")
    require(calibration_manifest.project_disjoint == development_manifest.project_disjoint,
            "Partition policy mismatch")
    PartitionManifest((*development_manifest.entries, *calibration_manifest.entries),
                      project_disjoint=calibration_manifest.project_disjoint)
    require(development_manifest.entries and all(e.partition == "development" for e in development_manifest.entries),
            "Development-only manifest required")
    require(calibration_manifest.entries and all(e.partition == "verifier_calibration" for e in calibration_manifest.entries),
            "Calibration-only manifest required")
    require(freeze.development_manifest_hash == development_manifest.to_dict()["manifest_hash"],
            "Development manifest differs from freeze")
    require(decision.freeze_hash == freeze.content_hash and decision.config_hash == config.content_hash
            and freeze.config_hash == config.content_hash and decision.proposal_hash == freeze.proposal_hash
            and decision.rubric_pipeline_hash == freeze.pipeline_hash, "Calibration freeze/config binding mismatch")
    require(decision.comparison_hash == digest(comparison) and comparison["purpose"] == "verifier_calibration"
            and comparison["candidate_pipeline_hash"] == freeze.pipeline_hash
            and comparison["fixed_pipeline_hash"] == freeze.baseline_pipeline_hash,
            "Calibration comparison binding mismatch")
    require(decision.calibration_manifest_hash == comparison["manifest_hash"]
            == calibration_manifest.to_dict()["manifest_hash"], "Calibration manifest binding mismatch")
    kinds = tuple(sorted(set(obligation_kinds)))
    require(kinds and set(kinds) <= KINDS, "Supported public obligation kinds required")
    computed = _calibration_constraints(comparison["full_natural"], config)
    require(decision.status == computed, "Verifier decision disagrees with frozen calibration constraints")
    require(comparison["full_natural"]["candidate"]["artifact_count"] ==
            sum(e.formal_eligible for e in calibration_manifest.entries),
            "Natural calibration counts disagree with original provenance")
    status = decision.status
    if engineering_simulation:
        require(all(e.provenance_kind == "fixture" and not e.legacy_exposed for e in calibration_manifest.entries),
                "Simulation requires explicitly fixture calibration, not fabricated natural provenance")
        status = "engineering_" + _calibration_constraints(comparison["diagnostic_only"], config)
    return seal({"version": "skill-admission-authority-v1", "status": status,
                 "pipeline_hash": freeze.pipeline_hash, "obligation_kinds": list(kinds),
                 "adapter_domain": "coding", "verifier_decision": decision.to_dict(),
                 "comparison_hash": digest(comparison), "verifier_freeze_hash": freeze.content_hash,
                 "calibration_manifest": calibration_manifest.to_dict(),
                 "development_manifest": development_manifest.to_dict(),
                 "engineering_simulation": engineering_simulation,
                 "deployment_authorized": False,
                 "obligation_scope_basis": "host_declared_matching_calibration_contracts_not_automatic_semantic_certification",
                 "limitation": "Verifier use authority only, not a Skill approval or cross-domain claim."})


def require_update_authority(authority, pipeline_hash, *, engineering_simulation=False):
    authority = verify(authority)
    require(authority["version"] == "skill-admission-authority-v1"
            and authority["pipeline_hash"] == pipeline_hash, "Verifier pipeline changed or authority invalid")
    require(authority["engineering_simulation"] is engineering_simulation,
            "Engineering authority cannot enter a real update/deployment path")
    expected = "engineering_accepted" if engineering_simulation else "accepted"
    require(authority["status"] == expected, "Verifier is not authorized: rejected/pending calibration blocks update and admission")
    return authority


@dataclass(frozen=True)
class ScopeRule(Record):
    """Only public obligations visible before solving; never host mechanism labels."""
    required_obligation_kinds: tuple[str, ...]
    forbidden_obligation_kinds: tuple[str, ...] = ()

    def __post_init__(self):
        require(self.required_obligation_kinds, "Scope must state a positive public condition")
        for values in (self.required_obligation_kinds, self.forbidden_obligation_kinds):
            require(type(values) is tuple and tuple(sorted(set(values))) == values and set(values) <= KINDS,
                    "Scope kinds must be supported, sorted and unique")
        require(not set(self.required_obligation_kinds) & set(self.forbidden_obligation_kinds), "Contradictory scope")

    def matches(self, task):
        require(type(task) is CallableTask, "Only the Coding adapter is supported")
        kinds = {o.kind for o in task.contract.obligations}
        return set(self.required_obligation_kinds) <= kinds and not set(self.forbidden_obligation_kinds) & kinds


@dataclass(frozen=True)
class SkillGateConfig(Record):
    min_target_families: int = 2
    min_retention_families: int = 2
    min_nonapplicable_families: int = 2
    min_coverage: float = 1.0
    min_net_wins: int = 1
    max_observed_losses: int = 0
    repeats: int = 1

    def __post_init__(self):
        for name in ("min_target_families", "min_retention_families", "min_nonapplicable_families", "min_net_wins", "repeats"):
            require(type(getattr(self, name)) is int and getattr(self, name) >= 1, "Positive frozen sample/repeat minimum required")
        require(type(self.max_observed_losses) is int and self.max_observed_losses >= 0, "Nonnegative loss limit required")
        require(type(self.min_coverage) in {float, int} and math.isfinite(self.min_coverage)
                and 0 <= self.min_coverage <= 1, "Coverage must be in [0, 1]")


def register_skill_freeze(*, parent_text, candidate_text, parent_version, candidate_version,
                          authority, scope, config, prior_manifest, confirmation_tasks,
                          ledger_dir, engineering_simulation=False):
    authority = require_update_authority(authority, authority["pipeline_hash"],
                                         engineering_simulation=engineering_simulation)
    require(type(scope) is ScopeRule and type(config) is SkillGateConfig, "Typed frozen scope/config required")
    require(type(prior_manifest) is PartitionManifest, "Prior partition registry required")
    required = PartitionManifest.from_dict(authority["development_manifest"]).entries
    required += PartitionManifest.from_dict(authority["calibration_manifest"]).entries
    require(all(prior_manifest.get(e.record_id) == e for e in required), "Prior registry must retain authority source data")
    require(not any(e.partition in {"skill_confirmation", "final"} for e in prior_manifest.entries),
            "Prior update registry cannot contain confirmation/final evidence")
    require(set(scope.required_obligation_kinds) <= set(authority["obligation_kinds"]), "Scope exceeds calibrated obligations")
    plan = []
    for task, region in confirmation_tasks:
        require(type(task) is CallableTask and task.contract.partition == "skill_confirmation",
                "Only skill_confirmation contracts may enter the frozen plan")
        require(region in {"target", "retention", "nonapplicable"}, "Unsupported region; cross-domain approval is not implemented")
        applicable = scope.matches(task)
        require(applicable == (region != "nonapplicable"), "Region conflicts with pre-execution public scope")
        require({o.kind for o in task.contract.obligations} <= set(authority["obligation_kinds"]),
                "Task includes obligations outside verifier authorization")
        require(not any(e.original_task_id == task.contract.original_task_id or e.near_duplicate_family == task.contract.family_id
                        for e in prior_manifest.entries), "Confirmation overlaps development/calibration tasks or families")
        plan.append({"task_hash": task.contract.content_hash, "callable_task_hash": task.content_hash,
                     "original_task_id": task.contract.original_task_id, "family_id": task.contract.family_id,
                     "region": region, "applicable": applicable})
    require(plan and len({p["task_hash"] for p in plan}) == len(plan)
            and len({p["original_task_id"] for p in plan}) == len(plan), "Unique confirmation tasks required")
    require(parent_version and candidate_version and parent_version != candidate_version,
            "Candidate needs a new explicit version")
    require(candidate_text.strip() and _sha(candidate_text) != _sha(parent_text),
            "Unchanged/empty Skill is not a new learning candidate")
    freeze = seal({"version": "skill-admission-freeze-v1", "authority_hash": authority["record_hash"],
                   "pipeline_hash": authority["pipeline_hash"], "scope": scope.to_dict(), "config": config.to_dict(),
                   "parent_skill_hash": _sha(parent_text), "candidate_skill_hash": _sha(candidate_text),
                   "parent_version": parent_version, "candidate_version": candidate_version,
                   "prior_manifest": prior_manifest.to_dict(), "plan": sorted(plan, key=lambda p: p["task_hash"]),
                   "engineering_simulation": engineering_simulation,
                   "fallback": "no_skill: current has no deployment authorization in this bounded adapter"})
    write_immutable_json(_safe(Path(ledger_dir) / "freezes" / (freeze["record_hash"] + ".json")), freeze)
    return freeze


def _status(report, task):
    require(set(report["obligations"]) == {o.id for o in task.contract.obligations}, "Common obligation universe changed")
    for obligation in task.contract.obligations:
        checks = [c["status"] for c in report["checks"] if c["obligation_id"] == obligation.id]
        expected = ("fail" if "fail" in checks else "unknown" if not checks or "unknown" in checks
                    or all(s == "not_applicable" for s in checks) else "pass")
        require(report["obligations"][obligation.id] == expected,
                "Obligation summary does not match its common evidence checks")
    states = [report["obligations"][o.id] for o in task.contract.obligations if o.critical]
    require(all(s in {"pass", "fail", "unknown", "not_applicable"} for s in states), "Unknown result semantics")
    return "fail" if "fail" in states else "pass" if states and all(s == "pass" for s in states) else "unknown"


def _paired(records, region, before, *, routed=False):
    rows = [r for r in records if r["region"] == region]
    counts, family = Counter(), defaultdict(list)
    for row in rows:
        a = row["statuses"][before]
        arm = "candidate" if not routed or row["applicable"] else "no_skill"
        b = row["statuses"][arm]
        outcome = "unknown" if "unknown" in {a, b} else "tie" if a == b else "win" if b == "pass" else "loss"
        counts[outcome] += 1
        family[row["family_id"]].append(None if outcome == "unknown" else 1 if outcome == "win" else -1 if outcome == "loss" else 0)
    signs = [1 if sum(v) > 0 else -1 if sum(v) < 0 else 0 for v in family.values() if None not in v]
    n = len(rows)
    return {"rows": n, "independent_families": len(family), "win": counts["win"], "loss": counts["loss"],
            "tie": counts["tie"], "unknown": counts["unknown"],
            "coverage": (n - counts["unknown"]) / n if n else None,
            "family_net_wins": sum(signs), "fully_known_families": len(signs)}


def decide_skill(entries, *, authority, freeze, config, manifest, ledger_dir, engineering_simulation=False):
    """Consume an independent confirmation panel once; final/H inputs unsupported."""
    authority = require_update_authority(authority, authority["pipeline_hash"],
                                         engineering_simulation=engineering_simulation)
    freeze = verify(freeze)
    require(freeze["authority_hash"] == authority["record_hash"] and freeze["pipeline_hash"] == authority["pipeline_hash"]
            and freeze["config"] == config.to_dict() and freeze["engineering_simulation"] is engineering_simulation,
            "Changed authority, configuration, pipeline or simulation mode")
    require(_read(Path(ledger_dir) / "freezes" / (freeze["record_hash"] + ".json")) == freeze,
            "Candidate/scope must be registered before confirmation")
    require(type(manifest) is PartitionManifest, "Frozen partition manifest required")
    prior = PartitionManifest.from_dict(freeze["prior_manifest"])
    require(prior.project_disjoint == manifest.project_disjoint, "Partition policy changed")
    PartitionManifest((*prior.entries, *manifest.entries), project_disjoint=manifest.project_disjoint)
    require(manifest.entries and all(e.partition == "skill_confirmation" for e in manifest.entries),
            "Final and non-confirmation data cannot authorize a Skill")
    plan = {p["task_hash"]: p for p in freeze["plan"]}
    records, used, pairs = [], set(), set()
    for entry in entries:
        require(set(entry) == {"task", "artifacts", "reports"}, "Only public confirmation task/artifact/reports are allowed")
        task, artifacts, reports = entry["task"], entry["artifacts"], entry["reports"]
        require(type(task) is CallableTask and task.contract.partition == "skill_confirmation", "Confirmation-only task required")
        task_plan = plan.get(task.contract.content_hash)
        require(task_plan and task_plan["callable_task_hash"] == task.content_hash, "Task absent from frozen scope/region plan")
        require(len(artifacts) == len(reports) == 3 and {a.condition for a in artifacts} == {"no_skill", "current", "candidate"},
                "Complete frozen three-condition panel required; unknown deliveries remain records")
        require(len({a.repeat for a in artifacts}) == 1, "Paired repeat mismatch")
        repeat = artifacts[0].repeat
        require(0 <= repeat < config.repeats and (task.contract.content_hash, repeat) not in pairs, "Repeated or unexpected pairing")
        pairs.add((task.contract.content_hash, repeat))
        reports = {verify(r)["artifact_record_hash"]: verify(r) for r in reports}
        statuses, refs = {}, []
        for artifact in artifacts:
            require(type(artifact) is ArtifactRecord and artifact.task_hash == task.contract.content_hash, "Artifact task mismatch")
            if artifact.condition != "no_skill":
                prefix = "parent" if artifact.condition == "current" else "candidate"
                require(artifact.skill_hash == freeze[prefix + "_skill_hash"]
                        and artifact.skill_version == freeze[prefix + "_version"], "Changed Skill cannot inherit approval evidence")
            assignment = manifest.get(artifact.content_hash)
            require((assignment.original_task_id, assignment.near_duplicate_family, assignment.project_id,
                     assignment.provenance_kind, assignment.provenance_complete, assignment.legacy_exposed) ==
                    (task.contract.original_task_id, task.contract.family_id, task.contract.project_id,
                     artifact.provenance_kind, artifact.provenance_complete, artifact.historical_only), "Artifact provenance/partition mismatch")
            report = reports.get(artifact.content_hash)
            require(report and report["task_hash"] == task.contract.content_hash
                    and report["callable_task_hash"] == task.content_hash
                    and report["pipeline_hash"] == authority["pipeline_hash"], "Report bound to different task/artifact/pipeline")
            for check in report["checks"]:
                require(check["status"] in {"pass", "fail", "unknown", "not_applicable"},
                        "Unsupported individual check status")
                require(check["status"] not in {"pass", "fail"} or check["evidence_refs"], "Known verdict needs execution evidence")
            statuses[artifact.condition] = _status(report, task)
            require(artifact.availability == "available" or statuses[artifact.condition] == "unknown", "Failed delivery is not semantic failure")
            refs.append(report["record_hash"])
            used.add(artifact.content_hash)
        records.append({**task_plan, "repeat": repeat, "statuses": statuses, "report_hashes": sorted(refs)})
    require(pairs == {(h, r) for h in plan for r in range(config.repeats)}, "Confirmation panel is incomplete; do not drop missing runs")
    require(used == {e.record_id for e in manifest.entries}, "Every registered confirmation artifact must remain in the panel")
    records.sort(key=lambda r: (r["task_hash"], r["repeat"]))
    owner = {"freeze_hash": freeze["record_hash"], "data_hash": digest(records)}
    locks = {_safe(Path(ledger_dir) / "consumed" / (digest([kind, value]) + ".json"))
             for p in plan.values() for kind, value in (("task", p["original_task_id"]), ("family", p["family_id"]))}
    for path in locks:
        require(not path.exists() or _read(path) == owner, "Confirmation task/family already consumed by another candidate or result")
    for path in sorted(locks):
        write_immutable_json(path, owner)
    raw = {region: {arm: _paired(records, region, arm) for arm in ("no_skill", "current")}
           for region in ("target", "retention", "nonapplicable")}
    routed = {region: {arm: _paired(records, region, arm, routed=True) for arm in ("no_skill", "current")}
              for region in raw}
    pending, risks = [], []
    if engineering_simulation:
        require(all(e.provenance_kind == "fixture" for e in manifest.entries), "Engineering simulation cannot mix natural labels")
    elif not all(e.formal_eligible for e in manifest.entries):
        pending.append("confirmation_has_diagnostic_only_or_incomplete_provenance")
    for region, minimum in (("target", config.min_target_families), ("retention", config.min_retention_families),
                            ("nonapplicable", config.min_nonapplicable_families)):
        for arm, metric in routed[region].items():
            if region == "nonapplicable" and arm == "current":
                continue  # Unapproved Current is not a deployed baseline.
            if metric["independent_families"] < minimum:
                pending.append(region + ":insufficient_independent_families")
            if metric["coverage"] is None or metric["coverage"] < config.min_coverage:
                pending.append(region + ":coverage_below_frozen_floor")
            if metric["loss"] > config.max_observed_losses:
                risks.append(region + ":observed_regression_vs_" + arm)
            if region == "target" and metric["family_net_wins"] < config.min_net_wins:
                risks.append("target:no_incremental_family_gain_vs_" + arm)
    action = "Pending" if pending else "Reject" if risks else "Restrict" if any(
        m["loss"] for m in raw["nonapplicable"].values()) else "Local Commit"
    approved = action in {"Local Commit", "Restrict"}
    deployed_records = records if approved else [{**r, "applicable": False} for r in records]
    deployed = {region: {arm: _paired(deployed_records, region, arm, routed=True)
                         for arm in ("no_skill", "current")} for region in raw}
    result = seal({"version": "skill-admission-decision-v1", "action": action,
                   "reasons": sorted(set(pending + risks)) or ["passed_frozen_finite_confirmation_constraints"],
                   "freeze_hash": freeze["record_hash"], "authority_hash": authority["record_hash"],
                   "pipeline_hash": authority["pipeline_hash"], "candidate_skill_hash": freeze["candidate_skill_hash"],
                   "candidate_version": freeze["candidate_version"], "scope": freeze["scope"],
                   "confirmation_manifest_hash": manifest.to_dict()["manifest_hash"], "raw_forced": raw,
                   "hypothetical_routed": routed, "decision_policy_replay": deployed, "records": records,
                   "engineering_simulation": engineering_simulation,
                   "deployment_authorized": approved and not engineering_simulation,
                   "deployment": {"on_scope": "candidate" if approved else "no_skill", "outside_scope": "no_skill",
                                  "fallback_rate": sum(not r["applicable"] or not approved for r in records) / len(records)},
                   "limitation": "Coding-only finite-data decision, not cross-domain safety or statistical sufficiency; current has no inherited authorization."})
    write_immutable_json(_safe(Path(ledger_dir) / "decisions" / (freeze["record_hash"] + ".json")), result)
    return result


def select_skill(task, candidate_text, candidate_version, decision, *, authority, pipeline_hash,
                 engineering_simulation=False):
    """Pre-execution selection only; no answer, outcome, H or host mechanism input.

    Final task *contracts* may be routed for frozen evaluation. Their outcomes
    cannot enter admission. This adapter never inherits an old Current approval.
    """
    require(type(task) is CallableTask, "Only Coding execution is supported")
    decision = verify(decision)
    require(decision["version"] == "skill-admission-decision-v1", "Unsupported Skill decision")
    authority = require_update_authority(authority, pipeline_hash, engineering_simulation=engineering_simulation)
    require(decision["authority_hash"] == authority["record_hash"] and decision["pipeline_hash"] == pipeline_hash,
            "Skill decision belongs to another verifier authority/pipeline")
    require(decision["engineering_simulation"] is engineering_simulation,
            "Engineering decision cannot authorize real deployment")
    require(_sha(candidate_text) == decision["candidate_skill_hash"]
            and candidate_version == decision["candidate_version"], "Changed Skill cannot inherit deployment authority")
    rule = ScopeRule(tuple(decision["scope"]["required_obligation_kinds"]),
                     tuple(decision["scope"]["forbidden_obligation_kinds"]))
    approved = decision["action"] in {"Local Commit", "Restrict"}
    require(engineering_simulation or not approved or decision["deployment_authorized"], "Missing real deployment authority")
    supported = {o.kind for o in task.contract.obligations} <= set(authority["obligation_kinds"])
    use = approved and supported and rule.matches(task)
    return seal({"condition": "candidate" if use else "no_skill", "skill_text": candidate_text if use else "",
            "skill_version": candidate_version if use else "none",
            "skill_hash": _sha(candidate_text if use else ""), "decision_hash": decision["record_hash"],
            "engineering_simulation": engineering_simulation,
            "deployment_authorized": use and not engineering_simulation,
            "reason": "approved_public_scope" if use else "clean_base_fallback_outside_scope_or_unapproved"})
