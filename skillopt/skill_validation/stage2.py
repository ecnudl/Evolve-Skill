"""Small, restartable Stage-2 engineering study; no Skill updates or deployment.

The host owns the frozen pool, audit labels and condition map. Only a typed
development projection crosses into the proposal model. This bounded callable
adapter does not collect repository benchmarks or authenticate imported labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from .calibration import (
    ActualCost,
    CalibrationRow,
    FreezeDeclaration,
    GateConfig,
    calibrate,
    evaluate_comparison,
    register_freeze,
)
from .checks import CallableTask, ExecutionCache, compare_frozen, pipeline_hash, validate_callable
from .models import ArtifactRecord, EvidenceRecord, Observation, RubricVersion, require
from .partitions import PartitionEntry, PartitionManifest
from .research import BoundedResearch, ResearchBudget, ResearchResult, fixed_rubric
from .sandbox import DockerExecutor
from .views import DevelopmentGap, bind, research_development_view

ARMS = ("fixed", "adaptive_no_research", "adaptive_research")
PURPOSES = ("development", "verifier_calibration", "verifier_audit")
CONTROL = "__input_preservation_applicability_control__"


def _path(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink study output/input unsupported")
    return path


def _read(path):
    path = _path(path)
    require(path.stat().st_size <= 32_000_000, "Study JSON exceeds bounded import size")
    return verify(json.loads(path.read_text(encoding="utf-8")))


def _write(path, value):
    write_immutable_json(_path(path), value)


def _execution_totals(root):
    records, pending = [], []
    for directory in (root / "development_execution", root / "execution"):
        for path in directory.rglob("*.json"):
            record = _read(path)
            if path.parent.name == "intents":
                if not path.parent.parent.joinpath(path.name).exists():
                    pending.append(record["record_hash"])
            else:
                verify(record["execution"])
                records.append(record["execution"])
    return {"executor_requests_including_development_and_shared_preparation": len(records),
            "observed_executions": sum(r["status"] == "observed" for r in records),
            "unsupported": sum(r["status"] == "unsupported" for r in records),
            "execution_errors": sum(r["status"] == "execution_error" for r in records),
            "interrupted_without_receipt": len(pending),
            "execution_seconds": sum(r.get("duration_seconds", 0) for r in records)}


def _manifest(pool):
    entries = []
    identities = set()
    for row in pool:
        require(type(row) is dict and set(row) == {"task", "artifacts", "audit", "near_miss"}, "Unexpected frozen pool fields")
        task, artifacts = row["task"], row["artifacts"]
        require(type(task) is CallableTask and task.contract.partition in PURPOSES, "Only Stage-2 data purposes allowed")
        require(type(artifacts) is tuple and len(artifacts) == 3
                and {a.condition for a in artifacts} == {"no_skill", "current", "candidate"}
                and len({a.repeat for a in artifacts}) == 1, "Frozen complete three-condition tuple required")
        require(type(row["near_miss"]) is bool and type(row["audit"]) is dict, "Host audit and applicability labels required")
        require(set(row["audit"]) == {a.content_hash for a in artifacts}, "Audit must match exact frozen artifacts")
        ids = {o.id for o in task.contract.obligations}
        require(CONTROL not in ids, "Reserved applicability-control slot")
        for artifact in artifacts:
            bind(task.contract, artifact, ())
            identity = (task.contract.task_id, artifact.repeat, artifact.condition)
            require(identity not in identities, "Duplicate frozen task/repeat/condition")
            identities.add(identity)
            labels = row["audit"][artifact.content_hash]
            require(type(labels) is dict and set(labels) == ids and all(v in {"pass", "fail", "unknown"} for v in labels.values()),
                    "Audit requires the same full task-obligation universe, including unknown")
            c = task.contract
            entries.append(PartitionEntry(artifact.content_hash, c.original_task_id, c.family_id, c.project_id,
                                          c.partition, artifact.provenance_kind, artifact.provenance_complete, artifact.historical_only))
    require({r["task"].contract.partition for r in pool} == set(PURPOSES), "Development, calibration and independent audit required")
    return PartitionManifest(entries)


def export_pool(pool, root):
    """Separate persisted public records and host-only truth before any proposal."""
    _manifest(pool)
    public, private = [], []
    for row in pool:
        key = digest([row["task"].content_hash, [a.content_hash for a in row["artifacts"]]])
        public.append({"id": key, "task": row["task"].to_dict(), "artifacts": [a.to_dict() for a in row["artifacts"]]})
        private.append({"id": key, "audit": row["audit"], "near_miss": row["near_miss"]})
    root = _path(root)
    _write(root / "pool.json", seal({"rows": public, "warning": "Host metadata; not a model view"}))
    _write(root / "host_only" / "audit.json", seal({"rows": private, "public_pool_hash": digest(public)}))


def import_pool(root):
    root = _path(root)
    public = _read(root / "pool.json")
    private = _read(root / "host_only" / "audit.json")
    require(private["public_pool_hash"] == digest(public["rows"]), "Audit belongs to another frozen pool")
    audit = {r["id"]: r for r in private["rows"]}
    require(len(audit) == len(private["rows"]) == len(public["rows"])
            and set(audit) == {r["id"] for r in public["rows"]}, "Duplicate or missing frozen pool row")
    result = []
    for row in public["rows"]:
        task = CallableTask.from_dict(row["task"])
        artifacts = tuple(ArtifactRecord.from_dict(a) for a in row["artifacts"])
        require(row["id"] == digest([task.content_hash, [a.content_hash for a in artifacts]]), "Frozen pool identity mismatch")
        result.append({"task": task, "artifacts": artifacts, "audit": audit[row["id"]]["audit"],
                       "near_miss": audit[row["id"]]["near_miss"]})
    _manifest(result)
    return result


def _development(pool, executor, root, budget):
    views, reports = [], []
    for row in pool:
        task = row["task"]
        if task.contract.partition != "development":
            continue
        cache = ExecutionCache(executor, root / "development_execution" / task.content_hash, max_executions=budget)
        for artifact in row["artifacts"]:
            report = validate_callable(task, artifact, fixed_rubric(), cache)
            reports.append(report)
            # Only observable public test outcomes are projected, never H labels.
            observations = tuple(Observation("public-" + str(i), o.id, "public_test", passed=report["obligations"][o.id] == "pass")
                                 for i, o in enumerate(task.contract.obligations)
                                 if o.kind == "requested_behavior" and report["obligations"][o.id] in {"pass", "fail"})
            evidence = EvidenceRecord(task.contract.content_hash, artifact.artifact_hash, artifact.content_hash,
                                      artifact.repeat, "public", "observed" if observations else "unsupported", observations,
                                      "stage2-public-check-report:" + report["record_hash"], report["record_hash"], artifact.provenance_kind)
            gaps = []
            labels = row["audit"][artifact.content_hash]
            for obligation in task.contract.obligations:
                status, truth = report["obligations"][obligation.id], labels[obligation.id]
                category = ("uncertainty" if status == "unknown" else "missed_error" if truth == "fail" and status != "fail"
                            else "false_rejection" if truth == "pass" and status == "fail" else None)
                if category:
                    gaps.append(DevelopmentGap(task.contract.content_hash, artifact.artifact_hash, obligation.id,
                                               category, "host-development-audit:" + digest(labels)))
            view = research_development_view(task.contract, artifact, (evidence,), gaps=tuple(gaps))
            view["anonymous_id"] = "item-" + digest(["public-presentation", artifact.content_hash])[:24]
            views.append(view)
    # Fixed order independent of condition and verifier; identity mapping stays host-side.
    return sorted(views, key=lambda v: v["anonymous_id"]), reports


def _proposal(research, arm, views, root, protocol_hash):
    path = root / "proposals" / (arm + ".json")
    request = {"arm": arm, "shared_evidence_hash": digest(views), "protocol_hash": protocol_hash}
    if path.exists():
        record = _read(path)
        require(record["request"] == request, "Proposal inputs changed; no calibration-set tuning on resume")
        data = record["result"]
        rubric = RubricVersion.from_dict(data["rubric"]) if data["rubric"] is not None else None
        return ResearchResult(data["status"], data["arm"], rubric, tuple(data["findings"]), tuple(data["sources"]),
                              data["costs"], tuple(data["trace"]), data["reason"], data["requires_calibration"])
    intent = path.with_suffix(".intent.json")
    if intent.exists():
        require(_read(intent)["request"] == request, "Interrupted proposal inputs changed")
        raise ValueError("Interrupted proposal without terminal receipt: retained for manual recovery, not retried")
    _write(intent, seal({"request": request}))
    result = research.propose(arm, fixed_rubric(), views)
    _write(path, seal({"request": request, "result": result.to_dict()}))
    return result


def _rows(row, reports):
    task = row["task"].contract
    result = []
    by_artifact = {r["artifact_record_hash"]: verify(r) for r in reports}
    for artifact in row["artifacts"]:
        report = by_artifact[artifact.content_hash]
        labels = row["audit"][artifact.content_hash]
        slots = [(o.id, report["obligations"][o.id], labels[o.id], True) for o in task.obligations]
        if row["near_miss"] and not any(o.kind == "input_preservation" for o in task.obligations):
            # Frozen host applicability control, not an added task requirement.
            checks = [c["status"] for c in report["checks"] if c["obligation_kind"] == "input_preservation"]
            misuse = next((s for s in checks if s in {"pass", "fail"}), None)
            control_status = misuse or ("unknown" if "unknown" in checks else "not_applicable")
            slots.append((CONTROL, control_status, "unknown", False))
        for oid, status, truth, applicable in slots:
            result.append(CalibrationRow(task.task_id, task.original_task_id, task.family_id, task.project_id, task.partition,
                task.content_hash, artifact.content_hash, artifact.repeat, artifact.condition, oid, status, truth,
                applicable, row["near_miss"], artifact.provenance_kind, artifact.provenance_complete, artifact.historical_only,
                report["pipeline_hash"], report["record_hash"], digest({"artifact": artifact.content_hash, "labels": labels})))
    return result


def run_study(pool, *, research, executor, output, transport_identity, gate_config=None,
              max_executions=192, common_evidence=False):
    """Freeze first, propose once, calibrate once, then independently audit.

Importers own provenance validation. A hash authenticates neither natural runs
nor audit truth. No result from audit is returned to the proposal model.
"""
    root = _path(output)
    manifest = _manifest(pool)
    config = gate_config or GateConfig(2, 2, 2, 2, 0.75, 0.0, 0.0, 1)
    source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
    protocol = seal({"version": "stage2-engineering-v1", "source": source, "manifest": manifest.to_dict(),
                     "transport": transport_identity, "budget": research.budget.to_dict(), "gate_config": config.to_dict(),
                     "max_executions_per_task_arm": max_executions, "common_evidence": common_evidence,
                     "executor_identity": executor.identity, "arm_order": list(ARMS),
                     "no_skill_updates": True, "calibration_is_not_deployment_authority": True})
    _write(root / "protocol.json", protocol)
    export_pool(pool, root / "frozen_pool")
    # Host-only development diagnostic before any model/executor request. This
    # does not tune thresholds, inspect held-out outcomes, or grant admission.
    from .panel import inspect_pool
    panel_preflight = inspect_pool(pool)
    _write(root / "host_only" / "panel_preflight.json", panel_preflight)
    views, dev_reports = _development(pool, executor, root, max_executions)
    _write(root / "development_views.json", seal({"views": views}))
    _write(root / "development_reports.json", seal({"reports": dev_reports}))
    proposals = {arm: _proposal(research, arm, views, root, protocol["record_hash"]) for arm in ARMS}
    # Invalid/no-update proposals have no new authority and honestly retain fixed
    # checks for the descriptive fallback comparison. Never pretend they updated.
    rubrics = {arm: p.rubric or fixed_rubric() for arm, p in proposals.items()}
    cache = ExecutionCache(executor, max_executions=max_executions,
                           mode="common_evidence" if common_evidence else "per_arm")
    pipelines = {arm: pipeline_hash(r, cache) for arm, r in rubrics.items()}
    candidates = tuple(sorted({pipelines[a] for a in ARMS[1:] if pipelines[a] != pipelines["fixed"]}))
    dev_manifest = PartitionManifest([e for e in manifest.entries if e.partition == "development"])
    freezes = {}
    for arm in ARMS[1:]:
        if pipelines[arm] == pipelines["fixed"]:
            continue
        freezes[arm] = FreezeDeclaration(proposals[arm].content_hash, pipelines[arm], pipelines["fixed"], candidates,
            protocol["record_hash"], config.content_hash, dev_manifest.to_dict()["manifest_hash"], digest(views),
            tuple(sorted({e.original_task_id for e in dev_manifest.entries})),
            tuple(sorted({e.near_duplicate_family for e in dev_manifest.entries})))
        register_freeze(freezes[arm], development_manifest=dev_manifest, ledger_dir=root / "gate")
    outcomes, execution_costs = {}, {}
    for purpose in PURPOSES[1:]:
        rows = {arm: [] for arm in ARMS}
        execution_cost = {arm: {"executions": 0, "seconds": 0.0, "missing": 0} for arm in ARMS}
        for row in pool:
            if row["task"].contract.partition != purpose:
                continue
            name = digest([row["task"].content_hash, [a.content_hash for a in row["artifacts"]]])
            result = compare_frozen(row["task"], row["artifacts"], rubrics, executor,
                                    root=root / "execution" / name, max_executions=max_executions,
                                    common_evidence=common_evidence)
            _write(root / "comparisons" / (name + ".json"), result)
            for arm in ARMS:
                rows[arm].extend(_rows(row, result["reports"][arm]))
                execution_cost[arm]["executions"] += result["costs"][arm]["execution_requests"]
                execution_cost[arm]["seconds"] += result["costs"][arm]["execution_seconds"]
                execution_cost[arm]["missing"] += result["costs"][arm]["missing_execution_records"]
        costs = {}
        for arm in ARMS:
            p, c = proposals[arm].costs, execution_cost[arm]
            scripted = transport_identity.get("kind") == "scripted_fixture"
            costs[arm] = (ActualCost(0 if scripted else p["model_calls"], p["input_tokens"], p["output_tokens"],
                                    0 if scripted else p["retrieval_requests"],
                                    c["executions"], c["seconds"], c["missing"])
                          if p["input_tokens"] is not None and p["output_tokens"] is not None else None)
        execution_costs[purpose] = execution_cost
        outcomes[purpose] = {}
        for arm in ARMS[1:]:
            if purpose == "verifier_calibration" and arm in freezes:
                decision, report = calibrate(rows["fixed"], rows[arm], manifest=manifest, freeze=freezes[arm], config=config,
                    ledger_dir=root / "gate", fixed_cost=costs["fixed"], candidate_cost=costs[arm])
                decision = decision.to_dict()
            else:
                report = evaluate_comparison(rows["fixed"], rows[arm], manifest=manifest, purpose=purpose,
                                             fixed_cost=costs["fixed"], candidate_cost=costs[arm])
                decision = {"status": "pending", "reason": "no_new_verifier" if purpose == "verifier_calibration" else
                            "independent_audit_has_no_admission_authority"}
            outcomes[purpose][arm] = {"decision": decision, "report": report}
    summary = seal({"protocol_hash": protocol["record_hash"], "proposal_status": {a: p.status for a, p in proposals.items()},
                    "panel_preflight_hash": panel_preflight["record_hash"],
                    "panel_readiness": panel_preflight["readiness"],
                    "proposal_costs": {a: p.costs for a, p in proposals.items()}, "outcomes": outcomes,
                    "total_unique_execution_cost": _execution_totals(root),
                    "execution_costs_by_partition": execution_costs,
                    "proposal_cost_accounting": {"transport": transport_identity,
                        "proposal_model_calls_field": "logical callback invocations, not necessarily paid provider calls",
                        "scripted_fixture_actual_provider_and_network_requests": 0 if transport_identity.get("kind") == "scripted_fixture" else None},
                    "pool_artifact_count": len(manifest.entries), "model_artifact_count": sum(e.provenance_kind == "model" for e in manifest.entries),
                    "learning_or_generalization_effect_established": False,
                    "limits": ["Fixture annotations and scripted proposals are engineering controls, not natural effect evidence.",
                               "One frozen proposal batch only; no Skill Gate, updater or scope promotion.",
                               "Calls and token caps are equal only for adaptive arms; actual costs are separate.",
                               "Proposal costs are shown in each panel for transparency: do not sum duplicate proposal charges.",
                               "Common-evidence execution costs are recorded in individual comparison files as shared overhead.",
                               "Input-state checks are available to both adaptive arms; Research is not guaranteed exclusive benefit."]})
    _write(root / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pool", type=Path, help="Explicit frozen pool directory; default is engineering fixtures")
    parser.add_argument("--image", default="sha256:" + "0" * 64, help="Locally available pinned Docker image ID; never pulled automatically")
    parser.add_argument("--common-evidence", action="store_true")
    args = parser.parse_args(argv)
    from .stage2_fixtures import fixture_pool, scripted_fetcher, scripted_model
    pool = import_pool(args.pool) if args.pool else fixture_pool()
    research = BoundedResearch(model=scripted_model, fetcher=scripted_fetcher,
                               cache_root=args.output / "research_cache", budget=ResearchBudget())
    result = run_study(pool, research=research, executor=DockerExecutor(args.image), output=args.output,
                       transport_identity={"kind": "scripted_fixture", "real_model_calls": 0,
                                           "real_document_retrievals": 0}, common_evidence=args.common_evidence)
    print(json.dumps({"summary": str(args.output / "summary.json"), "proposal_status": result["proposal_status"],
                      "decisions": {a: result["outcomes"]["verifier_calibration"][a]["decision"]["status"] for a in ARMS[1:]},
                      "model_artifact_count": result["model_artifact_count"], "effect_established": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
