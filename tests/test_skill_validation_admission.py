"""Fabricated unit controls only: never import these as real model records."""
import hashlib
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.admission import (
    ScopeRule,
    SkillGateConfig,
    decide_skill,
    derive_authority,
    register_skill_freeze,
    require_update_authority,
    select_skill,
)
from skillopt.skill_validation.calibration import (
    CalibrationRow,
    FreezeDeclaration,
    GateConfig,
    calibrate,
    register_freeze,
)
from skillopt.skill_validation.checks import CallableTask, PublicCase
from skillopt.skill_validation.models import ArtifactRecord, Obligation, SourceFile, TaskContract
from skillopt.skill_validation.partitions import PartitionEntry, PartitionManifest
from skillopt.validator_pilot.api import digest

BASELINE, PIPELINE = digest("fixed"), digest("research")
PARENT, CANDIDATE = "parent skill", "candidate skill"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def calibration(tmp_path, *, provenance="fixture", gain=True):
    fixed, candidate, entries = [], [], []
    for name, audit, applicable in (("wrong", "fail", True), ("right", "pass", True), ("near", "unknown", False)):
        artifact = digest(["cal", name])
        status = "pass" if applicable else "not_applicable"
        row = CalibrationRow(name, "cal:" + name, "cal-family:" + name, "cal-project:" + name,
                             "verifier_calibration", digest(["cal-task", name]), artifact, 0, "candidate", "input",
                             status, audit, applicable, not applicable, provenance, True, False,
                             BASELINE, digest(["baseline-report", name]), digest(["audit", name]))
        fixed.append(row)
        candidate.append(replace(row, rubric_pipeline_hash=PIPELINE,
                                 verifier_status="fail" if gain and audit == "fail" else status,
                                 report_hash=digest(["research-report", name, gain])))
        entries.append(PartitionEntry(artifact, row.original_task_id, row.family_id, row.project_id,
                                      row.partition, provenance, True))
    dev = PartitionManifest((PartitionEntry(digest("dev-artifact"), "dev:task", "dev:family", "dev:project",
                                            "development", provenance, True),))
    manifest = PartitionManifest(entries)
    config = GateConfig(1, 1, 1, 1, 1.0, 0.0, 0.0, 1)
    freeze = FreezeDeclaration(digest("proposal"), PIPELINE, BASELINE, (PIPELINE,), digest("protocol"),
                               config.content_hash, dev.to_dict()["manifest_hash"], digest("dev-data"),
                               ("dev:task",), ("dev:family",))
    register_freeze(freeze, development_manifest=dev, ledger_dir=tmp_path / "cal")
    decision, report = calibrate(fixed, candidate, manifest=manifest, freeze=freeze, config=config,
                                 ledger_dir=tmp_path / "cal")
    return decision, report, freeze, config, manifest, dev


def authority(tmp_path, *, provenance="fixture", gain=True):
    decision, comparison, freeze, config, manifest, dev = calibration(tmp_path, provenance=provenance, gain=gain)
    result = derive_authority(decision, comparison, freeze, config, calibration_manifest=manifest,
                              development_manifest=dev, obligation_kinds=("requested_behavior", "input_preservation"),
                              engineering_simulation=provenance == "fixture")
    return result, PartitionManifest((*dev.entries, *manifest.entries))


def task(name, *, preserve=True, partition="skill_confirmation"):
    requirement = "Return a sorted copy. Do not mutate input." if preserve else "Sort input in place."
    obligations = [Obligation("result", "requested_behavior", requirement, requirement)]
    if preserve:
        obligations.append(Obligation("input", "input_preservation", "Do not mutate input.", "Do not mutate input."))
    contract = TaskContract(name, "confirm:" + name, "confirm-family:" + name, "confirm-project:" + name,
                            partition, "coding", "host-only-mechanism", requirement, tuple(obligations))
    return CallableTask(contract, "solution", "solve", (PublicCase("public", '{"args":[[2,1]],"kwargs":{}}',
                                                                  requirement, tuple(o.id for o in obligations), "[1,2]"),))


def panel(tasks, *, provenance="fixture", candidate_target="pass", candidate_near="pass", repeat=0):
    entries, manifest = [], PartitionManifest()
    for current_task, region in tasks:
        artifacts, reports = [], []
        for condition in ("no_skill", "current", "candidate"):
            value = "" if condition == "no_skill" else PARENT if condition == "current" else CANDIDATE
            artifact = ArtifactRecord(current_task.contract.content_hash, repeat, condition,
                                      "none" if condition == "no_skill" else "parent-v1" if condition == "current" else "candidate-v2",
                                      sha(value), (SourceFile("solution.py", "def solve(xs): return sorted(xs)"),),
                                      "available", provenance, True, False, "synthetic:unit-test", digest([region, condition, repeat]))
            status = "fail" if region == "target" and condition != "candidate" else "pass"
            if condition == "candidate":
                status = candidate_target if region == "target" else candidate_near if region == "nonapplicable" else "pass"
            checks = [{"obligation_id": o.id, "status": status, "evidence_refs": [digest([artifact.content_hash, o.id])]}
                      for o in current_task.contract.obligations]
            report = seal({"task_hash": current_task.contract.content_hash, "callable_task_hash": current_task.content_hash,
                           "artifact_record_hash": artifact.content_hash, "pipeline_hash": PIPELINE,
                           "checks": checks, "obligations": {o.id: status for o in current_task.contract.obligations},
                           "status": status})
            artifacts.append(artifact)
            reports.append(report)
            contract = current_task.contract
            manifest.register(PartitionEntry(artifact.content_hash, contract.original_task_id, contract.family_id,
                                             contract.project_id, contract.partition, provenance, True))
        entries.append({"task": current_task, "artifacts": tuple(artifacts), "reports": tuple(reports)})
    return entries, manifest


def prepared(tmp_path, *, provenance="fixture", candidate_target="pass", candidate_near="pass", config=None):
    authorized, prior = authority(tmp_path, provenance=provenance)
    tasks = ((task("target"), "target"), (task("retention"), "retention"),
             (task("near", preserve=False), "nonapplicable"))
    config = config or SkillGateConfig(1, 1, 1)
    frozen = register_skill_freeze(parent_text=PARENT, candidate_text=CANDIDATE,
                                   parent_version="parent-v1", candidate_version="candidate-v2",
                                   authority=authorized, scope=ScopeRule(("input_preservation",)), config=config,
                                   prior_manifest=prior, confirmation_tasks=tasks, ledger_dir=tmp_path / "skill",
                                   engineering_simulation=provenance == "fixture")
    entries, manifest = panel(tasks, provenance=provenance, candidate_target=candidate_target, candidate_near=candidate_near)
    kwargs = dict(authority=authorized, freeze=frozen, config=config, manifest=manifest,
                  ledger_dir=tmp_path / "skill", engineering_simulation=provenance == "fixture")
    return entries, kwargs, tasks


def test_fixture_simulation_accept_is_never_real_authority(tmp_path):
    authorized, _ = authority(tmp_path)
    assert authorized["status"] == "engineering_accepted"
    assert authorized["verifier_decision"]["status"] == "pending"
    assert not authorized["deployment_authorized"]
    with pytest.raises(ValueError, match="Engineering"):
        require_update_authority(authorized, PIPELINE)
    require_update_authority(authorized, PIPELINE, engineering_simulation=True)


def test_pending_or_rejected_verifier_blocks_updates(tmp_path):
    authorized, _ = authority(tmp_path, gain=False)
    assert authorized["status"] == "engineering_rejected"
    with pytest.raises(ValueError, match="not authorized"):
        require_update_authority(authorized, PIPELINE, engineering_simulation=True)


def test_calibration_binding_rejects_changed_pipeline_config_comparison(tmp_path):
    d, report, freeze, config, manifest, dev = calibration(tmp_path)
    kwargs = dict(calibration_manifest=manifest, development_manifest=dev,
                  obligation_kinds=("input_preservation",), engineering_simulation=True)
    with pytest.raises(ValueError, match="binding"):
        derive_authority(d, {**report, "net_new_detection": 99}, freeze, config, **kwargs)
    with pytest.raises(ValueError, match="binding"):
        derive_authority(d, report, freeze, replace(config, min_coverage=.5), **kwargs)
    with pytest.raises(ValueError, match="binding"):
        derive_authority(replace(d, rubric_pipeline_hash=digest("new")), report, freeze, config, **kwargs)


def test_fixture_local_commit_and_replay(tmp_path):
    entries, kwargs, _ = prepared(tmp_path)
    result = decide_skill(entries, **kwargs)
    assert result["action"] == "Local Commit" and not result["deployment_authorized"]
    assert result["raw_forced"]["target"]["no_skill"]["win"] == 1
    assert result["deployment"]["outside_scope"] == "no_skill"
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert decide_skill(entries, **kwargs) == result
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")} == before


def test_natural_path_unit_control_has_finite_local_rights_only(tmp_path):
    # Deliberately fabricated labels to exercise the branch, NOT actual model data.
    entries, kwargs, _ = prepared(tmp_path, provenance="model")
    result = decide_skill(entries, **kwargs)
    assert result["action"] == "Local Commit" and result["deployment_authorized"]
    assert result["scope"] == {"required_obligation_kinds": ["input_preservation"], "forbidden_obligation_kinds": []}


def test_predeclared_scope_restricts_harmful_near_miss(tmp_path):
    entries, kwargs, _ = prepared(tmp_path, candidate_near="fail")
    result = decide_skill(entries, **kwargs)
    assert result["action"] == "Restrict"
    assert result["raw_forced"]["nonapplicable"]["no_skill"]["loss"] == 1
    assert result["hypothetical_routed"]["nonapplicable"]["no_skill"]["loss"] == 0
    assert result["deployment"]["fallback_rate"] == pytest.approx(1 / 3)


def test_no_gain_rejects_and_reports_zero_learning_coverage(tmp_path):
    entries, kwargs, _ = prepared(tmp_path, candidate_target="fail")
    result = decide_skill(entries, **kwargs)
    assert result["action"] == "Reject" and result["deployment"]["fallback_rate"] == 1


def test_unknown_is_pending_not_semantic_failure(tmp_path):
    entries, kwargs, _ = prepared(tmp_path, candidate_target="unknown")
    result = decide_skill(entries, **kwargs)
    assert result["action"] == "Pending"
    assert result["raw_forced"]["target"]["no_skill"]["unknown"] == 1
    assert result["raw_forced"]["target"]["no_skill"]["loss"] == 0


def test_insufficient_independent_families_pending(tmp_path):
    entries, kwargs, _ = prepared(tmp_path, config=SkillGateConfig(2, 1, 1))
    assert decide_skill(entries, **kwargs)["action"] == "Pending"


def test_changed_skill_cannot_inherit_confirmation(tmp_path):
    entries, kwargs, _ = prepared(tmp_path)
    artifacts = list(entries[0]["artifacts"])
    artifacts[2] = replace(artifacts[2], skill_hash=digest("other skill"))
    entries[0] = {**entries[0], "artifacts": tuple(artifacts)}
    with pytest.raises(ValueError, match="Changed Skill"):
        decide_skill(entries, **kwargs)


def test_final_cannot_enter_gate(tmp_path):
    entries, kwargs, _ = prepared(tmp_path)
    final_entries = [replace(e, partition="final") for e in kwargs["manifest"].entries]
    with pytest.raises(ValueError, match="Final"):
        decide_skill(entries, **{**kwargs, "manifest": PartitionManifest(final_entries)})


def test_changed_pipeline_cannot_inherit_authority(tmp_path):
    authorized, _ = authority(tmp_path)
    with pytest.raises(ValueError, match="pipeline"):
        require_update_authority(authorized, digest("new-check-generation-policy"), engineering_simulation=True)


def test_gate_forbids_hidden_audit_fields(tmp_path):
    entries, kwargs, _ = prepared(tmp_path)
    entries[0]["audit"] = {"candidate": "pass"}
    with pytest.raises(ValueError, match="Only public"):
        decide_skill(entries, **kwargs)


def test_confirmation_consumed_once_across_candidate_freezes(tmp_path):
    entries, kwargs, tasks = prepared(tmp_path)
    decide_skill(entries, **kwargs)
    authority_record = kwargs["authority"]
    prior = PartitionManifest.from_dict(kwargs["freeze"]["prior_manifest"])
    changed = register_skill_freeze(parent_text=PARENT, candidate_text=CANDIDATE,
                                    parent_version="parent-v1", candidate_version="candidate-v3",
                                    authority=authority_record, scope=ScopeRule(("input_preservation",)),
                                    config=kwargs["config"], prior_manifest=prior, confirmation_tasks=tasks,
                                    ledger_dir=kwargs["ledger_dir"], engineering_simulation=True)
    # Same content but new candidate version still cannot reuse consumed panel.
    for entry in entries:
        old = entry["artifacts"][2]
        new = replace(old, skill_version="candidate-v3")
        entry["artifacts"] = (*entry["artifacts"][:2], new)
        report = {k: v for k, v in entry["reports"][2].items() if k != "record_hash"}
        entry["reports"] = (*entry["reports"][:2], seal({**report, "artifact_record_hash": new.content_hash}))
    manifest = PartitionManifest(PartitionEntry(a.content_hash, e["task"].contract.original_task_id,
                                                 e["task"].contract.family_id, e["task"].contract.project_id,
                                                 "skill_confirmation", "fixture", True)
                                 for e in entries for a in e["artifacts"])
    with pytest.raises(ValueError, match="already consumed"):
        decide_skill(entries, **{**kwargs, "freeze": changed, "manifest": manifest})


def test_scope_ignores_host_domain_mechanism_outcomes():
    original = task("a")
    changed = replace(original, contract=replace(original.contract, mechanism="adversarial-hidden-label"))
    rule = ScopeRule(("input_preservation",))
    assert rule.matches(original) == rule.matches(changed)
    assert not rule.matches(task("b", preserve=False))


def test_missing_run_cannot_disappear(tmp_path):
    entries, kwargs, _ = prepared(tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        decide_skill(entries[:2], **kwargs)


def test_forged_summary_cannot_upgrade_unknown_checks(tmp_path):
    entries, kwargs, _ = prepared(tmp_path)
    report = entries[0]["reports"][2]
    altered = {k: v for k, v in report.items() if k != "record_hash"}
    altered["checks"] = [{**c, "status": "unknown"} for c in report["checks"]]
    entries[0]["reports"] = (*entries[0]["reports"][:2], seal(altered))
    with pytest.raises(ValueError, match="summary does not match"):
        decide_skill(entries, **kwargs)


def test_known_verdict_without_execution_evidence_is_rejected(tmp_path):
    entries, kwargs, _ = prepared(tmp_path)
    report = entries[0]["reports"][2]
    altered = {k: v for k, v in report.items() if k != "record_hash"}
    altered["checks"] = [{**c, "evidence_refs": []} for c in report["checks"]]
    entries[0]["reports"] = (*entries[0]["reports"][:2], seal(altered))
    with pytest.raises(ValueError, match="execution evidence"):
        decide_skill(entries, **kwargs)


@pytest.mark.parametrize("illegal_status", ["skip", "success", "", None, True])
def test_illegal_check_status_cannot_silently_aggregate_to_pass(tmp_path, illegal_status):
    entries, kwargs, _ = prepared(tmp_path)
    report = entries[0]["reports"][2]
    altered = {k: v for k, v in report.items() if k != "record_hash"}
    altered["checks"] = [{**c, "status": illegal_status} for c in report["checks"]]
    entries[0]["reports"] = (*entries[0]["reports"][:2], seal(altered))
    with pytest.raises(ValueError, match="individual check status"):
        decide_skill(entries, **kwargs)


def test_preexecution_selection_matches_scope_and_blocks_old_authority(tmp_path):
    entries, kwargs, tasks = prepared(tmp_path)
    decision = decide_skill(entries, **kwargs)
    authorization = {"authority": kwargs["authority"], "pipeline_hash": PIPELINE}
    with pytest.raises(ValueError, match="Engineering"):
        select_skill(tasks[0][0], CANDIDATE, "candidate-v2", decision, **authorization)
    routed = select_skill(tasks[0][0], CANDIDATE, "candidate-v2", decision, engineering_simulation=True, **authorization)
    assert routed["condition"] == "candidate" and not routed["deployment_authorized"]
    assert select_skill(tasks[2][0], CANDIDATE, "candidate-v2", decision,
                        engineering_simulation=True, **authorization)["skill_text"] == ""
    with pytest.raises(ValueError, match="Changed Skill"):
        select_skill(tasks[0][0], "updated again", "candidate-v2", decision, engineering_simulation=True, **authorization)
    final_task = replace(tasks[0][0], contract=replace(tasks[0][0].contract, partition="final"))
    assert select_skill(final_task, CANDIDATE, "candidate-v2", decision,
                        engineering_simulation=True, **authorization)["condition"] == "candidate"
    with pytest.raises(ValueError, match="pipeline"):
        select_skill(final_task, CANDIDATE, "candidate-v2", decision, engineering_simulation=True,
                     authority=kwargs["authority"], pipeline_hash=digest("changed checks"))
    original = tasks[0][0]
    extra_requirement = " Preserve README.md exactly."
    unsupported = replace(original, contract=replace(original.contract,
        prompt=original.contract.prompt + extra_requirement,
        obligations=(*original.contract.obligations, Obligation("file", "file_preservation",
                        extra_requirement.strip(), extra_requirement.strip(), "README.md")),
        public_files=(SourceFile("README.md", "baseline"),)))
    assert select_skill(unsupported, CANDIDATE, "candidate-v2", decision,
                        engineering_simulation=True, **authorization)["condition"] == "no_skill"
