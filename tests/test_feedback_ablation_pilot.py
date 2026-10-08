"""Feedback-content pilot orchestration: fixture controls with no model calls or containers."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import continue_fivebench_baselines as sequence
from scripts import run_feedback_ablation_pilot as pilot
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning import skillopt as learner
from skillopt.continual_learning.contracts import BUDGET_VERSION, manifest
from skillopt.continual_learning.execution_evidence import PROFILE
from skillopt.continual_learning.recovery import POLICY_V7
from tests.test_continual_learning_domains import setup

REPO = Path(__file__).resolve().parents[1]
SERVICE = {"name": "fixture-service"}
NO_SKILL = ["pass", "fail", "fail", "pass", "pass", "fail", "fail", "pass"]
ARM_A = ["pass", "pass", "fail", "pass", "pass", "fail", "pass", "pass"]   # +2 vs No-Skill
ARM_B = ["pass", "pass", "pass", "pass", "pass", "pass", "pass", "pass"]   # +4 vs No-Skill, +2 vs A
FILES = {"continual_eval/core.py": "require(len(skill_text.encode()) <= 6000)\n",
         "continual_eval/truncation_recovery.py": "require(len(skill.encode()) <= 6000)\n",
         "continual_eval/runner.py": "x = 1\n"}


def rows(statuses):
    return [{"task_id": f"t{i // 2}", "family_id": str(i // 2), "repeat": i % 2, "status": s,
             "record_hash": f"{i:064d}"} for i, s in enumerate(statuses)]


def source_tree(root, budget):
    for name, text in FILES.items():
        (root / "skillopt" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "skillopt" / name).write_text(text.replace("6000", str(budget)))


def learning_result(root, value, skill, *, status="completed", evaluations=None):
    identity = seal({"manifest": value, "native_sources": learner.native_sources()})
    write_json(root / "identity.json", identity)
    write_json(root / "native/0/result.json", seal({"fixture": True}))
    for name, row in (evaluations or {}).items():
        write_json(root / name, row)
    artifacts = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                 for name in ("native/0/result.json", *(evaluations or {}))}
    result = seal({"status": status, "candidate_skill": skill, "reason": "fixture", "identity_hash": identity["record_hash"],
                   "artifacts": artifacts, "initial_selection_score": 0.5, "selected_score": 0.6, "steps": [],
                   "costs": {"logical_calls": 3}})
    write_json(root / "result.json", result)
    return result


def f_study(tmp_path, *, profile=None, edit=None, roles=None, status="completed", completed=True):
    _, panel, args = setup("bigcodebench")
    args.update(version=BUDGET_VERSION, recovery_policy=deepcopy(POLICY_V7))
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    root = tmp_path / "f"
    write_json(root / "panels/bigcodebench.json", panel)
    arm_a = manifest(panel, **args, feedback_profile=profile)
    if edit:
        arm_a = seal({**{k: v for k, v in arm_a.items() if k != "record_hash"}, **edit(arm_a)})
    write_json(root / pilot.STAGE / "manifest.json", arm_a)
    source_tree(tmp_path / "src", 6000)
    source_tree(tmp_path / "derived", 32000)
    plan = seal({"source_identity": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in FILES.items()}})
    write_json(tmp_path / "noskill/plan.json", plan)
    reference = {"benchmark": "bigcodebench", "positions": 8, "rows": rows(NO_SKILL), "plan_hash": plan["record_hash"],
                 "report_hash": "r" * 64, "root": str(tmp_path / "noskill"), "source": str(tmp_path / "src"),
                 "python": "python", "evaluation_source": str(tmp_path / "derived"), "model_service": SERVICE}
    (tmp_path / "native.lock").write_text("")
    protocol = seal({"version": sequence.BUDGET_SEQUENCE, "methods": ["skillopt", "gepa"],
                     "learning_version": BUDGET_VERSION, "references": {"bigcodebench": reference},
                     "roles": {"bigcodebench": {"path": str(root / "panels/bigcodebench.json"),
                                                **(roles or {"train": ["0", "1"], "selection": ["2", "3"]})}},
                     "learning_model_service": SERVICE, "learning_client_options": {}, "model": args["model"],
                     "config": {"native_lock": str(tmp_path / "native.lock"), "workers": 1}})
    write_json(root / "protocol.json", protocol)
    learning = learning_result(root / pilot.STAGE / "learning", arm_a, "A skill" if status == "completed" else "",
                               status=status)
    stage_dir = root / pilot.STAGE
    request = seal({"reference": sequence._reference_identity(reference), "benchmark": "bigcodebench",
                    "baseline_plan_hash": reference["plan_hash"], "chain": ["A skill"]})
    write_json(stage_dir / "requests/bigcodebench.json", request)
    evaluated = seal({"rows": rows(ARM_A)})
    write_json(stage_dir / "evaluation-bigcodebench.json", evaluated)
    write_json(stage_dir / "stage.json", seal({
        "protocol_hash": protocol["record_hash"], "method": "skillopt", "stage": 1, "benchmark": "bigcodebench",
        "manifest_hash": arm_a["record_hash"], "learning_result_hash": learning["record_hash"],
        "skill": "A skill" if status == "completed" else "", "action": "selected_update",
        "learning_completed": completed, "cells": {"bigcodebench": {
            "result": evaluated, "kind": "new_frozen_policy_evaluation", "source_stage": 1,
            "request_path": str(stage_dir / "requests/bigcodebench.json"),
            "output_path": str(stage_dir / "evaluation-bigcodebench.json")}}}))
    return root, arm_a


def test_prepare_repeats_arm_a_except_the_feedback_profile(tmp_path):
    f_root, arm_a = f_study(tmp_path)
    protocol = pilot.prepare(f_root, REPO, tmp_path / "pilot")
    arm_b = read_json(tmp_path / "pilot/manifest-b.json", sealed=True)
    assert arm_b["feedback_profile"] == PROFILE and arm_a["feedback_profile"] != PROFILE
    assert all(arm_a[k] == arm_b[k] for k in arm_a if k not in {"feedback_profile", "record_hash", "source_identity"})
    assert protocol["learning_source_changes"] == {} and (tmp_path / "pilot/source-diff.patch").read_text() == ""
    assert set(protocol["evaluation_source_changes"]) == set(sequence.BUDGET_SOURCE_EDITS)
    assert protocol["excluded_families"] == ["0", "1", "2", "3"] and not protocol["deployment_authorized"]


@pytest.mark.parametrize("kwargs,source,message", [
    ({"profile": PROFILE}, REPO, "scalar-feedback"),
    ({"edit": lambda a: {"source_identity": {**a["source_identity"], "continual_eval/core.py": "0" * 64}}},
     REPO, "reviewed evidence wiring"),
    ({"edit": lambda a: {"host_runtime": {**a["host_runtime"], "python": "other"}}}, REPO, "host runtime"),
    ({"roles": {"train": ["0", "1"], "selection": ["2"]}}, REPO, "Role metadata"),
    ({"status": "pending"}, REPO, "did not complete"),
    ({"completed": False}, REPO, "did not complete"),
    ({}, Path("/nonexistent-f-source"), "not arm A's source tree"),
])
def test_prepare_refuses_anything_but_the_profile_difference(tmp_path, kwargs, source, message):
    f_root, _ = f_study(tmp_path, **kwargs)
    with pytest.raises(ValueError, match=message):
        pilot.prepare(f_root, source, tmp_path / "pilot")


def test_prepare_refuses_unreviewed_wiring_and_drifted_evaluation_sources(tmp_path, monkeypatch):
    edited = {"edit": lambda a: {"source_identity": {**a["source_identity"], "continual_learning/skillopt.py": "0" * 64}}}
    f_root, _ = f_study(tmp_path / "a", **edited)
    monkeypatch.setattr(pilot, "REVIEWED_SOURCES", {"continual_learning/skillopt.py": "f" * 64})
    with pytest.raises(ValueError, match="reviewed evidence wiring"):
        pilot.prepare(f_root, REPO, tmp_path / "a/pilot")
    f_root, _ = f_study(tmp_path / "b")
    for tree in ("src", "derived"):   # identical drift in both trees is still drift from the plan
        (tmp_path / "b" / tree / "skillopt/continual_eval/runner.py").write_text("x = 2\n")
    with pytest.raises(ValueError, match="drifted from its plan"):
        pilot.prepare(f_root, REPO, tmp_path / "b/pilot")


def test_arm_a_evaluation_must_bind_to_its_request_and_output(tmp_path):
    f_root, _ = f_study(tmp_path)
    stage_dir = f_root / pilot.STAGE
    (stage_dir / "evaluation-bigcodebench.json").write_text(json.dumps(seal({"rows": rows(NO_SKILL)})))
    with pytest.raises(ValueError, match="Arm A evaluation does not bind"):
        pilot.prepare(f_root, REPO, tmp_path / "pilot")


def test_source_verification_requires_the_frozen_reference_plan(tmp_path):
    f_root, _ = f_study(tmp_path)
    plan = read_json(tmp_path / "noskill/plan.json", sealed=True)
    # An unbound plan that matches drifted sources must not vouch for them.
    (tmp_path / "noskill/plan.json").write_text(json.dumps(seal({**{k: v for k, v in plan.items() if k != "record_hash"}, "other": 1})))
    with pytest.raises(ValueError, match="not the frozen reference plan"):
        pilot.prepare(f_root, REPO, tmp_path / "pilot")


FAILED = 'Traceback (most recent call last):\n  File "/t/__test__.py", line 99, in test_case_1\nAssertionError: 3 != 4\n'


def execution(manifest_hash, *, role="train"):
    return seal({"request": {"role": role, "manifest_hash": manifest_hash},
                 "prediction": {"output": "def f():\n    return 0\n"},
                 "score": {"status": "fail", "metrics": {"details": {"test_case_1": FAILED, "ALL": "raw"}}}})


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    f_root, arm_a = f_study(tmp_path)
    pilot.prepare(f_root, REPO, tmp_path / "pilot")
    calls = {"learning": 0, "invoke": [], "skill": "B skill", "arm_a_rows": ARM_A}

    def learning(value, panel, output, repo=None):
        calls["learning"] += 1
        recorded = {"evaluations/train.json": execution(value["record_hash"]),
                    "evaluations/selection.json": execution(value["record_hash"], role="selection")}
        return learning_result(Path(output), value, calls["skill"], evaluations=recorded)

    def invoke(reference, operation, request, output, *, log):
        request = read_json(request, sealed=True)
        calls["invoke"].append((operation, request))
        value = seal({"rows": rows(calls["arm_a_rows"] if request["chain"] == ["A skill"] else ARM_B)})
        write_json(output, value)
        return value

    monkeypatch.setattr(learner, "run_stage", learning)
    monkeypatch.setattr(sequence, "_invoke", invoke)
    for name in ("check_client_service", "require_safe_handoff", "verify_service"):
        monkeypatch.setattr(sequence, name, lambda *a, **k: None)
    return f_root, arm_a, calls


def test_run_evaluates_arm_b_through_the_derived_source_once(prepared, tmp_path):
    _, _, calls = prepared
    result = pilot.run(tmp_path / "pilot", tmp_path / "repo")
    # Arm A is recomputed by the frozen worker before any paid learning starts.
    assert [(op, r["chain"]) for op, r in calls["invoke"]] == [("verify-evaluation", ["A skill"]),
                                                               ("evaluate", ["B skill"])]
    assert calls["invoke"][1][1]["reference"]["evaluation_source"] == str(tmp_path / "derived")
    assert result["skill_bytes"] == len("B skill") and not result["evaluation_reused_no_skill"]
    assert pilot.run(tmp_path / "pilot", tmp_path / "repo") == result
    assert calls["learning"] == 1 and [op for op, _ in calls["invoke"]][2:] == ["verify-evaluation"]


def test_arm_a_must_reproduce_before_paid_learning(prepared, tmp_path):
    _, _, calls = prepared
    calls["arm_a_rows"] = NO_SKILL
    with pytest.raises(ValueError, match="Arm A evaluation does not reproduce"):
        pilot.run(tmp_path / "pilot", tmp_path / "repo")
    assert calls["learning"] == 0


@pytest.mark.parametrize("skill", ["B skill", ""])
def test_replay_and_report_recheck_frozen_sources(prepared, tmp_path, monkeypatch, skill):
    _, _, calls = prepared
    calls["skill"] = skill
    result = pilot.run(tmp_path / "pilot", tmp_path / "repo")
    assert result["evaluation_reused_no_skill"] is (not skill)
    (tmp_path / "derived/skillopt/continual_eval/runner.py").write_text("x = 3\n")
    for call in (lambda: pilot.run(tmp_path / "pilot", tmp_path / "repo"), lambda: pilot.report(tmp_path / "pilot")):
        with pytest.raises(ValueError, match="outside the Skill budget"):
            call()
    (tmp_path / "derived/skillopt/continual_eval/runner.py").write_text("x = 1\n")
    monkeypatch.setattr(pilot, "native_sources", lambda: {"changed": "0" * 64})
    for call in (lambda: pilot.run(tmp_path / "pilot", tmp_path / "repo"), lambda: pilot.report(tmp_path / "pilot")):
        with pytest.raises(ValueError, match="Native optimizer sources changed"):
            call()


def test_a_stale_evaluation_request_is_refused(prepared, tmp_path):
    write_json(tmp_path / "pilot/requests/evaluate.json", seal({"chain": ["another skill"]}))
    with pytest.raises(ValueError, match="stale"):
        pilot.run(tmp_path / "pilot", tmp_path / "repo")


def test_report_pairs_both_arms_and_detects_tampering(prepared, tmp_path):
    pilot.run(tmp_path / "pilot", tmp_path / "repo")
    # Unrecorded executions are not learning evidence and are never counted.
    write_json(tmp_path / "pilot/learning/evaluations/unrecorded.json", execution("0" * 64))
    report = pilot.report(tmp_path / "pilot")
    comparisons = report["comparisons"]
    assert comparisons["a_vs_no_skill"]["all"]["positions"]["win"] == 2
    assert comparisons["b_vs_no_skill"]["all"]["positions"]["win"] == 4
    assert comparisons["b_vs_a"]["all"]["positions"] == {"win": 2, "loss": 0, "tie": 6, "unknown": 0, "unscored": 0}
    # Every fixture family is a planned learning family: nothing is left as held-out.
    assert report["learning_family_excluded_positions"] == 0
    coverage = report["arms"]["b_execution_evidence"]["evidence_coverage"]
    assert coverage == {"failed_train_executions": 1, "with_evidence": 1, "loci": {"hidden_test_assertion": 1}}
    assert report["histories_per_arm"] == 1 and not report["significance_claimed"]
    (tmp_path / "pilot/learning/native/0/result.json").unlink()
    with pytest.raises(ValueError, match="artifacts are missing"):
        pilot.report(tmp_path / "pilot")


def test_report_detects_a_substituted_evaluation(prepared, tmp_path):
    pilot.run(tmp_path / "pilot", tmp_path / "repo")
    # Bypass the immutable writer, as an out-of-band tamper would.
    (tmp_path / "pilot/evaluation-bigcodebench.json").write_text(json.dumps(seal({"rows": rows(NO_SKILL)})))
    with pytest.raises(ValueError, match="substituted"):
        pilot.report(tmp_path / "pilot")


def test_coverage_refuses_executions_another_manifest_authorized(prepared, tmp_path):
    pilot.run(tmp_path / "pilot", tmp_path / "repo")
    root, _, _, arm_b = pilot._load(tmp_path / "pilot")
    learning = read_json(root / "learning/result.json", sealed=True)
    write_json(root / "learning/evaluations/foreign.json", execution("0" * 64))
    foreign = {**learning, "artifacts": {**learning["artifacts"], "evaluations/foreign.json": "unused"}}
    with pytest.raises(ValueError, match="not authorized by arm B"):
        pilot._evidence_coverage(root, arm_b, foreign)
