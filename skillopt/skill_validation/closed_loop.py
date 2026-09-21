"""One strictly gated Skill/verifier round; the CLI runs engineering smoke only.

Unlike single_round's exploratory comparison, failed verifier calibration stops
the updater. Skill confirmation precedes final evaluation and controls routing.
Host audit labels never enter an updater or a Skill admission decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from .admission import (
    ScopeRule,
    SkillGateConfig,
    decide_skill,
    derive_authority,
    register_skill_freeze,
    require_update_authority,
    select_skill,
)
from .calibration import FreezeDeclaration, GateConfig, calibrate, register_freeze
from .checks import CallableTask, ExecutionCache, pipeline_hash, validate_callable
from .models import ArtifactRecord, RubricVersion, require
from .panel import checked_path
from .partitions import PartitionEntry, PartitionManifest
from .probe_recipes import InputStateProbeRecipe, bind_rubric, instantiate
from .replay import partition_entry
from .research import BoundedResearch, ResearchResult, fixed_rubric
from .single_round import IMAGE, _healthy, _research_views
from .single_round_feedback import build_feedback_bundle, candidate_from_response, messages
from .stage2 import _rows

VERSION = "skill-verifier-gated-round-v1"
CONDITIONS = ("no_skill", "current", "candidate")


def _write(path, value):
    write_immutable_json(checked_path(path), value)


def _read(path):
    return verify(json.loads(checked_path(path).read_text(encoding="utf-8")))


def _cached(root, request, produce):
    """No silent retry after an ambiguous interrupted callback."""
    key = digest(request)
    path, intent = root / (key + ".json"), root / "intents" / (key + ".json")
    if path.exists():
        record = _read(path)
        require(record["request"] == request and intent.exists()
                and _read(intent)["request"] == request, "Callback cache binding mismatch")
        return record["result"]
    require(not intent.exists(), "Interrupted callback retained; no automatic resampling")
    _write(intent, seal({"request": request}))
    result = produce()
    _write(path, seal({"request": request, "result": result}))
    return result


def _manifest(entries):
    return PartitionManifest([partition_entry(e["task"].contract, a) for e in entries for a in e["artifacts"]])


def _plan(tasks):
    require(type(tasks) is tuple and tasks, "Frozen typed task plan required")
    purposes = {"development", "verifier_calibration", "skill_confirmation", "final"}
    result = []
    for task, region in tasks:
        require(type(task) is CallableTask and task.contract.partition in purposes, "Unsupported task purpose")
        allowed = {"target", "retention", "nonapplicable"}
        if task.contract.partition == "development":
            allowed.add("development")
        if task.contract.partition == "verifier_calibration":
            allowed.add("calibration")
        require(region in allowed, "Unknown task region")
        c = task.contract
        result.append(PartitionEntry(task.content_hash, c.original_task_id, c.family_id, c.project_id,
                                     c.partition, "fixture", False))
    registry = PartitionManifest(result)
    require(len(registry.entries) == len(tasks), "Duplicate task in plan")
    require({e.partition for e in registry.entries} == purposes, "All four independent purposes required")
    return registry


def run_round(*, tasks, parent_skill, solver, updater, auditor, research, executor, capabilities,
              output, transport_identity, engineering_simulation=False, gate_config=None,
              skill_config=None, recipe=None, scope=None, max_executions=256):
    """Trusted host callbacks supply artifacts/audit; model views remain narrow.

    `solver(task, text, condition, repeat)` must return a source-bound artifact;
    `auditor(task, artifact)` returns host-only common-obligation labels. These
    callbacks are not arbitrary model scripts. Importers own source authenticity.
    The public CLI installs explicit fixture callbacks, never natural provenance.
    """
    root = checked_path(output)
    _plan(tasks)
    original_tasks = {task.contract.content_hash: task for task, _ in tasks}
    require(type(engineering_simulation) is bool, "Explicit engineering flag required")
    gate_config = gate_config or GateConfig(2, 2, 2, 2, .75, 0., 0., 1)
    skill_config = skill_config or SkillGateConfig()
    recipe = recipe or InputStateProbeRecipe(choice="reverse_list", max_cases=1)
    scope = scope or ScopeRule(("input_preservation",))
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
    protocol = seal({"version": VERSION, "tasks": [{"task": t.to_dict(), "region": r} for t, r in tasks],
        "source_hashes": source_hashes, "parent_skill_hash": hashlib.sha256(parent_skill.encode()).hexdigest(),
        "gate_config": gate_config.to_dict(), "skill_config": skill_config.to_dict(), "scope": scope.to_dict(),
        "recipe": recipe.to_dict(), "capabilities": {k: v.to_dict() for k, v in sorted(capabilities.items())},
        "transport": transport_identity, "executor": executor.identity, "research_budget": research.budget.to_dict(),
        "engineering_simulation": engineering_simulation, "max_executions": max_executions,
        "independent_final_not_for_admission": True, "automatic_next_round": False,
        "scope_limit": "Coding public input-preservation contracts only; no cross-domain approval"})
    _write(root / "protocol.json", protocol)
    cache = ExecutionCache(executor, root / "execution", max_executions=max_executions)
    baseline = fixed_rubric()
    histories = []

    def solve(task, skill, condition, repeat):
        request = {"protocol": protocol["record_hash"], "task": task.content_hash,
                   "skill_hash": hashlib.sha256(skill.encode()).hexdigest(), "condition": condition, "repeat": repeat}
        data = _cached(root / "solver", request, lambda: solver(task, skill, condition, repeat).to_dict())
        artifact = ArtifactRecord.from_dict(data)
        require(artifact.task_hash == task.contract.content_hash and artifact.condition == condition
                and artifact.repeat == repeat and artifact.skill_hash == request["skill_hash"], "Solver artifact binding mismatch")
        require(not engineering_simulation or artifact.provenance_kind == "fixture", "Fixture mode cannot invent natural evidence")
        return artifact

    def audit(task, artifact):
        request = {"task": task.content_hash, "artifact": artifact.content_hash, "protocol": protocol["record_hash"]}
        labels = _cached(root / "host_only" / "audits", request, lambda: auditor(task, artifact))
        require(set(labels) == {o.id for o in task.contract.obligations}
                and all(v in {"pass", "fail", "unknown"} for v in labels.values()), "Audit changed common obligation universe")
        return labels

    def evaluate(task, artifacts, rubric):
        reports = tuple(validate_callable(task, a, rubric, cache) for a in artifacts)
        for record in cache.records.values():
            _healthy(record["execution"])
        for report in reports:
            _write(root / "reports" / (report["record_hash"] + ".json"), report)
        return {"task": task, "artifacts": artifacts, "reports": reports}

    # Development: no Candidate exists; the identical paired artifacts feed V updates.
    development, dev_audits = [], {}
    for task, _ in tasks:
        if task.contract.partition != "development":
            continue
        pair = tuple(solve(task, text, condition, 0) for text, condition in (("", "no_skill"), (parent_skill, "current")))
        development.append(evaluate(task, pair, baseline))
        for artifact in pair:
            labels = audit(task, artifact)
            status = "fail" if "fail" in labels.values() else "unknown" if "unknown" in labels.values() else "pass"
            dev_audits[artifact.content_hash] = seal({"status": status, "information_origin": "host_development_audit"})
    dev_manifest = _manifest(development)
    views = _research_views(development, dev_audits)
    _write(root / "development_views.json", seal({"views": views}))
    data = _cached(root / "research", {"protocol": protocol["record_hash"], "views": digest(views)},
                   lambda: research.propose("adaptive_research", baseline, views).to_dict())
    proposal = ResearchResult(data["status"], data["arm"], RubricVersion.from_dict(data["rubric"]) if data["rubric"] else None,
                              tuple(data["findings"]), tuple(data["sources"]), data["costs"], tuple(data["trace"]),
                              data["reason"], data["requires_calibration"])

    def finish(phase, **fields):
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "phase": phase,
                       "engineering_simulation": engineering_simulation, "research_status": proposal.status,
                       "real_deployment_performed": False, "automatic_next_round": False,
                       "completed_solver_callbacks": len(list((root / "solver").glob("*.json"))),
                       "completed_updater_callbacks": len(list((root / "updater").glob("*.json"))),
                       **fields})
        _write(root / "summary.json", result)
        return result

    if proposal.status != "update" or proposal.rubric is None:
        return finish("blocked_verifier_proposal", reason=proposal.reason, skill_gate="Pending")
    if not any(c.method == "input_state" for c in proposal.rubric.checks):
        return finish("blocked_verifier_proposal", reason="No preservation method for the preregistered recipe", skill_gate="Pending")
    rubric = bind_rubric(proposal.rubric, recipe)
    phash = pipeline_hash(rubric, cache)
    freeze = FreezeDeclaration(proposal.content_hash, phash, pipeline_hash(baseline, cache), (phash,),
        protocol["record_hash"], gate_config.content_hash, dev_manifest.to_dict()["manifest_hash"],
        digest([a.content_hash for e in development for a in e["artifacts"]]),
        tuple(sorted({e.original_task_id for e in dev_manifest.entries})),
        tuple(sorted({e.near_duplicate_family for e in dev_manifest.entries})))
    register_freeze(freeze, development_manifest=dev_manifest, ledger_dir=root / "verifier_gate")

    def expanded(task):
        updated, receipt = instantiate(task, recipe, capabilities.get(task.contract.content_hash))
        _write(root / "probe_instances" / (task.content_hash + ".json"), receipt)
        return updated

    # Calibrate on separate No-Skill/Current artifacts; an updated Candidate
    # does not exist yet and is never fabricated for this panel.
    calibration, left, right = [], [], []
    for task, region in tasks:
        if task.contract.partition != "verifier_calibration":
            continue
        artifacts = tuple(solve(task, "" if c == "no_skill" else parent_skill, c, 0) for c in CONDITIONS[:2])
        row = {"task": task, "artifacts": artifacts,
               "audit": {a.content_hash: audit(task, a) for a in artifacts}, "near_miss": region == "nonapplicable"}
        fixed = evaluate(task, artifacts, baseline)
        advanced = evaluate(expanded(task), artifacts, rubric)
        calibration.append(fixed)
        left.extend(_rows(row, fixed["reports"]))
        right.extend(_rows(row, advanced["reports"]))
    cal_manifest = _manifest(calibration)
    verifier_decision, comparison = calibrate(left, right, manifest=cal_manifest, freeze=freeze,
        config=gate_config, ledger_dir=root / "verifier_gate")
    authority = derive_authority(verifier_decision, comparison, freeze, gate_config,
        calibration_manifest=cal_manifest, development_manifest=dev_manifest,
        obligation_kinds=("input_preservation", "requested_behavior"), engineering_simulation=engineering_simulation)
    _write(root / "host_only" / "verifier_comparison.json", seal(comparison))
    _write(root / "verifier_authority.json", authority)
    expected = "engineering_accepted" if engineering_simulation else "accepted"
    if authority["status"] != expected:
        return finish("blocked_verifier_gate", verifier_gate=verifier_decision.status,
                      verifier_authority=authority["status"], skill_gate="Pending", authority_hash=authority["record_hash"])
    require_update_authority(authority, phash, engineering_simulation=engineering_simulation)

    # The accepted recipe now produces fresh executable development evidence.
    feedback_entries = [evaluate(expanded(e["task"]), e["artifacts"], rubric) for e in development]
    bundle = build_feedback_bundle(feedback_entries, parent_skill=parent_skill, rubric=rubric,
        pipeline_hash=phash, execution_identity=cache.identity,
        execution_records=tuple((*cache.records.values(), *cache.missing_records.values())))
    _write(root / "feedback.json", bundle)
    system, user, prompt_hash = messages(parent_skill, bundle)
    response = _cached(root / "updater", {"protocol": protocol["record_hash"], "prompt_hash": prompt_hash,
                       "authority_hash": authority["record_hash"]}, lambda: updater(system, user, 2048))
    update = candidate_from_response(response, parent_skill, bundle)
    _write(root / "candidate.json", update)
    if update["update"]["status"] != "candidate":
        return finish("no_skill_update", verifier_gate=verifier_decision.status, verifier_authority=authority["status"],
                      skill_gate="Pending", update_status=update["update"]["status"])
    candidate = update["update"]["candidate_skill"]
    prior = PartitionManifest((*dev_manifest.entries, *cal_manifest.entries))
    confirmation_tasks = tuple((expanded(t), region) for t, region in tasks if t.contract.partition == "skill_confirmation")
    # Solver callbacks use these deterministic text-derived versions; callers
    # must preserve them rather than laundering old evidence under a new Skill.
    def version(skill):
        return "skill-" + hashlib.sha256(skill.encode()).hexdigest()[:16]
    skill_freeze = register_skill_freeze(parent_text=parent_skill, candidate_text=candidate,
        parent_version=version(parent_skill), candidate_version=version(candidate), authority=authority,
        scope=scope, config=skill_config, prior_manifest=prior, confirmation_tasks=confirmation_tasks,
        ledger_dir=root / "skill_gate", engineering_simulation=engineering_simulation)
    _write(root / "frozen_candidate_and_scope.json", skill_freeze)
    confirmation = []
    skills = {"no_skill": "", "current": parent_skill, "candidate": candidate}
    for task, _ in confirmation_tasks:
        for repeat in range(skill_config.repeats):
            # New verifier probes are NOT solver-facing examples. All solver
            # conditions receive the original, common public task context.
            artifacts = tuple(solve(original_tasks[task.contract.content_hash], skills[c], c, repeat) for c in CONDITIONS)
            confirmation.append(evaluate(task, artifacts, rubric))
    confirmation_manifest = _manifest(confirmation)
    decision = decide_skill(confirmation, authority=authority, freeze=skill_freeze, config=skill_config,
        manifest=confirmation_manifest, ledger_dir=root / "skill_gate", engineering_simulation=engineering_simulation)
    _write(root / "skill_decision.json", decision)

    # Final observes a frozen decision. Routing is chosen BEFORE solve/audit.
    final_plan = []
    approved = decision["action"] in {"Local Commit", "Restrict"}
    for task, region in tasks:
        if task.contract.partition == "final":
            route = select_skill(task, candidate, version(candidate), decision, authority=authority,
                pipeline_hash=phash, engineering_simulation=engineering_simulation)
            final_plan.append({"task_hash": task.contract.content_hash, "region": region,
                               "selected": route["condition"], "route_hash": route["record_hash"]})
            _write(root / "routing" / (task.contract.content_hash + ".json"), route)
    _write(root / "frozen_final_routing.json", seal({"decision_hash": decision["record_hash"], "rows": final_plan}))
    selected = {r["task_hash"]: r["selected"] for r in final_plan}
    final = []
    for task, region in tasks:
        if task.contract.partition != "final":
            continue
        for repeat in range(skill_config.repeats):
            # Each condition starts clean; replaying its independent artifact is
            # not fallback after a candidate has already changed the environment.
            outcomes, artifacts = {}, []
            for condition in CONDITIONS:
                artifact = solve(task, skills[condition], condition, repeat)
                artifacts.append(artifact)
                labels = audit(task, artifact)
                outcomes[condition] = "unknown" if artifact.availability != "available" else (
                    "fail" if "fail" in labels.values() else "unknown" if "unknown" in labels.values() else "pass")
            observed = evaluate(expanded(task), tuple(artifacts), rubric)
            route = selected[task.contract.content_hash]
            outcomes["deployed_policy"] = outcomes[route]
            final.append({"task_hash": task.contract.content_hash, "repeat": repeat, "region": region,
                          "selected": route, "outcomes": outcomes,
                          "artifact_hashes": [a.content_hash for a in artifacts],
                          "public_verifier_outcomes": {a.condition: r["status"] for a, r in zip(artifacts, observed["reports"])},
                          "public_report_hashes": [r["record_hash"] for r in observed["reports"]]})
            histories.extend(partition_entry(task.contract, a) for a in artifacts)
    PartitionManifest((*prior.entries, *confirmation_manifest.entries, *histories))
    _write(root / "host_only" / "final.json", seal({"decision_hash": decision["record_hash"], "rows": final,
                                                   "not_used_for_learning_or_admission": True}))
    scores = {c: dict(Counter(r["outcomes"][c] for r in final)) for c in (*CONDITIONS, "deployed_policy")}
    state = seal({"parent_hash": protocol["parent_skill_hash"], "candidate_hash": update["update"]["candidate_skill_hash"],
                  "rubric": rubric.to_dict(), "recipe": recipe.to_dict(), "scope": scope.to_dict(),
                  "authority_hash": authority["record_hash"], "decision_hash": decision["record_hash"],
                  "accepted_for_next_real_round": decision["deployment_authorized"],
                  "simulated_next_skill": candidate if approved else "", "engineering_simulation": engineering_simulation,
                  "new_round_requires_fresh_partitions": True})
    _write(root / "next_state.json", state)
    return finish("completed", verifier_gate=verifier_decision.status, verifier_authority=authority["status"],
                  skill_gate=decision["action"], final=scores, final_tasks=len(final_plan),
                  final_audit_source="scripted_fixture_labels_not_independent_research" if engineering_simulation else "host_auditor",
                  fallback_fraction=sum(r["selected"] == "no_skill" for r in final) / len(final),
                  deployment_authorized=decision["deployment_authorized"], next_state_hash=state["record_hash"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo")
    parser.add_argument("--scenario", choices=("beneficial", "harmful", "insufficient"), default="beneficial")
    parser.add_argument("--probe", choices=("reverse_list", "none"), default="reverse_list")
    args = parser.parse_args(argv)
    from .closed_loop_fixtures import PARENT_SKILL, audit_labels, fixture_solver, fixture_tasks, scripted_updater
    from .probe_recipes import HostInputCapability
    from .sandbox import DockerExecutor
    from .stage2_fixtures import scripted_fetcher, scripted_model
    rows = fixture_tasks()
    index = {r["task"].contract.content_hash: r for r in rows}
    def solve(task, skill, condition, repeat):
        return fixture_solver(index[task.contract.content_hash], condition=condition, skill_text=skill,
                              repeat=repeat, scenario=args.scenario if args.scenario != "insufficient" else "beneficial")
    def audit(task, artifact):
        return audit_labels(index[task.contract.content_hash], artifact)
    if args.remote_repo:
        from .remote_executor import SSHExecutor
        executor = SSHExecutor(IMAGE, remote_repo=args.remote_repo)
    else:
        executor = DockerExecutor(IMAGE)
    try:
        result = run_round(tasks=tuple((r["task"], r["region"]) for r in rows), parent_skill=PARENT_SKILL,
            solver=solve, auditor=audit, updater=scripted_updater,
            research=BoundedResearch(model=scripted_model, fetcher=scripted_fetcher, cache_root=args.output / "research_docs"),
            executor=executor, output=args.output, engineering_simulation=True,
            recipe=InputStateProbeRecipe(args.probe),
            capabilities={k: HostInputCapability(task_hash=k, positional_arg_index=0) for k in index},
            gate_config=GateConfig(99 if args.scenario == "insufficient" else 2, 2, 2, 2, .75, 0., 0., 1),
            transport_identity={"kind": "explicit_engineering_fixture", "scenario": args.scenario,
                                "real_model_calls": 0, "real_retrievals": 0})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        if hasattr(executor, "close"):
            executor.close()


if __name__ == "__main__":
    main()
